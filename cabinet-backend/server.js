// Wallcov «Кабінет» — авторизація + синхронізація кошторисів між пристроями.
// Стек: Node + Express, сховище — JSON-файл (без нативних залежностей).
// Дані: /app/data/db.json (монтується як volume, тому переживає рестарти).
// ENV: JWT_SECRET (обов'язково), SIGNUP_CODE (код-запрошення для реєстрації), PORT, DB_FILE.

import express from "express";
import cors from "cors";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const PORT = process.env.PORT || 8090;
const SECRET = process.env.JWT_SECRET || "change-me-please";
const SIGNUP_CODE = process.env.SIGNUP_CODE || "";
const DB_FILE = process.env.DB_FILE || "./data/db.json";

fs.mkdirSync(path.dirname(DB_FILE), { recursive: true });
let db = { users: [], objects: [] };
try { db = JSON.parse(fs.readFileSync(DB_FILE, "utf8")); } catch (_) {}
let t = null;
function persist() { clearTimeout(t); t = setTimeout(() => {
  const tmp = DB_FILE + ".tmp"; fs.writeFileSync(tmp, JSON.stringify(db)); fs.renameSync(tmp, DB_FILE);
}, 50); }

const hashPw = (pw, salt = crypto.randomBytes(16).toString("hex")) =>
  salt + ":" + crypto.scryptSync(pw, salt, 32).toString("hex");
function checkPw(pw, stored) {
  const [salt, h] = String(stored).split(":");
  const a = Buffer.from(crypto.scryptSync(pw, salt, 32).toString("hex")); const b = Buffer.from(h);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}
const b64u = (s) => Buffer.from(s).toString("base64url");
const sign = (p) => { const body = b64u(JSON.stringify(p)); return body + "." + crypto.createHmac("sha256", SECRET).update(body).digest("base64url"); };
function verify(tok) {
  if (!tok) return null; const [body, sig] = tok.split(".");
  if (!body || !sig) return null;
  const exp = crypto.createHmac("sha256", SECRET).update(body).digest("base64url");
  const a = Buffer.from(sig), b = Buffer.from(exp);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;
  try { return JSON.parse(Buffer.from(body, "base64url").toString()); } catch (_) { return null; }
}

const app = express();
app.use(cors());
app.use(express.json({ limit: "25mb" }));

app.get("/health", (_q, r) => r.json({ ok: true }));

app.post("/auth/register", (req, res) => {
  const { login, password, code } = req.body || {};
  if (SIGNUP_CODE && code !== SIGNUP_CODE) return res.status(403).json({ error: "Невірний код запрошення" });
  if (!login || !password) return res.status(400).json({ error: "Вкажіть логін і пароль" });
  if (db.users.find((u) => u.login === login)) return res.status(409).json({ error: "Такий користувач вже існує" });
  const user = { id: crypto.randomUUID(), login, pass: hashPw(password) };
  db.users.push(user); persist();
  res.json({ token: sign({ uid: user.id, login }), login });
});
app.post("/auth/login", (req, res) => {
  const { login, password } = req.body || {};
  const user = db.users.find((u) => u.login === login);
  if (!user || !checkPw(password, user.pass)) return res.status(401).json({ error: "Невірний логін або пароль" });
  res.json({ token: sign({ uid: user.id, login }), login });
});

function auth(req, res, next) {
  const p = verify((req.get("authorization") || "").replace(/^Bearer /, ""));
  if (!p) return res.status(401).json({ error: "unauthorized" });
  req.uid = p.uid; next();
}

app.get("/api/objects", auth, (req, res) => {
  res.json(db.objects.filter((o) => o.uid === req.uid)
    .map((o) => ({ id: o.id, name: o.name, updated_at: o.updated_at }))
    .sort((a, b) => b.updated_at - a.updated_at));
});
app.get("/api/objects/:id", auth, (req, res) => {
  const o = db.objects.find((o) => o.id === req.params.id && o.uid === req.uid);
  if (!o) return res.status(404).json({ error: "not found" });
  res.json(o);
});
app.post("/api/objects", auth, (req, res) => {
  const o = { id: crypto.randomUUID(), uid: req.uid, name: req.body?.name || "Об'єкт", data: req.body?.data || {}, updated_at: Date.now() };
  db.objects.push(o); persist();
  res.json({ id: o.id, name: o.name, updated_at: o.updated_at });
});
app.put("/api/objects/:id", auth, (req, res) => {
  const o = db.objects.find((o) => o.id === req.params.id && o.uid === req.uid);
  if (!o) return res.status(404).json({ error: "not found" });
  if (req.body?.name != null) o.name = req.body.name;
  if (req.body?.data != null) o.data = req.body.data;
  o.updated_at = Date.now(); persist();
  res.json({ id: o.id, name: o.name, updated_at: o.updated_at });
});
app.delete("/api/objects/:id", auth, (req, res) => {
  const i = db.objects.findIndex((o) => o.id === req.params.id && o.uid === req.uid);
  if (i < 0) return res.status(404).json({ error: "not found" });
  db.objects.splice(i, 1); persist();
  res.json({ ok: true });
});

app.listen(PORT, () => console.log(`Wallcov cabinet на :${PORT}`));
