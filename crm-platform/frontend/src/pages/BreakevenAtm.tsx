import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../Icon";

/* Розшифровка точки беззбитковості (виправлено 14.09 за словами Олега «фонди були розставлені правильно»).
 * Цифра ТБ — ОДНА на всю CRM: її рахують Фінанси з фондів «Планування» (compute_breakeven). Тут лише:
 *  1) з чого вона складається — групи фондів рівно як у «Плануванні»;
 *  2) зарплати: скільки у фонді і скільки виходить за ставками — «Підставити» лише кнопкою власника;
 *  3) вакансії «що якщо» — кілька, з додаванням прямо тут. Фонди самі не змінюються. */

const money = (n: any) => (n == null ? "—" : Math.round(Number(n)).toLocaleString("uk-UA") + " ₴");
const pct = (n: any) => (n == null ? "—" : `${Number(n).toLocaleString("uk-UA", { maximumFractionDigits: 2 })}%`);
const GROUPS: { key: string; color: string; hint: string; unit: "%" | "₴" }[] = [
  { key: "revenue", color: "#2563eb", hint: "% з кожної гривні виручки — зменшують маржинальність", unit: "%" },
  { key: "margin", color: "#7c3aed", hint: "₴ на місяць: оренда, ФОТ, реклама, сервіси, кредити, резерв", unit: "₴" },
  { key: "skd", color: "#059669", hint: "₴ на місяць: розвиток, навчання, офіс", unit: "₴" },
  { key: "upr", color: "#475569", hint: "₴ на місяць: обовʼязкові управлінські", unit: "₴" },
  { key: "other", color: "#64748b", hint: "за кожну угоду × угоди місяця", unit: "₴" },
];
const inp: React.CSSProperties = { height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px", fontSize: 13, boxSizing: "border-box" };
const EMPL: [string, string][] = [["labor", "Трудовий договір"], ["fop", "ФОП"], ["none", "Без оформлення"]];

function Group({ g, label, rows }: { g: typeof GROUPS[number]; label: string; rows: any[] }) {
  const [all, setAll] = useState(false);
  const total = rows.reduce((s, r) => s + Number(r.value || 0), 0);
  const zero = rows.filter((r) => !Number(r.value)).length;
  const shown = all ? rows : rows.filter((r) => Number(r.value));
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
        <span style={{ width: 9, height: 9, borderRadius: 3, background: g.color, flexShrink: 0 }} />
        <b style={{ fontSize: 13.5, flex: 1 }}>{label}</b>
        <b style={{ fontVariantNumeric: "tabular-nums" }}>{g.unit === "%" ? pct(total) : money(total)}</b>
      </div>
      <div className="muted" style={{ fontSize: 11.5, margin: "2px 0 6px" }}>{g.hint}</div>
      {shown.map((r, i) => (
        <div key={r.id ?? i} style={{ display: "flex", gap: 8, fontSize: 12.5, padding: "3px 0", borderBottom: "1px solid #f1f5f9", color: Number(r.value) ? undefined : "#94a3b8" }}>
          <span style={{ flex: 1, minWidth: 0 }}>{r.name}{r.auto && <span className="muted" style={{ fontSize: 11 }}> · з Meta Ads</span>}</span>
          <span style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{g.unit === "%" ? pct(r.value) : money(r.value)}</span>
        </div>
      ))}
      {zero > 0 && <button className="btn btn-light" style={{ fontSize: 11.5, height: 24, marginTop: 5 }} onClick={() => setAll(!all)}>{all ? "сховати нульові" : `ще ${zero} з нулем`}</button>}
    </div>
  );
}

