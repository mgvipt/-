import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Card, Funnel, Paginated } from "../api";
import { Avatar, SourceChip } from "../ui";

// Универсальный канбан для лидов и сделок. Перетаскивание карточки между
// колонками меняет стадию через PATCH к API.
export default function Board({ endpoint, funnel }: { endpoint: string; funnel: Funnel }) {
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [dropStage, setDropStage] = useState<number | null>(null);
  const dragId = useRef<number | null>(null);
  const nav = useNavigate();
  const isLead = endpoint.includes("leads");

  async function load() {
    setLoading(true);
    const data = await api.get<Paginated<Card>>(`${endpoint}?funnel=${funnel.id}&page_size=200`);
    setCards(data.results);
    setLoading(false);
  }
  useEffect(() => { load(); }, [endpoint, funnel.id]);

  async function onDrop(stageId: number) {
    const id = dragId.current;
    setDropStage(null);
    dragId.current = null;
    if (id == null) return;
    const card = cards.find((c) => c.id === id);
    if (!card || card.stage === stageId) return;
    setCards((cs) => cs.map((c) => (c.id === id ? { ...c, stage: stageId } : c))); // оптимистично
    try { await api.patch(`${endpoint}${id}/`, { stage: stageId }); }
    catch { load(); } // откат при ошибке
  }

  if (loading) return <div className="spin">Загрузка…</div>;

  return (
    <div className="board fade">
      <div className="cols">
        {funnel.stages.map((st) => {
          const colCards = cards.filter((c) => c.stage === st.id);
          const sum = colCards.reduce((a, c) => a + Number(c.amount), 0);
          return (
            <div className="col" key={st.id}>
              {isLead ? (
                <div className="col-head" style={{ ["--c" as any]: st.color }}>
                  <b>{st.name}</b><span className="muted">{colCards.length}</span>
                </div>
              ) : (
                <div className="stage" style={{ background: st.color }}>{st.name}</div>
              )}
              <div
                className={"col-body" + (dropStage === st.id ? " drop" : "")}
                onDragOver={(e) => { e.preventDefault(); setDropStage(st.id); }}
                onDragLeave={() => setDropStage((s) => (s === st.id ? null : s))}
                onDrop={() => onDrop(st.id)}
              >
                <div className="sum">{sum.toLocaleString("ru")} грн.</div>
                {colCards.map((c) => (
                  <div
                    key={c.id}
                    className="card"
                    draggable
                    onDragStart={() => { dragId.current = c.id; }}
                    onClick={() => !isLead && nav(`/deals/${c.id}`)}
                  >
                    <div className="ttl">{c.title}</div>
                    <div className="price">{Number(c.amount).toLocaleString("ru")} грн.</div>
                    <SourceChip source={c.source} />
                    {c.owner_name && (
                      <div className="owner"><Avatar name={c.owner_name} />{c.owner_name}</div>
                    )}
                    {isLead && !c.is_seen && (
                      <div style={{ marginTop: 6 }}><span className="chip chip-unseen">НЕПЕРЕГЛЯНУТІ</span></div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
