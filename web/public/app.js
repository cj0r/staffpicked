'use strict';

// ---------------------------------------------------------------- helpers

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icons = () => window.lucide && lucide.createIcons();

async function api(path, { method = 'GET', body } = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`api/${path}`, opts);
  if (res.status === 401 && path !== 'login') {
    window.location.href = 'login.html';
    throw new Error('Sign in first');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `HTTP ${res.status}`);
    err.data = data;   // problems and warnings, where the server sends them
    throw err;
  }
  return data;
}

// Toast notifications (same look as lftp-sync-manager)
let toastContainer = null;
function showToast(message, type = 'info') {
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    document.body.appendChild(toastContainer);
  }
  const kinds = { success: 'check-circle', error: 'alert-circle', warning: 'alert-triangle', info: 'info' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<i data-lucide="${kinds[type] || 'info'}"></i><span class="toast-message"></span><button type="button" class="toast-close" aria-label="Dismiss"><i data-lucide="x"></i></button>`;
  toast.querySelector('.toast-message').textContent = message;
  const dismiss = () => {
    toast.classList.remove('toast-visible');
    setTimeout(() => toast.remove(), 250);
  };
  toast.querySelector('.toast-close').addEventListener('click', dismiss);
  toastContainer.appendChild(toast);
  icons();
  requestAnimationFrame(() => toast.classList.add('toast-visible'));
  setTimeout(dismiss, type === 'error' ? 7000 : 4500);
}

// In-app confirm (native confirm() blocks the page)
function showAppConfirm(message, { danger = false, okText = 'OK', cancelText = 'Cancel', prompt = null, placeholder = '' } = {}) {
  return new Promise((resolve) => {
    const overlay = $('app-confirm-overlay');
    const ok = $('app-confirm-ok');
    const cancel = $('app-confirm-cancel');
    const input = $('app-confirm-input');
    $('app-confirm-message').textContent = message;
    $('app-confirm-input-wrapper').style.display = prompt === null ? 'none' : 'block';
    ok.textContent = okText;
    cancel.textContent = cancelText;
    input.placeholder = placeholder;
    ok.classList.toggle('btn-danger', danger);
    ok.classList.toggle('btn-primary', !danger);
    overlay.style.display = 'flex';
    if (prompt !== null) {
      input.value = prompt;
      input.focus();
      input.select();
    } else {
      ok.focus();
    }
    const done = (v) => {
      overlay.style.display = 'none';
      ok.removeEventListener('click', onOk);
      cancel.removeEventListener('click', onCancel);
      overlay.removeEventListener('keydown', onKey);
      resolve(v);
    };
    const onOk = () => done(prompt === null ? true : input.value);
    const onCancel = () => done(prompt === null ? false : null);
    const onKey = (e) => {
      if (e.key === 'Enter') { e.preventDefault(); onOk(); }
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onCancel(); }
    };
    ok.addEventListener('click', onOk);
    cancel.addEventListener('click', onCancel);
    overlay.addEventListener('keydown', onKey);
  });
}

function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return sameDay ? `today ${time}` : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${time}`;
}

