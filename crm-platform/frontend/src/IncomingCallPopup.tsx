/* Жива спливашка ВХІДНОГО дзвінка — опитує CRM кожні 2.5с, показує хто дзвонить
 * і на яку лінію. Зʼявляється на будь-якій сторінці. */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";
import { startCallRing, stopCallRing } from "./sounds";

interface Ring { uniqueid: string; number: string; line: string; contact?: number; contact_name?: string; }

export default function IncomingCallPopup() {
  const { t } = useLang();
  const [ring, setRing] = useState<Ring | null>(null);
  const dismissed = useRef<Set<string>>(new Set());
  const nav = useNavigate();
  const [canAnswer, setCanAnswer] = useState<boolean>(typeof window !== "undefined" && !!(window as any).wallcovIncoming);

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const list = await api.get<Ring[]>("/api/telephony/ringing/active/");
        if (!alive) return;
        const r = (list || []).find((x) => !dismissed.current.has(x.uniqueid)) || null;
        setRing(r);
      } catch { /* мовчки */ }
    }
    poll();
    const t = setInterval(poll, 2500);
    const onState = (e: any) => setCanAnswer(e?.detail?.state === "incoming");
    window.addEventListener("wallcov-phone-state", onState as any);
    return () => { alive = false; clearInterval(t); window.removeEventListener("wallcov-phone-state", onState as any); };
  }, []);

  useEffect(() => {
    if (!ring) { stopCallRing(); return; }
    startCallRing();
    return () => stopCallRing();
  }, [ring?.uniqueid]);

  if (!ring) return null;
  const close = () => { dismissed.current.add(ring.uniqueid); setRing(null); };

  return (
    <div style={{
      position: "fixed", top: 72, right: 20, zIndex: 9999, width: 330,
      background: "#fff", borderRadius: 14, boxShadow: "0 14px 44px rgba(22,163,74,.35)",
      border: "2px solid #16a34a", padding: 16,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <div style={{ fontSize: 30 }}><Icon n="📞" size={30} /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 800, color: "#16a34a", fontSize: 13, letterSpacing: ".3px" }}>{t("ВХОДЯЩИЙ ЗВОНОК","ВХІДНИЙ ДЗВІНОК")}</div>
          {ring.line && <div style={{ fontSize: 11, color: "#7c5cff" }}><Icon n="📡" size={11} /> {ring.line}</div>}
        </div>
        <button onClick={close} title={t("Скрыть","Сховати")} style={{ border: "none", background: "transparent", fontSize: 20, cursor: "pointer", color: "#94a3b8" }}>×</button>
      </div>
      <div style={{ fontSize: 19, fontWeight: 700, lineHeight: 1.2 }}>{ring.contact_name || t("Неизвестный номер","Невідомий номер")}</div>
      <div style={{ color: "#475569", marginBottom: 12, fontSize: 14 }}>{ring.number}</div>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <button className="btn btn-green" style={{ flex: 1, height: 40, fontWeight: 700 }}
            onClick={() => { try { (window as any).wallcovAnswer?.(); } catch { /* */ } }}>
            <><Icon n="✅" size={16} /> {t("Принять","Прийняти")}</>
          </button>
          <button className="btn" style={{ flex: 1, height: 40, background: "#fee2e2", color: "#b91c1c", fontWeight: 700 }}
            onClick={() => { try { (window as any).wallcovHangup?.(); } catch { /* */ } close(); }}>
            {t("✖ Сбросить","✖ Скинути")}
          </button>
      </div>
      <button className="btn" style={{ width: "100%", height: 36, background: "#eff6ff", color: "#1d4ed8" }}
        onClick={() => { if (ring.contact) nav(`/clients/${ring.contact}`); else nav("/phone"); close(); }}>
        {ring.contact ? t("Открыть карточку клиента","Відкрити картку клієнта") : t("Открыть телефонию","Відкрити телефонію")}
      </button>
    </div>
  );
}
