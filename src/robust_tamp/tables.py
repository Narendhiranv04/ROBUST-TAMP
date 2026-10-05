"""Strict paper-record aggregation; missing trials never become failures or successes."""
from pathlib import Path
import csv,json,statistics
ROOT=Path(__file__).resolve().parents[2]
METHODS=['vlm_tamp','owl_tamp','inner_monologue','epog','ours']
NAMES=['VLM-TAMP (adapted)','OWL-TAMP (reimplementation)','Inner Monologue (adapted prompt)','EPoG (without lost-object estimation)†','ROBUST-TAMP']
# Transcribed from the latest available main-paper Table 5; latency is NOT in the compact CSVs.
EXPECTED=[
[23.3,6.0,17.1,71.4,2.1,77,31.8,176],[23.3,10.0,18.6,71.9,2.1,85,35.9,183],
[17.8,2.0,12.1,49.1,6.3,730,115.3,790],[17.8,8.0,14.3,53.3,6.4,740,114.6,803],
[64.4,6.0,43.6,76.5,14.4,956,62.3,1114],[64.4,10.0,45.0,76.8,15.0,1047,68.4,1240],
[44.4,0.0,28.6,48.9,5.1,159,25.4,216],[44.4,0.0,28.6,48.8,5.1,159,25.5,216],
[94.4,22.0,68.6,86.5,5.1,540,103.4,643],[94.4,88.0,92.1,97.8,3.8,355,91.6,449]]

def load_records():
    out=[]
    for name in ('baselines','main_results'):
        with (ROOT/'experiments/reference_results/trial_level'/f'{name}.csv').open() as f:out.extend(csv.DictReader(f))
    return out

