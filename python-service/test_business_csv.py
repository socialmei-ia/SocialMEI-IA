import csv
from datetime import date
from decimal import Decimal
import io
import os
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import psycopg
from fastapi.testclient import TestClient
from app import app
from business_csv import ExportPeriod, cell
import test_account_auth as accounts
from test_account_auth import DB, ENV, HEADERS, ORIGIN


class CsvContracts(unittest.TestCase):
    def test_formula_and_excel_values(self):
        zone = ZoneInfo("America/Recife")
        for value in ("=1+1", " +cmd", "@SUM(A1)", "-formula", "\ttexto", "\ntexto", "\ufeff=1+1"):
            self.assertTrue(cell(value, zone).startswith("'"))
        self.assertEqual(cell(Decimal("59.90"), zone), "59,90")
        self.assertEqual(cell(date(2026, 11, 4), zone), "04/11/2026")
        self.assertEqual(cell(None, zone), "")

    def test_invalid_periods(self):
        for data in ({"start":"2026-11-04"}, {"start":"2026-11-04","end":"2026-10-01"},
                     {"start":"2020-01-01","end":"2026-01-01"}, {"start":"9999-12-31","end":"9999-12-31"}, {"workspace_id":5}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                ExportPeriod.model_validate(data)

    def test_unauthenticated_export_does_not_open_database(self):
        with patch.dict(os.environ, ENV), patch("account_auth.connect", side_effect=AssertionError("database")):
            client=TestClient(app,base_url=ORIGIN,headers=HEADERS)
            self.assertEqual(client.post("/api/v1/exports/clientes",json={}).status_code,401)


@unittest.skipUnless(DB, "TEST_DATABASE_URL not configured")
class CsvDatabase(unittest.TestCase):
    setUpClass=classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp=accounts.AccountDatabaseTests.setUp
    login=accounts.AccountDatabaseTests.login

    def test_owner_export_is_scoped_formula_safe_and_audited(self):
        client=self.admin_client
        self.assertEqual(client.post("/api/v1/clientes",json={"nome":"=Cliente Teste"}).status_code,201)
        with psycopg.connect(DB) as conn:
            wid=conn.execute("INSERT INTO socialmei.workspaces(slug,nome) VALUES('other','Other') RETURNING id").fetchone()[0]
            conn.execute("INSERT INTO socialmei.crm_clientes(workspace_id,nome) VALUES(%s,'PRIVATE_OTHER')",(wid,))
        response=client.post("/api/v1/exports/clientes",json={})
        self.assertEqual(response.status_code,200,response.text)
        value=response.json()
        self.assertEqual(value["row_count"],1)
        self.assertTrue(value["csv"].startswith("\ufeff"))
        rows=list(csv.reader(io.StringIO(value["csv"].lstrip("\ufeff")),delimiter=";"))
        self.assertEqual(rows[1][1],"'=Cliente Teste")
        self.assertNotIn("PRIVATE_OTHER",value["csv"])
        self.assertNotIn("observacao",value["csv"])
        with psycopg.connect(DB) as conn:
            actions=[r[0] for r in conn.execute("SELECT acao FROM socialmei.auth_auditoria WHERE user_id=%s",(self.admin_id,))]
        self.assertIn("export_clientes:"+str(client.identity["negocio"]["id"]),actions)

    def test_period_and_exact_decimal_product_export(self):
        client=self.admin_client
        self.assertEqual(client.post("/api/v1/produtos",json={"nome":"Blusa Teste","preco":59.9,"estoque":5}).status_code,201)
        result=client.post("/api/v1/exports/produtos",json={}).json()
        self.assertIn('"59,90"',result["csv"])
        empty=client.post("/api/v1/exports/produtos",json={"start":"2020-01-01","end":"2020-01-02"})
        self.assertEqual(empty.status_code,200)
        self.assertEqual(empty.json()["row_count"],0)
        for kind in ("vendas","financeiro","agendamentos"):
            response=client.post("/api/v1/exports/"+kind,json={})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()["row_count"],0)

    def test_csrf_readonly_roles_revocation_and_no_silent_truncation(self):
        client=self.admin_client
        client.post("/api/v1/clientes",json={"nome":"One"})
        client.post("/api/v1/clientes",json={"nome":"Two"})
        with patch("business_csv.LIMIT",1):
            self.assertEqual(client.post("/api/v1/exports/clientes",json={}).status_code,422)
        csrf=client.headers.pop("X-SocialMEI-CSRF")
        self.assertEqual(client.post("/api/v1/exports/clientes",json={}).status_code,403)
        client.headers["X-SocialMEI-CSRF"]=csrf
        for role in ("member","viewer","report_viewer"):
            with psycopg.connect(DB) as conn:
                conn.execute("UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s",(role,self.admin_id))
            self.assertEqual(client.post("/api/v1/exports/clientes",json={}).status_code,403)
        with psycopg.connect(DB) as conn:
            conn.execute("UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE user_id=%s",(self.admin_id,))
        self.assertEqual(client.post("/api/v1/exports/clientes",json={}).status_code,401)
