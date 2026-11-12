"""Restore configuration only after idle/receipt reconciliation. Default: preflight."""
import copy, hashlib, http.client, json, pathlib, socket, subprocess as sp, sys, time
ROOT=pathlib.Path('/home/ubuntu/.socialmei-webjs-recovery-222')
API='socialmei-team-team-api-1';WORKER='socialmei-menu-worker-continuo'
def run(*args,input=None):
 r=sp.run(list(args),input=input,text=True,capture_output=True,timeout=90)
 if r.returncode:raise RuntimeError('rollback_command_failed')
 return r.stdout
def inspect(name):return json.loads(run('docker','inspect',name))[0]
before=json.loads((ROOT/'before.private.json').read_text());backups=json.loads((ROOT/'rollback.private.json').read_text());db=json.loads((ROOT/'binding-before.private.json').read_text());session=json.loads((ROOT/'session-before.private.json').read_text())
for old in backups.values():assert inspect(old)['State']['Status']=='exited'
code="""import psycopg,json
from database import database_url
with psycopg.connect(database_url()) as c:
 c.execute('SET TRANSACTION READ ONLY')
 n=c.execute("SELECT (SELECT count(*) FROM socialmei.wa_bot_decisions WHERE workspace_id=1 AND channel_id=1 AND status IN ('claimed','uncertain'))+(SELECT count(*) FROM socialmei.wa_human_replies WHERE workspace_id=1 AND channel_id=1 AND status IN ('dispatching','uncertain'))").fetchone()[0]
 print(json.dumps({'pending':n}))
"""
result=json.loads(run('docker','exec','-i',API,'python','-',input=code));assert result['pending']==0
print('ROLLBACK_PREFLIGHT_PASSED',flush=True)
if '--apply' not in sys.argv:sys.exit(0)
statefile=pathlib.Path(next(m['Source'] for m in before[WORKER]['Mounts'] if m['Destination']=='/run/socialmei/continuous-state'))/'state.json'
for attempt in range(20):
 run('docker','kill','--signal','STOP',WORKER)
 if not json.loads(statefile.read_text())['in_flight']:break
 run('docker','kill','--signal','CONT',WORKER);time.sleep(1)
else:raise RuntimeError('sender_not_idle')
run('docker','kill','--signal','CONT',WORKER);run('docker','stop','-t','2',WORKER)
e=dict(x.split('=',1) for x in before[WORKER]['Config']['Env'] if '=' in x)
key=pathlib.Path(next(m['Source'] for m in before[WORKER]['Mounts'] if m['Destination']==e['SOCIALMEI_MENU_WAHA_KEY_FILE'])).read_text().strip()
from urllib.parse import quote
payload={'name':session['name'],'config':session.get('config') or {}}
code='import httpx\nr=httpx.put('+repr(e['SOCIALMEI_MENU_WAHA_URL']+'/api/sessions/'+quote(session['name'],safe=''))+',headers={"X-Api-Key":'+repr(key)+'},json='+repr(payload)+',timeout=45,trust_env=False)\nassert r.status_code==200\nprint("hook_restored")'
assert run('docker','exec','-i',API,'python','-',input=code).strip()=='hook_restored'
old=db['channel']
code="""import psycopg,hashlib,json
from database import database_url
x=OLD
with psycopg.connect(database_url()) as c:
 c.execute("SET LOCAL lock_timeout='3s'");c.execute("SET LOCAL statement_timeout='10s'")
 assert c.execute("SELECT (SELECT count(*) FROM socialmei.wa_bot_decisions WHERE workspace_id=1 AND channel_id=1 AND status IN ('claimed','uncertain'))+(SELECT count(*) FROM socialmei.wa_human_replies WHERE workspace_id=1 AND channel_id=1 AND status IN ('dispatching','uncertain'))").fetchone()[0]==0
 row=c.execute('SELECT versao FROM socialmei.crm_canais WHERE workspace_id=1 AND id=1 FOR UPDATE').fetchone();assert row[0]==x['versao']+1
 c.execute('UPDATE socialmei.crm_canais SET sessao=%s,versao=%s WHERE workspace_id=1 AND id=1',(x['sessao'],x['versao']))
 c.execute('UPDATE socialmei.wa_bot_access SET binding_hash=%s WHERE workspace_id=1 AND channel_id=1',(HASH,))
print('binding_restored')
""".replace('OLD',repr(old)).replace('HASH',repr(db['access']['binding_hash']))
assert run('docker','exec','-i',API,'python','-',input=code).strip()=='binding_restored'
stamp=str(int(time.time()))
for name in ['socialmei-waha-edge','socialmei-menu-public-api-v3',API,WORKER]:
 if inspect(name)['State']['Running']:run('docker','stop','-t','10',name)
 run('docker','rename',name,name+'-after-recovery-'+stamp)
 run('docker','rename',backups[name],name);run('docker','start',name)
# The old state is known to contain the session drift. Rollback is containment,
# not proof of restored service; do not send old messages or restore message data.
(ROOT/'rollback-result.json').write_text(json.dumps({'restored_configuration':True,'message_data_restored':False,'old_drift_requires_recovery':True}))
print('ROLLBACK_CONFIGURATION_RESTORED_NO_REPLAY')
