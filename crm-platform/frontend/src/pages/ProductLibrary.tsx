import { useEffect, useState } from "react";
import { api, ChatMessage } from "../api";

type Asset = { id: number; title: string; color_code: string; url: string; preview_url?: string; product?: { id: number; display_name: string; price: string; unit: string; available: boolean; description: string } };
const money = (value: string) => Number(value).toLocaleString("uk-UA", { maximumFractionDigits: 2 });
const plain = (html: string) => {
  const doc = new DOMParser().parseFromString(html.replace(/<\/(p|div|li|h[1-6])>/gi, "\n").replace(/<br\s*\/?\s*>/gi, "\n"), "text/html");
  return doc.body.textContent?.trim() || "";
};

export function ProductLibrary({ material, conversationId, onSent, onBack, onClose }: { material: string; conversationId: number; onSent: (m: ChatMessage) => void; onBack: () => void; onClose: () => void }) {
  const [items, setItems] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<Asset | null>(null);
  const [photos, setPhotos] = useState<Asset[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const refresh = () => api.get<any>(`/api/inbox/media-library/?view=picker&material=${encodeURIComponent(material)}`)
      .then(d => { if (active) { setItems(d.items || []); setPreview(false); setSelected(s => s ? (d.items || []).find((a: Asset) => a.id === s.id) || null : null); } })
      .catch(() => { if (active) setError("Не вдалося завантажити товари"); })
      .finally(() => { if (active) setLoading(false); });
    refresh(); window.addEventListener("focus", refresh);
    return () => { active = false; window.removeEventListener("focus", refresh); };
  }, [material]);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    setLoading(true); setPhotos([]); setPicked([]); setPreview(false); setError("");
    api.get<any>(`/api/inbox/media-library/?view=picker&material=${encodeURIComponent(material)}&color=${encodeURIComponent(selected.color_code)}`)
      .then(d => { if (active) { setPhotos(d.items || []); setPicked(d.items?.length ? [d.items[0].id] : []); if (d.items?.[0]?.product) setSelected(s => s ? { ...s, product: d.items[0].product } : null); } })
      .catch(() => { if (active) setError("Не вдалося завантажити фото"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selected?.id, material]);
  const product = selected?.product;
  const chosen = photos.filter(a => picked.includes(a.id));
  const text = product ? `${product.display_name}\n${money(product.price)} грн / ${product.unit}` : "";
  const message = [text, ...chosen.map(a => `📷 Фото — ${a.color_code} · ${a.title}\n${a.url}`)].join("\n\n");
  const card = { border: "1px solid #dbe3ee", borderRadius: 9, padding: 10, background: "#fff", color: "#172b42", textAlign: "left" as const, cursor: "pointer", minWidth: 0 };
  async function send() {
    if (!preview || !product || !chosen.length || busy) return;
    setBusy(true); setError("");
    try {
      const m = await api.post<ChatMessage>(`/api/conversations/${conversationId}/send-library/`, { item_ids: chosen.map(a => a.id), text, cezar_include_price: true, cezar_preview_price: product.price });
      onSent(m); onClose();
    } catch (e: any) { setPreview(false); setError(e?.response?.data?.detail || "Не вдалося надіслати. Перевірте ціну та спробуйте знову."); }
    finally { setBusy(false); }
  }
  return <div style={{ position: "absolute", zIndex: 50, left: 0, bottom: 46, width: 480, maxWidth: "calc(100vw - 24px)", maxHeight: "min(650px,75dvh)", display: "flex", flexDirection: "column", background: "#fff", color: "#172b42", border: "1px solid #cbd5e1", borderRadius: 12, boxShadow: "0 12px 32px #0f172a33", overflow: "hidden" }}>
    <div style={{ display: "flex", padding: 14, gap: 12 }}><b>Бібліотека · {material}</b><button className="btn" disabled={busy} onClick={onClose} style={{ marginLeft: "auto" }}>×</button></div>
    <div style={{ padding: 14, overflowY: "auto", minHeight: 0 }}>
      <button className="btn" disabled={busy} onClick={() => preview ? setPreview(false) : selected ? setSelected(null) : onBack()}>← {preview ? "До товару" : selected ? "Усі товари" : "Усі матеріали"}</button>
      {!selected ? <><input aria-label="Пошук товару" placeholder="Знайти товар або виробника" value={query} onChange={e => setQuery(e.target.value)} style={{ width: "100%", margin: "12px 0", padding: 10 }} /><div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10 }}>{items.filter(a => `${a.color_code} ${a.product?.display_name || ""}`.toLowerCase().includes(query.toLowerCase())).map(a => <button key={a.id} style={card} onClick={() => setSelected(a)}><img src={a.preview_url || a.url} alt={a.color_code} loading="lazy" style={{ width: "100%", height: 120, objectFit: "contain" }} /><b style={{ display: "block", margin: "8px 0" }}>{a.product?.display_name || a.color_code}</b>{a.product && <span>{money(a.product.price)} грн / {a.product.unit}</span>}</button>)}</div></> : <>
        <h3>{product?.display_name || selected.color_code}</h3>
        {product && <p><b>{money(product.price)} грн / {product.unit}</b> · <a href={`/warehouse?product=${product.id}`} target="_blank" rel="noreferrer">Номенклатура ↗</a></p>}
        {preview ? <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", background: "#f1f5f9", padding: 12, lineHeight: 1.5 }}>{message}</div> : <>
          <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, fontSize: 14 }}>{plain(product?.description || "")}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 10 }}>{photos.map(a => <button key={a.id} style={{ ...card, border: picked.includes(a.id) ? "2px solid #397aca" : card.border }} aria-pressed={picked.includes(a.id)} onClick={() => setPicked(ids => ids.includes(a.id) ? ids.filter(id => id !== a.id) : [...ids, a.id])}><img src={a.preview_url || a.url} alt={a.title} style={{ width: "100%", height: 140, objectFit: "contain" }} /><span>{picked.includes(a.id) ? "✓ " : ""}{a.title}</span></button>)}</div>
        </>}
      </>}
      {loading && <p role="status">Завантаження…</p>}{error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    </div>
    {selected && <div style={{ padding: 12, borderTop: "1px solid #e2e8f0" }}><button className="btn btn-primary" style={{ width: "100%" }} disabled={busy || loading || !product?.available || !chosen.length} onClick={preview ? send : () => setPreview(true)}>{busy ? "Надсилання…" : preview ? "Надіслати в чат" : "Переглянути повідомлення з ціною"}</button></div>}
  </div>;
}
