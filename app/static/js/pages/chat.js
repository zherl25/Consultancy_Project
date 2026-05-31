/**
 * Chat page controller.
 *
 * Responsibilities:
 *   - Session sidebar (list, create, delete, activate)
 *   - Document filter dropdown
 *   - Message rendering with SSE streaming
 *   - AbortController-based stream cancellation on leave()
 *   - Full event-listener cleanup on leave() to prevent memory leaks
 */

import {
  sanitize, renderMarkdown, getExtension, formatDate, typeBadgeClass,
} from '../utils.js';

export class ChatPage {
  get pageId() { return 'page-chat'; }

  /**
   * @param {{
   *   api:      import('../api.js').ApiClient,
   *   toast:    import('../toast.js').Toast,
   *   sessions: import('../sessions.js').SessionStore,
   * }} deps
   */
  constructor({ api, toast, sessions }) {
    this.#api      = api;
    this.#toast    = toast;
    this.#sessions = sessions;
  }

  #api;
  #toast;
  #sessions;

  // ── State ─────────────────────────────────────────────────
  /** @type {string|null} */                        #sessionId     = null;
  /** @type {Array<{role:string,content:string}>} */ #conversation  = [];
  /** @type {string|null} */                        #docFilter     = null;
  /** @type {{ abort: () => void }|null} */         #stream        = null;
  /** @type {string|null} */                        #pendingId     = null;
  /** @type {Array<import('../api.js').Document>} */#docs          = [];
  /** @type {(() => void)|null} */                  #unsubSessions = null;
  /** @type {Record<string, EventListener>} */      #handlers      = {};

  // ── Public API ────────────────────────────────────────────

  /** Activate a specific session when the chat page next opens. */
  setPendingSession(id) { this.#pendingId = id; }

  // ── Lifecycle ─────────────────────────────────────────────

  async enter() {
    this.#attachListeners();
    this.#unsubSessions = this.#sessions.subscribe(() => this.#renderSessionList());

    // Guarantee at least one session exists
    if (!this.#sessions.getAll().length) this.#sessions.create();

    await this.#loadDocs();

    const targetId = this.#pendingId ?? this.#sessions.getLastId() ?? this.#sessions.getAll()[0]?.id;
    this.#pendingId = null;
    this.#activateSession(targetId);
  }

  leave() {
    this.#stream?.abort();
    this.#stream = null;
    this.#unsubSessions?.();
    this.#unsubSessions = null;
    this.#detachListeners();
    document.getElementById('flt-dd')?.classList.remove('open');
  }

  // ── Session management ────────────────────────────────────

  #activateSession(id) {
    const session = this.#sessions.findById(id);
    if (!session) return;

    this.#sessionId    = id;
    this.#conversation = [...(session.messages ?? [])];
    this.#docFilter    = session.documentFilter ?? null;
    this.#sessions.setLastId(id);

    document.getElementById('sess-title').textContent = session.name;
    this.#updateFilterUI();
    this.#renderSessionList();
    this.#renderMessages();
  }

  #renderSessionList() {
    const container = document.getElementById('sess-list');
    const sessions  = this.#sessions.getAll();

    if (!sessions.length) {
      container.innerHTML = '<div class="ss-empty">No sessions yet</div>';
      return;
    }

    container.innerHTML = '';
    sessions.forEach((s, i) => {
      const msgCount = Math.ceil((s.messages?.length ?? 0) / 2);
      const isActive = s.id === this.#sessionId;

      const item = document.createElement('div');
      item.className            = `si${isActive ? ' active' : ''}`;
      item.style.animationDelay = `${i * 0.03}s`;
      item.setAttribute('role', 'listitem');
      item.innerHTML = `
        <span class="si-ico" aria-hidden="true">💬</span>
        <div class="si-info">
          <div class="si-name" title="${sanitize(s.name)}">${sanitize(s.name)}</div>
          <div class="si-meta">${formatDate(s.updatedAt)}${msgCount ? ` · ${msgCount} msg${msgCount !== 1 ? 's' : ''}` : ''}</div>
        </div>
        <button class="si-del" aria-label="Delete session ${sanitize(s.name)}">×</button>`;

      item.addEventListener('click', (e) => {
        if (!e.target.classList.contains('si-del')) this.#activateSession(s.id);
      });
      item.querySelector('.si-del').addEventListener('click', (e) => {
        e.stopPropagation();
        this.#deleteSession(s.id);
      });

      container.appendChild(item);
    });
  }

  #deleteSession(id) {
    if (!confirm('Delete this session?')) return;
    this.#sessions.delete(id);

