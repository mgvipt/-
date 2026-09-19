// 19.09.2026 (Олег): план продажника по тижнях і днях + «що потрібно для плану» + зведена для власника.
// Гроші — з одного місця (як ЗП): оплати по угодах менеджера з фінансового журналу мінус повернення, за датою приходу.
import { Fragment, useEffect, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";

const fmt = (v: any) => Math.round(Number(v || 0)).toLocaleString("uk-UA");
const pctColor = (p: number | null | undefined) =>
  p === null || p === undefined ? "#94a3b8" : p >= 100 ? "#15803d" : p >= 80 ? "#b45309" : "#b91c1c";
const TH: any = { padding: "7px 8px", textAlign: "right", fontSize: 11.5, color: "#64748b", fontWeight: 600, whiteSpace: "nowrap" };
const TD: any = { padding: "7px 8px", textAlign: "right", whiteSpace: "nowrap" };

function Pct({ v }: { v: number | null | undefined }) {
  if (v === null || v === undefined) return <span style={{ color: "#cbd5e1" }}>—</span>;
  return <b style={{ color: pctColor(v) }}>{v}%</b>;
}

export default function PlanGrid({ period, userId }: { period: string; userId?: number }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (!period) return;
    setErr("");
    api.get<any>(`/api/payroll/my/plan-grid/?period=${period}` + (userId ? `&user=${userId}` : ""))
      .then((r) => { setD(r); const cw = (r.weeks || []).find((w: any) => w.current); if (cw) setOpen({ [cw.from]: true }); })
      .catch((e: any) => setErr(e?.response?.data?.detail || "Не вдалося завантажити план"));
  }, [period, userId]);
  if (err) return <div className="note">{err}</div>;
  if (!d) return null;
  if (!d.plan || !d.plan.total) return <div className="panel"><div className="label">📅 План по тижнях</div><div className="muted" style={{ fontSize: 12.5 }}>План на цей місяць ще не встановлено (Фінанси → Плани).</div></div>;
  const n = d.need;
  const m = d.model || {};
  return (
    <div className="panel">
      <div className="label" style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <Icon n="calendar" size={15} /> План по тижнях і днях
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "baseline", fontSize: 13, marginBottom: 10 }}>
        <span>План місяця <b>{fmt(d.plan.total)} ₴</b></span>
        <span>Факт <b>{fmt(d.fact)} ₴</b> · <Pct v={d.pct} /></span>
        <span className="muted">Темп: <Pct v={d.pace_pct} /> від плану на сьогодні ({fmt(d.plan_to_date)} ₴)</span>
        {d.by_part?.online && <span className="muted">онлайн {fmt(d.by_part.online.fact)} / {fmt(d.by_part.online.plan)} (<Pct v={d.by_part.online.pct} />) · офлайн {fmt(d.by_part.offline.fact)} / {fmt(d.by_part.offline.plan)} (<Pct v={d.by_part.offline.pct} />)</span>}
      </div>

      {n && (
        <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8 }}>Що потрібно до кінця місяця · {n.days} роб. дн. · залишилось {fmt(n.left)} ₴</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 8 }}>
            {[["Оплат на день", `${fmt(n.per_day)} ₴`, ""], ["Основних продажів", `${n.mains_per_day} / день`, `разом ${n.mains}`],
              ["Тест-наборів", `${n.tests_per_day} / день`, `разом ${n.tests}`], ["Діалогів взяти", `${n.dialogs_per_day} / день`, `разом ${n.dialogs}`]].map(([l, v, s]) => (
              <div key={l} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "8px 10px" }}>
                <div className="muted" style={{ fontSize: 11.5 }}>{l}</div>
                <div style={{ fontSize: 18, fontWeight: 800 }}>{v}</div>
                {s && <div className="muted" style={{ fontSize: 11 }}>{s}</div>}
              </div>
            ))}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 7, lineHeight: 1.45 }}>
            Як пораховано: середній чек основного {fmt(m.avg_check)} ₴ ({m.avg_check_src}); через тест-набір приходить {m.via_test}% основних ({m.via_test_src});
            тест→основне {m.conv_tm}% ({m.conv_tm_src}){m.dialogs_per_sale ? `; ${m.dialogs_per_sale} діалога на одну оплату` : `; діалог→тест ${m.conv_lt}% (${m.conv_lt_src})`}.
          </div>
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 620 }}>
          <thead><tr style={{ background: "#f8fafc" }}>
            <th style={{ ...TH, textAlign: "left" }}>Тиждень / день</th><th style={TH}>План, ₴</th><th style={TH}>Факт, ₴</th><th style={TH}>%</th>
            <th style={TH} title="Основні продажі — за днем першої оплати">Основних</th><th style={TH} title="Тест-набори — за днем першої оплати">Тест-наборів</th>
            <th style={TH} title="Діалоги, які ви взяли в роботу">Діалогів взято</th>
          </tr></thead>
          <tbody>{(d.weeks || []).map((w: any) => {
            const on = !!open[w.from];
            return (
              <Fragment key={w.from}>
                <tr onClick={() => setOpen((o) => ({ ...o, [w.from]: !o[w.from] }))} style={{ borderTop: "1px solid #e2e8f0", cursor: "pointer", background: w.current ? "#eff6ff" : undefined }}>
                  <td style={{ ...TD, textAlign: "left", fontWeight: 700 }}>
                    <Icon n="chevron-down" size={13} style={{ transform: on ? "none" : "rotate(-90deg)", color: "#64748b", marginRight: 4 }} />
                    {w.label}{w.current && <span style={{ marginLeft: 6, fontSize: 10.5, color: "#1d4ed8" }}>цей тиждень</span>}
                  </td>
                  <td style={{ ...TD, fontWeight: 700 }}>{fmt(w.plan)}</td><td style={{ ...TD, fontWeight: 700 }}>{fmt(w.fact)}</td><td style={TD}><Pct v={w.pct} /></td>
                  <td style={TD}>{w.mains}</td><td style={TD}>{w.tests}</td><td style={TD}>{w.taken}</td>
                </tr>
                {on && w.days.map((x: any) => (
                  <tr key={x.date} style={{ borderTop: "1px solid #f1f5f9", color: x.workday ? undefined : "#94a3b8", background: x.future ? "#fcfcfd" : undefined }}>
                    <td style={{ ...TD, textAlign: "left", paddingLeft: 28 }}>{x.date.slice(8, 10)}.{x.date.slice(5, 7)} <span className="muted">{x.wd}</span>{!x.workday && <span className="muted"> · вихідний</span>}</td>
                    <td style={TD}>{x.plan ? fmt(x.plan) : "—"}</td><td style={TD}>{x.future ? "" : fmt(x.fact)}</td><td style={TD}>{x.future ? "" : <Pct v={x.pct} />}</td>
                    <td style={TD}>{x.future ? "" : x.mains || ""}</td><td style={TD}>{x.future ? "" : x.tests || ""}</td><td style={TD}>{x.future ? "" : x.taken || ""}</td>
                  </tr>
                ))}
              </Fragment>
            );
          })}</tbody>
          <tfoot><tr style={{ borderTop: "2px solid #e2e8f0", fontWeight: 800 }}>
            <td style={{ ...TD, textAlign: "left" }}>Місяць</td><td style={TD}>{fmt(d.plan.total)}</td><td style={TD}>{fmt(d.fact)}</td><td style={TD}><Pct v={d.pct} /></td>
            <td style={TD}>{d.totals.mains}</td><td style={TD}>{d.totals.tests}</td><td style={TD}>{d.totals.taken}</td>
          </tr></tfoot>
        </table>
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{d.source} Денний план = план місяця ÷ {d.workdays} роб. днів (пн–пт).</div>
    </div>
  );
}

