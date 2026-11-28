"""Exercise the frozen dispatcher and real menu over a private Docker network."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

spec = importlib.util.spec_from_file_location("rollback", Path(__file__).with_name("rehearse-8-0-rollback.py"))
rollback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollback)
docker, wait = rollback.docker, rollback.wait
MENU = "socialmei-menu-public-api-v3"
WAHA = "socialmei-waha-gows-piloto"
INSTANCE = "dispatch-lab"
ACCOUNT = "111@c.us"
KEY = "synthetic-fixture-hmac-for-dispatcher"
FAKE_WAHA = """
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
auth = Path('/run/secrets/waha').read_text().strip()
mode = Path('/tmp/lab-mode')
log = Path('/tmp/lab-count')
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def answer(self,status,data):
        self.send_response(status); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    def do_GET(self):
        if self.path=='/health': return self.answer(200,{})
        if self.headers.get('X-Api-Key')!=auth: return self.answer(401,{})
        if mode.exists() and mode.read_text().strip()=='unavailable': return self.answer(503,{})
        if self.path=='/api/version': return self.answer(200,{'engine':'GOWS'})
        if self.path=='/api/sessions/01':
            return self.answer(200,{'name':'01','status':'WORKING','me':{'id':'111@c.us'}})
        return self.answer(404,{})
    def do_POST(self):
        if self.headers.get('X-Api-Key')!=auth: return self.answer(401,{})
        if self.path not in ('/api/sendText','/api/sendList'): return self.answer(404,{})
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if body.get('chatId') not in ('222@c.us','333@c.us') or body.get('session')!='01':
            return self.answer(400,{})
        count=int(log.read_text())+1 if log.exists() else 1
        log.write_text(str(count))
        if mode.exists() and mode.read_text().strip()=='uncertain': return self.answer(200,{})
        return self.answer(200,{'id':'local-receipt-'+str(count)})
HTTPServer(('0.0.0.0',3000),Handler).serve_forever()
"""
INGRESS = """
import hmac,json,os,sys,time
from lab_ingress import WahaBinding, WahaIngressService
contact, mid, workspace, channel = sys.argv[1:]
instance='dispatch-lab' if workspace=='60' else 'dispatch-other'
account='111@c.us' if workspace=='60' else '444@c.us'
key='synthetic-fixture-hmac-for-dispatcher'
service=WahaIngressService({instance:WahaBinding(instance=instance,session='01',account_id=account,
    workspace_id=int(workspace),channel_id=int(channel),hmac_key=key,engine='GOWS')})
now=int(time.time())
body=json.dumps({'event':'message','id':mid,'timestamp':now*1000,'session':'01','engine':'GOWS',
    'me':{'id':account},'payload':{'id':mid,'timestamp':now,'from':contact,'to':account,
    'fromMe':False,'hasMedia':False,'type':'chat','body':'0'}}).encode()
sig=hmac.digest(key.encode(),body,'sha512').hex()
assert service.receive(instance,body,sig,'sha512')['processed']==1
assert service.receive(instance,body,sig,'sha512')['duplicates']==1
"""
HTTP_CHECK = """
from urllib.request import urlopen
from urllib.error import HTTPError
import sys
try:
    with urlopen(sys.argv[1],timeout=3) as res: actual=res.status
