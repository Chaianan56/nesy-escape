const AccusationUI = (() => {
  // ต้องตรงกับ MAX_SUBMITTED_EVIDENCE / MAX_FAILED_ACCUSATIONS ใน app/symbolic/engine.py
  const MAX_EVIDENCE = 15, MAX_TRIES = 3;
  let dialog, target, evidence = [], opener, busy = false, request = 0;
  const drafts = new Map();
  function init() {
    dialog = document.createElement('dialog');
    dialog.className = 'accusation-dialog';
    dialog.setAttribute('aria-labelledby', 'accusationTitle');
    dialog.innerHTML = `<h2 id="accusationTitle">ยื่นคำกล่าวหา</h2>
      <p id="accusationPerson"></p>
      <p>เลือกหลักฐานและคำให้การที่รองรับเวลา แรงจูงใจ โอกาส และร่องรอยของบุคคลนี้ แล้วตรวจทานก่อนยืนยัน เวลาในเกมยังเดินต่อ</p>
      <p id="accusationLimits"></p>
      <div id="accusationEvidence"></div><p id="accusationStatus" role="status"></p>
      <div class="accusation-actions"><button type="button" id="cancelAccusation">กลับไปสืบสวน</button>
      <button type="button" id="confirmAccusation">ยืนยันคำกล่าวหา · อาจจบคดี</button></div>`;
    document.body.append(dialog);
    dialog.querySelector('#cancelAccusation').onclick = () => dialog.close();
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.addEventListener('close', () => { request++; opener?.focus(); });
    dialog.querySelector('#confirmAccusation').onclick = async () => {
      if (busy || gameOver) return;
      const selected = [...(drafts.get(target) || [])];
      if (!selected.length) return;
      busy = true; controls();
      try {
        await locked(async () => {
          const text = `กล่าวหา${suspectsMap[target] || target}`;
          renderUser(`${text} · ยื่นหลักฐาน ${selected.length} รายการ`);
          const result = await submit(text, {submittedEvidence: selected});
          if (result?.new_state?.ending_id || gameOver) dialog.close();
          else {
            status(result?.decision?.message || 'ยังส่งไม่สำเร็จ หลักฐานที่เลือกยังอยู่ ลองใหม่ได้');
            limits();
            dialog.querySelector('#accusationStatus').scrollIntoView({block: 'nearest'});
          }
        });
      } finally { busy = false; controls(); }
    };
  }
  // คดีปิดได้สองทาง: หลักฐานพอสรุป (แม้สรุปผิด) หรือยื่นไม่พอครบโควตา ต้องบอกทั้งคู่ก่อนกดยืนยัน
  function limits() {
    const tries = MAX_TRIES - (gameState?.failed_accusations || 0);
    dialog.querySelector('#accusationLimits').textContent =
      `เลือกได้ไม่เกิน ${MAX_EVIDENCE} ชิ้น · ยื่นได้อีก ${tries} ครั้ง
`
      + 'หลักฐานพอสรุปคดีได้ → คดีปิดทันที แม้ข้อสรุปผิด · ยังไม่พอ → ได้คำติชมแล้วยื่นใหม่ได้ · ครั้งสุดท้ายยังไม่พอ → คดีปิดแบบพิสูจน์ไม่ได้';
  }
  function status(text) { dialog.querySelector('#accusationStatus').textContent = text; }
  function controls() {
    dialog.querySelector('#confirmAccusation').disabled = busy || gameOver || !(drafts.get(target)?.size);
    dialog.querySelector('#cancelAccusation').disabled = busy;
    dialog.querySelectorAll('input').forEach(input => { input.disabled = busy; });
  }
  async function open(suspect) {
    if (gameOver || busy || !suspectsMap[suspect]) return;
    if (!dialog) init();
    const revision = ++request;
    opener = document.activeElement; target = suspect;
    dialog.querySelector('#accusationPerson').textContent = suspectsMap[suspect];
    limits();
    const list = dialog.querySelector('#accusationEvidence'); list.replaceChildren();
    status('กำลังเปิดรายการหลักฐาน…');
    if (!dialog.open) dialog.showModal();
    dialog.querySelector('#confirmAccusation').disabled = true;
    try {
      const response = await fetch(`${API_BASE}/journal`, {method: 'POST', signal: AbortSignal.timeout(8000)});
      if (!response.ok) throw Error();
      const journal = await response.json();
      if (request !== revision || !dialog.open) return;
      if (gameOver || journal.case_closed) { dialog.close(); return; }
      evidence = journal.evidence;
      const available = new Set(evidence.map(item => item.id));
      const chosen = new Set([...(drafts.get(target) || [])].filter(id => available.has(id)));
      drafts.set(target, chosen);
      evidence.forEach(item => {
        const label = document.createElement('label'); label.className = 'accusation-evidence';
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = chosen.has(item.id);
        const copy = document.createElement('span'); const title = document.createElement('strong'); title.textContent = item.name;
        const description = document.createElement('small'); description.textContent = item.description;
        copy.append(title, description); label.append(checkbox, copy); list.append(label);
        checkbox.onchange = () => { checkbox.checked ? chosen.add(item.id) : chosen.delete(item.id); status(`เลือก ${chosen.size} จาก ${evidence.length} รายการ (ไม่เกิน ${MAX_EVIDENCE})`); controls(); };
      });
      status(evidence.length ? `เลือก ${chosen.size} จาก ${evidence.length} รายการ (ไม่เกิน ${MAX_EVIDENCE})` : 'ยังไม่มีหลักฐาน กลับไปตรวจสิ่งของและสอบปากคำก่อน');
      controls();
    } catch { if (revision === request) status('เปิดหลักฐานไม่สำเร็จ ปิดหน้าต่างแล้วลองอีกครั้ง'); }
  }
  return {open};
})();
