/* ============================================================================
 *  ЗВІТ «ПОВЕРНЕННЯ» — frontend/src/ReturnsReport.tsx  (16.09.2026)
 *  Аналітика → Аналітика продажів → вкладка «Повернення»: скільки, чому, по матеріалах, по людях.
 *  API: GET /api/returns/report/?from=YYYY-MM-DD&to=YYYY-MM-DD (право analytics.view).
 * ========================================================================== */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

interface Rep {
  from: string; to: string; show_cost: boolean;
  totals: { count: number; deals: number; amount: number; refunded: number; offset: number; pending: number; loss?: number; delivery_us: number };
  by_reason: { code: string; label: string; count: number; amount: number }[];
  by_destination: { code: string; label: string; lines: number; amount: number }[];
  by_material: { name: string; count: number; amount: number }[];
  by_product: { name: string; unit: string; qty: number; amount: number; count: number }[];
  by_person: { name: string; count: number; amount: number; errors: number }[];
  by_blamed: { name: string; count: number; confirmed: number; deduction: number }[];
  rows: { id: number; date: string; deal_id: number | null; deal_title: string; client: string; manager: string; reason: string; amount: number; money: string; lines: string }[];
}

const fmt = (n: number) => Number(n || 0).toLocaleString("uk", { maximumFractionDigits: 2 });
const iso = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const th: any = { padding: "6px 8px", textAlign: "left", fontSize: 11, color: "#64748b", fontWeight: 600, whiteSpace: "nowrap" };
const td: any = { padding: "6px 8px", borderTop: "1px solid #f1f5f9", fontSize: 12.5 };
const tdr: any = { ...td, textAlign: "right", whiteSpace: "nowrap" };

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="panel" style={{ padding: "10px 12px", minWidth: 150, flex: "1 1 150px" }} title={hint || ""}>
      <div className="muted" style={{ fontSize: 11 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 800 }}>{value}</div>
    </div>
  );
}

