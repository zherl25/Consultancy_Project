/**
 * Custom confirmation dialog — replaces the browser's native confirm().
 * Returns a Promise<boolean> so it can be awaited just like confirm().
 *
 * Usage:
 *   const ok = await showConfirm({ title: 'Delete session?', message: '...', confirmLabel: 'Delete' });
 *   if (!ok) return;
 */

/**
 * @param {{
 *   title:         string,
 *   message:       string,
 *   confirmLabel?: string,
 *   danger?:       boolean,
 * }} opts
 * @returns {Promise<boolean>}
 */
export function showConfirm({ title, message, confirmLabel = 'Confirm', danger = true }) {
  return new Promise((resolve) => {
    const overlay  = document.getElementById('confirm-overlay');
    const titleEl  = document.getElementById('confirm-title');
    const msgEl    = document.getElementById('confirm-msg');
    const okBtn    = document.getElementById('confirm-ok');
    const cancelBtn = document.getElementById('confirm-cancel');

    titleEl.textContent = title;
    msgEl.textContent   = message;
    okBtn.textContent   = confirmLabel;
    okBtn.classList.toggle('danger', danger);

    overlay.classList.remove('hidden');
    // Slight delay so the animation plays before focus moves
    requestAnimationFrame(() => okBtn.focus());

    const cleanup = () => {
      overlay.classList.add('hidden');
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      overlay.removeEventListener('click', onBackdrop);
      document.removeEventListener('keydown', onKeydown);
    };

    const onOk      = ()  => { cleanup(); resolve(true);  };
    const onCancel  = ()  => { cleanup(); resolve(false); };
    const onBackdrop = (e) => { if (e.target === overlay) { cleanup(); resolve(false); } };
    const onKeydown = (e) => { if (e.key === 'Escape') { cleanup(); resolve(false); } };

    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    overlay.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKeydown);
  });
}
