"""Publish only the contact-bound list canary; keep GOWS/text rollback intact."""
import copy, datetime as dt, hashlib, http.client, json, pathlib, socket, subprocess as sp, sys, time
from gows_list_source import patch_bot
ROOT=pathlib.Path('/home/ubuntu/.socialmei-gows-list-canary-222');ROOT.mkdir(mode=0o700,exist_ok=True)
MENU='socialmei-menu-public-api-v3';WORKER='socialmei-menu-worker-continuo';API='socialmei-team-team-api-1'

def private(name,data):
 p=ROOT/name;p.write_text(data if isinstance(data,str) else json.dumps(data,default=str));p.chmod(0o600)
def run(*args,input=None):
 r=sp.run(list(args),input=input,text=True,capture_output=True,timeout=120)
 if r.returncode:private('last-error.private.txt',r.stderr+'\n'+r.stdout);raise RuntimeError('canary_operation_failed')
 return r.stdout
def inspect(n):return json.loads(run('docker','inspect',n))[0]
def env(c):return dict(x.split('=',1) for x in c['Config']['Env'] if '=' in x)
def py(code):return run('docker','exec','-i',API,'python','-',input=code)
def pending():
 return int(py("from database import database_url\nimport psycopg\nwith psycopg.connect(database_url()) as c:\n c.execute('SET TRANSACTION READ ONLY')\n print(c.execute(\"SELECT (SELECT count(*) FROM socialmei.wa_bot_decisions WHERE workspace_id=1 AND channel_id=1 AND status IN ('claimed','uncertain'))+(SELECT count(*) FROM socialmei.wa_human_replies WHERE workspace_id=1 AND channel_id=1 AND status IN ('dispatching','uncertain'))\").fetchone()[0])").strip())
class UnixHTTP(http.client.HTTPConnection):
 def connect(self):self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.sock.connect('/var/run/docker.sock')
def clone(name,old,changes=None,mounts=None,image=None):
 cfg=copy.deepcopy(old['Config']);cfg['Image']=image or old['Image'];e=env(old);e.update(changes or {});cfg['Env']=[k+'='+v for k,v in e.items()]
 host=copy.deepcopy(old['HostConfig']);host.pop('Mounts',None);mapping={m['Destination']:(m['Source'],m['RW']) for m in old['Mounts']};mapping.update(mounts or {});host['Binds']=[str(src)+':'+dst+('' if rw else ':ro') for dst,(src,rw) in mapping.items()];cfg['HostConfig']=host
 cfg['NetworkingConfig']={'EndpointsConfig':{n:{'Aliases':list(dict.fromkeys([name]+(v.get('Aliases') or [])))} for n,v in old['NetworkSettings']['Networks'].items()}}
 conn=UnixHTTP('localhost');conn.request('POST','/containers/create?name='+name,body=json.dumps(cfg),headers={'Content-Type':'application/json'});r=conn.getresponse();data=r.read();conn.close()
 if r.status!=201:private('clone-error.private.txt',data.decode());raise RuntimeError('canary_clone_failed')
 run('docker','start',name)
def stop_sender():
 for _ in range(30):
  run('docker','kill','--signal','STOP',WORKER)
  state=json.loads(statefile.read_text())
  if not state['in_flight']:break
  run('docker','kill','--signal','CONT',WORKER);time.sleep(1)
 else:raise RuntimeError('sender_not_idle')
 # Stop while frozen at an idle boundary; do not resume into another poll.
 run('docker','stop','-t','1',WORKER)
def restore():
 # Never clear an uncertain ledger or journal to make a rollback look healthy.
 try:
  if inspect(WORKER)['State']['Running']:stop_sender()
 except Exception:pass
 state=json.loads(statefile.read_text())
 if pending() or state['status']!='running' or state['in_flight']:
  private('rollback-hold.json',{'reason':'reconcile_before_resuming_sender'});raise RuntimeError('rollback_hold_no_retry')
 now=dt.datetime.now(dt.timezone.utc).isoformat()
 for n in [MENU,WORKER]:
  if n not in changed:continue
  try:run('docker','stop','-t','5',n);run('docker','rename',n,n+'-list-canary-inactive-'+stamp)
  except Exception:pass
  if n==MENU:clone(n,before[n],{'SOCIALMEI_CONTINUOUS_START_UTC':now})
  else:run('docker','rename',backups[n],n);run('docker','start',n)
 private('rollback-result.json',{'text_restored':True,'messages_replayed':False});print('TEXT_RESTORED_NO_REPLAY',flush=True)

mode=next((a for a in sys.argv[1:] if a in ['--prepare','--apply','--rollback','--rollback-check']), '--preflight')
if mode in {'--rollback','--rollback-check'}:
 m=json.loads((ROOT/'manifest.private.json').read_text());before=m['before'];backups=m['backups'];changed=m['changed'];statefile=pathlib.Path(m['statefile']);stamp=m['stamp']
 if mode=='--rollback-check':
  assert pending()==0 and all(inspect(n)['State']['Status']=='exited' for n in backups.values());print('CANARY_ROLLBACK_PREFLIGHT_PASSED');sys.exit(0)
 restore();sys.exit(0)
