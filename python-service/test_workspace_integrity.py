"""Workspace links, tested only against an explicitly configured disposable database."""

import os
import unittest
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

DB = os.getenv("TEST_DATABASE_URL", "").strip()
ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "database/migrations/011_crm_workspace_links.sql"
LINKS = [
    ("crm_vendas", "cliente_id", "crm_clientes", "fk_crm_sales_workspace_customer"),
    ("crm_vendas", "produto_id", "crm_produtos", "fk_crm_sales_workspace_product"),
    (
        "crm_financeiro",
        "cliente_id",
        "crm_clientes",
        "fk_crm_finance_workspace_customer",
    ),
    (
        "crm_cliente_importacoes",
        "cliente_id",
        "crm_clientes",
        "fk_crm_customer_import_workspace",
    ),
    (
        "crm_produto_importacoes",
        "produto_id",
        "crm_produtos",
        "fk_crm_product_import_workspace",
    ),
    ("crm_venda_importacoes", "venda_id", "crm_vendas", "fk_crm_sale_import_workspace"),
    (
        "crm_financeiro_importacoes",
        "lancamento_id",
        "crm_financeiro",
        "fk_crm_finance_import_workspace",
    ),
]


@unittest.skipUnless(DB, "TEST_DATABASE_URL não configurado")
class WorkspaceIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DB) as conn:
            for path in sorted((ROOT / "database/migrations").glob("*.sql")):
                conn.execute(path.read_text(), prepare=False)

    def setUp(self):
        self.conn = psycopg.connect(DB)
        self.workspaces = [
            self.insert("workspaces", slug="integrity-" + uuid4().hex, nome="QA")
            for _ in range(2)
        ]
        self.parents = {}
        for workspace in self.workspaces:
            self.parents[workspace] = {
                table: self.insert(table, **self.fields(table, workspace))
                for table in [
                    "crm_clientes",
                    "crm_produtos",
                    "crm_vendas",
                    "crm_financeiro",
                ]
            }

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def fields(self, table, workspace):
        if table == "crm_clientes":
            return {"workspace_id": workspace, "nome": "Synthetic"}
        if table == "crm_produtos":
            return {
                "workspace_id": workspace,
                "nome": "Synthetic",
                "tipo": "Produto",
                "preco": 1,
                "estoque": 5,
                "minimo": 1,
            }
        if table == "crm_vendas":
            return {
                "workspace_id": workspace,
                "cliente": "Snapshot",
                "item": "Snapshot",
                "data": "2026-10-13",
                "quantidade": 1,
                "preco": 1,
                "valor": 1,
                "pagamento": "Pix",
                "status": "Rascunho",
            }
        if table == "crm_financeiro":
            return {
                "workspace_id": workspace,
                "descricao": "Synthetic",
                "tipo": "receita",
                "valor": 1,
                "vencimento": "2026-10-13",
                "status": "aberto",
            }
        return {
            "workspace_id": workspace,
            "origem": uuid4(),
            "local_id": 1,
            "fingerprint": "a" * 64,
            "snapshot": "{}",
        }

    def insert(self, table, **fields):
        query = sql.SQL("INSERT INTO socialmei.{} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, fields)),
            sql.SQL(", ").join(sql.Placeholder() for _ in fields),
        )
        if "importacoes" not in table:
            query += sql.SQL(" RETURNING id")
        result = self.conn.execute(query, list(fields.values()))
        return result.fetchone()[0] if "importacoes" not in table else None

    def test_direct_sql_rejects_all_cross_workspace_links(self):
        first, second = self.workspaces
        for table, column, parent, _ in LINKS:
            with self.subTest(table=table, column=column):
                fields = {
                    **self.fields(table, first),
                    column: self.parents[second][parent],
                }
                with self.assertRaises(
                    psycopg.errors.ForeignKeyViolation
                ), self.conn.transaction():
                    self.insert(table, **fields)

    def test_same_workspace_and_nullable_history_links_remain_valid(self):
        workspace = self.workspaces[0]
        for table, column, parent, _ in LINKS:
            with self.subTest(table=table, column=column):
                self.insert(
                    table,
                    **{
                        **self.fields(table, workspace),
                        column: self.parents[workspace][parent],
                    }
                )

    def test_deleting_customer_keeps_workspace_and_history(self):
        workspace = self.workspaces[0]
        customer = self.parents[workspace]["crm_clientes"]
        sale = self.insert(
            "crm_vendas",
            **{**self.fields("crm_vendas", workspace), "cliente_id": customer}
        )
        self.insert(
            "crm_cliente_importacoes",
            **{
                **self.fields("crm_cliente_importacoes", workspace),
                "cliente_id": customer,
            }
        )
        self.conn.execute("DELETE FROM socialmei.crm_clientes WHERE id=%s", (customer,))
        self.assertEqual(
            self.conn.execute(
                "SELECT workspace_id, cliente_id, cliente FROM socialmei.crm_vendas WHERE id=%s",
                (sale,),
            ).fetchone(),
            (workspace, None, "Snapshot"),
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT workspace_id, cliente_id FROM socialmei.crm_cliente_importacoes WHERE workspace_id=%s",
                (workspace,),
            ).fetchone(),
            (workspace, None),
        )

    def test_hardening_is_idempotent(self):
        self.conn.execute(MIGRATION.read_text(), prepare=False)
        self.conn.execute(MIGRATION.read_text(), prepare=False)
        names = [link[3] for link in LINKS]
        self.assertEqual(
            self.conn.execute(
                "SELECT count(*) FROM pg_constraint WHERE connamespace='socialmei'::regnamespace AND conname=ANY(%s) AND convalidated",
                (names,),
            ).fetchone()[0],
            len(names),
        )

    def test_invalid_existing_link_blocks_upgrade_without_repairing_data(self):
        first, second = self.workspaces
        self.conn.execute(
            "ALTER TABLE socialmei.crm_financeiro DROP CONSTRAINT fk_crm_finance_workspace_customer"
        )
        entry = self.insert(
            "crm_financeiro",
            **{
                **self.fields("crm_financeiro", first),
                "cliente_id": self.parents[second]["crm_clientes"],
            }
        )
        with self.assertRaises(
            psycopg.errors.ForeignKeyViolation
        ), self.conn.transaction():
            self.conn.execute(MIGRATION.read_text(), prepare=False)
        self.assertEqual(
            self.conn.execute(
                "SELECT workspace_id, cliente_id FROM socialmei.crm_financeiro WHERE id=%s",
                (entry,),
            ).fetchone(),
            (first, self.parents[second]["crm_clientes"]),
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT count(*) FROM pg_constraint WHERE conname='fk_crm_finance_workspace_customer' AND connamespace='socialmei'::regnamespace"
            ).fetchone()[0],
            0,
        )

    def test_internal_readonly_profile_excludes_auth_and_writes(self):
        self.conn.execute(
            (ROOT / "database/team-readonly-access.sql").read_text(), prepare=False
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname='socialmei_team_readonly'"
            ).fetchone(),
            (False, False, False, False, False, False),
        )
        self.assertTrue(
            self.conn.execute(
                "SELECT has_table_privilege('socialmei_team_readonly', 'socialmei.crm_clientes', 'SELECT')"
            ).fetchone()[0]
        )
        for table, privilege in [
            ("crm_clientes", "INSERT"),
            ("crm_vendas", "UPDATE"),
            ("crm_financeiro", "DELETE"),
            ("auth_credenciais", "SELECT"),
            ("auth_sessoes", "SELECT"),
            ("auth_convites", "SELECT"),
        ]:
            with self.subTest(table=table, privilege=privilege):
                self.assertFalse(
                    self.conn.execute(
                        "SELECT has_table_privilege('socialmei_team_readonly', %s, %s)",
                        ("socialmei." + table, privilege),
                    ).fetchone()[0]
                )
        self.assertFalse(
            self.conn.execute(
                "SELECT has_column_privilege('socialmei_team_readonly', 'socialmei.workspaces', 'configuracao', 'SELECT')"
            ).fetchone()[0]
        )

    def test_readonly_provisioning_rejects_a_privileged_existing_role(self):
        self.conn.execute("CREATE ROLE socialmei_team_readonly NOLOGIN CREATEROLE")
        with self.assertRaises(psycopg.errors.RaiseException), self.conn.transaction():
            self.conn.execute(
                (ROOT / "database/team-readonly-access.sql").read_text(), prepare=False
            )
        self.assertTrue(
            self.conn.execute(
                "SELECT rolcreaterole FROM pg_roles WHERE rolname='socialmei_team_readonly'"
            ).fetchone()[0]
        )
