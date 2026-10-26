"""Safety checks for private PDF ingestion, without touching a real database."""
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

import pdf_knowledge as knowledge


class PDFKnowledgeSafetyTests(unittest.TestCase):
    def test_feature_is_off_by_default(self):
        with patch.dict(os.environ, {"SOCIALMEI_KNOWLEDGE_PDF_ENABLED": "false"}):
            with self.assertRaises(HTTPException) as err:
                knowledge._enabled()
            self.assertEqual(err.exception.status_code, 503)

    def test_rejects_oversized_or_non_pdf_input(self):
        for blob in (b"not a pdf", b"%PDF-" + b"x" * knowledge.MAX_FILE):
            with self.subTest(size=len(blob)), self.assertRaises(HTTPException) as err:
                knowledge._extract(blob)
            self.assertEqual(err.exception.status_code, 422)

    def test_extract_returns_page_references(self):
        source = MagicMock()
        source.is_encrypted = False
        source.pages = [MagicMock(), MagicMock()]
        source.pages[0].extract_text.return_value = "Venda de produtos"
        source.pages[1].extract_text.return_value = "  "
        with patch("pdf_knowledge.PdfReader", return_value=source):
            pages, indexed = knowledge._extract(b"%PDF-test-data")
        self.assertEqual(pages, 2)
        self.assertEqual(indexed, [(1, "Venda de produtos")])

    @patch("pdf_knowledge.require_enabled")
    @patch("pdf_knowledge.current", return_value={"workspace_id": 19, "role": "viewer"})
    def test_viewer_cannot_manage_documents(self, _current, _require):
        with self.assertRaises(HTTPException) as err:
            knowledge._user(manage=True)
        self.assertEqual(err.exception.status_code, 403)

    def test_migrations_do_not_collide_with_instagram(self):
        from pathlib import Path
        migrations = Path(__file__).resolve().parents[1] / "database" / "migrations"
        self.assertTrue((migrations / "028_instagram_temporary_media.sql").is_file())
        self.assertTrue((migrations / "029_knowledge_pdfs.sql").is_file())
        self.assertEqual(
            len(list(migrations.glob("029_*.sql"))), 1,
            "Knowledge schema must have exactly one migration version",
        )


if __name__ == "__main__":
    unittest.main()
