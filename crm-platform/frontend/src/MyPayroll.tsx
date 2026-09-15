/* ─── «Моя ЗП і KPI» + «Як виконати план і умови ЗП» (14.09.2026, пакет my-kpi) ─────────────
 * Рішення Олега 14.09: кожен співробітник бачить СВОЮ статистику ЗП і KPI — лише свої дані.
 * Бекенд: GET /api/payroll/my/?period=YYYY-MM (затверджена відомість або розрахунок наживо);
 *         GET /api/payroll/my/?only=rules — правила з власної схеми (секція id="plan" на сторінці «Розвиток»).
 * Суми маржі тут немає: бекенд прибирає «маржа N ₴» з пояснень до «% з маржі».
 * Якщо маршрут ще не підключено (404) — блоки нічого не показують.
 * Усі компоненти — на верхньому рівні файлу (не всередині render).
 */
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";
import { LineDetail, matchDetail } from "./PayCalcDetail";
import InfoTip from "./InfoTip";  // 16.09 Розвиток v2: (i) — формула на реальних числах
import WhatIf from "./WhatIf";  // 16.09 Розвиток v2: «Що буде, якщо…» за формулою ЗП

type T = (ru: string, uk: string) => string;
type Line = { kind: string; component?: number | null; title: string; amount: number; rate?: string | null; detail: string; warn: string; estimate: boolean };
type Part = { kind: string; title: string; plain: string };
type Plan = { fact: number; target: number; min: number; ambition: number; pct: number | null; left: number | null; over: number; basis: string; to_pct?: number; over_pct?: number; gate_pct?: number; note?: string };
type Std = { title: string; max: number; set: boolean; score_pct: number | null; amount: number | null };
type Cond = { text: string; ok: boolean | null };
type Guar = { amount: number; start: string | null; end: string | null; active: boolean; confirmed: boolean; checked: boolean; note: string; topup: number; paid_topup: number; conditions: Cond[] };
type Opp = { deal_id: number; title: string; client: string; test_paid: string; deadline: string; days_left: number; fast: number; slow: number; small: number; min_order: number };
type More = { code: string; title: string; amount: number | null; hint: string };
type WhRow = { op: string; label: string; count: number; amount: number; kg: number | null };
type Rule = { kind: string; title: string; need: string[]; where: string[] };
type Scheme = { position: string; title: string; valid_from: string; parts: Part[] };
// 16.09 Розвиток v2: «гарантовано / умовно» і пункти стандарту складу (лише свої)
type CondPart = { code: string; amount: number; label: string; hint: string };
type WhPt = { n: number; title: string; who: string; target: string; value_text: string; ok: boolean; no_data: boolean; hint: string; details: string[] };
type WhStd = { in_scheme: boolean; max: number | null; score_pct: number | null; suggested_pct: number; good: number; total: number; points: WhPt[]; partial: boolean; rule: string; note: string };
type My = {
  period: string; period_label: string; periods: { value: string; label: string }[]; user_name: string; has_scheme: boolean; is_current: boolean;
  message?: string; source?: "approved" | "live"; approved_at?: string | null; total?: number; live_total?: number; paid?: number; remaining?: number;
  lines?: Line[]; warnings?: string[]; scheme?: Scheme | null; plan?: Plan | null; standard?: Std | null; guarantee?: Guar | null;
  opportunities?: Opp[]; opp_older?: number; more?: More[]; warehouse?: { rows: WhRow[]; total: number } | null; rules?: Rule[];
  guaranteed?: number; conditional?: CondPart[]; has_plan?: boolean; wh_standard?: WhStd | null;
};

const BLUE = "#1d4ed8";
const fmt = (n: number | null | undefined) => Math.round(Number(n || 0)).toLocaleString("uk-UA");
const dmy = (iso?: string | null) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : "—");

/** Перехід до секції «Умови ЗП і план» (id="plan"): на цій сторінці — прокрутка; інакше — «Моя ЗП» (є в меню в усіх). */
export function goToPlan(navigate: (to: string) => void) {
  const el = document.getElementById("plan");
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    window.history.replaceState(null, "", window.location.pathname + "#plan");
  } else {
    navigate("/my-pay#plan");
  }
}

