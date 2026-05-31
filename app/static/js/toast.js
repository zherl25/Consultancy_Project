/**
 * Toast notification system.
 * Appends transient alert elements to a container and auto-dismisses them.
 */

const ICONS   = { success: '✓', error: '✕', info: 'ℹ' };
const CLASSES = { success: 'ok', error: 'err', info: 'inf' };

export class Toast {
  /** @param {HTMLElement} container */
  constructor(container) {
    this._el = container;
  }

  /**
   * @param {string}                        message
   * @param {'success'|'error'|'info'}      [type='info']
   * @param {number}                        [duration=3800]  ms before auto-dismiss
   */
  show(message, type = 'info', duration = 3800) {
    const el = document.createElement('div');
    el.className = `toast ${CLASSES[type] ?? 'inf'}`;
    el.innerHTML = `<div class="t-icon">${ICONS[type] ?? 'ℹ'}</div><span>${String(message)}</span>`;
    this._el.appendChild(el);

    const dismiss = () => {
      el.classList.add('dying');
      el.addEventListener('animationend', () => el.remove(), { once: true });
    };

    const timer = setTimeout(dismiss, duration);
    el.addEventListener('click', () => { clearTimeout(timer); dismiss(); }, { once: true });
  }
}
