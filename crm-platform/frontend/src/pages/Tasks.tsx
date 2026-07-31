/* Модуль «Задачі» — канбан з 4 колонок (Сьогодні / Тиждень / Пізніше / Готово).
   Фільтри: Мої/Всі + Виконавець (для керівника). Використовує TaskQuickModal. */
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
type StaffBrief = { id: number; full_name: string; department_name: string };

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

export default function Tasks() {
  const { t } = useLang();
  const [mode, setMode] = useState<"mine" | "all" | "user">("mine");
  const [userId, setUserId] = useState<number | null>(null);
  const [users, setUsers] = useState<StaffBrief[]>([]);
  const [data, setData] = useState<Kanban | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [editTask, setEditTask] = useState<Task | null>(null);

  useEffect(() => {
    api.get<StaffBrief[]>("/api/users/staff_brief/").then((r) => setUsers(r)).catch(() => setUsers([]));
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (mode === "mine") params.set("mine", "1");
      if (mode === "user" && userId) params.set("assignee", String(userId));
      const r = await api.get<Kanban>(`/api/tasks/kanban/?${params.toString()}`);
      setData(r);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [mode, userId]);

  const moveTo = async (task: Task, bucket: "today" | "week" | "later" | "done") => {
    if (bucket === "done") {
      await api.post(`/api/tasks/${task.id}/done/`);
    } else {
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

  return (
    <div className="scroll pad fade" style={{ width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}>
          <Icon n="check" size={20} /> {t("Задачи", "Задачі")}
        </h2>

        <div style={{ display: "flex", gap: 4, background: "#f1f5f9", padding: 4, borderRadius: 8 }}>
          <button className={"btn " + (mode === "mine" ? "btn-primary" : "btn-light")} style={{ fontSize: 13, padding: "6px 14px" }} onClick={() => { setMode("mine"); setUserId(null); }}>{t("Мои", "Мої")}</button>
          <button className={"btn " + (mode === "all" ? "btn-primary" : "btn-light")} style={{ fontSize: 13, padding: "6px 14px" }} onClick={() => { setMode("all"); setUserId(null); }}>{t("Все", "Всі")}</button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#64748b" }}>{t("Исполнитель:", "Виконавець:")}</span>
          <select
            value={mode === "user" ? String(userId ?? "") : ""}
            onChange={(e) => { const v = Number(e.target.value); if (v) { setMode("user"); setUserId(v); } else { setMode("mine"); setUserId(null); } }}
            style={{ padding: "6px 8px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}>
            <option value="">— {t("любой", "будь-хто")} —</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>

        <div style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setCreating(true)} style={{ fontSize: 14, padding: "8px 16px" }}>
          + {t("Задача", "Задача")}
        </button>
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
