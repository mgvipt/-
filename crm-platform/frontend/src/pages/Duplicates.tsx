/* Пошук дублів: контакти (телефон/email/мессенджер/імʼя) + ліди/сделки (один контакт — кілька).
   Контакти можна обʼєднати в один (перепривʼязка лідів/сделок/чатів + дозаповнення полів). */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createPortal } from "react-dom";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

type Item = { id: number; name: string; phone?: string; email?: string; social?: string; stage?: string; owner?: string; amount?: string };
type Group = { reason: string; by: string; key: string; count: number; items: Item[] };

const REASON_ICON: Record<string, string> = { phone: "phone", email: "mail", social: "link", name: "user", contact: "user" };
const REASON_LABEL: Record<string, [string, string]> = { phone: ["Телефон", "Телефон"], email: ["Email", "Email"], social: ["Мессенджер/ник", "Мессенджер/нік"], name: ["Имя", "Імʼя"], contact: ["Один контакт — несколько", "Один контакт — декілька"] };

// поля, які можна перенести при обʼєднанні (ключ, RU, UA)
function msgLabel(v: string): string {
  const l = (v || "").toLowerCase();
  if (l.includes("instagram")) return "Instagram";
  if (l.includes("t.me") || l.includes("telegram") || l.startsWith("tg://")) return "Telegram";
  if (l.includes("viber")) return "Viber";
  if (l.includes("facebook") || l.includes("fb.") || l.includes("m.me")) return "Facebook";
  if (l.includes("tiktok")) return "TikTok";
  if (/^\+?\d[\d\s()-]{6,}$/.test(v.trim())) return "Телефон/Viber";
  return "Мессенджер";
}

const MFIELDS: [string, string, string][] = [
  ["first_name", "Имя", "Імʼя"], ["last_name", "Фамилия", "Прізвище"], ["middle_name", "Отчество", "По батькові"],
  ["nickname", "Ник (мессенджер)", "Нік (месенджер)"], ["phone", "Телефон", "Телефон"], ["email", "Email", "Email"],
  ["address", "Адрес", "Адреса"],
  ["birthday", "Дата рождения", "Дата народження"], ["source", "Источник", "Джерело"],
  ["edrpou", "ЄДРПОУ/ИНН", "ЄДРПОУ/ІПН"], ["iban", "IBAN", "IBAN"], ["comment", "Комментарий", "Коментар"],
];

