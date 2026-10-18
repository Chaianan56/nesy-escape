// Reuse the existing game controls and journal; only change their presentation.
window.addEventListener('DOMContentLoaded', () => {
  const header = document.querySelector('.header-right');
  const clock = document.getElementById('clockWidget');

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

    if (clock) {
      header.append(clock, journalButton, historyButton);
    } else {
      header.append(journalButton, historyButton);
    }

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

  // Keep the latest response panel layered over the scene artwork, as in the main UI.
  const art = document.querySelector('.scene-art');
  const dialoguePanel = document.querySelector('.dialogue-panel');
  if (art && dialoguePanel) art.append(dialoguePanel);

  // Toggle hiding dialogue overlay so the user can view the scene artwork unobstructed
  function hideDialogueBox() {
    if (typeof window.hideDialogue === 'function') {
      window.hideDialogue();
    } else {
      const panel = document.querySelector('.dialogue-panel');
      const showBtn = document.getElementById('showDialogueBtn');
      if (panel) {
        panel.classList.add('is-hidden');
        panel.style.setProperty('display', 'none', 'important');
      }
      if (showBtn) {
        showBtn.removeAttribute('hidden');
        showBtn.style.setProperty('display', 'inline-flex', 'important');
      }
    }
  }

  function showDialogueBox() {
    if (typeof window.showDialogue === 'function') {
      window.showDialogue();
    } else {
      const panel = document.querySelector('.dialogue-panel');
      const showBtn = document.getElementById('showDialogueBtn');
      if (panel) {
        panel.classList.remove('is-hidden');
        panel.style.removeProperty('display');
      }
      if (showBtn) {
        showBtn.setAttribute('hidden', '');
        showBtn.style.setProperty('display', 'none', 'important');
      }
    }
  }

  document.addEventListener('click', (e) => {
    if (e.target.closest('#hideDialogueBtn, #toggleDialogueBtn, .dialogue-hide-btn')) {
      e.preventDefault();
      hideDialogueBox();
    } else if (e.target.closest('#showDialogueBtn, .show-dialogue-floating-btn')) {
      e.preventDefault();
      showDialogueBox();
    }
  });

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

  // Smooth Mouse Wheel & Click-and-Drag Horizontal Scrolling for Chips
  function setupHorizontalScroll(el) {
    if (!el || el.__hasHorizontalScroll) return;
    el.__hasHorizontalScroll = true;

    // 1. Mouse wheel horizontal scrolling
    el.addEventListener('wheel', (e) => {
      if (e.deltaY !== 0) {
        e.preventDefault();
        el.scrollLeft += e.deltaY;
      }
    }, { passive: false });

    // 2. Click and drag to scroll
    let isDown = false;
    let startX = 0;
    let initialScrollLeft = 0;
    let hasMoved = false;

    el.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return; // Only primary mouse button
      isDown = true;
      hasMoved = false;
      el.classList.add('is-dragging');
      startX = e.pageX - el.offsetLeft;
      initialScrollLeft = el.scrollLeft;
    });

    window.addEventListener('mouseup', () => {
      if (isDown) {
        isDown = false;
        el.classList.remove('is-dragging');
      }
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDown) return;
      const x = e.pageX - el.offsetLeft;
      const walk = (x - startX) * 1.5;
      if (Math.abs(walk) > 4) {
        hasMoved = true;
      }
      el.scrollLeft = initialScrollLeft - walk;
    });

    // Suppress child button clicks if user dragged rather than clicked
    el.addEventListener('click', (e) => {
      if (hasMoved) {
        e.preventDefault();
        e.stopPropagation();
        hasMoved = false;
      }
    }, true);
  }

  // Attach to #visibleObjects and existing .chips-scroll
  const visibleObjects = document.getElementById('visibleObjects');
  if (visibleObjects) setupHorizontalScroll(visibleObjects);
  document.querySelectorAll('.chips-scroll').forEach(setupHorizontalScroll);

  // Expose globally so dynamic chip rows can use it
  window.setupHorizontalScroll = setupHorizontalScroll;
});
