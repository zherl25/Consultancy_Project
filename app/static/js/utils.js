/**
 * Pure utility functions — no side-effects, no DOM access.
 * CDN globals (marked, DOMPurify) are loaded as <script> tags before this module runs.
 */

const { marked, DOMPurify } = window;

marked.setOptions({ breaks: true, gfm: true });

/** Collision-resistant local ID (not a UUID — for client-side keys only). */
export const generateId = () =>
  `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;

/** @param {number} bytes @returns {string} */
export function formatBytes(bytes) {
  if (!bytes) return '';
  if (bytes < 1_024)       return `${bytes} B`;
  if (bytes < 1_048_576)   return `${(bytes / 1_024).toFixed(1)} KB`;
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

/** @param {string|undefined} iso @returns {string} */
export function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Lowercase extension without the dot. @param {string} filename */
export const getExtension = (filename) =>
  (filename.split('.').pop() ?? '').toLowerCase();

/** Sanitize arbitrary HTML to prevent XSS. */
export const sanitize = (/** @type {string} */ html) =>
  DOMPurify.sanitize(String(html));

/** Parse markdown text then sanitize. */
export const renderMarkdown = (/** @type {string} */ text) =>
  DOMPurify.sanitize(marked.parse(text));

/** CSS class for the `.tb` badge element based on filename extension. */
export function typeBadgeClass(filename) {
  return (
    { pdf: 'tb-pdf', docx: 'tb-docx', xlsx: 'tb-xlsx', txt: 'tb-txt', md: 'tb-md' }[
      getExtension(filename)
    ] ?? 'tb-txt'
  );
}

/** CSS class for the square doc-type icon based on filename extension. */
export function typeIconClass(filename) {
  return (
    { pdf: 'di-pdf', docx: 'di-docx', xlsx: 'di-xlsx', txt: 'di-txt', md: 'di-md' }[
      getExtension(filename)
    ] ?? 'di-txt'
  );
}
