import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../Icon";
import { DealGroups } from "../DealGroupsTable";

/* ЗП за ставками співробітників (14.09) — одне джерело: Налаштування → Ставки співробітників.
 * Відомість місяця: «Затвердити місяць» заморожує суму (зміна ставок потім її не чіпає — лише «зараз вийшло б …»),
 * «Привʼязати виплату» — відмітити фактичні виплати з журналу: нараховано / виплачено / залишок.
 * Показується у Фінанси → ЗП/KPI над старою формулою. Бачить лише той, у кого є право на ставки.
 * 15.09 (whpay): «Як прорахувалось» біля кожного рядка — угоди, оплати, записи складу, з яких склалась сума
 * (/api/payroll/calc-detail/, один запит на людину при першому відкритті; затверджений місяць — розшифровка наживо). */

const money = (n: any) => Math.round(Number(n || 0)).toLocaleString("uk-UA") + " ₴";
const dm = (s: string) => (s ? `${s.slice(8, 10)}.${s.slice(5, 7)}` : "");
const money2 = (n: any) => Number(n || 0).toLocaleString("uk-UA", { maximumFractionDigits: 2 }) + " ₴";
const num = (n: any) => Number(n || 0).toLocaleString("uk-UA", { maximumFractionDigits: 3 });
const dmy = (s: string) => (s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "");
const RIGHT = ["money", "pct", "num"];

function cellView(c: any, v: any) {
  if (v === null || v === undefined || v === "") return <span className="muted">—</span>;
  if (c.t === "deal") return <a href={`/deals/${v}`} target="_blank" rel="noreferrer">#{v}</a>;
  if (c.t === "money") return money2(v);
  if (c.t === "pct") return `${num(v)}%`;
  if (c.t === "num") return num(v);
  if (c.t === "date") return dmy(String(v));
  return String(v);
}

/** Рядок відомості → його рядок у розшифровці (для затвердженого місяця — за компонентом схеми). */
function matchDetail(dls: any[], l: any, i: number) {
  if (l.component != null) {
    const x = dls.find((d: any) => d.component === l.component && d.kind === l.kind);
    if (x) return x;
  }
  const same = dls.filter((d: any) => d.kind === l.kind);
  if (same.length === 1) return same[0];
  return dls[i] && dls[i].kind === l.kind ? dls[i] : null;
}

/** «Як прорахувалось»: пояснення, зведення, таблиця угод/оплат/записів (прокрутка), попередження, разом = сума рядка. */
function LineDetail({ dl, frozenAmount }: { dl: any; frozenAmount: number | null }) {
  const cols: any[] = dl.columns || [];
  const rows: any[] = dl.rows || [];
  return (
    <div style={{ margin: "6px 0 8px", padding: "8px 10px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 12.5 }}>
      {dl.explain && <div style={{ marginBottom: 6, lineHeight: 1.45 }}>{dl.explain}</div>}
      {(dl.summary || []).length > 0 && <div style={{ display: "grid", gap: 2, marginBottom: 6 }}>{dl.summary.map((s: any, i: number) => (
        <div key={i} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><span className="muted" style={{ minWidth: 190 }}>{s.label}</span><span>{s.value}</span></div>))}</div>}
      {(dl.groups || []).length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>{dl.groups.map((g: any) => (
        <span key={g.op} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 999, padding: "2px 9px", fontSize: 12 }}>{g.label} ×{g.count}{g.kg ? ` · ${num(g.kg)} кг` : ""} · <b style={{ color: g.amount < 0 ? "#b91c1c" : undefined }}>{money2(g.amount)}</b></span>))}</div>}
      {(dl.deal_groups || []).length > 0 && <DealGroups groups={dl.deal_groups} />}
      {cols.length > 0 && rows.length > 0 && (() => {
        const flat = <div style={{ overflowX: "auto", maxHeight: 380, overflowY: "auto", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 6 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: Math.max(480, cols.length * 95) }}>
            <thead><tr>{cols.map((c: any) => <th key={c.k} style={{ position: "sticky", top: 0, background: "#f1f5f9", textAlign: RIGHT.includes(c.t) ? "right" : "left", padding: "5px 7px", fontWeight: 600, whiteSpace: "nowrap" }}>{c.label}</th>)}</tr></thead>
            <tbody>{rows.map((row: any, i: number) => <tr key={i} style={{ borderTop: "1px solid #f1f5f9", background: row.estimate ? "#fffbeb" : undefined }}>
              {cols.map((c: any) => <td key={c.k} style={{ padding: "4px 7px", textAlign: RIGHT.includes(c.t) ? "right" : "left", whiteSpace: c.t === "text" ? "normal" : "nowrap", color: c.t === "money" && Number(row[c.k]) < 0 ? "#b91c1c" : undefined }}>{cellView(c, row[c.k])}</td>)}
            </tr>)}</tbody>
          </table>
        </div>;
        return (dl.deal_groups || []).length > 0
          ? <details style={{ marginBottom: 6 }}><summary style={{ cursor: "pointer", fontSize: 12 }}>Усі записи підряд ({rows.length})</summary>{flat}</details>
          : flat;
      })()}
      {cols.length > 0 && rows.length === 0 && <div className="muted">Записів за місяць немає.</div>}
      {dl.truncated && <div className="muted" style={{ fontSize: 11.5 }}>Показано перші {rows.length} рядків; «Разом» — з усіх.</div>}
      {(dl.warnings || []).map((w: string, i: number) => <div key={i} style={{ marginTop: 5, color: "#92400e" }}><Icon n="warn" size={12} /> {w}</div>)}
      {(dl.links || []).length > 0 && <div style={{ marginTop: 3, display: "flex", flexWrap: "wrap", gap: "2px 10px", fontSize: 11.5, maxHeight: 110, overflowY: "auto" }}>{dl.links.map((x: any, i: number) => <a key={i} href={`/deals/${x.deal_id}`} target="_blank" rel="noreferrer">{x.label}</a>)}</div>}
      {(dl.notes || []).map((n: string, i: number) => <div key={i} className="muted" style={{ fontSize: 11.5, marginTop: 3 }}>{n}</div>)}
      <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 6, fontWeight: 600, flexWrap: "wrap" }}>
        <Icon n={dl.matches ? "check" : "warn"} size={13} style={{ color: dl.matches ? "#15803d" : "#b45309" }} />
        Разом за розшифровкою: {dl.total === null || dl.total === undefined ? "—" : money(dl.total)}{dl.matches ? " = сума рядка" : ` · сума рядка ${money(dl.amount)}`}
      </div>
      {frozenAmount !== null && frozenAmount !== dl.amount && <div style={{ fontSize: 11.5, color: "#92400e", marginTop: 2 }}>Затверджено {money(frozenAmount)}; наживо зараз {money(dl.amount)} — розшифровка показує «наживо».</div>}
    </div>
  );
}

