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
const TAB_KEYS = ["overview", "profitability", "ads", "creatives", "content", "funnel", "pixel", "forms", "sources"] as const;
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

/* ─── События · Пиксель: что CRM отправила в Meta (статусы переписок) ─── */
function PixelEventsTab({ from, to }: { from: string; to: string }) {
  const { t } = useLang();
  const [px, setPx] = useState<"crm" | "site">("crm");
  const [d, setD] = useState<any>(null);
  const [sortKey, setSortKey] = useState<string>("at");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [fStage, setFStage] = useState("");
  const [fEvent, setFEvent] = useState("");
  const [pg, setPg] = useState(0);
  useEffect(() => { setPg(0); }, [fStage, fEvent, sortKey, sortDir, from, to]);
  useEffect(() => { setD(null); api.get<any>(`/api/meta-marketing/pixel-events/?from=${from}&to=${to}` + (px === "site" ? "&pixel=site" : "")).then(setD).catch(() => setD({ error: true })); }, [from, to, px]);
  if (d && d.error) return <div className="muted" style={{ padding: 20 }}>{t("Не удалось загрузить", "Не вдалося завантажити")}</div>;
  const sm = (d && d.summary) || {};
  const EV_LABEL: any = {
    LeadSubmitted: t("Лид (заявка)", "Лід (заявка)"), QualifiedLead: t("Квалифицированный лид", "Кваліфікований лід"),
    ViewContent: t("Просмотр предложения (КП)", "Перегляд пропозиції (КП)"), InitiateCheckout: t("Договорились об оплате", "Домовились про оплату"),
    Purchase: t("Оплачено", "Оплачено"), OrderCreated: t("Размещен заказ", "Розміщено замовлення"),
    OrderShipped: t("Отправлено", "Відправлено"), OrderDelivered: t("Доставлено", "Доставлено"),
    OrderCanceled: t("Отменено", "Скасовано"), Lead: t("Лид (старый формат)", "Лід (старий формат)"),
    Contact: t("Контакт (старый формат)", "Контакт (старий формат)"),
  };
  const maxDay = Math.max(...((d && d.daily) || []).map((x: any) => (x.sent || 0) + (x.pending || 0) + (x.failed || 0)), 1);
  const cardsRow: any = { display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14 };
  const card = (label: string, value: ReactNode, color = "#0f172a", hint?: string) => (
    <div className="panel" style={{ padding: "9px 11px", minWidth: 124, flex: "1 1 124px", margin: 0 }}>
      <div className="muted" style={{ fontSize: 10.5, lineHeight: 1.25 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 800, color, marginTop: 2 }}>{value}</div>
      {hint && <div className="muted" style={{ fontSize: 9.5, marginTop: 3, lineHeight: 1.25 }}>{hint}</div>}
    </div>
  );
  const table = (headers: string[], rows: ReactNode[][], empty: string, minWidth = 760) => (
    <ResizableTable headers={headers} rows={rows} empty={empty} minWidth={minWidth}
      storageKey={"mm_px_" + headers.length} />
  );
  const SITE_EV: any = {
    PageView: t("Открыл страницу сайта", "Відкрив сторінку сайту"),
    ViewContent: t("Просмотр контента", "Перегляд контенту"),
    Lead: t("Заявка с сайта", "Заявка з сайту"),
    Purchase: t("Покупка", "Покупка"),
    QuizStart: t("Начал квиз", "Почав квіз"),
    QuizMaterialPhotoViewed: t("Смотрел фото материалов (квиз)", "Дивився фото матеріалів (квіз)"),
    QuizSilkSelected: t("Выбрал шёлк (квиз)", "Обрав шовк (квіз)"),
    QuizVelvetSelected: t("Выбрал бархат (квиз)", "Обрав оксамит (квіз)"),
    QuizVelvetColorSelected: t("Выбрал цвет бархата (квиз)", "Обрав колір оксамиту (квіз)"),
    VelvetColorPreviewed: t("Смотрел цвета бархата", "Дивився кольори оксамиту"),
    VelvetColorConfirmed: t("Подтвердил цвет", "Підтвердив колір"),
    VelvetGallerySlide: t("Листал галерею (бархат)", "Гортав галерею (оксамит)"),
    SilkGallerySlide: t("Листал галерею (шёлк)", "Гортав галерею (шовк)"),
  };
  const pxTabs = (
    <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
      <button className={px === "crm" ? "btn btn-primary" : "btn btn-light"} onClick={() => setPx("crm")} style={{ fontSize: 12.5 }}>💬 {t("Переписки (CRM → Meta)", "Листування (CRM → Meta)")}</button>
      <button className={px === "site" ? "btn btn-primary" : "btn btn-light"} onClick={() => setPx("site")} style={{ fontSize: 12.5 }}>🌐 {t("Пиксель сайта (лендинг)", "Піксель сайту (лендінг)")}</button>
    </div>
  );
  if (px === "site") {
    const sm2 = d?.summary || {};
    const maxD2 = Math.max(...((d?.daily || []).map((x: any) => x.total || 0)), 1);
    return (<>
      {pxTabs}
      <div className="note" style={{ marginBottom: 12, lineHeight: 1.5 }}>
        {t("Это события с САЙТА (лендинга): что люди делали на страницах — открывали, проходили квиз, выбирали цвета. Их шлёт пиксель, установленный на сайте («Пиксель Лендинг новый»). Данные из Meta, обновляются ~раз в 5 минут.", "Це події з САЙТУ (лендінгу): що люди робили на сторінках. Їх шле піксель, встановлений на сайті. Дані з Meta.")}
      </div>
      {!d ? <div className="muted" style={{ padding: 20 }}>…</div> : d.error ? <div className="muted" style={{ padding: 20 }}>{t("Ошибка загрузки из Meta:", "Помилка завантаження з Meta:")} {d.error}</div> : (<>
        <div style={cardsRow}>
          {card(t("Всего событий", "Всього подій"), count(sm2.total), "#0f172a")}
          {card(t("Открытий страниц", "Відкриттів сторінок"), count(sm2.pageviews), "#2563eb")}
          {card(t("Типов событий", "Типів подій"), count(sm2.types), "#7c3aed")}
        </div>
        {table([t("Событие", "Подія"), t("Что означает", "Що означає"), t("Сколько раз", "Скільки разів")],
          (d.by_event || []).map((r: any) => [r.event_name, SITE_EV[r.event_name] || "—", <b>{count(r.total)}</b>]),
          t("Событий с сайта за период нет", "Подій із сайту за період немає"), 640)}
        <SectionTitle title={t("По дням", "По днях")} note={t("Активность на сайте", "Активність на сайті")} />
        <div className="panel">
          <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 110, overflowX: "auto" }}>
            {(d.daily || []).map((x: any) => (
              <div key={x.d} style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 30, flex: 1 }} title={`${x.d}: ${x.total}`}>
                <span style={{ fontSize: 10, color: "#334155", fontWeight: 700 }}>{x.total}</span>
                <div style={{ width: "70%", maxWidth: 24, height: Math.max((x.total / maxD2) * 74, 2), background: "#2563eb", borderRadius: "4px 4px 0 0" }} />
                <span style={{ fontSize: 9, color: "#94a3b8", whiteSpace: "nowrap" }}>{String(x.d).slice(5)}</span>
              </div>
            ))}
          </div>
        </div>
      </>)}
    </>);
  }
  if (!d) return (<>{pxTabs}<div className="muted" style={{ padding: 20 }}>…</div></>);
  return (<>
    {pxTabs}
    <div className="note" style={{ marginBottom: 12, lineHeight: 1.5 }}>
      {t("Это события, которые CRM отправляет в пиксель Meta по стадиям сделок (Лид → Оплачено → Отправлено). По ним Meta ставит ярлыки в переписках Direct и учится находить платящих клиентов.", "Це події, які CRM відправляє в піксель Meta за стадіями угод. За ними Meta ставить ярлики в Direct і вчиться знаходити платників.")}
    </div>
    <div style={cardsRow}>
      {card(t("Всего событий", "Всього подій"), count(sm.total), "#0f172a")}
      {card(t("Отправлено ✅", "Відправлено ✅"), count(sm.sent), "#15803d")}
      {card(t("В очереди", "У черзі"), count(sm.pending), sm.pending ? "#a16207" : "#94a3b8", t("уйдут автоматически (раз в 10 минут)", "підуть автоматично"))}
      {card(t("Ошибки", "Помилки"), count(sm.failed), sm.failed ? "#dc2626" : "#94a3b8")}
      {card(t("С привязкой к переписке", "З привʼязкою до листування"), `${sm.bm_pct}%`, "#7c3aed", t("сопоставлены по номеру переписки (IGSID) — Meta их точно узнаёт", "зіставлені за номером листування (IGSID)"))}
    </div>
    <SectionTitle title={t("По типам событий", "За типами подій")} note={t("Что именно отправили за период", "Що саме відправили за період")} />
    {table([t("Событие", "Подія"), t("Что означает", "Що означає"), t("Всего", "Всього"), t("Отправлено", "Відправлено"), t("В очереди", "У черзі"), t("Ошибки", "Помилки")],
      (d.by_event || []).map((r: any) => [
        r.event_name, EV_LABEL[r.event_name] || "—", r.total,
        <b style={{ color: "#15803d" }}>{r.sent}</b>, r.pending || 0,
        r.failed ? <b style={{ color: "#dc2626" }}>{r.failed}</b> : 0,
      ]), t("За период событий нет", "За період подій немає"), 700)}
    <SectionTitle title={t("По дням", "По днях")} note={t("Сколько событий уходило в Meta каждый день", "Скільки подій йшло в Meta щодня")} />
    <div className="panel" style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 120, overflowX: "auto" }}>
        {(d.daily || []).map((x: any) => {
          const tot = (x.sent || 0) + (x.pending || 0) + (x.failed || 0);
          return <div key={x.d} style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 30, flex: 1 }} title={`${x.d}: ✅${x.sent} ⏳${x.pending || 0} ❌${x.failed || 0}`}>
            <span style={{ fontSize: 10, color: "#334155", fontWeight: 700 }}>{tot}</span>
            <div style={{ width: "70%", maxWidth: 24, height: Math.max((tot / maxDay) * 84, 2), background: (x.failed || 0) > 0 ? "linear-gradient(180deg,#dc2626,#15803d)" : "#15803d", borderRadius: "4px 4px 0 0" }} />
            <span style={{ fontSize: 9, color: "#94a3b8", whiteSpace: "nowrap" }}>{String(x.d).slice(5)}</span>
          </div>;
        })}
      </div>
    </div>
    <SectionTitle title={t("Последние события", "Останні події")} note={t("Клик по заголовку столбца — сортировка; фильтры по стадии и событию", "Клік по заголовку — сортування; фільтри за стадією та подією")} />
    {(() => {
      const rows: any[] = d.recent || [];
      const stages = Array.from(new Set(rows.map((r) => r.stage).filter(Boolean))).sort();
      const events = Array.from(new Set(rows.map((r) => r.event).filter(Boolean))).sort();
      let list = rows.filter((r) => (!fStage || r.stage === fStage) && (!fEvent || r.event === fEvent));
      const val = (r: any, k: string) => (k === "at" ? r.at : String(r[k] ?? ""));
      list = list.slice().sort((a, b) => val(a, sortKey).localeCompare(val(b, sortKey), "uk") * sortDir);
      const PAGE = 20;
      const pages = Math.max(1, Math.ceil(list.length / PAGE));
      const cur = Math.min(pg, pages - 1);
      const slice = list.slice(cur * PAGE, cur * PAGE + PAGE);
      const hdr = (key: string, label: string) => (
        <th key={key} onClick={() => { if (sortKey === key) setSortDir((x) => (x === 1 ? -1 : 1)); else { setSortKey(key); setSortDir(key === "at" ? -1 : 1); } }}
          style={{ textAlign: "left", padding: "8px 10px", fontSize: 11.5, color: sortKey === key ? "#0f172a" : "#64748b", cursor: "pointer", userSelect: "none", whiteSpace: "nowrap", borderBottom: "2px solid #e2e8f0", background: "#f8fafc" }}>
          {label}{sortKey === key ? (sortDir === 1 ? " ▲" : " ▼") : ""}
        </th>
      );
      return (<div className="panel" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", padding: "10px 12px" }}>
          <select value={fStage} onChange={(e) => setFStage(e.target.value)} style={{ height: 30, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 12.5, background: "#fff" }}>
            <option value="">{t("— все стадии —", "— всі стадії —")}</option>
            {stages.map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
          <select value={fEvent} onChange={(e) => setFEvent(e.target.value)} style={{ height: 30, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 12.5, background: "#fff" }}>
            <option value="">{t("— все события —", "— всі події —")}</option>
            {events.map((x) => <option key={x} value={x}>{EV_LABEL[x] || x}</option>)}
          </select>
          <span className="muted" style={{ fontSize: 12 }}>{t("найдено", "знайдено")}: <b>{list.length}</b></span>
          <span style={{ marginLeft: "auto", display: "inline-flex", gap: 6, alignItems: "center" }}>
            <button className="btn btn-light" style={{ padding: "2px 10px" }} disabled={cur === 0} onClick={() => setPg(cur - 1)}>‹</button>
            <span className="muted" style={{ fontSize: 12 }}>{cur + 1} / {pages}</span>
            <button className="btn btn-light" style={{ padding: "2px 10px" }} disabled={cur >= pages - 1} onClick={() => setPg(cur + 1)}>›</button>
          </span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 820, fontSize: 13 }}>
            <thead><tr>
              {hdr("at", t("Когда", "Коли"))}
              {hdr("contact", t("Клиент", "Клієнт"))}
              {hdr("stage", t("Стадия CRM", "Стадія CRM"))}
              {hdr("event", t("Событие", "Подія"))}
              {hdr("channel", t("Канал", "Канал"))}
              {hdr("status", t("Статус", "Статус"))}
            </tr></thead>
            <tbody>
              {slice.map((r: any, i: number) => (
                <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                  <td style={{ padding: "7px 10px", whiteSpace: "nowrap" }}>{r.at}</td>
                  <td style={{ padding: "7px 10px" }}><a href={`/${r.object_type === "lead" ? "leads" : "deals"}/${r.object_id}`} style={{ color: "#2563eb", textDecoration: "none" }}>{r.contact}</a></td>
                  <td style={{ padding: "7px 10px" }}>{r.stage}</td>
                  <td style={{ padding: "7px 10px" }}>{EV_LABEL[r.event] || r.event}</td>
                  <td style={{ padding: "7px 10px" }}>{r.channel}</td>
                  <td style={{ padding: "7px 10px" }}>{r.status === "sent" ? <b style={{ color: "#15803d" }}>✅ {t("отправлено", "відправлено")}</b>
                    : r.status === "pending" ? <span style={{ color: "#a16207" }}>⏳ {t("в очереди", "у черзі")}</span>
                    : <b style={{ color: "#dc2626" }}>❌ {r.status}</b>}</td>
                </tr>
              ))}
              {!slice.length && <tr><td colSpan={6} style={{ padding: 22, textAlign: "center", color: "#64748b" }}>{t("Событий нет", "Подій немає")}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>);
    })()}
  </>);
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
    api.get<any>(`/api/meta-marketing/?from=${from}&to=${to}` + (refreshKey ? `&fresh=1` : ""))
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
    { key: "pixel", ru: "События · Пиксель", ua: "Події · Піксель" },
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

  /* UI v3 «таблиця показників»: назва ліворуч — значення праворуч, у кілька колонок.
     Максимально компактно: усе видно без прокрутки. Пояснення — тултип Tip на наведення (ⓘ),
     НЕ нативний title (нативний не видно при демонстрації екрана). */
  const card = (label: string, value: ReactNode, color = "#0f172a", hint?: string) => (
    <div style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "5px 2px", borderBottom: "1px dashed #eef2f7", minWidth: 0 }}>
      <span style={{ fontSize: 11.5, color: "#475569", fontWeight: 600, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {hint ? <Tip text={hint}>{label} <span style={{ color: "#94a3b8", fontSize: 9.5 }}>ⓘ</span></Tip> : label}
      </span>
      <b style={{ fontSize: 14.5, fontWeight: 800, color, whiteSpace: "nowrap", flexShrink: 0 }}>{value}</b>
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
    count(r.instagram_follows), r.cost_per_instagram_follow == null ? "—" : moneyUsd(r.cost_per_instagram_follow),
    count(r.messages_started), count(r.meta_leads), count(r.crm_leads), r.cost_per_message == null ? "—" : moneyUsd(r.cost_per_message),
  ]);
  const dailyTable = <DailySalesTable rows={daily} t={t} />;
  // похідні показники реклами: ціни за клік / ліда (дзеркало Ads Manager простими словами)
  const cpcUsd = paidSummary.clicks ? paidSummary.spend / paidSummary.clicks : null;
  const cplUah = (paidSummary.spend_uah && summary.meta_origin_leads) ? paidSummary.spend_uah / summary.meta_origin_leads : null;
  const cplExactUah = (paidSummary.spend_uah && summary.attributed_leads) ? paidSummary.spend_uah / summary.attributed_leads : null;

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
          <SectionTitle title={t("Подписчики Instagram", "Підписники Instagram") + (followers.username ? " · @" + followers.username : "")} note={t("Всё о подписчиках в одном блоке: сколько есть, сколько пришло за период и почём", "Все про підписників в одному блоці: скільки є, скільки прийшло за період і почому")} />
          <div style={cardsRow}>
            {card(t("Подписчиков сейчас", "Підписників зараз"), optional(followers.current_total, "", t("ожидает синхронизации", "очікує синхронізації")), "#c026d3")}
            {card(t("Новых за период (итог)", "Нових за період (підсумок)"), followers.period_gained == null ? "—" : (followers.period_gained >= 0 ? "+" : "") + count(followers.period_gained), "#db2777", t("подписались минус отписались за выбранный период", "підписалися мінус відписалися за вибраний період"))}
            {card(t("С рекламы (платно)", "З реклами (платно)"), followers.paid_report_rows ? count(followers.paid_from_ads) : "—", "#2563eb", t("Из ежедневного отчёта Ads Manager: только подписки, которые Meta отнесла к рекламе.", "З щоденного звіту Ads Manager: лише підписки, які Meta віднесла до реклами."))}
            {card(t("Органика (остальные)", "Органіка (решта)"), followers.organic_other == null ? "—" : count(followers.organic_other), "#7c3aed", t("Итоговый прирост кабинета минус подписки с рекламы. Для Reels Meta отдельные подписки не отдаёт.", "Підсумковий приріст кабінету мінус підписки з реклами. Для Reels Meta окремі підписки не віддає."))}
            {card(t("Цена подписчика", "Ціна підписника"), paidSummary.cost_per_instagram_follow == null ? "—" : moneyUsd(paidSummary.cost_per_instagram_follow), "#0f766e", t("расход рекламы ÷ подписки с рекламы из отчёта Ads Manager", "витрати реклами ÷ підписки з реклами зі звіту Ads Manager"))}
            {card(t("Цена подписчика, ₴", "Ціна підписника, ₴"), (paidSummary.spend_uah && paidSummary.instagram_follows) ? moneyUah(paidSummary.spend_uah / paidSummary.instagram_follows) : "—", "#0f766e", t("расход в гривне ÷ подписки с рекламы", "витрати у гривні ÷ підписки з реклами"))}
            {card(t("Публикаций за период", "Публікацій за період"), count(daily.reduce((sum: number, r: any) => sum + Number(r.content_published || 0), 0)), "#7c3aed")}
          </div>
          <SectionTitle title={t("Лиды из Meta в CRM", "Ліди з Meta у CRM")} note={t("Сколько людей с Meta-каналов попало в CRM за период", "Скільки людей з Meta-каналів потрапило в CRM за період")} />
          <div style={cardsRow}>
            {card(t("Все лиды CRM из Meta", "Усі ліди CRM з Meta"), count(summary.meta_origin_leads), "#0284c7")}
            {card(t("С точным ID рекламы", "З точним ID реклами"), count(summary.attributed_leads), "#2563eb")}
            {card(t("Источник объявления не определён", "Джерело оголошення не визначене"), count(summary.meta_unassigned_leads), "#d97706")}
          </div>
          <SectionTitle title={t("Платная реклама Meta", "Платна реклама Meta")} note={t("Данные Ads Manager за выбранный период", "Дані Ads Manager за вибраний період")} />
          <div style={cardsRow}>
            {card(t("Расход", "Витрати"), moneyUsd(paidSummary.spend), "#dc2626")}
            {card(t("Подписки с рекламы", "Підписки з реклами"), followers.paid_report_rows ? count(paidSummary.instagram_follows) : "—", "#2563eb", t("Из ежедневного отчёта Ads Manager", "З щоденного звіту Ads Manager"))}
            {card(t("Цена подписчика", "Ціна підписника"), paidSummary.cost_per_instagram_follow == null ? "—" : moneyUsd(paidSummary.cost_per_instagram_follow), "#0f766e")}
            {card(t("Расход в гривне (НБУ)", "Витрати у гривні (НБУ)"), paidSummary.spend_uah == null ? "—" : moneyUah(paidSummary.spend_uah), "#dc2626", t("официальный курс НБУ на каждый день", "офіційний курс НБУ на кожен день"))}
            {card(t("Показы", "Покази"), count(paidSummary.impressions), "#2563eb")}
            {card(t("Клики", "Кліки"), count(paidSummary.clicks), "#7c3aed")}
            {card("CTR", optional(paidSummary.ctr, "%"), "#7c3aed")}
            {card(t("Цена клика (CPC)", "Ціна кліку (CPC)"), cpcUsd == null ? "—" : moneyUsd(cpcUsd), "#0891b2", t("расход ÷ клики", "витрати ÷ кліки"))}
            {card("CPM", optional(paidSummary.cpm), "#0891b2", t("цена 1000 показов, $", "ціна 1000 показів, $"))}
            {card(t("Начатые диалоги по Ads Manager", "Розпочаті діалоги за Ads Manager"), count(paidSummary.messages_started), "#0f766e", t("Это показатель рекламы Meta, а не продажи и не уникальные лиды CRM", "Це показник реклами Meta, а не продажі й не унікальні ліди CRM"))}
            {card(t("Цена диалога", "Ціна діалогу"), paidSummary.cost_per_message == null ? "—" : moneyUsd(paidSummary.cost_per_message), "#0f766e", t("расход рекламы ÷ начатые диалоги", "витрати реклами ÷ розпочаті діалоги"))}
            {card(t("Цена диалога, ₴", "Ціна діалогу, ₴"), (paidSummary.spend_uah && paidSummary.messages_started) ? moneyUah(paidSummary.spend_uah / paidSummary.messages_started) : "—", "#0f766e", t("расход в гривне ÷ начатые диалоги", "витрати у гривні ÷ розпочаті діалоги"))}
            {card(t("Лиды Meta", "Ліди Meta"), count(paidSummary.meta_leads), "#0f766e")}
            {card(t("Цена лида (все из Meta)", "Ціна ліда (всі з Meta)"), cplUah == null ? "—" : moneyUah(cplUah), "#b45309", t("расход в грн ÷ все лиды CRM из Meta", "витрати грн ÷ усі ліди CRM з Meta"))}
            {card(t("Цена лида (с точным ID)", "Ціна ліда (з точним ID)"), cplExactUah == null ? "—" : moneyUah(cplExactUah), "#d97706", t("расход в грн ÷ лиды с подтверждённой рекламой", "витрати грн ÷ ліди з підтвердженою рекламою"))}
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
            {card(t("Из выручки — повторные", "З виручки — повторні"), moneyUah(profitability.repeat_revenue), "#0e7490", t("часть общей выручки, не прибавлять второй раз", "частина загальної виручки, не додавати вдруге"))}
            {card(t("Средний LTV", "Середній LTV"), moneyUah(profitability.average_ltv), "#7c3aed", t("сколько в среднем приносит один покупатель", "скільки в середньому приносить один покупець"))}
            {card(t("Цена клиента", "Ціна клієнта"), (profitability.buyers > 0 && paidSummary.spend) ? "$" + (paidSummary.spend / profitability.buyers).toFixed(2) : "—", "#dc2626", t("расход рекламы ÷ покупателей", "витрати реклами ÷ покупців"))}
            {card(t("Цена продажи", "Ціна продажу"), (paidSummary.spend_uah && profitability.sales) ? moneyUah(paidSummary.spend_uah / profitability.sales) : "—", "#dc2626", t("расход рекламы в грн ÷ все продажи периода", "витрати реклами в грн ÷ усі продажі періоду"))}
            {card(t("Реклама по курсу НБУ", "Реклама за курсом НБУ"), profitability.ad_spend_uah == null ? "—" : moneyUah(profitability.ad_spend_uah), "#dc2626")}
            {card(t("Прибыль после рекламы", "Прибуток після реклами"), profitability.marketing_profit == null ? "—" : moneyUah(profitability.marketing_profit), Number(profitability.marketing_profit) >= 0 ? "#15803d" : "#dc2626", t("валовая прибыль − реклама", "валовий прибуток − реклама"))}
            {card(t("Общий ROAS", "Загальний ROAS"), profitability.blended_roas == null ? "—" : `${profitability.blended_roas}×`, "#2563eb", t("вся выручка ÷ реклама (blended)", "вся виручка ÷ реклама (blended)"))}
            {card(t("ROAS с точным ID", "ROAS з точним ID"), profitability.exact_ad_roas == null ? "—" : `${profitability.exact_ad_roas}×`, "#7c3aed", t("только доказанная связь с объявлением; «—» = таких продаж пока нет", "лише доведений звʼязок з оголошенням; «—» = таких продажів поки немає"))}
            {card("ROMI", profitability.romi == null ? "—" : `${profitability.romi}%`, Number(profitability.romi) >= 0 ? "#15803d" : "#dc2626", t("(валовая прибыль − реклама) ÷ реклама", "(валовий прибуток − реклама) ÷ реклама"))}
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
            t("Расход", "Витрати"), t("Показы", "Покази"), t("Клики", "Кліки"), "CTR", t("Подписки", "Підписки"), t("Цена подписки", "Ціна підписки"), t("Диалоги Meta", "Діалоги Meta"), t("Лиды Meta", "Ліди Meta"), t("Лиды CRM", "Ліди CRM"), t("Цена диалога", "Ціна діалогу"),
          ], adRows, t("За выбранный период реклама не показывалась", "За вибраний період реклама не показувалась"), 1300)}
          <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
            {t("Охват по дням не суммируется как уникальный охват периода, поэтому в таблице он не используется для оценки результата.", "Охоплення за днями не підсумовується як унікальне охоплення періоду, тому в таблиці воно не використовується для оцінки результату.")}
          </div>
        </>}

        {tab === "creatives" && <>
          {syncWarning}
          {(() => { const c = data.attribution_coverage || {}; const m = c.messenger_leads || 0; const g = c.tagged_leads || 0;
            const pct = m ? Math.round(g * 100 / m) : 0;
            return m > 0 ? <div className="note" style={{ marginBottom: 10, background: pct < 60 ? "#fff7ed" : "#f0fdf4", borderLeft: "3px solid " + (pct < 60 ? "#f59e0b" : "#16a34a") }}>
              <b>{t("Метка объявления долетает до", "Мітка оголошення долітає до")} {pct}% {t("лидов", "лідів")}</b> ({g} {t("из", "з")} {m} {t("лидов из мессенджеров за период", "лідів з месенджерів за період")}).{" "}
              {c.since && <b style={{ color: "#0f766e" }}>{t("Метки работают с", "Мітки працюють з")} {c.since} — {t("за более ранние периоды привязки к объявлениям нет.", "за раніші періоди привʼязки до оголошень немає.")} </b>}
              {t("Остальные тоже в CRM — просто без привязки к конкретному объявлению: метку передаёт только прямой канал Meta, через ChatPlace её нет. Значит реальный результат рекламы ВЫШЕ, чем показано в карточках ниже.", "Решта теж у CRM — просто без привʼязки до конкретного оголошення: мітку передає лише прямий канал Meta, через ChatPlace її немає. Отже реальний результат реклами ВИЩИЙ, ніж показано нижче.")}
            </div> : null; })()}
          <div style={cardsRow}>
            {card(t("Подписчиков с рекламы", "Підписників з реклами"), followers.paid_report_rows ? count(paidSummary.instagram_follows) : "—", "#2563eb", t("Из ежедневного отчёта Ads Manager. В таблице «Объявления» видно, какое объявление их привело.", "З щоденного звіту Ads Manager. У таблиці «Оголошення» видно, яке оголошення їх привело."))}
            {card(t("Расход на рекламу", "Витрати на рекламу"), moneyUsd(paidSummary.spend), "#dc2626")}
            {card(t("Начатые диалоги", "Розпочаті діалоги"), count(paidSummary.messages_started), "#0f766e")}
          </div>
          <div className="note" style={{ marginBottom: 12 }}>
            <b>{t("Каждая карточка — одно объявление.", "Кожна картка — одне оголошення.")}</b> {t("Наведи на название показателя (значок ⓘ) — появится объяснение простыми словами.", "Наведи на назву показника (значок ⓘ) — з'явиться пояснення простими словами.")}
            <div style={{ marginTop: 6, lineHeight: 1.55 }}>
              {t("Почему «Диалоги» больше «Лидов CRM»: Meta записывает объявлению ВСЕХ, кто написал в течение 7 дней после клика (даже через профиль, даже старых клиентов). А метку с названием объявления Instagram передаёт ТОЛЬКО тем, кто нажал кнопку прямо в рекламе. Все люди в CRM есть — просто у части не написано, с какого они объявления.", "Чому «Діалоги» більші за «Ліди CRM»: Meta записує оголошенню ВСІХ, хто написав протягом 7 днів після кліку (навіть через профіль, навіть старих клієнтів). А мітку з назвою оголошення Instagram передає ТІЛЬКИ тим, хто натиснув кнопку прямо в рекламі. Всі люди в CRM є — просто у частини не написано, з якого вони оголошення.")}<br />
              • {t("сравнивай креативы МЕЖДУ СОБОЙ — у кого дешевле диалог и больше привязанных лидов, тот и лучше", "порівнюй креативи МІЖ СОБОЮ — у кого дешевший діалог і більше привʼязаних лідів, той і кращий")}<br />
              • {t("расход идёт, а диалогов нет — креатив не работает, менять", "витрати йдуть, а діалогів немає — креатив не працює, міняти")}<br />
              • {t("Подсветка:", "Підсвітка:")} <span style={{ color: "#047857", fontWeight: 700 }}>{t("зелёный", "зелений")}</span> — {t("цена диалога до $1 / CTR от 3%", "ціна діалогу до $1 / CTR від 3%")}, <span style={{ color: "#a16207", fontWeight: 700 }}>{t("жёлтый", "жовтий")}</span> — {t("$1–2 / CTR 1–3%", "$1–2 / CTR 1–3%")}, <span style={{ color: "#dc2626", fontWeight: 700 }}>{t("красный", "червоний")}</span> — {t("дороже $2 / CTR ниже 1%", "дорожче $2 / CTR нижче 1%")}<br />
              • <b>{t("Наш «лид» = «Диалоги Meta»", "Наш «лід» = «Діалоги Meta»")}</b>: {t("каждый написавший становится лидом в CRM. А в обратную сторону CRM сама сообщает Meta статусы («лид», «оплачено», «размещен заказ», «отправлено») — они видны ярлыками в переписках Direct и учат рекламу находить платящих клиентов, а не просто болтунов.", "кожен, хто написав, стає лідом у CRM. А назад CRM сама повідомляє Meta статуси («лід», «оплачено», «розміщено замовлення», «відправлено») — вони видні ярликами у Direct і вчать рекламу знаходити платників.")}
            </div>
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

        {tab === "pixel" && <PixelEventsTab from={from} to={to} />}

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
      <Metric label={t("Расход", "Витрати")} value={moneyUsd(row.spend)}
        tip={t("Сколько денег потрачено именно на ЭТО объявление за выбранный период (в долларах, как в кабинете Meta). Меняешь период сверху — цифра пересчитывается.", "Скільки грошей витрачено саме на ЦЕ оголошення за обраний період (у доларах, як у кабінеті Meta).")} />
      <Metric label={t("Диалоги Meta", "Діалоги Meta")} value={count(row.messages_started)}
        tip={t("Так считает Meta ПО КЛИКАМ: она записывает объявлению ВСЕ переписки в течение 7 дней после клика по нему. Даже если человек не нажал кнопку в рекламе, а просто зашёл в профиль и написал. И даже если это старый клиент, который написал снова. Поэтому цифра всегда больше, чем «Лиды CRM».", "Так рахує Meta ПО КЛІКАХ: вона записує оголошенню ВСІ листування протягом 7 днів після кліку. Навіть якщо людина не натиснула кнопку в рекламі, а просто зайшла в профіль і написала. І навіть якщо це старий клієнт, який написав знову. Тому цифра завжди більша за «Ліди CRM».")} />
      <Metric label={t("Лиды Meta", "Ліди Meta")} value={count(row.meta_leads)}
        tip={t("Сколько лидов засчитала себе Meta. Раньше тут был всегда 0 (Meta сама считает лидом только лид-форму, а у нас кампании на переписку). Теперь CRM САМА сообщает Meta о каждом лиде и его статусе: лид → оплачено → отправлено. Эти отметки появляются как ярлыки в переписке в Direct («Лид», «Оплачено», «Размещен заказ») и попадают в статистику Meta — цифра начнёт наполняться.", "Скільки лідів зарахувала собі Meta. Раніше тут завжди був 0. Тепер CRM САМА повідомляє Meta про кожного ліда і його статус: лід → оплачено → відправлено. Ці позначки зʼявляються як ярлики у Direct і потрапляють у статистику Meta.")} />
      <Metric label={t("Лиды CRM", "Ліди CRM")} value={count(row.crm_leads)}
        tip={t("Те, кто написал ИМЕННО ЧЕРЕЗ КНОПКУ в этом объявлении — только тогда Instagram сообщает нам, с какого объявления человек, и мы клеим метку на его карточку. Пример: Диалоги 94, Лиды CRM 34 — значит 34 пришли с кнопки объявления, а остальные 60 ТОЖЕ у нас в CRM (никто не потерялся), просто написали в обход кнопки (зашли в профиль / уже переписывались), и Instagram не сказал, с какого они объявления.", "Ті, хто написав САМЕ ЧЕРЕЗ КНОПКУ в цьому оголошенні — лише тоді Instagram повідомляє, з якого оголошення людина. Приклад: Діалоги 94, Ліди CRM 34 — 34 прийшли з кнопки, а решта 60 ТЕЖ у нас в CRM (ніхто не загубився), просто написали в обхід кнопки, і Instagram не сказав, з якого вони оголошення.")} />
      <Metric label="CTR" value={row.ctr == null ? "—" : `${row.ctr}%`} tone={toneCtr(row.ctr)}
        tip={t("Какой процент увидевших нажал на объявление. Показывает, цепляет ли картинка и текст. Ориентир: ниже 1% — креатив слабый, меняй; 1-3% — норма; выше 3% — хороший. Если CTR высокий, а лидов мало — проблема не в креативе, а в том, что происходит после клика.", "Який відсоток тих, хто побачив, натиснув. Орієнтир: до 1% — слабко, 1-3% — норма, вище 3% — добре. Високий CTR і мало лідів = проблема не в креативі, а в тому, що після кліку.")} />
      <Metric label={t("Цена диалога", "Ціна діалогу")} value={row.cost_per_message == null ? "—" : moneyUsd(row.cost_per_message)} tone={toneCostMsg(row.cost_per_message)}
        tip={t("Сколько стоила одна начатая переписка: расход ÷ диалоги. Чем дешевле — тем выгоднее объявление. Сравнивай креативы между собой: тот, у кого диалог дешевле при таком же качестве лидов, — на него и переносить бюджет.", "Скільки коштувало одне розпочате листування: витрати ÷ діалоги. Порівнюй креативи між собою: де діалог дешевший за тієї ж якості лідів — туди й переносити бюджет.")} />
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
      <Metric label={t("Охват", "Охоплення")} value={contentMetric(row.reach)}
        tip={t("Сколько РАЗНЫХ людей увидели публикацию (каждый считается один раз, даже если смотрел трижды). Главная цифра охвата: сколько человек мы реально достали этим постом.", "Скільки РІЗНИХ людей побачили публікацію (кожен рахується один раз). Головна цифра: скільки людей ми реально дістали цим постом.")} />
      <Metric label={t("Просмотры", "Перегляди")} value={contentMetric(row.views)}
        tip={t("Сколько раз ролик запускали ВСЕГО, с повторами. Один человек мог пересмотреть несколько раз — поэтому просмотров больше охвата. Если просмотров сильно больше охвата — ролик пересматривают, это хороший знак.", "Скільки разів ролик запускали ВСЬОГО, з повторами. Якщо переглядів набагато більше за охоплення — ролик передивляються, це добре.")} />
      <Metric label={t("Лайки", "Вподобання")} value={count(row.likes)} />
      <Metric label={t("Комментарии", "Коментарі")} value={count(row.comments)} />
      <Metric label={t("Сохранения", "Збереження")} value={contentMetric(row.saved)}
        tip={t("Сколько человек сохранили пост себе в закладки. Сильный сигнал: контент полезный, к нему хотят вернуться. Instagram поднимает в ленте посты, которые много сохраняют.", "Скільки людей зберегли пост у закладки. Сильний сигнал: контент корисний. Instagram піднімає в стрічці пости, які багато зберігають.")} />
      <Metric label={t("Поделились", "Поширення")} value={contentMetric(row.shares)}
        tip={t("Сколько раз публикацию переслали друзьям или в свои сторис. Самый сильный сигнал, что контент зашёл — люди рекомендуют нас сами, бесплатно. Такие темы стоит повторять.", "Скільки разів публікацію переслали друзям або в сторіс. Найсильніший сигнал — люди рекомендують нас самі, безкоштовно. Такі теми варто повторювати.")} />
      <Metric label={t("Подписчики", "Підписники")} value={contentMetric(row.follows)} accent
        tip={t("Сколько человек подписалось после этой публикации. ВАЖНО: для Reels Meta эту цифру не отдаёт — там будет «нет данных». Общий рост смотри во вкладке «Рост кабинета».", "Скільки людей підписалося після цієї публікації. ВАЖЛИВО: для Reels Meta цю цифру не віддає.")} />
      <Metric label={t("Визиты профиля", "Візити профілю")} value={contentMetric(row.profile_visits)}
        tip={t("Сколько человек после этой публикации зашли к нам в профиль — то есть заинтересовались настолько, что решили посмотреть, кто мы. Ступенька между «увидел» и «подписался/написал».", "Скільки людей після цієї публікації зайшли в наш профіль — зацікавились настільки, щоб подивитись, хто ми. Сходинка між «побачив» і «підписався/написав».")} />
      <Metric label={t("Вовлечённость", "Залученість")} value={row.engagement_rate == null ? "—" : `${row.engagement_rate}%`}
        tip={t("Какой процент увидевших как-то отреагировал: лайк, комментарий, сохранение или репост. Главный показатель качества контента. Ориентир для Instagram: 3-6% — норма, выше 6% — отличный пост, ниже 2% — тема не зашла.", "Який відсоток тих, хто побачив, якось відреагував. Орієнтир: 3-6% — норма, вище 6% — відмінно, нижче 2% — тема не зайшла.")} />
      <Metric label={t("Диалоги CRM", "Діалоги CRM")} value={count(row.crm_dialogues)}
        tip={t("Сколько переписок в нашей CRM началось именно с этой публикации — то есть сколько живых людей она привела в Direct. Это главная бизнес-цифра для органики: лайки приятны, но клиенты приходят отсюда.", "Скільки листувань у нашій CRM почалося саме з цієї публікації. Головна бізнес-цифра для органіки: лайки приємні, але клієнти приходять звідси.")} />
    </div>
    <div className="muted" style={{ fontSize: 9, marginTop: 8 }}>{t("Обновлено", "Оновлено")}: {dateTime(row.synced_at)}</div>
  </div>;
}

