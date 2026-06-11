/**
 * Lightweight hash-based SPA router.
 *
 * Each route controller must expose:
 *   pageId {string}  — DOM element ID to show/hide
 *   enter()          — called when navigating INTO this route
 *   leave()          — called when navigating AWAY (cleanup: cancel requests, remove listeners)
 */
export class Router {
  #routes = [];
  #active = null;

  /**
   * Register a route.
   * @param {string} prefix  e.g. '#docs' — matched as exact or as a prefix with '/'
   * @param {{ pageId: string, enter?: () => void | Promise<void>, leave?: () => void }} controller
   * @param {{ requiresAuth?: boolean }} [options]
   */
  add(prefix, controller, options = {}) {
    this.#routes.push({ prefix, controller, options });
    return this; // fluent
  }

  /** Begin listening for hash changes and dispatch the initial route. */
  start() {
    window.addEventListener('hashchange', () => this.#dispatch());
    this.#dispatch();
    return this;
  }

  /** @param {string} hash e.g. '#chat' */
  navigate(hash) {
    window.location.hash = hash;
  }

  // ── Private ───────────────────────────────────────────────

  #dispatch() {
    const hash  = window.location.hash || '#';
    const route = this.#resolveRoute(hash);
    if (!route || this.#active?.controller === route.controller) return;

    if (route.options?.requiresAuth && !localStorage.getItem('consultant_ai_token')) {
      window.location.hash = '#login';
      return;
    }

    this.#active?.controller?.leave?.();
    this.#active = route;

    this.#showPage(route.controller.pageId);
    route.controller.enter?.();
  }

  #resolveRoute(hash) {
    return (
      this.#routes.find((r) => hash === r.prefix || hash.startsWith(r.prefix + '/')) ??
      this.#routes.find((r) => r.prefix === '#')
    );
  }

  #showPage(targetId) {
    this.#routes.forEach(({ controller }) => {
      const el = document.getElementById(controller.pageId);
      if (el) el.classList.toggle('hidden', controller.pageId !== targetId);
    });

    const target = document.getElementById(targetId);
    if (!target) return;

    // Re-trigger animation on each navigation
    target.style.animation = 'none';
    void target.offsetWidth; // force reflow
    target.style.animation  = 'pageIn .38s cubic-bezier(.16,1,.3,1) forwards';
  }
}
