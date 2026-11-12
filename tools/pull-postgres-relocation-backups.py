#!/usr/bin/env python3
"""Copy the isolated relocation backup off AWS. No production writes or cutover."""
import argparse
import base64
import csv
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

HOST = 'ubuntu@54.94.213.7'
REMOTE_ROOT = '/home/ubuntu/.socialmei-postgres-relocation-20261112'
ORIGINAL = '/home/ubuntu/.socialmei-instagram-86cdd5b/backup/prisma.dump'
TASK = 'SocialMEI PostgreSQL relocation external backup'
SHA256 = re.compile(r'^[0-9a-f]{64}$')

# This runs through sudo Python stdin. It never emits file contents or secrets.
REMOTE_PREPARE = r'''
import hashlib,json,os,tarfile,time,uuid
from pathlib import Path
os.umask(0o077)
root=Path('/home/ubuntu/.socialmei-postgres-relocation-20261112')
original=Path('/home/ubuntu/.socialmei-instagram-86cdd5b/backup/prisma.dump')
def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()
if root.is_symlink() or original.is_symlink() or not original.is_file():
    raise SystemExit(2)
receipt=json.loads((original.parent/'backup-receipt.json').read_text())
if sha(original)!=receipt['backup_sha256']:
    raise SystemExit(2)
candidates=[]
for path in (root/'backups').glob('destination-*.json'):
    if path.is_symlink():
        raise SystemExit(2)
    data=json.loads(path.read_text())
    dump=Path(data.get('dump_path',''))
    if (dump.parent!=root/'backups' or dump.suffix!='.dump' or dump.is_symlink()
        or not dump.is_file() or dump.stat().st_size!=data.get('bytes')
        or sha(dump)!=data.get('sha256')):
        continue
    candidates.append((data.get('created_at_utc',''),dump,path))
if not candidates:
    raise SystemExit(2)
_,latest,latest_receipt=sorted(candidates,key=lambda item:item[0])[-1]
folder=root/'external-packages'
folder.mkdir(mode=0o700,exist_ok=True)
if folder.is_symlink():
    raise SystemExit(2)
archive=folder/('configuration-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:12]+'.tar.gz')
members=set()
for pattern in ('*.private.env','*.private.json','*-receipt.json','*.crt'):
    members.update(root.glob(pattern))
members.update((root/'certificates').glob('*'))
members.update((root/'tools').glob('*.py'))
members.add(latest_receipt)
for path in members:
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        raise SystemExit(2)
with archive.open('xb') as output:
    os.chmod(archive,0o600)
    with tarfile.open(fileobj=output,mode='w:gz') as bundle:
        for path in sorted(members):
            bundle.add(path,arcname=str(path.relative_to(root)),recursive=False)
        bundle.add(original.parent/'backup-receipt.json',arcname='source-backup-receipt.json',recursive=False)
    output.flush()
    os.fsync(output.fileno())
items=[]
for kind,path in (('original-prisma',original),('isolated-destination',latest),('private-configuration',archive)):
    items.append({'kind':kind,'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)})
print(json.dumps({'historical_snapshot_only':True,'current_production_freshness_verified':False,'files':items}))
'''


def digest_file(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def checked_items(manifest):
    if (manifest.get('historical_snapshot_only') is not True
            or manifest.get('current_production_freshness_verified') is not False):
        raise ValueError('Snapshot provenance unavailable')
    items = manifest.get('files')
    expected = {'original-prisma', 'isolated-destination', 'private-configuration'}
    if not isinstance(items, list) or len(items) != 3 or {x.get('kind') for x in items} != expected:
        raise ValueError('Incomplete backup manifest')
    root = PurePosixPath(REMOTE_ROOT)
    for item in items:
        path = PurePosixPath(item.get('path', ''))
        if ('..' in path.parts or not path.is_absolute() or str(path) != item.get('path')
                or type(item.get('bytes')) is not int or item['bytes'] <= 0
                or not SHA256.fullmatch(str(item.get('sha256', '')))):
            raise ValueError('Invalid backup metadata')
        if item['kind'] == 'original-prisma':
            valid = str(path) == ORIGINAL
        elif item['kind'] == 'isolated-destination':
            valid = path.parent == root / 'backups' and bool(re.fullmatch(r'destination-[A-Za-z0-9_-]+\.dump', path.name))
        else:
            valid = path.parent == root / 'external-packages' and bool(re.fullmatch(r'configuration-[A-Za-z0-9_-]+\.tar\.gz', path.name))
        if not valid:
            raise ValueError('Unexpected remote file')
    return items


def windows_identity():
    value = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True,
                           text=True, check=True, timeout=20)
    row = next(csv.reader(io.StringIO(value.stdout.strip())))
    if len(row) != 2 or not re.fullmatch(r'S-1-[0-9-]+', row[1]):
        raise ValueError('Windows identity unavailable')
    return row[1]


