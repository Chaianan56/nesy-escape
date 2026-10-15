// Modern Cinematic Presentation: Preserves the detective layout with permanent right archive panel
window.addEventListener('DOMContentLoaded', () => {
  // Document Dialog Close Handler
  const docDialog = document.getElementById('documentDialog');
  const closeDocBtn = document.getElementById('closeDocDialog');
  if (docDialog && closeDocBtn) {
    closeDocBtn.addEventListener('click', () => docDialog.close());
    docDialog.addEventListener('click', (e) => {
      if (e.target === docDialog) docDialog.close();
    });
  }

  // Dialogue overlay in scene-art
  const art = document.querySelector('.scene-art');
  const dialoguePanel = document.querySelector('.dialogue-panel');
  if (art && dialoguePanel && !art.contains(dialoguePanel)) {
    art.append(dialoguePanel);
  }

  // Auto-scroll chat on new message and sync right panel chat tab
  const feed = document.getElementById('chatFeed');
  if (feed) {
    new MutationObserver(() => {
      const historyDialog = document.getElementById('historyDialog');
      if (!historyDialog || !historyDialog.open) {
        feed.scrollTop = feed.scrollHeight;
      }
      if (typeof PixelUI !== 'undefined' && PixelUI.updateChatTab) {
        PixelUI.updateChatTab();
      }
    }).observe(feed, { childList: true, subtree: true });
  }
});
