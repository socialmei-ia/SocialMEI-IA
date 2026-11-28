"""Rehearse the 8.0 rollback against disposable Postgres, without external egress."""

import json
import re
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://rollback.example.test"
IMAGES = {
    "legacy_api": "sha256:051cda78a17f23da42244e9db827d0c248be2395b5c95ac31da1689f484b58ea",
    "legacy_gateway": "sha256:b567a72a6f2c8e801456a196eeaacc5c148ac94eb1e8188f96d91017d82116cb",
    "legacy_menu": "sha256:d7f83bd9449c2d172ed7742df351b638319a16f83c5fe600fb2ba9694dc1f889",
    "api": "sha256:92eefdb2f8a7cec7b69341fc48d01c39808feae9ff46e712834a1574a02b8374",
    "gateway": "sha256:5c0a593957309d1e0b920ae086725971abffbc9767e71419f0c93c7035ed296e",
    "menu": "sha256:ecf7c82f5b1ee1440d9ccc27b4d3f28d94a76277d7a0200cdb3489600f946db1",
    "worker": "sha256:aaed81c235fedb2693dd5f53ab15dd40fce02d2e8d3ab219450cc2727e234c2b",
    "instagram": "sha256:696a6b3717a8932ce0231b55ee5e33b2b98fd5413fea1a0793bd21b865960f1a",
    "edge": "sha256:0dce4dbfdf56700bcc512ecaa375a0f7076d7dda59d16f0ef79988565acd46c3",
    "db": "sha256:526f86d93c6ea08fd3f1fe5605650cacc781b2c6013169a0ad8f42c7d3d84f32",
}
AFFECTED = ("schema_migrations", "crm_vendas", "crm_venda_operacoes", "crm_financeiro",
            "crm_financeiro_liquidacoes", "stock_movements")
DRIVER = r"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from http.cookies import SimpleCookie
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

origin = 'https://rollback.example.test'
def call(path, method='GET', data=None, identity=None):
    headers = {'Origin': origin, 'X-SocialMEI-Client': 'browser', 'Content-Type': 'application/json'}
    if identity:
        headers.update(Cookie=identity[0])
        headers['X-SocialMEI-CSRF'] = identity[1]
    req = Request('http://gateway' + path, headers=headers, method=method,
                  data=None if data is None else json.dumps(data).encode())
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw
        return response.status, body, response.headers

if sys.argv[1] == 'probe':
    assert call('/health/db')[0] == 200, 'database readiness'
    assert call('/socialmei-app.html')[0] == 200, 'frontend readiness'
    assert call('/config.js')[0] == 200, 'readonly browser config mount'
    if sys.argv[2] == 'candidate':
        assert b'Hor' in call('/scripts/agenda-hours.js')[1], 'agenda asset'
    # The menu is deliberately not configured for external dispatch.
    with urlopen('http://menu:8000/health', timeout=5) as response:
        assert response.status == 200
    sys.exit(0)
if sys.argv[1] == 'fenced':
    for path, method in (('/health/db','GET'), ('/api/v1/vendas','POST'),
                         ('/api/v1/financeiro/42/pagar','POST'), ('/internal/test','POST')):
        assert call(path, method, {})[0] == 503, 'maintenance must fail closed'
    sys.exit(0)

def register(name):
    status, body, headers = call('/api/v1/auth/register', 'POST', {
        'nome': 'Synthetic ' + name, 'email': name + '@example.test', 'senha': 'Strong-synthetic-9!'
    })
    assert status == 201, ('register', status)
    cookies = SimpleCookie(headers['Set-Cookie'])
    name = '__Host-socialmei-session'
    return (name + '=' + cookies[name].value, body['csrf_token'])

identity = register('rollback')
other = register('other')
today = date.today().isoformat()
status, product, _ = call('/api/v1/produtos', 'POST', {'nome':'Synthetic', 'preco':'10.00','estoque':5}, identity)
assert status == 201, ('product', status)
draft = {'operation_id': str(uuid4()), 'produto_id': product['id'], 'quantidade': 3,
         'preco':'10.00','data':today}
def sale_once(_):
    status, sale, _ = call('/api/v1/vendas', 'POST', draft, identity)
    assert status == 201, ('sale', status)
    return sale['id']
with ThreadPoolExecutor(max_workers=2) as pool:
    first, second = pool.map(sale_once, [0,1])
assert first == second
status, item, _ = call('/api/v1/financeiro/de-venda/' + str(first), 'POST',
                       {'operation_id': str(uuid4()), 'expected_version':1, 'vencimento':today}, identity)
