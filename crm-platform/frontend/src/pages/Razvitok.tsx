/* «Розвиток» v2 (16.09.2026, рішення Олега: «синхронно з ЗП і KPI; публічний рейтинг прибери, мотивуй людей»).
   Співробітник бачить лише СЕБЕ: «ти проти себе» (бали цього місяця проти минулого і особистий рекорд), сезонний рівень
   (план / стандарт / якість дзвінків за квартал), якість дзвінків і навички, змагання тижня (лише свої цифри), що робити далі.
   Один перемикач місяця вгорі; «Місяць» = календарний місяць (як у ЗП). Біля кожного числа — (i) з формулою на реальних числах.
   Власник / РОП: зведення команди, змагання тижня з кнопкою «Нарахувати приз» (через Біржу задач) і вибірка чатів для ІІ.
   SVG/CSS без бібліотек. Усі компоненти — на верхньому рівні файлу. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
import InfoTip from "../InfoTip";
import MyPayroll, { PlanRules } from "../MyPayroll";
import MyStats from "../MyStats";  // 16.09 (Олег): статистика місяця — у кожного

type T = (ru: string, uk: string) => string;
const C = { green: "#16a34a", amber: "#ca8a04", red: "#dc2626", terra: "#C67D5F", blue: "#1d4ed8" };
const thr = (v: number | null | undefined) => (v == null ? "#94a3b8" : v >= 70 ? C.green : v >= 50 ? C.amber : C.red);
const fmt = (n: number | null | undefined) => Math.round(Number(n || 0)).toLocaleString("uk-UA");
const dm = (iso?: string | null) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}` : "");

type Opt = { value: string; label: string };
type Skill = { key: string; label: string; cur: number; prev: number };
type TrendPt = { period: string; date: string; avg: number | null; n: number };
type Trend = { state: "empty" | "sparse" | "enough"; points: TrendPt[]; first_score: number | null; last_score: number | null; delta: number | null; dialogs_needed: number };
type Tip = { coaching: string; deal_id: number | null; kind: string; date: string; score: number };
type Practice = { key: string; text: string; text_ru: string; done: boolean };
type NextSteps = { focus: { key: string; label: string; cur: number; prev: number; target: number; what: string; what_ru: string }; tips: Tip[];
  model: { recommended_reply: string; why: string; deal_id: number | null; date: string } | null; practice: Practice[]; week: string; practice_note: string };
type PRow = { kind: string; label: string; rule: string; count: number; xp: number };
type Recent = { date: string; kind: string; label: string; xp: number; deal_id: number | null; credit: string };
type Points = { total: number; rows: PRow[]; prev_total: number; prev_label: string; delta: number; prev_rows: PRow[];
  record: { period: string; label: string; total: number } | null; recent: Recent[]; explain: string; compare: string };
type Quality = { label: string; avg: number | null; n: number; best: number | null; prev_avg: number | null; prev_n: number; delta: number | null;
  credit: { speaker: number; owner: number; sample: number }; credit_note: string; explain: string };
type SPart = { key: string; label: string; value: number | null; detail: string };
type SLevel = { no: number; name: string; emoji: string; color: string; from: number; next_name: string | null; next_from: number | null; to_next: number };
type Season = { label: string; from: string; to: string; reset: string; index: number | null; level: SLevel | null; parts: SPart[]; formula: string;
  levels: { from: number; name: string; emoji: string }[]; rule: string };
type CVal = { value: number | null; ok: boolean; text: string };
type CItem = { code: string; title: string; rule: string; unit: string; prize: number; enabled: boolean; now: CVal | null; last: CVal | null; won_last: boolean };
type Contests = { week: string; from: string; to: string; last_week: string; items: CItem[] } | null;
type Badge = { code: string; emoji: string; label: string; desc: string };
type Mgr = { id: number; name: string; period: string; period_label: string; periods: Opt[]; is_current: boolean; points: Points; quality: Quality;
  skills: Skill[]; trend: Trend; season: Season | null; badges: Badge[]; next_steps: NextSteps | null; is_team_viewer: boolean; is_self: boolean; contests: Contests };
type TRow = { id: number; name: string; points: number; prev_points: number; quality: number | null; quality_n: number; prev_quality: number | null;
  season_index: number | null; season_level: string | null; season_emoji: string | null };
type Team = { period: string; period_label: string; prev_label: string; managers: TRow[]; team_avg: number | null; team_count: number; quality_label: string; note: string };
type CState = { code: string; title: string; rule: string; unit: string; prize: number; offer_id: number | null; seeded: boolean; enabled: boolean;
  awarded?: { user_id: number; name: string; amount: number; status: string } | null };
type Settings = { chat_sampling: boolean; chat_sample_per_week: number; quality_label: string; contests: CState[]; cost_note: string };
type CRow = { id: number; name: string; growth: CVal; conversion: CVal; quality: CVal };
type CWin = { user_id: number | null; name?: string; value?: number; tie?: number[]; note?: string };
type CRes = { week: string; from: string; to: string; finished: boolean; rows: CRow[]; winners: Record<string, CWin>; contests: CState[] };

function confetti() {
  const cols = [C.terra, C.green, "#2563eb", C.amber, C.red, "#8b5cf6"];
  for (let i = 0; i < 70; i++) {
    const el = document.createElement("div");
    el.style.cssText = `position:fixed;top:-12px;left:${Math.random() * 100}vw;width:8px;height:13px;background:${cols[i % cols.length]};z-index:99999;border-radius:2px;pointer-events:none;`;
    document.body.appendChild(el);
    const dur = 1600 + Math.random() * 1600;
    el.animate([{ transform: "translateY(0) rotate(0)", opacity: 1 }, { transform: `translateY(105vh) rotate(${720 * (Math.random() - 0.5)}deg)`, opacity: 0.6 }], { duration: dur, easing: "cubic-bezier(.2,.6,.4,1)" });
    setTimeout(() => el.remove(), dur);
  }
}

/** ISO-тиждень дати: «2026-W38». */
function isoWeekKey(d: Date) {
  const x = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = x.getUTCDay() || 7;
  x.setUTCDate(x.getUTCDate() + 4 - day);
  const y0 = new Date(Date.UTC(x.getUTCFullYear(), 0, 1));
  const w = Math.ceil(((x.getTime() - y0.getTime()) / 86400000 + 1) / 7);
  return `${x.getUTCFullYear()}-W${String(w).padStart(2, "0")}`;
}
function shiftWeek(fromIso: string, days: number) {
  const d = new Date(fromIso + "T12:00:00");
  d.setDate(d.getDate() + days);
  return isoWeekKey(d);
}

