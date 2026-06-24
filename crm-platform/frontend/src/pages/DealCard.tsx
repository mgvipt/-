/* ============================================================================
 *  КАРТОЧКА СДЕЛКИ  —  frontend/src/pages/DealCard.tsx
 * ----------------------------------------------------------------------------
 *  Открывается по клику на сделку в канбане (Board.tsx → /deals/:id).
 *  Документация: docs/CODEMAP.md  → разд. 3 (экран) и разд. 4 («где менять»).
 *
 *  СТРУКТУРА ФАЙЛА (ищи по номеру блока):
 *    [1] ТИПЫ            — интерфейсы Deal / Item / Pay / Product
 *    [2] ХЕЛПЕРЫ         — формат чисел, стили чипов
 *    [3] STATE           — состояние компонента
 *    [4] ЗАГРУЗКА        — load() сделки и справочников
 *    [5] ДЕЙСТВИЯ        — стадия, оплата, отгрузка, ТТН, чек (API-вызовы)
 *    [6] ВЫЧИСЛЯЕМОЕ     — остаток, скидка, лента событий
 *    [7] РЕНДЕР: шапка   — название, отгрузка, тосты
 *    [8] РЕНДЕР: стадии  — полоса стадий + дни на текущей
 *    [9] РЕНДЕР: действия— быстрые кнопки (оплата/ТТН/чек)
 *    [10] РЕНДЕР: левая  — клиент, сумма, скидка, доставка, маржа, ответственный
 *    [11] РЕНДЕР: правая — лента событий ИЛИ товары
 *    [12] РЕНДЕР: модалка— приём оплаты
 *    [13] СУБ-КОМПОНЕНТЫ — chip(), Inline (инлайн-редактор поля)
 *
 *  КАК ДОБАВИТЬ КНОПКУ-ДЕЙСТВИЕ: функция в [5] (api.post .../action/) + кнопка в [9].
 *  КАК ДОБАВИТЬ ПОЛЕ СДЕЛКИ: тип в [1] + строка в нужном блоке-панели [10].
 * ========================================================================== */

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, Funnel, Paginated } from "../api";
import OwnerSelect from "../OwnerSelect";
import { Avatar } from "../ui";
import NeedsForm from "../NeedsForm";
import CardFields from "../CardFields";
import ClientChat from "../ClientChat";
import ActivityLog from "../ActivityLog";
import CallButton from "../CallButton";
import KpDoc from "../KpDoc";
import { useLang } from "../i18n";

/* ─── [1] ТИПЫ ─────────────────────────────────────────────────────────── */

interface Item { id: number; product: number; product_name: string; quantity: string; price: string; discount_pct?: string; discount_sum?: string; total: string; reserved?: boolean; product_stock?: number | null; }
interface Pay { id: number; provider: string; amount: string; is_paid: boolean; created_at: string; }
interface Deal {
  qualification?: any; card_fields?: any[];
  id: number; title: string; contact_name?: string; owner_name?: string; owner?: number | null;
  funnel: number; stage: number; amount: string; source: string;
  items: Item[]; payments: Pay[]; paid: number;
  // поля merge-карточки (см. CODEMAP разд.2, модель Deal):
  discount_pct?: string; pay_type?: string; ttn?: string; checkbox_status?: string;
  margin?: number; bonus?: { total: number; from_revenue: number; from_margin: number; revenue_pct: number; margin_pct: number }; days_in_stage?: number;
  contact_loyalty?: string; contact_id?: number; conversation_id?: number | null; b24_id?: string;
}
interface Product { id: number; name: string; price: string; stock: number; }

/* ─── [2] ХЕЛПЕРЫ ──────────────────────────────────────────────────────── */

const fmt = (n: number) => Number(n || 0).toLocaleString("ru");
const LOYALTY_COLOR: Record<string, string> = { VIP: "#7c3aed", Активный: "#2563eb", Новый: "#16a34a", Спящий: "#64748b" };
const editInp: any = { width: 62, height: 28, borderRadius: 6, border: "1px solid #cbd5e1", padding: "0 6px", fontSize: 12 };
const rowTot: any = { display: "flex", justifyContent: "space-between", padding: "3px 0", gap: 24 };

