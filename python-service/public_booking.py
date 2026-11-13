"""Opt-in visitor booking with verified email; no administrative visitor authority."""
import base64
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from email.message import EmailMessage
from email.headerregistry import Address
from email.errors import HeaderParseError
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import ssl
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
import psycopg
from pydantic import Field, field_validator

from account_auth import normalize_email, origin, require_enabled
from agenda import Strict, configure, identity
import channel_booking as booking
from database import connect
from shared_data import MAX_SAFE_ID


def unavailable():
    return HTTPException(503, 'Agendamento online indisponível. Entre em contato com o negócio.')


def secret():
    value = os.getenv('SOCIALMEI_PUBLIC_BOOKING_KEY', '')
    if len(value.strip().encode()) < 32 or '\r' in value or '\n' in value:
        raise unavailable()
    return value.encode()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def keyed(value):
    return hmac.new(secret(), value.encode(), hashlib.sha256).hexdigest()


def opaque(purpose, value, lifetime=600):
    key = base64.urlsafe_b64encode(hashlib.sha256(b'socialmei-public-booking-v1\0' + secret()).digest())
    body = {**value, 'purpose': purpose, 'expires': int(datetime.now(timezone.utc).timestamp()) + lifetime}
    return Fernet(key).encrypt(json.dumps(body, separators=(',', ':')).encode()).decode()


def decode(token, purpose, *, expired=False):
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 6000:
            raise ValueError()
        key = base64.urlsafe_b64encode(hashlib.sha256(b'socialmei-public-booking-v1\0' + secret()).digest())
        value = json.loads(Fernet(key).decrypt(token.encode()))
        if value.get('purpose') != purpose or type(value.get('expires')) is not int:
            raise ValueError()
        if not expired and value['expires'] < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError, UnicodeError, InvalidToken):
        raise HTTPException(409, 'Esta solicitação expirou ou mudou. Consulte os horários novamente.') from None


def limit(value, action, seconds, maximum):
    # Reuse durable hashed abuse counters, never recovery codes or account credentials.
    with connect() as conn:
        conn.execute("SET LOCAL statement_timeout='3s'")
        count = conn.execute(
            'INSERT INTO socialmei.auth_limites(chave) VALUES(%s) ON CONFLICT(chave) DO UPDATE SET '
            'tentativas=CASE WHEN auth_limites.inicio<NOW()-make_interval(secs=>%s) THEN 1 ELSE auth_limites.tentativas+1 END,'
            'inicio=CASE WHEN auth_limites.inicio<NOW()-make_interval(secs=>%s) THEN NOW() ELSE auth_limites.inicio END '
            'RETURNING tentativas', (keyed('public:' + action + ':' + value), seconds, seconds)).fetchone()[0]
        if count > maximum:
            conn.commit()
            raise HTTPException(429, 'Aguarde antes de tentar novamente.', headers={'Retry-After': str(seconds)})


