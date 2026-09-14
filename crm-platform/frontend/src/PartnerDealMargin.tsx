/* Угода клієнта-партнера: скільки маржі лишається в кожній позиції (14.09.2026, крок 4).
 * ЛИШЕ ПІДКАЗКА — ціни і знижки в угоді не змінюються, нічого не блокується.
 * Показується ОКРЕМИМ блоком під таблицею товарів (саму таблицю не чіпаємо). Для не-партнерів — нічого.
 * Цифри маржі — лише з правом «Бачити собівартість». Дані: /api/partners/deals/<id>/margin/. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";

type Row = {
  item_id: number; name: string; quantity: number; retail_line: number; total: number;
  discount_fact_pct: number | null; recommended_pct: number | null; recommended_note: string;
  max_pct: number | null; no_cost: boolean; below_min: boolean; left_pp: number | null;
};
type Data = {
  deal_id: number; is_partner: boolean; level?: { id: number; name: string; color: string };
  min_margin_pp?: number; can_cost?: boolean; rows?: Row[]; n_below?: number; auto_apply?: boolean;
};

const pct = (n: number | null | undefined) => (n == null ? "—" : `${Math.round(n * 10) / 10}%`);

export default function PartnerDealMargin({ dealId, reloadKey }: { dealId: number; reloadKey?: string }) {
  const [d, setD] = useState<Data | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let alive = true;
    api.get<Data>(`/api/partners/deals/${dealId}/margin/`).then((r) => { if (alive) setD(r); }).catch(() => { if (alive) setD(null); });
    return () => { alive = false; };
  }, [dealId, reloadKey]);

  if (!d || !d.is_partner || !d.level) return null;
  const rows = d.rows || [];
  const below = d.n_below || 0;
  const showOpen = open || below > 0;
  return (
    <div data-testid="partner-deal-margin" style={{ marginTop: 12, border: "1px solid " + (below ? "#fca5a5" : "#f5d0e6"),
      background: below ? "#fef2f2" : "#fdf2f8", borderRadius: 10, padding: "8px 12px", fontSize: 12.5 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Icon n="💼" size={14} />
        <b>Партнер</b>
        <span className="chip" style={{ background: d.level.color, color: "#fff", fontWeight: 700 }}>{d.level.name}</span>
        {below > 0
          ? <span style={{ color: "#b91c1c", fontWeight: 700 }}><Icon n="warn" size={13} /> {below} поз. — після знижки маржі менше {d.min_margin_pp} п.п.</span>
          : <span className="muted">усі позиції в межах мінімальної маржі {d.min_margin_pp} п.п.</span>}
        <span className="muted">· лише підказка, угода не змінюється</span>
        <button className="btn btn-light" style={{ marginLeft: "auto", height: 24, padding: "0 8px", fontSize: 11.5 }}
          onClick={() => setOpen((v) => !v)}>{showOpen ? "Сховати" : "Показати позиції"}</button>
      </div>
      {showOpen && rows.length > 0 && (
        <div style={{ marginTop: 6, overflowX: "auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(160px,1fr) 90px 110px 120px", gap: "2px 10px",
            minWidth: 520, alignItems: "center" }}>
            <span className="muted">Товар</span>
            <span className="muted">Знижка факт</span>
            <span className="muted" title="Скільки дає рівень партнера за номенклатурою">За рівнем</span>
            <span className="muted" title="Маржа після знижки, п.п. від роздрібної ціни">Лишається маржі</span>
            {rows.map((r) => (
              <Row key={r.item_id} r={r} canCost={!!d.can_cost} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ r, canCost }: { r: Row; canCost: boolean }) {
  const red = r.below_min ? "#b91c1c" : undefined;
  const left = r.no_cost ? "немає собівартості" : canCost ? `${r.left_pp} п.п.` : r.below_min ? "нижче мінімуму" : "в межах";
  return (
    <>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: red }} title={r.name}>{r.name}</span>
      <span style={{ color: red }}>{pct(r.discount_fact_pct)}</span>
      <span title={r.recommended_note || ""}>{pct(r.recommended_pct)}{r.max_pct != null && canCost ? <span className="muted"> (макс. {r.max_pct}%)</span> : null}</span>
      <span style={{ color: red || (r.no_cost ? "#94a3b8" : "#166534"), fontWeight: r.below_min ? 700 : 500 }}>{left}</span>
    </>
  );
}
