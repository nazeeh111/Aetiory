"""Draw the actual two-trial diagnostic trace, not a hypothetical product UI."""
from pathlib import Path
import json,html,hashlib
P=Path(__file__).resolve().parent;c=json.loads((P/'case.json').read_text());assert c['input_records']==9 and c['workers']==128 and c['input_total']==3370;assert c['trials'][0]['replacement']==['none'] and not c['trials'][0]['goal_met'];assert c['trials'][1]['replacement']==['int','1'] and c['trials'][1]['goal_met'];assert c['fresh_replay']=='reproduced' and c['fresh_undo_equal']
for mobile in [False,True]:
 name='paired-trials-mobile' if mobile else 'paired-trials';W,H=(480,1200) if mobile else (1200,800);s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Arial" role="img" aria-labelledby="{name}-title {name}-desc"><title id="{name}-title">Faultsplice: a changed failure is not success</title><desc id="{name}-desc">Two actual paired return trials retain an original zero-capacity ValueError; replacing zero with None produces a TypeError, while replacing zero with one meets the exact nine-record and 3370 total goal.</desc><rect width="100%" height="100%" fill="#f4f6f8"/>']
 def text(x,y,t,size=20,color='#161c26',weight=400,mono=False):s.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}"'+(' font-family="Courier New"' if mono else '')+'>'+html.escape(str(t))+'</text>')
 def line(x1,y1,x2,y2,color='#cbd2dc'):s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.5"/>')
 text(32,38,'FAULTSPLICE / ACTUAL RETURN TRIALS',13 if mobile else 16,'#526071',700)
 if mobile:text(32,92,'Changing the failure',30,weight=700);text(32,130,"isn’t success.",30,weight=700)
 else:text(32,100,"Changing the failure isn’t success.",46,weight=700)
 text(32,178 if mobile else 145,'9 records · 128 workers · original capacity 0',17 if mobile else 23,'#526071')
 text(32,214 if mobile else 196,c['return_expression'],16 if mobile else 23,mono=True)
 text(32,247 if mobile else 232,'Each trial forks a fresh live computation.',15 if mobile else 18,'#526071')
 if mobile:
  for i,top in enumerate([310,598]):
   original='ValueError';alt='TypeError' if i==0 else 'exit 0';replacement='None' if i==0 else '1';line(32,top-24,448,top-24);text(32,top,'TRIAL '+str(i+1),14,'#526071',700);text(32,top+46,'0 → '+replacement,34,'#1755ad',700)
   text(32,top+89,'Original: ValueError · exit 1',18);text(32,top+124,'Alternate: '+alt+(' · exit 1' if i==0 else ''),18,'#b32335' if i==0 else '#161c26')
   if i==0:text(32,top+174,'Goal NOT met',23,'#b32335',700);text(32,top+208,'A different exception is still a failure.',15,'#526071')
   else:text(32,top+163,'9 records · 9 batches · total 3370',18);text(32,top+211,'Exact stdout goal MET',23,'#1755ad',700)
  fy=932;line(32,fy,448,fy);text(32,fy+43,'Fresh replay reproduced both outcomes.',18,weight=700);text(32,fy+76,'Fresh unchanged control kept the failure.',17);text(32,fy+109,'Native children were reaped.',17)
  text(32,1132,'A diagnostic experiment, not a source patch.',16,'#526071');text(32,1166,'Owned synthetic workload · not general causal proof',13,'#526071')
 else:
  text(64,290,'ORIGINAL PARENT / RETURN 0',15,'#1755ad',700);text(640,290,'ALTERNATE CHILD / ONE RETURN REPLACED',15,'#b32335',700);line(32,312,1168,312)
  for i,top in enumerate([360,528]):
   text(64,top,'Trial '+str(i+1),16,'#526071',700);text(64,top+42,'ValueError · exit 1',26,weight=700);text(64,top+77,'n must be at least one',19,'#526071')
   text(640,top,'Replacement: '+('None' if i==0 else '1'),20,'#b32335' if i==0 else '#1755ad',700)
   text(640,top+42,'TypeError · exit 1' if i==0 else '9 records · 9 batches · total 3370',25,weight=700)
   text(640,top+77,'Goal NOT met' if i==0 else 'Exact stdout goal MET',20,'#b32335' if i==0 else '#1755ad',700)
   if i==0:line(32,472,1168,472)
  line(592,328,592,626);line(32,658,1168,658)
  text(32,701,'Fresh paired replay reproduced both outcomes; unchanged control reproduced the original failure.',20,weight=700)
  text(32,738,'Native children reaped · target source unchanged · one eligible return, two attempted trials',18,'#526071')
  text(32,777,'Diagnostic influence on this owned run, not a source patch or general causal proof.',16,'#526071')
 s.append('</svg>');svg='\n'.join(s)+'\n';(P/(name+'.svg')).write_text(svg);(P/(name+'.html')).write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Faultsplice return trials</title><style>body{margin:0}.diagram-container{overflow-x:auto}svg{display:block;min-width:'+str(W)+'px}</style><div class="diagram-container">'+svg+'</div></html>')
files=['case.json','render.py','paired-trials.svg','paired-trials-mobile.svg','paired-trials.html','paired-trials-mobile.html'];(P/'figure-manifest.json').write_text(json.dumps({'source_revision':c['source_revision'],'type':'Source-derived paired trial trace, not an application screenshot or new universal causal claim','files':{n:{'bytes':(P/n).stat().st_size,'sha256':hashlib.sha256((P/n).read_bytes()).hexdigest()} for n in files}},indent=2)+'\n')
