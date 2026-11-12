"""Authorized GOWS cutover. Run on AWS; default is read-only preflight."""
import copy, datetime as dt, hashlib, http.client, json, os, pathlib, socket, sqlite3, subprocess as sp, sys, time
from urllib.parse import quote
from gows_edge_source import patch_receiver, patch_service
ROOT=pathlib.Path('/home/ubuntu/.socialmei-gows-cutover-final-222')
API='socialmei-team-team-api-1';MENU='socialmei-menu-public-api-v3';WORKER='socialmei-menu-worker-continuo';EDGE='socialmei-waha-edge';GOWS='socialmei-waha-gows-piloto';GOWS_EDGE='socialmei-waha-gows-edge'
NAMES=[API,MENU,WORKER,EDGE];URL='http://socialmei-waha-gows-piloto:3000'

def private(name,data):
 p=ROOT/name;p.write_text(data if isinstance(data,str) else json.dumps(data,default=str));p.chmod(0o600)
def run(*args,input=None):
 r=sp.run(list(args),input=input,text=True,capture_output=True,timeout=150)
 if r.returncode:
  private('last-error.private.txt',r.stderr+'\n'+r.stdout);raise RuntimeError('private_operation_failed')
 return r.stdout
def inspect(n):return json.loads(run('docker','inspect',n))[0]
def env(c):return dict(x.split('=',1) for x in c['Config']['Env'] if '=' in x)
def py(code):
 for name in [API,MENU]:
  r=sp.run(['docker','inspect',name],capture_output=True,text=True)
  if r.returncode==0 and json.loads(r.stdout)[0]['State']['Running']:
   return run('docker','exec','-i',name,'python','-',input=code)
 raise RuntimeError('database_query_container_unavailable')
def pending():
 return int(py("from database import database_url\nimport psycopg\nwith psycopg.connect(database_url()) as c:\n c.execute('SET TRANSACTION READ ONLY')\n print(c.execute(\"SELECT (SELECT count(*) FROM socialmei.wa_bot_decisions WHERE workspace_id=1 AND channel_id=1 AND status IN ('claimed','uncertain'))+(SELECT count(*) FROM socialmei.wa_human_replies WHERE workspace_id=1 AND channel_id=1 AND status IN ('dispatching','uncertain'))\").fetchone()[0])").strip())
def provider(method,path,body=None):
 code='import httpx,json\nr=httpx.request('+repr(method)+','+repr(URL+path)+',headers={"X-Api-Key":'+repr(key)+'},json='+repr(body)+',timeout=45,trust_env=False)\nprint(json.dumps({"http":r.status_code,"body":r.json()}))'
 return json.loads(py(code))
