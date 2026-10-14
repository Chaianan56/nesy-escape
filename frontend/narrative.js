/* Render only scene pages already approved by the server. This view grants no facts. */
const StoryScenes = (() => {
  let dialog, scene, mode, position = 0, complete = null, opener, loading = false;
  const $ = id => dialog.querySelector(`#${id}`);

  function init() {
    if (dialog) return;
    dialog = document.createElement('dialog');
    dialog.id = 'storySceneDialog'; dialog.className = 'narrative-dialog';
    dialog.setAttribute('aria-labelledby', 'narrativeTitle');
    dialog.innerHTML = `<header class="narrative-header">
      <div><p id="narrativeMode"></p><h2 id="narrativeTitle"></h2></div>
      <button type="button" id="narrativeClose">กลับไปสืบสวน</button>
    </header>
    <div class="narrative-body">
      <figure><img id="narrativeArt" alt="ภาพประกอบเหตุการณ์"><figcaption id="narrativeTime"></figcaption></figure>
      <section class="narrative-copy" aria-live="polite" aria-atomic="true">
        <h3 id="narrativeSpeaker"></h3><p id="narrativeText"></p>
        <div id="narrativeEvidence"></div>
      </section>
    </div>
    <footer class="narrative-footer">
      <div><p id="narrativeProgress"></p><small id="narrativeClockNote"></small></div>
      <div class="narrative-actions"><button type="button" id="narrativeSkip">ข้ามไปหน้ารับคดี</button>
        <button type="button" id="narrativePrevious">ย้อนอ่าน</button>
        <button type="button" id="narrativeNext" autofocus>อ่านต่อ</button></div>
    </footer>`;
    document.body.append(dialog);
    $('narrativePrevious').onclick = () => { if (position > 0) {position--; paint();} };
    $('narrativeNext').onclick = () => {
      if (position < scene.pages.length - 1) {position++; paint();}
      else finish();
    };
    $('narrativeSkip').onclick = () => {position = scene.pages.length - 1; paint();};
    $('narrativeClose').onclick = finish;
    dialog.addEventListener('cancel', event => {
      event.preventDefault();
      if (mode !== 'opening') finish();
    });
    $('narrativeArt').onerror = () => { $('narrativeArt').hidden = true; };
  }

  function paint() {
    const page = scene.pages[position];
    $('narrativeTitle').textContent = scene.title;
    $('narrativeSpeaker').textContent = page.speaker || 'คำบรรยาย';
    $('narrativeText').textContent = page.text;
    $('narrativeTime').textContent = page.time_label || '';
    const art = $('narrativeArt');
    art.hidden = !/^[a-z0-9-]+$/.test(page.art || '');
    if (!art.hidden) art.src = `/game-art/${page.art}.png`;
    const evidence = $('narrativeEvidence'); evidence.replaceChildren();
    if (page.evidence?.length) {
      const title = document.createElement('strong'); title.textContent = 'ข้อมูลที่คุณใช้เชื่อมเหตุการณ์'; evidence.append(title);
      const list = document.createElement('ul');
      page.evidence.forEach(item => {const li=document.createElement('li');li.textContent=item.name;list.append(li);});
      evidence.append(list);
    }
    $('narrativeProgress').textContent = `${position + 1} / ${scene.pages.length}`;
    $('narrativePrevious').disabled = position === 0;
    $('narrativeSkip').hidden = mode !== 'opening' || position === scene.pages.length - 1;
    $('narrativeNext').textContent = position < scene.pages.length - 1 ? 'อ่านต่อ →'
      : mode === 'opening' ? 'เริ่มสืบสวน' : mode === 'reconstruction' ? 'กลับไปดูผลคดี' : 'กลับไปสืบสวน';
    dialog.querySelector('.narrative-copy').scrollTop = 0;
    dialog.scrollTop = 0;
  }

  function finish() {
    const resolve = complete; complete = null;
    if (dialog?.open) dialog.close();
    opener?.focus();
    resolve?.(true);
  }

  function play(next, options = {}) {
    if (!next?.pages?.length || dialog?.open) return Promise.resolve(false);
    init(); scene = next; mode = options.mode || 'confrontation'; position = 0;
    opener = document.activeElement;
    $('narrativeMode').textContent = mode === 'opening' ? 'ก่อนเริ่มคดี'
      : mode === 'reconstruction' ? 'ทบทวนคดีจากหลักฐานที่คุณยื่น' : 'เผชิญหน้าด้วยข้อสรุปของคุณ';
    $('narrativeClockNote').textContent = mode === 'opening' ? 'เวลา 90 นาทีจะเริ่มเมื่อคุณกดเริ่มสืบสวน'
      : mode === 'reconstruction' ? 'คดีปิดแล้ว · อ่านซ้ำได้' : 'เวลาในคดียังเดินต่อ · บทสนทนาเก็บไว้ในประวัติ';
    $('narrativeClose').hidden = mode === 'opening';
    $('narrativeClose').textContent = mode === 'reconstruction' ? 'ปิดฉากย้อนหลัง' : 'กลับไปสืบสวน';
    if (mode === 'opening') {
      document.getElementById('chatInput').disabled = true;
      document.getElementById('sendBtn').disabled = true;
    }
    paint();
    const pending = new Promise(resolve => { complete = resolve; });
    dialog.showModal(); $('narrativeNext').focus();
    return pending;
  }

  function appendReplay(next) {
    const card = document.createElement('div'); card.className = 'msg-system scene-replay';
    const label = document.createElement('strong');label.textContent=next.title;
    const button = document.createElement('button');button.type='button';button.className='chip-btn';
    button.textContent='อ่านฉากนี้อีกครั้ง';button.onclick=()=>play(next);
    card.append(label,button);document.getElementById('chatFeed').append(card);
  }

  async function reconstruct() {
    if (loading) return;
    loading = true;
    const button = document.getElementById('reconstructCase'); if(button)button.disabled=true;
    try {
      const response = await fetch(`${API_BASE}/reconstruction`, {signal:AbortSignal.timeout(8000)});
      if (!response.ok) throw Error();
      const result = await response.json();
      if (result.scene) await play(result.scene, {mode:'reconstruction'});
      else renderError('คดีนี้ยังไม่มีฉากประกอบเหตุการณ์จากหลักฐานที่ยื่น');
    } catch { renderError('เปิดฉากย้อนหลังไม่สำเร็จ ลองอีกครั้งได้'); }
    finally {loading=false; if(button)button.disabled=false;}
  }

  return {play,appendReplay,reconstruct,stop:finish};
})();
