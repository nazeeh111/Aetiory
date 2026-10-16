// Actual browser-controller handlers with a minimal DOM. No layout or browser claim.
import assert from 'node:assert/strict';
import fs from 'node:fs';
const completePayload=JSON.parse(fs.readFileSync(new URL('./demo.json',import.meta.url),'utf8'));
const payload={...completePayload,experiments:completePayload.experiments.filter(e=>e.selector.kind!=='successful-exit')};
const html=fs.readFileSync(new URL('./index.html',import.meta.url),'utf8');
const created=[],downloads=[];
class Node {
 constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.disabled=false;this.hidden=false;this.value='';this.files=[];this._text='';this.classes=new Set();this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),toggle:(x,on)=>on?this.classes.add(x):this.classes.delete(x)};}
 get textContent(){return this._text;} set textContent(v){this._text=String(v??'');this.children=[];}
 get className(){return [...this.classes].join(' ');} set className(v){this.classes=new Set(v.split(/\s+/));}
 append(...nodes){this.children.push(...nodes);for(const n of nodes)n.parent=this;}
 replaceChildren(...nodes){this.children=[];this._text='';this.append(...nodes);}
 setAttribute(k,v){this.attributes[k]=String(v);} getAttribute(k){return this.attributes[k];}
 click(){if(this.disabled)return;if(this.tag==='a')downloads.push({name:this.download,href:this.href});return this.onclick?.({target:this});}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);}
}
const ids=new Map();for(const match of html.matchAll(/<([a-z-]+)[^>]*\bid="([^"]+)"[^>]*>/g)){const node=new Node(match[1]);node.id=match[2];node.disabled=/\bdisabled\b/.test(match[0]);node.hidden=/\bhidden\b/.test(match[0]);ids.set(node.id,node);}
const nativeCrypto=globalThis.crypto;
let delayed=false;const pending=[];
Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{digest:(...args)=>delayed?new Promise((resolve,reject)=>pending.push(()=>nativeCrypto.subtle.digest(...args).then(resolve,reject))):nativeCrypto.subtle.digest(...args)}}});
globalThis.document={getElementById:id=>ids.get(id)??null,createElement:tag=>{const node=new Node(tag);created.push(node);return node;},body:new Node('body')};
globalThis.fetch=async()=>({ok:true,headers:{get:()=>null},text:async()=>JSON.stringify(payload)});
const $=id=>ids.get(id),tick=()=>new Promise(resolve=>setImmediate(resolve));
async function settle(){for(let i=0;i<4;i++){await tick();await new Promise(resolve=>setTimeout(resolve,2));}}
async function waitFor(predicate){for(let i=0;i<100&&!predicate();i++)await new Promise(resolve=>setTimeout(resolve,2));assert(predicate(),'Expected asynchronous controller condition');}
const viewer=await import('./app.js?controller-tests');await settle();
assert.equal($('workspace').hidden,false);assert.equal($('download-before').disabled,false);assert.equal($('download-after').disabled,false);assert.equal($('case-title').textContent,payload.experiments[0].title);let checks=4;
async function importRecord(p){const file={size:JSON.stringify(p).length,text:async()=>JSON.stringify(p)};await $('import-file').onchange({target:{files:[file],value:'x'}});await settle();}
for(const status of ['refused','partial','no_effect']){const p=structuredClone(payload);p.experiments[0].status=status;await importRecord(p);assert.equal($('download-after').disabled,status!=='no_effect');assert(!/recorded effect has/.test($('receipt-heading').textContent));assert.match($('mode-label').textContent,/IMPORTED/);checks+=3;}
const fail=structuredClone(payload);fail.experiments[0].guards.parent_matches_original=false;await importRecord(fail);assert.match($('receipt-heading').textContent,/contradicts/);assert.equal($('status-label').textContent,'CONTRADICTORY RECORD');checks+=2;
const missing=structuredClone(payload);missing.experiments[0].status='partial';missing.experiments[0].source=null;missing.experiments[0].event=null;missing.experiments[0].changes=[];missing.experiments[0].artifacts.after=null;await importRecord(missing);assert.match($('return-site').textContent,/not available/);assert.match($('source').textContent,/No source/);assert.match($('selection-context').textContent,/No retained changed field/);checks++;assert.equal($('download-after').disabled,true);checks+=3;
await importRecord(payload);const originalTitle=$('case-title').textContent;const priorCases=$('cases').children.slice();
await $('import-file').onchange({target:{files:[{size:14,text:async()=>'{"bad":'}],value:'x'}});assert.equal($('case-title').textContent,originalTitle);assert.deepEqual($('cases').children,priorCases);assert.match($('load-status').textContent,/Import refused/);checks+=3;
const deep=structuredClone(payload);let v=0;for(let i=0;i<45;i++)v=[v];deep.experiments[0].extra=v;await importRecord(deep);assert.equal($('case-title').textContent,originalTitle);assert.match($('load-status').textContent,/nesting/);checks+=2;
await $('import-file').onchange({target:{files:[{size:8*1024*1024+1,text:async()=>{throw Error('Must not read oversized content');}}],value:'x'}});assert.equal($('case-title').textContent,originalTitle);assert.match($('load-status').textContent,/8 MiB/);checks+=2;
const attack='<img src="https://invalid.example/spy" onerror="alert(1)"><script>globalThis.compromised=true</script>';
const hostile=structuredClone(payload);hostile.experiments[0].source.text=attack;hostile.experiments[0].event.args_preview=attack;hostile.experiments[0].changes.find(c=>c.selected).before=attack;await importRecord(hostile);assert.match($('source').textContent,/<script>/);assert.equal($('before-value').textContent,attack);assert.match($('argument-note').textContent,/<img/);assert(!created.some(x=>['script','img','iframe','object','embed'].includes(x.tag)));assert.equal(globalThis.compromised,undefined);checks+=5;
const corrupted=structuredClone(payload);corrupted.experiments[0].artifacts.after.text+='altered';await importRecord(corrupted);assert.equal($('download-after').disabled,true);assert.match($('integrity-note').textContent,/MISMATCH/);const count=downloads.length;$('download-after').onclick();assert.equal(downloads.length,count);checks+=3;
await importRecord(payload);$('download-before').click();$('download-after').click();assert.equal(downloads.length,count+2);assert.equal(downloads.at(-2).name,payload.experiments[0].id+'-before.html');assert.equal(downloads.at(-1).name,payload.experiments[0].id+'-after.html');checks+=3;
// Hold two actual digest calls across a case switch, then complete them out of order.
delayed=true;$('cases').children[0].click();assert.equal($('download-after').disabled,true);$('cases').children[1].click();assert.equal($('case-title').textContent,payload.experiments[1].title);assert.equal(pending.length,2);checks+=3;
delayed=false;await pending[1]();await waitFor(()=>$('download-after').disabled===false);assert.equal($('case-title').textContent,payload.experiments[1].title);assert.equal($('download-after').disabled,false);const before=$('integrity-note').textContent;await pending[0]();await settle();assert.equal($('case-title').textContent,payload.experiments[1].title);assert.equal($('integrity-note').textContent,before);checks+=4;
// Selection uses the actual retained field; no program invocation is wired to it.
$('cases').children[0].click();await settle();$('changes').children[payload.experiments[0].changes.findIndex(c=>!c.selected)].children[0].children[0].click();assert.equal($('selected-tag').textContent,'Collateral field');assert.equal($('selection-context').textContent,payload.experiments[0].id+' / '+payload.experiments[0].changes.find(c=>!c.selected).path+' / collateral');checks++;assert.match($('effect-note').textContent,/collateral/);checks+=2;
// Actual core snapshot shape has content, while prototype snapshots have children.
function coreShape(v){if(!v||typeof v!=='object')return v;if(Array.isArray(v))return v.map(coreShape);const out={};for(const [k,x]of Object.entries(v))out[k==='children'?'content':k]=coreShape(x);return out;}
const core=structuredClone(payload);for(const c of core.experiments[0].changes){c.before=coreShape(c.before);c.after=coreShape(c.after);}core.experiments[0].selector.sibling=0;await importRecord(core);assert.equal($('selector').textContent,'#from0_72 (element)');assert($('before-value').children.some(x=>x.className.includes('diff_chg')));assert($('after-value').children.some(x=>x.className.includes('diff_sub')));assert($('after-value').children[0].textContent.includes('sig=failure_signature'));assert(!$('before-value').textContent.includes('"content"'));checks+=5;
const snapshotAttack=structuredClone(core);snapshotAttack.experiments[0].changes.find(c=>c.selected).before={tag:'td',attrs:[['onclick','globalThis.compromised=true']],content:[{tag:'span',attrs:[['class','diff_sub'],['onerror','alert(1)'],['src','https://invalid.example/spy']],content:[attack]}]};await importRecord(snapshotAttack);assert.equal($('before-value').children[0].textContent,attack);assert.equal($('before-value').children[0].attributes.onerror,undefined);assert.equal($('before-value').children[0].attributes.src,undefined);assert.equal(globalThis.compromised,undefined);checks+=4;
const failurePayload={...completePayload,experiments:completePayload.experiments.filter(e=>e.selector.kind==='successful-exit')};await importRecord(failurePayload);assert.equal($('outcome-panel').hidden,false);assert.equal($('selection-context').textContent,failurePayload.experiments[0].id+' / '+failurePayload.experiments[0].changes.find(c=>c.selected).path+' / original target');checks++;assert.match($('outcome-before').textContent,/code 2/);assert.match($('outcome-after').textContent,/code 0/);assert.match($('stdout-after').textContent,/-3000000000000/);assert.match($('stderr-before').textContent,/expected one argument/);assert.equal($('download-after').disabled,false);checks+=6;
// An embedded imported record has no file-chooser state; its own mode still labels it unauthenticated.
const embeddedImport=structuredClone(failurePayload);embeddedImport.experiments[0].mode='imported';
globalThis.fetch=async()=>({ok:true,headers:{get:()=>null},text:async()=>JSON.stringify(embeddedImport)});
viewer.boot();await settle();assert.equal($('mode-label').textContent,'IMPORTED · NOT AUTHENTICATED');assert.equal($('status-label').textContent,'UNAUTHENTICATED IMPORT');checks+=2;
console.log(`${checks} actual controller checks passed: status, incomplete receipts, hostile text, exact download gating, malformed-import survival and stale digest exclusion. Minimal DOM only; browser/layout verification remains separate.`);
