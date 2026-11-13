"""Opt-in account activation and workspace invitations. No provider calls in HTTP."""
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, field_validator

import account_auth as auth
from database import connect
from public_booking import smtp_configuration
from queue_wakeup import notify_queue
import team_members

router = APIRouter(prefix='/api/v1', tags=['identity activation'])
CHANNEL = 'socialmei_identity_mail'


def enabled():
    mode = os.getenv('SOCIALMEI_IDENTITY_MODE', 'disabled')
    if mode not in {'disabled', 'enforced'}:
        raise HTTPException(503, 'Ativação de conta indisponível.')
    return mode == 'enforced'


def configured():
    auth.require_enabled()
    if not enabled():
        raise HTTPException(503, 'Ativação por e-mail ainda não habilitada.')
    try:
        config = smtp_configuration()
    except HTTPException:
        raise HTTPException(503, 'Verificação por e-mail indisponível. Tente mais tarde ou procure o responsável pelo serviço.') from None
    with connect() as conn:
        if not all(conn.execute("SELECT to_regclass('socialmei.auth_email_activation'),to_regclass('socialmei.auth_identity_mail')").fetchone()):
            raise HTTPException(503, 'Ativação por e-mail ainda não instalada.')
    return config


def lock(conn):
    conn.execute("SET LOCAL lock_timeout='5s'")
    conn.execute("SET LOCAL statement_timeout='10s'")
    conn.execute('SELECT pg_advisory_xact_lock(72426060)')


def state(user_id):
    if not enabled():
        return None
    with connect() as conn:
        row = conn.execute('SELECT a.verified_at IS NOT NULL AND a.email=u.email FROM socialmei.auth_email_activation a JOIN socialmei.users u ON u.id=a.user_id WHERE a.user_id=%s', (user_id,)).fetchone()
    return {'required': row is not None, 'verified': bool(row and row[0])}


def guard(user, path):
    value = state(user['id'])
    allowed = {'/api/v1/auth/me', '/api/v1/auth/session', '/api/v1/auth/logout', '/api/v1/auth/password'}
    if value and value['required'] and not value['verified'] and path not in allowed and not path.startswith('/api/v1/auth/verification/'):
        raise HTTPException(403, 'Confirme seu e-mail para ativar a conta.')


