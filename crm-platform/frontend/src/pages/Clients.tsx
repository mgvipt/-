import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Paginated } from "../api";
import { SourceChip } from "../ui";
import { useLang } from "../i18n";

interface Contact {
  id: number; display_name: string; phone: string; email: string; channels: string[];
  source?: string; loyalty_tag?: string; owner_name?: string; created_at?: string;
}

const LOY_COLOR: Record<string, string> = { VIP: "#7c3aed", Активний: "#16a34a", Новий: "#2563eb", Сплячий: "#d97706", Активный: "#16a34a", Новый: "#2563eb", Спящий: "#d97706" };

export default function Clients() {
  const { t } = useLang();
  const nav = useNavigate();
  const [rows, setRows] = useState<Contact[]>([]);
  const [count, setCount] = useState(0);
  const [q, setQ] = useState("");
  const [loys, setLoys] = useState<string[]>([]);
  const [src, setSrc] = useState("");
  const [withPhone, setWithPhone] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [ordering, setOrdering] = useState("-created_at");

  function load(p = page) {
    const qp = new URLSearchParams({ page: String(p), page_size: String(pageSize), ordering });
    if (q.trim()) qp.set("search", q.trim());
    if (loys.length) qp.set("loyalty_in", loys.join(","));
    if (withPhone) qp.set("has_phone", "1");
    if (src) qp.set("source", src);
    api.get<Paginated<Contact>>(`/api/contacts/?${qp.toString()}`).then((d) => {
      setRows(d.results); setCount(d.count ?? d.results.length);
    });
  }
  useEffect(() => { load(1); setPage(1); /* eslint-disable-next-line */ }, [pageSize, loys, src, ordering, withPhone]);
  const totalPages = Math.max(1, Math.ceil(count / pageSize));
  function apply() { setPage(1); load(1); }
  function go(p: number) { setPage(p); load(p); }

  return (
    <div className="scroll pad fade">
      {/* фільтри */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10, background: "#fff", padding: 10, borderRadius: 8, border: "1px solid #e2e8f0" }}>
        <input placeholder={t("🔍 Имя / телефон / email","🔍 Імʼя / телефон / email")} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && apply()} style={{ flex: "1 1 220px", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 10px" }} />
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 12 }}>{t("Статус","Статус")}:</span>
          {["VIP", "Активний", "Новий", "Сплячий"].map((x) => {
            const on = loys.includes(x);
            return <span key={x} onClick={() => setLoys((c) => on ? c.filter((y) => y !== x) : [...c, x])} style={{ cursor: "pointer", fontSize: 12, fontWeight: 600, padding: "5px 10px", borderRadius: 14, border: "1px solid " + (on ? "#2563eb" : "#cbd5e1"), background: on ? "#2563eb" : "#fff", color: on ? "#fff" : "#475569" }}>{x}</span>;
          })}
        </div>
        <input placeholder={t("Источник","Джерело")} value={src} onChange={(e) => setSrc(e.target.value)} onKeyDown={(e) => e.key === "Enter" && apply()} style={{ width: 130, height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }} />
        <select value={ordering} onChange={(e) => setOrdering(e.target.value)} style={{ height: 34, border: "1px solid #cbd5e1", borderRadius: 7 }}>
          <option value="-created_at">{t("Сначала новые","Спершу нові")}</option><option value="created_at">{t("Сначала старые","Спершу старі")}</option><option value="first_name">{t("По имени А-Я","За імʼям А-Я")}</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13 }}><input type="checkbox" checked={withPhone} onChange={(e) => setWithPhone(e.target.checked)} />{t("только с телефоном","лише з телефоном")}</label>
        <button className="btn btn-primary" onClick={apply}>{t("Найти","Знайти")}</button>
      </div>
      {/* пагінація */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, fontSize: 13 }}>
        <span className="muted">{t("Всего клиентов","Всього клієнтів")}: <b>{count.toLocaleString("ru")}</b></span>
        <div style={{ flex: 1 }} />
        <span className="muted">{t("На стр.","На стор.")}:</span>
        <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6 }}>{[20, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}</select>
        <button className="btn btn-light" disabled={page <= 1} onClick={() => go(page - 1)}>←</button>
        <span>{t("стр.","стор.")} <b>{page}</b> {t("из","з")} {totalPages}</span>
        <button className="btn btn-light" disabled={page >= totalPages} onClick={() => go(page + 1)}>→</button>
      </div>
      <div className="tablewrap">
        <table>
          <thead><tr><th>{t("Имя","Імʼя")}</th><th>{t("Телефон","Телефон")}</th><th>{t("Email","Email")}</th><th>{t("Источник","Джерело")}</th><th>{t("Лояльность","Лояльність")}</th><th>{t("Ответственный","Відповідальний")}</th><th>{t("Создано","Створено")}</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 14 }}>{t("Ничего не найдено.","Нічого не знайдено.")}</td></tr>}
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
