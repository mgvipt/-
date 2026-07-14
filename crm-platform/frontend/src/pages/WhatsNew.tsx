/* Сторінка «Що нового» / Інструкції — історія доробок CRM простою мовою, згрупована по БЛОКАХ (розділах).
 * Дані з /api/changelog/ (модель ChangeLogEntry, поле section). Блок пишеться ОДИН раз, під ним список пунктів. */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

interface Entry { id: number; date: string; section: string; title: string; body: string; }

/* Іконка блоку за ключовим словом у назві розділу */
function sectionIcon(name: string) {
  const n = (name || "").toLowerCase();
  if (n.includes("инанс") || n.includes("інанс") || n.includes("грош") || n.includes("плат")) return "💰";
  if (n.includes("клад")) return "📦";
  if (n.includes("лиент") || n.includes("лієнт") || n.includes("контакт")) return "👥";
  if (n.includes("родаж") || n.includes("сделк") || n.includes("угод")) return "📈";
  if (n.includes("елефон") || n.includes("дзвін") || n.includes("звонк")) return "☎️";
  if (n.includes("автомат") || n.includes("агент") || n.includes("ии") || n.includes("ші")) return "🤖";
  return "📋";
}

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

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleDateString("uk-UA", { day: "2-digit", month: "long", year: "numeric" }); }
  catch { return iso; }
}

export default function WhatsNew() {
  const { t } = useLang();
  const [rows, setRows] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<string>("");   // "" = всі блоки

  useEffect(() => {
    api.get<Entry[]>("/api/changelog/").then((d) => setRows(d || [])).catch(() => setRows([])).finally(() => setLoading(false));
  }, []);

  const GENERAL = t("Общее", "Загальне");

  /* Порядок блоків: Фінанси перші, далі за кількістю пунктів, «Загальне» — останнє */
  const groups = useMemo(() => {
    const map = new Map<string, Entry[]>();
    for (const e of rows) {
      const key = (e.section || "").trim() || GENERAL;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(e);
    }
    const keys = Array.from(map.keys());
    keys.sort((a, b) => {
      const fa = /инанс|інанс/i.test(a) ? 0 : 1, fb = /инанс|інанс/i.test(b) ? 0 : 1;
      if (fa !== fb) return fa - fb;
      if (a === GENERAL) return 1;
      if (b === GENERAL) return -1;
      return (map.get(b)!.length - map.get(a)!.length) || a.localeCompare(b);
    });
    return keys.map((k) => ({ name: k, items: map.get(k)! }));
  }, [rows, GENERAL]);

  const shown = active ? groups.filter((g) => g.name === active) : groups;

  return (
    <div className="scroll pad" style={{ maxWidth: 880, margin: "0 auto" }}>
      <div className="panel" style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 20, fontWeight: 800, color: "#0f172a" }}>📋 {t("Инструкции и что нового", "Інструкції та що нового")}</div>
        <div className="muted" style={{ fontSize: 13, marginTop: 6, lineHeight: 1.55 }}>
          {t("Как всё работает — простым языком, по блокам. Зайди в нужный блок (например «Финансы») и изучи по пунктам. Пополняется при каждом изменении.",
             "Як усе працює — простою мовою, по блоках. Зайди у потрібний блок (наприклад «Фінанси») і вивчи по пунктах. Поповнюється при кожній зміні.")}
        </div>
      </div>

      {/* Чіпи-фільтри блоків */}
      {!loading && groups.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          <span onClick={() => setActive("")} style={chip(active === "")}>
            {t("Все", "Усі")} <span style={{ opacity: .6 }}>· {rows.length}</span>
          </span>
          {groups.map((g) => (
            <span key={g.name} onClick={() => setActive(g.name === active ? "" : g.name)} style={chip(active === g.name)}>
              {sectionIcon(g.name)} {g.name} <span style={{ opacity: .6 }}>· {g.items.length}</span>
            </span>
          ))}
        </div>
      )}

      {loading && <div className="muted" style={{ padding: 12 }}>{t("Загрузка…", "Завантаження…")}</div>}
      {!loading && rows.length === 0 && <div className="muted" style={{ padding: 12 }}>{t("Пока пусто", "Поки порожньо")}</div>}

      {shown.map((g) => (
        <div key={g.name} style={{ marginBottom: 26 }}>
          {/* Заголовок блоку — ОДИН раз над списком пунктів */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "0 0 12px", padding: "10px 14px", borderRadius: 12, background: "linear-gradient(90deg,#fdf3ec,#fff)", border: "1px solid #f0e2d7" }}>
            <span style={{ fontSize: 22 }}>{sectionIcon(g.name)}</span>
            <b style={{ fontSize: 17, color: "#8a4b2a", letterSpacing: .2 }}>{g.name}</b>
            <span className="muted" style={{ fontSize: 12, marginLeft: "auto" }}>{g.items.length} {t("пунктов", "пунктів")}</span>
          </div>

          {/* Пункти блоку */}
          {g.items.map((e) => (
            <div key={e.id} className="panel" style={{ marginBottom: 12, marginLeft: 6, borderLeft: "4px solid var(--brand, #C67D5F)" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
                <b style={{ fontSize: 15.5, color: "#0f172a" }}>{e.title}</b>
                <span style={{ background: "#f1f5f9", color: "#64748b", fontSize: 11, fontWeight: 600, padding: "2px 9px", borderRadius: 999, whiteSpace: "nowrap", marginLeft: "auto" }}>{fmtDate(e.date)}</span>
              </div>
              <div style={{ fontSize: 13.5, color: "#475569" }}>
                {(e.body || "").split("\n").map((ln, i) => renderLine(ln, i))}
              </div>
            </div>
          ))}
        </div>
      ))}
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
