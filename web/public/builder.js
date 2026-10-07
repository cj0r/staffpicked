'use strict';
// Building collections, playlists and genre artwork in forms, editing a list file's films, and clearing out
// old artwork. Uses the helpers in app.js. Every delete goes through review() first.

const KIND = { collections: 'collection', playlists: 'playlist', genres: 'genre' };
const IMAGE_HINT = 'Upload one from this device, pick a file already in the config folder (images/name.jpg), paste a web link (https://…) or a path on the server (/media/art/poster.jpg), or use tmdb:movie/<id>, tmdb:/<file>.jpg, fanart:movie/<id>, mediux:movie/<id> or a mediux.pro set link. A ThePosterDB poster is added by hand: download it from theposterdb.com, then upload it here. In Docker, a server path must be inside a folder mounted into the container.';
const LOCAL_IMAGE = /^(images|collections|playlists|watchlists)\/[^?#]+\.(jpe?g|png|webp)$/i;
// The media servers by name: "Emby", "Emby and Jellyfin". only = just these (an entry's servers).
const serverNames = () => (status?.servers || []).map((s) => s.name);
const joinNames = (names) => (names.length < 2 ? names[0] || 'the media server' : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`);
const serverName = (only) => joinNames(only?.length ? only : serverNames());

// Which servers an entry goes to: a box per server, none ticked = every server. Shown once
// there's more than one server, or when the entry already names some.
function serversField(e) {
  const names = serverNames();
  const mine = (e.servers || []).map((s) => s.toLowerCase());
  if (names.length < 2 && !mine.length) return '';
  const extra = (e.servers || []).filter((s) => !names.some((n) => n.toLowerCase() === s.toLowerCase()));
  return `
    <div class="form-section full-width"><h4>Servers</h4></div>
    <div class="form-group full-width">
      <div class="server-checks">
        ${[...names, ...extra].map((n) => `<label class="check-label"><input type="checkbox" data-server-pick="${esc(n)}" ${mine.includes(n.toLowerCase()) ? 'checked' : ''}> ${esc(n)}${extra.includes(n) ? ' (not set up)' : ''}</label>`).join('')}
      </div>
      <span class="field-hint">Tick the servers it goes to. None ticked = every server${names.length > 1 ? ` (${esc(joinNames(names))})` : ''}, including ones you add later.</span>
    </div>`;
}

function fmtSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

// ---------------------------------------------------------------- review before deleting

// Shows exactly what will go, and resolves {ok, option} only when the person approves.
function review({ title, intro = '', items = [], option = null, foot = '', okText = 'Delete', danger = true }) {
  return new Promise((resolve) => {
    const overlay = $('review-overlay');
    const ok = $('review-ok');
    const cancel = $('review-cancel');
    $('review-title').textContent = title;
    $('review-intro').textContent = intro;
    $('review-list').innerHTML = items.map((i) => `<li>${esc(i)}</li>`).join('');
    $('review-option').style.display = option ? '' : 'none';
    $('review-option-box').checked = Boolean(option?.checked);
    $('review-option-text').textContent = option?.text || '';
    $('review-foot').textContent = foot;
    ok.textContent = okText;
    ok.className = `btn ${danger ? 'btn-danger' : 'btn-primary'}`;
    overlay.style.display = 'flex';
    cancel.focus();   // the safe choice has focus; Enter alone never deletes
    const done = (yes) => {
      overlay.style.display = 'none';
      ok.removeEventListener('click', onOk);
      cancel.removeEventListener('click', onCancel);
      overlay.removeEventListener('keydown', onKey);
      resolve({ ok: yes, option: $('review-option-box').checked });
    };
    const onOk = () => done(true);
    const onCancel = () => done(false);
    const onKey = (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onCancel(); } };
    ok.addEventListener('click', onOk);
    cancel.addEventListener('click', onCancel);
    overlay.addEventListener('keydown', onKey);
  });
}

function showNotes(el, problems = [], warnings = []) {
  el.innerHTML = [
    ...problems.map((p) => `<div class="builder-note bad"><i data-lucide="alert-circle"></i><span>${esc(p)}</span></div>`),
    ...warnings.map((w) => `<div class="builder-note warn"><i data-lucide="alert-triangle"></i><span>${esc(w)}</span></div>`),
  ].join('');
  icons();
}

// ---------------------------------------------------------------- one collection or playlist

let entryJob = null;
let entryIndex = null;
let entryData = null;      // the builder's view of the config file
let entrySnapshot = '';

function listField(key, values, placeholder, { image = false, single = false } = {}) {
  const rows = (values.length ? values : ['']).map((v) => `
    <div class="list-row">
      ${image ? '<img class="art-thumb" alt="" hidden>' : ''}
      <input type="text" data-list="${key}" value="${esc(v)}" placeholder="${esc(placeholder)}" autocomplete="off" ${image ? 'list="image-files"' : ''} ${single ? `id="f-${key}"` : ''}>
      ${image ? '<button type="button" class="btn btn-secondary btn-xs" data-upload title="Upload an image from this device"><i data-lucide="upload"></i><span>Upload</span></button>' : ''}
      ${single ? '' : '<button type="button" class="btn btn-icon-only" data-unlist title="Remove"><i data-lucide="x"></i></button>'}
    </div>`).join('');
  return `<div class="list-field" data-field="${key}">${rows}</div>`;
}

// The artwork fields every kind has; genres also get a thumb.
function artworkFields(e, kind) {
  return `
    <div class="form-section full-width"><h4>Artwork</h4></div>
    <div class="form-group full-width">
      <label for="f-poster">Poster</label>
      ${listField('poster', e.poster ? [e.poster] : [], 'images/poster.jpg or https://…', { image: true, single: true })}
      ${kind === 'genre' ? '<span class="field-hint">The genre\'s main image: its card on Jellyfin and Emby.</span>' : ''}
    </div>
    ${kind === 'genre' ? `
    <div class="form-group full-width">
      <label for="f-thumb">Thumb</label>
      ${listField('thumb', e.thumb ? [e.thumb] : [], 'images/thumb.jpg, https://… or fanart:movie/<id>', { image: true, single: true })}
      <span class="field-hint">A wide 16:9 card, which Emby shows in its genre rows when it's set.</span>
    </div>` : ''}
    <div class="form-group full-width">
      <label>Backdrops</label>
      ${listField('backdrops', e.backdrops || [], 'images/backdrop.jpg, https://… or tmdb:/file.jpg', { image: true })}
      <div class="list-actions">
        <button type="button" class="btn btn-secondary btn-xs" data-addlist="backdrops"><i data-lucide="plus"></i><span>Add Backdrop</span></button>
      </div>
      <span class="field-hint">${esc(IMAGE_HINT)}</span>
      <datalist id="image-files">${(entryData.images || []).map((i) => `<option value="${esc(i)}">`).join('')}</datalist>
    </div>`;
}

// A genre is only artwork: its name has to match a genre already on the server.
function renderGenreForm(e) {
  const isNew = entryIndex === null;
  $('entry-title').textContent = isNew ? 'New Genre Artwork' : e.name || '(no name)';
  $('entry-fields').innerHTML = `
    <div class="form-group full-width">
      <label for="f-name">Genre</label>
      <input type="text" id="f-name" value="${esc(e.name || '')}" autocomplete="off" list="server-genres" required>
      <datalist id="server-genres"></datalist>
      <span class="field-hint" id="genre-hint">The genre's name on ${serverName()}, as a film's genres show it. ${serverName()} makes its genres from your films' metadata, so StaffPicked only sets their artwork and never creates or deletes one.</span>
    </div>
    ${artworkFields(e, 'genre')}
    ${serversField(e)}`;
  showNotes($('entry-notes'));
  $('btn-entry-delete').style.display = isNew ? 'none' : '';
  updateEntryButtons();
  wireEntryForm();
  icons();
  entrySnapshot = JSON.stringify(readEntryForm());
  fillServerGenres();
}

// Suggest the server's own genre names, so the name matches exactly.
async function fillServerGenres() {
  try {
    const r = await api('genres');
    const list = $('server-genres');
    if (!list) return;
    list.innerHTML = r.genres.map((g) => `<option value="${esc(g)}">`).join('');
    const taken = new Set(entryData.entries.filter((x) => x.index !== entryIndex).map((x) => (x.name || '').toLowerCase()));
    const free = r.genres.filter((g) => !taken.has(g.toLowerCase()));
    $('genre-hint').textContent += ` ${r.genres.length} genres on ${r.server}${free.length < r.genres.length ? `, ${free.length} without StaffPicked artwork yet` : ''}; start typing to pick one.`;
  } catch (err) {
    if ($('genre-hint')) $('genre-hint').textContent += ` (Couldn't list the server's genres: ${err.message})`;
  }
}

function renderEntryForm(e) {
  const kind = KIND[entryJob];
  if (kind === 'genre') { renderGenreForm(e); return; }
  const isNew = entryIndex === null;
  const [from, to] = (e.active || '').split(/\s+to\s+/);
  const wl = entryData.watchlists;
  const choice = (v, cur) => (v === cur ? 'selected' : '');
  const iw = e.include_watched === undefined ? '' : String(e.include_watched);
  const defaults = entryData.settings || {};
  $('entry-title').textContent = isNew ? `New ${kind[0].toUpperCase()}${kind.slice(1)}` : e.name || '(no name)';
  $('entry-fields').innerHTML = `
    <div class="form-group full-width">
      <label for="f-name">Name</label>
      <input type="text" id="f-name" value="${esc(e.name || '')}" autocomplete="off" required>
      <span class="field-hint">As it shows on ${serverName()}. ${isNew ? '' : 'Rename it here and the next sync replaces the old one on the server with the new name.'}</span>
    </div>
    <div class="form-section full-width"><h4>What's In It</h4></div>
    ${isNew ? `
    <div class="form-group full-width">
      <label class="check-label"><input type="checkbox" id="f-newlist" ${kind === 'playlist' ? 'checked' : ''}> Start a new list of your own for it</label>
      <input type="text" id="f-newlist-desc" placeholder="One line on what the list is${kind === 'playlist' ? ' and how it\'s ordered' : ''} (optional)" autocomplete="off">
      <span class="field-hint">Creates ${entryJob}/&lt;name&gt;.md. After saving, add films to it by title.${kind === 'collection' ? ' Leave it off for a collection that follows an MDBList or Trakt list.' : ''}</span>
    </div>
    <div class="form-group full-width">
      <label for="f-paste">Or paste a whole list</label>
      <textarea id="f-paste" class="paste-list" rows="5" spellcheck="false" placeholder="# 80s Sci-Fi&#10;&#10;- tt0084787 | The Thing (1982)&#10;- tt0080749 | The Fog (1980)"></textarea>
      <span class="field-hint">Paste a .md list, one film per line as "- tt0084787 | Title (Year) notes", top to bottom in play order. It's saved as ${entryJob}/&lt;name&gt;.md, and its "# title" fills in the name if that's blank.</span>
    </div>` : ''}
    <div class="form-group full-width">
      <label>Sources</label>
      ${listField('sources', e.sources || [], `https://mdblist.com/lists/user/list, https://trakt.tv/users/user/lists/list or ${entryJob}/file.md`)}
      <div class="list-actions">
        <button type="button" class="btn btn-secondary btn-xs" data-addlist="sources"><i data-lucide="plus"></i><span>Add List Link</span></button>
        ${wl.length ? `<select class="profile-select" id="f-add-watchlist" aria-label="Add one of your lists">
          <option value="">Add one of your lists…</option>${wl.map((w) => `<option value="${esc(w)}">${esc(w)}</option>`).join('')}</select>` : ''}
      </div>
      <span class="field-hint">Items from every source go in, in order. MDBList and Trakt links need their keys in Settings.</span>
    </div>
    <div class="form-section full-width"><h4>Season</h4></div>
    <div class="form-group full-width">
      <label class="check-label"><input type="checkbox" id="f-allyear" ${e.active ? '' : 'checked'}> All year</label>
    </div>
    <div class="form-group season-field">
      <label for="f-from">From</label>
      <input type="text" id="f-from" value="${esc(from || '')}" placeholder="09-25" autocomplete="off">
    </div>
    <div class="form-group season-field">
      <label for="f-to">To</label>
      <input type="text" id="f-to" value="${esc(to || '')}" placeholder="10-31" autocomplete="off">
    </div>
    <span class="field-hint full-width season-field">MM-DD repeats every year and may wrap the new year (11-30 to 01-01). YYYY-MM-DD on both runs once. Outside the window it is taken off the server and comes back when the window opens.</span>
    ${artworkFields(e, kind)}
    ${kind === 'collection' ? `
    <div class="form-section full-width"><h4>Details</h4></div>
    <div class="form-group full-width">
      <label for="f-description">Description</label>
      <input type="text" id="f-description" value="${esc(e.description || '')}" autocomplete="off">
    </div>
    <div class="form-group">
      <label for="f-sort">Sort name</label>
      <input type="text" id="f-sort" value="${esc(e.sort_name || '')}" placeholder="0 80s Horror" autocomplete="off">
      <span class="field-hint">Where it sorts on the server. Blank = by name.</span>
    </div>
    <div class="form-group">
      <label for="f-order">Display order</label>
      <select id="f-order">
        <option value="" ${choice('', e.display_order || '')}>Leave as set on the server</option>
        <option value="release_date" ${choice('release_date', e.display_order)}>Release date</option>
        <option value="sort_name" ${choice('sort_name', e.display_order)}>Sort name</option>
      </select>
      <span class="field-hint">The order of its films on Emby and Jellyfin until a viewer picks another sort.</span>
    </div>` : `
    <div class="form-section full-width"><h4>Viewers</h4></div>
    <div class="form-group">
      <label for="f-watched">Films already watched</label>
      <select id="f-watched">
        <option value="" ${choice('', iw)}>Default (${defaults.include_watched ? 'keep them' : 'drop them'})</option>
        <option value="false" ${choice('false', iw)}>Drop them</option>
        <option value="true" ${choice('true', iw)}>Keep them</option>
      </select>
    </div>
    <div class="form-group">
      <label for="f-share">Who can see it</label>
      <select id="f-share">
        <option value="" ${choice('', e.share || '')}>Default (${defaults.share === 'private' ? 'owner only' : 'everyone'})</option>
        <option value="view" ${choice('view', e.share)}>Everyone</option>
        <option value="private" ${choice('private', e.share)}>Owner only</option>
      </select>
    </div>
    <div class="form-group full-width">
      <label>Watched by</label>
      <div class="user-checks" id="f-watchedby" data-users="${esc(JSON.stringify(e.watched_by || []))}">
        ${(e.watched_by || []).map((u) => userCheck(u, true)).join('')}
        <span class="field-hint" id="watchedby-loading">Loading ${serverName(e.servers)}'s users…</span>
      </div>
      <span class="field-hint" id="watchedby-hint">Tick the users whose viewing drops a film from this playlist. None ticked = the setting in Settings.</span>
    </div>`}
    ${serversField(e)}`;
  showNotes($('entry-notes'));
  $('btn-entry-delete').style.display = isNew ? 'none' : '';
  updateEntryButtons();
  wireEntryForm();
  icons();
  entrySnapshot = JSON.stringify(readEntryForm());
  if ($('f-watchedby')) fillServerUsers(e);
}

function userCheck(name, checked, note = '') {
  return `<label class="check-label"><input type="checkbox" data-watcher="${esc(name)}" ${checked ? 'checked' : ''}> ${esc(name)}${note ? ` <span class="user-note">(${esc(note)})</span>` : ''}</label>`;
}

// Offer the users on the servers this playlist goes to, as one ticked list. Watched by is one
// setting for every server, so a user only some servers have says which.
async function fillServerUsers(e) {
  const box = $('f-watchedby');
  try {
    const r = await api('users');
    if ($('f-watchedby') !== box) return;   // the form was redrawn meanwhile
    const want = (e.servers || []).map((s) => s.toLowerCase());
    const servers = r.servers.filter((s) => !want.length || want.includes(s.name.toLowerCase()));
    const found = new Map();   // lower-cased name -> {name, on: [server]}
    servers.forEach((s) => s.users.forEach((u) => {
      const k = u.toLowerCase();
      if (!found.has(k)) found.set(k, { name: u, on: [] });
      found.get(k).on.push(s.name);
    }));
    const wasClean = JSON.stringify(readEntryForm()) === entrySnapshot;
    const ticked = new Set([...box.querySelectorAll('[data-watcher]:checked')].map((i) => i.dataset.watcher.toLowerCase()));
    const kept = JSON.parse(box.dataset.users || '[]').filter((u) => !found.has(u.toLowerCase()));
    const many = servers.length > 1;
    box.innerHTML = [...found.values()].sort((a, b) => a.name.localeCompare(b.name))
      .map((u) => userCheck(u.name, ticked.has(u.name.toLowerCase()), many && u.on.length < servers.length ? `${joinNames(u.on)} only` : ''))
      .concat(kept.map((u) => userCheck(u, ticked.has(u.toLowerCase()), `not on ${servers.length ? joinNames(servers.map((s) => s.name)) : 'the server'}`)))
      .join('') || '<span class="field-hint">No users found.</span>';
    if (r.problems.length) $('watchedby-hint').textContent += ` (${r.problems.join('; ')})`;
    if (wasClean) entrySnapshot = JSON.stringify(readEntryForm());
  } catch (err) {
    if ($('f-watchedby') !== box) return;
    $('watchedby-loading')?.remove();
    $('watchedby-hint').textContent += ` (Couldn't list the server's users: ${err.message})`;
  }
}

// Fill the name from a pasted list's "# title", and save the paste as the new list.
function pastedList() {
  const text = $('f-paste')?.value || '';
  if (!text.trim()) return;
  $('f-newlist').checked = true;
  const title = text.split(/\r?\n/).find((l) => /^#\s+\S/.test(l));
  if (title && !$('f-name').value.trim()) $('f-name').value = title.replace(/^#\s+/, '').trim();
}

function seasonToggle() {
  if (!$('f-allyear')) return;   // genres have no season
  const allYear = $('f-allyear').checked;
  document.querySelectorAll('#entry-fields .season-field').forEach((el) => { el.style.display = allYear ? 'none' : ''; });
}

function updateEntryButtons() {
  const sources = [...document.querySelectorAll('[data-list="sources"]')].map((i) => i.value.trim());
  const lists = sources.filter((s) => /^(collections|playlists|watchlists)\//.test(s) && s.endsWith('.md'));
  $('btn-entry-films').style.display = entryIndex !== null && lists.length ? '' : 'none';
  // genres are named after the server's own, so a copy of one has nothing to be
  $('btn-entry-duplicate').style.display = entryIndex !== null && KIND[entryJob] !== 'genre' ? '' : 'none';
  $('btn-entry-films').dataset.file = lists[0] || '';
}

function wireEntryForm() {
  const form = $('entry-fields');
  form.querySelectorAll('[data-unlist]').forEach((b) => b.onclick = () => {
    const field = b.closest('.list-field');
    if (field.children.length > 1) b.closest('.list-row').remove();
    else field.querySelector('input').value = '';
    updateEntryButtons();
  });
  form.querySelectorAll('[data-addlist]').forEach((b) => b.onclick = () => addListRow(b.dataset.addlist, ''));
  const addWl = $('f-add-watchlist');
  if (addWl) addWl.onchange = () => {
    if (addWl.value) {
      addListRow('sources', addWl.value);
      if ($('f-newlist')) $('f-newlist').checked = false;   // the list already exists
    }
    addWl.value = '';
  };
  if ($('f-paste')) $('f-paste').oninput = pastedList;
  form.querySelectorAll('[data-upload]').forEach((b) => b.onclick = () => {
    uploadTarget = b.closest('.list-row').querySelector('input');
    $('upload-input').value = '';
    $('upload-input').click();
  });
  if ($('f-allyear')) $('f-allyear').onchange = seasonToggle;
  seasonToggle();
  form.oninput = () => { updateEntryButtons(); updateThumbs(); };
  updateThumbs();
}

// A small preview for images in the config folder (links and server paths aren't fetched here).
function updateThumbs() {
  document.querySelectorAll('#entry-fields .art-thumb').forEach((img) => {
    const v = img.parentElement.querySelector('input').value.trim();
    const local = LOCAL_IMAGE.test(v) && !v.includes('..');
    const src = local ? `api/images/file?name=${encodeURIComponent(v)}` : '';
    if (img.dataset.src !== src) {
      img.dataset.src = src;
      img.hidden = !local;
      img.onerror = () => { img.hidden = true; };   // not there (yet)
      if (src) img.src = src; else img.removeAttribute('src');
    }
  });
}

let uploadTarget = null;
$('upload-input').addEventListener('change', async (ev) => {
  const file = ev.target.files[0];
  const target = uploadTarget;
  if (!file || !target) return;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    showToast('Pick a JPEG, PNG or WebP image.', 'error');
    return;
  }
  if (file.size > 30_000_000) {
    showToast('That image is over 30 MB.', 'error');
    return;
  }
  showToast(`Uploading ${file.name}…`, 'info');
  try {
    const res = await fetch(`api/images/upload?name=${encodeURIComponent(file.name)}`, {
      method: 'POST', headers: { 'Content-Type': file.type }, body: file,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    target.value = data.name;
    entryData.images = [...(entryData.images || []), data.name];
    $('image-files')?.insertAdjacentHTML('beforeend', `<option value="${esc(data.name)}">`);
    updateThumbs();
    showToast(`Uploaded as ${data.name}. Save to use it.`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
});

function addListRow(key, value) {
  const field = document.querySelector(`.list-field[data-field="${key}"]`);
  const empty = [...field.querySelectorAll('input')].find((i) => !i.value.trim());
  if (empty) {
    empty.value = value;
    empty.focus();
  } else {
    const row = field.querySelector('.list-row').cloneNode(true);
    row.querySelector('input').value = value;
    row.querySelector('.art-thumb')?.setAttribute('hidden', '');
    field.appendChild(row);
    row.querySelector('input').focus();
  }
  wireEntryForm();
  updateEntryButtons();
}

function readEntryForm() {
  const val = (id) => ($(id) ? $(id).value.trim() : '');
  const list = (key) => [...document.querySelectorAll(`[data-list="${key}"]`)].map((i) => i.value.trim()).filter(Boolean);
  const servers = [...document.querySelectorAll('#entry-fields [data-server-pick]:checked')].map((i) => i.dataset.serverPick);
  if (KIND[entryJob] === 'genre') return { name: val('f-name'), poster: val('f-poster'), thumb: val('f-thumb'), backdrops: list('backdrops'), servers };
  const e = {
    name: val('f-name'),
    sources: list('sources'),
    active: $('f-allyear').checked ? '' : `${val('f-from')} to ${val('f-to')}`,
    poster: val('f-poster'),
    backdrops: list('backdrops'),
    servers,
  };
  if (KIND[entryJob] === 'collection') {
    e.description = val('f-description');
    e.sort_name = val('f-sort');
    e.display_order = val('f-order');
  } else {
    e.include_watched = val('f-watched') === '' ? null : val('f-watched') === 'true';
    e.share = val('f-share');
    e.watched_by = [...document.querySelectorAll('#f-watchedby [data-watcher]:checked')].map((i) => i.dataset.watcher);
  }
  return e;
}

drawerGuards['entry-drawer'] = {
  dirty: () => entryJob !== null && JSON.stringify(readEntryForm()) !== entrySnapshot,
  save: () => saveEntry(true),
  discard: () => { entryJob = null; },
  what: () => `${$('entry-title').textContent} has changes that aren't saved.`,
};

async function openEntry(job, index) {
  let data;
  try {
    data = await api(`builder/${job}`);
  } catch (err) {
    showToast(err.message, 'error');
    return;
  }
  if (!data.editable) {
    showToast(`${job}.toml is laid out in a way the builder can't edit safely, so it opens as text.`, 'warning');
    openFiles(job);
    return;
  }
  if (index !== null && !data.entries[index]) {
    showToast('That entry changed meanwhile. The list is refreshed.', 'warning');
    refresh();
    return;
  }
  entryJob = job;
  entryIndex = index;
  entryData = data;
  openDrawer('entry-drawer');
  renderEntryForm(index === null ? {} : data.entries[index]);
  $('f-name').focus();
}

$('btn-new-entry').addEventListener('click', async () => {
  const job = status.jobs.find((j) => j.name === listTab) || status.jobs[0];
  openEntry(job.name, null);
});

$('entry-form').addEventListener('submit', (ev) => {
  ev.preventDefault();
  saveEntry();
});

// Saves the form; true once saved. Closing the drawer saves without opening the new list's films.
async function saveEntry(closing = false) {
  const e = readEntryForm();
  const newList = $('f-newlist')?.checked;
  const genre = KIND[entryJob] === 'genre';
  if (!e.name) { showNotes($('entry-notes'), [genre ? 'Pick the genre.' : 'Give it a name.']); return false; }
  if (genre && !(e.poster || e.thumb || e.backdrops.length)) { showNotes($('entry-notes'), ['Set at least one image.']); return false; }
  if (!genre && !$('f-allyear').checked && !($('f-from').value.trim() && $('f-to').value.trim())) {
    showNotes($('entry-notes'), ['Fill in both season dates, or tick All year.']);
    return false;
  }
  if (!genre && !e.sources.length && !newList) { showNotes($('entry-notes'), ['Add at least one source.']); return false; }
  const pasted = $('f-paste')?.value || '';
  if (pasted.trim() && !newList) {
    showNotes($('entry-notes'), ['Tick "Start a new list of your own for it" to save the pasted list, or clear the paste.']);
    return false;
  }
  const body = { entry: e, version: entryData.version };
  if (newList) body.new_watchlist = { title: e.name, description: $('f-newlist-desc').value.trim(), text: pasted };
  const isNew = entryIndex === null;
  try {
    const r = await api(`builder/${entryJob}${isNew ? '' : `/${entryIndex}`}`, { method: isNew ? 'POST' : 'PUT', body });
    entryData = await api(`builder/${entryJob}`);
    entryIndex = r.index;
    renderEntryForm(entryData.entries[r.index]);
    showNotes($('entry-notes'), [], r.warnings);
    showToast(`${e.name} saved. ${r.warnings.length ? 'See the notes in the form.' : genre ? 'The next sync sets its artwork.' : r.renamed ? `The next sync builds it and removes "${r.renamed}" from the server.` : 'The next sync builds it.'}`, r.warnings.length ? 'warning' : 'success');
    refresh();
    if (r.watchlist && !closing) openWatchlist(r.watchlist);
    return true;
  } catch (err) {
    const d = err.data || {};
    showNotes($('entry-notes'), d.problems || [err.message], d.warnings || []);
    showToast(err.message, 'error');
    return false;
  }
}

// Duplicate: the same settings as a new, unsaved entry called "Copy of ...", using the same
// lists, for a seasonal variant or a second take. Nothing is written until it's saved.
$('btn-entry-duplicate').addEventListener('click', () => {
  if (drawerDirty('entry-drawer')) { showToast('Save your changes first.', 'warning'); return; }
  const e = entryData.entries[entryIndex];
  const taken = new Set(entryData.entries.map((x) => (x.name || '').toLowerCase()));
  let name = `Copy of ${e.name}`;
  for (let n = 2; taken.has(name.toLowerCase()); n += 1) name = `Copy ${n} of ${e.name}`;
  entryIndex = null;
  renderEntryForm({ ...e, name });
  if ($('f-newlist')) $('f-newlist').checked = false;   // it keeps the original's sources
  entrySnapshot = '';     // unsaved, so closing asks first
  $('f-name').focus();
  $('f-name').select();
  showToast(`Copied ${e.name}. Rename it, change what you like, and save.`, 'info');
});

$('btn-entry-films').addEventListener('click', () => {
  if (drawerDirty('entry-drawer')) { showToast('Save your changes first.', 'warning'); return; }
  openWatchlist($('btn-entry-films').dataset.file);
});

$('btn-entry-delete').addEventListener('click', async () => {
  const e = entryData.entries[entryIndex];
  const kind = KIND[entryJob];
  const job = entryJob;
  const config = `${job}.toml`;
  const files = [...(e.sources || []).filter((s) => s.endsWith('.md')), ...[e.poster, e.thumb].filter(Boolean), ...(e.backdrops || [])]
    .filter((f) => !/^[a-z]+:/i.test(f));
  const kept = files.length ? `Its files are kept (${files.join(', ')}); clear them out under Artwork or Config Files.` : '';
  const r = await review(kind === 'genre' ? {
    title: `Delete the artwork for the genre "${e.name}"?`,
    intro: 'This will:',
    items: [`Remove "${e.name}" and its artwork settings from ${config}`],
    option: { text: `Also take the artwork StaffPicked set off "${e.name}" on ${serverName(e.servers)} now. The genre itself and your library are not touched.`, checked: true },
    foot: `If you untick that, the artwork stays on ${serverName(e.servers)} until you change it there. ${kept}`,
  } : {
    title: `Delete the ${kind} "${e.name}"?`,
    intro: 'This will:',
    items: [`Remove "${e.name}" and its settings from ${config}`],
    option: { text: `Also delete "${e.name}" from ${serverName(e.servers)} now. The films and shows in your library are not touched.`, checked: true },
    foot: `If you untick that, it stays on ${serverName(e.servers)} until you delete it there. ${kept}`,
  });
  if (!r.ok) return;
  const q = `version=${encodeURIComponent(entryData.version)}${r.option ? '&server=1' : ''}`;
  try {
    const out = await api(`builder/${job}/${entryIndex}?${q}`, { method: 'DELETE' });
    entryJob = null;   // nothing left to save
    closeDrawer();
    if (out.pending) {
      showToast(kind === 'genre' ? `Taking StaffPicked's artwork off "${out.name}". Its entry is deleted when that finishes.`
        : `Removing "${out.name}" from ${serverName(e.servers)}. Its entry is deleted when that finishes.`, 'info');
      showLogs(job);
    } else {
      showToast(`"${e.name}" deleted from ${config}.`, 'success');
    }
    refresh();
  } catch (err) {
    showToast(err.message, 'error');
  }
});

// ---------------------------------------------------------------- a list file's films

let wl = null;          // {name, title, rows, version}
let wlDirty = false;
let dragFrom = null;

drawerGuards['watchlist-drawer'] = {
  dirty: () => wl !== null && wlDirty,
  save: saveWatchlist,
  discard: () => setWlDirty(false),
  what: () => `${wl.name} has changes that aren't saved.`,
};

async function openWatchlist(name) {
  try {
    const r = await api(`watchlist?name=${encodeURIComponent(name)}`);
    wl = r;
    wlDirty = false;
    openDrawer('watchlist-drawer');
    $('search-results').innerHTML = '';
    renderFilms();
    $('search-q').focus();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function setWlDirty(v = true) {
  wlDirty = v;
  $('watchlist-dirty').textContent = v ? 'Unsaved changes' : '';
}

// Row indexes of the films, in play order. Other lines (the title, the description) stay put.
const shown = () => wl.rows.map((r, i) => i).filter((i) => wl.rows[i].kind === 'film');
const blank = (r) => r && r.kind === 'text' && !r.text.trim();

function moveRow(from, to) {
  const [row] = wl.rows.splice(from, 1);
  wl.rows.splice(to > from ? to - 1 : to, 0, row);
  setWlDirty();
  renderFilms();
}

function renderFilms() {
  const films = wl.rows.filter((r) => r.kind === 'film');
  $('watchlist-title').textContent = wl.title || wl.name;
  $('watchlist-sub').textContent = `${wl.name} · ${films.length} film${films.length === 1 ? '' : 's'}${wl.name.startsWith('collections/') ? '' : ', played from the top down'}` +
    (wl.used_by.length ? ` · used by ${wl.used_by.join(', ')}` : ' · not used yet');
  let n = 0;
  const html = shown().map((i) => {
    const r = wl.rows[i];
    n += 1;
    return `<div class="film-row" draggable="true" data-i="${i}">
      <span class="film-grip" title="Drag to reorder"><i data-lucide="grip-vertical"></i></span>
      <button type="button" class="film-pos" data-pos="${i}" title="Move to position…">${n}</button>
      <input type="text" class="film-notes" value="${esc(r.notes)}" data-notes="${i}" aria-label="Title and notes" placeholder="Title (Year) and notes">
      <a class="film-id" href="https://www.imdb.com/title/${esc(r.id)}/" target="_blank" rel="noopener noreferrer" title="Open on IMDb">${esc(r.id)}</a>
      <button type="button" class="btn btn-icon-only" data-up="${i}" title="Move up"><i data-lucide="arrow-up"></i></button>
      <button type="button" class="btn btn-icon-only" data-down="${i}" title="Move down"><i data-lucide="arrow-down"></i></button>
      <button type="button" class="btn btn-icon-only btn-danger-light" data-drop="${i}" title="Take it off the list"><i data-lucide="x"></i></button>
    </div>`;
  }).join('');
  $('film-list').innerHTML = html || '<div class="empty-state"><i data-lucide="film"></i><span>No films yet. Search above to add some.</span></div>';
  icons();
}

const filmList = $('film-list');
filmList.addEventListener('input', (e) => {
  const t = e.target;
  if (t.dataset.notes !== undefined) {
    Object.assign(wl.rows[Number(t.dataset.notes)], { notes: t.value, edited: true });
    setWlDirty();
  }
});
filmList.addEventListener('click', async (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  const d = b.dataset;
  const vis = shown();
  if (d.up !== undefined) {
    const i = Number(d.up);
    const prev = vis[vis.indexOf(i) - 1];
    if (prev !== undefined) moveRow(i, prev);
  } else if (d.down !== undefined) {
    const i = Number(d.down);
    const next = vis[vis.indexOf(i) + 1];
    if (next !== undefined) moveRow(i, next + 1);
  } else if (d.drop !== undefined) {
    wl.rows.splice(Number(d.drop), 1);
    setWlDirty();
    renderFilms();
  } else if (d.pos !== undefined) {
    const i = Number(d.pos);
    const films = wl.rows.map((r, k) => k).filter((k) => wl.rows[k].kind === 'film');
    const answer = await showAppConfirm(`Move to which position (1 to ${films.length})?`, { prompt: String(films.indexOf(i) + 1), okText: 'Move' });
    const to = parseInt(answer, 10);
    if (!to || to < 1 || to > films.length) return;
    const target = films[to - 1];
    if (target === i) return;
    moveRow(i, target < i ? target : target + 1);
  }
});

filmList.addEventListener('dragstart', (e) => {
  const row = e.target.closest('.film-row');
  if (!row) return;
  dragFrom = Number(row.dataset.i);
  e.dataTransfer.effectAllowed = 'move';
  row.classList.add('dragging');
});
filmList.addEventListener('dragend', () => {
  dragFrom = null;
  filmList.querySelectorAll('.dragging, .drop-before, .drop-after').forEach((el) => el.classList.remove('dragging', 'drop-before', 'drop-after'));
});
filmList.addEventListener('dragover', (e) => {
  const row = e.target.closest('.film-row');
  if (dragFrom === null || !row) return;
  e.preventDefault();
  const rect = row.getBoundingClientRect();
  const before = e.clientY < rect.top + rect.height / 2;
  filmList.querySelectorAll('.drop-before, .drop-after').forEach((el) => el.classList.remove('drop-before', 'drop-after'));
  row.classList.add(before ? 'drop-before' : 'drop-after');
});
filmList.addEventListener('drop', (e) => {
  const row = e.target.closest('.film-row');
  if (dragFrom === null || !row) return;
  e.preventDefault();
  const target = Number(row.dataset.i);
  const before = row.classList.contains('drop-before');
  const from = dragFrom;
  dragFrom = null;
  if (target !== from) moveRow(from, before ? target : target + 1);
});

function addFilm(id, notes) {
  const at = wl.rows.findIndex((r) => r.kind === 'film' && r.id === id);
  if (at >= 0) {
    const n = wl.rows.slice(0, at + 1).filter((r) => r.kind === 'film').length;
    showToast(`${notes || id} is already on the list at #${n}.`, 'warning');
    return;
  }
  const vis = shown();
  const last = vis.length ? vis[vis.length - 1] : -1;
  const film = { kind: 'film', id, notes, edited: true };
  if (last < 0) {
    // the first film: after the title and description, set off by a blank line
    let to = wl.rows.length;
    while (to > 0 && blank(wl.rows[to - 1])) to -= 1;
    wl.rows.splice(to, 0, { kind: 'text', text: '' }, film);
  } else {
    wl.rows.splice(last + 1, 0, film);
  }
  setWlDirty();
  renderFilms();
  const rows = filmList.querySelectorAll('.film-row');
  rows[rows.length - 1]?.scrollIntoView({ block: 'nearest' });
  showToast(`Added ${notes || id} at #${rows.length}.`, 'success');
}

$('search-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = $('search-q').value.trim();
  if (!q) return;
  const out = $('search-results');
  out.innerHTML = '<div class="search-empty">Searching…</div>';
  try {
    const r = await api(`search?q=${encodeURIComponent(q)}&type=${$('search-type').value}`);
    if (!r.results.length) {
      out.innerHTML = '<div class="search-empty">Nothing found. Try another spelling, or paste the IMDb link.</div>';
      return;
    }
    out.innerHTML = r.results.map((f, n) => {
      const label = f.title ? `${f.title}${f.year ? ` (${f.year})` : ''}` : '';
      const on = wl.rows.some((x) => x.kind === 'film' && x.id === f.id);
      return `<div class="search-row">
        <span class="search-title">${esc(label || 'IMDb ID')}</span>
        <a class="film-id" href="https://www.imdb.com/title/${esc(f.id)}/" target="_blank" rel="noopener noreferrer">${esc(f.id)}</a>
        <button type="button" class="btn btn-secondary btn-xs" data-add="${n}" ${on ? 'disabled' : ''}>${on ? 'On the list' : '<i data-lucide="plus"></i><span>Add</span>'}</button>
      </div>`;
    }).join('');
    out.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', () => {
      const f = r.results[Number(b.dataset.add)];
      addFilm(f.id, f.title ? `${f.title}${f.year ? ` (${f.year})` : ''}` : '');
      b.disabled = true;
      b.textContent = 'On the list';
    }));
    icons();
  } catch (err) {
    out.innerHTML = `<div class="search-empty">${esc((err.data?.problems || [err.message]).join(' '))}</div>`;
  }
});

