"""Exporta o PostgreSQL do notebook em uma única fotografia consistente."""

import json
import sys
from datetime import UTC, datetime
from uuid import UUID

import psycopg
from catalog_data import PRODUCT_COLUMNS
from finance_data import FINANCE_COLUMNS
from psycopg.rows import dict_row
from pydantic import ValidationError
from sales_data import SALE_COLUMNS
from shared_data import CLIENTE_COLUMNS, workspace_slug
from workspace_transfer import TransferPacket

from database import connect


def export_packet(origin):
    if workspace_slug() != "development":
        raise RuntimeError("Execute no ambiente de desenvolvimento do notebook.")
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cur.execute(
            "SELECT id FROM socialmei.workspaces WHERE slug = %s", (workspace_slug(),)
        )
        workspace = cur.fetchone()
        if not workspace:
            raise RuntimeError("Workspace de desenvolvimento não encontrado.")
        data = {}
        for name, columns in [
            ("clientes", CLIENTE_COLUMNS),
            ("produtos", PRODUCT_COLUMNS),
            ("vendas", SALE_COLUMNS),
            ("financeiro", FINANCE_COLUMNS),
        ]:
            cur.execute(
                f"SELECT {columns} FROM socialmei.crm_{name} WHERE workspace_id = %s ORDER BY id",
                (workspace["id"],),
            )
            data[name] = cur.fetchall()
        return TransferPacket(
            formato="socialmei-workspace-transfer",
            versao_formato=1,
            origem=UUID(str(origin)),
            workspace_origem="development",
            exportado_em=datetime.now(UTC),
            **data,
        )


if __name__ == "__main__":
    try:
        packet = export_packet(sys.argv[1])
        print(
            json.dumps(
                packet.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    except (psycopg.Error, RuntimeError, ValueError, IndexError, ValidationError):
        print(
            "Exportação não concluída. Confira o banco, o workspace development e os limites do pacote; nenhum dado foi alterado.",
            file=sys.stderr,
        )
        sys.exit(1)
