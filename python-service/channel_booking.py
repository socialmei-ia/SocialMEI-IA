"""Shared booking core for authenticated, persisted WhatsApp and Instagram input."""
import base64
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import hmac
import json
import re
from uuid import NAMESPACE_URL, UUID, uuid5
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import Field, field_validator, model_validator

from agenda import Strict, configure
from database import connect
from shared_data import MAX_SAFE_ID
import settings


class TimeWindow(Strict):
    opens: str
    closes: str

    @field_validator('opens', 'closes')
    @classmethod
    def clock(cls, value):
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', value):
            raise ValueError('Informe horário no formato HH:MM.')
        return value

    @model_validator(mode='after')
    def increasing(self):
        if self.opens >= self.closes:
            raise ValueError('O fechamento deve ocorrer depois da abertura no mesmo dia.')
        return self


class OpeningWindow(TimeWindow):
    weekday: int = Field(ge=0, le=6, strict=True)


class SpecialDay(Strict):
    day: date
    hours: list[TimeWindow] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def non_overlapping_windows(self):
        ordered = sorted(self.hours, key=lambda item: item.opens)
        if any(a.closes > b.opens for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Os horários especiais não podem se sobrepor.')
        return self


class BookingPolicy(Strict):
    enabled: bool = Field(default=False, strict=True)
    timezone: str = Field(default_factory=lambda: settings.business_timezone().key)
    hours: list[OpeningWindow] = Field(default_factory=list, max_length=21)
    special_days: list[SpecialDay] = Field(default_factory=list, max_length=120)
    step_minutes: int = Field(default=15, ge=5, le=120, strict=True)
    lead_minutes: int = Field(default=60, ge=0, le=10080, strict=True)
    horizon_days: int = Field(default=30, ge=1, le=60, strict=True)

    @field_validator('timezone')
    @classmethod
    def zone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError('Selecione um fuso horário válido.') from None
        return value

    @model_validator(mode='after')
    def non_overlapping_hours(self):
        if self.enabled and not self.hours:
            raise ValueError('Defina os horários antes de habilitar agendamento pelos canais.')
        if len({item.day for item in self.special_days}) != len(self.special_days):
            raise ValueError('Informe cada data especial uma única vez.')
        ordered = sorted(self.hours, key=lambda item: (item.weekday, item.opens))
        for before, after in zip(ordered, ordered[1:]):
            if before.weekday == after.weekday and after.opens < before.closes:
                raise ValueError('Os horários de funcionamento não podem se sobrepor.')
        return self


class BookingPolicyUpdate(Strict):
    expected_revision: int = Field(ge=0, strict=True)
    policy: BookingPolicy


class MessageContext(Strict):
    origin: Literal['waha', 'instagram']
    conversation_id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)
    source_message_id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)


class ResourceRequest(MessageContext):
    service_id: int = Field(ge=1, le=MAX_SAFE_ID, strict=True)


class SlotRequest(ResourceRequest):
    resource_id: UUID
    day: date
    page: int = Field(default=0, ge=0, le=100, strict=True)


class ConfirmationRequest(MessageContext):
    confirmation: str = Field(min_length=1, max_length=1600)
    confirmed: bool = Field(strict=True)


@contextmanager
def transaction(connection=None):
    if connection is not None:
        configure(connection)
        yield connection
    else:
        with connect() as conn:
            configure(conn)
            yield conn


