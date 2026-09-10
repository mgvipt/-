/* ============================================================================
 *  Переиспользуемые конусы воронок (Аналитика продаж + Маркетинг Meta)
 * ========================================================================== */
import { Icon } from "./Icon";

function fmtMoney(n: number): string {
  n = Math.round(n || 0);
  if (n >= 1000000) return (n / 1000000).toFixed(n >= 10000000 ? 0 : 1).replace(".0", "") + " млн ₴";
  if (n >= 1000) return Math.round(n / 1000) + " тыс ₴";
  return n + " ₴";
}

export type FunnelVisualStep = {
  key: string | number;
  label: string;
  value: number;
  pctPrev?: number | null;
  detail?: any;
};

/* Спокойная воронка в стиле YouTube Analytics: реальные числа остаются внутри
   сегментов, а процент перехода вынесен в белую полосу между этапами. */
export function FunnelSteps({ steps, t, scale = "linear" }: {
  steps: FunnelVisualStep[];
  t: any;
  scale?: "linear" | "log";
}) {
  if (!steps.length) return null;
  const top = Math.max(Number(steps[0]?.value || 0), 1);
  const ratio = (value: number) => {
    if (scale === "log") return Math.log10(Math.max(value, 0) + 1) / Math.log10(top + 1);
    return Math.max(value, 0) / top;
  };
  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "2px 0" }}>
      {steps.map((step, i) => {
        const width = Math.max(Math.min(ratio(step.value) * 100, 100), 28);
        return <div key={step.key}>
          {i > 0 && (
            <div style={{ minHeight: 34, display: "flex", alignItems: "center", justifyContent: "center", gap: 7, color: "#64748b", fontSize: 12, fontWeight: 700 }}>
              <span aria-hidden="true" style={{ color: "#94a3b8" }}>↓</span>
              {step.pctPrev == null
                ? t("нет базы для расчёта", "немає бази для розрахунку")
                : `${step.pctPrev}% ${t("от предыдущего этапа", "від попереднього етапу")}`}
            </div>
          )}
          <div style={{ width: `${width}%`, minWidth: "min(220px, 100%)", margin: "0 auto", background: "linear-gradient(180deg,#eef1f5,#d9dee5)", border: "1px solid #c8ced7", clipPath: "polygon(3% 0,97% 0,94% 100%,6% 100%)", color: "#172033", textAlign: "center", padding: "12px 24px 13px", boxSizing: "border-box" }}>
            <div style={{ fontSize: 12.5, fontWeight: 700, lineHeight: 1.25, overflowWrap: "anywhere" }}>{step.label}</div>
            <div style={{ fontSize: 28, fontWeight: 850, lineHeight: 1.05, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>{Number(step.value || 0).toLocaleString("ru-RU")}</div>
            {step.detail && <div style={{ fontSize: 11, color: "#526071", marginTop: 5, lineHeight: 1.3 }}>{step.detail}</div>}
          </div>
        </div>;
      })}
    </div>
  );
}

/* Конус воронки: 3D-сегменты, число внутри, плавное сужение к плоскому дну;
   справа — % перехода, сумма ₴ и кто вёл (бот-ИИ / менеджер) */
export function Cone({ d, t }: { d: any; t: any }) {
  if (!d || !d.stages || d.stages.length === 0) return null;
  return (
    <div style={{ maxWidth: 680, margin: "0 auto" }}>
      <FunnelSteps steps={(d.stages || []).map((st: any, i: number) => ({
        key: st.id,
        label: st.name,
        value: st.through,
        pctPrev: i === 0 ? undefined : st.pct_prev,
        detail: <span style={{ display: "inline-flex", justifyContent: "center", gap: 10, flexWrap: "wrap" }}>
          {st.amount > 0 && <span style={{ color: "#0f766e", fontWeight: 700 }}>{fmtMoney(st.amount)}</span>}
          {st.ai > 0 && <span style={{ display: "inline-flex", alignItems: "center", gap: 3, color: "#7c3aed" }}><Icon n="bot" size={12} />{st.ai}</span>}
          {st.man > 0 && <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><Icon n="user" size={11} />{st.man}</span>}
        </span>,
      }))} t={t} />
      <div style={{ display: "flex", gap: 16, marginTop: 10, fontSize: 12, flexWrap: "wrap" }}>
        <span style={{ color: "#dc2626", fontWeight: 700 }}>❌ {t("Потеряно (отказы)", "Втрачено (відмови)")}: {d.lost.count}{d.lost.amount > 0 ? " · " + fmtMoney(d.lost.amount) : ""}</span>
        {d.won.count > 0 && <span style={{ color: "#16a34a", fontWeight: 700 }}>✅ {d.won.label || t("Продано", "Продано")}: {d.won.count}{d.won.amount > 0 ? " · " + fmtMoney(d.won.amount) : ""}</span>}
      </div>
    </div>
  );
}

/* Конус воронки Меты (stages: key/label/n/pct_prev; ширина по лог-шкале — показы огромны) */
export function MetaCone({ d, t }: { d: any; t: any }) {
  if (!d || !d.stages || d.stages.length === 0) return null;
  const num = (n: number) => Number(n || 0).toLocaleString("ru-RU");
  return (
    <div style={{ maxWidth: 780, margin: "0 auto" }}>
      <FunnelSteps steps={d.stages.map((s: any, i: number) => ({
        key: s.key,
        label: s.label,
        value: s.n,
        pctPrev: i === 0 ? undefined : s.pct_prev,
      }))} t={t} scale="log" />
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 12, paddingTop: 12, borderTop: "1px solid #eef2f7", fontSize: 13, justifyContent: "center" }}>
        <span className="muted">{t("Расход", "Витрати")}: <b style={{ color: "#0f172a" }}>{num(Math.round(d.spend_uah))} ₴</b></span>
        <span className="muted">{t("Цена лида", "Ціна ліда")}: <b style={{ color: "#0f172a" }}>{d.cost_per_lead != null ? num(Math.round(d.cost_per_lead)) + " ₴" : "—"}</b></span>
        <span className="muted">{t("Цена продажи", "Ціна продажу")}: <b style={{ color: "#0f172a" }}>{d.cost_per_sale != null ? num(Math.round(d.cost_per_sale)) + " ₴" : "—"}</b></span>
        <span className="muted">{t("Выручка", "Виручка")}: <b style={{ color: d.revenue != null ? "#166534" : "#94a3b8" }}>{d.revenue != null ? num(Math.round(d.revenue)) + " ₴" : "—"}</b></span>
        <span className="muted">ROAS: <b style={{ color: (d.roas || 0) >= 1 ? "#166534" : "#b91c1c" }}>{d.roas != null ? d.roas : "—"}</b></span>
      </div>
    </div>
  );
}
