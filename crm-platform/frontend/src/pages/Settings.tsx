import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { useAuth } from "../auth";
import SettingsGlobalRules from "./SettingsGlobalRules";
import SettingsAutomations from "./SettingsAutomations";
import SettingsAgent from "./SettingsAgent";
import { Icon } from "../Icon";

interface Prov { provider: string; fields: string[]; values: Record<string, string>; is_active: boolean; }

const TITLES: Record<string, string> = { liqpay: "LiqPay", checkbox: "Checkbox", novaposhta: "Нова Пошта" };

export default function Settings() {
  const { t, lang, setLang } = useLang();
  const [provs, setProvs] = useState<Prov[]>([]);
  const [edit, setEdit] = useState<Record<string, Record<string, string>>>({});
  const [saved, setSaved] = useState("");
  const [tab, setTab] = useState<"integrations" | "automations" | "rules" | "agent">("rules");
  const { can } = useAuth();
  const canRules = can("roles.manage");

  function load() { api.get<Prov[]>("/api/integrations/settings/").then(setProvs); }
  useEffect(() => { load(); }, []);

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

  const TABS: [string, React.ReactNode][] = [["rules", <><Icon n="📋" size={15} /> {t("Глобальные правила", "Глобальні правила")}</>], ["automations", <><Icon n="⚙️" size={15} /> {t("Автоматизации", "Автоматизації")}</>], ["agent", <><Icon n="🤖" size={15} /> {t("AI-агент", "AI-агент")}</>], ["integrations", <><Icon n="🔌" size={15} /> {t("Интеграции / Язык", "Інтеграції / Мова")}</>]];
  return (
    <div className="scroll pad fade">
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {TABS.map(([k, label]) => ((k === "rules" || k === "automations" || k === "agent") && !canRules ? null : (
          <button key={k} onClick={() => setTab(k as any)}
            style={{ fontSize: 14, fontWeight: tab === k ? 700 : 500, padding: "8px 16px", borderRadius: 10, cursor: "pointer",
              border: "1px solid " + (tab === k ? "var(--brand)" : "#e2e8f0"), background: tab === k ? "var(--brand)" : "#fff", color: tab === k ? "#fff" : "#475569" }}>{label}</button>
        )))}
      </div>
      {tab === "rules" && <SettingsGlobalRules />}
      {tab === "automations" && <SettingsAutomations />}
      {tab === "agent" && <SettingsAgent />}
      {tab !== "integrations" ? null : (<>
      <div className="panel" style={{ margin: "0 0 12px", maxWidth: 360 }}>
        <div className="label" style={{ marginBottom: 6 }}><Icon n="🌐" size={14} /> {t("Язык интерфейса", "Мова інтерфейсу")}</div>
        <select value={lang} onChange={(e) => setLang(e.target.value as "uk" | "ru")}
          style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 14 }}>
          <option value="uk">Українська</option>
          <option value="ru">Русский</option>
        </select>
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
                <label className="label" style={{ display: "block", marginBottom: 3 }}>{f}</label>
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
          </div>
        ))}
      </div>
      </>)}
    </div>
  );
}
