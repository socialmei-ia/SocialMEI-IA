"""IPC adapter to the real FastAPI app, exclusively on a disposable local DB."""

import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from uuid import uuid4

database = os.environ.get("TEST_DATABASE_URL", "")
parsed = urlsplit(database)
if (os.environ.get("SOCIALMEI_DEMO_DISPOSABLE_TESTS") != "1"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.port != 55491 or parsed.path != "/socialmei_demo_test"):
    raise SystemExit("Only the explicitly marked loopback:55491 disposable DB is accepted.")

origin = "https://mei-demo.example.test"
os.environ.update({
    "DATABASE_URL": database,
    "SOCIALMEI_AUTH_ENABLED": "true",
    "SOCIALMEI_AUTH_ORIGIN": origin,
    "SOCIALMEI_SHARED_DATA_ENABLED": "true",
    "SOCIALMEI_REGISTRATION_MODE": "open",
    "SOCIALMEI_IDENTITY_MODE": "disabled",
    "SOCIALMEI_SMTP_ENABLED": "false",
    "SOCIALMEI_PUBLIC_BOOKING_ENABLED": "false",
    "SOCIALMEI_WHATSAPP_BOT_ENABLED": "false",
    "SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED": "false",
    "SOCIALMEI_WAHA_INGRESS_MODE": "disabled",
    "SOCIALMEI_INSTAGRAM_INGRESS_MODE": "disabled",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-service"))
import psycopg
from fastapi.testclient import TestClient
from app import app

clients = {}
tables = ("crm_clientes", "crm_produtos", "agenda_resources", "agenda_appointments",
          "crm_vendas", "crm_financeiro", "crm_opportunities", "agenda_reminders")
transport_tables = ("me_messages", "me_conversations", "crm_canais", "ig_meta_connections")


def request(client, command):
    response = client.request(command.get("method", "GET"), "/api/v1" + command["path"],
                              json=command.get("body"), headers=command.get("headers"))
    result = None if response.status_code == 204 else response.json()
    if isinstance(result, dict) and result.get("csrf_token"):
        client.identity = result
        client.headers["X-SocialMEI-CSRF"] = result["csrf_token"]
        client.headers["X-SocialMEI-Identity"] = f"{result['usuario']['id']}:{result['negocio']['id']}"
    return {"status": response.status_code, "body": result}


def execute(command):
    action = command["action"]
    if action == "register":
        if command["business"] not in {"Brilho&Limpeza Service", "Bella Store"}:
            raise ValueError("Unknown fixture business")
        client = TestClient(app, base_url=origin, headers={
            "Origin": origin, "X-SocialMEI-Client": "browser"})
        result = request(client, {"method": "POST", "path": "/auth/register", "body": {
            "nome": "Proprietário FICTÍCIO", "email": f"mei-demo-{uuid4().hex}@example.test",
            "senha": "Isolated-fictional-password-2026!"}})
        if result["status"] != 201:
            return result
        clients[command["account"]] = client
        return request(client, {"method": "PATCH", "path": "/auth/profile", "body": {
            "nome_negocio": command["business"]}})
    client = clients[command["account"]]
    if action == "request":
        return request(client, command)
    if action == "snapshot":
        workspace = client.identity["negocio"]["id"]
        with psycopg.connect(database) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            counts = {table: conn.execute(
                f"SELECT count(*) FROM socialmei.{table} WHERE workspace_id=%s", (workspace,)
            ).fetchone()[0] for table in tables}
            counts["fingerprints"] = {table: conn.execute(
                f"SELECT md5(COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.id),'[]'::jsonb)::text) "
                f"FROM socialmei.{table} t WHERE workspace_id=%s", (workspace,)
            ).fetchone()[0] for table in tables}
            counts["transport_global"] = {table: conn.execute(
                f"SELECT count(*) FROM socialmei.{table}"
            ).fetchone()[0] for table in transport_tables}
        return {"status": 200, "body": counts}
    raise ValueError("Unknown command")


print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    try:
        command = json.loads(line)
        result = execute(command)
        print(json.dumps({"id": command["id"], **result}, ensure_ascii=False), flush=True)
    except Exception as error:
        print(json.dumps({"id": command.get("id"), "error": type(error).__name__}), flush=True)

for client in clients.values():
    client.close()