function Table({ title, head, rows }: { title: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="panel" style={{ padding: 12, flex: "1 1 320px", minWidth: 0 }}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{title}</div>
      {rows.length === 0 ? <div className="muted" style={{ fontSize: 12 }}>—</div> : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>{head.map((h, i) => <th key={i} style={i ? { ...th, textAlign: "right" } : th}>{h}</th>)}</tr></thead>
            <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} style={j ? tdr : td}>{c}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function ReturnsReport() {
  const { t } = useLang();
  const today = new Date();
  const [from, setFrom] = useState(iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 89)));
  const [to, setTo] = useState(iso(today));
  const [rep, setRep] = useState<Rep | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setErr("");
    api.get<Rep>(`/api/returns/report/?from=${from}&to=${to}`).then(setRep).catch((e: any) => { setRep(null); setErr(e?.data?.detail || t("Нет доступа", "Немає доступу")); });
  }, [from, to]);
  const preset = (days: number) => { const d = new Date(); setTo(iso(d)); setFrom(iso(new Date(d.getFullYear(), d.getMonth(), d.getDate() - days + 1))); };
  const month = () => { const d = new Date(); setFrom(iso(new Date(d.getFullYear(), d.getMonth(), 1))); setTo(iso(d)); };
  const T = rep?.totals;
  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginBottom: 12 }}>
        <button className="btn btn-light" onClick={month}>{t("Этот месяц", "Цей місяць")}</button>
        <button className="btn btn-light" onClick={() => preset(30)}>30 {t("дней", "днів")}</button>
        <button className="btn btn-light" onClick={() => preset(90)}>90 {t("дней", "днів")}</button>
        <button className="btn btn-light" onClick={() => preset(365)}>{t("Год", "Рік")}</button>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px" }} />
        <span className="muted">—</span>
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px" }} />
      </div>
      {err && <div className="muted" style={{ padding: 20 }}>{err}</div>}
      {rep && T && <>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
          <Tile label={t("Возвратов", "Повернень")} value={`${T.count}`} hint={t(`по ${T.deals} сделкам`, `по ${T.deals} угодах`)} />
          <Tile label={t("На сумму (минус к сделкам)", "На суму (мінус до угод)")} value={`${fmt(T.amount)} ₴`} />
          <Tile label={t("Возвращено деньгами", "Повернуто грошима")} value={`${fmt(T.refunded)} ₴`} />
          <Tile label={t("Зачтено в следующий заказ", "Зараховано в наступне замовлення")} value={`${fmt(T.offset)} ₴`} />
          <Tile label={t("Ждёт решения бухгалтера", "Чекає рішення бухгалтера")} value={`${fmt(T.pending)} ₴`} />
          {rep.show_cost && T.loss !== undefined && <Tile label={t("Потери: брак/списано (себест.)", "Втрати: брак/списано (собів.)")} value={`${fmt(T.loss)} ₴`} />}
          <Tile label={t("Доставка возвратов за наш счёт", "Доставка повернень за наш рахунок")} value={`${fmt(T.delivery_us)} ₴`} hint={t("то, что указали в форме возврата", "те, що вказали у формі повернення")} />
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 10 }}>
          <Table title={t("Почему возвращают", "Чому повертають")} head={[t("Причина", "Причина"), t("Возвратов", "Повернень"), "₴"]}
            rows={rep.by_reason.map((r) => [r.label, r.count, fmt(r.amount)])} />
          <Table title={t("Куда пошёл товар", "Куди пішов товар")} head={[t("Куда", "Куди"), t("Позиций", "Позицій"), "₴"]}
            rows={rep.by_destination.map((r) => [r.label, r.lines, fmt(r.amount)])} />
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 10 }}>
          <Table title={t("По материалам", "По матеріалах")} head={[t("Материал (раздел товара)", "Матеріал (розділ товару)"), t("Возвратов", "Повернень"), "₴"]}
            rows={rep.by_material.map((r) => [r.name, r.count, fmt(r.amount)])} />
          <Table title={t("По людям (ответственный за сделку)", "По людях (відповідальний за угоду)")} head={[t("Сотрудник", "Співробітник"), t("Возвратов", "Повернень"), t("Из них ошибки", "З них помилки"), "₴"]}
            rows={rep.by_person.map((r) => [r.name, r.count, r.errors, fmt(r.amount)])} />
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 10 }}>
          <Table title={t("Товары", "Товари")} head={[t("Товар", "Товар"), t("Кол-во", "К-сть"), "₴"]}
            rows={rep.by_product.map((r) => [r.name, `${fmt(r.qty)} ${r.unit}`, fmt(r.amount)])} />
          <Table title={t("Ошибки сотрудников (кто ошибся)", "Помилки співробітників (хто помилився)")} head={[t("Сотрудник", "Співробітник"), t("Случаев", "Випадків"), t("Подтверждено", "Підтверджено"), t("Удержано", "Утримано")]}
            rows={rep.by_blamed.map((r) => [r.name, r.count, r.confirmed, `${fmt(r.deduction)} ₴`])} />
        </div>
        <div className="panel" style={{ padding: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>{t("Все возвраты за период", "Усі повернення за період")}</div>
          {rep.rows.length === 0 ? <div className="muted" style={{ fontSize: 12 }}>{t("Возвратов нет", "Повернень немає")}</div> : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr>
                  <th style={th}>№</th><th style={th}>{t("Дата", "Дата")}</th><th style={th}>{t("Сделка", "Угода")}</th><th style={th}>{t("Клиент", "Клієнт")}</th>
                  <th style={th}>{t("Ответственный", "Відповідальний")}</th><th style={th}>{t("Причина", "Причина")}</th><th style={th}>{t("Товары", "Товари")}</th>
                  <th style={{ ...th, textAlign: "right" }}>₴</th><th style={th}>{t("Деньги", "Гроші")}</th>
                </tr></thead>
                <tbody>{rep.rows.map((r) => (
                  <tr key={r.id}>
                    <td style={td}>{r.id}</td><td style={td}>{r.date.split("-").reverse().join(".")}</td>
                    <td style={td}>{r.deal_id ? <a href={`/deals/${r.deal_id}`}>#{r.deal_id}</a> : "—"}</td>
                    <td style={td}>{r.client}</td><td style={td}>{r.manager}</td><td style={td}>{r.reason}</td>
                    <td style={{ ...td, minWidth: 220 }}>{r.lines}</td><td style={tdr}>{fmt(r.amount)}</td><td style={td}>{r.money}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </>}
    </div>
  );
}