def read_policy(conn, workspace_id, *, lock=False):
    row = conn.execute('SELECT configuracao FROM socialmei.workspaces WHERE id=%s' +
                       (' FOR UPDATE' if lock else ' FOR SHARE'), (workspace_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Negócio indisponível.')
    stored = row['configuracao'].get('channel_booking')
    if stored is None:
        return {'revision': 0, 'policy': dump_policy(BookingPolicy())}
    try:
        if type(stored['revision']) is not int or stored['revision'] < 1:
            raise ValueError()
        policy = BookingPolicy.model_validate(stored['policy'])
        return {'revision': stored['revision'], 'policy': dump_policy(policy)}
    except (KeyError, TypeError, ValueError):
        raise HTTPException(503, 'Confira as configurações de agendamento deste negócio.') from None


def save_policy(conn, workspace_id, payload):
    previous = read_policy(conn, workspace_id, lock=True)
    if previous['revision'] != payload.expected_revision:
        raise HTTPException(409, 'As configurações mudaram. Recarregue antes de salvar.')
    result = {'revision': previous['revision'] + 1, 'policy': dump_policy(payload.policy)}
    conn.execute("UPDATE socialmei.workspaces SET configuracao=jsonb_set(configuracao,'{channel_booking}',%s::jsonb),atualizado_em=NOW() WHERE id=%s",
                 (json.dumps(result), workspace_id))
    return result


def context_for_message(conn, workspace, conversation, message, origin, *, allow_media_read=False):
    if (origin not in {'waha', 'instagram'} or any(type(value) is not int or value < 1
            for value in [workspace, conversation, message])):
        raise HTTPException(403, 'Conversa indisponível para agendamento.')
    if not conn.execute('SELECT id FROM socialmei.workspaces WHERE id=%s FOR SHARE', (workspace,)).fetchone():
        raise HTTPException(403, 'Negócio indisponível.')
    row = conn.execute('SELECT v.id,v.cliente_id,v.account_ref,v.contact_ref FROM '
        'socialmei.me_conversations v JOIN socialmei.me_messages m '
        'ON m.workspace_id=v.workspace_id AND m.conversation_id=v.id AND m.origin=v.origin '
        'WHERE v.workspace_id=%s AND v.id=%s AND m.id=%s AND v.origin=%s FOR SHARE OF v',
        (workspace, conversation, message, origin)).fetchone()
    if not row:
        raise HTTPException(404, 'Mensagem recebida não encontrada nesta conversa.')
    if origin == 'waha':
        channel = conn.execute("SELECT c.id,c.versao FROM socialmei.crm_canais c JOIN "
            "socialmei.crm_eventos_canal e ON e.workspace_id=c.workspace_id AND e.canal_id=c.id "
            "WHERE c.workspace_id=%s AND e.inbox_message_id=%s AND e.inbox_origin='waha' "
            "AND e.status='processado' AND e.tipo='message' AND e.waha_account_snapshot=c.identificador_conta "
            "AND c.provedor='waha' AND c.ativo AND c.ingress_provisioned "
            "AND %s='waha:' || c.identificador_conta FOR SHARE OF c",
            (workspace, message, row['account_ref'])).fetchone()
    else:
        channel = conn.execute("SELECT c.id,c.revision AS versao FROM socialmei.ig_meta_connections c JOIN "
            "socialmei.ig_meta_ingress_events e ON e.workspace_id=c.workspace_id AND e.connection_id=c.id "
            "AND e.external_account_id=c.external_account_id WHERE c.workspace_id=%s AND e.message_id=%s "
            "AND (e.kind='message' OR (%s AND e.kind='media')) AND e.status='processed' AND c.status='connected' AND c.expires_at>NOW() "
            "AND c.scopes @> ARRAY['instagram_business_basic','instagram_business_manage_messages']::text[] "
            "AND %s='instagram:' || c.external_account_id FOR SHARE OF c",
            (workspace, message, allow_media_read, row['account_ref'])).fetchone()
    if not channel:
        raise HTTPException(403, 'Canal não está conectado a este negócio.')
    if row['cliente_id'] is None:
        raise HTTPException(409, 'Nossa equipe precisa associar seu cadastro antes de confirmar um horário.')
    if origin == 'waha':
        conn.execute("INSERT INTO socialmei.wa_bot_conversations(workspace_id,channel_id,conversation_id) "
                     "VALUES(%s,%s,%s) ON CONFLICT DO NOTHING", (workspace, channel['id'], conversation))
        human = conn.execute("SELECT state FROM socialmei.wa_bot_conversations WHERE workspace_id=%s "
                             "AND channel_id=%s AND conversation_id=%s FOR UPDATE",
                             (workspace, channel['id'], conversation)).fetchone()
        pending = conn.execute("SELECT 1 FROM socialmei.wa_human_replies WHERE workspace_id=%s "
            "AND channel_id=%s AND conversation_id=%s AND status IN ('dispatching','uncertain') LIMIT 1",
            (workspace, channel['id'], conversation)).fetchone()
    else:
        conn.execute("INSERT INTO socialmei.ig_menu_conversations(workspace_id,conversation_id) "
                     "VALUES(%s,%s) ON CONFLICT DO NOTHING", (workspace, conversation))
        human = conn.execute("SELECT state FROM socialmei.ig_menu_conversations WHERE workspace_id=%s "
                             "AND conversation_id=%s FOR UPDATE", (workspace, conversation)).fetchone()
        pending = conn.execute("SELECT 1 FROM socialmei.ig_direct_jobs WHERE workspace_id=%s "
            "AND conversation_id=%s AND status IN ('draft','approved','dispatching','retry_ready','uncertain') LIMIT 1",
            (workspace, conversation)).fetchone()
    if pending or human and human['state'] == 'human':
        raise HTTPException(409, 'Atendimento humano em andamento. Continue com nossa equipe.')
    binding = [workspace, conversation, origin, row['account_ref'], row['contact_ref'],
               row['cliente_id'], str(channel['id']), channel['versao']]
    return {**row, 'channel_id': channel['id'], 'channel_revision': channel['versao'],
            'binding': hashlib.sha256(json.dumps(binding).encode()).hexdigest()}


def active_policy(conn, workspace):
    snapshot = read_policy(conn, workspace)
    policy = BookingPolicy.model_validate(snapshot['policy'])
    if not policy.enabled:
        raise HTTPException(409, 'O agendamento por conversa ainda precisa ser configurado pela equipe.')
    return policy, hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def signing_key_for_context(conn, workspace, conversation, message, origin):
    context = context_for_message(conn, workspace, conversation, message, origin)
    if origin == 'waha':
        from waha_ingress import waha_service
        bindings = [binding for binding in waha_service().registry.values()
                    if binding.workspace_id == workspace
                    and context['account_ref'] == 'waha:' + binding.account_id
                    and context['channel_id'] == binding.channel_id
                    and context['channel_revision'] == binding.revision]
        if len(bindings) != 1:
            raise HTTPException(503, 'Confirmação de horário ainda não configurada.')
        key = bindings[0].hmac_key
    else:
        key = settings.instagram_n8n_ingress_configuration().get('meta_app_secret')
        if not key:
            key = settings.instagram_runtime_configuration().get('client_secret')
    signing_digest(key, b'')
    return key


def services_for_message(workspace_id, conversation_id, source_message_id, origin, *, connection=None, allow_media_read=False):
    with transaction(connection) as conn:
        context_for_message(conn, workspace_id, conversation_id, source_message_id, origin, allow_media_read=allow_media_read)
        active_policy(conn, workspace_id)
        rows = conn.execute("SELECT id,nome,preco,duracao_minutos FROM socialmei.crm_produtos "
            "WHERE workspace_id=%s AND tipo='Serviço' AND status='Ativo' AND duracao_minutos IS NOT NULL "
            "ORDER BY nome,id LIMIT 101", (workspace_id,)).fetchall()
    return {'items': [{**row, 'preco': str(row['preco'])} for row in rows[:100]], 'truncated': len(rows)>100}


def resources_for_message(workspace_id, conversation_id, source_message_id, origin, service_id, *, connection=None):
    from appointments import service
    with transaction(connection) as conn:
        context_for_message(conn, workspace_id, conversation_id, source_message_id, origin)
        active_policy(conn, workspace_id)
        service(conn, workspace_id, service_id)
        rows = conn.execute("SELECT id,nome FROM socialmei.agenda_resources WHERE workspace_id=%s "
                            "AND ativo ORDER BY nome,id LIMIT 101", (workspace_id,)).fetchall()
    return {'items': [{**row, 'id': str(row['id'])} for row in rows[:100]], 'truncated': len(rows)>100}


def dump_policy(policy):
    dump = policy.model_dump(mode='json')
    if not dump['special_days']:
        del dump['special_days']
    return dump


def windows_for_day(policy, day):
    for special in policy.special_days:
        if special.day == day:
            return sorted(special.hours, key=lambda item: item.opens)
    return sorted((window for window in policy.hours if window.weekday == day.weekday()),
                  key=lambda item: item.opens)


def allowed_start(policy, start, duration, now):
    zone = ZoneInfo(policy.timezone)
    local = start.astimezone(zone)
    end = start.astimezone(timezone.utc) + timedelta(minutes=duration)
    local_end = end.astimezone(zone)
    if (start < now + timedelta(minutes=policy.lead_minutes)
            or local.date() > now.astimezone(zone).date() + timedelta(days=policy.horizon_days)
            or local.second or local.microsecond or local.date() != local_end.date()):
        return False
    # Reject ambiguous/nonexistent local times rather than offering an uncertain slot.
    for value in (local, local_end):
        if value.replace(fold=0).utcoffset() != value.replace(fold=1).utcoffset():
            return False
        roundtrip = value.astimezone(timezone.utc).astimezone(zone)
        if roundtrip.replace(tzinfo=None) != value.replace(tzinfo=None):
            return False
    for window in windows_for_day(policy, local.date()):
        if window.opens <= local.strftime('%H:%M') and local_end.strftime('%H:%M') <= window.closes:
            opening = datetime.combine(local.date(), time.fromisoformat(window.opens), tzinfo=zone)
            return int((local - opening).total_seconds()) % (policy.step_minutes * 60) == 0
    return False


def bookable_days(policy, duration, now):
    """Calendar candidates only; resource conflicts remain checked at slot/confirm."""
    zone = ZoneInfo(policy.timezone)
    today = now.astimezone(zone).date()
    days = []
    for offset in range(policy.horizon_days + 1):
        day = today + timedelta(days=offset)
        for window in windows_for_day(policy, day):
            start = datetime.combine(day, time.fromisoformat(window.opens), tzinfo=zone)
            closing = datetime.combine(day, time.fromisoformat(window.closes), tzinfo=zone)
            while start + timedelta(minutes=duration) <= closing:
                if allowed_start(policy, start, duration, now):
                    days.append(day)
                    break
                start += timedelta(minutes=policy.step_minutes)
            if days and days[-1] == day:
                break
    return days


def signing_digest(key, raw):
    if not isinstance(key, str) or len(key.encode()) < 32:
        raise HTTPException(503, 'Confirmação de horário ainda não configurada.')
    return hmac.new(key.encode(), b'socialmei-channel-booking-v1\0' + raw, hashlib.sha256).digest()


def confirmation_token(value, key):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=') + '.' + signing_digest(key, raw).hex()


def decode_confirmation(token, key):
    try:
        if not isinstance(token, str) or len(token) > 1600:
            raise ValueError()
        encoded, signature = token.split('.')
        raw = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True)
        if not hmac.compare_digest(bytes.fromhex(signature), signing_digest(key, raw)):
            raise ValueError()
        value = json.loads(raw)
        if set(value) != {'binding','policy','service','service_revision','resource','resource_revision','start','expires'}:
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise HTTPException(409, 'Esta opção de horário expirou ou mudou. Consulte os horários novamente.') from None


def slots_for_message(workspace_id, conversation_id, source_message_id, origin, service_id,
                      resource_id, day, signing_key, *, page=0, connection=None, appointment_reference=None):
    from appointments import service, lock_resource, free, end_time
    try:
        day = date.fromisoformat(day) if isinstance(day, str) else day
        if type(day) is not date or not 1 <= day.year <= 9998:
            raise ValueError()
        resource_id = UUID(str(resource_id))
    except (TypeError, ValueError):
        raise HTTPException(422, 'Selecione uma data e um recurso válidos.') from None
    if type(page) is not int or not 0 <= page <= 100:
        raise HTTPException(422, 'Escolha uma página de horários válida.')
    offset = page * 3
    now = datetime.now(timezone.utc)
    with transaction(connection) as conn:
        if appointment_reference is not None:
            from appointments import lock_workspace
            lock_workspace(conn, workspace_id)
        context = context_for_message(conn, workspace_id, conversation_id, source_message_id, origin)
        existing = None
        if appointment_reference is not None:
            existing = owned_appointment(conn, workspace_id, context, appointment_reference)
            if (appointment_snapshot(existing) != appointment_reference.get('snapshot')
                    or existing['revision'] != appointment_reference['revision'] or existing['status'] != 'pending'
                    or existing['scheduled_for'] <= now or existing['servico_id'] != service_id
                    or str(existing['resource_id']) != str(resource_id)):
                raise HTTPException(409, 'O agendamento mudou. Consulte novamente.')
        policy, policy_hash = active_policy(conn, workspace_id)
        resource = lock_resource(conn, workspace_id, resource_id)
        item = service(conn, workspace_id, service_id)
        if existing is not None and (item['preco'] != existing['price']
                or item['duracao_minutos'] != existing['duration_minutes']):
            raise HTTPException(409, 'As condições do serviço mudaram. Fale com nossa equipe.')
        slots = []
        seen = 0
        for window in windows_for_day(policy, day):
            start = datetime.combine(day, time.fromisoformat(window.opens), tzinfo=ZoneInfo(policy.timezone))
            end = datetime.combine(day, time.fromisoformat(window.closes), tzinfo=ZoneInfo(policy.timezone))
            while (end_time(start.astimezone(timezone.utc), item['duracao_minutos']).astimezone(start.tzinfo) <= end
                   and seen < offset + 4):
                until = end_time(start.astimezone(timezone.utc), item['duracao_minutos']).astimezone(start.tzinfo)
                if allowed_start(policy, start, item['duracao_minutos'], now) and free(conn, workspace_id, resource['id'], start, until, existing['id'] if existing is not None else None):
                    if seen >= offset:
                        value = {'binding': context['binding'], 'policy': policy_hash, 'service': service_id,
                        'service_revision': item['versao'], 'resource': str(resource['id']),
                        'resource_revision': resource['revision'], 'start': start.astimezone(timezone.utc).isoformat(),
                        'expires': int(now.timestamp()) + 600}
                        slots.append({'service_id': service_id, 'service_name': item['nome'], 'price': str(item['preco']),
                            'duration_minutes': item['duracao_minutos'], 'resource_id': str(resource['id']),
                            'resource_name': resource['nome'], 'scheduled_for': start.isoformat(), 'ends_at': until.isoformat(),
                            'confirmation': confirmation_token(value, signing_key)})
                    seen += 1
                start += timedelta(minutes=policy.step_minutes)
    return {'items': slots[:3], 'has_more': len(slots) > 3,
            'reservation_created': False, 'timezone': policy.timezone}


def confirm_for_message(workspace_id, conversation_id, source_message_id, origin, confirmation,
                        signing_key, *, confirmed=False, connection=None):
    from appointments import (AppointmentCreate, service, lock_workspace, lock_resource,
                              existing_appointment_in, create_appointment_in)
    if confirmed is not True:
        raise HTTPException(409, 'Confirme os detalhes antes de agendar.')
    value = decode_confirmation(confirmation, signing_key)
    now = datetime.now(timezone.utc)
    with transaction(connection) as conn:
        lock_workspace(conn, workspace_id)
        context = context_for_message(conn, workspace_id, conversation_id, source_message_id, origin)
        if value['binding'] != context['binding']:
            raise HTTPException(409, 'A conversa ou as condições mudaram. Consulte os horários novamente.')
        try:
            start = datetime.fromisoformat(value['start'])
            if start.tzinfo is None or type(value['expires']) is not int:
                raise ValueError()
            resource_id = UUID(value['resource'])
        except (ValueError, TypeError):
            raise HTTPException(409, 'Esta opção de horário expirou. Consulte os horários novamente.') from None
        operation = uuid5(NAMESPACE_URL, 'socialmei-channel-booking-v1:' + confirmation)
        payload = AppointmentCreate(operation_id=operation, cliente_id=context['cliente_id'],
            servico_id=value['service'], resource_id=resource_id, scheduled_for=start,
            notes='Agendamento confirmado pelo canal ' + origin + '; conversa ' + str(conversation_id) + '.')
        previous = existing_appointment_in(conn, workspace_id, payload)
        if previous is not None:
            return previous
        policy, policy_hash = active_policy(conn, workspace_id)
        if value['policy'] != policy_hash or value['expires'] < now.timestamp():
            raise HTTPException(409, 'Esta opção de horário expirou ou mudou. Consulte os horários novamente.')
        resource = lock_resource(conn, workspace_id, resource_id)
        item = service(conn, workspace_id, value['service'])
        if (item['versao'] != value['service_revision'] or resource['revision'] != value['resource_revision']
                or not allowed_start(policy, start, item['duracao_minutos'], now)):
            raise HTTPException(409, 'O serviço ou horário mudou. Consulte a disponibilidade novamente.')
        return create_appointment_in(conn, workspace_id, payload)


def appointment_snapshot(row):
    fields = ('id', 'cliente_id', 'servico_id', 'resource_id', 'service_name',
              'duration_minutes', 'price', 'scheduled_for', 'ends_at', 'status', 'revision')
    return hashlib.sha256(json.dumps({key: str(row[key]) for key in fields},
                                     sort_keys=True).encode()).hexdigest()


def appointments_for_message(workspace, conversation, message, origin, *, connection):
    context = context_for_message(connection, workspace, conversation, message, origin)
    rows = connection.execute("SELECT * FROM socialmei.agenda_appointments WHERE workspace_id=%s "
        "AND cliente_id=%s AND status='pending' AND scheduled_for>NOW() "
        "ORDER BY scheduled_for,id LIMIT 31", (workspace, context['cliente_id'])).fetchall()
    return [{**row, 'reference': {'id': str(row['id']), 'revision': row['revision'],
             'snapshot': appointment_snapshot(row), 'binding': context['binding']}} for row in rows]


def owned_appointment(conn, workspace, context, reference):
    try:
        identifier = UUID(reference['id'])
        if (type(reference['revision']) is not int or reference['revision'] < 0
                or reference['binding'] != context['binding']):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise HTTPException(409, 'Esta seleção mudou. Consulte seus agendamentos novamente.') from None
    row = conn.execute("SELECT * FROM socialmei.agenda_appointments WHERE workspace_id=%s "
        "AND cliente_id=%s AND id=%s FOR UPDATE", (workspace, context['cliente_id'], identifier)).fetchone()
    if not row:
        raise HTTPException(404, 'Agendamento não disponível para esta conversa.')
    return row


def change_for_message(workspace, conversation, message, origin, reference, *,
                       confirmation=None, signing_key=None, confirmed=False, connection):
    """No visitor endpoint: only verified inbound context and server-stored menu references."""
    from appointments import lock_workspace, update_appointment_in, AppointmentUpdate, view, service, lock_resource
    if confirmed is not True:
        raise HTTPException(409, 'Confirme a alteração antes de continuar.')
    lock_workspace(connection, workspace)
    context = context_for_message(connection, workspace, conversation, message, origin)
    row = owned_appointment(connection, workspace, context, reference)
    start = row['scheduled_for']
    status = 'cancelled'
    if confirmation is not None:
        claims = decode_confirmation(confirmation, signing_key)
        try:
            start = datetime.fromisoformat(claims['start'])
            if (start.tzinfo is None or claims['binding'] != context['binding']
                    or claims['service'] != row['servico_id'] or claims['resource'] != str(row['resource_id'])):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise HTTPException(409, 'A confirmação não pertence a esta conversa.') from None
        status = 'pending'
    # Exact repeat of the accepted transition returns its receipt without writing history again.
    if (row['revision'] == reference['revision'] + 1 and row['status'] == status
            and row['scheduled_for'] == start):
        resource = lock_resource(connection, workspace, row['resource_id'], False)
        return view({**row, 'resource_name': resource['nome']})
    if (row['revision'] != reference['revision'] or appointment_snapshot(row) != reference.get('snapshot')
            or row['status'] != 'pending' or row['scheduled_for'] <= datetime.now(timezone.utc)):
        raise HTTPException(409, 'O agendamento mudou ou já ocorreu. Consulte novamente.')
    if confirmation is not None:
        policy, policy_hash = active_policy(connection, workspace)
        resource = lock_resource(connection, workspace, row['resource_id'])
        item = service(connection, workspace, row['servico_id'])
        if (claims['policy'] != policy_hash or type(claims['expires']) is not int
                or claims['expires'] < datetime.now(timezone.utc).timestamp()
                or claims['service'] != row['servico_id'] or claims['resource'] != str(row['resource_id'])
                or claims['service_revision'] != item['versao'] or claims['resource_revision'] != resource['revision']
                or item['duracao_minutos'] != row['duration_minutes'] or item['preco'] != row['price']
                or not allowed_start(policy, start, row['duration_minutes'], datetime.now(timezone.utc))):
            raise HTTPException(409, 'As condições mudaram. Consulte os horários novamente.')
    payload = AppointmentUpdate(expected_revision=reference['revision'], status=status,
                                **({'scheduled_for': start} if confirmation is not None else {}))
    return update_appointment_in(connection, workspace, row['id'], payload)