function duration(a, b) {
  if (!a || !b) return '';
  const s = Math.max(0, Math.round((new Date(b) - new Date(a)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

// The server reports each step of slow work (an import, a scan, reading a list, a sync) as a
// 'progress' event; whoever shows that work puts a handler here for its task.
const progressHandlers = {};

// ---------------------------------------------------------------- dropdown menus

// Browsers draw a <select>'s open list themselves, and on Linux and Windows that's a flat
// grey menu nothing on the page can restyle. So with a mouse, opening any <select> shows
// this themed list instead. The <select> itself stays the field, holds the value and fires
// 'change', so nothing else on the page needs to know. Touch screens keep the phone's own
// picker, which fits a small screen better.
const selectMenu = (() => {
  if (!window.matchMedia('(pointer: fine)').matches) return null;
  const menu = document.createElement('div');
  menu.className = 'select-menu';
  menu.setAttribute('role', 'listbox');
  menu.hidden = true;
  document.body.appendChild(menu);
  let sel = null;
  let active = -1;
  let typed = '';
  let typedAt = 0;
  const items = () => [...menu.querySelectorAll('.select-option')];

  function highlight(n, scroll = true) {
    const all = items();
    if (!all.length) return;
    active = Math.max(0, Math.min(n, all.length - 1));
    all.forEach((el, i) => el.classList.toggle('active', i === active));
    sel.setAttribute('aria-activedescendant', all[active].id);
    if (scroll) all[active].scrollIntoView({ block: 'nearest' });
  }
  // the next option that isn't disabled, going by step from n
  function step(n, by) {
    const all = items();
    for (let i = n + by; i >= 0 && i < all.length; i += by) if (!all[i].classList.contains('disabled')) return i;
    return n;
  }
  function place() {
    const r = sel.getBoundingClientRect();
    const below = window.innerHeight - r.bottom - 8;
    const above = r.top - 8;
    const want = Math.min(menu.scrollHeight, 320);
    const up = below < Math.min(want, 200) && above > below;
    menu.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - Math.max(r.width, 180) - 8))}px`;
    menu.style.minWidth = `${r.width}px`;
    menu.style.maxHeight = `${Math.max(120, Math.min(320, up ? above : below))}px`;
    menu.style.top = up ? '' : `${r.bottom + 4}px`;
    menu.style.bottom = up ? `${window.innerHeight - r.top + 4}px` : '';
  }
  function open(target) {
    sel = target;
    menu.innerHTML = [...sel.options].map((o, i) => `
      <div class="select-option${o.disabled ? ' disabled' : ''}${i === sel.selectedIndex ? ' selected' : ''}" role="option" id="select-option-${i}"
        aria-selected="${i === sel.selectedIndex}" data-i="${i}">${esc(o.textContent)}</div>`).join('');
    menu.hidden = false;
    sel.setAttribute('aria-expanded', 'true');
    sel.classList.add('menu-open');
    place();
    highlight(Math.max(0, sel.selectedIndex));
  }
  function close() {
    if (!sel) return;
    menu.hidden = true;
    sel.removeAttribute('aria-expanded');
    sel.removeAttribute('aria-activedescendant');
    sel.classList.remove('menu-open');
    sel = null;
  }
  function pick(n) {
    const target = sel;
    const opt = target.options[n];
    close();
    if (!opt || opt.disabled) return;
    target.focus({ preventScroll: true });
    if (target.selectedIndex === n) return;
    target.selectedIndex = n;
    target.dispatchEvent(new Event('input', { bubbles: true }));
    target.dispatchEvent(new Event('change', { bubbles: true }));
  }
  const usable = (el) => el instanceof HTMLSelectElement && !el.multiple && !el.disabled && el.size <= 1;

  document.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    if (menu.contains(e.target)) { e.preventDefault(); return; }   // keep focus on the field
    const target = e.target.closest?.('select');
    if (target && usable(target)) {
      e.preventDefault();
      if (sel === target) { close(); return; }
      close();
      target.focus({ preventScroll: true });
      open(target);
      return;
    }
    close();
  }, true);
  menu.addEventListener('click', (e) => {
    const o = e.target.closest('.select-option');
    if (o && sel) pick(Number(o.dataset.i));
  });
  menu.addEventListener('mousemove', (e) => {
    const o = e.target.closest('.select-option');
    if (o && !o.classList.contains('disabled')) highlight(Number(o.dataset.i), false);
  });
  document.addEventListener('keydown', (e) => {
    if (!sel) {
      const target = e.target;
      const opens = e.key === 'Enter' || e.key === ' ' || e.key === 'F4' || (e.altKey && (e.key === 'ArrowDown' || e.key === 'ArrowUp'));
      if (usable(target) && opens) { e.preventDefault(); open(target); }
      return;
    }
    if (e.target !== sel) { close(); return; }
    const all = items();
    const keys = {
      ArrowDown: () => highlight(step(active, 1)),
      ArrowUp: () => highlight(step(active, -1)),
      Home: () => highlight(step(-1, 1)),
      End: () => highlight(step(all.length, -1)),
      PageDown: () => highlight(step(Math.min(active + 7, all.length), -1)),
      PageUp: () => highlight(step(Math.max(active - 7, -1), 1)),
      Enter: () => pick(active),
      ' ': () => pick(active),
      Escape: () => close(),
    };
    if (e.key === 'Tab') { close(); return; }
    if (keys[e.key] && !(e.key === ' ' && typed && Date.now() - typedAt < 800)) {
      e.preventDefault();
      e.stopPropagation();   // Escape closes the menu, not the drawer behind it
      keys[e.key]();
      return;
    }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {   // type to jump
      e.preventDefault();
      typed = Date.now() - typedAt < 800 ? typed + e.key.toLowerCase() : e.key.toLowerCase();
      typedAt = Date.now();
      const opts = [...sel.options];
      const match = (o) => !o.disabled && o.textContent.trim().toLowerCase().startsWith(typed);
      const from = typed.length === 1 ? active + 1 : active;   // one letter again moves on to the next
      let n = opts.findIndex((o, i) => i >= from && match(o));
      if (n < 0) n = opts.findIndex(match);
      if (n >= 0) highlight(n);
    }
  }, true);
  document.addEventListener('focusout', (e) => { if (sel && e.target === sel) setTimeout(() => { if (sel && document.activeElement !== sel) close(); }); });
  window.addEventListener('resize', close);
  document.addEventListener('scroll', (e) => { if (sel && !menu.contains(e.target)) close(); }, true);
  return { close };
})();

// ---------------------------------------------------------------- drawers

const backdrop = $('drawer-backdrop');
let openDrawerEl = null;

// Opening a drawer replaces the open one, unless that one has unsaved edits: then it stays.
function openDrawer(id) {
  if (openDrawerEl && openDrawerEl.id !== id && drawerDirty(openDrawerEl.id)) {
    showToast('Save or discard your changes here first.', 'warning');
    return;
  }
  hideDrawer();
  openDrawerEl = $(id);
  openDrawerEl.classList.add('open');
  backdrop.classList.add('open');
  document.body.classList.add('modal-open');
}

function hideDrawer() {
  if (!openDrawerEl) return;
  openDrawerEl.classList.remove('open');
  backdrop.classList.remove('open');
  document.body.classList.remove('modal-open');
  openDrawerEl = null;
}

// Drawers with unsaved edits ask before closing: Save, Discard or Keep Editing.
// Each registers {dirty, save, discard, what}; save resolves true once saved (builder.js adds its own).
const drawerGuards = {};
const drawerDirty = (id) => Boolean(drawerGuards[id]?.dirty());
let closing = false;

async function closeDrawer() {
  if (!openDrawerEl || closing) return;
  const id = openDrawerEl.id;
  const guard = drawerGuards[id];
  if (guard && guard.dirty()) {
    closing = true;
    try {
      const pick = await askUnsaved(guard.what ? guard.what() : 'You have changes that aren\'t saved.');
      if (pick === 'keep') return;
      if (pick === 'save' && !(await guard.save())) return;   // a failed save keeps the drawer open
      if (pick === 'discard') guard.discard?.();
    } finally {
      closing = false;
    }
    if (openDrawerEl?.id !== id) return;
  }
  hideDrawer();
}

function askUnsaved(message) {
  return new Promise((resolve) => {
    const overlay = $('unsaved-overlay');
    $('unsaved-message').textContent = `${message} Save them before closing?`;
    overlay.style.display = 'flex';
    $('unsaved-save').focus();
    const done = (v) => {
      overlay.style.display = 'none';
      overlay.removeEventListener('click', onClick);
      overlay.removeEventListener('keydown', onKey);
      resolve(v);
    };
    const onClick = (e) => {
      if (e.target === overlay) done('keep');
      else if (e.target.closest('#unsaved-save')) done('save');
      else if (e.target.closest('#unsaved-discard')) done('discard');
      else if (e.target.closest('#unsaved-keep')) done('keep');
    };
    const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done('keep'); } };
    overlay.addEventListener('click', onClick);
    overlay.addEventListener('keydown', onKey);
  });
}

const dialogOpen = () => [...document.querySelectorAll('.app-confirm-overlay')].some((o) => o.style.display !== 'none');

backdrop.addEventListener('click', closeDrawer);
document.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', closeDrawer));
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && openDrawerEl && !dialogOpen()) closeDrawer();
});

// ---------------------------------------------------------------- admin mode

// Admin mode shows the tools most people never need: Config Files, Artwork,
// Live Logs, Dry run and the delete buttons (marked .admin-only). Disabled until
// enabled in Settings; remembered per browser.
const ADMIN_KEY = 'staffpicked-admin-mode';
const adminMode = () => document.body.classList.contains('admin-mode');

function setAdminMode(on) {
  document.body.classList.toggle('admin-mode', on);
  $('admin-mode-toggle').checked = on;
  $('admin-mode-label').textContent = on ? 'Enabled: every tool is showing' : 'Disabled: admin tools are hidden';
}

setAdminMode((() => { try { return localStorage.getItem(ADMIN_KEY) === '1'; } catch { return false; } })());
$('admin-mode-toggle').addEventListener('change', (e) => {
  setAdminMode(e.target.checked);
  try { localStorage.setItem(ADMIN_KEY, e.target.checked ? '1' : '0'); } catch { /* storage blocked: this visit only */ }
  if (status) renderJobPanel();   // the Sync button's label follows Dry run
});

// ---------------------------------------------------------------- screen effects

// The worn-tape effects (tracking band, grain, scanlines, vignette, blinking PLAY). Enabled
// unless disabled in Settings; saved on the server, which marks the page before it draws.
function setEffects(on) {
  document.documentElement.classList.toggle('no-effects', !on);
  $('effects-toggle').checked = on;
  $('effects-label').textContent = on ? 'Enabled: the full worn-tape look' : 'Disabled: a calmer, cleaner screen';
}

setEffects(!document.documentElement.classList.contains('no-effects'));
$('effects-toggle').addEventListener('change', async (e) => {
  const on = e.target.checked;
  setEffects(on);
  try {
    await api('effects', { method: 'POST', body: { effects: on } });
  } catch (err) {
    setEffects(!on);
    showToast(`Couldn't save Screen Effects: ${err.message}`, 'error');
  }
});

// ---------------------------------------------------------------- state & dashboard

let status = null;
let listTab = null;
let logTab = null;
const logLines = {};

function jobBadge(job) {
  if (!job.installed) return ['missing', 'Not installed'];
  if (job.running) return ['syncing', job.run?.action === 'check' ? 'Checking' : 'Running'];
  if (!job.enabled) return ['off', 'Off'];
  const st = job.run?.status;
  if (st === 'failed') return ['failed', 'Failed'];
  if (st === 'aborted') return ['paused', 'Aborted'];
  return ['idle', 'Idle'];
}

function jobDetail(job) {
  if (!job.installed) return 'The StaffPicked generator is not installed next to the UI.';
  const r = job.run;
  if (job.running) return `${r.dry_run ? 'Dry run' : r.action === 'check' ? 'Checking config' : 'Syncing'} since ${fmtTime(r.started)}…`;
  if (!r) return job.enabled ? `Ready. ${job.description}.` : job.name === 'genres' ? 'Turned off in Settings (Genre artwork).' : 'Turned off by the current mode.';
  const what = r.action === 'check' ? 'Check' : r.action === 'remove' ? 'Remove' : r.dry_run ? 'Dry run' : 'Sync';
  const verdict = { ok: 'finished', failed: `failed (exit ${r.exit})`, aborted: 'was aborted' }[r.status] || r.status;
  const bad = Object.entries(r.servers || {}).filter(([, v]) => v !== 'ok').map(([n]) => n);
  return `${what}${r.server ? ` on ${r.server}` : ''} ${verdict} ${fmtTime(r.ended)}${r.started && r.ended ? ` in ${duration(r.started, r.ended)}` : ''}.`
    + (bad.length && Object.keys(r.servers).length > 1 ? ` Errors on ${joinNames(bad)}.` : '');
}

// The open shelf tab's sync controls: what the section is, its status, which list to sync,
// Sync, Abort and Dry run.
// Built once per tab, then updated in place so focus survives refreshes; the picked list and
// Dry run are kept per tab.
const jobPicks = {};   // job name -> {only, dry}
const SECTION_TEXT = {
  collections: 'Collections built from your MDBList and Trakt lists, each on the server during its season.',
  playlists: 'Playlists built from your ranked list files and MDBList or Trakt lists, in the order you set.',
  genres: 'Your own poster, thumb and backdrops on the server\'s genres.',
};

function renderJobPanel() {
  const panel = $('job-panel');
  const j = status.jobs.find((x) => x.name === listTab);
  const pick = (jobPicks[j.name] ||= { only: '', dry: false, server: '' });
  if (panel.dataset.job !== j.name) {
    panel.dataset.job = j.name;
    panel.innerHTML = `
      <div class="job-status">
        <span class="status-sub">${esc(SECTION_TEXT[j.name] || `${j.description}.`)}</span>
        <span class="pulse-badge idle" data-badge></span>
      </div>
      <div class="job-controls">
        ${j.supports_only ? `<select class="profile-select only-select" data-only aria-label="Which ${esc(j.label.toLowerCase())} to sync"></select>` : ''}
        <select class="profile-select server-select" data-server aria-label="Which server to sync" title="Which media server Sync and the remove buttons work on"></select>
        <button class="btn btn-primary" data-act="sync"><i data-lucide="play" class="btn-icon"></i><span data-sync-label>Sync</span></button>
        <button class="btn btn-danger" data-act="abort" title="Stop this run" hidden><i data-lucide="square" class="btn-icon"></i><span>Stop</span></button>
        <label class="check-label dry-run-toggle admin-only" title="Show every change the sync would make without touching the media server">
          <input type="checkbox" data-dry><span>Dry run</span>
        </label>
      </div>
      <div class="vhs-osd" data-osd role="status" aria-live="polite" hidden></div>`;
    panel.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', () => jobAction(j.name, b.dataset.act, panel)));
    const dry = panel.querySelector('[data-dry]');
    dry.checked = pick.dry;
    dry.addEventListener('change', () => { pick.dry = dry.checked; syncLabel(); });
    panel.querySelector('[data-only]')?.addEventListener('change', (e) => { pick.only = e.target.value; });
    panel.querySelector('[data-server]').addEventListener('change', (e) => { pick.server = e.target.value; });
    icons();
  }
  const syncLabel = () => { panel.querySelector('[data-sync-label]').textContent = pick.dry && adminMode() ? 'Dry Run' : 'Sync'; };
  syncLabel();
  const [cls, text] = jobBadge(j);
  const badge = panel.querySelector('[data-badge]');
  badge.className = `pulse-badge ${cls}`;
  badge.textContent = text;
  badge.title = jobDetail(j);   // what it's doing, or how the last run went
  panel.classList.toggle('job-off', !j.enabled);
  const busy = j.running || !j.installed;
  // one button at a time: Sync while idle, Stop while it runs
  panel.querySelectorAll('[data-act]').forEach((b) => {
    const stop = b.dataset.act === 'abort';
    b.hidden = stop ? !j.running : j.running;
    b.disabled = stop ? !j.running : busy;
  });
  renderOsd(panel, j);
  panel.querySelector('[data-dry]').disabled = busy;
  const srv = panel.querySelector('[data-server]');
  const names = serverNames();
  if (!names.includes(pick.server)) pick.server = '';
  srv.style.display = names.length > 1 ? '' : 'none';
  srv.innerHTML = `<option value="">All servers (${names.length})</option>` + names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
  srv.value = pick.server;
  srv.disabled = busy;
  const only = panel.querySelector('[data-only]');
  if (only) {
    const names = j.items.map((i) => i.name);
    only.innerHTML = `<option value="">All ${esc(j.label.toLowerCase())} (${names.length})</option>` +
      names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
    if (!names.includes(pick.only)) pick.only = '';
    only.value = pick.only;
    only.disabled = busy;
  }
}

// While a job runs, its tab shows a VCR's on-screen display: PLAY (or STOP once asked),
// a tape counter of which list it's on, and that list's name.
const pad2 = (n) => String(n).padStart(2, '0');
function renderOsd(panel, j) {
  const osd = panel.querySelector('[data-osd]');
  if (!j.running) { osd.hidden = true; osd.innerHTML = ''; return; }
  const r = j.run || {};
  const p = r.progress || {};
  const mode = r.action === 'check' ? 'CHECK' : r.action === 'remove' ? 'EJECT' : r.dry_run ? 'PREVIEW' : 'PLAY';
  const counter = p.total ? `${pad2(Math.min(p.done || 0, p.total))}/${pad2(p.total)}` : (p.done ? pad2(p.done) : '--');
  osd.hidden = false;
  osd.innerHTML = `<span class="osd-mode"><span class="osd-play" aria-hidden="true">${mode === 'EJECT' ? '⏏' : '▶'}</span>${mode}</span>
    <span class="osd-counter" title="Lists done of this run's lists">${counter}</span>
    <span class="osd-title">${esc(p.current || (r.action === 'check' ? 'Checking the config' : 'Rewinding…'))}</span>`;
}

progressHandlers.sync = (d) => {
  const j = status?.jobs.find((x) => x.name === d.job);
  if (!j?.run) return;
  j.run.progress = { done: d.done, total: d.total, current: d.current };
  const panel = $('job-panel');
  if (panel.dataset.job === d.job) renderOsd(panel, j);
};

async function jobAction(name, act, panel) {
  if (act === 'abort') {
    await api(`jobs/${name}/abort`, { method: 'POST', body: {} }).catch((e) => showToast(e.message, 'error'));
    return;
  }
  const only = panel.querySelector('[data-only]')?.value || '';
  const server = panel.querySelector('[data-server]')?.value || '';
  const dry = adminMode() && panel.querySelector('[data-dry]').checked;   // a hidden box never dry-runs
  const job = status.jobs.find((j) => j.name === name);
  if (!dry && !job.enabled) {
    const yes = await showAppConfirm(`${job.label} are turned off ${name === 'genres' ? 'in Settings' : 'by the current mode'}. Sync them anyway?`, { okText: 'Sync' });
    if (!yes) return;
  }
  try {
    await api(`jobs/${name}/run`, { method: 'POST', body: { action: 'sync', dry_run: dry, only, server } });
    if (dry) previewWatch.add(name);   // opens what it would change when it's done
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// Deleting from the media server: one list from its row, or all of a job's from Settings.
// Both go through review() so the person sees exactly what goes. Config files stay.
// target = one server's name; '' = every server each list goes to.
async function removeFromServer(jobName, name = '', target = '') {
  const job = status.jobs.find((j) => j.name === jobName);
  const kind = job.label.toLowerCase();
  const names = name ? [name] : job.items.map((i) => i.name);
  if (!names.length) { showToast(`No ${kind} are configured.`, 'info'); return; }
  const only = name ? job.items.find((i) => i.name === name)?.servers : [];
  const server = target || serverName(only);
  const genres = jobName === 'genres';
  const r = await review(genres ? {
    title: name ? `Take StaffPicked's artwork off "${name}" on ${server}?` : `Take StaffPicked's artwork off every genre on ${server}?`,
    intro: `The poster, thumb and backdrops StaffPicked set will be removed from ${name ? 'this genre' : 'these genres'} now:`,
    items: names,
    foot: `The genres themselves stay, as does artwork set some other way. Your config and image files are not changed, and the next sync puts the artwork back.`,
    okText: 'Remove',
  } : {
    title: name ? `Remove "${name}" from ${server}?` : `Remove all ${kind} from ${server}?`,
    intro: name ? `This ${KIND[jobName]} will be deleted from ${server} now:` : `These ${kind} will be deleted from ${server} now:`,
    items: names,
    foot: `Your config and list files are not changed, and the next sync puts back any that are in season.`,
    okText: 'Remove',
  });
  if (!r.ok) return;
  try {
    await api(`jobs/${jobName}/run`, { method: 'POST', body: { action: 'remove', only: name, server: target } });
    showToast(genres ? `Taking StaffPicked's artwork off ${name ? `"${name}"` : 'every genre'}.`
      : `Removing ${name ? `"${name}"` : `all ${kind}`} from ${server}.`, 'info');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function renderMetrics() {
  const all = status.jobs.filter((j) => j.enabled && j.name !== 'genres').flatMap((j) => j.items);   // genres have no season
  const active = all.filter((i) => i.active === true).length;
  $('stat-active').textContent = `${active} of ${all.length}`;
  $('stat-active-sub').textContent = all.length ? 'lists inside their active window · click for the calendar' : 'No lists configured yet';
  if (status.next_run) {
    // shown in the time zone the schedule runs in, which may not be this browser's
    const d = new Date(status.next_run);
    let zone = status.time_zone || 'UTC';
    try {
      new Intl.DateTimeFormat([], { timeZone: zone });
    } catch {
      zone = undefined;
    }
    const day = (x) => x.toLocaleDateString('en-CA', { timeZone: zone });
    const short = new Intl.DateTimeFormat([], { timeZone: zone, timeZoneName: 'short' })
      .formatToParts(d).find((p) => p.type === 'timeZoneName')?.value || '';
    $('stat-next').innerHTML = `${esc(d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: zone }))}<span class="stat-zone">${esc(short)}</span>`;
    $('stat-next').title = status.time_zone || '';
    const tomorrow = new Date(Date.now() + 86400000);
    const when = day(d) === day(new Date()) ? 'Today' : day(d) === day(tomorrow) ? 'Tomorrow'
      : d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', timeZone: zone });
    $('stat-next-sub').textContent = `${when}, ${status.mode === 'both' ? 'playlists + collections' : status.mode}. ${status.schedule ? `${status.schedule}, ` : ''}${(status.time_zone || 'UTC').replace(/_/g, ' ')} time.`;
    if (status.setup?.needed) $('stat-next-sub').textContent = 'Waiting for a media server: nothing syncs until one is set up.';
  }
}

function renderTabs(el, current, onPick, { dots = false } = {}) {
  el.innerHTML = status.jobs.map((j) => {
    // a running or failed job shows on its tab, so it's seen from the other tabs too
    const [cls, text] = jobBadge(j);
    const dot = dots && ['syncing', 'failed', 'paused'].includes(cls) ? `<span class="tab-dot ${cls}" title="${esc(text)}"></span>` : '';
    return `
    <button class="log-tab ${j.name === current ? 'active' : ''}" data-job="${j.name}">
      <i data-lucide="${{ playlists: 'list-ordered', genres: 'tags' }[j.name] || 'library'}" class="tab-icon"></i>
      <span>${esc(j.label)}</span>${dot}
    </button>`;
  }).join('');
  el.querySelectorAll('.log-tab').forEach((b) => b.addEventListener('click', () => onPick(b.dataset.job)));
  icons();
}

// On the Shelves order: all-year lists first by name, then seasonal ones by start date
// (January 1 first; a window that wraps the year counts from its start), the one that ends
// first leading on a shared start. Windows that can't be read go last. Each keeps its config index.
function windowKey(window) {
  const m = String(window || '').trim().match(/^(?:\d{4}-)?(\d{2})-(\d{2})\s+to\s+(?:\d{4}-)?(\d{2})-(\d{2})$/);
  if (!m) return null;
  const start = Number(m[1]) * 100 + Number(m[2]);
  let end = Number(m[3]) * 100 + Number(m[4]);
  if (end < start) end += 1200;   // wraps the new year: it ends after it starts
  return [start, end];
}

function shelfOrder(items) {
  const rank = (i) => {
    if (!i.window) return [0, 0, 0];
    const k = windowKey(i.window);
    return k ? [1, ...k] : [2, 0, 0];
  };
  return items.map((i, n) => [i, n, rank(i)]).sort((a, b) => {
    for (let x = 0; x < 3; x += 1) if (a[2][x] !== b[2][x]) return a[2][x] - b[2][x];
    return a[0].name.localeCompare(b[0].name, undefined, { sensitivity: 'base', numeric: true });
  });
}

// " · Jellyfin only" for a list limited to some servers
const onlyOn = (i) => {
  if (!i.servers?.length) return '';
  const known = serverNames();   // as the server is named in Settings, whatever the config's capitals
  return ` · ${esc(joinNames(i.servers.map((n) => known.find((k) => k.toLowerCase() === n.toLowerCase()) || n)))} only`;
};

// How each shelf shows: rows (the default) or tape covers. Remembered per browser.
const SHELF_VIEW_KEY = 'staffpicked-shelf-view';
let shelfView = (() => { try { return localStorage.getItem(SHELF_VIEW_KEY) === 'covers' ? 'covers' : 'rows'; } catch { return 'rows'; } })();

function setShelfView(v) {
  shelfView = v;
  try { localStorage.setItem(SHELF_VIEW_KEY, v); } catch { /* storage blocked: this visit only */ }
  document.querySelectorAll('.view-toggle [data-view]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.view === v)));
  if (status) renderItems();
}
document.querySelectorAll('.view-toggle [data-view]').forEach((b) => b.addEventListener('click', () => setShelfView(b.dataset.view)));
setShelfView(shelfView);

// What the last sync found for a list: when, how much of it the server has, and any problem.
function lastSync(i, genre = false) {
  const l = i.last;
  if (!l) return { text: 'Not synced yet', warn: '' };
  const parts = [l.off_season ? `Out of season · checked ${fmtTime(l.at)}` : `Synced ${fmtTime(l.at)}`];
  if (!genre && !l.off_season && l.listed != null) parts.push(`${l.in_library} of ${l.listed} in library`);
  const warn = l.errors ? (l.error || 'The last sync had a problem with this list. Open Recent Runs for its log.') : (l.warning || '');
  return { text: parts.join(' · '), warn, bad: Boolean(l.errors) };
}


const warnIcon = (w) => (w.warn ? `<span class="item-warn ${w.bad ? 'bad' : ''}" title="${esc(w.warn)}" aria-label="${esc(w.warn)}"><i data-lucide="alert-triangle"></i></span>` : '');

function seasonBadge(i) {
  if (i.kind === 'genre') return ['', ''];
  if (i.active === null) return ['bad', 'Bad window'];
  if (!i.window) return ['year', 'Year round'];
  return i.active ? ['on', 'In season'] : ['', 'Out of season'];
}

// One list as a rental tape: its poster as the cover, its name on the spine, and its
// season as the sticker on the box.
function tapeCover(i, n, job) {
  const [cls, label] = seasonBadge(i);
  const w = lastSync(i, job === 'genres');
  const cover = i.poster
    ? `<img src="api/images/file?name=${encodeURIComponent(i.poster)}" alt="" loading="lazy">`
    : `<div class="tape-blank"><i data-lucide="${job === 'genres' ? 'tags' : 'film'}"></i><span>${esc(i.name)}</span></div>`;
  return `<div class="tape" data-open="${n}" role="button" tabindex="0" title="${esc(job === 'genres' ? `Show the artwork for ${i.name}` : `Show the films on ${i.name}`)}">
    <div class="tape-box">
      <div class="tape-spine" aria-hidden="true"><span>${esc(i.name)}</span></div>
      <div class="tape-cover">${cover}</div>
      ${label ? `<span class="tape-sticker ${cls}">${label}</span>` : ''}
      ${warnIcon(w)}
    </div>
    <div class="tape-label">
      <span class="tape-name">${esc(i.name)}</span>
      <span class="tape-meta">${esc(w.text)}</span>
    </div>
  </div>`;
}

function renderItems() {
  if (!listTab) listTab = status.jobs[0].name;
  renderTabs($('list-tabs'), listTab, (j) => { listTab = j; renderItems(); }, { dots: true });
  updateTabFade();
  renderJobPanel();
  const job = status.jobs.find((j) => j.name === listTab);
  const el = $('item-list');
  const genres = listTab === 'genres';
  const covers = shelfView === 'covers' && job.items.length > 0;
  el.classList.toggle('tape-shelf', covers);
  if (!job.items.length) {
    el.innerHTML = genres
      ? `<div class="empty-state"><i data-lucide="tags"></i><span>No genre artwork on this shelf yet. Give one of ${serverName()}'s genres your own poster, thumb or backdrops.</span>
      <button class="btn btn-secondary btn-xs" data-new><i data-lucide="plus"></i><span>Add one</span></button></div>`
      : `<div class="empty-state"><i data-lucide="cassette-tape"></i><span>No tapes on this shelf yet. Build your first ${esc(KIND[listTab] || job.label.toLowerCase())}.</span>
      <button class="btn btn-secondary btn-xs" data-new><i data-lucide="plus"></i><span>Build one</span></button></div>`;
  } else if (covers) {
    const order = genres
      ? [...job.items.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name, undefined, { sensitivity: 'base' })).map(([n, i]) => [i, n])
      : shelfOrder(job.items);
    el.innerHTML = order.map(([i, n]) => tapeCover(i, n, listTab)).join('');
  } else if (genres) {
    el.innerHTML = [...job.items.entries()].sort((a, b) => a[1].name.localeCompare(b[1].name, undefined, { sensitivity: 'base' })).map(([n, i]) => {
      const w = lastSync(i, true);
      return `
      <div class="item-row" data-open="${n}" role="button" tabindex="0" title="Show the artwork for ${esc(i.name)}">
        <div class="item-main">
          <span class="item-name">${esc(i.name)}</span>
          <span class="item-meta">${esc(i.detail)}${onlyOn(i)}</span>
          <span class="item-last">${esc(w.text)}</span>
        </div>
        ${warnIcon(w)}
        <button class="btn btn-icon-only" data-entry="${n}" title="Edit ${esc(i.name)}"><i data-lucide="pencil"></i></button>
        <button class="btn btn-icon-only btn-danger-light admin-only" data-remove="${esc(i.name)}" title="Take StaffPicked's artwork off ${esc(i.name)} on the media server" ${job.running || !job.installed ? 'disabled' : ''}><i data-lucide="trash-2"></i></button>
      </div>`;
    }).join('');
  } else {
    el.innerHTML = shelfOrder(job.items).map(([i, n]) => {
      const [cls, label] = seasonBadge(i);
      const w = lastSync(i);
      return `<div class="item-row" data-open="${n}" role="button" tabindex="0" title="Show the films on ${esc(i.name)}">
        <div class="item-main">
          <span class="item-name">${esc(i.name)}</span>
          <span class="item-meta">${esc(i.detail)}${i.window ? ` · ${esc(i.window)}` : ''}${onlyOn(i)}</span>
          <span class="item-last">${esc(w.text)}</span>
        </div>
        ${warnIcon(w)}
        <span class="season-badge ${cls}">${label}</span>
        ${/^(collections|playlists|watchlists)\/.+\.md$/.test(i.file) ? `<button class="btn btn-icon-only" data-films="${esc(i.file)}" title="Edit the films in ${esc(i.file)}"><i data-lucide="list-ordered"></i></button>` : ''}
        <button class="btn btn-icon-only" data-entry="${n}" title="Edit ${esc(i.name)}"><i data-lucide="pencil"></i></button>
        <button class="btn btn-icon-only btn-danger-light admin-only" data-remove="${esc(i.name)}" title="Remove ${esc(i.name)} from the media server" ${job.running || !job.installed ? 'disabled' : ''}><i data-lucide="trash-2"></i></button>
      </div>`;
    }).join('');
  }
  el.querySelectorAll('[data-entry]').forEach((b) => b.addEventListener('click', () => openEntry(listTab, Number(b.dataset.entry))));
  el.querySelectorAll('[data-films]').forEach((b) => b.addEventListener('click', () => openWatchlist(b.dataset.films)));
  el.querySelectorAll('[data-new]').forEach((b) => b.addEventListener('click', () => openEntry(listTab, null)));
  el.querySelectorAll('[data-remove]').forEach((b) => b.addEventListener('click', () => removeFromServer(listTab, b.dataset.remove, jobPicks[listTab]?.server || '')));
  // The whole row (or tape) opens the list; its own buttons keep their own actions.
  el.querySelectorAll('[data-open]').forEach((row) => {
    const open = () => openList(listTab, Number(row.dataset.open));
    row.addEventListener('click', (e) => { if (!e.target.closest('button, a')) open(); });
    row.addEventListener('keydown', (e) => {
      if (e.target === row && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); open(); }
    });
  });
  filterShelf();
  icons();
}

// The filters above the shelf: a name search, one list picked by name, and a season chip.
// They live here rather than in the page, so the shelf and the search box always agree:
// if the browser empties the box on its own (some do when a tab comes back from the
// background), the box is filled back in instead of the lists staying filtered by
// text that is no longer shown.
// seasons: the chips picked; a list shows when it matches any of them (none picked = All).
// The shelf opens on Active: what's on the server now.
const shelfFilter = { q: '', seasons: new Set(['active']), pick: {} };   // pick: list name per tab
const SEASONS = [['active', 'Active'], ['inactive', 'Inactive'], ['on', 'In season'], ['off', 'Out of season'], ['year', 'Year round']];
// Active = on the server now (in season or year round); Inactive = everything else.
const inSeason = (i, k) => {
  if (k === 'active') return i.active === true;
  if (k === 'inactive') return i.active !== true;
  return seasonOf(i) === k;
};

function seasonOf(i) {
  if (i.kind === 'genre') return '';
  if (i.active === null) return 'bad';
  if (!i.window) return 'year';
  return i.active ? 'on' : 'off';
}

// A click picks just that chip. Ctrl+click (Cmd+click on a Mac), or a long press on a
// touch screen, adds or drops a chip from what is already picked, by these rules.
// Which chips can be on together. Active holds In season and Year round, Inactive holds
// Out of season, so a chip and the group it sits in never show together: picking the
// group drops its chips, and picking a chip narrows its group down to that chip.
// In season plus Year round is Active, and picks that cover every list on the shelf
// (Active and Inactive, say) are just All.
const SEASON_GROUPS = { active: ['on', 'year'], inactive: ['off'] };
function pickSeason(k, items) {
  const picks = shelfFilter.seasons;
  if (k === 'all') { picks.clear(); return; }
  if (picks.delete(k)) return;
  if (SEASON_GROUPS[k]) SEASON_GROUPS[k].forEach((c) => picks.delete(c));
  for (const [group, inside] of Object.entries(SEASON_GROUPS)) {
    if (inside.includes(k)) picks.delete(group);
  }
  picks.add(k);
  if (picks.has('on') && picks.has('year')) { picks.delete('on'); picks.delete('year'); picks.add('active'); }
  if (items.length && items.every((i) => [...picks].some((c) => inSeason(i, c)))) picks.clear();
}

function filterShelf() {
  const job = status.jobs.find((j) => j.name === listTab);
  const items = job?.items || [];
  const seasonal = items.some((i) => seasonOf(i));   // genres have no season
  const filtersOn = items.length >= 2;   // one list needs no filters, and none apply to it
  $('shelf-filters').hidden = !filtersOn;

  const box = $('shelf-search');
  if (box.value !== shelfFilter.q) box.value = shelfFilter.q;
  $('shelf-search-clear').hidden = !shelfFilter.q;
  const q = filtersOn ? shelfFilter.q.trim().toLowerCase() : '';

  // One list: the menu holds this tab's lists in shelf order.
  const names = (listTab === 'genres'
    ? [...items].sort((x, y) => x.name.localeCompare(y.name, undefined, { sensitivity: 'base' }))
    : shelfOrder(items).map(([i]) => i)).map((i) => i.name);
  let pick = filtersOn ? shelfFilter.pick[listTab] || '' : '';
  if (pick && !names.includes(pick)) pick = shelfFilter.pick[listTab] = '';   // renamed or removed
  const sel = $('shelf-pick');
  sel.innerHTML = `<option value="">All ${esc(job ? job.label.toLowerCase() : 'lists')} (${names.length})</option>` +
    names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
  sel.value = pick;
  sel.classList.toggle('active', Boolean(pick));

  // Season chips, each with how many lists it would show.
  const seasons = seasonal && filtersOn ? shelfFilter.seasons : new Set();
  const chips = $('shelf-chips');
  chips.hidden = !seasonal;
  const chip = (k, label, n, pressed) =>
    `<button type="button" class="shelf-chip ${k}" data-season="${k}" aria-pressed="${pressed}" title="${k === 'all' ? 'Show every list' : `Show ${label.toLowerCase()} lists. Ctrl+click or long-press to pick more than one.`}" ${n || pressed ? '' : 'disabled'}>${label}<span class="shelf-chip-count">${n}</span></button>`;
  chips.innerHTML = seasonal ? chip('all', 'All', items.length, !seasons.size) +
    SEASONS.map(([k, label]) => chip(k, label, items.filter((i) => inSeason(i, k)).length, seasons.has(k))).join('') : '';

  let shown = 0;
  $('item-list').querySelectorAll('[data-open]').forEach((row) => {
    const i = items[Number(row.dataset.open)];
    const hit = Boolean(i)
      && (!q || i.name.toLowerCase().includes(q))
      && (!pick || i.name === pick)
      && (!seasons.size || [...seasons].some((k) => inSeason(i, k)));
    row.hidden = !hit;
    if (hit) shown += 1;
  });

  const filtered = q || pick || seasons.size;
  const none = $('shelf-no-match');
  none.hidden = !filtered || shown > 0 || !items.length;
  none.innerHTML = `Nothing on this shelf matches these filters. <button type="button" class="btn btn-secondary btn-xs" id="shelf-reset"><i data-lucide="filter-x"></i><span>Show all</span></button>`;
  $('shelf-reset').addEventListener('click', () => {
    shelfFilter.q = '';
    shelfFilter.seasons.clear();
    shelfFilter.pick[listTab] = '';
    filterShelf();
  });
  icons();
}
// Chip clicks, handled on the strip since filterShelf redraws the chips.
function chipClick(k, multi) {
  const items = status.jobs.find((j) => j.name === listTab)?.items || [];
  if (multi) pickSeason(k, items);
  else {
    shelfFilter.seasons.clear();
    if (k !== 'all') shelfFilter.seasons.add(k);
  }
  filterShelf();
}
let chipPress = null;   // a long press in progress: { k, timer, done }
$('shelf-chips').addEventListener('click', (e) => {
  const b = e.target.closest('[data-season]');
  if (!b || b.disabled) return;
  if (chipPress?.done) { chipPress = null; return; }   // the long press already picked it
  chipClick(b.dataset.season, e.ctrlKey || e.metaKey);
});
$('shelf-chips').addEventListener('pointerdown', (e) => {
  clearTimeout(chipPress?.timer);
  chipPress = null;
  const b = e.target.closest('[data-season]');
  if (!b || b.disabled || e.pointerType === 'mouse') return;
  const press = { k: b.dataset.season, done: false };
  press.timer = setTimeout(() => {
    press.done = true;
    navigator.vibrate?.(15);
    chipClick(press.k, true);
    setTimeout(() => { if (chipPress === press) chipPress = null; }, 800);   // in case no click follows
  }, 500);
  chipPress = press;
});
['pointerup', 'pointercancel', 'pointerleave'].forEach((t) => $('shelf-chips').addEventListener(t, () => {
  if (chipPress && !chipPress.done) { clearTimeout(chipPress.timer); chipPress = null; }
}));
$('shelf-chips').addEventListener('contextmenu', (e) => { if (e.target.closest('[data-season]')) e.preventDefault(); });
$('shelf-search').addEventListener('input', (e) => { shelfFilter.q = e.target.value; filterShelf(); });
$('shelf-search').addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && shelfFilter.q) { e.preventDefault(); shelfFilter.q = ''; filterShelf(); }
});
$('shelf-search-clear').addEventListener('click', () => { shelfFilter.q = ''; filterShelf(); $('shelf-search').focus(); });
$('shelf-pick').addEventListener('change', (e) => { shelfFilter.pick[listTab] = e.target.value; filterShelf(); });
// A page coming back from the browser's cache, or a tab coming back into view, gets the
// box and the shelf put back in step.
window.addEventListener('pageshow', () => { if (status) filterShelf(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && status) filterShelf(); });

// On a narrow screen the shelf tabs scroll sideways; a fade on the side with more tabs says so.
function updateTabFade() {
  const tabs = $('list-tabs');
  const strip = tabs.parentElement;
  strip.classList.toggle('more-right', tabs.scrollLeft + tabs.clientWidth < tabs.scrollWidth - 2);
  strip.classList.toggle('more-left', tabs.scrollLeft > 2);
}
$('list-tabs').addEventListener('scroll', updateTabFade, { passive: true });
window.addEventListener('resize', updateTabFade);

// ---------------------------------------------------------------- progress of slow work

// (progressHandlers, near the top, takes the server's 'progress' events for each task)

// Shows a spinner, the step being worked on, and a bar in el, updating it in place so the
// spinner keeps turning. d is {done, total}; without a total the bar just sweeps.
function setProgress(el, step, d = null) {
  let box = el.querySelector(':scope > .progress-box');
  if (!box) {
    el.innerHTML = `<div class="progress-box" role="status" aria-live="polite">
      <div class="progress-head"><i data-lucide="loader-circle" class="spin"></i><span class="progress-step"></span><span class="progress-count"></span></div>
      <div class="progress-bar"><span></span></div>
    </div>`;
    icons();
    box = el.querySelector('.progress-box');
  }
  if (step) box.querySelector('.progress-step').textContent = step;
  const total = d?.total || 0;
  const done = Math.min(d?.done || 0, total);
  // while a step is underway it counts as the current one: "3 of 25"
  const at = step && done < total ? done + 1 : done;
  box.querySelector('.progress-count').textContent = total > 1 ? `${at} of ${total}` : '';
  const bar = box.querySelector('.progress-bar');
  bar.classList.toggle('sweep', !total);
  bar.firstElementChild.style.width = total ? `${Math.round((done / total) * 100)}%` : '';
}

// ---------------------------------------------------------------- one list's films

let listView = null;   // {job, index, name}

async function openList(job, index) {
  const item = status.jobs.find((j) => j.name === job).items[index];
  listView = { job, index, name: item.name };
  const genre = job === 'genres';   // only artwork: no films or sources
  $('list-title').textContent = item.name;
  $('list-feeds').style.display = genre ? 'none' : '';
  $('btn-list-remove').title = genre ? 'Take StaffPicked\'s artwork off it on the media server' : 'Remove from the media server';
  $('list-details').innerHTML = '<div><dt>Films</dt><dd>Reading the list…</dd></div>';
  ['list-poster', 'list-feeds', 'list-art', 'list-notes', 'list-library'].forEach((id) => { $(id).innerHTML = ''; });
  $('list-items').innerHTML = '';
  $('btn-list-export').hidden = true;
  // a sync held back by the removal limit: say so, and offer to let it through
  $('list-held').hidden = !item.last?.held;
  setProgress($('list-items'), genre ? 'Reading the artwork…' : 'Reading the list…');
  icons();
  openDrawer('list-drawer');
  progressHandlers.list = (d) => {
    if (listView?.job === d.job && listView.index === d.index && $('list-items').querySelector('.progress-box')) {
      setProgress($('list-items'), d.step, d);
    }
  };
  let r;
  try {
    r = await api(`builder/${job}/${index}/items`);
  } catch (e) {
    r = { items: [], feeds: [], artwork: [], details: [], problems: e.data?.problems || [e.message] };
  }
  if (listView?.job !== job || listView.index !== index) return;   // another list was opened meanwhile
  const films = r.items.filter((i) => !i.duplicate);
  const unread = !films.length && (r.problems || []).length > 0;   // the list couldn't be read at all
  $('list-details').innerHTML = (r.details || []).map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(k === 'Films' && unread ? 'Not read' : v)}</dd></div>`).join('');
  renderListFeeds(r.feeds || []);
  renderListArt(r.artwork || []);
  showNotes($('list-notes'), r.problems || []);
  if (!genre) renderListLibrary(r.library || [], films);
  // MDBList and Trakt lists can be frozen into a list file of your own
  listView.linked = (r.sources || []).filter((x) => !/^(collections|playlists|watchlists)\/[^/]+\.md$/.test(x.trim()));
  $('btn-list-export').hidden = genre || !listView.linked.length || !films.some((f) => f.imdb);
  const mark = (f) => {
    if (f.in_library === true) return '<span class="film-mark have" title="On the server"><i data-lucide="circle-check"></i></span>';
    if (f.in_library === false) return '<span class="film-mark missing" title="Not in your library">Missing</span>';
    return '';
  };
  $('list-items').innerHTML = genre ? '' : films.length ? films.map((f, n) => `
    <div class="film-row list-film${f.in_library === false ? ' is-missing' : ''}"${f.in_library === false && f.imdb ? ` data-imdb="${esc(f.imdb)}"` : ''}>
      <span class="film-num">${n + 1}</span>
      <span class="list-film-title">${esc(f.title)}${f.year ? ` <span class="list-film-year">(${esc(f.year)})</span>` : ''}${f.notes ? ` <span class="list-film-notes">${esc(f.notes)}</span>` : ''}</span>
      ${mark(f)}
      ${f.in_library === false && canRequest(f) ? `<button type="button" class="btn btn-secondary btn-xs film-request" data-request-film="${esc(f.imdb)}"
        data-show="${f.show ? 1 : 0}" data-name="${esc(f.year ? `${f.title} (${f.year})` : f.title)}"
        title="Request this ${f.show ? 'show' : 'film'} from ${requestService(f.show)}"><i data-lucide="download"></i><span>Request</span></button>` : ''}
      ${f.imdb ? `<a class="film-score${scoreTone(f.score)}" href="https://mdblist.com/${f.show ? 'show' : 'movie'}/${esc(f.imdb)}" target="_blank" rel="noopener noreferrer"
        title="${f.score != null ? `MDBList score ${esc(f.score)}. ` : ''}Open on MDBList">${f.score != null ? esc(f.score) : 'MDB'}</a>` : ''}
      ${f.imdb ? `<a class="film-id" href="https://www.imdb.com/title/${esc(f.imdb)}/" target="_blank" rel="noopener noreferrer" title="Open on IMDb">${esc(f.imdb)}</a>` : ''}
    </div>`).join('')
    : emptyTape(r.needs || [], unread);
  $('list-items').querySelectorAll('[data-request-film]').forEach((b) => b.addEventListener('click', () => requestFilm(b)));
  $('list-items').querySelectorAll('[data-setting]').forEach((b) => b.addEventListener('click', () => openSettings(b.dataset.setting)));
  icons();
  if (!genre) loadRequestStates(films.filter((f) => f.in_library === false && canRequest(f)), job, index);
}

// MDBList scores run 0-100; color them like a review shelf: good, fair, poor
function scoreTone(score) {
  if (score == null) return ' none';
  return score >= 70 ? ' good' : score >= 50 ? ' fair' : ' poor';
}

// Nothing on the list: say why, and when a key is missing, go straight to it in Settings.
const KEY_NAMES = { MDBLIST_API_KEY: 'MDBList API key', TRAKT_CLIENT_ID: 'Trakt client ID', TRAKT_ACCESS_TOKEN: 'Trakt access token' };
function emptyTape(needs, unread) {
  const key = needs.find((k) => KEY_NAMES[k]);
  if (key) {
    return `<div class="empty-state tape-empty"><i data-lucide="cassette-tape"></i>
      <b>Nothing on this tape yet</b>
      <span>StaffPicked needs your ${KEY_NAMES[key]} to read this list.</span>
      <button type="button" class="btn btn-primary btn-xs" data-setting="${key}"><i data-lucide="key-round"></i><span>Add the ${KEY_NAMES[key]}</span></button></div>`;
  }
  return `<div class="empty-state tape-empty"><i data-lucide="cassette-tape"></i>
    <b>Nothing on this tape yet</b>
    <span>${unread ? 'The list couldn\'t be read; the note above says why.' : 'This list has no films on it yet.'}</span></div>`;
}

// What the last sync found on the server: how much of the list it has, and the IMDb IDs of
// the films it doesn't, ready to copy (into Radarr's or Sonarr's import, say).
function renderListLibrary(library, films) {
  const el = $('list-library');
  if (!library.length) {
    el.innerHTML = films.length ? '<div class="library-line muted"><i data-lucide="circle-dashed"></i><span>Not synced yet, so it\'s not known which of these films are on the server.</span></div>' : '';
    icons();
    return;
  }
  el.innerHTML = library.map((l, n) => {
    const unknown = l.listed == null;   // that sync stopped before it compared the list with the library
    const all = !unknown && l.missing_count === 0;
    return `<div class="library-line ${l.errors ? 'bad' : unknown ? 'muted' : all ? 'ok' : ''}">
      <i data-lucide="${l.errors ? 'alert-triangle' : unknown ? 'circle-dashed' : all ? 'circle-check' : 'film'}"></i>
      <span>${l.listed == null ? `The last sync on ${esc(l.server)} didn't get this far · ${fmtTime(l.at)}`
        : `<b>${l.in_library} of ${l.listed}</b> in ${esc(l.server)}'s library${l.missing_count ? `, <b>${l.missing_count}</b> not there` : ''} · synced ${fmtTime(l.at)}`}${l.errors && l.error ? `<br><span class="library-error">${esc(l.error)}</span>` : ''}</span>
      ${l.missing.length ? `<span class="library-actions">
        <button type="button" class="btn btn-secondary btn-xs" data-copy-missing="${n}" title="Copy the IMDb IDs of the films not in the library, one per line"><i data-lucide="copy"></i><span>Copy IDs</span></button>
      </span>` : ''}
    </div>`;
  }).join('');
  el.querySelectorAll('[data-copy-missing]').forEach((b) => b.addEventListener('click', () => {
    const ids = library[Number(b.dataset.copyMissing)].missing;
    copyText(ids.join('\n')).then((ok) => showToast(ok ? `Copied ${ids.length} IMDb ID${ids.length === 1 ? '' : 's'}.` : 'Couldn\'t copy here; select them from the list instead.', ok ? 'success' : 'warning'));
  }));
  icons();
}

// Requests: Seerr takes films and shows; or Radarr takes films and Sonarr shows (Settings > Requests).
function requestService(show) {
  const rq = status.requests || {};
  return rq.service === 'arr' ? (show ? 'Sonarr' : 'Radarr') : 'Seerr';
}
function canRequest(f) {
  const rq = status.requests || {};
  return Boolean(f.imdb && (f.show ? rq.shows : rq.movies));
}

// A missing title the request service already has isn't missing: it's requested (not downloaded
// yet) or available (downloaded; the server shows it after its next scan and sync).
const REQUEST_MARKS = {
  requested: ['Requested', (svc) => `${svc} has it; it hasn't downloaded yet`],
  available: ['Available', (svc) => `${svc} has downloaded it; the next sync will see it`],
};
function markRequestState(row, state) {
  const mark = row?.querySelector('.film-mark');
  if (!mark || !REQUEST_MARKS[state]) return;
  const btn = row.querySelector('[data-request-film]');
  const [label, why] = REQUEST_MARKS[state];
  mark.className = `film-mark ${state}`;
  mark.textContent = label;
  mark.title = why(requestService(btn ? btn.dataset.show === '1' : false));
  btn?.remove();
}

