/**
 * Application entry point.
 * Wires up all dependencies and hands control to the router.
 * This file is intentionally thin — it contains no business logic.
 */

import { ApiClient }    from './api.js';
import { Toast }        from './toast.js';
import { Router }       from './router.js';
import { SessionStore } from './sessions.js';
import { LoginPage, TOKEN_KEY, ROLE_KEY } from './pages/login.js';
import { LandingPage }  from './pages/landing.js';
import { ProjectsPage } from './pages/projects.js';
import { ChatPage }     from './pages/chat.js';
import { SetupPage }    from './pages/setup.js';

// ── Dependency construction ───────────────────────────────
const api      = new ApiClient();
const toast    = new Toast(document.getElementById('toasts'));
const sessions = new SessionStore();

// Silently clear any stale/expired token before the user interacts.
// Runs in the background — landing page shows immediately without waiting.
if (localStorage.getItem(TOKEN_KEY)) {
  api.me()
    .then((me) => localStorage.setItem(ROLE_KEY, me.role))
    .catch(() => { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(ROLE_KEY); });
}

const login    = new LoginPage({ api });
const landing  = new LandingPage();
const projects = new ProjectsPage({ api, toast });
const chat     = new ChatPage({ api, toast, sessions });
const setup    = new SetupPage({ api, toast });

// ── 401 handler — redirect to login on expired token ──────
api.onUnauthorized = () => {
  toast.show('Your session has expired — please sign in again.', 'error');
  window.location.hash = '#login';
};

// ── Logout wiring ─────────────────────────────────────────
function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
  window.location.hash = '#';
}
document.querySelectorAll('[data-logout]').forEach((btn) => {
  btn.addEventListener('click', logout);
});

// ── Router ────────────────────────────────────────────────
const router = new Router()
  .add('#login',    login)
  .add('#signup',   login)
  .add('#',         landing)
  .add('#projects', projects, { requiresAuth: true, role: 'admin' })
  .add('#chat',     chat,     { requiresAuth: true, role: 'admin' })
  .add('#setup',    setup,    { requiresAuth: true, role: 'client' })
  .start();

// Redirect already-authenticated users away from landing straight to the app
landing.onEnter = () => {
  if (localStorage.getItem(TOKEN_KEY)) router.navigate(router.homeFor(localStorage.getItem(ROLE_KEY)));
};

// After login, return to the page the user was trying to reach (default: their home page)
login.onSuccess = (role) => {
  const dest = router.returnHash ?? router.homeFor(role);
  router.clearReturnHash();
  router.navigate(dest);
};
