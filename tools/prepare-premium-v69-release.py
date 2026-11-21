"""Stage and inspect the approved v6.9 files; never deploy or restart a service."""
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
import re
import posixpath
from pathlib import Path, PurePosixPath
import zipfile

spec=importlib.util.spec_from_file_location('crm_preflight',Path(__file__).with_name('prepare-crm233-release.py'))
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
require=base.require
GATEWAY='socialmei-team-team-gateway-1'
API='socialmei-team-team-api-1'
PREMIUM_ID='sha256:b93aeac93d11ea0e88dd2c44961bc8f13df9bcb928d960b3562563e68b6cc8ec'
API_ID='sha256:6cf2bc60fec3f31e5e0cc24d4e276a7ba43911e94343e1439dce75d84a5673f8'
REVIEWED_FILE_COUNT=48
PROTECTED={'frontend/config.js','frontend/scripts/auth-store.js','frontend/scripts/v22-inbox-customer.js'}

def sha(value):return hashlib.sha256(value).hexdigest()


def frontend_dependencies(candidate, read_runtime):
    """Resolve static document/script/style references against the actual overlay."""
    queue=list(candidate)+['frontend/entrada.html','frontend/socialmei-app.html']
    checked=set();missing=set()
    while queue:
        path=queue.pop()
        if path in checked:continue
        checked.add(path)
        content=candidate.get(path)
        if content is None:content=read_runtime(path)
        if content is None:
            missing.add(path);continue
        if not path.endswith(('.html','.js','.css')):continue
        source=content.decode('utf-8',errors='replace')
        refs=re.findall(r'''(?:\b(?:src|href)\s*=|\.(?:src|href)\s*=)\s*["']([^"']+)["']''',source)
        refs+=re.findall(r'''["']((?:scripts|styles|assets|telas)/[A-Za-z0-9_./-]+\.(?:js|css|html|png|svg|ico|jpg|webp|woff2?))(?:[?#][^"']*)?["']''',source)
        css_refs=re.findall(r'''url\(\s*["']?([^\s'"\)]+)["']?\s*\)''',source) if path.endswith('.css') else []
        for ref in refs+css_refs:
            ref=ref.split('#')[0].split('?')[0]
            if not ref or ':' in ref or ref.startswith('//'):continue
            if not re.fullmatch(r'[A-Za-z0-9_./-]+',ref):continue
            if ref.startswith('/'):
                target=posixpath.normpath(ref.lstrip('/'))
            else:
                parent=posixpath.dirname(path) if not path.endswith('.js') else 'frontend'
                target=posixpath.normpath(posixpath.join(parent,ref))
            # Navigation outside /frontend is not a static frontend asset.
            if target.startswith('frontend/') and '.' in PurePosixPath(target).name:queue.append(target)
    return {'checked':len(checked),'missing':sorted(missing)}


def runtime_asset(path):
    require(bool(re.fullmatch(r'frontend/[A-Za-z0-9_./-]+',path)) and '..' not in PurePosixPath(path).parts,
            'INVALID_DEPENDENCY_PATH')
    value=base.run(['docker','exec',GATEWAY,'sh','-c',
                   'if [ -f /srv/'+path+' ]; then base64 /srv/'+path+'; else printf MISSING; fi'])
    return None if value=='MISSING' else base64.b64decode(value,validate=False)


def require_dependencies(candidate):
    result=frontend_dependencies(candidate,runtime_asset)
    require(not result['missing'],'MISSING_FRONTEND_DEPENDENCIES:'+','.join(result['missing']))
    return result

def candidate_files(manifest):
    rows=manifest['candidate_files']
    paths=[r['path'] for r in rows]
    require(len(paths)==len(set(paths)) and bool(paths),'DUPLICATE_OR_EMPTY_CANDIDATE')
    for row in rows:
        p=PurePosixPath(row['path'])
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in row['path']
                and p.parts[0]=='frontend' and len(p.parts)>1 and p.as_posix()==row['path']
                and re.fullmatch(r'frontend/[A-Za-z0-9_./-]+',row['path']), 'INVALID_CANDIDATE_PATH')
        require(row['path'] not in PROTECTED,'PROTECTED_ASSET_IN_CANDIDATE')
        require(len(row['sha256'])==64,'INVALID_ASSET_DIGEST')
    return rows

def validate_delta(before,after,files,directory):
    expected=copy.deepcopy(before)
    service=expected['services']['team-gateway']
    require(service['image'] in {base.PREMIUM,PREMIUM_ID},'COMPOSE_PREMIUM_DIVERGENTE')
    new={}
    for row in files:
        target='/srv/'+row['path']
        new[target]={'type':'bind','source':str(directory/row['path']),'target':target,'read_only':True,'bind':{'create_host_path':False}}
    volumes={v['target']:v for v in service.get('volumes',[])}
    volumes.update(new)
    service['volumes']=list(volumes.values())
    actual=copy.deepcopy(after)
    for doc in (expected,actual):
        doc['services']['team-gateway']['volumes']=sorted(doc['services']['team-gateway'].get('volumes',[]),key=lambda v:v['target'])
    require(expected==actual,'DELTA_EXCEEDS_REVIEWED_FRONTEND_BINDS')
    return new

