/* Повна картка операції (як у Журналі), відкривається модалкою ПРЯМО в картці клієнта.
 * Створення нової (дохід / витрата / переказ) + перегляд/редагування + видалення + переробити на переказ + розподіл + чек. */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { useLang } from "./i18n";
import { Attachments, ClientPick, CpField, DealPick } from "./pages/Finance";

const CHANNELS: [string, string][] = [
  ["", "—"], ["instagram", "Instagram"], ["tiktok", "TikTok"], ["facebook", "Facebook"],
  ["site", "Сайт"], ["salon", "Салон (офлайн)"], ["wholesale", "Опт"], ["designers", "Дизайнери/прораби"],
  ["telegram", "Telegram"], ["call", "Дзвінок"], ["other", "Інше"],
];

export default function TxCardModal({ txId, initDirection, initContact, initContactName, onClose, onSaved, nav }: {
  txId?: number; initDirection?: "in" | "out"; initContact?: number; initContactName?: string;
  onClose: () => void; onSaved: () => void; nav?: (p: string) => void;
}) {
  const { t } = useLang();
  const [f, setF] = useState<any>(null);
  const [accs, setAccs] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [dirs, setDirs] = useState<any[]>([]);
  const [arts, setArts] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [convAcc, setConvAcc] = useState(0);
  const [splitOn, setSplitOn] = useState(false);
  const [payerDir, setPayerDir] = useState(0);
  const [splitRows, setSplitRows] = useState<any[]>([]);
  const [asDebt, setAsDebt] = useState(false);   // false = сразу в журнал (оплачено); true = долг (кредиторка/дебиторка)
  const [recvLoan, setRecvLoan] = useState(false);  // для дебиторки (нам винні): false=продаж (буд. дохід), true=позика (свои деньги в долг, НЕ дохід)

  useEffect(() => {
    let ok = true;
    if (txId) {
      api.get<any>(`/api/transactions/${txId}/`).then((tx: any) => {
        if (!ok) return;
        setF({
          id: tx.id, direction: tx.direction, amount: tx.amount, amount_uah: tx.amount_uah, currency: tx.currency || "UAH", rate: tx.rate || 1,
          date: tx.date || "", set_category: tx.category_name || "", counterparty: tx.counterparty || "",
          account: tx.account || 0, transfer_account: tx.transfer_account || 0, transfer_amount: "",
          fin_article: tx.fin_article || 0, fin_direction: tx.fin_direction || 0,
          channel: tx.channel || "", comment: tx.comment || "", deal: tx.deal || 0, deal_title: tx.deal_title || "",
          contact: tx.contact || 0, contact_name: tx.contact_name || "",
        });
        setSplitOn(((tx as any).splits || []).length > 0);
        setSplitRows(((tx as any).splits || []).map((sp: any) => ({ dir: sp.fin_direction || 0, amt: sp.amount })));
        setPayerDir((tx as any).payer_direction || 0);
      }).catch(() => onClose());
    } else {
      setF({
        id: 0, direction: initDirection || "out", amount: "", amount_uah: 0, currency: "UAH", rate: 1,
        date: new Date().toISOString().slice(0, 10), set_category: "", counterparty: "",
        account: 0, transfer_account: 0, transfer_amount: "", fin_article: 0, fin_direction: 0, channel: "", comment: "", deal: 0, deal_title: "",
        contact: initContact || 0, contact_name: initContactName || "",
      });
    }
    api.get<any>("/api/accounts/?page_size=200").then((x: any) => setAccs((x.results || x).filter((a: any) => a.is_active !== false)));
    api.get<any>("/api/categories/?page_size=500").then((x: any) => setCats((x.results || x).filter((c: any) => !c.hidden)));
    api.get<any>("/api/fin-directions/?page_size=100").then((x: any) => setDirs(x.results || x));
    api.get<any>("/api/finmodel-articles/?page_size=300").then((x: any) => setArts(x.results || x));
    return () => { ok = false; };
  }, [txId]); // eslint-disable-line

  async function save() {
    if (!f || busy) return;
    const _amt = Number(String(f.amount).replace(",", "."));
    if (!_amt) { alert(t("Впиши сумму", "Впиши суму")); return; }
    // Кредиторка/дебиторка (как в журнале): не транзакция, а плановый платёж (долг) → в Дт/Кт
    if (!f.id && f.direction !== "transfer" && asDebt) {
      setBusy(true);
      try {
        const catId = (cats.find((c: any) => c.name === f.set_category && c.direction === f.direction) || cats.find((c: any) => c.name === f.set_category) || {}).id || null;
        await api.post("/api/planned-payments/", {
          kind: f.direction === "out" ? "payable" : "receivable",
          amount: _amt, due_date: f.date || new Date().toISOString().slice(0, 10),
          counterparty: f.counterparty, contact: f.contact || null, category: catId,
          account: f.account || null, fin_article: f.fin_article || null,
          fin_direction: f.fin_direction || null, comment: f.comment,
          is_loan: (f.direction === "in" && recvLoan) ? true : false,   // позика (свои деньги в долг) — НЕ считается доходом
        });
        onSaved(); return;
      } catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось сохранить", "Не вдалося зберегти")); setBusy(false); return; }
    }
    let body: any;
    if (f.direction === "transfer") {
      if (!f.account || !f.transfer_account) { alert(t("Выбери оба счёта перевода", "Обери обидва рахунки переказу")); return; }
      if (f.account === f.transfer_account) { alert(t("Счета должны быть разными", "Рахунки мають бути різними")); return; }
      body = {
        direction: "transfer", amount: _amt, account: f.account, transfer_account: f.transfer_account,
        transfer_amount: f.transfer_amount ? Number(String(f.transfer_amount).replace(",", ".")) : null,
        date: f.date || null, comment: f.comment, category: null, fin_article: null, fin_direction: null, channel: "",
      };
    } else {
      if (splitOn) {
        if (!payerDir) { alert(t("Выбери подразделение, чья касса оплатила", "Обери підрозділ, чия каса сплатила")); return; }
        const _ss = splitRows.reduce((a: number, r: any) => a + (Number(r.amt) || 0), 0);
        if (Math.abs(_ss - _amt) > 0.01) { alert(t("Сумма распределения не равна сумме операции", "Сума розподілу не дорівнює сумі операції")); return; }
      }
      body = {
        direction: f.direction, amount: _amt, account: f.account || null, date: f.date || null,
        set_category: f.set_category, counterparty: f.counterparty,
        fin_article: f.fin_article || null, fin_direction: f.fin_direction || null,
        channel: f.channel, comment: f.comment, contact: f.contact || null,
        deal: f.deal || null,
        currency: f.currency || "UAH", rate: Number(f.rate) || 1,
        payer_direction: splitOn ? (payerDir || null) : null,
        splits: splitOn ? splitRows.filter((r: any) => r.dir && Number(r.amt)).map((r: any) => ({ fin_direction: r.dir, set_category: f.set_category, amount: Number(r.amt) })) : [],
      };
    }
    setBusy(true);
    try {
      if (f.id) await api.patch(`/api/transactions/${f.id}/`, body);
      else await api.post(`/api/transactions/`, body);
      onSaved();
    } catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось сохранить", "Не вдалося зберегти")); setBusy(false); }
  }
  async function del() {
    if (!f || !f.id || busy) return;
    if (!confirm(t("Удалить операцию? Это повлияет на остатки и аналитику.", "Видалити операцію? Це вплине на залишки й аналітику."))) return;
    setBusy(true);
    try { await api.del(`/api/transactions/${f.id}/`); onSaved(); }
    catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось удалить", "Не вдалося видалити")); setBusy(false); }
  }
  async function toTransfer() {
    if (!f || !f.id || !convAcc || busy) return;
    setBusy(true);
    try {
      const body: any = { direction: "transfer", category: null, fin_article: null, fin_direction: null, channel: "" };
      if (f.direction === "out") { body.account = f.account; body.transfer_account = convAcc; }
      else { body.account = convAcc; body.transfer_account = f.account; }
      await api.patch(`/api/transactions/${f.id}/`, body);
      onSaved();
    } catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось", "Не вдалося")); setBusy(false); }
  }

  const inp: React.CSSProperties = { height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", width: "100%", marginBottom: 10, fontSize: 13, boxSizing: "border-box" };
  const isTr = f && f.direction === "transfer";
  const color = f && (f.direction === "in" ? "#16a34a" : isTr ? "#6366f1" : "#dc2626");
  const dirLabel = f && (f.direction === "in" ? t("Доход", "Дохід") : isTr ? t("Перевод", "Переказ") : t("Расход", "Витрата"));

  return createPortal((
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2147483000 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 440, maxWidth: "94vw", maxHeight: "90vh", overflowY: "auto" }}>
        {!f ? <div className="muted" style={{ padding: 20 }}>{t("Загрузка…", "Завантаження…")}</div> : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <h3 style={{ margin: 0, flex: 1 }}>{f.id ? <>{t("Операция №", "Операція №")}{f.id} · </> : <>{t("Новая операция · ", "Нова операція · ")}</>}<span style={{ color }}>{dirLabel}</span></h3>
              <button onClick={onClose} title={t("Закрыть", "Закрити")} style={{ border: "none", background: "transparent", fontSize: 22, cursor: "pointer", color: "#94a3b8" }}>×</button>
            </div>

            {!f.id && (
              <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
                {[["in", "💰", t("Доход", "Дохід"), "#16a34a"], ["out", "💸", t("Расход", "Витрата"), "#dc2626"], ["transfer", "⇄", t("Перевод", "Переказ"), "#6366f1"]].map(([k, ic, lb, cl]: any) => (
                  <span key={k} onClick={() => setF({ ...f, direction: k })} style={{ flex: 1, textAlign: "center", padding: "7px 6px", borderRadius: 999, fontSize: 12.5, fontWeight: 700, cursor: "pointer", background: f.direction === k ? cl : "#fff", color: f.direction === k ? "#fff" : "#64748b", border: "1.5px solid " + (f.direction === k ? cl : "#e2e8f0") }}>{ic} {lb}</span>
                ))}
              </div>
            )}

            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ flex: 1 }}>
                <label className="label">{t("Сумма", "Сума")}</label>
                <input type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} style={inp} autoFocus />
              </div>
              <div style={{ width: 92 }}>
                <label className="label">{t("Валюта", "Валюта")}</label>
                <select value={f.currency} onChange={(e) => { const cc = e.target.value; if (cc === "UAH") { setF({ ...f, currency: cc, rate: 1 }); } else { setF({ ...f, currency: cc }); api.get<any>(`/api/finance/fx-rate/?ccy=${cc}`).then((r: any) => { if (r?.rate) setF((x: any) => ({ ...x, currency: cc, rate: r.rate })); }).catch(() => {}); } }} style={inp}>
                  {["UAH", "USD", "EUR", "PLN", "GBP"].map((cc) => <option key={cc} value={cc}>{cc}</option>)}
                </select>
              </div>
            </div>
            {f.currency && f.currency !== "UAH" ? (
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, fontSize: 13 }}>
                <span className="muted">{t("Курс НБУ", "Курс НБУ")}:</span>
                <input type="number" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value })} style={{ width: 90, height: 30, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }} title={t("Курс грн за 1 единицу валюты (можно исправить вручную)", "Курс грн за 1 одиницю валюти (можна виправити вручну)")} />
                <span style={{ fontWeight: 600, color: "#0ea5e9" }}>= {Math.round(Number(f.amount || 0) * (Number(f.rate) || 1)).toLocaleString("ru")} ₴</span>
              </div>
            ) : null}

            <label className="label">{t("Дата операции", "Дата операції")}</label>
            <input type="date" value={f.date || ""} onChange={(e) => setF({ ...f, date: e.target.value })} style={inp} />

            {isTr ? (
              <>
                <label className="label">{t("Со счёта (откуда)", "З рахунку (звідки)")}</label>
                <select value={f.account} onChange={(e) => setF({ ...f, account: Number(e.target.value) })} style={inp}>
                  <option value={0}>—</option>
                  {accs.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
                <label className="label">{t("На счёт (получатель)", "На рахунок (отримувач)")}</label>
                <select value={f.transfer_account} onChange={(e) => setF({ ...f, transfer_account: Number(e.target.value) })} style={inp}>
                  <option value={0}>—</option>
                  {accs.filter((a: any) => a.id !== f.account).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
                <label className="label">{t("Зачислено получателю (если другая валюта)", "Зараховано одержувачу (якщо інша валюта)")}</label>
                <input value={f.transfer_amount} onChange={(e) => setF({ ...f, transfer_amount: e.target.value })} placeholder={t("пусто = та же сумма", "пусто = та ж сума")} style={inp} />
                <div className="muted" style={{ fontSize: 11.5, marginBottom: 8 }}>{t("↔ Перевод не считается ни в доход, ни в расход — только движение между счетами.", "↔ Переказ не рахується ні в дохід, ні у витрати — лише рух між рахунками.")}</div>
              </>
            ) : (
              <>
                <label className="label">{t("Категория", "Категорія")}</label>
                <select value={f.set_category} onChange={(e) => setF({ ...f, set_category: e.target.value })} style={inp}>
                  <option value="">{t("— категория —", "— категорія —")}</option>
                  {cats.filter((c: any) => c.direction === f.direction).map((c: any) => <option key={c.id} value={c.name}>{c.parent ? "└ " : ""}{c.name}</option>)}
                </select>

                <label className="label" title={t("Кто заплатил / кому платим — из базы CRM. Начни вводить имя или телефон.", "Хто заплатив / кому платимо — з бази CRM. Почни вводити імʼя або телефон.")}>{t("Контрагент", "Контрагент")}</label>
                <CpField value={f.counterparty} onChange={(v: string) => setF({ ...f, counterparty: v })} />

                <label className="label">{t("Счёт", "Рахунок")}</label>
                <select value={f.account} onChange={(e) => setF({ ...f, account: Number(e.target.value) })} style={inp}>
                  <option value={0}>—</option>
                  {accs.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>

                <label className="label">{t("Фонд (статья)", "Фонд (стаття)")}</label>
                <select value={f.fin_article} onChange={(e) => setF({ ...f, fin_article: Number(e.target.value) })} style={inp}>
                  <option value={0}>{t("— без фонда —", "— без фонду —")}</option>
                  {arts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>

                <label className="label">{t("Направление", "Напрямок")}</label>
                <select value={f.fin_direction} onChange={(e) => setF({ ...f, fin_direction: Number(e.target.value) })} style={inp}>
                  <option value={0}>{t("— без направления —", "— без напрямку —")}</option>
                  {dirs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>

                {!f.id && (
                  <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
                    <span onClick={() => setAsDebt(false)} style={{ flex: 1, textAlign: "center", padding: "7px 6px", borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: "pointer", background: !asDebt ? (f.direction === "out" ? "#dc2626" : "#16a34a") : "#fff", color: !asDebt ? "#fff" : "#64748b", border: "1.5px solid " + (!asDebt ? (f.direction === "out" ? "#dc2626" : "#16a34a") : "#e2e8f0") }}>{f.direction === "out" ? "💸 " + t("Оплата сейчас", "Оплата зараз") : "💰 " + t("Деньги пришли", "Гроші прийшли")}</span>
                    <span onClick={() => setAsDebt(true)} title={t("Долг: попадёт в Дт/Кт, в журнал — после кнопки «Оплачено»", "Борг: потрапить у Дт/Кт, у журнал — після кнопки «Оплачено»")} style={{ flex: 1, textAlign: "center", padding: "7px 6px", borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: "pointer", background: asDebt ? "#b45309" : "#fff", color: asDebt ? "#fff" : "#64748b", border: "1.5px solid " + (asDebt ? "#b45309" : "#e2e8f0") }}>{f.direction === "out" ? "🕐 " + t("Кредиторка (оплатим позже)", "Кредиторка (оплатимо пізніше)") : "🕐 " + t("Нам должны (дебиторка)", "Нам винні (дебіторка)")}</span>
                  </div>
                )}
                {!f.id && asDebt && f.direction === "in" && (
                  <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
                    <span onClick={() => setRecvLoan(false)} title={t("Клиент должен за товар/услугу — будущая прибыль", "Клієнт винен за товар/послугу — майбутній прибуток")} style={{ flex: 1, textAlign: "center", padding: "6px 6px", borderRadius: 999, fontSize: 11.5, fontWeight: 700, cursor: "pointer", background: !recvLoan ? "#16a34a" : "#fff", color: !recvLoan ? "#fff" : "#64748b", border: "1.5px solid " + (!recvLoan ? "#16a34a" : "#e2e8f0") }}>🛒 {t("Продажа", "Продаж")}</span>
                    <span onClick={() => setRecvLoan(true)} title={t("Я дал свои деньги в долг — возврат НЕ прибыль (не считается доходом)", "Я дав свої гроші в борг — повернення НЕ прибуток (не рахується доходом)")} style={{ flex: 1, textAlign: "center", padding: "6px 6px", borderRadius: 999, fontSize: 11.5, fontWeight: 700, cursor: "pointer", background: recvLoan ? "#7c3aed" : "#fff", color: recvLoan ? "#fff" : "#64748b", border: "1.5px solid " + (recvLoan ? "#7c3aed" : "#e2e8f0") }}>🤝 {t("Заём (в долг)", "Позика (в борг)")}</span>
                  </div>
                )}

                {!asDebt && <div style={{ margin: "2px 0 10px", border: "1px solid #e2e8f0", borderRadius: 10, padding: 10, background: splitOn ? "#fbf7f4" : "#fff" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
                    <input type="checkbox" checked={splitOn} onChange={(e) => { setSplitOn(e.target.checked); if (e.target.checked && splitRows.length === 0) setSplitRows([{ dir: f.fin_direction || 0, amt: f.amount || "" }]); }} style={{ width: 15, height: 15, accentColor: "#C67D5F" }} />
                    🔀 {t("Разделить между подразделениями", "Розподілити між підрозділами")}
                  </label>
                  {splitOn && <div style={{ marginTop: 8 }}>
                    <label className="label">{t("Оплатило подразделение (чья касса)", "Оплатив підрозділ (чия каса)")}</label>
                    <select value={payerDir} onChange={(e) => { const _pd = Number(e.target.value); setPayerDir(_pd); if (_pd && !splitRows.some((r: any) => r.dir === _pd)) setSplitRows((rows: any[]) => [{ dir: _pd, amt: "" }, ...rows]); }} style={inp}>
                      <option value={0}>{t("— выбери подразделение —", "— обери підрозділ —")}</option>
                      {dirs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                    {splitRows.map((r: any, i: number) => (
                      <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6, alignItems: "center" }}>
                        <select value={r.dir} onChange={(e) => { const n = [...splitRows]; n[i] = { ...n[i], dir: Number(e.target.value) }; setSplitRows(n); }} style={{ ...inp, marginBottom: 0, flex: 2 }}>
                          <option value={0}>{t("— подразделение —", "— підрозділ —")}</option>
                          {dirs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                        </select>
                        <input type="number" value={r.amt} onChange={(e) => { const n = [...splitRows]; n[i] = { ...n[i], amt: e.target.value }; setSplitRows(n); }} placeholder={t("сумма", "сума")} style={{ ...inp, marginBottom: 0, width: 104, textAlign: "right" }} />
                        <span onClick={() => setSplitRows(splitRows.filter((_: any, j: number) => j !== i))} style={{ cursor: "pointer", color: "#cbd5e1", fontSize: 16 }}>×</span>
                      </div>
                    ))}
                    {(() => { const _s = splitRows.reduce((a: number, r: any) => a + (Number(r.amt) || 0), 0); const _rem = (Number(f.amount) || 0) - _s; return (
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
                        <span onClick={() => setSplitRows([...splitRows, { dir: 0, amt: "" }])} style={{ cursor: "pointer", color: "#C67D5F", fontSize: 12.5, fontWeight: 700 }}>+ {t("подразделение", "підрозділ")}</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: Math.abs(_rem) < 0.01 ? "#16a34a" : (_rem < 0 ? "#dc2626" : "#b45309") }}>{t("распределено", "розподілено")} {Math.round(_s).toLocaleString("ru")} / {Math.round(Number(f.amount) || 0).toLocaleString("ru")} · {_rem < 0 ? t("перерасход ", "перевитрата ") + Math.round(-_rem).toLocaleString("ru") : t("остаток ", "залишок ") + Math.round(_rem).toLocaleString("ru")}</span>
                      </div>
                    ); })()}
                    <div className="muted" style={{ fontSize: 10.5, marginTop: 5, lineHeight: 1.4 }}>{t("Строка плательщика — его собственная доля (не долг). Долг — только доли других подразделений. Видно в Дт/Кт → Взаиморасчёты.", "Рядок платника — його власна частка (не борг). Борг — тільки частки інших підрозділів. Видно в Дт/Кт → Взаєморозрахунки.")}</div>
                  </div>}
                </div>}

                <label className="label">{t("Канал", "Канал")}</label>
                <select value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })} style={inp}>
                  {CHANNELS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </>
            )}

            <label className="label">{t("Комментарий", "Коментар")}</label>
            <textarea value={f.comment} onChange={(e) => setF({ ...f, comment: e.target.value })} style={{ ...inp, height: 60, padding: "8px 10px", resize: "vertical" }} />

            {!isTr && (
              <div style={{ marginBottom: 10 }}>
                <label className="label" title={t("Привязать операцию к сделке — найди по номеру или названию. «Оплачено» сделки учтёт этот платёж.", "Привʼязати операцію до сделки — знайди за номером або назвою. «Оплачено» сделки врахує цей платіж.")}>{t("Сделка (№ или название)", "Угода (№ або назва)")}</label>
                <DealPick value={f.deal || 0} label={f.deal_title} contact={f.contact || 0} onPick={(did: number, dt: string) => setF({ ...f, deal: did, deal_title: dt })} />
                {f.deal && nav ? <span onClick={() => nav(`/deals/${f.deal}`)} style={{ fontSize: 12, color: "#1d4ed8", cursor: "pointer" }}>↗ {t("Открыть сделку", "Відкрити угоду")}</span> : null}
              </div>
            )}
            {!isTr && (
              <div style={{ marginBottom: 10 }}>
                <label className="label" title={t("Клиент CRM, к которому относятся эти деньги (объект). Контрагент может быть мастером/магазином, а деньги считаются по этому клиенту.", "Клієнт CRM, якого стосуються ці гроші (обʼєкт). Контрагент може бути майстром/магазином, а гроші рахуються по цьому клієнту.")}>{t("Клиент (объект)", "Клієнт (обʼєкт)")}</label>
                <ClientPick value={f.contact} label={f.contact_name} placeholder={t("начни вводить имя или телефон…", "почни вводити імʼя або телефон…")} onPick={(cid: number, nm: string) => setF({ ...f, contact: cid, contact_name: nm })} />
              </div>
            )}

            {f.id ? <div style={{ margin: "6px 0 10px" }}><label className="label">📎 {t("Чек / документы", "Чек / документи")}</label><Attachments txId={f.id} /></div>
              : <div className="muted" style={{ fontSize: 11, margin: "0 0 10px" }}>📎 {t("Сохрани операцию — тогда сможешь прикрепить фото/скан чека.", "Збережи операцію — тоді зможеш прикріпити фото/скан чека.")}</div>}

            {f.id && !isTr && (
              <div style={{ margin: "2px 0 12px", padding: 10, border: "1px solid #ede9fe", borderRadius: 10, background: "#faf8ff" }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: "#6d28d9", marginBottom: 6 }}>⇄ {t("Переделать в перевод между счетами", "Переробити на переказ між рахунками")}</div>
                <div style={{ display: "flex", gap: 6 }}>
                  <select value={convAcc} onChange={(e) => setConvAcc(Number(e.target.value))} style={{ ...inp, marginBottom: 0, flex: 1 }}>
                    <option value={0}>{f.direction === "out" ? t("— на какой счёт перешли деньги —", "— на який рахунок перейшли гроші —") : t("— с какого счёта пришли деньги —", "— з якого рахунку прийшли гроші —")}</option>
                    {accs.filter((a: any) => a.id !== f.account).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                  <button className="btn btn-primary" disabled={!convAcc || busy} style={{ opacity: convAcc ? 1 : 0.5, background: "#7c3aed" }} onClick={toTransfer}>⇄ OK</button>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{t("Категория и фонд очистятся — перевод не считается ни в доход, ни в расход.", "Категорія і фонд очистяться — переказ не рахується ні в дохід, ні у витрату.")}</div>
              </div>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              <button className="btn btn-primary" style={{ flex: 1 }} disabled={busy} onClick={save}>{busy ? "…" : t("Сохранить", "Зберегти")}</button>
              {f.id ? <button className="btn" style={{ background: "#fee2e2", color: "#b91c1c", fontWeight: 700 }} disabled={busy} onClick={del}>{t("Удалить", "Видалити")}</button> : null}
              <button className="btn btn-light" onClick={onClose}>{t("Закрыть", "Закрити")}</button>
            </div>
          </>
        )}
      </div>
    </div>
  ), document.body);
}
