/**
 * NeSy-Escape: Nocturne Express 1938 — Controller & UI Manager
 * Theme: 1938 Victorian Noir Wireframe Interface
 * Synchronized with NeSy Backend API (GET /scene, POST /command, POST /pillars)
 */

const API_BASE = "http://127.0.0.1:8000";

let currentMode = "B"; // 'B' = NeSy Engine (Default), 'A' = Baseline LLM
let gameState = null;
let timeLimitSeconds = 3600;
let locationsMap = {};
let suspectsMap = {};
let objectsMap = {};
let pillarsData = {};

// Fallback scene data if backend server is starting up or offline
const DEFAULT_INITIAL_STATE = {
  current_location: "dining_car",
  elapsed_seconds: 30,
  inventory: ["brass_button"],
  discovered_clues: ["mara_record", "seat8_ticket"],
  interrogated_suspects: ["mara"],
  solved_questions: 1
};

const LOCATION_NAMES = {
  locomotive: "หัวจักร",
  passenger_car: "ตู้โดยสาร",
  dining_car: "ตู้เสบียง",
  luggage_van: "ตู้สัมภาระ",
  electrical_compartment: "ห้องไฟฟ้า",
  service_pantry: "ห้องเก็บสัมภาระท้ายขบวน"
};

// ============================================================
// 1. INITIALIZATION (DOM Ready)
// ============================================================
window.addEventListener("DOMContentLoaded", () => {
  initGame();
});

