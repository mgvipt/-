/* Модуль «Задачі» v5 — дошка/список + ЄДИНЕ вікно фільтрів (кнопка → попап) + чіпи вибраних фільтрів з ✕. */
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
// Статус: зручні пресети + конкретні
const STATUS_OPTS: [string, string][] = [
  ["active", "Активні (не закриті)"], ["closed", "Закриті (готово/скасовані)"], ["all", "Всі статуси"],
  ["open", "Відкрита"], ["in_progress", "В роботі"], ["proposed", "Запропоновано"],
  ["done", "Виконана"], ["canceled", "Скасована"],
];
const STATUS_LBL: Record<string, string> = Object.fromEntries(STATUS_OPTS);
const PRIO_OPTS: [string, string][] = [
  ["high", "🔴 Високий"], ["normal", "Звичайний"], ["low", "⬇️ Низький"],
];
const PRIO_SHORT: Record<string, string> = { high: "🔴 Високий", normal: "Звичайний", low: "⬇️ Низький" };
const KIND_LBL: Record<string, string> = Object.fromEntries(KIND_OPTS);

const STATUS_COLOR: Record<string, string> = {
  open: "#2563eb", in_progress: "#d97706", proposed: "#7c3aed",
  done: "#16a34a", canceled: "#94a3b8", cancelled: "#94a3b8",
};
// статуси, що вважаються «закритими» (впливає на колонку «Готово» на дошці)
const CLOSED_SET = new Set(["closed", "all", "done", "canceled"]);

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
const fmtDate = (s: string) => { const [y, m, d] = s.split("-"); return `${d}.${m}`; };

const LS_KEY = "tasks_view_selected";
const LS_MODE = "tasks_view_mode";
const LS_STATUS = "tasks_filter_status";
const PAGE_SIZE = 100;

