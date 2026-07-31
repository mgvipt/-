/* Модуль «Задачі» v3 — канбан + таби зверху з іменами співробітників та лічильниками. */
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

const LS_KEY = "tasks_view_selected";  // localStorage: "mine" | "all" | "u:<id>"

export default function Tasks() {
  const { t } = useLang();
  const { me } = useAuth();
  // Selected view — persist
  const [selected, setSelectedState] = useState<string>(() => {
    try { return localStorage.getItem(LS_KEY) || "mine"; } catch { return "mine"; }
  });
  const setSelected = (v: string) => {
    setSelectedState(v);
    try { localStorage.setItem(LS_KEY, v); } catch { /* noop */ }
    // Синхронізуємо з Layout badge через custom event
    try { window.dispatchEvent(new CustomEvent("tasks-view-changed", { detail: v })); } catch { /* noop */ }
  };

  const [data, setData] = useState<Kanban | null>(null);
  const [ucounts, setUCounts] = useState<UserCounts | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [editTask, setEditTask] = useState<Task | null>(null);

  const buildKanbanUrl = () => {
    const p = new URLSearchParams();
    if (selected === "mine") p.set("mine", "1");
    else if (selected.startsWith("u:")) p.set("assignee", selected.slice(2));
    return `/api/tasks/kanban/?${p.toString()}`;
  };

  const load = async () => {
    setLoading(true);
    try {
      const [k, uc] = await Promise.all([
        api.get<Kanban>(buildKanbanUrl()),
        api.get<UserCounts>(`/api/tasks/user_counts/`),
      ]);
      setData(k);
      setUCounts(uc);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [selected]);

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

  // Tabs: [Мої, Всі] + один таб per user
  const mineCount = ucounts?.users.find((u) => u.id === me?.id)?.today ?? 0;
  const allCount = ucounts?.total.today ?? 0;
  const otherUsers = (ucounts?.users || []).filter((u) => u.id !== me?.id);

  const Tab = ({ id, label, count, subtle }: { id: string; label: string; count: number; subtle?: boolean }) => {
    const active = selected === id;
    return (
      <button
        onClick={() => setSelected(id)}
        className={"btn " + (active ? "btn-primary" : "btn-light")}
        style={{
          fontSize: 13, padding: "7px 12px", display: "flex", alignItems: "center", gap: 6,
          borderRadius: 20, fontWeight: active ? 700 : 500,
          whiteSpace: "nowrap", opacity: subtle && !count ? 0.55 : 1,
        }}>
        <span>{label}</span>
        {count > 0 && (
          <span style={{
            background: active ? "rgba(255,255,255,.28)" : "#dc2626",
            color: active ? "#fff" : "#fff",
            borderRadius: 10, padding: "0 7px", fontSize: 11, fontWeight: 700, minWidth: 18, textAlign: "center",
          }}>{count}</span>
        )}
      </button>
    );
  };

  return (
    <div className="scroll pad fade" style={{ width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}>
          <Icon n="check" size={20} /> {t("Задачи", "Задачі")}
        </h2>
        <div style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setCreating(true)} style={{ fontSize: 14, padding: "8px 16px" }}>
          + {t("Задача", "Задача")}
        </button>
      </div>

      {/* Tabs: вибір чиї задачі показувати */}
      <div style={{
        display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16, padding: "10px 12px",
        background: "linear-gradient(90deg,#f8fafc,#eef2ff)", borderRadius: 10, border: "1px solid #e2e8f0",
        alignItems: "center",
      }}>
        <span style={{ fontSize: 12, color: "#64748b", fontWeight: 600, marginRight: 4 }}>
          {t("Показать задачи:", "Показати задачі:")}
        </span>
        <Tab id="mine" label={t("Мои", "Мої")} count={mineCount} />
        <Tab id="all" label={t("Все", "Всі")} count={allCount} />
        <div style={{ width: 1, height: 22, background: "#cbd5e1", margin: "0 4px" }} />
        {otherUsers.map((u) => (
          <Tab key={u.id} id={`u:${u.id}`} label={u.full_name} count={u.today} subtle />
        ))}
      </div>

      {loading && <div className="muted" style={{ padding: 40, textAlign: "center" }}>Завантаження…</div>}

      {!loading && data && (
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

      {creating && <TaskQuickModal onClose={() => setCreating(false)} onSaved={() => { setCreating(false); load(); }} />}
      {editTask && <TaskQuickModal existing={editTask as any} onClose={() => setEditTask(null)} onSaved={() => { setEditTask(null); load(); }} />}
    </div>
  );
}

function Card({ task, onClick, onMove }: { task: Task; onClick: () => void; onMove: (b: "today" | "week" | "later" | "done") => void }) {
  const [prIcon, prColor] = PRIO_LBL[task.priority] || ["", "#64748b"];
  const link = task.deal ? `/deals/${task.deal}` : task.lead ? `/leads/${task.lead}` : task.contact ? `/clients/${task.contact}` : task.conversation ? `/inbox?conv=${task.conversation}` : null;
  const linkText = task.deal_title || task.lead_title || task.contact_name || task.conversation_title || "";
  return (
    <div style={{ background: "#fff", padding: 10, borderRadius: 8, boxShadow: "0 1px 2px rgba(0,0,0,.06)", cursor: "pointer", borderLeft: `3px solid ${prColor}` }} onClick={onClick}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
        {prIcon && <span style={{ fontSize: 12 }}>{prIcon}</span>}
        <div style={{ flex: 1, fontSize: 13, fontWeight: 600, lineHeight: 1.3 }}>{task.title}</div>
      </div>
      {link && linkText && (
        <div style={{ marginTop: 6 }}>
          <Link to={link} onClick={(e) => e.stopPropagation()} style={{ fontSize: 11, color: "#2563eb", textDecoration: "none" }}>
            → {linkText.slice(0, 50)}
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
