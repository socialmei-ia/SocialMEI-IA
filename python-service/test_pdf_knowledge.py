"""Private PDF ingestion and search contract, no network or real documents."""
import io
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app import app
from pdf_knowledge import extract_chunks, validated_name, MAX_BYTES


class PdfKnowledgeContracts(unittest.TestCase):
    def test_reject_bad_filename_and_invalid_documents(self):
        for name in ("", "../segredo.pdf", "arquivo.txt", "/tmp/doc.pdf", "doc.pdf\n", "doc.pdf\x00"):
            with self.subTest(name=name), self.assertRaises(HTTPException):
                validated_name(name)
        self.assertEqual(validated_name("tabela-precos.pdf"), "tabela-precos.pdf")
        for raw in (b"%PDF-", b"not a pdf", b"%PDF-1.7" + b"x" * (MAX_BYTES + 1)):
            with self.subTest(length=len(raw)), self.assertRaises(HTTPException):
                extract_chunks(raw)

    def test_blank_pdf_flags_no_text_not_fake_knowledge(self):
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        writer.write(output)
        pages, chunks = extract_chunks(output.getvalue())
        self.assertEqual(pages, 1)
        self.assertEqual(chunks, [])

    def test_off_by_default_before_upload_or_database_access(self):
        with patch.dict(os.environ, {
            "SOCIALMEI_KNOWLEDGE_PDF_ENABLED": "false",
            "SOCIALMEI_AUTH_ENABLED": "true",
            "SOCIALMEI_AUTH_ORIGIN": "https://app.example.com",
            "SOCIALMEI_SHARED_DATA_ENABLED": "true",
        }):
            client = TestClient(app, base_url="https://app.example.com")
            self.assertEqual(client.get("/api/v1/knowledge/pdf").status_code, 401)
            # An authenticated request is needed; disabled endpoint never opens PDF.
            self.assertEqual(
                client.post("/api/v1/knowledge/pdf?filename=test.pdf",
                            headers={"Origin": "https://app.example.com", "Content-Type": "application/pdf"},
                            content=b"%PDF-1.7").status_code,
                401,
            )
