/* Сторінка «Що нового» / Інструкції — історія доробок CRM простою мовою, згрупована по БЛОКАХ (розділах).
 * Дані з /api/changelog/ (модель ChangeLogEntry). Двомовність uk/ru: контент і назви категорій показуються за мовою.
 * Категорії групуються по МАШИННОМУ ключу section_key (щоб Фінанси/Финансы не дублювались). */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

interface Entry {
  id: number; date: string; section_key?: string; section?: string;
  title_uk?: string; title_ru?: string; body_uk?: string; body_ru?: string;
  title?: string; body?: string; // legacy fallback
}

/* Довідник категорій: ключ → іконка + назва двома мовами + порядок. Одне джерело правди. */
const CATS: Record<string, { icon: string; uk: string; ru: string; order: number }> = {
  finance:   { icon: "💰", uk: "Фінанси",          ru: "Финансы",          order: 1 },
  warehouse: { icon: "📦", uk: "Склад",            ru: "Склад",            order: 2 },
  sales:     { icon: "📈", uk: "Продажі",          ru: "Продажи",          order: 3 },
  clients:   { icon: "👥", uk: "Клієнти",          ru: "Клиенты",          order: 4 },
  delivery:  { icon: "🚚", uk: "Доставка НП",      ru: "Доставка НП",      order: 5 },
  shop:      { icon: "🛒", uk: "Інтернет-магазин", ru: "Интернет-магазин", order: 6 },
  telephony: { icon: "☎️", uk: "Телефонія",        ru: "Телефония",        order: 7 },
  general:   { icon: "📋", uk: "Загальне",         ru: "Общее",            order: 99 },
};
function catMeta(key: string) { return CATS[key] || CATS.general; }

/* Мінімальний рендер рядка: **жирний** + • для списків + картинки */
function renderLine(line: string, key: number) {
  const img = line.trim().match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
  if (img) {
    return (
      <a key={key} href={img[2]} target="_blank" rel="noreferrer" style={{ display: "block", margin: "10px 0" }}>
        <img src={img[2]} alt={img[1]} loading="lazy" style={{ maxWidth: "100%", borderRadius: 10, border: "1px solid #e2e8f0", boxShadow: "0 1px 4px rgba(0,0,0,.08)", cursor: "zoom-in" }} />
        {img[1] && <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>{img[1]}</div>}
      </a>
    );
  }
  const isBullet = line.trimStart().startsWith("- ");
  const text = isBullet ? line.trimStart().slice(2) : line;
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  const spans = parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <b key={i} style={{ color: "#0f172a" }}>{p.slice(2, -2)}</b>
      : <span key={i}>{p}</span>
  );
  if (isBullet) {
    return (
      <div key={key} style={{ display: "flex", gap: 8, margin: "3px 0", lineHeight: 1.5 }}>
        <span style={{ color: "var(--brand, #C67D5F)", flexShrink: 0 }}>•</span>
        <span>{spans}</span>
      </div>
    );
  }
  return <div key={key} style={{ margin: "6px 0", lineHeight: 1.5 }}>{spans}</div>;
}

function fmtDate(iso: string, lang: string) {
  try { return new Date(iso).toLocaleDateString(lang === "uk" ? "uk-UA" : "ru-RU", { day: "2-digit", month: "long", year: "numeric" }); }
  catch { return iso; }
}

