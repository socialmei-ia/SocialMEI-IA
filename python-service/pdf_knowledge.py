"""Workspace-scoped private PDF knowledge; no remote LLM, OCR or automatic sends.

Original PDF bytes remain in PostgreSQL and are never served over public routes.
Plain text is indexed by PostgreSQL's Portuguese full-text search. Every result
is a source excerpt with document/page provenance, not an AI-generated answer.
"""
import hashlib
import io
import os
import re
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pypdf import PdfReader

from account_auth import current, require_enabled
from database import connect

router = APIRouter(prefix="/api/v1/knowledge/pdf", tags=["private PDF knowledge"])
MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 100
MAX_CHUNKS = 500
MAX_CHARACTERS = 500000
MAX_DOCUMENTS = 25


def require_knowledge(manage=False):
    require_enabled()
    if os.getenv("SOCIALMEI_KNOWLEDGE_PDF_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Documentos PDF ainda não habilitados neste ambiente.")
    user = current()
    if user["role"] not in {"owner", "admin", "member", "viewer"}:
        raise HTTPException(403, "Acesso não autorizado.")
    if manage and user["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "Somente responsáveis podem alterar documentos.")
    return user


def validated_name(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 160
        or not value.lower().endswith(".pdf") or "/" in value or "\\" in value
        or any(ord(char) < 32 for char in value)
        or not value.strip() or "\x00" in value):
        raise HTTPException(422, "Nome de PDF inválido.")
    return value


def extract_chunks(raw):
    """Bounded extraction; no OCR, active PDF contents or external calls."""
    if not isinstance(raw, bytes) or not 8 <= len(raw) <= MAX_BYTES:
        raise HTTPException(413, "PDF acima do limite de 2 MB.")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(422, "Envie um PDF válido.")
    try:
        pdf = PdfReader(io.BytesIO(raw), strict=True)
        if pdf.is_encrypted or not 1 <= len(pdf.pages) <= MAX_PAGES:
            raise ValueError("encrypted or too many pages")
        chunks = []
        total = 0
        for page_number, page in enumerate(pdf.pages, 1):
            extracted = page.extract_text() or ""
            total += len(extracted)
            if total > MAX_CHARACTERS:
                raise ValueError("too much text")
            extracted = re.sub(r"\s+", " ", extracted).strip()
            extracted = "".join(char for char in extracted if char.isprintable())
            start = 0
            while start < len(extracted):
                part = extracted[start:start + 950].strip()
                if part:
                    chunks.append((len(chunks), page_number, part))
                if len(chunks) > MAX_CHUNKS:
                    raise ValueError("too many chunks")
                if start + 950 >= len(extracted):
                    break
                start += 850
        return len(pdf.pages), chunks
    except Exception:
        # Never include user-controlled PDF errors, filename or parsed text.
        raise HTTPException(422, "PDF não pôde ser processado. Confira se não está protegido ou digitalizado.") from None


def view(row):
    return {
        "id": str(row["id"]),
        "filename": row["filename"],
        "page_count": row["page_count"],
        "status": row["status"],
        "uploaded_at": row["uploaded_at"].isoformat(),
    }


@router.post("", status_code=201)
async def upload(request: Request, filename: str = Query(min_length=1, max_length=160)):
    user = require_knowledge(manage=True)
    validated_name(filename)
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/pdf":
        raise HTTPException(415, "Envie um PDF com Content-Type application/pdf.")
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > MAX_BYTES:
            raise HTTPException(413, "PDF acima do limite de 2 MB.")
    raw = bytes(body)
    pages, chunks = extract_chunks(raw)
    digest = hashlib.sha256(raw).hexdigest()
    with connect() as conn:
        conn.row_factory = dict_row
        # Serialize quota checks with other uploads in the same workspace.
        workspace = conn.execute(
            "SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE",
            (user["workspace_id"],),
        ).fetchone()
        if not workspace:
            raise HTTPException(403, "Negócio indisponível.")
        number = conn.execute(
            "SELECT COUNT(*) AS n FROM socialmei.kb_pdf_documents WHERE workspace_id=%s",
            (user["workspace_id"],),
        ).fetchone()["n"]
        if number >= MAX_DOCUMENTS:
            raise HTTPException(429, "Limite de 25 PDFs por negócio.")
        existing = conn.execute(
            "SELECT 1 FROM socialmei.kb_pdf_documents WHERE workspace_id=%s AND sha256=%s",
            (user["workspace_id"], digest),
        ).fetchone()
        if existing:
            raise HTTPException(409, "Este PDF já está cadastrado neste negócio.")
        identifier = uuid4()
        row = conn.execute(
            "INSERT INTO socialmei.kb_pdf_documents"
            "(workspace_id,id,filename,sha256,pdf_bytes,page_count,status,uploaded_by)"
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING id,filename,page_count,status,uploaded_at",
            (
                user["workspace_id"], identifier, filename, digest, raw, pages,
                "indexed" if chunks else "no_text", user["id"],
            ),
        ).fetchone()
        if chunks:
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO socialmei.kb_pdf_chunks "
                    "(workspace_id,document_id,ordinal,page_number,content) "
                    "VALUES(%s,%s,%s,%s,%s)",
                    [
                        (user["workspace_id"], identifier, ordinal, page, text)
                        for ordinal, page, text in chunks
                    ],
                )
    return view(row)


@router.get("")
def list_documents():
    user = require_knowledge()
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT id,filename,page_count,status,uploaded_at "
            "FROM socialmei.kb_pdf_documents WHERE workspace_id=%s "
            "ORDER BY uploaded_at DESC,id LIMIT 25",
            (user["workspace_id"],),
        ).fetchall()
    return {"items": [view(row) for row in rows]}


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=160), limit: int = Query(5, ge=1, le=10)):
    user = require_knowledge()
    text = q.strip()
    if len(text) < 2 or "\x00" in text:
        raise HTTPException(422, "Consulta inválida.")
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT d.id AS document_id,d.filename,c.page_number,c.content,"
            "ts_rank_cd(c.search_vector,plainto_tsquery('portuguese',%s)) AS relevance "
            "FROM socialmei.kb_pdf_chunks c "
            "JOIN socialmei.kb_pdf_documents d "
            "ON d.workspace_id=c.workspace_id AND d.id=c.document_id "
            "WHERE c.workspace_id=%s AND "
            "c.search_vector @@ plainto_tsquery('portuguese',%s) "
            "ORDER BY relevance DESC, d.uploaded_at DESC, d.id, c.ordinal "
            "LIMIT %s",
            (text, user["workspace_id"], text, limit),
        ).fetchall()
    return {"items": [
        {"document_id": str(row["document_id"]), "filename": row["filename"],
         "page": row["page_number"], "excerpt": row["content"]}
        for row in rows
    ]}


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: UUID):
    user = require_knowledge(manage=True)
    with connect() as conn:
        row = conn.execute(
            "DELETE FROM socialmei.kb_pdf_documents "
            "WHERE workspace_id=%s AND id=%s RETURNING id",
            (user["workspace_id"], document_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "PDF não encontrado.")
    return None
