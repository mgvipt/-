/* Повна картка операції (як у Журналі), відкривається модалкою ПРЯМО в картці клієнта.
 * Створення нової + перегляд/редагування + видалення + переказ + розподіл між підрозділами + чек. */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { useLang } from "./i18n";
import { Attachments } from "./pages/Finance";

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

  useEffect(() => {
    let ok = true;
    if (txId) {
      api.get<any>(`/api/transactions/${txId}/`).then((tx: any) => {
        if (!ok) return;
        setF({
          id: tx.id, direction: tx.direction, amount: tx.amount, amount_uah: tx.amount_uah, currency: tx.currency || "UAH", rate: tx.rate || 1,
          date: tx.date || "", set_category: tx.category_name || "", counterparty: tx.counterparty || "",
          account: tx.account || 0, fin_article: tx.fin_article || 0, fin_direction: tx.fin_direction || 0,
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
        account: 0, fin_article: 0, fin_direction: 0, channel: "", comment: "", deal: 0, deal_title: "",
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
    if (splitOn) {
      if (!payerDir) { alert(t("Выбери подразделение, чья касса оплатила", "Обери підрозділ, чия каса сплатила")); return; }
      const _ss = splitRows.reduce((a: number, r: any) => a + (Number(r.amt) || 0), 0);
      if (Math.abs(_ss - _amt) > 0.01) { alert(t("Сумма распределения не равна сумме операции", "Сума розподілу не дорівнює сумі операції")); return; }
    }
    setBusy(true);
    const body: any = {
      direction: f.direction, amount: _amt, account: f.account || null, date: f.date || null,
      set_category: f.set_category, counterparty: f.counterparty,
      fin_article: f.fin_article || null, fin_direction: f.fin_direction || null,
      channel: f.channel, comment: f.comment, contact: f.contact || null,
      currency: f.currency || "UAH", rate: Number(f.rate) || 1,
      payer_direction: splitOn ? (payerDir || null) : null,
      splits: splitOn ? splitRows.filter((r: any) => r.dir && Number(r.amt)).map((r: any) => ({ fin_direction: r.dir, set_category: f.set_category, amount: Number(r.amt) })) : [],
    };
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
  const color = f && (f.direction === "in" ? "#16a34a" : f.direction === "transfer" ? "#6366f1" : "#dc2626");
  const dirLabel = f && (f.direction === "in" ? t("Доход", "Дохід") : f.direction === "transfer" ? t("Перевод", "Переказ") : t("Расход", "Витрата"));

  return createPortal((
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2147483000 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 440, maxWidth: "94vw", maxHeight: "90vh", overflowY: "auto" }}>
        {!f ? <div className="muted" style={{ padding: 20 }}>{t("Загрузка…", "Завантаження…")}</div> : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <h3 style={{ margin: 0, flex: 1 }}>{f.id ? <>{t("Операция №", "Операція №")}{f.id} · </> : <>{t("Новая операция · ", "Нова операція · ")}</>}<span style={{ color }}>{dirLabel}</span></h3>
              <button onClick={onClose} title={t("Закрыть", "Закрити")} style={{ border: "none", background: "transparent", fontSize: 22, cursor: "pointer", color: "#94a3b8" }}>×</button>
            </div>

            {f.direction === "transfer" ? (
              <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>{t("Это перевод между счетами — редактируется в Журнале.", "Це переказ між рахунками — редагується в Журналі.")}</div>
            ) : (
              <>
                <label className="label">{t("Сумма, ₴", "Сума, ₴")}</label>
                <input type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} style={inp} autoFocus />
                {f.currency && f.currency !== "UAH" ? <div className="muted" style={{ fontSize: 12, marginTop: -6, marginBottom: 10 }}>{f.currency} · = {Math.round(Number(f.amount_uah || 0)).toLocaleString("ru")} ₴</div> : null}

                <label className="label">{t("Дата операции", "Дата операції")}</label>
                <input type="date" value={f.date || ""} onChange={(e) => setF({ ...f, date: e.target.value })} style={inp} />

                <label className="label">{t("Категория", "Категорія")}</label>
                <select value={f.set_category} onChange={(e) => setF({ ...f, set_category: e.target.value })} style={inp}>
                  <option value="">{t("— категория —", "— категорія —")}</option>
                  {cats.filter((c: any) => c.direction === f.direction).map((c: any) => <option key={c.id} value={c.name}>{c.parent ? "└ " : ""}{c.name}</option>)}
                </select>

                <label className="label">{t("Контрагент", "Контрагент")}</label>
                <input value={f.counterparty} onChange={(e) => setF({ ...f, counterparty: e.target.value })} style={inp} placeholder={t("Мастер / магазин / клиент", "Майстер / магазин / клієнт")} />

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

                <div style={{ margin: "2px 0 10px", border: "1px solid #e2e8f0", borderRadius: 10, padding: 10, background: splitOn ? "#fbf7f4" : "#fff" }}>
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
                </div>

                <label className="label">{t("Канал", "Канал")}</label>
                <select value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })} style={inp}>
                  {CHANNELS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </>
            )}

            <label className="label">{t("Комментарий", "Коментар")}</label>
            <textarea value={f.comment} onChange={(e) => setF({ ...f, comment: e.target.value })} style={{ ...inp, height: 60, padding: "8px 10px", resize: "vertical" }} />

            {f.deal ? (
              <div style={{ marginBottom: 10, fontSize: 13 }}>
                <span className="muted">{t("Сделка:", "Угода:")} </span>
                <a onClick={() => nav && nav(`/deals/${f.deal}`)} style={{ color: "#1d4ed8", cursor: "pointer", fontWeight: 600 }} title={t("Открыть сделку", "Відкрити угоду")}>№{f.deal}{f.deal_title ? " · " + f.deal_title : ""}</a>
              </div>
            ) : null}
            {f.contact ? <div style={{ marginBottom: 10, fontSize: 13 }}><span className="muted">{t("Клиент:", "Клієнт:")} </span><b>{f.contact_name}</b></div> : null}

            {f.id ? <div style={{ margin: "6px 0 10px" }}><label className="label">📎 {t("Чек / документы", "Чек / документи")}</label><Attachments txId={f.id} /></div>
              : <div className="muted" style={{ fontSize: 11, margin: "0 0 10px" }}>📎 {t("Сохрани операцию — тогда сможешь прикрепить фото/скан чека.", "Збережи операцію — тоді зможеш прикріпити фото/скан чека.")}</div>}

            {f.id && f.direction !== "transfer" && (
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
              {f.direction !== "transfer" && <button className="btn btn-primary" style={{ flex: 1 }} disabled={busy} onClick={save}>{busy ? "…" : t("Сохранить", "Зберегти")}</button>}
              {f.id ? <button className="btn" style={{ background: "#fee2e2", color: "#b91c1c", fontWeight: 700 }} disabled={busy} onClick={del}>{t("Удалить", "Видалити")}</button> : null}
              <button className="btn btn-light" onClick={onClose}>{t("Закрыть", "Закрити")}</button>
            </div>
          </>
        )}
      </div>
    </div>
  ), document.body);
}
