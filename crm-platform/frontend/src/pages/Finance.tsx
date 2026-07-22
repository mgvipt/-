/* ============================================================================
 *  ФІНАНСИ  —  frontend/src/pages/Finance.tsx
 *  Вкладки: Дашборд (ДДС) · P&L (ATM) · Точка беззбитковості · Фінмодель.
 *  Источник формул — Wallcov Cashflow. Документация: docs/TZ-finmodule.md.
 * ========================================================================== */
import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import DealCard from "./DealCard";
import TxCardModal from "../TxCardModal";
import { useNavigate } from "react-router-dom";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
import { useAuth } from "../auth";
function useNav() { return useNavigate(); }

/* Контрагент -> клієнт CRM: єдиний кеш, щоб контрагент був клікабельним і в Журналі, і в Дт/Кт */
let _cpMapCache: Record<string, number> | null = null;
let _cpMapPromise: Promise<Record<string, number>> | null = null;
function loadCpMap(): Promise<Record<string, number>> {
  if (_cpMapCache) return Promise.resolve(_cpMapCache);
  if (!_cpMapPromise) _cpMapPromise = api.get<any>("/api/finance/counterparties/").then((rows: any) => {
    const m: Record<string, number> = {};
    (rows || []).forEach((r: any) => { if (r && r.contact_id) m[String(r.name || "").trim().toLowerCase()] = r.contact_id; });
    _cpMapCache = m; return m;
  }).catch(() => ({}));
  return _cpMapPromise;
}
function useCpMap(): Record<string, number> {
  const [m, setM] = useState<Record<string, number>>(_cpMapCache || {});
  useEffect(() => { let ok = true; loadCpMap().then((x) => { if (ok) setM(x); }); return () => { ok = false; }; }, []);
  return m;
}
function CpText({ name, contact, cpMap, nav }: { name?: string; contact?: number; cpMap: Record<string, number>; nav: (p: string) => void }) {
  if (!name) return <span className="muted">—</span>;
  const cid = contact || cpMap[String(name).trim().toLowerCase()];
  if (!cid) return <span>{name}</span>;
  return <a onClick={(e) => { e.stopPropagation(); nav("/clients/" + cid); }}
    style={{ color: "#0e7490", cursor: "pointer", fontWeight: 600, textDecoration: "none" }}
    title="Відкрити картку клієнта">{name}</a>;
}

