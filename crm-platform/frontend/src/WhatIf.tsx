/* «Що буде, якщо…» у «Моя ЗП» (Розвиток v2, 16.09.2026). Бекенд: GET /api/payroll/my/whatif/?pay=&tests=&avg_order=
 * рахує ТІЄЮ САМОЮ формулою, що ЗП (engine.calc). Без права «маржа угоди» — суми округлено до 10 ₴, маржі немає.
 * Якщо маршрут ще не підключено (404) — блок нічого не показує. Компоненти — на верхньому рівні файлу. */
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";
import InfoTip from "./InfoTip";

type Part = { label: string; amount: number };
type Scen = { code: string; input: number; delta: number; new_total: number; explain: string; parts?: Part[]; avg_order?: number;
  deals?: { deal_id: number; title: string; discount: number }[]; n_deals?: number };
type W = { available: boolean; message?: string; total?: number; scenarios?: Scen[]; notes?: string[]; formula?: string; rounded?: boolean; has_plan?: boolean };

const fmt = (n: number | null | undefined) => Math.round(Number(n || 0)).toLocaleString("uk-UA");
const GREEN = "#15803d";

function NumIn({ v, on, w, step, min }: { v: number | ""; on: (x: number | "") => void; w?: number; step?: number; min?: number }) {
  return (
    <input type="number" inputMode="numeric" value={v} min={min ?? 0} step={step ?? 1}
      onChange={(e) => on(e.target.value === "" ? "" : Math.max(min ?? 0, Number(e.target.value)))}
      style={{ width: w || 90, height: 26, fontSize: 13, padding: "0 6px", border: "1px solid #cbd5e1", borderRadius: 6 }} />
  );
}

function Row({ s, children, t }: { s?: Scen; children: any; t: (ru: string, uk: string) => string }) {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "7px 0", borderBottom: "1px solid #f1f5f9", flexWrap: "wrap" }}>
      <div style={{ flex: 1, minWidth: 240, fontSize: 12.8 }}>{children}{s && <InfoTip text={s.explain} title={t("Как посчитано", "Як пораховано")} />}</div>
      {s && <b style={{ fontSize: 14, color: s.delta > 0 ? GREEN : "#64748b", whiteSpace: "nowrap" }}>{s.delta > 0 ? "+" : ""}{fmt(s.delta)} ₴</b>}
    </div>
  );
}

export default function WhatIf() {
  const { t } = useLang();
  const [pay, setPay] = useState<number | "">(10000);
  const [tests, setTests] = useState<number | "">(3);
  const [avg, setAvg] = useState<number | "">("");
  const [d, setD] = useState<W | null>(null);
  const [gone, setGone] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const q = `pay=${Number(pay || 0)}&tests=${Number(tests || 0)}` + (avg ? `&avg_order=${Number(avg)}` : "");
      api.get<W>(`/api/payroll/my/whatif/?${q}`).then((r) => { setD(r); if (avg === "") { const ts = r.scenarios?.find((x) => x.code === "tests"); if (ts?.avg_order) setAvg(ts.avg_order); } })
        .catch((e: any) => { if (e?.status === 404) setGone(true); });
    }, 350);
    return () => window.clearTimeout(timer.current);
  }, [pay, tests, avg]);

  if (gone || (d && !d.available)) return null;
  const sc = (code: string) => d?.scenarios?.find((x) => x.code === code);
  const sPay = sc("pay"), sTests = sc("tests"), sDisc = sc("discount");
  return (
    <div style={{ marginTop: 12, background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "10px 12px" }}>
      <div style={{ fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}><Icon n="calculator" size={14} /> {t("Что будет, если…", "Що буде, якщо…")}</div>
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 4 }}>{t("Та же формула, что и ЗП. Меняйте числа — сумма пересчитается.", "Та сама формула, що й ЗП. Змінюйте числа — сума перерахується.")}</div>
      {!d && <div className="muted" style={{ fontSize: 12 }}>{t("Считаем…", "Рахуємо…")}</div>}
      {sPay && (
        <Row s={sPay} t={t}>{t("Ещё оплат на", "Ще оплат на")} <NumIn v={pay} on={setPay} w={100} step={1000} /> ₴ {t("по моим сделкам", "по моїх угодах")}</Row>
      )}
      {sTests && (
        <Row s={sTests} t={t}>
          {t("Конвертирую", "Конвертую")} <NumIn v={tests} on={setTests} w={56} /> {t("тест-наборов в основной заказ вовремя, средний заказ", "тест-наборів в основне вчасно, середнє замовлення")} <NumIn v={avg} on={setAvg} w={90} step={500} /> ₴
          {(sTests.parts || []).length > 0 && <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>{sTests.parts!.map((p) => `${p.label}: +${fmt(p.amount)} ₴`).join(" · ")}</div>}
        </Row>
      )}
      {sDisc && (
        <Row s={sDisc} t={t}>
          {sDisc.n_deals ? t(`Без скидки на открытых сделках (${sDisc.n_deals}, скидки ${fmt(sDisc.input)} ₴)`, `Без знижки на відкритих угодах (${sDisc.n_deals}, знижки ${fmt(sDisc.input)} ₴)`) : t("Без скидки: на открытых сделках скидок нет", "Без знижки: на відкритих угодах знижок немає")}
          {(sDisc.deals || []).length > 0 && <div style={{ fontSize: 11.5, marginTop: 2, display: "flex", flexWrap: "wrap", gap: "2px 10px" }}>{sDisc.deals!.map((x) => <a key={x.deal_id} href={`/deals/${x.deal_id}`} style={{ color: "#2563eb" }}>#{x.deal_id} −{fmt(x.discount)} ₴</a>)}</div>}
        </Row>
      )}
      {d?.formula && <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{d.formula}</div>}
      {(d?.notes || []).map((n, i) => <div key={i} className="muted" style={{ fontSize: 11, marginTop: 2 }}>{n}</div>)}
    </div>
  );
}
