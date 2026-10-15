import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("n8n_structure", ROOT / "tools/export-n8n-structure.py")
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


class StructureExportTests(unittest.TestCase):
    def document(self, workflow_id):
        return {
            "id": workflow_id,
            "name": "PRIVATE_SENTINEL",
            "active": True,
            "nodes": [
                {
                    "name": "PRIVATE_SENTINEL start",
                    "type": "n8n-nodes-base.webhook",
                    "typeVersion": 2,
                    "parameters": {"path": "PRIVATE_SENTINEL"},
                    "credentials": {"password": "PRIVATE_SENTINEL"},
                    "webhookId": "PRIVATE_SENTINEL",
                },
                {
                    "name": "PRIVATE_SENTINEL end",
                    "type": "n8n-nodes-base.code",
                    "typeVersion": 2,
                    "parameters": {"jsCode": "return 'PRIVATE_SENTINEL';"},
                    "notes": "PRIVATE_SENTINEL",
                },
            ],
            "connections": {
                "PRIVATE_SENTINEL start": {"main": [[{
                    "node": "PRIVATE_SENTINEL end", "type": "main", "index": 0,
                    "extra": "PRIVATE_SENTINEL",
                }]]},
            },
            "pinData": {"data": "PRIVATE_SENTINEL"},
            "staticData": {"data": "PRIVATE_SENTINEL"},
            "settings": {"errorWorkflow": "PRIVATE_SENTINEL"},
        }

    def test_private_content_removed_while_connections_preserved(self):
        workflow_id = next(iter(EXPORTER.WORKFLOWS))
        raw = self.document(workflow_id)
        before = copy.deepcopy(raw)
        result = EXPORTER.build_template(raw, workflow_id)
        serialized = json.dumps(result)
        self.assertNotIn("PRIVATE_SENTINEL", serialized)
        self.assertNotIn("credentials", serialized)
        self.assertNotIn("pinData", serialized)
        self.assertFalse(result["active"])
        self.assertTrue(all(node["disabled"] for node in result["nodes"]))
        source, target = (node["name"] for node in result["nodes"])
        self.assertEqual(result["connections"][source]["main"][0][0]["node"], target)
        self.assertEqual(raw, before)

    def test_unknown_node_and_invalid_connections_rejected(self):
        workflow_id = next(iter(EXPORTER.WORKFLOWS))
        raw = self.document(workflow_id)
        raw["nodes"][0]["type"] = "private.unknown"
        with self.assertRaises(ValueError):
            EXPORTER.build_template(raw, workflow_id)
        raw = self.document(workflow_id)
        raw["connections"]["PRIVATE_SENTINEL start"]["main"][0][0]["node"] = "missing"
        with self.assertRaises(ValueError):
            EXPORTER.build_template(raw, workflow_id)

    def test_validates_all_sources_before_writing_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "private"
            destination = Path(folder) / "public"
            source.mkdir()
            workflow_ids = list(EXPORTER.WORKFLOWS)
            for workflow_id in workflow_ids[:-1]:
                (source / f"{workflow_id}.json").write_text(json.dumps(self.document(workflow_id)))
            with self.assertRaises(FileNotFoundError):
                EXPORTER.export_templates(source, destination)
            self.assertFalse(destination.exists())
            workflow_id = workflow_ids[-1]
            (source / f"{workflow_id}.json").write_text(json.dumps(self.document(workflow_id)))
            EXPORTER.export_templates(source, destination)
            self.assertEqual(len(list(destination.glob("*.json"))), 8)
            with self.assertRaises(ValueError):
                EXPORTER.export_templates(source, destination)
            with self.assertRaises(ValueError):
                EXPORTER.export_templates(source, source / "public")


if __name__ == "__main__":
    unittest.main()
