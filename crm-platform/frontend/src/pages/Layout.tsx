import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import { api } from "../api";
import { Avatar } from "../ui";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
import IncomingCallPopup from "../IncomingCallPopup";
import VersionWatcher from "../VersionWatcher";
import Notifier from "../Notifier";
import WebPhone from "../WebPhone";
import GlobalSearch from "../GlobalSearch";

// [путь, заголовок, иконка, требуемое право (или null)]
const NAV: [string, string, string, string, string | null][] = [
  ["/leads", "Лиды", "Ліди", "list", "lead.view"],
  ["/deals", "Сделки", "Угоди", "handshake", "deal.view"],
  ["/inbox", "Чаты · Открытые линии", "Чати · Відкриті лінії", "chat", "inbox.view"],
  ["/tasks", "Задачи", "Задачі", "check", "task.view"],
  ["/contact-center", "Контакт-центр", "Контакт-центр", "🎛️", "roles.manage"],
  ["/phone", "Телефония", "Телефонія", "phone", "telephony.view"],
  ["/warehouse", "Складской учёт", "Складський облік", "package", "warehouse.view"],
  ["/wh", "Отгрузка", "Відвантаження", "truck", "warehouse.view"],
  ["/clients", "Клиенты", "Клієнти", "users", "contact.view"],
  ["/development", "Развитие", "Розвиток", "trophy", "development.view"],
  ["/finance", "Финансы", "Фінанси", "wallet", "finance.view"],
  ["/analytics", "Аналитика", "Аналітика", "chart", "analytics.view"],
  ["/tiktok", "TikTok", "TikTok", "tiktok", "analytics.view"],
  ["/ai-costs", "AI ЦЕНТР", "AI ЦЕНТР", "brain", "settings.agent"],
  ["/employees", "Сотрудники и права", "Співробітники і права", "🛡️", "roles.manage"],
  ["/duplicates", "Дубли", "Дублі", "copy", "roles.manage"],
  ["/settings", "Настройки", "Налаштування", "settings", "roles.manage"],
  ["/whats-new", "Что нового", "Що нового", "bulb", "changelog.view"],
];

