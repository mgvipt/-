import { useEffect, useState } from "react";
import { api, Paginated } from "../api";

interface Call {
  id: number; direction: string; direction_display: string; from_number: string; to_number: string;
  contact_name?: string; manager_name?: string; duration: number; recording_url: string; created_at: string;
}
interface Stats { total: number; recorded: number; missed: number; avg_seconds: number; }

const COLOR: Record<string, string> = { in: "#16a34a", out: "#3b82f6", missed: "#ef4444" };
function dur(s: number) { return s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "—"; }

export default function Phone() {
  const [calls, setCalls] = useState<Call[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  useEffect(() => {
    api.get<Paginated<Call>>("/api/calls/?page_size=200").then((d) => setCalls(d.results));
    api.get<Stats>("/api/calls/stats/").then(setStats);
  }, []);

  return (
    <div className="scroll pad fade">
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 14 }}>
          {[["Всего звонков", stats.total], ["Записано", stats.recorded], ["Пропущено", stats.missed], ["Средн. длит.", dur(stats.avg_seconds)]].map(([t, v]) => (
            <div key={t} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{t}</div><div style={{ fontSize: 24, fontWeight: 700 }}>{v}</div></div>
          ))}
        </div>
      )}
      <div className="tablewrap">
        <div className="tabletitle" style={{ padding: "10px 16px", borderBottom: "1px solid #e2e8f0", fontWeight: 600 }}>Журнал звонков · SIP-шлюз (Hetzner)</div>
        <table>
          <thead><tr><th>Тип</th><th>Клиент</th><th>Номер</th><th>Длит.</th><th>Менеджер</th><th>Запись</th></tr></thead>
          <tbody>
            {calls.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 20 }}>Звонков пока нет. Подключим SIP-шлюз — журнал заполнится автоматически.</td></tr>}
            {calls.map((c) => (
              <tr key={c.id}>
                <td><span className="chip" style={{ background: COLOR[c.direction] }}>{c.direction_display}</span></td>
                <td>{c.contact_name || "—"}</td>
                <td className="muted">{c.from_number || c.to_number}</td>
                <td>{dur(c.duration)}</td>
                <td>{c.manager_name || "—"}</td>
                <td>{c.recording_url ? <a href={c.recording_url} target="_blank" rel="noreferrer" style={{ color: "#2563eb" }}>▶ прослушать</a> : <span className="muted">нет</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="note">💡 SIP-шлюз шлёт событие на <code>/api/telephony/webhook/</code> после звонка — запись и длительность попадают сюда и в карточку клиента. Записи хранятся в Opus (≈10× экономия места).</div>
    </div>
  );
}
