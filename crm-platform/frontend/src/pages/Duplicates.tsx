/* Пошук дублів: контакти (телефон/email/мессенджер/імʼя) + ліди/сделки (один контакт — кілька).
   Контакти можна обʼєднати в один (перепривʼязка лідів/сделок/чатів + дозаповнення полів).
   Є: пошук по номеру/прізвищу, фільтр за критерієм збігу, фільтр за «силою» збігу
   та МАСОВЕ обʼєднання відмічених груп (з попереднім показом «що буде зроблено»). */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createPortal } from "react-dom";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

type Item = { id: number; name: string; phone?: string; email?: string; social?: string; stage?: string; owner?: string; amount?: string };
type Group = { reason: string; by: string; key: string; count: number; items: Item[]; matched?: string[]; strength?: number; keep_suggest?: number };

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
  // ── фільтри ──
  const [qInput, setQInput] = useState("");   // те, що набирає користувач
  const [q, setQ] = useState("");             // те, що вже пішло на сервер (з затримкою)
  const [byF, setByF] = useState("");         // критерій: '' | phone | email | social | name
  const [minF, setMinF] = useState(0);        // мінімальна «сила» збігу
  // ── масове обʼєднання ──
  const [sel, setSel] = useState<Record<number, boolean>>({}); // groupIdx -> відмічено
  const [bulk, setBulk] = useState<null | { preview: any; busy: boolean }>(null);

  // пошук з затримкою 400мс — щоб не смикати сервер на кожну літеру
  useEffect(() => { const h = setTimeout(() => setQ(qInput), 400); return () => clearTimeout(h); }, [qInput]);

  const load = () => {
    setLoading(true); setData(null); setPage(1); setSel({});
    const p = new URLSearchParams({ type: tab });
    if (q) p.set("q", q);
    if (tab === "contacts" && byF) p.set("by", byF);
    if (tab === "contacts" && minF) p.set("min", String(minF));
    api.get<any>(`/api/duplicates/?${p.toString()}`).then((d) => setData(d)).catch(() => setData({ total: 0, groups: [] })).finally(() => setLoading(false));
  };
  useEffect(load, [tab, q, byF, minF]);

  const openMerge = async (gi: number, g: Group) => {
    const ids = g.items.map((i) => i.id);
    const preKeep = keep[gi] ?? g.keep_suggest ?? ids[0];
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

  // ── масове обʼєднання: спершу показуємо «що буде зроблено», лише потім виконуємо ──
  const selectedGroups = () => (data ? data.groups.map((g, i) => ({ g, i })).filter(({ i }) => sel[i]) : []);
  const payloadGroups = () => selectedGroups().map(({ g, i }) => ({ keep: keep[i] ?? g.keep_suggest ?? g.items[0].id, ids: g.items.map((x) => x.id) }));

  const previewBulk = async () => {
    const groups = payloadGroups();
    if (!groups.length) return;
    setBulk({ preview: null, busy: true });
    try {
      const r = await api.post<any>("/api/duplicates/", { groups, dry_run: true });
      setBulk({ preview: r, busy: false });
    } catch { alert(t("Не удалось посчитать", "Не вдалося порахувати")); setBulk(null); }
  };

  const runBulk = async () => {
    const groups = payloadGroups();
    setBulk((b) => (b ? { ...b, busy: true } : b));
    try {
      const r = await api.post<any>("/api/duplicates/", { groups });
      setBulk(null); setSel({});
      alert(t(`Готово. Объединено групп: ${r.groups}, удалено дублей: ${r.merged}`,
        `Готово. Обʼєднано груп: ${r.groups}, видалено дублів: ${r.merged}`));
      load();
    } catch { alert(t("Не удалось объединить", "Не вдалося обʼєднати")); setBulk((b) => (b ? { ...b, busy: false } : b)); }
  };

  const tabs: [typeof tab, string, string][] = [
    ["contacts", "Клиенты", "Клієнти"], ["leads", "Лиды", "Ліди"], ["deals", "Сделки", "Сделки"],
  ];
  const byOptions: [string, string, string][] = [
    ["", "Все совпадения", "Всі збіги"], ["phone", "Только телефон", "Тільки телефон"],
    ["email", "Только email", "Тільки email"], ["social", "Только мессенджер", "Тільки месенджер"],
    ["name", "Только имя/фамилия", "Тільки імʼя/прізвище"],
  ];
  const minOptions: [number, string, string][] = [
    [0, "Любая точность", "Будь-яка точність"], [2, "Совпало ≥ 2 полей", "Збіглось ≥ 2 полів"],
    [3, "Совпало ≥ 3 полей", "Збіглось ≥ 3 полів"], [4, "Совпало всё (4 поля)", "Збіглось усе (4 поля)"],
  ];
  const pageGroups = data ? data.groups.slice((page - 1) * pageSize, page * pageSize) : [];
  const selCount = Object.values(sel).filter(Boolean).length;
  const allPageSelected = pageGroups.length > 0 && pageGroups.every((_, j) => sel[(page - 1) * pageSize + j]);

  return (
    <div className="scroll pad fade">
      <h2 style={{ margin: "0 0 4px", fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}>
        <Icon n="copy" size={20} /> {t("Поиск дублей", "Пошук дублів")}
      </h2>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
        {t("Совпадения по телефону, email, мессенджеру и имени. Контакты можно объединить в один.",
          "Збіги за телефоном, email, мессенджером та імʼям. Контакти можна обʼєднати в один.")}
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {tabs.map(([k, ru, uk]) => (
          <button key={k} className={"btn" + (tab === k ? " btn-primary" : " btn-light")} onClick={() => setTab(k)}>{t(ru, uk)}</button>
        ))}
        <button className="btn btn-light" onClick={load} title={t("Обновить", "Оновити")}><Icon n="refresh" size={15} /></button>
      </div>

      {/* ── панель фільтрів ── */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ position: "relative", flex: "1 1 260px", minWidth: 220 }}>
          <input value={qInput} onChange={(e) => setQInput(e.target.value)}
            placeholder={t("Поиск: номер телефона, фамилия, email, ник…", "Пошук: номер телефону, прізвище, email, нік…")}
            style={{ width: "100%", height: 34, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 30px 0 10px", fontSize: 13 }} />
          {qInput && <button onClick={() => setQInput("")} title={t("Очистить", "Очистити")}
            style={{ position: "absolute", right: 6, top: 6, border: "none", background: "transparent", cursor: "pointer", color: "#94a3b8", fontSize: 14 }}>✕</button>}
        </div>
        {tab === "contacts" && (<>
          <select value={byF} onChange={(e) => setByF(e.target.value)} style={{ height: 34, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 12.5, padding: "0 8px" }}>
            {byOptions.map(([v, ru, ua]) => <option key={v} value={v}>{t(ru, ua)}</option>)}
          </select>
          <select value={minF} onChange={(e) => setMinF(Number(e.target.value))} style={{ height: 34, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 12.5, padding: "0 8px" }}>
            {minOptions.map(([v, ru, ua]) => <option key={v} value={v}>{t(ru, ua)}</option>)}
          </select>
        </>)}
      </div>

      {loading && <div className="spin">{t("Ищем дубли…", "Шукаємо дублі…")}</div>}
      {data && !loading && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: 13 }}>{t(`Найдено групп: ${data.total}`, `Знайдено груп: ${data.total}`)}{data.groups.length < data.total ? t(` (первые ${data.groups.length})`, ` (перші ${data.groups.length})`) : ""}</span>
            {tab === "contacts" && pageGroups.length > 0 && (
              <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, cursor: "pointer" }}>
                <input type="checkbox" checked={allPageSelected} onChange={() => {
                  const next = { ...sel };
                  pageGroups.forEach((_, j) => { next[(page - 1) * pageSize + j] = !allPageSelected; });
                  setSel(next);
                }} />
                {t("Отметить всё на странице", "Відмітити все на сторінці")}
              </label>
            )}
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

          {pageGroups.map((g, j) => {
            const gi = (page - 1) * pageSize + j;
            const keepId = keep[gi] ?? g.keep_suggest ?? g.items[0].id;
            return (
              <div key={gi} className="panel" style={{ marginBottom: 12, padding: 0, overflow: "hidden", border: sel[gi] ? "1.5px solid #16a34a" : "" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "9px 14px", background: "#f8fafc", borderBottom: "1px solid #eef2f7", flexWrap: "wrap" }}>
                  {tab === "contacts" && (
                    <input type="checkbox" checked={!!sel[gi]} onChange={() => setSel((s) => ({ ...s, [gi]: !s[gi] }))}
                      title={t("Отметить для массового объединения", "Відмітити для масового обʼєднання")} style={{ cursor: "pointer" }} />
                  )}
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 700, color: "#475569" }}>
                    <Icon n={REASON_ICON[g.by] || "copy"} size={14} /> {t(...(REASON_LABEL[g.by] || [g.reason, g.reason]))}
                  </span>
                  {g.key && <span className="muted" style={{ fontSize: 12 }}>· {g.key}</span>}
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#fff", background: "#ef4444", borderRadius: 20, padding: "1px 9px" }}>{g.count}</span>
                  {/* чіпи: за якими полями збіг ПОВНИЙ у всіх учасників */}
                  {(g.matched || []).map((m) => (
                    <span key={m} style={{ fontSize: 10, fontWeight: 700, color: "#166534", background: "#dcfce7", borderRadius: 5, padding: "1px 6px" }}>
                      {t(...(REASON_LABEL[m] || [m, m]))}
                    </span>
                  ))}
                  {(g.strength || 0) >= 2 && (
                    <span style={{ fontSize: 10, fontWeight: 800, color: "#fff", background: "#16a34a", borderRadius: 5, padding: "1px 6px" }}>
                      {t(`совпало ${g.strength}`, `збіглось ${g.strength}`)}
                    </span>
                  )}
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

      {/* ── плаваюча панель масового обʼєднання ── */}
      {tab === "contacts" && selCount > 0 && !mm && !bulk && (
        <div style={{ position: "fixed", left: "50%", transform: "translateX(-50%)", bottom: 22, zIndex: 900, display: "flex", alignItems: "center", gap: 12, background: "#0f172a", color: "#fff", borderRadius: 12, padding: "10px 16px", boxShadow: "0 12px 34px rgba(0,0,0,.35)" }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>{t(`Отмечено групп: ${selCount}`, `Відмічено груп: ${selCount}`)}</span>
          <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => setSel({})}>{t("Снять", "Зняти")}</button>
          <button className="btn btn-primary" style={{ fontSize: 12.5 }} onClick={previewBulk}>
            <Icon n="check" size={14} /> {t("Объединить отмеченные", "Обʼєднати відмічені")}
          </button>
        </div>
      )}

      {/* ── підтвердження масового обʼєднання: спершу «що буде зроблено» ── */}
      {bulk && createPortal(
        <div onClick={() => !bulk.busy && setBulk(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 2147483000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: 640, maxWidth: "97vw", maxHeight: "86vh", overflow: "auto", background: "#fff", borderRadius: 14, boxShadow: "0 24px 70px rgba(0,0,0,.35)", padding: 18 }}>
            <h3 style={{ margin: "0 0 8px", fontSize: 17 }}>{t("Массовое объединение", "Масове обʼєднання")}</h3>
            {!bulk.preview ? <div className="muted" style={{ padding: 24, textAlign: "center" }}>…</div> : (<>
              <div style={{ fontSize: 13.5, marginBottom: 10 }}>
                {t(`Будет объединено групп: ${bulk.preview.groups}. Лишних контактов удалится: ${bulk.preview.will_delete}.`,
                  `Буде обʼєднано груп: ${bulk.preview.groups}. Зайвих контактів видалиться: ${bulk.preview.will_delete}.`)}
              </div>
              <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
                {t("Сделки, лиды и чаты перейдут на оставленный контакт. Пустые поля у него дозаполнятся из дублей.",
                  "Сделки, ліди і чати перейдуть на залишений контакт. Порожні поля в нього дозаповняться з дублів.")}
              </div>
              {(bulk.preview.skipped || []).length > 0 && (
                <div className="note" style={{ fontSize: 12, marginBottom: 10 }}>
                  {t(`Пропущено групп: ${bulk.preview.skipped.length} (контакт уже участвует в другой группе — объедини их отдельно).`,
                    `Пропущено груп: ${bulk.preview.skipped.length} (контакт вже бере участь в іншій групі — обʼєднай їх окремо).`)}
                </div>
              )}
              <div style={{ border: "1px solid #e2e8f0", borderRadius: 10, maxHeight: 320, overflow: "auto" }}>
                {(bulk.preview.preview || []).map((p: any) => (
                  <div key={p.keep} style={{ padding: "7px 10px", borderBottom: "1px solid #f1f5f9", fontSize: 12.5 }}>
                    <span style={{ fontWeight: 700, color: "#16a34a" }}>{p.keep_name} #{p.keep}</span>
                    <span className="muted"> ← {p.delete.map((d: any) => `${d.name} #${d.id}`).join(", ")}</span>
                  </div>
                ))}
              </div>
            </>)}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
              <button className="btn btn-light" disabled={bulk.busy} onClick={() => setBulk(null)}>{t("Отмена", "Скасувати")}</button>
              <button className="btn btn-primary" disabled={bulk.busy || !bulk.preview || !bulk.preview.groups} onClick={runBulk}>
                <Icon n="check" size={14} /> {bulk.busy ? "…" : t("Да, объединить", "Так, обʼєднати")}
              </button>
            </div>
          </div>
        </div>, document.body)}

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
