"""Existing-account workspace team access; no identities, invitations or sends."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, field_validator
from psycopg.rows import dict_row

from account_auth import COOKIE, Strict, current, digest, normalize_email, require_enabled, throttle
from database import connect
from shared_data import MAX_SAFE_ID

router = APIRouter(prefix="/api/v1/team/members", tags=["workspace team"])
ManagedRole = Literal['member', 'report_viewer']


class Grant(Strict):
    email: str = Field(max_length=255)
    role: ManagedRole
    _email = field_validator('email')(normalize_email)


class RoleChange(Strict):
    role: ManagedRole
    expected_role: Literal['member', 'viewer', 'report_viewer']


class Revoke(Strict):
    expected_role: Literal['member', 'viewer', 'report_viewer']


def identity(request, *, write=False):
    require_enabled()
    actor = current()
    if actor['role'] not in ({'owner'} if write else {'owner', 'admin'}):
        raise HTTPException(403, 'Somente o proprietário pode gerenciar a equipe; administradores podem consultar.')
    if write and request.headers.get('x-socialmei-identity') != f"{actor['id']}:{actor['workspace_id']}":
        raise HTTPException(409, 'O negócio mudou. Atualize antes de alterar a equipe.')
    return actor


def locked_scope(conn, actor, request):
    conn.execute("SET LOCAL lock_timeout='5s'")
    conn.execute('SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE', (actor['workspace_id'],))
    credential = conn.execute('SELECT user_id FROM socialmei.auth_credenciais WHERE user_id=%s AND ativo FOR SHARE',
                              (actor['id'],)).fetchone()
    live = conn.execute(
        'SELECT m.role FROM socialmei.auth_sessoes s '
        'JOIN socialmei.workspace_members m ON m.workspace_id=s.workspace_id AND m.user_id=s.user_id '
        'WHERE s.token_hash=%s AND s.user_id=%s AND s.workspace_id=%s '
        'AND s.revogada_em IS NULL AND s.expira_em>NOW() '
        'FOR SHARE OF s,m',
        (digest(request.cookies.get(COOKIE, '')), actor['id'], actor['workspace_id']),
    ).fetchone()
    if not credential or not live:
        raise HTTPException(401, 'Sessão expirada. Entre novamente.')
    if live['role'] != 'owner':
        raise HTTPException(403, 'Somente o proprietário pode gerenciar a equipe.')


def audit(conn, actor, target, action):
    conn.execute(
        'INSERT INTO socialmei.auth_auditoria(user_id,alvo_user_id,acao) VALUES(%s,%s,%s)',
        (actor['id'], target, f"equipe:{actor['workspace_id']}:{action}"),
    )


def guarded_member(conn, actor, member_id, expected):
    if member_id == actor['id']:
        raise HTTPException(403, 'Você não pode alterar seu próprio acesso por esta tela.')
    member = conn.execute(
        'SELECT role FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s FOR UPDATE',
        (actor['workspace_id'], member_id),
    ).fetchone()
    if not member:
        raise HTTPException(404, 'Integrante não encontrado neste negócio.')
    if member['role'] in {'owner', 'admin'}:
        raise HTTPException(403, 'Proprietários e administradores não podem ser alterados por esta tela.')
    if member['role'] != expected:
        raise HTTPException(409, 'O acesso mudou. Atualize a equipe antes de continuar.')
    return member


def viewer_capacity(conn, workspace):
    count = conn.execute(
        "SELECT count(*) AS n FROM socialmei.workspace_members WHERE workspace_id=%s AND role='report_viewer'",
        (workspace,),
    ).fetchone()['n']
    if count >= 20:
        raise HTTPException(429, 'Limite de 20 visualizadores de relatórios por negócio.')


@router.get('')
def members(request: Request):
    actor = identity(request)
    with connect() as conn:
        conn.row_factory = dict_row
        records = conn.execute(
            'SELECT u.id,u.nome,u.email,m.role,c.ativo,m.criado_em '
            'FROM socialmei.workspace_members m JOIN socialmei.users u ON u.id=m.user_id '
            'JOIN socialmei.auth_credenciais c ON c.user_id=u.id '
            'WHERE m.workspace_id=%s ORDER BY m.criado_em,u.id LIMIT 51',
            (actor['workspace_id'],),
        ).fetchall()
    return {'items': records[:50], 'truncated': len(records) > 50,
            'can_manage': actor['role'] == 'owner', 'workspace_id': actor['workspace_id']}


@router.post('')
def grant(payload: Grant, request: Request):
    actor = identity(request, write=True)
    with connect() as conn:
        conn.row_factory = dict_row
        locked_scope(conn, actor, request)
        candidate = conn.execute(
            'SELECT u.id FROM socialmei.users u JOIN socialmei.auth_credenciais c ON c.user_id=u.id '
            'WHERE lower(btrim(u.email))=%s AND c.ativo FOR SHARE OF c', (payload.email,),
        ).fetchone()
        if not candidate:
            throttle(str(actor['id']), 'team-grant')
            raise HTTPException(409, 'Use uma conta SocialMEI já cadastrada e ativa. Nenhum convite será enviado.')
        target = candidate['id']
        if target == actor['id']:
            raise HTTPException(403, 'Você já é responsável por este negócio.')
        existing = conn.execute(
            'SELECT role FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s',
            (actor['workspace_id'], target),
        ).fetchone()
        if existing:
            if existing['role'] != payload.role:
                raise HTTPException(409, 'Essa conta já possui outro acesso. Atualize a equipe para conferir.')
            return {'granted': False, 'already_member': True}
        count = conn.execute('SELECT count(*) AS n FROM socialmei.workspace_members WHERE workspace_id=%s',
                             (actor['workspace_id'],)).fetchone()['n']
        if count >= 50:
            raise HTTPException(429, 'Limite de 50 integrantes por negócio.')
        if payload.role == 'report_viewer':
            viewer_capacity(conn, actor['workspace_id'])
        throttle(str(actor['id']), 'team-grant')
        conn.execute('INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,%s)',
                     (actor['workspace_id'], target, payload.role))
        audit(conn, actor, target, 'concedida')
    return {'granted': True, 'already_member': False}


@router.patch('/{member_id}')
def change(member_id: int, payload: RoleChange, request: Request):
    if not 1 <= member_id <= MAX_SAFE_ID:
        raise HTTPException(404, 'Integrante não encontrado neste negócio.')
    actor = identity(request, write=True)
    with connect() as conn:
        conn.row_factory = dict_row
        locked_scope(conn, actor, request)
        member = guarded_member(conn, actor, member_id, payload.expected_role)
        if member['role'] == payload.role:
            return {'changed': False}
        if payload.role == 'report_viewer':
            viewer_capacity(conn, actor['workspace_id'])
        conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE workspace_id=%s AND user_id=%s',
                     (payload.role, actor['workspace_id'], member_id))
        conn.execute('UPDATE socialmei.auth_sessoes SET revogada_em=NOW() '
                     'WHERE workspace_id=%s AND user_id=%s AND revogada_em IS NULL',
                     (actor['workspace_id'], member_id))
        audit(conn, actor, member_id, 'papel')
    return {'changed': True}


@router.delete('/{member_id}', status_code=204)
def revoke(member_id: int, payload: Revoke, request: Request):
    if not 1 <= member_id <= MAX_SAFE_ID:
        raise HTTPException(404, 'Integrante não encontrado neste negócio.')
    actor = identity(request, write=True)
    with connect() as conn:
        conn.row_factory = dict_row
        locked_scope(conn, actor, request)
        guarded_member(conn, actor, member_id, payload.expected_role)
        # The membership FK cascades only this workspace's sessions.
        conn.execute('DELETE FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s',
                     (actor['workspace_id'], member_id))
        audit(conn, actor, member_id, 'revogada')