export function PlanTeam({ period }: { period: string }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => { if (period) api.get<any>(`/api/payroll/plan-team/?period=${period}`).then(setD).catch(() => setD(null)); }, [period]);
  if (!d || !(d.rows || []).length) return null;
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 6 }}>📅 Плани команди · тиждень і місяць</div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 820 }}>
          <thead><tr style={{ background: "#f8fafc" }}>
            <th style={{ ...TH, textAlign: "left" }}>Співробітник</th><th style={TH}>План міс.</th><th style={TH}>Факт</th><th style={TH}>%</th><th style={TH}>Темп</th>
            <th style={TH}>Цей тиждень</th><th style={TH}>Треба в день</th><th style={TH}>Основних/день</th><th style={TH}>Тестів/день</th><th style={TH}>Діалогів/день</th>
          </tr></thead>
          <tbody>{d.rows.map((r: any) => (
            <tr key={r.user.id} style={{ borderTop: "1px solid #f1f5f9" }}>
              <td style={{ ...TD, textAlign: "left", fontWeight: 600 }}>{r.user.name}</td>
              <td style={TD}>{fmt(r.plan)}</td><td style={TD}>{fmt(r.fact)}</td><td style={TD}><Pct v={r.pct} /></td><td style={TD}><Pct v={r.pace_pct} /></td>
              <td style={TD}>{r.week ? <>{fmt(r.week.fact)} / {fmt(r.week.plan)} · <Pct v={r.week.pct} /></> : "—"}</td>
              <td style={TD}>{r.need ? `${fmt(r.need.per_day)} ₴` : "—"}</td><td style={TD}>{r.need?.mains_per_day ?? "—"}</td>
              <td style={TD}>{r.need?.tests_per_day ?? "—"}</td><td style={TD}>{r.need?.dialogs_per_day ?? "—"}</td>
            </tr>
          ))}</tbody>
          <tfoot><tr style={{ borderTop: "2px solid #e2e8f0", fontWeight: 800 }}>
            <td style={{ ...TD, textAlign: "left" }}>Команда</td><td style={TD}>{fmt(d.team.plan)}</td><td style={TD}>{fmt(d.team.fact)}</td><td style={TD}><Pct v={d.team.pct} /></td><td colSpan={6} />
          </tr></tfoot>
        </table>
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>Гроші — оплати по угодах з фінансового журналу мінус повернення (те саме, що ЗП). Темп — факт проти плану на сьогодні.</div>
    </div>
  );
}
