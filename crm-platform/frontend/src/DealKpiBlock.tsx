/* ─── «Ваш заробіток з угоди» + що зробити саме в цій угоді (14.09.2026, пакет my-kpi) ─────────────
 * Рішення Олега 14.09: менеджер бачить не маржу, а скільки заробить зараз і скільки можна, якщо виконати KPI,
 * і чек-лист цієї угоди: тест-набір → «не забути, проконтролювати, тримати у фокусі», строк бонусу 300/200/100;
 * основне → знижка (скільки ₴ заробітку забирає), безкоштовна доставка від порогу, передоплата, розрахунок по
 * приміщеннях, відгук після отримання, партнер, план місяця.
 * Суми і % маржі тут немає ніколи (бекенд їх не віддає). Власник і право deal.margin.view бачать свій блок маржі.
 * Бекенд: GET /api/payroll/deal-kpi/<id>/. Якщо недоступний — показуємо старий рядок «Ваш заробіток з угоди».
 */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";

type T = (ru: string, uk: string) => string;
type Check = { code: string; status: "done" | "todo" | "warn" | "info"; title: string; hint?: string; where?: string; date?: string | null };
type Part = { code: string; label: string; amount: number };
type Kpi = {
  deal_id: number; kind: "test" | "main" | "other"; kind_label: string; focus: string; show_money: boolean; is_owner_view: boolean; owner_name: string;
  earn: { now: number; max: number; parts: Part[]; estimate: boolean; note: string } | null; no_scheme: boolean; checks: Check[];
};

const fmt = (n: number | null | undefined) => Math.round(Number(n || 0)).toLocaleString("uk-UA");
const ST: Record<Check["status"], { icon: string; color: string; bg: string }> = {
  done: { icon: "check", color: "#166534", bg: "#f0fdf4" },
  todo: { icon: "target", color: "#1d4ed8", bg: "#eff6ff" },
  warn: { icon: "warn", color: "#b45309", bg: "#fffbeb" },
  info: { icon: "info", color: "#475569", bg: "#f8fafc" },
};
const ORDER: Record<Check["status"], number> = { warn: 0, todo: 1, info: 2, done: 3 };

function CheckRow({ c }: { c: Check }) {
  const s = ST[c.status] || ST.info;
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-start", background: s.bg, borderRadius: 8, padding: "7px 9px", marginBottom: 5 }}>
      <span style={{ color: s.color, marginTop: 1 }}><Icon n={s.icon} size={14} /></span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: c.status === "done" ? "#166534" : "#0f172a" }}>{c.title}</div>
        {c.hint && <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.45 }}>{c.hint}</div>}
        {c.where && <div style={{ fontSize: 11, color: "#64748b", display: "flex", gap: 4, alignItems: "center", marginTop: 1 }}><Icon n="map-pin" size={11} /> {c.where}</div>}
      </div>
    </div>
  );
}

function Earn({ k, t }: { k: Kpi; t: T }) {
  const e = k.earn!;
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="row" title={t("Бонус ответственного со сделки по его ставкам. Итог месяца — в ЗП.", "Бонус відповідального з угоди за його ставками. Підсумок місяця — у ЗП.")}>
        <span className="muted"><Icon n="💰" size={14} /> {k.is_owner_view ? t("Ваш заработок со сделки сейчас", "Ваш заробіток з угоди зараз") : t(`Заработок ответственного (${k.owner_name})`, `Заробіток відповідального (${k.owner_name})`)}</span>
        <b style={{ color: "#1d4ed8" }}>{fmt(e.now)} ₴</b>
      </div>
      {e.max > e.now && (
        <div className="row"><span className="muted"><Icon n="trending-up" size={14} /> {t("Можно до, если выполнить KPI", "Можна до, якщо виконати KPI")}</span><b style={{ color: "#16a34a" }}>{fmt(e.max)} ₴</b></div>
      )}
      {e.parts.filter((p) => p.code !== "now").map((p) => (
        <div key={p.code} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 11.5, color: "#475569", padding: "1px 0 1px 20px" }}>
          <span>{p.label}</span><span style={{ whiteSpace: "nowrap", color: "#16a34a", fontWeight: 600 }}>+{fmt(p.amount)} ₴</span>
        </div>
      ))}
      <div className="muted" style={{ fontSize: 10.5, marginTop: 3 }}>{e.note}{e.estimate ? t(" В товарах нет себестоимости — сумма оценочная.", " У товарах немає собівартості — сума орієнтовна.") : ""}</div>
    </div>
  );
}

