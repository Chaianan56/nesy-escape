/**
 * NeSy-Escape: Nocturne Express 1938 — Controller & UI Manager
 * Theme: 1938 Victorian Noir Wireframe / 2D Pixel Art Edition
 * Aligned with:
 *  - Left Panel: Reasoning Chain & Symbolic Engine
 *  - Center: Elevated Scene & Dialogue Card
 *  - Right Panel: 4-Tab Dossier (Evidence, Suspects, Chat History, 4 Pillars)
 *  - Bottom: Unified Command Deck (Train Map + Chips + Wide Command Form)
 */

const API_BASE = "http://127.0.0.1:8000";

let currentMode = "B"; // 'B' = NeSy Engine (Proposed), 'A' = Baseline LLM
let isBackendConnected = false;
let turnCount = 1;

// History of all dialogue turns
let dialogueHistory = [
  {
    turn: 1,
    time: "23:17",
    userQuery: "เริ่มต้นการสืบสวน",
    speaker: "Mara Voss",
    role: "พนักงานควบคุมรถไฟ",
    message: "...ฉันจำเวลาไม่ได้เป๊ะ ๆ หรอกนะคะ แต่ก่อนที่จะไฟดับ ฉันเห็นคุณ Cassian ยืนอยู่แถวตู้โดยสาร... เหมือนกำลังรอใครบางคน",
    allowed: true
  }
];

