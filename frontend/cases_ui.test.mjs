import test from 'node:test';
import assert from 'node:assert/strict';

test('updateCaseEdition formats route indicators correctly for dev awareness', () => {
  const el = { textContent: '', title: '' };
  const mono = { title: '' };
  globalThis.document = {
    getElementById(id) {
      if (id === 'caseEdition') return el;
      if (id === 'monogramRestart') return mono;
      return null;
    },
    querySelector(sel) {
      if (sel === '.edition') return el;
      if (sel === '.monogram') return mono;
      return null;
    }
  };

  const mapping = {
    'case_01_gideon': { letter: 'A', label: 'Route A: The Burnt Dossier' },
    'case_02_vincent': { letter: 'B', label: 'Route B: The Strike in the Dark' },
    'case_03_liora': { letter: 'C', label: "Route C: The Doctor's Retribution" }
  };

  function updateCaseEdition(caseId) {
    const target = globalThis.document.getElementById('caseEdition') || globalThis.document.querySelector('.edition');
    const info = mapping[caseId] || { letter: 'A', label: 'Route A' };
    if (target) {
      target.textContent = `แฟ้มคดี  /  01 [${info.letter}]`;
      target.title = `Active Route: ${info.label} (${caseId || 'default'})`;
    }
    const monogram = globalThis.document.getElementById('monogramRestart') || globalThis.document.querySelector('.monogram');
    if (monogram) {
      monogram.title = `เริ่มคดีใหม่ (กลับหน้าแรก) • แฟ้มคดี  /  01 [${info.letter}] (${info.label})`;
    }
  }

  // Case 01 -> Route A
  updateCaseEdition('case_01_gideon');
  assert.equal(el.textContent, 'แฟ้มคดี  /  01 [A]');
  assert.ok(el.title.includes('Route A'));
  assert.ok(mono.title.includes('01 [A]'));

  // Case 02 -> Route B (คงเลข 01 เปลี่ยนเฉพาะอักษร [B])
  updateCaseEdition('case_02_vincent');
  assert.equal(el.textContent, 'แฟ้มคดี  /  01 [B]');
  assert.ok(el.title.includes('Route B'));
  assert.ok(mono.title.includes('01 [B]'));

  // Case 03 -> Route C (คงเลข 01 เปลี่ยนเฉพาะอักษร [C])
  updateCaseEdition('case_03_liora');
  assert.equal(el.textContent, 'แฟ้มคดี  /  01 [C]');
  assert.ok(el.title.includes('Route C'));
  assert.ok(mono.title.includes('01 [C]'));

  // Fallback
  updateCaseEdition('unknown_case');
  assert.equal(el.textContent, 'แฟ้มคดี  /  01 [A]');
});

