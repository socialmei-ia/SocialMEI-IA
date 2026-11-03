"""Manual CRM association uses disposable data and existing inbox/session guards."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from pydantic import ValidationError

import inbox_customer
import test_account_auth as accounts
from account_auth import COOKIE
from test_message_enrichment import MODE, message

BASE = "/api/v1/message-enrichment"


class CustomerLinkValidationTests(unittest.TestCase):
    def test_strict_required_nullable_customer_and_revision(self):
        for values in ({"expected_revision":1}, {"expected_revision":True,"cliente_id":1},
                       {"expected_revision":-1,"cliente_id":1}, {"expected_revision":1,"cliente_id":True},
                       {"expected_revision":1,"cliente_id":0}, {"expected_revision":1,"cliente_id":"1"},
                       {"expected_revision":1,"cliente_id":None,"workspace_id":2}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                inbox_customer.CustomerLink.model_validate(values)
        self.assertIsNone(inbox_customer.CustomerLink(expected_revision=0,cliente_id=None).cliente_id)

    def test_missing_session_and_database_failure_never_leak_details(self):
        with patch.dict(os.environ, {**accounts.ENV, **MODE}, clear=True):
            client=TestClient(accounts.app,base_url=accounts.ORIGIN)
            with patch("message_enrichment.connect",side_effect=AssertionError("No storage")):
                self.assertEqual(client.get(BASE+"/conversations/1/customer").status_code,401)
            user={"id":1,"workspace_id":1,"role":"owner","administrador_plataforma":False}
            client.cookies.set(COOKIE,"a"*64)
            with patch("account_auth.session_identity",return_value=user), patch("message_enrichment.connect",side_effect=psycopg.OperationalError("private-database-marker")):
                response=client.get(BASE+"/conversations/1/customer")
                self.assertEqual(response.status_code,503)
                self.assertEqual(response.headers["cache-control"],"no-store")
                self.assertNotIn("private-database-marker",response.text)


@unittest.skipUnless(accounts.DB,"Disposable PostgreSQL required")
class CustomerLinkDatabaseTests(unittest.TestCase):
    setUpClass=classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login=accounts.AccountDatabaseTests.login
    invited=accounts.AccountDatabaseTests.invited
    register=accounts.AccountDatabaseTests.register

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        env=patch.dict(os.environ,MODE);env.start();self.addCleanup(env.stop)
        self.client=self.admin_client
        self.body=message()
        received=self.client.post(BASE+"/synthetic-messages",json=self.body)
        self.assertEqual(received.status_code,200,received.text)
        self.conversation=received.json()
        self.url=BASE+"/conversations/"+str(self.conversation["conversation_id"])+"/customer"
        response=self.client.post("/api/v1/clientes",json={"nome":"Cliente fictício","telefone":"85999990001","email":"fixture@example.test"})
        self.assertEqual(response.status_code,201,response.text)
        self.customer=response.json()
        self.workspace=self.client.identity["negocio"]["id"]

    def link(self,customer=None,revision=None):
        return self.client.patch(self.url,json={"expected_revision":revision if revision is not None else self.conversation["revision"],"cliente_id":self.customer["id"] if customer is None else customer})

    def test_link_unlink_persist_noop_and_preserve_message_labels(self):
        before=self.client.get(BASE+"/conversations").json()["items"][0]
        empty=self.client.get(self.url)
        self.assertEqual(empty.status_code,200,empty.text)
        self.assertIsNone(empty.json()["customer"])
        response=self.link()
        self.assertEqual(response.status_code,200,response.text)
        linked=response.json()
        self.assertEqual(linked,{"conversation_id":before["id"],"revision":before["revision"]+1,"cliente_id":self.customer["id"],"customer":{"id":self.customer["id"],"nome":"Cliente fictício","telefone":"85999990001","email":"fixture@example.test"}})
        self.assertEqual(response.headers["cache-control"],"no-store")
        self.assertEqual(self.login("admin@example.com").get(self.url).json(),linked)
        noop=self.link(revision=linked["revision"])
        self.assertEqual(noop.json(),linked)
        after=self.client.get(BASE+"/conversations").json()["items"][0]
        for key in ("contact_name","contact_ref","account_ref","channel","messages"):
            self.assertEqual(after[key],before[key])
        unlink=self.client.patch(self.url,json={"expected_revision":linked["revision"],"cliente_id":None})
        self.assertEqual(unlink.status_code,200,unlink.text)
        self.assertIsNone(unlink.json()["customer"])
        self.assertEqual(unlink.json()["revision"],linked["revision"]+1)
        self.assertEqual(self.client.get(BASE+"/conversations").json()["items"][0]["messages"],before["messages"])

    def test_workspace_foreign_customer_conversation_and_database_fk_are_rejected(self):
        other=self.register("other-link@example.test")
        foreign=other.post("/api/v1/clientes",json={"nome":"Outro cliente"}).json()
        self.assertEqual(self.link(customer=foreign["id"]).status_code,404)
        self.assertEqual(other.get(self.url).status_code,404)
        self.assertEqual(other.patch(self.url,json={"expected_revision":self.conversation["revision"],"cliente_id":foreign["id"]}).status_code,404)
        with self.assertRaises(psycopg.errors.ForeignKeyViolation),psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.me_conversations SET cliente_id=%s WHERE workspace_id=%s AND id=%s",(foreign["id"],self.workspace,self.conversation["conversation_id"]))
        self.assertIsNone(self.client.get(self.url).json()["cliente_id"])

    def test_viewer_read_only_member_writes_origin_and_csrf_required(self):
        uid=self.client.identity["usuario"]["id"]
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE workspace_id=%s AND user_id=%s",(self.workspace,uid))
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(self.link().status_code,403)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='member' WHERE workspace_id=%s AND user_id=%s",(self.workspace,uid))
        self.assertEqual(self.link().status_code,200)
        row=self.client.get(self.url).json()
        for headers in ({"Origin":"https://foreign.example.test"},{"X-SocialMEI-CSRF":"invalid"}):
            rejected=self.client.patch(self.url,json={"expected_revision":row["revision"],"cliente_id":None},headers=headers)
            self.assertEqual(rejected.status_code,403,rejected.text)
        self.assertEqual(self.client.get(self.url).json(),row)

    def test_customer_deletion_unlinks_increments_revision_preserves_messages_and_workspace(self):
        linked=self.link().json()
        before=self.client.get(BASE+"/conversations").json()["items"][0]
        removed=self.client.delete("/api/v1/clientes/"+str(self.customer["id"])+"?expected_version="+str(self.customer["versao"]))
        self.assertEqual(removed.status_code,204,removed.text)
        current=self.client.get(self.url).json()
        self.assertIsNone(current["cliente_id"])
        self.assertIsNone(current["customer"])
        self.assertEqual(current["revision"],linked["revision"]+1)
        stale=self.client.patch(self.url,json={"expected_revision":linked["revision"],"cliente_id":None})
        self.assertEqual(stale.status_code,409)
        after=self.client.get(BASE+"/conversations").json()
        self.assertEqual(after["workspace_id"],self.workspace)
        self.assertEqual(after["items"][0]["messages"],before["messages"])
        self.assertEqual(after["items"][0]["contact_name"],before["contact_name"])

    def test_new_incoming_message_invalidates_stale_revision_without_unlinking(self):
        linked=self.link().json()
        following={**message(),"text":"Segunda mensagem fictícia"}
        response=self.client.post(BASE+"/synthetic-messages",json=following)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()["conversation_id"],linked["conversation_id"])
        self.assertEqual(self.client.patch(self.url,json={"expected_revision":linked["revision"],"cliente_id":None}).status_code,409)
        current=self.client.get(self.url).json()
        self.assertEqual(current["cliente_id"],self.customer["id"])
        self.assertEqual(current["revision"],linked["revision"]+1)
        self.client.post(BASE+"/synthetic-messages",json=following)
        self.assertEqual(self.client.get(self.url).json(),current)

    def test_concurrent_links_use_compare_and_swap(self):
        other=self.client.post("/api/v1/clientes",json={"nome":"Segundo cliente fictício"}).json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda customer:self.link(customer=customer),[self.customer["id"],other["id"]]))
        self.assertEqual(sorted(r.status_code for r in responses),[200,409])
        winner=next(r.json() for r in responses if r.status_code==200)
        self.assertEqual(self.client.get(self.url).json(),winner)

    def test_origin_boundary_matches_inbox_visibility_not_just_workspace(self):
        with psycopg.connect(accounts.DB) as conn:
            instagram=conn.execute("INSERT INTO socialmei.me_conversations(workspace_id,channel,account_ref,contact_ref,contact_name,origin,revision) VALUES(%s,'instagram','instagram:123','instagram:456','IG fixture','instagram',1) RETURNING id",(self.workspace,)).fetchone()[0]
            waha=conn.execute("INSERT INTO socialmei.me_conversations(workspace_id,channel,account_ref,contact_ref,contact_name,origin,revision) VALUES(%s,'whatsapp','waha:111@c.us','waha:222@c.us','WA fixture','waha',1) RETURNING id",(self.workspace,)).fetchone()[0]
        for cid in (instagram,waha):
            url=BASE+"/conversations/"+str(cid)+"/customer"
            self.assertEqual(self.client.get(url).status_code,404)
            self.assertEqual(self.client.patch(url,json={"expected_revision":1,"cliente_id":self.customer["id"]}).status_code,404)
        with patch.dict(os.environ,{"SOCIALMEI_INSTAGRAM_INGRESS_MODE":"isolated","SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT":"isolated"}):
            self.assertEqual(self.client.get(BASE+"/conversations/"+str(instagram)+"/customer").status_code,200)
            self.assertEqual(self.client.get(BASE+"/conversations/"+str(waha)+"/customer").status_code,404)
        with patch.dict(os.environ,{"SOCIALMEI_MESSAGE_ENRICHMENT_MODE":"disabled","SOCIALMEI_WAHA_INGRESS_MODE":"isolated","SOCIALMEI_WAHA_LAB_ENVIRONMENT":"isolated"}):
            url=BASE+"/conversations/"+str(waha)+"/customer"
            response=self.client.patch(url,json={"expected_revision":1,"cliente_id":self.customer["id"]})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(self.client.get(self.url).status_code,404)
            self.assertEqual(self.client.get(BASE+"/conversations/"+str(instagram)+"/customer").status_code,404)


if __name__ == "__main__":
    unittest.main()
