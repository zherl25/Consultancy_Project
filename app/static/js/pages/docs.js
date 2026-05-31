/**
 * Docs page controller.
 *
 * Responsibilities:
 *   - Drag-and-drop file upload with real XHR progress
 *   - Document library grid with staggered animation
 *   - Clean event-listener teardown on leave()
 */

import { formatBytes, formatDate, getExtension, sanitize, typeBadgeClass, typeIconClass } from '../utils.js';

const ALLOWED_EXTENSIONS = new Set(['pdf', 'docx', 'xlsx', 'txt', 'md']);

export class DocsPage {
  get pageId() { return 'page-docs'; }

  /**
   * @param {{
   *   api:   import('../api.js').ApiClient,
   *   toast: import('../toast.js').Toast,
   * }} deps
   */
  constructor({ api, toast }) {
    this.#api   = api;
    this.#toast = toast;
  }

  #api;
  #toast;
  /** @type {import('../api.js').Document[]} */
  #docs = [];
  /** @type {Record<string, EventListener>} Stored so we can removeEventListener cleanly. */
  #handlers = {};

  /**
   * Optional callback set by main.js — called when the user clicks "chat about this doc".
   * @type {((filename: string) => void) | null}
   */
  onChatAbout = null;

  // ── Lifecycle ─────────────────────────────────────────────

  enter() {
    this.#setupDropZone();
    this.#loadDocuments();
  }

  leave() {
    this.#teardownDropZone();
  }

  // ── Private: data ─────────────────────────────────────────

