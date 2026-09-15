import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { Icon } from "../Icon";

/* Налаштування → Ставки співробітників (14.09, рішення Олега «все з одного місця»).
 * Тут задаються оклади, % з маржі, % з обороту, гарантія новачку, відрядна оплата, акти обʼєктів.
 * Звідси беруть: ЗП (Фінанси → ЗП/KPI) і бонус у картці угоди. Точка беззбитковості — Фінанси (фонди «Планування»),
 * акти обʼєктів — картка клієнта (ObjectActsBlock).
 * 14.09 (payrates-ux, «усе врозкид, незрозуміло, чому в Лаптева 23 766»): схема відкривається ЧИТАННЯМ — таблиця
 * «Частина оплати | Як рахується | Сума»; кнопка «Змінити» → рівна форма (підписи 180px). Справа — вартість з розшифровкою
 * (бекенд scheme_cost: breakdown / fixed_explain). Ставки складу — ті самі статті Фінмоделі (PATCH /api/finmodel-articles/<id>/).
 * Зміна з наступного місяця = нова версія; минулі місяці не перераховуються.
 * 15.09 (whkpi, «KPI складу ок, я затверджую»): у стандарту можуть бути пункти (params.criteria). У читанні — нумерований
 * список «вимірює CRM / відмічає керівник»; у «Розрахунку за місяць» — підказка CRM по пунктах, які вона вимірює
 * (GET /api/payroll/wh-kpi/), і галочки керівника по решті → оцінка; збереження — POST /api/payroll/wh-kpi/
 * (без цього маршруту — лише оцінка через /components/<id>/mark/). Сума як і раніше = максимум × оцінка. */

type Comp = { id?: number; kind: string; kind_label?: string; title: string; params: any; active?: boolean };
type Step = { label: string; amount: number; hint?: string; sub?: boolean; plus?: boolean; total?: boolean };
type GInfo = { amount: number; months: number; start: string | null; end: string | null; active: boolean; status: string };
type Cost = {
  fixed_net: number; fixed_cost: number; taxes_ratio: number; guarantee: number; parts: any[];
  fixed_items?: { kind: string; title: string; amount: number }[]; fixed_sum?: number; guarantee_info?: GInfo | null;
  fixed_explain?: string; fixed_notes?: string[]; breakdown?: Step[]; breakdown_text?: string;
};
type Scheme = {
  id: number; user_id: number | null; user_name: string; position: string; department: string; title: string;
  purpose: string; status: string; employment: string; employment_label: string; valid_from: string; valid_to: string | null;
  is_vacancy: boolean; in_plan: boolean; planned_start: string | null; options: any; note: string; components: Comp[]; cost?: Cost;
};
type WhRate = { id: number; code: string; name: string; value: number; unit: string; auto: string; auto_note: string };
type Crit = { key: string; title: string; how_measured: string; target?: string; target_pct?: number };
type SugPoint = { n: number; key: string; title: string; how_measured: string; target: string; value: number | null; value_text: string;
  pass: boolean | null; details: string[]; hint?: string; mark: boolean; marked: boolean };
type Sug = { period: string; from: string; to: string | null; partial: boolean; points: SugPoint[]; good: number; suggested_pct: number;
  suggested_score: number; workdays: number; workdays_source: string; rule: string; criteria_source: string };

const money = (n: any) => Math.round(Number(n || 0)).toLocaleString("uk-UA") + " ₴";
const num = (n: any) => Math.round(Number(n || 0)).toLocaleString("uk-UA");
const dec = (n: any, d = 2) => Number(n || 0).toLocaleString("uk-UA", { minimumFractionDigits: d, maximumFractionDigits: d });
const pc = (v: any) => String(Number(v ?? 0)).replace(".", ",");
const month = () => new Date().toISOString().slice(0, 7);
const dm = (s: string | null) => (s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "");
const DEPTS = ["Продажі", "Склад", "Маркетинг", "Офіс"];
/* 15.09 (whkpi): 8 пунктів стандарту складу — копія backend apps/payroll/wh_kpi.py WH_STANDARD_CRITERIA (ключі мають збігатися).
 * Пункти з ключами WH_AUTO_KEYS CRM рахує сама (1, 4, 5, 6), решту відмічає керівник. */
const WH_AUTO_KEYS = ["ship_same_day", "weight_photo", "queue_clean", "receipt_same_day"];
const WH_STD_CRITERIA: Crit[] = [
  { key: "ship_same_day", title: "Відвантаження вчасно: оплачено до 14:00 — відправлено того ж дня", how_measured: "auto", target: "не менше 95% замовлень", target_pct: 95 },
  { key: "no_picking_errors", title: "Нуль помилок комплектації (не той товар / колір / кількість)", how_measured: "manual", target: "0 підтверджених помилок; кожна знижує стандарт; утримання 50% — окремо, як і було" },
  { key: "no_damage", title: "Нуль пошкоджень у дорозі через пакування (скарги / повернення «розбилось / протекло»)", how_measured: "manual", target: "0 випадків" },
  { key: "weight_photo", title: "Вага і фото посилки в CRM у кожного відвантаження", how_measured: "auto", target: "100% відвантажень", target_pct: 100 },
  { key: "queue_clean", title: "Черга порожня в кінці дня: задачі «Відвантажити» не старші доби", how_measured: "auto", target: "щодня — не менше 95% робочих днів", target_pct: 95 },
  { key: "receipt_same_day", title: "Прихід — у день надходження: накладна оприбуткована, собівартість є", how_measured: "auto", target: "не менше 95% накладних того ж дня; собівартість — у кожному рядку", target_pct: 95 },
  { key: "stock_accuracy", title: "Точність залишків: розбіжність при перерахунку полиці ≤ 1%; раз на тиждень вибіркова перевірка", how_measured: "manual", target: "розбіжність ≤ 1%, перевірка щотижня" },
  { key: "order_timesheet", title: "Порядок і табель: без запізнень і прогулів, фото порядку на складі раз на тиждень", how_measured: "manual", target: "0 запізнень і прогулів, фото щотижня" },
];
const critOf = (c: Comp): Crit[] => (Array.isArray(c.params?.criteria) ? c.params.criteria : []).filter((x: any) => x && String(x.title || "").trim());
const isAutoCrit = (x: Crit) => x.how_measured === "auto" && WH_AUTO_KEYS.includes(x.key);
const clampPct = (v: number) => Math.max(0, Math.min(100, Math.round(Number.isFinite(v) ? v : 100)));
const EMPL: [string, string][] = [["labor", "Трудовий договір"], ["fop", "ФОП"], ["none", "Без оформлення"]];
const EMPL_HINT: Record<string, string> = {
  labor: "з нарахованої ЗП утримуються ПДФО і військовий збір, компанія платить ЄСВ зверху",
  fop: "людина — ФОП 3 гр.; компенсацію податків ФОП задано у «Правилах компанії»",
  none: "податків немає — компанії коштує рівно сума на руки",
};
const BASIS: [string, string][] = [["funnels", "з оплат обраних воронок"], ["object_acts", "від суми акту обʼєкта (при закритті)"],
  ["own_payments", "з усіх оплат своїх угод"], ["objects_income", "з приходів напрямку «Обʼєкти»"]];
const box: React.CSSProperties = { border: "1px solid #e2e8f0", borderRadius: 10, padding: "10px 12px", background: "#fff" };
const inp: React.CSSProperties = { height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px", fontSize: 13 };
const LABEL_W = 180;
const formGrid: React.CSSProperties = { display: "grid", gridTemplateColumns: `minmax(120px, ${LABEL_W}px) minmax(0, 1fr)`, gap: "7px 12px", alignItems: "center" };
const fieldLbl: React.CSSProperties = { fontSize: 12.5, color: "#475569" };
const fieldCtl: React.CSSProperties = { display: "flex", flexWrap: "wrap", alignItems: "center", gap: "6px 8px", minWidth: 0, fontSize: 12.5 };
const iconBtn: React.CSSProperties = { height: 22, width: 22, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", borderRadius: 999 };

const EVENT: Comp = { kind: "event_bonus", title: "Бонус «тест-набір → основне» 300 / 200 / 100 ₴", params: { tiers: { fast_days: 30, min_order: 3000, fast: 300, slow: 200, small: 100 } } };
const SALES: Comp[] = [
  { kind: "base_by_days", title: "За вихід (по табелю)", params: { amount: 6000 } },
  { kind: "standard", title: "Стандарт роботи (до 6 000 ₴)", params: { max: 6000 } },
  { kind: "margin_share", title: "10% з маржі онлайн до плану, 20% понад план", params: { funnels: [15, 16], pct_to_plan: 10, pct_over_plan: 20, gate_standard_min: 0.75 } },
  EVENT,
];
const TEMPLATES: Record<string, { label: string; comps: (start: string) => Comp[] }> = {
  sales: { label: "Продажник (нова схема)", comps: () => SALES },
  newbie: { label: "Новачок з гарантією 15 000 ₴ на 2 міс.", comps: (start) => [...SALES, { kind: "guarantee", title: "Гарантія новачку 15 000 ₴ × 2 міс.", params: { amount: 15000, months: 2, start } }] },
  warehouse: { label: "Комірник: ставка + відрядно", comps: () => [{ kind: "fixed_monthly", title: "Ставка", params: { amount: 8000 } }, { kind: "piece_rate", title: "Відрядно (ставки складу)", params: {} }] },
  warehouse_std: { label: "Комірник: за вихід + стандарт складу + відрядно", comps: () => [
    { kind: "base_by_days", title: "За вихід (по табелю)", params: { amount: 5000 } },
    { kind: "standard", title: "Стандарт складу (до 3 000 ₴, 8 пунктів)", params: { max: 3000, criteria: WH_STD_CRITERIA.map((x) => ({ ...x })) } },
    { kind: "piece_rate", title: "Відрядно (ставки складу)", params: {} }] },
  fixed: { label: "Фіксована оплата", comps: () => [{ kind: "fixed_monthly", title: "Оплата за місяць", params: { amount: 0 } }] },
};

/** Останній день гарантії — як engine.guarantee_window: старт + N місяців − 1 день. */
function gEnd(start: string | null | undefined, months: number): string | null {
  if (!start || start.length < 10) return null;
  const [y, m, d] = start.slice(0, 10).split("-").map(Number);
  const tm = m - 1 + (Number(months) || 0);
  const ty = y + Math.floor(tm / 12), mm = tm % 12;
  const last = new Date(Date.UTC(ty, mm + 1, 0)).getUTCDate();
  const dt = new Date(Date.UTC(ty, mm, Math.min(d, last)));
  dt.setUTCDate(dt.getUTCDate() - 1);
  return dt.toISOString().slice(0, 10);
}

function Num({ value, onChange, suffix, width = 90, disabled }: { value: any; onChange: (v: number) => void; suffix?: string; width?: number; disabled?: boolean }) {
  return <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
    <input type="number" value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))} style={{ ...inp, width, textAlign: "right" }} />
    {suffix && <span className="muted" style={{ fontSize: 12 }}>{suffix}</span>}
  </span>;
}

