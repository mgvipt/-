// Платёжный слой: единый интерфейс поверх ЮKassa / Stripe / Telegram.
// Каждый провайдер: createCheckout(user, resolved) -> {url|link}; webhook -> {userId, product, amount}.
import crypto from "crypto";
import { CONFIG } from "./config.js";

// Преобразовать запрос клиента в товар с ценой.
export function resolveProduct(body) {
  if (body.product === "sub") {
    return { product: "sub", amount: CONFIG.planPrice, title: "Подписка «Умный ИИ» на " + CONFIG.planDays + " дн.", credits: 0 };
  }
  if (body.product === "credits") {
    var pack = CONFIG.creditPacks.find(p => p.id === body.packId) || CONFIG.creditPacks[0];
    return { product: "credits:" + pack.credits, amount: pack.price, title: pack.credits + " сообщений", credits: pack.credits };
  }
  return null;
}

export async function createCheckout(provider, user, r) {
  if (provider === "yookassa") return yooCreate(user, r);
  if (provider === "stripe") return stripeCreate(user, r);
  if (provider === "telegram") return tgCreate(user, r);
  throw new Error("unknown provider");
}

/* ---------- ЮKassa ---------- */
async function yooCreate(user, r) {
  var auth = Buffer.from(CONFIG.yookassa.shopId + ":" + CONFIG.yookassa.secret).toString("base64");
  var res = await fetch("https://api.yookassa.ru/v3/payments", {
    method: "POST",
    headers: { "content-type": "application/json", "Idempotence-Key": crypto.randomUUID(), Authorization: "Basic " + auth },
    body: JSON.stringify({
      amount: { value: r.amount.toFixed(2), currency: CONFIG.currency },
      capture: true,
      confirmation: { type: "redirect", return_url: CONFIG.publicUrl + "/paid" },
      description: r.title,
      metadata: { userId: user.id, product: r.product }
    })
  });
  var d = await res.json();
  if (d.type === "error") throw new Error(d.description || "yookassa error");
  return { url: d.confirmation && d.confirmation.confirmation_url };
}
export async function yooVerify(body) {
  // Подтверждаем повторным запросом статуса (не доверяем телу вебхука).
  var pid = body && body.object && body.object.id; if (!pid) return null;
  var auth = Buffer.from(CONFIG.yookassa.shopId + ":" + CONFIG.yookassa.secret).toString("base64");
  var res = await fetch("https://api.yookassa.ru/v3/payments/" + pid, { headers: { Authorization: "Basic " + auth } });
  var p = await res.json();
  if (p.status !== "succeeded" || !p.metadata) return null;
  return { userId: p.metadata.userId, product: p.metadata.product, amount: Number(p.amount && p.amount.value) || 0 };
}

/* ---------- Stripe ---------- */
async function stripeCreate(user, r) {
  var form = new URLSearchParams();
  form.set("mode", "payment");
  form.set("success_url", CONFIG.publicUrl + "/paid");
  form.set("cancel_url", CONFIG.publicUrl + "/cancelled");
  form.set("line_items[0][quantity]", "1");
  form.set("line_items[0][price_data][currency]", CONFIG.currency.toLowerCase());
  form.set("line_items[0][price_data][unit_amount]", String(Math.round(r.amount * 100)));
  form.set("line_items[0][price_data][product_data][name]", r.title);
  form.set("metadata[userId]", user.id);
  form.set("metadata[product]", r.product);
  var res = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: { Authorization: "Bearer " + CONFIG.stripe.secret, "content-type": "application/x-www-form-urlencoded" },
    body: form
  });
  var d = await res.json();
  if (d.error) throw new Error(d.error.message || "stripe error");
  return { url: d.url };
}
export function stripeVerify(rawBody, sigHeader) {
  // Проверка подписи вебхука Stripe.
  if (!CONFIG.stripe.webhookSecret || !sigHeader) return null;
  var parts = {}; sigHeader.split(",").forEach(kv => { var i = kv.indexOf("="); parts[kv.slice(0, i)] = kv.slice(i + 1); });
  var signed = parts.t + "." + rawBody;
  var expected = crypto.createHmac("sha256", CONFIG.stripe.webhookSecret).update(signed).digest("hex");
  if (!parts.v1 || !safeEq(expected, parts.v1)) return null;
  var evt = JSON.parse(rawBody);
  if (evt.type !== "checkout.session.completed") return null;
  var m = evt.data.object.metadata || {};
  return { userId: m.userId, product: m.product, amount: (evt.data.object.amount_total || 0) / 100 };
}
function safeEq(a, b) { var x = Buffer.from(a), y = Buffer.from(b); return x.length === y.length && crypto.timingSafeEqual(x, y); }

/* ---------- Telegram ---------- */
async function tgCreate(user, r) {
  var res = await fetch("https://api.telegram.org/bot" + CONFIG.telegram.botToken + "/createInvoiceLink", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({
      title: r.title, description: "Цикл вдвоём",
      payload: JSON.stringify({ userId: user.id, product: r.product }),
      provider_token: CONFIG.telegram.providerToken,
      currency: CONFIG.currency,
      prices: [{ label: r.title, amount: Math.round(r.amount * 100) }]
    })
  });
  var d = await res.json();
  if (!d.ok) throw new Error((d.description) || "telegram error");
  return { url: d.result };
}
// Разбор апдейта Telegram: возвращает {answerPreCheckout} или {grant:{userId,product,amount}}.
export function tgParseUpdate(update) {
  if (update.pre_checkout_query) return { answerPreCheckout: update.pre_checkout_query.id };
  var sp = update.message && update.message.successful_payment;
  if (sp) {
    var p = {}; try { p = JSON.parse(sp.invoice_payload); } catch (e) {}
    return { grant: { userId: p.userId, product: p.product, amount: (sp.total_amount || 0) / 100 } };
  }
  return {};
}
export async function tgAnswerPreCheckout(id) {
  await fetch("https://api.telegram.org/bot" + CONFIG.telegram.botToken + "/answerPreCheckoutQuery", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ pre_checkout_query_id: id, ok: true })
  });
}
