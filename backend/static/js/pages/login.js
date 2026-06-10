/**
 * Login page controller.
 * Handles credential submission and stores the JWT on success.
 */
export class LoginPage {
  pageId = 'page-login';

  /** @param {{ api: import('../api.js').ApiClient }} deps */
  constructor({ api }) {
    this.#api = api;
  }

  enter() {
    this.#form  = document.getElementById('login-form');
    this.#errEl = document.getElementById('login-error');
    this.#btn   = document.getElementById('login-btn');
    this.#form.addEventListener('submit', this.#onSubmit);
    document.getElementById('login-username')?.focus();
  }

  leave() {
    this.#form?.removeEventListener('submit', this.#onSubmit);
    if (this.#errEl) this.#errEl.textContent = '';
  }

  /** Called by main.js after the router is available. @param {() => void} fn */
  set onSuccess(fn) { this.#onSuccess = fn; }

  // ── Private ────────────────────────────────────────────────

  #api;
  #form    = null;
  #errEl   = null;
  #btn     = null;
  #onSuccess = () => {};

  #onSubmit = async (e) => {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    if (!username || !password) return;

    this.#btn.disabled    = true;
    this.#btn.textContent = 'Signing in…';
    this.#errEl.textContent = '';

    try {
      const { access_token } = await this.#api.login(username, password);
      localStorage.setItem('consultant_ai_token', access_token);
      this.#onSuccess();
    } catch (err) {
      this.#errEl.textContent = err.message ?? 'Invalid credentials.';
    } finally {
      this.#btn.disabled    = false;
      this.#btn.textContent = 'Sign in';
    }
  };
}