def private_directory():
    if os.name != 'nt':
        raise ValueError('This off-host copy is configured for Windows')
    base = Path(os.environ['LOCALAPPDATA'])
    root = base / 'SocialMEI-Database-Backups' / 'postgres-relocation-20261112'
    for parent in (base, root.parent, root):
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise ValueError('Backup directory cannot be a link')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    sid = windows_identity()
    command = "$ErrorActionPreference='Stop';" + (
        "$sid=[System.Security.Principal.SecurityIdentifier]::new('{sid}');"
        "$acl=[System.Security.AccessControl.DirectorySecurity]::new();"
        "$acl.SetAccessRuleProtection($true,$false);"
        "$rule=[System.Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl',"
        "'ContainerInherit,ObjectInherit','None','Allow');$acl.AddAccessRule($rule);"
        # Persist only modified access rules; do not request owner or SACL privileges.
        "([System.IO.DirectoryInfo]::new('{path}')).SetAccessControl($acl);"
        "$verified=Get-Acl -LiteralPath '{path}';"
        "$rules=$verified.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]);"
        "if(-not $verified.AreAccessRulesProtected -or $rules.Count -ne 1 "
        "-or $rules[0].IdentityReference.Value -ne '{sid}' "
        "-or $rules[0].AccessControlType -ne 'Allow' "
        "-or $rules[0].FileSystemRights -ne [System.Security.AccessControl.FileSystemRights]::FullControl "
        "-or $rules[0].InheritanceFlags -ne 'ContainerInherit, ObjectInherit' "
        "-or $rules[0].PropagationFlags -ne 'None'){{throw 'Private ACL unavailable'}}"
    ).format(sid=sid, path=str(root).replace("'", "''"))
    encoded = base64.b64encode(command.encode('utf-16-le')).decode('ascii')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                   check=True, capture_output=True, timeout=30)
    return root


def ssh_args():
    key = Path(os.environ['LOCALAPPDATA']) / 'SocialMEI-SSH' / 'socialmei-aws-key.pem'
    if not key.is_file():
        raise ValueError('Existing SSH key unavailable')
    return ['ssh', '-i', str(key), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=12', HOST]


def copy_file(args, item, folder):
    name = item['kind'] + ('.tar.gz' if item['kind'] == 'private-configuration' else '.dump')
    partial = folder / (name + '.partial')
    target = folder / name
    if partial.exists() or target.exists():
        raise ValueError('Backup files are never overwritten')
    with partial.open('xb') as stream:
        os.chmod(partial, 0o600)
        result = subprocess.run(args + ['sudo', '-n', 'cat', '--', item['path']],
                                stdout=stream, stderr=subprocess.PIPE, timeout=180)
        stream.flush()
        os.fsync(stream.fileno())
    if (result.returncode or partial.stat().st_size != item['bytes']
            or digest_file(partial) != item['sha256']):
        raise ValueError('External copy did not pass content verification')
    # Windows rename refuses an existing destination, even if another process races.
    partial.rename(target)
    return {'kind': item['kind'], 'local_file': target.name,
            'bytes': item['bytes'], 'sha256': item['sha256'], 'verified': True}


def pull():
    root = private_directory()
    args = ssh_args()
    prepared = subprocess.run(args + ['sudo', '-n', 'python3', '-'], input=REMOTE_PREPARE.encode(),
                              capture_output=True, timeout=120)
    if prepared.returncode:
        raise ValueError('Remote verified backup package unavailable')
    manifest = json.loads(prepared.stdout)
    items = checked_items(manifest)
    folder = root / (datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:12])
    folder.mkdir(mode=0o700)
    verified = [copy_file(args, item, folder) for item in items]
    receipt = {'files': verified, 'historical_snapshot_only': True,
               'current_production_freshness_verified': False, 'cutover_authorized': False}
    with (folder / 'verified-copy.json').open('x', encoding='utf-8') as output:
        os.chmod(output.name, 0o600)
        json.dump(receipt, output, indent=2)
    print(json.dumps({'external_files_verified': len(verified), 'destination': str(folder),
                      'historical_snapshot_only': True, 'cutover_authorized': False}))


