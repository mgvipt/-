import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

const TAB_KEYS = ["overview", "ads", "funnel", "creatives", "content", "forms", "sources"] as const;
type Tab = typeof TAB_KEYS[number];

function iso(d: Date) { return d.toISOString().slice(0, 10); }
function money(v: any) { return `${Number(v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ₴`; }

export default function MetaMarketing() {
  const { t } = useLang();
  const today = useMemo(() => new Date(), []);
  const monthAgo = useMemo(() => { const d = new Date(today); d.setDate(d.getDate() - 29); return d; }, [today]);
  const [from, setFrom] = useState(iso(monthAgo));
  const [to, setTo] = useState(iso(today));
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.get<any>(`/api/meta-marketing/?from=${from}&to=${to}`).then(setData).catch(() => setError(t("Не удалось загрузить данные", "Не вдалося завантажити дані")));
  }, [from, to, t]);

  const tabs: { key: Tab; ru: string; ua: string }[] = [
    { key: "overview", ru: "Обзор", ua: "Огляд" },
    { key: "ads", ru: "Реклама", ua: "Реклама" },
    { key: "funnel", ru: "Воронка", ua: "Воронка" },
    { key: "creatives", ru: "Креативы", ua: "Креативи" },
    { key: "content", ru: "Контент · SMM", ua: "Контент · SMM" },
    { key: "forms", ru: "Лид-формы", ua: "Лід-форми" },
    { key: "sources", ru: "Источники диалогов", ua: "Джерела діалогів" },
  ];
  const summary = data?.summary || {};
  const integration = data?.integration || {};
  const card = (label: string, value: any, color = "#0f172a") => (
    <div className="panel" style={{ padding: 16, minWidth: 170, flex: "1 1 170px" }}>
      <div className="muted" style={{ fontSize: 12 }}>{label}</div>
      <div style={{ fontSize: 27, fontWeight: 850, color, marginTop: 4 }}>{value}</div>
    </div>
  );
  const table = (headers: string[], rows: any[][], empty: string) => (
    <div className="panel" style={{ padding: 0, overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 660 }}>
        <thead><tr>{headers.map((h) => <th key={h} style={th}>{h}</th>)}</tr></thead>
        <tbody>{rows.length ? rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} style={td}>{v}</td>)}</tr>) :
          <tr><td colSpan={headers.length} style={{ ...td, color: "#64748b", textAlign: "center", padding: 28 }}>{empty}</td></tr>}</tbody>
      </table>
    </div>
  );
  const waiting = (
    <div className="note" style={{ marginBottom: 14, borderLeft: "4px solid #f59e0b", lineHeight: 1.55 }}>
      <b>{t("Показатели Meta ещё не синхронизированы", "Показники Meta ще не синхронізовані")}</b><br />
      {t("CRM уже считает рекламные лиды, сделки и оплаты. Расходы, показы, охват, CTR, CPM, CPC и ROAS появятся после подключения Marketing/Insights API — сейчас нулевые значения не подставляются.",
         "CRM уже рахує рекламні ліди, угоди й оплати. Витрати, покази, охоплення, CTR, CPM, CPC і ROAS з'являться після підключення Marketing/Insights API — зараз нульові значення не підставляються.")}
    </div>
  );

  return <div style={{ height: "100%", overflowY: "auto", padding: 16, boxSizing: "border-box" }}>
    <div style={{ maxWidth: 1220 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <div><h2 style={{ margin: 0, fontSize: 23 }}>📣 {t("Маркетинг · Meta", "Маркетинг · Meta")}</h2>
          <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>{t("Только подтверждённая реклама и лид-формы", "Лише підтверджена реклама та лід-форми")}</div></div>
        <div style={{ flex: 1 }} />
        <label style={dateLabel}>{t("с", "з")} <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={dateInput} /></label>
        <label style={dateLabel}>{t("по", "по")} <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={dateInput} /></label>
      </div>

      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 8, marginBottom: 8 }}>
        {tabs.map((item) => <button key={item.key} className={tab === item.key ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab(item.key)} style={{ whiteSpace: "nowrap" }}>{t(item.ru, item.ua)}</button>)}
      </div>
      {error && <div className="note" style={{ color: "#b91c1c" }}>{error}</div>}
      {!data ? <div className="muted" style={{ padding: 30 }}>…</div> : <>
        {tab === "overview" && <>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
            {card(t("Рекламные лиды", "Рекламні ліди"), summary.attributed_leads || 0, "#2563eb")}
            {card(t("Рекламные сделки", "Рекламні угоди"), summary.attributed_deals || 0, "#7c3aed")}
            {card(t("Успешные сделки", "Успішні угоди"), summary.won_deals || 0, "#16a34a")}
            {card(t("Выручка успешных", "Виручка успішних"), money(summary.won_revenue), "#15803d")}
            {card(t("Фактически оплачено", "Фактично сплачено"), money(summary.paid_revenue), "#047857")}
          </div>
          <div className="note" style={{ marginBottom: 12, lineHeight: 1.55 }}>
            <b>{t("Защита от неверных конверсий включена.", "Захист від хибних конверсій увімкнено.")}</b> {t(
              `${summary.manual_or_organic_leads || 0} ручных/органических лидов и ${summary.manual_or_organic_deals || 0} сделок исключены из передачи Meta.`,
              `${summary.manual_or_organic_leads || 0} ручних/органічних лідів і ${summary.manual_or_organic_deals || 0} угод виключено з передачі Meta.`
            )}
          </div>
          {waiting}
          {table([t("Платформа", "Платформа"), t("Лиды", "Ліди"), t("Сделки", "Угоди"), t("Успешные", "Успішні"), t("Выручка", "Виручка")],
            (data.by_platform || []).map((r: any) => [r.platform, r.leads, r.deals, r.won, money(r.revenue)]), t("За период рекламных данных нет", "За період рекламних даних немає"))}
        </>}

        {tab === "ads" && <>{waiting}{table([
          t("Кампания / объявление", "Кампанія / оголошення"), t("Лиды", "Ліди"), t("Сделки", "Угоди"), t("Успешные", "Успішні"), t("Выручка CRM", "Виручка CRM")],
          (data.campaigns || []).map((r: any) => [r.campaign_name || r.campaign_id || t("ID пока не получен", "ID ще не отримано"), r.leads, r.deals, r.won, money(r.revenue)]),
          t("Нет подтверждённых рекламных кампаний за период", "Немає підтверджених рекламних кампаній за період"))}</>}

        {tab === "funnel" && <>{table([
          t("Воронка CRM", "Воронка CRM"), t("Точная стадия CRM", "Точна стадія CRM"), t("Событие Meta", "Подія Meta"), t("Лиды", "Ліди"), t("Сделки", "Угоди")],
          (data.stages || []).map((r: any) => [r.funnel, r.stage, r.meta_event, r.leads, r.deals]),
          t("Нет рекламных карточек на стадиях", "Немає рекламних карток на стадіях"))}</>}

        {tab === "creatives" && <>{waiting}{table([
          t("Контент / объявление", "Контент / оголошення"), t("Лиды", "Ліди"), t("Сделки", "Угоди"), t("Статус", "Статус")],
          (data.content || []).map((r: any) => [r.content_id || "—", r.leads, r.deals, t("CRM-результат доступен", "CRM-результат доступний")]),
          t("Креативы появятся после синхронизации объявлений", "Креативи з'являться після синхронізації оголошень"))}</>}

        {tab === "content" && <>{waiting}<div className="panel" style={{ padding: 18, lineHeight: 1.6 }}>
          <b>{t("Здесь будет рабочее место SMM", "Тут буде робоче місце SMM")}</b><br />
          {t("Публикации, Reels и Stories: охват, вовлечённость, сохранения, комментарии, переходы в диалог и продажи в CRM. Сейчас экран не смешивает органику с рекламой и ждёт Content/Insights API.",
             "Публікації, Reels і Stories: охоплення, залучення, збереження, коментарі, переходи в діалог і продажі в CRM. Зараз екран не змішує органіку з рекламою та чекає Content/Insights API.")}
        </div></>}

        {tab === "forms" && <>{table([
          t("Тип", "Тип"), t("Лиды", "Ліди"), t("Сделки", "Угоди"), t("Назначение", "Призначення")],
          (data.by_source_kind || []).filter((r: any) => r.source_kind === "lead_form").map((r: any) => [t("Лид-форма Meta", "Лід-форма Meta"), r.leads, r.deals, t("Автоматическое создание лида", "Автоматичне створення ліда")]),
          t("За период лид-формы не зафиксированы", "За період лід-форми не зафіксовані"))}</>}

        {tab === "sources" && <>{table([
          t("Платформа", "Платформа"), t("Лиды", "Ліди"), t("Сделки", "Угоди"), t("Успешные", "Успішні"), t("Путь ответа", "Шлях відповіді")],
          (data.by_platform || []).map((r: any) => [r.platform, r.leads, r.deals, r.won, t("CRM → Meta/ChatPlace по типу диалога", "CRM → Meta/ChatPlace за типом діалогу")]),
          t("Нет подтверждённых рекламных источников", "Немає підтверджених рекламних джерел"))}</>}

        <div className="panel" style={{ marginTop: 12, padding: 14, display: "flex", gap: 16, flexWrap: "wrap", fontSize: 12 }}>
          <b>{t("Состояние подключения:", "Стан підключення:")}</b>
          <span>{integration.capi_enabled ? "🟢" : "⚪"} CAPI</span>
          <span>{integration.capi_dataset_configured && integration.capi_token_configured ? "🟢" : "⚪"} Dataset + token</span>
          <span>{integration.insights_sync_configured ? "🟢" : "🟡"} Marketing/Insights API</span>
        </div>
      </>}
    </div>
  </div>;
}

const th: any = { textAlign: "left", padding: "10px 12px", fontSize: 12, color: "#64748b", borderBottom: "2px solid #e2e8f0", whiteSpace: "nowrap" };
const td: any = { padding: "10px 12px", fontSize: 13, borderBottom: "1px solid #eef2f7" };
const dateLabel: any = { display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#64748b" };
const dateInput: any = { height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px", background: "#fff" };
