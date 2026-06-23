/* Вбудований чат з клієнтом + AI-РОП підказка. Використовується в картці ліда і сделки.
 * Знаходить переписку по контакту, показує живу стрічку (опитує кожні 6с),
 * дозволяє відповісти і попросити AI-РОП підказати відповідь. */
import { useEffect, useRef, useState } from "react";
import { api, ChatMessage, Conversation, Paginated } from "./api";

export default function ClientChat({ contact }: { contact?: number | null }) {
  const [conv, setConv] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [ai, setAi] = useState<{ context?: string } | null>(null);
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  async function loadConv() {
    if (!contact) { setLoaded(true); return; }
    try {
      const r = await api.get<Paginated<Conversation>>(`/api/conversations/?contact=${contact}`);
      const c = ((r as any).results || (r as any) || [])[0] || null;
      setConv(c);
      if (c) loadMsgs(c.id);
    } catch { /* ignore */ }
    setLoaded(true);
  }
  async function loadMsgs(id: number) {
    try {
      const m = await api.get<ChatMessage[]>(`/api/conversations/${id}/messages/`);
      setMsgs((prev) => (m.length !== prev.length ? m : prev));
    } catch { /* ignore */ }
  }
  useEffect(() => { loadConv(); /* eslint-disable-next-line */ }, [contact]);
  useEffect(() => {
    if (!conv) return;
    const t = setInterval(() => loadMsgs(conv.id), 6000);
    return () => clearInterval(t);
  }, [conv]);
  useEffect(() => { endRef.current?.scrollIntoView(); }, [msgs]);

  async function send() {
    if (!conv || !text.trim()) return;
    setBusy(true); setErr("");
    try {
      const m = await api.post<ChatMessage>(`/api/conversations/${conv.id}/send/`, { text });
      setMsgs((p) => [...p, m]); setText("");
    } catch { setErr("Не вдалося надіслати — чат має бути відкритий оператором"); }
    setBusy(false);
  }
  async function aiReply() {
    if (!conv) return;
    setBusy(true); setErr("");
    try {
      const d = await api.post<{ context?: string; suggestion?: string }>(`/api/conversations/${conv.id}/ai_reply/`, {});
      setAi(d);
      if (d.suggestion) setText(d.suggestion);
    } catch { setErr("AI-РОП тимчасово недоступний"); }
    setBusy(false);
  }

  if (!loaded) return <div className="muted" style={{ fontSize: 13 }}>Завантаження чату…</div>;
  if (!contact) return <div className="muted" style={{ fontSize: 13 }}>Немає привʼязаного клієнта</div>;
  if (!conv) return <div className="muted" style={{ fontSize: 13 }}>Переписки ще немає — зʼявиться після першого повідомлення клієнта в Instagram</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 440 }}>
      <div style={{ flex: 1, minHeight: 160, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6, padding: 10, background: "#f8fafc", borderRadius: 10, border: "1px solid #eef2f7" }}>
        {msgs.length === 0 && <div className="muted" style={{ fontSize: 13 }}>Повідомлень поки немає</div>}
        {msgs.map((m) => (
          <div key={m.id} style={{ alignSelf: m.direction === "in" ? "flex-start" : "flex-end", maxWidth: "80%" }}>
            <div style={{ fontSize: 10.5, color: "#94a3b8", marginBottom: 2, textAlign: m.direction === "in" ? "left" : "right" }}>
              {m.direction === "in" ? "Клієнт" : (m.sender_name === "ai_assistant" ? "Юля (AI)" : (m.sender_name || "Менеджер"))}
            </div>
            <div style={{ background: m.direction === "in" ? "#ffffff" : "#dbeafe", padding: "7px 11px", borderRadius: 12, fontSize: 13, whiteSpace: "pre-wrap", border: m.direction === "in" ? "1px solid #eef2f7" : "none" }}>{m.text}</div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {ai?.context && (
        <div style={{ marginTop: 10, fontSize: 12.5, background: "#fffbeb", border: "1px solid #fde68a", padding: "8px 10px", borderRadius: 10 }}>
          🧠 <b>AI-РОП:</b> {ai.context}
        </div>
      )}
      {err && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 6 }}>{err}</div>}

      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Відповідь клієнту…" rows={2}
        style={{ width: "100%", fontSize: 13, padding: 9, borderRadius: 10, border: "1px solid #e2e8f0", marginTop: 8, boxSizing: "border-box", resize: "vertical" }} />
      <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
        <button className="btn" style={{ flex: 1, background: "#fef3c7", color: "#92400e" }} onClick={aiReply} disabled={busy}>🧠 AI-РОП підказати відповідь</button>
        <button className="btn btn-primary" style={{ flex: 1 }} onClick={send} disabled={busy || !text.trim()}>{busy ? "…" : "Надіслати"}</button>
      </div>
    </div>
  );
}
