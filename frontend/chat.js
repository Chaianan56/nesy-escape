/**
 * NeSy-Escape: Complete Controller
 * 
 * ครอบคลุมสเปก:
 * 1. ตัวอย่างคำสั่ง (Quick Suggestion Chips & Onboarding Hints)
 * 2. คำบรรยายห้องตอนเริ่มเกม (Auto-execute 'ดูรอบๆ' หลังโหลด /scene)
 * 3. แผงความคืบหน้าสี่เสา (FE-4: POST /pillars ทุกครั้งที่คำสั่งผ่าน)
 * 4. นาฬิกาการสืบสวน (FE-3: นับถอยหลังตาม time_limit_seconds - elapsed_seconds)
 */

const API_BASE = "http://127.0.0.1:8000";

let currentMode = "B"; // 'B' = NeSy Engine, 'A' = Baseline LLM
let gameState = null;
let timeLimitSeconds = 3600;
let suspectsMap = {};
let pillarsData = {};

const PILLAR_NAMES = {
  motive: "แรงจูงใจ (Motive)",
  means: "วิธีการ (Means)",
  opportunity: "โอกาส (Opportunity)",
  corroboration: "หลักฐานสนับสนุน (Corroboration)"
};

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
    timeLimitSeconds = sceneData.time_limit_seconds || 3600;
    suspectsMap = sceneData.suspects || {};

    // อัปเดตนาฬิกาครั้งแรก (FE-3)
    updateClock();

    // เคลียร์ loading และแสดงบทเปิดคดี (Briefing) จาก story.json จริง
    feed.innerHTML = "";
    renderBriefing(sceneData.briefing);

    // ดึงสถานะสี่เสาตั้งต้น (FE-4)
    await fetchPillars();

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

// แสดงการ์ดบทเปิดคดี พร้อมตัวอย่างคำสั่งเบื้องต้น (ข้อ 1)
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
        <div>• <code>ดูรอบๆ</code> — สำรวจตู้รถที่ยืนอยู่และดูว่ามีอะไรให้ตรวจสอบบ้าง</div>
        <div>• <code>ไปที่จุดเกิดเหตุ</code> — เดินทางไปยังห้องเก็บของบริการ</div>
        <div>• <code>ตรวจดูสมุดบันทึกของผู้ตาย</code> — ตรวจสอบวัตถุหรือหลักฐานในห้อง</div>
        <div>• <code>ขอสอบปากคำพนักงานควบคุมรถหน่อย</code> — พูดคุยกับพยานหรือผู้ต้องสงสัย</div>
        <div>• <code>กล่าวหากิเดียน ฮาร์ต</code> — ตั้งข้อกล่าวหา (เมื่อรวบรวมหลักฐานครบ 4 เสา)</div>
      </div>
    </div>
  `;
  feed.appendChild(card);
}

// ข้อ 2: ยิงคำสั่ง "ดูรอบๆ" อัตโนมัติเพื่อแสดงคำบรรยายห้องที่ผู้เล่นยืนอยู่
async function executeInitialLookAround() {
  try {
    const res = await fetch(`${API_BASE}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: "ดูรอบๆ",
        mode: currentMode,
        state: gameState
      })
    });

    if (res.ok) {
      const data = await res.json();
      if (data.new_state) gameState = data.new_state;
      updateClock();

      // แสดงผลคำบรรยายห้อง
      renderSystem(data.decision, data.parsed, true);
    }
  } catch (e) {
    console.warn("Auto look_around failed:", e);
  }
}

// ============================================================
// 2. นาฬิกาการสืบสวน (FE-3)
// ============================================================
function updateClock() {
  const clockText = document.getElementById("clockText");
  const clockWidget = document.getElementById("clockWidget");
  if (!clockText || !clockWidget) return;

  const elapsed = gameState ? (gameState.elapsed_seconds || 0) : 0;
  const remaining = Math.max(0, timeLimitSeconds - elapsed);
  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;

  clockText.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

  if (remaining <= 0) {
    clockWidget.className = "clock-widget danger";
    clockText.textContent = "00:00 (หมดเวลา)";
  } else if (remaining <= 600) { // เหลือน้อยกว่า 10 นาที
    clockWidget.className = "clock-widget danger";
  } else if (remaining <= 1200) { // เหลือน้อยกว่า 20 นาที
    clockWidget.className = "clock-widget warning";
  } else {
    clockWidget.className = "clock-widget";
  }
}

// ============================================================
// 3. แผงความคืบหน้าสี่เสา (FE-4)
// ============================================================
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
      renderPillarsUI();
    }
  } catch (e) {
    console.warn("Fetch pillars failed:", e);
  }
}

