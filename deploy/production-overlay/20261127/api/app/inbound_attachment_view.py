
import base64,hashlib,re
from pathlib import Path
from fastapi import HTTPException

ROOT=Path('/run/socialmei/private/inbound-media-v1')

MIMES={
    '.mp3':'audio/mpeg',
    '.ogg':'audio/ogg',
    '.oga':'audio/ogg',
    '.opus':'audio/ogg',
    '.wav':'audio/wav',
    '.m4a':'audio/mp4',
    '.jpg':'image/jpeg',
    '.jpeg':'image/jpeg',
    '.png':'image/png',
    '.webp':'image/webp',
    '.pdf':'application/pdf'
}

SQL="""
SELECT a.id,a.media_kind,a.sha256,a.size_bytes,
       m.id AS message_id,j.status AS ai_status,
       j.interpretation
FROM socialmei.me_inbound_attachments a
JOIN socialmei.crm_eventos_canal e
 ON e.workspace_id=a.workspace_id
 AND e.canal_id=a.channel_id
 AND e.fingerprint=a.source_fingerprint
 AND (
   e.chave_evento=a.source_event_key
   OR e.waha_event_key=a.source_event_key
 )
JOIN socialmei.me_messages m
 ON m.workspace_id=a.workspace_id
 AND m.id=e.inbox_message_id
 AND m.conversation_id=a.conversation_id
LEFT JOIN socialmei.me_attachment_ai j
 ON j.attachment_id=a.id AND j.sha256=a.sha256
WHERE a.workspace_id=%s
 AND a.channel_id=3 AND a.origin='waha'
 AND e.tipo='media' AND e.status='processado'
 AND m.origin='waha'
"""

def metadata(conn,workspace,ids):
    if workspace!=60 or not ids:
        return {}

    rows=conn.execute(
        SQL+' AND m.id=ANY(%s)',
        (workspace,ids)
    ).fetchall()

    result={}

    for row in rows:
        result.setdefault(row['message_id'],[]).append({
            k:row[k] for k in (
                'id','media_kind','size_bytes',
                'ai_status','interpretation'
            )
        })

    return result

def file_data(conn,workspace,attachment_id):
    if workspace!=60:
        raise HTTPException(404,'Anexo nao encontrado.')

    row=conn.execute(
        SQL+' AND a.id=%s',
        (workspace,attachment_id)
    ).fetchone()

    if not row:
        raise HTTPException(404,'Anexo nao encontrado.')

    sha=row['sha256']

    if not re.fullmatch('[a-f0-9]{64}',sha):
        raise HTTPException(503,'Anexo indisponivel.')

    files=[
        p for p in ROOT.glob(sha+'.*')
        if p.suffix.lower() in MIMES
        and p.is_file()
        and not p.is_symlink()
    ]

    if len(files)!=1:
        raise HTTPException(503,'Anexo indisponivel.')

    p=files[0]

    if not 0<p.stat().st_size==row['size_bytes']<=10485760:
        raise HTTPException(503,'Anexo indisponivel.')

    data=p.read_bytes()

    if (
        len(data)!=row['size_bytes']
        or hashlib.sha256(data).hexdigest()!=sha
    ):
        raise HTTPException(503,'Anexo indisponivel.')

    return {
        'id':attachment_id,
        'mime':MIMES[p.suffix.lower()],
        'data':base64.b64encode(data).decode()
    }