def enqueue(conn, purpose, email, *, user_id=None, workspace=None, actor=None, role=None):
    lock(conn)
    if purpose == 'verification':
        conn.execute("UPDATE socialmei.auth_identity_mail SET status='revoked',token_hash=NULL,finished_at=NOW() WHERE purpose=%s AND user_id=%s AND status IN ('pending','processing','sent')", (purpose, user_id))
    else:
        conn.execute("UPDATE socialmei.auth_identity_mail SET status='revoked',token_hash=NULL,finished_at=NOW() WHERE purpose=%s AND workspace_id=%s AND email=%s AND status IN ('pending','processing','sent')", (purpose, workspace, email))
    job = uuid4()
    conn.execute('INSERT INTO socialmei.auth_identity_mail(id,purpose,email,user_id,workspace_id,created_by,role) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                 (job, purpose, email, user_id, workspace, actor, role))
    notify_queue(conn, CHANNEL)
    return job


def enroll(conn, user_id, email):
    if enabled():
        conn.execute('INSERT INTO socialmei.auth_email_activation(user_id,email) VALUES(%s,%s)', (user_id, email))
        enqueue(conn, 'verification', email, user_id=user_id)


class Code(auth.Strict):
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


class EmailCorrection(auth.Strict):
    email: str = Field(max_length=255)
    atual: str = Field(min_length=1, max_length=128)
    _email = field_validator('email')(auth.normalize_email)


class Invitation(auth.Strict):
    email: str = Field(max_length=255)
    role: Literal['admin', 'member', 'viewer', 'report_viewer']
    _email = field_validator('email')(auth.normalize_email)


class Acceptance(Code):
    email: str = Field(max_length=255)
    nome: str | None = Field(default=None, min_length=1, max_length=160)
    senha: str | None = Field(default=None, min_length=8, max_length=128)
    _email = field_validator('email')(auth.normalize_email)

    @field_validator('senha')
    @classmethod
    def password_valid(cls, value):
        return auth.validate_new_password(value) if value is not None else None


class AccessRevoke(auth.Strict):
    expected_role: Literal['admin', 'member', 'viewer', 'report_viewer']


def audit(conn, user, action, workspace=None):
    conn.execute('INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,%s)',
                 (user, ('equipe:' + str(workspace) + ':' if workspace else '') + action))


@router.get('/auth/verification/status')
def verification_status():
    configured()
    user = auth.current()
    return {**state(user['id']), 'email': user['email']}


@router.post('/auth/verification/resend', status_code=202)
def resend():
    configured()
    user = auth.current()
    auth.throttle(str(user['id']), 'identity-resend')
    with connect() as conn:
        lock(conn)
        row = conn.execute('SELECT email,verified_at FROM socialmei.auth_email_activation WHERE user_id=%s FOR UPDATE', (user['id'],)).fetchone()
        if row and (row[1] is None or row[0] != user['email']):
            recent = conn.execute("SELECT 1 FROM socialmei.auth_identity_mail WHERE user_id=%s AND purpose='verification' AND created_at>NOW()-INTERVAL '60 seconds' LIMIT 1", (user['id'],)).fetchone()
            if recent:
                raise HTTPException(429, 'Aguarde um minuto antes de solicitar outro e-mail.')
            conn.execute('UPDATE socialmei.auth_email_activation SET email=%s,verified_at=NULL WHERE user_id=%s', (user['email'], user['id']))
            enqueue(conn, 'verification', user['email'], user_id=user['id'])
    return {'message': 'Confira seu e-mail e o spam. O envio pode levar alguns minutos.'}


@router.post('/auth/verification/email', status_code=202)
def correct_email(payload: EmailCorrection):
    configured()
    user = auth.current()
    auth.throttle(str(user['id']), 'identity-email')
    try:
        with connect() as conn:
            lock(conn)
            row = conn.execute('SELECT verified_at IS NOT NULL AND email=%s FROM socialmei.auth_email_activation WHERE user_id=%s FOR UPDATE', (user['email'], user['id'])).fetchone()
            credential = conn.execute('SELECT senha_hash FROM socialmei.auth_credenciais WHERE user_id=%s AND ativo FOR UPDATE', (user['id'],)).fetchone()
            if not row or row[0] or not credential or not auth.verify_password(payload.atual, credential[0]):
                raise HTTPException(400, 'Não foi possível corrigir o e-mail. Confira a senha e a situação da conta.')
            conn.execute('UPDATE socialmei.users SET email=%s WHERE id=%s', (payload.email, user['id']))
            conn.execute('UPDATE socialmei.auth_email_activation SET email=%s,verified_at=NULL WHERE user_id=%s', (payload.email, user['id']))
            enqueue(conn, 'verification', payload.email, user_id=user['id'])
            audit(conn, user['id'], 'email_corrigido')
    except psycopg.errors.UniqueViolation:
        raise HTTPException(400, 'Não foi possível utilizar esse e-mail. Confira os dados ou entre na conta existente.') from None
    return {'message': 'E-mail atualizado. Confira o novo endereço.'}


def valid_job(conn, token, purpose):
    conn.row_factory = dict_row
    row = conn.execute("SELECT * FROM socialmei.auth_identity_mail WHERE token_hash=%s AND purpose=%s AND expires_at>NOW() AND (status='sent' OR (status='processing' AND started_at>NOW()-INTERVAL '2 minutes')) FOR UPDATE", (auth.digest(token), purpose)).fetchone()
    if not row:
        raise HTTPException(400, 'Link inválido, expirado ou já utilizado. Solicite outro.')
    return row


@router.post('/auth/verification/confirm')
def verify(payload: Code, request: Request):
    configured()
    # Capabilities have per-token limits; a shared gateway must not merge recipients.
    auth.throttle(auth.digest(payload.token), 'identity-confirm')
    with connect() as conn:
        lock(conn)
        job = valid_job(conn, payload.token, 'verification')
        updated = conn.execute('UPDATE socialmei.auth_email_activation a SET verified_at=NOW() FROM socialmei.users u,socialmei.auth_credenciais c WHERE a.user_id=%s AND a.user_id=u.id AND c.user_id=u.id AND c.ativo AND a.email=u.email AND a.email=%s AND a.verified_at IS NULL RETURNING a.user_id', (job['user_id'], job['email'])).fetchone()
        if not updated:
            raise HTTPException(400, 'Link inválido ou conta alterada. Solicite outro.')
        conn.execute("UPDATE socialmei.auth_identity_mail SET status='used',finished_at=NOW() WHERE id=%s", (job['id'],))
        audit(conn, job['user_id'], 'email_verificado')
    return {'verified': True}


@router.get('/team/invitations')
def invitations(request: Request):
    configured()
    actor = team_members.identity(request)
    with connect() as conn:
        conn.row_factory = dict_row
        return {'items': conn.execute("SELECT id,email,role,status,created_at,expires_at FROM socialmei.auth_identity_mail WHERE workspace_id=%s AND purpose='invitation' ORDER BY created_at DESC LIMIT 100", (actor['workspace_id'],)).fetchall()}


@router.post('/team/invitations', status_code=202)
def invite(payload: Invitation, request: Request):
    configured()
    actor = team_members.identity(request, write=True)
    auth.throttle(str(actor['id']), 'identity-invite')
    with connect() as conn:
        lock(conn)
        conn.row_factory = dict_row
        team_members.locked_scope(conn, actor, request)
        existing = conn.execute('SELECT 1 FROM socialmei.users u JOIN socialmei.workspace_members m ON m.user_id=u.id WHERE m.workspace_id=%s AND LOWER(BTRIM(u.email))=%s', (actor['workspace_id'], payload.email)).fetchone()
        if existing:
            raise HTTPException(409, 'Essa conta já integra este negócio. Gerencie o acesso existente.')
        pending = conn.execute("SELECT count(*) AS n FROM socialmei.auth_identity_mail WHERE workspace_id=%s AND purpose='invitation' AND status IN ('pending','processing','sent') AND expires_at>NOW()", (actor['workspace_id'],)).fetchone()['n']
        if pending >= 50:
            raise HTTPException(429, 'Limite de convites pendentes atingido.')
        job = enqueue(conn, 'invitation', payload.email, workspace=actor['workspace_id'], actor=actor['id'], role=payload.role)
        audit(conn, actor['id'], 'convite_criado', actor['workspace_id'])
    return {'id': str(job), 'queued': True}


@router.delete('/team/invitations/{job_id}', status_code=204)
def revoke_invitation(job_id: UUID, request: Request):
    configured()
    actor = team_members.identity(request, write=True)
    with connect() as conn:
        lock(conn)
        conn.row_factory = dict_row
        team_members.locked_scope(conn, actor, request)
        conn.execute("UPDATE socialmei.auth_identity_mail SET status='revoked',token_hash=NULL,finished_at=NOW() WHERE id=%s AND workspace_id=%s AND purpose='invitation' AND status IN ('pending','processing','sent')", (job_id, actor['workspace_id']))
        audit(conn, actor['id'], 'convite_revogado', actor['workspace_id'])


@router.delete('/team/invitations/{job_id}/access', status_code=204)
def revoke_invited_access(job_id: UUID, payload: AccessRevoke, request: Request):
    configured()
    actor = team_members.identity(request, write=True)
    with connect() as conn:
        lock(conn)
        conn.row_factory = dict_row
        team_members.locked_scope(conn, actor, request)
        job = conn.execute("SELECT user_id,role FROM socialmei.auth_identity_mail WHERE id=%s AND workspace_id=%s AND purpose='invitation' AND status='used' FOR UPDATE", (job_id, actor['workspace_id'])).fetchone()
        if not job or not job['user_id'] or job['user_id'] == actor['id']:
            raise HTTPException(409, 'O acesso mudou. Atualize a equipe antes de continuar.')
        member = conn.execute('SELECT role FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s FOR UPDATE', (actor['workspace_id'], job['user_id'])).fetchone()
        if not member or member['role'] != job['role'] or member['role'] != payload.expected_role:
            raise HTTPException(409, 'O papel foi alterado. Confira o acesso atual com o proprietário.')
        conn.execute('DELETE FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s', (actor['workspace_id'], job['user_id']))
        conn.execute("UPDATE socialmei.auth_identity_mail SET status='revoked',token_hash=NULL,finished_at=NOW() WHERE id=%s", (job_id,))
        audit(conn, actor['id'], 'acesso_revogado', actor['workspace_id'])


@router.post('/auth/invitations/inspect')
def inspect_invitation(payload: Code, request: Request):
    configured()
    auth.throttle(auth.digest(payload.token), 'invite-inspect')
    with connect() as conn:
        lock(conn)
        job = valid_job(conn, payload.token, 'invitation')
        name = conn.execute('SELECT nome FROM socialmei.workspaces WHERE id=%s', (job['workspace_id'],)).fetchone()['nome']
        return {'business_name': name, 'role': job['role'], 'email_hint': job['email'][:1] + '***@' + job['email'].split('@')[-1]}


@router.post('/auth/invitations/accept')
def accept(payload: Acceptance, request: Request):
    configured()
    auth.throttle(auth.digest(payload.token), 'invite-accept')
    hashed = auth.hash_password(payload.senha) if payload.senha is not None else None
    try:
        with connect() as conn:
            lock(conn)
            job = valid_job(conn, payload.token, 'invitation')
            if job['email'] != payload.email:
                raise HTTPException(400, 'Confira o e-mail que recebeu o convite.')
            conn.execute('SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE', (job['workspace_id'],))
            creator = conn.execute("SELECT 1 FROM socialmei.workspace_members m JOIN socialmei.auth_credenciais c ON c.user_id=m.user_id WHERE m.workspace_id=%s AND m.user_id=%s AND m.role='owner' AND c.ativo FOR SHARE OF m,c", (job['workspace_id'], job['created_by'])).fetchone()
            if not creator:
                raise HTTPException(409, 'O convite precisa ser renovado pelo proprietário.')
            count = conn.execute('SELECT count(*) AS n FROM socialmei.workspace_members WHERE workspace_id=%s', (job['workspace_id'],)).fetchone()['n']
            if count >= 50:
                raise HTTPException(429, 'A equipe atingiu o limite de integrantes.')
            if job['role'] == 'report_viewer':
                team_members.viewer_capacity(conn, job['workspace_id'])
            target = conn.execute('SELECT u.id,c.ativo FROM socialmei.users u JOIN socialmei.auth_credenciais c ON c.user_id=u.id WHERE LOWER(BTRIM(u.email))=%s FOR UPDATE OF u,c', (payload.email,)).fetchone()
            if target:
                session = conn.execute('SELECT user_id FROM socialmei.auth_sessoes WHERE token_hash=%s AND user_id=%s AND revogada_em IS NULL AND expira_em>NOW() FOR SHARE',
                                       (auth.digest(request.cookies.get(auth.COOKIE, '')), target['id'])).fetchone()
                if not target['ativo'] or not session:
                    raise HTTPException(409, 'Entre na conta que recebeu o convite antes de aceitá-lo.')
                if payload.senha is not None or request.headers.get('x-socialmei-csrf') != auth.csrf(request.cookies.get(auth.COOKIE, '')):
                    raise HTTPException(403, 'Confira a sessão da conta convidada.')
                user_id = target['id']
            else:
                if not hashed or not payload.nome or not payload.nome.strip() or any(ord(c) < 32 for c in payload.nome):
                    raise HTTPException(422, 'Informe seu nome e uma senha segura para criar a conta.')
                user_id = conn.execute('INSERT INTO socialmei.users(email,nome) VALUES(%s,%s) RETURNING id', (payload.email, payload.nome.strip())).fetchone()['id']
                conn.execute('INSERT INTO socialmei.auth_credenciais(user_id,senha_hash) VALUES(%s,%s)', (user_id, hashed))
            if conn.execute('SELECT 1 FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s', (job['workspace_id'], user_id)).fetchone():
                raise HTTPException(409, 'Essa conta já possui acesso. O convite não altera permissões existentes.')
            conn.execute('INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,%s)', (job['workspace_id'], user_id, job['role']))
            conn.execute('INSERT INTO socialmei.auth_email_activation(user_id,email,verified_at) VALUES(%s,%s,NOW()) ON CONFLICT(user_id) DO UPDATE SET email=EXCLUDED.email,verified_at=NOW()', (user_id, payload.email))
            conn.execute("UPDATE socialmei.auth_identity_mail SET status='used',user_id=%s,finished_at=NOW() WHERE id=%s", (user_id, job['id']))
            audit(conn, user_id, 'convite_aceito', job['workspace_id'])
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, 'A conta mudou durante o aceite. Entre na sua conta e confira o convite.') from None
    return {'accepted': True, 'message': 'Acesso confirmado. Entre na sua conta e selecione o negócio.'}


