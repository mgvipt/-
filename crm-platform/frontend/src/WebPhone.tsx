/* Веб-телефон Wallcov-CRM — дзвінки прямо з браузера через нашу телефонію (WebRTC/JsSIP).
 * Реєструється як SIP-розширення, дзвонить і приймає. Плаваючий віджет. */
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

declare global {
  interface Window { JsSIP: any; wallcovDial?: (n: string) => void; wallcovPhoneReady?: boolean; wallcovAnswer?: () => void; wallcovHangup?: () => void; wallcovIncoming?: boolean; }
}

const ICE_CFG = { iceServers: [{ urls: "stun:stun.l.google.com:19302" }, { urls: "stun:stun1.l.google.com:19302" }] };

type St = "off" | "connecting" | "ready" | "incoming" | "calling" | "incall" | "error";

export default function WebPhone() {
  const { t } = useLang();
  const [st, setSt] = useState<St>("off");
  const [enabled, setEnabled] = useState(false);   // телефония доступна (конфиг получен) — виджет не прячем при кратких разрег.
  const [everReady, setEverReady] = useState(false);  // хоч раз зареєструвались → панель набору тримаємо стабільно
  const [peer, setPeer] = useState("");
  const [msg, setMsg] = useState("");
  const [dialN, setDialN] = useState("");
  const [line, setLine] = useState<string>(() => localStorage.getItem("crm_phone_line") || "789");
  const lineRef = useRef<string>(localStorage.getItem("crm_phone_line") || "789");
  function pickLine(l: string) { setLine(l); lineRef.current = l; localStorage.setItem("crm_phone_line", l); }
  const [recent, setRecent] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem("crm_phone_recent") || "[]"); } catch { return []; } });
  const uaRef = useRef<any>(null);
  const sessRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let ua: any, cancelled = false, regTimer: any;
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    (async () => {
      try {
        // 1) дочекатись бібліотеки JsSIP (sync-скрипт міг ще не виконатись на момент монтування)
        const t0 = Date.now();
        while (!window.JsSIP && !cancelled && Date.now() - t0 < 8000) await sleep(150);
        if (cancelled || !window.JsSIP) return;
        // 2) конфіг з ретраями — разовий 401/збій мережі НЕ повинні назавжди ховати віджет
        let cfg: any = null;
        for (let i = 0; i < 6 && !cancelled; i++) {
          try { cfg = await api.get<any>("/api/telephony/webrtc-config/"); if (cfg?.enabled) break; } catch { /* retry */ }
          await sleep(1000);
        }
        if (cancelled || !cfg?.enabled) return;
        setEnabled(true);   // телефония настроена → виджет показываем постоянно
        const JsSIP = window.JsSIP;
        const socket = new JsSIP.WebSocketInterface(cfg.ws);
        const host = window.location.host;
        ua = new JsSIP.UA({
          sockets: [socket], uri: `sip:${cfg.ext}@${host}`, password: cfg.secret,
          register: true, session_timers: false, user_agent: "Wallcov CRM Phone",
        });
        uaRef.current = ua;
        ua.on("connecting", () => setSt("connecting"));
        ua.on("registered", () => { clearTimeout(regTimer); setSt("ready"); setEverReady(true); window.wallcovPhoneReady = true; });
        ua.on("unregistered", () => {
          clearTimeout(regTimer);
          regTimer = setTimeout(() => setSt((s) => (["incoming", "calling", "incall", "ready"].includes(s) ? s : "connecting")), 5000);
        });
        ua.on("registrationFailed", (e: any) => { setSt("error"); setMsg(t("Регистрация не удалась: ","Реєстрація не вдалась: ") + (e?.cause || "")); });
        ua.on("newRTCSession", (data: any) => {
          const session = data.session; sessRef.current = session;
          setPeer(session.remote_identity?.uri?.user || "");
          const attach = (pc: any) => {
            if (!pc) return;
            pc.addEventListener("track", (ev: any) => {
              const stream = ev.streams && ev.streams[0];
              if (stream && audioRef.current) {
                audioRef.current.srcObject = stream;
                audioRef.current.muted = false;
                audioRef.current.play().catch(() => {});
              }
            });
          };
          session.on("peerconnection", (e: any) => attach(e.peerconnection));
          if (session.connection) attach(session.connection);
          session.on("accepted", () => setSt("incall"));
          session.on("confirmed", () => setSt("incall"));
          session.on("ended", () => { setSt("ready"); setPeer(""); sessRef.current = null; });
          session.on("failed", (e: any) => { setSt("ready"); setPeer(""); sessRef.current = null; setMsg(t("Звонок не удался: ","Дзвінок не вдався: ") + (e?.cause || "")); });
          setSt(data.originator === "remote" ? "incoming" : "calling");
        });
        ua.start();
        window.wallcovDial = (n: string) => doDial(n);
      } catch { /* конфіг недоступний — віджет не показуємо */ }
    })();
    return () => { cancelled = true; clearTimeout(regTimer); try { window.wallcovDial = undefined; window.wallcovPhoneReady = false; ua?.stop(); } catch { /* */ } };
  }, []);

  function doDial(number: string) {
    const ua = uaRef.current;
    if (!ua) { setMsg(t("Веб-телефон не готов","Веб-телефон не готовий")); return; }
    const num = (number || "").replace(/[^\d+]/g, "");
    const dn = num.startsWith("+380") ? "0" + num.slice(4) : num.replace(/^\+/, "");
    if (!dn) return;
    setRecent((r) => { const nr = [dn, ...r.filter((x) => x !== dn)].slice(0, 5); localStorage.setItem("crm_phone_recent", JSON.stringify(nr)); return nr; });
    try {
      ua.call(`sip:${lineRef.current}*${dn}@${window.location.host}`, {
        mediaConstraints: { audio: true, video: false },
        rtcOfferConstraints: { offerToReceiveAudio: true, offerToReceiveVideo: false },
        pcConfig: ICE_CFG,
      });
      setPeer(number); setSt("calling"); setMsg("");
    } catch (e: any) { setMsg(t("Ошибка: ","Помилка: ") + (e?.message || "")); }
  }
  function answer() { try { sessRef.current?.answer({ mediaConstraints: { audio: true, video: false }, pcConfig: ICE_CFG }); setSt("incall"); } catch { /* */ } }
  function hangup() { try { sessRef.current?.terminate(); } catch { /* */ } setSt("ready"); setPeer(""); }
  useEffect(() => {
    window.wallcovAnswer = answer;
    window.wallcovHangup = hangup;
    window.wallcovIncoming = st === "incoming";
    window.dispatchEvent(new CustomEvent("wallcov-phone-state", { detail: { state: st, peer } }));
  }, [st, peer]);

  const dot = ({ off: "#94a3b8", connecting: "#f59e0b", ready: "#16a34a", incoming: "#16a34a", calling: "#3b82f6", incall: "#3b82f6", error: "#dc2626" } as any)[st];
  const label = ({ off: t("выключено","вимкнено"), connecting: t("подключение…","підключення…"), ready: t("готов","готовий"), incoming: t("входящий звонок","вхідний дзвінок"), calling: t("набор…","набір…"), incall: t("разговор","розмова"), error: t("ошибка","помилка") } as any)[st];
  const busy = st === "incoming" || st === "calling" || st === "incall";

  if (!enabled) return <audio ref={audioRef} autoPlay playsInline />;

  return (
    <>
      <audio ref={audioRef} autoPlay playsInline />
      <div style={{ margin: "0 10px 8px", background: "#fff", borderRadius: 12, boxShadow: "0 4px 16px rgba(0,0,0,.18)", border: "1px solid #e2e8f0", padding: 11 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: busy ? 10 : 0 }}>
          <span style={{ width: 9, height: 9, borderRadius: 9, background: dot, display: "inline-block" }} />
          <b style={{ fontSize: 13, whiteSpace: "nowrap" }}>{t("📞 Телефон","📞 Телефон")}</b>
          <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>{label}</span>
        </div>

        {busy && <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 10 }}>{peer || "—"}</div>}

        {st === "incoming" && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-green" style={{ flex: 1 }} onClick={answer}>{t("✅ Принять","✅ Прийняти")}</button>
            <button className="btn" style={{ background: "#fee2e2", color: "#b91c1c" }} onClick={hangup}>{t("✖ Сбросить","✖ Скинути")}</button>
          </div>
        )}
        {(st === "calling" || st === "incall") && (
          <button className="btn" style={{ width: "100%", background: "#fee2e2", color: "#b91c1c" }} onClick={hangup}>{t("📵 Завершить","📵 Завершити")}</button>
        )}
        {everReady && !busy && (
          <div style={{ marginTop: 8 }}>
            <div className="muted" style={{ fontSize: 11, marginBottom: 3 }}>{t("Звонить с линии:","Дзвонити з лінії:")}</div>
            <select value={line} onChange={(e) => pickLine(e.target.value)}
              style={{ width: "100%", height: 30, borderRadius: 7, border: "1px solid #cbd5e1", fontSize: 12, marginBottom: 6 }}>
              <option value="789">{t("Салон · 0964191890","Салон · 0964191890")}</option>
              <option value="788">{t("Алмазное · 0673812702","Алмазне · 0673812702")}</option>
            </select>
          <div style={{ display: "flex", gap: 6 }}>
            <input value={dialN} onChange={(e) => setDialN(e.target.value)} onKeyDown={(e) => e.key === "Enter" && doDial(dialN)}
              placeholder="0XX XXX XX XX" style={{ flex: 1, minWidth: 0, width: 0, height: 32, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 9px", fontSize: 13 }} />
            <button className="btn btn-green" style={{ flexShrink: 0 }} onClick={() => doDial(dialN)} disabled={!dialN.trim()}>📞</button>
          </div>
          {recent.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div className="muted" style={{ fontSize: 11, marginBottom: 3 }}>{t("Последние номера:","Останні номери:")}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                {recent.map((n) => (
                  <button key={n} onClick={() => doDial(n)} title={t("Позвонить","Подзвонити")}
                    style={{ cursor: "pointer", background: "#eef2ff", color: "#4338ca", border: "none", borderRadius: 999, fontSize: 11.5, padding: "3px 9px" }}>{n}</button>
                ))}
              </div>
            </div>
          )}
          </div>
        )}
        {msg && <div style={{ fontSize: 11, marginTop: 7, color: st === "error" ? "#dc2626" : "#64748b" }}>{msg}</div>}
      </div>
    </>
  );
}
