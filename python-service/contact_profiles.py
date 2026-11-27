
import os
import re
import json
import time
import fcntl
import hashlib
import base64
import logging
import threading
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import settings

from database import connect
from instagram_runtime import build_runtime
from instagram_token_vault import TokenBinding
from whatsapp_human_transport import WahaHumanTransport

ROOT=Path("/tmp/socialmei-contact-profiles")
ROOT.mkdir(mode=0o700,exist_ok=True)

def load(workspace):
    try:
        return json.loads(
            (ROOT/(str(workspace)+".json")).read_text()
        )
    except Exception:
        return {}

def save(workspace,data):
    fd,path=tempfile.mkstemp(dir=ROOT)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(data,f)
        os.replace(path,ROOT/(str(workspace)+".json"))
    finally:
        if os.path.exists(path):
            os.unlink(path)

def clean(value):
    if not isinstance(value,str):
        return ""
    value=" ".join(value.split())
    if any(c in value for c in "<>&"):
        return ""
    return value[:100]

def picture(url):
    if not isinstance(url,str):
        return ""

    parsed=urlsplit(url)
    host=parsed.hostname or ""

    allowed=("fbcdn.net","cdninstagram.com","whatsapp.net")

    if (
        parsed.scheme!="https"
        or parsed.username or parsed.password
        or parsed.port not in (None,443)
        or not any(
            host==d or host.endswith("."+d)
            for d in allowed
        )
    ):
        return ""

    try:
        with httpx.Client(
            timeout=8,
            trust_env=False,
            follow_redirects=False
        ) as client:
            with client.stream("GET",url) as r:
                if r.status_code!=200:
                    return ""

                mime=r.headers.get(
                    "content-type",""
                ).split(";")[0]

                if mime not in (
                    "image/jpeg","image/png","image/webp"
                ):
                    return ""

                data=bytearray()

                for chunk in r.iter_bytes():
                    data.extend(chunk)
                    if len(data)>262144:
                        return ""

        valid=(
            (mime=="image/jpeg" and data[:3]==b"\xff\xd8\xff")
            or
            (mime=="image/png" and data[:8]==b"\x89PNG\r\n\x1a\n")
            or
            (mime=="image/webp" and data[:4]==b"RIFF"
             and data[8:12]==b"WEBP")
        )

        if not valid:
            return ""

        return (
            "data:"+mime+";base64,"
            +base64.b64encode(data).decode()
        )
    except Exception:
        return ""

