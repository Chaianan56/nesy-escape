/**
 * chat.test.mjs — ทดสอบตรรกะการส่งคำสั่งของหน้าเว็บ
 *
 * ทดสอบสามกรณีที่เคยพลาดมาแล้วและมองไม่เห็นจากฝั่ง Python
 *   1. กดซ้อน       — ส่งคำสั่งใหม่ทั้งที่คำสั่งเดิมยังไม่กลับ
 *   2. เน็ตหลุด      — fetch พังกลางคำสั่งพ่วง
 *   3. คดีปิด        — กล่าวหาผ่านปุ่มคำสั่งพ่วงแล้วหน้าจอต้องปิด
 *
 * ใช้ node ล้วน ไม่มีไลบรารีเพิ่ม โหลด chat.js เข้าไปใน vm พร้อม DOM ปลอมตัวเล็กๆ
 * เท่าที่ไฟล์นั้นใช้จริง
 *
 * รันด้วย:  node --test frontend/chat.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const SRC = readFileSync(new URL("./chat.js", import.meta.url), "utf-8");

// ---------- DOM ปลอม เท่าที่ chat.js แตะจริง ----------
function makeDom() {
  const byId = new Map();
  const make = (id = "") => {
    const node = {
      id, value: "", placeholder: "", className: "", innerHTML: "",
      disabled: false, scrollTop: 0, scrollHeight: 0, type: "", onclick: null,
      children: [],
      set textContent(v) { this._text = String(v); this.innerHTML = String(v); },
      get textContent() { return this._text || ""; },
      focus() {},
      remove() { byId.delete(this.id); },
      appendChild(c) { this.children.push(c); if (c.id) byId.set(c.id, c); return c; },
      querySelector() { return make(); },
    };
    return node;
  };
  for (const id of ["chatInput", "sendBtn", "sendBtnText", "chatFeed",
                    "locText", "clockText", "clockWidget"]) {
    byId.set(id, make(id));
  }
  return {
    byId,
    document: {
      getElementById: (id) => byId.get(id) || null,
      createElement: () => make(),
    },
  };
}

/** โหลด chat.js ขึ้นมาหนึ่งชุด พร้อม fetch ที่เราคุมเอง */
function loadChat(fetchImpl) {
  const dom = makeDom();
  const sandbox = {
    window: { location: { protocol: "http:" }, addEventListener() {} },
    document: dom.document,
    fetch: fetchImpl,
    console,
    setInterval: () => 1,
    clearInterval() {},
    AbortSignal: { timeout: () => null },
  };
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox, { filename: "chat.js" });
  // ตั้งสถานะเริ่มต้นให้เลย จะได้ไม่ต้องผ่าน /scene ทุกครั้ง เหมือนตอน initGame ทำงานจบแล้ว
  vm.runInContext('gameState = { current_location: "lounge_car", elapsed_seconds: 0 }', sandbox);
  // let/const อยู่ใน global lexical scope ไม่ใช่ property ของ sandbox จึงต้องอ่านผ่าน eval
  const read = (expr) => vm.runInContext(expr, sandbox);
  return { sandbox, dom, read, el: (id) => dom.byId.get(id) };
}

/** คำตอบปลอมของ POST /command */
function reply({ allowed = true, ending = null, state = {} } = {}) {
  return {
    ok: true,
    json: async () => ({
      parsed: { action: "examine", target: "x", alternatives: [] },
      decision: { allowed, message: "ok", reasoning_chain: [], violated_rule_id: null },
      new_state: { current_location: "lounge_car", elapsed_seconds: 60,
                   ending_id: ending, ...state },
    }),
  };
}

const SCENE = {
  ok: true,
  json: async () => ({ initial_state: { current_location: "lounge_car", elapsed_seconds: 0 },
                       time_limit_seconds: 5400, locations: {}, objects: {},
                       suspects: {}, rules_count: 10, briefing: "b" }),
};

/** fetch ที่หน่วงคำตอบไว้จนกว่าเราจะสั่งปล่อย ใช้จำลองช่วงที่คำสั่งยังค้างอยู่ในสาย */
function pendingFetch() {
  const calls = [];
  const fetchImpl = (url) => {
    if (String(url).endsWith("/scene")) return Promise.resolve(SCENE);
    let release;
    const p = new Promise((res) => { release = res; });
    calls.push({ url, release });
    return p;
  };
  return { fetchImpl, calls };
}

const ev = { preventDefault() {} };
// รอให้ microtask ที่ค้างอยู่วิ่งจนหมดก่อน setImmediate จึงจะถูกเรียก
const flush = () => new Promise((r) => setImmediate(r));
const step = { action: "examine", target: "pocket_watch", label: "นาฬิกาพก" };

test("เวลาที่อ่านเฉยๆ ทำให้คดีหมดเวลาได้โดยไม่ส่งคำสั่ง", async () => {
  const urls = [];
  const chat = loadChat(async (url) => {
    urls.push(url);
    return reply({ allowed: false, ending: "cold_arrival" });
  });
  chat.read('timeLimitSeconds = 10; clockElapsed = 0; clockAnchor = Date.now() - 11000');
  await chat.sandbox.tickClock();
  assert.deepEqual(urls, ["/clock"]);
  assert.equal(chat.read("gameOver"), true);
  assert.equal(chat.el("chatInput").disabled, true);
});

