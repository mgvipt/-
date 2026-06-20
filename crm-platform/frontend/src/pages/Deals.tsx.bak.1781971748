import { useEffect, useState } from "react";
import { api, Funnel } from "../api";
import Board from "./Board";

export default function Deals() {
  const [funnels, setFunnels] = useState<Funnel[]>([]);
  const [curId, setCurId] = useState<number | null>(null);

  useEffect(() => {
    api.get<{ results: Funnel[] }>("/api/funnels/").then((d) => {
      const sales = d.results.filter((f) => !f.is_lead_funnel);
      setFunnels(sales);
      setCurId(sales[0]?.id ?? null);
    });
  }, []);

  const cur = funnels.find((f) => f.id === curId);
  if (!cur) return <div className="spin">Нет доступных воронок продаж.</div>;

  return (
    <div className="kanban">
      <div className="toolbar">
        <button className="btn btn-primary">+ Сделка</button>
        <select value={curId ?? ""} onChange={(e) => setCurId(Number(e.target.value))}>
          {funnels.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <div className="spacer" />
        <span className="muted">Воронок доступно: {funnels.length}</span>
      </div>
      <Board endpoint="/api/deals/" funnel={cur} />
    </div>
  );
}
