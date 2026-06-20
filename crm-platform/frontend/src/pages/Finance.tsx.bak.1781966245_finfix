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
  const [tab, setTab] = useState<"dash" | "pnl" | "be" | "model">("dash");
  const tabs: [string, string][] = [["dash", "💰 Дашборд"], ["pnl", "📊 P&L (ATM)"], ["be", "🎯 Точка беззбитковості"], ["model", "⚙️ Фінмодель"]];
  return (
    <div className="scroll pad fade">
      <div className="note warn">🔒 Розділ бачать тільки ролі з правом <b>finance.view</b>.</div>
      <div style={{ display: "flex", gap: 6, margin: "12px 0", flexWrap: "wrap" }}>
        {tabs.map(([k, l]) => <button key={k} className={tab === k ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab(k as any)}>{l}</button>)}
      </div>
      {tab === "dash" && <Dashboard />}
      {tab === "pnl" && <PnL />}
      {tab === "be" && <Breakeven />}
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
    ["Виручка", d.revenue, "#0f172a", ""],
    ["− Прямі витрати", -d.direct, "#ef4444", d.direct_pct + "% від виручки"],
    ["= Маржа", d.margin, "#16a34a", d.margin_pct + "%"],
    ["− Перемінні", -d.variable, "#ef4444", d.variable_pct + "% від маржі"],
    ["= СКД (сума до розподілу)", d.skd, "#2563eb", ""],
    ["− УПР (постійні)", -d.upr, "#ef4444", "за період"],
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
    ["Маржа з кожної ₴", d.margin_pct + "%"], ["ТБ — потрібна виручка", money(d.breakeven)],
    ["Факт виручка", money(d.revenue)], ["ТБ в угодах", d.tb_deals], ["Ціль (ТБ +націнка)", money(d.company_target)],
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
          {prog >= 100 ? "✅ Точку беззбитковості пройдено — далі чистий прибуток." : `Залишилось ${money(d.breakeven - d.revenue)} до беззбитковості.`}
        </div>
      </div>
      <div className="panel" style={{ margin: 0, maxWidth: 520 }}>
        <b style={{ fontSize: 14 }}>Прогноз</b>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">Темп виручки</span><b>{money(d.daily_pace)} / день</b></div>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">Прогноз на період</span><b>{money(d.projected)}</b></div>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">Треба робити / день</span><b style={{ color: "#d97706" }}>{money(d.required_daily)}</b></div>
        <div className="row" style={{ padding: "7px 0" }}><span className="muted">Днів залишилось</span><b>{d.days_left}</b></div>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА: ФІНМОДЕЛЬ (CRUD статей) ─────────────────────────────────── */
const CAT_LABEL: Record<string, string> = {
  revenue_fund: "📊 Фонди виручки (% з виручки)", payment_fee: "💳 Комісія еквайрингу (₴/угода)",
  variable: "💼 Перемінні (% від маржі)", fixed: "🏢 Постійні витрати (₴/міс)",
  upr_cat2: "🏭 УПР обов'язкові (у ТБ)", upr_cat3: "📁 УПР відмовні", warehouse_rate: "📦 Ставки складу", config: "⚙️ Конфіг",
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
