import { useEffect, useRef, useState } from "react";
import { api, ChatMessage, Conversation, Paginated } from "../api";

// Встроенный чат с клиентом — переиспользуется в карточке лида и сделки.
// Находит диалог по контакту, показывает переписку, отправку и AI-подсказку.
export default function ChatPanel({ contactId }: { contactId: number | null }) {
  const [conv, setConv] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [err, setErr] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!contactId) { setConv(null); return; }
    api.get<Paginated<Conversation>>(`/api/conversations/?contact=${contactId}`).then((d) => {
      const c = d.results[0] || null;
      setConv(c);
      if (c) api.get<ChatMessage[]>(`/api/conversations/${c.id}/messages/`).then(setMsgs);
    });
  }, [contactId]);
  useEffect(() => { endRef.current?.scrollIntoView(); }, [msgs]);

  async function send() {
    if (!conv || !text.trim()) return;
    setBusy(true); setErr("");
    try {
      const m = await api.post<ChatMessage>(`/api/conversations/${conv.id}/send/`, { text });
      setMsgs((x) => [...x, m]); setText("");
    } catch { setErr("Не удалось отправить (нужен токен канала)."); }
    finally { setBusy(false); }
  }
  async function aiSuggest() {
    if (!conv) return;
    setAiBusy(true);
    try {
      const r = await api.post<{ suggestion: string }>("/api/ai/suggest/", { conversation: conv.id });
      setText(r.suggestion);
    } catch { setErr("AI недоступен."); }
    finally { setAiBusy(false); }
  }

  if (!contactId) return <div className="panel"><div className="muted" style={{ fontSize: 13 }}>У сделки нет контакта — чат недоступен.</div></div>;
  if (!conv) return <div className="panel"><div className="label">Чат с клиентом</div><div className="muted" style={{ fontSize: 13 }}>Диалогов с этим клиентом пока нет. Появятся, когда он напишет в мессенджер.</div></div>;

  return (
    <div className="panel" style={{ display: "flex", flexDirection: "column", padding: 0, height: 460 }}>
      <div style={{ padding: "10px 14px", borderBottom: "1px solid #eef1f5", fontSize: 13, fontWeight: 600 }}>
        💬 Чат · {conv.channel_name}
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 8, background: "#f8fafc" }}>
        {msgs.map((m) => (
          <div key={m.id} style={{ maxWidth: "78%", padding: "8px 11px", borderRadius: 10, fontSize: 13,
            alignSelf: m.direction === "out" ? "flex-end" : "flex-start",
            background: m.direction === "out" ? "var(--brand)" : "#fff",
            color: m.direction === "out" ? "#fff" : "inherit", boxShadow: "0 1px 2px rgba(0,0,0,.05)" }}>
            {m.text}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      {err && <div className="err" style={{ padding: "0 14px" }}>{err}</div>}
      <div style={{ padding: 10, borderTop: "1px solid #eef1f5" }}>
        <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
          <button className="btn btn-light" style={{ fontSize: 12, height: 28 }} onClick={aiSuggest} disabled={aiBusy}>
            {aiBusy ? "AI думает…" : "🤖 AI-РОП: подсказать ответ"}
          </button>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Сообщение клиенту…" style={{ flex: 1, height: 34, background: "#f1f5f9", border: "none", borderRadius: 7, padding: "0 12px", fontSize: 13, outline: "none" }} />
          <button className="btn btn-primary" onClick={send} disabled={busy}>{busy ? "…" : "↑"}</button>
        </div>
      </div>
    </div>
  );
}