export default function Razvitok() {
  const { t } = useLang();
  const [period, setPeriod] = useState("");
  const [periods, setPeriods] = useState<Opt[]>([]);
  const [mine, setMine] = useState<Mgr | null>(null);
  const [other, setOther] = useState<Mgr | null>(null);
  const [mode, setMode] = useState<"me" | "team" | "other">("me");
  const [team, setTeam] = useState<Team | null>(null);
  const [pickOpen, setPickOpen] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    setErr("");
    api.get<Mgr>("/api/gamification/me/" + (period ? `?period=${period}` : "")).then((m) => {
      if (!alive) return;
      setMine(m);
      setPeriods(m.periods || []);
      if (!period) {
        setPeriod(m.period);
        if (m.is_team_viewer) setMode("team");
      }
      const lv = m.season?.level?.no || 0;
      const key = `crm_season_lvl_${m.season?.from || ""}`;
      try {
        const prev = Number(localStorage.getItem(key) || "0");
        if (lv > prev && prev > 0) confetti();
        if (lv) localStorage.setItem(key, String(lv));
      } catch { /* приватний режим */ }
    }).catch(() => { if (alive) setErr(t("Не удалось загрузить — обновите страницу.", "Не вдалося завантажити — оновіть сторінку.")); });
    return () => { alive = false; };
  }, [period]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!mine?.is_team_viewer || !period) return;
    api.get<Team>(`/api/gamification/leaderboard/?period=${period}`).then(setTeam).catch(() => setTeam(null));
    if (mode === "other" && other) api.get<Mgr>(`/api/gamification/manager/${other.id}/?period=${period}`).then(setOther).catch(() => {});
  }, [mine?.is_team_viewer, period]); // eslint-disable-line react-hooks/exhaustive-deps

  const openManager = (id: number) => {
    setPickOpen(false);
    if (mine && id === mine.id) { setMode("me"); return; }
    api.get<Mgr>(`/api/gamification/manager/${id}/?period=${period}`).then((m) => { setOther(m); setMode("other"); }).catch(() => {});
  };
  const v = mode === "me" ? mine : mode === "other" ? other : null;

  return (
    <div className="scroll pad fade">
      <h2 style={{ margin: "0 0 2px", fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}><Icon n="trophy" size={20} /> {t("Развитие", "Розвиток")}</h2>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>{t("Ты против себя: этот месяц против прошлого, твой рекорд и уровень сезона. Рейтинга между людьми нет — только твой рост.", "Ти проти себе: цей місяць проти минулого, твій рекорд і рівень сезону. Рейтингу між людьми немає — лише твій ріст.")}</div>

      {/* ── ОДИН перемикач місяця (календарний місяць, як у ЗП) + вибір людини для власника ── */}
      <div style={{ position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", background: "rgba(255,255,255,.75)", backdropFilter: "blur(6px)", borderRadius: 12, padding: "8px 10px", marginBottom: 14, border: "1px solid #e8edf3" }}>
        {mine?.is_team_viewer && (
          <div style={{ position: "relative" }}>
            <button className="btn btn-light" style={{ fontSize: 13, fontWeight: 600 }} onClick={() => setPickOpen((o) => !o)}>
              <Icon n="users" size={15} /> {mode === "team" ? t("Команда (только вы видите)", "Команда (бачите лише ви)") : (v?.name || "—")} <span style={{ opacity: .6 }}>▾</span>
            </button>
            {pickOpen && (
              <div style={{ position: "absolute", top: 38, left: 0, zIndex: 40, background: "#fff", borderRadius: 12, boxShadow: "0 8px 28px rgba(20,40,80,.18)", border: "1px solid #e8edf3", minWidth: 240, padding: 6 }}>
                <div onClick={() => { setMode("team"); setPickOpen(false); }} style={{ padding: "8px 10px", borderRadius: 8, cursor: "pointer", fontWeight: 700, background: mode === "team" ? "#eff6ff" : "" }}>👥 {t("Команда (сводка)", "Команда (зведення)")}</div>
                <div style={{ height: 1, background: "#eef2f7", margin: "4px 0" }} />
                {(team?.managers || []).map((m) => (
                  <div key={m.id} onClick={() => openManager(m.id)} style={{ display: "flex", gap: 8, padding: "7px 10px", borderRadius: 8, cursor: "pointer", background: mode === "other" && other?.id === m.id ? "#eff6ff" : "" }}>
                    <span>{m.season_emoji || "·"}</span><span style={{ flex: 1, fontSize: 13, fontWeight: 600 }}>{m.name}</span>
                  </div>
                ))}
                {mine && <div onClick={() => openManager(mine.id)} style={{ padding: "7px 10px", borderRadius: 8, cursor: "pointer", fontSize: 13 }}>🙂 {t("Мой развитие", "Мій розвиток")}</div>}
              </div>
            )}
          </div>
        )}
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", gap: 3, background: "#f1f5f9", borderRadius: 9, padding: 3 }}>
          {periods.map((p) => (
            <button key={p.value} onClick={() => setPeriod(p.value)} style={{ fontSize: 12, fontWeight: 600, padding: "5px 11px", borderRadius: 7, cursor: "pointer", border: "none", background: period === p.value ? C.terra : "transparent", color: period === p.value ? "#fff" : "#475569" }}>{p.label}</button>
          ))}
        </div>
      </div>

      {err && <div className="note">{err}</div>}
      {!mine && !err && <div className="spin">{t("Загрузка…", "Завантаження…")}</div>}

      {mode === "me" && period && <MyPayroll period={period} hidePeriods />}
      {mode === "me" && <MyStats period={period} />}
      {mode === "other" && <div className="note" style={{ marginBottom: 12 }}>{t("Зарплату этого человека смотрите в «Финансы → ЗП/KPI».", "Зарплату цієї людини дивіться у «Фінанси → ЗП/KPI».")}</div>}

      {mode === "team" && mine?.is_team_viewer && (
        <>
          {team && <TeamBoard team={team} t={t} onOpen={openManager} />}
          <ContestAdmin t={t} />
          <OwnerSettings t={t} />
        </>
      )}

      {v && mode !== "team" && (
        <>
          <SelfCompare p={v.points} t={t} />
          {v.season && <SeasonCard s={v.season} t={t} />}
          <QualityCard q={v.quality} t={t} />
          <Skills v={v} t={t} />
          <TrendBlock tr={v.trend} label={v.quality.label} t={t} />
          {mode === "me" && v.contests && <ContestsCard c={v.contests} t={t} />}
          {v.next_steps && <NextStepsCard ns={v.next_steps} t={t} editable={mode === "me"} />}
          {v.badges.length > 0 && (
            <div className="panel">
              <div className="label" style={{ marginBottom: 8 }}>{t("Награды", "Нагороди")}</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {v.badges.map((b) => <span key={b.code} title={b.desc} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 13, fontWeight: 600, background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 20, padding: "5px 12px" }}>{b.emoji} {b.label}</span>)}
              </div>
            </div>
          )}
        </>
      )}
      {mode === "me" && <PlanRules />}
    </div>
  );
}