$('btn-watchlist-save').addEventListener('click', saveWatchlist);

async function saveWatchlist() {
  try {
    const r = await api(`watchlist?name=${encodeURIComponent(wl.name)}`, { method: 'PUT', body: { rows: wl.rows, version: wl.version } });
    const fresh = await api(`watchlist?name=${encodeURIComponent(wl.name)}`);
    wl = fresh;
    setWlDirty(false);
    renderFilms();
    showToast(`${wl.name} saved: ${r.films} films.${r.flattened ? ' Headings between the films were taken out, since playlists have no sections.' : ''}`, 'success');
    refresh();
    return true;
  } catch (err) {
    showToast((err.data?.problems || [err.message]).join(' '), 'error');
    return false;
  }
}

// ---------------------------------------------------------------- artwork files

let images = [];
const picked = new Set();

async function openImages() {
  try {
    images = (await api('images')).images;
  } catch (err) {
    showToast(err.message, 'error');
    return;
  }
  picked.clear();
  openDrawer('images-drawer');
  renderImages();
}

function renderImages() {
  const groups = [
    ['unused', 'Not used by anything', 'Nothing in collections.toml, playlists.toml or genres.toml points at these.'],
    ['archived', 'Archived', 'Older copies kept when StaffPicked saved a newer image.'],
    ['used', 'In use', 'A collection, playlist or genre uses these, so they can\'t be deleted here.'],
  ];
  const total = (list) => fmtSize(list.reduce((a, i) => a + i.size, 0));
  $('image-list').innerHTML = groups.map(([state, title, hint]) => {
    const list = images.filter((i) => i.state === state);
    if (!list.length) return '';
    return `<div class="image-group">
      <div class="image-group-head"><h4>${title}</h4><span>${list.length} file${list.length === 1 ? '' : 's'} · ${total(list)}</span></div>
      <p class="field-hint">${hint}</p>
      ${list.map((i) => `
      <div class="image-row ${state}">
        <input type="checkbox" data-pick="${esc(i.name)}" ${state === 'used' ? 'disabled' : ''} ${picked.has(i.name) ? 'checked' : ''} aria-label="Select ${esc(i.name)}">
        <img src="api/images/file?name=${encodeURIComponent(i.name)}" alt="" loading="lazy">
        <div class="image-info">
          <span class="image-name">${esc(i.name)}</span>
          <span class="image-meta">${fmtSize(i.size)} · ${new Date(i.modified * 1000).toLocaleDateString()}${i.used_by.length ? ` · ${esc(i.used_by.join(', '))}` : ''}</span>
        </div>
        ${state === 'used' ? '' : `<button type="button" class="btn btn-icon-only btn-danger-light" data-delimg="${esc(i.name)}" title="Delete this file"><i data-lucide="trash-2"></i></button>`}
      </div>`).join('')}
    </div>`;
  }).join('') || '<div class="empty-state"><i data-lucide="image"></i><span>No image files in images/ or next to your lists.</span></div>';
  updateImageButtons();
  icons();
}

