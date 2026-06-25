/* Дії над діалогом (як у Бітриксі): закріпити за собою, переадресувати,
 * додати менеджера, завершити. Використовується скрізь де є чат із клієнтом. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { Avatar } from "./ui";

export default function ChatActions({ convId, onClosed, onChanged }: { convId: number; onClosed?: () => void; onChanged?: (c: any) => void }) {
  const [emps, setEmps] = useState<{ id: number; full_name: string }[]>([]);
  const [picker, setPicker] = useState<null | "transfer" | "add">(null);
  useEffect(() => { api.get<any>("/api/users/?page_size=500").then((d) => setEmps(((d.results || d) as any[]).filter((u) => u.is_active).map((u) => ({ id: u.id, full_name: u.full_name || u.username })))).catch(() => {}); }, []);
  async function take() { try { const c = await api.post<any>(`/api/conversations/${convId}/take/`, {}); onChanged?.(c); } catch { /* ignore */ } }
  async function close() { try { await api.post<any>(`/api/conversations/${convId}/close/`, {}); onClosed?.(); } catch { /* ignore */ } }
  async function pick(uid: number) { try { const c = await api.post<any>(`/api/conversations/${convId}/${picker === "transfer" ? "assign" : "add_member"}/`, { user_id: uid }); onChanged?.(c); } catch { /* ignore */ } setPicker(null); }
  const btn: any = { fontSize: 11.5, fontWeight: 600, padding: "5px 9px", borderRadius: 7, cursor: "pointer", border: "1px solid #e2e8f0", background: "#fff" };
  return (
    <div style={{ position: "relative", display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
      <button style={{ ...btn, color: "#0369a1" }} onClick={take} title="Закріпити чат за собою (стати відповідальним)">📌 Закріпити</button>
      <button style={{ ...btn, color: "#c2410c" }} onClick={() => setPicker(picker === "transfer" ? null : "transfer")}>↪ Переадресувати</button>
      <button style={{ ...btn, color: "#4338ca" }} onClick={() => setPicker(picker === "add" ? null : "add")}>➕ Менеджер</button>
      <button style={{ ...btn, color: "#dc2626" }} onClick={close} title="Завершити діалог — наступний лист клієнта створить новий лід">✅ Завершити</button>
      {picker && (<>
        <div onClick={() => setPicker(null)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
        <div style={{ position: "absolute", top: 32, left: 0, width: 250, maxHeight: 300, overflowY: "auto", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 12px 30px rgba(0,0,0,.16)", zIndex: 41 }}>
          <div style={{ padding: "8px 12px", fontSize: 12, fontWeight: 700, color: "#475569", borderBottom: "1px solid #f1f5f9", position: "sticky", top: 0, background: "#fff" }}>{picker === "transfer" ? "Переадресувати на:" : "Додати менеджера:"}</div>
          {emps.map((e) => (<div key={e.id} onClick={() => pick(e.id)} style={{ padding: "7px 12px", cursor: "pointer", fontSize: 13, display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid #f8fafc" }}><Avatar name={e.full_name} cls="av-md" />{e.full_name}</div>))}
          {emps.length === 0 && <div className="muted" style={{ padding: 12, fontSize: 12 }}>Немає співробітників</div>}
        </div>
      </>)}
    </div>
  );
}
