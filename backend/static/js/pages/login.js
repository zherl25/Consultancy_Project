/**
 * Login page controller.
 * Signs in consultants (admin) and client companies, and lets new companies
 * create an account. Stores the JWT and the account role on success.
 */
export const TOKEN_KEY = 'consultant_ai_token';
export const ROLE_KEY  = 'consultant_ai_role';

export class LoginPage {
  pageId = 'page-login';

  /** @param {{ api: import('../api.js').ApiClient }} deps */
  constructor({ api }) {
    this.#api = api;
  }

  enter() {
    if (localStorage.getItem(TOKEN_KEY)) {
      // Token present — validate it; redirect to app if still good, show form if stale.
      this.#api.me()
        .then((me) => {
          localStorage.setItem(ROLE_KEY, me.role);
          this.#onSuccess(me.role);
        })
        .catch(() => {
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem(ROLE_KEY);
          this.#setupForm();
        });
      return;
    }
    this.#setupForm();
  }

  leave() {
    this.#form?.removeEventListener('submit', this.#onSubmit);
    this.#switchBtn?.removeEventListener('click', this.#toggleMode);
    if (this.#errEl) this.#errEl.textContent = '';
  }

  /** Called by main.js after the router is available. @param {(role: string) => void} fn */
  set onSuccess(fn) { this.#onSuccess = fn; }

  // ── Private ────────────────────────────────────────────────

  #api;
  #form      = null;
  #errEl     = null;
  #btn       = null;
  #switchBtn = null;
  #signup    = false;
  #onSuccess = () => {};

  #setupForm() {
    this.#form      = document.getElementById('login-form');
    this.#errEl     = document.getElementById('login-error');
    this.#btn       = document.getElementById('login-btn');
    this.#switchBtn = document.getElementById('login-switch-btn');
    this.#form.addEventListener('submit', this.#onSubmit);
    this.#switchBtn.addEventListener('click', this.#toggleMode);
    this.#signup = window.location.hash === '#signup';
    this.#applyMode();
    document.getElementById('login-username')?.focus();
  }

  #toggleMode = () => {
    this.#signup = !this.#signup;
    this.#errEl.textContent = '';
    this.#applyMode();
    document.getElementById(this.#signup ? 'signup-company' : 'login-username')?.focus();
  };

  #applyMode() {
    const s = this.#signup;
    document.getElementById('login-heading').textContent        = s ? 'Create your account' : 'Welcome back';
    document.getElementById('login-sub').textContent            = s ? 'Get ISO 9001 documentation for your company'
                                                                    : 'Sign in to your workspace';
    document.getElementById('signup-company-field').classList.toggle('hidden', !s);
    document.getElementById('login-username-label').textContent = s ? 'Email' : 'Email or username';
    document.getElementById('login-password').autocomplete      = s ? 'new-password' : 'current-password';
    document.getElementById('login-password').placeholder       = s ? 'At least 8 characters' : 'Enter password';
    document.getElementById('login-switch-text').textContent    = s ? 'Already have an account?' : 'New company?';
    this.#switchBtn.textContent = s ? 'Sign in' : 'Create an account';
    this.#btn.textContent       = s ? 'Create account' : 'Sign in';
  }

  #onSubmit = async (e) => {
    e.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const company  = document.getElementById('signup-company').value.trim();
    if (!username || !password) return;
    if (this.#signup && !company) {
      this.#errEl.textContent = 'Please enter your company name.';
      return;
    }

    const label = this.#btn.textContent;
    this.#btn.disabled    = true;
    this.#btn.textContent = this.#signup ? 'Creating account…' : 'Signing in…';
    this.#errEl.textContent = '';

    try {
      const { access_token, role } = this.#signup
        ? await this.#api.signup(username, password, company)
        : await this.#api.login(username, password);
      localStorage.setItem(TOKEN_KEY, access_token);
      localStorage.setItem(ROLE_KEY, role ?? 'admin');
      this.#onSuccess(role ?? 'admin');
    } catch (err) {
      this.#errEl.textContent = this.#friendlyError(err);
    } finally {
      this.#btn.disabled    = false;
      this.#btn.textContent = label;
    }
  };

  /** Pydantic validation errors arrive as a list; turn them into one readable line. */
  #friendlyError(err) {
    if (err.status === 422) {
      return this.#signup
        ? 'Please use a valid email and a password of at least 8 characters.'
        : 'Please fill in both fields.';
    }
    return typeof err.message === 'string' && err.message !== '[object Object]'
      ? err.message
      : 'Something went wrong. Please try again.';
  }
}
