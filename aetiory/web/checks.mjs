// Product contracts, not a native execution or browser-layout test.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {validatePayload,receiptAssessment,hashText,selectorText,valueText} from './app.js';
const actual=JSON.parse(fs.readFileSync(new URL('./demo.json',import.meta.url),'utf8'));
validatePayload(actual);
let checks=1;
const clone=()=>structuredClone(actual);
for(const e of actual.experiments){for(const side of ['before','after']){assert.equal(await hashText(e.artifacts[side].text),e.artifacts[side].sha256);checks++;}assert.equal(receiptAssessment(e,{before:'match',after:'match'}).accepted,true);checks++;}
const mutations=[p=>p.schema='arbitrary',p=>p.experiments[1].id=p.experiments[0].id,p=>p.experiments[0].artifacts.before.text=42,p=>p.experiments[0].artifacts.after.sha256='not-a-hash',p=>p.experiments[0].selector.sibling=-1,p=>p.experiments[0].event.id=1.2,p=>p.experiments[0].event.ancestry[0].line=-1,p=>p.experiments[0].guards.child_reaped='true',p=>p.experiments[0].source.start_line=0,p=>p.experiments[0].changes.find(c=>c.selected).selected=1,p=>p.experiments[0].changes.find(c=>c.selected).before=Infinity,p=>p.experiments[0].status='revolutionary',p=>{let v=0;for(let i=0;i<43;i++)v=[v];p.experiments[0].changes.find(c=>c.selected).before=v;}];
for(const mutate of mutations){const p=clone();mutate(p);assert.throws(()=>validatePayload(p));checks++;}
for(const status of ['no_effect','refused','partial']){const p=clone();p.experiments[0].status=status;validatePayload(p);const a=receiptAssessment(p.experiments[0],{before:'match',after:'match'});assert.equal(a.accepted,false);assert.equal(a.downloadAfter,status==='no_effect');checks++;}
for(const key of Object.keys(actual.experiments[0].guards)){for(const v of [false,null]){const p=clone();p.experiments[0].guards[key]=v;validatePayload(p);assert.equal(receiptAssessment(p.experiments[0],{before:'match',after:'match'}).accepted,false);checks++;}}
for(const side of ['before','after']){for(const value of ['MISMATCH','unavailable','identity not retained']){assert.equal(receiptAssessment(actual.experiments[0],{before:'match',after:'match',[side]:value}).accepted,false);checks++;}}
const missing=clone();missing.experiments[0].status='partial';missing.experiments[0].event=null;missing.experiments[0].source=null;missing.experiments[0].changes=[];missing.experiments[0].artifacts.after=null;validatePayload(missing);assert.equal(receiptAssessment(missing.experiments[0],{before:'match',after:'not retained'}).accepted,false);checks++;
const contradictory=clone();contradictory.experiments[0].changes.find(c=>c.selected).after=contradictory.experiments[0].changes.find(c=>c.selected).before;assert.equal(receiptAssessment(contradictory.experiments[0],{before:'match',after:'match'}).contradictory,true);checks++;
const script='<img src="https://invalid.example/x" onerror="alert(1)"><script>globalThis.bad=true</script>';
const hostile=clone();hostile.experiments[0].source.text=script;hostile.experiments[0].changes.find(c=>c.selected).before=script;hostile.experiments[0].event.args_preview={html:script};validatePayload(hostile);assert.equal(valueText(hostile.experiments[0].changes.find(c=>c.selected).before),script);checks++;
const source=fs.readFileSync(new URL('./app.js',import.meta.url),'utf8');assert(!/\.innerHTML|insertAdjacentHTML|\.srcdoc|eval\s*\(|new Function/.test(source));checks++;
assert.equal(selectorText(actual.experiments[0].selector),'#from0_72 → element sibling 1');assert.equal(selectorText(actual.experiments[1].selector),'/baseline/outputs/MANIFOLD/faces/98/1');checks++;
const self=clone();self.experiments[0].selector.sibling=0;validatePayload(self);assert.equal(selectorText(self.experiments[0].selector),'#from0_72 (element)');checks++;
console.log(`${checks} viewer contract controls passed. Actual proof bytes match; malformed, partial, missing, contradictory, unauthenticated-value and hash-mismatch paths covered. No target program executed.`);
