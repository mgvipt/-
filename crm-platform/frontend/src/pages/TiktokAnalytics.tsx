/* ============================================================================
 * TIKTOK — окрема сторінка аналітики акаунта @dekor_dlia_stin (без ChatPlace).
 * Дані: /api/tiktok-insights/* (бекенд apps/tiktok_insights, синк — крон tiktok_sync).
 * НЕ повʼязана з Meta-маркетингом — окремий блок, як просив Олег.
 * Блоки: шапка-плитки → динаміка підписників → перегляди по днях → активність
 * аудиторії по годинах → стать/вік/гео → таблиця відео → трендові запити.
 * ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

const fmt = (n: number | undefined | null) =>
  (n ?? 0) >= 1_000_000 ? ((n as number) / 1_000_000).toFixed(1) + "M"
  : (n ?? 0) >= 1_000 ? ((n as number) / 1_000).toFixed(1) + "k"
  : String(n ?? 0);
const pct = (x: number | undefined | null, digits = 1) => ((x ?? 0) * 100).toFixed(digits) + "%";
const secs = (s: number) => (s >= 60 ? `${Math.floor(s / 60)}м ${Math.round(s % 60)}с` : `${(s ?? 0).toFixed(1)}с`);

// ─── Прості SVG-графіки (без бібліотек, у стилі CRM) ───────────────────────
function Bars({ data, color = "#111827", h = 120, title }: { data: { label: string; value: number }[]; color?: string; h?: number; title?: (d: any) => string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: h }}>
      {data.map((d, i) => (
        <div key={i} title={title ? title(d) : `${d.label}: ${d.value}`}
          style={{ flex: 1, minWidth: 3, height: Math.max(2, (d.value / max) * (h - 14)), background: color, borderRadius: 3, opacity: 0.55 + 0.45 * (d.value / max) }} />
      ))}
    </div>
  );
}

function Line({ data, color = "#0ea5e9", h = 120 }: { data: number[]; color?: string; h?: number }) {
  if (!data.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const span = Math.max(1, max - min);
  const pts = data.map((v, i) => `${(i / Math.max(1, data.length - 1)) * 100},${100 - ((v - min) / span) * 92 - 4}`).join(" ");
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: "100%", height: h, display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2.2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function HBar({ label, share, color = "#111827" }: { label: string; share: number; color?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
      <span style={{ width: 92, fontSize: 12, color: "#475569", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</span>
      <div style={{ flex: 1, background: "#f1f5f9", borderRadius: 6, height: 14 }}>
        <div style={{ width: `${Math.min(100, share * 100)}%`, background: color, height: 14, borderRadius: 6 }} />
      </div>
      <span style={{ width: 48, fontSize: 12, fontWeight: 700, textAlign: "right" }}>{pct(share)}</span>
    </div>
  );
}

const GENDER_LBL: Record<string, [string, string]> = { Female: ["Женщины", "Жінки"], Male: ["Мужчины", "Чоловіки"], Other: ["Другое", "Інше"] };

export default function TiktokAnalytics() {
  const { t } = useLang();
  const [sum, setSum] = useState<any>(null);
  const [series, setSeries] = useState<any[]>([]);
  const [videos, setVideos] = useState<any[]>([]);
  const [sort, setSort] = useState<"date" | "views" | "engagement">("views");
  const [trendQ, setTrendQ] = useState("декор стін");
  const [trends, setTrends] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  function loadAll() {
    api.get<any>("/api/tiktok-insights/summary/").then(setSum).catch(() => {});
    api.get<any>("/api/tiktok-insights/timeseries/?days=30").then((d) => setSeries(Array.isArray(d) ? d : [])).catch(() => {});
  }
  useEffect(loadAll, []);
  useEffect(() => {
    api.get<any>(`/api/tiktok-insights/videos/?sort=${sort}&limit=60`).then((d) => setVideos(Array.isArray(d) ? d : [])).catch(() => {});
  }, [sort]);

  async function syncNow() {
    setBusy(true); setMsg("…");
    try { const r = await api.post<any>("/api/tiktok-insights/sync/", {}); setMsg(`✓ ${t("Обновлено", "Оновлено")}: ${r.daily_rows ?? 0} ${t("дней", "днів")}, ${r.videos ?? 0} ${t("видео", "відео")}`); loadAll(); }
    catch (e: any) { setMsg(e?.response?.data?.detail || t("Ошибка синка", "Помилка синку")); }
    setBusy(false);
  }
  async function loadTrends() {
    setTrends([]);
    try { const r = await api.get<any>(`/api/tiktok-insights/trending/?q=${encodeURIComponent(trendQ)}`); setTrends(r.keywords || []); } catch { /* ignore */ }
  }

  const activity = useMemo(() => {
    const arr = [...(sum?.audience_activity || [])].map((a: any) => ({ label: `${a.hour}:00`, value: a.count }));
    arr.sort((a, b) => parseInt(a.label) - parseInt(b.label));
    return arr;
  }, [sum]);
  const bestHours = useMemo(() => [...(sum?.audience_activity || [])].sort((a: any, b: any) => b.count - a.count).slice(0, 3).map((a: any) => `${a.hour}:00`), [sum]);

  const tile = (icon: string, label: string, value: string, sub?: string, color = "#111827") => (
    <div className="panel" style={{ flex: "1 1 150px", minWidth: 150, borderTop: `3px solid ${color}` }}>
      <div style={{ fontSize: 12, color: "#64748b", display: "flex", gap: 6, alignItems: "center" }}><Icon n={icon} size={14} /> {label}</div>
      <div style={{ fontSize: 24, fontWeight: 800, marginTop: 4 }}>{value}</div>
      {sub && <div style={{ fontSize: 11.5, color: "#16a34a", marginTop: 2 }}>{sub}</div>}
    </div>
  );

  return (
    <div className="scroll fade" style={{ padding: 20 }}>
      {/* ── Шапка ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}><Icon n="tiktok" size={20} /> TikTok · @{sum?.profile?.username || "dekor_dlia_stin"}</h2>
        {sum && !sum.connected && <span className="chip" style={{ background: "#d97706" }}>{t("канал не подключён", "канал не підключено")}</span>}
        <span style={{ flex: 1 }} />
        {sum?.last_sync && <span className="muted" style={{ fontSize: 12 }}>{t("Обновлено", "Оновлено")}: {new Date(sum.last_sync).toLocaleString()}</span>}
        <button className="btn" disabled={busy} onClick={syncNow}>↻ {t("Обновить данные", "Оновити дані")}</button>
        {msg && <span style={{ fontSize: 12.5, color: msg.startsWith("✓") ? "#16a34a" : "#b45309" }}>{msg}</span>}
      </div>

      {/* ── Плитки ── */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        {tile("👥", t("Подписчики", "Підписники"), fmt(sum?.followers_count), `+${fmt(sum?.followers_gained_30d)} / −${fmt(sum?.followers_lost_30d)} ${t("за 30 дн", "за 30 дн")}`)}
        {tile("▶️", t("Просмотры видео 30д", "Перегляди відео 30д"), fmt(sum?.video_views_30d), `${fmt(sum?.video_views_7d)} ${t("за 7 дн", "за 7 дн")}`, "#0ea5e9")}
        {tile("❤️", t("Реакции 30д", "Реакції 30д"), fmt((sum?.likes_30d || 0) + (sum?.comments_30d || 0) + (sum?.shares_30d || 0)), `ER ${pct(sum?.engagement_rate_avg_30d, 2)}`, "#e11d48")}
        {tile("🔗", t("Клики: сайт+контакты", "Кліки: сайт+контакти"), fmt((sum?.link_clicks_30d || 0) + (sum?.contact_clicks_30d || 0)), t("за 30 дней", "за 30 днів"), "#7c3aed")}
        {tile("🎯", t("Лиды из TikTok 30д", "Ліди з TikTok 30д"), fmt(sum?.leads_30d), `${t("видео на канале", "відео на каналі")}: ${sum?.videos_count ?? 0}`, "#16a34a")}
      </div>

      {/* ── Графіки: підписники + перегляди ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 14, marginBottom: 16 }}>
        <div className="panel">
          <div className="label">{t("Подписчики — динамика 30 дней", "Підписники — динаміка 30 днів")}</div>
          <Line data={series.map((r) => r.followers_total).filter((v) => v > 0)} color="#111827" />
          <div style={{ marginTop: 8 }}>
            <div className="muted" style={{ fontSize: 11, marginBottom: 3 }}>{t("пришло / ушло по дням", "прийшло / пішло по днях")}</div>
            <Bars h={54} color="#16a34a" data={series.map((r) => ({ label: r.date, value: r.followers_gained }))} title={(d) => `${d.label}: +${d.value}`} />
            <Bars h={30} color="#dc2626" data={series.map((r) => ({ label: r.date, value: r.followers_lost }))} title={(d) => `${d.label}: −${d.value}`} />
          </div>
        </div>
        <div className="panel">
          <div className="label">{t("Просмотры видео по дням", "Перегляди відео по днях")}</div>
          <Bars h={130} color="#0ea5e9" data={series.map((r) => ({ label: r.date, value: r.video_views }))} />
          <div className="label" style={{ marginTop: 12 }}>{t("Просмотры профиля", "Перегляди профілю")}</div>
          <Bars h={44} color="#7c3aed" data={series.map((r) => ({ label: r.date, value: r.profile_views }))} />
        </div>
        <div className="panel">
          <div className="label">{t("Когда аудитория онлайн (часы)", "Коли аудиторія онлайн (години)")}</div>
          <Bars h={120} color="#111827" data={activity} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#94a3b8" }}><span>0:00</span><span>12:00</span><span>23:00</span></div>
          {bestHours.length > 0 && <div style={{ marginTop: 8, fontSize: 12.5 }}>💡 {t("Лучшее время публикаций", "Найкращий час публікацій")}: <b>{bestHours.join(", ")}</b></div>}
        </div>
      </div>

      {/* ── Аудиторія ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 14, marginBottom: 16 }}>
        <div className="panel">
          <div className="label">{t("Пол аудитории", "Стать аудиторії")}</div>
          {(sum?.audience_genders || []).map((g: any) => (
            <HBar key={g.gender} label={t(...(GENDER_LBL[g.gender] || [g.gender, g.gender]) as [string, string])} share={g.percentage} color={g.gender === "Female" ? "#e11d48" : "#0ea5e9"} />
          ))}
          <div className="label" style={{ marginTop: 10 }}>{t("Возраст", "Вік")}</div>
          {(sum?.audience_ages || []).map((a: any) => <HBar key={a.age} label={a.age} share={a.percentage} />)}
        </div>
        <div className="panel">
          <div className="label">{t("Страны", "Країни")}</div>
          {(sum?.audience_countries || []).slice(0, 6).map((c: any, i: number) => <HBar key={i} label={c.country || c.country_name || "—"} share={c.percentage} color="#16a34a" />)}
          <div className="label" style={{ marginTop: 10 }}>{t("Города", "Міста")}</div>
          {(sum?.audience_cities || []).slice(0, 6).map((c: any, i: number) => <HBar key={i} label={c.city || c.city_name || c.name || "—"} share={c.percentage} color="#7c3aed" />)}
        </div>
        <div className="panel">
          <div className="label">{t("Тренды поиска TikTok (Украина)", "Тренди пошуку TikTok (Україна)")}</div>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <input style={{ flex: 1, height: 34, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13 }}
              value={trendQ} onChange={(e) => setTrendQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && loadTrends()} />
            <button className="btn" onClick={loadTrends}>{t("Искать", "Шукати")}</button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {trends.map((k) => <span key={k} className="chip" style={{ background: "#111827" }}>{k}</span>)}
            {!trends.length && <span className="muted" style={{ fontSize: 12 }}>{t("Введите тему и нажмите «Искать» — увидите, что сейчас ищут люди.", "Введіть тему і натисніть «Шукати» — побачите, що зараз шукають люди.")}</span>}
          </div>
        </div>
      </div>

      {/* ── Таблиця відео ── */}
      <div className="panel">
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
          <div className="label" style={{ margin: 0 }}>{t("Видео канала", "Відео каналу")} ({videos.length})</div>
          <span style={{ flex: 1 }} />
          {(["views", "date", "engagement"] as const).map((s) => (
            <button key={s} className="btn" style={{ height: 28, fontSize: 11.5, background: sort === s ? "#111827" : undefined, color: sort === s ? "#fff" : undefined }} onClick={() => setSort(s)}>
              {s === "views" ? t("По просмотрам", "За переглядами") : s === "date" ? t("Новые", "Нові") : t("По реакциям", "За реакціями")}
            </button>
          ))}
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead><tr style={{ textAlign: "right", color: "#64748b" }}>
              <th style={{ textAlign: "left", padding: 6 }}>{t("Видео", "Відео")}</th>
              <th style={{ padding: 6 }}>{t("Просмотры", "Перегляди")}</th>
              <th style={{ padding: 6 }}>{t("Охват", "Охоплення")}</th>
              <th style={{ padding: 6 }}>❤️</th><th style={{ padding: 6 }}>💬</th><th style={{ padding: 6 }}>↗</th>
              <th style={{ padding: 6 }}>ER</th>
              <th style={{ padding: 6 }}>{t("Ср. просмотр", "Сер. перегляд")}</th>
              <th style={{ padding: 6 }}>{t("Досмотры", "Досмотри")}</th>
            </tr></thead>
            <tbody>
              {videos.map((v) => (
                <tr key={v.item_id} style={{ borderTop: "1px solid #f1f5f9", textAlign: "right" }}>
                  <td style={{ textAlign: "left", padding: 6, maxWidth: 380 }}>
                    <a href={v.share_url} target="_blank" rel="noreferrer" style={{ display: "flex", gap: 8, alignItems: "center", textDecoration: "none", color: "inherit" }}>
                      {v.thumbnail_url && <img src={v.thumbnail_url} alt="" style={{ width: 34, height: 46, objectFit: "cover", borderRadius: 6, flexShrink: 0 }} />}
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.caption || v.item_id}</span>
                    </a>
                  </td>
                  <td style={{ padding: 6, fontWeight: 700 }}>{fmt(v.views)}</td>
                  <td style={{ padding: 6 }}>{fmt(v.reach)}</td>
                  <td style={{ padding: 6 }}>{fmt(v.likes)}</td>
                  <td style={{ padding: 6 }}>{fmt(v.comments)}</td>
                  <td style={{ padding: 6 }}>{fmt(v.shares)}</td>
                  <td style={{ padding: 6 }}>{pct(v.engagement_rate)}</td>
                  <td style={{ padding: 6 }}>{secs(v.average_time_watched)}</td>
                  <td style={{ padding: 6 }}>{pct(v.full_video_watched_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>{t("Клик по видео открывает его в TikTok. Данные обновляются ночью автоматически и кнопкой «Обновить данные».", "Клік по відео відкриває його в TikTok. Дані оновлюються вночі автоматично та кнопкою «Оновити дані».")}</div>
      </div>
    </div>
  );
}