def refresh(workspace,force=False):
    if workspace not in (60,61):
        return

    lock=ROOT/(str(workspace)+".lock")

    with lock.open("a") as handle:
        try:
            fcntl.flock(
                handle,fcntl.LOCK_EX|fcntl.LOCK_NB
            )
        except BlockingIOError:
            return

        cache=load(workspace)
        now=time.time()

        with connect() as conn:
            rows=conn.execute(
                "SELECT id,origin,account_ref,contact_ref "
                "FROM socialmei.me_conversations "
                "WHERE workspace_id=%s "
                "AND origin IN ('instagram','waha') "
                "ORDER BY id DESC LIMIT 100",
                (workspace,)
            ).fetchall()

            ig=conn.execute(
                "SELECT id,external_account_id,encrypted_token "
                "FROM socialmei.ig_meta_connections "
                "WHERE workspace_id=%s AND status='connected' "
                "AND expires_at>NOW()",
                (workspace,)
            ).fetchone()

        runtime=build_runtime()
        cfg=settings.instagram_runtime_configuration()
        base="https://graph.instagram.com/"+cfg["graph_version"]

        wa=settings.whatsapp_human_configuration()

        ig_token=None
        if ig:
            ig_token=runtime.oauth.vault.open(
                ig[2],TokenBinding(workspace,ig[0],ig[1])
            )

        wa_ok=(
            wa is not None
            and wa.workspace_id==workspace
            and wa.engine=="GOWS"
        )

        if wa_ok:
            try:
                wa_ok=(
                    WahaHumanTransport(wa)
                    .inspect_session()["status"]=="WORKING"
                )
            except Exception:
                wa_ok=False

        names=0
        photos=0
        checked=0

        valid_ids={str(r[0]) for r in rows}
        cache={
            k:v for k,v in cache.items()
            if k in valid_ids
        }

        with httpx.Client(
            timeout=10,
            trust_env=False,
            follow_redirects=False
        ) as client:

            for cid,origin,account,contact in rows:
                key=str(cid)
                old=cache.get(key,{})

                if (
                    not force
                    and old.get("account")==account
                    and old.get("contact")==contact
                    and old.get("expires",0)>now
                ):
                    continue

                if checked>=20:
                    break

                checked+=1
                name=""
                photo=""

                try:
                    if (
                        origin=="instagram"
                        and ig_token
                        and account=="instagram:"+ig[1]
                        and re.fullmatch(
                            r"instagram:[0-9]{1,40}",contact
                        )
                    ):
                        ident=contact.split(":",1)[1]

                        r=client.get(
                            base+"/"+ident,
                            params={
                                "fields":"name,username,profile_pic"
                            },
                            headers={
                                "Authorization":"Bearer "+ig_token
                            }
                        )

                        if r.status_code==200:
                            d=r.json()

                            if str(d.get("id"))==ident:
                                name=clean(d.get("name"))
                                username=clean(d.get("username"))

                                if not name and username:
                                    name="@"+username

                                photo=picture(d.get("profile_pic"))

                    elif (
                        origin=="waha" and wa_ok
                        and account=="waha:"+wa.account_id
                    ):
                        WahaHumanTransport(wa).validate_scope({
                            "workspace_id":workspace,
                            "instancia":wa.instance,
                            "sessao":wa.session,
                            "identificador_conta":wa.account_id,
                            "contact_ref":contact
                        })

                        params={
                            "session":wa.session,
                            "contactId":contact[5:]
                        }

                        headers={"X-Api-Key":wa.api_key}

                        r=client.get(
                            wa.base_url+"/api/contacts",
                            params=params,headers=headers
                        )

                        if r.status_code==200:
                            d=r.json()
                            name=clean(
                                d.get("pushname")
                                or d.get("name")
                                or d.get("shortName")
                            )

                        r=client.get(
                            wa.base_url+"/api/contacts/profile-picture",
                            params=params,headers=headers
                        )

                        if r.status_code==200:
                            photo=picture(
                                r.json().get("profilePictureURL")
                            )

                    if name and any(c.isalpha() for c in name):
                        with connect() as conn:
                            result=conn.execute(
                                "UPDATE socialmei.me_conversations "
                                "SET contact_name=CASE "
                                "WHEN contact_name ~ '^[+][0-9]{8,15}$' "
                                "THEN %s||' ('||contact_name||')' "
                                "ELSE %s END "
                                "WHERE workspace_id=%s AND id=%s "
                                "AND account_ref=%s AND contact_ref=%s "
                                "AND origin=%s AND cliente_id IS NULL "
                                "AND (contact_name IN "
                                "('Contato do Instagram','Contato do WhatsApp') "
                                "OR contact_name ~ '^[+][0-9]{8,15}$')",
                                (
                                    name,name,workspace,cid,
                                    account,contact,origin
                                )
                            )
                            names+=result.rowcount

                    cache[key]={
                        "account":account,
                        "contact":contact,
                        "photo":photo,
                        "expires":now+(21600 if photo else 3600)
                    }

                    photos+=bool(photo)

                except Exception:
                    continue

        save(workspace,cache)

        if force:
            print("WORKSPACE="+str(workspace))
            print("NOMES_ATUALIZADOS="+str(names))
            print("FOTOS_CARREGADAS="+str(photos))

_last={}
_mutex=threading.Lock()

def refresh_safe(workspace):
    try:
        refresh(workspace)
    except Exception:
        pass

def attach(workspace,items):
    if workspace not in (60,61):
        return

    cache=load(workspace)
    now=time.time()

    for row in items:
        item=cache.get(str(row["id"]),{})

        if (
            item.get("account")==row.get("account_ref")
            and item.get("contact")==row.get("contact_ref")
            and item.get("expires",0)>now
        ):
            photo=item.get("photo","")

            if photo:
                row["contact_avatar"]=photo
                row["avatar_version"]=hashlib.sha256(
                    photo.encode()
                ).hexdigest()[:16]

    with _mutex:
        if now-_last.get(workspace,0)>=300:
            _last[workspace]=now
            threading.Thread(
                target=refresh_safe,
                args=(workspace,),
                daemon=True
            ).start()
