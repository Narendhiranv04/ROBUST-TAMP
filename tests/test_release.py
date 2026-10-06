import json
from pathlib import Path
from unittest.mock import patch
import pytest
from robust_tamp.__main__ import flags, seeds, trial_command, run_one
from robust_tamp.tables import paper_rows, summarize, load_records
from robust_tamp.resources import check_resources
from robust_tamp.provenance import identity

def test_evaluated_where_coupling():
    f=flags('no_where')
    assert 'parallel.enabled=false' in f and 'replan.output_mode=full_replan' in f
    assert 'memory.enabled=true' in f and 'replan.trigger_mode=if_rule' in f

def test_paper_icl_interfaces_are_distinct(tmp_path):
    c={'method':'full','model':'qwen3-vl-8b-thinking','endpoint':'http://localhost:8000','icl':'paper','mock':False,'gui':False}
    assert 'examples_v3' in trial_command(c,'FINAL.G1',0,tmp_path,1)
    for b in ['vlm_tamp','owl_tamp','inner_monologue','epog']:
        assert 'examples_v2' in trial_command(dict(c,method=b),'FINAL.G1',0,tmp_path,1)
    llm=trial_command(dict(c,model='qwen3-8b'),'FINAL.G1',0,tmp_path,1)
    assert '--vision' not in llm

def test_table5_all_available_cells_and_denominators():
    rows=paper_rows()
    assert len(rows)==10 and all(r['n']==140 for r in rows)
    assert rows[-1]['values'][2]==92.1
    assert all('unavailable' in r['latency_source'] for r in rows)

def test_aggregation_rejects_missing_duplicate_and_infrastructure():
    rows=[r for r in load_records() if r['label']=='ours_zero_shot']
    for bad in (rows[:-1],rows+[rows[0]],[dict(rows[0],termination_reason='infrastructure'),*rows[1:]]):
        with pytest.raises(ValueError):summarize(bad)

def test_reference_resources():assert check_resources()==[]

def test_archive_identity_detects_edits(tmp_path):
    import hashlib
    p=tmp_path/'x.py';p.write_text('x=1')
    (tmp_path/'release-manifest.json').write_text(json.dumps({'files':{'x.py':hashlib.sha256(p.read_bytes()).hexdigest()}}))
    assert identity(tmp_path)['dirty'] is False
    p.write_text('x=2');assert identity(tmp_path)['changed_files']==['x.py']

def test_only_infrastructure_reruns_and_attempts_preserved(tmp_path):
    c={'method':'oracle','timeout':10,'gui':False};calls=[]
    def fake(cmd,**kw):
        d=Path(cmd[cmd.index('--output-dir')+1]);calls.append(d)
        reason='infrastructure' if len(calls)==1 else 'max_replans'
        (d/'trial_log.jsonl').write_text(json.dumps({'event':'trial_end','termination_reason':reason})+'\n')
        return type('Result',(),{'returncode':0})()
    with patch('robust_tamp.__main__.subprocess.run',fake):
        result=run_one(c,'FINAL.K0',0,tmp_path)
        assert result['attempt']==2 and not result['infrastructure']
        assert run_one(c,'FINAL.K0',0,tmp_path)['resumed'] is True
    assert len(calls)==2 and (tmp_path/'FINAL.K0/seed_00.infra_attempt1/trial_log.jsonl').exists()

def test_seed_validation():
    assert seeds('0-2,5')==[0,1,2,5]
    with pytest.raises(ValueError):seeds('0,0')

def test_all_evaluated_ablation_configurations():
    expected={'no_memory':'memory.enabled=false','no_if':'replan.trigger_mode=discovery',
      'no_where':'replan.output_mode=full_replan','fixed_front':'replan.insertion_mode=always_front',
      'fixed_end':'replan.insertion_mode=always_end','no_when':'parallel.enabled=false'}
    from llm_pipeline.flags import PipelineFlags
    for method,assignment in expected.items():
        values=flags(method);assert assignment in values
        PipelineFlags.from_assignments(values)

def test_extended_tables_against_final_paper(tmp_path):
    from robust_tamp.extended_tables import generate
    out=tmp_path/'tables';generate(out)
    result=json.loads((out/'verification.json').read_text())
    assert all(r['matches'] for r in result['table2']+result['table4'])

def test_resume_rejects_configuration_change_before_execution(tmp_path):
    from robust_tamp.__main__ import main
    out=tmp_path/'run';out.mkdir();(out/'effective_config.json').write_text('{}')
    with patch('robust_tamp.provenance.identity',return_value={'commit':'release-sha256:test','dirty':False}), \
         patch('sys.argv',['robust_tamp','run','--method','oracle','--variants','FINAL.G0','--out',str(out),'--resume']):
        assert main()==2
    assert not (out/'.run.lock').exists()
