// Reuse the existing game controls and journal; only change their presentation.
window.addEventListener('DOMContentLoaded', () => {
  const clock = document.getElementById('clockWidget');
  const dockNote = document.querySelector('.dock-note');
  if (clock && dockNote && !dockNote.querySelector('small')) {
    const caption = document.createElement('small');
    caption.textContent = 'เวลาเหลือ · นาที';
    clock.before(caption);
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
