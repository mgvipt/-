import { DealGroups } from "./DealGroupsTable";
import { Icon } from "./Icon";

/* 15.09.2026: «Як прорахувалось» — одна розшифровка рядка ЗП для власника (Фінанси → ЗП/KPI) і для самого співробітника
 * (Розвиток → Моя ЗП і KPI): пояснення, зведення, таблиця угод / оплат / записів, «Разом = сума рядка». */

const money = (n: any) => Math.round(Number(n || 0)).toLocaleString("uk-UA") + " ₴";
const money2 = (n: any) => {
  const x = Number(n || 0);
  return x.toLocaleString("uk-UA", { minimumFractionDigits: Number.isInteger(x) ? 0 : 2, maximumFractionDigits: 2 }) + " ₴";
};
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
export function matchDetail(dls: any[], l: any, i: number) {
  if (l.component != null) {
    const x = dls.find((d: any) => d.component === l.component && d.kind === l.kind);
    if (x) return x;
  }
  const same = dls.filter((d: any) => d.kind === l.kind);
  if (same.length === 1) return same[0];
  return dls[i] && dls[i].kind === l.kind ? dls[i] : null;
}

/** «Як прорахувалось»: пояснення, зведення, таблиця угод/оплат/записів (прокрутка), попередження, разом = сума рядка. */
export function LineDetail({ dl, frozenAmount }: { dl: any; frozenAmount: number | null }) {
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
