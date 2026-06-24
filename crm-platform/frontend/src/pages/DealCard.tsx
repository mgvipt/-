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

/* ─── [1] ТИПЫ ─────────────────────────────────────────────────────────── */

interface Item { id: number; product: number; product_name: string; quantity: string; price: string; total: string; }
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

export default function DealCard({ dealId, onClose }: { dealId?: number; onClose?: () => void } = {}) {

  /* ─── [3] STATE ──────────────────────────────────────────────────────── */
  const params = useParams();
  const id = dealId != null ? String(dealId) : params.id;
  const nav = useNavigate();
  const [deal, setDeal] = useState<Deal | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [tab, setTab] = useState<"general" | "items" | "cashflow">("general");
  const [addProd, setAddProd] = useState(0);
  const [addQty, setAddQty] = useState(1);
  const [psearch, setPsearch] = useState(""); const [presults, setPresults] = useState<Product[]>([]); const [psel, setPsel] = useState<Product | null>(null); const [addReserve, setAddReserve] = useState(false);
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

  async function setStage(stageId: number) { await patch({ stage: stageId }); }

  async function addItem() {
    if (!psel) return;
    setDeal(await api.post<Deal>(`/api/deals/${id}/add_item/`, { product: psel.id, quantity: addQty, reserved: addReserve }));
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
  async function removeItem(item: number) { setDeal(await api.post<Deal>(`/api/deals/${id}/remove_item/`, { item })); }

  async function acceptPayment() {
    setDeal(await api.post<Deal>(`/api/deals/${id}/accept_payment/`, { amount: payAmount || deal?.amount }));
    setPayOpen(false); setPayAmount(""); flash("✓ Оплата проведена в финансы");
  }
  async function ship() {
    try { const r = await api.post<any>(`/api/deals/${id}/ship/`, {}); setDeal(r.deal); flash(`✓ Отгружено. Себестоимость ${r.cogs} ₴ списана`); }
    catch { flash("В сделке нет товаров для отгрузки"); }
  }
  // TODO боевой режим: завести @action в DealViewSet поверх integrations/adapters.py
  //      (np_create_ttn / checkbox_create_receipt / liqpay_checkout_link). Сейчас — заглушки.
  async function createTTN() { await patch({ ttn: "НП " + Math.floor(2e13 + Math.random() * 1e13) }); flash("✓ ТТН Нова Пошта создана"); }
  async function issueCheckbox() { await patch({ checkbox_status: deal?.paid && deal.paid < Number(deal.amount) ? "аванс" : "финальный" }); flash("✓ Чек Checkbox сформирован"); }
  function sendPayLink() { flash("✓ Ссылка на оплату отправлена клиенту · cashflow.wallcovdec.com.ua"); }
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
  async function removeContact() { if (!confirm("Прибрати клієнта зі сделки?")) return; await api.patch(`/api/deals/${id}/`, { contact: null }); load(); }
  async function createInlineClient() { const p = cliN.name.trim().split(/\s+/); const c = await api.post<any>("/api/contacts/", { first_name: p[0] || cliN.name.trim(), last_name: p.slice(1).join(" "), phone: cliN.phone }); setContact(c.id); setCliN({ name: "", phone: "" }); }
  async function createClient() {
    const parts = nc.name.trim().split(" ");
    const contact = await api.post<{ id: number }>(`/api/contacts/`, { first_name: parts[0] || nc.name, last_name: parts.slice(1).join(" "), phone: nc.phone, email: nc.email });
    await api.patch(`/api/deals/${id}/`, { contact: contact.id });
    setNcOpen(false); setNc({ name: "", phone: "", email: "" }); load();
  }
  async function sendChat() {
    if (!draft.trim() || !deal?.conversation_id) { if (!deal?.conversation_id) flash("Немає активного чату з клієнтом"); return; }
    setSending(true);
    try {
      const m = await api.post<any>(`/api/conversations/${deal.conversation_id}/send/`, { text: draft.trim() });
      setChat((c) => [...c, m]); setDraft("");
    } catch { flash("Не вдалося відправити (канал/токен)"); }
    finally { setSending(false); }
  }
  async function aiSuggest() {
    setAiLoad(true); setAi(null);
    try { setAi(await api.post<any>(`/api/deals/${id}/ai_suggest/`, {})); }
    catch { flash("AI недоступний"); }
    finally { setAiLoad(false); }
  }

  /* ─── [6] ВЫЧИСЛЯЕМОЕ ────────────────────────────────────────────────── */
  if (notFound) return <div className="scroll pad fade"><div className="panel" style={{ textAlign: "center", padding: 40 }}><h3>Сделку не знайдено</h3><div className="muted" style={{ marginBottom: 16 }}>Можливо, її видалено або змінено ID після перенесення з Бітрикса. Відкрий зі списку сделок.</div><button className="btn btn-primary" onClick={() => nav("/deals")}>← До списку сделок</button></div></div>;
  if (!deal) return <div className="spin">Загрузка сделки…</div>;
  const curOrder = funnel?.stages.find((s) => s.id === deal.stage)?.order ?? 0;
  const remaining = Number(deal.amount) - deal.paid;
  const disc = Number(deal.discount_pct || 0);
  const loyalty = deal.contact_loyalty || "";
  const hasCheck = !!deal.checkbox_status && deal.checkbox_status !== "none";
  // Лента событий из реальных данных (оплаты + системное «создана»):
  const events = [
    ...deal.payments.map((p) => ({ t: p.created_at, kind: "pay", text: `Оплата ${fmt(Number(p.amount))} ₴ · ${p.provider}` })),
    { t: deal.payments[0]?.created_at || "", kind: "sys", text: "Сделка создана" },
  ].filter((e) => e.t);

  return (
    <div className="scroll fade">

      {/* ─── [7] РЕНДЕР: шапка ─────────────────────────────────────────── */}
      <div className="dealhead">
        <button className="back" onClick={() => onClose ? onClose() : nav("/deals")}>←</button>
        <b style={{ fontSize: 16 }}>#{deal.id} · {deal.title}</b>
        <span className="muted">{funnel?.name}</span>
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        <button className="btn btn-green" onClick={ship}>📦 Отгрузить</button>
      </div>

      {/* ─── [8] РЕНДЕР: стадии (клик = смена, на текущей — дни) ────────── */}
      {funnel && (
        <div className="stagebar">
          {funnel.stages.map((s) => {
            const cur = s.id === deal.stage;
            return (
              <div key={s.id} className="stage" onClick={() => setStage(s.id)}
                style={{ cursor: "pointer", background: s.order <= curOrder ? "var(--brand)" : "#cbd5e1" }}>
                {s.name}{cur && deal.days_in_stage != null ? ` · ${deal.days_in_stage}д` : ""}
              </div>
            );
          })}
        </div>
      )}

      {/* ─── [9] РЕНДЕР: єдина панель — вкладки + дії (dealbar-unified) ──── */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", margin: "12px 0", padding: "8px 10px", background: "linear-gradient(90deg,#f8fafc,#eef2ff)", borderRadius: 10, border: "1px solid #e2e8f0" }}>
        <button className={"btn" + (tab === "general" ? " btn-primary" : "")} onClick={() => setTab("general")}>💬 Лента / Чат</button>
        <button className={"btn" + (tab === "items" ? " btn-primary" : "")} onClick={() => setTab("items")}>📦 Товари ({deal.items.length})</button>
        <button className={"btn" + (tab === "cashflow" ? " btn-primary" : "")} onClick={() => setTab("cashflow")}>💰 Cashflow</button>
        <div style={{ width: 1, height: 24, background: "#cbd5e1", margin: "0 6px" }} />
        <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Дії:</span>
        <button className="btn" onClick={sendPayLink}>💳 Оплата</button>
        <button className="btn" onClick={createTTN}>🚚 ТТН</button>
        <button className="btn" onClick={issueCheckbox}>🧾 Checkbox</button>
      </div>

      {tab !== "cashflow" ? (
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <div className="grid2" style={{ flex: 1, minWidth: 0 }}>

        {/* ─── [10] РЕНДЕР: левая колонка — данные заказа ───────────────── */}
        <div>
          {/* 10.1 Клиент — інлайн вибір/зміна/прибирання (без попапів) */}
          <div className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="label">Клиент</div>
              {deal.contact_id && !cliEdit && (
                <span style={{ fontSize: 11, display: "flex", gap: 10 }}>
                  <span style={{ color: "#2563eb", cursor: "pointer" }} onClick={() => { setCliEdit(true); setCliNew(false); }}>✏️ Змінити</span>
                  <span style={{ color: "#dc2626", cursor: "pointer" }} onClick={removeContact}>✕ Прибрати</span>
                </span>
              )}
            </div>
            {deal.contact_id && !cliEdit ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600 }}>{deal.contact_name || "Без контакта"}</span>
                  {loyalty && <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: (LOYALTY_COLOR[loyalty] || "#64748b") + "22", color: LOYALTY_COLOR[loyalty] || "#64748b" }}>{loyalty}</span>}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  <button className="btn" style={{ flex: 1, background: "#ecfdf5", color: "#047857" }}>📞 Позвонить</button>
                  <button className="btn" style={{ flex: 1, background: "#eff6ff", color: "#1d4ed8" }} onClick={() => deal.conversation_id ? nav(`/inbox?c=${deal.conversation_id}`) : setTab("general")}>💬 Чат</button>
                  <button className="btn" style={{ background: "#f1f5f9" }} title="Картка клієнта" onClick={() => nav(`/clients/${deal.contact_id}`)}>Клієнт →</button>
                </div>
              </>
            ) : (
              <div style={{ marginTop: 6 }}>
                <input value={cliSearch} autoFocus onChange={(e) => setCliSearch(e.target.value)} placeholder="🔍 Телефон або імʼя клієнта…" style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px" }} />
                {cliResults.length > 0 && (
                  <div style={{ maxHeight: 200, overflowY: "auto", marginTop: 6, border: "1px solid #e2e8f0", borderRadius: 8 }}>
                    {cliResults.map((c) => (
                      <div key={c.id} onClick={() => setContact(c.id)} style={{ padding: "7px 9px", borderBottom: "1px solid #f1f5f9", cursor: "pointer", fontSize: 13 }}>
                        👤 <b>{c.display_name || `${c.first_name || ""} ${c.last_name || ""}`.trim() || "—"}</b> {c.phone ? <span className="muted">· {c.phone}</span> : null}
                      </div>
                    ))}
                  </div>
                )}
                {cliSearch.trim() && cliResults.length === 0 && <div className="muted" style={{ fontSize: 12, padding: "6px 0" }}>Не знайдено — створи нового нижче.</div>}
                {!cliNew ? (
                  <div style={{ display: "flex", gap: 10, marginTop: 8, fontSize: 12 }}>
                    <span style={{ color: "#16a34a", cursor: "pointer" }} onClick={() => setCliNew(true)}>➕ Створити нового</span>
                    {deal.contact_id && <span style={{ color: "#64748b", cursor: "pointer", marginLeft: "auto" }} onClick={() => { setCliEdit(false); setCliSearch(""); }}>Скасувати</span>}
                  </div>
                ) : (
                  <div style={{ marginTop: 8 }}>
                    <input value={cliN.name} onChange={(e) => setCliN({ ...cliN, name: e.target.value })} placeholder="Імʼя та прізвище" style={{ width: "100%", height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 9px", marginBottom: 6 }} />
                    <input value={cliN.phone} onChange={(e) => setCliN({ ...cliN, phone: e.target.value })} placeholder="+380…" style={{ width: "100%", height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 9px", marginBottom: 6 }} />
                    <div style={{ display: "flex", gap: 6 }}>
                      <button className="btn btn-light" style={{ flex: 1, fontSize: 12 }} onClick={() => setCliNew(false)}>Назад</button>
                      <button className="btn btn-primary" style={{ flex: 1, fontSize: 12 }} onClick={createInlineClient} disabled={!cliN.name.trim()}>Створити</button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 10.2 Сумма / оплачено / осталось (сумма — инлайн-edit) */}
          <div className="panel">
            <div className="label">Сумма сделки</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              <Inline value={Number(deal.amount)} fmt={(v) => fmt(v) + " грн."} onSave={(v) => patch({ amount: v })} />
            </div>
            <div className="row" style={{ marginTop: 8 }}><span className="muted">Оплачено</span><b style={{ color: "#16a34a" }}>{fmt(deal.paid)} ₴</b></div>
            <div className="row"><span className="muted">Осталось</span><b style={{ color: remaining > 0 ? "#d97706" : "#16a34a" }}>{fmt(remaining)} ₴</b></div>
            <button className="btn btn-primary" style={{ width: "100%", height: 36, marginTop: 10 }} onClick={() => { setPayAmount(String(remaining > 0 ? remaining : deal.amount)); setPayOpen(true); }}>💳 Принять оплату</button>
          </div>
          <ActivityLog kind="deal" id={deal.id} />

          {/* 10.3 Скидка (инлайн-edit) + авто-рекомендация для VIP */}
          <div className="panel">
            <div className="label">Скидка</div>
            <div className="row"><span className="muted">Текущая</span><b><Inline value={disc} fmt={(v) => v + " %"} onSave={(v) => patch({ discount_pct: v })} /></b></div>
            {loyalty === "VIP" && disc < 10 && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginTop: 8, background: "#ecfdf5", color: "#047857", padding: "7px 9px", borderRadius: 8, fontSize: 12 }}>
                <span>VIP: при полной оплате доступно 10%</span>
                <button className="btn" style={{ padding: "3px 8px" }} onClick={() => patch({ discount_pct: 10 })}>Применить</button>
              </div>
            )}
          </div>

          {/* 10.4 Доставка и документы (ТТН / чек + бейджи) */}
          <div className="panel">
            <div className="label">Доставка и документы</div>
            <div className="row"><span className="muted">ТТН Нова Пошта</span><b>{deal.ttn || "—"}</b></div>
            <div className="row"><span className="muted">Чек Checkbox</span><b>{hasCheck ? deal.checkbox_status : "—"}</b></div>
            <div style={{ marginTop: 6, display: "flex", gap: 6 }}>
              <span style={chip(hasCheck)}>Чек {hasCheck ? "✓" : "—"}</span>
              <span style={chip(!!deal.ttn)}>ТТН {deal.ttn ? "✓" : "—"}</span>
            </div>
          </div>

          {/* 10.5 Маржа + бонус менеджера (для руководителя) */}
          <div className="panel">
            <div className="label">Маржа (видит РОП / руководитель)</div>
            <div className="row"><span className="muted">Маржа</span><b>{fmt(deal.margin || 0)} ₴{deal.margin && Number(deal.amount) ? ` · ${Math.round((deal.margin / Number(deal.amount)) * 100)}%` : ""}</b></div>
            <div className="row" title={deal.bonus ? `${deal.bonus.revenue_pct}% з обороту + ${deal.bonus.margin_pct}% з маржі. Ставки міняються у Фінмоделі → ЗП.` : ""}><span className="muted">💰 Бонус менеджера з угоди</span><b style={{ color: "#1d4ed8" }}>{fmt(deal.bonus?.total || 0)} ₴</b></div>
            {deal.bonus && <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{deal.bonus.revenue_pct}% обороту = {fmt(deal.bonus.from_revenue)} ₴ + {deal.bonus.margin_pct}% маржі = {fmt(deal.bonus.from_margin)} ₴</div>}
          </div>

          {/* 10.6 Ответственный */}
          <div className="panel">
            <div className="label">Ответственный</div>
            <OwnerSelect ownerId={deal.owner} ownerName={deal.owner_name} onSet={(uid) => patch({ owner: uid })} />
          </div>
        </div>

        {/* ─── [11] РЕНДЕР: правая колонка — лента ИЛИ товары ───────────── */}
        <div>
          {tab === "general" ? (
            <>
              <NeedsForm leadId={deal.id} initial={deal.qualification} endpoint="/api/deals/" />
              <CardFields leadId={deal.id} initial={deal.card_fields} endpoint="/api/deals/" />
            {/* 11.1 ЧАТ З КЛІЄНТОМ + події + AI-помічник */}
            <div className="panel">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div className="label">Чат з клієнтом · {deal.contact_name || "—"}</div>
                <button className="btn" style={{ fontSize: 12, padding: "3px 9px", background: "#f5f3ff", color: "#6d28d9" }} onClick={aiSuggest} disabled={aiLoad}>{aiLoad ? "AI думає…" : "✨ AI-помічник"}</button>
              </div>
              {ai && (
                <div style={{ background: "#faf5ff", border: "1px solid #e9d5ff", borderRadius: 8, padding: 10, margin: "8px 0", fontSize: 13 }}>
                  <div style={{ color: "#6d28d9", fontWeight: 600, marginBottom: 4 }}>✨ Контекст діалогу</div>
                  <div style={{ color: "#475569", marginBottom: 8 }}>{ai.context}</div>
                  <div style={{ color: "#6d28d9", fontWeight: 600, marginBottom: 4 }}>Пропонована відповідь</div>
                  <div style={{ color: "#1e293b" }}>{ai.suggestion}</div>
                  <button className="btn btn-light" style={{ fontSize: 12, padding: "3px 9px", marginTop: 8 }} onClick={() => { setDraft(ai.suggestion); setAi(null); }}>↧ Вставити у відповідь</button>
                </div>
              )}
              <div style={{ maxHeight: 280, overflowY: "auto", marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                {chat.length === 0 && events.length === 0 && <div className="muted" style={{ fontSize: 13 }}>Повідомлень ще немає. Чат підтягнеться з відкритих ліній (inbox).</div>}
                {chat.map((m) => (
                  <div key={m.id} style={{ maxWidth: "85%", padding: "8px 11px", borderRadius: 10, fontSize: 13, alignSelf: m.direction === "out" ? "flex-end" : "flex-start", background: m.direction === "out" ? "var(--brand,#2563eb)" : "#f1f5f9", color: m.direction === "out" ? "#fff" : "#1e293b" }}>{m.text}</div>
                ))}
                {events.map((e, i) => (
                  <div key={"e" + i} style={{ fontSize: 12, padding: "6px 9px", borderRadius: 8, background: e.kind === "pay" ? "#ecfdf5" : "#f8fafc", color: e.kind === "pay" ? "#047857" : "#64748b", alignSelf: "center" }}>{e.text}</div>
                ))}
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && sendChat()} placeholder={deal.conversation_id ? "Повідомлення клієнту…" : "Немає активного чату"} style={{ flex: 1, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 10px" }} />
                <button className="btn btn-primary" onClick={sendChat} disabled={sending}>{sending ? "…" : "➤"}</button>
              </div>
            </div>
            </>
          ) : (
            /* 11.2 Товары в сделке (добавить/удалить → пересчёт суммы на бэке) */
            <div className="panel">
              <div className="label">Товары в сделке</div>
              <div className="prod-search" style={{ position: "relative", margin: "8px 0 12px" }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input value={psearch} onChange={(e) => { setPsearch(e.target.value); setPsel(null); }} placeholder="🔍 Пошук товару з номенклатури за назвою…" style={{ flex: 1, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 10px" }} />
                  <input type="number" value={addQty} min={1} onChange={(e) => setAddQty(Number(e.target.value))} title="Кількість" style={{ width: 56, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px" }} />
                  <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, whiteSpace: "nowrap" }} title="Зарезервувати товар під сделку"><input type="checkbox" checked={addReserve} onChange={(e) => setAddReserve(e.target.checked)} />Резерв</label>
                  <button className="btn btn-primary" onClick={addItem} disabled={!psel}>Додати</button>
                </div>
                {presults.length > 0 && (
                  <div style={{ position: "absolute", top: 38, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 8px 24px rgba(15,23,42,.15)", zIndex: 20, maxHeight: 260, overflowY: "auto" }}>
                    {presults.map((p) => (
                      <div key={p.id} onClick={() => { setPsel(p); setPsearch(p.name); setPresults([]); }} style={{ padding: "8px 10px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13 }}>
                        <b>{p.name}</b> <span className="muted">· {fmt(Number(p.price))} ₴ · ост. {(p as any).stock}</span>
                      </div>
                    ))}
                  </div>
                )}
                {psel && <div style={{ fontSize: 12, color: "#16a34a", marginTop: 4 }}>✓ Обрано: {psel.name} · {fmt(Number(psel.price))} ₴ · сума {fmt(Number(psel.price) * addQty)} ₴</div>}
              </div>
              {deal.items.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>Товаров пока нет.</div> : (
                <table><thead><tr><th>Товар</th><th>Кол-во</th><th>Залишок</th><th>Цена</th><th>Сумма</th><th>Резерв</th><th></th></tr></thead>
                  <tbody>{deal.items.map((it: any) => {
                    const low = it.product_stock != null && Number(it.quantity) > Number(it.product_stock);
                    return (
                    <tr key={it.id}><td><span style={{ color: "#1d4ed8", cursor: "pointer" }} onClick={() => nav(`/warehouse?p=${it.product}`)}>{it.product_name}</span></td><td>{Number(it.quantity)}</td>
                      <td style={{ color: low ? "#dc2626" : "#64748b" }} title={low ? "Не вистачає на складі" : ""}>{it.product_stock != null ? Number(it.product_stock) : "—"}{low ? " ⚠" : ""}</td>
                      <td>{fmt(Number(it.price))} ₴</td><td><b>{fmt(Number(it.total))} ₴</b></td>
                      <td style={{ textAlign: "center" }}><input type="checkbox" checked={!!it.reserved} onChange={() => toggleReserve(it)} title="Зарезервувати під сделку" /></td>
                      <td><span style={{ color: "#ef4444", cursor: "pointer" }} onClick={() => removeItem(it.id)}>✕</span></td></tr>
                  ); })}</tbody>
                </table>
              )}
            </div>
          )}
        </div>
        </div>
        {deal.contact_id && (
          <div style={{ width: 360, flexShrink: 0, display: "flex", maxHeight: "calc(100vh - 110px)", position: "sticky", top: 56 }}>
            <div className="panel" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
              <div className="label">💬 Чат з клієнтом</div>
              <div style={{ flex: 1, minHeight: 0 }}><ClientChat contact={deal.contact_id} /></div>
            </div>
          </div>
        )}
      </div>
      ) : <CashflowTab deal={deal} remaining={remaining} onPay={() => { setPayAmount(String(remaining > 0 ? remaining : deal.amount)); setPayOpen(true); }} createTTN={createTTN} issueCheckbox={issueCheckbox} sendPayLink={sendPayLink} flash={flash} />}

      {/* модалка створення клієнта зі сделки */}
      {ncOpen && (
        <div onClick={() => setNcOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>Клієнт сделки</h3>
            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              <button className={"btn" + (ncMode === "pick" ? " btn-primary" : " btn-light")} style={{ flex: 1 }} onClick={() => setNcMode("pick")}>🔍 Обрати існуючого</button>
              <button className={"btn" + (ncMode === "new" ? " btn-primary" : " btn-light")} style={{ flex: 1 }} onClick={() => setNcMode("new")}>➕ Створити нового</button>
            </div>
            {ncMode === "pick" ? (
              <>
                <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>Знайди клієнта серед існуючих (37 тис.) і привʼяжи до сделки.</div>
                <input value={ncSearch} autoFocus onChange={(e) => setNcSearch(e.target.value)} placeholder="Імʼя, прізвище, телефон…" style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 8 }} />
                <div style={{ maxHeight: 240, overflowY: "auto", marginBottom: 12 }}>
                  {ncResults.map((c) => (
                    <div key={c.id} onClick={() => linkExisting(c.id)} style={{ padding: "8px 10px", borderRadius: 8, cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13 }}>
                      👤 <b>{c.display_name || `${c.first_name || ""} ${c.last_name || ""}`.trim() || "—"}</b> {c.phone ? <span className="muted">· {c.phone}</span> : null}
                    </div>
                  ))}
                  {ncSearch.trim() && ncResults.length === 0 && <div className="muted" style={{ fontSize: 13, padding: 8 }}>Нічого не знайдено. Створи нового на сусідній вкладці.</div>}
                </div>
                <button className="btn btn-light" style={{ width: "100%" }} onClick={() => setNcOpen(false)}>Закрити</button>
              </>
            ) : (
              <>
                <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>Створиться картка клієнта і привʼяжеться до цієї сделки.</div>
                <label className="label">Ім'я та прізвище</label>
                <input value={nc.name} onChange={(e) => setNc({ ...nc, name: e.target.value })} placeholder="Ірина Турок" style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 }} />
                <label className="label">Телефон</label>
                <input value={nc.phone} onChange={(e) => setNc({ ...nc, phone: e.target.value })} placeholder="+380..." style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 10 }} />
                <label className="label">Email</label>
                <input value={nc.email} onChange={(e) => setNc({ ...nc, email: e.target.value })} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 14 }} />
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setNcOpen(false)}>Скасувати</button>
                  <button className="btn btn-primary" style={{ flex: 1 }} onClick={createClient} disabled={!nc.name.trim()}>Створити</button>
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
            <h3 style={{ marginTop: 0 }}>Принять оплату</h3>
            <label className="label">Сумма</label>
            <input type="number" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} style={{ width: "100%", height: 38, marginBottom: 16, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setPayOpen(false)}>Отмена</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={acceptPayment}>Провести</button>
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>Создаст доходную транзакцию в Финансах.</div>
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
  /* Боєвий віджет Wallcov Cashflow (finmap-bridge) через iframe — 1:1 функціонал Бітрикса:
     Платежі (LiqPay/QR/Реквізити/історія/повернення/чек), Доставка НП (повна форма ТТН+пакування),
     Склад (бланк викраски), Архів кольорів, Лояльність. Працює по реальному Bitrix deal_id. */
  if (!deal.b24_id) {
    return (
      <div className="panel" style={{ margin: 0, textAlign: "center", padding: 40 }}>
        <h3>Cashflow недоступний</h3>
        <div className="muted">У цієї сделки немає Bitrix-ID. Віджет працює лише для перенесених із Бітрикса угод.</div>
      </div>
    );
  }
  const viewer = 4; // адмін-перегляд (повний доступ). Пізніше — id менеджера.
  const url = `https://cashflow.wallcovdec.com.ua/widget/cashflow?deal_id=${deal.b24_id}&viewer_id=${viewer}`;
  return (
    <div className="panel" style={{ margin: 0, padding: 0, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderBottom: "1px solid #e2e8f0", background: "#f8fafc" }}>
        <b style={{ fontSize: 13 }}>💰 Wallcov Cashflow</b>
        <span className="muted" style={{ fontSize: 12 }}>боєвий віджет · deal #{deal.b24_id}</span>
        <div style={{ flex: 1 }} />
        <a href={url} target="_blank" rel="noreferrer" className="btn btn-light" style={{ fontSize: 12, padding: "3px 9px" }}>↗ Відкрити в окремій вкладці</a>
      </div>
      <iframe src={url} title="Wallcov Cashflow" style={{ width: "100%", height: "82vh", border: "none", display: "block" }} />
    </div>
  );
}
