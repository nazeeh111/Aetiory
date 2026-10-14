import difflib
from pathlib import Path
import sys
a=Path(sys.argv[1]).read_text().splitlines()
b=Path(sys.argv[2]).read_text().splitlines()
Path("artifact.html").write_text(difflib.HtmlDiff().make_file(a,b,fromdesc="old verifier",todesc="new verifier"))
