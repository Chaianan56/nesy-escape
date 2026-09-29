// Reuse the existing game controls and journal; only change their presentation.
window.addEventListener('DOMContentLoaded', () => {
  const header = document.querySelector('.header-right');
  const clock = document.getElementById('clockWidget');
  document.querySelector('.dock-note').replaceChildren(clock);
  const caption = document.createElement('small');
  caption.textContent = 'เวลาเหลือ · นาที';
  clock.before(caption);
  header.replaceChildren();
  const journalButton = document.createElement('button');
  journalButton.type = 'button';
  journalButton.className = 'utility-button';
  journalButton.textContent = '◇ สมุดคดี';
  journalButton.setAttribute('aria-haspopup', 'dialog');
  const historyButton = document.querySelector('.dialogue-panel [data-open-history]');
  historyButton.textContent = '↶ ประวัติ';
  header.append(journalButton, historyButton);

  const journal = document.createElement('dialog');
  journal.id = 'casebookDialog';
  journal.className = 'casebook-dialog';
  journal.setAttribute('aria-labelledby', 'casebookTitle');
  journal.innerHTML = '<header class="history-header"><div><div class="eyebrow">DETECTIVE’S JOURNAL</div><h2 id="casebookTitle">สมุดคดี</h2><p>หลักฐาน บุคคล และบันทึกที่คุณค้นพบ · เวลาในเกมยังเดินต่อ</p></div><button type="button" class="history-close" autofocus>✕ ปิด</button></header><div class="casebook-body"></div>';
  journal.querySelector('.casebook-body').append(document.querySelector('.journal-panel'), document.querySelector('.case-panel'));
  document.body.append(journal);
  journalButton.addEventListener('click', () => journal.showModal());
  journal.querySelector('button').addEventListener('click', () => journal.close());
  journal.addEventListener('close', () => journalButton.focus());

  const route = document.querySelector('.train-map');
  document.querySelector('.dock-label').replaceWith(route);
  document.querySelector('.route-label').textContent = 'ตำแหน่งบนขบวน · พิมพ์เพื่อเดินทาง';
  document.querySelector('.scene-art').append(document.querySelector('.dialogue-panel'));
  document.querySelector('.quick-actions').replaceChildren();
  const prompt = document.createElement('label');
  prompt.htmlFor = 'chatInput';
  prompt.textContent = 'คุณจะทำอะไรต่อ?';
  document.querySelector('.quick-actions').append(prompt);
  document.getElementById('chatInput').placeholder = 'พิมพ์ เช่น ไปตู้ 4 หรือ สอบปากคำกิเดียน';
  const feed = document.getElementById('chatFeed');
  new MutationObserver(() => {
    if (!document.getElementById('historyDialog').open) feed.scrollTop = 0;
  }).observe(feed, {childList:true});
});