async function loadRequestStates(films, job, index) {
  $('list-requests')?.remove();
  if (!films.length) return;
  let r;
  try {
    r = await api('requests/status', { method: 'POST', body: { items: films.map((f) => ({ imdb: f.imdb, show: Boolean(f.show) })) } });
  } catch (e) {
    r = { states: {}, errors: { service: e.message } };
  }
  if (listView?.job !== job || listView.index !== index) return;   // another list was opened meanwhile
  films.forEach((f) => markRequestState($('list-items').querySelector(`[data-imdb="${CSS.escape(f.imdb)}"]`), r.states[f.imdb]));
  const line = document.createElement('div');
  line.id = 'list-requests';
  line.dataset.services = [...new Set(films.map((f) => requestService(f.show)))].join(' and ');
  line.dataset.errors = Object.values(r.errors || {}).join('; ');
  $('list-library').append(line);
  renderRequestCounts();
}

// "Seerr: 2 requested, 1 missing", counted from the marks, so a request moves it along.
function renderRequestCounts() {
  const line = $('list-requests');
  if (!line) return;
  const counts = {};
  $('list-items').querySelectorAll('[data-imdb] .film-mark').forEach((m) => {
    const state = ['requested', 'available'].find((k) => m.classList.contains(k)) || 'missing';
    counts[state] = (counts[state] || 0) + 1;
  });
  const errors = line.dataset.errors;
  line.className = `library-line${errors ? ' bad' : ''}`;
  line.innerHTML = `<i data-lucide="${errors ? 'alert-triangle' : 'inbox'}"></i><span>${esc(line.dataset.services)}: `
    + ['requested', 'available', 'missing'].filter((k) => counts[k]).map((k) => `<b>${counts[k]}</b> ${k}`).join(', ')
    + (errors ? `<br><span class="library-error">Couldn't check: ${esc(errors)}</span>` : '') + '</span>';
  icons();
}

