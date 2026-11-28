"""Run the existing observer and candidate queue contracts without external egress."""

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile


SPEC = importlib.util.spec_from_file_location("rehearse_rollback", Path(__file__).with_name("rehearse-8-0-rollback.py"))
rollback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rollback)
docker, wait = rollback.docker, rollback.wait
OBSERVER = "sha256:fad45c4a9f644f51b694dd9799cea857bcb1eb77caf1bee02554a530a0d48636"
CERTIFICATE = """
from datetime import datetime, timedelta, timezone
import json
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'db')])
now = datetime.now(timezone.utc)
certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
    .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
    .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),True)
    .add_extension(x509.SubjectAlternativeName([x509.DNSName('db')]),False).sign(key,hashes.SHA256()))
print(json.dumps([certificate.public_bytes(serialization.Encoding.PEM).decode(),
    key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                      serialization.NoEncryption()).decode()]))
"""
SEED = """
INSERT INTO socialmei.workspaces(id,slug,nome) VALUES (60,'observer-60','Fixture 60'),(61,'observer-61','Fixture 61');
INSERT INTO socialmei.ig_meta_connections(id,workspace_id,external_account_id,account_type,status,scopes,
    encrypted_token,token_kind,issued_at,expires_at)
SELECT gen_random_uuid(), id, id::text, 'BUSINESS','connected',
    ARRAY['instagram_business_basic','instagram_business_manage_messages'], 'fixture', 'long',
    now(), now()+INTERVAL '1 day'
FROM socialmei.workspaces WHERE id IN (60,61);
INSERT INTO socialmei.me_conversations(workspace_id,channel,account_ref,contact_ref,contact_name,origin)
VALUES (60,'instagram','instagram:60','instagram:100','Fixture','instagram'),
       (61,'instagram','instagram:61','instagram:100','Fixture','instagram');
INSERT INTO socialmei.me_messages(workspace_id,conversation_id,external_message_id,fingerprint,conversation_revision,text,origin)
SELECT workspace_id,id,'fixture:'||workspace_id,repeat('a',64),1,'Fixture Direct','instagram'
FROM socialmei.me_conversations WHERE workspace_id IN (60,61);
INSERT INTO socialmei.ig_meta_ingress_events(external_account_id,event_key,workspace_id,connection_id,
    kind,fingerprint,status,message_id)
SELECT c.external_account_id,repeat('b',64),c.workspace_id,c.id,'message', repeat('a',64),'processed',m.id
FROM socialmei.ig_meta_connections c JOIN socialmei.me_messages m ON c.workspace_id=m.workspace_id;
"""


EDGE = """
import hashlib, hmac, json, os, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from waha_durable_receiver import DurableReceiver, Rejected
from waha_durable_service import load_binding

now = int(time.time())
os.environ['WAHA_INGRESS_AFTER'] = str(now-5)
binding = dict(workspace_id=60,channel_id=3,revision=2,ingress_after=now-5,session='01',
               engine='GOWS',instance='socialmei-equipe-piloto',account_id='105976@c.us',
               hmac_key='detached-fixture-not-a-provider-key')
with tempfile.TemporaryDirectory() as temporary:
    directory = Path(temporary)
    reg = directory/'registry.json'
    reg.write_text(json.dumps({'version':1,'bindings':[binding]}))
    reg.chmod(0o644)
    try:
        load_binding(reg)
    except ValueError as error:
        assert str(error)=='registry_not_private'
    else:
        raise AssertionError('unsafe registry accepted')
    reg.chmod(0o400)
    received = load_binding(reg)
    store = directory/'spool'
    receiver = DurableReceiver(store,received)
    raw = json.dumps(dict(session='01', engine='GOWS', event='message', me={'id':binding['account_id']},
                          payload={'timestamp':now,'id':'fixture-1'})).encode()
    sig = hmac.new(binding['hmac_key'].encode(),raw,hashlib.sha512).hexdigest()
    try:
        receiver.accept(raw,'0'*128,'sha512')
    except Rejected:
        pass
    else:
        raise AssertionError('signature accepted')
    with ThreadPoolExecutor(4) as executor:
        keys = list(executor.map(lambda _: receiver.accept(raw,sig,'sha512'),range(4)))
    assert len(set(keys))==1 and receiver.counts()=={'pending':1}
    assert receiver.deliver_one(lambda *_: (503,{}),now=now+1)
    assert receiver.counts()=={'pending':1}
    restarted = DurableReceiver(store,received)
    calls = []
    def recovered(body, signature, algorithm):
        calls.append((body,signature,algorithm))
        return 200,dict(processed=0,ignored=0,duplicates=1)
    assert restarted.deliver_one(recovered,now=now+3)
    assert not restarted.deliver_one(recovered,now=now+10)
    assert calls==[(raw,sig,'sha512')] and restarted.counts()=={'delivered':1}
print('Edge: private registry, signed intake, concurrent deduplication, persisted retry and receipt')

"""


