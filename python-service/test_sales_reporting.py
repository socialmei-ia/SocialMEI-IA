"""Persisted sales aggregates use a repeatable read of one authenticated workspace."""
from datetime import date
import os
import unittest
from unittest.mock import patch

import psycopg
from fastapi import HTTPException
import test_account_auth as accounts
from workspace_reporting import sales, sales_period


class SalesPeriodTests(unittest.TestCase):
    def test_invalid_custom_period_rejected_before_database_connection(self):
        with patch("workspace_reporting.scope", return_value=1), patch(
            "workspace_reporting.connect", side_effect=AssertionError("No database")
        ), self.assertRaises(HTTPException) as error:
            sales(date(2026, 3, 1), None)
        self.assertEqual(error.exception.status_code, 422)

    def test_default_and_same_length_previous_period(self):
        self.assertEqual(sales_period(None, None, date(2026, 3, 1)),
                         (date(2026, 1, 31), date(2026, 3, 1), 30, date(2026, 1, 1), date(2026, 1, 30)))

    def test_invalid_partial_reverse_too_long_and_underflow_dates(self):
        for start, end in ((date(2026, 1, 1), None), (None, date(2026, 1, 1)),
                           (date(2026, 2, 1), date(2026, 1, 1)),
                           (date(2025, 1, 1), date(2026, 1, 2)),
                           (date(1, 1, 1), date(1, 1, 1))):
            with self.subTest(start=start, end=end), self.assertRaises(HTTPException) as error:
                sales_period(start, end, date(2026, 1, 1))
            self.assertEqual(error.exception.status_code, 422)


