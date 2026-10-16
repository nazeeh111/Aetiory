"""Verify an installed wheel from outside its source checkout, with isolated Python."""
import hashlib
import importlib.resources
import json
from pathlib import Path
import sys
import tempfile
from aetiory import __version__, engine
from aetiory.export import experiment, export_record
from aetiory.mcp import Server

assert __version__ == '0.2.2'
source_root = Path(__file__).resolve().parents[1]
assert not Path(engine.__file__).resolve().is_relative_to(source_root)
resources = importlib.resources.files('aetiory.web')
for name in ['index.html','style.css','app.js','demo.json','NOTICES.txt','API.md']:
    assert resources.joinpath(name).is_file(), name
payload = json.loads(resources.joinpath('demo.json').read_text())
assert len(payload['experiments']) == 4
for case in payload['experiments']:
    for side in ['before','after']:
        artifact=case['artifacts'][side]
        assert hashlib.sha256(artifact['text'].encode()).hexdigest()==artifact['sha256']
with tempfile.TemporaryDirectory(prefix='aetiory-installed-') as directory:
    root=Path(directory).resolve()
    (root/'target.py').write_text('def paused():\n    return (i for i in range(2))\ndef compute(x):\n    iterator=paused()\n    return next(iterator)+x*2\n')
    (root/'input.json').write_text('{"n":3}\n')
    (root/'entry.py').write_text('import target,json,sys\nfrom pathlib import Path\nx=json.loads(Path(sys.argv[1]).read_bytes())["n"]\nv=target.compute(x)\nPath("result.json").write_text(json.dumps({"answer":v,"untouched":13}))\n')
    server=Server(root,root/'state')
    observation=server.call('observe_program', {'script':'entry.py','modules':{'target':'target.py'},'inputs':['input.json'],'arguments':['@input:0'],'artifact':'result.json','timeout':3})
    assert observation['baseline_byte_parity'] is True
    search=server.call('find_influence',{'observation':observation['observation'],'selector':{'pointer':'/answer'},'max_trials':8,'seconds':20,'timeout':3})
    assert search['status']=='influence_confirmed'
    replay=server.call('replay_experiment',{'intervention':search['intervention'],'timeout':3})
    assert replay['status']=='reproduced'
    record=experiment(observation['report_file'],search['report_file'],replay_path=replay['report_file'])
    assert record['changes']==[{'path':'/answer','before':6,'after':7,'selected':True}]
    exported=export_record({'schema':'experiment-view/1','experiments':[record]},root/'portable')
    html=(root/'portable/index.html').read_text()
    assert 'id="embedded-record"' in html and 'id="included-licenses"' in html
    assert 'src="app.js"' not in html
    assert 'MIT License' in html and 'PYTHON SOFTWARE FOUNDATION' in html
    (root/'failed.py').write_text('import json\ndef capacity():\n    return 0\nn=capacity()\nif not n:\n    raise ValueError("zero capacity")\nprint(json.dumps({"records":9,"checksum":45},sort_keys=True))\n')
    diagnostic=server.call('diagnose_program',{'script':'failed.py','stdout_pointer':'',
        'stdout_equals':'{"checksum":45,"records":9}','max_trials':8,'seconds':20,'timeout':3})
    assert diagnostic['status']=='diagnosed' and diagnostic['source_repair'] is False
    assert server.call('inspect_experiment',{'handle':diagnostic['diagnosis']})['kind']=='diagnosis'
    diagnostic_record=json.loads(Path(diagnostic['experiment_file']).read_bytes())['experiments'][0]
    assert diagnostic_record['selector']['kind']=='successful-exit'
    assert json.loads(diagnostic_record['artifacts']['before']['text'])['kind']=='exception'
    assert json.loads(diagnostic_record['artifacts']['after']['text'])['exit_code']==0
print(json.dumps({'status':'passed','python':sys.version.split()[0],'installed_engine':str(engine.__file__),'resources':6,'actual_observe_search_replay_export':True,'selected_change':'6 to 7','untouched':13,'runtime_dependencies':0,'actual_failure_diagnosis':True}))
