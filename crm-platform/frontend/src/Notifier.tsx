/* Глобальний нотифаер: опитує сервер на нові вхідні повідомлення клієнтів.
   1) програє звук, 2) показує спливаюче вікно (тост) з імʼям+текстом → клік відкриває чат,
   3) ставить лічильник непрочитаних у заголовок вкладки браузера. Монтується в Layout. */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { playMessageSound, playTeamSound, loadSoundLibrary } from "./sounds";
import { useLang } from "./i18n";

type Toast = { id: number; name: string; preview: string; channel: string; conv_id: number };

export default function Notifier() {
  const last = useRef<number | null>(null);
  const teamLast = useRef<number | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nav = useNavigate();
  const { t } = useLang();

  useEffect(() => {
    let stop = false;
    loadSoundLibrary();
    async function poll() {
      try {
        const d = await api.get<{ last_in: number; latest: any; unread: number; team_last?: number; team_latest?: any }>("/api/inbox/ping/");
        if (d && typeof d.last_in === "number") {
          if (last.current !== null && d.last_in > last.current) {
            playMessageSound();
            if (d.latest) {
              const id = d.last_in;
              setToasts((ts) => [{ id, name: d.latest.name, preview: d.latest.preview, channel: d.latest.channel, conv_id: d.latest.conv_id }, ...ts].slice(0, 4));
              setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), 9000);
            }
          }
          last.current = d.last_in;
          if (typeof d.team_last === "number") {
            if (teamLast.current !== null && d.team_last > teamLast.current) {
              playTeamSound();
              if (d.team_latest) {
                const tid = -1000000 - d.team_last;
                setToasts((ts) => [{ id: tid, name: d.team_latest.name, preview: d.team_latest.preview, channel: "team", conv_id: -1 }, ...ts].slice(0, 4));
                setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== tid)), 9000);
              }
            }
            teamLast.current = d.team_last;
          }
          document.title = d.unread > 0 ? `(${d.unread}) Wallcov CRM` : "Wallcov CRM";
        }
      } catch { /* мовчки */ }
    }
    poll();
    const tm = setInterval(() => { if (!stop && document.visibilityState !== "hidden") poll(); }, 12000);
    return () => { stop = true; clearInterval(tm); };
  }, []);

  if (toasts.length === 0) return null;
  return (
    <div style={{ position: "fixed", top: 16, right: 16, zIndex: 99998, display: "flex", flexDirection: "column", gap: 10, width: 320, maxWidth: "90vw" }}>
      {toasts.map((to) => (
        <div key={to.id} onClick={() => { nav(to.channel === "team" ? "/inbox?tab=team" : `/inbox?c=${to.conv_id}`); setToasts((ts) => ts.filter((x) => x.id !== to.id)); }}
          style={{ background: "#fff", borderRadius: 14, boxShadow: "0 12px 34px rgba(20,40,80,.24)", border: "1px solid #e8edf3", borderLeft: "4px solid " + (to.channel === "team" ? "#2563eb" : "#C67D5F"), padding: "11px 13px", cursor: "pointer" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
            <span style={{ fontSize: 16 }}>{to.channel === "team" ? "👥" : "💬"}</span>
            <b style={{ fontSize: 13.5, flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{to.name}</b>
            <button onClick={(e) => { e.stopPropagation(); setToasts((ts) => ts.filter((x) => x.id !== to.id)); }}
              style={{ border: "none", background: "transparent", cursor: "pointer", color: "#94a3b8", fontSize: 17, lineHeight: 1, padding: 0 }}>×</button>
          </div>
          <div style={{ fontSize: 12.5, color: "#475569", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{to.preview || t("Новое сообщение", "Нове повідомлення")}</div>
          <div style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 3 }}>{to.channel ? to.channel + " · " : ""}{t("нажми, чтобы открыть", "натисни, щоб відкрити")}</div>
        </div>
      ))}
    </div>
  );
}
