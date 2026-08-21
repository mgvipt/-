type Labels = {
  reply: string;
  client: string;
  manager: string;
  photo: string;
  video: string;
  voice: string;
  file: string;
  unavailable: string;
  reaction: string;
};

const UA: Labels = {
  reply: "Відповідь на",
  client: "Клієнт",
  manager: "Менеджер",
  photo: "Фото",
  video: "Відео",
  voice: "Голосове повідомлення",
  file: "Файл",
  unavailable: "Початкове повідомлення недоступне",
  reaction: "Реакція клієнта",
};

export type MessageContextLabels = Partial<Labels>;

type StatusLabels = {
  sent: string;
  delivered: string;
  read: string;
  failed: string;
  windowRisk: string;
  edited: string;
  previousVersion: string;
};

const UA_STATUS: StatusLabels = {
  sent: "Надіслано",
  delivered: "Доставлено",
  read: "Прочитано",
  failed: "Не доставлено",
  windowRisk: "Міг не дійти (вікно закрите)",
  edited: "змінено",
  previousVersion: "Попередня версія",
};

function labels(custom?: MessageContextLabels): Labels {
  return { ...UA, ...(custom || {}) };
}

function isHttpUrl(value: unknown): value is string {
  return typeof value === "string" && /^https?:\/\//i.test(value);
}

export function ReplyContext({ attachments, idPrefix, customLabels }: {
  attachments?: any[];
  idPrefix: string;
  customLabels?: MessageContextLabels;
}) {
  const l = labels(customLabels);
  const ref = (attachments || []).find((a: any) => a?.type === "reply_ref");
  if (!ref) return null;

  const media = ref.attachment || null;
  const mediaName = media?.type === "photo" ? l.photo
    : media?.type === "video" ? l.video
    : media?.type === "voice" ? l.voice
    : media ? l.file : "";
  const author = ref.direction === "in" ? l.client
    : ref.sender_name === "ai_assistant" ? "Юля (AI)" : l.manager;
  const preview = String(ref.text || mediaName || l.unavailable);
  const canJump = Number.isFinite(Number(ref.target_id)) && Number(ref.target_id) > 0;

  const jump = () => {
    if (!canJump) return;
    const el = document.getElementById(`${idPrefix}${ref.target_id}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    const prev = el.style.boxShadow;
    el.style.boxShadow = "0 0 0 3px rgba(37,99,235,.35)";
    window.setTimeout(() => { el.style.boxShadow = prev; }, 1500);
  };

  return (
    <div onClick={jump} title={canJump ? preview : undefined}
      style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 7, padding: "6px 8px",
        borderLeft: "3px solid #6366f1", borderRadius: 7, background: "rgba(99,102,241,.08)",
        cursor: canJump ? "pointer" : "default", minWidth: 150 }}>
      {isHttpUrl(media?.url) && media?.type === "photo" && (
        <img src={media.url} alt={l.photo} style={{ width: 42, height: 42, borderRadius: 6, objectFit: "cover", flexShrink: 0 }} />
      )}
      {media?.type === "video" && <span style={{ fontSize: 22, flexShrink: 0 }}>🎬</span>}
      {media?.type === "voice" && <span style={{ fontSize: 22, flexShrink: 0 }}>🎤</span>}
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, color: "#4f46e5", marginBottom: 2 }}>{l.reply}: {author}</div>
        <div style={{ fontSize: 11.5, color: "#475569", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 290 }}>{preview}</div>
      </div>
    </div>
  );
}

export function ReactionBadges({ attachments, customLabels }: {
  attachments?: any[];
  customLabels?: MessageContextLabels;
}) {
  const l = labels(customLabels);
  const grouped = new Map<string, number>();
  for (const item of attachments || []) {
    if (item?.type !== "message_reaction" || item?.actor !== "customer") continue;
    const emoji = String(item.emoji || item.reaction || "👍");
    grouped.set(emoji, (grouped.get(emoji) || 0) + 1);
  }
  if (!grouped.size) return null;
  return (
    <div style={{ display: "flex", gap: 4, marginTop: 5, flexWrap: "wrap" }} title={l.reaction}>
      {Array.from(grouped.entries()).map(([emoji, count]) => (
        <span key={emoji} style={{ display: "inline-flex", alignItems: "center", gap: 3, padding: "1px 6px",
          borderRadius: 12, background: "#fff", border: "1px solid #c7d2fe", boxShadow: "0 1px 2px rgba(0,0,0,.08)", fontSize: 14 }}>
          {emoji}{count > 1 && <small style={{ fontSize: 9, color: "#475569", fontWeight: 700 }}>{count}</small>}
        </span>
      ))}
    </div>
  );
}

export function MessageStatusLine({ message, time, customLabels }: {
  message: any;
  time: string;
  customLabels?: Partial<StatusLabels>;
}) {
  const l = { ...UA_STATUS, ...(customLabels || {}) };
  const history = (message?.attachments || []).find((a: any) => a?.type === "message_edit_history");
  const previous = String(history?.revisions?.[history.revisions.length - 1]?.text || "");
  const editedTitle = previous ? `${l.previousVersion}: ${previous}` : l.edited;

  if (message?.direction !== "out" || message?.internal) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 3, opacity: .58, fontSize: 10 }}>
        <span>{time}</span>
        {history && <span title={editedTitle} style={{ fontWeight: 600, cursor: previous ? "help" : "default" }}>· {l.edited}</span>}
      </div>
    );
  }

  const status = String(message?.status || "sent");
  const meta = status === "read"
    ? { icon: "✓✓", text: l.read, color: "#2563eb" }
    : status === "delivered"
      ? { icon: "✓✓", text: l.delivered, color: "#64748b" }
      : status === "failed"
        ? { icon: "✕", text: l.failed, color: "#b91c1c" }
        : status === "window_risk"
          ? { icon: "⚠", text: l.windowRisk, color: "#b45309" }
          : { icon: "✓", text: l.sent, color: "#64748b" };
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 5, marginTop: 3, fontSize: 10, color: meta.color }} title={meta.text}>
      <span style={{ opacity: .72 }}>{time}</span>
      {history && <span title={editedTitle} style={{ fontWeight: 600, cursor: previous ? "help" : "default" }}>· {l.edited}</span>}
      <span aria-label={meta.text} style={{ fontWeight: 800, letterSpacing: -1 }}>{meta.icon}</span>
    </div>
  );
}

export function isContextAttachment(attachment: any): boolean {
  return attachment?.type === "reply_ref"
    || attachment?.type === "message_reaction"
    || attachment?.type === "message_edit_history";
}
