// Wallcov «Кабінет»: авторизація, синхронізація кошторисів, доступ клієнта (тільки його об'єкти),
// відновлення пароля по email.
// Стек: Node + Express, сховище — JSON-файл. Дані: /app/data/db.json (volume).
// ENV: JWT_SECRET, SIGNUP_CODE, APP_URL, PORT, DB_FILE,
//      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM (для відновлення пароля).

import express from "express";
import cors from "cors";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import nodemailer from "nodemailer";

const PORT = process.env.PORT || 8090;
const SECRET = process.env.JWT_SECRET || "change-me-please";
const SIGNUP_CODE = process.env.SIGNUP_CODE || "";
const APP_URL = (process.env.APP_URL || "https://calc.wallcovdec.com.ua").replace(/\/$/, "");
const DB_FILE = process.env.DB_FILE || "./data/db.json";

fs.mkdirSync(path.dirname(DB_FILE), { recursive: true });
let db = { users: [], objects: [] };
try { db = JSON.parse(fs.readFileSync(DB_FILE, "utf8")); } catch (_) {}
let t = null;
function persist() { clearTimeout(t); t = setTimeout(() => {
  const tmp = DB_FILE + ".tmp"; fs.writeFileSync(tmp, JSON.stringify(db)); fs.renameSync(tmp, DB_FILE);
}, 50); }

// --- mail ---
let transporter = null;
if (process.env.SMTP_HOST) {
  transporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: +(process.env.SMTP_PORT || 587),
    secure: +(process.env.SMTP_PORT || 587) === 465,
    auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS } : undefined,
  });
}
async function sendMail(to, subject, text) {
  if (!transporter) { console.log("[MAIL вимкнено] →", to, "|", subject, "|", text); return false; }
  await transporter.sendMail({ from: process.env.MAIL_FROM || "Wallcov <no-reply@wallcovdec.com.ua>", to, subject, text });
  return true;
}

