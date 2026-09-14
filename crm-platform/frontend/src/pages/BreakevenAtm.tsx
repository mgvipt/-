import { useEffect, useState } from "react";
import { api } from "../api";

/* Точка беззбитковості за ATM (14.09): фінмодель + ставки співробітників + вакансії «що якщо».
 * Знизу вгору: Маржа = (фонди СКД + тверді фонди маржі) ÷ (1 − Σ% фондів маржі); Виручка = Маржа ÷ (1 − Σ% фондів виручки). */

const money = (n: any) => (n == null ? "—" : Math.round(Number(n)).toLocaleString("uk-UA") + " ₴");
const pct = (n: any) => (n == null ? "—" : `${Number(n).toLocaleString("uk-UA", { maximumFractionDigits: 2 })}%`);

function Level({ title, hint, rows, unit }: { title: string; hint: string; rows: any[]; unit: string }) {
  const total = rows.reduce((s, r) => s + Number(r.value || 0), 0);
  return (
    <div className="panel" style={{ margin: 0 }}>
      <b style={{ fontSize: 13.5 }}>{title}</b>
      <div className="muted" style={{ fontSize: 11.5, margin: "2px 0 6px" }}>{hint}</div>
      {rows.filter((r) => Number(r.value) !== 0 || r.source === "ставки").map((r, i) => (
        <div key={i} style={{ display: "flex", gap: 8, fontSize: 12.5, padding: "3px 0", borderBottom: "1px solid #f1f5f9" }}>
          <span style={{ flex: 1, minWidth: 0 }}>{r.name}{r.source === "ставки" && <span style={{ marginLeft: 6, fontSize: 10.5, color: "#2E6FB0", background: "#e6eef8", borderRadius: 999, padding: "0 6px" }}>ставки</span>}</span>
          <b style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{unit === "%" ? pct(r.value) : money(r.value)}</b>
        </div>
      ))}
      <div style={{ display: "flex", fontSize: 12.5, paddingTop: 5 }}><span className="muted" style={{ flex: 1 }}>Разом</span><b>{unit === "%" ? pct(total) : money(total)}</b></div>
    </div>
  );
}

