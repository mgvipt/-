import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Card, Funnel, Paginated } from "../api";
import { Avatar, SourceChip } from "../ui";
import { useLang } from "../i18n";

// Универсальный канбан для лидов и сделок. Перетаскивание карточки между
// колонками меняет стадию через PATCH к API.
export default function Board({ endpoint, funnel, query }: { endpoint: string; funnel: Funnel; query?: string }) {
  const [cards, setCards] = useState<Card[]>([]);
  const { t } = useLang();
  const [loading, setLoading] = useState(true);
  const [dropStage, setDropStage] = useState<number | null>(null);
  const dragId = useRef<number | null>(null);
  const nav = useNavigate();
  const isLead = endpoint.includes("leads");

  async function load() {
    setLoading(true);
    const data = await api.get<Paginated<Card>>(`${endpoint}?funnel=${funnel.id}&page_size=200${query || ""}`);
    setCards(data.results);
    setLoading(false);
  }
  useEffect(() => { load(); }, [endpoint, funnel.id, query]);

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

  if (loading) return <div className="spin">{t("Загрузка…","Завантаження…")}</div>;

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
                <div className="stage-head-rich" style={{ background: `linear-gradient(135deg, ${st.color}, ${st.color}cc)` }}>
                  <span className="sh-name">{st.name}{st.is_won ? " ✓" : st.is_lost ? " ✕" : ""}</span>
                  <span className="sh-meta">{colCards.length} · {sum.toLocaleString("ru")}₴</span>
                </div>
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
                    style={{ position: "relative" }}
                    draggable
                    onDragStart={() => { dragId.current = c.id; }}
                    onClick={() => nav(isLead ? `/leads/${c.id}` : `/deals/${c.id}`)}
                  >
                    {(c as any).contact && (
                      <span onClick={(e) => { e.stopPropagation(); nav(`/inbox?contact=${(c as any).contact}`); }}
                        title={t("Открыть чат с клиентом","Відкрити чат з клієнтом")}
                        style={{ position: "absolute", top: 6, right: 8, cursor: "pointer", fontSize: 15, lineHeight: 1 }}>💬</span>
                    )}
                    <div className="ttl">{c.title}</div>
                    <div className="price">{Number(c.amount).toLocaleString("ru")} грн.</div>
                    {(c as any).created_at && <div className="muted" style={{ fontSize: 10.5, marginBottom: 5 }}>🕓 {new Date((c as any).created_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</div>}
                    <SourceChip source={c.source} />
                    {c.owner_name && (
                      <div className="owner"><Avatar name={c.owner_name} />{c.owner_name}</div>
                    )}
                    {isLead && !c.is_seen && (
                      <div style={{ marginTop: 6 }}><span className="chip chip-unseen">{t("НЕПРОСМОТРЕННЫЕ","НЕПЕРЕГЛЯНУТІ")}</span></div>
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
