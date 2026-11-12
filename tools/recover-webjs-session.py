"""Private bounded WEBJS recovery; no messages or credentials in stdout."""
import copy, datetime, hashlib, http.client, json, os, pathlib, socket, sqlite3, subprocess as sp, sys, time
ROOT=pathlib.Path('/home/ubuntu/.socialmei-webjs-recovery-222');ROOT.mkdir(mode=0o700,exist_ok=True)
API='socialmei-team-team-api-1';MENU='socialmei-menu-public-api-v3';WORKER='socialmei-menu-worker-continuo';EDGE='socialmei-waha-edge';WAHA='socialmei-waha'
NAMES=[API,MENU,WORKER,EDGE]
if (ROOT/'result.json').exists() or (ROOT/'failure.json').exists():
 raise RuntimeError('reconcile_existing_recovery_before_reentry')
def run(*args,input=None):
 r=sp.run(list(args),input=input,capture_output=True,text=True,timeout=90)
 if r.returncode:
  private('last-error.private.txt',r.stderr+'\n'+r.stdout);raise RuntimeError('private_command_failed')
 return r.stdout

def private(name,value):
 p=ROOT/name;p.write_text(value if isinstance(value,str) else json.dumps(value,default=str));p.chmod(0o600)
def inspect(n):return json.loads(run('docker','inspect',n))[0]
def env(c):return dict(x.split('=',1) for x in c['Config']['Env'] if '=' in x)
def execpy(n,code):return run('docker','exec','-i',n,'python','-',input=code)

def provider(method,path,body=None):
 c=before[WORKER];e=env(c);key=pathlib.Path(next(m['Source'] for m in c['Mounts'] if m['Destination']==e['SOCIALMEI_MENU_WAHA_KEY_FILE'])).read_text().strip()
 # The request runs on the worker's existing private Docker network.
 code='import httpx,json\nr=httpx.request('+repr(method)+','+repr(e['SOCIALMEI_MENU_WAHA_URL']+path)+',headers={"X-Api-Key":'+repr(key)+'},json='+repr(body)+',timeout=35,trust_env=False)\nprint(json.dumps({"http":r.status_code,"body":r.json()}))'
 return json.loads(execpy(WORKER,code))

