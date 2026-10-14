// Actual inline export controller with minimal DOM; no browser/layout claim.
import assert from 'node:assert/strict';
import fs from 'node:fs';
const html=fs.readFileSync(process.argv[2], 'utf8');
const data=html.match(/<script id="embedded-record" type="application\/json">([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script type="module">([\s\S]*?)<\/script>/)[1];
class Node {
 constructor(){this.children=[];this.dataset={};this.disabled=false;this.hidden=false;this.value='';this._text='';this.classList={add(){},remove(){},toggle(){}};}
 get textContent(){return this._text;} set textContent(value){this._text=String(value??'');this.children=[];}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;this._text='';}
 setAttribute(){}
}
const ids=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(x=>[x[1],new Node()]));
ids.get('embedded-record').textContent=data;
globalThis.document={getElementById:id=>ids.get(id)??null,createElement:()=>new Node(),body:new Node()};
let fetchCalls=0;
globalThis.fetch=()=>{fetchCalls++;throw Error('Portable export must not fetch.');};
await import('data:text/javascript;base64,'+Buffer.from(script).toString('base64'));
for(let i=0;i<100&&!ids.get('load-status').textContent.startsWith('Evidence loaded.');i++)await new Promise(r=>setTimeout(r,2));
assert.equal(fetchCalls,0);
assert.equal(ids.get('workspace').hidden,false);
assert.equal(ids.get('case-title').textContent,JSON.parse(data).experiments[0].title);
assert.match(ids.get('load-status').textContent,/^Evidence loaded\./);
assert.match(ids.get('integrity-note').textContent,/original match; alternate match/);
console.log(JSON.stringify({passed:true,fetch_calls:fetchCalls,actual_inline_controller:true,dom:'minimal test double; not browser/layout verification'}));