// One missing title, only when you press its button. Whole lists are never requested.
async function requestFilm(btn) {
  const name = btn.dataset.name;
  btn.disabled = true;
  try {
    const out = await api('requests/add', { method: 'POST', body: { imdb: btn.dataset.requestFilm, show: btn.dataset.show === '1' } });
    if (out.result === 'added' || out.result === 'already') {
      showToast(out.result === 'added' ? `Requested ${name} from ${out.service}.` : `${out.service} already has ${name}.`, 'success');
      markRequestState(btn.closest('.list-film'), out.state || 'requested');
      renderRequestCounts();
      return;
    }
    showToast(`${name} wasn't requested: ${out.error || `${out.service} said no`}.`, 'warning');
  } catch (e) {
    showToast(e.message, 'error');
  }
  btn.disabled = false;
}

// The clipboard API needs https; on a plain-http LAN address fall back to a hidden textarea.
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fall through */ }
  const t = document.createElement('textarea');
  t.value = text;
  t.setAttribute('readonly', '');
  t.style.position = 'fixed';
  t.style.opacity = '0';
  document.body.appendChild(t);
  t.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { ok = false; }
  t.remove();
  return ok;
}

// Where the films come from: MDBList and Trakt links, and list files that open in the film editor.
function renderListFeeds(feeds) {
  const names = { mdblist: 'MDBList', trakt: 'Trakt', file: 'List file', unknown: 'Source' };
  const icon = { mdblist: 'list', trakt: 'list', file: 'file-text', unknown: 'help-circle' };
  $('list-feeds').innerHTML = `<span class="list-feeds-label">Sources</span>` + (feeds.length ? feeds.map((f) => {
    const what = `<i data-lucide="${icon[f.kind] || 'list'}"></i><b>${names[f.kind] || 'Source'}</b><span class="list-feed-spec">${esc(f.spec)}</span><span class="list-feed-count" title="Films from this source">${f.count}</span>`;
    if (f.url) return `<a class="list-feed" href="${esc(f.url)}" target="_blank" rel="noopener noreferrer" title="Open ${esc(f.url)}">${what}<i data-lucide="external-link" class="list-feed-go"></i></a>`;
    if (f.file) return `<button type="button" class="list-feed" data-feed-file="${esc(f.file)}" title="Edit the films in ${esc(f.file)}">${what}<i data-lucide="list-ordered" class="list-feed-go"></i></button>`;
    return `<span class="list-feed">${what}</span>`;
  }).join('') : '<span class="list-feed-none">None set</span>');
  $('list-feeds').querySelectorAll('[data-feed-file]').forEach((b) => b.addEventListener('click', () => openWatchlist(b.dataset.feedFile)));
  icons();
}

// The poster sits beside the details and the backdrops go under them; a URL or provider
// image shows the copy the last sync saved.
function artFigure(a) {
  const src = a.image ? `api/images/file?name=${encodeURIComponent(a.image)}` : a.url;
  const label = { poster: 'Poster', thumb: 'Thumb' }[a.what] || 'Backdrop';
  return `<figure class="list-art-item ${a.what}">
    ${src ? `<a href="${esc(src)}" target="_blank" rel="noopener noreferrer" title="Open full size"><img src="${esc(src)}" alt="${label}" loading="lazy"></a>`
      : `<div class="list-art-missing"><i data-lucide="image-off"></i><span>${a.remote ? 'Not downloaded yet. The next sync fetches it.' : 'File not found in the config folder.'}</span></div>`}
    <figcaption title="${esc(a.spec)}"><b>${label}</b> ${esc(a.spec)}</figcaption>
  </figure>`;
}

function renderListArt(art) {
  const poster = art.find((a) => a.what === 'poster');
  $('list-poster').innerHTML = poster ? artFigure(poster)
    : '<figure class="list-art-item poster"><div class="list-art-missing"><i data-lucide="image-off"></i><span>No poster set</span></div></figure>';
  $('list-art').innerHTML = art.filter((a) => a.what !== 'poster').map(artFigure).join('');
  icons();
}

$('btn-list-edit').addEventListener('click', () => listView && openEntry(listView.job, listView.index));

// Save what the list's MDBList or Trakt sources give today as a list file to hand-edit.
$('btn-list-export').addEventListener('click', async () => {
  if (!listView) return;
  const { job, index, name } = listView;
  const r = await review({
    title: `Save "${name}" as a list file?`,
    intro: 'This will:',
    items: [`Write the films its lists give today to a new ${job}/….md, one per line, in order`],
    option: { text: `Then have "${name}" use that file instead of ${listView.linked.join(', ')}, so it stops following those lists and only changes when you edit it.`, checked: false },
    foot: 'Nothing changes on the media server until the next sync.',
    okText: 'Save List File',
    danger: false,
  });
  if (!r.ok) return;
  const btn = $('btn-list-export');
  btn.disabled = true;
  try {
    const out = await api(`builder/${job}/${index}/export`, { method: 'POST', body: { use_it: r.option } });
    showToast(`Saved ${out.films} films to ${out.name}${out.skipped ? ` (${out.skipped} without an IMDb ID left out)` : ''}.${out.used ? ` "${name}" now uses it.` : ''}`, 'success');
    refresh();
    openWatchlist(out.name);
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    btn.disabled = false;
  }
});
$('btn-list-anyway').addEventListener('click', async () => {
  if (!listView) return;
  const { job, name } = listView;
  const yes = await showAppConfirm(`Sync "${name}" anyway? The films its lists no longer have come off the server, however many that is.`, { okText: 'Sync Anyway', danger: true });
  if (!yes) return;
  try {
    await api(`jobs/${job}/run`, { method: 'POST', body: { action: 'sync', only: name, allow_removals: true } });
    $('list-held').hidden = true;
    showToast(`Syncing "${name}" without the removal limit.`, 'info');
  } catch (e) {
    showToast(e.message, 'error');
  }
});

$('btn-list-remove').addEventListener('click', () => listView && removeFromServer(listView.job, listView.name, jobPicks[listView.job]?.server || ''));

const TRIGGERS = { start: 'On startup', schedule: 'Scheduled', manual: 'Manual', arrival: 'New film', setup: 'First sync' };