def boundary(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    require_enabled()
    if os.getenv('SOCIALMEI_PUBLIC_BOOKING_ENABLED', 'false') != 'true':
        raise unavailable()
    secret()
    smtp_configuration()
    if request.method == 'POST' and (request.headers.get('origin') != origin()
            or request.headers.get('content-type', '').split(';', 1)[0].lower() != 'application/json'):
        raise HTTPException(403, 'Solicitação não permitida.')
    peer = request.client.host if request.client else 'unknown'
    try:
        limit('all', 'read-global', 60, 600)
        limit(peer, 'read', 60, 120)
        yield
    except psycopg.Error:
        raise unavailable() from None


router = APIRouter(prefix='/api/v1/public/booking', tags=['public booking'], dependencies=[Depends(boundary)])
admin_router = APIRouter(prefix='/api/v1/agenda', tags=['public booking configuration'])


class Publication(Strict):
    enabled: bool = Field(default=False, strict=True)
    service_ids: list[int] = Field(default_factory=list, max_length=50)
    resource_ids: list[UUID] = Field(default_factory=list, max_length=50)
    allow_new_customers: bool = Field(default=False, strict=True)
    allow_verified_email_match: bool = Field(default=False, strict=True)

    @field_validator('service_ids', mode='before')
    @classmethod
    def service_ids_valid(cls, values):
        if not isinstance(values, list) or any(type(v) is not int or not 1 <= v <= MAX_SAFE_ID for v in values) or len(set(values)) != len(values):
            raise ValueError('Selecione serviços válidos.')
        return values

    @field_validator('resource_ids')
    @classmethod
    def unique_resources(cls, values):
        if len(set(values)) != len(values):
            raise ValueError('Selecione cada profissional uma única vez.')
        return values


class PublicationUpdate(Strict):
    expected_revision: int = Field(ge=0, strict=True)
    policy: Publication


def publication(row):
    stored = row['configuracao'].get('public_booking', {'revision': 0, 'policy': {}})
    try:
        if type(stored['revision']) is not int or stored['revision'] < 0:
            raise ValueError()
        return {'revision': stored['revision'], 'policy': Publication.model_validate(stored['policy']).model_dump(mode='json')}
    except (ValueError, TypeError, KeyError):
        raise unavailable() from None


@contextmanager
def business(slug, *, replay=False):
    with connect() as conn:
        configure(conn)
        row = conn.execute('SELECT id,nome,slug,configuracao FROM socialmei.workspaces WHERE slug=%s FOR SHARE', (slug,)).fetchone()
        if not row:
            raise HTTPException(404, 'Agendamento indisponível para este negócio.')
        published = publication(row)
        if not published['policy']['enabled'] and not replay:
            raise HTTPException(404, 'Agendamento indisponível para este negócio.')
        if replay:
            snapshot = booking.read_policy(conn, row['id'])
            policy = booking.BookingPolicy.model_validate(snapshot['policy'])
            policy_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
        else:
            policy, policy_hash = booking.active_policy(conn, row['id'])
        yield conn, row, published['policy'], policy, fingerprint([published, policy_hash])


@admin_router.get('/public-booking')
def get_publication():
    user = identity()
    if user['role'] not in {'owner', 'admin'}:
        raise HTTPException(403, 'Somente responsáveis podem publicar a agenda.')
    with connect() as conn:
        configure(conn)
        row = conn.execute('SELECT slug,configuracao FROM socialmei.workspaces WHERE id=%s', (user['workspace_id'],)).fetchone()
        ready = os.getenv('SOCIALMEI_PUBLIC_BOOKING_ENABLED', 'false') == 'true'
        if ready:
            try:
                secret()
                smtp_configuration()
            except HTTPException:
                ready = False
        return {**publication(row), 'slug': row['slug'], 'server_enabled': ready}


@admin_router.put('/public-booking')
def update_publication(payload: PublicationUpdate):
    user = identity(write=True)
    if user['role'] not in {'owner', 'admin'}:
        raise HTTPException(403, 'Somente responsáveis podem publicar a agenda.')
    with connect() as conn:
        configure(conn)
        row = conn.execute('SELECT configuracao FROM socialmei.workspaces WHERE id=%s FOR UPDATE', (user['workspace_id'],)).fetchone()
        if publication(row)['revision'] != payload.expected_revision:
            raise HTTPException(409, 'A publicação mudou. Recarregue antes de salvar.')
        policy = payload.policy.model_dump(mode='json')
        if policy['enabled']:
            if not policy['allow_new_customers'] and not policy['allow_verified_email_match']:
                raise HTTPException(422, 'Defina como o contato verificado será cadastrado antes de publicar.')
            booking.active_policy(conn, user['workspace_id'])
            services = conn.execute("SELECT id FROM socialmei.crm_produtos WHERE workspace_id=%s AND id=ANY(%s::bigint[]) "
                "AND tipo='Serviço' AND status='Ativo' AND duracao_minutos IS NOT NULL", (user['workspace_id'], policy['service_ids'])).fetchall()
            resources = conn.execute('SELECT id FROM socialmei.agenda_resources WHERE workspace_id=%s AND id=ANY(%s::uuid[]) AND ativo',
                                     (user['workspace_id'], policy['resource_ids'])).fetchall()
            if (not services or not resources or len(services) != len(policy['service_ids'])
                    or len(resources) != len(set(policy['resource_ids']))):
                raise HTTPException(422, 'Selecione serviços e profissionais ativos deste negócio.')
        result = {'revision': payload.expected_revision + 1, 'policy': policy}
        conn.execute("UPDATE socialmei.workspaces SET configuracao=jsonb_set(configuracao,'{public_booking}',%s::jsonb),atualizado_em=NOW() WHERE id=%s",
                     (json.dumps(result), user['workspace_id']))
        conn.execute('INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,%s)',
                     (user['id'], f"agenda:{user['workspace_id']}:publica"))
    return result


class ServiceRequest(Strict):
    service: str = Field(min_length=1, max_length=3000)


class SlotsRequest(ServiceRequest):
    resource: str = Field(min_length=1, max_length=3000)
    day: date
    page: int = Field(default=0, ge=0, le=100, strict=True)


class VerificationRequest(Strict):
    offer: str = Field(min_length=1, max_length=6000)
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(max_length=255)
    @field_validator('email')
    @classmethod
    def single_email(cls, value):
        normalized = normalize_email(value)
        try:
            address = Address(addr_spec=normalized)
            if address.addr_spec != normalized or not address.username or not address.domain:
                raise ValueError()
        except (ValueError, HeaderParseError, IndexError):
            raise ValueError('Informe um único e-mail válido.') from None
        return normalized

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = ' '.join(value.split())
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError('Informe seu nome.')
        value.encode('utf-8')
        return value


class VerificationConfirm(Strict):
    challenge: str = Field(min_length=1, max_length=6000)
    code: str = Field(pattern=r'^[0-9]{6}$')


class Confirm(Strict):
    offer: str = Field(min_length=1, max_length=6000)
    proof: str = Field(min_length=1, max_length=6000)
    confirmed: bool = Field(strict=True)


def reference(token, purpose, workspace, allowed):
    value = decode(token, purpose)
    if value['workspace'] != workspace or value['id'] not in allowed:
        raise HTTPException(409, 'A seleção mudou. Consulte novamente.')
    return value['id']


@router.get('/{slug}')
def catalogue(slug: str):
    with business(slug) as (conn, row, published, policy, _):
        services = conn.execute("SELECT id,nome,preco,duracao_minutos FROM socialmei.crm_produtos WHERE workspace_id=%s "
            "AND id=ANY(%s::bigint[]) AND tipo='Serviço' AND status='Ativo' AND duracao_minutos IS NOT NULL ORDER BY nome,id",
            (row['id'], published['service_ids'])).fetchall()
        return {'name': row['nome'], 'timezone': policy.timezone, 'horizon_days': policy.horizon_days,
                'server_date': datetime.now(ZoneInfo(policy.timezone)).date().isoformat(),
                'services': [{'reference': opaque('service', {'workspace': row['id'], 'id': s['id']}, 3600),
                    'name': s['nome'], 'price': str(s['preco']), 'duration_minutes': s['duracao_minutos']} for s in services]}


@router.post('/{slug}/resources')
def resources(slug: str, payload: ServiceRequest):
    with business(slug) as (conn, row, published, _, __):
        service_id = reference(payload.service, 'service', row['id'], published['service_ids'])
        from appointments import service
        service(conn, row['id'], service_id)
        items = conn.execute('SELECT id,nome FROM socialmei.agenda_resources WHERE workspace_id=%s AND id=ANY(%s::uuid[]) AND ativo ORDER BY nome,id',
                             (row['id'], published['resource_ids'])).fetchall()
        return {'items': [{'reference': opaque('resource', {'workspace': row['id'], 'id': str(r['id'])}, 3600), 'name': r['nome']} for r in items]}


@router.post('/{slug}/slots')
def slots(slug: str, payload: SlotsRequest):
    from appointments import service, lock_resource, end_time
    with business(slug) as (conn, row, published, policy, binding):
        zone = ZoneInfo(policy.timezone)
        today = datetime.now(zone).date()
        if payload.day < today or (payload.day - today).days > policy.horizon_days:
            raise HTTPException(422, 'Selecione uma data dentro do período disponível.')
        sid = reference(payload.service, 'service', row['id'], published['service_ids'])
        rid = reference(payload.resource, 'resource', row['id'], published['resource_ids'])
        resource = lock_resource(conn, row['id'], UUID(rid))
        item = service(conn, row['id'], sid)
        start_day = datetime.combine(payload.day, time(), tzinfo=zone)
        busy = conn.execute("SELECT scheduled_for,ends_at FROM socialmei.agenda_appointments WHERE workspace_id=%s AND resource_id=%s "
            "AND status!='cancelled' AND scheduled_for<%s AND ends_at>%s LIMIT 1001",
            (row['id'], rid, start_day + timedelta(days=1), start_day)).fetchall()
        if len(busy) > 1000:
            raise unavailable()
        now = datetime.now(timezone.utc)
        found = []
        for window in policy.hours:
            if window.weekday != payload.day.weekday():
                continue
            start = datetime.combine(payload.day, time.fromisoformat(window.opens), tzinfo=zone)
            close = datetime.combine(payload.day, time.fromisoformat(window.closes), tzinfo=zone)
            while start < close:
                end = end_time(start.astimezone(timezone.utc), item['duracao_minutos']).astimezone(zone)
                if booking.allowed_start(policy, start, item['duracao_minutos'], now) and not any(
                        b['scheduled_for'] < end and b['ends_at'] > start for b in busy):
                    data = {'workspace': row['id'], 'binding': binding, 'service': sid, 'resource': rid,
                            'service_revision': item['versao'], 'resource_revision': resource['revision'],
                            'start': start.isoformat(), 'price': str(item['preco']), 'duration': item['duracao_minutos'],
                            'service_name': item['nome'], 'resource_name': resource['nome']}
                    found.append({'offer': opaque('offer', data), 'scheduled_for': start.isoformat(), 'ends_at': end.isoformat(),
                        'price': data['price'], 'duration_minutes': data['duration'],
                        'service_name': data['service_name'], 'resource_name': data['resource_name']})
                start += timedelta(minutes=policy.step_minutes)
        begin = payload.page * 12
        return {'items': found[begin:begin + 12], 'has_more': len(found) > begin + 12, 'timezone': policy.timezone}


def check_offer(conn, row, published, policy, binding, value):
    from appointments import service, lock_resource
    if (value['workspace'] != row['id'] or value['binding'] != binding
            or value['service'] not in published['service_ids'] or value['resource'] not in published['resource_ids']):
        raise HTTPException(409, 'Os detalhes mudaram. Consulte os horários novamente.')
    resource = lock_resource(conn, row['id'], UUID(value['resource']))
    item = service(conn, row['id'], value['service'])
    start = datetime.fromisoformat(value['start'])
    if (item['versao'] != value['service_revision'] or resource['revision'] != value['resource_revision']
            or item['nome'] != value['service_name'] or resource['nome'] != value['resource_name']
            or str(item['preco']) != value['price'] or item['duracao_minutos'] != value['duration']
            or not booking.allowed_start(policy, start, item['duracao_minutos'], datetime.now(timezone.utc))):
        raise HTTPException(409, 'Os detalhes mudaram. Consulte os horários novamente.')


def smtp_configuration():
    values = {k: os.getenv('SOCIALMEI_SMTP_' + k.upper(), '') for k in ('host', 'user', 'password', 'from')}
    try:
        port = int(os.getenv('SOCIALMEI_SMTP_PORT', '465'))
        if port not in (465, 587) or any(not v or '\r' in v or '\n' in v for v in values.values()):
            raise ValueError()
    except (ValueError, TypeError):
        raise unavailable() from None
    return {**values, 'port': port}


def send_code(address, code):
    values = smtp_configuration()
    port = values['port']
    try:
        message = EmailMessage()
        message['From'], message['To'] = values['from'], address
        message['Subject'] = 'SocialMEI — confirme seu agendamento'
        message.set_content('Seu código para verificar o contato é: ' + code + '\nVálido por 10 minutos. '
                            'A reserva só será criada após sua confirmação na página. Se não solicitou, ignore este e-mail.')
        context = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(values['host'], port, timeout=10, context=context) if port == 465
                  else smtplib.SMTP(values['host'], port, timeout=10))
        with server:
            if port == 587:
                server.starttls(context=context)
            server.login(values['user'], values['password'])
            server.send_message(message)
    except Exception:
        # SMTP acceptance may be uncertain. No proof or booking is issued on failure.
        raise HTTPException(503, 'Não foi possível enviar o código. Aguarde e tente novamente.') from None