test('parallel case timeline logic differentiates routes', () => {
  function evaluateTimeBanner(caseId, evidenceIds) {
    const evidenceSet = new Set(evidenceIds);
    let isConfirmed = false;
    let title = '';

    if (caseId === 'case_02_vincent') {
      isConfirmed = evidenceSet.has('wall_clock') && (evidenceSet.has('liora_time_estimate') || evidenceSet.has('vincent_blood'));
      if (isConfirmed) title = 'ช่วงเวลาเกิดเหตุรุนแรง: 21:15 – 21:18 (ช่วงไฟดับ)';
      else if (evidenceSet.has('wall_clock')) title = 'ช่วงเวลาเกิดเหตุ: คาดว่าเป็นช่วงไฟดับ (รอผลชันสูตร)';
    } else if (caseId === 'case_03_liora') {
      isConfirmed = evidenceSet.has('pocket_watch') && (evidenceSet.has('liora_time_estimate') || evidenceSet.has('second_teacup'));
      if (isConfirmed) title = 'ช่วงเวลาเกิดเหตุรุนแรง: 20:20 – 20:25 (วางยาพิษอำพราง)';
      else if (evidenceSet.has('pocket_watch')) title = 'ช่วงเวลาเกิดเหตุ: เข็มนาฬิกาหยุด 20:25 (รอตรวจสารพิษ)';
    } else {
      isConfirmed = evidenceSet.has('pocket_watch');
      if (isConfirmed) title = 'ช่วงเวลาเกิดเหตุรุนแรง: 20:20 – 20:26';
    }
    return { isConfirmed, title };
  }

  // In Route A, pocket_watch confirms 20:20 - 20:26
  const resA = evaluateTimeBanner('case_01_gideon', ['pocket_watch']);
  assert.equal(resA.isConfirmed, true);
  assert.equal(resA.title, 'ช่วงเวลาเกิดเหตุรุนแรง: 20:20 – 20:26');

  // In Route B, pocket_watch does NOT confirm murder window; wall_clock alone is pending autopsy; clock + blood confirms
  const resBWithoutClock = evaluateTimeBanner('case_02_vincent', ['pocket_watch']);
  assert.equal(resBWithoutClock.isConfirmed, false);
  const resBClockOnly = evaluateTimeBanner('case_02_vincent', ['wall_clock']);
  assert.equal(resBClockOnly.isConfirmed, false);
  assert.equal(resBClockOnly.title, 'ช่วงเวลาเกิดเหตุ: คาดว่าเป็นช่วงไฟดับ (รอผลชันสูตร)');
  const resBWithClockAndBlood = evaluateTimeBanner('case_02_vincent', ['wall_clock', 'vincent_blood']);
  assert.equal(resBWithClockAndBlood.isConfirmed, true);
  assert.equal(resBWithClockAndBlood.title, 'ช่วงเวลาเกิดเหตุรุนแรง: 21:15 – 21:18 (ช่วงไฟดับ)');

  // In Route C, watch alone waits for poison check; watch + second_teacup confirms poison window (20:20 - 20:25)
  const resCWatchOnly = evaluateTimeBanner('case_03_liora', ['pocket_watch']);
  assert.equal(resCWatchOnly.isConfirmed, false);
  assert.equal(resCWatchOnly.title, 'ช่วงเวลาเกิดเหตุ: เข็มนาฬิกาหยุด 20:25 (รอตรวจสารพิษ)');
  const resCConfirmed = evaluateTimeBanner('case_03_liora', ['pocket_watch', 'second_teacup']);
  assert.equal(resCConfirmed.isConfirmed, true);
  assert.equal(resCConfirmed.title, 'ช่วงเวลาเกิดเหตุรุนแรง: 20:20 – 20:25 (วางยาพิษอำพราง)');
});