class UnixHTTP(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.connect('/var/run/docker.sock')
def clone(name,old,changes=None,mounts=None,image=None):
 cfg=copy.deepcopy(old['Config']);cfg['Image']=image or old['Image'];values=env(old);values.update(changes or {});cfg['Env']=[k+'='+v for k,v in values.items()]
 host=copy.deepcopy(old['HostConfig']);host.pop('Mounts',None)
 mapping={m['Destination']:(m['Source'],m['RW']) for m in old['Mounts']};mapping.update(mounts or {})
 host['Binds']=[str(src)+':'+dst+('' if rw else ':ro') for dst,(src,rw) in mapping.items()];cfg['HostConfig']=host
 cfg['NetworkingConfig']={'EndpointsConfig':{n:{'Aliases':list(dict.fromkeys([name]+([a for a in v.get('Aliases',[]) if a not in [old['Id'][:12],old['Name'].lstrip('/')]] if name==old['Name'].lstrip('/') else [])))} for n,v in old['NetworkSettings']['Networks'].items()}}
 conn=UnixHTTP('localhost');conn.request('POST','/containers/create?name='+name,body=json.dumps(cfg),headers={'Content-Type':'application/json'});r=conn.getresponse();data=r.read();conn.close()
 if r.status!=201:private('clone-error.private.txt',data.decode());raise RuntimeError('container_clone_failed')
 run('docker','start',name)
def rebind(target,expected):
 code="""import psycopg,hashlib,json
from database import database_url
x=TARGET;y=EXPECTED
with psycopg.connect(database_url()) as c:
 c.execute("SET LOCAL lock_timeout='3s'");c.execute("SET LOCAL statement_timeout='10s'")
 assert c.execute("SELECT (SELECT count(*) FROM socialmei.wa_bot_decisions WHERE workspace_id=1 AND channel_id=1 AND status IN ('claimed','uncertain'))+(SELECT count(*) FROM socialmei.wa_human_replies WHERE workspace_id=1 AND channel_id=1 AND status IN ('dispatching','uncertain'))").fetchone()[0]==0
 actual=c.execute('SELECT sessao,versao FROM socialmei.crm_canais WHERE workspace_id=1 AND id=1 FOR UPDATE').fetchone();assert actual==(y['sessao'],y['versao'])
 c.execute('UPDATE socialmei.crm_canais SET sessao=%s,versao=%s WHERE workspace_id=1 AND id=1',(x['sessao'],x['versao']))
 fields=[x[k] for k in ('workspace_id','channel_id','instancia','sessao','identificador_conta','versao')]
 digest=hashlib.sha256(json.dumps(fields,separators=(',',':')).encode()).hexdigest()
 c.execute('UPDATE socialmei.wa_bot_access SET binding_hash=%s WHERE workspace_id=1 AND channel_id=1',(digest,))
print('rebound')
""".replace('TARGET',repr(target)).replace('EXPECTED',repr(expected))
 assert py(code).strip()=='rebound'
def idle_stop():
 for _ in range(30):
  run('docker','kill','--signal','STOP',WORKER)
  if not json.loads(statefile.read_text())['in_flight']:break
  run('docker','kill','--signal','CONT',WORKER);time.sleep(1)
 else:raise RuntimeError('sender_not_idle')
 run('docker','kill','--signal','CONT',WORKER);run('docker','stop','-t','2',WORKER)
def wait_api():
 for _ in range(45):
  if inspect(API)['State'].get('Health',{}).get('Status')=='healthy':return
  time.sleep(1)
 raise RuntimeError('api_unhealthy')
def retire(name):
 run('docker','stop','-t','10',name);run('docker','rename',name,backups[name]);changed.append(name)
def rollback():
 # An uncertain send is never retried through WEBJS. Keep the sender stopped.
 try:
  if inspect(WORKER)['State']['Running']:idle_stop()
 except Exception:pass
 if pending():
  private('rollback-hold.json',{'reason':'uncertain_send_requires_reconciliation','sender_stopped':True});raise RuntimeError('rollback_blocked_by_uncertain_send')
 if manifest.get('binding_changed'):rebind(channel,target)
 rollback_time=int(time.time())+2;activation=dt.datetime.fromtimestamp(rollback_time,dt.timezone.utc).isoformat()
 for name in [API,MENU,WORKER]:
  if name not in changed:continue
  try:run('docker','stop','-t','5',name);run('docker','rename',name,name+'-gows-failed-'+stamp)
  except Exception:pass
  run('docker','rename',backups[name],name)
  if name==MENU:
   # Fresh source watermark; journal/quotas and all messages remain unchanged.
   run('docker','rename',name,name+'-rollback-source-'+stamp)
   clone(name,before[name],{'SOCIALMEI_CONTINUOUS_START_UTC':activation})
  else:run('docker','start',name)
 if EDGE in changed:
  # Old spool is preserved; new live cutoff prevents importing GOWS-era inputs.
  clone(EDGE,before[EDGE],{'WAHA_INGRESS_AFTER':str(rollback_time)})
 try:run('docker','stop','-t','5',GOWS_EDGE)
 except Exception:pass
 wait_api();private('rollback-result.json',{'webjs_restored':True,'old_messages_replayed':False,'message_data_restored':False,'source_cutoff':activation});print('WEBJS_RESTORED_NO_REPLAY',flush=True)

ROOT.mkdir(mode=0o700,exist_ok=True)
mode=next((a for a in sys.argv[1:] if a in ['--prepare','--apply','--rollback']), '--preflight')
if mode=='--rollback':
 manifest=json.loads((ROOT/'manifest.private.json').read_text());before=manifest['before'];channel=manifest['channel'];target=manifest['target'];backups=manifest['backups'];changed=manifest['changed'];stamp=manifest['stamp'];statefile=pathlib.Path(manifest['statefile']);rollback();sys.exit(0)
if (ROOT/'manifest.private.json').exists():raise RuntimeError('reconcile_existing_cutover_before_reentry')
before={n:inspect(n) for n in NAMES};gows=inspect(GOWS);key=env(gows)['WAHA_API_KEY']
s=provider('GET','/api/sessions/01');v=provider('GET','/api/version');assert s['http']==200 and s['body']['status']=='WORKING';assert v['http']==200 and v['body']['engine']=='GOWS' and v['body']['version']=='2026.10.1'
registry_source=next(m['Source'] for m in before[API]['Mounts'] if m['Destination']=='/run/socialmei/private');registry=json.loads((pathlib.Path(registry_source)/'waha-registry.json').read_text());assert len(registry['bindings'])==1;binding=registry['bindings'][0]
assert s['body']['me']['id']==binding['account_id'];assert binding.get('engine','WEBJS')=='WEBJS';assert not s['body'].get('config',{}).get('webhooks')
assert pending()==0
channel=json.loads(py("from database import database_url\nfrom psycopg.rows import dict_row\nimport psycopg,json\nwith psycopg.connect(database_url(),row_factory=dict_row) as c:\n c.execute('SET TRANSACTION READ ONLY')\n print(json.dumps(c.execute('SELECT workspace_id,id AS channel_id,instancia,sessao,identificador_conta,versao FROM socialmei.crm_canais WHERE workspace_id=1 AND id=1').fetchone()))"))
assert channel['sessao']==binding['session'] and channel['versao']==binding['revision'] and channel['identificador_conta']==binding['account_id']
statefile=pathlib.Path(next(m['Source'] for m in before[WORKER]['Mounts'] if m['Destination']=='/run/socialmei/continuous-state'))/'state.json';assert json.loads(statefile.read_text())['status']=='running'
oldspool=pathlib.Path(next(m['Source'] for m in before[EDGE]['Mounts'] if m['Destination']=='/var/lib/socialmei/wa-edge'))
with sqlite3.connect('file:'+str(oldspool/'ingress.sqlite3')+'?mode=ro',uri=True) as c:assert c.execute("SELECT count(*) FROM queue WHERE state='pending'").fetchone()[0]==0
print('PREFLIGHT_PASSED_SAME_ACCOUNT_NO_PENDING',flush=True)
if mode=='--preflight':sys.exit(0)
private('before.private.json',before);private('gows-session-before.private.json',s['body']);private('registry-before.private.json',registry);private('journal-before.private.json',json.loads(statefile.read_text()))
if mode=='--prepare':
 receiver=patch_receiver(run('docker','exec',EDGE,'cat','/app/waha_durable_receiver.py'));service=patch_service(run('docker','exec',EDGE,'cat','/app/waha_durable_service.py'));private('waha_durable_receiver.py',receiver);private('waha_durable_service.py',service)
 compile(receiver,'receiver','exec');compile(service,'service','exec')
 for name,files in [('api',['settings.py','waha_ingress.py','whatsapp_human_transport.py']),('worker',['public_worker.py'])]:
  base=before[API if name=='api' else WORKER]['Image'];base_tag='socialmei-gows-pinned-base:'+name;run('docker','tag',base,base_tag);recipe='FROM '+base_tag+'\n'+''.join('COPY '+f+' /app/'+f+'\n' for f in files)
  private('Dockerfile.'+name,recipe);run('docker','build','--network','none','--pull=false','-f',str(ROOT/('Dockerfile.'+name)),'-t','socialmei-gows-'+name+':'+(ROOT/'source-sha').read_text().strip(),str(ROOT))
 private('prepared.json',{'source':(ROOT/'source-sha').read_text().strip(),'api':'socialmei-gows-api:'+(ROOT/'source-sha').read_text().strip(),'worker':'socialmei-gows-worker:'+(ROOT/'source-sha').read_text().strip(),'base_images':{n:before[n]['Image'] for n in [API,WORKER]}})
 print('CANDIDATES_BUILT_NO_DEPENDENCY_CHANGES',flush=True);sys.exit(0)
assert mode=='--apply' and (ROOT/'prepared.json').is_file()
prepared=json.loads((ROOT/'prepared.json').read_text());assert prepared['base_images']=={n:before[n]['Image'] for n in [API,WORKER]}
stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');backups={n:n+'-before-gows-'+stamp for n in NAMES};changed=[];target=dict(channel);target.update(sessao='01',versao=channel['versao']+1)
manifest=dict(before=before,channel=channel,target=target,backups=backups,changed=changed,stamp=stamp,statefile=str(statefile),binding_changed=False)
def save():manifest['changed']=changed[:];private('manifest.private.json',manifest)
try:
 idle_stop();run('docker','rename',WORKER,backups[WORKER]);changed.append(WORKER);save()
 cutoff=int(time.time())+3;activation=dt.datetime.fromtimestamp(cutoff,dt.timezone.utc).isoformat();private('activation.json',{'cutoff':cutoff,'utc':activation})
 new_registry=ROOT/'registry';new_registry.mkdir(mode=0o700,exist_ok=True);new=copy.deepcopy(registry);new['bindings'][0].update(session='01',revision=target['versao'],engine='GOWS',ingress_after=cutoff);p=new_registry/'waha-registry.json';p.write_text(json.dumps(new));p.chmod(0o600)
 new_spool=ROOT/'spool';new_spool.mkdir(mode=0o700,exist_ok=True);os.chown(new_spool,oldspool.stat().st_uid,oldspool.stat().st_gid)
 private('gows-api-key',key)
 clone(GOWS_EDGE,before[EDGE],{'WAHA_INGRESS_AFTER':str(cutoff)},{'/run/socialmei/private':(new_registry,False),'/var/lib/socialmei/wa-edge':(new_spool,True),'/app/waha_durable_receiver.py':(ROOT/'waha_durable_receiver.py',False),'/app/waha_durable_service.py':(ROOT/'waha_durable_service.py',False)})
 # No session or webhook changes to WEBJS. Its paired engine stays WORKING.
 config=copy.deepcopy(s['body'].get('config') or {});port=env(before[EDGE]).get('WAHA_LISTEN_PORT','8097');config['webhooks']=[{'url':'http://'+GOWS_EDGE+':'+port+'/receive','events':['message'],'hmac':{'key':binding['hmac_key']}}]
 r=provider('PUT','/api/sessions/01',{'name':'01','config':config});assert r['http']==200
 for _ in range(45):
  r=provider('GET','/api/sessions/01')
  if r['http']==200 and r['body'].get('status')=='WORKING' and (r['body'].get('me') or {}).get('id')==binding['account_id']:break
  time.sleep(1)
 else:raise RuntimeError('gows_not_working_after_webhook')
 retire(API);save()
 clone(API,before[API],{'SOCIALMEI_WHATSAPP_HUMAN_ENGINE':'GOWS','SOCIALMEI_WHATSAPP_HUMAN_SESSION':'01','SOCIALMEI_WAHA_PRIVATE_BASE_URL':URL,'SOCIALMEI_WAHA_PRIVATE_API_KEY':key},{'/run/socialmei/private':(new_registry,False)},prepared['api']);wait_api()
 rebind(target,channel);manifest['binding_changed']=True;save()
 retire(MENU);save();clone(MENU,before[MENU],{'SOCIALMEI_MENU_SESSION':'01','SOCIALMEI_CONTINUOUS_START_UTC':activation})
 retire(EDGE);save()
 clone(WORKER,before[WORKER],{'SOCIALMEI_MENU_SESSION':'01','SOCIALMEI_MENU_WAHA_ENGINE':'GOWS','SOCIALMEI_MENU_WAHA_URL':URL},{'/run/secrets/waha-key':(ROOT/'gows-api-key',False),'/app/continuous_guard.py':(ROOT/'whatsapp-continuous-guard.py',False)},prepared['worker'])
 time.sleep(2);assert inspect(WORKER)['State']['Running'];assert json.loads(statefile.read_text())['status']=='running'
 check="""import httpx,json
from public_worker import Config,API_URL,SOURCE_URL
c=Config.from_env()
with httpx.Client(trust_env=False) as h:
 r=h.get(c.waha_url+'/api/sessions/'+c.session,headers={'X-Api-Key':c.waha_key},timeout=10);d=r.json();assert r.status_code==200 and d['status']=='WORKING' and d['me']['id']==c.account
 r=h.get(API_URL+SOURCE_URL,headers={'Authorization':'Bearer '+c.token},timeout=15);assert r.status_code==200
print('gows_sender_ready')
"""
 assert run('docker','exec','-i',WORKER,'python','-',input=check).strip()=='gows_sender_ready'
 private('result.json',{'status':'gows_active_waiting_real_homologation','source':prepared['source'],'one_sender':True,'webjs_container_preserved':True,'old_messages_replayed':False,'cutoff':cutoff})
 print('GOWS_ACTIVE_WAITING_REAL_HOMOLOGATION',flush=True)
except BaseException as error:
 private('failure.json',{'error':type(error).__name__,'changed':changed});save()
 try:rollback()
 except Exception:print('ROLLBACK_HOLD_REQUIRES_RECONCILIATION',flush=True)
 raise SystemExit(1)
