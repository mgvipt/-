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

import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import { TaskQuickModal } from "../TaskQuickModal";
import { api, Funnel, Paginated } from "../api";
import OwnerSelect from "../OwnerSelect";
import { Avatar, SOURCES } from "../ui";
import NeedsForm from "../NeedsForm";
import CardFields from "../CardFields";
import ClientChat from "../ClientChat";
import ReceiptModal from "../ReceiptModal";
import ActivityLog from "../ActivityLog";
import CallButton from "../CallButton";
import KpDoc from "../KpDoc";
import { useLang } from "../i18n";
import VykraskaDoc from "../VykraskaDoc";
import { SocialLink } from "../social";
import { SalesAnalystPanel } from "../SalesAnalyst";
import { Icon } from "../Icon";
import NPDelivery from "./NPDelivery";
import DealEstimatePanel from "./DealEstimatePanel";

/* ─── [1] ТИПЫ ─────────────────────────────────────────────────────────── */

interface Item { id: number; product: number; product_name: string; quantity: string; price: string; discount_pct?: string; discount_amount?: string; discount_sum?: string; total: string; reserved?: boolean; product_stock?: number | null; }
interface Pay { id: number; provider: string; amount: string; is_paid: boolean; created_at: string; }
interface Deal {
  qualification?: any; card_fields?: any[];
  id: number; title: string; contact_name?: string; contact_social_link?: string; contact_phone?: string; owner_name?: string; owner?: number | null; created_at?: string;
  funnel: number; stage: number; amount: string; source: string; is_seen?: boolean;
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

function methodPair(p: string): [string, string] {
  switch (p) {
    case "cash": return ["Наличные", "Готівка"];
    case "liqpay": return ["LiqPay", "LiqPay"];
    case "terminal": return ["Терминал · карта/телефон", "Термінал · картка/телефон"];
    case "requisites": return ["Реквизиты IBAN", "Реквізити IBAN"];
    case "np": return ["Наложенный платёж", "Накладений платіж"];
    case "np_cod": return ["Наложка НП", "Наложка НП"];
    case "reqs": return ["Реквизиты IBAN", "Реквізити IBAN"];
    case "credit": return ["Товарный кредит", "Товарний кредит"];
    case "installment": return ["Рассрочка", "Розстрочка"];
    case "bank": return ["Банк", "Банк"];
    case "checkbox": return ["Checkbox", "Checkbox"];
    default: return [p, p];
  }
}

function methodIcon(p: string): string {
  switch (p) {
    case "cash": return "💵";
    case "terminal": return "💳";
    case "liqpay": return "💳";
    case "requisites": case "reqs": return "🏦";
    case "np": case "np_cod": return "📦";
    case "installment": return "📅";
    case "credit": return "🤝";
    default: return "💰";
  }
}

function resizeToDataUrl(file: File, max: number, q: number): Promise<string> {
  return new Promise((resolve) => {
    const r = new FileReader();
    r.onload = () => {
      const img = new Image();
      img.onload = () => {
        let w = img.width, h = img.height;
        if (w > max || h > max) { const sc = max / Math.max(w, h); w = Math.round(w * sc); h = Math.round(h * sc); }
        const c = document.createElement("canvas"); c.width = w; c.height = h;
        const ctx = c.getContext("2d"); if (ctx) ctx.drawImage(img, 0, 0, w, h);
        resolve(c.toDataURL("image/jpeg", q));
      };
      img.src = r.result as string;
    };
    r.readAsDataURL(file);
  });
}


function KpHistory({ history, deal }: { history?: any[]; deal: any }) {
  const { t } = useLang();
  const [view, setView] = useState<any>(null);
  const h = history || [];
  const f = (v: any) => Number(v || 0).toLocaleString("uk-UA");
  const th: React.CSSProperties = { textAlign: "left", padding: "4px 6px", borderBottom: "1px solid #e2e8f0", fontSize: 11, color: "#64748b" };
  const td: React.CSSProperties = { padding: "4px 6px", borderBottom: "1px solid #f1f5f9", fontSize: 12.5 };
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 8 }}>🧾 {t("История КП / накладных", "Історія КП / накладних")} <span className="muted" style={{ fontSize: 11, fontWeight: 400 }}>({h.length})</span></div>
      {h.length === 0 ? <div className="muted" style={{ fontSize: 12.5 }}>{t("Пока пусто — сохрани КП из документа (кнопка «Зберегти в історію»)", "Поки порожньо — збережи КП з документа (кнопка «Зберегти в історію»)")}</div> : (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {h.slice().reverse().map((s: any, idx: number) => (
            <div key={idx} onClick={() => setView(s)} title={t("Открыть версию", "Відкрити версію")} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 9px", border: "1px solid #e8edf3", borderRadius: 8, cursor: "pointer" }}>
              <span style={{ fontWeight: 700, fontSize: 12 }}>#{h.length - idx}</span>
              <span style={{ fontSize: 11.5, color: "#64748b" }}>{new Date(s.ts).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
              {s.note && <span style={{ fontSize: 11, color: "#0369a1", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 120 }}>{s.note}</span>}
              <span style={{ marginLeft: "auto", fontWeight: 700, fontSize: 12.5 }}>{f(s.total)} ₴</span>
            </div>
          ))}
        </div>
      )}
      {view && (
        <KpDoc
          deal={{ ...deal, items: (view.items || []).map((it: any) => ({
            product_name: it.name, quantity: it.qty, price: it.price, total: it.total,
            discount_sum: Math.max(0, Number(it.qty) * Number(it.price) - Number(it.total)),
          })) }}
          readOnly
          dateOverride={new Date(view.ts).toLocaleDateString("uk-UA")}
          onClose={() => setView(null)}
        />
      )}
    </div>
  );
}

function RefPhotos({ dealId, initial }: { dealId: number; initial?: string[] }) {
  const { t } = useLang();
  const [photos, setPhotos] = useState<string[]>(initial || []);
  const [busy, setBusy] = useState(false);
  const [zoom, setZoom] = useState<string | null>(null);
  async function onFiles(e: any) {
    const files = Array.from(e.target.files || []) as File[];
    if (!files.length) return;
    setBusy(true);
    const added: string[] = [];
    for (const f of files) { try { added.push(await resizeToDataUrl(f, 1280, 0.72)); } catch { /* skip */ } }
    const next = [...photos, ...added];
    setPhotos(next);
    try { await api.patch("/api/deals/" + dealId + "/", { ref_photos: next }); } catch { /* ignore */ }
    setBusy(false); e.target.value = "";
  }
  async function del(i: number) {
    const next = photos.filter((_, j) => j !== i);
    setPhotos(next);
    try { await api.patch("/api/deals/" + dealId + "/", { ref_photos: next }); } catch { /* ignore */ }
  }
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 8 }}>📷 {t("Скриншоты от клиента", "Скріни від клієнта")} <span className="muted" style={{ fontSize: 11, fontWeight: 400 }}>{t("— увидит склад в задаче", "— побачить склад у задачі")}</span></div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {photos.map((p, i) => (
          <div key={i} style={{ position: "relative" }}>
            <img src={p} onClick={() => setZoom(p)} title={t("Открыть в масштабе","Відкрити у масштабі")} style={{ width: 86, height: 86, objectFit: "cover", borderRadius: 8, border: "1px solid #e2e8f0", display: "block", cursor: "zoom-in" }} />
            <button onClick={() => del(i)} style={{ position: "absolute", top: -6, right: -6, width: 20, height: 20, borderRadius: 10, border: "none", background: "#dc2626", color: "#fff", cursor: "pointer", fontSize: 11, lineHeight: "20px", padding: 0 }}>✕</button>
          </div>
        ))}
        <label style={{ width: 86, height: 86, borderRadius: 8, border: "2px dashed #cbd5e1", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "#94a3b8", fontSize: 26 }}>
          {busy ? "…" : "+"}
          <input type="file" accept="image/*" multiple onChange={onFiles} style={{ display: "none" }} />
        </label>
      </div>
      {zoom && createPortal(
        <div onClick={() => setZoom(null)} style={{ position: "fixed", inset: 0, zIndex: 100000, background: "rgba(0,0,0,.88)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "zoom-out", animation: "drawerBgIn .18s ease" }}>
          <img src={zoom} onClick={(e) => e.stopPropagation()} style={{ maxWidth: "94vw", maxHeight: "94vh", objectFit: "contain", borderRadius: 8, boxShadow: "0 10px 60px rgba(0,0,0,.6)" }} />
          <button onClick={() => setZoom(null)} style={{ position: "fixed", top: 20, right: 26, width: 44, height: 44, borderRadius: 22, border: "none", background: "rgba(255,255,255,.18)", color: "#fff", fontSize: 24, cursor: "pointer" }}>✕</button>
        </div>, document.body)}
    </div>
  );
}

