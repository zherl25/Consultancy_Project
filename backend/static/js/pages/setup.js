/**
 * Client page: the documentation questionnaire, logo, generation and downloads.
 */
import { escapeHtml, formatDateTime } from '../utils.js';
import { showConfirm } from '../confirm.js';

export class SetupPage {
  pageId = 'page-setup';

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
    this.#bind();
    try {
      const [q, me, gens] = await Promise.all([
        this.#api.getQuestionnaire(), this.#api.me(), this.#api.getGenerations(),
      ]);
      if (!q) return;
      this.#schema = q.schema;
      document.getElementById('setup-company').textContent = me?.company_name ?? '';
      this.#render(q.answers);
      this.#setSaved(q.updated_at);
      this.#showLogo(q.has_logo);
      this.#renderResults(gens ?? []);
    } catch (err) {
      this.#toast.show(err.message ?? 'Could not load your questionnaire.', 'error');
    }
  }

  leave() {
    this.#unbind?.();
    this.#unbind = null;
    if (this.#logoUrl) URL.revokeObjectURL(this.#logoUrl);
    this.#logoUrl = null;
  }

  // ── Private ────────────────────────────────────────────────

  #api;
  #toast;
  #schema  = null;
  #unbind  = null;
  #logoUrl = null;
  #busy    = false;
  #dirty   = false;

  #el = (id) => document.getElementById(id);

  #bind() {
    const form = this.#el('gen-form');
    const on = (el, ev, fn) => { el.addEventListener(ev, fn); return () => el.removeEventListener(ev, fn); };
    const offs = [
      on(form, 'submit', (e) => { e.preventDefault(); this.#save(); }),
      on(form, 'input', () => this.#markDirty()),
      on(form, 'change', (e) => {
        if (e.target.name === 'policy_mode' || e.target.name === 'objectives_mode') this.#syncModes();
        this.#markDirty();
      }),
      on(form, 'click', (e) => {
        const del = e.target.closest('[data-remove]');
        if (del) { del.closest('[data-row]').remove(); this.#markDirty(); }
      }),
      on(this.#el('gen-generate'), 'click', () => this.#generate()),
      on(this.#el('gen-policy-add'), 'click', () => { this.#addPolicy(''); this.#markDirty(); }),
      on(this.#el('gen-objective-add'), 'click', () => { this.#addObjective({}); this.#markDirty(); }),
      on(this.#el('gen-logo-input'), 'change', (e) => this.#uploadLogo(e.target)),
      on(this.#el('gen-logo-remove'), 'click', () => this.#removeLogo()),
      on(this.#el('gen-results'), 'click', (e) => this.#onResultsClick(e)),
    ];
    this.#unbind = () => offs.forEach((off) => off());
  }

  // ── Questionnaire rendering ────────────────────────────────

  #render(answers) {
    const s = this.#schema;
    this.#el('gen-fields').innerHTML = s.fields.map((f) => {
      const id    = `gen-f-${f.key}`;
      const value = escapeHtml(answers[f.key] ?? '');
      const ph    = f.placeholder ? ` placeholder="${escapeHtml(f.placeholder)}"` : '';
      const input = f.type === 'textarea'
        ? `<textarea id="${id}" name="${f.key}" rows="3"${ph}>${value}</textarea>`
        : `<input id="${id}" name="${f.key}" type="${f.type === 'date' ? 'date' : 'text'}" value="${value}"${ph} />`;
      return `<div class="gen-field">
        <label for="${id}">${escapeHtml(f.label)}</label>${input}
        ${f.help ? `<span class="gen-hint">${escapeHtml(f.help)}</span>` : ''}
      </div>`;
    }).join('');

    const chosen = new Set(answers.modules ?? []);
    this.#el('gen-modules').innerHTML = s.modules.map((m) => `
      <label class="gen-module">
        <input type="checkbox" name="modules" value="${m.key}"${chosen.has(m.key) ? ' checked' : ''} />
        <span><strong>${escapeHtml(m.label)}</strong><small>${escapeHtml(m.help)}</small></span>
      </label>`).join('');

    this.#el('gen-policy-standard').innerHTML =
      s.standard_policy.map((p) => `<li>${escapeHtml(p)}</li>`).join('');
    this.#el('gen-policy-list').innerHTML = '';
    const points = answers.policy_points?.length ? answers.policy_points : [''];
    points.forEach((p) => this.#addPolicy(p));

    this.#el('gen-objectives-list').innerHTML = '';
    const objectives = answers.objectives?.length ? answers.objectives : [{}];
    objectives.forEach((o) => this.#addObjective(o));

    this.#setRadio('policy_mode', answers.policy_mode);
    this.#setRadio('objectives_mode', answers.objectives_mode);
    this.#syncModes();
    this.#dirty = false;
  }

  #setRadio(name, value) {
    const input = this.#el('gen-form').querySelector(`input[name="${name}"][value="${value}"]`);
    if (input) input.checked = true;
  }

  #syncModes() {
    const mode = (name) => this.#el('gen-form').querySelector(`input[name="${name}"]:checked`)?.value;
    const policyCustom = mode('policy_mode') === 'custom';
    const objCustom    = mode('objectives_mode') === 'custom';
    this.#el('gen-policy-standard').classList.toggle('hidden', policyCustom);
    this.#el('gen-policy-custom').classList.toggle('hidden', !policyCustom);
    this.#el('gen-objectives-standard').classList.toggle('hidden', objCustom);
    this.#el('gen-objectives-custom').classList.toggle('hidden', !objCustom);
  }

  #addPolicy(text) {
    const row = document.createElement('div');
    row.className = 'gen-row';
    row.dataset.row = 'policy';
    row.innerHTML = `
      <input type="text" data-policy aria-label="Policy commitment" value="${escapeHtml(text)}"
             placeholder="e.g. Delivering projects on time and to specification." />
      <button type="button" class="gen-x" data-remove aria-label="Remove commitment">×</button>`;
    this.#el('gen-policy-list').appendChild(row);
  }

  #addObjective(o) {
    const cols = this.#schema.objective_columns;
    const box  = document.createElement('div');
    box.className = 'gen-objective';
    box.dataset.row = 'objective';
    box.innerHTML = cols.map((c) => `
      <label class="gen-mini">${escapeHtml(c.label)}
        <input type="text" data-obj="${c.key}" value="${escapeHtml(o[c.key] ?? '')}" />
      </label>`).join('') +
      '<button type="button" class="gen-x" data-remove aria-label="Remove objective">×</button>';
    this.#el('gen-objectives-list').appendChild(box);
  }

  #collect() {
    const form = this.#el('gen-form');
    const out  = {};
    for (const f of this.#schema.fields) out[f.key] = form.elements[f.key]?.value ?? '';
    out.modules         = [...form.querySelectorAll('input[name="modules"]:checked')].map((i) => i.value);
    out.policy_mode     = form.querySelector('input[name="policy_mode"]:checked')?.value ?? 'standard';
    out.objectives_mode = form.querySelector('input[name="objectives_mode"]:checked')?.value ?? 'standard';
    out.policy_points   = [...form.querySelectorAll('[data-policy]')].map((i) => i.value.trim()).filter(Boolean);
    out.objectives      = [...form.querySelectorAll('[data-row="objective"]')].map((box) =>
      Object.fromEntries([...box.querySelectorAll('[data-obj]')].map((i) => [i.dataset.obj, i.value.trim()])))
      .filter((o) => Object.values(o).some(Boolean));
    return out;
  }

  // ── Save / generate ────────────────────────────────────────

  #markDirty() {
    this.#dirty = true;
    this.#el('gen-saved').textContent = 'Unsaved changes';
  }

  #setSaved(iso) {
    this.#dirty = false;
    this.#el('gen-saved').textContent = iso ? `Saved ${formatDateTime(iso)}` : 'Not saved yet';
  }

  async #save({ quiet = false } = {}) {
    try {
      const res = await this.#api.saveQuestionnaire(this.#collect());
      if (!res) return false;
      this.#setSaved(res.updated_at);
      if (!quiet) this.#toast.show('Answers saved.', 'success');
      return true;
    } catch (err) {
      this.#toast.show(err.message ?? 'Could not save your answers.', 'error');
      return false;
    }
  }

  async #generate() {
    if (this.#busy) return;
    this.#busy = true;
    const btn = this.#el('gen-generate');
    btn.disabled = true;
    btn.textContent = 'Generating…';
    try {
      if (!(await this.#save({ quiet: true }))) return;
      const gen = await this.#api.generateDocuments();
      if (!gen) return;
      this.#toast.show(`${gen.file_count} documents ready.`, 'success');
      this.#renderResults((await this.#api.getGenerations()) ?? [gen]);
      this.#el('gen-results').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
      this.#toast.show(err.message ?? 'Could not generate the documents.', 'error');
    } finally {
      this.#busy = false;
      btn.disabled = false;
      btn.textContent = 'Generate documents';
    }
  }

  // ── Logo ───────────────────────────────────────────────────

  async #showLogo(hasLogo) {
    if (this.#logoUrl) URL.revokeObjectURL(this.#logoUrl);
    this.#logoUrl = hasLogo ? await this.#api.getLogoUrl() : null;
    const img = this.#el('gen-logo-img');
    img.classList.toggle('hidden', !this.#logoUrl);
    if (this.#logoUrl) img.src = this.#logoUrl;
    this.#el('gen-logo-none').classList.toggle('hidden', !!this.#logoUrl);
    this.#el('gen-logo-remove').classList.toggle('hidden', !this.#logoUrl);
  }

  async #uploadLogo(input) {
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    try {
      await this.#api.uploadLogo(file);
      await this.#showLogo(true);
      this.#toast.show('Logo uploaded. It will appear in newly generated documents.', 'success');
    } catch (err) {
      this.#toast.show(err.message ?? 'Could not upload the logo.', 'error');
    }
  }

  async #removeLogo() {
    try {
      await this.#api.deleteLogo();
      await this.#showLogo(false);
    } catch (err) {
      this.#toast.show(err.message ?? 'Could not remove the logo.', 'error');
    }
  }

  // ── Results ────────────────────────────────────────────────

  #renderResults(gens) {
    const box = this.#el('gen-results');
    if (!gens.length) { box.innerHTML = ''; return; }
    const [latest, ...older] = gens;
    const folders = {};
    for (const f of latest.files) (folders[f.path.split('/')[0]] ??= []).push(f);

    box.innerHTML = `
      <div class="gen-card">
        <div class="gen-result-hdr">
          <div>
            <h2>Your documents</h2>
            <p class="gen-hint">Generated ${escapeHtml(formatDateTime(latest.created_at))} · ${latest.file_count} files</p>
          </div>
          <button type="button" class="gen-btn primary" data-zip="${latest.id}">Download all (.zip)</button>
        </div>
        ${latest.flags.length ? `
          <div class="gen-flags" role="note">
            <strong>${latest.flags.length} item${latest.flags.length > 1 ? 's' : ''} to confirm.</strong>
            These are highlighted in yellow in the documents:
            <ul>${latest.flags.map((f) => `<li>${escapeHtml(f)}</li>`).join('')}</ul>
          </div>` : '<p class="gen-ok">Every field was filled in. Nothing to confirm.</p>'}
        ${Object.entries(folders).map(([folder, files]) => `
          <h3 class="gen-folder">${escapeHtml(folder)}</h3>
          <ul class="gen-files">${files.map((f) => `
            <li>
              <button type="button" class="gen-file" data-gen="${latest.id}" data-path="${escapeHtml(f.path)}">
                <span class="tb ${f.path.endsWith('.xlsx') ? 'tb-xlsx' : 'tb-docx'}">${f.path.endsWith('.xlsx') ? 'XLSX' : 'DOCX'}</span>
                ${escapeHtml(f.path.split('/').pop())}
              </button>
              ${f.flags.length ? `<span class="gen-flag-count" title="${escapeHtml(f.flags.join(', '))}">${f.flags.length} to confirm</span>` : ''}
            </li>`).join('')}
          </ul>`).join('')}
      </div>
      ${older.length ? `
        <div class="gen-card">
          <h2>Earlier versions</h2>
          <ul class="gen-history">${older.map((g) => `
            <li>
              <span>${escapeHtml(formatDateTime(g.created_at))} · ${g.file_count} files
                ${g.flag_count ? `· ${g.flag_count} to confirm` : ''}</span>
              <span>
                <button type="button" class="gen-btn ghost" data-zip="${g.id}">Download</button>
                <button type="button" class="gen-btn ghost danger" data-delete="${g.id}">Delete</button>
              </span>
            </li>`).join('')}
          </ul>
        </div>` : ''}`;
  }

  async #onResultsClick(e) {
    const zip  = e.target.closest('[data-zip]');
    const file = e.target.closest('[data-path]');
    const del  = e.target.closest('[data-delete]');
    try {
      if (zip)  await this.#api.download(`/generator/generations/${zip.dataset.zip}/download`, 'documents.zip');
      if (file) await this.#api.download(
        `/generator/generations/${file.dataset.gen}/files/${file.dataset.path.split('/').map(encodeURIComponent).join('/')}`);
      if (del) {
        const okay = await showConfirm({ title: 'Delete this version?', message: 'Its files will be removed.',
                                         confirmLabel: 'Delete' });
        if (!okay) return;
        await this.#api.deleteGeneration(del.dataset.delete);
        this.#renderResults((await this.#api.getGenerations()) ?? []);
      }
    } catch (err) {
      this.#toast.show(err.message ?? 'Something went wrong.', 'error');
    }
  }
}
