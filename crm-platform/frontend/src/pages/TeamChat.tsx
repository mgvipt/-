/* Внутрішній чат між співробітниками: DM, емодзі, файли, згадки @. */
import { useEffect, useState, useRef } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
import { Avatar } from "../ui";
import { linkify } from "../chatUtils";

const EMOJIS = ["👋","🤚","🖐️","✋","🖖","👌","🤌","🤏","✌️","🤞","🫰","🤟","🤘","🤙","👈","👉","👆","👇","☝️","🫵","👍","👎","✊","👊","🤛","🤜","👏","🙌","🫶","👐","🤲","🤝","🙏","✍️","💪","😀","😁","😂","🤣","🙂","😊","😉","😍","🥰","😎","🤩","🤗","😋","😜","🤔","😅","😴","🥳","😇","🤯","😱","😭","😤","👀","❤️","🧡","💛","💚","💙","💜","🖤","🔥","💯","✨","⭐","🎉","🎁","✅","❗","⚠️","📌","📎","📷","📞","💬","🚀","💡","☕","🍕"];

export default function TeamChat() {
  const { t } = useLang();
  const [contacts, setContacts] = useState<any[]>([]);
  const [sel, setSel] = useState<any>(null);
  const [msgs, setMsgs] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [mentions, setMentions] = useState<number[]>([]);
  const [showEmoji, setShowEmoji] = useState(false);
  const [showMention, setShowMention] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const loadContacts = () => api.get<any>("/api/team-chat/contacts/").then(setContacts).catch(() => {});
  useEffect(() => { loadContacts(); const tm = setInterval(loadContacts, 15000); return () => clearInterval(tm); }, []);
  useEffect(() => { if (sel) { api.get<any>(`/api/team-chat/${sel.id}/`).then((d) => { setMsgs(d); setTimeout(() => endRef.current?.scrollIntoView(), 60); }); const tm = setInterval(() => api.get<any>(`/api/team-chat/${sel.id}/`).then(setMsgs).catch(() => {}), 8000); return () => clearInterval(tm); } }, [sel]);

  async function send() {
    if (!sel || !text.trim()) return;
    try { const m = await api.post<any>(`/api/team-chat/${sel.id}/`, { text, mentions }); setMsgs((p) => [...p, m]); setText(""); setMentions([]); setTimeout(() => endRef.current?.scrollIntoView(), 60); loadContacts(); } catch { /* */ }
  }
  function sendFile(f: File) {
    if (!sel) return;
    const r = new FileReader();
    r.onload = async () => { try { const m = await api.post<any>(`/api/team-chat/${sel.id}/`, { content_b64: r.result, filename: f.name }); setMsgs((p) => [...p, m]); setTimeout(() => endRef.current?.scrollIntoView(), 60); } catch { /* */ } };
    r.readAsDataURL(f);
  }
  function addMention(c: any) { setText((x) => x + "@" + c.full_name + " "); setMentions((m) => Array.from(new Set([...m, c.id]))); setShowMention(false); }

  return (
    <div style={{ display: "flex", height: "calc(100vh - 130px)", border: "1px solid #e2e8f0", borderRadius: 12, overflow: "hidden", background: "#fff" }}>
      <div style={{ width: 270, borderRight: "1px solid #e2e8f0", overflowY: "auto" }}>
        <div className="label" style={{ padding: "10px 12px" }}>{t("Сотрудники", "Співробітники")}</div>
        {contacts.map((c) => (
          <div key={c.id} onClick={() => setSel(c)} style={{ padding: "9px 12px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", background: sel?.id === c.id ? "#eff6ff" : "transparent", display: "flex", gap: 8, alignItems: "center" }}>
            <Avatar name={c.full_name} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{c.full_name}</div>
              <div className="muted" style={{ fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.last || c.dept}</div>
            </div>
            {c.unread > 0 && <span style={{ background: "#dc2626", color: "#fff", borderRadius: 10, fontSize: 11, padding: "1px 7px" }}>{c.unread}</span>}
          </div>
        ))}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {!sel ? <div className="muted" style={{ padding: 40, textAlign: "center" }}>{t("Выбери сотрудника слева, чтобы написать", "Обери співробітника зліва, щоб написати")}</div> : <>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid #e2e8f0", fontWeight: 700 }}>{sel.full_name} <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>· {sel.dept || "—"}</span></div>
          <div style={{ flex: 1, overflowY: "auto", padding: 14, background: "#f8fafc" }}>
            {msgs.map((m) => (
              <div key={m.id} style={{ display: "flex", justifyContent: m.out ? "flex-end" : "flex-start", marginBottom: 8 }}>
                <div style={{ maxWidth: "70%", background: m.out ? "#2563eb" : "#fff", color: m.out ? "#fff" : "#0f172a", borderRadius: 12, padding: "7px 11px", border: m.out ? "none" : "1px solid #e2e8f0", fontSize: 13.5 }}>
                  {m.text && <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{linkify(m.text, m.out)}</div>}
                  {(m.attachments || []).map((a: any, i: number) => <a key={i} href={a.url} target="_blank" rel="noreferrer" style={{ color: m.out ? "#fff" : "#2563eb", fontSize: 12, textDecoration: "underline", display: "block", marginTop: 2 }}>{a.kind === "image" ? "📷" : "📎"} {a.name}</a>)}
                  <div style={{ fontSize: 10, opacity: 0.6, marginTop: 2, textAlign: "right" }}>{new Date(m.created_at).toLocaleString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</div>
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
          <div style={{ borderTop: "1px solid #e2e8f0", padding: 10, position: "relative" }}>
            {showEmoji && <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 8, padding: 8, background: "#f8fafc", borderRadius: 8, maxHeight: 180, overflowY: "auto" }}>{EMOJIS.map((e) => <span key={e} onClick={() => { setText((x) => x + e); setShowEmoji(false); }} style={{ cursor: "pointer", fontSize: 21 }}>{e}</span>)}</div>}
            {showMention && <div style={{ position: "absolute", bottom: 56, left: 10, background: "#fff", border: "1px solid #cbd5e1", borderRadius: 8, boxShadow: "0 4px 16px rgba(0,0,0,.15)", maxHeight: 200, overflowY: "auto", zIndex: 5, minWidth: 200 }}>{contacts.map((c) => <div key={c.id} onClick={() => addMention(c)} style={{ padding: "6px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f1f5f9" }}>@ {c.full_name}</div>)}</div>}
            <div style={{ display: "flex", gap: 6, alignItems: "flex-end" }}>
              <button className="btn btn-light" style={{ padding: "6px 9px" }} onClick={() => { setShowEmoji((s) => !s); setShowMention(false); }} title={t("Эмодзи", "Емодзі")}>😊</button>
              <button className="btn btn-light" style={{ padding: "6px 9px" }} onClick={() => { setShowMention((s) => !s); setShowEmoji(false); }} title={t("Упомянуть сотрудника", "Згадати співробітника")}>@</button>
              <button className="btn btn-light" style={{ padding: "6px 9px" }} onClick={() => fileRef.current?.click()} title={t("Файл", "Файл")}><Icon n="📎" size={16} /></button>
              <input ref={fileRef} type="file" style={{ display: "none" }} onChange={(e) => { if (e.target.files?.[0]) sendFile(e.target.files[0]); e.target.value = ""; }} />
              <textarea value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} placeholder={t("Сообщение…", "Повідомлення…")} style={{ flex: 1, minHeight: 38, maxHeight: 120, border: "1px solid #cbd5e1", borderRadius: 8, padding: "8px 10px", resize: "vertical", fontSize: 13.5, boxSizing: "border-box" }} />
              <button className="btn btn-primary" style={{ padding: "8px 12px" }} onClick={send} disabled={!text.trim()}><Icon n="send" size={16} /></button>
            </div>
          </div>
        </>}
      </div>
    </div>
  );
}
