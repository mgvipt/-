/* Списковий вид сделок/лидов (альтернатива канбану). */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { useLang } from "./i18n";
import { useAuth } from "./auth";

export default function ListView({ endpoint, funnel, query, onChanged }: { endpoint: string; funnel: any; query?: string; onChanged?: () => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const nav = useNavigate();
  const { t } = useLang();
  const { can } = useAuth();
  const canDel = endpoint.includes("deals") && can("deal.delete");

  const load = () => {
    setLoading(true);
    api.get<any>(`${endpoint}?funnel=${funnel.id}${query || ""}&page_size=300`)
      .then((d) => setRows(d.results || d))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  };
  useEffect(() => { setSel(new Set()); load(); /* eslint-disable-next-line */ }, [endpoint, funnel.id, query]);
  function toggle(id: number, e: any) { e.stopPropagation(); setSel((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; }); }
  async function bulkDelete() {
    if (!confirm(t("Удалить выбранные сделки","Видалити обрані сделки") + ` (${sel.size})? ` + t("Это навсегда.","Це назавжди."))) return;
    try {
      const r: any = await api.post("/api/deals/bulk-delete/", { ids: Array.from(sel) });
      alert(t("Удалено","Видалено") + `: ${r.deleted}`); setSel(new Set()); load(); onChanged && onChanged();
    } catch (e: any) { alert(e?.response?.data?.detail || t("Нет права «Удалять сделки»","Немає права «Видаляти сделки»")); }
  }

  const path = endpoint.includes("deals") ? "deals" : "leads";
  const stage = (id: number) => funnel.stages.find((s: any) => s.id === id);

  if (loading) return <div className="spin">{t("Загрузка…", "Завантаження…")}</div>;
  return (
    <div className="board fade" style={{ overflowY: "auto" }}>
      {canDel && sel.size > 0 && (
        <div style={{ position: "sticky", top: 0, zIndex: 5, background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "7px 12px", margin: "0 0 8px", display: "flex", gap: 10, alignItems: "center" }}>
          <b style={{ fontSize: 13 }}>{t("Выбрано","Вибрано")}: {sel.size}</b>
          <button className="btn" style={{ background: "#dc2626", color: "#fff", padding: "4px 14px" }} onClick={bulkDelete}>🗑 {t("Удалить выбранные","Видалити обрані")}</button>
          <button className="btn btn-light" style={{ padding: "4px 10px" }} onClick={() => setSel(new Set())}>{t("Снять выбор","Зняти вибір")}</button>
        </div>
      )}
      <table className="listtbl">
        <thead><tr>
          {canDel && <th style={{ width: 30 }}><input type="checkbox" checked={rows.length > 0 && sel.size === rows.length} onChange={() => setSel(sel.size === rows.length ? new Set() : new Set(rows.map((r) => r.id)))} /></th>}
          <th>#</th><th>{t("Название", "Назва")}</th><th>{t("Клиент", "Клієнт")}</th>
          <th>{t("Стадия", "Стадія")}</th><th style={{ textAlign: "right" }}>{t("Сумма", "Сума")}</th>
          <th>{t("Ответственный", "Відповідальний")}</th><th>{t("Создано", "Створено")}</th>
        </tr></thead>
        <tbody>
          {rows.map((r) => {
            const st = stage(r.stage);
            return (
              <tr key={r.id} onClick={() => nav(`/${path}/${r.id}`)} style={{ cursor: "pointer", background: sel.has(r.id) ? "#fef2f2" : undefined }}>
                {canDel && <td onClick={(e) => toggle(r.id, e)} style={{ textAlign: "center" }}><input type="checkbox" readOnly checked={sel.has(r.id)} style={{ pointerEvents: "none" }} /></td>}
                <td className="muted">#{r.id}</td>
                <td><b>{r.title}</b></td>
                <td>{r.contact_name || "—"}</td>
                <td>{st && <span className="chip" style={{ background: st.color }}>{st.name}</span>}</td>
                <td style={{ textAlign: "right" }}>{Number(r.amount || 0).toLocaleString("uk-UA")} ₴</td>
                <td>{r.owner_name || "—"}</td>
                <td className="muted">{r.created_at ? new Date(r.created_at).toLocaleDateString("uk-UA") : "—"}</td>
              </tr>
            );
          })}
          {rows.length === 0 && <tr><td colSpan={canDel ? 8 : 7} className="muted" style={{ padding: 20, textAlign: "center" }}>{t("Пусто", "Порожньо")}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