/** Рядок форми: підпис зліва (фіксована колонка), поле + одиниця + підказка справа. */
function Field({ label, hint, children }: { label: React.ReactNode; hint?: React.ReactNode; children?: React.ReactNode }) {
  return <>
    <div style={fieldLbl}>{label}</div>
    <div style={fieldCtl}>{children}{hint && <span className="muted" style={{ fontSize: 11.5 }}>{hint}</span>}</div>
  </>;
}

function InfoToggle({ open, onClick, title }: { open: boolean; onClick: () => void; title: string }) {
  return <button type="button" className="btn btn-light" title={title} aria-expanded={open} onClick={onClick}
    style={{ ...iconBtn, marginLeft: 5, color: open ? "#2E6FB0" : "#64748b", background: open ? "#e0edff" : undefined }}><Icon n="info" size={13} /></button>;
}

// службові воронки (найм, технічна, база клієнтів) — не для ставок; показуються лише якщо вже обрані
const SERVICE_FUNNEL = /найм|техническ|технічн|база клиент|база клієнт/i;
const chip: React.CSSProperties = { fontSize: 11.5, background: "#eef2ff", color: "#3730a3", borderRadius: 999, padding: "1px 8px", whiteSpace: "nowrap" };

function FunnelPick({ value, funnels, onChange, disabled }: { value: number[]; funnels: any[]; onChange: (v: number[]) => void; disabled?: boolean }) {
  const [edit, setEdit] = useState(false);
  const v = value || [];
  const picked = funnels.filter((f) => v.includes(f.id));
  const unknown = v.filter((id) => !funnels.some((f) => f.id === id));
  return <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 5, alignItems: "center" }}>
    {picked.map((f) => <span key={f.id} style={chip}>{f.name}</span>)}
    {unknown.map((id) => <span key={id} style={chip}>воронка #{id}</span>)}
    {v.length === 0 && <span className="muted" style={{ fontSize: 12 }}>не обрано</span>}
    {!disabled && <button type="button" className="btn btn-light" style={{ fontSize: 11.5, height: 22, padding: "0 7px" }} onClick={() => setEdit(!edit)}>{edit ? "готово" : "змінити"}</button>}
    {edit && <span style={{ flexBasis: "100%", display: "flex", flexWrap: "wrap", gap: 10, background: "#f8fafc", borderRadius: 8, padding: "6px 8px", marginTop: 3 }}>
      {funnels.filter((f) => !SERVICE_FUNNEL.test(f.name) || v.includes(f.id)).map((f) => <label key={f.id} style={{ fontSize: 12, display: "inline-flex", gap: 4, alignItems: "center" }}>
        <input type="checkbox" checked={v.includes(f.id)} onChange={() => onChange(v.includes(f.id) ? v.filter((x) => x !== f.id) : [...v, f.id])} />{f.name}
      </label>)}
    </span>}
  </span>;
}

/** Умови гарантії — нумерований список (зберігається як масив params.conditions). */
function CondList({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const set = (i: number, t: string) => onChange(value.map((x, j) => (j === i ? t : x)));
  return <div style={{ display: "grid", gap: 5, width: "100%" }}>
    <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 5 }}>
      {value.map((t, i) => <li key={i} style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
        <span style={{ width: 22, textAlign: "right", fontSize: 12.5, color: "#64748b", paddingTop: 6, flexShrink: 0 }}>{i + 1}.</span>
        <textarea value={t} rows={Math.max(1, Math.ceil(t.length / 75))} onChange={(e) => set(i, e.target.value)} placeholder="Умова…"
          style={{ flex: 1, minWidth: 0, boxSizing: "border-box", fontSize: 12.5, border: "1px solid #cbd5e1", borderRadius: 6, padding: "5px 8px", resize: "vertical", fontFamily: "inherit" }} />
        <button type="button" className="btn btn-light" title="Прибрати умову" style={{ height: 28, padding: "0 7px" }} onClick={() => onChange(value.filter((_, j) => j !== i))}><Icon n="x" size={13} /></button>
      </li>)}
    </ol>
    <div><button type="button" className="btn btn-light" style={{ fontSize: 12, height: 26 }} onClick={() => onChange([...value, ""])}><Icon n="plus" size={13} /> Додати умову</button></div>
  </div>;
}

/** Поля однієї частини оплати (режим «Змінити») — у сітці formGrid. */
function ParamsFields({ comp, funnels, conds, onChange }: { comp: Comp; funnels: any[]; conds: string[]; onChange: (p: any) => void }) {
  const p = comp.params || {};
  const set = (k: string, v: any) => onChange({ ...p, [k]: v });
  switch (comp.kind) {
    case "base_by_days":
      return <Field label="Сума «на руки»" hint="пропорційно відпрацьованим дням табеля"><Num value={p.amount} onChange={(v) => set("amount", v)} suffix="₴ / міс" /></Field>;
    case "fixed_monthly":
      return <Field label="Сума «на руки»" hint="щомісяця; у перший місяць — пропорційно робочим дням"><Num value={p.amount} onChange={(v) => set("amount", v)} suffix="₴ / міс" /></Field>;
    case "standard":
      return <>
        <Field label="Максимум" hint="× оцінка стандарту за місяць (ставиться справа, у «Розрахунку за місяць»)"><Num value={p.max} onChange={(v) => set("max", v)} suffix="₴ / міс" /></Field>
        <Field label={<>Пункти стандарту<div className="muted" style={{ fontSize: 11 }}>пояснення і підказка CRM; сума = максимум × оцінка</div></>}>
          <CritEdit value={Array.isArray(p.criteria) ? p.criteria : []} onChange={(v) => set("criteria", v)} />
        </Field>
      </>;
    case "margin_share":
      return <>
        <Field label="До плану"><Num value={p.pct_to_plan} onChange={(v) => set("pct_to_plan", v)} suffix="% з маржі" width={70} /></Field>
        <Field label="Понад план" hint="з частини оплат понад план"><Num value={p.pct_over_plan} onChange={(v) => set("pct_over_plan", v)} suffix="% з маржі" width={70} /></Field>
        <Field label="Понад план — якщо стандарт від" hint="інакше понад план теж за ставкою «до плану»"><Num value={Math.round((p.gate_standard_min ?? 0.75) * 100)} onChange={(v) => set("gate_standard_min", v / 100)} suffix="%" width={70} /></Field>
        <Field label="Воронки"><FunnelPick value={p.funnels || []} funnels={funnels} onChange={(v) => set("funnels", v)} /></Field>
      </>;
    case "revenue_share": {
      const basis = p.basis || "funnels";
      return <>
        <Field label="Відсоток"><Num value={p.pct} onChange={(v) => set("pct", v)} suffix="%" width={70} /></Field>
        <Field label="Від чого"><select value={basis} onChange={(e) => set("basis", e.target.value)} style={{ ...inp, maxWidth: 320 }}>{BASIS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        {basis === "funnels" && <Field label="Чиї угоди"><label style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><input type="checkbox" checked={p.own_only !== false} onChange={(e) => set("own_only", e.target.checked)} /> лише свої угоди</label></Field>}
        {basis === "funnels" && <Field label="Воронки"><FunnelPick value={p.funnels || []} funnels={funnels} onChange={(v) => set("funnels", v)} /></Field>}
      </>;
    }
    case "event_bonus": {
      const t = p.tiers || {};
      const st = (k: string, v: number) => set("tiers", { ...t, [k]: v });
      return <>
        <Field label="«Швидко» — це до" hint="від оплати тест-набору до оплати основного"><Num value={t.fast_days} onChange={(v) => st("fast_days", v)} suffix="днів" width={70} /></Field>
        <Field label="Бонус, якщо швидко"><Num value={t.fast} onChange={(v) => st("fast", v)} suffix="₴" width={80} /></Field>
        <Field label="Бонус, якщо пізніше"><Num value={t.slow} onChange={(v) => st("slow", v)} suffix="₴" width={80} /></Field>
        <Field label="Мале замовлення — менше"><Num value={t.min_order} onChange={(v) => st("min_order", v)} suffix="₴" width={80} /></Field>
        <Field label="Бонус за мале замовлення"><Num value={t.small} onChange={(v) => st("small", v)} suffix="₴" width={80} /></Field>
      </>;
    }
    case "guarantee": {
      const end = gEnd(p.start, p.months ?? 2);
      return <>
        <Field label="Гарантія «на руки»" hint="доплачуємо різницю до цієї суми"><Num value={p.amount} onChange={(v) => set("amount", v)} suffix="₴ / міс" /></Field>
        <Field label="Скільки місяців"><Num value={p.months} onChange={(v) => set("months", v)} suffix="міс" width={60} /></Field>
        <Field label="З дати" hint={end ? `діє до ${dm(end)} включно` : "вкажіть дату — без неї гарантія не діє"}><input type="date" value={p.start || ""} onChange={(e) => set("start", e.target.value)} style={inp} /></Field>
        <Field label={<>Умови<div className="muted" style={{ fontSize: 11 }}>платимо гарантію лише в місяці, коли власник відмітив «умови виконано»</div></>}>
          <CondList value={p.conditions || conds} onChange={(v) => set("conditions", v)} />
        </Field>
      </>;
    }
    case "piece_rate":
      return <Field label="Ставки">спільні ставки складу — таблиця «Ставки складу» нижче</Field>;
    default:
      return null;
  }
}

/** Позначка пункту стандарту: хто його перевіряє (15.09, whkpi). */
function CritBadge({ auto }: { auto: boolean }) {
  return <span style={{ fontSize: 10.5, fontWeight: 700, borderRadius: 999, padding: "1px 7px", whiteSpace: "nowrap", marginLeft: 5,
    background: auto ? "#dcfce7" : "#f1f5f9", color: auto ? "#166534" : "#475569" }}>{auto ? "вимірює CRM" : "відмічає керівник"}</span>;
}

/** Пункти стандарту в режимі читання — нумерований список. */
function CritView({ list }: { list: Crit[] }) {
  if (!list.length) return null;
  const auto = list.filter(isAutoCrit).length;
  return <div style={{ marginTop: 5 }}>
    <div className="muted" style={{ fontSize: 11.5 }}>{list.length} пунктів, кожен — 1/{list.length} оцінки: {auto} рахує CRM, {list.length - auto} відмічає керівник</div>
    <ol style={{ margin: "4px 0 0", paddingLeft: 20, fontSize: 12, color: "#334155", display: "grid", gap: 3 }}>
      {list.map((x, i) => <li key={x.key || i}>{x.title}{x.target ? <span className="muted"> — {x.target}</span> : null}<CritBadge auto={isAutoCrit(x)} /></li>)}
    </ol>
  </div>;
}

/** Пункти стандарту в режимі «Змінити»: назва і мета; пункти 1, 4, 5, 6 складу CRM рахує сама (їх ключі не змінюються). */
function CritEdit({ value, onChange }: { value: Crit[]; onChange: (v: Crit[]) => void }) {
  const set = (i: number, patch: Partial<Crit>) => onChange(value.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const nextKey = () => { let k = value.length + 1; while (value.some((x) => x.key === `c${k}`)) k++; return `c${k}`; };
  const ta: React.CSSProperties = { width: "100%", boxSizing: "border-box", fontSize: 12.5, border: "1px solid #cbd5e1", borderRadius: 6, padding: "5px 8px", resize: "vertical", fontFamily: "inherit" };
  return <div style={{ display: "grid", gap: 6, width: "100%" }}>
    {value.length === 0 && <div className="muted" style={{ fontSize: 12 }}>Пунктів немає — оцінка стандарту ставиться одним числом.</div>}
    <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 6 }}>
      {value.map((x, i) => <li key={x.key || i} style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
        <span style={{ width: 22, textAlign: "right", fontSize: 12.5, color: "#64748b", paddingTop: 6, flexShrink: 0 }}>{i + 1}.</span>
        <div style={{ flex: 1, minWidth: 0, display: "grid", gap: 4 }}>
          <textarea value={x.title || ""} rows={Math.max(1, Math.ceil((x.title || "").length / 75))} onChange={(e) => set(i, { title: e.target.value })} placeholder="Що саме має бути виконано…" style={ta} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <input value={x.target || ""} onChange={(e) => set(i, { target: e.target.value })} placeholder="Мета, напр. «не менше 95%»" style={{ ...inp, flex: 1, minWidth: 160 }} />
            {WH_AUTO_KEYS.includes(x.key)
              ? <label style={{ display: "inline-flex", gap: 5, alignItems: "center", fontSize: 12 }}><input type="checkbox" checked={x.how_measured === "auto"} onChange={(e) => set(i, { how_measured: e.target.checked ? "auto" : "manual" })} /> CRM рахує сама</label>
              : <span className="muted" style={{ fontSize: 11.5 }}>відмічає керівник</span>}
          </div>
        </div>
        <button type="button" className="btn btn-light" title="Прибрати пункт" style={{ height: 28, padding: "0 7px" }} onClick={() => onChange(value.filter((_, j) => j !== i))}><Icon n="x" size={13} /></button>
      </li>)}
    </ol>
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      <button type="button" className="btn btn-light" style={{ fontSize: 12, height: 26 }} onClick={() => onChange([...value, { key: nextKey(), title: "", how_measured: "manual", target: "" }])}><Icon n="plus" size={13} /> Додати пункт</button>
      {value.length === 0 && <button type="button" className="btn btn-light" style={{ fontSize: 12, height: 26 }} onClick={() => onChange(WH_STD_CRITERIA.map((x) => ({ ...x })))}><Icon n="package" size={13} /> Підставити 8 пунктів складу</button>}
    </div>
  </div>;
}

