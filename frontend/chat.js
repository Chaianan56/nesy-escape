/**
 * NeSy-Escape: FE-1 Chat & Reasoning Chain Controller
 * 
 * ข้อกำหนดทางวิชาการ:
 * 1. ห้ามสร้าง reasoning chain ปลอม (No post-hoc rationalization) — ถ้าเซิร์ฟเวอร์ต่อไม่ได้ ให้แจ้งความจริง
 * 2. ดึง initial_state (ครบ 8 ฟิลด์) และ briefing จาก GET /scene เสมอ ไม่ hardcode ทับ story.json
 * 3. ล็อกช่องพิมพ์ (disabled) และแสดง loading ระหว่างรอ LLM เพื่อกัน request ซ้อนและ gameState เพี้ยน
 * 4. ปุ่มสลับโหมด A/B ระบุชัดเจนว่าโหมด A คือ Baseline (เปรียบเทียบ) และโหมด B คือ NeSy Engine (เสนอแนะ)
 */

const API_BASE = "http://127.0.0.1:8000";

let currentMode = "B"; // 'B' = NeSy Engine (Proposed), 'A' = Baseline LLM
let gameState = null;  // จะถูกโหลดจาก GET /scene -> initial_state (ครบ 8 ฟิลด์)

// 1. โหลดข้อมูลเริ่มต้นจาก GET /scene เมื่อเปิดหน้าเว็บ
window.addEventListener("DOMContentLoaded", () => {
  initGame();
});

