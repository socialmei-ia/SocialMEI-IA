"""Workspace-scoped private PDF knowledge store. Off by default.

Indexes text pages with PostgreSQL FTS; no model training or outbound requests.
Only owner/admin can upload/delete; collaborators with access can search.
"""
import hashlib
import io
import os
import re
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from psycopg.rows import dict_row
from pypdf import PdfReader

from account_auth import current, require_enabled
from database import connect

router = APIRouter(prefix="/api/v1/knowledge/pdfs", tags=["Private PDF knowledge"])
MAX_FILE = 5 * 1024 * 1024
MAX_PAGES = 80
MAX_PAGE_TEXT = 32768


def _enabled():
    if os.getenv("SOCIALMEI_KNOWLEDGE_PDF_ENABLED", "false").lower() != "true":
        raise HTTPException(503, "Biblioteca PDF ainda não habilitada.")


def _user(*, manage=False):
    require_enabled()
    user = current()
    if manage and user["role"] not in ("owner", "admin"):
        raise HTTPException(403, "Somente responsáveis podem gerenciar documentos.")
    return user


def _extract(blob):
    if not blob.startswith(b"%PDF-") or len(blob) > MAX_FILE:
        raise HTTPException(422, "Arquivo PDF inválido ou maior que 5 MB.")
    try:
        document = PdfReader(io.BytesIO(blob), strict=True)
        if document.is_encrypted or not 1 <= len(document.pages) <= MAX_PAGES:
            raise ValueError("Documento protegido ou grande demais.")
        pages = []
        for page_number, page in enumerate(document.pages, 1):
            text = (page.extract_text() or "").strip()
            if len(text.encode("utf-8")) > MAX_PAGE_TEXT:
                raise ValueError("Texto extenso demais.")
            if text:
                pages.append((page_number, text))
        if not pages:
            raise ValueError("PDF sem texto pesquisável.")
        return len(document.pages), pages
    except (Exception,):
        raise HTTPException(422, "PDF inválido, digitalizado ou sem texto extraível.") from None


@router.post("", status_code=201)
async def upload(request: Request, document: UploadFile = File(...), title: str = Form(...)):
    _enabled()
    user = _user(manage=True)
    if request.query_params:
        raise HTTPException(422, "Parâmetros não permitidos.")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 180:
        raise HTTPException(422, "Nome do documento inválido.")
    if document.content_type != "application/pdf":
        raise HTTPException(422, "Somente PDFs são aceitos.")
    blob = await document.read(MAX_FILE + 1)
    await document.close()
    if len(blob) > MAX_FILE:
        raise HTTPException(413, "Arquivo excede 5 MB.")
    page_count, pages = _extract(blob)
    filehash = hashlib.sha256(blob).hexdigest()
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute(
            "SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE",
            (user["workspace_id"],),
        )
        amount = conn.execute(
            "SELECT COUNT(*) n FROM socialmei.knowledge_pdfs WHERE workspace_id=%s",
            (user["workspace_id"],),
        ).fetchone()["n"]
        if amount >= 30:
            raise HTTPException(429, "Limite de documentos atingido.")
        prior = conn.execute(
            "SELECT id,pages FROM socialmei.knowledge_pdfs WHERE workspace_id=%s AND file_sha256=%s",
            (user["workspace_id"], filehash),
        ).fetchone()
        if prior:
            return {"id": str(prior["id"]), "pages": prior["pages"], "replayed": True}
        doc_id = uuid4()
        conn.execute(
            "INSERT INTO socialmei.knowledge_pdfs(id,workspace_id,uploaded_by,filename,file_sha256,original_bytes,pages) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (doc_id, user["workspace_id"], user["id"], title.strip(), filehash, blob, page_count),
        )
        conn.executemany(
            "INSERT INTO socialmei.knowledge_pdf_pages(workspace_id,document_id,page_number,page_text) VALUES(%s,%s,%s,%s)",
            [(user["workspace_id"], doc_id, page, text) for page, text in pages],
        )
    return {"id": str(doc_id), "pages": page_count, "indexed_pages": len(pages), "replayed": False}


@router.get("")
def list_pdfs():
    _enabled()
    user = _user()
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT id,filename,pages,created_at FROM socialmei.knowledge_pdfs "
            "WHERE workspace_id=%s ORDER BY created_at DESC LIMIT 30",
            (user["workspace_id"],),
        ).fetchall()
    return {"items": [{"id": str(r["id"]), "title": r["filename"], "pages": r["pages"],
                        "created_at": r["created_at"].isoformat()} for r in rows]}


@router.get("/search")
def search(q: str):
    _enabled()
    user = _user()
    if not 2 <= len(q.strip()) <= 200:
        raise HTTPException(422, "Consulta inválida.")
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT p.document_id,p.page_number,d.filename,"
            " LEFT(p.page_text,600) AS excerpt "
            "FROM socialmei.knowledge_pdf_pages p "
            "JOIN socialmei.knowledge_pdfs d ON d.workspace_id=p.workspace_id AND d.id=p.document_id "
            "WHERE p.workspace_id=%s AND p.indexed_text @@ plainto_tsquery('portuguese',%s) "
            "ORDER BY ts_rank(p.indexed_text,plainto_tsquery('portuguese',%s)) DESC LIMIT 8",
            (user["workspace_id"],q,q),
        ).fetchall()
    return {"results": [{"document_id":str(r["document_id"]),"title":r["filename"],
                          "page":r["page_number"],"excerpt":r["excerpt"]} for r in rows]}


@router.delete("/{document_id}", status_code=204)
def delete(document_id: UUID):
    _enabled()
    user = _user(manage=True)
    with connect() as conn:
        deleted = conn.execute(
            "DELETE FROM socialmei.knowledge_pdfs WHERE workspace_id=%s AND id=%s RETURNING id",
            (user["workspace_id"], document_id),
        ).fetchone()
        if not deleted:
            raise HTTPException(404, "Documento não encontrado.")