/** Оцінка стандарту з пунктами (склад): підказка CRM по пунктах, які вона вимірює, + галочки керівника по решті →
 * «підказана оцінка». Сума як і раніше = максимум × оцінка; керівник може вписати будь-який %. */
function StdCritMark({ comp, scheme, period, onSaved }: { comp: Comp; scheme: Scheme; period: string; onSaved: () => void }) {
  const crit = critOf(comp);
  const stored: Record<string, boolean> = (comp.params?.items || {})[period] || {};
  const saved = (comp.params?.scores || {})[period];
  const [sug, setSug] = useState<Sug | null | "none">(null);
  const [items, setItems] = useState<Record<string, boolean>>({});
  const [score, setScore] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const storedKey = JSON.stringify(stored);
  useEffect(() => {
    setItems(Object.fromEntries(crit.filter((x) => !isAutoCrit(x)).map((x) => [x.key, stored[x.key] !== false])));
    setScore(saved != null ? String(Math.round(saved * 100)) : "");
  }, [comp.id, period, saved, storedKey]);
  useEffect(() => {
    setSug(null); setMsg("");
    api.get<Sug>(`/api/payroll/wh-kpi/?scheme=${scheme.id}&period=${period}`).then(setSug).catch(() => setSug("none"));
  }, [scheme.id, period]);
  const s = sug && sug !== "none" ? sug : null;
  const pt = (key: string) => s?.points.find((p) => p.key === key);
  const okOf = (x: Crit) => (isAutoCrit(x) ? pt(x.key)?.pass !== false : items[x.key] !== false);
  const good = crit.filter(okOf).length;
  const calcPct = crit.length ? Math.round((good / crit.length) * 100) : 100;
  const autoNums = crit.map((x, i) => (isAutoCrit(x) ? String(i + 1) : "")).filter(Boolean).join(", ");
  async function save(pct: number) {
    setBusy(true); setMsg("");
    const full = Object.fromEntries(crit.map((x) => [x.key, okOf(x)]));
    try {
      await api.post("/api/payroll/wh-kpi/", { component: comp.id, period, score: pct / 100, items: full });
      setMsg(`Збережено: ${pct}%.`);
    } catch (e: any) {
      if (!(e?.status === 404 || String(e?.message || "").includes("404"))) { setMsg(e?.data?.detail || "Не вдалося зберегти"); setBusy(false); return; }
      try {
        await api.post(`/api/payroll/components/${comp.id}/mark/`, { period, score: pct / 100 });
        setMsg(`Збережено оцінку ${pct}%; позначки пунктів не збережено — на сервері ще немає /api/payroll/wh-kpi/.`);
      } catch (e2: any) { setMsg(e2?.data?.detail || "Не вдалося зберегти"); setBusy(false); return; }
    }
    setScore(String(pct)); setBusy(false); onSaved();
  }
  const verdict = (pass: boolean | null) => pass === null
    ? <span className="muted" style={{ fontSize: 11.5 }}>немає даних — не знижує</span>
    : <span style={{ display: "inline-flex", alignItems: "center", gap: 3, fontWeight: 700, color: pass ? "#166534" : "#b91c1c" }}><Icon n={pass ? "check" : "x"} size={13} />{pass ? "так" : "ні"}</span>;
  return <div style={{ flexBasis: "100%", display: "grid", gap: 6 }}>
    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <span>Стандарт за {period}:</span>
      <input value={score} placeholder={String(calcPct)} onChange={(e) => setScore(e.target.value)} style={{ ...inp, width: 55 }} />%
      <button className="btn btn-light" style={{ fontSize: 11.5 }} disabled={busy} onClick={() => save(clampPct(score.trim() === "" ? calcPct : Number(score.replace(",", "."))))}>Зберегти</button>
      <span className="muted" style={{ fontSize: 11.5 }}>{saved != null ? `збережено ${Math.round(saved * 100)}%` : "ще не виставлено — у розрахунку 100%"}</span>
    </div>
    {sug === null && <div className="muted" style={{ fontSize: 12 }}>Рахуємо підказку CRM…</div>}
    {sug === "none" && <div className="muted" style={{ fontSize: 12 }}>Підказка CRM зараз недоступна — оцінку можна вписати вручну.</div>}
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "7px 9px", display: "grid", gap: 5 }}>
      {s && <div style={{ fontWeight: 600 }}>Підказка CRM: пункти {autoNums} за місяць{s.to ? ` (${dm(s.from)} – ${dm(s.to)}${s.partial ? ", місяць ще йде" : ""})` : " — завершених днів ще немає"}
        <span className="muted" style={{ fontWeight: 400 }}> · робочих днів: {s.workdays} ({s.workdays_source})</span></div>}
      {crit.map((x, i) => {
        const p = pt(x.key);
        if (isAutoCrit(x)) return <div key={x.key || i} style={{ fontSize: 12 }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "baseline" }}>
            <span style={{ flex: 1, minWidth: 200 }}>{i + 1}. {x.title}{x.target ? <span className="muted"> — мета: {x.target}</span> : null}</span>
            {p ? <><b>{p.value_text}</b>{verdict(p.pass)}</> : <span className="muted">{sug === null ? "…" : "—"}</span>}
            {p && p.details.length > 0 && <button type="button" className="btn btn-light" style={{ fontSize: 11, height: 20, padding: "0 6px" }} onClick={() => setOpen({ ...open, [x.key]: !open[x.key] })}>{open[x.key] ? "сховати" : `деталі (${p.details.length})`}</button>}
          </div>
          {p && open[x.key] && <ul style={{ margin: "3px 0 0", paddingLeft: 22, color: "#475569", fontSize: 11.5, display: "grid", gap: 1 }}>{p.details.slice(0, 40).map((t, k) => <li key={k}>{t}</li>)}</ul>}
        </div>;
        return <label key={x.key || i} style={{ display: "flex", gap: 6, alignItems: "flex-start", fontSize: 12 }}>
          <input type="checkbox" checked={items[x.key] !== false} onChange={(e) => setItems({ ...items, [x.key]: e.target.checked })} style={{ marginTop: 2 }} />
          <span style={{ flex: 1, minWidth: 0 }}>{i + 1}. {x.title}{x.target ? <span className="muted"> — мета: {x.target}</span> : null}<CritBadge auto={false} />
            {p?.hint && <span className="muted" style={{ display: "block", fontSize: 11.5 }}>{p.hint}</span>}</span>
        </label>;
      })}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", borderTop: "1px solid #f1f5f9", paddingTop: 5 }}>
        <span>Виконано {good} з {crit.length} → підказана оцінка <b>{calcPct}%</b></span>
        <button type="button" className="btn btn-primary" style={{ fontSize: 12 }} disabled={busy} onClick={() => save(calcPct)}>Поставити підказану оцінку</button>
      </div>
      <div className="muted" style={{ fontSize: 11.5 }}>{s?.rule || "Кожен пункт — рівна частка оцінки. Пункти керівника — «так», поки галочку не знято."}</div>
    </div>
    {msg && <div style={{ fontSize: 12, color: "#166534" }}>{msg}</div>}
  </div>;
}

/** 15.09.2026 (Олег): у кожного — «рахувати за табелем: так / ні» (тверда ставка ↔ «За вихід (по табелю)»). */
function toggleByDays(c: Comp, on: boolean): Comp {
  const DAYS = "За вихід (по табелю)", FIX = "Ставка";
  const title = on ? (!c.title || c.title === FIX || c.title.startsWith("Ставка (") ? DAYS : c.title)
    : (!c.title || c.title === DAYS ? FIX : c.title);
  return { ...c, kind: on ? "base_by_days" : "fixed_monthly", title };
}

function byDaysInfo(comps: Comp[]): string {
  const f = comps.filter((c) => c.active !== false && (c.kind === "fixed_monthly" || c.kind === "base_by_days"));
  if (!f.length) return "";
  return f.some((c) => c.kind === "base_by_days") ? "так — ставка пропорційно відпрацьованим дням табеля" : "ні — ставка щомісяця повністю, табель не впливає";
}

