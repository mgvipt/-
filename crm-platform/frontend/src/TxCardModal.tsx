/* Картка операції (як у Журналі), але відкривається модалкою прямо в картці клієнта —
 * без переходу на список журналу. Перегляд + редагування основних полів + видалення. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

const CHANNELS: [string, string][] = [
  ["", "—"], ["instagram", "Instagram"], ["tiktok", "TikTok"], ["facebook", "Facebook"],
  ["site", "Сайт"], ["salon", "Салон (офлайн)"], ["wholesale", "Опт"], ["designers", "Дизайнери/прораби"],
  ["telegram", "Telegram"], ["call", "Дзвінок"], ["other", "Інше"],
];

export default function TxCardModal({ txId, onClose, onSaved, nav }: {
  txId: number; onClose: () => void; onSaved: () => void; nav?: (p: string) => void;
}) {
  const { t } = useLang();
  const [f, setF] = useState<any>(null);
  const [accs, setAccs] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [dirs, setDirs] = useState<any[]>([]);
  const [arts, setArts] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let ok = true;
    api.get<any>(`/api/transactions/${txId}/`).then((tx: any) => {
      if (!ok) return;
      setF({
        id: tx.id, direction: tx.direction, amount: tx.amount, amount_uah: tx.amount_uah, currency: tx.currency || "UAH",
        date: tx.date || "", set_category: tx.category_name || "", counterparty: tx.counterparty || "",
        account: tx.account || 0, fin_article: tx.fin_article || 0, fin_direction: tx.fin_direction || 0,
        channel: tx.channel || "", comment: tx.comment || "", deal: tx.deal || 0, deal_title: tx.deal_title || "",
        contact: tx.contact || 0, contact_name: tx.contact_name || "",
      });
    }).catch(() => onClose());
    api.get<any>("/api/accounts/?page_size=200").then((x: any) => setAccs((x.results || x).filter((a: any) => a.is_active !== false)));
    api.get<any>("/api/categories/?page_size=500").then((x: any) => setCats((x.results || x).filter((c: any) => !c.hidden)));
    api.get<any>("/api/fin-directions/?page_size=100").then((x: any) => setDirs(x.results || x));
    api.get<any>("/api/finmodel-articles/?page_size=300").then((x: any) => setArts(x.results || x));
    return () => { ok = false; };
  }, [txId]); // eslint-disable-line

  async function save() {
    if (!f || busy) return;
    setBusy(true);
    try {
      await api.patch(`/api/transactions/${f.id}/`, {
        amount: Number(String(f.amount).replace(",", ".")), date: f.date || null,
        set_category: f.set_category, counterparty: f.counterparty,
        account: f.account || null, fin_article: f.fin_article || null, fin_direction: f.fin_direction || null,
        channel: f.channel, comment: f.comment,
      });
      onSaved();
    } catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось сохранить", "Не вдалося зберегти")); }
    finally { setBusy(false); }
  }
  async function del() {
    if (!f || busy) return;
    if (!confirm(t("Удалить операцию? Это повлияет на остатки и аналитику.", "Видалити операцію? Це вплине на залишки й аналітику."))) return;
    setBusy(true);
    try { await api.del(`/api/transactions/${f.id}/`); onSaved(); }
    catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось удалить", "Не вдалося видалити")); setBusy(false); }
  }

  const inp: React.CSSProperties = { height: 36, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", width: "100%", marginBottom: 10, fontSize: 13, boxSizing: "border-box" };
  const color = f && (f.direction === "in" ? "#16a34a" : f.direction === "transfer" ? "#6366f1" : "#dc2626");

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2147483000 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 440, maxWidth: "94vw", maxHeight: "90vh", overflowY: "auto" }}>
        {!f ? <div className="muted" style={{ padding: 20 }}>{t("Загрузка…", "Завантаження…")}</div> : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <h3 style={{ margin: 0, flex: 1 }}>{t("Операция №", "Операція №")}{f.id} · <span style={{ color }}>{f.direction === "in" ? t("Доход", "Дохід") : f.direction === "transfer" ? t("Перевод", "Переказ") : t("Расход", "Витрата")}</span></h3>
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

            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              {f.direction !== "transfer" && <button className="btn btn-primary" style={{ flex: 1 }} disabled={busy} onClick={save}>{busy ? "…" : t("Сохранить", "Зберегти")}</button>}
              <button className="btn" style={{ background: "#fee2e2", color: "#b91c1c", fontWeight: 700 }} disabled={busy} onClick={del}>{t("Удалить", "Видалити")}</button>
              <button className="btn btn-light" onClick={onClose}>{t("Закрыть", "Закрити")}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