// Full Scenario Registry (aligned with story.json)
const STORY_REGISTRY = {
  locations: {
    passenger_car: {
      name_th: "ตู้โดยสาร",
      icon: "🪑",
      description: "ตู้โดยสารชั้นหนึ่ง ผ้าม่านกำมะหยี่ปิดสนิท ทางเดินแคบทอดยาวออกไปทั้งสองด้าน มีผู้โดยสารนั่งนิ่งอยู่ในห้องส่วนตัว",
      suspects: ["gideon_hart", "elias_venn", "mara_voss"],
      objects: ["seat8_ticket"]
    },
    dining_car: {
      name_th: "ตู้เสบียง",
      icon: "🍷",
      description: "ตู้เสบียงยังจัดโต๊ะค้างไว้จากมื้อค่ำ แก้วไวน์ครึ่งใบวางอยู่ริมหน้าต่าง สมุดบิลของพนักงานเปิดค้างอยู่บนเคาน์เตอร์",
      suspects: ["clara_duval", "victor_kane"],
      objects: ["wine_receipt_2316"]
    },
    service_pantry: {
      name_th: "ห้องเก็บของบริการ (จุดเกิดเหตุ)",
      icon: "⚠️",
      description: "ห้องเก็บของบริการ กลิ่นเหล็กและไวน์ปนกัน ร่างของแคสเซียน รีด ถูกคลุมผ้าไว้ตรงกลางห้อง ประตูลงกลอนจากด้านใน มีช่องส่งของขนาดคนลอดได้",
      suspects: ["cassian_reed"],
      objects: ["crime_scene_record", "elias_button", "cassian_notebook", "latch_scratches", "copper_wire"]
    },
    conductor_office: {
      name_th: "ห้องพนักงานควบคุมรถ",
      icon: "📋",
      description: "ห้องพนักงานควบคุมรถ แฟ้มและสมุดบันทึกเรียงเต็มชั้น มีสมุดลงชื่อเบิกกุญแจและรายชื่อผู้โดยสารฉบับทางการ",
      suspects: ["mara_voss"],
      objects: ["manifest_altered", "conductor_log"]
    },
    electrical_compartment: {
      name_th: "ห้องระบบไฟฟ้า",
      icon: "⚡",
      description: "ห้องระบบไฟฟ้า อากาศอบและมีกลิ่นน้ำมันเครื่อง แผงฟิวส์หลักของขบวนถูกเปิดค้างไว้ มีช่องหนึ่งว่างอยู่",
      suspects: [],
      objects: ["fuse_panel", "broken_fuse"]
    },
    luggage_van: {
      name_th: "ตู้สัมภาระ",
      icon: "📦",
      description: "ตู้สัมภาระ เย็นและมืดกว่าตู้อื่น หีบเดินทางซ้อนกันเป็นแถว มีกระเป๋าเดินทางใบหนึ่งวางแยกออกมาโดยไม่มีป้ายชื่อ",
      suspects: [],
      objects: ["elias_ticket", "heavy_wrench"]
    }
  },
  suspects: {
    mara_voss: {
      name_th: "มารา วอสส์ (Mara Voss)",
      role: "พนักงานควบคุมรถไฟ",
      relationship: "ให้ความร่วมมือ",
      status: "พยานสำคัญ",
      dialogue: "...ฉันจำเวลาไม่ได้เป๊ะ ๆ หรอกนะคะ แต่ก่อนที่จะไฟดับ ฉันเห็นคุณ Cassian ยืนอยู่แถวตู้โดยสาร... เหมือนกำลังรอใครบางคน"
    },
    gideon_hart: {
      name_th: "กิเดียน ฮาร์ต (Gideon Hart)",
      role: "อดีตผู้พิพากษาคดีเบลล์เวเธอร์",
      relationship: "ต้องสงสัยระดับสูง (★)",
      status: "ผู้ต้องสงสัยหลัก",
      dialogue: "ผมไม่มีอะไรจะพูดกับคุณ ทุกคำตัดสินของผมในคดีเบลล์เวเธอร์ถูกต้องตามกฎหมาย และผมอยู่ในห้องโดยสารตลอดเวลาที่ไฟดับ"
    },
    elias_venn: {
      name_th: "อีไลอัส เวนน์ (Elias Venn)",
      role: "แพทย์ประจำตัว / ทายาทตระกูลเวนน์",
      relationship: "มีพิรุธ",
      status: "ผู้ต้องสงสัย",
      dialogue: "กระดุมนั่นเหรอ? เสื้อคลุมของผมหายไปตั้งแต่ช่วงค่ำ มีคนขโมยมันไปสร้างหลักฐานเท็จใส่ร้ายผมแน่นอน!"
    },
    clara_duval: {
      name_th: "คลารา ดูวัล (Clara Duval)",
      role: "ศิลปินอิสระ",
      relationship: "เป็นกลาง",
      status: "พยาน",
      dialogue: "ตอนไฟดับ 46 วินาที ฉันนั่งดื่มชาอยู่ที่ตู้เสบียง ได้ยินเสียงคนวิ่งผ่านทางเดินไปทางท้ายขบวนอย่างรีบร้อนค่ะ"
    },
    victor_kane: {
      name_th: "วิคเตอร์ เคน (Victor Kane)",
      role: "นักสะสมของเก่า",
      relationship: "เฉยเมย",
      status: "พยาน",
      dialogue: "คุณรีดเขาพยายามจะเปิดเผยความลับบางอย่างก่อนขึ้นรถไฟขบวนนี้... เรื่องนี้มีคนเสียประโยชน์หลายคน"
    },
    cassian_reed: {
      name_th: "แคสเซียน รีด (Cassian Reed)",
      role: "นักประวัติศาสตร์ / ผู้เสียชีวิต",
      relationship: "ผู้เสียชีวิต (เหยื่อ)",
      status: "พบศพ ณ เวลา 23:17",
      dialogue: "(ร่างของแคสเซียน รีด นอนสงบนิ่งอยู่ใต้ผ้าคลุม ในมือยังมีเศษกระดาษกำแน่น)"
    }
  },
  objects: {
    crime_scene_record: { name_th: "บันทึกสภาพจุดเกิดเหตุ", loc: "service_pantry", clue: "ประตูลงกลอนจากใน หน้าต่างล็อกทุกบาน เวลาตาย 23:17:25" },
    cassian_notebook: { name_th: "สมุดบันทึกของแคสเซียน รีด", loc: "service_pantry", clue: "เบลล์เวเธอร์ไม่ใช่อุบัติเหตุ คนลงนามปิดคดีอยู่บนขบวนนี้ (ชี้ไปที่ Gideon Hart)" },
    elias_button: { name_th: "กระดุมของอีไลอัส ใกล้ศพ", loc: "service_pantry", clue: "กระดุมทองเหลืองตระกูลเวนน์ รอยตัดด้ายใหม่ผิดปกติ เหมือนจงใจวางทิ้งไว้" },
    latch_scratches: { name_th: "รอยขีดบริเวณกลอนประตู", loc: "service_pantry", clue: "รอยลวดเกี่ยวกลอนจากภายนอก พิสูจน์ว่าไม่ใช่ห้องปิดตายจริง" },
    copper_wire: { name_th: "เส้นลวดทองแดงซ่อนหลังช่องส่งของ", loc: "service_pantry", clue: "ลวดยาวหนึ่งศอก ปลายงอตะขอ มีรอยครูดตรงกับรอยบนกลอนประตู" },
    seat8_ticket: { name_th: "ตั๋วที่นั่งหมายเลข 8", loc: "passenger_car", clue: "ตั๋วขบวนพิเศษที่มีการจองเกินจำนวนทางการ" },
    elias_ticket: { name_th: "ตั๋วโดยสารครึ่งใบหมายเลข 8", loc: "luggage_van", clue: "ชื่อผู้ถือถูกลบออก มีร่องรอยการขึ้นรถโดยไม่มีชื่อในระบบ" },
    manifest_altered: { name_th: "รายชื่อผู้โดยสารฉบับแก้ไข", loc: "conductor_office", clue: "บรรทัดที่ 8 มีรอยเขียนทับ ลายมือไม่ใช่ของพนักงานควบคุมรถ" },
    wine_receipt_2316: { name_th: "ใบเสร็จสั่งไวน์ 23:16", loc: "dining_car", clue: "มีการสั่งไวน์ก่อนไฟดับเพียง 1 นาที" },
    fuse_panel: { name_th: "แผงฟิวส์ระบบไฟฟ้า", loc: "electrical_compartment", clue: "ฟิวส์ถูกถอดออกด้วยมือ ทำให้ไฟดับทั่วขบวน 46 วินาที" },
    conductor_log: { name_th: "สมุดลงชื่อเบิกกุญแจ", loc: "conductor_office", clue: "มีการเบิกกุญแจห้องไฟฟ้าก่อนเกิดเหตุ" },
    heavy_wrench: { name_th: "ประแจเหล็กหนัก", loc: "luggage_van", clue: "เครื่องมือช่างที่มีคราบน้ำมันเครื่อง" }
  }
};

// Initial Active Game State
let gameState = {
  current_location: "passenger_car",
  elapsed_seconds: 0,
  inventory: ["seat8_ticket"],
  discovered_clues: ["crime_scene_record", "cassian_notebook"],
  interrogated_suspects: ["mara_voss"],
  visited_locations: ["passenger_car", "dining_car", "service_pantry"],
  solved_questions: [1]
};

// ============================================================
// 1. INITIALIZATION
// ============================================================
window.addEventListener("DOMContentLoaded", () => {
  initGame();
});

