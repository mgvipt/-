import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, Funnel, Paginated } from "../api";
import { Avatar } from "../ui";
import ChatPanel from "./ChatPanel";

interface Item { id: number; product: number; product_name: string; quantity: string; price: string; total: string; }
interface Pay { id: number; provider: string; amount: string; is_paid: boolean; created_at: string; }
interface CF { income: number; expense: number; profit: number; margin: number; cogs_planned: number; }
interface Deal {
  id: number; title: string; contact: number | null; contact_name?: string; owner_name?: string;
  funnel: number; stage: number; amount: string; items: Item[]; payments: Pay[]; paid: number; cashflow: CF;
}
interface Product { id: number; name: string; price: string; stock: number; }

export default function DealCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const [deal, setDeal] = useState<Deal | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [addProd, setAddProd] = useState(0);
  const [addQty, setAddQty] = useState(1);
  const [payOpen, setPayOpen] = useState(false);
  const [payAmount, setPayAmount] = useState("");
  const [ttn, setTtn] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    const d = await api.get<Deal>(`/api/deals/${id}/`);
    setDeal(d);
    if (!funnel || funnel.id !== d.funnel) setFunnel(await api.get<Funnel>(`/api/funnels/${d.funnel}/`));
  }
  useEffect(() => { load(); api.get<Paginated<Product>>("/api/products/?page_size=200").then((p) => setProducts(p.results)); }, [id]);

  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(""), 3000); };
  async function setStage(s: number) { await api.patch(`/api/deals/${id}/`, { stage: s }); load(); }
  async function addItem() { if (!addProd) return; setDeal(await api.post<Deal>(`/api/deals/${id}/add_item/`, { product: addProd, quantity: addQty })); setAddProd(0); setAddQty(1); }
  async function removeItem(item: number) { setDeal(await api.post<Deal>(`/api/deals/${id}/remove_item/`, { item })); }
  async function acceptPayment() { setDeal(await api.post<Deal>(`/api/deals/${id}/accept_payment/`, { amount: payAmount || deal?.amount })); setPayOpen(false); setPayAmount(""); flash("✓ Оплата проведена в Финансы"); }
  async function ship() { try { const r = await api.post<any>(`/api/deals/${id}/ship/`, {}); setDeal(r.deal); flash(`✓ Отгружено, себестоимость ${r.cogs} ₴ списана`); } catch { flash("В сделке нет товаров"); } }
  async function createTtn() {
    try { const r = await api.post<any>("/api/integrations/novaposhta/ttn/", { props: {} }); flash(r?.data?.[0]?.IntDocNumber ? `ТТН: ${r.data[0].IntDocNumber}` : "ТТН создана"); }
    catch { flash("Нова Пошта не настроена — задай ключ в Настройках"); }
  }

  if (!deal) return <div className="spin">Загрузка сделки…</div>;
  const curOrder = funnel?.stages.find((s) => s.id === deal.stage)?.order ?? 0;
  const remaining = Number(deal.amount) - deal.paid;
  const cf = deal.cashflow;

  return (
    <div className="scroll fade">
      <div className="dealhead">
        <button className="back" onClick={() => nav("/deals")}>←</button>
        <b style={{ fontSize: 16 }}>{deal.title}</b><span className="muted">{funnel?.name}</span>
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        <button className="btn btn-green" onClick={ship}>📦 Отгрузить</button>
      </div>

      {funnel && (
        <div className="stagebar">
          {funnel.stages.map((s) => (
            <div key={s.id} className="stage" onClick={() => setStage(s.id)} style={{ cursor: "pointer", background: s.order <= curOrder ? "var(--brand)" : "#cbd5e1" }}>{s.name}</div>
          ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "330px 1fr 360px", gap: 14, padding: 14 }}>
        {/* ЛЕВО: клиент, сумма, оплата */}
        <div>
          <div className="panel">
            <div className="label">Клиент</div>
            <div style={{ fontWeight: 600 }}>{deal.contact_name || "Без контакта"}</div>
            <div className="owner" style={{ fontSize: 13, marginTop: 8 }}><Avatar name={deal.owner_name || "—"} /> {deal.owner_name || "—"}</div>
          </div>
          <div className="panel">
            <div className="label">Сумма сделки</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{Number(deal.amount).toLocaleString("ru")} <span className="muted" style={{ fontSize: 14 }}>грн.</span></div>
            <div className="row" style={{ marginTop: 8 }}><span className="muted">Оплачено</span><b style={{ color: "#16a34a" }}>{deal.paid.toLocaleString("ru")} ₴</b></div>
            <div className="row"><span className="muted">Осталось</span><b style={{ color: remaining > 0 ? "#d97706" : "#16a34a" }}>{remaining.toLocaleString("ru")} ₴</b></div>
            <button className="btn btn-primary" style={{ width: "100%", height: 36, marginTop: 10 }} onClick={() => { setPayAmount(String(remaining > 0 ? remaining : deal.amount)); setPayOpen(true); }}>💳 Принять оплату</button>
          </div>
          {/* КЕШФЛОУ прямо в карточке */}
          <div className="panel">
            <div className="label">💰 Кешфлоу сделки</div>
            <div className="row"><span className="muted">Доход</span><b style={{ color: "#16a34a" }}>{cf.income.toLocaleString("ru")} ₴</b></div>
            <div className="row"><span className="muted">Расход (себест.)</span><b style={{ color: "#ef4444" }}>{cf.expense.toLocaleString("ru")} ₴</b></div>
            <div className="row" style={{ borderTop: "1px solid #eef1f5", marginTop: 4, paddingTop: 6 }}><span>Прибыль</span><b style={{ color: cf.profit >= 0 ? "#16a34a" : "#ef4444" }}>{cf.profit.toLocaleString("ru")} ₴</b></div>
            <div className="row"><span className="muted">Маржа</span><b>{cf.margin}%</b></div>
          </div>
          {/* Нова Пошта */}
          <div className="panel">
            <div className="label">📮 Нова Пошта</div>
            <button className="btn btn-light" style={{ width: "100%", marginBottom: 6 }} onClick={createTtn}>Создать ТТН</button>
            <div style={{ display: "flex", gap: 6 }}>
              <input placeholder="Трек по ТТН" value={ttn} onChange={(e) => setTtn(e.target.value)} style={{ flex: 1, height: 32, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13 }} />
              <button className="btn btn-light" onClick={async () => { try { const r = await api.post<any>("/api/integrations/novaposhta/track/", { ttn }); flash(r?.data?.[0]?.Status || "Нет данных"); } catch { flash("Нова Пошта не настроена"); } }}>Трек</button>
            </div>
          </div>
        </div>

        {/* ЦЕНТР: товары */}
        <div>
          <div className="panel">
            <div className="label">Товары в сделке</div>
            <div style={{ display: "flex", gap: 6, margin: "8px 0 12px" }}>
              <select value={addProd} onChange={(e) => setAddProd(Number(e.target.value))} style={{ flex: 1, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px" }}>
                <option value={0}>+ добавить товар…</option>
                {products.map((p) => <option key={p.id} value={p.id}>{p.name} ({Number(p.price).toLocaleString("ru")} ₴, ост. {p.stock})</option>)}
              </select>
              <input type="number" value={addQty} min={1} onChange={(e) => setAddQty(Number(e.target.value))} style={{ width: 60, height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px" }} />
              <button className="btn btn-primary" onClick={addItem}>+</button>
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
        </div>

        {/* ПРАВО: чат с клиентом + AI-РОП */}
        <ChatPanel contactId={deal.contact} />
      </div>

      {payOpen && (
        <div onClick={() => setPayOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 24, width: 340 }}>
            <h3 style={{ marginTop: 0 }}>Принять оплату</h3>
            <input type="number" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} style={{ width: "100%", height: 38, marginBottom: 16, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setPayOpen(false)}>Отмена</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={acceptPayment}>Провести</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
