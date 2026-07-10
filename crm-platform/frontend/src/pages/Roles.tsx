import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

interface Role { id: number; name: string; permissions: string[]; funnels: number[]; open_lines: number[]; }
interface Chan { id: number; name: string; kind: string; }
interface Cat { code: string; label: string; }

// Матрица ролей: галочки выдают права. Изменения сразу сохраняются в API.
export default function Roles() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [cat, setCat] = useState<Cat[]>([]);
  const [chans, setChans] = useState<Chan[]>([]);
  const [pgroups, setPgroups] = useState<any[]>([]);
  const { t } = useLang();

  useEffect(() => {
    api.get<{ results: Role[] }>("/api/roles/").then((d) => setRoles(d.results));
    api.get<any>("/api/me/").then((m) => setCat(m.permission_catalog));
    api.get<any>("/api/channels/").then((d) => setChans(d.results || d || []));
    api.get<any>("/api/permissions/").then((dd) => setPgroups(dd.groups || [])).catch(() => {});
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

  const blocks: { group: string; items: Cat[] }[] = pgroups.length
    ? pgroups.map((g: any) => ({ group: g.group, items: g.items }))
    : [{ group: "", items: cat }];
  const flatCols: any[] = blocks.flatMap((g) => g.items.map((it: any, i: number) => ({ ...it, first: i === 0 })));
  const blockLine = "2px solid color-mix(in srgb, var(--brand) 55%, transparent)";
  return (
    <div className="scroll">
      <div className="note">
        {t("Роли динамические: галочка выдаёт право. «Свои лиды» — сотрудник видит только свои; «Все лиды» — руководитель видит отдел. Доступ к воронкам и линиям настраивается в карточке роли.","Ролі динамічні: галочка видає право. «Свої ліди» — співробітник бачить лише свої; «Всі ліди» — керівник бачить відділ. Доступ до воронок і ліній налаштовується в картці ролі.")}
      </div>
      <div className="pad" style={{ paddingTop: 0 }}>
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th rowSpan={2} style={{ verticalAlign: "bottom" }}>{t("Роль","Роль")}</th>
                {blocks.map((g, gi) => <th key={g.group || gi} colSpan={g.items.length}
                  style={{ textAlign: "center", fontSize: 11, fontWeight: 800, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--brand)", borderLeft: blockLine, background: "color-mix(in srgb, var(--brand) 9%, transparent)", padding: "6px 4px" }}>{g.group}</th>)}
              </tr>
              <tr>
                {flatCols.map((c) => <th key={c.code} style={{ textAlign: "center", fontSize: 10, borderLeft: c.first ? blockLine : undefined }}>{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {roles.map((r) => (
                <tr key={r.id}>
                  <td style={{ fontWeight: 500 }}>{r.name}</td>
                  {flatCols.map((c) => (
                    <td key={c.code} style={{ textAlign: "center", borderLeft: c.first ? blockLine : undefined }}>
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
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4, display: "flex", alignItems: "center", gap: 6 }}><Icon n="📣" size={16} /> {t("Доступ к мессенджерам","Доступ до месенджерів")}</div>
          <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Выберите, какие каналы видит роль. Если ничего не выбрано — роль видит все каналы.","Оберіть, які канали бачить роль. Якщо нічого не обрано — роль бачить усі канали.")}</div>
          {roles.map((r) => (
            <div key={r.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderTop: "1px solid #f1f5f9" }}>
              <div style={{ width: 170, fontWeight: 500, fontSize: 13 }}>{r.name}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, flex: 1 }}>
                {chans.length === 0 && <span className="muted" style={{ fontSize: 12 }}>{t("Каналов ещё нет","Каналів ще немає")}</span>}
                {chans.map((ch) => {
                  const on = (r.open_lines || []).includes(ch.id);
                  return (
                    <span key={ch.id} onClick={() => toggleChannel(r, ch.id)}
                      style={{ cursor: "pointer", fontSize: 12, padding: "4px 11px", borderRadius: 14, border: "1px solid " + (on ? "var(--brand)" : "#e2e8f0"), background: on ? "var(--brand)" : "#fff", color: on ? "#fff" : "#475569" }}>
                      {ch.name}
                    </span>
                  );
                })}
                {(r.open_lines || []).length === 0 && chans.length > 0 && <span className="muted" style={{ fontSize: 11, alignSelf: "center" }}>{t("← все каналы","← усі канали")}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
