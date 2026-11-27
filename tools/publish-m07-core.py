"""Apply the approved M07-046 plan with additive DDL and application-only rollback."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

ROOT = Path('/var/lib/socialmei/production-consolidation-m07/preflight-bfvgu3zz')
EXPECTED = '94c52c116bae9de5a6db1711a66b73dfd3800fb94547b71da2e8277e85dd3be7'
API = 'socialmei-team-team-api-1'
GATEWAY = 'socialmei-team-team-gateway-1'
PG = 'socialmei-postgres-relocation-20261112'
DB = 'socialmei_candidate040_20261114'
ORIGIN = 'https://socialmei-ia.54-94-213-7.sslip.io'
SERVICES = {'api': (API,'team-api'), 'gateway': (GATEWAY,'team-gateway')}


def require(ok, label):
    if not ok:
        raise RuntimeError(label)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args, data=None, timeout=130):
    result=subprocess.run(args,input=data,capture_output=True,timeout=timeout)
    require(result.returncode==0,'COMMAND_FAILED_'+args[0]+'_'+args[1])
    return result.stdout


def inspect(name):
    return json.loads(command('docker','inspect',name))[0]


def snapshot():
    return sorted(line for line in command('docker','ps','-a','--no-trunc','--format','{{.Names}} {{.ID}}')
                  .decode().splitlines() if line.split()[0] not in (API,GATEWAY))


def checked_backup(profile):
    receipt = read(ROOT/f'backup-profile-{profile}-verified.json')
    proof = read(Path(receipt['proof_path']))
    current = read(Path('/var/lib/socialmei/postgres040-backups/destination.private.json'))
    require(receipt['profile']==profile and current['schema']==profile and receipt['restored']
            and receipt['automatic_export_verified'] and proof['source_contents_compared']
            and proof['owned_cleanup_verified'] and proof['dump_sha256']==receipt['dump_sha256']
            and current['restore_receipt_file']==receipt['proof_path']
            and current['validated_backup_sha256']==receipt['dump_sha256'], 'CURRENT_BACKUP_NOT_VERIFIED')
    require(command('systemctl','is-active','socialmei-postgres040-backup.timer').strip()==b'active', 'BACKUP_TIMER_INACTIVE')


def frozen():
    plan=ROOT/'core-release-046.private.json'
    require(sha(plan)==EXPECTED, 'APPROVED_PLAN_DRIFT')
    state=read(plan)
    require(state['current_ledger']==41 and state['planned_ledger']==46, 'PLAN_SCOPE_DIVERGED')
    require(sha(ROOT/'schema-046.private.sql')==state['database_transaction_sha256'], 'SQL_DRIFT')
    require(sha(ROOT/'prechange041.dump')==state['verified_backup_sha256'], 'BACKUP_DRIFT')
    af=ROOT/'api-stage-046'
    gf=ROOT/'gateway-stage-046'
    require(sha(af/'gate.private.json')==state['api_gate_sha256'], 'API_PLAN_DRIFT')
    require(sha(gf/'pair.private.json')==state['gateway_pair_sha256'], 'GATEWAY_PLAN_DRIFT')
    api=read(af/'gate.private.json')
    gateway=read(gf/'pair.private.json')['gateway']
    receipt=read(ROOT/'migration-rehearsal.json')
    require(receipt['isolated_restore'] and receipt['source_ledger']==41
            and receipt['archive_sha256']==state['verified_backup_sha256']
            and receipt['tables_preserved']==82, 'MIGRATION_REHEARSAL_MISSING')
    stage={}
    for role,folder in (('api',af),('gateway',gf)):
        stage[role]={}
        for action in ('candidate','rollback'):
            path=folder/(action+'.compose.private.json')
            image=api['images'][action] if role=='api' else gateway[action]['image']
            expected=api['compose'][action] if role=='api' else gateway[action]['sha256']
            require(sha(path)==expected and inspect(image)['Id']==image, 'COMPOSE_OR_IMAGE_DRIFT')
            stage[role][action]={'path':str(path),'image':image}
    volumes=read(af/'candidate.compose.private.json')['services']['team-api']['volumes']
    for dest,expected in api['private_content'].items():
        bind=next(v for v in volumes if v['target']==dest)
        require(bind['read_only'] and sha(Path(bind['source']))==expected, 'API_PRIVATE_BIND_DRIFT')
    return stage,api


def ledger():
    value=command('docker','exec',PG,'psql','-X','-w','-qAt','-v','ON_ERROR_STOP=1','-U',
       'relocation_admin','-d',DB,'-c','SELECT current_database(),count(*),max(version) FROM socialmei.schema_migrations')
    expected=value.decode().strip().split('|')
    require(len(expected)==3 and expected[0]==DB,'DATABASE_IDENTITY_MISMATCH')
    return int(expected[1]),expected[2]


def compose_switch(role, action, stage):
    service=SERVICES[role][1]
    command('docker','compose','-p','socialmei-team','-f',stage[role][action]['path'],
        'up','-d','--no-deps','--no-build','--pull','never','--force-recreate',service)


def api_health(stage, action):
    entry=stage['api'][action]
    for _ in range(28):
        item=inspect(API)
        networks=item['NetworkSettings']['Networks']
        if (item['Image']==entry['image'] and item['State'].get('Health',{}).get('Status')=='healthy'
           and len(networks)==5 and 'socialmei-ig-api' in (networks.get('socialmei-instagram-ai-private',{}).get('Aliases') or [])
           and len(item['Mounts'])==7):
            break
        time.sleep(2)
    else:
        raise RuntimeError('API_HEALTH_FAILED')
    with_data="""from database import connect
