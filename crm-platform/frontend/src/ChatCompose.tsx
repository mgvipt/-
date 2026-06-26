import { useState } from "react";

export const SALES_EMOJIS = "😊 🙂 😉 😍 🥰 😎 🤩 🤗 😋 🙏 👍 👌 🤝 👏 💪 🫶 🔥 💯 ✨ ⭐ 🌟 🎉 🥳 🎁 🛍️ 💎 💰 💳 🧾 📦 🚚 ✅ ☑️ 🆕 🔝 📲 📞 💬 ❓ ❗ ‼️ 💡 🎯 📍 🏷️ 🖌️ 🎨 🏠 🛋️ 🪞 🌈 ⚡ ⏰ 📅 🤔 😅 👋 ❤️ 🧡 💛 💚 💙 💜 🤍 🤎 🖤 🥇 📌 ➡️ ↩️".split(" ");

export function EmojiButton({ onPick, up = true }: { onPick: (e: string) => void; up?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative", flex: "0 0 auto" }}>
      <button className="btn" type="button" style={{ background: "#f1f5f9" }} title="Емодзі та символи" onClick={() => setOpen((o) => !o)}>😊</button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 49 }} />
          <div style={{ position: "absolute", [up ? "bottom" : "top"]: 44, left: 0, zIndex: 50, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 8px 24px rgba(15,23,42,.18)", padding: 8, width: 268, maxHeight: 210, overflowY: "auto", display: "grid", gridTemplateColumns: "repeat(8,1fr)", gap: 2 }}>
            {SALES_EMOJIS.map((e, i) => (
              <button key={i} type="button" onClick={() => { onPick(e); setOpen(false); }}
                style={{ border: "none", background: "transparent", fontSize: 19, cursor: "pointer", padding: 3, borderRadius: 6, lineHeight: 1 }}
                onMouseEnter={(ev) => (ev.currentTarget.style.background = "#f1f5f9")}
                onMouseLeave={(ev) => (ev.currentTarget.style.background = "transparent")}>{e}</button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