export default function DealCard({ dealId, onClose }: { dealId?: number; onClose?: () => void } = {}) {

  /* ─── [3] STATE ──────────────────────────────────────────────────────── */
  const params = useParams();
  const id = dealId != null ? String(dealId) : params.id;
  const nav = useNavigate();
  const loc = useLocation();
  const [showReceipt, setShowReceipt] = useState(false);
  const { can } = useAuth();
  const [taskOpen, setTaskOpen] = useState(false);
  const [gearOpen, setGearOpen] = useState(false);
  const gItem: any = { display: "flex", alignItems: "center", gap: 8, padding: "9px 13px", fontSize: 13.5, cursor: "pointer", borderBottom: "1px solid #f6f8fb" };
  const [deal, setDeal] = useState<Deal | null>(null);
  const [discMode, setDiscMode] = useState<Record<number, "pct" | "amt">>({});   // режим скидки на позицию: % или ₴
  const { t } = useLang();
  const [chatW, setChatW] = useState(() => Number(localStorage.getItem("crm_card_chatW")) || 360);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [allFunnels, setAllFunnels] = useState<any[]>([]);
  const [tab, setTab] = useState<"general" | "items" | "cashflow" | "np" | "smeta">(() => (localStorage.getItem("deal_tab") as any) || "general");
  useEffect(() => { try { localStorage.setItem("deal_tab", tab); } catch (e) { /* noop */ } }, [tab]);
  const [docOpen, setDocOpen] = useState(false);
  const [vkOpen, setVkOpen] = useState(false);
  const [addProd, setAddProd] = useState(0);
  const [addQty, setAddQty] = useState(1);
  const [psearch, setPsearch] = useState(""); const [presults, setPresults] = useState<Product[]>([]); const [psel, setPsel] = useState<Product | null>(null); const [addReserve, setAddReserve] = useState(false); const [showList, setShowList] = useState(false);
  const [editProdItem, setEditProdItem] = useState<number>(0); const [epq, setEpq] = useState(""); const [epr, setEpr] = useState<Product[]>([]);
  const epBoxRef = useRef<HTMLDivElement>(null);
  const [payOpen, setPayOpen] = useState(false);
  const [ciOpen, setCiOpen] = useState(false);
  const [ci, setCi] = useState<any>({ name: "", qty: 1, price: "" });
  const [payAmount, setPayAmount] = useState("");
  const [payType, setPayType] = useState("cash");
  const [cashReceipt, setCashReceipt] = useState(false);
  const [advAvail, setAdvAvail] = useState<number | null>(null);
  useEffect(() => {
    if (payOpen && payType === "advance" && deal?.contact_id) {
      api.get<any>(`/api/contacts/${deal.contact_id}/finance/`).then((d: any) => setAdvAvail(Number(d?.advance || 0))).catch(() => setAdvAvail(null));
    }
  }, [payOpen, payType, deal?.contact_id]);
  const [debtList, setDebtList] = useState<any[]>([]);
  const [selDebts, setSelDebts] = useState<number[]>([]);
  useEffect(() => {
    if (payOpen && deal?.contact_id) {
      api.get<any>(`/api/planned-payments/?kind=receivable&status=planned&page_size=200`).then((r: any) => setDebtList(((r.results || r) as any[]).filter((x: any) => x.contact === deal.contact_id))).catch(() => setDebtList([]));
    } else { setDebtList([]); setSelDebts([]); }
  }, [payOpen, deal?.contact_id]);
  const [verify, setVerify] = useState<any>(null);   // крок 2 — вікно перевірки платежу (воронка салону)
  const [vRefs, setVRefs] = useState<any>({ accs: [], cats: [], dirs: [] });
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
  const [cliFieldsOpen, setCliFieldsOpen] = useState(false);
  const [cliForm, setCliForm] = useState<any>({ first_name: "", last_name: "", middle_name: "", nickname: "", phone: "", social_link: "", email: "", comment: "" });
  const [reqFields, setReqFields] = useState<string[]>([]);
  const [cfgCanEdit, setCfgCanEdit] = useState(false);
  const [cfgIsAdmin, setCfgIsAdmin] = useState(false);
  const [cfgEditors, setCfgEditors] = useState<number[]>([]);
  const [cfgOpen, setCfgOpen] = useState(false);
  const [cfgStaff, setCfgStaff] = useState<any[]>([]);
  const fIn: any = { width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", fontSize: 13, boxSizing: "border-box" };
  const lblS: any = { fontSize: 10.5, color: "#94a3b8", marginBottom: 2, fontWeight: 600, textTransform: "lowercase" };
  const [ttnOpen, setTtnOpen] = useState(false); const [ttnSending, setTtnSending] = useState(false);
  const [ttnName, setTtnName] = useState(""); const [ttnPhone, setTtnPhone] = useState("");
  const [ttnCityQ, setTtnCityQ] = useState(""); const [ttnCities, setTtnCities] = useState<any[]>([]); const [ttnCity, setTtnCity] = useState<any>(null);
  const [ttnWhs, setTtnWhs] = useState<any[]>([]); const [ttnWh, setTtnWh] = useState<any>(null);
  const [ttnWeight, setTtnWeight] = useState("0.5"); const [ttnSeats, setTtnSeats] = useState("1");
  const [ttnCost, setTtnCost] = useState(""); const [ttnCod, setTtnCod] = useState(""); const [ttnService, setTtnService] = useState("WarehouseWarehouse");

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
    api.get<any>("/api/funnels/").then((f) => setAllFunnels(f.results || f)).catch(() => {});
  }, [id]);
  // live-оновлення стадії/відповідального без перезавантаження (не чіпає поля сделки)
  useEffect(() => {
    if (!id) return;
    const tm = setInterval(async () => {
      try {
        const d = await api.get<Deal>(`/api/deals/${id}/`);
        setDeal((cur) => {
          if (!cur) return cur;
          // НЕ чіпаємо qualification + items — їх редагує менеджер (інакше збиває фокус при наборі)
          if (cur.stage === d.stage && cur.owner === d.owner && (cur as any).amount === (d as any).amount && (cur as any).is_seen === (d as any).is_seen) return cur;
          return { ...cur, stage: d.stage, owner: d.owner, owner_name: (d as any).owner_name, is_seen: (d as any).is_seen, amount: (d as any).amount, payments: (d as any).payments, paid: (d as any).paid };
        });
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(tm);
  }, [id]);
  useEffect(() => {
    if (deal?.conversation_id) api.get<any>(`/api/conversations/${deal.conversation_id}/messages/`).then(setChat).catch(() => setChat([]));
    else setChat([]);
  }, [deal?.conversation_id]);

  /* ─── [5] ДЕЙСТВИЯ ───────────────────────────────────────────────────── */
  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 2800); };
  async function patch(body: Record<string, unknown>) { await api.patch(`/api/deals/${id}/`, body); load(); }
  const [titleEdit, setTitleEdit] = useState(false); const [titleVal, setTitleVal] = useState("");
  async function saveTitle() { const v = titleVal.trim(); if (!v) { setTitleEdit(false); return; } try { await api.patch(`/api/deals/${id}/`, { title: v }); setDeal((d) => (d ? { ...d, title: v } : d)); } catch { flash(t("Нет прав на изменение","Немає прав на зміну")); } setTitleEdit(false); }

  // Перетягування правого краю → ширина чату (спільна для всіх карток CRM)
  function startResize(e: any) {
    e.preventDefault();
    const startX = e.clientX, startW = chatW; let w = startW;
    function mv(ev: MouseEvent) { w = Math.min(760, Math.max(280, startW + (startX - ev.clientX))); setChatW(w); }
    function up() { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); localStorage.setItem("crm_card_chatW", String(w)); }
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }

  async function setStage(stageId: number) {
    try { await api.patch(`/api/deals/${id}/`, { stage: stageId }); load(); }
    catch (e: any) {
      if (e?.data?.confirm_unpaid) {
        if (confirm(e.data.warn || t("Сделка оплачена не полностью. Точно перенести?","Угода оплачена не повністю. Точно перенести?"))) {
          try { await api.patch(`/api/deals/${id}/`, { stage: stageId, confirm_unpaid: 1 }); load(); } catch { flash(t("Ошибка переноса","Помилка перенесення")); }
        }
      } else { flash(t("Нет прав на перенос стадии","Немає прав на перенос стадії")); }
    }
  }
  async function changeFunnel(fid: number) {
    if (!deal || fid === deal.funnel) return;
    const nf = allFunnels.find((f: any) => f.id === fid);
    if (!nf || !nf.stages?.length) return;
    const cf = allFunnels.find((f: any) => f.id === deal.funnel);
    const curName = ((cf?.stages || []).find((s: any) => s.id === deal.stage)?.name || "").trim();
    const keep = (nf.stages || []).some((s: any) => (s.name || "").trim().toLowerCase() === curName.toLowerCase());
    const msg = keep
      ? t("Перенести сделку в воронку «" + nf.name + "»? Стадия «" + curName + "» сохранится, все автоматизации продолжат работать.",
          "Перенести угоду у воронку «" + nf.name + "»? Стадія «" + curName + "» збережеться, всі автоматизації продовжать працювати.")
      : t("Перенести в воронку «" + nf.name + "»? В ней нет такой же стадии «" + curName + "» — сделка встанет на первую стадию новой воронки.",
          "Перенести у воронку «" + nf.name + "»? У ній немає такої ж стадії «" + curName + "» — угода стане на першу стадію нової воронки.");
    if (!confirm(msg)) return;
    await api.post(`/api/deals/${id}/change_funnel/`, { funnel: fid });
    flash(t("Воронка изменена", "Воронку змінено"));
    load();
  }

  async function confirmItems() {
    try { const d = await api.post<any>(`/api/deals/${id}/confirm_items/`, {}); setDeal(d); flash(t("✓ Список сохранён · стадия → Розрахунок здійснено","✓ Список збережено · стадія → Розрахунок здійснено")); }
    catch { flash(t("Сначала добавьте товары","Спершу додайте товари")); }
  }
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
  // поиск для ПЕРЕВЫБОРА товара в позиции
  useEffect(() => {
    if (!editProdItem || !epq.trim()) { setEpr([]); return; }
    const t = setTimeout(() => api.get<Paginated<Product>>(`/api/products/?search=${encodeURIComponent(epq)}&page_size=10`).then((d) => setEpr(d.results)).catch(() => setEpr([])), 250);
    return () => clearTimeout(t);
  }, [epq, editProdItem]);
  async function reselectItemProduct(itemId: number, prodId: number) {
    setDeal(await api.post<Deal>(`/api/deals/${id}/update_item/`, { item: itemId, product: prodId }));
    setEditProdItem(0); setEpq(""); setEpr([]);
  }
  async function toggleReserve(it: any) {
    setDeal(await api.post<Deal>(`/api/deals/${id}/set_reserve/`, { item: it.id, reserved: !it.reserved }));
  }
  async function updateItem(itemId: number, body: any) {
    setDeal(await api.post<Deal>(`/api/deals/${id}/update_item/`, { item: itemId, ...body }));
  }
  async function addCustomItem() {
    if (!ci.name.trim() || Number(ci.qty) <= 0 || Number(ci.price) < 0) { flash(t("Впиши название, количество и цену","Впиши назву, кількість і ціну")); return; }
    try {
      setDeal(await api.post<Deal>(`/api/deals/${id}/add_item/`, { custom_name: ci.name.trim(), quantity: ci.qty, price: ci.price }));
      setCi({ name: "", qty: 1, price: "" }); setCiOpen(false);
      flash(t("✓ Позиция добавлена (без складского учёта)","✓ Позицію додано (без складського обліку)"));
    } catch (e: any) { flash(e?.response?.data?.detail || t("Не удалось добавить","Не вдалося додати")); }
  }
  async function removeItem(item: number) { setDeal(await api.post<Deal>(`/api/deals/${id}/remove_item/`, { item })); }

  const salonFunnel = (((deal as any)?.funnel_name || "") as string).toLowerCase().includes("покры") || (((deal as any)?.funnel_name || "") as string).toLowerCase().includes("покрит");
  const inpV: any = { width: "100%", height: 36, marginBottom: 10, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13 };
  async function openVerify() {
    setSending(true);
    try {
      const [aRes, cRes, dRes] = await Promise.all([
        api.get<any>("/api/accounts/"), api.get<any>("/api/categories/?page_size=500"), api.get<any>("/api/fin-directions/?page_size=200")]);
      const accs = ((aRes.results || aRes) as any[]).filter((x: any) => x.is_active !== false);
      const cats = ((cRes.results || cRes) as any[]).filter((x: any) => x.direction === "in" && !x.hidden);
      const dirs = (dRes.results || dRes) as any[];
      const defAcc = accs.find((x: any) => (x.name || "").toLowerCase().includes("касса салон")) || accs[0];
      const defCat = cats.find((x: any) => x.name === "САЛОН(Оффлайн)") || cats[0];
      setVRefs({ accs, cats, dirs });
      setVerify({
        mode: payType === "credit" ? "credit" : "pay",
        amount: payAmount || String(deal?.amount || ""),
        account: defAcc?.id || 0, category: defCat?.id || 0,
        direction: defCat?.fin_direction || 0,
        counterparty: ((deal as any)?.contact_name || "") as string,
        channel: "Салон", comment: "", ship: true, days: 14,
      });
    } catch { flash(t("Не удалось загрузить справочники","Не вдалося завантажити довідники")); }
    finally { setSending(false); }
  }
  async function confirmVerify() {
    if (!verify) return;
    setSending(true);
    try {
      if (verify.mode === "credit") {
        let r: any;
        try {
          r = await api.post<any>(`/api/deals/${id}/credit_sale/`, { amount: verify.amount, days: verify.days, ship: verify.ship ? 1 : 0 });
        } catch (err: any) {
          if (err?.response?.status === 409 && err?.response?.data?.need_force) {
            if (!confirm(err.response.data.detail)) { setSending(false); return; }
            r = await api.post<any>(`/api/deals/${id}/credit_sale/`, { amount: verify.amount, days: verify.days, ship: verify.ship ? 1 : 0, force: 1 });
          } else { throw err; }
        }
        setDeal(r.deal);
        setVerify(null); setPayOpen(false); setPayAmount("");
        flash(t("✓ Дебиторка создана: долг виден в Финансы → Дт/Кт и в карточке клиента. «Оплачено» там создаст доход.","✓ Дебіторку створено: борг видно у Фінанси → Дт/Кт і в картці клієнта. «Оплачено» там створить дохід."));
      } else {
        const body: any = { amount: verify.amount, provider: payType, no_receipt: payType === "cash" && !cashReceipt ? 1 : 0,
          tx_account: verify.account, tx_category: verify.category, tx_direction: verify.direction,
          tx_counterparty: verify.counterparty, tx_channel: verify.channel, tx_comment: verify.comment,
          no_warehouse: verify.ship ? 0 : 1, debt_ids: selDebts };
        try {
          setDeal(await api.post<Deal>(`/api/deals/${id}/accept_payment/`, body));
        } catch (err: any) {
          if (err?.response?.status === 409 && err?.response?.data?.need_force) {
            if (!confirm(err.response.data.detail)) { setSending(false); return; }
            setDeal(await api.post<Deal>(`/api/deals/${id}/accept_payment/`, { ...body, force: 1 }));
          } else { throw err; }
        }
        setVerify(null); setPayOpen(false); setPayAmount("");
        flash(t("✓ Оплата проведена в финансы","✓ Оплата проведена у фінанси"));
      }
    } catch (e: any) { flash(e?.response?.data?.detail || t("Не удалось провести","Не вдалося провести")); }
    finally { setSending(false); }
  }
  async function acceptPayment() {
    if (salonFunnel && (payType === "cash" || payType === "terminal" || payType === "credit")) { await openVerify(); return; }
    setSending(true);
    try {
      if (payType === "liqpay" || payType === "requisites" || payType === "installment") {
        const r = await api.post<any>(`/api/deals/${id}/send_pay_link/`, { kind: payType, amount: payAmount || deal?.amount });
        const d = await api.get<Deal>(`/api/deals/${id}/`); setDeal(d);
        setPayOpen(false); setPayAmount("");
        try { await navigator.clipboard.writeText(r.url); } catch (er) { /* noop */ }
        flash((r.sent ? t("✓ Отправлено в чат. Ссылка скопирована в буфер: ","✓ Надіслано в чат. Посилання скопійовано в буфер: ") : t("⚠ Чата нет. Ссылка СКОПИРОВАНА в буфер — вставь клиенту вручную: ","⚠ Чату немає. Посилання СКОПІЙОВАНО в буфер — встав клієнту вручну: ")) + r.url);
      } else {
        try {
          setDeal(await api.post<Deal>(`/api/deals/${id}/accept_payment/`, { amount: payAmount || deal?.amount, provider: payType, no_receipt: payType === "cash" && !cashReceipt ? 1 : 0, debt_ids: selDebts }));
        } catch (err: any) {
          // захист від дубля: сервер просить підтвердження (по сделці є LiqPay-посилання/оплата на цю суму)
          if (err?.response?.status === 409 && err?.response?.data?.need_force) {
            if (!confirm(err.response.data.detail)) { setSending(false); return; }
            setDeal(await api.post<Deal>(`/api/deals/${id}/accept_payment/`, { amount: payAmount || deal?.amount, provider: payType, force: 1, no_receipt: payType === "cash" && !cashReceipt ? 1 : 0, debt_ids: selDebts }));
          } else { throw err; }
        }
        setPayOpen(false); setPayAmount(""); flash(t("✓ Оплата проведена в финансы","✓ Оплата проведена у фінанси"));
      }
    } catch (e: any) { flash(e?.response?.data?.detail || t("Не удалось — проверь сумму / сеть","Не вдалося — перевір суму / мережу")); }
    finally { setSending(false); }
  }
  async function ship() {
    try { const r = await api.post<any>(`/api/deals/${id}/ship/`, {}); setDeal(r.deal); flash(t(`✓ Отгружено. Со склада списано на ${r.cogs} ₴ по закупке (деньги не трогаются)`, `✓ Відвантажено. Зі складу списано на ${r.cogs} ₴ по закупці (гроші не чіпаються)`)); }
    catch { flash(t("В сделке нет товаров для отгрузки","В угоді немає товарів для відвантаження")); }
  }
  // TODO боевой режим: завести @action в DealViewSet поверх integrations/adapters.py
  //      (np_create_ttn / checkbox_create_receipt / liqpay_checkout_link). Сейчас — заглушки.
  function createTTN() {
    setTtnName(((deal as any)?.contact_name) || ""); setTtnPhone(((deal as any)?.contact_phone) || "");
    setTtnCost(String(deal?.amount || "")); setTtnCod(((deal as any)?.pay_type === "prepay_np" && remaining > 0) ? String(remaining) : "");
    setTtnCity(null); setTtnCityQ(""); setTtnCities([]); setTtnWhs([]); setTtnWh(null); setTtnOpen(true);
  }
  async function pickCity(c: any) {
    setTtnCity(c); setTtnCityQ(c.present || c.name); setTtnCities([]); setTtnWh(null); setTtnWhs([]);
    try { setTtnWhs(await api.get<any[]>(`/api/deals/np_warehouses/?settlement_ref=${encodeURIComponent(c.settlement_ref)}`)); } catch { /* */ }
  }
  async function submitTTN() {
    if (!ttnCity || !ttnWh) { flash(t("Выберите город и отделение","Виберіть місто і відділення")); return; }
    if (!ttnName || !ttnPhone) { flash(t("Укажите получателя и телефон","Вкажіть отримувача і телефон")); return; }
    setTtnSending(true);
    try {
      const r = await api.post<any>(`/api/deals/${id}/create_ttn/`, {
        recipient_name: ttnName, recipient_phone: ttnPhone,
        recipient_city_name: ttnCity.name, recipient_area: ttnCity.area, recipient_region: ttnCity.region,
        warehouse_number: ttnWh.number, weight: ttnWeight, seats: ttnSeats, cost: ttnCost,
        service_type: ttnService, cod_amount: ttnCod || 0, payer: "Recipient", payment_method: "Cash",
      });
      const d = await api.get<Deal>(`/api/deals/${id}/`); setDeal(d); setTtnOpen(false);
      flash(r.sent ? t(`✓ ТТН ${r.ttn} создана и отправлена клиенту`, `✓ ТТН ${r.ttn} створена і надіслана клієнту`) : t(`✓ ТТН ${r.ttn} создана`, `✓ ТТН ${r.ttn} створена`));
    } catch (e: any) { flash(t("Ошибка НП: ", "Помилка НП: ") + (e?.response?.data?.detail || e?.message || "")); }
    finally { setTtnSending(false); }
  }
  async function issueCheckbox() {
    try {
      const r = await api.post<any>(`/api/deals/${id}/issue_checkbox/`, {});
      const d = await api.get<Deal>(`/api/deals/${id}/`); setDeal(d);
      if (r.already) { flash(t("Чек уже создан","Чек вже створено")); return; }
      flash(r.sent ? t("✓ Фискальный чек создан и отправлен клиенту","✓ Фіскальний чек створено і надіслано клієнту")
                   : t("✓ Чек создан (нет открытого чата)","✓ Чек створено (немає чату для надсилання)"));
    } catch (e: any) {
      flash(t("Ошибка Checkbox: ","Помилка Checkbox: ") + (e?.response?.data?.detail || e?.message || ""));
    }
  }
  function sendPayLink() { if (!deal) return; const rem = Number(deal.amount) - (deal.paid || 0); setPayAmount(String(rem > 0 ? rem : deal.amount)); setPayOpen(true); }
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
  useEffect(() => {
    if (!ttnOpen || ttnCity || ttnCityQ.trim().length < 2) return;
    const tm = setTimeout(() => api.get<any[]>(`/api/deals/np_cities/?q=${encodeURIComponent(ttnCityQ)}`).then(setTtnCities).catch(() => setTtnCities([])), 350);
    return () => clearTimeout(tm);
  }, [ttnCityQ, ttnOpen, ttnCity]);
  async function setContact(cid: number) { await api.patch(`/api/deals/${id}/`, { contact: cid }); setCliEdit(false); setCliSearch(""); setCliResults([]); setCliNew(false); load(); }
  async function removeContact() { if (!confirm(t("Убрать клиента из сделки?","Прибрати клієнта з угоди?"))) return; await api.patch(`/api/deals/${id}/`, { contact: null }); load(); }
  async function delDeal() {
    if (!confirm(t("Удалить сделку безвозвратно? Действие необратимо.","Видалити угоду безповоротно? Дію не відмінити."))) return;
    try { await api.del("/api/deals/" + id + "/"); flash(t("Сделка удалена","Угоду видалено")); nav(-1); }
    catch (e: any) { flash(e?.response?.data?.detail || t("Нет прав на удаление","Немає прав на видалення")); }
  }
  async function resetClient() {
    if (!confirm(t("ТЕСТ: удалить ВСЕ данные клиента (лиды/сделки/чаты)? Он зайдёт как новый.","ТЕСТ: видалити ВСІ дані клієнта (ліди/сделки/чати)? Зайде як новий."))) return;
    try { await api.post("/api/contacts/" + (deal as any).contact_id + "/reset/", {}); flash(t("Клиент сброшен — зайдёт как новый","Клієнта скинуто — зайде як новий")); nav(-1); }
    catch (e: any) { flash(e?.response?.data?.detail || t("Нет прав","Немає прав")); }
  }
  async function dozakazDeal() {
    try { const r = await api.post<any>(`/api/deals/${id}/dozakaz/`, {}); flash(t("Создан дозаказ (одна посылка)","Створено дозамовлення (одна посилка)")); nav("/deals/" + r.id); }
    catch { flash(t("Ошибка создания дозаказа","Помилка створення дозамовлення")); }
  }
  async function dupDeal() {
    try { const r = await api.post<any>("/api/deals/", { title: (deal?.title || "") + t(" (копия)"," (копія)"), contact: (deal as any)?.contact_id || null, funnel: (deal as any)?.funnel, stage: (deal as any)?.stage, amount: deal?.amount }); flash(t("Создана копия","Створено копію")); nav("/deals/" + r.id); }
    catch (e: any) { flash(e?.response?.data?.detail || t("Не удалось дублировать","Не вдалося дублювати")); }
  }
  async function openCliEdit() {
    setCliEdit(false);
    try {
      const c = await api.get<any>(`/api/contacts/${(deal as any).contact_id}/`);
      setCliForm({ first_name: c.first_name || "", last_name: c.last_name || "", middle_name: c.middle_name || "", nickname: c.nickname || "", phone: c.phone || "", social_link: c.social_link || "", email: c.email || "", comment: c.comment || "" });
    } catch { setCliForm({ first_name: "", last_name: "", middle_name: "", nickname: "", phone: (deal as any)?.contact_phone || "", social_link: (deal as any)?.contact_social_link || "", email: "", comment: "" }); }
    try { const cf = await api.get<any>(`/api/contact-form-config/`); setReqFields(cf.required || []); setCfgCanEdit(!!cf.can_edit); setCfgIsAdmin(!!cf.is_admin); setCfgEditors(cf.editors || []); } catch { /* ignore */ }
    setCliFieldsOpen(true);
  }
  const REQ_LBL: any = { first_name: t("имя","імʼя"), last_name: t("фамилия","прізвище"), middle_name: t("отчество","по батькові"), nickname: t("ник","нік"), phone: t("телефон","телефон"), social_link: "instagram", email: "email" };
  async function saveCliFields() {
    if (!(deal as any)?.contact_id) return;
    const miss = (reqFields || []).filter((fld) => !String(cliForm[fld] || "").trim());
    if (miss.length) { flash(t("Заполни обязательные: ","Заповни обовʼязкові: ") + miss.map((x) => REQ_LBL[x] || x).join(", ")); return; }
    try { await api.patch(`/api/contacts/${(deal as any).contact_id}/`, cliForm); } catch { flash(t("Ошибка сохранения","Помилка збереження")); return; }
    setCliFieldsOpen(false); load();
  }
  async function saveReqCfg(required: string[], editors?: number[]) {
    try { const d = await api.patch<any>(`/api/contact-form-config/`, editors !== undefined ? { required, editors } : { required }); setReqFields(d.required || []); if (d.editors) setCfgEditors(d.editors); flash(t("✓ Сохранено","✓ Збережено")); }
    catch { flash(t("Нет прав менять настройку","Немає прав змінювати налаштування")); }
  }
  function toggleCfg() { setCfgOpen((v) => !v); if (cfgStaff.length === 0 && cfgIsAdmin) api.get<any>("/api/conversations/staff/").then((d) => setCfgStaff(((d.results || d) as any[]))).catch(() => {}); }
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
  if (notFound) return <div className="scroll pad fade"><div className="panel" style={{ textAlign: "center", padding: 40 }}><h3>{t("Сделка не найдена","Угоду не знайдено")}</h3><div className="muted" style={{ marginBottom: 16 }}>{t("Возможно, она удалена или изменён ID после переноса из Битрикса. Открой из списка сделок.","Можливо, її видалено або змінено ID після перенесення з Бітрикса. Відкрий зі списку угод.")}</div><button className="btn btn-primary" onClick={() => nav("/deals")}>{t("← К списку сделок","← До списку угод")}</button></div></div>;
  if (!deal) return <div className="spin">{t("Завантаження угоди…","Завантаження угоди…")}</div>;
  const curOrder = funnel?.stages.find((s) => s.id === deal.stage)?.order ?? 0;
  const remaining = Number(deal.amount) - deal.paid;
  const inp: any = { width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13, boxSizing: "border-box" };
  const disc = Number(deal.discount_pct || 0);
  const loyalty = deal.contact_loyalty || "";
  const hasCheck = !!deal.checkbox_status && deal.checkbox_status !== "none";
  // Лента событий из реальных данных (оплаты + системное «создана»):
  const events = [
    ...deal.payments.map((p) => ({ t: p.created_at, kind: "pay", text: t(`Оплата ${fmt(Number(p.amount))} ₴ · ${p.provider}`, `Оплата ${fmt(Number(p.amount))} ₴ · ${p.provider}`) })),
    { t: deal.payments[0]?.created_at || "", kind: "sys", text: t("Сделка создана","Угоду створено") },
  ].filter((e) => e.t);

  return (
    <div className="scroll fade">

      {/* ─── [7] РЕНДЕР: шапка ─────────────────────────────────────────── */}
      <div className="dealhead">
        <button className="back" title="Назад" onClick={() => onClose ? onClose() : (loc.key !== "default" ? nav(-1) : nav("/deals"))}>←</button>
        <b style={{ fontSize: 16 }}><span title={t("Клик — скопировать № (идентификатор для оплат)","Клік — скопіювати № (ідентифікатор для оплат)")} style={{ cursor: "pointer" }} onClick={() => { navigator.clipboard?.writeText(String(deal.id)); flash(t("№ "+deal.id+" скопирован","№ "+deal.id+" скопійовано")); }}>#{deal.id}</span> · {titleEdit ? (
          <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
            <input value={titleVal} autoFocus onChange={(e) => setTitleVal(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") saveTitle(); if (e.key === "Escape") setTitleEdit(false); }} style={{ fontSize: 15, fontWeight: 700, padding: "3px 7px", borderRadius: 6, border: "1px solid #cbd5e1", minWidth: 200 }} />
            <button className="btn btn-primary" style={{ padding: "3px 9px" }} onClick={saveTitle}>✓</button>
            <button className="btn btn-light" style={{ padding: "3px 9px" }} onClick={() => setTitleEdit(false)}>✕</button>
          </span>
        ) : (<span style={{ cursor: "pointer" }} title={t("Клик — изменить название","Клік — змінити назву")} onClick={() => { setTitleVal(deal.title); setTitleEdit(true); }}>{deal.title} <span style={{ fontSize: 11, opacity: .45 }}><Icon n="✏️" size={11} /></span></span>)}</b>
        <button className="btn" title={t("Скопировать ссылку на сделку","Скопіювати посилання на угоду")} onClick={() => { navigator.clipboard?.writeText(window.location.origin+"/deals/"+deal.id); flash(t("Ссылка скопирована","Посилання скопійовано")); }}><Icon n="🔗" size={16} /></button>
        {deal.is_seen ? <span style={{ fontSize: 11, fontWeight: 700, color: "#16a34a", background: "#dcfce7", padding: "2px 9px", borderRadius: 20, whiteSpace: "nowrap" }} title={t("Ответили клиенту","Відповіли клієнту")}>✓ {t("Відповіли","Відповіли")}</span> : <span style={{ fontSize: 11, fontWeight: 700, color: "#fff", background: "#ef4444", padding: "2px 9px", borderRadius: 20, whiteSpace: "nowrap", boxShadow: "0 0 0 3px rgba(239,68,68,.18)" }} title={t("Клиент написал — не отвечено","Клієнт написав — не відповіли")}>● {t("Не отвечено","Не відповіли")}</span>}
        {allFunnels.length ? (
          <select value={deal.funnel} onChange={(e) => changeFunnel(Number(e.target.value))} title={t("Воронка сделки — можно сменить","Воронка угоди — можна змінити")} style={{ height: 30, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 13, background: "#fff", cursor: "pointer", maxWidth: 230 }}>
            {allFunnels.filter((f: any) => !f.is_lead_funnel).map((f: any) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        ) : <span className="muted">{funnel?.name}</span>}
        {deal.created_at && <span className="muted" style={{ fontSize: 12.5, whiteSpace: "nowrap" }} title={t("Сделка появилась","Угода зʼявилась")}><Icon n="🕓" size={14} /> {new Date(deal.created_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>}
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        {deal.contact_id && <CallButton contact={deal.contact_id} small />}
        <div style={{ position: "relative" }}>
          <button className="btn" title={t("Действия со сделкой","Дії з угодою")} onClick={() => setGearOpen((v) => !v)}><Icon n="settings" size={16} /></button>
          {gearOpen ? (
            <div onMouseLeave={() => setGearOpen(false)} style={{ position: "absolute", top: 42, right: 0, width: 240, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 14px 36px rgba(0,0,0,.18)", zIndex: 41, overflow: "hidden" }}>
              <div onClick={() => { setGearOpen(false); navigator.clipboard?.writeText(window.location.origin + "/deals/" + deal.id); flash(t("Ссылка скопирована", "Посилання скопійовано")); }} style={gItem}><Icon n="🔗" size={15} /> {t("Копировать ссылку", "Копіювати посилання")}</div>
              {deal.contact_id ? <div onClick={() => { setGearOpen(false); nav("/clients/" + deal.contact_id); }} style={gItem}><Icon n="👤" size={15} /> {t("Карточка клиента", "Картка клієнта")}</div> : null}
              <div onClick={() => { setGearOpen(false); dupDeal(); }} style={gItem}><Icon n="📄" size={15} /> {t("Дублировать сделку", "Дублювати угоду")}</div>
              <div onClick={() => { setGearOpen(false); dozakazDeal(); }} style={gItem}><Icon n="➕" size={15} /> {t("Дозаказ (одна посылка)", "Дозамовлення (одна посилка)")}</div>
              {(can("roles.manage") && deal.contact_id) ? <div onClick={() => { setGearOpen(false); resetClient(); }} style={{ ...gItem, color: "#b45309" }}><Icon n="trash" size={15} /> {t("Сбросить клиента (тест)","Скинути клієнта (тест)")}</div> : null}
              {can("deal.delete") ? <div onClick={() => { setGearOpen(false); delDeal(); }} style={{ ...gItem, color: "#dc2626", borderTop: "1px solid #f1f5f9", borderBottom: "none" }}><Icon n="trash" size={15} /> {t("Удалить сделку", "Видалити угоду")}</div> : null}
            </div>
          ) : null}
        </div>
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
        <button className={"btn" + (tab === "general" ? " btn-primary" : "")} onClick={() => setTab("general")}><Icon n="💬" size={15} /> {t("Лента / Чат","Стрічка / Чат")}</button>
        <button className={"btn" + (tab === "items" ? " btn-primary" : "")} onClick={() => setTab("items")}><Icon n="📦" size={15} /> {t("Товары","Товари")} ({deal.items.length})</button>
        <button className={"btn" + (tab === "np" ? " btn-primary" : "")} onClick={() => setTab("np")}><Icon n="🚚" size={15} /> {t("Новая почта","Нова Пошта")}</button>
        {can("deal.smeta.tab") && <button className={"btn" + (tab === "smeta" ? " btn-primary" : "")} onClick={() => setTab("smeta")}><Icon n="📐" size={15} /> {t("Смета","Кошторис")}</button>}
        <button className="btn" style={{ padding: "0 10px" }} title={t("Накладная / КП (документ)","Накладна / КП (документ)")} onClick={() => setDocOpen(true)}><Icon n="file" size={16} /></button>
        <button className="btn" style={{ padding: "0 10px" }} title={t("Печать бланка выкраски","Друк бланка викраски")} onClick={() => setVkOpen(true)}><Icon n="palette" size={16} /></button>
        <div style={{ width: 1, height: 24, background: "#cbd5e1", margin: "0 6px" }} />
        <button className="btn" onClick={issueCheckbox}><Icon n="🧾" size={15} /> {t("Checkbox","Checkbox")}</button>
        <button className="btn" onClick={() => setTaskOpen(true)} title={t("Поставить задачу по сделке","Поставити задачу по угоді")}><Icon n="check" size={15} /> {t("Задача","+ Задача")}</button>
        {deal.contact_id && (
          <div id={`deal-reply-channel-${deal.id}`} data-testid="deal-reply-channel-target"
            style={{ marginLeft: "auto", minWidth: 260, maxWidth: 380, flex: "0 1 380px" }} />
        )}
      </div>

      {taskOpen && <TaskQuickModal prefill={{ deal: deal.id, deal_title: deal.title, contact: deal.contact_id }} onClose={() => setTaskOpen(false)} onSaved={() => setTaskOpen(false)} />}

      {(tab === "smeta" && can("deal.smeta.tab")) ? (
        <DealEstimatePanel dealId={deal.id} />
      ) : tab === "np" ? (<NPDelivery deal={deal} flash={flash} onReload={() => api.get<Deal>(`/api/deals/${id}/`).then(setDeal)} />) : tab !== "cashflow" ? (
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div className="grid2" style={{ flex: 1, minWidth: 0 }}>

        {/* ─── [10] РЕНДЕР: левая колонка — данные заказа ───────────────── */}
        <div>
          {/* 10.1 Клиент — інлайн вибір/зміна/прибирання (без попапів) */}
          <div className="panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="label">{t("Клиент","Клієнт")}</div>
              {deal.contact_id && !cliEdit && !cliFieldsOpen && (
                <span style={{ fontSize: 11, display: "flex", gap: 10 }}>
                  <span style={{ color: "#2563eb", cursor: "pointer" }} onClick={openCliEdit}><Icon n="✏️" size={12} /> {t("Изменить","Змінити")}</span>
                  <span style={{ color: "#64748b", cursor: "pointer" }} title={t("Привязать другого клиента","Привʼязати іншого клієнта")} onClick={() => { setCliEdit(true); setCliNew(false); }}>↺ {t("Другой","Інший")}</span>
                  <span style={{ color: "#dc2626", cursor: "pointer" }} onClick={removeContact}>{t("✕ Убрать","✕ Прибрати")}</span>
                </span>
              )}
            </div>
            {deal.contact_id && !cliEdit && !cliFieldsOpen ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600 }}>{deal.contact_name || t("Без контакта","Без контакту")}</span>
                  {loyalty && <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: (LOYALTY_COLOR[loyalty] || "#64748b") + "22", color: LOYALTY_COLOR[loyalty] || "#64748b" }}>{loyalty}</span>}
                </div>
                {(deal.contact_phone || deal.contact_social_link) && (
                  <div style={{ marginTop: 6, fontSize: 12.5, display: "flex", flexDirection: "column", gap: 3 }}>
                    {deal.contact_phone && <a href={`tel:${deal.contact_phone}`} style={{ color: "#0f172a", fontWeight: 600 }}><Icon n="📱" size={13} /> {deal.contact_phone}</a>}
                    {deal.contact_social_link && <SocialLink link={deal.contact_social_link} />}
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  <button className="btn" style={{ flex: 1, background: "#ecfdf5", color: "#047857" }}><Icon n="📞" size={14} /> {t("Позвонить","Подзвонити")}</button>
                  <button className="btn" style={{ flex: 1, background: "#eff6ff", color: "#1d4ed8" }} onClick={() => deal.conversation_id ? nav(`/inbox?c=${deal.conversation_id}`) : setTab("general")}><Icon n="💬" size={14} /> {t("Чат","Чат")}</button>
                  <button className="btn" style={{ background: "#f1f5f9" }} title={t("Карточка клиента","Картка клієнта")} onClick={() => nav(`/clients/${deal.contact_id}`)}>{t("Клиент →","Клієнт →")}</button>
                </div>
                <div style={{ marginTop: 10 }}>
                  <div className="label" style={{ fontSize: 11 }}>{t("Источник (общий для клиента)","Джерело (спільне для клієнта)")}</div>
                  <select value={deal.source || ""} onChange={async (e) => { const v = e.target.value; try { await api.patch(`/api/contacts/${deal.contact_id}/`, { source: v }); load(); } catch { /* */ } }}
                    style={{ width: "100%", height: 32, border: "1px solid #cbd5e1", borderRadius: 7, fontSize: 12.5 }}>
                    <option value="">—</option>
                    {Object.keys(SOURCES).map((k) => <option key={k} value={k}>{(SOURCES as any)[k][0]}</option>)}
                  </select>
                </div>
              </>
            ) : cliFieldsOpen ? (
              <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 8 }}>
                {(() => {
                  const F = (fld: string, label: string, ph: string, auto?: boolean) => {
                    const req = reqFields.includes(fld);
                    const empty = !String(cliForm[fld] || "").trim();
                    return (<div style={{ flex: 1 }}><div style={lblS}>{label}{req && <span style={{ color: "#dc2626" }}> *</span>}</div>
                      <input value={cliForm[fld] || ""} autoFocus={auto} onChange={(e) => setCliForm({ ...cliForm, [fld]: e.target.value })} placeholder={ph} style={{ ...fIn, border: "1px solid " + (req && empty ? "#fca5a5" : "#cbd5e1") }} /></div>);
                  };
                  return (<>
                    <div style={{ display: "flex", gap: 7 }}>{F("last_name", t("фамилия","прізвище"), "Литвинчук")}{F("first_name", t("имя","імʼя"), "Антон", true)}</div>
                    <div style={{ display: "flex", gap: 7 }}>{F("middle_name", t("отчество","по батькові"), "Сергійович")}{F("nickname", t("ник / имя из Instagram","нік / імʼя з Instagram"), "Tony")}</div>
                    {F("phone", t("телефон","телефон"), "+380…")}
                    {F("social_link", t("инстаграм / соцсеть (ссылка)","інстаграм / соцмережа (посилання)"), "instagram.com/…")}
                    {F("email", "email", "email@…")}
                    <div><div style={lblS}>{t("заметка (видна команде)","нотатка (видно команді)")}</div><textarea value={cliForm.comment} onChange={(e) => setCliForm({ ...cliForm, comment: e.target.value })} placeholder={t("комментарий о клиенте","коментар про клієнта")} rows={2} style={{ ...fIn, height: "auto", padding: 8 }} /></div>
                  </>);
                })()}
                {cfgCanEdit && <div>
                  <span style={{ fontSize: 11, color: "#64748b", cursor: "pointer" }} onClick={toggleCfg}>⚙ {t("Обязательные поля","Обовʼязкові поля")} {cfgOpen ? "▴" : "▾"}</span>
                  {cfgOpen && <div style={{ background: "#f8fafc", borderRadius: 8, padding: 10, marginTop: 6, fontSize: 12 }}>
                    {([["last_name", t("Фамилия","Прізвище")], ["first_name", t("Имя","Імʼя")], ["middle_name", t("Отчество","По батькові")], ["phone", t("Телефон","Телефон")], ["social_link", "Instagram / соцмережа"], ["email", "Email"], ["nickname", t("Ник","Нік")]] as [string, string][]).map(([fld, lab]) => (
                      <label key={fld} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                        <input type="checkbox" checked={reqFields.includes(fld)} onChange={(e) => { const nx = e.target.checked ? [...reqFields, fld] : reqFields.filter((x) => x !== fld); setReqFields(nx); saveReqCfg(nx); }} /> {lab}
                      </label>
                    ))}
                    {cfgIsAdmin && <div style={{ marginTop: 8, borderTop: "1px solid #e2e8f0", paddingTop: 8 }}>
                      <div style={{ fontWeight: 700, marginBottom: 2 }}>{t("Кто ещё может менять","Хто ще може змінювати")}</div>
                      <div className="muted" style={{ fontSize: 10.5, marginBottom: 5 }}>{t("Админ — всегда. Отметь сотрудников:","Адмін — завжди. Познач співробітників:")}</div>
                      <div style={{ maxHeight: 150, overflowY: "auto" }}>{cfgStaff.map((u) => (
                        <label key={u.id} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                          <input type="checkbox" checked={cfgEditors.includes(u.id)} onChange={(e) => { const nx = e.target.checked ? [...cfgEditors, u.id] : cfgEditors.filter((x) => x !== u.id); setCfgEditors(nx); saveReqCfg(reqFields, nx); }} /> {u.full_name}
                        </label>))}</div>
                    </div>}
                  </div>}
                </div>}
                <div style={{ display: "flex", gap: 7 }}>
                  <button className="btn btn-primary" style={{ flex: 1 }} onClick={saveCliFields}>{t("Сохранить","Зберегти")}</button>
                  <button className="btn" style={{ background: "#f1f5f9" }} onClick={() => setCliFieldsOpen(false)}>{t("Отмена","Скасувати")}</button>
                  <button className="btn" style={{ background: "#f1f5f9" }} title={t("Полная карточка клиента","Повна картка клієнта")} onClick={() => nav(`/clients/${(deal as any).contact_id}`)}>{t("Карточка →","Картка →")}</button>
                </div>
              </div>
            ) : (
              <div style={{ marginTop: 6 }}>
                <input value={cliSearch} autoFocus onChange={(e) => setCliSearch(e.target.value)} placeholder={t("🔍 Телефон или имя клиента…","🔍 Телефон або імʼя клієнта…")} style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px" }} />
                {cliResults.length > 0 && (
                  <div style={{ maxHeight: 200, overflowY: "auto", marginTop: 6, border: "1px solid #e2e8f0", borderRadius: 8 }}>
                    {cliResults.map((c) => (
                      <div key={c.id} onClick={() => setContact(c.id)} style={{ padding: "7px 9px", borderBottom: "1px solid #f1f5f9", cursor: "pointer", fontSize: 13 }}>
                        <Icon n="👤" size={14} /> <b>{c.display_name || `${c.first_name || ""} ${c.last_name || ""}`.trim() || "—"}</b> {c.phone ? <span className="muted">· {c.phone}</span> : null}
                      </div>
                    ))}
                  </div>
                )}
                {cliSearch.trim() && cliResults.length === 0 && <div className="muted" style={{ fontSize: 12, padding: "6px 0" }}>{t("Не найдено — создай нового ниже.","Не знайдено — створи нового нижче.")}</div>}
                {!cliNew ? (
                  <div style={{ display: "flex", gap: 10, marginTop: 8, fontSize: 12 }}>
                    <span style={{ color: "#16a34a", cursor: "pointer" }} onClick={() => setCliNew(true)}><Icon n="➕" size={12} /> {t("Создать нового","Створити нового")}</span>
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
            <div className="label">{t("Сумма сделки","Сума угоди")}</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              <Inline value={Number(deal.amount)} fmt={(v) => fmt(v) + t(" грн."," грн.")} onSave={(v) => patch({ amount: v })} />
            </div>
            <div className="row" style={{ marginTop: 8 }}><span className="muted">{t("Оплачено (за сделку)","Оплачено (за угоду)")}</span><b style={{ color: "#16a34a" }}>{fmt(Math.min(deal.paid, Number(deal.amount)))} ₴</b></div>
            <div className="row"><span className="muted">{t("Осталось","Залишилось")}</span><b style={{ color: remaining > 0 ? "#d97706" : "#16a34a" }}>{fmt(Math.max(0, remaining))} ₴</b></div>
            {deal.paid > Number(deal.amount) && <div className="row"><span className="muted" style={{ fontSize: 11 }} title={t("Клиент заплатил больше суммы сделки — излишек это его аванс (свободные деньги), виден в карточке клиента","Клієнт заплатив більше суми угоди — надлишок це його аванс (вільні гроші), видно в картці клієнта")}>{t("Переплата → аванс клиента","Переплата → аванс клієнта")}</span><b style={{ color: "#2563eb", fontSize: 12.5 }}>+{fmt(deal.paid - Number(deal.amount))} ₴</b></div>}
            <div style={{ marginTop: 10 }}>
              <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{t("Тип оплаты","Тип оплати")}</div>
              <select value={deal.pay_type || "full"} onChange={(e) => patch({ pay_type: e.target.value })} style={{ width: "100%", height: 32, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 12.5, padding: "0 8px" }}>
                <option value="full">{t("💯 Полная оплата","💯 Повна оплата")}</option>
                <option value="prepay_np">{t("🚚 Предоплата + послеоплата НП","🚚 Передоплата + післяплата НП")}</option>
                <option value="reserve">{t("🔒 Бронь","🔒 Бронь")}</option>
              </select>
              <div className="muted" style={{ fontSize: 10.5, marginTop: 3 }}>{deal.pay_type === "prepay_np" ? t("Аванс → Оплату отримано + чек, остаток собирает НП","Аванс → Оплату отримано + чек, решту збере НП") : t("Полная сумма → Оплату отримано; частично → остаётся Домовились","Повна сума → Оплату отримано; частково → лишається Домовились")}</div>
            </div>
            <div style={{ marginTop: 8 }}>
              <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{t("Способ оплаты","Спосіб оплати")}</div>
              {((deal.payments || []).length > 0)
                ? <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                    {(deal.payments || []).slice().sort((a: any, b: any) => a.id - b.id).map((p: any) => {
                      const ok = !!p.is_paid;
                      const isCod = p.provider === "np_cod" || p.provider === "np";
                      return (
                        <span key={p.id}
                          title={ok ? t("Деньги получены","Гроші отримано") : (isCod ? t("Клиент получил посылку — ждём выплату НоваПей на счёт","Клієнт отримав посилку — чекаємо виплату НоваПей на рахунок") : t("Ожидаем оплату","Очікуємо оплату"))}
                          style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, fontWeight: 700, background: ok ? "#dcfce7" : "#fef3c7", color: ok ? "#166534" : "#92400e", borderRadius: 8, padding: "4px 9px" }}>
                          {methodIcon(p.provider)} {t(...methodPair(p.provider))} · {fmt(Number(p.amount))} ₴ {ok ? "✓" : (isCod ? t("· ⏳ ждём выплату НП","· ⏳ чекаємо виплату НП") : t("· ⏳ ждём","· ⏳ чекаємо"))}
                        </span>
                      );
                    })}
                  </div>
                : ((deal as any).pay_method
                  ? <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, fontWeight: 600, background: "#eff6ff", color: "#1d4ed8", borderRadius: 8, padding: "5px 11px" }}>💳 {t(...methodPair((deal as any).pay_method))}</span>
                  : <span className="muted" style={{ fontSize: 12 }}>{t("выберется при «Принять оплату»","обереться при «Прийняти оплату»")}</span>)}
            </div>
            <div style={{ height: 8, background: "#e2e8f0", borderRadius: 6, overflow: "hidden", margin: "10px 0 6px" }} title={t("Прогресс оплаты","Прогрес оплати")}>
              <div style={{ height: "100%", width: (Number(deal.amount) > 0 ? Math.min(100, Math.round((deal.paid / Number(deal.amount)) * 100)) : 0) + "%", background: (deal.paid >= Number(deal.amount) && deal.paid > 0) ? "#16a34a" : "#f59e0b", transition: "width .3s" }} />
            </div>
            {(() => {
              const st = deal.paid <= 0 ? { txt: t("⏳ Ожидаем оплату","⏳ Очікуємо оплату"), bg: "#eff6ff", c: "#1d4ed8" } : (deal.paid < Number(deal.amount) ? { txt: t("🟡 Оплачено частично (аванс)","🟡 Оплачено частково (аванс)"), bg: "#fef3c7", c: "#92400e" } : { txt: t("✅ Оплачено полностью","✅ Оплачено повністю"), bg: "#dcfce7", c: "#166534" });
              return <div style={{ textAlign: "center", fontSize: 12.5, fontWeight: 600, padding: "6px", borderRadius: 8, background: st.bg, color: st.c, marginBottom: 8 }}>{st.txt}</div>;
            })()}
            <button className="btn btn-primary" style={{ width: "100%", height: 36 }} onClick={() => { setPayAmount(String(remaining > 0 ? remaining : deal.amount)); setPayOpen(true); }}>{t("💳 Принять оплату","💳 Прийняти оплату")}</button>
            {(deal.payments || []).length > 0 && (
              <div style={{ marginTop: 10, borderTop: "1px solid #f1f5f9", paddingTop: 8 }}>
                <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{t("История платежей","Історія платежів")}</div>
                {(deal.payments || []).map((p: any) => (
                  <div key={p.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, padding: "3px 0" }}>
                    <span className="muted">{t(...methodPair(p.provider))} · {p.created_at ? new Date(p.created_at).toLocaleDateString("uk", { day: "2-digit", month: "2-digit" }) : ""}</span>
                    <b style={{ color: "#16a34a" }}>{fmt(Number(p.amount))} ₴</b>
                  </div>
                ))}
              </div>
            )}
          </div>
          <SalesAnalystPanel kind="deals" id={id!} onInsert={(txt) => setDraft(txt)} />
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
            <div className="row"><span className="muted">{t("Накладная Нова Пошта (ТТН)","Накладна Нова Пошта (ТТН)")}</span><b>{deal.ttn || t("ще не створено","ще не створено")}</b></div>
            <div className="row"><span className="muted">{t("Фискальный чек","Фіскальний чек")}</span>{(deal as any).checkbox_url ? <a href={(deal as any).checkbox_url} target="_blank" rel="noreferrer" style={{ fontWeight: 700, color: "#16a34a" }}><Icon n="🧾" size={14} /> {t("відкрити чек","відкрити чек")}</a> : <b>{hasCheck ? deal.checkbox_status : t("ще не створено","ще не створено")}</b>}</div>
            {(deal as any).checkbox_relation_id && <div className="row"><span className="muted">{t("№ заказа Checkbox","№ замовлення Checkbox")}</span><b style={{ userSelect: "all", fontSize: 13 }} title={t("По этому номеру можно найти сделку в поиске","За цим номером можна знайти угоду в пошуку")}>{(deal as any).checkbox_relation_id}</b></div>}
            <div style={{ marginTop: 6, display: "flex", gap: 6 }}>
              <span style={chip(hasCheck)}>{t("Фискальный чек","Фіскальний чек")} {hasCheck ? "✓" : t("ще нема","ще нема")}</span>
              <span style={chip(!!deal.ttn)}>{t("Накладна НП","Накладна НП")} {deal.ttn ? "✓" : t("ще нема","ще нема")}</span>
            </div>
          </div>

          {/* 10.5 Маржа + бонус менеджера (для руководителя) */}
          <div className="panel">
            <div className="label">{t("Маржа (видит РОП / руководитель)","Маржа (бачить РОП / керівник)")}</div>
            <div className="row"><span className="muted">{t("Маржа","Маржа")}</span><b>{fmt(deal.margin || 0)} ₴{deal.margin && Number(deal.amount) ? ` · ${Math.round((deal.margin / Number(deal.amount)) * 100)}%` : ""}</b></div>
            <div className="row" title={deal.bonus ? t(`${deal.bonus.revenue_pct}% с оборота + ${deal.bonus.margin_pct}% с маржи. Ставки меняются в Финмодели → ЗП.`, `${deal.bonus.revenue_pct}% з обороту + ${deal.bonus.margin_pct}% з маржі. Ставки міняються у Фінмоделі → ЗП.`) : ""}><span className="muted"><Icon n="💰" size={14} /> {t("Бонус менеджера со сделки","Бонус менеджера з угоди")}</span><b style={{ color: "#1d4ed8" }}>{fmt(deal.bonus?.total || 0)} ₴</b></div>
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
              <RefPhotos dealId={deal.id} initial={(deal as any).ref_photos} />
              <KpHistory history={(deal as any).kp_history} deal={deal} />
              <CardFields leadId={deal.id} initial={deal.card_fields} endpoint="/api/deals/" />

            </>
          ) : (
            /* 11.2 Товары в сделке (добавить/удалить → пересчёт суммы на бэке) */
            <div className="panel">
              <div className="label" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span>{t("Товары в сделке","Товари в угоді")}</span>
                <button className="btn" onClick={() => setDocOpen(true)} title={t("Сформировать документ КП","Сформувати документ КП")}><Icon n="📄" size={14} /> {t("Документ","Документ")}</button>
              </div>
              <div className="prod-search" style={{ position: "relative", margin: "8px 0 12px" }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input value={psearch} onChange={(e) => { setPsearch(e.target.value); setPsel(null); }} placeholder={t("🔍 Поиск товара из номенклатуры по названию…","🔍 Пошук товару з номенклатури за назвою…")} style={{ flex: 1, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 10px" }} />
                  <input type="number" value={addQty} min={1} onChange={(e) => setAddQty(Number(e.target.value))} title={t("Количество","Кількість")} style={{ width: 56, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px" }} />
                  <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, whiteSpace: "nowrap" }} title={t("Зарезервировать товар под сделку","Зарезервувати товар під угоду")}><input type="checkbox" checked={addReserve} onChange={(e) => setAddReserve(e.target.checked)} />{t("Резерв","Резерв")}</label>
                  <button className="btn btn-primary" onClick={() => addItem()} disabled={!psel}>{t("Добавить","Додати")}</button>
                  <button className="btn" onClick={() => setShowList((s) => !s)} title={t("Показать весь список товаров (двойной клик — добавить)","Показати весь список товарів (подвійний клік — додати)")}>{showList ? <>{t("✕ Список","✕ Список")}</> : <><Icon n="📋" size={14} /> {t("Список","Список")}</>}</button>
                  {can("deal.items.custom") || can("roles.manage") ? <button className="btn" onClick={() => setCiOpen((v) => !v)} title={t("Добавить позицию НЕ из номенклатуры — без складского учёта и списания","Додати позицію НЕ з номенклатури — без складського обліку і списання")} style={{ whiteSpace: "nowrap" }}>{ciOpen ? "✕" : "➕"} {t("Своя","Своя")}</button> : null}
                  {can("warehouse.tab.receipts") && <button className="btn" onClick={() => setShowReceipt(true)} title={t("Оприходовать товар (дроп/закупка у поставщика) — приход на склад с выбором поставщика","Оприбуткувати товар (дроп/закупка у постачальника) — прихід на склад з вибором постачальника")} style={{ whiteSpace: "nowrap" }}><Icon n="📥" size={14} /> {t("Приход","Прихід")}</button>}
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
                {ciOpen && (
                  <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 8, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "8px 10px" }}>
                    <input value={ci.name} onChange={(e) => setCi({ ...ci, name: e.target.value })} placeholder={t("Название своей позиции (не со склада)","Назва своєї позиції (не зі складу)")} style={{ flex: 1, height: 32, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13 }} />
                    <input type="number" value={ci.qty} min={1} onChange={(e) => setCi({ ...ci, qty: Number(e.target.value) })} title={t("Количество","Кількість")} style={{ width: 56, height: 32, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 13 }} />
                    <input type="number" value={ci.price} onChange={(e) => setCi({ ...ci, price: e.target.value })} placeholder={t("Цена","Ціна")} style={{ width: 90, height: 32, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 13 }} />
                    <button className="btn btn-primary" style={{ height: 32 }} onClick={addCustomItem}>{t("Добавить","Додати")}</button>
                  </div>
                )}
              </div>
              {showList && (
                <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, maxHeight: 300, overflowY: "auto", marginBottom: 12 }}>
                  <div style={{ padding: "6px 10px", fontSize: 11, color: "#64748b", borderBottom: "1px solid #f1f5f9", position: "sticky", top: 0, background: "#f8fafc" }}>{t("Двойной клик по товару — добавить в сделку. Поиск сверху фильтрует список.","Подвійний клік по товару — додати в угоду. Пошук зверху фільтрує список.")}</div>
                  {products.filter((p) => !psearch.trim() || p.name.toLowerCase().includes(psearch.toLowerCase())).map((p) => {
                    const added = deal.items.some((it: any) => it.product === p.id);
                    return (
                      <div key={p.id} onDoubleClick={() => addItem(p)} title={t("Двойной клик — добавить","Подвійний клік — додати")} style={{ padding: "7px 10px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13, display: "flex", justifyContent: "space-between", gap: 8 }}>
                        <span><b>{p.name}</b> <span className="muted">· {fmt(Number(p.price))} ₴ · {t("ост.","зал.")} {(p as any).stock}</span></span>
                        {added && <span style={{ color: "#16a34a", whiteSpace: "nowrap" }}>✓ {t("в сделке","в угоді")}</span>}
                      </div>
                    );
                  })}
                  {products.filter((p) => !psearch.trim() || p.name.toLowerCase().includes(psearch.toLowerCase())).length === 0 && <div style={{ padding: 12, fontSize: 13, color: "#94a3b8" }}>{t("Ничего не найдено","Нічого не знайдено")}</div>}
                </div>
              )}
              {deal.items.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>{t("Товаров пока нет.","Товарів поки немає.")}</div> : (
                <>
                <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", minWidth: 730, fontSize: 13, tableLayout: "fixed" as const }}>
                <colgroup><col style={{ width: 22 }} /><col /><col style={{ width: 74 }} />{can("product.cost.view") && <><col style={{ width: 58 }} /><col style={{ width: 68 }} /></>}<col style={{ width: 44 }} /><col style={{ width: 40 }} /><col style={{ width: 44 }} /><col style={{ width: 98 }} /><col style={{ width: 62 }} /><col style={{ width: 22 }} /></colgroup>
                <thead><tr style={{ color: "#64748b", fontSize: 9.5, lineHeight: 1.1, textAlign: "left", verticalAlign: "bottom" }}>
                  <th style={{ padding: "6px 4px" }}>№</th><th style={{ padding: "6px 4px" }}>{t("Товар","Товар")}</th>
                  <th style={{ padding: "6px 4px" }}>{t("Цена","Ціна")}</th>{can("product.cost.view") && <><th style={{ padding: "4px 3px" }}>{t("Закуп/ед","Закуп/од")}</th><th style={{ padding: "4px 3px" }}>{t("Сумма закуп","Сума закуп")}</th></>}<th style={{ padding: "6px 4px" }}>{t("Кол-во","К-сть")}</th>
                  <th style={{ padding: "4px 3px", textAlign: "center" }}>{t("Рез.","Рез.")}</th><th style={{ padding: "4px 3px" }}>{t("Ост.","Зал.")}</th>
                  <th style={{ padding: "4px 3px" }}>{t("Скидка","Знижка")}</th>
                  <th style={{ padding: "6px 4px" }}>{t("Сумма","Сума")}</th><th></th></tr></thead>
                  <tbody>{deal.items.map((it: any, idx: number) => {
                    const low = it.product_stock != null && Number(it.quantity) > Number(it.product_stock);
                    return (
                    <tr key={it.id} style={{ borderTop: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "6px 4px", color: "#94a3b8" }}>{idx + 1}</td>
                      <td style={{ padding: "6px 4px", position: "relative" }}>
                        {editProdItem === it.id ? (
                          <>
                            <div ref={epBoxRef} style={{ display: "flex", alignItems: "center", gap: 4, border: "1px solid #2563eb", borderRadius: 6, padding: "0 6px", height: 30, background: "#fff", boxSizing: "border-box" }}>
                              <input autoFocus value={epq} onFocus={(e) => e.target.select()} onChange={(e) => setEpq(e.target.value)} onBlur={() => setTimeout(() => setEditProdItem(0), 200)} placeholder={t("товар по названию/артикулу…", "товар за назвою/артикулом…")} style={{ flex: 1, minWidth: 0, height: 26, border: "none", outline: "none", fontSize: 12.5, background: "transparent" }} />
                              {it.product ? <a onMouseDown={(e) => e.preventDefault()} onClick={(e) => e.stopPropagation()} href={"/warehouse?product=" + it.product} target="_blank" rel="noreferrer" title={t("Открыть карточку товара", "Відкрити картку товару")} style={{ color: "#1d4ed8", textDecoration: "none", fontSize: 14, flexShrink: 0, lineHeight: 1 }}>↗</a> : null}
                              <span onMouseDown={(e) => { e.preventDefault(); setEpq(""); setEpr([]); }} title={t("Очистить", "Очистити")} style={{ color: "#94a3b8", cursor: "pointer", fontSize: 13, flexShrink: 0, fontWeight: 700, lineHeight: 1 }}>✕</span>
                            </div>
                            {epr.length > 0 && epBoxRef.current && createPortal((() => {
                              const r = epBoxRef.current!.getBoundingClientRect();
                              return (
                                <div style={{ position: "fixed", top: r.bottom + 2, left: r.left, width: Math.max(r.width, 240), background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 12px 32px rgba(15,23,42,.25)", zIndex: 2147483000, maxHeight: 300, overflowY: "auto" }}>
                                  {epr.map((p: any) => <div key={p.id} onMouseDown={() => reselectItemProduct(it.id, p.id)} style={{ padding: "8px 11px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 12.5 }}>{p.name}{p.sku ? <span className="muted"> · {p.sku}</span> : null}</div>)}
                                </div>
                              );
                            })(), document.body)}
                          </>
                        ) : (
                          <div onClick={() => { setEditProdItem(it.id); setEpq(it.product_name || ""); setEpr([]); }} title={t("Нажми, чтобы набрать и выбрать другой товар", "Натисни, щоб набрати й обрати інший товар")} style={{ display: "flex", alignItems: "flex-start", gap: 4, minWidth: 0, border: "1px solid #e2e8f0", borderRadius: 6, padding: "5px 6px", minHeight: 30, background: "#fff", boxSizing: "border-box", cursor: "text" }}>
                            <span style={{ fontWeight: 500, flex: 1, minWidth: 0, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as any, overflow: "hidden", wordBreak: "break-word", lineHeight: 1.25 }} title={it.product_name}>{it.product_name || <span className="muted">{t("— выбрать товар —", "— обрати товар —")}</span>}</span>
                            {it.product ? <a onClick={(e) => e.stopPropagation()} href={"/warehouse?product=" + it.product} target="_blank" rel="noreferrer" title={t("Открыть карточку товара", "Відкрити картку товару")} style={{ color: "#1d4ed8", textDecoration: "none", fontSize: 14, flexShrink: 0, lineHeight: 1 }}>↗</a> : null}
                            <span onClick={(e) => { e.stopPropagation(); setEditProdItem(it.id); setEpq(""); setEpr([]); }} title={t("Удалить и выбрать другой", "Видалити й обрати інший")} style={{ color: "#94a3b8", cursor: "pointer", fontSize: 13, flexShrink: 0, fontWeight: 700, lineHeight: 1 }}>✕</span>
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "6px 4px", whiteSpace: "nowrap" }}><input key={"pr-" + it.id + "-" + it.price} defaultValue={Number(it.price)} type="number" min={0} onBlur={(e) => Number(e.target.value) !== Number(it.price) && updateItem(it.id, { price: e.target.value })} style={editInp} /> ₴</td>
                      {can("product.cost.view") && <><td style={{ padding: "6px 4px", color: "#9a3412", whiteSpace: "nowrap" }} title={t("Закупка за единицу (себестоимость товара)","Закупка за одиницю (собівартість товару)")}>{Number(it.cost || 0) > 0 ? fmt(Number(it.cost)) + " ₴" : "—"}</td><td style={{ padding: "6px 4px", color: "#9a3412", whiteSpace: "nowrap", fontWeight: 600 }} title={t("Сумма закупки по строке (себестоимость × кол-во)","Сума закупки по рядку (собівартість × кількість)")}>{Number(it.cost || 0) > 0 ? fmt(Number(it.cost) * Number(it.quantity)) + " ₴" : "—"}</td></>}
                      <td style={{ padding: "6px 4px" }}><input defaultValue={Number(it.quantity)} type="number" min={0} onBlur={(e) => Number(e.target.value) !== Number(it.quantity) && updateItem(it.id, { quantity: e.target.value })} style={{ ...editInp, width: 50 }} /></td>
                      <td style={{ padding: "6px 4px", textAlign: "center" }}><input type="checkbox" checked={!!it.reserved} onChange={() => toggleReserve(it)} title={t("Зарезервировать под сделку","Зарезервувати під угоду")} /></td>
                      <td style={{ padding: "6px 4px", color: low ? "#dc2626" : "#64748b" }} title={low ? t("Не хватает на складе","Не вистачає на складі") : ""}>{it.product_stock != null ? Number(it.product_stock) : "—"}{low ? " ⚠" : ""}</td>
                      <td style={{ padding: "6px 4px", whiteSpace: "nowrap" }}>{(() => {
                        const mode = discMode[it.id] || (Number(it.discount_amount || 0) > 0 ? "amt" : "pct");
                        return (
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                            <input key={it.id + "-" + mode} defaultValue={mode === "amt" ? Number(it.discount_amount || 0) : Number(it.discount_pct || 0)} type="number" min={0} max={mode === "pct" ? 100 : undefined}
                              onBlur={(e) => { const v = e.target.value; if (mode === "amt") updateItem(it.id, { discount_amount: v, discount_pct: 0 }); else updateItem(it.id, { discount_pct: v, discount_amount: 0 }); }}
                              style={{ ...editInp, width: 46 }} />
                            <select value={mode} onChange={(e) => setDiscMode((m) => ({ ...m, [it.id]: e.target.value as "pct" | "amt" }))} title={t("Скидка в % или в гривнах","Знижка у % або в гривнях")} style={{ height: 28, border: "1px solid #cbd5e1", borderRadius: 6, fontSize: 12, color: "#2563eb", fontWeight: 700, padding: "0 1px", background: "#fff" }}><option value="pct">%</option><option value="amt">₴</option></select>
                          </span>
                        );
                      })()}</td>
                      
                      <td style={{ padding: "6px 4px" }}><b>{fmt(Number(it.total))} ₴</b></td>
                      <td style={{ padding: "6px 4px" }}><span style={{ color: "#ef4444", cursor: "pointer" }} onClick={() => removeItem(it.id)}>✕</span></td></tr>
                  ); })}</tbody>
                </table>
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                  <div style={{ minWidth: 290 }}>
                    <div style={rowTot}><span className="muted">{t("Сумма без скидки","Сума без знижки")}</span><b>{fmt(deal.items.reduce((s: number, i: any) => s + Number(i.total) + Number(i.discount_sum || 0), 0))} ₴</b></div>
                    <div style={rowTot}><span className="muted">{t("Сумма скидки","Сума знижки")}</span><b style={{ color: "#16a34a" }}>−{fmt(deal.items.reduce((s: number, i: any) => s + Number(i.discount_sum || 0), 0))} ₴</b></div>
                    <div style={{ ...rowTot, fontSize: 16, borderTop: "2px solid #e2e8f0", paddingTop: 8, marginTop: 4 }}><span>{t("Итого","Загальна сума")}</span><b>{fmt(deal.items.reduce((s: number, i: any) => s + Number(i.total), 0))} ₴</b></div>
                    {can("product.cost.view") && (() => { const cogs = deal.items.reduce((s: number, i: any) => s + Number(i.quantity) * Number(i.cost || 0), 0); const rev = deal.items.reduce((s: number, i: any) => s + Number(i.total), 0); return (
                      <>
                        <div style={{ ...rowTot, fontSize: 12.5 }}><span className="muted">{t("Сумма по закупке","Сума по закупці")}</span><b style={{ color: "#9a3412" }}>{fmt(cogs)} ₴</b></div>
                        <div style={{ ...rowTot, fontSize: 12.5 }}><span className="muted">{t("Маржа угоди","Маржа угоди")}</span><b style={{ color: rev - cogs > 0 ? "#166534" : "#dc2626" }}>{fmt(rev - cogs)} ₴{rev > 0 ? " · " + Math.round(((rev - cogs) / rev) * 100) + "%" : ""}</b></div>
                      </>
                    ); })()}
                    {(deal as any).realization && (
                      <div style={{ ...rowTot, fontSize: 12.5, marginTop: 6, color: (deal as any).realization.posted ? "#166534" : "#92400e" }}>
                        <span className="muted">{t("Реализация","Реалізація")} 📤</span>
                        <b>{(deal as any).realization.number} · {((deal as any).realization.created_at || "").slice(0, 10)} · {(deal as any).realization.posted ? t("проведён","проведено") : t("черновик","чернетка")}</b>
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 12, marginTop: 14 }}>
                  <span className="muted" style={{ fontSize: 12 }}>{t("Зафиксируй список — сделка перейдёт на расчёт","Зафіксуй список — угода перейде на розрахунок")}</span>
                  <button className="btn btn-primary" onClick={confirmItems} title={t("Сохранить список товаров и перейти к расчёту","Зберегти список товарів і перейти до розрахунку")}><Icon n="💾" size={14} /> {t("Сохранить список → Розрахунок","Зберегти список → Розрахунок")}</button>
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
              <div className="label"><Icon n="💬" size={14} /> {t("Чат с клиентом","Чат з клієнтом")}</div>
              <ClientChat contact={deal.contact_id} channelPickerTargetId={`deal-reply-channel-${deal.id}`} />
            </div>
          </div>
        )}
      </div>
      ) : <CashflowTab deal={deal} remaining={remaining} onPay={() => { setPayAmount(String(remaining > 0 ? remaining : deal.amount)); setPayOpen(true); }} createTTN={createTTN} issueCheckbox={issueCheckbox} sendPayLink={sendPayLink} flash={flash} />}

      {docOpen && <KpDoc deal={deal} onClose={() => setDocOpen(false)} />}
      {vkOpen && <VykraskaDoc data={{ number: deal.id, material: ((deal as any).qualification || {}).material, color: ((deal as any).qualification || {}).color, area: ((deal as any).qualification || {}).area, underlay: ((deal as any).qualification || {}).underlay, kits: ((deal as any).qualification || {}).kits, client: (deal as any).contact_name, phone: (deal as any).contact_phone }} onClose={() => setVkOpen(false)} />}
      {/* модалка створення клієнта зі сделки */}
      {ncOpen && (
        <div onClick={() => setNcOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>{t("Клиент сделки","Клієнт угоди")}</h3>
            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              <button className={"btn" + (ncMode === "pick" ? " btn-primary" : " btn-light")} style={{ flex: 1 }} onClick={() => setNcMode("pick")}><Icon n="🔍" size={14} /> {t("Выбрать существующего","Обрати існуючого")}</button>
              <button className={"btn" + (ncMode === "new" ? " btn-primary" : " btn-light")} style={{ flex: 1 }} onClick={() => setNcMode("new")}><Icon n="➕" size={14} /> {t("Создать нового","Створити нового")}</button>
            </div>
            {ncMode === "pick" ? (
              <>
                <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("Найди клиента среди существующих (37 тыс.) и привяжи к сделке.","Знайди клієнта серед існуючих (37 тис.) і привʼяжи до угоди.")}</div>
                <input value={ncSearch} autoFocus onChange={(e) => setNcSearch(e.target.value)} placeholder={t("Имя, фамилия, телефон…","Імʼя, прізвище, телефон…")} style={{ width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 8 }} />
                <div style={{ maxHeight: 240, overflowY: "auto", marginBottom: 12 }}>
                  {ncResults.map((c) => (
                    <div key={c.id} onClick={() => linkExisting(c.id)} style={{ padding: "8px 10px", borderRadius: 8, cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13 }}>
                      <Icon n="👤" size={14} /> <b>{c.display_name || `${c.first_name || ""} ${c.last_name || ""}`.trim() || "—"}</b> {c.phone ? <span className="muted">· {c.phone}</span> : null}
                    </div>
                  ))}
                  {ncSearch.trim() && ncResults.length === 0 && <div className="muted" style={{ fontSize: 13, padding: 8 }}>{t("Ничего не найдено. Создай нового на соседней вкладке.","Нічого не знайдено. Створи нового на сусідній вкладці.")}</div>}
                </div>
                <button className="btn btn-light" style={{ width: "100%" }} onClick={() => setNcOpen(false)}>{t("Закрыть","Закрити")}</button>
              </>
            ) : (
              <>
                <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Создастся карточка клиента и привяжется к этой сделке.","Створиться картка клієнта і привʼяжеться до цієї угоди.")}</div>
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
      {showReceipt && <ReceiptModal dealId={deal.id} onClose={() => setShowReceipt(false)} onSaved={() => { setShowReceipt(false); flash(t("Приход проведён ✓","Прихід проведено ✓")); }} />}
      {ttnOpen && (
        <div onClick={() => setTtnOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 420, maxHeight: "88vh", overflowY: "auto" }}>
            <h3 style={{ marginTop: 0 }}><Icon n="🚚" size={18} /> {t("Создать ТТН Нова Пошта", "Створити ТТН Нова Пошта")}</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div><label className="label">{t("Получатель", "Отримувач")}</label><input value={ttnName} onChange={(e) => setTtnName(e.target.value)} style={inp} /></div>
              <div><label className="label">{t("Телефон", "Телефон")}</label><input value={ttnPhone} onChange={(e) => setTtnPhone(e.target.value)} placeholder="0XX..." style={inp} /></div>
            </div>
            <label className="label" style={{ marginTop: 8 }}>{t("Город", "Місто")}</label>
            <input value={ttnCityQ} onChange={(e) => { setTtnCityQ(e.target.value); setTtnCity(null); }} placeholder={t("Начните вводить…", "Почніть вводити…")} style={inp} />
            {!ttnCity && ttnCities.length > 0 && <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, maxHeight: 160, overflowY: "auto", marginTop: 2 }}>{ttnCities.map((c, i) => (<div key={i} onClick={() => pickCity(c)} style={{ padding: "7px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f1f5f9" }}>{c.present || c.name}</div>))}</div>}
            {ttnCity && (<>
              <label className="label" style={{ marginTop: 8 }}>{t("Отделение", "Відділення")} ({ttnWhs.length})</label>
              <select value={ttnWh?.ref || ""} onChange={(e) => setTtnWh(ttnWhs.find((w) => w.ref === e.target.value) || null)} style={inp}>
                <option value="">{t("— выберите —", "— виберіть —")}</option>
                {ttnWhs.map((w) => (<option key={w.ref} value={w.ref}>{w.desc}</option>))}
              </select>
            </>)}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 8 }}>
              <div><label className="label">{t("Вес, кг", "Вага, кг")}</label><input type="number" value={ttnWeight} onChange={(e) => setTtnWeight(e.target.value)} style={inp} /></div>
              <div><label className="label">{t("Мест", "Місць")}</label><input type="number" value={ttnSeats} onChange={(e) => setTtnSeats(e.target.value)} style={inp} /></div>
              <div><label className="label">{t("Оценка, ₴", "Оцінка, ₴")}</label><input type="number" value={ttnCost} onChange={(e) => setTtnCost(e.target.value)} style={inp} /></div>
            </div>
            <label className="label" style={{ marginTop: 8 }}>{t("Наложенный платёж (послеоплата), ₴", "Накладений платіж (післяплата), ₴")}</label>
            <input type="number" value={ttnCod} onChange={(e) => setTtnCod(e.target.value)} placeholder={t("0 — без наложки", "0 — без наложки")} style={inp} />
            <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>{t("Сумма, которую клиент платит при получении (НП-послеоплата). После прихода денег создастся финальный чек.", "Сума, яку клієнт платить при отриманні (НП-післяплата). Після приходу грошей створиться фінальний чек.")}</div>
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setTtnOpen(false)}>{t("Отмена", "Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 2 }} onClick={submitTTN} disabled={ttnSending}>{ttnSending ? "…" : t("Создать ТТН", "Створити ТТН")}</button>
            </div>
          </div>
        </div>
      )}
      {payOpen && (
        <div onClick={() => setPayOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 24, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>{t("Принять оплату","Прийняти оплату")}</h3>
            <label className="label" style={{ marginBottom: 6 }}>{t("Способ оплаты","Спосіб оплати")}</label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 14 }}>
              {([["cash", t("💵 Наличные","💵 Готівка")], ["liqpay", t("💳 LiqPay (оплата картой онлайн)","💳 LiqPay (оплата картою онлайн)")], ["terminal", t("💳 Терминал · карта/телефон NFC","💳 Термінал · картка/телефон NFC")], ["requisites", t("🏦 Реквизиты IBAN","🏦 Реквізити IBAN")], ["np", t("📦 Наложенный платёж","📦 Накладений платіж")], ["installment", t("📅 Рассрочка Приват","📅 Розстрочка Приват")]].concat(salonFunnel ? [["credit", t("🤝 Товарный кредит (отгрузка в долг)","🤝 Товарний кредит (відвантаження в борг)")]] : []).concat(deal.contact_id ? [["advance", t("🏦 Из аванса клиента","🏦 З авансу клієнта")]] : []) as [string,string][]).map(([k, label]) => (
                <button key={k} onClick={() => setPayType(k)} style={{ fontSize: 12, padding: "8px 8px", borderRadius: 8, cursor: "pointer", textAlign: "left", border: "1px solid " + (payType === k ? "var(--brand,#2563eb)" : "#e2e8f0"), background: payType === k ? "#eff6ff" : "#fff", color: payType === k ? "#1d4ed8" : "#475569", fontWeight: payType === k ? 600 : 400 }}>{label}</button>
              ))}
            </div>
            {payType === "cash" && (
              <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
                <span onClick={() => setCashReceipt(false)} style={{ flex: 1, textAlign: "center", padding: "7px 8px", borderRadius: 999, fontSize: 12.5, fontWeight: 700, cursor: "pointer", background: !cashReceipt ? "#475569" : "#fff", color: !cashReceipt ? "#fff" : "#64748b", border: "1.5px solid " + (!cashReceipt ? "#475569" : "#e2e8f0") }}>{t("Без чека","Без чека")}</span>
                <span onClick={() => setCashReceipt(true)} style={{ flex: 1, textAlign: "center", padding: "7px 8px", borderRadius: 999, fontSize: 12.5, fontWeight: 700, cursor: "pointer", background: cashReceipt ? "#16a34a" : "#fff", color: cashReceipt ? "#fff" : "#64748b", border: "1.5px solid " + (cashReceipt ? "#16a34a" : "#e2e8f0") }}>🧾 {t("С фискальным чеком","З фіскальним чеком")}</span>
              </div>
            )}
            {payType === "advance" && (
              <div className="muted" style={{ fontSize: 11.5, marginBottom: 12, background: "#eff6ff", padding: "8px 10px", borderRadius: 8, color: "#1d4ed8" }}>
                {t("Списываем из уже полученных денег клиента (аванса) — новый доход и чек НЕ создаются.","Списуємо з уже отриманих грошей клієнта (авансу) — новий дохід і чек НЕ створюються.")}
                {advAvail !== null && <div style={{ marginTop: 4, fontWeight: 700 }}>{t("Доступный аванс:","Доступний аванс:")} {Math.round(advAvail).toLocaleString("ru")} ₴</div>}
                {advAvail !== null && advAvail <= 0 && (
                  <div style={{ marginTop: 6, padding: "6px 8px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, color: "#b91c1c", fontWeight: 700 }}>
                    {t("У клиента нет свободного аванса — все его деньги уже разнесены по сделкам. Выбери реальный способ оплаты (наличные/карта/LiqPay).","У клієнта немає вільного авансу — усі його гроші вже рознесені по сделках. Обери реальний спосіб оплати (готівка/картка/LiqPay).")}
                  </div>
                )}
                {advAvail !== null && advAvail > 0 && advAvail + 0.01 < remaining && (
                  <div style={{ marginTop: 6, padding: "6px 8px", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 6, color: "#92400e", fontWeight: 700 }}>
                    {t(`Аванс покрывает только ${Math.round(advAvail).toLocaleString("ru")} ₴ из ${Math.round(remaining).toLocaleString("ru")} ₴. Остаток ${Math.round(remaining - advAvail).toLocaleString("ru")} ₴ проведи отдельно другим способом (наличные/карта).`,`Аванс покриває лише ${Math.round(advAvail).toLocaleString("ru")} ₴ з ${Math.round(remaining).toLocaleString("ru")} ₴. Решту ${Math.round(remaining - advAvail).toLocaleString("ru")} ₴ проведи окремо іншим способом (готівка/картка).`)}
                    <button type="button" onClick={() => setPayAmount(String(Math.round(Number(advAvail))))} style={{ marginTop: 6, width: "100%", height: 30, borderRadius: 8, border: "1px solid #2563eb", background: "#fff", color: "#1d4ed8", fontWeight: 700, fontSize: 12, cursor: "pointer" }}>
                      {t(`Списать весь аванс (${Math.round(advAvail).toLocaleString("ru")} ₴)`,`Списати весь аванс (${Math.round(advAvail).toLocaleString("ru")} ₴)`)}
                    </button>
                  </div>
                )}
              </div>
            )}
            <label className="label">{t("Сумма, ₴","Сума, ₴")}</label>
            <input type="number" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} style={{ width: "100%", height: 38, marginBottom: 14, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            {payType === "advance" && advAvail !== null && Number(payAmount || 0) > advAvail + 0.01 && (
              <div style={{ marginTop: -10, marginBottom: 12, color: "#dc2626", fontSize: 11.5, fontWeight: 700 }}>
                {t(`Сумма больше доступного аванса (${Math.round(advAvail).toLocaleString("ru")} ₴) — оплата не пройдёт. Уменьши сумму или проведи остаток другим способом.`,`Сума більша за доступний аванс (${Math.round(advAvail).toLocaleString("ru")} ₴) — оплата не пройде. Зменш суму або проведи решту іншим способом.`)}
              </div>
            )}
            {debtList.length > 0 && (
              <div style={{ marginBottom: 12, background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "8px 10px" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#92400e", marginBottom: 6 }}>💳 {t("Клиент должен (закрыть этой оплатой):","Клієнт винен (закрити цією оплатою):")}</div>
                {debtList.map((d0: any) => (
                  <label key={d0.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, padding: "3px 0", cursor: "pointer" }}>
                    <input type="checkbox" checked={selDebts.includes(d0.id)} onChange={(e) => setSelDebts(e.target.checked ? [...selDebts, d0.id] : selDebts.filter((x) => x !== d0.id))} style={{ accentColor: "#C67D5F" }} />
                    <span style={{ flex: 1 }}>{d0.counterparty || d0.comment || t("материалы","матеріали")} — <b>{Math.round(Number(d0.amount)).toLocaleString("ru")} ₴</b></span>
                  </label>
                ))}
                <div className="muted" style={{ fontSize: 10.5, marginTop: 4 }}>{t("Отмеченное закроется как оплаченное (транзит-материалы). Остаток платежа пойдёт на сделку.","Відмічене закриється як оплачене (транзит-матеріали). Решта платежу піде на сделку.")}</div>
              </div>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setPayOpen(false)}>{t("Отмена","Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 2 }} onClick={acceptPayment} disabled={sending}>{sending ? t("Отправляю…","Надсилаю…") : ((payType === "liqpay" || payType === "requisites" || payType === "installment") ? t("Создать ссылку и отправить","Створити посилання і надіслати") : t("Провести оплату","Провести оплату"))}</button>
            </div>
            {payType === "credit" && <div className="muted" style={{ fontSize: 11.5, marginBottom: 10, background: "#fef9c3", padding: "8px 10px", borderRadius: 8 }}>{t("Товар отдаём СЕЙЧАС, деньги — потом. Создастся долг клиента (дебиторка) + стадия «Выдано в товарный кредит».","Товар віддаємо ЗАРАЗ, гроші — потім. Створиться борг клієнта (дебіторка) + стадія «Выдано в товарный кредит».")}</div>}
            <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>{payType === "terminal"
              ? t("Прими оплату в приложении Checkbox (Tap to Pay) — телефон читает карту/телефон клиента и сразу бьёт чек + печать. Потом «Провести оплату» — CRM проведёт доход и закроет сделку.","Прийми оплату в застосунку Checkbox (Tap to Pay) — телефон читає картку/телефон клієнта і одразу б'є чек + друк. Потім «Провести оплату» — CRM проведе дохід і закриє угоду.")
              : (payType === "liqpay" || payType === "requisites")
              ? t("Создаст ссылку LiqPay и отправит клиенту в чат. Статус сменится только после реальной оплаты.","Створить посилання LiqPay і надішле клієнту в чат. Статус зміниться лише після реальної оплати.")
              : t("Создаст доходную транзакцию в Финансах + двинет стадию.","Створить дохідну транзакцію у Фінансах + рухне стадію.")}</div>
          </div>
        </div>
      )}
      {verify && (
        <div onClick={() => setVerify(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 440, maxHeight: "92vh", overflowY: "auto" }}>
            <h3 style={{ margin: "0 0 4px" }}>{verify.mode === "credit" ? t("Шаг 2 — товарный кредит","Крок 2 — товарний кредит") : t("Шаг 2 — проверь платёж","Крок 2 — перевір платіж")}</h3>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{verify.mode === "credit"
              ? t("Деньги НЕ приходят сейчас: создаётся долг клиента (дебиторка). Когда оплатит — в Финансы → Дт/Кт жми «Оплачено», доход появится в журнале сам.","Гроші НЕ приходять зараз: створюється борг клієнта (дебіторка). Коли оплатить — у Фінанси → Дт/Кт тисни «Оплачено», дохід зʼявиться в журналі сам.")
              : t("Так операция запишется в журнал Финансов. Проверь каждое поле — можно поправить прямо тут.","Так операція запишеться в журнал Фінансів. Перевір кожне поле — можна виправити прямо тут.")}</div>
            <label className="label">{t("Сумма, ₴","Сума, ₴")}</label>
            <input type="number" value={verify.amount} onChange={(e) => setVerify({ ...verify, amount: e.target.value })} style={inpV} />
            {verify.mode === "credit" ? (<>
              <label className="label">{t("Срок долга, дней","Строк боргу, днів")}</label>
              <input type="number" value={verify.days} onChange={(e) => setVerify({ ...verify, days: e.target.value })} style={inpV} />
              <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("Должник (из сделки):","Боржник (з угоди):")} <b>{verify.counterparty || "—"}</b></div>
            </>) : (<>
              <label className="label">{t("Счёт (куда пришли деньги)","Рахунок (куди прийшли гроші)")}</label>
              <select value={verify.account} onChange={(e) => setVerify({ ...verify, account: Number(e.target.value) })} style={inpV}>
                {vRefs.accs.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
              <label className="label">{t("Категория дохода","Категорія доходу")}</label>
              <select value={verify.category} onChange={(e) => { const c = vRefs.cats.find((x: any) => x.id === Number(e.target.value)); setVerify({ ...verify, category: Number(e.target.value), direction: (c?.fin_direction || verify.direction) }); }} style={inpV}>
                {vRefs.cats.map((c: any) => <option key={c.id} value={c.id}>{c.parent ? "└ " : ""}{c.name}</option>)}
              </select>
              <label className="label">{t("Направление","Напрямок")}</label>
              <select value={verify.direction} onChange={(e) => setVerify({ ...verify, direction: Number(e.target.value) })} style={inpV}>
                <option value={0}>—</option>
                {vRefs.dirs.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
              <label className="label">{t("Контрагент (клиент)","Контрагент (клієнт)")}</label>
              <input value={verify.counterparty} onChange={(e) => setVerify({ ...verify, counterparty: e.target.value })} style={inpV} />
              <label className="label">{t("Источник (канал)","Джерело (канал)")}</label>
              <input value={verify.channel} onChange={(e) => setVerify({ ...verify, channel: e.target.value })} style={inpV} />
              <label className="label">{t("Комментарий","Коментар")}</label>
              <input value={verify.comment} onChange={(e) => setVerify({ ...verify, comment: e.target.value })} style={inpV} />
            </>)}
            <div onClick={() => setVerify({ ...verify, ship: !verify.ship })} style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 12px", borderRadius: 10, cursor: "pointer", border: "1.5px solid " + (verify.ship ? "#16a34a" : "#e2e8f0"), background: verify.ship ? "#f0fdf4" : "#fff", margin: "6px 0 12px" }}>
              <span style={{ fontSize: 18 }}>{verify.ship ? "📦" : "🚫"}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{verify.ship ? t("Отгрузка со склада: ДА","Відвантаження зі складу: ТАК") : t("Отгрузка со склада: НЕТ","Відвантаження зі складу: НІ")}</div>
                <div className="muted" style={{ fontSize: 11 }}>{verify.ship
                  ? t("Создастся задача складу в общем списке, статусы дальше двигаются сами. Кликни, если отгрузка не нужна.","Створиться задача складу в загальному списку, статуси далі рухаються самі. Клікни, якщо відвантаження не потрібне.")
                  : t("Задача складу НЕ создаётся (товар выдан сразу в салоне / услуга). Кликни, чтобы вернуть.","Задача складу НЕ створюється (товар виданий одразу в салоні / послуга). Клікни, щоб повернути.")}</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setVerify(null)}>{t("← Назад","← Назад")}</button>
              <button className="btn btn-primary" style={{ flex: 2 }} onClick={confirmVerify} disabled={sending}>{sending ? "…" : (verify.mode === "credit" ? t("✓ Создать долг (дебиторку)","✓ Створити борг (дебіторку)") : t("✓ Всё верно — провести","✓ Усе правильно — провести"))}</button>
            </div>
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
function CashflowTab({ deal, remaining, onPay, createTTN, issueCheckbox }: any) {
  const { t } = useLang();
  const f = (v: number) => new Intl.NumberFormat("uk").format(Math.round(v || 0));
  const mBox: React.CSSProperties = { background: "#f8fafc", borderRadius: 10, padding: "10px 12px" };
  const paid = deal.paid || 0;
  return (
    <div className="panel" style={{ margin: 0 }}>
      <div className="label" style={{ marginBottom: 12 }}><Icon n="💰" size={16} /> {t("Оплата и доставка","Оплата та доставка")} <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>({t("нативно, без Битрикса","нативно, без Бітрикса")})</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginBottom: 16 }}>
        <div style={mBox}><div className="muted" style={{ fontSize: 12 }}>{t("Сумма","Сума")}</div><div style={{ fontSize: 20, fontWeight: 600 }}>{f(Number(deal.amount))} ₴</div></div>
        <div style={mBox}><div className="muted" style={{ fontSize: 12 }}>{t("Оплачено (за сделку)","Оплачено (за угоду)")}</div><div style={{ fontSize: 20, fontWeight: 600, color: "#16a34a" }}>{f(Math.min(paid, Number(deal.amount)))} ₴</div>{paid > Number(deal.amount) && <div style={{ fontSize: 11, color: "#2563eb", marginTop: 2 }}>{t("+ аванс","+ аванс")} {f(paid - Number(deal.amount))} ₴</div>}</div>
        <div style={mBox}><div className="muted" style={{ fontSize: 12 }}>{t("Осталось","Залишилось")}</div><div style={{ fontSize: 20, fontWeight: 600, color: remaining > 0 ? "#d97706" : "#16a34a" }}>{f(Math.max(0, remaining))} ₴</div></div>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <button className="btn btn-primary" onClick={onPay}><Icon n="💳" size={15} /> {t("Принять оплату","Прийняти оплату")}</button>
        <button className="btn" onClick={issueCheckbox}><Icon n="🧾" size={15} /> {t("Фискальный чек","Фіскальний чек")}</button>
      </div>
      <div className="label" style={{ marginBottom: 6 }}>{t("История платежей","Історія платежів")}</div>
      {(deal.payments || []).length === 0 ? <div className="muted" style={{ fontSize: 13 }}>{t("Платежей пока нет","Платежів поки немає")}</div> :
        (deal.payments || []).map((p: any) => (
          <div key={p.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "6px 0", borderBottom: "1px solid #f1f5f9" }}>
            <span>{t(...methodPair(p.provider))} · {p.created_at ? new Date(p.created_at).toLocaleDateString("uk") : ""}</span>
            <b style={{ color: "#16a34a" }}>{f(Number(p.amount))} ₴</b>
          </div>
        ))}
      <div style={{ display: "flex", gap: 16, marginTop: 14, fontSize: 12 }}>
        <span className="muted">ТТН: {deal.ttn || "—"}</span>
        <span className="muted">{t("Чек","Чек")}: {deal.checkbox_status || "—"}</span>
      </div>
    </div>
  );
}
