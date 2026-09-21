/**
 * NeSy-Escape: Complete Controller & UI Manager (Victorian Dark Luxury Noir Theme)
 */

const API_BASE = window.location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";

let gameState = null;
let timeLimitSeconds = 3600;
let locationsMap = {};
let suspectsMap = {};
let objectsMap = {};
let rulesCount = null;
let gameOver = false;
let busy = false;
let clockTimer = null;
let clockPending = false;
let deadlineReached = false;
let clockAnchor = null;
let clockElapsed = 0;

function anchorClock() {
  clockElapsed = gameState?.elapsed_seconds || 0;
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
    document.getElementById("clockText").textContent = "00:00 (หมดเวลา)";
  } finally {
    clockPending = false;
  }
}

// ============================================================
// 1. INIT GAME & SCREEN SWITCHING
// ============================================================
let pendingSceneData = null;

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
    pendingSceneData = sceneData;

    if (sceneData.briefing) {
      const bText = document.getElementById("modalBriefingText");
      if (bText) bText.textContent = sceneData.briefing;
    }
    if (sceneData.prologue) {
      const pArr = document.getElementById("prologueArrival");
      const pBlk = document.getElementById("prologueBlackout");
      const pDis = document.getElementById("prologueDiscovery");
      if (pArr && sceneData.prologue.arrival) pArr.textContent = sceneData.prologue.arrival;
      if (pBlk && sceneData.prologue.blackout) pBlk.textContent = sceneData.prologue.blackout;
      if (pDis && sceneData.prologue.discovery) pDis.textContent = sceneData.prologue.discovery;
    }

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

async function startGameInvestigation() {
  const wScreen = document.getElementById("welcomeScreen");
  const gWorkspace = document.getElementById("gameWorkspace");
  if (wScreen) wScreen.style.display = "none";
  if (gWorkspace) gWorkspace.style.display = "flex";

  if (!pendingSceneData) return;

  gameState = pendingSceneData.initial_state;
  anchorClock();
  deadlineReached = false;
  if (clockTimer !== null) clearInterval(clockTimer);
  clockTimer = setInterval(tickClock, 1000);
  timeLimitSeconds = pendingSceneData.time_limit_seconds || 3600;
  locationsMap = pendingSceneData.locations || {};
  suspectsMap = pendingSceneData.suspects || {};
  objectsMap = pendingSceneData.objects || {};
  rulesCount = pendingSceneData.rules_count || null;

  updateLocationHUD();
  updateClock();
  updateCaseBoardProgress();

  const feed = document.getElementById("chatFeed");
  feed.innerHTML = "";
  renderBriefing(pendingSceneData.briefing);

  await executeInitialLookAround();
}

function renderBriefing(briefingText) {
  const feed = document.getElementById("chatFeed");
  const card = document.createElement("div");
  card.className = "msg-system";
  card.innerHTML = `
    <div class="card-header-bar">
      <span class="badge info">📋 บรีฟคดี (Case Briefing)</span>
      <span class="mode-tag">Nocturne Express 1938</span>
    </div>
    <div class="story-text">${escapeHtml(briefingText)}</div>
    
    <div class="hints-box">
      <div class="hints-title">💡 ตัวอย่างคำสั่งที่พิมพ์ได้ในเกม:</div>
      <div class="hints-list">
        <div>• <code>ดูรอบๆ</code> — สำรวจตู้รถที่ยืนอยู่และดูสิ่งที่มองเห็นได้</div>
        <div>• <code>ไปที่ตู้เสบียง</code> — เดินทางไปยังตู้เสบียงหรือตู้รถอื่น</div>
        <div>• <code>ตรวจดูนาฬิกาพกของผู้ตาย</code> — ตรวจสอบวัตถุหรือหลักฐานในห้อง</div>
        <div>• <code>สอบปากคำ กิเดียน ฮาร์ต</code> — พูดคุยกับพยานหรือผู้ต้องสงสัย</div>
        <div>• <code>กล่าวหากิเดียน ฮาร์ต</code> — กล่าวหาผู้สงสัยเมื่อมีหลักฐานมัดตัวครบ</div>
      </div>
    </div>
  `;
  feed.appendChild(card);
}

function executeInitialLookAround() {
  return locked(() => submit("ดูรอบๆ", { isRoomLook: true }));
}

// ============================================================
// 2. HUD & TRAIN MAP & CASE BOARD UPDATES
// ============================================================
function updateLocationHUD() {
  const locText = document.getElementById("locText");
  if (!locText || !gameState) return;
  const locId = gameState.current_location || "lounge_car";
  
  let locObj = locationsMap[locId];
  let locName = typeof locObj === "object" ? locObj.name_th : locObj;
  locText.textContent = locName || locId;

  // Highlight active car button in train blueprint map
  document.querySelectorAll(".train-car-btn").forEach(btn => btn.classList.remove("active"));
  const activeBtn = document.getElementById(`car_${locId}`);
  if (activeBtn) activeBtn.classList.add("active");
}

function selectTrainCar(carId) {
  if (busy || gameOver) return;
  let locObj = locationsMap[carId];
  let carName = typeof locObj === "object" ? locObj.name_th : (locObj || carId);
  
  // Strip car number prefix if present
  carName = carName.replace(/^ตู้\s*\d+:\s*/, "");

  fillInput(`ไปที่${carName}`);
}

