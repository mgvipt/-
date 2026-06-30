/* Плавающая панель активного звонка — видна поверх всего интерфейса.
 * Слушает событие wallcov-phone-state от WebPhone и даёт кнопку «положить трубку» где угодно. */
import { useEffect, useState } from "react";
import { useLang } from "./i18n";
import { Icon } from "./Icon";

export default function CallBar() {
  const { t } = useLang();
  const [st, setSt] = useState("");
  const [peer, setPeer] = useState("");
  useEffect(() => {
    const h = (e: any) => { setSt(e.detail?.state || ""); setPeer(e.detail?.peer || ""); };
    window.addEventListener("wallcov-phone-state", h as any);
    return () => window.removeEventListener("wallcov-phone-state", h as any);
  }, []);
  if (!(st === "calling" || st === "incall" || st === "incoming")) return null;
  const label = st === "incoming" ? t("Входящий звонок", "Вхідний дзвінок") : st === "calling" ? t("Набор…", "Набір…") : t("Разговор", "Розмова");
  const w = window as any;
  return (
    <div style={{ position: "fixed", top: 14, left: "50%", transform: "translateX(-50%)", zIndex: 99999, background: "#fff", borderRadius: 14, boxShadow: "0 8px 30px rgba(0,0,0,.28)", border: "1px solid #e2e8f0", padding: "10px 14px", display: "flex", alignItems: "center", gap: 14, minWidth: 330 }}>
      <span style={{ width: 11, height: 11, borderRadius: 11, background: st === "incoming" ? "#16a34a" : "#3b82f6", display: "inline-block", flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11.5, color: "#64748b" }}><Icon n="📞" size={13} /> {label}</div>
        <div style={{ fontSize: 16, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{peer || "—"}</div>
      </div>
      {st === "incoming" && <button onClick={() => w.wallcovAnswer && w.wallcovAnswer()} style={{ background: "#16a34a", color: "#fff", border: "none", borderRadius: 10, padding: "10px 16px", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 5, flexShrink: 0 }}><Icon n="✅" size={16} /> {t("Принять", "Прийняти")}</button>}
      <button onClick={() => w.wallcovHangup && w.wallcovHangup()} style={{ background: "#dc2626", color: "#fff", border: "none", borderRadius: 10, padding: "10px 18px", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, fontSize: 14, flexShrink: 0 }}><Icon n="📵" size={16} /> {t("Положить трубку", "Покласти слухавку")}</button>
    </div>
  );
}
