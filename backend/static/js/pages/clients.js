/**
 * Admin page: client companies with their generated sets, and the master template library.
 */
import { escapeHtml, formatDateTime } from '../utils.js';

export class ClientsPage {
  pageId = 'page-clients';

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

  async enter() {
    this.#el('clients-list').addEventListener('click', this.#onClick);
    this.#el('templates-list').addEventListener('click', this.#onClick);
    this.#el('templates-list').addEventListener('change', this.#onUpload);
    await this.#loadTemplates();   // first: it supplies the activity labels used in the client list
    await this.#loadClients();
  }

  leave() {
    this.#el('clients-list').removeEventListener('click', this.#onClick);
    this.#el('templates-list').removeEventListener('click', this.#onClick);
    this.#el('templates-list').removeEventListener('change', this.#onUpload);
  }

  // ── Private ────────────────────────────────────────────────

  #api;
  #toast;
  #moduleLabels = {};

  #el = (id) => document.getElementById(id);

  async #loadClients() {
    const box = this.#el('clients-list');
    try {
      const clients = (await this.#api.getClients()) ?? [];
      if (!clients.length) {
        box.innerHTML = '<p class="gen-hint">No client has signed up yet.</p>';
        return;
      }
      box.innerHTML = `<table class="gen-table">
        <thead><tr><th>Company</th><th>Email</th><th>Signed up</th><th>Activities</th><th>Latest documents</th></tr></thead>
        <tbody>${clients.map((c) => {
          const g = c.generations[0];
          return `<tr>
            <td><strong>${escapeHtml(c.company_name)}</strong></td>
            <td>${escapeHtml(c.email)}</td>
            <td>${escapeHtml(formatDateTime(c.created_at))}</td>
            <td>${c.modules.length ? c.modules.map((m) => `<span class="gen-chip">${escapeHtml(this.#moduleLabels[m] ?? m)}</span>`).join('')
                                   : '<span class="gen-hint">Core only</span>'}</td>
            <td>${g ? `<button type="button" class="gen-btn ghost" data-client-zip="${g.id}">
                         ${g.file_count} files · ${escapeHtml(formatDateTime(g.created_at))}</button>
                       ${g.flag_count ? `<span class="gen-flag-count" title="${escapeHtml(g.flags.join(', '))}">${g.flag_count} to confirm</span>` : ''}`
                    : '<span class="gen-hint">Not generated yet</span>'}</td>
          </tr>`;
        }).join('')}</tbody></table>`;
    } catch (err) {
      box.innerHTML = `<p class="gen-hint">${escapeHtml(err.message ?? 'Could not load clients.')}</p>`;
    }
  }

  async #loadTemplates() {
    const box = this.#el('templates-list');
    try {
      const templates = (await this.#api.getTemplates()) ?? [];
      if (!templates.length) {
        box.innerHTML = '<p class="gen-hint">The template library has not been built yet (see tools/build_templates.py).</p>';
        return;
      }
      for (const t of templates) this.#moduleLabels[t.module] = t.module_label;
      const kinds = { manual: 'Quality Manual', procedure: 'Procedure', procedure_appendix: 'Procedure appendix', form: 'Form' };
      box.innerHTML = `<table class="gen-table">
        <thead><tr><th>Document</th><th>Type</th><th>Used for</th><th>Last changed</th><th></th></tr></thead>
        <tbody>${templates.map((t) => `<tr>
          <td>${escapeHtml(t.title)}</td>
          <td>${kinds[t.kind] ?? t.kind}</td>
          <td>${escapeHtml(t.module_label)}</td>
          <td>${t.updated_at ? escapeHtml(new Date(t.updated_at * 1000).toLocaleDateString(undefined,
                 { day: 'numeric', month: 'short', year: 'numeric' })) : ''}</td>
          <td class="gen-table-actions">
            <button type="button" class="gen-btn ghost" data-template="${t.key}">Download</button>
            <label class="gen-btn ghost">Replace
              <input type="file" class="sr-only" data-replace="${t.key}"
                     accept="${t.file.endsWith('.xlsx') ? '.xlsx' : '.docx'}" /></label>
          </td></tr>`).join('')}</tbody></table>`;
    } catch (err) {
      box.innerHTML = `<p class="gen-hint">${escapeHtml(err.message ?? 'Could not load templates.')}</p>`;
    }
  }

  #onClick = async (e) => {
    const zip = e.target.closest('[data-client-zip]');
    const tpl = e.target.closest('[data-template]');
    try {
      if (zip) await this.#api.download(`/admin/generations/${zip.dataset.clientZip}/download`, 'documents.zip');
      if (tpl) await this.#api.download(`/admin/templates/${tpl.dataset.template}/download`);
    } catch (err) {
      this.#toast.show(err.message ?? 'Download failed.', 'error');
    }
  };

  #onUpload = async (e) => {
    const input = e.target.closest('[data-replace]');
    const file  = input?.files?.[0];
    if (!file) return;
    input.value = '';
    try {
      await this.#api.replaceTemplate(input.dataset.replace, file);
      this.#toast.show('Template replaced. New client documents will use it.', 'success');
      await this.#loadTemplates();
    } catch (err) {
      this.#toast.show(err.message ?? 'Could not replace the template.', 'error');
    }
  };
}
