"""Reproduce both shipped investigations with this installed Python's sources."""
import argparse
import json
from pathlib import Path
import sysconfig
from types import SimpleNamespace
from aetiory import engine
from aetiory.export import experiment, export_record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, help='New no-clobber output directory')
    p.add_argument('--only', choices=('diff','report'), help='Run one case instead of both')
    args = p.parse_args()
    root = engine.create_dir(args.out)
    here = Path(__file__).resolve().parent
    stdlib = Path(sysconfig.get_path('stdlib'))
    cases = [
        ('diff', 'difflib', here/'compare_sources.py', [here/'inputs/verifier-0.1.1.py',here/'inputs/verifier-0.1.2.py'], 'artifact.html',
         {'pointer':None,'html_id':'from0_72','html_next_sibling':1,'encoding':'json'}, 'Which decision changed this diff highlight?'),
        ('report', 'pprint', here/'format_report.py', [here/'inputs/native-geometry-report.json'], 'artifact.txt',
         {'pointer':'/baseline/outputs/MANIFOLD/faces/98/1','html_id':None,'html_next_sibling':0,'encoding':'literal'}, 'Which return controls one value in this report?')]
    records, receipts = [], []
    for key, module, script, inputs, artifact, selector, title in cases:
        if args.only and key != args.only:
            continue
        observation = root/(key+'-observation')
        search = root/(key+'-search')
        baseline = engine.observe(SimpleNamespace(script=str(script),module=[module+'='+str(stdlib/(module+'.py'))],input=[str(x) for x in inputs],arg=[str(x) for x in inputs],artifact=artifact,out=str(observation),max_events=300000,timeout=60))
        if not baseline['baseline_byte_parity']:
            raise engine.Refusal('Original/observed outputs differ: '+key)
        result = engine.search(SimpleNamespace(observation=str(observation/'observation.json'),out=str(search),timeout=60,max_trials=128,seconds=600,start=None,end=None,**selector))
        if result['status'] != 'influence_confirmed':
            raise engine.Refusal('Search unresolved; inspect retained trials: '+str(search))
        replay = engine.replay(SimpleNamespace(plan=str(search/'intervention.json'),out=str(root/(key+'-replay')),timeout=60))
        if replay['status'] != 'reproduced':
            raise engine.Refusal('Replay refused; inspect retained receipt: '+key)
        records.append(experiment(observation/'observation.json', search/'search.json',title,root/(key+'-replay')/'replay.json'))
        receipts.append({'case':key,'candidate_count':result['candidate_count'],'trial_count':result['trial_count'],'undo_byte_identical':result['undo_byte_identical'],'replay':replay['status']})
        print(json.dumps(receipts[-1]),flush=True)
    exported = export_record({'schema':'experiment-view/1','experiments':records}, root/'viewer')
    (root/'cases.json').write_text(json.dumps({'cases':receipts,'export':exported},indent=2)+'\n')
    print(json.dumps(exported),flush=True)


if __name__=='__main__':
    main()
