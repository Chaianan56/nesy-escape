/**
 * NeSy-Escape: Complete Controller & UI Manager (Alliance Modern Dashboard)
 * 
 * คุณสมบัติ:
 * 1. ตัวอย่างคำสั่ง (Quick Suggestion Chips & Onboarding Hints)
 * 2. คำบรรยายห้องตอนเริ่มเกม (Auto Look Around via POST /command)
 * 4. นาฬิกาการสืบสวน (FE-3: Investigation Clock)
 * 5. ป้ายแสดงตู้รถปัจจุบัน (Location HUD Pill)
 */

// ใช้ origin เดียวกับหน้าเว็บ เพราะ FastAPI เสิร์ฟทั้ง API และไฟล์หน้าเว็บ
// ถ้าฝัง 127.0.0.1 ไว้ พอขึ้นคลาวด์เบราว์เซอร์จะยิงกลับไปที่เครื่องผู้ใช้เอง ไม่ใช่เซิร์ฟเวอร์
// เปิดไฟล์ตรงๆ ด้วย file:// ค่อยถอยไปใช้ localhost
const API_BASE = window.location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";

let gameState = null;
let timeLimitSeconds = 3600;
let locationsMap = {};
let suspectsMap = {};
let objectsMap = {};
let rulesCount = null;
let gameOver = false;   // ปิดคดีแล้วหรือหมดเวลาแล้ว ห้ามรับคำสั่งอีก
let busy = false;       // มีคำสั่งค้างอยู่ในสาย ห้ามส่งซ้อน
let clockTimer = null;
let clockPending = false;
let deadlineReached = false;
let clockFailures = 0;
let clockAnchor = null;
let clockElapsed = 0;

function anchorClock() {
  clockElapsed = gameState.elapsed_seconds || 0;
  clockAnchor = Date.now();
}

function elapsedNow() {
  return clockAnchor === null ? (gameState?.elapsed_seconds || 0)
    : clockElapsed + Math.floor((Date.now() - clockAnchor) / 1000);
}

async function tickClock() {
  if (!gameState || gameOver) return;
  updateClock();
  if (elapsedNow() < timeLimitSeconds) return;
  deadlineReached = true;
  setBusy(busy);
  if (clockPending || clockFailures >= 3) return;
  clockPending = true;
  setEndingStatus("กำลังยืนยันฉากจบ…");
  try {
    const res = await fetch(`${API_BASE}/clock`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}), signal: AbortSignal.timeout(10000),
    });
    if (gameOver) return null;
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(typeof error.detail === 'string' ? error.detail : `HTTP ${res.status}`);
    }
    const data = await res.json();
    if (gameOver) return;
    clockFailures = 0;
    // Keep action state if a command completed while this clock request was pending.
    if (data.new_state.ending_id) {
      gameState = { ...gameState, ending_id: data.new_state.ending_id,
        elapsed_seconds: data.new_state.elapsed_seconds };
      showGameOver(data.decision);
    } else {
      gameState.elapsed_seconds = data.new_state.elapsed_seconds;
      anchorClock();
      deadlineReached = false;
      setEndingStatus("");
      setBusy(busy);
    }
  } catch (err) {
    if (gameOver) return;
    clockFailures++;
    setEndingStatus(clockFailures >= 3
      ? "ยังยืนยันฉากจบไม่ได้ กรุณาตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง"
      : "เชื่อมต่อไม่สำเร็จ กำลังลองยืนยันฉากจบอีกครั้ง…", clockFailures >= 3);
  } finally {
    clockPending = false;
  }
}


function setEndingStatus(message, retry = false) {
  const status = document.getElementById('endingStatus');
  const button = document.getElementById('retryEnding');
  if (status) { status.hidden = !message; status.textContent = message; }
  if (button) button.hidden = !retry;
}

function retryEnding() {
  if (gameOver || clockPending) return;
  clockFailures = 0;
  return tickClock();
}

// ============================================================
// 1. เริ่มต้นเกม (INIT GAME)
// ============================================================
window.addEventListener("DOMContentLoaded", () => {
  initGame();
});

