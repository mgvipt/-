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
type MaterialSummary = { name: string; codes: number; catalog_pages: number; preview_url: string; photos?: number };
type Screen = "materials" | "material" | "color";
const SAND_EFFECTS = ["Galateya", "Eleganti", "Gaia Gloss", "Mio Gloss"] as const;
const isColorSwatch = (asset: Asset) => asset.kind === "image" && /(каталог|зразок|sample)/i.test(`${asset.title} ${asset.tags}`);
const effectFor = (asset: Asset) => {
  const match = (asset.tags || "").match(/(?:^|[,;\s])effect:([^,;]+)/i);
  // у мітці після назви фактури йдуть службові хвости (source:…, вид:…) — показуємо лише назву
  return (match?.[1] || "").split(/ · реальний об/i)[0].replace(/\s+(source|вид):\S+/g, "").trim();
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
  const [query, setQuery] = useState(""); const [tab, setTab] = useState<"colors" | "quick" | "instructions" | "ral">(initialTab || "colors");
  const [ralQ, setRalQ] = useState(""); const [ralBusy, setRalBusy] = useState(false); const [ralData, setRalData] = useState<any>(null);
  const [screen, setScreen] = useState<Screen>("materials"); const [material, setMaterial] = useState(""); const [color, setColor] = useState("");
  const [zoom, setZoom] = useState<Asset | null>(null);
  const [photosOpen, setPhotosOpen] = useState(false);
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
  // Реальні фото обʼєктів: окремо інтерʼєри (видно кімнату) і окремо образці (стіна крупно).
  const realPhotos = useMemo(() => materialItems.filter((x) => /реальне фото/i.test(x.tags || "")), [materialItems]);
  const realByKind = useMemo(() => {
    const q = query.trim().toLowerCase();
    const mk = (kind: "інтерʼєр" | "образець") => {
      const groups = new Map<string, Asset[]>();
      realPhotos.filter((a) => (kind === "інтерʼєр") === /вид:інтерʼєр/.test(a.tags || "")).forEach((a) => {
        const name = (effectFor(a) || "Реальні обʼєкти").replace(/ · реальний об.єкт$/i, "");
        if (q && !`${name} ${a.title}`.toLowerCase().includes(q)) return;
        groups.set(name, [...(groups.get(name) || []), a]);
      });
      return Array.from(groups.entries()).sort((a, b) => b[1].length - a[1].length);
    };
    return { interiors: mk("інтерʼєр"), samples: mk("образець") };
  }, [realPhotos, query]);
  const realCount = realByKind.interiors.reduce((n, g) => n + g[1].length, 0) + realByKind.samples.reduce((n, g) => n + g[1].length, 0);
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
  // Підбір нашого кольору за кодом клієнта (RAL Classic, RAL Design, NCS) і навпаки.
  async function ralSearch(q?: string) {
    const query = (q ?? ralQ).trim();
    if (!query) return;
    setRalBusy(true); setError("");
    try { setRalData(await api.get<any>(`/api/knowledge/colors/?q=${encodeURIComponent(query)}`)); }
    catch { setError("Не вдалося підібрати колір"); }
    finally { setRalBusy(false); }
  }
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

  return <>
  <div style={{ position: "absolute", zIndex: 50, left: 0, bottom: 46, width: 390, maxWidth: "calc(100vw - 24px)", maxHeight: 470, display: "flex", flexDirection: "column", overflow: "hidden", background: "#fff", border: "1px solid #cbd5e1", borderRadius: 12, padding: 10, boxShadow: "0 12px 32px rgba(15,23,42,.2)" }}>
    <div style={{ display: "flex", gap: 6, marginBottom: 8 }}><b style={{ fontSize: 13 }}>Бібліотека</b><span style={{ flex: 1 }} /><button className="btn" style={{ padding: "1px 7px" }} onClick={onClose}>×</button></div>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}><button className="btn" onClick={() => { setTab("colors"); setScreen("materials"); setMaterial(""); setColor(""); setQuery(""); loadPicker(); }} style={{ fontSize: 12, background: tab === "colors" ? "#e0edff" : undefined }}>🎨 Матеріали</button><button className="btn" onClick={() => { setTab("quick"); setQuery(""); }} style={{ fontSize: 12 }}>⚡ Швидкі відповіді</button><button className="btn" style={{fontSize:12}} onClick={() => setTab("instructions")}>Інструкції</button><button className="btn" style={{ fontSize: 12, background: tab === "ral" ? "#e0edff" : undefined }} onClick={() => setTab("ral")}>🎨 RAL / NCS</button></div>
    <input value={query} onChange={(e) => setQuery(e.target.value)} autoFocus
      placeholder={screen === "materials" ? "Пошук матеріалу" : "Знайти назву або код кольору"}
      style={{ width: "100%", boxSizing: "border-box", padding: "7px 9px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 13, marginBottom: 8, flexShrink: 0 }} />
    <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
    {tab === "ral" && <div>
      <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.45, marginBottom: 8 }}>
        Клієнт назвав колір за каталогом (RAL 7016, RAL Design 270 30 25, NCS S 2005-Y20R) — введіть код і побачите наші найближчі кольори з фото.
        Можна і навпаки: введіть наш код (FBK20-1,5) — покаже, який це приблизно RAL або NCS.
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 9 }}>
        <input value={ralQ} onChange={(e) => setRalQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") ralSearch(); }}
          placeholder="RAL 9010 · NCS S 1002-Y · FBK20-1,5"
          style={{ flex: 1, boxSizing: "border-box", padding: "7px 9px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 13 }} />
        <button className="btn btn-primary" disabled={ralBusy || !ralQ.trim()} onClick={() => ralSearch()} style={{ fontSize: 12.5 }}>{ralBusy ? "…" : "Підібрати"}</button>
      </div>
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 10 }}>
        {["RAL 9010", "RAL 1013", "RAL 7016", "NCS S 1002-Y"].map((x) => (
          <button key={x} className="btn" style={{ fontSize: 11.5, padding: "2px 8px" }} onClick={() => { setRalQ(x); ralSearch(x); }}>{x}</button>))}
      </div>
      {ralData?.found?.map((f: any) => <section key={f.code} style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
          <span style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid #dbe3ee", background: f.hex, flexShrink: 0 }} />
          <div style={{ minWidth: 0 }}><b style={{ fontSize: 13 }}>{f.label}</b>{f.name ? <span className="muted" style={{ fontSize: 11.5 }}> · {f.name}</span> : null}
            <br /><span className="muted" style={{ fontSize: 11 }}>наші найближчі кольори</span></div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7 }}>
          {f.ours?.map((o: any) => <div key={o.item_id} style={{ position: "relative", border: picked.includes(o.item_id) ? "2px solid var(--brand)" : "1px solid #dbe3ee", background: "#fff", borderRadius: 9, padding: 5 }}>
            <button type="button" onClick={() => toggle(o.item_id)} title={picked.includes(o.item_id) ? "Прибрати" : "Вибрати"}
              style={{ position: "absolute", top: 8, left: 8, zIndex: 2, width: 20, height: 20, borderRadius: 6, cursor: "pointer",
                border: picked.includes(o.item_id) ? "none" : "1px solid #cbd5e1", background: picked.includes(o.item_id) ? "var(--brand)" : "rgba(255,255,255,.9)", color: "#fff", fontSize: 12, lineHeight: "18px", padding: 0 }}>{picked.includes(o.item_id) ? "✓" : ""}</button>
            {o.preview_url && <img src={o.preview_url} loading="lazy" onClick={() => setZoom({ id: o.item_id, title: o.title, url: o.url, preview_url: o.preview_url } as any)}
              style={{ width: "100%", height: 72, objectFit: "cover", borderRadius: 6, cursor: "zoom-in", display: "block" }} />}
            <div style={{ fontSize: 11.5, marginTop: 4 }}><b>{o.code}</b><br />
              <span className="muted">{o.material} · збіг {o.level}</span></div>
          </div>)}
        </div>
      </section>)}
      {ralData?.reverse?.refs && <section style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
          <span style={{ width: 34, height: 34, borderRadius: 8, border: "1px solid #dbe3ee", background: ralData.reverse.hex }} />
          <div><b style={{ fontSize: 13 }}>{ralData.reverse.material} {ralData.reverse.code}</b><br />
            <span className="muted" style={{ fontSize: 11 }}>це приблизно такі кольори каталогів</span></div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7 }}>
          {ralData.reverse.refs.map((r: any) => <div key={r.system + r.code} style={{ display: "flex", gap: 7, alignItems: "center", border: "1px solid #dbe3ee", borderRadius: 9, padding: 6 }}>
            <span style={{ width: 26, height: 26, borderRadius: 6, background: r.hex, border: "1px solid #dbe3ee", flexShrink: 0 }} />
            <div style={{ minWidth: 0, fontSize: 11.5 }}><b>{r.system === "ral" ? r.code : "NCS " + r.code}</b><br />
              <span className="muted">{r.name ? r.name + " · " : ""}{r.level}</span></div>
          </div>)}
        </div>
      </section>}
      {ralData && !ralData.found?.length && !ralData.reverse?.refs && <div className="muted" style={{ fontSize: 12 }}>Не впізнали код. Приклади: RAL 9010, RAL Design 270 30 25, NCS S 2005-Y20R, або наш код FBK20-1,5.</div>}
      {ralData && <div className="muted" style={{ fontSize: 11, marginTop: 8, lineHeight: 1.4 }}>{ralData.note}</div>}
    </div>}
    {tab === "colors" && <>
      {screen !== "materials" && <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}><button className="btn" onClick={back} style={{ fontSize: 12 }}>← {screen === "color" ? material : "Усі матеріали"}</button>{screen === "material" && realCount > 0 && <button type="button" onClick={() => setPhotosOpen((v) => !v)} title="Фото наших обʼєктів: інтерʼєри й образці" style={{ fontSize: 12, cursor: "pointer", borderRadius: 8, padding: "4px 9px", border: photosOpen ? "1px solid var(--brand)" : "1px solid #dbe3ee", background: photosOpen ? "#e6eef8" : "#fff", fontWeight: photosOpen ? 700 : 500 }}>📸 Реальні обʼєкти <span className="muted" style={{ fontWeight: 500 }}>{realCount}</span></button>}</div>}
      {screen === "materials" && <><div className="muted" style={{ fontSize: 12, marginBottom: 7 }}>Спочатку оберіть матеріал — далі побачите лише кольори-образки. Відео та інтер'єри відкриваються всередині кольору.</div><div style={{ display: "grid", gap: 7 }}>{materials.map((entry) => <button key={entry.name} onClick={() => openMaterial(entry.name)} className="btn" style={{ display: "flex", alignItems: "center", gap: 8, textAlign: "left" }}>{entry.preview_url && <img src={entry.preview_url} loading="lazy" decoding="async" style={{ width: 42, height: 42, objectFit: "cover", borderRadius: 6 }} />}<span><b>{entry.name}</b><br /><span className="muted" style={{ fontSize: 11 }}>{["Фарби", "Підготовка та витратні матеріали"].includes(entry.name) ? `${entry.codes} товарів · фото й актуальна ціна` : entry.name === "Плінтуси Cezar" ? `${entry.codes} моделей і довжин` : entry.codes === 0 && entry.photos ? `${entry.photos} фото наших обʼєктів` : `${entry.codes} кольорів · ${entry.catalog_pages} сторінок каталогу${entry.photos ? ` · ${entry.photos} фото обʼєктів` : ""}`}</span></span><span style={{ marginLeft: "auto" }}>›</span></button>)}</div></>}
      {screen === "material" && <><b style={{ fontSize: 13 }}>{material}</b><div className="muted" style={{ fontSize: 12, margin: "3px 0 8px" }}>Сторінки каталогу та кольори-образки. Інтер'єри — після вибору кольору.</div>{catalogPages.length > 0 && <div style={{ marginBottom: 10 }}><b style={{ fontSize: 12 }}>📖 Каталог</b><div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7, marginTop: 5 }}>{catalogPages.map(card)}</div></div>}<b style={{ fontSize: 12 }}>🎨 Кольори ({colors.length})</b><div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 7, marginTop: 5 }}>{colors.map((code) => { const sample = materialItems.find((x) => x.color_code === code && isColorSwatch(x)); return <button key={code} onClick={() => openColor(code)} style={{ border: "1px solid #dbe3ee", background: "#fff", padding: 5, borderRadius: 8, textAlign: "left", cursor: "pointer" }}>{(sample?.preview_url || sample?.url) && <img src={sample?.preview_url || sample?.url} loading="lazy" decoding="async" style={{ width: "100%", height: 65, objectFit: "cover", borderRadius: 5 }} />}<div style={{ fontSize: 11, marginTop: 3 }}>{material === "Мокрий шовк" && silkColorName(code) && <b style={{ display: "block", fontSize: 13, lineHeight: 1.3, marginBottom: 3 }}>{silkColorName(code)}</b>}<b>{code}</b><br /><span className="muted">Відкрити добірку ›</span></div></button>; })}</div></>}
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
  </div>
    {photosOpen && screen === "material" && realCount > 0 && <div style={{ position: "absolute", zIndex: 51, left: (typeof window !== "undefined" && window.innerWidth < 830) ? 0 : 398, bottom: 46, width: 360,
      maxWidth: "calc(100vw - 24px)", maxHeight: 470, display: "flex", flexDirection: "column", overflow: "hidden", background: "#fff",
      border: "1px solid #cbd5e1", borderRadius: 12, padding: 10, boxShadow: "0 12px 32px rgba(15,23,42,.2)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 8 }}>
        <b style={{ fontSize: 13 }}>📸 Реальні обʼєкти</b>
        <span className="muted" style={{ fontSize: 11 }}>{material} · {realCount}</span>
        <span style={{ flex: 1 }} />
        <button className="btn" style={{ padding: "1px 7px" }} onClick={() => setPhotosOpen(false)}>×</button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        {([["Інтерʼєри", "видно кімнату", realByKind.interiors], ["Образці", "стіна крупним планом", realByKind.samples]] as [string, string, [string, Asset[]][]][])
          .filter(([, , groups]) => groups.length > 0).map(([label, hint, groups]) => <div key={label} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6, padding: "4px 0 2px", borderBottom: "1px solid #eef2f7", marginBottom: 7 }}>
            <b style={{ fontSize: 12 }}>{label}</b>
            <span className="muted" style={{ fontSize: 10.5 }}>{hint} · {groups.reduce((n, g) => n + g[1].length, 0)}</span>
          </div>
          {groups.map(([name, assets]) => <section key={name} style={{ marginBottom: 9 }}>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: "#334155" }}>{name} <span className="muted" style={{ fontWeight: 500 }}>· {assets.length}</span></div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 6, marginTop: 5 }}>{assets.map(photoCard)}</div>
          </section>)}
        </div>)}
      </div>
      {picked.length > 0 && <button className="btn btn-primary" disabled={busy} style={{ marginTop: 8, width: "100%", flexShrink: 0 }}
        onClick={() => { if (onStage) { onStage(items.filter((x) => picked.includes(x.id))); setPicked([]); onClose(); } else { send(); } }}>
        {busy ? "…" : onStage ? `Додати в повідомлення (${picked.length})` : `Надіслати (${picked.length})`}</button>}
    </div>}
  </>;
}
