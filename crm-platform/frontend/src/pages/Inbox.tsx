import { Fragment, useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api, ChatMessage, Conversation, Paginated } from "../api";
import { Avatar, SourceChip } from "../ui";
import { useAuth } from "../auth";
import { useLang } from "../i18n";
import TeamChat from "./TeamChat";
import DealCard from "./DealCard";
import { EmojiButton } from "../ChatCompose";
import { AiComposeAssist } from "../AiComposeAssist";
import { linkify, dayLabel, metaWindow, SNDR_MAP } from "../chatUtils";
import { Icon } from "../Icon";
import { TaskQuickModal } from "../TaskQuickModal";
import ConversationSourceCard from "../ConversationSourceCard";
import { ReplyContext, ReactionBadges, isContextAttachment } from "../MessageContext";
import { msgSoundOn, setMsgSoundOn, teamSoundOn, setTeamSoundOn } from "../sounds";




export default function Inbox() {
  const { can, me } = useAuth();
  const { t } = useLang();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [scope, setScope] = useState<"mine" | "all" | "unassigned" | "clients" | "need" | "waiting">("all");
  const [tab, setTab] = useState<"chats" | "notif" | "team">("chats");
  const [sndCli, setSndCli] = useState(msgSoundOn());
  const [sndTeam, setSndTeam] = useState(teamSoundOn());
  useEffect(() => { if (params.get("tab") === "team") setTab("team"); /* eslint-disable-next-line */ }, [params]);
  const [notifN, setNotifN] = useState(0);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [dealDrawer, setDealDrawer] = useState<number | null>(null);
  const PRIO: Record<string, { icon: string; color: string; bg: string; label: string }> = {
    complaint: { icon: "warn", color: "#dc2626", bg: "#fef2f2", label: t("Возмущение","Обурення") },
    urgent: { icon: "flame", color: "#ea580c", bg: "#fff7ed", label: t("Хочет срочно","Хоче терміново") },
    needs_quote: { icon: "calculator", color: "#d97706", bg: "#fffbeb", label: t("Нужен просчёт","Потрібен прорахунок") },
    quoted: { icon: "badge-check", color: "#16a34a", bg: "#f0fdf4", label: t("Просчитано ИИ","Прораховано ШІ") },
    thinking: { icon: "clock", color: "#64748b", bg: "#f1f5f9", label: t("Думает","Думає") },
  };
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [siblings, setSiblings] = useState<Conversation[]>([]); // інші діалоги того ж клієнта (інші канали)
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [internalNote, setInternalNote] = useState(false);
  const [taskOpen, setTaskOpen] = useState(false);
  const [composerH, setComposerH] = useState<number | null>(null);
  const [pending, setPending] = useState<any[]>([]);
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
  const headRef = useRef<HTMLDivElement | null>(null);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const el = headRef.current; if (!el) return;
    const ro = new ResizeObserver(() => setCompact(el.offsetWidth < 660));
    ro.observe(el); return () => ro.disconnect();
  }, [active]);
  const [search, setSearch] = useState("");
  const [channels, setChannels] = useState<{ id: number; name: string }[]>([]);
  const [chFilter, setChFilter] = useState("");
  const [period, setPeriod] = useState("all");
  const [prio, setPrio] = useState("");
  const [density, setDensity] = useState<"xs" | "sm" | "md" | "lg">(() => ((localStorage.getItem("inboxDensity") as any) || "sm"));
  const [filtersOpen, setFiltersOpen] = useState(() => localStorage.getItem("inboxFiltersOpen") === "1");
  useEffect(() => { localStorage.setItem("inboxDensity", density); }, [density]);
  useEffect(() => { localStorage.setItem("inboxFiltersOpen", filtersOpen ? "1" : "0"); }, [filtersOpen]);
  const DENS = ({ xs: { pad: "3px 10px", gap: 0, av: "", name: 11, text: 9.5, sub: 9, time: 8.5 }, sm: { pad: "4px 9px", gap: 6, av: "av-xs", name: 11.5, text: 10.5, sub: 9.5, time: 9 }, md: { pad: "6px 10px", gap: 7, av: "av-sm", name: 12.5, text: 11.5, sub: 10, time: 9.5 }, lg: { pad: "9px 12px", gap: 9, av: "av-md", name: 13.5, text: 12.5, sub: 11, time: 10 } } as any)[density];
  const [selMode, setSelMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const endRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<Conversation | null>(null);

  function listQuery() {
    const sp = new URLSearchParams({ page_size: "50" });
    const beScope = scope; // need/waiting = справжній фільтр на бекенді
    if (beScope && beScope !== "all") sp.set("scope", beScope);
    if (chFilter.startsWith("meta_")) sp.set("channel_group", chFilter);
    else if (chFilter) sp.set("channel", chFilter);
    if (period && period !== "all") sp.set("period", period);
    if (prio) sp.set("priority", prio);
    if (search.trim()) sp.set("search", search.trim());
    return "?" + sp.toString();
  }
  async function loadConvs() {
    const q = listQuery();
    const d = await api.get<Paginated<Conversation>>(`/api/conversations/${q}`);
    setConvs(d.results); setNextUrl((d as any).next || null);
    // НЕ відкривати «перший-ліпший» чат, коли прийшли за конкретним клієнтом (?contact= / ?c=)
    if (!activeRef.current && d.results[0] && !params.get("contact") && !params.get("c")) openConv(d.results[0]);
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
      const fresh = new Map<number, Conversation>(d.results.map((r) => [r.id, r]));
      // Оновлюємо НА МІСЦІ (без пересортування → список не стрибає, менеджер не втрачає діалог).
      // Незмінені чати повертаємо ТИМ САМИМ обʼєктом → React не перемальовує (нема моргання).
      const merged = cs.map((c) => {
        const r: any = fresh.get(c.id); const cc: any = c;
        if (!r) return c;
        if (r.last_message_at === cc.last_message_at && r.unread === cc.unread && r.needs_reply === cc.needs_reply
            && r.assigned_to === cc.assigned_to && r.priority === cc.priority && r.is_seen === cc.is_seen) return c;
        return { ...c, ...r };
      });
      const existing = new Set(cs.map((c) => c.id));
      const added = d.results.filter((r) => !existing.has(r.id));  // нові чати — зверху
      return added.length ? [...added, ...merged] : merged;
    });
  }
  useEffect(() => { loadConvs(); }, [scope, chFilter, period, prio]);
  useEffect(() => { const id = setTimeout(() => loadConvs(), 400); return () => clearTimeout(id); /* eslint-disable-next-line */ }, [search]);
  // live-оновлення відкритого чату (без ручного refresh)
  useEffect(() => {
    if (!active) return;
    const t = setInterval(async () => {
      try {
        const m = await api.get<ChatMessage[]>(`/api/conversations/${active.id}/messages/?seen=1`);
        setMsgs((prev) => (m.length !== prev.length ? m : prev));
      } catch { /* ignore */ }
    }, 6000);
    return () => clearInterval(t);
  }, [active]);
  // періодичне оновлення списку чатів
  useEffect(() => {
    const t = setInterval(() => refreshList(), 20000);
    return () => clearInterval(t);
  }, [scope, chFilter, period, prio]);
  useEffect(() => {
    const contactId = params.get("contact");
    if (contactId) {
      api.get<any>(`/api/conversations/?contact=${contactId}`).then((r) => {
        const conv = ((r as any).results || [])[0];
        if (conv) { setConvs((cs) => cs.some((x) => x.id === conv.id) ? cs : [conv, ...cs]); openConv(conv); }
        else setErr(t("⚠️ У этого клиента ещё НЕТ переписки — чат не открыт. Напиши первым через карточку клиента или дождись входящего.","⚠️ У цього клієнта ще НЕМАЄ листування — чат не відкрито. Напиши першим через картку клієнта або дочекайся вхідного."));
      }).catch(() => {});
      return;
    }
    const cid = params.get("c");
    if (!cid) return;
    api.get<Conversation>(`/api/conversations/${cid}/`).then((c) => { setConvs((cs) => cs.some((x) => x.id === c.id) ? cs : [c, ...cs]); openConv(c); }).catch(() => {});
  }, [params]);
  useEffect(() => { activeRef.current = active; }, [active]);
  useEffect(() => { const f = () => api.get<any>("/api/inbox/ping/").then((d) => setNotifN(d.unread || 0)).catch(() => {}); f(); const tm = setInterval(f, 15000); return () => clearInterval(tm); }, []);
  const [msgMenu, setMsgMenu] = useState<number | null>(null); // id повідомлення з відкритим меню
  async function markUnreadFrom(convId: number, msgId?: number) {
    try {
      const r: any = await api.post(`/api/conversations/${convId}/mark-unread/`, msgId ? { from_message: msgId } : {});
      setConvs((cs) => cs.map((x) => (x.id === convId ? ({ ...x, unread: r.unread, needs_reply: true } as any) : x)));
      setMsgMenu(null);
    } catch { alert("Не вдалося"); }
  }
  useEffect(() => { api.get<any>("/api/channels/").then((d) => setChannels(((d.results || d) as any[]).map((c) => ({ id: c.id, name: c.name })))).catch(() => {}); }, []);
  useEffect(() => { api.get<any>("/api/conversations/staff/").then((d) => setEmps(((d.results || d) as any[]).map((u) => ({ id: u.id, full_name: u.full_name || u.username })))).catch(() => {}); }, []);
  useEffect(() => { endRef.current?.scrollIntoView(); }, [msgs]);

  async function analyzeAI(id: number) {
    setAiLoad(true);
    try { setAi(await api.post<any>(`/api/conversations/${id}/ai_reply/`, {})); }
    catch { setAi(null); }
    setAiLoad(false);
  }

  async function openConv(c: Conversation) {
    setActive(c); setErr(""); setAi(null);
    const m = await api.get<ChatMessage[]>(`/api/conversations/${c.id}/messages/?seen=1`);
    setMsgs(m);
    setConvs((cs) => cs.map((x) => (x.id === c.id ? { ...x, unread: 0 } : x)));
    // актуалізувати стан діалогу (хто вже взяв у роботу) — список міг бути застарілим
    try { const fresh = await api.get<Conversation>(`/api/conversations/${c.id}/`); setActive((cur) => (cur && cur.id === fresh.id ? { ...cur, ...fresh } : cur)); setConvs((cs) => cs.map((x) => (x.id === fresh.id ? { ...x, ...fresh } : x))); } catch { /* ignore */ }
  }

  // інші діалоги того ж клієнта (веб-чат / Telegram / Instagram …) — щоб бачити, що клієнт писав в іншому каналі
  useEffect(() => {
    const cid = active?.contact;
    if (!cid) { setSiblings([]); return; }
    api.get<Conversation[]>(`/api/conversations/by_contact/?contact=${cid}`)
      .then((rows) => setSiblings((rows || []).filter((r) => r.id !== active?.id)))
      .catch(() => setSiblings([]));
  }, [active?.id, active?.contact]);

  async function goToCard() {
    if (!active) return;
    try {
      if ((active as any).deal_id) { setDealDrawer((active as any).deal_id); return; }
      if (active.contact) {
        const dl = await api.get<any>(`/api/deals/?contact=${active.contact}`);
        const deal = ((dl as any).results || [])[0];
        if (deal) { setDealDrawer(deal.id); return; }
      }
      const r = await api.post<any>(`/api/conversations/${active.id}/create_deal/`, {});
      if (r.deal_id) setDealDrawer(r.deal_id); else setErr(t("Не удалось создать сделку", "Не вдалося створити угоду"));
    } catch { setErr(t("Не удалось открыть карточку", "Не вдалося відкрити картку")); }
  }

  async function send() {
    if (!active) return;
    if (!text.trim() && pending.length === 0) return;
    setSending(true); setErr("");
    try {
      for (const att of pending) {
        const m = await api.post<ChatMessage>(`/api/conversations/${active.id}/send_media/`, { content_b64: att.dataURL, filename: att.name, kind: att.kind, internal: internalNote });
        setMsgs((ms) => [...ms, m]);
      }
      setPending([]);
      if (text.trim()) {
        const m = await api.post<ChatMessage>(`/api/conversations/${active.id}/send/`, { text, internal: internalNote });
        setMsgs((ms) => [...ms, m]); setText("");
      }
    } catch (e: any) {
      setErr(e?.response?.data?.detail || t("Не удалось отправить (проверь токен бота / сеть).","Не вдалося надіслати (перевір токен бота / мережу)."));
    } finally { setSending(false); }
  }

  function stageFile(f: File | null | undefined) {
    if (!f) return;
    const kind = f.type.startsWith("video") ? "video" : f.type.startsWith("image") ? "photo" : "document";
    const reader = new FileReader();
    reader.onload = () => setPending((p) => [...p, { name: f.name, kind, dataURL: String(reader.result) }]);
    reader.readAsDataURL(f);
  }
  function sendFile(e: any) { stageFile(e.target.files?.[0]); e.target.value = ""; }
  function onPasteFile(e: any) {
    const items = e.clipboardData?.items || [];
    for (let i = 0; i < items.length; i++) { const it = items[i]; if (it.type && it.type.startsWith("image")) { const f = it.getAsFile(); if (f) { e.preventDefault(); stageFile(f); return; } } }
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
    try { const c = await api.post<Conversation>(`/api/conversations/${active.id}/take/`, {}); setActive(c); setConvs((cs) => cs.map((x) => (x.id === c.id ? { ...x, ...c } : x))); }
    catch (e: any) {
      if (e?.status === 409) {
        alert(e?.data?.detail || t("Диалог уже взят другим менеджером","Діалог уже взяв інший менеджер"));
        // підтягнути актуальний стан (хто взяв) — щоб зникла кнопка й оновився список
        try { const fresh = await api.get<Conversation>(`/api/conversations/${active.id}/`); setActive(fresh); setConvs((cs) => cs.map((x) => (x.id === fresh.id ? { ...x, ...fresh } : x))); } catch { /* ignore */ }
        refreshList();
      } else { setErr(t("Не удалось","Не вдалося")); }
    }
    setMenu(false);
  }
  async function closeConv() {
    if (!active) return;
    try { await api.post<any>(`/api/conversations/${active.id}/close/`, {}); setConvs((cs) => cs.filter((x) => x.id !== active.id)); setActive(null); setMsgs([]); } catch { setErr(t("Не удалось","Не вдалося")); }
    setMenu(false);
  }
  function goToContact() { setMenu(false); if (active?.contact) nav(`/clients/${active.contact}?c=${active.id}`); }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", gap: 6, padding: "8px 12px", background: "#fff", borderBottom: "1px solid #e2e8f0", flexShrink: 0, alignItems: "center" }}>
        <button onClick={() => setTab("chats")} className={"btn" + (tab === "chats" ? " btn-primary" : " btn-light")} style={{ fontSize: 13, fontWeight: 600 }}><Icon n="message" size={15} /> {t("Чаты с клиентами", "Чати з клієнтами")}</button>
        <button onClick={() => setTab("notif")} className={"btn" + (tab === "notif" ? " btn-primary" : " btn-light")} style={{ fontSize: 13, fontWeight: 600 }}><Icon n="bell" size={15} /> {t("Уведомления", "Сповіщення")}{notifN > 0 && <span style={{ marginLeft: 6, background: "#dc2626", color: "#fff", borderRadius: 20, fontSize: 11, fontWeight: 700, padding: "1px 7px" }}>{notifN}</span>}</button>
        <button onClick={() => setTab("team")} className={"btn" + (tab === "team" ? " btn-primary" : " btn-light")} style={{ fontSize: 13, fontWeight: 600 }}><Icon n="users" size={15} /> {t("Чаты сотрудников", "Чати співробітників")}</button>
        <div style={{ flex: 1 }} />
        <button title={t(sndCli ? "Звук чатов с клиентами: включён — нажмите чтобы выключить" : "Звук чатов с клиентами: выключен", sndCli ? "Звук чатів з клієнтами: увімкнено — натисніть щоб вимкнути" : "Звук чатів з клієнтами: вимкнено")}
          onClick={() => { const v = !sndCli; setSndCli(v); setMsgSoundOn(v); }} className="btn btn-light" style={{ fontSize: 12.5, fontWeight: 600, opacity: sndCli ? 1 : 0.5 }}>
          <span style={{ fontSize: 15 }}>{sndCli ? "🔔" : "🔕"}</span> {t("Клиенты", "Клієнти")}
        </button>
        <button title={t(sndTeam ? "Звук чата сотрудников: включён — нажмите чтобы выключить" : "Звук чата сотрудников: выключен", sndTeam ? "Звук чату співробітників: увімкнено — натисніть щоб вимкнути" : "Звук чату співробітників: вимкнено")}
          onClick={() => { const v = !sndTeam; setSndTeam(v); setTeamSoundOn(v); }} className="btn btn-light" style={{ fontSize: 12.5, fontWeight: 600, opacity: sndTeam ? 1 : 0.5 }}>
          <span style={{ fontSize: 15 }}>{sndTeam ? "🔔" : "🔕"}</span> {t("Сотрудники", "Співробітники")}
        </button>
      </div>
      {tab === "team" ? <TeamChat /> : tab === "notif"
        ? <NotifFeed t={t} nav={nav} onOpen={(cid: number) => { setTab("chats"); api.get<Conversation>(`/api/conversations/${cid}/`).then((c) => { setConvs((cs) => cs.some((x) => x.id === c.id) ? cs : [c, ...cs]); openConv(c); }).catch(() => {}); }} />
        : <div className="inbox fade" style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "300px 1fr 340px" }}>
      {/* список диалогов */}
      <div style={{ background: "#fff", borderRight: "1px solid #e2e8f0", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: 12, borderBottom: "1px solid #e2e8f0", fontWeight: 600 }}>{t("Диалоги","Діалоги")}</div>
        <div style={{ padding: "8px 12px", borderBottom: "1px solid #f1f5f9" }}>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("🔍 Имя, телефон, ник…","🔍 Імʼя, телефон, нік…")} style={{ width: "100%", height: 28, border: "1px solid #e2e8f0", borderRadius: 8, padding: "0 10px", fontSize: 12, boxSizing: "border-box" }} />
        </div>
        <div style={{ display: "flex", gap: 6, padding: "6px 12px", borderBottom: "1px solid #f1f5f9", alignItems: "center" }}>
          <button onClick={() => setFiltersOpen((v) => !v)} title={t("Показать / скрыть фильтры: разделы, канал, статус, дата","Показати / сховати фільтри: розділи, канал, статус, дата")}
            style={{ fontSize: 12, fontWeight: 600, padding: "5px 9px", borderRadius: 7, cursor: "pointer", border: "1px solid " + (filtersOpen ? "var(--brand)" : "#e2e8f0"), background: filtersOpen ? "#eff6ff" : "#fff", color: "#475569" }}>{t("Фильтры","Фільтри")} {filtersOpen ? "▴" : "▾"}</button>
          <div style={{ flex: 1 }} />
          <div title={t("Размер чатов в списке — выбери удобный масштаб","Розмір чатів у списку — обери зручний масштаб")} style={{ display: "flex", border: "1px solid #e2e8f0", borderRadius: 7, overflow: "hidden" }}>
            {(["sm", "md", "lg", "xs"] as const).map((d) => (
              <button key={d} onClick={() => setDensity(d)} title={d === "sm" ? t("Мелкий","Дрібний") : d === "md" ? t("Средний","Середній") : d === "lg" ? t("Крупный","Великий") : t("Без аватара — максимум чатов","Без аватара — максимум чатів")}
                style={{ fontSize: 11, fontWeight: 700, padding: "5px 7px", cursor: "pointer", border: "none", background: density === d ? "var(--brand)" : "#fff", color: density === d ? "#fff" : "#64748b" }}>{d === "sm" ? "S" : d === "md" ? "M" : d === "lg" ? "L" : "☰"}</button>
            ))}
          </div>
          <button onClick={() => { setSelMode((v) => !v); setSelected(new Set()); }} title={t("Выбрать несколько чатов и массово закрыть","Обрати кілька чатів і масово закрити")}
            style={{ height: 30, fontSize: 13, padding: "0 9px", borderRadius: 7, cursor: "pointer", border: "1px solid " + (selMode ? "var(--brand)" : "#e2e8f0"), background: selMode ? "var(--brand)" : "#fff", color: selMode ? "#fff" : "#475569" }}><Icon n="check-square" size={16} /></button>
        </div>
        {filtersOpen && (
          <div style={{ borderBottom: "1px solid #f1f5f9" }}>
            <div style={{ display: "flex", gap: 6, padding: "8px 12px 4px", flexWrap: "wrap" }}>
              {(([["mine", t("Мои","Мої")], ["clients", t("Клиенты","Клієнти")], ["need", t("Нужен ответ","Потрібна відповідь")], ["waiting", t("Ждём клиента","Чекаємо клієнта")]].concat(can("conversation.view.all") ? [["all", t("Все","Всі")], ["unassigned", t("Не назначены","Не призначені")]] : [])) as [string, string][]).map(([k, label]) => (
                <button key={k} onClick={() => setScope(k as any)} title={t("Раздел диалогов","Розділ діалогів")}
                  style={{ fontSize: 12, padding: "4px 10px", borderRadius: 14, cursor: "pointer", border: "1px solid " + (scope === k ? "var(--brand)" : "#e2e8f0"), background: scope === k ? "var(--brand)" : "#fff", color: scope === k ? "#fff" : "#475569" }}>{label}</button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 6, padding: "0 12px 8px", alignItems: "center", flexWrap: "wrap" }}>
              <select value={chFilter} onChange={(e) => setChFilter(e.target.value)} title={t("Фильтр по каналу (Instagram, Telegram…)","Фільтр за каналом (Instagram, Telegram…)")} style={{ flex: 1, minWidth: 86, height: 28, fontSize: 12, border: "1px solid #e2e8f0", borderRadius: 7, padding: "0 6px" }}>
                <option value="">{t("Все каналы","Всі канали")}</option>
                <option value="meta_instagram_direct">Meta · Instagram Direct</option>
                <option value="meta_facebook_direct">Meta · Facebook Messenger</option>
                <option value="meta_instagram_comments">{t("Meta · Комментарии Instagram","Meta · Коментарі Instagram")}</option>
                <option value="meta_facebook_comments">{t("Meta · Комментарии Facebook","Meta · Коментарі Facebook")}</option>
                {channels
                  .filter((c) => {
                    const name = c.name.toLowerCase();
                    return !name.includes("chatplace") && !name.startsWith("meta ·");
                  })
                  .map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <select value={prio} onChange={(e) => setPrio(e.target.value)} title={t("Фильтр по статусу / приоритету ИИ","Фільтр за статусом / пріоритетом ШІ")} style={{ flex: 1, minWidth: 96, height: 28, fontSize: 12, border: "1px solid #e2e8f0", borderRadius: 7, padding: "0 6px" }}>
                <option value="">{t("Все статусы","Всі статуси")}</option>
                <option value="needs_quote">{t("Нужен просчёт","Потрібен прорахунок")}</option>
                <option value="quoted">{t("Просчитано ИИ","Прораховано ШІ")}</option>
                <option value="urgent">{t("Хочет срочно","Хоче терміново")}</option>
                <option value="complaint">{t("Возмущение","Обурення")}</option>
                <option value="thinking">{t("Думает","Думає")}</option>
              </select>
              <select value={period} onChange={(e) => setPeriod(e.target.value)} title={t("Фильтр по дате","Фільтр за датою")} style={{ flex: 1, minWidth: 86, height: 28, fontSize: 12, border: "1px solid #e2e8f0", borderRadius: 7, padding: "0 6px" }}>
                <option value="all">{t("Все дни","Всі дні")}</option>
                <option value="today">{t("Сегодня","Сьогодні")}</option>
                <option value="yesterday">{t("Вчера","Вчора")}</option>
                <option value="7d">{t("7 дней","7 днів")}</option>
                <option value="30d">{t("30 дней","30 днів")}</option>
              </select>
            </div>
          </div>
        )}
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
                style={{ padding: DENS.pad, borderBottom: "1px solid #f1f5f9", cursor: "pointer",
                  display: "flex", gap: DENS.gap, background: selected.has(c.id) ? "#fef3c7" : (active?.id === c.id ? "#eff6ff" : "") }}>
                {selMode && <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggleSel(c.id)} onClick={(e) => e.stopPropagation()} style={{ alignSelf: "center", width: 16, height: 16, cursor: "pointer" }} />}
                {DENS.av ? <Avatar name={c.contact_name || c.title || "?"} cls={DENS.av} /> : null}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: DENS.name, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.contact_name || c.title || t("Без имени","Без імені")}</span>
                    <span style={{ fontSize: DENS.time, color: "#94a3b8", whiteSpace: "nowrap" }}>{fmtAt((c as any).last_message_at)}</span>
                  </div>
                  <div className="muted" style={{ fontSize: DENS.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.last_text}</div>
                  <FitChips>
                    {/* канал — круглою іконкою ЗЛІВА; решта бейджів єдиної висоти 18px */}
                    <SourceChip source={c.channel_kind} />
                    <span title={c.assigned_to ? t("Ответственный","Відповідальний") : t("Свободный — не назначен","Вільний — не призначено")} style={{ display: "inline-flex", alignItems: "center", height: 18, fontSize: 10, fontWeight: 600, color: c.assigned_to ? "#1d4ed8" : "#64748b", background: c.assigned_to ? "#dbeafe" : "#f1f5f9", borderRadius: 20, padding: "0 8px", whiteSpace: "nowrap" }}>{c.assigned_to ? "👤 " + c.assigned_to_name : t("Вільний","Вільний")}</span>
                    {(c as any).deal_stage && <span title={t("Стадия сделки","Стадія угоди")} style={{ display: "inline-flex", alignItems: "center", height: 18, fontSize: 10, fontWeight: 600, color: "#0369a1", background: "#e0f2fe", borderRadius: 20, padding: "0 8px", whiteSpace: "nowrap" }}>{(c as any).deal_stage}</span>}
                    {(c as any).priority && PRIO[(c as any).priority] && <span title={(c as any).priority_reason || PRIO[(c as any).priority].label} style={{ display: "inline-flex", alignItems: "center", gap: 3, height: 18, fontSize: 10, fontWeight: 700, color: PRIO[(c as any).priority].color, background: PRIO[(c as any).priority].bg, borderRadius: 20, padding: "0 8px", whiteSpace: "nowrap" }}><Icon n={PRIO[(c as any).priority].icon} size={10} /> {PRIO[(c as any).priority].label}</span>}
                  </FitChips>
                </div>
                {(() => {
                  const cnt = (((c as any).unhandled_in as number) || 0) || (c.unread || 0);
                  const ai = !!(c as any).ai_answered;
                  if (!cnt && !ai) return null;
                  // ІІ-іконка (bot, як у всій CRM) — база; червоний лічильник — маленьким бейджем у куті
                  return (
                    <span style={{ position: "relative", display: "inline-flex", alignItems: "center", justifyContent: "center", alignSelf: "center", flexShrink: 0, width: ai ? 20 : undefined, height: 20 }}>
                      {ai && <span title={t("Ответил ИИ-агент, менеджер не смотрел", "Відповів ШІ-агент, менеджер не дивився")} style={{ color: "#7c3aed", display: "inline-flex" }}><Icon n="bot" size={16} /></span>}
                      {cnt > 0 && (
                        <span title={t("Сообщений клиента без ответа менеджера", "Повідомлень клієнта без відповіді менеджера")}
                          style={{ position: ai ? "absolute" : "static", top: ai ? -4 : undefined, right: ai ? -6 : undefined, minWidth: 15, height: 15, borderRadius: 8, padding: "0 3px", background: "#ef4444", color: "#fff", fontSize: 9.5, fontWeight: 700, lineHeight: 1, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 0 0 1.5px #fff" }}>
                          {cnt}
                        </span>
                      )}
                    </span>
                  );
                })()}
                
              </div>
            );
            // 3 категорії: Непризначені (вільний пул, видно всім з доступом до каналу)
            // + Потрібна відповідь / В роботі (тільки призначені = свої)
            // БЕЗ пересортування на рендер: порядок приходить із сервера (-last_message_at,
            // сьогодні зверху) і тримається refreshList «на місці». Інакше при відповіді час
            // чату оновлюється → чат стрибав наверх і менеджер губив вибраний діалог.
            const unassigned = convs.filter((c) => !c.assigned_to);
            const need = convs.filter((c) => c.assigned_to && (c as any).needs_reply);
            const work = convs.filter((c) => c.assigned_to && !(c as any).needs_reply);
            const hdr = (icon: string, label: string, color: string) => <div style={{ padding: "8px 12px 4px", fontSize: 11, fontWeight: 700, color, textTransform: "uppercase", letterSpacing: .3, display: "flex", alignItems: "center", gap: 5 }}><Icon n={icon} size={12} /> {label}</div>;
            const withDays = (list: Conversation[]) => {
              const dk = (c: any) => c.last_message_at ? new Date(c.last_message_at).toDateString() : "\u2014";
              const cnt: any = {}; list.forEach((c: any) => { const k = dk(c); cnt[k] = (cnt[k] || 0) + 1; });
              const out: any[] = []; let prev: any = null;
              list.forEach((c: any) => { const k = dk(c); if (k !== prev) { prev = k; out.push(<div key={"day-" + c.id} style={{ position: "sticky", top: 0, zIndex: 3, background: "#e2e8f0", padding: "5px 12px", fontSize: 11, fontWeight: 700, color: "#334155", borderTop: "1px solid #cbd5e1", borderBottom: "1px solid #cbd5e1", display: "flex", justifyContent: "space-between", alignItems: "center" }}><span style={{ textTransform: "capitalize" }}>{dayLabel(c.last_message_at, t)}</span><span style={{ background: "#94a3b8", color: "#fff", borderRadius: 20, padding: "1px 8px", fontSize: 10.5 }}>{cnt[k]}</span></div>); } out.push(card(c)); });
              return out;
            };
            return (<>
              {scope !== "need" && scope !== "waiting" && unassigned.length > 0 && hdr("bell", t(`Не назначены — свободные (${unassigned.length})`,`Непризначені — вільні (${unassigned.length})`), "#7c3aed")}
              {scope !== "need" && scope !== "waiting" && withDays(unassigned)}
              {scope !== "waiting" && need.length > 0 && hdr("circle", t(`Нужен ответ (${need.length})`,`Потрібна відповідь (${need.length})`), "#dc2626")}
              {scope !== "waiting" && withDays(need)}
              {scope !== "need" && work.length > 0 && hdr("check", t(`Ждём клиента (${work.length})`,`Чекаємо клієнта (${work.length})`), "#16a34a")}
              {scope !== "need" && withDays(work)}
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
            <div ref={headRef} style={{ minHeight: 52, background: "#fff", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6, rowGap: 6, padding: "7px 14px" }}>
              <Avatar name={active.contact_name || active.title || "?"} cls="av-md" />
              <div style={{ flex: "1 1 130px", minWidth: 0, display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
                <b style={{ fontSize: 14, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{active.contact_name || active.title}</b>
                <span className="muted" style={{ fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{active.assigned_to ? "👤 " + active.assigned_to_name : t("Не назначено","Не призначено")}{(active as any).participant_names && (active as any).participant_names.length > 0 ? " · 👥 " + (active as any).participant_names.join(", ") : ""} · {active.channel_name}</span>
              </div>
              <SourceChip source={active.channel_kind} />
              {(() => { const w = metaWindow(active, msgs); return w ? <span title={w.closed ? t("Окно Instagram (24ч) закрыто — клиент может НЕ получить обычное сообщение","Вікно Instagram (24г) закрите — клієнт може НЕ отримати звичайне повідомлення") : t("Окно открыто — клиент получит сообщение","Вікно відкрите — клієнт отримає повідомлення")} style={{ fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 20, whiteSpace: "nowrap", color: w.closed ? "#b91c1c" : "#15803d", background: w.closed ? "#fee2e2" : "#dcfce7" }}>{w.closed ? "\ud83d\udd34 " + t("Окно закрыто","Вікно закрите") + " · " + w.hrs + t("ч","г") : "\ud83d\udfe2 " + t("Окно 24ч","Вікно 24 год")}</span> : null; })()}
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                <button className="btn" style={{ padding: compact ? "0 9px" : undefined, background: "#fef3c7", color: "#92400e" }} title={t("Поставить задачу по клиенту","Поставити задачу по клієнту")} onClick={() => setTaskOpen(true)}><Icon n="check" size={15} />{!compact && <> {t("Задача","Задача")}</>}</button>
                <button className="btn btn-green" style={{ padding: compact ? "0 9px" : undefined }} title={t("Позвонить","Подзвонити")}><Icon n="phone" size={15} />{!compact && <> {t("Позвонить","Подзвонити")}</>}</button>
                <button className="btn" style={{ background: "#f1f5f9", fontWeight: 700, lineHeight: 1, padding: "0 11px" }} onClick={() => setMenu((m) => !m)} title={t("Ещё","Ще")}><Icon n="more" size={16} /></button>
              </div>
            </div>
            {taskOpen && active && <TaskQuickModal prefill={{ conversation: active.id, contact: active.contact, contact_name: active.contact_name || active.title, conversation_title: active.title }} onClose={() => setTaskOpen(false)} onSaved={() => setTaskOpen(false)} />}
            {menu && (<>
              <div onClick={() => setMenu(false)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
              <div style={{ position: "fixed", top: 104, right: 360, width: 260, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 14px 36px rgba(0,0,0,.18)", zIndex: 41, overflow: "hidden" }}>
                <div onClick={() => { setMenu(false); setTaskOpen(true); }} style={mItem}><Icon n="check" size={15} /> {t("+ Задача","+ Задача")}</div>
                {(active.assigned_to && active.assigned_to !== (me as any)?.id && !can("conversation.view.all"))
                  ? <div style={{ ...mItem, color: "#b45309", cursor: "default", background: "#fffbeb" }}><Icon n="pin" size={15} /> {t("Взято","Взято")}: {active.assigned_to_name}</div>
                  : <div onClick={takeConv} style={mItem}><Icon n="pin" size={15} /> {t("Закрепить за мной","Закріпити за мною")}</div>}
                <div onClick={() => { setMenu(false); setPicker("transfer"); }} style={mItem}><Icon n="forward" size={15} /> {t("Переадресовать","Переадресувати")}</div>
                <div onClick={() => { setMenu(false); setPicker("add"); }} style={mItem}><Icon n="user-plus" size={15} /> {t("Добавить менеджера","Додати менеджера")}</div>
                <div onClick={() => { setMenu(false); markUnreadFrom(active.id); }} style={mItem}><Icon n="eye" size={15} /> {t("Пометить неотвеченным","Позначити неотвеченим")}</div>
                {active.contact && <div onClick={goToContact} style={mItem}><Icon n="user" size={15} /> {t("Перейти в контакт","Перейти в контакт")}</div>}
                <div onClick={() => { setMenu(false); goToCard(); }} style={mItem}><Icon n="handshake" size={15} /> {((active as any).deal_id || active.contact) ? t("Перейти в сделку","Перейти в угоду") : t("Создать сделку из чата","Створити угоду з чату")}</div>
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
            {siblings.length > 0 && (
              <div style={{ padding: "6px 12px", borderBottom: "1px solid #eef2f7", background: "#fbfdff", display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, color: "#64748b", fontWeight: 600 }}>💬 {t("Клиент писал ещё:", "Клієнт писав ще:")}</span>
                {siblings.map((sib) => (
                  <button key={sib.id} onClick={() => openConv(sib)} title={sib.last_text || ""}
                    style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, padding: "3px 9px", borderRadius: 14, border: "1px solid #dbeafe", background: "#fff", cursor: "pointer", maxWidth: 240 }}>
                    <SourceChip source={sib.channel_kind} />
                    <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: "#475569" }}>{sib.channel_name}</span>
                    {(sib as any).unhandled_in > 0 && <span style={{ minWidth: 15, height: 15, borderRadius: 8, background: "#ef4444", color: "#fff", fontSize: 9.5, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 3px", flexShrink: 0 }}>{(sib as any).unhandled_in}</span>}
                  </button>
                ))}
              </div>
            )}
            <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
              <ConversationSourceCard card={(active as any)?.source_card} />
              {msgs.map((m, i) => (
                <Fragment key={m.id}>
                {(i === 0 || new Date((m as any).created_at).toDateString() !== new Date((msgs[i - 1] as any).created_at).toDateString()) && <div style={{ position: "sticky", top: 2, zIndex: 3, textAlign: "center", margin: "8px 0 6px", pointerEvents: "none" }}><span style={{ fontSize: 11, fontWeight: 700, color: "#475569", background: "#e2e8f0", borderRadius: 20, padding: "3px 13px", boxShadow: "0 1px 4px rgba(0,0,0,.14)" }}>{dayLabel((m as any).created_at, t)}</span></div>}
                <div id={`inbox-message-${m.id}`} className={"msg" + (m.direction === "out" ? " msg-out" : " msg-in")} data-internal={(m as any).internal ? "1" : ""}
                  style={{ maxWidth: "70%", padding: "9px 11px", borderRadius: 10, fontSize: 13,
                    alignSelf: m.direction === "out" ? "flex-end" : "flex-start",
                    background: (m as any).internal ? "#fef9c3" : "#fff",
                    color: "#0f172a",
                    border: (m as any).internal ? "1px dashed #d4a017" : (m.direction === "out" ? "1.5px solid #2563eb" : "1px solid #e8edf3"),
                    boxShadow: "0 1px 2px rgba(0,0,0,.05)" }}>
                  <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: .2, marginBottom: 4, paddingBottom: 3, borderBottom: (m as any).internal ? "1px solid rgba(212,160,23,.3)" : (m.direction === "out" ? "1px solid rgba(37,99,235,.25)" : "1px solid rgba(0,0,0,.08)"), color: (m as any).internal ? "#92400e" : (m.direction === "out" ? "#2563eb" : "var(--brand)") }}>
                    {(m as any).internal ? "📝 " + ((m as any).sender_display || SNDR_MAP[m.sender_name] || m.sender_name || t("Менеджер","Менеджер")) + " · " + t("только команда","тільки команда") : ((m as any).sender_display || SNDR_MAP[m.sender_name] || m.sender_name || (m.direction === "out" ? t("Менеджер","Менеджер") : (active?.title || t("Клиент","Клієнт"))))}
                  </div>
                  <ReplyContext attachments={m.attachments} idPrefix="inbox-message-" customLabels={{
                    reply: t("Ответ на", "Відповідь на"), client: t("Клиент", "Клієнт"), manager: t("Менеджер", "Менеджер"),
                    photo: t("Фото", "Фото"), video: t("Видео", "Відео"), voice: t("Голосовое сообщение", "Голосове повідомлення"),
                    file: t("Файл", "Файл"), unavailable: t("Исходное сообщение недоступно", "Початкове повідомлення недоступне"),
                    reaction: t("Реакция клиента", "Реакція клієнта"),
                  }} />
                  <span onClick={() => { if (m.direction === "in") setMsgMenu(msgMenu === m.id ? null : m.id); }}
                    style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", cursor: m.direction === "in" ? "pointer" : "default" }}>{linkify(m.text, m.direction === "out")}</span>
                  {msgMenu === m.id && m.direction === "in" && active && (
                    <div style={{ marginTop: 6 }}>
                      <button className="btn btn-light" style={{ height: 26, fontSize: 11.5 }}
                        onClick={(e) => { e.stopPropagation(); markUnreadFrom(active.id, m.id); }}>
                        👁 {t("Отметить непрочитанным с этого места", "Позначити непрочитаним з цього місця")}
                      </button>
                    </div>
                  )}
                  {m.attachments?.map((a: any, i: number) => (
                    isContextAttachment(a) ? null
                    : (a.url && a.type === "photo") ? <a key={i} href={a.url} target="_blank" rel="noreferrer" style={{ display: "block", marginTop: 6 }}><img src={a.url} alt="" style={{ maxWidth: 240, maxHeight: 260, borderRadius: 8, display: "block", objectFit: "cover" }} /></a>
                    : (a.url && a.type === "video") ? <video key={i} src={a.url} controls style={{ maxWidth: 240, borderRadius: 8, marginTop: 6, display: "block" }} />
                    : (a.url && a.type === "voice") ? <audio key={i} src={a.url} controls style={{ marginTop: 6, maxWidth: 240 }} />
                    : a.url ? <a key={i} href={a.url} target="_blank" rel="noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: 12.5, color: "#2563eb", fontWeight: 600 }}><Icon n="paperclip" size={14} /> {a.name || t("файл","файл")}</a>
                    : <div key={i} style={{ fontSize: 11, opacity: .8, marginTop: 4 }}><Icon n="paperclip" size={13} /> {a.type === "voice" ? t(`голосовое ${a.duration ?? ""}с`,`голосове ${a.duration ?? ""}с`) : a.type}</div>
                  ))}
                  <ReactionBadges attachments={m.attachments} customLabels={{ reaction: t("Реакция клиента", "Реакція клієнта") }} />
                  <div style={{ fontSize: 10, opacity: .55, marginTop: 3, textAlign: m.direction === "out" ? "right" : "left" }}>{(m as any).created_at ? new Date((m as any).created_at).toLocaleTimeString("uk", { hour: "2-digit", minute: "2-digit" }) : ""}</div>
                  {m.direction === "out" && !(m as any).internal && ((m as any).status === "window_risk" || (m as any).status === "failed") && <div style={{ fontSize: 10, fontWeight: 700, marginTop: 1, textAlign: "right", color: (m as any).status === "failed" ? "#b91c1c" : "#b45309" }}>{(m as any).status === "failed" ? "\u2717 " + t("не доставлено","не доставлено") : "⚠️ " + t("мог не дойти (окно закрыто)","міг не дійти (вікно закрите)")}</div>}
                </div>
                </Fragment>
              ))}
              <div ref={endRef} />
            </div>
            {err && <div className="err" style={{ padding: "0 16px" }}>{err}</div>}
            <div style={{ background: "#fff", borderTop: "1px solid #e2e8f0", padding: "0 12px 12px" }}>
              <div onMouseDown={startResizeComposer} title={t("Потяни вверх — увеличить поле ввода","Потягни вгору — збільшити поле введення")} style={{ height: 13, cursor: "ns-resize", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div style={{ width: 44, height: 4, borderRadius: 4, background: "#cbd5e1" }} />
              </div>
              {pending.length > 0 && <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 7 }}>
                {pending.map((att: any, i: number) => (
                  <div key={i} style={{ position: "relative", border: "1px solid #e2e8f0", borderRadius: 8, background: "#f8fafc", padding: att.kind === "photo" ? 0 : "8px 12px", display: "flex", alignItems: "center", gap: 6 }}>
                    {att.kind === "photo" ? <img src={att.dataURL} alt="" style={{ height: 54, maxWidth: 90, borderRadius: 8, objectFit: "cover", display: "block" }} /> : <span style={{ fontSize: 12, color: "#475569", display: "inline-flex", alignItems: "center", gap: 5 }}><Icon n="file" size={15} /> {att.name.slice(0, 24)}</span>}
                    <button type="button" onClick={() => setPending((p) => p.filter((_: any, j: number) => j !== i))} title={t("Убрать","Прибрати")} style={{ position: "absolute", top: -7, right: -7, width: 18, height: 18, borderRadius: "50%", background: "#dc2626", color: "#fff", border: "none", cursor: "pointer", fontSize: 11, lineHeight: "16px", padding: 0 }}>✕</button>
                  </div>
                ))}
              </div>}
              {internalNote && <div style={{ background: "#fef9c3", color: "#854d0e", fontSize: 11.5, fontWeight: 600, padding: "5px 10px", borderRadius: 6, marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}><Icon n="eye" size={14} /> {t("Режим заметки — клиент НЕ увидит, видят только менеджеры","Режим нотатки — клієнт НЕ побачить, бачать лише менеджери")}</div>}
              {(() => { const w = metaWindow(active, msgs); return w && w.closed ? <div style={{ background: "#fee2e2", color: "#b91c1c", fontSize: 11.5, fontWeight: 600, padding: "6px 10px", borderRadius: 6, marginBottom: 6, lineHeight: 1.35 }}>⚠️ {t("Окно Instagram закрыто (прошло " + w.hrs + "ч). Сообщение может НЕ дойти — дождись ответа клиента или напиши с другого канала.","Вікно Instagram закрите (минуло " + w.hrs + "г). Повідомлення може НЕ дійти — дочекайся відповіді клієнта або напиши з іншого каналу.")}</div> : null; })()}
              <div style={{ display: "flex", gap: 6, alignItems: "flex-end" }}>
              <input ref={fileRef} type="file" hidden onChange={sendFile} />
              <button className="btn" type="button" style={{ background: internalNote ? "#fde68a" : "#f1f5f9", color: internalNote ? "#92400e" : "#475569", fontWeight: internalNote ? 700 : 400, flex: "0 0 auto", height: 38 }} title={t("Скрытая заметка для менеджеров (клиент не увидит)","Прихована нотатка для менеджерів (клієнт не побачить)")} onClick={() => setInternalNote((v) => !v)}><Icon n="eye" size={17} /></button>
              <EmojiButton onPick={(em) => setText((tx) => tx + em)} />
              <button className="btn" type="button" style={{ background: "#f1f5f9", flex: "0 0 auto", height: 38 }} title={t("Прикрепить файл / фото / видео / документ","Прикріпити файл / фото / відео / документ")} onClick={() => fileRef.current?.click()} disabled={sending}><Icon n="paperclip" size={17} /></button>
              <textarea value={text} rows={1}
                onChange={(e) => { setText(e.target.value); if (composerH === null) { e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 170) + "px"; } }}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                onPaste={onPasteFile}
                placeholder={internalNote ? (compact ? t("Внутренняя заметка…","Внутрішня нотатка…") : t("Внутренняя заметка — клиент НЕ увидит…  (Enter — отправить, Shift+Enter — новая строка)","Внутрішня нотатка — клієнт НЕ побачить…  (Enter — надіслати, Shift+Enter — новий рядок)")) : (compact ? t(`Сообщение в ${active.channel_name}…`,`Повідомлення в ${active.channel_name}…`) : t(`Сообщение в ${active.channel_name}…  (Enter — отправить, Shift+Enter — строка, вставить фото — Ctrl+V)`,`Повідомлення в ${active.channel_name}…  (Enter — надіслати, Shift+Enter — рядок, вставити фото — Ctrl+V)`))}
                style={{ flex: 1, minHeight: 38, height: composerH ? composerH + "px" : undefined, maxHeight: composerH ? undefined : 170, background: internalNote ? "#fffbeb" : "#f1f5f9", border: internalNote ? "1.5px dashed #d4a017" : "none", borderRadius: 7, padding: "9px 12px", fontSize: 13, outline: "none", resize: "none", lineHeight: 1.4, fontFamily: "inherit", boxSizing: "border-box" }} />
              <AiComposeAssist draft={text} convId={active.id} onApply={setText} compact t={t} />
              <button className="btn btn-primary" onClick={send} disabled={sending} title={internalNote ? t("Заметка","Нотатка") : t("Отправить","Надіслати")} style={{ background: internalNote ? "#d4a017" : undefined, height: 38, padding: compact ? "0 11px" : undefined }}>{sending ? "…" : (internalNote ? <><Icon n="file" size={15} />{!compact && <> {t("Заметка","Нотатка")}</>}</> : <><Icon n="send" size={16} />{!compact && <> {t("Отправить","Надіслати")}</>}</>)}</button>
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
      }
      {dealDrawer && (
        <div onClick={() => { setDealDrawer(null); refreshList(); }} className="deal-drawer-bg" style={{ position: "fixed", inset: 0, zIndex: 300, background: "rgba(15,23,42,.35)" }}>
          <div onClick={(e) => e.stopPropagation()} className="deal-drawer" style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: "90%", background: "var(--bg, #f3efe9)", boxShadow: "-10px 0 40px rgba(0,0,0,.3)", overflowY: "auto" }}>
            <DealCard dealId={dealDrawer} onClose={() => { setDealDrawer(null); refreshList(); }} />
          </div>
        </div>
      )}
    </div>
  );
}

function FitChips({ children }: any) {
  const inner = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const el = inner.current;
    if (!el || !el.parentElement) return;
    const fit = () => {
      const parent = el.parentElement;
      if (!parent) return;
      const avail = parent.clientWidth, natural = el.scrollWidth;
      if (avail > 4 && natural > 0) setScale(natural > avail ? Math.max(0.6, avail / natural) : 1);
    };
    const raf = requestAnimationFrame(fit);
    const ro = new ResizeObserver(fit);
    ro.observe(el.parentElement);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  }, []);
  return (
    <div style={{ overflow: "hidden", marginTop: 3 }}>
      <div ref={inner} style={{ display: "inline-flex", gap: 4, whiteSpace: "nowrap", transformOrigin: "left center", transform: scale < 0.999 ? `scale(${scale})` : undefined }}>
        {children}
      </div>
    </div>
  );
}





function NotifFeed({ t, onOpen, nav }: any) {
  const [items, setItems] = useState<any[]>([]);
  const [load, setLoad] = useState(true);
  useEffect(() => { api.get<any>("/api/inbox/notifications/").then((d) => setItems(d.items || [])).catch(() => {}).finally(() => setLoad(false)); }, []);
  const fmt = (s: string) => s ? new Date(s).toLocaleString("uk", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
  return (
    <div className="scroll" style={{ flex: 1, minHeight: 0, padding: 16, background: "#f8fafc" }}>
      <div style={{ maxWidth: 760, margin: "0 auto" }}>
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>{t("Новые сообщения клиентов и звонки. Системные события появятся здесь же.", "Нові повідомлення клієнтів і дзвінки. Системні події з\u02bcявляться тут же.")}</div>
        {load && <div className="spin">{t("Загрузка…", "Завантаження…")}</div>}
        {!load && items.length === 0 && <div className="note">{t("Пока нет уведомлений.", "Поки немає сповіщень.")}</div>}
        {items.map((it, i) => (
          <div key={i} onClick={() => (it.type === "message" || it.type === "added") ? onOpen(it.conv_id) : (it.deal_id && nav(`/deals/${it.deal_id}`))}
            style={{ display: "flex", gap: 11, alignItems: "flex-start", background: "#fff", border: "1px solid #eef2f7", borderRadius: 12, padding: "11px 13px", marginBottom: 8, cursor: "pointer" }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: it.type === "call" ? "#ecfdf5" : "#eff6ff", color: it.type === "call" ? "#16a34a" : "#2563eb" }}>
              <Icon n={it.type === "call" ? "phone" : it.type === "added" ? "user-plus" : "message"} size={17} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <b style={{ fontSize: 13.5 }}>{it.name}</b>
                {it.type === "message" && it.unread > 0 && <span style={{ background: "#dc2626", color: "#fff", borderRadius: 20, fontSize: 10.5, fontWeight: 700, padding: "0 6px" }}>{it.unread}</span>}
                <div style={{ flex: 1 }} />
                <span className="muted" style={{ fontSize: 11 }}>{fmt(it.at)}</span>
              </div>
              <div className="muted" style={{ fontSize: 12.5, marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {it.type === "message" ? (it.preview || t("(вложение)", "(вкладення)")) : `${it.direction === "in" ? t("Входящий", "Вхідний") : it.direction === "out" ? t("Исходящий", "Вихідний") : t("Пропущенный", "Пропущений")} · ${it.line || "—"} · ${Math.round((it.duration || 0) / 60)} ${t("мин", "хв")}`}
              </div>
              <div className="muted" style={{ fontSize: 10.5, marginTop: 2 }}>{it.type === "message" ? "💬 " + (it.channel || t("сообщение", "повідомлення")) : "📞 " + t("звонок", "дзвінок")}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