def private_json(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n')
    path.chmod(0o600)

def prepare(package):
    package=Path(package).resolve(strict=True)
    require(package.is_dir() and not package.is_symlink(),'INVALID_PACKAGE')
    manifest=json.loads((package/'integration.json').read_text())
    files=candidate_files(manifest)
    require(len(files)==REVIEWED_FILE_COUNT,'REVIEWED_FILE_COUNT_CHANGED')
    archive=package/'candidate.zip'
    require(sha(archive.read_bytes())==manifest['artifact']['sha256'],'ARCHIVE_HASH_MISMATCH')
    with zipfile.ZipFile(archive) as z:
        require(sorted(z.namelist())==sorted(r['path'] for r in files),'ARCHIVE_FILE_LIST_DIFFERS')
        for row in files:
            require(sha(z.read(row['path']))==row['sha256'],'ARCHIVE_ASSET_HASH_MISMATCH')
        candidate={row['path']:z.read(row['path']) for row in files}
    gateway,api=base.inspect(GATEWAY),base.inspect(API)
    require(gateway['Image']==PREMIUM_ID and gateway['Config']['Image'] in {base.PREMIUM,PREMIUM_ID},'PREMIUM_IMAGE_CHANGED')
    require(api['Image']==API_ID and api['State'].get('Health',{}).get('Status')=='healthy','API_IMAGE_OR_HEALTH_CHANGED')
    require(gateway['State']['Running'],'GATEWAY_NOT_RUNNING')
    command,folder,chain=base.chain(gateway,'team-gateway')
    before=json.loads(base.run(command+['config','--format','json'],cwd=folder))
    base.validate_runtime(before['services']['team-gateway'],gateway,before)
    require_dependencies(candidate)
    stage=package/'frozen-plan'
    stage.mkdir(mode=0o700)
    assets=stage/'candidate'
    assets.mkdir(mode=0o700)
    with zipfile.ZipFile(archive) as z:
        for row in files:
            path=assets/row['path'];path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with path.open('xb') as f:f.write(z.read(row['path']))
            path.chmod(0o444)
    overlay={'services':{'team-gateway':{'volumes':[{'type':'bind','source':str(assets/r['path']),'target':'/srv/'+r['path'],'read_only':True,'bind':{'create_host_path':False}} for r in files]}}}
    after=json.loads(base.run(command+['-f','-','config','--format','json'],source=json.dumps(overlay),cwd=folder))
    validate_delta(before,after,files,assets)
    # Save exact bytes, effective config and identities privately before approval.
    originals=stage/'original-compose'
    originals.mkdir(mode=0o700)
    for i,path in enumerate(chain):
        destination=originals/(str(i)+'-'+Path(path).name)
        with destination.open('xb') as f:f.write(Path(path).read_bytes())
        destination.chmod(0o600)
    private_json(stage/'baseline-compose.json',before)
    private_json(stage/'candidate-compose.json',after)
    rollback=copy.deepcopy(before)
    rollback['services']['team-gateway']['image']=gateway['Image']
    private_json(stage/'rollback-compose.json',rollback)
    private_json(stage/'overlay.json',overlay)
    private_json(stage/'gateway-inspect.json',gateway)
    private_json(stage/'api-inspect.json',api)
    mounted_files={}
    private_mounts=stage/'original-private-mounts'
    private_mounts.mkdir(mode=0o700)
    for i,mount in enumerate(gateway.get('Mounts',[])):
        path=Path(mount['Source'])
        if mount['Type']=='bind' and path.is_file():
            data=path.read_bytes();saved=private_mounts/str(i)
            with saved.open('xb') as f:f.write(data)
            saved.chmod(0o600)
            mounted_files[str(path)]=sha(data)
    protected={}
    for name in PROTECTED:
        code="sha256sum /srv/"+name
        protected[name]=base.run(['docker','exec',GATEWAY,'sh','-c',code]).split()[0]
    require(protected['frontend/scripts/v22-inbox-customer.js']==base.JS_HASH,'CRM233_RUNTIME_HASH_CHANGED')
    before_files={}
    old_assets=stage/'original-assets'
    old_assets.mkdir(mode=0o700)
    for row in files:
        # Missing new files are expected; capture current bytes for changed files.
        output=base.run(['docker','exec',GATEWAY,'sh','-c','if [ -f /srv/'+row['path']+' ]; then sha256sum /srv/'+row['path']+'; else printf MISSING; fi'])
        before_files[row['path']]=output.split()[0]
        if before_files[row['path']]!='MISSING':
            old=old_assets/row['path'];old.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            base.run(['docker','cp',GATEWAY+':/srv/'+row['path'],str(old)])
            old.chmod(0o600)
            require(sha(old.read_bytes())==before_files[row['path']],'LIVE_ASSET_CHANGED_DURING_BACKUP')
    result={'mode':'prepared_not_applied','api_image_id':api['Image'],'premium_image_id':gateway['Image'],'gateway_container_id':gateway['Id'],
      'candidate_files':files,'protected_runtime_hashes':protected,'prior_asset_hashes':before_files,
      'mounted_private_file_hashes':mounted_files,
      'compose_chain_sha256':base.digest(chain),'baseline_sha256':base.digest(before),'candidate_sha256':base.digest(after),
      'rollback_sha256':base.digest(rollback),
      'permitted_delta':str(REVIEWED_FILE_COUNT)+'_reviewed_frontend_readonly_file_binds_only','affected_services':['team-gateway'],
      'restart_required_after_approval':['team-gateway'],'api_restart':False,'migrations':False,'database_writes':False,
      'workers_changed':False,'channels_changed':False,'production_services_modified':False,
      'rollback':'Frozen rollback-compose.json with immutable premium image ID; recreate only team-gateway with --no-deps --no-build --pull never. Keep original CRM233 bind and all private mounts.',
      'approval_required':True}
    result['plan_sha256']=base.digest(result)
    private_json(stage/'approval-plan.json',result)
    return result

def verify(package):
    """Fresh read-only gate for an already frozen package; never regenerates it."""
    package=Path(package).resolve(strict=True)
    stage=package/'frozen-plan'
    plan=json.loads((stage/'approval-plan.json').read_text())
    expected=dict(plan);digest=expected.pop('plan_sha256')
    require(base.digest(expected)==digest,'APPROVAL_PLAN_CHANGED')
    for name,key in [('baseline-compose.json','baseline_sha256'),('candidate-compose.json','candidate_sha256'),('rollback-compose.json','rollback_sha256')]:
        require(base.digest(json.loads((stage/name).read_text()))==plan[key],'FROZEN_COMPOSE_CHANGED')
    gateway,api=base.inspect(GATEWAY),base.inspect(API)
    for current,name in [(gateway,'gateway'),(api,'api')]:
        frozen=json.loads((stage/(name+'-inspect.json')).read_text())
        require(all(current[key]==frozen[key] for key in ['Id','Image','Config','HostConfig','Mounts']),'LIVE_SERVICE_BASELINE_CHANGED')
    command,folder,chain=base.chain(gateway,'team-gateway')
    before=json.loads(base.run(command+['config','--format','json'],cwd=folder))
    require(base.digest(before)==plan['baseline_sha256'],'EFFECTIVE_COMPOSE_CHANGED')
    base.validate_runtime(before['services']['team-gateway'],gateway,before)
    require(json.loads(base.run(['docker','image','inspect',base.PREMIUM]))[0]['Id']==plan['premium_image_id'],'PREMIUM_TAG_CHANGED')
    for row in plan['candidate_files']:
        require(sha((stage/'candidate'/row['path']).read_bytes())==row['sha256'],'STAGED_ASSET_CHANGED')
    require_dependencies({row['path']:(stage/'candidate'/row['path']).read_bytes() for row in plan['candidate_files']})
    for name,expected in plan['protected_runtime_hashes'].items():
        require(base.run(['docker','exec',GATEWAY,'sh','-c','sha256sum /srv/'+name]).split()[0]==expected,'PROTECTED_RUNTIME_ASSET_CHANGED')
    for name,expected in plan['prior_asset_hashes'].items():
        observed=base.run(['docker','exec',GATEWAY,'sh','-c','if [ -f /srv/'+name+' ]; then sha256sum /srv/'+name+'; else printf MISSING; fi']).split()[0]
        require(observed==expected,'LIVE_FRONTEND_ASSET_CHANGED')
    for name,expected in plan['mounted_private_file_hashes'].items():
        require(sha(Path(name).read_bytes())==expected,'MOUNTED_PRIVATE_FILE_CHANGED')
    require(api['State'].get('Health',{}).get('Status')=='healthy' and gateway['State']['Running'],'SERVICE_UNHEALTHY')
    return {'mode':'verified_not_applied','plan_sha256':digest,'production_services_modified':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--verify',action='store_true');args=p.parse_args()
    try:print(json.dumps(verify(args.package) if args.verify else prepare(args.package)))
    except Exception as error:
        print(json.dumps({'complete':False,'production_services_modified':False,'reason':str(error) if isinstance(error,RuntimeError) else type(error).__name__}))
        raise SystemExit(1)