/** (i) біля суми: «Разом = рядок + рядок + … = сума». */
function totalFormula(d: My, t: T) {
  const ls = (d.lines || []).filter((l) => l.amount);
  if (!ls.length) return "";
  return t("Итого = сумма строк ниже: ", "Разом = сума рядків нижче: ") + ls.map((l) => `${l.title} ${fmt(l.amount)}`).join(" + ") + ` = ${fmt(d.total)} ₴`
    + ((d.conditional || []).length ? t(". Из них условно — стандарт, пока не оценён.", ". З них умовно — стандарт, поки не оцінено.") : "");
}

// 15.09.2026 (Олег): у кожного рядка — «Як прорахувалось», як у керівника в ЗП/KPI (угоди, оплати, записи; без маржі без права)
function LineRow({ l, t, open, onToggle, busy, err, det, dl, frozen }: {
  l: Line; t: T; open: boolean; onToggle: () => void; busy: boolean; err: string; det: any; dl: any; frozen: boolean;
}) {
  return (
    <div style={{ padding: "7px 0", borderBottom: "1px solid #f1f5f9" }}>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{l.title}{l.rate ? <span className="muted" style={{ fontWeight: 400 }}> · {l.rate}</span> : null}</div>
          {l.detail && <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.45 }}>{l.detail}</div>}
          {l.warn && <div style={{ fontSize: 11.5, color: "#b45309", display: "flex", gap: 4, alignItems: "center" }}><Icon n="warn" size={12} /> {l.warn}</div>}
          <button type="button" className="btn btn-light" style={{ fontSize: 11, height: 22, padding: "0 8px", marginTop: 3, display: "inline-flex", alignItems: "center", gap: 4 }} onClick={onToggle}>
            <Icon n="calculator" size={12} /> {open ? t("Скрыть расчёт", "Сховати розрахунок") : t("Как посчитано", "Як прорахувалось")}</button>
        </div>
        <b style={{ fontSize: 14, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", color: l.amount > 0 ? "#0f172a" : "#94a3b8" }}>{fmt(l.amount)} ₴</b>
      </div>
      {open && (busy && !det ? <div className="muted" style={{ fontSize: 12, padding: "4px 0" }}>{t("Считаем…", "Рахуємо…")}</div>
        : err ? <div className="note" style={{ fontSize: 12 }}>{err}</div>
          : dl ? <LineDetail dl={dl} frozenAmount={frozen ? l.amount : null} />
            : det ? <div className="muted" style={{ fontSize: 12, padding: "4px 0" }}>{t("Этой строки сейчас нет в расчёте вживую.", "Цього рядка зараз немає в розрахунку наживо.")}</div> : null)}
    </div>
  );
}
function PlanBar({ p, t }: { p: Plan; t: T }) {
  const pct = Math.max(0, Math.min(100, p.pct || 0));
  return (
    <div style={{ background: "#f8fafc", borderRadius: 10, padding: "10px 12px", marginTop: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 700 }}><Icon n="target" size={14} /> {t("План месяца", "План місяця")}</div>
      {p.target ? (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginTop: 6 }}>
            <span>{fmt(p.fact)} ₴ {t("из", "з")} {fmt(p.target)} ₴</span><b style={{ color: pct >= 100 ? "#16a34a" : BLUE }}>{p.pct ?? 0}%</b>
          </div>
          <div style={{ height: 10, background: "#e2e8f0", borderRadius: 20, overflow: "hidden", marginTop: 5 }}>
            <div style={{ width: `${pct}%`, height: "100%", background: pct >= 100 ? "#16a34a" : BLUE, borderRadius: 20 }} />
          </div>
          <div className="muted" style={{ fontSize: 11.5, marginTop: 5 }}>
            {p.left ? `${t("Осталось", "Лишилось")} ${fmt(p.left)} ₴. ` : `${t("Сверх плана", "Понад план")}: ${fmt(p.over)} ₴. `}
            {p.over_pct && p.over_pct !== p.to_pct ? t(`Сверх плана — ${p.over_pct}% вместо ${p.to_pct}% (при стандарте от ${p.gate_pct}%).`, `Понад план — ${p.over_pct}% замість ${p.to_pct}% (при стандарті від ${p.gate_pct}%).`) : ""}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>{t("Считаются", "Рахуються")}: {p.basis}</div>
        </>
      ) : <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{p.note || t("План не установлен", "План не встановлено")} · {t("факт", "факт")}: {fmt(p.fact)} ₴</div>}
    </div>
  );
}

