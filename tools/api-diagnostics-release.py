"""API-only diagnostic image update. Preserves existing egress; no SQL or gateway cutover."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import tarfile

spec=importlib.util.spec_from_file_location('api_egress_common',Path(__file__).with_name('team-api-egress.py'))
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
TARGET='041cf0b16154410adc633645662554760931c935'
BASE='3653da7d94063c7f9cd38c234fa6430db7c4d795'
TAG='socialmei-v22/team-api:'+TARGET
CHANGED={'python-service/instagram_http_transport.py','python-service/instagram_meta_adapter.py','python-service/test_instagram_http_transport.py','python-service/test_instagram_meta_adapter.py'}
require=common.require

def validate(before,after):
    expected=copy.deepcopy(before)
    expected['services']['team-api']['image']=TAG
    expected['services']['team-api'].setdefault('environment',{})['SOCIALMEI_RELEASE_SHA']=TARGET
    require(after==expected,'Unexpected API/config/network change.')

class Update(common.Egress):
    def command(self,live):
        labels=live['Config']['Labels']
        require(labels.get('com.docker.compose.project')=='socialmei-team' and labels.get('com.docker.compose.project.working_dir')==str(common.ROOT),'Unexpected project.')
        files=labels['com.docker.compose.project.config_files'].split(',')
        require(files[0]==str(common.ROOT/'compose.team.yaml') and all(Path(f).is_absolute() and Path(f).is_file() for f in files),'Effective Compose missing.')
        command=['docker','compose','--project-name','socialmei-team','--env-file',str(common.ROOT/'.env.team')]
        for path in files:command+=['-f',path]
        return command,files
    def prepare(self):
        require(not (self.folder/'api-diagnostic.private.json').exists(),'Already prepared.')
        meta=self.load('preparation.private.json')
        require(meta['candidate_sha']==TARGET and meta['missing_migrations']==[],'Candidate/schema mismatch.')
        for name,value in meta['hashes'].items():
            require(Path(name).name==name and common.digest(self.folder/name)==value,'Prepared artifacts changed.')
        changed=self.run(['git','diff','--name-only',BASE,TARGET,'--','python-service']).decode().splitlines()
        require(set(changed)==CHANGED,'API patch scope differs.')
        live=self.inspect(common.NAME);command,files=self.command(live)
        baseline=meta['installed_images']['team-api']
        require(live['Id']==baseline['container_id'] and live['Image']==baseline['image_id'] and live['Config']['Image']=='socialmei-v22/team-api:'+BASE,'Installed API changed.')
        require(live['State'].get('Health',{}).get('Status')=='healthy' and not live['HostConfig'].get('PortBindings') and not live['Mounts'],'Unexpected API health/ports/mounts.')
        require(self.inspect(live['Config']['Image'])['Id']==live['Image'],'Rollback tag changed.')
        before=self.model(command)
        require(before==self.load('team-api.before.private.json'),'Effective Compose differs.')
        api=before['services']['team-api']
        env=dict(item.split('=',1) for item in live['Config']['Env'])
        require(all(env.get(k)==str(v) for k,v in api.get('environment',{}).items()),'Runtime environment differs.')
        require(set(live['NetworkSettings']['Networks'])=={before['networks'][key]['name'] for key in api['networks']} and common.NETWORK in live['NetworkSettings']['Networks'],'Existing egress not preserved.')
        candidate=command+['-f',str(self.folder/'team-api.override.private.json')]
        after=self.model(candidate);validate(before,after)
        paths={Path(f) for f in files}|{common.ROOT/'.env.team'}
        require(all(p.is_file() and not p.is_symlink() for p in paths),'Private config unavailable.')
        with tarfile.open(self.folder/'api-runtime-backup.tar.gz','w:gz') as archive:
            for path in sorted(paths):archive.add(path,arcname=str(path).lstrip('/'))
        self.write('container.private.json',live)
        self.run(['docker','image','save','-o',str(self.folder/'api-rollback.tar'),live['Config']['Image']])
        source=self.folder/'api-source'
        require(not source.exists(),'Source folder already exists; review partial preparation.')
        package=self.folder/'api-source.tar'
        self.run(['git','archive','-o',str(package),TARGET,'python-service'])
        source.mkdir(mode=0o700)
        with tarfile.open(package) as archive:archive.extractall(source,filter='data')
        print('BUILDING API ONLY; existing services unchanged.',flush=True)
        self.run(['docker','build','--build-arg','SOCIALMEI_RELEASE_SHA='+TARGET,'-t',TAG,str(source/'python-service')])
        image=self.inspect(TAG)
        require(image['Config']['Labels'].get('org.opencontainers.image.revision')==TARGET,'Built image revision differs.')
        require(self.inspect(common.NAME)['Id']==live['Id'],'API changed during build.')
        artifacts={name:common.digest(self.folder/name) for name in ('container.private.json','api-runtime-backup.tar.gz','api-rollback.tar','team-api.override.private.json','team-api.before.private.json')}
        self.write('api-diagnostic.private.json',{'sha':TARGET,'container_id':live['Id'],'image_id':live['Image'],'candidate_image_id':image['Id'],'env':live['Config']['Env'],'mounts':live['Mounts'],'others':self.others(),'before_command':command,'candidate_command':candidate,'source_hashes':{str(p):common.digest(p) for p in paths},'artifact_hashes':artifacts})
        print('API DIAGNOSTIC PREPARED: '+str(self.folder)+'; no SQL or services changed.',flush=True)
    def guard(self,r):
        require(r['sha']==TARGET,'Wrong candidate.')
        live=self.inspect(common.NAME)
        require(live['Id']==r['container_id'] and live['Image']==r['image_id'] and sorted(live['Config']['Env'])==sorted(r['env']) and live['Mounts']==r['mounts'],'API baseline drift.')
        require(live['State'].get('Health',{}).get('Status')=='healthy' and not live['HostConfig'].get('PortBindings'),'API health/ports changed.')
        require(self.others()==r['others'],'Other services changed.')
        for path,value in r['source_hashes'].items():require(common.digest(Path(path))==value,'Private configuration changed.')
        for name,value in r['artifact_hashes'].items():require(common.digest(self.folder/name)==value,'Private artifact changed.')
        command,files=self.command(live)
        require(command==r['before_command'] and r['candidate_command']==command+['-f',str(self.folder/'team-api.override.private.json')],'Command scope changed.')
        before=self.model(command);after=self.model(r['candidate_command'])
        require(before==self.load('team-api.before.private.json'),'Compose baseline changed.')
        validate(before,after)
        require(self.inspect(TAG)['Id']==r['candidate_image_id'] and self.inspect(live['Config']['Image'])['Id']==r['image_id'],'Image drift.')
    def verify(self,r,candidate):
        expected=dict(r)
        if candidate:
            expected['image_id']=r['candidate_image_id']
            expected['env']=[('SOCIALMEI_RELEASE_SHA='+TARGET) if v.startswith('SOCIALMEI_RELEASE_SHA=') else v for v in r['env']]
        # Egress already exists before and after the image update.
        super().verify(expected,True)
    def apply(self):
        r=self.load('api-diagnostic.private.json');self.guard(r)
        try:
            self.run(common.up(r['candidate_command']));self.verify(r,True)
            self.write('api-diagnostic-installed.private.json',{'sha':TARGET,'api_id':self.inspect(common.NAME)['Id'],'gateway_changed':False,'sql_executed':False,'provider_flags_changed':False})
        except Exception:
            self.run(common.up(r['before_command']));self.verify(r,False)
            print('API IMAGE ROLLED BACK; egress preserved.',flush=True)
            raise
        print('API DIAGNOSTICS INSTALLED: '+TARGET+'; start one NEW authorization and inspect sanitized failure markers.',flush=True)

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
    task=Update(args.folder)
    if args.apply:task.apply()
    else:task.prepare()

if __name__=='__main__':
    try:main()
    except Exception:print('STOPPED: API-only update failed; private logs retained. Do not share logs.');raise SystemExit(1)
