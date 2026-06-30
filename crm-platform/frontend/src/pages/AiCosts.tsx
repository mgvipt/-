/* Детальний звіт витрат на Claude — по днях, функціях, моделях. Дані з /api/ai-usage. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

export default function AiCosts() {
  const { t } = useLang();
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.get<any>("/api/ai-usage/").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="muted" style={{ padding: 16 }}>…</div>;
  const usd = (v: number) => "$" + (Number(v) || 0).toFixed(2);
  const kt = (v: number) => { v = Number(v) || 0; return v >= 1000 ? (v / 1000).toFixed(1) + "k" : String(v); };
  const card: any = { flex: 1, padding: "14px 16px" };
  const th: any = { textAlign: "left", padding: "6px 8px", fontSize: 12, color: "#64748b", borderBottom: "2px solid #eef2f7" };
  const td: any = { padding: "6px 8px", fontSize: 13, borderBottom: "1px solid #f1f5f9" };
  return (
    <div style={{ padding: 16, maxWidth: 1040 }}>
      <h2 style={{ fontSize: 22, display: "flex", alignItems: "center", gap: 8, margin: "0 0 4px" }}><Icon n="money" size={20} /> {t("Расходы ИИ (Claude)", "Витрати ШІ (Claude)")}</h2>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>{t("Точный лог каждого вызова — с момента включения (01.07.2026). Историю до этой даты Anthropic даёт только по модели в консоли.", "Точний лог кожного виклику — з моменту увімкнення (01.07.2026). Історію до цієї дати Anthropic дає лише по моделі в консолі.")}</div>

      <div style={{ display: "flex", gap: 12, marginBottom: 14 }}>
        <div className="panel" style={card}><div className="muted" style={{ fontSize: 12 }}>{t("Всего", "Всього")}</div><div style={{ fontSize: 30, fontWeight: 800, color: "#166534" }}>{usd(d.total_cost)}</div></div>
        <div className="panel" style={card}><div className="muted" style={{ fontSize: 12 }}>{t("Вызовов ИИ", "Викликів ШІ")}</div><div style={{ fontSize: 30, fontWeight: 800 }}>{d.total_calls}</div></div>
      </div>

      <div className="panel" style={{ marginBottom: 14 }}>
        <div className="label" style={{ marginBottom: 6 }}>{t("По функциям (куда идут деньги)", "По функціях (куди йдуть гроші)")}</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>{t("Функция", "Функція")}</th><th style={th}>{t("Вызовов", "Викликів")}</th><th style={th}>{t("Токены in/out", "Токени in/out")}</th><th style={{ ...th, textAlign: "right" }}>{t("Стоимость", "Вартість")}</th></tr></thead>
          <tbody>{(d.by_source || []).map((r: any, i: number) => <tr key={i}><td style={td}>{r.source}</td><td style={td}>{r.calls}</td><td style={td}>{kt(r.itok)} / {kt(r.otok)}</td><td style={{ ...td, textAlign: "right", fontWeight: 700 }}>{usd(r.cost)}</td></tr>)}
          {(!d.by_source || !d.by_source.length) && <tr><td style={td} colSpan={4}><span className="muted">{t("Пока нет вызовов с момента включения лога", "Поки немає викликів з моменту увімкнення логу")}</span></td></tr>}</tbody>
        </table>
      </div>

      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        <div className="panel" style={{ flex: 1, minWidth: 300 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("По моделям", "По моделях")}</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><th style={th}>{t("Модель", "Модель")}</th><th style={th}>{t("Вызовов", "Викликів")}</th><th style={{ ...th, textAlign: "right" }}>$</th></tr></thead>
            <tbody>{(d.by_model || []).map((r: any, i: number) => <tr key={i}><td style={td}>{r.model}</td><td style={td}>{r.calls}</td><td style={{ ...td, textAlign: "right", fontWeight: 700 }}>{usd(r.cost)}</td></tr>)}</tbody>
          </table>
        </div>
        <div className="panel" style={{ flex: 1, minWidth: 300 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("По дням", "По днях")}</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr><th style={th}>{t("День", "День")}</th><th style={th}>{t("Вызовов", "Викликів")}</th><th style={{ ...th, textAlign: "right" }}>$</th></tr></thead>
            <tbody>{(d.days || []).map((r: any, i: number) => <tr key={i}><td style={td}>{r.d}</td><td style={td}>{r.calls}</td><td style={{ ...td, textAlign: "right", fontWeight: 700 }}>{usd(r.cost)}</td></tr>)}</tbody>
          </table>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="label" style={{ marginBottom: 6 }}>{t("Детально: день × функция", "Детально: день × функція")}</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>{t("День", "День")}</th><th style={th}>{t("Функция", "Функція")}</th><th style={th}>{t("Вызовов", "Викликів")}</th><th style={{ ...th, textAlign: "right" }}>$</th></tr></thead>
          <tbody>{(d.day_source || []).map((r: any, i: number) => <tr key={i}><td style={td}>{r.d}</td><td style={td}>{r.source}</td><td style={td}>{r.calls}</td><td style={{ ...td, textAlign: "right" }}>{usd(r.cost)}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}
