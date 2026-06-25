import { useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api, ChatMessage, Conversation, Paginated } from "../api";
import { Avatar, SourceChip } from "../ui";
import { useAuth } from "../auth";
import { useLang } from "../i18n";

function linkify(text: string, out: boolean) {
  return String(text || "").split(/(https?:\/\/[^\s]+)/g).map((p, i) =>
    /^https?:\/\//.test(p)
      ? <a key={i} href={p} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} style={{ color: "#1d4ed8", textDecoration: "underline", wordBreak: "break-all" }}>{p}</a>
      : <span key={i}>{p}</span>);
}


export default function Inbox() {
  const { can } = useAuth();
  const { t } = useLang();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [scope, setScope] = useState<"mine" | "all" | "unassigned">("all");
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const [ai, setAi] = useState<{ context?: string; points?: string[]; suggestion?: string } | null>(null);
  const [aiLoad, setAiLoad] = useState(false);
  const [nextUrl, setNextUrl] = useState<string | null>(null);
  const [picker, setPicker] = useState<null | "transfer" | "add">(null);
  const [emps, setEmps] = useState<{ id: number; full_name: string }[]>([]);
  const endRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<Conversation | null>(null);

  async function loadConvs() {
    const q = scope && scope !== "all" ? `?scope=${scope}&page_size=50` : "?page_size=50";
    const d = await api.get<Paginated<Conversation>>(`/api/conversations/${q}`);
    setConvs(d.results); setNextUrl((d as any).next || null);
    if (!activeRef.current && d.results[0]) openConv(d.results[0]);
  }
  async function loadMore() {
    if (!nextUrl) return;
    const url = nextUrl.replace(/^https?:\/\/[^/]+/, "");
    const d = await api.get<Paginated<Conversation>>(url);
    setConvs((cs) => { const ids = new Set(cs.map((x) => x.id)); return [...cs, ...d.results.filter((r) => !ids.has(r.id))]; });
    setNextUrl((d as any).next || null);
  }
  async function refreshList() {
    const q = scope && scope !== "all" ? `?scope=${scope}&page_size=50` : "?page_size=50";
    const d = await api.get<Paginated<Conversation>>(`/api/conversations/${q}`);
    setConvs((cs) => {
      const map = new Map<number, Conversation>(cs.map((c) => [c.id, c]));
      d.results.forEach((r) => map.set(r.id, { ...(map.get(r.id) as any), ...r }));
      return Array.from(map.values()).sort((a, b) => String(b.last_message_at || "").localeCompare(String(a.last_message_at || "")));
    });
  }
  useEffect(() => { loadConvs(); }, [scope]);
  // live-оновлення відкритого чату (без ручного refresh)
  useEffect(() => {
    if (!active) return;
    const t = setInterval(async () => {
      try {
        const m = await api.get<ChatMessage[]>(`/api/conversations/${active.id}/messages/`);
        setMsgs((prev) => (m.length !== prev.length ? m : prev));
      } catch { /* ignore */ }
    }, 6000);
    return () => clearInterval(t);
  }, [active]);
  // періодичне оновлення списку чатів
  useEffect(() => {
    const t = setInterval(() => refreshList(), 20000);
    return () => clearInterval(t);
  }, [scope]);
  useEffect(() => {
    const contactId = params.get("contact");
    if (contactId) {
      api.get<any>(`/api/conversations/?contact=${contactId}`).then((r) => {
        const conv = ((r as any).results || [])[0];
        if (conv) { setConvs((cs) => cs.some((x) => x.id === conv.id) ? cs : [conv, ...cs]); openConv(conv); }
        else setErr(t("Переписки с этим клиентом ещё нет","Переписки з цим клієнтом ще немає"));
      }).catch(() => {});
      return;
    }
    const cid = params.get("c");
    if (!cid) return;
    api.get<Conversation>(`/api/conversations/${cid}/`).then((c) => { setConvs((cs) => cs.some((x) => x.id === c.id) ? cs : [c, ...cs]); openConv(c); }).catch(() => {});
  }, [params]);
  useEffect(() => { activeRef.current = active; }, [active]);
  useEffect(() => { api.get<any>("/api/users/?page_size=500").then((d) => setEmps(((d.results || d) as any[]).filter((u) => u.is_active).map((u) => ({ id: u.id, full_name: u.full_name || u.username })))).catch(() => {}); }, []);
  useEffect(() => { endRef.current?.scrollIntoView(); }, [msgs]);

  async function analyzeAI(id: number) {
    setAiLoad(true);
    try { setAi(await api.post<any>(`/api/conversations/${id}/ai_reply/`, {})); }
    catch { setAi(null); }
    setAiLoad(false);
  }

  async function openConv(c: Conversation) {
    setActive(c); setErr(""); setAi(null);
    const m = await api.get<ChatMessage[]>(`/api/conversations/${c.id}/messages/`);
    setMsgs(m);
    setConvs((cs) => cs.map((x) => (x.id === c.id ? { ...x, unread: 0 } : x)));
  }

  async function goToCard() {
    if (!active?.contact) return;
    try {
      const dl = await api.get<any>(`/api/deals/?contact=${active.contact}`);
      const deal = ((dl as any).results || [])[0];
      if (deal) { nav(`/deals/${deal.id}`); return; }
      const ld = await api.get<any>(`/api/leads/?contact=${active.contact}`);
      const lead = ((ld as any).results || [])[0];
      if (lead) nav(`/leads/${lead.id}`); else setErr(t("Карточка не найдена","Картку не знайдено"));
    } catch { setErr(t("Не удалось открыть карточку","Не вдалося відкрити картку")); }
  }

  async function send() {
    if (!active || !text.trim()) return;
    setSending(true); setErr("");
    try {
      const m = await api.post<ChatMessage>(`/api/conversations/${active.id}/send/`, { text });
      setMsgs((ms) => [...ms, m]);
      setText("");
    } catch (e: any) {
      setErr(t("Не удалось отправить (проверь токен бота / сеть).","Не вдалося відправити (перевір токен бота / мережу)."));
    } finally { setSending(false); }
  }

  async function pickUser(uid: number) {
    if (!active) return;
    const ep = picker === "transfer" ? "assign" : "add_member";
    try {
      const c = await api.post<Conversation>(`/api/conversations/${active.id}/${ep}/`, { user_id: uid });
      setActive(c);
      setConvs((cs) => cs.map((x) => (x.id === c.id ? { ...x, ...c } : x)));
    } catch { setErr(t("Не удалось","Не вдалося")); }
    setPicker(null);
  }

  return (
    <div className="inbox fade" style={{ height: "100%", display: "grid", gridTemplateColumns: "300px 1fr 340px" }}>
      {/* список диалогов */}
      <div style={{ background: "#fff", borderRight: "1px solid #e2e8f0", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: 12, borderBottom: "1px solid #e2e8f0", fontWeight: 600 }}>{t("Диалоги","Діалоги")}</div>
        <div style={{ display: "flex", gap: 6, padding: "8px 12px", borderBottom: "1px solid #f1f5f9" }}>
          {(([["mine", t("Мои","Мої")]].concat(can("conversation.view.all") ? [["all", t("Все","Всі")], ["unassigned", t("Не назначены","Не призначені")]] : [])) as [string, string][]).map(([k, label]) => (
            <button key={k} onClick={() => setScope(k as any)}
              style={{ fontSize: 12, padding: "4px 10px", borderRadius: 14, cursor: "pointer",
                border: "1px solid " + (scope === k ? "var(--brand)" : "#e2e8f0"),
                background: scope === k ? "var(--brand)" : "#fff", color: scope === k ? "#fff" : "#475569" }}>{label}</button>
          ))}
        </div>
        <div style={{ flex: 1, overflowY: "auto" }} onScroll={(e) => { const el = e.currentTarget; if (el.scrollHeight - el.scrollTop - el.clientHeight < 140) loadMore(); }}>
          {convs.length === 0 && <div className="spin">{t("Пока нет диалогов.","Поки немає діалогів.")}</div>}
          {(() => {
            const fmtAt = (d?: string) => d ? new Date(d).toLocaleString("uk", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
            const card = (c: Conversation) => (
              <div key={c.id} onClick={() => openConv(c)}
                style={{ padding: "10px 12px", borderBottom: "1px solid #f1f5f9", cursor: "pointer",
                  display: "flex", gap: 9, background: active?.id === c.id ? "#eff6ff" : "" }}>
                <Avatar name={c.contact_name || c.title || "?"} cls="av-md" />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.contact_name || c.title || t("Без имени","Без імені")}</span>
                    <span style={{ fontSize: 10, color: "#94a3b8", whiteSpace: "nowrap" }}>{fmtAt((c as any).last_message_at)}</span>
                  </div>
                  <div className="muted" style={{ fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.last_text}</div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: c.assigned_to ? "#2563eb" : "#94a3b8" }}>{c.assigned_to ? "👤 " + c.assigned_to_name : t("Не назначено","Не призначено")}</span>
                    <SourceChip source={c.channel_kind} />
                  </div>
                </div>
                {c.unread > 0 && <span style={{ width: 16, height: 16, borderRadius: "50%", background: "#ef4444", color: "#fff", fontSize: 10, display: "flex", alignItems: "center", justifyContent: "center", alignSelf: "center" }}>{c.unread}</span>}
              </div>
            );
            const need = convs.filter((c) => (c as any).needs_reply);
            const work = convs.filter((c) => !(c as any).needs_reply);
            const hdr = (t: string, color: string) => <div style={{ padding: "8px 12px 4px", fontSize: 11, fontWeight: 700, color, textTransform: "uppercase", letterSpacing: .3 }}>{t}</div>;
            return (<>
              {need.length > 0 && hdr(t(`🔴 Нужен ответ (${need.length})`,`🔴 Потрібна відповідь (${need.length})`), "#dc2626")}
              {need.map(card)}
              {work.length > 0 && hdr(t(`✅ В работе (${work.length})`,`✅ В роботі (${work.length})`), "#16a34a")}
              {work.map(card)}
            </>);
          })()}
          {nextUrl && <div onClick={() => loadMore()} style={{ padding: "10px 12px", textAlign: "center", fontSize: 12, color: "var(--brand)", cursor: "pointer", borderTop: "1px solid #f1f5f9" }}>{t("Загрузить ещё ↓","Завантажити ще ↓")}</div>}
        </div>
      </div>

      {/* переписка */}
      <div style={{ display: "flex", flexDirection: "column", background: "#f8fafc", overflow: "hidden" }}>
        {!active ? (
          <div className="spin">{t("Выбери диалог слева","Обери діалог зліва")}</div>
        ) : (
          <>
            <div style={{ height: 52, background: "#fff", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 8, padding: "0 16px" }}>
              <Avatar name={active.contact_name || active.title || "?"} cls="av-md" />
              <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.25 }}>
                <b style={{ fontSize: 14 }}>{active.contact_name || active.title}</b>
                <span className="muted" style={{ fontSize: 11 }}>{active.assigned_to ? "👤 " + active.assigned_to_name : t("Не назначено","Не призначено")}{(active as any).participant_names && (active as any).participant_names.length > 0 ? " · 👥 " + (active as any).participant_names.join(", ") : ""} · {active.channel_name}</span>
              </div>
              <SourceChip source={active.channel_kind} />
              <div className="spacer" />
              <button className="btn btn-green">{t("📞 Позвонить","📞 Подзвонити")}</button>
              {active.contact && <button className="btn btn-primary" style={{ marginLeft: 8 }} onClick={goToCard}>{t("🤝 В карточку","🤝 В картку")}</button>}
              <button className="btn" style={{ marginLeft: 8, background: "#fff7ed", color: "#c2410c", fontWeight: 600 }} onClick={() => setPicker(picker === "transfer" ? null : "transfer")}>{t("↪ Переадресовать","↪ Переадресувати")}</button>
              <button className="btn" style={{ marginLeft: 8, background: "#eef2ff", color: "#4338ca", fontWeight: 600 }} onClick={() => setPicker(picker === "add" ? null : "add")}>{t("➕ Менеджер","➕ Менеджер")}</button>
            </div>
            {picker && (<>
              <div onClick={() => setPicker(null)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
              <div style={{ position: "fixed", top: 104, right: 360, width: 300, maxHeight: 420, overflowY: "auto", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 14px 36px rgba(0,0,0,.18)", zIndex: 41 }}>
                <div style={{ padding: "9px 12px", fontSize: 12.5, fontWeight: 700, color: "#475569", borderBottom: "1px solid #f1f5f9", position: "sticky", top: 0, background: "#fff" }}>{picker === "transfer" ? t("Переадресовать чат на:","Переадресувати чат на:") : t("Добавить менеджера в чат:","Додати менеджера у чат:")}</div>
                {emps.map((e) => (
                  <div key={e.id} onClick={() => pickUser(e.id)} style={{ padding: "8px 12px", cursor: "pointer", fontSize: 13, display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid #f8fafc" }}>
                    <Avatar name={e.full_name} cls="av-md" />{e.full_name}
                  </div>
                ))}
                {emps.length === 0 && <div className="muted" style={{ padding: 12, fontSize: 12 }}>{t("Нет сотрудников","Немає співробітників")}</div>}
              </div>
            </>)}
            <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
              {msgs.map((m) => (
                <div key={m.id} className={"msg" + (m.direction === "out" ? " msg-out" : " msg-in")}
                  style={{ maxWidth: "70%", padding: "9px 11px", borderRadius: 10, fontSize: 13,
                    alignSelf: m.direction === "out" ? "flex-end" : "flex-start",
                    background: "#fff",
                    color: "#0f172a",
                    border: m.direction === "out" ? "1.5px solid #2563eb" : "1px solid #e8edf3",
                    boxShadow: "0 1px 2px rgba(0,0,0,.05)" }}>
                  <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: .2, marginBottom: 4, paddingBottom: 3, borderBottom: m.direction === "out" ? "1px solid rgba(37,99,235,.25)" : "1px solid rgba(0,0,0,.08)", color: m.direction === "out" ? "#2563eb" : "var(--brand)" }}>
                    {m.sender_name || (m.direction === "out" ? t("Менеджер","Менеджер") : (active?.title || t("Клиент","Клієнт")))}
                  </div>
                  <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{linkify(m.text, m.direction === "out")}</span>
                  {m.attachments?.map((a, i) => (
                    <div key={i} style={{ fontSize: 11, opacity: .8, marginTop: 4 }}>
                      📎 {a.type === "voice" ? t(`голосовое ${a.duration ?? ""}с`,`голосове ${a.duration ?? ""}с`) : a.type}
                    </div>
                  ))}
                  <div style={{ fontSize: 10, opacity: .55, marginTop: 3, textAlign: m.direction === "out" ? "right" : "left" }}>{(m as any).created_at ? new Date((m as any).created_at).toLocaleTimeString("uk", { hour: "2-digit", minute: "2-digit" }) : ""}</div>
                </div>
              ))}
              <div ref={endRef} />
            </div>
            {err && <div className="err" style={{ padding: "0 16px" }}>{err}</div>}
            <div style={{ background: "#fff", borderTop: "1px solid #e2e8f0", padding: 12, display: "flex", gap: 8 }}>
              <input value={text} onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send()}
                placeholder={t(`Сообщение уйдёт в ${active.channel_name}…`,`Повідомлення піде в ${active.channel_name}…`)}
                style={{ flex: 1, height: 36, background: "#f1f5f9", border: "none", borderRadius: 7, padding: "0 12px", fontSize: 13, outline: "none" }} />
              <button className="btn btn-primary" onClick={send} disabled={sending}>{sending ? "…" : t("Отправить","Відправити")}</button>
            </div>
          </>
        )}
      </div>

      {/* AI-РОП панель */}
      <div style={{ background: "#fff", borderLeft: "1px solid #e2e8f0", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "14px 14px 12px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center" }}>
          <b style={{ fontSize: 14 }}>🧠 AI-РОП</b>
          <div style={{ flex: 1 }} />
          {active && <button className="btn" style={{ fontSize: 12, padding: "3px 10px" }} onClick={() => analyzeAI(active.id)} disabled={aiLoad}>{aiLoad ? "…" : t("🔄 Обновить","🔄 Оновити")}</button>}
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 14 }}>
          {!active ? (
            <div className="muted" style={{ fontSize: 13 }}>{t("Выбери диалог — AI-РОП подскажет тезисы и ответ.","Обери діалог — AI-РОП підкаже тези й відповідь.")}</div>
          ) : aiLoad && !ai ? (
            <div className="muted" style={{ fontSize: 13 }}>{t("AI-РОП анализирует диалог…","AI-РОП аналізує діалог…")}</div>
          ) : ai ? (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 8 }}>{t("Что в диалоге","Що в діалозі")}</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.5 }}>
                {(ai.points && ai.points.length ? ai.points : (ai.context ? [ai.context] : [])).map((p, i) => <li key={i} style={{ marginBottom: 5 }}>{p}</li>)}
              </ul>
              {ai.suggestion && (
                <>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", margin: "16px 0 8px" }}>{t("Предлагаемый ответ","Пропонована відповідь")}</div>
                  <div style={{ fontSize: 13, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 10, padding: 10, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{ai.suggestion}</div>
                  <button className="btn btn-primary" style={{ width: "100%", marginTop: 8 }} onClick={() => setText(ai.suggestion || "")}>{t("✍️ Вставить в ответ","✍️ Вставити у відповідь")}</button>
                </>
              )}
            </>
          ) : (
            <div style={{ textAlign: "center", paddingTop: 24 }}>
              <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>{t("AI-РОП подскажет тезисы диалога + готовый ответ.","AI-РОП підкаже тези діалогу + готову відповідь.")}</div>
              <button className="btn btn-primary" onClick={() => active && analyzeAI(active.id)} disabled={aiLoad}>{aiLoad ? t("Анализирую…","Аналізую…") : t("🧠 Проанализировать диалог","🧠 Проаналізувати діалог")}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
