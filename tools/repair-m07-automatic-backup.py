"""Repair the existing automatic backup using the current reviewed ledger."""
import argparse
import contextlib
import io
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import tempfile

ROOT = Path('/var/lib/socialmei/postgres040-backups')
CONFIG = ROOT/'destination.private.json'
ENV = Path('/etc/socialmei/backup040.private.env')
UNIT = 'socialmei-postgres040-backup.service'
TIMER = 'socialmei-postgres040-backup.timer'
LOCK = Path('/run/lock/socialmei-backup040.lock')
RELEASE = Path('/var/lib/socialmei/production-consolidation-m07/preflight-bfvgu3zz')
DB = 'socialmei_candidate040_20261114'
PG = 'socialmei-postgres-relocation-20261112'
PACKAGE = Path(__file__).resolve().parents[1]


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def run(*args, timeout=180):
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    require(result.returncode == 0, 'FAILED_' + '_'.join(args[:2]))
    return result.stdout


def load(name):
    path = PACKAGE/'tools'/name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, sort_keys=True)


def atomic(path, data):
    temp = path.with_name(path.name + '.m07.new')
    with temp.open('xb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def mem_guard():
    page = Path('/proc/meminfo').read_text()
    available = int(re.search(r'MemAvailable:\s+(\d+)', page)[1])
    require(available >= 375*1024, 'MEMORY_RESERVE_TOO_LOW')


def config_lock():
    lock = LOCK.open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return lock


def restore(receipt, folder, profile, helper):
    mem_guard()
    backup = load('aws-postgres-backup.py')
    recovery = load('backup-restore-rehearsal.py')
    dump = Path(receipt['dump_path'])
    manifest = Path(receipt['manifest_path'])
    require(receipt['schema']==int(profile) and receipt['database']==DB and receipt['shared_snapshot']
            and backup.file_sha256(dump)==receipt['sha256']
            and backup.file_sha256(manifest)==receipt['manifest_sha256'], 'BACKUP_ARTIFACT_INVALID')
    approval=folder/'restore-input.json'
    write(approval, {'explicit_authorization':True,'scope':'isolated_restore','production_mutation':False,
        'dump_sha256':receipt['sha256'],'manifest_sha256':receipt['manifest_sha256'],'profile':profile,
        'postgres_major':17,'postgres_image_id':run('docker','inspect','-f','{{.Image}}',PG).decode().strip(),
        'validator_api_image_id':helper})
    proof=recovery.rehearse(dump,manifest,approval,compact=True)
    require(proof['restoration_verified'] and proof['source_contents_compared'] and proof['owned_cleanup_verified']
            and proof['dump_sha256']==receipt['sha256'], 'RESTORE_PROOF_INVALID')
    path=folder/'restore-proof.json'
    write(path,proof)
    return path,proof


def profile_ready(profile):
    previous = json.loads(CONFIG.read_text())
    require(previous['schema'] in ('040','041') and previous['current_production_backup'] is True and
            previous['backup_target_approved'] is True and previous['container']==PG and previous['database']==DB
            and not (ROOT/'s3-backup.private.json').exists(), 'BACKUP_TARGET_DIVERGED')
    core = RELEASE/'core-release-046.private.json'
    require(hashlib.sha256(core.read_bytes()).hexdigest() ==
            '94c52c116bae9de5a6db1711a66b73dfd3800fb94547b71da2e8277e85dd3be7', 'FROZEN_CORE_PLAN_CHANGED')
    base_id = previous['export_helper_image_id']
    require(re.fullmatch(r'sha256:[a-f0-9]{64}',base_id) is not None,'UNEXPECTED_BACKUP_IMAGE')
    helper_tag='socialmei-backup-m07:reviewed'
    previous_helper='socialmei-backup-m07:base040'
    if profile=='041':
        mem_guard()
        run('docker','image','tag',base_id,previous_helper)
        dockerfile=RELEASE/'m07-backup.Dockerfile'
        contents = (f'FROM {previous_helper}\nCOPY tools/postgres-source-export.py tools/postgres-copy-validate.py /backup/tools/\n'
                    'COPY database/migrations/*.sql /backup/database/migrations/\n')
        if dockerfile.exists():
            require(dockerfile.read_text() == contents, 'BACKUP_BUILD_CHANGED')
        else:
            with dockerfile.open('x',encoding='ascii') as handle:
                handle.write(contents)
        run('docker','build','--pull=false','--network=none','-f',str(dockerfile),'-t',helper_tag,str(PACKAGE))
    helper=run('docker','image','inspect','-f','{{.Id}}',helper_tag).decode().strip()
    require(re.fullmatch(r'sha256:[a-f0-9]{64}',helper) is not None,'BACKUP_HELPER_MISSING')
    configuration={**previous,'schema':profile,'source':f'approved_schema{profile}_destination',
                   'export_helper_image_id':helper,'export_container_admin':True}
    return configuration,helper


def fresh_bootstrap_proof(profile, backup):
    for folder in sorted(RELEASE.glob('backup-profile-'+profile+'-*')):
        path=folder/'restore-proof.json'
        if not path.is_file() or time.time()-path.stat().st_mtime>1800:
            continue
        proof=json.loads(path.read_text())
        if (proof.get('profile')!=profile or proof.get('verification_mode')!='full_comparison'
                or not all(proof.get(key) is True for key in ('restoration_verified','source_contents_compared',
                                                           'archive_integrity_verified','owned_cleanup_verified'))
                or proof.get('production_mutation') is not False):
            continue
        for dump in folder.glob('backups/destination-*.dump'):
            if backup.file_sha256(dump)==proof['dump_sha256']:
                return path,proof['dump_sha256']
    return None


def automatic(profile):
    folder=Path(tempfile.mkdtemp(prefix='backup-profile-'+profile+'-',dir=RELEASE))
    original_config=CONFIG.read_bytes()
    original_env=ENV.read_bytes()
    (folder/'old-config.private.json').write_bytes(original_config)
    (folder/'old-unit.private.env').write_bytes(original_env)
    config,helper=profile_ready(profile)
    backup=load('aws-postgres-backup.py')
    backup.ROOT=folder
    backup.current_database_provenance(config)
    # Establish an approved full-restore receipt before making the profile eligible for the timer.
    previous_proof=fresh_bootstrap_proof(profile,backup)
    if previous_proof:
        restore_path,restore_hash=previous_proof
    else:
        capture=io.StringIO()
        with config_lock(), contextlib.redirect_stdout(capture):
            backup.backup(config=config,with_manifest=True)
        bootstrap=json.loads(capture.getvalue())
        restore_path,_=restore(bootstrap,folder,profile,helper)
        restore_hash=bootstrap['sha256']
    config.update(restore_receipt_file=str(restore_path),validated_backup_sha256=restore_hash)
    replacement=original_env
    for key,script in (('SOCIALMEI_BACKUP_SCRIPT','aws-postgres-backup.py'),
                       ('SOCIALMEI_BACKUP_RETENTION_SCRIPT','backup-retention.py')):
        pattern=rb'(?m)^'+key.encode()+rb'=[^\r\n]+'
        replacement,count=re.subn(pattern,key.encode()+b'='+str(PACKAGE/'tools'/script).encode(),replacement)
        require(count==1,'BACKUP_UNIT_ENV_DIVERGED')
    try:
        with config_lock():
            require(CONFIG.read_bytes()==original_config and ENV.read_bytes()==original_env,'BACKUP_UNIT_CHANGED')
            atomic(CONFIG,json.dumps(config,sort_keys=True).encode())
            atomic(ENV,replacement)
        started=time.time()
        run('systemctl','reset-failed',UNIT)
        run('systemctl','start',UNIT,timeout=220)
        require(run('systemctl','show',UNIT,'-p','Result','--value').strip()==b'success'
                  and run('systemctl','is-active',TIMER).strip()==b'active', 'AUTOMATIC_RUN_NOT_HEALTHY')
        backups=sorted(
            (p for p in (ROOT/'backups').glob('destination-*.json')
             if re.fullmatch(r'destination-\d{8}T\d{6}Z(?:-[a-f0-9]+)?\.json',p.name)),
            key=lambda p:p.stat().st_mtime,reverse=True)
        require(bool(backups) and backups[0].stat().st_mtime>=started-1,'SCHEDULED_DUMP_NOT_FRESH')
        result=json.loads(backups[0].read_text())
        final=folder/'scheduled'
        final.mkdir(mode=0o700)
        proof_path,proof=restore(result,final,profile,helper)
        # Keep the verified periodic run as the durable configuration receipt.
        config.update(restore_receipt_file=str(proof_path),validated_backup_sha256=result['sha256'])
        with config_lock():
            atomic(CONFIG,json.dumps(config,sort_keys=True).encode())
        summary={'profile':profile,'timer_active':True,'automatic_export_verified':True,'restored':True,
                 'tables':proof['tables_verified'],'dump_sha256':proof['dump_sha256'],'helper':helper}
        summary['proof_path']=str(proof_path)
        write(folder/'automatic-result.json',summary)
        write(RELEASE/('backup-profile-'+profile+'-verified.json'),summary)
        print(json.dumps(summary))
    except BaseException:
        with config_lock():
            atomic(CONFIG,original_config)
            atomic(ENV,original_env)
        raise


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile',choices=['041','046'])
    args=parser.parse_args()
    require(os.geteuid()==0 and RELEASE in PACKAGE.parents,'AUTHORIZED_RELEASE_CONTEXT_REQUIRED')
    automatic(args.profile)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        msg=str(error) if re.fullmatch(r'[A-Z0-9_-]+',str(error)) else type(error).__name__
        raise SystemExit('BACKUP_GATE:'+msg) from None
