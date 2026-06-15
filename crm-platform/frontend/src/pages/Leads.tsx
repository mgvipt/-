import { useEffect, useState } from "react";
import { api, Funnel } from "../api";
import Board from "./Board";

export default function Leads() {
  const [funnel, setFunnel] = useState<Funnel | null>(null);

  useEffect(() => {
    api.get<{ results: Funnel[] }>("/api/funnels/").then((d) => {
      setFunnel(d.results.find((f) => f.is_lead_funnel) ?? d.results[0] ?? null);
    });
  }, []);

  if (!funnel) return <div className="spin">Загрузка воронки…</div>;
  return (
    <div className="kanban">
      <div className="toolbar">
        <button className="btn btn-primary">+ Создать</button>
        <input placeholder="Фильтр + поиск" />
        <div className="spacer" />
        <span className="muted">Видны лиды согласно вашим правам</span>
      </div>
      <Board endpoint="/api/leads/" funnel={funnel} />
    </div>
  );
}
