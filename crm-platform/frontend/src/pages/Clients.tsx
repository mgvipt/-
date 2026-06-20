import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Paginated } from "../api";
import { SourceChip } from "../ui";

interface Contact { id: number; display_name: string; phone: string; email: string; channels: string[]; }

export default function Clients() {
  const nav = useNavigate();
  const [rows, setRows] = useState<Contact[]>([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.get<Paginated<Contact>>(`/api/contacts/?page_size=200&search=${encodeURIComponent(q)}`)
      .then((d) => setRows(d.results));
  }, [q]);

  return (
    <div className="scroll pad fade">
      <div className="toolbar" style={{ borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 12, background: "#fff" }}>
        <input placeholder="Поиск по имени/телефону" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 280 }} />
        <div className="spacer" />
        <span className="muted">Всего: {rows.length}</span>
      </div>
      <div className="tablewrap">
        <table>
          <thead><tr><th>Имя</th><th>Телефон</th><th>Email</th><th>Каналы</th></tr></thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} onClick={() => nav(`/clients/${c.id}`)} style={{ cursor: "pointer" }}>
                <td style={{ fontWeight: 500, color: "#1d4ed8" }}>{c.display_name}</td>
                <td className="muted">{c.phone || "—"}</td>
                <td className="muted">{c.email || "—"}</td>
                <td><div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>{(c.channels || []).map((ch) => <SourceChip key={ch} source={ch} />)}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
