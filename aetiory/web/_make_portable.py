"""Build one self-contained recorded viewer, without executing its source.

Prototype consumer packaging helper. The final native CLI owns its own validated
record construction; this helper deliberately performs no target execution.
"""
import argparse
import json
import html as html_module
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def portable_document(payload):
    if payload.get('schema')!='experiment-view/1':
        raise ValueError('Expected experiment-view/1')
    data=json.dumps(payload,ensure_ascii=True,separators=(',',':'))
    if len(data.encode())>8*1024*1024:
        raise ValueError('Record exceeds 8 MiB')
    data=data.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    css=(ROOT/'style.css').read_text()
    js=(ROOT/'app.js').read_text()
    if '</style' in css.lower() or '</script' in js.lower():
        raise ValueError('Unexpected trusted resource closing tag')
    html=(ROOT/'index.html').read_text()
    html=html.replace('<link rel="stylesheet" href="style.css">','<style>'+css+'</style>')
    html=html.replace('<script type="module" src="app.js"></script>','<script id="embedded-record" type="application/json">'+data+'</script><script type="module">'+js+'</script>')
    notices=html_module.escape((ROOT/'NOTICES.txt').read_text())
    html=html.replace('<a href="NOTICES.txt">Licenses</a>', '<a href="#included-licenses">Licenses</a>')
    html=html.replace('</footer>', '<details id="included-licenses"><summary>Included licenses and provenance</summary><pre>'+notices+'</pre></details></footer>')
    return html

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.record.stat().st_size>8*1024*1024:
        raise ValueError('Input exceeds 8 MiB')
    text=portable_document(json.loads(args.record.read_text()))
    with args.output.open('x',encoding='utf-8',newline='\n') as f:
        f.write(text)
    print(args.output)
