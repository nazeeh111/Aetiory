// Canonical target outcome and typed stdout checks; no native execution claim.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {outcomeGoal,receiptAssessment,validatePayload,hashText} from './app.js';
let checks=0;
const outcome=(stdout='',exit_code=0,kind='exit')=>JSON.stringify({schema:'target-outcome/1',kind,exit_code,exception:kind==='exception'?{type:'ValueError',message:'fixture',frames:[]}:null,stdout,stderr:''});
const selector=(pointer=null,value=null)=>({kind:'successful-exit',stdout_pointer:pointer,stdout_expected:value});
for(const [text,goal,expected]of[
 [outcome(),selector(),true], [outcome('',2),selector(),false], [outcome('',0,'exception'),selector(),null],
 [outcome('{"param":-3000000000000.0}\n'),selector('/param',['float','-0x1.5d3ef79800000p+41']),true],
 [outcome('{"param":-3000000000000}\n'),selector('/param',['float','-0x1.5d3ef79800000p+41']),false],
 [outcome('{"n":1.0}'),selector('/n',['int','1']),false], [outcome('{"n":1}'),selector('/n',['int','1']),true],
 [outcome('{"n":9007199254740993}'),selector('/n',['int','9007199254740993']),true],
 [outcome('{"n":9007199254740992}'),selector('/n',['int','9007199254740993']),false],
 [outcome('{"n":-0.0}'),selector('/n',['float','-0x0.0p+0']),true],
 [outcome('{"n":0.0}'),selector('/n',['float','-0x0.0p+0']),true],
 [outcome('{"a/b":{"~x":[true,null,"3"]}}'),selector('/a~1b/~0x',['list',[['bool',true],['none'],['str','3']]]),true],
 [outcome('NaN'),selector('',['float','0x0.0p+0']),false],
 [outcome(''),selector('/missing',['int','1']),false],
 [outcome('{"n":"1"}'),selector('/n',['int','1']),false],
 [outcome('{}'),selector('/x~2',['none']),false],
 [outcome('{"typed":1,"keep":29}'),selector('',['dict',[[['str','typed'],['int','1']],[['str','typed'],['int','1']]]]),false],
 [outcome('{"n":1.0}'),selector('/n',['float','0x1.00p+0']),null],
]){assert.equal(outcomeGoal(text,goal),expected);checks++;}
// Use a valid legacy record shell solely to test consumer contract/gating.
const p=JSON.parse(fs.readFileSync(new URL('./demo.json',import.meta.url)));
const e=p.experiments.find(e=>e.selector.kind!=='successful-exit');e.selector=selector();e.artifacts={before:{text:outcome('',2),media_type:'application/json',sha256:null},after:{text:outcome(),media_type:'application/json',sha256:null}};
for(const a of Object.values(e.artifacts))a.sha256=await hashText(a.text);
e.changes=[{path:'Requested successful outcome',before:false,after:true,selected:true}];
validatePayload(p);assert(receiptAssessment(e,{before:'match',after:'match'}).accepted);checks++;
const originalAfter=e.artifacts.after.text;for(const mutation of [o=>o.exception={type:'ValueError',message:'bad',frames:[]},o=>delete o.stderr,o=>o.schema='wrong',o=>o.exit_code=999]){const bad=JSON.parse(originalAfter);mutation(bad);e.artifacts.after.text=JSON.stringify(bad);e.artifacts.after.sha256=await hashText(e.artifacts.after.text);assert.equal(receiptAssessment(e,{before:'match',after:'match'}).accepted,false);assert.equal(receiptAssessment(e,{before:'match',after:'match'}).downloadAfter,false);checks+=2;}e.artifacts.after.text=outcome('',3);e.artifacts.after.sha256=await hashText(e.artifacts.after.text);
assert.equal(receiptAssessment(e,{before:'match',after:'match'}).accepted,false);assert.equal(receiptAssessment(e,{before:'match',after:'match'}).downloadAfter,false);checks+=2;
const genuine=JSON.parse(fs.readFileSync(new URL('./demo.json',import.meta.url))).experiments.find(e=>e.selector.kind==='successful-exit');
const nativeParse=JSON.parse;JSON.parse=(text,reviver)=>nativeParse(text,reviver?((key,value)=>reviver(key,value)):undefined);
try{const unavailable=receiptAssessment(genuine,{before:'match',after:'match'});assert.equal(unavailable.accepted,false);assert.equal(unavailable.contradictory,false);assert.equal(unavailable.downloadAfter,false);checks+=3;}finally{JSON.parse=nativeParse;}
if(process.argv[2]){const real=JSON.parse(fs.readFileSync(process.argv[2]));validatePayload(real);for(const r of real.experiments.filter(x=>x.selector.kind==='successful-exit')){for(const side of ['before','after'])assert.equal(await hashText(r.artifacts[side].text),r.artifacts[side].sha256);assert.equal(receiptAssessment(r,{before:'match',after:'match'}).accepted,true);checks+=3;}}
console.log(`${checks} failure viewer controls passed, including exact integer/float distinction, negative zero, unsafe integer tokens and actual exit-goal gating.`);
