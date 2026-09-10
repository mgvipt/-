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

/* Статичная воронка (Олег, 10.09.2026): форма ПОСТОЯННАЯ — плавно сужается от широкого
   верха к узкому низу; ширина этапа зависит только от его места, а НЕ от числа.
   Слева — название этапа, внутри — число и детали, справа — % от предыдущего этапа.
   Параметр scale оставлен для совместимости вызовов (на форму больше не влияет). */
const FUNNEL_COLS = "minmax(90px, 210px) minmax(0, 1fr) minmax(56px, 150px)";
const FUNNEL_BOTTOM = 30;   // ширина нижнего края, % от верхнего
const FUNNEL_CURVE = 1.35;  // изгиб боков (1 = прямые)
const funnelWidth = (y: number) => FUNNEL_BOTTOM + (100 - FUNNEL_BOTTOM) * Math.pow(1 - y, FUNNEL_CURVE);
// спокойный серый: сверху светлее (#eef1f5), к низу чуть темнее (#c3ccd7)
const funnelShade = (p: number) => {
  const a = [0xee, 0xf1, 0xf5], b = [0xc3, 0xcc, 0xd7];
  return "#" + a.map((v, k) => Math.round(v + (b[k] - v) * p).toString(16).padStart(2, "0")).join("");
};
// «В колір воронки» (Олег, 10.09): цвет воронки подмешивается к белому — сверху светлее, к низу насыщеннее
const mixHex = (hex: string, share: number) => {
  const h = hex.replace("#", ""), c = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return "#" + c.map((v) => Math.round(255 + (v - 255) * share).toString(16).padStart(2, "0")).join("");
};
// Цвета — те же, что у заголовков «Ліди / Тест-набір / Основний продукт» в Аналітиці; прочие воронки остаются серыми
export function funnelColor(d: any): string | undefined {
  const n = String(d?.funnel || "").toLowerCase();
  if (d?.is_lead || /лід|лид/.test(n)) return "#2E6FB0";
  if (/набір|набор/.test(n)) return "#B67A12";
  if (/основн/.test(n)) return "#2F8F5B";
  return undefined;
}

export function FunnelSteps({ steps, t, color }: {
  steps: FunnelVisualStep[];
  t: any;
  scale?: "linear" | "log";
  color?: string;
}) {
  if (!steps.length) return null;
  const n = steps.length;
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "2px 0", display: "grid", gap: 2 }}>
      {color && <style>{".fs-dk,.fs-dk *{color:#fff !important}"}</style>}
      <div style={{ display: "grid", gridTemplateColumns: FUNNEL_COLS, gap: 14, paddingBottom: 6, fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: ".06em" }}>
        <span style={{ textAlign: "right" }}>{t("Этап", "Етап")}</span>
        <span style={{ textAlign: "center" }}>{t("Прошло через этап", "Пройшло через етап")}</span>
        <span>{t("% от предыдущего", "% від попереднього")}</span>
      </div>
      {steps.map((step, i) => {
        const top = funnelWidth(i / n), bottom = funnelWidth((i + 1) / n);
        const p = n > 1 ? i / (n - 1) : 0, share = 0.16 + 0.84 * p, dark = !!color && share >= 0.58;
        const bg = color ? mixHex(color, share) : funnelShade(p);
        const clip = `polygon(${(50 - top / 2).toFixed(2)}% 0, ${(50 + top / 2).toFixed(2)}% 0, ${(50 + bottom / 2).toFixed(2)}% 100%, ${(50 - bottom / 2).toFixed(2)}% 100%)`;
        return <div key={step.key} style={{ display: "grid", gridTemplateColumns: FUNNEL_COLS, gap: 14, alignItems: "center" }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, lineHeight: 1.25, color: "#172033", textAlign: "right", overflowWrap: "anywhere" }}>{step.label}</div>
          <div className={dark ? "fs-dk" : undefined} style={{ minHeight: 54, clipPath: clip, background: bg, color: dark ? "#fff" : "#172033", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", padding: "6px 0", boxSizing: "border-box" }}>
            <div style={{ fontSize: 22, fontWeight: 850, lineHeight: 1.05, fontVariantNumeric: "tabular-nums" }}>{Number(step.value || 0).toLocaleString("ru-RU")}</div>
            {step.detail && <div style={{ fontSize: 11, color: "#526071", marginTop: 3, lineHeight: 1.3, maxWidth: "100%" }}>{step.detail}</div>}
          </div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b" }}>
            {i > 0 && (step.pctPrev == null
              ? <span style={{ fontWeight: 600, color: "#94a3b8" }}>{t("нет базы для расчёта", "немає бази для розрахунку")}</span>
              : <><span aria-hidden="true" style={{ color: "#94a3b8" }}>↓</span> {step.pctPrev}%</>)}
          </div>
        </div>;
      })}
    </div>
  );
}

/* Конус воронки: 3D-сегменты, число внутри, плавное сужение к плоскому дну;
   справа — % перехода, сумма ₴ и кто вёл (бот-ИИ / менеджер) */
export function Cone({ d, t, color }: { d: any; t: any; color?: string }) {
  if (!d || !d.stages || d.stages.length === 0) return null;
  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
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
      }))} t={t} color={color || funnelColor(d)} />
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
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
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
