import { useEffect, useState } from "react";
import { api, Paginated } from "../api";

interface Product { id: number; name: string; sku: string; unit: string; price: string; cost: string; stock: number; }
interface WH { id: number; name: string; is_default: boolean; }

export default function Warehouse() {
  const [products, setProducts] = useState<Product[]>([]);
  const [whs, setWhs] = useState<WH[]>([]);
  const [modal, setModal] = useState<null | "in" | "out">(null);
  const [form, setForm] = useState({ product: 0, quantity: 1, price: 0 });

  async function load() {
    const [p, w] = await Promise.all([
      api.get<Paginated<Product>>("/api/products/?page_size=200"),
      api.get<Paginated<WH>>("/api/warehouses/"),
    ]);
    setProducts(p.results); setWhs(w.results);
  }
  useEffect(() => { load(); }, []);

  async function saveDoc() {
    if (!form.product) return;
    await api.post("/api/stock-documents/", {
      kind: modal, warehouse: whs[0]?.id,
      items: [{ product: form.product, quantity: form.quantity, price: form.price }],
    });
    setModal(null); setForm({ product: 0, quantity: 1, price: 0 });
    load();
  }

  const totalStock = products.reduce((a, p) => a + Number(p.stock), 0);

  return (
    <div className="scroll pad fade">
      <div className="toolbar" style={{ borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 12, background: "#fff" }}>
        <button className="btn btn-primary" onClick={() => setModal("in")}>📥 Приход</button>
        <button className="btn btn-light" onClick={() => setModal("out")}>📤 Расход</button>
        <div className="spacer" />
        <span className="muted">Всего на складе: <b style={{ color: "#1e293b" }}>{totalStock.toLocaleString("ru")} ед.</b></span>
      </div>

      <div className="tablewrap">
        <table>
          <thead><tr><th>Товар</th><th>Артикул</th><th>Цена</th><th>Себест.</th><th>Остаток</th><th>Ед.</th></tr></thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id}>
                <td style={{ fontWeight: 500 }}>{p.name}</td>
                <td className="muted">{p.sku}</td>
                <td>{Number(p.price).toLocaleString("ru")} грн</td>
                <td className="muted">{Number(p.cost).toLocaleString("ru")} грн</td>
                <td><span style={{ color: Number(p.stock) < 100 ? "#d97706" : "#1e293b", fontWeight: 600 }}>{Number(p.stock).toLocaleString("ru")}</span></td>
                <td>{p.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="note">📦 Партионный учёт: приход создаёт остаток с себестоимостью, расход списывает. Себестоимость уходит в Финансы для расчёта маржи.</div>

      {modal && (
        <div onClick={() => setModal(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 24, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>{modal === "in" ? "Приходная накладная" : "Расходная накладная"}</h3>
            <label className="label">Товар</label>
            <select value={form.product} onChange={(e) => setForm({ ...form, product: Number(e.target.value) })}
              style={{ width: "100%", height: 38, marginBottom: 10, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }}>
              <option value={0}>— выбери товар —</option>
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