before={n:inspect(n) for n in NAMES};private('before.private.json',before)
e=env(before[WORKER]);assert e['SOCIALMEI_MENU_SESSION']=='01';assert e['SOCIALMEI_MENU_PUBLIC_INBOUND_ACTIVE']=='YES'
a=provider('GET','/api/sessions');assert a['http']==200
sessions=[x for x in a['body'] if x.get('status')=='WORKING' and (x.get('me') or {}).get('id')==e['SOCIALMEI_MENU_ACCOUNT']];assert len(sessions)==1
session=sessions[0]['name'];assert session!='01'
from urllib.parse import quote
session_path='/api/sessions/'+quote(session,safe='')
s=provider('GET',session_path);assert s['http']==200;session_before=s['body'];private('session-before.private.json',session_before)
assert session_before['status']=='WORKING' and session_before['me']['id']==e['SOCIALMEI_MENU_ACCOUNT']
registry_mount=next(m for m in before[API]['Mounts'] if m['Destination']=='/run/socialmei/private');registry=json.loads((pathlib.Path(registry_mount['Source'])/'waha-registry.json').read_text());assert len(registry['bindings'])==1
binding=registry['bindings'][0];assert binding['session']=='01' and binding['account_id']==e['SOCIALMEI_MENU_ACCOUNT'];private('registry-before.private.json',registry)
dbcode="""import psycopg,json
from database import database_url
from psycopg.rows import dict_row
with psycopg.connect(database_url(),row_factory=dict_row) as c:
 c.execute('SET TRANSACTION READ ONLY')
 channel=c.execute('SELECT workspace_id,id AS channel_id,instancia,sessao,identificador_conta,versao FROM socialmei.crm_canais WHERE workspace_id=1 AND id=1').fetchone()
 access=c.execute('SELECT binding_hash FROM socialmei.wa_bot_access WHERE workspace_id=1 AND channel_id=1').fetchone()
 pending=c.execute("SELECT (SELECT count(*) FROM socialmei.wa_bot_decisions WHERE workspace_id=1 AND channel_id=1 AND status IN ('claimed','uncertain'))+(SELECT count(*) FROM socialmei.wa_human_replies WHERE workspace_id=1 AND channel_id=1 AND status IN ('dispatching','uncertain')) AS n").fetchone()['n']
 print(json.dumps(dict(channel=channel,access=access,pending=pending)))
"""
db=json.loads(execpy(API,dbcode));private('binding-before.private.json',db);assert db['pending']==0;assert db['channel']['sessao']=='01';assert db['channel']['versao']==binding['revision'];assert db['channel']['identificador_conta']==binding['account_id']
spool_mount=next(m for m in before[EDGE]['Mounts'] if m['Destination']=='/var/lib/socialmei/wa-edge')
with sqlite3.connect('file:'+str(pathlib.Path(spool_mount['Source'])/'ingress.sqlite3')+'?mode=ro',uri=True) as c:assert c.execute("SELECT count(*) FROM queue WHERE state='pending'").fetchone()[0]==0
statefile=pathlib.Path(next(m['Source'] for m in before[WORKER]['Mounts'] if m['Destination']=='/run/socialmei/continuous-state'))/'state.json';state=json.loads(statefile.read_text());assert state['status']=='running';private('journal-before.private.json',state)
# Preserve every unrelated container and the paired provider container untouched.
all_before=json.loads(run('docker','inspect',*run('docker','ps','-q').split()));private('unrelated-before.private.json',{x['Id']:x['State']['StartedAt'] for x in all_before if x['Name'].lstrip('/') not in NAMES})
print(json.dumps({'preflight':'passed','same_account':True,'session_divergence':True,'pending_sends':0,'edge_pending':0,'backup':str(ROOT)}),flush=True)
if '--apply' not in sys.argv:sys.exit(0)
assert (ROOT/'whatsapp-public-continuous.py').is_file()
# A new private spool prevents changing the owner hash of the preserved old spool.
new_registry=ROOT/'registry';new_registry.mkdir(mode=0o700,exist_ok=True)
new_binding=copy.deepcopy(binding);new_binding['session']=session;new_binding['revision']=binding['revision']+1
new_config=copy.deepcopy(registry);new_config['bindings']=[new_binding]
p=new_registry/'waha-registry.json';p.write_text(json.dumps(new_config));p.chmod(0o600)
new_spool=ROOT/'spool';new_spool.mkdir(mode=0o700,exist_ok=True);os.chown(new_spool,os.stat(spool_mount['Source']).st_uid,os.stat(spool_mount['Source']).st_gid)
# Derive only the edge admission function from its installed source. HMAC/owner
# checks remain before the fresh timestamp cutoff and durable queue insertion.
source=run('docker','exec',EDGE,'cat','/app/waha_durable_receiver.py')
needle='        key = hashlib.sha256(body).hexdigest()'
assert source.count(needle)==1
addition="""        cutoff = int(__import__('os').environ['WAHA_INGRESS_AFTER'])
        payload = event.get('payload')
        stamp = payload.get('timestamp') if isinstance(payload, dict) else None
        if type(stamp) not in (int, float):
            raise Rejected('invalid_message_time')
        if stamp < cutoff:
            return None
"""
source=source.replace(needle,addition+needle);compile(source,'waha_durable_receiver.py','exec');private('waha_durable_receiver.py',source)
# Preserve installed images, environment, mounts and network aliases.
class UnixHTTP(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.connect('/var/run/docker.sock')
def create(n,changes,mount_changes):
 old=before[n];cfg=copy.deepcopy(old['Config']);cfg['Image']=old['Image'];values=env(old);values.update(changes);cfg['Env']=[k+'='+v for k,v in values.items()]
 host=copy.deepcopy(old['HostConfig']);host.pop('Mounts',None)
 mounts={m['Destination']:(m['Source'],m['RW']) for m in old['Mounts']};mounts.update(mount_changes)
 host['Binds']=[str(src)+':'+dst+('' if rw else ':ro') for dst,(src,rw) in mounts.items()];cfg['HostConfig']=host
 cfg['NetworkingConfig']={'EndpointsConfig':{net:{'Aliases':list(dict.fromkeys([n]+[a for a in (v.get('Aliases') or []) if a!=old['Id'][:12]]))} for net,v in old['NetworkSettings']['Networks'].items()}}
 conn=UnixHTTP('localhost');conn.request('POST','/containers/create?name='+n,body=json.dumps(cfg),headers={'Content-Type':'application/json'});r=conn.getresponse();data=r.read();conn.close()
 if r.status!=201:private('create-error.private.txt',data.decode());raise RuntimeError('clone_failed')
 run('docker','start',n)
def dbchange(restore=False):
 channel=db['channel'];target=dict(channel);target['sessao']=session;target['versao']+=1
 source,target=(target,channel) if restore else (channel,target)
 code="""import psycopg,json,hashlib
from database import database_url
from psycopg.rows import dict_row
old=OLD;new=NEW
with psycopg.connect(database_url(),row_factory=dict_row) as c:
 c.execute("SET LOCAL lock_timeout='3s'");c.execute("SET LOCAL statement_timeout='10s'")
 row=c.execute('SELECT sessao,versao FROM socialmei.crm_canais WHERE workspace_id=1 AND id=1 FOR UPDATE').fetchone()
 assert row['sessao']==old['sessao'] and row['versao']==old['versao']
 assert c.execute("SELECT count(*) AS n FROM socialmei.wa_bot_decisions WHERE workspace_id=1 AND channel_id=1 AND status IN ('claimed','uncertain')").fetchone()['n']==0
 assert c.execute("SELECT count(*) AS n FROM socialmei.wa_human_replies WHERE workspace_id=1 AND channel_id=1 AND status IN ('dispatching','uncertain')").fetchone()['n']==0
 c.execute('UPDATE socialmei.crm_canais SET sessao=%s,versao=%s WHERE workspace_id=1 AND id=1',(new['sessao'],new['versao']))
 fields=[new[k] for k in ('workspace_id','channel_id','instancia','sessao','identificador_conta','versao')]
 digest=hashlib.sha256(json.dumps(fields,separators=(',',':')).encode()).hexdigest()
 c.execute('UPDATE socialmei.wa_bot_access SET binding_hash=%s WHERE workspace_id=1 AND channel_id=1',(digest,))
print('binding_updated')
""".replace('OLD',repr(source)).replace('NEW',repr(target))
 assert execpy(API,code).strip()=='binding_updated'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');backups={n:n+'-before-recovery-'+stamp for n in NAMES};private('rollback.private.json',backups)
changed=[];binding_changed=False;hook_changed=False
try:
 # Freeze the one automatic sender at a reconciled idle boundary.
 for attempt in range(20):
  run('docker','kill','--signal','STOP',WORKER);state=json.loads(statefile.read_text())
  if not state['in_flight']:break
  run('docker','kill','--signal','CONT',WORKER);time.sleep(1)
 else:raise RuntimeError('sender_not_idle')
 run('docker','kill','--signal','CONT',WORKER);run('docker','stop','-t','2',WORKER);run('docker','rename',WORKER,backups[WORKER]);changed.append(WORKER)
 cutoff=int(time.time())+3;activation=datetime.datetime.fromtimestamp(cutoff,datetime.timezone.utc).isoformat();private('activation.json',{'utc':activation,'cutoff':cutoff})
 # Disable manual WA briefly while rebinding, keeping Instagram configuration intact.
 run('docker','stop','-t','15',API);run('docker','rename',API,backups[API]);changed.append(API)
 create(API,{'SOCIALMEI_WHATSAPP_HUMAN_SESSION':session}, {'/run/socialmei/private':(new_registry,False)})
 for attempt in range(30):
  if inspect(API)['State'].get('Health',{}).get('Status')=='healthy':break
  time.sleep(1)
 else:raise RuntimeError('api_not_healthy')
 dbchange();binding_changed=True
 for n in [MENU,EDGE]:
  run('docker','stop','-t','10',n);run('docker','rename',n,backups[n]);changed.append(n)
  if n==MENU:create(n,{'SOCIALMEI_MENU_SESSION':session,'SOCIALMEI_CONTINUOUS_START_UTC':activation},{'/app/whatsapp_public_continuous.py':(ROOT/'whatsapp-public-continuous.py',False)})
  else:create(n,{'WAHA_INGRESS_AFTER':str(cutoff)},{'/run/socialmei/private':(new_registry,False),'/var/lib/socialmei/wa-edge':(new_spool,True),'/app/waha_durable_receiver.py':(ROOT/'waha_durable_receiver.py',False)})
 # PUT keeps name/identity/credentials; WAHA stops/starts only this WEBJS session.
 config=copy.deepcopy(session_before.get('config') or {});hooks=[]
 for item in config.get('webhooks',[]):
  item=copy.deepcopy(item);item['events']=[v for v in item.get('events',[]) if not v.startswith('message')]
  if item['events']:hooks.append(item)
 port=env(before[EDGE]).get('WAHA_LISTEN_PORT','8097')
 hooks.append({'url':'http://socialmei-waha-edge:'+port+'/receive','events':['message'],'hmac':{'key':binding['hmac_key']}});config['webhooks']=hooks
 # The provider call uses preserved stopped worker's network via a temporary
 # read-only helper, because the automatic sender must remain stopped.
 def provider_stopped(method,path,body=None):
  # Existing main API shares the WAHA network; secret is read from original mount.
  key=pathlib.Path(next(m['Source'] for m in before[WORKER]['Mounts'] if m['Destination']==e['SOCIALMEI_MENU_WAHA_KEY_FILE'])).read_text().strip()
  code='import httpx,json\nr=httpx.request('+repr(method)+','+repr(e['SOCIALMEI_MENU_WAHA_URL']+path)+',headers={"X-Api-Key":'+repr(key)+'},json='+repr(body)+',timeout=45,trust_env=False)\nprint(json.dumps({"http":r.status_code,"body":r.json()}))'
  return json.loads(execpy(API,code))
 hook_changed=True;r=provider_stopped('PUT',session_path,{'name':session,'config':config});assert r['http']==200
 for attempt in range(40):
  r=provider_stopped('GET',session_path);d=r['body']
  if r['http']==200 and d.get('status')=='WORKING' and (d.get('me') or {}).get('id')==binding['account_id']:break
  time.sleep(1)
 else:raise RuntimeError('webjs_recovery_requires_human')
 # Check signed edge rejects unauthenticated traffic, accepts no fixture data.
 check="""import httpx
r=httpx.get('http://socialmei-waha-edge:PORT/health',timeout=10);assert r.status_code==204
r=httpx.post('http://socialmei-waha-edge:PORT/receive',content=b'{}',headers={'Content-Type':'application/json'},timeout=10);assert r.status_code==403
print('edge_healthy_signed_only')
""".replace('PORT',port)
 assert execpy(API,check).strip()=='edge_healthy_signed_only'
 # Keep original journal and quotas. Fresh source cutoff is API-side only.
 create(WORKER,{'SOCIALMEI_MENU_SESSION':session},{})
 time.sleep(2);assert inspect(WORKER)['State']['Running'];assert json.loads(statefile.read_text())['status']=='running'
 after={x['Id']:x['State']['StartedAt'] for x in json.loads(run('docker','inspect',*run('docker','ps','-q').split()))}
 for ident,started in json.loads((ROOT/'unrelated-before.private.json').read_text()).items():assert after.get(ident)==started
 private('result.json',{'status':'recovered_waiting_real_homologation','same_account':True,'webjs_working':True,'api_healthy':True,'edge_signed_only':True,'old_messages_replayed':False,'rollback':backups,'source_cutoff':activation})
 print('RECOVERED_WAITING_REAL_HOMOLOGATION',flush=True)
except BaseException as error:
 # No provider sends are repeated. Restore configuration, not message data.
 private('failure.json',{'error':type(error).__name__,'changed':changed,'binding_changed':binding_changed,'hook_changed':hook_changed})
 try:
  if WORKER in changed and any(inspect(WORKER) for _ in [0]):run('docker','stop','-t','2',WORKER)
 except Exception:pass
 try:
  if hook_changed:provider_stopped('PUT',session_path,{'name':session,'config':session_before.get('config') or {}})
  if binding_changed:dbchange(restore=True)
  for n in reversed(changed):
   try:run('docker','stop','-t','5',n);run('docker','rename',n,n+'-failed-'+stamp)
   except Exception:pass
   run('docker','rename',backups[n],n);run('docker','start',n)
  print('ROLLED_BACK_WITHOUT_REPLAY',flush=True)
 except Exception:print('ROLLBACK_REQUIRES_OPERATOR_PRIVATE_RECEIPT',flush=True)
 raise SystemExit(1)