if (ROOT/'manifest.private.json').exists():raise RuntimeError('reconcile_existing_canary_before_reentry')
before={n:inspect(n) for n in [MENU,WORKER]};e=env(before[WORKER]);assert e['SOCIALMEI_MENU_WAHA_ENGINE']=='GOWS' and e['SOCIALMEI_MENU_SESSION']=='01';assert pending()==0
allowed=json.loads((ROOT/'authorized-contact.private.json').read_text());assert len(allowed)==1;contact=allowed[0];assert contact.startswith('waha:')
statefile=pathlib.Path(next(m['Source'] for m in before[WORKER]['Mounts'] if m['Destination']=='/run/socialmei/continuous-state'))/'state.json';assert json.loads(statefile.read_text())['status']=='running'
private('before.private.json',before);private('journal-before.private.json',json.loads(statefile.read_text()))
print('CANARY_PREFLIGHT_PASSED_ONE_AUTHORIZED_CONTACT',flush=True)
if mode=='--preflight':sys.exit(0)
if mode=='--prepare':
 live=run('docker','exec',MENU,'cat','/app/whatsapp_bot.py');candidate=(ROOT/'whatsapp_bot.candidate.py').read_text();patched=patch_bot(live,candidate);private('whatsapp_bot.py',patched)
 for kind,container,filename in [('menu',MENU,'whatsapp_bot.py'),('worker',WORKER,'public_worker.py')]:
  base=before[container]['Image'];tag='socialmei-gows-list-base:'+kind;run('docker','tag',base,tag);recipe='FROM '+tag+'\nCOPY '+filename+' /app/'+filename+'\n';private('Dockerfile.'+kind,recipe)
  run('docker','build','--network','none','--pull=false','-f',str(ROOT/('Dockerfile.'+kind)),'-t','socialmei-gows-list-'+kind+':'+(ROOT/'source-sha').read_text().strip(),str(ROOT))
 private('prepared.json',{'source':(ROOT/'source-sha').read_text().strip(),'base_images':{n:before[n]['Image'] for n in before},'images':{kind:'socialmei-gows-list-'+kind+':'+(ROOT/'source-sha').read_text().strip() for kind in ['menu','worker']},'live_bot_sha256':hashlib.sha256(live.encode()).hexdigest(),'candidate_bot_sha256':hashlib.sha256(patched.encode()).hexdigest()})
 print('CANARY_CANDIDATES_BUILT_LIVE_POLICIES_PRESERVED');sys.exit(0)
prepared=json.loads((ROOT/'prepared.json').read_text());assert prepared['base_images']=={n:before[n]['Image'] for n in before}
assert hashlib.sha256(run('docker','exec',MENU,'cat','/app/whatsapp_bot.py').encode()).hexdigest()==prepared['live_bot_sha256']
stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');backups={n:n+'-before-list-'+stamp for n in before};changed=[]
manifest=dict(before=before,backups=backups,changed=changed,statefile=str(statefile),stamp=stamp)
def save():manifest['changed']=changed[:];private('manifest.private.json',manifest)
try:
 stop_sender();run('docker','rename',WORKER,backups[WORKER]);changed.append(WORKER);save()
 assert pending()==0
 activation=dt.datetime.now(dt.timezone.utc).isoformat();private('activation.json',{'utc':activation})
 run('docker','stop','-t','10',MENU);run('docker','rename',MENU,backups[MENU]);changed.append(MENU);save()
 flags={'SOCIALMEI_MENU_GOWS_LIST_CANARY_CONTACT':contact,'SOCIALMEI_MENU_GOWS_LIST_CANARY_ACTIVE':'YES','SOCIALMEI_MENU_WAHA_ENGINE':'GOWS'}
 clone(MENU,before[MENU],dict(flags,SOCIALMEI_CONTINUOUS_START_UTC=activation),image=prepared['images']['menu'])
 # Import and verify only selection/renderer; never write a fixture to production.
 code="""import whatsapp_bot as b,json,os
channel=dict(workspace_id=1,channel_id=1,instancia='socialmei-equipe-piloto',sessao='01')
assert b.native_list_canary(channel,os.environ['SOCIALMEI_MENU_GOWS_LIST_CANARY_CONTACT'])
assert not b.native_list_canary(channel,'waha:unrelated-test@lid')
assert not b.native_list_canary({**channel,'workspace_id':2},os.environ['SOCIALMEI_MENU_GOWS_LIST_CANARY_CONTACT'])
assert hasattr(b,'explicit_menu_action') and hasattr(b,'canonical_choice')
print('canary_scope_and_live_policy_ok')
"""
 assert run('docker','exec','-i',MENU,'python','-',input=code).strip()=='canary_scope_and_live_policy_ok'
 clone(WORKER,before[WORKER],flags,{'/app/continuous_guard.py':(ROOT/'whatsapp-continuous-guard.py',False)},prepared['images']['worker'])
 time.sleep(2);assert inspect(WORKER)['State']['Running'];state=json.loads(statefile.read_text());assert state['status']=='running'
 code="""from public_worker import Config,API_URL,SOURCE_URL
import httpx
c=Config.from_env();assert c.engine=='GOWS' and c.native_list_contact
with httpx.Client(trust_env=False) as h:
 r=h.get(c.waha_url+'/api/sessions/'+c.session,headers={'X-Api-Key':c.waha_key},timeout=10);assert r.status_code==200 and r.json()['status']=='WORKING' and r.json()['me']['id']==c.account
 r=h.get(API_URL+SOURCE_URL,headers={'Authorization':'Bearer '+c.token},timeout=15);assert r.status_code==200
print('canary_ready_no_messages_sent_by_probe')
"""
 assert run('docker','exec','-i',WORKER,'python','-',input=code).strip()=='canary_ready_no_messages_sent_by_probe'
 private('result.json',{'status':'list_canary_ready_waiting_one_real_test','source':prepared['source'],'authorized_contacts':1,'text_for_other_contacts':True,'journal_preserved':True,'messages_sent_by_operator':0});print('LIST_CANARY_ACTIVE_ONE_CONTACT_ONLY',flush=True)
except BaseException as error:
 private('failure.json',{'error':type(error).__name__,'changed':changed});save()
 try:restore()
 except Exception:print('CANARY_ROLLBACK_HOLD_NO_RETRY',flush=True)
 raise SystemExit(1)