@router.post('/{slug}/verification/request', status_code=202)
def request_verification(slug: str, payload: VerificationRequest, request: Request):
    value = decode(payload.offer, 'offer')
    limit(payload.email, 'mail', 3600, 3)
    limit('all', 'mail-global', 60, 30)
    limit('all', 'mail-day', 86400, 200)
    with business(slug, replay=True) as (conn, row, published, policy, binding):
        if not published['enabled'] or not policy.enabled:
            raise HTTPException(409, 'O agendamento online foi pausado. Entre em contato com o negócio.')
        check_offer(conn, row, published, policy, binding, value)
        workspace = row['id']
    nonce, code = str(uuid4()), f'{secrets.randbelow(1000000):06}'
    challenge = opaque('challenge', {'workspace': workspace, 'nonce': nonce, 'name': payload.name,
        'email': payload.email, 'offer_hash': fingerprint(payload.offer), 'code_hash': keyed(nonce + ':' + code)})
    send_code(payload.email, code)
    return {'challenge': challenge, 'message': 'Confira o código enviado ao seu e-mail. Nenhuma reserva foi criada ainda.'}


@router.post('/{slug}/verification/confirm')
def verify_contact(slug: str, payload: VerificationConfirm):
    value = decode(payload.challenge, 'challenge')
    limit(value['nonce'], 'code', 600, 8)
    with business(slug) as (_, row, __, ___, ____):
        if value['workspace'] != row['id'] or not hmac.compare_digest(value['code_hash'], keyed(value['nonce'] + ':' + payload.code)):
            raise HTTPException(400, 'Código inválido ou expirado.')
    proof = {key: value[key] for key in ('workspace', 'nonce', 'name', 'email', 'offer_hash')}
    # Verification cannot extend the original challenge lifetime.
    return {'proof': opaque('proof', proof, max(0, value['expires'] - int(datetime.now(timezone.utc).timestamp())))}


