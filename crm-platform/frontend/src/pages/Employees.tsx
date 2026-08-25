/* Співробітники — структура (інтелект-карта зі звʼязками + drag), список, запрошення, права. */
import { Component, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

interface Dept { id: number; name: string; parent: number | null; permissions: string[]; color: string; pos_x: number; pos_y: number; members_count: number; eff_permissions: string[]; idle_timeout_min?: number; }
interface Emp { id: number; username: string; full_name: string; email: string; role: number | null; role_name: string; department: number | null; department_name: string; extra_permissions: string[]; denied_permissions: string[]; is_active: boolean; account_kind?: "client" | "staff"; employment_status?: string; dismissed_at?: string | null; date_joined?: string; photo?: string; position?: string; birthday?: string | null; about?: string; interests?: string; telegram?: string; phone?: string; on_shift?: boolean; shift_paused?: boolean; }
interface Invite { id: number; email: string; department_name: string; status: string; link: string; }
interface Perm { code: string; label: string; }
interface Role { id: number; name: string; }
interface RepairStageReview { id: number; project_uuid: string; project_title: string; contact_id: number | null; contact_name: string; requested_by_id: number | null; requested_by_name: string; stage_id: string; title: string; status: string; note: string; created_at: string; }

const NODE_W = 210;

// ── Аватар: фото/лого якщо є, інакше ініціали кольором ──
function initialsOf(name: string) { return (name || "?").split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("").toUpperCase(); }
function colorOf(name: string) { let h = 0; for (let i = 0; i < (name || "").length; i++) h = (h * 31 + name.charCodeAt(i)) % 360; return `hsl(${h} 45% 62%)`; }
function PhotoAvatar({ photo, name, size = 34 }: { photo?: string; name: string; size?: number }) {
  const st: any = { width: size, height: size, borderRadius: "50%", flexShrink: 0, objectFit: "cover" };
  if (photo) return <img src={photo} alt={name} style={st} />;
  return <span style={{ ...st, background: colorOf(name), color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.38, fontWeight: 700 }}>{initialsOf(name)}</span>;
}
// ── Зелений бейдж «зараз на робочому дні» ──
function ShiftBadge({ on, paused, t }: { on?: boolean; paused?: boolean; t: any }) {
  if (!on) return null;
  return paused
    ? <span title={t("На смене, но на паузе/обеде", "На зміні, але на паузі/обіді")} style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: "#fef9c3", color: "#a16207", whiteSpace: "nowrap" }}>⏸ {t("Пауза", "Пауза")}</span>
    : <span title={t("Рабочий день идёт прямо сейчас", "Робочий день триває просто зараз")} style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: "#dcfce7", color: "#16a34a", whiteSpace: "nowrap" }}>🟢 {t("На работе", "На роботі")}</span>;
}

class ErrBoundary extends Component<{ children: any }, { err: boolean }> {
  state = { err: false };
  static getDerivedStateFromError() { return { err: true }; }
  render() { return this.state.err ? <div className="pad muted">Помилка відображення. Онови сторінку (Cmd+Shift+R).</div> : this.props.children; }
}