export default function Tasks() {
  const { t } = useLang();
  const { me, can } = useAuth();
  const canViewOthers = !!(me?.is_superuser || can("task.view.others") || can("roles.manage"));

  // Кого показувати (тепер у вікні фільтрів, не в шапці)
  const [selected, setSelectedState] = useState<string>(() => {
    try { return localStorage.getItem(LS_KEY) || "mine"; } catch { return "mine"; }
  });
  const setSelected = (v: string) => {
    setSelectedState(v);
    try { localStorage.setItem(LS_KEY, v); } catch { /* noop */ }
    try { window.dispatchEvent(new CustomEvent("tasks-view-changed", { detail: v })); } catch { /* noop */ }
  };

  const [mode, setModeState] = useState<"board" | "list">(() => {
    try { return (localStorage.getItem(LS_MODE) as "board" | "list") || "board"; } catch { return "board"; }
  });
  const setMode = (m: "board" | "list") => {
    setModeState(m);
    try { localStorage.setItem(LS_MODE, m); } catch { /* noop */ }
  };

  // Фільтри
  const [fStatus, setFStatus] = useState<string>(() => {
    try { return localStorage.getItem(LS_STATUS) || "active"; } catch { return "active"; }
  });
  const setStatus = (v: string) => { setFStatus(v); try { localStorage.setItem(LS_STATUS, v); } catch { /* noop */ } };
  const [fKind, setFKind] = useState("");
  const [fPrio, setFPrio] = useState("");
  const [fFrom, setFFrom] = useState("");
  const [fTo, setFTo] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);

  const resetAll = () => { setSelected("mine"); setStatus("active"); setFKind(""); setFPrio(""); setFFrom(""); setFTo(""); setPage(1); };

  useEffect(() => {
    if (!canViewOthers && (selected === "all" || selected.startsWith("u:"))) setSelected("mine");
    // eslint-disable-next-line
  }, [canViewOthers]);

  const [data, setData] = useState<Kanban | null>(null);
  const [list, setList] = useState<Paged | null>(null);
  const [page, setPage] = useState(1);
  const [ucounts, setUCounts] = useState<UserCounts | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [editTask, setEditTask] = useState<Task | null>(null);

  const baseParams = () => {
    const p = new URLSearchParams();
    if (selected === "mine") p.set("mine", "1");
    else if (selected.startsWith("u:")) p.set("assignee", selected.slice(2));
    // статус
    if (fStatus === "active") p.set("status_group", "active");
    else if (fStatus === "closed") p.set("status_group", "closed");
    else if (fStatus && fStatus !== "all") p.set("status", fStatus);
    if (fKind) p.set("kind", fKind);
    if (fPrio) p.set("priority", fPrio);
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
  useEffect(() => { load(); }, [selected, mode, page, fStatus, fKind, fPrio, fFrom, fTo]);
  // eslint-disable-next-line
  useEffect(() => { setPage(1); }, [selected, mode, fStatus, fKind, fPrio, fFrom, fTo]);

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
  const userName = (id: string) => usersList.find((u) => `u:${u.id}` === id)?.full_name || "Співробітник";

  // Чіпи активних фільтрів (кратко видно що вибрано; ✕ прибирає фільтр)
  type Chip = { key: string; label: string; clear: () => void };
  const chips: Chip[] = [];
  if (selected === "mine") chips.push({ key: "emp", label: t("Мои", "Мої"), clear: () => canViewOthers ? setSelected("all") : undefined as any });
  else if (selected.startsWith("u:")) chips.push({ key: "emp", label: userName(selected), clear: () => setSelected("all") });
  // (selected === "all" → чіпа немає, це найширше)
  if (fStatus && fStatus !== "all") chips.push({ key: "status", label: STATUS_LBL[fStatus] || fStatus, clear: () => setStatus("all") });
  if (fKind) chips.push({ key: "kind", label: KIND_LBL[fKind], clear: () => setFKind("") });
  if (fPrio) chips.push({ key: "prio", label: PRIO_SHORT[fPrio], clear: () => setFPrio("") });
  if (fFrom) chips.push({ key: "from", label: t("с ", "з ") + fmtDate(fFrom), clear: () => setFFrom("") });
  if (fTo) chips.push({ key: "to", label: t("по ", "по ") + fmtDate(fTo), clear: () => setFTo("") });

  const selStyle: React.CSSProperties = {
    fontSize: 13, padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", color: "#0f172a", width: "100%",
  };
  const fieldLbl: React.CSSProperties = { fontSize: 11, fontWeight: 700, color: "#64748b", marginBottom: 4, display: "block" };

  const totalPages = list ? Math.max(1, Math.ceil(list.count / PAGE_SIZE)) : 1;
  const showDone = CLOSED_SET.has(fStatus);           // чи показувати колонку «Готово» на дошці
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

      {/* ЄДИНА ЯЧЕЙКА ФІЛЬТРІВ: кнопка + чіпи вибраного */}
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

          {/* Чіпи */}
          {chips.map((c) => (
            <span key={c.key} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600,
              background: "#e0edff", color: "#1e40af", borderRadius: 16, padding: "5px 6px 5px 12px" }}>
              {c.label}
              <button onClick={c.clear} title={t("Убрать", "Прибрати")}
                style={{ border: "none", background: "#c7ddff", color: "#1e40af", borderRadius: "50%", width: 18, height: 18,
                  cursor: "pointer", fontSize: 12, lineHeight: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 0 }}>×</button>
            </span>
          ))}
          {chips.length === 0 && (
            <span style={{ fontSize: 12, color: "#94a3b8" }}>{t("Фильтры не выбраны", "Фільтри не вибрані")}</span>
          )}
          {chips.length > 0 && (
            <button className="btn btn-light" style={{ fontSize: 12, padding: "5px 10px", marginLeft: "auto" }} onClick={resetAll}>
              {t("Сбросить все", "Скинути все")}
            </button>
          )}
        </div>

        {/* ПОПАП вікно фільтрів */}
        {panelOpen && (
          <>
            <div onClick={() => setPanelOpen(false)}
              style={{ position: "fixed", inset: 0, zIndex: 40, background: "transparent" }} />
            <div style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 41, width: 320, maxWidth: "92vw",
              background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, boxShadow: "0 12px 32px rgba(0,0,0,.16)", padding: 16 }}>
              <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
                <span style={{ fontWeight: 800, fontSize: 15 }}>{t("Фильтры задач", "Фільтри задач")}</span>
                <div style={{ flex: 1 }} />
                <button className="btn btn-light" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => setPanelOpen(false)}>{t("Готово", "Готово")}</button>
              </div>

              {/* Співробітник */}
              {canViewOthers && (
                <div style={{ marginBottom: 12 }}>
                  <label style={fieldLbl}>{t("Сотрудник", "Співробітник")}</label>
                  <select style={selStyle} value={selected} onChange={(e) => setSelected(e.target.value)}>
                    <option value="mine">{t("Мои задачи", "Мої задачі")}</option>
                    <option value="all">{t("Все сотрудники", "Всі співробітники")}</option>
                    {usersList.map((u) => (
                      <option key={u.id} value={`u:${u.id}`}>{u.full_name}{u.all ? ` (${u.all})` : ""}</option>
                    ))}
                  </select>
                </div>
              )}

              <div style={{ marginBottom: 12 }}>
                <label style={fieldLbl}>{t("Статус", "Статус")}</label>
                <select style={selStyle} value={fStatus} onChange={(e) => setStatus(e.target.value)}>
                  {STATUS_OPTS.map(([v, l], i) => (
                    <option key={v} value={v} style={i === 3 ? { borderTop: "1px solid #eee" } : undefined}>{l}</option>
                  ))}
                </select>
              </div>

              <div style={{ marginBottom: 12 }}>
                <label style={fieldLbl}>{t("Тип", "Тип")}</label>
                <select style={selStyle} value={fKind} onChange={(e) => setFKind(e.target.value)}>
                  <option value="">{t("Все типы", "Всі типи")}</option>
                  {KIND_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>

              <div style={{ marginBottom: 12 }}>
                <label style={fieldLbl}>{t("Приоритет", "Пріоритет")}</label>
                <select style={selStyle} value={fPrio} onChange={(e) => setFPrio(e.target.value)}>
                  <option value="">{t("Любой", "Будь-який")}</option>
                  {PRIO_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>

              <div style={{ marginBottom: 8 }}>
                <label style={fieldLbl}>{t("Срок (от / до)", "Термін (з / по)")}</label>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="date" style={{ ...selStyle, width: "auto", flex: 1 }} value={fFrom} onChange={(e) => setFFrom(e.target.value)} />
                  <span style={{ color: "#94a3b8" }}>—</span>
                  <input type="date" style={{ ...selStyle, width: "auto", flex: 1 }} value={fTo} onChange={(e) => setFTo(e.target.value)} />
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                <button className="btn btn-light" style={{ fontSize: 12, padding: "6px 12px" }} onClick={resetAll}>
                  {t("Сбросить все", "Скинути все")}
                </button>
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
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
            {t("Всего задач:", "Всього задач:")} <b>{list.count}</b>
          </div>
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
                {!list.results.length && (
                  <tr><td colSpan={7} className="muted" style={{ padding: 30, textAlign: "center" }}>—</td></tr>
                )}
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
