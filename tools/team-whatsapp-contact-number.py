#!/usr/bin/env python3
"""Resolve a pilot LID to a verified display number. Read-only unless --apply.

Changes only a generic conversation label and its revision. Never changes contact
references, messages, channels, credentials, sender flags or provider sessions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid

ROOT = Path('/var/lib/socialmei-wa-pilot')
API = 'socialmei-team-team-api-1'
WAHA = 'socialmei-waha'
GENERIC = 'Contato do WhatsApp'
DB_CODE = r'''
import json,re,sys
from database import connect
from psycopg.rows import dict_row

def operate(data):
 op=data['operation']; cid=data['conversation_id']
 if op not in ('inspect','apply','rollback','candidates'): raise ValueError('operation')
 if op!='candidates' and (type(cid) is not int or cid<1): raise ValueError('operation')
 with connect() as c:
  c.row_factory=dict_row
  c.execute("SET LOCAL lock_timeout='3s'")
  c.execute("SET LOCAL statement_timeout='10s'")
  if op in ('inspect','candidates'): c.execute('SET TRANSACTION READ ONLY')
  if op=='candidates':
   return [r['id'] for r in c.execute("SELECT v.id FROM socialmei.me_conversations v WHERE v.workspace_id=1 "
    "AND v.origin='waha' AND v.contact_name='Contato do WhatsApp' AND EXISTS (SELECT 1 FROM socialmei.crm_canais c "
    "WHERE c.workspace_id=v.workspace_id AND v.account_ref='waha:'||c.identificador_conta "
    "AND c.provedor='waha' AND c.ativo AND c.ingress_provisioned AND c.instancia='socialmei-equipe-piloto' "
    "AND c.sessao='01') ORDER BY v.id LIMIT 200").fetchall()]
  lock='' if op=='inspect' else ' FOR SHARE OF c FOR UPDATE OF v'
  rows=c.execute("SELECT v.id,v.workspace_id,v.account_ref,v.contact_ref,v.contact_name,v.revision,"
   "c.id AS channel_id,c.versao AS channel_revision,c.instancia AS instance,c.sessao AS session,c.identificador_conta AS account_id "
   "FROM socialmei.me_conversations v JOIN socialmei.crm_canais c ON c.workspace_id=v.workspace_id "
   "AND v.account_ref='waha:'||c.identificador_conta WHERE v.workspace_id=1 AND v.id=%s AND v.origin='waha' "
   "AND c.provedor='waha' AND c.ativo AND c.ingress_provisioned AND c.instancia='socialmei-equipe-piloto' AND c.sessao='01'"+lock,(cid,)).fetchall()
  if len(rows)!=1: raise ValueError('binding')
  row=dict(rows[0])
  if op=='inspect': return row
  expected=data['expected']
  keys=['id','workspace_id','account_ref','contact_ref','channel_id','channel_revision','instance','session','account_id']
  if op=='apply': keys+=['contact_name','revision']
  if any(row[key]!=expected[key] for key in keys): raise ValueError('concurrent_change')
  desired=data['desired_name']
  if op=='apply':
   if row['contact_name']!='Contato do WhatsApp' or not re.fullmatch(r'\+[1-9][0-9]{6,14}',desired): raise ValueError('label')
  elif desired!='Contato do WhatsApp' or row['contact_name']!=data['expected_current_name']:
   raise ValueError('rollback_label_changed')
  updated=c.execute('UPDATE socialmei.me_conversations SET contact_name=%s,revision=revision+1 WHERE workspace_id=1 AND id=%s RETURNING id,revision',(desired,cid)).fetchone()
  return dict(updated)

if __name__=='__main__':
 try: print(json.dumps(operate(json.load(sys.stdin))))
 except Exception:
  print(json.dumps({'error':'database_operation_refused'}));raise SystemExit(1)
'''
NODE = r'''const fs=require('fs');(async()=>{
const b=JSON.parse(fs.readFileSync(0,'utf8')),key=process.env.WAHA_API_KEY;
if(!key)throw Error('auth');
const get=async path=>{const r=await fetch('http://127.0.0.1:3000'+path,{headers:{'X-Api-Key':key},signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error('lookup');return await r.json()};
const session=await get('/api/sessions/'+encodeURIComponent(b.session));
const lid=b.contact_ref.replace(/^waha:/,'');
if(lid.endsWith('@c.us')){process.stdout.write(JSON.stringify({session}));return;}
const forward=await get('/api/'+encodeURIComponent(b.session)+'/lids/'+encodeURIComponent(lid));
const reverse=typeof forward.pn==='string'?await get('/api/'+encodeURIComponent(b.session)+'/lids/pn/'+encodeURIComponent(forward.pn)):null;
process.stdout.write(JSON.stringify({session,forward,reverse}));
})().catch(()=>process.exit(1));'''


class Blocked(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise Blocked(code)


def docker(*args, data=None):
    result = subprocess.run(['docker', '--host=unix:///var/run/docker.sock', *args],
                            input=data, capture_output=True, timeout=45)
    require(result.returncode == 0, 'docker_operation_refused')
    return result.stdout


def database(operation, conversation_id, **fields):
    payload = json.dumps({'operation': operation, 'conversation_id': conversation_id, **fields}).encode()
    return json.loads(docker('exec', '-i', API, 'python', '-c', DB_CODE, data=payload))


def validate_binding(binding):
    require(binding.get('workspace_id') == 1 and binding.get('instance') == 'socialmei-equipe-piloto'
            and binding.get('session') == '01' and re.fullmatch(r'[0-9]+5976@c\.us', binding.get('account_id', ''))
            and binding.get('account_ref') == 'waha:' + binding['account_id']
            and re.fullmatch(r'waha:(?:[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid|[1-9][0-9]{6,14}@c\.us)', binding.get('contact_ref', '')),
            'pilot_binding_invalid')


def verified_phone(binding, mapping):
    validate_binding(binding)
    session = mapping.get('session') or {}
    engine = session.get('engine')
    engine = engine.get('engine') if isinstance(engine, dict) else engine
    require(session.get('name') == binding['session'] and session.get('status') == 'WORKING'
            and (session.get('me') or {}).get('id') == binding['account_id'] and engine == 'WEBJS',
            'session_identity_not_verified')
    forward, reverse = mapping.get('forward') or {}, mapping.get('reverse') or {}
    lid = binding['contact_ref'].removeprefix('waha:')
    if lid.endswith('@c.us'):
        require(lid != binding['account_id'], 'own_account_not_contact')
        return '+' + lid.removesuffix('@c.us')
    pn = forward.get('pn')
    require(isinstance(pn, str) and re.fullmatch(r'[1-9][0-9]{6,14}@c\.us', pn)
            and pn != binding['account_id'] and forward.get('lid') == lid
            and reverse.get('lid') == lid and reverse.get('pn') == pn,
            'bidirectional_phone_mapping_unavailable')
    return '+' + pn.removesuffix('@c.us')


def needs_update(binding, phone):
    if binding['contact_name'] == phone:
        return False
    require(binding['contact_name'] == GENERIC, 'existing_contact_label_preserved')
    return True


def validate_runtime(api):
    env = dict(item.split('=', 1) for item in api['Config'].get('Env', []) if '=' in item)
    require(api['State'].get('Health', {}).get('Status') == 'healthy'
            and env.get('SOCIALMEI_AUTH_ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on'}
            and env.get('SOCIALMEI_SHARED_DATA_ENABLED', '').lower() in {'1', 'true', 'yes', 'on'}
            and env.get('SOCIALMEI_WAHA_INGRESS_MODE') == 'team-pilot'
            and env.get('SOCIALMEI_WAHA_LAB_ENVIRONMENT') == 'team-pilot'
            and env.get('SOCIALMEI_WAHA_REGISTRY_FILE') == '/run/socialmei/private/waha-registry.json'
            and env.get('SOCIALMEI_WHATSAPP_BOT_ENABLED', 'false').strip().lower() in {'', '0', 'false', 'no', 'off'}, 'receive_only_runtime_required')


def private(path, mode, directory=False):
    require(not path.is_symlink() and (path.is_dir() if directory else path.is_file()), 'private_path_invalid')
    info = path.stat()
    require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == mode, 'private_permissions_invalid')


def save_snapshot(before, phone, source_sha):
    folder = ROOT / ('contact-number-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(mode=0o700)
    body = json.dumps({'version': 1, 'before': before, 'after_name': phone, 'source_sha': source_sha}, sort_keys=True).encode()
    for name, data in (('snapshot.json', body), ('snapshot.sha256', (hashlib.sha256(body).hexdigest()+'\n').encode())):
        fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
    require((folder / 'snapshot.json').read_bytes() == body, 'snapshot_write_failed')
    return folder


def read_snapshot(folder):
    require(folder.parent == ROOT and folder.name.startswith('contact-number-'), 'snapshot_outside_private_root')
    private(folder, 0o700, True)
    for name in ('snapshot.json', 'snapshot.sha256'):
        private(folder / name, 0o600)
    body = (folder / 'snapshot.json').read_bytes()
    require(len(body) <= 65536 and hashlib.sha256(body).hexdigest() == (folder / 'snapshot.sha256').read_text().strip(), 'snapshot_digest_failed')
    value = json.loads(body)
    require(value.get('version') == 1 and value['before']['contact_name'] == GENERIC, 'snapshot_shape_invalid')
    validate_binding(value['before'])
    return value


def validate_source(source_sha):
    require(os.geteuid() == 0, 'root_required_for_private_snapshot')
    private(ROOT, 0o700, True)
    source = Path(__file__).resolve().parents[1]
    require(source.name == 'source' and source.parent.parent == Path('/home/ubuntu/socialmei-backups'), 'source_stage_invalid')
    git = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture_output=True, timeout=15)
    require(re.fullmatch(r'[a-f0-9]{40}', source_sha) and git.returncode == 0 and git.stdout.decode().strip() == source_sha, 'source_sha_diverged')
    git = subprocess.run(['git', '-C', str(source), 'status', '--porcelain=v1', '--untracked-files=all'], capture_output=True, timeout=15)
    require(git.returncode == 0 and not git.stdout.strip(), 'source_stage_modified')


def validate_source_runtime(source_sha):
    validate_source(source_sha)
    api = json.loads(docker('inspect', API))[0]
    validate_runtime(api)
    return api


def operate(args):
    api = validate_source_runtime(args.source_sha)
    if args.rollback:
        require(args.confirm == 'TEAM-1', 'explicit_confirmation_required')
        snap = read_snapshot(args.rollback)
        before = snap['before']
        require(before['id'] == args.conversation_id, 'rollback_target_diverged')
        result = database('rollback', args.conversation_id, expected=before, desired_name=GENERIC,
                          expected_current_name=snap['after_name'])
        return {'action': 'contact_label_restored', 'conversation_id': result['id'], 'messages_changed': False}
    binding = database('inspect', args.conversation_id)
    validate_binding(binding)
    mapping = json.loads(docker('exec', '-i', WAHA, 'node', '-e', NODE, data=json.dumps(binding).encode()))
    phone = verified_phone(binding, mapping)
    change = needs_update(binding, phone)
    if not args.apply or not change:
        return {'action': 'read_only' if not args.apply else 'already_identified',
                'conversation_id': binding['id'], 'phone_verified': True, 'would_change': change, 'personal_identifiers_printed': False}
    require(args.confirm == 'TEAM-1', 'explicit_confirmation_required')
    current_api = json.loads(docker('inspect', API))[0]
    require(current_api['Id'] == api['Id'], 'api_changed_during_inspection')
    validate_runtime(current_api)
    saved = save_snapshot(binding, phone, args.source_sha)
    result = database('apply', args.conversation_id, expected=binding, desired_name=phone)
    return {'action': 'verified_contact_number_displayed', 'conversation_id': result['id'], 'revision': result['revision'],
            'backup': saved.name, 'phone_verified': True, 'contact_reference_changed': False,
            'messages_changed': False, 'provider_messages_sent': False, 'personal_identifiers_printed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--conversation-id', type=int, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--confirm')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        import fcntl
        require(os.geteuid() == 0, 'root_required_for_private_snapshot')
        private(ROOT, 0o700, True)
        fd = os.open(ROOT / 'contact-number.lock', os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = operate(args)
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({'action': 'stopped', 'error_code': str(exc) if isinstance(exc, Blocked) else 'operation_refused_details_suppressed'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
