/* ============================================================================
 * КОНТАКТ-ЦЕНТР (як у Бітриксі) — каталог усіх каналів звʼязку з клієнтом.
 * Кожна плитка = канал. Статус: підключено / доступно. Клік → панель налаштувань
 * (черга менеджерів + доступи + підключення).
 * Дані каналів: GET /api/contact-center/  (бекенд: ContactCenterView).
 * ========================================================================== */
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

// ─── Тип каналу ────────────────────────────────────────────────────────────
interface Channel {
  key: string;
  name: string;
  sub: string;          // що саме (Direct + Коментарі тощо)
  icon: string;
  color: string;
  status: "connected" | "available";
  via?: string;         // через що підключено (ChatPlace / Meta API)
  managers?: string[];  // черга відповідальних
}

// ─── Каталог каналів (порядок як у Бітриксі) ───────────────────────────────
const FALLBACK: Channel[] = [
  { key: "instagram", name: "Instagram", sub: "Direct + Коментарі", icon: "instagram", color: "#E1306C", status: "connected", via: "ChatPlace" },
  { key: "facebook", name: "Facebook", sub: "Messenger + Коментарі", icon: "facebook", color: "#1877F2", status: "available" },
  { key: "telegram_bot", name: "Telegram бот", sub: "Бот для клієнтів", icon: "telegram", color: "#229ED9", status: "connected", via: "ChatPlace" },
  { key: "telegram_phone", name: "Telegram (номер)", sub: "Клієнт пише на ваш номер", icon: "telegram", color: "#229ED9", status: "available" },
  { key: "tiktok", name: "TikTok", sub: "Повідомлення", icon: "tiktok", color: "#111827", status: "connected", via: "ChatPlace" },
  { key: "viber_bot", name: "Viber бот", sub: "Бот для клієнтів", icon: "viber", color: "#7360F2", status: "available" },
  { key: "viber_phone", name: "Viber (номер)", sub: "Клієнт пише на ваш номер", icon: "viber", color: "#7360F2", status: "available" },
  { key: "whatsapp", name: "WhatsApp", sub: "Повідомлення", icon: "whatsapp", color: "#25D366", status: "available" },
];

