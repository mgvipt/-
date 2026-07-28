// Лимиты: бесплатный дневной лимит + подписка (лимит в период) + кредиты.
import { CONFIG } from "./config.js";
import { markDirty } from "./store.js";

function today() { return new Date().toISOString().slice(0, 10); }

export function resetFree(u) {
  if (u.freeDate !== today()) { u.freeDate = today(); u.freeUsed = 0; markDirty(); }
}
export function subActive(u) { return !!(u.sub && u.sub.periodEnd > Date.now()); }

export function status(u) {
  resetFree(u);
  var freeRemaining = Math.max(0, CONFIG.freeDaily - u.freeUsed);
  var sub = subActive(u)
    ? { active: true, cap: u.sub.cap, used: u.sub.used, remaining: Math.max(0, u.sub.cap - u.sub.used), periodEnd: u.sub.periodEnd, plan: u.sub.plan }
    : null;
  var canChat = (sub && sub.remaining > 0) || u.credits > 0 || freeRemaining > 0;
  return {
    canChat: canChat,
    free: { used: u.freeUsed, limit: CONFIG.freeDaily, remaining: freeRemaining },
    sub: sub,
    credits: u.credits,
    plan: { price: CONFIG.planPrice, cap: CONFIG.planCap, days: CONFIG.planDays, currency: CONFIG.currency },
    packs: CONFIG.creditPacks
  };
}

// Определить, из какого «кошелька» списать (без списания).
export function pick(u) {
  resetFree(u);
  if (subActive(u) && u.sub.used < u.sub.cap) return "sub";
  if (u.credits > 0) return "credits";
  if (u.freeUsed < CONFIG.freeDaily) return "free";
  return null;
}
// Списать 1 сообщение из выбранного кошелька.
export function consume(u, bucket) {
  if (bucket === "sub") u.sub.used += 1;
  else if (bucket === "credits") u.credits = Math.max(0, u.credits - 1);
  else if (bucket === "free") u.freeUsed += 1;
  markDirty();
}

// Начислить покупку.
export function grant(u, product) {
  if (product === "sub") {
    u.sub = { plan: "monthly", cap: CONFIG.planCap, used: 0, periodEnd: Date.now() + CONFIG.planDays * 86400000 };
  } else if (String(product).indexOf("credits:") === 0) {
    var n = Number(String(product).split(":")[1]) || 0;
    u.credits += n;
  }
  markDirty();
}
