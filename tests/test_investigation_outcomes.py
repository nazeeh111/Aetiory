"""End-to-end bounded outcome states, partial evidence, and contract guards."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest
from aetiory import engine
from aetiory.export import export_partial
from aetiory.outcome import outcome, trial_classification


def setup_case(root, mode):
    root.mkdir(); module=root/'target.py'; module.write_text('def value():\n    return 1\n')
    script=root/'entry.py'
    if mode=='no_candidates': body="v=target.value()\nPath('artifact.json').write_text(json.dumps({'answer':'unmatched'}))\n"
    elif mode=='failed': body="v=target.value()\nif v != 1: raise RuntimeError('synthetic failure')\nPath('artifact.json').write_text(json.dumps({'answer':1}))\n"
    elif mode=='confirmed': body="v=target.value()\nPath('artifact.json').write_text(json.dumps({'answer':v}))\n"
    elif mode=='refused': body="stream=Path(__file__).open('r')\ntry:\n v=target.value()\n Path('artifact.json').write_text(json.dumps({'answer':1}))\nfinally:\n stream.close()\n"
    else: body="v=target.value()\nPath('artifact.json').write_text(json.dumps({'answer':1 if v in (0,1,2) else 1}))\n"
    script.write_text('import json,target\nfrom pathlib import Path\n'+body)
    obs=engine.observe(argparse.Namespace(script=str(script),module=['target='+str(module)],input=[],arg=[],artifact='artifact.json',out=str(root/'obs'),max_events=1000,timeout=3))
    assert obs['status']=='observed'
    return root/'obs/observation.json'


def args(root, obs, *, limit=16, seconds=20):
    return argparse.Namespace(observation=str(obs),out=str(root/'searched'),pointer='/answer',html_id=None,html_next_sibling=0,start=None,end=None,encoding='json',max_trials=limit,seconds=seconds,timeout=3)


@pytest.mark.parametrize(('mode','limit','seconds','reason'),[
    ('no_candidates',16,20,'no_candidates'),('unchanged',1,20,'trial_limit'),
    ('unchanged',16,.01,'time_limit'),('unchanged',2,20,'candidates_exhausted'),
    ('failed',16,20,'trials_failed'),('refused',16,20,'trials_refused'),
    ('confirmed',16,20,'influence_confirmed')])
def test_actual_bounded_end_states(tmp_path,mode,limit,seconds,reason):
    root=tmp_path/mode;obs=setup_case(root,mode);report=engine.search(args(root,obs,limit=limit,seconds=seconds))
    assert report['termination_reason']==reason
    counts=report['coverage']; assert sum(counts[k] for k in ('changed','unchanged','refused','timed_out','failed','parent_mismatch','selector_error'))==report['trial_count']
    assert counts['completed_trials']==counts['changed']+counts['unchanged']
    assert counts['remaining_trials']==counts['planned_trials']-counts['attempted_trials']
    if mode in ('failed','refused'):assert counts['completed_trials']==0
    assert (report['status']=='influence_confirmed')==(mode=='confirmed')
    assert json.loads((root/'searched/search.json').read_bytes())==report


def test_independent_small_counter_oracle():
    valid={'run':{'ok':True,'child':{'ok':True},'child_reaped':True},'paired_parent_baseline_equal':True,'selected_changed':False}
    changed={**valid,'selected_changed':True}
    refused={'run':{'ok':False,'error':{'type':'Refusal'}},'paired_parent_baseline_equal':False}
    timed={'run':{'ok':False,'error':{'type':'Timeout'}},'paired_parent_baseline_equal':False}
    failed={'run':{'ok':False,'child':{'ok':False,'error':{'type':'RuntimeError'}}},'paired_parent_baseline_equal':True}
    mismatch={'run':{'ok':True,'child':{'ok':True},'child_reaped':True},'paired_parent_baseline_equal':False}
    selector={**valid,'selector_error':'bad selector'}
    trials=[valid,changed,refused,timed,failed,mismatch,selector]
    expected=['unchanged','changed','refused','timed_out','failed','parent_mismatch','selector_error']
    assert [trial_classification(t) for t in trials]==expected
    actual=outcome(trials,4,10,'trial_limit',False,True)['coverage']
    assert {k:actual[k] for k in expected}==dict.fromkeys(expected,1)
    assert actual['completed_trials']==2 and actual['attempted_trials']==7 and actual['remaining_trials']==3


def test_controlled_mid_search_refusal_retains_previous_trial_and_exports(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'unchanged');real=engine.run_once
    def interrupted(manifest,path,name,*a,**kw):
        if name=='trial-0002':raise engine.Refusal('controlled second-trial refusal')
        return real(manifest,path,name,*a,**kw)
    with patch.object(engine,'run_once',side_effect=interrupted):report=engine.search(args(root,obs))
    assert report['termination_reason']=='trial_error' and report['coverage']['unchanged']==1 and report['coverage']['refused']==1
    assert report['trials'][0]['run']['ok'] and report['trials'][1]['run']['error']['message']=='controlled second-trial refusal'
    result=export_partial(obs,root/'searched/search.json','Partial test',root/'export')
    exported=json.loads(Path(result['file']).read_bytes())
    assert exported['status']=='unresolved' and exported['search']['trials']==report['trials']
    assert not (root/'export/index.html').exists()


def test_wrong_observation_and_tampered_coverage_refuse(tmp_path):
    root=tmp_path/'first';obs=setup_case(root,'unchanged');report=engine.search(args(root,obs,limit=1))
    second=tmp_path/'second';other=setup_case(second,'unchanged')
    with pytest.raises(engine.Refusal,match='same retained run'):export_partial(other,root/'searched/search.json','wrong',root/'bad')
    path=root/'searched/search.json';report['coverage']['unchanged']=999;path.write_bytes(engine.encoded(report)+b'\n')
    with pytest.raises(engine.Refusal,match='coverage'):export_partial(obs,path,'tampered',root/'bad2')


def test_undo_failure_never_becomes_confirmed(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'confirmed');real=engine.run_once
    def fail_undo(manifest,path,name,*a,**kw):
        if name=='fresh-undo':raise engine.Refusal('controlled undo refusal')
        return real(manifest,path,name,*a,**kw)
    with patch.object(engine,'run_once',side_effect=fail_undo):report=engine.search(args(root,obs))
    assert report['status']=='unresolved' and report['termination_reason']=='fresh_undo_failed'
    assert report['coverage']['changed']==1 and report['fresh_undo']['error']['type']=='Refusal'
    out=export_partial(obs,root/'searched/search.json','undo failed',root/'export')
    assert out['status']=='exported_unresolved'


def test_cli_search_and_partial_export_expose_same_outcome(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'unchanged');search=root/'cli-search';output=root/'cli-export'
    command=[sys.executable,'-m','aetiory','search','--observation',str(obs),'--pointer','/answer','--out',str(search),'--max-trials','1','--seconds','20','--timeout','3']
    trial=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert trial.returncode==3,trial.stderr
    summary=json.loads(trial.stdout); assert summary['termination_reason']=='trial_limit' and summary['coverage']['remaining_trials']==1
    result=subprocess.run([sys.executable,'-m','aetiory','export','--observation',str(obs),'--search',str(search/'search.json'),'--out',str(output)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    exported=json.loads((output/'investigation.json').read_bytes());assert exported['search']['termination_reason']=='trial_limit'


def test_native_permission_denial_is_not_retried(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'unchanged'); calls=[]
    def denied(manifest,path,name,*a,**kw):
        calls.append(name)
        raise PermissionError('controlled denial')
    with patch.object(engine,'run_once',side_effect=denied):report=engine.search(args(root,obs))
    assert calls==['trial-0001']
    assert report['stop_trigger']=='permission_denied' and report['termination_reason']=='permission_denied'
    assert report['fresh_undo']['error']['type']=='PermissionError'


def test_simulated_child_read_denial_stops_and_exports(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'confirmed');read=engine.bounded_bytes;run=engine.run_once;calls=[]
    def denied(path,*a,**kw):
        if 'trial-0001/child/artifact.json' in str(path): raise PermissionError('simulated child denial')
        return read(path,*a,**kw)
    def track(*a,**kw):
        calls.append(a[2]);return run(*a,**kw)
    with patch.object(engine,'bounded_bytes',side_effect=denied),patch.object(engine,'run_once',side_effect=track): report=engine.search(args(root,obs))
    assert calls==['trial-0001'] and report['termination_reason']=='permission_denied'
    assert report['trials'][0]['selector_error_type']=='PermissionError'
    result=subprocess.run([sys.executable,'-m','aetiory','export','--observation',str(obs),'--search',str(root/'searched/search.json'),'--out',str(root/'export')],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    exported=json.loads((root/'export/investigation.json').read_bytes())
    assert exported['search']['termination_reason']=='permission_denied'
    assert exported['search']['trials'][0]['selector_error_type']=='PermissionError'


@pytest.mark.parametrize('where', ['parent','child'])
def test_simulated_permission_receipt_stops(tmp_path,where):
    root=tmp_path/where;obs=setup_case(root,'unchanged');calls=[]
    def denied(manifest,path,name,*a,**kw):
        calls.append(name);error={'type':'PermissionError','message':'simulated receipt'}
        return {'ok':False,'error':error} if where=='parent' else {'ok':True,'child':{'ok':False,'error':error}}
    with patch.object(engine,'run_once',side_effect=denied): report=engine.search(args(root,obs))
    assert calls==['trial-0001'] and report['termination_reason']=='permission_denied'


def test_simulated_plan_write_denial_stops(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'confirmed');write=Path.write_bytes;run=engine.run_once;calls=[]
    def denied(path,*a,**kw):
        if path.name=='intervention.json': raise PermissionError('simulated plan denial')
        return write(path,*a,**kw)
    def track(*a,**kw): calls.append(a[2]);return run(*a,**kw)
    with patch.object(Path,'write_bytes',denied),patch.object(engine,'run_once',side_effect=track): report=engine.search(args(root,obs))
    assert calls==['trial-0001'] and report['termination_reason']=='permission_denied'
    assert report['trials'][0]['plan_error']['type']=='PermissionError'


def test_simulated_classifier_check_denial_stops_undo(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'unchanged');read=engine.bounded_bytes;run=engine.run_once;calls=[]; checks=[]
    def denied(path,*a,**kw):
        if Path(path).name=='outcome.py':
            checks.append(1)
            if len(checks)==2: raise PermissionError('simulated classifier denial')
        return read(path,*a,**kw)
    def track(*a,**kw): calls.append(a[2]);return run(*a,**kw)
    with patch.object(engine,'bounded_bytes',side_effect=denied),patch.object(engine,'run_once',side_effect=track): report=engine.search(args(root,obs,limit=1))
    assert calls==['trial-0001'] and report['termination_reason']=='permission_denied'
    assert report['outcome_check_error']['type']=='PermissionError'


def test_ordinary_artifact_io_error_is_not_permission_denial(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'confirmed');read=engine.bounded_bytes;run=engine.run_once;calls=[]
    def failed(path,*a,**kw):
        if 'trial-0001/child/artifact.json' in str(path): raise OSError('ordinary simulated I/O error')
        return read(path,*a,**kw)
    def track(*a,**kw): calls.append(a[2]);return run(*a,**kw)
    with patch.object(engine,'bounded_bytes',side_effect=failed),patch.object(engine,'run_once',side_effect=track): report=engine.search(args(root,obs))
    assert calls==['trial-0001','trial-0002','fresh-undo'] and report['termination_reason']=='influence_confirmed'


def test_simulated_scan_denial_stops_before_trial(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'unchanged');calls=[]
    def denied(*a,**kw): raise PermissionError('simulated scan denial')
    def track(*a,**kw): calls.append(a[2]);raise AssertionError('unexpected execution')
    with patch.object(engine,'load_events',side_effect=denied),patch.object(engine,'run_once',side_effect=track): report=engine.search(args(root,obs))
    assert not calls and report['termination_reason']=='permission_denied'
    assert report['candidate_scan_error']['type']=='PermissionError'
    assert report['coverage']['planned_trials'] is None


def test_simulated_fresh_undo_permission_receipt_is_denial(tmp_path):
    root=tmp_path/'case';obs=setup_case(root,'unchanged');real=engine.run_once;calls=[]
    def denied(manifest,path,name,*a,**kw):
        calls.append(name)
        if name=='fresh-undo': return {'ok':False,'error':{'type':'PermissionError','message':'simulated undo receipt'}}
        return real(manifest,path,name,*a,**kw)
    with patch.object(engine,'run_once',side_effect=denied):report=engine.search(args(root,obs,limit=1))
    assert calls==['trial-0001','fresh-undo'] and report['termination_reason']=='permission_denied'
