/* ─── Економіка угоди (14.09.2026) ──────────────────────────────────────────
 * Виручка − собівартість − доставка НП (якщо платимо ми) − комісія оплати − пакування
 * − роботи майстра − повернення = маржа ₴ і %.
 * Біля кожного рядка: «факт» (документ: журнал, НП, склад) або «оцінка» (норма / ставка).
 * Показується лише з правом deal.economics.view (14.09; бекенд теж перевіряє). Власник: «Перерахувати» і норми.
 * Матеріали пакування — % фонду «Упаковка (матеріали)» з Фінмоделі; норма ₴ за відправлення — лише запасна.
 */
import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

type Kind = "fact" | "estimate" | "mixed" | "none";
interface Line { key: string; amount: number; kind: Kind; note_uk: string; note_ru: string }
interface Flag { code: string; uk: string; ru: string }
interface Econ {
  deal_id: number; revenue: number; margin: number; margin_pct: number; is_estimate: boolean;
  lines: Line[]; flags: Flag[]; locked: boolean; saved: boolean; computed_at: string | null;
  can_recompute: boolean; can_edit_settings: boolean;
}
interface Norms {
  pack_material_per_shipment: number; liqpay_rate_pct: number; novapay_rate_pct: number;
  pack_material_fund_pct?: number | null; pack_material_fund_name?: string; [k: string]: unknown;
}

const LABEL: Record<string, [string, string]> = {
  revenue: ["Выручка", "Виручка"],
  cogs: ["Себестоимость товара", "Собівартість товару"],
  delivery: ["Доставка НП (платим мы)", "Доставка НП (платимо ми)"],
  commission: ["Комиссия оплаты", "Комісія оплати"],
  packaging: ["Упаковка", "Пакування"],
  master_works: ["Работы мастера", "Роботи майстра"],
  returns: ["Возвраты", "Повернення"],
};
const KIND: Record<Kind, { ru: string; uk: string; bg: string; fg: string }> = {
  fact: { ru: "факт", uk: "факт", bg: "#ecfdf5", fg: "#047857" },
  estimate: { ru: "оценка", uk: "оцінка", bg: "#fffbeb", fg: "#b45309" },
  mixed: { ru: "факт+оценка", uk: "факт+оцінка", bg: "#fffbeb", fg: "#b45309" },
  none: { ru: "—", uk: "—", bg: "#f1f5f9", fg: "#94a3b8" },
};
const money = (n: number) => Number(n || 0).toLocaleString("ru", { maximumFractionDigits: 2 });
const badge: CSSProperties = { fontSize: 10.5, padding: "1px 6px", borderRadius: 6, fontWeight: 600, whiteSpace: "nowrap" };
const numInput: CSSProperties = { width: 70, padding: "3px 6px", border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 12 };

