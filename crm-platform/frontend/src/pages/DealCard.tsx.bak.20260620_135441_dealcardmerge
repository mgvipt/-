import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, Funnel, Paginated } from "../api";
import { Avatar } from "../ui";

interface Item { id: number; product: number; product_name: string; quantity: string; price: string; total: string; }
interface Pay { id: number; provider: string; amount: string; is_paid: boolean; created_at: string; }
interface Deal {
  id: number; title: string; contact_name?: string; owner_name?: string;
  funnel: number; stage: number; amount: string; source: string;
  items: Item[]; payments: Pay[]; paid: number;
}
interface Product { id: number; name: string; price: string; stock: number; }

export default function DealCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const [deal, setDeal] = useState<Deal | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [tab, setTab] = useState<"general" | "items">("general");
  const [addProd, setAddProd] = useState(0);
  const [addQty, setAddQty] = useState(1);
  const [payOpen, setPayOpen] = useState(false);
  const [payAmount, setPayAmount] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    const d = await api.get<Deal>(`/api/deals/${id}/`);
    setDeal(d);
    if (!funnel || funnel.id !== d.funnel) setFunnel(await api.get<Funnel>(`/api/funnels/${d.funnel}/`));
  }
  useEffect(() => { load(); api.get<Paginated<Product>>("/api/products/?page_size=200").then((p) => setProducts(p.results)); }, [id]);

  async function setStage(stageId: number) { await api.patch(`/api/deals/${id}/`, { stage: stageId }); load(); }
  async function addItem() {
    if (!addProd) return;
    setDeal(await api.post<Deal>(`/api/deals/${id}/add_item/`, { product: addProd, quantity: addQty }));
    setAddProd(0); setAddQty(1);
  }
  async function removeItem(item: number) { setDeal(await api.post<Deal>(`/api/deals/${id}/remove_item/`, { item })); }
  async function acceptPayment() {
    setDeal(await api.post<Deal>(`/api/deals/${id}/accept_payment/`, { amount: payAmount || deal?.amount }));
    setPayOpen(false); setPayAmount(""); setMsg("✓ Оплата проведена в финансы");
    setTimeout(() => setMsg(""), 2500);
  }
  async function ship() {
    try { const r = await api.post<any>(`/api/deals/${id}/ship/`, {}); setDeal(r.deal); setMsg(`✓ Отгружено. Себестоимость ${r.cogs} ₴ списана`); }
    catch { setMsg("В сделке нет товаров для отгрузки"); }
    setTimeout(() => setMsg(""), 3000);
  }

  if (!deal) return <div className="spin">Загрузка сделки…</div>;
  const curOrder = funnel?.stages.find((s) => s.id === deal.stage)?.order ?? 0;
  const remaining = Number(deal.amount) - deal.paid;

  return (
    <div className="scroll fade">
      <div className="dealhead">
        <button className="back" onClick={() => nav("/deals")}>←</button>
        <b style={{ fontSize: 16 }}>{deal.title}</b>
        <span className="muted">{funnel?.name}</span>
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        <button className="btn btn-green" onClick={ship}>📦 Отгрузить</button>
      </div>

      {/* кликабельные стадии */}
      {funnel && (
        <div className="stagebar">
          {funnel.stages.map((s) => (
            <div key={s.id} className="stage" onClick={() => setStage(s.id)} style={{ cursor: "pointer", background: s.order <= curOrder ? "var(--brand)" : "#cbd5e1" }}>{s.name}</div>
          ))}
        </div>
      )}

      <div className="tabs">
        <div className={"tab" + (tab === "general" ? " active" : "")} onClick={() => setTab("general")}>Общее</div>
        <div className={"tab" + (tab === "items" ? " active" : "")} onClick={() => setTab("items")}>Товары ({deal.items.length})</div>
      </div>

      <div className="grid2">
        <div>
          <div className="panel">
            <div className="label">Клиент</div>
            <div style={{ fontWeight: 600 }}>{deal.contact_name || "Без контакта"}</div>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button className="btn" style={{ flex: 1, background: "#ecfdf5", color: "#047857" }}>📞 Позвонить</button>
              <button className="btn" style={{ flex: 1, background: "#eff6ff", color: "#1d4ed8" }}>💬 Чат</button>
            </div>
          </div>
          <div className="panel">
            <div className="label">Ответственный</div>
            <div className="owner" style={{ fontSize: 13 }}><Avatar name={deal.owner_name || "—"} />{deal.owner_name || "—"}</div>
          </div>
          <div className="panel">
            <div className="label">Сумма сделки</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{Number(deal.amount).toLocaleString("ru")} <span className="muted" style={{ fontSize: 14 }}>грн.</span></div>
            <div className="row" style={{ marginTop: 8 }}><span className="muted">Оплачено</span><b style={{ color: "#16a34a" }}>{deal.paid.toLocaleString("ru")} ₴</b></div>
            <div className="row"><span className="muted">Осталось</span><b style={{ color: remaining > 0 ? "#d97706" : "#16a34a" }}>{remaining.toLocaleString("ru")} ₴</b></div>
            <button className="btn btn-primary" style={{ width: "100%", height: 36, marginTop: 10 }} onClick={() => { setPayAmount(String(remaining > 0 ? remaining : deal.amount)); setPayOpen(true); }}>💳 Принять оплату</button>
            {deal.payments.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div className="label">История оплат</div>
                {deal.payments.map((p) => (
                  <div key={p.id} className="row"><span className="muted">{new Date(p.created_at).toLocaleDateString("ru")} · {p.provider}</span><b>{Number(p.amount).toLocaleString("ru")} ₴</b></div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div>
          {tab === "general" ? (
            <div className="panel">
              <div className="label">Лента событий</div>
              <div className="muted" style={{ fontSize: 13 }}>Звонки, сообщения и оплаты появятся здесь. Оплаты уже идут в Финансы, отгрузка — в Склад.</div>
            </div>
          ) : (
            <div className="panel">
              <div className="label">Товары в сделке</div>
              <div style={{ display: "flex", gap: 6, margin: "8px 0 12px" }}>
                <select value={addProd} onChange={(e) => setAddProd(Number(e.target.value))} style={{ flex: 1, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px" }}>
                  <option value={0}>+ добавить товар…</option>
                  {products.map((p) => <option key={p.id} value={p.id}>{p.name} ({Number(p.price).toLocaleString("ru")} ₴, ост. {p.stock})</option>)}
                </select>
                <input type="number" value={addQty} min={1} onChange={(e) => setAddQty(Number(e.target.value))} style={{ width: 64, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px" }} />
                <button className="btn btn-primary" onClick={addItem}>Добавить</button>
              </div>
              {deal.items.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>Товаров пока нет.</div> : (
                <table><thead><tr><th>Товар</th><th>Кол-во</th><th>Цена</th><th>Сумма</th><th></th></tr></thead>
                  <tbody>{deal.items.map((it) => (
                    <tr key={it.id}><td>{it.product_name}</td><td>{Number(it.quantity)}</td><td>{Number(it.price).toLocaleString("ru")} ₴</td><td><b>{Number(it.total).toLocaleString("ru")} ₴</b></td>
                      <td><span style={{ color: "#ef4444", cursor: "pointer" }} onClick={() => removeItem(it.id)}>✕</span></td></tr>
                  ))}</tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </div>

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