// --- helpers ---
const hashPw = (pw, salt = crypto.randomBytes(16).toString("hex")) => salt + ":" + crypto.scryptSync(pw, salt, 32).toString("hex");
function checkPw(pw, stored) {
  const [salt, h] = String(stored).split(":");
  const a = Buffer.from(crypto.scryptSync(pw, salt, 32).toString("hex")), b = Buffer.from(h);
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
const norm = (e) => String(e || "").toLowerCase().trim();

const app = express();
app.use(cors());
app.use(express.json({ limit: "25mb" }));
app.get("/health", (_q, r) => r.json({ ok: true }));

// --- auth ---
app.post("/auth/register", (req, res) => {
  const { login, password, email, code } = req.body || {};
  if (SIGNUP_CODE && code !== SIGNUP_CODE) return res.status(403).json({ error: "Невірний код запрошення" });
  if (!login || !password || !email) return res.status(400).json({ error: "Вкажіть логін, email і пароль" });
  if (db.users.find((u) => u.login === login)) return res.status(409).json({ error: "Такий логін вже існує" });
  if (db.users.find((u) => u.email === norm(email))) return res.status(409).json({ error: "Такий email вже зареєстровано" });
  const user = { id: crypto.randomUUID(), login, email: norm(email), pass: hashPw(password) };
  db.users.push(user); persist();
  res.json({ token: sign({ uid: user.id, login }), login, email: user.email });
});
app.post("/auth/login", (req, res) => {
  const { login, password } = req.body || {};
  const user = db.users.find((u) => u.login === login || u.email === norm(login));
  if (!user || !checkPw(password, user.pass)) return res.status(401).json({ error: "Невірний логін або пароль" });
  res.json({ token: sign({ uid: user.id, login: user.login }), login: user.login, email: user.email || "" });
});
app.post("/auth/forgot", async (req, res) => {
  const email = norm(req.body?.email);
  const user = db.users.find((u) => u.email === email);
  if (user) {
    const token = crypto.randomBytes(24).toString("hex");
    user.reset = { token, exp: Date.now() + 3600000 }; persist();
    const link = `${APP_URL}/?reset=${token}`;
    try { await sendMail(email, "Відновлення пароля Wallcov", `Щоб встановити новий пароль, перейдіть за посиланням:\n${link}\n\nПосилання дійсне 1 годину. Якщо ви не запитували — проігноруйте цей лист.`); }
    catch (e) { console.error("mail error", e); }
  }
  res.json({ ok: true }); // не розкриваємо, чи існує email
});
app.post("/auth/reset", (req, res) => {
  const { token, password } = req.body || {};
  if (!token || !password) return res.status(400).json({ error: "Потрібні токен і новий пароль" });
  const user = db.users.find((u) => u.reset && u.reset.token === token && u.reset.exp > Date.now());
  if (!user) return res.status(400).json({ error: "Посилання недійсне або застаріле" });
  user.pass = hashPw(password); delete user.reset; persist();
  res.json({ ok: true });
});

function auth(req, res, next) {
  const p = verify((req.get("authorization") || "").replace(/^Bearer /, ""));
  if (!p) return res.status(401).json({ error: "unauthorized" });
  req.user = db.users.find((u) => u.id === p.uid);
  if (!req.user) return res.status(401).json({ error: "unauthorized" });
  next();
}

app.put("/api/account", auth, (req, res) => {
  if (req.body?.email != null) {
    const e = norm(req.body.email);
    if (e && db.users.find((u) => u.email === e && u.id !== req.user.id)) return res.status(409).json({ error: "email зайнятий" });
    req.user.email = e;
  }
  if (req.body?.password) req.user.pass = hashPw(req.body.password);
  persist(); res.json({ ok: true, email: req.user.email || "" });
});

// --- об'єкти (власник = виконавець; клієнт бачить об'єкти, де clientEmail === його email) ---
const roleOf = (o, user) => (o.uid === user.id ? "owner" : (o.clientEmail && o.clientEmail === user.email ? "client" : null));

app.get("/api/objects", auth, (req, res) => {
  const list = db.objects
    .map((o) => ({ o, role: roleOf(o, req.user) }))
    .filter((x) => x.role)
    .map((x) => ({ id: x.o.id, name: x.o.name, updated_at: x.o.updated_at, role: x.role, clientEmail: x.role === "owner" ? (x.o.clientEmail || "") : undefined }))
    .sort((a, b) => b.updated_at - a.updated_at);
  res.json(list);
});
app.get("/api/objects/:id", auth, (req, res) => {
  const o = db.objects.find((o) => o.id === req.params.id);
  if (!o) return res.status(404).json({ error: "not found" });
  const role = roleOf(o, req.user);
  if (!role) return res.status(403).json({ error: "немає доступу" });
  res.json({ id: o.id, name: o.name, data: o.data, updated_at: o.updated_at, role, clientEmail: role === "owner" ? (o.clientEmail || "") : undefined });
});
app.post("/api/objects", auth, (req, res) => {
  const o = { id: crypto.randomUUID(), uid: req.user.id, name: req.body?.name || "Об'єкт",
    clientEmail: norm(req.body?.clientEmail), data: req.body?.data || {}, updated_at: Date.now() };
  db.objects.push(o); persist();
  res.json({ id: o.id, name: o.name, updated_at: o.updated_at, role: "owner", clientEmail: o.clientEmail });
});
app.put("/api/objects/:id", auth, (req, res) => {
  const o = db.objects.find((o) => o.id === req.params.id);
  if (!o) return res.status(404).json({ error: "not found" });
  if (o.uid !== req.user.id) return res.status(403).json({ error: "лише власник може редагувати" });
  if (req.body?.name != null) o.name = req.body.name;
  if (req.body?.data != null) o.data = req.body.data;
  if (req.body?.clientEmail != null) o.clientEmail = norm(req.body.clientEmail);
  o.updated_at = Date.now(); persist();
  res.json({ id: o.id, name: o.name, updated_at: o.updated_at, role: "owner", clientEmail: o.clientEmail });
});
// Запросити клієнта по email: прив'язати до об'єкта, створити акаунт (за потреби) і надіслати лист зі ссиланням на встановлення пароля
app.post("/api/objects/:id/invite", auth, async (req, res) => {
  const o = db.objects.find((o) => o.id === req.params.id);
  if (!o) return res.status(404).json({ error: "not found" });
  if (o.uid !== req.user.id) return res.status(403).json({ error: "лише власник може запрошувати" });
  const email = norm(req.body?.clientEmail);
  if (!email) return res.status(400).json({ error: "Вкажіть email клієнта" });
  o.clientEmail = email; o.updated_at = Date.now();
  let u = db.users.find((x) => x.email === email);
  let invited = false;
  if (!u) { u = { id: crypto.randomUUID(), login: email, email, pass: hashPw(crypto.randomBytes(9).toString("hex")) }; db.users.push(u); invited = true; }
  const token = crypto.randomBytes(24).toString("hex");
  u.reset = { token, exp: Date.now() + 7 * 24 * 3600000 }; persist();
  const link = `${APP_URL}/?reset=${token}`;
  const sent = await sendMail(email, "Доступ до кошторису Wallcov",
    `Вам відкрито доступ до об'єкта «${o.name}».\n\nЛогін (email): ${email}\nВстановіть пароль за посиланням (діє 7 днів):\n${link}\n\nПісля цього заходьте: ${APP_URL}`).catch(() => false);
  res.json({ ok: true, invited, mailed: !!sent });
});

app.delete("/api/objects/:id", auth, (req, res) => {
  const i = db.objects.findIndex((o) => o.id === req.params.id);
  if (i < 0) return res.status(404).json({ error: "not found" });
  if (db.objects[i].uid !== req.user.id) return res.status(403).json({ error: "лише власник може видаляти" });
  db.objects.splice(i, 1); persist();
  res.json({ ok: true });
});

app.listen(PORT, () => console.log(`Wallcov cabinet на :${PORT} (mail: ${transporter ? "увімкнено" : "вимкнено"})`));
