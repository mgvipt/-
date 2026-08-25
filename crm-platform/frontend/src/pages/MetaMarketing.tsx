import { Fragment, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { useLang } from "../i18n";
import { Cone, MetaCone } from "../FunnelCone";

// Явна підказка (тултип), яка показується ОДРАЗУ при наведенні і НЕ обрізається
// прокруткою таблиці (рендериться в body через портал, слідує за курсором).
function Tip({ text, children }: { text: string; children: ReactNode }) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  return (
    <span style={{ cursor: "help" }}
      onMouseEnter={(e) => { setPos({ x: e.clientX, y: e.clientY }); setShow(true); }}
      onMouseMove={(e) => setPos({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setShow(false)}>
      {children}
      {show && createPortal(
        <div style={{ position: "fixed", left: Math.min(pos.x + 14, window.innerWidth - 300), top: pos.y + 16, zIndex: 99999, background: "#231c18", color: "#fff", padding: "8px 11px", borderRadius: 9, fontSize: 12.5, maxWidth: 280, lineHeight: 1.45, fontWeight: 500, boxShadow: "0 6px 22px rgba(0,0,0,.35)", pointerEvents: "none" }}>{text}</div>,
        document.body)}
    </span>
  );
}

// ── Ширина столбцов, что запоминается (перетягивание за правый край шапки) ──
function useColWidths(storageKey: string, count: number) {
  const [widths, setWidths] = useState<Record<number, number>>(() => {
    try { const s = JSON.parse(localStorage.getItem(storageKey) || "{}"); return (s && typeof s === "object") ? s : {}; } catch { return {}; }
  });
  const set = (i: number, w: number) => setWidths((cur) => {
    const next = { ...cur, [i]: Math.max(56, Math.round(w)) };
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* */ }
    return next;
  });
  const reset = () => { try { localStorage.removeItem(storageKey); } catch { /* */ } setWidths({}); };
  return { widths, set, reset };
}

// Шапка-ячейка с ручкой изменения ширины у правого края.
function ResizableTh({ label, width, onResize, thStyle }: { label: ReactNode; width?: number; onResize: (w: number) => void; thStyle: any }) {
  const ref = useRef<HTMLTableCellElement>(null);
  const onDown = (e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX; const startW = ref.current ? ref.current.offsetWidth : (width || 120);
    const move = (ev: MouseEvent) => onResize(startW + (ev.clientX - startX));
    const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); document.body.style.cursor = ""; document.body.style.userSelect = ""; };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
    document.body.style.cursor = "col-resize"; document.body.style.userSelect = "none";
  };
  return (
    <th ref={ref} style={{ ...thStyle, width, minWidth: width, position: "relative" }}>
      {label}
      <span onMouseDown={onDown} title="Потягніть, щоб змінити ширину"
        style={{ position: "absolute", top: 0, right: -4, width: 9, height: "100%", cursor: "col-resize", zIndex: 2 }} />
    </th>
  );
}

// Панель пагинации: размер страницы (сохраняется) + перелистывание.
function Pager({ total, pageSize, page, sizeKey, onSize, onPage, t }: { total: number; pageSize: number; page: number; sizeKey: string; onSize: (n: number) => void; onPage: (p: number) => void; t: (ru: string, ua: string) => string }) {
  const all = pageSize >= 99999;
  const pages = all ? 1 : Math.max(1, Math.ceil(total / pageSize));
  const from = all || total === 0 ? (total ? 1 : 0) : page * pageSize + 1;
  const to = all ? total : Math.min(total, (page + 1) * pageSize);
  const btn: any = { minWidth: 30, height: 28, border: "1px solid #cbd5e1", borderRadius: 7, background: "#fff", cursor: "pointer", fontSize: 13 };
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", padding: "8px 12px", fontSize: 12.5, color: "#475569" }}>
      <span>{t("Показывать по", "Показувати по")}:</span>
      <select value={pageSize} onChange={(e) => { const n = Number(e.target.value); try { localStorage.setItem(sizeKey, String(n)); } catch { /* */ } onSize(n); onPage(0); }}
        style={{ height: 28, border: "1px solid #cbd5e1", borderRadius: 7, fontSize: 12.5, padding: "0 6px" }}>
        {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
        <option value={99999}>{t("все", "всі")}</option>
      </select>
      <span style={{ marginLeft: 4 }}>{from}–{to} {t("из", "з")} {total}</span>
      <div style={{ flex: 1 }} />
      {!all && pages > 1 && <>
        <button style={btn} disabled={page <= 0} onClick={() => onPage(0)}>«</button>
        <button style={btn} disabled={page <= 0} onClick={() => onPage(page - 1)}>‹</button>
        <span style={{ minWidth: 78, textAlign: "center" }}>{t("стр.", "стор.")} {page + 1} / {pages}</span>
        <button style={btn} disabled={page >= pages - 1} onClick={() => onPage(page + 1)}>›</button>
        <button style={btn} disabled={page >= pages - 1} onClick={() => onPage(pages - 1)}>»</button>
      </>}
    </div>
  );
}

// Універсальна таблиця для великих списків: перетягувані стовпці (память ширини),
// «прилипла» шапка + прокрутка в блоці фікс.висоти (горизонт.скрол завжди видно).
// Заголовки переносяться (стовпці можна звузити). Використовується у всіх вкладках.
function ResizableTable({ headers, rows, empty, minWidth, storageKey, tips }: { headers: string[]; rows: any[][]; empty: string; minWidth: number; storageKey: string; tips?: string[] }) {
  const cw = useColWidths(storageKey, headers.length);
  return (
    <div className="panel" style={{ padding: 0 }}>
      <div style={{ overflowX: "auto", overflowY: "auto", maxHeight: "calc(100vh - 240px)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", minWidth }}>
          <colgroup>{headers.map((_, i) => <col key={i} style={cw.widths[i] ? { width: cw.widths[i] } : undefined} />)}</colgroup>
          <thead style={{ position: "sticky", top: 0, zIndex: 3 }}><tr>{headers.map((h, i) => (
            <ResizableTh key={h + i} width={cw.widths[i]} onResize={(w) => cw.set(i, w)}
              thStyle={{ ...th, whiteSpace: "normal", wordBreak: "break-word", verticalAlign: "bottom", background: "#eef2f7" }}
              label={tips && tips[i] ? <Tip text={tips[i]}>{h}<span style={{ opacity: .45, marginLeft: 3, fontSize: 10, fontWeight: 400 }}>ⓘ</span></Tip> : h} />
          ))}</tr></thead>
          <tbody>{rows.length ? rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} style={td}>{v}</td>)}</tr>) :
            <tr><td colSpan={headers.length} style={{ ...td, color: "#64748b", textAlign: "center", padding: 28 }}>{empty}</td></tr>}</tbody>
        </table>
      </div>
    </div>
  );
}

const CONNECTED_FROM = "2026-06-16";
const TAB_KEYS = ["overview", "profitability", "ads", "creatives", "content", "funnel", "forms", "sources"] as const;
type Tab = typeof TAB_KEYS[number];
type AdLevel = "campaigns" | "adsets" | "ads";

