/* Модуль «Задачі» v6 — дошка/список + вікно фільтрів з МНОЖИННИМ вибором (чекбокси) + чіпи вибраного з ✕. */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useLang } from "../i18n";
import { useAuth } from "../auth";
import { Icon } from "../Icon";
import { TaskQuickModal } from "../TaskQuickModal";

type Task = {
  id: number;
  kind: string; kind_display: string;
  title: string; body: string;
  priority: string; priority_display: string;
  status: string; status_display: string;
  assignee: number | null; assignee_name: string;
  created_by: number | null; created_by_name: string;
  contact: number | null; contact_name: string;
  conversation: number | null; conversation_title: string;
  deal: number | null; deal_title: string;
  lead: number | null; lead_title: string;
  due_at: string | null;
  created_at: string;
  bucket: "today" | "week" | "later" | "done";
};

type Kanban = { groups: Record<string, Task[]>; counts: Record<string, number> };
type Paged = { count: number; next: string | null; previous: string | null; results: Task[] };
type UserCount = { id: number; full_name: string; today: number; all: number };
type UserCounts = { users: UserCount[]; total: { today: number; all: number } };

const COL = {
  today: { title: "На сьогодні", accent: "#dc2626", bg: "#fff5f5" },
  week: { title: "На тиждень", accent: "#d97706", bg: "#fffbeb" },
  later: { title: "Пізніше", accent: "#2563eb", bg: "#eff6ff" },
  done: { title: "Готово", accent: "#16a34a", bg: "#f0fdf4" },
};

const PRIO_LBL: Record<string, [string, string]> = {
  high: ["🔴", "#dc2626"], normal: ["", "#64748b"], low: ["⬇️", "#94a3b8"],
};

const KIND_OPTS: [string, string][] = [
  ["warehouse", "Склад"], ["tinting", "Тонування"], ["manager", "Менеджер"],
  ["followup", "Дожим"], ["other", "Інше"],
];
const STATUS_OPTS: [string, string][] = [
  ["open", "Відкрита"], ["in_progress", "В роботі"], ["proposed", "Запропоновано"],
  ["done", "Виконана"], ["canceled", "Скасована"],
];
const PRIO_OPTS: [string, string][] = [
  ["high", "🔴 Високий"], ["normal", "Звичайний"], ["low", "⬇️ Низький"],
];
const KIND_LBL: Record<string, string> = Object.fromEntries(KIND_OPTS);
const STATUS_LBL: Record<string, string> = Object.fromEntries(STATUS_OPTS);
const PRIO_LBL2: Record<string, string> = Object.fromEntries(PRIO_OPTS);

const STATUS_COLOR: Record<string, string> = {
  open: "#2563eb", in_progress: "#d97706", proposed: "#7c3aed",
  done: "#16a34a", canceled: "#94a3b8", cancelled: "#94a3b8",
};
const ACTIVE_ST = ["open", "in_progress", "proposed"];
const CLOSED_ST = ["done", "canceled"];
const eqSet = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join() === [...b].sort().join();

const fmtDue = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today); tomorrow.setDate(tomorrow.getDate() + 1);
  const day = new Date(d); day.setHours(0, 0, 0, 0);
  const hm = d.toLocaleTimeString("uk", { hour: "2-digit", minute: "2-digit" });
  if (day.getTime() === today.getTime()) return `Сьогодні ${hm}`;
  if (day.getTime() === tomorrow.getTime()) return `Завтра ${hm}`;
  return d.toLocaleDateString("uk", { day: "2-digit", month: "short" }) + " " + hm;
};
const fmtDate = (s: string) => { const [, m, d] = s.split("-"); return `${d}.${m}`; };

const LS_MODE = "tasks_view_mode";
const LS_EMP = "tasks_f_emp";
const LS_ST = "tasks_f_status";
const LS_KIND = "tasks_f_kind";
const LS_PRIO = "tasks_f_prio";
const PAGE_SIZE = 100;

