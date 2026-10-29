"""Three-file V25 gateway patch; prepare by default, no SQL/API/provider changes."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.request import urlopen
from urllib.error import HTTPError

ROOT=Path('/home/ubuntu/socialmei-team')
BACKUPS=Path('/home/ubuntu/socialmei-backups')
BASE='1b28e84eacc5a782504b810114ba19775a1df58e'
FILES=('frontend/scripts/entrada.js','frontend/scripts/v22-instagram.js','frontend/scripts/v22-knowledge-reporting.js')
NAME='socialmei-team-team-gateway-1'
ORIGIN='https://socialmei-ia.54-94-213-7.sslip.io'

def require(ok,message):
    if not ok: raise RuntimeError(message)

def candidate_model(before,image):
    after=copy.deepcopy(before)
    after['services']['team-gateway']['image']=image
    return after

def switch_command(command):
    return command+['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','team-gateway']

def sha(data):return hashlib.sha256(data).hexdigest()

def file_sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

class Patch:
    def __init__(self,folder):
        require(folder.parent==BACKUPS and folder.is_dir() and not folder.is_symlink(),'Invalid private folder.')
        require(folder.stat().st_uid==os.geteuid() and folder.stat().st_mode & 0o077==0,'Private folder required.')
        self.folder=folder
        self.lock=open(BACKUPS/'.v25-publication.lock','a')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def run(self,command):
        result=subprocess.run(command,cwd=ROOT,capture_output=True)
        with (self.folder/'operations.private.log').open('ab') as log:
            log.write(result.stdout);log.write(result.stderr)
        require(result.returncode==0,'Command failed; private log retained. Do not share it.')
        return result.stdout
    def write(self,name,value):
        (self.folder/name).write_text(json.dumps(value,indent=2))
    def read(self,name):return json.loads((self.folder/name).read_text())
    def inspect(self,name):return json.loads(self.run(['docker','inspect',name]))[0]
    def others(self):
        return self.run(['docker','ps','-a','--no-trunc','--format','{{.Names}} {{.ID}}']).decode().splitlines()
    def model(self,command):return json.loads(self.run(command+['config','--format','json']))
    def prepare(self,target):
        require(re.fullmatch('[0-9a-f]{40}',target),'Full SHA required.')
        require(not (self.folder/'receipt.private.json').exists(),'Folder already prepared.')
        require(self.run(['git','rev-parse',target+'^{commit}']).decode().strip()==target,'Unknown commit.')
        self.run(['git','merge-base','--is-ancestor',BASE,target])
        changed=self.run(['git','diff','--name-only',BASE,target,'--','frontend']).decode().splitlines()
        require(set(changed)==set(FILES),'Unexpected frontend changes.')
        live=self.inspect(NAME);labels=live['Config']['Labels']
        require(labels['com.docker.compose.project.working_dir']==str(ROOT),'Unexpected project directory.')
        files=labels['com.docker.compose.project.config_files'].split(',')
        require(all(Path(f).is_absolute() and Path(f).is_file() for f in files),'Compose file missing.')
        command=['docker','compose','--env-file',str(ROOT/'.env.team'),'-p',labels['com.docker.compose.project']]
        for file in files:command+=['-f',file]
        before=self.model(command)
        image=before['services']['team-gateway']['image']
        require(self.inspect(image)['Id']==live['Image'],'Rollback image tag drift.')
        for source in FILES:
            actual=self.run(['docker','exec',NAME,'cat','/srv/'+source])
            require(actual==self.run(['git','show',BASE+':'+source]),'Installed frontend differs from reviewed baseline.')
        context=self.folder/'build';context.mkdir()
        hashes={}
        for source in FILES:
            data=self.run(['git','show',target+':'+source])
            (context/Path(source).name).write_bytes(data);hashes[source]=sha(data)
        (context/'Dockerfile').write_text('FROM '+image+'\n'+''.join('COPY '+Path(f).name+' /srv/'+f+'\n' for f in FILES)+'LABEL org.opencontainers.image.revision="'+target+'"\n')
        tag='socialmei-v25/team-gateway:frontend-'+target
        self.write('before.private.json',before)
        self.write('gateway.private.json',live)
        saved=[line for line in self.others() if not line.startswith(NAME+' ')]
        config_files={f:sha(Path(f).read_bytes()) for f in files}
        mounts={m['Source']:sha(Path(m['Source']).read_bytes()) for m in live['Mounts'] if m['Type']=='bind' and Path(m['Source']).is_file()}
        # Keep the previous image locally and a verifiable Docker-save copy.
        archive=self.folder/'gateway-rollback.tar'
        self.run(['docker','image','save','-o',str(archive),image])
        self.run(['docker','build','--pull=false','--network=none','-t',tag,str(context)])
        require(self.inspect(NAME)['Id']==live['Id'],'Gateway changed during build.')
        require(self.inspect(image)['Id']==live['Image'],'Base image changed during build.')
        override=self.folder/'gateway.override.private.json'
        self.write(override.name,{'services':{'team-gateway':{'image':tag}}})
        candidate=command+['-f',str(override)]
        require(self.model(candidate)==candidate_model(before,tag),'Unexpected Compose changes.')
        self.write('receipt.private.json',{'sha':target,'container_id':live['Id'],'old_image_id':live['Image'],'image':tag,'image_id':self.inspect(tag)['Id'],'before_command':command,'candidate_command':candidate,'others':saved,'config_files':config_files,'mount_files':mounts,'hashes':hashes,'rollback_sha256':file_sha(archive)})
        print('PREPARED: '+str(self.folder)+'; no services changed.',flush=True)
    def guard(self,r):
        require(self.inspect(NAME)['Id']==r['container_id'],'Gateway identity changed; prepare again.')
        require([line for line in self.others() if not line.startswith(NAME+' ')]==r['others'],'Other services changed; inspect again.')
        for path,checksum in dict(r['config_files'],**r['mount_files']).items():
            require(sha(Path(path).read_bytes())==checksum,'Private configuration changed.')
        require(self.model(r['before_command'])==self.read('before.private.json'),'Effective Compose changed.')
        require(self.model(r['candidate_command'])==candidate_model(self.read('before.private.json'),r['image']),'Candidate Compose changed.')
        require(self.inspect(r['image'])['Id']==r['image_id'],'Candidate image changed.')
        old=self.read('before.private.json')['services']['team-gateway']['image']
        require(self.inspect(old)['Id']==r['old_image_id'],'Rollback image changed.')
        require(file_sha(self.folder/'gateway-rollback.tar')==r['rollback_sha256'],'Rollback archive changed.')
    def smoke(self,r):
        for source,checksum in r['hashes'].items():
            require(sha(self.run(['docker','exec',NAME,'cat','/srv/'+source]))==checksum,'Served asset mismatch.')
        for path,expected in (('/',200),('/api/v1/clientes',401),('/health/db',404)):
            passed=False
            for attempt in range(30):
                try:
                    try:
                        with urlopen(ORIGIN+path,timeout=10) as response:code=response.status
                    except HTTPError as error:code=error.code
                    if code==expected:passed=True;break
                except OSError:pass
                time.sleep(2)
            require(passed,'HTTPS verification failed.')
        require([line for line in self.others() if not line.startswith(NAME+' ')]==r['others'],'Other services changed.')
    def apply(self):
        r=self.read('receipt.private.json');self.guard(r)
        try:
            self.run(switch_command(r['candidate_command']))
            require(self.inspect(NAME)['Image']==r['image_id'],'Gateway image differs.')
            self.smoke(r)
            self.write('installed.private.json',{'sha':r['sha'],'container_id':self.inspect(NAME)['Id'],'api_changed':False,'database_changed':False})
        except Exception:
            self.run(switch_command(r['before_command']))
            require(self.inspect(NAME)['Image']==r['old_image_id'],'Rollback image verification failed.')
            restored=dict(r,hashes={f:sha(self.run(['git','show',BASE+':'+f])) for f in FILES})
            self.smoke(restored)
            print('Gateway rolled back and HTTPS verified; no SQL/API commands executed.',flush=True)
            raise
        print('FRONTEND UPDATED: '+r['sha']+'; validate Instagram authorization in browser.',flush=True)

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--sha')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    p=Patch(args.folder)
    if args.apply:p.apply()
    else:p.prepare(args.sha or '')

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('STOPPED: '+str(error))
        raise SystemExit(1)
