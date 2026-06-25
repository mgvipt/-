/* ============================================================================
 *  АНАЛИТИКА  —  frontend/src/pages/Analytics.tsx
 *  Две вкладки: ПРОДАЖІ (воронка, KPI, топ менеджеров) и СКЛАД (стоимость
 *  запасов по закупке/рознице, потенц. маржа, по категориям).
 *  Документация: docs/CODEMAP.md разд.3.
 * ========================================================================== */
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { useAuth } from "../auth";

/* ─── ТИПЫ ─────────────────────────────────────────────────────────────── */
interface SalesData {
  leads_total: number; deals_total: number; conversion: number; revenue: number; avg_check: number;
  funnel: string; stages: { name: string; color: string; count: number; amount: number }[];
  managers: { name: string; deals: number; sum: number }[];
  funnels: { id: number; name: string }[];
}
interface InvData {
  total_items: number; in_stock: number; out_stock: number; total_qty: number;
  value_cost: number; value_retail: number; potential_margin: number;
  by_category: { name: string; items: number; qty: number; cost: number; retail: number }[];
}
const fmt = (n: number) => Math.round(n || 0).toLocaleString("ru");

export default function Analytics() {
  const [tab, setTab] = useState<"sales" | "channels" | "stock">("sales");
  const { t } = useLang();
  return (
    <div className="scroll pad fade">
      <div className="tabline" style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <button className={tab === "sales" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("sales")}>📈 {t("Продажи","Продажі")}</button>
        <button className={tab === "channels" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("channels")}>📣 {t("Каналы","Канали")}</button>
        <button className={tab === "stock" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("stock")}>📦 {t("Склад","Склад")}</button>
      </div>
      {tab === "sales" && <SalesTab />}
      {tab === "channels" && <ChannelsTab />}
      {tab === "stock" && <StockTab />}
    </div>
  );
}

