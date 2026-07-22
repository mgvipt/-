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

// карта: картка -> реальний канал (kind) / e-chat платформа
const CARD_MAP: Record<string, { kind?: string; platform?: "viber" | "telegram" | "whatsapp" }> = {
  instagram: { kind: "instagram" }, facebook: { kind: "facebook" },
  telegram_bot: { kind: "telegram" }, telegram_phone: { kind: "echat_telegram", platform: "telegram" },
  tiktok: { kind: "tiktok" }, viber_bot: {}, viber_phone: { kind: "echat", platform: "viber" },
  whatsapp: { kind: "echat_whatsapp", platform: "whatsapp" },
};

// ─── Сторінка ──────────────────────────────────────────────────────────────
export default function ContactCenter() {
  const [channels, setChannels] = useState<Channel[]>(FALLBACK);
  const [sel, setSel] = useState<Channel | null>(null);
  const [msg, setMsg] = useState("");
  const [realChans, setRealChans] = useState<any[]>([]);
  const { t } = useLang();

  function loadReal() { api.get<any>("/api/channels/").then((d) => setRealChans((d.results || d) as any[])).catch(() => {}); }
  useEffect(() => {
    api.get<Channel[]>("/api/contact-center/").then((d) => { if (Array.isArray(d) && d.length) setChannels(d); }).catch(() => {});
    loadReal();
  }, []);
  async function toggleChannelActive(id: number, active: boolean) {
    try { await api.post(`/api/channels/${id}/set_active/`, { active }); loadReal(); setMsg(active ? t("✓ Канал включён","✓ Канал увімкнено") : t("✓ Канал отключён от CRM","✓ Канал відключено від CRM")); }
    catch (e: any) { setMsg(e?.response?.data?.detail || t("Ошибка","Помилка")); }
  }

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

            {(() => {
              const map = CARD_MAP[sel.key] || {};
              const rc = map.kind ? realChans.find((c: any) => c.kind === map.kind) : null;
              return (<>
                {/* Статус + активність */}
                <div className="panel" style={{ marginBottom: 14 }}>
                  <div className="label">{t("Статус подключения","Статус підключення")}</div>
                  {map.platform ? (
                    <div className="muted" style={{ fontSize: 12.5 }}>{t("Номера, ключ, вебхук, вкл/выкл и доступ — в блоке ниже.","Номери, ключ, вебхук, увімк/вимк і доступ — у блоці нижче.")}</div>
                  ) : rc ? (<>
                    <div style={{ color: rc.is_active ? "#16a34a" : "#d97706", fontWeight: 600 }}>{rc.is_active ? "● " + t("Подключено","Підключено") : "○ " + t("Отключено","Відключено")}{sel.via ? ` · ${sel.via}` : ""}</div>
                    <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                      <button className="btn" style={{ color: rc.is_active ? "#dc2626" : "#16a34a" }} onClick={() => toggleChannelActive(rc.id, !rc.is_active)}>{rc.is_active ? t("Отключить от CRM","Відключити від CRM") : t("Включить","Увімкнути")}</button>
                      {sel.via === "ChatPlace" && <button className="btn btn-primary" onClick={() => channelAction(sel)}>↻ {t("Синхронизировать","Синхронізувати")}</button>}
                    </div>
                  </>) : (<>
                    <div style={{ color: "#d97706", fontWeight: 600 }}>○ {t("Не подключено","Не підключено")}</div>
                    <button className="btn btn-primary" style={{ marginTop: 10 }} onClick={() => channelAction(sel)}>+ {t("Подключить канал","Підключити канал")}</button>
                  </>)}
                  {msg && <div style={{ marginTop: 10, fontSize: 12.5, color: "#475569", background: "#f8fafc", borderRadius: 8, padding: "8px 10px" }}>{msg}</div>}
                </div>

                {/* e-chat: підключення номерів + доступ/вимк на кожній лінії */}
                {map.platform && <div className="panel" style={{ marginBottom: 14 }}>
                  <div className="label">{t("Номера e-chat","Номери e-chat")}</div>
                  <EchatBlock t={t} only={map.platform} />
                </div>}

                {/* Доступ менеджерів (не-e-chat реальні канали) */}
                {!map.platform && rc && <div className="panel" style={{ marginBottom: 14 }}>
                  <div className="label">{t("Очередь ответственных · доступ менеджеров","Черга відповідальних · доступ менеджерів")}</div>
                  <ChannelAccessPanel channelId={rc.id} t={t} />
                </div>}
                {!map.platform && !rc && <div className="panel" style={{ marginBottom: 14 }}>
                  <div className="label">{t("Доступ менеджеров","Доступ менеджерів")}</div>
                  <div className="muted" style={{ fontSize: 12.5 }}>{t("Доступ можно настроить после подключения канала.","Доступ можна налаштувати після підключення каналу.")}</div>
                </div>}
              </>);
            })()}

            <div className="muted" style={{ fontSize: 12 }}>{t("Канал-ключ","Канал-ключ")}: <code>{sel.key}</code></div>
          </div>
        </div>
      )}
    </div>
  );
}