function updateImageButtons() {
  const n = picked.size;
  const size = images.filter((i) => picked.has(i.name)).reduce((a, i) => a + i.size, 0);
  const b = $('btn-images-delete');
  b.disabled = !n;
  b.querySelector('span').textContent = n ? `Review & Delete ${n} (${fmtSize(size)})` : 'Review & Delete';
}

$('image-list').addEventListener('change', (e) => {
  const name = e.target.dataset.pick;
  if (name === undefined) return;
  if (e.target.checked) picked.add(name); else picked.delete(name);
  updateImageButtons();
});
$('image-list').addEventListener('click', (e) => {
  const b = e.target.closest('[data-delimg]');
  if (b) deleteImages([b.dataset.delimg]);
});
$('btn-images-select-stale').addEventListener('click', () => {
  images.filter((i) => i.state !== 'used').forEach((i) => picked.add(i.name));
  renderImages();
});
$('btn-images-select-none').addEventListener('click', () => { picked.clear(); renderImages(); });
$('btn-images-delete').addEventListener('click', () => deleteImages([...picked]));

async function deleteImages(names) {
  const list = images.filter((i) => names.includes(i.name));
  if (!list.length) return;
  const size = fmtSize(list.reduce((a, i) => a + i.size, 0));
  const r = await review({
    title: list.length === 1 ? `Delete ${list[0].name}?` : `Delete these ${list.length} files (${size})?`,
    intro: list.length === 1 ? '' : 'These files will be deleted from the config folder:',
    items: list.length === 1 ? [] : list.map((i) => `${i.name} (${fmtSize(i.size)}, ${i.state === 'archived' ? 'archived' : 'not used'})`),
    foot: 'This can\'t be undone. Nothing on the media server changes.',
    okText: list.length === 1 ? 'Delete' : `Delete ${list.length} Files`,
  });
  if (!r.ok) return;
  try {
    const out = await api('images/delete', { method: 'POST', body: { names: list.map((i) => i.name) } });
    out.deleted.forEach((n) => picked.delete(n));
    showToast(`Deleted ${out.deleted.length} file${out.deleted.length === 1 ? '' : 's'}.`, 'success');
  } catch (err) {
    showToast((err.data?.problems || [err.message]).join(' '), 'error');
  }
  images = (await api('images').catch(() => ({ images }))).images;
  renderImages();
}

