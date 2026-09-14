import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import BreakevenAtm from "./BreakevenAtm";

/* Налаштування → Ставки співробітників (14.09, рішення Олега «все з одного місця»).
 * Тут задаються оклади, % з маржі, % з обороту, гарантія новачку, відрядна оплата, акти обʼєктів.
 * Звідси беруть: ЗП (Фінанси → ЗП/KPI), точка беззбитковості за ATM, бонус у картці угоди.
 * Зміна з наступного місяця = нова версія; минулі місяці не перераховуються. */

type Comp = { id?: number; kind: string; kind_label?: string; title: string; params: any; active?: boolean };
type Scheme = {
  id: number; user_id: number | null; user_name: string; position: string; department: string; title: string;
  purpose: string; status: string; employment: string; employment_label: string; valid_from: string; valid_to: string | null;
  is_vacancy: boolean; in_plan: boolean; planned_start: string | null; options: any; note: string; components: Comp[]; cost?: any;
};

const money = (n: any) => Math.round(Number(n || 0)).toLocaleString("uk-UA") + " ₴";
const month = () => new Date().toISOString().slice(0, 7);
const dm = (s: string | null) => (s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "");
const DEPTS = ["Продажі", "Склад", "Маркетинг", "Офіс"];
const EMPL: [string, string][] = [["labor", "Трудовий договір"], ["fop", "ФОП"], ["none", "Без оформлення"]];
const BASIS: [string, string][] = [["funnels", "з оплат обраних воронок"], ["object_acts", "від суми акту обʼєкта (при закритті)"],
  ["own_payments", "з усіх оплат своїх угод"], ["objects_income", "з приходів напрямку «Обʼєкти»"]];
const box: React.CSSProperties = { border: "1px solid #e2e8f0", borderRadius: 10, padding: "10px 12px", background: "#fff" };
const inp: React.CSSProperties = { height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px", fontSize: 13 };

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
  fixed: { label: "Фіксована оплата", comps: () => [{ kind: "fixed_monthly", title: "Оплата за місяць", params: { amount: 0 } }] },
};

function Num({ value, onChange, suffix, width = 90, disabled }: { value: any; onChange: (v: number) => void; suffix?: string; width?: number; disabled?: boolean }) {
  return <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
    <input type="number" value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))} style={{ ...inp, width, textAlign: "right" }} />
    {suffix && <span className="muted" style={{ fontSize: 12 }}>{suffix}</span>}
  </span>;
}

function FunnelPick({ value, funnels, onChange, disabled }: { value: number[]; funnels: any[]; onChange: (v: number[]) => void; disabled?: boolean }) {
  return <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 8 }}>
    {funnels.map((f) => <label key={f.id} style={{ fontSize: 12, display: "inline-flex", gap: 4, alignItems: "center" }}>
      <input type="checkbox" disabled={disabled} checked={(value || []).includes(f.id)} onChange={() => onChange((value || []).includes(f.id) ? value.filter((x) => x !== f.id) : [...(value || []), f.id])} />{f.name}
    </label>)}
  </span>;
}

