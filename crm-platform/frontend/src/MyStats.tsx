import { useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import { useLang } from "./i18n";

/* «Моя статистика за місяць» (16.09.2026, Олег: «статистика должна быть у каждого») — ті самі дані, що у керівника
 * в ЗП/KPI → «Статистика»: скільки прийшло, робота за днями і по яких угодах. Лише СВОЇ дані:
 * /api/finance/salary/deals/?user=<я> віддає чуже лише керівнику. */

const money = (n: any) => Math.round(Number(n || 0)).toLocaleString("uk-UA") + " ₴";
const dm = (s: string) => (s ? `${s.slice(8, 10)}.${s.slice(5, 7)}` : "");
const CELL: React.CSSProperties = { padding: "4px 6px", textAlign: "right", whiteSpace: "nowrap" };
const dim = (v: any) => (v ? { color: "#0f172a" } : { color: "#cbd5e1" });

export default function MyStats({ period }: { period?: string }) {
  const { t } = useLang();
  const { me } = useAuth();
  const [d, setD] = useState<any>(null);
  const [open, setOpen] = useState(false);       // список угод
  const [shown, setShown] = useState(false);     // 16.09 (Олег): блок угорі й розкривається по кліку
  const per = period || new Date().toISOString().slice(0, 7);
  useEffect(() => {
    let alive = true;
    setD(null);
    if (!me) return;
    api.get<any>(`/api/finance/salary/deals/?user=${me.id}&period=${per}`)
      .then((r) => { if (alive) setD(r); })
      .catch(() => { if (alive) setD({ rows: [], by_day: [], total: 0, deals: 0, count: 0 }); });
    return () => { alive = false; };
  }, [me, per]);
  if (!me) return null;
  const days: any[] = (d?.by_day || []);
  const rows: any[] = (d?.rows || []);
  const H: [string, string][] = [
    [t("Дата", "Дата"), t("День", "День")], [t("Деньги", "Гроші"), t("сколько собрал за день", "скільки зібрав за день")],
    [t("План", "План"), t("дневная норма из плана месяца", "денна норма з плану місяця")],
    [t("Продаж", "Продажів"), t("сделок с оплатой в этот день", "угод з оплатою цього дня")],
    [t("Сам", "Сам"), t("в переписке отвечал живой менеджер", "у переписці відповідала жива людина")],
    [t("ИИ", "ШІ"), t("продажа прошла на ответах ИИ", "продаж пройшов на відповідях ШІ")],
    [t("Осн.", "Осн."), t("основной продукт", "основний продукт")], [t("Тест", "Тест"), t("тестовый набор", "тестовий набір")],
    [t("Офл.", "Офл."), t("салон и алмазное", "салон і алмазне")], [t("Др.", "Інші"), t("другие воронки", "інші воронки")],
    [t("Ср.чек", "Сер.чек"), t("средний чек основной воронки", "середній чек основної воронки")],
    [t("Взял", "Взяв"), t("взял чат или лид в работу", "взяв чат або лід у роботу")],
    [t("Закрыл", "Закрив"), t("завершил чатов", "завершив чатів")],
    [t("Игноры", "Ігнори"), t("вернул клиента из игнора", "повернув клієнта з ігнору")],
    [t("Сообщ.", "Повідом."), t("написал сообщений клиентам", "написав повідомлень клієнтам")],
  ];
  return (
    <div className="card" style={{ padding: 12, marginTop: 10 }}>
      <div className="label" onClick={() => setShown(!shown)} title={t("Нажмите, чтобы раскрыть", "Натисніть, щоб розгорнути")}
        style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", cursor: "pointer", marginBottom: shown ? 6 : 0 }}>
        <span style={{ display: "inline-block", transform: shown ? "none" : "rotate(-90deg)", transition: "transform .15s", color: "#64748b" }}>▾</span>
        📊 {t("Моя статистика за месяц", "Моя статистика за місяць")}
        {d && <span className="muted" style={{ fontSize: 12.5, fontWeight: 400 }}>
          {t("Поступило", "Надійшло")}: <b style={{ color: "#16a34a" }}>{money(d.total)}</b>
          {d.total_fee ? <> · {t("комиссия", "комісія")}: <b style={{ color: "#dc2626" }}>−{money(d.total_fee)}</b></> : null}
          {d.total_net != null ? <> · {t("чисто", "чисто")}: <b style={{ color: "#047857" }}>{money(d.total_net)}</b></> : null}
          {" · "}{d.deals} {t("сделок", "угод")}
        </span>}
      </div>
      {!shown ? null : !d ? <div className="muted" style={{ fontSize: 12.5 }}>{t("Считаем…", "Рахуємо…")}</div> : days.length === 0 ? (
        <div className="muted" style={{ fontSize: 12.5 }}>{t("За этот месяц оплат по вашим сделкам пока нет.", "За цей місяць оплат по ваших угодах поки немає.")}</div>
      ) : (
        <>
          <div style={{ maxHeight: 260, overflow: "auto", border: "1px solid #e5eaf1", borderRadius: 8 }}>
            <table style={{ width: "100%", fontSize: 11.5, borderCollapse: "separate", borderSpacing: 0, minWidth: 760 }}>
              <thead><tr style={{ color: "#475569" }}>{H.map(([lb, tip], i) => (
                <th key={i} title={tip} style={{ position: "sticky", top: 0, background: "#f1f5f9", padding: "5px 6px", textAlign: i === 0 ? "left" : "right", fontSize: 10.5, fontWeight: 700, borderBottom: "1px solid #e2e8f0", whiteSpace: "nowrap" }}>{lb}</th>))}
              </tr></thead>
              <tbody>{days.map((b: any) => (
                <tr key={b.date} style={{ borderTop: "1px solid #f1f5f9" }}>
                  <td style={{ ...CELL, textAlign: "left", fontWeight: 700, color: "#475569" }}>{dm(b.date)}</td>
                  <td style={{ ...CELL, fontWeight: 800, color: "#16a34a" }}>{money(b.amount)}</td>
                  <td style={CELL}>{b.plan_day ? <span style={{ color: (b.plan_pct || 0) >= 100 ? "#16a34a" : "#b45309", fontWeight: 700 }}>{b.plan_pct}%</span> : <span style={{ color: "#cbd5e1" }}>—</span>}</td>
                  <td style={{ ...CELL, fontWeight: 700, ...dim(b.sales) }}>{b.sales || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.sales_self) }}>{b.sales_self || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.sales_ai), color: b.sales_ai ? "#7c3aed" : "#cbd5e1" }}>{b.sales_ai || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.sales_main) }}>{b.sales_main || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.sales_test) }}>{b.sales_test || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.sales_offline), color: b.sales_offline ? "#b45309" : "#cbd5e1" }}>{b.sales_offline || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.sales_other) }}>{b.sales_other || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.avg_check_main || b.avg_check) }}>{b.avg_check_main ? money(b.avg_check_main) : (b.avg_check ? money(b.avg_check) : "—")}</td>
                  <td style={{ ...CELL, ...dim(b.taken) }}>{b.taken || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.closed) }}>{b.closed || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.ignores) }}>{b.ignores || "—"}</td>
                  <td style={{ ...CELL, ...dim(b.msgs) }}>{b.msgs || "—"}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
          {(d.by_funnel || []).length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
              {(d.by_funnel || []).map((f: any, i: number) => (
                <span key={i} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 999, padding: "2px 9px", fontSize: 11.5 }}>
                  {f.funnel}: <b>{money(f.amount)}</b> <span className="muted">· {f.deals}</span>
                </span>))}
            </div>
          )}
          <button type="button" className="btn btn-light" style={{ marginTop: 8, fontSize: 12 }} onClick={() => setOpen(!open)}>
            {open ? t("Скрыть сделки", "Сховати угоди") : t("Мои сделки за период", "Мої угоди за період") + ` (${rows.length})`}
          </button>
          {open && (
            <div style={{ maxHeight: 280, overflow: "auto", marginTop: 6, border: "1px solid #e5eaf1", borderRadius: 8 }}>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <tbody>{rows.map((r: any) => (
                  <tr key={r.deal_id} style={{ borderTop: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "4px 6px", whiteSpace: "nowrap" }}>
                      <a href={`/deals/${r.deal_id}`} target="_blank" rel="noreferrer">#{r.deal_id}</a></td>
                    <td style={{ padding: "4px 6px" }}>{r.client || r.title}<div className="muted" style={{ fontSize: 10.5 }}>{r.funnel}</div></td>
                    <td style={{ padding: "4px 6px", textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>{money(r.amount)}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
