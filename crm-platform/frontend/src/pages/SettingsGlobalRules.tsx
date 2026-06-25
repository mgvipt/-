import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

const BLOCKS: [string, string][] = [
  ["products", "🛍 Товари"], ["sales", "🔻 Продажі"], ["automation", "⚙️ Автоматизації"],
  ["payments", "💳 Платежі"], ["novaposhta", "📦 Нова Пошта"], ["checkbox", "🧾 Чеки"],
  ["warehouse", "🏭 Склад"], ["followup", "🎯 Дожими"], ["general", "📋 Загальні"],
];

export default function SettingsGlobalRules() {
  const { t } = useLang();
  const [rules, setRules] = useState<any[]>([]);
  const [block, setBlock] = useState("products");

  function load() { api.get<any>("/api/global-rules/").then((d) => setRules(d.results || d)); }
  useEffect(() => { load(); }, []);

  async function patch(id: number, body: any) { try { await api.patch(`/api/global-rules/${id}/`, body); } catch { /* */ } }
  async function add() { await api.post("/api/global-rules/", { block, title: t("Новое правило", "Нове правило"), body: "" }); load(); }
  async function del(id: number) { if (!confirm(t("Удалить правило?", "Видалити правило?"))) return; await api.del(`/api/global-rules/${id}/`); load(); }

  const list = rules.filter((r) => r.block === block).sort((a, b) => a.priority - b.priority);

  return (
    <div>
      <div className="note">{t(
        "Здесь зафиксированы правила работы CRM по блокам — единый источник правды для обучения сотрудников и контекст для встроенного AI-агента. Редактируй прямо здесь.",
        "Тут зафіксовані правила роботи CRM по блоках — єдине джерело правди для навчання співробітників і контекст для вбудованого AI-агента. Редагуй прямо тут.")}</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "10px 0 14px" }}>
        {BLOCKS.map(([k, label]) => (
          <button key={k} onClick={() => setBlock(k)}
            style={{ fontSize: 13, padding: "6px 12px", borderRadius: 16, cursor: "pointer",
              border: "1px solid " + (block === k ? "var(--brand)" : "#e2e8f0"),
              background: block === k ? "var(--brand)" : "#fff", color: block === k ? "#fff" : "#475569",
              fontWeight: block === k ? 700 : 500 }}>{label}{rules.filter((r) => r.block === k).length ? ` (${rules.filter((r) => r.block === k).length})` : ""}</button>
        ))}
      </div>
      {list.map((r) => (
        <div key={r.id} className="panel" style={{ margin: "0 0 12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <input defaultValue={r.title} onBlur={(e) => patch(r.id, { title: e.target.value })}
              style={{ flex: 1, fontSize: 15, fontWeight: 700, border: "none", borderBottom: "1px solid #e2e8f0", padding: "4px 2px", background: "transparent" }} />
            <span className={"toggle" + (r.enabled ? " on" : "")} title={t("Включено", "Увімкнено")}
              onClick={() => { patch(r.id, { enabled: !r.enabled }); setRules((rs) => rs.map((x) => x.id === r.id ? { ...x, enabled: !x.enabled } : x)); }} />
            <span onClick={() => del(r.id)} style={{ cursor: "pointer", color: "#dc2626", fontSize: 18, lineHeight: 1 }} title={t("Удалить", "Видалити")}>✕</span>
          </div>
          <textarea defaultValue={r.body} onBlur={(e) => patch(r.id, { body: e.target.value })}
            placeholder={t("Текст правила (для сотрудников и AI-агента)…", "Текст правила (для співробітників і AI-агента)…")}
            style={{ width: "100%", minHeight: 120, fontSize: 13.5, lineHeight: 1.55, padding: 10, borderRadius: 8, border: "1px solid #e2e8f0", resize: "vertical", boxSizing: "border-box", whiteSpace: "pre-wrap" }} />
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{t("Обновлено", "Оновлено")}: {r.updated_at ? new Date(r.updated_at).toLocaleString("uk", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"}</div>
        </div>
      ))}
      {list.length === 0 && <div className="muted" style={{ padding: 16 }}>{t("В этом блоке пока нет правил.", "У цьому блоці поки немає правил.")}</div>}
      <button className="btn btn-primary" onClick={add}>{t("+ Добавить правило", "+ Додати правило")}</button>
    </div>
  );
}