function ParamsEditor({ comp, funnels, conds, onChange, disabled }: { comp: Comp; funnels: any[]; conds: string[]; onChange: (p: any) => void; disabled?: boolean }) {
  const p = comp.params || {};
  const set = (k: string, v: any) => onChange({ ...p, [k]: v });
  const row: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", fontSize: 12.5, marginTop: 4 };
  switch (comp.kind) {
    case "base_by_days":
    case "fixed_monthly":
      return <div style={row}>Сума «на руки»: <Num value={p.amount} onChange={(v) => set("amount", v)} suffix="₴ / міс" disabled={disabled} />
        {comp.kind === "base_by_days" && <span className="muted">— пропорційно відпрацьованим дням (табель)</span>}</div>;
    case "standard":
      return <div style={row}>Максимум: <Num value={p.max} onChange={(v) => set("max", v)} suffix="₴" disabled={disabled} /><span className="muted">— × оцінка стандарту за місяць (ставиться в «Розрахунку»)</span></div>;
    case "margin_share":
      return <div>
        <div style={row}>До плану <Num value={p.pct_to_plan} onChange={(v) => set("pct_to_plan", v)} suffix="%" width={60} disabled={disabled} />
          понад план <Num value={p.pct_over_plan} onChange={(v) => set("pct_over_plan", v)} suffix="%" width={60} disabled={disabled} />
          понад план лише якщо стандарт від <Num value={Math.round((p.gate_standard_min ?? 0.75) * 100)} onChange={(v) => set("gate_standard_min", v / 100)} suffix="%" width={60} disabled={disabled} /></div>
        <div style={row}>Воронки: <FunnelPick value={p.funnels || []} funnels={funnels} onChange={(v) => set("funnels", v)} disabled={disabled} /></div>
      </div>;
    case "revenue_share":
      return <div>
        <div style={row}><Num value={p.pct} onChange={(v) => set("pct", v)} suffix="%" width={60} disabled={disabled} />
          <select value={p.basis || "funnels"} disabled={disabled} onChange={(e) => set("basis", e.target.value)} style={inp}>{BASIS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          {(p.basis || "funnels") === "funnels" && <label style={{ fontSize: 12 }}><input type="checkbox" disabled={disabled} checked={p.own_only !== false} onChange={(e) => set("own_only", e.target.checked)} /> лише свої угоди</label>}</div>
        {(p.basis || "funnels") === "funnels" && <div style={row}>Воронки: <FunnelPick value={p.funnels || []} funnels={funnels} onChange={(v) => set("funnels", v)} disabled={disabled} /></div>}
      </div>;
    case "event_bonus": {
      const t = p.tiers || {};
      const st = (k: string, v: number) => set("tiers", { ...t, [k]: v });
      return <div style={row}>До <Num value={t.fast_days} onChange={(v) => st("fast_days", v)} suffix="дн" width={55} disabled={disabled} /> —
        <Num value={t.fast} onChange={(v) => st("fast", v)} suffix="₴" width={65} disabled={disabled} />, пізніше <Num value={t.slow} onChange={(v) => st("slow", v)} suffix="₴" width={65} disabled={disabled} />,
        замовлення менше <Num value={t.min_order} onChange={(v) => st("min_order", v)} suffix="₴" width={75} disabled={disabled} /> — <Num value={t.small} onChange={(v) => st("small", v)} suffix="₴" width={65} disabled={disabled} /></div>;
    }
    case "guarantee":
      return <div>
        <div style={row}>Гарантія <Num value={p.amount} onChange={(v) => set("amount", v)} suffix="₴ / міс" disabled={disabled} /> на <Num value={p.months} onChange={(v) => set("months", v)} suffix="міс" width={50} disabled={disabled} />
          з <input type="date" value={p.start || ""} disabled={disabled} onChange={(e) => set("start", e.target.value)} style={inp} /></div>
        <div style={{ fontSize: 12, marginTop: 6 }}><b>Умови</b> (гарантія платиться лише коли ви щомісяця відмітили «умови виконано»):</div>
        <textarea value={(p.conditions || conds).join("\n")} disabled={disabled} onChange={(e) => set("conditions", e.target.value.split("\n").filter((x) => x.trim()))} rows={6}
          style={{ width: "100%", boxSizing: "border-box", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 6, padding: 6, marginTop: 3 }} />
      </div>;
    case "piece_rate":
      return <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Відрядні ставки складу: вага 1,5 ₴/кг, пакування 8 / 13 / 20 ₴, тонування 20%, робочий день 300 ₴ — рахуються з записів складу.</div>;
    default:
      return null;
  }
}

function CalcPreview({ scheme, canEdit, onMarked }: { scheme: Scheme; canEdit: boolean; onMarked: () => void }) {
  const [period, setPeriod] = useState(month());
  const [r, setR] = useState<any>(null);
  const [score, setScore] = useState<Record<number, string>>({});
  const load = () => { setR(null); api.get<any>(`/api/payroll/calc/?scheme=${scheme.id}&period=${period}`).then(setR).catch(() => setR({ error: true })); };
  useEffect(load, [scheme.id, period]);
  const marks = scheme.components.filter((c) => c.id && (c.kind === "standard" || c.kind === "guarantee"));
  async function mark(c: Comp, body: any) { await api.post(`/api/payroll/components/${c.id}/mark/`, { period, ...body }); onMarked(); load(); }
  return <div style={{ ...box, marginTop: 10 }}>
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <b style={{ fontSize: 13.5 }}>Розрахунок за місяць</b>
      <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={inp} />
      {r && !r.error && <span style={{ marginLeft: "auto", fontSize: 13 }}>Разом <b>{money(r.total)}</b> · компанії коштує {money(r.company_cost)}</span>}
    </div>
    {canEdit && marks.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8, fontSize: 12.5, background: "#f8fafc", borderRadius: 8, padding: "6px 8px" }}>
      {marks.map((c) => {
        const cur = c.kind === "standard" ? (c.params?.scores || {})[period] : (c.params?.checks || {})[period];
        return c.kind === "standard"
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
            {l.warn && <div style={{ fontSize: 11.5, color: "#92400e" }}>⚠ {l.warn}</div>}</span>
          <b style={{ whiteSpace: "nowrap" }}>{money(l.amount)}</b></div>)}
        {r.preview && <div style={{ fontSize: 12, marginTop: 5, color: "#1d4ed8" }}>Приклад: так нарахувалось би за цією схемою в місяці, коли вона ще не діяла (на реальних оплатах і табелі того місяця).</div>}
        {r.legacy && <div className="muted" style={{ fontSize: 12, marginTop: 5 }}>За старою схемою («{r.legacy.title}») за цей місяць вийшло б {money(r.legacy.total)}.</div>}
      </div>}
  </div>;
}

