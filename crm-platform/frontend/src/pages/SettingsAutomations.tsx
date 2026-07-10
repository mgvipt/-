import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

export default function SettingsAutomations() {
  const { t } = useLang();
  const [funnels, setFunnels] = useState<any[]>([]);
  const [rules, setRules] = useState<any[]>([]);
  const [fid, setFid] = useState<number | null>(null);

  function loadRules() { api.get<any>("/api/automation-rules/").then((d) => setRules(d.results || d)); }
  useEffect(() => {
    api.get<any>("/api/funnels/").then((d) => { const fs = d.results || d; setFunnels(fs); if (fs[0]) setFid(fs[0].id); });
    loadRules();
  }, []);

  async function patch(id: number, body: any) { try { await api.patch(`/api/automation-rules/${id}/`, body); } catch { /* */ } }
  const funnel = funnels.find((f) => f.id === fid);
  const fRules = rules.filter((r) => r.funnel === fid);

  return (
    <div>
      <div className="note">{t(
        "Логика движения по воронке: при каком событии лид/сделка переходит на следующую стадию. Это тот же движок, что двигает карточки — меняешь здесь, меняется поведение. Каждый переход пишется в Историю изменений.",
        "Логіка руху по воронці: за якої події лід/угода переходить на наступну стадію. Це той самий двигун, що рухає картки — змінюєш тут, змінюється поведінка. Кожен перехід пишеться в Історію змін.")}</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "10px 0 14px" }}>
        {funnels.map((f) => (
          <button key={f.id} onClick={() => setFid(f.id)}
            style={{ fontSize: 13, padding: "6px 12px", borderRadius: 16, cursor: "pointer",
              border: "1px solid " + (fid === f.id ? "var(--brand)" : "#e2e8f0"),
              background: fid === f.id ? "var(--brand)" : "#fff", color: fid === f.id ? "#fff" : "#475569" }}>{f.name}</button>
        ))}
      </div>
      {(funnel?.stages || []).slice().sort((a: any, b: any) => a.order - b.order).map((st: any) => {
        const into = fRules.filter((r) => r.to_stage === st.id);
        return (
          <div key={st.id} className="panel" style={{ margin: "0 0 10px" }}>
            <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 6, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 12, height: 12, borderRadius: 4, background: st.color || "#94a3b8", display: "inline-block" }} />
              {st.name}
            </div>
            {into.length === 0 && <div className="muted" style={{ fontSize: 12 }}>{t("Сюда не ведёт ни одно авто-правило (только вручную).", "Сюди не веде жодне авто-правило (тільки вручну).")}</div>}
            {into.map((r) => (
              <div key={r.id} style={{ borderLeft: "3px solid var(--brand)", padding: "6px 10px", marginBottom: 6, background: "#f8fafc", borderRadius: "0 8px 8px 0" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                  <span>{t("Когда", "Коли")}: <b>{r.trigger_display}</b> {t("на стадии", "на стадії")} «{r.from_stage_name}» → «{r.to_stage_name}»</span>
                  <div style={{ flex: 1 }} />
                  <span className={"toggle" + (r.enabled ? " on" : "")} onClick={() => { patch(r.id, { enabled: !r.enabled }); setRules((rs) => rs.map((x) => x.id === r.id ? { ...x, enabled: !x.enabled } : x)); }} />
                </div>
                <textarea defaultValue={r.description} onBlur={(e) => patch(r.id, { description: e.target.value })}
                  placeholder={t("Описание правила простыми словами (для обучения)…", "Опис правила простими словами (для навчання)…")}
                  style={{ width: "100%", minHeight: 44, fontSize: 12.5, padding: 7, marginTop: 6, borderRadius: 6, border: "1px solid #e2e8f0", resize: "vertical", boxSizing: "border-box" }} />
              </div>
            ))}
          </div>
        );
      })}
      <div className="note" style={{ marginTop: 10 }}>{t(
        "Полный редактор условий входа и действий (создать задачу складу/тонировке, авто-чек, авто-ТТН, дожим) + встроенный AI-агент — следующий этап.",
        "Повний редактор умов входу та дій (створити задачу складу/тонуванню, авто-чек, авто-ТТН, дожим) + вбудований AI-агент — наступний етап.")}</div>
    </div>
  );
}
