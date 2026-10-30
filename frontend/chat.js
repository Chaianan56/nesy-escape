/**
 * frontend/chat.js — ตัวควบคุมการสื่อสารและจัดการหน้าจอหลัก (Main Game Controller & UI Manager)
 * 
 * หน้าที่หลัก:
 * 1. รับและส่งคำสั่งภาษาไทยของผู้เล่นผ่าน POST /command ไปยังเซิร์ฟเวอร์
 * 2. จัดการนาฬิกาคดี (Investigation Clock) ตรวจจับการหมดเวลาและส่งคำสั่ง /clock
 * 3. แสดงผลคำตัดสินของกฎ (ALLOWED / DENIED) พร้อมสายธารเหตุผล (Explainable Reasoning Chain)
 * 4. จัดการคำสั่งต่อเนื่อง (Sequence Step-by-Step Playback) และคำสั่งกำกวม (Ambiguous Choices)
 * 5. อัปเดตสถานะการเชื่อมต่อ Gemini API (Key Status & Fallback Badge)
 * 6. ซิงโครไนซ์สถานะเกม (GameState) กับส่วนประกอบ UI อื่นๆ (PixelUI, GameArt, NovelUI, StoryScenes)
 */

// ใช้ origin เดียวกับหน้าเว็บ เพราะ FastAPI เสิร์ฟทั้ง API และไฟล์หน้าเว็บ
// ถ้าฝัง 127.0.0.1 ไว้ พอขึ้นคลาวด์เบราว์เซอร์จะยิงกลับไปที่เครื่องผู้ใช้เอง ไม่ใช่เซิร์ฟเวอร์
// เปิดไฟล์ตรงๆ ด้วย file:// ค่อยถอยไปใช้ localhost
const API_BASE = window.location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";

let gameState = null;
let timeLimitSeconds = 5400;
let locationsMap = {};
let suspectsMap = {};
let accusableSuspects = null;
let suspectLocations = {};
let restrictedLocations = [];
let objectsMap = {};
let rulesCount = null;
let gameOver = false;   // ปิดคดีแล้วหรือหมดเวลาแล้ว ห้ามรับคำสั่งอีก
let busy = false;       // มีคำสั่งค้างอยู่ในสาย ห้ามส่งซ้อน
let clockTimer = null;
let sessionMonitorTimer = null;
let sessionCheckPending = false;
let serverSessionId = null;
let clockPending = false;
let deadlineReached = false;
let clockFailures = 0;
let clockAnchor = null;
let clockElapsed = 0;
// อัปเดตป้ายบอกคดีและ Dev Route Indicator บน Header
let currentCaseId = null;
function updateCaseEdition(caseId) {
  if (caseId) currentCaseId = caseId;
  const targetId = currentCaseId || caseId || (typeof gameState !== "undefined" && gameState?.case_id) || "case_01_gideon";
  const el = document.getElementById("caseEdition") || document.querySelector(".edition");
  if (!el) return;
  const mapping = {
    "case_01_gideon": { letter: "A", label: "Route A: The Burnt Dossier" },
    "case_02_vincent": { letter: "B", label: "Route B: The Strike in the Dark" },
    "case_03_liora": { letter: "C", label: "Route C: The Doctor's Retribution" }
  };
  const info = mapping[targetId] || { letter: "A", label: "Route A" };
  el.textContent = `แฟ้มคดี  /  01 [${info.letter}]`;
  el.title = `Active Route: ${info.label} (${targetId})`;
}
if (typeof window !== "undefined") window.updateCaseEdition = updateCaseEdition;

let latestProfile = null;

