/* Пошук дублів: контакти (телефон/email/мессенджер/імʼя) + ліди/сделки (один контакт — кілька).
   Контакти можна обʼєднати в один (перепривʼязка лідів/сделок/чатів + дозаповнення полів). */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

type Item = { id: number; name: string; phone?: string; email?: string; social?: string; stage?: string; owner?: string; amount?: string };
type Group = { reason: string; by: string; key: string; count: number; items: Item[] };

const REASON_ICON: Record<string, string> = { phone: "phone", email: "mail", social: "link", name: "user", contact: "user" };
const REASON_LABEL: Record<string, [string, string]> = { phone: ["Телефон", "Телефон"], email: ["Email", "Email"], social: ["Мессенджер/ник", "Мессенджер/нік"], name: ["Имя", "Імʼя"], contact: ["Один контакт — несколько", "Один контакт — декілька"] };

export default function Duplicates() {
  const { t } = useLang();
  const [tab, setTab] = useState<"contacts" | "leads" | "deals">("contacts");
  const [data, setData] = useState<{ total: number; groups: Group[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [keep, setKeep] = useState<Record<number, number>>({}); // groupIdx -> contactId
  const [busy, setBusy] = useState<number | null>(null);
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);

  const load = () => {
    setLoading(true); setData(null); setPage(1);
    api.get<any>(`/api/duplicates/?type=${tab}`).then((d) => setData(d)).catch(() => setData({ total: 0, groups: [] })).finally(() => setLoading(false));
  };
  useEffect(load, [tab]);

  const merge = async (gi: number, g: Group) => {
    const keepId = keep[gi] ?? g.items[0].id;
    const ids = g.items.map((i) => i.id);
    if (!confirm(t(`Объединить ${ids.length} контакта в одного? Лиды, сделки и чаты перейдут на выбранного, остальные удалятся.`,
      `Обʼєднати ${ids.length} контакти в один? Ліди, сделки і чати перейдуть на обраного, решта видаляться.`))) return;
    setBusy(gi);
    try {
      await api.post("/api/duplicates/", { keep: keepId, ids });
      load();
    } catch { alert(t("Не удалось объединить", "Не вдалося обʼєднати")); }
    finally { setBusy(null); }
  };

  const tabs: [typeof tab, string, string][] = [
    ["contacts", "Клиенты", "Клієнти"], ["leads", "Лиды", "Ліди"], ["deals", "Сделки", "Сделки"],
  ];

  return (
    <div className="scroll pad fade">
      <h2 style={{ margin: "0 0 4px", fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}>
        <Icon n="copy" size={20} /> {t("Поиск дублей", "Пошук дублів")}
      </h2>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
        {t("Совпадения по телефону, email, мессенджеру и имени. Контакты можно объединить в один.",
          "Збіги за телефоном, email, мессенджером та імʼям. Контакти можна обʼєднати в один.")}
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {tabs.map(([k, ru, uk]) => (
          <button key={k} className={"btn" + (tab === k ? " btn-primary" : " btn-light")} onClick={() => setTab(k)}>{t(ru, uk)}</button>
        ))}
        <button className="btn btn-light" onClick={load} title={t("Обновить", "Оновити")}><Icon n="refresh" size={15} /></button>
      </div>

      {loading && <div className="spin">{t("Ищем дубли…", "Шукаємо дублі…")}</div>}
      {data && !loading && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: 13 }}>{t(`Найдено групп: ${data.total}`, `Знайдено груп: ${data.total}`)}{data.groups.length < data.total ? t(` (первые ${data.groups.length})`, ` (перші ${data.groups.length})`) : ""}</span>
            <div style={{ flex: 1 }} />
            {data.groups.length > pageSize && (() => { const pages = Math.max(1, Math.ceil(data.groups.length / pageSize)); return (<>
              <button className="btn btn-light" style={{ fontSize: 12, padding: "3px 9px" }} disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>←</button>
              <span style={{ fontSize: 12.5, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{page} / {pages}</span>
              <button className="btn btn-light" style={{ fontSize: 12, padding: "3px 9px" }} disabled={page >= pages} onClick={() => setPage((p) => Math.min(pages, p + 1))}>→</button>
            </>); })()}
            <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ height: 28, borderRadius: 7, border: "1px solid #cbd5e1", fontSize: 12.5, padding: "0 6px" }}>
              {[5, 20, 50, 100].map((n) => <option key={n} value={n}>{t(`по ${n}`, `по ${n}`)}</option>)}
            </select>
          </div>
          {data.total === 0 && <div className="note" style={{ display: "flex", gap: 8, alignItems: "center" }}><Icon n="check" size={16} /> {t("Дублей не найдено — чисто!", "Дублів не знайдено — чисто!")}</div>}

          {data.groups.slice((page - 1) * pageSize, page * pageSize).map((g, j) => {
            const gi = (page - 1) * pageSize + j;
            const keepId = keep[gi] ?? g.items[0].id;
            return (
              <div key={gi} className="panel" style={{ marginBottom: 12, padding: 0, overflow: "hidden" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 14px", background: "#f8fafc", borderBottom: "1px solid #eef2f7" }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 700, color: "#475569" }}>
                    <Icon n={REASON_ICON[g.by] || "copy"} size={14} /> {t(...(REASON_LABEL[g.by] || [g.reason, g.reason]))}
                  </span>
                  {g.key && <span className="muted" style={{ fontSize: 12 }}>· {g.key}</span>}
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#fff", background: "#ef4444", borderRadius: 20, padding: "1px 9px" }}>{g.count}</span>
                  <div style={{ flex: 1 }} />
                  {tab === "contacts" && (
                    <button className="btn btn-primary" style={{ fontSize: 12 }} disabled={busy === gi} onClick={() => merge(gi, g)}>
                      <Icon n="check" size={14} /> {busy === gi ? "…" : t("Объединить", "Обʼєднати")}
                    </button>
                  )}
                </div>
                <div style={{ maxHeight: 320, overflowY: "auto" }}>
                  {g.items.map((it) => {
                    const href = tab === "contacts" ? `/clients/${it.id}` : tab === "leads" ? `/leads/${it.id}` : `/deals/${it.id}`;
                    const isKeep = tab === "contacts" && it.id === keepId;
                    return (
                      <div key={it.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px", borderBottom: "1px solid #f5f7fa", background: isKeep ? "#ecfdf5" : "" }}>
                        {tab === "contacts" && (
                          <button onClick={() => setKeep((k) => ({ ...k, [gi]: it.id }))} title={t("Оставить этого (в него объединить)", "Залишити цього (в нього обʼєднати)")}
                            style={{ flexShrink: 0, width: 18, height: 18, borderRadius: "50%", border: isKeep ? "none" : "2px solid #cbd5e1", background: isKeep ? "#16a34a" : "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", padding: 0 }}>
                            {isKeep && <Icon n="check" size={12} style={{ color: "#fff" }} />}
                          </button>
                        )}
                        <Link to={href} style={{ flex: 1, minWidth: 0, textDecoration: "none", color: "inherit", display: "flex", flexDirection: "column" }}>
                          <span style={{ fontSize: 13.5, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {it.name} <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>#{it.id}</span>
                            {isKeep && <span style={{ marginLeft: 6, fontSize: 10.5, fontWeight: 700, color: "#16a34a" }}>{t("ОСТАВИТЬ", "ЗАЛИШИТИ")}</span>}
                          </span>
                          <span className="muted" style={{ fontSize: 11.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {tab === "contacts"
                              ? [it.phone, it.email, it.social].filter(Boolean).join(" · ") || "—"
                              : [it.stage, it.owner, it.amount && it.amount !== "0" ? it.amount + " ₴" : ""].filter(Boolean).join(" · ")}
                          </span>
                        </Link>
                        <Link to={href} className="btn btn-light" style={{ fontSize: 11, flexShrink: 0 }}>{t("Открыть", "Відкрити")}</Link>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