// A run's outcome in a few words: "+3 films, -1, 1 error", or "would add 3" for a dry run.
function runOutcome(r) {
  const s = r.summary;
  if (r.status === 'running') return 'Running…';
  if (r.status === 'aborted') return 'Stopped';
  if (!s) return r.status === 'ok' ? 'Finished' : r.status === 'failed' ? 'Failed' : '';
  const films = (n) => `${n} film${n === 1 ? '' : 's'}`;
  const parts = [];
  if (s.dry_run) {
    if (s.added) parts.push(`would add ${films(s.added)}`);
    if (s.removed) parts.push(`would remove ${s.removed}`);
  } else {
    if (s.added) parts.push(`+${films(s.added)}`);
    if (s.removed) parts.push(`−${s.removed}`);
  }
  if (!parts.length && r.changed) parts.push(`${s.dry_run ? 'would change' : 'changed'} ${r.changed} list${r.changed === 1 ? '' : 's'}`);
  if (!parts.length && r.action === 'sync') parts.push('no changes');
  if (s.errors) parts.push(`${s.errors} error${s.errors === 1 ? '' : 's'}`);
  return parts.join(', ') || 'Finished';
}

let historyRows = [];
async function renderHistory() {
  const rows = await api('history').catch(() => []);
  historyRows = rows;
  const el = $('history-list');
  if (!rows.length) {
    el.innerHTML = '<div class="empty-state"><i data-lucide="history"></i><span>No runs yet. The first sync shows up here.</span></div>';
  } else {
    const labels = Object.fromEntries(status.jobs.map((j) => [j.name, j.label]));
    el.innerHTML = rows.slice(0, 12).map((r, n) => {
      const what = r.action === 'check' ? 'Check' : r.action === 'remove' ? 'Remove' : r.dry_run ? 'Dry run' : 'Sync';
      // each server's own result, when the run went to more than one
      const per = Object.entries(r.servers || {});
      const servers = per.length > 1 ? `<span class="history-servers">${per.map(([sn, v]) => `<span class="history-server" title="${esc(sn)}: ${v === 'ok' ? 'finished' : 'had errors'}"><span class="history-dot ${v === 'ok' ? 'ok' : 'failed'}"></span>${esc(sn)}</span>`).join('')}</span>` : '';
      const outcome = runOutcome(r);
      const tag = r.has_log ? 'button' : 'div';
      return `<${tag} ${r.has_log ? `type="button" data-run="${n}" title="Open this run's log"` : ''} class="history-row${r.has_log ? ' has-log' : ''}">
        <span class="history-dot ${esc(r.status)}"></span>
        <span class="history-what">${esc(labels[r.job] || r.job)} · ${what}${r.server ? ` · ${esc(r.server)}` : ''}${r.only ? ` · ${esc(r.only)}` : ''}${servers}</span>
        <span class="history-meta">${esc(TRIGGERS[r.trigger] || r.trigger)} · ${fmtTime(r.started)} · ${duration(r.started, r.ended)}${outcome ? ` · <span class="history-outcome ${r.summary?.errors || r.status === 'failed' ? 'bad' : ''}">${esc(outcome)}</span>` : ''}</span>
      </${tag}>`;
    }).join('');
    el.querySelectorAll('[data-run]').forEach((b) => b.addEventListener('click', () => openRun(historyRows[Number(b.dataset.run)])));
  }
  icons();
}

async function openRun(r) {
  const label = status.jobs.find((j) => j.name === r.job)?.label || r.job;
  const what = r.action === 'check' ? 'Check' : r.action === 'remove' ? 'Remove' : r.dry_run ? 'Dry run' : 'Sync';
  $('run-title').textContent = `${label} · ${what}`;
  $('run-sub').textContent = `${TRIGGERS[r.trigger] || r.trigger}, ${fmtTime(r.started)}${r.ended ? `, took ${duration(r.started, r.ended)}` : ''}. ${runOutcome(r).replace(/^./, (c) => c.toUpperCase())}.`;
  $('run-output').textContent = 'Loading…';
  $('run-changes').innerHTML = '';
  openDrawer('run-drawer');
  try {
    const out = await api(`runs/${encodeURIComponent(r.id)}/log`);
    $('run-output').textContent = out.lines.join('\n') || 'This run printed nothing.';
    renderRunChanges(out.changes || [], r);
  } catch (e) {
    $('run-output').textContent = e.message;
  }
}

// What a run changed (or a dry run would change), one card per list: films in and out by
// title, and anything else such as artwork.
function renderRunChanges(changes, r) {
  const el = $('run-changes');
  if (r.action !== 'sync') { el.innerHTML = ''; return; }
  const would = r.dry_run;
  const films = (n) => `${n} film${n === 1 ? '' : 's'}`;
  const servers = new Set(changes.map((c) => c.server));
  const head = would ? 'What this dry run would change' : 'What this run changed';
  if (!changes.length) {
    el.innerHTML = `<h4 class="run-changes-head">${head}</h4><p class="run-change-none">${would ? 'Nothing: the server already matches your lists.' : 'Nothing: the server already matched your lists.'}</p>`;
    return;
  }
  const titles = (list, sign, cls) => list.length ? `<ul class="run-change-films ${cls}">${list.slice(0, 200).map((t) => `<li><span>${sign}</span> ${esc(t)}</li>`).join('')}${list.length > 200 ? `<li class="muted">… and ${list.length - 200} more</li>` : ''}</ul>` : '';
  el.innerHTML = `<h4 class="run-changes-head">${head} <span class="muted">${changes.length} list${changes.length === 1 ? '' : 's'}</span></h4>` +
    changes.map((c) => {
      const bits = [];
      if (c.added.length) bits.push(`${would ? 'adds' : 'added'} ${films(c.added.length)}`);
      if (c.removed.length) bits.push(`${would ? 'removes' : 'removed'} ${c.removed.length}`);
      const other = c.changes.filter((x) => !/^(creating collection|adding \d|removing \d)/.test(x));
      if (other.some((x) => /poster|backdrop|thumb|artwork/i.test(x))) bits.push('artwork changes');
      const where = [servers.size > 1 ? c.server : '', c.person ? `for ${c.person}` : ''].filter(Boolean).join(' · ');
      return `<details class="run-change" ${changes.length <= 3 ? 'open' : ''}>
        <summary><span class="run-change-name">${esc(c.name)}</span>${where ? ` <span class="muted">${esc(where)}</span>` : ''}
          <span class="run-change-sum">${esc(bits.join(', ') || 'other changes')}</span></summary>
        ${titles(c.added, '+', 'added')}${titles(c.removed, '−', 'removed')}
        ${other.length ? `<ul class="run-change-other">${other.map((x) => `<li>${esc(x.replace(/^./, (ch) => ch.toUpperCase()))}</li>`).join('')}</ul>` : ''}
      </details>`;
    }).join('');
}

async function refresh() {
  try {
    status = await api('status');
  } catch (e) {
    return;
  }
  $('app-version').textContent = `v${status.version}`;
  if (status.setup?.needed && !status.setup.skipped && !setupShown) openSetup();
  $('header-mode-selector').value = status.mode;
  $('btn-logout').style.display = status.auth ? '' : 'none';
  renderMetrics();
  renderItems();
  renderHistory();
  if (openDrawerEl?.id === 'logs-drawer') renderLogTabs();
  if (openDrawerEl?.id === 'settings-drawer') renderBulkOps();
  if (openDrawerEl?.id === 'calendar-drawer') renderCalendar();
}

// One badge per media server in the header: its name and version, green when it answers.
async function refreshEmby(force = false) {
  if (status?.setup?.needed) {
    $('emby-status').innerHTML = `<button type="button" class="connection-badge setup-badge" id="btn-setup-badge" title="Nothing syncs until a media server is set up">
      <span class="status-dot red"></span><span>Set up a server</span></button>`;
    $('btn-setup-badge').addEventListener('click', openSetup);
    return { ok: false, servers: [] };
  }
  try {
    const s = await api('emby', { method: force ? 'POST' : 'GET', body: force ? {} : undefined });
    const kind = (x) => (x.type === 'jellyfin' ? 'Jellyfin' : 'Emby');
    $('emby-status').innerHTML = s.servers.map((x) => `
      <div class="connection-badge" title="${esc(x.ok ? `${x.name}: connected to ${kind(x)}${x.server ? ` (${x.server})` : ''}` : `${x.name}: ${x.error}`)}">
        <span class="status-dot ${x.ok ? 'green' : 'red'}"></span>
        <span>${esc(x.ok ? `${x.name}${x.version ? ` · ${x.version}` : ''}` : `${x.name}: not connected`)}</span>
      </div>`).join('');
    return s;
  } catch (e) {
    return { ok: false, servers: [], error: e.message };
  }
}

$('header-mode-selector').addEventListener('change', async (e) => {
  try {
    await api('settings', { method: 'PUT', body: { mode: e.target.value } });
    showToast(`Mode set to ${e.target.selectedOptions[0].textContent}.`, 'success');
    refresh();
  } catch (err) {
    showToast(err.message, 'error');
  }
});

$('btn-run-all').addEventListener('click', async () => {
  try {
    const r = await api('jobs/all/run', { method: 'POST', body: {} });
    showToast(`Running ${r.started.join(' then ')}.`, 'info');
  } catch (e) {
    showToast(e.message, 'error');
  }
});

$('btn-logout').addEventListener('click', async () => {
  await api('logout', { method: 'POST', body: {} }).catch(() => {});
  window.location.href = 'login.html';
});

// ---------------------------------------------------------------- live logs

function renderLogTabs() {
  renderTabs($('log-tabs'), logTab, (j) => { logTab = j; loadLog(); });
}

async function loadLog() {
  renderLogTabs();
  $('btn-download-logs').href = `api/logs/${logTab}?download=1`;
  const r = await api(`logs/${logTab}`).catch(() => ({ lines: [] }));
  logLines[logTab] = r.lines;
  const out = $('console-output');
  out.textContent = r.lines.length ? r.lines.join('\n') : 'No output yet. Start a run and it streams here.';
  scrollConsole();
}

function scrollConsole() {
  const w = $('console-output').parentElement;
  w.scrollTop = w.scrollHeight;
}

function showLogs(job) {
  logTab = job || logTab || status.jobs[0].name;
  openDrawer('logs-drawer');
  loadLog();
}

$('btn-logs-toggle').addEventListener('click', () => showLogs());
$('btn-clear-console').addEventListener('click', () => { $('console-output').textContent = ''; });
$('btn-clear-server-logs').addEventListener('click', async () => {
  const label = status.jobs.find((j) => j.name === logTab).label;
  if (!(await showAppConfirm(`Delete the saved ${label.toLowerCase()} log from the server?`, { danger: true, okText: 'Delete' }))) return;
  await api(`logs/${logTab}`, { method: 'DELETE' }).catch((e) => showToast(e.message, 'error'));
  loadLog();
});

// ---------------------------------------------------------------- server events

function connectEvents() {
  const es = new EventSource('api/events');
  es.addEventListener('log', (e) => {
    const { job, line } = JSON.parse(e.data);
    if (openDrawerEl?.id === 'logs-drawer' && job === logTab) {
      const out = $('console-output');
      const w = out.parentElement;
      const atBottom = w.scrollHeight - w.scrollTop - w.clientHeight < 40;
      out.textContent += (out.textContent ? '\n' : '') + line;
      if (atBottom) scrollConsole();
    }
    if (checkWatch && job === checkWatch) {
      const out = $('check-output');
      out.textContent += (out.textContent ? '\n' : '') + line;
      out.parentElement.scrollTop = out.parentElement.scrollHeight;
    }
  });
  es.addEventListener('status', (e) => {
    const job = JSON.parse(e.data);
    if (!job.running && job.run) {
      const ok = job.run.status === 'ok';
      if (job.run.action !== 'check' || !ok) {
        showToast(`${job.label}: ${jobDetail({ ...job, enabled: true })}`, ok ? 'success' : job.run.status === 'aborted' ? 'warning' : 'error');
      }
      if (checkWatch === job.name) checkWatch = null;
      if (previewWatch.delete(job.name) && job.run.dry_run && job.run.status !== 'aborted' && job.run.id) {
        openRun({ ...job.run, job: job.name });
      }
    }
    refresh();
  });
  es.addEventListener('settings', () => { refresh(); refreshEmby(); });
  es.addEventListener('files', () => refresh());
  es.addEventListener('effects', (e) => setEffects(JSON.parse(e.data).effects !== false));
  es.addEventListener('progress', (e) => {
    const d = JSON.parse(e.data);
    progressHandlers[d.task]?.(d);
  });
  es.onerror = () => {
    // EventSource reconnects by itself; a 401 means the session expired.
    if (es.readyState === EventSource.CLOSED) setTimeout(connectEvents, 5000);
  };
}

// ---------------------------------------------------------------- settings

let settings = null;
const secretEdits = {};
let serverCards = [];      // the Servers cards as edited: [{id, name, values, set, typed, cleared}]
let removedServers = [];   // ids of saved servers whose card was removed; gone on Save

// A card per media server. New cards have no id until saved; Remove takes effect on Save.
function renderServerCards() {
  const fields = settings.server_fields;
  const names = { emby: 'Emby', jellyfin: 'Jellyfin' };
  $('server-cards').innerHTML = serverCards.map((c, i) => `
    <details class="server-card" data-card="${i}" ${c.open ? 'open' : ''}>
      <summary class="server-card-head">
        <i data-lucide="chevron-right" class="server-card-chevron"></i>
        <h4>${esc(c.values.NAME || c.name || names[c.values.TYPE] || 'New server')}</h4>
        <span class="server-card-url">${esc(c.values.URL || 'no URL yet')}</span>
        <code class="env-key">${c.id ? (c.id === '1' ? 'SERVER_*' : `SERVER_${esc(c.id)}_*`) : 'not saved yet'}</code>
        <span class="server-card-actions">
          <button type="button" class="btn btn-secondary btn-xs" data-test-server="${i}" title="Check this server answers (save first)"><i data-lucide="plug-zap"></i><span>Test</span></button>
          ${serverCards.length > 1 ? `<button type="button" class="btn btn-danger-light btn-xs admin-only" data-remove-server="${i}" title="Stop syncing to this server"><i data-lucide="trash-2"></i><span>Remove</span></button>` : ''}
        </span>
      </summary>
      <div class="form-grid">
        ${fields.map((f) => {
          const id = `srv-${i}-${f.field}`;
          const wide = f.hint.length > 70 || f.field === 'URL';
          let input;
          if (f.choices) {
            input = `<select id="${id}" data-srv="${i}" data-field="${f.field}">${f.choices.map((ch) => `<option value="${esc(ch)}" ${ch === (c.values[f.field] || f.choices[0]) ? 'selected' : ''}>${esc(names[ch] || ch)}</option>`).join('')}</select>`;
          } else if (f.secret) {
            const saved = c.set[f.field] && !c.cleared[f.field];
            input = `<div class="secret-row">
              <input type="password" id="${id}" data-srv="${i}" data-field="${f.field}" data-secret value="${esc(c.typed[f.field] || '')}" autocomplete="new-password" placeholder="${saved ? '•••••••• saved; type to replace' : c.cleared[f.field] ? 'will be cleared on save' : 'not set'}">
              ${saved ? `<button type="button" class="btn btn-danger-light btn-xs" data-clear-srv="${i}:${f.field}" title="Clear this value">Clear</button>` : ''}
            </div>`;
          } else {
            input = `<input type="text" id="${id}" data-srv="${i}" data-field="${f.field}" value="${esc(c.values[f.field] || '')}" autocomplete="off"${f.field === 'NAME' ? ` placeholder="${esc(c.name || names[c.values.TYPE] || 'Emby')}"` : ''}>`;
          }
          return `<div class="form-group ${wide ? 'full-width' : ''}">
            <label for="${id}">${esc(f.label)}</label>
            ${input}
            ${f.hint ? `<span class="field-hint">${esc(f.hint)}</span>` : ''}
          </div>`;
        }).join('')}
      </div>
    </details>`).join('');
  const box = $('server-cards');
  box.querySelectorAll('details').forEach((d) => d.addEventListener('toggle', () => { serverCards[Number(d.dataset.card)].open = d.open; }));
  box.querySelectorAll('[data-clear-srv]').forEach((b) => b.addEventListener('click', () => {
    const [i, f] = b.dataset.clearSrv.split(':');
    readServerCards();
    serverCards[i].cleared[f] = true;
    serverCards[i].typed[f] = '';
    renderServerCards();
  }));
  box.querySelectorAll('[data-remove-server]').forEach((b) => b.addEventListener('click', async (e) => {
    e.preventDefault();   // a button in the card's summary doesn't fold the card
    readServerCards();
    const c = serverCards[Number(b.dataset.removeServer)];
    const label = c.values.NAME || c.name || 'this server';
    if (c.id && !(await showAppConfirm(`Remove ${label} from StaffPicked? Its settings go when you save. Nothing on the server itself is changed; what StaffPicked built there stays until you remove it.`, { danger: true, okText: 'Remove' }))) return;
    if (c.id) removedServers.push(c.id);
    serverCards.splice(Number(b.dataset.removeServer), 1);
    renderServerCards();
  }));
  box.querySelectorAll('[data-test-server]').forEach((b) => b.addEventListener('click', async (e) => {
    e.preventDefault();
    const c = serverCards[Number(b.dataset.testServer)];
    if (!c.id) { showToast('Save the settings first, then test this server.', 'warning'); return; }
    const s = await refreshEmby(true);
    const x = (s.servers || []).find((y) => y.id === c.id);
    if (!x) { showToast(s.error || 'Save the settings first, then test this server.', 'warning'); return; }
    showToast(testLine(x) + (x.ok ? '' : ' (Save settings first if you just changed them.)'), x.ok ? 'success' : 'error');
  }));
  // the card's title follows its name and type as they're typed, without redrawing the fields
  box.querySelectorAll('[data-field="NAME"], [data-field="TYPE"], [data-field="URL"]').forEach((el) => el.addEventListener('input', () => {
    readServerCards();
    const c = serverCards[Number(el.dataset.srv)];
    const card = el.closest('.server-card');
    card.querySelector('h4').textContent = c.values.NAME || c.name || names[c.values.TYPE] || 'New server';
    card.querySelector('.server-card-url').textContent = c.values.URL || 'no URL yet';
    if (el.dataset.field === 'TYPE' && !c.name) card.querySelector('[data-field="NAME"]').placeholder = names[c.values.TYPE];
  }));
  icons();
}

