/* Спливашка ВХІДНОГО дзвінка. Показується ЛИШЕ коли РЕАЛЬНО дзвонить ЦЕЙ браузер
 * (WebRTC-сесія веб-телефона) — тобто рівно тому, чий телефон зараз дзвонить.
 * Ніяких «серверних сигналів» для тих, кому не дзвонить — щоб не було плутанини. */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";
import { startCallRing, stopCallRing, loadSoundLibrary } from "./sounds";

interface Ring { uniqueid: string; number: string; line: string; contact?: number; contact_name?: string; }

export default function IncomingCallPopup() {
  const { t } = useLang();
  const nav = useNavigate();
  const [phState, setPhState] = useState<string>("");   // ready/incoming/calling/incall
  const [peer, setPeer] = useState("");
  const [talkSec, setTalkSec] = useState(0);
  const [hidden, setHidden] = useState(false);
  const [ring, setRing] = useState<Ring | null>(null);   // збагачення: лінія + контакт (для показу)
  const [card, setCard] = useState<any>(null);           // картка клієнта
  const wasIncoming = useRef(false);                     // поточний дзвінок почався як ВХІДНИЙ?

  useEffect(() => {
    loadSoundLibrary();
    try { if ("Notification" in window && Notification.permission === "default") Notification.requestPermission(); } catch { /* */ }
  }, []);
  const notifRef = useRef<any>(null);

  // стан веб-телефона цього браузера
  useEffect(() => {
    const onState = (e: any) => {
      const st = e?.detail?.state || "";
      setPhState(st);
      setPeer(e?.detail?.peer || "");
      if (st === "incoming") { wasIncoming.current = true; setHidden(false); }
      if (st === "calling") wasIncoming.current = false;          // ЦЕЙ браузер дзвонить назовні
      if (st === "ready" || st === "off" || st === "") wasIncoming.current = false;
    };
    window.addEventListener("wallcov-phone-state", onState as any);
    return () => window.removeEventListener("wallcov-phone-state", onState as any);
  }, []);

  const incoming = phState === "incoming";
  const outgoing = (phState === "calling" || phState === "incall") && !wasIncoming.current;   // менеджер сам дзвонить
  const inCall = phState === "incall" || phState === "calling";
  const show = (incoming || inCall) && !hidden;

  // збагачення: ВХІДНИЙ → з активних дзвінків; ВИХІДНИЙ → пошук контакту за набраним номером
  useEffect(() => {
    if (!incoming && !inCall) { setRing(null); return; }
    let ok = true;
    const d9 = (peer || "").replace(/\D/g, "").slice(-9);
    if (outgoing) {
      // менеджер дзвонить — шукаємо контакт за номером
      if (d9.length >= 7) {
        api.get<any>("/api/contacts/?q=" + encodeURIComponent(d9)).then((r) => {
          if (!ok) return;
          const arr = (r.results || r) as any[];
          const c = arr.find((x) => (x.phone || "").replace(/\D/g, "").slice(-9) === d9) || null;
          setRing({ uniqueid: "out", number: peer || "", line: "", contact: c ? c.id : undefined, contact_name: c ? ((c.first_name || "") + " " + (c.last_name || "")).trim() : "" });
        }).catch(() => setRing({ uniqueid: "out", number: peer || "", line: "" } as any));
      } else setRing({ uniqueid: "out", number: peer || "", line: "" } as any);
      return;
    }
    const f = () => api.get<Ring[]>("/api/telephony/ringing/active/").then((list) => {
      if (!ok) return;
      if (list && list.length) {
        setRing(list.find((x) => (x.number || "").replace(/\D/g, "").slice(-9) === d9) || list[0]);
      }
    }).catch(() => {});
    f();
    const tm = setInterval(f, 2500);
    return () => { ok = false; clearInterval(tm); };
  }, [incoming, inCall, outgoing, peer]);

  // картка клієнта
  useEffect(() => {
    const cid = ring?.contact;
    if (!cid) { setCard(null); return; }
    let ok = true;
    api.get<any>(`/api/contacts/${cid}/`).then((c) => { if (ok) setCard(c); }).catch(() => {});
    return () => { ok = false; };
  }, [ring?.contact]);

  // таймер розмови
  useEffect(() => {
    if (phState !== "incall") { setTalkSec(0); return; }
    const t0 = Date.now();
    const tm = setInterval(() => setTalkSec(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(tm);
  }, [phState]);

  // сигнал дзвінка — ЛИШЕ поки реально дзвонить цей браузер (Web Audio грає і у фоновій вкладці)
  useEffect(() => {
    if (incoming && !hidden) startCallRing(); else stopCallRing();
    return () => stopCallRing();
  }, [incoming, hidden]);

  // системне сповіщення коли дзвінок, а вкладка у фоні (менеджер в іншому застосунку / на робочому столі)
  useEffect(() => {
    if (!incoming) { try { notifRef.current?.close(); } catch { /* */ } notifRef.current = null; return; }
    try {
      if ("Notification" in window && Notification.permission === "granted") {
        const nm = ring?.contact_name || ring?.number || peer || t("клиент","клієнт");
        const n = new Notification(t("📞 Входящий звонок","📞 Вхідний дзвінок"), { body: String(nm) + (ring?.line ? " · " + ring.line : ""), tag: "wallcov-call", requireInteraction: true });
        n.onclick = () => { try { window.focus(); } catch { /* */ } setHidden(false); n.close(); };
        notifRef.current = n;
      }
    } catch { /* */ }
    return () => { try { notifRef.current?.close(); } catch { /* */ } notifRef.current = null; };
  }, [incoming, ring?.contact_name, ring?.number]);

  if (!show) return null;
  const name = ring?.contact_name || t("Неизвестный номер", "Невідомий номер");
  const number = ring?.number || peer || "";
  const cardName = card?.display_name || name;
  const lastDeal = (card?.deals || [])[0];

  return createPortal((
    <div onClick={() => setHidden(true)} style={{ position: "fixed", inset: 0, zIndex: 2147483000, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 380, maxWidth: "92vw", background: "#fff", borderRadius: 16, boxShadow: outgoing ? "0 24px 70px rgba(59,130,246,.4)" : "0 24px 70px rgba(22,163,74,.45)", border: "2px solid " + (outgoing ? "#3b82f6" : "#16a34a"), padding: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <div style={{ fontSize: 30 }}><Icon n="📞" size={30} /></div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, color: outgoing ? "#3b82f6" : "#16a34a", fontSize: 13, letterSpacing: ".3px" }}>{phState === "incall" ? ("🟢 " + t("РАЗГОВОР", "РОЗМОВА") + " · " + Math.floor(talkSec / 60) + ":" + String(talkSec % 60).padStart(2, "0")) : (outgoing ? t("ИСХОДЯЩИЙ · набор…", "ВИХІДНИЙ · набір…") : t("ВХОДЯЩИЙ ЗВОНОК", "ВХІДНИЙ ДЗВІНОК"))}</div>
            {ring?.line && <div style={{ fontSize: 11, color: "#7c5cff" }}><Icon n="📡" size={11} /> {ring.line}</div>}
          </div>
          <button onClick={() => setHidden(true)} title={t("Скрыть", "Сховати")} style={{ border: "none", background: "transparent", fontSize: 22, cursor: "pointer", color: "#94a3b8" }}>×</button>
        </div>
        <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.2 }}>{cardName}</div>
        <div style={{ color: "#475569", marginBottom: 10, fontSize: 15 }}>{number}</div>
        {card && (
          <div style={{ background: "#f8fafc", borderRadius: 10, padding: "8px 11px", marginBottom: 12, fontSize: 12.5 }}>
            {card.source ? <div><span className="muted">{t("Источник:", "Джерело:")}</span> <b>{card.source}</b></div> : null}
            {typeof card.total_spent !== "undefined" ? <div><span className="muted">{t("Потратил всего:", "Витратив усього:")}</span> <b style={{ color: "#16a34a" }}>{Math.round(Number(card.total_spent || 0)).toLocaleString("ru")} ₴</b></div> : null}
            {lastDeal ? <div style={{ marginTop: 2 }}><span className="muted">{t("Последняя сделка:", "Остання угода:")}</span> <b>{lastDeal.title}</b> · {lastDeal.stage || "—"}</div>
              : <div className="muted" style={{ marginTop: 2 }}>{t("Сделок ещё нет", "Угод ще немає")}</div>}
          </div>
        )}
        {inCall || outgoing ? (
          <button className="btn" style={{ width: "100%", height: 46, background: "#dc2626", color: "#fff", fontWeight: 800, fontSize: 15 }}
            onClick={() => { try { (window as any).wallcovHangup?.(); } catch { /* */ } setHidden(true); }}>
            <Icon n="📵" size={17} /> {phState === "incall" ? t("Завершить разговор", "Завершити розмову") : t("Отменить вызов", "Скасувати виклик")}
          </button>
        ) : (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-green" style={{ flex: 1, height: 44, fontWeight: 700, fontSize: 15 }}
              onClick={() => { stopCallRing(); try { (window as any).wallcovAnswer?.(); } catch { /* */ } }}>
              <><Icon n="✅" size={16} /> {t("Принять", "Прийняти")}</>
            </button>
            <button className="btn" style={{ flex: 1, height: 44, background: "#fee2e2", color: "#b91c1c", fontWeight: 700 }}
              onClick={() => { stopCallRing(); try { (window as any).wallcovHangup?.(); } catch { /* */ } setHidden(true); }}>
              {t("✖ Сбросить", "✖ Скинути")}
            </button>
          </div>
        )}
        {ring?.contact ? <button className="btn" style={{ width: "100%", height: 34, marginTop: 8, background: "#eff6ff", color: "#1d4ed8" }}
          onClick={() => { nav(`/clients/${ring.contact}`); setHidden(true); }}>{t("Открыть карточку клиента", "Відкрити картку клієнта")}</button> : null}
      </div>
    </div>
  ), document.body);
}
