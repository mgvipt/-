import { useEffect, useRef, useState } from "react";
import { api, ChatMessage, Conversation, Paginated } from "../api";
import { Avatar, SourceChip } from "../ui";
import { useAuth } from "../auth";

export default function Inbox() {
  const { can } = useAuth();
  const [scope, setScope] = useState<"mine" | "all" | "unassigned">("all");
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  async function loadConvs() {
    const q = scope && scope !== "all" ? `?scope=${scope}` : "";
    const d = await api.get<Paginated<Conversation>>(`/api/conversations/${q}`);
    setConvs(d.results);
    if (d.results[0]) openConv(d.results[0]);
  }
  useEffect(() => { loadConvs(); }, [scope]);
  useEffect(() => { endRef.current?.scrollIntoView(); }, [msgs]);

  async function openConv(c: Conversation) {
    setActive(c); setErr("");
    const m = await api.get<ChatMessage[]>(`/api/conversations/${c.id}/messages/`);
    setMsgs(m);
    setConvs((cs) => cs.map((x) => (x.id === c.id ? { ...x, unread: 0 } : x)));
  }

  async function send() {
    if (!active || !text.trim()) return;
    setSending(true); setErr("");
    try {
      const m = await api.post<ChatMessage>(`/api/conversations/${active.id}/send/`, { text });
      setMsgs((ms) => [...ms, m]);
      setText("");
    } catch (e: any) {
      setErr("Не удалось отправить (проверь токен бота / сеть).");
    } finally { setSending(false); }
  }

  return (
    <div className="inbox fade" style={{ height: "100%", display: "grid", gridTemplateColumns: "320px 1fr" }}>
      {/* список диалогов */}
      <div style={{ background: "#fff", borderRight: "1px solid #e2e8f0", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: 12, borderBottom: "1px solid #e2e8f0", fontWeight: 600 }}>Диалоги</div>
        <div style={{ display: "flex", gap: 6, padding: "8px 12px", borderBottom: "1px solid #f1f5f9" }}>
          {(([["mine", "Мої"]].concat(can("conversation.view.all") ? [["all", "Всі"], ["unassigned", "Не призначені"]] : [])) as [string, string][]).map(([k, label]) => (
            <button key={k} onClick={() => setScope(k as any)}
              style={{ fontSize: 12, padding: "4px 10px", borderRadius: 14, cursor: "pointer",
                border: "1px solid " + (scope === k ? "var(--brand)" : "#e2e8f0"),
                background: scope === k ? "var(--brand)" : "#fff", color: scope === k ? "#fff" : "#475569" }}>{label}</button>
          ))}
        </div>
        <div style={{ flex: 1, overflowY: "auto" }}>
          {convs.length === 0 && <div className="spin">Пока нет диалогов. Напиши боту в Telegram — появится здесь.</div>}
          {convs.map((c) => (
            <div key={c.id} onClick={() => openConv(c)}
              style={{ padding: "10px 12px", borderBottom: "1px solid #f1f5f9", cursor: "pointer",
                display: "flex", gap: 9, background: active?.id === c.id ? "#eff6ff" : "" }}>
              <Avatar name={c.contact_name || c.title || "?"} cls="av-md" />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{c.contact_name || c.title || "Без имени"}</span>
                  <SourceChip source={c.channel_kind} />
                </div>
                <div className="muted" style={{ fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.last_text}</div>
                <div style={{ fontSize: 11, color: c.assigned_to ? "#2563eb" : "#94a3b8" }}>{c.assigned_to ? "👤 " + c.assigned_to_name : "Не призначено"}</div>
              </div>
              {c.unread > 0 && <span style={{ width: 16, height: 16, borderRadius: "50%", background: "#3b82f6", color: "#fff", fontSize: 10, display: "flex", alignItems: "center", justifyContent: "center", alignSelf: "center" }}>{c.unread}</span>}
            </div>
          ))}
        </div>
      </div>

      {/* переписка */}
      <div style={{ display: "flex", flexDirection: "column", background: "#f8fafc", overflow: "hidden" }}>
        {!active ? (
          <div className="spin">Выбери диалог слева</div>
        ) : (
          <>
            <div style={{ height: 52, background: "#fff", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 8, padding: "0 16px" }}>
              <b style={{ fontSize: 14 }}>{active.contact_name || active.title}</b>
              <SourceChip source={active.channel_kind} />
              <div className="spacer" />
              <button className="btn btn-green">📞 Позвонить</button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
              {msgs.map((m) => (
                <div key={m.id} className={"msg" + (m.direction === "out" ? " me" : "")}
                  style={{ maxWidth: "70%", padding: "9px 11px", borderRadius: 10, fontSize: 13,
                    alignSelf: m.direction === "out" ? "flex-end" : "flex-start",
                    background: m.direction === "out" ? "var(--brand)" : "#fff",
                    color: m.direction === "out" ? "#fff" : "inherit",
                    boxShadow: "0 1px 2px rgba(0,0,0,.05)" }}>
                  {m.text}
                  {m.attachments?.map((a, i) => (
                    <div key={i} style={{ fontSize: 11, opacity: .8, marginTop: 4 }}>
                      📎 {a.type === "voice" ? `голосовое ${a.duration ?? ""}с` : a.type}
                    </div>
                  ))}
                </div>
              ))}
              <div ref={endRef} />
            </div>
            {err && <div className="err" style={{ padding: "0 16px" }}>{err}</div>}
            <div style={{ background: "#fff", borderTop: "1px solid #e2e8f0", padding: 12, display: "flex", gap: 8 }}>
              <input value={text} onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send()}
                placeholder={`Сообщение уйдёт в ${active.channel_name}…`}
                style={{ flex: 1, height: 36, background: "#f1f5f9", border: "none", borderRadius: 7, padding: "0 12px", fontSize: 13, outline: "none" }} />
              <button className="btn btn-primary" onClick={send} disabled={sending}>{sending ? "…" : "Отправить"}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
