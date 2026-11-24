import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {build} from 'esbuild';
const output=await build({entryPoints:['animation/StoryEngine.tsx'],bundle:true,write:false,platform:'node',format:'esm',jsxFactory:'jsx',jsxFragment:'Fragment'});
const engine=await import('data:text/javascript;base64,'+Buffer.from(output.outputFiles[0].text).toString('base64'));
const stories=JSON.parse(fs.readFileSync('fixtures/story-v3/normalized.json','utf8'));
function expand(v){
 if(v==null||v===false||v===true)return '';
 if(Array.isArray(v))return v.map(expand).join('');
 if(typeof v!=='object')return String(v);
 if(typeof v.type==='function')return expand(v.type(v.props));
 const props=Object.entries(v.props||{}).filter(([k])=>k!=='children').map(([k,x])=>k+'='+String(x)).join(' ');
 return '<'+v.type+' '+props+'>'+expand(v.props?.children)+'</'+v.type+'>';
}
test('all three stories draw real SVG elements at multiple times in every ratio',()=>{
 for(const story of Object.values(stories))for(const [w,h] of [[1920,1080],[1080,1920],[1080,1080],[1080,1350]]) {
  const frames=[0,2,4,story.duration*.58,story.duration-.01].map(t=>expand(engine.storyFrame(story,t,w,h)));
  for(const svg of frames){assert.ok(svg.includes('data-character-id'));assert.ok(svg.includes('path'));assert.ok(!svg.includes('NaN'));assert.ok(!svg.includes('undefined'));}
  assert.ok(new Set(frames).size>2);
 }
});
test('walking translates, pickup attaches, and open/close changes door state',()=>{
 const story=stories.library,scene=story.scenes[1],actor=scene.actors.find(a=>a.character_id==='arun');
 const start=engine.actorState(scene,actor,0),end=engine.actorState(scene,actor,2.4);
 assert.ok(end.x>start.x);
 const door=scene.props.find(p=>p.id==='door');
 assert.ok(engine.propState(scene,door,4.3).open>.8);
 assert.ok(engine.propState(scene,door,7.3).open<.1);
 const s=story.scenes[0],book=s.props.find(p=>p.id==='book');
 assert.equal(engine.propState(s,book,4).held,'mira');
});
test('seeking backwards is deterministic and mouth can remain closed during narration',()=>{
 const story=stories.jannat;
 const first=expand(engine.storyFrame(story,3,1920,1080));
 expand(engine.storyFrame(story,26,1920,1080));
 assert.equal(expand(engine.storyFrame(story,3,1920,1080)),first);
});
test('a box lid opens before the item is visible and the pickup attaches it',()=>{
 const story=structuredClone(stories.library),scene=story.scenes[0];
 const book=scene.props.find(p=>p.id==='book'),box={...book,id:'box',type:'box',state:'closed'};
 scene.props.push(box);
 book.reveal_from_id='box';
 scene.actions.push({type:'open_box',character_id:'mira',target_id:'box',start:0,end:1.4});
 const closed=expand(engine.storyFrame(story,.1,1080,1920));
 const revealed=expand(engine.storyFrame(story,1.5,1080,1920));
 assert.match(closed,/data-box-lid=box/);
 assert.doesNotMatch(closed,/data-prop-id=book/);
 assert.match(revealed,/data-prop-id=book/);
 assert.equal(engine.propState(scene,box,1.5).open,1);
 assert.equal(engine.propState(scene,book,4).held,'mira');
});
test('a held book opens to show its pages',()=>{
 const story=structuredClone(stories.library),scene=story.scenes[0];
 scene.actions.push({type:'open_book',character_id:'mira',target_id:'book',start:4,end:5});
 assert.match(expand(engine.storyFrame(story,3.9,1080,1920)),/data-book-open=0/);
 assert.match(expand(engine.storyFrame(story,4.5,1080,1920)),/data-book-open=0.5/);
 assert.match(expand(engine.storyFrame(story,5.1,1080,1920)),/data-book-open=1/);
});
