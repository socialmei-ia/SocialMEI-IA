"""TLS SMTP acceptance, distinct from delivery and session cleanup."""
import smtplib
import ssl


def deliver(message, config):
    port = config['port']
    if port not in (465, 587):
        raise ValueError('tls_smtp_port_required')
    context = ssl.create_default_context()
    server = (smtplib.SMTP_SSL(config['host'], 465, timeout=10, context=context)
              if port == 465 else smtplib.SMTP(config['host'], 587, timeout=10))
    accepted = False
    try:
        with server:
            if port == 587:
                server.starttls(context=context)
            server.login(config['user'], config['password'])
            refused = server.send_message(message)
            if not isinstance(refused, dict) or refused:
                raise RuntimeError('smtp_acceptance_not_confirmed')
            accepted = True
    except (OSError, smtplib.SMTPException):
        # A positive DATA receipt remains valid if QUIT/close subsequently fails.
        # Failure before that receipt remains uncertain and must not be retried.
        if not accepted:
            raise
    if not accepted:
        raise RuntimeError('smtp_acceptance_not_confirmed')
