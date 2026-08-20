// Картка джерела коментаря Meta: показує публікацію/ролик/рекламу, під якою клієнт залишив коментар.
// Кріпиться ОДИН раз зверху комент-чату, не дублюється біля кожного повідомлення.
import { Icon } from "./Icon";

const TYPE_LABEL: Record<string, string> = {
  IMAGE: "Публікація",
  VIDEO: "Відео",
  REEL: "Ролик",
  CAROUSEL_ALBUM: "Карусель",
  AD: "Реклама",
  STATUS: "Допис",
};

export default function ConversationSourceCard({ card }: { card?: any }) {
  if (!card || card.type !== "comment") return null;
  const isAd = !!card.is_ad;
  const typeLabel = isAd ? "Реклама" : (TYPE_LABEL[card.media_type] || "Публікація");
  const emoji = isAd ? "📣" : (card.media_type === "VIDEO" || card.media_type === "REEL" ? "🎬" : "🖼️");
  const isIG = card.platform === "instagram";
  const platLabel = isIG ? "Instagram" : "Facebook";
  const openLabel = isIG ? "Відкрити в Instagram" : "Відкрити в Facebook";

  return (
    <div style={{
      display: "flex", gap: 10, alignItems: "flex-start", padding: "8px 10px", marginBottom: 6,
      background: "#fff7ed", border: "1px solid #fed7aa", borderLeft: "3px solid #ea580c", borderRadius: 10,
    }}>
      {card.thumbnail
        ? <img src={card.thumbnail} alt="" style={{ width: 46, height: 46, borderRadius: 7, objectFit: "cover", flexShrink: 0, border: "1px solid #fed7aa" }} />
        : <div style={{ width: 46, height: 46, borderRadius: 7, flexShrink: 0, display: "grid", placeItems: "center", background: "#ffedd5", fontSize: 20 }}>{emoji}</div>}
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#9a3412", letterSpacing: ".01em" }}>
          {emoji} Коментар · {platLabel} · {typeLabel}
        </div>
        <div style={{ fontSize: 12, color: "#7c2d12", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
          {card.caption || <span style={{ color: "#c2795a" }}>Публікація без опису</span>}
        </div>
        <div style={{ display: "flex", gap: 12, marginTop: 4, alignItems: "center", flexWrap: "wrap" }}>
          {card.permalink && (
            <a href={card.permalink} target="_blank" rel="noreferrer" style={{ fontSize: 11.5, fontWeight: 600, color: "#ea580c", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
              <Icon n="link" size={12} /> {openLabel}
            </a>
          )}
          {card.parent_id && <span style={{ fontSize: 10.5, color: "#c2410c" }}>↳ відповідь у гілці</span>}
        </div>
      </div>
    </div>
  );
}
