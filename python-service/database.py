from hashlib import sha256
from threading import Lock
from time import monotonic

import psycopg

from settings import database_readiness_cache_seconds, database_url, shared_data_enabled


_readiness_lock = Lock()
_readiness_cache = None


def connect():
    return psycopg.connect(database_url())


CRM_MIGRATIONS = {
    "001_initial_socialmei_schema.sql",
    "002_shared_crm_foundation.sql",
    "003_client_contract.sql",
    "004_client_import.sql",
    "005_shared_catalog.sql",
    "006_shared_sales.sql",
    "007_shared_finance.sql",
    "008_workspace_transfer.sql",
}
AUTH_MIGRATION = "010_account_authentication.sql"
CHANNEL_MIGRATION = "009_shared_channel_foundation.sql"


CRM_SCHEMA_QUERIES = (
    "SELECT id, slug, nome, atualizado_em FROM socialmei.workspaces LIMIT 0",
    (
        "SELECT id, versao, cidade, desde, categoria, cadastro_original_em, "
        "observacao_atualizada_em, avatar_url, foto, ultima, total, pendente FROM "
        "socialmei.crm_clientes LIMIT 0"
    ),
    (
        "SELECT workspace_id, origem, local_id, cliente_id, fingerprint, snapshot FROM "
        "socialmei.crm_cliente_importacoes LIMIT 0"
    ),
    (
        "SELECT id, nome, categoria, descricao, tipo, preco, custo, estoque, minimo, status, versao, criado_em, "
        "atualizado_em FROM socialmei.crm_produtos LIMIT 0"
    ),
    (
        "SELECT workspace_id, origem, local_id, produto_id, fingerprint, snapshot FROM "
        "socialmei.crm_produto_importacoes LIMIT 0"
    ),
    (
        "SELECT id, cliente_id, produto_id, quantidade, preco, valor, estoque_aplicado, "
        "importada, excluida, versao FROM socialmei.crm_vendas LIMIT 0"
    ),
    (
        "SELECT workspace_id, operation_id, fingerprint, resposta FROM "
        "socialmei.crm_venda_operacoes LIMIT 0"
    ),
    (
        "SELECT workspace_id, origem, local_id, venda_id, fingerprint, snapshot FROM "
        "socialmei.crm_venda_importacoes LIMIT 0"
    ),
    (
        "SELECT id, cliente_id, descricao, tipo, valor, vencimento, status, data_pagamento,"
        " excluida, versao FROM socialmei.crm_financeiro LIMIT 0"
    ),
    (
        "SELECT workspace_id, operation_id, fingerprint, resposta FROM "
        "socialmei.crm_financeiro_operacoes LIMIT 0"
    ),
    (
        "SELECT workspace_id, origem, local_id, lancamento_id, fingerprint, snapshot FROM "
        "socialmei.crm_financeiro_importacoes LIMIT 0"
    ),
    (
        "SELECT workspace_id, origem, fingerprint, snapshot, resposta FROM "
        "socialmei.crm_transferencias LIMIT 0"
    ),
)

AUTH_SCHEMA_QUERIES = (
    "SELECT id, nome, email, telefone FROM socialmei.users LIMIT 0",
    "SELECT id, slug, nome, configuracao FROM socialmei.workspaces LIMIT 0",
    "SELECT workspace_id, user_id, role FROM socialmei.workspace_members LIMIT 0",
    (
        "SELECT user_id, senha_hash, ativo, administrador_plataforma, senha_alterada_em "
        "FROM socialmei.auth_credenciais LIMIT 0"
    ),
    (
        "SELECT token_hash, user_id, workspace_id, criada_em, expira_em, revogada_em FROM "
        "socialmei.auth_sessoes LIMIT 0"
    ),
    (
        "SELECT token_hash, email, criado_por, criado_em, expira_em, usado_em, revogado_em,"
        " user_id FROM socialmei.auth_convites LIMIT 0"
    ),
    "SELECT chave, inicio, tentativas FROM socialmei.auth_limites LIMIT 0",
    (
        "SELECT id, user_id, alvo_user_id, acao, criado_em FROM socialmei.auth_auditoria "
        "LIMIT 0"
    ),
)

