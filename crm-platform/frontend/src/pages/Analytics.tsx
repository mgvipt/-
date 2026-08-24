/* ============================================================================
 *  АНАЛИТИКА  —  frontend/src/pages/Analytics.tsx
 *  Две вкладки: ПРОДАЖІ (воронка, KPI, топ менеджеров) и СКЛАД (стоимость
 *  запасов по закупке/рознице, потенц. маржа, по категориям).
 *  Документация: docs/CODEMAP.md разд.3.
 * ========================================================================== */
import { useEffect, useState, Fragment } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { useAuth } from "../auth";
import { Icon } from "../Icon";

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
  by_category: { name: string; items: number; qty: number; cost: number; retail: number; prods?: { id: number; name: string; sku: string; unit: string; qty: number; price: number; retail: number; cost: number | null }[] }[];
  frozen_total?: number; frozen_top?: { name: string; sku: string; qty: number; unit: string; frozen: number }[];
  dead_count?: number; dead_total?: number; dead_top?: { name: string; sku: string; qty: number; unit: string; frozen: number }[]; dead_days?: number;
  losses_writeoff_90d?: number; losses_inv_90d?: number;
  inv_surplus_90d?: number; inv_surplus_cnt?: number; inv_shortage_cnt?: number;
  inv_docs_90d?: { id: number; date: string; comment: string; positions: number; surplus: number; shortage: number }[];
}
const fmt = (n: number) => Math.round(n || 0).toLocaleString("ru");

export default function Analytics() {
  const [tab, setTab] = useState<"sales" | "channels" | "stock" | "days" | "managers">("sales");
  const { t } = useLang();
  const { can } = useAuth();
  const canStock = can("warehouse.view");
  const canSales = can("analytics.view");
  return (
    <div className="scroll pad fade">
      <div className="tabline" style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {canSales && <button className={tab === "sales" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("sales")}><Icon n="📈" size={15} /> {t("Продажи","Продажі")}</button>}
        {canSales && <button className={tab === "channels" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("channels")}><Icon n="📣" size={15} /> {t("Каналы","Канали")}</button>}
        {canSales && <button className={tab === "days" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("days")}><Icon n="calendar" size={15} /> {t("По дням","По днях")}</button>}
        {canSales && <button className={tab === "managers" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("managers")}><Icon n="users" size={15} /> {t("Менеджеры","Менеджери")}</button>}
        {canStock && <button className={tab === "stock" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("stock")}><Icon n="📦" size={15} /> {t("Склад","Склад")}</button>}
      </div>
      {tab === "sales" && canSales && <SalesTab />}
      {tab === "channels" && canSales && <ChannelsTab />}
      {tab === "days" && canSales && <DaysTab />}
      {tab === "managers" && canSales && <ManagersTab />}
      {tab === "stock" && canStock && <StockTab />}
      {((tab === "stock" && !canStock) || ((tab === "sales" || tab === "channels" || tab === "days" || tab === "managers") && !canSales)) && <div className="muted" style={{ padding: 30 }}>{t("Нет доступа к этому разделу","Немає доступу до цього розділу")}</div>}
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
      <b style={{ fontSize: 14 }}>{t("Доход по каналам · какой канал растит доход","Дохід за каналами · який канал збільшує дохід")} (маржа {d.margin_pct}%)</b>
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
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}><Icon n="📣" size={14} /> {t("Канал = источник сделки (Instagram/Facebook/Сайт/Опт/Дизайнеры/TikTok/Telegram). «Чистый вклад» = выручка×маржа − реклама — показывает какой канал реально даёт прибыль. Spend/ROAS — введи рекламу в Настройках или авто из Meta-ads.","Канал = джерело угоди (Instagram/Facebook/Сайт/Опт/Дизайнери/TikTok/Telegram). «Чистий внесок» = виручка×маржа − реклама — показує, який канал реально дає прибуток. Spend/ROAS — введи рекламу в Налаштуваннях або авто з Meta-ads.")}</div>
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
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: 12, marginBottom: 14 }}>
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
        <table style={{ marginTop: 8 }}><thead><tr><th>{t("Менеджер","Менеджер")}</th><th style={{ textAlign: "right" }}>{t("Сделок","Угод")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th></tr></thead>
          <tbody>{d.managers.map((m, i) => <tr key={i}><td>{m.name.trim() || "—"}</td><td style={{ textAlign: "right" }}>{m.deals}</td><td style={{ textAlign: "right" }}><b>{fmt(m.sum)} ₴</b></td></tr>)}</tbody>
        </table>
      </div>

      {/* ── КАНАЛИ (джерела лідів і сделок) ── */}
      <div className="panel" style={{ margin: 0, marginTop: 12 }}>
        <b style={{ fontSize: 14 }}><Icon n="📣" size={15} /> {t("Каналы — источники лидов и сделок","Канали — джерела лідів і угод")}</b>
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
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{t("Живые лиды (Instagram / Telegram / Facebook) падают по источникам автоматически. «Лиды» — новые обращения, «Сделок/Выиграно» — за всё время. Конверсия = выиграно / (выиграно + проиграно).","Живі ліди (Instagram / Telegram / Facebook) розподіляються за джерелами автоматично. «Ліди» — нові звернення, «Угод/Виграно» — за весь час. Конверсія = виграно / (виграно + програно).")}</div>
      </div>
    </>
  );
}