const TONE_BG: any = { good: "#ecfdf5", warn: "#fefce8", bad: "#fef2f2" };
const TONE_FG: any = { good: "#047857", warn: "#a16207", bad: "#dc2626" };
function Metric({ label, value, accent = false, tip, tone }: { label: string; value: ReactNode; accent?: boolean; tip?: string; tone?: "good" | "warn" | "bad" }) {
  const bg = tone ? TONE_BG[tone] : (accent ? "#ecfdf5" : "#f8fafc");
  const fg = tone ? TONE_FG[tone] : (accent ? "#047857" : "#0f172a");
  return <div style={{ background: bg, borderRadius: 8, padding: "7px 8px" }}>
    <div className="muted" style={{ fontSize: 9 }}>{tip ? <Tip text={tip}>{label}<span style={{ opacity: .5, marginLeft: 3 }}>ⓘ</span></Tip> : label}</div>
    <div style={{ fontSize: 13, fontWeight: 800, color: fg, marginTop: 2 }}>{value}{tone === "good" ? " ✓" : ""}</div>
  </div>;
}
// Пороги для быстрого чтения карточек: цена диалога и CTR
function toneCostMsg(v: any): "good" | "warn" | "bad" | undefined {
  if (v == null) return undefined;
  return v <= 1 ? "good" : v <= 2 ? "warn" : "bad";
}
function toneCtr(v: any): "good" | "warn" | "bad" | undefined {
  if (v == null) return undefined;
  return v >= 3 ? "good" : v >= 1 ? "warn" : "bad";
}