export default function WhatsNew() {
  const { t, lang, setLang } = useLang();
  const [rows, setRows] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<string>("");   // "" = всі блоки (по section_key)

  useEffect(() => {
    api.get<Entry[]>("/api/changelog/").then((d) => setRows(d || [])).catch(() => setRows([])).finally(() => setLoading(false));
  }, []);

  /* Витягнути title/body за мовою (з fallback на іншу мову / legacy) */
  const titleOf = (e: Entry) => (lang === "uk" ? (e.title_uk || e.title || e.title_ru) : (e.title_ru || e.title || e.title_uk)) || "";
  const bodyOf = (e: Entry) => (lang === "uk" ? (e.body_uk || e.body || e.body_ru) : (e.body_ru || e.body || e.body_uk)) || "";
  const keyOf = (e: Entry) => (e.section_key || "general");

  /* Групування по МАШИННОМУ ключу — жодних дублів Фінанси/Финансы */
  const groups = useMemo(() => {
    const map = new Map<string, Entry[]>();
    for (const e of rows) {
      const k = keyOf(e);
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(e);
    }
    const keys = Array.from(map.keys());
    keys.sort((a, b) => {
      const oa = catMeta(a).order, ob = catMeta(b).order;
      if (oa !== ob) return oa - ob;
      return (map.get(b)!.length - map.get(a)!.length);
    });
    return keys.map((k) => ({ key: k, items: map.get(k)! }));
  }, [rows]);

  const shown = active ? groups.filter((g) => g.key === active) : groups;

  return (
    <div className="scroll pad" style={{ maxWidth: 880, margin: "0 auto" }}>
      <div className="panel" style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: "#0f172a" }}>📋 {t("Инструкции и что нового", "Інструкції та що нового")}</div>
            <div className="muted" style={{ fontSize: 13, marginTop: 6, lineHeight: 1.55 }}>
              {t("Как всё работает — простым языком, по блокам. Зайди в нужный блок (например «Финансы») и изучи по пунктам. Пополняется при каждом изменении.",
                 "Як усе працює — простою мовою, по блоках. Зайди у потрібний блок (наприклад «Фінанси») і вивчи по пунктах. Поповнюється при кожній зміні.")}
            </div>
          </div>
          {/* Перемикач мови інструкцій — окремо, щоб зручно було вивчати рос/укр */}
          <div style={{ display: "flex", gap: 0, border: "1.5px solid #e2e8f0", borderRadius: 999, overflow: "hidden", flexShrink: 0 }} title={t("Язык инструкций", "Мова інструкцій")}>
            <button onClick={() => setLang("uk")} style={langBtn(lang === "uk")}>🇺🇦 UK</button>
            <button onClick={() => setLang("ru")} style={langBtn(lang === "ru")}>🇷🇺 RU</button>
          </div>
        </div>
      </div>

      {/* Чіпи-фільтри блоків (назва за мовою, порядок і лічильник — по ключу) */}
      {!loading && groups.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          <span onClick={() => setActive("")} style={chip(active === "")}>
            {t("Все", "Усі")} <span style={{ opacity: .6 }}>· {rows.length}</span>
          </span>
          {groups.map((g) => {
            const m = catMeta(g.key);
            return (
              <span key={g.key} onClick={() => setActive(g.key === active ? "" : g.key)} style={chip(active === g.key)}>
                {m.icon} {lang === "uk" ? m.uk : m.ru} <span style={{ opacity: .6 }}>· {g.items.length}</span>
              </span>
            );
          })}
        </div>
      )}

      {loading && <div className="muted" style={{ padding: 12 }}>{t("Загрузка…", "Завантаження…")}</div>}
      {!loading && rows.length === 0 && <div className="muted" style={{ padding: 12 }}>{t("Пока пусто", "Поки порожньо")}</div>}

      {shown.map((g) => {
        const m = catMeta(g.key);
        return (
          <div key={g.key} style={{ marginBottom: 26 }}>
            {/* Заголовок блоку — ОДИН раз над списком пунктів */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "0 0 12px", padding: "10px 14px", borderRadius: 12, background: "linear-gradient(90deg,#fdf3ec,#fff)", border: "1px solid #f0e2d7" }}>
              <span style={{ fontSize: 22 }}>{m.icon}</span>
              <b style={{ fontSize: 17, color: "#8a4b2a", letterSpacing: .2 }}>{lang === "uk" ? m.uk : m.ru}</b>
              <span className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>{g.items.length} {t("пунктов", "пунктів")}</span>
            </div>

            {/* Пункти блоку */}
            {g.items.map((e) => (
              <div key={e.id} className="panel" style={{ marginBottom: 12, marginLeft: 6, borderLeft: "4px solid var(--brand, #C67D5F)" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
                  <b style={{ fontSize: 15.5, color: "#0f172a" }}>{titleOf(e)}</b>
                  <span style={{ background: "#f1f5f9", color: "#64748b", fontSize: 11, fontWeight: 600, padding: "2px 9px", borderRadius: 999, whiteSpace: "nowrap", marginLeft: "auto" }}>{fmtDate(e.date, lang)}</span>
                </div>
                <div style={{ fontSize: 13.5, color: "#475569" }}>
                  {bodyOf(e).split("\n").map((ln, i) => renderLine(ln, i))}
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function chip(on: boolean): React.CSSProperties {
  return {
    cursor: "pointer", userSelect: "none", fontSize: 13, fontWeight: 700,
    padding: "6px 13px", borderRadius: 999, whiteSpace: "nowrap",
    background: on ? "var(--brand, #C67D5F)" : "#fff",
    color: on ? "#fff" : "#475569",
    border: "1.5px solid " + (on ? "var(--brand, #C67D5F)" : "#e2e8f0"),
  };
}

function langBtn(on: boolean): React.CSSProperties {
  return {
    cursor: "pointer", fontSize: 12.5, fontWeight: 700, padding: "6px 12px",
    border: "none", background: on ? "var(--brand, #C67D5F)" : "#fff",
    color: on ? "#fff" : "#64748b",
  };
}
