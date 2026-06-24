/* Співробітники — структура компанії (інтелект-карта відділів з drag), список,
 * запрошення по пошті, права відділу/співробітника. */
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

interface Dept { id: number; name: string; parent: number | null; permissions: string[]; color: string; pos_x: number; pos_y: number; members_count: number; eff_permissions: string[]; }
interface Emp { id: number; username: string; full_name: string; email: string; role: number | null; role_name: string; department: number | null; department_name: string; extra_permissions: string[]; denied_permissions: string[]; is_active: boolean; }
interface Invite { id: number; email: string; first_name: string; last_name: string; department: number | null; department_name: string; role: number | null; status: string; link: string; }
interface Perm { code: string; label: string; }
interface Role { id: number; name: string; }

export default function Employees() {
  const { t } = useLang();
  const [tab, setTab] = useState<"map" | "list" | "invites" | "perms">("map");
  const [depts, setDepts] = useState<Dept[]>([]);
  const [emps, setEmps] = useState<Emp[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [perms, setPerms] = useState<Perm[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [msg, setMsg] = useState("");

  function load() {
    api.get<any>("/api/departments/").then((d) => setDepts(d.results || d)).catch(() => {});
    api.get<any>("/api/users/?page_size=500").then((d) => setEmps((d.results || d).filter((u: Emp) => u.is_active))).catch(() => {});
    api.get<any>("/api/invites/").then((d) => setInvites(d.results || d)).catch(() => {});
    api.get<Perm[]>("/api/permissions/").then(setPerms).catch(() => {});
    api.get<any>("/api/roles/").then((d) => setRoles(d.results || d)).catch(() => {});
  }
  useEffect(() => { load(); }, []);

  function flash(m: string) { setMsg(m); setTimeout(() => setMsg(""), 2500); }
  const byDept = (id: number | null) => emps.filter((e) => e.department === id);

  // ── відділи ──
  async function addDept() {
    const name = prompt(t("Название отдела", "Назва відділу")); if (!name) return;
    await api.post("/api/departments/", { name, pos_x: 380, pos_y: 260, color: "#64748b", permissions: [] }); load();
  }
  async function renameDept(d: Dept) {
    const name = prompt(t("Новое название", "Нова назва"), d.name); if (!name) return;
    await api.patch(`/api/departments/${d.id}/`, { name }); load();
  }
  async function delDept(d: Dept) {
    if (!confirm(t(`Удалить отдел «${d.name}»? Сотрудники станут без отдела.`, `Видалити відділ «${d.name}»? Співробітники лишаться без відділу.`))) return;
    await api.del(`/api/departments/${d.id}/`); load();
  }
  async function moveEmp(empId: number, deptId: number | null) {
    await api.patch(`/api/users/${empId}/`, { department: deptId }); flash(t("Перемещено", "Переміщено")); load();
  }
  async function saveDeptPos(id: number, x: number, y: number) { try { await api.patch(`/api/departments/${id}/`, { pos_x: x, pos_y: y }); } catch { /* */ } }
  async function toggleDeptPerm(d: Dept, code: string) {
    const next = d.permissions.includes(code) ? d.permissions.filter((c) => c !== code) : [...d.permissions, code];
    await api.patch(`/api/departments/${d.id}/`, { permissions: next }); load();
  }
  async function toggleUserPerm(e: Emp, code: string, kind: "extra" | "denied") {
    const field = kind === "extra" ? "extra_permissions" : "denied_permissions";
    const cur = (kind === "extra" ? e.extra_permissions : e.denied_permissions) || [];
    const next = cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code];
    await api.patch(`/api/users/${e.id}/`, { [field]: next }); load();
  }

  // ── drag відділу (репозиція) ──
  const dragRef = useRef<{ id: number; ox: number; oy: number; sx: number; sy: number } | null>(null);
  function deptMouseDown(e: React.MouseEvent, d: Dept) {
    dragRef.current = { id: d.id, ox: d.pos_x, oy: d.pos_y, sx: e.clientX, sy: e.clientY };
    function mv(ev: MouseEvent) {
      if (!dragRef.current) return;
      const nx = dragRef.current.ox + (ev.clientX - dragRef.current.sx);
      const ny = dragRef.current.oy + (ev.clientY - dragRef.current.sy);
      setDepts((ds) => ds.map((x) => x.id === dragRef.current!.id ? { ...x, pos_x: nx, pos_y: ny } : x));
    }
    function up() {
      window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up);
      const d2 = dragRef.current; if (d2) { const cur = depts.find((x) => x.id === d2.id); if (cur) saveDeptPos(d2.id, cur.pos_x, cur.pos_y); }
      dragRef.current = null;
    }
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }

  const TABS: [typeof tab, string, string][] = [
    ["map", "🗺 Структура компании", "🗺 Структура компанії"],
    ["list", "👥 Сотрудники", "👥 Співробітники"],
    ["invites", "✉️ Приглашения", "✉️ Запрошення"],
    ["perms", "🛡 Права", "🛡 Права"],
  ];

  return (
    <div className="scroll pad fade">
      <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
        {TABS.map(([k, ru, uk]) => (
          <button key={k} className={"btn" + (tab === k ? " btn-primary" : "")} onClick={() => setTab(k)}>{t(ru, uk)}</button>
        ))}
        {msg && <span style={{ marginLeft: "auto", color: "#16a34a", fontSize: 13, alignSelf: "center" }}>{msg}</span>}
      </div>

      {tab === "map" && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
            <button className="btn btn-green" onClick={addDept}>＋ {t("Добавить отдел", "Додати відділ")}</button>
            <span className="muted" style={{ fontSize: 12 }}>{t("Перетаскивай сотрудника на другой отдел. Двигай отдел за шапку.", "Перетягуй співробітника на інший відділ. Рухай відділ за шапку.")}</span>
          </div>
          <div style={{ position: "relative", minHeight: 560, background: "#fbfaf8", border: "1px solid #ece7df", borderRadius: 14, overflow: "hidden" }}
            onDragOver={(e) => e.preventDefault()}>
            {depts.map((d) => (
              <div key={d.id} style={{ position: "absolute", left: d.pos_x, top: d.pos_y, width: 220, background: "#fff", borderRadius: 12, boxShadow: "0 4px 16px rgba(0,0,0,.1)", border: `2px solid ${d.color || "#cbd5e1"}` }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { const id = Number(e.dataTransfer.getData("emp")); if (id) moveEmp(id, d.id); }}>
                <div onMouseDown={(e) => deptMouseDown(e, d)} style={{ cursor: "move", padding: "8px 10px", background: (d.color || "#64748b") + "1a", borderRadius: "10px 10px 0 0", display: "flex", alignItems: "center", gap: 6 }}>
                  <b style={{ fontSize: 13, flex: 1 }}>{d.name}</b>
                  <span className="muted" style={{ fontSize: 11 }}>{byDept(d.id).length}</span>
                  <span onClick={() => renameDept(d)} title={t("Переименовать", "Перейменувати")} style={{ cursor: "pointer", fontSize: 12 }}>✏️</span>
                  <span onClick={() => delDept(d)} title={t("Удалить", "Видалити")} style={{ cursor: "pointer", fontSize: 12 }}>🗑</span>
                </div>
                <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 4, minHeight: 30 }}>
                  {byDept(d.id).map((e) => (
                    <div key={e.id} draggable onDragStart={(ev) => ev.dataTransfer.setData("emp", String(e.id))}
                      style={{ cursor: "grab", background: "#f1f5f9", borderRadius: 7, padding: "4px 8px", fontSize: 12.5 }}>
                      {e.full_name} <span className="muted" style={{ fontSize: 10.5 }}>{e.role_name || ""}</span>
                    </div>
                  ))}
                  {byDept(d.id).length === 0 && <div className="muted" style={{ fontSize: 11 }}>{t("перетащи сюда", "перетягни сюди")}</div>}
                </div>
              </div>
            ))}
            {/* без відділу */}
            <div style={{ position: "absolute", right: 14, bottom: 14, width: 200, background: "#fff", borderRadius: 12, border: "2px dashed #cbd5e1" }}
              onDragOver={(e) => e.preventDefault()} onDrop={(e) => { const id = Number(e.dataTransfer.getData("emp")); if (id) moveEmp(id, null); }}>
              <div style={{ padding: "8px 10px", fontSize: 12, fontWeight: 600, color: "#64748b" }}>{t("Без отдела", "Без відділу")} ({byDept(null).length})</div>
              <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                {byDept(null).map((e) => (
                  <div key={e.id} draggable onDragStart={(ev) => ev.dataTransfer.setData("emp", String(e.id))}
                    style={{ cursor: "grab", background: "#f1f5f9", borderRadius: 7, padding: "4px 8px", fontSize: 12.5 }}>{e.full_name}</div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "list" && (
        <div className="tablewrap"><table>
          <thead><tr><th>{t("Сотрудник", "Співробітник")}</th><th>{t("Отдел", "Відділ")}</th><th>{t("Роль", "Роль")}</th><th>Email</th></tr></thead>
          <tbody>{emps.map((e) => (<tr key={e.id}><td>{e.full_name}</td><td>{e.department_name || "—"}</td><td>{e.role_name || "—"}</td><td className="muted">{e.email || "—"}</td></tr>))}</tbody>
        </table></div>
      )}

      {tab === "invites" && <InvitesTab depts={depts} roles={roles} invites={invites} reload={load} t={t} />}

      {tab === "perms" && <PermsTab depts={depts} emps={emps} perms={perms} t={t}
        toggleDept={toggleDeptPerm} toggleUser={toggleUserPerm} />}
    </div>
  );
}

// ─────────── Вкладка Запрошення ───────────
function InvitesTab({ depts, roles, invites, reload, t }: any) {
  const [f, setF] = useState({ email: "", first_name: "", last_name: "", department: "", role: "" });
  const [link, setLink] = useState("");
  async function create() {
    if (!f.email.trim()) return;
    const body: any = { email: f.email, first_name: f.first_name, last_name: f.last_name };
    if (f.department) body.department = Number(f.department);
    if (f.role) body.role = Number(f.role);
    const r = await api.post<any>("/api/invites/", body);
    setLink(r.link); setF({ email: "", first_name: "", last_name: "", department: "", role: "" }); reload();
  }
  async function revoke(id: number) { await api.post(`/api/invites/${id}/revoke/`, {}); reload(); }
  const inp = { height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13 } as any;
  return (
    <div style={{ maxWidth: 720 }}>
      <div className="panel">
        <div className="label" style={{ marginBottom: 8 }}>{t("Пригласить сотрудника по почте", "Запросити співробітника по пошті")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <input style={inp} placeholder="Email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          <select style={inp} value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })}>
            <option value="">{t("— отдел —", "— відділ —")}</option>
            {depts.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <input style={inp} placeholder={t("Имя", "Імʼя")} value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} />
          <input style={inp} placeholder={t("Фамилия", "Прізвище")} value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} />
          <select style={inp} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
            <option value="">{t("— роль —", "— роль —")}</option>
            {roles.map((r: any) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
          <button className="btn btn-green" onClick={create}>🔗 {t("Создать ссылку-приглашение", "Створити лінк-запрошення")}</button>
        </div>
        {link && (
          <div style={{ marginTop: 10, padding: 10, background: "#ecfdf5", borderRadius: 8 }}>
            <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{t("Скопируй и отправь сотруднику:", "Скопіюй і надішли співробітнику:")}</div>
            <div style={{ display: "flex", gap: 6 }}>
              <input readOnly value={link} style={{ ...inp, flex: 1 }} onFocus={(e) => e.target.select()} />
              <button className="btn" onClick={() => { navigator.clipboard?.writeText(link); }}>📋</button>
            </div>
          </div>
        )}
      </div>
      <div className="tablewrap" style={{ marginTop: 12 }}><table>
        <thead><tr><th>Email</th><th>{t("Отдел", "Відділ")}</th><th>{t("Статус", "Статус")}</th><th></th></tr></thead>
        <tbody>{invites.map((i: any) => (
          <tr key={i.id}><td>{i.email}</td><td>{i.department_name || "—"}</td>
            <td><span className="chip" style={{ background: i.status === "accepted" ? "#16a34a" : i.status === "pending" ? "#f59e0b" : "#94a3b8" }}>{i.status}</span></td>
            <td>{i.status === "pending" && <><a onClick={() => { navigator.clipboard?.writeText(i.link); }} style={{ cursor: "pointer", marginRight: 8 }}>📋</a><a onClick={() => revoke(i.id)} style={{ cursor: "pointer", color: "#dc2626" }}>{t("отозвать", "відкликати")}</a></>}</td></tr>
        ))}</tbody>
      </table></div>
    </div>
  );
}

// ─────────── Вкладка Права ───────────
function PermsTab({ depts, emps, perms, t, toggleDept, toggleUser }: any) {
  const [mode, setMode] = useState<"dept" | "user">("dept");
  const [selDept, setSelDept] = useState<any>(null);
  const [selUser, setSelUser] = useState<any>(null);
  const d = depts.find((x: any) => x.id === selDept);
  const u = emps.find((x: any) => x.id === selUser);
  const inp = { height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13, minWidth: 220 } as any;
  return (
    <div style={{ maxWidth: 760 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <button className={"btn" + (mode === "dept" ? " btn-primary" : "")} onClick={() => setMode("dept")}>{t("Права отдела", "Права відділу")}</button>
        <button className={"btn" + (mode === "user" ? " btn-primary" : "")} onClick={() => setMode("user")}>{t("Индивидуальные", "Індивідуальні")}</button>
      </div>
      {mode === "dept" ? (
        <div className="panel">
          <select style={inp} value={selDept || ""} onChange={(e) => setSelDept(Number(e.target.value))}>
            <option value="">{t("выбери отдел", "обери відділ")}</option>
            {depts.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
          {d && <div style={{ marginTop: 12 }}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{t("Эти права действуют на ВСЕХ сотрудников отдела:", "Ці права діють на ВСІХ співробітників відділу:")}</div>
            {perms.map((p: any) => (
              <label key={p.code} style={{ display: "flex", gap: 8, padding: "5px 0", fontSize: 13, cursor: "pointer" }}>
                <input type="checkbox" checked={d.permissions.includes(p.code)} onChange={() => toggleDept(d, p.code)} />{p.label}
              </label>
            ))}
          </div>}
        </div>
      ) : (
        <div className="panel">
          <select style={inp} value={selUser || ""} onChange={(e) => setSelUser(Number(e.target.value))}>
            <option value="">{t("выбери сотрудника", "обери співробітника")}</option>
            {emps.map((x: any) => <option key={x.id} value={x.id}>{x.full_name} ({x.department_name || "—"})</option>)}
          </select>
          {u && <div style={{ marginTop: 12 }}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{t("Зелёное = выдать лично, красное = запретить лично (поверх отдела):", "Зелене = видати особисто, червоне = заборонити особисто (поверх відділу):")}</div>
            {perms.map((p: any) => (
              <div key={p.code} style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 0", fontSize: 13 }}>
                <span style={{ flex: 1 }}>{p.label}</span>
                <button className="btn" style={{ padding: "2px 8px", fontSize: 11, background: u.extra_permissions?.includes(p.code) ? "#16a34a" : "#ecfdf5", color: u.extra_permissions?.includes(p.code) ? "#fff" : "#16a34a" }} onClick={() => toggleUser(u, p.code, "extra")}>＋</button>
                <button className="btn" style={{ padding: "2px 8px", fontSize: 11, background: u.denied_permissions?.includes(p.code) ? "#dc2626" : "#fee2e2", color: u.denied_permissions?.includes(p.code) ? "#fff" : "#b91c1c" }} onClick={() => toggleUser(u, p.code, "denied")}>✖</button>
              </div>
            ))}
          </div>}
        </div>
      )}
    </div>
  );
}