async function initGame() {
  const feed = document.getElementById("chatFeed");
  feed.innerHTML = `
    <div class="msg-loading" id="initLoading">
      <div class="spinner"></div>
      <span>กำลังเชื่อมต่อกับ backend และโหลดข้อมูลฉาก (GET /scene)...</span>
    </div>
  `;

  try {
    const res = await fetch(`${API_BASE}/scene`, { signal: AbortSignal.timeout(4000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sceneData = await res.json();

    // บันทึกสถานะตั้งต้นครบ 8 ฟิลด์และข้อมูลฉาก
    gameState = sceneData.initial_state;
    if (typeof NovelUI !== 'undefined' && gameState.started_at == null && !gameState.ending_id) {
      await NovelUI.intro(sceneData.briefing);
      const started = await fetch(`${API_BASE}/start`, {method:'POST'});
      if (!started.ok) throw Error(`HTTP ${started.status}`);
      gameState = (await started.json()).new_state;
    }
    anchorClock();
    deadlineReached = false;
    if (clockTimer !== null) clearInterval(clockTimer);
    clockTimer = setInterval(tickClock, 1000);
    timeLimitSeconds = sceneData.time_limit_seconds || 3600;
    locationsMap = sceneData.locations || {};
    suspectsMap = sceneData.suspects || {};
    objectsMap = sceneData.objects || {};
    rulesCount = sceneData.rules_count || null;
    if (typeof PixelUI !== 'undefined') PixelUI.refresh();

    // อัปเดต HUD (ตำแหน่งและนาฬิกา)
    updateLocationHUD();
    updateClock();

    // เคลียร์ loading และแสดงบรีฟคดี (Briefing) จาก story.json
    feed.innerHTML = "";
    renderBriefing(sceneData.briefing);

    // ดึงสถานะสี่เสาตั้งต้น (FE-4)

    // ข้อ 2: คำบรรยายห้องตอนเริ่มเกม — ยิง "ดูรอบๆ" อัตโนมัติหนึ่งครั้ง
    await executeInitialLookAround();

  } catch (err) {
    feed.innerHTML = `
      <div class="msg-error">
        <strong>⚠️ ไม่สามารถเชื่อมต่อกับ backend (${API_BASE}) ได้</strong><br>
        กรุณาตรวจสอบว่าเซิร์ฟเวอร์เปิดอยู่ (รันคำสั่ง: <code>uvicorn app.main:app --reload</code>)<br>
        <button onclick="initGame()">🔄 ลองเชื่อมต่อใหม่อีกครั้ง</button>
      </div>
    `;
  }
}

// แสดงการ์ดบรีฟคดี พร้อมตัวอย่างคำสั่งเบื้องต้น (ข้อ 1)
function renderBriefing(briefingText) {
  const feed = document.getElementById("chatFeed");
  const card = document.createElement("div");
  card.className = "msg-system";
  card.innerHTML = `
    <div class="card-header-bar">
      <span class="badge info">📋 บรีฟคดี (Case Briefing)</span>
      <span class="mode-tag">นอกเทิร์นเอกซ์เพรส 1938</span>
    </div>
    <div class="story-text">${escapeHtml(briefingText)}</div>
    
    <div class="hints-box">
      <div class="hints-title">💡 ตัวอย่างคำสั่งที่พิมพ์ได้ในเกม:</div>
      <div class="hints-list">
        <div>• <code>ดูรอบๆ</code> — สำรวจตู้รถที่ยืนอยู่และดูสิ่งที่มองเห็นได้</div>
        <div>• <code>ไปที่จุดเกิดเหตุ</code> — เดินทางไปยังห้องเก็บของบริการ</div>
        <div>• <code>ตรวจดูสมุดบันทึกของผู้ตาย</code> — ตรวจสอบวัตถุหรือหลักฐานในห้อง</div>
        <div>• <code>ขอสอบปากคำพนักงานควบคุมรถหน่อย</code> — พูดคุยกับพยานหรือผู้ต้องสงสัย</div>
        <div>• <code>กล่าวหากิเดียน ฮาร์ต</code> — ต้องมีหลักฐานเข้าเงื่อนไขฉากจบของบุคคลนั้นก่อน หากยังไม่ครบให้สืบสวนต่อ</div>
      </div>
    </div>
  `;
  feed.appendChild(card);
}

// ข้อ 2: ยิงคำสั่ง "ดูรอบๆ" อัตโนมัติเพื่อแสดงคำบรรยายห้องที่ยืนอยู่
function executeInitialLookAround() {
  return locked(() => submit("ดูรอบๆ", { isRoomLook: true }));
}

// ============================================================
// 2. HUD UPDATES (Location & Clock)
// ============================================================
function updateLocationHUD() {
  const locText = document.getElementById("locText");
  if (!locText || !gameState) return;
  const locId = gameState.current_location || "passenger_car";
  locText.textContent = locationsMap[locId] || locId;
}

function updateClock() {
  const clockText = document.getElementById("clockText");
  const clockWidget = document.getElementById("clockWidget");
  if (!clockText || !clockWidget) return;

  const elapsed = elapsedNow();
  const remaining = Math.max(0, timeLimitSeconds - elapsed);
  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;

  clockText.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

  if (remaining <= 0) {
    clockWidget.className = "hud-pill clock-pill danger";
    clockText.textContent = "00:00 (หมดเวลา)";
  } else if (remaining <= 600) {
    clockWidget.className = "hud-pill clock-pill danger";
  } else if (remaining <= 1200) {
    clockWidget.className = "hud-pill clock-pill warning";
  } else {
    clockWidget.className = "hud-pill clock-pill";
  }
}

// ============================================================


// ============================================================
// 4. สลับโหมดการทดลอง (Mode A vs Mode B)
// ============================================================

// ============================================================
// 5. ตัวอย่างคำสั่ง (Quick Chips Fill)
// ============================================================
function fillInput(text) {
  const input = document.getElementById("chatInput");
  if (!input) return;
  input.value = text;
  input.focus();
}

// ============================================================
// 6. ลูปการส่งคำสั่ง (Send Message & Lock Input)
// ============================================================
// ล็อกตัวเดียวคุมทุกเส้นทาง ทั้งพิมพ์เอง กดปุ่มคำสั่งพ่วง และดูรอบๆ ตอนเริ่มเกม
// เคยพลาดตรงนี้มาแล้ว ไปเช็ค input.disabled ซึ่งถูกตั้งเป็น true ตอนเริ่มส่งอยู่แล้ว
// เงื่อนไขจึงเป็นเท็จตลอด ปุ่มค้างที่ ประมวลผล... และพิมพ์ได้ครั้งเดียวทั้งเกม
// คราวนี้เก็บสถานะไว้ในตัวแปรของตัวเอง ไม่ไปอ่านจากหน้าจอ
function setBusy(on) {
  busy = on;
  const input = document.getElementById("chatInput");
  const btn = document.getElementById("sendBtn");
  const btnText = document.getElementById("sendBtnText");
  if (!input || !btn) return;
  // บทสนทนาไม่ล็อกช่องพิมพ์ ผู้เล่นพิมพ์คำสั่งถัดไปได้เลย ล็อกเฉพาะหน้าจอเปิดเรื่อง
  const intro = document.getElementById("introScreen");
  const lock = on || gameOver || deadlineReached || (!!intro && !intro.hidden);
  input.disabled = lock;
  btn.disabled = lock;
  if (btnText) btnText.textContent = gameOver ? "จบเกม" : (on ? "ประมวลผล..." : "ส่งคำสั่ง");
  if (!lock) input.focus();
}

// ถือล็อกตลอดทั้งงาน ไม่ใช่ต่อหนึ่งคำสั่ง
// คำสั่งพ่วงหลายขั้นจึงเดินจนจบโดยไม่มีคำสั่งอื่นแทรกกลางทาง
async function locked(fn) {
  if (busy || gameOver || deadlineReached) return false;
  setBusy(true);
  try {
    await fn();
  } finally {
    setBusy(false);
  }
  return true;
}

// เส้นทางเดียวของทุกคำสั่ง คืน data ถ้าสำเร็จ คืน null ถ้าเรียกไม่ได้
// เดิมมีสามเส้นทางแยกกัน แต่ละเส้นตรวจไม่เหมือนกัน ปุ่มคำสั่งพ่วงจึงไม่ดักเน็ตหลุด
// และไม่ปิดหน้าจอตอนคดีปิด กล่าวหาผ่านปุ่มแล้วยังพิมพ์ต่อได้
async function submit(text, opts = {}) {
  if (gameOver || deadlineReached) return null;
  if (text.trim() === 'ขอคำใบ้') {
    try {
      const response = await fetch(`${API_BASE}/hint`, {method:'POST'});
      if (!response.ok) throw Error(`HTTP ${response.status}`);
      const hint = await response.json();
      const note = document.createElement('div'); note.className='msg-system';note.textContent=hint.text;
      document.getElementById('chatFeed').appendChild(note);
    } catch { renderError('โหลดคำใบ้ไม่สำเร็จ กรุณาลองใหม่'); }
    return null;
  }
  showLoading();
  try {
    if (!gameState) {
      const sRes = await fetch(`${API_BASE}/scene`);
      if (!sRes.ok) throw new Error(`HTTP ${sRes.status}`);
      gameState = (await sRes.json()).initial_state;
    }

    // Typed evidence numbers refer to the numbered entries in the journal.
    const marker = text.indexOf('หลักฐาน:');
    if (marker >= 0) {
      const numbers = text.slice(marker + 'หลักฐาน:'.length).trim().split(/[\s,]+/);
      const response = await fetch(`${API_BASE}/journal`, {method:'POST'});
      if (!response.ok) throw Error(`HTTP ${response.status}`);
      const journal = await response.json();
      if (!numbers.length || numbers.some(n => !/^[1-9]\d*$/.test(n) || !journal.evidence[Number(n)-1])) {
        removeLoading(); renderError('ระบุเลขหลักฐานจากสมุดคดี เช่น กล่าวหากิเดียน หลักฐาน: 1, 2, 3'); return null;
      }
      opts = {...opts, submittedEvidence: numbers.map(n => journal.evidence[Number(n)-1].id)};
      text = text.slice(0, marker).trim();
    }
    const res = await fetch(`${API_BASE}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, ...(opts.submittedEvidence ? {submitted_evidence: opts.submittedEvidence} : {}) }),
      signal: AbortSignal.timeout(12000), // longer than the server's 8s Gemini budget
    });
    if (gameOver) return null;
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      if (gameOver) return null;
      if (typeof error.detail === 'string') { removeLoading(); renderError(`⚠️ ${error.detail}`); return null; }
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();

    if (gameOver) return null; // Ignore late responses after the deadline closed the case.
    if (data.new_state) gameState = data.new_state;
    anchorClock();
    updateLocationHUD();
    updateClock();
    removeLoading();
    if (gameState?.ending_id) { showGameOver(data.decision); return data; }
    // กล่าวหาโดยยังไม่ยื่นหลักฐาน: เปิดหน้าต่างเลือกหลักฐานแทนการให้พิมพ์เลข
    const askEvidence = data.decision.violated_rule_id === 'R_SUBMITTED_EVIDENCE' && !opts.submittedEvidence
      && data.parsed?.target && typeof AccusationUI !== 'undefined';
    if (askEvidence) AccusationUI.open(data.parsed.target);
    // คำสั่งพ่วงไม่ต้องโชว์การ์ด "กำกวม" ของตัวมันเอง เดี๋ยวแต่ละขั้นมีการ์ดของตัวเอง
    else if (!(data.parsed?.sequence && data.parsed.alternatives?.length)) renderSystem(data.decision, data.parsed, opts.isRoomLook);
    renderConversationSummary(data.conversation_summaries || []);
    if (typeof GameArt !== 'undefined') GameArt.onResult(data);
    if (typeof NovelUI !== 'undefined') NovelUI.onResult(data);
    if (typeof PixelUI !== 'undefined') PixelUI.refresh();

    return data;
  } catch (err) {
    removeLoading();
    if (gameOver) return null;
    renderError(err.name === 'TimeoutError'
      ? '⚠️ เซิร์ฟเวอร์ตอบช้าเกินไป ลองส่งคำสั่งอีกครั้ง'
      : `⚠️ เชื่อมต่อไม่ได้: ${err.message} กรุณาตรวจสอบสถานะ backend แล้วลองใหม่`);
    return null;
  }
}

function showLoading() {
  const feed = document.getElementById("chatFeed");
  const loadingDiv = document.createElement("div");
  loadingDiv.className = "msg-loading";
  loadingDiv.id = "activeLoading";
  loadingDiv.innerHTML = `
    <div class="spinner"></div>
    <span>NeSy Engine กำลังตีความและตรวจกฎ${rulesCount ? " " + rulesCount + " ข้อ" : ""}...</span>
  `;
  feed.appendChild(loadingDiv);
  feed.scrollTop = feed.scrollHeight;
}

async function sendMessage(e) {
  e.preventDefault();
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  // ระหว่างบทสนทนา: ช่องว่าง = อ่านต่อ, มีข้อความ = ข้ามบทสนทนาแล้วส่งคำสั่งเลย
  if (typeof NovelUI !== 'undefined' && NovelUI.active()) {
    if (!text) { NovelUI.next(); return; }
    NovelUI.close();
  }
  if (!text) return;

  let steps = [], sequence = false;
  await locked(async () => {
    renderUser(text);
    input.value = "";
    const data = await submit(text);
    if (!data || gameOver) return;

    // Backend sequences are already executed. Only pending steps need confirmation.
    // Retain the old wire format for compatibility with an older server.
    if (data.pending_steps?.length) {
      steps = parseSteps({action: 'ambiguous', sequence: true, alternatives: data.pending_steps});
      sequence = true;
    } else if (data.parsed?.action !== 'sequence') {
      steps = parseSteps(data.parsed);
      sequence = !!data.parsed.sequence;
    }
    if (!sequence && steps.length > 1) offerSteps(steps);
  });
  if (sequence && steps.length) await runSequence(steps);
}

async function restartGame() {
  try {
    const res = await fetch(`${API_BASE}/new-game`, { method: "POST" });
    if (!res.ok && res.status !== 401) throw new Error(`HTTP ${res.status}`);
    window.location.reload();
  } catch (err) {
    renderError(`เริ่มคดีใหม่ไม่ได้: ${err.message}`);
  }
}

function showGameOver(decision = null) {
  if (gameOver) return;
  gameOver = true;
  deadlineReached = true;
  removeLoading();
  setEndingStatus('');
  if (clockTimer !== null) clearInterval(clockTimer);
  if (typeof NovelUI !== 'undefined') NovelUI.close();
  setBusy(false);
  updateClock();
  document.getElementById('chatInput').placeholder = 'คดีปิดแล้ว';
  const restart = document.getElementById('restartGame');
  if (restart) restart.hidden = false;
  const feed = document.getElementById('chatFeed');
  const box = document.createElement('div');
  box.className = 'msg-system ending-card';
  box.innerHTML = `<div class="card-header-bar"><span class="badge info">${gameState?.ending_id === 'cold_arrival' ? 'หมดเวลา · รถไฟถึงปลายทาง' : 'บทสรุปคดี'}</span></div>` +
    `<div class="story-text">${escapeHtml(decision?.message || 'คดีนี้ปิดลงแล้ว')}</div>`;
  feed.appendChild(box);
  feed.scrollTop = 0;
  if (typeof PixelUI !== 'undefined') PixelUI.refresh();
}

// ============================================================
// คิวคำสั่งพ่วง — แปลง alternatives เป็นลำดับขั้นแล้วทำทีละขั้น
// ============================================================
const VERB_TH = { examine: "ตรวจ", move: "ไป", interrogate: "สอบปากคำ", take: "หยิบ",
                  accuse: "กล่าวหา", burn: "เผา", unlock: "ปลดล็อก", use: "ใช้" };
const IRREVERSIBLE = new Set(["accuse", "burn"]);

function parseSteps(parsed) {
  if (!parsed || (parsed.action !== "ambiguous" && parsed.action !== "unknown")) return [];
  const known = { ...locationsMap, ...objectsMap, ...suspectsMap };
  return (parsed.alternatives || [])
    .map((a) => {
      const [action, target] = a.split(/\s+/);
      // คำสั่งพ่วงเก็บของที่ยังมองไม่เห็นไว้ด้วย (อาจเห็นหลังเดินไปถึง) แต่ไม่เอ่ยชื่อจริงให้
      if (!action || !target || (!known[target] && !parsed.sequence)) return null;
      return { action, target, label: `${VERB_TH[action] || action} ${known[target] || "สิ่งที่คุณพิมพ์ไว้"}` };
    })
    .filter(Boolean);
}

// สั่งหลายอย่างต่อกัน (sequence) ทำให้เลยตามลำดับ
// ยกเว้นกล่าวหา/เผา ที่ย้อนกลับไม่ได้ หยุดรอให้ผู้เล่นกดยืนยันก่อน
async function runSequence(steps) {
  const cut = steps.findIndex(st => IRREVERSIBLE.has(st.action));
  const now = cut === -1 ? steps : steps.slice(0, cut);
  if (now.length && !(await runSteps(now))) return;
  if (cut !== -1 && !gameOver) offerSteps(steps.slice(cut), true);
}

// พิมพ์กำกวมจนต้องเลือก ("พาไปห้องอื่นหน่อย") ให้กดเลือกเอง แม่นกว่าเดาผิดแล้วเผาเวลาในเกมทิ้ง
// confirm=true ใช้ยืนยันขั้นที่ย้อนกลับไม่ได้ของคำสั่งพ่วง ปุ่มเดียวทำที่เหลือทั้งหมด
function offerSteps(steps, confirm = false) {
  const feed = document.getElementById("chatFeed");
  const box = document.createElement("div");
  box.className = "msg-system";
  box.innerHTML = confirm
    ? `<div class="story-text"><strong>ขั้นต่อไปย้อนกลับไม่ได้</strong><br>กดยืนยันถ้าต้องการทำต่อ</div>`
    : `<div class="story-text"><strong>คำสั่งนี้ตีความได้ ${steps.length} อย่าง</strong><br>เลือกสิ่งที่ต้องการ</div>`;
  const wrap = document.createElement("div");
  wrap.className = "chips-scroll";
  box.appendChild(wrap);
  feed.appendChild(box);

  const button = (text, run) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip-btn";
    b.textContent = text;
    b.onclick = () => { wrap.remove(); run(); };
    wrap.appendChild(b);
  };
  if (confirm) button(`ยืนยัน: ${steps.map(st => st.label).join(" → ")}`, () => runSteps(steps));
  else steps.forEach(st => button(st.label, () => runSteps([st])));

  feed.scrollTop = feed.scrollHeight;
}

// ใช้เส้นทางเดียวกับการพิมพ์เอง จึงได้การล็อก การดักเน็ตหลุด และการปิดหน้าจอตอนคดีปิด
// มาเหมือนกันทั้งหมด โดยไม่ต้องเขียนซ้ำ
async function runSteps(steps) {
  let done = false;
  const started = await locked(async () => {
    for (const [i, st] of steps.entries()) {
      renderUser(steps.length > 1 ? `(ขั้นที่ ${i + 1}) ${st.label}` : st.label);
      const data = await submit(`${st.action} ${st.target}`);
      const left = steps.length - i - 1;

      // ขั้นถัดไปตั้งอยู่บนสมมติฐานว่าขั้นนี้สำเร็จ ทำต่อไปก็ผิดยกแถว
      // คดีปิดกลางทางก็หยุดเหมือนกัน ที่เหลือไม่มีความหมายแล้ว
      if (!data || !data.decision.allowed || gameOver) {
        if (left > 0 && !gameOver) renderError(`ยกเลิกอีก ${left} ขั้นที่รออยู่ เพราะขั้นนี้ไปต่อไม่ได้`);
        return;
      }
    }
    done = true;
  });
  if (!started) renderError("มีคำสั่งกำลังประมวลผลอยู่ รอให้เสร็จก่อนแล้วค่อยกดใหม่");
  return done;
}

function removeLoading() {
  const loading = document.getElementById("activeLoading");
  if (loading) loading.remove();
}

// ============================================================
// 7. RENDER FUNCTIONS
// ============================================================
function renderUser(text) {
  const feed = document.getElementById("chatFeed");
  const div = document.createElement("div");
  div.className = "msg-user";
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

function renderSystem(decision, parsed = null, isRoomLook = false) {
  const feed = document.getElementById("chatFeed");
  const card = document.createElement("div");
  card.className = `msg-system ${decision.allowed ? "" : "denied"} ${isRoomLook ? "room-card" : ""}`;

  const steps = decision.reasoning_chain || [];
  let statusBadge = "";
  if (isRoomLook) {
    statusBadge = `<span class="badge info">📍 สภาพตู้รถปัจจุบัน</span>`;
  } else if (decision.allowed) {
    statusBadge = `<span class="badge allowed">✓ อนุมัติ (ALLOWED)</span>`;
  } else {
    statusBadge = `<span class="badge denied">✗ ปฏิเสธ (DENIED)</span>`;
  }

  const modeLabel = "โหมด B (NeSy Engine)";

  // Reasoning Chain (FE-1 Core)
  let reasoningHtml = "";
  if (steps.length > 0) {
    if (decision.allowed) {
      reasoningHtml = `
        <details class="reasoning-details">
          <summary>🔍 ดูการตรวจกฎ (${steps.length} ขั้น)</summary>
          <div class="rule-table">${renderRules(steps)}</div>
        </details>
      `;
    } else {
      const failed = steps.find(s => !s.passed) || { rule_id: decision.violated_rule_id || "RULE_FAILED", description: decision.message };
      const passed = steps.filter(s => s.passed);

      reasoningHtml = `
        <div class="fail-alert">
          <strong>✗ ไม่ผ่านกฎ: ${escapeHtml(failed.rule_id)}</strong> — ${escapeHtml(failed.description)}
        </div>
        ${passed.length > 0 ? `
          <details class="reasoning-details">
            <summary>ดูขั้นที่ตรวจผ่านมาก่อนหน้า (${passed.length} ขั้น)</summary>
            <div class="rule-table">${renderRules(passed)}</div>
          </details>
        ` : ""}
      `;
    }
  }

  card.innerHTML = `
    <div class="card-header-bar">
      ${statusBadge}
      <span class="mode-tag">${modeLabel}</span>
    </div>
    <div class="story-text">${escapeHtml(decision.message)}</div>
    ${reasoningHtml}
  `;

  feed.appendChild(card);
  feed.scrollTop = feed.scrollHeight;
}

function renderError(message) {
  const feed = document.getElementById("chatFeed");
  const div = document.createElement("div");
  div.className = "msg-error";
  div.innerHTML = `<div>${escapeHtml(message)}</div>`;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

function renderRules(steps) {
  return steps.map(s => `
    <div class="rule-row">
      <span class="rule-status ${s.passed ? 'pass' : 'fail'}">${s.passed ? 'ผ่าน' : 'ไม่ผ่าน'}</span>
      <span class="rule-id">${escapeHtml(s.rule_id.split('_')[0])}</span>
      <span>${escapeHtml(s.description)}</span>
    </div>
  `).join("");
}

function escapeHtml(t) {
  if (!t) return "";
  const div = document.createElement("div");
  div.textContent = t;
  return div.innerHTML;
}

function renderConversationSummary(summaries) {
  for (const summary of summaries) {
    const card = document.createElement('div');
    card.className = 'msg-system conversation-summary';
    card.innerHTML = `<div class="card-header-bar"><strong>ข้อมูลใหม่จาก ${escapeHtml(summary.person)}</strong></div>` +
      '<p>บันทึกจากการสอบปากคำ ไม่ใช่ข้อสรุปว่าใครพูดจริงหรือเป็นคนร้าย</p>' +
      '<ul>' + summary.entries.map(entry => `<li><strong>${escapeHtml(entry.name)}</strong><br>${escapeHtml(entry.description)}</li>`).join('') + '</ul>' +
      '<p>เปิดสมุดคดี → ประเด็นค้าง เพื่อทบทวนสิ่งที่ยังต้องตรวจสอบ</p>';
    document.getElementById('chatFeed').appendChild(card);
  }
}
