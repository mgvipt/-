/* Аудит-журнал змін сутності (лід/сделка): хто, коли, що зробив + авто-дії.
 * GET /api/activity/?kind=lead|deal&object_id=ID */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

export default function ActivityLog({ kind, id }: { kind: "lead" | "deal"; id: number }) {
  const { t } = useLang();
  const [log, setLog] = useState<{ action: string; detail: string; actor: string; at: string }[]>([]);

  useEffect(() => {
    api.get<any[]>(`/api/activity/?kind=${kind}&object_id=${id}`).then((d) => setLog(Array.isArray(d) ? d : [])).catch(() => {});
  }, [kind, id]);

  const fmt = (d: string) => d ? new Date(d).toLocaleString("uk", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <div className="panel">
      <div className="label">{t("🕘 История изменений","🕘 Історія змін")}</div>
      {log.length === 0 ? (
        <div className="muted" style={{ fontSize: 12 }}>{t("Пока нет записей.","Поки немає записів.")}</div>
      ) : (
        <div style={{ maxHeight: 320, overflowY: "auto" }}>
          {log.map((a, i) => (
            <div key={i} style={{ padding: "7px 0", borderTop: i ? "1px solid #f1f5f9" : "none" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                <b style={{ fontSize: 12.5 }}>{a.action}</b>
                <span className="muted" style={{ fontSize: 11, whiteSpace: "nowrap" }}>{fmt(a.at)}</span>
              </div>
              {a.detail && <div className="muted" style={{ fontSize: 12, marginTop: 1 }}>{a.detail}</div>}
              <div style={{ fontSize: 11, color: "#64748b", marginTop: 1 }}>👤 {a.actor}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