@unittest.skipUnless(accounts.DB, "Disposable PostgreSQL required")
class SalesReportDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def seed(self, user, day, value, status="Pago", excluded=False, quantity=1, item="Item fictício"):
        with psycopg.connect(accounts.DB) as conn:
            conn.execute(
                "INSERT INTO socialmei.crm_vendas(workspace_id,cliente,item,data,quantidade,preco,valor,pagamento,status,excluida) "
                "VALUES(%s,'Private customer never exposed',%s,%s,%s,%s,%s,'Pix',%s,%s)",
                (user.identity["negocio"]["id"], item, day, quantity, value, value, status, excluded),
            )

    def report(self, user, query="start=2026-03-01&end=2026-03-03"):
        response = user.get("/api/v1/reporting/sales?" + query)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("Private customer", response.text)
        return response.json()

    def test_custom_period_comparison_daily_ranking_status_and_workspace_isolation(self):
        owner = self.register("sales-owner@example.test")
        other = self.register("sales-other@example.test")
        self.seed(owner, "2026-03-01", "59.90", quantity=2)
        self.seed(owner, "2026-03-03", "10.10", status="Pendente")
        self.seed(owner, "2026-02-28", "20.00")
        for status, excluded in (("Rascunho", False), ("Cancelado", False), ("Pago", True)):
            self.seed(owner, "2026-03-01", "999.00", status=status, excluded=excluded)
        self.seed(owner, "2026-02-25", "999.00")
        self.seed(owner, "2026-03-04", "999.00")
        self.seed(other, "2026-03-01", "999.00")
        report = self.report(owner)
        self.assertEqual(report["current"], {"count": 2, "total": "70.00", "average_ticket": "35.00"})
        self.assertEqual(report["previous"], {"count": 1, "total": "20.00", "average_ticket": "20.00"})
        self.assertEqual(report["change_total_percent"], "250.00")
        self.assertEqual(report["period"]["previous_start"], "2026-02-26")
        self.assertEqual(report["daily"], [
            {"date": "2026-03-01", "count": 1, "total": "59.90"},
            {"date": "2026-03-02", "count": 0, "total": "0.00"},
            {"date": "2026-03-03", "count": 1, "total": "10.10"},
        ])
        self.assertEqual(report["products"], [{"product_id": None, "name": "Item fictício", "quantity": "3", "sales_count": 2, "total": "70.00"}])
        attempted = self.report(owner, "start=2026-03-01&end=2026-03-03&workspace_id=" + str(other.identity["negocio"]["id"]))
        self.assertEqual(attempted["current"], report["current"])

    def test_decimal_precision_large_quantity_and_no_percentage_for_zero_baseline(self):
        owner = self.register("sales-decimals@example.test")
        self.seed(owner, "2026-03-01", "9999999999999.99", quantity=9007199254740991)
        self.seed(owner, "2026-03-01", "0.01", quantity=9007199254740991)
        report = self.report(owner)
        self.assertEqual(report["current"]["total"], "10000000000000.00")
        self.assertEqual(report["current"]["average_ticket"], "5000000000000.00")
        self.assertEqual(report["products"][0]["quantity"], "18014398509481982")
        self.assertIsNone(report["change_total_percent"])

    def test_empty_rounding_and_bounded_rank(self):
        owner = self.register("sales-empty@example.test")
        empty = self.report(owner)
        self.assertEqual(empty["current"], {"count": 0, "total": "0.00", "average_ticket": "0.00"})
        self.assertEqual(len(empty["daily"]), 3)
        self.assertEqual(empty["products"], [])
        for index in range(12):
            self.seed(owner, "2026-03-01", str(index) + ".00", item="Item " + str(index))
        report = self.report(owner)
        self.assertEqual(len(report["products"]), 10)
        self.assertEqual(report["products"][0]["name"], "Item 11")
        self.assertEqual(report["current"]["average_ticket"], "5.50")

    def test_default_business_timezone_and_invalid_timezone_fail_closed(self):
        owner = self.register("sales-timezone@example.test")
        for zone in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
            with self.subTest(zone=zone), patch.dict(os.environ, {"TZ": zone}):
                with psycopg.connect(accounts.DB) as conn:
                    expected = conn.execute("SELECT (CURRENT_TIMESTAMP AT TIME ZONE %s)::date", (zone,)).fetchone()[0]
                report = self.report(owner, "")
                self.assertEqual(report["period"]["end"], expected.isoformat())
                self.assertEqual(report["period"]["timezone"], zone)
                self.assertEqual(len(report["daily"]), 30)
        with patch.dict(os.environ, {"TZ": "invalid-timezone"}):
            self.assertEqual(owner.get("/api/v1/reporting/sales").status_code, 503)

    def test_average_rounds_decimal_half_up_and_decline_is_negative(self):
        owner = self.register("sales-rounding@example.test")
        self.seed(owner, "2026-03-01", "0.01")
        self.seed(owner, "2026-03-01", "0.00")
        self.seed(owner, "2026-02-28", "0.02")
        report = self.report(owner)
        self.assertEqual(report["current"]["average_ticket"], "0.01")
        self.assertEqual(report["change_total_percent"], "-50.00")

    def test_dates_invalid_and_report_only_membership_revocation(self):
        owner = self.register("sales-granter@example.test")
        viewer = self.register("sales-reader@example.test")
        self.seed(owner, "2026-03-01", "59.90")
        for query in ("start=2026-01-01", "start=invalid&end=2026-01-01", "start=2026-03-03&end=2026-03-01", "start=2024-01-01&end=2026-01-01"):
            self.assertEqual(owner.get("/api/v1/reporting/sales?" + query).status_code, 422)
        target = owner.identity["negocio"]["id"]
        self.assertEqual(owner.post("/api/v1/reporting/access", json={"email": "sales-reader@example.test"}).status_code, 200)
        switched = viewer.post("/api/v1/auth/workspaces/switch", json={"workspace_id": target})
        self.assertEqual(switched.status_code, 200, switched.text)
        viewer.headers["X-SocialMEI-CSRF"] = switched.json()["csrf_token"]
        self.assertEqual(self.report(viewer)["current"]["total"], "59.90")
        self.assertEqual(viewer.get("/api/v1/clientes").status_code, 403)
        self.assertEqual(owner.delete("/api/v1/reporting/access/" + str(viewer.identity["usuario"]["id"])).status_code, 204)
        self.assertEqual(viewer.get("/api/v1/reporting/sales").status_code, 401)
