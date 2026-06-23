/* Карточка лида: стадии + левая колонка (контакт/ответственный/сумма/источник)
 * + конвертация в сделку. Открывается из канбана лидов (/leads/:id). */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, Funnel } from "../api";
import { Avatar, SourceChip } from "../ui";
import ClientChat from "../ClientChat";
import NeedsForm from "../NeedsForm";
import CardFields from "../CardFields";

interface Lead {
  id: number; title: string; contact?: number; contact_name?: string; owner_name?: string;
  funnel: number; stage: number; amount: string; source: string; is_seen: boolean; qualification?: any; card_fields?: any[];
}

export default function LeadCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const [lead, setLead] = useState<Lead | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [chatW, setChatW] = useState(360);
  const [leftW, setLeftW] = useState(220);
  const [msg, setMsg] = useState("");

  async function changeSource(src: string) {
    if (!lead) return;
    try { await api.patch(`/api/leads/${lead.id}/`, { source: src }); setLead({ ...lead, source: src }); } catch { /* ignore */ }
  }

  function startResizeLeft(e: any) {
    e.preventDefault();
    const startX = e.clientX, startW = leftW;
    function mv(ev: MouseEvent) { setLeftW(Math.min(440, Math.max(170, startW + (ev.clientX - startX)))); }
    function up() { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); }
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }

  function startResize(e: any) {
    e.preventDefault();
    const startX = e.clientX, startW = chatW;
    function mv(ev: MouseEvent) { setChatW(Math.min(760, Math.max(280, startW + (startX - ev.clientX)))); }
    function up() { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); }
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }

  async function openChat() {
    if (!lead || !lead.contact) { setMsg("У ліда немає контакту"); return; }
    try {
      const r: any = await api.get<any>(`/api/conversations/?contact=${lead.contact}`);
      const conv = (r.results || r || [])[0];
      if (conv) nav(`/inbox?c=${conv.id}`);
      else setMsg("Переписки ще немає — чат зʼявиться після першого повідомлення");
    } catch { setMsg("Не вдалося відкрити чат"); }
  }

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

      <div style={{ display: "flex", gap: 12, padding: "0 16px 16px", alignItems: "flex-start" }}>
        <div style={{ width: leftW, flexShrink: 0, display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="panel">
            <div className="label">Клієнт</div>
            <div style={{ fontWeight: 600 }}>{lead.contact_name || "Без контакту"}</div>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button className="btn" style={{ flex: 1, background: "#ecfdf5", color: "#047857" }}>📞</button>
              <button className="btn" style={{ flex: 2, background: "#eff6ff", color: "#1d4ed8" }} onClick={openChat}>💬 Чат</button>
            </div>
          </div>
          <div className="panel">
            <div className="label">Відповідальний</div>
            <div className="owner" style={{ fontSize: 13 }}><Avatar name={lead.owner_name || "—"} />{lead.owner_name || "—"}</div>
          </div>
          <div className="panel">
            <div className="label">Сума · Джерело</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{Number(lead.amount).toLocaleString("ru")} <span className="muted" style={{ fontSize: 14 }}>грн.</span></div>
            <div style={{ marginTop: 8 }}>
              <SourceChip source={lead.source} />
              <select value={lead.source} onChange={(e) => changeSource(e.target.value)} title="Звідки лід (ChatPlace не розрізняє платформу — обери вручну)"
                style={{ fontSize: 12, padding: "5px 8px", borderRadius: 7, border: "1px solid #e2e8f0", width: "100%", marginTop: 6 }}>
                {([["instagram", "Instagram"], ["telegram", "Telegram"], ["tiktok", "TikTok"], ["facebook", "Facebook"], ["viber", "Viber"], ["call", "Дзвінок"], ["site", "Сайт"], ["wholesale", "Опт / дилери"], ["designers", "Дизайнери"], ["other", "Інше"]] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          </div>
          <CardFields leadId={lead.id} initial={lead.card_fields} />
        </div>

        <div onMouseDown={startResizeLeft} title="Тягни, щоб змінити ширину лівого блоку"
          style={{ width: 6, alignSelf: "stretch", cursor: "col-resize", background: "#eef2f7", borderRadius: 3, flexShrink: 0 }} />

        <div style={{ flex: 1, minWidth: 300 }}>
          <NeedsForm leadId={lead.id} initial={lead.qualification} />
        </div>

        <div onMouseDown={startResize} title="Тягни, щоб змінити ширину чату"
          style={{ width: 6, alignSelf: "stretch", cursor: "col-resize", background: "#e2e8f0", borderRadius: 3, flexShrink: 0 }} />

        <div style={{ width: chatW, flexShrink: 0 }}>
          <div className="panel">
            <div className="label">💬 Чат з клієнтом</div>
            <ClientChat contact={lead.contact} />
          </div>
        </div>
      </div>
    </div>
  );
}
