'use strict';

const path = require('path');
const crypto = require('crypto');
const express = require('express');
const Database = require('better-sqlite3');

const PORT = parseInt(process.env.PORT || '3000', 10);
const HOST = process.env.HOST || '127.0.0.1';
const DB_PATH = process.env.DB_PATH || path.join(__dirname, 'data', 'shortener.db');
const PUBLIC_BASE_URL = (process.env.PUBLIC_BASE_URL || '').replace(/\/$/, '');
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || '';
const DEFAULT_SLUG_LEN = 6;
const MAX_SLUG_LEN = 40;
const SLUG_RE = /^[A-Za-z0-9_-]{1,40}$/;
const RESERVED_SLUGS = new Set(['api', 'admin', 'static', 'favicon.ico', 'robots.txt', 'health']);

if (!ADMIN_TOKEN) {
  console.warn('[warn] ADMIN_TOKEN is not set — admin endpoints are disabled. Set it in .env to enable link management.');
}

require('fs').mkdirSync(path.dirname(DB_PATH), { recursive: true });

const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS links (
    slug TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    clicks INTEGER NOT NULL DEFAULT 0,
    last_click_at INTEGER,
    note TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_links_created_at ON links(created_at DESC);
`);

const stmts = {
  get: db.prepare('SELECT slug, target, created_at, clicks, last_click_at, note FROM links WHERE slug = ?'),
  insert: db.prepare('INSERT INTO links (slug, target, created_at, note) VALUES (?, ?, ?, ?)'),
  list: db.prepare('SELECT slug, target, created_at, clicks, last_click_at, note FROM links ORDER BY created_at DESC LIMIT ? OFFSET ?'),
  count: db.prepare('SELECT COUNT(*) AS n FROM links'),
  del: db.prepare('DELETE FROM links WHERE slug = ?'),
  touch: db.prepare('UPDATE links SET clicks = clicks + 1, last_click_at = ? WHERE slug = ?'),
  update: db.prepare('UPDATE links SET target = ?, note = ? WHERE slug = ?'),
};

function generateSlug(len = DEFAULT_SLUG_LEN) {
  const alphabet = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  const bytes = crypto.randomBytes(len);
  let out = '';
  for (let i = 0; i < len; i++) out += alphabet[bytes[i] % alphabet.length];
  return out;
}

function normalizeUrl(raw) {
  if (typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  let candidate = trimmed;
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(candidate)) candidate = 'https://' + candidate;
  try {
    const u = new URL(candidate);
    if (!/^https?:$/i.test(u.protocol)) return null;
    if (!u.hostname || u.hostname.length > 253) return null;
    return u.toString();
  } catch {
    return null;
  }
}

function requireAdmin(req, res, next) {
  if (!ADMIN_TOKEN) return res.status(503).json({ error: 'Admin disabled: ADMIN_TOKEN not configured on server' });
  const header = req.get('authorization') || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : req.get('x-admin-token') || '';
  const a = Buffer.from(token);
  const b = Buffer.from(ADMIN_TOKEN);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
}

const app = express();
app.disable('x-powered-by');
app.set('trust proxy', true);
app.use(express.json({ limit: '64kb' }));

app.get('/health', (_req, res) => res.json({ ok: true, uptime: process.uptime() }));

app.use('/static', express.static(path.join(__dirname, 'public'), { maxAge: '1h' }));
app.get('/', (_req, res) => res.sendFile(path.join(__dirname, 'public', 'index.html')));
app.get('/admin', (_req, res) => res.sendFile(path.join(__dirname, 'public', 'admin.html')));

app.post('/api/links', requireAdmin, (req, res) => {
  const { url, slug, note } = req.body || {};
  const target = normalizeUrl(url);
  if (!target) return res.status(400).json({ error: 'Invalid URL' });

  let finalSlug = (slug || '').trim();
  if (finalSlug) {
    if (!SLUG_RE.test(finalSlug) || RESERVED_SLUGS.has(finalSlug.toLowerCase())) {
      return res.status(400).json({ error: 'Invalid or reserved slug' });
    }
    if (stmts.get.get(finalSlug)) return res.status(409).json({ error: 'Slug already exists' });
  } else {
    for (let attempt = 0; attempt < 6; attempt++) {
      const candidate = generateSlug(DEFAULT_SLUG_LEN + Math.floor(attempt / 2));
      if (!stmts.get.get(candidate) && !RESERVED_SLUGS.has(candidate.toLowerCase())) {
        finalSlug = candidate;
        break;
      }
    }
    if (!finalSlug) return res.status(500).json({ error: 'Could not generate unique slug' });
  }

  stmts.insert.run(finalSlug, target, Date.now(), (note || '').toString().slice(0, 500) || null);
  res.status(201).json(serializeLink(stmts.get.get(finalSlug), req));
});

app.get('/api/links', requireAdmin, (req, res) => {
  const limit = Math.min(parseInt(req.query.limit, 10) || 100, 500);
  const offset = Math.max(parseInt(req.query.offset, 10) || 0, 0);
  const rows = stmts.list.all(limit, offset);
  const total = stmts.count.get().n;
  res.json({ total, limit, offset, items: rows.map((r) => serializeLink(r, req)) });
});

app.patch('/api/links/:slug', requireAdmin, (req, res) => {
  const row = stmts.get.get(req.params.slug);
  if (!row) return res.status(404).json({ error: 'Not found' });
  const target = req.body && req.body.url != null ? normalizeUrl(req.body.url) : row.target;
  if (!target) return res.status(400).json({ error: 'Invalid URL' });
  const note = req.body && req.body.note != null ? String(req.body.note).slice(0, 500) || null : row.note;
  stmts.update.run(target, note, row.slug);
  res.json(serializeLink(stmts.get.get(row.slug), req));
});

app.delete('/api/links/:slug', requireAdmin, (req, res) => {
  const info = stmts.del.run(req.params.slug);
  if (info.changes === 0) return res.status(404).json({ error: 'Not found' });
  res.json({ ok: true });
});

app.get('/:slug', (req, res, next) => {
  const { slug } = req.params;
  if (!SLUG_RE.test(slug)) return next();
  const row = stmts.get.get(slug);
  if (!row) return res.status(404).sendFile(path.join(__dirname, 'public', '404.html'));
  stmts.touch.run(Date.now(), slug);
  res.redirect(302, row.target);
});

app.use((_req, res) => res.status(404).sendFile(path.join(__dirname, 'public', '404.html')));

app.use((err, _req, res, _next) => {
  console.error('[error]', err);
  res.status(500).json({ error: 'Internal error' });
});

function serializeLink(row, req) {
  if (!row) return null;
  const base = PUBLIC_BASE_URL || `${req.protocol}://${req.get('host')}`;
  return {
    slug: row.slug,
    short_url: `${base}/${row.slug}`,
    target: row.target,
    created_at: row.created_at,
    clicks: row.clicks,
    last_click_at: row.last_click_at,
    note: row.note,
  };
}

const server = app.listen(PORT, HOST, () => {
  console.log(`[ok] URL shortener listening on http://${HOST}:${PORT}`);
  console.log(`[ok] DB: ${DB_PATH}`);
  if (PUBLIC_BASE_URL) console.log(`[ok] Public base URL: ${PUBLIC_BASE_URL}`);
});

function shutdown(sig) {
  console.log(`[ok] ${sig} received, shutting down`);
  server.close(() => { db.close(); process.exit(0); });
  setTimeout(() => process.exit(1), 8000).unref();
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
