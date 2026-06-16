import { useEffect, useState } from "react";
import { api } from "../api";

interface Data {
  leads_total: number; deals_total: number; conversion: number; revenue: number; avg_check: number;
  funnel: string; stages: { name: string; color: string; count: number; amount: number }[];
  managers: { name: string; deals: number; sum: number }[];
  funnels: { id: number; name: string }[];
}

export default function Analytics() {
  const [d, setD] = useState<Data | null>(null);
  const [fid, setFid] = useState<string>("");

  useEffect(() => { api.get<Data>(`/api/analytics/${fid ? "?funnel=" + fid : ""}`).then(setD); }, [fid]);
  if (!d) return <div className="spin">Загрузка аналитики…</div>;
  const maxCount = Math.max(...d.stages.map((s) => s.count), 1);
  const cards: [string, string][] = [
    ["Лидов всего", d.leads_total.toLocaleString("ru")],
    ["Сделок", d.deals_total.toLocaleString("ru")],
    ["Конверсия", d.conversion + "%"],
    ["Выручка (won)", d.revenue.toLocaleString("ru") + " ₴"],
    ["Средний чек", Math.round(d.avg_check).toLocaleString("ru") + " ₴"],
  ];

  return (
    <div className="scroll pad fade">
      <div className="toolbar" style={{ borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 12, background: "#fff" }}>
        <span className="muted">Воронка:</span>
        <select value={fid} onChange={(e) => setFid(e.target.value)}>
          <option value="">Все продажи</option>
          {d.funnels.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginBottom: 14 }}>
        {cards.map(([t, v]) => (
          <div key={t} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{t}</div><div style={{ fontSize: 22, fontWeight: 700 }}>{v}</div></div>
        ))}
      </div>
      <div className="panel" style={{ margin: 0, marginBottom: 12 }}>
        <b style={{ fontSize: 14 }}>Воронка продаж {d.funnel && `· ${d.funnel}`}</b>
        <div style={{ marginTop: 12 }}>
          {d.stages.map((s) => (
            <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
              <span style={{ width: 180, fontSize: 12.5, color: "#475569" }}>{s.name}</span>
              <div style={{ flex: 1, height: 24, background: "#f1f5f9", borderRadius: 5 }}>
                <div style={{ width: `${(s.count / maxCount) * 100}%`, minWidth: 28, height: "100%", background: s.color, borderRadius: 5, color: "#fff", fontSize: 11, display: "flex", alignItems: "center", paddingLeft: 8 }}>{s.count}</div>
              </div>
              <span className="muted" style={{ width: 110, textAlign: "right", fontSize: 12 }}>{s.amount.toLocaleString("ru")} ₴</span>
            </div>
          ))}
        </div>
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <b style={{ fontSize: 14 }}>Топ менеджеров</b>
        <table style={{ marginTop: 8 }}><thead><tr><th>Менеджер</th><th>Сделок</th><th>Сумма</th></tr></thead>
          <tbody>{d.managers.map((m, i) => <tr key={i}><td>{m.name.trim() || "—"}</td><td>{m.deals}</td><td><b>{m.sum.toLocaleString("ru")} ₴</b></td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