/* ─────────── Ти проти себе ─────────── */
function Delta({ d, unit }: { d: number | null | undefined; unit?: string }) {
  if (d == null || d === 0) return <span className="muted" style={{ fontSize: 13 }}>→ 0</span>;
  return <b style={{ color: d > 0 ? C.green : C.red, fontSize: 14 }}>{d > 0 ? `▲ +${fmt(d)}` : `▼ ${fmt(d)}`}{unit || ""}</b>;
}

function SelfCompare({ p, t }: { p: Points; t: T }) {
  return (
    <div className="panel" style={{ borderLeft: `4px solid ${C.terra}` }}>
      <div className="label" style={{ marginBottom: 2 }}>🏁 {t("Ты против себя", "Ти проти себе")}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{p.compare}</div>
      <div style={{ display: "flex", gap: 22, flexWrap: "wrap", alignItems: "flex-end" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center" }}><span style={{ fontSize: 40, fontWeight: 800, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>{fmt(p.total)}</span><InfoTip text={p.explain} /></div>
          <div className="muted" style={{ fontSize: 12 }}>{t("баллов в этом месяце", "балів цього місяця")}</div>
        </div>
        <div><div style={{ fontSize: 22, fontWeight: 700, color: "#64748b" }}>{fmt(p.prev_total)}</div><div className="muted" style={{ fontSize: 12 }}>{p.prev_label}</div></div>
        <div style={{ paddingBottom: 6 }}><Delta d={p.delta} /></div>
        {p.record && <div><div style={{ fontSize: 22, fontWeight: 700, color: C.amber }}>🏆 {fmt(p.record.total)}</div><div className="muted" style={{ fontSize: 12 }}>{t("твой рекорд", "твій рекорд")} · {p.record.label}{p.total >= p.record.total && p.total > 0 ? t(" — это сейчас!", " — це зараз!") : ` · ${t("осталось", "лишилось")} ${fmt(p.record.total - p.total)}`}</div></div>}
      </div>
      {p.rows.length > 0 && (
        <div style={{ marginTop: 10 }}>
          {p.rows.map((r) => (
            <div key={r.kind} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12.8, padding: "3px 0" }}>
              <span style={{ flex: 1 }}>{r.label} <span className="muted">× {r.count}</span><InfoTip text={t("Правило: ", "Правило: ") + r.rule} /></span>
              <b style={{ fontVariantNumeric: "tabular-nums" }}>+{fmt(r.xp)}</b>
            </div>
          ))}
        </div>
      )}
      {p.recent.length > 0 && (
        <details style={{ marginTop: 6 }}>
          <summary style={{ cursor: "pointer", fontSize: 12 }}>{t("За что баллы в этом месяце", "За що бали цього місяця")} ({p.recent.length})</summary>
          {p.recent.map((e, i) => (
            <div key={i} className="muted" style={{ fontSize: 11.8, padding: "2px 0" }}>{dm(e.date)} · {e.label} +{e.xp}{e.deal_id ? <> · <a href={`/deals/${e.deal_id}`} style={{ color: "#2563eb" }}>#{e.deal_id}</a></> : null}{e.credit === "owner" ? t(" · засчитано ответственному за сделку", " · зараховано відповідальному за угоду") : ""}</div>
          ))}
        </details>
      )}
      <div className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>{t("Баллы — только за то, что ты контролируешь: тест-набор → основной заказ, заказ без скидки, отзыв, разбор звонка. За сам факт выигранной сделки баллов нет.", "Бали — лише за те, що ти контролюєш: тест-набір → основне, замовлення без знижки, відгук, розбір дзвінка. За сам факт виграної угоди балів немає.")}</div>
    </div>
  );
}

/* ─────────── Сезон ─────────── */
function SeasonCard({ s, t }: { s: Season; t: T }) {
  const L = s.level;
  return (
    <div className="panel">
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, background: L ? L.color : "#e2e8f0", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 30, flexShrink: 0 }}>{L ? L.emoji : "🌱"}</div>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div className="muted" style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: ".04em" }}>{t("Сезон", "Сезон")} · {s.label}</div>
          <div style={{ fontSize: 19, fontWeight: 800, display: "flex", alignItems: "center" }}>{L ? L.name : t("Сезон ещё не начался", "Сезон ще не почався")}{s.index != null && <span style={{ marginLeft: 8, color: thr(s.index) }}>{s.index}/100</span>}<InfoTip text={s.formula + " " + s.rule} /></div>
          <div className="muted" style={{ fontSize: 12 }}>{L?.next_name ? t(`ещё ${L.to_next} до уровня «${L.next_name}»`, `ще ${L.to_next} до рівня «${L.next_name}»`) : L ? t("максимальный уровень сезона", "максимальний рівень сезону") : s.formula}
            {` · ${t("с", "з")} ${dm(s.reset)} ${t("новый сезон — всё с нуля", "новий сезон — усе з нуля")}`}</div>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10, marginTop: 12 }}>
        {s.parts.map((p) => (
          <div key={p.key} style={{ background: "#f8fafc", borderRadius: 10, padding: "8px 10px" }}>
            <div style={{ display: "flex", alignItems: "center", fontSize: 12.5, fontWeight: 700 }}>{p.label}<span style={{ flex: 1 }} /><span style={{ color: thr(p.value) }}>{p.value == null ? "—" : p.value}</span><InfoTip text={p.detail} /></div>
            <div style={{ height: 8, background: "#e2e8f0", borderRadius: 20, overflow: "hidden", marginTop: 5 }}><div style={{ width: `${p.value || 0}%`, height: "100%", background: thr(p.value), borderRadius: 20 }} /></div>
            {p.value == null && <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{p.detail}</div>}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
        {s.levels.map((l) => <span key={l.from} style={{ fontSize: 11, padding: "2px 8px", borderRadius: 20, background: L && L.from === l.from ? "#fff7ed" : "#f1f5f9", border: L && L.from === l.from ? "1px solid #fed7aa" : "1px solid transparent" }}>{l.emoji} {l.name} {l.from}+</span>)}
      </div>
    </div>
  );
}

/* ─────────── Якість дзвінків ─────────── */
function QualityCard({ q, t }: { q: Quality; t: T }) {
  return (
    <div className="panel" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px,1fr))", gap: 16, alignItems: "center" }}>
      <div>
        <div style={{ display: "flex", alignItems: "center" }}><span style={{ fontSize: 56, fontWeight: 800, lineHeight: 1, color: thr(q.avg), fontVariantNumeric: "tabular-nums" }}>{q.avg ?? "—"}</span><span style={{ fontSize: 20, color: "#cbd5e1" }}>&nbsp;/100</span><InfoTip text={q.explain} /></div>
        <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>{q.label} {q.delta != null && q.delta !== 0 && <Delta d={q.delta} />}</div>
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {[[q.n, t("разборов", "розборів")], [q.prev_avg ?? "—", t("прошлый месяц", "минулий місяць")], [q.best ?? "—", t("лучший разбор", "найкращий розбір")]].map(([n, lab], i) => (
          <div key={i} style={{ textAlign: "center" }}><div style={{ fontSize: 22, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{n as any}</div><div className="muted" style={{ fontSize: 11 }}>{lab as any}</div></div>
        ))}
      </div>
      {q.credit_note && <div className="muted" style={{ fontSize: 11.5, gridColumn: "1 / -1" }}><Icon n="info" size={12} /> {q.credit_note}</div>}
    </div>
  );
}

function Skills({ v, t }: { v: Mgr; t: T }) {
  const sorted = [...v.skills].sort((a, b) => a.cur - b.cur);
  if (!sorted.some((s) => s.cur)) return null;
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 2 }}>{t("Твои 6 навыков продаж (из разборов звонков)", "Твої 6 навичок продажу (з розборів дзвінків)")}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Сверху — самый слабый, с него и начинай. Засечка = прошлый месяц.", "Зверху — найслабший, з нього й починай. Засічка = минулий місяць.")}</div>
      {sorted.map((s, i) => {
        const delta = s.cur - s.prev;
        return (
          <div key={s.key} style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{s.label}</span>
              {i === 0 && s.cur > 0 && <span style={{ fontSize: 11, fontWeight: 700, color: C.red, background: "#fef2f2", borderRadius: 20, padding: "1px 8px" }}>🎯 {t("зона роста", "зона зростання")}</span>}
              <div style={{ flex: 1 }} />
              <b style={{ fontSize: 14, color: thr(s.cur) }}>{s.cur}</b>
              {s.prev > 0 && delta !== 0 && <span style={{ fontSize: 12, fontWeight: 700, color: delta > 0 ? C.green : C.red }}>{delta > 0 ? `▲+${delta}` : `▼${delta}`}</span>}
            </div>
            <div style={{ position: "relative", height: 14, background: "#f1f5f9", borderRadius: 20, overflow: "hidden" }}>
              <div style={{ width: `${s.cur}%`, height: "100%", background: thr(s.cur), borderRadius: 20 }} />
              {s.prev > 0 && <div style={{ position: "absolute", top: -2, bottom: -2, left: `calc(${s.prev}% - 1px)`, width: 2, background: "#475569", opacity: .55 }} />}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TrendBlock({ tr, label, t }: { tr: Trend; label: string; t: T }) {
  const W = 560, H = 160, pad = 26, n = tr.points.length || 1;
  const bw = Math.min(46, (W - 2 * pad) / n - 8);
  const x = (i: number) => pad + i * ((W - 2 * pad) / n) + ((W - 2 * pad) / n - bw) / 2;
  const y = (val: number) => H - 24 - (val / 100) * (H - 44);
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 2 }}>{t("Ты растёшь?", "Ти ростеш?")} · {label}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("Средний балл по календарным месяцам. Выше — лучше; цель 70.", "Середній бал по календарних місяцях. Вище — краще; ціль 70.")}</div>
      {tr.state === "empty" && <div className="note">{t(`График появится после первых разборов звонков (ещё ${tr.dialogs_needed}).`, `Графік зʼявиться після перших розборів дзвінків (ще ${tr.dialogs_needed}).`)}</div>}
      {tr.state === "sparse" && tr.first_score != null && (
        <div className="muted" style={{ fontSize: 12.5 }}>{t("Первые разборы", "Перші розбори")}: <b style={{ color: thr(tr.first_score) }}>{tr.first_score}</b> → {t("сейчас", "зараз")}: <b style={{ color: thr(tr.last_score) }}>{tr.last_score}</b> {tr.delta ? <Delta d={tr.delta} /> : null}</div>
      )}
      {tr.state === "enough" && (
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%" }}>
          <line x1={pad} y1={y(70)} x2={W - pad} y2={y(70)} stroke={C.green} strokeWidth={1.3} strokeDasharray="5 4" />
          <text x={W - pad} y={y(70) - 4} fontSize={9} fill={C.green} textAnchor="end">{t("цель 70", "ціль 70")}</text>
          {tr.points.map((p, i) => (
            <g key={p.period}>
              {p.avg != null && <rect x={x(i)} y={y(p.avg)} width={bw} height={H - 24 - y(p.avg)} rx={4} fill={thr(p.avg)} opacity={i === n - 1 ? 1 : 0.8} />}
              {p.avg != null && <text x={x(i) + bw / 2} y={y(p.avg) - 4} fontSize={10} fontWeight={700} fill={thr(p.avg)} textAnchor="middle">{p.avg}</text>}
              <text x={x(i) + bw / 2} y={H - 9} fontSize={9} fill="#94a3b8" textAnchor="middle">{p.date}{p.n ? ` · ${p.n}` : ""}</text>
            </g>
          ))}
        </svg>
      )}
    </div>
  );
}