function iso(d: Date) { return d.toISOString().slice(0, 10); }
function count(v: any) { return Number(v || 0).toLocaleString("ru-RU"); }
function moneyUah(v: any) { return `${Number(v || 0).toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ₴`; }
function moneyUsd(v: any) { return `$${Number(v || 0).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }
function optional(v: any, suffix = "", empty = "нет данных") {
  return v === null || v === undefined ? <span style={{ color: "#94a3b8" }}>{empty}</span> : `${count(v)}${suffix}`;
}
function dateTime(v: any) {
  if (!v) return "—";
  return new Date(v).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/* ─── Дашборды воронок: выбор «Воронка Меты» / «Воронка продаж (CRM)» ─── */
function MetaConeFunnel({ from, to }: { from: string; to: string }) {
  const { t } = useLang();
  const [mode, setMode] = useState<"meta" | "crm">("meta");
  const [d, setD] = useState<any>(null);
  const [funnels, setFunnels] = useState<any[]>([]);
  const [crmFid, setCrmFid] = useState<string>("");
  const [crm, setCrm] = useState<any>(null);
  useEffect(() => { api.get<any>(`/api/meta-marketing/funnel/?from=${from}&to=${to}`).then(setD).catch(() => setD(null)); }, [from, to]);
  useEffect(() => {
    if (mode !== "crm") return;
    const q = `?from=${from}&to=${to}` + (crmFid ? `&funnel=${crmFid}` : "");
    api.get<any>("/api/analytics/sales-funnel/" + q).then((r) => { setCrm(r); setFunnels((f) => f.length ? f : (r.funnels || [])); }).catch(() => {});
  }, [mode, from, to, crmFid]);
  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>🎯 {t("Дашборды воронок", "Дашборди воронок")}</div>
        <div style={{ display: "flex", gap: 6, marginLeft: 8 }}>
          <button onClick={() => setMode("meta")} className={mode === "meta" ? "btn btn-primary" : "btn btn-light"} style={{ fontSize: 12.5 }}>{t("Воронка Меты", "Воронка Мети")}</button>
          <button onClick={() => setMode("crm")} className={mode === "crm" ? "btn btn-primary" : "btn btn-light"} style={{ fontSize: 12.5 }}>{t("Воронка продаж (CRM)", "Воронка продажів (CRM)")}</button>
        </div>
        {mode === "crm" && funnels.length > 0 && <select value={crmFid} onChange={(e) => setCrmFid(e.target.value)} style={{ height: 30, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 12.5, background: "#fff" }}>{funnels.map((f: any) => <option key={f.id} value={f.id}>{f.name}{f.is_lead ? " ★" : ""}</option>)}</select>}
      </div>
      {mode === "meta" ? (
        <>
          <div className="muted" style={{ fontSize: 12, marginBottom: 14, lineHeight: 1.5 }}>{t("Где теряются лиды от рекламы до продажи. «% от преды.» — конверсия шага. Тест/оплата — по клиентам рекламных лидов; пока атрибуция молодая, значения малы.", "Де губляться ліди від реклами до продажу. «% від попер.» — конверсія кроку.")}</div>
          {d ? <MetaCone d={d} t={t} /> : <div className="muted">…</div>}
        </>
      ) : (
        <>
          <div className="muted" style={{ fontSize: 12, marginBottom: 14, lineHeight: 1.5 }}>{t("Воронка CRM — тот же расчёт «прошло через этап», что в Аналитике продаж.", "Воронка CRM — той самий розрахунок, що в Аналітиці продажів.")}</div>
          {crm ? <Cone d={crm} t={t} /> : <div className="muted">…</div>}
        </>
      )}
    </div>
  );
}

/* ─── График роста подписчиков кабинета по дням ─── */
function AccountGrowth({ followers, organic, t }: { followers: any; organic: any[]; t: any }) {
  const daily = (followers.daily || []);
  const maxG = Math.max(...daily.map((d: any) => Math.abs(d.gained || 0)), 1);
  const num = (n: number) => Number(n || 0).toLocaleString("ru-RU");
  const withFollows = (organic || []).filter((r: any) => r.follows != null && r.follows > 0).sort((a: any, b: any) => b.follows - a.follows);
  const postFollows = withFollows.reduce((a: number, r: any) => a + (r.follows || 0), 0);
  const reelsCount = (organic || []).filter((r: any) => (r.media_product_type || "") === "REELS").length;
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(185px,1fr))", gap: 10, marginBottom: 14 }}>
        <div className="panel" style={{ margin: 0, borderLeft: "3px solid #7c3aed" }}>
          <div className="muted" style={{ fontSize: 12 }}>👥 {t("Подписалось — органика", "Підписалося — органіка")}</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: (followers.period_gained || 0) >= 0 ? "#15803d" : "#dc2626" }}>{(followers.period_gained || 0) >= 0 ? "+" : ""}{num(followers.period_gained)}</div>
          <div className="muted" style={{ fontSize: 11 }}>{t("чистый прирост кабинета за период", "чистий приріст кабінету за період")}</div>
        </div>
        <div className="panel" style={{ margin: 0, borderLeft: "3px solid #0f766e" }}>
          <div className="muted" style={{ fontSize: 12 }}>📄 {t("Подписок с постов", "Підписок з постів")}</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{num(postFollows)}</div>
          <div className="muted" style={{ fontSize: 11 }}>{t("Meta отдаёт только для обычных постов", "Meta віддає лише для звичайних постів")}</div>
        </div>
      </div>
      <div className="panel" style={{ margin: 0, marginBottom: 14 }}>
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>📈 {t("Прирост подписчиков по дням", "Приріст підписників по днях")}</div>
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 12 }}>{t("Зелёные — набрали в этот день, красные — потеряли. Это органика кабинета (платных подписок нет).", "Зелені — набрали, червоні — втратили. Це органіка кабінету.")}</div>
        {daily.length === 0 ? <div className="muted">{t("Нет данных за период", "Немає даних за період")}</div> : (
          <div style={{ display: "flex", alignItems: "center", gap: 3, minHeight: 170, overflowX: "auto" }}>
            {daily.map((d: any) => {
              const g = d.gained || 0;
              const h = (Math.abs(g) / maxG) * 62;
              return (
                <div key={d.date} style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 24, flex: 1 }} title={`${d.date}: ${g >= 0 ? "+" : ""}${g} (${t("всего", "всього")} ${num(d.total)})`}>
                  <span style={{ fontSize: 9, color: g >= 0 ? "#15803d" : "#dc2626", fontWeight: 700 }}>{g >= 0 ? "+" : ""}{g}</span>
                  <div style={{ height: 66, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>{g >= 0 && <div style={{ width: 13, height: Math.max(h, 2), background: "#22c55e", borderRadius: "3px 3px 0 0" }} />}</div>
                  <div style={{ height: 66, display: "flex", flexDirection: "column", justifyContent: "flex-start" }}>{g < 0 && <div style={{ width: 13, height: Math.max(h, 2), background: "#ef4444", borderRadius: "0 0 3px 3px" }} />}</div>
                  <span style={{ fontSize: 9, color: "#94a3b8", whiteSpace: "nowrap" }}>{String(d.date).slice(5)}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>👥 {t("Подписки по публикациям", "Підписки по публікаціях")}</div>
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 10, lineHeight: 1.5 }}>{t(`Meta отдаёт «подписки с публикации» ТОЛЬКО для обычных постов. Для Reels (${reelsCount} шт за период) — не отдаёт, это ограничение API Meta (проверено ответом API #100).`, `Meta віддає «підписки з публікації» ЛИШЕ для звичайних постів. Для Reels (${reelsCount}) — не віддає (обмеження API Meta).`)}</div>
        {withFollows.length === 0 ? <div className="muted" style={{ fontSize: 12.5 }}>{t("За период постов с подписками нет (или только Reels).", "За період постів з підписками немає.")}</div> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 420, fontSize: 13 }}>
              <thead><tr>
                <th style={{ textAlign: "left", padding: "6px 8px", color: "#64748b", fontSize: 12 }}>{t("Публикация", "Публікація")}</th>
                <th style={{ textAlign: "right", padding: "6px 8px", color: "#64748b", fontSize: 12 }}>{t("Подписок", "Підписок")}</th>
                <th style={{ textAlign: "right", padding: "6px 8px", color: "#64748b", fontSize: 12 }}>{t("Охват", "Охоплення")}</th>
              </tr></thead>
              <tbody>{withFollows.map((r: any) => (
                <tr key={r.media_id} style={{ borderTop: "1px solid #f1f5f9" }}>
                  <td style={{ padding: "6px 8px" }}><a href={r.permalink} target="_blank" rel="noreferrer" style={{ color: "#2563eb", textDecoration: "none" }}>{(r.caption || "—").slice(0, 44)}</a></td>
                  <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 700, color: "#7c3aed" }}>+{num(r.follows)}</td>
                  <td style={{ padding: "6px 8px", textAlign: "right" }}>{num(r.reach)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Модалка настроек маркетинга: интервалы обновления + доступы по ролям ─── */
function MetaSettingsModal({ onClose }: { onClose: () => void }) {
  const { t } = useLang();
  const [st, setSt] = useState<any>(null);
  const [roles, setRoles] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");
  useEffect(() => {
    api.get<any>("/api/meta-marketing/settings/").then(setSt).catch(() => {});
    api.get<any>("/api/roles/").then((r: any) => setRoles(r.results || r || [])).catch(() => {});
  }, []);
  const PRESETS: [number, string, string][] = [[30, "30 минут", "30 хвилин"], [60, "1 час", "1 година"], [120, "2 часа", "2 години"], [180, "3 часа", "3 години"], [360, "6 часов", "6 годин"], [720, "12 часов", "12 годин"], [1440, "24 часа", "24 години"]];
  const setField = (f: string, v: any) => setSt((s: any) => ({ ...s, [f]: v }));
  const save = () => {
    setSaving(true);
    api.put<any>("/api/meta-marketing/settings/", st).then((r) => { setSt(r); setSavedMsg(t("Сохранено ✓", "Збережено ✓")); setTimeout(() => setSavedMsg(""), 2500); }).catch(() => setSavedMsg(t("Ошибка", "Помилка"))).finally(() => setSaving(false));
  };
  const toggleRoleMkt = (role: any) => {
    const perms: string[] = role.permissions || [];
    const has = perms.includes("marketing.view");
    const next = has ? perms.filter((p) => p !== "marketing.view") : [...perms, "marketing.view"];
    setRoles((rs) => rs.map((x) => x.id === role.id ? { ...x, permissions: next } : x));
    api.patch<any>(`/api/roles/${role.id}/`, { permissions: next }).catch(() => {});
  };
  const src: [string, string, string][] = [["ads", "Реклама (Ads)", "Реклама (Ads)"], ["content", "Instagram (публикации)", "Instagram (публікації)"], ["account", "Подписчики кабинета", "Підписники кабінету"]];
  const body = !st ? <div className="muted" style={{ padding: 20 }}>…</div> : (() => {
    const canEdit = st.can_edit;
    return (
      <div>
        {!canEdit && <div className="note" style={{ marginBottom: 12, background: "#fef9c3", color: "#854d0e" }}>{t("Только просмотр — менять настройки может руководитель.", "Лише перегляд — змінювати може керівник.")}</div>}
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 6 }}>{t("Частота обновления данных", "Частота оновлення даних")}</div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Как часто фоновая система тянет свежие данные из каждого источника (действует без перезапуска).", "Як часто фонова система тягне свіжі дані з кожного джерела.")}</div>
        {src.map(([key, ru, ua]) => (
          <div key={key} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 220 }}>
              <input type="checkbox" checked={!!st[`${key}_enabled`]} disabled={!canEdit} onChange={(e) => setField(`${key}_enabled`, e.target.checked)} />
              <b style={{ fontSize: 13 }}>{t(ru, ua)}</b>
            </label>
            <select value={st[`${key}_interval_min`]} disabled={!canEdit || !st[`${key}_enabled`]} onChange={(e) => setField(`${key}_interval_min`, Number(e.target.value))} style={{ height: 32, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 8px", background: "#fff" }}>
              {PRESETS.map(([v, ru2, ua2]) => <option key={v} value={v}>{t(ru2, ua2)}</option>)}
            </select>
          </div>
        ))}
        {canEdit && <div style={{ marginTop: 8 }}><button className="btn btn-primary" onClick={save} disabled={saving}>{saving ? "…" : t("Сохранить", "Зберегти")}</button> {savedMsg && <span style={{ color: "#15803d", marginLeft: 10, fontWeight: 600 }}>{savedMsg}</span>}</div>}
        <div style={{ borderTop: "1px solid #eef2f7", margin: "18px 0" }} />
        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 6 }}>{t("Доступ к маркетингу (по ролям)", "Доступ до маркетингу (за ролями)")}</div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("Кому видна аналитика маркетинга. Отметь роль — она получит доступ.", "Кому видно аналітику маркетингу.")}</div>
        {roles.length === 0 ? <div className="muted">…</div> : roles.map((role) => (
          <label key={role.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, fontSize: 13 }}>
            <input type="checkbox" checked={(role.permissions || []).includes("marketing.view")} disabled={!canEdit} onChange={() => toggleRoleMkt(role)} />
            {role.name}
          </label>
        ))}
        <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>{t("Индивидуально по сотрудникам — Настройки → Пользователи.", "Індивідуально — Налаштування → Користувачі.")}</div>
      </div>
    );
  })();
  return createPortal(
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 9999, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 24, overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, maxWidth: 620, width: "100%", padding: 22, boxShadow: "0 20px 60px rgba(0,0,0,.3)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 18 }}>⚙️ {t("Настройки маркетинга", "Налаштування маркетингу")}</h3>
          <button className="btn btn-light" onClick={onClose}>✕</button>
        </div>
        {body}
      </div>
    </div>, document.body);
}

