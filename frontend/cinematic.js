// Reuse the existing game controls and journal; only change their presentation.
window.addEventListener('DOMContentLoaded', () => {
  const header = document.querySelector('.header-right');
  const clock = document.getElementById('clockWidget');
  const dockNote = document.querySelector('.dock-note');
  if (clock && dockNote) {
    if (!dockNote.contains(clock)) {
      dockNote.replaceChildren(clock);
    }
    if (!dockNote.querySelector('small')) {
      const caption = document.createElement('small');
      caption.textContent = 'เวลาเหลือ · นาที';
      clock.before(caption);
    }
  }

  if (header) {
    header.replaceChildren();
    const journalButton = document.createElement('button');
    journalButton.type = 'button';
    journalButton.className = 'utility-button';
    journalButton.textContent = '◇ สมุดคดี';
    journalButton.setAttribute('aria-haspopup', 'dialog');

    const historyButton = document.createElement('button');
    historyButton.type = 'button';
    historyButton.className = 'utility-button history-open-btn';
    historyButton.textContent = '↶ ประวัติ';
    historyButton.setAttribute('aria-haspopup', 'dialog');
    historyButton.setAttribute('data-open-history', '');
    historyButton.addEventListener('click', () => {
      document.getElementById('historyDialog')?.showModal();
    });
    header.append(journalButton, historyButton);

    const journal = document.createElement('dialog');
    journal.id = 'casebookDialog';
    journal.className = 'casebook-dialog';
    journal.setAttribute('aria-labelledby', 'casebookTitle');
    journal.innerHTML = '<header class="history-header"><div><div class="eyebrow">DETECTIVE’S JOURNAL</div><h2 id="casebookTitle">กระดานคดี</h2><p>หลักฐานและข้อสรุปที่คุณค้นพบ · เวลาในเกมยังเดินต่อ</p></div><button type="button" class="history-close" autofocus>✕ ปิด</button></header><div class="casebook-body"></div>';
    const casePanel = document.querySelector('.case-panel');
    if (casePanel) {
      journal.querySelector('.casebook-body').append(casePanel);
    }
    document.body.append(journal);
    journalButton.addEventListener('click', () => journal.showModal());
    journal.querySelector('.history-close')?.addEventListener('click', () => journal.close());
    journal.addEventListener('click', (e) => {
      if (e.target === journal) journal.close();
    });
    journal.addEventListener('close', () => journalButton.focus());
  }

  // Connect History Dialog button
  document.querySelectorAll('[data-open-history]').forEach(btn => {
    btn.onclick = () => document.getElementById('historyDialog')?.showModal();
  });

  // Keep the latest response panel layered over the scene artwork, as in the main UI.
  const art = document.querySelector('.scene-art');
  const dialoguePanel = document.querySelector('.dialogue-panel');
  if (art && dialoguePanel) art.append(dialoguePanel);

  const quickActions = document.querySelector('.quick-actions');
  if (quickActions) {
    quickActions.replaceChildren();
    const prompt = document.createElement('label');
    prompt.htmlFor = 'chatInput';
    prompt.textContent = 'คุณจะทำอะไรต่อ?';
    quickActions.append(prompt);
  }

  const chatInput = document.getElementById('chatInput');
  if (chatInput) {
    chatInput.placeholder = 'พิมพ์ เช่น ไปตู้ 4 หรือ สอบปากคำกิเดียน';
  }

  // Document Dialog Close Handler
  const docDialog = document.getElementById('documentDialog');
  const closeDocBtn = document.getElementById('closeDocDialog');
  if (docDialog && closeDocBtn) {
    closeDocBtn.addEventListener('click', () => docDialog.close());
    docDialog.addEventListener('click', (e) => {
      if (e.target === docDialog) docDialog.close();
    });
  }

  // Monogram Click -> Restart Game with Confirmation
  const monogram = document.querySelector('.monogram');
  const restartDialog = document.getElementById('restartConfirmDialog');
  const cancelRestartBtn = document.getElementById('cancelRestartBtn');
  const confirmRestartBtn = document.getElementById('confirmRestartBtn');

  if (monogram) {
    monogram.addEventListener('click', (e) => {
      e.preventDefault();
      const intro = document.getElementById('introScreen');
      if (intro && !intro.hidden) return; // Already on intro screen

      if (restartDialog && typeof restartDialog.showModal === 'function') {
        restartDialog.showModal();
      } else {
        if (window.confirm('คุณต้องการกลับไปหน้าแรกและเริ่มสืบสวนใหม่ใช่หรือไม่? (ความคืบหน้าทั้งหมดจะถูกรีเซ็ต)')) {
          if (typeof restartGame === 'function') restartGame();
        }
      }
    });
  }

  if (restartDialog) {
    if (cancelRestartBtn) {
      cancelRestartBtn.addEventListener('click', () => restartDialog.close());
    }
    if (confirmRestartBtn) {
      confirmRestartBtn.addEventListener('click', async () => {
        confirmRestartBtn.disabled = true;
        confirmRestartBtn.textContent = 'กำลังเริ่มใหม่...';
        try {
          if (typeof restartGame === 'function') {
            await restartGame();
          } else {
            window.location.reload();
          }
        } catch {
          confirmRestartBtn.disabled = false;
          confirmRestartBtn.textContent = 'ยืนยันเริ่มใหม่';
        }
      });
    }
    restartDialog.addEventListener('click', (e) => {
      if (e.target === restartDialog) restartDialog.close();
    });
    restartDialog.addEventListener('close', () => {
      if (confirmRestartBtn) {
        confirmRestartBtn.disabled = false;
        confirmRestartBtn.textContent = 'ยืนยันเริ่มใหม่';
      }
    });
  }

  const feed = document.getElementById('chatFeed');
  if (feed) {
    new MutationObserver(() => {
      if (!document.getElementById('historyDialog').open) feed.scrollTop = 0;
      if (typeof PixelUI !== 'undefined' && PixelUI.updateChatTab) {
        PixelUI.updateChatTab();
      }
    }).observe(feed, { childList: true, subtree: true });
  }
});
