import { useEffect, useState } from "react";
import { api } from "../api";

/* ЗП за ставками співробітників (14.09) — одне джерело: Налаштування → Ставки співробітників.
 * Показується у Фінанси → ЗП/KPI над старою формулою. Бачить лише той, у кого є право на ставки. */

const money = (n: any) => Math.round(Number(n || 0)).toLocaleString("uk-UA") + " ₴";

function Row({ r }: { r: any }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ borderTop: "1px solid #eef2f7", padding: "7px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }} onClick={() => setOpen(!open)}>
        <span style={{ width: 14 }}>{open ? "▾" : "▸"}</span>
        <b style={{ flex: 1 }}>{r.user_name}<span className="muted" style={{ fontWeight: 400, fontSize: 12 }}> · {r.scheme?.position || "ставку не задано"}</span></b>
        {r.warnings?.length > 0 && <span title={r.warnings.join("\n")} style={{ fontSize: 11, color: "#92400e", background: "#fef3c7", borderRadius: 999, padding: "1px 7px" }}>⚠ {r.warnings.length}</span>}
        <b style={{ fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{money(r.total)}</b>
      </div>
      {open && (
        <div style={{ margin: "6px 0 0 22px", fontSize: 12.5 }}>
          {r.lines.map((l: any, i: number) => (
            <div key={i} style={{ display: "flex", gap: 8, padding: "3px 0", borderBottom: "1px dashed #f1f5f9" }}>
              <span style={{ flex: 1, minWidth: 0 }}>{l.title}{l.rate ? <span className="muted"> · {l.rate}</span> : null}
                {l.detail && <div className="muted" style={{ fontSize: 11.5 }}>{l.detail}</div>}
                {l.warn && <div style={{ fontSize: 11.5, color: "#92400e" }}>⚠ {l.warn}</div>}</span>
              <b style={{ whiteSpace: "nowrap" }}>{money(l.amount)}</b>
            </div>
          ))}
          <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>
            Оформлення: {r.scheme?.employment_label || "—"} · компанії коштує ≈ {money(r.company_cost)}
            {r.legacy && <> · за старою схемою («{r.legacy.title}») вийшло б {money(r.legacy.total)}</>}
          </div>
        </div>
      )}
    </div>
  );
}

export default function PayrollTeam({ period }: { period: string }) {
  const [d, setD] = useState<any>(null);
  const [hidden, setHidden] = useState(false);
  useEffect(() => { setD(null); api.get<any>(`/api/payroll/calc/?period=${period}`).then(setD).catch(() => setHidden(true)); }, [period]);
  if (hidden) return null;
  return (
    <div className="panel" style={{ margin: "0 0 14px", border: "2px solid #2E6FB0" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <b style={{ fontSize: 15 }}>💼 ЗП за ставками співробітників</b>
        <span className="muted" style={{ fontSize: 12 }}>одне джерело — Налаштування → Ставки співробітників; змінили ставку — змінилось тут, у точці беззбитковості і в картці угоди</span>
        <span style={{ flex: 1 }} />
        {d && <span style={{ fontSize: 13 }}>Разом <b>{money(d.total)}</b> · компанії коштує <b>{money(d.company_cost)}</b></span>}
      </div>
      {!d ? <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>Рахуємо…</div>
        : d.rows.length === 0 ? <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>Ставок ще немає — додайте в Налаштування → Ставки співробітників.</div>
          : <div style={{ marginTop: 6 }}>{d.rows.map((r: any) => <Row key={r.user_id} r={r} />)}</div>}
    </div>
  );
}
