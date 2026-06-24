/* Співробітники — структура (інтелект-карта зі звʼязками + drag), список, запрошення, права. */
import { Component, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

interface Dept { id: number; name: string; parent: number | null; permissions: string[]; color: string; pos_x: number; pos_y: number; members_count: number; eff_permissions: string[]; }
interface Emp { id: number; username: string; full_name: string; email: string; role: number | null; role_name: string; department: number | null; department_name: string; extra_permissions: string[]; denied_permissions: string[]; is_active: boolean; }
interface Invite { id: number; email: string; department_name: string; status: string; link: string; }
interface Perm { code: string; label: string; }
interface Role { id: number; name: string; }

const NODE_W = 210;

class ErrBoundary extends Component<{ children: any }, { err: boolean }> {
  state = { err: false };
  static getDerivedStateFromError() { return { err: true }; }
  render() { return this.state.err ? <div className="pad muted">Помилка відображення. Онови сторінку (Cmd+Shift+R).</div> : this.props.children; }
}

export default function Employees() {
  const { t } = useLang();
  const [tab, setTab] = useState<"map" | "list" | "invites" | "perms">("map");
  const [depts, setDepts] = useState<Dept[]>([]);
  const [emps, setEmps] = useState<Emp[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [perms, setPerms] = useState<Perm[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [msg, setMsg] = useState("");
  const [linkFrom, setLinkFrom] = useState<number | null>(null); // режим звʼязування: дочірній відділ чекає батька

  function load() {
    api.get<any>("/api/departments/").then((d) => setDepts(((d.results || d) as Dept[]).map((x) => ({ ...x, permissions: x.permissions || [] })))).catch(() => {});
    api.get<any>("/api/users/?page_size=500").then((d) => setEmps(((d.results || d) as Emp[]).filter((u) => u.is_active))).catch(() => {});
    api.get<any>("/api/invites/").then((d) => setInvites(d.results || d)).catch(() => {});
    api.get<Perm[]>("/api/permissions/").then(setPerms).catch(() => {});
    api.get<any>("/api/roles/").then((d) => setRoles(d.results || d)).catch(() => {});
  }
  useEffect(() => { load(); }, []);
  function flash(m: string) { setMsg(m); setTimeout(() => setMsg(""), 2200); }
  const byDept = (id: number | null) => emps.filter((e) => e.department === id);

  async function addDept() { const name = prompt(t("Название отдела", "Назва відділу")); if (!name) return; await api.post("/api/departments/", { name, pos_x: 360, pos_y: 240, color: "#64748b", permissions: [] }); load(); }
  async function renameDept(d: Dept) { const name = prompt(t("Новое название", "Нова назва"), d.name); if (!name) return; await api.patch(`/api/departments/${d.id}/`, { name }); load(); }
  async function delDept(d: Dept) { if (!confirm(t(`Удалить отдел «${d.name}»?`, `Видалити відділ «${d.name}»?`))) return; await api.del(`/api/departments/${d.id}/`); load(); }
  async function moveEmp(empId: number, deptId: number | null) { await api.patch(`/api/users/${empId}/`, { department: deptId }); flash(t("Перемещено", "Переміщено")); load(); }
  async function setParent(childId: number, parentId: number | null) {
    if (childId === parentId) return;
    await api.patch(`/api/departments/${childId}/`, { parent: parentId }); flash(t("Связано", "Звʼязано")); load();
  }

  // ── надійний drag відділу (ref-based, без stale) ──
  const drag = useRef<{ id: number; sx: number; sy: number; bx: number; by: number; cx: number; cy: number } | null>(null);
  function startDeptDrag(e: React.MouseEvent, d: Dept) {
    e.preventDefault(); e.stopPropagation();
    drag.current = { id: d.id, sx: e.clientX, sy: e.clientY, bx: d.pos_x, by: d.pos_y, cx: d.pos_x, cy: d.pos_y };
    const mv = (ev: MouseEvent) => {
      const di = drag.current; if (!di) return;
      di.cx = di.bx + (ev.clientX - di.sx); di.cy = di.by + (ev.clientY - di.sy);
      setDepts((ds) => ds.map((x) => x.id === di.id ? { ...x, pos_x: di.cx, pos_y: di.cy } : x));
    };
    const up = () => {
      window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up);
      const di = drag.current; drag.current = null;
      if (di) api.patch(`/api/departments/${di.id}/`, { pos_x: Math.round(di.cx), pos_y: Math.round(di.cy) }).catch(() => {});
    };
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }

  function nodeClick(d: Dept) {
    if (linkFrom == null) return;
    if (linkFrom === d.id) { setLinkFrom(null); return; }
    setParent(linkFrom, d.id); setLinkFrom(null);
  }

  const center = (d: Dept) => ({ x: d.pos_x + NODE_W / 2, y: d.pos_y + 18 });

  const TABS: [typeof tab, string, string][] = [
    ["map", "🗺 Структура компании", "🗺 Структура компанії"],
    ["list", "👥 Сотрудники", "👥 Співробітники"],
    ["invites", "✉️ Приглашения", "✉️ Запрошення"],
    ["perms", "🛡 Права", "🛡 Права"],
  ];

  return (
    <ErrBoundary>
      <div className="scroll pad fade">
        <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
          {TABS.map(([k, ru, uk]) => <button key={k} className={"btn" + (tab === k ? " btn-primary" : "")} onClick={() => setTab(k)}>{t(ru, uk)}</button>)}
          {msg && <span style={{ marginLeft: "auto", color: "#16a34a", fontSize: 13, alignSelf: "center" }}>{msg}</span>}
        </div>

        {tab === "map" && (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
              <button className="btn btn-green" onClick={addDept}>＋ {t("Добавить отдел", "Додати відділ")}</button>
              {linkFrom != null
                ? <span style={{ color: "#C67D5F", fontSize: 13 }}>🔗 {t("Кликни родительский отдел…", "Клікни батьківський відділ…")} <a onClick={() => setLinkFrom(null)} style={{ cursor: "pointer", textDecoration: "underline" }}>{t("отмена", "скасувати")}</a></span>
                : <span className="muted" style={{ fontSize: 12 }}>{t("Тащи сотрудника на отдел · двигай отдел за шапку · 🔗 связать с родителем", "Тягни співробітника на відділ · рухай відділ за шапку · 🔗 звʼязати з батьком")}</span>}
            </div>
            <div style={{ position: "relative", height: 600, background: "#fbfaf8", border: "1px solid #ece7df", borderRadius: 14, overflow: "hidden" }} onDragOver={(e) => e.preventDefault()}>
              {/* лінії звʼязків батько→дитина */}
              <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
                {depts.filter((d) => d.parent != null).map((d) => {
                  const p = depts.find((x) => x.id === d.parent); if (!p) return null;
                  const a = center(p), b = center(d);
                  return <path key={d.id} d={`M ${a.x} ${a.y} C ${a.x} ${(a.y + b.y) / 2}, ${b.x} ${(a.y + b.y) / 2}, ${b.x} ${b.y}`} stroke="#cbb8a8" strokeWidth={2} fill="none" />;
                })}
              </svg>
              {depts.map((d) => (
                <div key={d.id} style={{ position: "absolute", left: d.pos_x, top: d.pos_y, width: NODE_W, background: "#fff", borderRadius: 12, boxShadow: "0 4px 16px rgba(0,0,0,.1)", border: `2px solid ${linkFrom === d.id ? "#C67D5F" : (d.color || "#cbd5e1")}` }}
                  onClick={() => nodeClick(d)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => { const id = Number(e.dataTransfer.getData("emp")); if (id) moveEmp(id, d.id); }}>
                  <div onMouseDown={(e) => startDeptDrag(e, d)} style={{ cursor: "move", padding: "7px 9px", background: (d.color || "#64748b") + "1a", borderRadius: "10px 10px 0 0", display: "flex", alignItems: "center", gap: 5 }}>
                    <b style={{ fontSize: 12.5, flex: 1 }}>{d.name}</b>
                    <span className="muted" style={{ fontSize: 11 }}>{byDept(d.id).length}</span>
                    <span onClick={(e) => { e.stopPropagation(); setLinkFrom(d.id); }} title={t("Связать с родителем", "Звʼязати з батьком")} style={{ cursor: "pointer", fontSize: 12 }}>🔗</span>
                    <span onClick={(e) => { e.stopPropagation(); renameDept(d); }} style={{ cursor: "pointer", fontSize: 12 }}>✏️</span>
                    <span onClick={(e) => { e.stopPropagation(); delDept(d); }} style={{ cursor: "pointer", fontSize: 12 }}>🗑</span>
                  </div>
                  <div style={{ padding: 7, display: "flex", flexDirection: "column", gap: 4, minHeight: 26 }}>
                    {byDept(d.id).map((e) => (
                      <div key={e.id} draggable onDragStart={(ev) => ev.dataTransfer.setData("emp", String(e.id))}
                        style={{ cursor: "grab", background: "#f1f5f9", borderRadius: 7, padding: "3px 8px", fontSize: 12 }}>
                        {e.full_name} {e.role_name && <span className="muted" style={{ fontSize: 10 }}>· {e.role_name}</span>}
                      </div>
                    ))}
                    {d.parent != null && <div className="muted" style={{ fontSize: 10 }}>↳ {depts.find((x) => x.id === d.parent)?.name} <a onClick={(ev) => { ev.stopPropagation(); setParent(d.id, null); }} style={{ cursor: "pointer" }}>✖</a></div>}
                  </div>
                </div>
              ))}
              <div style={{ position: "absolute", right: 14, bottom: 14, width: 190, background: "#fff", borderRadius: 12, border: "2px dashed #cbd5e1" }}
                onDragOver={(e) => e.preventDefault()} onDrop={(e) => { const id = Number(e.dataTransfer.getData("emp")); if (id) moveEmp(id, null); }}>
                <div style={{ padding: "7px 9px", fontSize: 12, fontWeight: 600, color: "#64748b" }}>{t("Без отдела", "Без відділу")} ({byDept(null).length})</div>
                <div style={{ padding: 7, display: "flex", flexDirection: "column", gap: 4 }}>
                  {byDept(null).map((e) => (
                    <div key={e.id} draggable onDragStart={(ev) => ev.dataTransfer.setData("emp", String(e.id))}
                      style={{ cursor: "grab", background: "#f1f5f9", borderRadius: 7, padding: "3px 8px", fontSize: 12 }}>{e.full_name}</div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {tab === "list" && (
          <div className="tablewrap"><table>
            <thead><tr><th>{t("Сотрудник", "Співробітник")}</th><th>{t("Отдел", "Відділ")}</th><th>{t("Роль", "Роль")}</th><th>Email</th></tr></thead>
            <tbody>{emps.map((e) => <tr key={e.id}><td>{e.full_name}</td><td>{e.department_name || "—"}</td><td>{e.role_name || "—"}</td><td className="muted">{e.email || "—"}</td></tr>)}</tbody>
          </table></div>
        )}
        {tab === "invites" && <InvitesTab depts={depts} roles={roles} invites={invites} reload={load} t={t} />}
        {tab === "perms" && <PermsTab depts={depts} emps={emps} perms={perms} t={t}
          toggleDept={async (d: Dept, code: string) => { const next = d.permissions.includes(code) ? d.permissions.filter((c) => c !== code) : [...d.permissions, code]; await api.patch(`/api/departments/${d.id}/`, { permissions: next }); load(); }}
          toggleUser={async (e: Emp, code: string, kind: "extra" | "denied") => { const field = kind === "extra" ? "extra_permissions" : "denied_permissions"; const cur = (kind === "extra" ? e.extra_permissions : e.denied_permissions) || []; const next = cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code]; await api.patch(`/api/users/${e.id}/`, { [field]: next }); load(); }} />}
      </div>
    </ErrBoundary>
  );
}

function InvitesTab({ depts, roles, invites, reload, t }: any) {
  const [f, setF] = useState({ email: "", first_name: "", last_name: "", department: "", role: "" });
  const [link, setLink] = useState("");
  async function create() { if (!f.email.trim()) return; const body: any = { email: f.email, first_name: f.first_name, last_name: f.last_name }; if (f.department) body.department = Number(f.department); if (f.role) body.role = Number(f.role); const r = await api.post<any>("/api/invites/", body); setLink(r.link); setF({ email: "", first_name: "", last_name: "", department: "", role: "" }); reload(); }
  async function revoke(id: number) { await api.post(`/api/invites/${id}/revoke/`, {}); reload(); }
  const inp: any = { height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13 };
  return (
    <div style={{ maxWidth: 720 }}>
      <div className="panel">
        <div className="label" style={{ marginBottom: 8 }}>{t("Пригласить сотрудника по почте", "Запросити співробітника по пошті")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <input style={inp} placeholder="Email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          <select style={inp} value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })}><option value="">{t("— отдел —", "— відділ —")}</option>{depts.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
          <input style={inp} placeholder={t("Имя", "Імʼя")} value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} />
          <input style={inp} placeholder={t("Фамилия", "Прізвище")} value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} />
          <select style={inp} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="">{t("— роль —", "— роль —")}</option>{roles.map((r: any) => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
          <button className="btn btn-green" onClick={create}>🔗 {t("Создать ссылку", "Створити лінк")}</button>
        </div>
        {link && <div style={{ marginTop: 10, padding: 10, background: "#ecfdf5", borderRadius: 8 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{t("Скопируй и отправь сотруднику:", "Скопіюй і надішли:")}</div>
          <div style={{ display: "flex", gap: 6 }}><input readOnly value={link} style={{ ...inp, flex: 1 }} onFocus={(e) => e.target.select()} /><button className="btn" onClick={() => navigator.clipboard?.writeText(link)}>📋</button></div>
        </div>}
      </div>
      <div className="tablewrap" style={{ marginTop: 12 }}><table>
        <thead><tr><th>Email</th><th>{t("Отдел", "Відділ")}</th><th>{t("Статус", "Статус")}</th><th></th></tr></thead>
        <tbody>{invites.map((i: any) => <tr key={i.id}><td>{i.email}</td><td>{i.department_name || "—"}</td><td><span className="chip" style={{ background: i.status === "accepted" ? "#16a34a" : i.status === "pending" ? "#f59e0b" : "#94a3b8" }}>{i.status}</span></td><td>{i.status === "pending" && <><a onClick={() => navigator.clipboard?.writeText(i.link)} style={{ cursor: "pointer", marginRight: 8 }}>📋</a><a onClick={() => revoke(i.id)} style={{ cursor: "pointer", color: "#dc2626" }}>{t("отозвать", "відкликати")}</a></>}</td></tr>)}</tbody>
      </table></div>
    </div>
  );
}

function PermsTab({ depts, emps, perms, t, toggleDept, toggleUser }: any) {
  const [mode, setMode] = useState<"dept" | "user">("dept");
  const [selDept, setSelDept] = useState<any>("");
  const [selUser, setSelUser] = useState<any>("");
  const d = depts.find((x: any) => x.id === Number(selDept));
  const u = emps.find((x: any) => x.id === Number(selUser));
  const inp: any = { height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13, minWidth: 240 };
  return (
    <div style={{ maxWidth: 760 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <button className={"btn" + (mode === "dept" ? " btn-primary" : "")} onClick={() => setMode("dept")}>{t("Права отдела", "Права відділу")}</button>
        <button className={"btn" + (mode === "user" ? " btn-primary" : "")} onClick={() => setMode("user")}>{t("Индивидуальные", "Індивідуальні")}</button>
      </div>
      {mode === "dept" ? (
        <div className="panel">
          <select style={inp} value={selDept} onChange={(e) => setSelDept(e.target.value)}><option value="">{t("выбери отдел", "обери відділ")}</option>{depts.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
          {d && <div style={{ marginTop: 12 }}><div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{t("Действуют на ВСЕХ сотрудников отдела:", "Діють на ВСІХ співробітників відділу:")}</div>{perms.map((p: any) => <label key={p.code} style={{ display: "flex", gap: 8, padding: "5px 0", fontSize: 13, cursor: "pointer" }}><input type="checkbox" checked={d.permissions.includes(p.code)} onChange={() => toggleDept(d, p.code)} />{p.label}</label>)}</div>}
        </div>
      ) : (
        <div className="panel">
          <select style={inp} value={selUser} onChange={(e) => setSelUser(e.target.value)}><option value="">{t("выбери сотрудника", "обери співробітника")}</option>{emps.map((x: any) => <option key={x.id} value={x.id}>{x.full_name} ({x.department_name || "—"})</option>)}</select>
          {u && <div style={{ marginTop: 12 }}><div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{t("Зелёное = выдать лично, красное = запретить лично:", "Зелене = видати, червоне = заборонити особисто:")}</div>{perms.map((p: any) => <div key={p.code} style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 0", fontSize: 13 }}><span style={{ flex: 1 }}>{p.label}</span><button className="btn" style={{ padding: "2px 8px", fontSize: 11, background: u.extra_permissions?.includes(p.code) ? "#16a34a" : "#ecfdf5", color: u.extra_permissions?.includes(p.code) ? "#fff" : "#16a34a" }} onClick={() => toggleUser(u, p.code, "extra")}>＋</button><button className="btn" style={{ padding: "2px 8px", fontSize: 11, background: u.denied_permissions?.includes(p.code) ? "#dc2626" : "#fee2e2", color: u.denied_permissions?.includes(p.code) ? "#fff" : "#b91c1c" }} onClick={() => toggleUser(u, p.code, "denied")}>✖</button></div>)}</div>}
        </div>
      )}
    </div>
  );
}
