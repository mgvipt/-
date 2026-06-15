import { useEffect, useState } from "react";
import { api } from "../api";

interface Role { id: number; name: string; permissions: string[]; funnels: number[]; }
interface Cat { code: string; label: string; }

// Матрица ролей: галочки выдают права. Изменения сразу сохраняются в API.
export default function Roles() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [cat, setCat] = useState<Cat[]>([]);

  useEffect(() => {
    api.get<{ results: Role[] }>("/api/roles/").then((d) => setRoles(d.results));
    api.get<any>("/api/me/").then((m) => setCat(m.permission_catalog));
  }, []);

  async function toggle(role: Role, code: string) {
    const has = role.permissions.includes(code);
    const permissions = has ? role.permissions.filter((p) => p !== code) : [...role.permissions, code];
    setRoles((rs) => rs.map((r) => (r.id === role.id ? { ...r, permissions } : r)));
    await api.patch(`/api/roles/${role.id}/`, { permissions });
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
      </div>
    </div>
  );
}
