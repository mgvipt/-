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

  const TABDEFS: [string, React.ReactNode, string][] = [
    ["rules", <><Icon n="📋" size={15} /> {t("Глобальные правила", "Глобальні правила")}</>, "settings.rules"],
    ["automations", <><Icon n="⚙️" size={15} /> {t("Автоматизации", "Автоматизації")}</>, "settings.automations"],
    ["agent", <><Icon n="🤖" size={15} /> {t("AI-агент", "AI-агент")}</>, "settings.agent"],
    ["sounds", <><Icon n="bell" size={15} /> {t("Звуки", "Звуки")}</>, "settings.sounds"],
    ["calculator", <><Icon n="calculator" size={15} /> {t("Калькулятор", "Калькулятор")}</>, "calc.settings.manage"],
    ["language", <><Icon n="🌐" size={15} /> {t("Язык", "Мова")}</>, ""],
    ["integrations", <><Icon n="🔌" size={15} /> {t("Интеграции", "Інтеграції")}</>, "roles.manage"],
  ];
  const visible = TABDEFS.filter(([, , perm]) => allow(perm));
  const [tab, setTab] = useState<string>(visible[0]?.[0] || "");
  useEffect(() => { if (!visible.some(([k]) => k === tab)) setTab(visible[0]?.[0] || ""); /* eslint-disable-next-line */ }, [visible.length]);

  function load() { if (canIntegr) api.get<Prov[]>("/api/integrations/settings/").then(setProvs).catch(() => { /* немає доступу — тихо */ }); }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

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
