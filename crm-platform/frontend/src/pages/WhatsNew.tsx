/* Сторінка «Що нового» — історія доробок CRM простою мовою.
 * Дані з /api/changelog/ (модель ChangeLogEntry). Поповнюється при кожній зміні. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

interface Entry { id: number; date: string; title: string; body: string; }

/* Мінімальний рендер рядка: **жирний** + • для списків */
function renderLine(line: string, key: number) {
  // Картинка: рядок виду ![підпис](/whatsnew/xxx.png) -> зображення (клік = відкрити повністю)
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
  useEffect(() => {
    api.get<Entry[]>("/api/changelog/").then((d) => setRows(d || [])).catch(() => setRows([])).finally(() => setLoading(false));
  }, []);

  return (
    <div className="scroll pad" style={{ maxWidth: 860, margin: "0 auto" }}>
      <div className="panel" style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 20, fontWeight: 800, color: "#0f172a" }}>📋 {t("Что нового в CRM", "Що нового в CRM")}</div>
        <div className="muted" style={{ fontSize: 13, marginTop: 6, lineHeight: 1.55 }}>
          {t("Живой журнал всех доработок простым языком. Пополняется при каждом изменении — новое сверху. Копия хранится на GitHub.",
             "Живий журнал усіх доробок простою мовою. Поповнюється при кожній зміні — нове зверху. Копія зберігається на GitHub.")}
        </div>
      </div>

      {loading && <div className="muted" style={{ padding: 12 }}>{t("Загрузка…", "Завантаження…")}</div>}
      {!loading && rows.length === 0 && <div className="muted" style={{ padding: 12 }}>{t("Пока пусто", "Поки порожньо")}</div>}

      {rows.map((e) => (
        <div key={e.id} className="panel" style={{ marginBottom: 12, borderLeft: "4px solid var(--brand, #C67D5F)" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
            <span style={{ background: "#fdf3ec", color: "#b45309", fontSize: 11.5, fontWeight: 700, padding: "3px 10px", borderRadius: 999, whiteSpace: "nowrap" }}>{fmtDate(e.date)}</span>
            <b style={{ fontSize: 15.5, color: "#0f172a" }}>{e.title}</b>
          </div>
          <div style={{ fontSize: 13.5, color: "#475569" }}>
            {(e.body || "").split("\n").map((ln, i) => renderLine(ln, i))}
          </div>
        </div>
      ))}
    </div>
  );
}
