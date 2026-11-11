"""Inspect the isolated GOWS sidecar; generate its QR only when the operator is ready."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess

CANDIDATE = 'socialmei-waha-gows-piloto'
PRIMARY = 'socialmei-waha'
PRIVATE = Path('/home/ubuntu/.socialmei-gows-parallel-20261111')


def pairing_action(engine, status, authenticated, webhook_count):
    if engine != 'GOWS' or webhook_count:
        raise ValueError('Only isolated GOWS without webhooks can be paired')
    if authenticated or status in {'WORKING', 'SCAN_QR_CODE', 'STARTING'}:
        return None
    if status not in {'FAILED', 'STOPPED'}:
        raise ValueError('Pairing requires human attention')
    return 'restart' if status == 'FAILED' else 'start'


def run(args, code=None):
    result = subprocess.run(args, input=code, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError('GOWS operation failed; no credentials are logged')
    return result.stdout


def inspect(name):
    return json.loads(run(['docker', 'inspect', name]))[0]


def main(qr=False):
    os.umask(0o077)
    candidate, primary = inspect(CANDIDATE), inspect(PRIMARY)
    assert candidate['Id'] != primary['Id']
    candidate_volumes = {m['Source'] for m in candidate['Mounts'] if m['Destination'] == '/app/.sessions'}
    primary_volumes = {m['Source'] for m in primary['Mounts'] if m['Destination'] == '/app/.sessions'}
    assert candidate_volumes and primary_volumes and candidate_volumes.isdisjoint(primary_volumes)
    primary_probe = '''import hashlib,json,httpx
from public_worker import Config,WAHA_URL
c=Config.from_env()
r=httpx.get(WAHA_URL+'/api/sessions/'+c.session,headers={'X-Api-Key':c.waha_key},trust_env=False,timeout=10)
r.raise_for_status();d=r.json()
assert d['status']=='WORKING' and d['me']['id']==c.account
print(json.dumps({'working':True,'account_hash':hashlib.sha256(c.account.encode()).hexdigest()}))
'''
    live = json.loads(run(['docker', 'exec', '-i', 'socialmei-menu-worker-continuo', 'python', '-'], primary_probe))
    probe = '''const crypto=require('node:crypto');
(async()=>{
 const headers={'X-Api-Key':process.env.WAHA_API_KEY};
 async function call(path,method='GET'){const r=await fetch('http://127.0.0.1:3000'+path,{method,headers,redirect:'error',signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error();return r;}
 const version=await(await call('/api/version')).json();
 let session=await(await call('/api/sessions/01')).json();
 if(version.engine!=='GOWS'||(session.config?.webhooks||[]).length)throw Error();
 const out={engine:version.engine,version:version.version,tier:version.tier,state:session.status,authenticated:!!session.me};
 if(session.me?.id)out.account_hash=crypto.createHash('sha256').update(session.me.id).digest('hex');
 if(QR_REQUESTED&&!session.me){
  if(session.status==='FAILED'||session.status==='STOPPED'){
   await call('/api/sessions/01/'+(session.status==='FAILED'?'restart':'start'),'POST');
   for(let i=0;i<20;i++){await new Promise(r=>setTimeout(r,500));session=await(await call('/api/sessions/01')).json();if(session.status!=='STARTING')break;}
  }
  if(session.status!=='SCAN_QR_CODE')throw Error();
  const r=await call('/api/01/auth/qr?format=image');
  if(!(r.headers.get('content-type')||'').startsWith('image/png'))throw Error();
  const image=Buffer.from(await r.arrayBuffer());
  if(image.length>1048576||!image.subarray(0,8).equals(Buffer.from('89504e470d0a1a0a','hex')))throw Error();
  out.state=session.status;out.qr=image.toString('base64');
 }
 console.log(JSON.stringify(out));
})().catch(()=>{console.error('isolated_gows_operation_failed');process.exitCode=1});
'''.replace('QR_REQUESTED', 'true' if qr else 'false')
    if qr:
        PRIVATE.mkdir(mode=0o700, exist_ok=True)
        backup = PRIVATE/'candidate-before-qr.private.json'
        if not backup.exists():
            backup.write_text(json.dumps(candidate))
    result = json.loads(run(['docker', 'exec', '-i', CANDIDATE, 'node', '-'], probe))
    pairing_action(result['engine'], result['state'], result['authenticated'], 0)
    account = result.pop('account_hash', None)
    image = result.pop('qr', None)
    result.update(primary_working=live['working'], same_account=account == live['account_hash'] if account else None,
                  migrated=False, native_lists_homologated=False)
    if image:
        path = PRIVATE/'pairing.png'
        path.write_bytes(base64.b64decode(image, validate=True))
        path.chmod(0o600)
        result['qr_file'] = str(path)
    after = inspect(PRIMARY)
    assert after['Id'] == primary['Id'] and after['State']['StartedAt'] == primary['State']['StartedAt']
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--qr', action='store_true', help='Only after the user confirms their phone is ready')
    main(qr=parser.parse_args().qr)