    if (id !== this.#sessionId) return;

    const remaining = this.#sessions.getAll();
    const nextId    = remaining[0]?.id ?? this.#sessions.create().id;
    this.#activateSession(nextId);
  }

  // ── Document filter dropdown ──────────────────────────────

  async #loadDocs() {
    try { this.#docs = await this.#api.getDocuments(); } catch { /* non-fatal */ }
    this.#renderFilterDropdown();
  }

  #renderFilterDropdown() {
    const dd = document.getElementById('flt-dd');
    dd.innerHTML = '';

    const makeOption = (label, iconHtml, filterValue) => {
      const opt = document.createElement('div');
      opt.className   = `fo${this.#docFilter === filterValue ? ' sel' : ''}`;
      opt.setAttribute('role', 'option');
      opt.setAttribute('aria-selected', String(this.#docFilter === filterValue));
      opt.innerHTML = `${iconHtml}<span class="fo-name" title="${sanitize(label)}">${sanitize(label)}</span>`;
      opt.addEventListener('click', () => { this.#setFilter(filterValue); dd.classList.remove('open'); });
      return opt;
    };

    dd.appendChild(makeOption('All Documents', '<span>🗂️</span>', null));
    this.#docs.forEach((doc) => {
      const ext    = getExtension(doc.filename).toUpperCase();
      const iconHtml = `<span class="tb ${typeBadgeClass(doc.filename)}">${ext}</span>`;
      dd.appendChild(makeOption(doc.filename, iconHtml, doc.filename));
    });
  }

  #setFilter(value) {
    this.#docFilter = value;
    if (this.#sessionId) this.#sessions.update(this.#sessionId, { documentFilter: value });
    this.#updateFilterUI();
    this.#renderFilterDropdown();
  }

  #updateFilterUI() {
    const btn = document.getElementById('flt-btn');
    const lbl = document.getElementById('flt-lbl');
    const f   = this.#docFilter;

    lbl.textContent = f ? (f.length > 26 ? `${f.slice(0, 26)}…` : f) : 'All Documents';
    btn.classList.toggle('on', Boolean(f));
    btn.setAttribute('aria-expanded', 'false');
  }

  // ── Message rendering ─────────────────────────────────────

  get #msgEl() { return document.getElementById('messages'); }

  #renderMessages() {
    const el = this.#msgEl;
    el.innerHTML = '';

    if (!this.#conversation.length) {
      el.innerHTML = '<div class="sys-msg">Ask a question to get started.</div>';
      return;
    }

