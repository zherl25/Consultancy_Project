/**
 * Application entry point.
 * Wires up all dependencies and hands control to the router.
 * This file is intentionally thin — it contains no business logic.
 */

import { ApiClient }   from './api.js';
import { Toast }       from './toast.js';
import { Router }      from './router.js';
import { SessionStore } from './sessions.js';
import { LoginPage }   from './pages/login.js';
import { LandingPage } from './pages/landing.js';
import { DocsPage }    from './pages/docs.js';
import { ChatPage }    from './pages/chat.js';

// ── Dependency construction ───────────────────────────────
const api      = new ApiClient();
const toast    = new Toast(document.getElementById('toasts'));
const sessions = new SessionStore();

// Silently clear any stale/expired token before the user interacts.
// Runs in the background — landing page shows immediately without waiting.
if (localStorage.getItem('consultant_ai_token')) {
  api.me().catch(() => localStorage.removeItem('consultant_ai_token'));
}

const login   = new LoginPage({ api });
const landing = new LandingPage();
const docs    = new DocsPage({ api, toast });
const chat    = new ChatPage({ api, toast, sessions });

// ── 401 handler — redirect to login on expired token ──────
api.onUnauthorized = () => {
  toast.show('Your session has expired — please sign in again.', 'error');
  window.location.hash = '#login';
};

// ── Logout wiring ─────────────────────────────────────────
function logout() {
  localStorage.removeItem('consultant_ai_token');
  window.location.hash = '#login';
}
document.querySelectorAll('[data-logout]').forEach((btn) => {
  btn.addEventListener('click', logout);
});

// ── Cross-page navigation wiring ──────────────────────────
docs.onChatAbout = (filename) => {
  const session = sessions.create({
    name:           `📎 ${filename.slice(0, 30)}`,
    documentFilter: filename,
  });
  chat.setPendingSession(session.id);
  router.navigate('#chat');
};

// ── Router ────────────────────────────────────────────────
const router = new Router()
  .add('#login', login)
  .add('#',      landing)
  .add('#docs',  docs, { requiresAuth: true })
  .add('#chat',  chat, { requiresAuth: true })
  .start();

// After login, return to the page the user was trying to reach (default: docs)
login.onSuccess = () => {
  const dest = router.returnHash ?? '#docs';
  router.clearReturnHash();
  router.navigate(dest);
};