assert status == 201, ('receivable', status)
path = '/api/v1/financeiro/' + str(item['id'])
operation = {'operation_id':str(uuid4()), 'expected_version':1, 'valor':'12.00', 'data':today}
for _ in range(2):
    assert call(path+'/liquidacoes', 'POST', operation, identity)[0] == 200, 'settlement'
assert call(path+'/liquidacoes', identity=other)[0] == 404, 'tenant scope'
print('HTTP: concurrent sale replay, linked receivable, partial receipt replay and tenant isolation')
"""


def docker(*args, stdin=None, check=True):
    return subprocess.run(["docker", *args], input=stdin, text=True, encoding="utf-8",
                          capture_output=True, check=check, timeout=90)


def wait(probe):
    for _ in range(32):
        result = probe()
        if result.returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError("isolated service did not pass readiness: " + result.stderr[-700:])


class Lab:
    def __init__(self, private):
        self.name = "socialmei80-" + secrets.token_hex(5)
        self.private = private
        self.containers = []
        self.images = {}
        self.password = secrets.token_urlsafe(24)
        self.gateway = private / "Caddyfile"
        self.gateway.write_text(":80 {\n reverse_proxy /api/* api:8000\n reverse_proxy /internal/* api:8000\n"
                                " reverse_proxy /health* api:8000\n root * /srv/frontend\n file_server\n}\n")

    def start(self, service, variant, env=(), mounts=(), entrypoint=None, command=()):
        name = self.name + "-" + service
        self.containers.append(name)
        args = ["run", "-d", "--pull=never", "--name", name, "--network", self.name, "--network-alias", service]
        for key, value in env:
            args.extend(("-e", f"{key}={value}"))
        for source, target in mounts:
            args.extend(("--mount", f"type=bind,source={source},target={target},readonly"))
        if entrypoint:
            args.extend(("--entrypoint", entrypoint))
        docker(*args, self.images[variant], *command)

    def db(self, sql, *, check=True):
        return docker("exec", "-i", self.name + "-db", "psql", "-XqAt", "-U", "postgres",
                      "-v", "ON_ERROR_STOP=1", stdin=sql, check=check)

    def driver(self, mode, variant="", *, check=True):
        return docker("run", "--rm", "--pull=never", "-i", "--network", self.name, "--entrypoint",
                      "python", self.images["api"], "-", mode, variant, stdin=DRIVER, check=check)

    def stop_app(self):
        for service in ("gateway", "api", "menu"):
            name = self.name + "-" + service
            if name in self.containers:
                docker("rm", "-fv", name)
                self.containers.remove(name)

    def app(self, variant):
        role = "candidate" if variant == "" else "legacy"
        env = (("DATABASE_URL", f"postgresql://{role}:{self.password}@db/postgres"),
               ("SOCIALMEI_SHARED_DATA_ENABLED", "true"), ("SOCIALMEI_AUTH_ENABLED", "true"),
               ("SOCIALMEI_AUTH_ORIGIN", ORIGIN), ("SOCIALMEI_REGISTRATION_MODE", "open"))
        for service in ("api", "menu"):
            mounts = [(self.private / "booking", "/app/.socialmei-booking-signing.private")]
            if service == "api":
                mounts.append((self.private / "gows", "/app/.human-gows-key.private"))
            self.start(service, variant+service, env, mounts, "python",
                       ("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"))
        self.start("gateway", variant+"gateway", mounts=((self.gateway, "/etc/caddy/Caddyfile"),
                   (self.private/"config.js", "/srv/frontend/config.js")))
        try:
            wait(lambda: self.driver("probe", role, check=False))
        except RuntimeError:
            for service in ("api", "menu", "gateway"):
                result = docker("logs", "--tail", "5", self.name + "-" + service, check=False)
                print(service, (result.stdout+result.stderr).replace(self.password, "[synthetic]"))
            raise

    def apply(self, files):
        for file in files:
            number = file.stem.split("_")[0]
            assert re.fullmatch(r"\d{3}", number)
            self.db("BEGIN;\n" + file.read_text(encoding="utf-8") +
                    f"\nINSERT INTO socialmei.schema_migrations(version) VALUES('{file.name}');\nCOMMIT;")

    def snapshot(self):
        tables = []
        for name in AFFECTED:
            tables.append("SELECT md5(coalesce(string_agg(row::text, E'\\n' ORDER BY row::text),'')) "
                          f"FROM socialmei.{name} row;")
        return self.db("\n".join(tables)).stdout

    def run(self):
        for name, tag in IMAGES.items():
            resolved = docker("image", "inspect", "--format", "{{.Id}}", tag).stdout.strip()
            if resolved != tag:
                raise RuntimeError(f"unexpected local image identity for {name}")
            self.images[name] = resolved
        docker("network", "create", "--internal", "--subnet", "10.223.214.0/24", self.name)
        self.start("db", "db", (("POSTGRES_PASSWORD", self.password),))
        wait(lambda: docker("exec", self.name+"-db", "pg_isready", "-h", "127.0.0.1", "-U", "postgres", check=False))
        self.db("CREATE SCHEMA socialmei; CREATE TABLE socialmei.schema_migrations "
                "(version text PRIMARY KEY, applied_at timestamptz DEFAULT now());")
        files = sorted((ROOT/"database/migrations").glob("*.sql"))[:57]
        assert len(files) == 57 and files[-1].name.startswith("057_")
        self.apply(files[:46])
        for role in ("legacy", "candidate"):
            self.db(f"CREATE ROLE {role} LOGIN PASSWORD '{self.password}'; "
                    f"GRANT USAGE ON SCHEMA socialmei TO {role}; ALTER DEFAULT PRIVILEGES IN SCHEMA socialmei "
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}; ALTER DEFAULT PRIVILEGES IN SCHEMA socialmei "
                    f"GRANT USAGE, SELECT ON SEQUENCES TO {role}; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA "
                    f"socialmei TO {role}; GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA socialmei TO {role};")
        for role in ("worker", "instagram", "edge"):
            self.start(role, role, entrypoint="python", command=("-c", "import time; time.sleep(600)"))

        self.app("legacy_")
        self.stop_app()
        self.apply(files[46:])
        self.app("")
        before = self.snapshot()
        self.stop_app()
        self.app("legacy_")
        assert self.snapshot() == before, "promotion without writes changed business state"
        print("Pre-write rollback: API, gateway and menu healthy on schema 057")
        self.stop_app()
        self.app("")
        print(self.driver("write").stdout.strip())
        proof = self.db("""
            SELECT count(*)=1 AND bool_and(q.valor=12 AND f.liquidado_parcial=12
                AND f.venda_id=v.id AND v.quantidade=3 AND p.estoque=2
                AND st.previous_stock=5 AND st.current_stock=2)
            FROM socialmei.crm_financeiro_liquidacoes q
            JOIN socialmei.crm_financeiro f ON (f.workspace_id,f.id)=(q.workspace_id,q.lancamento_id)
            JOIN socialmei.crm_vendas v ON (v.workspace_id,v.id)=(f.workspace_id,f.venda_id)
            JOIN socialmei.crm_produtos p ON (p.workspace_id,p.id)=(v.workspace_id,v.produto_id)
            JOIN socialmei.stock_movements st ON (st.workspace_id,st.sale_id)=(v.workspace_id,v.id);
        """)
        assert proof.stdout.strip()=="t", "receivable, partial amount or stock movement diverged"
        assert self.db("SELECT count(*) FROM socialmei.schema_migrations").stdout.strip()=="57"
        saved = self.snapshot()
        assert saved != before
        self.stop_app()
        self.db("ALTER ROLE legacy NOLOGIN; SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE usename='legacy' AND pid<>pg_backend_pid();")
        refusal = docker("exec", "-e", "PGPASSWORD="+self.password, self.name+"-db", "psql", "-h",
                         "127.0.0.1", "-U", "legacy", "-d", "postgres", "-c", "SELECT 1", check=False)
        assert refusal.returncode != 0 and "not permitted to log in" in refusal.stderr
        self.gateway.write_text(":80 {\n respond 503\n}\n")
        self.start("gateway", "legacy_gateway", mounts=((self.gateway, "/etc/caddy/Caddyfile"),))
        wait(lambda: self.driver("fenced", check=False))
        assert self.snapshot() == saved, "maintenance changed protected state"
        self.stop_app()
        self.gateway.write_text(":80 {\n reverse_proxy /api/* api:8000\n reverse_proxy /health* api:8000\n"
                                " root * /srv/frontend\n file_server\n}\n")
        self.app("")
        assert self.snapshot() == saved, "compatible recovery changed protected state"
        print("Post-write rollback: legacy role denied; maintenance returned 503; compatible recovery preserved records and ledger")

    def close(self):
        for name in reversed(self.containers):
            docker("rm", "-fv", name, check=False)
        docker("network", "rm", self.name, check=False)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="socialmei80-") as directory:
        private = Path(directory)
        for name in ("gows", "booking"):
            (private/name).write_text(secrets.token_urlsafe(40))
        (private/"config.js").write_text("// isolated rollback fixture\n")
        lab = Lab(private)
        try:
            lab.run()
        except subprocess.CalledProcessError as error:
            raise SystemExit((error.stderr or "Docker step failed").replace(lab.password, "[synthetic]")) from None
        finally:
            lab.close()
