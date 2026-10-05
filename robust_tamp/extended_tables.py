"""Final-paper Tables 2 and 4 from preserved metric-bearing event records."""
from pathlib import Path
import json
from evaluation.paper_tables import cell, KITCHEN, GRILL, CORE_K, CORE_G
ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/'reference_results/events'
V2=EVENTS/'v2_runs'
ZS=V2/'table2/qwen3-vl-8b-thinking'
ICL=V2/'icl_v3/qwen3-vl-8b-thinking'
CONDITIONS=['Full system','no_memory','no_if','no_where','fixed_front','fixed_end','no_when','LLM planner']
# Latest paper Table 2: SR, Calls, Unn., Ins., Idle, Plan., Time, kitchen then grill.
EXPECTED=[
([95,4.2,0,27.5,118,377,457],[86.7,2.7,0,0,135,281,373]),
([85,4,0,30,131,342,420],[60,2.6,0,30,175,343,435]),
([95,5.5,.25,30,199,441,511],[76.7,2.8,0,20,171,317,408]),
([75,3.9,0,None,76,348,434],[56.7,4.5,0,None,221,546,648]),
([90,4,0,25,116,394,473],[30,6.1,0,66.7,185,821,916]),
([52.5,6.5,0,50,438,562,609],[30,2.5,0,70,188,320,410]),
([92.5,4.5,0,25,127,399,483],[66.7,2.5,0,16.7,147,274,375]),
([87.5,5.2,0,22.5,65,205,286],[23.3,9.2,0,6.7,288,375,426])]

def checked_cell(root,variants):
    for v in variants:
        found={p.parent.name for p in (root/v).glob('seed_??/trial_log.jsonl')}
        if found!={f'seed_{s:02d}' for s in range(10)}:raise ValueError(f'Incomplete records: {root.name}/{v}')
    return cell(root,variants)

def generate(out):
    lines=['# Table 2 · Component ablations','', '| Condition | Domain | SR (%) | Calls | Unn. | Ins. (%) | Idle (s) | Plan. (s) | Time (s) |', '|---|---|---:|---:|---:|---:|---:|---:|---:|'];audit=[]
    for i,name in enumerate(CONDITIONS):
        kitchen=ZS if i==0 else V2/'table2/qwen3-8b' if i==7 else V2/'ablations'/name
        grill=ICL if i==0 else V2/'ablations_icl_v3'/('qwen3-8b-icl' if i==7 else name)
        for j,(domain,root,variants) in enumerate([('Kitchen zero-shot',kitchen,CORE_K),('Grill ICL',grill,CORE_G)]):
            c=checked_cell(root,variants)
            values=[round(c['SR']*100,1),round(c['Calls'],1),round(c['Unn'],2),None if name=='no_where' else round(c['Ins']*100,1),round(c['Idle']),round(c['Plan']),round(c['Time'])]
            audit.append({'condition':name,'domain':domain,'values':values,'paper':EXPECTED[i][j],'matches':values==EXPECTED[i][j]})
            lines.append('| '+' | '.join([name,domain,*['—' if x is None else str(x) for x in values]])+' |')
    lines+=['','# Table 4 · Main results','','| Variant | Oracle SR (%) | SR (%) | PGC (%) | Calls | Plan. (s) | Idle (s) | Time (s) | Urg. (%) |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    main=[]
    for v in KITCHEN+GRILL:
        c=checked_cell(ZS if v in KITCHEN else ICL,[v]);ceil=checked_cell(EVENTS/'gt_fixed/full_system',[v])
        from evaluation.final_variants import get_final_variant
        has=bool(get_final_variant(v).expected_urgency)
        vals=[round(ceil['SR']*100,1),round(c['SR']*100,1),round(c['PGC']*100,1),round(c['Calls'],1),round(c['Plan']),round(c['Idle']) if has and c['Idle'] is not None else None,round(c['Time']),round(c['Urg']*100,1) if has and c['Urg'] is not None else None]
        main.append({'variant':v,'values':vals});lines.append('| '+' | '.join([v,*['—' if x is None else str(x) for x in vals]])+' |')
    expected_main = {'FINAL.K0': [100, 100, 100, 2.2, 229, None, 298, None], 'FINAL.G0': [100, 100, 100, 1.1, 117, None, 197, None], 'FINAL.K1': [100, 90, 93.3, 5.7, 481, 189, 561, 10], 'FINAL.K2': [100, 90, 95, 4, 328, None, 397, None], 'FINAL.K3': [100, 100, 100, 3.8, 385, 122, 480, 70], 'FINAL.K4': [100, 100, 100, 3.1, 316, 96, 390, 10], 'FINAL.G1': [100, 80, 97.1, 2.2, 204, 97, 296, 90], 'FINAL.G2': [100, 90, 98.6, 2.5, 285, 139, 377, 90], 'FINAL.G3': [100, 90, 98.6, 3.4, 355, 169, 445, 50], 'FINAL.K3-n2': [100, 90, 98.6, 3.9, 413, 143, 522, 70], 'FINAL.K3-n3': [100, 100, 100, 4, 442, 128, 580, 86.7], 'FINAL.G1-n1': [100, 80, 96, 2.6, 248, 132, 328, 50], 'FINAL.K1-w1': [100, 90, 98.6, 7.7, 655, 266, 774, 0], 'FINAL.K1-w2': [100, 90, 93.8, 6.4, 515, 143, 648, 0]}
    for row in main:
        row['matches'] = row['values'] == expected_main[row['variant']]
        if not row['matches']: raise ValueError(f'Table 4 mismatch: {row}')
    lines+=['','SR/PGC/Ins./Urg. are percentages. Calls and Unn. are means per trial; Idle is mean waiting per discovery-triggered episode. Kitchen uses zero-shot and grill uses final examples_v3. Oracle rows are separate ground-truth planning runs.','']
    out.mkdir(parents=True,exist_ok=False)
    (out/'tables2-and4.md').write_text('\n'.join(lines));(out/'verification.json').write_text(json.dumps({'table2':audit,'table4':main},indent=2))
    mismatches=[x for x in audit if not x['matches']]
    print(f'Table 2: {len(audit)-len(mismatches)}/16 domain rows match paper; Table 4: 14/14 variant rows match paper.')
    if mismatches:raise ValueError(f'Table 2 discrepancies: {mismatches}')
