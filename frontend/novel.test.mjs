/**
 * frontend/novel.test.mjs — ชุดทดสอบระบบอินเทอร์เฟซแบบนิยายภาพ (Visual Novel UI Unit Tests)
 * 
 * ทดสอบ: การกดปุ่ม Enter เพื่อเปิดบทสนทนาหน้าถัดไป, ป้ายชื่อผู้พูด, 
 * การตัดบทสนทนาเมื่อคำสั่งถูกปฏิเสธ (denied commands), และการทำงานร่วมกับฟอร์มคำสั่ง
 */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
function setup(){
  const nodes=new Map();let handler;
  const context=vm.createContext({busy:false,suspectsMap:{gideon_hart:'กิเดียน ฮาร์ต (Gideon Hart)'},setBusy(){},
    document:{getElementById(id){if(!nodes.has(id))nodes.set(id,{hidden:true,scrollIntoView(){}});return nodes.get(id);},
      addEventListener(event,callback){handler=callback;},querySelector(){return null;}}});
  vm.runInContext(readFileSync(new URL('./novel.js',import.meta.url),'utf8'),context);
  return {ui:vm.runInContext('NovelUI',context),nodes,key(event){handler(event);}};
}
test('Enter advances one page and cannot submit; narration has its own label',()=>{
  const {ui,nodes,key}=setup();ui.onResult({decision:{allowed:true,message:'เขาวางแก้ว\n\n“ผมอยู่ที่นี่”'},parsed:{action:'interrogate',target:'gideon_hart'}});
  assert.equal(nodes.get('dialogueSpeaker').textContent,'คำบรรยาย');
  let blocked=0;key({key:'Enter',preventDefault(){blocked++;},stopImmediatePropagation(){blocked++;}});
  assert.equal(blocked,2);assert.equal(nodes.get('dialogueSpeaker').textContent,'กิเดียน ฮาร์ต');
  ui.next();assert.equal(ui.active(),false);assert.equal(nodes.get('sceneDialogue').hidden,true);
});
test('intro waits for Enter and denied commands do not create dialogue',async()=>{
  const {ui}=setup();const intro=ui.intro('คดี');assert.equal(ui.active(),true);ui.next();await intro;
  assert.equal(ui.active(),false);ui.onResult({decision:{allowed:false,message:'no'},parsed:{action:'interrogate'}});
  assert.equal(ui.active(),false);
});
test('Enter with a typed command is left for the form to send',()=>{
  const {ui,nodes,key}=setup();ui.onResult({decision:{allowed:true,message:'a\n\nb'},parsed:{action:'interrogate',target:'gideon_hart'}});
  nodes.set('chatInput',{value:'ไปตู้ 4'});
  let blocked=0;key({key:'Enter',preventDefault(){blocked++;},stopImmediatePropagation(){blocked++;}});
  assert.equal(blocked,0);assert.equal(ui.active(),true);
});