$('btn-images-toggle').addEventListener('click', openImages);

// ---------------------------------------------------------------- importing from the server

let found = null;          // {collection: [row], playlist: [row]} from the last scan
const chosen = new Set();  // "kind:id"
const STATES = {
  managed: ['on', 'Managed'],
  similar: ['warn', 'Similar name'],
  new: ['', 'Not in StaffPicked'],
  duplicate: ['bad', 'Duplicate'],
};

const listName = (u) => u.replace(/^https:\/\/(www\.)?/, '');
const sourceText = (src) => src.sources.map(listName).join(' + ');

function importNote(r) {
  const e = esc(r.entry);
  const n = esc(r.name);
  if (r.kind === 'genre') {
    const has = `Has ${esc((r.art || []).join(', '))} on ${esc(importServer || serverName())}.`;
    if (r.status === 'managed') return `${has} StaffPicked's "${e}" sets this genre's artwork.`;
    if (r.status === 'similar') return `${has} Looks like StaffPicked's "${e}". Linking renames that entry to "${n}" so it sets this genre's artwork.`;
    return `${has} Importing saves those images to images/ and adds the genre to genres.toml, so StaffPicked keeps them and you can swap any of them later.`;
  }
  if (r.action === 'source' && r.source) {
    return `StaffPicked's "${e}" is a fixed copy from an earlier import. Its list looks like <b>${esc(sourceText(r.source))}</b> (${esc(r.source.how)}); switching makes it follow that list again.`;
  }
  const noKey = r.no_key ? ' Add an MDBList API key in Settings so StaffPicked can look for the list it came from.' : '';
  if (r.status === 'managed' && r.fixed) return `StaffPicked's "${e}" is a fixed list, and no MDBList or Trakt list was found that it came from. Pick it to give its list's link.${noKey}`;
  if (r.status === 'managed') {
    return r.kind === 'collection' ? `StaffPicked's "${e}" updates this one in place.`
      : `StaffPicked's "${e}" rebuilds this one from its lists on every sync.`;
  }
  if (r.status === 'similar') return `Looks like StaffPicked's "${e}". Linking renames that entry to "${n}", so StaffPicked updates this one instead of building a second.`;
  if (r.status === 'duplicate') {
    return r.kind === 'collection' ? `A second collection named "${e}". StaffPicked only ever updates the first; this one is left alone.`
      : `A second playlist named "${e}". If StaffPicked manages that name, a sync replaces both with one.`;
  }
  if (r.source) return `Imports as a collection that follows <b>${esc(sourceText(r.source))}</b> (${esc(r.source.how)}).`;
  if (r.kind === 'collection') return `No list found for it. Importing asks for its list's link, or with Skip copies its films to a new file in collections/ as a fixed list that won't follow any list.${noKey}`;
  return 'Importing copies its films, in order, to a new file in playlists/ and adds it to playlists.toml.';
}