function GuaranteeBox({ g, t }: { g: Guar; t: T }) {
  return (
    <div style={{ background: g.confirmed ? "#f0fdf4" : "#fffbeb", border: `1px solid ${g.confirmed ? "#bbf7d0" : "#fde68a"}`, borderRadius: 10, padding: "10px 12px", marginTop: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 700 }}>
        <Icon n="shield" size={14} /> {t("Гарантия новичку", "Гарантія новачку")} {fmt(g.amount)} ₴ · {dmy(g.start)} — {dmy(g.end)}
      </div>
      <div style={{ fontSize: 12, marginTop: 4 }}>
        {!g.active ? t("В этом месяце гарантия не действует.", "Цього місяця гарантія не діє.")
          : g.confirmed ? t(`Условия подтверждены — доплата ${fmt(g.paid_topup)} ₴.`, `Умови підтверджено — доплата ${fmt(g.paid_topup)} ₴.`)
            : g.topup ? t(`Доплата +${fmt(g.topup)} ₴ — только после подтверждения условий руководителем.`, `Доплата +${fmt(g.topup)} ₴ — лише після підтвердження умов керівником.`)
              : t("Условия за месяц ещё не подтверждены.", "Умови за місяць ще не підтверджено.")}
        {g.note ? <span className="muted"> · {g.note}</span> : null}
      </div>
      <div style={{ marginTop: 6 }}>
        {g.conditions.map((c, i) => (
          <div key={i} style={{ display: "flex", gap: 7, alignItems: "flex-start", fontSize: 12, padding: "3px 0" }}>
            <span style={{ color: c.ok ? "#16a34a" : c.ok === false ? "#dc2626" : "#94a3b8", marginTop: 1 }}><Icon n={c.ok ? "check" : c.ok === false ? "x" : "clock"} size={13} /></span>
            <span>{c.text}</span>
          </div>
        ))}
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{t("Серый значок — ещё не проверено руководителем.", "Сірий значок — ще не перевірено керівником.")}</div>
    </div>
  );
}

function OppRow({ o, t }: { o: Opp; t: T }) {
  const late = o.days_left < 0;
  return (
    <a href={`/deals/${o.deal_id}`} style={{ display: "flex", gap: 10, alignItems: "center", padding: "7px 9px", borderRadius: 8, background: "#f8fafc", marginBottom: 5, color: "inherit", textDecoration: "none" }}>
      <Icon n="package" size={15} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.8, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{o.client || o.title}</div>
        <div className="muted" style={{ fontSize: 11 }}>{t("тест оплачен", "тест оплачено")} {dmy(o.test_paid)} · {t("срок", "строк")} {dmy(o.deadline)}{!late ? ` · ${t("осталось", "лишилось")} ${o.days_left} ${t("дн.", "дн.")}` : ""}</div>
      </div>
      <b style={{ fontSize: 13, color: late ? "#b45309" : "#16a34a", whiteSpace: "nowrap" }}>+{fmt(late ? o.slow : o.fast)} ₴</b>
    </a>
  );
}

