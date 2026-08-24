/* Аналитика работы менеджеров: дневной срез воронки + действия в чатах + недельный вердикт AI-РОП. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

export default function ManagerAnalytics() {
  const { t } = useLang();
  const iso = (dt: Date) => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
  const [fd, setFd] = useState<any>(null);
  const [funnelId, setFunnelId] = useState<string>("");
  const [from, setFrom] = useState<string>(() => { const d = new Date(); d.setDate(d.getDate() - 13); return iso(d); });
  const [to, setTo] = useState<string>(() => iso(new Date()));
  // действия менеджеров
  const [acts, setActs] = useState<any>(null);
  // недельный вердикт
  const [rev, setRev] = useState<any>(null);
  const [revLoad, setRevLoad] = useState(false);

  useEffect(() => {
    const q = `?from=${from}&to=${to}` + (funnelId ? `&funnel=${funnelId}` : "");
    api.get<any>("/api/analytics/funnel-daily/" + q).then(setFd).catch(() => {});
    api.get<any>(`/api/analytics/manager-actions/?from=${from}&to=${to}`).then(setActs).catch(() => setActs(null));
  }, [from, to, funnelId]);

  useEffect(() => { api.get<any>("/api/analytics/weekly-review/").then(setRev).catch(() => setRev(null)); }, []);
  function runReview() {
    setRevLoad(true);
    api.post<any>("/api/analytics/weekly-review/", {}).then((r) => { setRev(r); setRevLoad(false); }).catch(() => setRevLoad(false));
  }

  const th: any = { textAlign: "left", padding: "7px 9px", fontSize: 12, color: "#64748b", borderBottom: "2px solid #eef2f7", whiteSpace: "nowrap" };
  const td: any = { padding: "6px 9px", fontSize: 13, borderBottom: "1px solid #f1f5f9", verticalAlign: "middle" };
  const dateSt: any = { height: 32, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 13 };
  const selSt: any = { height: 32, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13, background: "#fff" };

  return (
    <div style={{ height: "100%", overflowY: "auto", boxSizing: "border-box", padding: 16 }}>
      <div style={{ maxWidth: 1200 }}>
        <h2 style={{ fontSize: 22, display: "flex", alignItems: "center", gap: 8, margin: "0 0 12px" }}><Icon n="chart" size={20} /> {t("Аналитика менеджеров", "Аналітика менеджерів")}</h2>

        {/* фильтры периода */}
        <div style={{ display: "flex", gap: 8, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: 12 }}>{t("Период:", "Період:")}</span>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={dateSt} />
          <span className="muted">—</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={dateSt} />
          {fd && <select value={funnelId} onChange={(e) => setFunnelId(e.target.value)} style={selSt}>
            {(fd.funnels || []).map((f: any) => <option key={f.id} value={f.id}>{f.name}{f.is_lead ? " ★" : ""}</option>)}
          </select>}
        </div>

        {/* ── БЛОК 1: дневной срез воронки ── */}
        <div className="panel" style={{ marginBottom: 18 }}>
          <div className="label" style={{ marginBottom: 4 }}>{t("Воронка по дням", "Воронка по днях")}{fd ? ` — ${fd.funnel}` : ""}</div>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 10, lineHeight: 1.5 }}>
            {t("«Вошло» — сколько лидов зашло в этот день. По статусам — сколько лидов ДОШЛО до этого статуса в этот день (лид мог за день пройти несколько статусов; вернувшийся из молчания тоже засчитается в тот день, когда двинулся).", "«Зайшло» — скільки лідів увійшло цього дня. По статусах — скільки лідів ДІЙШЛО до цього статусу цього дня.")}
          </div>
          {!fd ? <div className="muted">…</div> : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 700 }}>
                <thead><tr>
                  <th style={th}>{t("День", "День")}</th>
                  <th style={{ ...th, textAlign: "right", color: "#0f172a", fontWeight: 700 }}>{t("Вошло", "Зайшло")}</th>
                  {(fd.stages || []).map((s: any) => <th key={s.id} style={{ ...th, textAlign: "right", color: s.is_won ? "#166534" : s.is_lost ? "#b91c1c" : "#64748b" }}>{s.name}</th>)}
                </tr></thead>
                <tbody>{(fd.days || []).map((d: any) => (
                  <tr key={d.d}>
                    <td style={{ ...td, whiteSpace: "nowrap", fontWeight: 600 }}>{d.d}</td>
                    <td style={{ ...td, textAlign: "right", fontWeight: 800, color: "#0f172a" }}>{d.entered || 0}</td>
                    {(d.stages || []).map((s: any) => <td key={s.stage_id} style={{ ...td, textAlign: "right", color: s.reached ? "#0f172a" : "#cbd5e1", fontWeight: s.reached ? 600 : 400 }}>{s.reached || "·"}</td>)}
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── БЛОК 2: действия менеджеров в чатах ── */}
        <div className="panel" style={{ marginBottom: 18 }}>
          <div className="label" style={{ marginBottom: 4 }}>{t("Действия менеджеров в чатах", "Дії менеджерів у чатах")}</div>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>{t("За выбранный период: сколько ответил, взял в работу, закрыл (с причиной), дожал, вернул из игнора.", "За обраний період: скільки відповів, узяв у роботу, закрив, дожав, повернув з ігнору.")}</div>
          {!acts ? <div className="muted">…</div> : (acts.rows || []).length === 0 ? <div className="muted" style={{ fontSize: 12.5 }}>{t("Нет данных за период", "Немає даних за період")}</div> : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
                <thead><tr>
                  <th style={th}>{t("Менеджер", "Менеджер")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{t("Ответов", "Відповідей")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{t("Взял в работу", "Узяв у роботу")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{t("Дожимов", "Дожимів")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{t("Закрыл", "Закрив")}</th>
                </tr></thead>
                <tbody>{(acts.rows || []).map((r: any) => (
                  <tr key={r.user_id}>
                    <td style={{ ...td, fontWeight: 600 }}>{r.name}</td>
                    <td style={{ ...td, textAlign: "right" }}>{r.replies || 0}</td>
                    <td style={{ ...td, textAlign: "right" }}>{r.taken || 0}</td>
                    <td style={{ ...td, textAlign: "right", color: "#c2410c", fontWeight: 600 }}>{r.followups || 0}</td>
                    <td style={{ ...td, textAlign: "right" }}>{r.closed || 0}</td>
                  </tr>
                ))}</tbody>
              </table>
              {typeof acts.reactivations === "number" && acts.reactivations > 0 && (
                <div style={{ marginTop: 10, fontSize: 12.5, color: "#166534", fontWeight: 600 }}>
                  <Icon n="refresh" size={13} /> {t("Вернулись из игнора (команда):", "Повернулись з ігнору (команда):")} <b>{acts.reactivations}</b>
                </div>
              )}
              {acts.close_reasons && acts.close_reasons.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div className="muted" style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>{t("Причины закрытия (почему теряем):", "Причини закриття (чому втрачаємо):")}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {acts.close_reasons.map((c: any) => <span key={c.reason} style={{ fontSize: 12, background: "#fff1f2", color: "#9f1239", border: "1px solid #fecdd3", borderRadius: 20, padding: "3px 10px" }}>{c.reason} · <b>{c.count}</b></span>)}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── БЛОК 3: недельный вердикт AI-РОП (только руководителю) ── */}
        <div className="panel" style={{ marginBottom: 30, border: "2px solid #ddd6fe" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
            <div className="label" style={{ margin: 0 }}>{t("Разбор недели от AI-РОП", "Розбір тижня від AI-РОП")}</div>
            <button className="btn btn-primary" style={{ fontSize: 13 }} onClick={runReview} disabled={revLoad}>{revLoad ? t("AI анализирует…", "AI аналізує…") : <><Icon n="bulb" size={14} /> {t("Сделать разбор", "Зробити розбір")}</>}</button>
            {rev && rev.created_at && <span className="muted" style={{ fontSize: 11.5 }}>{t("последний:", "останній:")} {rev.created_at} · {rev.period || ""}</span>}
          </div>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>{t("AI-РОП разбирает обработанные диалоги за неделю и даёт вердикт: кто теряет лиды, групповые ошибки. Дёшево по токенам (раз в неделю).", "AI-РОП розбирає оброблені діалоги за тиждень і дає вердикт.")}</div>
          {rev && rev.summary && <div style={{ background: "#f5f3ff", borderRadius: 10, padding: "10px 14px", fontSize: 13.5, lineHeight: 1.55, marginBottom: 10, whiteSpace: "pre-wrap" }}>{rev.summary}</div>}
          {rev && (rev.managers || []).length > 0 && (rev.managers || []).map((m: any, i: number) => (
            <div key={i} style={{ borderTop: "1px solid #eef2f7", padding: "8px 0" }}>
              <div style={{ fontWeight: 700, fontSize: 13.5 }}>{m.name} {m.score != null && <span className="muted" style={{ fontWeight: 400 }}>· {m.score}/100</span>}</div>
              {m.verdict && <div style={{ fontSize: 12.5, color: "#334155", lineHeight: 1.5, marginTop: 2, whiteSpace: "pre-wrap" }}>{m.verdict}</div>}
            </div>
          ))}
          {rev && rev.error && <div style={{ color: "#b91c1c", fontSize: 12 }}>{rev.error}</div>}
        </div>
      </div>
    </div>
  );
}
