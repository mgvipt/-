/* Біржа задач (14.09.2026): прайс додаткових задач з оплатою по відділах — Маркетинг/SMM, Продажі, Склад, Салон,
 * Обʼєкти, Контент/сайт, ІІ і CRM, Офіс. «Беру» → доказ (посилання / фото / текст) → «Прийнято» або «На доробку»
 * → сума окремим рядком «Задачі з біржі» у ЗП того місяця. Гроші — з фонду «Біржа задач» (стаття Фінмоделі).
 * Правило «основний стандарт від 75%» — мʼяке: попередження, не блок.
 * Усі компоненти — на рівні модуля (поля не втрачають фокус), довгі списки — у прокручуваних контейнерах.
 * v2 (15.09.2026): у задачі — «Навіщо», «Кінцевий результат», підзадачі з «як зробити»; у взятій задачі — відмітки
 * підзадач (прогрес «3/5»), здати можна будь-коли, перевіряючий бачить невідмічені; у «Прайсі» — редактор підзадач. */
import { useCallback, useEffect, useState } from "react";
import type { CSSProperties, Dispatch, SetStateAction } from "react";
import { api } from "../api";
import { Icon } from "../Icon";

type Dept = { key: string; label: string; n_active: number; n_total: number };
type Cat = { id: number; department: string; department_label: string; name: string; order: number; active: boolean };
type Busy = { name: string; due_at: string | null; status: string };
type Sub = { title: string; how: string };
type ClaimSub = Sub & { i: number; done: boolean };
type Offer = {
  id: number; category_id: number; category_name: string; department: string; title: string; how_to: string; done_criteria: string;
  proof_type: string; proof_label: string; price: number; unit: string; unit_label: string; unit_text: string;
  monthly_limit_qty: number; max_per_person: number; max_takers: number; due_days: number; checker_id: number | null; checker_name: string;
  active: boolean; archived: boolean; order: number; note: string;
  why: string; expected_result: string; subtasks: Sub[];
  state?: string; used_qty?: number; my_qty?: number; left_qty?: number | null; my_claim_id?: number | null; busy_by?: Busy[];
};
type Std = { score: number | null; pct: number | null; period: string | null; ok: boolean; warning: string } | null;
type Fund = { name: string; found: boolean; period: string; limit: number | null; used: number; reserved: number; left: number | null; enforced: boolean; warning: string } | null;
type Opt = { key: string; label: string };
type UserOpt = { id: number; name: string };
type ArchivedOffer = { id: number; title: string; category_name: string; department: string };
type Board = {
  month: string; departments: Dept[]; categories: Cat[]; offers: Offer[]; units: Opt[]; proofs: Opt[];
  me: { id: number; name: string; can_manage: boolean; can_review: boolean; standard: Std; min_standard_pct: number; active_claims: number };
  review_count: number; fund: Fund; users?: UserOpt[]; archived_offers?: ArchivedOffer[];
};
type CFile = { id: number; filename: string; content_type: string; size: number };
type Hist = { at: string; by: number | null; by_name: string; act: string; note: string };
type Claim = {
  id: number; offer_id: number; offer_title: string; category_name: string; department: string; department_label: string;
  unit: string; unit_label: string; unit_text: string; price: number; qty: number; base_amount: number | null; amount: number; estimate: number;
  status: string; status_label: string; user_id: number; user_name: string; taken_at: string | null; due_at: string | null; submitted_at: string | null;
  overdue: boolean; proof_text: string; proof_url: string; proof_type: string; proof_label: string; done_criteria: string; how_to: string;
  files: CFile[]; reviewer_name: string; reviewed_at: string | null; comment: string; quality: number | null; payroll_period: string;
  std_warning: string; history: Hist[]; can_submit: boolean; can_review: boolean; can_cancel: boolean; can_force: boolean;
  why: string; expected_result: string; subtasks: ClaimSub[]; subtasks_total: number; subtasks_done_count: number; can_check: boolean;
};
type PersonRow = {
  user_id: number; name: string; count: number; amount: number; avg_quality: number | null; reworks: number; on_time_pct: number | null;
  by_department: { key: string; label: string; amount: number }[]; strengths: string[];
};
type CatRow = { category_id: number; name: string; department: string; department_label: string; count: number; amount: number };
type Summary = { period: string; people: PersonRow[]; categories: CatRow[]; total: number; fund: Fund; can_manage: boolean };
type ErrData = { detail?: string; code?: string; can_force?: boolean };

