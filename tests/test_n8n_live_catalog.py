"""Testa a sanitizacao e a classificacao sem consultar a AWS."""
import importlib.util
import json
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "tools/n8n-live-catalog.py"
spec = importlib.util.spec_from_file_location("n8n_live_catalog", path)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class CatalogTests(unittest.TestCase):
    def test_nome_nao_vaza_token_email_ou_url(self):
        self.assertNotIn("IGAGmuitosecreto123456", catalog.safe_name("Instagram IGAGmuitosecreto123456"))
        self.assertNotIn("cliente@example.com", catalog.safe_name("Contato cliente@example.com"))
        self.assertNotIn("private.example", catalog.safe_name("URL https://private.example/path"))

    def test_classifica_capacidades_sem_afirmar_ativacao(self):
        self.assertEqual(catalog.category("Publicar post no Instagram"), "instagram_publicacao")
        self.assertEqual(catalog.category("Análise de Sentimento"), "analise")
        self.assertEqual(catalog.category("whatsapp API oficial"), "whatsapp")

    def test_somente_campos_permitidos_sem_segredos(self):
        sample = [{
            "id": "abc123456",
            "nome": "Instagram Direct",
            "ativo": True,
            "atualizado_em": "2026-10-28T12:00:00Z",
            "salvo": {"total": 17, "tipos": {"httpRequest": 2},
                      "bearer_fixo_presente": True, "auth_template_presente": True,
                      "credentials": {"secret": "DO_NOT_OUTPUT"}},
            "publicado": {"total": 9, "secret": "DO_NOT_OUTPUT"},
            "versoes_diferentes": True,
            "parameters": {"Authorization": "DO_NOT_OUTPUT"}
        }]
        report = catalog.summarise(sample)
        printed = json.dumps(report)
        self.assertNotIn("DO_NOT_OUTPUT", printed)
        self.assertEqual(report["recentes"][0]["nos_publicados"], 9)
        self.assertTrue(report["recentes"][0]["versoes_diferentes"])
        self.assertFalse(report["altera_producao"])

    def test_nao_inclui_workflows_sem_data_inventada(self):
        report = catalog.summarise([{"id":"a","nome":"Teste","ativo":False}])
        self.assertEqual(report["recentes"], [])
        self.assertEqual(len(report["demais"]), 1)


if __name__ == "__main__":
    unittest.main()
