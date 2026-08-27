/**
 * NeSy-Escape: FE-1 Chat & Reasoning Chain Controller (Minimal & Clean)
 */

let currentMode = "B";
let gameState = {
  current_location: "passenger_car",
  inventory: [],
  discovered_evidence: [],
  elapsed_seconds: 0
};

// 1. Initial Story Message on Load
window.addEventListener("DOMContentLoaded", () => {
  renderSystem({
    allowed: true,
    message: "คืนวันที่ 14 พฤศจิกายน 1938 บนขบวนนอกเทิร์นเอกซ์เพรส\nเวลา 23:17 ไฟดับลง 46 วินาที เมื่อไฟกลับมา แคสเซียน รีด ถูกพบเสียชีวิตในห้องเก็บของบริการ โดยประตูลงกลอนจากด้านในแน่นหนา\n\nคุณคือผู้สืบสวน พิมพ์คำสั่งเป็นภาษาไทยเพื่อเริ่มไขคดี เช่น 'ไปที่จุดเกิดเหตุ', 'ตรวจดูบันทึกสภาพจุดเกิดเหตุ'",
    reasoning_chain: [
      { rule_id: "R000_KNOWN_ACTION", description: "คำสั่งต้องตีความได้และอยู่ในขอบเขตของสถานการณ์", passed: true },
      { rule_id: "R014_TIME_LIMIT", description: "การกระทำต้องอยู่ภายในกรอบเวลาของการสืบสวน", passed: true }
    ]
  });
});

// 2. Mode Selector (Mode B: NeSy vs Mode A: Baseline)
function setMode(mode) {
  currentMode = mode;
  document.getElementById("btnB").className = mode === "B" ? "active" : "";
  document.getElementById("btnA").className = mode === "A" ? "active" : "";
}

// 3. Send Message Handler
async function sendMessage(e) {
  e.preventDefault();
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  renderUser(text);

  try {
    // Call FastAPI Backend
    const res = await fetch("http://127.0.0.1:8000/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, mode: currentMode, state: gameState })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.new_state) gameState = data.new_state;
    renderSystem(data.decision);

  } catch (err) {
    // Graceful Fallback if backend is offline during demo
    renderSystem(mockFallback(text));
  }
}

// 4. Render User Message
function renderUser(text) {
  const feed = document.getElementById("chatFeed");
  const div = document.createElement("div");
  div.className = "msg-user";
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

// 5. Render System Story Message + Reasoning Chain (FE-1 Specification)
function renderSystem(decision) {
  const feed = document.getElementById("chatFeed");
  const card = document.createElement("div");
  card.className = `msg-system ${decision.allowed ? "" : "denied"}`;

  const steps = decision.reasoning_chain || [];
  const statusBadge = decision.allowed 
    ? `<span class="badge allowed">✓ อนุมัติ (ALLOWED)</span>`
    : `<span class="badge denied">✗ ปฏิเสธ (DENIED)</span>`;

  // FE-1: Reasoning Chain Presentation
  let reasoningHtml = "";
  if (steps.length > 0) {
    if (decision.allowed) {
      // ผ่าน: พับเก็บไว้ ไม่บังเนื้อเรื่อง (ใช้ native <details>)
      reasoningHtml = `
        <details class="reasoning-details">
          <summary>🔍 ดูการตรวจกฎ (ผ่านครบ ${steps.length} ขั้น)</summary>
          <div class="rule-table">${renderRules(steps)}</div>
        </details>
      `;
    } else {
      // ไม่ผ่าน: โชว์ขั้นที่ไม่ผ่านออกมาทันที!
      const failed = steps.find(s => !s.passed) || { rule_id: "RULE_FAIL", description: decision.message };
      const passed = steps.filter(s => s.passed);

      reasoningHtml = `
        <div class="fail-alert">
          <strong>✗ ไม่ผ่านกฎ: ${failed.rule_id}</strong> — ${escapeHtml(failed.description)}
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
    ${statusBadge}
    <div class="story-text">${escapeHtml(decision.message)}</div>
    ${reasoningHtml}
  `;

  feed.appendChild(card);
  feed.scrollTop = feed.scrollHeight;
}

// Helper: Render Rule Rows
function renderRules(steps) {
  return steps.map(s => `
    <div class="rule-row">
      <span class="rule-status ${s.passed ? 'pass' : 'fail'}">${s.passed ? 'ผ่าน' : 'ไม่ผ่าน'}</span>
      <span class="rule-id">${s.rule_id.split('_')[0]}</span>
      <span>${escapeHtml(s.description)}</span>
    </div>
  `).join("");
}

// Helper: Escape HTML
function escapeHtml(t) {
  if (!t) return "";
  const d = document.createElement("div");
  d.textContent = t;
  return d.innerHTML;
}

// 6. Compact Offline Fallback (Under 30 lines)
function mockFallback(text) {
  const q = text.toLowerCase();
  if (q.includes("จุดเกิดเหตุ") || q.includes("ห้องเก็บของ")) {
    gameState.current_location = "service_pantry";
    return {
      allowed: true,
      message: "คุณเดินมายังห้องเก็บของบริการ (จุดเกิดเหตุ) ร่างของแคสเซียน รีด ถูกคลุมผ้าไว้ ประตูลงกลอนจากด้านในแน่นหนา มีกลิ่นสนิมเหล็กคละคลุ้ง",
      reasoning_chain: [
        { rule_id: "R000_KNOWN_ACTION", description: "คำสั่งต้องตีความได้และอยู่ในขอบเขตของสถานการณ์", passed: true },
        { rule_id: "R014_TIME_LIMIT", description: "การกระทำต้องอยู่ภายในกรอบเวลาของการสืบสวน", passed: true },
        { rule_id: "R002_LOCATION_EXISTS", description: "จุดหมายของการเคลื่อนที่ต้องเป็นตู้รถที่มีอยู่จริง", passed: true }
      ]
    };
  }
  if (q.includes("บันทึก") || q.includes("สมุด")) {
    return {
      allowed: true,
      message: "บันทึกสภาพจุดเกิดเหตุระบุว่า: ประตูลงกลอนจากด้านใน เวลาเสียชีวิตคือ 23:17 ซึ่งตรงกับช่วงเวลาที่ไฟดับ 46 วินาทีพอดี",
      reasoning_chain: [
        { rule_id: "R000_KNOWN_ACTION", description: "คำสั่งต้องตีความได้และอยู่ในขอบเขตของสถานการณ์", passed: true },
        { rule_id: "R001_TARGET_EXISTS", description: "เป้าหมายของคำสั่งต้องมีอยู่จริงบนขบวนรถ", passed: true }
      ]
    };
  }
  return {
    allowed: false,
    message: "ไม่สามารถดำเนินการได้ในเวลานี้ สิ่งที่คุณระบุอาจไม่อยู่ในจุดที่คุณยืนอยู่ หรืออยู่นอกขอบเขต",
    reasoning_chain: [
      { rule_id: "R000_KNOWN_ACTION", description: "คำสั่งต้องตีความได้และอยู่ในขอบเขตของสถานการณ์", passed: true },
      { rule_id: "R005_SAME_LOCATION", description: "ต้องอยู่ในตู้รถเดียวกับสิ่งที่ต้องการเข้าถึง", passed: false }
    ]
  };
}