function MyBody({ d, t, onPlan }: { d: My; t: T; onPlan: () => void }) {
  const [showScheme, setShowScheme] = useState(false);
  const [det, setDet] = useState<any>(null);
  const [detBusy, setDetBusy] = useState(false);
  const [detErr, setDetErr] = useState("");
  const [open, setOpen] = useState<Record<number, boolean>>({});
  useEffect(() => { setDet(null); setDetErr(""); setOpen({}); }, [d.period]);
  function toggle(i: number) {
    setOpen((o) => ({ ...o, [i]: !o[i] }));
    if (det || detBusy) return;
    setDetBusy(true);
    api.get<any>(`/api/payroll/my/detail/?period=${d.period}`).then(setDet)
      .catch((e: any) => setDetErr(e?.data?.detail || e?.response?.data?.detail || t("Не удалось загрузить расчёт", "Не вдалося завантажити розрахунок")))
      .finally(() => setDetBusy(false));
  }
  if (!d.has_scheme) {
    return (
      <div style={{ marginTop: 10 }}>
        <div className="note" style={{ display: "flex", gap: 8, alignItems: "center" }}><Icon n="info" size={16} /> {d.message}</div>
        {d.warehouse && d.warehouse.rows.length > 0 && <WarehouseRows w={d.warehouse} t={t} />}
        <button className="btn btn-light" style={{ marginTop: 10, fontSize: 12.5 }} onClick={onPlan}><Icon n="bulb" size={14} /> {t("Условия ЗП и план", "Умови ЗП і план")}</button>
      </div>
    );
  }
  const more = d.more || [];
  const opps = d.opportunities || [];
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 2 }}><div style={{ fontSize: 34, fontWeight: 800, lineHeight: 1, color: BLUE, fontVariantNumeric: "tabular-nums" }}>{fmt(d.total)} ₴</div><InfoTip text={totalFormula(d, t)} /></div>
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
            {d.source === "approved"
              ? t(`Утверждено ${dmy(d.approved_at)}`, `Затверджено ${dmy(d.approved_at)}`) + (d.live_total != null && d.live_total !== d.total ? t(` · сейчас вышло бы ${fmt(d.live_total)} ₴`, ` · зараз вийшло б ${fmt(d.live_total)} ₴`) : "")
              : t("Расчёт вживую — может измениться до конца месяца", "Розрахунок наживо — може змінитися до кінця місяця")}
          </div>
          {(d.conditional || []).length > 0 && (
            <div style={{ fontSize: 12.5, marginTop: 5, lineHeight: 1.5 }}>
              {t("гарантировано", "гарантовано")} <b>{fmt(d.guaranteed)} ₴</b>
              {d.conditional!.map((c) => <span key={c.code}> · <span style={{ color: "#b45309", fontWeight: 600 }}>{t("условно", "умовно")} +{fmt(c.amount)} ₴</span> <span className="muted">({c.label})</span><InfoTip text={c.hint} /></span>)}
            </div>
          )}
        </div>
        {d.source === "approved" && (
          <div style={{ fontSize: 12.5 }}>{t("Выплачено", "Виплачено")} <b>{fmt(d.paid)} ₴</b> · {t("осталось", "лишилось")} <b>{fmt(d.remaining)} ₴</b></div>
        )}
        {d.scheme && <div className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>{d.scheme.position}{d.scheme.title ? ` · ${d.scheme.title}` : ""}</div>}
      </div>

      <div style={{ marginTop: 10 }}>{(d.lines || []).map((l, i) => <LineRow key={i} l={l} t={t} open={!!open[i]} onToggle={() => toggle(i)}
        busy={detBusy} err={detErr} det={det} dl={det?.lines ? matchDetail(det.lines, l, i) : null} frozen={d.source === "approved"} />)}</div>
      {det?.margin_hidden && Object.values(open).some(Boolean) && <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>{t("Маржу сделок видит только руководитель — здесь ваш заработок по каждой оплате.", "Маржу угод бачить лише керівник — тут ваш заробіток по кожній оплаті.")}</div>}

      {d.plan && <PlanBar p={d.plan} t={t} />}
      {d.standard && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12.5, marginTop: 10 }}>
          <Icon n="award" size={14} /> {t("Стандарт работы", "Стандарт роботи")}: {d.standard.set ? <b>{d.standard.score_pct}%</b> : <span className="muted">{t("ещё не оценён — в сумме 100% условно (за полный месяц, зависит от оценки)", "ще не оцінено — у сумі 100% умовно (за повний місяць, залежить від оцінки)")}</span>}
          <span className="muted">· {t("до", "до")} {fmt(d.standard.max)} ₴</span>
        </div>
      )}
      {d.guarantee && <GuaranteeBox g={d.guarantee} t={t} />}

      {d.is_current && (more.length > 0 || opps.length > 0) && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}><Icon n="trending-up" size={14} /> {t("Что ещё можно заработать в этом месяце", "Що ще можна заробити цього місяця")}</div>
          {more.map((m) => (
            <div key={m.code} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "6px 0" }}>
              <span style={{ color: BLUE, marginTop: 1 }}><Icon n="target" size={14} /></span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12.8, fontWeight: 600 }}>{m.title}</div>
                {m.hint && <div className="muted" style={{ fontSize: 11.5 }}>{m.hint}</div>}
              </div>
              {m.amount != null && m.amount > 0 && <b style={{ fontSize: 13, color: "#16a34a", whiteSpace: "nowrap" }}>{t("до", "до")} +{fmt(m.amount)} ₴</b>}
            </div>
          ))}
          {opps.length > 0 && <div style={{ marginTop: 4 }}>{opps.map((o) => <OppRow key={o.deal_id} o={o} t={t} />)}</div>}
          {(d.opp_older || 0) > 0 && <div className="muted" style={{ fontSize: 11.5 }}>{t(`Ещё ${d.opp_older} клиентов с тест-набором старше 30 дней — за основной заказ бонус меньше, но он есть.`, `Ще ${d.opp_older} клієнтів з тест-набором, старшим за 30 днів — за основне замовлення бонус менший, але він є.`)}</div>}
        </div>
      )}

      {d.warehouse && d.warehouse.rows.length > 0 && <WarehouseRows w={d.warehouse} t={t} />}
      {d.wh_standard && <WhStdBox w={d.wh_standard} t={t} />}
      {d.is_current && <WhatIf />}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <button className="btn btn-primary" style={{ fontSize: 12.5 }} onClick={onPlan}><Icon n="bulb" size={14} /> {t("Условия ЗП и план", "Умови ЗП і план")}</button>
        {d.scheme && <button className="btn btn-light" style={{ fontSize: 12.5 }} onClick={() => setShowScheme((v) => !v)}><Icon n="file" size={14} /> {t("Моя схема простыми словами", "Моя схема простими словами")}</button>}
      </div>
      {showScheme && d.scheme && <SchemeParts s={d.scheme} t={t} />}
    </div>
  );
}