// Copy what's typed in the cards back into serverCards, so a re-render keeps it.
function readServerCards() {
  document.querySelectorAll('#server-cards [data-srv]').forEach((el) => {
    const c = serverCards[Number(el.dataset.srv)];
    if (!c) return;
    if (el.dataset.secret !== undefined) c.typed[el.dataset.field] = el.value;
    else c.values[el.dataset.field] = el.value;
  });
}

function serverPayload() {
  readServerCards();
  return serverCards.map((c) => {
    const values = { ...c.values };
    settings.server_fields.filter((f) => f.secret).forEach((f) => {
      if (c.typed[f.field]) values[f.field] = c.typed[f.field];
      else if (c.cleared[f.field]) values[f.field] = '';
    });
    return { id: c.id, values };
  });
}

function loadServerCards() {
  // one server opens as before; several start folded to their name and URL
  const open = settings.servers.length === 1;
  serverCards = settings.servers.map((x) => ({ id: x.id, name: x.name, values: { ...x.values }, set: { ...x.set }, typed: {}, cleared: {}, open }));
  removedServers = [];
}

$('btn-add-server').addEventListener('click', () => {
  readServerCards();
  const taken = serverCards.map((c) => c.values.TYPE || 'emby');
  const type = taken.includes('emby') && !taken.includes('jellyfin') ? 'jellyfin' : 'emby';
  serverCards.push({ id: null, name: '', values: { TYPE: type }, set: {}, typed: {}, cleared: {}, open: true });
  renderServerCards();
  $('server-cards').lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});

// Quality profiles and root folders are picked from what Radarr and Sonarr have; blank means their first.
const ARR_PICKS = {
  RADARR_QUALITY_PROFILE: ['Radarr', 'profiles'], RADARR_ROOT_FOLDER: ['Radarr', 'folders'],
  SONARR_QUALITY_PROFILE: ['Sonarr', 'profiles'], SONARR_ROOT_FOLDER: ['Sonarr', 'folders'],
};
function arrOptions(svc, choices, value, first) {
  const all = [...choices];
  if (value && !all.includes(value)) all.unshift(value);   // keep a saved value the service hasn't listed (yet)
  return `<option value="">${first ? `${svc}'s first (${esc(first)})` : `${svc}'s first`}</option>`
    + all.map((c) => `<option value="${esc(c)}" ${c === value ? 'selected' : ''}>${esc(c)}${choices.length && !choices.includes(c) ? ` (not in ${svc})` : ''}</option>`).join('');
}
function fillArrPicks(svc, r) {
  Object.entries(ARR_PICKS).filter(([, [s]]) => s === svc).forEach(([key, [, list]]) => {
    const el = $(`env-${key}`);
    if (el) el.innerHTML = arrOptions(svc, r[list] || [], el.value, (r[list] || [])[0]);
  });
}

// Each request service has a Test button after its API key; Settings shows only the chosen service's fields.
const REQUEST_TESTS = { SEERR_API_KEY: 'Seerr', RADARR_API_KEY: 'Radarr', SONARR_API_KEY: 'Sonarr' };
const REQUEST_GROUPS = { Seerr: 'seerr', Radarr: 'arr', Sonarr: 'arr' };
function showRequestGroups() {
  const pick = $('env-REQUEST_SERVICE')?.value || 'seerr';
  document.querySelectorAll('#settings-fields [data-group]').forEach((el) => {
    const want = REQUEST_GROUPS[el.dataset.group];
    el.style.display = want && want !== pick ? 'none' : '';
  });
}
function testedText(svc, r) {
  if (svc === 'Seerr') return `Connected to Seerr ${r.version}.${r.user ? ` Requests go in as ${r.user}.` : ''}`;
  if (r.problem) return `Connected to ${svc} ${r.version}, but ${r.problem}.`;
  return `Connected to ${svc} ${r.version}. New ${svc === 'Sonarr' ? 'shows' : 'films'} go to ${r.folder} as ${r.profile}.`;
}
async function testRequestService(svc, saved) {
  const out = $(`test-result-${svc.toLowerCase()}`);
  const env = {};
  if (!saved) {   // what's typed, over what's saved
    settings.fields.filter((f) => f.key.startsWith(`${svc.toUpperCase()}_`)).forEach((f) => { env[f.key] = $(`env-${f.key}`)?.value.trim() || ''; });
  }
  out.textContent = 'Checking…';
  try {
    const r = await api('requests/test', { method: 'POST', body: { service: svc.toLowerCase(), env } });
    if (svc !== 'Seerr') fillArrPicks(svc, r);
    out.textContent = testedText(svc, r);
  } catch (err) {
    out.textContent = saved ? `Couldn't list ${svc}'s profiles and folders: ${err.message}` : err.message;
  }
}

// The schedule: at set times every day (SYNC_TIME, a list) or on an interval (SYNC_EVERY).
// The hidden SYNC_TIME and SYNC_EVERY inputs carry what Save sends; syncSchedule() fills them.
const EVERY_RE = /^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?$/i;
const timeRow = (t) => `<div class="sched-time">
  <input type="time" value="${esc(t)}" aria-label="Sync time" required>
  <button type="button" class="btn btn-danger-light btn-xs" data-remove-time title="Remove this time"><i data-lucide="x" class="btn-icon"></i></button>
</div>`;
function scheduleFields(timeField, everyField) {
  const times = (timeField.value || '').split(/[,\s]+/).filter((t) => /^\d{1,2}:\d{2}$/.test(t)).map((t) => t.padStart(5, '0'));
  const m = (everyField.value || '').trim().match(EVERY_RE);
  const minutes = m && (m[1] || m[2]) ? (+m[1] || 0) * 60 + (+m[2] || 0) : 0;
  const hours = minutes && minutes % 60 === 0;
  return `<div class="form-group full-width" data-group="Schedule">
      <label for="sched-mode">When to sync</label>
      <select id="sched-mode">
        <option value="times" ${minutes ? '' : 'selected'}>At set times every day</option>
        <option value="every" ${minutes ? 'selected' : ''}>On an interval, every few hours or minutes</option>
      </select>
    </div>
    <div class="form-group full-width" data-group="Schedule" id="sched-times-group">
      <label>${esc(timeField.label)} <code class="env-key">SYNC_TIME</code></label>
      <div class="sched-times" id="sched-times">${(times.length ? times : ['06:00']).map(timeRow).join('')}</div>
      <button type="button" class="btn btn-secondary btn-xs sched-add" id="btn-add-time"><i data-lucide="plus" class="btn-icon"></i><span>Add Time</span></button>
      <input type="hidden" id="env-SYNC_TIME" data-key="SYNC_TIME" value="${esc(timeField.value || '')}">
      <span class="field-hint">${esc(timeField.hint)}</span>
    </div>
    <div class="form-group full-width" data-group="Schedule" id="sched-every-group">
      <label for="sched-every-n">${esc(everyField.label || 'Sync every')} <code class="env-key">SYNC_EVERY</code></label>
      <div class="sched-every">
        <input type="number" id="sched-every-n" min="1" step="1" value="${minutes ? (hours ? minutes / 60 : minutes) : 6}">
        <select id="sched-every-unit">
          <option value="h" ${!minutes || hours ? 'selected' : ''}>hours</option>
          <option value="m" ${minutes && !hours ? 'selected' : ''}>minutes</option>
        </select>
      </div>
      <input type="hidden" id="env-SYNC_EVERY" data-key="SYNC_EVERY" value="${esc(everyField.value || '')}">
      <span class="field-hint">${esc(everyField.hint || '')}</span>
    </div>`;
}
function syncSchedule() {
  if (!$('sched-mode')) return;
  const every = $('sched-mode').value === 'every';
  $('sched-times-group').style.display = every ? 'none' : '';
  $('sched-every-group').style.display = every ? '' : 'none';
  const rows = [...document.querySelectorAll('#sched-times .sched-time')];
  rows.forEach((r) => { r.querySelector('[data-remove-time]').disabled = rows.length < 2; });
  const times = [...new Set(rows.map((r) => r.querySelector('input').value).filter(Boolean))].sort();
  $('env-SYNC_TIME').value = times.join(', ');
  // a blank or zero interval still goes to the server, which says what's wrong with it
  $('env-SYNC_EVERY').value = every ? `${Math.max(0, Math.round(+$('sched-every-n').value || 0))}${$('sched-every-unit').value}` : '';
}
function wireSchedule() {
  if (!$('sched-mode')) return;
  const wrap = $('sched-times');
  ['sched-mode', 'sched-every-n', 'sched-every-unit'].forEach((id) => {
    $(id).addEventListener('input', syncSchedule);
    $(id).addEventListener('change', syncSchedule);
  });
  wrap.addEventListener('input', syncSchedule);
  wrap.addEventListener('change', syncSchedule);
  wrap.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-remove-time]');
    if (!btn || wrap.children.length < 2) return;
    btn.closest('.sched-time').remove();
    syncSchedule();
  });
  $('btn-add-time').addEventListener('click', () => {
    // the new time defaults to 12 hours after the last one
    const last = [...wrap.querySelectorAll('input')].map((i) => i.value).filter(Boolean).pop() || '06:00';
    const [h, m] = last.split(':').map(Number);
    wrap.insertAdjacentHTML('beforeend', timeRow(`${String((h + 12) % 24).padStart(2, '0')}:${String(m).padStart(2, '0')}`));
    icons();
    syncSchedule();
    wrap.lastElementChild.querySelector('input').focus();
  });
  syncSchedule();
}

function renderSettings() {
  const groups = [];
  for (const f of settings.fields) {
    if (!groups.includes(f.group)) groups.push(f.group);
  }
  $('settings-fields').innerHTML = groups.map((g) => `
    <div class="form-section full-width" data-group="${esc(g)}"><h4>${esc(g)}</h4></div>
    ${settings.fields.filter((f) => f.group === g).map((f) => {
      if (f.key === 'SYNC_TIME') return scheduleFields(f, settings.fields.find((x) => x.key === 'SYNC_EVERY') || { value: '' });
      if (f.key === 'SYNC_EVERY') return '';
      const wide = f.hint.length > 70 || f.key.endsWith('URL');
      let input;
      if (f.choices) {
        const names = { emby: 'Emby', jellyfin: 'Jellyfin', 0: 'Off', 1: 'On', true: 'Yes', false: 'No',
          failures: 'Only when something fails', always: 'After every sync',
          seerr: 'Seerr (films and TV)', arr: 'Radarr (films) and Sonarr (TV)',
          '5m': 'Every 5 minutes', '15m': 'Every 15 minutes', '30m': 'Every 30 minutes', '1h': 'Every hour', off: 'Off' };
        input = `<select id="env-${f.key}" data-key="${f.key}">${f.choices.map((c) => `<option value="${esc(c)}" ${c === (f.value || f.choices[0]) ? 'selected' : ''}>${esc(names[c] || c)}</option>`).join('')}</select>`;
      } else if (ARR_PICKS[f.key]) {
        // filled with what Radarr or Sonarr actually has once it answers (fillArrPicks)
        input = `<select id="env-${f.key}" data-key="${f.key}">${arrOptions(ARR_PICKS[f.key][0], [], f.value)}</select>`;
      } else if (f.secret) {
        input = `<div class="secret-row">
          <input type="password" id="env-${f.key}" data-key="${f.key}" data-secret autocomplete="new-password" placeholder="${f.set ? '•••••••• saved; type to replace' : 'not set'}">
          ${f.set ? `<button type="button" class="btn btn-danger-light btn-xs" data-clear="${f.key}" title="Clear this value">Clear</button>` : ''}
        </div>`;
      } else if (f.suggest) {
        input = `<input type="text" id="env-${f.key}" data-key="${f.key}" value="${esc(f.value)}" list="env-${f.key}-list"
          placeholder="${esc(f.placeholder || '')} (the container's)" autocomplete="off" spellcheck="false">
          <datalist id="env-${f.key}-list">${f.suggest.map((z) => `<option value="${esc(z)}">`).join('')}</datalist>`;
      } else {
        input = `<input type="text" id="env-${f.key}" data-key="${f.key}" value="${esc(f.value)}" placeholder="${esc(f.placeholder || '')}" autocomplete="off">`;
      }
      if (REQUEST_TESTS[f.key]) {
        const svc = REQUEST_TESTS[f.key];
        input += `<button type="button" class="btn btn-secondary btn-xs notify-test" data-test-service="${svc}">
          <i data-lucide="plug-zap" class="btn-icon"></i><span>Test ${svc}</span></button>
          <span class="field-hint" id="test-result-${svc.toLowerCase()}"></span>`;
      }
      if (f.key === 'NOTIFY_URL') {
        input += `<button type="button" class="btn btn-secondary btn-xs notify-test" id="btn-notify-test">
          <i data-lucide="send" class="btn-icon"></i><span>Send Test</span></button>`;
      }
      return `<div class="form-group ${wide ? 'full-width' : ''}" data-group="${esc(g)}">
        <label for="env-${f.key}">${esc(f.label)} <code class="env-key">${f.key}</code></label>
        ${input}
        ${f.hint ? `<span class="field-hint">${esc(f.hint)}</span>` : ''}
      </div>`;
    }).join('')}`).join('');
  $('settings-fields').querySelectorAll('[data-clear]').forEach((b) => b.addEventListener('click', () => {
    secretEdits[b.dataset.clear] = '';
    const input = $(`env-${b.dataset.clear}`);
    input.value = '';
    input.placeholder = 'will be cleared on save';
    b.remove();
  }));
  $('settings-fields').querySelectorAll('[data-test-service]').forEach((b) => b.addEventListener('click', async () => {
    b.disabled = true;
    await testRequestService(b.dataset.testService, false);
    b.disabled = false;
  }));
  wireSchedule();
  $('env-REQUEST_SERVICE')?.addEventListener('change', showRequestGroups);
  showRequestGroups();
  // with Radarr or Sonarr saved, list its quality profiles and root folders straight away
  ['Radarr', 'Sonarr'].forEach((svc) => {
    const field = (k) => settings.fields.find((f) => f.key === `${svc.toUpperCase()}_${k}`) || {};
    if (field('URL').value && field('API_KEY').set) testRequestService(svc, true);
  });
  $('btn-notify-test')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      await api('notify/test', { method: 'POST', body: { url: $('env-NOTIFY_URL').value.trim() } });
      showToast('Test sent. Check that it arrived.', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btn.disabled = false;
    }
  });
  renderServerCards();
  renderBulkOps();
  $('current-password-group').style.display = settings.auth ? '' : 'none';
  $('btn-remove-password').style.display = settings.auth ? '' : 'none';
  $('password-hint').textContent = settings.auth
    ? 'A password is set. Changing it signs out every other browser.'
    : 'No password is set, so the UI only opens from your local network.';
  loadMfa();
}