export default function MetaMarketing() {
  const { t } = useLang();
  const today = useMemo(() => new Date(), []);
  const [from, setFrom] = useState(CONNECTED_FROM);
  const [to, setTo] = useState(iso(today));
  const [tab, setTab] = useState<Tab>("overview");
  const [adLevel, setAdLevel] = useState<AdLevel>("campaigns");
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncSt, setSyncSt] = useState<any>(null);
  const [syncing, setSyncing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [orgView, setOrgView] = useState<"cards" | "table" | "account">("cards");
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    setError(""); setLoading(true);
    api.get<any>(`/api/meta-marketing/?from=${from}&to=${to}`)
      .then(setData)
      .catch(() => setError(t("Не удалось загрузить данные", "Не вдалося завантажити дані")))
      .finally(() => setLoading(false));
  }, [from, to, t, refreshKey]);
  const loadSyncStatus = () => api.get<any>("/api/meta-marketing/sync-status/").then(setSyncSt).catch(() => {});
  useEffect(() => { loadSyncStatus(); }, []);
  const refreshNow = () => {
    if (syncing) return;
    setSyncing(true);
    const baseAds = syncSt?.sources?.ads?.at || "";
    const baseCont = syncSt?.sources?.content?.at || "";
    api.post<any>("/api/meta-marketing/sync-now/", { scope: "all", days: 7 }).catch(() => {});
    // sync из Meta идёт в фоне ~1-3 мин; опрашиваем статус, пока данные не обновятся
    let tries = 0;
    const poll = () => {
      tries++;
      api.get<any>("/api/meta-marketing/sync-status/").then((st) => {
        setSyncSt(st);
        const fresh = (st?.sources?.ads?.at && st.sources.ads.at !== baseAds) || (st?.sources?.content?.at && st.sources.content.at !== baseCont);
        if (fresh || tries >= 22) { setRefreshKey((k) => k + 1); setSyncing(false); }
        else setTimeout(poll, 12000);
      }).catch(() => { if (tries >= 22) setSyncing(false); else setTimeout(poll, 12000); });
    };
    setTimeout(poll, 12000);
  };

  const setLastDays = (days: number) => {
    const start = new Date(today); start.setDate(start.getDate() - days + 1);
    setFrom(iso(start)); setTo(iso(today));
  };

  const tabs: { key: Tab; ru: string; ua: string }[] = [
    { key: "overview", ru: "Обзор", ua: "Огляд" },
    { key: "profitability", ru: "Продажи и рентабельность", ua: "Продажі та рентабельність" },
    { key: "ads", ru: "Реклама", ua: "Реклама" },
    { key: "creatives", ru: "Креативы", ua: "Креативи" },
    { key: "content", ru: "Органика · SMM", ua: "Органіка · SMM" },
    { key: "funnel", ru: "Дашборды", ua: "Дашборди" },
    { key: "forms", ru: "Лид-формы", ua: "Лід-форми" },
    { key: "sources", ru: "Источники", ua: "Джерела" },
  ];
  const summary = data?.summary || {};
  const paid = data?.paid || {};
  const paidSummary = paid.summary || {};
  const integration = data?.integration || {};
  const organic = data?.organic?.content || [];
  const profitability = data?.profitability || {};
  const followers = data?.followers || {};
  const orgAgg = {
    reach: organic.reduce((a: number, r: any) => a + (r.reach || 0), 0),
    er: (() => { const arr = organic.filter((r: any) => r.engagement_rate != null); return arr.length ? arr.reduce((a: number, r: any) => a + r.engagement_rate, 0) / arr.length : 0; })(),
  };
  const daily = data?.daily || [];

  const card = (label: string, value: ReactNode, color = "#0f172a", hint?: string) => (
    <div className="panel" style={{ padding: "9px 11px", minWidth: 124, flex: "1 1 124px", margin: 0 }}>
      <div className="muted" style={{ fontSize: 10.5, lineHeight: 1.25 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 800, color, marginTop: 2 }}>{value}</div>
      {hint && <div className="muted" style={{ fontSize: 9.5, marginTop: 3, lineHeight: 1.25 }}>{hint}</div>}
    </div>
  );
  const table = (headers: string[], rows: ReactNode[][], empty: string, minWidth = 760, tips?: string[]) => (
    <ResizableTable headers={headers} rows={rows} empty={empty} minWidth={minWidth}
      storageKey={"mm_tbl_" + headers.join("|").slice(0, 60)} tips={tips} />
  );

  const syncWarning = !integration.insights_sync_configured ? (
    <div className="note" style={{ marginBottom: 14, borderLeft: "4px solid #f59e0b", lineHeight: 1.55 }}>
      <b>{t("Первичная загрузка Meta ещё не завершена.", "Первинне завантаження Meta ще не завершене.")}</b><br />
      {t("После синхронизации здесь появятся реальные расходы, кампании, объявления и органический контент. CRM не подставляет фиктивные нули.",
        "Після синхронізації тут з'являться реальні витрати, кампанії, оголошення та органічний контент. CRM не підставляє фіктивні нулі.")}
    </div>
  ) : null;

  const platformLabel = (row: any) => {
    const title = row.name || row.ad_name || row.adset_name || row.campaign_name || row.id;
    return <div style={{ minWidth: 220 }}><b>{title || "—"}</b>{row.effective_status && <div className="muted" style={{ fontSize: 10 }}>{row.effective_status}</div>}</div>;
  };
  const adRows = (paid[adLevel] || []).map((r: any) => [
    platformLabel(r), moneyUsd(r.spend), count(r.impressions), count(r.clicks), optional(r.ctr, "%"),
    count(r.messages_started), count(r.meta_leads), count(r.crm_leads), r.cost_per_message == null ? "—" : moneyUsd(r.cost_per_message),
  ]);
  const dailyTable = <DailySalesTable rows={daily} t={t} />;

  return <div style={{ height: "100%", overflowY: "auto", padding: 16, boxSizing: "border-box" }}>
    <div style={{ width: "100%" }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 23 }}>📣 {t("Маркетинг · Meta", "Маркетинг · Meta")}</h2>
          <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>
            {t("Платная реклама и органический контент считаются отдельно", "Платна реклама й органічний контент рахуються окремо")}
            {syncSt && <> · {t("обновление каждые", "оновлення кожні")} {syncSt.interval_hours}{t("ч", "год")}{syncSt.sources?.content && <> · Instagram <b style={{ color: (syncSt.sources.content.mins_ago > 420) ? "#b91c1c" : "#166534" }}>{syncSt.sources.content.at}</b></>}{syncSt.sources?.ads && <> · Ads <b style={{ color: (syncSt.sources.ads.mins_ago > 420) ? "#b91c1c" : "#166534" }}>{syncSt.sources.ads.at}</b></>}</>}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <button className="btn btn-light" onClick={() => setLastDays(1)}>{t("Сегодня", "Сьогодні")}</button>
        <button className="btn btn-light" onClick={() => setLastDays(7)}>7 {t("дней", "днів")}</button>
        <button className="btn btn-light" onClick={() => setLastDays(30)}>30 {t("дней", "днів")}</button>
        <button className="btn btn-light" onClick={() => setLastDays(90)}>90 {t("дней", "днів")}</button>
        <button className="btn btn-light" onClick={() => { setFrom(CONNECTED_FROM); setTo(iso(today)); }}>{t("С подключения CRM", "З підключення CRM")}</button>
        <label style={dateLabel}>{t("с", "з")} <input type="date" value={from} min={CONNECTED_FROM} onChange={(e) => setFrom(e.target.value)} style={dateInput} /></label>
        <label style={dateLabel}>{t("по", "по")} <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={dateInput} /></label>
        <button className="btn btn-primary" onClick={refreshNow} disabled={syncing} title={t("Подтянуть свежие данные со всех источников (Ads + Instagram + подписчики)", "Підтягнути свіжі дані з усіх джерел")}>{syncing ? `⏳ ${t("Обновляю…", "Оновлюю…")}` : `🔄 ${t("Обновить", "Оновити")}`}</button>
        <button className="btn btn-light" onClick={() => setShowSettings(true)} title={t("Настройки маркетинга: интервалы обновления и доступы", "Налаштування маркетингу")}>⚙️</button>
      </div>
      {showSettings && <MetaSettingsModal onClose={() => setShowSettings(false)} />}
      {syncing && <div className="note" style={{ marginBottom: 10, background: "#eff6ff", color: "#1e40af" }}>{t("Тянем свежие данные из Meta (Ads + Instagram + подписчики). Это ~1-3 минуты — таблицы обновятся автоматически, можно продолжать работать.", "Тягнемо свіжі дані з Meta. Це ~1-3 хвилини — таблиці оновляться автоматично.")}</div>}

      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 8, marginBottom: 8 }}>
        {tabs.map((item) => <button key={item.key} className={tab === item.key ? "btn btn-primary" : "btn btn-light"} onClick={() => setTab(item.key)} style={{ whiteSpace: "nowrap" }}>{t(item.ru, item.ua)}</button>)}
      </div>
      {error && <div className="note" style={{ color: "#b91c1c" }}>{error}</div>}
      {loading && !data ? <div className="muted" style={{ padding: 30 }}>Загрузка…</div> : data && <>
        {tab === "overview" && <>
          {syncWarning}
          <SectionTitle title={t("Instagram аккаунт", "Instagram акаунт")} note={t("Баланс подписчиков сохраняется ежедневно; прирост Meta отдаёт по дням", "Баланс підписників зберігається щодня; приріст Meta віддає по днях")} />
          <div style={cardsRow}>
            {card(t("Подписчиков сейчас", "Підписників зараз"), optional(followers.current_total, "", t("ожидает синхронизации", "очікує синхронізації")), "#c026d3", followers.username ? `@${followers.username}` : undefined)}
            {card(t("Новых за период", "Нових за період"), followers.period_gained == null ? "—" : count(followers.period_gained), "#db2777")}
            {card(t("Публикаций за период", "Публікацій за період"), count(daily.reduce((sum: number, r: any) => sum + Number(r.content_published || 0), 0)), "#7c3aed")}
            {card(t("Все лиды CRM из Meta", "Усі ліди CRM з Meta"), count(summary.meta_origin_leads), "#0284c7")}
            {card(t("С точным ID рекламы", "З точним ID реклами"), count(summary.attributed_leads), "#2563eb")}
            {card(t("Источник объявления не определён", "Джерело оголошення не визначене"), count(summary.meta_unassigned_leads), "#d97706")}
          </div>
          <SectionTitle title={t("Подписчики и стоимость (итоги)", "Підписники та вартість (підсумки)")} note={t("Подписки: органика отдельно от рекламы. Цена — рекламный расход ÷ на всех за период (blended).", "Підписки: органіка окремо від реклами. Ціна — витрати ÷ на всіх (blended).")} />
          <div style={cardsRow}>
            {card(t("Подписалось (органика)", "Підписалося (органіка)"), (followers.period_gained >= 0 ? "+" : "") + count(followers.period_gained), "#7c3aed")}
            {card(t("С рекламы (платно)", "З реклами (платно)"), "0", "#2563eb", t("кампании на переписку, не на подписку", "кампанії на листування"))}
            {card(t("Цена подписчика", "Ціна підписника"), (followers.period_gained > 0 && paidSummary.spend) ? "$" + (paidSummary.spend / followers.period_gained).toFixed(2) : "—", "#0f766e", t("расход рекламы ÷ новых подписчиков", "витрати ÷ нових підписників"))}
            {card(t("Цена клиента", "Ціна клієнта"), (profitability.buyers > 0 && paidSummary.spend) ? "$" + (paidSummary.spend / profitability.buyers).toFixed(2) : "—", "#dc2626", t("расход рекламы ÷ покупателей", "витрати ÷ покупців"))}
          </div>
          <SectionTitle title={t("Платная реклама Meta", "Платна реклама Meta")} note={t("Данные Ads Manager за выбранный период", "Дані Ads Manager за вибраний період")} />
          <div style={cardsRow}>
            {card(t("Расход", "Витрати"), moneyUsd(paidSummary.spend), "#dc2626")}
            {card(t("Показы", "Покази"), count(paidSummary.impressions), "#2563eb")}
            {card(t("Клики", "Кліки"), count(paidSummary.clicks), "#7c3aed")}
            {card("CTR", optional(paidSummary.ctr, "%"), "#7c3aed")}
            {card(t("Начатые диалоги по Ads Manager", "Розпочаті діалоги за Ads Manager"), count(paidSummary.messages_started), "#0f766e", t("Это показатель рекламы Meta, а не продажи и не уникальные лиды CRM", "Це показник реклами Meta, а не продажі й не унікальні ліди CRM"))}
            {card(t("Лиды Meta", "Ліди Meta"), count(paidSummary.meta_leads), "#0f766e")}
          </div>
          <SectionTitle title={t("Подтверждённый результат в CRM", "Підтверджений результат у CRM")} note={t("Только карточки с точным ID рекламы; ручные и органические исключены", "Лише картки з точним ID реклами; ручні та органічні виключені")} />
          <div style={cardsRow}>
            {card(t("Рекламные лиды CRM", "Рекламні ліди CRM"), count(summary.attributed_leads), "#2563eb")}
            {card(t("Рекламные сделки", "Рекламні угоди"), count(summary.attributed_deals), "#7c3aed")}
            {card(t("Успешные", "Успішні"), count(summary.won_deals), "#16a34a")}
            {card(t("Выручка успешных", "Виручка успішних"), moneyUah(summary.won_revenue), "#15803d")}
            {card(t("Оплачено", "Сплачено"), moneyUah(summary.paid_revenue), "#047857")}
          </div>
          <div className="note" style={{ lineHeight: 1.5 }}>
            <b>{t("Почему цифры Meta и CRM отличаются:", "Чому цифри Meta й CRM відрізняються:")}</b> {t(
              "Meta считает события по своему окну атрибуции. CRM показывает только реальные карточки с доказанной рекламной связью. Исторические лиды без ID объявления не приписываются рекламе задним числом.",
              "Meta рахує події за власним вікном атрибуції. CRM показує лише реальні картки з доведеною рекламною прив'язкою. Історичні ліди без ID оголошення не приписуються рекламі заднім числом."
            )}
          </div>
          <SectionTitle title={t("Продажи и окупаемость", "Продажі та окупність")} note={t("21 Основний продукт, 22 Тестовий набір; другие воронки только с точным ID рекламы", "21 Основний продукт, 22 Тестовий набір; інші воронки лише з точним ID реклами")} />
          <div style={cardsRow}>
            {card(t("Продажи", "Продажі"), count(profitability.sales), "#16a34a")}
            {card(t("Выручка", "Виручка"), moneyUah(profitability.revenue), "#047857")}
            {card(t("Повторные продажи", "Повторні продажі"), count(profitability.repeat_sales), "#0891b2")}
            {card(t("Из выручки — повторные", "З виручки — повторні"), moneyUah(profitability.repeat_revenue), "#0e7490")}
            {card(t("Средний LTV", "Середній LTV"), moneyUah(profitability.average_ltv), "#7c3aed")}
            {card("ROMI", profitability.romi == null ? "—" : `${profitability.romi}%`, Number(profitability.romi) >= 0 ? "#15803d" : "#dc2626")}
          </div>
          <SectionTitle title={t("Общая статистика по дням", "Загальна статистика за днями")} note={t("Реклама, лиды, продажи, повторные покупки, LTV и прибыль в одной таблице", "Реклама, ліди, продажі, повторні покупки, LTV і прибуток в одній таблиці")} />
          {dailyTable}
        </>}

        {tab === "profitability" && <>
          <div className="note" style={{ marginBottom: 12, lineHeight: 1.5 }}>
            <b>{t("Что входит в расчёт:", "Що входить у розрахунок:")}</b> {t(
              "Все оплаченные продажи из воронок «21 Основний продукт» и «22 Тестовий набір». Из остальных воронок — только продажи с подтверждённым ID Meta. Выручка считается по фактически оплаченным платежам. Повторная выручка — часть общей выручки, её не нужно прибавлять второй раз. Себестоимость считается по товарам сделки, рекламный расход переводится в гривну по официальному курсу НБУ за каждый день.",
              "Усі оплачені продажі з воронок «21 Основний продукт» і «22 Тестовий набір». З інших воронок — лише продажі з підтвердженим ID Meta. Виручка рахується за фактично сплаченими платежами. Повторна виручка — частина загальної виручки, її не потрібно додавати вдруге. Собівартість рахується за товарами угоди, рекламні витрати переводяться у гривню за офіційним курсом НБУ за кожен день."
            )}
          </div>
          <div style={cardsRow}>
            {card(t("Продажи", "Продажі"), count(profitability.sales), "#16a34a")}
            {card(t("Покупатели", "Покупці"), count(profitability.buyers), "#0f766e")}
            {card(t("Повторные продажи", "Повторні продажі"), count(profitability.repeat_sales), "#0891b2")}
            {card(t("Повторные клиенты", "Повторні клієнти"), count(profitability.repeat_buyers), "#0891b2")}
            {card(t("Выручка", "Виручка"), moneyUah(profitability.revenue), "#047857")}
            {card(t("Из выручки — повторные", "З виручки — повторні"), moneyUah(profitability.repeat_revenue), "#0e7490")}
            {card(t("Средний LTV", "Середній LTV"), moneyUah(profitability.average_ltv), "#7c3aed")}
            {card(t("Себестоимость", "Собівартість"), moneyUah(profitability.cost), "#b45309")}
            {card(t("Валовая прибыль", "Валовий прибуток"), moneyUah(profitability.gross_profit), "#15803d")}
            {card(t("Реклама по курсу НБУ", "Реклама за курсом НБУ"), profitability.ad_spend_uah == null ? "—" : moneyUah(profitability.ad_spend_uah), "#dc2626")}
            {card(t("Прибыль после рекламы", "Прибуток після реклами"), profitability.marketing_profit == null ? "—" : moneyUah(profitability.marketing_profit), Number(profitability.marketing_profit) >= 0 ? "#15803d" : "#dc2626")}
            {card(t("Общий ROAS", "Загальний ROAS"), profitability.blended_roas == null ? "—" : `${profitability.blended_roas}×`, "#2563eb")}
            {card(t("ROAS с точным ID", "ROAS з точним ID"), profitability.exact_ad_roas == null ? "—" : `${profitability.exact_ad_roas}×`, "#7c3aed", t("Консервативный показатель: только доказанная связь с объявлением", "Консервативний показник: лише доведений зв'язок з оголошенням"))}
            {card("ROMI", profitability.romi == null ? "—" : `${profitability.romi}%`, Number(profitability.romi) >= 0 ? "#15803d" : "#dc2626")}
          </div>
          <SectionTitle title={t("Рентабельность по дням", "Рентабельність за днями")} note={t("Меняйте период сверху: день, неделя, месяц, 90 дней или произвольный диапазон", "Змінюйте період зверху: день, тиждень, місяць, 90 днів або довільний діапазон")} />
          {dailyTable}
        </>}

        {tab === "ads" && <>
          {syncWarning}
          <div style={{ display: "flex", gap: 7, marginBottom: 10, flexWrap: "wrap" }}>
            {(["campaigns", "adsets", "ads"] as AdLevel[]).map((key) => <button key={key} className={adLevel === key ? "btn btn-primary" : "btn btn-light"} onClick={() => setAdLevel(key)}>
              {key === "campaigns" ? t("Кампании", "Кампанії") : key === "adsets" ? t("Группы объявлений", "Групи оголошень") : t("Объявления", "Оголошення")}
            </button>)}
          </div>
          {table([
            adLevel === "campaigns" ? t("Кампания", "Кампанія") : adLevel === "adsets" ? t("Группа", "Група") : t("Объявление", "Оголошення"),
            t("Расход", "Витрати"), t("Показы", "Покази"), t("Клики", "Кліки"), "CTR", t("Диалоги Meta", "Діалоги Meta"), t("Лиды Meta", "Ліди Meta"), t("Лиды CRM", "Ліди CRM"), t("Цена диалога", "Ціна діалогу"),
          ], adRows, t("За выбранный период реклама не показывалась", "За вибраний період реклама не показувалась"), 1120)}
          <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
            {t("Охват по дням не суммируется как уникальный охват периода, поэтому в таблице он не используется для оценки результата.", "Охоплення за днями не підсумовується як унікальне охоплення періоду, тому в таблиці воно не використовується для оцінки результату.")}
          </div>
        </>}

        {tab === "creatives" && <>
          {syncWarning}
          <div style={cardsRow}>
            {card(t("Подписчиков с рекламы", "Підписників з реклами"), "0", "#2563eb", t("кампании настроены на переписку, а не на подписку — платных подписок нет", "кампанії на листування, не на підписку"))}
            {card(t("Расход на рекламу", "Витрати на рекламу"), moneyUsd(paidSummary.spend), "#dc2626")}
            {card(t("Начатые диалоги", "Розпочаті діалоги"), count(paidSummary.messages_started), "#0f766e")}
          </div>
          <div className="note" style={{ marginBottom: 12 }}>
            {t("Каждая карточка — конкретное объявление. Миниатюра и ссылка помогают сразу увидеть, какой креатив дал диалоги и лиды.", "Кожна картка — конкретне оголошення. Мініатюра й посилання допомагають одразу побачити, який креатив дав діалоги та ліди.")}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 12 }}>
            {(paid.ads || []).map((r: any) => <AdCard key={r.id} row={r} t={t} />)}
            {!(paid.ads || []).length && <Empty text={t("Объявлений за период нет", "Оголошень за період немає")} />}
          </div>
        </>}

        {tab === "content" && <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: 10, marginBottom: 12 }}>
            {card(t("Подписчиков сейчас", "Підписників зараз"), count(followers.current_total), "#7c3aed")}
            {card(t("+ за период", "+ за період"), ((followers.period_gained || 0) >= 0 ? "+" : "") + count(followers.period_gained), (followers.period_gained || 0) >= 0 ? "#15803d" : "#dc2626")}
            {card(t("Публикаций", "Публікацій"), count(organic.length), "#0284c7")}
            {card(t("Суммарный охват", "Сумарне охоплення"), count(orgAgg.reach), "#2563eb")}
            {card(t("Средний ER", "Середній ER"), orgAgg.er ? orgAgg.er.toFixed(1) + "%" : "—", "#0f766e")}
          </div>
          <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
            <button className={orgView === "cards" ? "btn btn-primary" : "btn btn-light"} onClick={() => setOrgView("cards")} style={{ fontSize: 12.5 }}>🖼 {t("Карточки", "Картки")}</button>
            <button className={orgView === "table" ? "btn btn-primary" : "btn btn-light"} onClick={() => setOrgView("table")} style={{ fontSize: 12.5 }}>📋 {t("Таблица", "Таблиця")}</button>
            <button className={orgView === "account" ? "btn btn-primary" : "btn btn-light"} onClick={() => setOrgView("account")} style={{ fontSize: 12.5 }}>📈 {t("Рост кабинета", "Зростання кабінету")}</button>
          </div>
          <div className="note" style={{ marginBottom: 12, lineHeight: 1.5 }}>
            <b>{t("Только органика — без рекламы.", "Лише органіка — без реклами.")}</b> {t("«Подписки» Meta отдаёт не для всех форматов (для Reels — нет). Общий рост подписчиков смотри во вкладке «Рост кабинета».", "«Підписки» Meta віддає не для всіх форматів. Загальне зростання — у «Зростання кабінету».")}
          </div>
          {orgView === "cards" && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))", gap: 12 }}>
              {organic.map((r: any) => <ContentCard key={r.media_id} row={r} t={t} />)}
              {!organic.length && <Empty text={t("Органический контент за период не найден", "Органічний контент за період не знайдено")} />}
            </div>
          )}
          {orgView === "table" && table(
            [t("Дата", "Дата"), t("Тип", "Тип"), t("Публикация", "Публікація"), t("Охват", "Охоплення"), t("Просмотры", "Перегляди"), t("Лайки", "Лайки"), t("Комм.", "Комент."), t("Сохр.", "Збереж."), t("Репосты", "Репости"), t("Взаимод.", "Взаємодії"), "ER %", t("Подписки", "Підписки"), t("Лиды", "Ліди"), t("Сделки", "Угоди")],
            organic.map((r: any) => [
              r.published_at ? new Date(r.published_at).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }) : "—",
              r.media_product_type || r.media_type || "—",
              <a href={r.permalink} target="_blank" rel="noreferrer" style={{ color: "#2563eb", textDecoration: "none" }}>{(r.caption || "—").slice(0, 40)}</a>,
              count(r.reach), count(r.views), count(r.likes), count(r.comments), count(r.saved), count(r.shares), count(r.interactions),
              r.engagement_rate != null ? r.engagement_rate + "%" : "—",
              r.follows != null ? count(r.follows) : "—",
              r.crm_leads || 0, r.crm_deals || 0,
            ]),
            t("Органический контент за период не найден", "Органічний контент за період не знайдено"), 1100)}
          {orgView === "account" && <AccountGrowth followers={followers} organic={organic} t={t} />}
        </>}

        {tab === "funnel" && <>
          <MetaConeFunnel from={from} to={to} />
          <div className="note" style={{ marginBottom: 12, lineHeight: 1.5 }}>
            {t("Первая таблица показывает все реальные обращения Instagram и Facebook в CRM. «Точный ID рекламы» означает, что Meta передала идентификатор объявления/кампании/формы. «Не определено» — обращение пришло из Meta, но конкретное объявление технически не было передано.", "Перша таблиця показує всі реальні звернення Instagram і Facebook у CRM. «Точний ID реклами» означає, що Meta передала ідентифікатор оголошення/кампанії/форми. «Не визначено» — звернення прийшло з Meta, але конкретне оголошення технічно не було передано.")}
          </div>
          <SectionTitle title={t("Все обращения Meta в CRM", "Усі звернення Meta в CRM")} note={t("Не пропускает лиды без рекламного ID", "Не пропускає ліди без рекламного ID")} />
          {table([
            t("Воронка CRM", "Воронка CRM"), t("Стадия CRM", "Стадія CRM"), t("Лиды", "Ліди"), t("Сделки", "Угоди"),
            t("Точный ID рекламы", "Точний ID реклами"), t("Органика", "Органіка"), t("Источник не определён", "Джерело не визначене")],
            (data.all_meta_stages || []).map((r: any) => [r.funnel, r.stage, r.leads, r.deals, r.exact_paid_leads, r.organic_leads, r.unassigned_leads]),
            t("Обращений Meta за период нет", "Звернень Meta за період немає"), 1050)}
          <SectionTitle title={t("Только подтверждённая реклама", "Лише підтверджена реклама")} note={t("Консервативная воронка для точной атрибуции", "Консервативна воронка для точної атрибуції")} />
          {table([
            t("Воронка CRM", "Воронка CRM"), t("Стадия CRM", "Стадія CRM"), t("Событие Meta", "Подія Meta"), t("Лиды", "Ліди"), t("Сделки", "Угоди")],
            (data.stages || []).map((r: any) => [r.funnel, r.stage, r.meta_event, r.leads, r.deals]),
            t("Нет карточек с точным рекламным ID", "Немає карток із точним рекламним ID"))}
        </>}

        {tab === "forms" && table([
          t("Тип", "Тип"), t("Лиды", "Ліди"), t("Сделки", "Угоди"), t("Назначение", "Призначення")],
          (data.by_source_kind || []).filter((r: any) => r.source_kind === "lead_form").map((r: any) => [t("Лид-форма Meta", "Лід-форма Meta"), r.leads, r.deals, t("Автоматическое создание лида", "Автоматичне створення ліда")]),
          t("За период лид-формы не зафиксированы", "За період лід-форми не зафіксовані"))}

        {tab === "sources" && <>
          <div className="note" style={{ marginBottom: 12 }}>{t("Метка «Реклама подтверждена» ставится только когда в карточке есть стабильный ID объявления, кампании или лид-формы Meta. Если обращение пришло из Instagram/Facebook, но Meta не передала ID, CRM показывает «Источник объявления не определён» и не приписывает его конкретной рекламе.", "Позначка «Реклама підтверджена» ставиться лише коли в картці є стабільний ID оголошення, кампанії або лід-форми Meta. Якщо звернення прийшло з Instagram/Facebook, але Meta не передала ID, CRM показує «Джерело оголошення не визначене» і не приписує його конкретній рекламі.")}</div>
          {table([t("Платформа", "Платформа"), t("Лиды", "Ліди"), t("Сделки", "Угоди"), t("Успешные", "Успішні"), t("Выручка", "Виручка")],
            (data.by_platform || []).map((r: any) => [r.platform, r.leads, r.deals, r.won, moneyUah(r.revenue)]),
            t("Подтверждённых рекламных источников нет", "Підтверджених рекламних джерел немає"))}
          <SectionTitle title={t("Последние обращения Meta", "Останні звернення Meta")} note={t("По каждой карточке видно наличие рекламного идентификатора", "Для кожної картки видно наявність рекламного ідентифікатора")} />
          {table([
            t("Карточка", "Картка"), t("Платформа", "Платформа"), t("Атрибуция", "Атрибуція"),
            t("ID Meta", "ID Meta"), t("Воронка", "Воронка"), t("Стадия", "Стадія"), t("Создана", "Створена")],
            (data.recent || []).map((r: any) => [
              <div><b>{r.object_type === "lead" ? t("Лид", "Лід") : t("Сделка", "Угода")} #{r.id}</b><div className="muted" style={{ fontSize: 10 }}>{r.title}</div></div>,
              r.platform || "—",
              r.attribution_status === "exact_paid" ? <b style={{ color: "#15803d" }}>{t("Реклама подтверждена", "Реклама підтверджена")}</b>
                : r.attribution_status === "organic" ? <span style={{ color: "#7c3aed" }}>{t("Органика", "Органіка")}</span>
                  : <span style={{ color: "#d97706" }}>{t("Источник объявления не определён", "Джерело оголошення не визначене")}</span>,
              r.meta_identifier || "—", r.funnel, r.stage, dateTime(r.created_at),
            ]),
            t("Обращений Meta за период нет", "Звернень Meta за період немає"), 1200)}
        </>}

        <div className="panel" style={{ marginTop: 12, padding: 14, display: "flex", gap: 16, flexWrap: "wrap", fontSize: 12, alignItems: "center" }}>
          <b>{t("Состояние:", "Стан:")}</b>
          <span>{integration.insights_sync_configured ? "🟢" : "🟡"} Ads Insights</span>
          <span>{integration.content_sync_configured ? "🟢" : "🟡"} Instagram Content</span>
          <span>{integration.latest_account_sync ? "🟢" : "🟡"} Instagram Followers</span>
          <span>{integration.capi_enabled ? "🟢" : "⚪"} Conversions API</span>
          <span>{t("реклама обновлена", "реклама оновлена")}: {dateTime(integration.latest_ads_sync)}</span>
          <span>{t("органика обновлена", "органіка оновлена")}: {dateTime(integration.latest_content_sync)}</span>
          <span>{t("подписчики обновлены", "підписники оновлені")}: {dateTime(integration.latest_account_sync)}</span>
        </div>
      </>}
    </div>
  </div>;
}

