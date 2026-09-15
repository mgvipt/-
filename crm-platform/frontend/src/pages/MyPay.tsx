/* «Моя ЗП» (Розвиток v2, 16.09.2026) — окремий пункт меню для ВСІХ активних співробітників (і складу теж):
 * лише свої цифри — ЗП за місяць, «гарантовано / умовно», «Що буде, якщо», пункти стандарту складу, умови ЗП.
 * Бекенд той самий: /api/payroll/my/ (лише request.user). */
import MyPayroll, { PlanRules } from "../MyPayroll";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

export default function MyPay() {
  const { t } = useLang();
  return (
    <div className="scroll pad fade">
      <h2 style={{ margin: "0 0 2px", fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}><Icon n="wallet" size={20} /> {t("Моя ЗП", "Моя ЗП")}</h2>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>{t("Только ваши цифры: сколько заработано, из чего складывается и что будет, если…", "Лише ваші цифри: скільки зароблено, з чого складається і що буде, якщо…")}</div>
      <MyPayroll />
      <PlanRules />
    </div>
  );
}
