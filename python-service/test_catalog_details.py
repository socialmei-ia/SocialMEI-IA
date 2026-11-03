"""Catalog details persist on the authenticated business, including inactive items."""
import unittest
import hashlib
import json
from pydantic import ValidationError
from catalog_data import ProdutoCreate, ProdutoUpdate
from product_import import ImportItem, snapshot_and_hash
from workspace_transfer import TransferPacket, packet_fingerprint
from test_workspace_transfer import sample
import test_business_fixture_flows as fixtures
import test_account_auth as accounts


class CatalogDetailsValidationTests(unittest.TestCase):
    def test_legacy_transfer_fingerprint_preserved_and_details_bound(self):
        packet = TransferPacket.model_validate(sample())
        old = packet.model_dump(mode="json", exclude={"exportado_em"})
        for product in old["produtos"]:
            product.pop("categoria")
            product.pop("descricao")
            product.pop("duracao_minutos")
        for name in ("clientes", "produtos", "vendas", "financeiro"):
            old[name].sort(key=lambda row: row["id"])
        fingerprint = hashlib.sha256(json.dumps(
            old, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode()).hexdigest()
        self.assertEqual(packet_fingerprint(packet), fingerprint)
        packet.produtos[0].categoria = "Moda"
        self.assertNotEqual(packet_fingerprint(packet), fingerprint)

    def test_legacy_import_fingerprint_is_preserved_and_new_details_are_bound(self):
        item = ImportItem(local_id=1, produto={"nome": "Legado", "preco": 10})
        old = item.model_dump(mode="json")
        old["produto"].pop("categoria")
        old["produto"].pop("descricao")
        old["produto"].pop("duracao_minutos")
        fingerprint = hashlib.sha256(
            json.dumps(old, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        self.assertEqual(snapshot_and_hash(item)[1], fingerprint)
        detailed = ImportItem(
            local_id=1, produto={"nome": "Legado", "preco": 10, "categoria": "Moda"}
        )
        self.assertNotEqual(snapshot_and_hash(detailed)[1], fingerprint)

    def test_optional_details_accept_trim_and_limits(self):
        item = ProdutoCreate(
            nome="Blusa", preco=80, categoria=" Roupas ", descricao=" Tecido fictício "
        )
        self.assertEqual(item.categoria, "Roupas")
        self.assertEqual(item.descricao, "Tecido fictício")
        self.assertEqual(ProdutoCreate(nome="Legado", preco=1).categoria, "")
        for field, value in (
            ("categoria", "x" * 81), ("descricao", "x" * 2001),
            ("categoria", None), ("descricao", None),
            ("categoria", "bad\x00"), ("descricao", "bad\ud800"),
        ):
            with self.subTest(field=field, value_length=len(value or "")), self.assertRaises(ValidationError):
                ProdutoUpdate(expected_version=1, **{field: value})


@unittest.skipUnless(accounts.DB, "TEST_DATABASE_URL not configured")
class CatalogDetailsDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register
    create = accounts.AccountDatabaseTests.create
    business = fixtures.BusinessFixtureFlowsTests.business
    pair = fixtures.BusinessFixtureFlowsTests.pair

    def test_details_edit_deactivate_persist_and_isolate(self):
        sorria, style = self.pair()
        item = self.create(style, "produtos", {
            "nome": "Blusa fictícia", "preco": 80, "estoque": 5,
            "categoria": "Roupas", "descricao": "Descrição fictícia",
        })
        path = fixtures.PREFIX + "/produtos/" + str(item["id"])
        self.assertEqual(sorria.get(path).status_code, 404)
        foreign = sorria.patch(path, json={"expected_version": 1, "categoria": "Outra"})
        self.assertEqual(foreign.status_code, 404)
        saved = style.patch(path, json={
            "expected_version": 1, "categoria": "Moda", "descricao": "", "status": "Inativo",
        })
        self.assertEqual(saved.status_code, 200, saved.text)
        stale = style.patch(path, json={"expected_version": 1, "categoria": "Antiga"})
        self.assertEqual(stale.status_code, 409)
        fresh = self.login("style@example.test")
        actual = fresh.get(path).json()
        self.assertEqual(
            (actual["categoria"], actual["descricao"], actual["status"], actual["estoque"]),
            ("Moda", "", "Inativo", 5),
        )
        self.assertEqual(sorria.get(fixtures.PREFIX + "/produtos").json(), [])