/* ─────────── Змагання тижня (учасник: лише свої цифри) ─────────── */
function ContestsCard({ c, t }: { c: NonNullable<Contests>; t: T }) {
  return (
    <div className="panel" style={{ borderLeft: "4px solid #8b5cf6" }}>
      <div className="label" style={{ marginBottom: 2 }}>⚡ {t("Соревнование недели", "Змагання тижня")} · {dm(c.from)}–{dm(c.to)}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("Приз — в ЗП строкой «Задачи с биржи». Здесь только твои цифры; таблицу всех видит только руководитель.", "Приз — у ЗП рядком «Задачі з біржі». Тут лише твої цифри; таблицю всіх бачить лише керівник.")}</div>
      {c.items.map((it) => (
        <div key={it.code} style={{ padding: "7px 0", borderTop: "1px solid #f1f5f9" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <b style={{ fontSize: 13 }}>{it.title}</b><InfoTip text={it.rule} />
            <span style={{ marginLeft: "auto", fontSize: 12.5, color: C.green, fontWeight: 700 }}>🎁 {fmt(it.prize)} ₴</span>
          </div>
          <div style={{ fontSize: 12.3, marginTop: 2 }}>{t("Эта неделя", "Цей тиждень")}: {it.now ? it.now.text : "—"}{it.now && !it.now.ok ? <span className="muted"> · {t("пока не участвуешь", "поки не береш участі")}</span> : null}</div>
          {it.last && <div className="muted" style={{ fontSize: 11.8 }}>{t("Прошлая неделя", "Минулий тиждень")}: {it.last.text}{it.won_last ? <b style={{ color: C.green }}> · 🏆 {t("ты выиграл приз!", "ти виграв приз!")}</b> : null}</div>}
        </div>
      ))}
    </div>
  );
}

/* ─────────── Що робити далі (справи зберігаються до кінця тижня) ─────────── */
function NextStepsCard({ ns, t, editable }: { ns: NextSteps; t: T; editable: boolean }) {
  const [marks, setMarks] = useState<Record<string, boolean>>(() => Object.fromEntries(ns.practice.map((p) => [p.key, p.done])));
  useEffect(() => { setMarks(Object.fromEntries(ns.practice.map((p) => [p.key, p.done]))); }, [ns]);
  const ru = t("ru", "uk") === "ru";
  const f = ns.focus;
  const toggle = (p: Practice) => {
    if (!editable) return;
    const done = !marks[p.key];
    setMarks((m) => ({ ...m, [p.key]: done }));
    api.post("/api/gamification/practice/", { key: p.key, done, text: p.text }).catch(() => setMarks((m) => ({ ...m, [p.key]: !done })));
  };
  return (
    <div className="panel" style={{ borderLeft: `4px solid ${C.terra}` }}>
      <div className="label" style={{ marginBottom: 2 }}>🚀 {t("Что делать дальше", "Що робити далі")}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Один навык за раз. Всё построено из разборов твоих звонков.", "Один навик за раз. Усе побудовано з розборів твоїх дзвінків.")}</div>
      <div style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 12, padding: "12px 14px", marginBottom: 12 }}>
        <div style={{ fontSize: 15, fontWeight: 800, color: "#9a3412" }}>🎯 {t("Сейчас качаем", "Зараз качаємо")}: {f.label} <span style={{ color: thr(f.cur) }}>({f.cur}/100)</span></div>
        <div style={{ fontSize: 12.5, color: "#7c2d12", marginTop: 4 }}>{ru ? f.what_ru : f.what}</div>
        <div style={{ fontSize: 12.5, marginTop: 6 }}>{t("цель", "ціль")}: <b style={{ color: C.green }}>{f.cur} → {f.target}</b></div>
      </div>
      {ns.tips.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>{t("Советы лично тебе — из твоих же разговоров", "Поради особисто тобі — з твоїх же розмов")}</div>
          {ns.tips.map((tip, i) => (
            <div key={i} style={{ display: "flex", gap: 8, background: "#f8fafc", borderRadius: 10, padding: "9px 11px", marginBottom: 6 }}>
              <Icon n="check" size={15} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12.8, lineHeight: 1.5 }}>{tip.coaching}</div>
                <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>{tip.kind === "call" ? t("звонок", "дзвінок") : t("чат", "чат")} · {tip.date} · {t("балл", "бал")} {tip.score}{tip.deal_id ? <> · <a href={`/deals/${tip.deal_id}`} style={{ color: "#2563eb" }}>{t("открыть", "відкрити")}</a></> : null}</div>
              </div>
            </div>
          ))}
        </div>
      )}
      {ns.model && ns.model.recommended_reply && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>⭐ {t("Эталонный ответ — попробуй так", "Еталонна відповідь — спробуй так")}</div>
          {ns.model.why && <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{t("Что было не так", "Що було не так")}: {ns.model.why}</div>}
          <div style={{ background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: 10, padding: "10px 12px", fontSize: 12.8, lineHeight: 1.5, color: "#065f46" }}>{ns.model.recommended_reply}</div>
        </div>
      )}
      {ns.practice.length > 0 && (
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>{t("Маленькие дела на неделю — отмечай сделанное", "Маленькі справи на тиждень — відмічай зроблене")}</div>
          {ns.practice.map((p) => (
            <label key={p.key} style={{ display: "flex", gap: 9, alignItems: "flex-start", padding: "6px 0", cursor: editable ? "pointer" : "default" }}>
              <input type="checkbox" checked={!!marks[p.key]} disabled={!editable} onChange={() => toggle(p)} style={{ marginTop: 2, width: 16, height: 16, accentColor: C.terra }} />
              <span style={{ fontSize: 12.8, textDecoration: marks[p.key] ? "line-through" : "none", opacity: marks[p.key] ? .55 : 1 }}>{ru ? p.text_ru : p.text}</span>
            </label>
          ))}
          <div className="muted" style={{ fontSize: 11.5 }}>{ns.practice_note}</div>
        </div>
      )}
    </div>
  );
}

