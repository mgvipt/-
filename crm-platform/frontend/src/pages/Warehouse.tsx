/* ============================================================================
 *  СКЛАД / КАТАЛОГ ТОВАРОВ  —  frontend/src/pages/Warehouse.tsx
 * ----------------------------------------------------------------------------
 *  Дерево категорий + таблица товаров (поиск, пагинация 5/20/50/100/500),
 *  карточка товара (клик по названию) и ИНВЕНТАРИЗАЦИЯ (проведение).
 *  Документация: docs/CODEMAP.md разд.3.
 *
 *  БЛОКИ:
 *    [1] ТИПЫ
 *    [2] STATE
 *    [3] ЗАГРУЗКА (категории / товары)
 *    [4] ДЕЙСТВИЯ (приход/расход, карточка, инвентаризация)
 *    [5] РЕНДЕР: дерево категорий
 *    [6] РЕНДЕР: тулбар + таблица + пагинация
 *    [7] РЕНДЕР: модалка прихода/расхода
 *    [8] РЕНДЕР: карточка товара
 *    [9] РЕНДЕР: инвентаризация
 *    [10] СУБ-КОМПОНЕНТ: EditCost
 * ========================================================================== */
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { StockTab } from "./Analytics";
import { api, Paginated } from "../api";
import { useLang } from "../i18n";
import { useAuth } from "../auth";
import { Icon } from "../Icon";
import ReceiptModal from "../ReceiptModal";

/* ─── [1] ТИПЫ ─────────────────────────────────────────────────────────── */
interface Product {
  id: number; name: string; sku: string; unit: string;
  price: string; cost: string; cost_pct?: string; min_price?: string; currency: string; margin: number;
  category: number | null; category_name: string; stock: number;
  is_active?: boolean; description?: string; track_stock?: boolean; is_drop?: boolean;
  b24_created_by?: string; b24_modified_by?: string;
  b24_created_at?: string; b24_modified_at?: string;
  images?: { id: number; url: string; alt_text?: string; is_primary?: boolean; is_approved?: boolean; variant_key?: string }[];
  shop_managed?: boolean; shop_enabled?: boolean; shop_category_path?: string[]; shop_status?: string; shop_group_key?: string;
  shop_parent_name?: string; shop_slug?: string; shop_short_description?: string; shop_full_description?: string;
  shop_benefits?: string[]; shop_effect?: string; shop_rooms?: string[]; shop_beginner?: boolean;
  shop_video_url?: string; shop_instruction_url?: string; shop_sort?: number; shop_badges?: string[];
  shop_variant_type?: string; shop_has_board?: boolean | null; shop_is_tinted?: boolean | null;
  shop_variant_order?: number; shop_variant_name?: string; shop_contents?: string;
  seo_title?: string; seo_description?: string; seo_h1?: string; seo_categories?: string[]; seo_faqs?: any[]; seo_index?: boolean;
  shop_last_sync_at?: string; shop_sync_error?: string; shop_remote_url?: string;
  shop_validation_errors?: string[]; shop_group_variants?: any[]; shop_sync_history?: any[];
}
interface Category { id: number; name: string; parent: number | null; order: number; products_count: number; }
interface WH { id: number; name: string; is_default: boolean; }
interface Movement { id: number; kind: string; kind_display: string; quantity: number; price: number; warehouse: string; date: string; number: string | number; }