def public_receipt(row):
    status = {'pending': 'scheduled', 'done': 'completed', 'cancelled': 'cancelled'}[row['status']]
    return {'status': status, 'reference': keyed('receipt:' + str(row['id']))[:24],
            'scheduled_for': row['scheduled_for'].isoformat(), 'service_name': row['service_name'],
            'duration_minutes': row['duration_minutes'], 'price': str(row['price'])}


@router.post('/{slug}/confirm')
def confirm(slug: str, payload: Confirm):
    from appointments import AppointmentCreate, create_appointment_in, lock_workspace
    if payload.confirmed is not True:
        raise HTTPException(409, 'Confira e confirme os detalhes do agendamento.')
    offer = decode(payload.offer, 'offer', expired=True)
    proof = decode(payload.proof, 'proof', expired=True)
    if proof['workspace'] != offer['workspace'] or proof['offer_hash'] != fingerprint(payload.offer):
        raise HTTPException(409, 'A verificação não corresponde a este horário.')
    operation = uuid5(NAMESPACE_URL, 'socialmei-public-booking:' + proof['nonce'])
    with business(slug, replay=True) as (conn, row, published, policy, binding):
        if proof['workspace'] != row['id']:
            raise HTTPException(409, 'Verificação indisponível para este negócio.')
        lock_workspace(conn, row['id'])
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('public-booking:' + str(operation),))
        previous = conn.execute('SELECT id,status,scheduled_for,service_name,duration_minutes,price FROM socialmei.agenda_appointments WHERE workspace_id=%s AND id=%s',
                                (row['id'], operation)).fetchone()
        if previous:
            result = public_receipt(previous)
        else:
            if not published['enabled'] or not policy.enabled:
                raise HTTPException(409, 'O agendamento online foi pausado. Entre em contato com o negócio.')
            now = int(datetime.now(timezone.utc).timestamp())
            if min(proof['expires'], offer['expires']) < now:
                raise HTTPException(409, 'Esta solicitação expirou. Consulte os horários novamente.')
            check_offer(conn, row, published, policy, binding, offer)
            limit(proof['email'], 'booking-day:' + str(row['id']), 86400, 3)
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                         ('public-contact:' + str(row['id']) + ':' + keyed(proof['email']),))
            clients = conn.execute('SELECT id,status FROM socialmei.crm_clientes WHERE workspace_id=%s AND LOWER(BTRIM(email))=%s FOR UPDATE',
                                   (row['id'], proof['email'])).fetchall()
            if (len(clients) > 1 or (clients and (clients[0]['status'] != 'Ativo' or not published['allow_verified_email_match']))
                    or (not clients and not published['allow_new_customers'])):
                raise HTTPException(409, 'Nossa equipe precisa conferir seu cadastro. Entre em contato para concluir o agendamento.')
            client_id = clients[0]['id'] if clients else conn.execute(
                'INSERT INTO socialmei.crm_clientes(workspace_id,nome,email) VALUES(%s,%s,%s) RETURNING id',
                (row['id'], proof['name'], proof['email'])).fetchone()['id']
            appointment = AppointmentCreate(operation_id=operation, cliente_id=client_id, servico_id=offer['service'],
                resource_id=UUID(offer['resource']), scheduled_for=datetime.fromisoformat(offer['start']), notes='Agendamento pelo site; contato verificado por e-mail.')
            create_appointment_in(conn, row['id'], appointment)
            saved = conn.execute('SELECT id,status,scheduled_for,service_name,duration_minutes,price FROM socialmei.agenda_appointments WHERE workspace_id=%s AND id=%s',
                                 (row['id'], operation)).fetchone()
            result = public_receipt(saved)
    return result
