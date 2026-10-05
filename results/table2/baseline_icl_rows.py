"""Table 5 rows: zero-shot (all from baselines_final) and +ICL (kitchen from baselines_final, grill
from baselines_final_icl), on the paper's metric (evaluation.model_run_report.paper_outcome)."""
import glob, json, statistics, sys
sys.path.insert(0, '/home/projects/long-horizon/robust_tamp_icl')
from evaluation.model_run_report import paper_outcome
R = '/home/projects/long-horizon/robust_tamp_infer/real_trials/v2/'

def trials(root, b, prefix):
    out = []
    for d in sorted(glob.glob(f'{R}{root}/{b}/{prefix}*/seed_??')):
        v = d.split('/')[-2]
        ends = [json.loads(l) for l in open(d + '/trial_log.jsonl') if '"trial_end"' in l]
        if not ends:
            continue
        lat = []
        for x in glob.glob(d + '/prompts/*.exchange.json'):
            try: lat.append(json.load(open(x))['http_elapsed_s'])
            except Exception: pass
        out.append((v, ends[-1], paper_outcome(ends[-1], v), lat))
    return out

def row(k, g):
    allt = k + g
    sr = lambda ts: 100 * sum(o['success'] for _, _, o, _ in ts) / len(ts) if ts else float('nan')
    lat = [x for *_, l in allt for x in l]
    return (len(k), len(g), sr(k), sr(g), sr(allt), 100 * statistics.mean(o['pgc'] for _, _, o, _ in allt),
            statistics.mean(e['planner_calls'] for _, e, _, _ in allt), statistics.mean(e['planner_time_s'] for _, e, _, _ in allt),
            statistics.median(lat), statistics.mean(e['trial_time_s'] for _, e, _, _ in allt))

for b in sys.argv[1:]:
    k = trials('baselines_final', b, 'FINAL.K')
    for name, g in (('zero-shot', trials('baselines_final', b, 'FINAL.G')), ('+ICL', trials('baselines_final_icl', b, 'FINAL.G'))):
        if g:
            r = row(k, g)
            print(f'{b:16s} {name:9s} nK={r[0]} nG={r[1]} SR_K {r[2]:.1f} SR_G {r[3]:.1f} SR {r[4]:.1f} PGC {r[5]:.1f} '
                  f'Calls {r[6]:.1f} Plan {r[7]:.0f} Lat {r[8]:.1f} Time {r[9]:.0f}')