// ─── Блок: Viber + Telegram особистого номера через e-chat.tech ─────────────
function ChannelAccessPanel({ channelId, t }: { channelId: number; t: any }) {
  const [staff, setStaff] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  async function load() { try { const d = await api.get<any>(`/api/channels/${channelId}/access/`); setStaff(d.staff || []); } catch { setStaff([]); } setLoading(false); }
  useEffect(() => { setLoading(true); load(); /* eslint-disable-next-line */ }, [channelId]);
  async function toggle(u: any) { try { await api.post(`/api/channels/${channelId}/access/`, { user_id: u.id, grant: !u.has_access }); load(); } catch { /* ignore */ } }
  return (
    <div style={{ border: "1px solid #ddd6fe", borderTop: "none", borderRadius: "0 0 8px 8px", padding: "8px 10px", background: "#faf5ff" }}>
      <div style={{ fontSize: 11.5, color: "#6d28d9", fontWeight: 700, marginBottom: 6 }}>{t("Кто видит и отвечает в этом канале", "Хто бачить і відповідає в цьому каналі")}</div>
      {loading ? <div className="muted" style={{ fontSize: 12 }}>…</div> : staff.length === 0 ? <div className="muted" style={{ fontSize: 12 }}>{t("Нет сотрудников", "Немає співробітників")}</div> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 240, overflowY: "auto" }}>
          {staff.map((u) => (
            <label key={u.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, padding: "3px 4px", cursor: "pointer", borderRadius: 5 }}>
              <input type="checkbox" checked={!!u.has_access} onChange={() => toggle(u)} />
              <span style={{ flex: 1 }}>{u.full_name}</span>
              {u.via_role_dept && <span className="muted" style={{ fontSize: 10 }}>{t("через роль/отдел", "через роль/відділ")}</span>}
            </label>
          ))}
        </div>
      )}
      <div className="muted" style={{ fontSize: 10.5, marginTop: 6, lineHeight: 1.35 }}>{t("Галочка даёт сотруднику доступ к каналу. Если у него не было ограничений — он и так видит все каналы. Полное распределение — на странице «Сотрудники».", "Галочка дає співробітнику доступ до каналу. Якщо у нього не було обмежень — він і так бачить усі канали. Повний розподіл — на сторінці «Співробітники».")}</div>
    </div>
  );
}

