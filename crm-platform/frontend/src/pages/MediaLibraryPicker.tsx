import { useEffect, useMemo, useState } from "react";
import { api, ChatMessage } from "../api";

type Asset = {
  id: number; title: string; kind: "image" | "video" | "catalog"; section: "colors" | "quick";
  material: string; color_code: string; tags: string; url: string;
};
type Reply = { id: number; title: string; text: string; asset_ids: number[] };
type Screen = "materials" | "material" | "color";
const isColorSwatch = (asset: Asset) => asset.kind === "image" && /(каталог|зразок|sample)/i.test(`${asset.title} ${asset.tags}`);
const effectFor = (asset: Asset) => {
  const match = (asset.tags || "").match(/(?:^|[,;\s])effect:([^,;]+)/i);
  return match?.[1]?.trim() || "";
};

export function MediaLibraryPicker({ conversationId, onSent, onClose, onInsertText, clientName }: { conversationId: number; onSent: (m: ChatMessage) => void; onClose: () => void; onInsertText?: (t: string) => void; clientName?: string }) {
  // Підставляє імʼя клієнта замість {Ім'я}/{Имя} у шаблоні швидкої відповіді.
  const fillName = (txt: string) => {
    const raw = (clientName || "").trim();
    const first = raw.split(/[\s(·|]/)[0].replace(/^@/, "");
    const name = first && !/^\d+$/.test(first) && first.length > 1 ? first : "";
    return (txt || "")
      .replace(/\{\s*(Ім['’]я|Имя|ім['’]я|имя)\s*\}[,]?\s*/g, name ? name + ", " : "")
      .replace(/^([a-zа-яіїєґ])/u, (m0) => (name ? m0 : m0.toUpperCase()));
  };
  const [items, setItems] = useState<Asset[]>([]); const [replies, setReplies] = useState<Reply[]>([]);
  const [query, setQuery] = useState(""); const [tab, setTab] = useState<"colors" | "quick">("colors");
  const [screen, setScreen] = useState<Screen>("materials"); const [material, setMaterial] = useState(""); const [color, setColor] = useState("");
  const [picked, setPicked] = useState<number[]>([]); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  useEffect(() => { api.get<any>("/api/inbox/media-library/").then((d) => { setItems(d.items || []); setReplies(d.replies || []); }).catch(() => setError("Не вдалося завантажити бібліотеку")); }, []);
  const colorItems = useMemo(() => items.filter((x) => x.section === "colors"), [items]);
  const materials = useMemo(() => Array.from(new Set(colorItems.map((x) => x.material || "Матеріал без назви"))).filter((x) => x.toLowerCase().includes(query.toLowerCase())), [colorItems, query]);
  const materialItems = useMemo(() => colorItems.filter((x) => (x.material || "Матеріал без назви") === material), [colorItems, material]);
  const catalogPages = useMemo(() => materialItems.filter((x) => x.kind === "catalog"), [materialItems]);
  const colors = useMemo(() => Array.from(new Set(materialItems.filter(isColorSwatch).map((x) => x.color_code).filter(Boolean))).filter((x) => x.toLowerCase().includes(query.toLowerCase())), [materialItems, query]);
  const colorAssets = useMemo(() => materialItems.filter((x) => x.color_code === color), [materialItems, color]);
  const colorGroups = useMemo(() => {
    const groups = new Map<string, Asset[]>();
    colorAssets.forEach((asset) => {
      const name = effectFor(asset) || (isColorSwatch(asset) || asset.kind === "video" ? "Еталон і відео" : "Інтер'єри");
      groups.set(name, [...(groups.get(name) || []), asset]);
    });
    return Array.from(groups.entries());
  }, [colorAssets]);
  function toggle(id: number) { setPicked((v) => v.includes(id) ? v.filter((x) => x !== id) : [...v, id]); }
  function openMaterial(name: string) { setMaterial(name); setColor(""); setQuery(""); setScreen("material"); }
  function openColor(code: string) { setColor(code); setQuery(""); setScreen("color"); }
  async function send(replyId?: number) { setBusy(true); setError(""); try { const m = await api.post<ChatMessage>(`/api/conversations/${conversationId}/send-library/`, replyId ? { reply_id: replyId } : { item_ids: picked }); onSent(m); onClose(); } catch (e: any) { setError(e?.response?.data?.detail || "Не вдалося надіслати"); } finally { setBusy(false); } }
  const card = (a: Asset) => <button key={a.id} onClick={() => toggle(a.id)} style={{ border: picked.includes(a.id) ? "2px solid var(--brand)" : "1px solid #dbe3ee", background: "#fff", padding: 5, borderRadius: 8, textAlign: "left", cursor: "pointer" }}>
    {a.url && a.kind !== "video" && <img src={a.url} style={{ width: "100%", height: 72, objectFit: "cover", borderRadius: 5 }} />}
    <div style={{ fontSize: 11, marginTop: 3 }}>{a.kind === "video" ? "🎥 " : ""}{a.kind === "catalog" ? "📖 " : ""}{a.title}</div>
  </button>;
  const back = () => { if (screen === "color") { setScreen("material"); setColor(""); } else { setScreen("materials"); setMaterial(""); } setQuery(""); };

  return <div style={{ position: "absolute", zIndex: 50, left: 0, bottom: 46, width: 390, maxWidth: "calc(100vw - 24px)", maxHeight: 470, overflow: "auto", background: "#fff", border: "1px solid #cbd5e1", borderRadius: 12, padding: 10, boxShadow: "0 12px 32px rgba(15,23,42,.2)" }}>
    <div style={{ display: "flex", gap: 6, marginBottom: 8 }}><b style={{ fontSize: 13 }}>Бібліотека</b><span style={{ flex: 1 }} /><button className="btn" style={{ padding: "1px 7px" }} onClick={onClose}>×</button></div>
    <div style={{ display: "flex", gap: 6, marginBottom: 8 }}><button className="btn" onClick={() => { setTab("colors"); setScreen("materials"); setQuery(""); }} style={{ fontSize: 12, background: tab === "colors" ? "#e0edff" : undefined }}>🎨 Матеріали</button><button className="btn" onClick={() => { setTab("quick"); setQuery(""); }} style={{ fontSize: 12, background: tab === "quick" ? "#e0edff" : undefined }}>⚡ Швидкі відповіді</button></div>
    {tab === "quick" && <div style={{ display: "grid", gap: 6, marginBottom: 8 }}>{replies.map((r) => <button key={r.id} className="btn" style={{ justifyContent: "flex-start", textAlign: "left", fontSize: 12 }} disabled={busy} onClick={() => {
      const hasAssets = (r.asset_ids || []).length > 0;
      if (!hasAssets && onInsertText) { onInsertText(fillName(r.text || "")); onClose(); return; }
      send(r.id);
    }}><b>{r.title}</b>{r.text ? <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}> — {r.text}</span> : ""}</button>)}</div>}
    {tab === "quick" && <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Пошук швидкої відповіді" style={{ width: "100%", boxSizing: "border-box", padding: "7px 9px", border: "1px solid #cbd5e1", borderRadius: 7, fontSize: 12 }} />}
    {tab === "colors" && <>
      {screen !== "materials" && <button className="btn" onClick={back} style={{ fontSize: 12, marginBottom: 8 }}>← {screen === "color" ? material : "Усі матеріали"}</button>}
      {screen === "materials" && <><div className="muted" style={{ fontSize: 12, marginBottom: 7 }}>Спочатку оберіть матеріал — далі побачите лише кольори-образки. Відео та інтер'єри відкриваються всередині кольору.</div><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Пошук матеріалу" style={{ width: "100%", boxSizing: "border-box", padding: "7px 9px", border: "1px solid #cbd5e1", borderRadius: 7, fontSize: 12, marginBottom: 8 }} /><div style={{ display: "grid", gap: 7 }}>{materials.map((name) => { const group = colorItems.filter((x) => (x.material || "Матеріал без назви") === name); const codes = new Set(group.filter(isColorSwatch).map((x) => x.color_code).filter(Boolean)).size; const preview = group.find(isColorSwatch) || group.find((x) => x.kind === "catalog"); return <button key={name} onClick={() => openMaterial(name)} className="btn" style={{ display: "flex", alignItems: "center", gap: 8, textAlign: "left" }}>{preview?.url && <img src={preview.url} style={{ width: 42, height: 42, objectFit: "cover", borderRadius: 6 }} />}<span><b>{name}</b><br /><span className="muted" style={{ fontSize: 11 }}>{codes} кольорів · {group.filter((x) => x.kind === "catalog").length} сторінок каталогу</span></span><span style={{ marginLeft: "auto" }}>›</span></button>; })}</div></>}
      {screen === "material" && <><b style={{ fontSize: 13 }}>{material}</b><div className="muted" style={{ fontSize: 12, margin: "3px 0 8px" }}>Сторінки каталогу та кольори-образки. Інтер'єри — після вибору кольору.</div>{catalogPages.length > 0 && <div style={{ marginBottom: 10 }}><b style={{ fontSize: 12 }}>📖 Каталог</b><div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7, marginTop: 5 }}>{catalogPages.map(card)}</div></div>}<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Знайти код кольору" style={{ width: "100%", boxSizing: "border-box", padding: "7px 9px", border: "1px solid #cbd5e1", borderRadius: 7, fontSize: 12, marginBottom: 8 }} /><b style={{ fontSize: 12 }}>🎨 Кольори ({colors.length})</b><div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7, marginTop: 5 }}>{colors.map((code) => { const sample = materialItems.find((x) => x.color_code === code && isColorSwatch(x)); return <button key={code} onClick={() => openColor(code)} style={{ border: "1px solid #dbe3ee", background: "#fff", padding: 5, borderRadius: 8, textAlign: "left", cursor: "pointer" }}>{sample?.url && <img src={sample.url} style={{ width: "100%", height: 65, objectFit: "cover", borderRadius: 5 }} />}<div style={{ fontSize: 11, marginTop: 3 }}><b>{code}</b><br /><span className="muted">Відкрити добірку ›</span></div></button>; })}</div></>}
      {screen === "color" && <><b style={{ fontSize: 13 }}>{material} · {color}</b><div className="muted" style={{ fontSize: 12, margin: "3px 0 8px" }}>{material === "Патера" ? "Оберіть ефект: усередині — інтер'єри та світло." : "Еталон, відео та інтер'єри цього кольору"}</div>{colorGroups.map(([name, assets]) => <section key={name} style={{ marginTop: 10 }}><b style={{ fontSize: 12 }}>{name === "Еталон і відео" ? "◈ " : "✦ "}{name}</b><div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7, marginTop: 5 }}>{assets.map(card)}</div></section>)}</>}
      {screen === "materials" && !materials.length && <div className="muted" style={{ fontSize: 12 }}>Матеріалів поки немає — додайте їх у Налаштування → Відкриті лінії.</div>}
    </>}
    {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 6 }}>{error}</div>}
    {picked.length > 0 && <button className="btn btn-primary" disabled={busy} onClick={() => send()} style={{ marginTop: 9, width: "100%" }}>{busy ? "…" : `Надіслати (${picked.length})`}</button>}
  </div>;
}
