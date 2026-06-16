import { useEffect, useState } from "react";
import { api } from "../api";

interface Dash {
  total_balance: number; month_income: number; month_expense: number; month_profit: number;
  accounts: { id: number; name: string; balance: number }[];
  cashflow: { date: string; in: number; out: number }[];
}

export default function Finance() {
  const [d, setD] = useState<Dash | null>(null);
  useEffect(() => { api.get<Dash>("/api/finance/dashboard/").then(setD).catch(() => setD(null)); }, []);

  if (!d) return <div className="spin">Загрузка финансов…</div>;
  const max = Math.max(...d.cashflow.map((x) => Math.max(x.in, x.out)), 1);
  const cards: [string, number, string][] = [
    ["Остаток на счетах", d.total_balance, "#16a34a"],
    ["Доход (месяц)", d.month_income, "#2563eb"],
    ["Расход (месяц)", d.month_expense, "#ef4444"],
    ["Прибыль (месяц)", d.month_profit, "#7c3aed"],
  ];

  return (
    <div className="scroll pad fade">
      <div className="note warn">🔒 Раздел виден только ролям с правом <b>finance.view</b>. Менеджеры его не видят.</div>
      <div className="cards4" style={{ marginTop: 12 }}>
        {cards.map(([t, v, c]) => (
          <div key={t} className="panel stat" style={{ margin: 0 }}>
            <div className="lbl" style={{ fontSize: 12, color: "#94a3b8" }}>{t}</div>
            <div className="big" style={{ fontSize: 22, fontWeight: 700, color: c }}>{v.toLocaleString("ru")} ₴</div>
          </div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 12 }}>
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>Денежный поток · 30 дней</b>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 160, marginTop: 12 }}>
            {d.cashflow.map((x, i) => (
              <div key={i} title={`${x.date}: +${x.in} / -${x.out}`} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: 1 }}>
                <div style={{ height: `${(x.in / max) * 70}%`, background: "#22c55e", borderRadius: "2px 2px 0 0" }} />
                <div style={{ height: `${(x.out / max) * 70}%`, background: "#f87171", borderRadius: "0 0 2px 2px" }} />
              </div>
            ))}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>🟢 доход · 🔴 расход по дням</div>
        </div>
        <div className="panel" style={{ margin: 0 }}>
          <b style={{ fontSize: 14 }}>Счета / Кассы</b>
          {d.accounts.map((a) => (
            <div key={a.id} className="row" style={{ padding: "8px 0", borderBottom: "1px solid #f1f5f9" }}>
              <span className="muted">{a.name}</span><b>{a.balance.toLocaleString("ru")} ₴</b>
            </div>
          ))}
        </div>
      </div>
      <div className="note">💡 Замена Finmap внутри CRM: каждая оплата по сделке (LiqPay/Checkbox/наличка) создаёт транзакцию. Доход/расход по категориям, прибыль с учётом складской себестоимости.</div>
    </div>
  );
}
