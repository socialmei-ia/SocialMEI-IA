"""Despachante temporario de respostas de menu apenas para contatos que escreveram ao projeto.
A origem e o destinatario sao verificados pela API, jamais informados pelo navegador.
"""
import argparse
import json
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

API_URL = 'http://socialmei-menu-public-api-v3:8019'
WAHA_URL = 'http://socialmei-waha:3000'
GOWS_URL = 'http://socialmei-waha-gows-piloto:3000'
WAHA_ENDPOINTS = {'WEBJS': WAHA_URL, 'GOWS': GOWS_URL}
SOURCE_URL = '/internal/whatsapp/bot/sources'
VALID_CONTACT = re.compile(r'(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)\Z')
VALID_ACCOUNT = re.compile(r'[0-9]{1,40}@c\.us\Z')
VALID_INSTANCE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z')
VALID_ID = re.compile(r'[!-~]{1,1024}\Z')


class Blocked(Exception):
    """Nao imprimir dados sensiveis em erros/tracebacks."""


class SourceUnavailable(Blocked):
    """Apenas a leitura inicial falhou; nenhum claim ou envio foi iniciado."""


def _secret(path: str) -> str:
    if not path or not path.startswith('/run/secrets/') or '\x00' in path:
        raise Blocked('Arquivo de segredo fora do diretorio privado')
    p = Path(path)
    try:
        info = p.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 4097
                or info.st_size < 16):
            raise Blocked('Permissoes ou tamanho do segredo invalidos')
        value = p.read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError):
        raise Blocked('Segredo nao acessivel') from None
    if not re.fullmatch(r'[!-~]{16,4096}', value):
        raise Blocked('Segredo invalido')
    return value


@dataclass(frozen=True, repr=False)
class Config:
    instance: str
    session: str
    account: str
    token: str
    waha_key: str
    engine: str = 'WEBJS'
    waha_url: str = WAHA_URL

    def __post_init__(self):
        if (not VALID_INSTANCE.fullmatch(self.instance)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', self.session)
                or not VALID_ACCOUNT.fullmatch(self.account)
                or not re.fullmatch(r'[!-~]{16,4096}', self.token)
                or not re.fullmatch(r'[!-~]{16,4096}', self.waha_key)
                or self.engine not in WAHA_ENDPOINTS
                or self.waha_url != WAHA_ENDPOINTS.get(self.engine)
                or (self.engine == 'GOWS' and self.session != '01')):
            raise Blocked('Escopo do piloto invalido')

    @classmethod
    def from_env(cls):
        if (os.getenv('SOCIALMEI_MENU_SENDER_ACTIVE') != 'YES'
                or os.getenv('SOCIALMEI_PUBLIC_MENU_EXPLICIT_ENABLE') != 'YES'):
            raise Blocked('Envio automatico nao autorizado')
        engine = os.getenv('SOCIALMEI_MENU_WAHA_ENGINE', 'WEBJS')
        if (os.getenv('SOCIALMEI_MENU_API_URL') != API_URL
                or engine not in WAHA_ENDPOINTS
                or os.getenv('SOCIALMEI_MENU_WAHA_URL') != WAHA_ENDPOINTS.get(engine)):
            raise Blocked('Destino privado nao autorizado')
        return cls(
            os.getenv('SOCIALMEI_MENU_INSTANCE', ''),
            os.getenv('SOCIALMEI_MENU_SESSION', ''),
            os.getenv('SOCIALMEI_MENU_ACCOUNT', ''),
            _secret(os.getenv('SOCIALMEI_MENU_TOKEN_FILE', '')),
            _secret(os.getenv('SOCIALMEI_MENU_WAHA_KEY_FILE', '')),
            engine,
            os.getenv('SOCIALMEI_MENU_WAHA_URL', ''),
        )