function SchemeEditor({ scheme, funnels, users, kinds, conds, canEdit, k, onSaved }: {
  scheme: Scheme; funnels: any[]; users: any[]; kinds: any[]; conds: string[]; canEdit: boolean; k: number | null; onSaved: (id?: number) => void;
}) {
  const [s, setS] = useState<Scheme>(scheme);
  const [from, setFrom] = useState(scheme.valid_from.slice(0, 7));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [fillUser, setFillUser] = useState("");
  useEffect(() => { setS(scheme); setFrom(scheme.valid_from.slice(0, 7)); setMsg(""); setFillUser(""); }, [scheme.id, scheme.valid_from, scheme.status]);
  const newVersion = !s.is_vacancy && from > scheme.valid_from.slice(0, 7);
  const setComp = (i: number, c: Comp) => setS({ ...s, components: s.components.map((x, j) => (j === i ? c : x)) });
  async function save() {
    setBusy(true); setMsg("");
    try {
      const body: any = { position: s.position, department: s.department, title: s.title, employment: s.employment, note: s.note,
        valid_from: from + "-01", components: s.components, options: s.options, in_plan: s.in_plan, planned_start: s.planned_start };
      if (fillUser) body.user_id = Number(fillUser);
      const r = await api.post<any>(`/api/payroll/schemes/${s.id}/save/`, body);
      setMsg(newVersion ? `Створено нову версію з ${dm(from + "-01")}. Минулі місяці не змінились.` : "Збережено.");
      onSaved(r.id);
    } catch (e: any) { setMsg(e?.data?.detail || "Не вдалося зберегти"); }
    setBusy(false);
  }
  async function archive() {
    if (!window.confirm("Прибрати цю схему в архів? Минулі розрахунки не зміняться.")) return;
    await api.post(`/api/payroll/schemes/${s.id}/archive/`, {}); onSaved();
  }
  const cost = scheme.cost;
  const ro = !canEdit;
  return <div>
    <div style={box}>
      <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        <b style={{ fontSize: 15 }}>{s.user_name || (s.is_vacancy ? "Вакансія" : s.position)}</b>
        <span className="muted" style={{ fontSize: 12 }}>{s.purpose === "legacy" ? "як платили раніше (для порівняння)" : s.is_vacancy ? "вакансія — «що якщо»" : `діє з ${dm(scheme.valid_from)}${scheme.valid_to ? ` до ${dm(scheme.valid_to)}` : ""}`}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8, marginTop: 8, fontSize: 12.5 }}>
        <label>Посада<br /><input value={s.position} disabled={ro} onChange={(e) => setS({ ...s, position: e.target.value })} style={{ ...inp, width: "100%" }} /></label>
        <label>Відділ<br /><select value={s.department} disabled={ro} onChange={(e) => setS({ ...s, department: e.target.value })} style={{ ...inp, width: "100%" }}>{["", ...DEPTS].map((d) => <option key={d} value={d}>{d || "—"}</option>)}</select></label>
        <label>Оформлення<br /><select value={s.employment} disabled={ro} onChange={(e) => setS({ ...s, employment: e.target.value })} style={{ ...inp, width: "100%" }}>{EMPL.map(([k2, l]) => <option key={k2} value={k2}>{l}</option>)}</select></label>
        {!s.is_vacancy && <label>Діє з місяця<br /><input type="month" value={from} disabled={ro} onChange={(e) => setFrom(e.target.value)} style={{ ...inp, width: "100%" }} /></label>}
        {s.is_vacancy && <label>Плановий вихід<br /><input type="date" value={s.planned_start || ""} disabled={ro} onChange={(e) => setS({ ...s, planned_start: e.target.value })} style={{ ...inp, width: "100%" }} /></label>}
      </div>
      {s.is_vacancy && <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 8, fontSize: 12.5 }}>
        <label><input type="checkbox" disabled={ro} checked={s.in_plan} onChange={(e) => setS({ ...s, in_plan: e.target.checked })} /> Враховувати в точці беззбитковості</label>
        {canEdit && <label>Людина вийшла: <select value={fillUser} onChange={(e) => setFillUser(e.target.value)} style={inp}><option value="">—</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>}
      </div>}
      {newVersion && <div style={{ fontSize: 12, color: "#1d4ed8", marginTop: 6 }}>Зберегти створить НОВУ версію з {dm(from + "-01")}; до цього місяця діятиме поточна — минулі місяці не перераховуються.</div>}
      {cost && s.purpose === "official" && <div style={{ display: "flex", flexWrap: "wrap", gap: 14, fontSize: 12.5, marginTop: 8, background: "#f8fafc", borderRadius: 8, padding: "6px 8px" }}>
        <span>Тверда частина «на руки»: <b>{money(cost.fixed_net)}</b></span>
        <span>Коштує компанії з податками: <b>{money(cost.fixed_cost)}</b>{cost.taxes_ratio > 1 ? <span className="muted"> (×{cost.taxes_ratio})</span> : null}</span>
        {k && <span>Точка беззбитковості: <b>+{money(cost.fixed_cost * k)}</b> виручки / міс</span>}
        {k && <span className="muted">Щоб окупитися, людина має принести ≈ {money(cost.fixed_cost * k)} нової виручки на місяць</span>}
      </div>}
    </div>
    <div style={{ ...box, marginTop: 10 }}>
      <b style={{ fontSize: 13.5 }}>З чого складається оплата</b>
      {s.components.map((c, i) => <div key={c.id ?? `n${i}`} style={{ borderTop: "1px solid #eef2f7", paddingTop: 7, marginTop: 7 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 11.5, whiteSpace: "nowrap" }}>{kinds.find((x) => x.kind === c.kind)?.label || c.kind}</span>
          <input value={c.title} disabled={ro} onChange={(e) => setComp(i, { ...c, title: e.target.value })} style={{ ...inp, flex: 1, minWidth: 120 }} />
          {canEdit && <button className="btn btn-light" style={{ fontSize: 12, padding: "0 8px" }} onClick={() => setS({ ...s, components: s.components.filter((_, j) => j !== i) })}>✕</button>}
        </div>
        <ParamsEditor comp={c} funnels={funnels} conds={conds} disabled={ro} onChange={(p) => setComp(i, { ...c, params: p })} />
      </div>)}
      {canEdit && <div style={{ marginTop: 8 }}>
        <select value="" onChange={(e) => { if (e.target.value) setS({ ...s, components: [...s.components, { kind: e.target.value, title: kinds.find((x) => x.kind === e.target.value)?.label || "", params: e.target.value === "guarantee" ? { amount: 15000, months: 2, start: s.planned_start || s.valid_from } : {} }] }); }} style={inp}>
          <option value="">+ Додати частину оплати…</option>{kinds.map((x) => <option key={x.kind} value={x.kind}>{x.label}</option>)}
        </select>
      </div>}
      <label style={{ display: "block", fontSize: 12.5, marginTop: 8 }}>Примітка<textarea value={s.note} disabled={ro} onChange={(e) => setS({ ...s, note: e.target.value })} rows={2} style={{ width: "100%", boxSizing: "border-box", border: "1px solid #cbd5e1", borderRadius: 6, padding: 6, fontSize: 12.5 }} /></label>
      {canEdit && <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
        <button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? "…" : newVersion ? "Зберегти як нову версію" : "Зберегти"}</button>
        <button className="btn btn-light" onClick={archive}>В архів</button>
        {msg && <span style={{ fontSize: 12.5 }}>{msg}</span>}
      </div>}
    </div>
    <CalcPreview scheme={scheme} canEdit={canEdit} onMarked={() => onSaved(scheme.id)} />
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
  const lab: React.CSSProperties = { fontSize: 12.5 };
  return <div style={box}>
    <b style={{ fontSize: 14 }}>Нова ставка</b>
    <div style={{ display: "flex", gap: 12, margin: "8px 0", fontSize: 12.5 }}>
      {[["person", "Співробітник"], ["vacancy", "Вакансія (що якщо)"], ["position", "Посада без акаунта (бухгалтер…)"]].map(([k, l]) =>
        <label key={k}><input type="radio" checked={f.kind === k} onChange={() => setF({ ...f, kind: k })} /> {l}</label>)}
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 8 }}>
      {f.kind === "person" && <label style={lab}>Хто<br /><select value={f.user_id} onChange={(e) => setF({ ...f, user_id: e.target.value })} style={{ ...inp, width: "100%" }}><option value="">—</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>}
      <label style={lab}>Посада<br /><input value={f.position} onChange={(e) => setF({ ...f, position: e.target.value })} placeholder="Менеджер з продажу" style={{ ...inp, width: "100%" }} /></label>
      <label style={lab}>Відділ<br /><select value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} style={{ ...inp, width: "100%" }}>{DEPTS.map((d) => <option key={d}>{d}</option>)}</select></label>
      <label style={lab}>Оформлення<br /><select value={f.employment} onChange={(e) => setF({ ...f, employment: e.target.value })} style={{ ...inp, width: "100%" }}>{EMPL.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      {f.kind === "vacancy"
        ? <label style={lab}>Плановий вихід<br /><input type="date" value={f.planned_start} onChange={(e) => setF({ ...f, planned_start: e.target.value })} style={{ ...inp, width: "100%" }} /></label>
        : <label style={lab}>Діє з місяця<br /><input type="month" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} style={{ ...inp, width: "100%" }} /></label>}
      <label style={lab}>Шаблон оплати<br /><select value={f.tpl} onChange={(e) => setF({ ...f, tpl: e.target.value })} style={{ ...inp, width: "100%" }}>{Object.entries(TEMPLATES).map(([k, t]) => <option key={k} value={k}>{t.label}</option>)}</select></label>
    </div>
    {err && <div style={{ color: "#b91c1c", fontSize: 12.5, marginTop: 6 }}>{err}</div>}
    <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
      <button className="btn btn-primary" disabled={f.kind === "person" && !f.user_id} onClick={create}>Створити</button>
      <button className="btn btn-light" onClick={onCancel}>Скасувати</button>
    </div>
  </div>;
}

