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

const login   = new LoginPage({ api });
const landing = new LandingPage();
const docs    = new DocsPage({ api, toast });
const chat    = new ChatPage({ api, toast, sessions });

// ── 401 handler — redirect to login on expired token ──────
api.onUnauthorized = () => { window.location.hash = '#login'; };

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

// Wire login success now that router exists
login.onSuccess = () => router.navigate('#');