    this.#conversation.forEach((msg) => {
      if (msg.role === 'user') this.#appendUser(msg.content, false);
      else this.#appendAssistant(msg.content, msg.sources ?? [], false);
    });
    this.#scrollBottom();
  }

  #appendUser(text, animate = true) {
    const row = document.createElement('div');
    row.className = `mr user${animate ? '' : ' noani'}`;
    row.innerHTML = `<div class="ms">You</div><div class="bbl">${sanitize(text)}</div>`;
    this.#msgEl.appendChild(row);
    this.#scrollBottom();
    return row;
  }

  #appendAssistant(text, sources = [], animate = true) {
    const row = document.createElement('div');
    row.className = `mr assistant${animate ? '' : ' noani'}`;
    row.innerHTML = `<div class="ms">Consultant AI</div><div class="bbl">${renderMarkdown(text)}</div>`;
    if (sources.length) this.#appendSources(row, sources);
    this.#msgEl.appendChild(row);
    this.#scrollBottom();
    return row;
  }

  #appendTyping() {
    const row = document.createElement('div');
    row.className = 'mr assistant';
    row.innerHTML  = `<div class="ms">Consultant AI</div><div class="bbl"><div class="typing"><span></span><span></span><span></span></div></div>`;
    this.#msgEl.appendChild(row);
    this.#scrollBottom();
    return row;
  }

  #appendSources(row, sources) {
    const toggle = document.createElement('button');
    toggle.type      = 'button';
    toggle.className = 'src-toggle';
    toggle.innerHTML = `<span class="arr" aria-hidden="true">›</span> ${sources.length} source${sources.length > 1 ? 's' : ''} referenced`;

    const panel = document.createElement('div');
    panel.className = 'src-panel';

    sources.forEach((s) => {
      const cls  = s.score >= 75 ? 'hi' : s.score >= 50 ? 'md' : 'lo';
      const card = document.createElement('div');
      card.className = 'sc';
      card.innerHTML = `
        <div class="sc-hdr">
          <span class="tb ${typeBadgeClass(s.source)}">${getExtension(s.source).toUpperCase()}</span>
          <span class="sc-name" title="${sanitize(s.source)}">${sanitize(s.source)}</span>
          <span class="sc-pct ${cls}">${s.score}%</span>
        </div>
        <div class="sc-pre">${sanitize(s.preview)}…</div>`;
      panel.appendChild(card);
    });

    toggle.addEventListener('click', () => {
      const open = panel.classList.toggle('open');
      toggle.classList.toggle('open', open);
      toggle.setAttribute('aria-expanded', String(open));
    });

    row.appendChild(toggle);
    row.appendChild(panel);
  }

  #scrollBottom() {
    const el = this.#msgEl;
    el.scrollTop = el.scrollHeight;
  }

  // ── Send / streaming ──────────────────────────────────────

  async #send() {
    const input = document.getElementById('user-input');
    const btn   = document.getElementById('send-btn');
    const text  = input.value.trim();
    if (!text || this.#stream) return;

    input.value       = '';
    input.style.height = 'auto';
    btn.disabled      = true;

    // Auto-name session from first user message
    const session = this.#sessions.findById(this.#sessionId);
    if (session && !session.messages?.length) {
      const name = `${text.slice(0, 46)}${text.length > 46 ? '…' : ''}`;
      this.#sessions.update(this.#sessionId, { name });
      document.getElementById('sess-title').textContent = name;
    }

    this.#conversation.push({ role: 'user', content: text });
    this.#appendUser(text);

    const row  = this.#appendTyping();
    const bbl  = row.querySelector('.bbl');
    bbl.innerHTML = '';

    let fullText = '';
    let sources  = [];

    this.#stream = this.#api.streamChat(this.#conversation, this.#docFilter, {
      onToken: (token) => {
        fullText += token;
        bbl.innerHTML = renderMarkdown(fullText);
        this.#scrollBottom();
      },
      onSources: (s) => { sources = s; },
      onError: (msg) => {
        bbl.className   = 'bbl error';
        bbl.textContent = msg;
        this.#scrollBottom();
        this.#finalizeStream(btn);
      },
      onDone: () => {
        bbl.innerHTML = renderMarkdown(fullText);
        const assistantMsg = { role: 'assistant', content: fullText, sources };
        this.#conversation.push(assistantMsg);
        this.#appendSources(row, sources);
        if (this.#sessionId) {
          this.#sessions.update(this.#sessionId, { messages: [...this.#conversation] });
        }
        this.#scrollBottom();
        this.#finalizeStream(btn);
        document.getElementById('user-input')?.focus();
      },
    });
  }

  #finalizeStream(btn) {
    this.#stream  = null;
    btn.disabled  = false;
  }

  // ── Event listeners ───────────────────────────────────────

  #attachListeners() {
    this.#handlers.newSess = () => {
      const s = this.#sessions.create();
      this.#activateSession(s.id);
    };

    this.#handlers.send = () => this.#send();

    this.#handlers.keydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.#send(); }
    };

    this.#handlers.autoResize = function () {
      this.style.height = 'auto';
      this.style.height = `${Math.min(this.scrollHeight, 140)}px`;
    };

    this.#handlers.fltToggle = (e) => {
      e.stopPropagation();
      this.#loadDocs().then(() => {
        document.getElementById('flt-dd').classList.toggle('open');
      });
    };

    this.#handlers.closeFlt = () => document.getElementById('flt-dd').classList.remove('open');

    document.getElementById('new-sess').addEventListener('click',   this.#handlers.newSess);
    document.getElementById('send-btn').addEventListener('click',   this.#handlers.send);
    document.getElementById('user-input').addEventListener('keydown', this.#handlers.keydown);
    document.getElementById('user-input').addEventListener('input',   this.#handlers.autoResize);
    document.getElementById('flt-btn').addEventListener('click',    this.#handlers.fltToggle);
    document.addEventListener('click', this.#handlers.closeFlt);
  }

  #detachListeners() {
    document.getElementById('new-sess')?.removeEventListener('click',   this.#handlers.newSess);
    document.getElementById('send-btn')?.removeEventListener('click',   this.#handlers.send);
    document.getElementById('user-input')?.removeEventListener('keydown', this.#handlers.keydown);
    document.getElementById('user-input')?.removeEventListener('input',   this.#handlers.autoResize);
    document.getElementById('flt-btn')?.removeEventListener('click',    this.#handlers.fltToggle);
    document.removeEventListener('click', this.#handlers.closeFlt);
  }
}
