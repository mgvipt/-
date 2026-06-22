import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Paginated } from "../api";
import { SourceChip } from "../ui";

interface Contact {
  id: number; display_name: string; phone: string; email: string; channels: string[];
  source?: string; loyalty_tag?: string; owner_name?: string; created_at?: string;
}

const LOY_COLOR: Record<string, string> = { VIP: "#7c3aed", Активный: "#16a34a", Новый: "#2563eb", Спящий: "#d97706" };

export default function Clients() {
  const nav = useNavigate();
  const [rows, setRows] = useState<Contact[]>([]);
  const [count, setCount] = useState(0);
  const [q, setQ] = useState("");
  const [loy, setLoy] = useState("");
  const [src, setSrc] = useState("");
  const [withPhone, setWithPhone] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [ordering, setOrdering] = useState("-created_at");

  function load(p = page) {
    const qp = new URLSearchParams({ page: String(p), page_size: String(pageSize), ordering });
    if (q.trim()) qp.set("search", q.trim());
    if (loy) qp.set("loyalty_tag", loy);
    if (src) qp.set("source", src);
    api.get<Paginated<Contact>>(`/api/contacts/?${qp.toString()}`).then((d) => {
      let r = d.results;
      if (withPhone) r = r.filter((c) => c.phone);
      setRows(r); setCount(d.count ?? r.length);
    });
  }
  useEffect(() => { load(1); setPage(1); /* eslint-disable-next-line */ }, [pageSize, loy, src, ordering, withPhone]);
  const totalPages = Math.max(1, Math.ceil(count / pageSize));
  function apply() { setPage(1); load(1); }
  function go(p: number) { setPage(p); load(p); }

  return (
    <div className="scroll pad fade">
      {/* фільтри */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10, background: "#fff", padding: 10, borderRadius: 8, border: "1px solid #e2e8f0" }}>
        <input placeholder="🔍 Імʼя / телефон / email" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && apply()} style={{ flex: "1 1 220px", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 10px" }} />
        <select value={loy} onChange={(e) => setLoy(e.target.value)} style={{ height: 34, border: "1px solid #cbd5e1", borderRadius: 7 }}>
          <option value="">Лояльність: усі</option>{["VIP", "Активный", "Новый", "Спящий"].map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <input placeholder="Джерело" value={src} onChange={(e) => setSrc(e.target.value)} onKeyDown={(e) => e.key === "Enter" && apply()} style={{ width: 130, height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }} />
        <select value={ordering} onChange={(e) => setOrdering(e.target.value)} style={{ height: 34, border: "1px solid #cbd5e1", borderRadius: 7 }}>
          <option value="-created_at">Спершу нові</option><option value="created_at">Спершу старі</option><option value="first_name">За імʼям А-Я</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13 }}><input type="checkbox" checked={withPhone} onChange={(e) => setWithPhone(e.target.checked)} />лише з телефоном</label>
        <button className="btn btn-primary" onClick={apply}>Знайти</button>
      </div>
      {/* пагінація */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, fontSize: 13 }}>
        <span className="muted">Всього клієнтів: <b>{count.toLocaleString("ru")}</b></span>
        <div style={{ flex: 1 }} />
        <span className="muted">На стор.:</span>
        <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6 }}>{[20, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}</select>
        <button className="btn btn-light" disabled={page <= 1} onClick={() => go(page - 1)}>←</button>
        <span>стор. <b>{page}</b> з {totalPages}</span>
        <button className="btn btn-light" disabled={page >= totalPages} onClick={() => go(page + 1)}>→</button>
      </div>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Імʼя</th><th>Телефон</th><th>Email</th><th>Джерело</th><th>Лояльність</th><th>Відповідальний</th><th>Створено</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 14 }}>Нічого не знайдено.</td></tr>}
            {rows.map((c) => (
              <tr key={c.id} onClick={() => nav(`/clients/${c.id}`)} style={{ cursor: "pointer" }}>
                <td style={{ fontWeight: 500, color: "#1d4ed8" }}>{c.display_name}</td>
                <td className="muted">{c.phone || "—"}</td>
                <td className="muted">{c.email || "—"}</td>
                <td>{c.source ? <SourceChip source={c.source} /> : <span className="muted">—</span>}</td>
                <td>{c.loyalty_tag ? <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: (LOY_COLOR[c.loyalty_tag] || "#64748b") + "22", color: LOY_COLOR[c.loyalty_tag] || "#64748b" }}>{c.loyalty_tag}</span> : <span className="muted">—</span>}</td>
                <td className="muted">{c.owner_name || "—"}</td>
                <td className="muted">{c.created_at ? new Date(c.created_at).toLocaleDateString("ru") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
