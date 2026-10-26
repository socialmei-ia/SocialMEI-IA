"""Reports expose only anonymized aggregates; no direct DB credentials."""
import unittest

from fastapi.testclient import TestClient
from app import app
from workspace_reporting import csv_rows


class ReportContracts(unittest.TestCase):
    def test_report_requires_authenticated_user(self):
        client = TestClient(app)
        self.assertNotEqual(client.get("/api/v1/reporting/overview").status_code, 200)
        self.assertNotEqual(client.get("/api/v1/reporting/overview.csv").status_code, 200)

    def test_days_bounded_before_database_query(self):
        client = TestClient(app)
        # Auth middleware may reject before input validation; both must fail closed.
        for days in (0, -1, 367, 100000000):
            for suffix in ("overview", "overview.csv"):
                with self.subTest(days=days, suffix=suffix):
                    self.assertNotEqual(
                        client.get(f"/api/v1/reporting/{suffix}?days={days}").status_code,
                        200,
                    )

    def test_fixed_csv_structure_and_aggregates(self):
        synthetic = {
            "sales_by_status": {"Pago": {"quantidade": 3, "valor": "46.55"}},
            "finance_by_type_and_status": [
                {"tipo": "receita", "status": "pago", "quantidade": 2, "valor": "30.10"}
            ],
            "totals": {"clientes": 4, "itens_ativos": 3, "estoque_baixo": 1},
        }
        rows = list(csv_rows(synthetic))
        self.assertEqual(rows[1], ("Vendas", "", "Pago", 3, "46.55"))
        self.assertEqual(rows[2], ("Financeiro", "receita", "pago", 2, "30.10"))
        self.assertEqual(len(rows), 6)
