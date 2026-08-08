/* Вбудований чат з клієнтом + AI-РОП. Стрічка повідомлень і поле відповіді —
 * обидва з регульованою висотою (тягни за правий нижній кут). AI-РОП показує
 * тези діалогу + рекомендовану відповідь прямо тут. */
import { Fragment, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { EmojiButton } from "./ChatCompose";
import { AiComposeAssist } from "./AiComposeAssist";
import { Icon } from "./Icon";
import { api, ChatMessage, Conversation, Paginated } from "./api";
import ChatActions from "./ChatActions";
import { dayLabel, timeLabel, isNewDay, linkify, metaWindow } from "./chatUtils";

const tt = (_r: string, ua: string) => ua;  // ClientChat україномовний
const CH_META: Record<string, { i: string; l: string }> = {
  instagram: { i: "📸", l: "Instagram" }, telegram: { i: "✈️", l: "Telegram" }, echat_telegram: { i: "✈️", l: "Telegram" },
  facebook: { i: "📘", l: "Facebook" }, echat: { i: "🟣", l: "Viber" }, viber: { i: "🟣", l: "Viber" },
  echat_whatsapp: { i: "🟢", l: "WhatsApp" }, whatsapp: { i: "🟢", l: "WhatsApp" }, web: { i: "🌐", l: "Web" }, tiktok: { i: "🎵", l: "TikTok" },
};
type ReplyChannel = { channel_id: number; channel_kind: string; channel_name: string; number?: string; conversation_id?: number | null; selected?: boolean };
type StartConversationResult = { conversation: Conversation; message: ChatMessage };

export default function ClientChat({ contact, markSeen = true, channelPickerTargetId }: { contact?: number | null; markSeen?: boolean; channelPickerTargetId?: string }) {
  const [conv, setConv] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [internal, setInternal] = useState(false);
  const [pending, setPending] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [ai, setAi] = useState<{ context?: string; points?: string[]; suggestion?: string } | null>(null);
  const [aiLoad, setAiLoad] = useState(false);
  const [err, setErr] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [replyChannels, setReplyChannels] = useState<ReplyChannel[]>([]);
  const [switchingChannel, setSwitchingChannel] = useState(false);
  const [channelPickerTarget, setChannelPickerTarget] = useState<HTMLElement | null>(null);
  const [startChannels, setStartChannels] = useState<ReplyChannel[]>([]);
  const [startChannelId, setStartChannelId] = useState(0);
  const [firstText, setFirstText] = useState("");
  const [starting, setStarting] = useState(false);
  const [allConvs, setAllConvs] = useState<Conversation[]>([]);
  const [cinfo, setCinfo] = useState<any>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function loadConv() {
    if (!contact) { setLoaded(true); return; }
    try {
      const r = await api.get<Paginated<Conversation>>(`/api/conversations/by_contact/?contact=${contact}`);
      const rows = ((r as any).results || (r as any) || []) as Conversation[];
      setAllConvs(rows);
      const c = rows.find((row) => row.status === "open") || null;
      setConv(c);
      if (c) { setStartChannels([]); loadMsgs(c.id); }
      else await loadStartChannels();
    } catch { /* ignore */ }
    setLoaded(true);
  }
  async function loadStartChannels() {
    if (!contact) return;
    try {
      const lines = await api.get<ReplyChannel[]>(`/api/conversations/start_channels/?contact=${contact}`);
      setStartChannels(lines);
      setStartChannelId((current) => lines.some((line) => line.channel_id === current)
        ? current : (lines[0]?.channel_id || 0));
    } catch { setStartChannels([]); setStartChannelId(0); }
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
  async function switchConv(c: Conversation) {
    if (!c || c.id === conv?.id) return;
    setConv(c); setMsgs([]); setAi(null); setErr("");
    await Promise.all([loadMsgs(c.id), loadReplyChannels(c.id)]);
  }
  async function loadContactInfo() {
    if (!contact) { setCinfo(null); return; }
    try { setCinfo(await api.get<any>(`/api/contacts/${contact}/`)); } catch { setCinfo(null); }
  }
  useEffect(() => {
    setLoaded(false); setConv(null); setMsgs([]); setFirstText(""); setErr(""); setAllConvs([]); setCinfo(null);
    loadConv(); loadContactInfo();
    /* eslint-disable-next-line */
  }, [contact]);
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
    if (!conv || (!text.trim() && pending.length === 0)) return;
    setBusy(true); setErr("");
    try {
      for (const att of pending) {
        const m = await api.post<ChatMessage>(`/api/conversations/${conv.id}/send_media/`, { content_b64: att.dataURL, filename: att.name, kind: att.kind, internal });
        setMsgs((p) => [...p, m]);
      }
      setPending([]);
      if (text.trim()) {
        const m = await api.post<ChatMessage>(`/api/conversations/${conv.id}/send/`, { text, internal });
        setMsgs((p) => [...p, m]); setText("");
      }
    } catch (e: any) { setErr(e?.response?.data?.detail || "Не вдалося надіслати — чат має бути відкритий оператором"); }
    setBusy(false);
  }
  async function startConversation() {
    if (!contact || !startChannelId || !firstText.trim()) return;
    setStarting(true); setErr("");
    try {
      const result = await api.post<StartConversationResult>("/api/conversations/start_channel/", {
        contact_id: contact, channel_id: startChannelId, text: firstText,
      });
      setConv(result.conversation); setMsgs([result.message]); setFirstText(""); setStartChannels([]);
      await loadReplyChannels(result.conversation.id);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Не вдалося створити чат і надіслати повідомлення");
    }
    setStarting(false);
  }
  // ── Надіслати фото/відео клієнту ──
  function onPasteFile(e: any) {
    const items = e.clipboardData?.items || [];
    for (let i = 0; i < items.length; i++) { const it = items[i]; if (it.type && it.type.startsWith("image")) { const f = it.getAsFile(); if (f) { e.preventDefault(); stageFile(f); return; } } }
  }
  function stageFile(f: File | null | undefined) {
    if (!f) return;
    const kind = f.type.startsWith("video") ? "video" : f.type.startsWith("image") ? "photo" : "document";
    const reader = new FileReader();
    reader.onload = () => setPending((p) => [...p, { dataURL: reader.result as string, name: f.name, kind }]);
    reader.readAsDataURL(f);
  }
  async function sendFile(e: any) { stageFile(e.target.files?.[0]); e.target.value = ""; }
  async function analyze() {
    if (!conv) return;
    setAiLoad(true); setErr("");
    try { setAi(await api.post<any>(`/api/conversations/${conv.id}/ai_reply/`, {})); }
    catch { setErr("AI-РОП тимчасово недоступний"); }
    setAiLoad(false);
  }

  if (!loaded) return <div className="muted" style={{ fontSize: 13 }}>Завантаження чату…</div>;
  if (!contact) return <div className="muted" style={{ fontSize: 13 }}>Немає привʼязаного клієнта</div>;
  const clientHead = (cinfo || allConvs.length > 0) ? (
    <div style={{ marginBottom: 7 }}>
      {cinfo && (cinfo.nickname || cinfo.social_link || cinfo.display_name) && (
        <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12.5, flexWrap: "wrap", marginBottom: allConvs.length ? 5 : 0 }}>
          <b style={{ color: "#334155" }}>{cinfo.display_name || `${cinfo.first_name || ""} ${cinfo.last_name || ""}`.trim() || "Клієнт"}</b>
          {cinfo.nickname && <span style={{ color: "#7c3aed", fontWeight: 600 }}>{String(cinfo.nickname).startsWith("@") ? cinfo.nickname : "@" + cinfo.nickname}</span>}
          {cinfo.social_link && <a href={cinfo.social_link} target="_blank" rel="noreferrer" style={{ color: "#2563eb", fontSize: 11.5, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 3 }}><Icon n="link" size={12} /> профіль</a>}
        </div>
      )}
      {allConvs.length > 0 && (
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
          {allConvs.map((c) => { const meta = CH_META[(c as any).channel_kind] || { i: "💬", l: (c as any).channel_name || "Чат" }; const on = conv?.id === c.id; return (
            <button key={c.id} type="button" onClick={() => switchConv(c)} title={"Відкрити чат: " + ((c as any).channel_name || meta.l)}
              style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 600, padding: "3px 9px", borderRadius: 20, cursor: "pointer", whiteSpace: "nowrap",
                border: "1px solid " + (on ? "#7c3aed" : "#e2e8f0"), background: on ? "#f5f3ff" : "#fff", color: on ? "#6d28d9" : "#475569", opacity: (c as any).status === "open" ? 1 : 0.62 }}>
              <span>{meta.i}</span> {meta.l}
            </button>
          ); })}
        </div>
      )}
    </div>
  ) : null;
  if (!conv) {
    const startPicker = startChannels.length ? (
      <div data-testid="reply-channel-picker" style={{ display: "flex", alignItems: "center", gap: 7, width: "100%" }}>
        <span style={{ fontSize: 10.5, color: "#64748b", fontWeight: 700, whiteSpace: "nowrap" }}>Відповідати через</span>
        <select value={startChannelId} onChange={(e) => setStartChannelId(Number(e.target.value))} disabled={starting}
          title="Оберіть Viber або Telegram і номер, з якого CRM напише клієнту"
          style={{ minWidth: 0, flex: 1, height: 30, border: "1px solid #cbd5e1", borderRadius: 7, background: "#fff", color: "#334155", padding: "0 7px", fontSize: 11.5, fontWeight: 600 }}>
          {startChannels.map((line) => (
            <option key={line.channel_id} value={line.channel_id}>
              {line.channel_name}{line.number && !line.channel_name.includes(line.number) ? ` · ${line.number}` : ""}
            </option>
          ))}
        </select>
      </div>
    ) : null;
    return (
      <div style={{ display: "flex", flexDirection: "column", minHeight: 180 }}>
        {clientHead}
        {channelPickerTargetId ? (channelPickerTarget && startPicker ? createPortal(startPicker, channelPickerTarget) : null) : startPicker}
        <div style={{ flex: 1, minHeight: 92, padding: 12, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#334155", marginBottom: 5 }}>Почати чат з клієнтом</div>
          <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.4 }}>
            Перше повідомлення буде надіслано на номер із картки клієнта. Після відправки чат створиться автоматично.
          </div>
        </div>
        {startChannels.length ? (
          <>
            <textarea value={firstText} onChange={(e) => setFirstText(e.target.value)} rows={3}
              placeholder="Напишіть перше повідомлення клієнту…"
              style={{ width: "100%", fontSize: 13, padding: 9, borderRadius: 10, border: "1px solid #e2e8f0", background: "#fff", marginTop: 8, boxSizing: "border-box", resize: "vertical", minHeight: 70 }} />
            <div style={{ display: "flex", gap: 6, marginTop: 6, alignSelf: "flex-end", alignItems: "center" }}>
              <AiComposeAssist draft={firstText} contactId={contact} onApply={setFirstText} />
              <button className="btn btn-primary" onClick={startConversation}
                disabled={starting || !startChannelId || !firstText.trim()} style={{ minWidth: 130 }}>
                {starting ? "Надсилаємо…" : "Надіслати"}
              </button>
            </div>
          </>
        ) : (
          <div style={{ color: "#b45309", fontSize: 12, marginTop: 8 }}>
            Додайте коректний номер у картку клієнта та перевірте підключення Viber/Telegram у Контакт-центрі.
          </div>
        )}
        {err && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 6 }}>{err}</div>}
      </div>
    );
  }

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
    <div style={{ display: "flex", flexDirection: "column", containerType: "inline-size", height: "auto" }}>
      {clientHead}
      {channelPickerTargetId ? (channelPickerTarget ? createPortal(channelPicker, channelPickerTarget) : null) : channelPicker}
      <ChatActions convId={conv.id} onClosed={() => { setConv(null); setMsgs([]); loadStartChannels(); }} onChanged={(c) => setConv(c)} />
      {/* СТРІЧКА — заповнює доступну висоту */}
      <div title="Тягни за правий нижній кут, щоб збільшити вікно чату" style={{ height: 300, minHeight: 150, maxHeight: "72vh", resize: "vertical", overflow: "auto", display: "flex", flexDirection: "column", gap: 6, padding: 10, background: "#f8fafc", borderRadius: 10, border: "1px solid #eef2f7" }}>
        {msgs.length === 0 && <div className="muted" style={{ fontSize: 13 }}>Повідомлень поки немає</div>}
        {msgs.map((m, i) => (
          <Fragment key={m.id}>
            {isNewDay((m as any).created_at, (msgs[i - 1] as any)?.created_at) && (
              <div style={{ position: "sticky", top: 2, zIndex: 3, textAlign: "center", margin: "6px 0 4px", pointerEvents: "none" }}><span style={{ fontSize: 11, fontWeight: 700, color: "#475569", background: "#e2e8f0", borderRadius: 20, padding: "3px 13px", boxShadow: "0 1px 4px rgba(0,0,0,.14)" }}>{dayLabel((m as any).created_at, tt)}</span></div>
            )}
            <div style={{ alignSelf: m.direction === "in" ? "flex-start" : "flex-end", maxWidth: "82%" }}>
              <div style={{ fontSize: 10.5, color: "#94a3b8", marginBottom: 2, textAlign: m.direction === "in" ? "left" : "right" }}>
                {m.direction === "in" ? "Клієнт" : ((m as any).sender_display || (m.sender_name === "ai_assistant" ? "Юля (AI)" : (m.sender_name || "Менеджер")))}
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
      {pending.length > 0 && <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
        {pending.map((att: any, i: number) => (
          <div key={i} style={{ position: "relative", border: internal ? "1.5px dashed #d4a017" : "1px solid #e2e8f0", borderRadius: 8, background: internal ? "#fffbeb" : "#f8fafc", padding: att.kind === "photo" ? 0 : "8px 12px", display: "flex", alignItems: "center", gap: 6 }}>
            {att.kind === "photo" ? <img src={att.dataURL} alt="" style={{ height: 54, maxWidth: 90, borderRadius: 8, objectFit: "cover", display: "block" }} /> : <span style={{ fontSize: 12, color: "#475569", display: "inline-flex", alignItems: "center", gap: 5 }}><Icon n="paperclip" size={15} /> {String(att.name).slice(0, 24)}</span>}
            <button type="button" onClick={() => setPending((p: any[]) => p.filter((_: any, j: number) => j !== i))} title="Прибрати" style={{ position: "absolute", top: -7, right: -7, width: 18, height: 18, borderRadius: "50%", background: "#dc2626", color: "#fff", border: "none", cursor: "pointer", fontSize: 11, lineHeight: "16px", padding: 0 }}>✕</button>
          </div>
        ))}
      </div>}
      {internal && pending.length > 0 && <div style={{ fontSize: 11, color: "#92400e", marginTop: 4 }}><Icon n="📝" size={12} /> Файл піде у ВНУТРІШНЮ нотатку — клієнт НЕ побачить</div>}
      <textarea value={text} onChange={(e) => setText(e.target.value)} onPaste={onPasteFile} placeholder={internal ? "Внутрішня нотатка — клієнт НЕ побачить…  (вставити фото — Ctrl+V)" : "Відповідь клієнту…  (вставити фото — Ctrl+V)"} rows={3}
        style={{ width: "100%", fontSize: 13, padding: 9, borderRadius: 10, border: internal ? "1.5px dashed #d4a017" : "1px solid #e2e8f0", background: internal ? "#fffbeb" : "#fff", marginTop: 8, boxSizing: "border-box", resize: "vertical", minHeight: 56, flexShrink: 0 }} />
      <input ref={fileRef} type="file" hidden onChange={sendFile} />
      <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
        <button className="btn" type="button" style={{ background: internal ? "#fde68a" : "#f1f5f9", color: internal ? "#92400e" : "#475569", flex: "0 0 auto", fontWeight: internal ? 700 : 400 }} title="Прихована нотатка для менеджерів (клієнт не побачить)" onClick={() => setInternal((v) => !v)}><Icon n="eye" size={17} /></button>
        <EmojiButton onPick={(e) => setText((t) => t + e)} />
        <button className="btn" style={{ background: "#f1f5f9", flex: "0 0 auto" }} title="Надіслати фото / відео" onClick={() => fileRef.current?.click()} disabled={busy}><Icon n="paperclip" size={17} /></button>
        <AiComposeAssist draft={text} convId={conv.id} onApply={setText} compact />
        <button className="btn" style={{ flex: "1 1 150px", minWidth: 0, background: "#fef3c7", color: "#92400e", fontSize: "clamp(10px, 3cqi, 13px)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", padding: "6px 6px", minHeight: 34 }} onClick={analyze} disabled={aiLoad} title="AI-РОП підказати відповідь">{aiLoad ? "AI аналізує…" : <><Icon n="🧠" size={13} /> AI-РОП підказати відповідь</>}</button>
        <button className="btn btn-primary" style={{ flex: "1 1 120px", minWidth: 0, fontSize: "clamp(10px, 3cqi, 13px)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", padding: "6px 6px", minHeight: 34, background: internal ? "#d4a017" : undefined }} onClick={send} disabled={busy || (!text.trim() && pending.length === 0)}>{busy ? "…" : (internal ? <><Icon n="📝" size={13} /> Нотатка</> : "Надіслати")}</button>
      </div>
    </div>
  );
}
