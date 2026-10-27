"""Optional API-only egress. Prepare by default; no SQL, new images or provider sends."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT=Path('/home/ubuntu/socialmei-team')
BACKUPS=Path('/home/ubuntu/socialmei-backups')
NAME='socialmei-team-team-api-1'
NETWORK='socialmei_team_egress'
IMAGE='socialmei-v22/team-api:3653da7d94063c7f9cd38c234fa6430db7c4d795'
ORIGIN='https://socialmei-ia.54-94-213-7.sslip.io'

def require(ok,message):
    if not ok:raise RuntimeError(message)

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def validate_delta(before,after):
    require('egress' not in before['networks'] and 'egress' not in before['services']['team-api']['networks'],'Egress already configured.')
    network=after['networks'].get('egress',{})
    require(network.get('name')==NETWORK and network.get('driver','bridge')=='bridge' and network.get('internal',False) is False and set(network)<= {'name','driver','internal','ipam'} and not network.get('ipam'),'Unexpected egress network settings.')
    require(after['services']['team-api']['networks'].get('egress') in (None,{}),'Unexpected API egress settings.')
    expected=copy.deepcopy(before)
    expected['networks']['egress']=network
    expected['services']['team-api']['networks']['egress']=after['services']['team-api']['networks']['egress']
    require(after==expected,'Changes exceed API egress network.')

def up(command):return command+['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','team-api']

class Egress:
    def __init__(self,folder):
        self.folder=folder
        require(folder.parent==BACKUPS and folder.is_dir() and not folder.is_symlink(),'Use a private folder directly under backups.')
        require(folder.stat().st_uid==os.geteuid() and not folder.stat().st_mode&0o077,'Private folder permissions required.')
        self.lock=open(BACKUPS/'.v25-publication.lock','a')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def run(self,args):
        result=subprocess.run(args,cwd=ROOT,capture_output=True,timeout=180)
        with (self.folder/'operations.private.log').open('ab') as output:
            output.write(result.stdout);output.write(result.stderr)
        require(result.returncode==0,'Command failed; private log retained. Do not share it.')
        return result.stdout
    def write(self,name,value):(self.folder/name).write_text(json.dumps(value,indent=2))
    def load(self,name):return json.loads((self.folder/name).read_text())
    def inspect(self,name):return json.loads(self.run(['docker','inspect',name]))[0]
    def others(self):return sorted(row for row in self.run(['docker','ps','-a','--no-trunc','--format','{{.Names}} {{.ID}}']).decode().splitlines() if not row.startswith(NAME+' '))
    def model(self,command):return json.loads(self.run(command+['config','--format','json']))
    def network_absent(self):require(NETWORK not in self.run(['docker','network','ls','--format','{{.Name}}']).decode().splitlines(),'Egress network already exists; review before proceeding.')
    def runtime(self,model,live):
        api=model['services']['team-api']
        require(live['State'].get('Health',{}).get('Status')=='healthy','API unhealthy.')
        require(live['Config']['Image']==IMAGE and self.inspect(IMAGE)['Id']==live['Image'],'Unexpected API image.')
        require(not api.get('ports') and not live['HostConfig'].get('PortBindings'),'API must not publish ports.')
        expected={model['networks'][k]['name'] for k in api['networks']}
        require(set(live['NetworkSettings']['Networks'])==expected,'Runtime networks differ from Compose.')
        require(set(api['networks'])=={'api','database'},'Unexpected initial API networks.')
        env=dict(v.split('=',1) for v in live['Config']['Env'])
        require(all(env.get(k)==str(v) for k,v in api.get('environment',{}).items()),'Runtime environment differs from Compose.')
        mounts={(m['Type'],m['Source'],m['Destination'],m['RW']) for m in live['Mounts']}
        expected_mounts={(v['type'],v['source'],v['target'],not v.get('read_only',False)) for v in api.get('volumes',[])}
        require(mounts==expected_mounts,'Runtime mounts differ from Compose.')
    def prepare(self):
        require(not (self.folder/'receipt.private.json').exists(),'Already prepared.')
        self.network_absent()
        live=self.inspect(NAME);labels=live['Config']['Labels']
        require(labels.get('com.docker.compose.project')=='socialmei-team' and labels.get('com.docker.compose.project.working_dir')==str(ROOT),'Unexpected Compose project.')
        files=labels['com.docker.compose.project.config_files'].split(',')
        require(files[0]==str(ROOT/'compose.team.yaml') and all(Path(f).is_absolute() and Path(f).is_file() for f in files),'Effective Compose files missing.')
        command=['docker','compose','--project-name','socialmei-team','--env-file',str(ROOT/'.env.team')]
        for f in files:command+=['-f',f]
        before=self.model(command);self.runtime(before,live)
        for name in live['NetworkSettings']['Networks']:
            require(self.inspect(name)['Internal'] is True,'Initial API network is not internal.')
        overlay={'services':{'team-api':{'networks':dict(before['services']['team-api']['networks'],egress=None)}},'networks':{'egress':{'name':NETWORK,'driver':'bridge','internal':False}}}
        self.write('egress.override.private.json',overlay)
        candidate=command+['-f',str(self.folder/'egress.override.private.json')]
        after=self.model(candidate);validate_delta(before,after)
        self.write('before.private.json',before);self.write('candidate.private.json',after);self.write('container.private.json',live)
        paths={Path(f) for f in files}|{ROOT/'.env.team'}
        for m in live['Mounts']:
            require(m['Type']=='bind','API volume requires explicit review.')
            paths.add(Path(m['Source']))
        selected=[]
        for path in sorted(paths,key=lambda p:(len(p.parts),str(p))):
            require(path.is_file() and not path.is_symlink(),'Only regular private configuration files supported.')
            selected.append(path)
        with tarfile.open(self.folder/'runtime-config.tar.gz','w:gz') as archive:
            for path in selected:archive.add(path,arcname=str(path).lstrip('/'))
        self.write('receipt.private.json',{'before_command':command,'candidate_command':candidate,'container_id':live['Id'],'image_id':live['Image'],'env':live['Config']['Env'],'mounts':live['Mounts'],'others':self.others(),'source_hashes':{str(p):digest(p) for p in paths},'artifact_hashes':{name:digest(self.folder/name) for name in ('before.private.json','candidate.private.json','container.private.json','egress.override.private.json','runtime-config.tar.gz')}})
        print('EGRESS PREPARED: '+str(self.folder)+'; only API network differs; no services changed.',flush=True)
    def guard(self,r):
        self.network_absent()
        live=self.inspect(NAME)
        require(live['Id']==r['container_id'],'API recreated; prepare again.')
        require(self.others()==r['others'],'Other services changed; prepare again.')
        for p,value in r['source_hashes'].items():require(digest(Path(p))==value,'Private source config changed.')
        for p,value in r['artifact_hashes'].items():require(digest(self.folder/p)==value,'Prepared artifact changed.')
        before=self.load('before.private.json');after=self.load('candidate.private.json')
        require(self.model(r['before_command'])==before and self.model(r['candidate_command'])==after,'Effective Compose drift.')
        validate_delta(before,after);self.runtime(before,live)
    def verify(self,r,egress):
        for attempt in range(45):
            live=self.inspect(NAME)
            if live['State'].get('Health',{}).get('Status')=='healthy':break
            time.sleep(2)
        require(live['State'].get('Health',{}).get('Status')=='healthy','API health check failed.')
        require(live['Image']==r['image_id'] and sorted(live['Config']['Env'])==sorted(r['env']) and live['Mounts']==r['mounts'] and not live['HostConfig'].get('PortBindings'),'API image/environment/mounts/ports changed.')
        networks=set(self.load('container.private.json')['NetworkSettings']['Networks'])
        if egress:networks.add(NETWORK)
        require(set(live['NetworkSettings']['Networks'])==networks,'API network verification failed.')
        if egress:
            network=self.inspect(NETWORK)
            require(network['Driver']=='bridge' and not network['Internal'] and set(network['Containers'])=={live['Id']},'Egress network isolation differs.')
            probe="""import httpx,logging,json
