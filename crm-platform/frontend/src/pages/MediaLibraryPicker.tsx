import { useEffect, useMemo, useState } from "react";
import { api, ChatMessage } from "../api";

type Asset = { id: number; title: string; kind: "image" | "video" | "catalog"; section: "colors" | "quick"; color_code: string; tags: string; url: string };
type Reply = { id: number; title: string; text: string; asset_ids: number[] };

export function MediaLibraryPicker({ conversationId, onSent, onClose }: { conversationId: number; onSent: (m: ChatMessage) => void; onClose: () => void }) {
  const [items, setItems] = useState<Asset[]>([]); const [replies, setReplies] = useState<Reply[]>([]);
  const [query, setQuery] = useState(""); const [tab, setTab] = useState<"colors" | "quick">("colors");
  const [picked, setPicked] = useState<number[]>([]); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  useEffect(() => { api.get<any>("/api/inbox/media-library/").then((d) => { setItems(d.items || []); setReplies(d.replies || []); }).catch(() => setError("Не вдалося завантажити бібліотеку")); }, []);
  const found = useMemo(() => items.filter((x) => x.section === tab && `${x.title} ${x.color_code} ${x.tags}`.toLowerCase().includes(query.toLowerCase())), [items, tab, query]);
  function toggle(id: number) { setPicked((v) => v.includes(id) ? v.filter((x) => x !== id) : [...v, id]); }
  async function send(replyId?: number) { setBusy(true); setError(""); try { const m = await api.post<ChatMessage>(`/api/conversations/${conversationId}/send-library/`, replyId ? { reply_id: replyId } : { item_ids: picked }); onSent(m); onClose(); } catch (e: any) { setError(e?.response?.data?.detail || "Не вдалося надіслати"); } finally { setBusy(false); } }
  return <div style={{ position: "absolute", zIndex: 50, left: 0, bottom: 46, width: 380, maxWidth: "calc(100vw - 24px)", maxHeight: 440, overflow: "auto", background: "#fff", border: "1px solid #cbd5e1", borderRadius: 12, padding: 10, boxShadow: "0 12px 32px rgba(15,23,42,.2)" }}>
    <div style={{ display: "flex", gap: 6, marginBottom: 8 }}><b style={{ fontSize: 13 }}>Бібліотека</b><span style={{ flex: 1 }} /><button className="btn" style={{ padding: "1px 7px" }} onClick={onClose}>×</button></div>
    <div style={{ display: "flex", gap: 6, marginBottom: 8 }}><button className="btn" onClick={() => setTab("colors")} style={{ fontSize: 12, background: tab === "colors" ? "#e0edff" : undefined }}>🎨 Кольори</button><button className="btn" onClick={() => setTab("quick")} style={{ fontSize: 12, background: tab === "quick" ? "#e0edff" : undefined }}>⚡ Швидкі відповіді</button></div>
    {tab === "quick" && <div style={{ display: "grid", gap: 6, marginBottom: 8 }}>{replies.map((r) => <button key={r.id} className="btn" style={{ justifyContent: "flex-start", textAlign: "left", fontSize: 12 }} disabled={busy} onClick={() => send(r.id)}><b>{r.title}</b>{r.text ? <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}> — {r.text}</span> : ""}</button>)}</div>}
    <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={tab === "colors" ? "Код або відтінок, наприклад CSK 03-32" : "Пошук матеріалу"} style={{ width: "100%", boxSizing: "border-box", padding: "7px 9px", border: "1px solid #cbd5e1", borderRadius: 7, fontSize: 12, marginBottom: 8 }} />
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7 }}>{found.map((a) => <button key={a.id} onClick={() => toggle(a.id)} style={{ border: picked.includes(a.id) ? "2px solid var(--brand)" : "1px solid #dbe3ee", background: "#fff", padding: 5, borderRadius: 8, textAlign: "left", cursor: "pointer" }}>{a.url && a.kind !== "video" && <img src={a.url} style={{ width: "100%", height: 65, objectFit: "cover", borderRadius: 5 }} />}<div style={{ fontSize: 11, marginTop: 3 }}>{a.kind === "video" ? "🎥 " : ""}{a.color_code ? <b>{a.color_code}</b> : ""} {a.title}</div></button>)}</div>
    {!found.length && <div className="muted" style={{ fontSize: 12 }}>Матеріалів поки немає — додайте їх у Налаштування → Відкриті лінії.</div>}
    {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 6 }}>{error}</div>}
    {picked.length > 0 && <button className="btn btn-primary" disabled={busy} onClick={() => send()} style={{ marginTop: 9, width: "100%" }}>{busy ? "…" : `Надіслати (${picked.length})`}</button>}
  </div>;
}
