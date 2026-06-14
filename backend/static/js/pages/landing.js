/**
 * Landing page controller.
 * All behaviour is CSS-driven (animations, hover effects) — no JS needed at runtime.
 * onEnter is wired by main.js to redirect authenticated users straight to the app.
 */
export class LandingPage {
  get pageId() { return 'page-landing'; }

  /** Set by main.js — called on every entry to this page. */
  onEnter = null;

  enter() { this.onEnter?.(); }
  leave() {}
}
