"""SMTP recovery links are safe fragments and preserve the manual code fallback."""

import unittest
from unittest.mock import patch
import account_recovery

TOKEN = "A" * 43
ORIGIN = "https://socialmei.example.test"
CONFIG = {
    "from": "noreply@example.test",
    "host": "smtp.example.test",
    "port": 465,
    "user": "noreply@example.test",
    "password": "synthetic-password",
}


class RecoveryLinkTests(unittest.TestCase):
    def test_implicit_tls_mail_contains_link_and_same_manual_code(self):
        with patch("account_recovery.origin", return_value=ORIGIN), patch(
            "account_recovery.smtplib.SMTP_SSL"
        ) as tls:
            account_recovery.send_recovery_mail(
                "owner@example.test", TOKEN, CONFIG.copy()
            )
        tls.assert_called_once()
        args, kwargs = tls.call_args
        self.assertEqual(args[:2], ("smtp.example.test", 465))
        self.assertIsNotNone(kwargs["context"])
        smtp = tls.return_value.__enter__.return_value
        smtp.send_message.assert_called_once()
        message = smtp.send_message.call_args.args[0]
        body = message.get_content()
        link = ORIGIN + "/frontend/entrada.html#/recuperar/" + TOKEN
        self.assertIn(link, body)
        self.assertEqual(body.count(TOKEN), 2)
        self.assertIn("15 minutos", body)
        self.assertEqual(message["To"], "owner@example.test")
        self.assertNotIn(TOKEN, message["Subject"])
        self.assertNotIn(TOKEN, repr(CONFIG))

    def test_starttls_mail_preserves_existing_tls_enforcement(self):
        config = {**CONFIG, "port": 587}
        with patch("account_recovery.origin", return_value=ORIGIN), patch(
            "account_recovery.smtplib.SMTP"
        ) as smtp:
            account_recovery.send_recovery_mail(
                "owner@example.test", TOKEN, config
            )
        server = smtp.return_value.__enter__.return_value
        server.starttls.assert_called_once()
        self.assertEqual(server.method_calls[0][0], "starttls")
        self.assertEqual(server.method_calls[1][0], "login")
        self.assertEqual(server.method_calls[2][0], "send_message")


if __name__ == "__main__":
    unittest.main()
