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
  if (clockPending) return;
  clockPending = true;
  try {
    const res = await fetch(`${API_BASE}/clock`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(gameState), signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (gameOver) return;
    // Keep action state if a command completed while this clock request was pending.
    if (data.new_state.ending_id) {
      gameState = { ...gameState, ending_id: data.new_state.ending_id,
        elapsed_seconds: data.new_state.elapsed_seconds };
      renderSystem(data.decision, data.parsed);
      showGameOver();
    } else {
      gameState.elapsed_seconds = data.new_state.elapsed_seconds;
      anchorClock();
      deadlineReached = false;
      setBusy(busy);
    }
  } catch (err) {
    // Retry on the next tick; input stays locked at the deadline.
    document.getElementById("clockText").textContent = "00:00 (กำลังยืนยันฉากจบ...)";
  } finally {
    clockPending = false;
  }
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
    anchorClock();
    deadlineReached = false;
    if (clockTimer !== null) clearInterval(clockTimer);
    clockTimer = setInterval(tickClock, 1000);
    timeLimitSeconds = sceneData.time_limit_seconds || 3600;
    locationsMap = sceneData.locations || {};
    suspectsMap = sceneData.suspects || {};
    objectsMap = sceneData.objects || {};
    rulesCount = sceneData.rules_count || null;

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
  const lock = on || gameOver || deadlineReached;
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
  showLoading();
  try {
    if (!gameState) {
      const sRes = await fetch(`${API_BASE}/scene`);
      if (!sRes.ok) throw new Error(`HTTP ${sRes.status}`);
      gameState = (await sRes.json()).initial_state;
    }

    const res = await fetch(`${API_BASE}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, state: gameState }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (gameOver) return null; // Ignore late responses after the deadline closed the case.
    if (data.new_state) gameState = data.new_state;
    anchorClock();
    updateLocationHUD();
    updateClock();
    removeLoading();
    renderSystem(data.decision, data.parsed, opts.isRoomLook);

    // เกมจบแล้วก็คือจบ ไม่ให้พิมพ์ต่อ
    // กล่าวหาผ่านเงื่อนไขแล้วจึงปิดคดี ส่วนคำสั่งที่หลักฐานไม่พอยังเล่นต่อได้
    // หมดเวลาก็ปิดคดีเหมือนกัน ฝั่งกฎเป็นคนใส่ ending_id มาให้ในสถานะ
    // จึงดูที่ ending_id ที่เดียวพอ ไม่ต้องไปจำชื่อกฎข้อไหนไว้ในหน้าเว็บ
    if (gameState && gameState.ending_id) showGameOver();
    return data;
  } catch (err) {
    removeLoading();
    renderError(`⚠️ เชื่อมต่อไม่ได้: ${err.message} กรุณาตรวจสอบสถานะ backend แล้วลองใหม่`);
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
  if (!text) return;

  await locked(async () => {
    renderUser(text);
    input.value = "";
    const data = await submit(text);
    if (!data || gameOver) return;

    // ประโยคที่สั่งหลายอย่างต่อกันถูกตีความเป็น ambiguous พร้อมลิสต์ขั้นตอน
    // ระบบตัดสินได้ทีละคำสั่ง จึงต้องทำเรียงทีละขั้น ไม่ใช่รวดเดียว
    // หน่วยวัดจึงยังเป็น 1 คำสั่ง = 1 คำตัดสิน เหมือนเดิม
    const steps = parseSteps(data.parsed);
    if (steps.length > 1) offerSteps(steps);
  });
}

function showGameOver() {
  if (gameOver) return;   // เรียกซ้ำได้ แต่การ์ดปิดคดีต้องขึ้นครั้งเดียว
  gameOver = true;
  if (clockTimer !== null) clearInterval(clockTimer);
  const input = document.getElementById("chatInput");
  const btn = document.getElementById("sendBtn");
  input.disabled = true;
  btn.disabled = true;
  input.placeholder = "คดีปิดแล้ว";
  document.getElementById("sendBtnText").textContent = "จบเกม";

  const feed = document.getElementById("chatFeed");
  const box = document.createElement("div");
  box.className = "msg-system";
  box.innerHTML =
    `<div class="story-text"><strong>คดีนี้ปิดลงแล้ว</strong><br>` +
    `เรื่องนี้มีฉากจบหลายแบบ ขึ้นอยู่กับว่าคุณชี้ตัวใคร และตอนนั้นมีหลักฐานอยู่ในมือแค่ไหน</div>` +
    `<div class="chips-scroll"><button type="button" class="chip-btn" ` +
    `onclick="location.reload()">เริ่มคดีใหม่</button></div>`;
  feed.appendChild(box);
  feed.scrollTop = feed.scrollHeight;
}

// ============================================================
// คิวคำสั่งพ่วง — แปลง alternatives เป็นลำดับขั้นแล้วทำทีละขั้น
// ============================================================
function parseSteps(parsed) {
  if (!parsed || (parsed.action !== "ambiguous" && parsed.action !== "unknown")) return [];
  return (parsed.alternatives || [])
    .map((a) => {
      const [action, target] = a.split(/\s+/);
      const known = { ...locationsMap, ...objectsMap, ...suspectsMap };
      if (!action || !target || !known[target]) return null;
      return { action, target, label: known[target] };
    })
    .filter(Boolean);
}

// ระบบแยกไม่ออกว่าผู้เล่นหมายถึง "ทำทั้งหมด" หรือ "เลือกอย่างใดอย่างหนึ่ง"
//   "ไปที่ ก แล้วตรวจ ข"  -> ['move ก','examine ข']    ทำทั้งสอง
//   "พาไปห้องอื่นหน่อย"    -> ['move ก','move ข',...]   เลือกอันเดียว
// หน้าตาใน alternatives เหมือนกันทุกอย่าง จึงห้ามเดาแทนผู้เล่น
// ให้เขากดเอง แม่นกว่าเดาผิดแล้วเผาเวลาในเกมทิ้ง
function offerSteps(steps) {
  const feed = document.getElementById("chatFeed");
  const box = document.createElement("div");
  box.className = "msg-system";
  box.innerHTML =
    `<div class="story-text"><strong>คำสั่งนี้ตีความได้ ${steps.length} อย่าง</strong><br>` +
    `เลือกทำทีละอย่าง หรือทำทั้งหมดเรียงตามลำดับ</div>` +
    `<div class="chips-scroll" id="stepChoices"></div>`;
  feed.appendChild(box);

  const wrap = box.querySelector("#stepChoices");
  steps.forEach((st, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip-btn";
    b.textContent = `${i + 1}. ${st.label}`;
    b.onclick = () => { wrap.remove(); runSteps([st]); };
    wrap.appendChild(b);
  });
  const all = document.createElement("button");
  all.type = "button";
  all.className = "chip-btn";
  all.textContent = `▶ ทำทั้งหมด ${steps.length} ขั้นตามลำดับ`;
  all.onclick = () => { wrap.remove(); runSteps(steps); };
  wrap.appendChild(all);

  feed.scrollTop = feed.scrollHeight;
}

// ใช้เส้นทางเดียวกับการพิมพ์เอง จึงได้การล็อก การดักเน็ตหลุด และการปิดหน้าจอตอนคดีปิด
// มาเหมือนกันทั้งหมด โดยไม่ต้องเขียนซ้ำ
async function runSteps(steps) {
  const started = await locked(async () => {
    for (const [i, st] of steps.entries()) {
      renderUser(steps.length > 1 ? `(ขั้นที่ ${i + 1}) ${st.label}` : st.label);
      const data = await submit(`${st.action} ${st.target}`);
      const left = steps.length - i - 1;

      // ขั้นถัดไปตั้งอยู่บนสมมติฐานว่าขั้นนี้สำเร็จ ทำต่อไปก็ผิดยกแถว
      // คดีปิดกลางทางก็หยุดเหมือนกัน ที่เหลือไม่มีความหมายแล้ว
      if (!data || !data.decision.allowed || gameOver) {
        if (left > 0) renderError(`ยกเลิกอีก ${left} ขั้นที่รออยู่ เพราะขั้นนี้ไปต่อไม่ได้`);
        return;
      }
    }
  });
  if (!started) renderError("มีคำสั่งกำลังประมวลผลอยู่ รอให้เสร็จก่อนแล้วค่อยกดใหม่");
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
