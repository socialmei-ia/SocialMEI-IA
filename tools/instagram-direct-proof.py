"""Read-only Gate 9 evidence on the team host; never sends or replays webhooks."""
import argparse
import json
import re
import subprocess

API = "socialmei-team-team-api-1"
SHA = re.compile(r"[0-9a-f]{40}")
MARKER = re.compile(r"SOCIALMEI-G9-[A-Z0-9]{12,32}")

# Runs inside the existing API, using its database connection without exporting it.
CHILD = r'''
import json, logging, os, re, sys
logging.disable(logging.CRITICAL)
from database import connect
options = json.load(sys.stdin)
with connect() as conn:
    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    conn.execute("SET LOCAL statement_timeout='5s'")
    conn.execute("SET LOCAL lock_timeout='2s'")
    workspace = conn.execute("SELECT id FROM socialmei.workspaces WHERE id=1 AND slug='team'").fetchone()
    if not workspace:
        raise ValueError('Workspace unavailable')
    connected = conn.execute("SELECT count(*) FROM socialmei.ig_meta_connections WHERE workspace_id=1 AND status='connected' AND expires_at>NOW() AND scopes @> ARRAY['instagram_business_basic','instagram_business_manage_messages']::text[]").fetchone()[0]
    events = conn.execute("SELECT count(*),count(*) FILTER (WHERE kind='message' AND status='processed'),max(received_at)::text FROM socialmei.ig_meta_ingress_events WHERE workspace_id=1").fetchone()
    messages = conn.execute("SELECT count(*) FROM socialmei.me_messages WHERE workspace_id=1 AND origin='instagram'").fetchone()[0]
    result = {'connected_with_messaging_scopes': connected, 'events':events[0], 'processed_message_events':events[1], 'latest_event_at':events[2], 'inbox_messages':messages}
    if options.get('marker'):
        marker = options['marker']
        rows = conn.execute("SELECT count(*),count(*) FILTER (WHERE workspace_id=1),count(*) FILTER (WHERE workspace_id<>1) FROM socialmei.me_messages WHERE origin='instagram' AND text=%s", (marker,)).fetchone()
        linked = conn.execute("SELECT count(*),count(DISTINCT m.id),count(DISTINCT m.conversation_id) FROM socialmei.ig_meta_ingress_events e JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.message_id AND m.origin=e.message_origin JOIN socialmei.me_conversations c ON c.workspace_id=m.workspace_id AND c.id=m.conversation_id AND c.origin=m.origin JOIN socialmei.ig_meta_connections a ON a.workspace_id=e.workspace_id AND a.id=e.connection_id AND a.external_account_id=e.external_account_id WHERE e.workspace_id=1 AND e.kind='message' AND e.status='processed' AND m.text=%s AND c.account_ref='instagram:' || e.external_account_id", (marker,)).fetchone()
        result['marker'] = {'total_messages': rows[0], 'team_messages':rows[1], 'other_workspace_messages':rows[2], 'linked_events':linked[0], 'linked_messages':linked[1], 'linked_conversations':linked[2]}
if options.get('check_subscription'):
    result['subscription'] = {'status':'unavailable'}
    try:
        from instagram_runtime import build_runtime
        from instagram_token_vault import TokenBinding
        from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
        from urllib.error import HTTPError
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        runtime = build_runtime()
        with connect() as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            conn.execute("SET LOCAL statement_timeout='5s'")
            rows = conn.execute("SELECT id,external_account_id,encrypted_token FROM socialmei.ig_meta_connections WHERE workspace_id=1 AND status='connected' AND expires_at>NOW() AND scopes @> ARRAY['instagram_business_basic','instagram_business_manage_messages']::text[] ORDER BY created_at DESC,id DESC LIMIT 2").fetchall()
        if len(rows) != 1 or runtime.oauth is None:
            raise ValueError('Ambiguous or unavailable account')
        row = rows[0]
        account = row[1]
        version = os.getenv('SOCIALMEI_INSTAGRAM_GRAPH_VERSION','')
        app_id = options.get('meta_app_id') or os.getenv('SOCIALMEI_INSTAGRAM_CLIENT_ID','')
        if not re.fullmatch(r'[0-9]{1,40}',account) or not re.fullmatch(r'v[1-9][0-9]{0,2}\.0',version) or not re.fullmatch(r'[0-9]{1,40}',app_id):
            raise ValueError('Invalid provider configuration')
        token = runtime.oauth.vault.open(row[2],TokenBinding(1,row[0],account))
        request = Request('https://graph.instagram.com/'+version+'/'+account+'/subscribed_apps', headers={'Authorization':'Bearer '+token},method='GET')
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=12) as response:
            raw = response.read(65537)
        if len(raw)>65536:
            raise ValueError('Response too large')
        payload = json.loads(raw)
        data = payload.get('data')
        if not isinstance(data,list) or len(data)>100 or not all(isinstance(item,dict) for item in data):
            raise ValueError('Invalid response')
        matching = [item for item in data if item.get('id')==app_id]
        if len(matching)>1 or (payload.get('paging') or {}).get('next'):
            raise ValueError('Incomplete response')
        fields = matching[0].get('subscribed_fields') if matching else None
        result['subscription'] = {'status':'read_confirmed','app_listed':bool(matching),'messages_subscribed':isinstance(fields,list) and 'messages' in fields,'fields_available':isinstance(fields,list),'listed_apps':len(data),'any_app_has_messages':any(isinstance(item.get('subscribed_fields'),list) and 'messages' in item['subscribed_fields'] for item in data)}
    except HTTPError as error:
        result['subscription'] = {'status':'provider_refused','http_status':error.code}
    except Exception:
        pass
print(json.dumps(result))
'''


