const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('templates/keys_batch.html','utf8').split('<script>')[1].split('</script>')[0];
const capcut={kind:'product',title:'Capcut Pro For 1 Year',url:'/capcut'};
const claude={kind:'product',title:'Claude Pro',url:'/claude'};
const finalcut={kind:'product',title:'Final Cut',url:'/final-cut'};
const category={kind:'category',title:'Video Editing',url:'/video'};
function harness(plan={}) {
  const elements=new Map(), storage=new Map([['keys_batch_plan_v1',JSON.stringify(plan)]]), requests=[];
  function element(){return {value:'',innerHTML:'',textContent:'',style:{},disabled:false,children:[],addEventListener(){},querySelector(){return this.status||(this.status=element())},querySelectorAll(){return []},prepend(row){this.children.unshift(row)},insertAdjacentHTML(){}}}
  const document={getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id)},querySelectorAll(){return []},createElement:element};
  const context=vm.createContext({document,localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},setTimeout,clearTimeout,alert(){},confirm(){return true},console,fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,body:JSON.parse(options.body),resolve:(data,ok=true)=>resolve({ok,json:async()=>data}),reject}))});
  // Expose only the selection handler; execute the actual shipped event handlers.
  vm.runInContext(source.replace('  loadPlan();renderDrafts();','  globalThis.choose=selectTarget;loadPlan();renderDrafts();'),context);
  return {el:id=>document.getElementById(id),choose:context.choose,requests,storage};
}
test('selection clears plan and seed, preserves completed drafts, reload stays clean',()=>{
  const h=harness({version:2,target:claude,topics:'Claude topic',seed:'Claude direction'});
  h.storage.set('keys_batch_drafts_v1','[{"article":{"slug":"saved"}}]');
  h.choose(capcut);
  assert.equal(h.el('topics').value,'');assert.equal(h.el('seed').value,'');
  assert.equal(h.el('topic-count').textContent,'0 topics');
  assert.equal(JSON.parse(h.storage.get('keys_batch_plan_v1')).target.title,capcut.title);
  assert.equal(JSON.parse(h.storage.get('keys_batch_drafts_v1')).length,1);
  const reload=harness(JSON.parse(h.storage.get('keys_batch_plan_v1')));
  assert.equal(reload.el('topics').value,'');
});
test('legacy potentially mismatched plans are cleared without deleting drafts',()=>{
  const h=harness({target:capcut,topics:'Claude Pro guide',seed:'Claude'});
  assert.equal(h.el('topics').value,'');assert.equal(h.el('seed').value,'');
});
test('late topic response and old finally cannot overwrite newer selection/request',async()=>{
  const h=harness();h.choose(claude);
  const old=h.el('gen-topics').onclick();h.choose(capcut);
  const current=h.el('gen-topics').onclick();
  h.requests[0].resolve({topics:['Claude Pro guide'],provider:'old'});await old;
  assert.equal(h.el('topics').value,'');assert.equal(h.el('gen-topics').disabled,true);
  h.requests[1].resolve({topics:['CapCut guide'],provider:'new'});await current;
  assert.equal(h.el('topics').value,'CapCut guide');assert.equal(h.el('gen-topics').disabled,false);
});
test('A to B to A selection changes invalidate late errors too',async()=>{
  const h=harness();h.choose(finalcut);const old=h.el('gen-topics').onclick();
  h.choose(category);h.choose(finalcut);h.requests[0].reject(new Error('stale error'));await old;
  assert.equal(h.el('topic-provider').textContent,'');assert.equal(h.el('topics').value,'');
});
test('article batch stops on selection change and saves current draft with original target',async()=>{
  const h=harness();h.choose(finalcut);h.el('topics').value='Final Cut guide\nFinal Cut setup';
  const batch=h.el('gen-articles').onclick();h.choose(capcut);
  h.requests[0].resolve({article:{title:'Final Cut guide',slug:'final-cut'},gate_ok:true});await batch;
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].body.target.title,'Final Cut');
  assert.equal(JSON.parse(h.storage.get('keys_batch_drafts_v1'))[0].target.title,'Final Cut');
  assert.equal(h.el('overall').textContent,'');assert.equal(h.el('gen-articles').disabled,false);
});
