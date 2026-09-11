/* Якість звернення (останній лід клієнта) — випадний список:
 * Цільовий / Нецільовий (+ причина) / Коментар без запиту / Не відповів.
 * Одна відмітка на клієнта — однаково видна в чаті, картках ліда, угоди та клієнта.
 * У конверсію менеджера йдуть лише цільові. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

type St = { lead_id: number | null; quality: string; reason: string; by?: string };

export default function LeadQuality({ contactId, convId, compact }: { contactId?: number | null; convId?: number | null; compact?: boolean }) {
  const { t } = useLang();
  const base = convId ? `/api/conversations/${convId}/lead-quality/` : contactId ? `/api/contacts/${contactId}/lead-quality/` : "";
  const [st, setSt] = useState<St | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setSt(null); setErr("");
    if (!base) return;
    api.get<St>(base).then(setSt).catch(() => setSt(null));
  }, [base]);
  if (!base || !st || !st.lead_id) return null;

  const cur = st.quality === "nontarget" ? `nontarget:${st.reason || "other"}` : st.quality;
  async function change(v: string) {
    const [quality, reason] = v.startsWith("nontarget:") ? ["nontarget", v.slice(10)] : [v, ""];
    try { setSt(await api.post<St>(base, { quality, reason })); setErr(""); }
    catch { setErr(t("Не удалось сохранить", "Не вдалося зберегти")); }
  }
  const color: Record<string, string> = { target: "#15803d", nontarget: "#b91c1c", comment: "#6d28d9", noreply: "#b45309" };
  const fg = color[st.quality] || "#64748b";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, margin: compact ? 0 : "0 0 8px", minWidth: 0 }}
      title={t("Качество обращения: в конверсию менеджера идут только целевые", "Якість звернення: у конверсію менеджера йдуть лише цільові")
        + (st.by ? ` · ${t("отметил", "відмітив")}: ${st.by}` : "")}>
      <span style={{ fontSize: 11.5, color: "#64748b", fontWeight: 600, whiteSpace: "nowrap" }}>{t("Обращение:", "Звернення:")}</span>
      <select value={cur} onChange={(e) => change(e.target.value)}
        style={{ fontSize: 12, fontWeight: 600, padding: "3px 6px", borderRadius: 7, border: `1px solid ${st.quality ? fg : "#e2e8f0"}`,
          color: fg, background: "#fff", minWidth: 0, maxWidth: "100%" }}>
        <option value="">{t("— не отмечено —", "— не відмічено —")}</option>
        <option value="target">{t("Целевой", "Цільовий")}</option>
        <option value="noreply">{t("Не ответил (после дожимов)", "Не відповів (після дожимів)")}</option>
        <optgroup label={t("Нецелевой", "Нецільовий")}>
          <option value="nontarget:spam">{t("Нецелевой: спам / бот", "Нецільовий: спам / бот")}</option>
          <option value="nontarget:not_our">{t("Нецелевой: не наш товар", "Нецільовий: не наш товар")}</option>
          <option value="nontarget:supplier_job">{t("Нецелевой: поставщик / вакансия", "Нецільовий: постачальник / вакансія")}</option>
          <option value="nontarget:wrong">{t("Нецелевой: ошибся адресом", "Нецільовий: помилився адресою")}</option>
          <option value="nontarget:other">{t("Нецелевой: другое", "Нецільовий: інше")}</option>
        </optgroup>
        <option value="comment">{t("Комментарий без запроса", "Коментар без запиту")}</option>
      </select>
      {err && <span style={{ fontSize: 11, color: "#b91c1c" }}>{err}</span>}
    </div>
  );
}
