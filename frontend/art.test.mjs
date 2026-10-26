/**
 * frontend/art.test.mjs — ชุดทดสอบระบบจัดการภาพประกอบฉาก (GameArt Unit Tests)
 * 
 * ทดสอบ: การสลับภาพฉากตู้รถ, ภาพซูมวัตถุพยาน (Close-up), ภาพฉากจบ, และการแสดงผลสถานะ fallback
 */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('./art.js',import.meta.url),'utf8');
function setup(){
  const nodes=Object.fromEntries(['sceneImage','sceneLabel','sceneStatus','artStatus'].map(id=>[id,{}]));
  const context=vm.createContext({document:{getElementById:id=>nodes[id],createElement:()=>({})}});
  vm.runInContext(source,context);
  return {art:vm.runInContext('GameArt',context),nodes};
}
test('room, close-up and medical scene follow approved commands',()=>{
  const {art,nodes}=setup();const state={current_location:'first_class_car'};
  art.onResult({new_state:state,parsed:{action:'move',target:'first_class_car'},decision:{allowed:true}});art.sync(state);
  assert.match(nodes.sceneImage.src,/scene-04-crime.png$/);
  art.onResult({new_state:state,parsed:{action:'examine',target:'pocket_watch'},decision:{allowed:true}});art.sync(state);
  assert.match(nodes.sceneImage.src,/detail-pocket-watch.png$/);
  art.onResult({new_state:state,parsed:{action:'examine',target:'secret_file'},decision:{allowed:false}});art.sync(state);
  assert.match(nodes.sceneImage.src,/detail-pocket-watch.png$/);
  art.onResult({new_state:state,parsed:{action:'interrogate',target:'dr_liora_venn'},decision:{allowed:true}});art.sync(state);
  assert.match(nodes.sceneImage.src,/scene-04-medical.png$/);
  art.sync({current_location:'lounge_car'});assert.match(nodes.sceneImage.src,/scene-05-lounge.png$/);
});
test('entering, examining and reloading the victim room show the same location',()=>{
  const state={current_location:'first_class_car'};
  const {art,nodes}=setup();
  art.onResult({new_state:state,parsed:{action:'move',target:'first_class_car'},decision:{allowed:true}});art.sync(state);
  const entered=nodes.sceneImage.src;
  art.onResult({new_state:state,parsed:{action:'examine',target:'pocket_watch'},decision:{allowed:true}});art.sync(state);
  art.onResult({new_state:state,parsed:{action:'examine',target:'first_class_car'},decision:{allowed:true}});art.sync(state);
  assert.equal(nodes.sceneImage.src,entered);
  const reloaded=setup();reloaded.art.sync(state);
  assert.equal(reloaded.nodes.sceneImage.src,entered);
});
test('evidence images are valid or intentionally omitted; every ending has an image',()=>{
  const story=JSON.parse(readFileSync(new URL('../data/story.json',import.meta.url),'utf8'));
  const {art,nodes}=setup();
  const noDedicatedImage=new Set(['tunnel_schedule']);
  for(const id of Object.keys(story.objects)){
    const img=art.journalImage(id,id);
    if(noDedicatedImage.has(id)){assert.equal(img,null,id);continue;}
    assert.ok(img,id);
    assert.ok(existsSync(new URL('../assets/nocturne-stylized-v2/'+img.src.split('/').pop(),import.meta.url)),id);
  }
  const expected={true_ending:'true',cold_justice:'incomplete',the_scapegoat:'scapegoat',the_paranoia_trap:'paranoia',unproven:'unproven',cold_arrival:'arrival'};
  for(const id of Object.keys(story.endings)){
    art.sync({current_location:'lounge_car',ending_id:id});
    assert.equal(nodes.sceneImage.src,`/game-art/ending-${expected[id]}.png`);
    assert.ok(existsSync(new URL('../assets/nocturne-stylized-v2/'+nodes.sceneImage.src.split('/').pop(),import.meta.url)));
  }
});
test('restricted entrance preserves location; missing image has readable fallback',()=>{
  const {art,nodes}=setup();const state={current_location:'lounge_car'};art.sync(state);
  art.onResult({new_state:state,parsed:{action:'move',target:'locomotive'},decision:{allowed:false}});art.sync(state);
  assert.match(nodes.sceneImage.src,/scene-01-locomotive.png$/);
  assert.equal(state.current_location,'lounge_car');
  nodes.sceneImage.onerror();assert.equal(nodes.artStatus.hidden,false);
  assert.match(nodes.artStatus.textContent,/ยังอ่านข้อมูล/);
  nodes.sceneImage.onload();assert.equal(nodes.artStatus.hidden,true);
});