/* ─── ВКЛАДКА СКЛАД ────────────────────────────────────────────────────── */
export function StockTab() {
  const { t } = useLang();
  const { can } = useAuth();
  const showCost = can("product.cost.view");
  const [d, setD] = useState<InvData | null>(null);
  const [openCat, setOpenCat] = useState<number | null>(null);
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
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: 12, marginBottom: 14 }}>
        {cards.map(([lbl, v]) => <div key={lbl} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{lbl}</div><div style={{ fontSize: 20, fontWeight: 700 }}>{v}</div></div>)}
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <b style={{ fontSize: 14 }}>{t("Запасы по категориям","Запаси по категоріях")}</b>
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>{t("Категория","Категорія")}</th><th>{t("Позиций","Позицій")}</th><th>{t("Кол-во","К-сть")}</th>{showCost && <th>{t("По закупке","По закупці")}</th>}<th>{t("По рознице","По роздрібу")}</th></tr></thead>
          <tbody>{d.by_category.map((c, i) => (
            <Fragment key={i}>
              <tr onClick={() => setOpenCat(openCat === i ? null : i)} style={{ cursor: "pointer" }} title={t("Нажми — показать товары в категории","Натисни — показати товари в категорії")}>
                <td><span style={{ color: "#94a3b8", marginRight: 5 }}>{openCat === i ? "▾" : "▸"}</span>{c.name}</td>
                <td>{c.items}</td><td>{c.qty.toLocaleString("ru")}</td>{showCost && <td>{fmt(c.cost)} ₴</td>}<td><b>{fmt(c.retail)} ₴</b></td>
              </tr>
              {openCat === i && (c.prods || []).map((pr) => (
                <tr key={"p" + pr.id} style={{ background: "#f8fafc" }}>
                  <td style={{ paddingLeft: 24, fontSize: 12.5 }}>{pr.name}{pr.sku ? <span className="muted"> · {pr.sku}</span> : null}</td>
                  <td></td>
                  <td style={{ fontSize: 12.5 }}>{Number(pr.qty).toLocaleString("ru")} {pr.unit || ""}</td>
                  {showCost && <td style={{ fontSize: 12.5, color: "#9a3412" }}>{fmt(pr.cost ?? 0)} ₴</td>}
                  <td style={{ fontSize: 12.5 }}><b>{fmt(pr.retail)} ₴</b> <span className="muted" style={{ fontSize: 11 }}>({fmt(pr.price)}/{pr.unit || t("ед","од")})</span></td>
                </tr>
              ))}
            </Fragment>
          ))}</tbody>
        </table>
      </div>

      {showCost && ((d.losses_writeoff_90d || 0) > 0 || (d.losses_inv_90d || 0) > 0) && (
        <div className="panel" style={{ margin: "14px 0 0", borderLeft: "4px solid #f59e0b" }}>
          <b style={{ fontSize: 14 }}>⚠️ {t("Потери склада за 90 дней (справочно)","Втрати складу за 90 днів (довідково)")}</b>
          <div className="muted" style={{ fontSize: 12, margin: "2px 0 0" }}>
            {t("Брак/псування","Брак/псування")}: <b>{fmt(d.losses_writeoff_90d || 0)} ₴</b> · {t("Недостачи по инвентаризации","Нестачі по інвентаризації")}: <b>{fmt(d.losses_inv_90d || 0)} ₴</b> — {t("по закупочной. Это НЕ движение денег (деньги ушли при закупке), но эти потери уменьшают твою прибыль.","по закупівельній. Це НЕ рух грошей (гроші пішли при закупівлі), але ці втрати зменшують твій прибуток.")}
          </div>
        </div>
      )}

      {showCost && ((d.inv_surplus_90d || 0) > 0 || (d.losses_inv_90d || 0) > 0 || (d.inv_docs_90d || []).length > 0) && (
        <div className="panel" style={{ margin: "14px 0 0", borderLeft: "4px solid #3b82f6" }}>
          <b style={{ fontSize: 14 }}>📋 {t("Инвентаризация за 90 дней","Інвентаризація за 90 днів")}</b>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap", margin: "10px 0 4px" }}>
            <div>
              <div className="muted" style={{ fontSize: 12 }}>{t("Излишки (оприходовано)","Надлишки (оприбутковано)")}</div>
              <b style={{ fontSize: 15, color: "#16a34a" }}>+{fmt(d.inv_surplus_90d || 0)} ₴</b> <span className="muted" style={{ fontSize: 12 }}>({d.inv_surplus_cnt || 0} {t("поз.","поз.")})</span>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 12 }}>{t("Недостачи (списано)","Нестачі (списано)")}</div>
              <b style={{ fontSize: 15, color: "#dc2626" }}>−{fmt(d.losses_inv_90d || 0)} ₴</b> <span className="muted" style={{ fontSize: 12 }}>({d.inv_shortage_cnt || 0} {t("поз.","поз.")})</span>
            </div>
            <div>
              <div className="muted" style={{ fontSize: 12 }}>{t("Итог (излишки − недостачи)","Підсумок (надлишки − нестачі)")}</div>
              {(() => { const net = (d.inv_surplus_90d || 0) - (d.losses_inv_90d || 0); return <b style={{ fontSize: 15, color: net < 0 ? "#dc2626" : net > 0 ? "#16a34a" : "#475569" }}>{net > 0 ? "+" : ""}{fmt(net)} ₴</b>; })()}
            </div>
          </div>
          {(d.inv_docs_90d || []).length > 0 && (
            <table style={{ width: "100%", fontSize: 12, marginTop: 8 }}>
              <thead><tr>
                <th style={{ textAlign: "left" }}>{t("Дата","Дата")}</th>
                <th style={{ textAlign: "left" }}>{t("Инвентаризация","Інвентаризація")}</th>
                <th style={{ textAlign: "center" }}>{t("Позиций","Позицій")}</th>
                <th style={{ textAlign: "right" }}>{t("Излишки","Надлишки")}</th>
                <th style={{ textAlign: "right" }}>{t("Недостачи","Нестачі")}</th>
              </tr></thead>
              <tbody>{(d.inv_docs_90d || []).map((x) => (
                <tr key={x.id}>
                  <td>{x.date}</td>
                  <td>{x.comment}</td>
                  <td style={{ textAlign: "center" }}>{x.positions}</td>
                  <td style={{ textAlign: "right", color: "#16a34a" }}>{x.surplus ? "+" + fmt(x.surplus) + " ₴" : "—"}</td>
                  <td style={{ textAlign: "right", color: "#dc2626" }}>{x.shortage ? "−" + fmt(x.shortage) + " ₴" : "—"}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{t("По закупочной себестоимости. Отменённые (сторно) не учитываются.","За закупівельною собівартістю. Скасовані (сторно) не враховуються.")}</div>
        </div>
      )}
      {showCost && d.frozen_top && d.frozen_top.length > 0 && (
        <div className="panel" style={{ margin: "14px 0 0" }}>
          <b style={{ fontSize: 14 }}>💰 {t("Замороженные деньги (где лежит капитал)","Заморожені гроші (де лежить капітал)")}</b>
          <div className="muted" style={{ fontSize: 12, margin: "2px 0 8px" }}>{t("Всего в товаре по закупке","Всього в товарі по закупці")}: <b style={{ color: "#9a3412" }}>{fmt(d.frozen_total || 0)} ₴</b>. {t("Топ-20 где заморожен капитал.","Топ-20 де заморожений капітал.")}</div>
          <table style={{ marginTop: 4 }}><thead><tr><th>{t("Товар","Товар")}</th><th>{t("Артикул","Артикул")}</th><th>{t("Остаток","Залишок")}</th><th>{t("Заморожено ₴","Заморожено ₴")}</th></tr></thead>
            <tbody>{d.frozen_top!.map((r, i) => <tr key={i}><td>{r.name}</td><td className="muted">{r.sku}</td><td>{r.qty} {r.unit}</td><td><b>{fmt(r.frozen)} ₴</b></td></tr>)}</tbody></table>
        </div>
      )}

      {showCost && (d.dead_count ?? 0) > 0 && (
        <div className="panel" style={{ margin: "14px 0 0", borderLeft: "4px solid #dc2626" }}>
          <b style={{ fontSize: 14 }}>🪦 {t("Мёртвый сток","Мертвий сток")} — {t("нет продаж","немає продажів")} {d.dead_days} {t("дней","днів")}</b>
          <div className="muted" style={{ fontSize: 12, margin: "2px 0 8px" }}>{d.dead_count} {t("товаров","товарів")}, {t("в них заморожено","у них заморожено")} <b style={{ color: "#dc2626" }}>{fmt(d.dead_total || 0)} ₴</b>. {t("Кандидаты на акцию / распродажу → живые деньги.","Кандидати на акцію / розпродаж → живі гроші.")}</div>
          <table style={{ marginTop: 4 }}><thead><tr><th>{t("Товар","Товар")}</th><th>{t("Артикул","Артикул")}</th><th>{t("Остаток","Залишок")}</th><th>{t("Заморожено ₴","Заморожено ₴")}</th></tr></thead>
            <tbody>{d.dead_top!.map((r, i) => <tr key={i}><td>{r.name}</td><td className="muted">{r.sku}</td><td>{r.qty} {r.unit}</td><td><b>{fmt(r.frozen)} ₴</b></td></tr>)}</tbody></table>
        </div>
      )}
    </>
  );
}


/* ─── ВКЛАДКА «ПО ДНЯХ» — дневной срез воронки (все воронки) ──────────────── */
const _th: any = { textAlign: "left", padding: "7px 9px", fontSize: 12, color: "#64748b", borderBottom: "2px solid #eef2f7", whiteSpace: "nowrap" };
const _td: any = { padding: "6px 9px", fontSize: 13, borderBottom: "1px solid #f1f5f9", verticalAlign: "middle" };
const _dateSt: any = { height: 32, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 13 };
const _selSt: any = { height: 32, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13, background: "#fff" };
const _iso = (dt: Date) => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;

function DaysTab() {
  const { t } = useLang();
  const [fd, setFd] = useState<any>(null);
  const [funnelId, setFunnelId] = useState<string>("");
  const [from, setFrom] = useState<string>(() => { const d = new Date(); d.setDate(d.getDate() - 13); return _iso(d); });
  const [to, setTo] = useState<string>(() => _iso(new Date()));
  useEffect(() => {
    const q = `?from=${from}&to=${to}` + (funnelId ? `&funnel=${funnelId}` : "");
    api.get<any>("/api/analytics/funnel-daily/" + q).then(setFd).catch(() => {});
  }, [from, to, funnelId]);
  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
        <span className="muted" style={{ fontSize: 12 }}>{t("Период:", "Період:")}</span>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={_dateSt} />
        <span className="muted">—</span>
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={_dateSt} />
        {fd && <select value={funnelId} onChange={(e) => setFunnelId(e.target.value)} style={_selSt}>
          {(fd.funnels || []).map((f: any) => <option key={f.id} value={f.id}>{f.name}{f.is_lead ? " ★" : ""}</option>)}
        </select>}
      </div>
      <div className="panel">
        <div className="label" style={{ marginBottom: 4 }}>{t("Воронка по дням", "Воронка по днях")}{fd ? ` — ${fd.funnel}` : ""}</div>
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 10, lineHeight: 1.5 }}>
          {t("«Вошло» — сколько зашло в этот день. По статусам — сколько ДОШЛО до этого статуса в этот день (за день можно пройти несколько статусов; вернувшийся из молчания засчитается в тот день, когда двинулся).", "«Зайшло» — скільки увійшло цього дня. По статусах — скільки ДІЙШЛО до статусу цього дня.")}
        </div>
        {!fd ? <div className="muted">…</div> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 700 }}>
              <thead><tr>
                <th style={_th}>{t("День", "День")}</th>
                <th style={{ ..._th, textAlign: "right", color: "#0f172a", fontWeight: 700 }}>{t("Вошло", "Зайшло")}</th>
                {(fd.stages || []).map((st: any) => <th key={st.id} style={{ ..._th, textAlign: "right", color: st.is_won ? "#166534" : st.is_lost ? "#b91c1c" : "#64748b" }}>{st.name}</th>)}
              </tr></thead>
              <tbody>{(fd.days || []).map((d: any) => (
                <tr key={d.d}>
                  <td style={{ ..._td, whiteSpace: "nowrap", fontWeight: 600 }}>{d.d}</td>
                  <td style={{ ..._td, textAlign: "right", fontWeight: 800, color: "#0f172a" }}>{d.entered || 0}</td>
                  {(d.stages || []).map((st: any) => <td key={st.stage_id} style={{ ..._td, textAlign: "right", color: st.reached ? "#0f172a" : "#cbd5e1", fontWeight: st.reached ? 600 : 400 }}>{st.reached || "·"}</td>)}
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── ВКЛАДКА «МЕНЕДЖЕРИ» — действия в чатах + недельный вердикт AI-РОП ────── */
function ManagersTab() {
  const { t } = useLang();
  const [from, setFrom] = useState<string>(() => { const d = new Date(); d.setDate(d.getDate() - 13); return _iso(d); });
  const [to, setTo] = useState<string>(() => _iso(new Date()));
  const [acts, setActs] = useState<any>(null);
  const [rev, setRev] = useState<any>(null);
  const [revLoad, setRevLoad] = useState(false);
  const [ms, setMs] = useState<any>(null);
  const [msFunnel, setMsFunnel] = useState<string>("");
  useEffect(() => { api.get<any>(`/api/analytics/manager-actions/?from=${from}&to=${to}`).then(setActs).catch(() => setActs(null)); }, [from, to]);
  useEffect(() => { api.get<any>(`/api/analytics/manager-stages/?from=${from}&to=${to}` + (msFunnel ? `&funnel=${msFunnel}` : "")).then(setMs).catch(() => setMs(null)); }, [from, to, msFunnel]);
  useEffect(() => { api.get<any>("/api/analytics/weekly-review/").then(setRev).catch(() => setRev(null)); }, []);
  function runReview() { setRevLoad(true); api.post<any>("/api/analytics/weekly-review/", {}).then((r) => { setRev(r); setRevLoad(false); }).catch(() => setRevLoad(false)); }
  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
        <span className="muted" style={{ fontSize: 12 }}>{t("Период:", "Період:")}</span>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={_dateSt} />
        <span className="muted">—</span>
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={_dateSt} />
      </div>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="label" style={{ marginBottom: 4 }}>{t("Действия менеджеров в чатах", "Дії менеджерів у чатах")}</div>
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>{t("За период: ответов, взял в работу, дожимов, закрыл. Команда: вернулись из игнора + причины закрытия.", "За період: відповідей, узяв у роботу, дожимів, закрив.")}</div>
        {!acts ? <div className="muted">…</div> : (acts.rows || []).length === 0 ? <div className="muted" style={{ fontSize: 12.5 }}>{t("Нет данных за период", "Немає даних за період")}</div> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
              <thead><tr>
                <th style={_th}>{t("Менеджер", "Менеджер")}</th>
                <th style={{ ..._th, textAlign: "right" }}>{t("Ответов", "Відповідей")}</th>
                <th style={{ ..._th, textAlign: "right" }}>{t("Взял", "Узяв")}</th>
                <th style={{ ..._th, textAlign: "right" }}>{t("Дожимов", "Дожимів")}</th>
                <th style={{ ..._th, textAlign: "right" }}>{t("Закрыл", "Закрив")}</th>
              </tr></thead>
              <tbody>{(acts.rows || []).map((r: any) => (
                <tr key={r.user_id}>
                  <td style={{ ..._td, fontWeight: 600 }}>{r.name}</td>
                  <td style={{ ..._td, textAlign: "right" }}>{r.replies || 0}</td>
                  <td style={{ ..._td, textAlign: "right" }}>{r.taken || 0}</td>
                  <td style={{ ..._td, textAlign: "right", color: "#c2410c", fontWeight: 600 }}>{r.followups || 0}</td>
                  <td style={{ ..._td, textAlign: "right" }}>{r.closed || 0}</td>
                </tr>
              ))}</tbody>
            </table>
            {typeof acts.reactivations === "number" && acts.reactivations > 0 && (
              <div style={{ marginTop: 10, fontSize: 12.5, color: "#166534", fontWeight: 600 }}>
                <Icon n="refresh" size={13} /> {t("Вернулись из игнора (команда):", "Повернулись з ігнору (команда):")} <b>{acts.reactivations}</b>
              </div>
            )}
            {acts.close_reasons && acts.close_reasons.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div className="muted" style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>{t("Причины закрытия (почему теряем):", "Причини закриття (чому втрачаємо):")}</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {acts.close_reasons.map((c: any) => <span key={c.reason} style={{ fontSize: 12, background: "#fff1f2", color: "#9f1239", border: "1px solid #fecdd3", borderRadius: 20, padding: "3px 10px" }}>{c.reason} · <b>{c.count}</b></span>)}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
          <div className="label" style={{ margin: 0 }}>{t("По статусам: кто провёл лидов (менеджер vs ИИ)", "По статусах: хто провів лідів (менеджер vs ІІ)")}</div>
          {ms && <select value={msFunnel} onChange={(e) => setMsFunnel(e.target.value)} style={_selSt}>{(ms.funnels || []).map((f: any) => <option key={f.id} value={f.id}>{f.name}{f.is_lead ? " \u2605" : ""}</option>)}</select>}
        </div>
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 10, lineHeight: 1.5 }}>{t("Сколько лидов каждый провёл В статус за период. Строка «ИІ / автоматика» — сколько сделала автоматика/ИИ. Внизу — % работы ИИ по каждому статусу (чтобы видеть, где работает ИИ, а где менеджер).", "Скільки лідів кожен провів У статус. Рядок «ІІ / автоматика» — скільки зробила автоматика. Внизу — % роботи ІІ по кожному статусу.")}</div>
        {!ms ? <div className="muted">…</div> : (ms.rows || []).length === 0 ? <div className="muted" style={{ fontSize: 12.5 }}>{t("Нет переходов за период", "Немає переходів за період")}</div> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", minWidth: 640 }}>
              <thead><tr>
                <th style={_th}>{t("Менеджер", "Менеджер")}</th>
                {(ms.stages || []).map((st: any) => <th key={st.id} style={{ ..._th, textAlign: "center" }}><span style={{ display: "inline-block", background: st.color, color: "#fff", borderRadius: 6, padding: "2px 7px", fontSize: 11, fontWeight: 700, whiteSpace: "nowrap" }}>{st.name}</span></th>)}
                <th style={{ ..._th, textAlign: "right" }}>{t("Всего", "Всього")}</th>
              </tr></thead>
              <tbody>
                {(ms.rows || []).map((r: any) => (
                  <tr key={r.key} style={r.is_ai ? { background: "#faf5ff" } : undefined}>
                    <td style={{ ..._td, fontWeight: r.is_ai ? 800 : 600, color: r.is_ai ? "#7c3aed" : "#0f172a", whiteSpace: "nowrap" }}>{r.name}</td>
                    {(ms.stages || []).map((st: any) => <td key={st.id} style={{ ..._td, textAlign: "center", color: (r.stages[String(st.id)] ? "#0f172a" : "#cbd5e1") }}>{r.stages[String(st.id)] || "·"}</td>)}
                    <td style={{ ..._td, textAlign: "right", fontWeight: 700 }}>{r.total || 0}</td>
                  </tr>
                ))}
                <tr style={{ borderTop: "2px solid #eef2f7" }}>
                  <td style={{ ..._td, fontWeight: 700, color: "#7c3aed" }}>{t("% работы ИИ", "% роботи ІІ")}</td>
                  {(ms.stages || []).map((st: any) => { const p = ms.ai_pct ? ms.ai_pct[String(st.id)] : null; return <td key={st.id} style={{ ..._td, textAlign: "center", color: (p == null ? "#cbd5e1" : (p >= 80 ? "#b91c1c" : "#7c3aed")), fontWeight: 700 }}>{p == null ? "·" : p + "%"}</td>; })}
                  <td style={_td}></td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="panel" style={{ marginBottom: 24, border: "2px solid #ddd6fe" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
          <div className="label" style={{ margin: 0 }}>{t("Разбор недели от AI-РОП", "Розбір тижня від AI-РОП")}</div>
          <button className="btn btn-primary" style={{ fontSize: 13 }} onClick={runReview} disabled={revLoad}>{revLoad ? t("AI анализирует…", "AI аналізує…") : <><Icon n="bulb" size={14} /> {t("Сделать разбор", "Зробити розбір")}</>}</button>
          {rev && rev.created_at && <span className="muted" style={{ fontSize: 11.5 }}>{t("последний:", "останній:")} {rev.created_at} · {rev.period || ""}</span>}
        </div>
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>{t("AI-РОП разбирает работу менеджеров за неделю и даёт вердикт: кто теряет лиды, групповые ошибки. Дёшево по токенам.", "AI-РОП розбирає роботу менеджерів за тиждень і дає вердикт.")}</div>
        {rev && rev.summary && <div style={{ background: "#f5f3ff", borderRadius: 10, padding: "10px 14px", fontSize: 13.5, lineHeight: 1.55, marginBottom: 10, whiteSpace: "pre-wrap" }}>{rev.summary}</div>}
        {rev && (rev.managers || []).length > 0 && (rev.managers || []).map((m: any, i: number) => (
          <div key={i} style={{ borderTop: "1px solid #eef2f7", padding: "8px 0" }}>
            <div style={{ fontWeight: 700, fontSize: 13.5 }}>{m.name} {m.score != null && <span className="muted" style={{ fontWeight: 400 }}>· {m.score}/100</span>}</div>
            {m.verdict && <div style={{ fontSize: 12.5, color: "#334155", lineHeight: 1.5, marginTop: 2, whiteSpace: "pre-wrap" }}>{m.verdict}</div>}
          </div>
        ))}
        {rev && rev.error && <div style={{ color: "#b91c1c", fontSize: 12 }}>{rev.error}</div>}
      </div>
    </div>
  );
}
