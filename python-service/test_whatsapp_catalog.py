"""WAHA catalog menu cannot send, mutate stock or choose workspace via URL."""
import os
import re
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import app
from whatsapp_catalog import MENU, issue_secret, token_digest, product_view, menu_action


class WhatsAppCatalogContracts(unittest.TestCase):
    def test_server_generated_secret_never_is_short(self):
        secret = issue_secret()
        self.assertRegex(secret, r"^[A-Za-z0-9_-]{64}$")
        self.assertEqual(len(token_digest(secret)), 64)
        self.assertNotEqual(token_digest(secret), token_digest(issue_secret()))

    def test_menu_actions_never_send(self):
        self.assertEqual(len(MENU), 5)
        self.assertEqual(menu_action("2"), "availability")
        self.assertEqual(menu_action("5"), "human_handoff")
        for choice in ("0", "1", "2", "3", "4", "5"):
            self.assertNotIn("send", menu_action(choice))

    def test_products_distinguish_stock_and_services(self):
        base = {"nome": "Cuscuz", "tipo": "Produto", "preco": Decimal("14.50"), "estoque": 2}
        self.assertEqual(product_view(base)["disponibilidade"], "em_estoque")
        self.assertEqual(product_view({**base, "estoque": 0})["disponibilidade"], "nao_confirmada")
        self.assertEqual(
            product_view({**base, "tipo": "Serviço", "estoque": None})["disponibilidade"],
            "servico_sem_estoque",
        )
        self.assertEqual(product_view(base)["preco"], "14.50")

    def test_technical_api_closed_without_explicit_configuration(self):
        with patch.dict(os.environ, {
            "SOCIALMEI_WA_CATALOG_ENABLED": "false",
            "SOCIALMEI_AUTH_ENABLED": "true",
            "SOCIALMEI_SHARED_DATA_ENABLED": "true",
            "SOCIALMEI_AUTH_ORIGIN": "https://app.example.com",
        }):
            client = TestClient(app, base_url="https://app.example.com")
            response = client.get(
                "/api/v1/integracoes/whatsapp/menu?instancia=testing&opcao=1",
                headers={"Authorization": "Bearer " + issue_secret()},
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(client.get("/api/v1/whatsapp/catalog/access").status_code, 401)


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL", "").strip(), "Disposable PostgreSQL required")
class WhatsAppCatalogDatabaseTests(unittest.TestCase):
    """Owner-issued bearer reads one real workspace and revocation takes effect."""

    import test_account_auth as account_fixtures

    setUpClass = classmethod(account_fixtures.AccountDatabaseTests.setUpClass.__func__)
    setUp = account_fixtures.AccountDatabaseTests.setUp
    login = account_fixtures.AccountDatabaseTests.login
    invited = account_fixtures.AccountDatabaseTests.invited
    register = account_fixtures.AccountDatabaseTests.register

    def test_channel_status_exposes_unprovisioned_channels_only_to_its_owner(self):
        import psycopg
        first = self.register("wa-manager@example.test")
        other = self.register("wa-other@example.test")
        with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as conn:
            channel = conn.execute(
                "INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,nome,ativo) "
                "VALUES(%s,'private-instance','main','Loja',false) RETURNING id",
                (first.identity['negocio']['id'],),
            ).fetchone()[0]
        data = first.get('/api/v1/whatsapp/catalog/access').json()
        self.assertEqual([r['channel_id'] for r in data['channels']], [channel])
        self.assertFalse(data['channels'][0]['active'])
        self.assertFalse(data['channels'][0]['enabled'])
        self.assertFalse(data['channels'][0]['credential_configured'])
        self.assertEqual(other.get('/api/v1/whatsapp/catalog/access').json()['channels'], [])
        self.assertNotIn('token', str(data))
        self.assertEqual(first.post('/api/v1/whatsapp/catalog/access', json={'channel_id':channel}).status_code,404)
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='member' WHERE user_id=%s",(first.identity['usuario']['id'],))
        self.assertEqual(first.get('/api/v1/whatsapp/catalog/access').status_code,403)

    def test_rotation_and_revocation_are_audited_without_storing_plain_bearer(self):
        import psycopg
        first = self.register("wa-audited@example.test")
        wid = first.identity['negocio']['id']
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
            channel = conn.execute("INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,ativo) VALUES(%s,'audit','main',true) RETURNING id",(wid,)).fetchone()[0]
        tokens = [first.post('/api/v1/whatsapp/catalog/access',json={'channel_id':channel}).json()['token_once'] for _ in range(2)]
        self.assertNotEqual(*tokens)
        self.assertNotIn(tokens[1], first.get('/api/v1/whatsapp/catalog/access').text)
        self.assertEqual(first.delete('/api/v1/whatsapp/catalog/access/'+str(channel)).status_code,204)
        with psycopg.connect(os.environ['TEST_DATABASE_URL']) as conn:
            actions = [r[0] for r in conn.execute("SELECT acao FROM socialmei.auth_auditoria WHERE user_id=%s AND acao LIKE 'whatsapp_catalog_%%' ORDER BY id", (first.identity['usuario']['id'],)).fetchall()]
        self.assertEqual(actions,['whatsapp_catalog_rotated','whatsapp_catalog_rotated','whatsapp_catalog_revoked'])

    def test_real_catalog_isolation_and_revocation(self):
        import psycopg
        from fastapi.testclient import TestClient

        flag = patch.dict(os.environ, {"SOCIALMEI_WA_CATALOG_ENABLED": "true"})
        flag.start()
        self.addCleanup(flag.stop)
        first = self.register("first-whatsapp@example.test")
        second = self.register("second-whatsapp@example.test")
        workspace_a = first.identity["negocio"]["id"]
        workspace_b = second.identity["negocio"]["id"]
        with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as conn:
            channel_a = conn.execute(
                "INSERT INTO socialmei.crm_canais (workspace_id,instancia,sessao,ativo) "
                "VALUES (%s,'whatsapp-a','main',TRUE) RETURNING id",
                (workspace_a,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO socialmei.crm_canais (workspace_id,instancia,sessao,ativo) "
                "VALUES (%s,'whatsapp-b','main',TRUE)",
                (workspace_b,),
            )
        for client, name, stock in ((first, "Arroz do A", 7), (second, "Arroz do B", 99)):
            result = client.post(
                "/api/v1/produtos",
                json={"nome": name, "tipo": "Produto", "preco": 12.5,
                      "estoque": stock, "minimo": 0},
            )
            self.assertEqual(result.status_code, 201, result.text)

        created = first.post(
            "/api/v1/whatsapp/catalog/access", json={"channel_id": channel_a}
        )
        self.assertEqual(created.status_code, 200, created.text)
        token = created.json()["token_once"]
        headers = {"Authorization": "Bearer " + token}
        unauthenticated = TestClient(first.app, base_url="https://app.example.com")
        route = "/api/v1/integracoes/whatsapp/menu?instancia=whatsapp-a&opcao=2&produto=Arroz"
        result = unauthenticated.get(route, headers=headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual([p["nome"] for p in result.json()["items"]], ["Arroz do A"])
        self.assertEqual(result.json()["items"][0]["estoque"], 7)
        self.assertEqual(result.headers.get("cache-control"), "no-store")
        self.assertEqual(unauthenticated.get(route).status_code, 401)
        self.assertEqual(
            unauthenticated.get(route.replace("whatsapp-a", "whatsapp-b"), headers=headers).status_code,
            401,
        )
        self.assertEqual(
            unauthenticated.get("/api/v1/produtos", headers=headers).status_code, 401
        )
        self.assertEqual(second.delete("/api/v1/whatsapp/catalog/access/" + str(channel_a)).status_code, 404)
        self.assertEqual(first.delete("/api/v1/whatsapp/catalog/access/" + str(channel_a)).status_code, 204)
        self.assertEqual(unauthenticated.get(route, headers=headers).status_code, 401)
