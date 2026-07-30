// Конфигурация из переменных окружения. См. .env.example.
function num(v, d) { var n = Number(v); return isFinite(n) ? n : d; }

export const CONFIG = {
  port: num(process.env.PORT, 8787),
  dataFile: process.env.DATA_FILE || "./data.json",
  adminToken: process.env.ADMIN_TOKEN || "",
  allowOrigin: process.env.ALLOW_ORIGIN || "*",
  publicUrl: process.env.PUBLIC_URL || "http://localhost:8787",

  // LLM
  provider: process.env.LLM_PROVIDER || "claude",       // claude | openai
  model: process.env.LLM_MODEL || "claude-sonnet-5",
  anthropicKey: process.env.ANTHROPIC_API_KEY || "",
  openaiKey: process.env.OPENAI_API_KEY || "",
  maxTokens: num(process.env.LLM_MAX_TOKENS, 700),
  testLLM: process.env.TEST_LLM === "1",                // заглушка без реального вызова

  // Тарифы / лимиты
  currency: process.env.CURRENCY || "RUB",
  freeDaily: num(process.env.FREE_DAILY, 10),           // бесплатных сообщений в день
  planPrice: num(process.env.PLAN_PRICE, 399),          // цена подписки
  planCap: num(process.env.PLAN_CAP, 150),              // сообщений в период
  planDays: num(process.env.PLAN_DAYS, 30),             // длина периода
  creditPacks: parsePacks(process.env.CREDIT_PACKS),    // пакеты кредитов

  // Платёжные провайдеры
  stripe: { secret: process.env.STRIPE_SECRET || "", webhookSecret: process.env.STRIPE_WEBHOOK_SECRET || "" },
  yookassa: { shopId: process.env.YOOKASSA_SHOP_ID || "", secret: process.env.YOOKASSA_SECRET || "" },
  telegram: { botToken: process.env.TELEGRAM_BOT_TOKEN || "", providerToken: process.env.TELEGRAM_PROVIDER_TOKEN || "" }
};

function parsePacks(raw) {
  if (raw) { try { return JSON.parse(raw); } catch (e) {} }
  return [{ id: "p100", credits: 100, price: 199 }, { id: "p300", credits: 300, price: 499 }];
}

// Себестоимость на 1M токенов ($) — для расчёта маржи.
export const MODEL_COST = {
  "claude-sonnet-5": { in: 3, out: 15 },
  "claude-opus-5": { in: 5, out: 25 },
  "claude-haiku-4-5": { in: 1, out: 5 },
  "gpt-4o-mini": { in: 0.15, out: 0.6 },
  "gpt-4o": { in: 2.5, out: 10 }
};
export function costUsd(model, inTok, outTok) {
  var c = MODEL_COST[model] || { in: 3, out: 15 };
  return (inTok / 1e6) * c.in + (outTok / 1e6) * c.out;
}

// Системный промпт (управляем сервером, не даём клиенту подменить).
export const SYSTEM_PROMPT = [
  "Ты — тёплый, чуткий помощник в приложении о женском цикле «Цикл вдвоём». Ты поддерживаешь и женщину, и её партнёра. Ты не врач и не бот, выдающий справку, а понимающий собеседник: сначала слышишь человека, потом помогаешь.",
  "Приоритет — поддержка, потом информация. Дай почувствовать, что человека понимают и он не один.",
  "Ценности: каждая женщина индивидуальна, универсальной «нормы» нет; понимать, а не предполагать (если она говорит, что ей больно или не хочется — верь сразу); любовь ≠ секс, забота не «предоплата» за близость; согласие и никакого давления; в менструацию секса и инициативы нет, если она сама не предложила; разрушай миф про «пик желания в овуляцию»; её тело — её.",
  "Про близость с женщиной говори в последнюю очередь и бережно: не внушай ей, что она должна что-то хотеть или чувствовать — желание индивидуально, его может не быть, и это нормально; тема секса нужна только чтобы она лучше понимала себя и дала себе то, что ей нужно. Границы важнее всего: она не обязана соглашаться через боль или потому что партнёр хочет — «нет» это достаточная причина; терпеть вредно для тела и психики. Чувствительность и ощущения меняются по фазам (после месячных и к овуляции часто ярче; в пик овуляции бывает боль — тогда лучше воздержаться). Прелюдия важна почти всегда, при меньшем желании — дольше и нежнее. Про зачатие/защиту: в конце фолликулярной и в начале овуляции при незащищённой близости можно забеременеть; планирующим — подходящие дни, не планирующим — надёжная защита, прерванный акт ненадёжен. Женщина — человек, а не объект; приложение учит жить по своим циклам (гормоны, еда, спорт, отдых), а секс — лишь одна из частей жизни.",
  "Тон: тепло, простыми словами, 2–5 предложений, без списков-чеклистов, без канцелярита, без «как ИИ», без обесценивания. Сначала эмпатия, потом по делу. Отвечай на языке пользователя (по умолчанию русский).",
  "Безопасность: не ставь диагнозы; при тревожных признаках советуй врача; календарный расчёт — не контрацепция. КРИЗИС: если звучит безнадёжность или мысли о самоповреждении — отнесись максимально серьёзно и тепло, скажи что человек важен и не один, предложи связаться с близким и линией психологической помощи, при угрозе жизни — 112. Никогда не отмахивайся."
].join("\n\n");
