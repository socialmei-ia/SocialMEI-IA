"""Fail-closed V25 API/gateway cutover. Inspection is the default; never builds images.

--restore-evidence is a private operator_report, not an automated restore proof.
Rollback preserves additive database migrations and never restores database data.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import tarfile
from urllib.parse import urlsplit, unquote, parse_qsl


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = sibling('v25_legacy', 'team-publish-prepared.py')
prepare = sibling('v25_prepare', 'instagram-release-prepare.py')
ROOT, BACKUPS, SERVICES = legacy.ROOT, legacy.BACKUPS, legacy.SERVICES
require, digest = legacy.require, legacy.digest
DISABLED_FLAGS = ('SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED',
                  'SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED',
                  'SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED')



def verify_image_archive(path, expected):
    """Verify classic config IDs or OCI index IDs without loading any image."""
    members=set(); metadata={}; total=0
    with tarfile.open(path,'r|gz') as archive:
        for member in archive:
            name=member.name.removeprefix('./')
            if not member.isfile():continue
            require(name not in members,'Duplicate image archive entry.')
            members.add(name)
            is_metadata=(name in ('manifest.json','index.json') or
                         re.fullmatch(r'(?:blobs/sha256/)?[0-9a-f]{64}(?:\.json)?',name))
            if is_metadata and member.size<=2*1024*1024:
                total+=member.size
                require(total<=64*1024*1024,'Oversized image archive metadata.')
                metadata[name]=archive.extractfile(member).read()
    def decode(name):
        require(name in metadata,'Image metadata missing or oversized.')
        try:return json.loads(metadata[name])
        except (ValueError,UnicodeError):raise RuntimeError('Invalid image metadata.') from None
    def descriptor(value):
        require(isinstance(value,dict),'Invalid OCI descriptor.')
        key=value.get('digest','')
        require(isinstance(key,str) and re.fullmatch(r'sha256:[0-9a-f]{64}',key),'Invalid OCI digest.')
        name='blobs/sha256/'+key[7:]
        require(name in metadata,'OCI metadata blob missing.')
        content=metadata[name]
        require(len(content)==value.get('size') and 'sha256:'+hashlib.sha256(content).hexdigest()==key,'OCI metadata digest or size differs.')
        return name,decode(name)
    manifest=decode('manifest.json')
    require(isinstance(manifest,list) and 1<=len(manifest)<=10,'Docker save manifest missing.')
    for tag,image_id in expected.items():
        rows=[r for r in manifest if isinstance(r,dict) and tag in (r.get('RepoTags') or [])]
        require(len(rows)==1,'Archived image tag missing or duplicated.')
        row=rows[0];config_name=row.get('Config')
        require(isinstance(config_name,str) and config_name in metadata,'Archived image config missing.')
        config_id='sha256:'+hashlib.sha256(metadata[config_name]).hexdigest()
        layers=row.get('Layers')
        require(isinstance(layers,list) and all(isinstance(n,str) and n in members for n in layers),'Archived image layer missing.')
        if config_id==image_id:continue
        index=decode('index.json')
        require(isinstance(index,dict) and isinstance(index.get('manifests'),list),'OCI archive index missing.')
        roots=[d for d in index['manifests'] if isinstance(d,dict) and d.get('digest')==image_id]
        require(len(roots)==1,'Archived OCI image differs from baseline.')
        matches=[]
        def walk(value,depth=0):
            require(depth<=4,'OCI image index nesting exceeds limit.')
            name,document=descriptor(value)
            require(isinstance(document,dict),'Invalid OCI image document.')
            if 'manifests' in document:
                require(isinstance(document['manifests'],list),'Invalid OCI image index.')
                for child in document['manifests']:
                    require(isinstance(child,dict),'Invalid OCI image child.')
                    platform=child.get('platform',{})
                    if platform.get('os')=='linux' and platform.get('architecture')=='amd64':
                        walk(child,depth+1)
                return
            config=document.get('config')
            cname,cdata=descriptor(config)
            if cname!=config_name:return
            require(isinstance(cdata,dict) and cdata.get('os')=='linux' and cdata.get('architecture')=='amd64','Unexpected rollback image platform.')
            oci_layers=document.get('layers')
            require(isinstance(oci_layers,list),'Invalid OCI layers.')
            names=[]
            for layer in oci_layers:
                require(isinstance(layer,dict) and isinstance(layer.get('digest'),str) and re.fullmatch(r'sha256:[0-9a-f]{64}',layer['digest']),'Invalid OCI layer digest.')
                names.append('blobs/sha256/'+layer['digest'][7:])
            require(names==layers,'OCI layers differ from Docker manifest.')
            matches.append(name)
        walk(roots[0])
        require(len(matches)==1,'Archived image config not bound to baseline OCI index.')

def validate_flags(env):
    require(str(env.get('SOCIALMEI_AUTH_ENABLED', '')).lower() in ('true','1','yes','on'), 'Authentication must remain enabled.')
    require(all(str(env.get(key, 'false')).lower() in ('','false') for key in DISABLED_FLAGS), 'Provider activation is outside this release.')


def database_target(api, pg):
    networks=set(api['NetworkSettings']['Networks']) & set(pg['NetworkSettings']['Networks'])
    require(len(networks)==1,'Ambiguous database network.')
    network=next(iter(networks));meta=pg['NetworkSettings']['Networks'][network]
    hosts={'team-postgres','socialmei-team-team-postgres-1'} | set(meta.get('Aliases') or [])
    if meta.get('IPAddress'):hosts.add(meta['IPAddress'])
    env=dict(v.split('=',1) for v in api['Config']['Env'])
    pg_env=dict(v.split('=',1) for v in pg['Config']['Env'])
    if env.get('DATABASE_URL','').strip():
        url=urlsplit(env['DATABASE_URL'].strip())
        require(url.scheme in ('postgres','postgresql') and not url.fragment and all(k in {'sslmode','connect_timeout','application_name'} for k,v in parse_qsl(url.query)),'Database URL needs explicit target review.')
        host,port,user,db=url.hostname,url.port or 5432,unquote(url.username or ''),unquote(url.path.lstrip('/'))
    else:
        host,port,user,db=env.get('POSTGRES_HOST'),env.get('POSTGRES_PORT','5432'),env.get('POSTGRES_USER'),env.get('POSTGRES_DB')
    require(host in hosts and str(port)=='5432' and user and user==pg_env.get('POSTGRES_USER') and db and db==pg_env.get('POSTGRES_DB'),'Migration target differs from the installed team database.')
    return network


def has_http_auth(value):
    if isinstance(value, dict):
        return value.get('handler') == 'authentication' or any(has_http_auth(child) for child in value.values())
    return isinstance(value, list) and any(has_http_auth(child) for child in value)


def private_file(path):
    require(path.is_file() and not path.is_symlink(), 'Private regular file required.')
    info = path.stat()
    require(info.st_uid == os.geteuid() and not stat.S_IMODE(info.st_mode) & 0o077, 'Private file ownership/mode required.')
    return path


def private_folder(path):
    require(path.is_absolute() and not path.is_symlink() and path.resolve().parent == BACKUPS.resolve(), 'Use a direct private backup child.')
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, 'Private folder ownership/mode required.')
    return path


def write_private(path, content):
    require(not path.is_symlink(), 'Refusing symlink output.')
    fd, name = tempfile.mkstemp(prefix='.v25-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content if isinstance(content, bytes) else content.encode())
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class Publisher(legacy.Publisher):
    def __init__(self, folder, rollback_backup, evidence=None):
        self.folder, self.rollback_backup = private_folder(folder), private_folder(rollback_backup)
        self.meta = json.loads(private_file(folder/'preparation.private.json').read_text())
        self.sha = self.meta['candidate_sha']
        require(re.fullmatch(r'[0-9a-f]{40}', self.sha), 'Full candidate SHA required.')
        require(self.meta.get('target') == 'team' and self.meta.get('migration_stage') == 'functional', 'A functional001–031 preparation is required.')
        self.commands = self.load('compose-commands.private.json')
        self.evidence = evidence
        self.log = folder/'v25-publication.private.log'
        self.fresh = None

    def load(self, name):
        return json.loads(private_file(self.folder/name).read_text())

    def run(self, args, **kwargs):
        # Legacy runner captures all private output. Create its log with explicit
        # permissions even when used programmatically outside main().
        if not self.log.exists():
            fd = os.open(self.log, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
        private_file(self.log)
        kwargs.setdefault('timeout', 180)
        return super().run(args, **kwargs)

    def model(self, service, mode):
        return self.load(service+'.'+mode+'.private.json')

    def artifacts(self):
        expected = {'compose-commands.private.json', 'gateway.before.Caddyfile','gateway.candidate.Caddyfile'}
        expected |= {s+'.'+kind+'.private.json' for s in SERVICES for kind in ('installed','before','candidate','override')}
        if self.meta.get('checkout_policy', {}).get('mode') == 'preserved_caddy': expected.add('checkout-hotfix.preserved.Caddyfile')
        hashes = self.meta.get('hashes', {})
        require(set(hashes) == expected, 'Prepared artifact inventory differs.')
        for name, checksum in hashes.items():
            require(Path(name).name == name and re.fullmatch(r'[0-9a-f]{64}', checksum), 'Invalid prepared hash.')
            require(digest(private_file(self.folder/name)) == checksum, 'Prepared artifact changed.')
        require(set(self.commands) == set(SERVICES), 'Service scope changed.')
        for service in SERVICES:
            installed = self.model(service,'installed')
            before, candidate = self.model(service,'before'), self.model(service,'candidate')
            require(legacy.allowed_change(before,candidate,service,self.sha), 'Compose delta exceeds image/release SHA.')
            expected_override = {'services':{service:{'image':f'socialmei-v22/{service}:{self.sha}'}}}
            if service == 'team-api': expected_override['services'][service]['environment'] = {'SOCIALMEI_RELEASE_SHA':self.sha}
            require(self.model(service,'override') == expected_override, 'Unexpected override scope.')
            before_command = prepare.compose_command(installed)
            require(self.commands[service] == {'before':before_command,'candidate':before_command+['-f',str(self.folder/(service+'.override.private.json'))]}, 'Unexpected Compose command.')
        require(self.meta.get('provider_flags_changed') is False and self.meta.get('deployment_executed') is False, 'Preparation safety receipt changed.')

    def backup_checksums(self, folder, rollback=False):
        private_folder(folder)
        if rollback:
            expected = {'images.tar.gz','runtime-config.tar.gz','containers.json','image-ids.txt'}
            lines = private_file(folder/'SHA256SUMS').read_text().splitlines()
            hashes = {}
            for line in lines:
                match = re.fullmatch(r'([0-9a-f]{64}) [ *]([^/]+)',line)
                require(match and match[2] not in hashes, 'Invalid rollback checksum receipt.')
                hashes[match[2]] = match[1]
            require(set(hashes) == expected, 'Incomplete rollback backup.')
        else:
            hashes = json.loads(private_file(folder/'concluido.json').read_text()).get('sha256',{})
            require({'equipe.dump','configuracao.tar.gz','conteudo.txt'} <= set(hashes), 'Incomplete database backup.')
        for name, checksum in hashes.items():
            require(Path(name).name == name and re.fullmatch(r'[0-9a-f]{64}',checksum), 'Invalid backup receipt.')
            require(digest(private_file(folder/name)) == checksum, 'Backup checksum mismatch.')
        return hashes

    def checkout(self):
        policy = self.meta.get('checkout_policy', {})
        require(policy.get('mode') in ('clean','preserved_caddy'), 'Missing checkout policy.')
        require(self.run(['git','rev-parse','HEAD']).decode().strip() == self.meta['checkout_sha'], 'Checkout HEAD changed.')
        # Use this runner so command output never leaks. The preparer helper is
        # read-only and validates exact status/hash; never reset or stash.
        old = prepare.call
        prepare.call = lambda args, **kw: self.run(args, **kw).decode()
        try:
            require(prepare.checkout_policy(policy.get('sha256')) == policy, 'Checkout policy drift.')
        finally: prepare.call = old
        containers = [self.inspect('socialmei-team-'+s+'-1') for s in SERVICES]
        containers += [self.inspect('socialmei-caddy')]
        prepare.require_unmounted_hotfix(policy,containers)

    def rollback_material(self):
        saved=json.loads(private_file(self.rollback_backup/'containers.json').read_text())
        require(isinstance(saved,list),'Invalid archived containers.')
        expected={}
        for service in SERVICES:
            rows=[r for r in saved if r.get('Name')=='/socialmei-team-'+service+'-1']
            require(len(rows)==1,'Rollback container identity missing or duplicated.')
            baseline=self.meta['installed_images'][service]
            image=self.model(service,'before')['services'][service]['image']
            require(rows[0].get('Id')==baseline['container_id'] and rows[0].get('Image')==baseline['image_id'] and rows[0].get('Config',{}).get('Image')==image,'Rollback container differs from prepared baseline.')
            require(re.fullmatch(r'sha256:[0-9a-f]{64}',baseline['image_id']),'Invalid baseline image identity.')
            expected[image]=baseline['image_id']
        require(set(private_file(self.rollback_backup/'image-ids.txt').read_text().splitlines())==set(expected.values()),'Rollback image IDs differ.')
        verify_image_archive(self.rollback_backup/'images.tar.gz',expected)
        config_path=str(self.meta['gateway_config_source']).lstrip('/')
        found=0
        with tarfile.open(self.rollback_backup/'runtime-config.tar.gz','r|gz') as archive:
            for member in archive:
                if member.name.removeprefix('./')==config_path:
                    require(member.isfile() and member.size<=1024*1024,'Invalid archived gateway config.')
                    require(archive.extractfile(member).read()==(self.folder/'gateway.before.Caddyfile').read_bytes(),'Archived gateway config differs.')
                    found+=1
        require(found==1,'Archived gateway config missing or duplicated.')

    def source(self):
        source = self.folder/'source'
        require(source.is_dir() and not source.is_symlink(), 'Git archive source missing.')
        tree = self.run(['git','ls-tree','-r',self.sha]).decode().splitlines()
        expected = {}
        for line in tree:
            header, name = line.split('\t',1)
            mode, kind, oid = header.split()
            require(kind == 'blob' and mode in ('100644','100755'), 'Unsupported candidate archive entry.')
            expected[name] = oid
        actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() or p.is_symlink()}
        require(actual == set(expected), 'Git archive inventory changed.')
        for name in expected:
            path = source/name
            require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(source.resolve()), 'Unsafe source path.')
            data = path.read_bytes()
            require(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == expected[name], 'Git archive bytes changed.')
        files = sorted((source/'database/migrations').glob('*.sql'))
        require([p.name for p in files] == list(prepare.REVIEWED_MIGRATIONS), 'Migration chain must be exact001–031.')
        require({p.name:digest(p) for p in files} == self.meta['source_migration_sha256'], 'Migration hashes changed.')

    def ledger(self):
        value = self.run(['docker','exec','socialmei-team-team-postgres-1','sh','-ec',
            'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "BEGIN READ ONLY; SELECT COALESCE(json_agg(version ORDER BY version), \'[]\'::json) FROM socialmei.schema_migrations; ROLLBACK;"']).decode()
        rows = [line for line in value.splitlines() if line.startswith('[')]
        require(len(rows) == 1, 'Could not read immutable migration ledger.')
        return json.loads(rows[0])

    def evidence_check(self):
        require(self.evidence is not None, 'Private operator restore report required.')
        evidence = json.loads(private_file(self.evidence).read_text())
        require(evidence.get('kind') == 'operator_report' and evidence.get('restore_passed') is True and evidence.get('migration_passed') is True, 'Restore report incomplete.')
        require(evidence.get('network') == 'none' and evidence.get('memory_bytes') == 402653184, 'Restore trial isolation differs.')
        require(evidence.get('source_ledger') == list(prepare.REVIEWED_MIGRATIONS[:26]) and evidence.get('trial_ledger') == list(prepare.REVIEWED_MIGRATIONS), 'Restore trial ledgers differ.')
        require(evidence.get('candidate_sha') == self.sha and evidence.get('migration_sha256') == self.meta['source_migration_sha256'],'Restore trial source differs from candidate.')
        backup = private_folder(Path(evidence['backup_path']))
        require(evidence.get('backup_sha256') == self.backup_checksums(backup), 'Restore report backup differs.')
        return evidence

    def gateway(self, mode, check_candidate=True):
        name = 'socialmei-team-team-gateway-1'
        path = Path(self.meta['gateway_config_source'])
        require(path.resolve().is_relative_to(BACKUPS) or path.resolve().is_relative_to(ROOT/'deploy/team/private'), 'Gateway bind source outside private scope.')
        private_file(path)
        live = self.inspect(name)
        mounts = [m for m in live['Mounts'] if m['Destination'] == '/etc/caddy/Caddyfile']
        require(len(mounts) == 1 and mounts[0]['Type'] == 'bind' and mounts[0]['Source'] == str(path) and mounts[0]['RW'] is False, 'Gateway private mount drift.')
        raw = (self.folder/('gateway.'+mode+'.Caddyfile')).read_text()
        require(path.read_text() == raw and self.run(['docker','exec',name,'cat','/etc/caddy/Caddyfile']).decode() == raw, 'Gateway disk/container config drift.')
        active = json.loads(self.run(['docker','exec',name,'wget','-qO-','http://127.0.0.1:2019/config/']))
        # Adapt through the running Caddy, preserving its exact adapter semantics.
        adapted = json.loads(self.run(['docker','exec','-i',name,'caddy','adapt','--config','/dev/stdin','--adapter','caddyfile'],input=raw.encode()))
        require(prepare.privacy._normalized_auto_hidden_config(adapted) == active and prepare.privacy.protected(active), 'Gateway active/privacy drift.')
        require(not has_http_auth(active), 'Gateway HTTP Basic authentication is outside public-site policy.')
        public = json.loads(self.run(['docker','exec','socialmei-caddy','wget','-qO-','http://127.0.0.1:2019/config/']))
        require(prepare.privacy.protected(public) and not has_http_auth(public), 'Public Caddy privacy/auth drift.')
        if mode == 'before' and check_candidate:
            changed = (self.folder/'gateway.candidate.Caddyfile').read_bytes()
            candidate = json.loads(self.run(['docker','exec','-i',name,'caddy','adapt','--config','/dev/stdin','--adapter','caddyfile'],input=changed))
            candidate = prepare.privacy._normalized_auto_hidden_config(candidate)
            added = [p for p in ('/media/instagram/*','/webhooks/instagram') if p not in raw]
            require(prepare.routes_only(active,candidate,added) and prepare.privacy.protected(candidate) and all(prepare.preflight.proxy_routes(candidate).values()), 'Candidate gateway changes exceed reviewed routes.')
            self.run(['docker','exec','-i',name,'caddy','validate','--config','/dev/stdin','--adapter','caddyfile'],input=changed)
            env = live['Config']['Env']
            require(all('\n' not in v and '\r' not in v for v in env), 'Invalid gateway env-file.')
            envfile = self.folder/'v25-gateway-validation.private.env'
            write_private(envfile,'\n'.join(env)+'\n')
            try:
                image = self.inspect_image(f'socialmei-v22/team-gateway:{self.sha}')['Id']
                command = ['docker','run','--rm','-i','--pull','never','--network','none','--env-file',str(envfile)]
                for mount in live['Mounts']:
                    require(mount['Type'] == 'bind' and mount['RW'] is False, 'Gateway validation requires read-only bind mounts.')
                    command += ['--mount',f'type=bind,src={mount["Source"]},dst={mount["Destination"]},readonly']
                command += ['--entrypoint','caddy',image]
                rendered = json.loads(self.run(command+['adapt','--config','/dev/stdin','--adapter','caddyfile'],input=changed))
                require(prepare.privacy._normalized_auto_hidden_config(rendered) == candidate, 'Candidate Caddy adapter changed semantics.')
                self.run(command+['validate','--config','/dev/stdin','--adapter','caddyfile'],input=changed)
            finally: envfile.unlink(missing_ok=True)

    def build_images(self):
        receipt = self.load('build-image-ids.private.json')
        require(receipt.get('candidate_sha') == self.sha and set(receipt.get('images',{})) == set(SERVICES), 'Build receipt candidate/scope differs.')
        for service in SERVICES:
            expected = receipt['images'][service]
            tag = f'socialmei-v22/{service}:{self.sha}'
            image = self.inspect_image(tag)
            require(expected.get('image') == tag and expected.get('image_id') == image['Id'], 'Built image identity changed.')
            require(image['Config'].get('Labels',{}).get('org.opencontainers.image.revision') == self.sha, 'Built image revision differs.')
        return receipt

    def models(self, rollback=False):
        if not rollback: self.build_images()
        for service in SERVICES:
            for mode in (('before',) if rollback else ('before','candidate')):
                require(json.loads(self.run(self.commands[service][mode]+['config','--format','json'])) == self.model(service,mode), 'Compose files drifted.')
            before = self.model(service,'before')
            require(self.inspect_image(before['services'][service]['image'])['Id'] == self.meta['installed_images'][service]['image_id'], 'Rollback image drift.')

    def preflight(self):
        self.artifacts(); self.backup_checksums(self.rollback_backup,True)
        self.rollback_material()
        self.checkout(); self.source(); self.models()
        for service in SERVICES:
            live = self.inspect('socialmei-team-'+service+'-1')
            require(legacy.baseline_matches(self.meta['installed_images'][service],live), 'Installed container identity drift.')
            prepare.validate_runtime(self.model(service,'before'),live,service)
            require(live['State'].get('Running'), 'Installed service stopped.')
            if service == 'team-api':
                require(live['State'].get('Health',{}).get('Status') == 'healthy', 'Installed API unhealthy.')
                validate_flags(dict(v.split('=',1) for v in live['Config']['Env']))
        self.gateway('before')
        database_target(self.inspect('socialmei-team-team-api-1'),self.inspect('socialmei-team-team-postgres-1'))
        installed = self.ledger()
        require(prepare.missing_migrations(installed,list(prepare.REVIEWED_MIGRATIONS),stage='functional') == self.meta['missing_migrations'], 'Migration ledger drift.')
        require(installed == self.baseline_ledger(), 'Expected the exact prepared migration baseline.')
        self.evidence_check()
        self.remote_auth()

    def remote_auth(self):
        config = self.https('/frontend/config.js',200).decode()
        require(re.search(r'auth["\x27]?\s*:\s*\{[^{}]*?mode["\x27]?\s*:\s*["\x27]remote["\x27]', config), 'Remote authentication mode not confirmed.')

    def fresh_backup(self):
        output = self.run([sys.executable,'tools/team-maintenance.py','backup']).decode()
        match = re.search(r'Backup da equipe concluído e índice conferido: ([^\r\n]+)',output)
        require(match, 'Fresh backup receipt missing.')
        self.fresh = private_folder(Path(match[1]))
        self.backup_checksums(self.fresh)
        write_private(self.folder/'v25-fresh-backup.private.json',json.dumps({'path':str(self.fresh),'sha256':self.backup_checksums(self.fresh)}))

    def baseline_ledger(self):
        reviewed=list(prepare.REVIEWED_MIGRATIONS)
        missing=self.meta.get('missing_migrations')
        require(isinstance(missing,list) and len(missing)<=5 and missing==reviewed[len(reviewed)-len(missing):],'Prepared migration suffix differs.')
        return reviewed[:len(reviewed)-len(missing)]

    def migrate(self):
        require(self.fresh is not None, 'Fresh backup required before migrations.')
        self.backup_checksums(self.fresh)
        self.source(); self.build_images()
        require(self.ledger() == self.baseline_ledger(), 'Ledger changed before migration; prepare a new baseline after rollback.')
        api = self.inspect('socialmei-team-team-api-1')
        pg = self.inspect('socialmei-team-team-postgres-1')
        network=database_target(api,pg)
        env = api['Config']['Env']
        require(all('\n' not in v and '\r' not in v for v in env), 'Invalid env-file value.')
        envfile = self.folder/'v25-migration.private.env'
        write_private(envfile,'\n'.join(env)+'\n')
        source = self.folder/'source'
        image = self.inspect_image(f'socialmei-v22/team-api:{self.sha}')['Id']
        try:
            self.run(['docker','run','--rm','--pull','never','--network',network,'--env-file',str(envfile),
                      '--env','PGOPTIONS=-c lock_timeout=10s -c statement_timeout=120s','--env','PYTHONPATH=/app',
                      '--mount',f'type=bind,src={source / "tools/team_migrate.py"},dst=/maintenance/team_migrate.py,readonly',
                      '--mount',f'type=bind,src={source / "database/migrations"},dst=/migrations,readonly',
                      '--entrypoint','python',image,'/maintenance/team_migrate.py'])
        finally: envfile.unlink(missing_ok=True)
        require(self.ledger() == list(prepare.REVIEWED_MIGRATIONS), 'Post-migration ledger differs.')

    def replace_caddy(self, mode):
        path = Path(self.meta['gateway_config_source'])
        require(path.resolve().is_relative_to(BACKUPS) or path.resolve().is_relative_to(ROOT/'deploy/team/private'),'Gateway source outside private scope.')
        private_file(path)
        require(path.read_bytes() in {(self.folder/'gateway.before.Caddyfile').read_bytes(),(self.folder/'gateway.candidate.Caddyfile').read_bytes()},'Gateway source changed outside this release; do not overwrite it.')
        original_mode = stat.S_IMODE(path.stat().st_mode)
        write_private(path,(self.folder/('gateway.'+mode+'.Caddyfile')).read_bytes())
        os.chmod(path,original_mode)

    def switch(self, mode, services):
        require(mode in ('before','candidate'), 'Unknown release mode.')
        if mode == 'candidate': self.build_images()
        for service in services:
            require(service in SERVICES, 'Service outside release scope.')
            if service=='team-gateway':
                require(private_file(Path(self.meta['gateway_config_source'])).read_bytes()==(self.folder/('gateway.'+mode+'.Caddyfile')).read_bytes(),'Gateway source changed before recreation.')
            require(json.loads(self.run(self.commands[service][mode]+['config','--format','json'])) == self.model(service,mode), 'Compose changed before recreate.')
            image = self.inspect_image(self.model(service,mode)['services'][service]['image'])
            if mode == 'before': require(image['Id'] == self.meta['installed_images'][service]['image_id'], 'Rollback image changed.')
            else: require(image['Config'].get('Labels',{}).get('org.opencontainers.image.revision') == self.sha, 'Candidate image changed.')
            self.run(legacy.up_command(self.commands[service][mode],service)); self.wait(service)
            live = self.inspect('socialmei-team-'+service+'-1')
            require(live['Image'] == image['Id'], 'Recreated image differs.')
            prepare.validate_runtime(self.model(service,mode),live,service)
            if service == 'team-api':
                require(live['State'].get('Health',{}).get('Status') == 'healthy', 'API Docker health required.')

    def smoke(self):
        for path,status in (('/',200),('/frontend/entrada.html',200),('/api/v1/auth/registration',200),('/api/v1/clientes',401),('/health/db',404)):
            self.https(path,status)
        try: self.https('/api/v1/__v25_invalid__',401)
        except RuntimeError: self.https('/api/v1/__v25_invalid__',404)
        self.remote_auth(); self.gateway('candidate')
        source = self.folder/'source/frontend'
        for path in sorted(source.rglob('*')):
            if path.is_file():
                # Compare every published frontend byte, using Docker to avoid
                # query strings, cache rewriting or generated/non-public paths.
                relative = path.relative_to(source).as_posix()
                expected = path
                if relative == 'config.js':
                    mounts = [v for v in self.model('team-gateway','candidate')['services']['team-gateway'].get('volumes',[]) if v['target'] == '/srv/frontend/config.js']
                    if mounts:
                        require(len(mounts) == 1 and mounts[0]['type'] == 'bind' and mounts[0].get('read_only'), 'Unexpected public config mount.')
                        expected = Path(mounts[0]['source'])
                        require(expected.is_file() and not expected.is_symlink(), 'Mounted public config missing.')
                result = self.run(['docker','exec','socialmei-team-team-gateway-1','sha256sum','/srv/frontend/'+relative]).decode().split()[0]
                require(result == digest(expected), 'Published frontend byte mismatch.')

    def rollback(self, services=SERVICES):
        # Independent rollback: no old container-ID baseline requirement.
        self.artifacts(); self.backup_checksums(self.rollback_backup,True); self.models(rollback=True); self.checkout()
        self.rollback_material()
        failures = []
        config_restored=True
        try: self.replace_caddy('before')
        except Exception:
            failures.append('private gateway config');config_restored=False
        for service in services:
            if service=='team-gateway' and not config_restored:
                failures.append('team-gateway requires verified private configuration');continue
            try: self.switch('before',(service,))
            except Exception: failures.append(service)
        require(not failures, 'Rollback incomplete; private operator intervention required: '+', '.join(failures))
        if 'team-gateway' in services: self.gateway('before',check_candidate=False)

    def record(self):
        services = {s:{'container_id':self.inspect('socialmei-team-'+s+'-1')['Id'],
                       'image_id':self.inspect('socialmei-team-'+s+'-1')['Image'],
                       'image':self.model(s,'candidate')['services'][s]['image']} for s in SERVICES}
        write_private(self.folder/'v25-installed.private.json',json.dumps({'sha':self.sha,'services':services,
            'fresh_backup':str(self.fresh),'rollback_backup':str(self.rollback_backup),
            'restore_evidence_kind':'operator_report','browser_login':'pending_manual_validation'},indent=2))

    def publish(self):
        self.preflight(); self.fresh_backup(); self.preflight(); self.migrate()
        attempted = []
        try:
            attempted.append('team-api'); self.switch('candidate',('team-api',))
            attempted.append('team-gateway')
            self.replace_caddy('candidate')
            self.switch('candidate',('team-gateway',))
            self.smoke(); self.record()
        except BaseException:
            self.rollback(attempted)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--rollback-backup',type=Path,required=True)
    parser.add_argument('--restore-evidence',type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--inspect',action='store_true')
    mode.add_argument('--apply',action='store_true')
    mode.add_argument('--rollback',action='store_true')
    args = parser.parse_args()
    require(Path.cwd().resolve() == ROOT, 'Run from the authorized team checkout.')
    os.umask(0o077)
    private_folder(args.folder); private_folder(args.rollback_backup)
    lockpath = BACKUPS/'.v25-publication.lock'
    require(not lockpath.is_symlink(), 'Invalid release lock.')
    fd = os.open(lockpath,os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a') as lock:
        private_file(lockpath)
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        publisher = Publisher(args.folder,args.rollback_backup,args.restore_evidence)
        if args.rollback: publisher.rollback(); print('API/gateway rollback verified; additive database retained.')
        elif args.apply: publisher.publish(); print('V25 API/gateway cutover verified; browser login remains manual.')
        else: publisher.preflight(); print('Inspection passed. No services or database changed.')


if __name__ == '__main__':
    try: main()
    except RuntimeError as error:
        raise SystemExit('V25 publisher stopped: '+str(error)) from None
    except Exception:
        raise SystemExit('V25 publisher stopped. Inspect private artifacts/logs; no private command output was printed.') from None