class Lab(rollback.Lab):
    def observer(self, service, workspace, state, start, role="observer"):
        name = self.name + "-" + service
        self.containers.append(name)
        url = f"postgresql://{role}:{self.password}@db/postgres?sslmode=verify-full&sslrootcert=/run/database-ca.crt"
        env = {
            "DATABASE_URL": url,
            "SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME": "postgres",
            "SOCIALMEI_INSTAGRAM_WORKER_MODE": "observe",
            "SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID": str(workspace),
            "SOCIALMEI_INSTAGRAM_AUTO_MENU_START_UTC": start,
            "SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED": "false",
            "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        args = [item for key, value in env.items() for item in ("-e", f"{key}={value}")]
        docker("run", "-d", "--pull=never", "--name", name, "--network", self.name,
               "--read-only", "--tmpfs", "/tmp:size=8m", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--memory", "72m", "--memory-swap", "72m",
               "--pids-limit", "64", "--volume", f"{state}:/run/socialmei/instagram-menu-state",
               "--mount", f"type=bind,source={self.private/'ca.crt'},target=/run/database-ca.crt,readonly",
               *args, OBSERVER, "python", "-u", "/app/instagram-auto-menu-worker.py")
        return name

    def check_observer(self, name, workspace):
        wait(lambda: docker("exec", name, "python", "-m", "instagram_worker_health", check=False))
        data = json.loads(docker("exec", name, "cat", "/run/socialmei/instagram-menu-state/state.json").stdout)
        assert data["workspace_id"] == workspace and data["pending_count"] == 1
        assert data["send_enabled"] is False and data["in_flight"] is False
        return data

    def run(self):
        self.images = rollback.IMAGES
        docker("network", "create", "--internal", "--subnet", "10.223.215.0/24", self.name)
        assert docker("network", "inspect", "-f", "{{.Internal}}", self.name).stdout.strip() == "true"
        start = (datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        self.start("db", "db", (("POSTGRES_PASSWORD", self.password),))
        db_name = self.name + "-db"
        wait(lambda: docker("exec", db_name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", check=False))
        certificate, key = json.loads(docker("run", "--rm", "-i", "--network", "none", "--entrypoint",
                                              "python", self.images["api"], "-", stdin=CERTIFICATE).stdout)
        (self.private/"ca.crt").write_bytes(certificate.encode())
        docker("exec", "-i", db_name, "sh", "-ec",
               'umask 077; cat > "$PGDATA/server.key"; chown postgres "$PGDATA/server.key"', stdin=key)
        docker("exec", "-i", db_name, "sh", "-ec",
               'cat > "$PGDATA/server.crt"; chown postgres "$PGDATA/server.crt"', stdin=certificate)
        self.db("ALTER SYSTEM SET ssl='on';")
        self.db("SELECT pg_reload_conf();")
        self.db("CREATE SCHEMA socialmei; CREATE TABLE socialmei.schema_migrations "
                "(version text PRIMARY KEY, applied_at timestamptz DEFAULT now());")
        self.apply(sorted((rollback.ROOT/"database/migrations").glob("*.sql"))[:57])
        self.db(SEED)
        for role in ("observer", "observer_legacy"):
            self.db(f"CREATE ROLE {role} LOGIN PASSWORD '{self.password}'; "
                    f"GRANT USAGE ON SCHEMA socialmei TO {role}; "
                    "GRANT SELECT ON socialmei.me_messages,socialmei.ig_meta_connections,"
                    f"socialmei.ig_meta_ingress_events,socialmei.ig_menu_replies TO {role};")
        volumes = []
        try:
            for suffix in ("state60", "state61", "duplicate", "legacy"):
                name = self.name + "-" + suffix
                docker("volume", "create", name)
                volumes.append(name)
            first = self.observer("obs60", 60, volumes[0], start)
            second = self.observer("obs61", 61, volumes[1], start)
            before = self.check_observer(first, 60)
            other = self.check_observer(second, 61)
            assert before["latest_pending_message_id"] != other["latest_pending_message_id"]
            assert self.db("SELECT count(*) FROM pg_stat_activity a JOIN pg_stat_ssl s USING(pid) "
                           "WHERE a.usename='observer' AND s.ssl;").stdout.strip() == "2"
            duplicate = self.observer("obsduplicate", 60, volumes[2], start)
            assert docker("wait", duplicate).stdout.strip() == "1"
            log = docker("logs", duplicate)
            output = log.stdout + log.stderr
            assert "INSTAGRAM_MENU_STARTUP_BLOCKED RuntimeError" in output, "duplicate observer did not fail closed"
            docker("restart", first)
            assert self.check_observer(first, 60) == before
            self.db("ALTER ROLE observer_legacy NOLOGIN;")
            legacy = self.observer("obslegacy", 60, volumes[3], start, role="observer_legacy")
            assert docker("wait", legacy).stdout.strip() == "1"
            denial = docker("exec", "-e", "PGPASSWORD="+self.password, db_name, "psql", "-h", "127.0.0.1",
                            "-U", "observer_legacy", "-d", "postgres", "-c", "SELECT 1", check=False)
            assert denial.returncode != 0 and "not permitted to log in" in denial.stderr
            assert self.db("SELECT count(*) FROM socialmei.ig_menu_replies;").stdout.strip() == "0"
            print("Observers: TLS verify-full, scoped counts, exclusive lease, restart, legacy denial, zero sends")
            edge()
        finally:
            self.close()
            for volume in volumes:
                docker("volume", "rm", volume, check=False)


def edge():
    result = docker("run", "--rm", "--pull=never", "-i", "--network", "none", "--entrypoint",
                    "python", rollback.IMAGES["edge"], "-", stdin=EDGE)
    print(result.stdout.strip())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-only", action="store_true")
    if parser.parse_args().edge_only:
        edge()
        raise SystemExit(0)
    with tempfile.TemporaryDirectory(prefix="socialmei80-workers-") as directory:
        lab = Lab(Path(directory))
        try:
            lab.run()
        except subprocess.CalledProcessError as error:
            raise SystemExit((error.stderr or "Docker step failed").replace(lab.password, "[synthetic]")) from None
        finally:
            lab.close()
