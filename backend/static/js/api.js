/**
 * HTTP API client — all server communication goes through here.
 * Returns typed data; throws ApiError on non-2xx responses.
 */

/** Typed error that carries the HTTP status code. */
export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {number} status  HTTP status code, or 0 for network errors
   */
  constructor(message, status) {
    super(message);
    this.name   = 'ApiError';
    this.status = status;
  }
}

/**
 * @typedef {{ filename: string, uploaded_at: string, chunk_count: number, size_bytes: number, project_id: string|null, folder_id: string|null }} Document
 * @typedef {{ role: string, content: string }} ChatMessage
 * @typedef {{ source: string, score: number, preview: string }} Source
 * @typedef {{ id: string, name: string, description: string, created_at: string, updated_at: string, file_count: number, folders: FolderResponse[] }} ProjectResponse
 * @typedef {{ id: string, project_id: string, name: string, sort_order: number, created_at: string, documents: Document[] }} FolderResponse
 */

export class ApiClient {
  /** @param {string} [baseUrl] Defaults to the current origin. */
  constructor(baseUrl = '') {
    this._base = baseUrl;
    /** Set by main.js — called whenever the server returns 401. */
    this.onUnauthorized = null;
  }

  // ── Auth ─────────────────────────────────────────────────

  /**
   * Exchange credentials for a JWT.
   * @param {string} username
   * @param {string} password
   * @returns {Promise<{ access_token: string, token_type: string }>}
   */
  async login(username, password) {
    const res = await fetch(`${this._base}/auth/login`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ username, password }),
    });
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  /**
   * Validate the stored token. Throws ApiError(401) if invalid/expired.
   * @returns {Promise<{ username: string }>}
   */
  async me() {
    const res = await fetch(`${this._base}/auth/me`, { headers: this._authHeader() });
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  // ── Projects ──────────────────────────────────────────────

  /** @returns {Promise<ProjectResponse[]>} */
  async getProjects() {
    const res = await fetch(`${this._base}/projects`, { headers: this._authHeader() });
    if (res.status === 401) { this._handleUnauth(); return []; }
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  /**
   * @param {string} name
   * @param {string} [description]
   * @returns {Promise<ProjectResponse>}
   */
  async createProject(name, description = '') {
    const res = await fetch(`${this._base}/projects`, {
      method:  'POST',
      headers: { ...this._authHeader(), 'Content-Type': 'application/json' },
      body:    JSON.stringify({ name, description }),
    });
    if (res.status === 401) { this._handleUnauth(); return null; }
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  /**
   * @param {string} id
   * @returns {Promise<ProjectResponse>}
   */
  async getProject(id) {
    const res = await fetch(`${this._base}/projects/${id}`, { headers: this._authHeader() });
    if (res.status === 401) { this._handleUnauth(); return null; }
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  /**
   * @param {string} id
   * @param {{ name?: string, description?: string }} updates
   * @returns {Promise<ProjectResponse>}
   */
  async updateProject(id, updates) {
    const res = await fetch(`${this._base}/projects/${id}`, {
      method:  'PATCH',
      headers: { ...this._authHeader(), 'Content-Type': 'application/json' },
      body:    JSON.stringify(updates),
    });
    if (res.status === 401) { this._handleUnauth(); return null; }
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  /** @param {string} id */
  async deleteProject(id) {
    const res = await fetch(`${this._base}/projects/${id}`, {
      method:  'DELETE',
      headers: this._authHeader(),
    });
    if (res.status === 401) { this._handleUnauth(); return; }
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  // ── Folders ───────────────────────────────────────────────

  /**
   * @param {string} projectId
   * @param {string} name
   * @param {number} [sortOrder]
   * @returns {Promise<FolderResponse>}
   */
  async createFolder(projectId, name, sortOrder = 0) {
    const res = await fetch(`${this._base}/projects/${projectId}/folders`, {
      method:  'POST',
      headers: { ...this._authHeader(), 'Content-Type': 'application/json' },
      body:    JSON.stringify({ name, sort_order: sortOrder }),
    });
    if (res.status === 401) { this._handleUnauth(); return null; }
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  /**
   * @param {string} projectId
   * @param {string} folderId
   * @param {{ name?: string }} updates
   * @returns {Promise<FolderResponse>}
   */
  async updateFolder(projectId, folderId, updates) {
    const res = await fetch(`${this._base}/projects/${projectId}/folders/${folderId}`, {
      method:  'PATCH',
      headers: { ...this._authHeader(), 'Content-Type': 'application/json' },
      body:    JSON.stringify(updates),
    });
    if (res.status === 401) { this._handleUnauth(); return null; }
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  /**
   * @param {string} projectId
   * @param {string} folderId
   */
  async deleteFolder(projectId, folderId) {
    const res = await fetch(`${this._base}/projects/${projectId}/folders/${folderId}`, {
      method:  'DELETE',
      headers: this._authHeader(),
    });
    if (res.status === 401) { this._handleUnauth(); return; }
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  // ── Documents ────────────────────────────────────────────

  /**
   * @param {string} [projectId]
   * @returns {Promise<Document[]>}
   */
  async getDocuments(projectId) {
    const url = projectId
      ? `${this._base}/documents?project_id=${encodeURIComponent(projectId)}`
      : `${this._base}/documents`;
    const res = await fetch(url, { headers: this._authHeader() });
    if (res.status === 401) { this._handleUnauth(); return []; }
    if (!res.ok) await this._reject(res);
    return (await res.json()).documents;
  }

  /**
   * Upload a single file using XHR so we get real upload-progress events.
   * @param {File}   file
   * @param {string} [projectId]
   * @param {string} [folderId]
   * @param {(pct: number) => void} [onProgress]
   * @returns {Promise<{ filename: string, chunks_indexed: number, size_bytes: number }>}
   */
  uploadFile(file, projectId, folderId, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr  = new XMLHttpRequest();
      const form = new FormData();
      form.append('file', file);

      const params = new URLSearchParams();
      if (projectId) params.set('project_id', projectId);
      if (folderId)  params.set('folder_id',  folderId);
      const qs = params.toString() ? `?${params.toString()}` : '';

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100));
      });

      xhr.addEventListener('load', () => {
        if (xhr.status === 401) {
          this._handleUnauth();
          reject(new ApiError('Session expired — please sign in again.', 401));
          return;
        }
        const body = this._parseJson(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body);
        } else {
          reject(new ApiError(body?.detail ?? `Upload failed (${xhr.status})`, xhr.status));
        }
      });

      xhr.addEventListener('error', () => reject(new ApiError('Network error during upload', 0)));
      xhr.addEventListener('abort', () => reject(new ApiError('Upload cancelled', 0)));

      xhr.open('POST', `${this._base}/upload${qs}`);
      const token = localStorage.getItem('consultant_ai_token');
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.send(form);
    });
  }

  /**
   * @param {string} filename
   * @returns {Promise<{ filename: string, chunks_removed: number }>}
   */
  async deleteDocument(filename) {
    const res = await fetch(
      `${this._base}/documents/${encodeURIComponent(filename)}`,
      { method: 'DELETE', headers: this._authHeader() },
    );
    if (res.status === 401) { this._handleUnauth(); return; }
    if (!res.ok) await this._reject(res);
    return res.json();
  }

  // ── Chat streaming ────────────────────────────────────────

  /**
   * Open an SSE chat stream. Returns a handle whose `abort()` cancels it.
   *
   * @param {ChatMessage[]} messages
   * @param {string|null}   projectFilter  project_id to scope retrieval, or null for all
   * @param {{
   *   onToken:   (token: string)     => void,
   *   onSources: (sources: Source[]) => void,
   *   onError:   (message: string)   => void,
   *   onDone:    ()                  => void,
   * }} callbacks
   * @returns {{ abort: () => void }}
   */
  streamChat(messages, projectFilter, callbacks) {
    const controller = new AbortController();

    (async () => {
      try {
        const res = await fetch(`${this._base}/chat`, {
          method:  'POST',
          headers: { ...this._authHeader(), 'Content-Type': 'application/json' },
          body:    JSON.stringify({ messages, project_filter: projectFilter }),
          signal:  controller.signal,
        });

        if (res.status === 401) { this._handleUnauth(); return; }

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          callbacks.onError?.(body.detail ?? `Server error ${res.status}`);
          return;
        }

        await this._readSSE(res.body, callbacks);
      } catch (err) {
        if (err.name !== 'AbortError') {
          callbacks.onError?.(`Connection lost: ${err.message}`);
        }
      }
    })();

    return { abort: () => controller.abort() };
  }

  // ── Private helpers ───────────────────────────────────────

  /** Build Authorization header from stored token. */
  _authHeader() {
    const token = localStorage.getItem('consultant_ai_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  /** Clear token and invoke the 401 callback wired up by main.js. */
  _handleUnauth() {
    localStorage.removeItem('consultant_ai_token');
    this.onUnauthorized?.();
  }

  /** Read an SSE stream and dispatch events to callbacks. */
  async _readSSE(body, callbacks) {
    const reader  = body.getReader();
    const decoder = new TextDecoder();
    let buffer    = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() ?? '';

      for (const part of parts) {
        const dataLine = part.split('\n').find((l) => l.startsWith('data: '));
        if (!dataLine) continue;

        let event;
        try { event = JSON.parse(dataLine.slice(6)); } catch { continue; }

        if (event.type === 'token')   { callbacks.onToken?.(event.content); continue; }
        if (event.type === 'sources') { callbacks.onSources?.(event.sources); continue; }
        if (event.type === 'error')   { callbacks.onError?.(event.message);  return; }
        if (event.type === 'done')    { callbacks.onDone?.();                return; }
      }
    }

    callbacks.onDone?.();
  }

  /** Throw an ApiError from a non-ok Response. */
  async _reject(res) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail ?? `HTTP ${res.status}`, res.status);
  }

  /** Safe JSON parse — returns null on failure. */
  _parseJson(text) {
    try { return JSON.parse(text); } catch { return null; }
  }
}
