"""Two fictional businesses exercised through authenticated APIs on disposable SQL."""

import unittest
from uuid import uuid4

import test_account_auth as accounts
from workspace_profile import Capabilities

PREFIX = "/api/v1"
AGENDA_RANGE = "?from_date=2026-11-01&to_date=2026-11-30"


@unittest.skipUnless(accounts.DB, "TEST_DATABASE_URL not configured")
class BusinessFixtureFlowsTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register
    create = accounts.AccountDatabaseTests.create

    def business(self, address, name, services):
        client = self.register(address)
        response = client.patch(PREFIX + "/auth/profile", json={"nome_negocio": name})
        self.assertEqual(response.status_code, 200, response.text)
        profile = {
            "version": 1,
            "businessName": name,
            "segment": "services" if services else "fashion",
            "activity": "Odontologia fictícia" if services else "Moda fictícia",
            "offers": ["services" if services else "products"],
            "services": ["Avaliação odontológica"] if services else [],
            "productCategories": [] if services else ["Roupas"],
            "capabilities": {key: key == ("appointments" if services else "inventory") for key in Capabilities.model_fields},
            "modules": ["clients", "inbox", "services", "appointments"] if services else ["clients", "inbox", "products", "inventory", "sales"],
            "ignoredSuggestions": [],
            "completed": True,
        }
        response = client.patch(PREFIX + "/workspace-profile", json={"schema_version": 1, "expected_revision": 0, "profile": profile})
        self.assertEqual(response.status_code, 200, response.text)
        return client

    def pair(self):
        sorria = self.business("sorria@example.test", "SorriaOdonto", True)
        style = self.business("style@example.test", "She Style", False)
        self.assertNotEqual(sorria.identity["negocio"]["id"], style.identity["negocio"]["id"])
        return sorria, style

    def sale(self, client, customer, product, **changes):
        payload = {
            "operation_id": str(uuid4()), "cliente_id": customer["id"],
            "produto_id": product["id"], "data": "2026-11-03", "quantidade": 2,
            "preco": product["preco"], "desconto": 0, "pagamento": "Pix", **changes,
        }
        return client.post(PREFIX + "/vendas", json=payload), payload

    def test_two_businesses_persist_catalog_agenda_sales_and_new_sessions(self):
        sorria, style = self.pair()
        patient = self.create(sorria, "clientes", {"nome": "Paciente fictícia"})
        shopper = self.create(style, "clientes", {"nome": "Compradora fictícia"})
        service = self.create(sorria, "produtos", {"nome": "Avaliação odontológica fictícia", "tipo": "Serviço", "preco": 120})
        blouse = self.create(style, "produtos", {"nome": "Blusa fictícia", "preco": 79.9, "estoque": 5, "minimo": 2})
        self.assertIsNone(service["estoque"])
        reminder = {"operation_id": str(uuid4()), "title": service["nome"], "cliente_id": patient["id"], "scheduled_for": "2026-11-03T09:30:00-03:00", "notes": "Horário fictício; lembrete manual, sem envio."}
        appointment = self.create(sorria, "agenda", reminder)
        self.assertEqual(sorria.post(PREFIX + "/agenda", json=reminder).json()["id"], appointment["id"])
        response, packet = self.sale(style, shopper, blouse)
        self.assertEqual(response.status_code, 201, response.text)
        sold = response.json()
        self.assertEqual(sold["valor"], 159.8)
        self.assertTrue(sold["estoque_aplicado"])
        self.assertEqual(style.post(PREFIX + "/vendas", json=packet).json()["id"], sold["id"])
        service_sale, _ = self.sale(sorria, patient, service, quantidade=1)
        self.assertEqual(service_sale.status_code, 201, service_sale.text)
        self.assertFalse(service_sale.json()["estoque_aplicado"])
        for address, name, expected_item, expected_sales in (("sorria@example.test", "SorriaOdonto", service, 1), ("style@example.test", "She Style", blouse, 1)):
            fresh = self.login(address)
            self.assertEqual(fresh.get(PREFIX + "/workspace-profile").json()["profile"]["businessName"], name)
            items = fresh.get(PREFIX + "/produtos").json()
            self.assertEqual([row["id"] for row in items], [expected_item["id"]])
            self.assertEqual(items[0]["estoque"], None if name == "SorriaOdonto" else 3)
            self.assertEqual(len(fresh.get(PREFIX + "/vendas").json()), expected_sales)
            reminders = fresh.get(PREFIX + "/agenda" + AGENDA_RANGE).json()["items"]
            self.assertEqual(len(reminders), 1 if name == "SorriaOdonto" else 0)

    def test_foreign_links_are_rejected_without_stock_or_agenda_side_effects(self):
        sorria, style = self.pair()
        patient = self.create(sorria, "clientes", {"nome": "Paciente fictício"})
        shopper = self.create(style, "clientes", {"nome": "Comprador fictício"})
        blouse = self.create(style, "produtos", {"nome": "Blusa fictícia", "preco": 80, "estoque": 5})
        rejected, _ = self.sale(sorria, patient, blouse)
        self.assertEqual(rejected.status_code, 422)
        rejected, _ = self.sale(style, patient, blouse)
        self.assertEqual(rejected.status_code, 422)
        rejected, _ = self.sale(style, shopper, blouse, quantidade=6)
        self.assertEqual(rejected.status_code, 409)
        reminder = {"operation_id": str(uuid4()), "title": "Consulta fictícia", "cliente_id": shopper["id"], "scheduled_for": "2026-11-03T09:30:00-03:00"}
        self.assertEqual(sorria.post(PREFIX + "/agenda", json=reminder).status_code, 422)
        self.assertEqual(style.get(PREFIX + "/produtos").json()[0]["estoque"], 5)
        for client in (sorria, style):
            self.assertEqual(client.get(PREFIX + "/vendas").json(), [])
            self.assertEqual(client.get(PREFIX + "/agenda" + AGENDA_RANGE).json()["items"], [])

    def test_cancelled_sale_restores_only_style_stock_once(self):
        sorria, style = self.pair()
        service = self.create(sorria, "produtos", {"nome": "Consulta fictícia", "tipo": "Serviço", "preco": 120})
        shopper = self.create(style, "clientes", {"nome": "Compradora fictícia"})
        blouse = self.create(style, "produtos", {"nome": "Blusa fictícia", "preco": 80, "estoque": 5})
        response, _ = self.sale(style, shopper, blouse)
        self.assertEqual(response.status_code, 201, response.text)
        sale = response.json()
        action = {"operation_id": str(uuid4()), "expected_version": sale["versao"]}
        path = PREFIX + "/vendas/" + str(sale["id"]) + "/cancelar"
        self.assertEqual(sorria.post(path, json=action).status_code, 404)
        cancelled = style.post(path, json=action)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(style.post(path, json=action).json(), cancelled.json())
        self.assertEqual(style.get(PREFIX + "/produtos").json()[0]["estoque"], 5)
        self.assertEqual(sorria.get(PREFIX + "/produtos").json()[0]["id"], service["id"])
        self.assertIsNone(sorria.get(PREFIX + "/produtos").json()[0]["estoque"])
