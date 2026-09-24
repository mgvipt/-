import { useEffect, useMemo, useState } from "react";
import { api, ChatMessage } from "../api";
import { InstructionLibrary } from "./InstructionLibrary";
import { ProductLibrary } from "./ProductLibrary";
import { CezarLibrary } from "./CezarLibrary";
import { QuickRepliesScript, type Reply } from "./QuickRepliesScript";
import { silkColorName, formatSilkColor, matchesSilkColor } from "../silk-color-names";

type Asset = {
  id: number; title: string; kind: "image" | "video" | "catalog"; section: "colors" | "quick";
  material: string; color_code: string; tags: string; url: string; preview_url?: string;
};
type MaterialSummary = { name: string; codes: number; catalog_pages: number; preview_url: string };
type Screen = "materials" | "material" | "color";
const SAND_EFFECTS = ["Galateya", "Eleganti", "Gaia Gloss", "Mio Gloss"] as const;
const isColorSwatch = (asset: Asset) => asset.kind === "image" && /(каталог|зразок|sample)/i.test(`${asset.title} ${asset.tags}`);
const effectFor = (asset: Asset) => {
  const match = (asset.tags || "").match(/(?:^|[,;\s])effect:([^,;]+)/i);
  return match?.[1]?.trim() || "";
};