function AddVacancy({ funds, onAdded, onCancel }: { funds: any[]; onAdded: (id: number) => void; onCancel: () => void }) {
  const [f, setF] = useState<any>({ position: "", amount: "", employment: "labor", planned_start: "", fund: "59", department: "Продажі" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setErr(""); setBusy(true);
    const start = f.planned_start || new Date().toISOString().slice(0, 10);
    try {
      const r = await api.post<any>("/api/payroll/schemes/", {
        position: f.position, department: f.department, employment: f.employment, is_vacancy: true, in_plan: false,
        valid_from: start, planned_start: start, options: { fund_article_id: Number(f.fund) || null },
        components: [{ kind: "fixed_monthly", title: "Тверда частина «на руки»", params: { amount: Number(String(f.amount).replace(/\s/g, "")) || 0 } }],
      });
      onAdded(r.id);
    } catch (e: any) { setErr(e?.data?.detail || "Не вдалося додати вакансію"); }
    setBusy(false);
  }
  return (
    <div style={{ border: "1px dashed #94a3b8", borderRadius: 8, padding: "8px 10px", marginTop: 8 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8, fontSize: 12.5 }}>
        <label>Посада<br /><input value={f.position} onChange={(e) => setF({ ...f, position: e.target.value })} placeholder="Менеджер салону" style={{ ...inp, width: "100%" }} /></label>
        <label>Тверда «на руки», ₴/міс<br /><input value={f.amount} inputMode="numeric" onChange={(e) => setF({ ...f, amount: e.target.value })} placeholder="15000" style={{ ...inp, width: "100%" }} /></label>
        <label>Оформлення<br /><select value={f.employment} onChange={(e) => setF({ ...f, employment: e.target.value })} style={{ ...inp, width: "100%" }}>{EMPL.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label>Плановий вихід<br /><input type="date" value={f.planned_start} onChange={(e) => setF({ ...f, planned_start: e.target.value })} style={{ ...inp, width: "100%" }} /></label>
        <label>Відділ<br /><select value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} style={{ ...inp, width: "100%" }}>{["Продажі", "Склад", "Маркетинг", "Офіс"].map((x) => <option key={x}>{x}</option>)}</select></label>
        <label>Фонд у «Плануванні»<br /><select value={f.fund} onChange={(e) => setF({ ...f, fund: e.target.value })} style={{ ...inp, width: "100%" }}>{funds.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
      </div>
      <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>% з продажів новачка не додаємо: він платиться з нових грошей, які людина принесе. У точку беззбитковості йде лише тверда частина з податками.</div>
      {err && <div style={{ color: "#b91c1c", fontSize: 12.5, marginTop: 4 }}>{err}</div>}
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button className="btn btn-primary" style={{ fontSize: 12.5 }} disabled={busy || !f.position || !f.amount} onClick={save}>Додати вакансію</button>
        <button className="btn btn-light" style={{ fontSize: 12.5 }} onClick={onCancel}>Скасувати</button>
      </div>
    </div>
  );
}

export default function BreakevenAtm() {
  const [d, setD] = useState<any>(null);
  const [withIds, setWithIds] = useState<number[]>([]);
  const [withoutIds, setWithoutIds] = useState<number[]>([]);
  const [hidden, setHidden] = useState(false);
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState("");
  const q = [withIds.length ? `with=${withIds.join(",")}` : "", withoutIds.length ? `without=${withoutIds.join(",")}` : ""].filter(Boolean).join("&");
  const load = () => api.get<any>(`/api/payroll/breakeven/${q ? `?${q}` : ""}`).then(setD).catch(() => setHidden(true));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [q]);
  if (hidden) return null;
  if (!d) return <div className="muted" style={{ fontSize: 12.5, margin: "10px 0" }}>Рахуємо розшифровку…</div>;

  const toggle = (v: any) => {
    const id = v.scheme_id;
    if (v.included) { setWithIds((x) => x.filter((y) => y !== id)); setWithoutIds((x) => (x.includes(id) ? x : [...x, id])); }
    else { setWithoutIds((x) => x.filter((y) => y !== id)); setWithIds((x) => (x.includes(id) ? x : [...x, id])); }
  };
  async function sync(r: any) {
    const was = r.unit === "%" ? pct(r.value) : money(r.value);
    const will = r.unit === "%" ? pct(r.suggested) : money(r.suggested);
    if (!window.confirm(`Змінити фонд «${r.name}» у «Плануванні»: ${was} → ${will}?\nТочка беззбитковості перерахується. Зміна запишеться в історію ставок.`)) return;
    setMsg("");
    try { await api.post("/api/payroll/funds/sync/", { fund_id: r.fund_id }); setMsg(`Фонд «${r.name}» оновлено: ${will}.`); load(); }
    catch (e: any) { setMsg(e?.data?.detail || "Не вдалося оновити фонд"); }
  }
  async function archive(v: any) {
    if (!window.confirm(`Прибрати вакансію «${v.position}»?`)) return;
    await api.post(`/api/payroll/schemes/${v.scheme_id}/archive/`, {}); load();
  }
  const labels = d.group_labels || {};
  const groups = GROUPS.filter((g) => (d.levels?.[g.key] || []).length);
  const fixedSum = ["margin", "skd", "upr", "other"].reduce((s, k) => s + (d.levels?.[k] || []).reduce((a: number, r: any) => a + Number(r.value || 0), 0), 0);
  const fundChoices = (d.levels?.margin || []).filter((r: any) => r.id && !r.auto);
  const vac: any[] = d.vacancies || [];

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap", margin: "0 0 8px" }}>
        <b style={{ fontSize: 15 }}>З чого складається точка беззбитковості</b>
        <span className="muted" style={{ fontSize: 12 }}>фонди — з «Планування» (там і змінюються); тут нічого не підміняється</span>
      </div>
      <div className="panel" style={{ margin: "0 0 10px", fontSize: 13 }}>
        <Icon n="calculator" size={14} /> ТБ = фонди в гривнях <b>{money(fixedSum)}</b> ÷ маржинальність <b>{pct(d.margin_pct)}</b> = <b>{money(d.breakeven)}</b> на місяць.
        <span className="muted"> Маржинальність = 100% − фонди виручки {pct(d.rev_funds_pct)}.</span>
        {d.k_fixed && <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Кожні +10 000 ₴ твердих витрат на місяць піднімають ТБ на {money(10000 * d.k_fixed)} (×{d.k_fixed}).</div>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 10 }}>
        {groups.map((g) => <Group key={g.key} g={g} label={labels[g.key] || g.key} rows={d.levels[g.key]} />)}
      </div>

      {(d.fot || []).length > 0 && (
        <div className="panel" style={{ margin: "10px 0 0" }}>
          <b style={{ fontSize: 13.5 }}><Icon n="users" size={14} /> Зарплати: у фонді і за ставками</b>
          <div className="muted" style={{ fontSize: 11.5, margin: "2px 0 6px" }}>
            У ТБ йде сума з фонду. Праворуч — скільки виходить за «Ставками співробітників» (тверда частина з податками; % продажників — середнє за {d.shares?.from?.slice(8, 10)}.{d.shares?.from?.slice(5, 7)}–{d.shares?.to?.slice(8, 10)}.{d.shares?.to?.slice(5, 7)}).
            Фонд змінюється лише коли ви натиснете «Підставити».
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
              <thead><tr style={{ textAlign: "left", color: "#64748b", fontSize: 11.5 }}><th style={{ padding: "4px 6px" }}>Фонд</th><th style={{ textAlign: "right" }}>У фонді</th><th style={{ textAlign: "right" }}>За ставками</th><th style={{ textAlign: "right" }}>Різниця</th><th /></tr></thead>
              <tbody>{d.fot.map((r: any) => {
                const f = (x: any) => (r.unit === "%" ? pct(x) : money(x));
                const same = Math.abs(Number(r.diff || 0)) < (r.unit === "%" ? 0.01 : 1);
                return (
                  <tr key={r.fund_id} style={{ borderTop: "1px solid #f1f5f9", verticalAlign: "top" }}>
                    <td style={{ padding: "5px 6px" }}>{r.name}
                      {r.people?.length > 0 && <div className="muted" style={{ fontSize: 11 }}>{r.people.map((p: any) => `${p.name} ${money(p.amount)}`).join(" · ")}</div>}
                      {!r.syncable && <div className="muted" style={{ fontSize: 11 }}>у фонді не лише зарплати — тільки порівняння</div>}
                      {r.fund_id === 55 && <div className="muted" style={{ fontSize: 11 }}>відрядна склад: лише підтверджені записи складу (денна ставка й тонування ще не всі вносяться)</div>}</td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{f(r.value)}</td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{f(r.suggested)}</td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", color: same ? "#15803d" : "#b45309" }}>{same ? "збігається" : `${Number(r.diff) > 0 ? "+" : ""}${f(r.diff)}`}</td>
                    <td style={{ textAlign: "right" }}>{!same && r.syncable && d.can_sync && <button className="btn btn-light" style={{ fontSize: 12, height: 26 }} onClick={() => sync(r)}>Підставити</button>}</td>
                  </tr>);
              })}</tbody>
            </table>
          </div>
          {msg && <div style={{ fontSize: 12.5, marginTop: 6 }}>{msg}</div>}
        </div>
      )}

      <div className="panel" style={{ margin: "10px 0 0" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <b style={{ fontSize: 13.5 }}><Icon n="user-plus" size={14} /> Вакансії — «що якщо»</b>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 13 }}>ТБ з обраними: <b>{money(d.breakeven_with)}</b>{d.with_delta ? <span className="muted"> (+{money(d.with_delta)})</span> : null}</span>
        </div>
        <div className="muted" style={{ fontSize: 11.5, margin: "2px 0 6px" }}>Відмітьте кілька — побачите нову точку беззбитковості. Фонди від цього не змінюються: коли людина вийде — підставите ставку у фонд кнопкою вище.</div>
        {vac.length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>Вакансій немає.</div>}
        {vac.map((v) => (
          <div key={v.scheme_id} style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12.5, padding: "5px 0", borderBottom: "1px solid #f1f5f9", flexWrap: "wrap" }}>
            <label style={{ display: "flex", gap: 8, alignItems: "baseline", flex: 1, minWidth: 220, cursor: "pointer" }}>
              <input type="checkbox" checked={!!v.included} onChange={() => toggle(v)} />
              <span>{v.position}<span className="muted">{v.planned_start ? ` · вихід ${v.planned_start.slice(8, 10)}.${v.planned_start.slice(5, 7)}` : ""}{v.employment ? ` · ${v.employment}` : ""}{v.fund ? ` · фонд «${v.fund}»` : ""}</span></span>
            </label>
            {v.fixed_net != null && <span className="muted">«на руки» {money(v.fixed_net)} · компанії {money(v.fixed_cost)}/міс</span>}
            <b style={{ whiteSpace: "nowrap", minWidth: 110, textAlign: "right" }}>{v.delta_breakeven ? `ТБ +${money(v.delta_breakeven)}` : "—"}</b>
            {d.can_edit && <button className="btn btn-light" title="Прибрати вакансію" style={{ fontSize: 11.5, height: 24, padding: "0 6px" }} onClick={() => archive(v)}><Icon n="x" size={12} /></button>}
          </div>
        ))}
        {d.can_edit && !adding && <button className="btn btn-light" style={{ fontSize: 12.5, marginTop: 8 }} onClick={() => setAdding(true)}><Icon n="plus" size={13} /> Додати вакансію</button>}
        {adding && <AddVacancy funds={fundChoices} onCancel={() => setAdding(false)} onAdded={(id) => { setAdding(false); setWithoutIds((x) => x.filter((y) => y !== id)); setWithIds((x) => [...x, id]); }} />}
      </div>
    </div>
  );
}