function SectionTitle({ title, note }: { title: string; note: string }) {
  return <div style={{ margin: "14px 0 8px" }}><b style={{ fontSize: 16 }}>{title}</b><span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>{note}</span></div>;
}

function DailySalesTable({ rows, t }: { rows: any[]; t: (ru: string, ua: string) => string }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // Короткий заголовок + пояснення простими словами (тултип при наведенні).
  const headers = [
    { s: t("Дата", "Дата"), tip: t("День", "День") },
    { s: t("Подписчики", "Підписники"), tip: t("Сколько подписчиков всего на этот день", "Скільки підписників усього на цей день") },
    { s: t("Новые", "Нові"), tip: t("Сколько новых подписчиков прибавилось за день", "Скільки нових підписників додалося за день") },
    { s: t("Контент", "Контент"), tip: t("Сколько публикаций вышло за день", "Скільки публікацій вийшло за день") },
    { s: t("Реклама $", "Реклама $"), tip: t("Расход на рекламу за день, в долларах", "Витрати на рекламу за день, у доларах") },
    { s: t("Реклама ₴", "Реклама ₴"), tip: t("Расход на рекламу за день, в гривне (по курсу дня)", "Витрати на рекламу за день, у гривні (за курсом дня)") },
    { s: t("Диалоги", "Діалоги"), tip: t("Сколько переписок начал клиент с рекламы (по кабинету Meta)", "Скільки переписок почав клієнт з реклами (за кабінетом Meta)") },
    { s: t("Лиды", "Ліди"), tip: t("Сколько лидов с Meta попало в CRM за день", "Скільки лідів з Meta потрапило в CRM за день") },
    { s: t("С рекламой", "З рекламою"), tip: t("Лиды с точной меткой объявления — доказанная реклама", "Ліди з точною міткою оголошення — доведена реклама") },
    { s: t("Продажи", "Продажі"), tip: t("Сколько оплаченных продаж за день", "Скільки оплачених продажів за день") },
    { s: t("Повторные", "Повторні"), tip: t("Продажи клиентам, которые УЖЕ покупали основной продукт (тест-набор не считается)", "Продажі клієнтам, які ВЖЕ купували основний продукт (тест-набір не рахується)") },
    { s: t("Выручка", "Виручка"), tip: t("Сумма всех оплат за день", "Сума всіх оплат за день") },
    { s: t("Из них повторные", "З них повторні"), tip: t("Сколько из выручки — от повторных покупателей", "Скільки з виручки — від повторних покупців") },
    { s: "LTV", tip: t("Средняя сумма, которую приносит один клиент за всё время", "Середня сума, яку приносить один клієнт за весь час") },
    { s: t("Прибыль", "Прибуток"), tip: t("Выручка минус себестоимость — валовая прибыль", "Виручка мінус собівартість — валовий прибуток") },
    { s: "ROAS", tip: t("Сколько гривен вернулось на 1 грн рекламы (по кабинету Meta). Больше 1× — в плюс", "Скільки гривень повернулось на 1 грн реклами (за кабінетом Meta). Більше 1× — у плюс") },
    { s: "ROMI", tip: t("Окупаемость рекламы по подтверждённым продажам CRM. Больше 100% — в плюс", "Окупність реклами за підтвердженими продажами CRM. Більше 100% — у плюс") },
  ];
  const cw = useColWidths("mm_daily_cols", headers.length);
  const [pageSize, setPageSize] = useState<number>(() => { try { return Number(localStorage.getItem("mm_daily_pagesize") || "30") || 30; } catch { return 30; } });
  const [page, setPage] = useState(0);
  const total = rows.length;
  useEffect(() => { setPage(0); }, [total, pageSize]);
  const paged = pageSize >= 99999 ? rows : rows.slice(page * pageSize, page * pageSize + pageSize);
  const toggle = (date: string) => setExpanded((current) => {
    const next = new Set(current);
    if (next.has(date)) next.delete(date); else next.add(date);
    return next;
  });
  const values = (r: any): ReactNode[] => [
    optional(r.followers_total, "", t("снимок ещё не сохранён", "знімок ще не збережено")),
    r.followers_gained == null ? "—" : `${r.followers_gained > 0 ? "+" : ""}${count(r.followers_gained)}`,
    count(r.content_published), moneyUsd(r.spend), r.spend_uah == null ? "—" : moneyUah(r.spend_uah),
    count(r.messages_started), count(r.crm_meta_leads), count(r.exact_ad_leads), count(r.sales),
    count(r.repeat_sales), moneyUah(r.revenue), moneyUah(r.repeat_revenue), moneyUah(r.average_ltv),
    moneyUah(r.gross_profit), r.roas == null ? "—" : `${r.roas}×`, r.romi == null ? "—" : `${r.romi}%`,
  ];
  return <div className="panel" style={{ padding: 0 }}>
    <Pager total={total} pageSize={pageSize} page={page} sizeKey="mm_daily_pagesize" onSize={setPageSize} onPage={setPage} t={t} />
    {/* Прокрутка в межах блока фіксованої висоти: горизонтальний скрол видно ЗАВЖДИ
        внизу видимої області (а не в самому кінці довгої таблиці), шапка «прилипає». */}
    <div style={{ overflowX: "auto", overflowY: "auto", maxHeight: "calc(100vh - 240px)" }}>
    <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1400 }}>
      <colgroup>{headers.map((_, i) => <col key={i} style={cw.widths[i] ? { width: cw.widths[i] } : undefined} />)}</colgroup>
      <thead style={{ position: "sticky", top: 0, zIndex: 3 }}><tr>{headers.map((header, i) => <ResizableTh key={header.s} label={<Tip text={header.tip}>{header.s}<span style={{ opacity: .45, marginLeft: 3, fontSize: 10, fontWeight: 400 }}>ⓘ</span></Tip>} width={cw.widths[i]} onResize={(w) => cw.set(i, w)} thStyle={{ ...th, whiteSpace: "normal", wordBreak: "break-word", verticalAlign: "bottom", background: "#eef2f7" }} />)}</tr></thead>
      <tbody>{rows.length ? paged.map((r: any) => {
        const isOpen = expanded.has(r.date);
        return <Fragment key={r.date}>
          <tr style={{ background: isOpen ? "#f8fafc" : undefined }}>
            <td style={td}>
              <button
                type="button"
                aria-expanded={isOpen}
                aria-label={t(`Показать сделки за ${r.date}`, `Показати угоди за ${r.date}`)}
                onClick={() => toggle(r.date)}
                style={dayToggle}
              >
                <span style={{ width: 18, color: "#2563eb" }}>{isOpen ? "▾" : "▸"}</span>
                {new Date(`${r.date}T12:00:00`).toLocaleDateString("ru-RU")}
              </button>
            </td>
            {values(r).map((value, index) => <td key={index} style={td}>{value}</td>)}
          </tr>
          {isOpen && <tr>
            <td colSpan={headers.length} style={{ padding: 0, borderBottom: "1px solid #cbd5e1" }}>
              <div style={{ padding: "14px 16px 18px", background: "#f8fafc" }}>
                <div className="muted" style={{ fontSize: 11, marginBottom: 10 }}>
                  {t(
                    "Расшифровка ровно этой строки. Повторные сделки уже входят в общие продажи и выручку.",
                    "Розшифровка саме цього рядка. Повторні угоди вже входять у загальні продажі та виручку.",
                  )}
                </div>
                <DailyDealSection
                  title={t("Первичные оплаченные сделки", "Первинні оплачені угоди")}
                  rows={r.deals?.primary || []}
                  color="#15803d"
                  t={t}
                />
                <DailyDealSection
                  title={t("Повторные оплаченные сделки", "Повторні оплачені угоди")}
                  rows={r.deals?.repeat || []}
                  color="#0e7490"
                  t={t}
                />
              </div>
            </td>
          </tr>}
        </Fragment>;
      }) : <tr><td colSpan={headers.length} style={{ ...td, color: "#64748b", textAlign: "center", padding: 28 }}>{t("За период данных нет", "За період даних немає")}</td></tr>}</tbody>
    </table>
    </div>
    {total > pageSize && pageSize < 99999 && <Pager total={total} pageSize={pageSize} page={page} sizeKey="mm_daily_pagesize" onSize={setPageSize} onPage={setPage} t={t} />}
  </div>;
}

