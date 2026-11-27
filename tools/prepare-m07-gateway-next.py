"""Freeze the gateway of the 046 release pair, retaining the published gateway as rollback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage1', type=Path, required=True)
    parser.add_argument('--api-stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args()
    root = Path('/var/lib/socialmei/production-consolidation-m07')
    stage, api = (p.resolve(strict=True) for p in (args.stage1, args.api_stage))
    out = args.output.parent.resolve(strict=True)/args.output.name
    if os.geteuid()!=0 or not all(root in p.parents for p in (stage,api,out)):
        raise SystemExit('PRIVATE_RELEASE_CONTEXT_REQUIRED')
    driver = runpy.run_path(str(stage/'publish-r2.py'))
    read, write, inspect = (driver[key] for key in ('read','write','inspect'))
    require = driver['require']
    prev = read(stage/'plan.private.json')
    receipt = read(stage/'result.json')
    service = driver['SERVICE']
    name = driver['NAME']
    current = inspect(name)
    candidate = inspect(args.candidate)['Id']
    require(candidate==args.candidate,'PINNED_IMAGE_REQUIRED')
    require(receipt['status']=='published' and current['Image']==receipt['image']==prev['images']['candidate'],
            'PUBLISHED_GATEWAY_CHANGED')
    require(driver['runtime_identity'](current)==prev['runtime_private'], 'GATEWAY_RUNTIME_CHANGED')
    require(all(digest(Path(p))==h for p,h in prev['bind_hashes'].items()),'GATEWAY_BINDS_CHANGED')
    previous = stage/'candidate.compose.private.json'
    require(digest(previous)==prev['compose_hashes']['candidate'],'PUBLISHED_GATEWAY_COMPOSE_CHANGED')
    api_plan = read(api/'gate.private.json')
    require(inspect('socialmei-team-team-api-1')['Id']==api_plan['original_id'],'API_CHANGED')
    out.mkdir(mode=0o700)
    pair = {}
    for role,image in {'candidate':candidate,'rollback':current['Image']}.items():
        model = read(previous)
        model['services'][service]['image'] = image
        path = out/(role+'.compose.private.json')
        write(path, model)
        driver['run'](*driver['docker_compose'](path),'config','--quiet')
        pair[role] = {'image':image,'sha256':digest(path)}
    journal=out/'pair.private.json'
    write(journal,{'target_schema':46,'gateway':pair,'api_gate':digest(api/'gate.private.json'),
                   'stage1_frozen_plan':digest(stage/'plan.private.json'),'authorized':False})
    print(json.dumps({'gateway_frozen':pair,'pair_sha256':digest(journal)}))


if __name__=='__main__':
    main()