test('timeline suspect cards start as pending and do not spoil conclusions on turn 1', () => {
  function evaluateSuspectStamps(caseId, evidenceIds = [], deductions = []) {
    const evidenceSet = new Set(evidenceIds);
    const deductionSet = new Set(deductions.map(d => typeof d === 'string' ? d : d.id));
    const hasWatch = evidenceSet.has('pocket_watch');
    const hasWallClock = evidenceSet.has('wall_clock');
    const hasSoot = evidenceSet.has('red_soot');
    const hasStaffImpact = evidenceSet.has('staff_impact_testimony');
    const hasTunnelSched = evidenceSet.has('tunnel_schedule');
    const hasGideonAlibi = evidenceSet.has('gideon_blackout_alibi');
    const hasVincentConfession = evidenceSet.has('vincent_blackout_confession');
    const hasVincentCutters = evidenceSet.has('wire_cutters') || evidenceSet.has('cut_copper_wire');
    const hasVincentTicket = evidenceSet.has('vincent_ticket');
    const hasVincentStation = evidenceSet.has('vincent_station_alibi');
    const hasVincentBlood = evidenceSet.has('vincent_blood');
    const hasLioraLog = evidenceSet.has('liora_patient_log');
    const hasPatientWitness = evidenceSet.has('liora_patient_witness');
    const hasTeaTrace = evidenceSet.has('tea_lozenge_trace');
    const hasLioraEstimate = evidenceSet.has('liora_time_estimate');

    const hasCase01MurderWindow = (hasWatch && (hasSoot || hasStaffImpact || hasTunnelSched)) || deductionSet.has('D01_TRUE_MURDER_WINDOW');
    const hasCase01VincentCleared = (hasVincentStation && hasVincentTicket) || deductionSet.has('D08_VINCENT_CLEARED');
    const hasCase01LioraCleared = (hasLioraLog && hasPatientWitness) || deductionSet.has('D09_LIORA_CLEARED');
    const hasCase01GideonContradicted = (hasWatch || deductionSet.has('D02_BLACKOUT_ALIBI_IRRELEVANT')) && hasGideonAlibi;

    const hasCase02MurderWindow = (hasWallClock && (hasLioraEstimate || hasVincentBlood)) || deductionSet.has('D01_BLACKOUT_MURDER_WINDOW');
    const hasCase02VincentContradicted = (hasVincentBlood && (evidenceSet.has('letter_opener') || hasVincentCutters)) || deductionSet.has('D04_VINCENT_BLOOD_SPATTER');
    const hasCase02GideonVerified = hasGideonAlibi && (hasCase02MurderWindow || deductionSet.has('D05_GIDEON_ALIBI_SOLID'));
    const hasCase02LioraCleared = hasPatientWitness || deductionSet.has('D06_LIORA_CLEARED');

    const hasCase03MurderWindow = (hasWatch && (hasLioraEstimate || evidenceSet.has('second_teacup'))) || deductionSet.has('D01_POISON_DEATH_WINDOW');
    const hasCase03PoisonTrace = (hasTeaTrace && hasLioraLog) || deductionSet.has('D03_LIORA_POISON_TRACE');
    const hasCase03LioraAlibiBroken = (hasPatientWitness && hasTunnelSched) || deductionSet.has('D04_LIORA_ALIBI_BROKEN');
    const hasCase03VincentCleared = (hasVincentTicket && (hasCase03MurderWindow || hasCase03PoisonTrace)) || deductionSet.has('D05_VINCENT_CLEARED');
    const hasCase03GideonCleared = (hasGideonAlibi && (hasCase03MurderWindow || hasCase03PoisonTrace)) || deductionSet.has('D06_GIDEON_CLEARED');
    const hasCase03LioraContradicted = hasCase03PoisonTrace || hasCase03LioraAlibiBroken;

    let gideon = 'รอตรวจสอบ';
    let vincent = 'รอตรวจสอบ';
    let liora = 'รอตรวจสอบ';

    if (caseId === 'case_02_vincent') {
      if (hasCase02GideonVerified) gideon = 'ยืนยันแล้ว';
      if (hasCase02VincentContradicted) {
        vincent = 'หักล้างแล้ว';
      } else if (hasVincentCutters || hasVincentConfession || hasVincentBlood) {
        vincent = 'ต้องสงสัย';
      }
      if (hasCase02LioraCleared) liora = 'ยืนยันแล้ว';
    } else if (caseId === 'case_03_liora') {
      if (hasCase03GideonCleared) gideon = 'ยืนยันแล้ว';
      else if (evidenceSet.has('burnt_folder_c') || evidenceSet.has('dossier_missing_file_c')) gideon = 'ต้องสงสัย';

      if (hasCase03VincentCleared) {
        vincent = 'พ้นข้อหาฆาตกรรม';
      } else if (hasVincentBlood || hasVincentCutters || hasVincentConfession) {
        vincent = 'ต้องสงสัย';
      }

      if (hasCase03LioraContradicted) {
        liora = 'หักล้างแล้ว';
      } else if (hasTeaTrace || hasLioraLog || hasPatientWitness) {
        liora = 'ต้องสงสัย';
      }
    } else {
      if (hasCase01GideonContradicted) gideon = 'หักล้างแล้ว';
      if (hasCase01VincentCleared) {
        vincent = 'ยืนยันแล้ว';
      } else if (hasVincentConfession || hasVincentCutters || hasVincentBlood) {
        vincent = 'ต้องสงสัย';
      }
      if (hasCase01LioraCleared) liora = 'ยืนยันแล้ว';
    }

    return { gideon, vincent, liora };
  }

  // Turn 1: No evidence discovered yet -> All 3 cases must have ALL suspects as pending
  const t1Case01 = evaluateSuspectStamps('case_01_gideon', []);
  assert.equal(t1Case01.gideon, 'รอตรวจสอบ');
  assert.equal(t1Case01.vincent, 'รอตรวจสอบ');
  assert.equal(t1Case01.liora, 'รอตรวจสอบ');

  const t1Case02 = evaluateSuspectStamps('case_02_vincent', []);
  assert.equal(t1Case02.gideon, 'รอตรวจสอบ');
  assert.equal(t1Case02.vincent, 'รอตรวจสอบ');
  assert.equal(t1Case02.liora, 'รอตรวจสอบ');

  const t1Case03 = evaluateSuspectStamps('case_03_liora', []);
  assert.equal(t1Case03.gideon, 'รอตรวจสอบ');
  assert.equal(t1Case03.vincent, 'รอตรวจสอบ');
  assert.equal(t1Case03.liora, 'รอตรวจสอบ');

  // Progressive Clue Discovery in Case 02:
  // Step A: wall_clock alone does NOT clear Liora or Gideon
  const t2Case02StepA = evaluateSuspectStamps('case_02_vincent', ['wall_clock']);
  assert.equal(t2Case02StepA.gideon, 'รอตรวจสอบ');
  assert.equal(t2Case02StepA.liora, 'รอตรวจสอบ');
  assert.equal(t2Case02StepA.vincent, 'รอตรวจสอบ');

  // Step B: vincent_blood alone only raises suspicion on Vincent
  const t2Case02StepB = evaluateSuspectStamps('case_02_vincent', ['wall_clock', 'vincent_blood']);
  assert.equal(t2Case02StepB.vincent, 'ต้องสงสัย');
  assert.equal(t2Case02StepB.liora, 'รอตรวจสอบ');

  // Step C: Full evidence verified
  const t2Case02Full = evaluateSuspectStamps('case_02_vincent', [
    'wall_clock', 'vincent_blood', 'letter_opener', 'gideon_blackout_alibi', 'liora_patient_witness'
  ]);
  assert.equal(t2Case02Full.gideon, 'ยืนยันแล้ว');
  assert.equal(t2Case02Full.liora, 'ยืนยันแล้ว');
  assert.equal(t2Case02Full.vincent, 'หักล้างแล้ว');

  // Progressive Clue Discovery in Case 03:
  // Step A: tea trace alone ONLY marks Liora as suspected, does NOT solve the case!
  const t2Case03StepA = evaluateSuspectStamps('case_03_liora', ['tea_lozenge_trace']);
  assert.equal(t2Case03StepA.liora, 'ต้องสงสัย');
  assert.equal(t2Case03StepA.gideon, 'รอตรวจสอบ');
  assert.equal(t2Case03StepA.vincent, 'รอตรวจสอบ');

  // Step B: Connecting tea trace to medical log contradicts Liora
  const t2Case03StepB = evaluateSuspectStamps('case_03_liora', ['tea_lozenge_trace', 'liora_patient_log']);
  assert.equal(t2Case03StepB.liora, 'หักล้างแล้ว');
  assert.equal(t2Case03StepB.vincent, 'รอตรวจสอบ');

  // Step C: Adding vincent_ticket and gideon_blackout_alibi verifies the others
  const t2Case03Full = evaluateSuspectStamps('case_03_liora', [
    'tea_lozenge_trace', 'liora_patient_log', 'vincent_ticket', 'gideon_blackout_alibi'
  ]);
  assert.equal(t2Case03Full.liora, 'หักล้างแล้ว');
  assert.equal(t2Case03Full.vincent, 'พ้นข้อหาฆาตกรรม');
  assert.equal(t2Case03Full.gideon, 'ยืนยันแล้ว');
});

