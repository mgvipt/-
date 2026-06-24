/* Телефонія Wallcov-CRM — власний FreePBX (незалежно від Бітрикса).
 * Дві окремі картки: ВХІДНІ та ВИХІДНІ. Дзвінки тягнуться з нашого SIP-шлюзу. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Paginated } from "../api";
import { useLang } from "../i18n";

interface Call {
  id: number; direction: string; direction_display: string;
  from_number: string; to_number: string;
  contact?: number; contact_name?: string; manager_name?: string;
  duration: number; recording_url: string; recording_file?: string;
  extension?: string; disposition?: string; started_at?: string; created_at: string; line?: string;
}
interface Stats { total: number; recorded: number; missed: number; avg_seconds: number; }

function dur(s: number) { return s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "—"; }
function when(c: Call) {
  const d = c.started_at || c.created_at;
  return d ? new Date(d).toLocaleString("uk", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
}

export default function Phone() {
  const [calls, setCalls] = useState<Call[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const nav = useNavigate();
  const { t } = useLang();

  function load() {
    api.get<Paginated<Call>>("/api/calls/?page_size=300").then((d) => setCalls(d.results)).catch(() => {});
    api.get<Stats>("/api/calls/stats/").then(setStats).catch(() => {});
  }
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);

  const incoming = calls.filter((c) => c.direction === "in" || c.direction === "missed");
  const outgoing = calls.filter((c) => c.direction === "out");

  // ── одна картка дзвінка ──
  function Row({ c }: { c: Call }) {
    const missed = c.direction === "missed";
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", borderBottom: "1px solid #f1f5f9" }}>
        <div style={{ fontSize: 18, width: 22, textAlign: "center" }}>
          {c.direction === "out" ? "📤" : missed ? "📵" : "📥"}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 13.5, color: missed ? "#dc2626" : "#1e293b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {c.contact ? (
              <a onClick={() => nav(`/clients/${c.contact}`)} style={{ color: "var(--brand,#C67D5F)", cursor: "pointer" }}>{c.contact_name}</a>
            ) : (c.contact_name || (c.direction === "out" ? c.to_number : c.from_number) || "—")}
          </div>
          <div className="muted" style={{ fontSize: 11.5 }}>
            {c.direction === "out" ? c.to_number : c.from_number}{c.manager_name ? ` · ${c.manager_name}` : ""}
          </div>
          {c.line && <div style={{ fontSize: 10.5, color: "#7c5cff", marginTop: 1 }}>📡 {c.line}</div>}
        </div>
        <div style={{ textAlign: "right", fontSize: 11.5 }}>
          <div className="muted">{when(c)}</div>
          <div style={{ color: missed ? "#dc2626" : "#64748b" }}>{missed ? t("пропущенный","пропущений") : dur(c.duration)}</div>
        </div>
        {c.recording_url
          ? <a href={c.recording_url} target="_blank" rel="noreferrer" title={t("Прослушать","Прослухати")} style={{ color: "#2563eb", fontSize: 16 }}>▶</a>
          : c.recording_file ? <span title={t("Запись есть на сервере","Запис є на сервері")} style={{ color: "#94a3b8", fontSize: 14 }}>🎙</span>
          : <span style={{ width: 16 }} />}
      </div>
    );
  }

  // ── колонка (вхідні / вихідні) ──
  function Column({ title, icon, color, list }: { title: string; icon: string; color: string; list: Call[] }) {
    return (
      <div className="panel" style={{ margin: 0, padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "12px 14px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 8, background: color + "14" }}>
          <span style={{ fontSize: 18 }}>{icon}</span>
          <b style={{ fontSize: 15 }}>{title}</b>
          <span className="chip" style={{ background: color, marginLeft: "auto" }}>{list.length}</span>
        </div>
        <div style={{ maxHeight: "calc(100vh - 250px)", overflowY: "auto" }}>
          {list.length === 0
            ? <div className="muted" style={{ padding: 18, fontSize: 13 }}>{t("Пока пусто.","Поки порожньо.")}</div>
            : list.map((c) => <Row key={c.id} c={c} />)}
        </div>
      </div>
    );
  }

  return (
    <div className="scroll pad fade">
      <h2 style={{ margin: "0 0 4px" }}>📞 {t("Телефония","Телефонія")}</h2>
      <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>{t("Собственный SIP-шлюз на нашем сервере (независимо от Битрикса). Звонки и записи — наши.","Власний SIP-шлюз на нашому сервері (незалежно від Бітрикса). Дзвінки і записи — наші.")}</div>

      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 16 }}>
          {[[t("Всего","Всього"), stats.total], [t("С записью","Із записом"), stats.recorded], [t("Пропущенные","Пропущені"), stats.missed], [t("Ср. длительность","Сер. тривалість"), dur(stats.avg_seconds)]].map(([t, v]) => (
            <div key={t} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{t}</div><div style={{ fontSize: 24, fontWeight: 700 }}>{v}</div></div>
          ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, alignItems: "start" }}>
        <Column title={t("Входящие","Вхідні")} icon="📥" color="#16a34a" list={incoming} />
        <Column title={t("Исходящие","Вихідні")} icon="📤" color="#3b82f6" list={outgoing} />
      </div>

      <div className="note" style={{ marginTop: 14 }}>💡 {t("Журнал обновляется сам каждые 30 сек. Клик на имя клиента → его карточка. Дальше подключим звонок по клику и прослушивание записи прямо тут.","Журнал оновлюється сам кожні 30 сек. Клік на імʼя клієнта → його картка. Далі підключимо дзвінок по кліку і прослуховування запису прямо тут.")}</div>
    </div>
  );
}
