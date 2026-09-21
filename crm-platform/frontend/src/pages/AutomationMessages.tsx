import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

type Card = { key: string; title: string; group: string; when: string; result: string; messages: string[]; mode: string; note: string };
type Reference = { cards: Card[]; updated_at: string; help: string; delivery_note: string };

/** Read-only mirror: never feeds sample placeholders to the chat composer or send action. */
export function AutomationMessages({ onBack, onClose }: { onBack: () => void; onClose: () => void }) {
  const [data, setData] = useState<Reference | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("Усі етапи");
  const [selected, setSelected] = useState("");
  const [narrow, setNarrow] = useState(window.innerWidth < 760);
  const refresh = useCallback(async () => {
    setBusy(true);
    try { setData(await api.get<Reference>("/api/inbox/media-library/?view=automations")); setError(""); }
    catch { setError("Не вдалося оновити повідомлення. Перевірте з’єднання та спробуйте ще раз."); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => {
    void refresh();
    const focus = () => { if (!document.hidden) void refresh(); };
    const resize = () => setNarrow(window.innerWidth < 760);
    const timer = window.setInterval(focus, 60000);
    window.addEventListener("focus", focus);
    window.addEventListener("resize", resize);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", focus); window.removeEventListener("resize", resize); };
  }, [refresh]);
  const words = query.toLocaleLowerCase("uk").trim().split(/\s+/).filter(Boolean);
  const cards = (data?.cards || []).filter(c => (group === "Усі етапи" || c.group === group) && words.every(w => `${c.title} ${c.when} ${c.result} ${c.messages.join(" ")}`.toLocaleLowerCase("uk").includes(w)));
  const card = cards.find(c => c.key === selected) || cards[0];
  return <div role="dialog" aria-label="Автоматичні повідомлення клієнту" style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(15,23,42,.38)", display: "flex", alignItems: "center", justifyContent: "center", padding: narrow ? 6 : 16 }}>
    <div style={{ width: "min(1180px, 100%)", height: "min(820px, 94vh)", background: "#fff", borderRadius: 14, display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 24px 64px rgba(15,23,42,.3)" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 16px", borderBottom: "1px solid #e2e8f0", flexWrap: "wrap" }}>
        <button className="btn" type="button" onClick={onBack}>← Швидкі відповіді</button>
        <b style={{ flex: 1 }}>Автоматичні повідомлення клієнту</b>
        <button className="btn" type="button" disabled={busy} onClick={() => void refresh()}>{busy ? "Оновлюю…" : "Оновити"}</button>
        <button className="btn" type="button" onClick={onClose} aria-label="Закрити">×</button>
      </header>
      <div style={{ padding: "10px 16px", background: "#f0f7f4", fontSize: 13, lineHeight: 1.5 }}>
        <b>Актуальні тексти з автоматизацій</b> · Змінюються тут разом із ними.
        <div>{data?.help || "Завантажую чинні повідомлення…"}</div>
        {data && <small style={{ color: "#536577" }}>Перевірено о {new Date(data.updated_at).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}. Оновлюється при відкритті, поверненні до вікна й щохвилини.</small>}
      </div>
      {error && <div role="alert" style={{ color: "#b91c1c", padding: "8px 16px" }}>{error} {data && "Показані нижче тексти можуть бути застарілими."}</div>}
      <div style={{ padding: "10px 16px", display: "flex", gap: 8, flexWrap: "wrap", borderBottom: "1px solid #e2e8f0" }}>
        <input aria-label="Пошук автоматичних повідомлень" value={query} onChange={e => setQuery(e.target.value)} placeholder="Пошук: оплата, ТТН, майстер-клас…" style={{ flex: "1 1 240px", padding: 8, border: "1px solid #cbd5e1", borderRadius: 8, minWidth: 0 }} />
        {["Усі етапи", "Оплата", "Майстер-класи", "Доставка", "Після отримання"].map(g => <button className="btn" key={g} type="button" aria-pressed={g === group} onClick={() => setGroup(g)} style={{ background: g === group ? "#e0edff" : undefined }}>{g}</button>)}
      </div>
      <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: narrow ? "1fr" : "310px minmax(0, 1fr)", gridTemplateRows: narrow ? "minmax(110px, 30%) minmax(0, 1fr)" : "1fr" }}>
        <nav aria-label="Етапи оплати й доставки" style={{ overflowY: "auto", padding: 10, background: "#f8fafc", borderRight: "1px solid #e2e8f0" }}>
          {!cards.length && <p>{busy ? "Завантажую…" : "За цим запитом нічого не знайдено."}</p>}
          {cards.map(c => <button key={c.key} type="button" onClick={() => setSelected(c.key)} aria-current={c.key === card?.key ? "true" : undefined} style={{ width: "100%", textAlign: "left", display: "block", padding: "10px 12px", marginBottom: 6, borderRadius: 8, border: c.key === card?.key ? "1px solid #2e6fb0" : "1px solid #e2e8f0", background: c.key === card?.key ? "#eaf3fd" : "#fff", cursor: "pointer" }}>
            <small style={{ color: "#64748b" }}>{c.group}</small><div style={{ fontWeight: 650, margin: "3px 0" }}>{c.title}</div><small style={{ color: "#376457" }}>{c.mode}</small>
          </button>)}
        </nav>
        <article style={{ overflowY: "auto", padding: "16px 20px", fontSize: 14, lineHeight: 1.55 }}>
          {card && <>
            <h2 style={{ fontSize: 20, margin: "0 0 12px" }}>{card.title}</h2>
            <p><b>Коли:</b> {card.when}</p>
            <p><b>Що відбувається:</b> {card.result}</p>
            {card.note && <p style={{ background: "#fff8e6", padding: "9px 12px", borderRadius: 8 }}>{card.note}</p>}
            <h3 style={{ fontSize: 15, marginBottom: 8 }}>Що отримує клієнт</h3>
            {card.messages.length ? card.messages.map((text, i) => <section key={i} style={{ marginBottom: 12 }}>
              {card.messages.length > 1 && <div style={{ color: "#64748b", fontSize: 12, marginBottom: 4 }}>{card.key === "receipt" ? (i === 0 ? "Повна оплата — базовий варіант" : "Передоплата — базовий варіант") : `Повідомлення ${i + 1}`}</div>}
              <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", border: "1px solid #dce6e0", background: "#f3f8f5", padding: "12px 14px", borderRadius: "12px 12px 12px 3px" }}>{text}</div>
            </section>) : <p style={{ color: "#64748b" }}>Окреме повідомлення на цьому етапі не надсилається.</p>}
            {card.group === "Доставка" && <p style={{ color: "#64748b", fontSize: 12 }}>{data?.delivery_note}</p>}
            <p style={{ color: "#64748b", fontSize: 12 }}>Фактичний текст і результат відправки перевіряйте в чаті клієнта. Цей перегляд нічого не надсилає.</p>
          </>}
        </article>
      </div>
    </div>
  </div>;
}
