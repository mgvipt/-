import { useEffect, useState } from "react";
import { api, ChatMessage } from "../api";

type Asset = { id: number; title: string; color_code: string; tags: string; url: string; preview_url?: string; product?: Record<string, any> | null };
const MATERIAL = "Плінтуси Cezar";
const value = (a: Asset, key: string) => a.product ? String(a.product[key] ?? "") : (a.tags.match(new RegExp(`(?:^|\\s)${key}:([^\\s;]+)`)) || [])[1] || "";
const money = (n: number) => n.toLocaleString("uk-UA", { maximumFractionDigits: 2 });
const interiorStyle = (a: Asset) => /(?:^|\s)cad20260905(?:\s|$)/.test(a.tags) ? (a.tags.match(/(?:^|\s)style:(patera|silk)(?:\s|$)/) || [])[1] : undefined;

export function CezarLibrary({ conversationId, onSent, onBack, onClose }: {
  conversationId: number; onSent: (m: ChatMessage) => void; onBack: () => void; onClose: () => void;
}) {
  const [models, setModels] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<Asset | null>(null);
  const [photos, setPhotos] = useState<Asset[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [query, setQuery] = useState("");
  const [withPrice, setWithPrice] = useState(true);
  const [preview, setPreview] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const refresh = () => api.get<any>(`/api/inbox/media-library/?view=picker&material=${encodeURIComponent(MATERIAL)}`)
      .then(d => { if (active) { setModels(d.items || []); setSelected(current => current ? (d.items || []).find((a: Asset) => a.id === current.id) || null : null); } })
      .catch(() => { if (active) setError("Не вдалося завантажити моделі"); })
      .finally(() => { if (active) setLoading(false); });
    refresh(); window.addEventListener("focus", refresh);
    return () => { active = false; window.removeEventListener("focus", refresh); };
  }, []);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    setPhotos([]); setPicked([]); setPreview(false); setLoading(true); setError("");
    api.get<any>(`/api/inbox/media-library/?view=picker&material=${encodeURIComponent(MATERIAL)}&color=${encodeURIComponent(selected.color_code)}`)
      .then(d => { if (active) { setPhotos(d.items || []); if (d.items?.[0]?.product) setSelected(current => current ? { ...current, product: d.items[0].product } : null); setPicked((d.items || []).slice(0, 1).map((a: Asset) => a.id)); } })
      .catch(() => { if (active) setError("Не вдалося завантажити фото"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selected?.id]);
  const price = selected ? Number(value(selected, "price")) : 0;
  useEffect(() => { setPreview(false); }, [price]);
  const length = selected ? Number(value(selected, "length")) : 0;
  const specs = selected ? `${value(selected, "height")} × ${value(selected, "thickness")} мм · довжина ${money(length / 1000)} м` : "";
  const text = selected && withPrice ? `Плінтус Cezar ${selected.color_code}\nДюрополімер під фарбування\n${specs}\n${money(price)} грн за планку (${money(price / (length / 1000))} грн/м)` : "";
  const chosen = photos.filter(a => picked.includes(a.id));
  // Mirrors the existing send-library endpoint; preview and send use the same selection/text.
  const message = [text, ...chosen.map(a => `📷 Фото — ${a.color_code} · ${a.title}\n${a.url}`)].filter(Boolean).join("\n\n");
  async function send() {
    if (!preview || !chosen.length || busy) return;
    setBusy(true); setError("");
    try { const m = await api.post<ChatMessage>(`/api/conversations/${conversationId}/send-library/`, { item_ids: chosen.map(a => a.id), text, cezar_include_price: withPrice, cezar_preview_price: price }); onSent(m); onClose(); }
    catch (e: any) { setError(e?.response?.data?.detail || "Не вдалося надіслати"); }
    finally { setBusy(false); }
  }
  const cardStyle = { border: "1px solid #dbe3ee", background: "#fff", padding: 8, borderRadius: 9, textAlign: "left" as const, cursor: "pointer", color: "#172b42" };
  return <div style={{ position: "absolute", zIndex: 50, left: 0, bottom: 46, width: "min(480px, 100%)", maxWidth: "calc(100vw - 24px)", maxHeight: "min(650px, 75dvh)", display: "flex", flexDirection: "column", overflow: "hidden", background: "#fff", color: "#172b42", border: "1px solid #cbd5e1", borderRadius: 12, boxShadow: "0 12px 32px rgba(15,23,42,.2)" }}>
    <div style={{ padding: 14, display: "flex", alignItems: "center", gap: 8, borderBottom: "1px solid #e2e8f0" }}><b>Бібліотека · Плінтуси Cezar</b><button className="btn" aria-label="Закрити бібліотеку" disabled={busy} onClick={onClose} style={{ marginLeft: "auto" }}>×</button></div>
    <div style={{ padding: 14, overflowY: "auto", minHeight: 0 }}>
      <button className="btn" disabled={busy} onClick={() => { if (preview) setPreview(false); else if (selected) { setSelected(null); setError(""); } else onBack(); }} style={{ display: "block", marginBottom: 12 }}>← {preview ? "До фото" : selected ? "Усі моделі Cezar" : "Усі матеріали"}</button>
      {!selected && <>
        <input placeholder="Знайти модель, наприклад LPC-26" aria-label="Пошук моделі Cezar" value={query} onChange={e => setQuery(e.target.value)} style={{ width: "100%", padding: 9, border: "1px solid #cbd5e1", borderRadius: 8, marginBottom: 12 }} />
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 10 }}>Дюрополімер · під фарбування · {models.length} варіантів</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10 }}>
          {models.filter(a => a.color_code.toLowerCase().includes(query.toLowerCase())).map(a => <button key={a.id} style={cardStyle} onClick={() => setSelected(a)}>
            <img src={a.preview_url || a.url} alt={a.title} loading="lazy" decoding="async" style={{ width: "100%", height: 105, objectFit: "contain", background: "#fff" }} />
            <b style={{ display: "block", marginTop: 8 }}>{a.color_code}</b><div style={{ fontSize: 12, color: "#64748b", marginTop: 5 }}>{value(a,"height")} × {value(a,"thickness")} мм</div><div style={{ marginTop: 7 }}>{money(Number(value(a,"price")))} грн / шт.</div>
          </button>)}
        </div>
        {!loading && !models.filter(a => a.color_code.toLowerCase().includes(query.toLowerCase())).length && <p>Моделей не знайдено.</p>}
      </>}
      {selected && <>
        <b style={{ display: "block", fontSize: 18, marginBottom: 12 }}>Cezar {selected.color_code}</b>
        {!preview && <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginBottom: 14, alignItems: "center" }}>
          <img src={photos[0]?.url || selected.url} alt={`Профіль Cezar ${selected.color_code}`} style={{ flex: "1 1 170px", width: 170, height: 185, objectFit: "contain", borderRadius: 8, background: "#f8fafc" }} />
          <div style={{ flex: "1 1 150px" }}><div style={{ fontSize: 12, color: "#64748b" }}>Висота × товщина</div><b style={{ display: "block", fontSize: 20, margin: "4px 0 10px" }}>{value(selected,"height")} × {value(selected,"thickness")} мм</b>
          <div style={{ fontSize: 13 }}>Довжина планки: {money(length / 1000)} м</div><div style={{ fontSize: 12, color: "#64748b", marginTop: 6 }}>Дюрополімер · під фарбування</div>
          <div style={{ fontSize: 27, fontWeight: 700, marginTop: 12 }}>{money(price)} <span style={{ fontSize: 13, fontWeight: 400 }}>грн / шт.</span></div><div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>{money(price / (length / 1000))} грн / м</div></div>
        </div>}
        <div style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>Ціна Wallcov · {value(selected,"checked")}</div>
        {selected.product?.id && <div style={{ fontSize: 12, marginBottom: 12 }}><a href={`/warehouse?product=${selected.product.id}`} target="_blank" rel="noreferrer">Змінити ціну в номенклатурі ↗</a><span> · </span><a href="/shop-catalog" target="_blank" rel="noreferrer">Завантажити прайс ↗</a></div>}
        {!preview && selected.product?.description && <details style={{ marginBottom: 14, fontSize: 13 }}><summary style={{ cursor: "pointer", fontWeight: 600 }}>Як пояснити цінність клієнту</summary><div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, marginTop: 10 }}>{selected.product.description}</div></details>}
        {preview ? <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", padding: 12, background: "#f1f5f9", borderRadius: 8, fontSize: 13, lineHeight: 1.5 }}><b>Попередній перегляд повідомлення</b><div style={{ marginTop: 10 }}>{message}</div></div> : <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 9 }}>{photos.map(a => <div key={a.id} style={{ gridColumn: interiorStyle(a) ? "1 / -1" : undefined, minWidth: 0 }}><button aria-pressed={picked.includes(a.id)} style={{ ...cardStyle, width: "100%", border: picked.includes(a.id) ? "2px solid #397aca" : cardStyle.border }} onClick={() => { setPicked(ids => ids.includes(a.id) ? ids.filter(id => id !== a.id) : [...ids,a.id]); setPreview(false); }}>
            <img src={a.preview_url || a.url} alt={a.title} loading="lazy" style={{ width: "100%", height: interiorStyle(a) ? "auto" : 120, objectFit: "contain" }} /><span style={{ fontSize: 13 }}>{picked.includes(a.id) ? "✓ " : ""}{a.title}</span>
          </button>{interiorStyle(a) && <div style={{ display: "flex", flexWrap: "wrap", gap: 12, margin: "8px 0 12px", fontSize: 13 }}><a href={a.url} target="_blank" rel="noopener noreferrer">Відкрити інтер’єр ↗</a>{a.product?.sku && <a href={`https://wallcov.com.ua/interior/design-${interiorStyle(a)}-${encodeURIComponent(a.product.sku)}`} target="_blank" rel="noopener noreferrer">Розрахувати цей комплект ↗</a>}</div>}</div>)}</div>
          <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 15, fontSize: 13 }}><input type="checkbox" checked={withPrice} onChange={e => { setWithPrice(e.target.checked); setPreview(false); }} />Додати розміри й ціну до фото</label>
        </>}
      </>}
      {loading && <p role="status">Завантаження…</p>}{error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    </div>
    {selected && <div style={{ padding: 12, borderTop: "1px solid #e2e8f0" }}><button className="btn btn-primary" style={{ width: "100%" }} disabled={loading || busy || !chosen.length || !selected.product?.available || price <= 0 || length <= 0} onClick={preview ? send : () => setPreview(true)}>{busy ? "Надсилання…" : preview ? `Надіслати в чат (${chosen.length} фото)` : "Переглянути повідомлення"}</button></div>}
  </div>;
}