export default function Duplicates() {
  const { t } = useLang();
  const [tab, setTab] = useState<"contacts" | "leads" | "deals">("contacts");
  const [data, setData] = useState<{ total: number; groups: Group[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [keep, setKeep] = useState<Record<number, number>>({}); // groupIdx -> contactId
  const [busy, setBusy] = useState<number | null>(null);
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);
  const [mm, setMm] = useState<null | { ids: number[]; keepId: number; contacts: any[]; choice: Record<string, number>; msgSel: Record<string, boolean> }>(null);
  const [mmBusy, setMmBusy] = useState(false);

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

  const openMerge = async (gi: number, g: Group) => {
    const ids = g.items.map((i) => i.id);
    const preKeep = keep[gi] ?? ids[0];
    setMm({ ids, keepId: preKeep, contacts: [], choice: {}, msgSel: {} });
    try {
      const full = await Promise.all(ids.map((id) => api.get<any>(`/api/contacts/${id}/`)));
      const choice: Record<string, number> = {};
      MFIELDS.forEach(([f]) => {
        const withVal = full.filter((c: any) => (c[f] ?? "") !== "");
        choice[f] = (withVal.find((c: any) => c.id === preKeep) || withVal[0] || full[0])?.id;
      });
      const msgSel: Record<string, boolean> = {};
      full.forEach((c: any) => { [c.social_link, ...(c.messengers || [])].forEach((m: string) => { if (m && m.trim()) msgSel[m.trim()] = true; }); });
      setMm({ ids, keepId: preKeep, contacts: full, choice, msgSel });
    } catch { alert(t("Не удалось загрузить контакты", "Не вдалося завантажити контакти")); setMm(null); }
  };

  const doMerge = async () => {
    if (!mm) return;
    const { ids, keepId, contacts, choice } = mm;
    const fields: Record<string, any> = {};
    MFIELDS.forEach(([f]) => { const c = contacts.find((x: any) => x.id === choice[f]); fields[f] = c ? (c[f] ?? "") : ""; });
    const messengers = Object.keys(mm.msgSel).filter((m) => mm.msgSel[m]);
    setMmBusy(true);
    try { await api.post("/api/duplicates/", { keep: keepId, ids, fields, messengers }); setMm(null); load(); }
    catch { alert(t("Не удалось объединить", "Не вдалося обʼєднати")); }
    finally { setMmBusy(false); }
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
                    <button className="btn btn-primary" style={{ fontSize: 12 }} disabled={busy === gi} onClick={() => openMerge(gi, g)}>
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
      {mm && createPortal(
        <div onClick={() => !mmBusy && setMm(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 2147483000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: 920, maxWidth: "97vw", maxHeight: "90vh", overflow: "auto", background: "#fff", borderRadius: 14, boxShadow: "0 24px 70px rgba(0,0,0,.35)", padding: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
              <h3 style={{ margin: 0, fontSize: 17 }}>{t("Объединение контактов", "Обʼєднання контактів")}</h3>
              <div style={{ flex: 1 }} />
              <button className="btn btn-light" onClick={() => !mmBusy && setMm(null)}>✕</button>
            </div>
            <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>{t("Выбери контакт, который ОСТАНЕТСЯ (получит все сделки/лиды/чаты), и галочками — какие данные перенести в него.", "Обери контакт, що ЗАЛИШИТЬСЯ (отримає всі сделки/ліди/чати), і галочками — які дані перенести в нього.")}</div>
            {mm.contacts.length === 0 ? <div style={{ padding: 30, textAlign: "center" }} className="muted">…</div> : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
                  <thead><tr>
                    <th style={{ textAlign: "left", padding: "6px 8px", color: "#64748b", fontSize: 11, borderBottom: "2px solid #e2e8f0" }}>{t("Поле", "Поле")}</th>
                    {mm.contacts.map((c: any) => { const isK = mm.keepId === c.id; return (
                      <th key={c.id} style={{ textAlign: "left", padding: "6px 8px", borderBottom: "2px solid #e2e8f0", background: isK ? "#ecfdf5" : "", minWidth: 190 }}>
                        <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                          <input type="radio" name="keepc" checked={isK} onChange={() => setMm({ ...mm, keepId: c.id })} />
                          <span style={{ fontWeight: 700 }}>{c.display_name || ((c.first_name || "") + " " + (c.last_name || "")).trim() || ("#" + c.id)}</span>
                          <span className="muted" style={{ fontWeight: 400, fontSize: 10.5 }}>#{c.id}</span>
                          {isK && <span style={{ fontSize: 10, fontWeight: 800, color: "#16a34a" }}>{t("ОСТАВИТЬ", "ЗАЛИШИТИ")}</span>}
                        </label>
                      </th>); })}
                  </tr></thead>
                  <tbody>
                    {MFIELDS.map(([f, ru, ua]) => {
                      if (!mm.contacts.some((c: any) => (c[f] ?? "") !== "")) return null;
                      return (<tr key={f}>
                        <td style={{ padding: "6px 8px", color: "#475569", fontWeight: 600, borderBottom: "1px solid #f1f5f9", whiteSpace: "nowrap" }}>{t(ru, ua)}</td>
                        {mm.contacts.map((c: any) => { const val = c[f] ?? ""; const chosen = mm.choice[f] === c.id; const isK = mm.keepId === c.id;
                          return (<td key={c.id} onClick={() => val !== "" && setMm({ ...mm, choice: { ...mm.choice, [f]: c.id } })}
                            style={{ padding: "5px 8px", borderBottom: "1px solid #f1f5f9", cursor: val !== "" ? "pointer" : "default", background: chosen ? "#dcfce7" : (isK ? "#f0fdf4" : ""), wordBreak: "break-word" }}>
                            {val !== "" ? <label style={{ display: "flex", alignItems: "flex-start", gap: 6, cursor: "pointer" }}><input type="radio" name={"ff-" + f} checked={chosen} onChange={() => setMm({ ...mm, choice: { ...mm.choice, [f]: c.id } })} style={{ marginTop: 2 }} /><span>{String(val)}</span></label> : <span className="muted">—</span>}
                          </td>); })}
                      </tr>); })}
                  </tbody>
                </table>
              </div>
            )}
            {mm.contacts.length > 0 && Object.keys(mm.msgSel).length > 0 && (
              <div style={{ marginTop: 14, border: "1px solid #e2e8f0", borderRadius: 10, padding: "10px 12px", background: "#f8fafc" }}>
                <div style={{ fontWeight: 700, fontSize: 12.5, marginBottom: 6 }}>{t("Мессенджеры / контакты (можно несколько)", "Месенджери / контакти (можна декілька)")}</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px" }}>
                  {Object.keys(mm.msgSel).map((m) => (
                    <label key={m} style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 12.5 }}>
                      <input type="checkbox" checked={!!mm.msgSel[m]} onChange={() => setMm({ ...mm, msgSel: { ...mm.msgSel, [m]: !mm.msgSel[m] } })} />
                      <span style={{ fontWeight: 700, fontSize: 10.5, color: "#2563eb", background: "#eff6ff", borderRadius: 5, padding: "1px 6px" }}>{msgLabel(m)}</span>
                      <span style={{ wordBreak: "break-all" }}>{m}</span>
                    </label>
                  ))}
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{t("Отмеченные останутся у объединённого контакта.", "Відмічені залишаться в обʼєднаного контакту.")}</div>
              </div>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
              <button className="btn btn-light" onClick={() => !mmBusy && setMm(null)}>{t("Отмена", "Скасувати")}</button>
              <button className="btn btn-primary" disabled={mmBusy || mm.contacts.length === 0} onClick={doMerge}>
                <Icon n="check" size={14} /> {mmBusy ? "…" : t("Объединить", "Обʼєднати")}
              </button>
            </div>
          </div>
        </div>, document.body)}
    </div>
  );
}
