/* ============================================================================
 *  ПОВЕРНЕННЯ ТОВАРУ — frontend/src/DealReturnsBlock.tsx  (16.09.2026)
 *  Картка угоди → блок оплати: кнопка «↩ Повернення товару» → форма (які позиції і скільки, причина,
 *  куди товар, фото, хто платить доставку); під нею — список повернень угоди.
 *  Гроші — окремий крок і ЛИШЕ бухгалтер / власник (право deal.refund): повернути з рахунку,
 *  «вже повернуто через LiqPay» або зарахувати в наступне замовлення (аванс клієнта).
 *  API: GET/POST /api/returns/deal/<id>/, POST /api/returns/<id>/photos/, POST /api/returns/<id>/money/.
 * ========================================================================== */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { useLang } from "./i18n";

interface Opt { code: string; label: string }
interface RLine { name: string; unit: string; quantity: number; sold_quantity: number; amount: number; destination: string; destination_label: string }
interface RetErr { id: number; status: string; status_label: string; deduction: number; blamed: string }
interface Ret {
  id: number; created_at: string; created_by: string; reason: string; reason_label: string; amount: number;
  delivery_payer: string; delivery_payer_label: string; delivery_cost: number; comment: string; stock_note: string;
  receipt_doc: { id: number; number: string } | null; lines: RLine[]; photos: { id: number; url: string }[];
  money_status: string; money_label: string; money_due: number; money_amount: number; money_comment: string;
  money_by: string; money_at: string | null; error: RetErr | null; cost_back?: number; cost_loss?: number;
}
interface Item { id: number; name: string; unit: string; quantity: number; price: number; total: number; stock: boolean }
interface St {
  can_register: boolean; can_money: boolean; show_cost: boolean; realized: boolean; items: Item[]; amount: number; paid: number;
  reasons: Opt[]; destinations: Opt[]; payers: Opt[]; error_reasons: string[]; returns: Ret[];
  staff: { id: number; name: string }[]; accounts?: { id: number; name: string }[];
  liqpay_refunds?: { id: number; date: string; amount: number; comment: string }[];
}

