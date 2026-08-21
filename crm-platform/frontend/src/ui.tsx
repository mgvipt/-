// Мелкие визуальные помощники (аватар-инициалы, бейдж канала).
export const SOURCES: Record<string, [string, string]> = {
  telegram: ["Telegram", "#27a7e7"], viber: ["Viber", "#7d4fc4"],
  instagram: ["Instagram", "#e1306c"], tiktok: ["TikTok", "#010101"], facebook: ["Facebook", "#1877f2"],
  whatsapp: ["WhatsApp", "#25d366"], call: ["Звонок", "#16a34a"],
  google_business: ["Google", "#ea4335"], other: ["Другое", "#64748b"],
};

const PALETTE = ["#2563eb", "#7c3aed", "#db2777", "#ea580c", "#059669", "#0891b2", "#4f46e5"];
function colorFor(s: string) {
  let n = 0; for (let i = 0; i < s.length; i++) n += s.charCodeAt(i);
  return PALETTE[n % PALETTE.length];
}
function initials(s: string) {
  const p = s.trim().split(/\s+/);
  return ((p[0]?.[0] ?? "") + (p[1]?.[0] ?? "")).toUpperCase();
}

export function Avatar({ name, cls }: { name: string; cls?: string }) {
  return <span className={"av " + (cls ?? "")} style={{ background: colorFor(name) }}>{initials(name)}</span>;
}

// Іконки каналів для круглого бейджа (замість повного слова) — єдиний розмір, зліва.
const CH_ICON: Record<string, string> = {
  telegram: "✈️", echat_telegram: "✈️", viber: "🟣", echat: "🟣",
  instagram: "📸", tiktok: "🎵", facebook: "📘", whatsapp: "🟢", echat_whatsapp: "🟢",
  call: "📞", google_business: "🔍", web: "🌐", other: "💬",
};
export function SourceChip({ source }: { source: string }) {
  const [label, color] = SOURCES[source] ?? SOURCES.other;
  const icon = CH_ICON[source] ?? CH_ICON.other;
  return (
    <span title={label} aria-label={label} style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 18, height: 18, borderRadius: "50%", flexShrink: 0,
      background: "#fff", border: `1.5px solid ${color}`, fontSize: 10, lineHeight: 1,
    }}>{icon}</span>
  );
}
