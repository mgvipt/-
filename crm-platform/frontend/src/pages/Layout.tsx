import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import { api } from "../api";
import { Avatar } from "../ui";

// [путь, заголовок, иконка, требуемое право (или null)]
const NAV: [string, string, string, string | null][] = [
  ["/leads", "Лиды", "📋", null],
  ["/deals", "Сделки", "🤝", null],
  ["/inbox", "Чаты · Открытые линии", "💬", null],
  ["/phone", "Телефония", "📞", "telephony.view"],
  ["/warehouse", "Товары · Склад", "📦", "warehouse.view"],
  ["/clients", "Клиенты", "👥", null],
  ["/finance", "Финансы", "💰", "finance.view"],
  ["/analytics", "Аналитика", "📊", null],
  ["/roles", "Сотрудники и права", "🛡️", "roles.manage"],
];

const BGS = [
  "#eef2f7",
  "linear-gradient(135deg,#e0f2fe,#ede9fe)",
  "linear-gradient(135deg,#1e3a8a,#0ea5e9)",
  "linear-gradient(135deg,#0ea5e9,#67e8f9)",
];
const ACCENTS = ["#2a6df4", "#7c3aed", "#0ea5e9", "#059669"];

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

  const items = NAV.filter(([, , , perm]) => !perm || can(perm));
  const title = NAV.find(([path]) => loc.pathname.startsWith(path))?.[1] ?? "CRM";
  const fullName = me ? `${me.first_name} ${me.last_name}`.trim() || me.username : "";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo"><div className="logo-badge">G</div><b>GMIdeas <span>CRM</span></b></div>
        <nav className="nav">
          {items.map(([path, label, icon]) => (
            <NavLink key={path} to={path} className="nav-item">
              <span style={{ width: 18, textAlign: "center" }}>{icon}</span><span>{label}</span>
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
    </div>
  );
}