function DailyDealSection({ title, rows, color, t }: { title: string; rows: any[]; color: string; t: (ru: string, ua: string) => string }) {
  const sectionTotal = rows.reduce((sum, row) => sum + Number(row.paid_today || 0), 0);
  return <div style={{ marginTop: 10, border: "1px solid #e2e8f0", borderRadius: 10, background: "#fff", overflow: "hidden" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "10px 12px", background: "#f1f5f9", alignItems: "center" }}>
      <b style={{ color }}>{title}</b>
      <span style={{ fontWeight: 800, color }}>{count(rows.length)} · {moneyUah(sectionTotal)}</span>
    </div>
    {rows.length ? <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", minWidth: 1040, borderCollapse: "collapse" }}>
        <thead><tr>
          {[t("Сделка", "Угода"), t("Клиент", "Клієнт"), t("Воронка / стадия", "Воронка / стадія"), t("Менеджер", "Менеджер"), t("Способ оплаты", "Спосіб оплати"), t("Время", "Час"), t("Оплачено в этот день", "Сплачено цього дня"), t("Сумма сделки", "Сума угоди")].map((header) => <th key={header} style={{ ...th, padding: "8px 10px", fontSize: 11 }}>{header}</th>)}
        </tr></thead>
        <tbody>{rows.map((deal: any) => <tr key={deal.deal_id}>
          <td style={dealTd}><a href={`/deals/${deal.deal_id}`} style={{ color: "#2563eb", fontWeight: 750 }}>#{deal.deal_id} · {deal.title || t("Без названия", "Без назви")}</a>{deal.meta_attributed && <div style={{ color: "#7c3aed", fontSize: 10, marginTop: 2 }}>{t("Есть точный ID Meta", "Є точний ID Meta")}</div>}</td>
          <td style={dealTd}>{deal.contact_name || "—"}</td>
          <td style={dealTd}><b>{deal.funnel || "—"}</b><div className="muted" style={{ fontSize: 10, marginTop: 2 }}>{deal.stage || "—"}</div></td>
          <td style={dealTd}>{deal.manager || "—"}</td>
          <td style={dealTd}>
            {(deal.payment_methods || []).join(", ") || "—"}
            {Number(deal.payment_count || 0) > 1 && <div className="muted" style={{ fontSize: 10 }}>{t("платежей", "платежів")}: {deal.payment_count}</div>}
            {deal.historical_payment && <div style={{ color: "#64748b", fontSize: 10, marginTop: 2 }}>{t("Историческая оплата из финансов CRM", "Історична оплата з фінансів CRM")}</div>}
            {deal.inferred_payment_link && <div style={{ color: "#b45309", fontSize: 10, marginTop: 2 }}>{t("Связь восстановлена по дате и точной сумме", "Зв'язок відновлено за датою і точною сумою")}</div>}
          </td>
          <td style={dealTd}>{dateTime(deal.paid_at).split(", ").pop()}</td>
          <td style={{ ...dealTd, fontWeight: 850, color }}>{moneyUah(deal.paid_today)}</td>
          <td style={dealTd}>{moneyUah(deal.deal_amount)}{Number(deal.total_paid || 0) !== Number(deal.paid_today || 0) && <div className="muted" style={{ fontSize: 10 }}>{t("всего оплачено", "усього сплачено")}: {moneyUah(deal.total_paid)}</div>}</td>
        </tr>)}</tbody>
      </table>
    </div> : <div className="muted" style={{ padding: "12px", fontSize: 12 }}>{t("В этот день таких сделок нет", "Цього дня таких угод немає")}</div>}
  </div>;
}

