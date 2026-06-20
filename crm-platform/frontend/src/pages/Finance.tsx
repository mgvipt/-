/* ============================================================================
 *  ФІНАНСИ  —  frontend/src/pages/Finance.tsx
 *  Вкладки: Дашборд (ДДС) · P&L (ATM) · Точка беззбитковості · Фінмодель.
 *  Источник формул — Wallcov Cashflow. Документация: docs/TZ-finmodule.md.
 * ========================================================================== */
import { useEffect, useState } from "react";
import { api } from "../api";

const money = (n: number) => Math.round(n || 0).toLocaleString("ru") + " ₴";
const pad = (n: number) => String(n).padStart(2, "0");
const today = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const monthStart = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`; };

export default function Finance() {
  const [tab, setTab] = useState<"dash" | "pnl" | "be" | "dir" | "model">("dash");
  const tabs: [string, string][] = [["dash", "💰 Дашборд"], ["pnl", "📊 P&L (ATM)"], ["be", "🎯 Точка беззбитковості"], ["dir", "🗂 Напрямки (проекти)"], ["model", "⚙️ Фінмодель"]];
  return (
    <div className="scroll pad fade">
      <div className="note warn">🔒 Розділ бачать тільки ролі з правом <b>finance.view</b>.</div>
      <div style={{ display: "flex", gap: 6, margin: "12px 0", flexWrap: "wrap" }}>
        {tabs.map(([k, l]) => <button key={k} className={tab === k ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab(k as any)}>{l}</button>)}
      </div>
      {tab === "dash" && <Dashboard />}
      {tab === "pnl" && <PnL />}
      {tab === "be" && <Breakeven />}
      {tab === "dir" && <Directions />}
      {tab === "model" && <FinModel />}
    </div>
  );
}

/* ─── Период-пикер (общий) ─────────────────────────────────────────────── */
function Period({ from, to, set }: { from: string; to: string; set: (f: string, t: string) => void }) {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
      <span className="muted" style={{ fontSize: 13 }}>Період:</span>
      <input type="date" value={from} onChange={(e) => set(e.target.value, to)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
      <span className="muted">—</span>
      <input type="date" value={to} onChange={(e) => set(from, e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
    </div>
  );
}

/* ─── ВКЛАДКА: ДАШБОРД (ДДС) ───────────────────────────────────────────── */
function Dashboard() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.get<any>("/api/finance/dashboard/").then(setD).catch(() => setD(null)); }, []);
  if (!d) return <div className="spin">Загрузка…</div>;
  const max = Math.max(...d.cashflow.map((x: any) => Math.max(x.in, x.out)), 1);
  const cards: [string, number, string][] = [
    ["Залишок на рахунках", d.total_balance, "#16a34a"], ["Дохід (місяць)", d.month_income, "#2563eb"],
    ["Витрати (місяць)", d.month_expense, "#ef4444"], ["Прибуток (місяць)", d.month_profit, "#7c3aed"],
  ];
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 12 }}>
        {cards.map(([t, v, c]) => <div key={t} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{t}</div><div style={{ fontSize: 22, fontWeight: 700, color: c }}>{money(v)}</div></div>)}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 12 }}>
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>Грошовий потік · 30 днів</b>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 160, marginTop: 12 }}>
            {d.cashflow.map((x: any, i: number) => (
              <div key={i} title={`${x.date}: +${x.in} / -${x.out}`} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: 1 }}>
                <div style={{ height: `${(x.in / max) * 70}%`, background: "#22c55e", borderRadius: "2px 2px 0 0" }} />
                <div style={{ height: `${(x.out / max) * 70}%`, background: "#f87171", borderRadius: "0 0 2px 2px" }} />
              </div>
            ))}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>🟢 дохід · 🔴 витрата по днях</div>
        </div>
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>Рахунки / Каси</b>
          {d.accounts.map((a: any) => <div key={a.id} className="row" style={{ padding: "8px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">{a.name}</span><b>{money(a.balance)}</b></div>)}
        </div>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА: P&L (ATM, 5 уровней) ────────────────────────────────────── */
function PnL() {
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(today());
  const [d, setD] = useState<any>(null);
  const load = (f: string, t: string) => { setFrom(f); setTo(t); api.get<any>(`/api/finance/pnl/?from=${f}&to=${t}`).then(setD); };
  useEffect(() => { load(from, to); }, []);
  if (!d) return <div className="spin">Загрузка…</div>;
  const rows: [string, number, string, string][] = [
    ["Виручка", d.revenue, "#0f172a", d.deals + " угод"],
    ["− Прямі витрати", -d.direct, "#ef4444", d.direct_pct + "% з виручки + AI " + money(d.ai_total)],
    ["= Маржа", d.margin, "#16a34a", d.margin_pct + "%"],
    ["− Операційні (постійні + змінні)", -d.operating, "#ef4444", "за період"],
    ["= Чистий прибуток", d.net, d.net >= 0 ? "#16a34a" : "#dc2626", d.net_pct + "%"],
  ];
  return (
    <>
      <Period from={from} to={to} set={load} />
      <div className="panel" style={{ margin: 0, maxWidth: 620 }}>
        <b style={{ fontSize: 14 }}>P&L по методології ATM · {d.deals} угод</b>
        <table style={{ width: "100%", marginTop: 10 }}>
          <tbody>
            {rows.map(([t, v, c, note], i) => (
              <tr key={i} style={{ borderBottom: "1px solid #f1f5f9", background: t.startsWith("=") ? "#f8fafc" : "" }}>
                <td style={{ padding: "9px 4px", fontWeight: t.startsWith("=") ? 700 : 400 }}>{t}</td>
                <td className="muted" style={{ fontSize: 12, textAlign: "right" }}>{note}</td>
                <td style={{ padding: "9px 4px", textAlign: "right", fontWeight: 600, color: c, fontVariantNumeric: "tabular-nums" }}>{money(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА: ТОЧКА БЕЗУБЫТОЧНОСТИ ────────────────────────────────────── */
function Breakeven() {
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(today());
  const [d, setD] = useState<any>(null);
  const load = (f: string, t: string) => { setFrom(f); setTo(t); api.get<any>(`/api/finance/breakeven/?from=${f}&to=${t}`).then(setD); };
  useEffect(() => { load(from, to); }, []);
  if (!d) return <div className="spin">Загрузка…</div>;
  const prog = Math.min(100, d.progress);
  const cards: [string, string][] = [
    ["Сума фондів виручки", d.rev_funds_pct + " %"], ["Маржа з кожної ₴", d.margin_pct + " %"],
    ["Точка беззбитковості", money(d.breakeven)], ["Виручка (факт)", money(d.revenue)], ["Витрати / міс", money(d.monthly_costs)],
  ];
  return (
    <>
      <Period from={from} to={to} set={load} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginBottom: 14 }}>
        {cards.map(([t, v]) => <div key={t} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{t}</div><div style={{ fontSize: 20, fontWeight: 700 }}>{v}</div></div>)}
      </div>
      <div className="panel" style={{ margin: 0, marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
          <b style={{ fontSize: 14 }}>Прогрес до точки беззбитковості</b>
          <b style={{ color: prog >= 100 ? "#16a34a" : "#d97706" }}>{d.progress}%</b>
        </div>
        <div style={{ height: 26, background: "#f1f5f9", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ width: `${prog}%`, height: "100%", background: prog >= 100 ? "#16a34a" : "linear-gradient(90deg,#f59e0b,#facc15)", borderRadius: 8, transition: "width .3s" }} />
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          {prog >= 100 ? "✅ Точку беззбитковості пройдено — далі чистий прибуток." : `Залишилось ${money(d.to_breakeven)} до беззбитковості.`}
        </div>
      </div>
      <div className="panel" style={{ margin: 0, maxWidth: 560 }}>
        <b style={{ fontSize: 14 }}>🔮 Прогноз за поточним темпом</b>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">Темп виручки (минуло {d.days_elapsed} з {d.days_total} дн)</span><b>{money(d.daily_pace)} / день</b></div>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">Прогноз на кінець періоду</span><b>{money(d.projected)}</b></div>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">Прогрес-прогноз</span><b style={{ color: d.projected_progress >= 100 ? "#16a34a" : "#d97706" }}>{d.projected_progress}%</b></div>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">Треба робити / день до ТБ</span><b style={{ color: "#d97706" }}>{money(d.required_daily)}</b></div>
        <div className="row" style={{ padding: "7px 0" }}><span className="muted">Днів залишилось</span><b>{d.days_left}</b></div>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА: НАПРЯМКИ (проекти Finmap) ───────────────────────────────── */
function Directions() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.get<any>("/api/finance/directions/").then(setD); }, []);
  if (!d) return <div className="spin">Загрузка…</div>;
  const t = d.total;
  return (
    <div className="panel" style={{ margin: 0 }}>
      <b style={{ fontSize: 14 }}>Напрямки бізнесу · доходи / витрати / прибуток (план із Finmap, факт із CRM)</b>
      <table style={{ width: "100%", marginTop: 8, fontSize: 13 }}>
        <thead><tr><th>Напрямок</th><th>План дохід</th><th>План витрати</th><th>План прибуток</th><th>Рентаб.</th><th>Факт дохід</th><th>Факт прибуток</th></tr></thead>
        <tbody>
          {d.rows.map((r: any) => {
            const pr = r.plan_income ? Math.round(r.plan_profit / r.plan_income * 100) : 0;
            return (
              <tr key={r.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                <td style={{ fontWeight: 500 }}>{r.name}</td>
                <td style={{ textAlign: "right" }}>{money(r.plan_income)}</td>
                <td style={{ textAlign: "right" }}>{money(r.plan_expense)}</td>
                <td style={{ textAlign: "right", fontWeight: 600, color: r.plan_profit >= 0 ? "#16a34a" : "#dc2626" }}>{money(r.plan_profit)}</td>
                <td style={{ textAlign: "right", color: pr >= 0 ? "#16a34a" : "#dc2626" }}>{pr}%</td>
                <td style={{ textAlign: "right" }} className="muted">{money(r.income)}</td>
                <td style={{ textAlign: "right", color: r.profit >= 0 ? "#16a34a" : "#dc2626" }}>{money(r.profit)}</td>
              </tr>
            );
          })}
          <tr style={{ borderTop: "2px solid #e2e8f0", fontWeight: 700 }}>
            <td>РАЗОМ</td>
            <td style={{ textAlign: "right" }}>{money(t.plan_income)}</td>
            <td style={{ textAlign: "right" }}>{money(t.plan_expense)}</td>
            <td style={{ textAlign: "right", color: (t.plan_income - t.plan_expense) >= 0 ? "#16a34a" : "#dc2626" }}>{money(t.plan_income - t.plan_expense)}</td>
            <td></td>
            <td style={{ textAlign: "right" }} className="muted">{money(t.income)}</td>
            <td style={{ textAlign: "right" }}>{money(t.profit)}</td>
          </tr>
        </tbody>
      </table>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>📋 Напрямки перенесені з Finmap (Проекти). «План» — орієнтир із Finmap. «Факт» рахується з транзакцій CRM, прив'язаних до напрямку (тегуй платежі напрямком → факт авто).</div>
    </div>
  );
}

/* ─── ВКЛАДКА: ФІНМОДЕЛЬ (CRUD статей) ─────────────────────────────────── */
const CAT_LABEL: Record<string, string> = {
  revenue_fund: "📊 ФОНДИ ВИРУЧКИ (% від кожної угоди)", payment_fee: "💳 ВИТРАТИ НА ОБРОБКУ (на кожну угоду)",
  variable: "💼 ПЕРЕМІННІ ВИТРАТИ (грн/міс)", fixed: "🏢 ПОСТІЙНІ ВИТРАТИ (грн/міс)",
  warehouse_rate: "📦 СКЛАД / СТАВКИ", config: "⚙️ КОНФІГ / ЛІМІТИ",
};
function FinModel() {
  const [arts, setArts] = useState<any[]>([]);
  const load = () => api.get<any>("/api/finmodel-articles/").then((r) => setArts(r.results || r));
  useEffect(() => { load(); }, []);
  async function save(id: number, value: number) { await api.patch(`/api/finmodel-articles/${id}/`, { value }); }
  async function add(category: string) { await api.post("/api/finmodel-articles/", { category, name: "Нова стаття", value: 0, value_type: category === "revenue_fund" || category === "variable" ? "percent" : "fixed_sum_per_month" }); load(); }
  async function del(id: number) { await api.del(`/api/finmodel-articles/${id}/`); load(); }
  const cats = Object.keys(CAT_LABEL);
  return (
    <>
      <div className="note">⚙️ Налаштування фінмоделі — звідси рахуються P&L і Точка беззбитковості. Редагуй значення, все перерахується.</div>
      {cats.map((c) => {
        const items = arts.filter((a) => a.category === c);
        if (!items.length && c !== "revenue_fund" && c !== "fixed") return null;
        return (
          <div key={c} className="panel" style={{ margin: "10px 0 0" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <b style={{ fontSize: 13 }}>{CAT_LABEL[c]}</b>
              <button className="btn btn-light" style={{ fontSize: 12, padding: "3px 9px" }} onClick={() => add(c)}>+ стаття</button>
            </div>
            {items.map((a) => (
              <div key={a.id} className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9", alignItems: "center" }}>
                <span style={{ flex: 1 }}>{a.name}</span>
                <input type="number" defaultValue={a.value} onBlur={(e) => save(a.id, Number(e.target.value))} style={{ width: 100, height: 28, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px", textAlign: "right" }} />
                <span className="muted" style={{ width: 70, fontSize: 12 }}>{a.unit || a.value_type_display}</span>
                <span style={{ color: "#ef4444", cursor: "pointer", paddingLeft: 8 }} onClick={() => del(a.id)}>✕</span>
              </div>
            ))}
          </div>
        );
      })}
    </>
  );
}
