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
  "Помощник CRM (советы и расчёты)": "Разные функции по кнопке — советник «как увеличить прибыль», расчёт стратегии, рекомендации. Где: в разных местах CRM по кнопкам (финансы, карточки).",
};

export default function AiCosts() {
  const { t } = useLang();
  const [d, setD] = useState<any>(null);
  const [range, setRange] = useState<string>("");
  useEffect(() => { api.get<any>("/api/ai-usage/" + (range ? "?days=" + range : "")).then(setD).catch(() => {}); }, [range]);
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
  const RangeBtn = ({ v, label }: any) => (
    <button onClick={() => setRange(v)} className={"btn" + (range === v ? " btn-primary" : "")} style={{ fontSize: 13 }}>{label}</button>
  );

  return (
    <div style={{ height: "100%", overflowY: "auto", boxSizing: "border-box", padding: 16 }}>
      <div style={{ maxWidth: 1060 }}>
        <h2 style={{ fontSize: 22, display: "flex", alignItems: "center", gap: 8, margin: "0 0 10px" }}><Icon n="money" size={20} /> {t("Расходы на искусственный интеллект", "Витрати на штучний інтелект")}</h2>

        <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span className="muted" style={{ fontSize: 12 }}>{t("Период:", "Період:")}</span>
          <RangeBtn v="" label={t("Весь период", "Весь період")} />
          <RangeBtn v="30" label={t("30 дней", "30 днів")} />
          <RangeBtn v="7" label={t("7 дней", "7 днів")} />
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
        </div>

        <div className="panel" style={{ marginBottom: 14 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("Куда идут деньги — по каждому помощнику", "Куди йдуть гроші — по кожному помічнику")}</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><th style={th}>{t("Помощник / функция", "Помічник / функція")}</th><th style={th}>{t("Обращений", "Звернень")}</th><th style={{ ...th, textAlign: "right" }}>{t("Сумма", "Сума")}</th></tr></thead>
            <tbody>{(d.by_source || []).map((r: any, i: number) => (
              <tr key={i}>
                <td style={{ ...td, maxWidth: 620 }}><div style={{ fontWeight: 600 }}>{r.source}</div>{GUIDE[r.source] && <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.45, marginTop: 2 }}>{GUIDE[r.source]}</div>}{r.note && !GUIDE[r.source] && <div className="muted" style={{ fontSize: 11 }}>{r.note}</div>}</td>
                <td style={td}>{num(r.calls)}</td>
                <td style={{ ...td, textAlign: "right", fontWeight: 700 }}>{usd(r.cost)}</td>
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