let importBusy = false;    // a scan or an import is running; the buttons wait for it
let importServer = '';     // the server being imported from; '' = the first one

async function scanServer() {
  importBusy = true;
  updateImportButtons();
  $('import-list').innerHTML = '';
  setProgress($('import-list'), 'Reading the server…');
  progressHandlers.scan = (d) => {
    if ($('import-list').querySelector('.progress-box')) setProgress($('import-list'), d.step, d);
  };
  try {
    const { server, servers, ...rows } = await api(`import${importServer ? `?server=${encodeURIComponent(importServer)}` : ''}`);
    found = rows;
    document.querySelectorAll('.server-name').forEach((el) => { el.textContent = server; });
  } catch (err) {
    found = null;
    $('import-list').innerHTML = '';
    showNotes($('import-notes'), err.data?.problems || [err.message]);
    return;
  } finally {
    importBusy = false;
    updateImportButtons();
  }
  const live = new Set(Object.values(found).flat().filter((r) => r.action).map((r) => `${r.kind}:${r.id}`));
  [...chosen].forEach((k) => { if (!live.has(k)) chosen.delete(k); });
  renderImport();
}

async function openImport() {
  const names = serverNames();
  if (!names.includes(importServer)) importServer = names[0] || '';
  document.querySelectorAll('.server-name').forEach((el) => { el.textContent = importServer || serverName(); });
  const pick = $('import-server');
  pick.style.display = names.length > 1 ? '' : 'none';
  pick.innerHTML = names.map((n) => `<option value="${esc(n)}" ${n === importServer ? 'selected' : ''}>${esc(n)}</option>`).join('');
  chosen.clear();
  showNotes($('import-notes'));
  openDrawer('import-drawer');
  await scanServer();
}

