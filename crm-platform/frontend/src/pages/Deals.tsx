import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Funnel } from "../api";
import Board from "./Board";
import FunnelEditor from "./FunnelEditor";

export default function Deals() {
  const [funnels, setFunnels] = useState<Funnel[]>([]);
  const [curId, setCurId] = useState<number | null>(null);
  const [ver, setVer] = useState(0);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [editFunnel, setEditFunnel] = useState(false);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("-created_at");
  const [owner, setOwner] = useState("");
  const [users, setUsers] = useState<{ id: number; name: string }[]>([]);
  const nav = useNavigate();

  useEffect(() => {
    api.get<{ results: Funnel[] }>("/api/funnels/").then((d) => {
      const sales = d.results.filter((f) => !f.is_lead_funnel);
      setFunnels(sales);
      const saved = Number(localStorage.getItem("deals_funnel"));
      setCurId(sales.find((f) => f.id === saved) ? saved : (sales[0]?.id ?? null));
    });
  }, []);

  useEffect(() => { api.get<any>("/api/users/?page_size=100").then((d) => setUsers((d.results || d).map((u: any) => ({ id: u.id, name: u.get_full_name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username })))).catch(() => {}); }, []);

  const cur = funnels.find((f) => f.id === curId);
  const query = `&ordering=${sort}${search.trim() ? `&search=${encodeURIComponent(search.trim())}` : ""}${owner ? `&owner=${owner}` : ""}`;

  async function create() {
    if (!title.trim() || !cur) return;
    const stage = cur.stages[0]?.id;
    const d = await api.post<{ id: number }>("/api/deals/", { title: title.trim(), funnel: cur.id, stage, amount: 0, source: "other" });
    setCreating(false); setTitle("");
    nav(`/deals/${d.id}`);
  }

  if (!cur) return <div className="spin">Нет доступных воронок продаж.</div>;

  return (
    <div className="kanban">
      <div className="toolbar">
        <button className="btn btn-primary" onClick={() => setCreating(true)}>+ Сделка</button>
        <select value={curId ?? ""} onChange={(e) => { const id = Number(e.target.value); setCurId(id); localStorage.setItem("deals_funnel", String(id)); }}>
          {funnels.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <button className="btn btn-light" onClick={() => setEditFunnel(true)}>⚙ Воронка</button>
        <div className="spacer" />
        <span className="muted">Воронок доступно: {funnels.length}</span>
      </div>
      <Board key={ver} endpoint="/api/deals/" funnel={cur} query={query} />

      {creating && (
        <div onClick={() => setCreating(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>Нова сделка · {cur.name}</h3>
            <label className="label">Назва / клієнт</label>
            <input value={title} autoFocus onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()}
              placeholder="Напр. Турок Ірина — Покриття для стін"
              style={{ width: "100%", height: 38, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", marginBottom: 14 }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setCreating(false)}>Скасувати</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={create}>Створити</button>
            </div>
          </div>
        </div>
      )}

      {editFunnel && cur && (
        <FunnelEditor funnel={cur} onClose={() => setEditFunnel(false)}
          onSaved={(f) => { setFunnels((fs) => fs.map((x) => (x.id === f.id ? f : x))); setEditFunnel(false); setVer((v) => v + 1); }} />
      )}
    </div>
  );
}
