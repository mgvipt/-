// 19.09.2026 (Олег): склад перевіряє наявність і формує заявку на дозамовлення зі свого кабінету.
// Зверху — те, що впало нижче мінімального залишку (підтягується саме); нижче — пошук по всій номенклатурі.
// Без постачальників і цін: заявка йде власнику задачами, розділеними по постачальниках.
import { useEffect, useState } from "react";
import { api } from "./api";

const n = (v: any) => { const x = Number(v || 0); return x.toLocaleString("uk-UA", { maximumFractionDigits: 3 }); };

export default function WhReorder() {
  const [d, setD] = useState<any>(null);
  const [lines, setLines] = useState<Record<number, { name: string; unit: string; stock: number; qty: string; note: string }>>({});
  const [q, setQ] = useState("");
  const [found, setFound] = useState<any[]>([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const load = () => api.get<any>("/api/warehouse/reorder/").then((r) => {
    setD(r);
    setLines((cur) => {
      const next = { ...cur };
      (r.low || []).forEach((x: any) => { if (!next[x.id]) next[x.id] = { name: x.name, unit: x.unit, stock: x.stock, qty: String(x.suggest || ""), note: "" }; });
      return next;
    });
  }).catch(() => setD({ low: [], mine: [] }));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (q.trim().length < 2) { setFound([]); return; }
    const h = setTimeout(() => api.get<any>(`/api/warehouse/reorder/?q=${encodeURIComponent(q.trim())}`).then((r) => setFound(r.results || [])).catch(() => setFound([])), 300);
    return () => clearTimeout(h);
  }, [q]);
  const add = (x: any) => { setLines((c) => ({ ...c, [x.id]: c[x.id] || { name: x.name, unit: x.unit, stock: x.stock, qty: "", note: "" } })); setQ(""); setFound([]); };
  const set = (id: number, k: "qty" | "note", v: string) => setLines((c) => ({ ...c, [id]: { ...c[id], [k]: v } }));
  const drop = (id: number) => setLines((c) => { const x = { ...c }; delete x[id]; return x; });
  const ids = Object.keys(lines).map(Number);
  const ready = ids.filter((id) => Number(String(lines[id].qty).replace(",", ".")) > 0);
  const send = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await api.post<any>("/api/warehouse/reorder/", { comment, lines: ready.map((id) => ({ product: id, qty: lines[id].qty, note: lines[id].note })) });
      setMsg(`✓ Заявку №${r.id} надіслано: ${r.lines} поз.`); setLines({}); setComment(""); load();
    } catch (e: any) { setMsg(e?.response?.data?.detail || "Не вдалося надіслати"); }
    setBusy(false);
  };
  if (!d) return <div className="spin">…</div>;
  const low = new Set((d.low || []).map((x: any) => x.id));
  return (
    <div>
      <div className="panel">
        <div className="label" style={{ marginBottom: 4 }}>🛒 Перевірка наявності і дозамовлення</div>
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>
          Червоним — товари, яких менше за мінімальний залишок (підтягуються самі). Додайте інші через пошук, вкажіть скільки треба і надішліть заявку — вона піде відповідальному.
        </div>
        {ids.length === 0 && <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>Усе в наявності. Якщо чогось бракує — знайдіть товар нижче.</div>}
        {ids.length > 0 && <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 560 }}>
            <thead><tr style={{ background: "#f8fafc", textAlign: "left" }}>
              <th style={{ padding: 8 }}>Товар</th><th style={{ padding: 8, textAlign: "right" }}>Залишок</th>
              <th style={{ padding: 8, width: 110 }}>Скільки треба</th><th style={{ padding: 8 }}>Примітка</th><th />
            </tr></thead>
            <tbody>{ids.map((id) => {
              const x = lines[id];
              return (
                <tr key={id} style={{ borderTop: "1px solid #f1f5f9", background: low.has(id) ? "#fef2f2" : undefined }}>
                  <td style={{ padding: 8 }}>{x.name}{low.has(id) && <div style={{ fontSize: 11, color: "#b91c1c" }}>нижче мінімуму</div>}</td>
                  <td style={{ padding: 8, textAlign: "right", whiteSpace: "nowrap" }}>{n(x.stock)} {x.unit}</td>
                  <td style={{ padding: 8 }}><input value={x.qty} onChange={(e) => set(id, "qty", e.target.value)} inputMode="decimal" placeholder={x.unit} style={{ width: "100%", height: 32, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px" }} /></td>
                  <td style={{ padding: 8 }}><input value={x.note} onChange={(e) => set(id, "note", e.target.value)} placeholder="колір, фасування…" style={{ width: "100%", height: 32, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px" }} /></td>
                  <td style={{ padding: 8 }}><button type="button" onClick={() => drop(id)} title="Прибрати" style={{ border: 0, background: "transparent", color: "#94a3b8", cursor: "pointer", fontWeight: 800 }}>✕</button></td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>}
        <div style={{ position: "relative", marginTop: 10 }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="🔎 Знайти товар у номенклатурі (від 2 літер)" style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px" }} />
          {found.length > 0 && <div style={{ position: "absolute", left: 0, right: 0, top: 38, zIndex: 5, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, maxHeight: 260, overflowY: "auto", boxShadow: "0 8px 20px rgba(15,23,42,.12)" }}>
            {found.map((x: any) => (
              <div key={x.id} onClick={() => add(x)} style={{ padding: "8px 10px", cursor: "pointer", borderTop: "1px solid #f1f5f9", fontSize: 13 }}>
                {x.name} <span className="muted">· залишок {n(x.stock)} {x.unit}</span>
              </div>
            ))}
          </div>}
        </div>
        <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} placeholder="Коментар до заявки (необовʼязково)" style={{ width: "100%", marginTop: 8, borderRadius: 8, border: "1px solid #cbd5e1", padding: 8 }} />
        <button className="btn btn-primary" style={{ width: "100%", marginTop: 8 }} disabled={busy || ready.length === 0} onClick={send}>
          {busy ? "Надсилаю…" : `Надіслати заявку (${ready.length} поз.)`}
        </button>
        {msg && <div style={{ marginTop: 8, fontSize: 13, fontWeight: 600, color: msg.startsWith("✓") ? "#15803d" : "#b91c1c" }}>{msg}</div>}
      </div>
      {(d.mine || []).length > 0 && <div className="panel">
        <div className="label" style={{ marginBottom: 6 }}>Мої заявки</div>
        {d.mine.map((r: any) => (
          <div key={r.id} style={{ borderTop: "1px solid #f1f5f9", padding: "6px 0", fontSize: 12.5 }}>
            <b>№{r.id}</b> · {new Date(r.at).toLocaleDateString("uk-UA")} · {r.lines} поз. <span className="muted">— {r.items}</span>
          </div>
        ))}
      </div>}
    </div>
  );
}
