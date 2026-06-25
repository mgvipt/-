// Універсальний показ посилання на акаунт клієнта (різні месенджери)
export function SocialLink({ link, color = "#1d4ed8" }: { link?: string; color?: string }) {
  if (!link) return null;
  let label = "🔗 " + link;
  let sub = "";
  if (/^https?:\/\//.test(link)) {
    label = "🔗 " + link.replace(/^https?:\/\//, "");
  } else if (link.indexOf("tg://user?id=") === 0) {
    const id = link.split("=").pop() || "";
    label = "🔗 Відкрити профіль у Telegram";
    sub = "Telegram ID: " + id;
  } else if (link.indexOf("viber://") === 0) {
    const num = decodeURIComponent((link.split("number=").pop() || "")).replace("%2B", "+");
    label = "🔗 Відкрити чат у Viber";
    sub = num ? ("Viber: " + num) : "";
  }
  return (
    <div style={{ marginTop: 8 }}>
      <a href={link} target="_blank" rel="noreferrer" style={{ display: "block", fontSize: 12.5, color, wordBreak: "break-all", fontWeight: 600 }}>{label}</a>
      {sub ? <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2, userSelect: "all" }}>{sub}</div> : null}
    </div>
  );
}
