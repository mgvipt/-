/* Співробітники — структура (інтелект-карта зі звʼязками + drag), список, запрошення, права. */
import { Component, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

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
  const [permGroups, setPermGroups] = useState<any[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [funnels, setFunnels] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [linkFrom, setLinkFrom] = useState<number | null>(null); // режим звʼязування: дочірній відділ чекає батька

  function load() {
    api.get<any>("/api/departments/").then((d) => setDepts(((d.results || d) as Dept[]).map((x) => ({ ...x, permissions: x.permissions || [] })))).catch(() => {});
    api.get<any>("/api/users/?page_size=500").then((d) => setEmps(((d.results || d) as Emp[]).filter((u) => u.is_active))).catch(() => {});
    api.get<any>("/api/invites/").then((d) => setInvites(d.results || d)).catch(() => {});
    api.get<any>("/api/permissions/").then((dd) => { setPerms(dd.flat || dd); setPermGroups(dd.groups || []); }).catch(() => {});
    api.get<any>("/api/roles/").then((d) => setRoles(d.results || d)).catch(() => {});
    api.get<any>("/api/funnels/").then((d) => setFunnels(d.results || d)).catch(() => {});
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

  const TABS: [typeof tab, string, string, string][] = [
    ["map", "🗺", "Структура компании", "Структура компанії"],
    ["list", "👥", "Сотрудники", "Співробітники"],
    ["invites", "✉️", "Приглашения", "Запрошення"],
    ["perms", "🛡", "Права", "Права"],
  ];

  return (
    <ErrBoundary>
      <div className="scroll pad fade">
        <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
          {TABS.map(([k, ic, ru, uk]) => <button key={k} className={"btn" + (tab === k ? " btn-primary" : "")} onClick={() => setTab(k)}><Icon n={ic} size={15} /> {t(ru, uk)}</button>)}
          {msg && <span style={{ marginLeft: "auto", color: "#16a34a", fontSize: 13, alignSelf: "center" }}>{msg}</span>}
        </div>

        {tab === "map" && (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
              <button className="btn btn-green" onClick={addDept}>＋ {t("Добавить отдел", "Додати відділ")}</button>
              {linkFrom != null
                ? <span style={{ color: "#C67D5F", fontSize: 13 }}><Icon n="🔗" size={14} /> {t("Кликни родительский отдел…", "Клікни батьківський відділ…")} <a onClick={() => setLinkFrom(null)} style={{ cursor: "pointer", textDecoration: "underline" }}>{t("отмена", "скасувати")}</a></span>
                : <span className="muted" style={{ fontSize: 12 }}>{t("Тащи сотрудника на отдел · двигай отдел за шапку · 🔗 связать с родителем", "Тягни співробітника на відділ · рухай відділ за шапку · 🔗 звʼязати з батьком")}</span>}
            </div>
            <div style={{ position: "relative", height: 600, background: "#fbfaf8", border: "1px solid #ece7df", borderRadius: 14, overflow: "hidden" }} onDragOver={(e) => e.preventDefault()}>
              {/* лінії звʼязків батько→дитина */}
              <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
                {depts.filter((d) => d.parent != null).map((d) => {
                  const p = depts.find((x) => x.id === d.parent); if (!p) return null;
                  const a = center(p), b = center(d);
                  const path = `M ${a.x} ${a.y} C ${a.x} ${(a.y + b.y) / 2}, ${b.x} ${(a.y + b.y) / 2}, ${b.x} ${b.y}`;
                  return (
                    <g key={d.id} style={{ pointerEvents: "stroke", cursor: "pointer" }}
                      onClick={() => { if (confirm(t("Удалить связь?", "Видалити звʼязок?"))) setParent(d.id, null); }}>
                      <title>{t("Клик — удалить связь", "Клік — видалити звʼязок")}</title>
                      <path d={path} stroke="transparent" strokeWidth={14} fill="none" />
                      <path d={path} stroke="#cbb8a8" strokeWidth={2} fill="none" />
                    </g>
                  );
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
                    <span onClick={(e) => { e.stopPropagation(); setLinkFrom(d.id); }} title={t("Связать с родителем", "Звʼязати з батьком")} style={{ cursor: "pointer", fontSize: 12 }}><Icon n="🔗" size={13} /></span>
                    <span onClick={(e) => { e.stopPropagation(); renameDept(d); }} style={{ cursor: "pointer", fontSize: 12 }}><Icon n="✏️" size={13} /></span>
                    <span onClick={(e) => { e.stopPropagation(); delDept(d); }} style={{ cursor: "pointer", fontSize: 12 }}><Icon n="🗑" size={13} /></span>
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
        {tab === "perms" && <PermsTab depts={depts} emps={emps} perms={perms} permGroups={permGroups} funnels={funnels} roles={roles} reload={load} t={t}
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
          <button className="btn btn-green" onClick={create}><Icon n="🔗" size={15} /> {t("Создать ссылку", "Створити лінк")}</button>
        </div>
        {link && <div style={{ marginTop: 10, padding: 10, background: "#ecfdf5", borderRadius: 8 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{t("Скопируй и отправь сотруднику:", "Скопіюй і надішли:")}</div>
          <div style={{ display: "flex", gap: 6 }}><input readOnly value={link} style={{ ...inp, flex: 1 }} onFocus={(e) => e.target.select()} /><button className="btn" onClick={() => navigator.clipboard?.writeText(link)}><Icon n="📋" size={15} /></button></div>
        </div>}
      </div>
      <div className="tablewrap" style={{ marginTop: 12 }}><table>
        <thead><tr><th>Email</th><th>{t("Отдел", "Відділ")}</th><th>{t("Статус", "Статус")}</th><th></th></tr></thead>
        <tbody>{invites.map((i: any) => <tr key={i.id}><td>{i.email}</td><td>{i.department_name || "—"}</td><td><span className="chip" style={{ background: i.status === "accepted" ? "#16a34a" : i.status === "pending" ? "#f59e0b" : "#94a3b8" }}>{i.status}</span></td><td>{i.status === "pending" && <><a onClick={() => navigator.clipboard?.writeText(i.link)} style={{ cursor: "pointer", marginRight: 8 }}><Icon n="📋" size={14} /></a><a onClick={() => revoke(i.id)} style={{ cursor: "pointer", color: "#dc2626" }}>{t("отозвать", "відкликати")}</a></>}</td></tr>)}</tbody>
      </table></div>
    </div>
  );
}

function PermsTab({ depts, emps, perms, permGroups, funnels, roles, reload, t, toggleDept, toggleUser }: any) {
  const [mode, setMode] = useState<"dept" | "user" | "stage">("dept");
  const [selDept, setSelDept] = useState<any>("");
  const [selUser, setSelUser] = useState<any>("");
  const d = depts.find((x: any) => x.id === Number(selDept));
  const u = emps.find((x: any) => x.id === Number(selUser));
  const inp: any = { height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13, minWidth: 240 };
  const groups = (permGroups && permGroups.length) ? permGroups : [{ group: "", items: perms }];

  const Rows = ({ control }: any) => (
    <div style={{ marginTop: 12 }}>
      {groups.map((g: any) => (
        <div key={g.group} style={{ marginBottom: 12 }}>
          {g.group && <div style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8", letterSpacing: 0.3, textTransform: "uppercase", margin: "4px 0 2px" }}>{g.group}</div>}
          {g.items.map((p: any) => (
            <div key={p.code} style={{ display: "flex", gap: 10, alignItems: "center", padding: "7px 0", borderBottom: "0.5px solid #f1f5f9" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13 }}>{p.label}</div>
                {p.hint && <div style={{ fontSize: 11, color: "#94a3b8" }}>{p.hint}</div>}
              </div>
              {control(p)}
            </div>
          ))}
        </div>
      ))}
    </div>
  );

  const inherited = (() => {
    const set = new Set<string>();
    if (u) {
      const dep = depts.find((x: any) => x.id === u.department);
      (dep?.permissions || []).forEach((c: string) => set.add(c));
      const rl = roles.find((x: any) => x.id === u.role);
      (rl?.permissions || []).forEach((c: string) => set.add(c));
    }
    return set;
  })();
  const sw: any = (on: boolean) => ({ width: 44, height: 24, borderRadius: 20, border: "none", cursor: "pointer", background: on ? "#16a34a" : "#cbd5e1", position: "relative", flexShrink: 0 });
  const knob: any = (on: boolean) => ({ position: "absolute", top: 3, left: on ? 23 : 3, width: 18, height: 18, borderRadius: "50%", background: "#fff", transition: "left .15s" });
  const mini: any = { padding: "2px 9px", fontSize: 12, borderRadius: 7, border: "none", cursor: "pointer", fontWeight: 600 };

  return (
    <div style={{ maxWidth: 820 }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <button className={"btn" + (mode === "dept" ? " btn-primary" : "")} onClick={() => setMode("dept")}>{t("Права отдела", "Права відділу")}</button>
        <button className={"btn" + (mode === "user" ? " btn-primary" : "")} onClick={() => setMode("user")}>{t("Индивидуальные", "Індивідуальні")}</button>
        <button className={"btn" + (mode === "stage" ? " btn-primary" : "")} onClick={() => setMode("stage")}><Icon n="🚦" size={15} /> {t("По статусам", "За статусами")}</button>
      </div>
      {mode === "stage" ? (
        <StagePerms funnels={funnels} roles={roles} depts={depts} emps={emps} reload={reload} t={t} />
      ) : mode === "dept" ? (
        <div className="panel">
          <select style={inp} value={selDept} onChange={(e) => setSelDept(e.target.value)}><option value="">{t("выбери отдел", "обери відділ")}</option>{depts.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
          {d && <>
            <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>{t("Действуют на ВСЕХ сотрудников отдела. Нет «видеть все» = сотрудник видит только своё.", "Діють на ВСІХ співробітників відділу. Нема «бачити всі» = співробітник бачить лише своє.")}</div>
            <Rows control={(p: any) => { const on = d.permissions.includes(p.code); return <button onClick={() => toggleDept(d, p.code)} style={sw(on)} aria-label={p.label}><span style={knob(on)} /></button>; }} />
          </>}
        </div>
      ) : (
        <div className="panel">
          <select style={inp} value={selUser} onChange={(e) => setSelUser(e.target.value)}><option value="">{t("выбери сотрудника", "обери співробітника")}</option>{emps.map((x: any) => <option key={x.id} value={x.id}>{x.full_name} ({x.department_name || "—"})</option>)}</select>
          {u && <>
            <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>{t("Серое справа = что есть от отдела/роли. ＋ выдать лично · ✖ запретить лично (запрет важнее всего).", "Сіре праворуч = що є від відділу/ролі. ＋ видати особисто · ✖ заборонити особисто (заборона важливіша за все).")}</div>
            <Rows control={(p: any) => {
              const inh = inherited.has(p.code); const ex = u.extra_permissions?.includes(p.code); const dn = u.denied_permissions?.includes(p.code);
              const eff = dn ? false : (ex || inh);
              return <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 10.5, width: 92, textAlign: "right", color: eff ? "#16a34a" : "#cbd5e1" }}>{dn ? t("✖ запрещено", "✖ заборонено") : eff ? (inh && !ex ? t("✓ от отдела", "✓ від відділу") : t("✓ есть", "✓ є")) : t("— нет", "— нема")}</span>
                <button onClick={() => toggleUser(u, p.code, "extra")} title={t("Выдать лично", "Видати особисто")} style={{ ...mini, background: ex ? "#16a34a" : "#ecfdf5", color: ex ? "#fff" : "#16a34a" }}>＋</button>
                <button onClick={() => toggleUser(u, p.code, "denied")} title={t("Запретить лично", "Заборонити особисто")} style={{ ...mini, background: dn ? "#dc2626" : "#fee2e2", color: dn ? "#fff" : "#b91c1c" }}>✖</button>
              </div>;
            }} />
          </>}
        </div>
      )}
    </div>
  );
}

// ─────────── Права за СТАТУСАМИ ───────────
function StagePerms({ funnels, roles, depts, emps, reload, t }: any) {
  const [funnelId, setFunnelId] = useState<any>("");
  const [subject, setSubject] = useState<string>("");
  const fn = funnels.find((f: any) => String(f.id) === String(funnelId));
  const stages = fn?.stages || [];
  const [type, sid] = subject ? subject.split(":") : ["", ""];
  const subjObj = type === "role" ? roles.find((x: any) => x.id === Number(sid))
    : type === "dept" ? depts.find((x: any) => x.id === Number(sid))
      : type === "user" ? emps.find((x: any) => x.id === Number(sid)) : null;
  const endpoint = type === "role" ? "/api/roles/" : type === "dept" ? "/api/departments/" : "/api/users/";
  const inp: any = { height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13, minWidth: 220 };

  async function toggleAuto(st: any) { await api.patch(`/api/stages/${st.id}/`, { auto_only: !st.auto_only }); reload(); }
  async function toggleSubj(st: any, field: "stage_view_all" | "stage_lock") {
    if (!subjObj) return;
    const arr = (subjObj[field] || []) as number[];
    const next = arr.includes(st.id) ? arr.filter((x) => x !== st.id) : [...arr, st.id];
    await api.patch(`${endpoint}${sid}/`, { [field]: next }); reload();
  }

  return (
    <div className="panel" style={{ maxWidth: 860 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
        <select style={inp} value={funnelId} onChange={(e) => setFunnelId(e.target.value)}>
          <option value="">{t("выбери воронку", "обери воронку")}</option>
          {funnels.map((f: any) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <select style={inp} value={subject} onChange={(e) => setSubject(e.target.value)}>
          <option value="">{t("— кому настраивать (необяз.) —", "— кому (необовʼязково) —")}</option>
          <optgroup label={t("Роли", "Ролі")}>{roles.map((r: any) => <option key={"r" + r.id} value={"role:" + r.id}>{r.name}</option>)}</optgroup>
          <optgroup label={t("Отделы", "Відділи")}>{depts.map((d: any) => <option key={"d" + d.id} value={"dept:" + d.id}>{d.name}</option>)}</optgroup>
          <optgroup label={t("Сотрудники", "Співробітники")}>{emps.map((e: any) => <option key={"u" + e.id} value={"user:" + e.id}>{e.full_name}</option>)}</optgroup>
        </select>
      </div>
      {!fn ? <div className="muted" style={{ fontSize: 12 }}>{t("Выбери воронку, чтобы настроить права по её статусам.", "Обери воронку, щоб налаштувати права за її статусами.")}</div> : (
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead><tr style={{ textAlign: "left", color: "#64748b", fontSize: 11 }}>
            <th style={{ padding: "6px 4px" }}>{t("Статус", "Статус")}</th>
            <th style={{ padding: "6px 4px", textAlign: "center" }}><Icon n="🔒" size={14} /> {t("Только авто", "Тільки авто")}</th>
            {subjObj && <th style={{ padding: "6px 4px", textAlign: "center" }}><Icon n="👁" size={14} /> {t("Видеть все", "Бачити всі")}</th>}
            {subjObj && <th style={{ padding: "6px 4px", textAlign: "center" }}><Icon n="🚫" size={14} /> {t("Запрет перемещения", "Заборона переміщення")}</th>}
          </tr></thead>
          <tbody>{stages.map((st: any) => (
            <tr key={st.id} style={{ borderTop: "1px solid #f1f5f9" }}>
              <td style={{ padding: "6px 4px" }}><span style={{ display: "inline-block", width: 9, height: 9, borderRadius: 3, background: st.color, marginRight: 6, verticalAlign: "middle" }} />{st.name}</td>
              <td style={{ padding: "6px 4px", textAlign: "center" }}><input type="checkbox" checked={!!st.auto_only} onChange={() => toggleAuto(st)} /></td>
              {subjObj && <td style={{ padding: "6px 4px", textAlign: "center" }}><input type="checkbox" checked={(subjObj.stage_view_all || []).includes(st.id)} onChange={() => toggleSubj(st, "stage_view_all")} /></td>}
              {subjObj && <td style={{ padding: "6px 4px", textAlign: "center" }}><input type="checkbox" checked={(subjObj.stage_lock || []).includes(st.id)} onChange={() => toggleSubj(st, "stage_lock")} /></td>}
            </tr>
          ))}</tbody>
        </table>
      )}
      <div className="muted" style={{ fontSize: 11, marginTop: 12, lineHeight: 1.6 }}>
        <Icon n="🔒" size={13} /> {t("Только авто — карточку нельзя перетащить в этот статус вручную (ставит только автоматизация).", "Тільки авто — картку не можна перетягнути в цей статус вручну (ставить лише автоматизація).")}<br />
        <Icon n="👁" size={13} /> {t("Видеть все — выбранные видят ВСЕ карточки в этом статусе, даже чужие.", "Бачити всі — обрані бачать УСІ картки в цьому статусі, навіть чужі.")}<br />
        <Icon n="🚫" size={13} /> {t("Запрет перемещения — выбранным нельзя вручную двигать карточку в этот статус.", "Заборона переміщення — обраним не можна вручну рухати картку в цей статус.")}
      </div>
    </div>
  );
}
