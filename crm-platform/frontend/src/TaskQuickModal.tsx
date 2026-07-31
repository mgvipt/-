/* TaskQuickModal — модалка створення/редагування задачі.
   Використовується на сторінці /tasks + в DealCard + в Inbox з preFill. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";

type PreFill = {
  contact?: number | null;
  deal?: number | null;
  lead?: number | null;
  conversation?: number | null;
  contact_name?: string;
  deal_title?: string;
  conversation_title?: string;
  title?: string;
};

type Existing = {
  id: number;
  title: string; body: string;
  priority: string; status: string;
  assignee: number | null; due_at: string | null;
  contact: number | null; deal: number | null; lead: number | null; conversation: number | null;
} | null;

type StaffBrief = { id: number; full_name: string; department_name: string; role_name: string };

export function TaskQuickModal({ prefill, existing, onClose, onSaved }: {
  prefill?: PreFill; existing?: Existing;
  onClose: () => void; onSaved: () => void;
}) {
  const { me } = useAuth();
  const isEdit = !!existing;
  const [title, setTitle] = useState(existing?.title || prefill?.title || "");
  const [body, setBody] = useState(existing?.body || "");
  const [priority, setPriority] = useState(existing?.priority || "normal");
  const [assigneeId, setAssigneeId] = useState<number | null>(existing?.assignee ?? me?.id ?? null);
  const [dueAt, setDueAt] = useState(
    existing?.due_at ? existing.due_at.slice(0, 16)
      : new Date(Date.now() + 3 * 60 * 60 * 1000 - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  );
  // Прив'язка
  const initKind: "contact" | "deal" | "lead" | "conversation" | "none" =
    existing?.contact ? "contact"
      : existing?.deal ? "deal"
      : existing?.lead ? "lead"
      : existing?.conversation ? "conversation"
      : prefill?.contact ? "contact"
      : prefill?.deal ? "deal"
      : prefill?.lead ? "lead"
      : prefill?.conversation ? "conversation"
      : "none";
  const [linkKind, setLinkKind] = useState<typeof initKind>(initKind);
  const [linkId, setLinkId] = useState<string>(String(
    existing?.contact || existing?.deal || existing?.lead || existing?.conversation ||
    prefill?.contact || prefill?.deal || prefill?.lead || prefill?.conversation || ""
  ));
  const [linkLabel] = useState<string>(prefill?.deal_title || prefill?.contact_name || prefill?.conversation_title || "");
  const [users, setUsers] = useState<StaffBrief[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<StaffBrief[]>("/api/users/staff_brief/").then((r) => setUsers(r)).catch(() => setUsers([]));
  }, []);

  const save = async () => {
    setError("");
    if (!title.trim()) { setError("Вкажіть заголовок"); return; }
    if (!assigneeId) { setError("Оберіть виконавця"); return; }
    if (!dueAt) { setError("Вкажіть дедлайн"); return; }
    if (linkKind === "none" || !linkId) { setError("Оберіть прив'язку (клієнт/угода/лід/чат)"); return; }
    setBusy(true);
    try {
      const payload: any = {
        title: title.trim(), body: body.trim(),
        priority, assignee: assigneeId,
        due_at: new Date(dueAt).toISOString(),
        contact: null, deal: null, lead: null, conversation: null,
      };
      payload[linkKind] = Number(linkId);
      if (isEdit) {
        await api.patch(`/api/tasks/${existing!.id}/`, payload);
      } else {
        await api.post(`/api/tasks/`, { ...payload, kind: "manager", status: "open" });
      }
      onSaved();
    } catch (e: any) {
      setError(e?.response?.data?.detail || JSON.stringify(e?.response?.data || e?.message || e));
    } finally { setBusy(false); }
  };

  const remove = async () => {
    if (!existing) return;
    if (!confirm(`Видалити задачу «${existing.title}»?`)) return;
    await api.del(`/api/tasks/${existing.id}/`);
    onSaved();
  };

  const linkFixed = !isEdit && !!prefill && (prefill.deal || prefill.contact || prefill.conversation || prefill.lead);

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={onClose}>
      <div style={{ background: "#fff", borderRadius: 12, padding: 24, width: 560, maxWidth: "95%", maxHeight: "90vh", overflow: "auto" }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 16px" }}>{isEdit ? "Редагувати задачу" : "Нова задача"}</h3>

        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4, fontSize: 12, fontWeight: 600, color: "#475569" }}>Заголовок *</div>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Що зробити (напр. Прозвонити клієнта до 14:00)" style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid #cbd5e1" }} autoFocus />
        </div>

        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 4, fontSize: 12, fontWeight: 600, color: "#475569" }}>Опис (не обов'язково)</div>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid #cbd5e1", fontFamily: "inherit" }} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
          <div>
            <div style={{ marginBottom: 4, fontSize: 12, fontWeight: 600, color: "#475569" }}>Виконавець *</div>
            <select value={assigneeId ?? ""} onChange={(e) => setAssigneeId(Number(e.target.value) || null)} style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid #cbd5e1" }}>
              <option value="">—</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.full_name}{u.department_name ? ` · ${u.department_name}` : ""}</option>
              ))}
            </select>
          </div>
          <div>
            <div style={{ marginBottom: 4, fontSize: 12, fontWeight: 600, color: "#475569" }}>Дедлайн *</div>
            <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid #cbd5e1" }} />
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
          <div>
            <div style={{ marginBottom: 4, fontSize: 12, fontWeight: 600, color: "#475569" }}>Пріоритет</div>
            <select value={priority} onChange={(e) => setPriority(e.target.value)} style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid #cbd5e1" }}>
              <option value="low">⬇️ Низький</option>
              <option value="normal">Звичайний</option>
              <option value="high">🔴 Високий</option>
            </select>
          </div>
          <div>
            <div style={{ marginBottom: 4, fontSize: 12, fontWeight: 600, color: "#475569" }}>Прив'язка *</div>
            <select value={linkKind} onChange={(e) => setLinkKind(e.target.value as any)} style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid #cbd5e1" }} disabled={!!linkFixed}>
              <option value="none">—</option>
              <option value="contact">Клієнт</option>
              <option value="deal">Угода</option>
              <option value="lead">Лід</option>
              <option value="conversation">Чат</option>
            </select>
          </div>
        </div>

        {linkKind !== "none" && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ marginBottom: 4, fontSize: 12, fontWeight: 600, color: "#475569" }}>
              {linkKind === "contact" ? "ID клієнта" : linkKind === "deal" ? "ID угоди" : linkKind === "lead" ? "ID ліда" : "ID чату"}
              {linkFixed && linkLabel && <span style={{ marginLeft: 8, color: "#16a34a", fontWeight: 500 }}>· {linkLabel}</span>}
            </div>
            <input value={linkId} onChange={(e) => setLinkId(e.target.value)} placeholder={linkFixed ? "" : "напр. 65946"} style={{ width: "100%", padding: 8, borderRadius: 6, border: "1px solid #cbd5e1" }} readOnly={!!linkFixed} />
          </div>
        )}

        {error && <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 12, padding: 8, background: "#fef2f2", borderRadius: 6 }}>{error}</div>}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          {isEdit && <button className="btn btn-light" onClick={remove} style={{ color: "#dc2626", marginRight: "auto" }}>Видалити</button>}
          <button className="btn btn-light" onClick={onClose}>Скасувати</button>
          <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Збереження…" : (isEdit ? "Зберегти" : "Створити")}</button>
        </div>
      </div>
    </div>
  );
}