export default function Employees() {
  const { t } = useLang();
  const [tab, setTab] = useState<"map" | "list" | "registrations" | "activity" | "invites" | "perms">(() => (localStorage.getItem("emp_tab") as any) || "map");
  const [listStatus, setListStatus] = useState<"active" | "inactive" | "dismissed" | "all">("active");
  const [listEmps, setListEmps] = useState<Emp[]>([]);
  const [registrations, setRegistrations] = useState<Emp[]>([]);
  const [registrationsTotal, setRegistrationsTotal] = useState(0);
  const [registrationsLoading, setRegistrationsLoading] = useState(false);
  const [registrationsError, setRegistrationsError] = useState("");
  const [rolesLoadError, setRolesLoadError] = useState("");
  const [departmentsLoadError, setDepartmentsLoadError] = useState("");
  const [promotingId, setPromotingId] = useState<number | null>(null);
  const [promotionChoices, setPromotionChoices] = useState<Record<number, { role: string; department: string }>>({});
  const [promotionErrors, setPromotionErrors] = useState<Record<number, string>>({});
  const [repairReviews, setRepairReviews] = useState<RepairStageReview[]>([]);
  const [repairReviewsLoading, setRepairReviewsLoading] = useState(false);
  const [repairReviewsError, setRepairReviewsError] = useState("");
  const [repairReviewNotes, setRepairReviewNotes] = useState<Record<number, string>>({});
  const [repairReviewErrors, setRepairReviewErrors] = useState<Record<number, string>>({});
  const [repairReviewingId, setRepairReviewingId] = useState<number | null>(null);
  const [cardEmp, setCardEmp] = useState<Emp | null>(null);   // відкрита картка співробітника
  const [me, setMe] = useState<any>(null);
  useEffect(() => { try { localStorage.setItem("emp_tab", tab); } catch (e) { /* noop */ } }, [tab]);
  const [depts, setDepts] = useState<Dept[]>([]);
  const [emps, setEmps] = useState<Emp[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [perms, setPerms] = useState<Perm[]>([]);
  const [permGroups, setPermGroups] = useState<any[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [funnels, setFunnels] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [linkFrom, setLinkFrom] = useState<number | null>(null); // режим звʼязування: дочірній відділ чекає батька
  const canManageRoles = !!(me?.is_superuser || me?.permissions?.includes("roles.manage"));

  function load() {
    setDepartmentsLoadError("");
    api.get<any>("/api/departments/?page_size=500")
      .then((d) => setDepts(((d.results || d) as Dept[]).map((x) => ({ ...x, permissions: x.permissions || [] }))))
      .catch(() => setDepartmentsLoadError(t("Не удалось загрузить список отделов. Обновите страницу или проверьте доступ администратора.", "Не вдалося завантажити список відділів. Оновіть сторінку або перевірте доступ адміністратора.")));
    api.get<any>("/api/users/?account_kind=staff&page_size=500").then((d) => setEmps(((d.results || d) as Emp[]).filter((u) => u.is_active && u.account_kind !== "client"))).catch(() => {});
    api.get<any>("/api/invites/").then((d) => setInvites(d.results || d)).catch(() => {});
    api.get<any>("/api/permissions/").then((dd) => { setPerms(dd.flat || dd); setPermGroups(dd.groups || []); }).catch(() => {});
    setRolesLoadError("");
    api.get<any>("/api/roles/?page_size=500")
      .then((d) => setRoles(d.results || d))
      .catch(() => setRolesLoadError(t("Не удалось загрузить список ролей. Обновите страницу или проверьте доступ администратора.", "Не вдалося завантажити список ролей. Оновіть сторінку або перевірте доступ адміністратора.")));
    api.get<any>("/api/funnels/").then((d) => setFunnels(d.results || d)).catch(() => {});
    api.get<any>("/api/me/").then(setMe).catch(() => {});
  }
  useEffect(() => { load(); loadRegistrations(); }, []);
  // список сотрудников для вкладки «Список» — с фильтром по статусу занятости
  function loadList() {
    api.get<any>(`/api/users/?account_kind=staff&status=${listStatus}&page_size=500`).then((d) => setListEmps(((d.results || d) as Emp[]).filter((u) => u.account_kind !== "client"))).catch(() => {});
  }
  useEffect(() => { if (tab === "list") loadList(); /* eslint-disable-next-line */ }, [tab, listStatus]);
  useEffect(() => { if (tab === "registrations" && canManageRoles) loadRepairReviews(); /* eslint-disable-next-line */ }, [tab, canManageRoles]);
  function flash(m: string) { setMsg(m); setTimeout(() => setMsg(""), 2200); }
  const byDept = (id: number | null) => emps.filter((e) => e.department === id);

  function loadRepairReviews() {
    setRepairReviewsLoading(true); setRepairReviewsError("");
    api.get<any>("/api/zamer/reviews/?status=pending")
      .then((d) => setRepairReviews((d.results || d) as RepairStageReview[]))
      .catch((err: any) => {
        setRepairReviews([]);
        setRepairReviewsError(err?.response?.data?.detail || t("Не удалось загрузить проверки этапов ремонта. Обновите страницу или проверьте право управления ролями.", "Не вдалося завантажити перевірки етапів ремонту. Оновіть сторінку або перевірте право керування ролями."));
      })
      .finally(() => setRepairReviewsLoading(false));
  }

  function setRepairReviewNote(reviewId: number, value: string) {
    setRepairReviewNotes((prev) => ({ ...prev, [reviewId]: value }));
    setRepairReviewErrors((prev) => { const next = { ...prev }; delete next[reviewId]; return next; });
  }

  async function decideRepairReview(review: RepairStageReview, status: "accepted" | "rework") {
    const note = (repairReviewNotes[review.id] || "").trim();
    if (status === "rework" && !note) {
      setRepairReviewErrors((prev) => ({ ...prev, [review.id]: t("Укажите, что клиенту нужно исправить", "Вкажіть, що клієнту потрібно виправити") }));
      return;
    }
    if (status === "accepted" && !confirm(t(
      `Принять этап «${review.title || review.stage_id}» по проекту «${review.project_title || review.project_uuid}»?`,
      `Прийняти етап «${review.title || review.stage_id}» за проєктом «${review.project_title || review.project_uuid}»?`))) return;
    setRepairReviewingId(review.id);
    setRepairReviewErrors((prev) => { const next = { ...prev }; delete next[review.id]; return next; });
    try {
      await api.patch(`/api/zamer/reviews/${review.id}/`, status === "rework" ? { status, note } : { status });
      setRepairReviews((rows) => rows.filter((row) => row.id !== review.id));
      setRepairReviewNotes((prev) => { const next = { ...prev }; delete next[review.id]; return next; });
      setRepairReviewErrors((prev) => { const next = { ...prev }; delete next[review.id]; return next; });
      flash(status === "accepted" ? t("Этап принят", "Етап прийнято") : t("Этап возвращён на доработку", "Етап повернуто на доопрацювання"));
    } catch (err: any) {
      setRepairReviewErrors((prev) => ({ ...prev, [review.id]: err?.response?.data?.detail || t("Не удалось сохранить решение", "Не вдалося зберегти рішення") }));
    } finally {
      setRepairReviewingId(null);
    }
  }

  function loadRegistrations() {
    setRegistrationsLoading(true); setRegistrationsError("");
    api.get<any>("/api/users/?account_kind=client&page_size=500")
      .then((d) => {
        const rows = ((d.results || d) as Emp[]).filter((u) => u.account_kind !== "staff");
        setRegistrations(rows);
        setRegistrationsTotal(typeof d?.count === "number" ? d.count : rows.length);
      })
      .catch((err: any) => {
        setRegistrations([]);
        setRegistrationsTotal(0);
        setRegistrationsError(err?.response?.data?.detail || t("Не удалось загрузить очередь регистраций. Обновите страницу или проверьте доступ администратора.", "Не вдалося завантажити чергу реєстрацій. Оновіть сторінку або перевірте доступ адміністратора."));
      })
      .finally(() => setRegistrationsLoading(false));
  }

  function setPromotionChoice(userId: number, field: "role" | "department", value: string) {
    setRegistrationsError("");
    setPromotionErrors((prev) => { const next = { ...prev }; delete next[userId]; return next; });
    setPromotionChoices((prev) => ({
      ...prev,
      [userId]: { role: prev[userId]?.role || "", department: prev[userId]?.department || "", [field]: value },
    }));
  }

  async function promoteRegistration(e: Emp) {
    const choice = promotionChoices[e.id] || { role: "", department: "" };
    if (!choice.role || !choice.department) {
      setPromotionErrors((prev) => ({ ...prev, [e.id]: t("Сначала явно выберите роль и отдел", "Спочатку явно оберіть роль і відділ") }));
      return;
    }
    const roleId = choice.role === "none" ? null : Number(choice.role);
    const departmentId = choice.department === "none" ? null : Number(choice.department);
    const roleName = roleId == null ? t("без роли", "без ролі") : (roles.find((r) => r.id === roleId)?.name || "—");
    const departmentName = departmentId == null ? t("без отдела", "без відділу") : (depts.find((d) => d.id === departmentId)?.name || "—");
    const displayName = e.full_name || e.username || e.email || `#${e.id}`;
    if (!confirm(t(
      `Назначить «${displayName}» сотрудником?\n\nРоль: ${roleName}\nОтдел: ${departmentName}\n\nПосле подтверждения пользователь появится в структуре сотрудников.`,
      `Призначити «${displayName}» співробітником?\n\nРоль: ${roleName}\nВідділ: ${departmentName}\n\nПісля підтвердження користувач зʼявиться у структурі співробітників.`))) return;
    setPromotingId(e.id); setRegistrationsError("");
    setPromotionErrors((prev) => { const next = { ...prev }; delete next[e.id]; return next; });
    try {
      await api.post(`/api/users/${e.id}/promote/`, { role: roleId, department: departmentId });
      setRegistrations((xs) => xs.filter((x) => x.id !== e.id));
      setRegistrationsTotal((n) => Math.max(0, n - 1));
      setPromotionChoices((prev) => { const next = { ...prev }; delete next[e.id]; return next; });
      setPromotionErrors((prev) => { const next = { ...prev }; delete next[e.id]; return next; });
      setRegistrationsError("");
      flash(t("Пользователь назначен сотрудником", "Користувача призначено співробітником"));
      load(); loadRegistrations();
    } catch (err: any) {
      setPromotionErrors((prev) => ({ ...prev, [e.id]: err?.response?.data?.detail || t("Не удалось назначить сотрудником", "Не вдалося призначити співробітником") }));
    } finally {
      setPromotingId(null);
    }
  }

  async function addDept() { const name = prompt(t("Название отдела", "Назва відділу")); if (!name) return; await api.post("/api/departments/", { name, pos_x: 360, pos_y: 240, color: "#64748b", permissions: [] }); load(); }
  async function renameDept(d: Dept) { const name = prompt(t("Новое название", "Нова назва"), d.name); if (!name) return; await api.patch(`/api/departments/${d.id}/`, { name }); load(); }
  async function delDept(d: Dept) { if (!confirm(t(`Удалить отдел «${d.name}»?`, `Видалити відділ «${d.name}»?`))) return; await api.del(`/api/departments/${d.id}/`); load(); }
  async function moveEmp(empId: number, deptId: number | null) { await api.patch(`/api/users/${empId}/`, { department: deptId }); flash(t("Перемещено", "Переміщено")); load(); }
  async function dismissEmp(e: Emp) {
    if (!confirm(t(
      `Уволить «${e.full_name}»?\n\nАккаунт деактивируется (НЕ удаляется), доступ пропадёт. Его клиенты / лиды / сделки / чаты / задачи автоматически перейдут другим сотрудникам.`,
      `Звільнити «${e.full_name}»?\n\nАкаунт деактивується (НЕ видаляється), доступ зникне. Його клієнти / ліди / угоди / чати / задачі автоматично перейдуть іншим співробітникам.`))) return;
    try {
      const r = await api.post<any>(`/api/users/${e.id}/dismiss/`, {});
      const m = r.moved || {}; const sum = Object.entries(m).map(([k, v]) => `${k}: ${v}`).join(", ");
      flash(t(`Уволен. Передано (${sum || "ничего"}) → ${(r.to || []).join(", ") || "—"}`, `Звільнено. Передано (${sum || "нічого"}) → ${(r.to || []).join(", ") || "—"}`));
      load(); loadList();
    } catch (err: any) { flash(err?.response?.data?.detail || t("Ошибка", "Помилка")); }
  }
  async function setEmpStatus(e: Emp, newStatus: "active" | "inactive" | "dismissed") {
    const labels: any = { active: t("вернуть в активные", "повернути в активні"), inactive: t("пометить неактивным", "позначити неактивним"), dismissed: t("уволить", "звільнити") };
    if (newStatus === "dismissed") { dismissEmp(e); return; }
    if (!confirm(t(`Точно ${labels[newStatus]} «${e.full_name}»?`, `Точно ${labels[newStatus]} «${e.full_name}»?`))) return;
    try {
      await api.post(`/api/users/${e.id}/set_status/`, { status: newStatus });
      flash(t("Статус изменён", "Статус змінено")); load(); loadList();
    } catch (err: any) { flash(err?.response?.data?.detail || t("Ошибка", "Помилка")); }
  }
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
    ["registrations", "🆕", "Регистрации", "Реєстрації"],
    ["activity", "📊", "Активность", "Активність"],
    ["invites", "✉️", "Приглашения", "Запрошення"],
    ["perms", "🛡", "Права", "Права"],
  ];
  const STATUS_META: any = {
    active: { ru: "Активный", uk: "Активний", bg: "#dcfce7", fg: "#16a34a" },
    inactive: { ru: "Неактивный", uk: "Неактивний", bg: "#fef9c3", fg: "#ca8a04" },
    dismissed: { ru: "Уволен", uk: "Звільнений", bg: "#fee2e2", fg: "#dc2626" },
  };
  const statusChip = (s?: string) => { const m = STATUS_META[s || "active"] || STATUS_META.active; return <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: m.bg, color: m.fg }}>{t(m.ru, m.uk)}</span>; };

  return (
    <ErrBoundary>
      <div className="scroll pad fade">
        <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
          {TABS.map(([k, ic, ru, uk]) => <button key={k} className={"btn" + (tab === k ? " btn-primary" : "")} onClick={() => { setTab(k); if (k === "registrations" && tab !== "registrations") loadRegistrations(); }}><Icon n={ic} size={15} /> {t(ru, uk)}{k === "registrations" && registrationsTotal > 0 ? ` · ${registrationsTotal}` : ""}</button>)}
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
                        style={{ cursor: "grab", background: "#f1f5f9", borderRadius: 7, padding: "3px 8px", fontSize: 12, display: "flex", alignItems: "center", gap: 5 }}>
                        {e.on_shift && <span title={e.shift_paused ? t("На паузе", "На паузі") : t("На работе сейчас", "На роботі зараз")} style={{ width: 7, height: 7, borderRadius: "50%", background: e.shift_paused ? "#eab308" : "#16a34a", flexShrink: 0 }} />}
                        <span onClick={() => setCardEmp(e)} style={{ cursor: "pointer" }}>{e.full_name}</span>
                        {e.role_name && <span className="muted" style={{ fontSize: 10 }}>· {e.role_name}</span>}
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
          <div>
            <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap", alignItems: "center" }}>
              {([["active", "Активные", "Активні"], ["inactive", "Неактивные", "Неактивні"], ["dismissed", "Уволенные", "Звільнені"], ["all", "Все", "Всі"]] as const).map(([k, ru, uk]) => (
                <button key={k} className={"btn" + (listStatus === k ? " btn-primary" : "")} style={{ fontSize: 12.5, padding: "4px 12px" }} onClick={() => setListStatus(k as any)}>{t(ru, uk)}</button>
              ))}
              <span className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>{listEmps.length} {t("чел.", "осіб")}</span>
            </div>
            <div className="tablewrap" style={{ maxHeight: "calc(100vh - 280px)", overflowY: "auto" }}><table>
              <thead><tr><th>{t("Сотрудник", "Співробітник")}</th><th>{t("Отдел", "Відділ")}</th><th>{t("Роль", "Роль")}</th><th>{t("Статус", "Статус")}</th><th>{t("Принят / Уволен", "Прийнятий / Звільнений")}</th><th>{t("Действие", "Дія")}</th></tr></thead>
              <tbody>{listEmps.map((e) => {
                const st = e.employment_status || (e.is_active ? "active" : "dismissed");
                const dj = e.date_joined ? new Date(e.date_joined).toLocaleDateString("uk-UA") : "—";
                const da = e.dismissed_at ? new Date(e.dismissed_at).toLocaleDateString("uk-UA") : "";
                const btn = (label: string, onClick: () => void, color: string, bg: string, border: string) => (
                  <button onClick={onClick} style={{ fontSize: 11.5, padding: "3px 9px", borderRadius: 7, border: `1px solid ${border}`, background: bg, color, cursor: "pointer", marginRight: 5 }}>{label}</button>
                );
                return <tr key={e.id}>
                  <td>
                    <div onClick={() => setCardEmp(e)} title={t("Открыть карточку сотрудника", "Відкрити картку співробітника")} style={{ display: "flex", alignItems: "center", gap: 9, cursor: "pointer" }}>
                      <PhotoAvatar photo={e.photo} name={e.full_name} size={32} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 600 }}>{e.full_name}</div>
                        {e.position && <div className="muted" style={{ fontSize: 11.5 }}>{e.position}</div>}
                      </div>
                      <ShiftBadge on={e.on_shift} paused={e.shift_paused} t={t} />
                    </div>
                  </td>
                  <td>{e.department_name || "—"}</td><td>{e.role_name || "—"}</td>
                  <td>{statusChip(st)}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{dj}{da && <> → <span style={{ color: "#dc2626" }}>{da}</span></>}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {st === "active" && <>
                      {btn(t("⏸ Неактивный", "⏸ Неактивний"), () => setEmpStatus(e, "inactive"), "#ca8a04", "#fefce8", "#fde68a")}
                      {btn(t("🚪 Уволить", "🚪 Звільнити"), () => setEmpStatus(e, "dismissed"), "#dc2626", "#fef2f2", "#fecaca")}
                    </>}
                    {st === "inactive" && <>
                      {btn(t("▶ Вернуть", "▶ Повернути"), () => setEmpStatus(e, "active"), "#16a34a", "#f0fdf4", "#bbf7d0")}
                      {btn(t("🚪 Уволить", "🚪 Звільнити"), () => setEmpStatus(e, "dismissed"), "#dc2626", "#fef2f2", "#fecaca")}
                    </>}
                    {st === "dismissed" && btn(t("▶ Вернуть в активные", "▶ Повернути в активні"), () => setEmpStatus(e, "active"), "#16a34a", "#f0fdf4", "#bbf7d0")}
                  </td>
                </tr>;
              })}</tbody>
            </table></div>
          </div>
        )}
        {tab === "registrations" && (
          <div>
            {canManageRoles && (
              <div style={{ background: "#fff", border: "1px solid #dbe7df", borderRadius: 12, padding: "14px 16px", marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
                  <div style={{ flex: 1, minWidth: 220 }}>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>{t("Проверки этапов ремонта", "Перевірки етапів ремонту")}{repairReviews.length > 0 ? ` · ${repairReviews.length}` : ""}</div>
                    <div className="muted" style={{ fontSize: 12.5, marginTop: 3 }}>{t("Заявки клиентов, которым нужно решение ответственного сотрудника.", "Заявки клієнтів, яким потрібне рішення відповідального співробітника.")}</div>
                  </div>
                  <button className="btn" disabled={repairReviewsLoading} onClick={loadRepairReviews} style={{ fontSize: 12 }}>
                    {repairReviewsLoading ? t("Обновляю…", "Оновлюю…") : t("Обновить", "Оновити")}
                  </button>
                </div>

                {repairReviewsError && <div style={{ color: "#dc2626", fontSize: 12.5, marginBottom: 10 }}>{repairReviewsError}</div>}
                {repairReviewsLoading && repairReviews.length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>{t("Загрузка проверок…", "Завантаження перевірок…")}</div>}
                {!repairReviewsLoading && !repairReviewsError && repairReviews.length === 0 && (
                  <div style={{ background: "#f8faf9", borderRadius: 9, padding: "10px 12px", fontSize: 12.5, color: "#64748b" }}>{t("Заявок на проверку сейчас нет.", "Заявок на перевірку зараз немає.")}</div>
                )}
                {repairReviews.length > 0 && (
                  <div style={{ display: "grid", gap: 10 }}>
                    {repairReviews.map((review) => {
                      const clientName = review.contact_name || review.requested_by_name || (review.contact_id ? `#${review.contact_id}` : "—");
                      const projectName = review.project_title || review.project_uuid || "—";
                      const stageName = review.title || review.stage_id || "—";
                      const createdAt = review.created_at ? new Date(review.created_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
                      const actionError = repairReviewErrors[review.id];
                      return <div key={review.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, background: "#fbfcfb" }}>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "8px 14px", marginBottom: 10 }}>
                          <div><div className="muted" style={{ fontSize: 11 }}>{t("Клиент", "Клієнт")}</div><div style={{ fontSize: 13, fontWeight: 600 }}>{clientName}</div></div>
                          <div><div className="muted" style={{ fontSize: 11 }}>{t("Проект", "Проєкт")}</div><div style={{ fontSize: 13, fontWeight: 600 }}>{projectName}</div></div>
                          <div><div className="muted" style={{ fontSize: 11 }}>{t("Этап", "Етап")}</div><div style={{ fontSize: 13, fontWeight: 600 }}>{stageName}</div>{review.stage_id && review.stage_id !== stageName && <div className="muted" style={{ fontSize: 10.5 }}>{review.stage_id}</div>}</div>
                          <div><div className="muted" style={{ fontSize: 11 }}>{t("Дата заявки", "Дата заявки")}</div><div style={{ fontSize: 13 }}>{createdAt}</div></div>
                        </div>
                        <div style={{ background: "#fff", border: "1px solid #edf0ee", borderRadius: 8, padding: "7px 9px", marginBottom: 9 }}>
                          <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>{t("Комментарий к заявке", "Коментар до заявки")}</div>
                          <div style={{ fontSize: 12.5, whiteSpace: "pre-wrap" }}>{review.note || t("Без комментария", "Без коментаря")}</div>
                        </div>
                        <textarea
                          aria-label={t(`Комментарий для доработки этапа ${stageName}`, `Коментар для доопрацювання етапу ${stageName}`)}
                          value={repairReviewNotes[review.id] || ""}
                          onChange={(ev) => setRepairReviewNote(review.id, ev.target.value)}
                          placeholder={t("Что именно нужно исправить (обязательно для доработки)", "Що саме потрібно виправити (обовʼязково для доопрацювання)")}
                          rows={2}
                          style={{ width: "100%", resize: "vertical", padding: "7px 9px", borderRadius: 8, border: "1px solid #dbe3df", fontFamily: "inherit", fontSize: 12.5, marginBottom: 8 }}
                        />
                        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                          <button className="btn btn-green" disabled={repairReviewingId === review.id} onClick={() => decideRepairReview(review, "accepted")} style={{ fontSize: 12 }}>
                            {repairReviewingId === review.id ? t("Сохраняю…", "Зберігаю…") : t("Принять этап", "Прийняти етап")}
                          </button>
                          <button className="btn" disabled={repairReviewingId === review.id} onClick={() => decideRepairReview(review, "rework")} style={{ fontSize: 12, color: "#a16207", borderColor: "#fde68a", background: "#fefce8" }}>
                            {t("Вернуть на доработку", "Повернути на доопрацювання")}
                          </button>
                          {actionError && <span style={{ color: "#dc2626", fontSize: 11.5 }}>{actionError}</span>}
                        </div>
                      </div>;
                    })}
                  </div>
                )}
              </div>
            )}

            <div style={{ background: "#faf8f5", border: "1px solid #ece7df", borderRadius: 12, padding: "12px 16px", marginBottom: 12 }}>
              <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{t("Новые обычные пользователи", "Нові звичайні користувачі")}</div>
              <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.45 }}>
                {t(
                  "После регистрации человек остаётся обычным клиентом и не видит рабочие данные CRM. Только администратор может выбрать роль и отдел и назначить его сотрудником.",
                  "Після реєстрації людина залишається звичайним клієнтом і не бачить робочі дані CRM. Тільки адміністратор може обрати роль і відділ та призначити її співробітником.")}
              </div>
            </div>

            {registrationsLoading && <div className="pad muted">{t("Загрузка регистраций…", "Завантаження реєстрацій…")}</div>}
            {registrationsError && <div style={{ color: "#dc2626", fontSize: 12.5, marginBottom: 10 }}>{registrationsError}</div>}
            {rolesLoadError && <div style={{ color: "#dc2626", fontSize: 12.5, marginBottom: 8 }}>{rolesLoadError}</div>}
            {departmentsLoadError && <div style={{ color: "#dc2626", fontSize: 12.5, marginBottom: 8 }}>{departmentsLoadError}</div>}
            {!registrationsLoading && registrationsTotal > registrations.length && (
              <div style={{ color: "#a16207", background: "#fefce8", border: "1px solid #fde68a", borderRadius: 8, padding: "7px 10px", fontSize: 12.5, marginBottom: 10 }}>
                {t(`Показаны первые ${registrations.length} из ${registrationsTotal} регистраций.`, `Показані перші ${registrations.length} із ${registrationsTotal} реєстрацій.`)}
              </div>
            )}
            {!registrationsLoading && registrations.length === 0 && registrationsTotal === 0 && !registrationsError && (
              <div style={{ background: "#fff", border: "1px solid #ece7df", borderRadius: 12, padding: 20 }}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>{t("Новых регистраций нет", "Нових реєстрацій немає")}</div>
                <div className="muted" style={{ fontSize: 12.5 }}>{t("Обычные пользователи появятся здесь после регистрации.", "Звичайні користувачі зʼявляться тут після реєстрації.")}</div>
              </div>
            )}
            {!registrationsLoading && registrations.length > 0 && (
              <div className="tablewrap" style={{ maxHeight: "calc(100vh - 310px)", overflowY: "auto" }}><table>
                <thead><tr>
                  <th>{t("Пользователь", "Користувач")}</th>
                  <th>{t("Телефон / email", "Телефон / email")}</th>
                  <th>{t("Дата регистрации", "Дата реєстрації")}</th>
                  <th>{t("Роль", "Роль")}</th>
                  <th>{t("Отдел", "Відділ")}</th>
                  <th>{t("Действие", "Дія")}</th>
                </tr></thead>
                <tbody>{registrations.map((e) => {
                  const choice = promotionChoices[e.id] || { role: "", department: "" };
                  const displayName = e.full_name || e.username || e.email || `#${e.id}`;
                  const joined = e.date_joined ? new Date(e.date_joined).toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—";
                  const ready = !!choice.role && !!choice.department;
                  const promotionError = promotionErrors[e.id];
                  return <tr key={e.id}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                        <PhotoAvatar photo={e.photo} name={displayName} size={32} />
                        <div>
                          <div style={{ fontWeight: 600 }}>{displayName}</div>
                          {e.username && e.username !== displayName && <div className="muted" style={{ fontSize: 11.5 }}>@{e.username}</div>}
                        </div>
                      </div>
                    </td>
                    <td style={{ fontSize: 12.5 }}>
                      <div>{e.phone || "—"}</div>
                      {e.email && <div className="muted" style={{ marginTop: 2 }}>{e.email}</div>}
                    </td>
                    <td className="muted" style={{ fontSize: 12.5, whiteSpace: "nowrap" }}>{joined}</td>
                    <td>
                      <select aria-label={t(`Роль для ${displayName}`, `Роль для ${displayName}`)} value={choice.role} onChange={(ev) => setPromotionChoice(e.id, "role", ev.target.value)} style={{ minWidth: 150, padding: "6px 8px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12.5 }}>
                        <option value="">{t("Выберите роль", "Оберіть роль")}</option>
                        <option value="none">{t("Без роли", "Без ролі")}</option>
                        {roles.map((r) => <option key={r.id} value={String(r.id)}>{r.name}</option>)}
                      </select>
                    </td>
                    <td>
                      <select aria-label={t(`Отдел для ${displayName}`, `Відділ для ${displayName}`)} value={choice.department} onChange={(ev) => setPromotionChoice(e.id, "department", ev.target.value)} style={{ minWidth: 150, padding: "6px 8px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12.5 }}>
                        <option value="">{t("Выберите отдел", "Оберіть відділ")}</option>
                        <option value="none">{t("Без отдела", "Без відділу")}</option>
                        {depts.map((d) => <option key={d.id} value={String(d.id)}>{d.name}</option>)}
                      </select>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button className="btn btn-primary" disabled={!ready || promotingId === e.id} onClick={() => promoteRegistration(e)} style={{ fontSize: 12, padding: "6px 10px" }}>
                        {promotingId === e.id ? t("Назначаю…", "Призначаю…") : t("Назначить сотрудником", "Призначити співробітником")}
                      </button>
                      {promotionError && <div style={{ color: "#dc2626", fontSize: 11.5, marginTop: 5, maxWidth: 220, whiteSpace: "normal" }}>{promotionError}</div>}
                    </td>
                  </tr>;
                })}</tbody>
              </table></div>
            )}
          </div>
        )}
        {tab === "activity" && <ActivityTab depts={depts} t={t} statusChip={statusChip} openCard={(e: any) => setCardEmp(e)} />}

        {cardEmp && <EmployeeCard emp={cardEmp} t={t}
          canEdit={!!(me?.is_superuser || me?.permissions?.includes("roles.manage") || me?.id === cardEmp.id)}
          onClose={() => setCardEmp(null)}
          onSaved={(upd: any) => { setListEmps((xs) => xs.map((x) => x.id === upd.id ? { ...x, ...upd } : x)); load(); }} />}
        {tab === "invites" && <InvitesTab depts={depts} roles={roles} invites={invites} reload={load} t={t} />}
        {tab === "perms" && <PermsTab depts={depts} emps={emps} perms={perms} permGroups={permGroups} funnels={funnels} roles={roles} reload={load} t={t}
          toggleDept={async (d: Dept, code: string) => { const next = d.permissions.includes(code) ? d.permissions.filter((c) => c !== code) : [...d.permissions, code]; await api.patch(`/api/departments/${d.id}/`, { permissions: next }); load(); }}
          toggleUser={async (e: Emp, code: string, kind: "extra" | "denied") => { const field = kind === "extra" ? "extra_permissions" : "denied_permissions"; const cur = (kind === "extra" ? e.extra_permissions : e.denied_permissions) || []; const next = cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code]; await api.patch(`/api/users/${e.id}/`, { [field]: next }); load(); }} />}
      </div>
    </ErrBoundary>
  );
}