const fmt = (n: number) => Number(n || 0).toLocaleString("uk", { maximumFractionDigits: 2 });
const num = (s: string) => parseFloat(String(s || "").replace(",", ".")) || 0;
const newKey = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
const moneyColor: Record<string, [string, string]> = {
  pending: ["#fef3c7", "#92400e"], refund: ["#dcfce7", "#166534"], liqpay: ["#dcfce7", "#166534"],
  offset: ["#dbeafe", "#1d4ed8"], none: ["#f1f5f9", "#475569"],
};
const overlay: any = { position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 70 };
const box: any = { background: "#fff", borderRadius: 14, padding: 18, width: "min(680px, 94vw)", maxHeight: "90vh", overflow: "auto", boxShadow: "0 20px 50px rgba(15,23,42,.25)" };
const inp: any = { height: 32, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px", fontSize: 13, boxSizing: "border-box" };
const chip = (on: boolean): any => ({ padding: "5px 10px", borderRadius: 999, border: "1px solid " + (on ? "#c2410c" : "#cbd5e1"), background: on ? "#fff7ed" : "#fff", color: on ? "#c2410c" : "#334155", fontSize: 12.5, fontWeight: on ? 700 : 500, cursor: "pointer" });

// фото повернення (захищене — через blob із токеном); окремий компонент, не всередині іншого
function Thumb({ url }: { url: string }) {
  const [src, setSrc] = useState("");
  useEffect(() => { let off = false; api.blobUrl(url).then((u) => { if (!off) setSrc(u); }).catch(() => {}); return () => { off = true; }; }, [url]);
  if (!src) return <span style={{ display: "inline-block", width: 46, height: 46, borderRadius: 6, background: "#f1f5f9" }} />;
  return <a href={src} target="_blank" rel="noreferrer"><img src={src} alt="" style={{ width: 46, height: 46, objectFit: "cover", borderRadius: 6, border: "1px solid #e2e8f0" }} /></a>;
}

export default function DealReturnsBlock({ dealId, refreshKey, onChanged }: { dealId: number; refreshKey?: string; onChanged?: () => void }) {
  const { t } = useLang();
  const [st, setSt] = useState<St | null>(null);
  const [open, setOpen] = useState(false);
  const [qty, setQty] = useState<Record<number, string>>({});
  const [dest, setDest] = useState<Record<number, string>>({});
  const [reason, setReason] = useState("");
  const [payer, setPayer] = useState("client");
  const [dcost, setDcost] = useState("");
  const [comment, setComment] = useState("");
  const [blamed, setBlamed] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [money, setMoney] = useState<Ret | null>(null);
  const [mMode, setMMode] = useState("refund");
  const [mAmt, setMAmt] = useState("");
  const [mAcc, setMAcc] = useState("");
  const [mTx, setMTx] = useState("");
  const [mErr, setMErr] = useState("");

  const load = () => api.get<St>(`/api/returns/deal/${dealId}/`).then(setSt).catch(() => setSt(null));
  useEffect(() => { load(); }, [dealId, refreshKey]);
  if (!st) return null;

  function openForm() {
    setQty({}); setDest({}); setReason(""); setPayer("client"); setDcost(""); setComment(""); setBlamed(""); setFiles([]);
    setErr(""); setKey(newKey()); setOpen(true);
  }
  const chosen = (st.items || []).filter((i) => num(qty[i.id]) > 0);
  const approx = chosen.reduce((s, i) => s + Math.min(num(qty[i.id]), i.quantity) * (i.quantity ? i.total / i.quantity : 0), 0);
  const isErr = (st.error_reasons || []).includes(reason);

  async function save() {
    if (!st) return;
    setErr("");
    if (!chosen.length) { setErr(t("Укажите, сколько товара вернулось", "Вкажіть, скільки товару повернулось")); return; }
    const bad = chosen.find((i) => num(qty[i.id]) > i.quantity);
    if (bad) { setErr(t(`«${bad.name}»: не больше ${bad.quantity}`, `«${bad.name}»: не більше ${bad.quantity}`)); return; }
    if (!reason) { setErr(t("Выберите причину", "Оберіть причину")); return; }
    setBusy(true);
    try {
      const r: any = await api.post(`/api/returns/deal/${dealId}/`, {
        client_key: key, reason, delivery_payer: payer, delivery_cost: payer === "us" ? num(dcost) : 0, comment,
        blamed: isErr && blamed ? Number(blamed) : null,
        lines: chosen.map((i) => ({ item: i.id, quantity: num(qty[i.id]), destination: dest[i.id] || "stock" })),
      });
      if (files.length && r?.return?.id) {
        const fd = new FormData();
        files.forEach((f) => fd.append("file", f));
        try { await api.uploadForm(`/api/returns/${r.return.id}/photos/`, fd); }
        catch { alert(t("Возврат сохранён, но фото не загрузились — добавьте их ещё раз в списке возвратов", "Повернення збережено, але фото не завантажились — додайте їх ще раз у списку повернень")); }
      }
      setOpen(false);
      await load();
      onChanged && onChanged();
    } catch (e: any) {
      setErr(e?.data?.detail || e?.message || t("Ошибка", "Помилка"));
    } finally { setBusy(false); }
  }

  async function addPhotos(retId: number, list: FileList | null) {
    if (!list || !list.length) return;
    const fd = new FormData();
    Array.from(list).forEach((f) => fd.append("file", f));
    try { await api.uploadForm(`/api/returns/${retId}/photos/`, fd); load(); }
    catch (e: any) { alert(e?.response?.data?.detail || t("Фото не загрузились", "Фото не завантажились")); }
  }

  function openMoney(r: Ret) {
    setMoney(r); setMMode("refund"); setMAmt(String(r.money_due)); setMAcc(""); setMTx(""); setMErr("");
  }
  async function saveMoney() {
    if (!money) return;
    setMErr("");
    const body: any = { mode: mMode };
    if (mMode === "refund") {
      if (!mAcc) { setMErr(t("Выберите счёт", "Оберіть рахунок")); return; }
      body.amount = num(mAmt); body.account = Number(mAcc);
    }
    if (mMode === "liqpay") {
      if (!mTx) { setMErr(t("Выберите возврат LiqPay", "Оберіть повернення LiqPay")); return; }
      body.tx = Number(mTx);
    }
    setBusy(true);
    try {
      await api.post(`/api/returns/${money.id}/money/`, body);
      setMoney(null);
      await load();
      onChanged && onChanged();
    } catch (e: any) {
      setMErr(e?.data?.detail || e?.message || t("Ошибка", "Помилка"));
    } finally { setBusy(false); }
  }

  const rets = st.returns || [];
  return (
    <div style={{ marginTop: 6 }}>
      {(st.items || []).length > 0 && st.can_register && (
        <button className="btn" style={{ width: "100%", height: 32, background: "#fff", border: "1px solid #fed7aa", color: "#c2410c", fontWeight: 700, fontSize: 12.5 }}
          title={t("Клиент вернул товар: какие позиции и сколько, причина, куда товар, фото. Деньги возвращает только бухгалтер или владелец",
                   "Клієнт повернув товар: які позиції і скільки, причина, куди товар, фото. Гроші повертає лише бухгалтер або власник")}
          onClick={openForm}>↩ {t("Возврат товара", "Повернення товару")}</button>
      )}

      {rets.length > 0 && (
        <div style={{ marginTop: 10, borderTop: "1px solid #f1f5f9", paddingTop: 8 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{t("Возвраты товара", "Повернення товару")}</div>
          {rets.map((r) => {
            const [bg, c] = moneyColor[r.money_status] || moneyColor.none;
            return (
              <div key={r.id} style={{ border: "1px solid #f1f5f9", borderRadius: 10, padding: "8px 10px", marginBottom: 6, fontSize: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "baseline" }}>
                  <b>№{r.id} · {r.reason_label}</b>
                  <b style={{ color: "#c2410c" }}>−{fmt(r.amount)} ₴</b>
                </div>
                <div className="muted" style={{ fontSize: 11 }}>
                  {new Date(r.created_at).toLocaleDateString("uk", { day: "2-digit", month: "2-digit", year: "2-digit" })} · {r.created_by}
                  {r.delivery_payer === "us" ? ` · ${t("доставку возврата платим мы", "доставку повернення платимо ми")}${r.delivery_cost ? ` ${fmt(r.delivery_cost)} ₴` : ""}` : ""}
                </div>
                {r.lines.map((ln, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
                    <span>{ln.name} × {fmt(ln.quantity)} {ln.unit} <span className="muted">· {ln.destination_label.toLowerCase()}</span></span>
                    <span className="muted">−{fmt(ln.amount)} ₴</span>
                  </div>
                ))}
                {r.receipt_doc && <div className="muted" style={{ fontSize: 11 }}>📦 {t("Приход на склад", "Прихід на склад")} {r.receipt_doc.number}</div>}
                {r.stock_note && <div style={{ fontSize: 11, color: "#92400e" }}>⚠ {r.stock_note}</div>}
                {st.show_cost && !!r.cost_loss && <div className="muted" style={{ fontSize: 11 }}>{t("Потеря (брак/списано, по себестоимости)", "Втрата (брак/списано, по собівартості)")}: {fmt(r.cost_loss)} ₴</div>}
                {r.comment && <div className="muted" style={{ fontSize: 11, whiteSpace: "pre-wrap" }}>💬 {r.comment}</div>}
                {r.error && <div style={{ fontSize: 11, color: "#b91c1c" }}>⚠ {t("Ошибка сотрудника", "Помилка співробітника")}: {r.error.blamed || "—"} · {r.error.status_label} · {t("удержание", "утримання")} {fmt(r.error.deduction)} ₴</div>}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4, alignItems: "center" }}>
                  {r.photos.map((p) => <Thumb key={p.id} url={p.url} />)}
                  <label style={{ fontSize: 11, color: "#2563eb", cursor: "pointer" }}>
                    + {t("фото", "фото")}
                    <input type="file" accept="image/*" multiple style={{ display: "none" }} onChange={(e) => { addPhotos(r.id, e.target.files); e.target.value = ""; }} />
                  </label>
                </div>
                <div style={{ marginTop: 5, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                  <span style={{ fontSize: 11.5, fontWeight: 700, background: bg, color: c, borderRadius: 8, padding: "3px 8px" }}>
                    {r.money_label}{r.money_status === "pending" ? ` · ${fmt(r.money_due)} ₴` : (r.money_amount ? ` · ${fmt(r.money_amount)} ₴` : "")}
                  </span>
                  {r.money_status === "pending" && st.can_money && (
                    <button className="btn btn-light" style={{ padding: "2px 10px", fontSize: 11.5 }} onClick={() => openMoney(r)}>💸 {t("Решить по деньгам", "Вирішити по грошах")}</button>
                  )}
                  {r.money_status === "pending" && !st.can_money && (
                    <span className="muted" style={{ fontSize: 11 }}>{t("деньги возвращает бухгалтер или владелец", "гроші повертає бухгалтер або власник")}</span>
                  )}
                </div>
                {r.money_comment && <div className="muted" style={{ fontSize: 11 }}>{r.money_comment}</div>}
              </div>
            );
          })}
        </div>
      )}

      {open && createPortal(
        <div onClick={() => !busy && setOpen(false)} style={overlay}>
          <div onClick={(e) => e.stopPropagation()} style={box}>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 4 }}>↩ {t("Возврат товара", "Повернення товару")}</div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
              {t("Сумма сделки уменьшится на возвращённые позиции. Товар «как новый» CRM сама оприходует на склад. Деньги клиенту возвращает только бухгалтер или владелец.",
                 "Сума угоди зменшиться на повернені позиції. Товар «як новий» CRM сама оприбуткує на склад. Гроші клієнту повертає лише бухгалтер або власник.")}
              {!st.realized && <div style={{ color: "#92400e", marginTop: 4 }}>⚠ {t("Реализации (списания со склада) по сделке нет — склад не изменится.", "Реалізації (списання зі складу) по угоді немає — склад не зміниться.")}</div>}
            </div>

            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>1. {t("Что и сколько вернулось", "Що і скільки повернулось")}</div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead><tr className="muted" style={{ fontSize: 11, textAlign: "left" }}>
                  <th style={{ padding: "4px 6px" }}>{t("Позиция", "Позиція")}</th>
                  <th style={{ padding: "4px 6px", whiteSpace: "nowrap" }}>{t("В сделке", "В угоді")}</th>
                  <th style={{ padding: "4px 6px" }}>{t("Вернули", "Повернули")}</th>
                  <th style={{ padding: "4px 6px" }}>{t("Куда товар", "Куди товар")}</th>
                </tr></thead>
                <tbody>
                  {(st.items || []).map((i) => (
                    <tr key={i.id} style={{ borderTop: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "5px 6px" }}>{i.name}</td>
                      <td style={{ padding: "5px 6px", whiteSpace: "nowrap" }}>{fmt(i.quantity)} {i.unit}</td>
                      <td style={{ padding: "5px 6px" }}>
                        <input type="number" min={0} max={i.quantity} step="any" value={qty[i.id] || ""} placeholder="0"
                          onChange={(e) => setQty({ ...qty, [i.id]: e.target.value })} style={{ ...inp, width: 80 }} />
                      </td>
                      <td style={{ padding: "5px 6px" }}>
                        <select value={dest[i.id] || "stock"} onChange={(e) => setDest({ ...dest, [i.id]: e.target.value })} style={{ ...inp, width: "100%" }} disabled={num(qty[i.id]) <= 0}>
                          {st.destinations.map((d) => <option key={d.code} value={d.code}>{d.label}</option>)}
                        </select>
                        {!i.stock && num(qty[i.id]) > 0 && <div className="muted" style={{ fontSize: 10.5 }}>{t("без складского учёта — склад не меняется", "без складського обліку — склад не змінюється")}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {chosen.length > 0 && <div style={{ fontSize: 12.5, margin: "6px 0 0" }}>{t("Сумма сделки уменьшится примерно на", "Сума угоди зменшиться приблизно на")} <b style={{ color: "#c2410c" }}>{fmt(approx)} ₴</b> <span className="muted">({t("точно — с учётом скидок и минималки", "точно — з урахуванням знижок і мінімалки")})</span></div>}

            <div style={{ fontWeight: 700, fontSize: 13, margin: "14px 0 6px" }}>2. {t("Причина", "Причина")}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {st.reasons.map((r) => <button key={r.code} type="button" style={chip(reason === r.code)} onClick={() => setReason(r.code)}>{r.label}</button>)}
            </div>
            {isErr && (
              <div style={{ marginTop: 8, fontSize: 12, background: "#fef2f2", borderRadius: 8, padding: "8px 10px" }}>
                {t("Будет создана «Ошибка сотрудника» (на рассмотрении, удержание 50% суммы возврата — подтверждает руководитель).",
                   "Буде створено «Помилку співробітника» (на розгляді, утримання 50% суми повернення — підтверджує керівник).")}
                <div style={{ marginTop: 6, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                  <span className="muted">{t("Кто ошибся", "Хто помилився")}:</span>
                  <select value={blamed} onChange={(e) => setBlamed(e.target.value)} style={{ ...inp, minWidth: 200 }}>
                    <option value="">{reason === "wh_error" ? t("— исполнитель отгрузки", "— виконавець відвантаження") : t("— ответственный за сделку", "— відповідальний за угоду")}</option>
                    {(st.staff || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </div>
              </div>
            )}

            <div style={{ fontWeight: 700, fontSize: 13, margin: "14px 0 6px" }}>3. {t("Доставка возврата", "Доставка повернення")}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
              {st.payers.map((p) => <button key={p.code} type="button" style={chip(payer === p.code)} onClick={() => setPayer(p.code)}>{t("Платит", "Платить")}: {p.label.toLowerCase()}</button>)}
              {payer === "us" && <input type="number" min={0} step="any" value={dcost} onChange={(e) => setDcost(e.target.value)} placeholder={t("стоимость, ₴ (если известна)", "вартість, ₴ (якщо відома)")} style={{ ...inp, width: 190 }} />}
            </div>

            <div style={{ fontWeight: 700, fontSize: 13, margin: "14px 0 6px" }}>4. {t("Фото и комментарий", "Фото і коментар")}</div>
            <input type="file" accept="image/*" multiple onChange={(e) => setFiles(Array.from(e.target.files || []).slice(0, 10))} style={{ fontSize: 12 }} />
            {files.length > 0 && <div className="muted" style={{ fontSize: 11 }}>{t("Выбрано фото", "Обрано фото")}: {files.length}</div>}
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} placeholder={t("Что случилось (необязательно)", "Що сталося (необовʼязково)")}
              style={{ width: "100%", marginTop: 6, border: "1px solid #cbd5e1", borderRadius: 8, padding: 8, fontSize: 13, boxSizing: "border-box" }} />

            {err && <div style={{ color: "#b91c1c", fontSize: 12.5, margin: "8px 0", whiteSpace: "pre-wrap" }}>{err}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button className="btn" style={{ flex: 1, height: 38 }} disabled={busy} onClick={() => setOpen(false)}>{t("Отмена", "Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 2, height: 38 }} disabled={busy || !chosen.length || !reason} onClick={save}>
                {busy ? t("Сохраняем…", "Зберігаємо…") : t("Сохранить возврат", "Зберегти повернення")}
              </button>
            </div>
          </div>
        </div>, document.body)}

      {money && createPortal(
        <div onClick={() => !busy && setMoney(null)} style={overlay}>
          <div onClick={(e) => e.stopPropagation()} style={{ ...box, width: "min(460px, 94vw)" }}>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 4 }}>💸 {t("Деньги за возврат", "Гроші за повернення")} №{money.id}</div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
              {t("Клиент переплатил после возврата", "Клієнт переплатив після повернення")}: <b>{fmt(money.money_due)} ₴</b>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 10 }}>
              <label style={{ fontSize: 13 }}><input type="radio" checked={mMode === "refund"} onChange={() => setMMode("refund")} /> {t("Вернуть деньги клиенту (операция в журнале)", "Повернути гроші клієнту (операція в журналі)")}</label>
              {(st.liqpay_refunds || []).length > 0 && <label style={{ fontSize: 13 }}><input type="radio" checked={mMode === "liqpay"} onChange={() => setMMode("liqpay")} /> {t("Уже вернули кнопкой «Вернуть деньги (LiqPay)»", "Вже повернули кнопкою «Повернути кошти (LiqPay)»")}</label>}
              <label style={{ fontSize: 13 }}><input type="radio" checked={mMode === "offset"} onChange={() => setMMode("offset")} /> {t("Зачесть в следующий заказ (аванс клиента)", "Зарахувати в наступне замовлення (аванс клієнта)")}</label>
            </div>
            {mMode === "refund" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>{t("Сумма, ₴ (остаток останется авансом клиента)", "Сума, ₴ (решта лишиться авансом клієнта)")}</div>
                  <input type="number" min={0} max={money.money_due} step="0.01" value={mAmt} onChange={(e) => setMAmt(e.target.value)} style={{ ...inp, width: "100%" }} />
                </div>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>{t("С какого счёта", "З якого рахунку")}</div>
                  <select value={mAcc} onChange={(e) => setMAcc(e.target.value)} style={{ ...inp, width: "100%" }}>
                    <option value="">—</option>
                    {(st.accounts || []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </div>
                <div className="muted" style={{ fontSize: 11 }}>{t("Если возвращаете на карту через LiqPay — нажмите «Вернуть деньги (LiqPay)» (без галочки «Возврат»), потом выберите здесь «Уже вернули».",
                  "Якщо повертаєте на картку через LiqPay — натисніть «Повернути кошти (LiqPay)» (без галочки «Повернення»), потім оберіть тут «Вже повернули».")}</div>
              </div>
            )}
            {mMode === "liqpay" && (
              <select value={mTx} onChange={(e) => setMTx(e.target.value)} style={{ ...inp, width: "100%" }}>
                <option value="">—</option>
                {(st.liqpay_refunds || []).map((x) => <option key={x.id} value={x.id}>{x.date} · {fmt(x.amount)} ₴</option>)}
              </select>
            )}
            {mMode === "offset" && <div style={{ fontSize: 12.5 }}>{t("Деньги остаются у нас как аванс клиента: следующий заказ оплатить «Из аванса клиента».", "Гроші лишаються в нас як аванс клієнта: наступне замовлення оплатити «З авансу клієнта».")}</div>}
            {mErr && <div style={{ color: "#b91c1c", fontSize: 12.5, marginTop: 8 }}>{mErr}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
              <button className="btn" style={{ flex: 1, height: 38 }} disabled={busy} onClick={() => setMoney(null)}>{t("Отмена", "Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 2, height: 38 }} disabled={busy} onClick={saveMoney}>{busy ? t("Сохраняем…", "Зберігаємо…") : t("Подтвердить", "Підтвердити")}</button>
            </div>
          </div>
        </div>, document.body)}
    </div>
  );
}
