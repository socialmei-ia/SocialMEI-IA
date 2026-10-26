"""WAHA catalog menu cannot send, mutate stock or choose workspace via URL."""
import os
import re
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import app
from whatsapp_catalog import MENU, issue_secret, token_digest, product_view, menu_action


class WhatsAppCatalogContracts(unittest.TestCase):
    def test_server_generated_secret_never_is_short(self):
        secret = issue_secret()
        self.assertRegex(secret, r"^[A-Za-z0-9_-]{64}$")
        self.assertEqual(len(token_digest(secret)), 64)
        self.assertNotEqual(token_digest(secret), token_digest(issue_secret()))

    def test_menu_actions_never_send(self):
        self.assertEqual(len(MENU), 5)
        self.assertEqual(menu_action("2"), "availability")
        self.assertEqual(menu_action("5"), "human_handoff")
        for choice in ("0", "1", "2", "3", "4", "5"):
            self.assertNotIn("send", menu_action(choice))

    def test_products_distinguish_stock_and_services(self):
        base = {"nome": "Cuscuz", "tipo": "Produto", "preco": Decimal("14.50"), "estoque": 2}
        self.assertEqual(product_view(base)["disponibilidade"], "em_estoque")
        self.assertEqual(product_view({**base, "estoque": 0})["disponibilidade"], "indisponivel")
        self.assertEqual(
            product_view({**base, "tipo": "Serviço", "estoque": None})["disponibilidade"],
            "servico_sem_estoque",
        )
        self.assertEqual(product_view(base)["preco"], "14.50")

    def test_technical_api_closed_without_explicit_configuration(self):
        with patch.dict(os.environ, {
            "SOCIALMEI_WA_CATALOG_ENABLED": "false",
            "SOCIALMEI_AUTH_ENABLED": "true",
            "SOCIALMEI_SHARED_DATA_ENABLED": "true",
            "SOCIALMEI_AUTH_ORIGIN": "https://app.example.com",
        }):
            client = TestClient(app, base_url="https://app.example.com")
            response = client.get(
                "/api/v1/integracoes/whatsapp/menu?instancia=testing&opcao=1",
                headers={"Authorization": "Bearer " + issue_secret()},
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(client.get("/api/v1/whatsapp/catalog/access").status_code, 401)
