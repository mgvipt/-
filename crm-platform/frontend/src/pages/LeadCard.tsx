/* Карточка лида: стадии + левая колонка (контакт/ответственный/сумма/источник)
 * + конвертация в сделку. Открывается из канбана лидов (/leads/:id). */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, Funnel } from "../api";
import { Avatar, SourceChip } from "../ui";

interface Lead {
  id: number; title: string; contact_name?: string; owner_name?: string;
  funnel: number; stage: number; amount: string; source: string; is_seen: boolean;
}

export default function LeadCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const [lead, setLead] = useState<Lead | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [msg, setMsg] = useState("");

  async function load() {
    const l = await api.get<Lead>(`/api/leads/${id}/`);
    setLead(l);
    if (!funnel || funnel.id !== l.funnel) setFunnel(await api.get<Funnel>(`/api/funnels/${l.funnel}/`));
  }
  useEffect(() => { load(); }, [id]);
  if (!lead) return <div className="spin">Загрузка ліда…</div>;

  async function setStage(s: number) { await api.patch(`/api/leads/${id}/`, { stage: s }); load(); }
  async function convert() {
    const r = await api.post<{ deal_id: number }>(`/api/leads/${id}/convert/`, {});
    nav(`/deals/${r.deal_id}`);
  }
  const curOrder = funnel?.stages.find((s) => s.id === lead.stage)?.order ?? 0;

  return (
    <div className="scroll fade">
      <div className="dealhead">
        <button className="back" onClick={() => nav("/leads")}>←</button>
        <b style={{ fontSize: 16 }}>{lead.title}</b>
        <span className="muted">{funnel?.name}</span>
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        <button className="btn btn-green" onClick={convert}>✅ Конвертувати в сделку</button>
      </div>

      {funnel && (
        <div className="stagebar">
          {funnel.stages.map((s) => (
            <div key={s.id} className="stage" onClick={() => setStage(s.id)}
              style={{ cursor: "pointer", background: s.order <= curOrder ? "var(--brand)" : "#cbd5e1" }}>{s.name}</div>
          ))}
        </div>
      )}

      <div className="grid2">
        <div>
          <div className="panel">
            <div className="label">Клієнт</div>
            <div style={{ fontWeight: 600 }}>{lead.contact_name || "Без контакту"}</div>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button className="btn" style={{ flex: 1, background: "#ecfdf5", color: "#047857" }}>📞 Подзвонити</button>
              <button className="btn" style={{ flex: 1, background: "#eff6ff", color: "#1d4ed8" }}>💬 Чат</button>
            </div>
          </div>
          <div className="panel">
            <div className="label">Відповідальний</div>
            <div className="owner" style={{ fontSize: 13 }}><Avatar name={lead.owner_name || "—"} />{lead.owner_name || "—"}</div>
          </div>
          <div className="panel">
            <div className="label">Сума · Джерело</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{Number(lead.amount).toLocaleString("ru")} <span className="muted" style={{ fontSize: 14 }}>грн.</span></div>
            <div style={{ marginTop: 8 }}><SourceChip source={lead.source} /></div>
          </div>
        </div>
        <div>
          <div className="panel">
            <div className="label">Стрічка подій</div>
            <div className="muted" style={{ fontSize: 13 }}>Дзвінки, повідомлення з мессенджерів та задачі зʼявляться тут. Натисни «Конвертувати», щоб створити сделку з тим самим клієнтом.</div>
          </div>
        </div>
      </div>
    </div>
  );
}