const PRESETS = [
  { id: "terracotta", name: "Терракота", sidebar: "#33291f", sidebar2: "#463a30", accent: "#C67D5F", bg: "#f3efe9", topbar: "#ffffff", topbarText: "#0f172a" },
  { id: "ocean", name: "Океан", sidebar: "#0f2942", sidebar2: "#16466e", accent: "#0ea5e9", bg: "#eaf2f8", topbar: "#0f2942", topbarText: "#ffffff" },
  { id: "forest", name: "Ліс", sidebar: "#16271d", sidebar2: "#234735", accent: "#059669", bg: "#edf5ef", topbar: "#ffffff", topbarText: "#0f172a" },
  { id: "graphite", name: "Графіт", sidebar: "#1d1d24", sidebar2: "#30303b", accent: "#6366f1", bg: "#f0f0f4", topbar: "#1d1d24", topbarText: "#ffffff" },
  { id: "royal", name: "Роял", sidebar: "#241b3d", sidebar2: "#3a2c63", accent: "#8b5cf6", bg: "#f1ecfa", topbar: "#ffffff", topbarText: "#0f172a" },
  { id: "sunset", name: "Захід", sidebar: "#3a1c28", sidebar2: "#612f44", accent: "#f43f5e", bg: "#faecef", topbar: "#3a1c28", topbarText: "#ffffff" },
  { id: "midnight", name: "Ніч", sidebar: "#0b1220", sidebar2: "#1b2942", accent: "#38bdf8", bg: "#e8edf4", topbar: "#0b1220", topbarText: "#ffffff" },
  { id: "sand", name: "Пісок", sidebar: "#3a3326", sidebar2: "#524834", accent: "#d97706", bg: "#f7f2e8", topbar: "#ffffff", topbarText: "#0f172a" },
  { id: "coral", name: "Корал", sidebar: "#3a1c28", sidebar2: "#612f44", accent: "#fb7185", bg: "#fff1f2", topbar: "#ffffff", topbarText: "#0f172a" },
  { id: "teal", name: "Бірюза", sidebar: "#0c3b3b", sidebar2: "#155e5e", accent: "#14b8a6", bg: "#ecfeff", topbar: "#0c3b3b", topbarText: "#ffffff" },
  { id: "lavender", name: "Лаванда", sidebar: "#2e2747", sidebar2: "#433a66", accent: "#a78bfa", bg: "#f5f3ff", topbar: "#ffffff", topbarText: "#0f172a" },
  { id: "lime", name: "Лайм", sidebar: "#2a3b0c", sidebar2: "#455e15", accent: "#84cc16", bg: "#f7fee7", topbar: "#ffffff", topbarText: "#0f172a" },
  { id: "amber", name: "Бурштин", sidebar: "#3b2a0c", sidebar2: "#5e4515", accent: "#f59e0b", bg: "#fffbeb", topbar: "#3b2a0c", topbarText: "#ffffff" },
  { id: "fuchsia", name: "Фуксія", sidebar: "#3b0c2a", sidebar2: "#5e1545", accent: "#e879f9", bg: "#fdf4ff", topbar: "#ffffff", topbarText: "#0f172a" },
  { id: "indigo", name: "Індиго", sidebar: "#1e1b4b", sidebar2: "#312e81", accent: "#6366f1", bg: "#eef2ff", topbar: "#1e1b4b", topbarText: "#ffffff" },
  { id: "neon", name: "Фіолет ✦", sidebar: "#0a0e27", sidebar2: "#1b1146", accent: "#a855f7", fx2: "#22d3ee", bg: "#0a0e27", topbar: "#0a0e27", topbarText: "#ffffff", fx: "neon", glass: true, animBg: "night" },
  { id: "cyberpink", name: "Кібер-рожевий ✦", sidebar: "#1a0a1e", sidebar2: "#2d0f33", accent: "#ec4899", fx2: "#06b6d4", bg: "#12081a", topbar: "#1a0a1e", topbarText: "#ffffff", fx: "neon", glass: true, animBg: "flow" },
  { id: "aquaneon", name: "Аква ✦", sidebar: "#04201f", sidebar2: "#0a3a37", accent: "#14b8a6", fx2: "#22d3ee", bg: "#04201f", topbar: "#04201f", topbarText: "#ffffff", fx: "neon", glass: true, animBg: "mint" },
  { id: "electric", name: "Електрик ✦", sidebar: "#0a1030", sidebar2: "#141d4d", accent: "#3b82f6", fx2: "#8b5cf6", bg: "#0a1030", topbar: "#0a1030", topbarText: "#ffffff", fx: "neon", glass: true, animBg: "aurora" },
  { id: "sunsetneon", name: "Захід ✦", sidebar: "#2a0f16", sidebar2: "#451823", accent: "#f59e0b", fx2: "#ec4899", bg: "#1e0a10", topbar: "#2a0f16", topbarText: "#ffffff", fx: "neon", glass: true, animBg: "sunset" },
  { id: "matrix", name: "Матриця ✦", sidebar: "#06160a", sidebar2: "#0d2e15", accent: "#22c55e", fx2: "#84cc16", bg: "#06160a", topbar: "#06160a", topbarText: "#ffffff", fx: "neon", glass: true, animBg: "mint" },
  { id: "lightaqua", name: "Світло-аква ✧", sidebar: "#0c3b3b", sidebar2: "#177878", accent: "#06b6d4", bg: "#ecfeff", topbar: "#ffffff", topbarText: "#0c3b3b", glass: true, animBg: "sea" },
  { id: "lightlav", name: "Світло-лаванда ✧", sidebar: "#3a2c63", sidebar2: "#5641a0", accent: "#8b5cf6", bg: "#f3effe", topbar: "#ffffff", topbarText: "#2e2747", glass: true, animBg: "aurora" },
  { id: "lightrose", name: "Світло-рожевий ✧", sidebar: "#5e1545", sidebar2: "#8a2266", accent: "#ec4899", bg: "#fdf2f8", topbar: "#ffffff", topbarText: "#5e1545", glass: true, animBg: "candy" },
  { id: "snow", name: "Сніг ☀", sidebar: "#eef2f7", sidebar2: "#dde5ee", sidebarText: "#334155", accent: "#0ea5e9", bg: "#f8fafc", topbar: "#ffffff", topbarText: "#0f172a", animBg: "sea" },
  { id: "cream", name: "Крем ☀", sidebar: "#f3ebdd", sidebar2: "#e7d8c0", sidebarText: "#5b4636", accent: "#c08552", bg: "#fbf7f0", topbar: "#ffffff", topbarText: "#3a2e26", animBg: "candy" },
  { id: "mintlt", name: "Мʼята світла ☀", sidebar: "#e3f3ec", sidebar2: "#cbe9dc", sidebarText: "#0f5132", accent: "#10b981", bg: "#f0faf5", topbar: "#ffffff", topbarText: "#0f5132", animBg: "mint" },
  { id: "sky", name: "Небо ☀", sidebar: "#e7f0fb", sidebar2: "#d0e2f4", sidebarText: "#1e3a5f", accent: "#3b82f6", bg: "#f3f8fd", topbar: "#ffffff", topbarText: "#1e3a5f", animBg: "aurora" },
  { id: "nord", name: "Nord", sidebar: "#2e3440", sidebar2: "#3b4252", accent: "#88c0d0", bg: "#eceff4", topbar: "#ffffff", topbarText: "#2e3440" },
  { id: "dracula", name: "Dracula", sidebar: "#282a36", sidebar2: "#383a4a", accent: "#bd93f9", bg: "#f2f0fb", topbar: "#282a36", topbarText: "#ffffff" },
  { id: "tokyo", name: "Tokyo Night", sidebar: "#1a1b26", sidebar2: "#24283b", accent: "#7aa2f7", bg: "#e9ebf5", topbar: "#1a1b26", topbarText: "#ffffff" },
  { id: "catppuccin", name: "Catppuccin", sidebar: "#1e1e2e", sidebar2: "#313244", accent: "#cba6f7", bg: "#f1edf7", topbar: "#ffffff", topbarText: "#1e1e2e" },
  { id: "rosepine", name: "Rosé Pine", sidebar: "#191724", sidebar2: "#26233a", accent: "#ebbcba", bg: "#faf4ed", topbar: "#ffffff", topbarText: "#191724" },
  { id: "solar", name: "Solar", sidebar: "#073642", sidebar2: "#0d4a5a", accent: "#268bd2", bg: "#fdf6e3", topbar: "#073642", topbarText: "#ffffff" },
  { id: "emerald", name: "Смарагд", sidebar: "#0f2e25", sidebar2: "#1b4a3c", accent: "#34d399", bg: "#ecfdf5", topbar: "#ffffff", topbarText: "#0f2e25" },
  { id: "slatepro", name: "Slate Pro", sidebar: "#1e293b", sidebar2: "#334155", accent: "#38bdf8", bg: "#f1f5f9", topbar: "#1e293b", topbarText: "#ffffff" },
  { id: "mocha", name: "Мокко", sidebar: "#3a2e26", sidebar2: "#52423a", accent: "#c08552", bg: "#f6efe6", topbar: "#ffffff", topbarText: "#3a2e26" },
  { id: "plum", name: "Слива", sidebar: "#2d1b30", sidebar2: "#45294a", accent: "#e879f9", bg: "#fdf4ff", topbar: "#ffffff", topbarText: "#2d1b30" },
];
const ANIMBGS = [
  { id: "none", name: "Немає" }, { id: "sea", name: "Море" }, { id: "ocean", name: "Океан" },
  { id: "aurora", name: "Аврора" }, { id: "nebula", name: "Туманність" }, { id: "galaxy", name: "Галактика" },
  { id: "sunset", name: "Захід" }, { id: "forest", name: "Ліс" }, { id: "lava", name: "Лава" },
  { id: "cyber", name: "Кібер" }, { id: "candy", name: "Цукерка" },
];
const SIDEBARS: [string, string][] = [
  ["#33291f", "#463a30"], ["#0f2942", "#16466e"], ["#16271d", "#234735"], ["#1d1d24", "#30303b"],
  ["#241b3d", "#3a2c63"], ["#3a1c28", "#612f44"], ["#0b1220", "#1b2942"], ["#1e293b", "#334155"],
  ["#0c3b3b", "#155e5e"], ["#3b0c2a", "#5e1545"], ["#2a3b0c", "#455e15"], ["#3b2a0c", "#5e4515"],
  ["#1e1b4b", "#312e81"], ["#2e2747", "#433a66"], ["#3a1c1c", "#5e2828"], ["#0c2a3b", "#15455e"],
];
const ACCENTS = ["#C67D5F", "#2a6df4", "#7c3aed", "#0ea5e9", "#059669", "#f43f5e", "#d97706", "#8b5cf6", "#ec4899", "#14b8a6", "#eab308", "#ef4444", "#6366f1", "#10b981", "#f97316", "#06b6d4"];
const BGS = ["#f3efe9", "#eef2f7", "#edf5ef", "#f1ecfa", "#faecef", "#fff7ed", "#ecfeff", "#fef2f2", "linear-gradient(135deg,#e0f2fe,#ede9fe)", "linear-gradient(135deg,#fef3c7,#fde68a)", "linear-gradient(135deg,#d1fae5,#a7f3d0)", "linear-gradient(135deg,#fce7f3,#fbcfe8)"];