with connect() as conn:
 conn.execute('SET TRANSACTION READ ONLY')
 assert conn.execute('SELECT current_database()').fetchone()[0]=='socialmei_candidate040_20261114'
 assert conn.execute('SELECT COUNT(*) FROM socialmei.schema_migrations').fetchone()[0]==46
"""
    command('docker','exec','-i',API,'python','-',data=with_data.encode())


def gateway_health(stage, action):
    entry=stage['gateway'][action]
    item=inspect(GATEWAY)
    require(item['Image']==entry['image'] and item['State']['Running']
            and len(item['Mounts'])==4 and len(item['NetworkSettings']['Networks'])==2, 'GATEWAY_START_FAILED')
    for _ in range(14):
        try:
            if action=='candidate':
                sources=ROOT/'api-public-package/frontend'
                for page in ('socialmei-app.html','scripts/v22-backend.js','scripts/v22-bootstrap.js','scripts/v79-central.js','scripts/v22-agenda.js'):
                    with urlopen(ORIGIN+'/frontend/'+page,timeout=6) as response:
                        require(response.status==200 and hashlib.sha256(response.read(4_000_000)).hexdigest()==sha(sources/page),
                                'PUBLIC_BYTES_DIVERGED')
            else:
                stage1=read(ROOT/'gateway-stage1/plan.private.json')
                for page,digest in stage1['expected'].items():
                    with urlopen(ORIGIN+'/frontend/'+page,timeout=6) as response:
                        require(response.status==200 and hashlib.sha256(response.read(4_000_000)).hexdigest()==digest,
                                'ROLLBACK_BYTES_DIVERGED')
            with urlopen(ORIGIN+'/api/v1/auth/session',timeout=6) as response:
                require(response.status==200, 'AUTH_SESSION_NOT_REACHABLE')
            return
        except (RuntimeError,OSError):
            time.sleep(2)
    raise RuntimeError('PUBLIC_HEALTH_FAILED')


def report(data):
    target=ROOT/'core-execution-result.json'
    temp=target.with_suffix('.tmp')
    with temp.open('x') as stream:
        json.dump(data,stream,sort_keys=True)
    temp.replace(target)
    print(json.dumps(data))


def rollback(stage, attempted):
    for role in reversed(attempted):
        compose_switch(role,'rollback',stage)
        if role=='gateway':
            gateway_health(stage,'rollback')
        else:
            api_health(stage,'rollback')
    report({'status':'rolled_back','roles':attempted,'ledger':46,'restored_database':False})


def apply(stage, api):
    require(ledger()==(41,'041_whatsapp_channel_lifecycle.sql'),'UNEXPECTED_STARTING_LEDGER')
    checked_backup('041')
    require(inspect(API)['Id']==api['original_id']
            and inspect(GATEWAY)['Image']==stage['gateway']['rollback']['image'],'LIVE_CONTAINER_DRIFT')
    before=snapshot()
    command('docker','exec','-i',PG,'psql','-X','-w','-q','-v','ON_ERROR_STOP=1','-U',
        'relocation_admin','-d',DB,data=(ROOT/'schema-046.private.sql').read_bytes())
    require(ledger()==(46,'046_inbox_pin_and_snooze.sql'),'POST_MIGRATION_LEDGER_UNEXPECTED')
    finish_cutover(stage,before)


def finish_cutover(stage,before):
    repair=ROOT/'backup-toolkit/tools/repair-m07-automatic-backup.py'
    try:
        proof=ROOT/'backup-profile-046-verified.json'
        if not proof.is_file():
            command('python3',str(repair),'046',timeout=420)
        checked_backup('046')
        backup=read(proof)
    except Exception:
        report({'status':'046_backup_gate_failed','ledger':46,'api_gateway_recreated':False})
        raise
    require(snapshot()==before,'UNRELATED_CONTAINERS_CHANGED')
    attempted=[]
    try:
        attempted.append('api')
        compose_switch('api','candidate',stage)
        api_health(stage,'candidate')
        attempted.append('gateway')
        compose_switch('gateway','candidate',stage)
        gateway_health(stage,'candidate')
        require(snapshot()==before,'UNRELATED_CONTAINERS_CHANGED')
    except BaseException:
        rollback(stage,attempted)
        raise
    report({'status':'published','ledger':46,'images':{k:v['candidate']['image'] for k,v in stage.items()},
            'unchanged_other_containers':True,'automatic_backup':backup,'plan_sha256':EXPECTED})


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['apply','complete','rollback'])
    parser.add_argument('--approved-plan',required=True)
    args=parser.parse_args()
    require(os.geteuid()==0 and args.approved_plan==EXPECTED, 'EXPLICIT_PLAN_REQUIRED')
    with (ROOT/'core046.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        stage,api=frozen()
        if args.operation=='apply':
            apply(stage,api)
        elif args.operation=='rollback':
            require(ledger()[0]==46, 'ROLLBACK_LEDGER_CHANGED')
            rollback(stage,['api','gateway'])
        else:
            previous=read(ROOT/'core-execution-result.json')
            require(previous['status']=='046_backup_gate_failed' and ledger()==(46,'046_inbox_pin_and_snooze.sql')
                    and inspect(API)['Id']==api['original_id']
                    and inspect(GATEWAY)['Image']==stage['gateway']['rollback']['image'],
                    'COMPLETION_REQUIRES_RECONCILIATION')
            finish_cutover(stage,snapshot())


if __name__=='__main__':
    try:
        main()
    except (RuntimeError,OSError,KeyError,ValueError,subprocess.TimeoutExpired) as error:
        reason=str(error)
        raise SystemExit(reason if reason.isupper() and ' ' not in reason else type(error).__name__) from None