def _json(response, maximum=16384):
    if not 200 <= response.status_code < 300:
        raise Blocked('Servico privado retornou erro')
    if response.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise Blocked('Resposta sem JSON')
    if len(response.content) > maximum:
        raise Blocked('Resposta muito grande')

    def unique(pairs):
        out = {}
        for name, val in pairs:
            if name in out:
                raise Blocked('JSON ambiguo')
            out[name] = val
        return out

    try:
        data = json.loads(response.content, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise Blocked('JSON invalido') from None
    if not isinstance(data, dict):
        raise Blocked('Resposta inesperada')
    return data


def _delivery(data, cfg):
    if not isinstance(data, dict) or set(data) != {'path', 'body'}:
        raise Blocked('Entrega inesperada')
    if data['path'] != '/api/sendText':
        raise Blocked('Somente menu textual autorizado')
    body = data['body']
    if (not isinstance(body, dict) or set(body) != {'session', 'chatId', 'text'}
            or body['session'] != cfg.session
            or not isinstance(body['chatId'], str) or not VALID_CONTACT.fullmatch(body['chatId'])
            or body['chatId'] == cfg.account
            or not isinstance(body['text'], str) or not body['text'].strip()
            or len(body['text'].encode('utf-8')) > 4096
            or any((ord(c) < 32 and c not in '\n\r\t') or 0x7f <= ord(c) <= 0x9f for c in body['text'])):
        raise Blocked('Contato ou conteudo fora do piloto')
    return body


def run_once(cfg, *, client_factory=httpx.Client):
    opts = dict(verify=True, follow_redirects=False, trust_env=False,
                timeout=httpx.Timeout(5, connect=2),
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=0))
    with client_factory(**opts) as api, client_factory(**opts) as waha:
        def request(client, method, url, *, headers, data=None):
            # Sem tentativas automaticas e sem redirecionamentos.
            content = None if data is None else json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
            r = client.request(method, url, headers={**headers, 'Accept': 'application/json',
                                      **({'Content-Type': 'application/json'} if content is not None else {})},
                               content=content)
            if method == 'GET' and url == API_URL + SOURCE_URL and r.status_code >= 500:
                raise SourceUnavailable('Fonte temporariamente indisponivel')
            return _json(r)

        auth = {'Authorization': 'Bearer ' + cfg.token}
        provider = {'X-Api-Key': cfg.waha_key}
        try:
            sources = request(api, 'GET', API_URL + SOURCE_URL, headers=auth)
        except httpx.TransportError as error:
            raise SourceUnavailable('Fonte temporariamente indisponivel') from error
        values = sources.get('sources')
        if not isinstance(values, list) or len(values) > 50:
            raise Blocked('Origens de mensagens invalidas')
        if not values:
            return 'SEM_MENSAGENS_NOVAS'
        src = values[0]
        if (not isinstance(src, dict) or set(src) != {'instance', 'external_message_id'}
                or src['instance'] != cfg.instance
                or not isinstance(src['external_message_id'], str)
                or not VALID_ID.fullmatch(src['external_message_id'])):
            raise Blocked('Origem nao corresponde ao piloto')

        planned = request(api, 'POST', API_URL + '/internal/whatsapp/bot/decisions', headers=auth, data=src)
        opid = planned.get('operation_id')
        if not isinstance(opid, str) or not re.fullmatch(r'[0-9a-fA-F-]{36}', opid):
            raise Blocked('Operacao sem identificador')
        if planned.get('status') != 'planned':
            return 'SEM_ENVIO_AUTORIZADO'

        # Preflight antes do claim. O contato so aparece no payload assinado do claim.
        if cfg.engine == 'GOWS':
            version = request(waha, 'GET', cfg.waha_url + '/api/version', headers=provider)
            if version.get('engine') != 'GOWS':
                raise Blocked('Engine WAHA diferente da configurada')
        session = request(waha, 'GET', cfg.waha_url + '/api/sessions/' + cfg.session, headers=provider)
        if (session.get('name') != cfg.session or session.get('status') != 'WORKING'
                or not isinstance(session.get('me'), dict)
                or session['me'].get('id') != cfg.account):
            raise Blocked('Sessao WAHA indisponivel ou outra conta')

        opurl = API_URL + '/internal/whatsapp/bot/decisions/' + opid
        claimed = request(api, 'POST', opurl + '/claim', headers=auth, data={})
        if claimed.get('dispatch_allowed') is not True:
            return 'ENVIO_NEGADO_PELO_SERVIDOR'
        # A partir daqui NUNCA tentar enviar duas vezes, mesmo em timeout.
        status = 'uncertain'
        provider_id = None
        try:
            body = _delivery(claimed.get('delivery'), cfg)
            # Revalidar sessao apos claim: qualquer erro exige conciliação, nao retry.
            if cfg.engine == 'GOWS':
                version = request(waha, 'GET', cfg.waha_url + '/api/version', headers=provider)
                if version.get('engine') != 'GOWS':
                    raise Blocked('Engine WAHA mudou apos claim')
            current = request(waha, 'GET', cfg.waha_url + '/api/sessions/' + cfg.session, headers=provider)
            if (current.get('name') != cfg.session or current.get('status') != 'WORKING'
                    or not isinstance(current.get('me'), dict)
                    or current['me'].get('id') != cfg.account):
                raise Blocked('Sessao mudou apos claim')
            sent = request(waha, 'POST', cfg.waha_url + '/api/sendText', headers=provider, data=body)
            receipt = sent.get('id')
            if isinstance(receipt, dict):
                receipt = receipt.get('_serialized')
            if not isinstance(receipt, str) or not VALID_ID.fullmatch(receipt):
                raise Blocked('Recibo de envio ambiguo')
            status, provider_id = 'confirmed', receipt
        except Exception:
            # Sem retry. Se POST chegou ao WAHA e resposta se perdeu, estado incerto.
            pass

        result = request(api, 'POST', opurl + '/receipt', headers=auth,
                         data={'status': status, 'provider_message_id': provider_id})
        if result.get('status') != status:
            raise Blocked('Recibo nao confirmado pela API; conciliacao manual')
        return 'ENVIO_CONFIRMADO' if status == 'confirmed' else 'RESULTADO_INCERTO_NAO_REENVIAR'