async function initGame() {
  const feed = document.getElementById("chatFeed");
  feed.innerHTML = `
    <div class="msg-loading" id="initLoading">
      <div class="spinner"></div>
      <span>กำลังเชื่อมต่อกับ backend และโหลดข้อมูลสถานการณ์ (GET /scene)...</span>
    </div>
  `;

  try {
    const res = await fetch(`${API_BASE}/scene`, { signal: AbortSignal.timeout(4000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sceneData = await res.json();

    // ดึง initial_state ครบ 8 ฟิลด์จาก Pydantic
    gameState = sceneData.initial_state;

    // เคลียร์ loading และแสดง briefing จาก story.json จริง
    feed.innerHTML = "";
    renderSystem({
      allowed: true,
      message: sceneData.briefing || "เริ่มการสืบสวนบนขบวนรถไฟนอกเทิร์นเอกซ์เพรส",
      reasoning_chain: []
    }, { action: "system_briefing" });

  } catch (err) {
    feed.innerHTML = `
      <div class="msg-error">
        <strong>⚠️ ไม่สามารถเชื่อมต่อกับ backend (${API_BASE}) ได้</strong><br>
        กรุณาตรวจสอบว่าเซิร์ฟเวอร์เปิดอยู่ (คำสั่ง: <code>uvicorn app.main:app --reload</code>)<br>
        <button onclick="initGame()">🔄 ลองเชื่อมต่อใหม่อีกครั้ง</button>
      </div>
    `;
  }
}

// 2. สลับโหมดการทดลอง (โหมด B = Proposed / โหมด A = Baseline)
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

// 3. จัดการการส่งคำสั่ง (มีระบบล็อกช่องพิมพ์ + Loading ป้องกัน gameState เพี้ยน)
async function sendMessage(e) {
  e.preventDefault();
  const input = document.getElementById("chatInput");
  const btn = document.getElementById("sendBtn");
  const btnText = document.getElementById("sendBtnText");
  const text = input.value.trim();

  if (!text) return;

  // ล็อกช่องพิมพ์และปุ่มส่งทันที กันกด Enter รัวๆ ขณะรอ LLM
  input.disabled = true;
  btn.disabled = true;
  btnText.textContent = "...";

  // แสดงข้อความของผู้เล่น
  renderUser(text);
  input.value = "";

  // แสดงสถานะ Loading ในแชท
  const feed = document.getElementById("chatFeed");
  const loadingDiv = document.createElement("div");
  loadingDiv.className = "msg-loading";
  loadingDiv.id = "activeLoading";
  loadingDiv.innerHTML = `
    <div class="spinner"></div>
    <span>${currentMode === "B" ? "NeSy Engine กำลังตีความและตรวจกฎ..." : "โหมด A (Baseline LLM) กำลังประมวลผล..."}</span>
  `;
  feed.appendChild(loadingDiv);
  feed.scrollTop = feed.scrollHeight;

  try {
    // ถ้ายังไม่มี gameState ให้พยายามดึงจาก /scene ก่อน
    if (!gameState) {
      const sRes = await fetch(`${API_BASE}/scene`);
      if (sRes.ok) {
        const sData = await sRes.json();
        gameState = sData.initial_state;
      }
    }

    // เรียก API จริง POST /command
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

    // อัปเดต GameState เมื่อ backend ส่ง new_state กลับมา
    if (data.new_state) {
      gameState = data.new_state;
    }

    // ลบ Loading และแสดงผลการตัดสินจริงจากระบบ
    removeLoading();
    renderSystem(data.decision, data.parsed);

  } catch (err) {
    // เซิร์ฟเวอร์ขัดข้อง: แจ้งความจริง ไม่ปลอมเหตุผล
    removeLoading();
    renderError(`⚠️ เชื่อมต่อไม่ได้: ${err.message} กรุณาตรวจสอบสถานะ backend แล้วลองใหม่`);
  } finally {
    // ปลดล็อกช่องพิมพ์คืนให้ผู้เล่นเสมอ
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

// 4. แสดงผลกล่องข้อความของผู้เล่น
function renderUser(text) {
  const feed = document.getElementById("chatFeed");
  const div = document.createElement("div");
  div.className = "msg-user";
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

// 5. แสดงผลการตัดสินและ Reasoning Chain ตามสเปก FE-1
function renderSystem(decision, parsed = null) {
  const feed = document.getElementById("chatFeed");
  const card = document.createElement("div");
  card.className = `msg-system ${decision.allowed ? "" : "denied"}`;

  const steps = decision.reasoning_chain || [];
  const statusBadge = decision.allowed 
    ? `<span class="badge allowed">✓ อนุมัติ (ALLOWED)</span>`
    : `<span class="badge denied">✗ ปฏิเสธ (DENIED)</span>`;

  const modeLabel = currentMode === "B" ? "โหมด B (NeSy Engine)" : "โหมด A (Baseline LLM)";

  // ส่วนแสดง Reasoning Chain (หัวใจของงานวิจัย)
  let reasoningHtml = "";
  if (steps.length > 0) {
    if (decision.allowed) {
      // ผ่าน: พับเก็บไว้ ไม่แย่งซีนเนื้อเรื่อง (ผู้เล่นกดขยายได้)
      reasoningHtml = `
        <details class="reasoning-details">
          <summary>🔍 ดูการตรวจกฎ (${steps.length} ขั้นผ่าน)</summary>
          <div class="rule-table">${renderRules(steps)}</div>
        </details>
      `;
    } else {
      // ไม่ผ่าน: โชว์ขั้นที่ไม่ผ่านออกมาทันที!
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

// 6. แสดงข้อความแจ้งเตือนข้อผิดพลาดการเชื่อมต่อ
function renderError(message) {
  const feed = document.getElementById("chatFeed");
  const div = document.createElement("div");
  div.className = "msg-error";
  div.innerHTML = `
    <div>${escapeHtml(message)}</div>
  `;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

// ฟังก์ชันย่อย: แสดงแถวกฎ
function renderRules(steps) {
  return steps.map(s => `
    <div class="rule-row">
      <span class="rule-status ${s.passed ? 'pass' : 'fail'}">${s.passed ? 'ผ่าน' : 'ไม่ผ่าน'}</span>
      <span class="rule-id">${escapeHtml(s.rule_id.split('_')[0])}</span>
      <span>${escapeHtml(s.description)}</span>
    </div>
  `).join("");
}

// ป้องกัน XSS
function escapeHtml(t) {
  if (!t) return "";
  const div = document.createElement("div");
  div.textContent = t;
  return div.innerHTML;
}