export default function DealCard({ dealId, onClose }: { dealId?: number; onClose?: () => void } = {}) {

  /* ─── [3] STATE ──────────────────────────────────────────────────────── */
  const params = useParams();
  const id = dealId != null ? String(dealId) : params.id;
  const nav = useNavigate();
  const [deal, setDeal] = useState<Deal | null>(null);
  const { t } = useLang();
  const [chatW, setChatW] = useState(() => Number(localStorage.getItem("crm_card_chatW")) || 360);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [tab, setTab] = useState<"general" | "items" | "cashflow">("general");
  const [docOpen, setDocOpen] = useState(false);
  const [addProd, setAddProd] = useState(0);
  const [addQty, setAddQty] = useState(1);
  const [psearch, setPsearch] = useState(""); const [presults, setPresults] = useState<Product[]>([]); const [psel, setPsel] = useState<Product | null>(null); const [addReserve, setAddReserve] = useState(false); const [showList, setShowList] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [payAmount, setPayAmount] = useState("");
  const [msg, setMsg] = useState("");
  const [chat, setChat] = useState<{ id: number; direction: string; text: string; created_at: string }[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [ai, setAi] = useState<{ context: string; suggestion: string } | null>(null);
  const [aiLoad, setAiLoad] = useState(false);
  const [ncOpen, setNcOpen] = useState(false);
  const [nc, setNc] = useState({ name: "", phone: "", email: "" });
  const [ncMode, setNcMode] = useState<"pick" | "new">("pick");
  const [ncSearch, setNcSearch] = useState(""); const [ncResults, setNcResults] = useState<any[]>([]);
  const [cliEdit, setCliEdit] = useState(false);
  const [cliSearch, setCliSearch] = useState(""); const [cliResults, setCliResults] = useState<any[]>([]);
  const [cliNew, setCliNew] = useState(false); const [cliN, setCliN] = useState({ name: "", phone: "" });

  /* ─── [4] ЗАГРУЗКА ───────────────────────────────────────────────────── */
  async function load() {
    try {
      const d = await api.get<Deal>(`/api/deals/${id}/`);
      setDeal(d);
      if (!funnel || funnel.id !== d.funnel) setFunnel(await api.get<Funnel>(`/api/funnels/${d.funnel}/`));
    } catch { setNotFound(true); }
  }
  useEffect(() => {
    load();
    api.get<Paginated<Product>>("/api/products/?page_size=200").then((p) => setProducts(p.results));
  }, [id]);
  useEffect(() => {
    if (deal?.conversation_id) api.get<any>(`/api/conversations/${deal.conversation_id}/messages/`).then(setChat).catch(() => setChat([]));
    else setChat([]);
  }, [deal?.conversation_id]);

  /* ─── [5] ДЕЙСТВИЯ ───────────────────────────────────────────────────── */
  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 2800); };
  async function patch(body: Record<string, unknown>) { await api.patch(`/api/deals/${id}/`, body); load(); }

  // Перетягування правого краю → ширина чату (спільна для всіх карток CRM)
  function startResize(e: any) {
    e.preventDefault();
    const startX = e.clientX, startW = chatW; let w = startW;
    function mv(ev: MouseEvent) { w = Math.min(760, Math.max(280, startW + (startX - ev.clientX))); setChatW(w); }
    function up() { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); localStorage.setItem("crm_card_chatW", String(w)); }
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }

  async function setStage(stageId: number) { await patch({ stage: stageId }); }

  async function addItem(prod?: Product) {
    const p = prod && (prod as any).id ? prod : psel;   // двойной клик передаёт товар напрямую, иначе берём выбранный
    if (!p) return;
    setDeal(await api.post<Deal>(`/api/deals/${id}/add_item/`, { product: p.id, quantity: addQty, reserved: addReserve }));
    setPsel(null); setPsearch(""); setPresults([]); setAddQty(1); setAddReserve(false);
  }
  useEffect(() => {
    if (!psearch.trim() || psel) { setPresults([]); return; }
    const t = setTimeout(() => api.get<Paginated<Product>>(`/api/products/?search=${encodeURIComponent(psearch)}&page_size=12`).then((d) => setPresults(d.results)).catch(() => setPresults([])), 250);
    return () => clearTimeout(t);
  }, [psearch, psel]);
  async function toggleReserve(it: any) {
    setDeal(await api.post<Deal>(`/api/deals/${id}/set_reserve/`, { item: it.id, reserved: !it.reserved }));
  }
  async function updateItem(itemId: number, body: any) {
    setDeal(await api.post<Deal>(`/api/deals/${id}/update_item/`, { item: itemId, ...body }));
  }
  async function removeItem(item: number) { setDeal(await api.post<Deal>(`/api/deals/${id}/remove_item/`, { item })); }

  async function acceptPayment() {
    setDeal(await api.post<Deal>(`/api/deals/${id}/accept_payment/`, { amount: payAmount || deal?.amount }));
    setPayOpen(false); setPayAmount(""); flash(t("✓ Оплата проведена в финансы","✓ Оплата проведена у фінанси"));
  }
  async function ship() {
    try { const r = await api.post<any>(`/api/deals/${id}/ship/`, {}); setDeal(r.deal); flash(t(`✓ Отгружено. Себестоимость ${r.cogs} ₴ списана`, `✓ Відвантажено. Собівартість ${r.cogs} ₴ списана`)); }
    catch { flash(t("В сделке нет товаров для отгрузки","У сделке немає товарів для відвантаження")); }
  }
  // TODO боевой режим: завести @action в DealViewSet поверх integrations/adapters.py
  //      (np_create_ttn / checkbox_create_receipt / liqpay_checkout_link). Сейчас — заглушки.
  async function createTTN() { await patch({ ttn: "НП " + Math.floor(2e13 + Math.random() * 1e13) }); flash(t("✓ ТТН Нова Пошта создана","✓ ТТН Нова Пошта створена")); }
  async function issueCheckbox() { await patch({ checkbox_status: deal?.paid && deal.paid < Number(deal.amount) ? "аванс" : "финальный" }); flash(t("✓ Чек Checkbox сформирован","✓ Чек Checkbox сформовано")); }
  function sendPayLink() { flash(t("✓ Ссылка на оплату отправлена клиенту · cashflow.wallcovdec.com.ua","✓ Посилання на оплату надіслано клієнту · cashflow.wallcovdec.com.ua")); }
  useEffect(() => {
    if (!ncOpen || ncMode !== "pick" || !ncSearch.trim()) { setNcResults([]); return; }
    const t = setTimeout(() => api.get<any>(`/api/contacts/?search=${encodeURIComponent(ncSearch)}&page_size=8`).then((d) => setNcResults(d.results || d)).catch(() => setNcResults([])), 250);
    return () => clearTimeout(t);
  }, [ncOpen, ncMode, ncSearch]);
  async function linkExisting(cid: number) {
    await api.patch(`/api/deals/${id}/`, { contact: cid });
    setNcOpen(false); setNcSearch(""); setNcResults([]); load();
  }
  useEffect(() => {
    if (!cliSearch.trim()) { setCliResults([]); return; }
    const t = setTimeout(() => api.get<any>(`/api/contacts/?search=${encodeURIComponent(cliSearch)}&page_size=8`).then((d) => setCliResults(d.results || d)).catch(() => setCliResults([])), 250);
    return () => clearTimeout(t);
  }, [cliSearch]);
  async function setContact(cid: number) { await api.patch(`/api/deals/${id}/`, { contact: cid }); setCliEdit(false); setCliSearch(""); setCliResults([]); setCliNew(false); load(); }
  async function removeContact() { if (!confirm(t("Убрать клиента из сделки?","Прибрати клієнта зі сделки?"))) return; await api.patch(`/api/deals/${id}/`, { contact: null }); load(); }
  async function createInlineClient() { const p = cliN.name.trim().split(/\s+/); const c = await api.post<any>("/api/contacts/", { first_name: p[0] || cliN.name.trim(), last_name: p.slice(1).join(" "), phone: cliN.phone }); setContact(c.id); setCliN({ name: "", phone: "" }); }
  async function createClient() {
    const parts = nc.name.trim().split(" ");
    const contact = await api.post<{ id: number }>(`/api/contacts/`, { first_name: parts[0] || nc.name, last_name: parts.slice(1).join(" "), phone: nc.phone, email: nc.email });
    await api.patch(`/api/deals/${id}/`, { contact: contact.id });
    setNcOpen(false); setNc({ name: "", phone: "", email: "" }); load();
  }
  async function sendChat() {
    if (!draft.trim() || !deal?.conversation_id) { if (!deal?.conversation_id) flash(t("Нет активного чата с клиентом","Немає активного чату з клієнтом")); return; }
    setSending(true);
    try {
      const m = await api.post<any>(`/api/conversations/${deal.conversation_id}/send/`, { text: draft.trim() });
      setChat((c) => [...c, m]); setDraft("");
    } catch { flash(t("Не удалось отправить (канал/токен)","Не вдалося відправити (канал/токен)")); }
    finally { setSending(false); }
  }
  async function aiSuggest() {
    setAiLoad(true); setAi(null);
    try { setAi(await api.post<any>(`/api/deals/${id}/ai_suggest/`, {})); }
    catch { flash(t("AI недоступен","AI недоступний")); }
    finally { setAiLoad(false); }
  }

  /* ─── [6] ВЫЧИСЛЯЕМОЕ ────────────────────────────────────────────────── */
  if (notFound) return <div className="scroll pad fade"><div className="panel" style={{ textAlign: "center", padding: 40 }}><h3>{t("Сделка не найдена","Сделку не знайдено")}</h3><div className="muted" style={{ marginBottom: 16 }}>{t("Возможно, она удалена или изменён ID после переноса из Битрикса. Открой из списка сделок.","Можливо, її видалено або змінено ID після перенесення з Бітрикса. Відкрий зі списку сделок.")}</div><button className="btn btn-primary" onClick={() => nav("/deals")}>{t("← К списку сделок","← До списку сделок")}</button></div></div>;
  if (!deal) return <div className="spin">{t("Загрузка сделки…","Загрузка сделки…")}</div>;
  const curOrder = funnel?.stages.find((s) => s.id === deal.stage)?.order ?? 0;
  const remaining = Number(deal.amount) - deal.paid;
  const disc = Number(deal.discount_pct || 0);
  const loyalty = deal.contact_loyalty || "";
  const hasCheck = !!deal.checkbox_status && deal.checkbox_status !== "none";
  // Лента событий из реальных данных (оплаты + системное «создана»):
  const events = [
    ...deal.payments.map((p) => ({ t: p.created_at, kind: "pay", text: t(`Оплата ${fmt(Number(p.amount))} ₴ · ${p.provider}`, `Оплата ${fmt(Number(p.amount))} ₴ · ${p.provider}`) })),
    { t: deal.payments[0]?.created_at || "", kind: "sys", text: t("Сделка создана","Сделка створена") },
  ].filter((e) => e.t);

  return (
    <div className="scroll fade">

      {/* ─── [7] РЕНДЕР: шапка ─────────────────────────────────────────── */}
      <div className="dealhead">
        <button className="back" onClick={() => onClose ? onClose() : nav("/deals")}>←</button>
        <b style={{ fontSize: 16 }}><span title={t("Клик — скопировать № (идентификатор для оплат)","Клік — скопіювати № (ідентифікатор для оплат)")} style={{ cursor: "pointer" }} onClick={() => { navigator.clipboard?.writeText(String(deal.id)); flash(t("№ "+deal.id+" скопирован","№ "+deal.id+" скопійовано")); }}>#{deal.id}</span> · {deal.title}</b>
        <button className="btn" title={t("Скопировать ссылку на сделку","Скопіювати лінк на сделку")} onClick={() => { navigator.clipboard?.writeText(window.location.origin+"/deals/"+deal.id); flash(t("Ссылка скопирована","Лінк скопійовано")); }}>🔗</button>
        <span className="muted">{funnel?.name}</span>
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        {deal.contact_id && <CallButton contact={deal.contact_id} small />}
        <button className="btn btn-green" onClick={ship}>{t("📦 Отгрузить","📦 Відвантажити")}</button>
      </div>

      {/* ─── [8] РЕНДЕР: стадии (клик = смена, на текущей — дни) ────────── */}
      {funnel && (
        <div className="stagebar">
          {funnel.stages.map((s) => {
            const cur = s.id === deal.stage;
            return (
              <div key={s.id} className="stage" onClick={() => setStage(s.id)}
                style={{ cursor: "pointer", background: s.order <= curOrder ? "var(--brand)" : "#cbd5e1" }}>
                {s.name}{cur && deal.days_in_stage != null ? t(` · ${deal.days_in_stage}д`, ` · ${deal.days_in_stage}д`) : ""}
              </div>
            );
          })}
        </div>
      )}

      {/* ─── [9] РЕНДЕР: єдина панель — вкладки + дії (dealbar-unified) ──── */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", margin: "12px 0", padding: "8px 10px", background: "linear-gradient(90deg,#f8fafc,#eef2ff)", borderRadius: 10, border: "1px solid #e2e8f0" }}>
        <button className={"btn" + (tab === "general" ? " btn-primary" : "")} onClick={() => setTab("general")}>{t("💬 Лента / Чат","💬 Стрічка / Чат")}</button>
        <button className={"btn" + (tab === "items" ? " btn-primary" : "")} onClick={() => setTab("items")}>{t("📦 Товары","📦 Товари")} ({deal.items.length})</button>
        <button className={"btn" + (tab === "cashflow" ? " btn-primary" : "")} onClick={() => setTab("cashflow")}>{t("💰 Cashflow","💰 Cashflow")}</button>
        <div style={{ width: 1, height: 24, background: "#cbd5e1", margin: "0 6px" }} />
        <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>{t("Действия:","Дії:")}</span>
        <button className="btn" onClick={sendPayLink}>{t("💳 Оплата","💳 Оплата")}</button>
        <button className="btn" onClick={createTTN}>{t("🚚 ТТН","🚚 ТТН")}</button>
        <button className="btn" onClick={issueCheckbox}>{t("🧾 Checkbox","🧾 Checkbox")}</button>
      </div>

      {tab !== "cashflow" ? (
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div className="grid2" style={{ flex: 1, minWidth: 0 }}>

        {/* ─── [10] РЕНДЕР: левая колонка — данные заказа ───────────────── */}
        <div>
          {/* 10.1 Клиент — інлайн вибір/зміна/прибирання (без попапів) */}
          <div className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="label">{t("Клиент","Клієнт")}</div>
              {deal.contact_id && !cliEdit && (
                <span style={{ fontSize: 11, display: "flex", gap: 10 }}>
                  <span style={{ color: "#2563eb", cursor: "pointer" }} onClick={() => { setCliEdit(true); setCliNew(false); }}>{t("✏️ Изменить","✏️ Змінити")}</span>
                  <span style={{ color: "#dc2626", cursor: "pointer" }} onClick={removeContact}>{t("✕ Убрать","✕ Прибрати")}</span>
                </span>
              )}
            </div>
            {deal.contact_id && !cliEdit ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600 }}>{deal.contact_name || t("Без контакта","Без контакту")}</span>
                  {loyalty && <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: (LOYALTY_COLOR[loyalty] || "#64748b") + "22", color: LOYALTY_COLOR[loyalty] || "#64748b" }}>{loyalty}</span>}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  <button className="btn" style={{ flex: 1, background: "#ecfdf5", color: "#047857" }}>{t("📞 Позвонить","📞 Подзвонити")}</button>
                  <button className="btn" style={{ flex: 1, background: "#eff6ff", color: "#1d4ed8" }} onClick={() => deal.conversation_id ? nav(`/inbox?c=${deal.conversation_id}`) : setTab("general")}>{t("💬 Чат","💬 Чат")}</button>
                  <button className="btn" style={{ background: "#f1f5f9" }} title={t("Карточка клиента","Картка клієнта")} onClick={() => nav(`/clients/${deal.contact_id}`)}>{t("Клиент →","Клієнт →")}</button>
                </div>
              </>
            ) : (
              <div style={{ marginTop: 6 }}>
                <input value={cliSearch} autoFocus onChange={(e) => setCliSearch(e.target.value)} placeholder={t("🔍 Телефон или имя клиента…","🔍 Телефон або імʼя клієнта…")} style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px" }} />
                {cliResults.length > 0 && (
                  <div style={{ maxHeight: 200, overflowY: "auto", marginTop: 6, border: "1px solid #e2e8f0", borderRadius: 8 }}>
                    {cliResults.map((c) => (
                      <div key={c.id} onClick={() => setContact(c.id)} style={{ padding: "7px 9px", borderBottom: "1px solid #f1f5f9", cursor: "pointer", fontSize: 13 }}>
                        👤 <b>{c.display_name || `${c.first_name || ""} ${c.last_name || ""}`.trim() || "—"}</b> {c.phone ? <span className="muted">· {c.phone}</span> : null}
                      </div>
                    ))}
                  </div>
                )}
                {cliSearch.trim() && cliResults.length === 0 && <div className="muted" style={{ fontSize: 12, padding: "6px 0" }}>{t("Не найдено — создай нового ниже.","Не знайдено — створи нового нижче.")}</div>}
                {!cliNew ? (
                  <div style={{ display: "flex", gap: 10, marginTop: 8, fontSize: 12 }}>
                    <span style={{ color: "#16a34a", cursor: "pointer" }} onClick={() => setCliNew(true)}>{t("➕ Создать нового","➕ Створити нового")}</span>
                    {deal.contact_id && <span style={{ color: "#64748b", cursor: "pointer", marginLeft: "auto" }} onClick={() => { setCliEdit(false); setCliSearch(""); }}>{t("Отменить","Скасувати")}</span>}
                  </div>
                ) : (
                  <div style={{ marginTop: 8 }}>
                    <input value={cliN.name} onChange={(e) => setCliN({ ...cliN, name: e.target.value })} placeholder={t("Имя и фамилия","Імʼя та прізвище")} style={{ width: "100%", height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 9px", marginBottom: 6 }} />
                    <input value={cliN.phone} onChange={(e) => setCliN({ ...cliN, phone: e.target.value })} placeholder="+380…" style={{ width: "100%", height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 9px", marginBottom: 6 }} />
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="btn btn-light" style={{ flex: 1, fontSize: 12 }} onClick={() => setCliNew(false)}>{t("Назад","Назад")}</button>
                      <button className="btn btn-primary" style={{ flex: 1, fontSize: 12 }} onClick={createInlineClient} disabled={!cliN.name.trim()}>{t("Создать","Створити")}</button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 10.2 Сумма / оплачено / осталось (сумма — инлайн-edit) */}
          <div className="panel">
            <div className="label">{t("Сумма сделки","Сума сделки")}</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              <Inline value={Number(deal.amount)} fmt={(v) => fmt(v) + t(" грн."," грн.")} onSave={(v) => patch({ amount: v })} />
            </div>
            <div className="row" style={{ marginTop: 8 }}><span className="muted">{t("Оплачено","Оплачено")}</span><b style={{ color: "#16a34a" }}>{fmt(deal.paid)} ₴</b></div>
            <div className="row"><span className="muted">{t("Осталось","Залишилось")}</span><b style={{ color: remaining > 0 ? "#d97706" : "#16a34a" }}>{fmt(remaining)} ₴</b></div>
            <button className="btn btn-primary" style={{ width: "100%", height: 36, marginTop: 10 }} onClick={() => { setPayAmount(String(remaining > 0 ? remaining : deal.amount)); setPayOpen(true); }}>{t("💳 Принять оплату","💳 Прийняти оплату")}</button>
          </div>
          <ActivityLog kind="deal" id={deal.id} />

          {/* 10.3 Скидка (инлайн-edit) + авто-рекомендация для VIP */}
          <div className="panel">
            <div className="label">{t("Скидка","Знижка")}</div>
            <div className="row"><span className="muted">{t("Текущая","Поточна")}</span><b><Inline value={disc} fmt={(v) => v + " %"} onSave={(v) => patch({ discount_pct: v })} /></b></div>
            {loyalty === "VIP" && disc < 10 && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginTop: 8, background: "#ecfdf5", color: "#047857", padding: "7px 9px", borderRadius: 8, fontSize: 12 }}>
                <span>{t("VIP: при полной оплате доступно 10%","VIP: при повній оплаті доступно 10%")}</span>
                <button className="btn" style={{ padding: "3px 8px" }} onClick={() => patch({ discount_pct: 10 })}>{t("Применить","Застосувати")}</button>
              </div>
            )}
          </div>

          {/* 10.4 Доставка и документы (ТТН / чек + бейджи) */}
          <div className="panel">
            <div className="label">{t("Доставка и документы","Доставка і документи")}</div>
            <div className="row"><span className="muted">{t("ТТН Нова Пошта","ТТН Нова Пошта")}</span><b>{deal.ttn || "—"}</b></div>
            <div className="row"><span className="muted">{t("Чек Checkbox","Чек Checkbox")}</span><b>{hasCheck ? deal.checkbox_status : "—"}</b></div>
            <div style={{ marginTop: 6, display: "flex", gap: 6 }}>
              <span style={chip(hasCheck)}>{t("Чек","Чек")} {hasCheck ? "✓" : "—"}</span>
              <span style={chip(!!deal.ttn)}>{t("ТТН","ТТН")} {deal.ttn ? "✓" : "—"}</span>
            </div>
          </div>

          {/* 10.5 Маржа + бонус менеджера (для руководителя) */}
          <div className="panel">
            <div className="label">{t("Маржа (видит РОП / руководитель)","Маржа (бачить РОП / керівник)")}</div>
            <div className="row"><span className="muted">{t("Маржа","Маржа")}</span><b>{fmt(deal.margin || 0)} ₴{deal.margin && Number(deal.amount) ? ` · ${Math.round((deal.margin / Number(deal.amount)) * 100)}%` : ""}</b></div>
            <div className="row" title={deal.bonus ? t(`${deal.bonus.revenue_pct}% с оборота + ${deal.bonus.margin_pct}% с маржи. Ставки меняются в Финмодели → ЗП.`, `${deal.bonus.revenue_pct}% з обороту + ${deal.bonus.margin_pct}% з маржі. Ставки міняються у Фінмоделі → ЗП.`) : ""}><span className="muted">{t("💰 Бонус менеджера со сделки","💰 Бонус менеджера з угоди")}</span><b style={{ color: "#1d4ed8" }}>{fmt(deal.bonus?.total || 0)} ₴</b></div>
            {deal.bonus && <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{deal.bonus.revenue_pct}{t("% оборота = ","% обороту = ")}{fmt(deal.bonus.from_revenue)} ₴ + {deal.bonus.margin_pct}{t("% маржи = ","% маржі = ")}{fmt(deal.bonus.from_margin)} ₴</div>}
          </div>

          {/* 10.6 Ответственный */}
          <div className="panel">
            <div className="label">{t("Ответственный","Відповідальний")}</div>
            <OwnerSelect ownerId={deal.owner} ownerName={deal.owner_name} onSet={(uid) => patch({ owner: uid })} />
          </div>
        </div>

        {/* ─── [11] РЕНДЕР: правая колонка — лента ИЛИ товары ───────────── */}
        <div>
          {tab === "general" ? (
            <>
              <NeedsForm leadId={deal.id} initial={deal.qualification} endpoint="/api/deals/" />
              <CardFields leadId={deal.id} initial={deal.card_fields} endpoint="/api/deals/" />

            </>
          ) : (
            /* 11.2 Товары в сделке (добавить/удалить → пересчёт суммы на бэке) */
            <div className="panel">
              <div className="label" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span>{t("Товары в сделке","Товари у сделке")}</span>
                <button className="btn" onClick={() => setDocOpen(true)} title={t("Сформировать документ КП","Сформувати документ КП")}>📄 {t("Документ","Документ")}</button>
              </div>
              <div className="prod-search" style={{ position: "relative", margin: "8px 0 12px" }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input value={psearch} onChange={(e) => { setPsearch(e.target.value); setPsel(null); }} placeholder={t("🔍 Поиск товара из номенклатуры по названию…","🔍 Пошук товару з номенклатури за назвою…")} style={{ flex: 1, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 10px" }} />
                  <input type="number" value={addQty} min={1} onChange={(e) => setAddQty(Number(e.target.value))} title={t("Количество","Кількість")} style={{ width: 56, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px" }} />
                  <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, whiteSpace: "nowrap" }} title={t("Зарезервировать товар под сделку","Зарезервувати товар під сделку")}><input type="checkbox" checked={addReserve} onChange={(e) => setAddReserve(e.target.checked)} />{t("Резерв","Резерв")}</label>
                  <button className="btn btn-primary" onClick={() => addItem()} disabled={!psel}>{t("Добавить","Додати")}</button>
                  <button className="btn" onClick={() => setShowList((s) => !s)} title={t("Показать весь список товаров (двойной клик — добавить)","Показати весь список товарів (подвійний клік — додати)")}>{showList ? t("✕ Список","✕ Список") : t("📋 Список","📋 Список")}</button>
                </div>
                {presults.length > 0 && (
                  <div style={{ position: "absolute", top: 38, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 8px 24px rgba(15,23,42,.15)", zIndex: 20, maxHeight: 260, overflowY: "auto" }}>
                    {presults.map((p) => (
                      <div key={p.id} onClick={() => { setPsel(p); setPsearch(p.name); setPresults([]); }} onDoubleClick={() => addItem(p)} title={t("Клик — выбрать, двойной клик — сразу добавить","Клік — обрати, подвійний клік — одразу додати")} style={{ padding: "8px 10px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13 }}>
                        <b>{p.name}</b> <span className="muted">· {fmt(Number(p.price))} ₴ · {t("ост.","зал.")} {(p as any).stock}</span>
                      </div>
                    ))}
                  </div>
                )}
                {psel && <div style={{ fontSize: 12, color: "#16a34a", marginTop: 4 }}>{t("✓ Выбрано:","✓ Обрано:")} {psel.name} · {fmt(Number(psel.price))} ₴ · {t("сумма","сума")} {fmt(Number(psel.price) * addQty)} ₴</div>}
              </div>
              {showList && (
                <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, maxHeight: 300, overflowY: "auto", marginBottom: 12 }}>
                  <div style={{ padding: "6px 10px", fontSize: 11, color: "#64748b", borderBottom: "1px solid #f1f5f9", position: "sticky", top: 0, background: "#f8fafc" }}>{t("Двойной клик по товару — добавить в сделку. Поиск сверху фильтрует список.","Подвійний клік по товару — додати у сделку. Пошук зверху фільтрує список.")}</div>
                  {products.filter((p) => !psearch.trim() || p.name.toLowerCase().includes(psearch.toLowerCase())).map((p) => {
                    const added = deal.items.some((it: any) => it.product === p.id);
                    return (
                      <div key={p.id} onDoubleClick={() => addItem(p)} title={t("Двойной клик — добавить","Подвійний клік — додати")} style={{ padding: "7px 10px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13, display: "flex", justifyContent: "space-between", gap: 8 }}>
                        <span><b>{p.name}</b> <span className="muted">· {fmt(Number(p.price))} ₴ · {t("ост.","зал.")} {(p as any).stock}</span></span>
                        {added && <span style={{ color: "#16a34a", whiteSpace: "nowrap" }}>✓ {t("в сделке","у сделці")}</span>}
                      </div>
                    );
                  })}
                  {products.filter((p) => !psearch.trim() || p.name.toLowerCase().includes(psearch.toLowerCase())).length === 0 && <div style={{ padding: 12, fontSize: 13, color: "#94a3b8" }}>{t("Ничего не найдено","Нічого не знайдено")}</div>}
                </div>
              )}
              {deal.items.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>{t("Товаров пока нет.","Товарів поки немає.")}</div> : (
                <>
                <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", fontSize: 13 }}><thead><tr style={{ color: "#64748b", fontSize: 11, textAlign: "left" }}>
                  <th style={{ padding: "6px 4px" }}>№</th><th style={{ padding: "6px 4px" }}>{t("Товар","Товар")}</th>
                  <th style={{ padding: "6px 4px" }}>{t("Цена","Ціна")}</th><th style={{ padding: "6px 4px" }}>{t("Кол-во","К-сть")}</th>
                  <th style={{ padding: "6px 4px", textAlign: "center" }}>{t("Резерв","Резерв")}</th><th style={{ padding: "6px 4px" }}>{t("Остаток","Залишок")}</th>
                  <th style={{ padding: "6px 4px" }}>{t("Скидка %","Знижка %")}</th><th style={{ padding: "6px 4px" }}>{t("Сумма скидки","Сума знижки")}</th>
                  <th style={{ padding: "6px 4px" }}>{t("Сумма","Сума")}</th><th></th></tr></thead>
                  <tbody>{deal.items.map((it: any, idx: number) => {
                    const low = it.product_stock != null && Number(it.quantity) > Number(it.product_stock);
                    return (
                    <tr key={it.id} style={{ borderTop: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "6px 4px", color: "#94a3b8" }}>{idx + 1}</td>
                      <td style={{ padding: "6px 4px" }}><span style={{ color: "#1d4ed8", cursor: "pointer" }} onClick={() => nav(`/warehouse?p=${it.product}`)}>{it.product_name}</span></td>
                      <td style={{ padding: "6px 4px", whiteSpace: "nowrap" }}><input defaultValue={Number(it.price)} type="number" onBlur={(e) => Number(e.target.value) !== Number(it.price) && updateItem(it.id, { price: e.target.value })} style={editInp} /> ₴</td>
                      <td style={{ padding: "6px 4px" }}><input defaultValue={Number(it.quantity)} type="number" onBlur={(e) => Number(e.target.value) !== Number(it.quantity) && updateItem(it.id, { quantity: e.target.value })} style={{ ...editInp, width: 50 }} /></td>
                      <td style={{ padding: "6px 4px", textAlign: "center" }}><input type="checkbox" checked={!!it.reserved} onChange={() => toggleReserve(it)} title={t("Зарезервировать под сделку","Зарезервувати під сделку")} /></td>
                      <td style={{ padding: "6px 4px", color: low ? "#dc2626" : "#64748b" }} title={low ? t("Не хватает на складе","Не вистачає на складі") : ""}>{it.product_stock != null ? Number(it.product_stock) : "—"}{low ? " ⚠" : ""}</td>
                      <td style={{ padding: "6px 4px", whiteSpace: "nowrap" }}><input defaultValue={Number(it.discount_pct || 0)} type="number" onBlur={(e) => Number(e.target.value) !== Number(it.discount_pct || 0) && updateItem(it.id, { discount_pct: e.target.value })} style={{ ...editInp, width: 44 }} /> %</td>
                      <td style={{ padding: "6px 4px", color: "#16a34a" }}>{fmt(Number(it.discount_sum || 0))} ₴</td>
                      <td style={{ padding: "6px 4px" }}><b>{fmt(Number(it.total))} ₴</b></td>
                      <td style={{ padding: "6px 4px" }}><span style={{ color: "#ef4444", cursor: "pointer" }} onClick={() => removeItem(it.id)}>✕</span></td></tr>
                  ); })}</tbody>
                </table>
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                  <div style={{ minWidth: 290 }}>
                    <div style={rowTot}><span className="muted">{t("Сумма без скидки","Сума без знижки")}</span><b>{fmt(deal.items.reduce((s: number, i: any) => s + Number(i.quantity) * Number(i.price), 0))} ₴</b></div>
                    <div style={rowTot}><span className="muted">{t("Сумма скидки","Сума знижки")}</span><b style={{ color: "#16a34a" }}>−{fmt(deal.items.reduce((s: number, i: any) => s + Number(i.discount_sum || 0), 0))} ₴</b></div>
                    <div style={{ ...rowTot, fontSize: 16, borderTop: "2px solid #e2e8f0", paddingTop: 8, marginTop: 4 }}><span>{t("Итого","Загальна сума")}</span><b>{fmt(deal.items.reduce((s: number, i: any) => s + Number(i.total), 0))} ₴</b></div>
                  </div>
                </div>
                </>
              )}
            </div>
          )}
        </div>
        </div>
        {deal.contact_id && (
          <div onMouseDown={startResize} title={t("Тяни, чтобы изменить ширину чата","Тягни, щоб змінити ширину чату")} style={{ width: 6, alignSelf: "stretch", cursor: "col-resize", background: "#e2e8f0", borderRadius: 3, flexShrink: 0 }} />
        )}
        {deal.contact_id && (
          <div style={{ width: chatW, flexShrink: 0, position: "sticky", top: 56, alignSelf: "flex-start" }}>
            <div className="panel">
              <div className="label">{t("💬 Чат с клиентом","💬 Чат з клієнтом")}</div>
              <ClientChat contact={deal.contact_id} />
            </div>
          </div>
        )}
      </div>
      ) : <CashflowTab deal={deal} remaining={remaining} onPay={() => { setPayAmount(String(remaining > 0 ? remaining : deal.amount)); setPayOpen(true); }} createTTN={createTTN} issueCheckbox={issueCheckbox} sendPayLink={sendPayLink} flash={flash} />}

      {docOpen && <KpDoc deal={deal} onClose={() => setDocOpen(false)} />}
      {/* модалка створення клієнта зі сделки */}
      {ncOpen && (
        <div onClick={() => setNcOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>{t("Клиент сделки","Клієнт сделки")}</h3>
            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              <button className={"btn" + (ncMode === "pick" ? " btn-primary" : " btn-light")} style={{ flex: 1 }} onClick={() => setNcMode("pick")}>{t("🔍 Выбрать существующего","🔍 Обрати існуючого")}</button>
              <button className={"btn" + (ncMode === "new" ? " btn-primary" : " btn-light")} style={{ flex: 1 }} onClick={() => setNcMode("new")}>{t("➕ Создать нового","➕ Створити нового")}</button>
            </div>
            {ncMode === "pick" ? (
              <>
                <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("Найди клиента среди существующих (37 тыс.) и привяжи к сделке.","Знайди клієнта серед існуючих (37 тис.) і привʼяжи до сделки.")}</div>
                <input value={ncSearch} autoFocus onChange={(e) => setNcSearch(e.target.value)} placeholder={t("Имя, фамилия, телефон…","Імʼя, прізвище, телефон…")} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 8 }} />
                <div style={{ maxHeight: 240, overflowY: "auto", marginBottom: 12 }}>
                  {ncResults.map((c) => (
                    <div key={c.id} onClick={() => linkExisting(c.id)} style={{ padding: "8px 10px", borderRadius: 8, cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13 }}>
                      👤 <b>{c.display_name || `${c.first_name || ""} ${c.last_name || ""}`.trim() || "—"}</b> {c.phone ? <span className="muted">· {c.phone}</span> : null}
                    </div>
                  ))}
                  {ncSearch.trim() && ncResults.length === 0 && <div className="muted" style={{ fontSize: 13, padding: 8 }}>{t("Ничего не найдено. Создай нового на соседней вкладке.","Нічого не знайдено. Створи нового на сусідній вкладці.")}</div>}
                </div>
                <button className="btn btn-light" style={{ width: "100%" }} onClick={() => setNcOpen(false)}>{t("Закрыть","Закрити")}</button>
              </>
            ) : (
              <>
                <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Создастся карточка клиента и привяжется к этой сделке.","Створиться картка клієнта і привʼяжеться до цієї сделки.")}</div>
                <label className="label">{t("Имя и фамилия","Імʼя та прізвище")}</label>
                <input value={nc.name} onChange={(e) => setNc({ ...nc, name: e.target.value })} placeholder="Ірина Турок" style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 }} />
                <label className="label">{t("Телефон","Телефон")}</label>
                <input value={nc.phone} onChange={(e) => setNc({ ...nc, phone: e.target.value })} placeholder="+380..." style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 }} />
                <label className="label">{t("Email","Email")}</label>
                <input value={nc.email} onChange={(e) => setNc({ ...nc, email: e.target.value })} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 14 }} />
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setNcOpen(false)}>{t("Отменить","Скасувати")}</button>
                  <button className="btn btn-primary" style={{ flex: 1 }} onClick={createClient} disabled={!nc.name.trim()}>{t("Создать","Створити")}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ─── [12] РЕНДЕР: модалка приёма оплаты ───────────────────────── */}
      {payOpen && (
        <div onClick={() => setPayOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 24, width: 340 }}>
            <h3 style={{ marginTop: 0 }}>{t("Принять оплату","Прийняти оплату")}</h3>
            <label className="label">{t("Сумма","Сума")}</label>
            <input type="number" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} style={{ width: "100%", height: 38, marginBottom: 16, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setPayOpen(false)}>{t("Отмена","Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={acceptPayment}>{t("Провести","Провести")}</button>
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>{t("Создаст доходную транзакцию в Финансах.","Створить дохідну транзакцію у Фінансах.")}</div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── [13] СУБ-КОМПОНЕНТЫ ──────────────────────────────────────────────── */

// Стиль чипа-бейджа «выполнено / нет» (зелёный / серый).
function chip(on: boolean): React.CSSProperties {
  return { fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: on ? "#dcfce7" : "#f1f5f9", color: on ? "#166534" : "#94a3b8" };
}

// Инлайн-редактор числового поля: клик по значению → input → Enter/blur сохраняет.
function Inline({ value, fmt, onSave }: { value: number; fmt: (v: number) => string; onSave: (v: number) => void }) {
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState(String(value));
  useEffect(() => setV(String(value)), [value]);
  if (edit) return (
    <input autoFocus value={v} onChange={(e) => setV(e.target.value)}
      onBlur={() => { setEdit(false); if (Number(v) !== value) onSave(Number(v)); }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") { setV(String(value)); setEdit(false); } }}
      style={{ width: 110, height: 28, borderRadius: 6, border: "1px solid var(--brand,#2563eb)", padding: "0 6px", fontSize: 14 }} />
  );
  return <span onClick={() => setEdit(true)} style={{ cursor: "text", borderBottom: "1px dashed #cbd5e1" }}>{fmt(value)}</span>;
}


/* ─── WALLCOV CASHFLOW — перенесено з віджета finmap-bridge (5 вкладок) ───── */
function CashflowTab({ deal }: any) {
  const { t } = useLang();
  /* Боєвий віджет Wallcov Cashflow (finmap-bridge) через iframe — 1:1 функціонал Бітрикса:
     Платежі (LiqPay/QR/Реквізити/історія/повернення/чек), Доставка НП (повна форма ТТН+пакування),
     Склад (бланк викраски), Архів кольорів, Лояльність. Працює по реальному Bitrix deal_id. */
  if (!deal.b24_id) {
    return (
      <div className="panel" style={{ margin: 0, textAlign: "center", padding: 40 }}>
        <h3>{t("Cashflow недоступен","Cashflow недоступний")}</h3>
        <div className="muted">{t("У этой сделки нет Bitrix-ID. Виджет работает только для перенесённых из Битрикса сделок.","У цієї сделки немає Bitrix-ID. Віджет працює лише для перенесених із Бітрикса угод.")}</div>
      </div>
    );
  }
  const viewer = 4; // адмін-перегляд (повний доступ). Пізніше — id менеджера.
  const url = `https://cashflow.wallcovdec.com.ua/widget/cashflow?deal_id=${deal.b24_id}&viewer_id=${viewer}`;
  return (
    <div className="panel" style={{ margin: 0, padding: 0, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderBottom: "1px solid #e2e8f0", background: "#f8fafc" }}>
        <b style={{ fontSize: 13 }}>💰 Wallcov Cashflow</b>
        <span className="muted" style={{ fontSize: 12 }}>{t("боевой виджет","боєвий віджет")} · deal #{deal.b24_id}</span>
        <div style={{ flex: 1 }} />
        <a href={url} target="_blank" rel="noreferrer" className="btn btn-light" style={{ fontSize: 12, padding: "3px 9px" }}>{t("↗ Открыть в отдельной вкладке","↗ Відкрити в окремій вкладці")}</a>
      </div>
      <iframe src={url} title="Wallcov Cashflow" style={{ width: "100%", height: "82vh", border: "none", display: "block" }} />
    </div>
  );
}