async function initGame() {
  setSystemStatus("กำลังเชื่อมต่อเซิร์ฟเวอร์...", "#38bdf8");
  
  try {
    const res = await fetch(`${API_BASE}/scene`, { signal: AbortSignal.timeout(3000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sceneData = await res.json();

    gameState = sceneData.initial_state;
    timeLimitSeconds = sceneData.time_limit_seconds || 3600;
    locationsMap = sceneData.locations || LOCATION_NAMES;
    suspectsMap = sceneData.suspects || {};
    objectsMap = sceneData.objects || {};

    if (sceneData.briefing) {
      document.getElementById("modalBriefingText").textContent = sceneData.briefing;
    }

    updateHUD();
    updateTrainSchematic();
    updateProgressBars();
    await fetchPillars();

    setSystemStatus("ระบบทำงานปกติ", "#22c55e");

  } catch (err) {
    console.warn("Backend not active, using default scenario state:", err);
    gameState = Object.assign({}, DEFAULT_INITIAL_STATE);
    locationsMap = LOCATION_NAMES;
    
    updateHUD();
    updateTrainSchematic();
    updateProgressBars();
    setSystemStatus("โหมด Wireframe จำลอง (Offline)", "#eab308");
  }
}

// ============================================================
// 2. HUD & STATUS UPDATES
// ============================================================
function updateHUD() {
  if (!gameState) return;

  // Location Pill
  const locHeader = document.getElementById("locHeader");
  const currentLoc = gameState.current_location || "dining_car";
  if (locHeader) {
    locHeader.textContent = locationsMap[currentLoc] || currentLoc;
  }

  // Investigation Clock (23:17 start + elapsed)
  const clockHeader = document.getElementById("clockHeader");
  const timerVal = document.getElementById("elapsedSecondsText");
  const elapsed = gameState.elapsed_seconds || 0;

  if (timerVal) {
    timerVal.textContent = `${elapsed} วินาที`;
  }

  if (clockHeader) {
    const baseMinutes = 23 * 60 + 17;
    const currentTotalMinutes = baseMinutes + Math.floor(elapsed / 60);
    const hrs = Math.floor((currentTotalMinutes / 60) % 24);
    const mins = Math.floor(currentTotalMinutes % 60);
    clockHeader.textContent = `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
  }
}

function updateProgressBars() {
  if (!gameState) return;

  const cluesFound = (gameState.discovered_clues || []).length + (gameState.inventory || []).length;
  const cluesTotal = 42;
  const suspectsFound = (gameState.interrogated_suspects || []).length;
  const suspectsTotal = 12;
  const locsFound = 4;
  const locsTotal = 8;
  const pillarsSolved = gameState.solved_questions || 1;
  const pillarsTotal = 4;

  const evRatio = document.getElementById("evidenceRatio");
  const evBar = document.getElementById("evidenceBar");
  if (evRatio && evBar) {
    evRatio.textContent = `${cluesFound} / ${cluesTotal}`;
    evBar.style.width = `${Math.min(100, Math.round((cluesFound / cluesTotal) * 100))}%`;
  }

  const susRatio = document.getElementById("suspectRatio");
  const susBar = document.getElementById("suspectBar");
  if (susRatio && susBar) {
    susRatio.textContent = `${suspectsFound} / ${suspectsTotal}`;
    susBar.style.width = `${Math.min(100, Math.round((suspectsFound / suspectsTotal) * 100))}%`;
  }

  const locRatio = document.getElementById("locRatio");
  const locBar = document.getElementById("locBar");
  if (locRatio && locBar) {
    locRatio.textContent = `${locsFound} / ${locsTotal}`;
    locBar.style.width = `${Math.min(100, Math.round((locsFound / locsTotal) * 100))}%`;
  }

  const pillarRatio = document.getElementById("pillarRatio");
  const pillarBar = document.getElementById("pillarBar");
  if (pillarRatio && pillarBar) {
    pillarRatio.textContent = `${pillarsSolved} / ${pillarsTotal}`;
    pillarBar.style.width = `${Math.min(100, Math.round((pillarsSolved / pillarsTotal) * 100))}%`;
  }
}

function updateTrainSchematic() {
  if (!gameState) return;
  const currentLoc = gameState.current_location || "dining_car";

  document.querySelectorAll(".train-cars-flex .car-card").forEach(card => {
    const locId = card.getAttribute("data-loc");
    const hull = card.querySelector(".car-hull");
    const pin = card.querySelector(".pin-marker");

    if (locId === currentLoc) {
      card.classList.add("active");
      if (hull) hull.classList.add("active-hull");
      if (!pin) {
        const newPin = document.createElement("div");
        newPin.className = "pin-marker";
        newPin.textContent = "📍";
        card.prepend(newPin);
      }
    } else {
      card.classList.remove("active");
      if (hull) hull.classList.remove("active-hull");
      if (pin) pin.remove();
    }
  });
}

function setSystemStatus(text, color = "#22c55e") {
  const statusLbl = document.getElementById("systemStatusText");
  const pulseDot = document.querySelector(".pulse-dot");
  if (statusLbl) {
    statusLbl.textContent = text;
    statusLbl.style.color = color;
  }
  if (pulseDot) {
    pulseDot.style.backgroundColor = color;
    pulseDot.style.boxShadow = `0 0 8px ${color}`;
  }
}

// ============================================================
// 3. COMMAND LOOP (Send Message & NeSy Engine)
// ============================================================
async function sendMessage(event) {
  if (event) event.preventDefault();
  
  const input = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");
  const sendBtnText = document.getElementById("sendBtnText");
  const text = input.value.trim();

  if (!text) return;

  // ป้องกัน race condition โดยการล็อก input
  input.disabled = true;
  sendBtn.disabled = true;
  sendBtnText.textContent = "กำลังคิด...";
  setSystemStatus("กำลังตรวจสอบกฎ NeSy...", "#38bdf8");

  try {
    const res = await fetch(`${API_BASE}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text,
        mode: currentMode,
        state: gameState
      })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.new_state) {
      gameState = data.new_state;
    }

    updateHUD();
    updateTrainSchematic();
    updateProgressBars();

    renderDialogue(data.decision, data.parsed);
    setSystemStatus("ระบบทำงานปกติ", "#22c55e");

  } catch (err) {
    console.warn("Backend error, rendering simulated response:", err);
    
    // Simulate wireframe dialogue response
    const mockDecision = {
      allowed: true,
      message: `คุณสั่ง: "${text}" — Mara มองหน้าคุณด้วยแววตาครุ่นคิด "เรื่องนั้นฉันไม่แน่ใจนัก แต่ถ้าลองไปดูที่ตู้โดยสารอาจจะพบเบาะแสเพิ่มเติมค่ะ"`,
      reasoning_chain: [
        { rule_id: "R01_PRESENCE", passed: true, description: "ผู้เล่นและเป้าหมายอยู่ในตู้รถเดียวกัน (Dining Car)" },
        { rule_id: "R02_TEMPORAL", passed: true, description: "เหตุการณ์สอดคล้องกับเส้นเวลา 23:17" },
        { rule_id: "R03_MOTIVE_CHECK", passed: true, description: "ไม่มีเงื่อนไขขัดแย้งกับหลักฐานก่อนหน้า" }
      ]
    };
    renderDialogue(mockDecision, null);
    setSystemStatus("โหมด Wireframe จำลอง (Offline)", "#eab308");

  } finally {
    input.value = "";
    input.disabled = false;
    sendBtn.disabled = false;
    sendBtnText.textContent = "ส่งคำสั่ง";
    input.focus();
  }
}

