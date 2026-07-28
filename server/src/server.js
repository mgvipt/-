import express from "express";
import { CONFIG, costUsd } from "./config.js";
import * as store from "./store.js";
import * as quota from "./quota.js";
import { chat } from "./llm.js";
import * as billing from "./billing.js";

store.load();
const app = express();

// CORS
app.use((req, res, next) => {
  res.set("Access-Control-Allow-Origin", CONFIG.allowOrigin);
  res.set("Access-Control-Allow-Headers", "content-type, authorization");
  res.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

// Stripe webhook needs the raw body — register before express.json().
app.post("/v1/webhooks/stripe", express.raw({ type: "*/*" }), (req, res) => {
  try {
    var g = billing.stripeVerify(req.body.toString("utf8"), req.get("stripe-signature"));
    if (g && g.userId) applyGrant(g);
    res.json({ ok: true });
  } catch (e) { res.status(400).json({ error: e.message }); }
});

app.use(express.json({ limit: "256kb" }));

function auth(req, res, next) {
  var h = req.get("authorization") || "";
  var token = h.indexOf("Bearer ") === 0 ? h.slice(7) : "";
  var u = token && store.getByToken(token);
  if (!u) return res.status(401).json({ error: "unauthorized" });
  req.user = u; next();
}
function applyGrant(g) {
  var u = store.getById(g.userId); if (!u) return;
  quota.grant(u, g.product);
  store.recordPayment({ userId: g.userId, product: g.product, amount: g.amount || 0, currency: CONFIG.currency });
}

app.get("/health", (req, res) => res.json({ ok: true }));

// Аккаунт (устройство). Токен хранится на устройстве клиента.
app.post("/v1/account/init", (req, res) => {
  var u = store.createUser();
  res.json({ userId: u.id, token: u.token });
});

app.get("/v1/me", auth, (req, res) => res.json(quota.status(req.user)));

// Чат с проверкой лимита.
app.post("/v1/chat", auth, async (req, res) => {
  var u = req.user;
  var bucket = quota.pick(u);
  if (!bucket) return res.status(402).json({ error: "quota_exceeded", status: quota.status(u) });
  var messages = Array.isArray(req.body.messages) ? req.body.messages.slice(-20) : [];
  var c = req.body.ctx || {};
  var context = "Контекст: пользователь — " + (c.role === "partner" ? "партнёр" : "женщина") +
    (c.phaseName ? (". Фаза цикла: " + c.phaseName + ", день " + (c.day || "?") + " из " + (c.len || "?")) : "") +
    (c.mood ? (". Настроение: " + c.mood) : "") + ".";
  try {
    var out = await chat(messages, context);
    quota.consume(u, bucket);
    u.totalMsgs += 1; u.totalInTok += out.inTok; u.totalOutTok += out.outTok;
    u.totalCostUsd += costUsd(out.model, out.inTok, out.outTok);
    store.markDirty();
    res.json({ text: out.text, bucket: bucket, status: quota.status(u) });
  } catch (e) {
    res.status(502).json({ error: "llm_error", message: e.message });
  }
});

// Создать оплату (подписка или пакет кредитов).
app.post("/v1/billing/checkout", auth, async (req, res) => {
  var r = billing.resolveProduct(req.body || {});
  if (!r) return res.status(400).json({ error: "bad_product" });
  var provider = req.body.provider || "yookassa";
  try {
    var out = await billing.createCheckout(provider, req.user, r);
    res.json({ url: out.url, provider: provider, amount: r.amount, currency: CONFIG.currency });
  } catch (e) { res.status(502).json({ error: "checkout_error", message: e.message }); }
});

// Вебхуки
app.post("/v1/webhooks/yookassa", async (req, res) => {
  try { var g = await billing.yooVerify(req.body); if (g && g.userId) applyGrant(g); res.json({ ok: true }); }
  catch (e) { res.status(400).json({ error: e.message }); }
});
app.post("/v1/webhooks/telegram", async (req, res) => {
  try {
    var out = billing.tgParseUpdate(req.body || {});
    if (out.answerPreCheckout) await billing.tgAnswerPreCheckout(out.answerPreCheckout);
    if (out.grant && out.grant.userId) applyGrant(out.grant);
    res.json({ ok: true });
  } catch (e) { res.status(400).json({ error: e.message }); }
});

// Админ-статистика (маржа): выручка vs себестоимость LLM.
app.get("/v1/admin/stats", (req, res) => {
  if (!CONFIG.adminToken || req.query.token !== CONFIG.adminToken) return res.status(403).json({ error: "forbidden" });
  res.json(store.stats());
});

// Тестовое начисление (только при TEST_LLM=1) — для локальной проверки без платёжки.
if (CONFIG.testLLM) {
  app.post("/v1/test/grant", auth, (req, res) => {
    applyGrant({ userId: req.user.id, product: req.body.product, amount: req.body.amount || 0 });
    res.json(quota.status(req.user));
  });
}

app.get("/paid", (req, res) => res.send("<h2>Оплата прошла. Вернитесь в приложение.</h2>"));
app.get("/cancelled", (req, res) => res.send("<h2>Оплата отменена.</h2>"));

app.listen(CONFIG.port, () => console.log("Цикл вдвоём API на :" + CONFIG.port + (CONFIG.testLLM ? " (TEST_LLM)" : "")));
