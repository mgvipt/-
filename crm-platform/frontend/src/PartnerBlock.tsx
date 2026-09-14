/* Блок «Партнер» у картці клієнта (14.09.2026).
 * Галочка «Партнер» → рівень «Старт» (або вище, якщо оборот уже більший). Рівень лише ПІДВИЩУЄТЬСЯ.
 * Зняти галочку — знижки не діють, але рівень і історія зберігаються.
 * Змінювати — лише з правом partners.assign (власник / відповідальний). Знижки тут не зберігаються:
 * вони задаються на екрані «Партнери» (номенклатура). Дані: /api/partners/contacts/<id>/. */
import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "./api";
import { Icon } from "./Icon";

type Level = { id: number; name: string; order: number; threshold_uah: number; color: string };
type Hist = { created_at: string; reason: string; old_level: string | null; new_level: string | null; turnover_uah: number; note: string; user: string };
type Data = {
  contact_id: number; is_partner: boolean; has_status: boolean; level: Level | null; since: string | null;
  turnover_uah: number; turnover_from: string; next_level: Level | null; to_next_uah: number | null;
  progress_pct: number | null; level_by_turnover: string | null; levels: Level[]; can_assign: boolean; history: Hist[];
};

const money = (n: number | null | undefined) => (n == null ? "—" : Math.round(n).toLocaleString("uk-UA") + " ₴");
const dmy = (s: string | null | undefined) => (s ? s.slice(0, 10).split("-").reverse().join(".") : "");
const errText = (e: unknown, fallback: string) => {
  const dd = (e as { data?: { detail?: string } } | null)?.data;
  return dd?.detail || fallback;
};

const BOX: CSSProperties = {
  display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: 10,
  border: "1px solid #f5d0e6", background: "#fdf2f8", fontSize: 12.5, color: "#334155",
};

export default function PartnerBlock({ contactId }: { contactId: number }) {
  const [d, setD] = useState<Data | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [histOpen, setHistOpen] = useState(false);
  const load = useCallback(() => (
    api.get<Data>(`/api/partners/contacts/${contactId}/`).then(setD).catch(() => setD(null))
  ), [contactId]);
  useEffect(() => { load(); }, [load]);

  if (!d) return null;
  if (!d.has_status && !d.can_assign) return null;

  const post = async (body: Record<string, unknown>) => {
    setBusy(true);
    setErr("");
    try {
      setD(await api.post<Data>(`/api/partners/contacts/${contactId}/`, body));
    } catch (e) {
      setErr(errText(e, "Не вдалося змінити"));
    } finally {
      setBusy(false);
    }
  };
  const toggle = () => {
    if (d.is_partner && !window.confirm("Зняти галочку «Партнер»? Знижки перестануть діяти, рівень «" + (d.level?.name || "") + "» збережеться.")) return;
    post({ action: d.is_partner ? "unmark" : "mark" });
  };
  const higher = d.level ? d.levels.filter((l) => l.order > d.level!.order) : [];
  const raise = (id: number) => {
    const lv = d.levels.find((l) => l.id === id);
    if (!lv || !window.confirm(`Підвищити до «${lv.name}»? Знизити рівень потім не можна.`)) return;
    post({ action: "raise", level_id: id });
  };

  return (
    <div style={BOX} data-testid="partner-block">
      <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 700, color: "#be185d",
        cursor: d.can_assign ? "pointer" : "not-allowed" }}
        title={d.can_assign ? "Партнерська програма: рівень і знижки з номенклатури" : "Статус партнера присвоює власник або відповідальний"}>
        <input type="checkbox" checked={d.is_partner} disabled={busy || !d.can_assign} onChange={toggle} />
        <Icon n="💼" size={14} /> Партнер
      </label>
      {d.level && (
        <span className="chip" style={{ background: d.level.color, color: "#fff", fontWeight: 700 }}>{d.level.name}</span>
      )}
      {d.has_status && !d.is_partner && <span className="muted">галочку знято — рівень збережено, знижки не діють</span>}
      {d.since && d.is_partner && <span className="muted">з {dmy(d.since)}</span>}
      <span title={`Усі оплати клієнта з ${dmy(d.turnover_from)} (без тестових воронок, мінус повернення)`}>
        Оплачено: <b>{money(d.turnover_uah)}</b>
      </span>
      {!d.has_status && d.level_by_turnover && (
        <span className="muted">за оборотом одразу отримає «{d.level_by_turnover}»</span>
      )}
      {d.is_partner && d.next_level && (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 90, height: 6, borderRadius: 3, background: "#fbcfe8", overflow: "hidden", display: "inline-block" }}>
            <span style={{ display: "block", height: "100%", width: `${d.progress_pct ?? 0}%`, background: d.next_level.color }} />
          </span>
          до «{d.next_level.name}» залишилось <b>{money(d.to_next_uah)}</b>
        </span>
      )}
      {d.is_partner && !d.next_level && <span className="muted">найвищий рівень</span>}
      {d.can_assign && d.is_partner && higher.length > 0 && (
        <select value="" disabled={busy} onChange={(e) => e.target.value && raise(Number(e.target.value))}
          style={{ height: 26, borderRadius: 6, border: "1px solid #f5d0e6", fontSize: 12 }}>
          <option value="">Підвищити вручну…</option>
          {higher.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      )}
      {d.history.length > 0 && (
        <button className="btn btn-light" style={{ height: 24, padding: "0 8px", fontSize: 11.5 }} onClick={() => setHistOpen((v) => !v)}>
          <Icon n="list" size={12} /> Історія ({d.history.length})
        </button>
      )}
      {err && <span style={{ color: "#dc2626" }}>{err}</span>}
      {histOpen && (
        <div style={{ flexBasis: "100%", marginTop: 4, borderTop: "1px solid #f5d0e6", paddingTop: 6 }}>
          {d.history.map((h, i) => (
            <div key={i} style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: "2px 0" }}>
              <span className="muted" style={{ minWidth: 80 }}>{dmy(h.created_at)}</span>
              <b>{h.reason}</b>
              <span>{h.old_level && h.old_level !== h.new_level ? `${h.old_level} → ${h.new_level}` : h.new_level}</span>
              {h.turnover_uah > 0 && <span className="muted">оборот {money(h.turnover_uah)}</span>}
              {h.note && <span className="muted">· {h.note}</span>}
              <span className="muted">· {h.user}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