CHANNEL_SCHEMA_QUERIES = (
    (
        "SELECT id, workspace_id, canal, provedor, instancia, sessao, ativo, "
        "envio_habilitado, versao FROM socialmei.crm_canais LIMIT 0"
    ),
    (
        "SELECT id, workspace_id, canal_id, identificador_externo, cliente_id, status, "
        "nao_lidas, versao FROM socialmei.crm_conversas_canal LIMIT 0"
    ),
    (
        "SELECT id, workspace_id, canal_id, conversa_id, identificador_externo, "
        "operation_id, direcao, conteudo, status FROM socialmei.crm_mensagens_canal LIMIT 0"
    ),
    (
        "SELECT id, workspace_id, canal_id, chave_evento, tipo, fingerprint, "
        "mensagem_externa_id, mensagem_id, status FROM socialmei.crm_eventos_canal LIMIT 0"
    ),
)


def check_database_readiness(*, include_auth: bool = False) -> str:
    global _readiness_cache
    seconds = database_readiness_cache_seconds()
    if not seconds:
        with _readiness_lock:
            _readiness_cache = None
        return check_database(include_auth=include_auth)

    # Only readiness metadata is cached; never a DSN, exception or business data.
    identity = (sha256(database_url().encode()).digest(), include_auth, seconds)
    with _readiness_lock:
        state = _readiness_cache
        if state is None or state["identity"] != identity:
            state = {"identity": identity, "checked_at": None, "schema": None,
                     "structural_failure": False, "failed": False, "next_schema_at": 0}
            _readiness_cache = state
        if state["checked_at"] is None or monotonic() - state["checked_at"] >= seconds:
            try:
                _check_database_availability()
            except Exception:
                state["failed"] = True
            else:
                if state["schema"] is None and not state["structural_failure"]:
                    state["failed"] = True
                    if monotonic() >= state["next_schema_at"]:
                        try:
                            state["schema"] = check_database(include_auth=include_auth)
                            state["failed"] = False
                        except Exception as error:
                            # A partial deep failure must not rescan the schema every five minutes.
                            state["next_schema_at"] = monotonic() + 6 * 3600
                            state["structural_failure"] = (
                                isinstance(error, (psycopg.errors.UndefinedTable,
                                                   psycopg.errors.UndefinedColumn,
                                                   psycopg.errors.InsufficientPrivilege))
                                or isinstance(error, RuntimeError) and str(error) in {
                                    "Migrations do CRM incompletas.", "Migration de contas ausente.",
                                }
                            )
                else:
                    state["failed"] = state["structural_failure"]
            state["checked_at"] = monotonic()
        if state["failed"]:
            raise RuntimeError("Database readiness unavailable.") from None
        return state["schema"]


def _check_database_availability() -> None:
    url = database_url()
    options = psycopg.conninfo.conninfo_to_dict(url).get("options", "")
    options += " -c default_transaction_read_only=on -c statement_timeout=5000"
    with psycopg.connect(url, autocommit=True, connect_timeout=5, options=options) as conn:
        conn.execute("SELECT 1")


def check_database(*, include_auth: bool = False) -> str:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.execute("SELECT version FROM socialmei.schema_migrations")
        installed = {row[0] for row in cur.fetchall()}
        if not CRM_MIGRATIONS.issubset(installed):
            raise RuntimeError("Migrations do CRM incompletas.")
        if include_auth and AUTH_MIGRATION not in installed:
            raise RuntimeError("Migration de contas ausente.")
        for query in CRM_SCHEMA_QUERIES:
            cur.execute(query)
        if include_auth:
            for query in AUTH_SCHEMA_QUERIES:
                cur.execute(query)

        if CHANNEL_MIGRATION not in installed:
            return "unavailable"
        try:
            # Canal é capacidade separada: sua ausência não torna o CRM indisponível.
            with conn.transaction():
                for query in CHANNEL_SCHEMA_QUERIES:
                    cur.execute(query)
        except (
            psycopg.errors.UndefinedTable,
            psycopg.errors.UndefinedColumn,
            psycopg.errors.InsufficientPrivilege,
        ):
            return "unavailable"
        return "prepared"