function Empty({ text }: { text: string }) {
  return <div className="panel muted" style={{ padding: 28, textAlign: "center", gridColumn: "1 / -1" }}>{text}</div>;
}

/* UI v3: біла панель-сітка, рядки «назва — значення» у кілька колонок (компакт без прокрутки) */
const cardsRow: any = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(228px, 1fr))", columnGap: 22, rowGap: 0, marginBottom: 9, background: "#fff", border: "1px solid #e5eaf1", borderRadius: 10, padding: "6px 11px" };
const metricGrid: any = { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 6, marginTop: 12 };
const th: any = { textAlign: "left", padding: "10px 12px", fontSize: 12, color: "#64748b", borderBottom: "2px solid #e2e8f0", whiteSpace: "nowrap" };
const td: any = { padding: "10px 12px", fontSize: 13, borderBottom: "1px solid #eef2f7", verticalAlign: "top" };
const dealTd: any = { padding: "9px 10px", fontSize: 12, borderTop: "1px solid #eef2f7", verticalAlign: "top" };
const dayToggle: any = { minHeight: 36, padding: "0 8px 0 0", border: 0, background: "transparent", color: "#0f172a", fontWeight: 750, cursor: "pointer", display: "inline-flex", alignItems: "center", whiteSpace: "nowrap", textAlign: "left" };
const dateLabel: any = { display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#64748b" };
const dateInput: any = { height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 8px", background: "#fff" };
