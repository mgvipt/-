import { useEffect, useState } from "react";
import { api, Funnel } from "../api";
import Board from "./Board";

export default function Leads() {
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [ver, setVer] = useState(0);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");

  useEffect(() => {
    api.get<{ results: Funnel[] }>("/api/funnels/").then((d) => {
      setFunnel(d.results.find((f) => f.is_lead_funnel) ?? d.results[0] ?? null);
    });
  }, []);

  async function create() {
    if (!title.trim() || !funnel) return;
    const stage = funnel.stages[0]?.id;
    await api.post("/api/leads/", { title: title.trim(), funnel: funnel.id, stage, amount: 0, source: "other" });
    setCreating(false); setTitle(""); setVer((v) => v + 1);
  }

  if (!funnel) return <div className="spin">Загрузка воронки…</div>;
  return (
    <div className="kanban">
      <div className="toolbar">
        <button className="btn btn-primary" onClick={() => setCreating(true)}>+ Создать</button>
        <input placeholder="Фильтр + поиск" />
        <div className="spacer" />
        <span className="muted">Видны лиды согласно вашим правам</span>
      </div>
      <Board key={ver} endpoint="/api/leads/" funnel={funnel} />

      {creating && (
        <div onClick={() => setCreating(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>Новий лід</h3>
            <label className="label">Назва / клієнт</label>
            <input value={title} autoFocus onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()}
              placeholder="Напр. +380 67 ... — Покриття для стін"
              style={{ width: "100%", height: 38, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 14 }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setCreating(false)}>Скасувати</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={create}>Створити</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