function Thumb({ src, alt }: { src?: string; alt: string }) {
  return src ? <img src={src} alt={alt} loading="lazy" style={{ width: 82, height: 82, objectFit: "cover", borderRadius: 10, background: "#e2e8f0", flex: "0 0 82px" }} /> :
    <div style={{ width: 82, height: 82, borderRadius: 10, background: "#e2e8f0", display: "grid", placeItems: "center", fontSize: 28, flex: "0 0 82px" }}>🖼️</div>;
}

function AdCard({ row, t }: { row: any; t: (ru: string, ua: string) => string }) {
  return <div className="panel" style={{ padding: 13 }}>
    <div style={{ display: "flex", gap: 11 }}>
      <Thumb src={row.thumbnail_url} alt={row.name || "Meta ad"} />
      <div style={{ minWidth: 0 }}>
        <b style={{ display: "block", lineHeight: 1.3 }}>{row.name || row.id}</b>
        <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>{row.campaign_name || "—"}</div>
        <div className="muted" style={{ fontSize: 10 }}>{row.adset_name || "—"}</div>
        {row.permalink_url && <a href={row.permalink_url} target="_blank" rel="noreferrer" style={{ fontSize: 11 }}>{t("Открыть", "Відкрити")} ↗</a>}
      </div>
    </div>
    <div style={metricGrid}>
      <Metric label={t("Расход", "Витрати")} value={moneyUsd(row.spend)} />
      <Metric label={t("Диалоги Meta", "Діалоги Meta")} value={count(row.messages_started)} />
      <Metric label={t("Лиды Meta", "Ліди Meta")} value={count(row.meta_leads)} />
      <Metric label={t("Лиды CRM", "Ліди CRM")} value={count(row.crm_leads)} />
      <Metric label="CTR" value={row.ctr == null ? "—" : `${row.ctr}%`} />
      <Metric label={t("Цена диалога", "Ціна діалогу")} value={row.cost_per_message == null ? "—" : moneyUsd(row.cost_per_message)} />
    </div>
  </div>;
}

