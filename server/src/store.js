// Простое хранилище на JSON-файле (MVP). Для масштаба — заменить на Postgres.
import fs from "fs";
import crypto from "crypto";
import { CONFIG } from "./config.js";

let db = { users: {}, byToken: {}, payments: [] };
let dirty = false;

export function load() {
  try {
    if (fs.existsSync(CONFIG.dataFile)) {
      db = JSON.parse(fs.readFileSync(CONFIG.dataFile, "utf8"));
      db.users = db.users || {}; db.byToken = db.byToken || {}; db.payments = db.payments || [];
    }
  } catch (e) { console.error("store load failed:", e.message); }
}
function flush() {
  if (!dirty) return; dirty = false;
  try { fs.writeFileSync(CONFIG.dataFile, JSON.stringify(db)); }
  catch (e) { console.error("store write failed:", e.message); }
}
export function markDirty() { dirty = true; }
setInterval(flush, 2000).unref?.();
process.on("SIGINT", () => { flush(); process.exit(0); });
process.on("SIGTERM", () => { flush(); process.exit(0); });

function id(prefix) { return prefix + crypto.randomBytes(9).toString("hex"); }

export function createUser() {
  var u = {
    id: id("usr_"), token: id("tok_"), created: Date.now(),
    email: null,
    freeDate: "", freeUsed: 0,
    credits: 0,
    sub: null,                 // { plan, cap, used, periodEnd }
    totalMsgs: 0, totalInTok: 0, totalOutTok: 0, totalCostUsd: 0
  };
  db.users[u.id] = u; db.byToken[u.token] = u.id; markDirty();
  return u;
}
export function getById(uid) { return db.users[uid] || null; }
export function getByToken(token) { var uid = db.byToken[token]; return uid ? db.users[uid] : null; }
export function recordPayment(p) { db.payments.push(Object.assign({ at: Date.now() }, p)); markDirty(); }

export function stats() {
  var users = Object.values(db.users);
  var revenue = db.payments.reduce((s, p) => s + (p.amount || 0), 0);
  var cost = users.reduce((s, u) => s + (u.totalCostUsd || 0), 0);
  return {
    users: users.length,
    activeSubs: users.filter(u => u.sub && u.sub.periodEnd > Date.now()).length,
    totalMsgs: users.reduce((s, u) => s + (u.totalMsgs || 0), 0),
    revenue, currency: CONFIG.currency,
    llmCostUsd: Math.round(cost * 10000) / 10000,
    payments: db.payments.length
  };
}