// ── Контроль присутності: heartbeat + детектор простою + обов'язкове зняття з авто-паузи ──
const IDLE_WARN_SEC = 60;        // скільки секунд показувати «Ви на місці?» перед авто-паузою
const HEARTBEAT_MS = 90000;      // пульс присутності на сервер (щоб не рахувало «пішов»)
const ACT_KEY = "wc_last_activity";  // спільна мітка активності для ВСІХ вкладок/вікон CRM
function WorkTimer() {
  const [st, setSt] = useState<any>(null);
  const [sec, setSec] = useState(0);
  const [idleWarn, setIdleWarn] = useState(false);   // модалка «Ви на місці?»
  const [countdown, setCountdown] = useState(IDLE_WARN_SEC);
  const [backModal, setBackModal] = useState(false);  // модалка «З поверненням, зняти паузу?»
  const lastAct = useRef(Date.now());
  const lastWrite = useRef(0);         // коли востаннє писали спільну мітку (тротлінг)
  const idleWarnRef = useRef(false);   // чи показана зараз модалка «Ви на місці?»
  // остання активність з урахуванням ІНШИХ вкладок CRM
  const sharedLastAct = () => {
    let shared = 0;
    try { shared = Number(localStorage.getItem(ACT_KEY)) || 0; } catch (e) { /* noop */ }
    return Math.max(lastAct.current, shared);
  };
  const stRef = useRef<any>(null); stRef.current = st;
  // Скільки секунд показувати попередження перед авто-паузою: не більше половини порогу
  // (для малих порогів, напр. 1 хв → 30 сек), і не більше IDLE_WARN_SEC.
  const warnSecFor = (timeoutMin: number) => Math.max(10, Math.min(IDLE_WARN_SEC, Math.floor(timeoutMin * 60 / 2)));

  function load() { api.get<any>("/api/worktime/").then((d) => { setSt(d); setSec(d.worked_seconds || 0); }).catch(() => setSt({ active: false })); }
  useEffect(() => { load(); const _t = setInterval(load, 12000); const _f = () => load(); window.addEventListener("focus", _f); document.addEventListener("visibilitychange", _f); return () => { clearInterval(_t); window.removeEventListener("focus", _f); document.removeEventListener("visibilitychange", _f); }; }, []);
  useEffect(() => {
    if (!st?.active || st?.on_pause) return;
    const t = setInterval(() => setSec((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [st?.active, st?.on_pause]);
  async function act(action: string, reason?: string) {
    const d = await api.post<any>("/api/worktime/", reason ? { action, reason } : { action });
    if (action === "stop") { setSt({ active: false }); setSec(0); } else { setSt(d); setSec(d.worked_seconds || 0); }
  }

  // фіксуємо будь-яку активність користувача — СПІЛЬНО для всіх вкладок/вікон CRM.
  // Активність у будь-якій вкладці = людина працює → в інших вкладках вікно не виринає.
  useEffect(() => {
    const mark = () => {
      const now = Date.now();
      lastAct.current = now;
      // ділимося міткою з іншими вкладками (не частіше разу на 2 сек)
      if (now - lastWrite.current > 2000) {
        lastWrite.current = now;
        try { localStorage.setItem(ACT_KEY, String(now)); } catch (e) { /* noop */ }
      }
      const s = stRef.current;
      // будь-яка активність під час «Ви на місці?» → людина на місці, ховаємо попередження
      if (idleWarnRef.current) { idleWarnRef.current = false; setIdleWarn(false); }
      // повернувся під час авто-паузи (простій) → обов'язково зняти паузу
      if (s?.active && s?.on_pause && s?.pause_reason === "idle" && !backModal) setBackModal(true);
    };
    // перехід на вкладку / фокус вікна — теж ознака присутності
    const evs = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "wheel", "focus"];
    evs.forEach((e) => window.addEventListener(e, mark, { passive: true }));
    const vis = () => { if (document.visibilityState === "visible") mark(); };
    document.addEventListener("visibilitychange", vis);
    // активність в ІНШІЙ вкладці CRM → підтягуємо мітку і ховаємо вікно тут
    const onStorage = (e: StorageEvent) => {
      if (e.key !== ACT_KEY || !e.newValue) return;
      const v = Number(e.newValue) || 0;
      if (v > lastAct.current) lastAct.current = v;
      if (idleWarnRef.current) { idleWarnRef.current = false; setIdleWarn(false); }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      evs.forEach((e) => window.removeEventListener(e, mark));
      document.removeEventListener("visibilitychange", vis);
      window.removeEventListener("storage", onStorage);
    };
  }, [backModal]);

  // ПРИСУТНІСТЬ = вкладка CRM ВІДКРИТА (visible). Поки CRM видно — шлемо «пульс»,
  // і сервер (sweep_worktime) НЕ ставить паузу. Пішов з вкладки CRM (згорнув/перемкнувся
  // в інший застосунок чи вкладку) — пульс зупиняється, і сервер сам поставить авто-паузу
  // за порогом відділу. Так читання чату / розмова по телефону з відкритим CRM НЕ рахується
  // простоєм (раніше детект по миші/клавіатурі ставив хибні паузи присутнім менеджерам).
  useEffect(() => {
    if (!st?.active) return;
    const beat = () => { if (stRef.current?.active && !stRef.current?.on_pause && document.visibilityState === "visible") api.post("/api/worktime/", { action: "heartbeat" }).catch(() => {}); };
    beat();                                   // одразу відмітити присутність
    const hb = setInterval(beat, HEARTBEAT_MS);
    const onVis = () => { if (document.visibilityState === "visible") { beat(); load(); } };  // повернувся на вкладку → пульс + оновити стан (побачити авто-паузу)
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(hb); document.removeEventListener("visibilitychange", onVis); };
  }, [st?.active]);

  const hhmmss = (n: number) => [Math.floor(n / 3600), Math.floor((n % 3600) / 60), n % 60].map((x) => String(x).padStart(2, "0")).join(":");
  if (!st) return null;
  if (!st.active) return <button className="btn btn-primary" style={{ height: 32, padding: "0 12px", fontSize: 13 }} onClick={() => act("start")} title="Почати робочий день — табель відмітиться сам">▶ Почати робочий день</button>;
  return (
    <>
      <div style={{ display: "flex", gap: 6, alignItems: "center", background: "#fff", borderRadius: 8, padding: "3px 8px", border: "1px solid #e2e8f0" }}>
        <span style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 15, color: st.on_pause ? "#d97706" : "#16a34a" }} title="Відпрацьовано сьогодні">{st.on_pause ? (st.pause_reason === "idle" ? "🔴 " : "⏸ ") : "🟢 "}{hhmmss(sec)}</span>
        <button className="btn btn-light" style={{ height: 28, padding: "0 8px", fontSize: 12 }} onClick={() => act("pause")} title="Обід/пауза">{st.on_pause ? "▶ Продовжити" : <><Icon n="☕" size={14} /> Обід</>}</button>
        <button className="btn btn-light" style={{ height: 28, padding: "0 8px", fontSize: 12, color: "#dc2626" }} onClick={() => act("stop")} title="Завершити робочий день">⏹ Завершити</button>
      </div>

      {/* «З поверненням» — обов'язково зняти авто-паузу */}
      {backModal && st.on_pause && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "#fff", borderRadius: 16, padding: 28, maxWidth: 400, textAlign: "center", boxShadow: "0 20px 60px rgba(0,0,0,.3)" }}>
            <div style={{ fontSize: 44 }}>👋</div>
            <div style={{ fontSize: 19, fontWeight: 700, margin: "8px 0" }}>З поверненням!</div>
            <div className="muted" style={{ fontSize: 14, marginBottom: 12 }}>Раді бачити вас знову 🙂</div>
            <button className="btn btn-primary" style={{ height: 42, padding: "0 24px", fontSize: 15 }} onClick={async () => { setBackModal(false); lastAct.current = Date.now(); await act("pause"); }}>▶ Продовжити роботу</button>
          </div>
        </div>
      )}
    </>
  );
}

