import { useEffect, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";

/* Акти обʼєкта в картці клієнта (14.09, Олег: «акти в налаштуваннях нелогічно — в картку клієнта»).
 * Менеджеру обʼєкта — % від усієї суми акту (за його ставкою, зазвичай 2%), нараховується в ЗП місяця, коли акт закрили.
 * Вносити — право «Змінювати ставки», закривати — лише «Закривати акти обʼєктів» (Олег). Без прав блок не показується. */

const money = (n: any) => Math.round(Number(n || 0)).toLocaleString("uk-UA") + " ₴";
const dm = (s: string | null) => (s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "");
const inp: React.CSSProperties = { height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 8px", fontSize: 13, width: "100%", boxSizing: "border-box" };
const today = () => new Date().toISOString().slice(0, 10);

export default function ObjectActsBlock({ contactId }: { contactId: number }) {
  const [d, setD] = useState<any>(null);
  const [hidden, setHidden] = useState(false);
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState<any>({ title: "", number: "", act_date: today(), amount_total: "", manager_id: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api.get<any>(`/api/payroll/acts/?contact=${contactId}`).then(setD).catch(() => setHidden(true));
  useEffect(() => { setD(null); setAdding(false); load(); /* eslint-disable-next-line */ }, [contactId]);
  if (hidden || !d) return null;
  const acts: any[] = d.results || [];
  if (!acts.length && !d.can_add) return null;
  const open = acts.filter((a) => a.status !== "closed");
  const closedSum = acts.filter((a) => a.status === "closed").reduce((s, a) => s + Number(a.commission_amount || 0), 0);

  async function add() {
    setErr(""); setBusy(true);
    try {
      await api.post("/api/payroll/acts/", { ...f, contact_id: contactId, manager_id: Number(f.manager_id) || null });
      setF({ title: "", number: "", act_date: today(), amount_total: "", manager_id: f.manager_id }); setAdding(false); load();
    } catch (e: any) { setErr(e?.data?.detail || "Не вдалося внести акт"); }
    setBusy(false);
  }
  async function close(a: any) {
    if (!window.confirm(`Перевірили і закриваєте акт «${a.title}» на ${money(a.amount_total)}? Менеджеру ${a.manager_name || ""} нарахується % у ЗП цього місяця.`)) return;
    try { await api.post(`/api/payroll/acts/${a.id}/close/`, {}); load(); }
    catch (e: any) { setErr(e?.data?.detail || "Не вдалося закрити акт"); }
  }

  return (
    <div className="panel" style={{ margin: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Icon n="file" size={15} style={{ color: "#0e7490" }} />
        <b style={{ fontSize: 13.5 }}>Акти обʼєкта</b>
        <span className="muted" style={{ fontSize: 12 }}>
          {acts.length ? `${acts.length} · відкритих ${open.length}${closedSum ? ` · менеджеру нараховано ${money(closedSum)}` : ""}` : "ще немає"}
        </span>
        <span style={{ flex: 1 }} />
        {d.can_add && !adding && <button className="btn btn-light" style={{ fontSize: 12, height: 28 }} onClick={() => setAdding(true)}><Icon n="plus" size={13} /> Внести акт</button>}
      </div>
      {(acts.length > 0 || adding) && <div className="muted" style={{ fontSize: 11.5, margin: "4px 0 2px" }}>
        Менеджеру обʼєкта — % від усієї суми акту за його ставкою (зазвичай 2%). Нараховується в ЗП місяця, коли акт закрили. Закриває акт лише власник після перевірки.
      </div>}

      {adding && (
        <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "8px 10px", marginTop: 6 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8, fontSize: 12.5 }}>
            <label>Що за акт<br /><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="1-й поверх, стіни" style={inp} /></label>
            <label>№ акту<br /><input value={f.number} onChange={(e) => setF({ ...f, number: e.target.value })} style={inp} /></label>
            <label>Дата акту<br /><input type="date" value={f.act_date} onChange={(e) => setF({ ...f, act_date: e.target.value })} style={inp} /></label>
            <label>Сума акту, ₴<br /><input value={f.amount_total} inputMode="decimal" onChange={(e) => setF({ ...f, amount_total: e.target.value })} style={inp} /></label>
            <label>Менеджер обʼєкта<br /><select value={f.manager_id} onChange={(e) => setF({ ...f, manager_id: e.target.value })} style={inp}>
              <option value="">—</option>{(d.managers || []).map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button className="btn btn-primary" style={{ fontSize: 12.5 }} disabled={busy || !f.title || !f.amount_total || !f.manager_id} onClick={add}>Внести акт</button>
            <button className="btn btn-light" style={{ fontSize: 12.5 }} onClick={() => { setAdding(false); setErr(""); }}>Скасувати</button>
          </div>
        </div>
      )}
      {err && <div style={{ color: "#b91c1c", fontSize: 12.5, marginTop: 6 }}>{err}</div>}

      {acts.length > 0 && (
        <div style={{ overflowX: "auto", marginTop: 6 }}>
          <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
            <thead><tr style={{ textAlign: "left", color: "#64748b", fontSize: 11.5 }}>
              <th style={{ padding: "4px 6px" }}>Дата</th><th>Акт</th><th>Менеджер</th><th style={{ textAlign: "right" }}>Сума акту</th><th style={{ textAlign: "right" }}>Менеджеру</th><th>Статус</th><th />
            </tr></thead>
            <tbody>{acts.map((a) => (
              <tr key={a.id} style={{ borderTop: "1px solid #f1f5f9" }}>
                <td style={{ padding: "5px 6px", whiteSpace: "nowrap" }}>{dm(a.act_date)}</td>
                <td>{a.title}{a.number ? <span className="muted"> · №{a.number}</span> : null}</td>
                <td>{a.manager_name || "—"}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{money(a.amount_total)}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{a.commission_amount != null ? `${money(a.commission_amount)} (${a.commission_pct}%)` : <span className="muted">після закриття</span>}</td>
                <td>{a.status === "closed"
                  ? <span style={{ fontSize: 11.5, color: "#15803d", background: "#dcfce7", borderRadius: 999, padding: "1px 8px", whiteSpace: "nowrap" }}><Icon n="check" size={12} /> закрито · ЗП {a.payroll_period}</span>
                  : <span style={{ fontSize: 11.5, color: "#92400e", background: "#fef3c7", borderRadius: 999, padding: "1px 8px" }}>чекає перевірки</span>}
                  {a.closed_by ? <div className="muted" style={{ fontSize: 11 }}>{a.closed_by}</div> : null}</td>
                <td style={{ textAlign: "right" }}>{a.status !== "closed" && d.can_close && <button className="btn btn-primary" style={{ fontSize: 12, height: 26 }} onClick={() => close(a)}>Перевірив — закрити</button>}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
