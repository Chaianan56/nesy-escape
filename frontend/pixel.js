/* Code-drawn placeholder art. Replace drawScene with authored assets later. */
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
    const canvas=$('sceneCanvas'), c=canvas.getContext('2d'); c.imageSmoothingEnabled=false;
    const rect=(x,y,w,h,color)=>{c.fillStyle=color;c.fillRect(x,y,w,h)};
    const line=(x,y,x2,y2,color)=>{c.strokeStyle=color;c.lineWidth=1;c.beginPath();c.moveTo(x,y);c.lineTo(x2,y2);c.stroke()};
    const electrical=location==='luggage_van_electrical', first=location==='first_class_car', second=location==='second_class_car', dining=location==='dining_car_staff';
    rect(0,0,640,300,'#111b19');rect(0,32,640,204,electrical?'#29382e':'#3c3a28');
    // Paneled walls, night windows, distant trees and rain.
    for(let x=0;x<640;x+=32){rect(x,33,3,200,'#252a1e');rect(x+3,34,1,195,'#686044')}
    for(let x=25;x<550;x+=175){
      rect(x-5,51,129,123,'#171f19');rect(x-2,54,123,117,'#8b7950');rect(x+2,58,115,109,'#121f24');
      rect(x+8,63,103,98,'#263a3c');
      for(let j=0;j<10;j++){let xx=x+8+j*10;rect(xx,112+(j%3)*7,7,49-(j%3)*7,'#172b2c');rect(xx+2,96+(j%3)*7,3,25,'#172b2c')}
      for(let j=0;j<19;j++)line(x+10+(j*17)%96,65+(j*13)%70,x+7+(j*17)%96,74+(j*13)%70,'#456060');
      rect(x+55,60,4,104,'#776b4a');rect(x+4,115,112,3,'#746649');rect(x-7,174,135,5,'#a08b55');
    }
    rect(0,199,640,39,'#272d20');rect(0,199,640,4,'#83714b');rect(0,236,640,64,'#3b3726');
    for(let y=242;y<300;y+=10)rect(0,y,640,2,'#21281e');for(let x=-160;x<800;x+=52)line(320+(x-320)*.5,238,x,300,'#605239');
    // Ceiling beams and brass lamps.
    rect(0,0,640,31,'#1d251d');for(let x=0;x<640;x+=80){rect(x,0,8,33,'#655337');rect(x,29,80,3,'#9b8250')}
    for(let x of [130,465]){rect(x,5,3,34,'#aa8a4e');rect(x-9,38,22,6,'#d2b773');rect(x-13,44,30,9,'#e4cf91');rect(x-6,53,16,5,'#b39656');rect(x-1,58,5,3,'#6d633b');c.fillStyle='#dec78c0b';c.beginPath();c.moveTo(x-10,54);c.lineTo(x-65,208);c.lineTo(x+65,208);c.lineTo(x+20,54);c.fill()}
    function seat(x,y,color){rect(x,y,115,38,color);rect(x+4,y+4,107,3,'#72806a');rect(x-6,y+25,127,12,'#172c26');rect(x,y+38,115,18,color);rect(x+7,y+56,6,15,'#191e16');rect(x+102,y+56,6,15,'#191e16');for(let i=10;i<110;i+=18)rect(x+i,y+8,2,17,'#283e32')}
    if(electrical){rect(52,88,149,133,'#465448');rect(58,94,137,120,'#202d27');for(let i=0;i<4;i++){rect(69+i*29,107,18,25,'#a29668');rect(76+i*29,112,3,13,'#182820');rect(70+i*29,151,13,7,'#7d8a6b');rect(75+i*29,158,3,29,'#ae7c42')}rect(90,260,35,3,'#b07f45');rect(128,263,25,3,'#b07f45')}
    else if(dining){for(let x of [55,280]){seat(x,189,'#52604b');rect(x+10,224,132,11,'#a48c55');rect(x+65,235,9,38,'#55462f');rect(x+44,212,19,4,'#d2ccb0');rect(x+47,204,11,8,'#b8bca4')}}
    else if(first){rect(30,205,220,15,'#978154');rect(36,220,208,35,'#59604d');rect(40,208,48,12,'#d4c9a4');rect(190,190,49,20,'#5b372a');rect(210,195,10,3,'#c0a366')}
    else{seat(29,193,second?'#65533a':'#405442');seat(211,193,second?'#65533a':'#405442');rect(150,238,72,8,'#ab8b50');rect(181,246,7,34,'#594c32');rect(164,231,11,7,'#d9d0a4')}
    // Figure: intentional chunky sprite with a silhouette and limited palette.
    if(!electrical&&!dining){const x=first?477:second?470:492;const coat=first?'#8b8c6d':second?'#5f5140':'#303e34';
      rect(x+6,269,66,6,'#182019');rect(x+16,239,15,34,'#202b26');rect(x+42,239,15,34,'#202b26');rect(x+11,270,21,5,'#0e1917');rect(x+43,270,22,5,'#0e1917');
      rect(x+10,167,52,80,coat);rect(x,179,12,56,coat);rect(x+62,179,12,56,coat);rect(x+2,231,8,13,'#b69b73');rect(x+64,232,8,12,'#b69b73');
      rect(x+23,165,25,16,'#ba9d72');rect(x+25,181,20,39,'#b2ab87');rect(x+32,183,7,36,'#6c5435');rect(x+10,168,14,60,coat);rect(x+46,168,16,60,coat);
      rect(x+18,122,40,37,'#bd9f75');rect(x+24,159,25,9,'#a58360');rect(x+16,114,43,14,'#302d21');rect(x+15,125,9,19,'#3c3525');rect(x+55,126,5,19,'#3c3525');rect(x+26,138,5,3,'#282b23');rect(x+47,138,5,3,'#282b23');rect(x+37,140,3,9,'#94704f');rect(x+33,154,12,2,'#7c634a');
      if(first){rect(x+55,131,9,28,'#3e382b');rect(x+59,159,8,8,'#3e382b')}if(second)rect(x+1,213,9,15,'#743e31');
      rect(x+21,189,2,38,'#9e8e61');rect(x+47,202,8,2,'#a28e59');
    }
    // Lamps on tables and luggage.
    rect(573,192,48,43,'#393b29');rect(571,190,52,6,'#847049');rect(583,184,20,5,'#a38b53');rect(592,210,5,8,'#b39859');
    c.fillStyle='#09130e28';for(let y=0;y<300;y+=3)c.fillRect(0,y,640,1);
    const room=rooms.find(r=>r[0]===location);$('sceneLabel').textContent=room?.[2]||'NOCTURNE EXPRESS';canvas.setAttribute('aria-label',`ฉากพิกเซล ${room?.[1]||'รถไฟ'} ภาพชั่วคราว`);
  }
  function map() {
    const wrap=$('trainCars');wrap.replaceChildren();
    rooms.forEach(([id,label],i)=>{const b=document.createElement('button');b.className='car'+(gameState?.current_location===id?' active':'');b.type='button';b.disabled=i===0||gameOver;b.setAttribute('aria-label',i===0?'หัวรถจักร พื้นที่หวงห้าม':`เดินไปตู้${label}`);if(gameState?.current_location===id)b.setAttribute('aria-current','location');b.innerHTML='<div class="car-body"><div class="car-windows"><i></i><i></i><i></i><i></i></div></div>';const name=document.createElement('span');name.textContent=`${String(i+1).padStart(2,'0')} · ${label}`;b.append(name);b.onclick=()=>{fillInput(`ไปที่${locationsMap[id]||label}`);sendMessage({preventDefault(){}})};wrap.append(b)});
  }
  function board() {
    const wrap=$('pillarBoard');wrap.replaceChildren();if(!data)return;
    const status=data.pillars[$('suspectSelect').value]||{};
    Object.entries(data.pillar_labels).forEach(([id,label])=>{const yes=(status[id]||[]).length>0;const row=document.createElement('div');row.className='pillar-row';const line=document.createElement('div');const l=document.createElement('span');l.textContent=label;const r=document.createElement('span');r.textContent=yes?'มีข้อสรุป':'ยังไม่ครบ';line.append(l,r);const p=document.createElement('progress');p.max=1;p.value=yes?1:0;p.setAttribute('aria-label',label);row.append(line,p);wrap.append(row)});
  }
  function journal() {
    const wrap=$('journalContent');wrap.replaceChildren();if(!data){wrap.append(empty('กำลังเปิดสมุด','รอสักครู่…'));return}
    if(activeTab==='evidence'){
      if(!data.evidence.length)wrap.append(empty('ยังไม่พบหลักฐาน','ตรวจสิ่งของในฉาก แล้วหลักฐานที่พบจะถูกบันทึกไว้ที่นี่'));
      data.evidence.forEach((e,i)=>{const box=document.createElement('details');box.className='evidence-card';const title=document.createElement('summary');const icon=document.createElement('span');icon.className='clue-icon';icon.textContent=String(i+1).padStart(2,'0');title.append(icon,document.createTextNode(e.name));const p=document.createElement('p');p.textContent=e.description;box.append(title,p);wrap.append(box)});
    }else if(activeTab==='people'){
      data.people.forEach(p=>{const box=document.createElement('div');box.className='person-card';const name=document.createElement('strong');name.textContent=p.name;const status=document.createElement('small');status.textContent=(p.here?'อยู่ในตู้เดียวกัน · ':'')+(p.interrogated?'สอบปากคำแล้ว':'ยังไม่ได้สอบปากคำ');box.append(name,status);if(p.here)box.append(button('สอบปากคำ',`สอบปากคำ${p.name}`));box.append(button('กล่าวหา',`กล่าวหา${p.name}`));wrap.append(box)});
    }else{
      if(!data.deductions.length)wrap.append(empty('ยังไม่มีข้อสรุป','เมื่อมีหลักฐานครบตามกฎ ข้อสรุปจะปรากฏที่นี่'));
      data.deductions.forEach(d=>{const note=document.createElement('div');note.className='note';note.textContent=d.name;wrap.append(note)});
    }
  }
  async function refresh() {
    if(!gameState)return;drawScene(gameState.current_location);map();const request=++revision;
    try{const res=await fetch(`${API_BASE}/journal`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(gameState),signal:AbortSignal.timeout(8000)});if(!res.ok)throw Error();const next=await res.json();if(request!==revision)return;data=next;
      $('evidenceCount').textContent=data.evidence.length;$('deductionCount').textContent=data.deductions.length;
      const select=$('suspectSelect');if(!select.options.length)data.people.forEach(p=>{const opt=document.createElement('option');opt.value=p.id;opt.textContent=p.name.split(' (')[0];select.append(opt)});
      const visible=$('visibleObjects');visible.replaceChildren();data.visible.forEach(o=>visible.append(button(o.name,`ตรวจ${o.name}`)));if(!data.visible.length)visible.textContent=gameOver?'คดีปิดแล้ว':'ไม่มีสิ่งที่ตรวจเพิ่มได้ในตู้นี้';
      $('journalStatus').textContent=gameOver?'ปิดแฟ้มคดีแล้ว':'บันทึกจากหลักฐานที่ค้นพบจริง';board();journal();
    }catch{if(request===revision){$('journalStatus').textContent='โหลดสมุดไม่สำเร็จ · ลองใหม่';$('journalStatus').onclick=refresh;}}
  }
  function init(){
    drawScene('lounge_car');map();journal();$('suspectSelect').onchange=board;
    document.querySelectorAll('[data-tab]').forEach((b,i,all)=>{b.onclick=()=>{activeTab=b.dataset.tab;all.forEach(x=>x.setAttribute('aria-selected',String(x===b)));$('journalContent').setAttribute('aria-labelledby',b.id);journal()};b.onkeydown=e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();const next=all[(i+(e.key==='ArrowRight'?1:all.length-1))%all.length];next.click();next.focus()}}});
    $('talkHere').onclick=()=>{const p=data?.people.find(p=>p.here);fillInput(p?`สอบปากคำ${p.name}`:'ดูรอบๆ')};$('accuseSelected').onclick=()=>{const p=data?.people.find(p=>p.id===$('suspectSelect').value);if(p)fillInput(`กล่าวหา${p.name}`)};
  }
  document.addEventListener('DOMContentLoaded',init);
  return {refresh};
})();