// ─── Сторінка ──────────────────────────────────────────────────────────────
export default function ContactCenter() {
  const [channels, setChannels] = useState<Channel[]>(FALLBACK);
  const [sel, setSel] = useState<Channel | null>(null);
  const [msg, setMsg] = useState("");
  const { t } = useLang();

  useEffect(() => {
    api.get<Channel[]>("/api/contact-center/").then((d) => { if (Array.isArray(d) && d.length) setChannels(d); }).catch(() => {});
  }, []);

  // ─── Дія кнопки картки: ChatPlace-канали синхронізуємо, інші — інструкція ───
  async function channelAction(ch: Channel) {
    setMsg("…");
    if (ch.via === "ChatPlace") {
      try { const r = await api.post<any>("/api/inbox/chatplace/sync/", {}); setMsg(`✓ ${t("Синхронизировано","Синхронізовано")}: ${r.new_messages ?? 0} ${t("новых сообщений","нових повідомлень")}, ${r.chats ?? 0} ${t("чатов","чатів")}`); }
      catch { setMsg(t("Ошибка синхронизации ChatPlace","Помилка синхронізації ChatPlace")); }
    } else {
      const need: Record<string, string> = {
        facebook: t("Нужен Facebook Page Access Token (pages_messaging + pages_manage_engagement). Скинь в чат Wallcov.","Потрібен Facebook Page Access Token (pages_messaging + pages_manage_engagement). Скинь у чат Wallcov."),
        telegram_phone: t("Telegram (номер): нужен MTProto-доступ (api_id/api_hash). Лучше — Telegram бот.","Telegram (номер): потрібен MTProto-доступ (api_id/api_hash). Краще — Telegram бот."),
        viber_bot: t("Viber бот: создай бота на partners.viber.com → токен.","Viber бот: створи бота на partners.viber.com → токен."),
        viber_phone: t("Viber для бизнеса (номер): нужен Viber Business / провайдер (360dialog).","Viber для бізнесу (номер): потрібен Viber Business / провайдер (360dialog)."),
        whatsapp: t("WhatsApp: нужен BSP (360dialog / Twilio / Meta Cloud API) + номер.","WhatsApp: потрібен BSP (360dialog / Twilio / Meta Cloud API) + номер."),
      };
      setMsg(need[ch.key] || t("Подключение этого канала — дай токен/доступ.","Підключення цього каналу — дай токен/доступ."));
    }
  }

  return (
    <div className="scroll fade" style={{ padding: 20 }}>
      {/* ── Заголовок ── */}
      <div style={{ display: "flex", alignItems: "center", marginBottom: 18 }}>
        <h2 style={{ margin: 0, fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}><Icon n="🎛️" size={20} /> {t("Контакт-центр","Контакт-центр")}</h2>
        <span className="muted" style={{ marginLeft: 12, fontSize: 13 }}>{t("Каналы связи с клиентами · лиды с каждого канала падают в CRM разделённо","Канали звʼязку з клієнтами · ліди з кожного каналу потрапляють у CRM окремо")}</span>
      </div>

      <EchatBlock t={t} />

      {/* ── Сітка плиток каналів ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 14 }}>
        {channels.map((ch) => (
          <div key={ch.key} onClick={() => setSel(ch)}
            style={{ position: "relative", background: ch.color, color: "#fff", borderRadius: 14, padding: "18px 16px", minHeight: 120, cursor: "pointer", boxShadow: "0 4px 14px rgba(15,23,42,.12)", transition: "transform .1s" }}
            onMouseEnter={(e) => (e.currentTarget.style.transform = "translateY(-2px)")}
            onMouseLeave={(e) => (e.currentTarget.style.transform = "")}>
            {/* статус-галочка */}
            {ch.status === "connected" && (
              <span style={{ position: "absolute", top: 10, right: 10, width: 20, height: 20, borderRadius: "50%", background: "#22c55e", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12 }}>✓</span>
            )}
            <div style={{ width: 42, height: 42, borderRadius: 12, background: "rgba(255,255,255,.22)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, fontWeight: 700, marginBottom: 12 }}><Icon n={ch.icon} size={22} /></div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>{ch.name}</div>
            <div style={{ fontSize: 11.5, opacity: .9, marginTop: 3 }}>{ch.sub}</div>
            <div style={{ fontSize: 11, marginTop: 8, opacity: .95 }}>{ch.status === "connected" ? `● ${t("Подключено","Підключено")}${ch.via ? " · " + ch.via : ""}` : t("○ Доступно для подключения","○ Доступно для підключення")}</div>
          </div>
        ))}
      </div>

      {/* ── Панель налаштувань каналу (праворуч) ── */}
      {sel && (
        <div onClick={() => setSel(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.4)", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ position: "absolute", top: 0, right: 0, width: 460, maxWidth: "92vw", height: "100%", background: "#fff", boxShadow: "-8px 0 28px rgba(15,23,42,.18)", padding: 24, overflowY: "auto" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
              <div style={{ width: 48, height: 48, borderRadius: 12, background: sel.color, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, fontWeight: 700 }}><Icon n={sel.icon} size={24} /></div>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{sel.name}</div>
                <div className="muted" style={{ fontSize: 12.5 }}>{sel.sub}</div>
              </div>
            </div>

            {/* Статус */}
            <div className="panel" style={{ marginBottom: 14 }}>
              <div className="label">{t("Статус подключения","Статус підключення")}</div>
              {sel.status === "connected"
                ? <div style={{ color: "#16a34a", fontWeight: 600 }}>● {t("Подключено","Підключено")}{sel.via ? ` ${t("через","через")} ${sel.via}` : ""}</div>
                : <div style={{ color: "#d97706", fontWeight: 600 }}>○ {t("Не подключено","Не підключено")}</div>}
              <button className="btn btn-primary" style={{ marginTop: 10 }} onClick={() => channelAction(sel)}>
                {sel.status === "connected" ? t("↻ Синхронизировать / Переподключить","↻ Синхронізувати / Перепідключити") : t("+ Подключить канал","+ Підключити канал")}
              </button>
              {msg && <div style={{ marginTop: 10, fontSize: 12.5, color: "#475569", background: "#f8fafc", borderRadius: 8, padding: "8px 10px" }}>{msg}</div>}
            </div>

            {/* Черга менеджерів + доступи (як у Бітриксі) */}
            <div className="panel" style={{ marginBottom: 14 }}>
              <div className="label">{t("Очередь ответственных · доступ менеджеров","Черга відповідальних · доступ менеджерів")}</div>
              <div className="muted" style={{ fontSize: 12.5 }}>{t("Здесь выберем, какие менеджеры видят и отвечают в этом канале. Настройка доступов — следующим шагом (бекенд очереди + роли по каналам).","Тут оберемо, які менеджери бачать і відповідають у цьому каналі. Налаштування доступів — наступним кроком (бекенд черги + ролі за каналами).")}</div>
            </div>

            <div className="muted" style={{ fontSize: 12 }}>{t("Канал-ключ","Канал-ключ")}: <code>{sel.key}</code></div>
          </div>
        </div>
      )}
    </div>
  );
}


// ─── Блок: Viber через e-chat.tech ──────────────────────────────────────────
function EchatBlock({ t }: any) {
  const [st, setSt] = useState<any>(null);
  const [key, setKey] = useState("");
  const [num, setNum] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => { api.get<any>("/api/inbox/echat/setup/").then((d) => { setSt(d); setNum(d.number || ""); }).catch(() => {}); }, []);
  async function connect() {
    if (!num.trim()) { setMsg(t("Укажите Viber-номер","Вкажіть Viber-номер")); return; }
    setMsg("…");
    try {
      const r = await api.post<any>("/api/inbox/echat/setup/", { api_key: key.trim(), number: num.trim() });
      setSt({ ...(st || {}), connected: true, channel_id: r.channel_id, webhook: r.webhook, has_key: (st && st.has_key) || !!key.trim(), number: num.trim() });
      setKey(""); setMsg(t("✓ Подключено","✓ Підключено"));
    } catch { setMsg(t("Ошибка подключения","Помилка підключення")); }
  }
  const inp: any = { height: 36, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13 };
  return (
    <div className="panel" style={{ margin: "0 0 18px", borderLeft: "4px solid #7360F2" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ width: 26, height: 26, borderRadius: 7, background: "#7360F2", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 700 }}>V</span>
        <b style={{ fontSize: 15 }}>Viber через e-chat.tech</b>
        {st?.connected && <span className="chip" style={{ background: "#16a34a" }}>{t("подключено","підключено")}</span>}
      </div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("Введите API-ключ и Viber-номер канала из панели e-chat.tech. Входящие/исходящие пойдут в Чаты CRM.","Введіть API-ключ і Viber-номер каналу з панелі e-chat.tech. Вхідні/вихідні підуть у Чати CRM.")}</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input style={{ ...inp, flex: 2, minWidth: 200 }} placeholder={st?.has_key ? t("API-ключ (сохранён, можно не вводить)","API-ключ (збережено, можна не вводити)") : "Api-Key"} value={key} onChange={(e) => setKey(e.target.value)} />
        <input style={{ ...inp, flex: 1, minWidth: 150 }} placeholder={t("Viber-номер, напр. 380XXXXXXXXX","Viber-номер, напр. 380XXXXXXXXX")} value={num} onChange={(e) => setNum(e.target.value)} />
        <button className="btn btn-primary" onClick={connect}>{st?.connected ? t("Обновить","Оновити") : t("Подключить","Підключити")}</button>
        {msg && <span style={{ fontSize: 13, color: "#16a34a" }}>{msg}</span>}
      </div>
      {st?.webhook && (
        <div style={{ marginTop: 10, padding: 10, background: "#f1f5f9", borderRadius: 8 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{t("Webhook URL — вставь в панель e-chat.tech (callback для входящих):","Webhook URL — встав у панель e-chat.tech (callback для вхідних):")}</div>
          <div style={{ display: "flex", gap: 6 }}>
            <input readOnly value={st.webhook} style={{ ...inp, flex: 1, fontSize: 12 }} onFocus={(e) => e.target.select()} />
            <button className="btn" onClick={() => navigator.clipboard?.writeText(st.webhook)}><Icon n="📋" size={16} /></button>
          </div>
        </div>
      )}
    </div>
  );
}
