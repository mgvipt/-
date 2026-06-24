import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import { api } from "../api";
import { Avatar } from "../ui";
import { useLang } from "../i18n";
import IncomingCallPopup from "../IncomingCallPopup";
import WebPhone from "../WebPhone";

// [путь, заголовок, иконка, требуемое право (или null)]
const NAV: [string, string, string, string, string | null][] = [
  ["/leads", "Лиды", "Ліди", "📋", null],
  ["/deals", "Сделки", "Угоди", "🤝", null],
  ["/inbox", "Чаты · Открытые линии", "Чати · Відкриті лінії", "💬", null],
  ["/contact-center", "Контакт-центр", "Контакт-центр", "🎛️", "roles.manage"],
  ["/phone", "Телефония", "Телефонія", "📞", "telephony.view"],
  ["/warehouse", "Товары · Склад", "Товари · Склад", "📦", "warehouse.view"],
  ["/clients", "Клиенты", "Клієнти", "👥", null],
  ["/finance", "Финансы", "Фінанси", "💰", "finance.view"],
  ["/analytics", "Аналитика", "Аналітика", "📊", null],
  ["/roles", "Сотрудники и права", "Співробітники і права", "🛡️", "roles.manage"],
  ["/settings", "Настройки · Интеграции", "Налаштування · Інтеграції", "⚙️", "roles.manage"],
];

const BGS = [
  "#eef2f7",
  "linear-gradient(135deg,#e0f2fe,#ede9fe)",
  "linear-gradient(135deg,#1e3a8a,#0ea5e9)",
  "linear-gradient(135deg,#0ea5e9,#67e8f9)",
];
const ACCENTS = ["#2a6df4", "#7c3aed", "#0ea5e9", "#059669"];

function WorkTimer() {
  const [st, setSt] = useState<any>(null);
  const [sec, setSec] = useState(0);
  function load() { api.get<any>("/api/worktime/").then((d) => { setSt(d); setSec(d.worked_seconds || 0); }).catch(() => setSt({ active: false })); }
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!st?.active || st?.on_pause) return;
    const t = setInterval(() => setSec((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [st?.active, st?.on_pause]);
  async function act(action: string) {
    const d = await api.post<any>("/api/worktime/", { action });
    if (action === "stop") { setSt({ active: false }); setSec(0); } else { setSt(d); setSec(d.worked_seconds || 0); }
  }
  const hhmmss = (n: number) => [Math.floor(n / 3600), Math.floor((n % 3600) / 60), n % 60].map((x) => String(x).padStart(2, "0")).join(":");
  if (!st) return null;
  if (!st.active) return <button className="btn btn-primary" style={{ height: 32, padding: "0 12px", fontSize: 13 }} onClick={() => act("start")} title="Почати робочий день — табель відмітиться сам">▶ Почати робочий день</button>;
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", background: "#fff", borderRadius: 8, padding: "3px 8px", border: "1px solid #e2e8f0" }}>
      <span style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 15, color: st.on_pause ? "#d97706" : "#16a34a" }} title="Відпрацьовано сьогодні">{st.on_pause ? "⏸ " : "🟢 "}{hhmmss(sec)}</span>
      <button className="btn btn-light" style={{ height: 28, padding: "0 8px", fontSize: 12 }} onClick={() => act("pause")} title="Обід/пауза">{st.on_pause ? "▶ Продовжити" : "☕ Обід"}</button>
      <button className="btn btn-light" style={{ height: 28, padding: "0 8px", fontSize: 12, color: "#dc2626" }} onClick={() => act("stop")} title="Завершити робочий день">⏹ Завершити</button>
    </div>
  );
}

export default function Layout() {
  const { me, logout, can } = useAuth();
  const loc = useLocation();
  const [showTheme, setShowTheme] = useState(false);
  const [theme, setTheme] = useState(me?.theme ?? {});

  // применяем тему
  useEffect(() => {
    if (theme.accent) document.documentElement.style.setProperty("--brand", theme.accent);
  }, [theme.accent]);

  function applyBg(bg: string) { save({ ...theme, bg }); }
  function applyAccent(accent: string) { save({ ...theme, accent }); }
  function save(t: any) {
    setTheme(t);
    api.patch("/api/me/", { theme: t }).catch(() => {});
  }

  const { t } = useLang();
  const items = NAV.filter(([, , , , perm]) => !perm || can(perm));
  const _cur = NAV.find(([path]) => loc.pathname.startsWith(path));
  const title = _cur ? t(_cur[1], _cur[2]) : "CRM";
  const fullName = me ? `${me.first_name} ${me.last_name}`.trim() || me.username : "";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo"><div className="logo-badge">W</div><b>Wallcov</b></div>
        <nav className="nav">
          {items.map(([path, ru, uk, icon]) => (
            <NavLink key={path} to={path} className="nav-item">
              <span style={{ width: 18, textAlign: "center" }}>{icon}</span><span>{t(ru, uk)}</span>
            </NavLink>
          ))}
        </nav>
        <div className="me">
          <Avatar name={fullName} cls="av-md" />
          <div style={{ flex: 1 }}>
            <div style={{ color: "#fff" }}>{fullName}</div>
            <div style={{ color: "#7dd3fc", cursor: "pointer" }} onClick={logout}>Выйти</div>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <h1>{title}</h1>
          <div className="spacer" />
          <input className="search" placeholder="🔍  Поиск по CRM…" />
          <WorkTimer />
          <button className="btn btn-light" onClick={() => setShowTheme((v) => !v)}>🎨 Тема</button>
          <div className="clock">{new Date().toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}</div>
        </header>

        {showTheme && (
          <div className="themebar">
            <span className="muted">Фон:</span>
            {BGS.map((b) => <button key={b} className="swatch" style={{ background: b }} onClick={() => applyBg(b)} />)}
            <span className="muted" style={{ marginLeft: 10 }}>Акцент:</span>
            {ACCENTS.map((a) => <button key={a} className="dot" style={{ background: a }} onClick={() => applyAccent(a)} />)}
            <span className="muted" style={{ marginLeft: 8, fontStyle: "italic" }}>(сохраняется в твоём профиле)</span>
          </div>
        )}

        <main className="view" style={{ background: theme.bg }}>
          <Outlet />
        </main>
      </div>
      <IncomingCallPopup />
      <WebPhone />
    </div>
  );
}