export default function BreakevenAtm({ showStaff = true }: { showStaff?: boolean }) {
  const [d, setD] = useState<any>(null);
  const [withIds, setWithIds] = useState<number[]>([]);
  const [hidden, setHidden] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    api.get<any>(`/api/payroll/breakeven/${withIds.length ? `?with=${withIds.join(",")}` : ""}`)
      .then(setD).catch(() => setHidden(true));
  }, [withIds.join(",")]);
  if (hidden) return null;
  if (!d) return <div className="muted" style={{ fontSize: 12.5, margin: "6px 0 12px" }}>Рахуємо точку беззбитковості за ATM…</div>;
  const prog = Math.min(100, d.progress || 0);
  const toggle = (id: number) => setWithIds((v) => (v.includes(id) ? v.filter((x) => x !== id) : [...v, id]));
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="note" style={{ marginBottom: 10 }}>
        🎯 <b>Точка беззбитковості за ATM</b> — рахується знизу вгору з трьох рівнів ФРС. Зарплати беруться зі <b>Ставок співробітників</b> (Налаштування),
        решта — з Фінмоделі. Змінили ставку або додали вакансію — цифра перерахується сама. Дивіденди й резерв теж входять у точку беззбитковості.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 10, marginBottom: 10 }}>
        <div className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>Точка беззбитковості / міс</div><div style={{ fontSize: 22, fontWeight: 800 }}>{money(d.breakeven)}</div></div>
        <div className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>Потрібна маржа / міс</div><div style={{ fontSize: 20, fontWeight: 700 }}>{money(d.margin_needed)}</div></div>
        <div className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>Виручка цього місяця</div><div style={{ fontSize: 20, fontWeight: 700 }}>{money(d.revenue_month)}</div><div className="muted" style={{ fontSize: 11.5 }}>минулий місяць {money(d.revenue_prev_month)}</div></div>
        <div className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>+10 000 ₴ окладу</div><div style={{ fontSize: 20, fontWeight: 700 }}>{d.k_fixed ? `+${money(10000 * d.k_fixed)}` : "—"}</div><div className="muted" style={{ fontSize: 11.5 }}>до точки беззбитковості (×{d.k_fixed})</div></div>
      </div>
      <div style={{ height: 14, background: "#f1f5f9", borderRadius: 7, overflow: "hidden", marginBottom: 4 }}>
        <div style={{ width: `${prog}%`, height: "100%", background: prog >= 100 ? "#16a34a" : "#f59e0b" }} />
      </div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>Пройдено {d.progress ?? "—"}% точки беззбитковості цього місяця. Маржа за останні 90 днів — {d.shares?.margin_pct}% виручки (товари − собівартість; доставка й комісія — окремий крок).</div>

      {d.vacancies?.length > 0 && (
        <div className="panel" style={{ margin: "0 0 10px" }}>
          <b style={{ fontSize: 13.5 }}>Вакансії — «що якщо»</b>
          <div className="muted" style={{ fontSize: 11.5, margin: "2px 0 6px" }}>Поставте галочку — побачите нову точку беззбитковості з цією людиною. Вакансії додаються в Налаштування → Ставки співробітників.</div>
          {d.vacancies.map((v: any) => (
            <label key={v.scheme_id ?? v.position} style={{ display: "flex", gap: 8, alignItems: "baseline", fontSize: 12.5, padding: "4px 0", borderBottom: "1px solid #f1f5f9", cursor: v.scheme_id ? "pointer" : "default" }}>
              {v.scheme_id && <input type="checkbox" checked={v.included} onChange={() => toggle(v.scheme_id)} />}
              <span style={{ flex: 1 }}>{v.position}{v.planned_start ? ` · вихід ${v.planned_start.slice(8, 10)}.${v.planned_start.slice(5, 7)}` : ""}{v.employment ? ` · ${v.employment}` : ""}</span>
              {v.fixed_cost != null && <span className="muted">коштує {money(v.fixed_cost)}/міс</span>}
              <b style={{ whiteSpace: "nowrap" }}>{v.delta_breakeven ? `ТБ +${money(v.delta_breakeven)}` : "—"}</b>
            </label>
          ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 10 }}>
        <Level title="1. Фонди виручки (% з кожної гривні)" hint="Без них бізнес зупиниться: постачальники, доставка, комісії, відрядна оплата" rows={d.levels.revenue} unit="%" />
        <Level title="2а. Фонди маржі у відсотках" hint="% продавців з маржі, дивіденди власника" rows={d.levels.margin_pct} unit="%" />
        <Level title="2б. Тверді фонди маржі (₴ / міс)" hint="Оклади з податками, оренда, реклама, сервіси, кредити, резерв" rows={d.levels.margin_fixed} unit="₴" />
        <Level title="3. Фонди СКД (₴ / міс)" hint="Розвиток: обладнання, навчання, офіс" rows={d.levels.skd} unit="₴" />
      </div>

      {showStaff && d.payroll?.length > 0 && (
        <div className="panel" style={{ margin: "10px 0 0" }}>
          <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} Люди в точці беззбитковості ({d.payroll.length}) · тверда частина з податками {money(d.payroll_fixed)}</button>
          {open && <div style={{ overflowX: "auto", marginTop: 6 }}>
            <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
              <thead><tr style={{ color: "#64748b", textAlign: "left" }}><th style={{ padding: 4 }}>Хто</th><th>Оформлення</th><th style={{ textAlign: "right" }}>Тверда «на руки»</th><th style={{ textAlign: "right" }}>Коштує компанії</th><th style={{ textAlign: "right" }}>% маржі</th><th style={{ textAlign: "right" }}>% виручки</th></tr></thead>
              <tbody>{d.payroll.map((p: any) => (
                <tr key={p.scheme_id} style={{ borderTop: "1px solid #f1f5f9" }}>
                  <td style={{ padding: 4 }}>{p.name}<div className="muted" style={{ fontSize: 11 }}>{p.position}</div></td>
                  <td>{p.employment}</td>
                  <td style={{ textAlign: "right" }}>{money(p.fixed_net)}</td>
                  <td style={{ textAlign: "right" }}>{money(p.fixed_cost)}</td>
                  <td style={{ textAlign: "right" }}>{pct((p.margin_pct || 0) * 100)}</td>
                  <td style={{ textAlign: "right" }}>{pct((p.revenue_pct || 0) * 100)}</td>
                </tr>))}</tbody>
            </table>
            {d.replaced_articles?.length > 0 && <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>Замість статей фінмоделі (щоб не рахувати двічі): {d.replaced_articles.map((a: any) => a.name).join(", ")}.</div>}
          </div>}
        </div>
      )}
    </div>
  );
}
