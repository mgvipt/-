/* ============================================================================
 *  ФІНАНСИ  —  frontend/src/pages/Finance.tsx
 *  Вкладки: Дашборд (ДДС) · P&L (ATM) · Точка беззбитковості · Фінмодель.
 *  Источник формул — Wallcov Cashflow. Документация: docs/TZ-finmodule.md.
 * ========================================================================== */
import { Fragment, useEffect, useState } from "react";
import { api } from "../api";

const money = (n: number) => Math.round(n || 0).toLocaleString("ru") + " ₴";
const pad = (n: number) => String(n).padStart(2, "0");
const today = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const monthStart = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`; };

export default function Finance() {
  const [tab, setTab] = useState<"dash" | "journal" | "pnl" | "be" | "dir" | "plan" | "salary" | "mplan" | "model">("dash");
  const tabs: [string, string][] = [["dash", "💰 Дашборд"], ["journal", "🧾 Журнал"], ["pnl", "📊 P&L (ATM)"], ["be", "🎯 Точка беззбитковості"], ["dir", "🗂 Напрямки (проекти)"], ["plan", "💼 Планування"], ["salary", "💰 ЗП/KPI"], ["mplan", "🎯 Плани"], ["model", "⚙️ Фінмодель"]];
  return (
    <div className="scroll pad fade">
      <div className="note warn">🔒 Розділ бачать тільки ролі з правом <b>finance.view</b>.</div>
      <div style={{ display: "flex", gap: 6, margin: "12px 0", flexWrap: "wrap" }}>
        {tabs.map(([k, l]) => <button key={k} className={tab === k ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab(k as any)}>{l}</button>)}
      </div>
      {tab === "dash" && <Dashboard />}
      {tab === "journal" && <Journal />}
      {tab === "pnl" && <PnL />}
      {tab === "be" && <Breakeven />}
      {tab === "dir" && <Directions />}
      {tab === "plan" && <Planning />}
      {tab === "salary" && <Salary />}
      {tab === "mplan" && <MPlans />}
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

/* ─── ВКЛАДКА: ЖУРНАЛ ОПЕРАЦІЙ (як Finmap) ─────────────────────────────── */
const CHANNELS = [
  ["", "—"], ["instagram", "Instagram"], ["tiktok", "TikTok"], ["facebook", "Facebook"],
  ["site", "Сайт"], ["salon", "Салон (офлайн)"], ["wholesale", "Опт"], ["designers", "Дизайнери/прораби"],
  ["telegram", "Telegram"], ["call", "Дзвінок"], ["other", "Інше"],
];
function Journal() {
  const [tx, setTx] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [arts, setArts] = useState<any[]>([]);
  const [dirs, setDirs] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const blank = { direction: "out", amount: "", account: 0, fin_article: 0, fin_direction: 0, channel: "", comment: "" };
  const [f, setF] = useState<any>(blank);
  const load = () => api.get<any>("/api/transactions/?page_size=100").then((d) => setTx(d.results || d));
  useEffect(() => {
    load();
    api.get<any>("/api/accounts/").then((d) => setAccounts(d.results || d));
    api.get<any>("/api/finmodel-articles/?page_size=50").then((d) => setArts(d.results || d));
    api.get<any>("/api/fin-directions/").then((d) => setDirs(d.results || d));
  }, []);
  async function save() {
    if (!Number(f.amount)) return;
    const body: any = { direction: f.direction, amount: Number(f.amount), account: f.account || accounts[0]?.id, comment: f.comment, channel: f.channel };
    if (f.fin_article) body.fin_article = f.fin_article;
    if (f.fin_direction) body.fin_direction = f.fin_direction;
    await api.post("/api/transactions/", body);
    setOpen(false); setF(blank); load();
  }
  const inp = { height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", width: "100%", marginBottom: 10 } as React.CSSProperties;
  return (
    <>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <button className="btn btn-primary" onClick={() => { setF({ ...blank, direction: "in" }); setOpen(true); }}>+ Дохід</button>
        <button className="btn btn-light" onClick={() => { setF({ ...blank, direction: "out" }); setOpen(true); }}>− Витрата</button>
        <span className="muted" style={{ marginLeft: "auto", alignSelf: "center", fontSize: 13 }}>Операцій: {tx.length}</span>
      </div>
      <div className="panel" style={{ margin: 0, padding: 0 }}>
        <table style={{ width: "100%", fontSize: 13 }}>
          <thead><tr><th style={{ padding: "8px 12px" }}>Дата</th><th>Сума</th><th>Рахунок</th><th>Фонд (стаття)</th><th>Напрямок</th><th>Канал</th><th>Коментар</th></tr></thead>
          <tbody>
            {tx.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 14 }}>Операцій ще немає. Додай вручну або вони зʼявляться при оплаті сделок.</td></tr>}
            {tx.map((t) => (
              <tr key={t.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                <td className="muted" style={{ padding: "8px 12px" }}>{new Date(t.date || t.created_at).toLocaleDateString("ru")}</td>
                <td style={{ fontWeight: 600, color: t.direction === "in" ? "#16a34a" : "#dc2626" }}>{t.direction === "in" ? "+" : "−"}{Number(t.amount).toLocaleString("ru")} ₴</td>
                <td className="muted">{t.account_name}</td>
                <td>{t.fin_article_name || <span className="muted">—</span>}</td>
                <td>{t.fin_direction_name || <span className="muted">—</span>}</td>
                <td className="muted">{(CHANNELS.find((c) => c[0] === t.channel) || ["", "—"])[1]}</td>
                <td className="muted" style={{ maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.comment}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 420 }}>
            <h3 style={{ marginTop: 0 }}>{f.direction === "in" ? "Дохід" : "Витрата"}</h3>
            <label className="label">Сума, ₴</label>
            <input type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} style={inp} autoFocus />
            <label className="label">Рахунок</label>
            <select value={f.account} onChange={(e) => setF({ ...f, account: Number(e.target.value) })} style={inp}>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name} ({Number(a.balance).toLocaleString("ru")} ₴)</option>)}
            </select>
            <label className="label">Фонд (для аналітики та точки беззбитковості)</label>
            <select value={f.fin_article} onChange={(e) => setF({ ...f, fin_article: Number(e.target.value) })} style={inp}>
              <option value={0}>— без фонду —</option>
              {arts.map((a) => <option key={a.id} value={a.id}>{a.category_display}: {a.name}</option>)}
            </select>
            <label className="label">Напрямок (звідки гроші)</label>
            <select value={f.fin_direction} onChange={(e) => setF({ ...f, fin_direction: Number(e.target.value) })} style={inp}>
              <option value={0}>— без напрямку —</option>
              {dirs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            <label className="label">Канал</label>
            <select value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })} style={inp}>
              {CHANNELS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <label className="label">Коментар</label>
            <input value={f.comment} onChange={(e) => setF({ ...f, comment: e.target.value })} style={inp} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setOpen(false)}>Скасувати</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={save}>Зберегти</button>
            </div>
          </div>
        </div>
      )}
    </>
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

/* ─── ВКЛАДКА: НАПРЯМКИ (проекти Finmap) + drill-down журналу ───────────── */
function Directions() {
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(today());
  const [d, setD] = useState<any>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [edit, setEdit] = useState<any>(null); // напрямок для додавання/редагування або null
  const reload = () => { setD(null); api.get<any>(`/api/finance/directions/?from=${from}&to=${to}`).then(setD); };
  useEffect(() => { reload(); }, [from, to]);
  async function delDir(id: number, name: string) {
    if (!confirm(`Видалити напрямок «${name}»? Операції залишаться, але втратять привʼязку до напрямку.`)) return;
    await api.del(`/api/fin-directions/${id}/`); reload();
  }
  if (!d) return <div className="spin">Загрузка…</div>;
  const t = d.total;
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <b style={{ fontSize: 14, flex: 1 }}>Напрямки бізнесу · доходи / витрати / прибуток (план із Finmap, факт із CRM)</b>
        <button className="btn btn-primary" style={{ fontSize: 13 }} title="Додати новий напрямок (проект). Зʼявиться у журналі, плануванні й аналітиці." onClick={() => setEdit({ name: "", plan_income: 0, plan_expense: 0 })}>+ Напрямок</button>
      </div>
      <Period from={from} to={to} set={(f, tt) => { setFrom(f); setTo(tt); }} />
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>👆 Натисни на напрямок — нижче відкриється його журнал операцій за період.</div>
      <table style={{ width: "100%", marginTop: 4, fontSize: 13 }}>
        <thead><tr><th></th><th>Напрямок</th><th>План дохід</th><th>План витрати</th><th>План прибуток</th><th>Рентаб.</th><th>Факт дохід</th><th>Факт прибуток</th><th></th></tr></thead>
        <tbody>
          {d.rows.map((r: any) => {
            const pr = r.plan_income ? Math.round(r.plan_profit / r.plan_income * 100) : 0;
            const isOpen = openId === r.id;
            return (
              <Fragment key={r.id}>
                <tr onClick={() => setOpenId(isOpen ? null : r.id)} style={{ borderBottom: "1px solid #f1f5f9", cursor: "pointer", background: isOpen ? "#eff6ff" : undefined }}>
                  <td style={{ width: 22, color: "#2563eb", textAlign: "center" }}>{isOpen ? "▼" : "▶"}</td>
                  <td style={{ fontWeight: 500 }}>{r.name}</td>
                  <td style={{ textAlign: "right" }}>{money(r.plan_income)}</td>
                  <td style={{ textAlign: "right" }}>{money(r.plan_expense)}</td>
                  <td style={{ textAlign: "right", fontWeight: 600, color: r.plan_profit >= 0 ? "#16a34a" : "#dc2626" }}>{money(r.plan_profit)}</td>
                  <td style={{ textAlign: "right", color: pr >= 0 ? "#16a34a" : "#dc2626" }}>{pr}%</td>
                  <td style={{ textAlign: "right" }} className="muted">{money(r.income)}</td>
                  <td style={{ textAlign: "right", color: r.profit >= 0 ? "#16a34a" : "#dc2626" }}>{money(r.profit)}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }} onClick={(e) => e.stopPropagation()}>
                    <span title="Редагувати напрямок" style={{ cursor: "pointer", marginRight: 10 }} onClick={() => setEdit({ id: r.id, name: r.name, plan_income: r.plan_income, plan_expense: r.plan_expense })}>✏️</span>
                    <span title="Видалити напрямок" style={{ cursor: "pointer", color: "#ef4444" }} onClick={() => delDir(r.id, r.name)}>✕</span>
                  </td>
                </tr>
                {isOpen && (
                  <tr><td colSpan={9} style={{ padding: 0, background: "#f8fafc" }}><DirectionJournal directionId={r.id} from={from} to={to} /></td></tr>
                )}
              </Fragment>
            );
          })}
          <tr style={{ borderTop: "2px solid #e2e8f0", fontWeight: 700 }}>
            <td></td><td>РАЗОМ</td>
            <td style={{ textAlign: "right" }}>{money(t.plan_income)}</td>
            <td style={{ textAlign: "right" }}>{money(t.plan_expense)}</td>
            <td style={{ textAlign: "right", color: (t.plan_income - t.plan_expense) >= 0 ? "#16a34a" : "#dc2626" }}>{money(t.plan_income - t.plan_expense)}</td>
            <td></td>
            <td style={{ textAlign: "right" }} className="muted">{money(t.income)}</td>
            <td style={{ textAlign: "right" }}>{money(t.profit)}</td>
            <td></td>
          </tr>
        </tbody>
      </table>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>📋 Напрямки перенесені з Finmap (Проекти). «План» — орієнтир із Finmap. «Факт» рахується з транзакцій CRM, прив'язаних до напрямку. Зміни тут синхронізуються у журналі, плануванні та аналітиці.</div>
      {edit && <DirModal dir={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </div>
  );
}

function DirModal({ dir, onClose, onSaved }: { dir: any; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(dir.name || "");
  const [inc, setInc] = useState(String(dir.plan_income || 0));
  const [exp, setExp] = useState(String(dir.plan_expense || 0));
  const [busy, setBusy] = useState(false);
  async function save() {
    if (!name.trim()) return;
    setBusy(true);
    const body = { name: name.trim(), plan_income: Number(inc) || 0, plan_expense: Number(exp) || 0 };
    try {
      if (dir.id) await api.patch(`/api/fin-directions/${dir.id}/`, body);
      else await api.post("/api/fin-directions/", { ...body, active: true });
      onSaved();
    } finally { setBusy(false); }
  }
  const inp = { width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 } as React.CSSProperties;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, padding: 22, width: 420 }}>
        <h3 style={{ marginTop: 0 }}>{dir.id ? "Редагувати напрямок" : "Новий напрямок"}</h3>
        <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>Напрямок (проект) — звідки гроші: ДЕКОР товари, Обʼєкти, Алмазне свердління, Рекуператори, Особисте тощо.</div>
        <label className="label">Назва напрямку</label>
        <input value={name} autoFocus onChange={(e) => setName(e.target.value)} placeholder="Напр. ДЕКОР товари" style={inp} />
        <label className="label">План доходу (₴/міс)</label>
        <input type="number" value={inc} onChange={(e) => setInc(e.target.value)} style={inp} />
        <label className="label">План витрат (₴/міс)</label>
        <input type="number" value={exp} onChange={(e) => setExp(e.target.value)} style={inp} />
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>Скасувати</button>
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={save} disabled={busy || !name.trim()}>{busy ? "…" : "Зберегти"}</button>
        </div>
      </div>
    </div>
  );
}

function DirectionJournal({ directionId, from, to }: { directionId: number; from: string; to: string }) {
  const [tx, setTx] = useState<any[] | null>(null);
  useEffect(() => { setTx(null); api.get<any>(`/api/transactions/?fin_direction=${directionId}&from=${from}&to=${to}&page_size=200`).then((d) => setTx(d.results || d)); }, [directionId, from, to]);
  if (!tx) return <div className="spin" style={{ padding: 12 }}>Журнал…</div>;
  const inc = tx.filter((t) => t.direction === "in").reduce((a, t) => a + Number(t.amount), 0);
  const exp = tx.filter((t) => t.direction === "out").reduce((a, t) => a + Number(t.amount), 0);
  // ── ветки/канали напрямку: скільки продажів і на скільки з кожного каналу ──
  const byChan: Record<string, { sum: number; count: number }> = {};
  tx.filter((t) => t.direction === "in").forEach((t) => {
    const k = t.channel || "other";
    (byChan[k] ||= { sum: 0, count: 0 });
    byChan[k].sum += Number(t.amount); byChan[k].count += 1;
  });
  const chans = Object.entries(byChan).sort((a, b) => b[1].sum - a[1].sum);
  const chLabel = (k: string) => (CHANNELS.find((c) => c[0] === k) || ["", k])[1];
  return (
    <div style={{ padding: "8px 12px 14px" }}>
      <div style={{ display: "flex", gap: 14, fontSize: 12.5, marginBottom: 6 }}>
        <span style={{ color: "#16a34a", fontWeight: 600 }}>Дохід: {money(inc)}</span>
        <span style={{ color: "#dc2626", fontWeight: 600 }}>Витрати: {money(exp)}</span>
        <span style={{ fontWeight: 700 }}>Прибуток: {money(inc - exp)}</span>
        <span className="muted" style={{ marginLeft: "auto" }}>Операцій: {tx.length}</span>
      </div>
      {chans.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div className="muted" style={{ fontSize: 11.5, fontWeight: 600, marginBottom: 4 }}>🌿 Канали (ветки) напрямку · продажів × сума:</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {chans.map(([k, v]) => (
              <span key={k} style={{ fontSize: 12, padding: "4px 10px", borderRadius: 14, background: "#eef2ff", color: "#4338ca", fontWeight: 600 }}>
                {chLabel(k)} · {v.count} продаж{v.count === 1 ? "" : v.count < 5 ? "і" : "ів"} · {money(v.sum)}
              </span>
            ))}
          </div>
        </div>
      )}
      {tx.length === 0 ? (
        <div className="muted" style={{ fontSize: 13 }}>Немає операцій по цьому напрямку за період. Додай транзакцію у вкладці «Журнал» і обери цей напрямок.</div>
      ) : (
        <table style={{ width: "100%", fontSize: 12.5 }}>
          <thead><tr><th style={{ textAlign: "left", padding: "4px 8px" }}>Дата</th><th>Сума</th><th>Фонд</th><th>Канал</th><th style={{ textAlign: "left" }}>Коментар</th></tr></thead>
          <tbody>
            {tx.map((t) => (
              <tr key={t.id} style={{ borderTop: "1px solid #eef2f7" }}>
                <td className="muted" style={{ padding: "4px 8px" }}>{new Date(t.date || t.created_at).toLocaleDateString("ru")}</td>
                <td style={{ textAlign: "right", fontWeight: 600, color: t.direction === "in" ? "#16a34a" : "#dc2626" }}>{t.direction === "in" ? "+" : "−"}{Number(t.amount).toLocaleString("ru")} ₴</td>
                <td>{t.fin_article_name || <span className="muted">—</span>}</td>
                <td className="muted" style={{ textAlign: "center" }}>{(CHANNELS.find((c) => c[0] === t.channel) || ["", "—"])[1]}</td>
                <td className="muted" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.comment}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ─── ВКЛАДКА: ФІНМОДЕЛЬ (CRUD статей) ─────────────────────────────────── */
/* ─── ВКЛАДКА: ПЛАНУВАННЯ ПО ФОНДАХ-КОНВЕРТАХ ──────────────────────────── */
function Planning() {
  const [period, setPeriod] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; });
  const [data, setData] = useState<any>(null);
  const [dirs, setDirs] = useState<any[]>([]);
  const [alloc, setAlloc] = useState<any>(null); // {fund} модалка ручного розподілу
  const [auto, setAuto] = useState(false);       // модалка авто-розподілу виручки
  const [openAlloc, setOpenAlloc] = useState<number | null>(null); // розгорнутий список розподілів фонду
  const load = () => api.get<any>(`/api/finance/funds/?period=${period}`).then(setData);
  useEffect(() => { load(); }, [period]);
  useEffect(() => { api.get<any>("/api/fin-directions/?page_size=100").then((d) => setDirs(d.results || d)); }, []);

  function FundRow({ f, sub }: { f: any; sub?: boolean }) {
    const neg = f.balance < 0;
    const open = openAlloc === f.id;
    return (
      <>
        <div className="row" style={{ padding: "8px 0", borderBottom: "1px solid #f1f5f9", alignItems: "center", paddingLeft: sub ? 24 : 0 }}>
          <span style={{ flex: 1, fontWeight: sub ? 400 : 600 }}>{sub && <span style={{ color: "#cbd5e1", marginRight: 4 }}>↳</span>}{f.is_envelope && "✉️ "}{f.name}</span>
          <span title="Натисни, щоб побачити та прибрати окремі розподіли" onClick={() => setOpenAlloc(open ? null : f.id)}
            style={{ width: 110, textAlign: "right", color: "#0ea5e9", cursor: f.allocated ? "pointer" : "default", textDecoration: f.allocated ? "underline dotted" : "none" }}>{f.allocated ? (open ? "▾ " : "▸ ") : ""}{money(f.allocated)}</span>
          <span style={{ width: 110, textAlign: "right", color: "#ef4444" }}>−{money(f.spent)}</span>
          <span style={{ width: 120, textAlign: "right", fontWeight: 700, color: neg ? "#dc2626" : "#059669" }}>{money(f.balance)}</span>
          <button className="btn btn-light" style={{ fontSize: 11, padding: "3px 8px", marginLeft: 8 }} title="Покласти грошей у цей фонд-конверт" onClick={() => setAlloc(f)}>+ розподіл</button>
        </div>
        {open && <AllocList fundId={f.id} period={period} onChanged={load} />}
        {(f.subfunds || []).map((x: any) => <FundRow key={x.id} f={x} sub />)}
      </>
    );
  }

  if (!data) return <div className="spin">Завантаження фондів…</div>;
  return (
    <>
      <div className="note">💼 Гроші приходять на рахунок → розподіляєш по фондах-конвертах. У кожному фонді видно <b>залишок</b>, з нього робиш розхід. Порядок: <b>ФВ → ФМ → ФСКД</b>.</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <span className="muted" style={{ fontSize: 13 }}>Місяць:</span>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setAuto(true)}>⚡ Авто-розподіл виручки</button>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {data.accounts.map((a: any) => (
          <div key={a.id} className="panel" style={{ flex: "1 1 150px", padding: "10px 12px" }}>
            <div className="muted" style={{ fontSize: 12 }}>{a.name}</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{money(a.balance)}</div>
          </div>
        ))}
        <div className="panel" style={{ flex: "1 1 150px", padding: "10px 12px", background: "#f0fdf4" }}>
          <div className="muted" style={{ fontSize: 12 }}>Залишок у фондах</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#059669" }}>{money(data.totals.balance)}</div>
        </div>
      </div>

      {data.groups.map((g: any) => (
        <div key={g.key} className="panel" style={{ margin: "10px 0 0", borderLeft: `4px solid ${g.color}` }}>
          <div style={{ display: "flex", alignItems: "center", marginBottom: 4 }}>
            <b style={{ fontSize: 13.5, color: g.color, flex: 1 }}>{g.label}</b>
            <span className="muted" style={{ fontSize: 11, width: 110, textAlign: "right" }}>Розподілено</span>
            <span className="muted" style={{ fontSize: 11, width: 110, textAlign: "right" }}>Витрачено</span>
            <span className="muted" style={{ fontSize: 11, width: 120, textAlign: "right" }}>Залишок</span>
            <span style={{ width: 90 }} />
          </div>
          {g.funds.map((f: any) => <FundRow key={f.id} f={f} />)}
        </div>
      ))}

      {alloc && <AllocModal fund={alloc} period={period} accounts={data.accounts} dirs={dirs} onClose={() => setAlloc(null)} onSaved={() => { setAlloc(null); load(); }} />}
      {auto && <AutoModal period={period} accounts={data.accounts} dirs={dirs} onClose={() => setAuto(false)} onSaved={() => { setAuto(false); load(); }} />}
    </>
  );
}

function AllocList({ fundId, period, onChanged }: { fundId: number; period: string; onChanged: () => void }) {
  const [items, setItems] = useState<any[] | null>(null);
  const reload = () => api.get<any>(`/api/fund-allocations/?fund=${fundId}&period=${period}&page_size=100`).then((d) => setItems(d.results || d));
  useEffect(() => { reload(); }, [fundId, period]);
  async function del(id: number) { await api.del(`/api/fund-allocations/${id}/`); reload(); onChanged(); }
  async function patch(id: number, amount: number) { await api.patch(`/api/fund-allocations/${id}/`, { amount }); reload(); onChanged(); }
  if (!items) return <div className="muted" style={{ padding: "4px 0 8px 24px", fontSize: 12 }}>…</div>;
  if (!items.length) return <div className="muted" style={{ padding: "4px 0 8px 24px", fontSize: 12 }}>Окремих розподілів немає (можливо, прийшло авто-розподілом раніше).</div>;
  return (
    <div style={{ padding: "2px 0 8px 24px", background: "#f8fafc", borderBottom: "1px solid #f1f5f9" }}>
      <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>Розподіли цього фонду · зміни суму або прибери ✕ (баланс перерахується):</div>
      {items.map((a) => (
        <div key={a.id} className="row" style={{ padding: "4px 0", fontSize: 12.5, alignItems: "center" }}>
          <span style={{ flex: 1 }}>{a.comment || "розподіл"}{a.account_name ? ` · ${a.account_name}` : ""}{a.fin_direction_name ? ` · ${a.fin_direction_name}` : ""}</span>
          <input type="number" defaultValue={a.amount} title="Зміни суму розподілу" onBlur={(e) => patch(a.id, Number(e.target.value))} style={{ width: 92, height: 26, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px", textAlign: "right" }} />
          <span style={{ color: "#ef4444", cursor: "pointer", paddingLeft: 12 }} title="Прибрати цей розподіл" onClick={() => del(a.id)}>✕</span>
        </div>
      ))}
    </div>
  );
}

function AllocModal({ fund, period, accounts, dirs, onClose, onSaved }: any) {
  const [amount, setAmount] = useState("");
  const [account, setAccount] = useState(accounts[0]?.id || "");
  const [direction, setDirection] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    if (!Number(amount)) return;
    setBusy(true);
    try { await api.post("/api/fund-allocations/", { fund: fund.id, account: account || null, fin_direction: direction || null, amount: Number(amount), period, comment }); onSaved(); }
    finally { setBusy(false); }
  }
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, padding: 22, width: 420 }}>
        <h3 style={{ marginTop: 0 }}>Розподіл у фонд</h3>
        <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>✉️ {fund.name} · {period}</div>
        <label className="label">Сума, ₴</label>
        <input type="number" value={amount} autoFocus onChange={(e) => setAmount(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 }} />
        <label className="label">З рахунку</label>
        <select value={account} onChange={(e) => setAccount(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, marginBottom: 10 }}>
          <option value="">—</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <label className="label">Напрямок (необов.)</label>
        <select value={direction} onChange={(e) => setDirection(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, marginBottom: 10 }}>
          <option value="">— усі —</option>{dirs.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <label className="label">Коментар</label>
        <input value={comment} onChange={(e) => setComment(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 14 }} />
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>Скасувати</button>
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={save} disabled={busy}>{busy ? "…" : "Розподілити"}</button>
        </div>
      </div>
    </div>
  );
}

function AutoModal({ period, accounts, dirs, onClose, onSaved }: any) {
  const [revenue, setRevenue] = useState("");
  const [account, setAccount] = useState(accounts[0]?.id || "");
  const [direction, setDirection] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any[] | null>(null);
  async function run() {
    if (!Number(revenue)) return;
    setBusy(true);
    try { const r = await api.post<any>("/api/finance/funds/", { revenue: Number(revenue), account: account || null, fin_direction: direction || null, period }); setRes(r.created); }
    finally { setBusy(false); }
  }
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, padding: 22, width: 440 }}>
        <h3 style={{ marginTop: 0 }}>⚡ Авто-розподіл виручки</h3>
        <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>Кожен фонд виручки (ФВ) отримає свій % від суми за {period}.</div>
        <label className="label">Сума виручки, ₴</label>
        <input type="number" value={revenue} autoFocus onChange={(e) => setRevenue(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 }} />
        <label className="label">На рахунок</label>
        <select value={account} onChange={(e) => setAccount(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, marginBottom: 10 }}>
          <option value="">—</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <label className="label">Напрямок (необов.)</label>
        <select value={direction} onChange={(e) => setDirection(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, marginBottom: 12 }}>
          <option value="">— усі —</option>{dirs.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        {res && <div style={{ background: "#f0fdf4", borderRadius: 8, padding: 10, fontSize: 13, marginBottom: 12 }}>{res.length ? res.map((x, i) => <div key={i}>✓ {x.fund}: {money(x.amount)}</div>) : "Немає фондів виручки з %."}</div>}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={res ? onSaved : onClose}>{res ? "Готово" : "Скасувати"}</button>
          {!res && <button className="btn btn-primary" style={{ flex: 1 }} onClick={run} disabled={busy}>{busy ? "…" : "Розподілити"}</button>}
        </div>
      </div>
    </div>
  );
}

/* ─── ВКЛАДКА: ЗП / KPI МЕНЕДЖЕРІВ (стратегія РОП+психолог) ──────────────── */
function Salary() {
  const [period, setPeriod] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; });
  const [data, setData] = useState<any>(null);
  useEffect(() => { setData(null); api.get<any>(`/api/finance/salary/?period=${period}`).then(setData); }, [period]);
  if (!data) return <div className="spin">Рахуємо ЗП…</div>;
  const c = data.company;
  const tierLabel = (m: number) => m >= 1.3 ? "перевиконання ×1.3" : m >= 1 ? "повні премії ×1.0" : m >= 0.8 ? "майже план ×0.8" : m >= 0.5 ? "половина ×0.5" : "старт ×0.3";
  return (
    <>
      <div className="note">💰 ЗП рахується <b>без жорсткого GATE</b>: премії відкриваються поетапно з 70% плану (×0.3→×1.3). Ставки міняються у вкладці «Фінмодель → ЗП». Плани — у вкладці «Плани».</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <span className="muted" style={{ fontSize: 13 }}>Місяць:</span>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
        <div style={{ flex: 1 }} />
        <span className="muted" style={{ fontSize: 12 }}>ФОП-прогноз: <b>{money(c.total_payroll)}</b></span>
      </div>
      {data.rows.map((r: any) => {
        const pct = r.plan_pct ?? 0;
        return (
          <div key={r.user_id} className="panel" style={{ margin: "10px 0 0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <b style={{ fontSize: 15, flex: 1 }}>{r.user_name}</b>
              <span style={{ fontSize: 12, color: "#64748b" }} title="Множник премій за виконанням плану">{tierLabel(r.tier_mult)}</span>
              <span style={{ background: "linear-gradient(135deg,#16a34a,#15803d)", color: "#fff", padding: "4px 12px", borderRadius: 8, fontWeight: 700 }} title="Прогноз ЗП за місяць">{money(r.total)}</span>
            </div>
            <div style={{ margin: "8px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span className="muted">План {r.plan_target ? money(r.plan_target) : "не встановлено"} · {r.deals} угод · чек {money(r.avg_check)}</span>
                <b style={{ color: pct >= 100 ? "#16a34a" : pct >= 70 ? "#d97706" : "#dc2626" }}>{r.plan_pct != null ? r.plan_pct + "%" : "—"}</b>
              </div>
              <div style={{ height: 10, background: "#e2e8f0", borderRadius: 6, overflow: "hidden", marginTop: 4 }}>
                <div style={{ width: Math.min(100, pct) + "%", height: "100%", background: pct >= 100 ? "#16a34a" : pct >= 70 ? "#d97706" : "#0ea5e9" }} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 12, marginBottom: 8 }}>
              <span title="Фіксований оклад">Оклад {money(r.part_base)}</span>
              <span title="% з обороту">+ оборот {money(r.part_revenue)}</span>
              <span title={`% з маржі (плаваючий ${r.margin_kpi_pct}%)`}>+ маржа {money(r.part_margin)}</span>
              <span title={`${r.kpi_hits} KPI × ${money(r.kpi_premium)} × множник ${r.tier_mult}`} style={{ color: "#7c3aed" }}>+ KPI {money(r.bonus_kpi)}</span>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {r.kpi.map((k: any, i: number) => (
                <span key={i} title={k.detail} style={{ fontSize: 11, padding: "3px 9px", borderRadius: 12, fontWeight: 600,
                  background: k.na ? "#f1f5f9" : k.ok ? "#dcfce7" : "#fee2e2", color: k.na ? "#94a3b8" : k.ok ? "#166534" : "#991b1b" }}>
                  {k.na ? "?" : k.ok ? "✓" : "✕"} {k.name}
                </span>
              ))}
            </div>
          </div>
        );
      })}
      <div className="panel" style={{ margin: "12px 0 0", background: "#f8fafc" }}>
        <div className="muted" style={{ fontSize: 12 }}>🎯 Покриття цілі компанії: ТБ <b>{money(c.breakeven)}</b> · ціль ×1.3 <b>{money(c.target)}</b> · сума планів <b>{money(c.sum_plans)}</b> · покриття <b style={{ color: c.coverage_pct >= 100 ? "#16a34a" : "#dc2626" }}>{c.coverage_pct}%</b></div>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА: ПЛАНИ МЕНЕДЖЕРІВ (3 рівні, персональні) ──────────────────── */
function MPlans() {
  const [period, setPeriod] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; });
  const [sal, setSal] = useState<any>(null);
  const [plans, setPlans] = useState<Record<number, any>>({});
  const load = () => {
    api.get<any>(`/api/finance/salary/?period=${period}`).then(setSal);
    api.get<any>(`/api/manager-plans/?period=${period}&page_size=100`).then((d) => {
      const m: Record<number, any> = {}; (d.results || d).forEach((p: any) => { m[p.user] = p; }); setPlans(m);
    });
  };
  useEffect(() => { setSal(null); load(); }, [period]);
  async function save(userId: number, patch: any) {
    const ex = plans[userId];
    if (ex) await api.patch(`/api/manager-plans/${ex.id}/`, patch);
    else await api.post("/api/manager-plans/", { user: userId, period, min_revenue: 0, target_revenue: 0, ambition_revenue: 0, ...patch });
    load();
  }
  async function recommend(r: any) {
    const fact = r.revenue || 0;
    await save(r.user_id, { min_revenue: Math.round(fact * 0.9), target_revenue: Math.round(fact * 1.2), ambition_revenue: Math.round(fact * 1.5) });
  }
  if (!sal) return <div className="spin">Завантаження…</div>;
  const c = sal.company;
  const inp = { width: 110, height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px", textAlign: "right" } as React.CSSProperties;
  return (
    <>
      <div className="note">🎯 <b>Плани персональні</b> (не однакові!). Норма ≈ факт × 1.2, амбіція ≈ факт × 1.5 (рекомендація РОП). Кнопка «🎁 Авто» ставить рівні від фактичної виручки менеджера.</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <span className="muted" style={{ fontSize: 13 }}>Місяць:</span>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
      </div>
      <div className="panel" style={{ margin: "0 0 12px", background: "#f8fafc" }}>
        <div className="muted" style={{ fontSize: 12 }}>🏢 ТБ компанії <b>{money(c.breakeven)}</b> · ціль ×1.3 <b>{money(c.target)}</b> · сума планів <b>{money(c.sum_plans)}</b> · покриття <b style={{ color: c.coverage_pct >= 100 ? "#16a34a" : "#dc2626" }}>{c.coverage_pct}%</b></div>
      </div>
      {sal.rows.map((r: any) => {
        const p = plans[r.user_id] || {};
        return (
          <div key={r.user_id} className="panel" style={{ margin: "10px 0 0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <b style={{ fontSize: 14, flex: 1 }}>{r.user_name}</b>
              <span className="muted" style={{ fontSize: 12 }}>факт: {money(r.revenue)} · {r.deals} угод</span>
              <button className="btn btn-light" style={{ fontSize: 12 }} title="Поставити рівні автоматично від факту" onClick={() => recommend(r)}>🎁 Авто</button>
            </div>
            <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
              <label style={{ fontSize: 12 }} title="Мінімум — нижче не падати">🟥 Мінімум <input type="number" defaultValue={p.min_revenue || 0} onBlur={(e) => save(r.user_id, { min_revenue: Number(e.target.value) })} style={inp} /></label>
              <label style={{ fontSize: 12 }} title="Норма — головна ціль місяця">🟩 Норма <input type="number" defaultValue={p.target_revenue || 0} onBlur={(e) => save(r.user_id, { target_revenue: Number(e.target.value) })} style={inp} /></label>
              <label style={{ fontSize: 12 }} title="Амбіція — понад-результат">🟦 Амбіція <input type="number" defaultValue={p.ambition_revenue || 0} onBlur={(e) => save(r.user_id, { ambition_revenue: Number(e.target.value) })} style={inp} /></label>
            </div>
          </div>
        );
      })}
    </>
  );
}

const CAT_LABEL: Record<string, string> = {
  revenue_fund: "Фонди виручки (% від кожної угоди)", payment_fee: "Витрати на обробку (грн/угода)",
  variable: "🔁 Змінні витрати (ростуть із продажами)", fixed: "📌 Постійні витрати (фікс щомісяця)",
  skd: "Фонди СКД / розвитку (грн/міс)", upr_cat2: "УПР обов'язкові (у ТБ)", upr_cat3: "УПР відмовні",
  warehouse_rate: "Склад / ставки", config: "Конфіг / ліміти", salary: "Ставки ЗП / KPI менеджера",
};

const GROUP_HINT: Record<string, string> = {
  revenue: "ФВ — скільки відсотків з кожної виручки відкладається (податки, комісії, фонди). Зменшують маржу.",
  margin: "ФМ — операційні витрати, що покриваються з маржі. Постійні = фікс щомісяця, Змінні = ростуть із продажами.",
  skd: "ФСКД — фонди розвитку та резерви, що формуються з чистого (скоригованого) доходу.",
  upr: "УПР — управлінські витрати компанії.",
  other: "Технічні налаштування: комісії еквайрингу, ставки складу, ліміти знижок.",
  salary: "Ставки ЗП: оклад, % обороту, % маржі, премії. Міняєш тут → бонус у картці сделки і ЗП оновлюються синхронно.",
};

// Групи фондів у логіці Finmap: спочатку Виручки, потім Маржі (пост/змінні), потім СКД
const FUND_GROUPS: { key: string; label: string; color: string; cats: string[] }[] = [
  { key: "revenue", label: "📊 ФОНДИ ВИРУЧКИ (ФВ)", color: "#2563eb", cats: ["revenue_fund"] },
  { key: "margin", label: "💎 ФОНДИ МАРЖІ (ФМ) · постійні + змінні", color: "#7c3aed", cats: ["fixed", "variable"] },
  { key: "skd", label: "🎯 ФОНДИ СКОРИГОВАНОГО ДОХОДУ (ФСКД)", color: "#059669", cats: ["skd"] },
  { key: "upr", label: "🏛 УПРАВЛІНСЬКІ (УПР)", color: "#475569", cats: ["upr_cat2", "upr_cat3"] },
  { key: "other", label: "⚙️ ІНШЕ / КОНФІГ", color: "#64748b", cats: ["payment_fee", "warehouse_rate", "config"] },
  { key: "salary", label: "💰 ЗП / KPI МЕНЕДЖЕРА (ставки)", color: "#d97706", cats: ["salary"] },
];

function FinModel() {
  const [arts, setArts] = useState<any[]>([]);
  const [dragId, setDragId] = useState<number | null>(null);
  const [overCat, setOverCat] = useState<string | null>(null);
  const load = () => api.get<any>("/api/finmodel-articles/?page_size=200").then((r) => setArts(r.results || r));
  useEffect(() => { load(); }, []);
  async function save(id: number, patch: any) { await api.patch(`/api/finmodel-articles/${id}/`, patch); }
  async function add(category: string, parent?: number) {
    await api.post("/api/finmodel-articles/", { category, parent: parent ?? null, name: parent ? "Новий підфонд" : "Нова стаття", value: 0,
      value_type: category === "revenue_fund" || category === "variable" ? "percent" : "fixed_sum_per_month", is_envelope: !!parent });
    load();
  }
  async function del(id: number) { if (!confirm("Видалити цю статтю фінмоделі?")) return; await api.del(`/api/finmodel-articles/${id}/`); load(); }
  // перетягування фонду в іншу категорію (разом із підфондами)
  async function moveCat(id: number, newCat: string) {
    const a = arts.find((x) => x.id === id);
    if (!a || a.category === newCat) { setDragId(null); setOverCat(null); return; }
    await save(id, { category: newCat });
    for (const sub of arts.filter((x) => x.parent === id)) await save(sub.id, { category: newCat });
    setDragId(null); setOverCat(null); load();
  }

  const Row = ({ a, sub }: { a: any; sub?: boolean }) => (
    <div className="row" draggable={!sub} onDragStart={() => !sub && setDragId(a.id)} onDragEnd={() => setDragId(null)}
      style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9", alignItems: "center", paddingLeft: sub ? 22 : 0, opacity: dragId === a.id ? 0.4 : 1 }}>
      {!sub && <span title="Перетягни мишкою в іншу категорію" style={{ color: "#cbd5e1", cursor: "grab", marginRight: 4, userSelect: "none" }}>⠿</span>}
      {sub && <span style={{ color: "#cbd5e1", marginRight: 4 }}>↳</span>}
      <input defaultValue={a.name} title="Назва статті / фонду — клікни, щоб перейменувати" onBlur={(e) => save(a.id, { name: e.target.value })}
        style={{ flex: 1, height: 28, border: "1px solid transparent", borderRadius: 6, padding: "0 6px", fontWeight: sub ? 400 : 500, background: "transparent" }} />
      <button title={a.is_envelope ? "Це конверт: тримає гроші для планування. Клікни, щоб вимкнути." : "Зробити конвертом — тоді в нього можна класти гроші у вкладці «Планування»"} onClick={() => save(a.id, { is_envelope: !a.is_envelope }).then(load)}
        style={{ width: 28, height: 26, borderRadius: 6, marginRight: 6, cursor: "pointer", border: "1px solid " + (a.is_envelope ? "#0ea5e9" : "#e2e8f0"), background: a.is_envelope ? "#e0f2fe" : "#fff" }}>✉️</button>
      <input type="number" defaultValue={a.value} title="Значення: % або сума в гривнях (тип праворуч). Впливає на P&L і точку беззбитковості." onBlur={(e) => save(a.id, { value: Number(e.target.value) })} style={{ width: 96, height: 28, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px", textAlign: "right" }} />
      <span className="muted" style={{ width: 64, fontSize: 12 }} title="Одиниця: % від суми, грн/місяць, грн/угоду тощо">{a.unit || a.value_type_display}</span>
      {!sub && <span title="Додати підфонд (під-конверт усередині цього фонду)" style={{ color: "#0ea5e9", cursor: "pointer", paddingLeft: 6, fontWeight: 700 }} onClick={() => add(a.category, a.id)}>＋</span>}
      <span title="Видалити статтю" style={{ color: "#ef4444", cursor: "pointer", paddingLeft: 8 }} onClick={() => del(a.id)}>✕</span>
    </div>
  );

  return (
    <>
      <div className="note">⚙️ <b>Фінмодель</b> — серце розрахунків: звідси рахуються P&L і Точка беззбитковості. Порядок фондів: <b>ФВ (виручки) → ФМ (маржі) → ФСКД (скоригованого доходу)</b>. ✉️ = конверт (тримає гроші для планування). ＋ — додати підфонд. <b>⠿ Перетягни статтю мишкою в іншу категорію</b>, щоб перекласти фонд. Наведи на будь-яке поле — підкаже, що це.</div>
      {FUND_GROUPS.map((g) => {
        const groupArts = arts.filter((a) => g.cats.includes(a.category));
        if (!groupArts.length && g.key !== "revenue" && g.key !== "margin") return null;
        return (
          <div key={g.key} className="panel" style={{ margin: "12px 0 0", borderLeft: `4px solid ${g.color}` }}>
            <b style={{ fontSize: 13.5, color: g.color }} title={GROUP_HINT[g.key] || ""}>{g.label}</b>
            {g.cats.map((c) => {
              const tops = groupArts.filter((a) => a.category === c && !a.parent);
              if (!tops.length && c !== "revenue_fund" && c !== "fixed" && c !== "variable") return null;
              const isOver = overCat === c;
              return (
                <div key={c} style={{ marginTop: 8, borderRadius: 8, outline: isOver ? "2px dashed #0ea5e9" : "none", background: isOver ? "#f0f9ff" : "transparent", padding: isOver ? 6 : 0, transition: "background .12s" }}
                  onDragOver={(e) => { if (dragId) { e.preventDefault(); setOverCat(c); } }}
                  onDragLeave={() => setOverCat((x) => (x === c ? null : x))}
                  onDrop={() => dragId && moveCat(dragId, c)}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                    <span className="muted" style={{ fontSize: 12, fontWeight: 600 }} title={isOver ? "Відпусти тут, щоб перекласти фонд у цю категорію" : "Категорія статей"}>{CAT_LABEL[c]}{isOver ? " ⬇ відпусти тут" : ""}</span>
                    <button className="btn btn-light" style={{ fontSize: 11, padding: "2px 8px" }} title="Додати нову статтю в цю категорію" onClick={() => add(c)}>+ стаття</button>
                  </div>
                  {tops.map((a) => (
                    <div key={a.id}>
                      <Row a={a} />
                      {arts.filter((x) => x.parent === a.id).map((x) => <Row key={x.id} a={x} sub />)}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        );
      })}
    </>
  );
}