function ActsTab({ users, canEdit }: { users: any[]; canEdit: boolean }) {
  const [d, setD] = useState<any>(null);
  const [f, setF] = useState<any>({ title: "", number: "", act_date: new Date().toISOString().slice(0, 10), amount_total: "", manager_id: "", contact_id: null, contact_name: "" });
  const [q, setQ] = useState("");
  const [found, setFound] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const load = () => api.get<any>("/api/payroll/acts/").then(setD).catch(() => setD({ results: [], error: true }));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (q.trim().length < 2) { setFound([]); return; }
    const tm = setTimeout(() => api.get<any>(`/api/contacts/?search=${encodeURIComponent(q.trim())}&page_size=8`).then((r) => setFound(r.results || r || [])).catch(() => setFound([])), 300);
    return () => clearTimeout(tm);
  }, [q]);
  async function add() {
    setErr("");
    try { await api.post("/api/payroll/acts/", { ...f, manager_id: Number(f.manager_id) || null }); setF({ ...f, title: "", number: "", amount_total: "", contact_id: null, contact_name: "" }); setQ(""); load(); }
    catch (e: any) { setErr(e?.data?.detail || "Не вдалося внести акт"); }
  }
  async function close(id: number) { if (window.confirm("Підтвердити і закрити акт? Менеджеру нарахується % у ЗП цього місяця.")) { await api.post(`/api/payroll/acts/${id}/close/`, {}); load(); } }
  const cname = (c: any) => c.name || [c.first_name, c.last_name].filter(Boolean).join(" ") || `#${c.id}`;
  return <div>
    <div className="note" style={{ marginBottom: 10 }}>Акт обʼєкта: менеджеру обʼєкта — <b>2% від усієї суми акту</b>, нараховується в місяць, коли ви натиснули «Закрити акт». Закривати акти можете лише ви.</div>
    {canEdit && <div style={{ ...box, marginBottom: 10 }}>
      <b style={{ fontSize: 13.5 }}>Внести акт</b>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 8, marginTop: 6, fontSize: 12.5 }}>
        <label>Обʼєкт / назва<br /><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Іваненко, 1-й поверх" style={{ ...inp, width: "100%" }} /></label>
        <label>№ акту<br /><input value={f.number} onChange={(e) => setF({ ...f, number: e.target.value })} style={{ ...inp, width: "100%" }} /></label>
        <label>Дата акту<br /><input type="date" value={f.act_date} onChange={(e) => setF({ ...f, act_date: e.target.value })} style={{ ...inp, width: "100%" }} /></label>
        <label>Сума акту, ₴<br /><input value={f.amount_total} onChange={(e) => setF({ ...f, amount_total: e.target.value })} inputMode="decimal" style={{ ...inp, width: "100%" }} /></label>
        <label>Менеджер обʼєкта<br /><select value={f.manager_id} onChange={(e) => setF({ ...f, manager_id: e.target.value })} style={{ ...inp, width: "100%" }}><option value="">—</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
        <label style={{ position: "relative" }}>Клієнт (необовʼязково)<br /><input value={f.contact_id ? f.contact_name : q} onChange={(e) => { setQ(e.target.value); setF({ ...f, contact_id: null, contact_name: "" }); }} placeholder="пошук за імʼям/телефоном" style={{ ...inp, width: "100%" }} />
          {found.length > 0 && !f.contact_id && <div style={{ position: "absolute", zIndex: 5, background: "#fff", border: "1px solid #cbd5e1", borderRadius: 6, width: "100%", maxHeight: 180, overflowY: "auto" }}>
            {found.map((c) => <div key={c.id} onClick={() => { setF({ ...f, contact_id: c.id, contact_name: cname(c) }); setFound([]); }} style={{ padding: "5px 8px", cursor: "pointer", fontSize: 12.5 }}>{cname(c)}</div>)}</div>}
        </label>
      </div>
      {err && <div style={{ color: "#b91c1c", fontSize: 12.5, marginTop: 6 }}>{err}</div>}
      <button className="btn btn-primary" style={{ marginTop: 8 }} disabled={!f.title || !f.amount_total} onClick={add}>Внести акт</button>
    </div>}
    {!d ? <div className="muted">Завантаження…</div> : d.results.length === 0 ? <div className="muted" style={{ fontSize: 12.5 }}>Актів ще немає.</div> :
      <div style={{ overflowX: "auto" }}><table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
        <thead><tr style={{ textAlign: "left", color: "#64748b" }}><th style={{ padding: 5 }}>Дата</th><th>Обʼєкт</th><th>Менеджер</th><th style={{ textAlign: "right" }}>Сума</th><th style={{ textAlign: "right" }}>%</th><th>Статус</th><th /></tr></thead>
        <tbody>{d.results.map((a: any) => <tr key={a.id} style={{ borderTop: "1px solid #f1f5f9" }}>
          <td style={{ padding: 5 }}>{dm(a.act_date)}</td><td>{a.title}{a.number ? ` · №${a.number}` : ""}{a.contact_name ? <div className="muted" style={{ fontSize: 11 }}>{a.contact_name}</div> : null}</td>
          <td>{a.manager_name || "—"}</td><td style={{ textAlign: "right" }}>{money(a.amount_total)}</td>
          <td style={{ textAlign: "right" }}>{a.commission_amount != null ? `${money(a.commission_amount)} (${a.commission_pct}%)` : "—"}</td>
          <td>{a.status_label}{a.closed_by ? <div className="muted" style={{ fontSize: 11 }}>{a.closed_by}, ЗП {a.payroll_period}</div> : null}</td>
          <td>{a.status !== "closed" && d.can_close && <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => close(a.id)}>Закрити акт</button>}</td>
        </tr>)}</tbody></table></div>}
  </div>;
}