/** Одна частина оплати в режимі «Змінити» — окремий рядок у рамці. */
function CompEditRow({ comp, kindLabel, funnels, conds, onChange, onRemove }: {
  comp: Comp; kindLabel: string; funnels: any[]; conds: string[]; onChange: (c: Comp) => void; onRemove: () => void;
}) {
  return <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "8px 10px", marginTop: 8, background: "#fcfdfe" }}>
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
      <span style={{ fontSize: 11.5, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: ".03em", flex: 1 }}>{kindLabel}</span>
      <button type="button" className="btn btn-light" title="Прибрати цю частину" style={{ fontSize: 12, padding: "0 7px", height: 26 }} onClick={onRemove}><Icon n="x" size={13} /></button>
    </div>
    <div style={formGrid}>
      <Field label="Назва частини"><input value={comp.title} onChange={(e) => onChange({ ...comp, title: e.target.value })} style={{ ...inp, width: "100%", maxWidth: 460, fontWeight: 600 }} /></Field>
      {(comp.kind === "fixed_monthly" || comp.kind === "base_by_days") && <Field label="Рахувати за табелем"
        hint={comp.kind === "base_by_days" ? "ставка пропорційно відпрацьованим дням; не вийшов — за день не нараховується" : "ставка щомісяця повністю, табель не впливає (напр. таргетолог, підрядник)"}>
        <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={comp.kind === "base_by_days"} onChange={(e) => onChange(toggleByDays(comp, e.target.checked))} /> {comp.kind === "base_by_days" ? "так" : "ні"}</label>
      </Field>}
      <ParamsFields comp={comp} funnels={funnels} conds={conds} onChange={(pp) => onChange({ ...comp, params: pp })} />
    </div>
  </div>;
}

function CalcPreview({ scheme, canEdit, onMarked }: { scheme: Scheme; canEdit: boolean; onMarked: () => void }) {
  const [period, setPeriod] = useState(month());
  const [r, setR] = useState<any>(null);
  const [score, setScore] = useState<Record<number, string>>({});
  const load = () => { setR(null); api.get<any>(`/api/payroll/calc/?scheme=${scheme.id}&period=${period}`).then(setR).catch(() => setR({ error: true })); };
  useEffect(load, [scheme.id, period]);
  const marks = scheme.components.filter((c) => c.id && (c.kind === "standard" || c.kind === "guarantee"));
  async function mark(c: Comp, body: any) { await api.post(`/api/payroll/components/${c.id}/mark/`, { period, ...body }); onMarked(); load(); }
  return <div style={box}>
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <b style={{ fontSize: 13.5 }}>Розрахунок за місяць</b>
      <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={inp} />
      {r && !r.error && <span style={{ marginLeft: "auto", fontSize: 13 }}>Разом <b>{money(r.total)}</b> · компанії коштує {money(r.company_cost)}</span>}
    </div>
    {canEdit && marks.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8, fontSize: 12.5, background: "#f8fafc", borderRadius: 8, padding: "6px 8px" }}>
      {marks.map((c) => {
        const cur = c.kind === "standard" ? (c.params?.scores || {})[period] : (c.params?.checks || {})[period];
        return c.kind === "standard" && critOf(c).length > 0
          ? <StdCritMark key={c.id} comp={c} scheme={scheme} period={period} onSaved={() => { onMarked(); load(); }} />
          : c.kind === "standard"
          ? <span key={c.id}>Стандарт за {period}: <input value={score[c.id!] ?? (cur != null ? Math.round(cur * 100) : "")} placeholder="100" onChange={(e) => setScore({ ...score, [c.id!]: e.target.value })} style={{ ...inp, width: 55 }} />%
            <button className="btn btn-light" style={{ fontSize: 11.5, marginLeft: 4 }} onClick={() => mark(c, { score: Number(score[c.id!] || 100) / 100 })}>Зберегти</button></span>
          : <label key={c.id} style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><input type="checkbox" checked={!!cur?.ok} onChange={(e) => mark(c, { ok: e.target.checked })} />
            Умови гарантії за {period} виконано{cur?.by ? <span className="muted"> ({cur.by})</span> : null}</label>;
      })}
    </div>}
    {!r ? <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>Рахуємо…</div> : r.error ? <div style={{ color: "#b91c1c", fontSize: 12.5 }}>Не вдалося порахувати</div> :
      <div style={{ marginTop: 6 }}>
        {r.lines.map((l: any, i: number) => <div key={i} style={{ display: "flex", gap: 8, fontSize: 12.5, padding: "4px 0", borderBottom: "1px dashed #eef2f7" }}>
          <span style={{ flex: 1, minWidth: 0 }}>{l.title}{l.rate ? <span className="muted"> · {l.rate}</span> : null}
            {l.detail && <div className="muted" style={{ fontSize: 11.5 }}>{l.detail}</div>}
            {l.warn && <div style={{ fontSize: 11.5, color: "#92400e" }}><Icon n="warn" size={12} /> {l.warn}</div>}</span>
          <b style={{ whiteSpace: "nowrap" }}>{money(l.amount)}</b></div>)}
        {r.preview && <div style={{ fontSize: 12, marginTop: 5, color: "#1d4ed8" }}>Приклад: так нарахувалось би за цією схемою в місяці, коли вона ще не діяла (на реальних оплатах і табелі того місяця).</div>}
        {r.legacy && <div className="muted" style={{ fontSize: 12, marginTop: 5 }}>За старою схемою («{r.legacy.title}») за цей місяць вийшло б {money(r.legacy.total)}.</div>}
      </div>}
  </div>;
}

const SECTIONS: { key: string; title: string; hint: string; kinds: string[]; icon: string }[] = [
  { key: "fixed", title: "Тверда частина", hint: "Щомісяця, незалежно від продажів. Саме вона порівнюється з фондом у «Плануванні».", kinds: ["base_by_days", "fixed_monthly", "standard", "guarantee"], icon: "wallet" },
  { key: "sales", title: "Від продажів", hint: "% з маржі або з обороту — платиться з грошей, які людина принесла.", kinds: ["margin_share", "revenue_share"], icon: "trending-up" },
  { key: "bonus", title: "Бонуси за подію", hint: "Разові виплати: тест-набір → основне замовлення.", kinds: ["event_bonus"], icon: "gift" },
  { key: "piece", title: "Склад — відрядно", hint: "За вагу, пакування, тонування, збірку тест-наборів — із записів складу.", kinds: ["piece_rate"], icon: "package" },
];
const sectionOf = (kind: string) => SECTIONS.find((x) => x.kinds.includes(kind))?.key || "fixed";

/** Одне речення «як рахується» + сума/ставка для таблиці читання. Звичайна функція (не компонент). */
function describe(c: Comp, funnels: any[], isVacancy: boolean, today: string): { how: string; amount: string } {
  const p = c.params || {};
  const fn = (ids: number[] | undefined) => (ids || []).map((id) => funnels.find((f) => f.id === id)?.name || `воронка #${id}`).join(", ") || "воронки не обрано";
  switch (c.kind) {
    case "base_by_days":
      return { how: `${money(p.amount)} на руки, пропорційно відпрацьованим дням табеля`, amount: money(p.amount) };
    case "fixed_monthly":
      return { how: `${money(p.amount)} на руки щомісяця (у перший місяць — пропорційно робочим дням)${Number(p.amount) > 0 ? "" : " — суму не задано"}`, amount: money(p.amount) };
    case "standard":
      if (critOf(c).length) return { how: `до ${money(p.max)} × оцінка стандарту за місяць: ${critOf(c).length} пунктів (нижче), кожен — 1/${critOf(c).length}; оцінку ставить керівник у «Розрахунку за місяць», CRM підказує`, amount: `до ${money(p.max)}` };
      return { how: `до ${money(p.max)} × оцінка стандарту за місяць (ставиться в «Розрахунку за місяць»)`, amount: `до ${money(p.max)}` };
    case "margin_share": {
      const to = pc(p.pct_to_plan ?? 10), over = pc(p.pct_over_plan ?? p.pct_to_plan ?? 10);
      return { how: `${to}% з маржі оплат своїх угод (${fn(p.funnels)}) до плану; ${over}% — з частини понад план, якщо стандарт від ${Math.round((p.gate_standard_min ?? 0.75) * 100)}%`, amount: `${to}% / ${over}%` };
    }
    case "revenue_share": {
      const basis = p.basis || "funnels";
      const how = basis === "object_acts" ? `${pc(p.pct)}% від усієї суми акту обʼєкта — у місяць, коли власник закрив акт`
        : basis === "own_payments" ? `${pc(p.pct)}% з усіх оплат по своїх угодах`
          : basis === "objects_income" ? `${pc(p.pct)}% з приходів напрямку «Обʼєкти» (без угод)`
            : `${pc(p.pct)}% з оплат ${p.own_only !== false ? "своїх угод" : "усіх угод"} у воронках: ${fn(p.funnels)}`;
      return { how, amount: `${pc(p.pct)}%` };
    }
    case "event_bonus": {
      const t = p.tiers || {};
      return { how: `за перше основне замовлення клієнта після оплаченого тест-набору: до ${t.fast_days ?? 30} днів — ${money(t.fast)}, пізніше — ${money(t.slow)}; замовлення менше ${money(t.min_order)} — ${money(t.small)}`,
        amount: `${num(t.fast)} / ${num(t.slow)} / ${num(t.small)} ₴` };
    }
    case "guarantee": {
      const end = gEnd(p.start, p.months ?? 2);
      const when = isVacancy ? `на перші ${p.months ?? 2} міс. після виходу (${p.start ? `з ${dm(p.start)}` : "дата виходу не задана"})`
        : !p.start ? "дату початку не вказано — гарантія не діє"
          : `з ${dm(p.start)} до ${dm(end)}${end && end < today ? " (вже закінчилась)" : p.start > today ? " (ще не почалась)" : ""}`;
      return { how: `не менше ${money(p.amount)}/міс ${when}; доплачуємо різницю лише в місяці, коли власник відмітив «умови виконано»`, amount: money(p.amount) };
    }
    case "piece_rate":
      return { how: "за вагу, упаковку, тонування і збірку тест-наборів — із записів складу за спільними ставками (таблиця «Ставки складу»)", amount: "за ставками складу" };
    default:
      return { how: c.kind_label || c.kind, amount: "" };
  }
}