function WarehouseRows({ w, t }: { w: { rows: WhRow[]; total: number }; t: T }) {
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}><Icon n="package" size={14} /> {t("Сдельные записи склада за месяц", "Відрядні записи складу за місяць")}</div>
      {w.rows.map((r) => (
        <div key={r.op} style={{ display: "flex", gap: 8, fontSize: 12.5, padding: "3px 0" }}>
          <span style={{ flex: 1 }}>{r.label} <span className="muted">· {r.count}{r.kg ? ` · ${r.kg} ${t("кг", "кг")}` : ""}</span></span>
          <b style={{ color: r.amount < 0 ? "#dc2626" : "#0f172a" }}>{fmt(r.amount)} ₴</b>
        </div>
      ))}
      <div style={{ display: "flex", fontSize: 12.5, borderTop: "1px solid #e2e8f0", paddingTop: 4, marginTop: 2 }}><span style={{ flex: 1 }}>{t("Итого", "Разом")}</span><b>{fmt(w.total)} ₴</b></div>
    </div>
  );
}

// 16.09 Розвиток v2: пункти стандарту складу — підказка CRM + позначки керівника (лише свої)
function WhStdBox({ w, t }: { w: WhStd; t: T }) {
  return (
    <div style={{ marginTop: 12, background: "#f8fafc", borderRadius: 10, padding: "10px 12px" }}>
      <div style={{ fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <Icon n="award" size={14} /> {t("Стандарт склада", "Стандарт складу")}: {w.good} {t("из", "з")} {w.total} {t("пунктов", "пунктів")} → {t("CRM подсказывает", "CRM підказує")} {w.suggested_pct}%
        {w.score_pct != null ? <span style={{ color: "#15803d" }}> · {t("оценка руководителя", "оцінка керівника")} {w.score_pct}%</span>
          : w.in_scheme ? <span className="muted" style={{ fontWeight: 400 }}> · {t("ещё не оценено", "ще не оцінено")}</span> : null}
        <InfoTip text={w.rule + (w.max ? ` ${t("Максимум", "Максимум")} ${fmt(w.max)} ₴ × ${t("оценка", "оцінка")}.` : "")} />
      </div>
      <div className="muted" style={{ fontSize: 11.5, margin: "2px 0 6px" }}>{w.note}{w.partial ? t(" Месяц ещё идёт — считаются завершённые дни.", " Місяць ще триває — рахуються завершені дні.") : ""}</div>
      {w.points.map((p) => (
        <div key={p.n} style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "4px 0", borderTop: "1px solid #eef2f7" }}>
          <span style={{ color: p.no_data ? "#94a3b8" : p.ok ? "#16a34a" : "#dc2626", marginTop: 1 }}><Icon n={p.no_data ? "clock" : p.ok ? "check" : "x"} size={13} /></span>
          <div style={{ flex: 1, fontSize: 12.3, lineHeight: 1.45 }}>
            <b>{p.n}.</b> {p.title} <span className="muted">· {p.who}</span>
            {(p.value_text || p.target) && <div className="muted" style={{ fontSize: 11.5 }}>{p.value_text}{p.target ? ` · ${t("цель", "мета")}: ${p.target}` : ""}</div>}
            {p.hint && <div className="muted" style={{ fontSize: 11.5 }}>{p.hint}</div>}
            {p.details.length > 0 && <details style={{ fontSize: 11.5 }}><summary style={{ cursor: "pointer" }}>{t("Подробнее", "Детальніше")} ({p.details.length})</summary>{p.details.map((x, i) => <div key={i} className="muted">{x}</div>)}</details>}
          </div>
        </div>
      ))}
    </div>
  );
}