function PolicyTab({ canEdit }: { canEdit: boolean }) {
  const [d, setD] = useState<any>(null);
  const [p, setP] = useState<any>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => { api.get<any>("/api/payroll/policy/").then((r) => { setD(r); setP(r.params); }); }, []);
  if (!d || !p) return <div className="muted">Завантаження…</div>;
  const set = (path: string[], v: any) => { const n = JSON.parse(JSON.stringify(p)); let o = n; path.slice(0, -1).forEach((k) => { o[k] = o[k] || {}; o = o[k]; }); o[path[path.length - 1]] = v; setP(n); };
  const rep: number[] = p.replaced_articles || [];
  async function save() { setMsg(""); try { const r = await api.post<any>("/api/payroll/policy/", { params: p }); setP(r.params); setMsg("Збережено"); } catch (e: any) { setMsg(e?.data?.detail || "Помилка"); } }
  const row: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", fontSize: 12.5, padding: "6px 0", borderBottom: "1px solid #f1f5f9" };
  const ro = !canEdit;
  return <div style={box}>
    <div style={row}><b style={{ width: 260 }}>Дивіденди власника</b><Num value={p.dividends_pct} onChange={(v) => set(["dividends_pct"], v)} suffix="% маржі" width={60} disabled={ro} />
      <span className="muted">За ATM — першими з маржі. Це гроші власника, не «дивіденди майстрам» (оплата майстрам — фонд виручки).</span></div>
    <div style={row}><b style={{ width: 260 }}>Податки на ЗП (трудовий договір)</b>ПДФО <Num value={p.taxes.pdfo} onChange={(v) => set(["taxes", "pdfo"], v)} suffix="%" width={50} disabled={ro} /> військовий збір <Num value={p.taxes.vz} onChange={(v) => set(["taxes", "vz"], v)} suffix="%" width={50} disabled={ro} /> ЄСВ зверху <Num value={p.taxes.esv} onChange={(v) => set(["taxes", "esv"], v)} suffix="%" width={50} disabled={ro} /></div>
    <div style={row}><b style={{ width: 260 }}>ФОП 3 гр.</b>податок <Num value={p.taxes.fop_tax} onChange={(v) => set(["taxes", "fop_tax"], v)} suffix="%" width={50} disabled={ro} /> ЄСВ <Num value={p.taxes.fop_esv} onChange={(v) => set(["taxes", "fop_esv"], v)} suffix="₴/міс" width={70} disabled={ro} />
      <label><input type="checkbox" disabled={ro} checked={!!p.taxes.fop_compensate} onChange={(e) => set(["taxes", "fop_compensate"], e.target.checked)} /> компенсуємо податки ФОП</label></div>
    <div style={row}><b style={{ width: 260 }}>Гарантія новачку (за замовчуванням)</b><Num value={p.guarantee.amount} onChange={(v) => set(["guarantee", "amount"], v)} suffix="₴" disabled={ro} /> на <Num value={p.guarantee.months} onChange={(v) => set(["guarantee", "months"], v)} suffix="міс" width={50} disabled={ro} /></div>
    <div style={row}><b style={{ width: 260 }}>Зарплата продажників ≤ % маржі</b><Num value={p.cap.pct_of_margin} onChange={(v) => set(["cap", "pct_of_margin"], v)} suffix="%" width={50} disabled={ro} /><span className="muted">перевіряємо раз на квартал, ЗП за місяць не ріжемо</span></div>
    <div style={row}><b style={{ width: 260 }}>Коефіцієнт конверсії 0,8–1,2</b><label><input type="checkbox" disabled={ro} checked={!!p.conv_coef.enabled} onChange={(e) => set(["conv_coef", "enabled"], e.target.checked)} /> увімкнено</label>
      <span className="muted">вмикати, коли назбирається 2 місяці позначок якості звернень (з 11.09)</span></div>
    <div style={row}><b style={{ width: 260 }}>Частки для точки беззбитковості</b>за останні <Num value={p.lookback_days} onChange={(v) => set(["lookback_days"], v)} suffix="днів" width={55} disabled={ro} /></div>
    <div style={{ ...row, alignItems: "flex-start" }}><b style={{ width: 260 }}>Статті фінмоделі, замінені ставками</b>
      <span style={{ flex: 1 }}>{d.articles.map((a: any) => <label key={a.id} style={{ display: "block" }}><input type="checkbox" disabled={ro} checked={rep.includes(a.id)} onChange={() => set(["replaced_articles"], rep.includes(a.id) ? rep.filter((x) => x !== a.id) : [...rep, a.id])} /> {a.name} <span className="muted">({a.category}, {a.value})</span></label>)}
        <div className="muted" style={{ fontSize: 11.5 }}>Відмічені статті не рахуються в точці беззбитковості — замість них ставки співробітників, щоб зарплата не рахувалась двічі.</div></span></div>
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