def run(args, data=None):
    result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Consulta indisponível; detalhes privados omitidos.")
    return result.stdout


def marker_status(counts):
    keys = {"total_messages", "team_messages", "other_workspace_messages",
            "linked_events", "linked_messages", "linked_conversations"}
    if not isinstance(counts, dict) or set(counts) != keys:
        raise ValueError("Contagens inválidas.")
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError("Contagens inválidas.")
    if not any(counts.values()):
        return "not_observed"
    if counts == {key: (0 if key == "other_workspace_messages" else 1) for key in keys}:
        return "one_persisted_inbound_message"
    return "requires_investigation"


def inspect(expected_sha, marker=None, check_subscription=False, meta_app_id=None):
    if not SHA.fullmatch(expected_sha) or (marker is not None and not MARKER.fullmatch(marker)):
        raise ValueError("SHA ou marcador inválido.")
    if meta_app_id is not None and not re.fullmatch(r"[0-9]{1,40}", meta_app_id):
        raise ValueError("ID público do aplicativo inválido.")
    container = json.loads(run(["docker", "inspect", API]))[0]
    image = json.loads(run(["docker", "image", "inspect", container["Image"]]))[0]
    revision = (image.get("Config", {}).get("Labels") or {}).get("org.opencontainers.image.revision")
    if revision != expected_sha:
        raise ValueError("Revisão instalada difere do alvo; inspeção interrompida.")
    env = dict(item.split("=", 1) for item in container.get("Config", {}).get("Env", []) if "=" in item)
    database = json.loads(run(["docker", "exec", "-i", API, "python", "-c", CHILD], json.dumps({"marker": marker, "check_subscription": check_subscription, "meta_app_id": meta_app_id})))
    # Explicit allowlist: never forward child output or private values wholesale.
    result = {"mode": "read_only", "runtime_sha": revision, "workspace_id": 1,
              "messages_sent": False, "runtime_changed": False,
              "account_subscription_verified": False, "app_callback_verified": False,
              "site_display_verified": False,
              "signed_delivery_verified": False,
              "ingress_enabled": env.get("SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED") == "true",
              "dashboard_send_enabled": env.get("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED") == "true"}
    for key in ("connected_with_messaging_scopes", "events", "processed_message_events", "inbox_messages"):
        value = database[key]
        if type(value) is not int or value < 0:
            raise ValueError("Contagem inválida.")
        result[key] = value
    if marker:
        result["marker_status"] = marker_status(database.get("marker"))
        result["marker_counts"] = database["marker"]
    else:
        result["marker_status"] = "not_requested"
    if check_subscription:
        subscription = database.get("subscription", {})
        status = subscription.get("status")
        if status not in {"read_confirmed", "provider_refused", "unavailable"}:
            raise ValueError("Estado de inscrição inválido.")
        result["account_subscription"] = {"status": status}
        if status == "read_confirmed":
            for key in ("app_listed", "messages_subscribed", "fields_available", "any_app_has_messages"):
                if type(subscription.get(key)) is not bool:
                    raise ValueError("Inscrição inválida.")
                result["account_subscription"][key] = subscription[key]
            listed_apps = subscription.get("listed_apps")
            if type(listed_apps) is not int or not 0 <= listed_apps <= 100:
                raise ValueError("Contagem de aplicativos inválida.")
            result["account_subscription"]["listed_apps"] = listed_apps
            result["account_subscription"]["identity_basis"] = "explicit_meta_app_id" if meta_app_id else "oauth_client_only"
            result["account_subscription_verified"] = meta_app_id is not None and all(subscription[key] for key in (
                "app_listed", "messages_subscribed", "fields_available"))
        elif status == "provider_refused":
            code = subscription.get("http_status")
            if type(code) is not int or not 300 <= code <= 599:
                raise ValueError("Status HTTP inválido.")
            result["account_subscription"]["http_status"] = code
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=["team"])
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--marker", help="Exact text of ONE authorized manual test; no contact identifiers.")
    parser.add_argument("--check-subscription", action="store_true", help="Read the account subscription with ONE Meta GET; never modifies it.")
    parser.add_argument("--meta-app-id", help="Public parent Meta App ID verified in the developer dashboard; may differ from the Instagram OAuth client.")
    args = parser.parse_args()
    try:
        result = inspect(args.expected_sha, args.marker, args.check_subscription, args.meta_app_id)
    except Exception:
        print(json.dumps({"mode": "read_only", "status": "inspection_unavailable", "runtime_changed": False}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
