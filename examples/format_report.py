import pprint,json,sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_bytes())
Path("artifact.txt").write_text(pprint.pformat(data,width=120,sort_dicts=False))
