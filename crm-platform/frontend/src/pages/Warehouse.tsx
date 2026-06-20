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
import { useEffect, useMemo, useState } from "react";
import { api, Paginated } from "../api";

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
  const [cats, setCats] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [count, setCount] = useState(0);
  const [cat, setCat] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [whs, setWhs] = useState<WH[]>([]);
  const [modal, setModal] = useState<null | "in" | "out">(null);
  const [form, setForm] = useState({ product: 0, quantity: 1, price: 0 });
  const [loading, setLoading] = useState(false);
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
  useEffect(() => {
    api.get<Category[]>("/api/product-categories/").then(setCats).catch(() => setCats([]));
    api.get<Paginated<WH>>("/api/warehouses/").then((w) => setWhs(w.results));
  }, []);

  async function loadProducts() {
    setLoading(true);
    const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (cat) q.set("category", String(cat));
    if (search.trim()) q.set("search", search.trim());
    const d = await api.get<Paginated<Product>>(`/api/products/?${q.toString()}`);
    setProducts(d.results); setCount(d.count); setLoading(false);
  }
  useEffect(() => { loadProducts(); }, [cat, page, pageSize]);
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
    if (!items.length) { setInvMsg("Нет расхождений факта с учётом — нечего проводить."); return; }
    await api.post("/api/stock-documents/", { kind: "inv", warehouse: whs[0]?.id, comment: `Інвентаризація ${pFrom}…${pTo}`, items });
    setInvOpen(false); loadProducts();
  }

  const tree = useMemo(() => {
    const roots = cats.filter((c) => !c.parent).sort((a, b) => a.name.localeCompare(b.name));
    const childrenOf = (id: number) => cats.filter((c) => c.parent === id).sort((a, b) => a.name.localeCompare(b.name));
    return { roots, childrenOf };
  }, [cats]);
  function pick(id: number | null) { setCat(id); setPage(1); }

  return (
    <div className="scroll pad fade" style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 12, alignItems: "start" }}>

      {/* ─── [5] ДЕРЕВО КАТЕГОРИЙ ─────────────────────────────────────────── */}
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 8, position: "sticky", top: 8, maxHeight: "calc(100vh - 90px)", overflowY: "auto" }}>
        <div onClick={() => pick(null)} style={{ padding: "7px 9px", borderRadius: 6, cursor: "pointer", fontWeight: 600, background: cat === null ? "#eff6ff" : "", color: cat === null ? "#1d4ed8" : "#1e293b" }}>
          📦 Всі товари <span className="muted" style={{ fontWeight: 400 }}>({count})</span>
        </div>
        {tree.roots.map((r) => (
          <div key={r.id}>
            <div onClick={() => pick(r.id)} style={{ padding: "6px 9px", borderRadius: 6, cursor: "pointer", fontSize: 13, background: cat === r.id ? "#eff6ff" : "", color: cat === r.id ? "#1d4ed8" : "#334155" }}>
              📁 {r.name} <span className="muted">({r.products_count})</span>
            </div>
            {tree.childrenOf(r.id).map((ch) => (
              <div key={ch.id} onClick={() => pick(ch.id)} style={{ padding: "5px 9px 5px 24px", borderRadius: 6, cursor: "pointer", fontSize: 12.5, background: cat === ch.id ? "#eff6ff" : "", color: cat === ch.id ? "#1d4ed8" : "#475569" }}>
                {ch.name} <span className="muted">({ch.products_count})</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* ─── [6] ТУЛБАР + ТАБЛИЦА + ПАГИНАЦИЯ ─────────────────────────────── */}
      <div>
        <div className="toolbar" style={{ borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 10, background: "#fff", display: "flex", gap: 8, alignItems: "center", padding: 8, flexWrap: "wrap" }}>
          <button className="btn btn-primary" onClick={() => setModal("in")}>📥 Приход</button>
          <button className="btn btn-light" onClick={() => setModal("out")}>📤 Расход</button>
          <button className="btn btn-light" onClick={openInventory}>📋 Інвентаризація</button>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="🔍 Поиск товара / артикула…" style={{ flex: 1, minWidth: 160, height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 12px", fontSize: 13 }} />
          <span className="muted">Найдено: <b style={{ color: "#1e293b" }}>{count.toLocaleString("ru")}</b></span>
        </div>

        <div className="tablewrap" style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8 }}>
          <table style={{ width: "100%" }}>
            <thead><tr><th>Товар</th><th>Артикул</th><th>Категорія</th><th>Ціна</th><th>Закупка</th><th>Од.</th><th>Залишок</th></tr></thead>
            <tbody>
              {loading && <tr><td colSpan={7} className="muted" style={{ padding: 16 }}>Загрузка…</td></tr>}
              {!loading && products.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 16 }}>Товаров не найдено</td></tr>}
              {!loading && products.map((p) => (
                <tr key={p.id}>
                  <td><span onClick={() => openCard(p)} style={{ fontWeight: 500, color: "#1d4ed8", cursor: "pointer" }}>{p.name}</span></td>
                  <td className="muted">{p.sku}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{p.category_name || "—"}</td>
                  <td>{Number(p.price).toLocaleString("ru")} {p.currency || "грн"}</td>
                  <td><EditCost p={p} onSaved={(v) => setProducts((ps) => ps.map((x) => (x.id === p.id ? { ...x, cost: String(v) } : x)))} /></td>
                  <td>{p.unit}</td>
                  <td><span style={{ color: Number(p.stock) <= 0 ? "#dc2626" : Number(p.stock) < 100 ? "#d97706" : "#16a34a", fontWeight: 600 }}>{Number(p.stock).toLocaleString("ru")}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: 13 }}>На странице:</span>
          {PAGE_SIZES.map((s) => (
            <button key={s} onClick={() => { setPageSize(s); setPage(1); }} style={{ fontSize: 13, padding: "4px 11px", borderRadius: 7, cursor: "pointer", border: "1px solid " + (pageSize === s ? "var(--brand)" : "#cbd5e1"), background: pageSize === s ? "var(--brand)" : "#fff", color: pageSize === s ? "#fff" : "#475569" }}>{s}</button>
          ))}
          <div className="spacer" style={{ flex: 1 }} />
          <button className="btn btn-light" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>← Назад</button>
          <span style={{ fontSize: 13 }}>Стр. <b>{page}</b> из <b>{totalPages}</b></span>
          <button className="btn btn-light" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Вперёд →</button>
        </div>
      </div>

      {/* ─── [7] МОДАЛКА ПРИХОД/РАСХОД ────────────────────────────────────── */}
      {modal && (
        <div onClick={() => setModal(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 24, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>{modal === "in" ? "Приходная накладная" : "Расходная накладная"}</h3>
            <label className="label">Товар</label>
            <select value={form.product} onChange={(e) => setForm({ ...form, product: Number(e.target.value) })} style={{ width: "100%", height: 38, marginBottom: 10, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }}>
              <option value={0}>— выбери товар (из текущей страницы) —</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name} (остаток {p.stock})</option>)}
            </select>
            <label className="label">Количество</label>
            <input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} style={{ width: "100%", height: 38, marginBottom: 10, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            <label className="label">Цена за ед.</label>
            <input type="number" value={form.price} onChange={(e) => setForm({ ...form, price: Number(e.target.value) })} style={{ width: "100%", height: 38, marginBottom: 16, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setModal(null)}>Отмена</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={saveDoc}>Провести</button>
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
            <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>Артикул: {card.sku || "—"} · {card.category_name || "Без категорії"}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
              {[["Роздрібна ціна", Number(card.price).toLocaleString("ru") + " " + (card.currency || "грн")],
                ["Закупка", Number(card.cost) > 0 ? Number(card.cost).toLocaleString("ru") + " " + (card.currency || "грн") : "—"],
                ["Маржа", (card.margin || 0).toLocaleString("ru") + " ₴" + (Number(card.price) > 0 && card.margin ? " · " + Math.round((card.margin / Number(card.price)) * 100) + "%" : "")],
                ["Залишок", Number(card.stock).toLocaleString("ru") + " " + card.unit]].map(([t, v]) => (
                <div key={t} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{t}</div><div style={{ fontSize: 18, fontWeight: 700 }}>{v}</div></div>
              ))}
            </div>
            <div className="label" style={{ marginBottom: 6 }}>Рух товару (приход / расход / інвентаризація)</div>
            {movements.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>Рухів ще не було.</div> : (
              <table style={{ width: "100%", fontSize: 13 }}>
                <thead><tr><th>Дата</th><th>Тип</th><th>К-сть</th><th>Ціна</th></tr></thead>
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
            <h3 style={{ marginTop: 0 }}>Інвентаризаційна відомість {cat ? "· обрана категорія" : "· поточна сторінка"}</h3>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
              <span className="muted" style={{ fontSize: 12 }}>Період:</span>
              <input type="date" value={pFrom} onChange={(e) => { setPFrom(e.target.value); loadSheet(e.target.value, pTo); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px" }} />
              <span className="muted">—</span>
              <input type="date" value={pTo} onChange={(e) => { setPTo(e.target.value); loadSheet(pFrom, e.target.value); }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6, padding: "0 6px" }} />
              <span className="muted" style={{ fontSize: 12 }}>Початковий + Надходження − Продано = Кінцевий обліковий. Розбіжність = Факт − обліковий.</span>
            </div>
            <div style={{ overflowY: "auto", flex: 1 }}>
              <table style={{ width: "100%", fontSize: 13 }}>
                <thead><tr>{["Товар", "Од.", "Початковий", "Надходж.", "Продано", "Кінцевий (облік)", "Факт", "Розбіжність"].map((h) => <th key={h} style={{ position: "sticky", top: 0, background: "#fff", zIndex: 2, boxShadow: "inset 0 -1px 0 #e2e8f0", textAlign: "left" }}>{h}</th>)}</tr></thead>
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
                  {sheet.length === 0 && <tr><td colSpan={8} className="muted" style={{ padding: 12 }}>Завантаження відомості…</td></tr>}
                </tbody>
              </table>
            </div>
            {invMsg && <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{invMsg}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setInvOpen(false)}>Скасувати</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={conductInventory}>Провести інвентаризацію</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── [10] СУБ-КОМПОНЕНТ: инлайн-ввод закупочной цены ─── */
function EditCost({ p, onSaved }: { p: Product; onSaved: (v: number) => void }) {
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
  return <span onClick={() => setEdit(true)} style={{ cursor: "text", borderBottom: "1px dashed #cbd5e1", color: c > 0 ? "#1e293b" : "#94a3b8" }}>{c > 0 ? c.toLocaleString("ru") + " " + (p.currency || "грн") : "— вписати"}</span>;
}