def run_continuously(cfg, *, poll=run_once, sleep=time.sleep, max_seconds=None,
                     clock=time.monotonic):
    if max_seconds is not None and (type(max_seconds) is not int or not 1 <= max_seconds <= 3600):
        raise ValueError('Janela de teste invalida')
    deadline = clock() + max_seconds if max_seconds is not None else None
    backoff = 15
    while True:
        if deadline is not None and clock() >= deadline:
            print('JANELA_ENCERRADA_SEM_NOVOS_ENVIOS', flush=True)
            return 0
        try:
            result = poll(cfg)
        except SourceUnavailable:
            print('AGUARDANDO_FONTE', flush=True)
            sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue
        except Exception:
            print('WORKER_PAUSADO = ERRO_REQUER_REVISAO', flush=True)
            return 3
        if result not in {'SEM_MENSAGENS_NOVAS', 'SEM_ENVIO_AUTORIZADO',
                          'ENVIO_NEGADO_PELO_SERVIDOR', 'ENVIO_CONFIRMADO'}:
            print('WORKER_PAUSADO = RESULTADO_INCERTO_OU_DESCONHECIDO', flush=True)
            return 2
        if result != 'SEM_MENSAGENS_NOVAS':
            print(result, flush=True)
        backoff = 15
        sleep(3)


def main(argv=None):
    p = argparse.ArgumentParser(description='Despachante controlado SocialMEI WhatsApp')
    p.add_argument('--run-once', action='store_true')
    p.add_argument('--continuous', action='store_true')
    p.add_argument('--window-seconds', type=int)
    args = p.parse_args(argv)
    if args.window_seconds is not None and (not args.continuous or not 1 <= args.window_seconds <= 3600):
        p.error('--window-seconds exige --continuous e valor de 1 a 3600')
    if not args.run_once and not args.continuous:
        print('MODO_SEGURO = SEM_ENVIO')
        print('PARA_LIBERAR = PILOTO_RESTRITO_COM_SEGREDOS_E_AUTORIZACAO')
        return 0
    try:
        config = Config.from_env()
        if args.continuous:
            run_continuously(config, max_seconds=args.window_seconds)
            # Permanecer pausado impede restart_policy de repetir envio incerto.
            while True:
                time.sleep(3600)
        result = run_once(config)
        print('RESULTADO =', result)
        return 0 if result != 'RESULTADO_INCERTO_NAO_REENVIAR' else 2
    except Exception:
        print('ENVIO_BLOQUEADO_OU_INDETERMINADO = REVISAR_SEM_REPETIR')
        return 3


if __name__ == '__main__':
    sys.exit(main())