export default function PayRates() {
  const [tab, setTab] = useState("staff");
  const [d, setD] = useState<any>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [showOld, setShowOld] = useState(false);
  const [funnels, setFunnels] = useState<any[]>([]);
  const [k, setK] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const load = (pick?: number) => api.get<any>("/api/payroll/schemes/").then((r) => { setD(r); if (pick) setSel(pick); })
    .catch((e: any) => setErr(e?.status === 403 || String(e?.message || "").includes("403") ? "Немає доступу до ставок (право «Бачити ставки співробітників»)." : "Не вдалося завантажити ставки"));
  useEffect(() => {
    load();
    api.get<any>("/api/funnels/").then((r) => setFunnels((r.results || r || []).filter((f: any) => !f.is_lead_funnel && !f.is_archive).map((f: any) => ({ id: f.id, name: f.name })))).catch(() => {});
    api.get<any>("/api/payroll/breakeven/").then((r) => setK(r.k_fixed || null)).catch(() => {});
  }, []);
  const today = new Date().toISOString().slice(0, 10);
  const list: Scheme[] = useMemo(() => (d?.schemes || []).filter((s: Scheme) => showOld || (s.purpose === "official" && (!s.valid_to || s.valid_to >= today))), [d, showOld]);
  const groups = useMemo(() => {
    const g: Record<string, Scheme[]> = {};
    list.forEach((s) => { const key = s.is_vacancy ? "Вакансії" : (s.department || "Інше"); (g[key] = g[key] || []).push(s); });
    return Object.entries(g).sort(([a], [b]) => (a === "Вакансії" ? 1 : b === "Вакансії" ? -1 : a.localeCompare(b)));
  }, [list]);
  if (err) return <div className="panel">{err}</div>;
  if (!d) return <div className="spin">Завантаження ставок…</div>;
  const cur: Scheme | undefined = (d.schemes || []).find((s: Scheme) => s.id === sel);
  const TABS: [string, string][] = [["staff", "👥 Співробітники і вакансії"], ["be", "🎯 Точка беззбитковості"], ["acts", "🏗 Акти обʼєктів"], ["policy", "⚙️ Правила компанії"], ["log", "🕑 Історія змін"]];
  return <div>
    <div className="note" style={{ marginBottom: 10 }}>
      💼 <b>Ставки співробітників — одне місце для всіх зарплат.</b> Звідси рахуються ЗП (Фінанси → ЗП/KPI), точка беззбитковості і бонус у картці угоди.
      Змінили ставку з наступного місяця — створюється нова версія, минулі місяці не перераховуються. Суми — «на руки»; скільки людина коштує компанії з податками, CRM рахує сама.
    </div>
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
      {TABS.map(([key, label]) => <button key={key} className="btn" onClick={() => setTab(key)} style={{ fontSize: 13, background: tab === key ? "#e0edff" : undefined, fontWeight: tab === key ? 700 : 500 }}>{label}</button>)}
    </div>
    {tab === "be" && <BreakevenAtm />}
    {tab === "acts" && <ActsTab users={d.users} canEdit={d.can_edit} />}
    {tab === "policy" && <PolicyTab canEdit={d.can_edit} />}
    {tab === "log" && <LogTab />}
    {tab === "staff" && <div style={{ display: "grid", gridTemplateColumns: "minmax(240px, 320px) minmax(0, 1fr)", gap: 12, alignItems: "start" }}>
      <div style={box}>
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
          <b style={{ fontSize: 13.5, flex: 1 }}>Хто і скільки</b>
          {d.can_edit && <button className="btn btn-primary" style={{ fontSize: 12, height: 28 }} onClick={() => { setAdding(true); setSel(null); }}>+ Додати</button>}
        </div>
        <label style={{ fontSize: 11.5, display: "block", marginBottom: 6 }}><input type="checkbox" checked={showOld} onChange={(e) => setShowOld(e.target.checked)} /> показати минулі версії і «як платили раніше»</label>
        {groups.map(([g, items]) => <div key={g} style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 10.5, fontWeight: 800, color: "#64748b", textTransform: "uppercase", letterSpacing: ".05em", margin: "6px 0 3px" }}>{g}</div>
          {items.map((s) => <div key={s.id} onClick={() => { setSel(s.id); setAdding(false); }}
            style={{ padding: "6px 8px", borderRadius: 8, cursor: "pointer", background: sel === s.id ? "#eff6ff" : "transparent", border: s.is_vacancy ? "1px dashed #94a3b8" : "1px solid transparent", marginBottom: 3 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{s.user_name || s.position}{s.purpose === "legacy" && <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}> · раніше</span>}</div>
            <div className="muted" style={{ fontSize: 11.5 }}>{s.user_name ? s.position + " · " : ""}{s.employment_label}{s.cost ? ` · ${money(s.cost.fixed_net)} тверда` : ""}{s.is_vacancy ? (s.in_plan ? " · у точці беззбитковості" : " · не враховано") : ""}</div>
          </div>)}
        </div>)}
      </div>
      <div>
        {adding && <NewScheme users={d.users} onCancel={() => setAdding(false)} onCreated={(id) => { setAdding(false); load(id); }} />}
        {!adding && cur && <SchemeEditor scheme={cur} funnels={funnels} users={d.users} kinds={d.kinds} conds={d.guarantee_conditions} canEdit={d.can_edit} k={k} onSaved={(id) => load(id || undefined)} />}
        {!adding && !cur && <div className="muted" style={{ ...box, fontSize: 12.5 }}>Оберіть співробітника або вакансію зліва.</div>}
      </div>
    </div>}
  </div>;
}