function updateProfilerHUD(profile) {
  if (!profile) return;
  latestProfile = profile;
  const pill = document.getElementById("profilerWidget");
  const icon = document.getElementById("profilerIcon");
  const label = document.getElementById("profilerText");
  if (icon) icon.textContent = profile.archetype_badge || "⚖️";
  if (label) label.textContent = profile.archetype_name_th || "นักสืบสายสมดุล";
  if (pill) {
    const dimensions = profile.dimensions || {};
    pill.title = `${profile.archetype_name_th || "นักสืบสายสมดุล"} · ความรอบคอบ ${Math.round((dimensions.methodical_score || 0) * 100)}% · ความเคารพกฎ ${Math.round((dimensions.caution_score ?? 1) * 100)}%`;
  }
  const statBadge = document.getElementById("profilerStatBadge");
  const statLabel = document.getElementById("profilerStatLabel");
  if (statBadge) statBadge.textContent = profile.archetype_badge || "⚖️";
  if (statLabel) statLabel.textContent = profile.archetype_name_th || "นักสืบสายสมดุล";
}

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
    if (data.profile) updateProfilerHUD(data.profile);
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

// The backend keeps games in memory. If it restarts while this tab is open,
// /scene creates a fresh session for the stale cookie; reload into that case.
async function checkServerSession() {
  if (!serverSessionId || sessionCheckPending) return;
  sessionCheckPending = true;
  try {
    const response = await fetch(`${API_BASE}/scene`, { signal: AbortSignal.timeout(4000) });
    if (!response.ok) return;
    const scene = await response.json();
    const nextSessionId = scene.initial_state?.session_id;
    if (nextSessionId && nextSessionId !== serverSessionId) {
      serverSessionId = nextSessionId;
      window.location.reload();
    }
  } catch {
    // The server may be temporarily offline. Check again on the next interval.
  } finally {
    sessionCheckPending = false;
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
    if (sceneData.api_status) updateApiStatus(sceneData.api_status);
    if (sceneData.profile) updateProfilerHUD(sceneData.profile);
    if (sceneData.case_id) updateCaseEdition(sceneData.case_id);
    serverSessionId = gameState.session_id || null;
    timeLimitSeconds = sceneData.time_limit_seconds || 5400;
    if (sessionMonitorTimer !== null) clearInterval(sessionMonitorTimer);
    sessionMonitorTimer = setInterval(checkServerSession, 5000);
    if (gameState.started_at == null && !gameState.ending_id) {
      if (sceneData.opening_scene && typeof StoryScenes !== 'undefined') {
        await StoryScenes.play(sceneData.opening_scene, {mode:'opening'});
      } else if (typeof NovelUI !== 'undefined') {
        await NovelUI.intro(sceneData.briefing);
      }
      const started = await fetch(`${API_BASE}/start`, {method:'POST'});
      if (!started.ok) throw Error(`HTTP ${started.status}`);
      gameState = (await started.json()).new_state;
    }
    anchorClock();
    deadlineReached = false;
    if (clockTimer !== null) clearInterval(clockTimer);
    clockTimer = setInterval(tickClock, 1000);
    locationsMap = sceneData.locations || {};
    suspectsMap = sceneData.suspects || {};
    accusableSuspects = sceneData.accusable_suspects || Object.keys(suspectsMap);
    suspectLocations = sceneData.suspect_locations || {};
    restrictedLocations = sceneData.restricted_locations || [];
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
      <span class="mode-tag">คดีบนรถด่วน Nocturne Express · 1938</span>
    </div>
    <div class="story-text">${escapeHtml(briefingText)}</div>
    
    <div class="hints-box">
      <div class="hints-title">💡 ตัวอย่างคำสั่งที่พิมพ์ได้ในเกม:</div>
      <div class="hints-list">
        <div>• <code>ดูรอบๆ</code> — สำรวจตู้รถที่ยืนอยู่และดูสิ่งที่มองเห็นได้</div>
        <div>• <code>ไปตู้ 4</code> — ไปยังห้องพักของแคสเซียน ซึ่งเป็นที่เกิดเหตุ</div>
        <div>• <code>ตรวจนาฬิกาพกกลไก</code> — ตรวจหลักฐานที่มองเห็นในตู้</div>
        <div>• <code>สอบปากคำกิเดียน</code> — คุยกับพยานหรือผู้ต้องสงสัยที่อยู่ในตู้เดียวกัน</div>
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
  const status = document.getElementById("sceneStatus");
  if (status && !gameState.ending_id) status.textContent = `เป้าหมาย: ${nextObjective(gameState)}`;
}

// ชี้ขั้นต่อไปจากสิ่งที่ผู้เล่นทำไปแล้วเท่านั้น ไม่ดูหลักฐานหรือข้อสรุป จึงไม่เฉลยตัวคนร้าย
function nextObjective(state) {
  const car = id => (locationsMap[id] || id).split(":")[0];
  const visited = state.visited_locations || [];
  const talked = state.interrogated_suspects || [];
  if (!visited.includes("first_class_car")) return "ไปดูที่เกิดเหตุ · พิมพ์ ไปตู้ 4";
  const left = Object.keys(suspectsMap).filter(id => !talked.includes(id));
  left.sort((a, b) => (suspectLocations[b] === state.current_location) - (suspectLocations[a] === state.current_location));
  if (left.length) {
    const id = left[0];
    const place = car(suspectLocations[id]);
    if (id === "gideon_hart") return `ยังไม่ได้คุยกับกิเดียน ฮาร์ต (${place})`;
    if (id === "dr_liora_venn") return `ยังไม่ได้คุยกับแพทย์ประจำขบวน (${place})`;
    if (id === "car_attendant") return `ยังไม่ได้คุยกับพนักงานตู้เสบียง (${place})`;
    if (id === "patient_witness") return `ยังไม่ได้คุยกับผู้ป่วย (${place})`;
    return `ยังไม่ได้คุยกับผู้โดยสาร (${place})`;
  }
  const unseen = Object.keys(locationsMap).filter(id => !visited.includes(id) && !restrictedLocations.includes(id));
  if (unseen.length) return `ยังไม่ได้สำรวจ ${unseen.map(car).join(", ")}`;
  return "ตรวจของที่เหลือ แล้วเทียบในสมุดคดี · พร้อมแล้วพิมพ์ กล่าวหา ตามด้วยชื่อ";
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

function renderParserModeTag(parsed) {
  if (!parsed?.parser_mode) return '';
  if (parsed.parser_mode === 'typed') {
    return `<span class="parser-mode-tag fast">⚡ Fast-Path (&lt;1ms)</span>`;
  }
  if (parsed.parser_mode === 'fallback') {
    return `<span class="parser-mode-tag fallback">⚠️ Offline Fallback</span>`;
  }
  const latency = parsed.latency_ms != null ? parsed.latency_ms.toFixed(1) + 'ms' : '~3000ms';
  return `<span class="parser-mode-tag neural">🧠 Neural Few-Shot (${latency})</span>`;
}

function updateApiStatus(info) {
  if (!info) return;
  const statusText = document.getElementById("apiStatusText");
  const keyBadge = document.getElementById("apiKeyBadge");
  const dot = document.getElementById("apiStatusDot");
  const widget = document.getElementById("apiStatusWidget");
  if (statusText) statusText.textContent = info.message || (info.online ? "พร้อมใช้งาน" : "ออฟไลน์");
  if (keyBadge) {
    keyBadge.textContent = info.key_label || (info.active_key ? `Key ${info.active_key}` : "Key 1");
    keyBadge.classList.remove("key-error", "key-warning");
    if (info.status === 'quota_exceeded') {
      keyBadge.classList.add("key-warning");
    } else if (info.online === false) {
      keyBadge.classList.add("key-error");
    }
  }
  if (dot) {
    if (info.status === 'quota_exceeded') {
      dot.style.background = "#e58e26";
    } else if (info.online === false) {
      dot.style.background = "#d8a18d";
    } else {
      dot.style.background = "var(--green, #68ba82)";
    }
  }
  if (widget) {
    const detail = info.error_detail ? ` • ${info.error_detail}` : '';
    widget.title = `Gemini API: ${info.message || 'พร้อมใช้งาน'} · กำลังใช้งาน ${info.key_label || 'Key 1'}${info.total_keys ? ` (มีทั้งหมด ${info.total_keys} คีย์)` : ''}${detail}`;
  }
}

// ============================================================
// 4. ตัวอย่างคำสั่ง (Quick Chips Fill)
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

// ============================================================
// RPG-Style Sequential Playback Controller
// จัดการการเล่นทีละขั้นตอน (Step-by-step playback) พร้อมซิงค์ฉากและแผนที่
// ============================================================
const SequencePlayback = (() => {
  let active = false;
  let steps = [];
  let currentIndex = 0;
  let currentData = null;
  let resolvePromise = null;

  function isPlaying() {
    return active;
  }

  function play(data) {
    if (!data.sequence_steps || data.sequence_steps.length <= 1) return Promise.resolve();
    if (typeof window !== 'undefined' && typeof window.showDialogue === 'function') window.showDialogue();
    return new Promise((resolve) => {
      active = true;
      steps = data.sequence_steps;
      currentIndex = 0;
      currentData = data;
      resolvePromise = resolve;

      const panel = document.querySelector(".dialogue-panel");
      if (panel) panel.classList.add("seq-active");

      // ล็อกช่องพิมพ์ระหว่างเล่นทีละก้าว
      const chatInput = document.getElementById("chatInput");
      const sendBtn = document.getElementById("sendBtn");
      if (chatInput) chatInput.disabled = true;
      if (sendBtn) sendBtn.disabled = true;

      // ติดตั้งตัวตรวจจับการคลิกที่กล่องบทสนทนาเพื่อไปต่อ
      const feed = document.getElementById("chatFeed");
      if (feed && !feed.__hasSeqAdvanceListener) {
        feed.__hasSeqAdvanceListener = true;
        feed.addEventListener("click", (e) => {
          if (!active) return;
          // ไม่ข้ามถ้ากำลังลากครอบตัวหนังสือเพื่อก๊อปปี้
          if (window.getSelection && window.getSelection().toString().trim().length > 0) return;
          // ไม่ข้ามถ้ากดปุ่มหรือลิงก์ภายใน
          if (e.target.closest("button, a, input, select, summary")) return;
          next();
        });
      }

      // แสดง Step แรก
      renderCurrentStep();
    });
  }

  function buildStepCard(step, isLast, isActive) {
    const card = document.createElement("div");
    card.className = `msg-system seq-step-card ${isActive ? "active-step " : ""}${step.allowed ? "" : "denied-step"}`;

    const actionName = VERB_TH[step.action] || step.action;
    const targetName = (objectsMap && objectsMap[step.target]) 
                    || (suspectsMap && suspectsMap[step.target]) 
                    || (locationsMap && locationsMap[step.target]) 
                    || step.target;

    const parsed = currentData?.parsed;
    const modeTag = renderParserModeTag(parsed);

    const stepRepair = step.repair_note || (step.reasoning_chain?.some(r => r.rule_id === "SYMBOLIC_REPAIR") ? "Neuro-Symbolic Constraint Repair: ปรับเป้าหมายให้สอดคล้องกับวัตถุที่มีอยู่ในห้อง" : null) || (isLast ? parsed?.repair_note : null);
    const repairBanner = stepRepair ? `
      <div class="nesy-repair-banner">
        <span class="nesy-icon">⚡</span>
        <div class="nesy-repair-content">
          <strong>Neuro-Symbolic Constraint Repair</strong>
          <span>${escapeHtml(stepRepair)}</span>
        </div>
      </div>` : '';

    const stepsChain = step.reasoning_chain || [];
    let reasoningHtml = "";
    if (stepsChain.length > 0) {
      if (step.allowed) {
        reasoningHtml = `
          <details class="reasoning-details">
            <summary>🔍 ดูการตรวจกฎ (${stepsChain.length} ขั้น)</summary>
            <div class="rule-table">${renderRules(stepsChain)}</div>
          </details>
        `;
      } else {
        const failed = stepsChain.find(s => !s.passed) || { rule_id: step.violated_rule_id || "RULE_FAILED", description: step.message };
        const passed = stepsChain.filter(s => s.passed);

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

    let extraContent = "";
    if (step.action === "interrogate" && currentData?.conversation_summaries?.length) {
      const matching = currentData.conversation_summaries.filter(s => s.suspect_id === step.target);
      if (matching.length) {
        extraContent = matching.map(summary => `
          <div class="step-testimony-box" style="margin-top:10px;padding:10px;background:#1e271d;border:1px solid #4a5944;border-radius:4px;">
            <strong style="color:#d9b775;">📋 ข้อมูลใหม่จาก ${escapeHtml(summary.person)}</strong>
            <div style="font-size:11px;color:#a9ad9c;margin:4px 0 6px;">บันทึกจากการสอบปากคำ ไม่ใช่ข้อสรุปว่าใครพูดจริงหรือเป็นคนร้าย</div>
            <ul style="margin:0;padding-left:18px;">${summary.entries.map(e => `<li><strong style="color:#e4dfcc;">${escapeHtml(e.name)}</strong>: <span style="color:#c9c5b5;">${escapeHtml(e.description)}</span></li>`).join("")}</ul>
          </div>
        `).join("");
      }
    }

    const advanceHintHtml = isActive
      ? (isLast
          ? `<div class="seq-advance-hint finish"><span>ขั้นตอนสุดท้าย · คลิกเพื่อจบ</span> <span class="blink-arrow">✓</span></div>`
          : `<div class="seq-advance-hint"><span>คลิกเพื่อไปต่อ</span> <span class="blink-arrow">▼</span></div>`)
      : "";

    card.innerHTML = `
      <div class="card-header-bar seq-step-header">
        <div style="display:flex;align-items:center;gap:8px;">
          <span class="seq-step-badge ${step.allowed ? "" : "denied"}">${step.allowed ? "สำเร็จ ✓" : "ไม่สำเร็จ ✗"}</span>
          <span class="seq-step-num">ขั้นตอนที่ ${step.step_index} / ${steps.length}: ${escapeHtml(actionName)} ${escapeHtml(targetName || "")}</span>
        </div>
        <div class="card-meta-tags">
          ${modeTag}
          <span class="mode-tag">โหมด B (NeSy Engine)</span>
        </div>
      </div>
      <div class="seq-step-body">${escapeHtml(step.message)}</div>
      ${repairBanner}
      ${reasoningHtml}
      ${extraContent}
      ${advanceHintHtml}
    `;
    return card;
  }

  function renderCurrentStep() {
    if (!active || currentIndex >= steps.length) {
      finish();
      return;
    }

    const step = steps[currentIndex];
    const isLast = currentIndex === steps.length - 1;

    // 1. ซิงค์ภาพฉากตามตำแหน่งและแอ็กชันของ Step ปัจจุบัน
    if (typeof GameArt !== "undefined" && typeof GameArt.setStepScene === "function") {
      GameArt.setStepScene(step.action, step.target, step.location);
    }

    // 2. ซิงค์ HUD และแผนที่รถไฟแบบเจาะจง
    const locText = document.getElementById("locText");
    if (locText && step.location) {
      locText.textContent = locationsMap[step.location] || step.location;
    }
    if (step.location) {
      document.querySelectorAll(".train-cars .car").forEach(c => {
        c.classList.toggle("active", c.dataset.location === step.location);
      });
    }

    // 3. แสดงการ์ด Step ลงในกล่องบทสนทนา พร้อมคำแนะนำคลิกเพื่อไปต่อ
    const feed = document.getElementById("chatFeed");
    if (feed) {
      feed.querySelectorAll(".seq-step-card").forEach(c => {
        c.classList.remove("active-step");
        c.classList.add("history-older");
        const oldHint = c.querySelector(".seq-advance-hint");
        if (oldHint) oldHint.remove();
      });

      const card = buildStepCard(step, isLast, true);
      feed.appendChild(card);
      feed.scrollTop = feed.scrollHeight;
    }
  }

  function next() {
    if (!active) return;
    if (currentIndex < steps.length - 1) {
      currentIndex++;
      renderCurrentStep();
    } else {
      finish();
    }
  }

  function skip() {
    if (!active) return;
    const feed = document.getElementById("chatFeed");
    for (let i = currentIndex + 1; i < steps.length; i++) {
      const step = steps[i];
      const isLast = i === steps.length - 1;
      if (feed) {
        feed.querySelectorAll(".seq-step-card").forEach(c => {
          c.classList.remove("active-step");
          c.classList.add("history-older");
          const oldHint = c.querySelector(".seq-advance-hint");
          if (oldHint) oldHint.remove();
        });
        const card = buildStepCard(step, isLast, false);
        feed.appendChild(card);
      }
    }
    const lastStep = steps[steps.length - 1];
    if (typeof GameArt !== "undefined" && typeof GameArt.setStepScene === "function" && lastStep) {
      GameArt.setStepScene(lastStep.action, lastStep.target, lastStep.location);
    }
    if (feed) feed.scrollTop = feed.scrollHeight;
    finish();
  }

  function finish() {
    if (!active) return;
    active = false;

    const panel = document.querySelector(".dialogue-panel");
    if (panel) panel.classList.remove("seq-active");

    // ปลดคลาส active และเคลียร์คำแนะนำคลิกทั้งหมด พร้อมซ่อนขั้นตอนก่อนหน้าในหน้าหลัก
    const feed = document.getElementById("chatFeed");
    if (feed) {
      const allSteps = feed.querySelectorAll(".seq-step-card");
      allSteps.forEach((c, idx) => {
        c.classList.remove("active-step");
        const oldHint = c.querySelector(".seq-advance-hint");
        if (oldHint) oldHint.remove();
        if (idx < allSteps.length - 1) {
          c.classList.add("history-older");
        }
      });
    }

    if (currentData) {
      if (currentData.new_state) gameState = currentData.new_state;
      if (typeof GameArt !== "undefined") GameArt.onResult(currentData);
      if (typeof PixelUI !== "undefined") PixelUI.refresh();
      updateLocationHUD();
    }

    const chatInput = document.getElementById("chatInput");
    const sendBtn = document.getElementById("sendBtn");
    if (chatInput) {
      chatInput.disabled = false;
      chatInput.focus();
    }
    if (sendBtn) sendBtn.disabled = false;

    if (resolvePromise) {
      const res = resolvePromise;
      resolvePromise = null;
      res();
    }
  }

  return { play, next, skip, isPlaying };
})();

if (typeof window !== "undefined") {
  window.SequencePlayback = SequencePlayback;
  window.addEventListener("keydown", (e) => {
    if (SequencePlayback && SequencePlayback.isPlaying()) {
      if (e.key === " " || e.key === "Enter") {
        const activeEl = document.activeElement;
        if (!activeEl || activeEl.tagName !== "INPUT" || activeEl.disabled) {
          e.preventDefault();
          SequencePlayback.next();
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        SequencePlayback.skip();
      }
    }
  });
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
  if (typeof window !== 'undefined' && typeof window.showDialogue === 'function') {
    window.showDialogue();
  }
  try {
    if (!gameState) {
      const sRes = await fetch(`${API_BASE}/scene`);
      if (!sRes.ok) throw new Error(`HTTP ${sRes.status}`);
      gameState = (await sRes.json()).initial_state;
    }

    const res = await fetch(`${API_BASE}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, ...(opts.submittedEvidence ? {submitted_evidence: opts.submittedEvidence} : {}) }),
      signal: AbortSignal.timeout(25000), // longer than the server's 20s Gemini budget
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
    if (data.profile) updateProfilerHUD(data.profile);
    if (data.api_status) updateApiStatus(data.api_status);
    if (typeof window !== 'undefined' && typeof window.showDialogue === 'function') {
      window.showDialogue();
    } else if (typeof document.querySelector === 'function') {
      const dialoguePanel = document.querySelector('.dialogue-panel');
      const showBtn = document.getElementById('showDialogueBtn');
      if (dialoguePanel) {
        dialoguePanel.classList.remove('is-hidden');
        dialoguePanel.style.removeProperty('display');
      }
      if (showBtn) {
        showBtn.setAttribute('hidden', '');
        showBtn.hidden = true;
        showBtn.style.removeProperty('display');
        showBtn.style.setProperty('display', 'none', 'important');
      }
    }
    anchorClock();
    updateLocationHUD();
    updateClock();
    removeLoading();
    if (gameState?.ending_id) { showGameOver(data.decision); return data; }
    let askInference = false;
    if (data.parsed?.action === 'infer' && !opts.submittedEvidence && !data.decision.allowed
        && typeof InferenceUI !== 'undefined') {
      const response = await fetch(`${API_BASE}/journal`, {method:'POST', signal: AbortSignal.timeout(8000)});
      if (!response.ok) throw Error(`HTTP ${response.status}`);
      const journal = await response.json();
      const question = (journal.inference_questions || []).find(q => q.choices.some(c => c.target === data.parsed.target));
      if (question && !gameOver) { InferenceUI.open(question, journal.evidence); askInference = true; }
    }

    // กรณีคำสั่งพ่วง (Sequence) มีหลายขั้นตอน ให้แสดงผลทีละก้าวแบบ RPG Playback
    if (!askInference && data.sequence_steps && data.sequence_steps.length > 1) {
      await SequencePlayback.play(data);
    } else {
      // คำสั่งพ่วงไม่ต้องโชว์การ์ด "กำกวม" ของตัวมันเอง เดี๋ยวแต่ละขั้นมีการ์ดของตัวเอง
      if (!askInference && !(data.parsed?.sequence && data.parsed.alternatives?.length)) renderSystem(data.decision, data.parsed, opts.isRoomLook);
      renderConversationSummary(data.conversation_summaries || []);
      if (typeof GameArt !== 'undefined') GameArt.onResult(data);
      if (typeof PixelUI !== 'undefined') PixelUI.refresh();
      if (data.decision.allowed && data.narrative_scene && typeof StoryScenes !== 'undefined') {
        if (typeof NovelUI !== 'undefined') NovelUI.close();
        StoryScenes.appendReplay(data.narrative_scene);
        await StoryScenes.play(data.narrative_scene);
      } else if (typeof NovelUI !== 'undefined') NovelUI.onResult(data);
    }

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
    <span>กำลังตรวจสอบคำสั่งและข้อมูลในคดี…</span>
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
    const res = await fetch(`${API_BASE}/new-game`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ random: true }),
    });
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
  if (typeof StoryScenes !== 'undefined') StoryScenes.stop();
  if (typeof NovelUI !== 'undefined') NovelUI.close();
  setBusy(false);
  updateClock();
  document.getElementById('chatInput').placeholder = 'คดีปิดแล้ว';
  const restart = document.getElementById('restartGame');
  if (restart) restart.hidden = false;
  const reconstruction = document.getElementById('reconstructCase');
  if (reconstruction && typeof StoryScenes !== 'undefined') {
    reconstruction.hidden = gameState?.ending_id !== 'true_ending';
    reconstruction.onclick = StoryScenes.reconstruct;
  }
  const feed = document.getElementById('chatFeed');
  const box = document.createElement('div');
  box.className = 'msg-system ending-card';
  box.innerHTML = `<div class="card-header-bar"><span class="badge info">${gameState?.ending_id === 'cold_arrival' ? 'หมดเวลา · รถไฟถึงปลายทาง' : 'บทสรุปคดี'}</span></div>` +
    `<div class="story-text">${escapeHtml(decision?.message || 'คดีนี้ปิดลงแล้ว')}</div>`;
  if (latestProfile) {
    const profileCard = document.createElement('div');
    profileCard.className = 'story-text';
    profileCard.textContent = `${latestProfile.archetype_badge || '⚖️'} ${latestProfile.archetype_name_th || 'นักสืบสายสมดุล'} · ${latestProfile.archetype_description_th || ''}`;
    box.appendChild(profileCard);
    const exportButton = document.createElement('button');
    exportButton.type = 'button';
    exportButton.className = 'chip-btn';
    exportButton.textContent = 'ดูข้อมูลวิจัย';
    exportButton.addEventListener('click', () => window.open(`${API_BASE}/research/export`, '_blank'));
    box.appendChild(exportButton);
  }
  feed.appendChild(box);
  feed.scrollTop = 0;
  if (typeof PixelUI !== 'undefined') PixelUI.refresh();
}

// ============================================================
// คิวคำสั่งพ่วง — แปลง alternatives เป็นลำดับขั้นแล้วทำทีละขั้น
// ============================================================
const VERB_TH = { examine: "ตรวจ", move: "ไป", interrogate: "สอบปากคำ", take: "หยิบ",
                  accuse: "กล่าวหา", burn: "เผา", unlock: "ปลดล็อก", use: "ใช้", infer: "เสนอข้อสรุป" };
const REQUIRES_CONFIRMATION = new Set(["accuse", "burn", "infer"]);

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
  const cut = steps.findIndex(st => REQUIRES_CONFIRMATION.has(st.action));
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
      ? (steps[0]?.action === 'infer'
      ? `<div class="story-text"><strong>ขั้นต่อไปต้องให้คุณเสนอข้อสรุปเอง</strong><br>เลือกทำต่อเพื่อเลือกข้อสรุปและแนบหลักฐาน</div>`
      : `<div class="story-text"><strong>ขั้นต่อไปย้อนกลับไม่ได้</strong><br>กดยืนยันถ้าต้องการทำต่อ</div>`)
    : `<div class="story-text"><strong>คำสั่งนี้ตีความได้ ${steps.length} อย่าง</strong><br>เลือกสิ่งที่ต้องการ</div>`;
  const wrap = document.createElement("div");
  wrap.className = "chips-scroll";
  if (typeof window !== 'undefined' && typeof window.setupHorizontalScroll === 'function') {
    window.setupHorizontalScroll(wrap);
  }
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
  const modeTag = renderParserModeTag(parsed);

  const repairBanner = parsed?.repair_note ? `
    <div class="nesy-repair-banner">
      <span class="nesy-icon">⚡</span>
      <div class="nesy-repair-content">
        <strong>Neuro-Symbolic Constraint Repair</strong>
        <span>${escapeHtml(parsed.repair_note)}</span>
      </div>
    </div>` : '';

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
      <div class="card-meta-tags">
        ${modeTag}
        <span class="mode-tag">${modeLabel}</span>
      </div>
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
  return steps.map(s => {
    const isRepair = s.rule_id === "SYMBOLIC_REPAIR";
    const ruleIdLabel = isRepair ? "⚡ REPAIR" : escapeHtml(s.rule_id.split('_')[0]);
    const idClass = isRepair ? "rule-id nesy-repair-badge" : "rule-id";
    return `
    <div class="rule-row ${isRepair ? 'repair-row' : ''}">
      <span class="rule-status ${s.passed ? 'pass' : 'fail'}">${s.passed ? 'ผ่าน' : 'ไม่ผ่าน'}</span>
      <span class="${idClass}">${ruleIdLabel}</span>
      <span>${escapeHtml(s.description)}</span>
    </div>
  `;
  }).join("");
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
