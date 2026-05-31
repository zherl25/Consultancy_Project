/**
 * Persistent chat session store backed by localStorage.
 *
 * Emits change events via a subscriber pattern so any UI that cares about
 * session list changes stays in sync without polling.
 */

import { generateId } from './utils.js';

const STORAGE_KEY = 'consultant_ai_sessions';
const LAST_KEY    = 'consultant_ai_last_session';

/**
 * @typedef {{
 *   id:             string,
 *   name:           string,
 *   messages:       Array<{ role: string, content: string, sources?: Array }>,
 *   documentFilter: string|null,
 *   createdAt:      string,
 *   updatedAt:      string,
 * }} Session
 */

export class SessionStore {
  /** @type {Set<(sessions: Session[]) => void>} */
  #listeners = new Set();

  // ── Reads ─────────────────────────────────────────────────

  /** @returns {Session[]} */
  getAll() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
    } catch {
      return [];
    }
  }

  /** @param {string} id @returns {Session|null} */
  findById(id) {
    return this.getAll().find((s) => s.id === id) ?? null;
  }

  /** @returns {string|null} */
  getLastId() {
    return localStorage.getItem(LAST_KEY);
  }

  // ── Writes ────────────────────────────────────────────────

  /**
   * Create and persist a new session. Returns the new session object.
   * @param {Partial<Session>} overrides
   * @returns {Session}
   */
  create(overrides = {}) {
    const session = /** @type {Session} */ ({
      id:             generateId(),
      name:           'New Chat',
      messages:       [],
      documentFilter: null,
      createdAt:      new Date().toISOString(),
      updatedAt:      new Date().toISOString(),
      ...overrides,
    });
    this.#save([session, ...this.getAll()]);
    return session;
  }

  /**
   * Partially update a session by ID. Automatically updates `updatedAt`.
   * @param {string}          id
   * @param {Partial<Session>} patch
   * @returns {Session}
   */
  update(id, patch) {
    const sessions = this.getAll();
    const index    = sessions.findIndex((s) => s.id === id);
    if (index === -1) throw new Error(`Session "${id}" not found`);

    sessions[index] = { ...sessions[index], ...patch, updatedAt: new Date().toISOString() };
    this.#save(sessions);
    return sessions[index];
  }

  /** @param {string} id */
  delete(id) {
    this.#save(this.getAll().filter((s) => s.id !== id));
  }

  /** @param {string} id */
  setLastId(id) {
    localStorage.setItem(LAST_KEY, id);
  }

  // ── Subscription ──────────────────────────────────────────

  /**
   * Subscribe to any change (create / update / delete).
   * @param {(sessions: Session[]) => void} fn
   * @returns {() => void}  Call to unsubscribe.
   */
  subscribe(fn) {
    this.#listeners.add(fn);
    return () => this.#listeners.delete(fn);
  }

  // ── Private ───────────────────────────────────────────────

  #save(sessions) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    this.#listeners.forEach((fn) => fn(sessions));
  }
}