logging.disable(logging.CRITICAL)
with httpx.Client(verify=True,follow_redirects=False,trust_env=True,timeout=10) as client:
 for host in ('api.instagram.com','graph.instagram.com'):
  with client.stream('GET','https://'+host+'/') as response:
   print(json.dumps({'host':host,'https':True,'http':response.status_code}))
"""
            data=self.run(['docker','exec',NAME,'python','-c',probe])
            records=[json.loads(line) for line in data.decode().splitlines()]
            require(len(records)==2 and all(v.get('https') is True for v in records),'HTTPS egress probe failed.')
            for record in records:print(json.dumps(record),flush=True)
        for path,status in (('/',200),('/api/v1/clientes',401),('/health/db',404)):
            ok=False
            for attempt in range(15):
                try:
                    try:
                        with urlopen(ORIGIN+path,timeout=10) as response:code=response.status
                    except HTTPError as error:code=error.code
                    if code==status:ok=True;break
                except OSError:pass
                time.sleep(2)
            require(ok,'Public HTTPS authentication verification failed.')
        require(self.others()==r['others'],'Other service identities changed.')
    def apply(self):
        r=self.load('receipt.private.json');self.guard(r)
        try:
            self.run(up(r['candidate_command']));self.verify(r,True)
            self.write('installed.private.json',{'api_id':self.inspect(NAME)['Id'],'network':NETWORK,'image_id':r['image_id'],'database_changed':False,'provider_flags_changed':False})
        except Exception:
            self.run(up(r['before_command']));self.verify(r,False)
            print('API NETWORK ROLLED BACK; existing services and database preserved.',flush=True)
            raise
        print('API EGRESS VERIFIED. Start a NEW Instagram authorization from the site. No publishing or messaging enabled.',flush=True)

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
    task=Egress(args.folder)
    if args.apply:task.apply()
    else:task.prepare()

if __name__=='__main__':
    try:main()
    except Exception:print('STOPPED: egress operation failed; private log retained. Do not share it.');raise SystemExit(1)
