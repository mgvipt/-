/* Спливашка ВХІДНОГО дзвінка. Показується ЛИШЕ коли дзвонить САМЕ цей браузер (реальна WebRTC-сесія
 * веб-телефона) — тобто рівно тому, до кого зараз дійшла черга. Не взяв за N секунд → Asterisk скасовує
 * INVITE і переходить до наступного → тут вікно гасне, а зʼявляється у наступного. Дані про того, хто
 * дзвонить (імʼя/лінія/контакт) — з сервера для збагачення. */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";
import { startCallRing, stopCallRing, loadSoundLibrary } from "./sounds";

interface Ring { uniqueid: string; number: string; line: string; contact?: number; contact_name?: string; ring_ext?: string; }

export default function IncomingCallPopup() {
  const { t } = useLang();
  const nav = useNavigate();
  const [incoming, setIncoming] = useState(typeof window !== "undefined" && !!(window as any).wallcovIncoming);
  const [hidden, setHidden] = useState(false);
  const [peer, setPeer] = useState("");
  const [ring, setRing] = useState<Ring | null>(null);
  const alive = useRef(true);
  const sawRing = useRef(false);
  const [myExt, setMyExt] = useState("");

  // мій добавочний (щоб знати чи ЗАРАЗ моя черга за сигналом сервера) + свіжа бібліотека звуків
  useEffect(() => {
    api.get<any>("/api/telephony/webrtc-config/").then((c) => setMyExt(String(c?.my_ext || c?.ext || ""))).catch(() => {});
    loadSoundLibrary();
  }, []);

  // реальний стан веб-телефона: дзвонить саме цей браузер?
  useEffect(() => {
    const onState = (e: any) => {
      const isIn = e?.detail?.state === "incoming";
      setIncoming(isIn);
      setPeer(e?.detail?.peer || "");
      if (isIn) setHidden(false);           // нова черга дійшла — показати знову
      else stopCallRing();                  // вже НЕ дзвонить цей браузер — негайно глушимо звук
    };
    window.addEventListener("wallcov-phone-state", onState as any);
    return () => window.removeEventListener("wallcov-phone-state", onState as any);
  }, []);

  // збагачення (імʼя/лінія/контакт) з сервера — лише поки дзвонить цей браузер
  useEffect(() => {
    if (!incoming) { setRing(null); sawRing.current = false; return; }
    alive.current = true;
    const f = () => api.get<Ring[]>("/api/telephony/ringing/active/").then((list) => {
      if (!alive.current) return;
      if (list && list.length) {
        sawRing.current = true;
        const d = (peer || "").replace(/\D/g, "").slice(-9);
        const r = list.find((x) => (x.number || "").replace(/\D/g, "").slice(-9) === d) || list[0];
        setRing(r);
        // сервер каже: ЗАРАЗ дзвонить інший добавочний → це вже не моя черга → глушимо
        if (r?.ring_ext && myExt && String(r.ring_ext) !== String(myExt)) { setIncoming(false); stopCallRing(); }
      } else if (sawRing.current) {
        setIncoming(false);   // страховка: сервер каже дзвінок завершився (взяли/скинули) → ховаємо
      }
    }).catch(() => {});
    f();
    const tm = setInterval(f, 2500);
    return () => { alive.current = false; clearInterval(tm); };
  }, [incoming, peer, myExt]);

  // сигнал дзвінка поки показуємо вікно
  useEffect(() => {
    if (incoming && !hidden) startCallRing(); else stopCallRing();
    return () => stopCallRing();
  }, [incoming, hidden]);

  if (!incoming || hidden) return null;
  const name = ring?.contact_name || t("Неизвестный номер", "Невідомий номер");
  const number = ring?.number || peer || "";

  return (
    <div style={{ position: "fixed", top: 72, right: 20, zIndex: 9999, width: 330, background: "#fff", borderRadius: 14, boxShadow: "0 14px 44px rgba(22,163,74,.35)", border: "2px solid #16a34a", padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <div style={{ fontSize: 30 }}><Icon n="📞" size={30} /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 800, color: "#16a34a", fontSize: 13, letterSpacing: ".3px" }}>{t("ВХОДЯЩИЙ ЗВОНОК", "ВХІДНИЙ ДЗВІНОК")}</div>
          {ring?.line && <div style={{ fontSize: 11, color: "#7c5cff" }}><Icon n="📡" size={11} /> {ring.line}</div>}
        </div>
        <button onClick={() => setHidden(true)} title={t("Скрыть", "Сховати")} style={{ border: "none", background: "transparent", fontSize: 20, cursor: "pointer", color: "#94a3b8" }}>×</button>
      </div>
      <div style={{ fontSize: 19, fontWeight: 700, lineHeight: 1.2 }}>{name}</div>
      <div style={{ color: "#475569", marginBottom: 12, fontSize: 14 }}>{number}</div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-green" style={{ flex: 1, height: 40, fontWeight: 700 }}
          onClick={() => { try { (window as any).wallcovAnswer?.(); } catch { /* */ } }}>
          <><Icon n="✅" size={16} /> {t("Принять", "Прийняти")}</>
        </button>
        <button className="btn" style={{ flex: 1, height: 40, background: "#fee2e2", color: "#b91c1c", fontWeight: 700 }}
          onClick={() => { try { (window as any).wallcovHangup?.(); } catch { /* */ } setHidden(true); }}>
          {t("✖ Сбросить", "✖ Скинути")}
        </button>
      </div>
      {ring?.contact ? <button className="btn" style={{ width: "100%", height: 34, marginTop: 8, background: "#eff6ff", color: "#1d4ed8" }}
        onClick={() => { nav(`/clients/${ring.contact}`); setHidden(true); }}>{t("Открыть карточку клиента", "Відкрити картку клієнта")}</button> : null}
    </div>
  );
}