def send_mail(address, token, purpose, config):
    message = EmailMessage()
    message['From'], message['To'] = config['from'], address
    message['Subject'] = 'SocialMEI — ' + ('confirme seu e-mail' if purpose == 'verification' else 'convite para uma equipe')
    fragment = 'verificar' if purpose == 'verification' else 'convite'
    message.set_content('Abra o link para ' + ('verificar seu e-mail' if purpose == 'verification' else 'conferir e aceitar o convite') + ':\n' +
        auth.origin() + '/frontend/ativar.html#' + fragment + '/' + token + '\n\nVálido por 30 minutos, uma única vez. Se não solicitou, ignore. Não compartilhe este link.')
    context = ssl.create_default_context()
    server = smtplib.SMTP_SSL(config['host'], 465, timeout=10, context=context) if config['port'] == 465 else smtplib.SMTP(config['host'], 587, timeout=10)
    with server:
        if config['port'] == 587:
            server.starttls(context=context)
        server.login(config['user'], config['password'])
        server.send_message(message)


def process_one():
    config = configured()
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        lock(conn)
        conn.row_factory = dict_row
        conn.execute("UPDATE socialmei.auth_identity_mail SET status='uncertain',token_hash=NULL,finished_at=NOW() WHERE status='processing' AND started_at<NOW()-INTERVAL '2 minutes'")
        conn.execute("UPDATE socialmei.auth_identity_mail SET status='expired',token_hash=NULL,finished_at=NOW() WHERE status IN ('pending','sent') AND expires_at<=NOW()")
        job = conn.execute("SELECT * FROM socialmei.auth_identity_mail WHERE status='pending' ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
        if not job:
            return False
        if job['purpose'] == 'verification':
            valid = conn.execute('SELECT 1 FROM socialmei.auth_email_activation a JOIN socialmei.users u ON u.id=a.user_id JOIN socialmei.auth_credenciais c ON c.user_id=u.id WHERE a.user_id=%s AND a.email=%s AND u.email=a.email AND a.verified_at IS NULL AND c.ativo', (job['user_id'], job['email'])).fetchone()
            if not valid:
                conn.execute("UPDATE socialmei.auth_identity_mail SET status='revoked',finished_at=NOW() WHERE id=%s", (job['id'],))
                return True
        elif not conn.execute("SELECT 1 FROM socialmei.workspace_members m JOIN socialmei.auth_credenciais c ON c.user_id=m.user_id WHERE m.workspace_id=%s AND m.user_id=%s AND m.role='owner' AND c.ativo", (job['workspace_id'], job['created_by'])).fetchone():
            conn.execute("UPDATE socialmei.auth_identity_mail SET status='revoked',finished_at=NOW() WHERE id=%s", (job['id'],))
            return True
        conn.execute("UPDATE socialmei.auth_identity_mail SET status='processing',token_hash=%s,started_at=NOW(),expires_at=NOW()+INTERVAL '30 minutes' WHERE id=%s", (auth.digest(token), job['id']))
    status = 'sent'
    try:
        send_mail(job['email'], token, job['purpose'], config)
    except Exception:
        status = 'uncertain'
    with connect() as conn:
        conn.execute("UPDATE socialmei.auth_identity_mail SET status=%s,token_hash=CASE WHEN %s='uncertain' THEN NULL ELSE token_hash END,finished_at=NOW() WHERE id=%s AND token_hash=%s AND status='processing'", (status, status, job['id'], auth.digest(token)))
    return True
