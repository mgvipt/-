/* ============================================================================
 *  ФІНАНСИ  —  frontend/src/pages/Finance.tsx
 *  Вкладки: Дашборд (ДДС) · P&L (ATM) · Точка беззбитковості · Фінмодель.
 *  Источник формул — Wallcov Cashflow. Документация: docs/TZ-finmodule.md.
 * ========================================================================== */
import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import DealCard from "./DealCard";
import { useNavigate } from "react-router-dom";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
function useNav() { return useNavigate(); }

const money = (n: number) => Math.round(n || 0).toLocaleString("ru") + " ₴";
const pad = (n: number) => String(n).padStart(2, "0");
const today = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const monthStart = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`; };

export default function Finance() {
  const { t } = useLang();
  const [tab, setTab] = useState<"dash" | "journal" | "pnl" | "be" | "dir" | "plan" | "grow" | "salary" | "mplan" | "time" | "ref" | "model">("dash");
  const tabs: [string, React.ReactNode][] = [["dash", <><Icon n="💰" size={15} /> {t("Дашборд","Дашборд")}</>], ["journal", <><Icon n="🧾" size={15} /> {t("Журнал","Журнал")}</>], ["pnl", <><Icon n="📊" size={15} /> {t("P&L (ATM)","P&L (ATM)")}</>], ["be", <><Icon n="🎯" size={15} /> {t("Точка безубыточности","Точка беззбитковості")}</>], ["dir", <><Icon n="🗂" size={15} /> {t("Направления (проекты)","Напрямки (проекти)")}</>], ["plan", <><Icon n="💼" size={15} /> {t("Планирование","Планування")}</>], ["grow", <><Icon n="🚀" size={15} /> {t("Рост","Зростання")}</>], ["salary", <><Icon n="💰" size={15} /> {t("ЗП/KPI","ЗП/KPI")}</>], ["mplan", <><Icon n="🎯" size={15} /> {t("Планы","Плани")}</>], ["time", <><Icon n="🕐" size={15} /> {t("Табель","Табель")}</>], ["ref", <><Icon n="📚" size={15} /> {t("Справочники","Довідники")}</>], ["model", <><Icon n="⚙️" size={15} /> {t("Финмодель","Фінмодель")}</>]];
  return (
    <div className="scroll pad fade">
      <div className="note warn"><Icon n="🔒" size={15} /> {t("Раздел видят только роли с правом","Розділ бачать тільки ролі з правом")} <b>finance.view</b>.</div>
      <div style={{ display: "flex", gap: 6, margin: "12px 0", flexWrap: "wrap" }}>
        {tabs.map(([k, l]) => <button key={k} className={tab === k ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab(k as any)}>{l}</button>)}
      </div>
      {tab === "dash" && <Dashboard />}
      {tab === "journal" && <Journal />}
      {tab === "pnl" && <PnL />}
      {tab === "be" && <Breakeven />}
      {tab === "dir" && <Directions />}
      {tab === "plan" && <Planning />}
      {tab === "grow" && <Growth />}
      {tab === "salary" && <Salary />}
      {tab === "mplan" && <MPlans />}
      {tab === "time" && <Timesheet />}
      {tab === "ref" && <Reference />}
      {tab === "model" && <FinModel />}
    </div>
  );
}

/* ─── Период-пикер (общий) ─────────────────────────────────────────────── */
function Period({ from, to, set }: { from: string; to: string; set: (f: string, t: string) => void }) {
  const { t } = useLang();
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
      <span className="muted" style={{ fontSize: 13 }}>{t("Период","Період")}:</span>
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
/* Поле контрагента зі звʼязком із клієнтами CRM: автокомпліт + створення клієнта */
function CpField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useLang();
  const [res, setRes] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (!value.trim()) { setRes([]); return; }
    const t = setTimeout(() => api.get<any>(`/api/contacts/?search=${encodeURIComponent(value)}&page_size=6`).then((d) => setRes(d.results || d)).catch(() => setRes([])), 250);
    return () => clearTimeout(t);
  }, [value]);
  async function createClient() {
    const parts = value.trim().split(/\s+/);
    await api.post("/api/contacts/", { first_name: parts[0] || value.trim(), last_name: parts.slice(1).join(" ") });
    setMsg(t("✓ Клиент создан в CRM","✓ Клієнта створено в CRM")); setOpen(false); setTimeout(() => setMsg(""), 2500);
  }
  const exact = res.some((c) => `${c.first_name || ""} ${c.last_name || ""}`.trim().toLowerCase() === value.trim().toLowerCase());
  const inpS = { height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", width: "100%", marginBottom: 4 } as React.CSSProperties;
  return (
    <div style={{ position: "relative", marginBottom: 10 }}>
      <input value={value} onChange={(e) => { onChange(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} placeholder={t("Клиент / контрагент (связь с CRM)…","Клієнт / контрагент (звʼязок з CRM)…")} style={inpS} />
      {open && value.trim() && (res.length > 0 || !exact) && (
        <div style={{ position: "absolute", top: 38, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 8px 24px rgba(15,23,42,.15)", zIndex: 30, maxHeight: 220, overflowY: "auto" }}>
          {res.map((c) => (
            <div key={c.id} onClick={() => { onChange(`${c.first_name || ""} ${c.last_name || ""}`.trim()); setOpen(false); }} style={{ padding: "7px 10px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13 }}>
              <Icon n="👤" size={15} /> {`${c.first_name || ""} ${c.last_name || ""}`.trim() || "—"} {c.phone ? <span className="muted">· {c.phone}</span> : null}
            </div>
          ))}
          {!exact && <div onClick={createClient} style={{ padding: "8px 10px", cursor: "pointer", fontSize: 13, color: "#16a34a", fontWeight: 600 }}><Icon n="➕" size={14} /> {t("Создать клиента","Створити клієнта")} «{value.trim()}» {t("в CRM","у CRM")}</div>}
        </div>
      )}
      {msg && <div style={{ fontSize: 12, color: "#16a34a" }}>{msg}</div>}
    </div>
  );
}

function Journal() {
  const { t } = useLang();
  const [tx, setTx] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [arts, setArts] = useState<any[]>([]);
  const [dirs, setDirs] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const blank = { id: 0, direction: "out", amount: "", account: 0, transfer_account: 0, fin_article: 0, fin_direction: 0, channel: "", counterparty: "", set_category: "", currency: "UAH", rate: 1, comment: "", date: "" };
  const [f, setF] = useState<any>(blank);
  const [ff, setFf] = useState(""); const [ft, setFt] = useState(""); const [fq, setFq] = useState("");
  const [page, setPage] = useState(1); const [pageSize, setPageSize] = useState(50); const [count, setCount] = useState(0);
  const [showCols, setShowCols] = useState(false);
  const emptyCf = { direction: "", amount_min: "", amount_max: "", currency: "", cat: "", cp: "", account: "", fin_article: "", fin_direction: "", channel: "", comment: "" };
  const [cf, setCf] = useState<any>(emptyCf);
  const [selAcc, setSelAcc] = useState<number[]>([]);
  const [drawerDeal, setDrawerDeal] = useState<number | null>(null);
  const load = (p = page) => {
    const qp = new URLSearchParams({ page: String(p), page_size: String(pageSize) });
    if (ff) qp.set("from", ff); if (ft) qp.set("to", ft); if (fq.trim()) qp.set("q", fq.trim());
    Object.entries(cf).forEach(([k, v]) => { if (v) qp.set(k, String(v)); });
    if (selAcc.length) qp.set("accounts", selAcc.join(","));
    return api.get<any>(`/api/transactions/?${qp.toString()}`).then((d) => { setTx(d.results || d); setCount(d.count ?? (d.results ? d.results.length : (d.length || 0))); });
  };
  function apply() { setPage(1); load(1); }
  function goPage(p: number) { setPage(p); load(p); }
  function resetAll() { setFq(""); setFf(""); setFt(""); setCf(emptyCf); setPage(1); setTimeout(() => load(1), 0); }
  useEffect(() => {
    load(1);
    api.get<any>("/api/accounts/").then((d) => setAccounts(d.results || d));
    api.get<any>("/api/finmodel-articles/?page_size=200").then((d) => setArts(d.results || d));
    api.get<any>("/api/fin-directions/?page_size=100").then((d) => setDirs(d.results || d));
    api.get<any>("/api/categories/").then((d) => setCats(d.results || d)).catch(() => setCats([]));
  }, []);
  useEffect(() => { load(1); setPage(1); }, [pageSize]);
  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  function openNew(direction: string) { setF({ ...blank, direction, date: new Date().toISOString().slice(0, 10) }); setOpen(true); }
  function openEdit(t: any) {
    setF({ id: t.id, direction: t.direction, amount: t.amount, account: t.account || 0, fin_article: t.fin_article || 0, fin_direction: t.fin_direction || 0,
      transfer_account: t.transfer_account || 0, channel: t.channel || "", counterparty: t.counterparty || "", set_category: t.category_name || "", currency: t.currency || "UAH", rate: t.rate || 1, comment: t.comment || "", date: t.date || "" });
    setOpen(true);
  }
  async function fetchRate(ccy: string) {
    if (ccy === "UAH") { setF((x: any) => ({ ...x, currency: ccy, rate: 1 })); return; }
    setF((x: any) => ({ ...x, currency: ccy }));
    try { const r = await api.get<any>(`/api/finance/fx-rate/?ccy=${ccy}`); if (r.rate) setF((x: any) => ({ ...x, rate: r.rate })); } catch { /* лишаємо поточний */ }
  }
  async function save() {
    if (!Number(f.amount)) return;
    const isT = f.direction === "transfer";
    const body: any = { direction: f.direction, amount: Number(f.amount), account: f.account || accounts[0]?.id,
      comment: f.comment, currency: f.currency, rate: Number(f.rate) || 1 };
    if (f.date) body.date = f.date;
    if (isT) {
      if (!f.transfer_account || f.transfer_account === f.account) { alert("Оберіть інший рахунок-отримувач"); return; }
      body.transfer_account = f.transfer_account; body.fin_article = null; body.fin_direction = null;
    } else {
      body.channel = f.channel; body.counterparty = f.counterparty; body.set_category = f.set_category;
      body.fin_article = f.fin_article || null; body.fin_direction = f.fin_direction || null; body.transfer_account = null;
    }
    if (f.id) await api.patch(`/api/transactions/${f.id}/`, body);
    else await api.post("/api/transactions/", body);
    setOpen(false); setF(blank); load();
  }
  async function del() {
    if (!f.id || !confirm("Видалити цю операцію?")) return;
    await api.del(`/api/transactions/${f.id}/`); setOpen(false); setF(blank); load();
  }
  const inp = { height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", width: "100%", marginBottom: 10 } as React.CSSProperties;
  const grnEq = Number(f.amount || 0) * (Number(f.rate) || 1);

  function toggleAcc(id: number) {
    setSelAcc((cur) => { const n = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]; setTimeout(() => { setPage(1); const qp = new URLSearchParams({ page: "1", page_size: String(pageSize) }); if (ff) qp.set("from", ff); if (ft) qp.set("to", ft); if (fq.trim()) qp.set("q", fq.trim()); Object.entries(cf).forEach(([k, v]) => { if (v) qp.set(k, String(v)); }); if (n.length) qp.set("accounts", n.join(",")); api.get<any>(`/api/transactions/?${qp.toString()}`).then((d) => { setTx(d.results || d); setCount(d.count ?? 0); }); }, 0); return n; });
  }
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      <div className="panel acc-sidebar" style={{ width: 220, flex: "0 0 220px", margin: 0, maxHeight: "80vh", overflowY: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <b style={{ fontSize: 13 }}><Icon n="🏦" size={14} /> Рахунки</b>
          {selAcc.length > 0 && <span style={{ fontSize: 11, color: "#2563eb", cursor: "pointer" }} onClick={() => { setSelAcc([]); setTimeout(() => load(1), 0); }}>скинути</span>}
        </div>
        <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>Обери один або кілька — журнал відфільтрується.</div>
        {accounts.map((a) => (
          <label key={a.id} style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 4px", borderRadius: 6, cursor: "pointer", fontSize: 12.5, background: selAcc.includes(a.id) ? "#eff6ff" : "transparent" }}>
            <input type="checkbox" checked={selAcc.includes(a.id)} onChange={() => toggleAcc(a.id)} />
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
            <b style={{ fontSize: 11, color: a.balance < 0 ? "#dc2626" : "#16a34a" }}>{money(a.balance)}</b>
          </label>
        ))}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }} className="journal-filter">
        <input value={fq} onChange={(e) => setFq(e.target.value)} onKeyDown={(e) => e.key === "Enter" && apply()} placeholder={t("🔍 Поиск по всему: сумма, контрагент, комментарий, счёт…","🔍 Пошук по всьому: сума, контрагент, коментар, рахунок…")} style={{ flex: "1 1 220px", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 10px" }} />
        <span className="muted" style={{ fontSize: 12 }} title={t("Отдельный фильтр по дате операции","Окремий фільтр по даті операції")}><Icon n="📅" size={13} /> {t("Дата","Дата")}:</span>
        <input type="date" value={ff} onChange={(e) => setFf(e.target.value)} title={t("Дата от","Дата від")} style={{ height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 6px" }} />
        <input type="date" value={ft} onChange={(e) => setFt(e.target.value)} title={t("Дата до","Дата до")} style={{ height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 6px" }} />
        <button className="btn btn-light" onClick={() => setShowCols((x) => !x)} title={t("Фильтры по каждому столбцу","Фільтри по кожному стовпцю")}><Icon n="⚙" size={14} /> {t("Столбцы","Стовпці")} {showCols ? "▲" : "▼"}</button>
        <button className="btn btn-primary" onClick={apply}>{t("Найти","Знайти")}</button>
        <button className="btn btn-light" onClick={resetAll}>{t("Сбросить всё","Скинути все")}</button>
      </div>
      {showCols && (
        <div className="panel journal-cols" style={{ margin: "0 0 8px", padding: 12, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px,1fr))", gap: 8 }}>
          {(() => { const cs = { height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", width: "100%" } as React.CSSProperties; const set = (k: string, v: any) => setCf((c: any) => ({ ...c, [k]: v })); return (<>
            <select value={cf.direction} onChange={(e) => set("direction", e.target.value)} style={cs}><option value="">{t("Тип: все","Тип: усі")}</option><option value="in">{t("Доход","Дохід")}</option><option value="out">{t("Расход","Витрата")}</option><option value="transfer">{t("Перевод","Переказ")}</option></select>
            <input value={cf.amount_min} onChange={(e) => set("amount_min", e.target.value)} type="number" placeholder={t("Сумма от","Сума від")} style={cs} />
            <input value={cf.amount_max} onChange={(e) => set("amount_max", e.target.value)} type="number" placeholder={t("Сумма до","Сума до")} style={cs} />
            <select value={cf.currency} onChange={(e) => set("currency", e.target.value)} style={cs}><option value="">{t("Валюта: все","Валюта: усі")}</option>{["UAH","USD","EUR","PLN","GBP"].map((x) => <option key={x} value={x}>{x}</option>)}</select>
            <input value={cf.cat} onChange={(e) => set("cat", e.target.value)} placeholder={t("Категория","Категорія")} style={cs} />
            <input value={cf.cp} onChange={(e) => set("cp", e.target.value)} placeholder={t("Контрагент","Контрагент")} style={cs} />
            <select value={cf.account} onChange={(e) => set("account", e.target.value)} style={cs}><option value="">{t("Счёт: все","Рахунок: усі")}</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
            <select value={cf.fin_article} onChange={(e) => set("fin_article", e.target.value)} style={cs}><option value="">{t("Фонд: все","Фонд: усі")}</option>{arts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
            <select value={cf.fin_direction} onChange={(e) => set("fin_direction", e.target.value)} style={cs}><option value="">{t("Направление: все","Напрямок: усі")}</option>{dirs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
            <select value={cf.channel} onChange={(e) => set("channel", e.target.value)} style={cs}><option value="">{t("Канал: все","Канал: усі")}</option>{CHANNELS.filter((c) => c[0]).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            <input value={cf.comment} onChange={(e) => set("comment", e.target.value)} placeholder={t("Комментарий","Коментар")} style={cs} />
            <button className="btn btn-primary" onClick={apply}>{t("Применить фильтры","Застосувати фільтри")}</button>
          </>); })()}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <button className="btn btn-primary" title={t("Добавить поступление денег","Додати надходження грошей")} onClick={() => openNew("in")}>+ {t("Доход","Дохід")}</button>
        <button className="btn btn-light" title={t("Добавить расход","Додати витрату")} onClick={() => openNew("out")}>− {t("Расход","Витрата")}</button>
        <button className="btn btn-light" title={t("Перевод между счетами — не считается ни в доход, ни в расход","Переказ між рахунками — не рахується ні в дохід, ні у витрати")} onClick={() => openNew("transfer")}>⇄ {t("Перевод","Переказ")}</button>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
          <span className="muted">{t("На стр.","На стор.")}:</span>
          <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6 }}>{[20, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}</select>
          <span className="muted">{t("Всего","Всього")}: <b>{count}</b></span>
          <button className="btn btn-light" disabled={page <= 1} onClick={() => goPage(page - 1)}>←</button>
          <span>{t("стр.","стор.")} <b>{page}</b> {t("из","з")} {totalPages}</span>
          <button className="btn btn-light" disabled={page >= totalPages} onClick={() => goPage(page + 1)}>→</button>
        </div>
      </div>
      <div className="panel" style={{ margin: 0, padding: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", fontSize: 13 }}>
          <thead><tr>
            <th style={{ padding: "8px 12px" }}>{t("Дата","Дата")}</th><th>{t("Сумма","Сума")}</th><th>{t("Вал.","Вал.")}</th><th>₴</th><th>{t("Категория","Категорія")}</th><th>{t("Контрагент","Контрагент")}</th><th>{t("Счёт","Рахунок")}</th><th>{t("Сделка","Сделка")}</th><th>{t("Фонд","Фонд")}</th><th>{t("Направление","Напрямок")}</th><th>{t("Канал","Канал")}</th><th>{t("Комментарий","Коментар")}</th>
          </tr></thead>
          <tbody>
            {tx.length === 0 && <tr><td colSpan={12} className="muted" style={{ padding: 14 }}>{t("Операций ещё нет. Добавь вручную или они появятся при оплате сделок.","Операцій ще немає. Додай вручну або вони зʼявляться при оплаті сделок.")}</td></tr>}
            {tx.map((r) => (
              <tr key={r.id} onClick={() => openEdit(r)} title={t("Кликни, чтобы посмотреть и изменить","Клікни, щоб переглянути та змінити")} style={{ borderBottom: "1px solid #f1f5f9", cursor: "pointer" }}>
                <td className="muted" style={{ padding: "8px 12px" }}>{new Date(r.date || r.created_at).toLocaleDateString("ru")}</td>
                <td style={{ fontWeight: 600, color: r.direction === "in" ? "#16a34a" : r.direction === "transfer" ? "#6366f1" : "#dc2626" }}>{r.direction === "in" ? "+" : r.direction === "transfer" ? "⇄ " : "−"}{Number(r.amount).toLocaleString("ru")}</td>
                <td className="muted">{r.currency || "UAH"}</td>
                <td className="muted">{Number(r.amount_uah || r.amount).toLocaleString("ru")} ₴</td>
                <td>{r.direction === "transfer" ? <span style={{ color: "#6366f1" }}>→ {r.transfer_account_name}</span> : (r.category_name || <span className="muted">—</span>)}</td>
                <td>{r.direction === "transfer" ? <span className="muted">переказ</span> : (r.counterparty || <span className="muted">—</span>)}</td>
                <td className="muted">{r.account_name}</td>
                <td onClick={(e) => { e.stopPropagation(); if (r.deal) setDrawerDeal(r.deal); }}>{r.deal ? <span style={{ color: "#1d4ed8", cursor: "pointer", fontWeight: 600 }} title="Відкрити картку сделки">#{r.deal}{r.deal_title ? " · " + r.deal_title.slice(0, 16) : ""} · {Number(r.amount).toLocaleString("ru")}₴</span> : <span className="muted">—</span>}</td>
                <td>{r.fin_article_name || <span className="muted">—</span>}</td>
                <td>{r.fin_direction_name || <span className="muted">—</span>}</td>
                <td className="muted">{(CHANNELS.find((c) => c[0] === r.channel) || ["", "—"])[1]}</td>
                <td className="muted" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.comment}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </div>

      {drawerDeal && (
        <div onClick={() => setDrawerDeal(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.35)", zIndex: 60 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ position: "absolute", top: 0, right: 0, height: "100%", width: "76%", background: "#f1f5f9", boxShadow: "-12px 0 40px rgba(15,23,42,.25)", overflowY: "auto" }}>
            <div style={{ position: "sticky", top: 0, zIndex: 5, display: "flex", justifyContent: "flex-end", padding: 8, background: "#fff", borderBottom: "1px solid #e2e8f0" }}>
              <button className="btn btn-light" onClick={() => setDrawerDeal(null)}>✕ {t("Закрыть","Закрити")}</button>
            </div>
            <DealCard dealId={drawerDeal} onClose={() => setDrawerDeal(null)} />
          </div>
        </div>
      )}

      {open && (
        <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 440, maxHeight: "90vh", overflowY: "auto" }}>
            <h3 style={{ marginTop: 0 }}>{f.id ? t("Операция №","Операція №") + f.id : (f.direction === "in" ? t("Доход","Дохід") : f.direction === "transfer" ? t("Перевод между счетами","Переказ між рахунками") : t("Расход","Витрата"))}</h3>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ flex: 2 }}>
                <label className="label">{t("Сумма","Сума")}</label>
                <input type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} style={inp} autoFocus title={t("Сумма в выбранной валюте","Сума у вибраній валюті")} />
              </div>
              <div style={{ flex: 1 }}>
                <label className="label">{t("Валюта","Валюта")}</label>
                <select value={f.currency} onChange={(e) => fetchRate(e.target.value)} style={inp} title={t("Курс подтянется из НБУ автоматически","Курс підтягнеться з НБУ автоматично")}>
                  {["UAH", "USD", "EUR", "PLN", "GBP"].map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
            {f.currency !== "UAH" && (
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, fontSize: 13 }}>
                <span className="muted">{t("Курс НБУ","Курс НБУ")}:</span>
                <input type="number" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value })} style={{ width: 90, height: 30, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }} title={t("Курс грн за 1 единицу валюты (можно исправить вручную)","Курс грн за 1 одиницю валюти (можна виправити вручну)")} />
                <span style={{ fontWeight: 600, color: "#0ea5e9" }}>= {money(grnEq)}</span>
              </div>
            )}
            <label className="label">{t("Дата операции","Дата операції")}</label>
            <input type="date" value={f.date || ""} onChange={(e) => setF({ ...f, date: e.target.value })} style={inp} title={t("Можно указать прошедшую дату","Можна вказати минулу дату")} />
            {f.direction === "transfer" ? (
              <>
                <label className="label" title={t("Откуда списываются деньги","Звідки списуються гроші")}>{t("Со счёта","З рахунку")}</label>
                <select value={f.account} onChange={(e) => setF({ ...f, account: Number(e.target.value) })} style={inp}>
                  <option value={0}>—</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.name} ({Number(a.balance).toLocaleString("ru")} ₴)</option>)}
                </select>
                <label className="label" title={t("Куда поступают деньги","Куди надходять гроші")}>{t("На счёт (получатель)","На рахунок (отримувач)")}</label>
                <select value={f.transfer_account} onChange={(e) => setF({ ...f, transfer_account: Number(e.target.value) })} style={inp}>
                  <option value={0}>—</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.name} ({Number(a.balance).toLocaleString("ru")} ₴)</option>)}
                </select>
                <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("↔ Перевод не считается ни в доход, ни в расход — только движение между счетами.","↔ Переказ не рахується ні в дохід, ні у витрати — лише рух між рахунками.")}</div>
              </>
            ) : (
              <>
                <label className="label" title={t("Категория операции (как в Финмапе): Онлайн, Салон, Закупка, Аренда, Реклама…","Категорія операції (як у Фінмапі): Онлайн, Салон, Закупка, Оренда, Реклама…")}>{t("Категория","Категорія")}</label>
                <input value={f.set_category} onChange={(e) => setF({ ...f, set_category: e.target.value })} list="catlist" placeholder={t("Напр. Онлайн (Instagram/TikTok/сайт)","Напр. Онлайн (Instagram/TikTok/сайт)")} style={inp} />
                <datalist id="catlist">{cats.map((c) => <option key={c.id} value={c.name} />)}</datalist>
                <label className="label" title={t("От кого поступили / кому уплатили деньги. Связь с клиентами CRM.","Від кого надійшли / кому сплатили гроші. Звʼязок із клієнтами CRM.")}>{t("Мой контрагент","Мій контрагент")}</label>
                <CpField value={f.counterparty} onChange={(v) => setF({ ...f, counterparty: v })} />
                <label className="label">{t("Счёт","Рахунок")}</label>
                <select value={f.account} onChange={(e) => setF({ ...f, account: Number(e.target.value) })} style={inp}>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.name} ({Number(a.balance).toLocaleString("ru")} ₴)</option>)}
                </select>
                <label className="label" title={t("Фонд для аналитики и точки безубыточности","Фонд для аналітики та точки беззбитковості")}>{t("Фонд (статья)","Фонд (стаття)")}</label>
                <select value={f.fin_article} onChange={(e) => setF({ ...f, fin_article: Number(e.target.value) })} style={inp}>
                  <option value={0}>{t("— без фонда —","— без фонду —")}</option>
                  {arts.map((a) => <option key={a.id} value={a.id}>{a.category_display}: {a.name}</option>)}
                </select>
                <label className="label" title={t("Направление (проект): откуда/куда деньги","Напрямок (проект): звідки/куди гроші")}>{t("Направление","Напрямок")}</label>
                <select value={f.fin_direction} onChange={(e) => setF({ ...f, fin_direction: Number(e.target.value) })} style={inp}>
                  <option value={0}>{t("— без направления —","— без напрямку —")}</option>
                  {dirs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
                <label className="label" title={t("Канал/источник поступления","Канал/джерело надходження")}>{t("Канал","Канал")}</label>
                <select value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })} style={inp}>
                  {CHANNELS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </>
            )}
            <label className="label">{t("Комментарий","Коментар")}</label>
            <input value={f.comment} onChange={(e) => setF({ ...f, comment: e.target.value })} style={inp} />
            {f.id ? <Attachments txId={f.id} /> : <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}><Icon n="📎" size={14} /> {t("Сохрани операцию — тогда сможешь прикрепить фото/скан чека.","Збережи операцію — тоді зможеш прикріпити фото/скан чека.")}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              {f.id ? <button className="btn" style={{ background: "#fef2f2", color: "#dc2626" }} onClick={del} title={t("Удалить операцию","Видалити операцію")}><Icon n="🗑" size={15} /></button> : null}
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setOpen(false)}>{t("Отмена","Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={save}>{t("Сохранить","Зберегти")}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Attachments({ txId }: { txId: number }) {
  const { t } = useLang();
  const [items, setItems] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const reload = () => api.get<any>(`/api/transactions/${txId}/attachments/`).then((d) => setItems(d || [])).catch(() => setItems([]));
  useEffect(() => { reload(); }, [txId]);
  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]; if (!file) return;
    setErr(""); setBusy(true);
    try { await api.upload(`/api/transactions/${txId}/attach/`, file); reload(); }
    catch (x: any) { setErr(String(x).includes("10") ? t("Файл больше 10 МБ","Файл більший за 10 МБ") : t("Не удалось загрузить","Не вдалося завантажити")); }
    finally { setBusy(false); e.target.value = ""; }
  }
  async function openFile(a: any) {
    try { const url = await api.blobUrl(`/api/attachments/${a.id}/file/`); window.open(url, "_blank"); }
    catch { setErr(t("Не удалось открыть","Не вдалося відкрити")); }
  }
  async function del(id: number) { await api.del(`/api/attachments/${id}/file/`); reload(); }
  return (
    <div style={{ marginBottom: 10 }}>
      <label className="label" title={t("Прикрепи фото или скан чека. С телефона откроется камера.","Прикріпи фото або скан чека. З телефона відкриється камера.")}><Icon n="📎" size={14} /> {t("Чек / документы","Чек / документи")}</label>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
        {items.map((a) => (
          <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 4, background: "#f1f5f9", borderRadius: 8, padding: "4px 8px", fontSize: 12 }}>
            <span style={{ cursor: "pointer", color: "#1d4ed8", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={t("Открыть","Відкрити")} onClick={() => openFile(a)}>{a.content_type?.startsWith("image/") ? <Icon n="🖼" size={14} /> : <Icon n="📄" size={14} />} {a.filename}</span>
            <span style={{ color: "#ef4444", cursor: "pointer" }} title={t("Удалить","Видалити")} onClick={() => del(a.id)}>✕</span>
          </div>
        ))}
        {items.length === 0 && <span className="muted" style={{ fontSize: 12 }}>{t("Чеков ещё нет","Чеків ще немає")}</span>}
      </div>
      <label className="btn btn-light" style={{ fontSize: 13, cursor: "pointer", display: "inline-block" }}>
        {busy ? t("Загрузка…","Завантаження…") : <><Icon n="📷" size={14} /> {t("Добавить фото / файл","Додати фото / файл")}</>}
        <input type="file" accept="image/*,application/pdf" capture="environment" onChange={upload} style={{ display: "none" }} disabled={busy} />
      </label>
      {err && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 4 }}>{err}</div>}
    </div>
  );
}

function Dashboard() {
  /* Дашборд v2 (за мотивами ФінМапа): ГЛОБАЛЬНИЙ період на всі блоки,
     рух грошей grouped-bars + лінія сальдо, донати по категоріях, тренд 12 міс. */
  const { t } = useLang();
  const today = new Date();
  const iso = (dt: Date) => dt.toISOString().slice(0, 10);
  const [from, setFrom] = useState(iso(new Date(today.getFullYear(), today.getMonth(), 1)));
  const [to, setTo] = useState(iso(today));
  const [preset, setPreset] = useState("month");
  const [d, setD] = useState<any>(null);
  const [allAcc, setAllAcc] = useState(false);
  useEffect(() => { setD(null); api.get<any>(`/api/finance/overview/?from=${from}&to=${to}`).then(setD).catch(() => setD(null)); }, [from, to]);
  function pick(p: string) {
    setPreset(p);
    const n = new Date();
    if (p === "month") { setFrom(iso(new Date(n.getFullYear(), n.getMonth(), 1))); setTo(iso(n)); }
    else if (p === "prev") { setFrom(iso(new Date(n.getFullYear(), n.getMonth() - 1, 1))); setTo(iso(new Date(n.getFullYear(), n.getMonth(), 0))); }
    else if (p === "quarter") { setFrom(iso(new Date(n.getTime() - 89 * 864e5))); setTo(iso(n)); }
    else if (p === "year") { setFrom(iso(new Date(n.getFullYear(), 0, 1))); setTo(iso(n)); }
    else if (p === "all") { setFrom("2024-01-01"); setTo(iso(n)); }
  }
  if (!d) return <div className="spin">Завантаження дашборда…</div>;

  const k = d.kpi; const dNet = k.net - k.prev_net;
  const netColor = k.net > 0 ? "#16a34a" : k.net < 0 ? "#dc2626" : "#64748b";
  const kpiCards = [
    { t: t("Чистый (период)","Чистий (період)"), v: k.net, c: netColor, sub: `${dNet >= 0 ? "▲" : "▼"} ${money(Math.abs(dNet))} ${t("vs пред. период","vs попер. період")}` },
    { t: t("Деньги на счетах","Гроші на рахунках"), v: k.balance, c: "#0ea5e9", sub: `${d.accounts.length} ${t("счетов","рахунків")}` },
    { t: t("Поступления (период)","Надходження (період)"), v: k.income, c: "#16a34a", sub: `${t("маржа","маржа")} ${d.ratios.margin_pct}%` },
    { t: t("Списания (период)","Списання (період)"), v: k.expense, c: "#ef4444", sub: `${d.ratios.expense_ratio}% ${t("от поступлений","від надходжень")}` },
  ];

  const rows = d.series?.rows || [];
  const smax = Math.max(...rows.map((x: any) => Math.max(x.in, x.out)), 1);
  const nmax = Math.max(...rows.map((x: any) => Math.abs(x.net)), 1);
  const slbl = (x: any) => d.series.granularity === "day" ? x.d.slice(8) + "." + x.d.slice(5, 7) : x.d.slice(5) + "." + x.d.slice(2, 4);
  const CH = 170; // висота графіка руху
  const netY = (v: number) => CH / 2 - (v / nmax) * (CH / 2 - 8);

  const months = d.months || [];
  const mmax = Math.max(...months.map((m: any) => Math.max(m.income, m.expense)), 1);
  const mnetmax = Math.max(...months.map((m: any) => Math.abs(m.net)), 1);
  const MH = 150;
  const mNetY = (v: number) => MH / 2 - (v / mnetmax) * (MH / 2 - 6);

  const PAL = ["#16a34a", "#6366f1", "#f59e0b", "#0ea5e9", "#ec4899", "#8b5cf6", "#14b8a6", "#f97316", "#84cc16", "#64748b"];
  const Donut = ({ items, title, total }: { items: any[]; title: string; total: number }) => {
    const sum = items.reduce((s: number, x: any) => s + x.sum, 0) || 1;
    let acc = 0;
    const stops = items.map((x: any, i: number) => {
      const a0 = acc / sum * 360; acc += x.sum;
      return `${PAL[i % PAL.length]} ${a0}deg ${acc / sum * 360}deg`;
    }).join(", ");
    return (
      <div className="panel" style={{ margin: 0 }}>
        <b style={{ fontSize: 14 }}>{title}</b> <span className="muted" style={{ fontSize: 12 }}>{money(total)}</span>
        {items.length === 0 ? <div className="muted" style={{ fontSize: 12, padding: 16 }}>{t("Нет данных за период","Немає даних за період")}</div> : (
        <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
          <div style={{ width: 140, height: 140, borderRadius: "50%", flexShrink: 0, background: `conic-gradient(${stops})`, position: "relative" }}>
            <div style={{ position: "absolute", inset: 34, background: "var(--panel, #fff)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 }}>{items.length}</div>
          </div>
          <div style={{ flex: 1, minWidth: 180 }}>
            {items.slice(0, 8).map((x: any, i: number) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, padding: "2px 0" }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: PAL[i % PAL.length], flexShrink: 0 }} />
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.name}</span>
                <b>{money(x.sum)}</b>
                <span className="muted" style={{ width: 38, textAlign: "right" }}>{Math.round(x.sum / sum * 100)}%</span>
              </div>
            ))}
          </div>
        </div>
        )}
      </div>
    );
  };

  const expMax = Math.max(...d.top_expense.map((e: any) => e.sum), 1);
  const accShown = allAcc ? d.accounts : d.accounts.slice(0, 8);
  const aColor = (l: string) => l === "danger" ? "#dc2626" : l === "warn" ? "#d97706" : "#16a34a";
  const aBg = (l: string) => l === "danger" ? "#fef2f2" : l === "warn" ? "#fffbeb" : "#f0fdf4";

  return (
    <>
      {/* ГЛОБАЛЬНИЙ ПЕРІОД — діє на всі блоки */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <b style={{ fontSize: 13 }}>{t("Период","Період")}:</b>
        {[["month", t("Этот месяц","Цей місяць")], ["prev", t("Прошлый","Минулий")], ["quarter", t("90 дней","90 днів")], ["year", t("Год","Рік")], ["all", t("Всё","Все")]].map(([kk, l]) => (
          <button key={kk} onClick={() => pick(kk)} style={{ fontSize: 12, padding: "4px 12px", borderRadius: 8, cursor: "pointer", fontWeight: 600, border: "1px solid " + (preset === kk ? "var(--brand)" : "#cbd5e1"), background: preset === kk ? "var(--brand)" : "#fff", color: preset === kk ? "#fff" : "#475569" }}>{l}</button>
        ))}
        <input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPreset(""); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 6px", fontSize: 12 }} />
        <span className="muted">—</span>
        <input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPreset(""); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 6px", fontSize: 12 }} />
      </div>

      {/* KPI-СВІТЛОФОР */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
        {kpiCards.map((c) => (
          <div key={c.t} className="panel" style={{ margin: 0, borderTop: `3px solid ${c.c}` }}>
            <div className="muted" style={{ fontSize: 12 }}>{c.t}</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: c.c, letterSpacing: -0.5 }}>{money(c.v)}</div>
            <div className="muted" style={{ fontSize: 11.5 }}>{c.sub}</div>
          </div>
        ))}
      </div>

      {/* АЛЕРТИ */}
      <div style={{ margin: "12px 0" }}>
        {d.alerts.map((a: any, i: number) => (
          <div key={i} style={{ background: aBg(a.level), color: aColor(a.level), border: `1px solid ${aColor(a.level)}22`, borderRadius: 8, padding: "7px 12px", fontSize: 12.5, fontWeight: 600, marginBottom: 6 }}>
            {a.level === "danger" ? "🔴" : a.level === "warn" ? "🟡" : "🟢"} {a.text}
          </div>
        ))}
      </div>

      {/* РУХ ГРОШЕЙ — grouped bars + лінія сальдо */}
      <div className="panel" style={{ margin: "0 0 12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <b style={{ fontSize: 14 }}>{t("Движение денег","Рух грошей")}</b>
          <span style={{ fontSize: 12.5 }}>🟢 {t("Поступления","Надходження")}: <b style={{ color: "#16a34a" }}>{money(k.income)}</b></span>
          <span style={{ fontSize: 12.5 }}>⬛ {t("Списания","Списання")}: <b style={{ color: "#334155" }}>{money(k.expense)}</b></span>
          <span style={{ fontSize: 12.5 }}>🟠 {t("Сальдо","Сальдо")}: <b style={{ color: k.net >= 0 ? "#16a34a" : "#dc2626" }}>{money(k.net)}</b></span>
          <span className="muted" style={{ fontSize: 11.5 }}>{d.series.granularity === "day" ? t("по дням","по днях") : t("по месяцам","по місяцях")}</span>
        </div>
        <div style={{ position: "relative", marginTop: 12 }}>
          <div style={{ display: "flex", alignItems: "stretch", gap: rows.length > 45 ? 1 : 3, height: CH }}>
            {rows.map((x: any, i: number) => (
              <div key={i} title={`${x.d}\n+${Math.round(x.in).toLocaleString("uk-UA")} / −${Math.round(x.out).toLocaleString("uk-UA")} = ${Math.round(x.net).toLocaleString("uk-UA")}`}
                   style={{ flex: 1, minWidth: 2, height: "100%", display: "flex", alignItems: "flex-end", gap: rows.length > 20 ? 0.5 : 2 }}>
                <div style={{ flex: 1, height: `${Math.max(x.in / smax * 100, x.in > 0 ? 2 : 0)}%`, background: "#22c55e", borderRadius: "3px 3px 0 0" }} />
                <div style={{ flex: 1, height: `${Math.max(x.out / smax * 100, x.out > 0 ? 2 : 0)}%`, background: "#334155", borderRadius: "3px 3px 0 0" }} />
              </div>
            ))}
          </div>
          <svg width="100%" height={CH} style={{ position: "absolute", inset: 0, pointerEvents: "none" }} preserveAspectRatio="none" viewBox={`0 0 ${Math.max(rows.length, 1) * 10} ${CH}`}>
            <line x1="0" y1={CH / 2} x2={rows.length * 10} y2={CH / 2} stroke="#e2e8f0" strokeDasharray="4 4" />
            <polyline fill="none" stroke="#f97316" strokeWidth="2.5" points={rows.map((x: any, i: number) => `${i * 10 + 5},${netY(x.net)}`).join(" ")} />
            {rows.map((x: any, i: number) => <circle key={i} cx={i * 10 + 5} cy={netY(x.net)} r="2.6" fill="#f97316" />)}
          </svg>
        </div>
        <div style={{ display: "flex", gap: rows.length > 45 ? 1 : 3, marginTop: 4 }}>
          {rows.map((x: any, i: number) => (
            <div key={i} className="muted" style={{ flex: 1, fontSize: 8.5, textAlign: "center", overflow: "hidden", whiteSpace: "nowrap" }}>{(rows.length <= 16 || i % Math.ceil(rows.length / 16) === 0) ? slbl(x) : ""}</div>
          ))}
        </div>
      </div>

      {/* ДОНАТИ ПО КАТЕГОРІЯХ */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Donut items={d.by_cat_in || []} title={t("Поступления по категориям","Надходження по категоріях")} total={k.income} />
        <Donut items={d.top_expense || []} title={t("Списания по категориям","Списання по категоріях")} total={k.expense} />
      </div>

      {/* ТРЕНД 12 МІСЯЦІВ: доходи/витрати + лінія прибутку */}
      <div className="panel" style={{ margin: "12px 0" }}>
        <b style={{ fontSize: 14 }}>{t("Тренд 12 месяцев: доходы / расходы / прибыль","Тренд 12 місяців: доходи / витрати / прибуток")}</b>
        <div style={{ position: "relative", marginTop: 12 }}>
          <div style={{ display: "flex", alignItems: "stretch", gap: 6, height: MH }}>
            {months.map((m: any) => (
              <div key={m.ym} title={`${m.ym}\n+${money(m.income)} / −${money(m.expense)}\n${t("прибыль","прибуток")}: ${money(m.net)}`}
                   style={{ flex: 1, height: "100%", display: "flex", alignItems: "flex-end", gap: 2 }}>
                <div style={{ flex: 1, height: `${Math.max(m.income / mmax * 100, m.income > 0 ? 2 : 0)}%`, background: "#22c55e", borderRadius: "3px 3px 0 0" }} />
                <div style={{ flex: 1, height: `${Math.max(m.expense / mmax * 100, m.expense > 0 ? 2 : 0)}%`, background: "#334155", borderRadius: "3px 3px 0 0" }} />
              </div>
            ))}
          </div>
          <svg width="100%" height={MH} style={{ position: "absolute", inset: 0, pointerEvents: "none" }} preserveAspectRatio="none" viewBox={`0 0 ${Math.max(months.length, 1) * 10} ${MH}`}>
            <line x1="0" y1={MH / 2} x2={months.length * 10} y2={MH / 2} stroke="#e2e8f0" strokeDasharray="4 4" />
            <polyline fill="none" stroke="#f97316" strokeWidth="2.5" points={months.map((m: any, i: number) => `${i * 10 + 5},${mNetY(m.net)}`).join(" ")} />
            {months.map((m: any, i: number) => <circle key={i} cx={i * 10 + 5} cy={mNetY(m.net)} r="2.8" fill="#f97316" />)}
          </svg>
        </div>
        <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
          {months.map((m: any) => <div key={m.ym} className="muted" style={{ flex: 1, fontSize: 9.5, textAlign: "center" }}>{m.ym.slice(5)}.{m.ym.slice(2, 4)}</div>)}
        </div>
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>🟩 {t("доходы","доходи")} · ⬛ {t("расходы","витрати")} · 🟠 {t("линия прибыли","лінія прибутку")}</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* ТОП ВИТРАТИ */}
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>{t("Топ расходы периода","Топ витрати періоду")}</b>
          {d.top_expense.length === 0 && <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>{t("Расходов за период нет.","Витрат за період немає.")}</div>}
          {d.top_expense.map((e: any, i: number) => (
            <div key={i} style={{ margin: "8px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}><span>{e.name}</span><b>{money(e.sum)}</b></div>
              <div style={{ height: 7, background: "#f1f5f9", borderRadius: 4, marginTop: 3 }}>
                <div style={{ width: `${e.sum / expMax * 100}%`, height: "100%", background: PAL[i % PAL.length], borderRadius: 4 }} />
              </div>
            </div>
          ))}
        </div>
        {/* НАПРЯМКИ */}
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>{t("Доходы по направлениям","Доходи по напрямках")}</b>
          {(!d.directions || d.directions.length === 0) ? <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>{t("Нет данных по направлениям за период.","Немає даних по напрямках за період.")}</div> : (
            <table style={{ width: "100%", fontSize: 13, marginTop: 8 }}>
              <thead><tr className="muted" style={{ fontSize: 11, textAlign: "left" }}><th>{t("Направление","Напрямок")}</th><th style={{ textAlign: "right" }}>{t("Доход","Дохід")}</th><th style={{ textAlign: "right" }}>{t("Чистый","Чистий")}</th></tr></thead>
              <tbody>{d.directions.map((x: any) => (
                <tr key={x.name} style={{ borderTop: "1px solid #f1f5f9" }}>
                  <td style={{ padding: "6px 0" }}>{x.name}</td>
                  <td style={{ textAlign: "right" }}><b>{money(x.income)}</b></td>
                  <td style={{ textAlign: "right", color: x.net >= 0 ? "#16a34a" : "#dc2626", fontWeight: 700 }}>{money(x.net)}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
        {/* РАХУНКИ */}
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>{t("Балансы счетов","Баланси рахунків")}</b>
          {accShown.map((a: any) => (
            <div key={a.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "5px 0", borderBottom: "1px solid #f8fafc" }}>
              <span>{a.name}</span><b style={{ color: a.balance < 0 ? "#dc2626" : "#1e293b" }}>{money(a.balance)}</b>
            </div>
          ))}
          {d.accounts.length > 8 && <button className="btn btn-light" style={{ marginTop: 8, fontSize: 12 }} onClick={() => setAllAcc(!allAcc)}>{allAcc ? t("Свернуть","Згорнути") : t("Показать все","Показати всі") + ` ${d.accounts.length}`}</button>}
        </div>
        {/* КОЕФІЦІЄНТИ */}
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>{t("Ключевые коэффициенты","Ключові коефіцієнти")}</b>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
            {[[t("Маржинальность","Маржинальність"), `${d.ratios.margin_pct}%`, d.ratios.margin_pct > 20 ? "#16a34a" : "#d97706"],
              [t("Расходы / Доходы","Витрати / Доходи"), `${d.ratios.expense_ratio}%`, d.ratios.expense_ratio <= 100 ? "#16a34a" : "#dc2626"],
              [t("Личные в расходах","Особисті у витратах"), `${d.ratios.personal_pct}%`, d.ratios.personal_pct < 10 ? "#16a34a" : "#dc2626"],
              [t("Запас прочности","Запас міцності"), d.ratios.burn_months ? `${d.ratios.burn_months} ${t("мес","міс")}` : "∞", "#0ea5e9"]].map(([l, v, c]: any) => (
              <div key={l} style={{ background: "#f8fafc", borderRadius: 10, padding: "10px 12px" }}>
                <div className="muted" style={{ fontSize: 11.5 }}>{l}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: c }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

function FxImpact() {
  const { t } = useLang();
  const [ccy, setCcy] = useState("USD");
  const [d, setD] = useState<any>(null);
  useEffect(() => { setD(null); api.get<any>(`/api/finance/fx-impact/?ccy=${ccy}`).then(setD).catch(() => setD(null)); }, [ccy]);
  return (
    <div className="panel" style={{ margin: "12px 0 0", borderLeft: "4px solid #f59e0b" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <b style={{ fontSize: 14, flex: 1 }} title={t("Закупка декор-материалов завязана на курс. Падение гривны уменьшает маржу.","Закупка декор-матеріалів завʼязана на курс. Падіння гривні зменшує маржу.")}><Icon n="💱" size={14} /> {t("Влияние курса валют на прибыль","Вплив курсу валют на прибуток")}</b>
        <select value={ccy} onChange={(e) => setCcy(e.target.value)} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }}>
          {["USD", "EUR", "PLN", "GBP"].map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      {!d ? <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>{t("Загрузка курса НБУ…","Завантаження курсу НБУ…")}</div> : (
        <>
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap", margin: "10px 0", fontSize: 13 }}>
            <span title={t("Текущий курс НБУ","Поточний курс НБУ")}>{t("Курс НБУ","Курс НБУ")}: <b>{d.live_rate ? d.live_rate.toFixed(2) : "—"} ₴/{d.ccy}</b></span>
            <span title={t("Сколько потрачено в этой валюте за период","Скільки витрачено у цій валюті за період")}>{t("Расходы в","Витрати у")} {d.ccy}: <b>{money(d.fx_expense_uah)}</b></span>
            <span title={t("Доля закупки в выручке (импорт-зависимая)","Частка закупки у виручці (імпорт-залежна)")}>{t("Закупка","Закупка")} ≈ <b>{d.supplier_pct}%</b> {t("выручки","виручки")} = {money(d.supplier_cost)}/{t("период","період")}</span>
          </div>
          <div className="muted" style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{t("Что будет с прибылью, если курс изменится (закупка дорожает/дешевеет):","Що буде з прибутком, якщо курс зміниться (закупка дорожчає/дешевшає):")}</div>
          <table style={{ width: "100%", fontSize: 13, marginBottom: 8 }}>
            <thead><tr><th style={{ textAlign: "left", padding: "4px 8px" }}>{t("Изменение курса","Зміна курсу")}</th><th style={{ textAlign: "right" }}>{t("Δ себестоимости","Δ собівартості")}</th><th style={{ textAlign: "right" }}>{t("Δ прибыли","Δ прибутку")}</th><th style={{ textAlign: "right" }}>{t("Новая маржа","Нова маржа")}</th></tr></thead>
            <tbody>
              {d.scenarios.map((sc: any) => (
                <tr key={sc.delta_pct} style={{ borderTop: "1px solid #f1f5f9", background: sc.delta_pct > 0 ? "#fff7ed" : "#f0fdf4" }}>
                  <td style={{ padding: "4px 8px", fontWeight: 600 }}>{sc.delta_pct > 0 ? "+" : ""}{sc.delta_pct}% {sc.delta_pct > 0 ? t("↑ гривна слабеет","↑ гривня слабшає") : t("↓ гривна крепнет","↓ гривня міцніє")}</td>
                  <td style={{ textAlign: "right" }}>{sc.delta_pct > 0 ? "+" : ""}{money(sc.extra_cost)}</td>
                  <td style={{ textAlign: "right", fontWeight: 700, color: sc.profit_change >= 0 ? "#16a34a" : "#dc2626" }}>{sc.profit_change > 0 ? "+" : ""}{money(sc.profit_change)}</td>
                  <td style={{ textAlign: "right" }}>{sc.new_margin_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "8px 12px" }}>
            <div style={{ fontWeight: 600, fontSize: 12.5, color: "#b45309", marginBottom: 4 }}><Icon n="💡" size={13} /> {t("Рекомендации аналитика — чтобы не терять на курсе:","Рекомендації аналітика — щоб не втрачати на курсі:")}</div>
            <ul style={{ margin: "0 0 0 16px", fontSize: 12.5, lineHeight: 1.5 }}>
              {d.recommendations.map((r: string, i: number) => <li key={i}>{r}</li>)}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

/* ─── ВКЛАДКА: P&L (ATM, 5 уровней) ────────────────────────────────────── */
function PnL() {
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(today());
  const [d, setD] = useState<any>(null);
  const { t: tr } = useLang();
  const load = (f: string, t: string) => { setFrom(f); setTo(t); api.get<any>(`/api/finance/pnl/?from=${f}&to=${t}`).then(setD); };
  useEffect(() => { load(from, to); }, []);
  if (!d) return <div className="spin">{tr("Загрузка…","Завантаження…")}</div>;
  const rows: [string, number, string, string][] = [
    [tr("Выручка","Виручка"), d.revenue, "#0f172a", d.deals + tr(" сделок"," угод")],
    [tr("− Прямые расходы","− Прямі витрати"), -d.direct, "#ef4444", d.direct_pct + tr("% с выручки + AI ","% з виручки + AI ") + money(d.ai_total)],
    [tr("= Маржа","= Маржа"), d.margin, "#16a34a", d.margin_pct + "%"],
    [tr("− Операционные (постоянные + переменные)","− Операційні (постійні + змінні)"), -d.operating, "#ef4444", tr("за период","за період")],
    [tr("= Чистая прибыль","= Чистий прибуток"), d.net, d.net >= 0 ? "#16a34a" : "#dc2626", d.net_pct + "%"],
  ];
  return (
    <>
      <Period from={from} to={to} set={load} />
      <div className="panel" style={{ margin: 0, maxWidth: 620 }}>
        <b style={{ fontSize: 14 }}>{tr("P&L по методологии ATM","P&L по методології ATM")} · {d.deals} {tr("сделок","угод")}</b>
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
  const { t: tr } = useLang();
  const load = (f: string, t: string) => { setFrom(f); setTo(t); api.get<any>(`/api/finance/breakeven/?from=${f}&to=${t}`).then(setD); };
  useEffect(() => { load(from, to); }, []);
  if (!d) return <div className="spin">{tr("Загрузка…","Завантаження…")}</div>;
  const prog = Math.min(100, d.progress);
  const cards: [string, string][] = [
    [tr("Сумма фондов выручки","Сума фондів виручки"), d.rev_funds_pct + " %"], [tr("Маржа с каждой ₴","Маржа з кожної ₴"), d.margin_pct + " %"],
    [tr("Точка безубыточности","Точка беззбитковості"), money(d.breakeven)], [tr("Выручка (факт)","Виручка (факт)"), money(d.revenue)], [tr("Расходы / мес","Витрати / міс"), money(d.monthly_costs)],
  ];
  return (
    <>
      <Period from={from} to={to} set={load} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: 12, marginBottom: 14 }}>
        {cards.map(([t, v]) => <div key={t} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{t}</div><div style={{ fontSize: 20, fontWeight: 700 }}>{v}</div></div>)}
      </div>
      <div className="panel" style={{ margin: 0, marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
          <b style={{ fontSize: 14 }}>{tr("Прогресс до точки безубыточности","Прогрес до точки беззбитковості")}</b>
          <b style={{ color: prog >= 100 ? "#16a34a" : "#d97706" }}>{d.progress}%</b>
        </div>
        <div style={{ height: 26, background: "#f1f5f9", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ width: `${prog}%`, height: "100%", background: prog >= 100 ? "#16a34a" : "linear-gradient(90deg,#f59e0b,#facc15)", borderRadius: 8, transition: "width .3s" }} />
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          {prog >= 100 ? tr("✅ Точка безубыточности пройдена — дальше чистая прибыль.","✅ Точку беззбитковості пройдено — далі чистий прибуток.") : tr("Осталось","Залишилось") + ` ${money(d.to_breakeven)} ` + tr("до безубыточности.","до беззбитковості.")}
        </div>
      </div>
      <div className="panel" style={{ margin: 0, maxWidth: 560 }}>
        <b style={{ fontSize: 14 }}><Icon n="🔮" size={14} /> {tr("Прогноз по текущему темпу","Прогноз за поточним темпом")}</b>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">{tr("Темп выручки (прошло","Темп виручки (минуло")} {d.days_elapsed} {tr("из","з")} {d.days_total} {tr("дн)","дн)")}</span><b>{money(d.daily_pace)} / {tr("день","день")}</b></div>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">{tr("Прогноз на конец периода","Прогноз на кінець періоду")}</span><b>{money(d.projected)}</b></div>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">{tr("Прогресс-прогноз","Прогрес-прогноз")}</span><b style={{ color: d.projected_progress >= 100 ? "#16a34a" : "#d97706" }}>{d.projected_progress}%</b></div>
        <div className="row" style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}><span className="muted">{tr("Нужно делать / день до ТБ","Треба робити / день до ТБ")}</span><b style={{ color: "#d97706" }}>{money(d.required_daily)}</b></div>
        <div className="row" style={{ padding: "7px 0" }}><span className="muted">{tr("Дней осталось","Днів залишилось")}</span><b>{d.days_left}</b></div>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА: НАПРЯМКИ (проекти Finmap) + drill-down журналу ───────────── */
function Directions() {
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(today());
  const [d, setD] = useState<any>(null);
  const { t } = useLang();
  const [openId, setOpenId] = useState<number | null>(null);
  const [edit, setEdit] = useState<any>(null); // напрямок для додавання/редагування або null
  const reload = () => { setD(null); api.get<any>(`/api/finance/directions/?from=${from}&to=${to}`).then(setD); };
  useEffect(() => { reload(); }, [from, to]);
  async function delDir(id: number, name: string) {
    if (!confirm(t("Удалить направление","Видалити напрямок") + ` «${name}»? ` + t("Операции останутся, но потеряют привязку к направлению.","Операції залишаться, але втратять привʼязку до напрямку."))) return;
    await api.del(`/api/fin-directions/${id}/`); reload();
  }
  if (!d) return <div className="spin">{t("Загрузка…","Завантаження…")}</div>;
  const tot = d.total;
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <b style={{ fontSize: 14, flex: 1 }}>{t("Направления бизнеса · доходы / расходы / прибыль (план из Finmap, факт из CRM)","Напрямки бізнесу · доходи / витрати / прибуток (план із Finmap, факт із CRM)")}</b>
        <button className="btn btn-primary" style={{ fontSize: 13 }} title={t("Добавить новое направление (проект). Появится в журнале, планировании и аналитике.","Додати новий напрямок (проект). Зʼявиться у журналі, плануванні й аналітиці.")} onClick={() => setEdit({ name: "", plan_income: 0, plan_expense: 0 })}>+ {t("Направление","Напрямок")}</button>
      </div>
      <Period from={from} to={to} set={(f, tt) => { setFrom(f); setTo(tt); }} />
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}><Icon n="👆" size={13} /> {t("Нажми на направление — ниже откроется его журнал операций за период.","Натисни на напрямок — нижче відкриється його журнал операцій за період.")}</div>
      <table style={{ width: "100%", marginTop: 4, fontSize: 13 }}>
        <thead><tr><th></th><th>{t("Направление","Напрямок")}</th><th>{t("План доход","План дохід")}</th><th>{t("План расходы","План витрати")}</th><th>{t("План прибыль","План прибуток")}</th><th>{t("Рентаб.","Рентаб.")}</th><th>{t("Факт доход","Факт дохід")}</th><th>{t("Факт прибыль","Факт прибуток")}</th><th></th></tr></thead>
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
                    <span title={t("Редактировать направление","Редагувати напрямок")} style={{ cursor: "pointer", marginRight: 10 }} onClick={() => setEdit({ id: r.id, name: r.name, plan_income: r.plan_income, plan_expense: r.plan_expense })}><Icon n="✏️" size={14} /></span>
                    <span title={t("Удалить направление","Видалити напрямок")} style={{ cursor: "pointer", color: "#ef4444" }} onClick={() => delDir(r.id, r.name)}>✕</span>
                  </td>
                </tr>
                {isOpen && (
                  <tr><td colSpan={9} style={{ padding: 0, background: "#f8fafc" }}><DirectionJournal directionId={r.id} from={from} to={to} /></td></tr>
                )}
              </Fragment>
            );
          })}
          <tr style={{ borderTop: "2px solid #e2e8f0", fontWeight: 700 }}>
            <td></td><td>{t("ВСЕГО","РАЗОМ")}</td>
            <td style={{ textAlign: "right" }}>{money(tot.plan_income)}</td>
            <td style={{ textAlign: "right" }}>{money(tot.plan_expense)}</td>
            <td style={{ textAlign: "right", color: (tot.plan_income - tot.plan_expense) >= 0 ? "#16a34a" : "#dc2626" }}>{money(tot.plan_income - tot.plan_expense)}</td>
            <td></td>
            <td style={{ textAlign: "right" }} className="muted">{money(tot.income)}</td>
            <td style={{ textAlign: "right" }}>{money(tot.profit)}</td>
            <td></td>
          </tr>
        </tbody>
      </table>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}><Icon n="📋" size={13} /> {t("Направления перенесены из Finmap (Проекты). «План» — ориентир из Finmap. «Факт» считается из транзакций CRM, привязанных к направлению. Изменения тут синхронизируются в журнале, планировании и аналитике.","Напрямки перенесені з Finmap (Проекти). «План» — орієнтир із Finmap. «Факт» рахується з транзакцій CRM, привʼязаних до напрямку. Зміни тут синхронізуються у журналі, плануванні та аналітиці.")}</div>
      {edit && <DirModal dir={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </div>
  );
}

function DirModal({ dir, onClose, onSaved }: { dir: any; onClose: () => void; onSaved: () => void }) {
  const { t } = useLang();
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
        <h3 style={{ marginTop: 0 }}>{dir.id ? t("Редактировать направление","Редагувати напрямок") : t("Новое направление","Новий напрямок")}</h3>
        <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Направление (проект) — откуда деньги: ДЕКОР товары, Объекты, Алмазное сверление, Рекуператоры, Личное и т.д.","Напрямок (проект) — звідки гроші: ДЕКОР товари, Обʼєкти, Алмазне свердління, Рекуператори, Особисте тощо.")}</div>
        <label className="label">{t("Название направления","Назва напрямку")}</label>
        <input value={name} autoFocus onChange={(e) => setName(e.target.value)} placeholder={t("Напр. ДЕКОР товары","Напр. ДЕКОР товари")} style={inp} />
        <label className="label">{t("План дохода (₴/мес)","План доходу (₴/міс)")}</label>
        <input type="number" value={inc} onChange={(e) => setInc(e.target.value)} style={inp} />
        <label className="label">{t("План расходов (₴/мес)","План витрат (₴/міс)")}</label>
        <input type="number" value={exp} onChange={(e) => setExp(e.target.value)} style={inp} />
        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>{t("Отмена","Скасувати")}</button>
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={save} disabled={busy || !name.trim()}>{busy ? "…" : t("Сохранить","Зберегти")}</button>
        </div>
      </div>
    </div>
  );
}

function DirectionJournal({ directionId, from, to }: { directionId: number; from: string; to: string }) {
  const { t } = useLang();
  const [tx, setTx] = useState<any[] | null>(null);
  useEffect(() => { setTx(null); api.get<any>(`/api/transactions/?fin_direction=${directionId}&from=${from}&to=${to}&page_size=200`).then((d) => setTx(d.results || d)); }, [directionId, from, to]);
  if (!tx) return <div className="spin" style={{ padding: 12 }}>{t("Журнал…","Журнал…")}</div>;
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
        <span style={{ color: "#16a34a", fontWeight: 600 }}>{t("Доход","Дохід")}: {money(inc)}</span>
        <span style={{ color: "#dc2626", fontWeight: 600 }}>{t("Расходы","Витрати")}: {money(exp)}</span>
        <span style={{ fontWeight: 700 }}>{t("Прибыль","Прибуток")}: {money(inc - exp)}</span>
        <span className="muted" style={{ marginLeft: "auto" }}>{t("Операций","Операцій")}: {tx.length}</span>
      </div>
      {chans.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div className="muted" style={{ fontSize: 11.5, fontWeight: 600, marginBottom: 4 }}><Icon n="🌿" size={13} /> {t("Каналы (ветки) направления · продаж × сумма:","Канали (ветки) напрямку · продажів × сума:")}</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {chans.map(([k, v]) => (
              <span key={k} style={{ fontSize: 12, padding: "4px 10px", borderRadius: 14, background: "#eef2ff", color: "#4338ca", fontWeight: 600 }}>
                {chLabel(k)} · {v.count} {t("продаж","продаж")}{v.count === 1 ? "" : v.count < 5 ? t("и","і") : t("ей","ів")} · {money(v.sum)}
              </span>
            ))}
          </div>
        </div>
      )}
      {tx.length === 0 ? (
        <div className="muted" style={{ fontSize: 13 }}>{t("Нет операций по этому направлению за период. Добавь транзакцию во вкладке «Журнал» и выбери это направление.","Немає операцій по цьому напрямку за період. Додай транзакцію у вкладці «Журнал» і обери цей напрямок.")}</div>
      ) : (
        <table style={{ width: "100%", fontSize: 12.5 }}>
          <thead><tr><th style={{ textAlign: "left", padding: "4px 8px" }}>{t("Дата","Дата")}</th><th>{t("Сумма","Сума")}</th><th>{t("Фонд","Фонд")}</th><th>{t("Канал","Канал")}</th><th style={{ textAlign: "left" }}>{t("Комментарий","Коментар")}</th></tr></thead>
          <tbody>
            {tx.map((r) => (
              <tr key={r.id} style={{ borderTop: "1px solid #eef2f7" }}>
                <td className="muted" style={{ padding: "4px 8px" }}>{new Date(r.date || r.created_at).toLocaleDateString("ru")}</td>
                <td style={{ textAlign: "right", fontWeight: 600, color: r.direction === "in" ? "#16a34a" : "#dc2626" }}>{r.direction === "in" ? "+" : "−"}{Number(r.amount).toLocaleString("ru")} ₴</td>
                <td>{r.fin_article_name || <span className="muted">—</span>}</td>
                <td className="muted" style={{ textAlign: "center" }}>{(CHANNELS.find((c) => c[0] === r.channel) || ["", "—"])[1]}</td>
                <td className="muted" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.comment}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ─── ВКЛАДКА: ТАБЕЛЬ РОБОЧОГО ЧАСУ (як Бітрикс timeman) ────────────────── */
const WD_STATUS: Record<string, { label: string; short: string; color: string }> = {
  worked: { label: "Робочий день", short: "Р", color: "#16a34a" },
  overtime: { label: "Перевиконання (вихід у вихідний)", short: "+", color: "#7c3aed" },
  dayoff: { label: "Вихідний", short: "В", color: "#cbd5e1" },
  sick: { label: "Лікарняний", short: "Л", color: "#f59e0b" },
  vacation: { label: "Відпустка", short: "Від", color: "#0ea5e9" },
  absent: { label: "Прогул", short: "✕", color: "#ef4444" },
};
const WD_CYCLE = ["worked", "overtime", "dayoff", "sick", "vacation", "absent", ""];

function Timesheet() {
  const { t } = useLang();
  const now = new Date();
  const [users, setUsers] = useState<any[]>([]);
  const [uid, setUid] = useState<number | null>(null);
  const [ym, setYm] = useState(`${now.getFullYear()}-${pad(now.getMonth() + 1)}`);
  const [days, setDays] = useState<Record<string, string>>({});
  useEffect(() => { api.get<any>("/api/users/").then((d) => { const us = d.results || d; setUsers(us); if (us[0]) setUid(us[0].id); }); }, []);
  const [y, mo] = ym.split("-").map(Number);
  const load = () => { if (!uid) return; api.get<any>(`/api/workdays/?user=${uid}&year=${y}&month=${mo}&page_size=40`).then((d) => { const r = d.results || d; const map: any = {}; r.forEach((w: any) => { map[w.date] = w.status; }); setDays(map); }); };
  useEffect(() => { load(); }, [uid, ym]);
  const daysInMonth = new Date(y, mo, 0).getDate();
  async function cycle(dateStr: string) {
    const cur = days[dateStr] || "";
    const next = WD_CYCLE[(WD_CYCLE.indexOf(cur) + 1) % WD_CYCLE.length];
    setDays((d) => ({ ...d, [dateStr]: next }));
    await api.post("/api/workdays/set/", { user: uid, date: dateStr, status: next || "clear" });
  }
  const worked = Object.values(days).filter((s) => s === "worked" || s === "overtime").length;
  const overtime = Object.values(days).filter((s) => s === "overtime").length;
  return (
    <>
      <div className="note"><Icon n="🕐" size={14} /> <b>{t("Табель рабочего времени","Табель робочого часу")}</b> {t("(как в Битриксе). Клик на день меняет статус по кругу. Влияет на ЗП: оклад платится пропорционально отработанным дням, а","(як у Бітриксі). Клік на день міняє статус по колу. Впливає на ЗП: оклад платиться пропорційно відпрацьованим дням, а")} <b>{t("перевыполнение","перевиконання")}</b> {t("(выход в выходной) добавляет дневную ставку сверху. Если табель не вести — оклад полный по умолчанию.","(вихід у вихідний) додає денну ставку зверху. Якщо табель не вести — оклад повний за замовчуванням.")}</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <select value={uid ?? ""} onChange={(e) => setUid(Number(e.target.value))} style={{ height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }}>
          {users.map((u) => <option key={u.id} value={u.id}>{u.full_name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username}</option>)}
        </select>
        <input type="month" value={ym} onChange={(e) => setYm(e.target.value)} style={{ height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }} />
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 13 }}>{t("Отработано","Відпрацьовано")}: <b style={{ color: "#16a34a" }}>{worked}</b> · {t("Перевыполнений","Перевиконань")}: <b style={{ color: "#7c3aed" }}>{overtime}</b></span>
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 6 }}>
          {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"].map((w) => <div key={w} className="muted" style={{ fontSize: 11, textAlign: "center", fontWeight: 600 }}>{w}</div>)}
          {(() => {
            const first = new Date(y, mo - 1, 1).getDay(); // 0=Sun
            const offset = (first + 6) % 7; // Monday-first
            const cells: any[] = [];
            for (let i = 0; i < offset; i++) cells.push(<div key={"e" + i} />);
            for (let d = 1; d <= daysInMonth; d++) {
              const ds = `${y}-${pad(mo)}-${pad(d)}`;
              const st = days[ds] || "";
              const meta = WD_STATUS[st];
              cells.push(
                <div key={d} onClick={() => cycle(ds)} title={meta ? meta.label : t("Не отмечено — клик чтобы поставить","Не відмічено — клік щоб поставити")}
                  style={{ cursor: "pointer", borderRadius: 8, padding: "8px 4px", textAlign: "center", minHeight: 44, border: "1px solid #e2e8f0", background: meta ? meta.color + "22" : "#fff" }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{d}</div>
                  {meta && <div style={{ fontSize: 11, fontWeight: 700, color: meta.color }}>{meta.short}</div>}
                </div>
              );
            }
            return cells;
          })()}
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          {Object.entries(WD_STATUS).map(([k, v]) => <span key={k} style={{ fontSize: 12 }}><span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 3, background: v.color, marginRight: 4, verticalAlign: "middle" }} />{v.label}</span>)}
        </div>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА: ДОВІДНИКИ (рахунки/категорії/напрямки/контрагенти/канали/валюти) ─ */
function Reference() {
  const { t } = useLang();
  const [sub, setSub] = useState<"acc" | "cat" | "dir" | "cp" | "chan" | "ccy">("acc");
  const subs: [string, React.ReactNode][] = [["acc", <><Icon n="🏦" size={14} /> {t("Счета","Рахунки")}</>], ["cat", <><Icon n="🏷" size={14} /> {t("Категории","Категорії")}</>], ["dir", <><Icon n="🗂" size={14} /> {t("Направления","Напрямки")}</>], ["cp", <><Icon n="👥" size={14} /> {t("Контрагенты","Контрагенти")}</>], ["chan", <><Icon n="📡" size={14} /> {t("Каналы","Канали")}</>], ["ccy", <><Icon n="💱" size={14} /> {t("Валюты","Валюти")}</>]];
  return (
    <>
      <div className="note"><Icon n="📚" size={14} /> {t("Справочники CRM. Всё синхронно: изменения тут сразу доступны в Журнале, Планировании и Аналитике. Контрагенты подтягиваются из операций и связаны с клиентами CRM.","Довідники CRM. Усе синхронно: зміни тут одразу доступні в Журналі, Плануванні й Аналітиці. Контрагенти підтягуються з операцій і звʼязані з клієнтами CRM.")}</div>
      <div style={{ display: "flex", gap: 6, margin: "10px 0", flexWrap: "wrap" }}>
        {subs.map(([k, l]) => <button key={k} className={sub === k ? "btn btn-primary" : "btn btn-light"} style={{ fontSize: 12.5 }} onClick={() => setSub(k as any)}>{l}</button>)}
      </div>
      {sub === "acc" && <RefAccounts />}
      {sub === "cat" && <RefCategories />}
      {sub === "dir" && <RefDirections />}
      {sub === "cp" && <RefCounterparties />}
      {sub === "chan" && <RefConst title={t("Каналы продажи/источники","Канали продажу/джерела")} items={CHANNELS.filter((c) => c[0]).map((c) => c[1])} hint={t("Каналы зашиты в системе — выбираются в карточке операции и считаются в аналитике по каналам.","Канали зашиті в системі — обираються у картці операції та рахуються в аналітиці по каналах.")} />}
      {sub === "ccy" && <RefConst title={t("Валюты","Валюти")} items={[t("UAH — гривна","UAH — гривня"), t("USD — доллар","USD — долар"), t("EUR — евро","EUR — євро"), t("PLN — злотый","PLN — злотий"), t("GBP — фунт","GBP — фунт")]} hint={t("Курс подтягивается из НБУ автоматически при выборе валюты в операции.","Курс підтягується з НБУ автоматично при виборі валюти в операції.")} />}
    </>
  );
}

const tdS = { padding: "7px 10px", borderBottom: "1px solid #f1f5f9" } as React.CSSProperties;
const inpS = { height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" } as React.CSSProperties;

function RefAccounts() {
  const [items, setItems] = useState<any[]>([]);
  const { t } = useLang();
  const [nn, setNn] = useState(""); const [nk, setNk] = useState("bank"); const [err, setErr] = useState("");
  const load = () => api.get<any>("/api/accounts/").then((d) => setItems(d.results || d));
  useEffect(() => { load(); }, []);
  async function add() { if (!nn.trim()) return; await api.post("/api/accounts/", { name: nn.trim(), kind: nk, is_active: true }); setNn(""); load(); }
  async function save(a: any, p: any) { await api.patch(`/api/accounts/${a.id}/`, p); load(); }
  async function del(a: any) { setErr(""); try { await api.del(`/api/accounts/${a.id}/`); load(); } catch { setErr(`«${a.name}» ` + t("имеет операции — удаление заблокировано. Сделай неактивным.","має операції — видалення заблоковано. Зроби неактивним.")); } }
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <input value={nn} onChange={(e) => setNn(e.target.value)} placeholder={t("Новый счёт / касса","Новий рахунок / каса")} style={{ ...inpS, flex: 1 }} />
        <select value={nk} onChange={(e) => setNk(e.target.value)} style={inpS}><option value="bank">{t("Банк","Банк")}</option><option value="cash">{t("Наличные","Готівка")}</option><option value="acquiring">{t("Эквайринг","Еквайринг")}</option></select>
        <button className="btn btn-primary" onClick={add}>+ {t("Добавить","Додати")}</button>
      </div>
      {err && <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>{err}</div>}
      <table style={{ width: "100%", fontSize: 13 }}>
        <thead><tr><th style={{ textAlign: "left", ...tdS }}>{t("Название","Назва")}</th><th>{t("Тип","Тип")}</th><th>{t("Баланс","Баланс")}</th><th>{t("Активный","Активний")}</th><th></th></tr></thead>
        <tbody>{items.map((a) => (
          <tr key={a.id}>
            <td style={tdS}><input defaultValue={a.name} onBlur={(e) => e.target.value !== a.name && save(a, { name: e.target.value })} style={{ ...inpS, width: "100%", border: "1px solid transparent" }} /></td>
            <td style={{ ...tdS, textAlign: "center" }}>{a.kind}</td>
            <td style={{ ...tdS, textAlign: "right", fontWeight: 600 }}>{money(a.balance)}</td>
            <td style={{ ...tdS, textAlign: "center" }}><input type="checkbox" checked={a.is_active} onChange={(e) => save(a, { is_active: e.target.checked })} /></td>
            <td style={{ ...tdS, textAlign: "center" }}><span style={{ color: "#ef4444", cursor: "pointer" }} onClick={() => del(a)}>✕</span></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function RefCategories() {
  const [items, setItems] = useState<any[]>([]);
  const { t } = useLang();
  const [nn, setNn] = useState(""); const [nd, setNd] = useState("out");
  const load = () => api.get<any>("/api/categories/?page_size=200").then((d) => setItems(d.results || d));
  useEffect(() => { load(); }, []);
  async function add() { if (!nn.trim()) return; await api.post("/api/categories/", { name: nn.trim(), direction: nd }); setNn(""); load(); }
  async function del(id: number) { await api.del(`/api/categories/${id}/`); load(); }
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <input value={nn} onChange={(e) => setNn(e.target.value)} placeholder={t("Новая категория","Нова категорія")} style={{ ...inpS, flex: 1 }} />
        <select value={nd} onChange={(e) => setNd(e.target.value)} style={inpS}><option value="in">{t("Доход","Дохід")}</option><option value="out">{t("Расход","Витрата")}</option></select>
        <button className="btn btn-primary" onClick={add}>+ {t("Добавить","Додати")}</button>
      </div>
      <table style={{ width: "100%", fontSize: 13 }}>
        <thead><tr><th style={{ textAlign: "left", ...tdS }}>{t("Название","Назва")}</th><th>{t("Тип","Тип")}</th><th></th></tr></thead>
        <tbody>{items.map((c) => (
          <tr key={c.id}><td style={tdS}>{c.name}</td><td style={{ ...tdS, textAlign: "center" }}>{c.direction === "in" ? t("Доход","Дохід") : t("Расход","Витрата")}</td>
            <td style={{ ...tdS, textAlign: "center" }}><span style={{ color: "#ef4444", cursor: "pointer" }} onClick={() => del(c.id)}>✕</span></td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function RefDirections() {
  const { t } = useLang();
  const [items, setItems] = useState<any[]>([]);
  const [nn, setNn] = useState("");
  const load = () => api.get<any>("/api/fin-directions/?page_size=100").then((d) => setItems(d.results || d));
  useEffect(() => { load(); }, []);
  async function add() { if (!nn.trim()) return; await api.post("/api/fin-directions/", { name: nn.trim(), active: true }); setNn(""); load(); }
  async function save(d: any, p: any) { await api.patch(`/api/fin-directions/${d.id}/`, p); load(); }
  async function del(id: number) { if (!confirm(t("Удалить направление? Операции останутся, но потеряют привязку.","Видалити напрямок? Операції лишаться, але втратять привʼязку."))) return; await api.del(`/api/fin-directions/${id}/`); load(); }
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <input value={nn} onChange={(e) => setNn(e.target.value)} placeholder={t("Новое направление (проект)","Новий напрямок (проект)")} style={{ ...inpS, flex: 1 }} />
        <button className="btn btn-primary" onClick={add}>+ {t("Добавить","Додати")}</button>
      </div>
      <table style={{ width: "100%", fontSize: 13 }}>
        <thead><tr><th style={{ textAlign: "left", ...tdS }}>{t("Направление","Напрямок")}</th><th>{t("План доход","План дохід")}</th><th>{t("План расходы","План витрати")}</th><th></th></tr></thead>
        <tbody>{items.map((d) => (
          <tr key={d.id}>
            <td style={tdS}><input defaultValue={d.name} onBlur={(e) => e.target.value !== d.name && save(d, { name: e.target.value })} style={{ ...inpS, width: "100%", border: "1px solid transparent" }} /></td>
            <td style={{ ...tdS, textAlign: "right" }}><input type="number" defaultValue={d.plan_income} onBlur={(e) => save(d, { plan_income: Number(e.target.value) })} style={{ ...inpS, width: 110, textAlign: "right" }} /></td>
            <td style={{ ...tdS, textAlign: "right" }}><input type="number" defaultValue={d.plan_expense} onBlur={(e) => save(d, { plan_expense: Number(e.target.value) })} style={{ ...inpS, width: 110, textAlign: "right" }} /></td>
            <td style={{ ...tdS, textAlign: "center" }}><span style={{ color: "#ef4444", cursor: "pointer" }} onClick={() => del(d.id)}>✕</span></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function RefCounterparties() {
  const { t } = useLang();
  const [items, setItems] = useState<any[]>([]);
  const nav = useNav();
  useEffect(() => { api.get<any>("/api/finance/counterparties/").then(setItems).catch(() => setItems([])); }, []);
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("Контрагенты сведены из операций. 🔗 = связан с клиентом CRM (клик откроет).","Контрагенти зведені з операцій. 🔗 = звʼязаний із клієнтом CRM (клік відкриє).")}</div>
      <table style={{ width: "100%", fontSize: 13 }}>
        <thead><tr><th style={{ textAlign: "left", ...tdS }}>{t("Контрагент","Контрагент")}</th><th>{t("Операций","Операцій")}</th><th>{t("Сумма","Сума")}</th><th>{t("Клиент CRM","Клієнт CRM")}</th></tr></thead>
        <tbody>{items.slice(0, 300).map((c, i) => (
          <tr key={i}><td style={tdS}>{c.name}</td><td style={{ ...tdS, textAlign: "center" }}>{c.count}</td>
            <td style={{ ...tdS, textAlign: "right" }}>{money(c.total)}</td>
            <td style={{ ...tdS, textAlign: "center" }}>{c.contact_id ? <span style={{ color: "#1d4ed8", cursor: "pointer" }} onClick={() => nav(`/clients?contact=${c.contact_id}`)}><Icon n="🔗" size={13} /> {t("открыть","відкрити")}</span> : <span className="muted">—</span>}</td></tr>
        ))}</tbody>
      </table>
      {items.length > 300 && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{t("Показано первые 300 из","Показано перші 300 із")} {items.length}.</div>}
    </div>
  );
}

function RefConst({ title, items, hint }: { title: string; items: string[]; hint: string }) {
  const { t } = useLang();
  return (
    <div className="panel" style={{ margin: 0 }}>
      <b style={{ fontSize: 14 }}>{title}</b>
      <div className="muted" style={{ fontSize: 12, margin: "4px 0 10px" }}>{hint}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>{items.map((x) => <span key={x} style={{ background: "#f1f5f9", borderRadius: 14, padding: "5px 12px", fontSize: 13 }}>{x}</span>)}</div>
    </div>
  );
}

/* ─── ВКЛАДКА: ФІНМОДЕЛЬ (CRUD статей) ─────────────────────────────────── */
/* ─── ВКЛАДКА: ПЛАНУВАННЯ ПО ФОНДАХ-КОНВЕРТАХ ──────────────────────────── */
function Planning() {
  const [period, setPeriod] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; });
  const { t } = useLang();
  const [data, setData] = useState<any>(null);
  const [dirs, setDirs] = useState<any[]>([]);
  const [alloc, setAlloc] = useState<any>(null); // {fund} модалка ручного розподілу
  const [auto, setAuto] = useState(false);       // модалка авто-розподілу виручки
  const [openAlloc, setOpenAlloc] = useState<number | null>(null); // розгорнутий список розподілів фонду
  const [spend, setSpend] = useState<any>(null); // фонд, з якого робимо розхід
  const load = () => api.get<any>(`/api/finance/funds/?period=${period}`).then(setData);
  useEffect(() => { load(); }, [period]);
  useEffect(() => { api.get<any>("/api/fin-directions/?page_size=100").then((d) => setDirs(d.results || d)); }, []);

  function FundRow({ f, sub }: { f: any; sub?: boolean }) {
    const neg = f.balance < 0;
    const open = openAlloc === f.id;
    return (
      <>
        <div className="row" style={{ padding: "8px 0", borderBottom: "1px solid #f1f5f9", alignItems: "center", paddingLeft: sub ? 24 : 0 }}>
          <span style={{ flex: 1, fontWeight: sub ? 400 : 600 }}>{sub && <span style={{ color: "#cbd5e1", marginRight: 4 }}>↳</span>}{f.is_envelope && <Icon n="✉️" size={13} />}{f.is_envelope ? " " : ""}{f.name}</span>
          <span title={t("Нажми, чтобы увидеть и убрать отдельные распределения","Натисни, щоб побачити та прибрати окремі розподіли")} onClick={() => setOpenAlloc(open ? null : f.id)}
            style={{ width: 110, textAlign: "right", color: "#0ea5e9", cursor: f.allocated ? "pointer" : "default", textDecoration: f.allocated ? "underline dotted" : "none" }}>{f.allocated ? (open ? "▾ " : "▸ ") : ""}{money(f.allocated)}</span>
          <span style={{ width: 110, textAlign: "right", color: "#ef4444" }}>−{money(f.spent)}</span>
          <span style={{ width: 120, textAlign: "right", fontWeight: 700, color: neg ? "#dc2626" : "#059669" }}>{money(f.balance)}</span>
          <button className="btn btn-light" style={{ fontSize: 11, padding: "3px 8px", marginLeft: 8 }} title={t("Положить денег в этот фонд-конверт","Покласти грошей у цей фонд-конверт")} onClick={() => setAlloc(f)}>+ {t("распределение","розподіл")}</button>
          <button className="btn btn-light" style={{ fontSize: 11, padding: "3px 8px", marginLeft: 4, color: "#dc2626" }} title={t("Сделать расход из этого фонда (наполняет «Потрачено»)","Зробити витрату з цього фонду (наповнює «Витрачено»)")} onClick={() => setSpend(f)}>− {t("расход","розхід")}</button>
        </div>
        {open && <AllocList fundId={f.id} period={period} onChanged={load} />}
        {(f.subfunds || []).map((x: any) => <FundRow key={x.id} f={x} sub />)}
      </>
    );
  }

  if (!data) return <div className="spin">{t("Загрузка фондов…","Завантаження фондів…")}</div>;
  return (
    <>
      <div className="note"><Icon n="💼" size={14} /> {t("Деньги приходят на счёт → распределяешь по фондам-конвертам. В каждом фонде:","Гроші приходять на рахунок → розподіляєш по фондах-конвертах. У кожному фонді:")} <b>{t("Распределено","Розподілено")}</b> {t("(сколько положил)","(скільки поклав)")} − <b>{t("Потрачено","Витрачено")}</b> {t("(сколько списал)","(скільки списав)")} = <b>{t("Остаток","Залишок")}</b>. {t("Порядок:","Порядок:")} <b>ФВ → ФМ → ФСКД</b>.<br/><span style={{fontSize:12}}><Icon n="📌" size={13} /> <b>{t("«Потрачено»","«Витрачено»")}</b> {t("наполняется, когда создаёшь расход с этим фондом — кнопкой «","наповнюється, коли створюєш витрату з цим фондом — кнопкою «")}<b>{t("− расход","− розхід")}</b>{t("» тут или в Журнале выбираешь Фонд = этот. Тогда сумма появляется в столбце.","» тут або у Журналі обираєш Фонд = цей. Тоді сума зʼявляється у стовпці.")}</span></div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <span className="muted" style={{ fontSize: 13 }}>{t("Месяц","Місяць")}:</span>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setAuto(true)}><Icon n="⚡" size={14} /> {t("Авто-распределение выручки","Авто-розподіл виручки")}</button>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {data.accounts.map((a: any) => (
          <div key={a.id} className="panel" style={{ flex: "1 1 150px", padding: "10px 12px" }}>
            <div className="muted" style={{ fontSize: 12 }}>{a.name}</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{money(a.balance)}</div>
          </div>
        ))}
        <div className="panel" style={{ flex: "1 1 150px", padding: "10px 12px", background: "#eff6ff" }}>
          <div className="muted" style={{ fontSize: 12 }} title={t("Деньги на счетах, ещё НЕ разложенные по фондам","Гроші на рахунках, ще НЕ розкладені по фондах")}>{t("К распределению","До розподілу")}</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#2563eb" }}>{money(data.accounts.reduce((a: number, x: any) => a + x.balance, 0) - data.totals.balance)}</div>
        </div>
        <div className="panel" style={{ flex: "1 1 150px", padding: "10px 12px", background: "#f0fdf4" }}>
          <div className="muted" style={{ fontSize: 12 }} title={t("Сумма остатков во всех фондах-конвертах","Сума залишків у всіх фондах-конвертах")}>{t("Остаток в фондах","Залишок у фондах")}</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#059669" }}>{money(data.totals.balance)}</div>
        </div>
      </div>

      {data.groups.map((g: any) => (
        <div key={g.key} className="panel" style={{ margin: "10px 0 0", borderLeft: `4px solid ${g.color}` }}>
          <div style={{ display: "flex", alignItems: "center", marginBottom: 4 }}>
            <b style={{ fontSize: 13.5, color: g.color, flex: 1 }}>{g.label}</b>
            <span className="muted" style={{ fontSize: 11, width: 110, textAlign: "right" }}>{t("Распределено","Розподілено")}</span>
            <span className="muted" style={{ fontSize: 11, width: 110, textAlign: "right" }}>{t("Потрачено","Витрачено")}</span>
            <span className="muted" style={{ fontSize: 11, width: 120, textAlign: "right" }}>{t("Остаток","Залишок")}</span>
            <span style={{ width: 90 }} />
          </div>
          {g.funds.map((f: any) => <FundRow key={f.id} f={f} />)}
        </div>
      ))}

      {alloc && <AllocModal fund={alloc} period={period} accounts={data.accounts} dirs={dirs} onClose={() => setAlloc(null)} onSaved={() => { setAlloc(null); load(); }} />}
      {auto && <AutoModal period={period} accounts={data.accounts} dirs={dirs} onClose={() => setAuto(false)} onSaved={() => { setAuto(false); load(); }} />}
      {spend && <SpendModal fund={spend} accounts={data.accounts} dirs={dirs} onClose={() => setSpend(null)} onSaved={() => { setSpend(null); load(); }} />}
    </>
  );
}

function AllocList({ fundId, period, onChanged }: { fundId: number; period: string; onChanged: () => void }) {
  const { t } = useLang();
  const [items, setItems] = useState<any[] | null>(null);
  const reload = () => api.get<any>(`/api/fund-allocations/?fund=${fundId}&period=${period}&page_size=100`).then((d) => setItems(d.results || d));
  useEffect(() => { reload(); }, [fundId, period]);
  async function del(id: number) { await api.del(`/api/fund-allocations/${id}/`); reload(); onChanged(); }
  async function patch(id: number, amount: number) { await api.patch(`/api/fund-allocations/${id}/`, { amount }); reload(); onChanged(); }
  if (!items) return <div className="muted" style={{ padding: "4px 0 8px 24px", fontSize: 12 }}>…</div>;
  if (!items.length) return <div className="muted" style={{ padding: "4px 0 8px 24px", fontSize: 12 }}>{t("Отдельных распределений нет (возможно, пришло авто-распределением раньше).","Окремих розподілів немає (можливо, прийшло авто-розподілом раніше).")}</div>;
  return (
    <div style={{ padding: "2px 0 8px 24px", background: "#f8fafc", borderBottom: "1px solid #f1f5f9" }}>
      <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>{t("Распределения этого фонда · измени сумму или убери ✕ (баланс пересчитается):","Розподіли цього фонду · зміни суму або прибери ✕ (баланс перерахується):")}</div>
      {items.map((a) => (
        <div key={a.id} className="row" style={{ padding: "4px 0", fontSize: 12.5, alignItems: "center" }}>
          <span style={{ flex: 1 }}>{a.comment || t("распределение","розподіл")}{a.account_name ? ` · ${a.account_name}` : ""}{a.fin_direction_name ? ` · ${a.fin_direction_name}` : ""}</span>
          <input type="number" defaultValue={a.amount} title={t("Измени сумму распределения","Зміни суму розподілу")} onBlur={(e) => patch(a.id, Number(e.target.value))} style={{ width: 92, height: 26, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px", textAlign: "right" }} />
          <span style={{ color: "#ef4444", cursor: "pointer", paddingLeft: 12 }} title={t("Убрать это распределение","Прибрати цей розподіл")} onClick={() => del(a.id)}>✕</span>
        </div>
      ))}
    </div>
  );
}

function SpendModal({ fund, accounts, dirs, onClose, onSaved }: any) {
  /* spend-full-card: та сама картка, що й у Журналі (витрата) — синхронно з журналом */
  const { t } = useLang();
  const [amount, setAmount] = useState("");
  const [account, setAccount] = useState(accounts[0]?.id || "");
  const [direction, setDirection] = useState("");
  const [cat, setCat] = useState("");
  const [counterparty, setCounterparty] = useState("");
  const [currency, setCurrency] = useState("UAH");
  const [rate, setRate] = useState(1);
  const [comment, setComment] = useState("");
  const [cats, setCats] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get<any>("/api/categories/").then((d) => setCats(d.results || d)).catch(() => setCats([])); }, []);
  async function fetchRate(c: string) {
    if (c === "UAH") { setCurrency(c); setRate(1); return; }
    setCurrency(c);
    try { const r = await api.get<any>(`/api/finance/fx-rate/?ccy=${c}`); if (r.rate) setRate(r.rate); } catch { /* ok */ }
  }
  async function save() {
    if (!Number(amount)) return;
    setBusy(true);
    try {
      await api.post("/api/transactions/", { direction: "out", amount: Number(amount), account: account || null,
        fin_article: fund.id, fin_direction: direction || null, set_category: cat, counterparty,
        currency, rate: Number(rate) || 1, comment: comment || `Розхід: ${fund.name}` });
      onSaved();
    } finally { setBusy(false); }
  }
  const inp = { width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 } as React.CSSProperties;
  const grnEq = Number(amount || 0) * (Number(rate) || 1);
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, padding: 22, width: 440, maxHeight: "90vh", overflowY: "auto" }}>
        <h3 style={{ marginTop: 0 }}>{t("Расход","Витрата")} · {t("фонд","фонд")} {fund.name}</h3>
        <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}><Icon n="💸" size={13} /> {t("Это обычный расход (как в Журнале), уже привязанный к фонду. Уменьшит остаток фонда, наполнит «Потрачено» и появится в Журнале.","Це звичайна витрата (як у Журналі), уже привʼязана до фонду. Зменшить залишок фонду, наповнить «Витрачено» і зʼявиться в Журналі.")}</div>
        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ flex: 2 }}><label className="label">{t("Сумма","Сума")}</label><input type="number" value={amount} autoFocus onChange={(e) => setAmount(e.target.value)} style={inp} /></div>
          <div style={{ flex: 1 }}><label className="label">{t("Валюта","Валюта")}</label><select value={currency} onChange={(e) => fetchRate(e.target.value)} style={inp}>{["UAH", "USD", "EUR", "PLN"].map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        </div>
        {currency !== "UAH" && <div style={{ fontSize: 13, marginBottom: 10 }}><span className="muted">{t("Курс НБУ","Курс НБУ")}:</span> <input type="number" value={rate} onChange={(e) => setRate(Number(e.target.value))} style={{ width: 90, height: 30, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }} /> <b style={{ color: "#0ea5e9" }}>= {money(grnEq)}</b></div>}
        <label className="label">{t("Категория","Категорія")}</label>
        <input value={cat} onChange={(e) => setCat(e.target.value)} list="spendcat" placeholder={t("Напр. Закупка, Аренда, Реклама…","Напр. Закупка, Оренда, Реклама…")} style={inp} />
        <datalist id="spendcat">{cats.map((c) => <option key={c.id} value={c.name} />)}</datalist>
        <label className="label">{t("Мой контрагент","Мій контрагент")}</label>
        <CpField value={counterparty} onChange={setCounterparty} />
        <label className="label">{t("Со счёта","З рахунку")}</label>
        <select value={account} onChange={(e) => setAccount(e.target.value)} style={inp}>
          <option value="">—</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <label className="label">{t("Направление (необяз.)","Напрямок (необов.)")}</label>
        <select value={direction} onChange={(e) => setDirection(e.target.value)} style={inp}>
          <option value="">{t("— все —","— усі —")}</option>{dirs.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <label className="label">{t("Комментарий","Коментар")}</label>
        <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t("За что расход","За що витрата")} style={inp} />
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>{t("Отмена","Скасувати")}</button>
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={save} disabled={busy}>{busy ? "…" : t("Провести расход","Провести витрату")}</button>
        </div>
      </div>
    </div>
  );
}

function AllocModal({ fund, period, accounts, dirs, onClose, onSaved }: any) {
  const { t } = useLang();
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
        <h3 style={{ marginTop: 0 }}>{t("Распределение в фонд","Розподіл у фонд")}</h3>
        <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}><Icon n="✉️" size={13} /> {fund.name} · {period}</div>
        <label className="label">{t("Сумма, ₴","Сума, ₴")}</label>
        <input type="number" value={amount} autoFocus onChange={(e) => setAmount(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 }} />
        <label className="label">{t("Со счёта","З рахунку")}</label>
        <select value={account} onChange={(e) => setAccount(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, marginBottom: 10 }}>
          <option value="">—</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <label className="label">{t("Направление (необяз.)","Напрямок (необов.)")}</label>
        <select value={direction} onChange={(e) => setDirection(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, marginBottom: 10 }}>
          <option value="">{t("— все —","— усі —")}</option>{dirs.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <label className="label">{t("Комментарий","Коментар")}</label>
        <input value={comment} onChange={(e) => setComment(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 14 }} />
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>{t("Отмена","Скасувати")}</button>
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={save} disabled={busy}>{busy ? "…" : t("Распределить","Розподілити")}</button>
        </div>
      </div>
    </div>
  );
}

function AutoModal({ period, accounts, dirs, onClose, onSaved }: any) {
  const { t } = useLang();
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
        <h3 style={{ marginTop: 0 }}><Icon n="⚡" size={15} /> {t("Авто-распределение выручки","Авто-розподіл виручки")}</h3>
        <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>{t("Каждый фонд выручки (ФВ) получит свой % от суммы за","Кожен фонд виручки (ФВ) отримає свій % від суми за")} {period}.</div>
        <label className="label">{t("Сумма выручки, ₴","Сума виручки, ₴")}</label>
        <input type="number" value={revenue} autoFocus onChange={(e) => setRevenue(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 }} />
        <label className="label">{t("На счёт","На рахунок")}</label>
        <select value={account} onChange={(e) => setAccount(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, marginBottom: 10 }}>
          <option value="">—</option>{accounts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <label className="label">{t("Направление (необяз.)","Напрямок (необов.)")}</label>
        <select value={direction} onChange={(e) => setDirection(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, marginBottom: 12 }}>
          <option value="">{t("— все —","— усі —")}</option>{dirs.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        {res && <div style={{ background: "#f0fdf4", borderRadius: 8, padding: 10, fontSize: 13, marginBottom: 12 }}>{res.length ? res.map((x, i) => <div key={i}>✓ {x.fund}: {money(x.amount)}</div>) : t("Нет фондов выручки с %.","Немає фондів виручки з %.")}</div>}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={res ? onSaved : onClose}>{res ? t("Готово","Готово") : t("Отмена","Скасувати")}</button>
          {!res && <button className="btn btn-primary" style={{ flex: 1 }} onClick={run} disabled={busy}>{busy ? "…" : t("Распределить","Розподілити")}</button>}
        </div>
      </div>
    </div>
  );
}

/* ─── ВКЛАДКА: ЗП / KPI МЕНЕДЖЕРІВ (стратегія РОП+психолог) ──────────────── */
function Salary() {
  const { t } = useLang();
  const [period, setPeriod] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; });
  const [data, setData] = useState<any>(null);
  useEffect(() => { setData(null); api.get<any>(`/api/finance/salary/?period=${period}`).then(setData); }, [period]);
  if (!data) return <div className="spin">{t("Считаем ЗП…","Рахуємо ЗП…")}</div>;
  const c = data.company;
  const tierLabel = (m: number) => m >= 1.3 ? t("перевыполнение ×1.3","перевиконання ×1.3") : m >= 1 ? t("полные премии ×1.0","повні премії ×1.0") : m >= 0.8 ? t("почти план ×0.8","майже план ×0.8") : m >= 0.5 ? t("половина ×0.5","половина ×0.5") : t("старт ×0.3","старт ×0.3");
  return (
    <>
      <div className="note"><Icon n="💰" size={14} /> {t("ЗП считается","ЗП рахується")} <b>{t("без жёсткого GATE","без жорсткого GATE")}</b>: {t("премии открываются поэтапно с 70% плана (×0.3→×1.3). Ставки меняются во вкладке «Финмодель → ЗП». Планы — во вкладке «Планы».","премії відкриваються поетапно з 70% плану (×0.3→×1.3). Ставки міняються у вкладці «Фінмодель → ЗП». Плани — у вкладці «Плани».")}</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <span className="muted" style={{ fontSize: 13 }}>{t("Месяц","Місяць")}:</span>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
        <div style={{ flex: 1 }} />
        <span className="muted" style={{ fontSize: 12 }}>{t("ФОТ-прогноз","ФОП-прогноз")}: <b>{money(c.total_payroll)}</b></span>
      </div>
      {data.rows.map((r: any) => {
        const pct = r.plan_pct ?? 0;
        return (
          <div key={r.user_id} className="panel" style={{ margin: "10px 0 0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <b style={{ fontSize: 15, flex: 1 }}>{r.user_name}</b>
              <span style={{ fontSize: 12, color: "#64748b" }} title={t("Множитель премий за выполнением плана","Множник премій за виконанням плану")}>{tierLabel(r.tier_mult)}</span>
              <span style={{ background: "linear-gradient(135deg,#16a34a,#15803d)", color: "#fff", padding: "4px 12px", borderRadius: 8, fontWeight: 700 }} title={t("Прогноз ЗП за месяц","Прогноз ЗП за місяць")}>{money(r.total)}</span>
            </div>
            <div style={{ margin: "8px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span className="muted">{t("План","План")} {r.plan_target ? money(r.plan_target) : t("не установлено","не встановлено")} · {r.deals} {t("сделок","угод")} · {t("чек","чек")} {money(r.avg_check)}</span>
                <b style={{ color: pct >= 100 ? "#16a34a" : pct >= 70 ? "#d97706" : "#dc2626" }}>{r.plan_pct != null ? r.plan_pct + "%" : "—"}</b>
              </div>
              <div style={{ height: 10, background: "#e2e8f0", borderRadius: 6, overflow: "hidden", marginTop: 4 }}>
                <div style={{ width: Math.min(100, pct) + "%", height: "100%", background: pct >= 100 ? "#16a34a" : pct >= 70 ? "#d97706" : "#0ea5e9" }} />
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", fontSize: 12, marginBottom: 8 }}>
              <span title={t("Фиксированный оклад","Фіксований оклад")}>{t("Оклад","Оклад")} {money(r.part_base)}</span>
              <span title={t("% с оборота","% з обороту")}>+ {t("оборот","оборот")} {money(r.part_revenue)}</span>
              <span title={t("% с маржи (плавающий","% з маржі (плаваючий") + ` ${r.margin_kpi_pct}%)`}>+ {t("маржа","маржа")} {money(r.part_margin)}</span>
              <span title={`${r.kpi_hits} KPI × ${money(r.kpi_premium)} × ` + t("множитель","множник") + ` ${r.tier_mult}`} style={{ color: "#7c3aed" }}>+ KPI {money(r.bonus_kpi)}</span>
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
        <div className="muted" style={{ fontSize: 12 }}><Icon n="🎯" size={13} /> {t("Покрытие цели компании","Покриття цілі компанії")}: {t("ТБ","ТБ")} <b>{money(c.breakeven)}</b> · {t("цель","ціль")} ×1.3 <b>{money(c.target)}</b> · {t("сумма планов","сума планів")} <b>{money(c.sum_plans)}</b> · {t("покрытие","покриття")} <b style={{ color: c.coverage_pct >= 100 ? "#16a34a" : "#dc2626" }}>{c.coverage_pct}%</b></div>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА: ПЛАНИ МЕНЕДЖЕРІВ (3 рівні, персональні) ──────────────────── */
function MPlans() {
  const { t } = useLang();
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
  if (!sal) return <div className="spin">{t("Загрузка…","Завантаження…")}</div>;
  const c = sal.company;
  const inp = { width: 110, height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px", textAlign: "right" } as React.CSSProperties;
  return (
    <>
      <div className="note"><Icon n="🎯" size={14} /> <b>{t("Планы персональные","Плани персональні")}</b> {t("(не одинаковые!). Норма ≈ факт × 1.2, амбиция ≈ факт × 1.5 (рекомендация РОП). Кнопка «🎁 Авто» ставит уровни от фактической выручки менеджера.","(не однакові!). Норма ≈ факт × 1.2, амбіція ≈ факт × 1.5 (рекомендація РОП). Кнопка «🎁 Авто» ставить рівні від фактичної виручки менеджера.")}</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <span className="muted" style={{ fontSize: 13 }}>{t("Месяц","Місяць")}:</span>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
      </div>
      <div className="panel" style={{ margin: "0 0 12px", background: "#f8fafc" }}>
        <div className="muted" style={{ fontSize: 12 }}><Icon n="🏢" size={13} /> {t("ТБ компании","ТБ компанії")} <b>{money(c.breakeven)}</b> · {t("цель","ціль")} ×1.3 <b>{money(c.target)}</b> · {t("сумма планов","сума планів")} <b>{money(c.sum_plans)}</b> · {t("покрытие","покриття")} <b style={{ color: c.coverage_pct >= 100 ? "#16a34a" : "#dc2626" }}>{c.coverage_pct}%</b></div>
      </div>
      {sal.rows.map((r: any) => {
        const p = plans[r.user_id] || {};
        return (
          <div key={r.user_id} className="panel" style={{ margin: "10px 0 0" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <b style={{ fontSize: 14, flex: 1 }}>{r.user_name}</b>
              <span className="muted" style={{ fontSize: 12 }}>{t("факт","факт")}: {money(r.revenue)} · {r.deals} {t("сделок","угод")}</span>
              <button className="btn btn-light" style={{ fontSize: 12 }} title={t("Поставить уровни автоматически от факта","Поставити рівні автоматично від факту")} onClick={() => recommend(r)}><Icon n="🎁" size={13} /> {t("Авто","Авто")}</button>
            </div>
            <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
              <label style={{ fontSize: 12 }} title={t("Минимум — ниже не падать","Мінімум — нижче не падати")}>🟥 {t("Минимум","Мінімум")} <input type="number" defaultValue={p.min_revenue || 0} onBlur={(e) => save(r.user_id, { min_revenue: Number(e.target.value) })} style={inp} /></label>
              <label style={{ fontSize: 12 }} title={t("Норма — главная цель месяца","Норма — головна ціль місяця")}>🟩 {t("Норма","Норма")} <input type="number" defaultValue={p.target_revenue || 0} onBlur={(e) => save(r.user_id, { target_revenue: Number(e.target.value) })} style={inp} /></label>
              <label style={{ fontSize: 12 }} title={t("Амбиция — сверх-результат","Амбіція — понад-результат")}>🟦 {t("Амбиция","Амбіція")} <input type="number" defaultValue={p.ambition_revenue || 0} onBlur={(e) => save(r.user_id, { ambition_revenue: Number(e.target.value) })} style={inp} /></label>
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

/* ─── ВКЛАДКА: ЗРОСТАННЯ (звіт радчої системи агентів) ─────────────────── */
function mdToHtml(md: string): string {
  const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (t: string) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
  const lines = md.split("\n");
  let html = "", i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (/^\|(.+)\|\s*$/.test(ln) && i + 1 < lines.length && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const head = ln.split("|").slice(1, -1).map((c) => `<th style="text-align:left;padding:6px 10px;border-bottom:2px solid #e2e8f0">${inline(c.trim())}</th>`).join("");
      i += 2; let rows = "";
      while (i < lines.length && /^\|(.+)\|\s*$/.test(lines[i])) {
        rows += "<tr>" + lines[i].split("|").slice(1, -1).map((c) => `<td style="padding:6px 10px;border-bottom:1px solid #f1f5f9">${inline(c.trim())}</td>`).join("") + "</tr>"; i++;
      }
      html += `<table style="width:100%;border-collapse:collapse;margin:10px 0;font-size:13px"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
      continue;
    }
    if (/^###\s+/.test(ln)) html += `<h4 style="margin:14px 0 4px">${inline(ln.replace(/^###\s+/, ""))}</h4>`;
    else if (/^##\s+/.test(ln)) html += `<h3 style="margin:18px 0 6px;color:#1e293b">${inline(ln.replace(/^##\s+/, ""))}</h3>`;
    else if (/^#\s+/.test(ln)) html += `<h2 style="margin:6px 0 10px">${inline(ln.replace(/^#\s+/, ""))}</h2>`;
    else if (/^[-*]\s+/.test(ln)) { let items = ""; while (i < lines.length && /^[-*]\s+/.test(lines[i])) { items += `<li>${inline(lines[i].replace(/^[-*]\s+/, ""))}</li>`; i++; } html += `<ul style="margin:6px 0 6px 18px">${items}</ul>`; continue; }
    else if (/^\d+\.\s+/.test(ln)) { let items = ""; while (i < lines.length && /^\d+\.\s+/.test(lines[i])) { items += `<li>${inline(lines[i].replace(/^\d+\.\s+/, ""))}</li>`; i++; } html += `<ol style="margin:6px 0 6px 18px">${items}</ol>`; continue; }
    else if (/^---+\s*$/.test(ln)) html += "<hr style='border:none;border-top:1px solid #e2e8f0;margin:14px 0'/>";
    else if (ln.trim()) html += `<p style="margin:6px 0;line-height:1.55">${inline(ln)}</p>`;
    i++;
  }
  return html;
}

function Growth() {
  const { t } = useLang();
  const [rep, setRep] = useState<any | null | undefined>(undefined);
  useEffect(() => { api.get<any>("/api/advisory-reports/?page_size=1").then((d) => { const arr = d.results || d; setRep(arr[0] || null); }).catch(() => setRep(null)); }, []);
  if (rep === undefined) return <div className="spin">{t("Загрузка…","Завантаження…")}</div>;
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div className="note"><Icon n="🚀" size={14} /> <b>{t("Рост прибыли","Зростання прибутку")}</b> {t("— план от совещательной системы: бизнес-аналитик, финаналитик, РОП, коуч по команде и маркетолог проанализировали бизнес и конкурентов, проверили друг друга и составили безопасный план удвоения чистой прибыли за 2-3 месяца.","— план від радчої системи: бізнес-аналітик, фінаналітик, РОП, коуч по команді та маркетолог проаналізували бізнес і конкурентів, перевірили одне одного й склали безпечний план подвоєння чистого прибутку за 2-3 місяці.")}</div>
      {!rep ? (
        <div className="muted" style={{ fontSize: 14, padding: 20, textAlign: "center" }}>{t("Отчёт ещё готовится агентами или не сформирован. Зайди немного позже — он появится тут автоматически.","Звіт ще готується агентами або не сформований. Зайди трохи пізніше — він зʼявиться тут автоматично.")}</div>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 8 }}>
            <h2 style={{ margin: 0, fontSize: 20 }}>{rep.title}</h2>
            <span className="muted" style={{ fontSize: 12 }}>{new Date(rep.created_at).toLocaleString("ru")}</span>
          </div>
          <div style={{ marginTop: 10 }} dangerouslySetInnerHTML={{ __html: mdToHtml(rep.body) }} />
        </>
      )}
    </div>
  );
}

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
  const { t } = useLang();
  const [arts, setArts] = useState<any[]>([]);
  const [dragId, setDragId] = useState<number | null>(null);
  const [overCat, setOverCat] = useState<string | null>(null);
  const load = () => api.get<any>("/api/finmodel-articles/?page_size=200").then((r) => setArts(r.results || r));
  useEffect(() => { load(); }, []);
  async function save(id: number, patch: any) { await api.patch(`/api/finmodel-articles/${id}/`, patch); }
  async function add(category: string, parent?: number) {
    await api.post("/api/finmodel-articles/", { category, parent: parent ?? null, name: parent ? t("Новый подфонд","Новий підфонд") : t("Новая статья","Нова стаття"), value: 0,
      value_type: category === "revenue_fund" || category === "variable" ? "percent" : "fixed_sum_per_month", is_envelope: !!parent });
    load();
  }
  async function del(id: number) { if (!confirm(t("Удалить эту статью финмодели?","Видалити цю статтю фінмоделі?"))) return; await api.del(`/api/finmodel-articles/${id}/`); load(); }
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
      {!sub && <span title={t("Перетащи мышкой в другую категорию","Перетягни мишкою в іншу категорію")} style={{ color: "#cbd5e1", cursor: "grab", marginRight: 4, userSelect: "none" }}>⠿</span>}
      {sub && <span style={{ color: "#cbd5e1", marginRight: 4 }}>↳</span>}
      <input defaultValue={a.name} title={t("Название статьи / фонда — кликни, чтобы переименовать","Назва статті / фонду — клікни, щоб перейменувати")} onBlur={(e) => save(a.id, { name: e.target.value })}
        style={{ flex: 1, height: 28, border: "1px solid transparent", borderRadius: 6, padding: "0 6px", fontWeight: sub ? 400 : 500, background: "transparent" }} />
      <button title={a.is_envelope ? t("Это конверт: держит деньги для планирования. Кликни, чтобы выключить.","Це конверт: тримає гроші для планування. Клікни, щоб вимкнути.") : t("Сделать конвертом — тогда в него можно класть деньги во вкладке «Планирование»","Зробити конвертом — тоді в нього можна класти гроші у вкладці «Планування»")} onClick={() => save(a.id, { is_envelope: !a.is_envelope }).then(load)}
        style={{ width: 28, height: 26, borderRadius: 6, marginRight: 6, cursor: "pointer", border: "1px solid " + (a.is_envelope ? "#0ea5e9" : "#e2e8f0"), background: a.is_envelope ? "#e0f2fe" : "#fff" }}><Icon n="✉️" size={15} /></button>
      <input type="number" defaultValue={a.value} title={t("Значение: % или сумма в гривнах (тип справа). Влияет на P&L и точку безубыточности.","Значення: % або сума в гривнях (тип праворуч). Впливає на P&L і точку беззбитковості.")} onBlur={(e) => save(a.id, { value: Number(e.target.value) })} style={{ width: 96, height: 28, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px", textAlign: "right" }} />
      <span className="muted" style={{ width: 64, fontSize: 12 }} title={t("Единица: % от суммы, грн/месяц, грн/сделку и т.д.","Одиниця: % від суми, грн/місяць, грн/угоду тощо")}>{a.unit || a.value_type_display}</span>
      {!sub && <span title={t("Добавить подфонд (под-конверт внутри этого фонда)","Додати підфонд (під-конверт усередині цього фонду)")} style={{ color: "#0ea5e9", cursor: "pointer", paddingLeft: 6, fontWeight: 700 }} onClick={() => add(a.category, a.id)}>＋</span>}
      <span title={t("Удалить статью","Видалити статтю")} style={{ color: "#ef4444", cursor: "pointer", paddingLeft: 8 }} onClick={() => del(a.id)}>✕</span>
    </div>
  );

  return (
    <>
      <div className="note"><Icon n="⚙️" size={14} /> <b>{t("Финмодель","Фінмодель")}</b> {t("— сердце расчётов: отсюда считаются P&L и Точка безубыточности. Порядок фондов:","— серце розрахунків: звідси рахуються P&L і Точка беззбитковості. Порядок фондів:")} <b>{t("ФВ (выручки) → ФМ (маржи) → ФСКД (скорректированного дохода)","ФВ (виручки) → ФМ (маржі) → ФСКД (скоригованого доходу)")}</b>. {t("✉️ = конверт (держит деньги для планирования). ＋ — добавить подфонд.","✉️ = конверт (тримає гроші для планування). ＋ — додати підфонд.")} <b>{t("⠿ Перетащи статью мышкой в другую категорию","⠿ Перетягни статтю мишкою в іншу категорію")}</b>{t(", чтобы переложить фонд. Наведи на любое поле — подскажет, что это.",", щоб перекласти фонд. Наведи на будь-яке поле — підкаже, що це.")}</div>
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
                    <span className="muted" style={{ fontSize: 12, fontWeight: 600 }} title={isOver ? t("Отпусти тут, чтобы переложить фонд в эту категорию","Відпусти тут, щоб перекласти фонд у цю категорію") : t("Категория статей","Категорія статей")}>{CAT_LABEL[c]}{isOver ? t(" ⬇ отпусти тут"," ⬇ відпусти тут") : ""}</span>
                    <button className="btn btn-light" style={{ fontSize: 11, padding: "2px 8px" }} title={t("Добавить новую статью в эту категорию","Додати нову статтю в цю категорію")} onClick={() => add(c)}>+ {t("статья","стаття")}</button>
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
