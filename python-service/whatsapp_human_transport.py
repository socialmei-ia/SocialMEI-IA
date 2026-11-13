"""One-shot private WAHA transport. Explicit policy, no redirects, no startup I/O."""
import json
import logging
import re
import time
from contextvars import ContextVar
from urllib.parse import quote

import httpx

from settings import WhatsAppHumanConfiguration

_private_request = ContextVar('whatsapp_private_http', default=False)


class _PrivateHTTPLogs(logging.Filter):
    def filter(self, record):
        return not _private_request.get()


_private_logs = _PrivateHTTPLogs()


def _protect_logs():
    for name in ('httpx', 'httpcore', *list(logging.Logger.manager.loggerDict)):
        if name in {'httpx', 'httpcore'} or name.startswith(('httpx.', 'httpcore.')):
            logger = logging.getLogger(name)
            if _private_logs not in logger.filters:
                logger.addFilter(_private_logs)


class WahaTransportError(ValueError):
    def __init__(self):
        super().__init__('Transporte WhatsApp indisponível. Concilie o estado antes de repetir.')


class WahaPolicyError(ValueError):
    def __init__(self):
        super().__init__('Canal ou contato fora do piloto WhatsApp autorizado.')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WahaTransportError()
        result[key] = value
    return result


class WahaHumanTransport:
    def __init__(self, configuration, *, client_factory=httpx.Client, clock=time.monotonic):
        if not isinstance(configuration, WhatsAppHumanConfiguration) or not callable(client_factory) or not callable(clock):
            raise WahaPolicyError()
        # Defense in depth: no other URL is ever used, even with an injected configuration.
        allowed = {'WEBJS': {'http://waha:3000', 'http://socialmei-waha:3000'},
                   'GOWS': {'http://socialmei-waha-gows-piloto:3000'}}
        if (configuration.engine not in allowed or configuration.base_url not in allowed.get(configuration.engine, set())
                or (configuration.engine == 'GOWS' and configuration.session != '01')
                or type(configuration.public_inbound) is not bool):
            raise WahaPolicyError()
        self._configuration = configuration
        self._client_factory = client_factory
        self._clock = clock

    def __repr__(self):
        return 'WahaHumanTransport(private=<redacted>)'

    def inspect_session(self):
        """Read only the configured session; never pair, start, stop or send."""
        config = self._configuration
        token = _private_request.set(True)
        _protect_logs()
        try:
            with self._client_factory(verify=True, follow_redirects=False, trust_env=False,
                    timeout=httpx.Timeout(5, connect=2),
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=0)) as client:
                if config.engine == 'GOWS':
                    if self._request(client, 'GET', '/api/version').get('engine') != 'GOWS':
                        raise WahaTransportError()
                session = self._request(client, 'GET', '/api/sessions/' + quote(config.session, safe=''))
                status = session.get('status')
                if session.get('name') != config.session or status not in {'WORKING', 'STOPPED', 'STARTING', 'SCAN_QR_CODE', 'FAILED'}:
                    raise WahaTransportError()
                if status == 'WORKING' and (not isinstance(session.get('me'), dict) or session['me'].get('id') != config.account_id):
                    raise WahaTransportError()
                return {'status': status}
        except Exception:
            raise WahaTransportError() from None
        finally:
            _private_request.reset(token)

    def validate_scope(self, item):
        config = self._configuration
        if (
            item.get('workspace_id') != config.workspace_id
            or item.get('instancia') != config.instance
            or item.get('sessao') != config.session
            or item.get('identificador_conta') != config.account_id
            or (not config.public_inbound and item.get('contact_ref') not in {'waha:' + value for value in config.contacts})
            or not isinstance(item.get('contact_ref'), str)
            or not re.fullmatch(r'waha:(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)', item['contact_ref'])
        ):
            raise WahaPolicyError()

    def _request(self, client, method, path, *, body=None, maximum=32768):
        config = self._configuration
        started = self._clock()
        _protect_logs()
        with client.stream(method, config.base_url + path, headers={
            'X-Api-Key': config.api_key, 'Accept': 'application/json',
            **({'Content-Type': 'application/json'} if body is not None else {}),
        }, **({'content': json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()} if body is not None else {})) as response:
            if not 200 <= response.status_code <= 299:
                raise WahaTransportError()
            if response.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                raise WahaTransportError()
            raw = bytearray()
            for chunk in response.iter_bytes(chunk_size=min(8192, maximum + 1)):
                if len(raw) + len(chunk) > maximum or self._clock() - started > 10:
                    raise WahaTransportError()
                raw.extend(chunk)
            value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique)
            if not isinstance(value, dict):
                raise WahaTransportError()
            return value

    def __call__(self, delivery):
        config = self._configuration
        if not isinstance(delivery, dict) or set(delivery) != {'path', 'body'}:
            raise WahaPolicyError()
        body = delivery.get('body')
        if (
            delivery.get('path') != '/api/sendText'
            or not isinstance(body, dict) or set(body) != {'session', 'chatId', 'text'}
            or body.get('session') != config.session
            or not isinstance(body.get('chatId'), str)
            or (not config.public_inbound and body.get('chatId') not in config.contacts)
            or not re.fullmatch(r'(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)', body['chatId'])
            or body['chatId'] == config.account_id
            or not isinstance(body.get('text'), str) or not body['text'].strip()
            or any((ord(c) < 32 and c not in '\n\r\t') or 0x7f <= ord(c) <= 0x9f for c in body['text'])
        ):
            raise WahaPolicyError()
        try:
            if len(body['text'].encode()) > 4096:
                raise WahaPolicyError()
        except UnicodeEncodeError:
            raise WahaPolicyError() from None
        token = _private_request.set(True)
        _protect_logs()
        try:
            with self._client_factory(
                verify=True, follow_redirects=False, trust_env=False,
                timeout=httpx.Timeout(5, connect=2),
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=0),
            ) as client:
                if config.engine == 'GOWS':
                    version = self._request(client, 'GET', '/api/version')
                    if version.get('engine') != 'GOWS':
                        raise WahaTransportError()
                session = self._request(client, 'GET', '/api/sessions/' + quote(config.session, safe=''))
                if (session.get('name') != config.session or session.get('status') != 'WORKING'
                        or not isinstance(session.get('me'), dict)
                        or session['me'].get('id') != config.account_id):
                    raise WahaTransportError()
                receipt = self._request(client, 'POST', '/api/sendText', body=body, maximum=8192)
                provider_id = receipt.get('id')
                if isinstance(provider_id, dict):
                    provider_id = provider_id.get('_serialized')
                if not isinstance(provider_id, str) or not re.fullmatch(r'[!-~]{1,1024}', provider_id):
                    raise WahaTransportError()
                return provider_id
        except Exception:
            raise WahaTransportError() from None
        finally:
            _private_request.reset(token)
