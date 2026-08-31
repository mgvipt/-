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
import MetaMarketing from "./MetaMarketing";
import TiktokAnalytics from "./TiktokAnalytics";
import { Cone } from "../FunnelCone";

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
  const { t } = useLang();
  const { can } = useAuth();
  const canStock = can("warehouse.view");
  const canSales = can("analytics.view");
  const canMkt = can("marketing.view");
  const [section, setSection] = useState<"sales" | "marketing" | "tiktok">(canSales ? "sales" : "marketing");
  const [tab, setTab] = useState<"sales" | "channels" | "stock" | "days" | "managers">("sales");
  return (
    <div className="scroll pad fade">
      <div style={{ display: "flex", gap: 8, marginBottom: 14, borderBottom: "2px solid #eef2f7", paddingBottom: 10, flexWrap: "wrap" }}>
        {canSales && <button className={section === "sales" ? "btn btn-primary" : "btn btn-light"} onClick={() => setSection("sales")} style={{ fontSize: 14, fontWeight: 700 }}>📊 {t("Аналитика продаж", "Аналітика продажів")}</button>}
        {canMkt && <button className={section === "marketing" ? "btn btn-primary" : "btn btn-light"} onClick={() => setSection("marketing")} style={{ fontSize: 14, fontWeight: 700 }}>📣 {t("Аналитика маркетинга", "Аналітика маркетингу")}</button>}
        {canSales && <button className={section === "tiktok" ? "btn btn-primary" : "btn btn-light"} onClick={() => setSection("tiktok")} style={{ fontSize: 14, fontWeight: 700 }}><Icon n="tiktok" size={15} /> TikTok</button>}
      </div>
      {section === "marketing" && canMkt && <MetaMarketing />}
      {section === "tiktok" && canSales && <TiktokAnalytics />}
      {section === "sales" && canSales && <>
        <div className="tabline" style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          <button className={tab === "sales" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("sales")}><Icon n="📈" size={15} /> {t("Продажи","Продажі")}</button>
          <button className={tab === "channels" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("channels")}><Icon n="📣" size={15} /> {t("Каналы","Канали")}</button>
          <button className={tab === "days" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("days")}><Icon n="calendar" size={15} /> {t("По дням","По днях")}</button>
          <button className={tab === "managers" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("managers")}><Icon n="users" size={15} /> {t("Менеджеры","Менеджери")}</button>
          {canStock && <button className={tab === "stock" ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab("stock")}><Icon n="📦" size={15} /> {t("Склад","Склад")}</button>}
        </div>
        {tab === "sales" && <SalesTab />}
        {tab === "channels" && <ChannelsTab />}
        {tab === "days" && <DaysTab />}
        {tab === "managers" && <ManagersTab />}
        {tab === "stock" && canStock && <StockTab />}
        {tab === "stock" && !canStock && <div className="muted" style={{ padding: 30 }}>{t("Нет доступа к этому разделу","Немає доступу до цього розділу")}</div>}
      </>}
      {section === "sales" && !canSales && <div className="muted" style={{ padding: 30 }}>{t("Нет доступа к аналитике продаж","Немає доступу до аналітики продажів")}</div>}
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
/* Конус вынесен в ../FunnelCone (переиспользуется в Аналитике и Маркетинге) */

/* ─── Дневная динамика: сколько лидов зашло и сколько продаж по дням ─── */
function DailyChart({ from, to }: { from: string; to: string }) {
  const { t } = useLang();
  const [lead, setLead] = useState<any>(null);
  const [main, setMain] = useState<any>(null);
  useEffect(() => {
    api.get<any>(`/api/analytics/funnel-daily/?from=${from}&to=${to}`).then((d) => {
      setLead(d);
      const mf = (d.funnels || []).find((f: any) => /основн/i.test(f.name));
      if (mf) api.get<any>(`/api/analytics/funnel-daily/?from=${from}&to=${to}&funnel=${mf.id}`).then(setMain).catch(() => {});
    }).catch(() => {});
  }, [from, to]);
  if (!lead) return null;
  const wonByDay: Record<string, number> = {};
  (main?.days || []).forEach((d: any) => {
    const w = (d.stages || []).filter((s: any) => (main.stages.find((x: any) => x.id === s.stage_id) || {}).is_won).reduce((a: number, s: any) => a + (s.reached || 0), 0);
    wonByDay[d.d] = w;
  });
  const days = (lead.days || []).slice().reverse(); // от старых к новым
  const maxEnter = Math.max(...days.map((d: any) => d.entered || 0), 1);
  return (
    <div className="panel" style={{ marginTop: 6 }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>📈 {t("Динамика по дням", "Динаміка по днях")}</div>
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 12 }}>{t("Синие столбцы — сколько лидов зашло в этот день. Зелёная точка — сколько продаж (основной продукт) в этот день.", "Сині стовпці — скільки лідів зайшло. Зелена крапка — скільки продажів того дня.")}</div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 150, overflowX: "auto", paddingBottom: 4 }}>
        {days.map((d: any) => {
          const h = ((d.entered || 0) / maxEnter) * 120;
          const won = wonByDay[d.d] || 0;
          return (
            <div key={d.d} style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 30, flex: 1 }} title={`${d.d}: ${t("зашло", "зайшло")} ${d.entered || 0}${won ? `, ${t("продаж", "продажів")} ${won}` : ""}`}>
              <span style={{ fontSize: 10, color: "#64748b", fontWeight: 600 }}>{d.entered || 0}</span>
              <div style={{ width: "70%", maxWidth: 26, height: Math.max(h, 2), background: "linear-gradient(180deg,#4a90cf,#2E6FB0)", borderRadius: "4px 4px 0 0", position: "relative" }}>
                {won > 0 && <span style={{ position: "absolute", top: -16, left: "50%", transform: "translateX(-50%)", fontSize: 10, color: "#166534", fontWeight: 800 }}>●{won}</span>}
              </div>
              <span style={{ fontSize: 9, color: "#94a3b8", marginTop: 3, whiteSpace: "nowrap" }}>{d.d.slice(5)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── ПУТЬ ПРОДАЖ: Лиды → Тест → Основной (3 воронки + межворонковые %) ─── */
function SalesJourney() {
  const { t } = useLang();
  const [src, setSrc] = useState("all");
  const [from, setFrom] = useState<string>(() => { const x = new Date(); x.setDate(x.getDate() - 44); return _iso(x); });
  const [to, setTo] = useState<string>(() => _iso(new Date()));
  const [jr, setJr] = useState<any>(null);
  const [cones, setCones] = useState<any>({});
  const [sources, setSources] = useState<any[]>([]);
  useEffect(() => {
    const q = `?from=${from}&to=${to}&source=${src}`;
    setCones({});
    api.get<any>("/api/analytics/sales-journey/" + q).then((j) => {
      setJr(j);
      const ids: any = j.funnels || {};
      (["lead", "test", "main"] as const).forEach((k) => {
        const fn = ids[k];
        if (fn) api.get<any>(`/api/analytics/sales-funnel/${q}&funnel=${fn.id}`).then((cd) => {
          setCones((c: any) => ({ ...c, [k]: cd }));
          if (k === "lead" && cd.sources) setSources(cd.sources);
        }).catch(() => {});
      });
    }).catch(() => setJr({ error: true }));
  }, [src, from, to]);
  if (!jr) return <div className="panel" style={{ margin: 0, marginBottom: 12 }}><div className="muted">{t("Загрузка пути продаж…", "Завантаження шляху продажів…")}</div></div>;
  if (jr.error) return null;
  const P = jr.pct || {}; const C = jr.counts || {};
  const blocks: [string, string, string][] = [
    ["lead", t("Лиды", "Ліди"), "#2E6FB0"],
    ["test", t("Тест-набор", "Тест-набір"), "#B67A12"],
    ["main", t("Основной продукт", "Основний продукт"), "#2F8F5B"],
  ];
  return (
    <div className="panel" style={{ margin: 0, marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <b style={{ fontSize: 14 }}>🎯 {t("Путь продаж: Лиды → Тест → Основной", "Шлях продажів: Ліди → Тест → Основний")}</b>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={_dateSt} />
        <span className="muted">—</span>
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={_dateSt} />
      </div>
      {sources.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
          {sources.map((s: any) => (
            <button key={s.key} onClick={() => setSrc(s.key)} style={{ fontSize: 12, padding: "3px 11px", borderRadius: 20, cursor: "pointer", background: src === s.key ? "#2E6FB0" : "#f1f5f9", color: src === s.key ? "#fff" : "#475569", border: "none", fontWeight: 600 }}>{s.label} <b>{s.n}</b></button>
          ))}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 13 }}>
        <span style={{ padding: "6px 12px", borderRadius: 8, background: "#e2ecf7", color: "#2E6FB0", fontWeight: 700 }}>{t("Лиды", "Ліди")} {C.lead}</span>
        <span style={{ color: "#64748b", fontWeight: 700 }}>→ <b style={{ color: "#0f172a" }}>{P.lead_to_test}%</b></span>
        <span style={{ padding: "6px 12px", borderRadius: 8, background: "#f8ecd3", color: "#B67A12", fontWeight: 700 }}>{t("Тест", "Тест")} {C.test}</span>
        <span style={{ color: "#64748b", fontWeight: 700 }}>→ <b style={{ color: "#0f172a" }}>{P.test_to_main}%</b></span>
        <span style={{ padding: "6px 12px", borderRadius: 8, background: "#e1f1e8", color: "#2F8F5B", fontWeight: 700 }}>{t("Основной", "Основний")} {C.main}</span>
        <span style={{ marginLeft: "auto", fontSize: 12.5, color: "#475569" }}>{t("сразу основной", "одразу основний")}: <b>{C.main_direct}</b> · {t("лид→оплата", "лід→оплата")}: <b style={{ color: "#166534" }}>{P.lead_to_sale}%</b></span>
      </div>
      {jr.distribution && (
        <div style={{ marginBottom: 18 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{t("Куда ушли все лиды за период (по клиенту, с учётом фильтра источника):", "Куди пішли всі ліди за період (по клієнту, з урахуванням джерела):")}</div>
          <div style={{ display: "flex", height: 30, borderRadius: 8, overflow: "hidden", border: "1px solid #e2e8f0" }}>
            {([["bought_main", "#2F8F5B"], ["bought_test_only", "#B67A12"], ["stuck", "#2E6FB0"], ["lost", "#dc2626"]] as [string, string][]).map(([key, col]) => {
              const p = jr.distribution[key + "_pct"] || 0;
              if (!jr.distribution[key]) return null;
              return <div key={key} style={{ width: p + "%", background: col, color: "#fff", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", whiteSpace: "nowrap", overflow: "hidden" }}>{p >= 7 ? p + "%" : ""}</div>;
            })}
          </div>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 6, fontSize: 11.5 }}>
            {([["bought_main", t("Купили основной", "Купили основний"), "#2F8F5B"], ["bought_test_only", t("Только тест", "Тільки тест"), "#B67A12"], ["stuck", t("В работе", "В роботі"), "#2E6FB0"], ["lost", t("Потеряно", "Втрачено"), "#dc2626"]] as [string, string, string][]).map(([key, lbl, col]) => (
              <span key={key} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 9, height: 9, borderRadius: 2, background: col }} />{lbl}: <b>{jr.distribution[key] || 0}</b> ({jr.distribution[key + "_pct"] || 0}%)</span>
            ))}
          </div>
        </div>
      )}
      {blocks.map(([k, label, color]) => (
        <div key={k} style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color, marginBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: color }} />{label}
            {jr.funnels?.[k]?.name && <span className="muted" style={{ fontWeight: 400, fontSize: 11.5 }}>· {jr.funnels[k].name}</span>}
          </div>
          {cones[k] ? <Cone d={cones[k]} t={t} /> : (jr.funnels?.[k] ? <div className="muted" style={{ fontSize: 12 }}>…</div> : <div className="muted" style={{ fontSize: 12 }}>{t("воронка не найдена (проверь названия воронок)", "воронку не знайдено")}</div>)}
        </div>
      ))}
      <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
        {t("«Прошло через этап» — накопительно (достиг статуса ИЛИ любого следующего). 🤖 Юля, 👤 менеджер. Межворонковые % — по клиенту: сколько лидов дошло до теста, сколько с теста купили основной, сколько купили основной сразу (минуя тест).", "«Пройшло через етап» — накопично. 🤖 Юля, 👤 менеджер. Міжворонкові % — по клієнту.")}
      </div>
    </div>
  );
}

function SalesTab() {
  const { t } = useLang();
  const [d, setD] = useState<SalesData | null>(null);
  const [fid, setFid] = useState("");
  const [view, setView] = useState<"dash" | "table">("dash");
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
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        <button className={view === "dash" ? "btn btn-primary" : "btn btn-light"} onClick={() => setView("dash")}>📊 {t("Дашборды","Дашборди")}</button>
        <button className={view === "table" ? "btn btn-primary" : "btn btn-light"} onClick={() => setView("table")}>📋 {t("Таблица","Таблиця")}</button>
      </div>
      {view === "dash" && <SalesJourney />}
      {view === "table" && <>
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
      </>}
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
  const [funnels, setFunnels] = useState<any[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [src, setSrc] = useState("all");
  const [from, setFrom] = useState<string>(() => { const d = new Date(); d.setDate(d.getDate() - 29); return _iso(d); });
  const [to, setTo] = useState<string>(() => _iso(new Date()));
  const [cones, setCones] = useState<Record<number, any>>({});
  const [sources, setSources] = useState<any[]>([]);
  const [inited, setInited] = useState(false);
  // список воронок + чипы источника (тот же источник, что «Продажи»)
  useEffect(() => {
    api.get<any>(`/api/analytics/sales-funnel/?from=${from}&to=${to}&source=${src}`).then((d) => {
      setFunnels(d.funnels || []);
      if (d.sources) setSources(d.sources);
      if (!inited) {
        const lead = (d.funnels || []).find((f: any) => f.is_lead);
        const test = (d.funnels || []).find((f: any) => /тест/i.test(f.name) && /(набір|набор)/i.test(f.name));
        const main = (d.funnels || []).find((f: any) => /основн/i.test(f.name));
        setSelected([lead?.id, test?.id, main?.id].filter(Boolean));
        setInited(true);
      }
    }).catch(() => {});
  }, [from, to, src]);
  // конусы выбранных воронок
  useEffect(() => {
    selected.forEach((fid) => {
      api.get<any>(`/api/analytics/sales-funnel/?from=${from}&to=${to}&source=${src}&funnel=${fid}`)
        .then((d) => setCones((c) => ({ ...c, [fid]: d }))).catch(() => {});
    });
  }, [selected, from, to, src]);
  function toggle(fid: number) {
    setSelected((s) => s.includes(fid) ? s.filter((x) => x !== fid) : [...s, fid]);
  }
  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span className="muted" style={{ fontSize: 12 }}>{t("Период:", "Період:")}</span>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={_dateSt} />
        <span className="muted">—</span>
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={_dateSt} />
      </div>
      {sources.length > 0 && <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {sources.map((s: any) => <button key={s.key} onClick={() => setSrc(s.key)} style={{ fontSize: 12, padding: "3px 11px", borderRadius: 20, cursor: "pointer", background: src === s.key ? "#2E6FB0" : "#f1f5f9", color: src === s.key ? "#fff" : "#475569", border: "none", fontWeight: 600 }}>{s.label} <b>{s.n}</b></button>)}
      </div>}
      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>{t("Выбери воронки для показа (можно несколько — листай вниз):", "Обери воронки (можна кілька — гортай вниз):")}</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {funnels.map((f: any) => <button key={f.id} onClick={() => toggle(f.id)} style={{ fontSize: 12.5, padding: "5px 12px", borderRadius: 8, cursor: "pointer", border: "1px solid", borderColor: selected.includes(f.id) ? "#2E6FB0" : "#cbd5e1", background: selected.includes(f.id) ? "#e2ecf7" : "#fff", color: selected.includes(f.id) ? "#2E6FB0" : "#475569", fontWeight: 600 }}>{selected.includes(f.id) ? "✓ " : "+ "}{f.name}{f.is_lead ? " ★" : ""}</button>)}
        </div>
      </div>
      {selected.map((fid) => {
        const d = cones[fid];
        const fn = funnels.find((f) => f.id === fid);
        return (
          <div key={fid} className="panel" style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>🎯 {fn?.name || ""}{d && <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}> · {t("зашло", "зайшло")} {d.entered}</span>}</div>
            {d ? <Cone d={d} t={t} /> : <div className="muted">…</div>}
          </div>
        );
      })}
      {selected.length === 0 && <div className="muted" style={{ padding: 20 }}>{t("Выбери хотя бы одну воронку выше", "Обери хоча б одну воронку вище")}</div>}
      <DailyChart from={from} to={to} />
      <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.5, marginTop: 10 }}>
        {t("Единый источник со вкладкой «Продажи»: «прошло через этап» — накопительно (достиг статуса или следующего). «Лід отриманий» = все зашедшие. 🤖 Юля, 👤 менеджер. % — сколько прошло дальше.", "Єдине джерело з «Продажі»: накопичено. «Лід отриманий» = всі, хто зайшов. 🤖 Юля, 👤 менеджер.")}
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
  const [openU, setOpenU] = useState<number | null>(null);
  const [dlgs, setDlgs] = useState<any>(null);
  function toggleUser(id: number) {
    if (openU === id) { setOpenU(null); return; }
    setOpenU(id); setDlgs(null);
    api.get<any>(`/api/analytics/manager-dialogs/?user=${id}&from=${from}&to=${to}`).then(setDlgs).catch(() => setDlgs({ dialogs: [] }));
  }
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
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>{t("За период: ответов (через CRM), в ChatPlace (живой оператор писал прямо в ChatPlace), взял в работу, дожимов, закрыл. Клик по менеджеру — раскрыть его диалоги.", "За період: відповідей (через CRM), у ChatPlace, узяв у роботу, дожимів, закрив. Клік по менеджеру — розкрити діалоги.")}</div>
        {acts && acts.summary && (
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", background: "#f0f7ff", border: "1px solid #cfe3f7", borderRadius: 10, padding: "10px 14px", marginBottom: 12, fontSize: 12.5 }}>
            <span>👤 {t("Люди ответили", "Люди відповіли")}: <b>{acts.summary.human_total}</b> <span className="muted">({t("CRM", "CRM")} {acts.summary.human_crm} + ChatPlace {acts.summary.human_cp})</span></span>
            <span>🤖 {t("Юля", "Юля")}: <b>{acts.summary.ai}</b></span>
            <span>{t("Люди вели", "Люди вели")}: <b style={{ color: acts.summary.human_pct >= 50 ? "#166534" : "#c2410c" }}>{acts.summary.human_pct}%</b> {t("переписки", "листування")}</span>
            {acts.summary.unassigned_cp > 0 && <span className="muted" style={{ fontSize: 11.5 }}>⚠ {acts.summary.unassigned_cp} {t("ответов в ChatPlace без ответственного", "відповідей у ChatPlace без відповідального")}</span>}
          </div>
        )}
        {!acts ? <div className="muted">…</div> : (acts.rows || []).length === 0 ? <div className="muted" style={{ fontSize: 12.5 }}>{t("Нет данных за период", "Немає даних за період")}</div> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
              <thead><tr>
                <th style={_th}>{t("Менеджер", "Менеджер")}</th>
                <th style={{ ..._th, textAlign: "right" }} title={t("Ответы через CRM", "Відповіді через CRM")}>{t("Ответов", "Відповідей")}</th>
                <th style={{ ..._th, textAlign: "right" }} title={t("Живой оператор писал прямо в ChatPlace (раньше эти ответы терялись из статистики)", "Живий оператор писав прямо в ChatPlace (раніше ці відповіді губились)")}>{t("в ChatPlace", "у ChatPlace")}</th>
                <th style={{ ..._th, textAlign: "right" }}>{t("Взял", "Узяв")}</th>
                <th style={{ ..._th, textAlign: "right" }}>{t("Дожимов", "Дожимів")}</th>
                <th style={{ ..._th, textAlign: "right" }}>{t("Закрыл", "Закрив")}</th>
              </tr></thead>
              <tbody>{(acts.rows || []).map((r: any) => (
                <Fragment key={r.user_id}>
                <tr>
                  <td style={{ ..._td, fontWeight: 600 }}>
                    <button onClick={() => toggleUser(r.user_id)} style={{ background: "none", border: "none", cursor: "pointer", fontWeight: 600, color: "#0f172a", padding: 0, display: "inline-flex", alignItems: "center", gap: 5, fontSize: 13 }}>
                      <span style={{ display: "inline-block", transform: openU === r.user_id ? "rotate(90deg)" : "none", color: "#94a3b8" }}>▸</span>{r.name}
                    </button>
                  </td>
                  <td style={{ ..._td, textAlign: "right" }}>{r.replies || 0}</td>
                  <td style={{ ..._td, textAlign: "right", color: (r.replies_cp ? "#2563eb" : "#cbd5e1"), fontWeight: r.replies_cp ? 700 : 400 }}>{r.replies_cp || 0}</td>
                  <td style={{ ..._td, textAlign: "right" }}>{r.taken || 0}</td>
                  <td style={{ ..._td, textAlign: "right", color: "#c2410c", fontWeight: 600 }}>{r.followups || 0}</td>
                  <td style={{ ..._td, textAlign: "right" }}>{r.closed || 0}</td>
                </tr>
                {openU === r.user_id && (
                  <tr><td colSpan={6} style={{ padding: 0, background: "#f8fafc" }}>
                    {!dlgs ? <div className="muted" style={{ padding: 10, fontSize: 12 }}>…</div> : (dlgs.dialogs || []).length === 0 ? <div className="muted" style={{ padding: 10, fontSize: 12 }}>{t("Нет диалогов за период", "Немає діалогів за період")}</div> : (
                      <div style={{ padding: "8px 10px", maxHeight: 320, overflowY: "auto" }}>
                        <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>{t("Диалоги менеджера (👤 его сообщений / 🤖 Юли) — клик открывает чат:", "Діалоги менеджера (👤 його / 🤖 Юлі) — клік відкриває чат:")}</div>
                        {(dlgs.dialogs || []).map((dl: any) => (
                          <a key={dl.conversation_id} href={`/inbox?c=${dl.conversation_id}`} style={{ display: "flex", gap: 10, alignItems: "center", padding: "5px 8px", borderRadius: 6, fontSize: 12.5, textDecoration: "none", color: "#0f172a", borderBottom: "1px solid #eef2f7" }}>
                            <span style={{ flex: 1, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{dl.contact}</span>
                            <span className="muted" style={{ fontSize: 11 }}>{dl.channel}</span>
                            <span style={{ color: "#2563eb", fontWeight: 700 }}>👤 {dl.my_msgs}</span>
                            <span style={{ color: "#7c3aed" }}>🤖 {dl.ai_msgs}</span>
                            <span className="muted" style={{ fontSize: 11, whiteSpace: "nowrap" }}>{dl.last_at}</span>
                          </a>
                        ))}
                      </div>
                    )}
                  </td></tr>
                )}
                </Fragment>
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
