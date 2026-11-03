"""Service scheduling with disposable PostgreSQL and independent real sessions."""

import unittest
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import psycopg
from pydantic import ValidationError

import appointments
import test_account_auth as accounts
from catalog_data import ProdutoCreate
from product_import import ImportItem, snapshot_and_hash
from workspace_transfer import TransferPacket, packet_fingerprint
from test_workspace_transfer import sample

PATH = "/api/v1/agenda"
RANGE = "?from_date=2026-11-01&to_date=2026-11-30"


def booking(**changes):
    return {"operation_id": str(uuid4()), "cliente_id": 1, "servico_id": 1,
            "resource_id": str(uuid4()), "scheduled_for": "2026-11-05T09:00:00-03:00", **changes}


class AppointmentValidationTests(unittest.TestCase):
    def test_optional_duration_preserves_legacy_import_and_transfer_receipts(self):
        item = ImportItem(local_id=1, produto=ProdutoCreate(nome="Item", preco=10))
        snapshot, digest = snapshot_and_hash(item)
        legacy = item.model_dump(mode="json")
        legacy["produto"].pop("duracao_minutos")
        expected = hashlib.sha256(json.dumps(legacy,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
        self.assertEqual(digest,expected)
        self.assertNotIn("duracao_minutos",snapshot["produto"])
        service = ImportItem(local_id=1,produto=ProdutoCreate(nome="Service",tipo="Serviço",preco=10,duracao_minutos=30))
        self.assertEqual(snapshot_and_hash(service)[0]["produto"]["duracao_minutos"],30)
        packet = TransferPacket.model_validate(sample())
        legacy_packet = packet.model_dump(mode="json",exclude={"exportado_em"})
        for product in legacy_packet["produtos"]:
            product.pop("duracao_minutos")
        for name in ("clientes","produtos","vendas","financeiro"):
            legacy_packet[name].sort(key=lambda r:r["id"])
        expected = hashlib.sha256(json.dumps(legacy_packet,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()
        self.assertEqual(packet_fingerprint(packet),expected)

    def test_explicit_zone_ids_duration_and_payload_boundaries(self):
        for change in ({"scheduled_for": "2026-11-05T09:00:00"}, {"scheduled_for": 1},
                       {"cliente_id": True}, {"servico_id": 0}, {"workspace_id": 2},
                       {"notes": "private\x00text"}, {"notes": "\ud800"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                appointments.AppointmentCreate.model_validate(booking(**change))
        self.assertEqual(appointments.AppointmentCreate.model_validate(booking()).scheduled_for.utcoffset(), timedelta(hours=-3))
        for duration in (0, 1441, True):
            with self.subTest(duration=duration), self.assertRaises(ValidationError):
                ProdutoCreate(nome="Serviço", tipo="Serviço", preco=0, duracao_minutos=duration)
        with self.assertRaises(ValidationError):
            ProdutoCreate(nome="Produto", preco=1, duracao_minutos=30)

    def test_updates_reject_null_invalid_and_empty_changes(self):
        for change in ({}, {"status": None}, {"scheduled_for": None}, {"status": "sent"},
                       {"scheduled_for": "2026-11-05T09:00:00"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                appointments.AppointmentUpdate.model_validate({"expected_revision": 1, **change})
        with self.assertRaises(ValidationError):
            appointments.ResourceUpdate(expected_revision=1, ativo=None)


@unittest.skipUnless(accounts.DB, "Disposable PostgreSQL required")
class AppointmentDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        self.client = self.admin_client
        self.person = self.post("/api/v1/clientes", {"nome": "Cliente fictício Sorria"})
        self.service = self.post("/api/v1/produtos", {"nome": "Consulta fictícia", "tipo": "Serviço", "preco": 80, "duracao_minutos": 30})
        self.resource_payload = {"operation_id": str(uuid4()), "nome": "Profissional fictício A"}
        self.resource = self.post(PATH+"/resources", self.resource_payload)

    def post(self, path, payload, client=None):
        response = (client or self.client).post(path, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def payload(self, **changes):
        return booking(cliente_id=self.person["id"], servico_id=self.service["id"], resource_id=self.resource["id"], **changes)

    def test_complete_persistent_journey_history_replay_and_cancel(self):
        payload = self.payload()
        row = self.post(PATH+"/appointments", payload)
        self.assertEqual(row["duration_minutes"], 30)
        self.assertEqual(row["ends_at"], "2026-11-05T12:30:00+00:00")
        self.assertNotIn("creation_fingerprint", row)
        self.assertEqual(self.post(PATH+"/appointments", {**payload, "scheduled_for": "2026-11-05T12:00:00Z"}), row)
        fresh = self.login("admin@example.com")
        self.assertEqual(fresh.get(PATH+"/appointments"+RANGE).json()["items"], [row])
        url = PATH+"/appointments/"+row["id"]
        moved = fresh.patch(url, json={"expected_revision": 1, "scheduled_for": "2026-11-06T10:00:00-03:00"})
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["revision"], 2)
        self.assertEqual(fresh.patch(url, json={"expected_revision": 1, "status": "cancelled"}).status_code, 409)
        cancelled = fresh.patch(url, json={"expected_revision": 2, "status": "cancelled"})
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(fresh.get(PATH+"/appointments"+RANGE).json()["items"], [])
        self.assertEqual(fresh.get(PATH+"/appointments"+RANGE+"&include_cancelled=true").json()["items"][0]["status"], "cancelled")
        history = fresh.get(url+"/history").json()["items"]
        self.assertEqual([r["revision"] for r in history], [1,2,3])
        self.assertEqual([r["status"] for r in history], ["pending","pending","cancelled"])
        self.assertEqual(self.post(PATH+"/appointments", payload)["status"], "cancelled")

    def test_overlap_boundary_distinct_resources_and_concurrent_booking(self):
        first, second = self.payload(), self.payload()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda p:self.client.post(PATH+"/appointments",json=p), [first,second]))
        self.assertEqual(sorted(r.status_code for r in responses), [201,409])
        winner = next(r.json() for r in responses if r.status_code==201)
        self.post(PATH+"/appointments", self.payload(scheduled_for="2026-11-05T09:30:00-03:00"))
        conflict = self.client.patch(PATH+"/appointments/"+winner["id"], json={"expected_revision":1,"scheduled_for":"2026-11-05T09:15:00-03:00"})
        self.assertEqual(conflict.status_code,409)
        resource2 = self.post(PATH+"/resources", {"operation_id":str(uuid4()),"nome":"Profissional B"})
        self.post(PATH+"/appointments", {**self.payload(),"resource_id":resource2["id"]})

    def test_concurrent_retry_creates_only_one_history_entry(self):
        payload = self.payload()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _:self.client.post(PATH+"/appointments",json=payload), range(2)))
        self.assertEqual([r.status_code for r in responses], [201,201])
        self.assertEqual(responses[0].json(),responses[1].json())
        url = PATH+"/appointments/"+payload["operation_id"]
        self.assertEqual(len(self.client.get(url+"/history").json()["items"]),1)
        self.assertEqual(self.client.post(PATH+"/appointments",json={**payload,"notes":"Different"}).status_code,409)

    def test_workspace_client_service_resource_and_history_isolation(self):
        row = self.post(PATH+"/appointments", self.payload())
        other = self.register("other-sorria@example.test")
        self.assertEqual(other.get(PATH+"/appointments"+RANGE).json()["items"],[])
        self.assertEqual(other.get(PATH+"/resources").json()["items"],[])
        self.assertEqual(other.get(PATH+"/appointments/"+row["id"]+"/history").status_code,404)
        self.assertEqual(other.patch(PATH+"/appointments/"+row["id"],json={"expected_revision":1,"status":"cancelled"}).status_code,404)
        self.assertEqual(other.post(PATH+"/appointments",json=self.payload()).status_code,422)
        person2=self.post("/api/v1/clientes",{"nome":"Other"},other)
        service2=self.post("/api/v1/produtos",{"nome":"Other service","tipo":"Serviço","preco":0,"duracao_minutos":20},other)
        for change in ({"cliente_id":person2["id"]},{"servico_id":service2["id"]}):
            self.assertEqual(self.client.post(PATH+"/appointments",json={**self.payload(),**change}).status_code,422)
        with self.assertRaises(psycopg.errors.ForeignKeyViolation),psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.agenda_appointments SET cliente_id=%s WHERE id=%s",(person2["id"],row["id"]))

    def test_availability_inactive_resources_and_legacy_service_duration(self):
        query={"resource_id":self.resource["id"],"servico_id":self.service["id"],"scheduled_for":"2026-11-05T09:00:00-03:00"}
        self.assertTrue(self.client.get(PATH+"/availability",params=query).json()["available"])
        row=self.post(PATH+"/appointments",self.payload())
        check=self.client.get(PATH+"/availability",params=query)
        self.assertFalse(check.json()["available"])
        self.assertFalse(check.json()["reservation_created"])
        self.assertEqual(len(self.client.get(PATH+"/appointments"+RANGE).json()["items"]),1)
        self.assertEqual(self.client.patch(PATH+"/resources/"+self.resource["id"],json={"expected_revision":1,"ativo":False}).status_code,200)
        self.assertEqual(self.client.post(PATH+"/appointments",json=self.payload()).status_code,422)
        url=PATH+"/appointments/"+row["id"]
        self.assertEqual(self.client.patch(url,json={"expected_revision":1,"status":"cancelled"}).status_code,200)
        self.assertEqual(self.client.patch(url,json={"expected_revision":2,"status":"pending"}).status_code,422)
        self.client.patch(PATH+"/resources/"+self.resource["id"],json={"expected_revision":2,"ativo":True})
        self.client.patch("/api/v1/produtos/"+str(self.service["id"]),json={"expected_version":self.service["versao"],"duracao_minutos":None})
        self.assertEqual(self.client.post(PATH+"/appointments",json=self.payload()).status_code,422)

    def test_snapshot_survives_catalog_edits_and_deletion_and_viewer_cannot_write(self):
        row=self.post(PATH+"/appointments",self.payload())
        change=self.client.patch("/api/v1/produtos/"+str(self.service["id"]),json={"expected_version":self.service["versao"],"nome":"New name","preco":100,"duracao_minutos":90})
        self.assertEqual(change.status_code,200,change.text)
        changed=self.client.get(PATH+"/appointments"+RANGE).json()["items"][0]
        self.assertEqual((changed["service_name"],changed["duration_minutes"],changed["price"]),("Consulta fictícia",30,80))
        removed=self.client.delete("/api/v1/produtos/"+str(self.service["id"])+"?expected_version="+str(change.json()["versao"]))
        self.assertEqual(removed.status_code,204,removed.text)
        self.assertIsNone(self.client.get(PATH+"/appointments"+RANGE).json()["items"][0]["servico_id"])
        wid=self.client.identity["negocio"]["id"];uid=self.client.identity["usuario"]["id"]
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE workspace_id=%s AND user_id=%s",(wid,uid))
        self.assertEqual(self.client.get(PATH+"/appointments"+RANGE).status_code,200)
        self.assertEqual(self.client.patch(PATH+"/appointments/"+row["id"],json={"expected_revision":1,"status":"cancelled"}).status_code,403)
        self.assertEqual(self.client.post(PATH+"/resources",json={"operation_id":str(uuid4()),"nome":"No"}).status_code,403)

    def test_resource_idempotency_revision_and_invalid_ranges(self):
        self.assertEqual(self.post(PATH+"/resources",self.resource_payload),self.resource)
        self.assertEqual(self.client.post(PATH+"/resources",json={**self.resource_payload,"nome":"Other"}).status_code,409)
        url=PATH+"/resources/"+self.resource["id"]
        response=self.client.patch(url,json={"expected_revision":1,"nome":"Changed"})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.patch(url,json={"expected_revision":1,"ativo":False}).status_code,409)
        for query in ("?from_date=2026-12-01&to_date=2026-11-01","?from_date=2025-01-01&to_date=2026-11-01","?from_date=9999-12-31&to_date=9999-12-31"):
            self.assertEqual(self.client.get(PATH+"/appointments"+query).status_code,422)


if __name__ == "__main__":
    unittest.main()
