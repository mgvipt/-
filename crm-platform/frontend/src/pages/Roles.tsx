import { useEffect, useState } from "react";
import { api } from "../api";

interface Role { id: number; name: string; permissions: string[]; funnels: number[]; open_lines: number[]; }
interface Chan { id: number; name: string; kind: string; }
interface Cat { code: string; label: string; }

// Матрица ролей: галочки выдают права. Изменения сразу сохраняются в API.
export default function Roles() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [cat, setCat] = useState<Cat[]>([]);
  const [chans, setChans] = useState<Chan[]>([]);

  useEffect(() => {
    api.get<{ results: Role[] }>("/api/roles/").then((d) => setRoles(d.results));
    api.get<any>("/api/me/").then((m) => setCat(m.permission_catalog));
    api.get<any>("/api/channels/").then((d) => setChans(d.results || d || []));
  }, []);

  async function toggle(role: Role, code: string) {
    const has = role.permissions.includes(code);
    const permissions = has ? role.permissions.filter((p) => p !== code) : [...role.permissions, code];
    setRoles((rs) => rs.map((r) => (r.id === role.id ? { ...r, permissions } : r)));
    await api.patch(`/api/roles/${role.id}/`, { permissions });
  }

  async function toggleChannel(role: Role, cid: number) {
    const cur = role.open_lines || [];
    const open_lines = cur.includes(cid) ? cur.filter((x) => x !== cid) : [...cur, cid];
    setRoles((rs) => rs.map((r) => (r.id === role.id ? { ...r, open_lines } : r)));
    await api.patch(`/api/roles/${role.id}/`, { open_lines });
  }

  return (
    <div className="scroll">
      <div className="note">
        Роли динамические: галочка выдаёт право. «Свои лиды» — сотрудник видит только свои; «Все лиды» — руководитель видит отдел.
        Доступ к воронкам и линиям настраивается в карточке роли.
      </div>
      <div className="pad" style={{ paddingTop: 0 }}>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Роль</th>
                {cat.map((c) => <th key={c.code} style={{ textAlign: "center", fontSize: 10 }}>{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {roles.map((r) => (
                <tr key={r.id}>
                  <td style={{ fontWeight: 500 }}>{r.name}</td>
                  {cat.map((c) => (
                    <td key={c.code} style={{ textAlign: "center" }}>
                      <span className={"toggle" + (r.permissions.includes(c.code) ? " on" : "")}
                        onClick={() => toggle(r, c.code)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ── Доступ до месенджерів (каналів) по ролях ── */}
        <div className="tablewrap" style={{ marginTop: 18, padding: 14 }}>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>📣 Доступ до месенджерів</div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>Оберіть, які канали бачить роль. Якщо нічого не обрано — роль бачить <b>усі</b> канали.</div>
          {roles.map((r) => (
            <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderTop: "1px solid #f1f5f9" }}>
              <div style={{ width: 170, fontWeight: 500, fontSize: 13 }}>{r.name}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, flex: 1 }}>
                {chans.length === 0 && <span className="muted" style={{ fontSize: 12 }}>Каналів ще немає</span>}
                {chans.map((ch) => {
                  const on = (r.open_lines || []).includes(ch.id);
                  return (
                    <span key={ch.id} onClick={() => toggleChannel(r, ch.id)}
                      style={{ cursor: "pointer", fontSize: 12, padding: "4px 11px", borderRadius: 14, border: "1px solid " + (on ? "var(--brand)" : "#e2e8f0"), background: on ? "var(--brand)" : "#fff", color: on ? "#fff" : "#475569" }}>
                      {ch.name}
                    </span>
                  );
                })}
                {(r.open_lines || []).length === 0 && chans.length > 0 && <span className="muted" style={{ fontSize: 11, alignSelf: "center" }}>← усі канали</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
