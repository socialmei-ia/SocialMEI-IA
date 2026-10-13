import os
from urllib.parse import quote

import psycopg


def shared_data_enabled() -> bool:
    return os.getenv("SOCIALMEI_SHARED_DATA_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def database_url() -> str:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    host = os.getenv("POSTGRES_HOST", "").strip()
    user = os.getenv("POSTGRES_USER", "").strip()
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DB", "").strip()
    port = os.getenv("POSTGRES_PORT", "5432").strip() or "5432"

    if not all([host, user, database]):
        raise RuntimeError("PostgreSQL não configurado para a API compartilhada.")

    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}"
    )


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
        cur.execute(
            "SELECT id, slug, nome, atualizado_em FROM socialmei.workspaces LIMIT 0"
        )
        # Falha também quando o banco responde, mas a migration do CRM falta.
        cur.execute(
            "SELECT id, versao, cidade, desde, categoria, cadastro_original_em, "
            "observacao_atualizada_em, avatar_url, foto, ultima, total, pendente "
            "FROM socialmei.crm_clientes LIMIT 0"
        )
        cur.execute(
            "SELECT workspace_id, origem, local_id, cliente_id, fingerprint, snapshot "
            "FROM socialmei.crm_cliente_importacoes LIMIT 0"
        )
        cur.execute(
            "SELECT id, nome, tipo, preco, custo, estoque, minimo, status, versao, criado_em, atualizado_em "
            "FROM socialmei.crm_produtos LIMIT 0"
        )
        cur.execute(
            "SELECT workspace_id, origem, local_id, produto_id, fingerprint, snapshot "
            "FROM socialmei.crm_produto_importacoes LIMIT 0"
        )
        cur.execute(
            "SELECT id, cliente_id, produto_id, quantidade, preco, valor, estoque_aplicado, importada, excluida, versao FROM socialmei.crm_vendas LIMIT 0"
        )
        cur.execute(
            "SELECT workspace_id, operation_id, fingerprint, resposta FROM socialmei.crm_venda_operacoes LIMIT 0"
        )
        cur.execute(
            "SELECT workspace_id, origem, local_id, venda_id, fingerprint, snapshot FROM socialmei.crm_venda_importacoes LIMIT 0"
        )
        cur.execute(
            "SELECT id, cliente_id, descricao, tipo, valor, vencimento, status, data_pagamento, excluida, versao FROM socialmei.crm_financeiro LIMIT 0"
        )
        cur.execute(
            "SELECT workspace_id, operation_id, fingerprint, resposta FROM socialmei.crm_financeiro_operacoes LIMIT 0"
        )
        cur.execute(
            "SELECT workspace_id, origem, local_id, lancamento_id, fingerprint, snapshot FROM socialmei.crm_financeiro_importacoes LIMIT 0"
        )
        cur.execute(
            "SELECT workspace_id, origem, fingerprint, snapshot, resposta FROM socialmei.crm_transferencias LIMIT 0"
        )
        if include_auth:
            for query in (
                "SELECT id, nome, email, telefone FROM socialmei.users LIMIT 0",
                "SELECT id, slug, nome, configuracao FROM socialmei.workspaces LIMIT 0",
                "SELECT workspace_id, user_id, role FROM socialmei.workspace_members LIMIT 0",
                "SELECT user_id, senha_hash, ativo, administrador_plataforma, senha_alterada_em FROM socialmei.auth_credenciais LIMIT 0",
                "SELECT token_hash, user_id, workspace_id, criada_em, expira_em, revogada_em FROM socialmei.auth_sessoes LIMIT 0",
                "SELECT token_hash, email, criado_por, criado_em, expira_em, usado_em, revogado_em, user_id FROM socialmei.auth_convites LIMIT 0",
                "SELECT chave, inicio, tentativas FROM socialmei.auth_limites LIMIT 0",
                "SELECT id, user_id, alvo_user_id, acao, criado_em FROM socialmei.auth_auditoria LIMIT 0",
            ):
                cur.execute(query)

        if CHANNEL_MIGRATION not in installed:
            return "unavailable"
        try:
            # Canal é capacidade separada: sua ausência não torna o CRM indisponível.
            with conn.transaction():
                for query in (
                    "SELECT id, workspace_id, canal, provedor, instancia, sessao, ativo, envio_habilitado, versao FROM socialmei.crm_canais LIMIT 0",
                    "SELECT id, workspace_id, canal_id, identificador_externo, cliente_id, status, nao_lidas, versao FROM socialmei.crm_conversas_canal LIMIT 0",
                    "SELECT id, workspace_id, canal_id, conversa_id, identificador_externo, operation_id, direcao, conteudo, status FROM socialmei.crm_mensagens_canal LIMIT 0",
                    "SELECT id, workspace_id, canal_id, chave_evento, tipo, fingerprint, mensagem_externa_id, mensagem_id, status FROM socialmei.crm_eventos_canal LIMIT 0",
                ):
                    cur.execute(query)
        except (
            psycopg.errors.UndefinedTable,
            psycopg.errors.UndefinedColumn,
            psycopg.errors.InsufficientPrivilege,
        ):
            return "unavailable"
        return "prepared"
