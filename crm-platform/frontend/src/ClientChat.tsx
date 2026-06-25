/* Вбудований чат з клієнтом + AI-РОП. Стрічка повідомлень і поле відповіді —
 * обидва з регульованою висотою (тягни за правий нижній кут). AI-РОП показує
 * тези діалогу + рекомендовану відповідь прямо тут. */
import { useEffect, useRef, useState } from "react";
import { api, ChatMessage, Conversation, Paginated } from "./api";
import ChatActions from "./ChatActions";

export default function ClientChat({ contact }: { contact?: number | null }) {
  const [conv, setConv] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [ai, setAi] = useState<{ context?: string; points?: string[]; suggestion?: string } | null>(null);
  const [aiLoad, setAiLoad] = useState(false);
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

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
  // ── Надіслати фото/відео клієнту ──
  async function sendFile(e: any) {
    const f = e.target.files?.[0];
    if (!f || !conv) return;
    const kind = f.type.startsWith("video") ? "video" : f.type.startsWith("image") ? "photo" : "document";
    setBusy(true); setErr("");
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const m = await api.post<ChatMessage>(`/api/conversations/${conv.id}/send_media/`, { content_b64: reader.result, filename: f.name, kind });
        setMsgs((p) => [...p, m]);
      } catch { setErr("Не вдалося надіслати файл (цей канал може не підтримувати медіа)"); }
      setBusy(false);
    };
    reader.readAsDataURL(f);
    e.target.value = "";
  }
  async function analyze() {
    if (!conv) return;
    setAiLoad(true); setErr("");
    try { setAi(await api.post<any>(`/api/conversations/${conv.id}/ai_reply/`, {})); }
    catch { setErr("AI-РОП тимчасово недоступний"); }
    setAiLoad(false);
  }

  if (!loaded) return <div className="muted" style={{ fontSize: 13 }}>Завантаження чату…</div>;
  if (!contact) return <div className="muted" style={{ fontSize: 13 }}>Немає привʼязаного клієнта</div>;
  if (!conv) return <div className="muted" style={{ fontSize: 13 }}>Переписки ще немає — зʼявиться після першого повідомлення клієнта в Instagram</div>;

  const pts = ai ? (ai.points && ai.points.length ? ai.points : (ai.context ? [ai.context] : [])) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <ChatActions convId={conv.id} onClosed={() => { setConv(null); setMsgs([]); }} onChanged={(c) => setConv(c)} />
      {/* СТРІЧКА — заповнює доступну висоту */}
      <div style={{ height: 340, minHeight: 140, maxHeight: "70vh", resize: "vertical", overflowY: "auto", display: "flex", flexDirection: "column", gap: 6, padding: 10, background: "#f8fafc", borderRadius: 10, border: "1px solid #eef2f7" }}>
        {msgs.length === 0 && <div className="muted" style={{ fontSize: 13 }}>Повідомлень поки немає</div>}
        {msgs.map((m) => (
          <div key={m.id} style={{ alignSelf: m.direction === "in" ? "flex-start" : "flex-end", maxWidth: "82%" }}>
            <div style={{ fontSize: 10.5, color: "#94a3b8", marginBottom: 2, textAlign: m.direction === "in" ? "left" : "right" }}>
              {m.direction === "in" ? "Клієнт" : (m.sender_name === "ai_assistant" ? "Юля (AI)" : (m.sender_name || "Менеджер"))}
            </div>
            <div style={{ background: m.direction === "in" ? "#ffffff" : "#dbeafe", padding: "7px 11px", borderRadius: 12, fontSize: 13, whiteSpace: "pre-wrap", border: m.direction === "in" ? "1px solid #eef2f7" : "none" }}>{m.text}</div>
            <div style={{ fontSize: 9.5, color: "#cbd5e1", marginTop: 2, textAlign: m.direction === "in" ? "left" : "right" }}>{(m as any).created_at ? new Date((m as any).created_at).toLocaleTimeString("uk", { hour: "2-digit", minute: "2-digit" }) : ""}</div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {/* AI-РОП — тези + рекомендована відповідь */}
      {ai && (
        <div style={{ marginTop: 8, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 10, padding: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#92400e", marginBottom: 6 }}>🧠 AI-РОП — що в діалозі</div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, lineHeight: 1.5, color: "#334155" }}>
            {pts.map((p, i) => <li key={i} style={{ marginBottom: 3 }}>{p}</li>)}
          </ul>
          {ai.suggestion && (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#92400e", margin: "10px 0 5px" }}>Рекомендована відповідь</div>
              <div style={{ fontSize: 12.5, background: "#fff", border: "1px solid #fde68a", borderRadius: 8, padding: 8, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{ai.suggestion}</div>
              <button className="btn" style={{ marginTop: 6, fontSize: 12, background: "#fde68a", color: "#92400e" }} onClick={() => setText(ai.suggestion || "")}>✍️ Вставити у відповідь</button>
            </>
          )}
        </div>
      )}

      {err && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 6 }}>{err}</div>}

      {/* ПОЛЕ ВІДПОВІДІ — теж регульоване */}
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Відповідь клієнту…" rows={3}
        style={{ width: "100%", fontSize: 13, padding: 9, borderRadius: 10, border: "1px solid #e2e8f0", marginTop: 8, boxSizing: "border-box", resize: "vertical", minHeight: 56 }} />
      <input ref={fileRef} type="file" accept="image/*,video/*" hidden onChange={sendFile} />
      <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
        <button className="btn" style={{ background: "#f1f5f9" }} title="Надіслати фото / відео" onClick={() => fileRef.current?.click()} disabled={busy}>📎</button>
        <button className="btn" style={{ flex: 1, background: "#fef3c7", color: "#92400e" }} onClick={analyze} disabled={aiLoad}>{aiLoad ? "AI аналізує…" : "🧠 AI-РОП підказати відповідь"}</button>
        <button className="btn btn-primary" style={{ flex: 1 }} onClick={send} disabled={busy || !text.trim()}>{busy ? "…" : "Надіслати"}</button>
      </div>
    </div>
  );
}