/* ─── ВКЛАДКА КАНАЛИ ───────────────────────────────────────────────────── */
const CH_COLOR: Record<string, string> = {
  instagram: "#e1306c", facebook: "#1877f2", telegram: "#27a7e7", viber: "#7d4fc4",
  whatsapp: "#25d366", call: "#16a34a", google_business: "#ea4335", site: "#0ea5e9",
  wholesale: "#7c3aed", designers: "#d97706", tiktok: "#111", other: "#94a3b8",
};
function ChannelsTab() {
  const { t } = useLang();
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.get<any>("/api/finance/channels/").then(setD).catch(() => setD({ rows: [], total_revenue: 0 })); }, []);
  if (!d) return <div className="spin">{t("Загрузка…","Завантаження…")}</div>;
  return (
    <div className="panel" style={{ margin: 0 }}>
      <b style={{ fontSize: 14 }}>{t("Доход по каналам · какой канал растит доход","Дохід по каналах · який канал росте дохід")} (маржа {d.margin_pct}%)</b>
      <table style={{ width: "100%", marginTop: 8, fontSize: 13 }}>
        <thead><tr><th>{t("Канал","Канал")}</th><th>{t("Выручка","Виручка")}</th><th>{t("Доля","Частка")}</th><th>{t("Сделок","Угод")}</th><th>{t("Сред.чек","Сер.чек")}</th><th>Spend</th><th>ROAS</th><th>{t("Чистый вклад","Чистий внесок")}</th></tr></thead>
        <tbody>
          {d.rows.length === 0 && <tr><td colSpan={8} className="muted" style={{ padding: 14 }}>{t("Пока нет выигранных сделок за период. Канал берётся из Deal.source.","Поки немає виграних угод за період. Канал береться з Deal.source.")}</td></tr>}
          {d.rows.map((r: any) => (
            <tr key={r.source} style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td><span style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: CH_COLOR[r.source] || "#94a3b8", marginRight: 7 }} />{r.label}</td>
              <td style={{ textAlign: "right", fontWeight: 600 }}>{fmt(r.revenue)} ₴</td>
              <td style={{ textAlign: "right" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end" }}>
                  <div style={{ width: 50, height: 6, background: "#f1f5f9", borderRadius: 3 }}><div style={{ width: `${r.share}%`, height: "100%", background: CH_COLOR[r.source] || "#94a3b8", borderRadius: 3 }} /></div>
                  {r.share}%
                </div>
              </td>
              <td style={{ textAlign: "right" }}>{r.deals}</td>
              <td style={{ textAlign: "right" }}>{fmt(r.avg_check)} ₴</td>
              <td style={{ textAlign: "right" }} className="muted">{r.spend ? fmt(r.spend) + " ₴" : "—"}</td>
              <td style={{ textAlign: "right", fontWeight: 600, color: r.roas ? "#16a34a" : "#94a3b8" }}>{r.roas ? "×" + r.roas : "—"}</td>
              <td style={{ textAlign: "right", color: r.net >= 0 ? "#16a34a" : "#dc2626" }}>{fmt(r.net)} ₴</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>📣 {t("Канал = источник сделки (Instagram/Facebook/Сайт/Опт/Дизайнеры/TikTok/Telegram). «Чистый вклад» = выручка×маржа − реклама — показывает какой канал реально даёт прибыль. Spend/ROAS — введи рекламу в Настройках или авто из Meta-ads.","Канал = джерело сделки (Instagram/Facebook/Сайт/Опт/Дизайнери/TikTok/Telegram). «Чистий внесок» = виручка×маржа − реклама — показує який канал реально дає прибуток. Spend/ROAS — введи рекламу в Налаштування або авто з Meta-ads.")}</div>
    </div>
  );
}

/* ─── ВКЛАДКА ПРОДАЖІ ──────────────────────────────────────────────────── */
function SalesTab() {
  const { t } = useLang();
  const [d, setD] = useState<SalesData | null>(null);
  const [fid, setFid] = useState("");
  useEffect(() => { api.get<SalesData>(`/api/analytics/${fid ? "?funnel=" + fid : ""}`).then(setD); }, [fid]);
  if (!d) return <div className="spin">{t("Загрузка аналитики…","Завантаження аналітики…")}</div>;
  const maxCount = Math.max(...d.stages.map((s) => s.count), 1);
  const cards: [string, string][] = [
    [t("Лидов всего","Лідів усього"), fmt(d.leads_total)], [t("Сделок","Угод"), fmt(d.deals_total)],
    [t("Конверсия","Конверсія"), d.conversion + "%"], [t("Выручка (won)","Виручка (won)"), fmt(d.revenue) + " ₴"],
    [t("Средний чек","Середній чек"), fmt(d.avg_check) + " ₴"],
  ];
  return (
    <>
      <div className="toolbar" style={{ borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 12, background: "#fff" }}>
        <span className="muted">{t("Воронка:","Воронка:")}</span>
        <select value={fid} onChange={(e) => setFid(e.target.value)}>
          <option value="">{t("Все продажи","Усі продажі")}</option>
          {d.funnels.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginBottom: 14 }}>
        {cards.map(([lbl, v]) => <div key={lbl} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{lbl}</div><div style={{ fontSize: 22, fontWeight: 700 }}>{v}</div></div>)}
      </div>
      <div className="panel" style={{ margin: 0, marginBottom: 12 }}>
        <b style={{ fontSize: 14 }}>{t("Воронка продаж","Воронка продажів")} {d.funnel && `· ${d.funnel}`}</b>
        <div style={{ marginTop: 12 }}>
          {d.stages.map((s) => (
            <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
              <span style={{ width: 180, fontSize: 12.5, color: "#475569" }}>{s.name}</span>
              <div style={{ flex: 1, height: 24, background: "#f1f5f9", borderRadius: 5 }}>
                <div style={{ width: `${(s.count / maxCount) * 100}%`, minWidth: 28, height: "100%", background: s.color, borderRadius: 5, color: "#fff", fontSize: 11, display: "flex", alignItems: "center", paddingLeft: 8 }}>{s.count}</div>
              </div>
              <span className="muted" style={{ width: 110, textAlign: "right", fontSize: 12 }}>{fmt(s.amount)} ₴</span>
            </div>
          ))}
        </div>
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <b style={{ fontSize: 14 }}>{t("Топ менеджеров","Топ менеджерів")}</b>
        <table style={{ marginTop: 8 }}><thead><tr><th>{t("Менеджер","Менеджер")}</th><th>{t("Сделок","Угод")}</th><th>{t("Сумма","Сума")}</th></tr></thead>
          <tbody>{d.managers.map((m, i) => <tr key={i}><td>{m.name.trim() || "—"}</td><td>{m.deals}</td><td><b>{fmt(m.sum)} ₴</b></td></tr>)}</tbody>
        </table>
      </div>

      {/* ── КАНАЛИ (джерела лідів і сделок) ── */}
      <div className="panel" style={{ margin: 0, marginTop: 12 }}>
        <b style={{ fontSize: 14 }}>📣 {t("Каналы — источники лидов и сделок","Канали — джерела лідів і сделок")}</b>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>{t("Канал","Канал")}</th><th>{t("Лиды","Ліди")}</th><th>{t("Сделок","Угод")}</th><th>{t("Выиграно","Виграно")}</th><th>{t("Конверсия","Конверсія")}</th><th>{t("Выручка","Виручка")}</th></tr></thead>
          <tbody>{((d as any).channels || []).map((c: any, i: number) => (
            <tr key={i}>
              <td><span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 9, height: 9, borderRadius: "50%", background: CH_COLOR[c.source] || "#94a3b8" }} />{c.label}</span></td>
              <td>{c.leads || 0}</td>
              <td>{c.deals}</td>
              <td>{c.won}</td>
              <td><b style={{ color: c.conversion >= 30 ? "#16a34a" : c.conversion >= 10 ? "#d97706" : "#64748b" }}>{c.conversion}%</b></td>
              <td><b>{fmt(c.revenue)} ₴</b></td>
            </tr>
          ))}</tbody>
        </table>
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{t("Живые лиды (Instagram / Telegram / Facebook) падают по источникам автоматически. «Лиды» — новые обращения, «Сделок/Выиграно» — за всё время. Конверсия = выиграно / (выиграно + проиграно).","Живі ліди (Instagram / Telegram / Facebook) падають по джерелах автоматично. «Ліди» — нові звернення, «Сделок/Виграно» — за весь час. Конверсія = виграно / (виграно + програно).")}</div>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА СКЛАД ────────────────────────────────────────────────────── */
function StockTab() {
  const { t } = useLang();
  const { can } = useAuth();
  const showCost = can("product.cost.view");
  const [d, setD] = useState<InvData | null>(null);
  useEffect(() => { api.get<InvData>("/api/analytics/inventory/").then(setD); }, []);
  if (!d) return <div className="spin">{t("Загрузка склада…","Завантаження складу…")}</div>;
  const allCards: [string, string, boolean][] = [
    [t("Запас по закупке","Запас по закупці"), fmt(d.value_cost) + " ₴", showCost],
    [t("Запас по рознице","Запас по роздрібу"), fmt(d.value_retail) + " ₴", true],
    [t("Потенц. маржа","Потенц. маржа"), fmt(d.potential_margin) + " ₴", showCost],
    [t("Позиций в наличии","Позицій в наявності"), fmt(d.in_stock) + " / " + fmt(d.total_items), true],
    [t("Нет в наличии","Немає в наявності"), fmt(d.out_stock), true],
  ];
  const cards = allCards.filter((c) => c[2]);
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginBottom: 14 }}>
        {cards.map(([lbl, v]) => <div key={lbl} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{lbl}</div><div style={{ fontSize: 20, fontWeight: 700 }}>{v}</div></div>)}
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <b style={{ fontSize: 14 }}>{t("Запасы по категориям","Запаси по категоріях")}</b>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>{t("Категория","Категорія")}</th><th>{t("Позиций","Позицій")}</th><th>{t("Кол-во","К-сть")}</th>{showCost && <th>{t("По закупке","По закупці")}</th>}<th>{t("По рознице","По роздрібу")}</th></tr></thead>
          <tbody>{d.by_category.map((c, i) => (
            <tr key={i}><td>{c.name}</td><td>{c.items}</td><td>{c.qty.toLocaleString("ru")}</td>{showCost && <td>{fmt(c.cost)} ₴</td>}<td><b>{fmt(c.retail)} ₴</b></td></tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}
