/* ============================================================================
 *  Переиспользуемые конусы воронок (Аналитика продаж + Маркетинг Meta)
 * ========================================================================== */

export const CONE_PALETTE = ["#17a2b8", "#7cb342", "#e5533c", "#f39c12", "#5c6bc0", "#26a69a", "#8e44ad", "#c0392b"];

/* Конус воронки по данным sales-funnel (stages: through/ai/man/pct_prev; lost/won) */
export function Cone({ d, t }: { d: any; t: any }) {
  if (!d || !d.stages || d.stages.length === 0) return null;
  const base = (d.stages[0]?.through) || d.entered || 1;
  const wOf = (n: number) => Math.max((n / base) * 100, 15);
  const GC = "30px 1fr minmax(140px,230px)";
  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      {(d.stages || []).map((st: any, i: number) => {
        const wTop = i === 0 ? 100 : wOf(d.stages[i - 1].through);
        const wBot = wOf(st.through);
        const clip = `polygon(${(50 - wTop / 2).toFixed(2)}% 0, ${(50 + wTop / 2).toFixed(2)}% 0, ${(50 + wBot / 2).toFixed(2)}% 100%, ${(50 - wBot / 2).toFixed(2)}% 100%)`;
        const col = CONE_PALETTE[i % CONE_PALETTE.length];
        const drop = i > 0 && st.pct_prev < 55;
        return (
          <div key={st.id} style={{ display: "grid", gridTemplateColumns: GC, gap: 10, alignItems: "stretch", minHeight: 52 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ width: 26, height: 26, borderRadius: 7, background: "#2f3b52", color: "#fff", fontWeight: 800, fontSize: 13, display: "grid", placeItems: "center" }}>{i + 1}</span>
            </div>
            <div style={{ position: "relative" }}>
              <div style={{ position: "absolute", inset: "1px 0", clipPath: clip, background: `linear-gradient(180deg, ${col}, ${col}bb)`, boxShadow: "inset 0 3px 7px rgba(255,255,255,.4), inset 0 -7px 11px rgba(0,0,0,.18)" }} />
              <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, color: "#fff", fontWeight: 800, fontSize: 16, textShadow: "0 1px 3px rgba(0,0,0,.45)" }}>
                {st.through}
                {(st.man > 0 || st.ai > 0) && <span style={{ fontSize: 11, fontWeight: 600, opacity: .95 }}>{st.man > 0 ? `🤖${st.ai} 👤${st.man}` : `🤖${st.ai}`}</span>}
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "#334155", lineHeight: 1.2 }}>{st.name}</span>
              <span style={{ fontSize: 11.5, color: drop ? "#b91c1c" : "#94a3b8", fontWeight: 600 }}>{i === 0 ? t("вход · 100%", "вхід · 100%") : `${st.pct_prev}% ${t("от преды.", "від попер.")}`}{drop && " ⚠"}</span>
            </div>
          </div>
        );
      })}
      <div style={{ display: "grid", gridTemplateColumns: GC, gap: 10, alignItems: "center", marginTop: 10 }}>
        <div />
        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ flex: 1, height: 32, borderRadius: 8, background: "#fef2f2", border: "1px solid #fca5a5", display: "flex", alignItems: "center", justifyContent: "center", color: "#b91c1c", fontWeight: 700, fontSize: 12.5 }}>❌ {t("Потеряно", "Втрачено")}: {d.lost.count} · {d.lost.pct}%</div>
          {d.won.count > 0 && <div style={{ flex: 1, height: 32, borderRadius: 8, background: "#f0fdf4", border: "1px solid #86efac", display: "flex", alignItems: "center", justifyContent: "center", color: "#166534", fontWeight: 700, fontSize: 12.5 }}>✅ {t("Продано", "Продано")}: {d.won.count} · {d.won.pct}%</div>}
        </div>
        <div />
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
        <span className="muted">{t("Выручка", "Виручка")}: <b style={{ color: "#166534" }}>{num(Math.round(d.revenue))} ₴</b></span>
        <span className="muted">ROAS: <b style={{ color: (d.roas || 0) >= 1 ? "#166534" : "#b91c1c" }}>{d.roas != null ? d.roas : "—"}</b></span>
      </div>
    </div>
  );
}
