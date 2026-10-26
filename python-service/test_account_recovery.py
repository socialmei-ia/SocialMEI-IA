"""Password recovery: real SQL and sessions, fake mail delivery only."""

import os
import unittest
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from app import app
import test_account_auth as accounts


@unittest.skipUnless(accounts.DB, "Disposable PostgreSQL required")
class RecoveryTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        env = patch.dict(
            os.environ,
            {
                "SOCIALMEI_RECOVERY_MODE": "smtp",
                "SOCIALMEI_SMTP_HOST": "smtp.gmail.com",
                "SOCIALMEI_SMTP_USER": "sender@example.test",
                "SOCIALMEI_SMTP_PASSWORD": "fake-test-only",
                "SOCIALMEI_SMTP_FROM": "sender@example.test",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(
            app, base_url=accounts.ORIGIN, headers=accounts.HEADERS
        )
        self.owner = self.register("owner@example.test")
        self.other = self.register("other@example.test")

    def issue(self):
        with patch("account_recovery.send_recovery_mail") as mail:
            response = self.client.post(
                "/api/v1/auth/recovery/request", json={"email": "owner@example.test"}
            )
            from account_recovery import process_one

            process_one()
        self.assertEqual(response.status_code, 202, response.text)
        return mail.call_args.args[1]

    def confirm(self, token, password="FlorSol!"):
        return self.client.post(
            "/api/v1/auth/recovery/confirm", json={"token": token, "nova": password}
        )

    def test_reset_single_use_revokes_owner_sessions_only(self):
        token = self.issue()
        self.assertEqual(self.confirm(token, "FlorSol").status_code, 422)
        self.assertEqual(self.confirm(token).status_code, 204)
        self.assertEqual(self.confirm(token).status_code, 400)
        self.assertIsNone(self.owner.get("/api/v1/auth/session").json())
        self.assertIsNotNone(self.other.get("/api/v1/auth/session").json())
        self.login("owner@example.test", password="FlorSol!")
        with psycopg.connect(accounts.DB) as conn:
            stored = conn.execute(
                "SELECT token_hash FROM socialmei.auth_recuperacoes"
            ).fetchone()[0]
        self.assertNotEqual(stored, token)

    def test_expired_invalid_and_common_password_rejected(self):
        token = self.issue()
        self.assertEqual(self.confirm(token, "12345678").status_code, 422)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute(
                "UPDATE socialmei.auth_recuperacoes SET expira_em=NOW()-INTERVAL '1 second'"
            )
        self.assertEqual(self.confirm(token).status_code, 400)
        self.assertEqual(self.confirm("x" * 43).status_code, 400)
        self.assertEqual(self.owner.get("/api/v1/auth/me").status_code, 200)

    def test_unknown_email_generic_response_and_no_mail(self):
        with patch("account_recovery.send_recovery_mail") as mail:
            unknown = self.client.post(
                "/api/v1/auth/recovery/request", json={"email": "unknown@example.test"}
            )
            self.assertEqual(unknown.status_code, 202)
            mail.assert_not_called()
            known = self.client.post(
                "/api/v1/auth/recovery/request", json={"email": "owner@example.test"}
            )
            self.assertEqual(unknown.json(), known.json())
            self.assertNotIn("token", known.text)

    def test_origin_headers_default_disabled_and_throttle(self):
        payload = {"email": "owner@example.test"}
        self.assertEqual(
            TestClient(app, base_url=accounts.ORIGIN)
            .post("/api/v1/auth/recovery/request", json=payload)
            .status_code,
            403,
        )
        with patch.dict(os.environ, {"SOCIALMEI_RECOVERY_MODE": "disabled"}):
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/recovery/request", json=payload
                ).status_code,
                503,
            )
        with patch("account_recovery.send_recovery_mail"):
            for _ in range(10):
                self.assertEqual(
                    self.client.post(
                        "/api/v1/auth/recovery/request", json=payload
                    ).status_code,
                    202,
                )
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/recovery/request", json=payload
                ).status_code,
                429,
            )

    def test_failed_mail_leaves_no_usable_token(self):
        with patch(
            "account_recovery.send_recovery_mail", side_effect=OSError("fake failure")
        ):
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/recovery/request",
                    json={"email": "owner@example.test"},
                ).status_code,
                202,
            )
            from account_recovery import process_one

            process_one()
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT status FROM socialmei.auth_recuperacao_envios"
                ).fetchone()[0],
                "uncertain",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT count(*) FROM socialmei.auth_recuperacoes WHERE usado_em IS NULL"
                ).fetchone()[0],
                0,
            )

    def test_password_change_invalidates_code(self):
        token = self.issue()
        self.assertEqual(
            self.owner.post(
                "/api/v1/auth/password",
                json={"atual": accounts.PASSWORD, "nova": "Another-pass-789!"},
            ).status_code,
            204,
        )
        self.assertEqual(self.confirm(token).status_code, 400)

    def test_concurrent_confirmation_has_exactly_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor

        token = self.issue()

        def reset(password):
            with TestClient(
                app, base_url=accounts.ORIGIN, headers=accounts.HEADERS
            ) as client:
                return (
                    password,
                    client.post(
                        "/api/v1/auth/recovery/confirm",
                        json={"token": token, "nova": password},
                    ).status_code,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(reset, ["First-pass-890!", "Second-pass-890!"]))
        self.assertEqual(sorted(status for _, status in outcomes), [204, 400])
        self.login(
            "owner@example.test",
            password=next(password for password, status in outcomes if status == 204),
        )

    def test_missing_migration_returns_unavailable(self):
        with psycopg.connect(accounts.DB) as conn:
            conn.execute(
                "ALTER TABLE socialmei.auth_recuperacoes RENAME TO auth_recuperacoes_hidden"
            )
        try:
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/recovery/request",
                    json={"email": "owner@example.test"},
                ).status_code,
                503,
            )
        finally:
            with psycopg.connect(accounts.DB) as conn:
                conn.execute(
                    "ALTER TABLE socialmei.auth_recuperacoes_hidden RENAME TO auth_recuperacoes"
                )

    def test_durable_request_survives_worker_restart_and_never_auto_retries(self):
        from account_recovery import process_one

        with patch("account_recovery.send_recovery_mail") as mail:
            self.client.post(
                "/api/v1/auth/recovery/request", json={"email": "owner@example.test"}
            )
            mail.assert_not_called()
            with psycopg.connect(accounts.DB) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT status FROM socialmei.auth_recuperacao_envios"
                    ).fetchone()[0],
                    "pending",
                )
            self.assertTrue(process_one())
            self.assertFalse(process_one())
            mail.assert_called_once()
            with psycopg.connect(accounts.DB) as conn:
                conn.execute(
                    "UPDATE socialmei.auth_recuperacao_envios SET status='processing',started_at=NOW()-INTERVAL '5 minutes'"
                )
            self.assertFalse(process_one())
            mail.assert_called_once()
            with psycopg.connect(accounts.DB) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT status FROM socialmei.auth_recuperacao_envios"
                    ).fetchone()[0],
                    "uncertain",
                )

    def test_parallel_workers_claim_once_and_new_request_cancels_previous_code(self):
        from concurrent.futures import ThreadPoolExecutor
        from account_recovery import process_one

        old = self.issue()
        self.client.post(
            "/api/v1/auth/recovery/request", json={"email": "owner@example.test"}
        )
        self.assertEqual(self.confirm(old).status_code, 400)
        with patch("account_recovery.send_recovery_mail") as mail, ThreadPoolExecutor(
            max_workers=2
        ) as pool:
            self.assertEqual(
                sorted(pool.map(lambda _: process_one(), range(2))), [False, True]
            )
            mail.assert_called_once()

    def test_new_request_during_send_preserves_new_pending_generation(self):
        from account_recovery import process_one

        self.client.post(
            "/api/v1/auth/recovery/request", json={"email": "owner@example.test"}
        )
        tokens = []

        def replace_request(address, token, config):
            tokens.append(token)
            self.assertEqual(
                self.client.post(
                    "/api/v1/auth/recovery/request", json={"email": address}
                ).status_code,
                202,
            )

        with patch("account_recovery.send_recovery_mail", side_effect=replace_request):
            self.assertTrue(process_one())
        self.assertEqual(self.confirm(tokens[0]).status_code, 400)
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT status FROM socialmei.auth_recuperacao_envios"
                ).fetchone()[0],
                "pending",
            )
        with patch("account_recovery.send_recovery_mail") as mail:
            self.assertTrue(process_one())
        self.assertEqual(self.confirm(mail.call_args.args[1]).status_code, 204)

    def test_stale_queue_expires_without_email(self):
        from account_recovery import process_one

        self.client.post(
            "/api/v1/auth/recovery/request", json={"email": "owner@example.test"}
        )
        with psycopg.connect(accounts.DB) as conn:
            conn.execute(
                "UPDATE socialmei.auth_recuperacao_envios SET queued_at=NOW()-INTERVAL '16 minutes'"
            )
        with patch("account_recovery.send_recovery_mail") as mail:
            self.assertTrue(process_one())
            mail.assert_not_called()