// ── Картка співробітника: фото/лого + особисті дані + інтереси ──
function EmployeeCard({ emp, canEdit, onClose, onSaved, t }: any) {
  const [f, setF] = useState<any>({
    position: emp.position || "", birthday: emp.birthday || "", about: emp.about || "",
    interests: emp.interests || "", telegram: emp.telegram || "", phone: emp.phone || "",
  });
  const [photo, setPhoto] = useState<string>(emp.photo || "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const set = (k: string, v: string) => setF((p: any) => ({ ...p, [k]: v }));

  // стискаємо фото в браузері до 256px — щоб не вантажити базу
  function pickPhoto(file: File) {
    if (!file) return;
    const rd = new FileReader();
    rd.onload = () => {
      const img = new Image();
      img.onload = () => {
        const S = 256, c = document.createElement("canvas");
        const side = Math.min(img.width, img.height);
        c.width = S; c.height = S;
        const ctx = c.getContext("2d");
        if (ctx) { ctx.drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, S, S); setPhoto(c.toDataURL("image/jpeg", 0.82)); }
      };
      img.src = String(rd.result);
    };
    rd.readAsDataURL(file);
  }

  async function save() {
    setSaving(true); setErr("");
    try {
      const d = await api.patch<any>(`/api/users/${emp.id}/profile/`, { ...f, photo, birthday: f.birthday || null });
      onSaved?.(d); onClose();
    } catch (e: any) { setErr(e?.response?.data?.detail || t("Не удалось сохранить", "Не вдалося зберегти")); }
    setSaving(false);
  }

  const Field = ({ label, k, area, type }: any) => (
    <label style={{ display: "block", marginBottom: 10 }}>
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 3 }}>{label}</div>
      {area
        ? <textarea value={f[k]} onChange={(e) => set(k, e.target.value)} disabled={!canEdit} rows={3} style={{ width: "100%", padding: "7px 9px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13.5, fontFamily: "inherit", resize: "vertical" }} />
        : <input type={type || "text"} value={f[k]} onChange={(e) => set(k, e.target.value)} disabled={!canEdit} style={{ width: "100%", padding: "7px 9px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13.5 }} />}
    </label>
  );

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.4)", zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 16, width: "min(560px, 96vw)", maxHeight: "92vh", overflowY: "auto", boxShadow: "0 20px 60px rgba(0,0,0,.25)" }}>
        <div style={{ padding: "18px 20px", borderBottom: "1px solid #ece7df", display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ position: "relative" }}>
            <PhotoAvatar photo={photo} name={emp.full_name} size={64} />
            {canEdit && (
              <label title={t("Загрузить фото или лого", "Завантажити фото або лого")} style={{ position: "absolute", right: -2, bottom: -2, background: "#C67D5F", color: "#fff", width: 24, height: 24, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", fontSize: 12, border: "2px solid #fff" }}>
                <Icon n="📷" size={12} />
                <input type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => e.target.files && pickPhoto(e.target.files[0])} />
              </label>
            )}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 19, fontWeight: 700 }}>{emp.full_name}</div>
            <div className="muted" style={{ fontSize: 13 }}>{emp.department_name || "—"}{emp.role_name ? ` · ${emp.role_name}` : ""}</div>
            <div style={{ marginTop: 5, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <ShiftBadge on={emp.on_shift} paused={emp.shift_paused} t={t} />
              {photo && canEdit && <a onClick={() => setPhoto("")} style={{ fontSize: 11.5, color: "#dc2626", cursor: "pointer" }}>{t("убрать фото", "прибрати фото")}</a>}
            </div>
          </div>
          <button className="btn" onClick={onClose}>✕</button>
        </div>

        <div style={{ padding: "16px 20px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {Field({ label: t("Должность", "Посада"), k: "position" })}
            {Field({ label: t("День рождения", "День народження"), k: "birthday", type: "date" })}
            {Field({ label: t("Телефон", "Телефон"), k: "phone" })}
            {Field({ label: "Telegram", k: "telegram" })}
          </div>
          {Field({ label: t("О сотруднике", "Про співробітника"), k: "about", area: true })}
          {Field({ label: t("Интересы, хобби", "Інтереси, хобі"), k: "interests", area: true })}
          <div className="muted" style={{ fontSize: 12 }}>
            {t("Email", "Email")}: {emp.email || "—"} · {t("В компании с", "У компанії з")} {emp.date_joined ? new Date(emp.date_joined).toLocaleDateString("uk-UA") : "—"}
          </div>
          {err && <div style={{ color: "#dc2626", fontSize: 12.5, marginTop: 8 }}>{err}</div>}
          {canEdit && (
            <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
              <button className="btn btn-primary" disabled={saving} onClick={save}>{saving ? t("Сохраняю…", "Зберігаю…") : t("Сохранить", "Зберегти")}</button>
              <button className="btn" onClick={onClose}>{t("Отмена", "Скасувати")}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ActivityTab({ depts, t, statusChip, openCard }: any) {
  const now = new Date();
  const curMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const [period, setPeriod] = useState(curMonth);
  const [status, setStatus] = useState<"active" | "inactive" | "dismissed" | "all">("active");
  const [dept, setDept] = useState<number | "">("");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [sel, setSel] = useState<any>(null); // выбранный сотрудник (drill-down)
  const [selData, setSelData] = useState<any>(null);
  const [denied, setDenied] = useState(false);
  const [showIdleCfg, setShowIdleCfg] = useState(false);
  const [idleEmps, setIdleEmps] = useState<any[]>([]);   // сотрудники для персональной настройки простоя
  useEffect(() => {
    if (showIdleCfg && idleEmps.length === 0)
      api.get<any>("/api/users/?status=active&page_size=500").then((d) => setIdleEmps((d.results || d) as any[])).catch(() => {});
  }, [showIdleCfg]);

  useEffect(() => {
    setLoading(true); setDenied(false);
    const q = new URLSearchParams({ period, status }); if (dept) q.set("dept", String(dept));
    api.get<any>(`/api/staff/analytics/?${q.toString()}`).then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setLoading(false); if (e?.response?.status === 403) setDenied(true); });
  }, [period, status, dept]);

  function openEmp(row: any) {
    setSel(row); setSelData(null);
    const q = new URLSearchParams({ user: String(row.id), from: `${period}-01` });
    api.get<any>(`/api/staff/activity/?${q.toString()}`).then(setSelData).catch(() => setSelData({ feed: [], sessions: [] }));
  }
  const fmtDt = (s: string) => s ? new Date(s).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
  const fmtT = (s: string) => s ? new Date(s).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" }) : "—";
  const fmtTs = (s: string) => s ? new Date(s).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
  const fmtD = (s: string) => s ? new Date(s).toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit" }) : "—";
  const fmtDur = (sec: number) => { const x = Math.round(sec || 0); if (x < 60) return `${x} ${t("сек", "сек")}`; const m = Math.round(x / 60); return m < 60 ? `${m} ${t("мин", "хв")}` : `${Math.floor(m / 60)} ${t("ч", "год")} ${m % 60} ${t("мин", "хв")}`; };
  const pauseDur = (a: string, b: string) => (a && b) ? Math.max(0, Math.round((new Date(b).getTime() - new Date(a).getTime()) / 1000)) : null;

  if (denied) return <div className="pad muted">{t("Нет доступа к аналитике по сотрудникам (нужны права ЗП/KPI или управление сотрудниками).", "Немає доступу до аналітики по співробітниках (потрібні права ЗП/KPI або керування співробітниками).")}</div>;

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={{ padding: "5px 8px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }} />
        <select value={status} onChange={(e) => setStatus(e.target.value as any)} style={{ padding: "5px 8px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }}>
          <option value="active">{t("Активные", "Активні")}</option>
          <option value="inactive">{t("Неактивные", "Неактивні")}</option>
          <option value="dismissed">{t("Уволенные", "Звільнені")}</option>
          <option value="all">{t("Все", "Всі")}</option>
        </select>
        <select value={dept} onChange={(e) => setDept(e.target.value ? Number(e.target.value) : "")} style={{ padding: "5px 8px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }}>
          <option value="">{t("Все отделы", "Всі відділи")}</option>
          {depts.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        {loading && <span className="muted" style={{ fontSize: 12 }}>{t("Загрузка…", "Завантаження…")}</span>}
        <button className="btn" style={{ fontSize: 12.5, marginLeft: "auto" }} onClick={() => setShowIdleCfg((v) => !v)} title={t("Настройка контроля простоя", "Налаштування контролю простою")}>⏱ {t("Контроль простоя", "Контроль простою")}</button>
      </div>

      {showIdleCfg && (
        <div style={{ background: "#faf8f5", border: "1px solid #ece7df", borderRadius: 12, padding: "12px 16px", marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{t("Через сколько минут простоя ставить авто-паузу", "Через скільки хвилин простою ставити авто-паузу")}</div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("0 = выключить для отдела (напр. Склад/Тонировка — работают руками).", "0 = вимкнути для відділу (напр. Склад/Тонування — працюють руками).")}</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {depts.filter((d: any) => d.parent != null || depts.every((x: any) => x.parent == null)).map((d: any) => (
              <label key={d.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "5px 10px" }}>
                <b>{d.name}</b>
                <input type="number" min={0} max={480} defaultValue={d.idle_timeout_min ?? 15}
                  onBlur={(e) => { const v = Math.max(0, Math.min(480, Number(e.target.value) || 0)); api.patch(`/api/departments/${d.id}/`, { idle_timeout_min: v }).then(() => { d.idle_timeout_min = v; }).catch(() => {}); }}
                  style={{ width: 58, padding: "3px 6px", borderRadius: 6, border: "1px solid #e2e8f0", fontSize: 13, textAlign: "right" }} />
                <span className="muted" style={{ fontSize: 12 }}>{t("мин", "хв")}</span>
              </label>
            ))}
          </div>

          {/* ── персонально по менеджеру (важнее настройки отдела) ── */}
          <div style={{ fontSize: 13, fontWeight: 600, margin: "16px 0 4px", borderTop: "1px solid #ece7df", paddingTop: 12 }}>{t("Персонально по сотруднику", "Персонально по співробітнику")}</div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("Пусто = как в отделе. Число = свой порог (0 = выключить для этого человека). Личная настройка важнее отдела.", "Порожньо = як у відділі. Число = свій поріг (0 = вимкнути для цієї людини). Особиста настройка важливіша за відділ.")}</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {idleEmps.map((e: any) => (
              <label key={e.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "5px 10px" }}>
                <span>{e.full_name} <span className="muted" style={{ fontSize: 11 }}>· {e.department_name || "—"}</span></span>
                <input type="number" min={0} max={480} defaultValue={e.idle_timeout_min ?? ""} placeholder={t("отдел", "відділ")}
                  onBlur={(ev) => {
                    const raw = ev.target.value.trim();
                    const val = raw === "" ? null : Math.max(0, Math.min(480, Number(raw) || 0));
                    api.patch(`/api/users/${e.id}/`, { idle_timeout_min: val }).then(() => { e.idle_timeout_min = val; }).catch(() => {});
                  }}
                  style={{ width: 60, padding: "3px 6px", borderRadius: 6, border: "1px solid #e2e8f0", fontSize: 12.5, textAlign: "right" }} />
                <span className="muted" style={{ fontSize: 11.5 }}>{t("мин", "хв")}</span>
              </label>
            ))}
            {idleEmps.length === 0 && <span className="muted" style={{ fontSize: 12 }}>{t("Загрузка…", "Завантаження…")}</span>}
          </div>
        </div>
      )}

      {data && <>
        {/* сводка totals */}
        <div style={{ display: "flex", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
          {[[t("Сотрудников", "Співробітників"), data.totals.people], [t("Часов", "Годин"), data.totals.worked_hours], [t("Раб. дней", "Роб. днів"), data.totals.worked_days], [t("Действий", "Дій"), data.totals.actions]].map(([lbl, val]: any, i) => (
            <div key={i} style={{ background: "#fff", border: "1px solid #ece7df", borderRadius: 12, padding: "10px 16px", minWidth: 110 }}>
              <div className="muted" style={{ fontSize: 11 }}>{lbl}</div>
              <div style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{val}</div>
            </div>
          ))}
        </div>

        {/* по отделам */}
        {data.departments?.length > 1 && (
          <div style={{ marginBottom: 14 }}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 6, fontWeight: 600 }}>{t("По отделам", "По відділах")}</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {data.departments.map((d: any, i: number) => (
                <div key={i} style={{ background: "#faf8f5", border: "1px solid #ece7df", borderRadius: 10, padding: "8px 12px", fontSize: 12.5 }}>
                  <b>{d.department_name}</b> · {d.people} {t("чел", "ос")} · <span style={{ color: "#C67D5F", fontWeight: 600 }}>{d.worked_hours} {t("ч", "год")}</span> · {d.actions} {t("действ", "дій")}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* таблица по сотрудникам */}
        <div className="tablewrap" style={{ maxHeight: "calc(100vh - 420px)", overflowY: "auto" }}><table>
          <thead><tr>
            <th>{t("Сотрудник", "Співробітник")}</th><th>{t("Отдел", "Відділ")}</th><th>{t("Статус", "Статус")}</th>
            <th style={{ textAlign: "right" }}>{t("Часов", "Годин")}</th><th style={{ textAlign: "right" }}>{t("Дней", "Днів")}</th>
            <th style={{ textAlign: "right" }}>{t("Ср/день", "Сер/день")}</th><th style={{ textAlign: "right" }}>{t("Действий", "Дій")}</th>
            <th>{t("Больн/Отп/Прог", "Лік/Відп/Прог")}</th><th>{t("Последний вход", "Останній вхід")}</th>
          </tr></thead>
          <tbody>{data.rows.map((r: any) => (
            <tr key={r.id} onClick={() => openEmp(r)} style={{ cursor: "pointer" }} title={t("Клик — лента активности", "Клік — стрічка активності")}>
              <td>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span onClick={(ev) => { ev.stopPropagation(); openCard?.(r); }} title={t("Открыть карточку", "Відкрити картку")} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                    <PhotoAvatar photo={r.photo} name={r.full_name} size={30} />
                    <span style={{ fontWeight: 600 }}>{r.full_name}</span>
                  </span>
                  <ShiftBadge on={r.on_shift} paused={r.shift_paused} t={t} />
                </div>
              </td>
              <td className="muted" style={{ fontSize: 12 }}>{r.department_name}</td>
              <td>{statusChip(r.employment_status)}</td>
              <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600, color: r.worked_hours > 0 ? "#111" : "#cbd5e1" }}>{r.worked_hours}</td>
              <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{r.worked_days}</td>
              <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }} className="muted">{r.avg_hours_per_day || "—"}</td>
              <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600, color: r.actions > 0 ? "#111" : "#cbd5e1" }}>{r.actions}</td>
              <td className="muted" style={{ fontSize: 12 }}>{r.sick || 0}/{r.vacation || 0}/{r.absent || 0}</td>
              <td className="muted" style={{ fontSize: 12 }}>{fmtDt(r.last_seen)}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </>}

      {/* drill-down панель */}
      {sel && (
        <div onClick={() => setSel(null)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.35)", zIndex: 50, display: "flex", justifyContent: "flex-end" }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: "min(560px, 96vw)", background: "#fff", height: "100%", overflowY: "auto", boxShadow: "-8px 0 30px rgba(0,0,0,.2)" }}>
            <div style={{ padding: "16px 18px", borderBottom: "1px solid #ece7df", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 17, fontWeight: 700 }}>{sel.full_name}</div>
                <div className="muted" style={{ fontSize: 12.5 }}>{sel.department_name} · {statusChip(sel.employment_status)}</div>
              </div>
              <button className="btn" onClick={() => setSel(null)}>✕</button>
            </div>
            <div style={{ padding: "12px 18px", display: "flex", gap: 14, fontSize: 13, borderBottom: "1px solid #f1ece4" }}>
              <span>⏱ <b>{sel.worked_hours}</b> {t("ч", "год")}</span>
              <span>📅 <b>{sel.worked_days}</b> {t("дней", "днів")}</span>
              <span>⚡ <b>{sel.actions}</b> {t("действий", "дій")}</span>
            </div>
            {!selData && <div className="pad muted">{t("Загрузка…", "Завантаження…")}</div>}
            {selData && <div style={{ padding: "12px 18px" }}>
              {selData.sessions?.length > 0 && <>
                <div className="muted" style={{ fontSize: 12, fontWeight: 600, margin: "4px 0 8px" }}>{t("Смены и паузы", "Зміни та паузи")}</div>
                <div className="tablewrap"><table style={{ fontSize: 12.5, width: "100%" }}>
                  <thead><tr>
                    <th style={{ textAlign: "left" }}>{t("Дата", "Дата")}</th>
                    <th style={{ textAlign: "center" }}>{t("Приход", "Прихід")}</th>
                    <th style={{ textAlign: "center" }}>{t("Уход", "Вихід")}</th>
                    <th style={{ textAlign: "center" }}>{t("Паузы (обед/отлучки)", "Паузи (обід/відлучки)")}</th>
                    <th style={{ textAlign: "right" }}>{t("Пауза всего", "Пауза всього")}</th>
                    <th style={{ textAlign: "right" }}>{t("Отработано", "Відпрацьовано")}</th>
                  </tr></thead>
                  <tbody>{selData.sessions.slice(0, 20).map((s: any, i: number) => {
                    const ps = (s.pauses || []) as any[];
                    return <tr key={i}>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>{fmtD(s.started_at)}</td>
                      <td style={{ textAlign: "center", fontVariantNumeric: "tabular-nums" }}>{fmtT(s.started_at)}</td>
                      <td style={{ textAlign: "center", fontVariantNumeric: "tabular-nums" }}>{s.ended_at ? fmtT(s.ended_at) : <span style={{ color: "#16a34a" }}>{t("в работе", "в роботі")}</span>}</td>
                      <td style={{ textAlign: "center", fontSize: 11.5 }}>
                        {ps.length === 0 ? <span className="muted">—</span> : ps.map((p: any, j: number) => (
                          <span key={j} style={{ display: "inline-block", background: p.reason === "idle" ? "#fef2f2" : "#fef9c3", color: p.reason === "idle" ? "#dc2626" : "#a16207", borderRadius: 6, padding: "1px 6px", margin: 2, whiteSpace: "nowrap" }} title={(p.reason === "idle" ? t("Авто-пауза (простой)", "Авто-пауза (простій)") : t("Ручная пауза", "Ручна пауза")) + (pauseDur(p.start, p.end) !== null ? ` · ${fmtDur(pauseDur(p.start, p.end) as number)}` : "")}>
                            {fmtTs(p.start)}–{p.end ? fmtTs(p.end) : "…"}{pauseDur(p.start, p.end) !== null ? <span style={{ opacity: .7 }}> ({fmtDur(pauseDur(p.start, p.end) as number)})</span> : null}
                          </span>
                        ))}
                      </td>
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }} className="muted">{s.paused_seconds ? fmtDur(s.paused_seconds) : "—"}</td>
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>{s.worked_hours} {t("ч", "год")}</td>
                    </tr>;
                  })}</tbody>
                </table></div>
              </>}
              <div className="muted" style={{ fontSize: 12, fontWeight: 600, margin: "14px 0 8px" }}>{t("Действия (лента)", "Дії (стрічка)")}</div>
              {selData.feed?.length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>{t("Нет действий за период", "Немає дій за період")}</div>}
              {selData.feed?.map((f: any, i: number) => (
                <div key={i} style={{ fontSize: 12.5, padding: "6px 0", borderBottom: "1px solid #f6f2ec", display: "flex", gap: 8 }}>
                  <span className="muted" style={{ minWidth: 82, fontVariantNumeric: "tabular-nums" }}>{fmtDt(f.at)}</span>
                  <span><b>{f.action}</b>{f.detail && <span className="muted"> · {f.detail}</span>}</span>
                </div>
              ))}
            </div>}
          </div>
        </div>
      )}
    </div>
  );
}

function InvitesTab({ depts, roles, invites, reload, t }: any) {
  const [f, setF] = useState({ email: "", username: "", first_name: "", last_name: "", department: "", role: "" });
  const [link, setLink] = useState("");
  async function create() { if (!f.email.trim()) return; const body: any = { email: f.email, first_name: f.first_name, last_name: f.last_name }; if (f.username.trim()) body.username = f.username.trim(); if (f.department) body.department = Number(f.department); if (f.role) body.role = Number(f.role); try { const r = await api.post<any>("/api/invites/", body); setLink(r.link); setF({ email: "", username: "", first_name: "", last_name: "", department: "", role: "" }); reload(); } catch (e: any) { const msg = e?.data?.username?.[0] || e?.body?.username?.[0] || e?.data?.detail || e?.message; alert(msg || t("Не удалось создать (возможно логин уже занят)", "Не вдалося створити (можливо логін зайнятий)")); } }
  async function revoke(id: number) { if (!confirm(t("Отозвать приглашение? Ссылка сразу перестанет работать.", "Відкликати запрошення? Посилання одразу перестане працювати.") as string)) return; await api.post(`/api/invites/${id}/revoke/`, {}); reload(); }
  async function restore(id: number) { await api.post(`/api/invites/${id}/restore/`, {}); reload(); }
  async function delInvite(id: number) { if (!confirm(t("Удалить это приглашение из списка? Аккаунт сотрудника (если уже создан) останется — его убирают отдельно.", "Видалити це запрошення зі списку? Акаунт співробітника залишиться.") as string)) return; await api.del(`/api/invites/${id}/`); reload(); }
  const inp: any = { height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13 };
  return (
    <div style={{ maxWidth: 720 }}>
      <div className="panel">
        <div className="label" style={{ marginBottom: 8 }}>{t("Пригласить сотрудника по почте", "Запросити співробітника поштою")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <input style={inp} placeholder="Email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          <input style={inp} placeholder={t("Логин (необязательно)", "Логін (необовʼязково)")} value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />
          <select style={inp} value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })}><option value="">{t("— отдел —", "— відділ —")}</option>{depts.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
          <input style={inp} placeholder={t("Имя", "Імʼя")} value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} />
          <input style={inp} placeholder={t("Фамилия", "Прізвище")} value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} />
          <select style={inp} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="">{t("— роль —", "— роль —")}</option>{roles.map((r: any) => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
          <button className="btn btn-green" onClick={create}><Icon n="🔗" size={15} /> {t("Создать ссылку", "Створити посилання")}</button>
        </div>
        {link && <div style={{ marginTop: 10, padding: 10, background: "#ecfdf5", borderRadius: 8 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{t("Скопируй и отправь сотруднику:", "Скопіюй і надішли:")}</div>
          <div style={{ display: "flex", gap: 6 }}><input readOnly value={link} style={{ ...inp, flex: 1 }} onFocus={(e) => e.target.select()} /><button className="btn" onClick={() => navigator.clipboard?.writeText(link)}><Icon n="📋" size={15} /></button></div>
        </div>}
      </div>
      <div className="tablewrap" style={{ marginTop: 12 }}><table>
        <thead><tr><th>Email</th><th>{t("Отдел", "Відділ")}</th><th>{t("Статус", "Статус")}</th><th></th></tr></thead>
        <tbody>{invites.map((i: any) => <tr key={i.id}><td>{i.email}</td><td>{i.department_name || "—"}</td><td><span className="chip" style={{ background: i.status === "accepted" ? "#16a34a" : i.status === "pending" ? "#f59e0b" : "#94a3b8" }}>{i.status}</span></td><td><div style={{ display: "flex", gap: 12, alignItems: "center" }}>{i.status === "pending" && <><button className="btn btn-light" style={{ fontSize: 12, padding: "2px 9px" }} onClick={() => { navigator.clipboard?.writeText(i.link); alert(t("Ссылка скопирована", "Посилання скопійовано")); }}><Icon n="📋" size={13} /> {t("Ссылка", "Посилання")}</button><a onClick={() => revoke(i.id)} style={{ cursor: "pointer", color: "#dc2626", fontSize: 12.5 }}>{t("отозвать", "відкликати")}</a></>}{(i.status === "revoked" || i.status === "expired") && <a onClick={() => restore(i.id)} style={{ cursor: "pointer", color: "#16a34a", fontSize: 12.5, fontWeight: 600 }}>{t("восстановить", "відновити")}</a>}<a onClick={() => delInvite(i.id)} style={{ cursor: "pointer", color: "#94a3b8", fontSize: 14, marginLeft: "auto" }} title={t("Удалить запись из списка", "Видалити запис зі списку")}>🗑</a></div></td></tr>)}</tbody>
      </table></div>
    </div>
  );
}

function FinAccessTab({ depts, emps, roles, reload, t }: any) {
  const [kind, setKind] = useState<"dept" | "role" | "user">("dept");
  const [sel, setSel] = useState<any>("");
  const [accs, setAccs] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [dirs, setDirs] = useState<any[]>([]);
  const [cps, setCps] = useState<any[]>([]);
  const [q, setQ] = useState<any>({});
  const [, setTick] = useState(0);
  useEffect(() => {
    api.get<any>("/api/accounts/").then((d) => setAccs((d.results || d))).catch(() => {});
    api.get<any>("/api/categories/?page_size=400").then((d) => setCats(d.results || d)).catch(() => {});
    api.get<any>("/api/fin-directions/?page_size=100").then((d) => setDirs(d.results || d)).catch(() => {});
    api.get<any>("/api/finance/counterparties/").then((d) => setCps((d.results || d).map((x: any) => x.name).filter(Boolean))).catch(() => {});
  }, []);
  const list = kind === "dept" ? depts : kind === "role" ? roles : emps;
  const obj: any = list.find((x: any) => x.id === Number(sel));
  const url = kind === "dept" ? `/api/departments/${sel}/` : kind === "role" ? `/api/roles/${sel}/` : `/api/users/${sel}/`;
  async function toggle(key: string, val: any) {
    const cur = new Set(obj[key] || []);
    if (cur.has(val)) cur.delete(val); else cur.add(val);
    const next = Array.from(cur);
    const prev = obj[key];
    obj[key] = next;
    setTick((v) => v + 1);
    try { await api.patch(url, { [key]: next }); }
    catch { obj[key] = prev; setTick((v) => v + 1); alert("Помилка збереження"); }
  }
  const inp: any = { height: 32, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13 };
  const Block = ({ title, hint, items, key_, getId, getLabel }: any) => {
    const flt = (q[key_] || "").toLowerCase();
    const chosen = new Set(obj[key_] || []);
    const shown = items.filter((it: any) => !flt || getLabel(it).toLowerCase().includes(flt)).slice(0, 60);
    return (
      <div className="panel" style={{ flex: "1 1 340px", minWidth: 320, maxWidth: 480 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <b style={{ fontSize: 13.5 }}>{title}</b>
          <span className="muted" style={{ fontSize: 11 }}>{chosen.size ? t(`выбрано: ${chosen.size}`, `обрано: ${chosen.size}`) : t("не ограничено (видит все)", "не обмежено (бачить усі)")}</span>
        </div>
        <div className="muted" style={{ fontSize: 11, margin: "3px 0 7px" }}>{hint}</div>
        <input placeholder={t("Поиск…", "Пошук…")} value={q[key_] || ""} onChange={(e) => setQ({ ...q, [key_]: e.target.value })} style={{ ...inp, width: "100%", marginBottom: 6 }} />
        <div style={{ maxHeight: 260, overflowY: "auto" }}>
          {shown.map((it: any) => {
            const id = getId(it);
            return (
              <label key={String(id)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 2px", borderBottom: "0.5px solid #f1f5f9", cursor: "pointer", fontSize: 12.5 }}>
                <input type="checkbox" checked={chosen.has(id)} onChange={() => toggle(key_, id)} style={{ width: 15, height: 15, accentColor: "#C67D5F", flexShrink: 0 }} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{getLabel(it)}</span>
              </label>
            );
          })}
          {!shown.length && <div className="muted" style={{ fontSize: 12, padding: 4 }}>—</div>}
        </div>
      </div>
    );
  };
  return (
    <div>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 10, lineHeight: 1.5 }}>
        {t("Пообъектный доступ в Финансах. Если в блоке ничего не отмечено НИГДЕ (отдел + роль + лично) — сотрудник видит всё. Отметил хоть одно — видит только отмеченное. Доступ складывается: отдел ∪ роль ∪ личное. Права на ВКЛАДКИ и ДЕЙСТВИЯ — в «Права отдела»/«Индивидуальные», блоки «Фінанси · вкладки» и «Фінанси · дії».",
           "Пообʼєктний доступ у Фінансах. Якщо у блоці нічого не позначено НІДЕ (відділ + роль + особисто) — співробітник бачить усе. Позначив хоч одне — бачить лише позначене. Доступ складається: відділ ∪ роль ∪ особисте. Права на ВКЛАДКИ та ДІЇ — у «Права відділу»/«Індивідуальні», блоки «Фінанси · вкладки» і «Фінанси · дії».")}
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "inline-flex", borderRadius: 8, overflow: "hidden", border: "1px solid #e2e8f0" }}>
          {[["dept", t("Отдел", "Відділ")], ["role", t("Роль", "Роль")], ["user", t("Сотрудник", "Співробітник")]].map(([k, l]) => (
            <button key={k} onClick={() => { setKind(k as any); setSel(""); }} style={{ padding: "7px 13px", fontSize: 12.5, fontWeight: 600, border: "none", cursor: "pointer", background: kind === k ? "#C67D5F" : "#f8fafc", color: kind === k ? "#fff" : "#475569" }}>{l}</button>
          ))}
        </div>
        <select style={{ ...inp, minWidth: 260 }} value={sel} onChange={(e) => setSel(e.target.value)}>
          <option value="">{t("— выбери —", "— обери —")}</option>
          {list.map((x: any) => <option key={x.id} value={x.id}>{kind === "user" ? `${x.full_name} (${x.department_name || "—"})` : x.name}</option>)}
        </select>
      </div>
      {obj ? (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
          <Block title={"🏦 " + t("Счета", "Рахунки")} hint={t("Видит балансы и операции только этих счетов", "Бачить залишки та операції лише цих рахунків")}
            items={accs} key_="fin_accounts" getId={(a: any) => a.id} getLabel={(a: any) => a.name} />
          <Block title={"▲ " + t("Категории доходов", "Категорії доходів")} hint={t("Доступные категории при разноске доходов", "Доступні категорії при рознесенні доходів")}
            items={cats.filter((c: any) => c.direction === "in")} key_="fin_cats_in" getId={(c: any) => c.id} getLabel={(c: any) => c.name} />
          <Block title={"▼ " + t("Категории расходов", "Категорії витрат")} hint={t("Доступные категории при разноске расходов", "Доступні категорії при рознесенні витрат")}
            items={cats.filter((c: any) => c.direction === "out")} key_="fin_cats_out" getId={(c: any) => c.id} getLabel={(c: any) => c.name} />
          <Block title={"🗂 " + t("Проекты (направления)", "Проекти (напрямки)")} hint={t("Видимые направления", "Видимі напрямки")}
            items={dirs} key_="fin_dirs" getId={(d: any) => d.id} getLabel={(d: any) => d.name} />
          <Block title={"👥 " + t("Контрагенты", "Контрагенти")} hint={t("Видимые контрагенты (поиск по имени, клик — галочка)", "Видимі контрагенти (пошук за імʼям, клік — галочка)")}
            items={cps} key_="fin_counterparties" getId={(n: any) => n} getLabel={(n: any) => n} />
        </div>
      ) : <div className="muted" style={{ fontSize: 13 }}>{t("Выбери отдел, роль или сотрудника выше.", "Обери відділ, роль або співробітника вище.")}</div>}
    </div>
  );
}

function AccessTab({ depts, emps, roles, funnels, reload, t }: any) {
  const [kind, setKind] = useState<"dept" | "user">("dept");
  const [sel, setSel] = useState<any>("");
  const [channels, setChannels] = useState<any[]>([]);
  const [, setTick] = useState(0); // локальний ререндер без reload (щоб блок не мигав)
  useEffect(() => { api.get<any>("/api/channels/").then((d) => setChannels(d.results || d)).catch(() => {}); }, []);
  const obj: any = kind === "dept" ? depts.find((x: any) => x.id === Number(sel)) : emps.find((x: any) => x.id === Number(sel));
  const fKey = kind === "dept" ? "funnels" : "extra_funnels";
  const lKey = kind === "dept" ? "open_lines" : "extra_open_lines";
  const own = (key: string) => new Set<number>((obj && obj[key]) || []);
  const inhF = new Set<number>(); const inhL = new Set<number>();
  if (kind === "user" && obj) {
    const dep = depts.find((x: any) => x.id === obj.department);
    ((dep && dep.funnels) || []).forEach((i: number) => inhF.add(i));
    ((dep && dep.open_lines) || []).forEach((i: number) => inhL.add(i));
    const rl = roles.find((x: any) => x.id === obj.role);
    ((rl && rl.funnels) || []).forEach((i: number) => inhF.add(i));
    ((rl && rl.open_lines) || []).forEach((i: number) => inhL.add(i));
  }
  async function toggle(key: string, id: number) {
    const prev = (obj[key] || []).slice();
    const cur = own(key);
    if (cur.has(id)) cur.delete(id); else cur.add(id);
    const next = Array.from(cur);
    obj[key] = next;            // оптимістично — галочка перемикається миттєво
    setTick((v) => v + 1);
    const url = kind === "dept" ? `/api/departments/${obj.id}/` : `/api/users/${obj.id}/`;
    try {
      await api.patch(url, { [key]: next });
    } catch {
      obj[key] = prev;          // помилка — відкат
      setTick((v) => v + 1);
    }
  }
  const inp: any = { height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13, minWidth: 260 };
  const CheckList = ({ title, items, key_, inh, hint }: any) => (
    <div className="panel" style={{ flex: 1, minWidth: 300 }}>
      <div className="label">{title}</div>
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 8, lineHeight: 1.45 }}>{hint}</div>
      {items.map((it: any) => {
        const mine = own(key_).has(it.id); const inherited = inh && inh.has(it.id);
        return (
          <label key={it.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "0.5px solid #f1f5f9", cursor: "pointer", fontSize: 13 }}>
            <input type="checkbox" checked={mine} onChange={() => toggle(key_, it.id)} style={{ width: 16, height: 16, accentColor: "#C67D5F" }} />
            <span style={{ flex: 1 }}>{it.name}</span>
            {inherited && <span style={{ fontSize: 10.5, fontWeight: 700, color: "#16a34a", background: "#f0fdf4", borderRadius: 6, padding: "1px 7px", whiteSpace: "nowrap" }}>{t("от отдела/роли ✓", "від відділу/ролі ✓")}</span>}
          </label>
        );
      })}
      {!items.length && <div className="muted" style={{ fontSize: 12 }}>—</div>}
    </div>
  );
  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ display: "inline-flex", borderRadius: 8, overflow: "hidden", border: "1px solid #e2e8f0" }}>
          <button onClick={() => { setKind("dept"); setSel(""); }} style={{ padding: "7px 13px", fontSize: 12.5, fontWeight: 600, border: "none", cursor: "pointer", background: kind === "dept" ? "#C67D5F" : "#f8fafc", color: kind === "dept" ? "#fff" : "#475569" }}>{t("Отдел", "Відділ")}</button>
          <button onClick={() => { setKind("user"); setSel(""); }} style={{ padding: "7px 13px", fontSize: 12.5, fontWeight: 600, border: "none", cursor: "pointer", background: kind === "user" ? "#C67D5F" : "#f8fafc", color: kind === "user" ? "#fff" : "#475569" }}>{t("Сотрудник", "Співробітник")}</button>
        </div>
        <select style={inp} value={sel} onChange={(e) => setSel(e.target.value)}>
          <option value="">{kind === "dept" ? t("выбери отдел", "обери відділ") : t("выбери сотрудника", "обери співробітника")}</option>
          {(kind === "dept" ? depts : emps).map((x: any) => <option key={x.id} value={x.id}>{kind === "dept" ? x.name : `${x.full_name} (${x.department_name || "—"})`}</option>)}
        </select>
      </div>
      {obj ? (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
          <CheckList title={t("Воронки продаж", "Воронки продажів")} items={funnels} key_={fKey} inh={kind === "user" ? inhF : null}
            hint={t("Сотрудник работает ТОЛЬКО в отмеченных воронках (отдел + роль + личные вместе). Если нигде не отмечено ни одной — воронок не видит (кроме права «видеть все сделки»).",
                    "Співробітник працює ТІЛЬКИ у позначених воронках (відділ + роль + особисті разом). Якщо ніде не позначено жодної — воронок не бачить (крім права «бачити всі угоди»).")} />
          <CheckList title={t("Открытые линии (чаты)", "Відкриті лінії (чати)")} items={channels} key_={lKey} inh={kind === "user" ? inhL : null}
            hint={t("Отмеченные линии доступны в Чатах. ВАЖНО: пока ни одной линии не отмечено нигде (отдел + роль + лично) — сотрудник видит ВСЕ линии. Как только отмечена хоть одна — только отмеченные.",
                    "Позначені лінії доступні у Чатах. ВАЖЛИВО: поки жодної лінії не позначено ніде (відділ + роль + особисто) — співробітник бачить УСІ лінії. Щойно позначено хоч одну — тільки позначені.")} />
        </div>
      ) : <div className="muted" style={{ fontSize: 13 }}>{t("Выбери отдел или сотрудника выше.", "Обери відділ або співробітника вище.")}</div>}
    </div>
  );
}

function PermsTab({ depts, emps, perms, permGroups, funnels, roles, reload, t, toggleDept, toggleUser }: any) {
  const [mode, setMode] = useState<"dept" | "user" | "stage" | "access" | "fin">("dept");
  const [selDept, setSelDept] = useState<any>("");
  const [selUser, setSelUser] = useState<any>("");
  const d = depts.find((x: any) => x.id === Number(selDept));
  const u = emps.find((x: any) => x.id === Number(selUser));
  const inp: any = { height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13, minWidth: 240 };
  const groups = (permGroups && permGroups.length) ? permGroups : [{ group: "", items: perms }];

  const Rows = ({ control }: any) => (
    <div style={{ marginTop: 12 }}>
      {groups.map((g: any) => (
        <div key={g.group} className="panel" style={{ margin: "0 0 14px", padding: "12px 16px", borderLeft: "4px solid var(--brand)" }}>
          {g.group && <div style={{ fontSize: 13, fontWeight: 800, color: "var(--brand)", letterSpacing: 0.6, textTransform: "uppercase", margin: "0 0 4px", paddingBottom: 7, borderBottom: "1.5px solid color-mix(in srgb, var(--brand) 35%, transparent)" }}>{g.group}</div>}
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
        <button className={"btn" + (mode === "access" ? " btn-primary" : "")} onClick={() => setMode("access")}>🔀 {t("Воронки и линии", "Воронки і лінії")}</button>
        <button className={"btn" + (mode === "fin" ? " btn-primary" : "")} onClick={() => setMode("fin")}>💰 {t("Финансы", "Фінанси")}</button>
      </div>
      {mode === "fin" ? (
        <FinAccessTab depts={depts} emps={emps} roles={roles} reload={reload} t={t} />
      ) : mode === "access" ? (
        <AccessTab depts={depts} emps={emps} roles={roles} funnels={funnels} reload={reload} t={t} />
      ) : mode === "stage" ? (
        <StagePerms funnels={funnels} roles={roles} depts={depts} emps={emps} reload={reload} t={t} />
      ) : mode === "dept" ? (
        <div className="panel">
          <select style={inp} value={selDept} onChange={(e) => setSelDept(e.target.value)}><option value="">{t("выбери отдел", "обери відділ")}</option>{depts.map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</select>
          {d && <>
            <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>{t("Действуют на ВСЕХ сотрудников отдела. Нет «видеть все» = сотрудник видит только своё.", "Діють на ВСІХ співробітників відділу. Нема «бачити всі» = співробітник бачить лише своє.")}</div>
            <Rows control={(p: any) => { const on = d.permissions.includes(p.code); return <div style={{ display: "flex", alignItems: "center", gap: 7 }}><span style={{ fontSize: 11, fontWeight: 600, color: on ? "#16a34a" : "#94a3b8", width: 42, textAlign: "right" }}>{on ? t("Вкл", "Увімк") : t("Выкл", "Вимк")}</span><button onClick={() => toggleDept(d, p.code)} style={sw(on)} aria-label={p.label}><span style={knob(on)} /></button></div>; }} />
          </>}
        </div>
      ) : (
        <div className="panel">
          <select style={inp} value={selUser} onChange={(e) => setSelUser(e.target.value)}><option value="">{t("выбери сотрудника", "обери співробітника")}</option>{emps.map((x: any) => <option key={x.id} value={x.id}>{x.full_name} ({x.department_name || "—"})</option>)}</select>
          {u && <>
            <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>{t("«От отдела» = наследует. «Выдать» = дать лично. «Запретить» = убрать лично (важнее всего).", "«Від відділу» = успадковує. «Видати» = дати особисто. «Заборонити» = прибрати особисто (важливіше за все).")}</div>
            <Rows control={(p: any) => {
              const inh = inherited.has(p.code); const ex = u.extra_permissions?.includes(p.code); const dn = u.denied_permissions?.includes(p.code);
              const mode = dn ? "deny" : ex ? "grant" : "inherit";
              const seg: any = (active: boolean, color: string) => ({ padding: "4px 9px", fontSize: 11.5, border: "none", cursor: "pointer", fontWeight: 600, background: active ? color : "#f1f5f9", color: active ? "#fff" : "#64748b" });
              function setMode(target: string) {
                const wantEx = target === "grant", wantDn = target === "deny";
                if (!!ex !== wantEx) toggleUser(u, p.code, "extra");
                if (!!dn !== wantDn) toggleUser(u, p.code, "denied");
              }
              return <div style={{ display: "inline-flex", borderRadius: 7, overflow: "hidden", border: "1px solid #e2e8f0" }}>
                <button onClick={() => setMode("inherit")} title={t("Как у отдела/роли", "Як у відділу/ролі")} style={seg(mode === "inherit", "#64748b")}>{inh ? t("От отдела ✓", "Від відділу ✓") : t("Нет", "Нема")}</button>
                <button onClick={() => setMode("grant")} title={t("Выдать лично", "Видати особисто")} style={seg(mode === "grant", "#16a34a")}>{t("Выдать", "Видати")}</button>
                <button onClick={() => setMode("deny")} title={t("Запретить лично (важнее всего)", "Заборонити особисто (важливіше за все)")} style={seg(mode === "deny", "#dc2626")}>{t("Запретить", "Заборонити")}</button>
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
