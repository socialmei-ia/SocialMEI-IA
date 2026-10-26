"""Isolated, database-free contract checks for reporting and inventory lookup."""
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import workspace_insights as insights


class AuthorizationTests(unittest.TestCase):
    @patch("workspace_insights.current", return_value={"workspace_id": 7, "role": "viewer"})
    @patch("workspace_insights.require_enabled")
    @patch("workspace_insights.require_shared_data")
    def test_viewer_can_read(self, _shared, _enabled, _current):
        self.assertEqual(insights._actor()["workspace_id"], 7)

    @patch("workspace_insights.current", return_value={"workspace_id": 7, "role": "unknown"})
    @patch("workspace_insights.require_enabled")
    @patch("workspace_insights.require_shared_data")
    def test_unknown_role_cannot_read(self, _shared, _enabled, _current):
        with self.assertRaises(HTTPException) as error:
            insights._actor()
        self.assertEqual(error.exception.status_code, 403)


class AvailabilityTests(unittest.TestCase):
    @patch("workspace_insights.connect")
    @patch("workspace_insights._actor", return_value={"workspace_id": 117})
    def test_search_scoped_and_zero_is_unconfirmed(self, _actor, connected):
        conn = connected.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "nome": "Óleo", "tipo": "Produto", "preco": 25.0, "estoque": 0, "status": "Ativo"},
            {"id": 2, "nome": "Óleo premium", "tipo": "Produto", "preco": 30.0, "estoque": 4, "status": "Ativo"},
            {"id": 3, "nome": "Troca de óleo", "tipo": "Serviço", "preco": 50.0, "estoque": 0, "status": "Ativo"},
            {"id": 4, "nome": "Óleo antigo", "tipo": "Produto", "preco": 10.0, "estoque": 9, "status": "Inativo"},
        ]
        result = insights.availability(q="óleo", limit=10)
        self.assertEqual(conn.execute.call_args.args[1][0], 117)
        self.assertIn("workspace_id=%s", conn.execute.call_args.args[0])
        self.assertEqual([i["availability"] for i in result["items"]],
                         ["unconfirmed", "in_stock", "service", "inactive"])
        self.assertIsNone(result["items"][2]["stock"])
        self.assertFalse(result["automated_reply_enabled"])

    @patch("workspace_insights._actor", return_value={"workspace_id": 1})
    def test_control_characters_rejected_before_db(self, _actor):
        with self.assertRaises(HTTPException) as error:
            insights.availability(q="a\nb", limit=10)
        self.assertEqual(error.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