class MailTransportTests(unittest.TestCase):
    def test_tls_before_credentials_and_no_debug_logging(self):
        from account_recovery import send_recovery_mail
        from unittest.mock import MagicMock

        for port in (465, 587):
            with self.subTest(port=port), patch(
                "account_recovery.smtplib.SMTP_SSL"
            ) as ssl_server, patch("account_recovery.smtplib.SMTP") as plain_server:
                server = MagicMock()
                server.__enter__.return_value = server
                ssl_server.return_value = plain_server.return_value = server
                send_recovery_mail(
                    "recipient@example.test",
                    "x" * 43,
                    {
                        "host": "smtp.gmail.com",
                        "port": port,
                        "user": "sender@example.test",
                        "password": "synthetic-only",
                        "from": "sender@example.test",
                    },
                )
                if port == 465:
                    plain_server.assert_not_called()
                    ssl_server.assert_called_once()
                    self.assertIsNotNone(ssl_server.call_args.kwargs["context"])
                else:
                    ssl_server.assert_not_called()
                    names = [call[0] for call in server.method_calls]
                    self.assertLess(names.index("starttls"), names.index("login"))
                server.set_debuglevel.assert_not_called()
                server.send_message.assert_called_once()


class WorkerSafetyTests(unittest.TestCase):
    def test_worker_refuses_to_run_without_explicit_flag(self):
        import recovery_worker

        with patch("sys.argv", ["recovery_worker.py"]), patch(
            "recovery_worker.process_one"
        ) as process:
            with self.assertRaises(SystemExit):
                recovery_worker.main()
            process.assert_not_called()
