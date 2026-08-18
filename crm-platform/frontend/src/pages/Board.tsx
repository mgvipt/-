import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Card, Funnel, Paginated } from "../api";
import { Avatar, SourceChip } from "../ui";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

function socialMeta(link?: string) {
  if (!link) return null;
  const l = link.toLowerCase();
  if (l.includes("instagram")) return { icon: "instagram", label: "Instagram" };
  if (l.includes("facebook") || l.includes("fb.com") || l.includes("fb.me") || l.includes("m.me")) return { icon: "facebook", label: "Facebook" };
  if (l.includes("t.me") || l.includes("telegram")) return { icon: "telegram", label: "Telegram" };
  if (l.includes("viber")) return { icon: "viber", label: "Viber" };
  if (l.includes("tiktok")) return { icon: "tiktok", label: "TikTok" };
  return { icon: "link", label: "Профіль" };
}

// Универсальный канбан для лидов и сделок. Перетаскивание карточки между
// колонками меняет стадию через PATCH к API.
export default function Board({ endpoint, funnel, query, visibleStages }: { endpoint: string; funnel: Funnel; query?: string; visibleStages?: number[] }) {
  const [cards, setCards] = useState<Card[]>([]);
  const { t } = useLang();
  const [loading, setLoading] = useState(true);
  const [dropStage, setDropStage] = useState<number | null>(null);
  const dragId = useRef<number | null>(null);
  const nav = useNavigate();
  const isLead = endpoint.includes("leads");

  const [chatBadges, setChatBadges] = useState<any>({});
  async function load() {
    setLoading(true);
    // архивная воронка: НЕ грузим авто (только по поиску) — чтобы тысячи сделок не тормозили CRM
    if ((funnel as any).is_archive && !(query && query.trim())) { setCards([]); setLoading(false); return; }
    // грузим ВСЕ страницы воронки (max_page_size=500) — иначе сделки за пределом лимита пропадают с доски
    let all: Card[] = [];
    let page = 1;
    while (page <= 40) {
      const data = await api.get<Paginated<Card>>(`${endpoint}?funnel=${funnel.id}&page_size=500&page=${page}${(isLead || (funnel as any).is_archive) ? "" : ((query && query.includes("closed=")) ? "" : "&closed=recent")}${query || ""}`);
      all = all.concat(data.results || []);
      if (!(data as any).next || !(data.results || []).length) break;
      page++;
    }
    setCards(all);
    setLoading(false);
    if (!isLead && all.length) {
      // бейджи чата чанками по 200 (иначе URL со всеми id слишком длинный)
      const badges: any = {};
      for (let i = 0; i < all.length; i += 200) {
        try {
          const b = await api.get<any>(`/api/inbox/deal-badges/?ids=${all.slice(i, i + 200).map((c: any) => c.id).join(",")}`);
          Object.assign(badges, b);
        } catch { /* мовчки */ }
      }
      setChatBadges(badges);
    }
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
    catch (e: any) {
      if (e?.data?.confirm_unpaid && confirm(e.data.warn || "Угода оплачена не повністю. Точно перенести на цю стадію?")) {
        try { await api.patch(`${endpoint}${id}/`, { stage: stageId, confirm_unpaid: 1 }); } catch { load(); }
      } else { load(); }
    } // підтвердження/відкат
  }

  if (loading) return <div className="spin">{t("Загрузка…","Завантаження…")}</div>;
  if ((funnel as any).is_archive && !(query && query.trim())) return (
    <div className="panel" style={{ margin: 0, padding: "22px 18px", textAlign: "center", color: "#475569" }}>
      📦 <b>{t("Архивная воронка","Архівна воронка")}</b><br/>
      <span style={{ fontSize: 13 }}>{t("Сделки сохранены в истории клиентов и не грузятся на доску, чтобы не тормозить CRM. Найдите нужную сделку через 🔍 поиск сверху (ищет и открытые, и закрытые).","Угоди збережені в історії клієнтів і не вантажаться на дошку, щоб не гальмувати CRM. Знайдіть потрібну угоду через 🔍 пошук зверху (шукає і відкриті, і закриті).")}</span>
    </div>
  );

  return (
    <div className="board fade">
      <div className="cols">
        {funnel.stages.filter((st) => !visibleStages || visibleStages.length === 0 || visibleStages.includes(st.id)).map((st) => {
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
                        style={{ position: "absolute", top: 6, right: 8, cursor: "pointer", fontSize: 15, lineHeight: 1 }}><Icon n="💬" size={15} /></span>
                    )}
                    <div className="ttl">{c.title}</div>
                    {(c as any).contact_name && <div style={{ fontSize: 11.5, fontWeight: 600, color: "#334155", margin: "1px 0 2px" }}><Icon n="👤" size={13} /> {(c as any).contact_name}</div>}
                    {(() => { const m = socialMeta((c as any).contact_social_link); return m ? (<a href={(c as any).contact_social_link} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 10.5, fontWeight: 600, color: "#2563eb", textDecoration: "none", marginBottom: 3 }}><Icon n={m.icon} size={12} /> {m.label}</a>) : null; })()}
                    <div className="price">{Number(c.amount).toLocaleString("ru")} грн.</div>
                    {(c as any).created_at && <div className="muted" style={{ fontSize: 10.5, marginBottom: 5 }}><Icon n="🕓" size={12} /> {new Date((c as any).created_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</div>}
                    <SourceChip source={c.source} />
                    {c.owner_name && (
                      <div className="owner"><Avatar name={c.owner_name} />{c.owner_name}</div>
                    )}
                    <div style={{ marginTop: 6, display: "flex", gap: 5, alignItems: "center", flexWrap: "wrap" }}>{!c.is_seen
                      ? <span className="chip chip-unseen">{t("НЕ ОТВЕЧЕНО","НЕ ВІДПОВІЛИ")}</span>
                      : <span style={{ fontSize: 10.5, fontWeight: 600, color: "#0F6E56", background: "#E1F5EE", padding: "2px 8px", borderRadius: 20 }}>{t("✓ Отвечено","✓ Відповіли")}</span>}
                      {chatBadges[c.id]?.unread > 0 && <span title={t("Клиент написал — менеджер не читал", "Клієнт написав — менеджер не читав")} style={{ fontSize: 10.5, fontWeight: 800, background: "#ef4444", color: "#fff", borderRadius: 20, padding: "2px 7px" }}>✉ {chatBadges[c.id].unread}</span>}
                      {chatBadges[c.id]?.unread > 0 && chatBadges[c.id]?.ai && <span title={t("ИИ-агент ответил, менеджер не смотрел", "ШІ-агент відповів, менеджер не дивився")} style={{ fontSize: 10.5, fontWeight: 700, background: "#eef2ff", color: "#4f46e5", borderRadius: 20, padding: "2px 7px" }}>🤖 {t("відповів ШІ","відповів ШІ")}</span>}
                    </div>
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
