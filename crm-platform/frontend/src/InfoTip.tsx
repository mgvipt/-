/* (i) біля числа — «звідки це число»: формула на реальному прикладі (Розвиток v2, 16.09.2026).
 * Клік відкриває/закриває пояснення під числом; без бібліотек. Компонент верхнього рівня (не всередині render). */
import { useState } from "react";
import { Icon } from "./Icon";

export default function InfoTip({ text, title }: { text?: string | null; title?: string }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  return (
    <span style={{ display: "inline-block", verticalAlign: "middle" }}>
      <button type="button" aria-label={title || "Як пораховано"} title={title || "Як пораховано"} onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        style={{ border: "none", background: "transparent", cursor: "pointer", padding: "0 3px", color: open ? "#1d4ed8" : "#94a3b8", display: "inline-flex", alignItems: "center" }}>
        <Icon n="info" size={14} />
      </button>
      {open && (
        <span style={{ display: "block", position: "relative", zIndex: 5, marginTop: 4, maxWidth: 520, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "7px 10px", fontSize: 12, lineHeight: 1.5, color: "#334155", fontWeight: 400, whiteSpace: "normal", textAlign: "left" }}>
          {text}
        </span>
      )}
    </span>
  );
}
