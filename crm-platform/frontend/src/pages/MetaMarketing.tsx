import { ReactNode, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

const CONNECTED_FROM = "2026-06-16";
const TAB_KEYS = ["overview", "profitability", "ads", "creatives", "content", "funnel", "forms", "sources"] as const;
type Tab = typeof TAB_KEYS[number];
type AdLevel = "campaigns" | "adsets" | "ads";

function iso(d: Date) { return d.toISOString().slice(0, 10); }
function count(v: any) { return Number(v || 0).toLocaleString("ru-RU"); }
function moneyUah(v: any) { return `${Number(v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ₴`; }
function moneyUsd(v: any) { return `$${Number(v || 0).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }
function optional(v: any, suffix = "", empty = "нет данных") {
  return v === null || v === undefined ? <span style={{ color: "#94a3b8" }}>{empty}</span> : `${count(v)}${suffix}`;
}
function dateTime(v: any) {
  if (!v) return "—";
  return new Date(v).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function MetaMarketing() {
  const { t } = useLang();
  const today = useMemo(() => new Date(), []);
  const [from, setFrom] = useState(CONNECTED_FROM);
  const [to, setTo] = useState(iso(today));
  const [tab, setTab] = useState<Tab>("overview");
  const [adLevel, setAdLevel] = useState<AdLevel>("campaigns");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setError(""); setLoading(true);
    api.get<any>(`/api/meta-marketing/?from=${from}&to=${to}`)
      .then(setData)
      .catch(() => setError(t("Не удалось загрузить данные", "Не вдалося завантажити дані")))
      .finally(() => setLoading(false));
  }, [from, to, t]);

  const setLastDays = (days: number) => {
    const start = new Date(today); start.setDate(start.getDate() - days + 1);
    setFrom(iso(start)); setTo(iso(today));
  };

  const tabs: { key: Tab; ru: string; ua: string }[] = [
    { key: "overview", ru: "Обзор", ua: "Огляд" },
    { key: "profitability", ru: "Продажи и рентабельность", ua: "Продажі та рентабельність" },
    { key: "ads", ru: "Реклама", ua: "Реклама" },
    { key: "creatives", ru: "Креативы", ua: "Креативи" },
    { key: "content", ru: "Органика · SMM", ua: "Органіка · SMM" },
    { key: "funnel", ru: "Воронка CRM", ua: "Воронка CRM" },
    { key: "forms", ru: "Лид-формы", ua: "Лід-форми" },
    { key: "sources", ru: "Источники", ua: "Джерела" },
  ];
  const summary = data?.summary || {};
  const paid = data?.paid || {};
  const paidSummary = paid.summary || {};
  const integration = data?.integration || {};
  const organic = data?.organic?.content || [];
  const profitability = data?.profitability || {};
  const followers = data?.followers || {};
  const daily = data?.daily || [];

  const card = (label: string, value: ReactNode, color = "#0f172a", hint?: string) => (
    <div className="panel" style={{ padding: 15, minWidth: 165, flex: "1 1 165px" }}>
      <div className="muted" style={{ fontSize: 12 }}>{label}</div>
      <div style={{ fontSize: 25, fontWeight: 850, color, marginTop: 4 }}>{value}</div>
      {hint && <div className="muted" style={{ fontSize: 10, marginTop: 5, lineHeight: 1.3 }}>{hint}</div>}
    </div>
  );
  const table = (headers: string[], rows: ReactNode[][], empty: string, minWidth = 760) => (
    <div className="panel" style={{ padding: 0, overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", minWidth }}>
        <thead><tr>{headers.map((h) => <th key={h} style={th}>{h}</th>)}</tr></thead>
        <tbody>{rows.length ? rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} style={td}>{v}</td>)}</tr>) :
          <tr><td colSpan={headers.length} style={{ ...td, color: "#64748b", textAlign: "center", padding: 28 }}>{empty}</td></tr>}</tbody>
      </table>
    </div>
  );

  const syncWarning = !integration.insights_sync_configured ? (
    <div className="note" style={{ marginBottom: 14, borderLeft: "4px solid #f59e0b", lineHeight: 1.55 }}>
      <b>{t("Первичная загрузка Meta ещё не завершена.", "Первинне завантаження Meta ще не завершене.")}</b><br />
      {t("После синхронизации здесь появятся реальные расходы, кампании, объявления и органический контент. CRM не подставляет фиктивные нули.",
        "Після синхронізації тут з'являться реальні витрати, кампанії, оголошення та органічний контент. CRM не підставляє фіктивні нулі.")}
    </div>
  ) : null;

  const platformLabel = (row: any) => {
    const title = row.name || row.ad_name || row.adset_name || row.campaign_name || row.id;
    return <div style={{ minWidth: 220 }}><b>{title || "—"}</b>{row.effective_status && <div className="muted" style={{ fontSize: 10 }}>{row.effective_status}</div>}</div>;
  };
  const adRows = (paid[adLevel] || []).map((r: any) => [
    platformLabel(r), moneyUsd(r.spend), count(r.impressions), count(r.clicks), optional(r.ctr, "%"),
    count(r.messages_started), count(r.meta_leads), count(r.crm_leads), r.cost_per_message == null ? "—" : moneyUsd(r.cost_per_message),
  ]);
  const dailyRows = daily.map((r: any) => [
    new Date(`${r.date}T12:00:00`).toLocaleDateString("ru-RU"),
    optional(r.followers_total, "", t("снимок ещё не сохранён", "знімок ще не збережено")),
    r.followers_gained == null ? "—" : `${r.followers_gained > 0 ? "+" : ""}${count(r.followers_gained)}`,
    count(r.content_published), moneyUsd(r.spend), r.spend_uah == null ? "—" : moneyUah(r.spend_uah),
    count(r.messages_started), count(r.crm_meta_leads), count(r.exact_ad_leads),
    count(r.sales), count(r.repeat_sales), moneyUah(r.revenue), moneyUah(r.repeat_revenue),
    moneyUah(r.average_ltv), moneyUah(r.gross_profit), r.roas == null ? "—" : `${r.roas}×`,
    r.romi == null ? "—" : `${r.romi}%`,
  ]);
  const dailyTable = table([
    t("Дата", "Дата"), t("Подписчики всего", "Підписники всього"), t("Новые подписчики", "Нові підписники"),
    t("Контент", "Контент"), t("Реклама, $", "Реклама, $"), t("Реклама, ₴", "Реклама, ₴"),
    t("Диалоги Meta", "Діалоги Meta"), t("Лиды CRM из Meta", "Ліди CRM з Meta"),
    t("Точный ID рекламы", "Точний ID реклами"), t("Продажи", "Продажі"),
    t("Повторные", "Повторні"), t("Выручка", "Виручка"), t("Повторная выручка", "Повторна виручка"),
    "LTV", t("Валовая прибыль", "Валовий прибуток"), "ROAS", "ROMI",
  ], dailyRows, t("За период данных нет", "За період даних немає"), 1900);

  return <div style={{ height: "100%", overflowY: "auto", padding: 16, boxSizing: "border-box" }}>
    <div style={{ maxWidth: 1440 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 23 }}>📣 {t("Маркетинг · Meta", "Маркетинг · Meta")}</h2>
          <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>
            {t("Платная реклама и органический контент считаются отдельно", "Платна реклама й органічний контент рахуються окремо")}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <button className="btn btn-light" onClick={() => setLastDays(1)}>{t("Сегодня", "Сьогодні")}</button>
        <button className="btn btn-light" onClick={() => setLastDays(7)}>7 {t("дней", "днів")}</button>
        <button className="btn btn-light" onClick={() => setLastDays(30)}>30 {t("дней", "днів")}</button>
        <button className="btn btn-light" onClick={() => setLastDays(90)}>90 {t("дней", "днів")}</button>
        <button className="btn btn-light" onClick={() => { setFrom(CONNECTED_FROM); setTo(iso(today)); }}>{t("С подключения CRM", "З підключення CRM")}</button>
        <label style={dateLabel}>{t("с", "з")} <input type="date" value={from} min={CONNECTED_FROM} onChange={(e) => setFrom(e.target.value)} style={dateInput} /></label>
        <label style={dateLabel}>{t("по", "по")} <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={dateInput} /></label>
      </div>

      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 8, marginBottom: 8 }}>
        {tabs.map((item) => <button key={item.key} className={tab === item.key ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab(item.key)} style={{ whiteSpace: "nowrap" }}>{t(item.ru, item.ua)}</button>)}
      </div>
      {error && <div className="note" style={{ color: "#b91c1c" }}>{error}</div>}
      {loading && !data ? <div className="muted" style={{ padding: 30 }}>Загрузка…</div> : data && <>
        {tab === "overview" && <>
          {syncWarning}
          <SectionTitle title={t("Instagram аккаунт", "Instagram акаунт")} note={t("Баланс подписчиков сохраняется ежедневно; прирост Meta отдаёт по дням", "Баланс підписників зберігається щодня; приріст Meta віддає по днях")} />
          <div style={cardsRow}>
            {card(t("Подписчиков сейчас", "Підписників зараз"), optional(followers.current_total, "", t("ожидает синхронизации", "очікує синхронізації")), "#c026d3", followers.username ? `@${followers.username}` : undefined)}
            {card(t("Новых за период", "Нових за період"), followers.period_gained == null ? "—" : count(followers.period_gained), "#db2777")}
            {card(t("Публикаций за период", "Публікацій за період"), count(daily.reduce((sum: number, r: any) => sum + Number(r.content_published || 0), 0)), "#7c3aed")}
            {card(t("Все лиды CRM из Meta", "Усі ліди CRM з Meta"), count(summary.meta_origin_leads), "#0284c7")}
            {card(t("С точным ID рекламы", "З точним ID реклами"), count(summary.attributed_leads), "#2563eb")}
            {card(t("Источник объявления не определён", "Джерело оголошення не визначене"), count(summary.meta_unassigned_leads), "#d97706")}
          </div>
          <SectionTitle title={t("Платная реклама Meta", "Платна реклама Meta")} note={t("Данные Ads Manager за выбранный период", "Дані Ads Manager за вибраний період")} />
          <div style={cardsRow}>
            {card(t("Расход", "Витрати"), moneyUsd(paidSummary.spend), "#dc2626")}
            {card(t("Показы", "Покази"), count(paidSummary.impressions), "#2563eb")}
            {card(t("Клики", "Кліки"), count(paidSummary.clicks), "#7c3aed")}
            {card("CTR", optional(paidSummary.ctr, "%"), "#7c3aed")}
            {card(t("Диалоги Meta", "Діалоги Meta"), count(paidSummary.messages_started), "#0f766e", t("Атрибуция платформы, не уникальные лиды CRM", "Атрибуція платформи, не унікальні ліди CRM"))}
            {card(t("Лиды Meta", "Ліди Meta"), count(paidSummary.meta_leads), "#0f766e")}
          </div>
          <SectionTitle title={t("Подтверждённый результат в CRM", "Підтверджений результат у CRM")} note={t("Только карточки с точным ID рекламы; ручные и органические исключены", "Лише картки з точним ID реклами; ручні та органічні виключені")} />
          <div style={cardsRow}>
            {card(t("Рекламные лиды CRM", "Рекламні ліди CRM"), count(summary.attributed_leads), "#2563eb")}
            {card(t("Рекламные сделки", "Рекламні угоди"), count(summary.attributed_deals), "#7c3aed")}
            {card(t("Успешные", "Успішні"), count(summary.won_deals), "#16a34a")}
            {card(t("Выручка успешных", "Виручка успішних"), moneyUah(summary.won_revenue), "#15803d")}
            {card(t("Оплачено", "Сплачено"), moneyUah(summary.paid_revenue), "#047857")}
          </div>
          <div className="note" style={{ lineHeight: 1.5 }}>
            <b>{t("Почему цифры Meta и CRM отличаются:", "Чому цифри Meta й CRM відрізняються:")}</b> {t(
              "Meta считает события по своему окну атрибуции. CRM показывает только реальные карточки с доказанной рекламной связью. Исторические лиды без ID объявления не приписываются рекламе задним числом.",
              "Meta рахує події за власним вікном атрибуції. CRM показує лише реальні картки з доведеною рекламною прив'язкою. Історичні ліди без ID оголошення не приписуються рекламі заднім числом."
            )}
          </div>
          <SectionTitle title={t("Продажи и окупаемость", "Продажі та окупність")} note={t("21 Основний продукт, 22 Тестовий набір; другие воронки только с точным ID рекламы", "21 Основний продукт, 22 Тестовий набір; інші воронки лише з точним ID реклами")} />
          <div style={cardsRow}>
            {card(t("Продажи", "Продажі"), count(profitability.sales), "#16a34a")}
            {card(t("Выручка", "Виручка"), moneyUah(profitability.revenue), "#047857")}
            {card(t("Повторные продажи", "Повторні продажі"), count(profitability.repeat_sales), "#0891b2")}
            {card(t("Повторная выручка", "Повторна виручка"), moneyUah(profitability.repeat_revenue), "#0e7490")}
            {card(t("Средний LTV", "Середній LTV"), moneyUah(profitability.average_ltv), "#7c3aed")}
            {card("ROMI", profitability.romi == null ? "—" : `${profitability.romi}%`, Number(profitability.romi) >= 0 ? "#15803d" : "#dc2626")}
          </div>
          <SectionTitle title={t("Общая статистика по дням", "Загальна статистика за днями")} note={t("Реклама, лиды, продажи, повторные покупки, LTV и прибыль в одной таблице", "Реклама, ліди, продажі, повторні покупки, LTV і прибуток в одній таблиці")} />
          {dailyTable}
        </>}

        {tab === "profitability" && <>
          <div className="note" style={{ marginBottom: 12, lineHeight: 1.5 }}>
            <b>{t("Что входит в расчёт:", "Що входить у розрахунок:")}</b> {t(
              "Все оплаченные продажи из воронок «21 Основний продукт» и «22 Тестовий набір». Из остальных воронок — только продажи с подтверждённым ID Meta. Выручка считается по фактически оплаченным платежам, себестоимость — по товарам сделки, рекламный расход переводится в гривну по официальному курсу НБУ за каждый день.",
              "Усі оплачені продажі з воронок «21 Основний продукт» і «22 Тестовий набір». З інших воронок — лише продажі з підтвердженим ID Meta. Виручка рахується за фактично сплаченими платежами, собівартість — за товарами угоди, рекламні витрати переводяться у гривню за офіційним курсом НБУ за кожен день."
            )}
          </div>
          <div style={cardsRow}>
            {card(t("Продажи", "Продажі"), count(profitability.sales), "#16a34a")}
            {card(t("Покупатели", "Покупці"), count(profitability.buyers), "#0f766e")}
            {card(t("Повторные продажи", "Повторні продажі"), count(profitability.repeat_sales), "#0891b2")}
            {card(t("Повторные клиенты", "Повторні клієнти"), count(profitability.repeat_buyers), "#0891b2")}
            {card(t("Выручка", "Виручка"), moneyUah(profitability.revenue), "#047857")}
            {card(t("Повторная выручка", "Повторна виручка"), moneyUah(profitability.repeat_revenue), "#0e7490")}
            {card(t("Средний LTV", "Середній LTV"), moneyUah(profitability.average_ltv), "#7c3aed")}
            {card(t("Себестоимость", "Собівартість"), moneyUah(profitability.cost), "#b45309")}
            {card(t("Валовая прибыль", "Валовий прибуток"), moneyUah(profitability.gross_profit), "#15803d")}
            {card(t("Реклама по курсу НБУ", "Реклама за курсом НБУ"), profitability.ad_spend_uah == null ? "—" : moneyUah(profitability.ad_spend_uah), "#dc2626")}
            {card(t("Прибыль после рекламы", "Прибуток після реклами"), profitability.marketing_profit == null ? "—" : moneyUah(profitability.marketing_profit), Number(profitability.marketing_profit) >= 0 ? "#15803d" : "#dc2626")}
            {card(t("Общий ROAS", "Загальний ROAS"), profitability.blended_roas == null ? "—" : `${profitability.blended_roas}×`, "#2563eb")}
            {card(t("ROAS с точным ID", "ROAS з точним ID"), profitability.exact_ad_roas == null ? "—" : `${profitability.exact_ad_roas}×`, "#7c3aed", t("Консервативный показатель: только доказанная связь с объявлением", "Консервативний показник: лише доведений зв'язок з оголошенням"))}
            {card("ROMI", profitability.romi == null ? "—" : `${profitability.romi}%`, Number(profitability.romi) >= 0 ? "#15803d" : "#dc2626")}
          </div>
          <SectionTitle title={t("Рентабельность по дням", "Рентабельність за днями")} note={t("Меняйте период сверху: день, неделя, месяц, 90 дней или произвольный диапазон", "Змінюйте період зверху: день, тиждень, місяць, 90 днів або довільний діапазон")} />
          {dailyTable}
        </>}

        {tab === "ads" && <>
          {syncWarning}
          <div style={{ display: "flex", gap: 7, marginBottom: 10, flexWrap: "wrap" }}>
            {(["campaigns", "adsets", "ads"] as AdLevel[]).map((key) => <button key={key} className={adLevel === key ? "btn btn-primary" : "btn btn-light"} onClick={() => setAdLevel(key)}>
              {key === "campaigns" ? t("Кампании", "Кампанії") : key === "adsets" ? t("Группы объявлений", "Групи оголошень") : t("Объявления", "Оголошення")}
            </button>)}
          </div>
          {table([
            adLevel === "campaigns" ? t("Кампания", "Кампанія") : adLevel === "adsets" ? t("Группа", "Група") : t("Объявление", "Оголошення"),
            t("Расход", "Витрати"), t("Показы", "Покази"), t("Клики", "Кліки"), "CTR", t("Диалоги Meta", "Діалоги Meta"), t("Лиды Meta", "Ліди Meta"), t("Лиды CRM", "Ліди CRM"), t("Цена диалога", "Ціна діалогу"),
          ], adRows, t("За выбранный период реклама не показывалась", "За вибраний період реклама не показувалась"), 1120)}
          <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
            {t("Охват по дням не суммируется как уникальный охват периода, поэтому в таблице он не используется для оценки результата.", "Охоплення за днями не підсумовується як унікальне охоплення періоду, тому в таблиці воно не використовується для оцінки результату.")}
          </div>
        </>}

        {tab === "creatives" && <>
          {syncWarning}
          <div className="note" style={{ marginBottom: 12 }}>
            {t("Каждая карточка — конкретное объявление. Миниатюра и ссылка помогают сразу увидеть, какой креатив дал диалоги и лиды.", "Кожна картка — конкретне оголошення. Мініатюра й посилання допомагають одразу побачити, який креатив дав діалоги та ліди.")}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 12 }}>
            {(paid.ads || []).map((r: any) => <AdCard key={r.id} row={r} t={t} />)}
            {!(paid.ads || []).length && <Empty text={t("Объявлений за период нет", "Оголошень за період немає")} />}
          </div>
        </>}

        {tab === "content" && <>
          <div className="note" style={{ marginBottom: 12, lineHeight: 1.5 }}>
            <b>{t("Только органика — без рекламных объявлений.", "Лише органіка — без рекламних оголошень.")}</b> {t(
              "Показатели каждой публикации обновляются автоматически каждые 6 часов. «Подписчики» — люди, подписавшиеся после взаимодействия с конкретной публикацией, но Meta отдаёт этот показатель не для всех форматов. Для Reels и других неподдерживаемых публикаций CRM честно показывает «нет данных».",
              "Показники кожної публікації оновлюються автоматично кожні 6 годин. «Підписники» — люди, що підписалися після взаємодії з конкретною публікацією, але Meta віддає цей показник не для всіх форматів. Для Reels та інших непідтримуваних публікацій CRM чесно показує «немає даних»."
            )}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))", gap: 12 }}>
            {organic.map((r: any) => <ContentCard key={r.media_id} row={r} t={t} />)}
            {!organic.length && <Empty text={t("Органический контент за период не найден", "Органічний контент за період не знайдено")} />}
          </div>
        </>}

        {tab === "funnel" && <>
          <div className="note" style={{ marginBottom: 12, lineHeight: 1.5 }}>
            {t("Первая таблица показывает все реальные обращения Instagram и Facebook в CRM. «Точный ID рекламы» означает, что Meta передала идентификатор объявления/кампании/формы. «Не определено» — обращение пришло из Meta, но конкретное объявление технически не было передано.", "Перша таблиця показує всі реальні звернення Instagram і Facebook у CRM. «Точний ID реклами» означає, що Meta передала ідентифікатор оголошення/кампанії/форми. «Не визначено» — звернення прийшло з Meta, але конкретне оголошення технічно не було передано.")}
          </div>
          <SectionTitle title={t("Все обращения Meta в CRM", "Усі звернення Meta в CRM")} note={t("Не пропускает лиды без рекламного ID", "Не пропускає ліди без рекламного ID")} />
          {table([
            t("Воронка CRM", "Воронка CRM"), t("Стадия CRM", "Стадія CRM"), t("Лиды", "Ліди"), t("Сделки", "Угоди"),
            t("Точный ID рекламы", "Точний ID реклами"), t("Органика", "Органіка"), t("Источник не определён", "Джерело не визначене")],
            (data.all_meta_stages || []).map((r: any) => [r.funnel, r.stage, r.leads, r.deals, r.exact_paid_leads, r.organic_leads, r.unassigned_leads]),
            t("Обращений Meta за период нет", "Звернень Meta за період немає"), 1050)}
          <SectionTitle title={t("Только подтверждённая реклама", "Лише підтверджена реклама")} note={t("Консервативная воронка для точной атрибуции", "Консервативна воронка для точної атрибуції")} />
          {table([
            t("Воронка CRM", "Воронка CRM"), t("Стадия CRM", "Стадія CRM"), t("Событие Meta", "Подія Meta"), t("Лиды", "Ліди"), t("Сделки", "Угоди")],
            (data.stages || []).map((r: any) => [r.funnel, r.stage, r.meta_event, r.leads, r.deals]),
            t("Нет карточек с точным рекламным ID", "Немає карток із точним рекламним ID"))}
        </>}

        {tab === "forms" && table([
          t("Тип", "Тип"), t("Лиды", "Ліди"), t("Сделки", "Угоди"), t("Назначение", "Призначення")],
          (data.by_source_kind || []).filter((r: any) => r.source_kind === "lead_form").map((r: any) => [t("Лид-форма Meta", "Лід-форма Meta"), r.leads, r.deals, t("Автоматическое создание лида", "Автоматичне створення ліда")]),
          t("За период лид-формы не зафиксированы", "За період лід-форми не зафіксовані"))}

        {tab === "sources" && <>
          <div className="note" style={{ marginBottom: 12 }}>{t("Метка «Реклама подтверждена» ставится только когда в карточке есть стабильный ID объявления, кампании или лид-формы Meta. Если обращение пришло из Instagram/Facebook, но Meta не передала ID, CRM показывает «Источник объявления не определён» и не приписывает его конкретной рекламе.", "Позначка «Реклама підтверджена» ставиться лише коли в картці є стабільний ID оголошення, кампанії або лід-форми Meta. Якщо звернення прийшло з Instagram/Facebook, але Meta не передала ID, CRM показує «Джерело оголошення не визначене» і не приписує його конкретній рекламі.")}</div>
          {table([t("Платформа", "Платформа"), t("Лиды", "Ліди"), t("Сделки", "Угоди"), t("Успешные", "Успішні"), t("Выручка", "Виручка")],
            (data.by_platform || []).map((r: any) => [r.platform, r.leads, r.deals, r.won, moneyUah(r.revenue)]),
            t("Подтверждённых рекламных источников нет", "Підтверджених рекламних джерел немає"))}
          <SectionTitle title={t("Последние обращения Meta", "Останні звернення Meta")} note={t("По каждой карточке видно наличие рекламного идентификатора", "Для кожної картки видно наявність рекламного ідентифікатора")} />
          {table([
            t("Карточка", "Картка"), t("Платформа", "Платформа"), t("Атрибуция", "Атрибуція"),
            t("ID Meta", "ID Meta"), t("Воронка", "Воронка"), t("Стадия", "Стадія"), t("Создана", "Створена")],
            (data.recent || []).map((r: any) => [
              <div><b>{r.object_type === "lead" ? t("Лид", "Лід") : t("Сделка", "Угода")} #{r.id}</b><div className="muted" style={{ fontSize: 10 }}>{r.title}</div></div>,
              r.platform || "—",
              r.attribution_status === "exact_paid" ? <b style={{ color: "#15803d" }}>{t("Реклама подтверждена", "Реклама підтверджена")}</b>
                : r.attribution_status === "organic" ? <span style={{ color: "#7c3aed" }}>{t("Органика", "Органіка")}</span>
                  : <span style={{ color: "#d97706" }}>{t("Источник объявления не определён", "Джерело оголошення не визначене")}</span>,
              r.meta_identifier || "—", r.funnel, r.stage, dateTime(r.created_at),
            ]),
            t("Обращений Meta за период нет", "Звернень Meta за період немає"), 1200)}
        </>}

        <div className="panel" style={{ marginTop: 12, padding: 14, display: "flex", gap: 16, flexWrap: "wrap", fontSize: 12, alignItems: "center" }}>
          <b>{t("Состояние:", "Стан:")}</b>
          <span>{integration.insights_sync_configured ? "🟢" : "🟡"} Ads Insights</span>
          <span>{integration.content_sync_configured ? "🟢" : "🟡"} Instagram Content</span>
          <span>{integration.latest_account_sync ? "🟢" : "🟡"} Instagram Followers</span>
          <span>{integration.capi_enabled ? "🟢" : "⚪"} Conversions API</span>
          <span>{t("реклама обновлена", "реклама оновлена")}: {dateTime(integration.latest_ads_sync)}</span>
          <span>{t("органика обновлена", "органіка оновлена")}: {dateTime(integration.latest_content_sync)}</span>
          <span>{t("подписчики обновлены", "підписники оновлені")}: {dateTime(integration.latest_account_sync)}</span>
        </div>
      </>}
    </div>
  </div>;
}

function SectionTitle({ title, note }: { title: string; note: string }) {
  return <div style={{ margin: "14px 0 8px" }}><b style={{ fontSize: 16 }}>{title}</b><span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>{note}</span></div>;
}

function Thumb({ src, alt }: { src?: string; alt: string }) {
  return src ? <img src={src} alt={alt} loading="lazy" style={{ width: 82, height: 82, objectFit: "cover", borderRadius: 10, background: "#e2e8f0", flex: "0 0 82px" }} /> :
    <div style={{ width: 82, height: 82, borderRadius: 10, background: "#e2e8f0", display: "grid", placeItems: "center", fontSize: 28, flex: "0 0 82px" }}>🖼️</div>;
}

function AdCard({ row, t }: { row: any; t: (ru: string, ua: string) => string }) {
  return <div className="panel" style={{ padding: 13 }}>
    <div style={{ display: "flex", gap: 11 }}>
      <Thumb src={row.thumbnail_url} alt={row.name || "Meta ad"} />
      <div style={{ minWidth: 0 }}>
        <b style={{ display: "block", lineHeight: 1.3 }}>{row.name || row.id}</b>
        <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>{row.campaign_name || "—"}</div>
        <div className="muted" style={{ fontSize: 10 }}>{row.adset_name || "—"}</div>
        {row.permalink_url && <a href={row.permalink_url} target="_blank" rel="noreferrer" style={{ fontSize: 11 }}>{t("Открыть", "Відкрити")} ↗</a>}
      </div>
    </div>
    <div style={metricGrid}>
      <Metric label={t("Расход", "Витрати")} value={moneyUsd(row.spend)} />
      <Metric label={t("Диалоги Meta", "Діалоги Meta")} value={count(row.messages_started)} />
      <Metric label={t("Лиды Meta", "Ліди Meta")} value={count(row.meta_leads)} />
      <Metric label={t("Лиды CRM", "Ліди CRM")} value={count(row.crm_leads)} />
      <Metric label="CTR" value={row.ctr == null ? "—" : `${row.ctr}%`} />
      <Metric label={t("Цена диалога", "Ціна діалогу")} value={row.cost_per_message == null ? "—" : moneyUsd(row.cost_per_message)} />
    </div>
  </div>;
}

function ContentCard({ row, t }: { row: any; t: (ru: string, ua: string) => string }) {
  const type = row.media_product_type || row.media_type || "POST";
  const contentMetric = (value: any) => optional(value, "", t("нет данных", "немає даних"));
  return <div className="panel" style={{ padding: 13 }}>
    <div style={{ display: "flex", gap: 11 }}>
      <Thumb src={row.thumbnail_url} alt={type} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><b>{type}</b><span className="muted" style={{ fontSize: 10 }}>{dateTime(row.published_at)}</span></div>
        <div style={{ fontSize: 12, lineHeight: 1.35, marginTop: 5, display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{row.caption || t("Без подписи", "Без підпису")}</div>
        {row.permalink && <a href={row.permalink} target="_blank" rel="noreferrer" style={{ fontSize: 11 }}>{t("Открыть публикацию", "Відкрити публікацію")} ↗</a>}
      </div>
    </div>
    <div style={metricGrid}>
      <Metric label={t("Охват", "Охоплення")} value={contentMetric(row.reach)} />
      <Metric label={t("Просмотры", "Перегляди")} value={contentMetric(row.views)} />
      <Metric label={t("Лайки", "Вподобання")} value={count(row.likes)} />
      <Metric label={t("Комментарии", "Коментарі")} value={count(row.comments)} />
      <Metric label={t("Сохранения", "Збереження")} value={contentMetric(row.saved)} />
      <Metric label={t("Поделились", "Поширення")} value={contentMetric(row.shares)} />
      <Metric label={t("Подписчики", "Підписники")} value={contentMetric(row.follows)} accent />
      <Metric label={t("Визиты профиля", "Візити профілю")} value={contentMetric(row.profile_visits)} />
      <Metric label={t("Вовлечённость", "Залученість")} value={row.engagement_rate == null ? "—" : `${row.engagement_rate}%`} />
      <Metric label={t("Диалоги CRM", "Діалоги CRM")} value={count(row.crm_dialogues)} />
    </div>
    <div className="muted" style={{ fontSize: 9, marginTop: 8 }}>{t("Обновлено", "Оновлено")}: {dateTime(row.synced_at)}</div>
  </div>;
}

function Metric({ label, value, accent = false }: { label: string; value: ReactNode; accent?: boolean }) {
  return <div style={{ background: accent ? "#ecfdf5" : "#f8fafc", borderRadius: 8, padding: "7px 8px" }}>
    <div className="muted" style={{ fontSize: 9 }}>{label}</div>
    <div style={{ fontSize: 13, fontWeight: 800, color: accent ? "#047857" : "#0f172a", marginTop: 2 }}>{value}</div>
  </div>;
}

function Empty({ text }: { text: string }) {
  return <div className="panel muted" style={{ padding: 28, textAlign: "center", gridColumn: "1 / -1" }}>{text}</div>;
}

const cardsRow: any = { display: "flex", gap: 9, flexWrap: "wrap", marginBottom: 10 };
const metricGrid: any = { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 6, marginTop: 12 };
const th: any = { textAlign: "left", padding: "10px 12px", fontSize: 12, color: "#64748b", borderBottom: "2px solid #e2e8f0", whiteSpace: "nowrap" };
const td: any = { padding: "10px 12px", fontSize: 13, borderBottom: "1px solid #eef2f7", verticalAlign: "top" };
const dateLabel: any = { display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#64748b" };
const dateInput: any = { height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px", background: "#fff" };