function renderImport() {
  const order = { similar: 0, new: 1, duplicate: 3, managed: 4 };
  const rank = (r) => (r.action === 'source' ? 2 : order[r.status]);
  $('import-list').innerHTML = [['collection', 'Collections'], ['playlist', 'Playlists'], ['genre', 'Genres']].map(([kind, title]) => {
    const list = [...(found?.[kind] || [])].sort((a, b) => rank(a) - rank(b));
    const todo = list.filter((r) => r.action).length;
    return `<div class="image-group">
      <div class="image-group-head"><h4>${title}</h4><span>${list.length} ${kind === 'genre' ? 'with artwork ' : ''}on the server · ${todo ? `${todo} to bring in` : 'nothing to bring in'}</span></div>
      ${list.length ? '' : `<p class="field-hint">${kind === 'genre' ? 'No genres on the server have artwork of their own.' : `No ${title.toLowerCase()} on the server${kind === 'playlist' ? ' for the admin user' : ''}.`}</p>`}
      ${list.map((r) => {
        const [cls, label] = r.action === 'source' ? ['warn', 'Fixed copy'] : STATES[r.status];
        const pick = Boolean(r.action);
        const k = `${r.kind}:${r.id}`;
        return `<label class="image-row import-row ${pick ? 'pickable' : r.status}">
          <input type="checkbox" data-import="${esc(k)}" ${pick ? '' : 'disabled'} ${chosen.has(k) ? 'checked' : ''} aria-label="Select ${esc(r.name)}">
          <div class="image-info">
            <span class="image-name">${esc(r.name)}${r.count != null ? ` <span class="import-count">${r.count} item${r.count === 1 ? '' : 's'}</span>` : ''}</span>
            <span class="image-meta">${importNote(r)}</span>
          </div>
          <span class="season-badge ${cls}">${{ link: 'Link', source: r.source ? 'Use list' : 'Add list' }[r.action] || label}</span>
        </label>`;
      }).join('')}
    </div>`;
  }).join('');
  updateImportButtons();
  icons();
}