function CondsView({ list }: { list: string[] }) {
  const [open, setOpen] = useState(false);
  if (!list.length) return null;
  return <div style={{ marginTop: 4 }}>
    <button type="button" className="btn btn-light" style={{ fontSize: 11.5, height: 22, padding: "0 8px" }} onClick={() => setOpen(!open)}>
      <Icon n="list" size={12} /> {open ? "сховати умови" : `умови гарантії (${list.length})`}</button>
    {open && <ol style={{ margin: "5px 0 0", paddingLeft: 20, fontSize: 12, color: "#334155", display: "grid", gap: 2 }}>{list.map((t, i) => <li key={i}>{t}</li>)}</ol>}
  </div>;
}

const th: React.CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: ".04em", padding: "6px 8px", borderBottom: "1px solid #e2e8f0", whiteSpace: "nowrap" };
const td: React.CSSProperties = { fontSize: 12.5, padding: "7px 8px", borderBottom: "1px solid #f1f5f9", verticalAlign: "top" };

/** Режим читання: таблиця по розділах «Частина оплати | Як рахується | Сума / ставка». */
function SummaryTable({ comps, kinds, funnels, conds, isVacancy }: { comps: Comp[]; kinds: any[]; funnels: any[]; conds: string[]; isVacancy: boolean }) {
  const today = new Date().toISOString().slice(0, 10);
  const secs = SECTIONS.map((sec) => ({ sec, items: comps.filter((c) => sectionOf(c.kind) === sec.key) })).filter((x) => x.items.length);
  if (!secs.length) return <div className="muted" style={{ fontSize: 12.5 }}>Частин оплати ще немає — натисніть «Змінити», щоб додати.</div>;
  return <div style={{ overflowX: "auto" }}>
    <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 520 }}>
      <thead><tr><th style={{ ...th, width: "30%" }}>Частина оплати</th><th style={th}>Як рахується</th><th style={{ ...th, textAlign: "right" }}>Сума / ставка</th></tr></thead>
      <tbody>
        {secs.map(({ sec, items }) => [
          <tr key={sec.key}><td colSpan={3} style={{ padding: "9px 8px 5px", background: "#f8fafc", borderBottom: "1px solid #eef2f7" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, fontWeight: 700, color: "#1e293b" }}><Icon n={sec.icon} size={14} style={{ color: "#2E6FB0" }} />{sec.title}</span>
            <span className="muted" style={{ fontSize: 11.5, marginLeft: 8 }}>{sec.hint}</span>
          </td></tr>,
          ...items.map((c, i) => {
            const d = describe(c, funnels, isVacancy, today);
            return <tr key={`${sec.key}-${c.id ?? i}`} style={{ opacity: c.active === false ? 0.55 : 1 }}>
              <td style={{ ...td, fontWeight: 600 }}>{c.active === false && <span className="muted" style={{ fontWeight: 400 }}>(вимкнено) </span>}{c.title || kinds.find((x) => x.kind === c.kind)?.label || c.kind}</td>
              <td style={td}>{d.how}{c.kind === "guarantee" && <CondsView list={(c.params?.conditions || conds) as string[]} />}{c.kind === "standard" && <CritView list={critOf(c)} />}</td>
              <td style={{ ...td, textAlign: "right", whiteSpace: "nowrap", fontWeight: 700 }}>{d.amount}</td>
            </tr>;
          }),
        ])}
      </tbody>
    </table>
  </div>;
}

const AUTO_COLOR: Record<string, string> = { yes: "#16a34a", mark: "#d97706", day: "#2563eb", no: "#94a3b8" };