function renderDialogue(decision, parsed) {
  const dialogueText = document.getElementById("dialogueText");
  const decisionBadge = document.getElementById("decisionBadge");
  const decisionBadgeText = document.getElementById("decisionBadgeText");
  const rulesTable = document.getElementById("rulesTable");
  const rulesCountBadge = document.getElementById("rulesCountBadge");
  const failAlertBox = document.getElementById("failAlertBox");

  if (!decision) return;

  // Dialogue Content
  if (dialogueText) {
    dialogueText.textContent = decision.message || "...";
  }

  // Allowed / Denied Badge
  if (decisionBadge && decisionBadgeText) {
    if (decision.allowed) {
      decisionBadge.className = "decision-tag allowed";
      decisionBadgeText.textContent = "✓ ตรวจสอบผ่าน (ALLOWED)";
    } else {
      decisionBadge.className = "decision-tag denied";
      decisionBadgeText.textContent = "✗ ปฏิเสธการกระทำ (DENIED)";
    }
  }

  // Reasoning Chain (FE-1)
  const steps = decision.reasoning_chain || [];
  if (rulesTable && rulesCountBadge) {
    const passedCount = steps.filter(s => s.passed).length;
    rulesCountBadge.textContent = `ผ่าน ${passedCount}/${steps.length}`;
    
    rulesTable.innerHTML = steps.map(s => `
      <div class="rule-row-item ${s.passed ? 'pass' : 'fail'}">
        <span style="color: ${s.passed ? '#4ade80' : '#f87171'}; font-weight: 600;">${s.passed ? '✓' : '✗'}</span>
        <strong style="color: #d4af37;">${escapeHtml(s.rule_id)}</strong>
        <span style="color: #cbd5e1;">${escapeHtml(s.description)}</span>
      </div>
    `).join("");
  }

  if (failAlertBox) {
    if (!decision.allowed) {
      const failed = steps.find(s => !s.passed);
      failAlertBox.style.display = "block";
      failAlertBox.textContent = failed 
        ? `⚠️ ข้อผิดพลาด: ${failed.rule_id} — ${failed.description}`
        : `⚠️ ข้อผิดพลาด: ${decision.violated_rule_id || 'DENIED'}`;
    } else {
      failAlertBox.style.display = "none";
    }
  }
}

// ============================================================
// 4. QUICK ACTIONS & INTERACTIVE CONTROLS
// ============================================================
function quickMove(locId) {
  fillInput(`ไปที่ ${LOCATION_NAMES[locId] || locId}`);
  sendMessage();
}

function fillInput(text) {
  const input = document.getElementById("chatInput");
  if (!input) return;
  input.value = text;
  input.focus();
}

function setMode(mode) {
  currentMode = mode;
  const btnB = document.getElementById("btnModeB");
  const btnA = document.getElementById("btnModeA");

  if (mode === "B") {
    btnB.classList.add("active");
    btnA.classList.remove("active");
  } else {
    btnA.classList.add("active");
    btnB.classList.remove("active");
  }
}

function switchRightTab(tabId) {
  const tabBtnEvidence = document.getElementById("tabBtnEvidence");
  const tabBtnSuspects = document.getElementById("tabBtnSuspects");
  const tabBtnPillars = document.getElementById("tabBtnPillars");

  const paneEvidence = document.getElementById("tabContentEvidence");
  const paneSuspects = document.getElementById("tabContentSuspects");
  const panePillars = document.getElementById("tabContentPillars");

  [tabBtnEvidence, tabBtnSuspects, tabBtnPillars].forEach(btn => btn && btn.classList.remove("active"));
  [paneEvidence, paneSuspects, panePillars].forEach(pane => pane && pane.classList.remove("active"));

  if (tabId === "evidence") {
    if (tabBtnEvidence) tabBtnEvidence.classList.add("active");
    if (paneEvidence) paneEvidence.classList.add("active");
  } else if (tabId === "suspects") {
    if (tabBtnSuspects) tabBtnSuspects.classList.add("active");
    if (paneSuspects) paneSuspects.classList.add("active");
  } else if (tabId === "pillars") {
    if (tabBtnPillars) tabBtnPillars.classList.add("active");
    if (panePillars) panePillars.classList.add("active");
  }
}

async function fetchPillars() {
  if (!gameState) return;
  try {
    const res = await fetch(`${API_BASE}/pillars`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(gameState)
    });
    if (res.ok) {
      pillarsData = await res.json();
    }
  } catch (e) {
    console.warn("Fetch pillars skipped:", e);
  }
}

// Briefing Modal
function openBriefingModal() {
  const modal = document.getElementById("briefingModal");
  if (modal) modal.style.display = "flex";
}

function closeBriefingModal() {
  const modal = document.getElementById("briefingModal");
  if (modal) modal.style.display = "none";
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
