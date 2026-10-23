"""Real sessions and tenant isolation; database cases run on PostgreSQL in CI."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from account_admin import create_admin, enable_user, reset_password
from account_auth import COOKIE, Password, Register, digest, hash_password, origin, verify_password
from app import app
from auth_context import principal
from fastapi.testclient import TestClient

DB = os.getenv("TEST_DATABASE_URL", "").strip()
ORIGIN = "https://app.example.com"
PASSWORD = "Private-test-password-123!"
HEADERS = {"Origin": ORIGIN, "X-SocialMEI-Client": "browser"}
ENV = {
    "SOCIALMEI_AUTH_ENABLED": "true",
    "SOCIALMEI_REGISTRATION_MODE": "invite",
    "SOCIALMEI_AUTH_ORIGIN": ORIGIN,
    "SOCIALMEI_SHARED_DATA_ENABLED": "true",
    "SOCIALMEI_WORKSPACE_SLUG": "team",
    "SOCIALMEI_N8N_READ_TOKEN": "technical-key-long-enough-for-private-test-123",
}


class PasswordPolicyTests(unittest.TestCase):
    def test_seven_rejected_eight_accepted(self):
        for value in (
            "FlorSol", "7392518", "12345678", "PASSWORD", "senha123", "aaaaaaaa", "x" * 129
        ):
            with self.subTest(), self.assertRaises(ValueError):
                hash_password(value)
            with self.assertRaises(ValueError):
                Register(nome="Teste", email="teste@example.test", senha=value)
            with self.assertRaises(ValueError):
                Password(atual="existing", nova=value)
        for value in ("FlorSol!", "73925186", "luaverde"):
            self.assertEqual(
                Register(nome="Teste", email="teste@example.test", senha=value).senha, value
            )
            self.assertEqual(Password(atual="existing", nova=value).nova, value)
            encoded = hash_password(value)
            self.assertTrue(encoded.startswith("$argon2"))
            self.assertTrue(verify_password(value, encoded))

    def test_existing_common_password_can_still_authenticate(self):
        from account_auth import HASHER

        self.assertTrue(verify_password("12345678", HASHER.hash("12345678")))


class AccountGuards(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(app, base_url=ORIGIN)

    def test_registration_policy_is_public_no_store_and_does_not_open_database(self):
        with patch(
            "account_auth.connect", side_effect=AssertionError("unexpected database")
        ):
            for mode in ("open", "invite", "invalid"):
                with self.subTest(mode=mode), patch.dict(
                    os.environ, {"SOCIALMEI_REGISTRATION_MODE": mode}
                ):
                    response = self.client.get("/api/v1/auth/registration")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.json(),
                        {"mode": "open" if mode == "open" else "invite"},
                    )
                    self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(
                self.client.post("/api/v1/auth/registration").status_code, 403
            )
            with patch.dict(os.environ, {"SOCIALMEI_AUTH_ENABLED": "false"}):
                self.assertEqual(
                    self.client.get("/api/v1/auth/registration").status_code, 503
                )

    def test_browser_session_probe_uses_200_null_without_a_valid_cookie(self):
        with patch(
            "account_auth.connect", side_effect=AssertionError("unexpected database")
        ):
            for token in ("", "invalid-token"):
                self.client.cookies.set(COOKIE, token)
                response = self.client.get("/api/v1/auth/session")
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json())
                self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(self.client.post("/api/v1/auth/session").status_code, 403)
            with patch.dict(os.environ, {"SOCIALMEI_AUTH_ENABLED": "false"}):
                self.assertEqual(
                    self.client.get("/api/v1/auth/session").status_code, 503
                )

    def test_missing_invite_cannot_bypass_restricted_mode(self):
        with patch("account_auth.throttle"), patch(
            "account_auth.connect", side_effect=AssertionError("unexpected database")
        ):
            response = self.client.post(
                "/api/v1/auth/register",
                headers=HEADERS,
                json={"nome": "Test", "email": "user@example.com", "senha": PASSWORD},
            )
            self.assertEqual(response.status_code, 400)

    def test_open_registration_still_rejects_foreign_origin_and_admin_fields(self):
        with patch.dict(os.environ, {"SOCIALMEI_REGISTRATION_MODE": "open"}), patch(
            "account_auth.connect", side_effect=AssertionError("unexpected database")
        ):
            data = {"nome": "Test", "email": "user@example.com", "senha": PASSWORD}
            self.assertEqual(
                self.client.post("/api/v1/auth/register", json=data).status_code, 403
            )
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/register",
                    headers=HEADERS,
                    json={**data, "administrador_plataforma": True},
                ).status_code,
                422,
            )

    def test_session_required_and_database_not_opened_for_missing_cookie(self):
        with patch(
            "account_auth.connect", side_effect=AssertionError("unexpected database")
        ):
            for module in [
                "clientes",
                "produtos",
                "vendas",
                "financeiro",
                "admin/users",
                "auth/me",
            ]:
                response = self.client.get("/api/v1/" + module)
                self.assertEqual(response.status_code, 401, response.text)
                self.assertEqual(response.headers["cache-control"], "no-store")

    def test_login_requires_same_origin_json_and_browser_header(self):
        data = {"email": "user@example.com", "senha": PASSWORD}
        with patch(
            "account_auth.connect", side_effect=AssertionError("unexpected database")
        ):
            for headers in [
                {},
                {"Origin": "https://evil.example", "X-SocialMEI-Client": "browser"},
                {"Origin": ORIGIN},
            ]:
                self.assertEqual(
                    self.client.post(
                        "/api/v1/auth/login", json=data, headers=headers
                    ).status_code,
                    403,
                )
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/login", data=data, headers=HEADERS
                ).status_code,
                403,
            )

    def test_validation_never_echoes_password_or_invite(self):
        data = {
            "email": "wrong",
            "senha": PASSWORD,
            "convite": "private-token",
            "nome": "Test",
        }
        response = self.client.post("/api/v1/auth/register", json=data, headers=HEADERS)
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(PASSWORD, response.text)
        self.assertNotIn("private-token", response.text)
        data = {
            "email": "user@example.com",
            "senha": PASSWORD,
            "administrador_plataforma": True,
        }
        self.assertEqual(
            self.client.post(
                "/api/v1/auth/login", json=data, headers=HEADERS
            ).status_code,
            422,
        )

    def test_bad_origin_configuration_fails_closed(self):
        for value in [
            "http://app.example.com",
            "https://app.example.com/path",
            "https://[",
            "https://app.example.com:bad",
            "https://user:pass@app.example.com",
        ]:
            with patch.dict(os.environ, {"SOCIALMEI_AUTH_ORIGIN": value}):
                self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 503)
        self.assertEqual(origin(), ORIGIN)

    def test_misspelled_activation_flag_does_not_reopen_shared_crm(self):
        with patch.dict(os.environ, {"SOCIALMEI_AUTH_ENABLED": "treu"}):
            self.assertEqual(self.client.get("/api/v1/clientes").status_code, 503)

    def test_technical_token_does_not_authenticate_crm_or_admin(self):
        with patch(
            "n8n_read.connect", side_effect=AssertionError("unexpected database")
        ):
            self.assertEqual(
                self.client.get("/api/v1/integracoes/resumo").status_code, 401
            )
            for path in ["clientes", "admin/users", "transferencias/preview"]:
                self.assertEqual(
                    self.client.get(
                        "/api/v1/" + path,
                        headers={"Authorization": "Bearer technical-token"},
                    ).status_code,
                    401,
                )

    def test_disabled_feature_does_not_intercept_legacy_validation(self):
        with patch.dict(os.environ, {"SOCIALMEI_AUTH_ENABLED": "false"}):
            self.assertEqual(
                self.client.post(
                    "/api/v1/produtos", json={"nome": " ", "preco": -1}
                ).status_code,
                422,
            )
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/login",
                    json={"email": "a@example.com", "senha": PASSWORD},
                ).status_code,
                503,
            )


@unittest.skipUnless(DB, "TEST_DATABASE_URL not configured")
class AccountDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DB, autocommit=True) as conn:
            for path in sorted(
                (Path(__file__).resolve().parents[1] / "database/migrations").glob(
                    "*.sql"
                )
            ):
                conn.execute(path.read_text(), prepare=False)
        cls.hashed = hash_password(PASSWORD)

    def setUp(self):
        env = patch.dict(os.environ, {**ENV, "DATABASE_URL": DB})
        env.start()
        self.addCleanup(env.stop)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "TRUNCATE socialmei.workspaces, socialmei.users, socialmei.auth_limites RESTART IDENTITY CASCADE"
            )
            conn.execute(
                "INSERT INTO socialmei.workspaces(slug,nome) VALUES ('team','Existing team')"
            )
        self.admin_id = create_admin("admin@example.com", "Admin", self.hashed)
        self.admin_client = self.login("admin@example.com")

    def login(self, address, remember=False, password=PASSWORD):
        client = TestClient(app, base_url=ORIGIN, headers=HEADERS)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": address, "senha": password, "lembrar": remember},
        )
        self.assertEqual(response.status_code, 200, response.text)
        client.headers["X-SocialMEI-CSRF"] = response.json()["csrf_token"]
        client.identity = response.json()
        client.login_response = response
        return client

    def invited(self, address="mei@example.com"):
        response = self.admin_client.post(
            "/api/v1/admin/invites", json={"email": address}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["convite"]

    def register(self, address="mei@example.com", token=None):
        client = TestClient(app, base_url=ORIGIN, headers=HEADERS)
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": address,
                "nome": "MEI",
                "senha": PASSWORD,
                "convite": token or self.invited(address),
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        client.headers["X-SocialMEI-CSRF"] = response.json()["csrf_token"]
        client.identity = response.json()
        return client

    def create(self, client, path, data):
        response = client.post("/api/v1/" + path, json=data)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_eight_character_registration_and_password_change_with_sessions(self):
        address = "eight@example.test"
        token = self.invited(address)
        client = TestClient(app, base_url=ORIGIN, headers=HEADERS)
        payload = {
            "nome": "Teste", "email": address, "convite": token, "senha": "FlorSol"
        }
        self.assertEqual(client.post("/api/v1/auth/register", json=payload).status_code, 422)
        payload["senha"] = "12345678"
        self.assertEqual(client.post("/api/v1/auth/register", json=payload).status_code, 422)
        payload["senha"] = "FlorSol!"
        response = client.post("/api/v1/auth/register", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        client.headers["X-SocialMEI-CSRF"] = response.json()["csrf_token"]
        second = self.login(address, password="FlorSol!")
        for value in ("7392518", "senha123"):
            response = client.post(
                "/api/v1/auth/password", json={"atual": "FlorSol!", "nova": value}
            )
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(second.get("/api/v1/auth/me").status_code, 200)
        response = client.post(
            "/api/v1/auth/password", json={"atual": "FlorSol!", "nova": "73925186"}
        )
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(second.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(
            self.login(address, password="73925186").get("/api/v1/auth/me").status_code, 200
        )

    def test_admin_bootstrap_preserves_team_and_cannot_promote_existing_user(self):
        self.assertEqual(self.admin_client.identity["negocio"]["slug"], "team")
        self.assertTrue(
            self.admin_client.identity["usuario"]["administrador_plataforma"]
        )
        with self.assertRaises(RuntimeError):
            create_admin("other@example.com", "Other", self.hashed)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM socialmei.users").fetchone()[0], 1
            )
            self.assertEqual(
                conn.execute(
                    "SELECT nome FROM socialmei.workspaces WHERE slug='team'"
                ).fetchone()[0],
                "Existing team",
            )

    def test_open_registration_creates_isolated_non_admin_account_without_invite(self):
        with patch.dict(os.environ, {"SOCIALMEI_REGISTRATION_MODE": "open"}):
            client = TestClient(app, base_url=ORIGIN, headers=HEADERS)
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "nome": "New MEI",
                    "email": "open@example.com",
                    "senha": PASSWORD,
                    "telefone": "11999998888",
                },
            )
            self.assertEqual(response.status_code, 201, response.text)
            identity = response.json()
            self.assertFalse(identity["usuario"]["administrador_plataforma"])
            self.assertEqual(identity["papel"], "owner")
            self.assertNotEqual(identity["negocio"]["slug"], "team")
            self.assertEqual(client.get("/api/v1/clientes").json(), [])
            self.assertEqual(client.get("/api/v1/admin/users").status_code, 403)
            self.assertEqual(client.get("/api/v1/auth/me").status_code, 200)
            self.assertEqual(client.get("/api/v1/auth/session").json(), identity)
            self.login("open@example.com")
            with psycopg.connect(DB) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM socialmei.auth_convites"
                    ).fetchone()[0],
                    0,
                )
            client.headers["X-SocialMEI-CSRF"] = identity["csrf_token"]
            self.assertEqual(client.post("/api/v1/auth/logout").status_code, 204)
            self.assertEqual(client.get("/api/v1/auth/me").status_code, 401)
            self.assertIsNone(client.get("/api/v1/auth/session").json())
            duplicate = client.post(
                "/api/v1/auth/register",
                json={
                    "nome": "Duplicate",
                    "email": "open@example.com",
                    "senha": PASSWORD,
                },
            )
            self.assertEqual(duplicate.status_code, 400)
            with psycopg.connect(DB) as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM socialmei.users").fetchone()[0],
                    2,
                )

    def test_restricting_registration_again_blocks_new_uninvited_accounts(self):
        client = TestClient(app, base_url=ORIGIN, headers=HEADERS)
        fields = {"nome": "MEI", "email": "new@example.com", "senha": PASSWORD}
        for mode in ("invite", "invalid"):
            with self.subTest(mode=mode), patch.dict(
                os.environ, {"SOCIALMEI_REGISTRATION_MODE": mode}
            ):
                self.assertEqual(
                    client.post("/api/v1/auth/register", json=fields).status_code, 400
                )
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM socialmei.users").fetchone()[0], 1
            )

    def test_cookie_flags_session_lifetime_and_hash_only_storage(self):
        response = self.admin_client.login_response
        cookie = response.headers["set-cookie"]
        for flag in ["HttpOnly", "Secure", "SameSite=lax", "Path=/"]:
            self.assertIn(flag, cookie)
        self.assertNotIn("Max-Age", cookie)
        token = self.admin_client.cookies.get(COOKIE)
        self.assertEqual(len(token), 64)
        with psycopg.connect(DB) as conn:
            row = conn.execute(
                "SELECT token_hash, EXTRACT(EPOCH FROM expira_em-criada_em)::int FROM socialmei.auth_sessoes"
            ).fetchone()
            self.assertEqual(row, (digest(token), 86400))
            hashed = conn.execute(
                "SELECT senha_hash FROM socialmei.auth_credenciais"
            ).fetchone()[0]
            self.assertTrue(hashed.startswith("$argon2id$"))
            self.assertNotIn(PASSWORD, hashed)
        remembered = self.login("admin@example.com", remember=True)
        self.assertIn("Max-Age=604800", remembered.login_response.headers["set-cookie"])

    def test_invite_email_binding_expiry_reissue_and_no_privilege_escalation(self):
        token = self.invited()
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT token_hash FROM socialmei.auth_convites"
                ).fetchone()[0],
                digest(token),
            )
        client = TestClient(app, base_url=ORIGIN, headers=HEADERS)
        fields = {
            "email": "other@example.com",
            "nome": "MEI",
            "senha": PASSWORD,
            "convite": token,
        }
        self.assertEqual(
            client.post("/api/v1/auth/register", json=fields).status_code, 400
        )
        fields["email"] = "mei@example.com"
        self.assertEqual(
            client.post(
                "/api/v1/auth/register",
                json={**fields, "administrador_plataforma": True},
            ).status_code,
            422,
        )
        new_token = self.invited()
        self.assertEqual(
            client.post("/api/v1/auth/register", json=fields).status_code, 400
        )
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.auth_convites SET criado_em=NOW()-INTERVAL '4 days', expira_em=NOW()-INTERVAL '1 day' WHERE token_hash=%s",
                (digest(new_token),),
            )
        fields["convite"] = new_token
        self.assertEqual(
            client.post("/api/v1/auth/register", json=fields).status_code, 400
        )
        fields["convite"] = self.invited()
        result = client.post("/api/v1/auth/register", json=fields)
        self.assertEqual(result.status_code, 201, result.text)
        self.assertFalse(result.json()["usuario"]["administrador_plataforma"])
        self.assertNotEqual(result.json()["negocio"]["slug"], "team")
        self.assertEqual(
            client.post("/api/v1/auth/register", json=fields).status_code, 400
        )

    def test_invite_consumption_is_atomic_under_concurrent_registration(self):
        token = self.invited()
        fields = {
            "email": "mei@example.com",
            "nome": "MEI",
            "senha": PASSWORD,
            "convite": token,
        }

        def register(_):
            with TestClient(app, base_url=ORIGIN, headers=HEADERS) as client:
                return client.post("/api/v1/auth/register", json=fields).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(register, range(2))), [201, 400])
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.users WHERE email='mei@example.com'"
                ).fetchone()[0],
                1,
            )

    def test_password_errors_generic_and_throttled_across_sessions(self):
        client = TestClient(app, base_url=ORIGIN, headers=HEADERS)
        errors = []
        for address in ["admin@example.com", "unknown@example.com"]:
            response = client.post(
                "/api/v1/auth/login", json={"email": address, "senha": "wrong-password"}
            )
            self.assertEqual(response.status_code, 400)
            errors.append(response.json())
        self.assertEqual(errors[0], errors[1])
        for _ in range(9):
            client.post(
                "/api/v1/auth/login",
                json={"email": "unknown@example.com", "senha": "wrong"},
            )
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@example.com", "senha": PASSWORD},
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_logout_expiry_password_change_and_private_reset_revoke_sessions(self):
        first = self.register()
        second = self.login("mei@example.com")
        self.assertEqual(first.post("/api/v1/auth/logout", json={}).status_code, 204)
        self.assertEqual(first.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(second.get("/api/v1/auth/me").status_code, 200)
        response = second.post(
            "/api/v1/auth/password",
            json={"atual": PASSWORD, "nova": "Another-test-password-123!"},
        )
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(second.get("/api/v1/auth/me").status_code, 401)
        third = self.login("mei@example.com", password="Another-test-password-123!")
        reset_password("mei@example.com", self.hashed)
        self.assertEqual(third.get("/api/v1/auth/me").status_code, 401)
        fourth = self.login("mei@example.com")
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.auth_sessoes SET criada_em=NOW()-INTERVAL '2 days', expira_em=NOW()-INTERVAL '1 day' WHERE token_hash=%s",
                (digest(fourth.cookies.get(COOKIE)),),
            )
        self.assertEqual(fourth.get("/api/v1/auth/me").status_code, 401)

    def test_csrf_origin_viewer_permissions_and_disabled_accounts(self):
        mei = self.register()
        for headers in [
            {"X-SocialMEI-CSRF": ""},
            {"Origin": "https://evil.example"},
            {"X-SocialMEI-CSRF": "bad"},
        ]:
            self.assertEqual(
                mei.post(
                    "/api/v1/clientes", json={"nome": "Forbidden"}, headers=headers
                ).status_code,
                403,
            )
        self.assertEqual(mei.get("/api/v1/admin/users").status_code, 403)
        self.assertEqual(
            mei.post("/api/v1/transferencias/preview", json={}).status_code, 403
        )
        uid = mei.identity["usuario"]["id"]
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.workspace_members SET role='viewer' WHERE user_id=%s",
                (uid,),
            )
        self.assertEqual(mei.get("/api/v1/clientes").status_code, 200)
        self.assertEqual(
            mei.post("/api/v1/clientes", json={"nome": "Forbidden"}).status_code, 403
        )
        self.assertEqual(
            self.admin_client.post(
                f"/api/v1/admin/users/{self.admin_id}/disable", json={}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.admin_client.post(
                f"/api/v1/admin/users/{uid}/disable", json={}
            ).status_code,
            204,
        )
        self.assertEqual(mei.get("/api/v1/auth/me").status_code, 401)
        enable_user("mei@example.com")
        self.assertEqual(mei.get("/api/v1/auth/me").status_code, 401)
        self.assertEqual(
            self.login("mei@example.com").get("/api/v1/auth/me").status_code, 200
        )

    def test_all_crm_modules_and_linked_ids_are_isolated_from_other_mei(self):
        first, second = (
            self.register("first@example.com"),
            self.register("second@example.com"),
        )
        customer = self.create(first, "clientes", {"nome": "Private client"})
        product = self.create(
            first, "produtos", {"nome": "Private product", "preco": 10, "estoque": 5}
        )
        sale = self.create(
            first,
            "vendas",
            {
                "cliente_id": customer["id"],
                "produto_id": product["id"],
                "data": "2026-10-12",
                "quantidade": 1,
                "preco": 10,
                "operation_id": str(uuid4()),
            },
        )
        finance = self.create(
            first,
            "financeiro",
            {
                "descricao": "Private finance",
                "tipo": "receita",
                "valor": 10,
                "vencimento": "2026-10-12",
                "cliente_id": customer["id"],
                "operation_id": str(uuid4()),
            },
        )
        for path, row in [
            ("clientes", customer),
            ("produtos", product),
            ("vendas", sale),
            ("financeiro", finance),
        ]:
            self.assertEqual(second.get("/api/v1/" + path).json(), [])
            self.assertEqual(second.get(f"/api/v1/{path}/{row['id']}").status_code, 404)
        self.assertEqual(
            second.patch(
                f"/api/v1/clientes/{customer['id']}",
                json={"nome": "Attacked", "expected_version": 1},
            ).status_code,
            404,
        )
        self.assertEqual(
            second.post(
                "/api/v1/vendas",
                json={
                    "cliente_id": customer["id"],
                    "produto_id": product["id"],
                    "data": "2026-10-12",
                    "quantidade": 1,
                    "preco": 10,
                    "operation_id": str(uuid4()),
                },
            ).status_code,
            422,
        )
        self.assertEqual(
            second.post(
                "/api/v1/clientes",
                json={"nome": "Bad", "workspace_id": first.identity["negocio"]["id"]},
            ).status_code,
            422,
        )
        self.assertEqual(os.environ["SOCIALMEI_WORKSPACE_SLUG"], "team")
        self.assertIsNone(principal.get())

    def test_concurrent_requests_keep_context_and_import_identity_separate(self):
        first, second = (
            self.register("first@example.com"),
            self.register("second@example.com"),
        )
        batch = {
            "origem": str(uuid4()),
            "itens": [{"local_id": 1, "cliente": {"nome": "Imported"}}],
        }

        def request(client):
            response = client.post("/api/v1/clientes/importacoes/confirmar", json=batch)
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()["itens"][0]["cliente_id"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(request, [first, second]))
        self.assertNotEqual(ids[0], ids[1])
        self.assertEqual(request(first), ids[0])
        self.assertEqual(request(second), ids[1])
        self.assertEqual(
            [
                first.get("/api/v1/clientes").json()[0]["id"],
                second.get("/api/v1/clientes").json()[0]["id"],
            ],
            ids,
        )
        self.assertIsNone(principal.get())

    def test_account_and_business_profile_persist_between_logins(self):
        mei = self.register()
        response = mei.patch(
            "/api/v1/auth/profile",
            json={
                "nome": "Updated",
                "telefone": "11999999999",
                "nome_negocio": "New shop",
                "configuracao_negocio": {
                    "pix": "business@example.com",
                    "horario": "9-18",
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        another = self.login("mei@example.com")
        self.assertEqual(another.identity["usuario"]["nome"], "Updated")
        self.assertEqual(another.identity["negocio"]["nome"], "New shop")
        self.assertEqual(
            another.identity["negocio"]["configuracao"]["pix"], "business@example.com"
        )
        self.assertEqual(
            mei.patch(
                "/api/v1/auth/profile",
                json={"configuracao_negocio": {"administrador": True}},
            ).status_code,
            422,
        )
        self.assertEqual(
            mei.patch(
                "/api/v1/auth/profile", json={"email": "admin@example.com"}
            ).status_code,
            422,
        )

    def test_technical_read_scope_remains_team_after_account_activation(self):
        mei = self.register()
        self.create(mei, "clientes", {"nome": "Never in n8n team read"})
        with patch.dict(
            os.environ,
            {
                "SOCIALMEI_N8N_READ_TOKEN": "technical-key-long-enough-for-private-test-123"
            },
        ):
            client = TestClient(app, base_url=ORIGIN)
            response = client.get(
                "/api/v1/integracoes/clientes",
                headers={
                    "Authorization": "Bearer technical-key-long-enough-for-private-test-123"
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["itens"], [])
            self.assertEqual(
                client.get(
                    "/api/v1/clientes",
                    headers={
                        "Authorization": "Bearer technical-key-long-enough-for-private-test-123"
                    },
                ).status_code,
                401,
            )
