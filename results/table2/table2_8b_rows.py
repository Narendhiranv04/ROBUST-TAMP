"""Table 2 (a) 8B rows from the BF16 runs: SR / PGC (K, G, All) and Plan., on the paper's metric.
ICL rows: kitchen trials of the zero-shot run (the examples reach only the grill prompt), grill trials
of the ICL run(s)."""
import glob, json, statistics, sys
sys.path.insert(0, '/home/projects/long-horizon/robust_tamp_icl')
from evaluation.model_run_report import paper_outcome
V2 = '/home/projects/long-horizon/robust_tamp_infer/real_trials/v2/'

def trials(run, prefix):
    out = []
    for log in sorted(glob.glob(f'{V2}{run}/{prefix}*/**/trial_log.jsonl', recursive=True)):
        if '.infra' in log or 'shared_temp' in log:
            continue
        v = log[len(V2 + run) + 1:].split('/')[0]
        ends = [json.loads(l) for l in open(log) if '"trial_end"' in l]
        if ends:
            out.append((v, ends[-1], paper_outcome(ends[-1], v)))
    return out

def fmt(k, g):
    a = k + g
    sr = lambda t: 100 * sum(o['success'] for *_, o in t) / len(t)
    pgc = lambda t: 100 * statistics.mean(o['pgc'] for *_, o in t)
    plan = statistics.mean(e['planner_time_s'] for _, e, _ in a)
    return (f'nK={len(k)} nG={len(g)}  SR {sr(k):.1f} {sr(g):.1f} {sr(a):.1f}  PGC {pgc(k):.1f} {pgc(g):.1f} {pgc(a):.1f}  '
            f'Plan {plan:.0f}')

rows = {'VLM ZS': ('table2/qwen3-vl-8b-thinking', ['table2/qwen3-vl-8b-thinking']),
        'VLM ICL': ('table2/qwen3-vl-8b-thinking', ['icl_v3/qwen3-vl-8b-thinking']),
        'LLM ZS': ('table2/qwen3-8b', ['table2/qwen3-8b']),
        'LLM ICL': ('table2/qwen3-8b', ['ablations_icl_v3/qwen3-8b-icl', 'ablations_icl_v3_extra/qwen3-8b-icl'])}
for name, (krun, gruns) in rows.items():
    k = trials(krun, 'FINAL.K')
    g = [t for r in gruns for t in trials(r, 'FINAL.G')]
    print(f'8B {name:8s}', fmt(k, g), sorted({v for v, *_ in g}) if 'ICL' in name else '')
