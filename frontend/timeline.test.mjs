import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('./pixel.js', import.meta.url), 'utf8');
const renderer = source.slice(source.indexOf('  function renderTimelineTab('), source.indexOf('  // Journal Dispatcher'));
function render(data) {
  const element = () => ({innerHTML:'', children:[], append(child){this.children.push(child);}});
  const wrap = element();
  vm.runInNewContext(renderer + '\nrenderTimelineTab(wrap);', {data, wrap, document:{createElement:element}});
  const html = node => node.innerHTML + node.children.map(html).join('');
  return html(wrap);
}
for (const case_id of ['case_01_gideon','case_02_vincent','case_03_liora']) {
  const people = [{id:'vincent_gray',name:'วินเซนต์',encountered:true,interrogated:true}];
  test(`${case_id}: meeting or unrelated interview does not reveal a confession`, () => {
    const html = render({case_id,people,evidence:[],deductions:[]});
    assert.equal((html.match(/ยังไม่ได้รับคำให้การในสมุดคดี/g)||[]).length,3);
    assert.doesNotMatch(html,/ผมแค่ตัดไฟ|ผมตัดสายไฟ|ผมเข้าไปในห้อง|หมอลิโอราอ้างว่าเฝ้า/);
  });
  test(`${case_id}: displays only collected testimony and escapes its text`, () => {
    const html = render({case_id,people,evidence:[{id:'vincent_body_testimony',kind:'testimony',source:'วินเซนต์',description:'คำให้การที่ได้รับ <script>test</script>'}],deductions:[]});
    assert.match(html,/คำให้การที่ได้รับ &lt;script&gt;test&lt;\/script&gt;/);
    assert.doesNotMatch(html,/ผมแค่ตัดไฟ|ผมตัดสายไฟ|ผมเข้าไปในห้อง/);
    assert.equal((html.match(/ยังไม่ได้รับคำให้การในสมุดคดี/g)||[]).length,2);
  });
}

test('timeline does not infer murder or poison from a watch and tea alone', () => {
  const html = render({case_id:'case_03_liora',people:[],evidence:[
    {id:'pocket_watch',name:'นาฬิกา',description:'กลไกหยุด 20:25'},
    {id:'second_teacup',name:'ถ้วยชา',description:'ยังรอผลตรวจ'}
  ],deductions:[]});
  assert.match(html,/กลไกหยุด 20:25/);
  assert.doesNotMatch(html,/ยาพิษออกฤทธิ์|พ้นข้อหา|หักล้างแล้ว|ข้อสรุปหลังปิดคดี/);
});
test('timeline displays the server conclusion without rewriting it', () => {
  const html = render({people:[],evidence:[],deductions:[{id:'D01',name:'เหตุรุนแรงก่อนดับไฟ แต่ยังรอผลตรวจพิษ'}]});
  assert.match(html,/เหตุรุนแรงก่อนดับไฟ แต่ยังรอผลตรวจพิษ/);
});