function updateClock() {
  const clockText = document.getElementById("clockText");
  const clockWidget = document.getElementById("clockWidget");
  const timeSpentText = document.getElementById("timeSpentText");
  if (!clockText || !clockWidget) return;

  const elapsed = elapsedNow();
  const remaining = Math.max(0, timeLimitSeconds - elapsed);
  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;

  clockText.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  if (timeSpentText) timeSpentText.textContent = `${elapsed} วินาที`;

  if (remaining <= 0) {
    clockWidget.className = "nav-badge clock-badge danger";
    clockText.textContent = "00:00 (หมดเวลา)";
  } else if (remaining <= 600) {
    clockWidget.className = "nav-badge clock-badge danger";
  } else if (remaining <= 1200) {
    clockWidget.className = "nav-badge clock-badge warning";
  } else {
    clockWidget.className = "nav-badge clock-badge";
  }
}

function updateCaseBoardProgress() {
  if (!gameState) return;

  // 1. Clues Found
  const cluesCount = (gameState.discovered_evidence || []).length || (gameState.inventory || []).length || 3;
  const totalClues = 42;
  const cluesPercent = Math.min(100, Math.round((cluesCount / totalClues) * 100));
  const cBar = document.getElementById("progressCluesBar");
  const cText = document.getElementById("progressCluesText");
  if (cBar) cBar.style.width = `${cluesPercent}%`;
  if (cText) cText.textContent = `${cluesCount} / ${totalClues}`;

  // 2. Suspects Interrogated
  const interviewedCount = (gameState.interviewed_suspects || []).length || 1;
  const totalSuspects = 3;
  const sPercent = Math.min(100, Math.round((interviewedCount / totalSuspects) * 100));
  const sBar = document.getElementById("progressSuspectsBar");
  const sText = document.getElementById("progressSuspectsText");
  if (sBar) sBar.style.width = `${sPercent}%`;
  if (sText) sText.textContent = `${interviewedCount} / ${totalSuspects}`;

  // 3. Locations Visited
  const visitedCount = (gameState.visited_locations || []).length || 1;
  const totalLocs = 6;
  const lPercent = Math.min(100, Math.round((visitedCount / totalLocs) * 100));
  const lBar = document.getElementById("progressLocsBar");
  const lText = document.getElementById("progressLocsText");
  if (lBar) lBar.style.width = `${lPercent}%`;
  if (lText) lText.textContent = `${visitedCount} / ${totalLocs}`;

  // 4. Questions Solved
  const solvedCount = (gameState.deductions || []).length || 0;
  const totalQuestions = 4;
  const qPercent = Math.min(100, Math.round((solvedCount / totalQuestions) * 100));
  const qBar = document.getElementById("progressQuestionsBar");
  const qText = document.getElementById("progressQuestionsText");
  if (qBar) qBar.style.width = `${qPercent}%`;
  if (qText) qText.textContent = `${solvedCount} / ${totalQuestions}`;
}

// NOTEBOOK TABS SWITCHING
function switchNotebookTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(content => content.style.display = "none");

  if (tabName === 'evidence') {
    document.getElementById("tabEvidenceBtn")?.classList.add("active");
    const tabEl = document.getElementById("tabEvidence");
    if (tabEl) tabEl.style.display = "flex";
  } else if (tabName === 'suspects') {
    document.getElementById("tabSuspectsBtn")?.classList.add("active");
    const tabEl = document.getElementById("tabSuspects");
    if (tabEl) tabEl.style.display = "flex";
  } else if (tabName === 'notes') {
    document.getElementById("tabNotesBtn")?.classList.add("active");
    const tabEl = document.getElementById("tabNotes");
    if (tabEl) tabEl.style.display = "flex";
  }
}

// ============================================================
// 3. COMMAND INPUT & LOCKING
// ============================================================
function fillInput(text) {
  const input = document.getElementById("chatInput");
  if (!input) return;
  input.value = text;
  input.focus();
}

function setBusy(on) {
  busy = on;
  const input = document.getElementById("chatInput");
  const btn = document.getElementById("sendBtn");
  const btnText = document.getElementById("sendBtnText");
  if (!input || !btn) return;
  const lock = on || gameOver || deadlineReached;
  input.disabled = lock;
  btn.disabled = lock;
  if (btnText) btnText.textContent = gameOver ? "คดีปิดแล้ว" : (on ? "กำลังประมวลผล..." : "ส่งคำสั่ง");
  if (!lock) input.focus();
}

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

    if (gameOver) return null;
    if (data.new_state) gameState = data.new_state;
    anchorClock();
    updateLocationHUD();
    updateClock();
    updateCaseBoardProgress();
    removeLoading();
    renderSystem(data.decision, data.parsed, opts.isRoomLook);

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
    <span>NeSy Engine กำลังตีความคำสั่งและตรวจสอบกฎ...</span>
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

    const steps = parseSteps(data.parsed);
    if (steps.length > 1) offerSteps(steps);
  });
}

function showGameOver() {
  if (gameOver) return;
  gameOver = true;
  if (clockTimer !== null) clearInterval(clockTimer);
  const input = document.getElementById("chatInput");
  const btn = document.getElementById("sendBtn");
  if (input) input.disabled = true;
  if (btn) btn.disabled = true;
  if (input) input.placeholder = "คดีปิดแล้ว";
  const bText = document.getElementById("sendBtnText");
  if (bText) bText.textContent = "จบเกม";

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

async function runSteps(steps) {
  const started = await locked(async () => {
    for (const [i, st] of steps.entries()) {
      renderUser(steps.length > 1 ? `(ขั้นที่ ${i + 1}) ${st.label}` : st.label);
      const data = await submit(`${st.action} ${st.target}`);
      const left = steps.length - i - 1;
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
// 4. RENDER FUNCTIONS
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

  const modeLabel = "NeSy Engine";

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