test('people tab renders silhouette ??? for unencountered characters', () => {
  function formatPersonCard(person, visitedLocations = ['lounge_car']) {
    const isEncountered = Boolean(
      person.encountered !== undefined
        ? person.encountered
        : (person.here || visitedLocations.includes(person.location) || person.interrogated)
    );
    if (!isEncountered) {
      return {
        isUnknown: true,
        displayName: '??? (ยังไม่พบตัว)',
        badge: '❓ ยังไม่พบตัว',
      };
    }
    return {
      isUnknown: false,
      displayName: person.name,
      badge: person.here ? '📍 อยู่ในตู้นี้' : person.location,
    };
  }

  const gideonInLounge = { id: 'gideon_hart', name: 'กิเดียน ฮาร์ต', location: 'lounge_car', here: true, encountered: true };
  const lioraInDining = { id: 'dr_liora_venn', name: 'ดร. ลิโอรา เวนน์', location: 'car_3_dining', here: false, encountered: false };

  const cardGideon = formatPersonCard(gideonInLounge);
  assert.equal(cardGideon.isUnknown, false);
  assert.equal(cardGideon.displayName, 'กิเดียน ฮาร์ต');

  const cardLiora = formatPersonCard(lioraInDining);
  assert.equal(cardLiora.isUnknown, true);
  assert.equal(cardLiora.displayName, '??? (ยังไม่พบตัว)');
  assert.equal(cardLiora.badge, '❓ ยังไม่พบตัว');

  // When backend or client updates encountered to true
  const cardLioraVisited = formatPersonCard({ ...lioraInDining, encountered: true });
  assert.equal(cardLioraVisited.isUnknown, false);
  assert.equal(cardLioraVisited.displayName, 'ดร. ลิโอรา เวนน์');

  // When testing client-side fallback without backend encountered field
  const lioraFallback = { id: 'dr_liora_venn', name: 'ดร. ลิโอรา เวนน์', location: 'car_3_dining', here: false };
  assert.equal(formatPersonCard(lioraFallback, ['lounge_car']).isUnknown, true);
  assert.equal(formatPersonCard(lioraFallback, ['lounge_car', 'car_3_dining']).isUnknown, false);
});

