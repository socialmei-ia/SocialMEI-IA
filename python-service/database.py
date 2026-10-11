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


def check_database() -> None:
    with connect() as conn, conn.cursor() as cur:
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
