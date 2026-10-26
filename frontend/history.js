/**
 * frontend/history.js — ระบบบันทึกประวัติการสืบสวนย้อนหลัง (Investigation History)
 * 
 * หน้าที่:
 * 1. ย้าย DOM ของข้อความสนทนา (chatFeed) เข้าสู่หน้าต่างประวัติแบบเต็ม (History Dialog)
 * 2. ซ่อนข้อความเก่าในหน้าจอหลักเพื่อความสะอาดตา โดยคงข้อความล่าสุดไว้บนหน้าจอ
 * 3. จัดการตำแหน่ง Scroll และคืนตำแหน่งเมื่อปิดหน้าต่างประวัติ
 */
window.addEventListener('DOMContentLoaded', () => {
  const dialog = document.getElementById('historyDialog');
  const feed = document.getElementById('chatFeed');
  const home = document.getElementById('latestChatHost');
  let opener;
  let savedScroll = 0;

  function updatePreview() {
    const messages = [...feed.children];
    if (typeof SequencePlayback !== 'undefined' && typeof SequencePlayback.isPlaying === 'function' && SequencePlayback.isPlaying()) {
      const activeCard = messages.findLast(node => node.classList.contains('seq-step-card'));
      messages.forEach(node => {
        if (node.classList.contains('seq-step-card')) {
          node.classList.toggle('history-older', node !== activeCard);
        } else {
          node.classList.add('history-older');
        }
      });
      return;
    }
    const latest = messages.findLast(node => node.classList.contains('msg-system') || node.classList.contains('msg-error') || node.classList.contains('seq-step-card'));
    // Keep follow-up choices and loading indicators alongside the latest answer.
    const lastAnswer = messages.findLast(node => node.querySelector('.card-header-bar') || node.classList.contains('seq-step-card')) || latest;
    const start = Math.max(0, messages.indexOf(lastAnswer));
    messages.forEach((node, index) => node.classList.toggle('history-older', index < start));
  }

  new MutationObserver(updatePreview).observe(feed, {childList: true});
  updatePreview();

  // The header buttons can be rebuilt after this script initializes.
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-open-history]');
    if (!button || dialog.open) return;
    opener = button;
    savedScroll = feed.scrollTop;
    document.getElementById('historyChatHost').appendChild(feed);
    dialog.showModal();
    document.body.classList.add('history-is-open');
    feed.scrollTop = feed.scrollHeight;
  });
  document.getElementById('closeHistory').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    home.appendChild(feed);
    feed.scrollTop = savedScroll;
    document.body.classList.remove('history-is-open');
    opener?.focus();
  });
  document.getElementById('historyLatest').addEventListener('click', () => {
    feed.scrollTo({top: feed.scrollHeight, behavior: 'smooth'});
  });
});