function renderPillarsUI() {
  const grid = document.getElementById("pillarsGrid");
  const badge = document.getElementById("pillarsBadge");
  if (!grid || !badge) return;

  let maxFound = 0;
  grid.innerHTML = "";

  for (const [suspectId, pillars] of Object.entries(pillarsData)) {
    const thName = suspectsMap[suspectId] || suspectId;
    let foundCount = 0;

    let itemsHtml = "";
    for (const [pillarKey, pLabel] of Object.entries(PILLAR_NAMES)) {
      const evList = pillars[pillarKey] || [];
      const hasEv = evList.length > 0;
      if (hasEv) foundCount++;

      itemsHtml += `
        <div class="pillar-item">
          <span>${pLabel.split(" ")[0]}</span>
          <span class="status ${hasEv ? 'yes' : 'no'}">${hasEv ? '✓ พบแล้ว' : '✗ ยังไม่พบ'}</span>
        </div>
      `;
    }

    if (foundCount > maxFound) maxFound = foundCount;

    const isCulprit = suspectId === "gideon_hart";
    const card = document.createElement("div");
    card.className = `suspect-card ${isCulprit ? 'target' : ''}`;
    card.innerHTML = `
      <div class="suspect-name">
        <span>👤 ${escapeHtml(thName)}</span>
        <span class="suspect-count">${foundCount}/4 เสา</span>
      </div>
      <div>${itemsHtml}</div>
    `;
    grid.appendChild(card);
  }

  badge.textContent = `${maxFound}/4`;
}

function togglePillarsPanel() {
  const panel = document.getElementById("pillarsPanel");
  if (!panel) return;
  panel.style.display = panel.style.display === "none" ? "block" : "none";
}

// ============================================================
// 4. สลับโหมดการทดลอง (Mode A vs Mode B)
// ============================================================
function setMode(mode) {
  currentMode = mode;
  const btnB = document.getElementById("btnB");
  const btnA = document.getElementById("btnA");

  if (mode === "B") {
    btnB.className = "active";
    btnA.className = "";
  } else {
    btnB.className = "";
    btnA.className = "mode-a-active";
  }
}

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
async function sendMessage(e) {
  e.preventDefault();
  const input = document.getElementById("chatInput");
  const btn = document.getElementById("sendBtn");
  const btnText = document.getElementById("sendBtnText");
  const text = input.value.trim();

  if (!text) return;

  // ล็อกช่องพิมพ์ทันที กันกดซ้ำ
  input.disabled = true;
  btn.disabled = true;
  btnText.textContent = "...";

  renderUser(text);
  input.value = "";

  // แสดง Loading Bubble
  const feed = document.getElementById("chatFeed");
  const loadingDiv = document.createElement("div");
  loadingDiv.className = "msg-loading";
  loadingDiv.id = "activeLoading";
  loadingDiv.innerHTML = `
    <div class="spinner"></div>
    <span>${currentMode === "B" ? "NeSy Engine กำลังตีความและตรวจกฎ 15 ข้อ..." : "โหมด A (Baseline LLM) กำลังประมวลผล..."}</span>
  `;
  feed.appendChild(loadingDiv);
  feed.scrollTop = feed.scrollHeight;

  try {
    if (!gameState) {
      const sRes = await fetch(`${API_BASE}/scene`);
      if (sRes.ok) {
        const sData = await sRes.json();
        gameState = sData.initial_state;
      }
    }

    const res = await fetch(`${API_BASE}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text,
        mode: currentMode,
        state: gameState
      })
    });

    if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
    const data = await res.json();

    // อัปเดตสถานะเกม
    if (data.new_state) {
      gameState = data.new_state;
    }

    // อัปเดตนาฬิกา (FE-3)
    updateClock();

    // อัปเดตสี่เสาเมื่อคำสั่งผ่าน (FE-4)
    if (data.decision && data.decision.allowed) {
      fetchPillars();
    }

    removeLoading();
    renderSystem(data.decision, data.parsed);

  } catch (err) {
    removeLoading();
    renderError(`⚠️ เชื่อมต่อไม่ได้: ${err.message} กรุณาตรวจสอบสถานะ backend แล้วลองใหม่`);
  } finally {
    input.disabled = false;
    btn.disabled = false;
    btnText.textContent = "ส่ง";
    input.focus();
  }
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
  card.className = `msg-system ${decision.allowed ? "" : "denied"} ${isRoomLook ? "room-look" : ""}`;

  const steps = decision.reasoning_chain || [];
  let statusBadge = "";
  if (isRoomLook) {
    statusBadge = `<span class="badge info">📍 สภาพตู้รถปัจจุบัน</span>`;
  } else if (decision.allowed) {
    statusBadge = `<span class="badge allowed">✓ อนุมัติ (ALLOWED)</span>`;
  } else {
    statusBadge = `<span class="badge denied">✗ ปฏิเสธ (DENIED)</span>`;
  }

  const modeLabel = currentMode === "B" ? "โหมด B (NeSy)" : "โหมด A (Baseline)";

  // Reasoning Chain
  let reasoningHtml = "";
  if (steps.length > 0) {
    if (decision.allowed) {
      reasoningHtml = `
        <details class="reasoning-details">
          <summary>🔍 ดูการตรวจกฎ (${steps.length} ขั้นผ่าน)</summary>
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
