const NovelUI = (() => {
  let pages=[], position=0, box, introResolve=null, speaker='';
  function split(text){
    return String(text).split(/\n\s*\n/).map(s=>s.trim()).filter(Boolean);
  }
  function elements(){
    if(box)return;
    box=document.getElementById('sceneDialogue');
    document.addEventListener('keydown',event=>{
      if(!active()||event.isComposing||event.repeat||event.key!=='Enter')return;
      if(document.querySelector('dialog[open]'))return;
      // มีข้อความในช่องพิมพ์ ปล่อยให้ฟอร์มส่งคำสั่งไปตามปกติ (sendMessage จะปิดบทสนทนาเอง)
      if(!introResolve&&document.getElementById('chatInput')?.value?.trim())return;
      event.preventDefault();event.stopImmediatePropagation();next();
    },true);
    box.onclick=()=>next();
  }
  function active(){return pages.length>0 || introResolve!==null;}
  function paint(){
    document.getElementById('dialogueSpeaker').textContent=/^[“"]/.test(pages[position])?speaker:'คำบรรยาย';
    document.getElementById('dialogueText').textContent=pages[position];
    document.getElementById('dialogueProgress').textContent=`${position+1} / ${pages.length} · Enter หรือคลิก${position===pages.length-1?'เพื่อปิด':'เพื่ออ่านต่อ'} · พิมพ์คำสั่งต่อได้เลย`;
    box.hidden=false;
  }
  function close(){
    pages=[];position=0;if(box)box.hidden=true;
    const feed=document.getElementById('chatFeed');if(feed)feed.scrollTop=0;
    if(typeof setBusy==='function')setBusy(busy);
  }
  function next(){
    if(introResolve){
      document.getElementById('introScreen').hidden=true;
      const resolve=introResolve;introResolve=null;resolve();return;
    }
    if(!pages.length)return;
    if(++position>=pages.length){close();return;}
    paint();
  }
  function onResult(result){
    elements();close();
    if(!result.decision?.allowed || result.parsed?.action!=='interrogate' || result.new_state?.ending_id)return;
    pages=split(result.decision.message);
    if(!pages.length)return;
    speaker=(suspectsMap[result.parsed.target]||'บทสนทนา').split(' (')[0];
    position=0;paint();
    box.scrollIntoView({block:'center',behavior:'smooth'});
    setBusy(busy);
  }
  function intro(briefing){
    elements();document.getElementById('introBriefing').textContent=briefing;
    document.getElementById('introScreen').hidden=false;
    document.getElementById('chatInput').disabled=true;
    document.getElementById('sendBtn').disabled=true;
    return new Promise(resolve=>{introResolve=resolve;});
  }
  return {intro,onResult,next,close,active,split};
})();