/* ─────────── Власник / РОП: команда ─────────── */
function TeamBoard({ team, t, onOpen }: { team: Team; t: T; onOpen: (id: number) => void }) {
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 2 }}>👥 {t("Команда", "Команда")} · {team.period_label}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{team.note}</div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.8, minWidth: 560 }}>
          <thead><tr style={{ color: "#64748b", textAlign: "left" }}>
            <th style={{ padding: "5px 6px" }}>{t("Менеджер", "Менеджер")}</th>
            <th style={{ padding: "5px 6px", textAlign: "right" }}>{t("Баллы", "Бали")}</th>
            <th style={{ padding: "5px 6px", textAlign: "right" }}>{team.prev_label}</th>
            <th style={{ padding: "5px 6px", textAlign: "right" }}>{team.quality_label}</th>
            <th style={{ padding: "5px 6px" }}>{t("Сезон", "Сезон")}</th>
          </tr></thead>
          <tbody>{team.managers.map((m) => (
            <tr key={m.id} onClick={() => onOpen(m.id)} style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer" }}>
              <td style={{ padding: "6px" }}><b>{m.name}</b></td>
              <td style={{ padding: "6px", textAlign: "right" }}>{fmt(m.points)} <Delta d={m.points - m.prev_points} /></td>
              <td style={{ padding: "6px", textAlign: "right", color: "#64748b" }}>{fmt(m.prev_points)}</td>
              <td style={{ padding: "6px", textAlign: "right", color: thr(m.quality) }}><b>{m.quality ?? "—"}</b> <span className="muted">({m.quality_n})</span></td>
              <td style={{ padding: "6px" }}>{m.season_emoji} {m.season_level || "—"} {m.season_index != null ? `· ${m.season_index}` : ""}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>{t("Средняя качество команды", "Середня якість команди")}: <b style={{ color: thr(team.team_avg) }}>{team.team_avg ?? "—"}</b> · {t("клик по строке — страница развития человека", "клік по рядку — сторінка розвитку людини")}</div>
    </div>
  );
}

function ContestAdmin({ t }: { t: T }) {
  const [week, setWeek] = useState("");
  const [d, setD] = useState<CRes | null>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const load = (w: string) => api.get<CRes>("/api/gamification/contests/" + (w ? `?week=${w}` : "")).then((r) => { setD(r); setWeek(r.week); }).catch(() => setD(null));
  useEffect(() => { load(""); }, []);
  if (!d) return null;
  const award = (code: string, uid?: number | null) => {
    const c = d.contests.find((x) => x.code === code);
    if (!c || !window.confirm(t(`Начислить приз ${fmt(c.prize)} ₴ за неделю ${d.week}? Сумма пойдёт в ЗП строкой «Задачи с биржи».`, `Нарахувати приз ${fmt(c.prize)} ₴ за тиждень ${d.week}? Сума піде в ЗП рядком «Задачі з біржі».`))) return;
    setBusy(code); setMsg("");
    api.post<any>("/api/gamification/contests/", { code, week: d.week, user_id: uid || undefined })
      .then((r) => { setMsg(t(`Начислено ${fmt(r.amount)} ₴ в ЗП за ${r.payroll_period}.`, `Нараховано ${fmt(r.amount)} ₴ у ЗП за ${r.payroll_period}.`)); load(d.week); })
      .catch((e: any) => setMsg(e?.data?.detail || t("Не удалось начислить", "Не вдалося нарахувати")))
      .finally(() => setBusy(""));
  };
  const seeded = d.contests.some((c) => c.seeded);
  return (
    <div className="panel" style={{ borderLeft: "4px solid #8b5cf6" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <div className="label" style={{ margin: 0 }}>⚡ {t("Соревнование недели", "Змагання тижня")} · {dm(d.from)}–{dm(d.to)}</div>
        <div style={{ flex: 1 }} />
        <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => load(shiftWeek(d.from, -7))}>←</button>
        <span style={{ fontSize: 12 }}>{week}</span>
        <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => load(shiftWeek(d.from, 7))}>→</button>
      </div>
      {!seeded && <div className="note" style={{ marginTop: 8 }}>{t("Соревнования ещё не заведены: команда rozvytok_contests_seed --live (см. README).", "Змагання ще не заведено: команда rozvytok_contests_seed --live (див. README).")}</div>}
      <div style={{ overflowX: "auto", marginTop: 8 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.3, minWidth: 620 }}>
          <thead><tr style={{ color: "#64748b", textAlign: "left" }}><th style={{ padding: 5 }}>{t("Менеджер", "Менеджер")}</th>{d.contests.map((c) => <th key={c.code} style={{ padding: 5 }}>{c.title.replace("Змагання тижня: ", "")}</th>)}</tr></thead>
          <tbody>{d.rows.map((r) => (
            <tr key={r.id} style={{ borderTop: "1px solid #f1f5f9" }}>
              <td style={{ padding: 5 }}><b>{r.name}</b></td>
              {d.contests.map((c) => { const cv = (r as any)[c.code] as CVal; return <td key={c.code} style={{ padding: 5, color: cv.ok ? "#0f172a" : "#94a3b8" }}>{cv.text}</td>; })}
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
        {d.contests.map((c) => {
          const w = d.winners[c.code] || { user_id: null };
          return (
            <div key={c.code} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12.5 }}>
              <span style={{ minWidth: 220 }}>{c.title.replace("Змагання тижня: ", "")} · 🎁 {fmt(c.prize)} ₴ {c.enabled ? "" : <span className="muted">({t("выключено", "вимкнено")})</span>}</span>
              <span className="muted">{w.user_id ? `${t("победитель", "переможець")}: ${w.name}` : (w.note || "—")}</span>
              {c.awarded ? <b style={{ color: C.green }}>✓ {t("начислено", "нараховано")} {c.awarded.name} {fmt(c.awarded.amount)} ₴</b>
                : c.enabled && d.finished && (w.user_id || (w.tie || []).length > 0) ? (
                  w.user_id ? <button className="btn btn-primary" style={{ fontSize: 12 }} disabled={busy === c.code} onClick={() => award(c.code)}>{t("Начислить приз", "Нарахувати приз")}</button>
                    : (w.tie || []).map((uid) => <button key={uid} className="btn btn-light" style={{ fontSize: 12 }} disabled={busy === c.code} onClick={() => award(c.code, uid)}>{t("Приз", "Приз")}: {d.rows.find((r) => r.id === uid)?.name}</button>)
                ) : !d.finished ? <span className="muted">{t("неделя ещё идёт", "тиждень ще триває")}</span> : null}
            </div>
          );
        })}
      </div>
      {msg && <div className="note" style={{ marginTop: 8 }}>{msg}</div>}
    </div>
  );
}

function OwnerSettings({ t }: { t: T }) {
  const [s, setS] = useState<Settings | null>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => { api.get<Settings>("/api/gamification/settings/").then(setS).catch(() => setS(null)); }, []);
  if (!s) return null;
  const save = (patch: any) => { setMsg(""); api.patch<Settings>("/api/gamification/settings/", patch).then(setS).catch((e: any) => setMsg(e?.data?.detail || t("Не удалось сохранить", "Не вдалося зберегти"))); };
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 6 }}>⚙️ {t("Настройки развития (только руководитель)", "Налаштування розвитку (лише керівник)")}</div>
      <label style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12.8, cursor: "pointer" }}>
        <input type="checkbox" checked={s.chat_sampling} onChange={(e) => save({ chat_sampling: e.target.checked })} style={{ marginTop: 3 }} />
        <span>{t("Раз в неделю ИИ разбирает случайную выборку чатов каждого менеджера — тогда метрика станет «качество разговоров (звонки + чаты)». Стоит денег.", "Раз на тиждень ІІ розбирає випадкову вибірку чатів кожного менеджера — тоді метрика стане «якість розмов (дзвінки + чати)». Коштує грошей.")}
          <span className="muted" style={{ display: "block", fontSize: 11.5 }}>{s.cost_note}</span></span>
      </label>
      {s.chat_sampling && (
        <div style={{ fontSize: 12.5, margin: "6px 0 0 24px" }}>{t("Чатов на человека в неделю", "Чатів на людину за тиждень")}: <input type="number" min={1} max={20} defaultValue={s.chat_sample_per_week} onBlur={(e) => save({ chat_sample_per_week: Number(e.target.value) })} style={{ width: 60 }} /></div>
      )}
      <div style={{ marginTop: 10, fontSize: 12.8, fontWeight: 700 }}>{t("Соревнования недели", "Змагання тижня")}</div>
      {s.contests.map((c) => (
        <label key={c.code} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12.5, padding: "3px 0", cursor: c.seeded ? "pointer" : "default" }}>
          <input type="checkbox" checked={c.enabled} disabled={!c.seeded} onChange={(e) => save({ contests: { [c.code]: e.target.checked } })} />
          <span>{c.title} · 🎁 {fmt(c.prize)} ₴{!c.seeded ? t(" — не заведено", " — не заведено") : ""}</span><InfoTip text={c.rule} />
        </label>
      ))}
      <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>{t("Сумму приза меняйте на «Бирже задач» (направление «Змагання тижня»). Там задачи остаются неактивными — «Беру» для них нет.", "Суму призу змінюйте на «Біржі задач» (напрям «Змагання тижня»). Там задачі лишаються неактивними — «Беру» для них немає.")}</div>
      {msg && <div className="note" style={{ marginTop: 6 }}>{msg}</div>}
    </div>
  );
}
