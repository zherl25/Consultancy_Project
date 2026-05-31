/**
 * Application entry point.
 *
 * Wires up all dependencies and hands control to the router.
 * This file is intentionally thin — it contains no business logic.
 */

import { ApiClient }   from './api.js';
import { Toast }       from './toast.js';
import { Router }      from './router.js';
import { SessionStore } from './sessions.js';
import { LandingPage } from './pages/landing.js';
import { DocsPage }    from './pages/docs.js';
import { ChatPage }    from './pages/chat.js';

// ── Dependency construction ───────────────────────────────
const api      = new ApiClient();
const toast    = new Toast(document.getElementById('toasts'));
const sessions = new SessionStore();

const landing  = new LandingPage();
const docs     = new DocsPage({ api, toast });
const chat     = new ChatPage({ api, toast, sessions });

// ── Cross-page navigation wiring ──────────────────────────
// When the user clicks "Chat about this doc", DocsPage calls this callback.
// We create a targeted session, tell ChatPage which session to open, then navigate.
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
  .add('#',     landing)
  .add('#docs', docs)
  .add('#chat', chat)
  .start();
