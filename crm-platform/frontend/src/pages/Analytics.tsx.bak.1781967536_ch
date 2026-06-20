/* ============================================================================
 *  АНАЛИТИКА  —  frontend/src/pages/Analytics.tsx
 *  Две вкладки: ПРОДАЖІ (воронка, KPI, топ менеджеров) и СКЛАД (стоимость
 *  запасов по закупке/рознице, потенц. маржа, по категориям).
 *  Документация: docs/CODEMAP.md разд.3.
 * ========================================================================== */
import { useEffect, useState } from "react";
import { api } from "../api";

/* ─── ТИПЫ ─────────────────────────────────────────────────────────────── */
interface SalesData {
  leads_total: number; deals_total: number; conversion: number; revenue: number; avg_check: number;
  funnel: string; stages: { name: string; color: string; count: number; amount: number }[];
  managers: { name: string; deals: number; sum: number }[];
  funnels: { id: number; name: string }[];
}
interface InvData {
  total_items: number; in_stock: number; out_stock: number; total_qty: number;
  value_cost: number; value_retail: number; potential_margin: number;
  by_category: { name: string; items: number; qty: number; cost: number; retail: number }[];
}
const fmt = (n: number) => Math.round(n || 0).toLocaleString("ru");

export default function Analytics() {
  const [tab, setTab] = useState<"sales" | "stock">("sales");
  return (
    <div className="scroll pad fade">
      <div className="tabline" style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <button className={tab === "sales" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("sales")}>📈 Продажі</button>
        <button className={tab === "stock" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("stock")}>📦 Склад</button>
      </div>
      {tab === "sales" ? <SalesTab /> : <StockTab />}
    </div>
  );
}

/* ─── ВКЛАДКА ПРОДАЖІ ──────────────────────────────────────────────────── */
function SalesTab() {
  const [d, setD] = useState<SalesData | null>(null);
  const [fid, setFid] = useState("");
  useEffect(() => { api.get<SalesData>(`/api/analytics/${fid ? "?funnel=" + fid : ""}`).then(setD); }, [fid]);
  if (!d) return <div className="spin">Загрузка аналитики…</div>;
  const maxCount = Math.max(...d.stages.map((s) => s.count), 1);
  const cards: [string, string][] = [
    ["Лидов всего", fmt(d.leads_total)], ["Сделок", fmt(d.deals_total)],
    ["Конверсия", d.conversion + "%"], ["Выручка (won)", fmt(d.revenue) + " ₴"],
    ["Средний чек", fmt(d.avg_check) + " ₴"],
  ];
  return (
    <>
      <div className="toolbar" style={{ borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 12, background: "#fff" }}>
        <span className="muted">Воронка:</span>
        <select value={fid} onChange={(e) => setFid(e.target.value)}>
          <option value="">Все продажи</option>
          {d.funnels.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginBottom: 14 }}>
        {cards.map(([t, v]) => <div key={t} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{t}</div><div style={{ fontSize: 22, fontWeight: 700 }}>{v}</div></div>)}
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
              <span className="muted" style={{ width: 110, textAlign: "right", fontSize: 12 }}>{fmt(s.amount)} ₴</span>
            </div>
          ))}
        </div>
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <b style={{ fontSize: 14 }}>Топ менеджеров</b>
        <table style={{ marginTop: 8 }}><thead><tr><th>Менеджер</th><th>Сделок</th><th>Сумма</th></tr></thead>
          <tbody>{d.managers.map((m, i) => <tr key={i}><td>{m.name.trim() || "—"}</td><td>{m.deals}</td><td><b>{fmt(m.sum)} ₴</b></td></tr>)}</tbody>
        </table>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА СКЛАД ────────────────────────────────────────────────────── */
function StockTab() {
  const [d, setD] = useState<InvData | null>(null);
  useEffect(() => { api.get<InvData>("/api/analytics/inventory/").then(setD); }, []);
  if (!d) return <div className="spin">Загрузка склада…</div>;
  const cards: [string, string][] = [
    ["Запас по закупке", fmt(d.value_cost) + " ₴"],
    ["Запас по рознице", fmt(d.value_retail) + " ₴"],
    ["Потенц. маржа", fmt(d.potential_margin) + " ₴"],
    ["Позиций в наличии", fmt(d.in_stock) + " / " + fmt(d.total_items)],
    ["Нет в наличии", fmt(d.out_stock)],
  ];
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginBottom: 14 }}>
        {cards.map(([t, v]) => <div key={t} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{t}</div><div style={{ fontSize: 20, fontWeight: 700 }}>{v}</div></div>)}
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <b style={{ fontSize: 14 }}>Запасы по категориям</b>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>Категорія</th><th>Позицій</th><th>К-сть</th><th>По закупці</th><th>По роздрібу</th></tr></thead>
          <tbody>{d.by_category.map((c, i) => (
            <tr key={i}><td>{c.name}</td><td>{c.items}</td><td>{c.qty.toLocaleString("ru")}</td><td>{fmt(c.cost)} ₴</td><td><b>{fmt(c.retail)} ₴</b></td></tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}
