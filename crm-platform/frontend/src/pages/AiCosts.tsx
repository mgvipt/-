/* Расходы на искусственный интеллект — детально, простым языком, со скроллом и фильтром по дням. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

const MODEL_RU: any = {
  "claude-haiku-4-5": "Хайку (самая дешёвая)", "claude-sonnet-4-6": "Сонет (средняя)",
  "claude-sonnet-4-5": "Сонет (средняя)", "claude-opus-4-8": "Опус (умная, дорогая)",
  "claude-opus-4-7": "Опус (умная, дорогая)", "ChatPlace": "ChatPlace (внешний сервис)",
};
// Что делает + где найти — простыми словами
const GUIDE: any = {
  "Оценка качества диалога (коуч)": "Читает переписку с клиентом и ставит оценку, насколько хорошо менеджер ведёт к продаже, + советует как ответить лучше. Где: открой карточку сделки или лида → блок «Аналітик продажів — коуч» → кнопка «Оцінити якість».",
  "Помощник: напоминания дожать клиента": "Сам проверяет лиды: если клиент перестал отвечать — создаёт менеджеру задачу «напомнить клиенту», и двигает сделку по этапам. Где: задачи появляются у менеджера в его списке задач. Работает в фоне.",
  "Помощник: важность чатов (какой срочный)": "Смотрит чаты и ставит цветную метку — какой клиент срочный или недовольный — чтобы менеджер отвечал важным первым. Где: раздел «Чати · Відкриті лінії» — цветная метка на каждом чате.",
  "Подсказка ответа клиенту": "Предлагает готовый вариант ответа клиенту — менеджер вставляет одним кликом. Где: в чате (Чати · Відкриті лінії), кнопка подсказки.",
  "Телеграм-бот руководителя (кому позвонить / кого вернуть)": "Телеграм-бот для руководителя: показывает список клиентов, кому стоит позвонить сейчас; список давних клиентов, кого можно вернуть; справку по клиенту. Ещё ставит на паузу ИИ-продавца Юлю, когда в чат заходит живой менеджер. Где: в Телеграме, бот @wallcov_rop_bot.",
  "Телеграм-бот склада (учёт накладных)": "Телеграм-бот для склада — помогает оформлять приход и отгрузку товара (накладные). Где: в Телеграме, бот склада.",
  "Продавец Юля в Instagram/TikTok (ChatPlace)": "Главный ИИ-продавец — сам общается с клиентами в Instagram и TikTok, отвечает и продаёт. Где: личные сообщения Instagram/TikTok, настройки в сервисе ChatPlace. Деньги за него платятся отдельно подпиской ChatPlace, не через нашу систему.",
  "ИИ: конвертация лида в сделку": "Читает диалог с клиентом и решает, созрел ли лид в сделку (взял тестовый набор или основной продукт). Если да — сам создаёт сделку. Работает в фоне (раз в 15 минут) и проверяет ТОЛЬКО тех лидов, у кого появилось новое сообщение — молчащих не трогает, деньги на них не тратит. Где: лид сам превращается в сделку, в истории сделки пометка «Створено AI з ліда».",
  "other": "Технические/неподписанные вызовы. В норме тут должен быть 0. Если здесь появились деньги — значит какая-то новая функция забыла «представиться», её надо подписать (это сигнал разработчику).",
  "Помощник CRM (советы и расчёты)": "Разные функции по кнопке — советник «как увеличить прибыль», расчёт стратегии, рекомендации. Где: в разных местах CRM по кнопкам (финансы, карточки).",
  "Приём фото от клиента в чат": "Когда клиент присылает фото в Instagram/TikTok — оно появляется прямо в чате CRM (картинка, по клику откроется крупно). НЕ тратит токены ИИ: фото просто пересылается ссылкой (использует уже оплаченную обработку Юли в ChatPlace). Сейчас в процессе подключения: ждём одобрения Instagram/Meta (заявка подана) либо настройки пересылки в ChatPlace. Пока подключаем — в чате видна пометка «клиент прислал фото» и ссылка открыть Instagram. Где: чат клиента в «Чати · Відкриті лінії».",
};

// Повний довідник УСІХ функцій, що звертаються до ШІ (щоб бачити всі, навіть з 0 за сьогодні).
// [назва, модель, коли працює, чи перевіряє тільки чати з новим повідомленням]
const CATALOG: any[] = [
  ["Продавец Юля в Instagram/TikTok (ChatPlace)", "ChatPlace", "Фоном 24/7", "Оплата подпиской ChatPlace"],
  ["Помощник: важность чатов (какой срочный)", "Хайку", "Фоном, раз в 5 мин", "Да — только чаты с новым сообщением"],
  ["ИИ: конвертация лида в сделку", "Хайку", "Фоном, раз в 15 мин", "Да — только лиды с новым сообщением"],
  ["Помощник: напоминания дожать клиента", "Сонет", "Фоном, раз в 10 мин", "Проверяет лиды без ответа"],
  ["Оценка качества диалога (коуч)", "Сонет", "По кнопке (+ авто на звонках)", "Только по запросу"],
  ["Подсказка ответа клиенту", "Сонет", "По кнопке в чате", "Только по запросу"],
  ["Помощник CRM (советы и расчёты)", "Сонет", "По кнопке (финансы, карточки)", "Только по запросу"],
  ["Телеграм-бот руководителя (кому позвонить / кого вернуть)", "Сонет", "По запросу в Телеграме", "Отдельный ключ"],
  ["Телеграм-бот склада (учёт накладных)", "Сонет", "По запросу в Телеграме", "Отдельный ключ"],
  ["Приём фото от клиента в чат", "ChatPlace / Meta", "При получении фото", "~$0 — без токенов ИИ (пересылка ссылки)"],
];

export default function AiCosts() {
  const { t } = useLang();
  const [d, setD] = useState<any>(null);
  const [ac, setAc] = useState<any>(null);                  // повний рахунок Anthropic по ключах
  const [preset, setPreset] = useState<string>("");        // "", today, yesterday, 7, 30, 90, year, prevyear, day, custom
  const [dayDate, setDayDate] = useState<string>("");       // конкретний день
  const [fromDate, setFromDate] = useState<string>("");     // свій діапазон — з
  const [toDate, setToDate] = useState<string>("");         // свій діапазон — по
  const isoDay = (dt: Date) => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
  function buildQuery(): string {
    const today = new Date(); const y = today.getFullYear();
    const q = (o: Record<string, string>) => "?" + Object.entries(o).map(([k, v]) => k + "=" + v).join("&");
    switch (preset) {
      case "today": { const dd = isoDay(today); return q({ from: dd, to: dd }); }
      case "yesterday": { const yd = new Date(today); yd.setDate(yd.getDate() - 1); const dd = isoDay(yd); return q({ from: dd, to: dd }); }
      case "7": return q({ days: "7" });
      case "30": return q({ days: "30" });
      case "90": return q({ days: "90" });
      case "year": return q({ from: y + "-01-01", to: isoDay(today) });
      case "prevyear": return q({ from: (y - 1) + "-01-01", to: (y - 1) + "-12-31" });
      case "day": return dayDate ? q({ from: dayDate, to: dayDate }) : "";
      case "custom": { const o: any = {}; if (fromDate) o.from = fromDate; if (toDate) o.to = toDate; return Object.keys(o).length ? q(o) : ""; }
      default: return "";
    }
  }
  useEffect(() => { const qq = buildQuery(); api.get<any>("/api/ai-usage/" + qq).then(setD).catch(() => {}); api.get<any>("/api/ai-usage/anthropic/" + qq).then(setAc).catch(() => setAc({ configured: false })); /* eslint-disable-next-line */ }, [preset, dayDate, fromDate, toDate]);
  function exportCsv() {
    if (!d) return;
    const rows: any[] = [["Помічник / функція", "Модель", "Звернень", "Сума USD"]];
    (d.by_source || []).forEach((r: any) => rows.push([r.source, r.model || "", r.calls, (Number(r.cost) || 0).toFixed(4)]));
    const csv = rows.map((r) => r.map((c: any) => '"' + String(c).replace(/"/g, '""') + '"').join(",")).join("\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "ai-vitraty.csv"; a.click();
  }
  const usd = (v: number) => "$" + (Number(v) || 0).toFixed(2);
  const num = (v: number) => (Number(v) || 0).toLocaleString("ru-RU");
  const th: any = { textAlign: "left", padding: "7px 9px", fontSize: 12, color: "#64748b", borderBottom: "2px solid #eef2f7" };
  const td: any = { padding: "7px 9px", fontSize: 13, borderBottom: "1px solid #f1f5f9", verticalAlign: "top" };
  const Card = ({ label, val, color }: any) => (
    <div className="panel" style={{ flex: 1, minWidth: 150, padding: "14px 16px" }}>
      <div className="muted" style={{ fontSize: 12 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 800, color: color || "#0f172a" }}>{val}</div>
    </div>
  );
  const selSt: any = { height: 32, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", fontSize: 13, background: "#fff" };
  const dateSt: any = { height: 32, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 13 };

  return (
    <div style={{ height: "100%", overflowY: "auto", boxSizing: "border-box", padding: 16 }}>
      <div style={{ maxWidth: 1060 }}>
        <h2 style={{ fontSize: 22, display: "flex", alignItems: "center", gap: 8, margin: "0 0 10px" }}><Icon n="money" size={20} /> {t("Расходы на искусственный интеллект", "Витрати на штучний інтелект")}</h2>

        <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: 12 }}>{t("Период:", "Період:")}</span>
          <select value={preset} onChange={(e) => setPreset(e.target.value)} style={selSt}>
            <option value="">{t("Весь период", "Весь період")}</option>
            <option value="today">{t("Сегодня", "Сьогодні")}</option>
            <option value="yesterday">{t("Вчера", "Вчора")}</option>
            <option value="7">{t("Последние 7 дней", "Останні 7 днів")}</option>
            <option value="30">{t("Последние 30 дней", "Останні 30 днів")}</option>
            <option value="90">{t("Последние 90 дней", "Останні 90 днів")}</option>
            <option value="year">{t("Этот год", "Цей рік")}</option>
            <option value="prevyear">{t("Прошлый год", "Минулий рік")}</option>
            <option value="day">{t("Конкретный день…", "Конкретний день…")}</option>
            <option value="custom">{t("Свой диапазон (месяцы)…", "Свій діапазон (місяці)…")}</option>
          </select>
          {preset === "day" && <input type="date" value={dayDate} onChange={(e) => setDayDate(e.target.value)} style={dateSt} />}
          {preset === "custom" && <>
            <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} style={dateSt} title={t("С", "З")} />
            <span className="muted" style={{ fontSize: 12 }}>—</span>
            <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} style={dateSt} title={t("По", "По")} />
          </>}
          {(preset === "day" && !dayDate) && <span className="muted" style={{ fontSize: 11.5, color: "#d97706" }}>{t("выберите дату", "оберіть дату")}</span>}
          <div style={{ flex: 1 }} />
          <button className="btn btn-light" style={{ fontSize: 13 }} onClick={exportCsv}>📥 {t("Экспорт CSV", "Експорт CSV")}</button>
        </div>

        {!d ? <div className="muted">…</div> : <>
        <div className="note" style={{ marginBottom: 14, lineHeight: 1.6 }}>
          <b>{t("Как читать:", "Як читати:")}</b> {t("сколько денег тратит каждый «умный помощник» (ИИ) в системе. Чем больше текста он обрабатывает и чем «умнее» модель — тем дороже.", "скільки грошей витрачає кожен «розумний помічник» (ШІ). Чим більше тексту і чим «розумніша» модель — тим дорожче.")}<br />
          • <b>{t("Оценка", "Оцінка")}</b> {t("— приблизный расход за прошлые дни (точный учёт включили 01.07.2026).", "— приблизні витрати за минулі дні (точний облік увімкнули 01.07.2026).")} • <b>{t("Точно", "Точно")}</b> {t("— факт с 01.07.2026.", "— факт з 01.07.2026.")}
        </div>

        <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <Card label={t("Всего потрачено", "Всього витрачено")} val={usd(d.total_cost)} color="#166534" />
          <Card label={t("Оценка (прошлое)", "Оцінка (минуле)")} val={usd(d.est_cost)} color="#9a3412" />
          <Card label={t("Точно (с 01.07)", "Точно (з 01.07)")} val={usd(d.live_cost)} color="#1d4ed8" />
          <Card label={t("Обращений к ИИ", "Звернень до ШІ")} val={num(d.total_calls)} />
          {(d.days || []).length > 0 && <Card label={t("В среднем / день", "В середньому / день")} val={usd((d.total_cost || 0) / (d.days.length || 1))} color="#7c3aed" />}
          {(d.days || []).length > 1 && <Card label={t("Прогноз на месяц", "Прогноз на місяць")} val={usd((d.total_cost || 0) / (d.days.length || 1) * 30)} color="#be185d" />}
        </div>
        {(d.days || []).length > 1 && (() => {
          const days = [...(d.days || [])].reverse();
          const mx = Math.max(...days.map((x: any) => Number(x.cost) || 0), 0.0001);
          return (
            <div className="panel" style={{ marginBottom: 16 }}>
              <div className="label" style={{ marginBottom: 8 }}>{t("Расход по дням", "Витрати по днях")}</div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 120, overflowX: "auto" }}>
                {days.map((x: any, i: number) => (
                  <div key={i} title={x.d + ": " + usd(x.cost) + " · " + num(x.calls) + (t(" обращений", " звернень"))} style={{ flex: "1 0 6px", minWidth: 6, height: Math.max(2, (Number(x.cost) || 0) / mx * 110), background: "#818cf8", borderRadius: "3px 3px 0 0" }} />
                ))}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "#94a3b8", marginTop: 4 }}><span>{days[0]?.d}</span><span>{days[days.length - 1]?.d}</span></div>
            </div>
          );
        })()}

        {ac && (ac.configured ? (
          <div className="panel" style={{ marginBottom: 14, border: "2px solid #c7d2fe" }}>
            <div className="label" style={{ marginBottom: 4 }}>{t("Полный счёт Anthropic — ВСЕ боты (по ключам)", "Повний рахунок Anthropic — УСІ боти (по ключах)")}</div>
            <div className="muted" style={{ fontSize: 11.5, marginBottom: 8 }}>{t("Реальные списания из Anthropic по каждому сервису — включая ботов вне CRM (склад, контент, командный центр, реклама).", "Реальні списання з Anthropic по кожному сервісу — включно з ботами поза CRM.")}</div>
            {ac.error ? <div style={{ color: "#dc2626", fontSize: 12 }}>{ac.error}</div> : <>
              <div style={{ fontSize: 26, fontWeight: 800, color: "#166534", marginBottom: 8 }}>{usd(ac.total)}<span className="muted" style={{ fontSize: 12, fontWeight: 400 }}> {t("— реальный расход ботов (API-ключи) за период", "— реальний розхід ботів (API-ключі) за період")}</span></div>
              {ac.org_total != null && ac.org_total > (ac.total || 0) * 1.5 && (
                <div style={{ fontSize: 12, color: "#9a3412", background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 8, padding: "8px 10px", marginBottom: 10, lineHeight: 1.5 }}>
                  ⚠️ <b>{t("Весь аккаунт Anthropic за период: ", "Весь акаунт Anthropic за період: ")}{usd(ac.org_total)}</b><br />
                  {t("Сюда входят сессии Claude Code (агенты, закреплённые сессии) и подписка — а не только боты. Если Claude Code у тебя на фикс-подписке (Max/Team) — это НЕ отдельный счёт по токенам. Сверь с реальным инвойсом Anthropic.", "Сюди входять сесії Claude Code (агенти, закріплені сесії) і підписка — а не тільки боти. Якщо Claude Code на фікс-підписці (Max/Team) — це НЕ окремий рахунок по токенах. Звір з реальним інвойсом Anthropic.")}
                </div>
              )}
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr><th style={th}>{t("Ключ / сервис", "Ключ / сервіс")}</th><th style={{ ...th, textAlign: "right" }}>{t("Сумма", "Сума")}</th></tr></thead>
                <tbody>{(ac.rows || []).map((r: any, i: number) => <tr key={i}><td style={td}>{r.key}</td><td style={{ ...td, textAlign: "right", fontWeight: 700 }}>{usd(r.cost)}</td></tr>)}</tbody>
              </table>
            </>}
          </div>
        ) : (
          <div className="note" style={{ marginBottom: 14, background: "#fffbeb", borderColor: "#fde68a", lineHeight: 1.5 }}>
            ⚠️ <b>{t("Полный счёт (все боты):", "Повний рахунок (усі боти):")}</b> {t("чтобы видеть ВЕСЬ расход (включая склад, контент, командный центр, рекламу — они тратят вне CRM), нужен Admin-ключ Anthropic. Создай его в консоли (Settings → Admin keys) и пришли — подключу за минуту.", "щоб бачити ВЕСЬ розхід (включно зі складом, контентом, командним центром, рекламою — вони витрачають поза CRM), потрібен Admin-ключ Anthropic. Створи в консолі (Settings → Admin keys) і пришли — підключу.")}
          </div>
        ))}
        <div className="panel" style={{ marginBottom: 14 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("Куда идут деньги — по каждому помощнику (внутри CRM)", "Куди йдуть гроші — по кожному помічнику (всередині CRM)")}</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><th style={th}>{t("Помощник / функция", "Помічник / функція")}</th><th style={th}>{t("Модель", "Модель")}</th><th style={th}>{t("Обращений", "Звернень")}</th><th style={{ ...th, textAlign: "right" }}>{t("Сумма", "Сума")}</th></tr></thead>
            <tbody>{(d.by_source || []).map((r: any, i: number) => (
              <tr key={i}>
                <td style={{ ...td, maxWidth: 560 }}><div style={{ fontWeight: 600 }}>{r.source}</div>{GUIDE[r.source] && <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.45, marginTop: 2 }}>{GUIDE[r.source]}</div>}{r.note && !GUIDE[r.source] && <div className="muted" style={{ fontSize: 11 }}>{r.note}</div>}</td>
                <td style={{ ...td, fontSize: 11.5, color: "#64748b", whiteSpace: "nowrap" }}>{MODEL_RU[r.model] || r.model || "—"}</td>
                <td style={td}>{num(r.calls)}</td>
                <td style={{ ...td, textAlign: "right", fontWeight: 700 }}>{usd(r.cost)}</td>
              </tr>))}</tbody>
          </table>
        </div>

        <div className="panel" style={{ marginBottom: 14 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("Справочник: все ИИ-функции системы", "Довідник: усі ШІ-функції системи")}</div>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 8 }}>{t("Полный список всего, что обращается к искусственному интеллекту — чтобы вы видели каждую функцию, даже если сегодня она ничего не потратила.", "Повний список усього, що звертається до ШІ — щоб ви бачили кожну функцію, навіть якщо сьогодні вона нічого не витратила.")}</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><th style={th}>{t("Функция", "Функція")}</th><th style={th}>{t("Модель", "Модель")}</th><th style={th}>{t("Когда работает", "Коли працює")}</th><th style={th}>{t("Экономия / примечание", "Економія / примітка")}</th></tr></thead>
            <tbody>{CATALOG.map((r: any, i: number) => (
              <tr key={i}>
                <td style={{ ...td, maxWidth: 340 }}><div style={{ fontWeight: 600 }}>{r[0]}</div>{GUIDE[r[0]] && <div className="muted" style={{ fontSize: 11, lineHeight: 1.4, marginTop: 2 }}>{GUIDE[r[0]]}</div>}</td>
                <td style={td}>{r[1]}</td>
                <td style={td}>{r[2]}</td>
                <td style={{ ...td, fontSize: 12 }}>{r[3]}</td>
              </tr>))}</tbody>
          </table>
        </div>

        <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
          <div className="panel" style={{ flex: 1, minWidth: 280 }}>
            <div className="label" style={{ marginBottom: 6 }}>{t("По «уму» модели (дороже = умнее)", "По «розуму» моделі (дорожче = розумніша)")}</div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr><th style={th}>{t("Модель", "Модель")}</th><th style={th}>{t("Обращений", "Звернень")}</th><th style={{ ...th, textAlign: "right" }}>{t("Сумма", "Сума")}</th></tr></thead>
              <tbody>{(d.by_model || []).map((r: any, i: number) => <tr key={i}><td style={td}>{MODEL_RU[r.model] || r.model}</td><td style={td}>{num(r.calls)}</td><td style={{ ...td, textAlign: "right", fontWeight: 700 }}>{usd(r.cost)}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="panel" style={{ flex: 1, minWidth: 280 }}>
            <div className="label" style={{ marginBottom: 6 }}>{t("По дням", "По днях")}</div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr><th style={th}>{t("День", "День")}</th><th style={th}>{t("Обращений", "Звернень")}</th><th style={{ ...th, textAlign: "right" }}>{t("Сумма", "Сума")}</th></tr></thead>
              <tbody>{(d.days || []).map((r: any, i: number) => <tr key={i}><td style={td}>{r.d}</td><td style={td}>{num(r.calls)}</td><td style={{ ...td, textAlign: "right", fontWeight: 700 }}>{usd(r.cost)}</td></tr>)}</tbody>
            </table>
          </div>
        </div>

        <div className="panel" style={{ marginTop: 14, marginBottom: 30 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("Подробно: день и помощник", "Детально: день і помічник")}</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><th style={th}>{t("День", "День")}</th><th style={th}>{t("Помощник / функция", "Помічник / функція")}</th><th style={th}>{t("Обращений", "Звернень")}</th><th style={{ ...th, textAlign: "right" }}>{t("Сумма", "Сума")}</th></tr></thead>
            <tbody>{(d.day_source || []).map((r: any, i: number) => <tr key={i}><td style={td}>{r.d}</td><td style={td}>{r.source}</td><td style={td}>{num(r.calls)}</td><td style={{ ...td, textAlign: "right" }}>{usd(r.cost)}</td></tr>)}</tbody>
          </table>
        </div>
        </>}
      </div>
    </div>
  );
}
