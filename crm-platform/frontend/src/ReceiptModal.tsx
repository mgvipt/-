/* Зеркальна картка ПРИХОДУ (оприбуткування) — відкривається з картки товару, блоку «Прибуткові накладні» і зі сделки.
 * Модалка поверх (не закриває сутність). Постачальник з контрагентів, кілька позицій, оплата/борг → кредиторка. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

interface Row { product: number; product_name: string; qty: string; price: string; q: string; res: any[]; open: boolean; }

export default function ReceiptModal({ productId, productName, dealId, onClose, onSaved }: {
  productId?: number; productName?: string; dealId?: number; onClose: () => void; onSaved?: () => void;
}) {
  const { t } = useLang();
  const [wh, setWh] = useState<number>(0);
  const [rows, setRows] = useState<Row[]>([
    { product: productId || 0, product_name: productName || "", qty: "1", price: "", q: "", res: [], open: false },
  ]);
  const [sup, setSup] = useState<{ id: number; name: string }>({ id: 0, name: "" });
  const [supQ, setSupQ] = useState(""); const [supRes, setSupRes] = useState<any[]>([]); const [supOpen, setSupOpen] = useState(false);
  const [creating, setCreating] = useState(false); const [nc, setNc] = useState({ name: "", edrpou: "", phone: "", iban: "" });
  const [invoice, setInvoice] = useState("");
  const [dt, setDt] = useState(new Date().toISOString().slice(0, 10));
  const [paid, setPaid] = useState(true);   // true = оплачено, false = в долг (кредиторка постачальнику)
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");

  useEffect(() => { api.get<any>("/api/warehouses/").then((d) => { const arr = d.results || d || []; if (arr[0]) setWh(arr[0].id); }).catch(() => {}); }, []);

  // пошук постачальника (контрагенти)
  useEffect(() => {
    const q = supQ.trim(); if (!q || q === sup.name) { setSupRes([]); return; }
    const h = setTimeout(() => api.get<any>(`/api/contacts/?search=${encodeURIComponent(q)}&page_size=8`).then((d) => setSupRes((d.results || d) as any[])).catch(() => setSupRes([])), 250);
    return () => clearTimeout(h);
  }, [supQ, sup.name]);

  function setRow(i: number, patch: Partial<Row>) { setRows((rs) => rs.map((r, j) => j === i ? { ...r, ...patch } : r)); }
  function searchProd(i: number, q: string) {
    setRow(i, { q, open: true, product: 0, product_name: "" });
    if (!q.trim()) { setRow(i, { res: [] }); return; }
    api.get<any>(`/api/products/?search=${encodeURIComponent(q)}&page_size=8`).then((d) => setRow(i, { res: (d.results || d) as any[] })).catch(() => setRow(i, { res: [] }));
  }
  const total = rows.reduce((s, r) => s + (Number(r.qty) || 0) * (Number(String(r.price).replace(",", ".")) || 0), 0);

  async function createSupplier() {
    const nm = nc.name.trim(); if (!nm) { setErr(t("Впиши название поставщика", "Впиши назву постачальника")); return; }
    try {
      const c: any = await api.post("/api/contacts/", { first_name: nm, edrpou: nc.edrpou.trim(), phone: nc.phone.trim(), iban: nc.iban.trim(), source: "supplier" });
      setSup({ id: c.id, name: nm }); setCreating(false); setNc({ name: "", edrpou: "", phone: "", iban: "" }); setErr("");
    } catch (e: any) { setErr(e?.response?.data?.detail || t("Не удалось создать поставщика", "Не вдалося створити постачальника")); }
  }

  async function save() {
    const items = rows.filter((r) => r.product && Number(r.qty) > 0).map((r) => ({ product: r.product, quantity: Number(r.qty), price: Number(String(r.price).replace(",", ".")) || 0 }));
    if (!items.length) { setErr(t("Добавь хотя бы одну позицию с товаром и количеством", "Додай хоча б одну позицію з товаром і кількістю")); return; }
    if (!wh) { setErr(t("Нет склада", "Немає складу")); return; }
    setBusy(true); setErr("");
    try {
      await api.post("/api/stock-documents/", {
        kind: "in", warehouse: wh, comment,
        supplier: sup.id || null, supplier_invoice: invoice, doc_date: dt || null,
        deal: dealId || null, items,
      });
      // в долг → кредиторка постачальнику (ми винні магазину)
      if (!paid && total > 0) {
        await api.post("/api/planned-payments/", {
          kind: "payable", amount: total, due_date: dt || new Date().toISOString().slice(0, 10),
          counterparty: sup.name || "", contact: sup.id || null, comment: (t("Прихід товару", "Прихід товару") + (invoice ? " №" + invoice : "")).slice(0, 255),
        }).catch(() => {});
      }
      onSaved && onSaved(); onClose();
    } catch (e: any) { setErr(e?.response?.data?.detail || t("Не удалось провести приход", "Не вдалося провести прихід")); setBusy(false); }
  }

  const inp: any = { width: "100%", height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", fontSize: 13, boxSizing: "border-box" };
  const lbl: any = { fontSize: 11, color: "#64748b", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".03em", display: "block", margin: "8px 0 3px" };

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, padding: 20, width: 500, maxWidth: "95vw", maxHeight: "92vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
          <h3 style={{ margin: 0, flex: 1 }}>📥 {t("Приход товара (оприходование)", "Прихід товару (оприбуткування)")}</h3>
          <button onClick={onClose} style={{ border: "none", background: "transparent", fontSize: 22, cursor: "pointer", color: "#94a3b8" }}>×</button>
        </div>

        {/* Постачальник */}
        <label style={lbl}>{t("Поставщик (контрагент)", "Постачальник (контрагент)")}</label>
        <div style={{ position: "relative" }}>
          {sup.id ? (
            <div style={{ ...inp, display: "flex", alignItems: "center", background: "#f0fdf4" }}>
              <span style={{ flex: 1, fontWeight: 600 }}>{sup.name}</span>
              <span onClick={() => { setSup({ id: 0, name: "" }); setSupQ(""); }} style={{ cursor: "pointer", color: "#94a3b8" }}>✕</span>
            </div>
          ) : (
            <input value={supQ} onChange={(e) => { setSupQ(e.target.value); setSupOpen(true); }} onFocus={() => setSupOpen(true)} onBlur={() => setTimeout(() => setSupOpen(false), 180)} placeholder={t("имя, ЄДРПОУ, телефон…", "назва, ЄДРПОУ, телефон…")} style={inp} />
          )}
          {supOpen && !sup.id && supRes.length > 0 && (
            <div style={{ position: "absolute", top: 38, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 8px 24px rgba(15,23,42,.15)", zIndex: 20, maxHeight: 200, overflowY: "auto" }}>
              {supRes.map((c) => { const nm = (`${c.first_name || ""} ${c.last_name || ""}`.trim() || c.nickname || c.phone || ("#" + c.id)); return (
                <div key={c.id} onMouseDown={() => { setSup({ id: c.id, name: nm }); setSupOpen(false); }} style={{ padding: "7px 10px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 13 }}>{nm}{c.edrpou ? <span className="muted"> · ЄДРПОУ {c.edrpou}</span> : null}{c.phone ? <span className="muted"> · {c.phone}</span> : null}</div>
              ); })}
            </div>
          )}
        </div>
        {!sup.id && (
          creating ? (
            <div style={{ border: "1px solid #cbd5e1", borderRadius: 10, padding: 10, marginTop: 6, background: "#f8fafc" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#334155", marginBottom: 6 }}>{t("Новый поставщик", "Новий постачальник")}</div>
              <input value={nc.name} onChange={(e) => setNc({ ...nc, name: e.target.value })} placeholder={t("Название / ФИО *", "Назва / ПІБ *")} style={{ ...inp, marginBottom: 6 }} />
              <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
                <input value={nc.edrpou} onChange={(e) => setNc({ ...nc, edrpou: e.target.value })} placeholder="ЄДРПОУ / ІПН" style={inp} />
                <input value={nc.phone} onChange={(e) => setNc({ ...nc, phone: e.target.value })} placeholder={t("телефон", "телефон")} style={inp} />
              </div>
              <input value={nc.iban} onChange={(e) => setNc({ ...nc, iban: e.target.value })} placeholder="IBAN / рахунок" style={{ ...inp, marginBottom: 6 }} />
              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setCreating(false)}>{t("Отмена", "Скасувати")}</button>
                <button className="btn btn-primary" style={{ flex: 1 }} onClick={createSupplier}>{t("Создать и выбрать", "Створити і обрати")}</button>
              </div>
            </div>
          ) : (
            <span onClick={() => { setCreating(true); setNc({ ...nc, name: supQ }); }} style={{ cursor: "pointer", color: "#2563eb", fontSize: 12.5, fontWeight: 600, display: "inline-block", marginTop: 4 }}>+ {t("Создать нового поставщика с реквизитами", "Створити нового постачальника з реквізитами")}</span>
          )
        )}

        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ flex: 1 }}><label style={lbl}>{t("№ накладной", "№ накладної")}</label><input value={invoice} onChange={(e) => setInvoice(e.target.value)} style={inp} /></div>
          <div style={{ width: 150 }}><label style={lbl}>{t("Дата", "Дата")}</label><input type="date" value={dt} onChange={(e) => setDt(e.target.value)} style={inp} /></div>
        </div>

        {/* Позиції */}
        <label style={lbl}>{t("Позиции (товар · кол-во · закупка/ед)", "Позиції (товар · к-сть · закупка/од)")}</label>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6, alignItems: "flex-start" }}>
            <div style={{ flex: 1, position: "relative" }}>
              {r.product ? (
                <div style={{ ...inp, display: "flex", alignItems: "center", background: "#eff6ff" }}><span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 12.5 }}>{r.product_name}</span><span onClick={() => setRow(i, { product: 0, product_name: "", q: "" })} style={{ cursor: "pointer", color: "#94a3b8" }}>✕</span></div>
              ) : (
                <input value={r.q} onChange={(e) => searchProd(i, e.target.value)} onFocus={() => setRow(i, { open: true })} onBlur={() => setTimeout(() => setRow(i, { open: false }), 180)} placeholder={t("товар по названию/артикулу…", "товар за назвою/артикулом…")} style={inp} />
              )}
              {r.open && !r.product && r.res.length > 0 && (
                <div style={{ position: "absolute", top: 38, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 8px 24px rgba(15,23,42,.15)", zIndex: 20, maxHeight: 200, overflowY: "auto" }}>
                  {r.res.map((p) => (
                    <div key={p.id} onMouseDown={() => setRow(i, { product: p.id, product_name: p.name, price: r.price || String(p.cost || p.price || ""), open: false })} style={{ padding: "7px 10px", cursor: "pointer", borderBottom: "1px solid #f1f5f9", fontSize: 12.5 }}>{p.name}{p.sku ? <span className="muted"> · {p.sku}</span> : null}</div>
                  ))}
                </div>
              )}
            </div>
            <input value={r.qty} onChange={(e) => setRow(i, { qty: e.target.value })} type="number" placeholder={t("к-во", "к-сть")} style={{ ...inp, width: 60 }} />
            <input value={r.price} onChange={(e) => setRow(i, { price: e.target.value })} type="number" placeholder={t("закуп", "закуп")} style={{ ...inp, width: 78 }} />
            {rows.length > 1 && <span onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))} style={{ cursor: "pointer", color: "#ef4444", padding: "8px 2px" }}>✕</span>}
          </div>
        ))}
        <span onClick={() => setRows((rs) => [...rs, { product: 0, product_name: "", qty: "1", price: "", q: "", res: [], open: false }])} style={{ cursor: "pointer", color: "#2563eb", fontSize: 13, fontWeight: 600 }}>+ {t("ещё позиция", "ще позиція")}</span>

        {/* Оплата / долг */}
        <label style={lbl}>{t("Оплата поставщику", "Оплата постачальнику")}</label>
        <div style={{ display: "flex", gap: 6 }}>
          <span onClick={() => setPaid(true)} style={{ flex: 1, textAlign: "center", padding: "7px 6px", borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: "pointer", background: paid ? "#16a34a" : "#fff", color: paid ? "#fff" : "#64748b", border: "1.5px solid " + (paid ? "#16a34a" : "#e2e8f0") }}>💸 {t("Оплачено", "Оплачено")}</span>
          <span onClick={() => setPaid(false)} title={t("Создаст кредиторку (мы должны магазину)", "Створить кредиторку (ми винні магазину)")} style={{ flex: 1, textAlign: "center", padding: "7px 6px", borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: "pointer", background: !paid ? "#b45309" : "#fff", color: !paid ? "#fff" : "#64748b", border: "1.5px solid " + (!paid ? "#b45309" : "#e2e8f0") }}>🕐 {t("В долг (кредиторка)", "В борг (кредиторка)")}</span>
        </div>

        <label style={lbl}>{t("Комментарий", "Коментар")}</label>
        <textarea value={comment} onChange={(e) => setComment(e.target.value)} style={{ ...inp, height: 46, padding: "8px 10px", resize: "vertical" }} />

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", margin: "12px 0 4px" }}>
          <b style={{ fontSize: 15 }}>{t("Сумма прихода", "Сума приходу")}: {total.toLocaleString("ru")} ₴</b>
        </div>
        {err && <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 6 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>{t("Отмена", "Скасувати")}</button>
          <button className="btn btn-primary" style={{ flex: 2 }} disabled={busy} onClick={save}>{busy ? "…" : t("📥 Провести приход", "📥 Провести прихід")}</button>
        </div>
      </div>
    </div>
  );
}
