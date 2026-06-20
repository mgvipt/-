/* ============================================================================
 *  СКЛАД / КАТАЛОГ ТОВАРОВ  —  frontend/src/pages/Warehouse.tsx
 * ----------------------------------------------------------------------------
 *  Дерево категорий (слева) + таблица товаров (справа) с поиском, пагинацией
 *  и выбором числа строк на странице (5/20/50/100/500). Перенос из Bitrix.
 *  Документация: docs/CODEMAP.md разд.3.
 *
 *  БЛОКИ:
 *    [1] ТИПЫ
 *    [2] STATE
 *    [3] ЗАГРУЗКА (категории / товары с пагинацией)
 *    [4] ДЕЙСТВИЯ (приход/расход)
 *    [5] РЕНДЕР: дерево категорий (левая колонка)
 *    [6] РЕНДЕР: тулбар + таблица товаров + пагинация
 *    [7] РЕНДЕР: модалка прихода/расхода
 * ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api, Paginated } from "../api";

/* ─── [1] ТИПЫ ─────────────────────────────────────────────────────────── */
interface Product {
  id: number; name: string; sku: string; unit: string;
  price: string; cost: string; currency: string;
  category: number | null; category_name: string; stock: number;
}
interface Category { id: number; name: string; parent: number | null; order: number; products_count: number; }
interface WH { id: number; name: string; is_default: boolean; }

const PAGE_SIZES = [5, 20, 50, 100, 500];

export default function Warehouse() {
  /* ─── [2] STATE ──────────────────────────────────────────────────────── */
  const [cats, setCats] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [count, setCount] = useState(0);
  const [cat, setCat] = useState<number | null>(null);   // выбранная категория (null = все)
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [whs, setWhs] = useState<WH[]>([]);
  const [modal, setModal] = useState<null | "in" | "out">(null);
  const [form, setForm] = useState({ product: 0, quantity: 1, price: 0 });
  const [loading, setLoading] = useState(false);

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
  // поиск с дебаунсом + сброс на 1-ю страницу
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

  // дерево категорий: корневые + дети
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
        <div onClick={() => pick(null)}
          style={{ padding: "7px 9px", borderRadius: 6, cursor: "pointer", fontWeight: 600,
            background: cat === null ? "#eff6ff" : "", color: cat === null ? "#1d4ed8" : "#1e293b" }}>
          📦 Всі товари <span className="muted" style={{ fontWeight: 400 }}>({count})</span>
        </div>
        {tree.roots.map((r) => (
          <div key={r.id}>
            <div onClick={() => pick(r.id)}
              style={{ padding: "6px 9px", borderRadius: 6, cursor: "pointer", fontSize: 13,
                background: cat === r.id ? "#eff6ff" : "", color: cat === r.id ? "#1d4ed8" : "#334155" }}>
              📁 {r.name} <span className="muted">({r.products_count})</span>
            </div>
            {tree.childrenOf(r.id).map((ch) => (
              <div key={ch.id} onClick={() => pick(ch.id)}
                style={{ padding: "5px 9px 5px 24px", borderRadius: 6, cursor: "pointer", fontSize: 12.5,
                  background: cat === ch.id ? "#eff6ff" : "", color: cat === ch.id ? "#1d4ed8" : "#475569" }}>
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
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="🔍 Поиск товара / артикула…"
            style={{ flex: 1, minWidth: 180, height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 12px", fontSize: 13 }} />
          <span className="muted">Найдено: <b style={{ color: "#1e293b" }}>{count.toLocaleString("ru")}</b></span>
        </div>

        <div className="tablewrap" style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8 }}>
          <table style={{ width: "100%" }}>
            <thead><tr><th>Товар</th><th>Артикул</th><th>Категорія</th><th>Ціна</th><th>Од.</th><th>Залишок</th></tr></thead>
            <tbody>
              {loading && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Загрузка…</td></tr>}
              {!loading && products.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 16 }}>Товаров не найдено</td></tr>}
              {!loading && products.map((p) => (
                <tr key={p.id}>
                  <td style={{ fontWeight: 500 }}>{p.name}</td>
                  <td className="muted">{p.sku}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{p.category_name || "—"}</td>
                  <td>{Number(p.price).toLocaleString("ru")} {p.currency || "грн"}</td>
                  <td>{p.unit}</td>
                  <td><span style={{ color: Number(p.stock) <= 0 ? "#dc2626" : Number(p.stock) < 100 ? "#d97706" : "#16a34a", fontWeight: 600 }}>{Number(p.stock).toLocaleString("ru")}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* пагинация + выбор размера страницы */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: 13 }}>На странице:</span>
          {PAGE_SIZES.map((s) => (
            <button key={s} onClick={() => { setPageSize(s); setPage(1); }}
              style={{ fontSize: 13, padding: "4px 11px", borderRadius: 7, cursor: "pointer",
                border: "1px solid " + (pageSize === s ? "var(--brand)" : "#cbd5e1"),
                background: pageSize === s ? "var(--brand)" : "#fff", color: pageSize === s ? "#fff" : "#475569" }}>{s}</button>
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
            <select value={form.product} onChange={(e) => setForm({ ...form, product: Number(e.target.value) })}
              style={{ width: "100%", height: 38, marginBottom: 10, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }}>
              <option value={0}>— выбери товар (из текущей страницы) —</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name} (остаток {p.stock})</option>)}
            </select>
            <label className="label">Количество</label>
            <input type="number" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
              style={{ width: "100%", height: 38, marginBottom: 10, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            <label className="label">Цена за ед.</label>
            <input type="number" value={form.price} onChange={(e) => setForm({ ...form, price: Number(e.target.value) })}
              style={{ width: "100%", height: 38, marginBottom: 16, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setModal(null)}>Отмена</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={saveDoc}>Провести</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
