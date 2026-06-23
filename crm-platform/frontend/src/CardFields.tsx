/* Кастомні поля картки (як у Бітриксі): додаєш свої поля «назва → значення».
 * Зберігаються в lead.card_fields (JSON). */
import { useState } from "react";
import { api } from "./api";

const inp: React.CSSProperties = { width: "100%", fontSize: 13, padding: "6px 8px", borderRadius: 7, border: "1px solid #e2e8f0", boxSizing: "border-box", background: "#fff" };

export default function CardFields({ leadId, initial }: { leadId: number; initial?: { label: string; value: string }[] }) {
  const [fields, setFields] = useState<{ label: string; value: string }[]>(Array.isArray(initial) ? initial : []);
  const [saved, setSaved] = useState(true);
  const [busy, setBusy] = useState(false);

  function upd(i: number, k: "label" | "value", v: string) { setFields((f) => f.map((x, j) => (j === i ? { ...x, [k]: v } : x))); setSaved(false); }
  function add() { setFields((f) => [...f, { label: "", value: "" }]); setSaved(false); }
  function del(i: number) { setFields((f) => f.filter((_, j) => j !== i)); setSaved(false); }
  async function save() {
    setBusy(true);
    try { await api.patch(`/api/leads/${leadId}/`, { card_fields: fields.filter((f) => f.label || f.value) }); setSaved(true); } catch { /* ignore */ }
    setBusy(false);
  }

  return (
    <div className="panel">
      <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
        <div className="label" style={{ margin: 0 }}>🧩 Поля картки</div>
        <div style={{ flex: 1 }} />
        {!saved && <button className="btn btn-primary" style={{ fontSize: 11, padding: "3px 9px" }} onClick={save} disabled={busy}>{busy ? "…" : "💾"}</button>}
      </div>

      {fields.length === 0 && <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>Додай свої поля (телефон, email, адреса, обʼєкт, № договору…)</div>}

      {fields.map((f, i) => (
        <div key={i} style={{ marginBottom: 9 }}>
          <input value={f.label} placeholder="Назва поля" onChange={(e) => upd(i, "label", e.target.value)}
            style={{ ...inp, fontSize: 11, color: "#64748b", fontWeight: 600, marginBottom: 3, padding: "3px 8px" }} />
          <div style={{ display: "flex", gap: 4 }}>
            <input value={f.value} placeholder="Значення" onChange={(e) => upd(i, "value", e.target.value)} style={inp} />
            <button className="btn" style={{ padding: "0 9px", background: "#fef2f2", color: "#dc2626" }} onClick={() => del(i)} title="Видалити">✕</button>
          </div>
        </div>
      ))}

      <button className="btn" style={{ width: "100%", fontSize: 12, background: "#f1f5f9", color: "#334155", marginTop: 2 }} onClick={add}>+ Додати поле</button>
    </div>
  );
}