const MONTHS = ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"];
const money = (n: number | null | undefined) => (n == null ? "—" : Math.round(n).toLocaleString("uk-UA") + " ₴");
const num = (n: number) => (Math.round(n * 100) / 100).toLocaleString("uk-UA");
const dmy = (s: string | null | undefined) => (s ? new Date(s).toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" }) : "");
const dmyhm = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
const monthLabel = (p: string) => (p && p.length >= 7 ? `${MONTHS[Number(p.slice(5, 7)) - 1] || ""} ${p.slice(0, 4)}` : p);
const thisMonth = () => { const t = new Date(); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}`; };
const errData = (e: unknown): ErrData => ((e as { data?: ErrData } | null)?.data || {});
const errText = (e: unknown, fb = "Помилка") => errData(e).detail || fb;
const uploadErr = (e: unknown) => {
  const m = String((e as Error | null)?.message || "");
  const i = m.indexOf("{");
  if (i >= 0) { try { return (JSON.parse(m.slice(i)) as ErrData).detail || "Не вдалося завантажити файл"; } catch { /* не JSON */ } }
  return "Не вдалося завантажити файл";
};
const toNum = (s: string) => Number(String(s).replace(",", ".").replace(/\s/g, "")) || 0;

const STATUS_COLORS: Record<string, [string, string]> = {
  taken: ["#e0f2fe", "#075985"], submitted: ["#fef3c7", "#92400e"], rework: ["#fee2e2", "#991b1b"],
  accepted: ["#dcfce7", "#166534"], cancelled: ["#f1f5f9", "#64748b"],
};
const STATE_TEXT: Record<string, string> = { busy: "Зайнято", limit: "Ліміт на місяць вичерпано", person_limit: "Ваш ліміт на місяць вичерпано" };
const ACT_LABEL: Record<string, string> = { take: "взято", submit: "здано", accept: "прийнято", rework: "на доробку", cancel: "скасовано" };

const TH: CSSProperties = { textAlign: "left", padding: "6px 8px", fontSize: 11, color: "#64748b", fontWeight: 600, borderBottom: "1px solid #e2e8f0", whiteSpace: "nowrap" };
const TD: CSSProperties = { padding: "6px 8px", borderBottom: "1px solid #f1f5f9", fontSize: 12.5, verticalAlign: "top" };
const INP: CSSProperties = { height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", fontSize: 13, background: "#fff", color: "#0f172a" };
const AREA: CSSProperties = { width: "100%", minHeight: 70, border: "1px solid #cbd5e1", borderRadius: 7, padding: 8, fontSize: 13, fontFamily: "inherit", resize: "vertical", boxSizing: "border-box", background: "#fff", color: "#0f172a" };
const LIST: CSSProperties = { maxHeight: "calc(100vh - 300px)", minHeight: 220, overflowY: "auto", paddingRight: 4 };
const ROW: CSSProperties = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" };
const WARN: CSSProperties = { background: "#fff7ed", border: "1px solid #fed7aa", color: "#9a3412", borderRadius: 8, padding: "8px 10px", fontSize: 12.5 };
const OKBOX: CSSProperties = { background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#166534", borderRadius: 8, padding: "8px 10px", fontSize: 12.5 };
const ERRBOX: CSSProperties = { color: "#dc2626", fontSize: 12.5 };
const LBL: CSSProperties = { fontSize: 11.5, color: "#64748b", display: "block", marginBottom: 3 };

function StatusChip({ status, label }: { status: string; label: string }) {
  const [bg, fg] = STATUS_COLORS[status] || ["#f1f5f9", "#334155"];
  return <span className="chip" style={{ background: bg, color: fg, fontWeight: 600 }}>{label}</span>;
}

function Steps({ text }: { text: string }) {
  const lines = text.split("\n").map((s) => s.trim()).filter(Boolean);
  if (!lines.length) return null;
  return <ol style={{ margin: "4px 0 0", paddingLeft: 20, fontSize: 12.5, lineHeight: 1.5 }}>{lines.map((l, i) => <li key={i}>{l}</li>)}</ol>;
}

const MAX_SUBS = 12;
let SUB_SEQ = 0;
const subKey = () => ++SUB_SEQ;
type EditSub = Sub & { k: number };
const leftSubs = (c: Claim) => (c.subtasks || []).filter((x) => !x.done);

/* підзадачі в картці задачі біржі: номер, що зробити, як зробити */
function SubList({ items }: { items: Sub[] }) {
  if (!items.length) return null;
  return (
    <ol style={{ margin: "4px 0 0", paddingLeft: 20, fontSize: 12.5, lineHeight: 1.5 }}>
      {items.map((x, i) => (
        <li key={i} style={{ marginBottom: 3 }}>
          <b>{x.title}</b>{x.how && <span className="muted"> — {x.how}</span>}
        </li>
      ))}
    </ol>
  );
}

function Progress({ done, total }: { done: number; total: number }) {
  if (!total) return null;
  const full = done >= total;
  return (
    <span className="chip" title="Виконано підзадач" style={{ background: full ? "#dcfce7" : "#f1f5f9", color: full ? "#166534" : "#334155", fontWeight: 600 }}>
      <Icon n="check-square" size={12} /> {done}/{total}
    </span>
  );
}

/* відмітки підзадач: виконавець ставить галочки, решта бачить, що відмічено */
function SubChecklist({ c, onChanged }: { c: Claim; onChanged: () => void }) {
  const [done, setDone] = useState<number[]>(() => (c.subtasks || []).filter((x) => x.done).map((x) => x.i));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const subs = c.subtasks || [];
  if (!subs.length) return null;
  const toggle = async (i: number) => {
    const next = done.includes(i) ? done.filter((x) => x !== i) : [...done, i].sort((a, b) => a - b);
    setBusy(true);
    setErr("");
    try {
      await api.post(`/api/bounty/claims/${c.id}/subtasks/`, { done: next });
      setDone(next);
      onChanged();
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  const n = c.can_check ? done.length : subs.filter((x) => x.done).length;
  return (
    <div style={{ marginTop: 8 }}>
      <div style={LBL}>Підзадачі · виконано {n}/{subs.length}{c.can_check ? " — відмічайте те, що вже зроблено" : ""}</div>
      {subs.map((x) => {
        const on = c.can_check ? done.includes(x.i) : x.done;
        return (
          <label key={x.i} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12.5, padding: "3px 0", cursor: c.can_check ? "pointer" : "default" }}>
            {c.can_check
              ? <input type="checkbox" checked={on} disabled={busy} onChange={() => toggle(x.i)} style={{ marginTop: 2 }} />
              : <Icon n={on ? "check" : "circle"} size={14} style={{ color: on ? "#16a34a" : "#cbd5e1", marginTop: 1 }} />}
            <span>
              <b style={{ textDecoration: on ? "line-through" : "none", opacity: on ? 0.7 : 1 }}>{x.i + 1}. {x.title}</b>
              {x.how && <span className="muted"> — {x.how}</span>}
            </span>
          </label>
        );
      })}
      {err && <div style={ERRBOX}>{err}</div>}
    </div>
  );
}

/* редактор підзадач у «Прайсі»: додати / прибрати / вище / нижче */
function SubtaskEditor({ subs, setSubs }: { subs: EditSub[]; setSubs: Dispatch<SetStateAction<EditSub[]>> }) {
  const upd = (k: number, field: "title" | "how", v: string) => setSubs((p) => p.map((x) => (x.k === k ? { ...x, [field]: v } : x)));
  const move = (i: number, d: number) => setSubs((p) => {
    const j = i + d;
    if (j < 0 || j >= p.length) return p;
    const n = [...p];
    [n[i], n[j]] = [n[j], n[i]];
    return n;
  });
  const del = (k: number) => setSubs((p) => p.filter((x) => x.k !== k));
  const add = () => setSubs((p) => [...p, { k: subKey(), title: "", how: "" }]);
  return (
    <div style={{ marginTop: 8 }}>
      <span style={LBL}>Підзадачі — по порядку; до кожної одним реченням «як зробити» (до {MAX_SUBS})</span>
      <div style={{ maxHeight: 360, overflowY: "auto" }}>
        {subs.map((x, i) => (
          <div key={x.k} style={{ ...ROW, marginBottom: 4, flexWrap: "nowrap" }}>
            <span className="muted" style={{ width: 20, textAlign: "right", flexShrink: 0 }}>{i + 1}.</span>
            <input style={{ ...INP, flex: "1 1 180px", minWidth: 0 }} placeholder="Що зробити" value={x.title} onChange={(e) => upd(x.k, "title", e.target.value)} />
            <input style={{ ...INP, flex: "2 1 260px", minWidth: 0 }} placeholder="Як зробити — одним реченням" value={x.how} onChange={(e) => upd(x.k, "how", e.target.value)} />
            <button className="btn btn-light" style={{ padding: "2px 6px" }} disabled={i === 0} title="Вище" onClick={() => move(i, -1)}>
              <Icon n="chevron-down" size={13} style={{ transform: "rotate(180deg)" }} />
            </button>
            <button className="btn btn-light" style={{ padding: "2px 6px" }} disabled={i === subs.length - 1} title="Нижче" onClick={() => move(i, 1)}>
              <Icon n="chevron-down" size={13} />
            </button>
            <button className="btn btn-light" style={{ padding: "2px 6px" }} title="Прибрати" onClick={() => del(x.k)}><Icon n="trash" size={13} /></button>
          </div>
        ))}
      </div>
      {subs.length < MAX_SUBS && (
        <button className="btn btn-light" style={{ fontSize: 12, marginTop: 2 }} onClick={add}><Icon n="plus" size={12} /> Підзадача</button>
      )}
    </div>
  );
}

/* ───────────── головний екран ───────────── */
export default function Bounty() {
  const [board, setBoard] = useState<Board | null>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("board");
  const load = useCallback(() => {
    api.get<Board>("/api/bounty/board/").then((b) => { setBoard(b); setErr(""); }).catch((e) => setErr(errText(e, "Не вдалося завантажити біржу задач")));
  }, []);
  useEffect(() => { load(); }, [load]);
  if (!board) {
    return <div className="scroll pad fade">{err ? <div className="panel" style={ERRBOX}>{err}</div> : <div className="muted">Завантаження…</div>}</div>;
  }
  const me = board.me;
  const tabs: [string, string][] = [["board", "Біржа"], ["mine", "Мої задачі" + (me.active_claims ? ` (${me.active_claims})` : "")]];
  if (me.can_review) tabs.push(["review", "На перевірку" + (board.review_count ? ` (${board.review_count})` : "")]);
  if (me.can_manage) tabs.push(["catalog", "Прайс"]);
  tabs.push(["summary", "Підсумки місяця"], ["help", "Як це працює"]);
  return (
    <div className="scroll pad fade">
      <div style={{ ...ROW, marginBottom: 6 }}>
        <Icon n="target" size={20} />
        <h2 style={{ margin: 0 }}>Біржа задач</h2>
        <span className="muted">додаткові задачі з оплатою · {monthLabel(board.month)} · прийняте йде окремим рядком у ЗП</span>
      </div>
      {me.standard && !me.standard.ok && me.standard.warning && (
        <div style={{ ...WARN, marginBottom: 8 }}><Icon n="warn" size={14} /> {me.standard.warning}</div>
      )}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "8px 0 12px" }}>
        {tabs.map(([k, l]) => (
          <button key={k} className={"btn" + (tab === k ? " btn-primary" : "")} onClick={() => setTab(k)}>{l}</button>
        ))}
        <button className="btn btn-light" onClick={load} title="Оновити"><Icon n="refresh" size={14} /></button>
      </div>
      {tab === "board" && <BoardTab board={board} onChanged={load} />}
      {tab === "mine" && <MineTab onChanged={load} />}
      {tab === "review" && me.can_review && <ReviewTab canManage={me.can_manage} users={board.users || []} onChanged={load} />}
      {tab === "catalog" && me.can_manage && <CatalogTab board={board} onChanged={load} />}
      {tab === "summary" && <SummaryTab />}
      {tab === "help" && <HelpTab minPct={me.min_standard_pct} />}
    </div>
  );
}

/* ───────────── біржа: відділи → напрями → задачі ───────────── */
function BoardTab({ board, onChanged }: { board: Board; onChanged: () => void }) {
  const [dep, setDep] = useState("");
  const [q, setQ] = useState("");
  const [onlyFree, setOnlyFree] = useState(false);
  const liveCats = new Set(board.categories.filter((c) => c.active).map((c) => c.id));
  const live = board.offers.filter((o) => o.active && liveCats.has(o.category_id));
  const deps = board.departments.filter((d) => live.some((o) => o.department === d.key));
  const cur = deps.some((d) => d.key === dep) ? dep : deps[0]?.key || "";
  if (!deps.length) {
    return (
      <div className="panel">
        <div className="muted">Поки що жодна задача не увімкнена.{board.me.can_manage ? " Увімкніть задачі у вкладці «Прайс» — по одній або цілим відділом." : " Власник увімкне їх найближчим часом."}</div>
      </div>
    );
  }
  const needle = q.trim().toLowerCase();
  const cats = board.categories.filter((c) => c.department === cur && c.active);
  const shown = (catId: number) => live.filter((o) => o.category_id === catId
    && (!needle || [o.title, o.how_to, o.expected_result || "", ...(o.subtasks || []).map((x) => x.title)].join(" ").toLowerCase().includes(needle))
    && (!onlyFree || o.state === "free" || o.state === "mine"));
  return (
    <>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {deps.map((d) => (
          <button key={d.key} className={"btn" + (cur === d.key ? " btn-primary" : " btn-light")} onClick={() => setDep(d.key)}>
            {d.label} <span className="muted" style={{ marginLeft: 4 }}>{live.filter((o) => o.department === d.key).length}</span>
          </button>
        ))}
      </div>
      <div style={{ ...ROW, marginBottom: 10 }}>
        <input style={{ ...INP, minWidth: 240 }} placeholder="Пошук задачі…" value={q} onChange={(e) => setQ(e.target.value)} />
        <label style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={onlyFree} onChange={(e) => setOnlyFree(e.target.checked)} /> лише вільні
        </label>
      </div>
      <div style={LIST}>
        {cats.map((c) => {
          const list = shown(c.id);
          if (!list.length) return null;
          return (
            <div key={c.id} style={{ marginBottom: 14 }}>
              <div className="label" style={{ marginBottom: 6 }}>{c.name}</div>
              {list.map((o) => <OfferCard key={o.id} o={o} std={board.me.standard} onTaken={onChanged} />)}
            </div>
          );
        })}
      </div>
    </>
  );
}

function OfferCard({ o, std, onTaken }: { o: Offer; std: Std; onTaken: () => void }) {
  const [open, setOpen] = useState(false);
  const [qty, setQty] = useState("1");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const perUnit = o.unit === "piece" || o.unit === "hour";
  const take = async () => {
    if (std && !std.ok && std.warning && !window.confirm(std.warning + "\n\nВсе одно взяти задачу?")) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.post<{ warning: string }>(`/api/bounty/offers/${o.id}/take/`, { qty: perUnit ? qty : 1 });
      setMsg({ ok: true, text: "Взято — задача у вкладці «Мої задачі»" + (r.warning ? " (з попередженням про стандарт)" : "") });
      onTaken();
    } catch (e) {
      setMsg({ ok: false, text: errText(e) });
    } finally {
      setBusy(false);
    }
  };
  const limits: string[] = [];
  if (o.monthly_limit_qty) limits.push(`ліміт ${o.monthly_limit_qty}/міс` + (o.left_qty != null ? ` (залишилось ${num(o.left_qty)})` : ""));
  if (o.max_per_person) limits.push(`на людину ${o.max_per_person}/міс`);
  if (o.subtasks?.length) limits.push(`підзадач: ${o.subtasks.length}`);
  limits.push(`термін ${o.due_days} дн.`);
  limits.push(`доказ: ${o.proof_label.toLowerCase()}`);
  limits.push(`приймає: ${o.checker_name || "власник"}`);
  return (
    <div className="panel" style={{ marginBottom: 8, padding: 12 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 320px", minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{o.title}</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{limits.join(" · ")}</div>
          {o.expected_result && (
            <div style={{ fontSize: 12.5, marginTop: 4 }}><Icon n="target" size={12} /> <b>Кінцевий результат:</b> {o.expected_result}</div>
          )}
        </div>
        <div style={{ ...ROW, justifyContent: "flex-end" }}>
          <span className="chip" style={{ background: "#eef2ff", color: "#3730a3", fontWeight: 700 }}>{o.unit_text}</span>
          {o.state === "free" && (
            <>
              {perUnit && (
                <input style={{ ...INP, width: 70 }} value={qty} onChange={(e) => setQty(e.target.value)} title={o.unit === "hour" ? "Скільки годин" : `Скільки (${o.unit_label || "шт"})`} />
              )}
              <button className="btn btn-primary" disabled={busy} onClick={take}><Icon n="check" size={14} /> Беру</button>
            </>
          )}
          {o.state === "mine" && <span className="chip" style={{ background: "#dcfce7", color: "#166534", fontWeight: 600 }}>Ви виконуєте</span>}
          {o.state && STATE_TEXT[o.state] && <button className="btn btn-light" disabled><Icon n="lock" size={14} /> {STATE_TEXT[o.state]}</button>}
        </div>
      </div>
      {o.state === "busy" && !!o.busy_by?.length && (
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          Виконує: {o.busy_by.map((b) => `${b.name}${b.due_at ? " до " + dmy(b.due_at) : ""}`).join(", ")}
        </div>
      )}
      <button className="btn btn-light" style={{ marginTop: 6, fontSize: 12, padding: "2px 8px" }} onClick={() => setOpen(!open)}>
        <Icon n="chevron-down" size={12} style={{ transform: open ? "rotate(180deg)" : "none" }} /> {open ? "Сховати" : "Навіщо, як зробити, підзадачі"}
      </button>
      {open && (
        <div style={{ marginTop: 6 }}>
          {o.why && <><div style={LBL}>Навіщо</div><div style={{ fontSize: 12.5 }}><Icon n="bulb" size={12} /> {o.why}</div></>}
          {o.how_to && <><div style={{ ...LBL, marginTop: 8 }}>Як зробити</div><Steps text={o.how_to} /></>}
          {!!o.subtasks?.length && <><div style={{ ...LBL, marginTop: 8 }}>Підзадачі ({o.subtasks.length})</div><SubList items={o.subtasks} /></>}
          {o.done_criteria && <><div style={{ ...LBL, marginTop: 8 }}>Що вважається виконаним · доказ: {o.proof_label.toLowerCase()}</div><div style={{ fontSize: 12.5 }}>{o.done_criteria}</div></>}
        </div>
      )}
      {msg && <div style={{ ...(msg.ok ? OKBOX : WARN), marginTop: 6 }}>{msg.text}</div>}
    </div>
  );
}

/* ───────────── мої задачі ───────────── */
function MineTab({ onChanged }: { onChanged: () => void }) {
  const [rows, setRows] = useState<Claim[] | null>(null);
  const [flt, setFlt] = useState("active");
  const [err, setErr] = useState("");
  const load = useCallback(() => {
    api.get<{ results: Claim[] }>("/api/bounty/claims/?scope=mine" + (flt === "active" ? "&status=active" : ""))
      .then((r) => { setRows(r.results); setErr(""); }).catch((e) => setErr(errText(e)));
  }, [flt]);
  useEffect(() => { load(); }, [load]);
  const done = () => { load(); onChanged(); };
  return (
    <>
      <div style={{ ...ROW, marginBottom: 10 }}>
        <button className={"btn" + (flt === "active" ? " btn-primary" : " btn-light")} onClick={() => setFlt("active")}>В роботі</button>
        <button className={"btn" + (flt === "all" ? " btn-primary" : " btn-light")} onClick={() => setFlt("all")}>Усі</button>
      </div>
      {err && <div style={ERRBOX}>{err}</div>}
      {!rows ? <div className="muted">Завантаження…</div> : rows.length === 0 ? (
        <div className="panel muted">{flt === "active" ? "Немає задач у роботі. Візьміть задачу на вкладці «Біржа»." : "Ви ще не брали задач."}</div>
      ) : (
        <div style={LIST}>{rows.map((c) => <ClaimCard key={c.id} c={c} mode="mine" onDone={done} />)}</div>
      )}
    </>
  );
}

function ClaimCard({ c, mode, onDone }: { c: Claim; mode: "mine" | "review" | "all"; onDone: () => void }) {
  const [open, setOpen] = useState(mode !== "mine");
  const [msg, setMsg] = useState("");
  const cancel = async () => {
    let comment = "";
    if (mode === "mine") {
      if (!window.confirm("Відмовитися від задачі? Вона знову стане вільною для інших.")) return;
    } else {
      const r = window.prompt(c.status === "accepted" ? "Скасувати прийняття (сума зникне із ЗП). Причина:" : "Зняти задачу з виконавця. Причина:", "");
      if (r === null) return;
      comment = r;
    }
    try { await api.post(`/api/bounty/claims/${c.id}/cancel/`, { comment }); onDone(); } catch (e) { setMsg(errText(e)); }
  };
  const money_ = c.status === "accepted" ? money(c.amount) : c.unit === "pct" ? c.unit_text : "≈ " + money(c.estimate);
  return (
    <div className="panel" style={{ marginBottom: 8, padding: 12, borderLeft: c.overdue ? "3px solid #dc2626" : undefined }}>
      <div style={{ display: "flex", gap: 10, justifyContent: "space-between", flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 320px", minWidth: 0 }}>
          <div style={{ fontWeight: 700 }}>{c.offer_title}</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            {c.department_label} · {c.category_name}{mode !== "mine" ? ` · ${c.user_name}` : ""} · взято {dmyhm(c.taken_at)}
            {(c.unit === "piece" || c.unit === "hour") ? ` · кількість ${num(c.qty)}` : ""}
          </div>
        </div>
        <div style={ROW}>
          <StatusChip status={c.status} label={c.status_label} />
          <Progress done={c.subtasks_done_count} total={c.subtasks_total} />
          <b>{money_}</b>
          {c.status === "accepted" && <span className="muted" style={{ fontSize: 12 }}>у ЗП за {monthLabel(c.payroll_period)}</span>}
          {(c.status === "taken" || c.status === "rework") && c.due_at && (
            <span style={{ fontSize: 12, color: c.overdue ? "#dc2626" : "#64748b" }}><Icon n="clock" size={12} /> до {dmyhm(c.due_at)}{c.overdue ? " — прострочено" : ""}</span>
          )}
        </div>
      </div>
      {c.std_warning && mode !== "mine" && <div style={{ ...WARN, marginTop: 6 }}>{c.std_warning}</div>}
      {c.expected_result && <div style={{ fontSize: 12.5, marginTop: 6 }}><Icon n="target" size={12} /> <b>Кінцевий результат:</b> {c.expected_result}</div>}
      {c.comment && (
        <div style={{ ...(c.status === "rework" ? WARN : { fontSize: 12.5 }), marginTop: 6 }}>
          <b>Коментар перевіряючого{c.reviewer_name ? ` (${c.reviewer_name})` : ""}:</b> {c.comment}
        </div>
      )}
      <button className="btn btn-light" style={{ marginTop: 6, fontSize: 12, padding: "2px 8px" }} onClick={() => setOpen(!open)}>
        <Icon n="chevron-down" size={12} style={{ transform: open ? "rotate(180deg)" : "none" }} /> {open ? "Сховати деталі" : "Деталі, доказ, історія"}
      </button>
      {open && (
        <div style={{ marginTop: 6 }}>
          {c.why && <><div style={LBL}>Навіщо</div><div style={{ fontSize: 12.5 }}>{c.why}</div></>}
          {c.how_to && <><div style={{ ...LBL, marginTop: 8 }}>Як зробити</div><Steps text={c.how_to} /></>}
          {!(c.can_check && mode === "mine") && <SubChecklist c={c} onChanged={onDone} />}
          {c.done_criteria && <><div style={{ ...LBL, marginTop: 8 }}>Що вважається виконаним · доказ: {c.proof_label.toLowerCase()}</div><div style={{ fontSize: 12.5 }}>{c.done_criteria}</div></>}
          <ProofBlock c={c} onChanged={onDone} />
          {c.history.length > 0 && (
            <div className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>
              {c.history.map((h, i) => <div key={i}>{dmyhm(h.at)} — {ACT_LABEL[h.act] || h.act} · {h.by_name}{h.note ? ` · ${h.note}` : ""}</div>)}
            </div>
          )}
        </div>
      )}
      {c.can_check && mode === "mine" && <SubChecklist c={c} onChanged={onDone} />}
      {c.can_submit && mode === "mine" && <SubmitForm c={c} onDone={onDone} />}
      {c.can_review && mode !== "mine" && <ReviewForm c={c} onDone={onDone} />}
      {c.can_cancel && (
        <div style={{ marginTop: 8 }}>
          <button className="btn btn-light" style={{ fontSize: 12 }} onClick={cancel}>
            <Icon n="x" size={12} /> {mode === "mine" ? "Відмовитися" : c.status === "accepted" ? "Скасувати прийняття" : "Зняти задачу"}
          </button>
        </div>
      )}
      {msg && <div style={{ ...ERRBOX, marginTop: 6 }}>{msg}</div>}
    </div>
  );
}

function ProofBlock({ c, onChanged }: { c: Claim; onChanged: () => void }) {
  const [prev, setPrev] = useState<Record<number, string>>({});
  const [err, setErr] = useState("");
  const canDelete = c.can_submit;
  if (!c.proof_url && !c.proof_text && !c.files.length) return null;
  const show = async (f: CFile) => {
    try {
      const u = await api.blobUrl(`/api/bounty/files/${f.id}/`);
      if (f.content_type.startsWith("image/")) setPrev((p) => ({ ...p, [f.id]: u }));
      else window.open(u, "_blank");
    } catch { setErr("Не вдалося відкрити файл"); }
  };
  const del = async (f: CFile) => {
    if (!window.confirm(`Прибрати файл «${f.filename}»?`)) return;
    try { await api.del(`/api/bounty/files/${f.id}/`); onChanged(); } catch (e) { setErr(errText(e)); }
  };
  return (
    <div style={{ marginTop: 8 }}>
      <div style={LBL}>Доказ</div>
      {c.proof_url && <div style={{ fontSize: 12.5 }}><Icon n="link" size={12} /> <a href={c.proof_url} target="_blank" rel="noreferrer">{c.proof_url}</a></div>}
      {c.proof_text && <div style={{ fontSize: 12.5, whiteSpace: "pre-wrap", marginTop: 4 }}>{c.proof_text}</div>}
      {c.files.map((f) => (
        <div key={f.id} style={{ marginTop: 4 }}>
          <div style={ROW}>
            <Icon n={f.content_type.startsWith("image/") ? "image" : "file"} size={13} />
            <span style={{ fontSize: 12.5 }}>{f.filename}</span>
            <span className="muted" style={{ fontSize: 11 }}>{Math.max(1, Math.round(f.size / 1024))} КБ</span>
            <button className="btn btn-light" style={{ fontSize: 11, padding: "1px 6px" }} onClick={() => show(f)}>{f.content_type.startsWith("image/") ? "Показати" : "Відкрити"}</button>
            {canDelete && <button className="btn btn-light" style={{ fontSize: 11, padding: "1px 6px" }} onClick={() => del(f)}><Icon n="trash" size={11} /></button>}
          </div>
          {prev[f.id] && <img src={prev[f.id]} alt={f.filename} style={{ maxWidth: 260, maxHeight: 200, borderRadius: 6, marginTop: 4, display: "block" }} />}
        </div>
      ))}
      {err && <div style={ERRBOX}>{err}</div>}
    </div>
  );
}

function SubmitForm({ c, onDone }: { c: Claim; onDone: () => void }) {
  const [url, setUrl] = useState(c.proof_url || "");
  const [text, setText] = useState(c.proof_text || "");
  const [qty, setQty] = useState(String(c.qty || 1));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const perUnit = c.unit === "piece" || c.unit === "hour";
  const upload = async (f: File | undefined) => {
    if (!f) return;
    if (f.size > 10 * 1024 * 1024) { setMsg("Файл більший за 10 МБ — стисніть його або дайте посилання на папку"); return; }
    setBusy(true);
    setMsg("");
    try { await api.upload(`/api/bounty/claims/${c.id}/files/`, f); onDone(); } catch (e) { setMsg(uploadErr(e)); } finally { setBusy(false); }
  };
  const send = async () => {
    const left = leftSubs(c);
    if (left.length && !window.confirm(`Не відмічено підзадач: ${left.length} з ${c.subtasks_total}\n`
      + left.map((x) => `• ${x.i + 1}. ${x.title}`).join("\n") + "\n\nВсе одно здати? Перевіряючий побачить, що не відмічено.")) return;
    setBusy(true);
    setMsg("");
    try {
      await api.post(`/api/bounty/claims/${c.id}/submit/`, { proof_url: url, proof_text: text, qty: perUnit ? qty : undefined });
      onDone();
    } catch (e) { setMsg(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div style={{ marginTop: 10, borderTop: "1px dashed #e2e8f0", paddingTop: 10 }}>
      <div className="label" style={{ marginBottom: 6 }}>Здати на перевірку</div>
      {leftSubs(c).length > 0 && (
        <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Не відмічено підзадач: {leftSubs(c).length} з {c.subtasks_total}. Здати можна, але перевіряючий це побачить.</div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 8 }}>
        <div>
          <span style={LBL}>Посилання на результат (папка, пост, відео)</span>
          <input style={{ ...INP, width: "100%", boxSizing: "border-box" }} placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
        {perUnit && (
          <div>
            <span style={LBL}>{c.unit === "hour" ? "Скільки годин відпрацьовано" : `Скільки зроблено (${c.unit_label || "шт"})`}</span>
            <input style={{ ...INP, width: 120 }} value={qty} onChange={(e) => setQty(e.target.value)} />
          </div>
        )}
        <div>
          <span style={LBL}>Фото / файл (до 10 МБ)</span>
          <input type="file" disabled={busy} onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
        </div>
      </div>
      <div style={{ marginTop: 8 }}>
        <span style={LBL}>Короткий звіт: що зроблено, номери угод / карток</span>
        <textarea style={AREA} value={text} onChange={(e) => setText(e.target.value)} />
      </div>
      <div style={{ ...ROW, marginTop: 8 }}>
        <button className="btn btn-green" disabled={busy} onClick={send}><Icon n="upload" size={14} /> Здати</button>
        {msg && <span style={ERRBOX}>{msg}</span>}
      </div>
    </div>
  );
}

function ReviewForm({ c, onDone }: { c: Claim; onDone: () => void }) {
  const [qty, setQty] = useState(String(c.qty));
  const [base, setBase] = useState(c.base_amount != null ? String(c.base_amount) : "");
  const [amount, setAmount] = useState("");
  const [quality, setQuality] = useState(0);
  const [comment, setComment] = useState("");
  const [period, setPeriod] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const perUnit = c.unit === "piece" || c.unit === "hour";
  const pct = c.unit === "pct";
  const calc = pct ? toNum(base) * c.price / 100 : c.price * (perUnit ? toNum(qty) : c.qty);
  const send = async (force: boolean) => {
    const body = {
      qty: perUnit ? qty : undefined, base_amount: pct ? base : undefined, amount: amount || undefined,
      quality: quality || undefined, comment, payroll_period: period || undefined, force,
    };
    await api.post(`/api/bounty/claims/${c.id}/accept/`, body);
  };
  const accept = async () => {
    setBusy(true);
    setMsg("");
    try {
      await send(false);
      onDone();
    } catch (e) {
      const d = errData(e);
      if (d.can_force && (d.code === "limit" || d.code === "fund") && window.confirm((d.detail || "") + "\n\nПрийняти понад ліміт (рішення керівника)?")) {
        try { await send(true); onDone(); } catch (e2) { setMsg(errText(e2)); }
      } else {
        setMsg(d.detail || errText(e));
      }
    } finally {
      setBusy(false);
    }
  };
  const rework = async () => {
    if (comment.trim().length < 3) { setMsg("Напишіть у коментарі, що саме доробити"); return; }
    setBusy(true);
    setMsg("");
    try { await api.post(`/api/bounty/claims/${c.id}/rework/`, { comment }); onDone(); } catch (e) { setMsg(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div style={{ marginTop: 10, borderTop: "1px dashed #e2e8f0", paddingTop: 10 }}>
      <div className="label" style={{ marginBottom: 6 }}>Перевірка</div>
      {leftSubs(c).length > 0 && (
        <div style={{ ...WARN, marginBottom: 8 }}>
          <Icon n="warn" size={13} /> Виконавець не відмітив {leftSubs(c).length} з {c.subtasks_total} підзадач: {leftSubs(c).map((x) => `${x.i + 1}. ${x.title}`).join("; ")}
        </div>
      )}
      <div style={{ ...ROW, alignItems: "flex-end" }}>
        {perUnit && (
          <div><span style={LBL}>{c.unit === "hour" ? "Годин" : `Кількість (${c.unit_label || "шт"})`}</span><input style={{ ...INP, width: 90 }} value={qty} onChange={(e) => setQty(e.target.value)} /></div>
        )}
        {pct && (
          <div><span style={LBL}>Сума оплат, ₴ (з неї {num(c.price)}%)</span><input style={{ ...INP, width: 140 }} value={base} onChange={(e) => setBase(e.target.value)} /></div>
        )}
        <div><span style={LBL}>До виплати</span><b style={{ fontSize: 15 }}>{money(amount ? toNum(amount) : calc)}</b></div>
        {c.can_force && (
          <div><span style={LBL}>Інша сума (власник)</span><input style={{ ...INP, width: 110 }} placeholder={String(Math.round(calc))} value={amount} onChange={(e) => setAmount(e.target.value)} /></div>
        )}
        <div>
          <span style={LBL}>Місяць ЗП</span>
          <input type="month" style={INP} value={period} onChange={(e) => setPeriod(e.target.value)} title="Порожньо — поточний (або наступний, якщо ЗП вже затверджено)" />
        </div>
        <div>
          <span style={LBL}>Якість</span>
          <div style={{ display: "flex", gap: 2 }}>
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} className="btn btn-light" style={{ padding: "2px 4px" }} onClick={() => setQuality(quality === n ? 0 : n)} title={`${n} з 5`}>
                <Icon n="star" size={15} style={{ color: n <= quality ? "#f59e0b" : "#cbd5e1", fill: n <= quality ? "#f59e0b" : "none" }} />
              </button>
            ))}
          </div>
        </div>
      </div>
      <div style={{ marginTop: 8 }}>
        <span style={LBL}>Коментар (для «На доробку» — обовʼязково)</span>
        <textarea style={{ ...AREA, minHeight: 50 }} value={comment} onChange={(e) => setComment(e.target.value)} />
      </div>
      <div style={{ ...ROW, marginTop: 8 }}>
        <button className="btn btn-green" disabled={busy} onClick={accept}><Icon n="check" size={14} /> Прийнято</button>
        <button className="btn btn-light" disabled={busy} onClick={rework}><Icon n="refresh" size={14} /> На доробку</button>
        {msg && <span style={ERRBOX}>{msg}</span>}
      </div>
    </div>
  );
}

/* ───────────── перевірка і всі задачі команди ───────────── */
function ReviewTab({ canManage, users, onChanged }: { canManage: boolean; users: UserOpt[]; onChanged: () => void }) {
  const [scope, setScope] = useState<"review" | "all">("review");
  const [status, setStatus] = useState("");
  const [month, setMonth] = useState("");
  const [uid, setUid] = useState("");
  const [rows, setRows] = useState<Claim[] | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => {
    const url = scope === "review" ? "/api/bounty/claims/?scope=review"
      : `/api/bounty/claims/?scope=all&status=${encodeURIComponent(status)}&month=${encodeURIComponent(month)}&user_id=${encodeURIComponent(uid)}`;
    setRows(null);
    api.get<{ results: Claim[] }>(url).then((r) => { setRows(r.results); setErr(""); }).catch((e) => setErr(errText(e)));
  }, [scope, status, month, uid]);
  useEffect(() => { load(); }, [load]);
  const done = () => { load(); onChanged(); };
  return (
    <>
      <div style={{ ...ROW, marginBottom: 10 }}>
        <button className={"btn" + (scope === "review" ? " btn-primary" : " btn-light")} onClick={() => setScope("review")}>Чекають перевірки</button>
        {canManage && <button className={"btn" + (scope === "all" ? " btn-primary" : " btn-light")} onClick={() => setScope("all")}>Усі задачі команди</button>}
        {scope === "all" && (
          <>
            <select style={INP} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">усі статуси</option>
              <option value="active">в роботі (взято / здано / доробка)</option>
              <option value="taken">взято</option>
              <option value="submitted">здано</option>
              <option value="rework">на доробці</option>
              <option value="accepted">прийнято</option>
              <option value="cancelled">скасовано</option>
            </select>
            <input type="month" style={INP} value={month} onChange={(e) => setMonth(e.target.value)} />
            <select style={INP} value={uid} onChange={(e) => setUid(e.target.value)}>
              <option value="">усі співробітники</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </>
        )}
      </div>
      {err && <div style={ERRBOX}>{err}</div>}
      {!rows ? <div className="muted">Завантаження…</div> : rows.length === 0 ? (
        <div className="panel muted">{scope === "review" ? "Немає задач на перевірку." : "Нічого не знайдено."}</div>
      ) : (
        <div style={LIST}>{rows.map((c) => <ClaimCard key={c.id} c={c} mode={scope} onDone={done} />)}</div>
      )}
    </>
  );
}

/* ───────────── прайс: додати / змінити / видалити / увімкнути ───────────── */
type Draft = Record<string, string | boolean>;

const emptyDraft = (catId: number): Draft => ({
  category_id: String(catId), title: "", how_to: "", done_criteria: "", proof_type: "any", unit: "task", unit_label: "",
  price: "", monthly_limit_qty: "0", max_per_person: "0", max_takers: "1", due_days: "3", checker_id: "", active: false, note: "",
  why: "", expected_result: "",
});
const draftOf = (o: Offer): Draft => ({
  category_id: String(o.category_id), title: o.title, how_to: o.how_to, done_criteria: o.done_criteria, proof_type: o.proof_type,
  unit: o.unit, unit_label: o.unit_label, price: String(o.price), monthly_limit_qty: String(o.monthly_limit_qty),
  max_per_person: String(o.max_per_person), max_takers: String(o.max_takers), due_days: String(o.due_days),
  checker_id: o.checker_id ? String(o.checker_id) : "", active: o.active, note: o.note,
  why: o.why || "", expected_result: o.expected_result || "",
});

function CatalogTab({ board, onChanged }: { board: Board; onChanged: () => void }) {
  const [dep, setDep] = useState(board.departments[0]?.key || "marketing");
  const [editing, setEditing] = useState<string | null>(null);
  const [newCat, setNewCat] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [showArch, setShowArch] = useState(false);
  const d = board.departments.find((x) => x.key === dep);
  const cats = board.categories.filter((c) => c.department === dep).sort((a, b) => a.order - b.order || a.id - b.id);
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setMsg(null);
    try { await fn(); if (ok) setMsg({ ok: true, text: ok }); onChanged(); } catch (e) { setMsg({ ok: false, text: errText(e) }); }
  };
  const activateDep = (on: boolean) => {
    const n = board.offers.filter((o) => o.department === dep).length;
    if (!window.confirm(on ? `Увімкнути всі ${n} задач відділу «${d?.label}»? Співробітники одразу побачать їх і зможуть брати.` : `Вимкнути всі задачі відділу «${d?.label}»? Уже взяті доробляються і приймаються як звичайно.`)) return;
    run(() => api.post("/api/bounty/offers/activate/", { department: dep, active: on }), on ? "Відділ увімкнено" : "Відділ вимкнено");
  };
  const addCat = () => {
    if (!newCat.trim()) return;
    run(async () => { await api.post("/api/bounty/categories/", { department: dep, name: newCat.trim() }); setNewCat(""); }, "Напрям додано");
  };
  const fund = board.fund;
  return (
    <>
      {fund && <FundBlock fund={fund} />}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "10px 0" }}>
        {board.departments.map((x) => (
          <button key={x.key} className={"btn" + (dep === x.key ? " btn-primary" : " btn-light")} onClick={() => { setDep(x.key); setEditing(null); }}>
            {x.label} <span className="muted" style={{ marginLeft: 4 }}>{x.n_active}/{x.n_total}</span>
          </button>
        ))}
      </div>
      <div style={{ ...ROW, marginBottom: 10 }}>
        <button className="btn btn-green" onClick={() => activateDep(true)}><Icon n="check" size={14} /> Увімкнути весь відділ</button>
        <button className="btn btn-light" onClick={() => activateDep(false)}><Icon n="lock" size={14} /> Вимкнути весь відділ</button>
        <span style={{ flex: 1 }} />
        <input style={{ ...INP, minWidth: 200 }} placeholder="Новий напрям (напр. «Монтаж»)" value={newCat} onChange={(e) => setNewCat(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addCat(); }} />
        <button className="btn" onClick={addCat}><Icon n="plus" size={14} /> Напрям</button>
      </div>
      {msg && <div style={{ ...(msg.ok ? OKBOX : WARN), marginBottom: 8 }}>{msg.text}</div>}
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        Позначка «ціна для обговорення» — ціни запропоновані CRM. Нова або змінена задача не діє, доки не ввімкнена. Зміна ціни не чіпає вже взяті задачі.
      </div>
      <div style={LIST}>
        {cats.length === 0 && <div className="panel muted">У відділі ще немає напрямів — додайте перший.</div>}
        {cats.map((c, i) => (
          <CategoryBlock key={c.id} cat={c} first={i === 0} last={i === cats.length - 1} board={board}
            editing={editing} setEditing={setEditing} run={run} />
        ))}
        {!!board.archived_offers?.length && (
          <div className="panel" style={{ marginTop: 10 }}>
            <button className="btn btn-light" onClick={() => setShowArch(!showArch)}>
              <Icon n="trash" size={13} /> Видалені задачі ({board.archived_offers.length})
            </button>
            {showArch && board.archived_offers.map((a) => (
              <div key={a.id} style={{ ...ROW, marginTop: 6, fontSize: 12.5 }}>
                <span>{a.title}</span><span className="muted">· {a.category_name}</span>
                <button className="btn btn-light" style={{ fontSize: 11, padding: "1px 6px" }} onClick={() => run(() => api.post(`/api/bounty/offers/${a.id}/restore/`), "Задачу відновлено (вимкнена)")}>Відновити</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function CategoryBlock({ cat, first, last, board, editing, setEditing, run }: {
  cat: Cat; first: boolean; last: boolean; board: Board; editing: string | null;
  setEditing: (v: string | null) => void; run: (fn: () => Promise<unknown>, ok?: string) => void;
}) {
  const offers = board.offers.filter((o) => o.category_id === cat.id).sort((a, b) => a.order - b.order || a.id - b.id);
  const rename = () => {
    const name = window.prompt("Нова назва напряму", cat.name);
    if (name && name.trim() && name.trim() !== cat.name) run(() => api.patch(`/api/bounty/categories/${cat.id}/`, { name: name.trim() }));
  };
  const remove = () => {
    if (!window.confirm(`Видалити напрям «${cat.name}» разом з ${offers.length} задачами? Уже взяті доробляються і приймаються як звичайно.`)) return;
    run(() => api.del(`/api/bounty/categories/${cat.id}/`), "Напрям видалено");
  };
  return (
    <div className="panel" style={{ marginBottom: 10, padding: 12, opacity: cat.active ? 1 : 0.7 }}>
      <div style={{ ...ROW, marginBottom: 8 }}>
        <b style={{ fontSize: 14 }}>{cat.name}</b>
        {!cat.active && <span className="chip">напрям прихований</span>}
        <span style={{ flex: 1 }} />
        <button className="btn btn-light" style={{ padding: "2px 6px" }} disabled={first} title="Вище" onClick={() => run(() => api.post(`/api/bounty/categories/${cat.id}/move/`, { dir: "up" }))}>
          <Icon n="chevron-down" size={13} style={{ transform: "rotate(180deg)" }} />
        </button>
        <button className="btn btn-light" style={{ padding: "2px 6px" }} disabled={last} title="Нижче" onClick={() => run(() => api.post(`/api/bounty/categories/${cat.id}/move/`, { dir: "down" }))}>
          <Icon n="chevron-down" size={13} />
        </button>
        <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => run(() => api.post("/api/bounty/offers/activate/", { category_id: cat.id, active: true }), "Напрям увімкнено")}>Увімкнути всі</button>
        <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => run(() => api.post("/api/bounty/offers/activate/", { category_id: cat.id, active: false }), "Напрям вимкнено")}>Вимкнути всі</button>
        <button className="btn btn-light" style={{ padding: "2px 6px" }} title="Перейменувати" onClick={rename}><Icon n="pencil" size={13} /></button>
        <button className="btn btn-light" style={{ padding: "2px 6px" }} title="Видалити напрям" onClick={remove}><Icon n="trash" size={13} /></button>
      </div>
      {offers.map((o, i) => (
        editing === `o${o.id}` ? (
          <OfferEditor key={o.id} offer={o} catId={cat.id} board={board} onClose={() => setEditing(null)} run={run} />
        ) : (
          <OfferRow key={o.id} o={o} first={i === 0} last={i === offers.length - 1} onEdit={() => setEditing(`o${o.id}`)} run={run} />
        )
      ))}
      {editing === `n${cat.id}` ? (
        <OfferEditor offer={null} catId={cat.id} board={board} onClose={() => setEditing(null)} run={run} />
      ) : (
        <button className="btn btn-light" style={{ marginTop: 6, fontSize: 12 }} onClick={() => setEditing(`n${cat.id}`)}><Icon n="plus" size={12} /> Додати задачу</button>
      )}
    </div>
  );
}

function OfferRow({ o, first, last, onEdit, run }: {
  o: Offer; first: boolean; last: boolean; onEdit: () => void; run: (fn: () => Promise<unknown>, ok?: string) => void;
}) {
  const remove = () => {
    if (!window.confirm(`Видалити задачу «${o.title}»? Її можна буде відновити з «Видалені задачі».`)) return;
    run(() => api.del(`/api/bounty/offers/${o.id}/`), "Задачу видалено");
  };
  const limits = [o.monthly_limit_qty ? `ліміт ${o.monthly_limit_qty}/міс` : "без ліміту", o.max_per_person ? `на людину ${o.max_per_person}` : "",
    o.max_takers === 1 ? "одна людина" : o.max_takers ? `до ${o.max_takers} людей` : "будь-скільки людей",
    o.subtasks?.length ? `підзадач: ${o.subtasks.length}` : "без підзадач", `приймає: ${o.checker_name || "власник"}`].filter(Boolean);
  return (
    <div style={{ ...ROW, padding: "6px 0", borderTop: "1px solid #f1f5f9" }}>
      <label title={o.active ? "Увімкнена — видно всім" : "Вимкнена — співробітники не бачать"} style={{ display: "flex", alignItems: "center" }}>
        <input type="checkbox" checked={o.active} onChange={(e) => run(() => api.patch(`/api/bounty/offers/${o.id}/`, { active: e.target.checked }))} />
      </label>
      <div style={{ flex: "1 1 300px", minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13, opacity: o.active ? 1 : 0.65 }}>{o.title}</div>
        <div className="muted" style={{ fontSize: 11.5 }}>{limits.join(" · ")}{o.note ? ` · ${o.note}` : ""}</div>
      </div>
      <span className="chip" style={{ background: "#eef2ff", color: "#3730a3", fontWeight: 700 }}>{o.unit_text}</span>
      <button className="btn btn-light" style={{ padding: "2px 6px" }} disabled={first} title="Вище" onClick={() => run(() => api.post(`/api/bounty/offers/${o.id}/move/`, { dir: "up" }))}>
        <Icon n="chevron-down" size={13} style={{ transform: "rotate(180deg)" }} />
      </button>
      <button className="btn btn-light" style={{ padding: "2px 6px" }} disabled={last} title="Нижче" onClick={() => run(() => api.post(`/api/bounty/offers/${o.id}/move/`, { dir: "down" }))}>
        <Icon n="chevron-down" size={13} />
      </button>
      <button className="btn btn-light" style={{ padding: "2px 6px" }} title="Змінити" onClick={onEdit}><Icon n="pencil" size={13} /></button>
      <button className="btn btn-light" style={{ padding: "2px 6px" }} title="Видалити" onClick={remove}><Icon n="trash" size={13} /></button>
    </div>
  );
}

function OfferEditor({ offer, catId, board, onClose, run }: {
  offer: Offer | null; catId: number; board: Board; onClose: () => void; run: (fn: () => Promise<unknown>, ok?: string) => void;
}) {
  const [f, setF] = useState<Draft>(() => (offer ? draftOf(offer) : emptyDraft(catId)));
  const [subs, setSubs] = useState<EditSub[]>(() => (offer?.subtasks || []).map((x) => ({ ...x, k: subKey() })));
  const set = (k: string, v: string | boolean) => setF((p) => ({ ...p, [k]: v }));
  const s = (k: string) => String(f[k] ?? "");
  const save = () => {
    const body = { ...f, checker_id: s("checker_id") || null, category_id: Number(s("category_id")),
      subtasks: subs.map((x) => ({ title: x.title, how: x.how })) };
    run(async () => {
      if (offer) await api.patch(`/api/bounty/offers/${offer.id}/`, body);
      else await api.post("/api/bounty/offers/", body);
      onClose();
    }, offer ? "Задачу збережено" : "Задачу додано");
  };
  const txt = (k: string, label: string, w = 120) => (
    <div><span style={LBL}>{label}</span><input style={{ ...INP, width: w }} value={s(k)} onChange={(e) => set(k, e.target.value)} /></div>
  );
  return (
    <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 10, margin: "6px 0" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 8 }}>
        <div style={{ gridColumn: "1 / -1" }}>
          <span style={LBL}>Назва задачі</span>
          <input style={{ ...INP, width: "100%", boxSizing: "border-box" }} value={s("title")} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div>
          <span style={LBL}>Напрям</span>
          <select style={{ ...INP, width: "100%" }} value={s("category_id")} onChange={(e) => set("category_id", e.target.value)}>
            {board.categories.map((c) => <option key={c.id} value={c.id}>{c.department_label} · {c.name}</option>)}
          </select>
        </div>
        <div>
          <span style={LBL}>Хто приймає</span>
          <select style={{ ...INP, width: "100%" }} value={s("checker_id")} onChange={(e) => set("checker_id", e.target.value)}>
            <option value="">власник</option>
            {(board.users || []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
      </div>
      <div style={{ ...ROW, marginTop: 8, alignItems: "flex-end" }}>
        <div>
          <span style={LBL}>Одиниця</span>
          <select style={INP} value={s("unit")} onChange={(e) => set("unit", e.target.value)}>
            {board.units.map((u) => <option key={u.key} value={u.key}>{u.label}</option>)}
          </select>
        </div>
        {txt("price", s("unit") === "pct" ? "Відсоток, %" : "Ціна, ₴", 100)}
        {s("unit") === "piece" && txt("unit_label", "Штука — це (відео, контакт…)", 170)}
        {txt("monthly_limit_qty", "Ліміт на місяць (0 — без)", 90)}
        {txt("max_per_person", "На людину (0 — без)", 90)}
        {txt("max_takers", "Людей одночасно (0 — будь-скільки)", 90)}
        {txt("due_days", "Термін, днів", 70)}
        <div>
          <span style={LBL}>Доказ</span>
          <select style={INP} value={s("proof_type")} onChange={(e) => set("proof_type", e.target.value)}>
            {board.proofs.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
        </div>
      </div>
      <div style={{ marginTop: 8 }}>
        <span style={LBL}>Навіщо — один рядок (що це дає бізнесу)</span>
        <input style={{ ...INP, width: "100%", boxSizing: "border-box" }} value={s("why")} onChange={(e) => set("why", e.target.value)} />
      </div>
      <div style={{ marginTop: 8 }}>
        <span style={LBL}>Кінцевий результат — що і скільки має бути зроблено (можна перевірити)</span>
        <textarea style={{ ...AREA, minHeight: 50 }} value={s("expected_result")} onChange={(e) => set("expected_result", e.target.value)} />
      </div>
      <div style={{ marginTop: 8 }}>
        <span style={LBL}>Як зробити — загальні правила, кожне з нового рядка</span>
        <textarea style={{ ...AREA, minHeight: 60 }} value={s("how_to")} onChange={(e) => set("how_to", e.target.value)} />
      </div>
      <SubtaskEditor subs={subs} setSubs={setSubs} />
      <div style={{ marginTop: 8 }}>
        <span style={LBL}>Що вважається виконаним і який доказ (для перевіряючого)</span>
        <textarea style={{ ...AREA, minHeight: 50 }} value={s("done_criteria")} onChange={(e) => set("done_criteria", e.target.value)} />
      </div>
      <div style={{ ...ROW, marginTop: 8 }}>
        {txt("note", "Примітка (службова)", 220)}
        <label style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center", marginTop: 14 }}>
          <input type="checkbox" checked={!!f.active} onChange={(e) => set("active", e.target.checked)} /> увімкнена (видно співробітникам)
        </label>
        <span style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={save}><Icon n="check" size={14} /> Зберегти</button>
        <button className="btn btn-light" onClick={onClose}>Скасувати</button>
      </div>
    </div>
  );
}

function FundBlock({ fund }: { fund: NonNullable<Fund> }) {
  return (
    <div className="panel" style={{ padding: 12 }}>
      <div style={ROW}>
        <Icon n="wallet" size={16} />
        <b>Фонд «{fund.name}» · {monthLabel(fund.period)}</b>
        <span className="muted" style={{ fontSize: 12.5 }}>
          ліміт {fund.enforced ? money(fund.limit) : "не задано"} · прийнято {money(fund.used)} · у роботі ≈ {money(fund.reserved)}
          {fund.left != null ? ` · вільно ${money(fund.left)}` : ""}
        </span>
      </div>
      {fund.warning && <div style={{ ...WARN, marginTop: 6 }}>{fund.warning}. Ліміт задається у Фінмоделі: стаття «{fund.name}», ₴ на місяць.</div>}
    </div>
  );
}

/* ───────────── підсумки місяця ───────────── */
function SummaryTab() {
  const [month, setMonth] = useState(thisMonth());
  const [d, setD] = useState<Summary | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!month) return;
    setD(null);
    api.get<Summary>(`/api/bounty/summary/?month=${month}`).then((r) => { setD(r); setErr(""); }).catch((e) => setErr(errText(e)));
  }, [month]);
  return (
    <>
      <div style={{ ...ROW, marginBottom: 10 }}>
        <span className="muted">Місяць ЗП:</span>
        <input type="month" style={INP} value={month} onChange={(e) => setMonth(e.target.value)} />
        {d && <b>Разом прийнято: {money(d.total)}</b>}
      </div>
      {err && <div style={ERRBOX}>{err}</div>}
      {!d ? <div className="muted">Завантаження…</div> : (
        <>
          {d.fund && <div style={{ marginBottom: 10 }}><FundBlock fund={d.fund} /></div>}
          <div className="panel" style={{ marginBottom: 12 }}>
            <div className="label" style={{ marginBottom: 6 }}>{d.can_manage ? "Хто скільки заробив на біржі" : "Мій заробіток на біржі"}</div>
            {d.people.length === 0 ? <div className="muted">За цей місяць прийнятих задач немає.</div> : (
              <div style={{ overflowX: "auto", maxHeight: 420, overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720 }}>
                  <thead><tr>
                    <th style={TH}>Співробітник</th><th style={TH}>Задач</th><th style={TH}>Сума</th><th style={TH}>Якість</th>
                    <th style={TH}>Вчасно</th><th style={TH}>Доробок</th><th style={TH}>По відділах</th><th style={TH}>Сильні сторони (3 міс.)</th>
                  </tr></thead>
                  <tbody>
                    {d.people.map((p) => (
                      <tr key={p.user_id}>
                        <td style={TD}><b>{p.name}</b></td>
                        <td style={TD}>{p.count}</td>
                        <td style={TD}><b>{money(p.amount)}</b></td>
                        <td style={TD}>{p.avg_quality != null ? `${p.avg_quality} з 5` : "—"}</td>
                        <td style={TD}>{p.on_time_pct != null ? `${p.on_time_pct}%` : "—"}</td>
                        <td style={TD}>{p.reworks}</td>
                        <td style={TD}>{p.by_department.map((x) => `${x.label}: ${money(x.amount)}`).join("; ")}</td>
                        <td style={TD}>{p.strengths.length ? p.strengths.join("; ") : <span className="muted">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {d.categories.length > 0 && (
            <div className="panel">
              <div className="label" style={{ marginBottom: 6 }}>По напрямах</div>
              <div style={{ overflowX: "auto", maxHeight: 360, overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 480 }}>
                  <thead><tr><th style={TH}>Відділ</th><th style={TH}>Напрям</th><th style={TH}>Задач</th><th style={TH}>Сума</th></tr></thead>
                  <tbody>
                    {d.categories.map((c) => (
                      <tr key={c.category_id}><td style={TD}>{c.department_label}</td><td style={TD}>{c.name}</td><td style={TD}>{c.count}</td><td style={TD}>{money(c.amount)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

/* ───────────── як це працює ───────────── */
function HelpTab({ minPct }: { minPct: number }) {
  const items = [
    "Біржа — це прайс додаткових задач з оплатою: що зробити, як, що вважається виконаним, скільки платимо і скільки разів на місяць.",
    "Тиснете «Беру» — задача ваша, зʼявляється термін. Якщо задачу виконує одна людина, інші бачать «Зайнято». Штучні задачі (відео, контакти, дощечки) можуть брати кілька людей.",
    "У кожної задачі є «Кінцевий результат» і підзадачі з простою інструкцією. Узяли задачу — у «Мої задачі» відмічайте виконані підзадачі (видно прогрес «3/5»). Здати можна будь-коли, але перевіряючий побачить, що не відмічено.",
    "Виконали — «Мої задачі» → додаєте доказ (посилання, фото або короткий звіт) → «Здати».",
    "Власник або призначений перевіряючий тисне «Прийнято» або «На доробку» з коментарем. Свою задачу ніхто сам не приймає.",
    "Прийнята задача йде окремим рядком «Задачі з біржі» у вашу ЗП за цей місяць. Якщо ЗП за місяць уже затверджено — у наступний.",
    `Спершу — основна робота: брати задачі з біржі варто, коли ваш основний стандарт від ${minPct}%. Нижче — CRM попередить, а перевіряючий побачить попередження.`,
    "Гроші на біржу — з окремого фонду «Біржа задач» з лімітом на місяць. Коли фонд вичерпано, нові задачі взяти не можна до наступного місяця.",
    "Не встигаєте — «Відмовитися», щоб задача звільнилась для інших. Прострочені задачі видно червоним.",
  ];
  return (
    <div className="panel">
      <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.7, fontSize: 13 }}>{items.map((t, i) => <li key={i}>{t}</li>)}</ol>
    </div>
  );
}
