import { Fragment, useState } from "react";
import type { CSSProperties } from "react";
import { Icon } from "./Icon";

/* 15.09.2026: склад по угодах — одна таблиця для Фінанси → ЗП/KPI → «Як прорахувалось» і для Відвантаження → ЗП
 * (кожен комірник бачить свої угоди). Колонки за кожним пунктом оплати; клік по рядку — «як пораховано» і записи. */

const money2 = (n: any) => {
  const x = Number(n || 0);
  return x.toLocaleString("uk-UA", { minimumFractionDigits: Number.isInteger(x) ? 0 : 2, maximumFractionDigits: 2 }) + " ₴";
};
const num = (n: any) => Number(n || 0).toLocaleString("uk-UA", { maximumFractionDigits: 3 });
const dmy = (s: string) => (s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "");
const TH: CSSProperties = { position: "sticky", top: 0, background: "#f1f5f9", padding: "5px 7px", fontWeight: 600, whiteSpace: "nowrap", textAlign: "left" };
const TD: CSSProperties = { padding: "4px 7px", whiteSpace: "nowrap" };
const moneyOrDash = (v: any) => (Number(v) ? money2(v) : <span className="muted">—</span>);

export function DealGroups({ groups }: { groups: any[] }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const sum = (k: string) => groups.reduce((s, g) => s + Number(g[k] || 0), 0);
  const R: CSSProperties = { ...TD, textAlign: "right" };
  return (
    <div style={{ overflowX: "auto", maxHeight: 480, overflowY: "auto", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 6, marginBottom: 6 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 900 }}>
        <thead><tr>
          <th style={TH} />
          <th style={TH}>Дата</th><th style={TH}>Угода</th><th style={TH}>Клієнт</th>
          <th style={{ ...TH, textAlign: "right" }}>Кг</th><th style={{ ...TH, textAlign: "right" }}>Вага</th>
          <th style={{ ...TH, textAlign: "right" }}>Упаковка</th><th style={{ ...TH, textAlign: "right" }}>Тонування</th>
          <th style={{ ...TH, textAlign: "right" }}>Тест-набори</th><th style={{ ...TH, textAlign: "right" }} title="Мите відро, викраски, бонуси, утримання">Інше</th>
          <th style={{ ...TH, textAlign: "right" }}>Разом</th>
        </tr></thead>
        <tbody>{groups.map((g: any) => {
          const on = !!open[g.key];
          return (
            <Fragment key={g.key}>
              <tr onClick={() => setOpen((o) => ({ ...o, [g.key]: !o[g.key] }))} style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer", background: on ? "#eff6ff" : undefined }}>
                <td style={TD}><Icon n="chevron-down" size={13} style={{ transform: on ? "none" : "rotate(-90deg)", color: "#64748b" }} /></td>
                <td style={TD}>{dmy(g.date)}</td>
                <td style={TD}>{g.deal_id ? <a href={`/deals/${g.deal_id}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>#{g.deal_id}</a> : <span className="muted">—</span>}</td>
                <td style={{ ...TD, whiteSpace: "normal", minWidth: 140 }}>{g.client || "—"}</td>
                <td style={R}>{Number(g.kg) ? num(g.kg) : <span className="muted">—</span>}</td>
                <td style={R}>{moneyOrDash(g.weight)}</td>
                <td style={R}>{moneyOrDash(g.pack)}{g.pack_txt ? <div className="muted" style={{ fontSize: 10.5 }}>{g.pack_txt}</div> : null}</td>
                <td style={R}>{moneyOrDash(g.tint)}</td>
                <td style={R}>{moneyOrDash(g.test_set)}</td>
                <td style={{ ...R, color: Number(g.other) < 0 ? "#b91c1c" : undefined }}>{moneyOrDash(g.other)}</td>
                <td style={{ ...R, fontWeight: 700 }}>{money2(g.total)}</td>
              </tr>
              {on && <tr><td colSpan={11} style={{ padding: "6px 10px 10px 30px", background: "#f8fafc" }}>
                {(g.how || []).length > 0 && <div style={{ marginBottom: 6 }}>
                  <div style={{ fontWeight: 600, marginBottom: 2 }}>Як пораховано</div>
                  {g.how.map((h: string, i: number) => <div key={i} style={{ whiteSpace: "pre-wrap", paddingLeft: h.startsWith("  ") ? 14 : 0, color: h.startsWith("  ") ? "#475569" : undefined }}>{h.trim()}</div>)}
                  {g.how_note && <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{g.how_note}</div>}
                </div>}
                <table style={{ borderCollapse: "collapse", fontSize: 11.5 }}>
                  <tbody>{(g.entries || []).map((e: any, i: number) => <tr key={i}>
                    <td style={{ padding: "2px 10px 2px 0" }}>{e.op}</td>
                    <td style={{ padding: "2px 10px 2px 0" }} className="muted">{e.rate}</td>
                    <td style={{ padding: "2px 10px 2px 0", textAlign: "right" }}>{e.qty !== null && e.qty !== undefined ? num(e.qty) : ""}</td>
                    <td style={{ padding: "2px 10px 2px 0", textAlign: "right", fontWeight: 600, color: Number(e.amount) < 0 ? "#b91c1c" : undefined }}>{money2(e.amount)}</td>
                    <td style={{ padding: "2px 0" }} className="muted">{e.note}</td>
                  </tr>)}</tbody>
                </table>
              </td></tr>}
            </Fragment>);
        })}</tbody>
        <tfoot><tr style={{ borderTop: "2px solid #e2e8f0", fontWeight: 700 }}>
          <td style={TD} /><td style={TD} colSpan={3}>Разом ({groups.length})</td>
          <td style={R}>{num(sum("kg"))}</td><td style={R}>{money2(sum("weight"))}</td><td style={R}>{money2(sum("pack"))}</td>
          <td style={R}>{money2(sum("tint"))}</td><td style={R}>{money2(sum("test_set"))}</td><td style={R}>{money2(sum("other"))}</td>
          <td style={R}>{money2(sum("total"))}</td>
        </tr></tfoot>
      </table>
    </div>
  );
}
