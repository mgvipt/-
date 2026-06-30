/* «Розвиток» — зрозумілий дашборд розвитку для менеджерів-неекспертів.
   Шапка: вибір менеджера (для керівника) + період. Лідерборд зверху (3 вкладки з поясненнями).
   Герой (рівень + великий бал якості). Навички = горизонтальні смуги (замість радара).
   Тренд = стовпчики / було→стало / онбординг. Блок «Що робити далі» з реальним коучингом ИИ.
   SVG/CSS без бібліотек. Конфеті на новий рівень. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

const C = { green: "#16a34a", amber: "#ca8a04", red: "#dc2626", terra: "#C67D5F" };
const thr = (v: number | null | undefined) => (v == null ? "#94a3b8" : v >= 70 ? C.green : v >= 50 ? C.amber : C.red);

type Skill = { key: string; label: string; cur: number; prev: number };
type TrendPt = { date: string; avg: number | null; n: number };
type Trend = { state: "empty" | "sparse" | "enough"; points: TrendPt[]; first_score: number | null; last_score: number | null; delta: number | null; dialogs_needed: number };
type Tip = { coaching: string; deal_id: number | null; kind: string; date: string; score: number };
type NextSteps = { focus: { key: string; label: string; cur: number; prev: number; target: number; what: string; what_ru: string }; tips: Tip[]; model: { recommended_reply: string; why: string; deal_id: number | null; date: string } | null; practice: string[]; practice_ru: string[]; level_goal: { to_next: number; next_level: string | null } };
type Level = { level: number; name: string; emoji: string; color: string; total_xp: number; to_next: number; next_threshold: number | null; progress: number };
type Mgr = { id: number; name: string; level: Level; skills: Skill[]; trend: Trend; badges: { code: string; emoji: string; label: string; desc: string }[]; analyses: number; analyses_all: number; avg_overall: number | null; avg_prev: number | null; quality_delta: number | null; xp_period: number; best: number | null; xp_per_dialog: number; weakest: string | null; next_steps: NextSteps | null };
type LbRow = { id: number; name: string; level: number; level_name: string; level_emoji: string; color: string; total_xp: number; period_xp: number; avg_overall: number | null; was: number | null; now: number | null; growth: number | null; status: string };
type Lb = { week: LbRow[]; quality: LbRow[]; growth: LbRow[]; me: number; managers: LbRow[]; team_avg: number | null; team_count: number };

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

export default function Razvitok() {
  const { t } = useLang();
  const [period, setPeriod] = useState<"week" | "month" | "quarter" | "all">("month");
  const [lb, setLb] = useState<Lb | null>(null);
  const [view, setView] = useState<Mgr | null>(null);
  const [myId, setMyId] = useState<number | null>(null);
  const [isOwner, setIsOwner] = useState(false);
  const [mode, setMode] = useState<"manager" | "team">("manager");
  const [tab, setTab] = useState<"week" | "quality" | "growth">("quality");
  const [pickOpen, setPickOpen] = useState(false);
  const [done, setDone] = useState<Record<string, boolean>>({});

  const loadLb = (p: string) => api.get<Lb>(`/api/gamification/leaderboard/?period=${p}`);
  const loadMgr = (id: number, mine: boolean, p: string) =>
    api.get<Mgr>(mine ? `/api/gamification/me/?period=${p}` : `/api/gamification/manager/${id}/?period=${p}`);

  useEffect(() => {
    loadLb(period).then((lbd) => {
      setLb(lbd);
      api.get<Mgr>(`/api/gamification/me/?period=${period}`).then((me) => {
        setMyId(me.id);
        const owner = !(lbd.managers || []).some((m) => m.id === me.id);
        setIsOwner(owner);
        if (owner) { setMode("team"); }
        else {
          setMode("manager"); setView(me);
          const prev = Number(localStorage.getItem("crm_last_level") || "0");
          if (me.level.level > prev && prev > 0) confetti();
          localStorage.setItem("crm_last_level", String(me.level.level));
        }
      }).catch(() => {});
    }).catch(() => {});
  }, []);

  const changePeriod = (p: typeof period) => {
    setPeriod(p);
    loadLb(p).then(setLb).catch(() => {});
    if (mode === "manager" && view) loadMgr(view.id, view.id === myId, p).then(setView).catch(() => {});
  };
  const openManager = (id: number) => { setMode("manager"); setPickOpen(false); loadMgr(id, id === myId, period).then(setView).catch(() => {}); };
  const openTeam = () => { setMode("team"); setPickOpen(false); };

  const PERIODS: [typeof period, string, string][] = [["week", "Неделя", "Тиждень"], ["month", "Месяц", "Місяць"], ["quarter", "Квартал", "Квартал"], ["all", "Всё время", "Увесь час"]];
  const v = view;

  return (
    <div className="scroll pad fade">
      <h2 style={{ margin: "0 0 2px", fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}><Icon n="trophy" size={20} /> {t("Развитие", "Розвиток")}</h2>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>{t("Уровень, баллы за качество диалогов, прогресс навыков и что делать дальше. Баллы — для роста, не для штрафов.", "Рівень, бали за якість діалогів, прогрес навичок і що робити далі. Бали — для росту, не для штрафів.")}</div>

      {/* ── Шапка: вибір менеджера + період ── */}
      <div style={{ position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", background: "rgba(255,255,255,.7)", backdropFilter: "blur(6px)", borderRadius: 12, padding: "8px 10px", marginBottom: 14, border: "1px solid #e8edf3" }}>
        {isOwner && lb && (
          <div style={{ position: "relative" }}>
            <button className="btn btn-light" style={{ fontSize: 13, fontWeight: 600 }} onClick={() => setPickOpen((o) => !o)}>
              <Icon n="users" size={15} /> {mode === "team" ? t("Вся команда", "Вся команда") : (v?.name || "—")} <span style={{ opacity: .6 }}>▾</span>
            </button>
            {pickOpen && (
              <div style={{ position: "absolute", top: 38, left: 0, zIndex: 40, background: "#fff", borderRadius: 12, boxShadow: "0 8px 28px rgba(20,40,80,.18)", border: "1px solid #e8edf3", minWidth: 250, padding: 6 }}>
                <div onClick={openTeam} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 8, cursor: "pointer", fontWeight: 700, background: mode === "team" ? "#eff6ff" : "" }}>👥 {t("Вся команда (сводка)", "Вся команда (зведення)")}</div>
                <div style={{ height: 1, background: "#eef2f7", margin: "4px 0" }} />
                {lb.managers.map((m) => (
                  <div key={m.id} onClick={() => openManager(m.id)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", borderRadius: 8, cursor: "pointer", background: mode === "manager" && v?.id === m.id ? "#eff6ff" : "" }}>
                    <span style={{ fontSize: 16 }}>{m.level_emoji}</span>
                    <div style={{ flex: 1, minWidth: 0 }}><div style={{ fontSize: 13, fontWeight: 600 }}>{m.name}</div><div className="muted" style={{ fontSize: 11 }}>{m.level_name}</div></div>
                    <span style={{ width: 9, height: 9, borderRadius: "50%", background: m.status === "green" ? C.green : m.status === "amber" ? C.amber : C.red }} />
                    <b style={{ fontSize: 13, color: thr(m.avg_overall), fontVariantNumeric: "tabular-nums" }}>{m.avg_overall ?? "—"}</b>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", gap: 3, background: "#f1f5f9", borderRadius: 9, padding: 3 }}>
          {PERIODS.map(([p, ru, uk]) => (
            <button key={p} onClick={() => changePeriod(p)} style={{ fontSize: 12, fontWeight: 600, padding: "5px 11px", borderRadius: 7, cursor: "pointer", border: "none", background: period === p ? C.terra : "transparent", color: period === p ? "#fff" : "#475569" }}>{t(ru, uk)}</button>
          ))}
        </div>
      </div>

      {/* ── Лідерборд (зверху) ── */}
      {lb && <Leaderboard lb={lb} tab={tab} setTab={setTab} t={t} onOpen={openManager} highlight={mode === "manager" ? v?.id : undefined} />}

      {/* ── Командна зведення (для керівника) ── */}
      {mode === "team" && lb && (
        <div className="panel" style={{ display: "flex", alignItems: "center", gap: 22, flexWrap: "wrap" }}>
          <div><div style={{ fontSize: 44, fontWeight: 800, color: thr(lb.team_avg), fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>{lb.team_avg ?? "—"}</div><div className="muted" style={{ fontSize: 12 }}>{t("средняя качество команды", "середня якість команди")}</div></div>
          <div style={{ width: 1, alignSelf: "stretch", background: "#eef2f7" }} />
          <div><div style={{ fontSize: 44, fontWeight: 800, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>{lb.team_count}</div><div className="muted" style={{ fontSize: 12 }}>{t("менеджеров в продажах", "менеджерів у продажах")}</div></div>
          <div style={{ flex: 1, minWidth: 200 }} className="note">{t("Выбери менеджера вверху слева, чтобы открыть его развитие, навыки и что ему делать дальше.", "Обери менеджера вгорі зліва, щоб відкрити його розвиток, навички і що йому робити далі.")}</div>
        </div>
      )}

      {/* ── Персональні секції ── */}
      {mode === "manager" && v && (
        <>
          <Hero v={v} t={t} />
          <Skills v={v} t={t} />
          <TrendBlock v={v} t={t} />
          {v.next_steps && <NextStepsCard v={v} t={t} done={done} setDone={setDone} />}
          {v.badges.length > 0 && (
            <div className="panel">
              <div className="label" style={{ marginBottom: 8 }}>{t("Награды", "Нагороди")}</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {v.badges.map((b) => <span key={b.code} title={b.desc} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 13, fontWeight: 600, background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 20, padding: "5px 12px" }}>{b.emoji} {b.label}</span>)}
              </div>
              <div className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>{t("Награды за прогресс — копятся по мере работы.", "Нагороди за прогрес — накопичуються по мірі роботи.")}</div>
            </div>
          )}
        </>
      )}
      {!lb && <div className="spin">{t("Загрузка…", "Завантаження…")}</div>}
    </div>
  );
}

/* ─────────── Лідерборд ─────────── */
function Leaderboard({ lb, tab, setTab, t, onOpen, highlight }: any) {
  const TABS: [string, string, string, string][] = [
    ["week", "🔥", "Активность", "Активність"],
    ["quality", "⭐", "Качество", "Якість"],
    ["growth", "📈", "Прогресс", "Прогрес"],
  ];
  const CAP: Record<string, [string, string]> = {
    week: ["Кто больше работал — сумма баллов XP за период", "Хто більше працював — сума балів XP за період"],
    quality: ["У кого диалоги в среднем лучше (балл 0–100)", "У кого діалоги в середньому кращі (бал 0–100)"],
    growth: ["Кто вырос сильнее всех. Растёт даже новичок — видно тут", "Хто виріс найсильніше. Росте навіть новачок — видно тут"],
  };
  const rows: LbRow[] = lb[tab] || [];
  const metric = (r: LbRow) => tab === "week" ? `${r.period_xp} XP` : tab === "quality" ? `${r.avg_overall ?? "—"}` : (r.growth == null ? "—" : (r.growth > 0 ? `▲ +${r.growth}` : r.growth < 0 ? `▼ ${r.growth}` : "→ 0"));
  return (
    <div className="panel">
      <div style={{ display: "flex", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
        {TABS.map(([k, e, ru, uk]) => (
          <button key={k} onClick={() => setTab(k)} className={"btn" + (tab === k ? " btn-primary" : " btn-light")} style={{ fontSize: 12.5 }}>{e} {t(ru, uk)}</button>
        ))}
      </div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t(CAP[tab][0], CAP[tab][1])}</div>
      {rows.map((r, i) => (
        <div key={r.id} onClick={() => onOpen(r.id)} style={{ display: "flex", alignItems: "center", gap: 11, padding: "9px 10px", borderRadius: 9, marginBottom: 5, cursor: "pointer", background: r.id === highlight ? "#eff6ff" : r.id === lb.me ? "#fff7ed" : "#f8fafc", border: r.id === highlight ? "1px solid #bfdbfe" : "1px solid transparent" }}>
          <span style={{ width: 26, textAlign: "center", fontWeight: 800, fontSize: i < 3 ? 17 : 14, color: i === 0 ? "#ca8a04" : "#94a3b8" }}>{i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : i + 1}</span>
          <span style={{ fontSize: 19 }}>{r.level_emoji}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13.5, fontWeight: 600 }}>{r.name}{r.id === lb.me ? ` · ${t("это ты", "це ти")}` : ""}</div>
            <div className="muted" style={{ fontSize: 11 }}>{r.level_name} · {r.total_xp} XP{tab === "growth" && r.was != null && r.now != null ? ` · ${t("было", "було")} ${r.was} → ${t("стало", "стало")} ${r.now}` : ""}</div>
          </div>
          <div style={{ fontSize: 17, fontWeight: 800, fontVariantNumeric: "tabular-nums", color: tab === "growth" ? ((r.growth ?? 0) > 0 ? C.green : (r.growth ?? 0) < 0 ? C.red : "#64748b") : tab === "quality" ? thr(r.avg_overall) : "#0f172a" }}>{metric(r)}</div>
        </div>
      ))}
      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{t("Клик по строке — открыть страницу развития этого менеджера.", "Клік по рядку — відкрити сторінку розвитку цього менеджера.")}</div>
    </div>
  );
}

/* ─────────── Герой ─────────── */
const LEVEL_NAMES = ["Новачок", "Учень", "Продавець", "Профі", "Майстер", "Легенда Wallcov"];
function Hero({ v, t }: { v: Mgr; t: any }) {
  const L = v.level;
  const d = v.quality_delta;
  const nextName = LEVEL_NAMES[L.level] || "—";
  return (
    <div className="panel" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px,1fr))", gap: 18, alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ width: 60, height: 60, borderRadius: 16, background: L.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32, flexShrink: 0 }}>{L.emoji}</div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 19, fontWeight: 800 }}>{L.name}</div>
          <div className="muted" style={{ fontSize: 12 }}>{L.next_threshold ? `${t("ещё", "ще")} ${L.to_next} XP ${t("до уровня", "до рівня")} «${nextName}»` : t("максимальный уровень", "максимальний рівень")}</div>
          <div style={{ height: 12, background: "#f1f5f9", borderRadius: 20, marginTop: 7, overflow: "hidden", width: 180, maxWidth: "100%" }}><div style={{ width: `${L.progress}%`, height: "100%", background: `linear-gradient(90deg,${L.color},${L.color}cc)`, borderRadius: 20 }} /></div>
        </div>
      </div>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 64, fontWeight: 800, lineHeight: 1, color: thr(v.avg_overall), fontVariantNumeric: "tabular-nums" }}>{v.avg_overall ?? "—"}<span style={{ fontSize: 22, color: "#cbd5e1" }}> /100</span></div>
        <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>{t("Качество твоих диалогов", "Якість твоїх діалогів")}{d != null && d !== 0 ? <b style={{ color: d > 0 ? C.green : C.red, marginLeft: 6 }}>{d > 0 ? `▲ +${d}` : `▼ ${d}`}</b> : null}</div>
      </div>
      <div style={{ display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap" }}>
        {[[v.analyses, t("разборов", "розборів")], [v.xp_period, t("XP за период", "XP за період")], [v.best ?? "—", t("лучший балл", "найкращий бал")]].map(([n, lab], i) => (
          <div key={i} style={{ textAlign: "center" }}><div style={{ fontSize: 24, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{n as any}</div><div className="muted" style={{ fontSize: 11 }}>{lab as any}</div></div>
        ))}
      </div>
    </div>
  );
}

/* ─────────── Навички (смуги) ─────────── */
function Skills({ v, t }: { v: Mgr; t: any }) {
  const sorted = [...v.skills].sort((a, b) => a.cur - b.cur);
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 2 }}>{t("Твои 6 навыков продаж", "Твої 6 навичок продажу")}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Сверху — самый слабый, с него и начинай. Тонкая засечка = было в прошлом периоде.", "Зверху — найслабший, з нього й починай. Тонка засічка = було в минулому періоді.")}</div>
      {sorted.map((s, i) => {
        const delta = s.cur - s.prev;
        const isWeak = i === 0, isTop = i === sorted.length - 1;
        return (
          <div key={s.key} style={{ marginBottom: 13 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{s.label}</span>
              {isWeak && s.cur > 0 && <span style={{ fontSize: 11, fontWeight: 700, color: C.red, background: "#fef2f2", borderRadius: 20, padding: "1px 8px" }}>🎯 {t("зона роста", "зона зростання")}</span>}
              {isTop && s.cur >= 70 && <span style={{ fontSize: 11 }}>💪</span>}
              <div style={{ flex: 1 }} />
              <b style={{ fontSize: 14, color: thr(s.cur), fontVariantNumeric: "tabular-nums" }}>{s.cur}</b>
              {s.prev > 0 && delta !== 0 && <span style={{ fontSize: 12, fontWeight: 700, color: delta > 0 ? C.green : C.red }}>{delta > 0 ? `▲+${delta}` : `▼${delta}`}</span>}
            </div>
            <div style={{ position: "relative", height: 16, background: "#f1f5f9", borderRadius: 20, overflow: "hidden" }}>
              <div style={{ width: `${s.cur}%`, height: "100%", background: thr(s.cur), borderRadius: 20, transition: "width .4s" }} />
              {s.prev > 0 && <div title={t("было", "було") + " " + s.prev} style={{ position: "absolute", top: -2, bottom: -2, left: `calc(${s.prev}% - 1px)`, width: 2, background: "#475569", opacity: .55 }} />}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ─────────── Тренд ─────────── */
function TrendBlock({ v, t }: { v: Mgr; t: any }) {
  const tr = v.trend;
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 2 }}>{t("Ты растёшь?", "Ти ростеш?")}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Как меняется среднее качество твоих разговоров. Выше — лучше.", "Як змінюється середня якість твоїх розмов. Вище — краще.")}</div>
      {tr.state === "empty" && (
        <div className="note" style={{ display: "flex", alignItems: "center", gap: 10 }}><Icon n="info" size={18} /> {t(`Здесь появится график, когда разберём твои первые разговоры (ещё ${tr.dialogs_needed}).`, `Тут зʼявиться графік, коли розберемо твої перші розмови (ще ${tr.dialogs_needed}).`)}</div>
      )}
      {tr.state === "sparse" && tr.first_score != null && (
        <div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 22, justifyContent: "center", padding: "8px 0" }}>
            <Bar label={t("Первые", "Перші")} val={tr.first_score} />
            <div style={{ fontSize: 28, color: "#cbd5e1", alignSelf: "center" }}>→</div>
            <Bar label={t("Сейчас", "Зараз")} val={tr.last_score!} big />
            {tr.delta != null && tr.delta !== 0 && <div style={{ alignSelf: "center", fontSize: 20, fontWeight: 800, color: tr.delta > 0 ? C.green : C.red }}>{tr.delta > 0 ? `▲ +${tr.delta}` : `▼ ${tr.delta}`}</div>}
          </div>
          <div className="muted" style={{ fontSize: 11.5, textAlign: "center" }}>{t("Мало данных для графика. Показываем старт и где ты сейчас — график появится позже.", "Замало даних для графіка. Показуємо старт і де ти зараз — графік зʼявиться пізніше.")}</div>
        </div>
      )}
      {tr.state === "enough" && <Columns points={tr.points} t={t} />}
    </div>
  );
}
function Bar({ label, val, big }: { label: string; val: number; big?: boolean }) {
  const h = Math.max(8, (val / 100) * 120);
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: big ? 22 : 17, fontWeight: 800, color: thr(val), fontVariantNumeric: "tabular-nums" }}>{val}</div>
      <div style={{ width: big ? 64 : 52, height: h, background: thr(val), borderRadius: "8px 8px 0 0", margin: "4px auto 0" }} />
      <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>{label}</div>
    </div>
  );
}
function Columns({ points, t }: { points: TrendPt[]; t: any }) {
  const W = 560, H = 170, pad = 26, n = points.length;
  const bw = Math.min(46, (W - 2 * pad) / n - 8);
  const x = (i: number) => pad + i * ((W - 2 * pad) / n) + ((W - 2 * pad) / n - bw) / 2;
  const y = (val: number) => H - 24 - (val / 100) * (H - 44);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%" }}>
      <line x1={pad} y1={y(70)} x2={W - pad} y2={y(70)} stroke={C.green} strokeWidth={1.3} strokeDasharray="5 4" />
      <text x={W - pad} y={y(70) - 4} fontSize={9} fill={C.green} textAnchor="end">{t("цель 70", "ціль 70")}</text>
      {points.map((p, i) => {
        if (p.avg == null) return <text key={i} x={x(i) + bw / 2} y={H - 26} fontSize={8.5} fill="#cbd5e1" textAnchor="middle">·</text>;
        const last = i === n - 1;
        return (
          <g key={i}>
            <rect x={x(i)} y={y(p.avg)} width={bw} height={H - 24 - y(p.avg)} rx={4} fill={thr(p.avg)} opacity={last ? 1 : 0.82} />
            <text x={x(i) + bw / 2} y={y(p.avg) - 4} fontSize={last ? 12 : 9.5} fontWeight={last ? 800 : 600} fill={thr(p.avg)} textAnchor="middle">{p.avg}</text>
            <text x={x(i) + bw / 2} y={H - 9} fontSize={8.5} fill="#94a3b8" textAnchor="middle">{p.date}</text>
          </g>
        );
      })}
    </svg>
  );
}

/* ─────────── Що робити далі ─────────── */
function NextStepsCard({ v, t, done, setDone }: { v: Mgr; t: any; done: Record<string, boolean>; setDone: any }) {
  const ns = v.next_steps!;
  const f = ns.focus;
  const ru = t("ru", "uk") === "ru";
  const practice = ru ? ns.practice_ru : ns.practice;
  const what = ru ? f.what_ru : f.what;
  return (
    <div className="panel" style={{ borderLeft: `4px solid ${C.terra}` }}>
      <div className="label" style={{ marginBottom: 2 }}>🚀 {t("Что делать дальше", "Що робити далі")}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>{t("Один навык за раз — реальный результат. Это всё построено из разборов твоих диалогов.", "Один навик за раз — реальний результат. Це все побудовано з розборів твоїх діалогів.")}</div>

      {/* фокус */}
      <div style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 12, padding: "12px 14px", marginBottom: 14 }}>
        <div style={{ fontSize: 15, fontWeight: 800, color: "#9a3412" }}>🎯 {t("Сейчас качаем", "Зараз качаємо")}: {f.label} <span style={{ color: thr(f.cur) }}>({f.cur}/100)</span></div>
        <div style={{ fontSize: 12.5, color: "#7c2d12", marginTop: 4 }}>{what}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
          <span className="muted" style={{ fontSize: 12 }}>{t("цель", "ціль")}:</span>
          <div style={{ flex: 1, maxWidth: 220, height: 9, background: "#fde7d3", borderRadius: 20, position: "relative" }}>
            <div style={{ width: `${f.cur}%`, height: "100%", background: thr(f.cur), borderRadius: 20 }} />
            <div style={{ position: "absolute", top: -3, left: `calc(${f.target}% - 1px)`, height: 15, width: 2, background: C.green }} />
          </div>
          <b style={{ fontSize: 13, color: C.green }}>{f.cur} → {f.target}</b>
        </div>
      </div>

      {/* поради з власних діалогів */}
      {ns.tips.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>{t("Советы лично тебе — из твоих же разговоров", "Поради особисто тобі — з твоїх же розмов")}</div>
          {ns.tips.map((tip, i) => (
            <div key={i} style={{ display: "flex", gap: 8, background: "#f8fafc", borderRadius: 10, padding: "9px 11px", marginBottom: 6 }}>
              <Icon n="check" size={15} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12.8, lineHeight: 1.5 }}>{tip.coaching}</div>
                <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>{t("из диалога", "з діалогу")} · {tip.date} · {t("балл", "бал")} {tip.score}{tip.deal_id ? <> · <a href={`/deals/${tip.deal_id}`} style={{ color: "#2563eb" }}>{t("открыть", "відкрити")}</a></> : null}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* еталонна відповідь */}
      {ns.model && ns.model.recommended_reply && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>⭐ {t("Эталонный ответ — попробуй так в следующем чате", "Еталонна відповідь — спробуй так у наступному чаті")}</div>
          {ns.model.why && <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{t("Что было не так", "Що було не так")}: {ns.model.why}</div>}
          <div style={{ background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: 10, padding: "10px 12px", fontSize: 12.8, lineHeight: 1.5, color: "#065f46" }}>{ns.model.recommended_reply}</div>
        </div>
      )}

      {/* практики-чеклист */}
      {practice.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>{t("Маленькие дела на неделю — отмечай сделанное", "Маленькі справи на тиждень — відмічай зроблене")}</div>
          {practice.map((p, i) => {
            const key = f.key + i;
            return (
              <label key={i} style={{ display: "flex", gap: 9, alignItems: "flex-start", padding: "7px 0", cursor: "pointer" }}>
                <input type="checkbox" checked={!!done[key]} onChange={() => setDone((d: any) => ({ ...d, [key]: !d[key] }))} style={{ marginTop: 2, width: 16, height: 16, accentColor: C.terra }} />
                <span style={{ fontSize: 12.8, textDecoration: done[key] ? "line-through" : "none", opacity: done[key] ? .55 : 1 }}>{p}</span>
              </label>
            );
          })}
        </div>
      )}

      {/* ціль рівня */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#eff6ff", borderRadius: 10, padding: "9px 12px", fontSize: 12.8 }}>
        <Icon n="trophy" size={15} /> {ns.level_goal.next_level ? t(`Подними навык — общий балл вырастет, и до уровня «${ns.level_goal.next_level}» останется ${ns.level_goal.to_next} XP.`, `Підніми навик — загальний бал зросте, і до рівня «${ns.level_goal.next_level}» лишиться ${ns.level_goal.to_next} XP.`) : t("Ты на максимальном уровне — держи планку!", "Ти на максимальному рівні — тримай планку!")}
      </div>
    </div>
  );
}
