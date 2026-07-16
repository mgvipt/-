/* Вбудований чат з клієнтом + AI-РОП. Стрічка повідомлень і поле відповіді —
 * обидва з регульованою висотою (тягни за правий нижній кут). AI-РОП показує
 * тези діалогу + рекомендовану відповідь прямо тут. */
import { Fragment, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { EmojiButton } from "./ChatCompose";
import { Icon } from "./Icon";
import { api, ChatMessage, Conversation, Paginated } from "./api";
import ChatActions from "./ChatActions";
import { dayLabel, timeLabel, isNewDay, linkify, metaWindow } from "./chatUtils";

const tt = (_r: string, ua: string) => ua;  // ClientChat україномовний
type ReplyChannel = { channel_id: number; channel_kind: string; channel_name: string; number?: string; conversation_id?: number | null; selected?: boolean };

export default function ClientChat({ contact, markSeen = true, channelPickerTargetId }: { contact?: number | null; markSeen?: boolean; channelPickerTargetId?: string }) {
  const [conv, setConv] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ai, setAi] = useState<{ context?: string; points?: string[]; suggestion?: string } | null>(null);
  const [aiLoad, setAiLoad] = useState(false);
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [replyChannels, setReplyChannels] = useState<ReplyChannel[]>([]);
  const [switchingChannel, setSwitchingChannel] = useState(false);
  const [channelPickerTarget, setChannelPickerTarget] = useState<HTMLElement | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function loadConv() {
    if (!contact) { setLoaded(true); return; }
    try {
      const r = await api.get<Paginated<Conversation>>(`/api/conversations/by_contact/?contact=${contact}`);
      const c = ((r as any).results || (r as any) || [])[0] || null;
      setConv(c);
      if (c) loadMsgs(c.id);
    } catch { /* ignore */ }
    setLoaded(true);
  }
  async function loadMsgs(id: number) {
    try {
      const m = await api.get<ChatMessage[]>(`/api/conversations/${id}/messages/${markSeen ? "?seen=1" : ""}`);
      setMsgs((prev) => (m.length !== prev.length ? m : prev));
    } catch { /* ignore */ }
  }
  async function loadReplyChannels(id: number) {
    try { setReplyChannels(await api.get<ReplyChannel[]>(`/api/conversations/${id}/reply_channels/`)); }
    catch { setReplyChannels([]); }
  }
  async function useChannel(channelId: number) {
    if (!conv || channelId === conv.channel) return;
    setSwitchingChannel(true); setErr("");
    try {
      const selected = await api.post<Conversation>(`/api/conversations/${conv.id}/use_channel/`, { channel_id: channelId });
      setConv(selected); setMsgs([]); setAi(null);
      await Promise.all([loadMsgs(selected.id), loadReplyChannels(selected.id)]);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Не вдалося вибрати канал");
    }
    setSwitchingChannel(false);
  }
  useEffect(() => { loadConv(); /* eslint-disable-next-line */ }, [contact]);
  useEffect(() => {
    setChannelPickerTarget(channelPickerTargetId ? document.getElementById(channelPickerTargetId) : null);
  }, [channelPickerTargetId]);
  useEffect(() => {
    if (!conv) return;
    loadReplyChannels(conv.id);
    const t = setInterval(() => loadMsgs(conv.id), 6000);
    return () => clearInterval(t);
  }, [conv]);
  useEffect(() => { const el = endRef.current?.parentElement as HTMLElement | undefined; if (el) el.scrollTop = el.scrollHeight; }, [msgs]);

  async function send() {
    if (!conv || !text.trim()) return;
    setBusy(true); setErr("");
    try {
      const m = await api.post<ChatMessage>(`/api/conversations/${conv.id}/send/`, { text, internal });
      setMsgs((p) => [...p, m]); setText("");
    } catch (e: any) { setErr(e?.response?.data?.detail || "Не вдалося надіслати — чат має бути відкритий оператором"); }
    setBusy(false);
  }
  // ── Надіслати фото/відео клієнту ──
  function onPasteFile(e: any) {
    const items = e.clipboardData?.items || [];
    for (let i = 0; i < items.length; i++) { const it = items[i]; if (it.type && it.type.startsWith("image")) { const f = it.getAsFile(); if (f) { e.preventDefault(); uploadFile(f); return; } } }
  }
  async function uploadFile(f: File | null | undefined) {
    if (!f || !conv) return;
    const kind = f.type.startsWith("video") ? "video" : f.type.startsWith("image") ? "photo" : "document";
    setBusy(true); setErr("");
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const m = await api.post<ChatMessage>(`/api/conversations/${conv.id}/send_media/`, { content_b64: reader.result, filename: f.name, kind });
        setMsgs((p) => [...p, m]);
      } catch (e: any) { setErr(e?.response?.data?.detail || "Не вдалося надіслати файл (цей канал може не підтримувати медіа)"); }
      setBusy(false);
    };
    reader.readAsDataURL(f);
  }
  async function sendFile(e: any) { await uploadFile(e.target.files?.[0]); e.target.value = ""; }
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
  const channelPicker = (
    <div data-testid="reply-channel-picker" style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: channelPickerTargetId ? 0 : 7, width: "100%" }}>
      <span style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700, whiteSpace: "nowrap" }}>Відповідати через</span>
      <select value={conv.channel} onChange={(e) => useChannel(Number(e.target.value))} disabled={switchingChannel}
        title="Оберіть канал і номер, від імені якого CRM напише клієнту"
        style={{ minWidth: 0, flex: 1, height: 30, border: "1px solid #cbd5e1", borderRadius: 7, background: "#fff", color: "#334155", padding: "0 7px", fontSize: 11.5, fontWeight: 600 }}>
        {replyChannels.length === 0 && <option value={conv.channel}>{conv.channel_name}</option>}
        {replyChannels.map((line) => (
          <option key={line.channel_id} value={line.channel_id}>
            {line.channel_name}{line.number && !line.channel_name.includes(line.number) ? ` · ${line.number}` : ""}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", containerType: "inline-size", height: "calc(100vh - 96px)", maxHeight: "calc(100vh - 96px)" }}>
      {channelPickerTargetId ? (channelPickerTarget ? createPortal(channelPicker, channelPickerTarget) : null) : channelPicker}
      <ChatActions convId={conv.id} onClosed={() => { setConv(null); setMsgs([]); }} onChanged={(c) => setConv(c)} />
      {/* СТРІЧКА — заповнює доступну висоту */}
      <div style={{ flex: 1, minHeight: 80, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6, padding: 10, background: "#f8fafc", borderRadius: 10, border: "1px solid #eef2f7" }}>
        {msgs.length === 0 && <div className="muted" style={{ fontSize: 13 }}>Повідомлень поки немає</div>}
        {msgs.map((m, i) => (
          <Fragment key={m.id}>
            {isNewDay((m as any).created_at, (msgs[i - 1] as any)?.created_at) && (
              <div style={{ position: "sticky", top: 2, zIndex: 3, textAlign: "center", margin: "6px 0 4px", pointerEvents: "none" }}><span style={{ fontSize: 11, fontWeight: 700, color: "#475569", background: "#e2e8f0", borderRadius: 20, padding: "3px 13px", boxShadow: "0 1px 4px rgba(0,0,0,.14)" }}>{dayLabel((m as any).created_at, tt)}</span></div>
            )}
            <div style={{ alignSelf: m.direction === "in" ? "flex-start" : "flex-end", maxWidth: "82%" }}>
              <div style={{ fontSize: 10.5, color: "#94a3b8", marginBottom: 2, textAlign: m.direction === "in" ? "left" : "right" }}>
                {m.direction === "in" ? "Клієнт" : (m.sender_name === "ai_assistant" ? "Юля (AI)" : (m.sender_name || "Менеджер"))}
              </div>
              <div style={{ background: (m as any).internal ? "#fef9c3" : (m.direction === "in" ? "#ffffff" : "#dbeafe"), padding: "7px 11px", borderRadius: 12, fontSize: 13, whiteSpace: "pre-wrap", border: (m as any).internal ? "1px dashed #d4a017" : (m.direction === "in" ? "1px solid #eef2f7" : "none") }}>
                {(m as any).internal && <div style={{ fontSize: 10, fontWeight: 600, color: "#92400e", marginBottom: 2 }}><Icon n="📝" size={12} /> Нотатка (тільки команда)</div>}
                <span style={{ wordBreak: "break-word" }}>{linkify(m.text, m.direction !== "in")}</span>
                {(m as any).attachments?.map((a: any, j: number) => (
                  (a.url && a.type === "photo") ? <a key={j} href={a.url} target="_blank" rel="noreferrer" style={{ display: "block", marginTop: 6 }}><img src={a.url} alt="" style={{ maxWidth: 220, maxHeight: 240, borderRadius: 8, display: "block", objectFit: "cover" }} /></a>
                  : (a.url && a.type === "video") ? <video key={j} src={a.url} controls style={{ maxWidth: 220, borderRadius: 8, marginTop: 6, display: "block" }} />
                  : (a.url && a.type === "voice") ? <audio key={j} src={a.url} controls style={{ marginTop: 6, maxWidth: 220 }} />
                  : a.url ? <a key={j} href={a.url} target="_blank" rel="noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: 12.5, color: "#2563eb", fontWeight: 600 }}><Icon n="paperclip" size={14} /> {a.name || "файл"}</a>
                  : null
                ))}
              </div>
              <div style={{ fontSize: 9.5, color: "#cbd5e1", marginTop: 2, textAlign: m.direction === "in" ? "left" : "right" }}>{timeLabel((m as any).created_at)}</div>
            </div>
          </Fragment>
        ))}
        <div ref={endRef} />
      </div>

      {/* AI-РОП — тези + рекомендована відповідь */}
      {ai && (
        <div style={{ marginTop: 8, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 10, padding: 10, maxHeight: 220, overflowY: "auto", flexShrink: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#92400e", marginBottom: 6 }}><Icon n="🧠" size={14} /> AI-РОП — що в діалозі</div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, lineHeight: 1.5, color: "#334155" }}>
            {pts.map((p, i) => <li key={i} style={{ marginBottom: 3 }}>{p}</li>)}
          </ul>
          {ai.suggestion && (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#92400e", margin: "10px 0 5px" }}>Рекомендована відповідь</div>
              <div style={{ fontSize: 12.5, background: "#fff", border: "1px solid #fde68a", borderRadius: 8, padding: 8, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{ai.suggestion}</div>
              <button className="btn" style={{ marginTop: 6, fontSize: 12, background: "#fde68a", color: "#92400e" }} onClick={() => setText(ai.suggestion || "")}><Icon n="✍️" size={13} /> Вставити у відповідь</button>
            </>
          )}
        </div>
      )}

      {err && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 6 }}>{err}</div>}

      {(() => { const w = metaWindow(conv, msgs); return w && w.closed ? <div style={{ background: "#fee2e2", color: "#b91c1c", fontSize: 11.5, fontWeight: 600, padding: "6px 10px", borderRadius: 6, marginTop: 8, lineHeight: 1.35 }}>⚠️ Вікно Instagram закрите (минуло {w.hrs}г). Повідомлення може НЕ дійти — дочекайся відповіді клієнта.</div> : null; })()}
      {/* ПОЛЕ ВІДПОВІДІ — теж регульоване */}
      <textarea value={text} onChange={(e) => setText(e.target.value)} onPaste={onPasteFile} placeholder={internal ? "Внутрішня нотатка — клієнт НЕ побачить…  (вставити фото — Ctrl+V)" : "Відповідь клієнту…  (вставити фото — Ctrl+V)"} rows={3}
        style={{ width: "100%", fontSize: 13, padding: 9, borderRadius: 10, border: internal ? "1.5px dashed #d4a017" : "1px solid #e2e8f0", background: internal ? "#fffbeb" : "#fff", marginTop: 8, boxSizing: "border-box", resize: "vertical", minHeight: 56, flexShrink: 0 }} />
      <input ref={fileRef} type="file" hidden onChange={sendFile} />
      <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "nowrap" }}>
        <button className="btn" type="button" style={{ background: internal ? "#fde68a" : "#f1f5f9", color: internal ? "#92400e" : "#475569", flex: "0 0 auto", fontWeight: internal ? 700 : 400 }} title="Прихована нотатка для менеджерів (клієнт не побачить)" onClick={() => setInternal((v) => !v)}><Icon n="eye" size={17} /></button>
        <EmojiButton onPick={(e) => setText((t) => t + e)} />
        <button className="btn" style={{ background: "#f1f5f9", flex: "0 0 auto" }} title="Надіслати фото / відео" onClick={() => fileRef.current?.click()} disabled={busy}><Icon n="paperclip" size={17} /></button>
        <button className="btn" style={{ flex: "1.8 1 0", minWidth: 0, background: "#fef3c7", color: "#92400e", fontSize: "clamp(9px, 2.7cqi, 13px)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", padding: "0 6px" }} onClick={analyze} disabled={aiLoad} title="AI-РОП підказати відповідь">{aiLoad ? "AI аналізує…" : <><Icon n="🧠" size={13} /> AI-РОП підказати відповідь</>}</button>
        <button className="btn btn-primary" style={{ flex: "1 1 0", minWidth: 0, fontSize: "clamp(9px, 2.7cqi, 13px)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", padding: "0 6px", background: internal ? "#d4a017" : undefined }} onClick={send} disabled={busy || !text.trim()}>{busy ? "…" : (internal ? <><Icon n="📝" size={13} /> Нотатка</> : "Надіслати")}</button>
      </div>
    </div>
  );
}
