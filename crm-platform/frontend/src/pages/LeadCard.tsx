import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, Funnel } from "../api";
import { Avatar, SourceChip } from "../ui";
import ChatPanel from "./ChatPanel";

interface Lead {
  id: number; title: string; contact: number | null; contact_name?: string; owner_name?: string;
  funnel: number; stage: number; source: string; amount: string; is_seen: boolean;
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
    setFunnel(await api.get<Funnel>(`/api/funnels/${l.funnel}/`));
  }
  useEffect(() => { load(); }, [id]);

  async function setStage(s: number) { await api.patch(`/api/leads/${id}/`, { stage: s }); load(); }
  async function convert() {
    const r = await api.post<{ deal: number }>(`/api/leads/${id}/convert/`, {});
    nav(`/deals/${r.deal}`);
  }

  if (!lead) return <div className="spin">Загрузка лида…</div>;
  const curOrder = funnel?.stages.find((s) => s.id === lead.stage)?.order ?? 0;

  return (
    <div className="scroll fade">
      <div className="dealhead">
        <button className="back" onClick={() => nav("/leads")}>←</button>
        <b style={{ fontSize: 16 }}>{lead.title}</b>
        <SourceChip source={lead.source} />
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        <button className="btn btn-primary" onClick={convert}>➡️ Конвертировать в сделку</button>
      </div>

      {funnel && (
        <div className="stagebar">
          {funnel.stages.map((s) => (
            <div key={s.id} className="stage" onClick={() => setStage(s.id)} style={{ cursor: "pointer", background: s.order <= curOrder ? "var(--brand)" : "#cbd5e1" }}>{s.name}</div>
          ))}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "330px 1fr 360px", gap: 14, padding: 14 }}>
        <div>
          <div className="panel">
            <div className="label">Контакт</div>
            <div style={{ fontWeight: 600 }}>{lead.contact_name || "Без контакта"}</div>
            <div style={{ marginTop: 8 }}><SourceChip source={lead.source} /></div>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button className="btn" style={{ flex: 1, background: "#ecfdf5", color: "#047857" }}>📞 Позвонить</button>
            </div>
          </div>
          <div className="panel">
            <div className="label">Ответственный</div>
            <div className="owner" style={{ fontSize: 13 }}><Avatar name={lead.owner_name || "—"} /> {lead.owner_name || "—"}</div>
          </div>
          <div className="panel">
            <div className="label">Статус</div>
            <div className="row"><span className="muted">Просмотрен</span><b>{lead.is_seen ? "да" : "нет"}</b></div>
          </div>
        </div>
        <div>
          <div className="panel">
            <div className="label">Лента событий</div>
            <div className="muted" style={{ fontSize: 13 }}>Источник лида: <SourceChip source={lead.source} />. Дальше — общайся в чате справа и конвертируй в сделку, когда клиент готов.</div>
          </div>
        </div>
        <ChatPanel contactId={lead.contact} />
      </div>
    </div>
  );
}