const readLS = (k: string, def: string[]): string[] => {
  try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : def; } catch { return def; }
};
const saveLS = (k: string, v: string[]) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* noop */ } };

export default function Tasks() {
  const { t } = useLang();
  const { me, can } = useAuth();
  const canViewOthers = !!(me?.is_superuser || can("task.view.others") || can("roles.manage"));

  const [mode, setModeState] = useState<"board" | "list">(() => {
    try { return (localStorage.getItem(LS_MODE) as "board" | "list") || "board"; } catch { return "board"; }
  });
  const setMode = (m: "board" | "list") => { setModeState(m); try { localStorage.setItem(LS_MODE, m); } catch { /* noop */ } };

  // Множинні фільтри (масиви значень)
  const [selEmp, setSelEmpState] = useState<string[]>(() => readLS(LS_EMP, me ? [String(me.id)] : []));
  const [selSt, setSelStState] = useState<string[]>(() => readLS(LS_ST, ACTIVE_ST));
  const [selKind, setSelKindState] = useState<string[]>(() => readLS(LS_KIND, []));
  const [selPrio, setSelPrioState] = useState<string[]>(() => readLS(LS_PRIO, []));
  const [fFrom, setFFrom] = useState("");
  const [fTo, setFTo] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);

  const setSelEmp = (v: string[]) => { setSelEmpState(v); saveLS(LS_EMP, v); syncBadge(v); };
  const setSelSt = (v: string[]) => { setSelStState(v); saveLS(LS_ST, v); };
  const setSelKind = (v: string[]) => { setSelKindState(v); saveLS(LS_KIND, v); };
  const setSelPrio = (v: string[]) => { setSelPrioState(v); saveLS(LS_PRIO, v); };

  // Сумісність з бейджем у меню (Layout слухає tasks-view-changed)
  const syncBadge = (emp: string[]) => {
    let detail = "all";
    if (me && eqSet(emp, [String(me.id)])) detail = "mine";
    else if (emp.length === 1) detail = "u:" + emp[0];
    try { window.dispatchEvent(new CustomEvent("tasks-view-changed", { detail })); } catch { /* noop */ }
  };

  const toggle = (arr: string[], v: string, setter: (x: string[]) => void) =>
    setter(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  const resetAll = () => {
    setSelEmp(me ? [String(me.id)] : []); setSelSt(ACTIVE_ST); setSelKind([]); setSelPrio([]);
    setFFrom(""); setFTo(""); setPage(1);
  };

  const [data, setData] = useState<Kanban | null>(null);
  const [list, setList] = useState<Paged | null>(null);
  const [page, setPage] = useState(1);
  const [ucounts, setUCounts] = useState<UserCounts | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [editTask, setEditTask] = useState<Task | null>(null);

  const baseParams = () => {
    const p = new URLSearchParams();
    // сотрудники (тільки для тих, хто бачить чужі; порожньо = всі)
    if (canViewOthers && selEmp.length > 0) p.set("assignees", selEmp.join(","));
    else if (!canViewOthers) p.set("mine", "1");
    // статуси (порожньо або всі 5 = без фільтра)
    if (selSt.length > 0 && selSt.length < STATUS_OPTS.length) p.set("statuses", selSt.join(","));
    if (selKind.length > 0) p.set("kinds", selKind.join(","));
    if (selPrio.length > 0) p.set("priorities", selPrio.join(","));
    if (fFrom) p.set("due_from", fFrom);
    if (fTo) p.set("due_to", fTo);
    return p;
  };

  const load = async () => {
    setLoading(true);
    try {
      const uc = api.get<UserCounts>(`/api/tasks/user_counts/`);
      if (mode === "board") {
        const k = await api.get<Kanban>(`/api/tasks/kanban/?${baseParams().toString()}`);
        setData(k); setList(null);
      } else {
        const p = baseParams();
        p.set("page", String(page)); p.set("page_size", String(PAGE_SIZE)); p.set("ordering", "-created_at");
        const l = await api.get<Paged>(`/api/tasks/?${p.toString()}`);
        setList(l); setData(null);
      }
      setUCounts(await uc);
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line
  useEffect(() => { load(); }, [mode, page, selEmp, selSt, selKind, selPrio, fFrom, fTo]);
  // eslint-disable-next-line
  useEffect(() => { setPage(1); }, [mode, selEmp, selSt, selKind, selPrio, fFrom, fTo]);

  const moveTo = async (task: Task, bucket: "today" | "week" | "later" | "done") => {
    if (bucket === "done") await api.post(`/api/tasks/${task.id}/done/`);
    else {
      const now = new Date();
      let due: Date;
      if (bucket === "today") { due = new Date(now); due.setHours(23, 59, 0, 0); }
      else if (bucket === "week") { due = new Date(now); due.setDate(due.getDate() + 3); due.setHours(18, 0, 0, 0); }
      else { due = new Date(now); due.setDate(due.getDate() + 30); due.setHours(18, 0, 0, 0); }
      const payload: any = { due_at: due.toISOString() };
      if (task.status === "done" || task.status === "canceled") payload.status = task.assignee ? "in_progress" : "open";
      await api.patch(`/api/tasks/${task.id}/`, payload);
    }
    load();
  };

  const usersList = ucounts?.users || [];
  const userName = (id: string) => (String(me?.id) === id ? t("Я", "Я") : usersList.find((u) => String(u.id) === id)?.full_name || `#${id}`);

  // ── ЧІПИ активних фільтрів ──
  type Chip = { key: string; label: string; clear: () => void };
  const chips: Chip[] = [];
  // сотрудники (не показуємо, якщо порожньо = всі)
  if (canViewOthers && selEmp.length > 0) {
    selEmp.forEach((id) => chips.push({ key: "emp:" + id, label: userName(id), clear: () => setSelEmp(selEmp.filter((x) => x !== id)) }));
  }
  // статуси: пресети або окремі
  if (selSt.length > 0 && selSt.length < STATUS_OPTS.length) {
    if (eqSet(selSt, ACTIVE_ST)) chips.push({ key: "st", label: t("Активные", "Активні"), clear: () => setSelSt([]) });
    else if (eqSet(selSt, CLOSED_ST)) chips.push({ key: "st", label: t("Закрытые", "Закриті"), clear: () => setSelSt([]) });
    else selSt.forEach((s) => chips.push({ key: "st:" + s, label: STATUS_LBL[s] || s, clear: () => setSelSt(selSt.filter((x) => x !== s)) }));
  }
  selKind.forEach((k) => chips.push({ key: "k:" + k, label: KIND_LBL[k], clear: () => setSelKind(selKind.filter((x) => x !== k)) }));
  selPrio.forEach((pr) => chips.push({ key: "p:" + pr, label: PRIO_LBL2[pr], clear: () => setSelPrio(selPrio.filter((x) => x !== pr)) }));
  if (fFrom) chips.push({ key: "from", label: t("с ", "з ") + fmtDate(fFrom), clear: () => setFFrom("") });
  if (fTo) chips.push({ key: "to", label: t("по ", "по ") + fmtDate(fTo), clear: () => setFTo("") });

  const fieldLbl: React.CSSProperties = { fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 6, display: "block" };
  const dateInput: React.CSSProperties = { fontSize: 13, padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", color: "#0f172a", flex: 1, width: "auto" };
  const quickBtn = (active: boolean): React.CSSProperties => ({
    fontSize: 11, fontWeight: 700, padding: "4px 10px", borderRadius: 14, cursor: "pointer",
    border: "1px solid " + (active ? "#2563eb" : "#cbd5e1"), background: active ? "#2563eb" : "#fff", color: active ? "#fff" : "#475569",
  });

  // одна «пігулка»-чекбокс
  const pill = (checked: boolean, label: string, onClick: () => void, key: string) => (
    <button key={key} onClick={onClick} type="button" style={{
      display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, cursor: "pointer",
      padding: "6px 11px", borderRadius: 16, margin: "0 6px 6px 0",
      border: "1px solid " + (checked ? "#2563eb" : "#cbd5e1"), background: checked ? "#e0edff" : "#fff", color: checked ? "#1e40af" : "#475569",
    }}>
      <span style={{ width: 14, height: 14, borderRadius: 4, border: "1.5px solid " + (checked ? "#2563eb" : "#94a3b8"),
        background: checked ? "#2563eb" : "#fff", color: "#fff", fontSize: 11, lineHeight: "12px", textAlign: "center", display: "inline-block" }}>
        {checked ? "✓" : ""}
      </span>
      {label}
    </button>
  );

  const totalPages = list ? Math.max(1, Math.ceil(list.count / PAGE_SIZE)) : 1;
  const showDone = selSt.length === 0 || selSt.some((s) => CLOSED_ST.includes(s)) || selSt.length === STATUS_OPTS.length;
  const boardCols = (showDone ? (["today", "week", "later", "done"] as const) : (["today", "week", "later"] as const));

  return (
    <div className="scroll pad fade" style={{ width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}>
          <Icon n="check" size={20} /> {t("Задачи", "Задачі")}
        </h2>
        <div style={{ display: "flex", gap: 2, background: "#e2e8f0", borderRadius: 10, padding: 3 }}>
          {([["board", t("Доска", "Дошка")], ["list", t("Список", "Список")]] as const).map(([m, lbl]) => (
            <button key={m} onClick={() => setMode(m as "board" | "list")} className="btn"
              style={{ fontSize: 13, padding: "6px 14px", borderRadius: 8, fontWeight: 700,
                background: mode === m ? "#fff" : "transparent", color: mode === m ? "#0f172a" : "#64748b",
                boxShadow: mode === m ? "0 1px 2px rgba(0,0,0,.1)" : "none" }}>{lbl}</button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setCreating(true)} style={{ fontSize: 14, padding: "8px 16px" }}>
          + {t("Задача", "Задача")}
        </button>
      </div>

      {/* ЯЧЕЙКА ФІЛЬТРІВ: кнопка + чіпи */}
      <div style={{ position: "relative", marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", padding: "8px 10px",
          background: "#f8fafc", borderRadius: 10, border: "1px solid #e2e8f0" }}>
          <button className="btn" onClick={() => setPanelOpen((v) => !v)}
            style={{ fontSize: 13, fontWeight: 700, padding: "7px 14px", borderRadius: 8, display: "flex", alignItems: "center", gap: 7,
              background: panelOpen ? "#2563eb" : "#fff", color: panelOpen ? "#fff" : "#0f172a", border: "1px solid #cbd5e1" }}>
            <Icon n="filter" size={15} /> {t("Фильтры", "Фільтри")}
            {chips.length > 0 && (
              <span style={{ background: panelOpen ? "rgba(255,255,255,.3)" : "#2563eb", color: "#fff",
                borderRadius: 10, padding: "0 7px", fontSize: 11, fontWeight: 700 }}>{chips.length}</span>
            )}
          </button>

          {chips.map((c) => (
            <span key={c.key} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600,
              background: "#e0edff", color: "#1e40af", borderRadius: 16, padding: "5px 6px 5px 12px" }}>
              {c.label}
              <button onClick={c.clear} title={t("Убрать", "Прибрати")}
                style={{ border: "none", background: "#c7ddff", color: "#1e40af", borderRadius: "50%", width: 18, height: 18,
                  cursor: "pointer", fontSize: 12, lineHeight: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 0 }}>×</button>
            </span>
          ))}
          {chips.length === 0 && <span style={{ fontSize: 12, color: "#94a3b8" }}>{t("Фильтры не выбраны", "Фільтри не вибрані")}</span>}
          {chips.length > 0 && (
            <button className="btn btn-light" style={{ fontSize: 12, padding: "5px 10px", marginLeft: "auto" }} onClick={resetAll}>
              {t("Сбросить все", "Скинути все")}
            </button>
          )}
        </div>

        {/* ПОПАП */}
        {panelOpen && (
          <>
            <div onClick={() => setPanelOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 40, background: "transparent" }} />
            <div style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 41, width: 380, maxWidth: "94vw",
              maxHeight: "72vh", overflowY: "auto", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12,
              boxShadow: "0 12px 32px rgba(0,0,0,.16)", padding: 16 }}>
              <div style={{ display: "flex", alignItems: "center", marginBottom: 14 }}>
                <span style={{ fontWeight: 800, fontSize: 15 }}>{t("Фильтры задач", "Фільтри задач")}</span>
                <span style={{ fontSize: 12, color: "#94a3b8", marginLeft: 8 }}>{t("(можно несколько)", "(можна кілька)")}</span>
                <div style={{ flex: 1 }} />
                <button className="btn btn-light" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => setPanelOpen(false)}>{t("Готово", "Готово")}</button>
              </div>

              {/* Співробітники */}
              {canViewOthers && (
                <div style={{ marginBottom: 14 }}>
                  <label style={fieldLbl}>{t("Сотрудники", "Співробітники")}</label>
                  <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
                    <span style={quickBtn(!!(me && eqSet(selEmp, [String(me.id)])))} onClick={() => setSelEmp(me ? [String(me.id)] : [])}>{t("Только мои", "Тільки мої")}</span>
                    <span style={quickBtn(selEmp.length === 0)} onClick={() => setSelEmp([])}>{t("Все", "Всі")}</span>
                  </div>
                  <div style={{ maxHeight: 150, overflowY: "auto", border: "1px solid #eef2f7", borderRadius: 8, padding: 8 }}>
                    {usersList.map((u) => pill(selEmp.includes(String(u.id)), u.full_name + (u.all ? ` (${u.all})` : ""),
                      () => toggle(selEmp, String(u.id), setSelEmp), "u" + u.id))}
                    {!usersList.length && <span className="muted" style={{ fontSize: 12 }}>—</span>}
                  </div>
                </div>
              )}

              {/* Статус */}
              <div style={{ marginBottom: 14 }}>
                <label style={fieldLbl}>{t("Статус", "Статус")}</label>
                <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                  <span style={quickBtn(eqSet(selSt, ACTIVE_ST))} onClick={() => setSelSt(ACTIVE_ST)}>{t("Активные", "Активні")}</span>
                  <span style={quickBtn(eqSet(selSt, CLOSED_ST))} onClick={() => setSelSt(CLOSED_ST)}>{t("Закрытые", "Закриті")}</span>
                  <span style={quickBtn(selSt.length === 0 || selSt.length === STATUS_OPTS.length)} onClick={() => setSelSt([])}>{t("Все", "Всі")}</span>
                </div>
                <div>{STATUS_OPTS.map(([v, l]) => pill(selSt.includes(v), l, () => toggle(selSt, v, setSelSt), "s" + v))}</div>
              </div>

              {/* Тип */}
              <div style={{ marginBottom: 14 }}>
                <label style={fieldLbl}>{t("Тип", "Тип")}</label>
                <div>{KIND_OPTS.map(([v, l]) => pill(selKind.includes(v), l, () => toggle(selKind, v, setSelKind), "k" + v))}</div>
              </div>

              {/* Пріоритет */}
              <div style={{ marginBottom: 14 }}>
                <label style={fieldLbl}>{t("Приоритет", "Пріоритет")}</label>
                <div>{PRIO_OPTS.map(([v, l]) => pill(selPrio.includes(v), l, () => toggle(selPrio, v, setSelPrio), "p" + v))}</div>
              </div>

              {/* Термін */}
              <div style={{ marginBottom: 8 }}>
                <label style={fieldLbl}>{t("Срок (от / до)", "Термін (з / по)")}</label>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="date" style={dateInput} value={fFrom} onChange={(e) => setFFrom(e.target.value)} />
                  <span style={{ color: "#94a3b8" }}>—</span>
                  <input type="date" style={dateInput} value={fTo} onChange={(e) => setFTo(e.target.value)} />
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
                <button className="btn btn-light" style={{ fontSize: 12, padding: "6px 12px" }} onClick={resetAll}>{t("Сбросить все", "Скинути все")}</button>
              </div>
            </div>
          </>
        )}
      </div>

      {loading && <div className="muted" style={{ padding: 40, textAlign: "center" }}>Завантаження…</div>}

      {/* ДОШКА */}
      {!loading && mode === "board" && data && (
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${boardCols.length}, 1fr)`, gap: 12, alignItems: "flex-start" }}>
          {boardCols.map((k) => {
            const col = COL[k];
            const items = data.groups[k] || [];
            return (
              <div key={k} style={{ background: col.bg, borderRadius: 10, padding: 10, minHeight: 300, borderTop: `3px solid ${col.accent}` }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: col.accent, marginBottom: 10, display: "flex", justifyContent: "space-between" }}>
                  <span>{col.title}</span>
                  <span style={{ background: col.accent, color: "#fff", borderRadius: 10, padding: "1px 8px", fontSize: 11 }}>{items.length}</span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {items.map((task) => <Card key={task.id} task={task} onClick={() => setEditTask(task)} onMove={(b) => moveTo(task, b)} />)}
                  {!items.length && <div className="muted" style={{ fontSize: 12, textAlign: "center", padding: 20 }}>—</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* СПИСОК */}
      {!loading && mode === "list" && list && (
        <div>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>{t("Всего задач:", "Всього задач:")} <b>{list.count}</b></div>
          <div style={{ overflowX: "auto", border: "1px solid #e2e8f0", borderRadius: 10 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 760 }}>
              <thead>
                <tr style={{ background: "#f1f5f9", textAlign: "left", color: "#475569" }}>
                  <th style={{ padding: "8px 10px", width: 28 }}></th>
                  <th style={{ padding: "8px 10px" }}>{t("Задача", "Задача")}</th>
                  <th style={{ padding: "8px 10px", width: 110 }}>{t("Тип", "Тип")}</th>
                  <th style={{ padding: "8px 10px", width: 140 }}>{t("Исполнитель", "Виконавець")}</th>
                  <th style={{ padding: "8px 10px", width: 130 }}>{t("Срок", "Термін")}</th>
                  <th style={{ padding: "8px 10px", width: 120 }}>{t("Статус", "Статус")}</th>
                  <th style={{ padding: "8px 10px", width: 44 }}></th>
                </tr>
              </thead>
              <tbody>
                {list.results.map((task) => <Row key={task.id} task={task} onClick={() => setEditTask(task)} onDone={() => moveTo(task, "done")} />)}
                {!list.results.length && <tr><td colSpan={7} className="muted" style={{ padding: 30, textAlign: "center" }}>—</td></tr>}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "center", marginTop: 14 }}>
              <button className="btn btn-light" disabled={page <= 1} style={{ fontSize: 13, padding: "6px 12px", opacity: page <= 1 ? 0.5 : 1 }}
                onClick={() => setPage((p) => Math.max(1, p - 1))}>← {t("Назад", "Назад")}</button>
              <span style={{ fontSize: 13, color: "#64748b" }}>{t("Стр.", "Стор.")} {page} / {totalPages}</span>
              <button className="btn btn-light" disabled={page >= totalPages} style={{ fontSize: 13, padding: "6px 12px", opacity: page >= totalPages ? 0.5 : 1 }}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>{t("Вперёд", "Вперед")} →</button>
            </div>
          )}
        </div>
      )}

      {creating && <TaskQuickModal onClose={() => setCreating(false)} onSaved={() => { setCreating(false); load(); }} />}
      {editTask && <TaskQuickModal existing={editTask as any} onClose={() => setEditTask(null)} onSaved={() => { setEditTask(null); load(); }} />}
    </div>
  );
}

function taskLink(task: Task): { to: string | null; text: string } {
  const to = task.deal ? `/deals/${task.deal}` : task.lead ? `/leads/${task.lead}` : task.contact ? `/clients/${task.contact}` : task.conversation ? `/inbox?conv=${task.conversation}` : null;
  const text = task.deal_title || task.lead_title || task.contact_name || task.conversation_title || "";
  return { to, text };
}

function Card({ task, onClick, onMove }: { task: Task; onClick: () => void; onMove: (b: "today" | "week" | "later" | "done") => void }) {
  const [prIcon, prColor] = PRIO_LBL[task.priority] || ["", "#64748b"];
  const { to, text } = taskLink(task);
  return (
    <div style={{ background: "#fff", padding: 10, borderRadius: 8, boxShadow: "0 1px 2px rgba(0,0,0,.06)", cursor: "pointer", borderLeft: `3px solid ${prColor}` }} onClick={onClick}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
        {prIcon && <span style={{ fontSize: 12 }}>{prIcon}</span>}
        <div style={{ flex: 1, fontSize: 13, fontWeight: 600, lineHeight: 1.3 }}>{task.title}</div>
      </div>
      {to && text && (
        <div style={{ marginTop: 6 }}>
          <Link to={to} onClick={(e) => e.stopPropagation()} style={{ fontSize: 11, color: "#2563eb", textDecoration: "none" }}>→ {text.slice(0, 50)}</Link>
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8, fontSize: 11, color: "#64748b" }}>
        <span>{task.assignee_name || "—"}</span>
        <span>{fmtDue(task.due_at)}</span>
      </div>
      <div style={{ display: "flex", gap: 4, marginTop: 8 }} onClick={(e) => e.stopPropagation()}>
        {task.bucket !== "today" && <button className="btn btn-light" style={{ fontSize: 10, padding: "2px 6px" }} onClick={() => onMove("today")}>→ Сьогодні</button>}
        {task.bucket !== "done" && <button className="btn btn-light" style={{ fontSize: 10, padding: "2px 6px" }} onClick={() => onMove("done")}>✓</button>}
      </div>
    </div>
  );
}

function Row({ task, onClick, onDone }: { task: Task; onClick: () => void; onDone: () => void }) {
  const [prIcon, prColor] = PRIO_LBL[task.priority] || ["", "#64748b"];
  const { to, text } = taskLink(task);
  const isDone = task.status === "done" || task.status === "canceled" || task.status === "cancelled";
  return (
    <tr style={{ borderTop: "1px solid #eef2f7", cursor: "pointer", background: "#fff" }}
      onClick={onClick}
      onMouseEnter={(e) => (e.currentTarget.style.background = "#f8fafc")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "#fff")}>
      <td style={{ padding: "8px 10px", borderLeft: `3px solid ${prColor}` }}>{prIcon}</td>
      <td style={{ padding: "8px 10px" }}>
        <div style={{ fontWeight: 600, lineHeight: 1.3 }}>{task.title}</div>
        {to && text && (
          <Link to={to} onClick={(e) => e.stopPropagation()} style={{ fontSize: 11, color: "#2563eb", textDecoration: "none" }}>→ {text.slice(0, 60)}</Link>
        )}
      </td>
      <td style={{ padding: "8px 10px", color: "#475569" }}>{task.kind_display}</td>
      <td style={{ padding: "8px 10px", color: "#475569" }}>{task.assignee_name || "—"}</td>
      <td style={{ padding: "8px 10px", color: "#475569" }}>{fmtDue(task.due_at)}</td>
      <td style={{ padding: "8px 10px" }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: STATUS_COLOR[task.status] || "#64748b" }}>{task.status_display}</span>
      </td>
      <td style={{ padding: "8px 10px" }} onClick={(e) => e.stopPropagation()}>
        {!isDone && <button className="btn btn-light" style={{ fontSize: 12, padding: "3px 8px" }} onClick={onDone} title="Виконано">✓</button>}
      </td>
    </tr>
  );
}
