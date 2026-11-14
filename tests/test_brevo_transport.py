"""Brevo contract with mocked SMTP only; no live messages or database."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python-service'))
import account_recovery
import identity_activation
import public_booking
from fastapi import HTTPException

CONFIG = {'host': 'smtp-relay.brevo.com', 'port': 587, 'user': 'synthetic-login',
          'password': 'synthetic-secret', 'from': 'servermeiiafacepe@gmail.com'}
ENV = {'SOCIALMEI_SMTP_' + key.upper(): str(value) for key, value in CONFIG.items()}
ENV['SOCIALMEI_AUTH_ORIGIN'] = 'https://example.test'


class BrevoTransportTests(unittest.TestCase):
    def deliveries(self):
        return [lambda: identity_activation.send_mail('controlled@example.test', 'x' * 43, 'verification', CONFIG),
                lambda: identity_activation.send_mail('controlled@example.test', 'x' * 43, 'invitation', CONFIG),
                lambda: account_recovery.send_recovery_mail('controlled@example.test', 'x' * 43, CONFIG),
                lambda: public_booking.send_code('controlled@example.test', '123456')]

    def test_all_mail_flows_use_starttls_before_login_and_verified_sender(self):
        for index, deliver in enumerate(self.deliveries()):
            with self.subTest(flow=index), patch.dict(os.environ, ENV), \
                    patch('smtplib.SMTP') as smtp, patch('smtplib.SMTP_SSL') as implicit:
                server = MagicMock()
                smtp.return_value = server
                server.__enter__.return_value = server
                deliver()
                smtp.assert_called_once_with('smtp-relay.brevo.com', 587, timeout=10)
                implicit.assert_not_called()
                names = [call[0] for call in server.method_calls]
                self.assertLess(names.index('starttls'), names.index('login'))
                self.assertIsNotNone(server.starttls.call_args.kwargs['context'])
                message = server.send_message.call_args.args[0]
                self.assertEqual(message['From'], CONFIG['from'])
                self.assertEqual(message['To'], 'controlled@example.test')
                server.set_debuglevel.assert_not_called()

    def test_tls_failure_never_sends_credentials_and_uncertain_send_is_not_retried(self):
        for failure in ('starttls', 'send_message'):
            for index, deliver in enumerate(self.deliveries()):
                with self.subTest(failure=failure, flow=index), patch.dict(os.environ, ENV), \
                        patch('smtplib.SMTP') as smtp:
                    server = MagicMock()
                    smtp.return_value = server
                    server.__enter__.return_value = server
                    getattr(server, failure).side_effect = OSError('synthetic-private-error')
                    with self.assertRaises(Exception):
                        deliver()
                    smtp.assert_called_once()
                    if failure == 'starttls':
                        server.login.assert_not_called()
                        server.send_message.assert_not_called()
                    else:
                        server.send_message.assert_called_once()

    def test_persisted_pending_identity_remains_blocked_when_mail_disabled(self):
        with patch.dict(os.environ, {'SOCIALMEI_IDENTITY_MODE': 'disabled'}), \
                patch('identity_activation.connect', side_effect=AssertionError('No DB query')):
            with self.assertRaises(HTTPException) as result:
                identity_activation.guard({'id': 1, '_email_required': True, '_email_verified': False}, '/api/v1/clientes')
            self.assertEqual(result.exception.status_code, 403)
            identity_activation.guard({'id': 1, '_email_required': True, '_email_verified': True}, '/api/v1/clientes')


if __name__ == '__main__':
    unittest.main()