function SchemeParts({ s, t }: { s: Scheme; t: T }) {
  return (
    <div style={{ marginTop: 8, background: "#f8fafc", borderRadius: 10, padding: "10px 12px" }}>
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 4 }}>{t("Действует с", "Діє з")} {dmy(s.valid_from)}</div>
      {s.parts.map((p, i) => (
        <div key={i} style={{ fontSize: 12.5, padding: "4px 0" }}><b>{p.title}.</b> {p.plain}</div>
      ))}
    </div>
  );
}

/** Блок «Моя ЗП і KPI» — вгорі сторінки «Розвиток» (і будь-де, де людина дивиться свої цифри). */
export default function MyPayroll({ period: extPeriod, hidePeriods }: { period?: string; hidePeriods?: boolean } = {}) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [period, setPeriod] = useState(extPeriod || "");
  // 16.09 Розвиток v2: на сторінці «Розвиток» місяць обирається ОДНИМ перемикачем угорі сторінки
  useEffect(() => { if (extPeriod && extPeriod !== period) setPeriod(extPeriod); }, [extPeriod]); // eslint-disable-line react-hooks/exhaustive-deps
  const [d, setD] = useState<My | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<boolean>(() => { try { return localStorage.getItem("crm_mypay_open") !== "0"; } catch { return true; } });

  useEffect(() => {
    let alive = true;
    setErr("");
    api.get<My>("/api/payroll/my/" + (period ? `?period=${period}` : ""))
      .then((r) => { if (alive) { setD(r); if (!period) setPeriod(r.period); } })
      .catch((e: any) => { if (alive) setErr(e?.status === 404 ? "404" : "load"); });
    return () => { alive = false; };
  }, [period]);

  if (err === "404") return null;
  const toggle = () => { const v = !open; setOpen(v); try { localStorage.setItem("crm_mypay_open", v ? "1" : "0"); } catch { /* приватний режим */ } };
  return (
    <div className="panel" style={{ borderLeft: `4px solid ${BLUE}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div className="label" style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}><Icon n="wallet" size={16} /> {t("Моя ЗП и KPI", "Моя ЗП і KPI")}</div>
        <span className="muted" style={{ fontSize: 11.5, display: "inline-flex", alignItems: "center", gap: 4 }}><Icon n="lock" size={12} /> {t("видно только вам", "видно лише вам")}</span>
        <div style={{ flex: 1 }} />
        {!hidePeriods && (d?.periods || []).map((p) => (
          <button key={p.value} className={"btn " + (period === p.value ? "btn-primary" : "btn-light")} style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => setPeriod(p.value)}>{p.label}</button>
        ))}
        <button className="btn btn-light" style={{ fontSize: 12, padding: "4px 8px" }} onClick={toggle} title={open ? t("Свернуть", "Згорнути") : t("Развернуть", "Розгорнути")}>
          <span style={{ display: "inline-flex", transform: open ? "rotate(180deg)" : "none" }}><Icon n="chevron-down" size={14} /></span>
        </button>
      </div>
      {!d && !err && <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{t("Загрузка…", "Завантаження…")}</div>}
      {err === "load" && <div className="note" style={{ marginTop: 8 }}>{t("Не удалось загрузить — обновите страницу.", "Не вдалося завантажити — оновіть сторінку.")}</div>}
      {d && open && <MyBody d={d} t={t} onPlan={() => goToPlan(navigate)} />}
    </div>
  );
}

function RuleCard({ r, t }: { r: Rule; t: T }) {
  return (
    <div style={{ border: "1px solid #e8edf3", borderRadius: 12, padding: "10px 12px", background: "#fff" }}>
      <div style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 6 }}>{r.title}</div>
      {r.need.length > 0 && (
        <>
          <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em" }}>{t("Что нужно", "Що потрібно")}</div>
          {r.need.map((x, i) => <div key={i} style={{ display: "flex", gap: 7, fontSize: 12.5, padding: "3px 0", lineHeight: 1.45 }}><span style={{ color: "#16a34a", marginTop: 2 }}><Icon n="check" size={13} /></span><span>{x}</span></div>)}
        </>
      )}
      {r.where.length > 0 && (
        <>
          <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em", marginTop: 6 }}>{t("Куда смотреть в CRM", "Куди дивитись у CRM")}</div>
          {r.where.map((x, i) => <div key={i} style={{ display: "flex", gap: 7, fontSize: 12.5, padding: "3px 0" }}><span style={{ color: BLUE, marginTop: 2 }}><Icon n="map-pin" size={13} /></span><span>{x}</span></div>)}
        </>
      )}
    </div>
  );
}

/** Секція «Як виконати план і умови ЗП» (id="plan") — з власної схеми того, хто дивиться. */
export function PlanRules() {
  const { t } = useLang();
  const loc = useLocation();
  const ref = useRef<HTMLDivElement>(null);
  const [d, setD] = useState<My | null>(null);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    let alive = true;
    api.get<My>("/api/payroll/my/?only=rules").then((r) => { if (alive) setD(r); }).catch(() => { if (alive) setGone(true); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (d && loc.hash === "#plan" && ref.current) {
      const el = ref.current;
      window.setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    }
  }, [d, loc.hash]);

  if (gone) return null;
  return (
    <div id="plan" ref={ref} className="panel" style={{ scrollMarginTop: 70, borderLeft: "4px solid #16a34a" }}>
      <div className="label" style={{ marginBottom: 2, display: "flex", alignItems: "center", gap: 6 }}><Icon n="bulb" size={16} /> {t("Как выполнить план и условия ЗП", "Як виконати план і умови ЗП")}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
        {t("Собрано из вашей схемы оплаты: что нужно для каждой части и куда смотреть в CRM. Видно только вам.", "Зібрано з вашої схеми оплати: що потрібно для кожної частини і куди дивитись у CRM. Видно лише вам.")}
      </div>
      {!d && <div className="muted" style={{ fontSize: 12 }}>{t("Загрузка…", "Завантаження…")}</div>}
      {d && !d.has_scheme && <div className="note" style={{ marginBottom: 10 }}>{t("Для вас ещё не задана ставка — ниже общие правила. Вопросы — к руководителю.", "Для вас ще не задано ставку — нижче загальні правила. Питання — до керівника.")}</div>}
      {d && d.scheme && d.scheme.parts.length > 0 && (
        <div style={{ background: "#f8fafc", borderRadius: 10, padding: "10px 12px", marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{t("Из чего состоит ваша ЗП", "З чого складається ваша ЗП")}{d.scheme.position ? ` · ${d.scheme.position}` : ""}</div>
          {d.scheme.parts.map((p, i) => <div key={i} style={{ fontSize: 12.5, padding: "3px 0" }}><b>{p.title}.</b> {p.plain}</div>)}
        </div>
      )}
      {d && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 10 }}>
          {(d.rules || []).map((r, i) => <RuleCard key={r.kind + i} r={r} t={t} />)}
        </div>
      )}
    </div>
  );
}
