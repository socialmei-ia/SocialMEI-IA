"""No provider I/O; SMTP DATA acceptance and cleanup have separate outcomes."""
from email.message import EmailMessage
import smtplib
import unittest
from unittest.mock import MagicMock, patch
import smtp_delivery


class SMTPDeliveryTests(unittest.TestCase):
    def test_acceptance_survives_network_cleanup_error_but_not_unknown_send(self):
        config = {'host': 'smtp.example.test', 'port': 465, 'user': 'synthetic', 'password': 'synthetic'}
        for port in (465, 587):
            for after_accept in (True, False):
                server = MagicMock(); server.send_message.return_value = {}
                if after_accept: server.__exit__.side_effect = OSError('synthetic cleanup failure')
                else: server.send_message.side_effect = TimeoutError('synthetic uncertain DATA')
                with self.subTest(port=port, after_accept=after_accept), \
                        patch.object(smtp_delivery.smtplib, 'SMTP_SSL', return_value=server), \
                        patch.object(smtp_delivery.smtplib, 'SMTP', return_value=server):
                    if after_accept: smtp_delivery.deliver(EmailMessage(), {**config, 'port': port})
                    else:
                        with self.assertRaises(TimeoutError): smtp_delivery.deliver(EmailMessage(), {**config, 'port': port})
                server.send_message.assert_called_once()
                if port == 587:
                    names = [call[0] for call in server.method_calls]
                    self.assertLess(names.index('starttls'), names.index('login'))
                server.set_debuglevel.assert_not_called()

    def test_missing_or_refused_acceptance_never_becomes_success(self):
        config = {'host': 'smtp.example.test', 'port': 465, 'user': 'synthetic', 'password': 'synthetic'}
        for result in (None, {'recipient@example.test': (550, b'rejected')}):
            server = MagicMock(); server.send_message.return_value = result
            with patch.object(smtp_delivery.smtplib, 'SMTP_SSL', return_value=server):
                with self.assertRaises(RuntimeError): smtp_delivery.deliver(EmailMessage(), config)
        server = MagicMock(); server.send_message.return_value = {}; server.__exit__.side_effect = ValueError('unexpected programming failure')
        with patch.object(smtp_delivery.smtplib, 'SMTP_SSL', return_value=server):
            with self.assertRaises(ValueError): smtp_delivery.deliver(EmailMessage(), config)