function Lines({ lines, det, busy, err, open, onToggle, frozen }: {
  lines: any[]; det?: any; busy?: boolean; err?: string; open?: Record<number, boolean>; onToggle?: (i: number) => void; frozen?: boolean;
}) {
  return <>{lines.map((l: any, i: number) => {
    const dl = det?.lines ? matchDetail(det.lines, l, i) : null;
    return (
      <div key={i} style={{ padding: "3px 0", borderBottom: "1px dashed #f1f5f9" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <span style={{ flex: 1, minWidth: 0 }}>{l.title}{l.rate ? <span className="muted"> · {l.rate}</span> : null}
            {l.detail && <div className="muted" style={{ fontSize: 11.5 }}>{l.detail}</div>}
            {l.warn && <div style={{ fontSize: 11.5, color: "#92400e" }}><Icon n="warn" size={12} /> {l.warn}</div>}
            {onToggle && <div><button type="button" className="btn btn-light" style={{ fontSize: 11, height: 22, padding: "0 8px", marginTop: 3, display: "inline-flex", alignItems: "center", gap: 4 }} onClick={() => onToggle(i)}>
              <Icon n="calculator" size={12} /> {open?.[i] ? "Сховати розрахунок" : "Як прорахувалось"}</button></div>}</span>
          <b style={{ whiteSpace: "nowrap" }}>{money(l.amount)}</b>
        </div>
        {open?.[i] && (busy && !det ? <div className="muted" style={{ fontSize: 12, padding: "4px 0" }}>Рахуємо розшифровку…</div>
          : err ? <div className="note" style={{ fontSize: 12 }}>{err}</div>
            : dl ? <LineDetail dl={dl} frozenAmount={frozen ? l.amount : null} />
              : det ? <div className="muted" style={{ fontSize: 12, padding: "4px 0" }}>Цього рядка зараз немає в розрахунку наживо — розшифровки немає.</div> : null)}
      </div>);
  })}</>;
}

function Payouts({ run, canApprove, onChange }: { run: any; canApprove: boolean; onChange: () => void }) {
  const [cands, setCands] = useState<any[] | null>(null);
  const [pick, setPick] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  async function open() { setCands(null); const r = await api.get<any>(`/api/payroll/runs/${run.id}/candidates/`); setCands(r.results || []); }
  async function link() { setBusy(true); try { await api.post(`/api/payroll/runs/${run.id}/link/`, { transaction_ids: pick }); setCands(null); setPick([]); onChange(); } finally { setBusy(false); } }
  async function unlink(id: number) { await api.post(`/api/payroll/runs/${run.id}/unlink/`, { payout_ids: [id] }); onChange(); }
  return (
    <div style={{ marginTop: 6, fontSize: 12.5 }}>
      <div>Нараховано <b>{money(run.total)}</b> · виплачено <b>{money(run.paid)}</b> · залишок <b style={{ color: run.remaining > 0 ? "#b45309" : "#15803d" }}>{money(run.remaining)}</b></div>
      {run.payouts.map((p: any) => (
        <div key={p.id} className="muted" style={{ fontSize: 11.5 }}>• {dm(p.date)} · {money(p.amount)} · {p.counterparty || p.comment || "без коментаря"}
          {canApprove && <button className="btn btn-light" style={{ fontSize: 11, padding: "0 6px", marginLeft: 6, height: 20 }} onClick={() => unlink(p.id)}>відвʼязати</button>}</div>
      ))}
      {canApprove && cands === null && <button className="btn btn-light" style={{ fontSize: 12, marginTop: 4 }} onClick={open}>Привʼязати виплату з журналу</button>}
      {cands !== null && (
        <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "6px 8px", marginTop: 4, maxHeight: 220, overflowY: "auto" }}>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 4 }}>Виплати ЗП з журналу (категорії ЗП, цей місяць + 45 днів). Відмітьте ті, що стосуються цієї людини:</div>
          {cands.length === 0 && <div className="muted">Непривʼязаних виплат не знайдено.</div>}
          {cands.map((c: any) => (
            <label key={c.id} style={{ display: "flex", gap: 6, alignItems: "baseline", padding: "2px 0" }}>
              <input type="checkbox" checked={pick.includes(c.id)} onChange={() => setPick((v) => v.includes(c.id) ? v.filter((x) => x !== c.id) : [...v, c.id])} />
              <span>{dm(c.date)} · <b>{money(c.amount)}</b> · {c.counterparty || "—"} <span className="muted">· {c.category}{c.comment ? ` · ${c.comment}` : ""}</span></span>
            </label>
          ))}
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button className="btn btn-primary" style={{ fontSize: 12 }} disabled={busy || pick.length === 0} onClick={link}>Привʼязати ({pick.length})</button>
            <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => { setCands(null); setPick([]); }}>Скасувати</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ r, period, canApprove, onChange }: { r: any; period: string; canApprove: boolean; onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const run = r.run;
  const shown = run ? run.total : r.total;
  // 15.09 (whpay): «Як прорахувалось» — один запит на людину, при першому відкритті рядка; далі лише показ/приховування
  const [det, setDet] = useState<any>(null);
  const [detBusy, setDetBusy] = useState(false);
  const [detErr, setDetErr] = useState("");
  const [openL, setOpenL] = useState<Record<number, boolean>>({});
  async function toggleLine(i: number) {
    const willOpen = !openL[i];
    setOpenL({ ...openL, [i]: willOpen });
    if (!willOpen || det || detBusy) return;
    setDetBusy(true); setDetErr("");
    try { setDet(await api.get<any>(`/api/payroll/calc-detail/?user=${r.user_id}&period=${period}`)); }
    catch (e: any) { setDetErr(e?.data?.detail || "Не вдалося завантажити розшифровку"); }
    setDetBusy(false);
  }
  async function approve() {
    if (!window.confirm(`Затвердити ЗП за ${period} — ${r.user_name}: ${money(r.total)}? Після цього сума не зміниться, навіть якщо поміняти ставки.`)) return;
    setBusy(true); setErr("");
    try { await api.post("/api/payroll/runs/approve/", { period, user_id: r.user_id }); onChange(); }
    catch (e: any) { setErr(e?.data?.detail || "Не вдалося затвердити"); }
    setBusy(false);
  }
  async function reopen() {
    if (!window.confirm("Перевідкрити місяць? Сума знову рахуватиметься наживо; привʼязані виплати залишаться.")) return;
    await api.post(`/api/payroll/runs/${run.id}/reopen/`, {}); onChange();
  }
  return (
    <div style={{ borderTop: "1px solid #eef2f7", padding: "7px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", flexWrap: "wrap" }} onClick={() => setOpen(!open)}>
        <Icon n="chevron-down" size={14} style={{ transform: open ? "none" : "rotate(-90deg)", transition: "transform .15s", color: "#64748b" }} />
        <b style={{ flex: 1, minWidth: 160 }}>{r.user_name}<span className="muted" style={{ fontWeight: 400, fontSize: 12 }}> · {r.scheme?.position || "ставку не задано"}</span></b>
        {run
          ? <span style={{ fontSize: 11, color: "#15803d", background: "#dcfce7", borderRadius: 999, padding: "1px 8px" }}><Icon n="lock" size={11} /> затверджено{run.remaining > 0 ? ` · залишок ${money(run.remaining)}` : run.total > 0 ? " · виплачено" : ""}</span>
          : <span style={{ fontSize: 11, color: "#475569", background: "#f1f5f9", borderRadius: 999, padding: "1px 8px" }}>рахується наживо</span>}
        {run && run.live_diff ? <span style={{ fontSize: 11, color: "#92400e", background: "#fef3c7", borderRadius: 999, padding: "1px 8px" }} title="Ставки чи факти змінились після затвердження">зараз вийшло б {money(run.live_total)}</span> : null}
        {!run && r.warnings?.length > 0 && <span title={r.warnings.join("\n")} style={{ fontSize: 11, color: "#92400e", background: "#fef3c7", borderRadius: 999, padding: "1px 7px" }}><Icon n="warn" size={11} /> {r.warnings.length}</span>}
        <b style={{ fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{money(shown)}</b>
      </div>
      {open && (
        <div style={{ margin: "6px 0 0 22px", fontSize: 12.5 }}>
          {run && Object.values(openL).some(Boolean) && <div className="note" style={{ fontSize: 12, margin: "2px 0 6px", display: "flex", alignItems: "center", gap: 6 }}><Icon n="lock" size={12} /> {det?.frozen_note || `Розшифровка наживо; затверджена сума — ${money(run.total)}`}</div>}
          <Lines lines={run ? run.lines : r.lines} det={det} busy={detBusy} err={detErr} open={openL} onToggle={toggleLine} frozen={!!run} />
          <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>
            Оформлення: {r.scheme?.employment_label || "—"} · компанії коштує ≈ {money(run ? run.company_cost : r.company_cost)}
            {r.legacy && <> · за старою схемою («{r.legacy.title}») вийшло б {money(r.legacy.total)}</>}
            {run && <> · затвердив {run.approved_by} {run.approved_at ? new Date(run.approved_at).toLocaleDateString("uk-UA") : ""}{run.version > 1 ? ` (версія ${run.version})` : ""}</>}
          </div>
          {run && <Payouts run={run} canApprove={canApprove} onChange={onChange} />}
          {err && <div style={{ color: "#b91c1c", fontSize: 12, marginTop: 4 }}>{err}</div>}
          {canApprove && <div style={{ marginTop: 6, display: "flex", gap: 6 }}>
            {!run && r.scheme && <button className="btn btn-primary" style={{ fontSize: 12 }} disabled={busy} onClick={approve}>Затвердити місяць</button>}
            {run && <button className="btn btn-light" style={{ fontSize: 12 }} onClick={reopen}>Перевідкрити</button>}
          </div>}
        </div>
      )}
    </div>
  );
}

export default function PayrollTeam({ period }: { period: string }) {
  const [d, setD] = useState<any>(null);
  const [hidden, setHidden] = useState(false);
  const load = () => api.get<any>(`/api/payroll/runs/?period=${period}`).then(setD).catch(() => setHidden(true));
  useEffect(() => { setD(null); load(); /* eslint-disable-next-line */ }, [period]);
  if (hidden) return null;
  const q = d?.quarter;
  return (
    <div className="panel" style={{ margin: "0 0 14px", border: "2px solid #2E6FB0" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <b style={{ fontSize: 15 }}><Icon n="💼" size={15} /> ЗП за ставками співробітників</b>
        <span className="muted" style={{ fontSize: 12 }}>ставки — Налаштування → Ставки співробітників; «Затвердити місяць» фіксує суму, «Привʼязати виплату» — що вже виплачено</span>
        <span style={{ flex: 1 }} />
        {d && <span style={{ fontSize: 13 }}>Разом <b>{money(d.total)}</b> · виплачено <b>{money(d.paid)}</b> · затверджено {d.approved} з {d.rows.length}</span>}
      </div>
      {q && (
        <div style={{ marginTop: 6, fontSize: 12.5, borderRadius: 8, padding: "6px 10px", background: q.ok ? "#f0fdf4" : "#fef3c7" }}>
          <Icon n={q.ok ? "check" : "warn"} size={13} /> Квартал {q.months[0].slice(5)}–{q.months[2].slice(5)}.{q.months[2].slice(0, 4)}: ЗП продажників {money(q.sales_pay)} = <b>{q.pct}%</b> маржі компанії ({money(q.margin)}), межа {q.cap}%.
          <span className="muted"> {q.ok ? "У межах." : "Вище межі: розібрати причини і поправити ставки з наступного кварталу — ЗП за місяць не ріжемо."}</span>
        </div>
      )}
      {!d ? <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>Рахуємо…</div>
        : d.rows.length === 0 ? <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>Ставок ще немає — додайте в Налаштування → Ставки співробітників.</div>
          : <div style={{ marginTop: 6 }}>{d.rows.map((r: any) => <Row key={r.user_id} r={r} period={period} canApprove={!!d.can_approve} onChange={load} />)}</div>}
    </div>
  );
}
