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
import { api, Paginated } from "../api";
import { useLang } from "../i18n";
import { useAuth } from "../auth";
import { Icon } from "../Icon";

/* ─── [1] ТИПЫ ─────────────────────────────────────────────────────────── */
interface Product {
  id: number; name: string; sku: string; unit: string;
  price: string; cost: string; currency: string; margin: number;
  category: number | null; category_name: string; stock: number;
}
interface Category { id: number; name: string; parent: number | null; order: number; products_count: number; }
interface WH { id: number; name: string; is_default: boolean; }
interface Movement { id: number; kind: string; kind_display: string; quantity: number; price: number; warehouse: string; date: string; number: string | number; }

interface SheetRow { id: number; name: string; unit: string; opening: number; received: number; sold: number; book: number; }
const PAGE_SIZES = [5, 20, 50, 100, 500];
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
  const canRealize = can("warehouse.edit") || can("finance.manage");
  const [view, setView] = useState<"goods" | "realiz">("goods");
  const [realizDocs, setRealizDocs] = useState<any[]>([]);
  const [realizBusy, setRealizBusy] = useState(false);
  const [realizSel, setRealizSel] = useState<any>(null);
  function docTitle(d: any) {
    return (d.number || ("РН-" + d.id)) + " · " + (d.deal_title || (d.deal ? t("сделка","сделка") + " #" + d.deal : t("ручное","ручне"))) + " · " + (d.created_at || "").slice(0, 10);
  }
  async function openRealizList() {
    setRealizBusy(true);
    try { const r: any = await api.get("/api/stock-documents/?kind=out"); setRealizDocs(Array.isArray(r) ? r : (r.results || [])); }
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
  const [movements, setMovements] = useState<Movement[]>([]);
  // инвентаризация
  const [invOpen, setInvOpen] = useState(false);
  const [facts, setFacts] = useState<Record<number, string>>({});
  const [invMsg, setInvMsg] = useState("");
  const [sheet, setSheet] = useState<SheetRow[]>([]);
  const [pFrom, setPFrom] = useState(monthStart());
  const [pTo, setPTo] = useState(today());

  /* ─── [3] ЗАГРУЗКА ───────────────────────────────────────────────────── */
  const [params] = useSearchParams();
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
    q.set("is_active", "true");
    const d = await api.get<Paginated<Product>>(`/api/products/?${q.toString()}`);
    setProducts(d.results); setCount(d.count); setLoading(false);
  }
  useEffect(() => { loadProducts(); }, [cat, page, pageSize, ordering]);
  useEffect(() => {
    const t = setTimeout(() => { setPage(1); loadProducts(); }, 350);
    return () => clearTimeout(t);
  }, [search]);

  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  /* ─── [4] ДЕЙСТВИЯ ───────────────────────────────────────────────────── */
  async function saveDoc() {
    if (!form.product) return;
    await api.post("/api/stock-documents/", {
      kind: modal, warehouse: whs[0]?.id,
      items: [{ product: form.product, quantity: form.quantity, price: form.price }],
    });
    setModal(null); setForm({ product: 0, quantity: 1, price: 0 });
    loadProducts();
  }

  async function openCard(p: Product) {
    setCard(p); setMovements([]);
    const mv = await api.get<Movement[]>(`/api/products/${p.id}/movements/`);
    setMovements(mv);
  }

  async function loadSheet(from: string, to: string) {
    const ids = products.map((p) => p.id).join(",");
    if (!ids) { setSheet([]); return; }
    const q = new URLSearchParams({ ids, from, to });
    const d = await api.get<{ rows: SheetRow[] }>(`/api/warehouse/inventory-sheet/?${q.toString()}`);
    setSheet(d.rows);
    const init: Record<number, string> = {};
    d.rows.forEach((r) => { init[r.id] = String(r.book); });
    setFacts(init);
  }
  async function openInventory() {
    setInvMsg(""); setInvOpen(true);
    await loadSheet(pFrom, pTo);
  }
  async function conductInventory() {
    const items = sheet
      .filter((r) => facts[r.id] !== undefined && Number(facts[r.id]) !== Number(r.book))
      .map((r) => ({ product: r.id, quantity: Number(facts[r.id]), price: 0 }));
    if (!items.length) { setInvMsg(t("Нет расхождений факта с учётом — нечего проводить.","Немає розбіжностей факту з обліком — нічого проводити.")); return; }
    await api.post("/api/stock-documents/", { kind: "inv", warehouse: whs[0]?.id, comment: `Інвентаризація ${pFrom}…${pTo}`, items });
    setInvOpen(false); loadProducts();
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
      alert(t("Приход проведён ✓ Позиций: ", "Прихід проведено ✓ Позицій: ") + done.positions); loadProducts();
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
        <button className={"btn" + (view === "realiz" ? " btn-primary" : " btn-light")} onClick={() => { setView("realiz"); setRealizSel(null); openRealizList(); }}><Icon n="📤" size={15} /> {t("Реализации","Реалізації")}</button>
      </div>

      {view === "realiz" ? (
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
        {realizSel ? (
          <>
            <button className="btn btn-light" onClick={() => setRealizSel(null)}>← {t("К списку реализаций","До списку реалізацій")}</button>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10, marginTop: 12 }}>
              <div>
                <h3 style={{ margin: "0 0 4px" }}>{t("Реализация","Реалізація")} {docTitle(realizSel)}</h3>
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
              {canEdit && <button className="btn btn-light" onClick={() => setModal("out")} title={t("Ручное списание товара","Ручне списання товару")}><Icon n="📤" size={14} /> {t("Ручное списание","Ручне списання")}</button>}
            </div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("Создаются автоматически, когда сделка переходит в стадию «Успешная». «Проведён» = товар списан со склада. Кликните на строку — откроется документ. Провести/отменить может ответственный за склад или бухгалтер.","Створюються автоматично, коли сделка переходить у стадію «Успішна». «Проведено» = товар списано зі складу. Клікніть на рядок — відкриється документ. Провести/скасувати може відповідальний за склад або бухгалтер.")}</div>
            {realizBusy ? <div className="muted" style={{ padding: 16 }}>{t("Загрузка…","Завантаження…")}</div> :
             realizDocs.length === 0 ? <div className="muted" style={{ padding: 16 }}>{t("Пока нет реализаций.","Поки немає реалізацій.")}</div> :
            <table style={{ width: "100%" }}>
              <thead><tr><th>№</th><th>{t("Дата","Дата")}</th><th>{t("Сделка","Сделка")}</th><th>{t("Стадия закрытия","Стадія закриття")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th><th style={{ textAlign: "center" }}>{t("Статус","Статус")}</th><th></th></tr></thead>
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
          </>
        )}
      </div>
      ) : (
      <div style={{ display: "grid", gridTemplateColumns: `${catW}px 8px 1fr`, gap: 6, alignItems: "start" }}>

      {/* ─── [5] ДЕРЕВО КАТЕГОРИЙ ─────────────────────────────────────────── */}
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 8, position: "sticky", top: 8, maxHeight: "calc(100vh - 90px)", overflowY: "auto" }}>
        <div onClick={() => pick(null)} style={{ padding: "7px 9px", borderRadius: 6, cursor: "pointer", fontWeight: 600, background: cat === null ? "#eff6ff" : "", color: cat === null ? "#1d4ed8" : "#1e293b" }}>
          <Icon n="📦" size={15} /> {t("Все товары","Всі товари")} <span className="muted" style={{ fontWeight: 400 }}>({count})</span>
        </div>
        {tree.roots.map((r) => (
          <div key={r.id}>
            <div onClick={() => pick(r.id)} style={{ padding: "6px 9px", borderRadius: 6, cursor: "pointer", fontSize: 13, background: cat === r.id ? "#eff6ff" : "", color: cat === r.id ? "#1d4ed8" : "#334155" }}>
              <Icon n="📁" size={14} /> {r.name} <span className="muted">({r.products_count})</span>
            </div>
            {tree.childrenOf(r.id).map((ch) => (
              <div key={ch.id} onClick={() => pick(ch.id)} style={{ padding: "5px 9px 5px 24px", borderRadius: 6, cursor: "pointer", fontSize: 12.5, background: cat === ch.id ? "#eff6ff" : "", color: cat === ch.id ? "#1d4ed8" : "#475569" }}>
                {ch.name} <span className="muted">({ch.products_count})</span>
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
          <button className="btn btn-primary" onClick={() => setModal("in")}><Icon n="📥" size={15} /> {t("Приход","Прихід")}</button>
          {canEdit && <><input ref={receiptFileRef} type="file" accept=".csv,text/csv,text/plain" style={{ display: "none" }} onChange={importReceipt} /><button className="btn btn-light" onClick={() => receiptFileRef.current?.click()} title={t("Приход из файла: артикул, кол-во, цена","Прихід з файлу: артикул, к-сть, ціна")}><Icon n="📄" size={15} /> {t("Приход файлом","Прихід файлом")}</button></>}
          <button className="btn btn-light" onClick={openInventory}><Icon n="📋" size={15} /> {t("Инвентаризация","Інвентаризація")}</button>
          <button className="btn btn-light" onClick={exportCsv} title={t("Выгрузить номенклатуру в CSV (Excel)","Вивантажити номенклатуру в CSV (Excel)")}><Icon n="⬇️" size={15} /> {t("Экспорт","Експорт")}</button>
          {canEdit && <>
          <input ref={nomFileRef} type="file" accept=".csv,text/csv,text/plain" style={{ display: "none" }} onChange={importNom} />
          <button className="btn btn-light" onClick={() => nomFileRef.current?.click()} title={t("Загрузить номенклатуру из CSV (остатки не меняет)","Завантажити номенклатуру з CSV (залишки не змінює)")}><Icon n="⬆️" size={15} /> {t("Импорт","Імпорт")}</button>
          </>}
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("🔍 Поиск товара / артикула…","🔍 Пошук товару / артикулу…")} style={{ flex: 1, minWidth: 160, height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 12px", fontSize: 13 }} />
          <span className="muted">{t("Найдено","Знайдено")}: <b style={{ color: "#1e293b" }}>{count.toLocaleString("ru")}</b></span>
        </div>

        <div className="tablewrap" style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8 }}>
          <table style={{ width: "100%" }}>
            <thead><tr>{sortTh("name", t("Товар","Товар"))}{sortTh("sku", t("Артикул","Артикул"))}<th>{t("Категория","Категорія")}</th>{sortTh("price", t("Цена","Ціна"))}{showCost && sortTh("cost", t("Закупка","Закупка"))}<th>{t("Ед.","Од.")}</th><th>{t("Остаток","Залишок")}</th>{canEdit && <th></th>}</tr></thead>
            <tbody>
              {loading && <tr><td colSpan={6 + (showCost ? 1 : 0) + (canEdit ? 1 : 0)} className="muted" style={{ padding: 16 }}>{t("Загрузка…","Завантаження…")}</td></tr>}
              {!loading && products.length === 0 && <tr><td colSpan={6 + (showCost ? 1 : 0) + (canEdit ? 1 : 0)} className="muted" style={{ padding: 16 }}>{t("Товаров не найдено","Товарів не знайдено")}</td></tr>}
              {!loading && products.map((p) => (
                <tr key={p.id}>
                  <td><span onClick={() => openCard(p)} style={{ fontWeight: 500, color: "#1d4ed8", cursor: "pointer" }}>{p.name}</span></td>
                  <td className="muted">{p.sku}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{p.category_name || "—"}</td>
                  <td>{Number(p.price).toLocaleString("ru")} {p.currency || "грн"}</td>
                  {showCost && <td><EditCost p={p} onSaved={(v) => setProducts((ps) => ps.map((x) => (x.id === p.id ? { ...x, cost: String(v) } : x)))} /></td>}
                  <td>{p.unit}</td>
                  <td><span style={{ color: Number(p.stock) <= 0 ? "#dc2626" : Number(p.stock) < 100 ? "#d97706" : "#16a34a", fontWeight: 600 }}>{Number(p.stock).toLocaleString("ru")}</span></td>
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
      )}

      {/* ─── [7] МОДАЛКА ПРИХОД/РАСХОД ────────────────────────────────────── */}
      {modal && (
        <div onClick={() => setModal(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 24, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>{modal === "in" ? t("Приходная накладная","Прибуткова накладна") : t("Реализация (списание) товара","Реалізація (списання) товару")}</h3>
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
          <div onClick={(e) => e.stopPropagation()} style={{ width: "min(560px,94vw)", height: "100%", background: "#fff", overflow: "auto", padding: "18px 22px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <h3 style={{ margin: 0 }}>{card.name}</h3>
              <button className="btn btn-light" onClick={() => setCard(null)}>✕</button>
            </div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>Артикул: {card.sku || "—"} · {card.category_name || t("Без категории","Без категорії")}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
              {[[t("Розничная цена","Роздрібна ціна"), Number(card.price).toLocaleString("ru") + " " + (card.currency || "грн")],
                ...(showCost ? [[t("Закупка","Закупка"), Number(card.cost) > 0 ? Number(card.cost).toLocaleString("ru") + " " + (card.currency || "грн") : "—"], [t("Маржа","Маржа"), (card.margin || 0).toLocaleString("ru") + " ₴" + (Number(card.price) > 0 && card.margin ? " · " + Math.round((card.margin / Number(card.price)) * 100) + "%" : "")]] : []),
                [t("Остаток","Залишок"), Number(card.stock).toLocaleString("ru") + " " + card.unit]].map(([lbl, v]) => (
                <div key={lbl} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{lbl}</div><div style={{ fontSize: 18, fontWeight: 700 }}>{v}</div></div>
              ))}
            </div>
            <div className="label" style={{ marginBottom: 6 }}>{t("Движение товара (приход / расход / инвентаризация)","Рух товару (прихід / витрата / інвентаризація)")}</div>
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
      {invOpen && (
        <div onClick={() => setInvOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: "min(900px,96vw)", maxHeight: "88vh", display: "flex", flexDirection: "column" }}>
            <h3 style={{ marginTop: 0 }}>{t("Инвентаризационная ведомость","Інвентаризаційна відомість")} {cat ? t("· выбранная категория","· обрана категорія") : t("· текущая страница","· поточна сторінка")}</h3>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
              <span className="muted" style={{ fontSize: 12 }}>{t("Период","Період")}:</span>
              <input type="date" value={pFrom} onChange={(e) => { setPFrom(e.target.value); loadSheet(e.target.value, pTo); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px" }} />
              <span className="muted">—</span>
              <input type="date" value={pTo} onChange={(e) => { setPTo(e.target.value); loadSheet(pFrom, e.target.value); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px" }} />
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
                  {sheet.length === 0 && <tr><td colSpan={8} className="muted" style={{ padding: 12 }}>{t("Загрузка ведомости…","Завантаження відомості…")}</td></tr>}
                </tbody>
              </table>
            </div>
            {invMsg && <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{invMsg}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setInvOpen(false)}>{t("Отмена","Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={conductInventory}>{t("Провести инвентаризацию","Провести інвентаризацію")}</button>
            </div>
          </div>
        </div>
      )}
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
