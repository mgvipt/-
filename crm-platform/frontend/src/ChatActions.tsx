/* Дії над діалогом (як у Бітриксі): закріпити за собою, переадресувати,
 * додати менеджера, завершити. Використовується скрізь де є чат із клієнтом. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { Avatar } from "./ui";
import { Icon } from "./Icon";

const CLOSE_REASONS = [
  "Хочу пізніше (відкласти)", "Не відповідає (ігнор)", "Дорого / бюджет", "«Подумаю» / на днях",
  "Не наважився на пробник", "Немає в наявності / довгі терміни",
  "Купив у конкурента", "Не підійшов матеріал / продукт",
  "Немає обʼєкта зараз / просто дивився",
  "Питання вирішено / відповіли", "Не звернення (коментар, спілкування)",
];

export default function ChatActions({ convId, onClosed, onChanged }: { convId: number; onClosed?: () => void; onChanged?: (c: any) => void }) {
  const [emps, setEmps] = useState<{ id: number; full_name: string }[]>([]);
  const [picker, setPicker] = useState<null | "transfer" | "add" | "close">(null);
  const [note, setNote] = useState<string>("");
  useEffect(() => { api.get<any>("/api/conversations/staff/").then((d) => setEmps(((d.results || d) as any[]).map((u) => ({ id: u.id, full_name: u.full_name || u.username })))).catch(() => {}); }, []);
  function flashNote(txt: string, ms = 2600) { setNote(txt); window.setTimeout(() => setNote(""), ms); }
  async function take() {
    try {
      const c = await api.post<any>(`/api/conversations/${convId}/take/`, {});
      onChanged?.(c);
      flashNote("\uD83D\uDCCC " + ((c as any).assigned_to_name ? `\u0417\u0430\u043A\u0440\u0456\u043F\u043B\u0435\u043D\u043E \u0437\u0430: ${(c as any).assigned_to_name}` : "\u0417\u0430\u043A\u0440\u0456\u043F\u043B\u0435\u043D\u043E \u0437\u0430 \u0432\u0430\u043C\u0438"));
    } catch (e: any) {
      const who = e?.data?.detail || e?.response?.data?.detail || "";
      flashNote("\u26A0 " + (who || "\u041D\u0435 \u0432\u0434\u0430\u043B\u043E\u0441\u044F \u0437\u0430\u043A\u0440\u0456\u043F\u0438\u0442\u0438"), 4200);
    }
  }
  async function close(reason: string) {
    try { await api.post<any>(`/api/conversations/${convId}/close/`, { reason }); onClosed?.(); }
    catch { flashNote("\u26A0 \u041D\u0435 \u0432\u0434\u0430\u043B\u043E\u0441\u044F \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u0442\u0438", 3500); }
    setPicker(null);
  }
  async function pick(uid: number) { try { const c = await api.post<any>(`/api/conversations/${convId}/${picker === "transfer" ? "assign" : "add_member"}/`, { user_id: uid }); onChanged?.(c); } catch { /* ignore */ } setPicker(null); }
  const btn: any = { flex: "1 1 0", minWidth: 0, fontSize: "clamp(8px, 3cqi, 11.5px)", fontWeight: 600, padding: "5px 4px", borderRadius: 7, cursor: "pointer", border: "1px solid #e2e8f0", background: "#fff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textAlign: "center" };
  return (
    <>
    {note && <div style={{ fontSize: 11.5, fontWeight: 700, color: note.charAt(0) === "\u26A0" ? "#b91c1c" : "#0369a1", margin: "0 0 6px" }}>{note}</div>}
    <div style={{ position: "relative", display: "flex", gap: 4, marginBottom: 8, flexWrap: "nowrap" }}>
      <button style={{ ...btn, color: "#0369a1" }} onClick={take} title="Закріпити чат за собою (стати відповідальним)"><Icon n="📌" size={15} /> Закріпити</button>
      <button style={{ ...btn, color: "#c2410c" }} onClick={() => setPicker(picker === "transfer" ? null : "transfer")}>↪ Переадресувати</button>
      <button style={{ ...btn, color: "#4338ca" }} onClick={() => setPicker(picker === "add" ? null : "add")}><Icon n="➕" size={15} /> Менеджер</button>
      <button style={{ ...btn, color: "#dc2626" }} onClick={() => setPicker(picker === "close" ? null : "close")} title="Завершити діалог — оберіть причину (для аналітики)"><Icon n="✅" size={15} /> Завершити</button>
      {picker && (<>
        <div onClick={() => setPicker(null)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
        <div style={{ position: "absolute", top: 32, left: 0, width: 250, maxHeight: 300, overflowY: "auto", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 12px 30px rgba(0,0,0,.16)", zIndex: 41 }}>
          <div style={{ padding: "8px 12px", fontSize: 12, fontWeight: 700, color: "#475569", borderBottom: "1px solid #f1f5f9", position: "sticky", top: 0, background: "#fff" }}>{picker === "close" ? "Причина завершення:" : picker === "transfer" ? "Переадресувати на:" : "Додати менеджера:"}</div>
          {picker === "close" ? (<>
            {CLOSE_REASONS.map((r) => (<div key={r} onClick={() => close(r)} style={{ padding: "8px 12px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f8fafc" }}>{r}</div>))}
            <div onClick={() => close("")} style={{ padding: "8px 12px", cursor: "pointer", fontSize: 12.5, color: "#94a3b8", borderTop: "1px solid #eef2f7" }}>Завершити без причини</div>
          </>) : (<>
            {emps.map((e) => (<div key={e.id} onClick={() => pick(e.id)} style={{ padding: "7px 12px", cursor: "pointer", fontSize: 13, display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid #f8fafc" }}><Avatar name={e.full_name} cls="av-md" />{e.full_name}</div>))}
            {emps.length === 0 && <div className="muted" style={{ padding: 12, fontSize: 12 }}>Немає співробітників</div>}
          </>)}
        </div>
      </>)}
    </div>
    </>
  );
}