async function initGame() {
  setSystemStatus("กำลังเชื่อมต่อเซิร์ฟเวอร์...", "#38bdf8");

  try {
    const res = await fetch(`${API_BASE}/scene`, { signal: AbortSignal.timeout(2500) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sceneData = await res.json();

    isBackendConnected = true;
    if (sceneData.initial_state) {
      gameState = Object.assign(gameState, sceneData.initial_state);
    }
    if (sceneData.briefing) {
      document.getElementById("modalBriefingText").textContent = sceneData.briefing;
    }
    setSystemStatus("เชื่อมต่อ Backend สำเร็จ (Live API)", "#22c55e");
  } catch (e) {
    isBackendConnected = false;
    console.info("Running in Interactive Client Simulation mode:", e.message);
    setSystemStatus("โหมดจำลอง (Offline Mode)", "#eab308");
  }

  // Refresh all UI subsystems
  refreshAllUI();
}

function refreshAllUI() {
  updateHUD();
  updateTrainSchematic();
  updateDossier();
  renderChatHistoryLog();
}

// ============================================================
// 2. HUD & STATUS UPDATES
// ============================================================
function updateHUD() {
  const locData = STORY_REGISTRY.locations[gameState.current_location] || { name_th: gameState.current_location };
  
  // Location Pill
  const locHeader = document.getElementById("locHeader");
  if (locHeader) locHeader.textContent = locData.name_th;

  // Clock
  const elapsed = gameState.elapsed_seconds || 0;
  const baseMinutes = 23 * 60 + 17; // Start at 23:17
  const currentTotalMinutes = baseMinutes + Math.floor(elapsed / 60);
  const hrs = Math.floor((currentTotalMinutes / 60) % 24);
  const mins = Math.floor(currentTotalMinutes % 60);
  
  const clockHeader = document.getElementById("clockHeader");
  if (clockHeader) {
    clockHeader.textContent = `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
  }

  // Ambient Card updates based on location
  const ambientTag = document.getElementById("ambientTag");
  const ambientRow1 = document.getElementById("ambientRow1");
  const ambientRow2 = document.getElementById("ambientRow2");
  const ambientRow3 = document.getElementById("ambientRow3");
  const doorTag = document.getElementById("doorTag");

  if (ambientTag) ambientTag.textContent = locData.name_th.toUpperCase();
  if (ambientRow1) ambientRow1.textContent = "1938 NOCTURNE EXPRESS";
  if (ambientRow2) ambientRow2.textContent = `ตู้ปัจจุบัน: ${locData.name_th}`;
  if (ambientRow3) ambientRow3.textContent = `สำรวจแล้ว: ${gameState.visited_locations.length}/6 ตู้`;
  if (doorTag) doorTag.textContent = gameState.current_location.replace('_', ' ').toUpperCase();
}

function updateTrainSchematic() {
  const currentLoc = gameState.current_location;
  document.querySelectorAll(".train-cars-flex .car-card").forEach(card => {
    const locId = card.getAttribute("data-loc");
    const hull = card.querySelector(".car-hull");
    const existingPin = card.querySelector(".pin-marker");

    if (locId === currentLoc) {
      card.classList.add("active");
      if (hull) hull.classList.add("active-hull");
      if (!existingPin) {
        const pin = document.createElement("div");
        pin.className = "pin-marker";
        pin.textContent = "📍";
        card.prepend(pin);
      }
    } else {
      card.classList.remove("active");
      if (hull) hull.classList.remove("active-hull");
      if (existingPin) existingPin.remove();
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
// 3. RIGHT DOSSIER RENDERING (Evidence, Suspects, Chat History, 4 Pillars)
// ============================================================
function updateDossier() {
  renderEvidenceGrid();
  renderSuspectsGrid();
  renderFullSuspectsList();
  renderChatHistoryLog();
  renderPillarsMatrix();
}

function renderEvidenceGrid() {
  const grid = document.getElementById("evidenceGrid");
  if (!grid) return;

  const allFoundClues = Array.from(new Set([...(gameState.discovered_clues || []), ...(gameState.inventory || [])]));
  
  if (allFoundClues.length === 0) {
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #64748b; font-size: 11px; padding: 10px;">ยังไม่พบหลักฐานในบริเวณนี้ (ลองพิมพ์ 'ดูรอบๆ')</div>`;
    return;
  }

  grid.innerHTML = allFoundClues.slice(0, 6).map(clueId => {
    const item = STORY_REGISTRY.objects[clueId] || { name_th: clueId, loc: "unknown" };
    const locName = STORY_REGISTRY.locations[item.loc] ? STORY_REGISTRY.locations[item.loc].name_th : item.loc;
    return `
      <div class="item-slot" onclick="inspectClue('${clueId}', '${item.name_th}')" title="คลิกเพื่อตรวจสอบหลักฐานชิ้นนี้">
        <div class="slot-thumb">🔍</div>
        <div class="slot-name">${escapeHtml(item.name_th)}</div>
        <div class="slot-found">พบที่: ${escapeHtml(locName)} ➔</div>
      </div>
    `;
  }).join("");
}

function renderSuspectsGrid() {
  const grid = document.getElementById("suspectsGrid");
  if (!grid) return;

  const currentLocData = STORY_REGISTRY.locations[gameState.current_location] || {};
  const presentSuspects = currentLocData.suspects || [];

  if (presentSuspects.length === 0) {
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #64748b; font-size: 11px; padding: 10px;">ไม่มีผู้ต้องสงสัยอยู่ในตู้นี้</div>`;
    return;
  }

  grid.innerHTML = presentSuspects.map(suspectId => {
    const s = STORY_REGISTRY.suspects[suspectId] || { name_th: suspectId, role: "บุคคล", relationship: "---" };
    const isTarget = suspectId === "gideon_hart";
    return `
      <div class="suspect-slot ${isTarget ? 'target-suspect' : ''}" onclick="interrogateSuspect('${suspectId}', '${s.name_th}')" title="คลิกเพื่อสอบปากคำ">
        <div class="suspect-thumb">👤</div>
        <div class="suspect-name ${isTarget ? 'gold-name' : ''}">${escapeHtml(s.name_th.split('(')[0])}</div>
        <div class="suspect-role">${escapeHtml(s.role)}</div>
        <div class="suspect-rel">❖ ${escapeHtml(s.relationship)}</div>
      </div>
    `;
  }).join("");
}

function renderFullSuspectsList() {
  const listContainer = document.getElementById("fullSuspectsList");
  if (!listContainer) return;

  listContainer.innerHTML = Object.entries(STORY_REGISTRY.suspects).map(([id, s]) => {
    const isInterrogated = (gameState.interrogated_suspects || []).includes(id);
    const isTarget = id === "gideon_hart";
    return `
      <div class="suspect-card ${isTarget ? 'target' : ''}" style="margin-bottom: 8px; padding: 8px; background: #0f131c; border: 1px solid rgba(140,115,62,0.3); border-radius: 4px; cursor: pointer;" onclick="interrogateSuspect('${id}', '${s.name_th}')">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: ${isTarget ? '#f5d77f' : '#e2ded5'}; font-size: 12px;">👤 ${escapeHtml(s.name_th)}</strong>
          <span style="font-size: 10px; color: ${isInterrogated ? '#4ade80' : '#8c733e'};">${isInterrogated ? '✓ สอบปากคำแล้ว' : 'ยังไม่สอบปากคำ'}</span>
        </div>
        <div style="font-size: 10.5px; color: #94a3b8; margin: 3px 0;">บทบาท: ${escapeHtml(s.role)}</div>
        <div style="font-size: 10px; color: #d4af37;">ความสัมพันธ์: ${escapeHtml(s.relationship)}</div>
      </div>
    `;
  }).join("");
}

// Render Chat History Log (Tab 3)
function renderChatHistoryLog() {
  const container = document.getElementById("chatHistoryLog");
  if (!container) return;

  if (dialogueHistory.length === 0) {
    container.innerHTML = `<div style="text-align: center; color: #64748b; font-size: 11px; padding: 12px;">ยังไม่มีประวัติการพูดคุย</div>`;
    return;
  }

  container.innerHTML = dialogueHistory.map(entry => `
    <div class="history-turn-card">
      <div class="history-meta">
        <span class="history-turn-badge">เทิร์น #${entry.turn} (${entry.time})</span>
        <span class="history-speaker">${escapeHtml(entry.speaker)}</span>
      </div>
      <div class="history-user-query">💬 คุณสั่ง: "${escapeHtml(entry.userQuery)}"</div>
      <div class="history-response-text">${escapeHtml(entry.message).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</div>
    </div>
  `).reverse().join("");
}

function renderPillarsMatrix() {
  const listContainer = document.getElementById("pillarsDossierList");
  if (!listContainer) return;

  const suspectsToTrack = ["gideon_hart", "elias_venn", "clara_duval", "victor_kane"];

  listContainer.innerHTML = suspectsToTrack.map(suspectId => {
    const s = STORY_REGISTRY.suspects[suspectId];
    const isGideon = suspectId === "gideon_hart";
    
    // Check pillars based on discovered clues
    const hasMotive = gameState.discovered_clues.includes("cassian_notebook") && isGideon;
    const hasMeans = gameState.discovered_clues.includes("latch_scratches") || gameState.discovered_clues.includes("copper_wire");
    const hasOpportunity = gameState.discovered_clues.includes("crime_scene_record");
    const hasCorroboration = gameState.discovered_clues.includes("wine_receipt_2316") || gameState.discovered_clues.includes("broken_fuse");

    const pillars = [
      { name: "1. แรงจูงใจ (Motive)", ok: hasMotive, hint: hasMotive ? "สมุดบันทึกคดีเบลล์เวเธอร์" : "ยังไม่พบหลักฐาน" },
      { name: "2. วิธีการ (Means)", ok: hasMeans, hint: hasMeans ? "รอยลวดเกี่ยวกลอนประตู" : "ยังไม่พบหลักฐาน" },
      { name: "3. โอกาส (Opportunity)", ok: hasOpportunity, hint: hasOpportunity ? "บันทึกเวลาไฟดับ 46 วินาที" : "ยังไม่พบหลักฐาน" },
      { name: "4. หลักฐานสนับสนุน", ok: hasCorroboration, hint: hasCorroboration ? "พยานและใบเสร็จเวลา" : "ยังไม่พบหลักฐาน" }
    ];

    const score = pillars.filter(p => p.ok).length;

    return `
      <div class="pillar-table-card" style="margin-bottom: 10px; background: #0f131c; border: 1px solid rgba(140,115,62,0.3); border-radius: 4px; padding: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(140,115,62,0.2); padding-bottom: 4px; margin-bottom: 6px;">
          <strong style="color: ${isGideon ? '#f5d77f' : '#e2ded5'}; font-size: 11.5px;">👤 ${escapeHtml(s.name_th.split('(')[0])}</strong>
          <span style="font-size: 10px; background: rgba(212,175,55,0.15); color: #f5d77f; padding: 2px 6px; border-radius: 3px;">${score}/4 เสา</span>
        </div>
        ${pillars.map(p => `
          <div class="pillar-row-line">
            <span style="color: #cbd5e1; font-size: 10.5px;">${p.name}</span>
            <span class="pillar-stat-pill ${p.ok ? 'yes' : 'no'}" title="${p.hint}">
              ${p.ok ? '✓ พบแล้ว (' + p.hint + ')' : '✗ ยังไม่พบ'}
            </span>
          </div>
        `).join("")}
      </div>
    `;
  }).join("");
}

// ============================================================
// 4. COMMAND DISPATCHER & LOGIC ENGINE
// ============================================================
async function sendMessage(event) {
  if (event) event.preventDefault();

  const input = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");
  const sendBtnText = document.getElementById("sendBtnText");
  const text = input.value.trim();

  if (!text) return;

  // Lock input to prevent race conditions
  input.disabled = true;
  sendBtn.disabled = true;
  sendBtnText.textContent = "กำลังคิด...";
  setSystemStatus("กำลังประมวลผลคำสั่ง...", "#38bdf8");

  turnCount++;
  gameState.elapsed_seconds = (gameState.elapsed_seconds || 0) + 60; // 60s per turn

  const baseMinutes = 23 * 60 + 17;
  const currentTotalMinutes = baseMinutes + Math.floor(gameState.elapsed_seconds / 60);
  const hrs = Math.floor((currentTotalMinutes / 60) % 24);
  const mins = Math.floor(currentTotalMinutes % 60);
  const timeFormatted = `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;

  if (isBackendConnected) {
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

      if (data.new_state) gameState = data.new_state;
      renderDecision(data.decision, data.parsed);

      // Add to Dialogue History
      dialogueHistory.push({
        turn: turnCount,
        time: timeFormatted,
        userQuery: text,
        speaker: document.getElementById("speakerName").textContent || "ระบบ",
        role: document.getElementById("speakerRole").textContent || "",
        message: data.decision.message,
        allowed: data.decision.allowed
      });

      setSystemStatus("ระบบทำงานปกติ (Live API)", "#22c55e");
    } catch (err) {
      console.warn("Backend error during command, falling back to simulator:", err);
      processCommandSimulated(text, timeFormatted);
    }
  } else {
    // Client-side Interactive Simulation
    processCommandSimulated(text, timeFormatted);
  }

  refreshAllUI();

  // Unlock input
  input.value = "";
  input.disabled = false;
  sendBtn.disabled = false;
  sendBtnText.textContent = "ส่งคำสั่ง";
  input.focus();
}

function processCommandSimulated(text, timeFormatted) {
  const t = text.toLowerCase();
  let decision = {
    allowed: true,
    message: "",
    reasoning_chain: []
  };

  const currentLocData = STORY_REGISTRY.locations[gameState.current_location];

  // 1. Travel / Move Commands
  if (t.includes("ไปที่") || t.includes("เดินไป") || t.includes("ย้ายไป")) {
    let targetLoc = null;
    if (t.includes("จุดเกิดเหตุ") || t.includes("ห้องเก็บของ")) targetLoc = "service_pantry";
    else if (t.includes("ตู้เสบียง")) targetLoc = "dining_car";
    else if (t.includes("ตู้โดยสาร")) targetLoc = "passenger_car";
    else if (t.includes("ห้องไฟฟ้า")) targetLoc = "electrical_compartment";
    else if (t.includes("ห้องคุมรถ") || t.includes("ห้องพนักงาน")) targetLoc = "conductor_office";
    else if (t.includes("ตู้สัมภาระ")) targetLoc = "luggage_van";

    if (targetLoc) {
      gameState.current_location = targetLoc;
      if (!gameState.visited_locations.includes(targetLoc)) {
        gameState.visited_locations.push(targetLoc);
      }
      const newLoc = STORY_REGISTRY.locations[targetLoc];
      decision.message = `คุณเดินทางมาถึง **${newLoc.name_th}** ${newLoc.icon} — ${newLoc.description}`;
      decision.reasoning_chain = [
        { rule_id: "R01_PRESENCE", passed: true, description: `ย้ายตำแหน่งผู้เล่นไปยัง ${newLoc.name_th} สำเร็จ` },
        { rule_id: "R02_TEMPORAL", passed: true, description: "เวลาเดินหน้า +60 วินาทีตามกฎเทิร์น" }
      ];
      updateSpeakerSlot("ผู้บรรยาย", "สภาพพื้นที่");
    } else {
      decision.message = `ไม่พบตู้รถดังกล่าว กรุณาเลือกจากผังรถไฟด้านล่าง`;
      decision.allowed = false;
      decision.reasoning_chain = [{ rule_id: "R00_UNKNOWN_LOC", passed: false, description: "ไม่พบปลายทางในขบวนรถไฟ" }];
    }
  }
  // 2. Look Around / Explore
  else if (t.includes("ดูรอบ") || t.includes("สำรวจ") || t.includes("มีอะไร")) {
    const cluesInLoc = (currentLocData.objects || []).map(id => STORY_REGISTRY.objects[id] ? STORY_REGISTRY.objects[id].name_th : id);
    const suspectsInLoc = (currentLocData.suspects || []).map(id => STORY_REGISTRY.suspects[id] ? STORY_REGISTRY.suspects[id].name_th : id);

    // Auto-discover objects in this location
    (currentLocData.objects || []).forEach(id => {
      if (!gameState.discovered_clues.includes(id)) gameState.discovered_clues.push(id);
    });

    let details = currentLocData.description;
    if (cluesInLoc.length > 0) details += `\n\n🔍 **วัตถุ/หลักฐานที่สังเกตเห็น:** ${cluesInLoc.join(', ')}`;
    if (suspectsInLoc.length > 0) details += `\n👤 **บุคคลในบริเวณนี้:** ${suspectsInLoc.join(', ')}`;

    decision.message = details;
    decision.reasoning_chain = [
      { rule_id: "R01_PRESENCE", passed: true, description: `สำรวจพื้นที่ ${currentLocData.name_th}` },
      { rule_id: "R04_CLUE_DISCOVERY", passed: true, description: `บันทึกเบาะแสในห้องลงแฟ้มสืบสวน` }
    ];
    updateSpeakerSlot("ผู้บรรยาย", "การสำรวจ");
  }
  // 3. Inspect Clue / Evidence
  else if (t.includes("ตรวจ") || t.includes("ดู") || t.includes("อ่าน")) {
    let foundObjectKey = Object.keys(STORY_REGISTRY.objects).find(k => t.includes(STORY_REGISTRY.objects[k].name_th.toLowerCase()) || t.includes(k));
    
    if (foundObjectKey) {
      const obj = STORY_REGISTRY.objects[foundObjectKey];
      if (!gameState.discovered_clues.includes(foundObjectKey)) {
        gameState.discovered_clues.push(foundObjectKey);
      }
      decision.message = `🔎 **การตรวจสอบ: ${obj.name_th}**\n${obj.clue}`;
      decision.reasoning_chain = [
        { rule_id: "R04_CLUE_DISCOVERY", passed: true, description: `วิเคราะห์วัตถุ ${obj.name_th}` },
        { rule_id: "R03_MOTIVE_CHECK", passed: true, description: "เชื่อมโยงข้อมูลเข้ากับ Four Pillars Matrix" }
      ];

      if (foundObjectKey === "cassian_notebook" && !gameState.solved_questions.includes(4)) gameState.solved_questions.push(4);
      if (foundObjectKey === "latch_scratches" && !gameState.solved_questions.includes(2)) gameState.solved_questions.push(2);
      if (foundObjectKey === "fuse_panel" && !gameState.solved_questions.includes(3)) gameState.solved_questions.push(3);
      updateSpeakerSlot("การตรวจสอบ", "วัตถุพยาน");
    } else {
      decision.message = `คุณพยายามตรวจสอบ แต่ไม่พบวัตถุเป้าหมายที่ระบุในบริเวณนี้`;
      decision.reasoning_chain = [{ rule_id: "R01_PRESENCE", passed: false, description: "วัตถุไม่ได้อยู่ในระยะสายตาหรือตู้ปัจจุบัน" }];
    }
  }
  // 4. Interrogate Suspect
  else if (t.includes("สอบปากคำ") || t.includes("ถาม") || t.includes("คุยกับ")) {
    let suspectKey = Object.keys(STORY_REGISTRY.suspects).find(k => t.includes(STORY_REGISTRY.suspects[k].name_th.toLowerCase()) || t.includes(k.split('_')[0]));
    
    if (suspectKey) {
      const s = STORY_REGISTRY.suspects[suspectKey];
      if (!gameState.interrogated_suspects.includes(suspectKey)) {
        gameState.interrogated_suspects.push(suspectKey);
      }
      decision.message = `"${s.dialogue}"`;
      decision.reasoning_chain = [
        { rule_id: "R01_PRESENCE", passed: true, description: `สอบปากคำ ${s.name_th}` },
        { rule_id: "R05_INTERROGATION", passed: true, description: "บันทึกคำให้การเข้าสู่แฟ้มคดี" }
      ];
      updateSpeakerSlot(s.name_th, s.role, suspectKey);
    } else {
      decision.message = `ไม่พบบุคคลที่คุณต้องการพูดคุยด้วยในตู้นี้`;
      decision.allowed = false;
      decision.reasoning_chain = [{ rule_id: "R01_PRESENCE", passed: false, description: "ผู้ต้องสงสัยไม่ได้อยู่ในตู้เดียวกัน" }];
    }
  }
  // 5. Accuse Culprit
  else if (t.includes("กล่าวหา") || t.includes("จับกุม")) {
    if (t.includes("กิเดียน") || t.includes("gideon")) {
      const isComplete = gameState.discovered_clues.includes("cassian_notebook") && gameState.discovered_clues.includes("latch_scratches");
      if (isComplete) {
        decision.message = `🎉 **ข้อกล่าวหาถูกต้อง!** กิเดียน ฮาร์ต หน้าซีดเผือดเมื่อจำนนต่อหลักฐานสมุดบันทึกคดีเบลล์เวเธอร์และรอยลวดสะเดาะกลอน! เขาคือฆาตกรตัวจริงในคืนนี้!`;
        decision.reasoning_chain = [
          { rule_id: "R15_ACCUSATION_GROUNDING", passed: true, description: "หลักฐานครบทั้ง 4 เสา (Motive, Means, Opportunity, Corroboration)" },
          { rule_id: "R16_CASE_SOLVED", passed: true, description: "ผู้เล่นคลี่คลายปริศนาสำเร็จ" }
        ];
        if (!gameState.solved_questions.includes(1)) gameState.solved_questions.push(1);
      } else {
        decision.message = `⚠️ **ข้อกล่าวหาไม่สมบูรณ์:** คุณยังรวบรวมหลักฐาน 4 เสาหลักไม่ครบ! กิเดียน ฮาร์ต ปฏิเสธข้อกล่าวหาอย่างแข็งกร้าว`;
        decision.allowed = false;
        decision.reasoning_chain = [
          { rule_id: "R15_ACCUSATION_GROUNDING", passed: false, description: "หลักฐานยังไม่ครบ 4 เสา (ขาด Means หรือ Motive)" }
        ];
      }
      updateSpeakerSlot("กิเดียน ฮาร์ต (Gideon Hart)", "ผู้ต้องสงสัยหลัก", "gideon_hart");
    } else {
      decision.message = `ข้อกล่าวหาผิดคน! บุคคลนี้ไม่ใช่ผู้บงการคดีห้องปิดตาย`;
      decision.allowed = false;
      decision.reasoning_chain = [{ rule_id: "R15_ACCUSATION_GROUNDING", passed: false, description: "หลักฐานไม่ชี้ไปยังบุคคลนี้" }];
    }
  }
  // Default General Command
  else {
    decision.message = `คุณดำเนินการ: "${text}" — กำลังสังเกตการณ์รอบตัวเพื่อหาความเชื่อมโยงของคดี`;
    decision.reasoning_chain = [
      { rule_id: "R01_PRESENCE", passed: true, description: "คำสั่งผ่านการตรวจสอบบริบท" },
      { rule_id: "R02_TEMPORAL", passed: true, description: "บันทึกเวลาการกระทำสำเร็จ" }
    ];
  }

  renderDecision(decision, null);

  // Add to History
  dialogueHistory.push({
    turn: turnCount,
    time: timeFormatted,
    userQuery: text,
    speaker: document.getElementById("speakerName").textContent || "ระบบ",
    role: document.getElementById("speakerRole").textContent || "",
    message: decision.message,
    allowed: decision.allowed
  });
}

function renderDecision(decision, parsed) {
  const dialogueText = document.getElementById("dialogueText");
  const decisionBadge = document.getElementById("decisionBadge");
  const decisionBadgeText = document.getElementById("decisionBadgeText");
  const decisionVerdictText = document.getElementById("decisionVerdictText");
  const verdictBanner = document.getElementById("verdictBanner");
  const rulesCountBadge = document.getElementById("rulesCountBadge");
  const rulesLiveList = document.getElementById("rulesLiveList");
  const failAlertBox = document.getElementById("failAlertBox");

  if (!decision) return;

  // Dialogue text in Center Card
  if (dialogueText) {
    dialogueText.innerHTML = escapeHtml(decision.message).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  }

  // Allowed / Denied Badges
  if (decision.allowed) {
    if (decisionBadge) decisionBadge.className = "decision-tag allowed";
    if (decisionBadgeText) decisionBadgeText.textContent = "✓ ALLOWED (ผ่านกฎ)";
    if (verdictBanner) verdictBanner.className = "verdict-banner allowed";
    if (decisionVerdictText) {
      decisionVerdictText.className = "verdict-title allowed";
      decisionVerdictText.textContent = "✓ ตรวจสอบผ่าน (ALLOWED)";
    }
  } else {
    if (decisionBadge) decisionBadge.className = "decision-tag denied";
    if (decisionBadgeText) decisionBadgeText.textContent = "✗ DENIED (ปฏิเสธ)";
    if (verdictBanner) verdictBanner.className = "verdict-banner denied";
    if (decisionVerdictText) {
      decisionVerdictText.className = "verdict-title denied";
      decisionVerdictText.textContent = "✗ ปฏิเสธการกระทำ (DENIED)";
    }
  }

  // Reasoning Chain (FE-1 in Left Panel)
  const steps = decision.reasoning_chain || [];
  if (rulesCountBadge) {
    const passedCount = steps.filter(s => s.passed).length;
    rulesCountBadge.textContent = `ผ่าน ${passedCount}/${steps.length}`;
    rulesCountBadge.className = decision.allowed ? "box-badge pass" : "box-badge warn";
  }

  if (rulesLiveList) {
    if (steps.length === 0) {
      rulesLiveList.innerHTML = `
        <div class="wireframe-rule-item">
          <div class="wireframe-rule-head">
            <span class="rule-bullet">■</span>
            <strong class="rule-title">Reasoning Chain</strong>
          </div>
        </div>
      `;
    } else {
      rulesLiveList.innerHTML = steps.map((s, idx) => `
        <div class="wireframe-rule-item ${s.passed ? 'pass' : 'fail'}">
          <div class="wireframe-rule-head">
            <span class="rule-bullet" style="color: ${s.passed ? 'var(--px-green)' : 'var(--px-red)'}; font-weight: 700;">${s.passed ? '✓' : '✗'}</span>
            <strong class="rule-title">${escapeHtml(s.rule_id || `Reasoning #${idx + 1}`)}</strong>
          </div>
          ${s.description ? `<div class="rule-desc">${escapeHtml(s.description)}</div>` : ''}
        </div>
      `).join("");
    }
  }

  // Fail Alert Box in Left Panel
  if (failAlertBox) {
    if (!decision.allowed) {
      const failed = steps.find(s => !s.passed);
      failAlertBox.style.display = "block";
      failAlertBox.textContent = failed 
        ? `⚠️ ละเมิดกฎ: ${failed.rule_id} — ${failed.description}`
        : `⚠️ การกระทำนี้ถูกปฏิเสธโดยระบบ Guardrail`;
    } else {
      failAlertBox.style.display = "none";
    }
  }
}

function updateSpeakerSlot(name, role, suspectId = "mara_voss") {
  const speakerName = document.getElementById("speakerName");
  const speakerRole = document.getElementById("speakerRole");
  const slot = document.getElementById("silhouetteSlot");

  if (speakerName) speakerName.textContent = name;
  if (speakerRole) speakerRole.textContent = role;

  if (slot) {
    if (suspectId === "gideon_hart") {
      slot.innerHTML = `
        <svg viewBox="0 0 64 80" class="silhouette-vector">
          <g fill="#070a0f" stroke="#d4a32a" stroke-width="0.8">
            <rect x="24" y="6" width="16" height="4" />
            <rect x="20" y="10" width="24" height="6" />
            <rect x="22" y="16" width="20" height="16" />
            <rect x="26" y="32" width="12" height="6" />
            <rect x="20" y="38" width="24" height="6" fill="#1b2332" />
            <rect x="12" y="42" width="40" height="10" />
            <rect x="8" y="52" width="48" height="12" />
            <rect x="4" y="64" width="56" height="16" />
          </g>
          <rect x="28" y="38" width="8" height="8" fill="#ffd452" />
          <rect x="30" y="42" width="4" height="4" fill="#d4a32a" />
        </svg>
      `;
    } else if (suspectId === "elias_venn") {
      slot.innerHTML = `
        <svg viewBox="0 0 64 80" class="silhouette-vector">
          <g fill="#070a0f" stroke="#8c6619" stroke-width="0.8">
            <rect x="26" y="8" width="12" height="6" />
            <rect x="22" y="14" width="20" height="16" />
            <rect x="26" y="30" width="12" height="6" />
            <rect x="16" y="36" width="32" height="8" />
            <rect x="12" y="44" width="40" height="12" />
            <rect x="6" y="56" width="52" height="24" />
          </g>
          <rect x="26" y="18" width="12" height="3" fill="#38bdf8" />
          <rect x="29" y="36" width="6" height="6" fill="#8c6619" />
        </svg>
      `;
    } else {
      slot.innerHTML = `
        <svg viewBox="0 0 64 80" class="silhouette-vector">
          <g fill="#070a0f" stroke="#8c6619" stroke-width="0.8">
            <rect x="26" y="8" width="12" height="4" />
            <rect x="22" y="12" width="20" height="4" />
            <rect x="20" y="16" width="24" height="6" />
            <rect x="22" y="22" width="20" height="12" />
            <rect x="26" y="34" width="12" height="6" />
            <rect x="22" y="38" width="20" height="4" fill="#141c28" />
            <rect x="14" y="40" width="36" height="8" />
            <rect x="10" y="48" width="44" height="10" />
            <rect x="6" y="58" width="52" height="12" />
            <rect x="4" y="70" width="56" height="10" />
          </g>
          <rect x="30" y="40" width="4" height="8" fill="#d4a32a" />
          <rect x="31" y="43" width="2" height="2" fill="#ffd452" />
        </svg>
      `;
    }
  }
}

// ============================================================
// 5. INTERACTIVE SHORTCUTS & CLICKS
// ============================================================
function quickMove(locId) {
  const loc = STORY_REGISTRY.locations[locId];
  const locName = loc ? loc.name_th : locId;
  fillInput(`ไปที่ ${locName}`);
  sendMessage();
}

function inspectClue(clueId, clueName) {
  fillInput(`ตรวจดู ${clueName}`);
  sendMessage();
}

function interrogateSuspect(suspectId, suspectName) {
  fillInput(`สอบปากคำ ${suspectName}`);
  sendMessage();
}

function executeChip(commandText) {
  fillInput(commandText);
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
  const tag = document.getElementById("verdictModeTag");

  if (mode === "B") {
    btnB.classList.add("active");
    btnA.classList.remove("active");
    if (tag) tag.textContent = "NESY B";
  } else {
    btnA.classList.add("active");
    btnB.classList.remove("active");
    if (tag) tag.textContent = "LLM A";
  }
}

function switchRightTab(tabId) {
  const tabBtnEvidence = document.getElementById("tabBtnEvidence");
  const tabBtnSuspects = document.getElementById("tabBtnSuspects");
  const tabBtnHistory = document.getElementById("tabBtnHistory");
  const tabBtnPillars = document.getElementById("tabBtnPillars");

  const paneEvidence = document.getElementById("tabContentEvidence");
  const paneSuspects = document.getElementById("tabContentSuspects");
  const paneHistory = document.getElementById("tabContentHistory");
  const panePillars = document.getElementById("tabContentPillars");

  [tabBtnEvidence, tabBtnSuspects, tabBtnHistory, tabBtnPillars].forEach(btn => btn && btn.classList.remove("active"));
  [paneEvidence, paneSuspects, paneHistory, panePillars].forEach(pane => pane && pane.classList.remove("active"));

  if (tabId === "evidence") {
    if (tabBtnEvidence) tabBtnEvidence.classList.add("active");
    if (paneEvidence) paneEvidence.classList.add("active");
  } else if (tabId === "suspects") {
    if (tabBtnSuspects) tabBtnSuspects.classList.add("active");
    if (paneSuspects) paneSuspects.classList.add("active");
  } else if (tabId === "history") {
    if (tabBtnHistory) tabBtnHistory.classList.add("active");
    if (paneHistory) paneHistory.classList.add("active");
    renderChatHistoryLog();
  } else if (tabId === "pillars") {
    if (tabBtnPillars) tabBtnPillars.classList.add("active");
    if (panePillars) panePillars.classList.add("active");
  }
}

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
