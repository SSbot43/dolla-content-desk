const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.env.BATCH_HTML||'static/batch.html','utf8').split('<script>')[1].split('</script>')[0];
function harness(n){
 const nodes=new Map(),storage=new Map();
 function element(){return {value:'',innerHTML:'',textContent:'',hidden:false,disabled:false,dataset:{},style:{},handlers:{},addEventListener(name,fn){this.handlers[name]=fn},scrollIntoView(){}}}
 const navs=[0,1].map(()=>{const nav=element();nav.prev=element();nav.prev.dataset.topicPage='-1';nav.next=element();nav.next.dataset.topicPage='1';nav.status=element();nav.querySelector=s=>s.includes('status')?nav.status:s.includes('-1')?nav.prev:nav.next;return nav});
 const document={getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)},querySelectorAll(s){return s==='.topic-pagination'?navs:navs.flatMap(x=>[x.prev,x.next])},addEventListener(){}};
 document.getElementById('topics').value=Array.from({length:n},(_,i)=>`Story ${i+1}`).join('\n');document.getElementById('game').value='auto';
 const ctx=vm.createContext({document,window:{addEventListener(){}},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},console,location:{origin:'http://localhost'},alert:msg=>{throw Error(msg)},setTimeout,confirm:()=>true});
 const tail='loadDestinations();migrateOldDrafts();renderDrafts();topicsEl.dispatchEvent(new Event(\'input\'));';
 assert.ok(source.includes(tail));
 vm.runInContext(source.replace(tail,`globalThis.api={renderTopicLinks,topicOverrides,topicFiles,topicAlts};globalThis.generated=[];requestArticle=async r=>{generated.push(r);return {title:r.title,slug:r.title,gateOk:true,brief:{}}};sleep=async()=>{};renderTopicLinks();`),ctx);
 return {ctx,navs,el:id=>document.getElementById(id)};
}
test('40 stories have two pages with global numbering and matching controls',()=>{
 const h=harness(40);assert.match(h.el('topic-links').innerHTML,/20\. Story 20/);assert.doesNotMatch(h.el('topic-links').innerHTML,/21\. Story 21/);
 h.navs[0].next.handlers.click();assert.match(h.el('topic-links').innerHTML,/21\. Story 21/);assert.match(h.el('topic-links').innerHTML,/40\. Story 40/);
 for(const nav of h.navs){assert.match(nav.status.textContent,/Page 2 of 2/);assert.equal(nav.next.disabled,true);assert.equal(nav.prev.disabled,false)}
});
test('link image and alt text remain assigned after navigating away and back',()=>{
 const h=harness(40);h.ctx.api.topicOverrides['Story 21']='crash';h.ctx.api.topicFiles['Story 21']={name:'story.png'};h.ctx.api.topicAlts['Story 21']='A story image';
 h.navs[0].next.handlers.click();h.navs[1].prev.handlers.click();h.navs[0].next.handlers.click();
 assert.match(h.el('topic-links').innerHTML,/Selected: story.png/);assert.match(h.el('topic-links').innerHTML,/A story image/);assert.equal(h.ctx.api.topicOverrides['Story 21'],'crash');
});
test('shortening the list returns to a valid first page',()=>{
 const h=harness(40);h.navs[0].next.handlers.click();h.el('topics').value='Only story';h.el('topics').handlers.input();assert.match(h.el('topic-links').innerHTML,/1\. Only story/);assert.equal(h.navs[0].hidden,true);
});
test('all 100 topics are accessible and partial final pages work',()=>{
 const h=harness(100);for(let i=0;i<4;i++)h.navs[0].next.handlers.click();assert.match(h.el('topic-links').innerHTML,/100\. Story 100/);assert.equal(h.navs[0].next.disabled,true);
 const partial=harness(41);partial.navs[0].next.handlers.click();partial.navs[0].next.handlers.click();assert.match(partial.navs[0].status.textContent,/Topics 41–41 of 41/);
});
test('Generate still uses all 40 topics and settings from the second page',async()=>{
 const h=harness(40);h.ctx.api.topicOverrides['Story 21']='crash';h.ctx.api.topicFiles['Story 21']={name:'story.png'};h.ctx.api.topicAlts['Story 21']='Image alt';
 await h.el('generate').handlers.click();assert.equal(h.ctx.generated.length,40);assert.equal(h.ctx.generated[20].game,'crash');assert.equal(h.ctx.generated[20].file.name,'story.png');assert.equal(h.ctx.generated[20].alt,'Image alt');
});