interface SheetRow { id: number; name: string; unit: string; opening: number; received: number; sold: number; book: number; }
const PAGE_SIZES = [5, 20, 50, 100, 500];
const SHOP_CATEGORY_SUGGESTIONS = [
  "Декоративные покрытия",
  "Декоративные покрытия → Мягкий шёлк",
  "Декоративные покрытия → Камень и травертин",
  "Декоративные покрытия → Бетон",
  "Декоративные покрытия → Перламутр",
  "Пробники",
];
const categoryPathText = (path?: string[]) => (path || []).join(" → ");
const parseCategoryPath = (value: string) => value.split(/\s*(?:→|>|\/)\s*/).map((part) => part.trim()).filter(Boolean);
const pad = (n: number) => String(n).padStart(2, "0");
const today = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const monthStart = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01`; };

export default function Warehouse() {
  /* ─── [2] STATE ──────────────────────────────────────────────────────── */
  const { t } = useLang();
  const { can } = useAuth();
  const showCost = can("product.cost.view");
  const canEdit = can("warehouse.edit");
  const [cats, setCats] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [count, setCount] = useState(0);
  const [cat, setCat] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [whs, setWhs] = useState<WH[]>([]);
  const [modal, setModal] = useState<null | "in" | "out">(null);
  const [receiptFor, setReceiptFor] = useState<{ productId?: number; productName?: string } | null>(null);
  const canRealize = can("warehouse.edit") || can("finance.manage");
  const canTabReal = can("warehouse.tab.realizations");
  const canTabRec = can("warehouse.tab.receipts");
  const canTabInv = can("warehouse.tab.inventory");
  const canTabStat = can("analytics.warehouse");
  // якщо збережена вкладка стала недоступною (зняли право) — повертаємось до товарів
  useEffect(() => {
    if ((view === "realiz" && !canTabReal) || (view === "receipt" && !canTabRec) ||
        (view === "inv" && !canTabInv) || (view === "stat" && !canTabStat)) setView("goods");
    // eslint-disable-next-line
  }, [canTabReal, canTabRec, canTabInv, canTabStat]);
  const [view, setView] = useState<"goods" | "realiz" | "receipt" | "inv" | "stat">(() => (localStorage.getItem("whacc_tab") as any) || "goods");
  useEffect(() => { try { localStorage.setItem("whacc_tab", view); } catch (e) { /* noop */ } }, [view]);
  // авто-загрузка списка документов при входе на вкладку (в т.ч. после перезагрузки / создания прихода)
  useEffect(() => { if (view === "receipt") openReceiptList(); else if (view === "realiz") openRealizList(); else if (view === "inv") openInventory(); /* eslint-disable-next-line */ }, [view]);
  const [realizDocs, setRealizDocs] = useState<any[]>([]);
  const [realizBusy, setRealizBusy] = useState(false);
  const [realizSel, setRealizSel] = useState<any>(null);
  const [receiptDocs, setReceiptDocs] = useState<any[]>([]);
  const [receiptBusy, setReceiptBusy] = useState(false);
  const [receiptSel, setReceiptSel] = useState<any>(null);
  const [docPage, setDocPage] = useState({ realiz: 1, receipt: 1 });
  const [docPS, setDocPS] = useState({ realiz: 25, receipt: 25 });
  const [docCount, setDocCount] = useState({ realiz: 0, receipt: 0 });
  async function openReceiptList(pg?: number, ps?: number) {
    setReceiptBusy(true);
    const page = pg ?? docPage.receipt, size = ps ?? docPS.receipt;
    try { const r: any = await api.get(`/api/stock-documents/?kind=in&page=${page}&page_size=${size}`);
      setReceiptDocs(Array.isArray(r) ? r : (r.results || [])); setDocCount((c) => ({ ...c, receipt: r.count ?? (r.results || r).length })); }
    catch { setReceiptDocs([]); }
    setReceiptBusy(false);
  }
  function docTitle(d: any) {
    return (d.number || ("РН-" + d.id)) + " · " + (d.deal_title || (d.deal ? t("угода","угода") + " #" + d.deal : t("ручное","ручне"))) + " · " + (d.created_at || "").slice(0, 10);
  }
  async function openRealizList(pg?: number, ps?: number) {
    setRealizBusy(true);
    const page = pg ?? docPage.realiz, size = ps ?? docPS.realiz;
    try { const r: any = await api.get(`/api/stock-documents/?kind=out&page=${page}&page_size=${size}`);
      setRealizDocs(Array.isArray(r) ? r : (r.results || [])); setDocCount((c) => ({ ...c, realiz: r.count ?? (r.results || r).length })); }
    catch { setRealizDocs([]); }
    setRealizBusy(false);
  }
  async function realizRefresh() {
    try { const r: any = await api.get("/api/stock-documents/?kind=out"); const docs = Array.isArray(r) ? r : (r.results || []); setRealizDocs(docs); setRealizSel((s: any) => s ? (docs.find((x: any) => x.id === s.id) || null) : null); }
    catch { /* */ }
  }
  async function realizPost(rid: number) {
    try { await api.post(`/api/stock-documents/${rid}/post/`, {}); await realizRefresh(); loadProducts(); }
    catch { alert(t("Нет доступа (нужно «Редактировать склад» или «Финмодель»)","Немає доступу (потрібне «Редагувати склад» або «Фінмодель»)")); }
  }
  async function realizUnpost(rid: number) {
    if (!confirm(t("Отменить проведение? Товар вернётся на склад, себестоимость сторнируется.","Скасувати проведення? Товар повернеться на склад, собівартість сторнується."))) return;
    try { await api.post(`/api/stock-documents/${rid}/unpost/`, {}); await realizRefresh(); loadProducts(); }
    catch { alert(t("Нет доступа (нужно «Редактировать склад» или «Финмодель»)","Немає доступу (потрібне «Редагувати склад» або «Фінмодель»)")); }
  }
  const [form, setForm] = useState({ product: 0, quantity: 1, price: 0 });
  const [loading, setLoading] = useState(false);
  const [ordering, setOrdering] = useState("");
  const [catW, setCatW] = useState(() => Number(localStorage.getItem("wh_cat_w")) || 260);
  // карточка товара
  const [card, setCard] = useState<Product | null>(null);
  const [cardTab, setCardTab] = useState<"main" | "shop" | "media" | "sync">("main");
  const shopImageRef = useRef<HTMLInputElement>(null);
  const [movements, setMovements] = useState<Movement[]>([]);
  // фільтр по номенклатурі
  const [fltOpen, setFltOpen] = useState(false);
  const [fltActive, setFltActive] = useState<"active" | "all" | "hidden">("active");
  const [fltStock, setFltStock] = useState<"" | "in" | "zero">("");
  // створення товару
  const [newOpen, setNewOpen] = useState(false);
  const [newP, setNewP] = useState<any>({ name: "", sku: "", unit: "шт", price: "", cost: "", category: 0 });
  async function createProduct() {
    if (!newP.name.trim()) { alert(t("Укажи название","Вкажи назву")); return; }
    try {
      const p: any = await api.post("/api/products/", { name: newP.name.trim(), sku: newP.sku.trim(), unit: newP.unit || "шт",
        price: Number(newP.price) || 0, cost: Number(newP.cost) || 0, category: newP.category || null, is_active: true });
      setNewOpen(false); setNewP({ name: "", sku: "", unit: "шт", price: "", cost: "", category: 0 });
      loadProducts(); openCard(p);
    } catch { alert(t("Не удалось создать (нужно право «Редактировать склад»)","Не вдалося створити (потрібне право «Редагувати склад»)")); }
  }
  // масові дії над товарами
  const [selIds, setSelIds] = useState<Set<number>>(new Set());
  const [bulkUnit, setBulkUnit] = useState("");
  const UNITS = ["шт", "кг", "г", "л", "мл", "м", "см", "м²", "м³", "пог.м", "рулон", "упаковка",
                 "комплект", "набір", "пара", "відро", "банка", "пляшечка", "туба", "мішок",
                 "пачка", "лист", "день", "година", "послуга"];
  function toggleSel(id: number) {
    setSelIds((prev) => { const nx = new Set(prev); if (nx.has(id)) nx.delete(id); else nx.add(id); return nx; });
  }
  function toggleSelAll() {
    setSelIds((prev) => prev.size === products.length ? new Set() : new Set(products.map((p) => p.id)));
  }
  async function applyBulkUnit() {
    if (!bulkUnit || selIds.size === 0) return;
    try {
      const r: any = await api.post("/api/products/bulk-unit/", { ids: Array.from(selIds), unit: bulkUnit });
      alert(t("Обновлено товаров","Оновлено товарів") + `: ${r.updated} → ${r.unit}`);
      setSelIds(new Set()); setBulkUnit(""); loadProducts();
    } catch { alert(t("Не удалось (нужно право «Редактировать склад»)","Не вдалося (потрібне право «Редагувати склад»)")); }
  }
  async function delCategory(c: Category, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      const dry: any = await api.del(`/api/product-categories/${c.id}/?dry=1`);
      const msg = t("Удалить папку","Видалити папку") + ` «${c.name}»?\n` +
        t("Подпапок (вкл. эту)","Підпапок (разом із цією)") + `: ${dry.categories}\n` +
        t("Товаров удалится навсегда","Товарів видалиться назавжди") + `: ${dry.products_delete}\n` +
        t("Товаров скроется (есть движения)","Товарів приховається (є рухи)") + `: ${dry.products_hide}`;
      if (!confirm(msg)) return;
      const r: any = await api.del(`/api/product-categories/${c.id}/`);
      alert(t("Готово ✓ Папок","Готово ✓ Папок") + `: ${r.categories}, ` + t("удалено товаров","видалено товарів") + `: ${r.products_deleted}, ` + t("скрыто","приховано") + `: ${r.products_hidden}`);
      if (cat === c.id) pick(null);
      api.get<Category[]>("/api/product-categories/").then(setCats).catch(() => {});
      loadProducts();
    } catch { alert(t("Не удалось удалить (нужно право «Редактировать склад»)","Не вдалося видалити (потрібне право «Редагувати склад»)")); }
  }
  // редагування картки
  const [cardEdit, setCardEdit] = useState<any>(null);
  // склад набору (комплект)
  const [bundle, setBundle] = useState<any>(null);
  const [bundleQ, setBundleQ] = useState("");
  const [bundleOpts, setBundleOpts] = useState<any[]>([]);
  async function loadBundle(pid: number) {
    try { setBundle(await api.get(`/api/products/${pid}/components/`)); } catch { setBundle(null); }
  }
  useEffect(() => {
    if (!bundleQ.trim()) { setBundleOpts([]); return; }
    const tmr = setTimeout(async () => {
      try { const r: any = await api.get(`/api/products/?search=${encodeURIComponent(bundleQ.trim())}&page_size=8&is_active=true`); setBundleOpts((r.results || []).filter((x: any) => !x.is_bundle && x.id !== card?.id)); }
      catch { setBundleOpts([]); }
    }, 300);
    return () => clearTimeout(tmr);
    // eslint-disable-next-line
  }, [bundleQ]);
  async function saveBundle(rows: any[]) {
    if (!card) return;
    try {
      const r: any = await api.post(`/api/products/${card.id}/components/`, { components: rows.map((x: any) => ({ component: x.component, quantity: x.quantity })) });
      setBundle(r); loadProducts();
      try { setCard(await api.get<Product>(`/api/products/${card.id}/`)); } catch { /* */ }
    } catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось сохранить состав","Не вдалося зберегти склад")); }
  }
  async function saveCard() {
    if (!card || !cardEdit) return;
    try {
      const upd: any = await api.patch(`/api/products/${card.id}/`, {
        name: cardEdit.name, description: cardEdit.description, category: cardEdit.category || null,
        price: Number(cardEdit.price) || 0, cost: Number(cardEdit.cost) || 0, cost_pct: Number(cardEdit.cost_pct) || 0, min_price: Number(cardEdit.min_price) || 0, unit: cardEdit.unit,
        sku: cardEdit.sku, is_active: cardEdit.is_active, track_stock: cardEdit.track_stock, is_drop: cardEdit.is_drop,
        shop_enabled: cardEdit.shop_enabled, shop_category_path: cardEdit.shop_category_path, shop_group_key: cardEdit.shop_group_key,
        shop_parent_name: cardEdit.shop_parent_name, shop_slug: cardEdit.shop_slug,
        shop_short_description: cardEdit.shop_short_description, shop_full_description: cardEdit.shop_full_description,
        shop_effect: cardEdit.shop_effect, shop_rooms: cardEdit.shop_rooms,
        shop_beginner: cardEdit.shop_beginner, shop_video_url: cardEdit.shop_video_url,
        shop_instruction_url: cardEdit.shop_instruction_url, shop_sort: Number(cardEdit.shop_sort) || 0,
        shop_variant_type: cardEdit.shop_variant_type, shop_has_board: cardEdit.shop_has_board,
        shop_is_tinted: cardEdit.shop_is_tinted, shop_variant_order: Number(cardEdit.shop_variant_order) || 0,
        shop_variant_name: cardEdit.shop_variant_name, shop_contents: cardEdit.shop_contents,
        seo_title: cardEdit.seo_title, seo_description: cardEdit.seo_description,
        seo_h1: cardEdit.seo_h1, seo_index: cardEdit.seo_index });
      setCard(upd); setCardEdit(null); loadProducts();
      api.get<Category[]>("/api/product-categories/").then(setCats).catch(() => {});
    } catch { alert(t("Не удалось сохранить","Не вдалося зберегти")); }
  }
  // инвентаризация
  const [facts, setFacts] = useState<Record<number, string>>({});
  const [invMsg, setInvMsg] = useState("");
  const [sheet, setSheet] = useState<SheetRow[]>([]);
  const [pFrom, setPFrom] = useState(monthStart());
  const [pTo, setPTo] = useState(today());
  // инвентаризация: собственный список (независимо от вкладки «Товары») — весь склад с фильтром и пагинацией
  const [invMode, setInvMode] = useState<"all" | "folder">("all"); // все товары / по папке
  const [invCat, setInvCat] = useState<number | null>(null);        // выбранная папка (при invMode="folder")
  const [invPage, setInvPage] = useState(1);
  const [invPageSize, setInvPageSize] = useState(50);
  const [invCount, setInvCount] = useState(0);
  const [invLoading, setInvLoading] = useState(false);
  const [invPrinting, setInvPrinting] = useState(false);
  const [invBusy, setInvBusy] = useState(false);
  const [invConfirm, setInvConfirm] = useState<null | { items: { product: number; name: string; unit: string; book: number; fact: number; delta: number; quantity: number; price: number }[] }>(null);
  const invTotalPages = Math.max(1, Math.ceil(invCount / invPageSize));
  // инвентаризация: экран (ведомость / история проведённых) + список истории
  const [invScreen, setInvScreen] = useState<"sheet" | "history">("sheet");
  const [invHistDocs, setInvHistDocs] = useState<any[]>([]);
  const [invHistBusy, setInvHistBusy] = useState(false);
  const [invHistSel, setInvHistSel] = useState<any>(null);
  const [invHistPage, setInvHistPage] = useState(1);
  const [invHistCount, setInvHistCount] = useState(0);
  const invHistPageSize = 20;
  const invHistTotalPages = Math.max(1, Math.ceil(invHistCount / invHistPageSize));

  /* ─── [3] ЗАГРУЗКА ───────────────────────────────────────────────────── */
  const [params] = useSearchParams();
  useEffect(() => {
    const pid = params.get("product");
    if (pid) { api.get<Product>(`/api/products/${pid}/`).then((p) => openCard(p)).catch(() => {}); }
    const did = params.get("doc");
    if (did) {
      api.get<any>(`/api/stock-documents/${did}/`).then((doc) => {
        if (doc.kind === "out") { setView("realiz"); setRealizSel(doc); openRealizList(); }
        else { setView("receipt"); setReceiptSel(doc); openReceiptList(); }
      }).catch(() => {});
    }
    // eslint-disable-next-line
  }, []);
  useEffect(() => {
    api.get<Category[]>("/api/product-categories/").then(setCats).catch(() => setCats([]));
    api.get<Paginated<WH>>("/api/warehouses/").then((w) => setWhs(w.results));
  }, []);
  useEffect(() => {
    const pid = params.get("p");
    if (pid) api.get<Product>(`/api/products/${pid}/`).then(openCard).catch(() => {});
  }, [params]);

  async function loadProducts() {
    setLoading(true);
    const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (cat) q.set("category", String(cat));
    if (search.trim()) q.set("search", search.trim());
    if (ordering) q.set("ordering", ordering);
    if (fltActive === "active") q.set("is_active", "true");
    if (fltActive === "hidden") q.set("is_active", "false");
    if (fltStock === "in") q.set("in_stock", "1");
    if (fltStock === "zero") q.set("in_stock", "0");
    const d = await api.get<Paginated<Product>>(`/api/products/?${q.toString()}`);
    setProducts(d.results); setCount(d.count); setLoading(false);
  }
  useEffect(() => { loadProducts(); }, [cat, page, pageSize, ordering, fltActive, fltStock]);
  useEffect(() => {
    const t = setTimeout(() => { setPage(1); loadProducts(); }, 350);
    return () => clearTimeout(t);
  }, [search]);

  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  /* ─── [4] ДЕЙСТВИЯ ───────────────────────────────────────────────────── */
  async function saveDoc() {
    if (!form.product) return;
    let kind: string = modal || "in";
    let comment = "";
    if (modal === "out") {
      kind = "writeoff"; // ручне списання = порча/брак/викраска, НЕ реалізація по угоді
      comment = prompt(t("Причина списания (обязательно): брак, порча, выкраска…","Причина списання (обовʼязково): брак, псування, викраска…")) || "";
      if (!comment.trim()) { alert(t("Без причины списание не проводится.","Без причини списання не проводиться.")); return; }
    }
    await api.post("/api/stock-documents/", {
      kind, warehouse: whs[0]?.id, comment,
      items: [{ product: form.product, quantity: form.quantity, price: form.price }],
    });
    setModal(null); setForm({ product: 0, quantity: 1, price: 0 });
    loadProducts(); openReceiptList(); openRealizList();
  }

  async function openCard(p: Product) {
    setCard(p); setMovements([]); setCardEdit(null); setCardTab("main"); setBundle(null); setBundleQ("");
    loadBundle(p.id);
    try { setCard(await api.get<Product>(`/api/products/${p.id}/`)); } catch { /* */ }
    const mv = await api.get<Movement[]>(`/api/products/${p.id}/movements/`);
    setMovements(mv);
  }

  async function refreshCard() {
    if (!card) return;
    const fresh = await api.get<Product>(`/api/products/${card.id}/`);
    setCard(fresh);
  }
  async function queueShopSync() {
    if (!card) return;
    try { await api.post(`/api/products/${card.id}/shop-sync/`, {}); await refreshCard(); }
    catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось отправить","Не вдалося надіслати")); }
  }
  async function uploadShopImage(file?: File) {
    if (!card || !file) return;
    try { await api.upload(`/api/products/${card.id}/shop-images/`, file); await refreshCard(); }
    catch { alert(t("Фото не загрузилось. Допустимы JPG, PNG, WEBP до 10 МБ.","Фото не завантажилося. Дозволені JPG, PNG, WEBP до 10 МБ.")); }
  }
  async function patchShopImage(id: number, body: any) {
    if (!card) return;
    await api.patch(`/api/products/${card.id}/shop-images/${id}/`, body); await refreshCard();
  }
  async function deleteShopImage(id: number) {
    if (!card || !confirm(t("Удалить фото?","Видалити фото?"))) return;
    await api.del(`/api/products/${card.id}/shop-images/${id}/`); await refreshCard();
  }

  // строит параметры запроса ведомости из переданных опций или текущего состояния инвентаризации
  function invParams(from: string, to: string, o?: { page?: number; pageSize?: number; cat?: number | null; mode?: "all" | "folder"; all?: boolean }) {
    const mode = o?.mode ?? invMode;
    const c = o?.cat !== undefined ? o.cat : invCat;
    const q = new URLSearchParams({ from, to });
    if (o?.all) { q.set("all", "1"); }
    else { q.set("page", String(o?.page ?? invPage)); q.set("page_size", String(o?.pageSize ?? invPageSize)); }
    if (mode === "folder" && c) q.set("category", String(c));
    return q;
  }
  // грузит одну страницу ведомости; факт, уже введённый пользователем, НЕ затирает
  async function loadSheet(from: string, to: string, o?: { page?: number; pageSize?: number; cat?: number | null; mode?: "all" | "folder" }) {
    setInvLoading(true);
    try {
      const q = invParams(from, to, o);
      const d = await api.get<{ rows: SheetRow[]; count: number }>(`/api/warehouse/inventory-sheet/?${q.toString()}`);
      setSheet(d.rows);
      setInvCount(d.count ?? d.rows.length);
      setFacts((prev) => { const next = { ...prev }; d.rows.forEach((r) => { if (next[r.id] === undefined) next[r.id] = String(r.book); }); return next; });
    } catch { setSheet([]); }
    setInvLoading(false);
  }
  async function openInventory() {
    setInvMsg("");
    setInvPage(1);
    await loadSheet(pFrom, pTo, { page: 1 });
  }
  // шаг 1: собрать расхождения текущей страницы и открыть встроенное окно подтверждения (без браузерного confirm)
  function conductInventory() {
    const items = sheet
      .filter((r) => facts[r.id] !== undefined && Number(facts[r.id]) !== Number(r.book))
      .map((r) => {
        const q = Number(facts[r.id]);
        return { product: r.id, name: r.name, unit: r.unit, book: Number(r.book), fact: q, delta: q - Number(r.book), quantity: q, price: 0 };
      });
    if (!items.length) {
      setInvMsg(t("⚠ Расхождений нет: впишите фактический остаток в колонку «Факт» у нужных товаров, потом жмите «Провести».","⚠ Розбіжностей немає: впишіть фактичний залишок у колонку «Факт» у потрібних товарів, потім тисніть «Провести»."));
      return;
    }
    setInvConfirm({ items });
  }
  // шаг 2: подтверждено во встроенном окне — проводим
  async function doConduct() {
    const items = (invConfirm?.items || []).map((r) => ({ product: r.product, quantity: r.quantity, price: 0 }));
    if (!items.length) { setInvConfirm(null); return; }
    setInvBusy(true);
    try {
      await api.post("/api/stock-documents/", { kind: "inv", warehouse: whs[0]?.id, comment: `Інвентаризація ${pFrom}…${pTo}`, items });
      setInvConfirm(null);
      loadProducts(); loadSheet(pFrom, pTo); loadInvHistory(1);
      setInvMsg(t(`✓ Инвентаризация проведена. Скорректировано позиций: ${items.length}. Запись добавлена в «Историю».`,`✓ Інвентаризацію проведено. Скориговано позицій: ${items.length}. Запис додано в «Історію».`));
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || "";
      setInvConfirm(null);
      setInvMsg(t("✗ Не удалось провести инвентаризацию. ","✗ Не вдалося провести інвентаризацію. ") + msg);
    }
    setInvBusy(false);
  }
  // история проведённых инвентаризаций (документы kind=inv)
  async function loadInvHistory(pg?: number) {
    setInvHistBusy(true);
    const page = pg ?? invHistPage;
    setInvHistPage(page);
    try {
      const r: any = await api.get(`/api/stock-documents/?kind=inv&page=${page}&page_size=${invHistPageSize}`);
      setInvHistDocs(Array.isArray(r) ? r : (r.results || []));
      setInvHistCount(r.count ?? (r.results || r).length);
    } catch { setInvHistDocs([]); }
    setInvHistBusy(false);
  }
  // печать всей ведомости (все страницы по текущему фильтру) с пустой колонкой «Факт» для отметок на физскладе
  async function printInventory() {
    setInvPrinting(true);
    try {
      const q = invParams(pFrom, pTo, { all: true });
      const d = await api.get<{ rows: SheetRow[]; count: number }>(`/api/warehouse/inventory-sheet/?${q.toString()}`);
      const rows = d.rows || [];
      const scope = invMode === "folder" && invCat
        ? (cats.find((c) => c.id === invCat)?.name || t("папка","папка"))
        : t("все товары","всі товари");
      const esc = (s: any) => String(s ?? "").replace(/[&<>]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[m] as string));
      const body = rows.map((r, i) => `<tr><td class="n">${i + 1}</td><td>${esc(r.name)}</td><td class="c">${esc(r.unit)}</td><td class="r">${r.book.toLocaleString("ru")}</td><td class="fact"></td><td class="note"></td></tr>`).join("");
      const html = `<!doctype html><html><head><meta charset="utf-8"><title>${t("Инвентаризация","Інвентаризація")} ${pFrom}—${pTo}</title>