test('quick action strip limits normal state to at most 2 basic sample buttons and shows profiler chip', () => {
  function renderQuickButtons(visibleObjects, peopleHere, assistanceChip = null) {
    const buttons = [];
    if (assistanceChip) {
      buttons.push({ type: 'profiler-chip', label: assistanceChip.label, command: assistanceChip.command });
    }
    let sampleCount = 0;
    if (visibleObjects && visibleObjects.length && sampleCount < 2) {
      buttons.push({ type: 'inspect', label: `ตรวจ${visibleObjects[0].name}` });
      sampleCount++;
    }
    if (peopleHere && peopleHere.length && sampleCount < 2) {
      const person = peopleHere[0];
      buttons.push({ type: 'talk', label: `สอบปากคำ ${person.name}` });
      sampleCount++;
    }
    return buttons;
  }

  // Room with 5 objects and 2 people
  const objs = [{ name: 'นาฬิกาพก' }, { name: 'โต๊ะเครื่องดื่ม' }, { name: 'กระดุม' }];
  const people = [{ name: 'กิเดียน ฮาร์ต' }, { name: 'พนักงาน' }];

  // Normal state: limited to at most 2 buttons (not 5!)
  const normalBtns = renderQuickButtons(objs, people, null);
  assert.equal(normalBtns.length, 2);
  assert.equal(normalBtns[0].type, 'inspect');
  assert.equal(normalBtns[1].type, 'talk');

  // Profiler Level 2 assistance state: adds profiler chip
  const profilerChip = { command: 'ตรวจนาฬิกาพก', label: '💡 Profiler แนะนำ: ตรวจนาฬิกาพก' };
  const assistedBtns = renderQuickButtons(objs, people, profilerChip);
  assert.equal(assistedBtns.length, 3);
  assert.equal(assistedBtns[0].type, 'profiler-chip');
  assert.equal(assistedBtns[0].label, '💡 Profiler แนะนำ: ตรวจนาฬิกาพก');
});
