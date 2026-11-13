"""Business-owned WAHA requests; private provisioning and actual pairing remain operator-controlled."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import Field, field_validator

from account_auth import Strict, current, require_enabled, throttle
from contact_validation import validate_phone
from database import connect
import settings
import team_members
from waha_ingress import waha_service
from whatsapp_human_transport import WahaHumanTransport

router = APIRouter(prefix='/api/v1/whatsapp/connection', tags=['business WhatsApp management'])


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def now():
    return datetime.now(timezone.utc)


def configuration():
    enabled = os.getenv('SOCIALMEI_WAHA_MANAGEMENT_ENABLED', 'false')
    capacity = os.getenv('SOCIALMEI_WAHA_MANAGEMENT_MAX_SESSIONS', '2')
    if enabled not in {'true', 'false'} or not re.fullmatch(r'[1-9][0-9]{0,2}', capacity) or int(capacity) > 100:
        raise HTTPException(503, 'Gerenciamento WhatsApp indisponível.')
    return enabled == 'true', int(capacity)


def actor(request, *, write=False):
    require_enabled()
    user = current()
    if user['role'] not in {'owner', 'admin'} or (write and user['role'] != 'owner'):
        raise HTTPException(403, 'Somente o proprietário pode solicitar alterações do WhatsApp.')
    if write and request.headers.get('x-socialmei-identity') != f"{user['id']}:{user['workspace_id']}":
        raise HTTPException(409, 'O negócio mudou. Atualize antes de continuar.')
    return user


def registry():
    try:
        return list(waha_service().registry.values())
    except HTTPException:
        return None


def bound(bindings, workspace):
    found = [b for b in bindings or [] if b.workspace_id == workspace]
    if len(found) > 1:
        raise HTTPException(409, 'Há mais de um vínculo privado. A equipe precisa conciliar o canal.')
    return found[0] if found else None


def binding_hash(binding):
    return digest(json.dumps([binding.workspace_id, binding.channel_id, binding.instance,
                              binding.session, binding.account_id, binding.revision, binding.engine]))


def stored(row):
    value = row['configuracao'].get('whatsapp_management', {'revision': 0, 'receipts': []})
    if not isinstance(value, dict) or type(value.get('revision')) is not int or value['revision'] < 0 or not isinstance(value.get('receipts'), list):
        raise HTTPException(503, 'Configuração WhatsApp precisa ser conferida pela equipe.')
    return value


def channel_verified(conn, binding):
    return binding and conn.execute("SELECT 1 FROM socialmei.crm_canais WHERE workspace_id=%s AND id=%s AND instancia=%s AND sessao=%s AND identificador_conta=%s AND versao=%s AND provedor='waha' AND ativo AND ingress_provisioned",
        (binding.workspace_id, binding.channel_id, binding.instance, binding.session, binding.account_id, binding.revision)).fetchone()


def snapshot(conn, user, value, bindings):
    enabled, _ = configuration()
    binding = bound(bindings, user['workspace_id'])
    configured = bool(channel_verified(conn, binding))
    observation = value.get('observation', {})
    fresh = False
    if configured and observation.get('binding') == binding_hash(binding):
        try:
            fresh = -5 <= (now() - datetime.fromisoformat(observation['checked_at'])).total_seconds() <= 120
        except (KeyError, TypeError, ValueError):
            fresh = False
    provider_status = observation.get('status') if fresh else None
    state = {'WORKING': 'connected', 'STOPPED': 'disconnected', 'STARTING': 'connecting',
             'SCAN_QR_CODE': 'configuration_pending', 'FAILED': 'attention'}.get(provider_status,
             'configuration_pending' if configured or value.get('intent') else 'not_connected')
    live = provider_status == 'WORKING'
    recent = False
    if live and observation.get('first_verified_at'):
        receipt = conn.execute("SELECT max(processado_em) FROM socialmei.crm_eventos_canal WHERE workspace_id=%s AND canal_id=%s AND waha_account_snapshot=%s AND inbox_origin='waha' AND tipo='message' AND status='processado' AND processado_em>=%s AND processado_em>NOW()-INTERVAL '15 minutes' AND ocorrida_em>NOW()-INTERVAL '15 minutes' AND ocorrida_em<=NOW()",
                              (user['workspace_id'], binding.channel_id, binding.account_id, observation['first_verified_at'])).fetchone()
        recent = bool(receipt and receipt['max'])
    sending = False
    try:
        sender = settings.whatsapp_human_configuration()
        sending = bool(live and sender and all(getattr(sender, k) == getattr(binding, k) for k in ('workspace_id', 'instance', 'session', 'account_id', 'engine')))
    except ValueError:
        pass
    intent = value.get('intent')
    return {'source': 'server', 'workspace_id': user['workspace_id'], 'revision': value['revision'],
            'provider': 'waha_experimental', 'connection_state': state,
            'private_binding_verified': configured, 'session_live_verified': live,
            'receiving_messages': recent, 'sending_enabled': sending,
            'engine': binding.engine if configured else None,
            'checked_at': observation.get('checked_at') if fresh else None,
            'request': {'action': intent['action'], 'status': 'awaiting_operator_approval', 'requested_at': intent['requested_at'], 'phone_hint': intent.get('phone_hint')} if isinstance(intent, dict) else None,
            'management_available': enabled, 'probe_available': bool(enabled and configured and os.getenv('SOCIALMEI_WAHA_MANAGEMENT_PROBE_ENABLED', 'false') == 'true'),
            'pairing_available': False, 'external_mutations_enabled': False,
            'official_business_platform_available': False,
            'next_step': 'Solicitações não alteram sessões. A equipe deve conferir capacidade, titularidade do número, registro privado e respondedor único antes de executar.'}


@router.get('')
def status(request: Request):
    user = actor(request)
    if request.query_params:
        raise HTTPException(422, 'Utilize o negócio da sessão.')
    bindings = registry()
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute('SET TRANSACTION READ ONLY')
        row = conn.execute('SELECT configuracao FROM socialmei.workspaces WHERE id=%s', (user['workspace_id'],)).fetchone()
        return snapshot(conn, user, stored(row), bindings)


class Intent(Strict):
    operation_id: UUID
    expected_revision: int = Field(ge=0, strict=True)
    action: Literal['connect', 'reconnect', 'disconnect', 'cancel']
    confirmed: bool = Field(strict=True)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator('phone')
    @classmethod
    def phone_format(cls, value):
        if value is None:
            return None
        validate_phone(value)
        digits = re.sub(r'\D', '', value, flags=re.ASCII)
        if not value.strip().startswith('+'):
            digits = '55' + digits
        if not re.fullmatch(r'[1-9][0-9]{7,14}', digits):
            raise ValueError('Informe o número completo com código do país.')
        return digits


@router.post('/requests', status_code=202)
def request_change(payload: Intent, request: Request):
    user = actor(request, write=True)
    enabled, capacity = configuration()
    if not enabled:
        raise HTTPException(503, 'Solicitações WhatsApp ainda não habilitadas neste ambiente.')
    if payload.confirmed is not True:
        raise HTTPException(422, 'Confira o negócio e confirme a solicitação.')
    if payload.action == 'connect' and not payload.phone:
        raise HTTPException(422, 'Informe o número que pretende conectar.')
    if payload.action != 'connect' and payload.phone is not None:
        raise HTTPException(422, 'Não informe outro número para esta operação.')
    fingerprint = digest(payload.model_dump_json())
    throttle(str(user['id']), 'whatsapp-management')
    bindings = registry()
    if bindings is None:
        raise HTTPException(503, 'O registro privado precisa estar disponível antes de solicitar uma sessão.')
    binding = bound(bindings, user['workspace_id'])
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute('SELECT pg_advisory_xact_lock(72426061)')
        team_members.locked_scope(conn, user, request)
        row = conn.execute('SELECT configuracao FROM socialmei.workspaces WHERE id=%s', (user['workspace_id'],)).fetchone()
        value = stored(row)
        previous = next((r for r in value['receipts'] if r['operation'] == str(payload.operation_id)), None)
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise HTTPException(409, 'Esta tentativa já foi utilizada para outra solicitação.')
            return previous['result']
        if value['revision'] != payload.expected_revision:
            raise HTTPException(409, 'O estado mudou. Atualize antes de continuar.')
        if payload.action in {'reconnect', 'disconnect'} and not channel_verified(conn, binding):
            raise HTTPException(409, 'Não há sessão privada confirmada para este negócio.')
        if payload.action == 'connect' and binding:
            raise HTTPException(409, 'Este negócio já tem vínculo privado. Solicite reconexão ou transferência assistida.')
        if payload.action == 'connect':
            phone_hash = digest('waha-number:' + payload.phone)
            if any(b.account_id == payload.phone + '@c.us' for b in bindings):
                raise HTTPException(409, 'Esse número já tem vínculo. Uma transferência exige conferência pela equipe.')
            claims = conn.execute("SELECT id,configuracao->'whatsapp_management'->'intent' AS intent FROM socialmei.workspaces WHERE configuracao->'whatsapp_management'->'intent' IS NOT NULL").fetchall()
            active = []
            for claim in claims:
                intent = claim['intent']
                try:
                    if intent.get('action') == 'connect' and datetime.fromisoformat(intent['requested_at']) > now() - timedelta(hours=1):
                        active.append(claim)
                except (KeyError, TypeError, ValueError, AttributeError):
                    raise HTTPException(503, 'As solicitações precisam ser conciliadas pela equipe.') from None
            if any(c['id'] != user['workspace_id'] and c['intent'].get('phone_hash') == phone_hash for c in active):
                raise HTTPException(409, 'Esse número já tem uma solicitação em andamento. A equipe precisa conferir a titularidade.')
            if len(bindings) + sum(c['id'] != user['workspace_id'] for c in active) >= capacity:
                raise HTTPException(429, 'Capacidade de sessões atingida. Aguarde a conferência da equipe.')
        value = {**value, 'revision': value['revision'] + 1}
        if payload.action == 'cancel':
            value.pop('intent', None)
        else:
            value['intent'] = {'action': payload.action, 'requested_at': now().isoformat(),
                               **({'phone_hash': digest('waha-number:' + payload.phone), 'phone_hint': '•••• ' + payload.phone[-4:]} if payload.phone else {})}
        result = {'accepted': True, 'revision': value['revision'], 'status': 'cancelled' if payload.action == 'cancel' else 'awaiting_operator_approval', 'executed': False}
        value['receipts'] = (value['receipts'] + [{'operation': str(payload.operation_id), 'fingerprint': fingerprint, 'result': result}])[-10:]
        conn.execute("UPDATE socialmei.workspaces SET configuracao=jsonb_set(configuracao,'{whatsapp_management}',%s::jsonb),atualizado_em=NOW() WHERE id=%s", (json.dumps(value), user['workspace_id']))
        conn.execute('INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,%s)', (user['id'], f"waha:{user['workspace_id']}:solicitacao"))
        return result


def probe_configuration(binding):
    base = os.getenv('SOCIALMEI_WAHA_PRIVATE_BASE_URL', '')
    key = os.getenv('SOCIALMEI_WAHA_PRIVATE_API_KEY', '')
    if not re.fullmatch(r'[!-~]{16,4096}', key):
        raise HTTPException(503, 'Consulta privada da sessão ainda não configurada.')
    return settings.WhatsAppHumanConfiguration(binding.workspace_id, binding.instance, binding.session, binding.account_id,
        frozenset(), base, key, False, binding.engine)


@router.post('/inspect')
def inspect(request: Request):
    user = actor(request, write=True)
    enabled, _ = configuration()
    if not enabled or os.getenv('SOCIALMEI_WAHA_MANAGEMENT_PROBE_ENABLED', 'false') != 'true':
        raise HTTPException(503, 'Consulta ao provedor ainda não autorizada neste ambiente.')
    throttle(str(user['workspace_id']), 'whatsapp-probe')
    binding = bound(registry(), user['workspace_id'])
    if not binding:
        raise HTTPException(409, 'A equipe precisa provisionar o vínculo privado antes do pareamento.')
    with connect() as conn:
        conn.row_factory = dict_row
        team_members.locked_scope(conn, user, request)
        if not channel_verified(conn, binding):
            raise HTTPException(409, 'O canal não corresponde ao vínculo privado atual.')
    try:
        observation = WahaHumanTransport(probe_configuration(binding)).inspect_session()
    except Exception:
        raise HTTPException(503, 'Não foi possível confirmar a sessão. Nenhuma reconexão ou envio foi executado.') from None
    with connect() as conn:
        conn.row_factory = dict_row
        team_members.locked_scope(conn, user, request)
        current_binding = bound(registry(), user['workspace_id'])
        if current_binding is None or binding_hash(current_binding) != binding_hash(binding) or not channel_verified(conn, binding):
            raise HTTPException(409, 'O vínculo mudou durante a consulta. Confira novamente.')
        row = conn.execute('SELECT configuracao FROM socialmei.workspaces WHERE id=%s', (user['workspace_id'],)).fetchone()
        value = stored(row)
        previous = value.get('observation', {})
        first = previous.get('first_verified_at') if previous.get('binding') == binding_hash(binding) and previous.get('status') == 'WORKING' else None
        value['observation'] = {'binding': binding_hash(binding), 'status': observation['status'], 'checked_at': now().isoformat(),
                                'first_verified_at': (first or now().isoformat()) if observation['status'] == 'WORKING' else None}
        conn.execute("UPDATE socialmei.workspaces SET configuracao=jsonb_set(configuracao,'{whatsapp_management}',%s::jsonb),atualizado_em=NOW() WHERE id=%s", (json.dumps(value), user['workspace_id']))
        return snapshot(conn, user, value, [binding])