function renderBulkOps() {
  $('bulk-actions').innerHTML = status.jobs.map((j) => `
    <button type="button" class="btn btn-danger-light" data-bulk="${j.name}" ${j.running || !j.installed ? 'disabled' : ''}>
      <i data-lucide="trash-2" class="btn-icon"></i><span>${j.name === 'genres' ? 'Remove All Genre Artwork' : `Remove All ${esc(j.label)}`}</span>
    </button>`).join('');
  $('bulk-actions').querySelectorAll('[data-bulk]').forEach((b) => b.addEventListener('click', () => removeFromServer(b.dataset.bulk)));
  icons();
}

// Opens Settings; with a key (MDBLIST_API_KEY), scrolls to that field and puts the cursor in it.
async function openSettings(focusKey = '') {
  try {
    settings = await api('settings');
    Object.keys(secretEdits).forEach((k) => delete secretEdits[k]);
    loadServerCards();
    renderSettings();
    takeSettingsSnapshot();
    openDrawer('settings-drawer');
    const field = focusKey && $(`env-${focusKey}`);
    if (field) {
      field.scrollIntoView({ block: 'center' });
      field.focus({ preventScroll: true });
      field.closest('.form-group')?.classList.add('flash');
      setTimeout(() => field.closest('.form-group')?.classList.remove('flash'), 2000);
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
}

$('btn-settings-toggle').addEventListener('click', () => openSettings());

// Everything Save Settings would send, to tell whether anything was changed since it opened.
let settingsSnapshot = null;
function settingsState() {
  const env = {};
  document.querySelectorAll('#settings-fields [data-key]').forEach((el) => { env[el.dataset.key] = el.value; });
  return JSON.stringify({ env, cleared: Object.keys(secretEdits).sort(), servers: serverPayload(), removedServers });
}
const takeSettingsSnapshot = () => { settingsSnapshot = settingsState(); };

drawerGuards['settings-drawer'] = {
  dirty: () => settingsSnapshot !== null && settingsState() !== settingsSnapshot,
  save: saveSettings,
  discard: () => { settingsSnapshot = null; },
  what: () => 'You changed some settings.',
};

$('settings-form').addEventListener('submit', (e) => {
  e.preventDefault();
  saveSettings();
});

async function saveSettings() {
  const env = {};
  document.querySelectorAll('#settings-fields [data-key]').forEach((el) => {
    if (el.dataset.secret !== undefined) {
      if (el.value) env[el.dataset.key] = el.value;
      else if (el.dataset.key in secretEdits) env[el.dataset.key] = '';
    } else {
      env[el.dataset.key] = el.value;
    }
  });
  try {
    settings = await api('settings', {
      method: 'PUT',
      body: { env, servers: serverPayload(), removed_servers: removedServers },
    });
    Object.keys(secretEdits).forEach((k) => delete secretEdits[k]);
    loadServerCards();
    renderSettings();
    takeSettingsSnapshot();
    showToast('Settings saved.', 'success');
    refresh();
    refreshEmby(true);
    return true;
  } catch (err) {
    showToast(err.message, 'error');
    return false;
  }
}

// What one server's test found, as a sentence.
const testLine = (x) => (x.ok ? `${x.name}: connected${x.server ? ` to ${x.server}` : ''}${x.version ? ` v${x.version}` : ''}.` : `${x.name}: ${x.error}`);

$('btn-test-emby').addEventListener('click', async () => {
  const s = await refreshEmby(true);
  if (!s.servers.length) { showToast(s.error || 'No server is set up.', 'error'); return; }
  showToast(s.servers.map(testLine).join(' ') + (s.ok ? '' : ' (Save settings first if you just changed them.)'), s.ok ? 'success' : 'error');
});

async function setPassword(newPw) {
  try {
    const r = await api('password', { method: 'PUT', body: { current: $('current-password').value, new: newPw, code: $('password-code').value.trim() } });
    $('current-password').value = '';
    $('new-password').value = '';
    $('password-code').value = '';
    settings.auth = r.auth;
    readServerCards();   // keep unsaved server edits
    renderSettings();
    showToast(r.auth ? 'Password set. Other browsers have to sign in again.' : 'Password removed.', 'success');
    refresh();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

$('password-form').addEventListener('submit', (e) => {
  e.preventDefault();
  if (!$('new-password').value) { showToast('Type a new password first.', 'warning'); return; }
  setPassword($('new-password').value);
});
$('btn-remove-password').addEventListener('click', async () => {
  if (await showAppConfirm('Remove the password? Two-factor sign-in goes with it, and the UI will only open from your local network.', { danger: true, okText: 'Remove' })) setPassword('');
});

// ---------------------------------------------------------------- two-factor sign-in

let mfa = { enabled: false, password: false, recovery_left: 0 };
let mfaEnrolling = false;

async function loadMfa() {
  try {
    mfa = await api('mfa');
  } catch {
    return;
  }
  renderMfa();
}

function renderMfa() {
  const show = (id, on) => { $(id).hidden = !on; };
  $('password-code-group').hidden = !mfa.enabled;
  if (!mfa.password) {
    $('mfa-status').textContent = 'Set a password first. Two-factor sign-in then asks for a code from an authenticator app as well.';
  } else if (mfa.enabled) {
    $('mfa-status').textContent = `On: signing in asks for a code from your authenticator app. ${mfa.recovery_left} recovery code${mfa.recovery_left === 1 ? '' : 's'} left. Turning it off or making new recovery codes asks for your password and a code.`;
  } else if (mfaEnrolling) {
    $('mfa-status').textContent = 'Almost there.';
  } else {
    $('mfa-status').textContent = 'Off. Turn it on to sign in with your password and a code from an authenticator app (Google or Microsoft Authenticator, 1Password, Bitwarden, Aegis, 2FAS and the like). Recommended when StaffPicked can be reached from the internet.';
  }
  show('mfa-current-group', mfa.password && !mfaEnrolling);
  show('mfa-code-group', mfa.enabled);
  show('mfa-enroll', mfaEnrolling);
  show('btn-mfa-setup', mfa.password && !mfa.enabled && !mfaEnrolling);
  show('btn-mfa-enable', mfaEnrolling);
  show('btn-mfa-disable', mfa.enabled);
  show('btn-mfa-recovery', mfa.enabled);
}

function showRecoveryCodes(codes) {
  $('mfa-code-list').innerHTML = codes.map((c) => `<li><code>${esc(c)}</code></li>`).join('');
  $('mfa-code-list').dataset.codes = codes.join('\n');
  $('mfa-recovery').hidden = false;
}

function mfaInputs() {
  const body = { current: $('mfa-current').value, code: $('mfa-code').value.trim() };
  $('mfa-current').value = '';
  $('mfa-code').value = '';
  return body;
}

$('btn-mfa-setup').addEventListener('click', async () => {
  try {
    const r = await api('mfa/setup', { method: 'POST', body: mfaInputs() });
    const qr = qrcode(0, 'M');
    qr.addData(r.uri);
    qr.make();
    $('mfa-qr').innerHTML = qr.createSvgTag({ cellSize: 4, margin: 16, scalable: true });
    $('mfa-secret').textContent = r.secret.replace(/(.{4})/g, '$1 ').trim();
    $('mfa-recovery').hidden = true;
    mfaEnrolling = true;
    renderMfa();
    $('mfa-new-code').focus();
  } catch (e) {
    showToast(e.message, 'error');
  }
});

$('btn-mfa-enable').addEventListener('click', async () => {
  try {
    const r = await api('mfa/enable', { method: 'POST', body: { code: $('mfa-new-code').value.trim() } });
    $('mfa-new-code').value = '';
    $('mfa-qr').innerHTML = '';
    $('mfa-secret').textContent = '';
    mfaEnrolling = false;
    showRecoveryCodes(r.recovery_codes);
    showToast('Two-factor sign-in is on. Other browsers have to sign in again.', 'success');
    loadMfa();
  } catch (e) {
    showToast(e.message, 'error');
  }
});

$('btn-mfa-recovery').addEventListener('click', async () => {
  try {
    const r = await api('mfa/recovery', { method: 'POST', body: mfaInputs() });
    showRecoveryCodes(r.recovery_codes);
    showToast('New recovery codes made; the old ones no longer work.', 'success');
    loadMfa();
  } catch (e) {
    showToast(e.message, 'error');
  }
});

$('btn-mfa-disable').addEventListener('click', async () => {
  if (!await showAppConfirm('Turn off two-factor sign-in? Signing in will only ask for your password.', { danger: true, okText: 'Turn Off' })) return;
  try {
    await api('mfa/disable', { method: 'POST', body: mfaInputs() });
    $('mfa-recovery').hidden = true;
    showToast('Two-factor sign-in is off.', 'success');
    loadMfa();
  } catch (e) {
    showToast(e.message, 'error');
  }
});

$('btn-mfa-copy').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('mfa-code-list').dataset.codes || '');
    showToast('Recovery codes copied.', 'success');
  } catch {
    showToast('Copying isn\'t allowed here; select the codes and copy them yourself.', 'warning');
  }
});

// ---------------------------------------------------------------- config files

let fileJob = null;
let fileName = null;
let fileOriginal = '';
let fileIsNew = false;
let checkWatch = null;
const previewWatch = new Set();   // jobs this browser started a dry run of
const editor = $('file-editor');

const fileDirty = () => fileName !== null && editor.value !== fileOriginal;
function markDirty() {
  $('file-dirty').textContent = fileIsNew ? 'New file, not saved yet' : fileDirty() ? 'Unsaved changes' : '';
}
editor.addEventListener('input', markDirty);
editor.addEventListener('keydown', (e) => {
  if (e.key === 'Tab') {  // indent instead of leaving the editor
    e.preventDefault();
    editor.setRangeText('  ', editor.selectionStart, editor.selectionEnd, 'end');
    markDirty();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); saveFile(); }
});

async function openFiles(job, name) {
  fileJob = job || fileJob || status.jobs[0].name;
  openDrawer('files-drawer');
  await loadFileList(name);
}

async function loadFileList(pick) {
  renderTabs($('file-tabs'), fileJob, async (j) => {
    if (fileDirty() && !(await showAppConfirm('Discard unsaved changes?', { danger: true, okText: 'Discard' }))) return;
    fileJob = j;
    loadFileList();
  });
  const r = await api(`files/${fileJob}`);
  const sel = $('file-selector');
  sel.innerHTML = r.files.map((f) => `<option value="${esc(f.name)}">${esc(f.name)}</option>`).join('');
  $('btn-new-file').style.display = r.can_create ? '' : 'none';
  $('btn-delete-file').style.display = r.can_create ? '' : 'none';
  $('check-output-wrapper').style.display = 'none';
  const target = r.files.find((f) => f.name === pick) ? pick : r.files[0]?.name;
  if (target) {
    sel.value = target;
    await loadFile(target);
  } else {
    fileName = null;
    editor.value = '';
    editor.placeholder = r.can_create ? 'No files yet. Click New to start one from the template.' : 'No file yet.';
    markDirty();
  }
}

async function loadFile(name) {
  const r = await api(`files/${fileJob}/${encodeURIComponent(name)}`);
  fileName = name;
  fileIsNew = false;
  fileOriginal = r.text;
  $('btn-delete-file').style.display = name.startsWith(`${fileJob}/`) ? '' : 'none';
  editor.value = r.text;
  editor.scrollTop = 0;
  markDirty();
}

$('file-selector').addEventListener('change', async (e) => {
  if (fileDirty() && !(await showAppConfirm('Discard unsaved changes?', { danger: true, okText: 'Discard' }))) {
    e.target.value = fileName;
    return;
  }
  loadFile(e.target.value);
});

$('btn-new-file').addEventListener('click', async () => {
  const kind = fileJob === 'collections' ? 'collection' : 'playlist';
  const name = await showAppConfirm(`File name for the new list. Add it to a ${kind}'s sources in ${fileJob}.toml to use it.`, { prompt: 'my-list.md', okText: 'Create' });
  if (!name) return;
  const base = name.trim().replace(/^(collections|playlists|watchlists)\//, '');
  const clean = `${fileJob}/${base.endsWith('.md') ? base : `${base}.md`}`;
  const t = await api(`files/${fileJob}/_template`);
  const sel = $('file-selector');
  sel.insertAdjacentHTML('beforeend', `<option value="${esc(clean)}">${esc(clean)}</option>`);
  sel.value = clean;
  fileName = clean;
  fileIsNew = true;
  fileOriginal = '';
  editor.value = t.text;
  markDirty();
  editor.focus();
});

$('btn-delete-file').addEventListener('click', async () => {
  if (!fileName) return;
  if (fileIsNew) { loadFileList(); return; }
  if (!(await showAppConfirm(`Delete ${fileName}? Anything that uses it will report it missing until you take it out of ${fileJob}.toml.`, { danger: true, okText: 'Delete' }))) return;
  try {
    await api(`files/${fileJob}/${encodeURIComponent(fileName)}`, { method: 'DELETE' });
    showToast(`${fileName} deleted.`, 'success');
    fileName = null;
    loadFileList();
  } catch (e) {
    showToast(e.message, 'error');
  }
});

async function saveFile() {
  if (!fileName) return false;
  try {
    await api(`files/${fileJob}/${encodeURIComponent(fileName)}`, { method: 'PUT', body: { text: editor.value, create: fileIsNew } });
    fileOriginal = editor.value;
    fileIsNew = false;
    markDirty();
    showToast(`${fileName} saved.`, 'success');
    return true;
  } catch (e) {
    showToast(e.message, 'error');
    return false;
  }
}

$('btn-save-file').addEventListener('click', saveFile);
drawerGuards['files-drawer'] = {
  dirty: () => fileDirty() || (fileName !== null && fileIsNew),
  save: saveFile,
  discard: () => { editor.value = fileOriginal; fileIsNew = false; markDirty(); },
  what: () => `${fileName} has changes that aren't saved.`,
};
$('btn-check-file').addEventListener('click', async () => {
  if (fileDirty() || fileIsNew) {
    if (!(await saveFile())) return;
  }
  $('check-output').textContent = '';
  $('check-output-wrapper').style.display = '';
  checkWatch = fileJob;
  try {
    await api(`jobs/${fileJob}/run`, { method: 'POST', body: { action: 'check' } });
  } catch (e) {
    checkWatch = null;
    $('check-output').textContent = e.message;
  }
});

// Restore Previous: pick one of the copies kept before earlier saves; it opens in the editor
// as an unsaved change, so nothing is written until Save.
function pickVersion(name, versions) {
  return new Promise((resolve) => {
    const overlay = $('restore-overlay');
    const kb = (n) => (n < 1024 ? `${n} bytes` : `${(n / 1024).toFixed(1)} KB`);
    $('restore-intro').textContent = versions.length === 1 ? `${name} as it was before its last save:` : `${name} as it was before each of its last ${versions.length} saves, newest first:`;
    $('restore-list').innerHTML = versions.map((v, n) => `
      <label class="restore-row">
        <input type="radio" name="restore-pick" value="${n}" ${n === 0 ? 'checked' : ''}>
        <span class="restore-when">${esc(fmtTime(v.at))}</span>
        <span class="restore-size">${kb(v.size)}</span>
      </label>`).join('');
    overlay.style.display = 'flex';
    $('restore-ok').focus();
    const done = (v) => {
      overlay.style.display = 'none';
      $('restore-ok').removeEventListener('click', onOk);
      $('restore-cancel').removeEventListener('click', onCancel);
      overlay.removeEventListener('keydown', onKey);
      resolve(v);
    };
    const onOk = () => done(versions[Number($('restore-list').querySelector('input:checked')?.value ?? 0)]);
    const onCancel = () => done(null);
    const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onCancel(); } };
    $('restore-ok').addEventListener('click', onOk);
    $('restore-cancel').addEventListener('click', onCancel);
    overlay.addEventListener('keydown', onKey);
  });
}

