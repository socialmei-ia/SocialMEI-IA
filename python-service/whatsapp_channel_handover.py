"""Private channel lifecycle. No public routes, provider calls or runtime changes.

The operator must pause ingress/responders and issue a fresh scoped attestation.
This database transaction cannot itself stop Docker, WAHA or n8n processes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from database import connect
from workspace_access import digest, require, _save_receipt


@dataclass(frozen=True)
class Handover:
    actor_id: int
    target_owner_id: int
    source_workspace_id: int
    source_channel_id: int
    target_workspace_id: int
    expected_revision: int
    expected_instance: str
    expected_session: str
    expected_account: str
    reviewed_draft_ids: tuple[str, ...] = ()
    require_replies: bool = True

    def __post_init__(self):
        for value in (self.actor_id, self.target_owner_id, self.source_workspace_id,
                      self.source_channel_id, self.target_workspace_id, self.expected_revision):
            require(type(value) is int and 0 < value <= 9007199254740991, 'INVALID_HANDOVER_ID')
        require(self.source_workspace_id != self.target_workspace_id, 'SAME_WORKSPACE')
        require(type(self.require_replies) is bool, 'INVALID_REPLY_REQUIREMENT')
        require(all(isinstance(v, str) and v and len(v) <= 255 for v in
                    (self.expected_instance, self.expected_session, self.expected_account)), 'INVALID_BINDING')
        require(not self.expected_instance.startswith('fixture-') and not self.expected_session.startswith('fixture-'),
                'FIXTURE_CHANNEL_NOT_TRANSFERABLE')
        require(len(self.reviewed_draft_ids) == len(set(self.reviewed_draft_ids)) <= 100, 'INVALID_REVIEWED_DRAFTS')
        object.__setattr__(self, 'reviewed_draft_ids', tuple(sorted(str(UUID(v)) for v in self.reviewed_draft_ids)))


def now():
    return datetime.now(timezone.utc)


def paused(request, proof):
    # This is a private operator attestation, not an externally callable bypass.
    require(isinstance(proof, dict) and proof.get('scope_sha256') == digest(request.__dict__)
            and proof.get('ingress_paused') is True and proof.get('responders_paused') is True,
            'SCOPED_RUNTIME_PAUSE_REQUIRED')
    try:
        expires = datetime.fromisoformat(proof['expires_at'])
        require(now() < expires <= now() + timedelta(seconds=90), 'RUNTIME_PAUSE_EXPIRED')
    except (KeyError, TypeError, ValueError):
        require(False, 'INVALID_RUNTIME_PAUSE')


def setup(conn, request, *, lock, target_owner_required=True):
    conn.row_factory = dict_row
    conn.execute("SET LOCAL lock_timeout='5s'")
    conn.execute("SET LOCAL statement_timeout='10s'")
    require(conn.execute("SELECT to_regclass('socialmei.wa_channel_handovers') AS t").fetchone()['t'],
            'MIGRATION_041_REQUIRED')
    if lock:
        # Same account lock and order used by signed WAHA ingress.
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                     ('waha-ingress:' + request.expected_account,))
        conn.execute('SELECT id FROM socialmei.workspaces WHERE id=ANY(%s) ORDER BY id FOR UPDATE',
                     ([request.source_workspace_id, request.target_workspace_id],)).fetchall()
    admin = conn.execute('SELECT ativo,administrador_plataforma FROM socialmei.auth_credenciais WHERE user_id=%s'
                         + (' FOR SHARE' if lock else ''), (request.actor_id,)).fetchone()
    require(admin and admin['ativo'] and admin['administrador_plataforma'], 'ACTIVE_PLATFORM_ADMIN_REQUIRED')
    owner = conn.execute("SELECT m.role,c.ativo FROM socialmei.workspace_members m JOIN socialmei.auth_credenciais c "
                         "ON c.user_id=m.user_id WHERE m.workspace_id=%s AND m.user_id=%s"
                         + (' FOR SHARE OF m,c' if lock else ''),
                         (request.target_workspace_id, request.target_owner_id)).fetchone()
    if target_owner_required:
        require(owner and owner['ativo'] and owner['role'] == 'owner', 'ACTIVE_TARGET_OWNER_REQUIRED')


def physical_identity(request, row):
    require((row['provedor'],row['instancia'],row['sessao'],row['identificador_conta']) ==
            ('waha',request.expected_instance,request.expected_session,request.expected_account),
            'CHANNEL_PHYSICAL_IDENTITY_CHANGED')


def channel(conn, workspace, cid, *, lock=False):
    row = conn.execute('SELECT * FROM socialmei.crm_canais WHERE workspace_id=%s AND id=%s'
                       + (' FOR UPDATE' if lock else ''), (workspace, cid)).fetchone()
    require(row, 'CHANNEL_MISSING')
    return row


def queues(conn, workspace, cid, reviewed):
    bot = conn.execute("SELECT count(*) AS n FROM socialmei.wa_bot_decisions WHERE workspace_id=%s "
                       "AND channel_id=%s AND status NOT IN ('confirmed','skipped')", (workspace, cid)).fetchone()['n']
    human = conn.execute('SELECT id,status,fingerprint FROM socialmei.wa_human_replies '
                         'WHERE workspace_id=%s AND channel_id=%s ORDER BY id', (workspace, cid)).fetchall()
    require(bot == 0 and not any(r['status'] in {'dispatching','uncertain'} for r in human), 'UNRECONCILED_SENDS')
    drafts = [r for r in human if r['status'] == 'draft']
    require(sorted(str(r['id']) for r in drafts) == sorted(reviewed), 'HUMAN_DRAFT_REVIEW_REQUIRED')
    return drafts


def scope(conn, request, *, lock):
    setup(conn, request, lock=lock)
    source = channel(conn, request.source_workspace_id, request.source_channel_id, lock=lock)
    require(source['provedor'] == 'waha' and source['ativo'] and source['ingress_provisioned']
            and not source['envio_habilitado'] and source['retired_at'] is None, 'SOURCE_NOT_TRANSFERABLE')
    require((source['versao'],source['instancia'],source['sessao'],source['identificador_conta']) ==
            (request.expected_revision,request.expected_instance,request.expected_session,request.expected_account),
            'SOURCE_BINDING_CHANGED')
    drafts = queues(conn, request.source_workspace_id, request.source_channel_id, request.reviewed_draft_ids)
    conflict = conn.execute("SELECT id FROM socialmei.crm_canais WHERE retired_at IS NULL AND "
                            "workspace_id=%s AND provedor='waha' AND instancia=%s AND sessao=%s",
                            (request.target_workspace_id,request.expected_instance,request.expected_session)).fetchone()
    require(not conflict, 'TARGET_ALREADY_RESERVED')
    return source, drafts


def plan_for(request, source, drafts):
    return {'operation':'retire_and_reserve','source_workspace_id':request.source_workspace_id,
            'source_channel_id':request.source_channel_id,'target_workspace_id':request.target_workspace_id,
            'target_owner_id':request.target_owner_id,'reviewed_drafts':len(drafts),
            'require_replies':request.require_replies,
            'plan_sha256':digest([request.__dict__,source,drafts]),'external_effects':False}


def inspect_handover(request):
    with connect() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        source, drafts = scope(conn, request, lock=False)
        return plan_for(request, source, drafts)


def stored(conn, operation_id, request):
    row = conn.execute('SELECT * FROM socialmei.wa_channel_handovers WHERE id=%s FOR UPDATE',
                       (UUID(str(operation_id)),)).fetchone()
    if row:
        require(row['fingerprint'] == digest(request.__dict__), 'OPERATION_ID_REUSED')
    return row


def receipt(row):
    return {key: str(row[key]) if key in {'id','ingress_after'} else row[key] for key in
            ('id','source_workspace_id','source_channel_id','target_workspace_id','target_channel_id',
             'ingress_after','status')}


def reserve(request, approved_plan, operation_id, pause_proof, *, receipt_path):
    paused(request, pause_proof)
    require(receipt_path is not None, 'DURABLE_PRIVATE_RECEIPT_REQUIRED')
    with connect() as conn:
        setup(conn, request, lock=True)
        previous = stored(conn, operation_id, request)
        if previous:
            require(previous['status'] != 'rolled_back', 'HANDOVER_ALREADY_ROLLED_BACK')
            _save_receipt(receipt_path, receipt(previous))
            return receipt(previous)
        source, drafts = scope(conn, request, lock=True)
        require(plan_for(request, source, drafts)['plan_sha256'] == approved_plan, 'APPROVED_BASELINE_CHANGED')
        conn.execute('UPDATE socialmei.crm_canais SET ativo=false,ingress_provisioned=false,retired_at=NOW(),'
                     'versao=versao+1,atualizado_em=NOW() WHERE id=%s', (source['id'],))
        target = conn.execute("INSERT INTO socialmei.crm_canais(workspace_id,provedor,instancia,sessao,nome,"
                              "identificador_conta) VALUES(%s,'waha',%s,%s,%s,%s) RETURNING id",
                              (request.target_workspace_id,request.expected_instance,request.expected_session,
                               source['nome'],request.expected_account)).fetchone()['id']
        row = conn.execute("INSERT INTO socialmei.wa_channel_handovers(id,actor_id,target_owner_id,source_workspace_id,"
                           "source_channel_id,target_workspace_id,target_channel_id,status,fingerprint,previous_channel,"
                           "reviewed_draft_ids,ingress_after) VALUES(%s,%s,%s,%s,%s,%s,%s,'reserved',%s,%s,%s,NOW()) RETURNING *",
                           (UUID(str(operation_id)),request.actor_id,request.target_owner_id,request.source_workspace_id,
                            source['id'],request.target_workspace_id,target,digest(request.__dict__),
                            Jsonb({k: str(v) if isinstance(v,datetime) else v for k,v in source.items()}),
                            Jsonb(list(request.reviewed_draft_ids)))).fetchone()
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,alvo_user_id,acao) VALUES(%s,%s,'wa_handover_reserved')",
                     (request.actor_id,request.target_owner_id))
        _save_receipt(receipt_path, receipt(row))
        return receipt(row)


def runtime_binding(row, target, request):
    from waha_ingress import waha_service
    import settings
    service = waha_service()
    matches = [b for b in service.registry.values() if b.account_id == target['identificador_conta']]
    require(len(matches) == 1, 'EXCLUSIVE_REGISTRY_BINDING_REQUIRED')
    b = matches[0]
    require((b.workspace_id,b.channel_id,b.instance,b.session,b.revision) ==
            (target['workspace_id'],target['id'],target['instancia'],target['sessao'],target['versao']+1)
            and b.ingress_after >= row['ingress_after'].timestamp() and b.engine == 'GOWS',
            'REGISTRY_OR_CUTOFF_MISMATCH')
    require(settings.waha_inbox_enabled(target['workspace_id']), 'TARGET_INGRESS_NOT_AUTHORIZED')
    if request.require_replies:
        import whatsapp_bot
        require(settings.waha_ingress_team_pilot_enabled() and settings.whatsapp_bot_public_inbound_enabled()
                and whatsapp_bot.enabled() and settings.waha_pilot_binding_allowed(
                    b.workspace_id,b.channel_id,b.instance,b.session,b.account_id,b.revision,b.engine),
                'TARGET_REPLY_AUTHORIZATION_NOT_READY')
        try:
            human=settings.whatsapp_human_configuration()
        except ValueError:
            human=None
        require(human is not None and (human.workspace_id,human.instance,human.session,human.account_id,human.engine)
                == (b.workspace_id,b.instance,b.session,b.account_id,b.engine), 'TARGET_HUMAN_SENDER_NOT_READY')
    return b


def activate(request, operation_id, pause_proof):
    paused(request, pause_proof)
    with connect() as conn:
        setup(conn, request, lock=True)
        row = stored(conn, operation_id, request)
        require(row and row['status'] == 'reserved', 'RESERVED_HANDOVER_REQUIRED')
        old = channel(conn, request.source_workspace_id, request.source_channel_id, lock=True)
        physical_identity(request,old)
        require(old['retired_at'] is not None and not old['ativo'] and old['versao']==request.expected_revision+1,
                'SOURCE_RETIREMENT_CHANGED')
        queues(conn,request.source_workspace_id,request.source_channel_id,request.reviewed_draft_ids)
        target = channel(conn,request.target_workspace_id,row['target_channel_id'],lock=True)
        physical_identity(request,target)
        require(not target['ativo'] and not target['ingress_provisioned'] and target['retired_at'] is None
                and not target['envio_habilitado'] and target['versao'] == 1, 'RESERVATION_CHANGED')
        runtime_binding(row,target,request)
        conn.execute('UPDATE socialmei.crm_canais SET ativo=true,ingress_provisioned=true,versao=versao+1,'
                     'atualizado_em=NOW() WHERE id=%s', (target['id'],))
        conn.execute("UPDATE socialmei.wa_channel_handovers SET status='active',activated_at=NOW() WHERE id=%s",(row['id'],))
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,alvo_user_id,acao) VALUES(%s,%s,'wa_handover_active')",
                     (request.actor_id,request.target_owner_id))
        return {'active':True,'workspace_id':target['workspace_id'],'channel_id':target['id'],
                'revision':2,'responders_started':False,'credentials_issued':False}


def rollback(request, operation_id, pause_proof):
    """Only before target traffic. Afterwards use a separately approved reverse handover."""
    paused(request,pause_proof)
    with connect() as conn:
        setup(conn,request,lock=True,target_owner_required=False)
        row = stored(conn,operation_id,request)
        require(row and row['status'] in {'reserved','active'}, 'REVERSIBLE_HANDOVER_REQUIRED')
        source = channel(conn,request.source_workspace_id,request.source_channel_id,lock=True)
        target = channel(conn,request.target_workspace_id,row['target_channel_id'],lock=True)
        physical_identity(request,source)
        physical_identity(request,target)
        traffic = conn.execute('SELECT EXISTS(SELECT 1 FROM socialmei.crm_eventos_canal WHERE workspace_id=%s '
                               'AND canal_id=%s) AS present',(target['workspace_id'],target['id'])).fetchone()['present']
        require(not traffic,'TARGET_TRAFFIC_REQUIRES_REVERSE_HANDOVER')
        queues(conn,target['workspace_id'],target['id'],())
        require(source['retired_at'] is not None and source['versao']==request.expected_revision+1
                and target['retired_at'] is None and not target['envio_habilitado']
                and target['versao'] in {1,2}, 'ROLLBACK_BASELINE_CHANGED')
        conn.execute('UPDATE socialmei.crm_canais SET ativo=false,ingress_provisioned=false,envio_habilitado=false,'
                     'retired_at=NOW(),versao=versao+1,atualizado_em=NOW() WHERE id=%s',(target['id'],))
        # Monotonic revisions keep every stale registry/worker fail-closed.
        conn.execute('UPDATE socialmei.crm_canais SET ativo=true,ingress_provisioned=true,retired_at=NULL,'
                     'versao=versao+1,atualizado_em=NOW() WHERE id=%s',(source['id'],))
        conn.execute("UPDATE socialmei.wa_channel_handovers SET status='rolled_back',rolled_back_at=NOW() WHERE id=%s",(row['id'],))
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,alvo_user_id,acao) VALUES(%s,%s,'wa_handover_rollback')",
                     (request.actor_id,request.target_owner_id))
        return {'rolled_back':True,'source_revision':request.expected_revision+2,
                'registry_and_worker_revalidation_required':True,'historical_rows_moved':0}
