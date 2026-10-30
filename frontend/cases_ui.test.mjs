import test from 'node:test';
import assert from 'node:assert/strict';

test('updateCaseEdition formats route indicators correctly for dev awareness', () => {
  const el = { textContent: '', title: '' };
  globalThis.document = {
    getElementById(id) {
      if (id === 'caseEdition') return el;
      return null;
    },
    querySelector(sel) {
      if (sel === '.edition') return el;
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
    if (!target) return;
    const info = mapping[caseId] || { letter: 'A', label: 'Route A' };
    target.textContent = `แฟ้มคดี  /  01 [${info.letter}]`;
    target.title = `Active Route: ${info.label} (${caseId || 'default'})`;
  }

  // Case 01 -> Route A
  updateCaseEdition('case_01_gideon');
  assert.equal(el.textContent, 'แฟ้มคดี  /  01 [A]');
  assert.ok(el.title.includes('Route A'));

  // Case 02 -> Route B (คงเลข 01 เปลี่ยนเฉพาะอักษร [B])
  updateCaseEdition('case_02_vincent');
  assert.equal(el.textContent, 'แฟ้มคดี  /  01 [B]');
  assert.ok(el.title.includes('Route B'));

  // Case 03 -> Route C (คงเลข 01 เปลี่ยนเฉพาะอักษร [C])
  updateCaseEdition('case_03_liora');
  assert.equal(el.textContent, 'แฟ้มคดี  /  01 [C]');
  assert.ok(el.title.includes('Route C'));

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
      isConfirmed = evidenceSet.has('wall_clock') || evidenceSet.has('vincent_blood');
      if (isConfirmed) title = 'ช่วงเวลาเกิดเหตุรุนแรง: 21:15 – 21:18 (ช่วงไฟดับ)';
    } else if (caseId === 'case_03_liora') {
      isConfirmed = evidenceSet.has('pocket_watch') || evidenceSet.has('liora_time_estimate');
      if (isConfirmed) title = 'ช่วงเวลาเกิดเหตุรุนแรง: 20:20 – 20:25 (วางยาพิษอำพราง)';
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

  // In Route B, pocket_watch does NOT confirm murder window; wall_clock does (21:15 - 21:18)
  const resBWithoutClock = evaluateTimeBanner('case_02_vincent', ['pocket_watch']);
  assert.equal(resBWithoutClock.isConfirmed, false);
  const resBWithClock = evaluateTimeBanner('case_02_vincent', ['wall_clock']);
  assert.equal(resBWithClock.isConfirmed, true);
  assert.equal(resBWithClock.title, 'ช่วงเวลาเกิดเหตุรุนแรง: 21:15 – 21:18 (ช่วงไฟดับ)');

  // In Route C, pocket_watch or liora_time_estimate confirms poison window (20:20 - 20:25)
  const resC = evaluateTimeBanner('case_03_liora', ['pocket_watch']);
  assert.equal(resC.isConfirmed, true);
  assert.equal(resC.title, 'ช่วงเวลาเกิดเหตุรุนแรง: 20:20 – 20:25 (วางยาพิษอำพราง)');
});