$('btn-restore-file').addEventListener('click', async () => {
  if (!fileName) return;
  const q = `job=${encodeURIComponent(fileJob)}&name=${encodeURIComponent(fileName)}`;
  try {
    const { versions } = await api(`backups?${q}`);
    if (!versions.length) { showToast(`No earlier versions of ${fileName} yet. One is kept each time it's saved.`, 'info'); return; }
    if (fileDirty() && !(await showAppConfirm('Discard your unsaved changes and open an earlier version?', { danger: true, okText: 'Discard' }))) return;
    const v = await pickVersion(fileName, versions);
    if (!v) return;
    const { text } = await api(`backups?${q}&id=${encodeURIComponent(v.id)}`);
    editor.value = text;
    markDirty();
    showToast(`The version from ${fmtTime(v.at)} is in the editor. Save to bring it back.`, 'info');
  } catch (e) {
    showToast(e.message, 'error');
  }
});

$('btn-files-toggle').addEventListener('click', () => openFiles());
window.addEventListener('beforeunload', (e) => {
  if (Object.keys(drawerGuards).some(drawerDirty)) { e.preventDefault(); e.returnValue = ''; }
});

// ---------------------------------------------------------------- season calendar

// The year at a glance: a bar for each collection and playlist across the months it's on the
// server, so overlaps and empty stretches stand out. Windows are "MM-DD to MM-DD" (every year,
// may wrap the new year) or "YYYY-MM-DD to YYYY-MM-DD" (one time); blank is year round.
const DAY_MS = 86400000;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
let calYear = null;

function windowSpans(win, year) {
  if (!win) return [[Date.UTC(year, 0, 1), Date.UTC(year, 11, 31)]];
  const parts = String(win).trim().split(/\s+to\s+/);
  if (parts.length !== 2) return null;
  const dates = parts.map((p) => p.match(/^(?:(\d{4})-)?(\d{1,2})-(\d{1,2})$/));
  if (dates.some((m) => !m) || Boolean(dates[0][1]) !== Boolean(dates[1][1])) return null;
  const [a, b] = dates.map((m) => [m[1] ? Number(m[1]) : null, Number(m[2]) - 1, Number(m[3])]);
  const first = Date.UTC(year, 0, 1);
  const last = Date.UTC(year, 11, 31);
  const clip = (x, y) => (y < first || x > last ? [] : [[Math.max(x, first), Math.min(y, last)]]);
  if (a[0]) return clip(Date.UTC(a[0], a[1], a[2]), Date.UTC(b[0], b[1], b[2]));
  const start = Date.UTC(year, a[1], a[2]);
  const end = Date.UTC(year, b[1], b[2]);
  return start <= end ? [[start, end]] : [[first, end], [start, last]];   // wraps the new year
}

function renderCalendar() {
  const year = calYear;
  $('cal-year').textContent = year;
  const first = Date.UTC(year, 0, 1);
  const days = (Date.UTC(year + 1, 0, 1) - first) / DAY_MS;
  const pct = (t) => (((t - first) / DAY_MS) / days) * 100;
  const fmt = (t) => new Date(t).toLocaleDateString([], { month: 'short', day: 'numeric', timeZone: 'UTC' });
  const monthStarts = MONTHS.map((_, m) => pct(Date.UTC(year, m, 1)));
  const grid = `linear-gradient(to right, ${monthStarts.slice(1).map((x) => `transparent calc(${x}% - 1px), rgba(139, 92, 255, 0.18) calc(${x}% - 1px), rgba(139, 92, 255, 0.18) ${x}%, transparent ${x}%`).join(', ')})`;
  const t = status.today ? Date.parse(`${status.today}T00:00:00Z`) : null;
  const todayMark = t && new Date(t).getUTCFullYear() === year
    ? `<span class="cal-today" style="left:${pct(t) + 50 / days}%" title="Today, ${fmt(t)}"></span>` : '';
  const bar = (cls, [a, b], tip) => `<span class="cal-bar ${cls}" style="left:${pct(a)}%;width:${pct(b + DAY_MS) - pct(a)}%" title="${esc(tip)}"></span>`;
  const rows = [];
  const seasonal = [];
  for (const job of status.jobs.filter((j) => j.name !== 'genres')) {
    const lists = job.items.map((i, n) => ({ i, n, spans: windowSpans(i.window, year) }));
    lists.sort((x, y) => (x.i.window ? 0 : 1) - (y.i.window ? 0 : 1)
      || ((x.spans?.[0]?.[0] ?? Infinity) - (y.spans?.[0]?.[0] ?? Infinity))
      || x.i.name.localeCompare(y.i.name, undefined, { sensitivity: 'base' }));
    if (!lists.length) continue;
    rows.push(`<div class="cal-section">${esc(job.label)}</div>`);
    for (const { i, n, spans } of lists) {
      const cls = job.name === 'playlists' ? 'playlist' : 'collection';
      let track;
      if (!spans) {
        track = '<span class="cal-note bad">Bad season window</span>';
      } else if (!i.window) {
        track = bar(`${cls} year-round`, spans[0], `${i.name}: year round`);
      } else if (!spans.length) {
        track = `<span class="cal-note">Not on in ${year}</span>`;
      } else {
        seasonal.push(...spans);
        track = spans.map((sp) => bar(cls, sp, `${i.name}: ${fmt(sp[0])} to ${fmt(sp[1])}`)).join('');
      }
      rows.push(`<div class="cal-row" data-cal-job="${job.name}" data-cal-index="${n}" role="button" tabindex="0" title="Show the films on ${esc(i.name)}">
        <span class="cal-name">${esc(i.name)}${i.window ? `<small>${esc(i.window)}</small>` : '<small>Year round</small>'}</span>
        <span class="cal-track" style="background-image:${grid}">${track}${todayMark}</span>
      </div>`);
    }
  }
  // every seasonal window merged into one strip: the gaps are stretches with nothing seasonal on
  const merged = [];
  for (const [a, b] of seasonal.sort((x, y) => x[0] - y[0])) {
    const lastSpan = merged[merged.length - 1];
    if (lastSpan && a <= lastSpan[1] + DAY_MS) lastSpan[1] = Math.max(lastSpan[1], b);
    else merged.push([a, b]);
  }
  const head = `<div class="cal-row cal-head"><span class="cal-name"></span><span class="cal-track cal-months">${MONTHS.map((m, k) =>
    `<span style="left:${monthStarts[k]}%;width:${(k < 11 ? monthStarts[k + 1] : 100) - monthStarts[k]}%">${m}</span>`).join('')}</span></div>`;
  const any = `<div class="cal-row cal-any"><span class="cal-name">Any seasonal list<small>${merged.length ? 'Gaps have nothing seasonal on' : 'None this year'}</small></span>
    <span class="cal-track" style="background-image:${grid}">${merged.map((sp) => bar('any', sp, `Something seasonal is on: ${fmt(sp[0])} to ${fmt(sp[1])}`)).join('')}${todayMark}</span></div>`;
  $('calendar').innerHTML = rows.length ? head + any + rows.join('')
    : '<div class="empty-state"><i data-lucide="calendar-x"></i><span>No collections or playlists yet.</span></div>';
  $('calendar').querySelectorAll('[data-cal-job]').forEach((row) => {
    const open = () => openList(row.dataset.calJob, Number(row.dataset.calIndex));
    row.addEventListener('click', open);
    row.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
  });
  icons();
}

function openCalendar() {
  if (!status) return;
  calYear = Number((status.today || new Date().toISOString()).slice(0, 4));
  renderCalendar();
  openDrawer('calendar-drawer');
}

$('season-card').addEventListener('click', openCalendar);
$('season-card').addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCalendar(); } });
$('btn-cal-prev').addEventListener('click', () => { calYear -= 1; renderCalendar(); });
$('btn-cal-next').addEventListener('click', () => { calYear += 1; renderCalendar(); });

// ---------------------------------------------------------------- the whole config as one zip

// The zip is built on the server before the first byte comes back, which can take a while
// with a lot of artwork, so the button shows it's working instead of looking dead until the
// browser's download starts.
function setDownloadBusy(text) {
  const btn = $('btn-config-download');
  const busy = text != null;
  btn.classList.toggle('busy', busy);
  btn.setAttribute('aria-busy', String(busy));
  btn.querySelector('span').textContent = busy ? text : 'Download Config';
  const icon = btn.querySelector('.btn-icon');
  icon.outerHTML = `<i data-lucide="${busy ? 'loader-circle' : 'download'}" class="btn-icon${busy ? ' spin' : ''}"></i>`;
  icons();
}

const mb = (n) => (n / 1048576).toFixed(n < 10485760 ? 1 : 0);

$('btn-config-download').addEventListener('click', async (e) => {
  e.preventDefault();
  const btn = e.currentTarget;
  if (btn.classList.contains('busy')) return;
  setDownloadBusy('Building zip...');
  try {
    const res = await fetch(btn.getAttribute('href'), { cache: 'no-store' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    const total = Number(res.headers.get('Content-Length')) || 0;
    const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'staffpicked-config.zip';
    const chunks = [];
    let got = 0;
    const reader = res.body.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      got += value.length;
      setDownloadBusy(total ? `Downloading ${mb(got)} of ${mb(total)} MB` : `Downloading ${mb(got)} MB`);
    }
    const url = URL.createObjectURL(new Blob(chunks, { type: 'application/zip' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    showToast(`Saved ${name} (${mb(got)} MB).`, 'success');
  } catch (err) {
    showToast(`Couldn't download the config: ${err.message}`, 'error');
  } finally {
    setDownloadBusy(null);
  }
});

$('btn-config-restore').addEventListener('click', () => $('config-restore-file').click());
$('config-restore-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  const yes = await showAppConfirm(`Restore the config from ${file.name}? Its settings, configs, list files and artwork replace the ones here. The config as it is now is saved in backups/restores first.`, { okText: 'Restore', danger: true });
  if (!yes) return;
  try {
    const res = await fetch('api/config/restore', { method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    showToast(`Restored ${data.files} files. The config from before is in ${data.saved}.`, 'success');
    await openSettings();
    refresh();
    refreshEmby(true);
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// ---------------------------------------------------------------- first run

let setupShown = false;
let setupStep = 1;

function showSetupStep(n) {
  setupStep = n;
  document.querySelectorAll('#setup-overlay .setup-step').forEach((el) => { el.hidden = Number(el.dataset.step) !== n; });
  document.querySelectorAll('#setup-steps li').forEach((li) => {
    li.classList.toggle('active', Number(li.dataset.step) === n);
    li.classList.toggle('done', Number(li.dataset.step) < n);
  });
  $('btn-setup-back').hidden = n === 1;
  $('btn-setup-later').hidden = n !== 1;
  $('btn-setup-next').textContent = n === 3 ? 'Open the Store' : 'Next';
  const first = document.querySelector(`#setup-overlay .setup-step[data-step="${n}"] input:not([type="checkbox"]), #setup-overlay .setup-step[data-step="${n}"] select`);
  first?.focus();
}

function openSetup() {
  setupShown = true;
  // a password set already (say, before the server) stays; the step only says so
  const hasPw = Boolean(status?.auth);
  $('setup-password-fields').hidden = hasPw;
  $('setup-no-password').closest('label').hidden = hasPw;
  $('setup-password-intro').textContent = hasPw
    ? 'A password is already set, so this step is done.'
    : 'Until it has a password, StaffPicked only opens from your local network.';
  $('setup-overlay').style.display = 'flex';
  showSetupStep(1);
  icons();
}

const setupServer = () => ({ type: $('setup-type').value, url: $('setup-url').value.trim(), key: $('setup-key').value.trim() });

async function testSetupServer() {
  const out = $('setup-test-result');
  const server = setupServer();
  if (!server.url || !server.key) { out.textContent = 'Enter the URL and API key first.'; out.className = 'field-hint bad'; return false; }
  out.textContent = 'Testing…';
  out.className = 'field-hint';
  try {
    const r = await api('setup/test', { method: 'POST', body: { server } });
    out.textContent = r.ok ? `Connected${r.server ? ` to ${r.server}` : ''}${r.version ? ` v${r.version}` : ''}.` : r.error;
    out.className = `field-hint ${r.ok ? 'good' : 'bad'}`;
    return r.ok;
  } catch (e) {
    out.textContent = e.message;
    out.className = 'field-hint bad';
    return false;
  }
}

$('btn-setup-test').addEventListener('click', testSetupServer);
$('btn-setup-back').addEventListener('click', () => showSetupStep(setupStep - 1));
$('btn-setup-later').addEventListener('click', async () => {
  $('setup-overlay').style.display = 'none';
  await api('setup/skip', { method: 'POST', body: {} }).catch(() => {});
  showToast('Set up a server any time from the badge at the top, or in Settings.', 'info');
});
$('setup-no-password').addEventListener('change', (e) => {
  ['setup-password', 'setup-password2'].forEach((id) => { $(id).disabled = e.target.checked; });
});
$('btn-setup-next').addEventListener('click', async () => {
  const btn = $('btn-setup-next');
  if (setupStep === 1) {
    btn.disabled = true;
    const ok = await testSetupServer();
    btn.disabled = false;
    if (ok) showSetupStep(2);
    return;
  }
  if (setupStep === 2) { showSetupStep(3); return; }
  let password = '';
  if (!status?.auth && !$('setup-no-password').checked) {
    password = $('setup-password').value;
    if (password.length < 8) { showToast('Use at least 8 characters, or tick Skip.', 'error'); $('setup-password').focus(); return; }
    if (password !== $('setup-password2').value) { showToast("The passwords don't match.", 'error'); $('setup-password2').focus(); return; }
  }
  btn.disabled = true;
  try {
    await api('setup', { method: 'POST', body: {
      server: setupServer(), password,
      keys: { MDBLIST_API_KEY: $('setup-mdblist').value.trim(), TRAKT_CLIENT_ID: $('setup-trakt').value.trim() },
    } });
    $('setup-overlay').style.display = 'none';
    ['setup-key', 'setup-mdblist', 'setup-trakt', 'setup-password', 'setup-password2'].forEach((id) => { $(id).value = ''; });
    showToast('All set. The first sync is running.', 'success');
    await refresh();
    refreshEmby(true);
  } catch (e) {
    showToast(e.message, 'error');
    if (/connect|URL|key|type/i.test(e.message)) showSetupStep(1);
  } finally {
    btn.disabled = false;
  }
});

// ---------------------------------------------------------------- start

icons();
refresh().then(() => {
  connectEvents();
  refreshEmby();
});
setInterval(refresh, 60000);
setInterval(refreshEmby, 60000);