/** Ставки складу: ТІ САМІ статті Фінмоделі (категорія «Ставки складу»), які читає склад. Копій немає. */
function WarehouseRates({ rates, canEdit, onChanged }: { rates: WhRate[]; canEdit: boolean; onChanged: () => void }) {
  const [edit, setEdit] = useState(false);
  const [vals, setVals] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const by = (code: string) => rates.find((r) => r.code === code);
  const kg = by("WH_RATE_KG"), p10 = by("WH_PACK_10"), tint = by("WH_TINT_PCT"), kit = by("bundle_assembly");
  function start() { setVals(Object.fromEntries(rates.map((r) => [r.id, String(r.value).replace(".", ",")]))); setMsg(""); setEdit(true); }
  async function save() {
    setBusy(true); setMsg("");
    const done: string[] = [], problems: string[] = [];
    let bundle = false;
    for (const r of rates) {
      const raw = (vals[r.id] ?? "").trim().replace(",", ".");
      const v = Number(raw);
      if (raw === "" || !isFinite(v) || v < 0 || (r.unit.startsWith("%") && v > 100)) { problems.push(`«${r.name}»: невірне число`); continue; }
      if (Math.abs(v - r.value) < 0.0001) continue;
      try {
        // не перезаписуємо новіше: якщо ставку вже змінили у Фінмоделі після відкриття сторінки — зупиняємось
        const cur = await api.get<any>(`/api/finmodel-articles/${r.id}/`).catch(() => null);
        if (cur && Math.abs(Number(cur.value) - r.value) >= 0.0001) { problems.push(`«${r.name}»: уже змінено у Фінмоделі (зараз ${pc(Number(cur.value))}) — перевірте і збережіть ще раз`); continue; }
        await api.patch(`/api/finmodel-articles/${r.id}/`, { value: String(v) });
        done.push(`${r.name}: ${pc(r.value)} → ${pc(v)}`);
        if (r.code === "bundle_assembly") bundle = true;
      } catch (e: any) { problems.push(`«${r.name}»: ${e?.data?.detail || "не вдалося зберегти"}`); }
    }
    setBusy(false);
    setMsg([done.length ? `Збережено: ${done.join("; ")}.` : problems.length ? "" : "Нічого не змінено.",
      bundle ? "Собівартість тестових наборів перераховано." : "", ...problems].filter(Boolean).join(" "));
    if (!problems.length) setEdit(false);
    if (done.length) onChanged();
  }
  return <div style={box}>
    <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
      <Icon n="package" size={15} style={{ color: "#2E6FB0" }} />
      <b style={{ fontSize: 13.5, flex: 1 }}>Ставки складу — спільні для всіх комірників</b>
      {canEdit && !edit && rates.length > 0 && <button type="button" className="btn btn-light" style={{ fontSize: 12, height: 28 }} onClick={start}><Icon n="pencil" size={13} /> Змінити ставки</button>}
    </div>
    {rates.length === 0 ? <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>Ставок складу у Фінмоделі не знайдено (Фінанси → Фінмодель → «Склад / ставки»).</div> :
      <div style={{ overflowX: "auto", marginTop: 6 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
          <thead><tr><th style={th}>За що</th><th style={{ ...th, textAlign: "right" }}>Ставка</th><th style={th}>Одиниця</th><th style={th}>Нараховується автоматично</th></tr></thead>
          <tbody>{rates.map((r) => <tr key={r.id}>
            <td style={{ ...td, fontWeight: 600 }}>{r.name}</td>
            <td style={{ ...td, textAlign: "right", whiteSpace: "nowrap" }}>{edit
              ? <input value={vals[r.id] ?? ""} inputMode="decimal" onChange={(e) => setVals({ ...vals, [r.id]: e.target.value })} style={{ ...inp, width: 80, textAlign: "right" }} />
              : <b>{pc(r.value)}</b>}</td>
            <td style={{ ...td, whiteSpace: "nowrap" }} className="muted">{r.unit}</td>
            <td style={td}><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 999, background: AUTO_COLOR[r.auto] || "#cbd5e1", marginRight: 6, verticalAlign: "1px" }} />{r.auto_note}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    {edit && <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
      <button type="button" className="btn btn-primary" disabled={busy} onClick={save}>{busy ? "…" : "Зберегти ставки"}</button>
      <button type="button" className="btn btn-light" disabled={busy} onClick={() => { setEdit(false); setMsg(""); }}>Скасувати</button>
    </div>}
    {msg && <div style={{ fontSize: 12.5, marginTop: 6 }}>{msg}</div>}
    <div style={{ fontSize: 12, marginTop: 8, display: "grid", gap: 3 }}>
      {kg && p10 && <div>Приклад: посилка 7 кг = 7 × {pc(kg.value)} + {pc(p10.value)} = <b>{dec(7 * kg.value + p10.value)} ₴</b> <span className="muted">(вага × ставка за кг + упаковка до 10 кг)</span></div>}
      {tint && <div>Приклад: «Послуга тонування» на 2 000 ₴ → {pc(tint.value)}% = <b>{dec(2000 * tint.value / 100)} ₴</b></div>}
      {kit && <div>Приклад: 3 тестові набори × {pc(kit.value)} ₴ = <b>{dec(3 * kit.value)} ₴</b></div>}
      <div className="muted">Ці ж ставки видно у Фінанси → Фінмодель («Інше / конфіг» → «Склад / ставки») — це одна й та сама ставка: змінили тут — змінилось і там, і для всіх комірників. Ставка за тестовий набір ще й входить у собівартість набору — після зміни собівартість наборів перераховується.</div>
      {!canEdit && <div className="muted">Змінювати ставки складу може лише той, хто має право редагувати Фінмодель.</div>}
    </div>
  </div>;
}

/** Справа: скільки коштує на місяць — з розшифровкою «звідки ця сума». */
function CostCard({ cost, k, marginPct, employmentLabel }: { cost: Cost; k: number | null; marginPct: number | null; employmentLabel: string }) {
  const [open, setOpen] = useState<Record<string, boolean>>({ fixed: true, tax: true, pay: true });
  const tg = (key: string) => setOpen({ ...open, [key]: !open[key] });
  const row: React.CSSProperties = { display: "flex", alignItems: "center", fontSize: 12.5, padding: "6px 0" };
  const expl: React.CSSProperties = { fontSize: 12, background: "#f8fafc", borderRadius: 8, padding: "7px 9px", margin: "0 0 4px", display: "grid", gap: 3 };
  const g = cost.guarantee_info;
  return <div style={box}>
    <b style={{ fontSize: 13.5 }}>Скільки коштує на місяць</b>
    <div style={row}><span style={{ flex: 1 }}>Тверда частина «на руки»<InfoToggle open={open.fixed} onClick={() => tg("fixed")} title="Чому саме ця сума" /></span><b>{money(cost.fixed_net)}</b></div>
    {open.fixed && (cost.fixed_explain ? <div style={expl}>
      {(cost.fixed_items || []).map((it, i) => <div key={i} style={{ display: "flex", gap: 8 }}><span style={{ flex: 1, minWidth: 0 }} className="muted">{it.title}{it.kind === "standard" ? " — максимум" : ""}</span><span>{money(it.amount)}</span></div>)}
      {g && <div style={{ display: "flex", gap: 8 }}><span style={{ flex: 1, minWidth: 0 }} className="muted">Гарантія новачку{g.end && g.status !== "vacancy" ? ` (до ${dm(g.end)})` : ""}{g.active ? "" : " — не діє"}</span><span>{money(g.amount)}</span></div>}
      <div style={{ color: "#1e293b", fontWeight: 600, marginTop: 2 }}>{cost.fixed_explain}</div>
      {(cost.fixed_notes || []).map((n, i) => <div key={i} className="muted" style={{ fontSize: 11.5 }}>{n}</div>)}
    </div> : <div className="muted" style={expl}>Сума частин «Тверда частина» зліва (стандарт — за максимумом); якщо діє гарантія новачку й вона більша — береться гарантія.</div>)}
    <div style={{ ...row, borderTop: "1px solid #f1f5f9" }}><span style={{ flex: 1 }}>Компанії з податками<InfoToggle open={open.tax} onClick={() => tg("tax")} title="Як пораховано податки" /></span><b>{money(cost.fixed_cost)}</b></div>
    {open.tax && <div style={expl}>
      {(cost.breakdown || []).length > 0 ? (cost.breakdown || []).map((s, i) => <div key={i} title={s.hint || undefined}
        style={{ display: "flex", gap: 8, paddingLeft: s.sub ? 14 : 0, fontWeight: s.total ? 700 : 400, borderTop: s.total ? "1px solid #e2e8f0" : undefined, paddingTop: s.total ? 3 : 0, color: s.sub ? "#64748b" : undefined }}>
        <span style={{ flex: 1, minWidth: 0 }}>{s.plus ? "+ " : s.total ? "= " : s.sub ? "− " : ""}{s.label}</span><span style={{ whiteSpace: "nowrap" }}>{num(s.amount)} ₴</span></div>)
        : <div className="muted">{cost.breakdown_text || `Множник податків ×${cost.taxes_ratio}`}</div>}
      <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>Оформлення: {employmentLabel}. Ставки податків — вкладка «Правила компанії». Суми округлено до гривні так, щоб кроки сходилися.</div>
    </div>}
    {k && <>
      <div style={{ ...row, borderTop: "1px solid #f1f5f9" }}><span style={{ flex: 1 }}>Щоб окупитися, треба нової виручки<InfoToggle open={open.pay} onClick={() => tg("pay")} title="Звідки ця сума" /></span><b style={{ whiteSpace: "nowrap" }}>{money(cost.fixed_cost * k)} / міс</b></div>
      {open.pay && <div style={expl}>
        <div>= {money(cost.fixed_cost)} × {pc(k)}</div>
        <div className="muted" style={{ fontSize: 11.5 }}>{pc(k)} — коефіцієнт точки беззбитковості: кожна гривня твердих витрат вимагає {pc(k)} ₴ виручки{marginPct ? ` (з гривні виручки на покриття твердих витрат лишається ≈${Math.round(marginPct)} коп.)` : ""}. Береться з Фінанси → Точка беззбитковості.</div>
      </div>}
    </>}
    <div className="muted" style={{ fontSize: 11.5, marginTop: 3 }}>% з продажів сюди не входить — він платиться з грошей, які людина принесла.</div>
  </div>;
}

/** Зберігаємо позначки місяця (оцінка стандарту / «умови виконано»), зроблені поки форма була відкрита — не затираємо новіше. */
function withFreshMarks(comps: Comp[], fresh: Comp[]): Comp[] {
  const byId = new Map(fresh.filter((c) => c.id).map((c) => [c.id, c]));
  return comps.map((c) => {
    const f = c.id ? byId.get(c.id) : undefined;
    let params = c.params || {};
    if (f) {
      params = { ...params };
      for (const key of ["scores", "checks", "items"]) if (f.params?.[key] !== undefined) params[key] = f.params[key];
    }
    if (c.kind === "guarantee" && Array.isArray(params.conditions)) params = { ...params, conditions: params.conditions.filter((x: string) => String(x || "").trim()) };
    if (c.kind === "standard" && Array.isArray(params.criteria)) params = { ...params, criteria: params.criteria.filter((x: any) => x && String(x.title || "").trim()) };
    return { ...c, params };
  });
}

function SchemeEditor({ scheme, funnels, users, kinds, conds, funds, fundByDept, canEdit, k, marginPct, whRates, canEditWh, onSaved, onWhChanged }: {
  scheme: Scheme; funnels: any[]; users: any[]; kinds: any[]; conds: string[]; funds: any[]; fundByDept: Record<string, number>; canEdit: boolean;
  k: number | null; marginPct: number | null; whRates: WhRate[]; canEditWh: boolean; onSaved: (id?: number) => void; onWhChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [s, setS] = useState<Scheme>(scheme);
  const [from, setFrom] = useState(scheme.valid_from.slice(0, 7));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [fillUser, setFillUser] = useState("");
  const justSaved = useRef(false);
  useEffect(() => {
    setS(scheme); setFrom(scheme.valid_from.slice(0, 7)); setFillUser(""); setEditing(false);
    if (justSaved.current) justSaved.current = false; else setMsg("");
  }, [scheme.id, scheme.valid_from, scheme.status]);
  const newVersion = !s.is_vacancy && from > scheme.valid_from.slice(0, 7);
  const setComp = (i: number, c: Comp) => setS({ ...s, components: s.components.map((x, j) => (j === i ? c : x)) });
  const addComp = (kind: string) => setS({ ...s, components: [...s.components, { kind, title: kinds.find((x) => x.kind === kind)?.label || "", params: kind === "guarantee" ? { amount: 15000, months: 2, start: s.planned_start || s.valid_from } : {} }] });
  function startEdit() { setS(scheme); setFrom(scheme.valid_from.slice(0, 7)); setFillUser(""); setMsg(""); setEditing(true); }
  function cancel() { setS(scheme); setFrom(scheme.valid_from.slice(0, 7)); setFillUser(""); setMsg(""); setEditing(false); }
  async function save() {
    setBusy(true); setMsg("");
    try {
      const body: any = { position: s.position, department: s.department, title: s.title, employment: s.employment, note: s.note,
        valid_from: from + "-01", components: withFreshMarks(s.components, scheme.components), options: s.options, in_plan: s.in_plan, planned_start: s.planned_start };
      if (fillUser) body.user_id = Number(fillUser);
      const r = await api.post<any>(`/api/payroll/schemes/${s.id}/save/`, body);
      setMsg(newVersion ? `Створено нову версію з ${dm(from + "-01")}. Минулі місяці не змінились.` : "Збережено.");
      setEditing(false);
      justSaved.current = true;
      onSaved(r.id);
    } catch (e: any) { setMsg(e?.data?.detail || "Не вдалося зберегти"); }
    setBusy(false);
  }
  async function archive() {
    if (!window.confirm("Прибрати цю схему в архів? Минулі розрахунки не зміняться.")) return;
    await api.post(`/api/payroll/schemes/${s.id}/archive/`, {}); onSaved();
  }
  const cost = scheme.cost;
  const cur = editing ? s : scheme;
  const fundId = Number(cur.options?.fund_article_id) || fundByDept[cur.department] || 59;
  const fundName = funds.find((f) => f.id === fundId)?.name || "";
  const showWh = cur.components.some((c) => c.kind === "piece_rate") || cur.department === "Склад";
  const status = scheme.purpose === "legacy" ? "як платили раніше (для порівняння)" : scheme.is_vacancy ? "вакансія — «що якщо»"
    : `діє з ${dm(scheme.valid_from)}${scheme.valid_to ? ` до ${dm(scheme.valid_to)}` : ""}`;
  // 15.09.2026: зліва — картка і таблиці (від 560 px), справа — «Скільки коштує» (~320 px); якщо тісно — права частина
  // переходить униз. Раніше дві рівні колонки: таблиці ширші за колонку вилазили під праву картку.
  return <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
    <div style={{ flex: "999 1 560px", display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 10, minWidth: 0 }}>
      <div style={box}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 9 }}>
          <b style={{ fontSize: 15 }}>{scheme.user_name || (scheme.is_vacancy ? scheme.position || "Вакансія" : scheme.position)}</b>
          <span className="muted" style={{ fontSize: 12, flex: 1 }}>{status}</span>
          {canEdit && !editing && <button type="button" className="btn btn-light" style={{ fontSize: 12.5, height: 30 }} onClick={startEdit}><Icon n="pencil" size={13} /> Змінити</button>}
          {editing && <span style={{ fontSize: 11.5, fontWeight: 700, color: "#1d4ed8", background: "#e0edff", borderRadius: 999, padding: "2px 9px" }}>редагування</span>}
        </div>
        {!editing ? <div style={formGrid}>
          <Field label="Посада">{scheme.position || "—"}</Field>
          <Field label="Відділ">{scheme.department || "—"}</Field>
          <Field label="Оформлення" hint={EMPL_HINT[scheme.employment]}><b>{scheme.employment_label}</b></Field>
          {byDaysInfo(scheme.components) && <Field label="За табелем">{byDaysInfo(scheme.components)}</Field>}
          {!scheme.is_vacancy && <Field label="Діє з">{dm(scheme.valid_from)}{scheme.valid_to ? ` до ${dm(scheme.valid_to)}` : " — діє зараз"}</Field>}
          {scheme.is_vacancy && <Field label="Плановий вихід">{dm(scheme.planned_start) || "—"}</Field>}
          {scheme.is_vacancy && <Field label="У «що якщо»">{scheme.in_plan ? "завжди враховувати в точці беззбитковості" : "лише коли ввімкнете у Фінанси → Точка беззбитковості"}</Field>}
          {scheme.purpose === "official" && fundName && <Field label="Фонд у «Плануванні»" hint="лише для порівняння «у фонді / за ставками»">{fundName}</Field>}
          {scheme.note && <Field label="Примітка"><span style={{ whiteSpace: "pre-wrap" }}>{scheme.note}</span></Field>}
        </div> : <div style={formGrid}>
          <Field label="Посада"><input value={s.position} onChange={(e) => setS({ ...s, position: e.target.value })} style={{ ...inp, width: "100%", maxWidth: 420 }} /></Field>
          <Field label="Відділ"><select value={s.department} onChange={(e) => setS({ ...s, department: e.target.value })} style={{ ...inp, minWidth: 180 }}>{["", ...DEPTS].map((d) => <option key={d} value={d}>{d || "—"}</option>)}</select></Field>
          <Field label="Оформлення" hint={EMPL_HINT[s.employment]}><select value={s.employment} onChange={(e) => setS({ ...s, employment: e.target.value })} style={{ ...inp, minWidth: 180 }}>{EMPL.map(([k2, l]) => <option key={k2} value={k2}>{l}</option>)}</select></Field>
          {!s.is_vacancy && <Field label="Діє з місяця" hint={newVersion ? undefined : "той самий місяць — правка цієї версії"}><input type="month" value={from} onChange={(e) => setFrom(e.target.value)} style={inp} /></Field>}
          {s.is_vacancy && <Field label="Плановий вихід"><input type="date" value={s.planned_start || ""} onChange={(e) => setS({ ...s, planned_start: e.target.value })} style={inp} /></Field>}
          {s.is_vacancy && <Field label="У «що якщо»"><label style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><input type="checkbox" checked={s.in_plan} onChange={(e) => setS({ ...s, in_plan: e.target.checked })} /> завжди враховувати</label></Field>}
          {s.is_vacancy && <Field label="Людина вийшла" hint="вакансія стане ставкою співробітника"><select value={fillUser} onChange={(e) => setFillUser(e.target.value)} style={{ ...inp, minWidth: 180 }}><option value="">—</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field>}
          {s.purpose === "official" && funds.length > 0 && <Field label="Фонд у «Плануванні»" hint="куди йде тверда частина при порівнянні «у фонді / за ставками»; сам фонд не змінюється">
            <select value={fundId} onChange={(e) => setS({ ...s, options: { ...(s.options || {}), fund_article_id: Number(e.target.value) } })} style={{ ...inp, minWidth: 220 }}>
              {funds.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select></Field>}
          <Field label="Примітка"><textarea value={s.note} onChange={(e) => setS({ ...s, note: e.target.value })} rows={2} style={{ width: "100%", boxSizing: "border-box", border: "1px solid #cbd5e1", borderRadius: 6, padding: 6, fontSize: 12.5, fontFamily: "inherit" }} /></Field>
        </div>}
        {editing && newVersion && <div style={{ fontSize: 12, color: "#1d4ed8", marginTop: 8 }}>Зберегти створить НОВУ версію з {dm(from + "-01")}; до цього місяця діятиме поточна — минулі місяці не перераховуються.</div>}
        {!editing && msg && <div style={{ fontSize: 12.5, marginTop: 8, color: "#166534" }}>{msg}</div>}
      </div>

      {!editing ? <div style={box}>
        <b style={{ fontSize: 13.5, display: "block", marginBottom: 6 }}>Як платимо</b>
        <SummaryTable comps={scheme.components} kinds={kinds} funnels={funnels} conds={conds} isVacancy={scheme.is_vacancy} />
      </div> : SECTIONS.map((sec) => {
        const items = s.components.map((c, i) => ({ c, i })).filter(({ c }) => sectionOf(c.kind) === sec.key);
        const secKinds = kinds.filter((x) => sec.kinds.includes(x.kind));
        if (!items.length && sec.key === "piece" && s.department !== "Склад") return null;
        return <div key={sec.key} style={box}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <Icon n={sec.icon} size={15} style={{ color: "#2E6FB0" }} />
            <b style={{ fontSize: 13.5, flex: 1 }}>{sec.title}</b>
            {items.length === 0 && <span className="muted" style={{ fontSize: 12 }}>немає</span>}
          </div>
          <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>{sec.hint}</div>
          {items.map(({ c, i }) => <CompEditRow key={c.id ?? `n${i}`} comp={c} kindLabel={kinds.find((x) => x.kind === c.kind)?.label || c.kind} funnels={funnels} conds={conds}
            onChange={(nc) => setComp(i, nc)} onRemove={() => setS({ ...s, components: s.components.filter((_, j) => j !== i) })} />)}
          {secKinds.length > 0 && <select value="" onChange={(e) => { if (e.target.value) addComp(e.target.value); }} style={{ ...inp, marginTop: 8, fontSize: 12 }}>
            <option value="">+ Додати в «{sec.title}»…</option>{secKinds.map((x) => <option key={x.kind} value={x.kind}>{x.label}</option>)}
          </select>}
        </div>;
      })}

      {showWh && <WarehouseRates rates={whRates} canEdit={canEditWh} onChanged={onWhChanged} />}

      {editing && <div style={{ ...box, position: "sticky", bottom: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", boxShadow: "0 -2px 10px rgba(15,23,42,.06)" }}>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={save}>{busy ? "…" : newVersion ? "Зберегти як нову версію" : "Зберегти"}</button>
        <button type="button" className="btn btn-light" disabled={busy} onClick={cancel}>Скасувати</button>
        <span style={{ flex: 1 }} />
        <button type="button" className="btn btn-light" disabled={busy} onClick={archive}><Icon n="trash" size={13} /> В архів</button>
        {msg && <span style={{ fontSize: 12.5, flexBasis: "100%" }}>{msg}</span>}
      </div>}
    </div>
    <div style={{ flex: "1 1 320px", position: "sticky", top: 8, alignSelf: "flex-start", display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 10, minWidth: 0 }}>
      {cost && scheme.purpose === "official" && <CostCard cost={cost} k={k} marginPct={marginPct} employmentLabel={scheme.employment_label} />}
      {editing && <div className="note" style={{ fontSize: 12 }}>Вартість справа — для збереженої версії; після «Зберегти» перерахується.</div>}
      <CalcPreview scheme={scheme} canEdit={canEdit} onMarked={() => onSaved(scheme.id)} />
    </div>
  </div>;
}

function NewScheme({ users, onCreated, onCancel }: { users: any[]; onCreated: (id: number) => void; onCancel: () => void }) {
  const [f, setF] = useState<any>({ kind: "person", user_id: "", position: "", department: "Продажі", employment: "labor", valid_from: month(), planned_start: "", tpl: "sales" });
  const [err, setErr] = useState("");
  async function create() {
    setErr("");
    const vac = f.kind === "vacancy";
    const start = vac ? (f.planned_start || f.valid_from + "-01") : f.valid_from + "-01";
    try {
      const r = await api.post<any>("/api/payroll/schemes/", {
        user_id: f.kind === "person" ? Number(f.user_id) || null : null, position: f.position || TEMPLATES[f.tpl].label,
        department: f.department, employment: f.employment, valid_from: start, is_vacancy: vac, in_plan: !vac,
        planned_start: vac ? start : null, components: TEMPLATES[f.tpl].comps(start),
      });
      onCreated(r.id);
    } catch (e: any) { setErr(e?.data?.detail || "Не вдалося створити"); }
  }
  return <div style={box}>
    <b style={{ fontSize: 14 }}>Нова ставка</b>
    <div style={{ display: "flex", gap: 14, flexWrap: "wrap", margin: "8px 0 10px", fontSize: 12.5 }}>
      {[["person", "Співробітник"], ["vacancy", "Вакансія (що якщо)"], ["position", "Посада без акаунта (бухгалтер…)"]].map(([k, l]) =>
        <label key={k} style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><input type="radio" checked={f.kind === k} onChange={() => setF({ ...f, kind: k })} /> {l}</label>)}
    </div>
    <div style={formGrid}>
      {f.kind === "person" && <Field label="Хто"><select value={f.user_id} onChange={(e) => setF({ ...f, user_id: e.target.value })} style={{ ...inp, minWidth: 220 }}><option value="">—</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field>}
      <Field label="Посада"><input value={f.position} onChange={(e) => setF({ ...f, position: e.target.value })} placeholder="Менеджер з продажу" style={{ ...inp, width: "100%", maxWidth: 420 }} /></Field>
      <Field label="Відділ"><select value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} style={{ ...inp, minWidth: 180 }}>{DEPTS.map((d) => <option key={d}>{d}</option>)}</select></Field>
      <Field label="Оформлення" hint={EMPL_HINT[f.employment]}><select value={f.employment} onChange={(e) => setF({ ...f, employment: e.target.value })} style={{ ...inp, minWidth: 180 }}>{EMPL.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
      {f.kind === "vacancy"
        ? <Field label="Плановий вихід"><input type="date" value={f.planned_start} onChange={(e) => setF({ ...f, planned_start: e.target.value })} style={inp} /></Field>
        : <Field label="Діє з місяця"><input type="month" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} style={inp} /></Field>}
      <Field label="Шаблон оплати" hint="усе можна змінити після створення"><select value={f.tpl} onChange={(e) => setF({ ...f, tpl: e.target.value })} style={{ ...inp, minWidth: 220 }}>{Object.entries(TEMPLATES).map(([k, t]) => <option key={k} value={k}>{t.label}</option>)}</select></Field>
    </div>
    {err && <div style={{ color: "#b91c1c", fontSize: 12.5, marginTop: 6 }}>{err}</div>}
    <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
      <button className="btn btn-primary" disabled={f.kind === "person" && !f.user_id} onClick={create}>Створити</button>
      <button className="btn btn-light" onClick={onCancel}>Скасувати</button>
    </div>
  </div>;
}

function PolicyTab({ canEdit }: { canEdit: boolean }) {
  const [d, setD] = useState<any>(null);
  const [p, setP] = useState<any>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => { api.get<any>("/api/payroll/policy/").then((r) => { setD(r); setP(r.params); }); }, []);
  if (!d || !p) return <div className="muted">Завантаження…</div>;
  const set = (path: string[], v: any) => { const n = JSON.parse(JSON.stringify(p)); let o = n; path.slice(0, -1).forEach((k) => { o[k] = o[k] || {}; o = o[k]; }); o[path[path.length - 1]] = v; setP(n); };
  async function save() { setMsg(""); try { const r = await api.post<any>("/api/payroll/policy/", { params: p }); setP(r.params); setMsg("Збережено"); } catch (e: any) { setMsg(e?.data?.detail || "Помилка"); } }
  const row: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", fontSize: 12.5, padding: "6px 0", borderBottom: "1px solid #f1f5f9" };
  const ro = !canEdit;
  return <div style={box}>
    <div style={row}><b style={{ width: 260 }}>Податки на ЗП (трудовий договір)</b>ПДФО <Num value={p.taxes.pdfo} onChange={(v) => set(["taxes", "pdfo"], v)} suffix="%" width={50} disabled={ro} /> військовий збір <Num value={p.taxes.vz} onChange={(v) => set(["taxes", "vz"], v)} suffix="%" width={50} disabled={ro} /> ЄСВ зверху <Num value={p.taxes.esv} onChange={(v) => set(["taxes", "esv"], v)} suffix="%" width={50} disabled={ro} /></div>
    <div style={row}><b style={{ width: 260 }}>ФОП 3 гр.</b>податок <Num value={p.taxes.fop_tax} onChange={(v) => set(["taxes", "fop_tax"], v)} suffix="%" width={50} disabled={ro} /> ЄСВ <Num value={p.taxes.fop_esv} onChange={(v) => set(["taxes", "fop_esv"], v)} suffix="₴/міс" width={70} disabled={ro} />
      <label><input type="checkbox" disabled={ro} checked={!!p.taxes.fop_compensate} onChange={(e) => set(["taxes", "fop_compensate"], e.target.checked)} /> компенсуємо податки ФОП</label></div>
    <div style={row}><b style={{ width: 260 }}>Гарантія новачку (за замовчуванням)</b><Num value={p.guarantee.amount} onChange={(v) => set(["guarantee", "amount"], v)} suffix="₴" disabled={ro} /> на <Num value={p.guarantee.months} onChange={(v) => set(["guarantee", "months"], v)} suffix="міс" width={50} disabled={ro} /></div>
    <div style={row}><b style={{ width: 260 }}>Зарплата продажників ≤ % маржі</b><Num value={p.cap.pct_of_margin} onChange={(v) => set(["cap", "pct_of_margin"], v)} suffix="%" width={50} disabled={ro} /><span className="muted">перевіряємо раз на квартал, ЗП за місяць не ріжемо</span></div>
    <div style={row}><b style={{ width: 260 }}>Коефіцієнт конверсії 0,8–1,2</b><label><input type="checkbox" disabled={ro} checked={!!p.conv_coef.enabled} onChange={(e) => set(["conv_coef", "enabled"], e.target.checked)} /> увімкнено</label>
      <span className="muted">вмикати, коли назбирається 2 місяці позначок якості звернень (з 11.09)</span></div>
    <div style={row}><b style={{ width: 260 }}>Середні частки продажів (для порівняння фондів)</b>за останні <Num value={p.lookback_days} onChange={(v) => set(["lookback_days"], v)} suffix="днів" width={55} disabled={ro} /></div>
    {canEdit && <div style={{ marginTop: 8 }}><button className="btn btn-primary" onClick={save}>Зберегти правила</button> <span style={{ fontSize: 12.5 }}>{msg}</span></div>}
  </div>;
}

function LogTab() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.get<any>("/api/payroll/log/").then(setD); }, []);
  if (!d) return <div className="muted">Завантаження…</div>;
  const A: Record<string, string> = { create: "створено", update: "змінено", new_version: "нова версія", archive: "в архів", mark: "позначка", policy: "правила компанії", seed: "перенесено" };
  return <div style={box}>{d.results.length === 0 ? <div className="muted">Змін ще немає</div> : d.results.map((l: any) =>
    <div key={l.id} style={{ fontSize: 12.5, padding: "5px 0", borderBottom: "1px solid #f1f5f9" }}>
      <b>{new Date(l.at).toLocaleString("uk-UA")}</b> · {l.user || "система"} · {A[l.action] || l.action} · {l.scheme}{l.note ? <span className="muted"> — {l.note}</span> : null}
    </div>)}</div>;
}

