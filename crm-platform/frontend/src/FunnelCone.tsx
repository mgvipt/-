/* ============================================================================
 *  Переиспользуемые конусы воронок (Аналитика продаж + Маркетинг Meta)
 * ========================================================================== */
import { Icon } from "./Icon";

// Единая палитра-градиент воронки: от бирюзы вверху к фиолету внизу (без «тревожного» красного в середине)
export const CONE_PALETTE = ["#17a2b8", "#2298c0", "#2f8ec6", "#3d80c8", "#4d6fc6", "#5f5cbe", "#7248b0", "#8433a0"];

function shadeDown(hex: string): string {
  // затемняем цвет для нижней грани сегмента (3D)
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const r = Math.max(0, ((n >> 16) & 255) - 34), g = Math.max(0, ((n >> 8) & 255) - 34), b = Math.max(0, (n & 255) - 34);
  return `rgb(${r},${g},${b})`;
}
function fmtMoney(n: number): string {
  n = Math.round(n || 0);
  if (n >= 1000000) return (n / 1000000).toFixed(n >= 10000000 ? 0 : 1).replace(".0", "") + " млн ₴";
  if (n >= 1000) return Math.round(n / 1000) + " тыс ₴";
  return n + " ₴";
}

/* Конус воронки: 3D-сегменты, число внутри, плавное сужение к плоскому дну;
   справа — % перехода, сумма ₴ и кто вёл (бот-ИИ / менеджер) */
export function Cone({ d, t }: { d: any; t: any }) {
  if (!d || !d.stages || d.stages.length === 0) return null;
  const base = (d.stages[0]?.through) || d.entered || 1;
  const wOf = (n: number) => Math.max((n / base) * 100, 14);   // пол 14% — дно не острое
  const GC = "minmax(0,1fr) minmax(168px,250px)";
  return (
    <div style={{ maxWidth: 680, margin: "0 auto" }}>
      {(d.stages || []).map((st: any, i: number) => {
        const wTop = i === 0 ? 100 : wOf(d.stages[i - 1].through);
        const wBot = wOf(st.through);
        const clip = `polygon(${(50 - wTop / 2).toFixed(2)}% 0, ${(50 + wTop / 2).toFixed(2)}% 0, ${(50 + wBot / 2).toFixed(2)}% 100%, ${(50 - wBot / 2).toFixed(2)}% 100%)`;
        const col = CONE_PALETTE[i % CONE_PALETTE.length];
        const drop = i > 0 && st.pct_prev < 55;
        return (
          <div key={st.id} style={{ display: "grid", gridTemplateColumns: GC, columnGap: 12, alignItems: "center" }}>
            <div style={{ height: 40, position: "relative" }}>
              <div style={{ position: "absolute", inset: 0, clipPath: clip, background: `linear-gradient(180deg, ${col}, ${shadeDown(col)})`, boxShadow: "inset 0 3px 8px rgba(255,255,255,.45), inset 0 -9px 13px rgba(0,0,0,.22)" }} />
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 800, fontSize: 15, fontFamily: "ui-monospace,monospace", textShadow: "0 1px 3px rgba(0,0,0,.55)" }}>{st.through}</div>
            </div>
            <div style={{ lineHeight: 1.25, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: "#334155", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{st.name}</div>
              <div style={{ fontSize: 11, display: "flex", gap: 9, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ color: drop ? "#dc2626" : "#94a3b8", fontWeight: 700 }}>{i === 0 ? "100%" : st.pct_prev + "%"}{drop && " ⚠"}</span>
                {st.amount > 0 && <span style={{ color: "#0f766e", fontWeight: 600 }}>{fmtMoney(st.amount)}</span>}
                {(st.ai > 0 || st.man > 0) && (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                    {st.ai > 0 && <span style={{ display: "inline-flex", alignItems: "center", gap: 2, color: "#7c3aed" }}><Icon n="bot" size={12} />{st.ai}</span>}
                    {st.man > 0 && <span style={{ display: "inline-flex", alignItems: "center", gap: 2, color: "#334155" }}><Icon n="user" size={11} />{st.man}</span>}
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}
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
  const COLORS: any = { impressions: "#2563eb", clicks: "#7c3aed", messages: "#0f766e", leads: "#0284c7", test: "#f39c12", won: "#2F8F5B" };
  const top = d.stages[0]?.n || 1;
  const logMax = Math.log10(top + 1) || 1;
  const wOf = (n: number) => Math.max((Math.log10(n + 1) / logMax) * 100, 14);
  const num = (n: number) => Number(n || 0).toLocaleString("ru-RU");
  const GC = "30px 1fr minmax(150px,230px)";
  return (
    <div style={{ maxWidth: 780, margin: "0 auto" }}>
      {d.stages.map((s: any, i: number) => {
        const wTop = i === 0 ? 100 : wOf(d.stages[i - 1].n);
        const wBot = wOf(s.n);
        const clip = `polygon(${(50 - wTop / 2).toFixed(2)}% 0, ${(50 + wTop / 2).toFixed(2)}% 0, ${(50 + wBot / 2).toFixed(2)}% 100%, ${(50 - wBot / 2).toFixed(2)}% 100%)`;
        const col = COLORS[s.key] || CONE_PALETTE[i % CONE_PALETTE.length];
        const drop = i > 0 && s.pct_prev < 20;
        return (
          <div key={s.key} style={{ display: "grid", gridTemplateColumns: GC, gap: 10, alignItems: "stretch", minHeight: 50 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ width: 26, height: 26, borderRadius: 7, background: "#2f3b52", color: "#fff", fontWeight: 800, fontSize: 13, display: "grid", placeItems: "center" }}>{i + 1}</span>
            </div>
            <div style={{ position: "relative" }}>
              <div style={{ position: "absolute", inset: "1px 0", clipPath: clip, background: `linear-gradient(180deg, ${col}, ${col}bb)`, boxShadow: "inset 0 3px 7px rgba(255,255,255,.4), inset 0 -7px 11px rgba(0,0,0,.18)" }} />
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 800, fontSize: 15, textShadow: "0 1px 3px rgba(0,0,0,.45)" }}>{num(s.n)}</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "#334155", lineHeight: 1.2 }}>{s.label}</span>
              <span style={{ fontSize: 11.5, color: drop ? "#b91c1c" : "#94a3b8", fontWeight: 600 }}>{i === 0 ? t("100% показов", "100% показів") : `${s.pct_prev}% ${t("от преды.", "від попер.")}`}{drop && " ⚠"}</span>
            </div>
          </div>
        );
      })}
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