function EchatBlock({ t, only }: any) {
  const [lines, setLines] = useState<any[]>([]);
  const [key, setKey] = useState("");
  const [num, setNum] = useState("");
  const [platform, setPlatform] = useState<"viber" | "telegram" | "whatsapp">(only || "viber");
  const [msg, setMsg] = useState("");
  const [accessFor, setAccessFor] = useState<number | null>(null);
  async function reload() {
    try {
      const d = await api.get<any>("/api/inbox/echat/setup/");
      setLines(d.channels || (d.channel_id ? [d] : []));
    } catch { /* ignore */ }
  }
  useEffect(() => { reload(); }, []);
  async function connect() {
    if (!num.trim()) { setMsg(t("Укажите номер","Вкажіть номер")); return; }
    setMsg("…");
    try {
      await api.post<any>("/api/inbox/echat/setup/", { platform, api_key: key.trim(), number: num.trim() });
      await reload(); setKey(""); setNum("");
      setMsg(t("✓ Канал подключён. Добавьте его webhook в кабинете E-chat.", "✓ Канал підключено. Додайте його webhook у кабінеті E-chat."));
    } catch (e: any) { setMsg(e?.response?.data?.detail || t("Ошибка подключения","Помилка підключення")); }
  }
  async function toggleActive(channelId: number, active: boolean) {
    try { await api.post(`/api/channels/${channelId}/set_active/`, { active }); await reload(); }
    catch (e: any) { setMsg(e?.response?.data?.detail || t("Ошибка", "Помилка")); }
  }
  const inp: any = { height: 36, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13 };
  const renderLines = (kind: "viber" | "telegram" | "whatsapp") => lines.filter((x) => (x.platform || "viber") === kind).map((line) => (
    <div key={line.channel_id} style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", padding: "8px 10px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: accessFor === line.channel_id ? "8px 8px 0 0" : 8, flexWrap: "wrap" }}>
        <span style={{ color: line.connected ? "#16a34a" : "#d97706", fontWeight: 700 }}>{line.connected ? "●" : "○"}</span>
        <b style={{ fontSize: 13, flex: 1, minWidth: 130 }}>{kind === "telegram" ? "Telegram" : kind === "whatsapp" ? "WhatsApp" : "Viber"} · +{String(line.number || "").replace(/^\+/, "")}</b>
        <span className="muted" style={{ fontSize: 11 }}>#{line.channel_id}</span>
        <button className="btn" style={{ height: 28, fontSize: 11 }} title={t("Скопировать webhook", "Скопіювати webhook")} onClick={() => navigator.clipboard?.writeText(line.webhook || "")}><Icon n="📋" size={14} /></button>
        <button className="btn" style={{ height: 28, fontSize: 11 }} title={t("Обновить ключ", "Оновити ключ")} onClick={() => { setPlatform(kind); setNum(line.number || ""); setMsg(""); }}>{t("Ключ", "Ключ")}</button>
        <button className="btn" style={{ height: 28, fontSize: 11, background: accessFor === line.channel_id ? "#ede9fe" : undefined, color: "#6d28d9" }} onClick={() => setAccessFor(accessFor === line.channel_id ? null : line.channel_id)}><Icon n="👥" size={13} /> {t("Доступ", "Доступ")}</button>
        <button className="btn" style={{ height: 28, fontSize: 11, color: line.connected ? "#dc2626" : "#16a34a" }} onClick={() => toggleActive(line.channel_id, !line.connected)}>{line.connected ? t("Отключить", "Відключити") : t("Включить", "Увімкнути")}</button>
      </div>
      {accessFor === line.channel_id && <ChannelAccessPanel channelId={line.channel_id} t={t} />}
    </div>
  ));
  return (
    <div className={only ? "" : "panel"} style={only ? {} : { margin: "0 0 18px", borderLeft: "4px solid #7360F2" }}>
      {!only && <><div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ width: 26, height: 26, borderRadius: 7, background: "#7360F2", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 700 }}>E</span>
        <b style={{ fontSize: 15 }}>E-chat · Viber + Telegram + WhatsApp</b>
        {lines.filter((x) => x.connected).length > 0 && <span className="chip" style={{ background: "#16a34a" }}>{t("подключено", "підключено")}: {lines.filter((x) => x.connected).length}</span>}
      </div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("Viber и Telegram на одном номере — отдельные линии с отдельными ключами.", "Viber і Telegram на одному номері — окремі лінії з окремими ключами.")}</div></>}
      {only ? renderLines(only) : <>{renderLines("viber")}{renderLines("telegram")}{renderLines("whatsapp")}</>}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {!only && <select style={{ ...inp, minWidth: 130 }} value={platform} onChange={(e) => setPlatform(e.target.value as "viber" | "telegram" | "whatsapp")}>
          <option value="viber">Viber</option><option value="telegram">Telegram</option><option value="whatsapp">WhatsApp</option>
        </select>}
        <input style={{ ...inp, flex: 2, minWidth: 200 }} placeholder={t(`API-ключ E-chat для ${platform === "telegram" ? "Telegram" : platform === "whatsapp" ? "WhatsApp" : "Viber"}`, `API-ключ E-chat для ${platform === "telegram" ? "Telegram" : platform === "whatsapp" ? "WhatsApp" : "Viber"}`)} value={key} onChange={(e) => setKey(e.target.value)} />
        <input style={{ ...inp, flex: 1, minWidth: 150 }} placeholder={t("Номер, напр. 380XXXXXXXXX","Номер, напр. 380XXXXXXXXX")} value={num} onChange={(e) => setNum(e.target.value)} />
        <button className="btn btn-primary" onClick={connect}>{t("Подключить / обновить", "Підключити / оновити")}</button>
        {msg && <span style={{ fontSize: 13, color: msg.startsWith("✓") ? "#16a34a" : "#b45309" }}>{msg}</span>}
      </div>
      {lines.length > 0 && <div className="muted" style={{ marginTop: 9, fontSize: 11 }}>{t("Обязательно добавьте webhook каждой линии в соответствующем кабинете E-chat; без этого ответы клиента не поступят в CRM. Кнопка 📋 копирует точный адрес.", "Обовʼязково додайте webhook кожної лінії у відповідному кабінеті E-chat; без цього відповіді клієнта не надійдуть у CRM. Кнопка 📋 копіює точну адресу.")}</div>}
    </div>
  );
}