  async #loadDocuments() {
    try {
      this.#docs = await this.#api.getDocuments();
      this.#renderGrid();
    } catch (err) {
      this.#toast.show(`Could not load documents: ${err.message}`, 'error');
    }
  }

  async #deleteDocument(filename) {
    if (!confirm(`Remove "${filename}" from the knowledge base?`)) return;
    try {
      await this.#api.deleteDocument(filename);
      this.#toast.show(`Removed "${filename}"`, 'success');
      this.#docs = await this.#api.getDocuments();
      this.#renderGrid();
    } catch (err) {
      this.#toast.show(err.message, 'error');
    }
  }

  #uploadFile(file) {
    const ext = getExtension(file.name);
    if (!ALLOWED_EXTENSIONS.has(ext)) {
      this.#toast.show(`Unsupported file type: .${ext}`, 'error');
      return;
    }

    const item   = this.#createUploadItem(file.name, ext);
    const setBar = (pct) => { const b = item.querySelector('.ul-bar'); if (b) b.style.width = `${pct}%`; };
    const setSt  = (text, cls = '') => {
      const st = item.querySelector('.ul-st');
      if (!st) return;
      st.textContent = text;
      st.className   = `ul-st${cls ? ' ' + cls : ''}`;
    };

    this.#api.uploadFile(file, setBar)
      .then(async (data) => {
        setBar(100);
        setSt(`✓ ${data.chunks_indexed} chunks`, 'ok');
        this.#toast.show(`"${data.filename}" indexed — ${data.chunks_indexed} chunks`, 'success');
        this.#docs = await this.#api.getDocuments();
        this.#renderGrid();
        setTimeout(() => item.remove(), 4_000);
      })
      .catch((err) => {
        setBar(100);
        setSt(`✕ ${err.message}`, 'err');
        this.#toast.show(err.message, 'error');
        setTimeout(() => item.remove(), 5_000);
      });
  }

  // ── Private: rendering ────────────────────────────────────

  #renderGrid() {
    const grid = document.getElementById('doc-grid');
    const cnt  = document.getElementById('lib-cnt');

    cnt.textContent = `${this.#docs.length} file${this.#docs.length !== 1 ? 's' : ''}`;

    if (!this.#docs.length) {
      grid.innerHTML = `
        <div class="empty-state">
          <svg width="44" height="44" fill="none" stroke="#cbd5e1" stroke-width="1.5" viewBox="0 0 24 24">
            <path d="M9 12h6M9 16h6M17 21H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"
                  stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <p>No documents yet — upload files above to get started.</p>
        </div>`;
      return;
    }

    grid.innerHTML = '';
    this.#docs.forEach((doc, i) => {
      const ext  = getExtension(doc.filename).toUpperCase();
      const card = document.createElement('div');
      card.className          = 'doc-card';
      card.style.animationDelay = `${i * 0.045}s`;
      card.setAttribute('role', 'listitem');
      card.innerHTML = `
        <div class="doc-type-icon ${typeIconClass(doc.filename)}" aria-hidden="true">${ext}</div>
        <div class="doc-info">
          <div class="doc-name" title="${sanitize(doc.filename)}">${sanitize(doc.filename)}</div>
          <div class="doc-meta">
            ${doc.chunk_count} chunks · ${formatBytes(doc.size_bytes)}<br/>
            Uploaded ${formatDate(doc.uploaded_at)}
          </div>
        </div>
        <div class="doc-btns">
          <button class="doc-btn chat-btn" title="Chat about this document" aria-label="Chat about ${sanitize(doc.filename)}">💬</button>
          <button class="doc-btn del"      title="Delete document"          aria-label="Delete ${sanitize(doc.filename)}">🗑</button>
        </div>`;

      card.querySelector('.chat-btn').addEventListener('click', () => this.onChatAbout?.(doc.filename));
      card.querySelector('.del').addEventListener('click',      () => this.#deleteDocument(doc.filename));
      grid.appendChild(card);
    });
  }

  #createUploadItem(filename, ext) {
    const log  = document.getElementById('upload-log');
    const item = document.createElement('div');
    item.className = 'ul-item';
    item.innerHTML = `
      <span class="tb ${typeBadgeClass(filename)}">${ext.toUpperCase()}</span>
      <span class="ul-name">${sanitize(filename)}</span>
      <div class="ul-bar-w"><div class="ul-bar" style="width:0%"></div></div>
      <span class="ul-st">Uploading…</span>`;
    log.prepend(item);
    return item;
  }

  // ── Private: drop zone ────────────────────────────────────

  #setupDropZone() {
    const zone  = document.getElementById('drop-zone');
    const input = document.getElementById('file-input');
    const page  = document.getElementById('page-docs');

    this.#handlers.click      = ()  => input.click();
    this.#handlers.change     = ()  => { [...input.files].forEach((f) => this.#uploadFile(f)); input.value = ''; };
    this.#handlers.dragover   = (e) => { e.preventDefault(); zone.classList.add('over'); };
    this.#handlers.dragleave  = ()  => zone.classList.remove('over');
    this.#handlers.drop       = (e) => { e.preventDefault(); zone.classList.remove('over'); [...e.dataTransfer.files].forEach((f) => this.#uploadFile(f)); };
    this.#handlers.keydown    = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } };

    // Page-level drop so user can drop anywhere on the docs page
    this.#handlers.pageDragover = (e) => { e.preventDefault(); if (!zone.contains(e.target)) zone.classList.add('over'); };
    this.#handlers.pageDrop     = (e) => { e.preventDefault(); zone.classList.remove('over'); if (!zone.contains(e.target)) [...e.dataTransfer.files].forEach((f) => this.#uploadFile(f)); };

    zone.addEventListener('click',    this.#handlers.click);
    zone.addEventListener('keydown',  this.#handlers.keydown);
    input.addEventListener('change',  this.#handlers.change);
    zone.addEventListener('dragover', this.#handlers.dragover);
    zone.addEventListener('dragleave',this.#handlers.dragleave);
    zone.addEventListener('drop',     this.#handlers.drop);
    page.addEventListener('dragover', this.#handlers.pageDragover);
    page.addEventListener('drop',     this.#handlers.pageDrop);
  }

  #teardownDropZone() {
    const zone  = document.getElementById('drop-zone');
    const input = document.getElementById('file-input');
    const page  = document.getElementById('page-docs');
    if (!zone || !input || !page) return;

    zone.removeEventListener('click',    this.#handlers.click);
    zone.removeEventListener('keydown',  this.#handlers.keydown);
    input.removeEventListener('change',  this.#handlers.change);
    zone.removeEventListener('dragover', this.#handlers.dragover);
    zone.removeEventListener('dragleave',this.#handlers.dragleave);
    zone.removeEventListener('drop',     this.#handlers.drop);
    page.removeEventListener('dragover', this.#handlers.pageDragover);
    page.removeEventListener('drop',     this.#handlers.pageDrop);
  }
}
