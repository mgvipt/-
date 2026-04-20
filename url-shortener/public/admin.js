'use strict';

const TOKEN_KEY = 'shortener.adminToken';
const authCard = document.getElementById('auth-card');
const createCard = document.getElementById('create-card');
const listCard = document.getElementById('list-card');
const statusEl = document.getElementById('status');
const logoutBtn = document.getElementById('btn-logout');
const authForm = document.getElementById('auth-form');
const authTokenInput = document.getElementById('auth-token');
const authRemember = document.getElementById('auth-remember');
const createForm = document.getElementById('create-form');
const createUrl = document.getElementById('create-url');
const createSlug = document.getElementById('create-slug');
const createNote = document.getElementById('create-note');
const createResult = document.getElementById('create-result');
const linksBody = document.getElementById('links-body');
const listEmpty = document.getElementById('list-empty');
const refreshBtn = document.getElementById('btn-refresh');

let token = sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || '';

function show(el, visible) { el.hidden = !visible; }

function setAuthed(on) {
  show(authCard, !on);
  show(createCard, on);
  show(listCard, on);
  show(logoutBtn, on);
  statusEl.textContent = on ? 'Авторизовано' : '';
  if (on) refresh();
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      'content-type': 'application/json',
      'x-admin-token': token,
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) {
    clearToken();
    setAuthed(false);
    throw new Error('Не авторизовано');
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new Error((body && body.error) || `HTTP ${res.status}`);
  return body;
}

function saveToken(value, persist) {
  token = value;
  sessionStorage.setItem(TOKEN_KEY, value);
  if (persist) localStorage.setItem(TOKEN_KEY, value);
  else localStorage.removeItem(TOKEN_KEY);
}

function clearToken() {
  token = '';
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
}

authForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const value = authTokenInput.value.trim();
  if (!value) return;
  saveToken(value, authRemember.checked);
  try {
    await api('/api/links?limit=1');
    setAuthed(true);
    authTokenInput.value = '';
  } catch (err) {
    statusEl.textContent = err.message;
  }
});

logoutBtn.addEventListener('click', () => {
  clearToken();
  setAuthed(false);
});

createForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  createResult.textContent = '';
  createResult.className = 'result';
  try {
    const link = await api('/api/links', {
      method: 'POST',
      body: JSON.stringify({
        url: createUrl.value.trim(),
        slug: createSlug.value.trim() || undefined,
        note: createNote.value.trim() || undefined,
      }),
    });
    createResult.innerHTML = `Готово: <a href="${link.short_url}" target="_blank" rel="noopener">${link.short_url}</a>`;
    createResult.classList.add('ok');
    createForm.reset();
    await navigator.clipboard.writeText(link.short_url).catch(() => {});
    refresh();
  } catch (err) {
    createResult.textContent = 'Ошибка: ' + err.message;
    createResult.classList.add('err');
  }
});

refreshBtn.addEventListener('click', refresh);

async function refresh() {
  try {
    const data = await api('/api/links?limit=500');
    renderList(data.items);
  } catch (err) {
    if (token) statusEl.textContent = err.message;
  }
}

function renderList(items) {
  linksBody.innerHTML = '';
  show(listEmpty, items.length === 0);
  const fmt = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
  for (const item of items) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><a href="${item.short_url}" target="_blank" rel="noopener">${item.short_url.replace(/^https?:\/\//, '')}</a></td>
      <td class="truncate" title="${escapeAttr(item.target)}">${escapeHtml(item.target)}</td>
      <td>${fmt.format(new Date(item.created_at))}</td>
      <td class="num">${item.clicks}</td>
      <td class="truncate" title="${escapeAttr(item.note || '')}">${escapeHtml(item.note || '')}</td>
      <td class="row-actions">
        <button type="button" class="btn btn-ghost btn-sm" data-action="copy" data-url="${escapeAttr(item.short_url)}">Копир.</button>
        <button type="button" class="btn btn-ghost btn-sm" data-action="delete" data-slug="${escapeAttr(item.slug)}">Удалить</button>
      </td>
    `;
    linksBody.appendChild(tr);
  }
}

linksBody.addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  if (btn.dataset.action === 'copy') {
    await navigator.clipboard.writeText(btn.dataset.url).catch(() => {});
    const prev = btn.textContent;
    btn.textContent = 'Ок';
    setTimeout(() => (btn.textContent = prev), 800);
  } else if (btn.dataset.action === 'delete') {
    if (!confirm('Удалить ссылку?')) return;
    try {
      await api('/api/links/' + encodeURIComponent(btn.dataset.slug), { method: 'DELETE' });
      refresh();
    } catch (err) {
      alert('Ошибка: ' + err.message);
    }
  }
});

function escapeHtml(s) { return String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
function escapeAttr(s) { return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

(async function init() {
  if (!token) return setAuthed(false);
  try {
    await api('/api/links?limit=1');
    setAuthed(true);
  } catch {
    setAuthed(false);
  }
})();