test("ก่อนหมดเวลานาฬิกาเดินโดยไม่เรียก Gemini", async () => {
  let calls = 0;
  const chat = loadChat(async () => { calls++; return reply(); });
  chat.read('timeLimitSeconds = 100; clockElapsed = 0; clockAnchor = Date.now() - 5000');
  await chat.sandbox.tickClock();
  assert.equal(calls, 0);
  assert.equal(chat.el("clockText").textContent, "01:35");
});

test("คำตอบที่กลับช้าไม่เปิดคดีซ้ำหลังนาฬิกาปิดคดี", async () => {
  const pending = pendingFetch();
  const chat = loadChat(pending.fetchImpl);
  const action = chat.sandbox.submit("ดูรอบๆ");
  await flush();
  chat.read('gameState.ending_id = "cold_arrival"; showGameOver()');
  pending.calls[0].release(reply());
  await action;
  assert.equal(chat.read("gameState.ending_id"), "cold_arrival");
  assert.equal(chat.el("chatInput").disabled, true);
});


test("กดส่งซ้อนตอนคำสั่งเดิมยังไม่กลับ ต้องยิงไปหลังบ้านครั้งเดียว", async () => {
  const { fetchImpl, calls } = pendingFetch();
  const { sandbox, el, read } = loadChat(fetchImpl);

  el("chatInput").value = "ดูรอบๆ";
  const first = sandbox.sendMessage(ev);
  await flush();                    // ปล่อยให้ sendMessage วิ่งไปถึง fetch

  assert.equal(read("busy"), true, "ต้องล็อกทันทีที่เริ่มส่ง");
  assert.equal(el("chatInput").disabled, true);

  el("chatInput").value = "ดูอีกที";
  await sandbox.sendMessage(ev);     // ครั้งที่สองต้องถูกล็อกกั้นไว้
  assert.equal(calls.length, 1, `ยิงไป ${calls.length} ครั้ง ควรเป็น 1`);

  calls[0].release(reply());
  await first;
  assert.equal(read("busy"), false, "เสร็จแล้วต้องปลดล็อก");
  assert.equal(el("chatInput").disabled, false);
});


test("เน็ตหลุดกลางคำสั่งพ่วง ต้องขึ้นข้อความบอก และปลดล็อกกลับมา", async () => {
  let n = 0;
  const { sandbox, el, read } = loadChat(async (url) => {
    if (String(url).endsWith("/scene")) return SCENE;
    if (++n === 1) return reply();
    throw new TypeError("Failed to fetch");     // ขั้นที่สองเน็ตหลุด
  });

  await sandbox.runSteps([step, step, step]);

  const shown = el("chatFeed").children.map((c) => c.innerHTML).join("\n");
  assert.match(shown, /เชื่อมต่อไม่ได้/, "ต้องบอกผู้เล่นว่าต่อไม่ติด");
  assert.match(shown, /ยกเลิกอีก 1 ขั้น/, "ต้องบอกว่าขั้นที่เหลือถูกยกเลิก");
  assert.equal(read("busy"), false, "พังแล้วก็ต้องปลดล็อก ไม่ใช่ค้าง");
  assert.equal(el("chatInput").disabled, false);
});


test("คดีปิดระหว่างคำสั่งพ่วง ต้องหยุดขั้นที่เหลือและปิดหน้าจอ", async () => {
  let n = 0;
  const { sandbox, el, read } = loadChat(async (url) => {
    if (String(url).endsWith("/scene")) return SCENE;
    return ++n === 1 ? reply({ ending: "true_ending" }) : reply();
  });

  await sandbox.runSteps([step, step, step]);

  assert.equal(n, 1, `ยิงไป ${n} ครั้ง คดีปิดตั้งแต่ขั้นแรกแล้ว`);
  assert.equal(read("gameOver"), true);
  assert.equal(el("chatInput").disabled, true, "คดีปิดแล้วต้องพิมพ์ต่อไม่ได้");
  assert.equal(el("sendBtnText").textContent, "จบเกม");

  el("chatInput").value = "ถามต่อ";
  await sandbox.sendMessage(ev);
  assert.equal(n, 1, "คดีปิดแล้วยังส่งคำสั่งได้อีก");
});


test("ขั้นที่ถูกกฎปฏิเสธ ต้องยกเลิกขั้นที่เหลือ", async () => {
  let n = 0;
  const { sandbox, el } = loadChat(async (url) => {
    if (String(url).endsWith("/scene")) return SCENE;
    return ++n === 1 ? reply({ allowed: false }) : reply();
  });

  await sandbox.runSteps([step, step]);

  assert.equal(n, 1, "ขั้นแรกไม่ผ่าน ขั้นที่สองไม่ควรถูกยิง");
  const shown = el("chatFeed").children.map((c) => c.innerHTML).join("\n");
  assert.match(shown, /ยกเลิกอีก 1 ขั้น/);
});


test("กดปุ่มคำสั่งพ่วงตอนมีคำสั่งค้างอยู่ ต้องไม่แทรกเข้าไป", async () => {
  const { fetchImpl, calls } = pendingFetch();
  const { sandbox, el } = loadChat(fetchImpl);

  el("chatInput").value = "ดูรอบๆ";
  const first = sandbox.sendMessage(ev);
  await flush();

  await sandbox.runSteps([step]);
  assert.equal(calls.length, 1, "คำสั่งพ่วงไม่ควรแทรกระหว่างที่คำสั่งเดิมยังค้าง");

  calls[0].release(reply());
  await first;
});
