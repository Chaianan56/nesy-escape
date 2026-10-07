/* Game HUD and read-only journal. Scene artwork is managed by GameArt. */
const PixelUI = (() => {
  const $ = id => document.getElementById(id);
  const rooms = [
    ['locomotive','หัวรถจักร','ENGINE ROOM'],['luggage_van_electrical','ระบบไฟฟ้า','THE ELECTRICAL CAR'],
    ['dining_car_staff','ตู้เสบียง','THE DINING CAR'],['first_class_car','ชั้นหนึ่ง','THE FIRST CLASS CAR'],
    ['lounge_car','เลานจ์','THE LOUNGE CAR'],['second_class_car','ชั้นสอง','THE SECOND CLASS CAR'],
  ];
  let data = null, activeTab = 'evidence', revision = 0;
  function button(label, command, className='object-button') {
    const b = document.createElement('button'); b.type='button'; b.className=className;
    b.textContent=label; b.onclick=()=>fillInput(command); return b;
  }
  function empty(title, text) {
    const box=document.createElement('div'); box.className='empty-state';
    const icon=document.createElement('div');icon.className='empty-icon';icon.textContent='◇';
    const heading=document.createElement('strong');heading.textContent=title;
    const p=document.createElement('p');p.textContent=text;box.append(icon,heading,p);return box;
  }
  function drawScene(location) {
    GameArt.sync(gameState || {current_location:location});
  }
  function map() {
    const wrap=$('trainCars');wrap.replaceChildren();
    rooms.forEach(([id,label],i)=>{const b=document.createElement('div');b.className='car'+(gameState?.current_location===id?' active':'');b.setAttribute('aria-label',i===0?'หัวรถจักร พื้นที่หวงห้าม':`ตู้${label}`);if(gameState?.current_location===id)b.setAttribute('aria-current','location');b.innerHTML='<div class="car-body"><div class="car-windows"><i></i><i></i><i></i><i></i></div></div>';const name=document.createElement('span');name.textContent=`${String(i+1).padStart(2,'0')} · ${label}`;b.append(name);wrap.append(b)});
  }
  function board() {
    const wrap=$('pillarBoard');wrap.replaceChildren();if(!data)return;
    if(!data.case_closed){wrap.append(empty('ประเมินจากหลักฐาน', 'ใช้เวลา แรงจูงใจ โอกาส และร่องรอยประกอบกัน ข้อสรุปของระบบจะเปิดหลังจบคดี'));return;}
    const status=data.pillars[$('suspectSelect').value]||{};
    Object.entries(data.pillar_labels).forEach(([id,label])=>{const yes=(status[id]||[]).length>0;const row=document.createElement('div');row.className='pillar-row';const line=document.createElement('div');const l=document.createElement('span');l.textContent=label;const r=document.createElement('span');r.textContent=yes?'มีข้อสรุป':'ยังไม่ครบ';line.append(l,r);const p=document.createElement('progress');p.max=1;p.value=yes?1:0;p.setAttribute('aria-label',label);row.append(line,p);wrap.append(row)});
  }
  function journal() {
    const wrap=$('journalContent');wrap.replaceChildren();if(!data){wrap.append(empty('กำลังเปิดสมุด','รอสักครู่…'));return}
    if(activeTab==='evidence'){
      if(!data.evidence.length)wrap.append(empty('ยังไม่พบหลักฐาน','ตรวจสิ่งของในฉาก แล้วหลักฐานที่พบจะถูกบันทึกไว้ที่นี่'));
      data.evidence.forEach((e,i)=>{const box=document.createElement('details');box.className='evidence-card';const title=document.createElement('summary');const icon=document.createElement('span');icon.className='clue-icon';icon.textContent=String(i+1).padStart(2,'0');title.append(icon,document.createTextNode(e.name));const p=document.createElement('p');p.textContent=e.description;const source=document.createElement('small');source.className='evidence-source';source.textContent=`${e.kind==='testimony'?'คำให้การ / บันทึกการสนทนา':'หลักฐานที่ตรวจพบ'} · ${e.source || ''} — ${e.source_note || ''}`;box.append(title,source,p);box.addEventListener('toggle',()=>{if(box.open&&!box.querySelector('img')){const image=GameArt.journalImage(e.id,e.name);if(image)box.append(image);}});wrap.append(box)});
    }else if(activeTab==='questions'){
      const intro=document.createElement('p');intro.textContent='ประเด็นจากข้อมูลที่พบแล้ว ให้คุณตรวจสอบและเชื่อมโยงเอง ไม่ใช่คำใบ้หรือข้อสรุปของระบบ';wrap.append(intro);
      if(!data.questions?.length)wrap.append(empty('ยังไม่มีประเด็นจากการสนทนา','สอบปากคำบุคคล แล้วกลับมาทบทวนข้อมูลที่ได้'));
      (data.questions||[]).forEach(q=>{const box=document.createElement('div');box.className='case-question';const title=document.createElement('strong');title.textContent=q.question;const source=document.createElement('p');source.textContent=`จาก: ${q.source}`;const status=document.createElement('small');status.textContent=q.status;box.append(title,source,status);wrap.append(box)});
    }else if(activeTab==='people'){
      data.people.forEach(p=>{const box=document.createElement('div');box.className='person-card';const name=document.createElement('strong');name.textContent=p.name;const status=document.createElement('small');status.textContent=(p.here?'อยู่ในตู้เดียวกัน · ':'')+(p.interrogated?'สอบปากคำแล้ว':'ยังไม่ได้สอบปากคำ');box.append(name,status);wrap.append(box)});
    }else{
      if(data.submitted_evidence){const summary=document.createElement('p');summary.textContent=`ข้อสรุปจากหลักฐานที่ยื่น ${data.submitted_evidence.length} รายการ (หลักฐานที่พบทั้งหมดอยู่ในแท็บหลักฐาน)`;wrap.append(summary);}
      (data.background||[]).forEach(entry=>{const box=document.createElement('details');box.className='evidence-card';const title=document.createElement('summary');title.textContent=entry.title;const p=document.createElement('p');p.textContent=entry.text;box.append(title,p);wrap.append(box)});
      if(!data.case_closed){
        wrap.append(empty('บันทึกคดี', 'ข้อมูลอดีตจะเพิ่มเมื่ออ่านเอกสาร ส่วนข้อสรุปให้คุณเชื่อมโยงเองระหว่างสืบสวน'));
        const help=document.createElement('p');help.textContent='หากต้องการคำใบ้ ให้พิมพ์ ขอคำใบ้';wrap.append(help);
      }
      if(data.case_closed&&!data.deductions.length)wrap.append(empty('ไม่มีข้อสรุปที่พิสูจน์ได้','หลักฐานที่รวบรวมมายังไม่ครบพอ'));
      data.deductions.forEach(d=>{const note=document.createElement('div');note.className='note';note.textContent=d.name;wrap.append(note)});
    }
  }
  async function refresh() {
    if(!gameState)return;drawScene(gameState.current_location);map();const request=++revision;
    try{const res=await fetch(`${API_BASE}/journal`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({}),signal:AbortSignal.timeout(8000)});if(!res.ok)throw Error();const next=await res.json();if(request!==revision)return;data=next;
      for(const item of [...data.evidence,...data.visible]) objectsMap[item.id]=item.name;
      $('evidenceCount').textContent=data.evidence.length;$('deductionCount').textContent=data.case_closed?data.deductions.length:'—';
      const select=$('suspectSelect');if(!select.options.length)data.people.forEach(p=>{const opt=document.createElement('option');opt.value=p.id;opt.textContent=p.name.split(' (')[0];select.append(opt)});
      const visible=$('visibleObjects');visible.replaceChildren();data.visible.forEach(o=>{const label=document.createElement('span');label.className='object-button';label.textContent=o.name;visible.append(label)});if(!data.visible.length)visible.textContent=gameOver?'คดีปิดแล้ว':'ไม่มีสิ่งที่ตรวจเพิ่มได้ในตู้นี้';
      $('journalStatus').textContent=gameOver?'ปิดแฟ้มคดีแล้ว':'บันทึกจากหลักฐานที่ค้นพบจริง';board();journal();
    }catch{if(request===revision){$('journalStatus').textContent='โหลดสมุดไม่สำเร็จ · ลองใหม่';$('journalStatus').onclick=refresh;}}
  }
  function init(){
    drawScene('lounge_car');map();journal();$('suspectSelect').onchange=board;
    document.querySelectorAll('[data-tab]').forEach((b,i,all)=>{b.onclick=()=>{activeTab=b.dataset.tab;all.forEach(x=>x.setAttribute('aria-selected',String(x===b)));$('journalContent').setAttribute('aria-labelledby',b.id);journal()};b.onkeydown=e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();const next=all[(i+(e.key==='ArrowRight'?1:all.length-1))%all.length];next.click();next.focus()}}});

  }
  document.addEventListener('DOMContentLoaded',init);
  return {refresh};
})();
