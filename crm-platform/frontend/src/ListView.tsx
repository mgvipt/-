/* Списковий вид сделок/лидов (альтернатива канбану). */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { useLang } from "./i18n";

export default function ListView({ endpoint, funnel, query }: { endpoint: string; funnel: any; query?: string }) {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();
  const { t } = useLang();

  useEffect(() => {
    setLoading(true);
    api.get<any>(`${endpoint}?funnel=${funnel.id}${query || ""}&page_size=300`)
      .then((d) => setRows(d.results || d))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [endpoint, funnel.id, query]);

  const path = endpoint.includes("deals") ? "deals" : "leads";
  const stage = (id: number) => funnel.stages.find((s: any) => s.id === id);

  if (loading) return <div className="spin">{t("Загрузка…", "Завантаження…")}</div>;
  return (
    <div className="board fade" style={{ overflowY: "auto" }}>
      <table className="listtbl">
        <thead><tr>
          <th>#</th><th>{t("Название", "Назва")}</th><th>{t("Клиент", "Клієнт")}</th>
          <th>{t("Стадия", "Стадія")}</th><th style={{ textAlign: "right" }}>{t("Сумма", "Сума")}</th>
          <th>{t("Ответственный", "Відповідальний")}</th><th>{t("Создано", "Створено")}</th>
        </tr></thead>
        <tbody>
          {rows.map((r) => {
            const st = stage(r.stage);
            return (
              <tr key={r.id} onClick={() => nav(`/${path}/${r.id}`)} style={{ cursor: "pointer" }}>
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
          {rows.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 20, textAlign: "center" }}>{t("Пусто", "Порожньо")}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
