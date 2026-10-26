"""Prepare private team release artifacts. Never builds, deploys, migrates or enables providers."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/ubuntu/socialmei-team')
BACKUPS = Path('/home/ubuntu/socialmei-backups')
SERVICES = ('team-api', 'team-gateway')


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


privacy = sibling('ig_release_privacy', 'instagram-proxy-privacy.py')
publisher = sibling('ig_release_publisher', 'team-publish-prepared.py')
preflight = sibling('ig_release_preflight', 'instagram-release-preflight.py')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def candidate_model(before, service, sha):
    require(service in SERVICES and re.fullmatch(r'[0-9a-f]{40}', sha), 'Invalid release target.')
    env = before['services'][service].get('environment', {})
    if service == 'team-api':
        for key in ('SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED',
                    'SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED',
                    'SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED'):
            require(env.get(key, 'false') in ('', 'false'), 'Live sending/ingress/publishing requires a separate review.')
    override = {'services': {service: {'image': f'socialmei-v22/{service}:{sha}'}}}
    after = copy.deepcopy(before)
    after['services'][service]['image'] = override['services'][service]['image']
    if service == 'team-api':
        override['services'][service]['environment'] = {'SOCIALMEI_RELEASE_SHA': sha}
        after['services'][service].setdefault('environment', {})['SOCIALMEI_RELEASE_SHA'] = sha
    require(publisher.allowed_change(before, after, service, sha), 'Unexpected Compose changes.')
    return after, override


def missing_migrations(installed, source):
    source = sorted(source)
    installed = sorted(installed)
    require(len(source) == 28 and [name[:3] for name in source] == [f'{i:03}' for i in range(1,29)], 'Expected reviewed source migrations001–028.')
    require(len(source) == len(set(source)) and len(installed) == len(set(installed)), 'Duplicate migrations.')
    require(installed == source[:len(installed)], 'Installed ledger is not a source prefix.')
    missing = source[len(installed):]
    require(set(missing) <= {'027_instagram_image_publications.sql', '028_instagram_temporary_media.sql'},
            'Migrations beyond reviewed 027/028 require review.')
    return missing


MEDIA = '''        handle /media/instagram/* {
            @instagram_media_read method GET
            route {
                reverse_proxy @instagram_media_read team-api:8000 {
                    header_up -Authorization
                    header_up -Cookie
                }
                respond "Não encontrado." 404
            }
        }
'''
WEBHOOK = '''        handle /webhooks/instagram {
            reverse_proxy team-api:8000 {
                header_up -Authorization
            }
        }
'''


def patch_caddy(source):
    anchor = list(re.finditer(r'^\s*handle /api/v1/\* \{', source, re.M))
    require(len(anchor) == 1, 'Expected one literal API handler; review gateway source manually.')
    extra = ''
    for path, block in (('/media/instagram/*', MEDIA), ('/webhooks/instagram', WEBHOOK)):
        found = re.findall(r'^\s*handle ' + re.escape(path) + r'\s*\{', source, re.M)
        require(len(found) <= 1, 'Duplicate gateway handler.')
        if not found:
            require(path not in source, 'Gateway matcher requires manual review.')
            extra += block
    point = anchor[0].start()
    return source[:point] + '\n' + extra + source[point:]


def routes_only(before, after, added):
    """Remove only newly added literal handler nodes, then compare ALL remaining JSON."""
    clean = copy.deepcopy(after)
    removed = {path: 0 for path in added}
    def walk(node):
        if isinstance(node, list):
            keep = []
            for item in node:
                path = None
                if isinstance(item, dict) and len(item.get('match', [])) == 1:
                    match = item['match'][0]
                    paths = match.get('path', [])
                    if set(match) == {'path'} and len(paths) == 1 and paths[0] in removed:
                        path = paths[0]
                if path:
                    removed[path] += 1
                else:
                    walk(item)
                    keep.append(item)
            node[:] = keep
        elif isinstance(node, dict):
            for item in node.values(): walk(item)
    walk(clean)
    def canonical_groups(config):
        normalized=copy.deepcopy(config)
        names={}
        def visit(node):
            if isinstance(node,dict):
                group=node.get('group')
                if isinstance(group,str) and re.fullmatch(r'group[0-9]+',group):
                    if group not in names:names[group]='generated-'+str(len(names))
                    node['group']=names[group]
                for value in node.values():visit(value)
            elif isinstance(node,list):
                for value in node:visit(value)
        # Group names are opaque generated routing IDs. Preserve their exact
        # equality relationships, so neither merging nor splitting is accepted.
        visit(normalized.get('apps',{}).get('http',{}))
        return normalized
    return all(count == 1 for count in removed.values()) and canonical_groups(clean) == canonical_groups(before)


def call(args, *, input=None):
    result = subprocess.run(args, input=input, capture_output=True, text=True, cwd=ROOT, timeout=60)
    require(result.returncode == 0, 'Read-only command failed; no private output was printed.')
    return result.stdout


def compose_command(container):
    labels = container['Config'].get('Labels') or {}
    require(labels.get('com.docker.compose.project') == 'socialmei-team', 'Wrong Compose project.')
    require(labels.get('com.docker.compose.project.working_dir') == str(ROOT), 'Wrong Compose directory.')
    files = labels.get('com.docker.compose.project.config_files', '').split(',')
    require(files and all(Path(p).is_absolute() and Path(p).is_file() for p in files), 'Compose files unavailable.')
    require(files[0] == str(ROOT/'compose.team.yaml'), 'Unexpected base Compose.')
    args = ['docker','compose','--project-name','socialmei-team','--env-file',str(ROOT/'.env.team')]
    for path in files: args += ['-f',path]
    return args


def validate_runtime(model, container, service):
    require(publisher.runtime_shape_matches(model,container,service), 'Networks/mounts/ports differ from installed runtime.')
    config = model['services'][service]
    require(config.get('image') == container['Config']['Image'], 'Installed image differs from Compose.')
    live = dict(item.split('=',1) for item in container['Config'].get('Env',[]) if '=' in item)
    env = config.get('environment', {})
    require(all(live.get(k) == str(v) for k,v in env.items()), 'Environment differs from effective Compose.')
    for name in live:
        if name.startswith(('SOCIALMEI_', 'POSTGRES_')) or name == 'DATABASE_URL':
            require(name in env or name == 'SOCIALMEI_RELEASE_SHA', 'Runtime-only environment would be lost.')


def validate_gateway(name, raw, active):
    baseline = privacy._normalized_auto_hidden_config(privacy._adapt(name,raw))
    require(baseline == active and privacy.protected(active), 'Active gateway source/privacy not confirmed.')
    changed = patch_caddy(raw)
    adapted = privacy._normalized_auto_hidden_config(privacy._adapt(name,changed))
    added = [path for path in ('/media/instagram/*','/webhooks/instagram') if path not in raw]
    require(routes_only(active,adapted,added) and privacy.protected(adapted), 'Gateway delta exceeds reviewed handlers.')
    require(all(preflight.proxy_routes(adapted).values()), 'Gateway provider handlers fail structural checks.')
    return changed, adapted


def prepare(sha, output, expected_api, expected_gateway):
    require(re.fullmatch(r'[0-9a-f]{40}', sha), 'Full candidate SHA required.')
    require(output.parent.resolve() == BACKUPS and not output.exists(), 'Use a new direct child of the private backup directory.')
    require(not call(['git','status','--porcelain']).strip(), 'Unexpected checkout changes.')
    require(call(['git','rev-parse',sha+'^{commit}']).strip() == sha, 'Candidate commit unavailable.')
    installed = preflight.sql_read('socialmei-team-team-postgres-1',
        "BEGIN READ ONLY; SELECT jsonb_agg(version ORDER BY version) FROM socialmei.schema_migrations; ROLLBACK;")[0]
    source = call(['git','ls-tree','-r','--name-only',sha,'database/migrations/']).splitlines()
    names = [Path(p).name for p in source if p.endswith('.sql')]
    missing = missing_migrations(installed,names)
    migration_hashes = {name:hashlib.sha256(call(['git','show',sha+':database/migrations/'+name]).encode()).hexdigest() for name in names}
    containers, models, commands, candidates, overrides = {}, {}, {}, {}, {}
    for service, expected in zip(SERVICES,(expected_api,expected_gateway)):
        container = json.loads(call(['docker','inspect','socialmei-team-'+service+'-1']))[0]
        require(container['Config']['Image'] == expected, 'Installed baseline image changed.')
        require(container['State'].get('Running'), 'Installed service is not running.')
        if service == 'team-api':
            require(container['State'].get('Health',{}).get('Status') == 'healthy', 'Installed API is unhealthy.')
        args = compose_command(container)
        model = json.loads(call(args+['config','--format','json']))
        validate_runtime(model,container,service)
        candidate, override = candidate_model(model,service,sha)
        containers[service], models[service], commands[service] = container, model, args
        candidates[service], overrides[service] = candidate, override
    gateway = containers['team-gateway']
    mounts = [m for m in gateway['Mounts'] if m['Destination']=='/etc/caddy/Caddyfile']
    require(len(mounts)==1 and mounts[0]['Type']=='bind' and not mounts[0]['RW'], 'Persistent read-only gateway config mount required.')
    config_path = Path(mounts[0]['Source'])
    require(config_path.is_file() and not config_path.is_symlink(), 'Private gateway source unavailable.')
    require(config_path.resolve().is_relative_to(BACKUPS) or config_path.resolve().is_relative_to(ROOT/'deploy/team/private'),
            'Gateway config outside reviewed private directories.')
    name = 'socialmei-team-team-gateway-1'
    raw = call(['docker','exec',name,'cat','/etc/caddy/Caddyfile'])
    require(config_path.read_text()==raw, 'Gateway bind source differs from container.')
    active = json.loads(call(['docker','exec',name,'wget','-qO-','http://127.0.0.1:2019/config/']))
    changed, adapted = validate_gateway(name,raw,active)
    public = preflight.inspect_proxy('socialmei-caddy')
    require(public['source']=='active', 'Public proxy active config unavailable.')
    public_json=json.loads(call(['docker','exec','socialmei-caddy','wget','-qO-','http://127.0.0.1:2019/config/']))
    require(privacy.protected(public_json), 'Public proxy logging privacy not confirmed.')
    call(['docker','exec','-i',name,'caddy','validate','--config','/dev/stdin','--adapter','caddyfile'],input=changed)
    # All inspection/validation finishes before creating any artifacts.
    output.mkdir(mode=0o700)
    def write(name,value):
        privacy._write_private(output/name, value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')
    hashes={}
    for service in SERVICES:
        write(service+'.installed.private.json',containers[service])
        write(service+'.before.private.json',models[service])
        write(service+'.candidate.private.json',candidates[service])
        write(service+'.override.private.json',overrides[service])
    write('gateway.before.Caddyfile',raw)
    write('gateway.candidate.Caddyfile',changed)
    resolved_commands={}
    for service in SERVICES:
        args=commands[service]+['-f',str(output/(service+'.override.private.json'))]
        resolved=json.loads(call(args+['config','--format','json']))
        require(resolved == candidates[service], 'Resolved candidate differs from the permitted image-only delta.')
        resolved_commands[service]={'before':commands[service],'candidate':args}
    write('compose-commands.private.json',resolved_commands)
    for path in output.iterdir(): hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt={'target':'team','candidate_sha':sha,'checkout_sha':call(['git','rev-parse','HEAD']).strip(),
             'missing_migrations':missing,'source_migration_sha256':migration_hashes,'gateway_config_source':str(config_path),
             'installed_images':{s:{'image_id':containers[s]['Image'],'container_id':containers[s]['Id']} for s in SERVICES},
             'hashes':hashes,'deployment_executed':False,'provider_flags_changed':False,
             'required_before_apply':['current CI approval','verified fresh backup + saved images',
                 'fresh drift check','reviewed migration runner','anonymous media + session regression',
                 'explicit publishing activation after OAuth','separate n8n webhook decision']}
    write('preparation.private.json',receipt)
    print(json.dumps({'prepared':True,'folder':str(output),'candidate_sha':sha,
                      'missing_migrations':missing,'deployment_executed':False,'integrations_activated':False},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',choices=['team'],required=True)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--sha')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--expected-api-image')
    parser.add_argument('--expected-gateway-image')
    args=parser.parse_args()
    if not args.prepare:
        print('Preparation only. No runtime inspected or modified. Use --prepare with explicit SHA, baseline images and private output folder.')
        return
    require(all((args.sha,args.output,args.expected_api_image,args.expected_gateway_image)), 'Explicit preparation parameters required.')
    prepare(args.sha,args.output,args.expected_api_image,args.expected_gateway_image)


if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Preparation stopped. No services/configuration/database were changed; private details were not printed.') from None