def task_xml(python, script, sid, working_directory):
    ns = 'http://schemas.microsoft.com/windows/2004/02/mit/task'
    ET.register_namespace('', ns)
    def child(parent, tag, text=None, **attributes):
        item = ET.SubElement(parent, '{' + ns + '}' + tag, attributes)
        item.text = text
        return item
    root = ET.Element('{' + ns + '}Task', {'version': '1.2'})
    triggers = child(root, 'Triggers')
    calendar = child(triggers, 'CalendarTrigger')
    child(calendar, 'StartBoundary', datetime.now().strftime('%Y-%m-%d') + 'T03:30:00')
    child(calendar, 'Enabled', 'true')
    child(child(calendar, 'ScheduleByDay'), 'DaysInterval', '1')
    logon = child(triggers, 'LogonTrigger')
    child(logon, 'Enabled', 'true')
    child(logon, 'UserId', sid)
    principal = child(child(root, 'Principals'), 'Principal', id='Author')
    child(principal, 'UserId', sid)
    child(principal, 'LogonType', 'InteractiveToken')
    child(principal, 'RunLevel', 'LeastPrivilege')
    settings = child(root, 'Settings')
    for tag, value in (('MultipleInstancesPolicy', 'IgnoreNew'), ('DisallowStartIfOnBatteries', 'false'),
                       ('StopIfGoingOnBatteries', 'false'), ('StartWhenAvailable', 'true'),
                       ('Enabled', 'true'), ('ExecutionTimeLimit', 'PT20M')):
        child(settings, tag, value)
    action = child(child(root, 'Actions', Context='Author'), 'Exec')
    child(action, 'Command', str(python))
    child(action, 'Arguments', '"' + str(script) + '"')
    child(action, 'WorkingDirectory', str(working_directory))
    return ET.tostring(root, encoding='utf-16', xml_declaration=True)


def parse_task_xml(raw):
    # schtasks may declare UTF-16 while using the console encoding on redirected output.
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')) or b'\x00' in raw[:32]:
        value = raw.decode('utf-16')
    else:
        try:
            value = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            value = raw.decode('mbcs')
    return ET.fromstring(value)


def install_task():
    root = private_directory()
    folder = root / 'tools'
    if folder.is_symlink() or (hasattr(folder, 'is_junction') and folder.is_junction()):
        raise ValueError('Backup task tools cannot be a link')
    folder.mkdir(mode=0o700, exist_ok=True)
    source = Path(__file__)
    installed = folder / ('pull-' + digest_file(source)[:16] + '.py')
    if installed.exists():
        if digest_file(installed) != digest_file(source):
            raise ValueError('Installed backup script integrity mismatch')
    else:
        with installed.open('xb') as output:
            os.chmod(installed, 0o600)
            output.write(source.read_bytes())
    xml = task_xml(sys.executable, installed, windows_identity(), root)
    definition = folder / ('task-' + uuid.uuid4().hex + '.xml')
    with definition.open('xb') as output:
        os.chmod(definition, 0o600)
        output.write(xml)
    # No /F: never replace a task that already exists. No password is stored.
    subprocess.run(['schtasks', '/Create', '/TN', TASK, '/XML', str(definition)],
                   check=True, capture_output=True, timeout=30)
    registered = subprocess.run(['schtasks', '/Query', '/TN', TASK, '/XML'],
                                check=True, capture_output=True, timeout=30)
    tree = parse_task_xml(registered.stdout)
    ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
    if (tree.findtext('.//t:Exec/t:Command', namespaces=ns) != sys.executable
            or tree.findtext('.//t:Exec/t:Arguments', namespaces=ns) != '"' + str(installed) + '"'
            or tree.findtext('.//t:Principal/t:LogonType', namespaces=ns) != 'InteractiveToken'):
        raise ValueError('Registered backup task differs from reviewed definition')
    print(json.dumps({'external_copy_task_installed': True, 'requires_computer_on_and_user_logged_on': True,
                      'scheduled_daily_and_at_logon': True, 'password_stored': False,
                      'production_cutover_executed': False}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-task', action='store_true', help='Install daily/at-logon interactive Windows task')
    args = parser.parse_args(argv)
    try:
        install_task() if args.install_task else pull()
        return 0
    except Exception:
        print('Private external backup unavailable. Check SSH, verified receipts and Windows permissions.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