function updateImportButtons() {
  const n = chosen.size;
  const b = $('btn-import-go');
  b.disabled = !n || importBusy;
  ['btn-import-select-all', 'btn-import-select-none', 'btn-import-refresh', 'import-server'].forEach((id) => { $(id).disabled = importBusy; });
  $('import-list').classList.toggle('busy', importBusy);
  b.querySelector('span').textContent = n ? `Review & Import ${n}` : 'Review & Import';
}

const importRows = () => Object.values(found || {}).flat();

$('import-list').addEventListener('change', (e) => {
  const k = e.target.dataset.import;
  if (k === undefined) return;
  if (e.target.checked) chosen.add(k); else chosen.delete(k);
  updateImportButtons();
});
$('btn-import-select-all').addEventListener('click', () => {
  importRows().filter((r) => r.action).forEach((r) => chosen.add(`${r.kind}:${r.id}`));
  renderImport();
});
$('btn-import-select-none').addEventListener('click', () => { chosen.clear(); renderImport(); });
$('btn-import-refresh').addEventListener('click', scanServer);
$('import-server').addEventListener('change', (e) => { importServer = e.target.value; chosen.clear(); showNotes($('import-notes')); scanServer(); });

const LIST_LINK = /^(https?:\/\/)?(www\.)?(mdblist\.com\/lists\/[^/\s]+\/[^/\s]+|trakt\.tv\/users\/[^/\s]+\/(lists\/[^/\s]+|watchlist))\/?$/i;