const ellipsis: React.CSSProperties = { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

/** Рядок списку зліва — завжди два рядки: імʼя / посада · оформлення · «тверда X ₴». */
function SchemeListItem({ s, selected, today, onClick }: { s: Scheme; selected: boolean; today: string; onClick: () => void }) {
  const name = s.user_name || s.position || "Без назви";
  const who = s.user_name ? s.position : s.is_vacancy ? (s.planned_start ? `вихід з ${dm(s.planned_start)}` : "вакансія") : "посада без акаунта";
  const line2 = [who, s.employment_label, s.cost ? `тверда ${money(s.cost.fixed_net)}` : s.purpose === "legacy" ? "як платили раніше" : ""].filter(Boolean).join(" · ");
  const badge = s.purpose === "legacy" ? "раніше" : s.valid_to && s.valid_to < today ? `до ${dm(s.valid_to)}` : !s.is_vacancy && s.valid_from > today ? `з ${dm(s.valid_from)}` : s.is_vacancy && s.in_plan ? "у плані" : "";
  return <div role="button" tabIndex={0} onClick={onClick} onKeyDown={(e) => { if (e.key === "Enter") onClick(); }}
    style={{ padding: "6px 9px", borderRadius: 8, cursor: "pointer", background: selected ? "#eff6ff" : "transparent", borderLeft: `3px solid ${selected ? "#2E6FB0" : "transparent"}`, marginBottom: 2, minHeight: 36 }}>
    <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
      <span style={{ ...ellipsis, fontSize: 13, fontWeight: 600, flex: 1, minWidth: 0 }}>{name}</span>
      {badge && <span style={{ fontSize: 10.5, color: "#475569", background: "#f1f5f9", borderRadius: 999, padding: "0 7px", whiteSpace: "nowrap" }}>{badge}</span>}
    </div>
    <div className="muted" style={{ ...ellipsis, fontSize: 11.5 }} title={line2}>{line2}</div>
  </div>;
}

const groupHead: React.CSSProperties = { display: "flex", alignItems: "baseline", gap: 6, fontSize: 10.5, fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: ".05em", margin: "8px 0 3px 2px" };

export default function PayRates() {
  const [tab, setTab] = useState("staff");
  const [d, setD] = useState<any>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [showOld, setShowOld] = useState(false);
  const [funnels, setFunnels] = useState<any[]>([]);
  const [k, setK] = useState<number | null>(null);
  const [bm, setBm] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const load = (pick?: number) => api.get<any>("/api/payroll/schemes/").then((r) => { setD(r); if (pick) setSel(pick); })
    .catch((e: any) => setErr(e?.status === 403 || String(e?.message || "").includes("403") ? "Немає доступу до ставок (право «Бачити ставки співробітників»)." : "Не вдалося завантажити ставки"));
  useEffect(() => {
    load();
    api.get<any>("/api/funnels/").then((r) => setFunnels((r.results || r || []).filter((f: any) => !f.is_lead_funnel && !f.is_archive).map((f: any) => ({ id: f.id, name: f.name })))).catch(() => {});
    api.get<any>("/api/payroll/breakeven/").then((r) => { setK(r.k_fixed || null); setBm(Number(r.margin_pct) || null); }).catch(() => {});
  }, []);
  const today = new Date().toISOString().slice(0, 10);
  const list: Scheme[] = useMemo(() => (d?.schemes || []).filter((s: Scheme) => showOld || (s.purpose === "official" && (!s.valid_to || s.valid_to >= today))), [d, showOld]);
  const groups = useMemo(() => {
    const g: Record<string, Scheme[]> = {};
    list.filter((s) => !s.is_vacancy).forEach((s) => { const key = s.department || "Інше"; (g[key] = g[key] || []).push(s); });
    const rank = (x: string) => (DEPTS.indexOf(x) < 0 ? 99 : DEPTS.indexOf(x));
    return Object.entries(g).sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
      .map(([name, items]) => [name, [...items].sort((x, y) => (x.user_name || x.position).localeCompare(y.user_name || y.position) || (y.valid_from > x.valid_from ? 1 : -1))] as [string, Scheme[]]);
  }, [list]);
  const vacancies = useMemo(() => list.filter((s) => s.is_vacancy).sort((a, b) => String(a.planned_start || "").localeCompare(String(b.planned_start || ""))), [list]);
  if (err) return <div className="panel">{err}</div>;
  if (!d) return <div className="spin">Завантаження ставок…</div>;
  const cur: Scheme | undefined = (d.schemes || []).find((s: Scheme) => s.id === sel);
  const pick = (id: number) => { setSel(id); setAdding(false); };
  const TABS: [string, string, string][] = [["staff", "Співробітники і вакансії", "users"], ["policy", "Правила компанії", "settings"], ["log", "Історія змін", "clock"]];
  return <div>
    <div className="note" style={{ marginBottom: 10 }}>
      <Icon n="info" size={14} /> <b>Ставки співробітників — одне місце для всіх зарплат.</b> Звідси рахуються ЗП (Фінанси → ЗП/KPI) і бонус у картці угоди.
      Точка беззбитковості — Фінанси → Точка беззбитковості (фонди «Планування»); акти обʼєктів — у картці клієнта.
      Змінили ставку з наступного місяця — створюється нова версія, минулі місяці не перераховуються. Суми — «на руки»; скільки людина коштує компанії з податками, CRM рахує сама (розшифровка — справа, значок <Icon n="info" size={12} />).
    </div>
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
      {TABS.map(([key, label, ic]) => <button key={key} className="btn" onClick={() => setTab(key)} style={{ fontSize: 13, background: tab === key ? "#e0edff" : undefined, fontWeight: tab === key ? 700 : 500 }}><Icon n={ic} size={14} /> {label}</button>)}
    </div>
    {tab === "policy" && <PolicyTab canEdit={d.can_edit} />}
    {tab === "log" && <LogTab />}
    {tab === "staff" && <div style={{ display: "grid", gridTemplateColumns: "minmax(240px, 300px) minmax(0, 1fr)", gap: 12, alignItems: "start" }}>
      <div style={{ ...box, padding: "10px 8px" }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4, padding: "0 4px" }}>
          <b style={{ fontSize: 13.5, flex: 1 }}>Хто і скільки</b>
          {d.can_edit && <button className="btn btn-primary" style={{ fontSize: 12, height: 28 }} onClick={() => { setAdding(true); setSel(null); }}><Icon n="plus" size={13} /> Додати</button>}
        </div>
        <label style={{ fontSize: 11.5, display: "flex", gap: 5, alignItems: "center", margin: "0 4px 4px" }}><input type="checkbox" checked={showOld} onChange={(e) => setShowOld(e.target.checked)} /> показати минулі версії і «як платили раніше»</label>
        {groups.map(([g, items]) => <div key={g}>
          <div style={groupHead}><span style={{ flex: 1 }}>{g}</span><span style={{ fontWeight: 600 }}>{items.length}</span></div>
          {items.map((s) => <SchemeListItem key={s.id} s={s} selected={sel === s.id} today={today} onClick={() => pick(s.id)} />)}
        </div>)}
        {groups.length === 0 && <div className="muted" style={{ fontSize: 12, padding: "6px 4px" }}>Ставок ще немає.</div>}
        <div style={{ marginTop: 10, paddingTop: 6, borderTop: "1px dashed #cbd5e1", background: "#f8fafc", borderRadius: 8 }}>
          <div style={{ ...groupHead, marginTop: 2 }}><span style={{ flex: 1 }}>Вакансії — «що якщо»</span><span style={{ fontWeight: 600 }}>{vacancies.length}</span></div>
          <div className="muted" style={{ fontSize: 11, margin: "0 4px 4px" }}>У ЗП не входять; лише в «що якщо» точки беззбитковості.</div>
          {vacancies.map((s) => <SchemeListItem key={s.id} s={s} selected={sel === s.id} today={today} onClick={() => pick(s.id)} />)}
          {vacancies.length === 0 && <div className="muted" style={{ fontSize: 12, padding: "2px 6px 6px" }}>Вакансій немає.</div>}
        </div>
      </div>
      <div style={{ minWidth: 0 }}>
        {adding && <NewScheme users={d.users} onCancel={() => setAdding(false)} onCreated={(id) => { setAdding(false); load(id); }} />}
        {!adding && cur && <SchemeEditor scheme={cur} funnels={funnels} users={d.users} kinds={d.kinds} conds={d.guarantee_conditions} funds={d.funds || []} fundByDept={d.fund_by_dept || {}}
          canEdit={d.can_edit} k={k} marginPct={bm} whRates={d.warehouse_rates || []} canEditWh={!!d.can_edit_wh_rates}
          onSaved={(id) => load(id || undefined)} onWhChanged={() => load(cur.id)} />}
        {!adding && !cur && <div className="muted" style={{ ...box, fontSize: 12.5 }}>Оберіть співробітника або вакансію зліва.</div>}
      </div>
    </div>}
  </div>;
}
