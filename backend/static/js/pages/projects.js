/**
 * Projects page controller.
 *
 * Two-column layout:
 *   Left:  scrollable project list + "New" button
 *   Right: selected project detail — header, folder accordions, file uploads
 */

import { sanitize, getExtension, typeBadgeClass, formatBytes } from '../utils.js';
import { showConfirm } from '../confirm.js';

export class ProjectsPage {
  get pageId() { return 'page-projects'; }

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

  // ── State ─────────────────────────────────────────────────
  /** @type {import('../api.js').ProjectResponse[]} */ #projects    = [];
  /** @type {import('../api.js').ProjectResponse|null} */ #selected = null;
  /** @type {Record<string, boolean>} */               #folderOpen  = {};
  /** @type {Record<string, EventListener>} */         #handlers    = {};
  /** @type {string|null} */                           #uploadingIn = null;

  // ── Lifecycle ─────────────────────────────────────────────

  async enter() {
    this.#attachHandlers();
    await this.#loadProjects();
  }

  leave() {
    this.#detachHandlers();
  }

  // ── Data loading ─────────────────────────────────────────

  async #loadProjects() {
    try {
      this.#projects = await this.#api.getProjects();
    } catch {
      this.#toast.show('Could not load projects.', 'error');
      this.#projects = [];
    }
    this.#renderProjectList();

