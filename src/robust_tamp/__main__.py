"""Run reproducible experiments without a personal server layout."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
BASELINES = ('vlm_tamp', 'owl_tamp', 'inner_monologue', 'epog')
PRESETS = json.loads((ROOT/'configs/experiments.json').read_text())

def flags(method):
    from llm_pipeline.flags import PipelineFlags
    values = dict(PRESETS['full'])
    values.update(PRESETS.get(method, {}))
    return PipelineFlags().with_values(values).to_assignments()

def seeds(text):
    values = []
    for part in text.split(','):
        if '-' in part:
            a,b = map(int, part.split('-')); values.extend(range(a,b+1))
        else: values.append(int(part))
    if not values or min(values)<0 or len(values)!=len(set(values)):
        raise ValueError('Seeds must be distinct nonnegative integers, e.g. 0 or 0-9.')
    return values

def profile(name):
    from llm_pipeline.model_profiles import PROFILES
    if name not in PROFILES: raise ValueError(f'Unknown model profile {name!r}; run profiles.')
    return PROFILES[name]

def health(endpoint, model):
    p=profile(model)
    with urllib.request.urlopen(endpoint.rstrip('/')+'/v1/models', timeout=10) as f: data=json.load(f)
    with urllib.request.urlopen(endpoint.rstrip('/')+'/version', timeout=10) as f: version=json.load(f)
    if p['served_name'] not in [x['id'] for x in data['data']]:
        raise ValueError(f"Server does not serve {p['served_name']}; returned {[x['id'] for x in data['data']]}")
    return {'models':data, 'version':version}

def environment():
    env=dict(os.environ)
    env.update(SIM_BACKEND='mujoco', HEADLESS='True', PYTHONDONTWRITEBYTECODE='1')
    env['PYTHONPATH']=os.pathsep.join([str(ROOT/'src'), str(ROOT/'experiments'), str(ROOT/'src/pddlstream')])
    env.setdefault('MUJOCO_GL','egl')
    env['LLM_REQUEST_TIMEOUT_S']='1800'
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
    return env

def trial_command(c, variant, seed, directory, attempt):
    method=c['method']; cmd=[sys.executable,'-m']
    common=['--variant',variant,'--seed',str(seed),'--output-dir',str(directory),'--attempt',str(attempt)]
    if method=='oracle':
        cmd+=['llm_pipeline.oracle_trial_runner',*common]
    elif method in BASELINES:
        cmd+=['baselines.run_baseline_trial',*common,'--baseline',method,'--model',c['model'],
              '--remote-url',c['endpoint'],'--icl-mode','examples_v2' if c['icl']=='paper' else 'zero_shot']
        if c['mock']:cmd+=['--mock']
    else:
        p=profile(c['model']); cmd+=['llm_pipeline.trial_runner',*common,'--model',c['model'],
          '--model-type',p['model_type'],'--remote','--remote-api','openai','--remote-url',c['endpoint'],
          '--planner-max-new-tokens','24576','--no-live-masks','--no-goal-check',
          '--icl-mode','examples_v3' if c['icl']=='paper' else 'zero_shot']
        if p['model_type']=='vlm':cmd+=['--vision']
    if method not in BASELINES:
        for flag in flags(method):cmd+=['--flag',flag]
    if c['gui']:cmd+=['--gui']
    elif method not in BASELINES:cmd+=['--headless']
    return cmd

def last_end(directory):
    log=directory/'trial_log.jsonl'
    if log.exists():
        events=[json.loads(l) for l in log.read_text().splitlines() if l.strip()]
        return next((e for e in reversed(events) if e.get('event')=='trial_end'),None)
    return None

def run_one(c,variant,seed,out):
    parent=out/variant;parent.mkdir(exist_ok=True);directory=parent/f'seed_{seed:02d}'
    end=last_end(directory)
    if end and end.get('termination_reason')!='infrastructure':return {'variant':variant,'seed':seed,'resumed':True}
    # Each attempt is immutable. Only infrastructure failures are retried (two reruns).
    for attempt in range(1,4):
        prior=parent/f'{directory.name}.infra_attempt{attempt}'
        if prior.exists():continue
        if directory.exists(): directory.rename(prior);continue
        directory.mkdir();(directory/'effective_config.json').write_text(json.dumps(dict(c,variant=variant,seed=seed,attempt=attempt),indent=2))
        cwd=directory/'work';cwd.mkdir()
        cmd=trial_command(c,variant,seed,directory,attempt)
        (directory/'command.json').write_text(json.dumps(cmd,indent=2))
        with (directory/'stdout.log').open('w') as log:
            try: code=subprocess.run(cmd,cwd=cwd,env=environment(),stdout=log,stderr=subprocess.STDOUT,timeout=c['timeout']).returncode
            except subprocess.TimeoutExpired:code='timeout'
        end=last_end(directory)
        infra=not end or end.get('termination_reason')=='infrastructure'
        status={'variant':variant,'seed':seed,'attempt':attempt,'exit_code':code,'infrastructure':infra}
        (directory/'execution_status.json').write_text(json.dumps(status,indent=2))
        if not infra or code==2:return status
        directory.rename(prior)
    return {'variant':variant,'seed':seed,'infrastructure':True,'reruns_exhausted':True}

def run(args):
    from evaluation.model_run_report import FINAL_VARIANTS
    from robust_tamp.provenance import identity
    variants=args.variants or FINAL_VARIANTS
    if any(v not in FINAL_VARIANTS for v in variants):raise ValueError('Use FINAL.<variant>; see doctor for supported variants.')
    if len(variants)!=len(set(variants)):raise ValueError('Duplicate variants are not allowed.')
    if args.jobs<1 or args.timeout<1:raise ValueError('Jobs and timeout must be positive.')
    if args.mock and args.method not in BASELINES:raise ValueError('--mock applies only to baseline plumbing tests.')
    if args.method=='oracle' and args.icl!='zero_shot':raise ValueError('Oracle has no ICL condition.')
    code_identity=identity()
    if code_identity['commit'] is None or code_identity['dirty']:raise ValueError(f'Release verification failed: {code_identity}')
    out=args.out.resolve()
    if out==ROOT or out.is_relative_to(ROOT/'experiments/reference_results'):raise ValueError('Choose a separate output directory, outside reference_results.')
    c={k:v for k,v in vars(args).items() if k not in {'command','out','resume'}}
    c.update(variants=variants,seeds=seeds(args.seeds),release_identity=code_identity,
             flags=flags(args.method) if args.method not in BASELINES else ['memory.enabled=false','parallel.enabled=false','prompt.version=v2'],
             planner='oracle' if args.method=='oracle' else 'baseline_mock' if args.mock else 'model',
             model_profile=None if args.method=='oracle' else profile(args.model),max_replans=10,request_timeout_s=1800)
    manifest=out/'effective_config.json'
    if out.exists():
        if not args.resume or not manifest.exists():raise ValueError('Output exists. Use a new directory, or --resume with its exact configuration.')
        if json.loads(manifest.read_text())!=c:raise ValueError('Resume configuration differs; choose a new output directory.')
    else:out.mkdir(parents=True)
    # Exclusive lock prevents simultaneous writers and overlapping resumed batches.
    lock=out/'.run.lock'
    with lock.open('x') as f:f.write(str(os.getpid()))
    try:
        manifest.write_text(json.dumps(c,indent=2))
        if args.method!='oracle' and not args.mock:
            (out/'server.json').write_text(json.dumps(health(args.endpoint,args.model),indent=2))
        manifest.write_text(json.dumps(c,indent=2))
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures=[pool.submit(run_one,c,v,s,out) for v in variants for s in c['seeds']]
            outcomes=[f.result() for f in concurrent.futures.as_completed(futures)]
        (out/'batch_status.json').write_text(json.dumps(outcomes,indent=2))
        print(json.dumps(outcomes,indent=2))
        return int(any(x.get('infrastructure') for x in outcomes))
    finally:lock.unlink()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    subs=p.add_subparsers(dest='command',required=True)
    d=subs.add_parser('doctor',help='Verify imports, scene resources and optional inference endpoint')
    d.add_argument('--endpoint');d.add_argument('--model',default='qwen3-vl-8b-thinking')
    subs.add_parser('profiles',help='List pinned model profiles')
    for action in ('serve','download'):
        s=subs.add_parser(action,help='GPU server: foreground vLLM' if action=='serve' else 'GPU server: download the pinned checkpoint')
        s.add_argument('--model',default='qwen3-vl-8b-thinking')
        if action=='serve':
            s.add_argument('--host',default='127.0.0.1');s.add_argument('--port',type=int,default=8000)
            s.add_argument('--tensor-parallel-size',type=int,default=1);s.add_argument('--gpu-memory-utilization',type=float,default=.90)
    r=subs.add_parser('run',help='Run one trial or a matrix; outputs never overwrite existing trials')
    r.add_argument('--method',choices=['full','oracle',*list(PRESETS)[1:],*BASELINES],default='full')
    r.add_argument('--model',default='qwen3-vl-8b-thinking');r.add_argument('--variants',nargs='+')
    r.add_argument('--seeds',default='0');r.add_argument('--icl',choices=['zero_shot','paper'],default='zero_shot')
    r.add_argument('--endpoint',default='http://127.0.0.1:8000');r.add_argument('--out',type=Path,required=True)
    r.add_argument('--jobs',type=int,default=1);r.add_argument('--timeout',type=int,default=14400)
    r.add_argument('--gui',action='store_true');r.add_argument('--resume',action='store_true')
    r.add_argument('--mock',action='store_true',help='Baseline oracle responses: plumbing validation only')
    t=subs.add_parser('tables',help='Reproduce paper Table 5 from compact reference records')
    t.add_argument('--out',type=Path,required=True)
    t.add_argument('--extended',action='store_true',help='Also reproduce Tables 2 and 4 from preserved events')
    a=subs.add_parser('aggregate',help='Score fresh run logs with the paper metric')
    a.add_argument('run_dir',type=Path);a.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.command=='run':return run(args)
        if args.command=='profiles':
            from llm_pipeline.model_profiles import PROFILES
            print(json.dumps(PROFILES,indent=2));return 0
        if args.command=='doctor':
            env=environment();os.environ.update(env);sys.path.insert(0,str(ROOT/'src/pddlstream'))
            import sim_backend
            sim_backend.activate('mujoco')
            import mujoco, numpy, scipy, requests
            from pddlstream.algorithms.meta import solve
            from evaluation.model_run_report import FINAL_VARIANTS
            from robust_tamp.resources import check_resources
            from robust_tamp.provenance import identity
            issues=check_resources();ident=identity();print(json.dumps({'mujoco':mujoco.__version__,'variants':FINAL_VARIANTS,'resource_issues':issues,'release':ident},indent=2))
            binary=ROOT/'src/pddlstream/downward/builds/release/bin/downward'
            if not binary.exists():issues.append('FastDownward is not built: run sh experiments/build_planner.sh')
            if args.endpoint:print(json.dumps(health(args.endpoint,args.model),indent=2))
            for issue in issues:print(issue,file=sys.stderr)
            return int(bool(issues) or ident['dirty'] is not False)
        if args.command in ('serve','download'):
            prof=profile(args.model)
            if args.command=='download':
                cmd=['hf','download',prof['repo'],'--revision',prof['revision']]
                if prof.get('serve',{}).get('include'):cmd+=['--include',*prof['serve']['include']]
            else:
                from huggingface_hub import snapshot_download
                snapshot=snapshot_download(prof['repo'],revision=prof['revision'],allow_patterns=prof.get('serve',{}).get('include'))
                cmd=['vllm','serve',snapshot,'--served-model-name',prof['served_name'],
                  '--dtype','bfloat16','--max-model-len','32768','--generation-config','auto',
                  '--gpu-memory-utilization',str(args.gpu_memory_utilization),'--tensor-parallel-size',str(args.tensor_parallel_size),
                  '--host',args.host,'--port',str(args.port),*prof.get('serve',{}).get('args',[])]
            print(' '.join(cmd),flush=True);return subprocess.call(cmd)
        from robust_tamp.tables import generate,aggregate
        if args.command=='tables':
            generate(args.out)
            if args.extended:
                from robust_tamp.extended_tables import generate as extended
                extended(args.out/'extended')
        else:aggregate(args.run_dir,args.out)
        return 0
    except (ValueError,OSError,ImportError,KeyError) as exc:
        print(f'ROBUST-TAMP: {exc}',file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
