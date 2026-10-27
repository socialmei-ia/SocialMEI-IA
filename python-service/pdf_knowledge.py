"""Workspace-scoped private PDF knowledge; no remote LLM, OCR or automatic sends.

Original PDF bytes remain in PostgreSQL and are never served over public routes.
Plain text is indexed by PostgreSQL's Portuguese full-text search. Every result
is a source excerpt with document/page provenance, not an AI-generated answer.
"""
import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path
import os
import re
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request, Header, Response
from psycopg.rows import dict_row
from starlette.concurrency import run_in_threadpool

from account_auth import current, require_enabled, Strict
from pydantic import Field
from urllib.parse import quote
from database import connect

router = APIRouter(prefix="/api/v1/knowledge/pdf", tags=["private PDF knowledge"])
MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 100
MAX_CHUNKS = 500
MAX_CHARACTERS = 500000
MAX_DOCUMENTS = 25
EXTRACTION_SLOTS = threading.BoundedSemaphore(2)
METADATA = 'id,filename,page_count,status,uploaded_at,sha256,octet_length(pdf_bytes) AS size_bytes'


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
    """Isolate parser CPU/memory and keep private diagnostics out of API/logs."""
    if not isinstance(raw, bytes) or not 8 <= len(raw) <= MAX_BYTES:
        raise HTTPException(413, "PDF acima do limite de 2 MB.")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(422, "Envie um PDF válido.")
    if not EXTRACTION_SLOTS.acquire(blocking=False):
        raise HTTPException(503, "Há documentos em processamento. Aguarde e tente novamente.")
    try:
        result = subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('pdf_extractor.py'))],
                                input=raw,capture_output=True,timeout=8,check=False,cwd='/',
                                env={'PATH':os.defpath,'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
        if result.returncode or len(result.stdout)>4*1024*1024:
            raise ValueError()
        pages, chunks = json.loads(result.stdout)
        if type(pages) is not int or not 1 <= pages <= MAX_PAGES or not isinstance(chunks,list) or len(chunks)>MAX_CHUNKS:
            raise ValueError()
        return pages,[tuple(chunk) for chunk in chunks]
    except Exception:
        raise HTTPException(422, "PDF não pôde ser processado com segurança. Confira o arquivo e tente novamente.") from None
    finally:
        EXTRACTION_SLOTS.release()


def view(row):
    return {
        "id": str(row["id"]),
        "filename": row["filename"],
        "page_count": row["page_count"],
        "status": row["status"],
        "uploaded_at": row["uploaded_at"].isoformat(),
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
    }


@router.post("", status_code=201)
async def upload(request: Request, filename: str = Query(min_length=1, max_length=160)):
    user = require_knowledge(manage=True)
    validated_name(filename)
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/pdf":
        raise HTTPException(415, "Envie um PDF com Content-Type application/pdf.")
    raw = await pdf_body(request)
    return await run_in_threadpool(store_document, user, filename, raw)


async def pdf_body(request):
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > MAX_BYTES:
            raise HTTPException(413, "PDF acima do limite de 2 MB.")
    return bytes(body)


def store_document(user, filename, raw):
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
        member = conn.execute(
            "SELECT m.role FROM socialmei.workspace_members m JOIN socialmei.auth_credenciais c ON c.user_id=m.user_id AND c.ativo "
            "WHERE m.workspace_id=%s AND m.user_id=%s FOR SHARE OF m,c",
            (user['workspace_id'],user['id']),
        ).fetchone()
        if not member or member['role'] not in {'owner','admin'}:
            raise HTTPException(403,'Permissão para alterar documentos indisponível.')
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
            "RETURNING " + METADATA,
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
        audit(conn,user,'knowledge_pdf_uploaded')
    return view(row)


@router.get("")
def list_documents():
    user = require_knowledge()
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(
            "SELECT " + METADATA + " "
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
        audit(conn,user,'knowledge_pdf_deleted')
    return None


class Reprocess(Strict):
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def audit(conn, user, action):
    conn.execute('INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,%s)', (user['id'],action))


def stored_document(user, identifier):
    with connect() as conn:
        conn.row_factory = dict_row
        row = conn.execute('SELECT * FROM socialmei.kb_pdf_documents WHERE workspace_id=%s AND id=%s', (user['workspace_id'],identifier)).fetchone()
        if not row:
            raise HTTPException(404, 'PDF não encontrado.')
        return row


@router.get('/{document_id}/download')
def download(document_id: UUID):
    row = stored_document(require_knowledge(),document_id)
    return Response(bytes(row['pdf_bytes']), media_type='application/pdf', headers={
        'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
        'Content-Security-Policy':'sandbox',
        'Content-Disposition':"attachment; filename*=UTF-8''"+quote(row['filename'],safe=''),
    })


def rewrite(user, identifier, expected, raw=None, filename=None):
    old = stored_document(user,identifier)
    if old['sha256'] != expected:
        raise HTTPException(409,'O PDF mudou. Atualize a lista antes de continuar.')
    replaced = raw is not None
    raw = bytes(old['pdf_bytes']) if raw is None else raw
    pages,chunks = extract_chunks(raw)
    checksum = hashlib.sha256(raw).hexdigest()
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute('SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE',(user['workspace_id'],))
        role = conn.execute('SELECT role FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s FOR SHARE',(user['workspace_id'],user['id'])).fetchone()
        if not role or role['role'] not in {'owner','admin'}:
            raise HTTPException(403,'Permissão para alterar documentos indisponível.')
        row = conn.execute('SELECT sha256 FROM socialmei.kb_pdf_documents WHERE workspace_id=%s AND id=%s FOR UPDATE',(user['workspace_id'],identifier)).fetchone()
        if not row:
            raise HTTPException(404,'PDF não encontrado.')
        if row['sha256'] != expected:
            raise HTTPException(409,'O PDF mudou. Atualize a lista antes de continuar.')
        if conn.execute('SELECT 1 FROM socialmei.kb_pdf_documents WHERE workspace_id=%s AND sha256=%s AND id<>%s',(user['workspace_id'],checksum,identifier)).fetchone():
            raise HTTPException(409,'Este PDF já está cadastrado neste negócio.')
        row = conn.execute('UPDATE socialmei.kb_pdf_documents SET filename=%s,sha256=%s,pdf_bytes=%s,page_count=%s,status=%s WHERE workspace_id=%s AND id=%s RETURNING '+METADATA,
                           (filename or old['filename'],checksum,raw,pages,'indexed' if chunks else 'no_text',user['workspace_id'],identifier)).fetchone()
        conn.execute('DELETE FROM socialmei.kb_pdf_chunks WHERE workspace_id=%s AND document_id=%s',(user['workspace_id'],identifier))
        if chunks:
            with conn.cursor() as cur:
                cur.executemany('INSERT INTO socialmei.kb_pdf_chunks(workspace_id,document_id,ordinal,page_number,content) VALUES(%s,%s,%s,%s,%s)',[(user['workspace_id'],identifier,n,page,text) for n,page,text in chunks])
        audit(conn,user,'knowledge_pdf_replaced' if replaced else 'knowledge_pdf_reprocessed')
    return view(row)


@router.post('/{document_id}/reprocess')
def reprocess(document_id: UUID, payload: Reprocess):
    return rewrite(require_knowledge(manage=True),document_id,payload.sha256)


@router.put('/{document_id}')
async def replace(document_id: UUID, request: Request, filename: str = Query(min_length=1,max_length=160), if_match: str = Header(alias='If-Match',pattern=r'^[0-9a-f]{64}$')):
    user = require_knowledge(manage=True)
    validated_name(filename)
    if request.headers.get('content-type','').split(';')[0].lower() != 'application/pdf':
        raise HTTPException(415,'Envie um PDF com Content-Type application/pdf.')
    raw = await pdf_body(request)
    return await run_in_threadpool(rewrite,user,document_id,if_match,raw,filename)