export default function DealEconomicsBlock({ dealId, refreshKey }: { dealId: number; refreshKey?: string }) {
  const { t } = useLang();
  const [d, setD] = useState<Econ | null>(null);
  const [hidden, setHidden] = useState(false);
  const [busy, setBusy] = useState(false);
  const [normsOpen, setNormsOpen] = useState(false);
  const [norms, setNorms] = useState<Norms | null>(null);
  const [normsMsg, setNormsMsg] = useState("");

  const load = (recompute = false) => {
    setBusy(true);
    api.get<Econ>(`/api/deal-economics/${dealId}/${recompute ? "?recompute=1" : ""}`)
      .then((r) => { setD(r); setHidden(false); })
      .catch(() => setHidden(true))
      .finally(() => setBusy(false));
  };
  useEffect(() => { load(false); }, [dealId, refreshKey]);

  const toggleNorms = () => {
    if (normsOpen) { setNormsOpen(false); return; }
    api.get<Norms>("/api/deal-economics/settings/")
      .then((n) => { setNorms(n); setNormsOpen(true); setNormsMsg(""); })
      .catch(() => setNormsMsg(t("Не удалось загрузить нормы", "Не вдалося завантажити норми")));
  };
  const saveNorms = () => {
    if (!norms) return;
    api.patch<Norms>("/api/deal-economics/settings/", {
      pack_material_per_shipment: norms.pack_material_per_shipment,
      liqpay_rate_pct: norms.liqpay_rate_pct,
      novapay_rate_pct: norms.novapay_rate_pct,
    })
      .then((n) => { setNorms(n); setNormsMsg(t("Сохранено", "Збережено")); load(false); })
      .catch((e: any) => setNormsMsg(e?.data?.detail || e?.response?.data?.detail || t("Ошибка", "Помилка")));
  };

  if (hidden || !d) return null;

  const renderLine = (l: Line) => {
    const k = KIND[l.kind] || KIND.none;
    const isRev = l.key === "revenue";
    const note = t(l.note_ru, l.note_uk);
    return (
      <div key={l.key} style={{ marginBottom: 3 }}>
        <div className="row" title={note} style={{ alignItems: "center", gap: 6 }}>
          <span className="muted">{isRev ? "" : "− "}{t(LABEL[l.key]?.[0] || l.key, LABEL[l.key]?.[1] || l.key)}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap" }}>
            <b style={{ color: isRev ? undefined : (l.amount ? "#9a3412" : "#94a3b8") }}>{!isRev && l.amount ? "−" : ""}{money(l.amount)} ₴</b>
            <span style={{ ...badge, background: k.bg, color: k.fg }}>{t(k.ru, k.uk)}</span>
          </span>
        </div>
        {!isRev && l.amount !== 0 && note && <div className="muted" style={{ fontSize: 11, lineHeight: 1.3, marginTop: -1 }}>{note}</div>}
      </div>
    );
  };

  const estNames = d.lines
    .filter((l) => l.key !== "revenue" && (l.kind === "estimate" || l.kind === "mixed") && l.amount !== 0)
    .map((l) => t(LABEL[l.key]?.[0] || l.key, LABEL[l.key]?.[1] || l.key).toLowerCase());
  const good = d.margin > 0;

  return (
    <div className="panel">
      <div className="label" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
        <span>{t("Экономика сделки", "Економіка угоди")}</span>
        <span className="muted" style={{ fontSize: 11, fontWeight: 400 }}>
          {d.locked ? t("месяц закрыт · ", "місяць закрито · ") : ""}{t("факт / оценка", "факт / оцінка")}
        </span>
      </div>
      {d.lines.map(renderLine)}
      <div className="row" style={{ borderTop: "2px solid #e2e8f0", paddingTop: 6, marginTop: 4, fontSize: 15 }}>
        <span>= {t("Маржа", "Маржа")}</span>
        <b style={{ color: good ? "#166534" : "#dc2626" }}>{money(d.margin)} ₴ · {Number(d.margin_pct || 0).toLocaleString("ru", { maximumFractionDigits: 1 })}%</b>
      </div>
      {d.is_estimate && estNames.length > 0 && (
        <div style={{ fontSize: 11, color: "#b45309", marginTop: 2 }}>{t("оценка: ", "оцінка: ")}{estNames.join(", ")}</div>
      )}
      {d.flags.length > 0 && (
        <div style={{ marginTop: 6, background: "#fffbeb", color: "#92400e", padding: "6px 8px", borderRadius: 8, fontSize: 11.5, lineHeight: 1.35 }}>
          <b>{t("Проверить:", "Перевірити:")}</b>
          {d.flags.map((f, i) => <div key={f.code + i}>• {t(f.ru, f.uk)}</div>)}
        </div>
      )}
      {(d.can_recompute || d.can_edit_settings) && (
        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          {d.can_recompute && (
            <button className="btn btn-light" style={{ padding: "2px 8px", fontSize: 11 }} disabled={busy} onClick={() => load(true)}
              title={t("Пересчитать и сохранить (для ЗП и отчётов)", "Перерахувати і зберегти (для ЗП і звітів)")}>
              {busy ? "…" : t("Пересчитать", "Перерахувати")}
            </button>
          )}
          {d.can_edit_settings && (
            <button className="btn btn-light" style={{ padding: "2px 8px", fontSize: 11 }} onClick={toggleNorms}
              title={t("Нормы для оценок, пока нет факта", "Норми для оцінок, поки немає факту")}>
              {t("Нормы", "Норми")}
            </button>
          )}
        </div>
      )}
      {normsOpen && norms && (
        <div style={{ marginTop: 6, fontSize: 12, display: "grid", gap: 4 }}>
          {norms.pack_material_fund_pct != null ? (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}
              title={t("Меняется в Финансы → Финмодель → фонды выручки", "Змінюється у Фінанси → Фінмодель → фонди виручки")}>
              <span className="muted">{t("Материалы упаковки", "Матеріали пакування")}</span>
              <b style={{ fontSize: 12, textAlign: "right" }}>{Number(norms.pack_material_fund_pct).toLocaleString("ru", { maximumFractionDigits: 2 })}% {t("фонда", "фонду")} «{norms.pack_material_fund_name}» × {t("выручка товаров", "виручка товарів")}</b>
            </div>
          ) : (
          <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
            <span className="muted">{t("Материалы упаковки, ₴ за отправку", "Матеріали пакування, ₴ за відправлення")}</span>
            <input style={numInput} type="number" step="0.5" value={String(norms.pack_material_per_shipment)}
              onChange={(e) => setNorms({ ...norms, pack_material_per_shipment: Number(e.target.value) })} />
          </label>
          )}
          <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
            <span className="muted">LiqPay, %</span>
            <input style={numInput} type="number" step="0.01" value={String(norms.liqpay_rate_pct)}
              onChange={(e) => setNorms({ ...norms, liqpay_rate_pct: Number(e.target.value) })} />
          </label>
          <label style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
            <span className="muted">{t("НоваПей, %", "НоваПей, %")}</span>
            <input style={numInput} type="number" step="0.01" value={String(norms.novapay_rate_pct)}
              onChange={(e) => setNorms({ ...norms, novapay_rate_pct: Number(e.target.value) })} />
          </label>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <button className="btn btn-primary" style={{ padding: "2px 10px", fontSize: 11 }} onClick={saveNorms}>{t("Сохранить", "Зберегти")}</button>
            {normsMsg && <span className="muted" style={{ fontSize: 11 }}>{normsMsg}</span>}
          </div>
        </div>
      )}
    </div>
  );
}
