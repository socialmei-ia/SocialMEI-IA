"""Workspace team grants, revocation and races in disposable PostgreSQL."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from app import app
from team_members import Grant, RoleChange
import test_account_auth as accounts

DB = accounts.DB
PATH = '/api/v1/team/members'


class TeamContracts(unittest.TestCase):
    def test_only_existing_email_and_nonprivileged_roles_are_accepted(self):
        self.assertEqual(Grant(email=' PESSOA@EXAMPLE.TEST ', role='member').email, 'pessoa@example.test')
        for data in ({'email':'invalid','role':'member'}, {'email':'a@example.test','role':'owner'},
                     {'email':'a@example.test','role':'admin'}, {'email':'a@example.test','role':'member','workspace_id':3}):
            with self.assertRaises(ValueError): Grant(**data)
        with self.assertRaises(ValueError): RoleChange(role='owner', expected_role='member')


@unittest.skipUnless(DB, 'TEST_DATABASE_URL not configured')
class TeamMembersDatabase(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def scoped(self, client):
        value = client.get('/api/v1/auth/me').json()
        client.identity = value
        client.headers['X-SocialMEI-Identity'] = f"{value['usuario']['id']}:{value['negocio']['id']}"
        client.headers['X-SocialMEI-CSRF'] = value['csrf_token']
        return client

    def grant(self, client, email='person@example.test', role='member'):
        return self.scoped(client).post(PATH, json={'email':email,'role':role})

    def role(self, workspace, user, role):
        with psycopg.connect(DB) as conn:
            conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE workspace_id=%s AND user_id=%s',
                         (role, workspace, user))

    def switch(self, client, workspace):
        response = self.scoped(client).post('/api/v1/auth/workspaces/switch', json={'workspace_id':workspace})
        self.assertEqual(response.status_code, 200)
        client.identity = response.json()
        client.headers['X-SocialMEI-Identity'] = f"{client.identity['usuario']['id']}:{workspace}"
        client.headers['X-SocialMEI-CSRF'] = client.identity['csrf_token']
        return client

    def test_grant_existing_account_is_idempotent_scoped_and_audited(self):
        person = self.register('person@example.test')
        owner = self.scoped(self.admin_client)
        first = self.grant(owner)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()['granted'])
        self.assertTrue(self.grant(owner).json()['already_member'])
        members = owner.get(PATH).json()
        self.assertTrue(members['can_manage'])
        self.assertEqual(len(members['items']),2)
        self.assertNotIn('senha',str(members))
        self.assertEqual(person.get(PATH).status_code,200)  # Own independent workspace.
        self.assertEqual(len(person.get(PATH).json()['items']),1)
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.users').fetchone()[0],2)
            self.assertEqual(conn.execute("SELECT count(*) FROM socialmei.auth_auditoria WHERE acao=%s",
                             (f"equipe:{owner.identity['negocio']['id']}:concedida",)).fetchone()[0],1)

    def test_only_owner_can_mutate_admin_can_list_member_cannot_list(self):
        person = self.register('person@example.test')
        self.assertEqual(self.grant(self.admin_client).status_code,200)
        uid = person.identity['usuario']['id']; wid=self.admin_client.identity['negocio']['id']
        self.switch(person,wid)
        for role in ('member','viewer','admin'):
            self.role(wid,uid,role)
            self.assertEqual(person.get(PATH).status_code,200 if role=='admin' else 403)
            self.assertEqual(person.post(PATH,json={'email':'other@example.test','role':'member'}).status_code,403)
        self.assertFalse(person.get(PATH).json()['can_manage'])

    def test_owner_admin_and_self_are_protected_and_foreign_members_are_hidden(self):
        person=self.register('person@example.test')
        owner=self.scoped(self.admin_client); owner_id=owner.identity['usuario']['id']
        for method,data in [('patch',{'role':'member','expected_role':'member'}),('delete',{'expected_role':'member'})]:
            self.assertEqual(owner.request(method,PATH+f'/{owner_id}',json=data).status_code,403)
            self.assertEqual(owner.request(method,PATH+f"/{person.identity['usuario']['id']}",json=data).status_code,404)
        self.grant(owner)
        self.role(owner.identity['negocio']['id'],person.identity['usuario']['id'],'admin')
        self.assertEqual(owner.request('DELETE',PATH+f"/{person.identity['usuario']['id']}",json={'expected_role':'member'}).status_code,403)

    def test_role_change_revokes_only_target_workspace_sessions(self):
        person=self.register('person@example.test'); other_session=self.login('person@example.test')
        uid=person.identity['usuario']['id']; own_wid=person.identity['negocio']['id']
        owner=self.scoped(self.admin_client); shared=owner.identity['negocio']['id']
        self.grant(owner); self.switch(person,shared)
        response=owner.patch(PATH+f'/{uid}',json={'role':'report_viewer','expected_role':'member'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(person.get('/api/v1/auth/me').status_code,401)
        self.assertEqual(other_session.get('/api/v1/auth/me').json()['negocio']['id'],own_wid)
        self.assertEqual(owner.patch(PATH+f'/{uid}',json={'role':'member','expected_role':'member'}).status_code,409)
        fresh=self.login('person@example.test'); self.switch(fresh,shared)
        self.assertEqual(fresh.get('/api/v1/clientes').status_code,403)
        self.assertEqual(fresh.get('/api/v1/reporting/overview').status_code,200)
        self.assertEqual(owner.request('DELETE',PATH+f'/{uid}',json={'expected_role':'report_viewer'}).status_code,204)
        self.assertEqual(fresh.get('/api/v1/auth/me').status_code,401)
        self.assertEqual(other_session.get('/api/v1/auth/me').status_code,200)
        self.assertEqual(self.scoped(other_session).post('/api/v1/auth/workspaces/switch',json={'workspace_id':shared}).status_code,403)

    def test_unknown_inactive_accounts_no_user_creation_and_csrf_stale_rejected(self):
        owner=self.scoped(self.admin_client)
        self.assertEqual(self.grant(owner,'missing@example.test').status_code,409)
        person=self.register('person@example.test')
        with psycopg.connect(DB) as conn:
            conn.execute('UPDATE socialmei.auth_credenciais SET ativo=false WHERE user_id=%s',(person.identity['usuario']['id'],))
        self.assertEqual(self.grant(owner).status_code,409)
        owner.headers['X-SocialMEI-CSRF']='wrong'
        self.assertEqual(owner.post(PATH,json={'email':'person@example.test','role':'member'}).status_code,403)
        self.scoped(owner);owner.headers['X-SocialMEI-Identity']='9:9'
        self.assertEqual(owner.post(PATH,json={'email':'person@example.test','role':'member'}).status_code,409)
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.users').fetchone()[0],2)

    def test_concurrent_grants_add_one_membership_and_one_audit(self):
        self.register('person@example.test')
        owner=self.scoped(self.admin_client)
        def attempt(_):
            client=TestClient(app,base_url=accounts.ORIGIN,headers=dict(owner.headers))
            client.cookies.update(owner.cookies)
            response=client.post(PATH,json={'email':'person@example.test','role':'member'})
            self.assertEqual(response.status_code,200,response.text)
            return response.json()['granted']
        with ThreadPoolExecutor(max_workers=3) as pool:
            result=list(pool.map(attempt,range(3)))
        self.assertEqual(sum(result),1)
        self.assertEqual(len(owner.get(PATH).json()['items']),2)

    def test_audit_failure_rolls_back_role_change_and_session_revocation(self):
        person=self.register('person@example.test'); self.grant(self.admin_client)
        uid=person.identity['usuario']['id'];owner=self.scoped(self.admin_client)
        self.switch(person,owner.identity['negocio']['id'])
        with psycopg.connect(DB) as conn:
            conn.execute("CREATE FUNCTION socialmei.team_audit_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.acao LIKE 'equipe:%:papel' THEN RAISE EXCEPTION 'fixture'; END IF; RETURN NEW; END $$")
            conn.execute('CREATE TRIGGER team_audit_test BEFORE INSERT ON socialmei.auth_auditoria FOR EACH ROW EXECUTE FUNCTION socialmei.team_audit_test()')
        try:
            response=owner.patch(PATH+f'/{uid}',json={'role':'report_viewer','expected_role':'member'})
            self.assertEqual(response.status_code,503)
            self.assertEqual(person.get('/api/v1/auth/me').json()['papel'],'member')
        finally:
            with psycopg.connect(DB) as conn:
                conn.execute('DROP TRIGGER team_audit_test ON socialmei.auth_auditoria')
                conn.execute('DROP FUNCTION socialmei.team_audit_test()')

    def test_capacity_and_report_viewer_limits_do_not_create_partial_membership(self):
        person=self.register('person@example.test')
        owner=self.scoped(self.admin_client);workspace=owner.identity['negocio']['id']
        with psycopg.connect(DB) as conn:
            for i in range(49):
                uid=conn.execute('INSERT INTO socialmei.users(email,nome) VALUES(%s,%s) RETURNING id',
                                 (f'cap-{i}@example.test','Fixture')).fetchone()[0]
                conn.execute('INSERT INTO socialmei.auth_credenciais(user_id,senha_hash) VALUES(%s,%s)',(uid,self.hashed))
                conn.execute('INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,%s)',
                             (workspace,uid,'report_viewer' if i<20 else 'member'))
        self.assertEqual(self.grant(owner).status_code,429)
        self.assertEqual(len(owner.get(PATH).json()['items']),50)
        with psycopg.connect(DB) as conn:
            conn.execute("DELETE FROM socialmei.workspace_members WHERE workspace_id=%s AND role='member'",(workspace,))
        self.assertEqual(self.grant(owner,role='report_viewer').status_code,429)
        self.assertEqual(self.grant(owner).status_code,200)
        self.assertEqual(self.scoped(person).get(PATH).json()['workspace_id'],person.identity['negocio']['id'])

    def test_actor_throttle_limits_unknown_account_enumeration(self):
        owner=self.scoped(self.admin_client)
        statuses=[owner.post(PATH,json={'email':f'missing-{i}@example.test','role':'member'}).status_code for i in range(11)]
        self.assertEqual(statuses,[409]*10+[429])

    def test_concurrent_role_changes_use_expected_role_compare_and_swap(self):
        person=self.register('person@example.test');self.grant(self.admin_client)
        owner=self.scoped(self.admin_client);uid=person.identity['usuario']['id']
        def attempt(_):
            client=TestClient(app,base_url=accounts.ORIGIN,headers=dict(owner.headers))
            client.cookies.update(owner.cookies)
            return client.patch(PATH+f'/{uid}',json={'role':'report_viewer','expected_role':'member'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(attempt,range(2)))
        self.assertEqual(sorted(statuses),[200,409])


if __name__ == '__main__': unittest.main()