except HTTPError as err: actual=err.code
assert actual==int(sys.argv[2]),actual
"""


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


class Lab(rollback.Lab):
    def inside(self, role, script, *args, check=True):
        return docker("run", "--rm", "--pull=never", "-i", "--network", self.name, "--entrypoint",
                      "python", self.images[role], "-", *args, stdin=script, check=check)

    def fixture(self, contact, mid, workspace=60, channel=3):
        docker("exec", "-i", "-e", "SOCIALMEI_WAHA_INGRESS_MODE=isolated", "-e",
               "SOCIALMEI_WAHA_LAB_ENVIRONMENT=isolated", self.name+"-"+MENU,
               "python", "-", contact, mid, str(workspace), str(channel), stdin=INGRESS)
        self.db("UPDATE socialmei.crm_eventos_canal SET recebido_em=now()-INTERVAL '5 seconds';")

    def mode(self, value):
        docker("exec", "-i", self.name+"-"+WAHA, "sh", "-c", "cat > /tmp/lab-mode", stdin=value)

    def dispatch_env(self, secret="menu"):
        env = {
            "SOCIALMEI_MENU_SENDER_ACTIVE":"YES", "SOCIALMEI_PUBLIC_MENU_EXPLICIT_ENABLE":"YES",
            "SOCIALMEI_MENU_PUBLIC_INBOUND_ACTIVE":"YES",
            "SOCIALMEI_MENU_INSTANCE":INSTANCE, "SOCIALMEI_MENU_SESSION":"01",
            "SOCIALMEI_MENU_ACCOUNT":ACCOUNT, "SOCIALMEI_MENU_WAHA_ENGINE":"GOWS",
            "SOCIALMEI_MENU_API_URL":f"http://{MENU}:8019", "SOCIALMEI_MENU_WAHA_URL":f"http://{WAHA}:3000",
            "SOCIALMEI_MENU_TOKEN_FILE":"/run/secrets/"+secret,
            "SOCIALMEI_MENU_WAHA_KEY_FILE":"/run/secrets/waha",
        }
        return [item for key, value in env.items() for item in ("-e", f"{key}={value}")]

    def dispatch(self, expected, status=0, secret="menu"):
        result = docker("run", "--rm", "--pull=never", "--network", self.name, "--entrypoint",
                        "python", "-v", self.volume+":/run/secrets:ro", *self.dispatch_env(secret),
                        self.images["worker"], "/app/public_worker.py", "--run-once", check=False)
        if result.returncode != status or expected not in result.stdout:
            log=docker("logs","--tail","13",self.name+"-"+MENU,check=False)
            print((log.stdout+log.stderr).replace(self.password,"[synthetic]"))
            raise AssertionError((result.returncode,result.stdout[-300:]))

    def start_guard(self, role, cutoff):
        name = self.name + "-" + role
        docker("run", "-d", "--pull=never", "--name", name, "--network", self.name,
               "--entrypoint", "python", "-v", self.volume + ":/run/secrets:ro",
               "-v", self.state_volume + ":/run/socialmei/continuous-state",
               "-e", "SOCIALMEI_CONTINUOUS_START_UTC=" + cutoff, *self.dispatch_env(),
               self.images["worker"], "/app/continuous_guard.py")
        self.containers.append(name)
        return name

    def journal_matches(self, name, field, expected):
        outcome = docker("exec", name, "python", "-c",
                         "import json,sys; state=json.load(open('/run/socialmei/continuous-state/state.json')); "
                         "assert state.get(sys.argv[1]) == json.loads(sys.argv[2]) and not state['in_flight']",
                         field, json.dumps(expected), check=False)
        return outcome

    def run(self):
        self.images = {**rollback.IMAGES, "menu": "sha256:7d3467523deed357b6d9069193f0d6d85c424f4290835e48d98c098e32676f59"}
        docker("network", "create", "--internal", "--subnet", "10.223.216.0/24", self.name)
        assert docker("network", "inspect", "-f", "{{.Internal}}", self.name).stdout.strip() == "true"
        self.start("db","db", (("POSTGRES_PASSWORD",self.password),))
        wait(lambda:docker("exec",self.name+"-db","pg_isready","-h","127.0.0.1","-U","postgres",check=False))
        self.db("CREATE SCHEMA socialmei; CREATE TABLE socialmei.schema_migrations(version text PRIMARY KEY);")
        self.apply(sorted((rollback.ROOT/"database/migrations").glob("*.sql"))[:59])
        token, waha, stale = (secrets.token_hex(32) for _ in range(3))
        self.db(f"""
            CREATE ROLE dispatch_menu LOGIN PASSWORD '{self.password}';
            GRANT USAGE ON SCHEMA socialmei TO dispatch_menu;
            GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA socialmei TO dispatch_menu;
            GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA socialmei TO dispatch_menu;
            INSERT INTO socialmei.workspaces(id,slug,nome) VALUES(60,'dispatch-test','Fixture'),(61,'dispatch-other','Other');
            INSERT INTO socialmei.crm_canais(id,workspace_id,instancia,sessao,identificador_conta,ativo,ingress_provisioned)
            VALUES(3,60,'{INSTANCE}','01','{ACCOUNT}',true,true),(4,61,'dispatch-other','01','444@c.us',true,true);
            INSERT INTO socialmei.wa_bot_access(workspace_id,channel_id,token_hash,binding_hash)
            VALUES(60,3,'{hashlib.sha256(token.encode()).hexdigest()}','{digest([60,3,INSTANCE,"01",ACCOUNT,1])}');
        """)
        self.volume = self.name+"-secrets"
        self.state_volume = self.name + "-journal"
        docker("volume","create",self.volume)
        docker("volume", "create", self.state_volume)
        try:
            docker("run","--rm","--pull=never","-i","--network","none","--entrypoint","sh",
                   "-v",self.volume+":/secrets",self.images["worker"],"-ec",
                   'umask 077; for file in menu waha legacy; do read -r line; printf %s "$line" > /secrets/$file; chmod 400 /secrets/$file; done',
                   stdin="\n".join((token,waha,stale))+"\n")
            mounted = docker("run","--rm","--pull=never","--network","none","--entrypoint","python",
                "-v",self.volume+":/run/secrets:ro",self.images["worker"],"-c",
                "from pathlib import Path; from hashlib import sha256; print(sha256(Path('/run/secrets/menu').read_text().strip().encode()).hexdigest())").stdout.strip()
            assert mounted == hashlib.sha256(token.encode()).hexdigest(), "secret mount mismatch"
            app = self.private/"fake-waha.py"
            app.write_text(FAKE_WAHA, encoding="utf-8")
            name=self.name+"-"+WAHA
            self.containers.append(name)
            docker("run","-d","--pull=never","--name",name,"--network",self.name,"--network-alias",WAHA,
                   "-v",self.volume+":/run/secrets:ro","--mount",f"type=bind,source={app},target=/lab.py,readonly",
                   "--entrypoint","python",self.images["worker"],"/lab.py")
            cutoff=(datetime.now(timezone.utc)-timedelta(seconds=45)).isoformat()
            env={
                "DATABASE_URL":f"postgresql://dispatch_menu:{self.password}@db/postgres",
                "SOCIALMEI_AUTH_ENABLED":"true","SOCIALMEI_SHARED_DATA_ENABLED":"true",
                "SOCIALMEI_AUTH_ORIGIN":"https://dispatch.example.test","SOCIALMEI_WHATSAPP_BOT_ENABLED":"true",
                "SOCIALMEI_WAHA_INGRESS_MODE":"team-pilot","SOCIALMEI_WAHA_PILOT_WORKSPACE_ID":"60",
                "SOCIALMEI_WAHA_PILOT_BINDING_SHA256":digest([60,3,INSTANCE,"01",ACCOUNT,1,"GOWS"]),
                "SOCIALMEI_MENU_PUBLIC_INBOUND_ACTIVE":"YES","SOCIALMEI_PUBLIC_MENU_EXPLICIT_ENABLE":"YES",
                "SOCIALMEI_MENU_SESSION":"01","SOCIALMEI_MENU_WAHA_ENGINE":"GOWS",
                "SOCIALMEI_CONTINUOUS_START_UTC":cutoff,"SOCIALMEI_PUBLIC_MENU_START_UTC":cutoff,
                "SOCIALMEI_PUBLIC_MENU_CONTINUOUS_ENABLE":"YES",
            }
            private=self.private/"disabled.json"
            private.write_text("{}")
            booking=self.private/"booking"
            booking.write_text(secrets.token_hex(32))
            ingress = rollback.ROOT/"deploy/production-overlay/20261127/api/app/waha_ingress.py"
            self.start(MENU,"menu",env.items(),((ingress,"/app/lab_ingress.py"),(booking,"/app/.socialmei-booking-signing.private"),
                (private,"/app/.everson-pilot.private.json"),(private,"/tmp/.socialmei-typing.private.json")),
                "python",("-m","uvicorn","whatsapp_public_continuous:app","--host","0.0.0.0","--port","8019"))
            wait(lambda:self.inside("worker",HTTP_CHECK,f"http://{WAHA}:3000/health","200",check=False))
            wait(lambda:self.inside("worker",HTTP_CHECK,f"http://{MENU}:8019/internal/whatsapp/bot/sources",
                                    "401",check=False))
            self.fixture("222@c.us","false_222@c.us_fixture-confirmed")
            self.fixture("555@c.us","false_555@c.us_fixture-other",61,4)
            auth_check=HTTP_CHECK.replace("urlopen(sys.argv[1],timeout=3)", "urlopen(Request(sys.argv[1],headers={'Authorization':'Bearer '+sys.argv[3]}),timeout=3)").replace("from urllib.request import urlopen", "from urllib.request import Request,urlopen")
            self.inside("worker",auth_check,f"http://{MENU}:8019/internal/whatsapp/bot/sources","200",token)
            self.dispatch("ENVIO_BLOQUEADO",3,secret="legacy")
            self.mode("unavailable")
            self.dispatch("ENVIO_BLOQUEADO", 3)
            assert self.db("SELECT count(*) FROM socialmei.wa_bot_decisions;").stdout.strip()=="0"
            primary = self.start_guard("continuous", cutoff)
            wait(lambda: self.journal_matches(primary, "source_read_failures", 1))
            self.mode("ready")
            wait(lambda: self.journal_matches(primary, "confirmed", 1))
            contender = self.start_guard("contender", cutoff)
            wait(lambda: docker("exec", contender, "sh", "-ec",
                 "test -s /run/socialmei/continuous-state/state.json", check=False))
            for _ in range(6):
                log = docker("logs", contender)
                if "CONTINUOUS_STARTUP_BLOCKED BlockingIOError" in log.stdout:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Exclusive continuous sender lock not verified")
            self.fixture("333@c.us","false_333@c.us_fixture-uncertain")
            self.mode("uncertain")
            wait(lambda: self.journal_matches(primary, "isolated_uncertain", 1))
            docker("stop", "--time", "1", primary)
            def source_reads():
                return docker("logs", self.name+"-"+MENU).stdout.count(
                    "GET /internal/whatsapp/bot/sources")

            reads = source_reads()
            restarted = self.start_guard("restarted", cutoff)
            wait(lambda: self.journal_matches(restarted, "isolated_uncertain", 1))
            for _ in range(8):
                log = docker("logs", restarted).stdout
                if "CONTINUOUS_READY_PUBLIC_INBOUND" in log and source_reads() > reads:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Restarted guard did not poll")
            self.dispatch("SEM_MENSAGENS_NOVAS")
            assert docker("exec",name,"cat","/tmp/lab-count").stdout.strip()=="2"
            assert self.db("SELECT workspace_id||':'||status FROM socialmei.wa_bot_decisions ORDER BY status;").stdout.splitlines()==[
                "60:confirmed","60:uncertain"]
            print("Continuous dispatcher: exclusive lock, persistent journal, one confirmed receipt, "
                  "uncertain not replayed after restart, other tenant and old token denied")
        finally:
            self.close()
            docker("volume","rm",self.volume,check=False)
            docker("volume", "rm", self.state_volume, check=False)


if __name__=="__main__":
    with tempfile.TemporaryDirectory(prefix="socialmei80-dispatcher-") as directory:
        lab=Lab(Path(directory))
        try:
            lab.run()
        except subprocess.CalledProcessError as error:
            raise SystemExit((error.stderr or "Docker step failed").replace(lab.password,"[synthetic]")) from None
        finally:
            lab.close()
