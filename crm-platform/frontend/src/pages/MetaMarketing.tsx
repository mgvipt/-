import { Fragment, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
import { Cone, MetaCone } from "../FunnelCone";

// Явна підказка (тултип), яка показується ОДРАЗУ при наведенні і НЕ обрізається
// прокруткою таблиці (рендериться в body через портал, слідує за курсором).
/* Людська назва «Результату» за ціллю кампанії (колонка «Результати» кабінету).
   Невідомий індикатор показуємо його хвостом (напр. імʼя події пікселя) —
   нові цілі кампаній зʼявляються автоматично, без дописування коду. */
function resultLabel(indicator: string, t: (ru: string, ua: string) => string): string {
  if (!indicator) return "";
  if (indicator === "mixed") return t("смешанные цели", "змішані цілі");
  if (indicator === "profile_visit_view") return t("Визиты профиля", "Візити профілю");
  if (indicator.includes("messaging_conversation_started")) return t("Переписки", "Переписки");
  if (indicator === "landing_page_view") return t("Просмотры лендинга", "Перегляди лендінгу");
  if (indicator === "lead" || indicator.endsWith(".lead") || indicator.endsWith("lead_grouped")) return t("Лиды", "Ліди");
  if (indicator.includes("purchase")) return t("Покупки", "Покупки");
  if (indicator === "link_click") return t("Клики по ссылке", "Кліки за посиланням");
  const custom = indicator.match(/fb_pixel_custom\.(.+)$/);
  if (custom) return custom[1];
  return (indicator.split(".").pop() || indicator).replace(/_/g, " ");
}

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

// ── Редизайн 27.08 (макет Олега): кругла «i»-підказка та кільцева діаграма ──
function InfoI({ tip }: { tip: string }) {
  return <Tip text={tip}><span className="rd-info">i</span></Tip>;
}

// Кільце «скільки з усіх лідів мають точний ID реклами» (центр — всього лідів)
function Donut({ total, part, label }: { total: number; part: number; label: string }) {
  const R = 40, C = 2 * Math.PI * R;
  const pct = total > 0 ? Math.min(part / total, 1) : 0;
  return (
    <svg width={96} height={96} viewBox="0 0 96 96" style={{ flexShrink: 0 }}>
      <circle cx={48} cy={48} r={R} fill="none" stroke="var(--rd-border)" strokeWidth={8} />
      {pct > 0 && <circle cx={48} cy={48} r={R} fill="none" stroke="var(--rd-primary)" strokeWidth={8}
        strokeDasharray={`${C * pct} ${C}`} strokeLinecap="round" transform="rotate(-90 48 48)" />}
      <text x={48} y={48} textAnchor="middle" fontSize={total >= 1000 ? 16 : 24} fontWeight={700} fill="var(--rd-primary)">{count(total)}</text>
      <text x={48} y={64} textAnchor="middle" fontSize={10} fill="var(--rd-text2)">{label}</text>
    </svg>
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
  /* Стиль пагінації за макетами crm_2/crm_3 (27.08): кнопки-квадратики в рамках, «сторінка 1 / 2» */
  const btn: any = { minWidth: 32, height: 32, border: "1px solid var(--rd-border)", borderRadius: 6, background: "var(--rd-card)", cursor: "pointer", fontSize: 13, color: "var(--rd-text)" };
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", padding: "10px 14px", fontSize: 13, color: "var(--rd-text2)" }}>
      <span>{t("Показывать по", "Показувати по")}:</span>
      <select value={pageSize} onChange={(e) => { const n = Number(e.target.value); try { localStorage.setItem(sizeKey, String(n)); } catch { /* */ } onSize(n); onPage(0); }}
        style={{ height: 32, border: "1px solid var(--rd-border)", borderRadius: 6, fontSize: 13, padding: "0 8px", background: "var(--rd-card)", color: "var(--rd-text)" }}>
        {[10, 25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
        <option value={99999}>{t("все", "всі")}</option>
      </select>
      <span style={{ marginLeft: 4 }}>{from}–{to} {t("из", "з")} {total}</span>
      <div style={{ flex: 1 }} />
      {!all && pages > 1 && <>
        <button style={btn} disabled={page <= 0} onClick={() => onPage(0)}>«</button>
        <button style={btn} disabled={page <= 0} onClick={() => onPage(page - 1)}>‹</button>
        <span style={{ minWidth: 96, textAlign: "center", color: "var(--rd-text)" }}>{t("страница", "сторінка")} {page + 1} / {pages}</span>
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
              thStyle={{ ...th, whiteSpace: "normal", verticalAlign: "bottom", background: "var(--rd-muted)", fontSize: 10.5, lineHeight: 1.25 }}
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
          style={{ textAlign: "left", padding: "10px 10px", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".04em", color: sortKey === key ? "var(--rd-text)" : "var(--rd-text2)", cursor: "pointer", userSelect: "none", whiteSpace: "nowrap", borderBottom: "1px solid var(--rd-border)", background: "var(--rd-muted)" }}>
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
  // Редизайн 27.08: який пресет періоду підсвічено + пошук дати в «Деталізації за днями»
  const [preset, setPreset] = useState<string>("all");
  const [daySearch, setDaySearch] = useState("");

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

  const setLastDays = (days: number, key?: string) => {
    const start = new Date(today); start.setDate(start.getDate() - days + 1);
    setFrom(iso(start)); setTo(iso(today));
    setPreset(key || "");
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
  const dialogues = data?.dialogues || {};
  const offline = data?.offline || {};
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
  // Пара комірок «назва | значення» для панелі-таблиці «Платна реклама Meta» (макет crm_1)
  const kv = (label: ReactNode, value: ReactNode, color: string, divider = false) => (<>
    <td style={{ padding: "12px 24px", fontSize: 14, color: "var(--rd-text)", whiteSpace: "nowrap", borderLeft: divider ? "1px solid var(--rd-border)" : "none" }}>{label}</td>
    <td style={{ padding: "12px 24px", fontSize: 14, fontWeight: 600, color, textAlign: "right", whiteSpace: "nowrap" }}>{value}</td>
  </>);

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
    r.result_value ? <span>{count(r.result_value)}<div style={{ fontSize: 10, color: "var(--rd-text2)" }}>{resultLabel(r.result_indicator, t)}</div></span> : "—",
    count(r.instagram_follows), r.cost_per_instagram_follow == null ? "—" : moneyUsd(r.cost_per_instagram_follow),
    count(r.messages_started), count(r.meta_leads), count(r.crm_leads), r.cost_per_message == null ? "—" : moneyUsd(r.cost_per_message),
  ]);
  const dailyTable = <DailySalesTable rows={daily} t={t} />;
  // Пошук дати в «Деталізації за днями» (Огляд): збіг і по 2026-08-27, і по 27.08.2026
  const dailyFiltered = daySearch.trim() ? daily.filter((r: any) => {
    const q = daySearch.trim();
    const human = new Date(`${r.date}T12:00:00`).toLocaleDateString("ru-RU");
    return String(r.date).includes(q) || human.includes(q);
  }) : daily;
  // Кнопка «скачати» в «Деталізації за днями»: та сама таблиця файлом CSV (відкривається в Excel)
  const downloadDailyCsv = () => {
    const heads = [t("Дата", "Дата"), t("Подписчики", "Підписники"), t("Новые", "Нові"), t("Контент", "Контент"), "Реклама $", "Реклама ₴", t("Диалоги", "Діалоги"), t("Лиды", "Ліди"), t("С рекламой", "З рекламою"), t("Продажи", "Продажі"), t("Повторные", "Повторні"), t("Выручка", "Виручка"), t("Из них повторные", "З них повторні"), "LTV", t("Прибыль", "Прибуток"), "ROAS", "ROMI"];
    const lines = daily.map((r: any) => [r.date, r.followers_total ?? "", r.followers_gained ?? "", r.content_published ?? 0, r.spend ?? 0, r.spend_uah ?? "", r.messages_started ?? 0, r.crm_meta_leads ?? 0, r.exact_ad_leads ?? 0, r.sales ?? 0, r.repeat_sales ?? 0, r.revenue ?? 0, r.repeat_revenue ?? 0, r.average_ltv ?? 0, r.gross_profit ?? 0, r.roas ?? "", r.romi ?? ""].join(";"));
    const blob = new Blob(["﻿" + [heads.join(";"), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `meta-daily_${from}_${to}.csv`; a.click();
    URL.revokeObjectURL(a.href);
  };
  // похідні показники реклами: ціни за клік / ліда (дзеркало Ads Manager простими словами)
  const cpcUsd = paidSummary.clicks ? paidSummary.spend / paidSummary.clicks : null;
  const cplUah = (paidSummary.spend_uah && summary.meta_origin_leads) ? paidSummary.spend_uah / summary.meta_origin_leads : null;
  const cplExactUah = (paidSummary.spend_uah && summary.attributed_leads) ? paidSummary.spend_uah / summary.attributed_leads : null;

  return <div style={{ height: "100%", overflowY: "auto", background: "var(--rd-bg)", boxSizing: "border-box" }}>
    {/* Шапка-смуга (редизайн 27.08 за макетом Олега) */}
    <div style={{ background: "var(--rd-card)", borderBottom: "1px solid var(--rd-border)", padding: "18px clamp(14px,2.5vw,32px) 16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ background: "var(--rd-primary)", color: "#fff", fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 4, letterSpacing: ".04em" }}>BETA</span>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: "var(--rd-text)" }}>{t("Маркетинг · Meta", "Маркетинг · Meta")}</h1>
          </div>
          <div style={{ fontSize: 13, color: "var(--rd-text2)", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--rd-success)", display: "inline-block", flexShrink: 0 }} />
            {t("Платная реклама и органический контент считаются отдельно", "Платна реклама й органічний контент рахуються окремо")}
            {syncSt && <span style={{ fontSize: 12 }}>· {t("обновление каждые", "оновлення кожні")} {syncSt.interval_hours}{t("ч", "год")}{syncSt.sources?.content && <> · Instagram <b style={{ color: (syncSt.sources.content.mins_ago > 420) ? "var(--rd-error)" : "var(--rd-success)" }}>{syncSt.sources.content.at}</b></>}{syncSt.sources?.ads && <> · Ads <b style={{ color: (syncSt.sources.ads.mins_ago > 420) ? "var(--rd-error)" : "var(--rd-success)" }}>{syncSt.sources.ads.at}</b></>}</span>}
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
          <div className="rd-seg">
            <button className={preset === "1d" ? "active" : ""} onClick={() => setLastDays(1, "1d")}>{t("Сегодня", "Сьогодні")}</button>
            <button className={preset === "7d" ? "active" : ""} onClick={() => setLastDays(7, "7d")}>7 {t("дней", "днів")}</button>
            <button className={preset === "30d" ? "active" : ""} onClick={() => setLastDays(30, "30d")}>30 {t("дней", "днів")}</button>
            <button className={preset === "90d" ? "active" : ""} onClick={() => setLastDays(90, "90d")}>90 {t("дней", "днів")}</button>
            <button className={preset === "all" ? "active" : ""} onClick={() => { setFrom(CONNECTED_FROM); setTo(iso(today)); setPreset("all"); }}>{t("С подключения", "З підключення")}</button>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--rd-card)", border: "1px solid var(--rd-border)", borderRadius: 6, padding: "5px 10px", boxShadow: "0 1px 2px rgba(0,0,0,.05)" }}>
            <Icon n="calendar" size={15} style={{ color: "var(--rd-text2)" }} />
            <input type="date" value={from} min={CONNECTED_FROM} onChange={(e) => { setFrom(e.target.value); setPreset(""); }} style={rdDate} />
            <span style={{ color: "var(--rd-text2)", fontSize: 12 }}>—</span>
            <input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPreset(""); }} style={rdDate} />
          </div>
        </div>
      </div>
      <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 8 }}>
        <button onClick={refreshNow} disabled={syncing} title={t("Подтянуть свежие данные со всех источников (Ads + Instagram + подписчики)", "Підтягнути свіжі дані з усіх джерел")}
          style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 16px", fontSize: 13, fontWeight: 500, background: "var(--rd-primary)", color: "#fff", border: "none", borderRadius: 6, cursor: syncing ? "default" : "pointer", opacity: syncing ? .7 : 1, boxShadow: "0 1px 2px rgba(0,0,0,.05)" }}>
          <Icon n="refresh" size={16} style={syncing ? { animation: "rd-spin 1.2s linear infinite" } : undefined} /> {syncing ? t("Обновляю…", "Оновлюю…") : t("Обновить", "Оновити")}
        </button>
        <button className="rd-pill" onClick={() => setShowSettings(true)} title={t("Настройки маркетинга: интервалы обновления и доступы", "Налаштування маркетингу")} style={{ padding: "8px 12px", display: "inline-flex", alignItems: "center" }}>
          <Icon n="settings" size={16} style={{ color: "var(--rd-text2)" }} />
        </button>
      </div>
    </div>
    <div style={{ padding: "20px clamp(14px,2.5vw,32px) 28px" }}>
      {showSettings && <MetaSettingsModal onClose={() => setShowSettings(false)} />}
      {syncing && <div className="note" style={{ marginBottom: 10, background: "#eff6ff", color: "#1e40af" }}>{t("Тянем свежие данные из Meta (Ads + Instagram + подписчики). Это ~1-3 минуты — таблицы обновятся автоматически, можно продолжать работать.", "Тягнемо свіжі дані з Meta. Це ~1-3 хвилини — таблиці оновляться автоматично.")}</div>}

      <nav style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 8, marginBottom: 14 }}>
        {tabs.map((item) => <button key={item.key} className={"rd-pill" + (tab === item.key ? " active" : "")} onClick={() => setTab(item.key)}>{t(item.ru, item.ua)}</button>)}
      </nav>
      {error && <div className="note" style={{ color: "#b91c1c" }}>{error}</div>}
      {loading && !data ? <div className="muted" style={{ padding: 30 }}>Загрузка…</div> : data && <>
        {tab === "overview" && <>
          {syncWarning}
          {/* ── Ряд 1 (макет 27.08): Instagram Аудитория + Ads Manager Эффективность ── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(430px,100%), 1fr))", gap: 20, marginBottom: 20 }}>
            <div className="rd-card">
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                <span style={{ width: 24, height: 24, background: "#e5e7eb", borderRadius: 4, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700, color: "var(--rd-text)" }}>IG</span>
                <b style={{ fontSize: 16, color: "var(--rd-text)" }}>Instagram {t("Аудитория", "Аудиторія")}</b>
              </div>
              <div style={{ fontSize: 13, color: "var(--rd-text2)", marginBottom: 22 }}>{followers.username ? "@" + followers.username : "—"}</div>
              <div style={{ marginBottom: 22 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 13, color: "var(--rd-text2)", display: "inline-flex", alignItems: "center" }}>{t("Подписчиков сейчас", "Підписників зараз")} <InfoI tip={t("Живой баланс подписчиков аккаунта; CRM сохраняет его каждый день", "Живий баланс підписників акаунта; CRM зберігає його щодня")} /></span>
                  {followers.period_gained != null && <span style={{ display: "inline-flex", alignItems: "center", gap: 4, background: followers.period_gained >= 0 ? "#ecfdf5" : "#fef2f2", color: followers.period_gained >= 0 ? "var(--rd-success)" : "var(--rd-error)", fontSize: 12, fontWeight: 500, padding: "2px 8px", borderRadius: 4 }}>
                    <Icon n={followers.period_gained >= 0 ? "trending-up" : "🔻"} size={14} /> {followers.period_gained >= 0 ? "+" : ""}{count(followers.period_gained)}
                    <InfoI tip={t("подписались минус отписались за выбранный период", "підписалися мінус відписалися за вибраний період")} />
                  </span>}
                </div>
                <div style={{ fontSize: 32, fontWeight: 700, color: "var(--rd-purple)", lineHeight: 1.25 }}>{optional(followers.current_total, "", t("ожидает синхронизации", "очікує синхронізації"))}</div>
              </div>
              <div style={{ height: 1, background: "var(--rd-border)", marginBottom: 22 }} />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", rowGap: 22, columnGap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("С рекламы", "З реклами")} <InfoI tip={t("Из ежедневного отчёта Ads Manager: только подписки, которые Meta отнесла к рекламе.", "З щоденного звіту Ads Manager: лише підписки, які Meta віднесла до реклами.")} /></div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "var(--rd-primary)" }}>{followers.paid_report_rows ? count(followers.paid_from_ads) : "—"}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Органика", "Органіка")} <InfoI tip={t("Итоговый прирост кабинета минус подписки с рекламы. Для Reels Meta отдельные подписки не отдаёт.", "Підсумковий приріст кабінету мінус підписки з реклами. Для Reels Meta окремі підписки не віддає.")} /></div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "var(--rd-text2)" }}>{followers.organic_other == null ? "—" : count(followers.organic_other)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Цена подп.", "Ціна підп.")} <InfoI tip={t("расход за дни с данными подписок ÷ подписки с рекламы", "витрати за дні з даними підписок ÷ підписки з реклами")} /></div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "var(--rd-success)" }}>{paidSummary.cost_per_instagram_follow == null ? "—" : <>{moneyUsd(paidSummary.cost_per_instagram_follow)}{paidSummary.cost_per_instagram_follow_uah != null && <span style={{ fontSize: 14, color: "var(--rd-text2)", fontWeight: 400 }}> / {moneyUah(paidSummary.cost_per_instagram_follow_uah)}</span>}</>}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Публикаций", "Публікацій")} <InfoI tip={t("Сколько постов и Reels вышло за выбранный период", "Скільки постів і Reels вийшло за вибраний період")} /></div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "var(--rd-text)" }}>{count(daily.reduce((sum: number, r: any) => sum + Number(r.content_published || 0), 0))}</div>
                </div>
              </div>
            </div>
            <div className="rd-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 22, flexWrap: "wrap" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                    <span style={{ width: 24, height: 24, background: "#dbeafe", borderRadius: 4, display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon n="megaphone" size={14} style={{ color: "var(--rd-primary)" }} /></span>
                    <b style={{ fontSize: 16, color: "var(--rd-text)" }}>Ads Manager {t("Эффективность", "Ефективність")}</b>
                  </div>
                  <div style={{ fontSize: 13, color: "var(--rd-text2)" }}>{t("Расходы и конверсии за выбранный период", "Витрати та конверсії за вибраний період")}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 2, display: "flex", alignItems: "center", justifyContent: "flex-end" }}>{t("Расходы", "Витрати")} <InfoI tip={t("Потрачено в Ads Manager за период; в гривне — по курсу НБУ за каждый день", "Витрачено в Ads Manager за період; у гривні — за курсом НБУ на кожен день")} /></div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: "var(--rd-error)", whiteSpace: "nowrap" }}>{moneyUsd(paidSummary.spend)}{paidSummary.spend_uah != null && <span style={{ fontSize: 16, color: "var(--rd-text2)", fontWeight: 400 }}> / {moneyUah(paidSummary.spend_uah)}</span>}</div>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(118px, 1fr))", gap: 14 }}>
                <div className="rd-tile">
                  <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Показы", "Покази")} <InfoI tip={t("Сколько раз реклама была показана; CPM — цена 1000 показов", "Скільки разів рекламу показали; CPM — ціна 1000 показів")} /></div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-text)", marginBottom: 6 }}>{count(paidSummary.impressions)}</div>
                  <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>CPM: {paidSummary.cpm == null ? "—" : moneyUsd(paidSummary.cpm)}</div>
                </div>
                <div className="rd-tile">
                  <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Клики", "Кліки")} <InfoI tip={t("Все клики по рекламе; CTR — % кликов от показов", "Усі кліки по рекламі; CTR — % кліків від показів")} /></div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-primary)", marginBottom: 6 }}>{count(paidSummary.clicks)}</div>
                  <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>CTR: <span style={{ color: "var(--rd-purple)" }}>{paidSummary.ctr == null ? "—" : paidSummary.ctr + "%"}</span></div>
                </div>
                <div className="rd-tile">
                  <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Диалоги", "Діалоги")} <InfoI tip={t("Это показатель рекламы Meta, а не продажи и не уникальные лиды CRM", "Це показник реклами Meta, а не продажі й не унікальні ліди CRM")} /></div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-success)", marginBottom: 6 }}>{count(paidSummary.messages_started)}</div>
                  <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("Цена", "Ціна")}: {paidSummary.cost_per_message == null ? "—" : moneyUsd(paidSummary.cost_per_message)}{(paidSummary.spend_uah && paidSummary.messages_started) ? " / " + moneyUah(paidSummary.spend_uah / paidSummary.messages_started) : ""}</div>
                </div>
                <div className="rd-tile" style={{ background: "rgba(239,246,255,.5)", borderColor: "#bfdbfe" }}>
                  <div style={{ fontSize: 12, color: "var(--rd-primary)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Лиды Meta", "Ліди Meta")} <InfoI tip={t("Сколько лидов засчитала себе Meta по своему окну атрибуции", "Скільки лідів зарахувала собі Meta за власним вікном атрибуції")} /></div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-primary)", marginBottom: 6 }}>{count(paidSummary.meta_leads)}</div>
                  <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("Цена", "Ціна")}: {cplUah == null ? "—" : moneyUah(cplUah)}</div>
                </div>
                {/* Результати за ціллю кампанії (як «Результати» в кабінеті). Переписки
                    не дублюємо — вони вже показані плиткою «Діалоги». Нові цілі
                    (QuizStart, візити профілю…) зʼявляються тут автоматично. */}
                {Object.entries((paidSummary.results_by_type || {}) as Record<string, number>)
                  .filter(([key, value]) => key && value > 0 && !key.includes("messaging_conversation_started"))
                  .sort((a, b) => b[1] - a[1])
                  .map(([key, value]) => (
                    <div key={key} className="rd-tile">
                      <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{resultLabel(key, t)} <InfoI tip={t("«Результат» из кабинета Ads Manager: считается по цели каждой кампании (переписки, QuizStart, визиты профиля…)", "«Результат» з кабінету Ads Manager: рахується за ціллю кожної кампанії (переписки, QuizStart, візити профілю…)")} /></div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-purple)", marginBottom: 6 }}>{count(value)}</div>
                      <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("по цели кампании", "за ціллю кампанії")}</div>
                    </div>
                  ))}
              </div>
            </div>
          </div>
          {/* ── Діалоги за каналами (27.08): реклама йде лише на Instagram, тому
              Facebook/TikTok — органіка; ціни діалогу три — лише Ads, всі IG,
              всі соцмережі. Офлайн-воронки салону — окремо. ── */}
          <div className="rd-card" style={{ marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
              <span style={{ width: 24, height: 24, background: "#ecfdf5", borderRadius: 4, display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Icon n="chat" size={14} style={{ color: "var(--rd-success)" }} /></span>
              <b style={{ fontSize: 16, color: "var(--rd-text)" }}>{t("Диалоги по каналам", "Діалоги за каналами")}</b>
            </div>
            <div style={{ fontSize: 13, color: "var(--rd-text2)", marginBottom: 18 }}>{t("Новые переписки за период: сколько зашло и почём", "Нові переписки за період: скільки зайшло і почому")}</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 14 }}>
              <div className="rd-tile" style={{ background: "rgba(239,246,255,.5)", borderColor: "#bfdbfe" }}>
                <div style={{ fontSize: 12, color: "var(--rd-primary)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("С рекламы (Ads)", "З реклами (Ads)")} <InfoI tip={t("Начатые переписки по кабинету Meta: все, кто написал в течение 7 дней после клика по рекламе", "Розпочаті переписки за кабінетом Meta: всі, хто написав протягом 7 днів після кліку по рекламі")} /></div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-primary)", marginBottom: 6 }}>{count(dialogues.ads)}</div>
                <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("Цена", "Ціна")}: {dialogues.cost_ads?.usd != null ? moneyUsd(dialogues.cost_ads.usd) : "—"}{dialogues.cost_ads?.uah != null ? " / " + moneyUah(dialogues.cost_ads.uah) : ""}</div>
              </div>
              <div className="rd-tile">
                <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Instagram все", "Instagram усі")} <InfoI tip={t("Все новые переписки Instagram в CRM за период: и с рекламы, и органика. Цена — весь расход рекламы ÷ все IG-диалоги", "Усі нові переписки Instagram у CRM за період: і з реклами, і органіка. Ціна — всі витрати реклами ÷ всі IG-діалоги")} /></div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-purple)", marginBottom: 6 }}>{count(dialogues.instagram)}</div>
                <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("Цена", "Ціна")}: {dialogues.cost_ig_all?.usd != null ? moneyUsd(dialogues.cost_ig_all.usd) : "—"}{dialogues.cost_ig_all?.uah != null ? " / " + moneyUah(dialogues.cost_ig_all.uah) : ""}</div>
              </div>
              <div className="rd-tile">
                <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>Facebook <InfoI tip={t("Новые переписки из Facebook. Реклама на Facebook не идёт — это органика, но продажи отсюда тоже есть", "Нові переписки з Facebook. Реклама на Facebook не йде — це органіка, але продажі звідси теж є")} /></div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-text)", marginBottom: 6 }}>{count(dialogues.facebook)}</div>
                <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("органика", "органіка")}</div>
              </div>
              <div className="rd-tile">
                <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>TikTok <InfoI tip={t("Новые переписки из TikTok за период", "Нові переписки з TikTok за період")} /></div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-text)", marginBottom: 6 }}>{count(dialogues.tiktok)}</div>
                <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("органика", "органіка")}</div>
              </div>
              <div className="rd-tile" style={{ background: "rgba(236,253,245,.6)", borderColor: "#bbf7d0" }}>
                <div style={{ fontSize: 12, color: "var(--rd-success)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Соцсети вместе", "Соцмережі разом")} <InfoI tip={t("Instagram + Facebook + TikTok. Общая цена: весь расход рекламы ÷ все диалоги соцсетей", "Instagram + Facebook + TikTok. Загальна ціна: всі витрати реклами ÷ всі діалоги соцмереж")} /></div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-success)", marginBottom: 6 }}>{count(dialogues.social_total)}</div>
                <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("Цена", "Ціна")}: {dialogues.cost_social_all?.usd != null ? moneyUsd(dialogues.cost_social_all.usd) : "—"}{dialogues.cost_social_all?.uah != null ? " / " + moneyUah(dialogues.cost_social_all.uah) : ""}</div>
              </div>
              <div className="rd-tile">
                <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Другие каналы", "Інші канали")} <InfoI tip={t("Telegram, Viber, WhatsApp, веб-чат — не соцсети", "Telegram, Viber, WhatsApp, веб-чат — не соцмережі")} /></div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-text2)", marginBottom: 6 }}>{count(dialogues.other)}</div>
                <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("всего диалогов", "всього діалогів")}: {count(dialogues.total)}</div>
              </div>
              <div className="rd-tile" style={{ background: "rgba(255,251,235,.7)", borderColor: "#fde68a" }}>
                <div style={{ fontSize: 12, color: "var(--rd-warning)", marginBottom: 4, display: "flex", alignItems: "center" }}>{t("Офлайн-воронки", "Офлайн-воронки")} <InfoI tip={t("Салон: «1.С/Покрытия для стен» и «4.С/Алмазное + Вентиляция». Обращения и продажи за период — отдельно от соцсетей", "Салон: «1.С/Покриття для стін» і «4.С/Алмазне + Вентиляція». Звернення і продажі за період — окремо від соцмереж")} /></div>
                <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-warning)", marginBottom: 6 }}>{count(offline.deals_created)}</div>
                <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{t("продаж", "продажів")}: {count(offline.sales)} · {moneyUah(offline.revenue)}</div>
              </div>
            </div>
          </div>
          {/* ── Ряд 2 (макет 27.08): Лиды в CRM + Подтверждённый результат ── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(430px,100%), 1fr))", gap: 20, marginBottom: 8 }}>
            <div className="rd-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 22 }}>
                <b style={{ fontSize: 16, color: "var(--rd-text)", display: "flex", alignItems: "center", gap: 8 }}><Icon n="💱" size={18} style={{ color: "var(--rd-primary)" }} /> {t("Лиды в CRM", "Ліди в CRM")} <InfoI tip={t("Люди с Meta-каналов, попавшие в CRM за период. Диаграмма — какая часть с точной привязкой к объявлению", "Люди з Meta-каналів, що потрапили в CRM за період. Діаграма — яка частина з точною привʼязкою до оголошення")} /></b>
                <span style={{ fontSize: 11, background: "var(--rd-bg)", padding: "4px 8px", borderRadius: 4, color: "var(--rd-text2)" }}>Meta → CRM</span>
              </div>
              {(() => {
                const totalLeads = Number(summary.meta_origin_leads || 0);
                const attributed = Number(summary.attributed_leads || 0);
                const unassigned = Number(summary.meta_unassigned_leads || 0);
                const convPct = totalLeads ? Math.round(attributed * 100 / totalLeads) : 0;
                return (
                  <div style={{ display: "flex", alignItems: "center", gap: 28, flexWrap: "wrap" }}>
                    <Donut total={totalLeads} part={attributed} label={t("всего", "всього")} />
                    <div style={{ flex: 1, minWidth: 200, display: "flex", flexDirection: "column", gap: 14 }}>
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                          <span style={{ color: "var(--rd-text2)", display: "inline-flex", alignItems: "center" }}>{t("С точным ID рекламы", "З точним ID реклами")} <InfoI tip={t("Instagram передал метку объявления — лид точно с этой рекламы", "Instagram передав мітку оголошення — лід точно з цієї реклами")} /></span>
                          <b style={{ color: "var(--rd-text)" }}>{count(attributed)}</b>
                        </div>
                        <div style={{ width: "100%", background: "var(--rd-border)", height: 6, borderRadius: 999, overflow: "hidden" }}>
                          <div style={{ background: "var(--rd-primary)", height: "100%", width: convPct + "%" }} />
                        </div>
                      </div>
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                          <span style={{ color: "var(--rd-text2)", display: "inline-flex", alignItems: "center" }}>{t("Источник не определён", "Джерело не визначене")} <InfoI tip={t("Лид пришёл из Meta, но без метки объявления: например, через ChatPlace или сам зашёл в профиль", "Лід прийшов з Meta, але без мітки оголошення: наприклад, через ChatPlace або сам зайшов у профіль")} /></span>
                          <b style={{ color: "var(--rd-warning)" }}>{count(unassigned)}</b>
                        </div>
                        <div style={{ width: "100%", background: "var(--rd-border)", height: 6, borderRadius: 999, overflow: "hidden" }}>
                          <div style={{ background: "var(--rd-warning)", height: "100%", width: (totalLeads ? Math.round(unassigned * 100 / totalLeads) : 0) + "%" }} />
                        </div>
                      </div>
                      <div style={{ fontSize: 12, color: "var(--rd-text2)", display: "flex", alignItems: "center", gap: 4 }}>
                        <Icon n="info" size={14} /> {t("Конверсия в точный лид", "Конверсія в точний лід")}: {convPct}%
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
            <div className="rd-card" style={{ position: "relative", overflow: "hidden" }}>
              <div style={{ position: "absolute", right: -24, bottom: -24, opacity: .05, pointerEvents: "none" }}><Icon n="money" size={150} strokeWidth={1} /></div>
              <div style={{ marginBottom: 22 }}>
                <b style={{ fontSize: 16, color: "var(--rd-text)", display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}><Icon n="badge-check" size={18} style={{ color: "var(--rd-success)" }} /> {t("Подтверждённый результат", "Підтверджений результат")}</b>
                <div style={{ fontSize: 12, color: "var(--rd-text2)" }}>{t("Только карточки с точным ID рекламы", "Лише картки з точним ID реклами")}</div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(105px, 1fr))", gap: 14, marginBottom: 20, position: "relative", zIndex: 1 }}>
                <div style={{ border: "1px solid var(--rd-border)", borderRadius: 8, padding: 14, background: "var(--rd-card)" }}>
                  <div style={{ fontSize: 10, color: "var(--rd-text2)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 8, display: "flex", alignItems: "center" }}>{t("Рекл. лиды", "Рекл. ліди")} <InfoI tip={t("Карточки CRM с точной привязкой к объявлению за период", "Картки CRM з точною привʼязкою до оголошення за період")} /></div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-primary)" }}>{count(summary.attributed_leads)}</div>
                </div>
                <div style={{ border: "1px solid var(--rd-border)", borderRadius: 8, padding: 14, background: "var(--rd-card)" }}>
                  <div style={{ fontSize: 10, color: "var(--rd-text2)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 8, display: "flex", alignItems: "center" }}>{t("Сделки", "Угоди")} <InfoI tip={t("Сделки, созданные из рекламных лидов", "Угоди, створені з рекламних лідів")} /></div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-purple)" }}>{count(summary.attributed_deals)}</div>
                </div>
                <div style={{ border: "1px solid var(--rd-border)", borderRadius: 8, padding: 14, background: "var(--rd-card)" }}>
                  <div style={{ fontSize: 10, color: "var(--rd-text2)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 8, display: "flex", alignItems: "center" }}>{t("Успешные", "Успішні")} <InfoI tip={t("Из них доведены до успешного закрытия", "З них доведені до успішного закриття")} /></div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-success)" }}>{count(summary.won_deals)}</div>
                </div>
                <div style={{ border: "1px solid var(--rd-border)", borderRadius: 8, padding: 14, background: "var(--rd-card)" }}>
                  <div style={{ fontSize: 10, color: "var(--rd-text2)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 8, display: "flex", alignItems: "center" }}>{t("Выручка", "Виручка")} <InfoI tip={t("Деньги успешных сделок рекламных лидов", "Гроші успішних угод рекламних лідів")} /></div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "var(--rd-success)", whiteSpace: "nowrap" }}>{moneyUah(summary.won_revenue)}</div>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, color: "var(--rd-text2)", position: "relative", zIndex: 1 }}>
                <Icon n="bulb" size={16} style={{ color: "var(--rd-warning)", flexShrink: 0, marginTop: 2 }} />
                <span>{t("Meta считает события по своему окну атрибуции. CRM показывает только реальные карточки. Исторические лиды без ID не приписываются рекламе.", "Meta рахує події за власним вікном атрибуції. CRM показує лише реальні картки. Історичні ліди без ID не приписуються рекламі.")}</span>
              </div>
            </div>
          </div>
          {/* «Платна реклама Meta» (макет crm_1 27.08): панель-таблиця «назва — значення» 3×3.
              Покази / кліки / діалоги та витрати в ₴ не дублюються — вони у картці Ads Manager вище. */}
          <div className="rd-card" style={{ padding: 0, overflow: "hidden", marginTop: 20, marginBottom: 8 }}>
            <div style={{ padding: "16px 24px", borderBottom: "1px solid var(--rd-border)", background: "var(--rd-muted)" }}>
              <b style={{ fontSize: 18, color: "var(--rd-text)" }}>{t("Платная реклама Meta", "Платна реклама Meta")}</b>
              <div style={{ fontSize: 12, color: "var(--rd-text2)", marginTop: 2 }}>{t("Данные Ads Manager за выбранный период", "Дані Ads Manager за вибраний період")}</div>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 860 }}>
                <tbody>
                  <tr style={{ borderBottom: "1px solid var(--rd-border)" }}>
                    {kv(<>{t("Расходы", "Витрати")} <InfoI tip={t("Потрачено в Ads Manager за период; в гривне — по официальному курсу НБУ за каждый день", "Витрачено в Ads Manager за період; у гривні — за офіційним курсом НБУ на кожен день")} /></>, <>{moneyUsd(paidSummary.spend)}{paidSummary.spend_uah != null && <span style={{ fontSize: 13, color: "var(--rd-text2)", fontWeight: 400 }}> / {moneyUah(paidSummary.spend_uah)}{paidSummary.avg_fx ? " · " + t("курс", "курс") + " " + paidSummary.avg_fx : ""}</span>}</>, "var(--rd-error)")}
                    {kv(<>{t("Подписки с рекламы", "Підписки з реклами")} <InfoI tip={t("Из ежедневного отчёта Ads Manager: только подписки, которые Meta отнесла к рекламе", "З щоденного звіту Ads Manager: лише підписки, які Meta віднесла до реклами")} /></>, followers.paid_report_rows ? count(paidSummary.instagram_follows) : "—", "var(--rd-primary)", true)}
                    {kv(t("Стоимость подписчика", "Вартість підписника"), paidSummary.cost_per_instagram_follow == null ? "—" : moneyUsd(paidSummary.cost_per_instagram_follow), "var(--rd-success)", true)}
                  </tr>
                  <tr style={{ borderBottom: "1px solid var(--rd-border)" }}>
                    {kv(<>CTR <InfoI tip={t("% кликов от показов: сколько из увидевших кликнули", "% кліків від показів: скільки з тих, хто побачив, клікнули")} /></>, optional(paidSummary.ctr, "%"), "var(--rd-purple)")}
                    {kv(<>{t("Стоимость клика (CPC)", "Вартість кліку (CPC)")} <InfoI tip={t("расход ÷ клики", "витрати ÷ кліки")} /></>, cpcUsd == null ? "—" : moneyUsd(cpcUsd), "var(--rd-primary)", true)}
                    {kv(<>CPM <InfoI tip={t("цена 1000 показов, $", "ціна 1000 показів, $")} /></>, optional(paidSummary.cpm), "var(--rd-primary)", true)}
                  </tr>
                  <tr>
                    {kv(<>{t("Лиды Meta", "Ліди Meta")} <InfoI tip={t("Сколько лидов засчитала себе Meta по своему окну атрибуции", "Скільки лідів зарахувала собі Meta за власним вікном атрибуції")} /></>, count(paidSummary.meta_leads), "var(--rd-success)")}
                    {kv(<>{t("Стоимость лида (все из Meta)", "Вартість ліда (всі з Meta)")} <InfoI tip={t("расход в грн ÷ все лиды CRM из Meta", "витрати грн ÷ усі ліди CRM з Meta")} /></>, cplUah == null ? "—" : moneyUah(cplUah), "var(--rd-warning)", true)}
                    {kv(<>{t("Стоимость лида (с точным ID)", "Вартість ліда (з точним ID)")} <InfoI tip={t("расход в грн ÷ лиды с подтверждённой рекламой", "витрати грн ÷ ліди з підтвердженою рекламою")} /></>, cplExactUah == null ? "—" : moneyUah(cplExactUah), "var(--rd-warning)", true)}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          {/* «Продажі та окупність» у механіці редизайну (27.08): показники згруповано —
              продажі зі своїми цінами, гроші, реклама з курсом і окупністю. */}
          <div className="rd-card" style={{ marginTop: 20, marginBottom: 8 }}>
            <div style={{ marginBottom: 18 }}>
              <b style={{ fontSize: 16, color: "var(--rd-text)", display: "flex", alignItems: "center", gap: 8 }}><Icon n="money" size={18} style={{ color: "var(--rd-success)" }} /> {t("Продажи и окупаемость", "Продажі та окупність")}</b>
              <div style={{ fontSize: 12, color: "var(--rd-text2)", marginTop: 2 }}>{t("21 Основной продукт, 22 Тестовый набор; другие воронки только с точным ID рекламы", "21 Основний продукт, 22 Тестовий набір; інші воронки лише з точним ID реклами")}</div>
            </div>
            {[
              {
                label: t("ПРОДАЖИ И ИХ ЦЕНА", "ПРОДАЖІ ТА ЇХ ЦІНА"),
                tiles: [
                  { l: t("Продажи", "Продажі"), v: count(profitability.sales), c: "var(--rd-success)", tip: t("Оплаченные продажи за период", "Оплачені продажі за період"), sub: t("повторных", "повторних") + ": " + count(profitability.repeat_sales) },
                  { l: t("Повторные продажи", "Повторні продажі"), v: count(profitability.repeat_sales), c: "#0891b2", tip: t("Клиент вернулся и купил основной продукт снова. Дозаказы к текущему заказу НЕ считаются", "Клієнт повернувся і купив основний продукт знову. Дозамовлення до поточного замовлення НЕ рахуються") },
                  { l: t("Цена клиента", "Ціна клієнта"), v: (profitability.buyers > 0 && paidSummary.spend) ? "$" + (paidSummary.spend / profitability.buyers).toFixed(2) : "—", c: "var(--rd-error)", tip: t("расход рекламы ÷ покупателей", "витрати реклами ÷ покупців") },
                  { l: t("Цена продажи", "Ціна продажу"), v: (paidSummary.spend_uah && profitability.sales) ? moneyUah(paidSummary.spend_uah / profitability.sales) : "—", c: "var(--rd-error)", tip: t("расход рекламы в грн ÷ все продажи периода", "витрати реклами в грн ÷ усі продажі періоду") },
                  { l: t("Средний LTV", "Середній LTV"), v: moneyUah(profitability.average_ltv), c: "var(--rd-purple)", tip: t("сколько в среднем приносит один покупатель за всё время", "скільки в середньому приносить один покупець за весь час") },
                ],
              },
              {
                label: t("ДЕНЬГИ", "ГРОШІ"),
                tiles: [
                  { l: t("Выручка", "Виручка"), v: moneyUah(profitability.revenue), c: "var(--rd-success)", tip: t("Сумма фактически оплаченных платежей за период", "Сума фактично сплачених платежів за період") },
                  { l: t("Из выручки — повторные", "З виручки — повторні"), v: moneyUah(profitability.repeat_revenue), c: "#0e7490", tip: t("часть общей выручки от вернувшихся клиентов, не прибавлять второй раз", "частина загальної виручки від клієнтів, що повернулись; не додавати вдруге") },
                  { l: t("Прибыль после рекламы", "Прибуток після реклами"), v: profitability.marketing_profit == null ? "—" : moneyUah(profitability.marketing_profit), c: Number(profitability.marketing_profit) >= 0 ? "var(--rd-success)" : "var(--rd-error)", tip: t("валовая прибыль (выручка − себестоимость) минус реклама", "валовий прибуток (виручка − собівартість) мінус реклама") },
                ],
              },
              {
                label: t("РЕКЛАМА И ОКУПАЕМОСТЬ", "РЕКЛАМА Й ОКУПНІСТЬ"),
                tiles: [
                  { l: t("Реклама за период", "Реклама за період"), v: <>{moneyUsd(paidSummary.spend)}{profitability.ad_spend_uah != null && <span style={{ fontSize: 13, color: "var(--rd-text2)", fontWeight: 400 }}> / {moneyUah(profitability.ad_spend_uah)}</span>}</>, c: "var(--rd-error)", tip: t("Расход Ads Manager; гривна — по официальному курсу НБУ за каждый день", "Витрати Ads Manager; гривня — за офіційним курсом НБУ на кожен день"), sub: paidSummary.avg_fx ? t("курс НБУ ≈ ", "курс НБУ ≈ ") + paidSummary.avg_fx + " ₴/$" : undefined },
                  { l: t("Общий ROAS", "Загальний ROAS"), v: profitability.blended_roas == null ? "—" : profitability.blended_roas + "×", c: "var(--rd-primary)", tip: t("вся выручка ÷ реклама: сколько гривен вернула 1 грн рекламы", "вся виручка ÷ реклама: скільки гривень повернула 1 грн реклами") },
                  { l: t("ROAS с точным ID", "ROAS з точним ID"), v: profitability.exact_ad_roas == null ? "—" : profitability.exact_ad_roas + "×", c: "var(--rd-purple)", tip: t("только продажи с доказанной меткой объявления; «—» = таких продаж пока нет", "лише продажі з доведеною міткою оголошення; «—» = таких продажів поки немає") },
                  { l: "ROMI", v: profitability.romi == null ? "—" : profitability.romi + "%", c: Number(profitability.romi) >= 0 ? "var(--rd-success)" : "var(--rd-error)", tip: t("(валовая прибыль − реклама) ÷ реклама, в %", "(валовий прибуток − реклама) ÷ реклама, у %") },
                ],
              },
            ].map((group: any) => (
              <div key={group.label} style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 10, color: "var(--rd-text2)", textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 700, margin: "0 0 8px" }}>{group.label}</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 14 }}>
                  {group.tiles.map((tile: any) => (
                    <div key={tile.l} className="rd-tile">
                      <div style={{ fontSize: 12, color: "var(--rd-text2)", marginBottom: 4, display: "flex", alignItems: "center" }}>{tile.l} {tile.tip && <InfoI tip={tile.tip} />}</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: tile.c, marginBottom: tile.sub ? 6 : 0 }}>{tile.v}</div>
                      {tile.sub && <div style={{ fontSize: 11, color: "var(--rd-text2)" }}>{tile.sub}</div>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {/* «Деталізація за днями» (макет 27.08): шапка-панель з пошуком дати і скачуванням CSV */}
          <div className="rd-card" style={{ padding: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 12, marginTop: 20 }}>
            <div>
              <b style={{ fontSize: 16, color: "var(--rd-text)", display: "flex", alignItems: "center", gap: 8 }}><Icon n="list" size={18} style={{ color: "var(--rd-primary)" }} /> {t("Детализация по дням", "Деталізація за днями")}</b>
              <div style={{ fontSize: 12, color: "var(--rd-text2)", marginTop: 2 }}>{t("Сводная статистика по всем каналам", "Зведена статистика по всіх каналах")}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ position: "relative" }}>
                <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", display: "inline-flex" }}><Icon n="search" size={16} style={{ color: "var(--rd-text2)" }} /></span>
                <input value={daySearch} onChange={(e) => setDaySearch(e.target.value)} placeholder={t("Поиск даты…", "Пошук дати…")}
                  style={{ paddingLeft: 34, paddingRight: 12, height: 36, border: "1px solid var(--rd-border)", borderRadius: 6, fontSize: 13, width: 180, outline: "none", background: "var(--rd-card)", color: "var(--rd-text)", boxSizing: "border-box" }} />
              </div>
              <button onClick={downloadDailyCsv} title={t("Скачать таблицу файлом (CSV, открывается в Excel)", "Скачати таблицю файлом (CSV, відкривається в Excel)")}
                style={{ width: 36, height: 36, border: "1px solid var(--rd-border)", borderRadius: 6, background: "var(--rd-card)", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                <Icon n="download" size={16} style={{ color: "var(--rd-text2)" }} />
              </button>
            </div>
          </div>
          <DailySalesTable rows={dailyFiltered} t={t} />
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
            t("Расход", "Витрати"), t("Показы", "Покази"), t("Клики", "Кліки"), "CTR", t("Результат", "Результат"), t("Подписки", "Підписки"), t("Цена подписки", "Ціна підписки"), t("Диалоги Meta", "Діалоги Meta"), t("Лиды Meta", "Ліди Meta"), t("Лиды CRM", "Ліди CRM"), t("Цена диалога", "Ціна діалогу"),
          ], adRows, t("За выбранный период реклама не показывалась", "За вибраний період реклама не показувалась"), 1360, [
            t("Название из Ads Manager", "Назва з Ads Manager"),
            t("Потрачено за период, $", "Витрачено за період, $"),
            t("Сколько раз показали рекламу", "Скільки разів показали рекламу"),
            t("Все клики по рекламе", "Усі кліки по рекламі"),
            t("% кликов от показов", "% кліків від показів"),
            t("Как «Результаты» в кабинете: по цели кампании — переписки, QuizStart, визиты профиля", "Як «Результати» в кабінеті: за ціллю кампанії — переписки, QuizStart, візити профілю"),
            t("Подписки в Instagram из отчёта Ads Manager", "Підписки в Instagram зі звіту Ads Manager"),
            t("расход ÷ подписки", "витрати ÷ підписки"),
            t("Начатые переписки по данным Meta (7 дней после клика)", "Розпочаті переписки за даними Meta (7 днів після кліку)"),
            t("Лиды по подсчёту Meta (её окно атрибуции)", "Ліди за підрахунком Meta (її вікно атрибуції)"),
            t("Реальные карточки CRM с меткой этого объявления", "Реальні картки CRM з міткою цього оголошення"),
            t("расход ÷ начатые переписки", "витрати ÷ розпочаті переписки"),
          ])}
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
    r.followers_gained == null ? "—" : <b style={{ color: r.followers_gained > 0 ? "var(--rd-success)" : r.followers_gained < 0 ? "var(--rd-error)" : "var(--rd-text2)" }}>{r.followers_gained > 0 ? "+" : ""}{count(r.followers_gained)}</b>,
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
      <thead style={{ position: "sticky", top: 0, zIndex: 3 }}><tr>{headers.map((header, i) => <ResizableTh key={header.s} label={<Tip text={header.tip}>{header.s}<span style={{ opacity: .45, marginLeft: 3, fontSize: 10, fontWeight: 400 }}>ⓘ</span></Tip>} width={cw.widths[i]} onResize={(w) => cw.set(i, w)} thStyle={{ ...th, whiteSpace: "normal", verticalAlign: "bottom", background: "var(--rd-muted)", fontSize: 10.5, lineHeight: 1.25 }} />)}</tr></thead>
      <tbody>{rows.length ? paged.map((r: any) => {
        const isOpen = expanded.has(r.date);
        return <Fragment key={r.date}>
          <tr style={{ background: isOpen ? "var(--rd-muted)" : undefined }}>
            <td style={td}>
              <button
                type="button"
                aria-expanded={isOpen}
                aria-label={t(`Показать сделки за ${r.date}`, `Показати угоди за ${r.date}`)}
                onClick={() => toggle(r.date)}
                style={{ ...dayToggle, color: isOpen ? "var(--rd-primary)" : "var(--rd-text)" }}
              >
                <span style={{ width: 18, color: "var(--rd-primary)" }}>{isOpen ? "▾" : "▸"}</span>
                {new Date(`${r.date}T12:00:00`).toLocaleDateString("ru-RU")}
              </button>
            </td>
            {values(r).map((value, index) => <td key={index} style={td}>{value}</td>)}
          </tr>
          {isOpen && <tr>
            <td colSpan={headers.length} style={{ padding: 0, borderBottom: "1px solid var(--rd-border)" }}>
              <div style={{ padding: "14px 20px 18px", background: "var(--rd-bg)" }}>
                <div style={{ fontSize: 12, color: "var(--rd-text2)", fontStyle: "italic", marginBottom: 10 }}>
                  {t(
                    "Расшифровка ровно этой строки. Повторные сделки уже входят в общие продажи и выручку.",
                    "Розшифровка саме цього рядка. Повторні угоди вже входять у загальні продажі та виручку.",
                  )}
                </div>
                <DailyDealSection
                  title={t("Первичные оплаченные сделки", "Первинні оплачені угоди")}
                  rows={r.deals?.primary || []}
                  color="var(--rd-success)"
                  t={t}
                />
                <DailyDealSection
                  title={t("Повторные оплаченные сделки", "Повторні оплачені угоди")}
                  rows={r.deals?.repeat || []}
                  color="var(--rd-primary)"
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

/* Розшифровка дня (макет crm_3): заголовок секції кольором ПОЗА рамкою, таблиця угод у білій картці */
function DailyDealSection({ title, rows, color, t }: { title: string; rows: any[]; color: string; t: (ru: string, ua: string) => string }) {
  const sectionTotal = rows.reduce((sum, row) => sum + Number(row.paid_today || 0), 0);
  return <div style={{ marginTop: 12 }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "0 2px 8px", alignItems: "center" }}>
      <b style={{ color, fontSize: 13.5 }}>{title}</b>
      <span style={{ fontWeight: 800, color, fontSize: 13.5 }}>{count(rows.length)} · {moneyUah(sectionTotal)}</span>
    </div>
    {rows.length ? <div style={{ overflowX: "auto", border: "1px solid var(--rd-border)", borderRadius: 8, background: "var(--rd-card)" }}>
      <table style={{ width: "100%", minWidth: 1040, borderCollapse: "collapse" }}>
        <thead><tr>
          {[t("Сделка", "Угода"), t("Клиент", "Клієнт"), t("Воронка / стадия", "Воронка / стадія"), t("Менеджер", "Менеджер"), t("Способ оплаты", "Спосіб оплати"), t("Время", "Час"), t("Оплачено в этот день", "Сплачено цього дня"), t("Сумма сделки", "Сума угоди")].map((header) => <th key={header} style={{ ...th, padding: "8px 10px", fontSize: 11 }}>{header}</th>)}
        </tr></thead>
        <tbody>{rows.map((deal: any) => <tr key={deal.deal_id}>
          <td style={dealTd}><a href={`/deals/${deal.deal_id}`} style={{ color: "var(--rd-primary)", fontWeight: 750 }}>#{deal.deal_id} · {deal.title || t("Без названия", "Без назви")}</a>{deal.meta_attributed && <div style={{ color: "var(--rd-purple)", fontSize: 10, marginTop: 2 }}>{t("Есть точный ID Meta", "Є точний ID Meta")}</div>}</td>
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
/* Шапки таблиць за макетами crm_2/crm_3: ВЕЛИКІ літери, сірий текст, молочний фон */
const th: any = { textAlign: "left", padding: "12px 12px", fontSize: 11, fontWeight: 600, color: "var(--rd-text2)", textTransform: "uppercase", letterSpacing: ".04em", borderBottom: "1px solid var(--rd-border)", whiteSpace: "nowrap", background: "var(--rd-muted)" };
const td: any = { padding: "10px 12px", fontSize: 13, color: "var(--rd-text)", borderBottom: "1px solid var(--rd-border)", verticalAlign: "top" };
const dealTd: any = { padding: "9px 10px", fontSize: 12, borderTop: "1px solid var(--rd-border)", verticalAlign: "top" };
const dayToggle: any = { minHeight: 36, padding: "0 8px 0 0", border: 0, background: "transparent", color: "#0f172a", fontWeight: 750, cursor: "pointer", display: "inline-flex", alignItems: "center", whiteSpace: "nowrap", textAlign: "left" };
/* Поля дат у шапці редизайну: без рамки, всередині спільного «чипа» з календариком */
const rdDate: any = { border: "none", padding: 0, fontSize: 13, color: "var(--rd-text)", background: "transparent", outline: "none", width: 118, fontFamily: "inherit" };
