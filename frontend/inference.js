/**
 * frontend/inference.js — ระบบทบทวนข้อสรุปและข้อเสนอคดี (InferenceUI)
 * 
 * หน้าที่:
 * 1. แสดงหน้าต่างให้ผู้เล่นเสนอข้อสรุป (Claim) ในประเด็นสำคัญของคดี
 * 2. ให้ผู้เล่นเลือกหลักฐานประกอบ (Supporting Evidence) ที่ตนค้นพบแล้ว
 * 3. ส่งคำสั่ง infer ไปให้ Symbolic Engine ตัดสินความถูกต้อง
 */
const InferenceUI = (() => {
  let dialog, question, evidence = [], busy = false, opener;
  const chosen = new Set();
  function controls() {
    const choice = dialog.querySelector('#inferenceChoice').value;
    dialog.querySelector('#confirmInference').disabled = busy || gameOver || !choice || !chosen.size;
    dialog.querySelector('#cancelInference').disabled = busy;
    dialog.querySelectorAll('input,select').forEach(el => { el.disabled = busy; });
  }
  function init() {
    dialog = document.createElement('dialog'); dialog.className = 'accusation-dialog';
    dialog.setAttribute('aria-labelledby', 'inferenceTitle');
    dialog.innerHTML = `<h2 id="inferenceTitle">ทบทวนข้อสรุปของคุณ</h2>
      <p id="inferencePrompt"></p><label for="inferenceChoice">คุณเสนอว่าอย่างไร?</label>
      <select id="inferenceChoice"></select>
      <p>แนบข้อมูลที่ทำให้คุณสรุปเช่นนี้ การทบทวนไม่ใช้โอกาสกล่าวหา และเวลาในเกมยังเดินต่อ</p>
      <div id="inferenceEvidence"></div><p id="inferenceStatus" role="status"></p>
      <div class="accusation-actions"><button type="button" id="cancelInference">กลับไปตรวจสอบ</button>
      <button type="button" id="confirmInference">เสนอข้อสรุปพร้อมหลักฐาน</button></div>`;
    document.body.append(dialog);
    dialog.querySelector('#cancelInference').onclick = () => dialog.close();
    dialog.querySelector('#inferenceChoice').onchange = controls;
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.addEventListener('close', () => opener?.focus());
    dialog.querySelector('#confirmInference').onclick = async () => {
      if (busy || gameOver || !chosen.size) return;
      const target = dialog.querySelector('#inferenceChoice').value;
      const choice = question.choices.find(item => item.target === target);
      if (!choice) return;
      busy = true; controls();
      try {
        await locked(async () => {
          renderUser(`ข้อสรุปของฉัน: ${choice.label} · แนบข้อมูล ${chosen.size} รายการ`);
          const result = await submit(`infer ${target}`, {submittedEvidence: [...chosen]});
          if (result?.decision?.allowed || gameOver) dialog.close();
          else dialog.querySelector('#inferenceStatus').textContent = result?.decision?.message || 'ยังส่งไม่สำเร็จ ลองใหม่ได้';
        });
      } finally { busy = false; controls(); }
    };
  }
  function open(item, found) {
    if (gameOver || busy) return;
    if (!dialog) init();
    opener = document.activeElement; question = item; evidence = found; chosen.clear();
    dialog.querySelector('#inferencePrompt').textContent = item.prompt;
    const select = dialog.querySelector('#inferenceChoice'); select.replaceChildren();
    const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = 'เลือกข้อสรุปที่คุณต้องการเสนอ'; select.append(placeholder);
    item.choices.forEach(choice => { const opt = document.createElement('option'); opt.value = choice.target; opt.textContent = choice.label; select.append(opt); });
    const list = dialog.querySelector('#inferenceEvidence'); list.replaceChildren();
    evidence.forEach(entry => {
      const label = document.createElement('label'); label.className = 'accusation-evidence';
      const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
      const copy = document.createElement('span'); const title = document.createElement('strong'); title.textContent = entry.name;
      const text = document.createElement('small'); text.textContent = entry.description;
      copy.append(title, text); label.append(checkbox, copy); list.append(label);
      checkbox.onchange = () => { checkbox.checked ? chosen.add(entry.id) : chosen.delete(entry.id); controls(); };
    });
    dialog.querySelector('#inferenceStatus').textContent = '';
    controls(); dialog.showModal();
  }
  return {open};
})();