    if (this.#selected) {
      const still = this.#projects.find((p) => p.id === this.#selected.id);
      if (still) await this.#selectProject(still.id);
      else       this.#showEmpty();
    } else if (this.#projects.length) {
      await this.#selectProject(this.#projects[0].id);
    } else {
      this.#showEmpty();
    }
  }

  async #selectProject(id) {
    try {
      this.#selected = await this.#api.getProject(id);
    } catch {
      this.#toast.show('Could not load project.', 'error');
      return;
    }
    this.#renderProjectList();
    this.#renderProjectDetail();
  }

  // ── Left panel ────────────────────────────────────────────

  #renderProjectList() {
    const list = document.getElementById('proj-list');
    list.innerHTML = '';

    if (!this.#projects.length) {
      list.innerHTML = '<div class="proj-list-empty">No projects yet.<br/>Click <strong>New</strong> to create one.</div>';
      return;
    }

    this.#projects.forEach((p) => {
      const card = document.createElement('div');
      card.className  = `proj-card${this.#selected?.id === p.id ? ' active' : ''}`;
      card.setAttribute('role', 'listitem');
      card.innerHTML = `
        <div class="proj-card-name" title="${sanitize(p.name)}">${sanitize(p.name)}</div>
        <div class="proj-card-meta">${p.file_count} file${p.file_count !== 1 ? 's' : ''}</div>`;
      card.addEventListener('click', () => this.#selectProject(p.id));
      list.appendChild(card);
    });
  }

  #showEmpty() {
    this.#selected = null;
    document.getElementById('proj-empty').classList.remove('hidden');
    document.getElementById('proj-detail').classList.add('hidden');
  }

  // ── Right panel ───────────────────────────────────────────

  #renderProjectDetail() {
    const p = this.#selected;
    if (!p) return;

    document.getElementById('proj-empty').classList.add('hidden');
    document.getElementById('proj-detail').classList.remove('hidden');

    document.getElementById('proj-name').textContent = p.name;
    document.getElementById('proj-desc').textContent = p.description || 'No description';

    this.#renderFolders(p.folders ?? []);
  }

  #renderFolders(folders) {
    const container = document.getElementById('proj-folders');
    container.innerHTML = '';

    folders
      .slice()
      .sort((a, b) => a.sort_order - b.sort_order)
      .forEach((folder) => {
        if (!(folder.id in this.#folderOpen)) this.#folderOpen[folder.id] = false;
        container.appendChild(this.#buildFolderSection(folder));
      });
  }

  #buildFolderSection(folder) {
    const isOpen = this.#folderOpen[folder.id] ?? true;

    const section = document.createElement('div');
    section.className   = `pf-section${isOpen ? ' open' : ''}`;
    section.setAttribute('role', 'listitem');

    // Header
    const hdr = document.createElement('div');
    hdr.className = 'pf-hdr';
    hdr.innerHTML = `
      <svg class="pf-chevron" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span class="pf-name" title="${sanitize(folder.name)}">${sanitize(folder.name)}</span>
      <span class="pf-count">${folder.documents?.length ?? 0} file${(folder.documents?.length ?? 0) !== 1 ? 's' : ''}</span>
      <button class="pf-btn pf-rename" aria-label="Rename folder ${sanitize(folder.name)}" title="Rename folder">
        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <button class="pf-btn pf-delete" aria-label="Delete folder ${sanitize(folder.name)}" title="Delete folder">
        <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>`;

    // Body
    const body = document.createElement('div');
    body.className = 'pf-body';

    // File list
    const fileList = document.createElement('div');
    fileList.className = 'pf-files';
    (folder.documents ?? []).forEach((doc) => {
      fileList.appendChild(this.#buildFileChip(doc, folder));
    });
    if (!(folder.documents ?? []).length) {
      fileList.innerHTML = '<span class="pf-no-files">No files yet</span>';
    }

    // Upload area
    const uploadWrap = document.createElement('div');
    uploadWrap.className = 'pf-upload-wrap';

    const fileInput = document.createElement('input');
    fileInput.type     = 'file';
    fileInput.multiple = true;
    fileInput.accept   = '.pdf,.docx,.xlsx,.txt,.md';
    fileInput.style.display = 'none';
    fileInput.id = `fi-${folder.id}`;

    const uploadBtn = document.createElement('button');
    uploadBtn.className   = 'pf-upload-btn';
    uploadBtn.innerHTML   = `
      <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 16V8m0 0l-3 3m3-3l3 3" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M20 16.7A4 4 0 0017 9h-.9A7 7 0 104 15.9" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      Upload files`;
    uploadBtn.addEventListener('click', () => fileInput.click());

    const progressEl = document.createElement('span');
    progressEl.className = 'pf-progress hidden';

    uploadWrap.appendChild(fileInput);
    uploadWrap.appendChild(uploadBtn);
    uploadWrap.appendChild(progressEl);

    fileInput.addEventListener('change', async () => {
      const files = Array.from(fileInput.files);
      if (!files.length) return;
      fileInput.value = '';
      await this.#uploadFiles(files, folder.id, uploadBtn, progressEl);
    });

    body.appendChild(fileList);
    body.appendChild(uploadWrap);

    // Toggle on header click (but not on buttons)
    hdr.addEventListener('click', (e) => {
      if (e.target.closest('.pf-btn')) return;
      this.#folderOpen[folder.id] = !this.#folderOpen[folder.id];
      section.classList.toggle('open', this.#folderOpen[folder.id]);
    });

    // Rename
    hdr.querySelector('.pf-rename').addEventListener('click', (e) => {
      e.stopPropagation();
      this.#startFolderRename(folder, hdr.querySelector('.pf-name'));
    });

    // Delete
    hdr.querySelector('.pf-delete').addEventListener('click', (e) => {
      e.stopPropagation();
      this.#deleteFolder(folder);
    });

    section.appendChild(hdr);
    section.appendChild(body);
    return section;
  }

  #buildFileChip(doc, folder) {
    const ext  = getExtension(doc.filename).toUpperCase();
    const chip = document.createElement('div');
    chip.className = 'pf-chip';
    chip.innerHTML = `
      <span class="tb ${typeBadgeClass(doc.filename)}">${ext}</span>
      <span class="pf-chip-name" title="${sanitize(doc.filename)}">${sanitize(doc.filename)}</span>
      <span class="pf-chip-size">${formatBytes(doc.size_bytes)}</span>
      <button class="pf-chip-del" aria-label="Remove ${sanitize(doc.filename)}">×</button>`;

    chip.querySelector('.pf-chip-del').addEventListener('click', async () => {
      const ok = await showConfirm({
        title:        'Remove file?',
        message:      `"${doc.filename}" will be removed from the knowledge base.`,
        confirmLabel: 'Remove',
      });
      if (!ok) return;
      try {
        await this.#api.deleteDocument(doc.id);
        await this.#selectProject(this.#selected.id);
        await this.#loadProjectsQuiet();
      } catch {
        this.#toast.show('Could not remove file.', 'error');
      }
    });

    return chip;
  }

  async #uploadFiles(files, folderId, btn, progressEl) {
    if (this.#uploadingIn) return;
    this.#uploadingIn = folderId;
    btn.disabled = true;

    const total = files.length;
    let done    = 0;

    for (const file of files) {
      progressEl.classList.remove('hidden');
      progressEl.textContent = `Uploading ${file.name}…`;

      try {
        await this.#api.uploadFile(
          file,
          this.#selected.id,
          folderId,
          (pct) => { progressEl.textContent = `${file.name} — ${pct}%`; },
        );
        done++;
        progressEl.textContent = `${done}/${total} uploaded`;
      } catch (err) {
        this.#toast.show(`Failed to upload ${file.name}: ${err.message}`, 'error');
      }
    }

    progressEl.classList.add('hidden');
    btn.disabled      = false;
    this.#uploadingIn = null;

    if (done > 0) {
      this.#toast.show(`${done} file${done > 1 ? 's' : ''} uploaded.`, 'success');
      await this.#selectProject(this.#selected.id);
      await this.#loadProjectsQuiet();
    }
  }

  // ── Project actions ───────────────────────────────────────

  async #createProject() {
    const nameInput = document.createElement('input');
    nameInput.type        = 'text';
    nameInput.placeholder = 'Project name (e.g. Acme Corp)';
    nameInput.className   = 'proj-inline-input';
    nameInput.maxLength   = 80;

    const list = document.getElementById('proj-list');
    const wrap = document.createElement('div');
    wrap.className = 'proj-new-wrap';
    wrap.appendChild(nameInput);

    const actions = document.createElement('div');
    actions.className = 'proj-new-actions';
    actions.innerHTML = `
      <button class="proj-new-create">Create</button>
      <button class="proj-new-cancel">Cancel</button>`;
    wrap.appendChild(actions);
    list.prepend(wrap);
    nameInput.focus();

    const cleanup = () => wrap.remove();

    const submit = async () => {
      const name = nameInput.value.trim();
      if (!name) { nameInput.focus(); return; }
      cleanup();
      try {
        const project = await this.#api.createProject(name);
        this.#projects.unshift(project);
        await this.#selectProject(project.id);
        await this.#loadProjectsQuiet();
        this.#toast.show(`Project "${name}" created.`, 'success');
      } catch {
        this.#toast.show('Could not create project.', 'error');
      }
    };

    nameInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter')  submit();
      if (e.key === 'Escape') cleanup();
    });
    actions.querySelector('.proj-new-create').addEventListener('click', submit);
    actions.querySelector('.proj-new-cancel').addEventListener('click', cleanup);
  }

  async #editProject() {
    const p       = this.#selected;
    const nameEl  = document.getElementById('proj-name');
    const descEl  = document.getElementById('proj-desc');

    const origName = p.name;
    const origDesc = p.description;

    const nameIn = document.createElement('input');
    nameIn.type      = 'text';
    nameIn.className = 'proj-edit-input';
    nameIn.value     = origName;
    nameIn.maxLength = 80;

    const descIn = document.createElement('input');
    descIn.type      = 'text';
    descIn.className = 'proj-edit-input proj-edit-desc';
    descIn.value     = origDesc;
    descIn.placeholder = 'Description (optional)';
    descIn.maxLength = 200;

    nameEl.replaceWith(nameIn);
    descEl.replaceWith(descIn);

    const editBtn = document.getElementById('proj-edit-btn');
    const saveBtn = document.createElement('button');
    saveBtn.id        = 'proj-save-btn';
    saveBtn.className = 'proj-action-btn primary';
    saveBtn.textContent = 'Save';
    editBtn.replaceWith(saveBtn);

    nameIn.focus();
    nameIn.select();

    const restore = () => {
      const newNameEl = document.createElement('h2');
      newNameEl.id        = 'proj-name';
      newNameEl.className = 'proj-name';
      newNameEl.textContent = p.name;
      nameIn.replaceWith(newNameEl);

      const newDescEl = document.createElement('p');
      newDescEl.id        = 'proj-desc';
      newDescEl.className = 'proj-desc';
      newDescEl.textContent = p.description || 'No description';
      descIn.replaceWith(newDescEl);

      const origBtn = document.createElement('button');
      origBtn.id        = 'proj-edit-btn';
      origBtn.className = 'proj-action-btn';
      origBtn.innerHTML = `
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke-linecap="round" stroke-linejoin="round"/>
        </svg> Edit`;
      saveBtn.replaceWith(origBtn);
    };

    const save = async () => {
      const name = nameIn.value.trim() || origName;
      const desc = descIn.value.trim();
      try {
        const updated = await this.#api.updateProject(p.id, { name, description: desc });
        this.#selected = { ...this.#selected, name: updated.name, description: updated.description };
        this.#renderProjectDetail();
        await this.#loadProjectsQuiet();
      } catch {
        this.#toast.show('Could not update project.', 'error');
        restore();
      }
    };

    saveBtn.addEventListener('click', save);
    nameIn.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') restore(); });
    descIn.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') restore(); });
  }

  async #deleteProject() {
    const p  = this.#selected;
    const ok = await showConfirm({
      title:        `Delete "${p.name}"?`,
      message:      'All folders and uploaded files will be permanently removed from the knowledge base.',
      confirmLabel: 'Delete Project',
    });
    if (!ok) return;

    try {
      await this.#api.deleteProject(p.id);
      this.#selected  = null;
      this.#projects  = this.#projects.filter((x) => x.id !== p.id);
      this.#toast.show(`Project "${p.name}" deleted.`, 'success');
      this.#renderProjectList();

      if (this.#projects.length) {
        await this.#selectProject(this.#projects[0].id);
      } else {
        this.#showEmpty();
      }
    } catch {
      this.#toast.show('Could not delete project.', 'error');
    }
  }

  // ── Folder actions ────────────────────────────────────────

  #startFolderRename(folder, nameEl) {
    const orig  = folder.name;
    const input = document.createElement('input');
    input.type      = 'text';
    input.className = 'pf-rename-input';
    input.value     = orig;
    input.maxLength = 80;

    const commit = async () => {
      const next = input.value.trim() || orig;
      const span = document.createElement('span');
      span.className = 'pf-name';
      span.textContent = next;
      input.replaceWith(span);
      if (next === orig) return;
      try {
        await this.#api.updateFolder(this.#selected.id, folder.id, { name: next });
        await this.#selectProject(this.#selected.id);
      } catch {
        this.#toast.show('Could not rename folder.', 'error');
      }
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter')  { e.preventDefault(); input.blur(); }
      if (e.key === 'Escape') { input.value = orig; input.blur(); }
    });
    input.addEventListener('click',  (e) => e.stopPropagation());
    input.addEventListener('blur',   commit);

    nameEl.replaceWith(input);
    input.focus();
    input.select();
  }

  async #deleteFolder(folder) {
    const ok = await showConfirm({
      title:        `Delete "${folder.name}"?`,
      message:      'All files in this folder will be removed from the knowledge base.',
      confirmLabel: 'Delete Folder',
    });
    if (!ok) return;

    try {
      await this.#api.deleteFolder(this.#selected.id, folder.id);
      delete this.#folderOpen[folder.id];
      this.#toast.show(`Folder "${folder.name}" deleted.`, 'success');
      await this.#selectProject(this.#selected.id);
      await this.#loadProjectsQuiet();
    } catch {
      this.#toast.show('Could not delete folder.', 'error');
    }
  }

  async #addFolder() {
    const input = document.createElement('input');
    input.type        = 'text';
    input.placeholder = 'Folder name';
    input.className   = 'proj-inline-input';
    input.maxLength   = 80;

    const wrap = document.createElement('div');
    wrap.className = 'pf-new-folder-wrap';
    wrap.appendChild(input);

    const actions = document.createElement('div');
    actions.className = 'proj-new-actions';
    actions.innerHTML = '<button class="proj-new-create">Add</button><button class="proj-new-cancel">Cancel</button>';
    wrap.appendChild(actions);

    const container = document.getElementById('proj-folders');
    container.appendChild(wrap);
    input.focus();

    const cleanup = () => wrap.remove();

    const submit = async () => {
      const name = input.value.trim();
      if (!name) { input.focus(); return; }
      cleanup();
      try {
        const maxOrder = Math.max(-1, ...(this.#selected.folders ?? []).map((f) => f.sort_order));
        await this.#api.createFolder(this.#selected.id, name, maxOrder + 1);
        await this.#selectProject(this.#selected.id);
      } catch {
        this.#toast.show('Could not create folder.', 'error');
      }
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter')  submit();
      if (e.key === 'Escape') cleanup();
    });
    actions.querySelector('.proj-new-create').addEventListener('click', submit);
    actions.querySelector('.proj-new-cancel').addEventListener('click', cleanup);
  }

  // ── Helpers ───────────────────────────────────────────────

  /** Refresh project list counts in the background (no selected-project reload). */
  async #loadProjectsQuiet() {
    try {
      this.#projects = await this.#api.getProjects();
      this.#renderProjectList();
    } catch { /* non-fatal */ }
  }

  // ── Event listeners ───────────────────────────────────────

  #attachHandlers() {
    this.#handlers.newProj = () => this.#createProject();
    document.getElementById('new-proj-btn').addEventListener('click', this.#handlers.newProj);

    // proj-edit/del/add-folder are re-wired each time detail renders
    this.#handlers.delegatedDetail = (e) => {
      if (e.target.closest('#proj-edit-btn'))  this.#editProject();
      if (e.target.closest('#proj-del-btn'))   this.#deleteProject();
      if (e.target.closest('#add-folder-btn')) this.#addFolder();
    };
    document.getElementById('proj-detail').addEventListener('click', this.#handlers.delegatedDetail);
  }

  #detachHandlers() {
    document.getElementById('new-proj-btn')?.removeEventListener('click', this.#handlers.newProj);
    document.getElementById('proj-detail')?.removeEventListener('click', this.#handlers.delegatedDetail);
  }
}