export function MediaLibraryPicker({ conversationId, onSent, onClose, onInsertText, onStage, clientName, initialTab }: { conversationId: number; onSent: (m: ChatMessage) => void; onClose: () => void; onInsertText?: (t: string) => void; onStage?: (items: Asset[]) => void; clientName?: string; initialTab?: "colors" | "quick" }) {
  // Підставляє імʼя клієнта замість {Ім'я}/{Имя} у шаблоні швидкої відповіді.
  const fillName = (txt: string) => {
    const raw = (clientName || "").trim();
    const first = raw.split(/[\s(·|]/)[0].replace(/^@/, "");
    const name = first && !/^\d+$/.test(first) && first.length > 1 ? first : "";
    return (txt || "")
      .replace(/\{\s*(Ім['’]я|Имя|ім['’]я|имя)\s*\}[,]?\s*/g, name ? name + ", " : "")
      .replace(/^([a-zа-яіїєґ])/u, (m0) => (name ? m0 : m0.toUpperCase()));
  };
  const [items, setItems] = useState<Asset[]>([]); const [replies, setReplies] = useState<Reply[]>([]); const [materialSummaries, setMaterialSummaries] = useState<MaterialSummary[]>([]);
  const [quickRefreshing, setQuickRefreshing] = useState(false);
  const [query, setQuery] = useState(""); const [tab, setTab] = useState<"colors" | "quick" | "instructions">(initialTab || "colors");
  const [screen, setScreen] = useState<Screen>("materials"); const [material, setMaterial] = useState(""); const [color, setColor] = useState("");
  const [zoom, setZoom] = useState<Asset | null>(null);
  const [picked, setPicked] = useState<number[]>([]); const [loaded, setLoaded] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const loadPicker = async (nextMaterial = "", nextColor = "") => {
    setError("");
    const params = new URLSearchParams({ view: "picker" });
    if (nextMaterial) params.set("material", nextMaterial);
    if (nextColor) params.set("color", nextColor);
    try {
      const d = await api.get<any>(`/api/inbox/media-library/?${params.toString()}`);
      setItems(d.items || []); setReplies(d.replies || []); setMaterialSummaries(d.materials || []); setLoaded(true);
    } catch { setError("Не вдалося завантажити бібліотеку"); }
  };
  useEffect(() => { loadPicker(); }, []);
  useEffect(() => {
    if (tab !== "quick") return;
    let alive = true, pending = false;
    setQuickRefreshing(true);
    const refreshReplies = async () => {
      if (!alive || pending || document.visibilityState !== "visible") return;
      pending = true;
      try {
        const d = await api.get<any>("/api/inbox/media-library/?view=picker");
        if (alive) { setReplies(d.replies || []); setLoaded(true); setError(""); }
      } catch { if (alive) setError("Не вдалося оновити ціни. Перевірте з’єднання перед використанням відповіді."); }
      finally { pending = false; if (alive) setQuickRefreshing(false); }
    };
    refreshReplies();
    const timer = window.setInterval(refreshReplies, 15000);
    window.addEventListener("focus", refreshReplies);
    document.addEventListener("visibilitychange", refreshReplies);
    return () => { alive = false; window.clearInterval(timer); window.removeEventListener("focus", refreshReplies); document.removeEventListener("visibilitychange", refreshReplies); };
  }, [tab]);
  const colorItems = useMemo(() => items.filter((x) => x.section === "colors"), [items]);
  const materials = useMemo(() => materialSummaries.filter((x) => x.name.toLowerCase().includes(query.toLowerCase())), [materialSummaries, query]);
  const materialItems = useMemo(() => colorItems.filter((x) => (x.material || "Матеріал без назви") === material), [colorItems, material]);
  const catalogPages = useMemo(() => materialItems.filter((x) => x.kind === "catalog"), [materialItems]);
  // Реальні фото обʼєктів: без коду кольору, згруповані за фактурою («Галатея (Galateya)» тощо).
  const realGroups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const groups = new Map<string, Asset[]>();
    materialItems.filter((x) => /реальне фото/i.test(x.tags || "")).forEach((a) => {
      const name = (effectFor(a) || "Реальні обʼєкти").replace(/ · реальний об.єкт$/i, "");
      if (q && !`${name} ${a.title}`.toLowerCase().includes(q)) return;
      groups.set(name, [...(groups.get(name) || []), a]);
    });
    return Array.from(groups.entries()).sort((a, b) => b[1].length - a[1].length);
  }, [materialItems, query]);
  const colors = useMemo(() => Array.from(new Set(materialItems.filter(isColorSwatch).map((x) => x.color_code).filter(Boolean))).filter((x) => material === "Мокрий шовк" ? matchesSilkColor(x, query) : x.toLowerCase().includes(query.toLowerCase())), [materialItems, query, material]);
  const colorAssets = useMemo(() => materialItems.filter((x) => x.color_code === color), [materialItems, color]);
  const colorGroups = useMemo(() => {
    const groups = new Map<string, Asset[]>();
    colorAssets.forEach((asset) => {
      const name = effectFor(asset) || (isColorSwatch(asset) || asset.kind === "video" ? "Еталон і відео" : "Інтер'єри");
      groups.set(name, [...(groups.get(name) || []), asset]);
    });
    return Array.from(groups.entries());
  }, [colorAssets]);
  const visibleColorGroups = useMemo(() => {
    if (material !== "Перламутрові піщинки") return colorGroups;
    const grouped = new Map(colorGroups);
    const ordered: [string, Asset[]][] = [];
    const reference = grouped.get("Еталон і відео");
    if (reference?.length) ordered.push(["Еталон і відео", reference]);
    SAND_EFFECTS.forEach((effect) => ordered.push([effect, grouped.get(effect) || []]));
    colorGroups.forEach(([name, assets]) => {
      if (name !== "Еталон і відео" && !SAND_EFFECTS.includes(name as typeof SAND_EFFECTS[number])) ordered.push([name, assets]);
    });
    return ordered;
  }, [colorGroups, material]);
  function toggle(id: number) { setPicked((v) => v.includes(id) ? v.filter((x) => x !== id) : [...v, id]); }
  function openMaterial(name: string) { setMaterial(name); setColor(""); setQuery(""); setScreen("material"); loadPicker(name); }
  function openColor(code: string) { setColor(code); setQuery(""); setScreen("color"); loadPicker(material, code); }
  async function send(replyId?: number) { setBusy(true); setError(""); try { const m = await api.post<ChatMessage>(`/api/conversations/${conversationId}/send-library/`, replyId ? { reply_id: replyId } : { item_ids: picked }); onSent(m); onClose(); } catch (e: any) { setError(e?.response?.data?.detail || "Не вдалося надіслати"); } finally { setBusy(false); } }
  const card = (a: Asset) => <div key={a.id} style={{ position: "relative", border: picked.includes(a.id) ? "2px solid var(--brand)" : "1px solid #dbe3ee", background: "#fff", padding: 5, borderRadius: 8, textAlign: "left" }}>
    <button type="button" onClick={() => toggle(a.id)} title={picked.includes(a.id) ? "Прибрати з вибраних" : "Вибрати"} style={{ position: "absolute", top: 8, left: 8, zIndex: 2, width: 22, height: 22, borderRadius: 6, cursor: "pointer", border: picked.includes(a.id) ? "none" : "1px solid #cbd5e1", background: picked.includes(a.id) ? "var(--brand)" : "rgba(255,255,255,.88)", color: "#fff", fontSize: 13, lineHeight: "20px", padding: 0 }}>{picked.includes(a.id) ? "✓" : ""}</button>
    {(a.preview_url || a.url) && a.kind !== "video" && <img src={a.preview_url || a.url} loading="lazy" decoding="async" onClick={() => setZoom(a)} title="Відкрити фото" style={{ width: "100%", height: 72, objectFit: "cover", borderRadius: 5, cursor: "zoom-in" }} />}
    <div style={{ fontSize: 11, marginTop: 3 }}>{a.kind === "video" ? "🎥 " : ""}{a.kind === "catalog" ? "📖 " : ""}{a.material === "Мокрий шовк" && silkColorName(a.color_code) ? `${silkColorName(a.color_code)} · ` : ""}{a.title}</div>
  </div>;
  // Фото інтерʼєру вертикальне: видно стіну від підлоги до стелі, а не смужку.
  const photoCard = (a: Asset) => <div key={a.id} style={{ position: "relative", border: picked.includes(a.id) ? "2px solid var(--brand)" : "1px solid #dbe3ee", background: "#fff", padding: 4, borderRadius: 10 }}>
    <button type="button" onClick={() => toggle(a.id)} title={picked.includes(a.id) ? "Прибрати з вибраних" : "Вибрати"} style={{ position: "absolute", top: 8, left: 8, zIndex: 2, width: 22, height: 22, borderRadius: 6, cursor: "pointer", border: picked.includes(a.id) ? "none" : "1px solid #cbd5e1", background: picked.includes(a.id) ? "var(--brand)" : "rgba(255,255,255,.88)", color: "#fff", fontSize: 13, lineHeight: "20px", padding: 0 }}>{picked.includes(a.id) ? "✓" : ""}</button>
    <img src={a.preview_url || a.url} loading="lazy" decoding="async" onClick={() => setZoom(a)} title="Відкрити фото" style={{ width: "100%", aspectRatio: "3 / 4", objectFit: "cover", borderRadius: 7, cursor: "zoom-in", display: "block" }} />
  </div>;
  const back = () => { if (screen === "color") { setScreen("material"); setColor(""); loadPicker(material); } else { setScreen("materials"); setMaterial(""); loadPicker(); } setQuery(""); };

  // Швидкі відповіді — велике вікно-«скрипт продажів» з етапами розмови (14.09).
  if (tab === "instructions") return <InstructionLibrary conversationId={conversationId} onInsertText={onInsertText} onClose={onClose} onBack={() => setTab("colors")} />;

  if (tab === "quick") return <QuickRepliesScript replies={replies} loading={!loaded || quickRefreshing} fillName={fillName} busy={busy || quickRefreshing} error={error}
    onClose={onClose} onBack={() => setTab("colors")}
    onInsert={onInsertText ? (txt) => { onInsertText(txt); onClose(); } : undefined}
    onSend={(id) => send(id)} />;

  if (tab === "colors" && ["Фарби", "Підготовка та витратні матеріали"].includes(material)) return <ProductLibrary material={material} conversationId={conversationId} onSent={onSent} onClose={onClose} onBack={() => { setMaterial(""); setScreen("materials"); loadPicker(); }} />;

  if (tab === "colors" && material === "Плінтуси Cezar") return <CezarLibrary conversationId={conversationId} onSent={onSent} onClose={onClose} onBack={() => { setMaterial(""); setScreen("materials"); loadPicker(); }} />;

  return <div style={{ position: "absolute", zIndex: 50, left: 0, bottom: 46, width: 390, maxWidth: "calc(100vw - 24px)", maxHeight: 470, display: "flex", flexDirection: "column", overflow: "hidden", background: "#fff", border: "1px solid #cbd5e1", borderRadius: 12, padding: 10, boxShadow: "0 12px 32px rgba(15,23,42,.2)" }}>
    <div style={{ display: "flex", gap: 6, marginBottom: 8 }}><b style={{ fontSize: 13 }}>Бібліотека</b><span style={{ flex: 1 }} /><button className="btn" style={{ padding: "1px 7px" }} onClick={onClose}>×</button></div>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}><button className="btn" onClick={() => { setTab("colors"); setScreen("materials"); setMaterial(""); setColor(""); setQuery(""); loadPicker(); }} style={{ fontSize: 12, background: tab === "colors" ? "#e0edff" : undefined }}>🎨 Матеріали</button><button className="btn" onClick={() => { setTab("quick"); setQuery(""); }} style={{ fontSize: 12 }}>⚡ Швидкі відповіді</button><button className="btn" style={{fontSize:12}} onClick={() => setTab("instructions")}>Інструкції</button></div>
    <input value={query} onChange={(e) => setQuery(e.target.value)} autoFocus
      placeholder={screen === "materials" ? "Пошук матеріалу" : "Знайти назву або код кольору"}
      style={{ width: "100%", boxSizing: "border-box", padding: "7px 9px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 13, marginBottom: 8, flexShrink: 0 }} />
    <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
    {tab === "colors" && <>
      {screen !== "materials" && <button className="btn" onClick={back} style={{ fontSize: 12, marginBottom: 8 }}>← {screen === "color" ? material : "Усі матеріали"}</button>}
      {screen === "materials" && <><div className="muted" style={{ fontSize: 12, marginBottom: 7 }}>Спочатку оберіть матеріал — далі побачите лише кольори-образки. Відео та інтер'єри відкриваються всередині кольору.</div><div style={{ display: "grid", gap: 7 }}>{materials.map((entry) => <button key={entry.name} onClick={() => openMaterial(entry.name)} className="btn" style={{ display: "flex", alignItems: "center", gap: 8, textAlign: "left" }}>{entry.preview_url && <img src={entry.preview_url} loading="lazy" decoding="async" style={{ width: 42, height: 42, objectFit: "cover", borderRadius: 6 }} />}<span><b>{entry.name}</b><br /><span className="muted" style={{ fontSize: 11 }}>{["Фарби", "Підготовка та витратні матеріали"].includes(entry.name) ? `${entry.codes} товарів · фото й актуальна ціна` : entry.name === "Плінтуси Cezar" ? `${entry.codes} моделей і довжин` : `${entry.codes} кольорів · ${entry.catalog_pages} сторінок каталогу`}</span></span><span style={{ marginLeft: "auto" }}>›</span></button>)}</div></>}
      {screen === "material" && <><b style={{ fontSize: 13 }}>{material}</b><div className="muted" style={{ fontSize: 12, margin: "3px 0 8px" }}>Сторінки каталогу та кольори-образки. Інтер'єри — після вибору кольору.</div>{catalogPages.length > 0 && <div style={{ marginBottom: 10 }}><b style={{ fontSize: 12 }}>📖 Каталог</b><div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7, marginTop: 5 }}>{catalogPages.map(card)}</div></div>}{realGroups.length > 0 && <div style={{ marginBottom: 14, padding: "9px 9px 11px", border: "1px solid #dbe3ee", borderRadius: 11, background: "#f8fafc" }}><div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 2 }}><b style={{ fontSize: 12.5 }}>📸 Реальні обʼєкти</b><span className="muted" style={{ fontSize: 11 }}>{realGroups.reduce((n, g) => n + g[1].length, 0)} фото · наші роботи</span></div>{realGroups.map(([name, assets]) => <section key={name} style={{ marginTop: 8 }}><div style={{ fontSize: 11.5, fontWeight: 700, color: "#334155" }}>{name} <span className="muted" style={{ fontWeight: 500 }}>· {assets.length}</span></div><div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 6, marginTop: 5 }}>{assets.map(photoCard)}</div></section>)}</div>}<div style={{ borderTop: "1px dashed #dbe3ee", marginBottom: 9 }} /><b style={{ fontSize: 12 }}>🎨 Кольори ({colors.length})</b><div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7, marginTop: 5 }}>{colors.map((code) => { const sample = materialItems.find((x) => x.color_code === code && isColorSwatch(x)); return <button key={code} onClick={() => openColor(code)} style={{ border: "1px solid #dbe3ee", background: "#fff", padding: 5, borderRadius: 8, textAlign: "left", cursor: "pointer" }}>{(sample?.preview_url || sample?.url) && <img src={sample?.preview_url || sample?.url} loading="lazy" decoding="async" style={{ width: "100%", height: 65, objectFit: "cover", borderRadius: 5 }} />}<div style={{ fontSize: 11, marginTop: 3 }}>{material === "Мокрий шовк" && silkColorName(code) && <b style={{ display: "block", fontSize: 13, lineHeight: 1.3, marginBottom: 3 }}>{silkColorName(code)}</b>}<b>{code}</b><br /><span className="muted">Відкрити добірку ›</span></div></button>; })}</div></>}
      {screen === "color" && <><b style={{ fontSize: 13 }}>{material} · {material === "Мокрий шовк" ? formatSilkColor(color) : color}</b><div className="muted" style={{ fontSize: 12, margin: "3px 0 8px" }}>{material === "Патера" ? "Оберіть ефект: усередині — інтер'єри та світло." : material === "Перламутрові піщинки" ? "Оберіть вид піщинок — інтер'єри додамо після затвердження фактури." : "Еталон, відео та інтер'єри цього кольору"}</div>{visibleColorGroups.map(([name, assets]) => <section key={name} style={{ marginTop: 10 }}><b style={{ fontSize: 12 }}>{name === "Еталон і відео" ? "◈ " : "✦ "}{name}</b>{assets.length > 0 ? <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7, marginTop: 5 }}>{assets.map(card)}</div> : <div className="muted" style={{ fontSize: 11, marginTop: 4, padding: "7px 8px", border: "1px dashed #dbe3ee", borderRadius: 7 }}>Інтер'єри додамо після затвердження фактури.</div>}</section>)}</>}
      {screen === "materials" && !materials.length && <div className="muted" style={{ fontSize: 12 }}>Матеріалів поки немає — додайте їх у Налаштування → Відкриті лінії.</div>}
    </>}
    </div>
    {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 6 }}>{error}</div>}
    {picked.length > 0 && <button className="btn btn-primary" disabled={busy} onClick={() => { if (onStage) { onStage(items.filter((x) => picked.includes(x.id))); setPicked([]); onClose(); } else { send(); } }} style={{ marginTop: 9, width: "100%", flexShrink: 0, position: "sticky", bottom: 0 }}>{busy ? "…" : onStage ? `Додати в повідомлення (${picked.length})` : `Надіслати (${picked.length})`}</button>}
    {zoom && <div onClick={() => setZoom(null)} style={{ position: "fixed", inset: 0, zIndex: 3000, background: "rgba(8,12,20,.9)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, padding: 16 }}>
      <img src={zoom.url || zoom.preview_url} alt="" onClick={(e) => e.stopPropagation()} style={{ maxWidth: "min(900px, 92vw)", maxHeight: "calc(100vh - 150px)", objectFit: "contain", borderRadius: 10, background: "#000" }} />
      <div style={{ color: "#e8edf5", fontSize: 13, textAlign: "center", maxWidth: "90vw" }}>{zoom.title}</div>
      <div style={{ display: "flex", gap: 8 }} onClick={(e) => e.stopPropagation()}>
        <button className="btn btn-primary" onClick={() => { if (onStage) { onStage([zoom]); setZoom(null); onClose(); } else { setPicked((v) => v.includes(zoom.id) ? v : [...v, zoom.id]); setZoom(null); } }}>{onStage ? "Додати в повідомлення" : "Вибрати"}</button>
        <button className="btn" onClick={() => setZoom(null)}>Закрити</button>
      </div>
    </div>}
  </div>;
}