<style>
  *{box-sizing:border-box} body{font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#111;margin:18px}
  h1{font-size:17px;margin:0 0 2px} .sub{font-size:12px;color:#555;margin:0 0 12px}
  table{width:100%;border-collapse:collapse;font-size:12px} th,td{border:1px solid #333;padding:5px 7px;text-align:left}
  th{background:#eee} td.n,th.n{width:34px;text-align:center} td.c,th.c{text-align:center;width:52px}
  td.r,th.r{text-align:right;width:90px} td.fact,th.fact{width:110px} td.note,th.note{width:150px}
  td.fact{height:26px} tr{break-inside:avoid}
  .sign{margin-top:26px;font-size:12px;display:flex;gap:60px}
  @media print{body{margin:8mm} @page{margin:8mm}}
</style></head><body onload="window.print()">
  <h1>${t("Инвентаризационная ведомость","Інвентаризаційна відомість")}</h1>
  <p class="sub">${t("Период","Період")}: ${pFrom} — ${pTo} · ${t("Отображение","Відображення")}: ${esc(scope)} · ${t("Позиций","Позицій")}: ${rows.length} · ${t("Дата печати","Дата друку")}: ${today()}</p>
  <table><thead><tr><th class="n">№</th><th>${t("Товар","Товар")}</th><th class="c">${t("Ед.","Од.")}</th><th class="r">${t("Учёт","Облік")}</th><th class="fact">${t("Факт (вписать)","Факт (вписати)")}</th><th class="note">${t("Примечание","Примітка")}</th></tr></thead><tbody>${body}</tbody></table>
  <div class="sign"><div>${t("Провёл(а): _______________","Провів(ла): _______________")}</div><div>${t("Подпись: _______________","Підпис: _______________")}</div></div>
</body></html>`;
      const w = window.open("", "_blank");
      if (!w) { setInvMsg(t("Разрешите всплывающие окна для печати.","Дозвольте спливаючі вікна для друку.")); return; }
      w.document.write(html); w.document.close();
    } catch { setInvMsg(t("Не удалось сформировать печать.","Не вдалося сформувати друк.")); }
    setInvPrinting(false);
  }

  const tree = useMemo(() => {
    const roots = cats.filter((c) => !c.parent).sort((a, b) => a.name.localeCompare(b.name));
    const childrenOf = (id: number) => cats.filter((c) => c.parent === id).sort((a, b) => a.name.localeCompare(b.name));
    return { roots, childrenOf };
  }, [cats]);
  function pick(id: number | null) { setCat(id); setPage(1); }
  async function delProduct(p: Product) {
    if (!confirm(t("Удалить товар «", "Видалити товар «") + p.name + "»?")) return;
    try {
      const r: any = await api.del(`/api/products/${p.id}/`);
      if (r && r.hidden) alert(t("Товар имеет движения — скрыт (история сохранена).", "Товар має рухи — приховано (історія збережена)."));
    } catch { alert(t("Нет прав или ошибка", "Немає прав або помилка")); }
    loadProducts();
  }
  async function exportCsv() {
    const q = new URLSearchParams();
    if (cat) q.set("category", String(cat));
    if (search.trim()) q.set("search", search.trim());
    try { const u = await (api as any).blobUrl(`/api/products/export/?${q.toString()}`); const a = document.createElement("a"); a.href = u; a.download = "nomenklatura.csv"; a.click(); }
    catch { alert(t("Не удалось выгрузить", "Не вдалося вивантажити")); }
  }
  const nomFileRef = useRef<HTMLInputElement>(null);
  async function importNom(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return; e.target.value = "";
    let text = ""; try { text = await f.text(); } catch { return; }
    try {
      const dry: any = await api.post("/api/products/import/", { data: text, commit: false });
      const msg = t("Импорт номенклатуры:", "Імпорт номенклатури:") + "\n" + t("Новых: ", "Нових: ") + dry.created + "\n" + t("Обновлений: ", "Оновлень: ") + dry.updated + "\n" + t("Ошибок: ", "Помилок: ") + dry.errors + (dry.err_samples && dry.err_samples.length ? "\n" + dry.err_samples.join("\n") : "") + "\n\n" + t("Применить? Остатки НЕ меняются.", "Застосувати? Залишки НЕ змінюються.");
      if (!confirm(msg)) return;
      await api.post("/api/products/import/", { data: text, commit: true });
      alert(t("Готово ✓", "Готово ✓")); loadProducts();
      api.get<Category[]>("/api/product-categories/").then(setCats).catch(() => {});
    } catch { alert(t("Не удалось импортировать (нужно право «Редактировать склад»)", "Не вдалося імпортувати (потрібне право «Редагувати склад»)")); }
  }
  const receiptFileRef = useRef<HTMLInputElement>(null);
  async function importReceipt(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return; e.target.value = "";
    let text = ""; try { text = await f.text(); } catch { return; }
    try {
      const dry: any = await api.post("/api/stock-documents/import-receipt/", { data: text, commit: false });
      const msg = t("Приход файлом:", "Прихід файлом:") + "\n" + t("Позиций: ", "Позицій: ") + dry.positions + "\n" + t("Всего кол-во: ", "Всього к-сть: ") + dry.total_qty + "\n" + t("Сумма: ", "Сума: ") + dry.total_sum + " ₴\n" + t("Ошибок/не найдено: ", "Помилок/не знайдено: ") + dry.errors + (dry.err_samples && dry.err_samples.length ? "\n" + dry.err_samples.join("\n") : "") + "\n\n" + t("Провести приход?", "Провести прихід?");
      if (dry.positions === 0) { alert(t("Нет ни одной подходящей позиции.", "Немає жодної придатної позиції.") + (dry.err_samples ? "\n" + dry.err_samples.join("\n") : "")); return; }
      if (!confirm(msg)) return;
      const done: any = await api.post("/api/stock-documents/import-receipt/", { data: text, commit: true, warehouse: whs[0]?.id });
      alert(t("Приход проведён ✓ Позиций: ", "Прихід проведено ✓ Позицій: ") + done.positions); loadProducts(); openReceiptList();
    } catch { alert(t("Не удалось (нужно право «Редактировать склад»)", "Не вдалося (потрібне право «Редагувати склад»)")); }
  }
  function toggleSort(f: string) { setOrdering(ordering === f ? "-" + f : ordering === "-" + f ? "" : f); setPage(1); }
  const sortTh = (field: string, label: string) => {
    const d = ordering === field ? "\u2191" : ordering === "-" + field ? "\u2193" : "";
    return <th onClick={() => toggleSort(field)} style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }} title={t("Сортировать","Сортувати")}>{label} <span style={{ color: d ? "#1d4ed8" : "#cbd5e1", fontSize: 11 }}>{d || "\u2195"}</span></th>;
  };
  function startResize(e: React.MouseEvent) {
    e.preventDefault();
    const sx = e.clientX, sw = catW;
    const mv = (ev: MouseEvent) => { const w = Math.max(170, Math.min(520, sw + ev.clientX - sx)); setCatW(w); localStorage.setItem("wh_cat_w", String(w)); };
    const up = () => { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); document.body.style.cursor = ""; };
    document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up); document.body.style.cursor = "col-resize";
  }

  return (
    <div className="scroll pad fade">
      {/* ── ВКЛАДКИ: Товари / Реалізації ── */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10, borderBottom: "2px solid #e2e8f0", paddingBottom: 8 }}>
        <button className={"btn" + (view === "goods" ? " btn-primary" : " btn-light")} onClick={() => setView("goods")}><Icon n="📦" size={15} /> {t("Товары и остатки","Товари та залишки")}</button>
        {canTabReal && <button className={"btn" + (view === "realiz" ? " btn-primary" : " btn-light")} onClick={() => { setView("realiz"); setRealizSel(null); openRealizList(); }}><Icon n="📤" size={15} /> {t("Реализации","Реалізації")}</button>}
        {canTabRec && <button className={"btn" + (view === "receipt" ? " btn-primary" : " btn-light")} onClick={() => { setView("receipt"); setReceiptSel(null); openReceiptList(); }}><Icon n="📥" size={15} /> {t("Приходные накладные","Прибуткові накладні")}</button>}
        {canTabInv && <button className={"btn" + (view === "inv" ? " btn-primary" : " btn-light")} onClick={() => { setView("inv"); openInventory(); }}><Icon n="📋" size={15} /> {t("Инвентаризация","Інвентаризація")}</button>}
        {canTabStat && <button className={"btn" + (view === "stat" ? " btn-primary" : " btn-light")} onClick={() => setView("stat")}><Icon n="📊" size={15} /> {t("Аналитика","Аналітика")}</button>}
      </div>

      {view === "realiz" ? (
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
        {realizSel ? (
          <>
            <button className="btn btn-light" onClick={() => setRealizSel(null)}>← {t("К списку реализаций","До списку реалізацій")}</button>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10, marginTop: 12 }}>
              <div>
                <h3 style={{ margin: "0 0 4px" }}>{t("Реализация","Реалізація")} {docTitle(realizSel)} <button className="btn btn-light" style={{ padding: "2px 8px" }} title={t("Скопировать ссылку","Скопіювати посилання")} onClick={() => { navigator.clipboard?.writeText(window.location.origin + "/warehouse?doc=" + realizSel.id); alert(t("Ссылка скопирована ✓","Посилання скопійовано ✓")); }}>🔗</button></h3>
                <div className="muted" style={{ fontSize: 12 }}>{t("Стадия закрытия","Стадія закриття")}: <b>{realizSel.close_stage || "—"}</b></div>
              </div>
              <div style={{ textAlign: "right" }}>
                <span style={{ padding: "3px 10px", borderRadius: 6, fontSize: 13, fontWeight: 700, background: realizSel.posted ? "#dcfce7" : "#fef3c7", color: realizSel.posted ? "#166534" : "#92400e" }}>{realizSel.posted ? t("Проведён","Проведено") : t("Черновик","Чернетка")}</span>
                {canRealize && <div style={{ marginTop: 8 }}>{realizSel.posted
                  ? <button className="btn btn-light" onClick={() => realizUnpost(realizSel.id)}>{t("Отменить проведение","Скасувати проведення")}</button>
                  : <button className="btn btn-primary" onClick={() => realizPost(realizSel.id)}>{t("Провести","Провести")}</button>}</div>}
              </div>
            </div>
            <table style={{ width: "100%", marginTop: 14 }}>
              <thead><tr><th>{t("Товар","Товар")}</th><th style={{ textAlign: "right" }}>{t("Кол-во","К-сть")}</th><th style={{ textAlign: "right" }}>{t("Себестоимость","Собівартість")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th></tr></thead>
              <tbody>{(realizSel.items || []).map((it: any) => (
                <tr key={it.id}><td>{it.product_name}</td><td style={{ textAlign: "right" }}>{Math.abs(Number(it.quantity))}</td><td style={{ textAlign: "right" }}>{Number(it.price).toLocaleString("uk-UA")} ₴</td><td style={{ textAlign: "right" }}>{(Math.abs(Number(it.quantity)) * Number(it.price)).toLocaleString("uk-UA")} ₴</td></tr>
              ))}</tbody>
            </table>
          </>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <h3 style={{ margin: 0 }}>{t("Реализации (расходные накладные)","Реалізації (видаткові накладні)")}</h3>
              {canEdit && <button className="btn btn-light" onClick={() => setModal("out")} title={t("Списание: брак, порча, выкраска (не по сделке)","Списання: брак, псування, викраска (не за угодою)")}><Icon n="🗑" size={14} /> {t("Списание (брак/порча)","Списання (брак/псування)")}</button>}
            </div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("Создаются автоматически, когда угода переходит в стадию «Успешная». «Проведён» = товар списан со склада. Кликните на строку — откроется документ. Провести/отменить может ответственный за склад или бухгалтер.","Створюються автоматично, коли угода переходить у стадію «Успішна». «Проведено» = товар списано зі складу. Клікніть на рядок — відкриється документ. Провести/скасувати може відповідальний за склад або бухгалтер.")}</div>
            {realizBusy ? <div className="muted" style={{ padding: 16 }}>{t("Загрузка…","Завантаження…")}</div> :
             realizDocs.length === 0 ? <div className="muted" style={{ padding: 16 }}>{t("Пока нет реализаций.","Поки немає реалізацій.")}</div> :
            <table style={{ width: "100%" }}>
              <thead><tr><th>№</th><th>{t("Дата","Дата")}</th><th>{t("Угода","Угода")}</th><th>{t("Стадия закрытия","Стадія закриття")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th><th style={{ textAlign: "center" }}>{t("Статус","Статус")}</th><th></th></tr></thead>
              <tbody>{realizDocs.map((d: any) => (
                <tr key={d.id} onClick={() => setRealizSel(d)} style={{ cursor: "pointer" }} title={t("Открыть документ","Відкрити документ")}>
                  <td><b>{d.number || d.id}</b></td>
                  <td className="muted">{(d.created_at || "").slice(0, 10)}</td>
                  <td>{d.deal_title || (d.deal ? "#" + d.deal : t("ручное","ручне"))}</td>
                  <td className="muted">{d.close_stage || "—"}</td>
                  <td style={{ textAlign: "right" }}>{Number(d.total || 0).toLocaleString("uk-UA")} ₴</td>
                  <td style={{ textAlign: "center" }}><span style={{ padding: "2px 8px", borderRadius: 6, fontSize: 12, fontWeight: 600, background: d.posted ? "#dcfce7" : "#fef3c7", color: d.posted ? "#166534" : "#92400e" }}>{d.posted ? t("Проведён","Проведено") : t("Черновик","Чернетка")}</span></td>
                  <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                    {canRealize && (d.posted
                      ? <button className="btn btn-light" style={{ padding: "3px 10px" }} onClick={() => realizUnpost(d.id)}>{t("Отменить","Скасувати")}</button>
                      : <button className="btn btn-primary" style={{ padding: "3px 10px" }} onClick={() => realizPost(d.id)}>{t("Провести","Провести")}</button>)}
                  </td>
                </tr>
              ))}</tbody>
            </table>}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
              <span className="muted" style={{ fontSize: 12 }}>{t("Строк","Рядків")}:</span>
              {[25, 50, 100].map((n) => <button key={n} className={"btn" + (docPS.realiz === n ? " btn-primary" : " btn-light")} style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => { setDocPS((x) => ({ ...x, realiz: n })); setDocPage((x) => ({ ...x, realiz: 1 })); openRealizList(1, n); }}>{n}</button>)}
              <div style={{ flex: 1 }} />
              <button className="btn btn-light" disabled={docPage.realiz <= 1} onClick={() => { const p = docPage.realiz - 1; setDocPage((x) => ({ ...x, realiz: p })); openRealizList(p); }}>←</button>
              <span style={{ fontSize: 12 }}>{docPage.realiz} / {Math.max(1, Math.ceil(docCount.realiz / docPS.realiz))}</span>
              <button className="btn btn-light" disabled={docPage.realiz >= Math.ceil(docCount.realiz / docPS.realiz)} onClick={() => { const p = docPage.realiz + 1; setDocPage((x) => ({ ...x, realiz: p })); openRealizList(p); }}>→</button>
            </div>
          </>
        )}
      </div>
      ) : view === "stat" ? (
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
        <StockTab />
      </div>
      ) : view === "receipt" ? (
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
        {receiptSel ? (
          <>
            <button className="btn btn-light" onClick={() => setReceiptSel(null)}>← {t("К списку приходов","До списку приходів")}</button>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10, marginTop: 12 }}>
              <div>
                <h3 style={{ margin: "0 0 4px" }}>{t("Приходная накладная","Прибуткова накладна")} {receiptSel.number || ("#" + receiptSel.id)} <button className="btn btn-light" style={{ padding: "2px 8px" }} title={t("Скопировать ссылку","Скопіювати посилання")} onClick={() => { navigator.clipboard?.writeText(window.location.origin + "/warehouse?doc=" + receiptSel.id); alert(t("Ссылка скопирована ✓","Посилання скопійовано ✓")); }}>🔗</button></h3>
                <div className="muted" style={{ fontSize: 12 }}>{(receiptSel.created_at || "").slice(0, 10)}{receiptSel.comment ? " · " + receiptSel.comment : ""}</div>
                {(receiptSel.supplier_name || receiptSel.supplier_invoice) && (
                  <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                    {receiptSel.supplier_name ? t("Поставщик: ","Постачальник: ") + receiptSel.supplier_name : ""}
                    {receiptSel.supplier_invoice ? " · " + t("накладная №","накладна №") + receiptSel.supplier_invoice : ""}
                  </div>
                )}
                {receiptSel.source_invoice_doc ? (
                  <button className="btn btn-light" style={{ marginTop: 8, fontSize: 12.5, fontWeight: 700 }} title={t("Открыть исходную накладную поставщика (файл/письмо)","Відкрити вихідну накладну постачальника (файл/лист)")} onClick={async () => { try { const u = await (api as any).blobUrl(`/api/integrations/incoming-docs/${receiptSel.source_invoice_doc}/view/`); window.open(u, "_blank"); } catch { alert(t("Не удалось открыть накладную","Не вдалося відкрити накладну")); } }}><Icon n="📄" size={13} /> {t("Открыть накладную-источник","Відкрити накладну-джерело")}</button>
                ) : null}
              </div>
              <span style={{ padding: "3px 10px", borderRadius: 6, fontSize: 13, fontWeight: 700, background: receiptSel.posted ? "#dcfce7" : "#fef3c7", color: receiptSel.posted ? "#166534" : "#92400e" }}>{receiptSel.posted ? t("Проведён","Проведено") : t("Черновик","Чернетка")}</span>
            </div>
            <table style={{ width: "100%", marginTop: 14 }}>
              <thead><tr><th>{t("Товар","Товар")}</th><th style={{ textAlign: "right" }}>{t("Кол-во","К-сть")}</th><th style={{ textAlign: "right" }}>{t("Цена","Ціна")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th></tr></thead>
              <tbody>{(receiptSel.items || []).map((it: any) => (
                <tr key={it.id}><td>{it.product_name}</td><td style={{ textAlign: "right" }}>{Math.abs(Number(it.quantity))}</td><td style={{ textAlign: "right" }}>{Number(it.price).toLocaleString("uk-UA")} ₴</td><td style={{ textAlign: "right" }}>{(Math.abs(Number(it.quantity)) * Number(it.price)).toLocaleString("uk-UA")} ₴</td></tr>
              ))}</tbody>
            </table>
          </>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <h3 style={{ margin: 0 }}>{t("Приходные накладные","Прибуткові накладні")}</h3>
              {canEdit && <div style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-primary" onClick={() => setReceiptFor({})} title={t("Приход с поставщиком, несколькими позициями и оплатой/долгом","Прихід з постачальником, кількома позиціями і оплатою/боргом")}><Icon n="📥" size={14} /> {t("Приход","Прихід")}</button>
                <input ref={receiptFileRef} type="file" accept=".csv,text/csv,text/plain" style={{ display: "none" }} onChange={importReceipt} />
                <button className="btn btn-light" onClick={() => receiptFileRef.current?.click()} title={t("Приход из файла: артикул, кол-во, цена","Прихід з файлу: артикул, к-сть, ціна")}><Icon n="📄" size={14} /> {t("Приход файлом","Прихід файлом")}</button>
              </div>}
            </div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("Все поступления товара на склад по датам. Кликните на строку — откроется документ с позициями.","Усі надходження товару на склад по датах. Клікніть на рядок — відкриється документ з позиціями.")}</div>
            {receiptBusy ? <div className="muted" style={{ padding: 16 }}>{t("Загрузка…","Завантаження…")}</div> :
             receiptDocs.length === 0 ? <div className="muted" style={{ padding: 16 }}>{t("Пока нет приходов.","Поки немає приходів.")}</div> :
            <table style={{ width: "100%" }}>
              <thead><tr><th>№</th><th>{t("Дата","Дата")}</th><th>{t("Комментарий","Коментар")}</th><th style={{ textAlign: "right" }}>{t("Позиций","Позицій")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th><th style={{ textAlign: "center" }}>{t("Статус","Статус")}</th></tr></thead>
              <tbody>{receiptDocs.map((d: any) => (
                <tr key={d.id} onClick={() => setReceiptSel(d)} style={{ cursor: "pointer" }} title={t("Открыть документ","Відкрити документ")}>
                  <td><b>{d.number || ("#" + d.id)}</b></td>
                  <td className="muted">{(d.created_at || "").slice(0, 10)}</td>
                  <td className="muted">{d.comment || "—"}</td>
                  <td style={{ textAlign: "right" }}>{(d.items || []).length}</td>
                  <td style={{ textAlign: "right" }}>{Number(d.total || 0).toLocaleString("uk-UA")} ₴</td>
                  <td style={{ textAlign: "center" }}><span style={{ padding: "2px 8px", borderRadius: 6, fontSize: 12, fontWeight: 600, background: d.posted ? "#dcfce7" : "#fef3c7", color: d.posted ? "#166534" : "#92400e" }}>{d.posted ? t("Проведён","Проведено") : t("Черновик","Чернетка")}</span></td>
                </tr>
              ))}</tbody>
            </table>}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
              <span className="muted" style={{ fontSize: 12 }}>{t("Строк","Рядків")}:</span>
              {[25, 50, 100].map((n) => <button key={n} className={"btn" + (docPS.receipt === n ? " btn-primary" : " btn-light")} style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => { setDocPS((x) => ({ ...x, receipt: n })); setDocPage((x) => ({ ...x, receipt: 1 })); openReceiptList(1, n); }}>{n}</button>)}
              <div style={{ flex: 1 }} />
              <button className="btn btn-light" disabled={docPage.receipt <= 1} onClick={() => { const p = docPage.receipt - 1; setDocPage((x) => ({ ...x, receipt: p })); openReceiptList(p); }}>←</button>
              <span style={{ fontSize: 12 }}>{docPage.receipt} / {Math.max(1, Math.ceil(docCount.receipt / docPS.receipt))}</span>
              <button className="btn btn-light" disabled={docPage.receipt >= Math.ceil(docCount.receipt / docPS.receipt)} onClick={() => { const p = docPage.receipt + 1; setDocPage((x) => ({ ...x, receipt: p })); openReceiptList(p); }}>→</button>
            </div>
          </>
        )}
      </div>
      ) : view === "goods" ? (
      <div style={{ display: "grid", gridTemplateColumns: `${catW}px 8px 1fr`, gap: 6, alignItems: "start" }}>

      {/* ─── [5] ДЕРЕВО КАТЕГОРИЙ ─────────────────────────────────────────── */}
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 8, position: "sticky", top: 8, maxHeight: "calc(100vh - 90px)", overflowY: "auto" }}>
        <div onClick={() => pick(null)} style={{ padding: "7px 9px", borderRadius: 6, cursor: "pointer", fontWeight: 600, background: cat === null ? "#eff6ff" : "", color: cat === null ? "#1d4ed8" : "#1e293b" }}>
          <Icon n="📦" size={15} /> {t("Все товары","Всі товари")} <span className="muted" style={{ fontWeight: 400 }}>({count})</span>
        </div>
        {tree.roots.map((r) => (
          <div key={r.id}>
            <div onClick={() => pick(r.id)} className="cat-row" style={{ padding: "6px 9px", borderRadius: 6, cursor: "pointer", fontSize: 13, background: cat === r.id ? "#eff6ff" : "", color: cat === r.id ? "#1d4ed8" : "#334155", display: "flex", alignItems: "center" }}>
              <span style={{ flex: 1 }}><Icon n="📁" size={14} /> {r.name} <span className="muted">({r.products_count})</span></span>
              {canEdit && <span onClick={(e) => delCategory(r, e)} title={t("Удалить папку со всеми подпапками и товарами","Видалити папку з усіма підпапками і товарами")} style={{ color: "#dc2626", fontSize: 12, padding: "0 4px", opacity: 0.55 }}>🗑</span>}
            </div>
            {tree.childrenOf(r.id).map((ch) => (
              <div key={ch.id} onClick={() => pick(ch.id)} style={{ padding: "5px 9px 5px 24px", borderRadius: 6, cursor: "pointer", fontSize: 12.5, background: cat === ch.id ? "#eff6ff" : "", color: cat === ch.id ? "#1d4ed8" : "#475569", display: "flex", alignItems: "center" }}>
                <span style={{ flex: 1 }}>{ch.name} <span className="muted">({ch.products_count})</span></span>
                {canEdit && <span onClick={(e) => delCategory(ch, e)} title={t("Удалить подпапку с товарами","Видалити підпапку з товарами")} style={{ color: "#dc2626", fontSize: 12, padding: "0 4px", opacity: 0.55 }}>🗑</span>}
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* «потягни» — зміна ширини панелі категорій */}
      <div onMouseDown={startResize} title={t("Потяни, чтобы изменить ширину","Потягни, щоб змінити ширину")} style={{ cursor: "col-resize", alignSelf: "stretch", minHeight: "60vh", display: "flex", justifyContent: "center", position: "sticky", top: 8 }}>
        <div style={{ width: 3, borderRadius: 3, background: "#e2e8f0" }} />
      </div>

      {/* ─── [6] ТУЛБАР + ТАБЛИЦА + ПАГИНАЦИЯ ─────────────────────────────── */}
      <div>
        <div className="toolbar" style={{ borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 10, background: "#fff", display: "flex", gap: 8, alignItems: "center", padding: 8, flexWrap: "wrap" }}>
          {canEdit && <button className="btn btn-primary" onClick={() => setNewOpen(true)}><Icon n="➕" size={15} /> {t("Создать товар","Створити товар")}</button>}
          <button className={"btn" + ((fltActive !== "active" || fltStock) ? " btn-primary" : " btn-light")} onClick={() => setFltOpen(!fltOpen)} title={t("Фильтр по номенклатуре","Фільтр за номенклатурою")}><Icon n="🔽" size={15} /> {t("Фильтр","Фільтр")}</button>
          <button className="btn btn-light" onClick={exportCsv} title={t("Выгрузить номенклатуру в CSV (Excel)","Вивантажити номенклатуру в CSV (Excel)")}><Icon n="⬇️" size={15} /> {t("Экспорт","Експорт")}</button>
          {canEdit && <>
          <input ref={nomFileRef} type="file" accept=".csv,text/csv,text/plain" style={{ display: "none" }} onChange={importNom} />
          <button className="btn btn-light" onClick={() => nomFileRef.current?.click()} title={t("Загрузить номенклатуру из CSV (остатки не меняет)","Завантажити номенклатуру з CSV (залишки не змінює)")}><Icon n="⬆️" size={15} /> {t("Импорт","Імпорт")}</button>
          </>}
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("🔍 Поиск товара / артикула…","🔍 Пошук товару / артикулу…")} style={{ flex: 1, minWidth: 160, height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 12px", fontSize: 13 }} />
          <span className="muted">{t("Найдено","Знайдено")}: <b style={{ color: "#1e293b" }}>{count.toLocaleString("ru")}</b></span>
        </div>

        {canEdit && selIds.size > 0 && (
          <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, padding: "8px 12px", marginBottom: 10, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <b style={{ fontSize: 13 }}>{t("Выбрано","Вибрано")}: {selIds.size}</b>
            <span className="muted" style={{ fontSize: 13 }}>{t("Изменить единицу измерения","Змінити одиницю виміру")}:</span>
            <select value={bulkUnit} onChange={(e) => setBulkUnit(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }}>
              <option value="">{t("— выбери —","— обери —")}</option>
              {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
            <button className="btn btn-primary" disabled={!bulkUnit} onClick={applyBulkUnit} style={{ padding: "4px 14px" }}>{t("Применить","Застосувати")}</button>
            <button className="btn btn-light" onClick={() => setSelIds(new Set())} style={{ padding: "4px 10px" }}>{t("Снять выбор","Зняти вибір")}</button>
          </div>
        )}
        {fltOpen && (
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 12, marginBottom: 10, display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
            <label style={{ fontSize: 13 }}>{t("Активность","Активність")}: <select value={fltActive} onChange={(e) => { setFltActive(e.target.value as any); setPage(1); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6, marginLeft: 4 }}>
              <option value="active">{t("Только активные","Тільки активні")}</option>
              <option value="all">{t("Все (вкл. скрытые)","Всі (разом з прихованими)")}</option>
              <option value="hidden">{t("Только скрытые","Тільки приховані")}</option>
            </select></label>
            <label style={{ fontSize: 13 }}>{t("Остаток","Залишок")}: <select value={fltStock} onChange={(e) => { setFltStock(e.target.value as any); setPage(1); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6, marginLeft: 4 }}>
              <option value="">{t("Любой","Будь-який")}</option>
              <option value="in">{t("В наличии (> 0)","В наявності (> 0)")}</option>
              <option value="zero">{t("Нулевой / нет","Нульовий / немає")}</option>
            </select></label>
            <button className="btn btn-light" style={{ padding: "3px 10px" }} onClick={() => { setFltActive("active"); setFltStock(""); setPage(1); }}>{t("Сбросить","Скинути")}</button>
          </div>
        )}
        <div className="tablewrap" style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8 }}>
          <table style={{ width: "100%" }}>
            <thead><tr>{canEdit && <th style={{ width: 30 }}><input type="checkbox" checked={products.length > 0 && selIds.size === products.length} onChange={toggleSelAll} title={t("Выбрать все на странице","Вибрати всі на сторінці")} /></th>}{sortTh("name", t("Товар","Товар"))}{sortTh("sku", t("Артикул","Артикул"))}<th>{t("Категория","Категорія")}</th>{sortTh("price", t("Цена","Ціна"))}{showCost && sortTh("cost", t("Закупівля","Закупівля"))}<th>{t("Ед.","Од.")}</th><th>{t("Остаток","Залишок")}</th>{canEdit && <th></th>}</tr></thead>
            <tbody>
              {loading && <tr><td colSpan={6 + (showCost ? 1 : 0) + (canEdit ? 2 : 0)} className="muted" style={{ padding: 16 }}>{t("Загрузка…","Завантаження…")}</td></tr>}
              {!loading && products.length === 0 && <tr><td colSpan={6 + (showCost ? 1 : 0) + (canEdit ? 2 : 0)} className="muted" style={{ padding: 16 }}>{t("Товаров не найдено","Товарів не знайдено")}</td></tr>}
              {!loading && products.map((p) => (
                <tr key={p.id}>
                  {canEdit && <td style={{ textAlign: "center" }}><input type="checkbox" checked={selIds.has(p.id)} onChange={() => toggleSel(p.id)} onClick={(e) => e.stopPropagation()} /></td>}
                  <td><span onClick={() => openCard(p)} style={{ fontWeight: 500, color: "#1d4ed8", cursor: "pointer" }}>{(p as any).is_bundle && <span title="Набір (комплект)">🧩 </span>}{p.name}</span></td>
                  <td className="muted">{p.sku}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{p.category_name || "—"}</td>
                  <td>{Number(p.price).toLocaleString("ru")} {p.currency || "грн"}</td>
                  {showCost && <td><EditCost p={p} onSaved={(v) => setProducts((ps) => ps.map((x) => (x.id === p.id ? { ...x, cost: String(v) } : x)))} /></td>}
                  <td>{p.unit}</td>
                  <td>{(p as any).track_stock === false ? <span className="muted" title={t("Без количественного учёта","Без кількісного обліку")}>—</span> : <span style={{ color: Number(p.stock) <= 0 ? "#dc2626" : Number(p.stock) < 100 ? "#d97706" : "#16a34a", fontWeight: 600 }}>{Number(p.stock).toLocaleString("ru")}</span>}</td>
                  {canEdit && <td style={{ textAlign: "center" }}><button onClick={() => delProduct(p)} title={t("Удалить / скрыть товар","Видалити / приховати товар")} style={{ border: "none", background: "transparent", cursor: "pointer", color: "#dc2626", fontSize: 14 }}>🗑</button></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: 13 }}>{t("На странице","На сторінці")}:</span>
          {PAGE_SIZES.map((s) => (
            <button key={s} onClick={() => { setPageSize(s); setPage(1); }} style={{ fontSize: 13, padding: "4px 11px", borderRadius: 7, cursor: "pointer", border: "1px solid " + (pageSize === s ? "var(--brand)" : "#cbd5e1"), background: pageSize === s ? "var(--brand)" : "#fff", color: pageSize === s ? "#fff" : "#475569" }}>{s}</button>
          ))}
          <div className="spacer" style={{ flex: 1 }} />
          <button className="btn btn-light" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>{t("← Назад","← Назад")}</button>
          <span style={{ fontSize: 13 }}>{t("Стр.","Стор.")} <b>{page}</b> {t("из","з")} <b>{totalPages}</b></span>
          <button className="btn btn-light" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>{t("Вперёд →","Вперед →")}</button>
        </div>
      </div>
      </div>
      ) : null}

      {/* ─── [6c] МОДАЛКА СОЗДАНИЯ ТОВАРА ─────────────────────────────────── */}
      {newOpen && (
        <div onClick={() => setNewOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 24, width: 440, maxWidth: "94vw" }}>
            <h3 style={{ marginTop: 0 }}>{t("Новый товар","Новий товар")}</h3>
            <label className="label">{t("Название","Назва")}</label>
            <input value={newP.name} onChange={(e) => setNewP({ ...newP, name: e.target.value })} style={{ width: "100%", height: 38, marginBottom: 10, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} autoFocus />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <label style={{ fontSize: 12 }} className="muted">{t("Артикул","Артикул")}<input value={newP.sku} onChange={(e) => setNewP({ ...newP, sku: e.target.value })} style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", marginTop: 2 }} /></label>
              <label style={{ fontSize: 12 }} className="muted">{t("Ед. изм.","Од. вим.")}<input value={newP.unit} onChange={(e) => setNewP({ ...newP, unit: e.target.value })} style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", marginTop: 2 }} /></label>
              <label style={{ fontSize: 12 }} className="muted">{t("Розничная цена","Роздрібна ціна")}<input type="number" value={newP.price} onChange={(e) => setNewP({ ...newP, price: e.target.value })} style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", marginTop: 2 }} /></label>
              <label style={{ fontSize: 12 }} className="muted">{t("Закупочная","Закупівельна")}<input type="number" value={newP.cost} onChange={(e) => setNewP({ ...newP, cost: e.target.value })} style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", marginTop: 2 }} /></label>
            </div>
            <label style={{ fontSize: 12, display: "block", marginTop: 10 }} className="muted">{t("Раздел","Розділ")}<select value={newP.category} onChange={(e) => setNewP({ ...newP, category: Number(e.target.value) })} style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", marginTop: 2 }}>
              <option value={0}>{t("— без раздела —","— без розділу —")}</option>
              {cats.map((c) => <option key={c.id} value={c.id}>{c.parent ? "\u00a0\u00a0\u00a0" : ""}{c.name}</option>)}
            </select></label>
            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setNewOpen(false)}>{t("Отмена","Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={createProduct}>{t("Создать","Створити")}</button>
            </div>
          </div>
        </div>
      )}

      {/* ─── [7] МОДАЛКА ПРИХОД/РАСХОД ────────────────────────────────────── */}
      {modal && (
        <div onClick={() => setModal(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 24, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>{modal === "in" ? t("Приходная накладная","Прибуткова накладна") : t("Списание товара (брак / порча / выкраска)","Списання товару (брак / псування / викраска)")}</h3>
            <label className="label">{t("Товар","Товар")}</label>
            <select value={form.product} onChange={(e) => setForm({ ...form, product: Number(e.target.value) })} style={{ width: "100%", height: 38, marginBottom: 10, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }}>
              <option value={0}>{t("— выбери товар (из текущей страницы) —","— обери товар (з поточної сторінки) —")}</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name} ({t("остаток","залишок")} {p.stock})</option>)}
            </select>
            <label className="label">{t("Количество","Кількість")}</label>
            <input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} style={{ width: "100%", height: 38, marginBottom: 10, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            <label className="label">{t("Цена за ед.","Ціна за од.")}</label>
            <input type="number" value={form.price} onChange={(e) => setForm({ ...form, price: Number(e.target.value) })} style={{ width: "100%", height: 38, marginBottom: 16, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setModal(null)}>{t("Отмена","Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={saveDoc}>{t("Провести","Провести")}</button>
            </div>
          </div>
        </div>
      )}

      {/* ─── [8] КАРТОЧКА ТОВАРА ──────────────────────────────────────────── */}
      {card && (
        <div onClick={() => setCard(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", justifyContent: "flex-end", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: "min(640px,94vw)", height: "100%", background: "#fff", overflow: "auto", padding: "18px 22px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
              {cardEdit
                ? <input value={cardEdit.name} onChange={(e) => setCardEdit({ ...cardEdit, name: e.target.value })} style={{ flex: 1, fontSize: 17, fontWeight: 700, border: "1px solid #cbd5e1", borderRadius: 8, padding: "6px 10px" }} />
                : <h3 style={{ margin: 0 }}>{card.name} {card.is_active === false && <span style={{ fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 6, background: "#fee2e2", color: "#b91c1c", verticalAlign: "middle" }}>{t("скрыт","приховано")}</span>}</h3>}
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                <button className="btn btn-light" title={t("Скопировать ссылку на товар","Скопіювати посилання на товар")} onClick={() => { navigator.clipboard?.writeText(window.location.origin + "/warehouse?product=" + card.id); alert(t("Ссылка скопирована ✓","Посилання скопійовано ✓")); }}><Icon n="🔗" size={14} /></button>
                {canEdit && (cardEdit
                  ? <><button className="btn btn-primary" onClick={saveCard}>{t("Сохранить","Зберегти")}</button><button className="btn btn-light" onClick={() => setCardEdit(null)}>✕</button></>
                  : <button className="btn btn-light" onClick={() => setCardEdit({ name: card.name, sku: card.sku, unit: card.unit, price: card.price, cost: card.cost, cost_pct: card.cost_pct || 0, min_price: card.min_price || 0, category: card.category || 0, description: card.description || "", is_active: card.is_active !== false, track_stock: card.track_stock !== false, is_drop: (card as any).is_drop === true,
                      shop_enabled: !!card.shop_enabled, shop_category_path: card.shop_category_path?.length ? card.shop_category_path : (card.category === 59 ? ["Пробники"] : []), shop_group_key: card.shop_group_key || "", shop_parent_name: card.shop_parent_name || "", shop_slug: card.shop_slug || "", shop_short_description: card.shop_short_description || "", shop_full_description: card.shop_full_description || "", shop_effect: card.shop_effect || "", shop_rooms: card.shop_rooms || [], shop_beginner: !!card.shop_beginner, shop_video_url: card.shop_video_url || "", shop_instruction_url: card.shop_instruction_url || "", shop_sort: card.shop_sort || 0, shop_variant_type: card.shop_variant_type || (card.category === 59 ? "sample" : "product"), shop_has_board: card.shop_has_board ?? null, shop_is_tinted: card.shop_is_tinted ?? null, shop_variant_order: card.shop_variant_order || (card.category === 59 ? 0 : 1), shop_variant_name: card.shop_variant_name || (card.category === 59 ? "" : t("Основной товар", "Основний товар")), shop_contents: card.shop_contents || "", seo_title: card.seo_title || "", seo_description: card.seo_description || "", seo_h1: card.seo_h1 || "", seo_index: !!card.seo_index })}><Icon n="✏️" size={14} /> {t("Изменить","Змінити")}</button>)}
                <button className="btn btn-light" onClick={() => setCard(null)}>✕</button>
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, margin: "14px 0 10px", borderBottom: "1px solid #e2e8f0", paddingBottom: 8 }}>
              {([['main', t('Карточка','Картка')], ['shop', t('На сайте','На сайті')], ['media', t('Фото','Фото')], ['sync', t('Проверка','Перевірка')]] as const).map(([key, label]) =>
                <button key={key} className={cardTab === key ? "btn btn-primary" : "btn btn-light"} onClick={() => setCardTab(key)}>{label}</button>)}
            </div>
            {cardTab === "shop" && <div className="panel" style={{ margin: "0 0 14px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "space-between", alignItems: "center" }}><b>🛒 {t("Карточка интернет-магазина","Картка інтернет-магазину")}</b><span style={{ color: card.shop_status === 'published' ? '#15803d' : card.shop_status === 'error' ? '#b91c1c' : '#a16207' }}>{card.shop_status || 'draft'}</span></div>
              {cardEdit ? <>
                <label style={{fontSize:13,gridColumn:'1 / -1',padding:'10px 12px',borderRadius:9,background:cardEdit.shop_enabled?'#dcfce7':'#f1f5f9'}}><input type="checkbox" checked={cardEdit.shop_enabled} onChange={e => setCardEdit({...cardEdit,shop_enabled:e.target.checked})}/> <b>{t('Отображать в интернет-магазине','Показувати в інтернет-магазині')}</b><div className="muted" style={{fontSize:11,marginLeft:20}}>{t('После включения товар появится в разделе магазина и будет отправлен на сайт после проверки.','Після увімкнення товар з’явиться в розділі магазину й буде надісланий на сайт після перевірки.')}</div></label>
                <label className="muted" style={{ fontSize: 12, gridColumn:'1 / -1' }}>{t("Категория → подкатегория на сайте","Категорія → підкатегорія на сайті")}<input list="shop-category-paths" value={categoryPathText(cardEdit.shop_category_path)} onChange={e => setCardEdit({...cardEdit, shop_category_path:parseCategoryPath(e.target.value)})} placeholder={t("Например: Декоративные покрытия → Шёлк","Наприклад: Декоративні покриття → Шовк")} style={{width:'100%',height:34}} /><datalist id="shop-category-paths">{SHOP_CATEGORY_SUGGESTIONS.map(path=><option key={path} value={path}/>)}</datalist><small>{t('Можно указать любую глубину через стрелку →','Можна вказати будь-яку глибину через стрілку →')}</small></label>
                <label className="muted" style={{ fontSize: 12 }}>{t("Тип карточки","Тип картки")}<select value={cardEdit.shop_variant_type} onChange={e => setCardEdit({...cardEdit,shop_variant_type:e.target.value,shop_variant_order:e.target.value==='sample'?cardEdit.shop_variant_order:1,shop_variant_name:e.target.value==='sample'?cardEdit.shop_variant_name:t('Основной товар','Основний товар')})} style={{width:'100%',height:34}}><option value="product">{t('Обычный товар','Звичайний товар')}</option><option value="sample">{t('Пробник — 4 комплектации','Пробник — 4 комплектації')}</option></select></label>
                <label className="muted" style={{ fontSize: 12 }}>{t("Общее название покрытия","Спільна назва покриття")}<input value={cardEdit.shop_parent_name} onChange={e => setCardEdit({...cardEdit, shop_parent_name:e.target.value})} style={{width:'100%',height:34}} /></label>
                <label className="muted" style={{ fontSize: 12 }}>URL<input value={cardEdit.shop_slug} onChange={e => setCardEdit({...cardEdit, shop_slug:e.target.value})} style={{width:'100%',height:34}} /></label>
                <label className="muted" style={{ fontSize: 12 }}>{t("Группа четырёх вариантов","Група чотирьох варіантів")}<input value={cardEdit.shop_group_key} onChange={e => setCardEdit({...cardEdit, shop_group_key:e.target.value})} style={{width:'100%',height:34}} /></label>
                {cardEdit.shop_variant_type === 'sample' && <><label className="muted" style={{ fontSize: 12 }}>{t("Название комплектации","Назва комплектації")}<input value={cardEdit.shop_variant_name} onChange={e => setCardEdit({...cardEdit, shop_variant_name:e.target.value})} style={{width:'100%',height:34}} /></label>
                <label className="muted" style={{ fontSize: 12 }}>{t("Порядок 1–4","Порядок 1–4")}<input type="number" min="1" max="4" value={cardEdit.shop_variant_order} onChange={e => setCardEdit({...cardEdit, shop_variant_order:e.target.value})} style={{width:'100%',height:34}} /></label>
                <label className="muted" style={{ fontSize: 12 }}>{t("Дощечка","Дощечка")}<select value={cardEdit.shop_has_board === null ? '' : String(cardEdit.shop_has_board)} onChange={e => setCardEdit({...cardEdit, shop_has_board:e.target.value === '' ? null : e.target.value === 'true'})} style={{width:'100%',height:34}}><option value="">—</option><option value="false">{t('Без дощечки','Без дощечки')}</option><option value="true">{t('С дощечкой','З дощечкою')}</option></select></label>
                <label className="muted" style={{ fontSize: 12 }}>{t("Тонировка","Тонування")}<select value={cardEdit.shop_is_tinted === null ? '' : String(cardEdit.shop_is_tinted)} onChange={e => setCardEdit({...cardEdit, shop_is_tinted:e.target.value === '' ? null : e.target.value === 'true'})} style={{width:'100%',height:34}}><option value="">—</option><option value="false">{t('Без тонировки','Без тонування')}</option><option value="true">{t('С тонировкой','З тонуванням')}</option></select></label>
                </>}
                <label className="muted" style={{ fontSize: 12 }}>{t("Эффект","Ефект")}<input value={cardEdit.shop_effect} onChange={e => setCardEdit({...cardEdit, shop_effect:e.target.value})} style={{width:'100%',height:34}} /></label>
                <label className="muted" style={{ fontSize: 12, gridColumn:'1 / -1' }}>{t("Коротко и простыми словами","Коротко і простими словами")}<textarea rows={2} value={cardEdit.shop_short_description} onChange={e => setCardEdit({...cardEdit, shop_short_description:e.target.value})} style={{width:'100%'}} /></label>
                <label className="muted" style={{ fontSize: 12, gridColumn:'1 / -1' }}>{t("Полное описание","Повний опис")}<textarea rows={4} value={cardEdit.shop_full_description} onChange={e => setCardEdit({...cardEdit, shop_full_description:e.target.value})} style={{width:'100%'}} /></label>
                <label style={{fontSize:12}}><input type="checkbox" checked={cardEdit.shop_beginner} onChange={e => setCardEdit({...cardEdit,shop_beginner:e.target.checked})}/> {t('Подходит новичку','Підходить новачку')}</label>
              </> : <>
                <div style={{gridColumn:'1 / -1'}}><span className="muted">{t('Показывать в магазине','Показувати в магазині')}</span><br/><b style={{color:card.shop_enabled?'#15803d':'#64748b'}}>{card.shop_enabled?t('Да','Так'):t('Нет','Ні')}</b></div>
                <div style={{gridColumn:'1 / -1'}}><span className="muted">{t('Категория на сайте','Категорія на сайті')}</span><br/><b>{categoryPathText(card.shop_category_path?.length ? card.shop_category_path : (card.category === 59 ? ['Пробники'] : [])) || '—'}</b></div>
                <div><span className="muted">{t('Покрытие','Покриття')}</span><br/><b>{card.shop_parent_name || '—'}</b></div><div><span className="muted">URL</span><br/>{card.shop_slug || '—'}</div>
                <div><span className="muted">{t('Комплектация','Комплектація')}</span><br/>{card.shop_variant_name || '—'}</div><div><span className="muted">{t('Группа','Група')}</span><br/>{card.shop_group_key || '—'}</div>
                <div style={{gridColumn:'1 / -1'}}>{card.shop_short_description || t('Описание ещё не заполнено','Опис ще не заповнений')}</div>
                <div style={{gridColumn:'1 / -1'}}><b>{t('Варианты в этой группе','Варіанти у цій групі')}: {card.shop_group_variants?.length || 0}/4</b>{card.shop_group_variants?.map((v:any)=><div key={v.id}>#{v.id} · {v.sku} · {v.shop_variant_name || v.name} · {v.shop_status}</div>)}</div>
              </>}
            </div>}
            {cardTab === "media" && <div className="panel" style={{margin:'0 0 14px'}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><b>📷 {t('Фотографии этой комплектации','Фотографії цієї комплектації')}</b>{canEdit && <><input ref={shopImageRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={e=>{uploadShopImage(e.target.files?.[0]); e.target.value='';}}/><button className="btn btn-primary" onClick={()=>shopImageRef.current?.click()}>{t('Добавить фото','Додати фото')}</button></>}</div>
              <div className="muted" style={{fontSize:12,margin:'6px 0 10px'}}>{t('Новое фото сначала черновик. Проверьте его и нажмите «Утвердить».','Нове фото спочатку чернетка. Перевірте його й натисніть «Затвердити».')}</div>
              <div style={{display:'grid',gridTemplateColumns:'repeat(2,1fr)',gap:10}}>{(card.images||[]).map(im=><div key={im.id} style={{border:'1px solid #e2e8f0',borderRadius:8,padding:8}}><img src={im.url} alt={im.alt_text||''} style={{width:'100%',height:150,objectFit:'cover',borderRadius:6}}/><div style={{fontSize:12,marginTop:6}}>{im.is_approved?'✅ '+t('Утверждено','Затверджено'):'⏳ '+t('Не утверждено','Не затверджено')} {im.is_primary?' · ⭐ '+t('Главное','Головне'):''}</div>{canEdit&&<div style={{display:'flex',gap:5,marginTop:6,flexWrap:'wrap'}}><button className="btn btn-light" onClick={()=>patchShopImage(im.id,{is_approved:!im.is_approved})}>{im.is_approved?t('Снять утверждение','Зняти затвердження'):t('Утвердить','Затвердити')}</button><button className="btn btn-light" onClick={()=>patchShopImage(im.id,{is_primary:true})}>⭐</button><button className="btn btn-light" onClick={()=>deleteShopImage(im.id)}>🗑</button></div>}</div>)}</div>
            </div>}
            {cardTab === "sync" && <div className="panel" style={{margin:'0 0 14px'}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><b>🔄 {t('Проверка и передача на сайт','Перевірка й передача на сайт')}</b>{canEdit&&<button className="btn btn-primary" onClick={queueShopSync}>{t('Проверить и отправить','Перевірити й надіслати')}</button>}</div>
              <div style={{marginTop:8}}>{(card.shop_validation_errors||[]).length===0?<span style={{color:'#15803d'}}>✅ {t('Карточка заполнена','Картку заповнено')}</span>:<><b style={{color:'#b91c1c'}}>Не готово:</b><ul>{card.shop_validation_errors?.map(x=><li key={x}>{x}</li>)}</ul></>}</div>
              {card.shop_sync_error&&<div style={{color:'#b91c1c'}}>Ошибка связи: {card.shop_sync_error}</div>}
              <div className="muted" style={{fontSize:12}}>{t('Последняя передача','Остання передача')}: {card.shop_last_sync_at?new Date(card.shop_last_sync_at).toLocaleString():'—'}</div>
              {card.shop_remote_url&&<a href={card.shop_remote_url} target="_blank" rel="noreferrer">{t('Открыть карточку на сайте','Відкрити картку на сайті')} ↗</a>}
              <div style={{marginTop:10}}>{card.shop_sync_history?.map((e:any)=><div key={e.event_uuid} style={{fontSize:12,borderTop:'1px solid #e2e8f0',padding:'5px 0'}}>{e.status} · {e.action} · {new Date(e.created_at).toLocaleString()} {e.last_error&&<span style={{color:'#b91c1c'}}>· {e.last_error}</span>}</div>)}</div>
            </div>}
            {cardEdit ? (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, margin: "12px 0" }}>
                <label style={{ fontSize: 12 }} className="muted">{t("Артикул","Артикул")}<input value={cardEdit.sku} onChange={(e) => setCardEdit({ ...cardEdit, sku: e.target.value })} style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", marginTop: 2 }} /></label>
                <label style={{ fontSize: 12 }} className="muted">{t("Раздел (перенести в…)","Розділ (перенести в…)")}<select value={cardEdit.category} onChange={(e) => setCardEdit({ ...cardEdit, category: Number(e.target.value) })} style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, marginTop: 2 }}>
                  <option value={0}>{t("— без раздела —","— без розділу —")}</option>
                  {cats.map((c) => <option key={c.id} value={c.id}>{c.parent ? "\u00a0\u00a0\u00a0" : ""}{c.name}</option>)}
                </select></label>
                <label style={{ fontSize: 12 }} className="muted">{t("Розничная цена","Роздрібна ціна")}<input type="number" value={cardEdit.price} onChange={(e) => setCardEdit({ ...cardEdit, price: e.target.value })} style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", marginTop: 2 }} /></label>
                {showCost && <label style={{ fontSize: 12 }} className="muted">{t("Закупочная","Закупівельна")}<input type="number" value={cardEdit.cost} onChange={(e) => setCardEdit({ ...cardEdit, cost: e.target.value })} style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", marginTop: 2 }} /></label>}
                {showCost && <label style={{ fontSize: 12 }} className="muted" title={t("Для услуг/работ: себестоимость = цена × этот %. Пример монтаж: мастеру 80% → впиши 80. Тогда при любой цене маржа держит %. 0 = использовать фикс. закупочную.","Для послуг/робіт: собівартість = ціна × цей %. Приклад монтаж: майстру 80% → впиши 80. Тоді при будь-якій ціні маржа тримає %. 0 = фікс. закупівельна.")}>{t("Себест., % от цены","Собівартість, % від ціни")}<input type="number" value={cardEdit.cost_pct} onChange={(e) => setCardEdit({ ...cardEdit, cost_pct: e.target.value })} placeholder="0" style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", marginTop: 2 }} /></label>}
                <label style={{ fontSize: 12 }} className="muted" title={t("Минимум за строку в сделке: если цена×кол-во меньше — берётся этот минимум. Пример: сверление 17/см, но минимум 1500. 0 = без минимума.","Мінімум за рядок у сделці: якщо ціна×кількість менша — береться цей мінімум. Приклад: сверління 17/см, але мінімум 1500. 0 = без мінімуму.")}>{t("Минималка за позицию, ₴","Мінімалка за позицію, ₴")}<input type="number" value={cardEdit.min_price} onChange={(e) => setCardEdit({ ...cardEdit, min_price: e.target.value })} placeholder="0" style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", marginTop: 2 }} /></label>
                <label style={{ fontSize: 12 }} className="muted">{t("Ед. изм.","Од. вим.")}<input value={cardEdit.unit} onChange={(e) => setCardEdit({ ...cardEdit, unit: e.target.value })} style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", marginTop: 2 }} /></label>
                <label style={{ fontSize: 12, display: "flex", alignItems: "flex-end", gap: 6, paddingBottom: 8 }}><input type="checkbox" checked={cardEdit.is_active} onChange={(e) => setCardEdit({ ...cardEdit, is_active: e.target.checked })} /> {t("Активен (виден в каталоге)","Активний (видно у каталозі)")}</label>
                <label style={{ fontSize: 12, display: "flex", alignItems: "flex-end", gap: 6, paddingBottom: 8 }} title={t("Выключи для услуг/работ — не списывается со склада, остаток не считается","Вимкни для послуг/робіт — не списується зі складу, залишок не рахується")}><input type="checkbox" checked={cardEdit.track_stock} onChange={(e) => setCardEdit({ ...cardEdit, track_stock: e.target.checked })} /> {t("Количественный учёт склада","Кількісний облік складу")}</label>
                <label style={{ fontSize: 12, display: "flex", alignItems: "flex-end", gap: 6, paddingBottom: 8 }} title={t("Товар под заказ: закупаем ПОСЛЕ продажи. При приходе закупочная цена автоматически обновится во ВСЕХ сделках с этим товаром (в т.ч. закрытых) и в движении товара.","Товар під замовлення: закуповуємо ПІСЛЯ продажу. При приході закупівельна ціна автоматично оновиться в УСІХ угодах з цим товаром (в т.ч. закритих) і в русі товару.")}><input type="checkbox" checked={cardEdit.is_drop} onChange={(e) => setCardEdit({ ...cardEdit, is_drop: e.target.checked })} /> {t("Дроп (докупаем под заказ)","Дроп (докуповуємо під замовлення)")}</label>
                <label style={{ fontSize: 12, gridColumn: "1 / -1" }} className="muted">{t("Описание","Опис")}<textarea value={cardEdit.description} onChange={(e) => setCardEdit({ ...cardEdit, description: e.target.value })} rows={5} style={{ width: "100%", border: "1px solid #cbd5e1", borderRadius: 7, padding: 8, marginTop: 2, fontFamily: "inherit", fontSize: 13 }} /></label>
              </div>
            ) : (
            <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>Артикул: {card.sku || "—"} · {card.category_name || t("Без категории","Без категорії")}</div>
            )}
            {!cardEdit && card.images && card.images.length > 0 && (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
                {card.images.map((im) => <a key={im.id} href={im.url} target="_blank" rel="noreferrer"><img src={im.url} alt="" style={{ width: 92, height: 92, objectFit: "cover", borderRadius: 8, border: "1px solid #e2e8f0" }} /></a>)}
              </div>
            )}
            {!cardEdit && (card.description || "").trim() !== "" && (
              <div className="panel" style={{ margin: "0 0 14px", fontSize: 13, whiteSpace: "pre-wrap" }}>{card.description}</div>
            )}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
              {[[t("Розничная цена","Роздрібна ціна"), Number(card.price).toLocaleString("ru") + " " + (card.currency || "грн")],
                ...(Number(card.min_price) > 0 ? [[t("Минималка за позицию","Мінімалка за позицію"), Number(card.min_price).toLocaleString("ru") + " " + (card.currency || "грн")]] : []),
                ...(showCost && Number(card.cost_pct) > 0 ? [[t("Себест., % от цены","Собівартість, % від ціни"), Number(card.cost_pct) + " %"]] : []),
                ...(showCost ? [[t("Закупівля","Закупівля"), Number(card.cost) > 0 ? Number(card.cost).toLocaleString("ru") + " " + (card.currency || "грн") : "—"], [t("Маржа","Маржа"), (card.margin || 0).toLocaleString("ru") + " ₴" + (Number(card.price) > 0 && card.margin ? " · " + Math.round((card.margin / Number(card.price)) * 100) + "%" : "")]] : []),
                [t("Остаток","Залишок"), Number(card.stock).toLocaleString("ru") + " " + card.unit]].map(([lbl, v]) => (
                <div key={lbl} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{lbl}</div><div style={{ fontSize: 18, fontWeight: 700 }}>{v}</div></div>
              ))}
            </div>
            {(card.b24_created_by || card.b24_modified_by) && (
              <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
                {card.b24_created_by && <>👤 {t("Создал","Створив")}: <b>{card.b24_created_by}</b>{card.b24_created_at ? " · " + card.b24_created_at.slice(0, 10) : ""}</>}
                {card.b24_modified_by && <> &nbsp;·&nbsp; ✏️ {t("Изменил","Змінив")}: <b>{card.b24_modified_by}</b>{card.b24_modified_at ? " · " + card.b24_modified_at.slice(0, 10) : ""}</>}
              </div>
            )}
            {(bundle && (bundle.components.length > 0 || canEdit)) && (
              <div className="panel" style={{ margin: "0 0 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <b style={{ fontSize: 13.5 }}>🧩 {t("Состав набора","Склад набору")}</b>
                  {bundle.components.length > 0 && bundle.can_build !== null && (
                    <span style={{ fontSize: 12.5, fontWeight: 700, padding: "2px 10px", borderRadius: 6, background: bundle.can_build > 0 ? "#dcfce7" : "#fee2e2", color: bundle.can_build > 0 ? "#166534" : "#b91c1c" }}>
                      {t("можно собрать","можна зібрати")}: {bundle.can_build}
                    </span>
                  )}
                </div>
                {bundle.components.length === 0 && <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{t("Это обычный товар. Добавь компоненты — станет набором: при продаже списываются компоненты, закупочная цена считается автоматически.","Це звичайний товар. Додай компоненти — стане набором: при продажу списуються компоненти, закупівельна ціна рахується автоматично.")}</div>}
                {bundle.components.length > 0 && (
                  <table style={{ width: "100%", fontSize: 13 }}>
                    <thead><tr><th>{t("Компонент","Компонент")}</th><th style={{ textAlign: "right" }}>{t("Кол-во","К-сть")}</th><th style={{ textAlign: "right" }}>{t("Розничная","Роздрібна")}</th>{showCost && <th style={{ textAlign: "right" }}>{t("Закупівля","Закупівля")}</th>}<th style={{ textAlign: "right" }}>{t("Остаток","Залишок")}</th>{canEdit && <th></th>}</tr></thead>
                    <tbody>{bundle.components.map((c: any) => (
                      <tr key={c.id}>
                        <td>{c.name} <span className="muted">{c.sku}</span></td>
                        <td style={{ textAlign: "right" }}>
                          {canEdit
                            ? <input type="number" step="0.1" defaultValue={c.quantity} onBlur={(e) => { const q = Number(e.target.value) || 0; if (q !== c.quantity) saveBundle(bundle.components.map((x: any) => x.id === c.id ? { ...x, quantity: q } : x).filter((x: any) => x.quantity > 0)); }} style={{ width: 64, height: 26, border: "1px solid #cbd5e1", borderRadius: 6, textAlign: "right", padding: "0 4px" }} />
                            : c.quantity} {c.unit}
                        </td>
                        <td style={{ textAlign: "right" }}>{Number(c.price || 0).toLocaleString("uk-UA")} ₴</td>
                        {showCost && <td style={{ textAlign: "right" }}>{c.cost.toLocaleString("uk-UA")} ₴</td>}
                        <td style={{ textAlign: "right", color: c.stock > 0 ? "#166534" : "#b91c1c" }}>{c.track_stock === false ? "—" : c.stock}</td>
                        {canEdit && <td style={{ textAlign: "right" }}><button onClick={() => saveBundle(bundle.components.filter((x: any) => x.id !== c.id))} style={{ border: "none", background: "transparent", cursor: "pointer", color: "#dc2626" }}>✕</button></td>}
                      </tr>
                    ))}</tbody>
                  </table>
                )}
                {showCost && bundle.components.length > 0 && (
                  <div style={{ fontSize: 12.5, marginTop: 8, background: "#f8fafc", borderRadius: 8, padding: "8px 10px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}><span className="muted">{t("Компоненты (закупка)","Компоненти (закупівля)")}</span><b>{Number(bundle.components_cost || 0).toLocaleString("uk-UA")} ₴</b></div>
                    <div style={{ display: "flex", justifyContent: "space-between" }} title={t("Меняется в Финансы → Настройка финмодели → Склад/ставки","Змінюється у Фінанси → Налаштування фінмоделі → Склад/ставки")}>
                      <span className="muted">🛠 {t("Работа склада за сборку (из финмодели)","Робота складу за збірку (з фінмоделі)")}</span><b>{Number(bundle.assembly_fee || 0).toLocaleString("uk-UA")} ₴</b>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", borderTop: "1px solid #e2e8f0", marginTop: 4, paddingTop: 4 }}><span>{t("Закупочная набора (авто)","Закупівельна набору (авто)")}</span><b style={{ color: "#9a3412" }}>{bundle.cost.toLocaleString("uk-UA")} ₴</b></div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}><span className="muted">{t("Розничная набора / маржа","Роздрібна набору / маржа")}</span><b>{Number(card.price).toLocaleString("uk-UA")} ₴ · <span style={{ color: Number(card.price) - bundle.cost > 0 ? "#166534" : "#b91c1c" }}>{(Number(card.price) - bundle.cost).toLocaleString("uk-UA")} ₴</span></b></div>
                  </div>
                )}
                {canEdit && (
                  <div style={{ position: "relative", marginTop: 8 }}>
                    <input value={bundleQ} onChange={(e) => setBundleQ(e.target.value)} placeholder={t("➕ Найти товар и добавить в состав…","➕ Знайти товар і додати до складу…")} style={{ width: "100%", height: 32, border: "1px dashed #cbd5e1", borderRadius: 7, padding: "0 10px", fontSize: 13 }} />
                    {bundleOpts.length > 0 && (
                      <div style={{ position: "absolute", top: 34, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 8px 20px rgba(15,23,42,.12)", zIndex: 5, maxHeight: 220, overflow: "auto" }}>
                        {bundleOpts.map((o: any) => (
                          <div key={o.id} onClick={() => { setBundleQ(""); setBundleOpts([]); saveBundle([...bundle.components, { component: o.id, quantity: 1 }]); }} style={{ padding: "7px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f1f5f9" }}>
                            {o.name} <span className="muted">{o.sku} · {t("ост.","зал.")} {o.stock}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", marginBottom: 6 }}>
              <div className="label" style={{ flex: 1, margin: 0 }}>{t("Движение товара (приход / расход / инвентаризация)","Рух товару (прихід / витрата / інвентаризація)")}</div>
              {canTabRec && <button className="btn btn-light" style={{ padding: "3px 10px", fontSize: 12 }} onClick={() => setReceiptFor({ productId: card.id, productName: card.name })} title={t("Оприходовать этот товар (приход с поставщиком)","Оприбуткувати цей товар (прихід з постачальником)")}><Icon n="📥" size={13} /> {t("Приход","Прихід")}</button>}
            </div>
            {movements.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>{t("Движений ещё не было.","Рухів ще не було.")}</div> : (
              <table style={{ width: "100%", fontSize: 13 }}>
                <thead><tr><th>{t("Дата","Дата")}</th><th>{t("Тип","Тип")}</th><th>{t("Кол-во","К-сть")}</th><th>{t("Цена","Ціна")}</th></tr></thead>
                <tbody>{movements.map((m) => (
                  <tr key={m.id}><td className="muted">{new Date(m.date).toLocaleDateString("ru")}</td><td>{m.kind_display}</td>
                    <td style={{ color: m.quantity < 0 ? "#dc2626" : "#16a34a", fontWeight: 600 }}>{m.quantity > 0 ? "+" : ""}{m.quantity}</td>
                    <td>{m.price ? m.price.toLocaleString("ru") + " ₴" : "—"}</td></tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ─── [9] ИНВЕНТАРИЗАЦИЯ ───────────────────────────────────────────── */}
      {view === "inv" && (
        <div style={{ background: "#fff", borderRadius: 8, border: "1px solid #e2e8f0", padding: 22, maxHeight: "calc(100vh - 170px)", display: "flex", flexDirection: "column" }}>
            {/* Ведомость / История проведённых инвентаризаций */}
            <div style={{ display: "flex", gap: 8, marginBottom: 12, borderBottom: "1px solid #f1f5f9", paddingBottom: 8 }}>
              <button className={"btn " + (invScreen === "sheet" ? "btn-primary" : "btn-light")} onClick={() => setInvScreen("sheet")}>{t("Ведомость","Відомість")}</button>
              <button className={"btn " + (invScreen === "history" ? "btn-primary" : "btn-light")} onClick={() => { setInvScreen("history"); setInvHistSel(null); loadInvHistory(1); }}>{t("История","Історія")}{invHistCount ? " (" + invHistCount + ")" : ""}</button>
            </div>
            {invScreen === "sheet" && (<>
            <h3 style={{ marginTop: 0 }}>{t("Инвентаризационная ведомость","Інвентаризаційна відомість")} · {invMode === "folder" && invCat ? (cats.find((c) => c.id === invCat)?.name || t("папка","папка")) : t("все товары","всі товари")} <span className="muted" style={{ fontSize: 13, fontWeight: 400 }}>({invCount})</span></h3>
            {/* Отображение: все товары / по папке + печать */}
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
              <span className="muted" style={{ fontSize: 12 }}>{t("Отображение","Відображення")}:</span>
              <button className={"btn " + (invMode === "all" ? "btn-primary" : "btn-light")} style={{ padding: "4px 12px" }} onClick={() => { setInvMode("all"); setInvPage(1); loadSheet(pFrom, pTo, { mode: "all", page: 1 }); }}>{t("Все товары","Всі товари")}</button>
              <button className={"btn " + (invMode === "folder" ? "btn-primary" : "btn-light")} style={{ padding: "4px 12px" }} onClick={() => { setInvMode("folder"); setInvPage(1); loadSheet(pFrom, pTo, { mode: "folder", page: 1 }); }}>{t("По папке","За папкою")}</button>
              {invMode === "folder" && (
                <select value={invCat ?? ""} onChange={(e) => { const v = e.target.value ? Number(e.target.value) : null; setInvCat(v); setInvPage(1); loadSheet(pFrom, pTo, { mode: "folder", cat: v, page: 1 }); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px", maxWidth: 340 }}>
                  <option value="">{t("— выберите папку —","— оберіть папку —")}</option>
                  {tree.roots.map((r) => [
                    <option key={"r" + r.id} value={r.id}>{r.name}</option>,
                    ...tree.childrenOf(r.id).map((ch) => <option key={"c" + ch.id} value={ch.id}>{"    — " + ch.name}</option>),
                  ])}
                </select>
              )}
              <span style={{ flex: 1 }} />
              <button className="btn btn-light" style={{ padding: "4px 12px" }} disabled={invPrinting} onClick={printInventory} title={t("Печать ведомости с пустой колонкой Факт для отметок на складе","Друк відомості з порожньою колонкою Факт для відміток на складі")}><Icon n="🖨" size={14} /> {invPrinting ? t("Готовим…","Готуємо…") : t("Печать","Друк")}</button>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
              <span className="muted" style={{ fontSize: 12 }}>{t("Период","Період")}:</span>
              <input type="date" value={pFrom} onChange={(e) => { setPFrom(e.target.value); setInvPage(1); loadSheet(e.target.value, pTo, { page: 1 }); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px" }} />
              <span className="muted">—</span>
              <input type="date" value={pTo} onChange={(e) => { setPTo(e.target.value); setInvPage(1); loadSheet(pFrom, e.target.value, { page: 1 }); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px" }} />
              <span className="muted" style={{ fontSize: 12 }}>{t("Начальный + Поступление − Продано = Конечный учётный. Расхождение = Факт − учётный.","Початковий + Надходження − Продано = Кінцевий обліковий. Розбіжність = Факт − обліковий.")}</span>
            </div>
            <div style={{ overflowY: "auto", flex: 1 }}>
              <table style={{ width: "100%", fontSize: 13 }}>
                <thead><tr>{[t("Товар","Товар"), t("Ед.","Од."), t("Начальный","Початковий"), t("Поступ.","Надходж."), t("Продано","Продано"), t("Конечный (учёт)","Кінцевий (облік)"), t("Факт","Факт"), t("Расхождение","Розбіжність")].map((h) => <th key={h} style={{ position: "sticky", top: 0, background: "#fff", zIndex: 2, boxShadow: "inset 0 -1px 0 #e2e8f0", textAlign: "left" }}>{h}</th>)}</tr></thead>
                <tbody>
                  {sheet.map((r) => {
                    const fact = facts[r.id] ?? String(r.book);
                    const delta = Number(fact) - Number(r.book);
                    return (
                      <tr key={r.id}>
                        <td>{r.name}</td><td className="muted">{r.unit}</td>
                        <td>{r.opening.toLocaleString("ru")}</td>
                        <td style={{ color: r.received ? "#16a34a" : "#94a3b8" }}>{r.received ? "+" + r.received.toLocaleString("ru") : "—"}</td>
                        <td style={{ color: r.sold ? "#dc2626" : "#94a3b8" }}>{r.sold ? "−" + r.sold.toLocaleString("ru") : "—"}</td>
                        <td style={{ fontWeight: 600 }}>{r.book.toLocaleString("ru")}</td>
                        <td><input type="number" value={fact} onChange={(e) => setFacts({ ...facts, [r.id]: e.target.value })} style={{ width: 74, height: 28, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px" }} /></td>
                        <td style={{ color: delta < 0 ? "#dc2626" : delta > 0 ? "#16a34a" : "#94a3b8", fontWeight: 600 }}>{delta > 0 ? "+" : ""}{Math.round(delta * 100) / 100 || 0}</td>
                      </tr>
                    );
                  })}
                  {sheet.length === 0 && <tr><td colSpan={8} className="muted" style={{ padding: 12 }}>{invLoading ? t("Загрузка ведомости…","Завантаження відомості…") : t("Нет товаров по этому фильтру.","Немає товарів за цим фільтром.")}</td></tr>}
                </tbody>
              </table>
            </div>
            {invMsg && (() => {
              const ok = invMsg.startsWith("✓"); const bad = invMsg.startsWith("✗"); const warn = invMsg.startsWith("⚠");
              const bg = ok ? "#dcfce7" : bad ? "#fee2e2" : warn ? "#fef9c3" : "#f1f5f9";
              const col = ok ? "#166534" : bad ? "#991b1b" : warn ? "#854d0e" : "#475569";
              return <div style={{ fontSize: 13, marginTop: 10, padding: "8px 12px", borderRadius: 8, background: bg, color: col, display: "flex", alignItems: "center", gap: 8 }}>{invMsg}<span style={{ flex: 1 }} /><button onClick={() => setInvMsg("")} style={{ border: "none", background: "transparent", color: col, cursor: "pointer", fontSize: 16, lineHeight: 1 }}>×</button></div>;
            })()}
            {/* Пагинация ведомости */}
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginTop: 10, paddingTop: 10, borderTop: "1px solid #f1f5f9" }}>
              <span className="muted" style={{ fontSize: 12 }}>{t("Строк на странице","Рядків на сторінці")}:</span>
              {PAGE_SIZES.map((sz) => (
                <button key={sz} onClick={() => { setInvPageSize(sz); setInvPage(1); loadSheet(pFrom, pTo, { pageSize: sz, page: 1 }); }} style={{ fontSize: 13, padding: "4px 11px", borderRadius: 7, cursor: "pointer", border: "1px solid " + (invPageSize === sz ? "var(--brand)" : "#cbd5e1"), background: invPageSize === sz ? "var(--brand)" : "#fff", color: invPageSize === sz ? "#fff" : "#475569" }}>{sz}</button>
              ))}
              <span style={{ flex: 1 }} />
              <button className="btn btn-light" disabled={invPage <= 1 || invLoading} onClick={() => { const pg = Math.max(1, invPage - 1); setInvPage(pg); loadSheet(pFrom, pTo, { page: pg }); }}>{t("← Назад","← Назад")}</button>
              <span style={{ fontSize: 13 }}>{t("Стр.","Стор.")} <b>{invPage}</b> {t("из","з")} <b>{invTotalPages}</b></span>
              <button className="btn btn-light" disabled={invPage >= invTotalPages || invLoading} onClick={() => { const pg = Math.min(invTotalPages, invPage + 1); setInvPage(pg); loadSheet(pFrom, pTo, { page: pg }); }}>{t("Вперёд →","Вперед →")}</button>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setView("goods")}>{t("← К товарам","← До товарів")}</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={conductInventory}>{t("Провести инвентаризацию","Провести інвентаризацію")}</button>
            </div>
            </>)}
            {invScreen === "history" && (
              <div style={{ overflowY: "auto", flex: 1 }}>
                {!invHistSel && (<>
                  {invHistBusy && <div className="muted" style={{ fontSize: 13, padding: 8 }}>{t("Загрузка…","Завантаження…")}</div>}
                  {!invHistBusy && invHistDocs.length === 0 && <div className="muted" style={{ fontSize: 13, padding: 8 }}>{t("Инвентаризаций ещё не проводили.","Інвентаризацій ще не проводили.")}</div>}
                  {invHistDocs.map((d) => {
                    const items = d.items || [];
                    const short = items.filter((it: any) => Number(it.quantity) < 0).length;
                    const over = items.filter((it: any) => Number(it.quantity) > 0).length;
                    return (
                      <div key={d.id} onClick={() => setInvHistSel(d)} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 8px", borderBottom: "1px solid #f1f5f9", cursor: "pointer" }}>
                        <div style={{ minWidth: 92, fontWeight: 600 }}>{(d.created_at || "").slice(0, 10)}</div>
                        <div style={{ flex: 1 }}>{d.comment || t("Инвентаризация","Інвентаризація")}</div>
                        <div className="muted" style={{ fontSize: 12 }}>{t("позиций","позицій")}: <b>{items.length}</b></div>
                        {short > 0 && <span style={{ color: "#dc2626", fontSize: 12 }} title={t("недостача","нестача")}>−{short}</span>}
                        {over > 0 && <span style={{ color: "#16a34a", fontSize: 12 }} title={t("излишек","надлишок")}>+{over}</span>}
                        <span className="muted">→</span>
                      </div>
                    );
                  })}
                  {invHistCount > invHistPageSize && (
                    <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 10 }}>
                      <button className="btn btn-light" disabled={invHistPage <= 1 || invHistBusy} onClick={() => loadInvHistory(invHistPage - 1)}>{t("← Назад","← Назад")}</button>
                      <span style={{ fontSize: 13 }}>{t("Стр.","Стор.")} <b>{invHistPage}</b> {t("из","з")} <b>{invHistTotalPages}</b></span>
                      <button className="btn btn-light" disabled={invHistPage >= invHistTotalPages || invHistBusy} onClick={() => loadInvHistory(invHistPage + 1)}>{t("Вперёд →","Вперед →")}</button>
                    </div>
                  )}
                </>)}
                {invHistSel && (
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
                      <button className="btn btn-light" onClick={() => setInvHistSel(null)}>{t("← К списку","← До списку")}</button>
                      <b>{(invHistSel.created_at || "").slice(0, 10)}</b>
                      <span className="muted" style={{ fontSize: 13 }}>{invHistSel.comment}</span>
                    </div>
                    <table style={{ width: "100%", fontSize: 13 }}>
                      <thead><tr>{[t("Товар","Товар"), t("Расхождение","Розбіжність"), t("Себест.","Собівар."), t("Сумма","Сума")].map((h) => <th key={h} style={{ textAlign: "left", boxShadow: "inset 0 -1px 0 #e2e8f0" }}>{h}</th>)}</tr></thead>
                      <tbody>
                        {(invHistSel.items || []).map((it: any) => {
                          const q = Number(it.quantity); const pr = Number(it.price);
                          return (
                            <tr key={it.id}>
                              <td>{it.product_name}</td>
                              <td style={{ color: q < 0 ? "#dc2626" : q > 0 ? "#16a34a" : "#94a3b8", fontWeight: 600 }}>{q > 0 ? "+" : ""}{q}</td>
                              <td className="muted">{pr ? pr.toLocaleString("ru") : "—"}</td>
                              <td>{pr ? (Math.round(q * pr * 100) / 100).toLocaleString("ru") + " ₴" : "—"}</td>
                            </tr>
                          );
                        })}
                        {(invHistSel.items || []).length === 0 && <tr><td colSpan={4} className="muted" style={{ padding: 10 }}>{t("Расхождений не было — остатки совпали.","Розбіжностей не було — залишки збіглися.")}</td></tr>}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
      )}
      {/* Встроенное окно подтверждения проведения инвентаризации (вместо браузерного alert/confirm) */}
      {invConfirm && (
        <div onClick={() => !invBusy && setInvConfirm(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 24, width: 560, maxWidth: "92vw", maxHeight: "84vh", display: "flex", flexDirection: "column" }}>
            <h3 style={{ marginTop: 0 }}>{t("Провести инвентаризацию?","Провести інвентаризацію?")}</h3>
            <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>{t("Остатки этих товаров будут скорректированы по факту. Недостача — в минус, излишек — в плюс. Запись попадёт в «Историю».","Залишки цих товарів будуть скориговані за фактом. Нестача — у мінус, надлишок — у плюс. Запис потрапить в «Історію».")}</div>
            <div style={{ overflowY: "auto", flex: 1, marginBottom: 14, border: "1px solid #f1f5f9", borderRadius: 8 }}>
              <table style={{ width: "100%", fontSize: 13 }}>
                <thead><tr>{[t("Товар","Товар"), t("Было (учёт)","Було (облік)"), t("Стало (факт)","Стало (факт)"), t("Разница","Різниця")].map((h) => <th key={h} style={{ position: "sticky", top: 0, background: "#f8fafc", textAlign: "left", padding: "6px 8px", boxShadow: "inset 0 -1px 0 #e2e8f0" }}>{h}</th>)}</tr></thead>
                <tbody>
                  {invConfirm.items.map((r) => (
                    <tr key={r.product}>
                      <td style={{ padding: "6px 8px" }}>{r.name} <span className="muted">{r.unit}</span></td>
                      <td style={{ padding: "6px 8px" }}>{r.book.toLocaleString("ru")}</td>
                      <td style={{ padding: "6px 8px", fontWeight: 600 }}>{r.fact.toLocaleString("ru")}</td>
                      <td style={{ padding: "6px 8px", fontWeight: 600, color: r.delta < 0 ? "#dc2626" : r.delta > 0 ? "#16a34a" : "#94a3b8" }}>{r.delta > 0 ? "+" : ""}{Math.round(r.delta * 100) / 100}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} disabled={invBusy} onClick={() => setInvConfirm(null)}>{t("Отмена","Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 1 }} disabled={invBusy} onClick={doConduct}>{invBusy ? t("Проводим…","Проводимо…") : t(`Провести (${invConfirm.items.length})`,`Провести (${invConfirm.items.length})`)}</button>
            </div>
          </div>
        </div>
      )}
      {receiptFor && <ReceiptModal productId={receiptFor.productId} productName={receiptFor.productName} onClose={() => setReceiptFor(null)} onSaved={() => { loadProducts(); openReceiptList(); if (card) api.get<Movement[]>(`/api/products/${card.id}/movements/`).then(setMovements).catch(() => {}); }} />}
    </div>
  );
}

/* ─── [10] СУБ-КОМПОНЕНТ: инлайн-ввод закупочной цены ─── */
function EditCost({ p, onSaved }: { p: Product; onSaved: (v: number) => void }) {
  const { t } = useLang();
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState(p.cost);
  useEffect(() => setV(p.cost), [p.cost]);
  if (edit) return (
    <input autoFocus type="number" value={v} onChange={(e) => setV(e.target.value)}
      onBlur={async () => { setEdit(false); if (Number(v) !== Number(p.cost)) { await api.patch(`/api/products/${p.id}/`, { cost: Number(v) }); onSaved(Number(v)); } }}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
      style={{ width: 84, height: 26, border: "1px solid var(--brand)", borderRadius: 5, padding: "0 5px", fontSize: 12 }} />
  );
  const c = Number(p.cost);
  return <span onClick={() => setEdit(true)} style={{ cursor: "text", borderBottom: "1px dashed #cbd5e1", color: c > 0 ? "#1e293b" : "#94a3b8" }}>{c > 0 ? c.toLocaleString("ru") + " " + (p.currency || "грн") : t("— вписать","— вписати")}</span>;
}
