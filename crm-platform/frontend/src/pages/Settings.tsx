import { useEffect, useState } from "react";
import { api } from "../api";

interface Prov { provider: string; fields: string[]; values: Record<string, string>; is_active: boolean; }

const TITLES: Record<string, string> = { liqpay: "LiqPay (оплаты)", checkbox: "Checkbox (фискализация)", novaposhta: "Нова Пошта", ai: "AI-РОП (Anthropic ключ)" };

export default function Settings() {
  const [provs, setProvs] = useState<Prov[]>([]);
  const [edit, setEdit] = useState<Record<string, Record<string, string>>>({});
  const [saved, setSaved] = useState("");

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

  return (
    <div className="scroll pad fade">
      <div className="note">Перенеси сюда ключи из Битрикса (один раз) — и оплаты, фискализация и Нова Пошта заработают вживую. Ключи хранятся на сервере и показываются замаскированными.</div>
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
                  placeholder={p.values[f] ? `сейчас: ${p.values[f]}` : "не задано"}
                  value={edit[p.provider]?.[f] ?? ""}
                  onChange={(e) => setEdit({ ...edit, [p.provider]: { ...(edit[p.provider] || {}), [f]: e.target.value } })}
                  style={{ width: "100%", height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13 }} />
              </div>
            ))}
            <button className="btn btn-primary" style={{ marginTop: 6 }} onClick={() => save(p)}>
              {saved === p.provider ? "✓ Сохранено" : "Сохранить"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
