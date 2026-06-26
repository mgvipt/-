import { useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api, ChatMessage, Conversation, Paginated } from "../api";
import { Avatar, SourceChip } from "../ui";
import { useAuth } from "../auth";
import { useLang } from "../i18n";
import { EmojiButton } from "../ChatCompose";
import { Icon } from "../Icon";

function linkify(text: string, out: boolean) {
  return String(text || "").split(/(https?:\/\/[^\s]+)/g).map((p, i) =>
    /^https?:\/\//.test(p)
      ? <a key={i} href={p} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} style={{ color: "#1d4ed8", textDecoration: "underline", wordBreak: "break-all" }}>{p}</a>
      : <span key={i}>{p}</span>);
}


export default function Inbox() {
  const { can, me } = useAuth();
  const { t } = useLang();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [scope, setScope] = useState<"mine" | "all" | "unassigned">("all");
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [internalNote, setInternalNote] = useState(false);
  const [composerH, setComposerH] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  function startResizeComposer(e: any) {
    e.preventDefault();
    const startY = e.clientY; const startH = composerH ?? 38;
    function mv(ev: MouseEvent) { setComposerH(Math.min(420, Math.max(38, startH - (ev.clientY - startY)))); }
    function up() { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); }
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }
  const [err, setErr] = useState("");
  const [ai, setAi] = useState<{ context?: string; points?: string[]; suggestion?: string } | null>(null);
  const [aiLoad, setAiLoad] = useState(false);
  const [nextUrl, setNextUrl] = useState<string | null>(null);
  const [picker, setPicker] = useState<null | "transfer" | "add">(null);
  const [emps, setEmps] = useState<{ id: number; full_name: string }[]>([]);
  const [menu, setMenu] = useState(false);
  const [search, setSearch] = useState("");
  const [channels, setChannels] = useState<{ id: number; name: string }[]>([]);
  const [chFilter, setChFilter] = useState("");
  const [period, setPeriod] = useState("all");
  const [selMode, setSelMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const endRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<Conversation | null>(null);

  function listQuery() {
    const sp = new URLSearchParams({ page_size: "50" });
    if (scope && scope !== "all") sp.set("scope", scope);
    if (chFilter) sp.set("channel", chFilter);
    if (period && period !== "all") sp.set("period", period);
    if (search.trim()) sp.set("search", search.trim());
    return "?" + sp.toString();
  }
  async function loadConvs() {
    const q = listQuery();
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
    const q = listQuery();
    const d = await api.get<Paginated<Conversation>>(`/api/conversations/${q}`);
    setConvs((cs) => {
      const map = new Map<number, Conversation>(cs.map((c) => [c.id, c]));
      d.results.forEach((r) => map.set(r.id, { ...(map.get(r.id) as any), ...r }));
      return Array.from(map.values()).sort((a, b) => String(b.last_message_at || "").localeCompare(String(a.last_message_at || "")));
    });
  }
  useEffect(() => { loadConvs(); }, [scope, chFilter, period]);
  useEffect(() => { const id = setTimeout(() => loadConvs(), 400); return () => clearTimeout(id); /* eslint-disable-next-line */ }, [search]);
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
  }, [scope, chFilter, period]);
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
  useEffect(() => { api.get<any>("/api/channels/").then((d) => setChannels(((d.results || d) as any[]).map((c) => ({ id: c.id, name: c.name })))).catch(() => {}); }, []);
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
      const m = await api.post<ChatMessage>(`/api/conversations/${active.id}/send/`, { text, internal: internalNote });
      setMsgs((ms) => [...ms, m]);
      setText("");
    } catch (e: any) {
      setErr(t("Не удалось отправить (проверь токен бота / сеть).","Не вдалося відправити (перевір токен бота / мережу)."));
    } finally { setSending(false); }
  }

  async function uploadFile(f: File | null | undefined) {
    if (!f || !active) return;
    const kind = f.type.startsWith("video") ? "video" : f.type.startsWith("image") ? "photo" : "document";
    setSending(true); setErr("");
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const m = await api.post<ChatMessage>(`/api/conversations/${active.id}/send_media/`, { content_b64: reader.result, filename: f.name, kind });
        setMsgs((ms) => [...ms, m]);
      } catch { setErr(t("Не удалось отправить файл","Не вдалося надіслати файл")); }
      finally { setSending(false); }
    };
    reader.readAsDataURL(f);
  }
  async function sendFile(e: any) { await uploadFile(e.target.files?.[0]); e.target.value = ""; }
  function onPasteFile(e: any) {
    const items = e.clipboardData?.items || [];
    for (let i = 0; i < items.length; i++) { const it = items[i]; if (it.type && it.type.startsWith("image")) { const f = it.getAsFile(); if (f) { e.preventDefault(); uploadFile(f); return; } } }
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

  function toggleSel(id: number) { setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; }); }
  function selectAllVisible() { setSelected(new Set(convs.map((c) => c.id))); }
  async function bulkClose() {
    if (selected.size === 0) return;
    try {
      await api.post<any>("/api/conversations/bulk_close/", { ids: Array.from(selected) });
      setConvs((cs) => cs.filter((x) => !selected.has(x.id)));
      if (active && selected.has(active.id)) { setActive(null); setMsgs([]); }
      setSelected(new Set()); setSelMode(false);
    } catch { setErr(t("Не удалось закрыть","Не вдалося закрити")); }
  }

  const mItem: any = { padding: "10px 14px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f8fafc" };
  async function takeConv() {
    if (!active) return;
    try { const c = await api.post<Conversation>(`/api/conversations/${active.id}/take/`, {}); setActive(c); setConvs((cs) => cs.map((x) => (x.id === c.id ? { ...x, ...c } : x))); } catch { setErr(t("Не удалось","Не вдалося")); }
    setMenu(false);
  }
  async function closeConv() {
    if (!active) return;
    try { await api.post<any>(`/api/conversations/${active.id}/close/`, {}); setConvs((cs) => cs.filter((x) => x.id !== active.id)); setActive(null); setMsgs([]); } catch { setErr(t("Не удалось","Не вдалося")); }
    setMenu(false);
  }
  function goToContact() { setMenu(false); if (active?.contact) nav(`/clients/${active.contact}`); }

  return (
    <div className="inbox fade" style={{ height: "100%", display: "grid", gridTemplateColumns: "300px 1fr 340px" }}>
      {/* список диалогов */}
      <div style={{ background: "#fff", borderRight: "1px solid #e2e8f0", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: 12, borderBottom: "1px solid #e2e8f0", fontWeight: 600 }}>{t("Диалоги","Діалоги")}</div>
        <div style={{ padding: "8px 12px", borderBottom: "1px solid #f1f5f9" }}>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("🔍 Имя, телефон, ник…","🔍 Імʼя, телефон, нік…")} style={{ width: "100%", height: 30, border: "1px solid #e2e8f0", borderRadius: 8, padding: "0 10px", fontSize: 12.5, boxSizing: "border-box" }} />
        </div>
        <div style={{ display: "flex", gap: 6, padding: "8px 12px", borderBottom: "1px solid #f1f5f9" }}>
          {(([["mine", t("Мои","Мої")]].concat(can("conversation.view.all") ? [["all", t("Все","Всі")], ["unassigned", t("Не назначены","Не призначені")]] : [])) as [string, string][]).map(([k, label]) => (
            <button key={k} onClick={() => setScope(k as any)}
              style={{ fontSize: 12, padding: "4px 10px", borderRadius: 14, cursor: "pointer",
                border: "1px solid " + (scope === k ? "var(--brand)" : "#e2e8f0"),
                background: scope === k ? "var(--brand)" : "#fff", color: scope === k ? "#fff" : "#475569" }}>{label}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 6, padding: "6px 12px", borderBottom: "1px solid #f1f5f9", alignItems: "center", flexWrap: "wrap" }}>
          <select value={chFilter} onChange={(e) => setChFilter(e.target.value)} style={{ flex: 1, minWidth: 86, height: 28, fontSize: 12, border: "1px solid #e2e8f0", borderRadius: 7, padding: "0 6px" }}>
            <option value="">{t("Все каналы","Всі канали")}</option>
            {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={period} onChange={(e) => setPeriod(e.target.value)} style={{ flex: 1, minWidth: 86, height: 28, fontSize: 12, border: "1px solid #e2e8f0", borderRadius: 7, padding: "0 6px" }}>
            <option value="all">{t("Все дни","Всі дні")}</option>
            <option value="today">{t("Сегодня","Сьогодні")}</option>
            <option value="yesterday">{t("Вчера","Вчора")}</option>
            <option value="7d">{t("7 дней","7 днів")}</option>
            <option value="30d">{t("30 дней","30 днів")}</option>
          </select>
          <button onClick={() => { setSelMode((v) => !v); setSelected(new Set()); }} title={t("Выбрать чаты для закрытия","Обрати чати для закриття")}
            style={{ height: 28, fontSize: 13, padding: "0 9px", borderRadius: 7, cursor: "pointer", border: "1px solid " + (selMode ? "var(--brand)" : "#e2e8f0"), background: selMode ? "var(--brand)" : "#fff", color: selMode ? "#fff" : "#475569" }}><Icon n="check-square" size={16} /></button>
        </div>
        {selMode && (
          <div style={{ display: "flex", gap: 8, padding: "6px 12px", borderBottom: "1px solid #f1f5f9", alignItems: "center", background: "#fff7ed" }}>
            <span style={{ fontSize: 12, color: "#9a3412" }}>{t("Выбрано","Обрано")}: {selected.size}</span>
            <button onClick={selectAllVisible} style={{ fontSize: 11.5, padding: "3px 8px", borderRadius: 6, cursor: "pointer", border: "1px solid #e2e8f0", background: "#fff" }}>{t("Все","Всі")}</button>
            <button onClick={() => setSelected(new Set())} style={{ fontSize: 11.5, padding: "3px 8px", borderRadius: 6, cursor: "pointer", border: "1px solid #e2e8f0", background: "#fff" }}>{t("Сброс","Скинути")}</button>
            <button onClick={bulkClose} disabled={selected.size === 0} style={{ marginLeft: "auto", fontSize: 12, fontWeight: 600, padding: "5px 10px", borderRadius: 7, cursor: selected.size ? "pointer" : "default", border: "none", background: selected.size ? "#dc2626" : "#fca5a5", color: "#fff" }}><Icon n="check" size={15} /> {t("Закрыть","Закрити")} ({selected.size})</button>
          </div>
        )}
        <div style={{ flex: 1, overflowY: "auto" }} onScroll={(e) => { const el = e.currentTarget; if (el.scrollHeight - el.scrollTop - el.clientHeight < 140) loadMore(); }}>
          {convs.length === 0 && <div className="spin">{t("Пока нет диалогов.","Поки немає діалогів.")}</div>}
          {(() => {
            const fmtAt = (d?: string) => d ? new Date(d).toLocaleString("uk", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
            const card = (c: Conversation) => (
              <div key={c.id} onClick={() => (selMode ? toggleSel(c.id) : openConv(c))}
                style={{ padding: "10px 12px", borderBottom: "1px solid #f1f5f9", cursor: "pointer",
                  display: "flex", gap: 9, background: selected.has(c.id) ? "#fef3c7" : (active?.id === c.id ? "#eff6ff" : "") }}>
                {selMode && <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggleSel(c.id)} onClick={(e) => e.stopPropagation()} style={{ alignSelf: "center", width: 16, height: 16, cursor: "pointer" }} />}
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
              <button className="btn btn-green"><Icon n="phone" size={15} /> {t("Позвонить","Подзвонити")}</button>
              {active.contact && <button className="btn btn-primary" style={{ marginLeft: 8 }} onClick={goToCard}><Icon n="handshake" size={15} /> {t("В карточку","В картку")}</button>}
              {active.assigned_to !== me?.id && <button className="btn" style={{ marginLeft: 8, background: "#ecfdf5", color: "#047857", fontWeight: 600 }} onClick={takeConv} title={t("Закрепить чат за собой","Закріпити чат за собою")}><Icon n="check" size={15} /> {t("Взять себе","Взяти собі")}</button>}
              <button className="btn" style={{ marginLeft: 8, background: "#fff7ed", color: "#c2410c", fontWeight: 600 }} onClick={() => setPicker(picker === "transfer" ? null : "transfer")}>{t("↪ Переадресовать","↪ Переадресувати")}</button>
              <button className="btn" style={{ marginLeft: 8, background: "#eef2ff", color: "#4338ca", fontWeight: 600 }} onClick={() => setPicker(picker === "add" ? null : "add")}><Icon n="plus" size={15} /> {t("Менеджер","Менеджер")}</button>
              <button className="btn" style={{ marginLeft: 8, background: "#f1f5f9", fontWeight: 700, fontSize: 17, lineHeight: 1, padding: "0 12px" }} onClick={() => setMenu((m) => !m)} title={t("Ещё","Ще")}>⋯</button>
            </div>
            {menu && (<>
              <div onClick={() => setMenu(false)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
              <div style={{ position: "fixed", top: 104, right: 360, width: 260, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 14px 36px rgba(0,0,0,.18)", zIndex: 41, overflow: "hidden" }}>
                <div onClick={takeConv} style={mItem}><Icon n="pin" size={15} /> {t("Закрепить за мной","Закріпити за мною")}</div>
                {active.contact && <div onClick={goToContact} style={mItem}><Icon n="user" size={15} /> {t("Перейти в контакт","Перейти в контакт")}</div>}
                {active.contact && <div onClick={() => { setMenu(false); goToCard(); }} style={mItem}><Icon n="handshake" size={15} /> {t("Перейти в сделку","Перейти в угоду")}</div>}
                <div onClick={closeConv} style={{ ...mItem, color: "#dc2626", borderTop: "1px solid #f1f5f9", fontWeight: 600 }}><Icon n="check" size={15} /> {t("Завершить диалог","Завершити діалог")}</div>
              </div>
            </>)}
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
                <div key={m.id} className={"msg" + (m.direction === "out" ? " msg-out" : " msg-in")} data-internal={(m as any).internal ? "1" : ""}
                  style={{ maxWidth: "70%", padding: "9px 11px", borderRadius: 10, fontSize: 13,
                    alignSelf: m.direction === "out" ? "flex-end" : "flex-start",
                    background: (m as any).internal ? "#fef9c3" : "#fff",
                    color: "#0f172a",
                    border: (m as any).internal ? "1px dashed #d4a017" : (m.direction === "out" ? "1.5px solid #2563eb" : "1px solid #e8edf3"),
                    boxShadow: "0 1px 2px rgba(0,0,0,.05)" }}>
                  <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: .2, marginBottom: 4, paddingBottom: 3, borderBottom: (m as any).internal ? "1px solid rgba(212,160,23,.3)" : (m.direction === "out" ? "1px solid rgba(37,99,235,.25)" : "1px solid rgba(0,0,0,.08)"), color: (m as any).internal ? "#92400e" : (m.direction === "out" ? "#2563eb" : "var(--brand)") }}>
                    {(m as any).internal ? "📝 " + (m.sender_name || t("Менеджер","Менеджер")) + " · " + t("только команда","тільки команда") : (m.sender_name || (m.direction === "out" ? t("Менеджер","Менеджер") : (active?.title || t("Клиент","Клієнт"))))}
                  </div>
                  <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{linkify(m.text, m.direction === "out")}</span>
                  {m.attachments?.map((a, i) => (
                    <div key={i} style={{ fontSize: 11, opacity: .8, marginTop: 4 }}>
                      <Icon n="paperclip" size={13} /> {a.type === "voice" ? t(`голосовое ${a.duration ?? ""}с`,`голосове ${a.duration ?? ""}с`) : a.type}
                    </div>
                  ))}
                  <div style={{ fontSize: 10, opacity: .55, marginTop: 3, textAlign: m.direction === "out" ? "right" : "left" }}>{(m as any).created_at ? new Date((m as any).created_at).toLocaleTimeString("uk", { hour: "2-digit", minute: "2-digit" }) : ""}</div>
                </div>
              ))}
              <div ref={endRef} />
            </div>
            {err && <div className="err" style={{ padding: "0 16px" }}>{err}</div>}
            <div style={{ background: "#fff", borderTop: "1px solid #e2e8f0", padding: "0 12px 12px" }}>
              <div onMouseDown={startResizeComposer} title={t("Потяни вверх — увеличить поле ввода","Потягни вгору — збільшити поле вводу")} style={{ height: 13, cursor: "ns-resize", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div style={{ width: 44, height: 4, borderRadius: 4, background: "#cbd5e1" }} />
              </div>
              {internalNote && <div style={{ background: "#fef9c3", color: "#854d0e", fontSize: 11.5, fontWeight: 600, padding: "5px 10px", borderRadius: 6, marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}><Icon n="eye" size={14} /> {t("Режим заметки — клиент НЕ увидит, видят только менеджеры","Режим нотатки — клієнт НЕ побачить, бачать лише менеджери")}</div>}
              <div style={{ display: "flex", gap: 6, alignItems: "flex-end" }}>
              <input ref={fileRef} type="file" hidden onChange={sendFile} />
              <button className="btn" type="button" style={{ background: internalNote ? "#fde68a" : "#f1f5f9", color: internalNote ? "#92400e" : "#475569", fontWeight: internalNote ? 700 : 400, flex: "0 0 auto", height: 38 }} title={t("Скрытая заметка для менеджеров (клиент не увидит)","Прихована нотатка для менеджерів (клієнт не побачить)")} onClick={() => setInternalNote((v) => !v)}><Icon n="eye" size={17} /></button>
              <EmojiButton onPick={(em) => setText((tx) => tx + em)} />
              <button className="btn" type="button" style={{ background: "#f1f5f9", flex: "0 0 auto", height: 38 }} title={t("Прикрепить файл / фото / видео / документ","Прикріпити файл / фото / відео / документ")} onClick={() => fileRef.current?.click()} disabled={sending}><Icon n="paperclip" size={17} /></button>
              <textarea value={text} rows={1}
                onChange={(e) => { setText(e.target.value); if (composerH === null) { e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 170) + "px"; } }}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                onPaste={onPasteFile}
                placeholder={internalNote ? t("Внутренняя заметка — клиент НЕ увидит…  (Enter — отправить, Shift+Enter — новая строка)","Внутрішня нотатка — клієнт НЕ побачить…  (Enter — надіслати, Shift+Enter — новий рядок)") : t(`Сообщение в ${active.channel_name}…  (Enter — отправить, Shift+Enter — строка, вставить фото — Ctrl+V)`,`Повідомлення в ${active.channel_name}…  (Enter — надіслати, Shift+Enter — рядок, вставити фото — Ctrl+V)`)}
                style={{ flex: 1, minHeight: 38, height: composerH ? composerH + "px" : undefined, maxHeight: composerH ? undefined : 170, background: internalNote ? "#fffbeb" : "#f1f5f9", border: internalNote ? "1.5px dashed #d4a017" : "none", borderRadius: 7, padding: "9px 12px", fontSize: 13, outline: "none", resize: "none", lineHeight: 1.4, fontFamily: "inherit", boxSizing: "border-box" }} />
              <button className="btn btn-primary" onClick={send} disabled={sending} style={{ background: internalNote ? "#d4a017" : undefined, height: 38 }}>{sending ? "…" : (internalNote ? <><Icon n="file" size={14} /> {t("Заметка","Нотатка")}</> : t("Отправить","Відправити"))}</button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* AI-РОП панель */}
      <div style={{ background: "#fff", borderLeft: "1px solid #e2e8f0", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: "14px 14px 12px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center" }}>
          <b style={{ fontSize: 14 }}><Icon n="brain" size={16} /> AI-РОП</b>
          <div style={{ flex: 1 }} />
          {active && <button className="btn" style={{ fontSize: 12, padding: "3px 10px" }} onClick={() => analyzeAI(active.id)} disabled={aiLoad}>{aiLoad ? "…" : <><Icon n="refresh" size={14} /> {t("Обновить","Оновити")}</>}</button>}
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
                  <button className="btn btn-primary" style={{ width: "100%", marginTop: 8 }} onClick={() => setText(ai.suggestion || "")}><Icon n="pencil" size={14} /> {t("Вставить в ответ","Вставити у відповідь")}</button>
                </>
              )}
            </>
          ) : (
            <div style={{ textAlign: "center", paddingTop: 24 }}>
              <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>{t("AI-РОП подскажет тезисы диалога + готовый ответ.","AI-РОП підкаже тези діалогу + готову відповідь.")}</div>
              <button className="btn btn-primary" onClick={() => active && analyzeAI(active.id)} disabled={aiLoad}>{aiLoad ? t("Анализирую…","Аналізую…") : <><Icon n="brain" size={15} /> {t("Проанализировать диалог","Проаналізувати діалог")}</>}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
