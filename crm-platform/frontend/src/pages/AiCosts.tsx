/* Расходы на искусственный интеллект — детально, простым языком. Данные: /api/ai-usage. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

const MODEL_RU: any = {
  "claude-haiku-4-5": "Хайку (самая дешёвая)", "claude-sonnet-4-6": "Сонет (средняя)",
  "claude-sonnet-4-5": "Сонет (средняя)", "claude-opus-4-8": "Опус (умная, дорогая)",
  "claude-opus-4-7": "Опус (умная, дорогая)", "ChatPlace": "ChatPlace (внешний сервис)",
};

export default function AiCosts() {
  const { t } = useLang();
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.get<any>("/api/ai-usage/").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="muted" style={{ padding: 16 }}>…</div>;
  const usd = (v: number) => "$" + (Number(v) || 0).toFixed(2);
  const num = (v: number) => (Number(v) || 0).toLocaleString("ru-RU");
  const th: any = { textAlign: "left", padding: "7px 9px", fontSize: 12, color: "#64748b", borderBottom: "2px solid #eef2f7" };
  const td: any = { padding: "7px 9px", fontSize: 13, borderBottom: "1px solid #f1f5f9", verticalAlign: "top" };
  const Card = ({ label, val, color, sub }: any) => (
    <div className="panel" style={{ flex: 1, minWidth: 150, padding: "14px 16px" }}>
      <div className="muted" style={{ fontSize: 12 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 800, color: color || "#0f172a" }}>{val}</div>
      {sub && <div className="muted" style={{ fontSize: 11 }}>{sub}</div>}
    </div>
  );

  return (
    <div style={{ padding: 16, maxWidth: 1060 }}>
      <h2 style={{ fontSize: 22, display: "flex", alignItems: "center", gap: 8, margin: "0 0 4px" }}><Icon n="money" size={20} /> {t("Расходы на искусственный интеллект", "Витрати на штучний інтелект")}</h2>

      <div className="note" style={{ marginBottom: 14, lineHeight: 1.6 }}>
        <b>{t("Как читать эту страницу:", "Як читати цю сторінку:")}</b><br />
        {t("Здесь видно, сколько денег тратит каждый «умный помощник» (ИИ), который работает в нашей системе. Чем больше он обрабатывает текста и чем «умнее» модель — тем дороже.", "Тут видно, скільки грошей витрачає кожен «розумний помічник» (ШІ), який працює в нашій системі. Чим більше тексту він обробляє і чим «розумніша» модель — тим дорожче.")}<br />
        • <b>{t("Оценка", "Оцінка")}</b> {t("— это расход ЗА ПРОШЛЫЕ ДНИ, посчитанный приблизительно (точный учёт по каждому помощнику мы включили только 01.07.2026).", "— це витрати ЗА МИНУЛІ ДНІ, пораховані приблизно (точний облік по кожному помічнику ми увімкнули лише 01.07.2026).")}<br />
        • <b>{t("Точно", "Точно")}</b> {t("— расход С 01.07.2026, посчитанный по факту каждого обращения к ИИ. С каждым днём этих точных данных будет больше.", "— витрати З 01.07.2026, пораховані по факту кожного звернення до ШІ. З кожним днем цих точних даних буде більше.")}
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <Card label={t("Всего потрачено", "Всього витрачено")} val={usd(d.total_cost)} color="#166534" />
        <Card label={t("Из них: оценка (прошлое)", "З них: оцінка (минуле)")} val={usd(d.est_cost)} color="#9a3412" />
        <Card label={t("Из них: точно (с 01.07)", "З них: точно (з 01.07)")} val={usd(d.live_cost)} color="#1d4ed8" />
        <Card label={t("Обращений к ИИ", "Звернень до ШІ")} val={num(d.total_calls)} />
      </div>

      <div className="panel" style={{ marginBottom: 14 }}>
        <div className="label" style={{ marginBottom: 6 }}>{t("Куда идут деньги — по каждому помощнику", "Куди йдуть гроші — по кожному помічнику")}</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>{t("Помощник / функция", "Помічник / функція")}</th><th style={th}>{t("Обращений", "Звернень")}</th><th style={{ ...th, textAlign: "right" }}>{t("Сумма", "Сума")}</th></tr></thead>
          <tbody>{(d.by_source || []).map((r: any, i: number) => (
            <tr key={i}>
              <td style={td}><div style={{ fontWeight: 600 }}>{r.source}</div>{r.note && <div className="muted" style={{ fontSize: 11 }}>{r.note}</div>}</td>
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

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="label" style={{ marginBottom: 6 }}>{t("Подробно: день и помощник", "Детально: день і помічник")}</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>{t("День", "День")}</th><th style={th}>{t("Помощник / функция", "Помічник / функція")}</th><th style={th}>{t("Обращений", "Звернень")}</th><th style={{ ...th, textAlign: "right" }}>{t("Сумма", "Сума")}</th></tr></thead>
          <tbody>{(d.day_source || []).map((r: any, i: number) => <tr key={i}><td style={td}>{r.d}</td><td style={td}>{r.source}</td><td style={td}>{num(r.calls)}</td><td style={{ ...td, textAlign: "right" }}>{usd(r.cost)}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
