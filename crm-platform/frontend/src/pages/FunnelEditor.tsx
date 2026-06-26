/* Редактор воронки: перейменувати стадії, змінити колір, додати «+» у будь-яке
 * місце, перетягнути порядок (↑↓), видалити. Зберігає одним запитом save_stages.
 * Стадію з картками видалити не можна — бек поверне її у blocked. */
import { useState } from "react";
import { api, Funnel, Stage } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

type Row = { id?: number; name: string; color: string; is_won: boolean; is_lost: boolean };
const PRESETS = ["#3b82f6", "#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#14b8a6", "#ef4444", "#64748b", "#0ea5e9"];

export default function FunnelEditor({ funnel, onClose, onSaved }: { funnel: Funnel; onClose: () => void; onSaved: (f: Funnel) => void }) {
  const { t } = useLang();
  const [rows, setRows] = useState<Row[]>(funnel.stages.map((s: Stage) => ({ id: s.id, name: s.name, color: s.color, is_won: s.is_won, is_lost: s.is_lost })));
  const [saving, setSaving] = useState(false);
  const [warn, setWarn] = useState("");

  function patch(i: number, p: Partial<Row>) { setRows((r) => r.map((x, j) => (j === i ? { ...x, ...p } : x))); }
  function insertAt(i: number) { setRows((r) => [...r.slice(0, i), { name: t("Новая стадия","Нова стадія"), color: PRESETS[r.length % PRESETS.length], is_won: false, is_lost: false }, ...r.slice(i)]); }
  function remove(i: number) { setRows((r) => r.filter((_, j) => j !== i)); }
  function move(i: number, d: number) {
    setRows((r) => { const n = [...r]; const j = i + d; if (j < 0 || j >= n.length) return n; [n[i], n[j]] = [n[j], n[i]]; return n; });
  }

  async function save() {
    setSaving(true); setWarn("");
    try {
      const f = await api.post<Funnel & { blocked: string[] }>(`/api/funnels/${funnel.id}/save_stages/`, { stages: rows });
      if (f.blocked && f.blocked.length) { setWarn(t("Не удалено (есть карточки)","Не видалено (є картки)") + `: ${f.blocked.join(", ")}`); setRows(f.stages.map((s) => ({ id: s.id, name: s.name, color: s.color, is_won: s.is_won, is_lost: s.is_lost }))); }
      else onSaved(f);
    } catch { setWarn(t("Ошибка сохранения","Помилка збереження")); }
    finally { setSaving(false); }
  }

  const PlusRow = ({ i }: { i: number }) => (
    <div style={{ height: 14, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <button onClick={() => insertAt(i)} title={t("Добавить стадию сюда","Додати стадію сюди")}
        style={{ width: 22, height: 22, borderRadius: 11, border: "1px dashed #94a3b8", background: "#fff", color: "#475569", cursor: "pointer", fontSize: 14, lineHeight: 1, padding: 0 }}>+</button>
    </div>
  );

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 16, padding: 22, width: 560, maxHeight: "86vh", overflowY: "auto", boxShadow: "0 24px 60px rgba(15,23,42,.35)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <h3 style={{ margin: 0, fontSize: 18 }}>{t("Настройка воронки","Налаштування воронки")}</h3>
          <span className="muted" style={{ fontSize: 13 }}>· {funnel.name}</span>
        </div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>{t("Переименуй, измени цвет, добавь «+» в любое место, перетащи ↑↓ или удали. «✓ Выиграно» / «✕ Проиграно» обозначают финальные стадии.","Перейменуй, зміни колір, додай «+» у будь-яке місце, перетягни ↑↓ або видали. «✓ Виграно» / «✕ Програно» позначають фінальні стадії.")}</div>

        <PlusRow i={0} />
        {rows.map((r, i) => (
          <div key={i}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, padding: "8px 10px" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <button onClick={() => move(i, -1)} disabled={i === 0} style={{ border: "none", background: "none", cursor: "pointer", opacity: i === 0 ? 0.3 : 0.7, fontSize: 11, padding: 0 }}>▲</button>
                <button onClick={() => move(i, 1)} disabled={i === rows.length - 1} style={{ border: "none", background: "none", cursor: "pointer", opacity: i === rows.length - 1 ? 0.3 : 0.7, fontSize: 11, padding: 0 }}>▼</button>
              </div>
              <span style={{ width: 14, height: 30, borderRadius: 5, background: r.color, flex: "0 0 auto" }} />
              <input value={r.name} onChange={(e) => patch(i, { name: e.target.value })}
                style={{ flex: 1, height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 9px", fontWeight: 600 }} />
              <input type="color" value={r.color} onChange={(e) => patch(i, { color: e.target.value })}
                title={t("Свой цвет","Свій колір")} style={{ width: 30, height: 30, border: "none", background: "none", padding: 0, cursor: "pointer" }} />
              <button onClick={() => patch(i, { is_won: !r.is_won, is_lost: false })} title={t("Стадия «Выиграно»","Стадія «Виграно»")}
                style={{ width: 30, height: 30, borderRadius: 7, border: "1px solid " + (r.is_won ? "#10b981" : "#cbd5e1"), background: r.is_won ? "#10b981" : "#fff", color: r.is_won ? "#fff" : "#94a3b8", cursor: "pointer" }}>✓</button>
              <button onClick={() => patch(i, { is_lost: !r.is_lost, is_won: false })} title={t("Стадия «Проиграно»","Стадія «Програно»")}
                style={{ width: 30, height: 30, borderRadius: 7, border: "1px solid " + (r.is_lost ? "#ef4444" : "#cbd5e1"), background: r.is_lost ? "#ef4444" : "#fff", color: r.is_lost ? "#fff" : "#94a3b8", cursor: "pointer" }}>✕</button>
              <button onClick={() => remove(i)} title={t("Удалить стадию","Видалити стадію")}
                style={{ width: 30, height: 30, borderRadius: 7, border: "1px solid #fecaca", background: "#fef2f2", color: "#dc2626", cursor: "pointer" }}><Icon n="🗑" size={16} /></button>
            </div>
            <div style={{ display: "flex", gap: 4, margin: "4px 0 0 30px" }}>
              {PRESETS.map((c) => <span key={c} onClick={() => patch(i, { color: c })} style={{ width: 16, height: 16, borderRadius: 4, background: c, cursor: "pointer", border: r.color === c ? "2px solid #0f172a" : "1px solid #e2e8f0" }} />)}
            </div>
            <PlusRow i={i + 1} />
          </div>
        ))}

        {warn && <div style={{ background: "#fffbeb", border: "1px solid #fde68a", color: "#b45309", borderRadius: 8, padding: "8px 10px", fontSize: 13, marginTop: 8 }}><Icon n="⚠" size={15} /> {warn}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <button className="btn btn-light" style={{ flex: 1 }} onClick={onClose}>{t("Закрыть","Закрити")}</button>
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={save} disabled={saving}>{saving ? t("Сохранение…","Збереження…") : t("Сохранить воронку","Зберегти воронку")}</button>
        </div>
      </div>
    </div>
  );
}
