import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { useAuth } from "../auth";
import SettingsGlobalRules from "./SettingsGlobalRules";
import SettingsAutomations from "./SettingsAutomations";
import SoundSettings from "./SoundSettings";
import SettingsAgent from "./SettingsAgent";
import CalculatorSettings from "./CalculatorSettings";
import { Icon } from "../Icon";

interface Prov { provider: string; fields: string[]; values: Record<string, string>; is_active: boolean; }

const TITLES: Record<string, string> = { liqpay: "LiqPay", checkbox: "Checkbox", novaposhta: "Нова Пошта", email_invoices: "Пошта накладних" };
const FIELD_LABELS: Record<string, string> = { imap_host: "IMAP-сервер (Gmail: imap.gmail.com)", email: "E-mail скриньки", app_password: "Пароль застосунку (app-password)", senders: "Відправники через кому (Нова Пошта, постачальники)" };

export default function Settings() {
  const { t, lang, setLang } = useLang();
  const { can } = useAuth();
  const canAll = can("roles.manage");
  // "" — видно всім, хто відкрив налаштування; "roles.manage" — лише адмін; "settings.*" — делегується
  const allow = (perm: string) => perm === "" ? true : (canAll || can(perm));
  const canIntegr = allow("roles.manage"); // Інтеграції = чутливі ключі, лише адмін

  const [provs, setProvs] = useState<Prov[]>([]);
  const [edit, setEdit] = useState<Record<string, Record<string, string>>>({});
  const [saved, setSaved] = useState("");
  const [library, setLibrary] = useState<any[]>([]); const [quickReplies, setQuickReplies] = useState<any[]>([]);
  const [assetFile, setAssetFile] = useState<File | null>(null); const [assetTitle, setAssetTitle] = useState(""); const [assetMaterial, setAssetMaterial] = useState("Мокрий шовк"); const [assetCode, setAssetCode] = useState(""); const [assetSection, setAssetSection] = useState("colors"); const [assetEditId, setAssetEditId] = useState<number | null>(null);
  const [replyTitle, setReplyTitle] = useState(""); const [replyText, setReplyText] = useState(""); const [replyAssets, setReplyAssets] = useState<number[]>([]); const [replyEditId, setReplyEditId] = useState<number | null>(null);

  const TABDEFS: [string, React.ReactNode, string][] = [
    ["rules", <><Icon n="📋" size={15} /> {t("Глобальные правила", "Глобальні правила")}</>, "settings.rules"],
    ["automations", <><Icon n="⚙️" size={15} /> {t("Автоматизации", "Автоматизації")}</>, "settings.automations"],
    ["agent", <><Icon n="🤖" size={15} /> {t("AI-агент", "AI-агент")}</>, "settings.agent"],
    ["sounds", <><Icon n="bell" size={15} /> {t("Звуки", "Звуки")}</>, "settings.sounds"],
    ["open-lines", <><Icon n="chat" size={15} /> {t("Открытые линии", "Відкриті лінії")}</>, "roles.manage"],
    ["calculator", <><Icon n="calculator" size={15} /> {t("Калькулятор", "Калькулятор")}</>, "calc.settings.manage"],
    ["language", <><Icon n="🌐" size={15} /> {t("Язык", "Мова")}</>, ""],
    ["integrations", <><Icon n="🔌" size={15} /> {t("Интеграции", "Інтеграції")}</>, "roles.manage"],
  ];
  const visible = TABDEFS.filter(([, , perm]) => allow(perm));
  const [tab, setTab] = useState<string>(visible[0]?.[0] || "");
  useEffect(() => { if (!visible.some(([k]) => k === tab)) setTab(visible[0]?.[0] || ""); /* eslint-disable-next-line */ }, [visible.length]);

  function load() { if (canIntegr) api.get<Prov[]>("/api/integrations/settings/").then(setProvs).catch(() => { /* немає доступу — тихо */ }); }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  function loadLibrary() { api.get<any>("/api/inbox/media-library/").then((d) => { setLibrary(d.items || []); setQuickReplies(d.replies || []); }).catch(() => {}); }
  useEffect(() => { if (tab === "open-lines") loadLibrary(); }, [tab]);
  async function addAsset() {
    let content_b64 = ""; let filename = "";
    if (assetFile) { filename = assetFile.name; content_b64 = await new Promise<string>((resolve) => { const r = new FileReader(); r.onload = () => resolve(String(r.result)); r.readAsDataURL(assetFile); }); }
    await api.post("/api/inbox/media-library/", assetEditId ? { action: "update_asset", id: assetEditId, title: assetTitle, material: assetMaterial, color_code: assetCode, section: assetSection } : { action: "asset", title: assetTitle, material: assetMaterial, filename, content_b64, color_code: assetCode, section: assetSection, kind: assetFile?.type.startsWith("video") ? "video" : (assetSection === "colors" ? "catalog" : "image") });
    setAssetFile(null); setAssetTitle(""); setAssetMaterial("Мокрий шовк"); setAssetCode(""); setAssetEditId(null); loadLibrary();
  }
  async function addReply() { await api.post("/api/inbox/media-library/", replyEditId ? { action: "update_reply", id: replyEditId, title: replyTitle, text: replyText, asset_ids: replyAssets } : { action: "reply", title: replyTitle, text: replyText, asset_ids: replyAssets }); setReplyTitle(""); setReplyText(""); setReplyAssets([]); setReplyEditId(null); loadLibrary(); }

  async function save(p: Prov) {
    const body: any = { provider: p.provider, is_active: p.is_active, ...(edit[p.provider] || {}) };
    await api.post("/api/integrations/settings/", body);
    setSaved(p.provider); setTimeout(() => setSaved(""), 2000);
    setEdit({ ...edit, [p.provider]: {} });
    load();
  }
  async function toggle(p: Prov) {
    await api.post("/api/integrations/settings/", { provider: p.provider, is_active: !p.is_active });
    load();
  }

  if (!visible.length) return <div className="scroll pad fade"><div className="note">{t("Нет доступа к настройкам", "Немає доступу до налаштувань")}</div></div>;

  return (
    <div className="scroll pad fade">
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {visible.map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            style={{ fontSize: 14, fontWeight: tab === k ? 700 : 500, padding: "8px 16px", borderRadius: 10, cursor: "pointer",
              border: "1px solid " + (tab === k ? "var(--brand)" : "#e2e8f0"), background: tab === k ? "var(--brand)" : "#fff", color: tab === k ? "#fff" : "#475569" }}>{label}</button>
        ))}
      </div>

      {tab === "rules" && <SettingsGlobalRules />}
      {tab === "automations" && <SettingsAutomations />}
      {tab === "agent" && <SettingsAgent />}
      {tab === "sounds" && <SoundSettings />}
      {tab === "calculator" && <CalculatorSettings />}
      {tab === "open-lines" && <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 1fr) minmax(300px, 1fr)", gap: 14 }}>
        <div className="panel" style={{ margin: 0 }}><b>🎨 {t("Библиотека цветов и медиа", "Бібліотека кольорів і медіа")}</b><div className="muted" style={{ fontSize: 12, margin: "5px 0 10px" }}>{t("Загрузите страницу каталога, фото или видео. Менеджер найдёт материал по коду в скрепке чата.", "Завантажте сторінку каталогу, фото або відео. Менеджер знайде матеріал за кодом у скріпці чату.")}</div>
          <select value={assetSection} onChange={(e) => setAssetSection(e.target.value)} style={{ width: "100%", marginBottom: 7 }}><option value="colors">Кольори / каталог</option><option value="quick">Швидка відповідь</option></select>
          <input value={assetMaterial} onChange={(e) => setAssetMaterial(e.target.value)} placeholder={t("Материал, например «Мокрый шёлк»", "Матеріал, наприклад «Мокрий шовк»")} style={{ width: "100%", boxSizing: "border-box", marginBottom: 7 }} />
          <input value={assetTitle} onChange={(e) => setAssetTitle(e.target.value)} placeholder={t("Название материала", "Назва матеріалу")} style={{ width: "100%", boxSizing: "border-box", marginBottom: 7 }} />
          <input value={assetCode} onChange={(e) => setAssetCode(e.target.value)} placeholder="CSK 03-32 (якщо це колір)" style={{ width: "100%", boxSizing: "border-box", marginBottom: 7 }} />
          <input type="file" accept="image/*,video/*" onChange={(e) => setAssetFile(e.target.files?.[0] || null)} style={{ marginBottom: 7, width: "100%" }} />
          <button className="btn btn-primary" disabled={!assetEditId && !assetFile} onClick={addAsset}>{assetEditId ? t("Сохранить изменения", "Зберегти зміни") : t("Добавить материал", "Додати матеріал")}</button>{assetEditId && <button className="btn" style={{ marginLeft: 6 }} onClick={() => { setAssetEditId(null); setAssetFile(null); setAssetTitle(""); setAssetMaterial("Мокрий шовк"); setAssetCode(""); }}>{t("Отмена", "Скасувати")}</button>}
          <div style={{ marginTop: 12, display: "grid", gap: 5 }}>{library.map((a) => <div key={a.id} style={{ borderTop: "1px solid #e2e8f0", paddingTop: 6, fontSize: 12, display: "flex", gap: 7, alignItems: "center" }}><span style={{ flex: 1 }}><b>{a.material ? a.material + " · " : ""}{a.color_code ? a.color_code + " · " : ""}{a.title}</b> <span className="muted">{a.kind}</span></span><button className="btn" onClick={() => { setAssetEditId(a.id); setAssetTitle(a.title); setAssetMaterial(a.material || "Мокрий шовк"); setAssetCode(a.color_code || ""); setAssetSection(a.section); }}>{t("Изменить", "Змінити")}</button><button className="btn" onClick={async () => { await api.post("/api/inbox/media-library/", { action: "delete_asset", id: a.id }); loadLibrary(); }}>×</button></div>)}</div>
        </div>
        <div className="panel" style={{ margin: 0 }}><b>⚡ {t("Быстрые ответы", "Швидкі відповіді")}</b><div className="muted" style={{ fontSize: 12, margin: "5px 0 10px" }}>{t("Текст и отмеченные фото/видео уходят клиенту одним действием.", "Текст і позначені фото/відео йдуть клієнту однією дією.")}</div>
          <input value={replyTitle} onChange={(e) => setReplyTitle(e.target.value)} placeholder={t("Название, например «Каталог шелка»", "Назва, наприклад «Каталог шовку»")} style={{ width: "100%", boxSizing: "border-box", marginBottom: 7 }} />
          <textarea value={replyText} onChange={(e) => setReplyText(e.target.value)} placeholder={t("Текст ответа", "Текст відповіді")} style={{ width: "100%", boxSizing: "border-box", minHeight: 72, marginBottom: 7 }} />
          <div style={{ maxHeight: 140, overflow: "auto", fontSize: 12, marginBottom: 7 }}>{library.map((a) => <label key={a.id} style={{ display: "block", padding: "3px 0" }}><input type="checkbox" checked={replyAssets.includes(a.id)} onChange={() => setReplyAssets((ids) => ids.includes(a.id) ? ids.filter((x) => x !== a.id) : [...ids, a.id])} /> {a.color_code ? a.color_code + " · " : ""}{a.title}</label>)}</div>
          <button className="btn btn-primary" disabled={!replyTitle} onClick={addReply}>{replyEditId ? t("Сохранить изменения", "Зберегти зміни") : t("Сохранить быстрый ответ", "Зберегти швидку відповідь")}</button>{replyEditId && <button className="btn" style={{ marginLeft: 6 }} onClick={() => { setReplyEditId(null); setReplyTitle(""); setReplyText(""); setReplyAssets([]); }}>{t("Отмена", "Скасувати")}</button>}
          <div style={{ marginTop: 12, display: "grid", gap: 5 }}>{quickReplies.map((q) => <div key={q.id} style={{ borderTop: "1px solid #e2e8f0", paddingTop: 6, fontSize: 12, display: "flex", gap: 7, alignItems: "center" }}><span style={{ flex: 1 }}><b>{q.title}</b><br /><span className="muted">{q.text}</span></span><button className="btn" onClick={() => { setReplyEditId(q.id); setReplyTitle(q.title); setReplyText(q.text); setReplyAssets(q.assets.map((a: any) => a.id)); }}>{t("Изменить", "Змінити")}</button><button className="btn" onClick={async () => { await api.post("/api/inbox/media-library/", { action: "delete_reply", id: q.id }); loadLibrary(); }}>×</button></div>)}</div>
        </div>
      </div>}

      {tab === "language" && (
        <div className="panel" style={{ margin: 0, maxWidth: 360 }}>
          <div className="label" style={{ marginBottom: 6 }}><Icon n="🌐" size={14} /> {t("Язык интерфейса", "Мова інтерфейсу")}</div>
          <select value={lang} onChange={(e) => setLang(e.target.value as "uk" | "ru")}
            style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 14 }}>
            <option value="uk">Українська</option>
            <option value="ru">Русский</option>
          </select>
          <div className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>{t("Личная настройка — сохраняется на этом устройстве.", "Особисте налаштування — зберігається на цьому пристрої.")}</div>
        </div>
      )}

      {tab === "integrations" && (<>
        <div className="note" style={{ background: "#fff7ed", border: "1px solid #fed7aa", color: "#9a3412" }}>
          🔐 {t("Ключи платежей, фискализации и Нова Пошта. Доступ только у администратора — сотрудникам эти ключи не выдаются.", "Ключі платежів, фіскалізації та Нова Пошта. Доступ лише в адміністратора — співробітникам ці ключі не видаються.")}
        </div>
        <div className="note">{t("Перенеси сюда ключи из Битрикса (один раз) — и оплаты, фискализация и Нова Пошта заработают вживую. Ключи хранятся на сервере и показываются замаскированными.", "Перенеси сюди ключі з Бітрикса (один раз) — і оплати, фіскалізація та Нова Пошта запрацюють наживо. Ключі зберігаються на сервері та показуються замаскованими.")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {provs.map((p) => (
            <div key={p.provider} className="panel" style={{ margin: 0 }}>
              <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
                <b style={{ fontSize: 15 }}>{TITLES[p.provider] || p.provider}</b>
                <div className="spacer" />
                <span className={"toggle" + (p.is_active ? " on" : "")} onClick={() => toggle(p)} />
              </div>
              {p.fields.map((f) => (
                <div key={f} style={{ marginBottom: 8 }}>
                  <label className="label" style={{ display: "block", marginBottom: 3 }}>{FIELD_LABELS[f] || f}</label>
                  <input
                    placeholder={p.values[f] ? `${t("сейчас", "зараз")}: ${p.values[f]}` : t("не задано", "не задано")}
                    value={edit[p.provider]?.[f] ?? ""}
                    onChange={(e) => setEdit({ ...edit, [p.provider]: { ...(edit[p.provider] || {}), [f]: e.target.value } })}
                    style={{ width: "100%", height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13 }} />
                </div>
              ))}
              <button className="btn btn-primary" style={{ marginTop: 6 }} onClick={() => save(p)}>
                {saved === p.provider ? t("✓ Сохранено", "✓ Збережено") : t("Сохранить", "Зберегти")}
              </button>
              {p.provider === "email_invoices" && (
                <button className="btn btn-light" style={{ marginTop: 6, marginLeft: 8 }} onClick={async () => {
                  try {
                    const r: any = await api.post("/api/integrations/email-invoices/test/", {});
                    if (r.ok) alert(t("Связь есть ✓", "Зв'язок є ✓") + `\n${r.email}\n` + t("Писем от отправителей", "Листів від відправників") + `: ${r.matched}\n\n` + (r.samples || []).join("\n"));
                    else alert(r.detail || "?");
                  } catch (e: any) { alert(e?.response?.data?.detail || t("Ошибка связи", "Помилка зв'язку")); }
                }}>📬 {t("Проверить связь", "Перевірити зв'язок")}</button>
              )}
            </div>
          ))}
        </div>
      </>)}
    </div>
  );
}