def summarize(rows, strict=True):
    keys=[(r['variant'],int(r['seed'])) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate trial key')
    if any(r['termination_reason']=='infrastructure' for r in rows):raise ValueError('Infrastructure failures must be excluded and rerun')
    k=[r for r in rows if r['variant'].startswith('FINAL.K')];g=[r for r in rows if r['variant'].startswith('FINAL.G')]
    if strict:
        from evaluation.model_run_report import FINAL_VARIANTS
        expected={(v,s) for v in FINAL_VARIANTS for s in range(10)}
        if set(keys)!=expected:raise ValueError(f'Incomplete Table 5 row: {len(keys)} / 140 trials')
    if not rows:raise ValueError('No scored trials')
    sr=lambda rs:100*sum(int(r['success']) for r in rs)/len(rs) if rs else None
    # Reconstruct PGC exactly from condition counts, avoiding CSV rounding artifacts.
    pgc=100*statistics.mean((int(r['conditions'])-int(r['unmet']))/int(r['conditions']) for r in rows)
    return [sr(k),sr(g),sr(rows),pgc,*[statistics.mean(float(r[x]) for r in rows) for x in ('planner_calls','planner_time_s','trial_time_s')]]

def paper_rows(records=None):
    records=load_records() if records is None else records;out=[]
    for i,method in enumerate(METHODS):
        zs=[r for r in records if r['label']==method+'_zero_shot'];icl=[r for r in records if r['label']==method+'_icl_grill']
        for mode,rs in [('zero-shot',zs),('+ ICL',[r for r in zs if r['variant'].startswith('FINAL.K')]+icl)]:
            values=summarize(rs);expected=EXPECTED[len(out)]
            formatted=[round(x,1 if n<5 else 0) for n,x in enumerate(values)]
            target=expected[:6]+expected[7:]
            if formatted!=target:raise ValueError(f'{method} {mode}: records {formatted} differ from paper {target}')
            out.append({'method':NAMES[i],'condition':mode,'n':len(rs),'values':expected,'verified_metrics':['SR_K','SR_G','SR','PGC','Calls','Plan.','Time'],'latency_source':'paper transcription; per-call records unavailable'})
    return out

def markdown(rows):
    """GitHub-compatible Table 5, paired by prompt condition."""
    links = ["https://github.com/Learning-and-Intelligent-Systems/kitchen-worlds",
             "https://arxiv.org/abs/2411.08253", "https://innermonologue.github.io/",
             "https://github.com/buaa-colalab/EPoG", "#method"]
    labels = ["VLM-TAMP<br>(adapted)", "OWL-TAMP<br>(reimplementation)",
              "Inner Monologue<br>(adapted prompt)", "EPoG†<br>(without lost-object estimation)", "ROBUST-TAMP (ours)"]
    headers = ["SR<sub>K</sub><br>(%) ↑", "SR<sub>G</sub><br>(%) ↑", "SR<br>(%) ↑", "PGC<br>(%) ↑",
               "Calls<br>/ trial ↓", "Plan.<br>(s) ↓", "Lat.<br>(s) ↓", "Time<br>(s) ↓"]
    out = ['<table>', '<caption>Table 5. Comparison across 14 MuJoCo variants × 10 seeds.</caption>',
           '<thead><tr><th rowspan="2" scope="col">Method</th><th colspan="8" scope="colgroup">Zero-shot</th><th colspan="8" scope="colgroup">With ICL</th></tr>',
           '<tr>' + ''.join('<th scope="col">'+h+'</th>' for h in headers*2) + '</tr></thead>', '<tbody>']
    for i,label in enumerate(labels):
        if i == 4: out += ['</tbody><tbody>']
        out += ['<tr><th scope="row"><a href="'+links[i]+'">'+label+'</a></th>']
        for condition in range(2):
            row = rows[i*2+condition]
            for j,v in enumerate(row['values']):
                value = f'{v:.1f}' if j in (0,1,2,3,4,6) else str(int(v))
                if j < 4 and v == max(r['values'][j] for r in rows): value = '<strong>'+value+'</strong>'
                if j < 4 and condition == 0 and v == max(r['values'][j] for r in rows[::2]): value = '<ins>'+value+'</ins>'
                out += ['<td align="right">'+value+'</td>']
        out += ['</tr>']
    out += ['</tbody></table>', '',
        '**Reading the table.** SR is task success; SR<sub>K</sub> and SR<sub>G</sub> cover 90 kitchen and 50 grill trials. PGC is partial goal completion. Calls are mean foundation-model calls per trial; Plan. and Time are mean planning and total time; Lat. is median per-call latency. Bold marks highest reported completion; underlining marks highest zero-shot completion. Lower cost alone does not imply better task performance.', '',
        '**Conditions.** All methods use Qwen3-VL-8B-Thinking. ICL affects grill only; kitchen results are shared. ROBUST-TAMP uses three examples (`examples_v3`); the baseline adaptations use two (`examples_v2`) in their respective interfaces. †The evaluated EPoG goal graph does not encode cooking. These are adaptations/reimplementations, not the original authors’ benchmark results.', '',
        '**Evidence.** Seven metrics per row (70 cells) match the preserved records. The ten latency cells are transcribed from the paper because final per-call logs are unavailable. Matching historical records is distinct from reproducing results with fresh model trials.', '']
    return '\n'.join(out)

def generate(out):
    out.mkdir(parents=True,exist_ok=False);rows=paper_rows()
    (out/'table5.md').write_text(markdown(rows));(out/'table5.json').write_text(json.dumps(rows,indent=2))
    print(f'Verified 70 aggregate cells from 950 unique scored trials. Latency: paper transcription. Output: {out}')

def aggregate(run_dir,out):
    from evaluation.model_run_report import build_report
    cfg=json.loads((run_dir/'effective_config.json').read_text())
    report=build_report(run_dir,cfg['variants'],cfg['seeds'])
    out.mkdir(parents=True,exist_ok=False);(out/'report.json').write_text(json.dumps(report,indent=2))
    print(f'Fresh-run report: {out}/report.json (see completeness/problems before interpreting means)')