function ContentCard({ row, t }: { row: any; t: (ru: string, ua: string) => string }) {
  const type = row.media_product_type || row.media_type || "POST";
  const contentMetric = (value: any) => optional(value, "", t("нет данных", "немає даних"));
  return <div className="panel" style={{ padding: 13 }}>
    <div style={{ display: "flex", gap: 11 }}>
      <Thumb src={row.thumbnail_url} alt={type} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><b>{type}</b><span className="muted" style={{ fontSize: 10 }}>{dateTime(row.published_at)}</span></div>
        <div style={{ fontSize: 12, lineHeight: 1.35, marginTop: 5, display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{row.caption || t("Без подписи", "Без підпису")}</div>
        {row.permalink && <a href={row.permalink} target="_blank" rel="noreferrer" style={{ fontSize: 11 }}>{t("Открыть публикацию", "Відкрити публікацію")} ↗</a>}
      </div>
    </div>
    <div style={metricGrid}>
      <Metric label={t("Охват", "Охоплення")} value={contentMetric(row.reach)} />
      <Metric label={t("Просмотры", "Перегляди")} value={contentMetric(row.views)} />
      <Metric label={t("Лайки", "Вподобання")} value={count(row.likes)} />
      <Metric label={t("Комментарии", "Коментарі")} value={count(row.comments)} />
      <Metric label={t("Сохранения", "Збереження")} value={contentMetric(row.saved)} />
      <Metric label={t("Поделились", "Поширення")} value={contentMetric(row.shares)} />
      <Metric label={t("Подписчики", "Підписники")} value={contentMetric(row.follows)} accent />
      <Metric label={t("Визиты профиля", "Візити профілю")} value={contentMetric(row.profile_visits)} />
      <Metric label={t("Вовлечённость", "Залученість")} value={row.engagement_rate == null ? "—" : `${row.engagement_rate}%`} />
      <Metric label={t("Диалоги CRM", "Діалоги CRM")} value={count(row.crm_dialogues)} />
    </div>
    <div className="muted" style={{ fontSize: 9, marginTop: 8 }}>{t("Обновлено", "Оновлено")}: {dateTime(row.synced_at)}</div>
  </div>;
}

function Metric({ label, value, accent = false }: { label: string; value: ReactNode; accent?: boolean }) {
  return <div style={{ background: accent ? "#ecfdf5" : "#f8fafc", borderRadius: 8, padding: "7px 8px" }}>
    <div className="muted" style={{ fontSize: 9 }}>{label}</div>
    <div style={{ fontSize: 13, fontWeight: 800, color: accent ? "#047857" : "#0f172a", marginTop: 2 }}>{value}</div>
  </div>;
}

function Empty({ text }: { text: string }) {
  return <div className="panel muted" style={{ padding: 28, textAlign: "center", gridColumn: "1 / -1" }}>{text}</div>;
}

const cardsRow: any = { display: "flex", gap: 9, flexWrap: "wrap", marginBottom: 10 };
const metricGrid: any = { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 6, marginTop: 12 };
const th: any = { textAlign: "left", padding: "10px 12px", fontSize: 12, color: "#64748b", borderBottom: "2px solid #e2e8f0", whiteSpace: "nowrap" };
const td: any = { padding: "10px 12px", fontSize: 13, borderBottom: "1px solid #eef2f7", verticalAlign: "top" };
const dealTd: any = { padding: "9px 10px", fontSize: 12, borderTop: "1px solid #eef2f7", verticalAlign: "top" };
const dayToggle: any = { minHeight: 36, padding: "0 8px 0 0", border: 0, background: "transparent", color: "#0f172a", fontWeight: 750, cursor: "pointer", display: "inline-flex", alignItems: "center", whiteSpace: "nowrap", textAlign: "left" };
const dateLabel: any = { display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#64748b" };
const dateInput: any = { height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px", background: "#fff" };
