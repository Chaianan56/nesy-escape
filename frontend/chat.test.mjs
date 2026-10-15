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

test("กล่าวหาไม่ต้องเปิดสมุดหรือแปลงเลขหลักฐาน", async () => {
  let body;
  let journalRequests = 0;
  const c = loadChat(async (url, options) => {
    if (url.endsWith('/journal')) journalRequests++;
    body=JSON.parse(options.body); return reply();
  });
  await c.sandbox.submit('กล่าวหากิเดียน หลักฐาน: 2, 1');
  assert.deepEqual(body,{text:'กล่าวหากิเดียน หลักฐาน: 2, 1'});
  assert.equal(journalRequests,0);
});

test("การกล่าวหาไม่ต้องเลือกเลขหลักฐาน", async () => {
  let commands=0;
  const c = loadChat(async (url, options) => {
    if (url.endsWith('/command')) { commands++; assert.deepEqual(JSON.parse(options.body), {text:'กล่าวหากิเดียน หลักฐาน: 99'}); }
    return reply();
  });
  await c.sandbox.submit('กล่าวหากิเดียน หลักฐาน: 99');
  assert.equal(commands,1);
});

test("ส่งหลักฐานที่เลือกได้เฉพาะตอนเสนอข้อสรุป", async () => {
  let body;
  const c = loadChat(async (url, options) => {
    body = JSON.parse(options.body);
    return reply();
  });
  await c.sandbox.submit('กล่าวหา', {submittedEvidence: ['pocket_watch']});
  assert.deepEqual(body, {text: 'กล่าวหา', submitted_evidence: ['pocket_watch']});
});

test("ส่งเฉพาะข้อความ ไม่ส่งสถานะที่ client แก้เอง", async () => {
  let body;
  const c = loadChat(async (url, options) => {
    body = JSON.parse(options.body);
    return reply();
  });
  await c.sandbox.submit("ดูรอบๆ");
  assert.deepEqual(body, { text: "ดูรอบๆ" });
});

