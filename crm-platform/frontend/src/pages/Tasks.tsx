/* Модуль «Задачі» v4 — дошка АБО список + панель фільтрів (тип/статус/пріоритет/дата) + таби співробітників. */
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
  high: ["🔴", "#dc2626"],
  normal: ["", "#64748b"],
  low: ["⬇️", "#94a3b8"],
};

// Опції фільтрів (значення = як у БД)
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

const STATUS_COLOR: Record<string, string> = {
  open: "#2563eb", in_progress: "#d97706", proposed: "#7c3aed",
  done: "#16a34a", canceled: "#94a3b8", cancelled: "#94a3b8",
};

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

const LS_KEY = "tasks_view_selected";      // localStorage: "mine" | "all" | "u:<id>"
const LS_MODE = "tasks_view_mode";          // localStorage: "board" | "list"
const PAGE_SIZE = 100;

export default function Tasks() {
  const { t } = useLang();
  const { me, can } = useAuth();
  const canViewOthers = !!(me?.is_superuser || can("task.view.others") || can("roles.manage"));

  // Кого показувати (таби)
  const [selected, setSelectedState] = useState<string>(() => {
    try { return localStorage.getItem(LS_KEY) || "mine"; } catch { return "mine"; }
  });
  const setSelected = (v: string) => {
    setSelectedState(v);
    try { localStorage.setItem(LS_KEY, v); } catch { /* noop */ }
    try { window.dispatchEvent(new CustomEvent("tasks-view-changed", { detail: v })); } catch { /* noop */ }
  };

  // Режим відображення: дошка / список
  const [mode, setModeState] = useState<"board" | "list">(() => {
    try { return (localStorage.getItem(LS_MODE) as "board" | "list") || "board"; } catch { return "board"; }
  });
  const setMode = (m: "board" | "list") => {
    setModeState(m);
    try { localStorage.setItem(LS_MODE, m); } catch { /* noop */ }
  };

  // Фільтри
  const [fKind, setFKind] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [fPrio, setFPrio] = useState("");
  const [fFrom, setFFrom] = useState("");
  const [fTo, setFTo] = useState("");
  const resetFilters = () => { setFKind(""); setFStatus(""); setFPrio(""); setFFrom(""); setFTo(""); setPage(1); };
  const hasFilters = !!(fKind || fStatus || fPrio || fFrom || fTo);

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

  // Спільні параметри (кого показувати + фільтри)
  const baseParams = () => {
    const p = new URLSearchParams();
    if (selected === "mine") p.set("mine", "1");
    else if (selected.startsWith("u:")) p.set("assignee", selected.slice(2));
    if (fKind) p.set("kind", fKind);
    if (fStatus) p.set("status", fStatus);
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
        const p = baseParams();
        const k = await api.get<Kanban>(`/api/tasks/kanban/?${p.toString()}`);
        setData(k); setList(null);
      } else {
        const p = baseParams();
        p.set("page", String(page));
        p.set("page_size", String(PAGE_SIZE));
        p.set("ordering", "-created_at");
        const l = await api.get<Paged>(`/api/tasks/?${p.toString()}`);
        setList(l); setData(null);
      }
      setUCounts(await uc);
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line
  useEffect(() => { load(); }, [selected, mode, page, fKind, fStatus, fPrio, fFrom, fTo]);
  // Скидаємо сторінку при зміні набору
  // eslint-disable-next-line
  useEffect(() => { setPage(1); }, [selected, mode, fKind, fStatus, fPrio, fFrom, fTo]);

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

  const mineCount = ucounts?.users.find((u) => u.id === me?.id)?.today ?? 0;
  const allCount = ucounts?.total.today ?? 0;
  const otherUsers = (ucounts?.users || []).filter((u) => u.id !== me?.id);

  const Tab = ({ id, label, count, subtle }: { id: string; label: string; count: number; subtle?: boolean }) => {
    const active = selected === id;
    return (
      <button onClick={() => setSelected(id)} className={"btn " + (active ? "btn-primary" : "btn-light")}
        style={{ fontSize: 13, padding: "7px 12px", display: "flex", alignItems: "center", gap: 6,
          borderRadius: 20, fontWeight: active ? 700 : 500, whiteSpace: "nowrap", opacity: subtle && !count ? 0.55 : 1 }}>
        <span>{label}</span>
        {count > 0 && (
          <span style={{ background: active ? "rgba(255,255,255,.28)" : "#dc2626", color: "#fff",
            borderRadius: 10, padding: "0 7px", fontSize: 11, fontWeight: 700, minWidth: 18, textAlign: "center" }}>{count}</span>
        )}
      </button>
    );
  };

  const selStyle: React.CSSProperties = {
    fontSize: 13, padding: "6px 10px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", color: "#0f172a",
  };

  const totalPages = list ? Math.max(1, Math.ceil(list.count / PAGE_SIZE)) : 1;

  return (
    <div className="scroll pad fade" style={{ width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}>
          <Icon n="check" size={20} /> {t("Задачи", "Задачі")}
        </h2>
        {/* Перемикач Дошка / Список */}
        <div style={{ display: "flex", gap: 2, background: "#e2e8f0", borderRadius: 10, padding: 3 }}>
          {([["board", t("Доска", "Дошка")], ["list", t("Список", "Список")]] as const).map(([m, lbl]) => (
            <button key={m} onClick={() => setMode(m as "board" | "list")}
              className="btn" style={{ fontSize: 13, padding: "6px 14px", borderRadius: 8, fontWeight: 700,
                background: mode === m ? "#fff" : "transparent", color: mode === m ? "#0f172a" : "#64748b",
                boxShadow: mode === m ? "0 1px 2px rgba(0,0,0,.1)" : "none" }}>
              {lbl}
            </button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setCreating(true)} style={{ fontSize: 14, padding: "8px 16px" }}>
          + {t("Задача", "Задача")}
        </button>
      </div>

      {/* Таби: чиї задачі показувати */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10, padding: "10px 12px",
        background: "linear-gradient(90deg,#f8fafc,#eef2ff)", borderRadius: 10, border: "1px solid #e2e8f0", alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "#64748b", fontWeight: 600, marginRight: 4 }}>
          {t("Показать задачи:", "Показати задачі:")}
        </span>
        <Tab id="mine" label={t("Мои", "Мої")} count={mineCount} />
        {canViewOthers && <Tab id="all" label={t("Все", "Всі")} count={allCount} />}
        {canViewOthers && <div style={{ width: 1, height: 22, background: "#cbd5e1", margin: "0 4px" }} />}
        {canViewOthers && otherUsers.map((u) => (
          <Tab key={u.id} id={`u:${u.id}`} label={u.full_name} count={u.today} subtle />
        ))}
      </div>

      {/* Панель фільтрів */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16, padding: "10px 12px",
        background: "#f8fafc", borderRadius: 10, border: "1px solid #e2e8f0", alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "#64748b", fontWeight: 600 }}>{t("Фильтры:", "Фільтри:")}</span>
        <select style={selStyle} value={fKind} onChange={(e) => setFKind(e.target.value)}>
          <option value="">{t("Все типы", "Всі типи")}</option>
          {KIND_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select style={selStyle} value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
          <option value="">{t("Все статусы", "Всі статуси")}</option>
          {STATUS_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select style={selStyle} value={fPrio} onChange={(e) => setFPrio(e.target.value)}>
          <option value="">{t("Любой приоритет", "Будь-який пріоритет")}</option>
          {PRIO_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <span style={{ fontSize: 12, color: "#64748b" }}>{t("Срок:", "Термін:")}</span>
        <input type="date" style={selStyle} value={fFrom} onChange={(e) => setFFrom(e.target.value)} title={t("Срок с", "Термін з")} />
        <span style={{ color: "#94a3b8" }}>—</span>
        <input type="date" style={selStyle} value={fTo} onChange={(e) => setFTo(e.target.value)} title={t("Срок по", "Термін по")} />
        {hasFilters && (
          <button className="btn btn-light" style={{ fontSize: 12, padding: "6px 12px" }} onClick={resetFilters}>
            ✕ {t("Сбросить", "Скинути")}
          </button>
        )}
      </div>

      {loading && <div className="muted" style={{ padding: 40, textAlign: "center" }}>Завантаження…</div>}

      {/* ДОШКА */}
      {!loading && mode === "board" && data && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, alignItems: "flex-start" }}>
          {(["today", "week", "later", "done"] as const).map((k) => {
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
          {/* Пагінація */}
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
          <Link to={to} onClick={(e) => e.stopPropagation()} style={{ fontSize: 11, color: "#2563eb", textDecoration: "none" }}>
            → {text.slice(0, 50)}
          </Link>
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
          <Link to={to} onClick={(e) => e.stopPropagation()} style={{ fontSize: 11, color: "#2563eb", textDecoration: "none" }}>
            → {text.slice(0, 60)}
          </Link>
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