export default function DealKpiBlock({ dealId, fallbackTotal, refreshKey }: { dealId: number; fallbackTotal: number; refreshKey?: string }) {
  const { t } = useLang();
  const [k, setK] = useState<Kpi | null>(null);
  const [failed, setFailed] = useState(false);
  const [showDone, setShowDone] = useState(false);

  useEffect(() => {
    let alive = true;
    api.get<Kpi>(`/api/payroll/deal-kpi/${dealId}/`)
      .then((r) => { if (alive) { setK(r); setFailed(false); } })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [dealId, refreshKey]);

  // запасний варіант — як було до 14.09: один рядок із deal.bonus
  if (failed || !k) {
    return (
      <div className="panel">
        <div className="row" title={t("Бонус ответственного менеджера со сделки по его ставкам. Итог месяца — в ЗП.", "Бонус відповідального менеджера з угоди за його ставками. Підсумок місяця — у ЗП.")}>
          <span className="muted"><Icon n="💰" size={14} /> {t("Ваш заработок со сделки", "Ваш заробіток з угоди")}</span>
          <b style={{ color: "#1d4ed8" }}>{fmt(fallbackTotal)} ₴</b>
        </div>
      </div>
    );
  }
  const checks = [...k.checks].sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  const open = checks.filter((c) => c.status !== "done");
  const done = checks.filter((c) => c.status === "done");
  return (
    <div className="panel">
      <div className="label" style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <Icon n="target" size={15} /> {t("Заработок и KPI по сделке", "Заробіток і KPI по угоді")}
        <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 600, color: k.kind === "test" ? "#b45309" : "#1d4ed8", background: k.kind === "test" ? "#fffbeb" : "#eff6ff", borderRadius: 20, padding: "1px 8px" }}>{k.kind_label}</span>
      </div>
      {k.earn ? <Earn k={k} t={t} /> : k.show_money ? (
        <div className="row"><span className="muted"><Icon n="💰" size={14} /> {t("Ваш заработок со сделки", "Ваш заробіток з угоди")}</span><b style={{ color: "#1d4ed8" }}>{fmt(fallbackTotal)} ₴</b></div>
      ) : null}
      {k.no_scheme && <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>{t("Ставка ответственного ещё не задана — сумма по старой формуле.", "Ставку відповідального ще не задано — сума за старою формулою.")}</div>}
      <div style={{ fontSize: 12, color: "#334155", background: "#f8fafc", borderRadius: 8, padding: "6px 9px", margin: "4px 0 8px", display: "flex", gap: 6 }}><Icon n="bulb" size={13} /> <span>{k.focus}</span></div>
      {open.map((c) => <CheckRow key={c.code} c={c} />)}
      {done.length > 0 && (
        <>
          <button className="btn btn-light" style={{ fontSize: 11.5, padding: "3px 8px", marginTop: 2 }} onClick={() => setShowDone((v) => !v)}>
            <Icon n="check" size={12} /> {showDone ? t("Скрыть выполненное", "Сховати виконане") : t(`Выполнено: ${done.length}`, `Виконано: ${done.length}`)}
          </button>
          {showDone && <div style={{ marginTop: 6 }}>{done.map((c) => <CheckRow key={c.code} c={c} />)}</div>}
        </>
      )}
      <a href="/my-pay#plan" style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11.5, color: "#2563eb", marginTop: 8 }}><Icon n="bulb" size={12} /> {t("Условия ЗП и план — Моя ЗП", "Умови ЗП і план — Моя ЗП")}</a>
    </div>
  );
}
