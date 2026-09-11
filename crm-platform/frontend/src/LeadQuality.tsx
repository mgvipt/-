/* Якість звернення (останній лід клієнта): Цільовий / Нецільовий (+ причина) / Коментар / Не відповів.
 * Одна відмітка на весь клієнтський контакт — показується в чаті, картках ліда, угоди та клієнта.
 * У конверсію менеджера йдуть лише цільові. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

type St = { lead_id: number | null; quality: string; reason: string; reason_label?: string; by?: string };

export default function LeadQuality({ contactId, convId }: { contactId?: number | null; convId?: number | null }) {
  const { t } = useLang();
  const base = convId ? `/api/conversations/${convId}/lead-quality/` : contactId ? `/api/contacts/${contactId}/lead-quality/` : "";
  const [st, setSt] = useState<St | null>(null);
  const [ntOpen, setNtOpen] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    setSt(null); setNtOpen(false); setErr("");
    if (!base) return;
    api.get<St>(base).then(setSt).catch(() => setSt(null));
  }, [base]);
  if (!base || !st || !st.lead_id) return null;

  const Q: [string, string, string, string][] = [
    ["target", t("Целевой", "Цільовий"), "#15803d", "#f0fdf4"],
    ["nontarget", t("Нецелевой", "Нецільовий"), "#b91c1c", "#fef2f2"],
    ["comment", t("Комментарий", "Коментар"), "#6d28d9", "#f5f3ff"],
    ["noreply", t("Не ответил", "Не відповів"), "#b45309", "#fffbeb"],
  ];
  const NT: [string, string][] = [
    ["spam", t("Спам / бот", "Спам / бот")],
    ["not_our", t("Не наш товар", "Не наш товар")],
    ["supplier_job", t("Поставщик / вакансия", "Постачальник / вакансія")],
    ["wrong", t("Ошибся адресом", "Помилився адресою")],
    ["other", t("Другое", "Інше")],
  ];
  async function save(quality: string, reason = "") {
    try {
      const r = await api.post<St>(base, { quality, reason });
      setSt(r); setNtOpen(false); setErr("");
    } catch { setErr(t("Не удалось сохранить", "Не вдалося зберегти")); }
  }
  const pill = (on: boolean, fg: string, bg: string): any => ({
    fontSize: 11.5, fontWeight: on ? 700 : 600, padding: "2px 9px", borderRadius: 999, cursor: "pointer",
    border: `1px solid ${on ? fg : "#e2e8f0"}`, background: on ? bg : "#fff", color: on ? fg : "#475569", whiteSpace: "nowrap",
  });
  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 4, margin: "0 0 8px" }}
      title={t("Качество обращения: в конверсию менеджера идут только целевые", "Якість звернення: у конверсію менеджера йдуть лише цільові")}>
      <span style={{ fontSize: 11.5, color: "#64748b", fontWeight: 600, marginRight: 2 }}>{t("Обращение:", "Звернення:")}</span>
      {Q.map(([k, l, fg, bg]) => {
        const on = st.quality === k;
        return (
          <button key={k} type="button" style={pill(on, fg, bg)}
            onClick={() => (k === "nontarget" && !on ? setNtOpen((v) => !v) : save(on ? "" : k))}>
            {l}{on && k === "nontarget" && st.reason_label ? ` · ${st.reason_label}` : ""}
          </button>
        );
      })}
      {!st.quality && <span style={{ fontSize: 11, color: "#94a3b8" }}>{t("не отмечено", "не відмічено")}</span>}
      {ntOpen && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, width: "100%", marginTop: 2 }}>
          {NT.map(([k, l]) => (
            <button key={k} type="button" style={pill(false, "#b91c1c", "#fef2f2")} onClick={() => save("nontarget", k)}>{l}</button>
          ))}
        </div>
      )}
      {err && <span style={{ fontSize: 11, color: "#b91c1c" }}>{err}</span>}
    </div>
  );
}