const money = (n: number) => Math.round(n || 0).toLocaleString("ru") + " ₴";
const FUND_GROUPS_G: [string, string][] = [["revenue_fund", "ФОНДИ ВИРУЧКИ (ФВ)"], ["variable", "ФОНДИ МАРЖІ — змінні"], ["fixed", "ФОНДИ МАРЖІ — постійні"], ["skd", "СКОРИГОВАНИЙ ДОХІД (СКД)"], ["payment_fee", "Комісії за оплату"], ["upr_cat2", "УПР обовʼязкові"], ["upr_cat3", "УПР відмовні"]];
const money2 = (n: number) => (Number(n) || 0).toLocaleString("ru", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " ₴";
/* короткий формат грошей для осі: 1.2М / 850К / 0 / −40К */
function fmtShort(n: number): string {
  const a = Math.abs(n), sign = n < 0 ? "−" : "";
  if (a >= 1e6) return sign + (a / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(".0", "") + "М";
  if (a >= 1e3) return sign + Math.round(a / 1e3) + "К";
  return sign + Math.round(a);
}
/* красиві поділки осі: верх, половини, нуль, низ */
function mkTicks(hi: number, lo: number): number[] {
  const t = [hi, hi / 2, 0];
  if (lo < 0) { t.push(lo / 2, lo); }
  return Array.from(new Set(t.map((v) => Math.round(v))));
}
/* плавна крива через точки (Catmull-Rom → кубічні Безьє) */
function smoothPath(pts: number[][]): string {
  if (pts.length < 2) return "";
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    d += ` C ${p1[0] + (p2[0] - p0[0]) / 6} ${p1[1] + (p2[1] - p0[1]) / 6}, ${p2[0] - (p3[0] - p1[0]) / 6} ${p2[1] - (p3[1] - p1[1]) / 6}, ${p2[0]} ${p2[1]}`;
  }
  return d;
}
const pad = (n: number) => String(n).padStart(2, "0");
const today = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const monthStart = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`; };

export default function Finance() {
  const { t } = useLang();
  const [tab, setTab] = useState<"dash" | "journal" | "triage" | "pnl" | "be" | "dir" | "plan" | "debts" | "grow" | "salary" | "mplan" | "time" | "ref" | "model" | "incoming">(() => ((new URLSearchParams(window.location.search).get("tx") || new URLSearchParams(window.location.search).get("client")) ? "journal" : (localStorage.getItem("fin_tab") as any) || "dash"));
  useEffect(() => { try { localStorage.setItem("fin_tab", tab); } catch (e) { /* noop */ } }, [tab]);
  const [quickOpen, setQuickOpen] = useState(false);
  const isMobile = useIsMobile();
  const { can: canF } = useAuth();
  const tabAllowed = (k: string) => k === "dash" ? true : (canF("finance.tab." + k) || canF("roles.manage"));
  useEffect(() => { if (!tabAllowed(tab)) setTab("dash"); /* eslint-disable-next-line */ }, [tab]);
  const tabs: [string, React.ReactNode][] = [["dash", <><Icon n="💰" size={15} /> {t("Дашборд","Дашборд")}</>], ["journal", <><Icon n="🧾" size={15} /> {t("Журнал","Журнал")}</>], ["triage", <><Icon n="🧹" size={15} /> {t("Разноска","Рознесення")}</>], ["pnl", <><Icon n="📊" size={15} /> {t("P&L (ATM)","P&L (ATM)")}</>], ["be", <><Icon n="🎯" size={15} /> {t("Точка безубыточности","Точка беззбитковості")}</>], ["dir", <><Icon n="🗂" size={15} /> {t("Направления (проекты)","Напрямки (проекти)")}</>], ["plan", <><Icon n="💼" size={15} /> {t("Планирование","Планування")}</>], ["debts", <><Icon n="🤝" size={15} /> {t("Дт/Кт","Дт/Кт")}</>], ["incoming", <><Icon n="📥" size={15} /> {t("Вх. накладные","Вхідні накладні")}</>], ["grow", <><Icon n="🚀" size={15} /> {t("Рост","Зростання")}</>], ["salary", <><Icon n="💰" size={15} /> {t("ЗП/KPI","ЗП/KPI")}</>], ["mplan", <><Icon n="🎯" size={15} /> {t("Планы","Плани")}</>], ["time", <><Icon n="🕐" size={15} /> {t("Табель","Табель")}</>], ["ref", <><Icon n="📚" size={15} /> {t("Справочники","Довідники")}</>], ["model", <><Icon n="⚙️" size={15} /> {t("Финмодель","Фінмодель")}</>]];
  const tabMap: any = Object.fromEntries(tabs);
  const GROUPS: [string, string[], string][] = [
    [t("Обзор", "Огляд"), ["dash"], "💰"],
    [t("Операции", "Операції"), ["journal", "triage", "debts", "incoming"], "🧾"],
    [t("Аналитика", "Аналітика"), ["pnl", "be", "grow", "dir"], "📊"],
    [t("Планы", "Плани"), ["plan", "mplan", "salary", "time"], "💼"],
    [t("Справочники", "Довідники"), ["ref", "model"], "📚"],
  ];
  const activeGroup = GROUPS.find(([, ks]) => ks.includes(tab)) || GROUPS[0];
  return (
    <div className="scroll pad fade">
      <button onClick={() => setQuickOpen(true)} title={t("Быстрый платёж", "Швидкий платіж")}
        style={{ position: "fixed", right: 16, bottom: isMobile ? 74 : 18, zIndex: 900, width: 56, height: 56, borderRadius: "50%", border: "none", background: "#C67D5F", color: "#fff", fontSize: 24, boxShadow: "0 6px 20px rgba(198,125,95,.5)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon n="⚡" size={24} /></button>
      {quickOpen && <QuickExpenseModal onClose={() => setQuickOpen(false)} />}
      {!isMobile && <div className="fin-tabs" style={{ display: "flex", gap: 6, margin: "12px 0 6px" }}>
        {GROUPS.filter(([, ks]) => ks.some((k) => tabAllowed(k))).map(([gl, ks]) => (
          <button key={gl} className={activeGroup[0] === gl ? "btn btn-primary" : "btn btn-light"} onClick={() => { const first = ks.find((k) => tabAllowed(k)); if (first) setTab(first as any); }} style={{ fontWeight: 700 }}>{gl}</button>
        ))}
      </div>}
      {activeGroup[1].filter((k) => tabAllowed(k)).length > 1 && (
        <div className="fin-tabs" style={{ display: "flex", gap: 6, marginBottom: 12, paddingBottom: 8, borderBottom: "1px solid #e2e8f0" }}>
          {activeGroup[1].filter((k) => tabAllowed(k)).map((k) => (
            <button key={k} className={tab === k ? "btn btn-primary" : "btn btn-light"} style={{ height: 30, fontSize: 12.5 }} onClick={() => setTab(k as any)}>{tabMap[k]}</button>
          ))}
        </div>
      )}
      {tab === "dash" && <Dashboard />}
      {tab === "journal" && <Journal />}
      {tab === "triage" && <TriageTab />}
      {tab === "pnl" && <PnL />}
      {tab === "be" && <Breakeven />}
      {tab === "dir" && <Directions />}
      {tab === "plan" && <Planning />}
      {tab === "debts" && <Debts />}
      {tab === "incoming" && <IncomingDocsTab />}
      {tab === "grow" && <Growth />}
      {tab === "salary" && <Salary />}
      {tab === "mplan" && <MPlans />}
      {tab === "time" && <Timesheet />}
      {tab === "ref" && <Reference />}
      {tab === "model" && <FinModel />}
      {isMobile && (
        <div style={{ position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 950, display: "flex", background: "#fff", borderTop: "1px solid #e2e8f0", boxShadow: "0 -2px 12px rgba(0,0,0,.08)" }}>
          {GROUPS.filter(([, ks]) => ks.some((k) => tabAllowed(k))).map(([gl, ks, ic]) => {
            const act = activeGroup[0] === gl;
            return <button key={gl} onClick={() => { const first = ks.find((k) => tabAllowed(k)); if (first) setTab(first as any); }} style={{ flex: 1, border: "none", background: "none", padding: "7px 2px", cursor: "pointer", color: act ? "#2563eb" : "#64748b", fontWeight: act ? 700 : 500, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}><Icon n={ic} size={20} /><span style={{ fontSize: 10 }}>{gl}</span></button>;
          })}
        </div>
      )}
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
export function CpField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
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

/* Пошук/вибір угоди: за номером, назвою АБО зі списку угод обраного клієнта (contact) — щоб не шукати номер вручну */
export function DealPick({ value, label, contact, onPick }: { value?: number; label?: string; contact?: number; onPick: (id: number, title: string) => void }) {
  const { t } = useLang();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const qq = q.trim();
    if (qq) {
      const h = setTimeout(async () => {
        try {
          if (/^\d+$/.test(qq)) { const one = await api.get<any>(`/api/deals/${qq}/`).catch(() => null); setRes(one && one.id ? [one] : []); }
          else { const d = await api.get<any>(`/api/deals/?search=${encodeURIComponent(qq)}&page_size=8`); setRes((d.results || d) as any[]); }
        } catch { setRes([]); }
      }, 250);
      return () => clearTimeout(h);
    } else if (open && contact) {
      api.get<any>(`/api/deals/?contact=${contact}&page_size=20`).then((d) => setRes((d.results || d) as any[])).catch(() => setRes([]));
    } else { setRes([]); }
  }, [q, open, contact]);
  const inpS = { height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", width: "100%", fontSize: 13, boxSizing: "border-box" } as React.CSSProperties;
  return (
    <div style={{ position: "relative", marginBottom: 10 }}>
      {value ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, height: 36, border: "1px solid #bfdbfe", borderRadius: 8, padding: "0 10px", background: "#eff6ff" }}>
          <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: "#1d4ed8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>№{value}{label ? " · " + label : ""}</span>
          <span onClick={() => onPick(0, "")} title={t("Отвязать", "Відвʼязати")} style={{ cursor: "pointer", color: "#94a3b8", fontSize: 16 }}>✕</span>
        </div>
      ) : (
        <input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 180)} placeholder={contact ? t("Сделки клиента ↓ или № / название", "Угоди клієнта ↓ або № / назва") : t("№ или название сделки…", "№ або назва угоди…")} style={inpS} />
      )}
      {open && !value && res.length > 0 && (
        <div style={{ position: "absolute", top: 38, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 8px 24px rgba(15,23,42,.15)", zIndex: 40, maxHeight: 240, overflowY: "auto" }}>
          {!q.trim() && contact ? <div style={{ padding: "5px 10px", fontSize: 11, color: "#94a3b8", background: "#f8fafc" }}>{t("Сделки этого клиента:", "Угоди цього клієнта:")}</div> : null}
          {res.map((d) => (
            <div key={d.id} onMouseDown={() => { onPick(d.id, d.title || ""); setQ(""); setOpen(false); }} style={{ padding: "7px 10px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13 }}>
              <b style={{ color: "#1d4ed8" }}>№{d.id}</b> · {String(d.title || "").slice(0, 42)} {d.amount ? <span className="muted">· {Math.round(Number(d.amount)).toLocaleString("ru")} ₴</span> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const RULE_FIELDS: [string, string][] = [["osnd", "Коментар / призначення"], ["counterparty", "Контрагент"], ["account", "Рахунок"]];
const RULE_OPS: [string, string][] = [["contains", "містить"], ["not_contains", "не містить"], ["equals", "дорівнює"]];
const RULE_ACTS: [string, string][] = [["category", "Категорію"], ["fin_direction", "Проект (напрямок)"], ["fin_article", "Фонд"], ["counterparty", "Контрагента"], ["channel", "Канал"]];

function RuleEditor({ rule, cats, dirs, arts, accsR, cps, onClose, onSaved, t }: any) {
  const [r, setR] = useState<any>(() => ({
    name: rule?.name || "",
    direction: rule?.direction || "",
    logic: rule?.logic || "or",
    active: rule ? rule.active !== false : true,
    conditions: (rule?.conditions && rule.conditions.length ? rule.conditions : [{ field: "osnd", op: "contains", text: "" }]).map((c: any) => ({ ...c })),
    acts: rule?.actions ? Object.entries(rule.actions).map(([k, v]) => ({ type: k, value: String(v) })) : [{ type: "category", value: "" }],
  }));
  const [busy, setBusy] = useState(false);
  const inp: any = { height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 9px", fontSize: 13, background: "#fff" };
  const setCond = (i: number, patch: any) => setR((x: any) => ({ ...x, conditions: x.conditions.map((c: any, j: number) => j === i ? { ...c, ...patch } : c) }));
  const setAct = (i: number, patch: any) => setR((x: any) => ({ ...x, acts: x.acts.map((a: any, j: number) => j === i ? { ...a, ...patch } : a) }));
  async function save() {
    const conditions = r.conditions.filter((c: any) => (c.text || "").trim());
    if (!conditions.length) { alert(t("Добавь хотя бы одно условие с текстом", "Додай хоча б одну умову з текстом")); return; }
    const actions: any = {};
    r.acts.forEach((a: any) => {
      if (!a.type || a.value === "" || a.value == null) return;
      actions[a.type] = ["category", "fin_direction", "fin_article"].includes(a.type) ? Number(a.value) : a.value;
    });
    if (!Object.keys(actions).length) { alert(t("Добавь хотя бы одно действие", "Додай хоча б одну дію")); return; }
    setBusy(true);
    const body = { name: r.name || conditions.map((c: any) => c.text).join(" / "), direction: r.direction, logic: r.logic, active: r.active, conditions, actions };
    try {
      if (rule?.id) await api.patch(`/api/finance/bank-rules/${rule.id}/`, body);
      else await api.post("/api/finance/bank-rules/", body);
      onSaved(); onClose();
    } catch (e: any) { alert(e?.response?.data?.detail || "Помилка збереження"); }
    setBusy(false);
  }
  const valueCtrl = (a: any, i: number) => {
    if (a.type === "category") return (
      <select value={a.value} onChange={(e) => setAct(i, { value: e.target.value })} style={{ ...inp, flex: 1 }}>
        <option value="">{t("— выбери категорию —", "— обери категорію —")}</option>
        {cats.filter((c: any) => !r.direction || c.direction === r.direction || r.direction === "transfer").map((c: any) => <option key={c.id} value={c.id}>{c.direction === "in" ? "▲ " : "▼ "}{c.name}</option>)}
      </select>);
    if (a.type === "fin_direction") return (
      <select value={a.value} onChange={(e) => setAct(i, { value: e.target.value })} style={{ ...inp, flex: 1 }}>
        <option value="">{t("— выбери проект —", "— обери проект —")}</option>
        {dirs.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
      </select>);
    if (a.type === "fin_article") return (
      <select value={a.value} onChange={(e) => setAct(i, { value: e.target.value })} style={{ ...inp, flex: 1 }}>
        <option value="">{t("— выбери фонд —", "— обери фонд —")}</option>
        {arts.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
      </select>);
    return <input value={a.value} onChange={(e) => setAct(i, { value: e.target.value })} placeholder={a.type === "channel" ? "instagram / tiktok / offline…" : t("Имя контрагента", "Імʼя контрагента")} style={{ ...inp, flex: 1 }} />;
  };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 16, padding: 22, width: "min(760px,96vw)", maxHeight: "92vh", overflowY: "auto" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ margin: 0, flex: 1 }}>{rule?.id ? t("Редактирование правила", "Редагування правила") : t("Новое правило", "Нове правило")}</h3>
          <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12.5, cursor: "pointer" }}>
            <span className={"toggle" + (r.active ? " on" : "")} onClick={() => setR({ ...r, active: !r.active })} />
            {r.active ? t("Включено", "Увімкнено") : t("Выключено", "Вимкнено")}
          </label>
        </div>
        <input value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} placeholder={t("Название правила", "Назва правила")} style={{ ...inp, width: "100%", height: 38, marginBottom: 12, fontWeight: 600 }} />
        <div style={{ display: "flex", gap: 6, marginBottom: 14, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 12 }}>{t("Применять для:", "Застосовувати для:")}</span>
          {[["", t("Любой", "Будь-який")], ["in", t("Доход", "Дохід")], ["out", t("Расход", "Витрата")], ["transfer", t("Перевод", "Переказ")]].map(([k, l]) => (
            <button key={k} onClick={() => setR({ ...r, direction: k })} className={"btn" + (r.direction === k ? " btn-primary" : " btn-light")} style={{ height: 28, fontSize: 12 }}>{l}</button>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "4px 0 8px" }}>
          <b style={{ fontSize: 13 }}>{t("Условие", "Умова")}</b>
          <div style={{ display: "inline-flex", borderRadius: 8, overflow: "hidden", border: "1px solid #e2e8f0" }}>
            {[["and", "І"], ["or", "АБО"]].map(([k, l]) => (
              <button key={k} onClick={() => setR({ ...r, logic: k })} style={{ padding: "4px 14px", fontSize: 11.5, fontWeight: 700, border: "none", cursor: "pointer", background: r.logic === k ? "#0f172a" : "#f8fafc", color: r.logic === k ? "#fff" : "#64748b" }}>{l}</button>
            ))}
          </div>
          <span className="muted" style={{ fontSize: 11 }}>{r.logic === "and" ? t("должны совпасть ВСЕ строки", "мають збігтися ВСІ рядки") : t("достаточно ЛЮБОЙ строки", "достатньо БУДЬ-ЯКОГО рядка")}</span>
        </div>
        {r.conditions.map((c: any, i: number) => (
          <div key={i} style={{ display: "flex", gap: 7, marginBottom: 7, alignItems: "center" }}>
            <select value={c.field} onChange={(e) => setCond(i, { field: e.target.value })} style={{ ...inp, width: 190 }}>
              {RULE_FIELDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <select value={c.op} onChange={(e) => setCond(i, { op: e.target.value })} style={{ ...inp, width: 130 }}>
              {RULE_OPS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            {c.field === "account" ? (
              <select value={c.text} onChange={(e) => setCond(i, { text: e.target.value })} style={{ ...inp, flex: 1 }}>
                <option value="">{t("— выбери счёт —", "— обери рахунок —")}</option>
                {accsR.map((a: any) => <option key={a.id} value={a.name}>{a.name}</option>)}
              </select>
            ) : c.field === "counterparty" ? (
              <>
                <input list={`cp-list-${i}`} value={c.text} onChange={(e) => setCond(i, { text: e.target.value })} placeholder={t("Начни вводить — подскажет из списка…", "Почни вводити — підкаже зі списку…")} style={{ ...inp, flex: 1 }} />
                <datalist id={`cp-list-${i}`}>{cps.filter((n: string) => !c.text || n.toLowerCase().includes(c.text.toLowerCase())).slice(0, 50).map((n: string) => <option key={n} value={n} />)}</datalist>
              </>
            ) : (
              <input value={c.text} onChange={(e) => setCond(i, { text: e.target.value })} placeholder={t("Текст комментария", "Текст коментаря")} style={{ ...inp, flex: 1 }} />
            )}
            <button onClick={() => setR((x: any) => ({ ...x, conditions: x.conditions.filter((_: any, j: number) => j !== i) }))} style={{ border: "none", background: "none", color: "#dc2626", cursor: "pointer", fontSize: 15 }}><Icon n="🗑" size={15} /></button>
          </div>
        ))}
        <button className="btn btn-light" style={{ width: "100%", marginBottom: 16, borderStyle: "dashed" }} onClick={() => setR((x: any) => ({ ...x, conditions: [...x.conditions, { field: "osnd", op: "contains", text: "" }] }))}>＋ {t("Добавить ещё одно условие", "Додати ще одну умову")}</button>
        <b style={{ fontSize: 13, display: "block", marginBottom: 8 }}>{t("Что проставить, когда условие сработало", "Що проставити, коли умова спрацювала")}</b>
        {r.acts.map((a: any, i: number) => (
          <div key={i} style={{ display: "flex", gap: 7, marginBottom: 7, alignItems: "center" }}>
            <select value={a.type} onChange={(e) => setAct(i, { type: e.target.value, value: "" })} style={{ ...inp, width: 190 }}>
              {RULE_ACTS.filter(([k]) => k === a.type || !r.acts.some((x: any) => x.type === k)).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            {valueCtrl(a, i)}
            <button onClick={() => setR((x: any) => ({ ...x, acts: x.acts.filter((_: any, j: number) => j !== i) }))} style={{ border: "none", background: "none", color: "#dc2626", cursor: "pointer", fontSize: 15 }}><Icon n="🗑" size={15} /></button>
          </div>
        ))}
        {r.acts.length < RULE_ACTS.length && <button className="btn btn-light" style={{ width: "100%", marginBottom: 16, borderStyle: "dashed" }} onClick={() => { const used = r.acts.map((a: any) => a.type); const next = RULE_ACTS.find(([k]) => !used.includes(k)); if (next) setR((x: any) => ({ ...x, acts: [...x.acts, { type: next[0], value: "" }] })); }}>＋ {t("Добавить ещё одно действие", "Додати ще одну дію")}</button>}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-primary" disabled={busy} style={{ flex: 1 }} onClick={save}>{busy ? "…" : t("Сохранить", "Зберегти")}</button>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>{t("Отмена", "Скасувати")}</button>
          {rule?.id && <button className="btn btn-light" style={{ color: "#dc2626" }} onClick={async () => { if (confirm(t("Удалить правило?", "Видалити правило?"))) { await api.del(`/api/finance/bank-rules/${rule.id}/`); onSaved(); onClose(); } }}>{t("Удалить", "Видалити")}</button>}
        </div>
      </div>
    </div>
  );
}

function SuggestModal({ t, onClose, onCreated }: any) {
  const [items, setItems] = useState<any[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get<any>("/api/finance/bank-rules/suggest/").then((d) => {
      const rows = d.results || d;
      setItems(rows);
      setSel(new Set(rows.map((_: any, i: number) => i)));
    }).catch(() => setItems([]));
  }, []);
  async function create() {
    if (!items) return;
    const chosen = items.filter((_: any, i: number) => sel.has(i));
    if (!chosen.length) { alert(t("Ничего не выбрано", "Нічого не обрано")); return; }
    setBusy(true);
    try {
      const r: any = await api.post("/api/finance/bank-rules/suggest-create/", { items: chosen });
      alert(t(`Создано правил: ${r.created}`, `Створено правил: ${r.created}`));
      onCreated(); onClose();
    } catch (e: any) { alert(e?.response?.data?.detail || "Помилка"); }
    setBusy(false);
  }
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 85 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 16, padding: 22, width: "min(820px,96vw)", maxHeight: "90vh", display: "flex", flexDirection: "column" }}>
        <h3 style={{ margin: "0 0 4px" }}><Icon n="🤖" size={18} /> {t("Правила из истории (перенос из ФинМапа)", "Правила з історії (перенос із ФінМапа)")}</h3>
        <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
          {t("Анализ всех операций 2021–2026: повторяющийся контрагент → категория, которую он получал в 80%+ случаев. Это и есть правила ФинМапа, восстановленные из его же разноски. Сними галочки с лишних и создай.",
             "Аналіз усіх операцій 2021–2026: повторюваний контрагент → категорія, яку він отримував у 80%+ випадків. Це і є правила ФінМапа, відновлені з його ж рознесення. Зніми галочки із зайвих і створи.")}
        </div>
        {items === null ? <div className="spin">{t("Анализирую 20 000 операций…", "Аналізую 20 000 операцій…")}</div> : (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
              <b style={{ fontSize: 13 }}>{t("Найдено:", "Знайдено:")} {items.length}</b>
              <button className="btn btn-light" style={{ height: 26, fontSize: 11.5 }} onClick={() => setSel(new Set(items.map((_: any, i: number) => i)))}>{t("выбрать все", "обрати всі")}</button>
              <button className="btn btn-light" style={{ height: 26, fontSize: 11.5 }} onClick={() => setSel(new Set())}>{t("снять все", "зняти всі")}</button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", border: "1px solid #eef2f7", borderRadius: 10 }}>
              <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
                <thead><tr className="muted" style={{ fontSize: 11, textAlign: "left", position: "sticky", top: 0, background: "#f8fafc" }}>
                  <th style={{ padding: "6px" }}></th><th style={{ padding: "6px" }}>{t("Контрагент содержит", "Контрагент містить")}</th>
                  <th style={{ padding: "6px" }}>{t("Тип", "Тип")}</th><th style={{ padding: "6px" }}>→ {t("Категория", "Категорія")}</th>
                  <th style={{ padding: "6px" }}>→ {t("Направление", "Напрямок")}</th><th style={{ padding: "6px", textAlign: "right" }}>{t("Операций", "Операцій")}</th>
                  <th style={{ padding: "6px", textAlign: "right" }}>{t("Совпадение", "Збіг")}</th>
                </tr></thead>
                <tbody>
                  {items.map((it: any, i: number) => (
                    <tr key={i} onClick={() => { const n = new Set(sel); n.has(i) ? n.delete(i) : n.add(i); setSel(n); }}
                      style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer", background: sel.has(i) ? "#f0f9ff" : "transparent" }}>
                      <td style={{ padding: "5px 6px" }}><input type="checkbox" readOnly checked={sel.has(i)} /></td>
                      <td style={{ padding: "5px 6px", fontWeight: 600 }}>{it.counterparty}</td>
                      <td style={{ padding: "5px 6px" }}>{it.direction === "in" ? "▲ дохід" : "▼ витрата"}</td>
                      <td style={{ padding: "5px 6px" }}>{it.category_name || "—"}</td>
                      <td style={{ padding: "5px 6px" }}>{it.fin_direction_name || "—"}</td>
                      <td style={{ padding: "5px 6px", textAlign: "right" }}>{it.count}</td>
                      <td style={{ padding: "5px 6px", textAlign: "right", color: it.share >= 95 ? "#16a34a" : "#d97706", fontWeight: 700 }}>{it.share}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!items.length && <div className="muted" style={{ padding: 10, fontSize: 12 }}>{t("Новых закономерностей не найдено — всё уже покрыто правилами.", "Нових закономірностей не знайдено — все вже покрито правилами.")}</div>}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button className="btn btn-primary" disabled={busy || !items.length} style={{ flex: 1 }} onClick={create}>{busy ? "…" : "✓ " + t(`Создать выбранные (${sel.size})`, `Створити обрані (${sel.size})`)}</button>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>{t("Отмена", "Скасувати")}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function RulesTab({ cats, dirs, t }: any) {
  const [rules, setRules] = useState<any[]>([]);
  const [arts, setArts] = useState<any[]>([]);
  const [edit, setEdit] = useState<any>(undefined); // undefined = закрыто, null = новое, obj = правка
  const [busyAJ, setBusyAJ] = useState(false);
  const [suggest, setSuggest] = useState(false);
  const load = () => api.get<any>("/api/finance/bank-rules/").then((d) => setRules(d.results || d)).catch(() => {});
  const [accsR, setAccsR] = useState<any[]>([]);
  const [cps, setCps] = useState<string[]>([]);
  useEffect(() => {
    load();
    api.get<any>("/api/finmodel-articles/?page_size=300").then((d) => setArts(d.results || d)).catch(() => {});
    api.get<any>("/api/accounts/").then((d) => setAccsR((d.results || d).filter((a: any) => a.is_active !== false))).catch(() => {});
    api.get<any>("/api/finance/counterparties/").then((d) => setCps(((d.results || d) as any[]).map((x: any) => x.name || String(x)).filter(Boolean))).catch(() => {});
  }, []);
  const fLab = Object.fromEntries(RULE_FIELDS);
  const oLab = Object.fromEntries(RULE_OPS);
  async function applyJournal() {
    setBusyAJ(true);
    try {
      const prev: any = await api.post("/api/finance/bank-rules/apply-journal/", { dry: 1 });
      if (prev.changed === 0) { alert(t("Правилам нечего заполнить — все поля уже проставлены.", "Правилам нема чого заповнити — всі поля вже проставлені.")); setBusyAJ(false); return; }
      if (!confirm(t(`Правила заполнят ПУСТЫЕ поля у ${prev.changed} операций журнала (ничего не перезаписывается). Продолжить?`, `Правила заповнять ПОРОЖНІ поля у ${prev.changed} операцій журналу (нічого не перезаписується). Продовжити?`))) { setBusyAJ(false); return; }
      const r: any = await api.post("/api/finance/bank-rules/apply-journal/", { dry: 0 });
      alert(t(`Готово: обновлено ${r.changed} операций.`, `Готово: оновлено ${r.changed} операцій.`));
      load();
    } catch (e: any) { alert(e?.response?.data?.detail || "Помилка"); }
    setBusyAJ(false);
  }
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>
        {t("Автоправила: условие по комментарию/контрагенту/счёту → категория, проект, фонд, контрагент, канал. Срабатывают при синке банков, заливке периода и импорте выписок. Первое совпавшее правило — по порядку списка.",
           "Автоправила: умова за коментарем/контрагентом/рахунком → категорія, проект, фонд, контрагент, канал. Спрацьовують при синхронізації банків, заливці періоду та імпорті виписок. Перше правило, що збіглося — за порядком списку.")}
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button className="btn btn-primary" onClick={() => setEdit(null)}><Icon n="➕" size={14} /> {t("Добавить правило", "Додати правило")}</button>
        <button className="btn btn-light" disabled={busyAJ} onClick={applyJournal}>{busyAJ ? "…" : <><Icon n="⚡" size={14} /> {t("Прогнать по журналу", "Прогнати по журналу")}</>}</button>
        <button className="btn btn-light" onClick={() => setSuggest(true)}><Icon n="🤖" size={14} /> {t("Подобрать из истории", "Підібрати з історії")}</button>
      </div>
      {rules.map((r: any) => (
        <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 10px", borderTop: "1px solid #f1f5f9", opacity: r.active ? 1 : 0.55 }}>
          <div style={{ flex: 1, minWidth: 0, cursor: "pointer" }} onClick={() => setEdit(r)}>
            <div style={{ fontSize: 13.5, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.name || "(без назви)"}</div>
            <div className="muted" style={{ fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {(r.direction === "in" ? "▲ дохід · " : r.direction === "out" ? "▼ витрата · " : r.direction === "transfer" ? "⇄ переказ · " : "")}
              {(r.conditions || []).map((c: any) => `${fLab[c.field] || c.field} ${oLab[c.op] || c.op} «${c.text}»`).join(r.logic === "and" ? " І " : " АБО ")}
            </div>
          </div>
          {r.hits > 0 && <span title={t("Сколько раз сработало", "Скільки разів спрацювало")} style={{ fontSize: 10.5, fontWeight: 700, color: "#2563eb", background: "#eff6ff", borderRadius: 7, padding: "2px 8px", flexShrink: 0 }}><Icon n="⚡" size={12} /> {r.hits}</span>}
          <span className={"toggle" + (r.active ? " on" : "")} onClick={async () => { await api.patch(`/api/finance/bank-rules/${r.id}/`, { active: !r.active }); load(); }} style={{ flexShrink: 0 }} />
          <button onClick={() => setEdit(r)} style={{ border: "none", background: "none", cursor: "pointer", fontSize: 14, flexShrink: 0 }}><Icon n="✏️" size={14} /></button>
        </div>
      ))}
      {!rules.length && <div className="muted" style={{ fontSize: 12, padding: 8 }}>{t("Правил пока нет.", "Правил поки немає.")}</div>}
      {edit !== undefined && <RuleEditor rule={edit} cats={cats} dirs={dirs} arts={arts} accsR={accsR} cps={cps} t={t} onClose={() => setEdit(undefined)} onSaved={load} />}
      {suggest && <SuggestModal t={t} onClose={() => setSuggest(false)} onCreated={load} />}
    </div>
  );
}

function BankHubModal({ onClose }: { onClose: () => void }) {
  /* Налаштування інтеграцій: банки по API (Приват/Моно), правила розноски, історія завантажень (відкат), рахунки. */
  const { t } = useLang();
  const [tab, setTab] = useState<"banks" | "rules" | "hist" | "accs">("banks");
  const [banks, setBanks] = useState<any>(null);
  const [rules, setRules] = useState<any[]>([]);
  const [hist, setHist] = useState<any[]>([]);
  const [accs, setAccs] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [dirs, setDirs] = useState<any[]>([]);
  const [pbForm, setPbForm] = useState<any>({ token: "", acc: "", account_id: "" });
  const [monoForm, setMonoForm] = useState<any>({ token: "", account_id: "" });
  const [period, setPeriod] = useState<any>({ from: "", to: "" });
  const [busy, setBusy] = useState("");
  const [newRule, setNewRule] = useState<any>({ field: "osnd", contains: "", direction: "", set_category: "", set_fin_direction: "", set_counterparty: "" });
  const [bankAccs, setBankAccs] = useState<any>({ privatbank: null, monobank: null });
  const [loadingBA, setLoadingBA] = useState("");
  async function loadBankAccs(prov: string) {
    setLoadingBA(prov);
    try {
      const d = await api.get<any>(`/api/transactions/bank-accounts/?provider=${prov}`);
      setBankAccs((b: any) => ({ ...b, [prov]: d }));
    } catch (e: any) { alert(e?.response?.data?.detail || "Помилка"); }
    setLoadingBA("");
  }
  async function mapBank(prov: string, key: string, val: string) {
    try {
      if (val === "__new__") {
        const nm = prompt(t("Название нового счёта в CRM", "Назва нового рахунку в CRM"));
        if (!nm) return;
        await api.post("/api/transactions/bank-map/", { provider: prov, key, create_name: nm });
        api.get<any>("/api/accounts/").then((d) => setAccs(d.results || d)).catch(() => {});
      } else {
        await api.post("/api/transactions/bank-map/", { provider: prov, key, account_id: val ? Number(val) : null });
      }
      loadBankAccs(prov);
    } catch (e: any) { alert(e?.response?.data?.detail || "Помилка"); }
  }
  async function pullOne(prov: string, key: string) {
    if (!period.from || !period.to) { alert(t("Выбери период (внизу)", "Обери період (внизу)")); return; }
    setBusy(prov + key);
    try {
      const url = prov === "privatbank" ? "/api/transactions/privat-sync/" : "/api/transactions/mono-sync/";
      const body: any = { from: period.from, to: period.to };
      if (prov === "privatbank") body.acc = key; else body.account = key;
      const r: any = await api.post(url, body);
      alert(t("Загружено", "Завантажено") + `: ${r.created}, ` + t("дубликатов пропущено", "дублікатів пропущено") + `: ${r.skipped_existing}\n` + t("Партия", "Партія") + `: ${r.batch}`);
      loadAll();
    } catch (e: any) { alert(e?.response?.data?.detail || "Помилка"); }
    setBusy("");
  }
  const BankAccTable = ({ prov }: any) => {
    const rows = bankAccs[prov];
    if (rows === null) return null;
    return (
      <table style={{ width: "100%", fontSize: 12.5, marginTop: 10, borderCollapse: "collapse" }}>
        <thead><tr className="muted" style={{ fontSize: 11, textAlign: "left" }}>
          <th style={{ padding: "4px 6px" }}>{t("Счёт в банке", "Рахунок у банку")}</th>
          <th style={{ padding: "4px 6px" }}>{t("Остаток", "Залишок")}</th>
          <th style={{ padding: "4px 6px" }}>{t("→ Счёт в CRM (куда пишутся операции)", "→ Рахунок у CRM (куди пишуться операції)")}</th>
          <th style={{ padding: "4px 6px" }}></th>
        </tr></thead>
        <tbody>
          {rows.map((r: any) => (
            <tr key={r.key} style={{ borderTop: "1px solid #f1f5f9" }}>
              <td style={{ padding: "6px" }}>
                <b>…{r.tail}</b> {r.title && <span className="muted">· {r.title}</span>}
                <div className="muted" style={{ fontSize: 10.5 }}>{r.iban}</div>
              </td>
              <td style={{ padding: "6px", whiteSpace: "nowrap" }}><b>{r.balance}</b> {r.currency}</td>
              <td style={{ padding: "6px" }}>
                <select value={r.mapped_account_id || ""} onChange={(e) => mapBank(prov, r.key, e.target.value)} style={{ ...inp, minWidth: 220 }}>
                  <option value="">{t("— не подключён —", "— не підключено —")}</option>
                  {accs.filter((a: any) => a.is_active !== false).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  <option value="__new__">➕ {t("Создать новый счёт…", "Створити новий рахунок…")}</option>
                </select>
              </td>
              <td style={{ padding: "6px" }}>
                <button className="btn btn-light" disabled={busy !== "" || !r.mapped_account_id} title={!r.mapped_account_id ? t("Сначала выбери счёт CRM", "Спочатку обери рахунок CRM") : ""}
                  onClick={() => pullOne(prov, r.key)}>{busy === prov + r.key ? "…" : <><Icon n="📥" size={14} /> {t("Залить период", "Залити період")}</>}</button>
              </td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={4} className="muted" style={{ padding: 8 }}>{t("Банк не вернул счета", "Банк не повернув рахунки")}</td></tr>}
        </tbody>
      </table>
    );
  };
  const loadAll = () => {
    api.get<any>("/api/transactions/bank-settings/").then(setBanks).catch(() => {});
    api.get<any>("/api/finance/bank-rules/").then((d) => setRules(d.results || d)).catch(() => {});
    api.get<any>("/api/transactions/import-batches/").then((d) => setHist(d)).catch(() => {});
    api.get<any>("/api/accounts/").then((d) => setAccs(d.results || d)).catch(() => {});
    api.get<any>("/api/categories/?page_size=500").then((d) => setCats(d.results || d)).catch(() => {});
    api.get<any>("/api/fin-directions/?page_size=200").then((d) => setDirs(d.results || d)).catch(() => {});
  };
  useEffect(loadAll, []);
  const inp = { height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", fontSize: 13 } as any;
  async function saveBank(prov: string, extra: any) {
    try { await api.post("/api/transactions/bank-settings/", { provider: prov, ...extra }); loadAll(); alert(t("Сохранено ✓","Збережено ✓")); }
    catch (e: any) { alert(e?.response?.data?.detail || "Помилка"); }
  }
  async function pull(prov: string) {
    if (!period.from || !period.to) { alert(t("Выбери период","Обери період")); return; }
    setBusy(prov);
    try {
      const url = prov === "privatbank" ? "/api/transactions/privat-sync/" : "/api/transactions/mono-sync/";
      const r: any = await api.post(url, { from: period.from, to: period.to });
      alert(t("Загружено","Завантажено") + `: ${r.created}, ` + t("дубликатов","дублікатів") + `: ${r.skipped_existing}\n` + t("Партия","Партія") + `: ${r.batch}\n` + t("Откат — во вкладке «История»","Відкат — у вкладці «Історія»"));
      loadAll();
    } catch (e: any) { alert(e?.response?.data?.detail || "Помилка"); }
    setBusy("");
  }
  async function addRule() {
    if (!newRule.contains.trim()) return;
    try {
      await api.post("/api/finance/bank-rules/", { ...newRule,
        set_category: newRule.set_category || null, set_fin_direction: newRule.set_fin_direction || null });
      setNewRule({ field: "osnd", contains: "", direction: "", set_category: "", set_fin_direction: "", set_counterparty: "" });
      loadAll();
    } catch { alert("Помилка правила"); }
  }
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, padding: 22, width: "min(880px,96vw)", maxHeight: "90vh", overflow: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}><Icon n="⚙️" size={18} /> {t("Интеграции и правила","Інтеграції та правила")}</h3>
          <button className="btn btn-light" onClick={onClose}>✕</button>
        </div>
        <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
          {[["banks", "🏦", t("Банки","Банки")], ["rules", "🧭", t("Правила разноски","Правила рознесення")], ["hist", "🕓", t("История загрузок","Історія завантажень")], ["accs", "👁", t("Счета в учёте","Рахунки в обліку")]].map(([k, ic, l]) => (
            <button key={k} className={"btn" + (tab === k ? " btn-primary" : " btn-light")} onClick={() => setTab(k as any)}><Icon n={ic} size={14} /> {l}</button>
          ))}
        </div>

        {tab === "banks" && banks && (
          <>
            <div className="panel" style={{ margin: "0 0 12px" }}>
              <b>ПриватБанк (AutoClient · рахунок ФОП)</b> {banks.privatbank.connected ? <span style={{ color: "#16a34a", fontWeight: 700 }}>✓ {t("подключён","підключено")} {banks.privatbank.token_tail}</span> : <span className="muted">{t("не подключён","не підключено")}</span>}
              <div className="muted" style={{ fontSize: 12, margin: "4px 0 8px" }}>{t("Токен создаётся в Приват24 для бизнеса: Настройки → API AutoClient. Новые операции подтягиваются автоматически каждые 10 минут + можно загрузить период.","Токен створюється у Приват24 для бізнесу: Налаштування → API AutoClient. Нові операції підтягуються автоматично кожні 10 хвилин + можна завантажити період.")}</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <input placeholder="Token" value={pbForm.token} onChange={(e) => setPbForm({ ...pbForm, token: e.target.value })} style={{ ...inp, width: 220 }} />
                <input placeholder="IBAN (UA…)" value={pbForm.acc} onChange={(e) => setPbForm({ ...pbForm, acc: e.target.value })} style={{ ...inp, width: 220 }} />
                <select value={pbForm.account_id} onChange={(e) => setPbForm({ ...pbForm, account_id: e.target.value })} style={inp}>
                  <option value="">{t("— счёт в CRM —","— рахунок у CRM —")}</option>
                  {accs.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
                <button className="btn btn-primary" onClick={() => saveBank("privatbank", { ...(pbForm.token ? { token: pbForm.token } : {}), ...(pbForm.acc ? { acc: pbForm.acc } : {}), ...(pbForm.account_id ? { account_id: Number(pbForm.account_id) } : {}) })}>{t("Сохранить","Зберегти")}</button>
                <button className="btn btn-light" disabled={loadingBA !== ""} onClick={() => loadBankAccs("privatbank")}>{loadingBA === "privatbank" ? "…" : <><Icon n="🏦" size={14} /> {t("Показать счета банка","Показати рахунки банку")}</>}</button>
              </div>
              <BankAccTable prov="privatbank" />
            </div>
            <div className="panel" style={{ margin: "0 0 12px" }}>
              <b>Monobank (особисті картки)</b> {banks.monobank.connected ? <span style={{ color: "#16a34a", fontWeight: 700 }}>✓ {t("подключён","підключено")} {banks.monobank.token_tail}</span> : <span className="muted">{t("не подключён","не підключено")}</span>}
              <div className="muted" style={{ fontSize: 12, margin: "4px 0 8px" }}>{t("Токен: api.monobank.ua (вход через приложение mono). Лимит API: период до 31 дня за одну загрузку.","Токен: api.monobank.ua (вхід через застосунок mono). Ліміт API: період до 31 доби за одне завантаження.")}</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <input placeholder="X-Token" value={monoForm.token} onChange={(e) => setMonoForm({ ...monoForm, token: e.target.value })} style={{ ...inp, width: 220 }} />
                <select value={monoForm.account_id} onChange={(e) => setMonoForm({ ...monoForm, account_id: e.target.value })} style={inp}>
                  <option value="">{t("— счёт в CRM —","— рахунок у CRM —")}</option>
                  {accs.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
                <button className="btn btn-primary" onClick={() => saveBank("monobank", { ...(monoForm.token ? { token: monoForm.token } : {}), ...(monoForm.account_id ? { account_id: Number(monoForm.account_id) } : {}) })}>{t("Сохранить","Зберегти")}</button>
                <button className="btn btn-light" disabled={loadingBA !== ""} onClick={() => loadBankAccs("monobank")}>{loadingBA === "monobank" ? "…" : <><Icon n="🏦" size={14} /> {t("Показать счета и карты","Показати рахунки і картки")}</>}</button>
              </div>
              <BankAccTable prov="monobank" />
            </div>
            <div className="panel" style={{ margin: 0 }}>
              <b><Icon n="📥" size={14} /> {t("Загрузить операции за период","Завантажити операції за період")}</b>
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
                <input type="date" value={period.from} onChange={(e) => setPeriod({ ...period, from: e.target.value })} style={inp} />
                <span className="muted">—</span>
                <input type="date" value={period.to} onChange={(e) => setPeriod({ ...period, to: e.target.value })} style={inp} />
                <button className="btn btn-primary" disabled={busy !== ""} onClick={() => pull("privatbank")}>{busy === "privatbank" ? "…" : t("Загрузить из Привата","Завантажити з Привату")}</button>
                <button className="btn btn-light" disabled={busy !== ""} onClick={() => pull("monobank")}>{busy === "monobank" ? "…" : t("Загрузить из Mono","Завантажити з Mono")}</button>
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{t("Комиссия LiqPay по сделкам разносится автоматически в «Комиссия Банка». Переводы между своими счетами не попадают в расходы. Ошиблись — откатите партию во вкладке «История».","Комісія LiqPay за угодами розноситься автоматично у «Комиссия Банка». Перекази між своїми рахунками не потрапляють у витрати. Помилились — відкотіть партію у вкладці «Історія».")}</div>
            </div>
          </>
        )}

        {tab === "rules" && <RulesTab cats={cats} dirs={dirs} t={t} />}

        {tab === "hist" && (
          <div className="panel" style={{ margin: 0 }}>
            <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>{t("Каждая загрузка из банка/выписки = партия. Ошиблись — откатите: все операции партии удалятся.","Кожне завантаження з банку/виписки = партія. Помилились — відкотіть: усі операції партії видаляться.")}</div>
            {hist.length === 0 ? <div className="muted">{t("Загрузок ещё не было.","Завантажень ще не було.")}</div> :
            <table style={{ width: "100%", fontSize: 13 }}>
              <thead><tr className="muted" style={{ fontSize: 11, textAlign: "left" }}><th>{t("Партия","Партія")}</th><th>{t("Период операций","Період операцій")}</th><th style={{ textAlign: "right" }}>{t("Операций","Операцій")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th><th></th></tr></thead>
              <tbody>{hist.map((h: any) => (
                <tr key={h.batch} style={{ borderTop: "1px solid #f1f5f9" }}>
                  <td><b>{h.batch}</b></td>
                  <td className="muted">{h.from} — {h.to}</td>
                  <td style={{ textAlign: "right" }}>{h.count}</td>
                  <td style={{ textAlign: "right" }}>{money(h.total)}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn-light" style={{ padding: "3px 10px", color: "#dc2626" }} onClick={async () => {
                      if (!confirm(t("Откатить партию","Відкотити партію") + ` ${h.batch}? ` + t("Удалится операций","Видалиться операцій") + `: ${h.count}`)) return;
                      const r: any = await api.del(`/api/transactions/import-batches/?batch=${encodeURIComponent(h.batch)}`);
                      alert(t("Откачено","Відкочено") + `: ${r.rolled_back}`); loadAll();
                    }}>↩ {t("Откатить","Відкотити")}</button>
                  </td>
                </tr>
              ))}</tbody>
            </table>}
          </div>
        )}

        {tab === "accs" && (
          <div className="panel" style={{ margin: 0 }}>
            <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>{t("Выключенные счета скрываются из журнала, дашборда и «Деньги на счетах». Операции не удаляются.","Вимкнені рахунки ховаються з журналу, дашборда та «Гроші на рахунках». Операції не видаляються.")}</div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 700, padding: "4px 0 8px", borderBottom: "2px solid #e2e8f0" }}>
              <span>{t("Итого по активным","Разом по активних")} ({accs.filter((a: any) => a.is_active !== false).length})</span>
              <span style={{ color: "#0ea5e9" }}>{money2(accs.filter((a: any) => a.is_active !== false).reduce((sm: number, a: any) => sm + Number(a.balance || 0), 0))}</span>
            </div>
            {accs.map((a: any, ai: number) => (
              <div key={a.id} onClick={() => {
                const nv = !(a.is_active !== false);
                setAccs((prev) => prev.map((x: any) => x.id === a.id ? { ...x, is_active: nv } : x));  // одразу
                api.patch(`/api/accounts/${a.id}/`, { is_active: nv }).catch((e: any) => {
                  setAccs((prev) => prev.map((x: any) => x.id === a.id ? { ...x, is_active: !nv } : x));  // відкат
                  alert(e?.response?.data?.detail || t("Не удалось сохранить","Не вдалося зберегти"));
                });
              }} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", borderBottom: "1px solid #f8fafc", fontSize: 13, cursor: "pointer", userSelect: "none" }}>
                <input type="checkbox" readOnly checked={a.is_active !== false} style={{ pointerEvents: "none" }} />
                <span style={{ flex: 1, opacity: a.is_active === false ? 0.5 : 1 }}>{a.name}</span>
                <b className="muted">{money2(a.balance)}</b>
                <span onClick={(e) => { e.stopPropagation(); if (ai === 0) return;
                  const nx = [...accs]; [nx[ai - 1], nx[ai]] = [nx[ai], nx[ai - 1]]; setAccs(nx);
                  api.post("/api/accounts/reorder/", { ids: nx.map((x: any) => x.id) }).catch(() => {});
                }} title={t("Выше","Вище")} style={{ cursor: ai === 0 ? "default" : "pointer", opacity: ai === 0 ? 0.25 : 0.7, padding: "0 3px" }}>▲</span>
                <span onClick={(e) => { e.stopPropagation(); if (ai === accs.length - 1) return;
                  const nx = [...accs]; [nx[ai + 1], nx[ai]] = [nx[ai], nx[ai + 1]]; setAccs(nx);
                  api.post("/api/accounts/reorder/", { ids: nx.map((x: any) => x.id) }).catch(() => {});
                }} title={t("Ниже","Нижче")} style={{ cursor: ai === accs.length - 1 ? "default" : "pointer", opacity: ai === accs.length - 1 ? 0.25 : 0.7, padding: "0 3px" }}>▼</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Journal() {
  const { t } = useLang();
  const nav = useNav();
  const cpMap = useCpMap();
  const [tx, setTx] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [arts, setArts] = useState<any[]>([]);
  const [dirs, setDirs] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const blank = { id: 0, direction: "out", amount: "", account: 0, transfer_account: 0, transfer_amount: "", fin_article: 0, fin_direction: 0, channel: "", counterparty: "", set_category: "", currency: "UAH", rate: 1, comment: "", date: "", deal: 0, deal_title: "", contact: 0, contact_name: "" };
  const [f, setF] = useState<any>(blank);
  const [splitOn, setSplitOn] = useState(false);
  const [payerDir, setPayerDir] = useState(0);
  const [splitRows, setSplitRows] = useState<any[]>([]);
  const [ff, setFf] = useState(""); const [ft, setFt] = useState(""); const [fq, setFq] = useState("");
  const [searchOpen, setSearchOpen] = useState(false); const [accOpen, setAccOpen] = useState(false);
  const [actMenu, setActMenu] = useState(false);
  const mrow: any = { display: "flex", alignItems: "center", gap: 10, padding: "11px 12px", background: "transparent", border: "none", borderRadius: 8, fontSize: 15, fontWeight: 600, color: "#1e293b", cursor: "pointer", textAlign: "left", width: "100%" };
  const [page, setPage] = useState(1); const [pageSize, setPageSize] = useState(50); const [count, setCount] = useState(0);
  const { can: canJ } = useAuth();
  const canTx = canJ("finance.tx.edit") || canJ("roles.manage");
  const canTotal = canJ("finance.balance.total") || canJ("roles.manage");
  const [lock, setLock] = useState<{ closed_until: string | null; can_close: boolean }>({ closed_until: null, can_close: false });
  useEffect(() => { api.get<any>("/api/transactions/period-lock/").then(setLock).catch(() => {}); }, []);
  async function setPeriodLock() {
    const v = prompt(t("Закрыть период ДО даты (включительно), формат ГГГГ-ММ-ДД. Пусто — снять закрытие.", "Закрити період ДО дати (включно), формат РРРР-ММ-ДД. Порожньо — зняти закриття."), lock.closed_until || "");
    if (v === null) return;
    try {
      const r: any = await api.post("/api/transactions/period-lock/", { closed_until: v.trim() || null });
      setLock(r);
      alert(r.closed_until ? t("Период закрыт до ", "Період закрито до ") + r.closed_until : t("Закрытие снято", "Закриття знято"));
    } catch (e: any) { alert(e?.response?.data?.detail || "Помилка"); }
  }
  // ширини колонок журналу (тягнеться за праву грань заголовка, зберігається)
  const JCOL_DEF = [95, 95, 50, 90, 190, 190, 150, 140, 130, 140, 95, 300];
  const [colW, setColW] = useState<number[]>(() => {
    try { const v = JSON.parse(localStorage.getItem("fin_journal_cols") || "null"); if (Array.isArray(v) && v.length === 12) return v; } catch (e) { /* noop */ }
    return JCOL_DEF;
  });
  const startColResize = (i: number) => (e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX; const w0 = colW[i];
    function mv(ev: MouseEvent) {
      setColW((prev) => { const nx = prev.slice(); nx[i] = Math.max(50, w0 + (ev.clientX - startX)); return nx; });
    }
    function up() {
      window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up);
      setColW((prev) => { try { localStorage.setItem("fin_journal_cols", JSON.stringify(prev)); } catch (er) { /* noop */ } return prev; });
    }
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  };
  const [showCols, setShowCols] = useState(false);
  const emptyCf = { direction: "", amount_min: "", amount_max: "", currency: "", cat: "", cp: "", account: "", fin_article: "", fin_direction: "", channel: "", comment: "" };
  const [cf, setCf] = useState<any>(emptyCf);
  const [selAcc, setSelAcc] = useState<number[]>([]);
  const [drawerDeal, setDrawerDeal] = useState<number | null>(null);
  const loadAccs = () => api.get<any>("/api/accounts/").then((d) => setAccounts((d.results || d).filter((a: any) => a.is_active !== false)));
  const load = (p = page) => {
    const qp = new URLSearchParams({ page: String(p), page_size: String(pageSize) });
    if (ff) qp.set("from", ff); if (ft) qp.set("to", ft); if (fq.trim()) qp.set("q", fq.trim());
    Object.entries(cf).forEach(([k, v]) => { if (v) qp.set(k, String(v)); });
    if (selAcc.length) qp.set("accounts", selAcc.join(","));
    if (fContact) qp.set("contact", String(fContact));
    qp.set("sort", sortF);
    return api.get<any>(`/api/transactions/?${qp.toString()}`).then((d) => { setTx(d.results || d); setCount(d.count ?? (d.results ? d.results.length : (d.length || 0))); });
  };
  function apply() { setPage(1); load(1); }
  const [bankHub, setBankHub] = useState(false);
  const [sortF, setSortF] = useState("-date");
  const [selTx, setSelTx] = useState<Record<number, boolean>>({});
  const isMobile = useIsMobile();
  const [bulkField, setBulkField] = useState("category");
  const [bulkVal, setBulkVal] = useState<any>("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const selCount = Object.values(selTx).filter(Boolean).length;
  async function applyBulk() {
    const ids = Object.entries(selTx).filter(([, v]) => v).map(([k]) => Number(k));
    if (!ids.length || bulkBusy) return;
    const v = bulkField === "counterparty" || bulkField === "comment" || bulkField === "channel" || bulkField === "currency" ? bulkVal : (Number(bulkVal) || null);
    setBulkBusy(true);
    try {
      await api.post("/api/transactions/bulk-edit/", { ids, set: { [bulkField]: v } });
      setBulkVal("");
      load(page); loadAccs();
    } catch (e: any) { alert(e?.response?.data?.detail || "Помилка"); }
    finally { setBulkBusy(false); }
  }
  const [fContact, setFContact] = useState(() => Number(new URLSearchParams(window.location.search).get("client")) || 0);
  const [fContactName, setFContactName] = useState(() => new URLSearchParams(window.location.search).get("cname") || "");
  useEffect(() => { if (fContact || fContactName === "") { setPage(1); load(1); } /* eslint-disable-next-line */ }, [fContact]);
  const [accW, setAccW] = useState(() => Number(localStorage.getItem("fin_acc_w")) || 220);
  const [accCollapsed, setAccCollapsed] = useState(() => localStorage.getItem("fin_acc_collapsed") === "1");
  function startAccResize(e: React.MouseEvent) {
    e.preventDefault();
    const sx = e.clientX, sw = accW;
    const mv = (ev: MouseEvent) => { const w = Math.max(170, Math.min(480, sw + ev.clientX - sx)); setAccW(w); localStorage.setItem("fin_acc_w", String(w)); };
    const up = () => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); document.body.style.cursor = ""; };
    document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up); document.body.style.cursor = "col-resize";
  }
  function goPage(p: number) { setPage(p); load(p); }
  const bulkPanel = selCount > 0 ? (
    <div style={{ position: "fixed", left: 0, right: 0, bottom: 0, background: "#26201B", color: "#fff", padding: "10px 18px", zIndex: 60, boxShadow: "0 -8px 30px rgba(0,0,0,.3)" }}>
      <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <b>{t("Выбрано","Вибрано")}: {selCount}</b>
        <select value={bulkField} onChange={(e) => { setBulkField(e.target.value); setBulkVal(""); }} style={{ padding: "7px 10px", borderRadius: 8, border: "none", fontSize: 13 }}>
          <option value="category">{t("Категория","Категорія")}</option>
          <option value="counterparty">{t("Контрагент","Контрагент")}</option>
          <option value="account">{t("Счёт","Рахунок")}</option>
          <option value="deal">{t("Угода (№)","Угода (№)")}</option>
          <option value="fin_article">{t("Фонд","Фонд")}</option>
          <option value="fin_direction">{t("Направление","Напрямок")}</option>
          <option value="channel">{t("Канал","Канал")}</option>
          <option value="comment">{t("Комментарий","Коментар")}</option>
          <option value="currency">{t("Валюта","Валюта")}</option>
        </select>
        {bulkField === "category" && (
          <select value={bulkVal} onChange={(e) => setBulkVal(e.target.value)} style={{ padding: "7px 10px", borderRadius: 8, border: "none", fontSize: 13, maxWidth: 300 }}>
            <option value="">{t("— выбери категорию —","— обери категорію —")}</option>
            {cats.filter((c: any) => !c.hidden).map((c: any) => <option key={c.id} value={c.id}>{c.direction === "in" ? "▲ " : "▼ "}{c.parent ? "└ " : ""}{c.name.slice(0, 42)}</option>)}
          </select>)}
        {bulkField === "account" && (
          <select value={bulkVal} onChange={(e) => setBulkVal(e.target.value)} style={{ padding: "7px 10px", borderRadius: 8, border: "none", fontSize: 13, maxWidth: 280 }}>
            <option value="">{t("— выбери счёт —","— обери рахунок —")}</option>
            {accounts.map((a: any) => <option key={a.id} value={a.id}>{a.name.slice(0, 40)}</option>)}
          </select>)}
        {bulkField === "fin_article" && (
          <select value={bulkVal} onChange={(e) => setBulkVal(e.target.value)} style={{ padding: "7px 10px", borderRadius: 8, border: "none", fontSize: 13, maxWidth: 300 }}>
            <option value="">{t("— без фонда —","— без фонду —")}</option>
            {FUND_GROUPS_G.map(([gk, gl]) => { const gr = arts.filter((a: any) => a.category === gk && !a.parent); return gr.length ? <optgroup key={gk} label={gl}>{gr.map((a: any) => <option key={a.id} value={a.id}>{a.name.slice(0, 40)}</option>)}</optgroup> : null; })}
          </select>)}
        {bulkField === "fin_direction" && (
          <select value={bulkVal} onChange={(e) => setBulkVal(e.target.value)} style={{ padding: "7px 10px", borderRadius: 8, border: "none", fontSize: 13, maxWidth: 260 }}>
            <option value="">{t("— без направления —","— без напрямку —")}</option>
            {dirs.map((d: any) => <option key={d.id} value={d.id}>{d.name.slice(0, 36)}</option>)}
          </select>)}
        {bulkField === "channel" && (
          <select value={bulkVal} onChange={(e) => setBulkVal(e.target.value)} style={{ padding: "7px 10px", borderRadius: 8, border: "none", fontSize: 13 }}>
            {CHANNELS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>)}
        {bulkField === "currency" && (
          <select value={bulkVal} onChange={(e) => setBulkVal(e.target.value)} style={{ padding: "7px 10px", borderRadius: 8, border: "none", fontSize: 13 }}>
            <option value="">—</option>
            {["UAH", "USD", "EUR", "PLN", "GBP"].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>)}
        {(bulkField === "counterparty" || bulkField === "comment" || bulkField === "deal") && (
          <input value={bulkVal} onChange={(e) => setBulkVal(e.target.value)} placeholder={bulkField === "deal" ? t("№ сделки (пусто — отвязать)","№ угоди (порожньо — відвʼязати)") : t("Новое значение","Нове значення")} style={{ padding: "7px 10px", borderRadius: 8, border: "none", fontSize: 13, minWidth: 220 }} />)}
        <button disabled={bulkBusy || (bulkVal === "" && !["counterparty", "comment", "deal", "fin_article", "fin_direction"].includes(bulkField))} onClick={applyBulk}
          style={{ padding: "8px 18px", borderRadius: 9, border: "none", fontWeight: 700, fontSize: 13, cursor: "pointer", background: "#C67D5F", color: "#fff", opacity: bulkBusy ? 0.6 : 1 }}>
          {bulkBusy ? "…" : "✓ " + t("Применить к выбранным","Застосувати до вибраних")}
        </button>
        <button onClick={() => setSelTx({})} style={{ padding: "8px 14px", borderRadius: 9, border: "1px solid #5a5047", background: "transparent", color: "#cbbfb4", fontSize: 13, cursor: "pointer" }}>{t("снять выделение","зняти виділення")}</button>
      </div>
    </div>
  ) : null;
  function resetAll() { setFq(""); setFf(""); setFt(""); setCf(emptyCf); setFContact(0); setFContactName(""); setPage(1); setTimeout(() => load(1), 0); }
  useEffect(() => {
    load(1);
    loadAccs();
    api.get<any>("/api/finmodel-articles/?page_size=200").then((d) => setArts(d.results || d));
    api.get<any>("/api/fin-directions/?page_size=100").then((d) => setDirs(d.results || d));
    api.get<any>("/api/categories/?page_size=500").then((d) => setCats(d.results || d)).catch(() => setCats([]));
    // deep-link: /fin?tab=journal&tx=<id> — відкрити конкретну операцію
    const txId = new URLSearchParams(window.location.search).get("tx");
    if (txId) {
      api.get<any>(`/api/transactions/${txId}/`).then((t0) => { if (t0 && t0.id) openEdit(t0); }).catch(() => {});
    }
    // deep-link: /finance?tab=journal&newop=in|out&contact=<id>&cname=<name> — нова операція з картки клієнта (та сама повна картка)
    const _sp = new URLSearchParams(window.location.search);
    const _np = _sp.get("newop");
    if (_np === "in" || _np === "out") {
      openNew(_np);
      const _cid = Number(_sp.get("contact")) || 0;
      const _cnm = _sp.get("cname") || "";
      if (_cid) setTimeout(() => setF((x: any) => ({ ...x, contact: _cid, contact_name: _cnm })), 30);
    }
  }, []);
  useEffect(() => { load(1); setPage(1); }, [pageSize]);
  useEffect(() => { setPage(1); load(1); /* eslint-disable-next-line */ }, [sortF]);
  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  const [convAcc, setConvAcc] = useState(0);
  const [asDebt, setAsDebt] = useState(false);
  async function toTransfer() {
    if (!f.id || !convAcc) return;
    const body: any = { direction: "transfer", category: null, fin_article: null, fin_direction: null, channel: "" };
    if (f.direction === "out") { body.account = f.account; body.transfer_account = convAcc; }
    else { body.account = convAcc; body.transfer_account = f.account; }
    await api.patch(`/api/transactions/${f.id}/`, body);
    setConvAcc(0); setOpen(false); load(page); loadAccs();
  }
  function openNew(direction: string) { setF({ ...blank, direction, date: new Date().toISOString().slice(0, 10) }); setConvAcc(0); setAsDebt(false); setSplitOn(false); setSplitRows([]); setPayerDir(0); setOpen(true); }
  function openEdit(t: any) {
    setF({ id: t.id, direction: t.direction, amount: t.amount, account: t.account || 0, fin_article: t.fin_article || 0, fin_direction: t.fin_direction || 0,
      transfer_account: t.transfer_account || 0, transfer_amount: (t as any).transfer_amount || "", channel: t.channel || "", counterparty: t.counterparty || "", set_category: t.category_name || "", currency: t.currency || "UAH", rate: t.rate || 1, comment: t.comment || "", date: t.date || "", deal: (t as any).deal || 0, deal_title: (t as any).deal_title || "", contact: (t as any).contact || 0, contact_name: (t as any).contact_name || "" });
    setSplitOn(((t as any).splits || []).length > 0);
    setSplitRows(((t as any).splits || []).map((sp: any) => ({ dir: sp.fin_direction || 0, amt: sp.amount })));
    setPayerDir((t as any).payer_direction || 0);
    setOpen(true);
  }
  async function fetchRate(ccy: string) {
    if (ccy === "UAH") { setF((x: any) => ({ ...x, currency: ccy, rate: 1 })); return; }
    setF((x: any) => ({ ...x, currency: ccy }));
    try { const r = await api.get<any>(`/api/finance/fx-rate/?ccy=${ccy}`); if (r.rate) setF((x: any) => ({ ...x, rate: r.rate })); } catch { /* лишаємо поточний */ }
  }
  async function save() {
    const _amt = Number(String(f.amount).replace(",", "."));
    if (!_amt) return;
    if (splitOn) {
      if (!payerDir) { alert(t("Выбери подразделение, чья касса оплатила", "Обери підрозділ, чия каса сплатила")); return; }
      const _ss = splitRows.reduce((a: number, r: any) => a + (Number(r.amt) || 0), 0);
      if (Math.abs(_ss - _amt) > 0.01) { alert(t("Сумма распределения не равна сумме операции", "Сума розподілу не дорівнює сумі операції")); return; }
    }
    if (!f.id && f.direction === "out" && asDebt) {
      const catId = (cats.find((cc: any) => cc.name === f.set_category) || {}).id || null;
      await api.post("/api/planned-payments/", { kind: "payable", amount: _amt,
        due_date: f.date || new Date().toISOString().slice(0, 10), counterparty: f.counterparty,
        contact: (f as any).contact || null, category: catId, account: f.account || null,
        fin_article: f.fin_article || null, fin_direction: f.fin_direction || null, comment: f.comment });
      setAsDebt(false); setOpen(false); load(page);
      return;
    }
    const isT = f.direction === "transfer";
    const body: any = { direction: f.direction, amount: _amt, account: f.account || accounts[0]?.id,
      comment: f.comment, currency: f.currency, rate: Number(f.rate) || 1 };
    if (f.date) body.date = f.date;
    if (isT) {
      if (!f.transfer_account || f.transfer_account === f.account) { alert("Оберіть інший рахунок-отримувач"); return; }
      body.transfer_account = f.transfer_account; body.transfer_amount = f.transfer_amount ? Number(String(f.transfer_amount).replace(",", ".")) : null; body.fin_article = null; body.fin_direction = null;
    } else {
      body.channel = f.channel; body.counterparty = f.counterparty; body.set_category = f.set_category;
      body.fin_article = f.fin_article || null; body.fin_direction = f.fin_direction || null; body.transfer_account = null; body.transfer_amount = null;
      body.contact = (f as any).contact || null;
      body.deal = (f as any).deal || null;
      body.payer_direction = splitOn ? (payerDir || null) : null;
      body.splits = splitOn ? splitRows.filter((r: any) => r.dir && Number(r.amt)).map((r: any) => ({ fin_direction: r.dir, set_category: f.set_category, amount: Number(r.amt) })) : [];
    }
    if (f.id) await api.patch(`/api/transactions/${f.id}/`, body);
    else await api.post("/api/transactions/", body);
    setOpen(false); setF(blank); load(); loadAccs();
  }
  async function del() {
    if (!f.id || !confirm("Видалити цю операцію?")) return;
    await api.del(`/api/transactions/${f.id}/`); setOpen(false); setF(blank); load(); loadAccs();
  }
  const inp = { height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", width: "100%", marginBottom: 10 } as React.CSSProperties;
  const grnEq = Number(f.amount || 0) * (Number(f.rate) || 1);

  function toggleAcc(id: number) {
    setSelAcc((cur) => { const n = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]; setTimeout(() => { setPage(1); const qp = new URLSearchParams({ page: "1", page_size: String(pageSize) }); if (ff) qp.set("from", ff); if (ft) qp.set("to", ft); if (fq.trim()) qp.set("q", fq.trim()); Object.entries(cf).forEach(([k, v]) => { if (v) qp.set(k, String(v)); }); if (n.length) qp.set("accounts", n.join(",")); api.get<any>(`/api/transactions/?${qp.toString()}`).then((d) => { setTx(d.results || d); setCount(d.count ?? 0); }); }, 0); return n; });
  }
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      <div className="panel acc-sidebar" style={{ width: accCollapsed ? 40 : accW, flex: `0 0 ${accCollapsed ? 40 : accW}px`, margin: 0, maxHeight: "80vh", overflowY: accCollapsed ? "hidden" : "auto", padding: accCollapsed ? "10px 4px" : undefined }}>
        {accCollapsed ? (
          <div onClick={() => { setAccCollapsed(false); localStorage.setItem("fin_acc_collapsed", "0"); }} title={t("Развернуть счета","Розгорнути рахунки")} style={{ cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 8, color: "#64748b", fontWeight: 700 }}>
            <span style={{ fontSize: 17 }}>»</span><Icon n="🏦" size={16} /><span style={{ writingMode: "vertical-rl", letterSpacing: 1, fontSize: 12 }}>{t("Рахунки","Рахунки")}</span>
          </div>
        ) : (<>
        {/* Σ активних — над заголовком, лише з правом «Бачити ЗАГАЛЬНИЙ баланс» */}
        {canTotal &&
        <div style={{ textAlign: "center", marginBottom: 6 }}>
          <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: -0.3 }}>{money2(accounts.filter((a: any) => !/liqpay/i.test(a.name || "")).reduce((sm: number, a: any) => sm + Number(a.balance || 0), 0))}</div>
          <div className="muted" style={{ fontSize: 10.5 }}>{t("на активных счетах","на активних рахунках")}</div>
        </div>}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <b style={{ fontSize: 13 }}><Icon n="🏦" size={14} /> Рахунки</b>
          <span>
            {selAcc.length > 0 && <span style={{ fontSize: 11, color: "#2563eb", cursor: "pointer", marginRight: 6 }} onClick={() => { setSelAcc([]); setTimeout(() => load(1), 0); }}>скинути</span>}
            <button onClick={() => { setAccCollapsed(true); localStorage.setItem("fin_acc_collapsed", "1"); }} title={t("Свернуть блок","Згорнути блок")} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 15, marginRight: 2, color: "#64748b" }}>«</button>
            <button onClick={() => setBankHub(true)} title={t("Настройки: банки по API, правила разноски, история загрузок, счета","Налаштування: банки по API, правила рознесення, історія завантажень, рахунки")} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 14 }}><Icon n="⚙️" size={16} /></button>
          </span>
        </div>
        <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>Обери один або кілька — журнал відфільтрується.</div>
        {accounts.filter((a) => !/liqpay/i.test(a.name || "")).map((a) => {
          const on = selAcc.includes(a.id);
          return (
          <div key={a.id} onClick={() => toggleAcc(a.id)} style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 8px", borderRadius: 7, cursor: "pointer", fontSize: 12.5, userSelect: "none",
            background: on ? "rgba(37, 99, 235, 0.14)" : "transparent",
            boxShadow: on ? "inset 3px 0 0 #2563eb" : "none", fontWeight: on ? 700 : 400 }}>
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
            <b style={{ fontSize: 11, color: a.balance < 0 ? "#dc2626" : "#16a34a" }}>{money2(a.balance)}</b>
          </div>
        ); })}
        </>)}
      </div>
      {/* ручка зміни ширини блоку рахунків */}
      {!accCollapsed && <div onMouseDown={startAccResize} title={t("Тяни, чтобы изменить ширину","Тягни, щоб змінити ширину")} style={{ width: 6, alignSelf: "stretch", cursor: "col-resize", background: "#e2e8f0", borderRadius: 3, flexShrink: 0, minHeight: "60vh" }} />}
      <div style={{ flex: 1, minWidth: 0 }}>
      {!isMobile && (
      <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center" }} className="journal-filter">
        <input value={fq} onChange={(e) => setFq(e.target.value)} onKeyDown={(e) => e.key === "Enter" && apply()} placeholder={t("🔍 Поиск: сумма, контрагент, категория, комментарий, счёт…","🔍 Пошук: сума, контрагент, категорія, коментар, рахунок…")} style={{ flex: 1, height: 40, border: "1px solid #cbd5e1", borderRadius: 10, padding: "0 14px", fontSize: 14 }} />
        <button className="btn btn-light" onClick={() => setShowCols(true)} title={t("Все фильтры","Всі фільтри")} style={{ whiteSpace: "nowrap" }}><Icon n="⚙" size={14} /> {t("Фильтры","Фільтри")}{(() => { const n = (fContact ? 1 : 0) + (ff ? 1 : 0) + (ft ? 1 : 0) + Object.values(cf).filter((v: any) => v !== "" && v != null).length; return n ? ` (${n})` : ""; })()}</button>
        <button className="btn btn-primary" onClick={apply}>{t("Найти","Знайти")}</button>
        <button className="btn btn-light" onClick={resetAll} title={t("Сбросить всё","Скинути все")}>✕</button>
      </div>
      )}
      {searchOpen && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 1100, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 16 }} onClick={() => setSearchOpen(false)}>
          <div className="panel" style={{ maxWidth: 480, width: "100%", background: "#fff", margin: "16px auto" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}><h3 style={{ margin: 0, fontSize: 16 }}><Icon n="🔍" size={16} /> {t("Поиск","Пошук")}</h3><button onClick={() => setSearchOpen(false)} style={{ border: "none", background: "none", fontSize: 22, color: "#94a3b8", cursor: "pointer" }}>✕</button></div>
            <input autoFocus value={fq} onChange={(e) => setFq(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { apply(); setSearchOpen(false); } }} placeholder={t("Сумма, контрагент, категория, комментарий…","Сума, контрагент, категорія, коментар…")} style={{ width: "100%", height: 44, border: "1px solid #cbd5e1", borderRadius: 10, padding: "0 14px", fontSize: 15, boxSizing: "border-box", marginBottom: 12 }} />
            <button className="btn btn-primary" style={{ width: "100%", height: 46 }} onClick={() => { apply(); setSearchOpen(false); }}>{t("Найти","Знайти")}</button>
          </div>
        </div>
      )}
      {accOpen && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 1100, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 16, overflowY: "auto" }} onClick={() => setAccOpen(false)}>
          <div className="panel" style={{ maxWidth: 480, width: "100%", background: "#fff", margin: "16px auto", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}><h3 style={{ margin: 0, fontSize: 16 }}><Icon n="🏦" size={16} /> {t("Счета","Рахунки")}</h3><button onClick={() => setAccOpen(false)} style={{ border: "none", background: "none", fontSize: 22, color: "#94a3b8", cursor: "pointer" }}>✕</button></div>
            {canTotal && <div style={{ textAlign: "center", marginBottom: 10 }}><div style={{ fontSize: 22, fontWeight: 800 }}>{money2(accounts.filter((a: any) => !/liqpay/i.test(a.name || "")).reduce((sm: number, a: any) => sm + Number(a.balance || 0), 0))}</div><div className="muted" style={{ fontSize: 11 }}>{t("на активных счетах","на активних рахунках")}</div></div>}
            <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{t("Тапни счёт — журнал отфильтруется","Тапни рахунок — журнал відфільтрується")}</div>
            {accounts.map((a: any) => (
              <div key={a.id} onClick={() => setSelAcc((cur) => { const n = cur.includes(a.id) ? cur.filter((x) => x !== a.id) : [...cur, a.id]; setTimeout(() => { setPage(1); const qp = new URLSearchParams({ page: "1", page_size: String(pageSize) }); if (ff) qp.set("from", ff); if (ft) qp.set("to", ft); if (fq.trim()) qp.set("q", fq.trim()); Object.entries(cf).forEach(([k, v]) => { if (v) qp.set(k, String(v)); }); if (n.length) qp.set("accounts", n.join(",")); api.get<any>(`/api/transactions/?${qp.toString()}`).then((d) => { setTx(d.results || d); setCount(d.count ?? 0); }); }, 0); return n; })}
                style={{ display: "flex", justifyContent: "space-between", padding: "10px 6px", borderBottom: "1px solid #f1f5f9", cursor: "pointer", background: selAcc.includes(a.id) ? "#fdf3ec" : undefined }}>
                <span style={{ fontSize: 13.5 }}>{selAcc.includes(a.id) ? "✓ " : ""}{a.name}</span>
                <span style={{ fontWeight: 700, fontSize: 13.5, whiteSpace: "nowrap" }}>{money2(Number(a.balance || 0))}</span>
              </div>
            ))}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              {selAcc.length > 0 && <button className="btn btn-light" onClick={() => { setSelAcc([]); setTimeout(() => load(1), 0); }}>{t("Сбросить","Скинути")}</button>}
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => setAccOpen(false)}>{t("Готово","Готово")}</button>
            </div>
          </div>
        </div>
      )}
      {showCols && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 1100, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 16, overflowY: "auto" }} onClick={() => setShowCols(false)}>
        <div className="panel" style={{ maxWidth: 580, width: "100%", background: "#fff", margin: "24px auto" }} onClick={(e) => e.stopPropagation()}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}><h3 style={{ margin: 0, fontSize: 17 }}><Icon n="⚙" size={16} /> {t("Фильтры журнала","Фільтри журналу")}</h3><button onClick={() => setShowCols(false)} style={{ border: "none", background: "none", fontSize: 22, color: "#94a3b8", cursor: "pointer" }}>✕</button></div>
          <label className="label" style={{ display: "block", marginBottom: 4 }}>{t("Клиент","Клієнт")}</label>
          <div style={{ marginBottom: 10 }}><ClientPick value={fContact} label={fContactName} placeholder={t("Клиент / контрагент…","Клієнт / контрагент…")} onPick={(cid, nm) => { setFContact(cid); setFContactName(nm); }} /></div>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <div style={{ flex: 1 }}><label className="label" style={{ display: "block", marginBottom: 4 }}>{t("Дата от","Дата від")}</label><input type="date" value={ff} onChange={(e) => setFf(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px", boxSizing: "border-box" }} /></div>
            <div style={{ flex: 1 }}><label className="label" style={{ display: "block", marginBottom: 4 }}>{t("Дата до","Дата до")}</label><input type="date" value={ft} onChange={(e) => setFt(e.target.value)} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px", boxSizing: "border-box" }} /></div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {(() => { const cs = { height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px", width: "100%", boxSizing: "border-box" } as React.CSSProperties; const set = (k: string, v: any) => setCf((c: any) => ({ ...c, [k]: v })); return (<>
            <select value={cf.direction} onChange={(e) => set("direction", e.target.value)} style={cs}><option value="">{t("Тип: все","Тип: усі")}</option><option value="in">{t("Доход","Дохід")}</option><option value="out">{t("Расход","Витрата")}</option><option value="transfer">{t("Перевод","Переказ")}</option></select>
            <input value={cf.amount_min} onChange={(e) => set("amount_min", e.target.value)} type="number" placeholder={t("Сумма от","Сума від")} style={cs} />
            <input value={cf.amount_max} onChange={(e) => set("amount_max", e.target.value)} type="number" placeholder={t("Сумма до","Сума до")} style={cs} />
            <select value={cf.currency} onChange={(e) => set("currency", e.target.value)} style={cs}><option value="">{t("Валюта: все","Валюта: усі")}</option>{["UAH","USD","EUR","PLN","GBP"].map((x) => <option key={x} value={x}>{x}</option>)}</select>
            <input value={cf.cat} onChange={(e) => set("cat", e.target.value)} placeholder={t("Категория","Категорія")} style={cs} />
            <input value={cf.cp} onChange={(e) => set("cp", e.target.value)} placeholder={t("Контрагент","Контрагент")} style={cs} />
            <select value={cf.account} onChange={(e) => set("account", e.target.value)} style={cs}><option value="">{t("Счёт: все","Рахунок: усі")}</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
            <select value={cf.fin_article} onChange={(e) => set("fin_article", e.target.value)} style={cs}><option value="">{t("Фонд: все","Фонд: усі")}</option>{FUND_GROUPS_G.map(([gk, gl]) => { const gr = arts.filter((a: any) => a.category === gk && !a.parent); return gr.length ? <optgroup key={gk} label={gl}>{gr.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</optgroup> : null; })}</select>
            <select value={cf.fin_direction} onChange={(e) => set("fin_direction", e.target.value)} style={cs}><option value="">{t("Направление: все","Напрямок: усі")}</option>{dirs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
            <select value={cf.channel} onChange={(e) => set("channel", e.target.value)} style={cs}><option value="">{t("Канал: все","Канал: усі")}</option>{CHANNELS.filter((c) => c[0]).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            <input value={cf.comment} onChange={(e) => set("comment", e.target.value)} placeholder={t("Комментарий","Коментар")} style={cs} />
          </>); })()}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => { apply(); setShowCols(false); }}>{t("Применить","Застосувати")}</button>
            <button className="btn btn-light" onClick={resetAll}>{t("Сбросить всё","Скинути все")}</button>
          </div>
        </div>
        </div>
      )}
      <div className="jrnl-actions" style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center", flexWrap: "wrap" }}>
        {canTx && <button className="btn btn-primary" title={t("Добавить поступление денег","Додати надходження грошей")} onClick={() => openNew("in")}><Icon n="➕" size={13} /> {t("Доход","Дохід")}</button>}
        {canTx && <button className="btn btn-light" title={t("Добавить расход","Додати витрату")} onClick={() => openNew("out")}>− {t("Расход","Витрата")}</button>}
        {canTx && <button className="btn btn-light" title={t("Перевод между счетами — не считается ни в доход, ни в расход","Переказ між рахунками — не рахується ні в дохід, ні у витрати")} onClick={() => openNew("transfer")}>⇄ {t("Перевод","Переказ")}</button>}
        {isMobile && <div style={{ flexBasis: "100%", height: 0 }} />}
        {!isMobile && (lock.closed_until || lock.can_close) && (
          <span onClick={lock.can_close ? setPeriodLock : undefined} title={lock.can_close ? t("Изменить закрытие периода", "Змінити закриття періоду") : t("Период закрыт бухгалтерией", "Період закрито бухгалтерією")}
            style={{ fontSize: 12, fontWeight: 700, padding: "5px 12px", borderRadius: 8, cursor: lock.can_close ? "pointer" : "default",
                     background: lock.closed_until ? "#fef2f2" : "#f0fdf4", color: lock.closed_until ? "#dc2626" : "#16a34a", border: "1px solid " + (lock.closed_until ? "#fecaca" : "#bbf7d0") }}>
            <Icon n="🔒" size={14} /> {lock.closed_until ? t("Закрыто до ", "Закрито до ") + lock.closed_until : t("Период открыт", "Період відкритий")}
          </span>
        )}
        {!isMobile && canTx && <label className="btn btn-light" style={{ cursor: "pointer" }} title={t("Импорт банковской выписки CSV","Імпорт банківської виписки CSV")}>
          <Icon n="📤" size={14} /> {t("Выписка","Виписка")}
          <input type="file" accept=".csv,text/csv" style={{ display: "none" }} onChange={async (e) => {
            const f = e.target.files?.[0]; if (!f) return; (e.target as any).value = "";
            const text = await f.text();
            try {
              const dry: any = await api.post("/api/transactions/import-statement/", { data: text, commit: false });
              const msg = t("Импорт выписки на счёт","Імпорт виписки на рахунок") + ` «${dry.account}»:\n` +
                t("Новых операций","Нових операцій") + `: ${dry.created}\n` + t("Дубликатов (пропустим)","Дублікатів (пропустимо)") + `: ${dry.duplicates}\n` +
                t("Ошибок строк","Помилок рядків") + `: ${dry.errors}\n\n` +
                (dry.preview || []).map((p: any) => `${p.date} ${p.dir === "in" ? "+" : "−"}${p.amount} ${p.osnd}`).join("\n") +
                "\n\n" + t("Применить?","Застосувати?");
              if (!confirm(msg)) return;
              const done: any = await api.post("/api/transactions/import-statement/", { data: text, commit: true });
              alert(t("Готово ✓ Добавлено","Готово ✓ Додано") + `: ${done.created}`); load();
            } catch (err: any) { alert(err?.response?.data?.detail || t("Не удалось импортировать","Не вдалося імпортувати")); }
          }} />
        </label>}
        {!isMobile && <button className="btn btn-light" title={t("Выгрузить журнал в CSV (Excel)","Вивантажити журнал у CSV (Excel)")} onClick={async () => {
          try { const u = await (api as any).blobUrl("/api/transactions/export/"); const a = document.createElement("a"); a.href = u; a.download = "journal.csv"; a.click(); }
          catch { alert(t("Не удалось выгрузить","Не вдалося вивантажити")); }
        }}><Icon n="📥" size={14} /> CSV</button>}
        {isMobile && (
          <div style={{ position: "relative", flexShrink: 0 }}>
            <button className="btn btn-light" style={{ fontWeight: 700 }} onClick={() => setActMenu((v) => !v)}><Icon n="📋" size={15} /> {t("Дії","Дії")} ▾</button>
            {actMenu && (<>
              <div onClick={() => setActMenu(false)} style={{ position: "fixed", inset: 0, zIndex: 340 }} />
              <div style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, background: "#fff", borderRadius: 14, boxShadow: "0 18px 50px rgba(15,23,42,.28)", border: "1px solid #e8edf3", padding: 8, zIndex: 350, minWidth: 244, display: "flex", flexDirection: "column", gap: 2 }}>
                <button style={mrow} onClick={() => { setSearchOpen(true); setActMenu(false); }}><Icon n="🔍" size={17} /> <span>{t("Поиск","Пошук")}{fq ? " •" : ""}</span></button>
                <button style={mrow} onClick={() => { setShowCols(true); setActMenu(false); }}><Icon n="⚙" size={17} /> <span>{t("Фильтры","Фільтри")}{(() => { const n = (fContact ? 1 : 0) + (ff ? 1 : 0) + (ft ? 1 : 0) + Object.values(cf).filter((v: any) => v !== "" && v != null).length; return n ? ` (${n})` : ""; })()}</span></button>
                <button style={mrow} onClick={() => { setAccOpen(true); setActMenu(false); }}><Icon n="🏦" size={17} /> <span>{t("Счета","Рахунки")}</span></button>
                {canTx && <label style={{ ...mrow, cursor: "pointer" }}><Icon n="📤" size={17} /> <span>{t("Загрузить выписку","Завантажити виписку")}</span>
                  <input type="file" accept=".csv,text/csv" style={{ display: "none" }} onChange={async (e) => {
                    const f = e.target.files?.[0]; if (!f) return; (e.target as any).value = ""; setActMenu(false);
                    const text = await f.text();
                    try {
                      const dry: any = await api.post("/api/transactions/import-statement/", { data: text, commit: false });
                      const msg = t("Импорт выписки на счёт","Імпорт виписки на рахунок") + ` «${dry.account}»:\n` +
                        t("Новых операций","Нових операцій") + `: ${dry.created}\n` + t("Дубликатов (пропустим)","Дублікатів (пропустимо)") + `: ${dry.duplicates}\n` +
                        t("Ошибок строк","Помилок рядків") + `: ${dry.errors}\n\n` +
                        (dry.preview || []).map((p: any) => `${p.date} ${p.dir === "in" ? "+" : "−"}${p.amount} ${p.osnd}`).join("\n") +
                        "\n\n" + t("Применить?","Застосувати?");
                      if (!confirm(msg)) return;
                      const done: any = await api.post("/api/transactions/import-statement/", { data: text, commit: true });
                      alert(t("Готово ✓ Добавлено","Готово ✓ Додано") + `: ${done.created}`); load();
                    } catch (err: any) { alert(err?.response?.data?.detail || t("Не удалось импортировать","Не вдалося імпортувати")); }
                  }} />
                </label>}
                <button style={mrow} onClick={async () => { setActMenu(false); try { const u = await (api as any).blobUrl("/api/transactions/export/"); const a = document.createElement("a"); a.href = u; a.download = "journal.csv"; a.click(); } catch { alert(t("Не удалось выгрузить","Не вдалося вивантажити")); } }}><Icon n="📥" size={17} /> <span>{t("Экспорт в CSV (Excel)","Експорт у CSV (Excel)")}</span></button>
                {(lock.closed_until || lock.can_close) && <button style={{ ...mrow, color: lock.closed_until ? "#dc2626" : "#16a34a" }} onClick={lock.can_close ? () => { setPeriodLock(); setActMenu(false); } : () => setActMenu(false)}><Icon n="🔒" size={17} /> <span>{lock.closed_until ? t("Период: закрыт до ","Період: закрито до ") + lock.closed_until : t("Период открыт","Період відкритий")}</span></button>}
              </div>
            </>)}
          </div>
        )}
        {bankHub && <BankHubModal onClose={() => { setBankHub(false); load(); api.get<any>("/api/accounts/").then((d) => setAccounts((d.results || d).filter((a: any) => a.is_active !== false))); }} />}
        <div style={{ marginLeft: isMobile ? 0 : "auto", width: "auto", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: isMobile ? 6 : 8, fontSize: isMobile ? 13 : 13 }}>
          {!isMobile && <span className="muted">{t("На стр.","На стор.")}:</span>}
          <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} style={{ height: isMobile ? 30 : 30, border: "1px solid #cbd5e1", borderRadius: 8, fontSize: isMobile ? 13 : 13, padding: "0 2px", flexShrink: 0 }}>{[20, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}</select>
          {!isMobile && <span className="muted">{t("Всего","Всього")}: <b>{count}</b></span>}
          <button className="btn btn-light" style={{ padding: isMobile ? "5px 12px" : undefined, fontSize: isMobile ? 16 : undefined }} disabled={page <= 1} onClick={() => goPage(page - 1)}>←</button>
          <span style={{ whiteSpace: "nowrap" }}>{!isMobile && (t("стр.","стор.") + " ")}<b>{page}</b> {t("из","з")} {totalPages}</span>
          <button className="btn btn-light" style={{ padding: isMobile ? "5px 12px" : undefined, fontSize: isMobile ? 16 : undefined }} disabled={page >= totalPages} onClick={() => goPage(page + 1)}>→</button>
        </div>
      </div>
      {isMobile ? (
        <div className="panel" style={{ margin: 0, padding: "2px 4px" }}>
          {tx.length === 0 && <div className="muted" style={{ padding: 14 }}>{t("Операций ещё нет","Операцій ще немає")}</div>}
          {tx.map((r) => (
            <div key={r.id} onClick={() => openEdit(r)} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10, padding: "12px 6px", borderBottom: "1px solid #f1f5f9", cursor: "pointer" }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 14, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.direction === "transfer" ? t("Перевод","Переказ") : (r.counterparty || r.category_name || "—")}</div>
                <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{new Date(r.date || r.created_at).toLocaleDateString("ru")}{r.op_time ? " · " + String(r.op_time).slice(0, 5) : ""}{r.category_name && r.direction !== "transfer" ? " · " + r.category_name : ""}</div>
                {r.deal ? <div style={{ fontSize: 11.5, color: "#1d4ed8", marginTop: 2 }}>#{r.deal}{r.deal_title ? " · " + r.deal_title.slice(0, 22) : ""}</div> : null}
              </div>
              <div style={{ fontWeight: 800, fontSize: 15, whiteSpace: "nowrap", color: r.direction === "in" ? "#16a34a" : r.direction === "transfer" ? "#6366f1" : "#dc2626" }}>{r.direction === "in" ? "+" : r.direction === "transfer" ? "⇄ " : "−"}{Number(r.amount).toLocaleString("ru")} ₴</div>
            </div>
          ))}
        </div>
      ) : (
      <div className="panel" style={{ margin: 0, padding: 0, overflow: "auto", maxHeight: "calc(100vh - 230px)" }}>
        <table className="jrnl-tbl" style={{ width: "100%", fontSize: 13, tableLayout: "fixed" }}>
          <colgroup>{colW.map((w, i) => <col key={i} style={{ width: w }} />)}</colgroup>
          <thead><tr>
            {([[t("Дата","Дата"), "date"], [t("Сумма","Сума"), "amount_uah"], [t("Вал.","Вал."), "currency"], ["₴", "amount_uah"], [t("Категория","Категорія"), "category__name"], [t("Контрагент","Контрагент"), "counterparty"], [t("Счёт","Рахунок"), "account__name"], [t("Угода","Угода"), ""], [t("Фонд","Фонд"), "fin_article__name"], [t("Направление","Напрямок"), "fin_direction__name"], [t("Канал","Канал"), "channel"], [t("Комментарий","Коментар"), "comment"]] as [string, string][]).map(([label, fld], i) => (
              <th key={i} onClick={() => { if (!fld) return; setSortF(sortF === fld ? "-" + fld : (sortF === "-" + fld ? fld : "-" + fld)); }}
                title={fld ? t("Клик — сортировать по этому столбцу","Клік — сортувати за цим стовпцем") : undefined}
                style={{ position: "sticky" as any, top: 0, background: "#f8fafc", zIndex: 5, boxShadow: "0 1px 0 #e2e8f0", padding: "8px 10px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", cursor: fld ? "pointer" : "default", userSelect: "none" }}>
                {i === 0 && <input type="checkbox" checked={tx.length > 0 && tx.every((r: any) => selTx[r.id])} onClick={(e) => e.stopPropagation()} onChange={(e) => { const n: any = { ...selTx }; tx.forEach((r: any) => { n[r.id] = e.target.checked; }); setSelTx(n); }} title={t("Выбрать все на странице","Вибрати всі на сторінці")} style={{ marginRight: 6, verticalAlign: "middle", width: 14, height: 14, accentColor: "#C67D5F" }} />}
                {label}{sortF.replace("-", "") === fld ? (sortF.startsWith("-") ? " ↓" : " ↑") : ""}
                <span onMouseDown={startColResize(i)} title={t("Тяни — ширина колонки", "Тягни — ширина колонки")}
                  style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: 7, cursor: "col-resize", borderRight: "2px solid #e2e8f0" }} />
              </th>
            ))}
          </tr></thead>
          <tbody>
            {tx.length === 0 && <tr><td colSpan={12} className="muted" style={{ padding: 14 }}>{t("Операций ещё нет. Добавь вручную или они появятся при оплате сделок.","Операцій ще немає. Додай вручну або вони зʼявляться при оплаті угод.")}</td></tr>}
            {tx.map((r) => (
              <tr key={r.id} onClick={() => openEdit(r)} title={t("Кликни, чтобы посмотреть и изменить","Клікни, щоб переглянути та змінити")} style={{ borderBottom: "1px solid #f1f5f9", cursor: "pointer", background: selTx[r.id] ? "#fdf3ec" : undefined }}>
                <td className="muted" style={{ padding: "8px 12px", whiteSpace: "nowrap" }}>
                  <input type="checkbox" checked={!!selTx[r.id]} onClick={(e) => e.stopPropagation()} onChange={(e) => setSelTx({ ...selTx, [r.id]: e.target.checked })} style={{ marginRight: 6, verticalAlign: "middle", width: 14, height: 14, accentColor: "#C67D5F" }} />
                  {new Date(r.date || r.created_at).toLocaleDateString("ru")}{r.op_time ? <span style={{ display: "block", fontSize: 10.5, opacity: 0.75, paddingLeft: 20 }}>{String(r.op_time).slice(0, 5)}</span> : null}</td>
                <td style={{ fontWeight: 600, color: r.direction === "in" ? "#16a34a" : r.direction === "transfer" ? "#6366f1" : "#dc2626" }}>{r.direction === "in" ? "+" : r.direction === "transfer" ? "⇄ " : "−"}{Number(r.amount).toLocaleString("ru")}</td>
                <td className="muted">{r.currency || "UAH"}</td>
                <td className="muted">{Number(r.amount_uah || r.amount).toLocaleString("ru")} ₴</td>
                <td>{r.direction === "transfer" ? <span style={{ color: "#6366f1", fontWeight: 600 }}>Переказ</span> : ((r as any).category_path ? ((r as any).category_path.includes(" → ") ? <span><span className="muted" style={{ fontSize: 11 }}>{(r as any).category_path.split(" → ")[0]} → </span><b style={{ fontWeight: 600 }}>{(r as any).category_path.split(" → ")[1]}</b></span> : (r as any).category_path) : (r.category_name || <span className="muted">—</span>))}</td>
                <td>{r.direction === "transfer" ? <span className="muted">переказ</span> : <CpText name={r.counterparty} contact={(r as any).contact} cpMap={cpMap} nav={nav} />}</td>
                <td className="muted">{r.direction === "transfer" && r.transfer_account_name
                  ? <span><span>{r.account_name}</span><span style={{ color: "#6366f1", fontWeight: 700 }}> → </span><span>{r.transfer_account_name}</span>{(r as any).transfer_amount ? <span style={{ color: "#6366f1" }}> ({Number((r as any).transfer_amount).toLocaleString("ru")})</span> : null}</span>
                  : r.account_name}</td>
                <td onClick={(e) => { e.stopPropagation(); if (r.deal) setDrawerDeal(r.deal); }}>{r.deal ? <span style={{ color: "#1d4ed8", cursor: "pointer", fontWeight: 600 }} title="Відкрити картку угоди">#{r.deal}{r.deal_title ? " · " + r.deal_title.slice(0, 16) : ""} · {Number(r.amount).toLocaleString("ru")}₴</span> : <span className="muted">—</span>}{(r as any).contact_name ? <div><a href={"/clients/" + (r as any).contact} onClick={(e) => e.stopPropagation()} style={{ fontSize: 11, color: "#0e7490", textDecoration: "none", fontWeight: 600 }} title="Картка клієнта"><Icon n="👤" size={11} /> {(r as any).contact_name.slice(0, 22)}</a></div> : null}</td>
                <td>{r.fin_article_name || <span className="muted">—</span>}</td>
                <td>{r.fin_direction_name || <span className="muted">—</span>}</td>
                <td className="muted">{(CHANNELS.find((c) => c[0] === r.channel) || ["", "—"])[1]}</td>
                <td className="muted" title={r.comment} style={{ maxWidth: 260, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 11.5, lineHeight: 1.35 }}>{(r.comment || "").replace(/^[A-ZА-ЯІЇЄ#]+#\S+\s*·\s*/u, "")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
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

      {bulkPanel}
      {open && (
        <TxCardModal
          key={"txm-" + (f.id || "new") + "-" + f.direction + "-" + (f.contact || 0)}
          txId={f.id || undefined}
          initDirection={f.direction === "in" || f.direction === "transfer" ? f.direction : "out"}
          initContact={f.contact || undefined}
          initContactName={f.contact_name || ""}
          onClose={() => setOpen(false)}
          onSaved={() => { setOpen(false); load(page); loadAccs(); }}
          nav={(pth: string) => nav(pth)}
        />
      )}
    </div>
  );
}

export function Attachments({ txId }: { txId: number }) {
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
    // ВАЖНО: окно открываем СИНХРОННО (в контексте клика), иначе попап блокируется после await
    const w = window.open("", "_blank");
    try { const url = await api.blobUrl(`/api/attachments/${a.id}/file/`); if (w) w.location.href = url; else window.open(url, "_blank"); }
    catch { if (w) w.close(); setErr(t("Не удалось открыть","Не вдалося відкрити")); }
  }
  async function del(id: number) { await api.del(`/api/attachments/${id}/file/`); reload(); }
  return (
    <div style={{ marginBottom: 10 }}>
      <label className="label" title={t("Прикрепи фото или скан чека. С телефона откроется камера.","Прикріпи фото або скан чека. З телефона відкриється камера.")}><Icon n="📎" size={14} /> {t("Чек / документы","Чек / документи")}</label>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
        {items.map((a) => (
          <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 4, background: "#f1f5f9", borderRadius: 8, padding: "4px 8px", fontSize: 12 }}>
            <span style={{ cursor: "pointer", color: "#1d4ed8", textDecoration: "underline", fontWeight: 600, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={t("Нажми, чтобы открыть","Натисни, щоб відкрити")} onClick={() => openFile(a)}>{a.content_type?.startsWith("image/") ? <Icon n="🖼" size={14} /> : <Icon n="📄" size={14} />} {a.filename}</span>
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
  const isMobile = useIsMobile();
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
  const slbl = (x: any) => d.series.granularity === "day" ? x.d.slice(8) + "." + x.d.slice(5, 7) : x.d.slice(5) + "." + x.d.slice(2, 4);
  const CH = 190; // висота графіка руху
  const sHi = Math.max(...rows.map((x: any) => Math.max(x.in, x.out, x.net)), 1);
  const sLo = Math.min(...rows.map((x: any) => Math.min(0, x.net)), 0);
  const sY = (v: number) => 6 + (sHi - v) / (sHi - sLo || 1) * (CH - 12);
  const sZero = sY(0);
  const sTicks = mkTicks(sHi, sLo);

  const months = d.months || [];
  const MH = 170;
  const mHi = Math.max(...months.map((m: any) => Math.max(m.income, m.expense, m.net)), 1);
  const mLo = Math.min(...months.map((m: any) => Math.min(0, m.net)), 0);
  const mY = (v: number) => 6 + (mHi - v) / (mHi - mLo || 1) * (MH - 12);
  const mZero = mY(0);
  const mTicks = mkTicks(mHi, mLo);

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
            <div style={{ position: "absolute", inset: 34, background: "var(--panel, #fff)", borderRadius: "50%" }} />
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
        <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
          {/* ЛЕСЕНКА ГРОШЕЙ (вісь Y) */}
          <div style={{ position: "relative", width: 52, height: CH, flexShrink: 0 }}>
            {sTicks.map((v) => (
              <div key={v} className="muted" style={{ position: "absolute", top: sY(v) - 7, right: 2, fontSize: 10, fontWeight: v === 0 ? 700 : 400, color: v === 0 ? "#334155" : undefined }}>{fmtShort(v)}</div>
            ))}
          </div>
          <div style={{ position: "relative", flex: 1, height: CH }}>
            {sTicks.map((v) => <div key={v} style={{ position: "absolute", left: 0, right: 0, top: sY(v), borderTop: v === 0 ? "1.5px dashed #94a3b8" : "1px solid #e2e8f055" }} />)}
            <div style={{ display: "flex", gap: rows.length > 45 ? 1 : 3, height: CH }}>
              {rows.map((x: any, i: number) => (
                <div key={i} title={`${x.d}\n+${Math.round(x.in).toLocaleString("uk-UA")} / −${Math.round(x.out).toLocaleString("uk-UA")} = ${Math.round(x.net).toLocaleString("uk-UA")}`}
                     style={{ flex: 1, minWidth: 2, position: "relative" }}>
                  <div style={{ position: "absolute", left: 0, width: "46%", bottom: CH - sZero, height: Math.max(sZero - sY(x.in), x.in > 0 ? 2 : 0), background: "#22c55e", borderRadius: "3px 3px 0 0" }} />
                  <div style={{ position: "absolute", right: 0, width: "46%", bottom: CH - sZero, height: Math.max(sZero - sY(x.out), x.out > 0 ? 2 : 0), background: "#334155", borderRadius: "3px 3px 0 0" }} />
                </div>
              ))}
            </div>
            <svg width="100%" height={CH} style={{ position: "absolute", inset: 0, pointerEvents: "none" }} preserveAspectRatio="none" viewBox={`0 0 ${Math.max(rows.length, 1) * 10} ${CH}`}>
              <path fill="none" stroke="#f97316" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" d={smoothPath(rows.map((x: any, i: number) => [i * 10 + 5, sY(x.net)]))} />
            </svg>
          </div>
        </div>
        <div style={{ display: "flex", gap: rows.length > 45 ? 1 : 3, marginTop: 4, marginLeft: 58 }}>
          {rows.map((x: any, i: number) => (
            <div key={i} className="muted" style={{ flex: 1, fontSize: 8.5, textAlign: "center", overflow: "hidden", whiteSpace: "nowrap" }}>{(rows.length <= 16 || i % Math.ceil(rows.length / 16) === 0) ? slbl(x) : ""}</div>
          ))}
        </div>
      </div>

      {/* ДОНАТИ ПО КАТЕГОРІЯХ */}
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 12 }}>
        <Donut items={d.by_cat_in || []} title={t("Поступления по категориям","Надходження по категоріях")} total={k.income} />
        <Donut items={d.top_expense || []} title={t("Списания по категориям","Списання по категоріях")} total={k.expense} />
      </div>

      {/* ТРЕНД 12 МІСЯЦІВ: доходи/витрати + лінія прибутку */}
      <div className="panel" style={{ margin: "12px 0" }}>
        <b style={{ fontSize: 14 }}>{t("Тренд 12 месяцев: доходы / расходы / прибыль","Тренд 12 місяців: доходи / витрати / прибуток")}</b>
        <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
          <div style={{ position: "relative", width: 52, height: MH, flexShrink: 0 }}>
            {mTicks.map((v) => (
              <div key={v} className="muted" style={{ position: "absolute", top: mY(v) - 7, right: 2, fontSize: 10, fontWeight: v === 0 ? 700 : 400, color: v === 0 ? "#334155" : undefined }}>{fmtShort(v)}</div>
            ))}
          </div>
          <div style={{ position: "relative", flex: 1, height: MH }}>
            {mTicks.map((v) => <div key={v} style={{ position: "absolute", left: 0, right: 0, top: mY(v), borderTop: v === 0 ? "1.5px dashed #94a3b8" : "1px solid #e2e8f055" }} />)}
            <div style={{ display: "flex", gap: 6, height: MH }}>
              {months.map((m: any) => (
                <div key={m.ym} title={`${m.ym}\n+${money(m.income)} / −${money(m.expense)}\n${t("прибыль","прибуток")}: ${money(m.net)}`}
                     style={{ flex: 1, position: "relative" }}>
                  <div style={{ position: "absolute", left: 0, width: "46%", bottom: MH - mZero, height: Math.max(mZero - mY(m.income), m.income > 0 ? 2 : 0), background: "#22c55e", borderRadius: "3px 3px 0 0" }} />
                  <div style={{ position: "absolute", right: 0, width: "46%", bottom: MH - mZero, height: Math.max(mZero - mY(m.expense), m.expense > 0 ? 2 : 0), background: "#334155", borderRadius: "3px 3px 0 0" }} />
                </div>
              ))}
            </div>
            <svg width="100%" height={MH} style={{ position: "absolute", inset: 0, pointerEvents: "none" }} preserveAspectRatio="none" viewBox={`0 0 ${Math.max(months.length, 1) * 10} ${MH}`}>
              <path fill="none" stroke="#f97316" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" d={smoothPath(months.map((m: any, i: number) => [i * 10 + 5, mY(m.net)]))} />
            </svg>
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, marginTop: 4, marginLeft: 58 }}>
          {months.map((m: any) => <div key={m.ym} className="muted" style={{ flex: 1, fontSize: 9.5, textAlign: "center" }}>{m.ym.slice(5)}.{m.ym.slice(2, 4)}</div>)}
        </div>
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>🟩 {t("доходы","доходи")} · ⬛ {t("расходы","витрати")} · 🟠 {t("линия прибыли","лінія прибутку")}</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 12 }}>
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

      {/* ВАЛЮТНА АНАЛІТИКА (курси, вплив на прибуток) */}
      <div style={{ marginTop: 12 }}>
        <FxImpact />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 12, marginTop: 12 }}>
        {/* РАХУНКИ */}
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>{t("Балансы счетов","Баланси рахунків")}</b>
          {accShown.map((a: any) => (
            <div key={a.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "5px 0", borderBottom: "1px solid #f8fafc" }}>
              <span>{a.name}</span><b style={{ color: a.balance < 0 ? "#dc2626" : "#1e293b" }}>{money2(a.balance)}</b>
            </div>
          ))}
          {d.accounts.length > 8 && <button className="btn btn-light" style={{ marginTop: 8, fontSize: 12 }} onClick={() => setAllAcc(!allAcc)}>{allAcc ? t("Свернуть","Згорнути") : t("Показать все","Показати всі") + ` ${d.accounts.length}`}</button>}
        </div>
        {/* КОЕФІЦІЄНТИ */}
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>{t("Ключевые коэффициенты","Ключові коефіцієнти")}</b>
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 10, marginTop: 10 }}>
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
function PnLNote() {
  const { t } = useLang();
  return (
    <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, padding: "8px 12px", fontSize: 12.5, color: "#1e40af", marginBottom: 10 }}>
      ℹ️ {t("P&L — НОРМАТИВНЫЙ (проценты финмодели на фактической выручке). Кассовый факт денег — в Журнале и на Дашборде. Эти две цифры и должны отличаться: P&L показывает «как должно быть по модели», журнал — «как прошло по кассе».",
            "P&L — НОРМАТИВНИЙ (відсотки фінмоделі на фактичній виручці). Касовий факт грошей — у Журналі та на Дашборді. Ці дві цифри і мають відрізнятись: P&L показує «як має бути по моделі», журнал — «як пройшло по касі».")}
    </div>
  );
}

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
      <PnLNote />
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
  const [d, setD] = useState<any>(null);
  const { t: tr } = useLang();
  useEffect(() => { api.get<any>(`/api/finance/breakeven/`).then(setD); }, []);
  if (!d) return <div className="spin">{tr("Загрузка…","Завантаження…")}</div>;
  const prog = Math.min(100, d.progress);
  const cards: [string, string][] = [
    [tr("Сумма фондов выручки (финмодель)","Сума фондів виручки (фінмодель)"), d.rev_funds_pct + " %"], [tr("Маржа с каждой ₴","Маржа з кожної ₴"), d.margin_pct + " %"],
    [tr("ТБ на месяц (по финмодели)","ТБ на місяць (за фінмоделлю)"), money(d.breakeven)], [tr("Выручка этого месяца (факт)","Виручка цього місяця (факт)"), money(d.revenue)], [tr("Затраты / мес (финмодель)","Витрати / міс (фінмодель)"), money(d.monthly_costs)],
  ];
  return (
    <>
      <div className="note" style={{ marginBottom: 10 }}><Icon n="🎯" size={14} /> {tr("Точка безубыточности считается ОТ ФИНМОДЕЛИ (нормативы затрат и маржи), снизу вверх. Прогресс — факт текущего месяца.","Точка беззбитковості рахується ВІД ФІНМОДЕЛІ (нормативи витрат і маржі), знизу вгору. Прогрес — факт поточного місяця.")}</div>
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
  const isMobile = useIsMobile();
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
      <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
      <table style={{ width: "100%", marginTop: 4, fontSize: 13, minWidth: isMobile ? 720 : undefined }}>
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
      </div>
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
          <div className="muted" style={{ fontSize: 11.5, fontWeight: 600, marginBottom: 4 }}><Icon n="🌿" size={13} /> {t("Каналы (ветки) направления · продаж × сумма:","Канали (гілки) напрямку · продажів × сума:")}</div>
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
          <thead><tr><th style={{ textAlign: "left", padding: "4px 8px" }}>{t("Дата","Дата")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th><th style={{ textAlign: "left" }}>{t("Фонд","Фонд")}</th><th style={{ textAlign: "center" }}>{t("Канал","Канал")}</th><th style={{ textAlign: "left" }}>{t("Комментарий","Коментар")}</th></tr></thead>
          <tbody>
            {tx.map((r) => (
              <tr key={r.id} style={{ borderTop: "1px solid #eef2f7" }}>
                <td className="muted" style={{ padding: "4px 8px" }}>{new Date(r.date || r.created_at).toLocaleDateString("ru")}</td>
                <td style={{ textAlign: "right", fontWeight: 600, color: r.direction === "in" ? "#16a34a" : "#dc2626" }}>{r.direction === "in" ? "+" : "−"}{Number(r.amount).toLocaleString("ru")} ₴</td>
                <td>{r.fin_article_name || <span className="muted">—</span>}</td>
                <td className="muted" style={{ textAlign: "center" }}>{(CHANNELS.find((c) => c[0] === r.channel) || ["", "—"])[1]}</td>
                <td className="muted" title={r.comment} style={{ maxWidth: 260, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 11.5, lineHeight: 1.35 }}>{(r.comment || "").replace(/^[A-ZА-ЯІЇЄ#]+#\S+\s*·\s*/u, "")}</td>
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
      <div className="note"><Icon n="🕐" size={14} /> <b>{t("Табель рабочего времени","Табель робочого часу")}</b> {t("(как в Битриксе). Клик на день меняет статус по кругу. Влияет на ЗП: оклад платится пропорционально отработанным дням, а","(як у Бітриксі). Клік на день змінює статус по колу. Впливає на ЗП: оклад платиться пропорційно відпрацьованим дням, а")} <b>{t("перевыполнение","перевиконання")}</b> {t("(выход в выходной) добавляет дневную ставку сверху. Если табель не вести — оклад полный по умолчанию.","(вихід у вихідний) додає денну ставку зверху. Якщо табель не вести — оклад повний за замовчуванням.")}</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0", flexWrap: "wrap", rowGap: 8 }}>
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
            <td style={{ ...tdS, textAlign: "right", fontWeight: 600 }}>{money2(a.balance)}</td>
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
  const [arts, setArts] = useState<any[]>([]);
  const [dirs, setDirs] = useState<any[]>([]);
  const [showHidden, setShowHidden] = useState(false);
  const { t } = useLang();
  const isMobile = useIsMobile();
  const [nn, setNn] = useState(""); const [nd, setNd] = useState("out"); const [np, setNp] = useState(0);
  const load = () => api.get<any>("/api/categories/?page_size=400").then((d) => setItems(d.results || d));
  useEffect(() => {
    load();
    api.get<any>("/api/finmodel-articles/?page_size=300").then((d) => setArts((d.results || d).filter((a: any) => !a.parent && a.active && !["config", "salary", "warehouse_rate"].includes(a.category)))).catch(() => {});
    api.get<any>("/api/fin-directions/?page_size=100").then((d) => setDirs(d.results || d)).catch(() => {});
  }, []);
  async function add() { if (!nn.trim()) return; await api.post("/api/categories/", { name: nn.trim(), direction: nd, parent: np || null }); setNn(""); setNp(0); load(); }
  async function patch(id: number, body: any) { await api.patch(`/api/categories/${id}/`, body); load(); }
  async function delCat(c: any) {
    if (!confirm(t(`Удалить категорию «${c.name}»? Операции НЕ удалятся — они останутся без категории. Подкатегории станут верхнего уровня.`, `Видалити категорію «${c.name}»? Операції НЕ видаляться — лишаться без категорії. Підкатегорії стануть верхнього рівня.`))) return;
    await api.del(`/api/categories/${c.id}/`); load();
  }
  const [dragId, setDragId] = useState<number | null>(null);
  async function dropOn(target: any) {
    if (!dragId || dragId === target.id) return;
    const src = items.find((x) => x.id === dragId);
    if (!src || src.direction !== target.direction || (src.parent || 0) !== (target.parent || 0)) { setDragId(null); return; }
    const group = items.filter((x) => x.direction === src.direction && (x.parent || 0) === (src.parent || 0) && (showHidden || !x.hidden));
    const ordered = group.filter((x) => x.id !== src.id);
    const idx = ordered.findIndex((x) => x.id === target.id);
    ordered.splice(idx, 0, src);
    setDragId(null);
    for (let i = 0; i < ordered.length; i++) {
      if (ordered[i].sort_order !== (i + 1) * 10) await api.patch(`/api/categories/${ordered[i].id}/`, { sort_order: (i + 1) * 10 });
    }
    load();
  }
  const tops = (dr: string) => items.filter((c) => c.direction === dr && !c.parent && (showHidden || !c.hidden));
  const kids = (pid: number) => items.filter((c) => c.parent === pid && (showHidden || !c.hidden));
  const FUND_GROUPS: [string, string][] = [["revenue_fund", t("Фонды выручки (ФВ)","Фонди виручки (ФВ)")], ["variable", t("Переменные (ФМ)","Змінні (ФМ)")], ["fixed", t("Постоянные (ФМ)","Постійні (ФМ)")], ["skd", t("СКД (развитие)","СКД (розвиток)")], ["payment_fee", t("Комиссии за оплату","Комісії за оплату")], ["upr_cat2", "УПР"], ["upr_cat3", "УПР (відмовні)"]];
  const fundSel = (c: any, inherited?: any) => (
    <select value={c.fin_article || 0} onChange={(e) => patch(c.id, { fin_article: Number(e.target.value) || null })}
      style={{ ...inpS, fontSize: 11.5, padding: "3px 6px", maxWidth: 230, color: c.fin_article ? "#0f172a" : "#94a3b8" }}
      title={t("Фонд: подставляется в операцию автоматически по категории. Список живой — новый фонд из Финмодели/Планирования появляется тут сразу","Фонд: підставляється в операцію автоматично за категорією. Список живий — новий фонд з Фінмоделі/Планування зʼявляється тут одразу")}>
      <option value={0}>{inherited ? "↑ " + inherited.name.slice(0, 26) : t("— фонд не задан —","— фонд не задано —")}</option>
      {FUND_GROUPS.map(([key, label]) => {
        const gr = arts.filter((a) => a.category === key);
        return gr.length ? <optgroup key={key} label={label}>{gr.map((a) => <option key={a.id} value={a.id}>{a.name.slice(0, 44)}</option>)}</optgroup> : null;
      })}
    </select>
  );
  const dirSel = (c: any) => (
    <select value={c.fin_direction || 0} onChange={(e) => patch(c.id, { fin_direction: Number(e.target.value) || null })}
      style={{ ...inpS, fontSize: 11.5, padding: "3px 6px", maxWidth: 150, color: c.fin_direction ? "#0f172a" : "#94a3b8" }}>
      <option value={0}>{t("общий","загальний")}</option>
      {dirs.map((d) => <option key={d.id} value={d.id}>{d.name.slice(0, 24)}</option>)}
    </select>
  );
  const row = (c: any, depth: number, parent?: any) => (
    <tr key={c.id} style={{ opacity: c.hidden ? 0.45 : 1, cursor: "grab", background: dragId === c.id ? "#fdf3ec" : undefined }}
      draggable onDragStart={() => setDragId(c.id)} onDragOver={(e) => e.preventDefault()} onDrop={() => dropOn(c)}>
      <td style={{ ...tdS, paddingLeft: 8 + depth * 22 }} title={t("Потяни строку, чтобы поменять порядок","Потягни рядок, щоб змінити порядок")}><span className="muted" style={{ marginRight: 6 }}>⠿</span>{depth > 0 && <span className="muted">└ </span>}{c.name}</td>
      <td style={{ ...tdS }}>{c.direction === "out" || depth > 0 ? fundSel(c, parent && arts.find((a) => a.id === parent.fin_article)) : null}</td>
      <td style={{ ...tdS }}>{dirSel(c)}</td>
      <td style={{ ...tdS, textAlign: "center", whiteSpace: "nowrap" }}>
        <span style={{ cursor: "pointer" }} title={c.hidden ? t("Показать в выборе","Показати у виборі") : t("Скрыть из выбора (история остаётся)","Приховати з вибору (історія лишається)")}
          onClick={() => patch(c.id, { hidden: !c.hidden })}>{c.hidden ? <Icon n="🚫" size={14} /> : <Icon n="👁" size={14} />}</span>
        <span style={{ cursor: "pointer", color: "#ef4444", marginLeft: 8 }} title={t("Удалить категорию","Видалити категорію")} onClick={() => delCat(c)}><Icon n="🗑" size={14} /></span>
      </td>
    </tr>
  );
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div className="note" style={{ marginBottom: 10 }}>{t("Связка «категория → фонд»: фонд и направление из этой таблицы подставляются в операцию автоматически. Подкатегория без своего фонда наследует фонд родителя (серым «↑»).","Звʼязка «категорія → фонд»: фонд і напрямок з цієї таблиці підставляються в операцію автоматично. Підкатегорія без свого фонду наслідує фонд батька (сірим «↑»).")}</div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <input value={nn} onChange={(e) => setNn(e.target.value)} placeholder={t("Новая категория","Нова категорія")} style={{ ...inpS, flex: 1, minWidth: 160 }} />
        <select value={nd} onChange={(e) => { setNd(e.target.value); setNp(0); }} style={inpS}><option value="in">{t("Доход","Дохід")}</option><option value="out">{t("Расход","Витрата")}</option></select>
        <select value={np} onChange={(e) => setNp(Number(e.target.value))} style={{ ...inpS, maxWidth: 220 }}>
          <option value={0}>{t("— верхний уровень —","— верхній рівень —")}</option>
          {items.filter((c) => c.direction === nd && !c.parent).map((c) => <option key={c.id} value={c.id}>{t("внутри:","всередині:")} {c.name.slice(0, 30)}</option>)}
        </select>
        <button className="btn btn-primary" onClick={add}>+ {t("Добавить","Додати")}</button>
        <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
          <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} />{t("показать скрытые","показати приховані")}
        </label>
      </div>
      {["out", "in"].map((dr) => (
        <div key={dr} style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 800, fontSize: 13, margin: "6px 0" }}>{dr === "out" ? t("Расходы","Витрати") : t("Доходы","Доходи")}</div>
          <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
          <table style={{ width: "100%", fontSize: 12.5, minWidth: isMobile ? 520 : undefined }}>
            <thead><tr><th style={{ textAlign: "left", ...tdS }}>{t("Категория","Категорія")}</th><th style={{ textAlign: "left", ...tdS }}>{t("Фонд (автоматом в операцию)","Фонд (автоматом в операцію)")}</th><th style={{ textAlign: "left", ...tdS }}>{t("Направление","Напрямок")}</th><th></th></tr></thead>
            <tbody>{tops(dr).map((c) => [row(c, 0), ...kids(c.id).map((k) => row(k, 1, c))])}</tbody>
          </table>
          </div>
        </div>
      ))}
    </div>
  );
}

function RefDirections() {
  const { t } = useLang();
  const isMobile = useIsMobile();
  const [items, setItems] = useState<any[]>([]);
  const [nn, setNn] = useState("");
  const load = () => api.get<any>("/api/fin-directions/?page_size=100").then((d) => setItems(d.results || d));
  useEffect(() => { load(); }, []);
  async function add() { if (!nn.trim()) return; await api.post("/api/fin-directions/", { name: nn.trim(), active: true }); setNn(""); load(); }
  async function save(d: any, p: any) { await api.patch(`/api/fin-directions/${d.id}/`, p); load(); }
  async function del(id: number) { if (!confirm(t("Удалить направление? Операции останутся, но потеряют привязку.","Видалити напрямок? Операції лишаться, але втратять привʼязку."))) return; await api.del(`/api/fin-directions/${id}/`); load(); }
  const [dragId, setDragId] = useState<number | null>(null);
  async function dropOn(target: any) {
    if (!dragId || dragId === target.id) { setDragId(null); return; }
    const src = items.find((x) => x.id === dragId);
    const ordered = items.filter((x) => x.id !== dragId);
    const idx = ordered.findIndex((x) => x.id === target.id);
    ordered.splice(idx, 0, src);
    setDragId(null);
    for (let i = 0; i < ordered.length; i++) {
      if (ordered[i].sort_order !== (i + 1) * 10) await api.patch(`/api/fin-directions/${ordered[i].id}/`, { sort_order: (i + 1) * 10 });
    }
    load();
  }
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <input value={nn} onChange={(e) => setNn(e.target.value)} placeholder={t("Новое направление (проект)","Новий напрямок (проект)")} style={{ ...inpS, flex: 1 }} />
        <button className="btn btn-primary" onClick={add}>+ {t("Добавить","Додати")}</button>
      </div>
      <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
      <table style={{ width: "100%", fontSize: 13, minWidth: isMobile ? 480 : undefined }}>
        <thead><tr><th style={{ textAlign: "left", ...tdS }}>{t("Направление","Напрямок")}</th><th>{t("План доход","План дохід")}</th><th>{t("План расходы","План витрати")}</th><th></th></tr></thead>
        <tbody>{items.map((d) => (
          <tr key={d.id} draggable onDragStart={() => setDragId(d.id)} onDragOver={(e) => e.preventDefault()} onDrop={() => dropOn(d)}
            style={{ background: dragId === d.id ? "#fdf3ec" : undefined }}>
            <td style={tdS}><span className="muted" style={{ marginRight: 6, cursor: "grab" }} title={t("Потяни, чтобы поменять порядок","Потягни, щоб змінити порядок")}>⠿</span><input defaultValue={d.name} onBlur={(e) => e.target.value !== d.name && save(d, { name: e.target.value })} style={{ ...inpS, width: "70%", border: "1px solid transparent" }} /></td>
            <td style={{ ...tdS, textAlign: "right" }}><input type="number" defaultValue={d.plan_income} onBlur={(e) => save(d, { plan_income: Number(e.target.value) })} style={{ ...inpS, width: 110, textAlign: "right" }} /></td>
            <td style={{ ...tdS, textAlign: "right" }}><input type="number" defaultValue={d.plan_expense} onBlur={(e) => save(d, { plan_expense: Number(e.target.value) })} style={{ ...inpS, width: 110, textAlign: "right" }} /></td>
            <td style={{ ...tdS, textAlign: "center" }}><span style={{ color: "#ef4444", cursor: "pointer" }} onClick={() => del(d.id)}>✕</span></td>
          </tr>
        ))}</tbody>
      </table>
      </div>
    </div>
  );
}

function RefCounterparties() {
  const { t } = useLang();
  const [items, setItems] = useState<any[]>([]);
  const nav = useNav();
  const load = () => api.get<any>("/api/finance/counterparties/").then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);
  async function renameCp(c: any) {
    const nn = prompt(t("Новое написание контрагента (обновится во ВСЕХ операциях):","Нове написання контрагента (оновиться у ВСІХ операціях):"), c.name);
    if (!nn || nn.trim() === c.name) return;
    await api.post("/api/transactions/counterparty-rename/", { old: c.name, new: nn.trim() });
    load();
  }
  async function delCp(c: any) {
    if (!confirm(t(`Убрать контрагента «${c.name}» из ${c.count} операций? Операции останутся, поле контрагента очистится.`, `Прибрати контрагента «${c.name}» з ${c.count} операцій? Операції лишаться, поле контрагента очиститься.`))) return;
    await api.post("/api/transactions/counterparty-delete/", { name: c.name });
    load();
  }
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("Контрагенты сведены из операций. 🔗 = связан с клиентом CRM (клик откроет).","Контрагенти зведені з операцій. 🔗 = звʼязаний із клієнтом CRM (клік відкриє).")}</div>
      <table style={{ width: "100%", fontSize: 13 }}>
        <thead><tr><th style={{ textAlign: "left", ...tdS }}>{t("Контрагент","Контрагент")}</th><th style={{ textAlign: "center" }}>{t("Операций","Операцій")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th><th style={{ textAlign: "center" }}>{t("Клиент CRM","Клієнт CRM")}</th></tr></thead>
        <tbody>{items.slice(0, 300).map((c, i) => (
          <tr key={i}><td style={tdS}>{c.name} <span style={{ cursor: "pointer", marginLeft: 4 }} title={t("Переименовать во всех операциях","Перейменувати у всіх операціях")} onClick={() => renameCp(c)}><Icon n="✏️" size={13} /></span></td><td style={{ ...tdS, textAlign: "center" }}>{c.count}</td>
            <td style={{ ...tdS, textAlign: "right" }}>{money(c.total)}</td>
            <td style={{ ...tdS, textAlign: "center", whiteSpace: "nowrap" }}>{c.contact_id ? <span style={{ color: "#1d4ed8", cursor: "pointer" }} onClick={() => nav(`/clients?contact=${c.contact_id}`)}><Icon n="🔗" size={13} /> {t("открыть","відкрити")}</span> : <span className="muted">—</span>} <span style={{ color: "#ef4444", cursor: "pointer", marginLeft: 8 }} title={t("Убрать из всех операций","Прибрати з усіх операцій")} onClick={() => delCp(c)}>✕</span></td></tr>
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
function DebtCard({ row, cats, dirs, arts, accs2, t, onClose, onSaved }: any) {
  const [f, setF] = useState<any>(() => ({
    kind: row?.kind || "payable", is_loan: row?.is_loan || false, amount: row?.amount || "", due_date: row?.due_date || "",
    counterparty: row?.counterparty || "", category: row?.category || "", account: row?.account || "",
    fin_direction: row?.fin_direction || "", fin_article: row?.fin_article || "", channel: row?.channel || "",
    deal: row?.deal || "", comment: row?.comment || "",
  }));
  const [busy, setBusy] = useState(false);
  const inp: any = { height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 9px", fontSize: 13, background: "#fff" };
  const lab: any = { fontSize: 11, color: "#64748b", fontWeight: 600, marginBottom: 3 };
  const Fld = "div";
  async function save() {
    if (!f.amount || !f.due_date) { alert(t("Сумма и срок обязательны", "Сума і строк обовʼязкові")); return; }
    setBusy(true);
    const body: any = { ...f, amount: Number(String(f.amount).replace(",", ".")) };
    ["category", "account", "fin_direction", "fin_article", "deal"].forEach((k) => { body[k] = f[k] ? Number(f[k]) : null; });
    try {
      if (row?.id) await api.patch(`/api/planned-payments/${row.id}/`, body);
      else await api.post("/api/planned-payments/", body);
      onSaved(); onClose();
    } catch (e: any) { alert(e?.response?.data?.detail || JSON.stringify(e?.response?.data || "Помилка")); }
    setBusy(false);
  }
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 16, padding: 22, width: "min(680px,96vw)", maxHeight: "92vh", overflowY: "auto" }}>
        <h3 style={{ margin: "0 0 14px" }}>{row?.id ? t("Карточка операции Дт/Кт", "Картка операції Дт/Кт") + ` №${row.id}` : t("Новая запись Дт/Кт", "Новий запис Дт/Кт")}</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Fld><div style={lab}>{t("Тип", "Тип")}</div>
            <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} style={{ ...inp, width: "100%" }}>
              <option value="payable">🔻 {t("Кредиторка (мы должны)", "Кредиторка (ми винні)")}</option>
              <option value="receivable">🔺 {t("Дебиторка (нам должны)", "Дебіторка (нам винні)")}</option>
            </select></Fld>
          {f.kind === "receivable" && (
            <Fld><div style={lab}>{t("Характер дебиторки", "Характер дебіторки")}</div>
              <select value={f.is_loan ? "1" : "0"} onChange={(e) => setF({ ...f, is_loan: e.target.value === "1" })} style={{ ...inp, width: "100%" }}>
                <option value="0">🛒 {t("Продажа (будущая прибыль)", "Продаж (майбутній прибуток)")}</option>
                <option value="1">🤝 {t("Заём — свои деньги в долг (не прибыль)", "Позика — свої гроші в борг (не прибуток)")}</option>
              </select></Fld>
          )}
          <Fld><div style={lab}>{t("Сумма, грн", "Сума, грн")}</div>
            <input type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} style={{ ...inp, width: "100%" }} /></Fld>
          <Fld><div style={lab}>{t("Срок (когда возник долг / оплатить до)", "Строк (коли виник борг / сплатити до)")}</div>
            <input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} style={{ ...inp, width: "100%" }} /></Fld>
          <Fld><div style={lab}>{t("Контрагент", "Контрагент")}</div>
            <input value={f.counterparty} onChange={(e) => setF({ ...f, counterparty: e.target.value })} style={{ ...inp, width: "100%" }} /></Fld>
          <Fld><div style={lab}>{t("Категория", "Категорія")}</div>
            <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} style={{ ...inp, width: "100%" }}>
              <option value="">—</option>
              {cats.filter((c: any) => c.direction === (f.kind === "payable" ? "out" : "in")).map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></Fld>
          <Fld><div style={lab}>{t("Счёт оплаты", "Рахунок оплати")}</div>
            <select value={f.account} onChange={(e) => setF({ ...f, account: e.target.value })} style={{ ...inp, width: "100%" }}>
              <option value="">—</option>
              {accs2.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select></Fld>
          <Fld><div style={lab}>{t("Направление (проект)", "Напрямок (проект)")}</div>
            <select value={f.fin_direction} onChange={(e) => setF({ ...f, fin_direction: e.target.value })} style={{ ...inp, width: "100%" }}>
              <option value="">—</option>
              {dirs.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select></Fld>
          <Fld><div style={lab}>{t("Фонд", "Фонд")}</div>
            <select value={f.fin_article} onChange={(e) => setF({ ...f, fin_article: e.target.value })} style={{ ...inp, width: "100%" }}>
              <option value="">—</option>
              {FUND_GROUPS_G.map(([gk, gl]) => { const gr = arts.filter((a: any) => a.category === gk && !a.parent); return gr.length ? <optgroup key={gk} label={gl}>{gr.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}</optgroup> : null; })}
            </select></Fld>
          <Fld><div style={lab}>{t("Канал", "Канал")}</div>
            <input value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })} placeholder="instagram / tiktok / offline…" style={{ ...inp, width: "100%" }} /></Fld>
          <Fld><div style={lab}>{t("Угода (№)", "Угода (№)")}</div>
            <input type="number" value={f.deal} onChange={(e) => setF({ ...f, deal: e.target.value })} placeholder="65496" style={{ ...inp, width: "100%" }} /></Fld>
        </div>
        <div style={{ marginTop: 12 }}>
          <div style={lab}>{t("Комментарий", "Коментар")}</div>
          <input value={f.comment} onChange={(e) => setF({ ...f, comment: e.target.value })} style={{ ...inp, width: "100%" }} />
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button className="btn btn-primary" disabled={busy} style={{ flex: 1 }} onClick={save}>{busy ? "…" : t("Сохранить", "Зберегти")}</button>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>{t("Закрыть", "Закрити")}</button>
          {row?.id && row.status === "planned" && <button className="btn btn-light" style={{ color: "#dc2626" }} onClick={async () => { if (confirm(t("Удалить запись?", "Видалити запис?"))) { await api.del(`/api/planned-payments/${row.id}/`); onSaved(); onClose(); } }}><Icon n="🗑" size={15} /></button>}
        </div>
      </div>
    </div>
  );
}

// Привʼязати вже зроблений платіж із журналу як (часткове) погашення боргу
function LinkPaymentModal({ row, onClose, onDone }: { row: any; onClose: () => void; onDone: () => void }) {
  const { t } = useLang();
  const [cands, setCands] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [txId, setTxId] = useState<number | 0>(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.get<any>(`/api/planned-payments/${row.id}/pay-candidates/`).then((d) => { setCands(d.rows || []); setLoading(false); }).catch(() => setLoading(false));
  }, [row.id]);
  const rem = Number(row.remaining ?? (Number(row.amount) - Number(row.paid_amount || 0)));
  const ql = q.trim().toLowerCase();
  const shown = cands.filter((r) => !ql
    || String((r.counterparty || "") + " " + (r.comment || "")).toLowerCase().includes(ql)
    || String(Math.round(Number(r.amount))).includes(ql.replace(/\s/g, "")));
  const link = async () => {
    if (!txId) return;
    setBusy(true);
    try {
      const r: any = await api.post(`/api/planned-payments/${row.id}/link-payment/`, { tx_id: txId });
      alert(t("Платёж привязан ✓", "Платіж привʼязано ✓") + `\n` +
        t("зачтено", "зараховано") + `: ${money(Number(r.linked_amount))}` +
        (r.status === "paid" ? "\n" + t("долг закрыт полностью", "борг закрито повністю")
          : "\n" + t("остаток", "залишок") + `: ${money(Number(r.remaining))}`));
      onDone();
    } catch (e: any) { alert(e?.response?.data?.detail || t("Ошибка", "Помилка")); } finally { setBusy(false); }
  };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1000, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "5vh 12px", overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 16, padding: 18, width: 620, maxWidth: "100%", boxShadow: "0 24px 70px rgba(15,23,42,.35)" }}>
        <h3 style={{ margin: "0 0 4px" }}>{t("Привязать платёж из журнала", "Привʼязати платіж із журналу")}</h3>
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>
          {t("Деньги уже ушли — привязываем существующую операцию как погашение (без новой). Можно частично.",
             "Гроші вже пішли — привʼязуємо існуючу операцію як погашення (без нової). Можна частково.")}
          <br />{t("Долг", "Борг")}: <b>{row.counterparty}</b> · {t("остаток", "залишок")}: <b>{money(rem)}</b>
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={t("🔍 Поиск: контрагент, назначение или сумма", "🔍 Пошук: контрагент, призначення або сума")}
          style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 10px", marginBottom: 8 }} />
        <div style={{ maxHeight: 320, overflowY: "auto", border: "1px solid #e2e8f0", borderRadius: 8 }}>
          {loading && <div className="muted" style={{ padding: 10, fontSize: 12.5 }}>{t("Ищу платежи…", "Шукаю платежі…")}</div>}
          {!loading && !shown.length && <div className="muted" style={{ padding: 10, fontSize: 12.5 }}>{t("Подходящих платежей не найдено", "Відповідних платежів не знайдено")}</div>}
          {shown.map((r) => {
            const on = txId === r.id;
            const exact = Math.abs(Number(r.amount) - rem) < 0.01;
            return (
              <div key={r.id} onClick={() => setTxId(on ? 0 : r.id)}
                style={{ display: "flex", gap: 8, alignItems: "center", padding: "9px 10px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", background: on ? "#eef2ff" : "transparent" }}>
                <input type="radio" checked={on} readOnly />
                <b style={{ minWidth: 96, fontSize: 13 }}>{Number(r.amount).toLocaleString()} ₴</b>
                <span className="muted" style={{ fontSize: 12, minWidth: 78 }}>{r.date}</span>
                <span style={{ fontSize: 12.5, flex: 1 }}>{r.counterparty || r.comment || "—"}</span>
                {r.same_contact && <span className="chip" style={{ background: "#eff6ff", color: "#1d4ed8", fontSize: 11 }}>{t("тот же", "той самий")}</span>}
                {exact && <span className="chip" style={{ background: "#f0fdf4", color: "#15803d", fontSize: 11 }}>{t("сумма совпала", "сума збіглася")}</span>}
              </div>
            );
          })}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 14, justifyContent: "flex-end" }}>
          <button className="btn btn-light" onClick={onClose}>{t("Отмена", "Скасувати")}</button>
          <button className="btn btn-primary" disabled={busy || !txId} onClick={link}>{busy ? "…" : t("Привязать как оплату", "Привʼязати як оплату")}</button>
        </div>
      </div>
    </div>
  );
}

function Debts() {
  const { t } = useLang();
  const nav = useNav();
  const cpMap = useCpMap();
  const [cpFilter, setCpFilter] = useState("");
  const isMobile = useIsMobile();
  const [rows, setRows] = useState<any[]>([]);
  const [st, setSt] = useState("planned");
  const [sortF, setSortF] = useState("");
  const [dirFilter, setDirFilter] = useState("");
  const [catFilter, setCatFilter] = useState("");
  const [cats, setCats] = useState<any[]>([]);
  const [accs2, setAccs2] = useState<any[]>([]);
  const [dirs, setDirs] = useState<any[]>([]);
  const [arts, setArts] = useState<any[]>([]);
  const [card, setCard] = useState<any>(undefined); // undefined=закрыто, null=новая, obj=правка
  const load = () => api.get<any>(`/api/planned-payments/?status=${st}&page_size=500`).then((d) => setRows(d.results || d)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [st]);
  useEffect(() => { setSortF(st === "paid" ? "-paid_date" : st === "planned" ? "due_date" : "-due_date"); }, [st]);
  useEffect(() => {
    api.get<any>("/api/categories/?page_size=300").then((d) => setCats(d.results || d)).catch(() => {});
    api.get<any>("/api/accounts/").then((d) => setAccs2((d.results || d).filter((a: any) => a.is_active !== false))).catch(() => {});
    api.get<any>("/api/fin-directions/?page_size=100").then((d) => setDirs(d.results || d)).catch(() => {});
    api.get<any>("/api/finmodel-articles/?page_size=300").then((d) => setArts(d.results || d)).catch(() => {});
  }, []);
  async function markPaid(r: any, e: any) {
    e.stopPropagation();
    const rem = Number(r.remaining ?? (Number(r.amount) - Number(r.paid_amount || 0)));
    const inp = prompt(t(`Сумма погашения. Остаток по этому долгу: ${money(rem)} грн. Можно частично (напр. половину).`, `Сума погашення. Залишок за цим боргом: ${money(rem)} грн. Можна частково (напр. половину).`), String(rem));
    if (inp === null) return;
    const amt = parseFloat(String(inp).replace(",", "."));
    if (!amt || amt <= 0) return;
    await api.post(`/api/planned-payments/${r.id}/mark-paid/`, { amount: amt }); load();
  }
  const openDoc = async (id: number) => {
    try { const u = await api.blobUrl(`/api/integrations/incoming-docs/${id}/view/`); window.open(u, "_blank"); }
    catch { alert(t("Не удалось открыть накладную", "Не вдалося відкрити накладну")); }
  };
  const [payFopDoc, setPayFopDoc] = useState<any>(null);
  const [linkR, setLinkR] = useState<any>(null);   // кредиторка для привʼязки платежу з журналу
  const payFop = (r: any, e: any) => { e.stopPropagation(); setPayFopDoc(r); };
  const Section = ({ kind, title, color }: any) => {
    const arw = (f: string) => (sortF === f ? " ▲" : sortF === "-" + f ? " ▼" : "");
    const Hh = (f: string, label: string) => <th style={{ padding: "4px", cursor: "pointer", whiteSpace: "nowrap" }} onClick={() => setSortF(sortF === f ? "-" + f : f)}>{label}{arw(f)}</th>;
    const sortRows = (arr: any[]) => {
      if (!sortF) return arr;
      const desc = sortF[0] === "-"; const f = desc ? sortF.slice(1) : sortF;
      const g = (r: any) => {
        if (f === "amount") return Number(r.amount || 0);
        if (f === "deal") return Number(r.deal || 0);
        if (f === "due_date" || f === "paid_date") return r[f] || "";
        return String(r[f] || "").toLowerCase();
      };
      return [...arr].sort((a, b) => { const x = g(a), y = g(b); const c = x < y ? -1 : x > y ? 1 : 0; return desc ? -c : c; });
    };
    const list = sortRows(rows.filter((r) => r.kind === kind && !r.is_internal
      && (!cpFilter || String(r.counterparty || "").toLowerCase().includes(cpFilter.toLowerCase()))
      && (!dirFilter || r.fin_direction_name === dirFilter)
      && (!catFilter || r.category_name === catFilter)));
    const total = list.reduce((sm, r) => sm + Number(r.amount || 0), 0);
    if (isMobile) return (
      <div className="panel" style={{ margin: "0 0 12px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
          <b style={{ fontSize: 14 }}>{title}</b>
          <span style={{ fontSize: 18, fontWeight: 800, color }}>{money(total)}</span>
          <span className="muted" style={{ fontSize: 11 }}>{list.length}</span>
        </div>
        {list.map((r) => (
          <div key={r.id} onClick={() => setCard(r)} style={{ borderTop: "1px solid #f1f5f9", padding: "11px 2px", cursor: "pointer" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <span onClick={(e) => e.stopPropagation()} style={{ fontWeight: 600, fontSize: 14 }}><CpText name={r.counterparty} contact={(r as any).contact} cpMap={cpMap} nav={nav} /></span>
              <span style={{ fontWeight: 800, color, fontSize: 15, whiteSpace: "nowrap" }}>{money(Number(r.amount))}</span>
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>{r.due_date}{r.category_name ? " · " + r.category_name : ""}{Number(r.paid_amount) > 0 ? " · " + t("залишок", "залишок") + " " + money(Number(r.remaining)) : ""}</div>
            {st === "paid" && r.paid_date && <div style={{ fontSize: 11.5, color: "#16a34a", marginTop: 2 }}>✓ {r.paid_date}{r.paid_account_name ? ` · ${r.paid_account_name}` : ""}</div>}
            {r.source_doc_id && <div onClick={(e) => { e.stopPropagation(); openDoc(r.source_doc_id); }} style={{ fontSize: 12.5, color: "#2563eb", marginTop: 3 }}><Icon n="📄" size={13} /> {t("Открыть накладную", "Відкрити накладну")}</div>}
            {st === "planned" && <div style={{ display: "flex", gap: 6, marginTop: 9 }} onClick={(e) => e.stopPropagation()}>
              <button className="btn btn-light" style={{ height: 34, fontSize: 12.5, flex: 1 }} onClick={(e) => markPaid(r, e)}>✓ {t("Оплачено", "Оплачено")}</button>
              {r.kind === "payable" && <button className="btn btn-light" style={{ height: 34, fontSize: 12.5, flex: 1 }} title={t("Привязать уже сделанный платёж из журнала (частично)", "Привʼязати вже зроблений платіж із журналу (частково)")} onClick={(e) => { e.stopPropagation(); setLinkR(r); }}><Icon n="🔗" size={13} /> {t("З журналу", "З журналу")}</button>}
              {r.kind === "payable" && <button className="btn btn-light" style={{ height: 34, fontSize: 12.5, flex: 1 }} onClick={(e) => payFop(r, e)}><Icon n="💳" size={13} /> {t("ФОП", "ФОП")}</button>}
            </div>}
          </div>
        ))}
        {!list.length && <div className="muted" style={{ fontSize: 12, padding: 6 }}>{t("Пусто", "Порожньо")}</div>}
      </div>
    );
    return (
      <div className="panel" style={{ margin: "0 0 14px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8 }}>
          <b style={{ fontSize: 15 }}>{title}</b>
          <span style={{ fontSize: 20, fontWeight: 800, color }}>{money(total)}</span>
          <span className="muted" style={{ fontSize: 12 }}>{list.length} {t("шт", "шт")}</span>
        </div>
        <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse", minWidth: 900 }}>
          <thead><tr className="muted" style={{ fontSize: 11, textAlign: "left" }}>
            {Hh("due_date", t("Срок", "Строк"))}{Hh("amount", t("Сумма", "Сума"))}
            {Hh("counterparty", t("Контрагент", "Контрагент"))}{Hh("category_name", t("Категория", "Категорія"))}
            {Hh("fin_direction_name", t("Направление", "Напрямок"))}{Hh("channel", t("Канал", "Канал"))}
            {Hh("deal", t("Угода", "Угода"))}{Hh("comment", t("Комментарий", "Коментар"))}<th></th>
          </tr></thead>
          <tbody>{list.map((r) => (
            <tr key={r.id} onClick={() => setCard(r)} style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer" }} title={t("Открыть карточку", "Відкрити картку")}>
              <td style={{ padding: "6px 4px", whiteSpace: "nowrap" }}>{r.due_date}</td>
              <td style={{ padding: "6px 4px", fontWeight: 700, color, whiteSpace: "nowrap" }}>{money(Number(r.amount))}{Number(r.paid_amount) > 0 && <div style={{ fontWeight: 400, fontSize: 11, color: "#64748b" }}>{t("залишок", "залишок")} {money(Number(r.remaining))}</div>}{st === "paid" && r.paid_date && <div style={{ fontWeight: 400, fontSize: 11, color: "#16a34a" }}>✓ {r.paid_date}{r.paid_account_name ? ` · ${r.paid_account_name}` : ""}</div>}</td>
              <td style={{ padding: "6px 4px" }} onClick={(e) => e.stopPropagation()}><CpText name={r.counterparty} contact={(r as any).contact} cpMap={cpMap} nav={nav} /></td>
              <td style={{ padding: "6px 4px" }}>{r.category_name || "—"}</td>
              <td style={{ padding: "6px 4px" }}>{r.fin_direction_name || "—"}</td>
              <td style={{ padding: "6px 4px" }}>{r.channel || "—"}</td>
              <td style={{ padding: "6px 4px" }} onClick={(e) => e.stopPropagation()}>
                {r.deal ? <a href={`/deals/${r.deal}`} style={{ color: "#2563eb", fontWeight: 600 }}>#{r.deal}</a> : "—"}
              </td>
              <td style={{ padding: "6px 4px", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.comment} onClick={(e) => e.stopPropagation()}>{r.source_doc_id ? <span onClick={() => openDoc(r.source_doc_id)} style={{ cursor: "pointer", color: "#2563eb", textDecoration: "underline" }} title={t("Открыть накладную", "Відкрити накладну")}><Icon n="📄" size={12} /> {r.comment || t("накладна", "накладна")}</span> : (r.comment || "—")}</td>
              <td style={{ padding: "6px 4px", whiteSpace: "nowrap", textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                {st === "planned" && <>
                  <button className="btn btn-light" style={{ height: 26, padding: "0 9px", fontSize: 11.5 }} onClick={(e) => markPaid(r, e)}>✓ {t("Оплачено", "Оплачено")}</button>{" "}
                  {r.kind === "payable" && <><button className="btn btn-light" style={{ height: 26, padding: "0 9px", fontSize: 11.5 }} title={t("Привязать уже сделанный платёж из журнала (частично)", "Привʼязати вже зроблений платіж із журналу (частково)")} onClick={(e) => { e.stopPropagation(); setLinkR(r); }}><Icon n="🔗" size={12} /> {t("З журналу", "З журналу")}</button>{" "}</>}
                  {r.kind === "payable" && <><button className="btn btn-light" style={{ height: 26, padding: "0 9px", fontSize: 11.5 }} title={t("Оплатить с ФОП через Приват (создаст черновик — подпишешь КЕП)", "Оплатити з ФОП через Приват (створить чернетку — підпишеш КЕП)")} onClick={(e) => payFop(r, e)}><Icon n="💳" size={12} /> {t("ФОП", "ФОП")}</button>{" "}</>}
                  <button title={t("Отменить (не платим)", "Скасувати (не платимо)")} onClick={async (e) => { e.stopPropagation(); await api.patch(`/api/planned-payments/${r.id}/`, { status: "canceled" }); load(); }}
                    style={{ border: "none", background: "none", color: "#dc2626", cursor: "pointer", fontSize: 14 }}>✕</button>
                </>}
                {st !== "planned" && <button title={t("Удалить", "Видалити")} onClick={async (e) => { e.stopPropagation(); if (confirm("Видалити запис?")) { await api.del(`/api/planned-payments/${r.id}/`); load(); } }}
                  style={{ border: "none", background: "none", color: "#94a3b8", cursor: "pointer", fontSize: 14 }}><Icon n="🗑" size={15} /></button>}
              </td>
            </tr>
          ))}</tbody>
        </table>
        </div>
        {!list.length && <div className="muted" style={{ fontSize: 12, padding: 6 }}>{t("Пусто", "Порожньо")}</div>}
      </div>
    );
  };
  return (
    <div className="scroll pad">
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>
        {t("Запланированные платежи живут ОТДЕЛЬНО от журнала: на остатки, расходы и P&L не влияют, пока не оплачены. «✓ Оплачено» — создаёт фактическую операцию в журнале со всеми полями. Клик по строке — карточка операции.",
           "Заплановані платежі живуть ОКРЕМО від журналу: на залишки, витрати і P&L не впливають, доки не оплачені. «✓ Оплачено» — створює фактичну операцію в журналі з усіма полями. Клік по рядку — картка операції.")}
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <button className="btn btn-primary" onClick={() => setCard(null)}><Icon n="➕" size={14} /> {t("Добавить", "Додати")}</button>
        <label className="btn btn-light" style={{ cursor: "pointer" }} title={t("Импорт акта Новой Почты (Специфікація + Рахунок .xlsx)","Імпорт акта Нової Пошти (Специфікація + Рахунок .xlsx)")}>
          <Icon n="📤" size={14} /> {t("Акт НП","Акт НП")}
          <input type="file" accept=".xlsx" multiple style={{ display: "none" }} onChange={async (e) => {
            const fs = Array.from(e.target.files || []); (e.target as any).value = "";
            if (!fs.length) return;
            const spec = fs.find((f) => f.name.toLowerCase().includes("специф")) || fs.find((f) => !/рахун/i.test(f.name)) || fs[0];
            const rah = fs.find((f) => f.name.toLowerCase().includes("рахун"));
            const build = (commit: boolean) => { const fd = new FormData(); fd.append("spec", spec); if (rah) fd.append("rahunok", rah); if (commit) fd.append("commit", "1"); return fd; };
            try {
              const dry: any = await (api as any).uploadForm("/api/planned-payments/import-np-act/", build(false));
              if (dry.already_imported) { alert(t("Этот акт уже загружен","Цей акт вже завантажено") + ` №${dry.invoice_number}`); return; }
              const msg = t("Акт Новой Почты","Акт Нової Пошти") + ` №${dry.invoice_number} ${t("от","від")} ${dry.invoice_date}\n` +
                t("Сумма","Сума") + `: ${dry.amount} ₴ (${t("НДС","ПДВ")} ${dry.vat || 0})\n` +
                t("Отправлений","Відправлень") + `: ${dry.shipments_count} · ${t("к сделкам","до сделок")}: ${dry.matched_deals} · ${t("без сделки","без сделки")}: ${dry.unmatched}\n\n` +
                t("Создать кредиторку на Нову Пошту и разнести доставку по сделкам?","Створити кредиторку на Нову Пошту і рознести доставку по сделкам?");
              if (!confirm(msg)) return;
              const done: any = await (api as any).uploadForm("/api/planned-payments/import-np-act/", build(true));
              alert(t("Готово ✓ Кредиторка создана","Готово ✓ Кредиторка створена") + ` №${done.payable_id}, ` + t("сделок обновлено","сделок оновлено") + `: ${done.deals_updated}`);
              load();
            } catch (err: any) { alert(err?.response?.data?.detail || t("Не удалось загрузить акт","Не вдалося завантажити акт")); }
          }} />
        </label>
        <div style={{ width: 10 }} />
        {[["planned", t("Запланированные", "Заплановані")], ["paid", t("Оплаченные", "Оплачені")], ["canceled", t("Отменённые", "Скасовані")]].map(([k, l]) => (
          <button key={k} className={"btn" + (st === k ? " btn-primary" : " btn-light")} onClick={() => setSt(k as string)}>{l}</button>
        ))}
        <input value={cpFilter} onChange={(e) => setCpFilter(e.target.value)} placeholder={t("🔎 Фильтр по контрагенту", "🔎 Фільтр за контрагентом")} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 10px", fontSize: 13, minWidth: 210 }} />
        {cpFilter && <button className="btn btn-light" onClick={() => setCpFilter("")} title={t("Сбросить", "Скинути")}>✕</button>}
        <select value={dirFilter} onChange={(e) => setDirFilter(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px", fontSize: 13 }}>
          <option value="">{t("Все направления", "Всі напрямки")}</option>
          {dirs.map((d: any) => <option key={d.id} value={d.name}>{d.name}</option>)}
        </select>
        <select value={catFilter} onChange={(e) => setCatFilter(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px", fontSize: 13, maxWidth: 220 }}>
          <option value="">{t("Все категории", "Всі категорії")}</option>
          {cats.map((c: any) => <option key={c.id} value={c.name}>{c.name}</option>)}
        </select>
        {(dirFilter || catFilter) && <button className="btn btn-light" onClick={() => { setDirFilter(""); setCatFilter(""); }} title={t("Сбросить фильтры", "Скинути фільтри")}>✕ {t("фильтры", "фільтри")}</button>}
      </div>
      {linkR && <LinkPaymentModal row={linkR} onClose={() => setLinkR(null)} onDone={() => { setLinkR(null); load(); }} />}
      {payFopDoc && <PayFopModal r={payFopDoc} onClose={() => setPayFopDoc(null)} onDone={load} />}
      <Section kind="payable" title={"🔻 " + t("Кредиторка — мы должны", "Кредиторка — ми винні")} color="#dc2626" />
      <Section kind="receivable" title={"🔺 " + t("Дебиторка — нам должны", "Дебіторка — нам винні")} color="#16a34a" />
      {(() => {
        const intl = rows.filter((r: any) => r.is_internal && (!cpFilter || (String(r.counterparty || "") + " " + String(r.contact_name || "")).toLowerCase().includes(cpFilter.toLowerCase())));
        const itotal = intl.reduce((sm: number, r: any) => sm + Number(r.amount || 0), 0);
        return (
          <div className="panel" style={{ margin: "0 0 14px", borderLeft: "4px solid #C67D5F", borderRadius: 0 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4, flexWrap: "wrap" }}>
              <b style={{ fontSize: 15 }}>🔁 {t("Взаиморасчёты между подразделениями", "Взаєморозрахунки між підрозділами")}</b>
              <span style={{ fontSize: 20, fontWeight: 800, color: "#C67D5F" }}>{money(itotal)}</span>
              <span className="muted" style={{ fontSize: 12 }}>{intl.length} {t("шт", "шт")}</span>
            </div>
            <div className="muted" style={{ fontSize: 11.5, marginBottom: 8, lineHeight: 1.45 }}>{t("Внутренний долг между направлениями бизнеса — на баланс компании НЕ влияет (нетто = 0). Одно направление одолжило (заплатило со своей кассы) — другие ему должны. В общую кредиторку/дебиторку выше НЕ входит.", "Внутрішній борг між напрямками бізнесу — на баланс компанії НЕ впливає (нетто = 0). Одне направлення позичило (сплатило зі своєї каси) — інші йому винні. У загальну кредиторку/дебіторку вище НЕ входить.")}</div>
            {intl.length === 0 ? <div className="muted" style={{ fontSize: 12 }}>{t("Пока пусто — появится при распределении платежа между подразделениями.", "Поки порожньо — зʼявиться при розподілі платежу між підрозділами.")}</div> : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse", minWidth: 640 }}>
                  <thead><tr className="muted" style={{ fontSize: 11, textAlign: "left" }}>
                    <th style={{ padding: 4 }}>{t("Срок", "Строк")}</th><th style={{ padding: 4 }}>{t("Кто должен", "Хто винен")}</th><th style={{ padding: 4 }}></th><th style={{ padding: 4 }}>{t("Кому", "Кому")}</th><th style={{ padding: 4, textAlign: "right" }}>{t("Сумма", "Сума")}</th><th style={{ padding: 4 }}>{t("Статья", "Стаття")}</th>
                  </tr></thead>
                  <tbody>{intl.map((r: any) => (
                    <tr key={r.id} onClick={() => setCard(r)} style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer" }} title={t("Открыть карточку", "Відкрити картку")}>
                      <td style={{ padding: "6px 4px", whiteSpace: "nowrap" }}>{r.due_date}</td>
                      <td style={{ padding: "6px 4px" }}>{r.contact ? <a onClick={(e) => { e.stopPropagation(); nav("/clients/" + r.contact); }} style={{ color: "#0e7490", fontWeight: 600, cursor: "pointer", textDecoration: "none" }}>{r.contact_name}</a> : r.contact_name}</td>
                      <td style={{ padding: "6px 4px", color: "#94a3b8", textAlign: "center" }}>→</td>
                      <td style={{ padding: "6px 4px" }}>{r.counterparty_contact ? <a onClick={(e) => { e.stopPropagation(); nav("/clients/" + r.counterparty_contact); }} style={{ color: "#0e7490", fontWeight: 600, cursor: "pointer", textDecoration: "none" }}>{r.counterparty}</a> : r.counterparty}</td>
                      <td style={{ padding: "6px 4px", fontWeight: 700, textAlign: "right", color: "#C67D5F", whiteSpace: "nowrap" }}>{money(Number(r.amount))}</td>
                      <td style={{ padding: "6px 4px" }}>{r.category_name || "—"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </div>
        );
      })()}
      {card !== undefined && <DebtCard row={card} cats={cats} dirs={dirs} arts={arts} accs2={accs2} t={t} onClose={() => setCard(undefined)} onSaved={load} />}
    </div>
  );
}


function Planning() {
  const [period, setPeriod] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; });
  const { t } = useLang();
  const isMobile = useIsMobile();
  const { can: canP } = useAuth();
  const canAcc = canP("finance.plan.accounts") || canP("finance.accounts.manage") || canP("roles.manage");
  const [data, setData] = useState<any>(null);
  const [dirs, setDirs] = useState<any[]>([]);
  const [alloc, setAlloc] = useState<any>(null); // {fund} модалка ручного розподілу
  const [auto, setAuto] = useState(false);       // модалка авто-розподілу виручки
  const [openAlloc, setOpenAlloc] = useState<number | null>(null); // розгорнутий список розподілів фонду
  const [spend, setSpend] = useState<any>(null); // фонд, з якого робимо витрата
  const [debts, setDebts] = useState<any>({ pay: 0, rec: 0, payN: 0, recN: 0 });
  const load = () => api.get<any>(`/api/finance/funds/?period=${period}`).then(setData);
  useEffect(() => { load(); }, [period]);
  useEffect(() => { const iv = setInterval(() => { api.get<any>(`/api/finance/funds/?period=${period}`).then((d) => setData((prev: any) => JSON.stringify(prev) === JSON.stringify(d) ? prev : d)).catch(() => {}); }, 10000); return () => clearInterval(iv); }, [period]);
  useEffect(() => {
    api.get<any>("/api/planned-payments/?status=planned&page_size=500").then((d) => {
      const rows = d.results || d;
      const pay = rows.filter((r: any) => r.kind === "payable");
      const rec = rows.filter((r: any) => r.kind === "receivable");
      setDebts({ pay: pay.reduce((s: number, r: any) => s + Number(r.amount || 0), 0), payN: pay.length,
                 rec: rec.reduce((s: number, r: any) => s + Number(r.amount || 0), 0), recN: rec.length });
    }).catch(() => {});
  }, []);
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
          <button className="btn btn-light" style={{ fontSize: 11, padding: "3px 8px", marginLeft: 4, color: "#dc2626" }} title={t("Сделать расход из этого фонда (наполняет «Потрачено»)","Зробити витрату з цього фонду (наповнює «Витрачено»)")} onClick={() => setSpend(f)}>− {t("расход","витрата")}</button>
        </div>
        {open && <AllocList fundId={f.id} period={period} onChanged={load} />}
        {(f.subfunds || []).map((x: any) => <FundRow key={x.id} f={x} sub />)}
      </>
    );
  }

  if (!data) return <div className="spin">{t("Загрузка фондов…","Завантаження фондів…")}</div>;
  const debtsBar = (debts.payN > 0 || debts.recN > 0) ? (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
      {debts.payN > 0 && <div className="panel" style={{ margin: 0, padding: "8px 14px", borderLeft: "4px solid #dc2626" }}>
        🔻 {t("Кредиторка (мы должны):", "Кредиторка (ми винні):")} <b style={{ color: "#dc2626" }}>{money(debts.pay)}</b> <span className="muted" style={{ fontSize: 11 }}>({debts.payN} {t("платежей — учитывай в планах", "платежів — враховуй у планах")})</span>
      </div>}
      {debts.recN > 0 && <div className="panel" style={{ margin: 0, padding: "8px 14px", borderLeft: "4px solid #16a34a" }}>
        🔺 {t("Дебиторка (нам должны):", "Дебіторка (нам винні):")} <b style={{ color: "#16a34a" }}>{money(debts.rec)}</b> <span className="muted" style={{ fontSize: 11 }}>({debts.recN})</span>
      </div>}
    </div>
  ) : null;
  return (
    <>
      <div className="note"><Icon n="💼" size={14} /> {t("Деньги приходят на счёт → распределяешь по фондам-конвертам. В каждом фонде:","Гроші приходять на рахунок → розподіляєш по фондах-конвертах. У кожному фонді:")} <b>{t("Распределено","Розподілено")}</b> {t("(сколько положил)","(скільки поклав)")} − <b>{t("Потрачено","Витрачено")}</b> {t("(сколько списал)","(скільки списав)")} = <b>{t("Остаток","Залишок")}</b>. {t("Порядок:","Порядок:")} <b>ФВ → ФМ → ФСКД</b>.<br/><span style={{fontSize:12}}><Icon n="📌" size={13} /> <b>{t("«Потрачено»","«Витрачено»")}</b> {t("наполняется, когда создаёшь расход с этим фондом — кнопкой «","наповнюється, коли створюєш витрату з цим фондом — кнопкою «")}<b>{t("− расход","− витрата")}</b>{t("» тут или в Журнале выбираешь Фонд = этот. Тогда сумма появляется в столбце.","» тут або у Журналі обираєш Фонд = цей. Тоді сума зʼявляється у стовпці.")}</span></div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <span className="muted" style={{ fontSize: 13 }}>{t("Месяц","Місяць")}:</span>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setAuto(true)}><Icon n="⚡" size={14} /> {t("Авто-распределение выручки","Авто-розподіл виручки")}</button>
      </div>
      {debtsBar}

      {/* блоки-підсумки зверху */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <div className="panel" style={{ flex: "1 1 180px", padding: "12px 14px", background: "#eff6ff", margin: 0 }}>
          <div className="muted" style={{ fontSize: 12 }} title={t("Деньги на счетах, ещё НЕ разложенные по фондам","Гроші на рахунках, ще НЕ розкладені по фондах")}>{t("К распределению","До розподілу")}</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: "#2563eb" }}>{money(data.accounts.filter((x: any) => x.in_planning !== false).reduce((a: number, x: any) => a + x.balance, 0) - Math.max(0, data.totals.balance))}</div>
        </div>
        <div className="panel" style={{ flex: "1 1 180px", padding: "12px 14px", background: "#f0fdf4", margin: 0 }}>
          <div className="muted" style={{ fontSize: 12 }} title={t("Сумма остатков во всех фондах-конвертах","Сума залишків у всіх фондах-конвертах")}>{t("Остаток в фондах","Залишок у фондах")}</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: "#059669" }}>{money(data.totals.balance)}</div>
        </div>
      </div>

      {/* рахунки — список збоку (як у журналі), фонди — праворуч */}
      <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", gap: 12, alignItems: "flex-start" }}>
      <div className="panel" style={{ width: isMobile ? "100%" : 235, minWidth: isMobile ? 0 : 150, maxWidth: isMobile ? "100%" : 560, flex: "0 0 auto", margin: 0, maxHeight: isMobile ? "40vh" : "72vh", overflowY: "auto", resize: isMobile ? "none" : "horizontal" as any, overflowX: "hidden" }}>
        <b style={{ fontSize: 13 }}><Icon n="🏦" size={13} /> {t("Счета","Рахунки")}</b>
        <div className="muted" style={{ fontSize: 10.5, margin: "2px 0 4px" }}>{t("В «К распределению» идут только выделенные счета.","У «До розподілу» йдуть лише виділені рахунки.")}{canAcc ? " " + t("Клик по счёту — вкл/выкл (общее для всех).","Клік по рахунку — увімк/вимк (спільне для всіх).") : ""}</div>
        {data.accounts.map((a: any) => {
          const onP = a.in_planning !== false;
          return (
            <div key={a.id}
              onClick={async () => { if (!canAcc) return; await api.patch(`/api/accounts/${a.id}/`, { in_planning: !onP }); load(); }}
              title={a.name + " — " + money2(a.balance) + "\n" + (canAcc ? t("Клик — включить/исключить счёт из «К распределению»","Клік — увімкнути/виключити рахунок з «До розподілу»") : t("Менять состав может тот, у кого право «Планування: обирати рахунки»","Змінювати склад може той, у кого право «Планування: обирати рахунки»"))}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 6px", margin: "2px 0", borderRadius: 7, fontSize: 12.5, cursor: canAcc ? "pointer" : "default",
                       background: onP ? "color-mix(in srgb, var(--brand) 15%, transparent)" : "transparent",
                       borderLeft: onP ? "3px solid var(--brand)" : "3px solid transparent",
                       opacity: onP ? 1 : 0.5, fontWeight: onP ? 600 : 400 }}>
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
              <b style={{ fontSize: 11.5, color: a.balance < 0 ? "#dc2626" : "#16a34a", whiteSpace: "nowrap" }}>{money2(a.balance)}</b>
            </div>
          );
        })}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>

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

      </div>
      </div>
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
  useEffect(() => { api.get<any>("/api/categories/?page_size=500").then((d) => setCats(d.results || d)).catch(() => setCats([])); }, []);
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
        currency, rate: Number(rate) || 1, comment: comment || `Витрата: ${fund.name}` });
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
      <div className="note"><Icon n="💰" size={14} /> {t("ЗП считается","ЗП рахується")} <b>{t("без жёсткого GATE","без жорсткого GATE")}</b>: {t("премии открываются поэтапно с 70% плана (×0.3→×1.3). Ставки меняются во вкладке «Финмодель → ЗП». Планы — во вкладке «Планы».","премії відкриваються поетапно з 70% плану (×0.3→×1.3). Ставки змінюються у вкладці «Фінмодель → ЗП». Плани — у вкладці «Плани».")}</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <span className="muted" style={{ fontSize: 13 }}>{t("Месяц","Місяць")}:</span>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} />
        <div style={{ flex: 1 }} />
        <span className="muted" style={{ fontSize: 12 }}>{t("ФОТ-прогноз","ФОТ-прогноз")}: <b>{money(c.total_payroll)}</b></span>
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
              <label style={{ fontSize: 12 }} title={t("Амбиция — сверх-результат","Амбіція — надрезультат")}>🟦 {t("Амбиция","Амбіція")} <input type="number" defaultValue={p.ambition_revenue || 0} onBlur={(e) => save(r.user_id, { ambition_revenue: Number(e.target.value) })} style={inp} /></label>
            </div>
          </div>
        );
      })}
    </>
  );
}

const CAT_LABEL: Record<string, React.ReactNode> = {
  revenue_fund: "Фонди виручки (% від кожної угоди)", payment_fee: "Витрати на обробку (грн/угода)",
  variable: <><Icon n="🔁" size={13} /> Змінні витрати (ростуть із продажами)</>, fixed: <><Icon n="📌" size={13} /> Постійні витрати (фікс щомісяця)</>,
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
      <div className="note"><Icon n="🚀" size={14} /> <b>{t("Рост прибыли","Зростання прибутку")}</b> {t("— план от совещательной системы: бизнес-аналитик, финаналитик, РОП, коуч по команде и маркетолог проанализировали бизнес и конкурентов, проверили друг друга и составили безопасный план удвоения чистой прибыли за 2-3 месяца.","— план від дорадчої системи: бізнес-аналітик, фінаналітик, РОП, коуч команди та маркетолог проаналізували бізнес і конкурентів, перевірили одне одного й склали безпечний план подвоєння чистого прибутку за 2-3 місяці.")}</div>
      {!rep ? (
        <div className="muted" style={{ fontSize: 14, padding: 20, textAlign: "center" }}>{t("Отчёт ещё готовится агентами или не сформирован. Зайди немного позже — он появится тут автоматически.","Звіт ще готується агентами або не сформований. Зайди трохи пізніше — він зʼявиться тут автоматично.")}</div>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 8 }}>
            <h2 style={{ margin: 0, fontSize: 20 }}>{rep.title}</h2>
            <span className="muted" style={{ fontSize: 12 }}>{new Date(rep.created_at).toLocaleString("ru")}</span>
          </div>
          <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
            <div style={{ marginTop: 10 }} dangerouslySetInnerHTML={{ __html: mdToHtml(rep.body) }} />
          </div>
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
  salary: "Ставки ЗП: оклад, % обороту, % маржі, премії. Змінюєш тут → бонус у картці угоди і ЗП оновлюються синхронно.",
};

// Групи фондів у логіці Finmap: спочатку Виручки, потім Маржі (пост/змінні), потім СКД
const FUND_GROUPS: { key: string; label: React.ReactNode; color: string; cats: string[] }[] = [
  { key: "revenue", label: <><Icon n="📊" size={13} /> ФОНДИ ВИРУЧКИ (ФВ)</>, color: "#2563eb", cats: ["revenue_fund"] },
  { key: "margin", label: <><Icon n="💎" size={13} /> ФОНДИ МАРЖІ (ФМ) · постійні + змінні</>, color: "#7c3aed", cats: ["fixed", "variable"] },
  { key: "skd", label: <><Icon n="🎯" size={13} /> ФОНДИ СКОРИГОВАНОГО ДОХОДУ (ФСКД)</>, color: "#059669", cats: ["skd"] },
  { key: "upr", label: <><Icon n="🏛" size={13} /> УПРАВЛІНСЬКІ (УПР)</>, color: "#475569", cats: ["upr_cat2", "upr_cat3"] },
  { key: "other", label: <><Icon n="⚙️" size={13} /> ІНШЕ / КОНФІГ</>, color: "#64748b", cats: ["payment_fee", "warehouse_rate", "config"] },
  { key: "salary", label: <><Icon n="💰" size={13} /> ЗП / KPI МЕНЕДЖЕРА (ставки)</>, color: "#d97706", cats: ["salary"] },
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


function TriageTab() {
  /* Рознесення сміттєвих категорій: пропозиція з історії/коментаря, масове застосування. */
  const { t } = useLang();
  const [rows, setRows] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [sel, setSel] = useState<Record<number, boolean>>({});
  const [choice, setChoice] = useState<Record<number, string>>({});
  const [q, setQ] = useState("");
  const [onlySug, setOnlySug] = useState(false);
  const [limit, setLimit] = useState(200);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const load = () => api.get<any>("/api/transactions/triage/").then((d) => { setRows(d || []); setSel({}); setChoice({}); });
  useEffect(() => {
    load();
    api.get<any>("/api/categories/?page_size=400").then((d) => setCats((d.results || d).filter((c: any) => !c.hidden)));
  }, []);
  const catName = (id: number) => cats.find((c) => c.id === id)?.name || "";
  const valOf = (r: any) => choice[r.id] !== undefined ? choice[r.id] : (r.to_transfer ? "TR" : (r.suggest ? String(r.suggest) : ""));
  const ql = q.toLowerCase();
  const vis = rows.filter((r) => (!onlySug || valOf(r)) && (!ql || ((r.counterparty || "") + " " + (r.comment || "") + " " + r.amount_uah).toLowerCase().includes(ql)));
  const shown = vis.slice(0, limit);
  const selRows = vis.filter((r) => sel[r.id] && valOf(r));
  async function apply(rowsToApply: any[]) {
    if (!rowsToApply.length || busy) return;
    setBusy(true); setMsg("");
    const items = rowsToApply.map((r) => {
      const v = valOf(r);
      return v === "TR" ? { id: r.id, to_transfer: true } : { id: r.id, category: Number(v) };
    });
    try {
      const res = await api.post<any>("/api/transactions/triage-apply/", { items });
      setMsg(t("Готово: разнесено ", "Готово: рознесено ") + (res.updated || 0) + t(" операций", " операцій"));
      load();
    } catch { setMsg(t("Ошибка применения", "Помилка застосування")); }
    finally { setBusy(false); }
  }
  const tdT: React.CSSProperties = { padding: "6px 8px", borderBottom: "1px solid #f1f5f9", verticalAlign: "top", fontSize: 12.6 };
  return (
    <div className="panel">
      <div className="note" style={{ marginBottom: 10 }}><Icon n="🧹" size={14} /> {t("Операции из «Категории расходов/доходов» (мусорные из импорта). Предложение уже подставлено в селект — правь где нужно, отмечай галочками и жми «Применить». Категория + фонд + направление проставятся сразу.","Операції з «Категории расходов/доходов» (сміттєві з імпорту). Пропозиція вже підставлена у селект — виправляй де треба, відмічай галочками і тисни «Застосувати». Категорія + фонд + напрямок проставляться одразу.")}</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Поиск…","Пошук…")} style={{ ...inpS, minWidth: 200 }} />
        <label style={{ fontSize: 12.5, display: "flex", gap: 5, alignItems: "center" }}>
          <input type="checkbox" checked={onlySug} onChange={(e) => setOnlySug(e.target.checked)} />{t("только с предложением","тільки з пропозицією")}
        </label>
        <button className="btn btn-light" onClick={() => { const n: any = {}; vis.forEach((r) => { if (valOf(r)) n[r.id] = true; }); setSel(n); }}>{t("Выделить все с предложением","Виділити всі з пропозицією")} ({vis.filter((r) => valOf(r)).length})</button>
        <button className="btn btn-primary" disabled={!selRows.length || busy} onClick={() => apply(selRows)}>
          {busy ? "…" : "✓ " + t("Применить отмеченные","Застосувати відмічені") + " (" + selRows.length + ")"}
        </button>
        <span className="muted" style={{ fontSize: 12.5 }}>{t("всего","усього")}: {rows.length} · {t("показано","показано")}: {shown.length}</span>
        {msg && <b style={{ color: "#16a34a", fontSize: 12.5 }}>{msg}</b>}
      </div>
      <div style={{ overflowX: "auto", border: "1px solid #e2e8f0", borderRadius: 12, background: "#fff" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1000 }}>
          <thead><tr>
            <th style={{ ...tdT, background: "#f8fafc" }}><input type="checkbox" onChange={(e) => { const n: any = { ...sel }; shown.forEach((r) => { if (valOf(r)) n[r.id] = e.target.checked; }); setSel(n); }} /></th>
            {[t("Дата","Дата"), t("Сумма","Сума"), t("Контрагент","Контрагент"), t("Комментарий","Коментар"), t("Станет (категория)","Стане (категорія)"), t("Откуда","Звідки"), ""].map((h, i) => <th key={i} style={{ ...tdT, background: "#f8fafc", textAlign: "left", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".05em", color: "#64748b" }}>{h}</th>)}
          </tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} style={{ background: sel[r.id] ? "#fdf5ef" : undefined }}>
                <td style={tdT}><input type="checkbox" checked={!!sel[r.id]} disabled={!valOf(r)} onChange={(e) => setSel({ ...sel, [r.id]: e.target.checked })} /></td>
                <td style={{ ...tdT, whiteSpace: "nowrap" }}>{r.date}<div className="muted" style={{ fontSize: 10.5 }}>{r.direction === "in" ? "▲ " + t("доход","дохід") : "▼ " + t("расход","витрата")}</div></td>
                <td style={{ ...tdT, textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>{Number(r.amount_uah).toLocaleString("ru")}</td>
                <td style={{ ...tdT, maxWidth: 170, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 600 }} title={r.counterparty}>{r.counterparty || "—"}</td>
                <td style={{ ...tdT, maxWidth: 360, wordBreak: "break-word", color: "#5b6472" }}>{r.comment || "—"}</td>
                <td style={tdT}>
                  <select value={valOf(r)} onChange={(e) => setChoice({ ...choice, [r.id]: e.target.value })}
                    style={{ ...inpS, fontSize: 12, padding: "4px 6px", maxWidth: 260, color: valOf(r) ? "#0f172a" : "#94a3b8" }}>
                    <option value="">{t("— не трогать —","— не чіпати —")}</option>
                    <option value="TR">⇄ {t("Перевод (вне П&Л)","Переказ (поза П&Л)")}</option>
                    {cats.filter((c: any) => c.direction === r.direction).map((c: any) => <option key={c.id} value={String(c.id)}>{c.parent ? "└ " : ""}{c.name.slice(0, 44)}</option>)}
                  </select>
                </td>
                <td style={{ ...tdT, fontSize: 11, color: "#94a3b8", whiteSpace: "nowrap" }}>{r.src || ""}</td>
                <td style={tdT}><a href={"/finance?tx=" + r.id} target="_blank" rel="noreferrer" style={{ color: "#C67D5F", fontWeight: 700, fontSize: 11.5, textDecoration: "none", border: "1px solid #eadfd6", borderRadius: 7, padding: "2px 8px", whiteSpace: "nowrap" }}>{t("открыть","відкрити")} ↗</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {vis.length > limit && <div style={{ textAlign: "center", margin: "12px 0" }}><button className="btn btn-light" onClick={() => setLimit(limit + 300)}>{t("Показать ещё","Показати ще")} ({vis.length - limit})</button></div>}
    </div>
  );
}


export function ClientPick({ value, label, placeholder, onPick }: { value?: number; label?: string; placeholder?: string; onPick: (id: number, name: string) => void }) {
  /* Автокомпліт клієнта CRM: пошук по імені/телефону, ✕ — зняти привʼязку. */
  const [q, setQ] = useState(label || "");
  const [opts, setOpts] = useState<any[]>([]);
  const [openL, setOpenL] = useState(false);
  useEffect(() => { setQ(label || ""); }, [label]);
  useEffect(() => {
    if (q.trim().length < 2 || q === label) { setOpts([]); setOpenL(false); return; }
    const h = setTimeout(() => {
      api.get<any>(`/api/contacts/?search=${encodeURIComponent(q.trim())}&page_size=8`)
        .then((d) => { setOpts(d.results || d || []); setOpenL(true); }).catch(() => {});
    }, 300);
    return () => clearTimeout(h);
  }, [q]); // eslint-disable-line
  const nm = (o: any) => o.display_name || (`${o.first_name || ""} ${o.last_name || ""}`.trim()) || o.nickname || o.phone || ("#" + o.id);
  return (
    <div style={{ position: "relative", marginBottom: 8 }}>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder || "почни вводити імʼя або телефон…"}
        style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: value ? "0 26px 0 10px" : "0 10px", fontSize: 13, background: value ? "#f0fdfa" : "#fff" }} />
      {value ? <span onClick={() => { onPick(0, ""); setQ(""); }} title="Прибрати клієнта"
        style={{ position: "absolute", right: 8, top: 7, cursor: "pointer", color: "#94a3b8", fontWeight: 700 }}>✕</span> : null}
      {openL && opts.length > 0 && (
        <div style={{ position: "absolute", top: 36, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 10px 30px rgba(15,23,42,.15)", zIndex: 30, maxHeight: 220, overflowY: "auto" }}>
          {opts.map((o) => (
            <div key={o.id} onClick={() => { onPick(o.id, nm(o)); setOpenL(false); }}
              style={{ padding: "7px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f8fafc" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#f8fafc")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "")}>
              <b>{nm(o)}</b>{o.phone ? <span className="muted" style={{ marginLeft: 6, fontSize: 11.5 }}>{o.phone}</span> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


function FundPick({ value, arts, onPick }: { value: number; arts: any[]; onPick: (id: number) => void }) {
  /* Пошук фонду: набираєш частину назви — список фільтрується; клік — вибір; ✕ — без фонду. */
  const { t } = useLang();
  const sel = arts.find((a) => a.id === value);
  const [q, setQ] = useState("");
  const [openL, setOpenL] = useState(false);
  useEffect(() => { setQ(sel ? sel.name : ""); }, [value]); // eslint-disable-line
  const ql = q.trim().toLowerCase();
  const filtered = (openL && ql && (!sel || q !== sel.name))
    ? arts.filter((a) => (a.name + " " + (a.category_display || "")).toLowerCase().includes(ql))
    : arts;
  return (
    <div style={{ position: "relative", marginBottom: 8 }}>
      <input value={q}
        onChange={(e) => { setQ(e.target.value); setOpenL(true); }}
        onFocus={() => setOpenL(true)}
        onBlur={() => setTimeout(() => setOpenL(false), 180)}
        placeholder={t("— без фонда — (начни вводить для поиска)","— без фонду — (почни вводити для пошуку)")}
        style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: value ? "0 26px 0 10px" : "0 10px", fontSize: 13, background: value ? "#f0fdf4" : "#fff" }} />
      {value ? <span onMouseDown={(e) => { e.preventDefault(); onPick(0); setQ(""); }} title={t("Без фонда","Без фонду")}
        style={{ position: "absolute", right: 8, top: 7, cursor: "pointer", color: "#94a3b8", fontWeight: 700 }}>✕</span> : null}
      {openL && (
        <div style={{ position: "absolute", top: 36, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 10px 30px rgba(15,23,42,.15)", zIndex: 40, maxHeight: 280, overflowY: "auto" }}>
          {filtered.length === 0 && <div className="muted" style={{ padding: "8px 10px", fontSize: 12.5 }}>{t("Ничего не найдено","Нічого не знайдено")}</div>}
          {FUND_GROUPS_G.map(([gk, gl]) => {
            const gr = filtered.filter((a) => a.category === gk && !a.parent);
            if (!gr.length) return null;
            return (
              <div key={gk}>
                <div style={{ padding: "6px 10px 3px", fontSize: 10.5, fontWeight: 800, letterSpacing: ".04em", color: "#0f172a", background: "#f5efe9", position: "sticky", top: 0 }}>{gl}</div>
                {gr.map((a) => (
                  <div key={a.id} onMouseDown={(e) => { e.preventDefault(); onPick(a.id); setQ(a.name); setOpenL(false); }}
                    style={{ padding: "6px 10px 6px 16px", cursor: "pointer", fontSize: 12.5, borderBottom: "1px solid #f8fafc", background: a.id === value ? "#f0fdf4" : "" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#f8fafc")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = a.id === value ? "#f0fdf4" : "")}>
                    {a.name}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


export function CatPick({ value, direction, cats, onPick }: { value: string; direction: string; cats: any[]; onPick: (name: string) => void }) {
  /* Дерево категорій: категорія ЖИРНИМ → підкатегорії з відступом; пошук фільтрує; клік — вибір. */
  const { t } = useLang();
  const [q, setQ] = useState(value || "");
  const [openL, setOpenL] = useState(false);
  useEffect(() => { setQ(value || ""); }, [value]);
  const mine = cats.filter((c: any) => !c.hidden && c.direction === direction);
  const tops = mine.filter((c: any) => !c.parent);
  const kidsOf = (pid: number) => mine.filter((c: any) => c.parent === pid);
  const ql = (openL && q.trim() && q !== value) ? q.trim().toLowerCase() : "";
  const matches = (c: any) => !ql || c.name.toLowerCase().includes(ql);
  return (
    <div style={{ position: "relative", marginBottom: 8 }}>
      <input value={q}
        onChange={(e) => { setQ(e.target.value); setOpenL(true); }}
        onFocus={() => setOpenL(true)}
        onBlur={() => setTimeout(() => setOpenL(false), 180)}
        placeholder={t("Выбери из списка или начни вводить…","Обери зі списку або почни вводити…")}
        style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: value ? "0 26px 0 10px" : "0 10px", fontSize: 13, background: value ? "#f0fdf4" : "#fff", marginBottom: 0 }} />
      {value ? <span onMouseDown={(e) => { e.preventDefault(); onPick(""); setQ(""); }} title={t("Очистить","Очистити")}
        style={{ position: "absolute", right: 8, top: 7, cursor: "pointer", color: "#94a3b8", fontWeight: 700 }}>✕</span> : null}
      {openL && (
        <div style={{ position: "absolute", top: 36, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 10px 30px rgba(15,23,42,.15)", zIndex: 40, maxHeight: 300, overflowY: "auto" }}>
          {tops.map((c: any) => {
            const kids = kidsOf(c.id).filter(matches);
            const showTop = matches(c) || kids.length > 0;
            if (!showTop) return null;
            return (
              <div key={c.id}>
                <div onMouseDown={(e) => { e.preventDefault(); onPick(c.name); setQ(c.name); setOpenL(false); }}
                  style={{ padding: "7px 10px", cursor: "pointer", fontSize: 12.5, fontWeight: 800, background: c.name === value ? "#f0fdf4" : "#faf8f5", borderBottom: "1px solid #f1ece6" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#f3ede7")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = c.name === value ? "#f0fdf4" : "#faf8f5")}>
                  {c.name}
                </div>
                {(matches(c) ? kidsOf(c.id) : kids).map((k: any) => (
                  <div key={k.id} onMouseDown={(e) => { e.preventDefault(); onPick(k.name); setQ(k.name); setOpenL(false); }}
                    style={{ padding: "6px 10px 6px 24px", cursor: "pointer", fontSize: 12.5, background: k.name === value ? "#f0fdf4" : "", borderBottom: "1px solid #fafafa" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#f8fafc")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = k.name === value ? "#f0fdf4" : "")}>
                    └ {k.name}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


function IncomingDocsTab() {
  const { t } = useLang();
  const [rows, setRows] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [sub, setSub] = useState<"np_act" | "supplier">("np_act");
  const [mapDoc, setMapDoc] = useState<number | null>(null);
  const [msgDoc, setMsgDoc] = useState<number | null>(null);
  const load = () => api.get<any[]>("/api/integrations/incoming-docs/?status=draft").then(setRows).catch(() => setRows([]));
  useEffect(() => { load(); }, []);
  const pull = async () => {
    setBusy(true);
    try {
      const r: any = await api.post("/api/integrations/email-invoices/poll/", { backfill: false });
      alert(t("Проверено ✓", "Перевірено ✓") + `\n` + t("Новых", "Нових") + `: ${r.created} (` + t("акты НП", "акти НП") + ` ${r.np}, ` + t("поставщики", "постачальники") + ` ${r.supplier})`);
      load();
    } catch (e: any) { alert(e?.response?.data?.detail || "?"); } finally { setBusy(false); }
  };
  const act = async (id: number, action: string, ask?: string) => {
    if (ask && !confirm(ask)) return;
    try {
      const r: any = await api.post(`/api/integrations/incoming-docs/${id}/action/`, { action });
      if (action === "confirm") alert(t("Кредиторка создана ✓", "Кредиторка створена ✓") + ` №${r.payable_id}\n` + t("сделок обновлено", "сделок оновлено") + `: ${r.deals_updated} / ${r.shipments}`);
      load();
    } catch (e: any) { alert(e?.response?.data?.detail || t("Ошибка", "Помилка")); }
  };
  const np = rows.filter((r) => r.doc_type === "np_act");
  const sup = rows.filter((r) => r.doc_type === "supplier");
  const list = sub === "np_act" ? np : sup;
  return (
    <div className="scroll pad">
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>
        {t("Накладные и акты приходят на почту и сами попадают сюда как черновики. Проверь и «Проведи» — или «Отклони». Ничего не создаётся, пока не подтвердишь.",
           "Накладні та акти приходять на пошту і самі потрапляють сюди як чернетки. Перевір і «Проведи» — або «Відхили». Нічого не створюється, доки не підтвердиш.")}
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button className={"btn" + (sub === "np_act" ? " btn-primary" : " btn-light")} onClick={() => setSub("np_act")}><Icon n="🚚" size={14} /> {t("Нова Пошта", "Нова Пошта")} ({np.length})</button>
        <button className={"btn" + (sub === "supplier" ? " btn-primary" : " btn-light")} onClick={() => setSub("supplier")}><Icon n="📦" size={14} /> {t("Поставщики", "Постачальники")} ({sup.length})</button>
        <div style={{ flex: 1 }} />
        <label className="btn btn-light" style={{ cursor: "pointer" }} title={t("Загрузить накладную .xls/.xlsx с любой почты (если пришла не на почту CRM)", "Завантажити накладну .xls/.xlsx з будь-якої пошти (якщо прийшла не на пошту CRM)")}>
          <Icon n="📤" size={14} /> {t("Загрузить накладную", "Завантажити накладну")}
          <input type="file" accept=".xls,.xlsx" style={{ display: "none" }} onChange={async (e) => {
            const f = e.target.files?.[0]; if (!f) return; (e.target as any).value = "";
            setBusy(true);
            try {
              const fd = new FormData(); fd.append("file", f);
              const r: any = await api.uploadForm("/api/integrations/incoming-docs/upload/", fd);
              await load();
              if (r.duplicate) { alert(r.detail); }
              else {
                setSub("supplier");
                if (r.id) setMapDoc(r.id);   // одразу відкрити вікно проведення
              }
            } catch (err: any) { alert(err?.response?.data?.detail || t("Не удалось загрузить", "Не вдалося завантажити")); }
            finally { setBusy(false); }
          }} />
        </label>
        <button className="btn btn-light" disabled={busy} onClick={pull}>{busy ? "…" : "📬 " + t("Проверить почту", "Перевірити пошту")}</button>
      </div>
      {mapDoc && <SupplierMapModal docId={mapDoc} onClose={() => setMapDoc(null)} onDone={load} />}
      {msgDoc && <IncomingMsgModal docId={msgDoc} onClose={() => setMsgDoc(null)} onProvesti={(id, dt) => { setMsgDoc(null); if (dt === "supplier") setMapDoc(id); else act(id, "confirm"); }} onReject={(id) => { act(id, "reject"); setMsgDoc(null); }} />}
      {!list.length && <div className="muted" style={{ padding: 8 }}>{t("Пусто — новых документов нет", "Порожньо — нових документів немає")}</div>}
      {list.map((r) => (
        <div key={r.id} className="panel" style={{ margin: "0 0 8px", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 240, cursor: "pointer" }} onClick={() => setMsgDoc(r.id)} title={t("Открыть письмо", "Відкрити лист")}>
            {r.doc_type === "np_act" ? (
              <><b>{r.invoice_number}</b> <span className="muted">{t("от", "від")} {r.invoice_date}</span><br />
                <span style={{ fontSize: 13 }}>{Number(r.amount || 0).toLocaleString()} ₴ · {r.shipments_count} {t("отправлений", "відправлень")}{r.vat ? ` · ${t("НДС", "ПДВ")} ${r.vat}` : ""}</span></>
            ) : (
              <><b>{(r.subject || t("Накладная", "Накладна"))}{r.invoice_number ? ` №${r.invoice_number}` : ""}</b>
                {r.invoice_date ? <span className="muted"> {t("от", "від")} {r.invoice_date}</span> : null}
                {(r.amount || r.lines_count) ? <><br /><span style={{ fontSize: 13 }}>{r.amount ? Number(r.amount).toLocaleString() + " ₴" : ""}{r.amount && r.lines_count ? " · " : ""}{r.lines_count ? `${r.lines_count} ${t("позиций", "позицій")}` : ""}</span></> : null}
                <br /><span className="muted" style={{ fontSize: 12 }}>{r.sender} · {(r.files || []).join(", ")}</span></>
            )}
          </div>
          {r.doc_type === "np_act" && <button className="btn btn-primary" onClick={() => act(r.id, "confirm")}>✓ {t("Провести", "Провести")}</button>}
          {r.doc_type === "supplier" && <button className="btn btn-primary" onClick={() => setMapDoc(r.id)}>✓ {t("Провести", "Провести")}</button>}
          <button className="btn btn-light" onClick={() => act(r.id, "reject", t("Отклонить документ?", "Відхилити документ?"))}>{t("Отклонить", "Відхилити")}</button>
          <button className="btn btn-light" style={{ color: "#dc2626" }} onClick={() => act(r.id, "delete", t("Удалить?", "Видалити?"))}><Icon n="🗑" size={15} /></button>
        </div>
      ))}
    </div>
  );
}


// Пошук товару складу по БУДЬ-ЯКІЙ частині назви (заміна кривого <datalist>)
function ProductPicker({ value, productId, prods, onPick }:
  { value: string; productId: number | null; prods: any[]; onPick: (p: any | null, name: string) => void }) {
  const { t } = useLang();
  const [q, setQ] = useState(value || "");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  useEffect(() => { setQ(value || ""); }, [value]);
  const ql = q.trim().toLowerCase();
  const words = ql.split(/\s+/).filter(Boolean);
  const matches = (words.length
    ? prods.filter((p) => { const n = (p.name || "").toLowerCase(); return words.every((w) => n.includes(w)); })
    : prods).slice(0, 60);
  return (
    <div style={{ position: "relative" }}>
      <input value={q}
        onChange={(e) => { setQ(e.target.value); onPick(null, e.target.value); setOpen(true); setHi(0); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 160)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { setHi((h) => Math.min(h + 1, matches.length - 1)); e.preventDefault(); }
          else if (e.key === "ArrowUp") { setHi((h) => Math.max(h - 1, 0)); e.preventDefault(); }
          else if (e.key === "Enter" && matches[hi]) { const p = matches[hi]; onPick(p, p.name); setQ(p.name); setOpen(false); e.preventDefault(); }
        }}
        placeholder={t("поиск товара…", "пошук товару…")}
        style={{ width: "100%", height: 30, borderRadius: 6, padding: "0 8px",
                 border: "1px solid " + (productId ? "#86efac" : "#fca5a5") }} />
      {open && (
        <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20, background: "#fff",
                      border: "1px solid #cbd5e1", borderRadius: 8, marginTop: 2, maxHeight: 240, overflowY: "auto",
                      boxShadow: "0 12px 30px rgba(15,23,42,.18)" }}>
          {!matches.length && <div className="muted" style={{ padding: "8px 10px", fontSize: 12 }}>{t("Ничего не найдено", "Нічого не знайдено")}</div>}
          {matches.map((p, j) => (
            <div key={p.id} onMouseDown={() => { onPick(p, p.name); setQ(p.name); setOpen(false); }}
              onMouseEnter={() => setHi(j)}
              style={{ padding: "6px 10px", cursor: "pointer", fontSize: 12.5,
                       background: j === hi ? "#eef2ff" : "transparent",
                       borderBottom: "1px solid #f4f6fb" }}>
              {p.name}{(p.stock !== undefined && p.stock !== null) ? <span className="muted" style={{ fontSize: 11 }}>  · {t("ост.", "зал.")} {p.stock}</span> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Пошук категорії закупівлі (з батьківською категорією у назві)
function CategoryPicker({ cats, value, onPick }:
  { cats: any[]; value: number | 0; onPick: (id: number | 0) => void }) {
  const { t } = useLang();
  const byId = (id: number) => cats.find((c) => c.id === id);
  const label = (c: any) => {
    if (!c) return "";
    const parent = c.parent ? byId(c.parent) : null;
    return (parent ? parent.name + " → " : "") + c.name;
  };
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  useEffect(() => { const c = value ? byId(value) : null; setQ(c ? label(c) : ""); /* eslint-disable-next-line */ }, [value, cats.length]);
  const ql = q.trim().toLowerCase();
  const words = ql.split(/\s+/).filter(Boolean);
  const list = cats.map((c) => ({ c, lbl: label(c) }))
    .filter(({ lbl }) => !words.length || words.every((w) => lbl.toLowerCase().includes(w)))
    .sort((a, b) => a.lbl.localeCompare(b.lbl)).slice(0, 80);
  return (
    <div style={{ position: "relative" }}>
      <input value={q}
        onChange={(e) => { setQ(e.target.value); onPick(0); setOpen(true); }}
        onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 160)}
        placeholder={t("выбери категорию…", "обери категорію…")}
        style={{ width: "100%", height: 34, borderRadius: 7, padding: "0 10px",
                 border: "1px solid " + (value ? "#86efac" : "#cbd5e1") }} />
      {open && (
        <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 20, background: "#fff",
                      border: "1px solid #cbd5e1", borderRadius: 8, marginTop: 2, maxHeight: 260, overflowY: "auto",
                      boxShadow: "0 12px 30px rgba(15,23,42,.18)" }}>
          {!list.length && <div className="muted" style={{ padding: "8px 10px", fontSize: 12 }}>{t("Ничего не найдено", "Нічого не знайдено")}</div>}
          {list.map(({ c, lbl }) => (
            <div key={c.id} onMouseDown={() => { onPick(c.id); setQ(lbl); setOpen(false); }}
              style={{ padding: "6px 10px", cursor: "pointer", fontSize: 12.5, borderBottom: "1px solid #f4f6fb" }}>
              {lbl}{c.fin_article_name ? <span className="muted" style={{ fontSize: 11 }}>  · {c.fin_article_name}</span> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SupplierMapModal({ docId, onClose, onDone }: { docId: number; onClose: () => void; onDone: () => void }) {
  const { t } = useLang();
  const [det, setDet] = useState<any>(null);
  const [prods, setProds] = useState<any[]>([]);
  const [lines, setLines] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  // постачальник: обрати наявного / створити нового з пошти
  const [sups, setSups] = useState<any[]>([]);
  const [supId, setSupId] = useState<number | 0>(0);
  const [newSup, setNewSup] = useState<any | null>(null);
  // оплата: кредиторка (заплачу потім) або привʼязка до вже зробленого платежу
  const [payMode, setPayMode] = useState<"payable" | "paid">("payable");
  const [cands, setCands] = useState<any[]>([]);
  const [txId, setTxId] = useState<number | 0>(0);
  const [candQ, setCandQ] = useState("");   // пошук платежу
  const [cats, setCats] = useState<any[]>([]);   // категорії закупівлі (out)
  const [catId, setCatId] = useState<number | 0>(0);

  useEffect(() => {
    api.get<any>(`/api/integrations/incoming-docs/${docId}/`).then((d) => { setDet(d); setLines((d.lines || []).map((l: any) => ({ ...l }))); }).catch(() => {});
    (async () => {
      // API обмежує сторінку 500 → тягнемо всі сторінки, поки є next
      try {
        let all: any[] = [];
        let page = 1;
        while (page <= 20) {
          const d: any = await api.get(`/api/products/?page_size=500&page=${page}&is_active=true`);
          const rows = d.results || d;
          all = all.concat(rows);
          if (!d.next || rows.length === 0) break;
          page++;
        }
        setProds(all.filter((p: any) => p.is_active !== false));   // лише активні (без вимкнених дублів)
      } catch { setProds([]); }
    })();
    api.get<any>("/api/contacts/?kind=supplier&page_size=300").then((d) => setSups(d.results || d)).catch(() => setSups([]));
    api.get<any>("/api/categories/?page_size=400").then((d) => setCats((d.results || d).filter((c: any) => c.direction === "out" && !c.hidden))).catch(() => setCats([]));
  }, [docId]);
  // автопідстановка категорії постачальника: за обраним у списку АБО за ІПН з файлу
  useEffect(() => {
    if (catId) return;
    let sup: any = null;
    if (supId) sup = sups.find((x) => x.id === supId);
    else if (det?.supplier?.ipn) sup = sups.find((x) => (x.edrpou || "") === det.supplier.ipn);
    if (sup && sup.default_purchase_category) setCatId(sup.default_purchase_category);
  }, [supId, sups, det, catId]);
  useEffect(() => {
    if (payMode === "paid" && !cands.length) {
      api.get<any>(`/api/integrations/incoming-docs/${docId}/pay-candidates/`).then((d) => setCands(d.rows || [])).catch(() => setCands([]));
    }
  }, [payMode, docId, cands.length]);
  // пошта відправника — з неї створюємо нового постачальника
  const senderMail = ((det?.sender || "").match(/[\w.+-]+@[\w-]+\.[\w.-]+/) || [""])[0];
  const setLine = (i: number, patch: any) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const addLine = () => setLines((ls) => [...ls, { their_name: "", qty: 1, price: 0, sum: 0, factor: 1, product_id: null, product_name: "" }]);
  const delLine = (i: number) => setLines((ls) => ls.filter((_, j) => j !== i));
  const post = async () => {
    if (lines.some((l) => !l.product_id) && !confirm(t("Не все строки сопоставлены — провести только сопоставленные?", "Не всі рядки зіставлені — провести лише зіставлені?"))) return;
    setBusy(true);
    try {
      const body: any = { action: "confirm", lines };
      if (supId) body.contact_id = supId;
      if (newSup) body.new_supplier = newSup;
      if (payMode === "paid" && txId) { body.pay_mode = "paid"; body.tx_id = txId; }
      if (catId) body.category_id = catId;
      const r: any = await api.post(`/api/integrations/incoming-docs/${docId}/action/`, body);
      alert(t("Приход проведён ✓", "Прихід проведено ✓") + `\n` +
        t("поставщик", "постачальник") + `: ${r.supplier}\n` +
        t("позиций", "позицій") + `: ${r.positions}, ` + t("правил", "правил") + `: ${r.rules_saved}\n` +
        (r.settled_tx
          ? t("Долг закрыт платежом из журнала №", "Борг закрито платежем із журналу №") + `${r.settled_tx}`
          : t("кредиторка", "кредиторка") + ` №${r.payable_id} на ${r.amount} ₴`));
      onDone(); onClose();
    } catch (e: any) { alert(e?.response?.data?.detail || t("Ошибка", "Помилка")); } finally { setBusy(false); }
  };
  if (!det) return null;
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 1000, overflow: "auto", padding: 16 }} onClick={onClose}>
      <div className="panel" style={{ maxWidth: 920, margin: "16px auto", background: "#fff" }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 4px" }}>{t("Накладная поставщика", "Накладна постачальника")} №{det.invoice_number} {t("от", "від")} {det.invoice_date}</h3>
        <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{det.supplier?.name} · {t("сумма", "сума")} <b>{det.amount} ₴</b>. {t("Под каждый его товар выбери наш со склада — запомнится как правило.", "Під кожен його товар обери наш зі складу — запамʼятається як правило.")}<br />{t("Закупаешь в единицах поставщика (вёдра), а склад в кг — впиши «Коэф →скл» (напр. 15). Сумма — со скидкой (можно править).", "Закуповуєш в одиницях постачальника (відра), а склад у кг — впиши «Коеф →скл» (напр. 15). Сума — зі знижкою (можна правити).")}</div>
        {/* ── ПОСТАЧАЛЬНИК ── */}
        <div style={{ padding: 10, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: "#475569", marginBottom: 6 }}>{t("Поставщик", "Постачальник")}</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select value={supId} onChange={(e) => { setSupId(Number(e.target.value)); setNewSup(null); }}
              style={{ flex: "1 1 260px", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }}>
              <option value={0}>{t("— определить автоматически (по ІПН / почте) —", "— визначити автоматично (за ІПН / поштою) —")}</option>
              {sups.map((c) => <option key={c.id} value={c.id}>{c.display_name}</option>)}
            </select>
            {!newSup && (
              <button className="btn btn-light" onClick={() => setNewSup({
                name: det?.supplier?.name || "", edrpou: det?.supplier?.ipn || "",
                iban: det?.supplier?.iban || "", email: senderMail, phone: "",
              })}>+ {t("Новый поставщик", "Новий постачальник")}</button>
            )}
          </div>
          {newSup && (
            <div style={{ marginTop: 8, padding: 10, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8 }}>
              <div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>
                {t("Создастся контрагент с типом «Постачальник» и включённым мониторингом накладных с этой почты.",
                   "Створиться контрагент із типом «Постачальник» і увімкненим моніторингом накладних із цієї пошти.")}
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {([["name", t("Название / ФИО", "Назва / ПІБ"), "1 1 200px"], ["edrpou", "ЄДРПОУ / ІПН", "0 1 140px"],
                   ["iban", "IBAN", "1 1 220px"], ["email", t("Почта (отправитель)", "Пошта (відправник)"), "1 1 200px"],
                   ["phone", t("Телефон", "Телефон"), "0 1 140px"]] as [string, string, string][]).map(([k, ph, fl]) => (
                  <input key={k} value={newSup[k] || ""} placeholder={ph} onChange={(e) => setNewSup({ ...newSup, [k]: e.target.value })}
                    style={{ flex: fl, height: 32, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px", fontSize: 13 }} />
                ))}
              </div>
              <button className="btn btn-light" style={{ marginTop: 6 }} onClick={() => setNewSup(null)}>{t("Отмена", "Скасувати")}</button>
            </div>
          )}
        </div>

        {/* ── ОПЛАТА ── */}
        <div style={{ padding: 10, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: "#475569", marginBottom: 6 }}>{t("Оплата", "Оплата")}</div>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 13 }}>
              <input type="radio" checked={payMode === "payable"} onChange={() => setPayMode("payable")} />
              {t("Ещё не оплачено — создать долг (кредиторку)", "Ще не оплачено — створити борг (кредиторку)")}
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 13 }}>
              <input type="radio" checked={payMode === "paid"} onChange={() => setPayMode("paid")} />
              {t("Уже оплатил — привязать платёж из журнала", "Вже оплатив — привʼязати платіж із журналу")}
            </label>
          </div>
          {payMode === "paid" && (() => {
            const inv = Number(det?.amount || 0);
            const q = candQ.trim().toLowerCase();
            const shown = cands.filter((r) => !q
              || String((r.counterparty || "") + " " + (r.comment || "")).toLowerCase().includes(q)
              || String(Math.round(Number(r.amount))).includes(q.replace(/\s/g, "")));
            return (
              <div style={{ marginTop: 8 }}>
                <input value={candQ} onChange={(e) => setCandQ(e.target.value)}
                  placeholder={t("🔍 Поиск платежа: контрагент, назначение или сумма", "🔍 Пошук платежу: контрагент, призначення або сума")}
                  style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 10px", marginBottom: 6 }} />
                <div className="muted" style={{ fontSize: 11.5, marginBottom: 4 }}>
                  {inv ? t("Сумма накладной", "Сума накладної") + ": " + inv.toLocaleString() + " ₴. " : ""}
                  {t("Выбери расход, которым оплатил (последние 120 дней, ближайшие по сумме сверху).", "Обери витрату, якою оплатив (останні 120 днів, найближчі за сумою зверху).")}
                </div>
                <div style={{ maxHeight: 240, overflowY: "auto", border: "1px solid #e2e8f0", borderRadius: 8, background: "#fff" }}>
                  {!cands.length && <div className="muted" style={{ padding: 10, fontSize: 12.5 }}>{t("Ищу подходящие расходы…", "Шукаю відповідні витрати…")}</div>}
                  {cands.length > 0 && !shown.length && <div className="muted" style={{ padding: 10, fontSize: 12.5 }}>{t("Ничего не найдено по поиску", "Нічого не знайдено за пошуком")}</div>}
                  {shown.map((r) => {
                    const on = txId === r.id;
                    const exact = inv > 0 && Math.abs(Number(r.amount) - inv) < 0.01;
                    return (
                      <div key={r.id} onClick={() => setTxId(on ? 0 : r.id)}
                        style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 10px", cursor: "pointer",
                                 borderBottom: "1px solid #f1f5f9", background: on ? "#eef2ff" : "transparent" }}>
                        <input type="radio" checked={on} readOnly />
                        <b style={{ minWidth: 92, fontSize: 13 }}>{Number(r.amount).toLocaleString()} ₴</b>
                        <span className="muted" style={{ fontSize: 12, minWidth: 78 }}>{r.date}</span>
                        <span style={{ fontSize: 12.5, flex: 1 }}>{r.counterparty || r.comment || "—"}</span>
                        {exact && <span className="chip" style={{ background: "#f0fdf4", color: "#15803d", fontSize: 11 }}>{t("сумма совпала", "сума збіглася")}</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </div>

        {/* ── КАТЕГОРІЯ ЗАКУПІВЛІ (правило постачальника) ── */}
        <div style={{ padding: 10, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: "#475569", marginBottom: 6 }}>{t("Категория закупки", "Категорія закупівлі")}</div>
          <CategoryPicker cats={cats} value={catId} onPick={(id) => setCatId(id)} />
          <div className="muted" style={{ fontSize: 11.5, marginTop: 5 }}>
            {t("Фонд и направление подтянутся автоматически. Запомнится для этого поставщика — в следующий раз подставится сама.",
               "Фонд і напрямок підтягнуться автоматично. Запамʼятається для цього постачальника — наступного разу підставиться сама.")}
          </div>
        </div>

        <datalist id="wh-prods">{prods.map((p) => <option key={p.id} value={p.name} />)}</datalist>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead><tr style={{ textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
            <th style={{ padding: 4 }}>{t("Его товар", "Його товар")}</th><th>{t("Наш товар (склад)", "Наш товар (склад)")}</th><th style={{ width: 52 }} title={t("Кол-во в единицах поставщика (напр. вёдра)", "К-сть в одиницях постачальника (напр. відра)")}>{t("К-во", "К-сть")}</th><th style={{ width: 66 }} title={t("Сколько наших единиц (кг) в 1 единице поставщика (ведро). 1 = одинаковые", "Скільки наших одиниць (кг) в 1 одиниці постачальника (відро). 1 = однакові")}>{t("Коэф →скл", "Коеф →скл")}</th><th style={{ width: 80 }} title={t("Итоговая сумма строки со скидкой", "Підсумкова сума рядка зі знижкою")}>{t("Сумма", "Сума")}</th><th style={{ width: 30 }}></th></tr></thead>
          <tbody>
            {!lines.length && (
              <tr><td colSpan={6} className="muted" style={{ padding: "10px 4px", fontSize: 12.5 }}>
                {t("Позиции не распознаны в файле — добавь строки вручную кнопкой ниже.", "Позиції не розпізнані у файлі — додай рядки вручну кнопкою нижче.")}
              </td></tr>
            )}
            {lines.map((l, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                <td style={{ padding: "6px 4px" }}><input value={l.their_name || ""} onChange={(e) => setLine(i, { their_name: e.target.value })} placeholder={t("наименование", "найменування")} style={{ width: "100%", height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px" }} /></td>
                <td><ProductPicker value={l.product_name || ""} productId={l.product_id || null} prods={prods} onPick={(p, name) => setLine(i, { product_name: name, product_id: p ? p.id : null })} />{(Number(l.factor) || 1) !== 1 && (() => { const q = Number(l.qty) || 0; const f = Number(l.factor) || 1; const tot = (l.sum != null && l.sum !== "") ? Number(l.sum) : q * (Number(l.price) || 0); const sq = q * f; const cost = sq ? tot / sq : 0; return <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>→ {sq.toLocaleString()} {t("ед.", "од.")} · {cost.toLocaleString(undefined, { maximumFractionDigits: 2 })} ₴/{t("ед.", "од.")}</div>; })()}</td>
                <td><input type="number" value={l.qty} onChange={(e) => setLine(i, { qty: parseFloat(e.target.value) })} style={{ width: 48, height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 5px" }} /></td>
                <td><input type="number" value={l.factor ?? 1} onChange={(e) => setLine(i, { factor: parseFloat(e.target.value) || 1 })} style={{ width: 60, height: 30, border: "1px solid " + ((Number(l.factor) || 1) !== 1 ? "#93c5fd" : "#cbd5e1"), borderRadius: 6, padding: "0 5px" }} /></td>
                <td><input type="number" value={l.sum ?? ""} placeholder={String(Math.round((Number(l.qty) || 0) * (Number(l.price) || 0)))} onChange={(e) => setLine(i, { sum: e.target.value === "" ? null : parseFloat(e.target.value) })} style={{ width: 76, height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px" }} /></td>
                <td style={{ textAlign: "center" }}><button onClick={() => delLine(i)} title={t("Удалить строку", "Видалити рядок")} style={{ border: "none", background: "transparent", cursor: "pointer", color: "#dc2626", fontSize: 16 }}>×</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <button className="btn btn-light" style={{ marginTop: 8 }} onClick={addLine}>+ {t("Добавить строку", "Додати рядок")}</button>
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button className="btn btn-primary" disabled={busy || (payMode === "paid" && !txId)} onClick={post}>
            {busy ? "…" : "✓ " + (payMode === "paid"
              ? t("Оприходовать и закрыть платежом", "Оприбуткувати і закрити платежем")
              : t("Провести приход + кредиторку", "Провести прихід + кредиторку"))}
          </button>
          <button className="btn btn-light" onClick={onClose}>{t("Отмена", "Скасувати")}</button>
        </div>
      </div>
    </div>
  );
}


function IncomingMsgModal({ docId, onClose, onProvesti, onReject }: { docId: number; onClose: () => void; onProvesti: (id: number, dt: string) => void; onReject: (id: number) => void }) {
  const { t } = useLang();
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.get<any>(`/api/integrations/incoming-docs/${docId}/`).then(setD).catch(() => {}); }, [docId]);
  const openView = async () => {
    try { const u = await api.blobUrl(`/api/integrations/incoming-docs/${docId}/view/`); window.open(u, "_blank"); }
    catch { alert(t("Не удалось открыть накладную", "Не вдалося відкрити накладну")); }
  };
  const downloadFile = async (idx: number, name: string) => {
    try { const u = await api.blobUrl(`/api/integrations/incoming-docs/${docId}/file/${idx}/`); const a = document.createElement("a"); a.href = u; a.download = name || "file"; document.body.appendChild(a); a.click(); a.remove(); }
    catch { alert(t("Не удалось скачать файл", "Не вдалося завантажити файл")); }
  };
  if (!d) return null;
  const isSup = d.doc_type === "supplier";
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 1000, overflow: "auto", padding: 16 }} onClick={onClose}>
      <div className="panel" style={{ maxWidth: 680, margin: "24px auto", background: "#fff" }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 4px" }}>{d.subject || (isSup ? t("Накладная поставщика", "Накладна постачальника") : t("Акт Новой Почты", "Акт Нової Пошти"))}</h3>
        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("От", "Від")}: {d.sender}{d.invoice_number ? ` · №${d.invoice_number} ${t("от", "від")} ${d.invoice_date}` : ""}{d.amount ? ` · ${Number(d.amount).toLocaleString()} ₴` : ""}</div>
        <div style={{ marginBottom: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
          {d.invoice_number && <button className="btn btn-primary" onClick={openView}><Icon n="📄" size={14} /> {t("Открыть накладную", "Відкрити накладну")}</button>}
          {(d.files || []).map((f: any) => (
            <button key={f.idx} className="btn btn-light" onClick={() => downloadFile(f.idx, f.name)}><Icon n="📥" size={14} /> {t("Скачать", "Завантажити")}: {f.name}</button>
          ))}
        </div>
        {d.email_text
          ? <div style={{ background: "#f8fafc", borderRadius: 8, padding: 10, fontSize: 13, whiteSpace: "pre-wrap", maxHeight: 260, overflow: "auto", marginBottom: 12 }}>{d.email_text}</div>
          : <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Текст письма пуст — смотри вложение", "Текст листа порожній — дивись вкладення")}</div>}
        {isSup && (d.lines || []).length > 0 && <div style={{ fontSize: 12.5, marginBottom: 12 }}>{t("Позиций в накладной", "Позицій у накладній")}: {d.lines.length}</div>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn btn-primary" onClick={() => onProvesti(docId, d.doc_type)}>✓ {t("Провести", "Провести")}</button>
          <button className="btn btn-light" onClick={() => { if (confirm(t("Отклонить документ?", "Відхилити документ?"))) onReject(docId); }}>{t("Отклонить", "Відхилити")}</button>
          <button className="btn btn-light" onClick={onClose}>{t("Закрыть", "Закрити")}</button>
        </div>
      </div>
    </div>
  );
}


function PayFopModal({ r, onClose, onDone }: { r: any; onClose: () => void; onDone: () => void }) {
  const { t } = useLang();
  const [dry, setDry] = useState<any>(null);
  const [amount, setAmount] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState<string>("");
  const [accs, setAccs] = useState<any[]>([]);
  const [payer, setPayer] = useState<string>("");
  useEffect(() => {
    api.get<any>("/api/planned-payments/fop-accounts/").then((d: any) => { setAccs(d.accounts || []); setPayer(d.default || ""); }).catch(() => {});
    api.post<any>(`/api/planned-payments/${r.id}/pay-with-fop/`, {}).then((d: any) => {
      if (d.detail) { setErr(d.detail); return; }
      setDry(d); setAmount(String(d.would_send?.payment_amount || ""));
    }).catch((e: any) => setErr(e?.response?.data?.detail || t("Не удалось подготовить платёж", "Не вдалося підготувати платіж")));
  }, [r.id]);
  const send = async () => {
    setBusy(true); setErr("");
    try {
      const res: any = await api.post(`/api/planned-payments/${r.id}/pay-with-fop/`, { confirm: 1, amount, payer_account: payer });
      if (res.detail) { setErr(res.detail); setBusy(false); return; }
      setResult(res); onDone();
    } catch (e: any) { setErr(e?.response?.data?.detail || t("Ошибка", "Помилка")); } finally { setBusy(false); }
  };
  const w = dry?.would_send || {};
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 1100, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }} onClick={onClose}>
      <div className="panel" style={{ maxWidth: 500, width: "100%", background: "#fff", boxShadow: "0 20px 60px rgba(0,0,0,.25)" }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 14px", display: "flex", alignItems: "center", gap: 8 }}><Icon n="💳" size={18} /> {t("Оплата с ФОП через Приват", "Оплата з ФОП через Приват")}</h3>
        {err && <div style={{ background: "#fef2f2", color: "#dc2626", borderRadius: 8, padding: 10, fontSize: 13, marginBottom: 12 }}>{err}</div>}
        {result ? (
          <>
            <div style={{ background: "#f0fdf4", color: "#15803d", borderRadius: 8, padding: 12, fontSize: 13.5, marginBottom: 14 }}>✓ {result.note}{result.payment_ref ? ` (ref: ${result.payment_ref})` : ""}</div>
            <button className="btn btn-primary" onClick={onClose}>{t("Закрыть", "Закрити")}</button>
          </>
        ) : dry ? (
          <>
            {dry.already_created && <div style={{ background: "#fffbeb", color: "#b45309", borderRadius: 8, padding: 10, fontSize: 13, marginBottom: 12 }}><Icon n="⚠️" size={13} /> {t("По этому долгу платёж уже создавался. Проверь в Приват24, чтобы не оплатить дважды.", "За цим боргом платіж вже створювався. Перевір у Приват24, щоб не сплатити двічі.")}</div>}
            <div style={{ background: "#f8fafc", borderRadius: 10, padding: "12px 14px", fontSize: 13.5, lineHeight: 1.7, marginBottom: 14 }}>
              <div><span style={{ color: "#64748b" }}>{t("Получатель", "Отримувач")}:</span> <b>{w.payment_naming}</b></div>
              <div><span style={{ color: "#64748b" }}>{t("Счёт", "Рахунок")}:</span> {w.recipient_account}</div>
              <div><span style={{ color: "#64748b" }}>ЄДРПОУ/ІПН:</span> {w.recipient_nceo}</div>
              <div style={{ whiteSpace: "normal" }}><span style={{ color: "#64748b" }}>{t("Назначение", "Призначення")}:</span> {w.payment_destination}</div>
            </div>
            <label className="label" style={{ display: "block", marginBottom: 4 }}>{t("Сумма к оплате, грн", "Сума до оплати, грн")}</label>
            <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: "100%", height: 40, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 12px", fontSize: 17, fontWeight: 700, marginBottom: 12, boxSizing: "border-box" }} />
            <label className="label" style={{ display: "block", margin: "0 0 4px" }}>{t("Счёт списания", "Рахунок списання")}</label>
            <select value={payer} onChange={(e) => setPayer(e.target.value)} style={{ width: "100%", height: 40, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", fontSize: 13, marginBottom: 6, boxSizing: "border-box" }}>
              {accs.length === 0 && <option value={payer}>{payer ? "…" + payer.slice(-4) : t("основной счёт", "основний рахунок")}</option>}
              {accs.map((a: any) => <option key={a.iban} value={a.iban}>…{a.iban.slice(-4)} · {a.name} · {t("остаток", "залишок")} {Number(a.balance).toLocaleString()} {a.ccy}</option>)}
            </select>
            {(() => { const sel = accs.find((a: any) => a.iban === payer); if (sel && Number(sel.balance) < Number(amount)) return <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 8 }}><Icon n="⚠️" size={12} /> {t("На счету меньше суммы платежа", "На рахунку менше суми платежу")}: {Number(sel.balance).toLocaleString()} {sel.ccy}</div>; return null; })()}
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>{t("Создастся ЧЕРНОВИК в Приват24 — подпишешь его КЕП (SmartID), тогда деньги уйдут.", "Створиться ЧЕРНЕТКА у Приват24 — підпишеш її КЕП (SmartID), тоді гроші підуть.")}</div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary" disabled={busy || !dry.ready} onClick={send}>{busy ? "…" : "✓ " + t("Создать платёж", "Створити платіж")}</button>
              <button className="btn btn-light" onClick={onClose}>{t("Отмена", "Скасувати")}</button>
            </div>
            {!dry.ready && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 8 }}>{t("Приват не настроен (токен/счёт)", "Приват не налаштований (токен/рахунок)")}</div>}
          </>
        ) : <div className="muted" style={{ padding: 10 }}>{t("Загрузка…", "Завантаження…")}</div>}
      </div>
    </div>
  );
}


function QuickExpenseModal({ onClose }: { onClose: () => void }) {
  const { t } = useLang();
  const [amount, setAmount] = useState("");
  const [arts, setArts] = useState<any[]>([]);
  const [artId, setArtId] = useState<number | null>(null);
  const [cp, setCp] = useState("Нова Пошта");
  const [method, setMethod] = useState("card");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  useEffect(() => { api.get<any>("/api/finmodel-articles/?page_size=300").then((d) => setArts(d.results || d)).catch(() => {}); }, []);
  const PIN = ["упаков", "доставк", "логіст", "логист", "матеріал", "материал", "транспорт"];
  const shortF = (n: string) => (n || "").replace(/^ФОНД\s+/i, "").replace(/\s*\(.*\)/, "").split(/[—/]/)[0].trim();
  const _seen = new Set<string>();
  const pinned = arts.filter((a: any) => {
    const nl = (a.name || "").toLowerCase();
    if (nl.startsWith("фот") || !PIN.some((k) => nl.includes(k))) return false;
    const sh = shortF(a.name); if (_seen.has(sh)) return false; _seen.add(sh); return true;
  }).slice(0, 5);
  const save = async () => {
    const amt = parseFloat(String(amount).replace(",", "."));
    if (!amt || amt <= 0) { alert(t("Впиши сумму", "Впиши суму")); return; }
    if (!artId) { alert(t("Выбери фонд «за что»", "Обери фонд «за що»")); return; }
    setBusy(true);
    try {
      const r: any = await api.post("/api/transactions/quick-expense/", { amount: amt, fin_article: artId, counterparty: cp, method, comment });
      setDone(r.note || t("Готово", "Готово"));
      setTimeout(onClose, 1400);
    } catch (e: any) { alert(e?.response?.data?.detail || t("Ошибка", "Помилка")); setBusy(false); }
  };
  const inp: any = { width: "100%", border: "1px solid #cbd5e1", borderRadius: 10, padding: "0 12px", fontSize: 15, boxSizing: "border-box" };
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 1200, display: "flex", alignItems: "flex-end", justifyContent: "center" }} onClick={onClose}>
      <div className="panel" style={{ width: "100%", maxWidth: 460, background: "#fff", borderRadius: "18px 18px 0 0", maxHeight: "92vh", overflowY: "auto", padding: 0 }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, background: "linear-gradient(90deg,#C67D5F,#b5674a)", color: "#fff", padding: "14px 18px", borderRadius: "18px 18px 0 0", zIndex: 2 }}>
          <h3 style={{ margin: 0, fontSize: 17, color: "#fff", fontWeight: 800 }}><Icon n="⚡" size={17} /> {t("Быстрый платёж", "Швидкий платіж")}</h3>
          <button onClick={onClose} style={{ border: "none", background: "rgba(255,255,255,.2)", width: 30, height: 30, borderRadius: "50%", fontSize: 17, color: "#fff", cursor: "pointer" }}>✕</button>
        </div>
        <div style={{ padding: 18 }}>
        {done ? (
          <div style={{ textAlign: "center", padding: "30px 10px" }}>
            <div style={{ fontSize: 46 }}>✅</div>
            <div style={{ fontSize: 15, color: "#15803d", marginTop: 8 }}>{done}</div>
          </div>
        ) : (<>
          <label className="label" style={{ display: "block", marginBottom: 4 }}>{t("Сумма, грн", "Сума, грн")}</label>
          <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder="0" autoFocus
            style={{ ...inp, height: 56, fontSize: 30, fontWeight: 800, textAlign: "center", marginBottom: 14 }} />
          <label className="label" style={{ display: "block", marginBottom: 6 }}>{t("За что (фонд)", "За що (фонд)")}</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
            {pinned.map((a: any) => (
              <button key={a.id} onClick={() => setArtId(a.id)}
                style={{ padding: "8px 13px", borderRadius: 18, fontSize: 13, cursor: "pointer", border: "1.5px solid " + (artId === a.id ? "#C67D5F" : "#cbd5e1"), background: artId === a.id ? "#C67D5F" : "#fff", color: artId === a.id ? "#fff" : "#1e293b", fontWeight: 600, whiteSpace: "nowrap" }}>{shortF(a.name)}</button>
            ))}
          </div>
          <select value={artId ?? ""} onChange={(e) => setArtId(e.target.value ? Number(e.target.value) : null)} style={{ ...inp, height: 44, marginBottom: 14 }}>
            <option value="">{t("…или выбери из всех фондов", "…або обери з усіх фондів")}</option>
            {arts.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <label className="label" style={{ display: "block", marginBottom: 4 }}>{t("Кому", "Кому")}</label>
          <input value={cp} onChange={(e) => setCp(e.target.value)} style={{ ...inp, height: 44, marginBottom: 14 }} />
          <label className="label" style={{ display: "block", marginBottom: 6 }}>{t("Чем платил", "Чим платив")}</label>
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            {[["card", "💳", t("Карта", "Картка")], ["cash", "💵", t("Наличка", "Готівка")]].map(([m, ic, l]) => (
              <button key={m} onClick={() => setMethod(m)} style={{ flex: 1, height: 46, borderRadius: 10, fontSize: 14.5, cursor: "pointer", fontWeight: 700, border: "1.5px solid " + (method === m ? "#2563eb" : "#cbd5e1"), background: method === m ? "#eff6ff" : "#fff", color: method === m ? "#2563eb" : "#1e293b" }}><Icon n={ic} size={15} /> {l}</button>
            ))}
          </div>
          <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t("Комментарий (необязательно)", "Коментар (необовʼязково)")} style={{ ...inp, height: 44, marginBottom: 16 }} />
          <button className="btn btn-primary" disabled={busy} onClick={save} style={{ width: "100%", height: 52, fontSize: 16, fontWeight: 700 }}>{busy ? "…" : "✓ " + t("Зафиксировать", "Зафіксувати")}</button>
          <div style={{ fontSize: 11.5, color: "#64748b", textAlign: "center", marginTop: 8 }}>{method === "card" ? t("Выписка склеится сама — дубля не будет", "Виписка склеїться сама — дубля не буде") : t("Наличка фиксируется только здесь", "Готівка фіксується лише тут")}</div>
        </>)}
        </div>
      </div>
    </div>
  );
}

function useIsMobile() {
  const [m, setM] = useState(typeof window !== "undefined" && window.innerWidth <= 640);
  useEffect(() => { const h = () => setM(window.innerWidth <= 640); window.addEventListener("resize", h); return () => window.removeEventListener("resize", h); }, []);
  return m;
}