// A collection whose list wasn't found: ask for its link. Resolves the link, or '' to skip.
async function askForList(r) {
  const fixed = r.action === 'source';
  let hint = '';
  for (;;) {
    const v = await showAppConfirm(
      `${hint}StaffPicked couldn't find the list the collection "${r.name}" was built from. If you know it, paste its MDBList or Trakt link. `
      + (fixed ? 'Skip leaves it as it is.' : 'Skip imports it as a fixed list of the films it has now.'),
      { prompt: '', placeholder: 'https://mdblist.com/lists/user/list', okText: 'Use This Link', cancelText: 'Skip' },
    );
    const link = (v || '').trim();
    if (!link) return '';
    if (LIST_LINK.test(link)) return /^https?:/i.test(link) ? link : `https://${link}`;
    hint = `"${link}" isn't an MDBList or Trakt list link. `;
  }
}

$('btn-import-go').addEventListener('click', async () => {
  let rows = importRows().filter((r) => chosen.has(`${r.kind}:${r.id}`));
  if (!rows.length) return;
  for (const x of rows) {
    delete x.url;
    if (x.kind === 'collection' && !x.source && ['import', 'source'].includes(x.action)) x.url = await askForList(x);
  }
  rows = rows.filter((x) => !(x.action === 'source' && !x.source && !x.url));   // skipped: nothing to switch to
  if (!rows.length) return;
  const r = await review({
    title: `Bring ${rows.length} into StaffPicked?`,
    intro: 'StaffPicked will:',
    items: rows.map((x) => {
      if (x.action === 'link') return `Link the ${x.kind} "${x.name}": rename StaffPicked's "${x.entry}" to match it`;
      if (x.kind === 'genre') return `Import the artwork of the genre "${x.name}" (${(x.art || []).join(', ')})`;
      const follow = x.url ? `${listName(x.url)} (the link you gave)` : x.source && sourceText(x.source);
      if (x.action === 'source') return `Switch the collection "${x.name}" to follow ${follow}`;
      if (follow) return `Import the collection "${x.name}" following ${follow}`;
      return `Import the ${x.kind} "${x.name}"${x.count != null ? ` (${x.count} item${x.count === 1 ? '' : 's'})` : ''} as a fixed list`;
    }),
    foot: `Only the config folder changes now. From the next sync on, StaffPicked keeps these up to date like everything else it manages: a collection that follows a list gains and loses films as the list does, and a fixed list stays as it is. A link you gave is checked before anything is saved. Imported playlists keep every film and stay private until you change that. Imported genres keep the artwork they have now. Anything without an IMDb ID can't go in a list file; it's listed at the end of the file.`,
    okText: `Import ${rows.length}`,
    danger: false,
  });
  if (!r.ok) return;
  importBusy = true;
  updateImportButtons();
  // each pick's result shows up as soon as it's done, under a bar counting them off
  showNotes($('import-notes'));
  $('import-notes').insertAdjacentHTML('afterbegin', '<div id="import-progress"></div><div id="import-live" class="builder-notes"></div>');
  setProgress($('import-progress'), 'Checking what\'s on the server…', { done: 0, total: rows.length });
  progressHandlers.import = (d) => {
    if (!$('import-progress')) return;
    setProgress($('import-progress'), d.step, d);
    if (d.line) {
      const bad = /^(Failed|Skipped)/.test(d.line);
      $('import-live').insertAdjacentHTML('beforeend', `<div class="builder-note ${bad ? 'warn' : 'ok'}"><i data-lucide="${bad ? 'alert-triangle' : 'check-circle'}"></i><span>${esc(d.line)}</span></div>`);
      icons();
    }
  };
  try {
    const out = await api('import', { method: 'POST', body: { server: importServer, picks: rows.map((x) => ({ kind: x.kind, id: x.id, action: x.action, ...(x.url ? { url: x.url } : {}) })) } });
    const bad = out.results.filter((l) => /^(Failed|Skipped)/.test(l));
    showNotes($('import-notes'), [], bad);
    $('import-notes').insertAdjacentHTML('afterbegin', out.results.filter((l) => !bad.includes(l))
      .map((l) => `<div class="builder-note ok"><i data-lucide="check-circle"></i><span>${esc(l)}</span></div>`).join(''));
    icons();
    const good = out.results.length - bad.length;
    showToast(`Brought ${good} of ${out.results.length} into StaffPicked.`, bad.length ? 'warning' : 'success');
  } catch (err) {
    showNotes($('import-notes'), err.data?.problems || [err.message]);
  } finally {
    delete progressHandlers.import;
    importBusy = false;
  }
  chosen.clear();
  await scanServer();
});

$('btn-import').addEventListener('click', openImport);