export default function Layout() {
  const { me, logout, can } = useAuth();
  const loc = useLocation();
  const [showTheme, setShowTheme] = useState(false);
  const [motto, setMotto] = useState(false);
  const [theme, setTheme] = useState<any>(me?.theme ?? {});

  // применяем тему — всі CSS-перемінні блоків + анімації
  useEffect(() => {
    const r = document.documentElement.style;
    if (theme.accent) r.setProperty("--brand", theme.accent);
    r.setProperty("--fx2", theme.fx2 || theme.accent || "#22d3ee");
    r.setProperty("--glass-a", String(theme.glassA != null ? theme.glassA : 0.6));
    r.setProperty("--sidebar-text", theme.sidebarText || "#c5d4e6");
    const darkCards = theme.fx === "neon";
    r.setProperty("--card-text", darkCards ? "#eef2ff" : "#1e293b");
    r.setProperty("--card-text-2", darkCards ? "#aab8d6" : "#475569");
    if (theme.sidebar) r.setProperty("--sidebar", theme.sidebar);
    if (theme.sidebar2) r.setProperty("--sidebar2", theme.sidebar2);
    r.setProperty("--topbar", theme.topbar || "#ffffff");
    r.setProperty("--topbar-text", theme.topbarText || "#0f172a");
    document.body.classList.toggle("anim-on", theme.anim !== false);
    document.body.classList.toggle("glass", !!theme.glass);
    document.body.classList.toggle("fx-neon", theme.fx === "neon");
  }, [theme]);

  function setT(patch: any) { save({ ...theme, ...patch }); }
  function save(t: any) {
    setTheme(t);
    api.patch("/api/me/", { theme: t }).catch(() => {});
  }

  const { t } = useLang();
  const SETTINGS_PERMS = ["settings.sounds", "settings.agent", "settings.automations", "settings.rules", "calc.settings.manage"];
  const items = NAV.filter(([path, , , , perm]) => path === "/settings" ? (can("roles.manage") || SETTINGS_PERMS.some((pp) => can(pp))) : path === "/analytics" ? (can("analytics.view") || can("marketing.view")) : (!perm || can(perm)));
  const _cur = NAV.find(([path]) => loc.pathname.startsWith(path));
  const title = _cur ? t(_cur[1], _cur[2]) : "CRM";
  const fullName = me ? `${me.first_name} ${me.last_name}`.trim() || me.username : "";

  const [yuliaBadge, setYuliaBadge] = useState<{silence_on: boolean; active_count: number} | null>(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const r: any = await api.get("/api/yulia/status/");
        if (alive) setYuliaBadge({silence_on: !!r?.silence_on, active_count: Number(r?.active_count || 0)});
      } catch { /* noop */ }
    };
    load();
    const id = setInterval(load, 30000);
    return () => { alive = false; clearInterval(id); };
  }, []);
  const [tasksToday, setTasksToday] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const sel = (() => { try { return localStorage.getItem("tasks_view_selected") || "mine"; } catch { return "mine"; } })();
        // ЛЕГКО: user_counts отдаёт ТОЛЬКО числа. Раньше кружок тянул /api/tasks/kanban/ целиком (все активные задачи со связями) каждые 60с × каждая вкладка — главная нагрузка (аудит 12.08, docs/АУДИТ-И-КООРДИНАЦИЯ.md).
        const r: any = await api.get("/api/tasks/user_counts/");
        let today = 0;
        if (sel.startsWith("u:")) {
          const uid = Number(sel.slice(2));
          const row = (r?.users || []).find((x: any) => x.id === uid);
          today = row ? (row.today || 0) : 0;
        } else if (sel === "mine" && me) {
          const row = (r?.users || []).find((x: any) => x.id === me.id);
          today = row ? (row.today || 0) : ((r?.total?.today) || 0);
        } else {
          today = (r?.total?.today) || 0;
        }
        if (alive) setTasksToday(today);
      } catch { /* noop */ }
    };
    load();
    const id = setInterval(load, 60000);
    const onChanged = () => load();
    window.addEventListener("tasks-view-changed", onChanged);
    window.addEventListener("storage", onChanged);  // якщо змінили в іншій вкладці
    return () => {
      alive = false; clearInterval(id);
      window.removeEventListener("tasks-view-changed", onChanged);
      window.removeEventListener("storage", onChanged);
    };
  }, []);
  const [navOpen, setNavOpen] = useState(false);
  const [mobMenu, setMobMenu] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth <= 768);
  useEffect(() => {
    const on = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  useEffect(() => { if (!isMobile) setMobMenu(false); }, [isMobile]);
  return (
    <div className="app">
      {theme.animBg && theme.animBg !== "none" && <div className={"appbg viewbg-" + theme.animBg} aria-hidden="true" />}
      {navOpen && <div className="nav-backdrop" onClick={() => setNavOpen(false)} />}
      <aside className={"sidebar" + (navOpen ? " open" : "")}>
        <div className="logo"><div className="logo-badge">W</div><b>Wallcov</b></div>
        <nav className="nav">
          {items.map(([path, ru, uk, icon]) => (
            <NavLink key={path} to={path} className="nav-item" onClick={() => setNavOpen(false)}>
              <span style={{ width: 18, textAlign: "center", display: "inline-flex", justifyContent: "center" }}><Icon n={icon as string} size={17} /></span>
              <span style={{ flex: 1 }}>{t(ru, uk)}</span>
              {path === "/tasks" && tasksToday > 0 && (
                <span style={{ marginLeft: "auto", background: "#dc2626", color: "#fff", borderRadius: 10, padding: "1px 7px", fontSize: 11, fontWeight: 700, minWidth: 18, textAlign: "center", boxShadow: "0 0 0 2px rgba(220,38,38,.18)" }}>{tasksToday}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <WebPhone />
        <div className="me">
          <Avatar name={fullName} cls="av-md" />
          <div style={{ flex: 1 }}>
            <div style={{ color: "var(--sidebar-text, #fff)" }}>{fullName}</div>
            <div style={{ color: "var(--brand)", cursor: "pointer", fontWeight: 500 }} onClick={logout}>Выйти</div>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="burger" onClick={() => setNavOpen((v) => !v)} aria-label="Меню">☰</button>
          {!isMobile && <h1>{title}</h1>}
          {yuliaBadge && (
            <div title={yuliaBadge.silence_on
              ? `Юля в тихому режимі — на зміні ${yuliaBadge.active_count} менеджер(ів). Відповідає в Direct ЗАВЖДИ, але тільки на нетронуті чати через 10 год. Менеджери ведуть самі.`
              : "Юля відповідає всім — усі менеджери на паузі / день закрито. Веде клієнтів у Direct сама, без 10-год паузи."}
              style={{
                marginLeft: 12, display: "flex", alignItems: "center", gap: 6,
                padding: "4px 10px", borderRadius: 20,
                background: yuliaBadge.silence_on ? "#dbeafe" : "#dcfce7",
                color: yuliaBadge.silence_on ? "#1e40af" : "#166534",
                fontSize: 12, fontWeight: 700, whiteSpace: "nowrap",
              }}>
              🤖 Юля: {yuliaBadge.silence_on ? `тихий режим (${yuliaBadge.active_count})` : "відповідає всім"}
            </div>
          )}
          <div className="topbar-motto" onMouseEnter={() => setMotto(true)} onMouseLeave={() => setMotto(false)} onClick={() => setMotto((v) => !v)}
            style={{ position: "relative", marginLeft: isMobile ? 8 : 16, display: "flex", alignItems: "center", gap: 7, cursor: "help" }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--brand)", flexShrink: 0 }} />
            <span style={{ fontWeight: 800, fontSize: isMobile ? 11.5 : 13.5, color: "var(--topbar-text)", whiteSpace: "nowrap" }}>«Держим слово — держим клиента»</span>
            {!isMobile && <Icon n="bulb" size={14} style={{ opacity: .55 }} />}
            {motto && (
              <div onClick={(e) => e.stopPropagation()} style={{ position: "absolute", top: "calc(100% + 12px)", left: 0, width: 480, maxWidth: "82vw", background: "#fff", color: "#1e293b", borderRadius: 18, boxShadow: "0 22px 60px rgba(15,23,42,.30)", padding: "22px 24px", zIndex: 300, border: "1px solid #e8edf3", cursor: "default" }}>
                <div style={{ fontSize: 19, fontWeight: 800, color: "#0f172a" }}>Держим слово — держим клиента</div>
                <div style={{ fontSize: 13.5, color: "var(--brand)", fontWeight: 700, marginTop: 3, marginBottom: 14 }}>Мы продаём не декор. Мы продаём уверенность.</div>
                <div style={{ fontSize: 13, lineHeight: 1.6, color: "#475569", marginBottom: 14 }}>Обещание рождается на первом касании с клиентом — и его держит вся цепочка, каждый из нас. Рвётся одно звено — рвётся слово всей компании.</div>
                {([
                  ["Первое касание / реклама", "Объясняем клиенту, почему важно прийти именно к нам. Цель не просто продать, а решить его вопрос — и дать больше, чем обещали."],
                  ["Менеджер", "Несёт ту же идею, с которой клиент пришёл, не «впаривает». Клиент покупает спокойно — уверенный, что будет как обещали."],
                  ["Производство", "Тонируем точно по цвету, надёжно упаковываем, отгружаем вовремя — чтобы материал доехал в сохранности."],
                  ["Доставка", "Клиент получает посылку — ту и тогда, как договорились."],
                  ["Поддержка клиента", "Убеждаемся, что у клиента получился результат. А если не выходит — делаем всё, чтобы получилось."],
                ] as [string, string][]).map(([h, txt], i) => (
                  <div key={i} style={{ display: "flex", gap: 11, marginBottom: 9 }}>
                    <span style={{ flexShrink: 0, width: 22, height: 22, borderRadius: "50%", background: "var(--brand)", color: "#fff", fontSize: 12, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>{i + 1}</span>
                    <div style={{ fontSize: 12.5, lineHeight: 1.5 }}><b style={{ color: "#0f172a" }}>{h}.</b> <span style={{ color: "#64748b" }}> {txt}</span></div>
                  </div>
                ))}
                <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid #eef2f7", fontSize: 13, fontWeight: 700, color: "#0f172a" }}>Сначала отвечаем друг перед другом. Потом — перед клиентом.</div>
              </div>
            )}
          </div>
          <div className="spacer" />
          <GlobalSearch />
          {!isMobile && <WorkTimer />}
          {!isMobile && <button className="btn btn-light" onClick={() => setShowTheme((v) => !v)}><Icon n="🎨" size={15} /> Тема</button>}
          {!isMobile && <div className="clock">{new Date().toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}</div>}
          {isMobile && (
            <div style={{ position: "relative" }}>
              <button className="btn btn-light" aria-label="Ще" onClick={() => setMobMenu((v) => !v)} style={{ fontSize: 20, lineHeight: 1, padding: "2px 10px" }}>⋯</button>
              {mobMenu && (
                <>
                  <div onClick={() => setMobMenu(false)} style={{ position: "fixed", inset: 0, zIndex: 340 }} />
                  <div style={{ position: "absolute", top: "calc(100% + 8px)", right: 0, background: "#fff", borderRadius: 14, boxShadow: "0 18px 50px rgba(15,23,42,.28)", border: "1px solid #e8edf3", padding: 12, zIndex: 350, minWidth: 210, display: "flex", flexDirection: "column", gap: 10 }}>
                    <WorkTimer />
                    <button className="btn btn-light" onClick={() => { setShowTheme((v) => !v); setMobMenu(false); }} style={{ justifyContent: "center" }}><Icon n="🎨" size={15} /> Тема</button>
                    <div style={{ textAlign: "center", fontSize: 13, color: "#64748b", fontWeight: 700 }}>{new Date().toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}</div>
                  </div>
                </>
              )}
            </div>
          )}
        </header>

        {showTheme && (
          <div className="themebar" style={{ flexWrap: "wrap", rowGap: 10, alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", flexWrap: "wrap" }}>
              <span className="muted" style={{ width: 74, fontSize: 12 }}>{t("Пресеты","Пресети")}:</span>
              {PRESETS.map((p) => (
                <button key={p.id} className="preset-chip" title={p.name} onClick={() => save({ ...theme, ...p, fx: (p as any).fx || "", glass: (p as any).glass || false, animBg: (p as any).animBg || "none", sidebarText: (p as any).sidebarText || "#c5d4e6" })}
                  style={{ borderColor: theme.sidebar === p.sidebar ? p.accent : "transparent", display: "inline-flex", alignItems: "center", gap: 6, height: 28, padding: "0 9px 0 0" }}>
                  <span style={{ display: "inline-flex", height: 28, borderRadius: "7px 0 0 7px", overflow: "hidden" }}>
                    <span style={{ width: 13, height: 28, background: `linear-gradient(165deg,${p.sidebar},${p.sidebar2})`, display: "inline-block" }} />
                    <span style={{ width: 11, height: 28, background: p.accent, display: "inline-block" }} />
                  </span>
                  <span style={{ fontSize: 11.5, whiteSpace: "nowrap", color: "#0f172a" }}>{p.name}</span>
                </button>
              ))}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="muted" style={{ width: 74, fontSize: 12 }}>{t("Сайдбар","Сайдбар")}:</span>
              {SIDEBARS.map(([s, s2]) => <button key={s} className="swatch-lg" title={t("Левый блок","Лівий блок")} style={{ background: `linear-gradient(165deg,${s},${s2})`, borderColor: theme.sidebar === s ? "#0f172a" : "#fff" }} onClick={() => setT({ sidebar: s, sidebar2: s2 })} />)}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="muted" style={{ width: 74, fontSize: 12 }}>{t("Акцент","Акцент")}:</span>
              {ACCENTS.map((a) => <button key={a} className="swatch-lg" style={{ background: a, borderColor: theme.accent === a ? "#0f172a" : "#fff" }} onClick={() => setT({ accent: a })} />)}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="muted" style={{ width: 74, fontSize: 12 }}>{t("Фон","Фон")}:</span>
              {BGS.map((b) => <button key={b} className="swatch-lg" style={{ background: b, borderColor: theme.bg === b ? "#0f172a" : "#fff" }} onClick={() => setT({ bg: b, animBg: "none" })} />)}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="muted" style={{ width: 74, fontSize: 12 }}>{t("Верх","Верх")}:</span>
              <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => setT({ topbar: "#ffffff", topbarText: "#0f172a" })}>{t("Белый","Білий")}</button>
              <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => setT({ topbar: theme.sidebar || "#33291f", topbarText: "#ffffff" })}>{t("Как сайдбар","Як сайдбар")}</button>
              <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => setT({ topbar: theme.accent || "#C67D5F", topbarText: "#ffffff" })}>{t("Акцент","Акцент")}</button>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, width: "100%" }}>
              <span className="muted" style={{ width: 74, fontSize: 12 }}>{t("Анимфон","Анімфон")}:</span>
              {ANIMBGS.map((a) => <button key={a.id} className={"btn btn-light"} style={{ fontSize: 12, fontWeight: (theme.animBg || "none") === a.id ? 700 : 400 }} onClick={() => setT({ animBg: a.id })}>{a.name}</button>)}
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 13 }}>
              <input type="checkbox" checked={!!theme.glass} onChange={(e) => setT({ glass: e.target.checked })} /> <Icon n="🪟" size={15} /> {t("Прозрачность","Прозорість")}
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, minWidth: 210 }}>
              <span className="muted">{t("Прозрачность","Прозорість")}</span>
              <input type="range" min={15} max={95} step={5} value={Math.round((theme.glassA != null ? theme.glassA : 0.6) * 100)} onChange={(e) => setT({ glassA: Number(e.target.value) / 100 })} style={{ flex: 1 }} />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 13 }}>
              <input type="checkbox" checked={theme.anim !== false} onChange={(e) => setT({ anim: e.target.checked })} /> <Icon n="✨" size={15} /> {t("Анимации","Анімації")}
            </label>
            <span className="muted" style={{ fontStyle: "italic", fontSize: 11 }}>({t("сохраняется в профиле","зберігається у профілі")})</span>
          </div>
        )}

        <main className="view" style={{ background: theme.animBg && theme.animBg !== "none" ? "transparent" : theme.bg }}>
          <Outlet />
        </main>
      </div>
      <IncomingCallPopup />
      <VersionWatcher />
      <Notifier />
    </div>
  );
}
