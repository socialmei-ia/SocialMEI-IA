"""API-only GOWS selection parser release; never replay stored provider events."""
import copy,datetime as dt,hashlib,http.client,json,pathlib,socket,subprocess as sp,sys,time
ROOT=pathlib.Path('/home/ubuntu/.socialmei-gows-selection-fix-222');ROOT.mkdir(mode=0o700,exist_ok=True)
API='socialmei-team-team-api-1';MENU='socialmei-menu-public-api-v3'
def private(name,data):
 p=ROOT/name;p.write_text(data if isinstance(data,str) else json.dumps(data));p.chmod(0o600)
def run(*args,input=None):
 r=sp.run(list(args),input=input,text=True,capture_output=True,timeout=120)
 if r.returncode:private('last-error.private.txt',r.stderr+'\n'+r.stdout);raise RuntimeError('selection_release_failed')
 return r.stdout
def inspect(n):return json.loads(run('docker','inspect',n))[0]
def py(code):
 for n in [API,MENU]:
  r=sp.run(['docker','inspect',n],capture_output=True,text=True)
  if r.returncode==0 and json.loads(r.stdout)[0]['State']['Running']:return run('docker','exec','-i',n,'python','-',input=code)
 raise RuntimeError('database_probe_unavailable')
def pending():
 return int(py("from database import database_url\nimport psycopg\nwith psycopg.connect(database_url()) as c:\n c.execute('SET TRANSACTION READ ONLY')\n print(c.execute(\"SELECT count(*) FROM socialmei.wa_human_replies WHERE workspace_id=1 AND channel_id=1 AND status IN ('dispatching','uncertain')\").fetchone()[0])").strip())
class UnixHTTP(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.connect('/var/run/docker.sock')
def clone(image,registry):
 cfg=copy.deepcopy(before['Config']);cfg['Image']=image;host=copy.deepcopy(before['HostConfig']);host.pop('Mounts',None)
 mounts={m['Destination']:(m['Source'],m['RW']) for m in before['Mounts']};mounts['/run/socialmei/private']=(registry,False)
 host['Binds']=[str(src)+':'+dst+('' if rw else ':ro') for dst,(src,rw) in mounts.items()];cfg['HostConfig']=host
 cfg['NetworkingConfig']={'EndpointsConfig':{n:{'Aliases':list(dict.fromkeys([API]+(v.get('Aliases') or [])))} for n,v in before['NetworkSettings']['Networks'].items()}}
 c=UnixHTTP('localhost');c.request('POST','/containers/create?name='+API,body=json.dumps(cfg),headers={'Content-Type':'application/json'});r=c.getresponse();data=r.read();c.close()
 if r.status!=201:private('clone-error.private.txt',data.decode());raise RuntimeError('api_clone_failed')
 run('docker','start',API)
def wait_healthy():
 for _ in range(45):
  if inspect(API)['State'].get('Health',{}).get('Status')=='healthy':return
  time.sleep(1)
 raise RuntimeError('api_unhealthy')
def registry_at(name):
 directory=ROOT/name;directory.mkdir(mode=0o700,exist_ok=True);value=copy.deepcopy(registry);value['bindings'][0]['ingress_after']=int(time.time());p=directory/'waha-registry.json';p.write_text(json.dumps(value));p.chmod(0o600);return directory

def rollback():
 if pending():raise RuntimeError('manual_dispatch_requires_reconciliation')
 try:run('docker','stop','-t','10',API);run('docker','rename',API,API+'-selection-inactive-'+stamp)
 except Exception:pass
 clone(before['Image'],registry_at('rollback-registry'));wait_healthy();private('rollback-result.json',{'api_restored':True,'old_events_replayed':False});print('API_ROLLED_BACK_NO_REPLAY')
mode=next((v for v in sys.argv[1:] if v in ['--prepare','--apply','--rollback','--rollback-check']),'--preflight')
if mode in {'--rollback','--rollback-check'}:
 m=json.loads((ROOT/'manifest.private.json').read_text());before=m['before'];registry=m['registry'];stamp=m['stamp']
 if mode=='--rollback-check':
  assert pending()==0;assert inspect(m['backup'])['State']['Status']=='exited';print('SELECTION_ROLLBACK_PREFLIGHT_PASSED');sys.exit(0)
 rollback();sys.exit(0)
if (ROOT/'manifest.private.json').exists():raise RuntimeError('reconcile_existing_release_before_reentry')
before=inspect(API);assert before['State']['Health']['Status']=='healthy' and pending()==0
path=pathlib.Path(next(m['Source'] for m in before['Mounts'] if m['Destination']=='/run/socialmei/private'))/'waha-registry.json';registry=json.loads(path.read_text());assert len(registry['bindings'])==1 and registry['bindings'][0]['engine']=='GOWS'
live=run('docker','exec',API,'cat','/app/waha_ingress.py');source=(ROOT/'source-sha').read_text().strip()
print('SELECTION_PREFLIGHT_PASSED',flush=True)
if mode=='--preflight':sys.exit(0)
if mode=='--prepare':
 private('before.private.json',before);private('registry-before.private.json',registry)
 tag='socialmei-gows-selection-base:'+source;run('docker','tag',before['Image'],tag);private('Dockerfile','FROM '+tag+'\nCOPY waha_ingress.py /app/waha_ingress.py\n')
 image='socialmei-gows-selection-api:'+source;run('docker','build','--network','none','--pull=false','-t',image,str(ROOT))
 private('prepared.json',{'source':source,'base_image':before['Image'],'image':image,'old_parser_sha256':hashlib.sha256(live.encode()).hexdigest()});print('SELECTION_CANDIDATE_BUILT_ONE_FILE',flush=True);sys.exit(0)
p=json.loads((ROOT/'prepared.json').read_text());assert p['base_image']==before['Image'] and p['old_parser_sha256']==hashlib.sha256(live.encode()).hexdigest()
stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup=API+'-before-selection-'+stamp
# Other channel services must retain their exact running containers.
others={n:inspect(n)['Id'] for n in [MENU,'socialmei-menu-worker-continuo','socialmei-instagram-menu-worker','socialmei-waha-gows-piloto','socialmei-waha','socialmei-team-team-gateway-1']}
private('manifest.private.json',{'before':before,'registry':registry,'stamp':stamp,'backup':backup,'source':p['source'],'others':others})
try:
 fresh_registry=registry_at('registry');run('docker','stop','-t','15',API);run('docker','rename',API,backup)
 clone(p['image'],fresh_registry);wait_healthy();assert inspect(API)['Config']['Env']==before['Config']['Env']
 assert all(inspect(n)['Id']==ident and inspect(n)['State']['Running'] for n,ident in others.items())
 assert py("from database import database_url\nimport psycopg\nwith psycopg.connect(database_url()) as c:\n c.execute('SET TRANSACTION READ ONLY')\n assert c.execute('SELECT 1').fetchone()[0]==1\nprint('database_read_ok')").strip()=='database_read_ok'
 private('result.json',{'status':'selection_parser_published_no_replay','source':p['source'],'api_healthy':True,'other_services_preserved':True,'old_events_replayed':False});print('SELECTION_PARSER_PUBLISHED_NO_REPLAY',flush=True)
except BaseException as error:
 private('failure.json',{'error':type(error).__name__})
 try:rollback()
 except Exception:print('SELECTION_ROLLBACK_REQUIRES_RECONCILIATION',flush=True)
 raise SystemExit(1)