test("เริ่มคดีใหม่ต้องรีเซ็ต server สำเร็จก่อนโหลดหน้า", async () => {
  const calls = [];
  const c = loadChat(async (url, options) => {
    calls.push([url, options.method]);
    return { ok: true };
  });
  c.sandbox.window.location.reload = () => calls.push("reload");
  await c.sandbox.restartGame();
  assert.deepEqual(calls, [["/new-game", "POST"], "reload"]);
});

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
                    "locText", "clockText", "clockWidget", "endingStatus", "retryEnding", "restartGame"]) {
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
test("เป้าหมายพาไปที่เกิดเหตุ แล้วคนที่ยังไม่ได้คุย แล้วตู้ที่ยังไม่ได้ไป", () => {
  const c = loadChat(async () => reply());
  c.read(`locationsMap = {locomotive:'ตู้ 1: หัวรถจักร', first_class_car:'ตู้ 4: ชั้นหนึ่ง', lounge_car:'ตู้ 5: เลานจ์', second_class_car:'ตู้ 6: ชั้นสอง'};
    suspectsMap = {gideon_hart:'กิเดียน ฮาร์ต (Gideon Hart)', vincent_gray:'วินเซนต์ เกรย์ (Vincent Gray)'};
    suspectLocations = {gideon_hart:'lounge_car', vincent_gray:'second_class_car'}; restrictedLocations = ['locomotive'];`);
  const goal = (s) => c.read(`nextObjective(${JSON.stringify(s)})`);
  assert.match(goal({current_location:'lounge_car', visited_locations:['lounge_car']}), /ตู้ 4/);
  assert.equal(goal({current_location:'second_class_car', visited_locations:['first_class_car'], interrogated_suspects:[]}), 'ยังไม่ได้คุยกับผู้โดยสาร (ตู้ 6)');
  assert.equal(goal({visited_locations:['first_class_car'], interrogated_suspects:['gideon_hart','vincent_gray']}), 'ยังไม่ได้สำรวจ ตู้ 5, ตู้ 6');
  assert.match(goal({visited_locations:['first_class_car','lounge_car','second_class_car'], interrogated_suspects:['gideon_hart','vincent_gray']}), /กล่าวหา/);
});

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


test("คำสั่งพ่วงทำต่อกันเอง และหยุดรอยืนยันก่อนกล่าวหา", async () => {
  const bodies = [];
  const { sandbox, el } = loadChat(async (url, options) => {
    if (String(url).endsWith("/scene")) return SCENE;
    const text = JSON.parse(options.body).text;
    bodies.push(text);
    if (bodies.length > 1) return reply();
    const r = reply({ allowed: false });
    const data = await r.json();
    data.parsed = { action: "ambiguous", sequence: true,
                    alternatives: ["examine pocket_watch", "move first_class_car", "accuse gideon_hart"] };
    return { ok: true, json: async () => data };
  });
  el("chatInput").value = "ตรวจนาฬิกา ไปตู้ 4 แล้วกล่าวหากิเดียน";
  await sandbox.sendMessage(ev);
  assert.deepEqual(bodies, ["ตรวจนาฬิกา ไปตู้ 4 แล้วกล่าวหากิเดียน",
                            "examine pocket_watch", "move first_class_car"]);
  const shown = el("chatFeed").children.map((c) => c.innerHTML).join("\n");
  assert.match(shown, /ย้อนกลับไม่ได้/, "ต้องหยุดถามก่อนกล่าวหา");
});


test("timeout is an ending, with restart outside the transcript", async () => {
  const c = loadChat(async () => reply({allowed:false, ending:'cold_arrival'}));
  c.read('timeLimitSeconds = 1; clockElapsed = 2; clockAnchor = Date.now()');
  await c.sandbox.tickClock();
  const html = c.el('chatFeed').children.map(n=>n.innerHTML).join('');
  assert.match(html, /หมดเวลา · รถไฟถึงปลายทาง/);
  assert.doesNotMatch(html, /DENIED|ไม่ผ่านกฎ|restartGame/);
  assert.equal(c.el('restartGame').hidden, false);
});

test("confirmation failures stop after three attempts and can be retried", async () => {
  let calls = 0;
  const c = loadChat(async () => {
    if (++calls <= 3) throw Error('offline');
    return reply({allowed:false, ending:'cold_arrival'});
  });
  c.read('timeLimitSeconds = 1; clockElapsed = 2; clockAnchor = Date.now()');
  for(let i=0;i<5;i++) await c.sandbox.tickClock();
  assert.equal(calls,3);
  assert.equal(c.el('retryEnding').hidden,false);
  assert.equal(c.el('chatInput').disabled,true);
  assert.equal(c.read('gameOver'),false);
  await c.sandbox.retryEnding();
  assert.equal(calls,4);
  assert.equal(c.read('gameOver'),true);
  assert.equal(c.el('retryEnding').hidden,true);
});

test("command timeout uses the same terminal presentation", async () => {
  const c = loadChat(async () => reply({allowed:false, ending:'cold_arrival'}));
  await c.sandbox.submit('ดูรอบๆ', {isRoomLook:true});
  assert.match(c.el('chatFeed').children.at(-1).innerHTML,/หมดเวลา/);
  assert.equal(c.el('restartGame').hidden,false);
});

test("late clock failure cannot overwrite a completed ending", async () => {
  let reject;
  const c = loadChat(() => new Promise((_, fail)=>{reject=fail;}));
  c.read('timeLimitSeconds = 1; clockElapsed = 2; clockAnchor = Date.now()');
  const pending = c.sandbox.tickClock();
  c.read('gameState.ending_id = "cold_arrival"; showGameOver()');
  reject(Error('offline'));
  await pending;
  assert.equal(c.el('endingStatus').hidden,true);
  assert.equal(c.el('retryEnding').hidden,true);
});


test("late HTTP error cannot append a rejection after the ending", async () => {
  const pending = pendingFetch();
  const c = loadChat(pending.fetchImpl);
  const request = c.sandbox.submit('ดูรอบๆ');
  await flush();
  c.read('gameState.ending_id = "cold_arrival"; showGameOver()');
  const count = c.el('chatFeed').children.length;
  pending.calls[0].release({ok:false,status:500,json:async()=>({detail:'failure'})});
  await request;
  assert.equal(c.el('chatFeed').children.length,count);
});


test("reload of an expired session restores the ending and restart control", async () => {
  const urls = [];
  const c = loadChat(async url => {
    urls.push(url);
    if(url === '/scene') {
      const scene = await SCENE.json();
      scene.initial_state = {current_location:'lounge_car',elapsed_seconds:5400,ending_id:'cold_arrival',started_at:100};
      return {ok:true,json:async()=>scene};
    }
    return reply({allowed:false,ending:'cold_arrival',state:{elapsed_seconds:5400}});
  });
  await c.sandbox.initGame();
  assert.deepEqual(urls,['/scene','/command']);
  assert.equal(c.read('gameOver'),true);
  assert.equal(c.el('restartGame').hidden,false);
  assert.equal(c.el('chatInput').disabled,true);
  assert.match(c.el('chatFeed').children.at(-1).innerHTML,/หมดเวลา/);
});

test("pending confirmation does not issue duplicate requests", async () => {
  const pending = pendingFetch();
  const c = loadChat(pending.fetchImpl);
  c.read('timeLimitSeconds = 1; clockElapsed = 2; clockAnchor = Date.now()');
  const first = c.sandbox.tickClock();
  await c.sandbox.tickClock();
  await c.sandbox.retryEnding();
  assert.equal(pending.calls.length,1);
  pending.calls[0].release(reply({allowed:false,ending:'cold_arrival'}));
  await first;
  assert.equal(c.read('gameOver'),true);
});

test("server clock correction clears confirmation and unlocks input", async () => {
  const c = loadChat(async () => reply({state:{elapsed_seconds:2}}));
  c.read('timeLimitSeconds = 10; clockElapsed = 11; clockAnchor = Date.now()');
  await c.sandbox.tickClock();
  assert.equal(c.read('deadlineReached'),false);
  assert.equal(c.el('endingStatus').hidden,true);
  assert.equal(c.el('chatInput').disabled,false);
});


test("backend sequences execute once and only pending steps await confirmation", async () => {
  const sent = [];
  const c = loadChat(async (url, options) => {
    sent.push(JSON.parse(options.body).text);
    const data = await reply().json();
    data.parsed = {action:'sequence',sequence:false,alternatives:['move first_class_car','burn burnt_folder_c']};
    data.pending_steps = ['burn burnt_folder_c'];
    return {ok:true,json:async()=>data};
  });
  c.el('chatInput').value = 'ไปตู้ 4 แล้วเผาเอกสาร';
  await c.sandbox.sendMessage(ev);
  assert.deepEqual(sent,['ไปตู้ 4 แล้วเผาเอกสาร']);
  const confirmation = c.el('chatFeed').children.at(-1);
  assert.match(confirmation.innerHTML,/ย้อนกลับไม่ได้/);
  assert.match(confirmation.children[0].children[0].textContent,/ยืนยัน/);
  confirmation.children[0].children[0].onclick();
  await flush();
  assert.deepEqual(sent,['ไปตู้ 4 แล้วเผาเอกสาร','burn burnt_folder_c']);
});

test("completed backend sequence is never replayed by the frontend", async () => {
  let calls=0;
  const c = loadChat(async () => {
    calls++;
    const data = await reply().json();
    data.parsed = {action:'sequence',sequence:false,alternatives:['move first_class_car','examine pocket_watch']};
    data.pending_steps=[];
    return {ok:true,json:async()=>data};
  });
  c.el('chatInput').value='ไปตู้ 4 แล้วตรวจนาฬิกา';
  await c.sandbox.sendMessage(ev);
  assert.equal(calls,1);
  assert.doesNotMatch(c.el('chatFeed').children.at(-1).innerHTML,/ย้อนกลับไม่ได้|ตีความได้/);
});


test("new conversation notes appear after the answer", async () => {
  const c=loadChat(async()=>{
    const data=await reply().json();
    data.conversation_summaries=[{person:'กิเดียน',entries:[{name:'ที่อยู่',description:'คำให้การใหม่'}]}];
    return {ok:true,json:async()=>data};
  });
  await c.sandbox.submit('สอบปากคำกิเดียน');
  const summary=c.el('chatFeed').children.at(-1);
  assert.match(summary.className,/conversation-summary/);
  assert.match(summary.innerHTML,/คำให้การใหม่/);
  assert.match(summary.innerHTML,/ประเด็นค้าง/);
});

// The scene player owns a promise that resolves when reading finishes (or the
// clock closes it). Exercise the real send/sequence flow around that boundary.
function pendingStoryScenes(chat) {
  const played = [], replayed = [];
  let finish, stops = 0;
  chat.sandbox.StoryScenes = {
    play(scene) {
      played.push(scene);
      return new Promise(resolve => { finish = resolve; });
    },
    appendReplay(scene) { replayed.push(scene); },
    stop() { stops++; finish?.(); },
  };
  return {played, replayed, finish: () => finish(), stops: () => stops};
}

async function confrontationReply({allowed = true, pending = []} = {}) {
  const data = await reply({allowed}).json();
  data.parsed = pending.length
    ? {action:'sequence', sequence:false, alternatives:['interrogate gideon_hart', ...pending]}
    : {action:'interrogate', target:'gideon_hart', topic:'confrontation', alternatives:[]};
  data.narrative_scene = {id:'gideon_confrontation', title:'สองเวลา', pages:[{text:'บทสนทนา'}]};
  data.pending_steps = pending;
  return {ok:true, json:async()=>data};
}

test("approved confrontation finishes before a pending sequence resumes", async () => {
  const sent = [];
  const c = loadChat(async (url, options) => {
    sent.push(JSON.parse(options.body).text);
    return sent.length === 1
      ? confrontationReply({pending:['move first_class_car']}) : reply();
  });
  const scenes = pendingStoryScenes(c);
  c.el('chatInput').value = 'ทักท้วงกิเดียนแล้วไปตู้ 4';
  let finished = false;
  const action = c.sandbox.sendMessage(ev).then(() => { finished = true; });
  await flush();
  assert.equal(scenes.played.length, 1);
  assert.equal(scenes.played[0].id, 'gideon_confrontation');
  assert.equal(scenes.replayed.length, 1);
  assert.equal(finished, false);
  assert.equal(c.read('busy'), true);
  assert.equal(c.el('chatInput').disabled, true);
  assert.deepEqual(sent, ['ทักท้วงกิเดียนแล้วไปตู้ 4']);

  scenes.finish();
  await action;
  assert.deepEqual(sent, ['ทักท้วงกิเดียนแล้วไปตู้ 4', 'move first_class_car']);
  assert.equal(scenes.played.length, 1, 'the completed interrogation must not be replayed');
  assert.equal(c.read('busy'), false);
  assert.equal(c.el('chatInput').disabled, false);
});

test("a denied command cannot open or offer replay of an attached narrative", async () => {
  const c = loadChat(async () => confrontationReply({allowed:false}));
  const scenes = pendingStoryScenes(c);
  c.el('chatInput').value = 'ทักท้วงกิเดียน';
  await c.sandbox.sendMessage(ev);
  assert.equal(scenes.played.length, 0);
  assert.equal(scenes.replayed.length, 0);
  assert.equal(c.read('busy'), false);
  assert.match(c.el('chatFeed').children.at(-1).className, /denied/);
});

for (const ending of ['cold_arrival', 'true_ending']) {
  test(`${ending} closes an active scene and cancels pending commands`, async () => {
    const requests = [];
    const c = loadChat(async (url, options) => {
      requests.push(url);
      if (url === '/clock') return reply({allowed:false, ending});
      return confrontationReply({pending:['move first_class_car']});
    });
    const scenes = pendingStoryScenes(c);
    c.el('chatInput').value = 'ทักท้วงกิเดียนแล้วไปตู้ 4';
    const action = c.sandbox.sendMessage(ev);
    await flush();
    assert.equal(scenes.played.length, 1);
    assert.equal(c.read('busy'), true);

    c.read('timeLimitSeconds = 1; clockElapsed = 2; clockAnchor = Date.now()');
    await c.sandbox.tickClock();
    await action;
    assert.equal(scenes.stops(), 1);
    assert.deepEqual(requests, ['/command', '/clock']);
    assert.equal(c.read('gameState.ending_id'), ending);
    assert.equal(c.read('gameOver'), true);
    assert.equal(c.read('busy'), false);
    assert.equal(c.el('chatInput').disabled, true);
    assert.equal(c.el('sendBtnText').textContent, 'จบเกม');
  });
}
