/* Карточка лида: стадии + левая колонка (контакт/ответственный/сумма/источник)
 * + конвертация в сделку. Открывается из канбана лидов (/leads/:id). */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, Funnel } from "../api";
import { Avatar, SourceChip } from "../ui";
import ClientChat from "../ClientChat";
import NeedsForm from "../NeedsForm";
import CardFields from "../CardFields";
import ActivityLog from "../ActivityLog";
import { useLang } from "../i18n";
import { SocialLink } from "../social";

interface Lead {
  id: number; title: string; contact?: number; contact_name?: string; owner_name?: string; created_at?: string;
  funnel: number; stage: number; amount: string; source: string; is_seen: boolean; qualification?: any; card_fields?: any[]; contact_social_link?: string; contact_phone?: string;
}

export default function LeadCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const [lead, setLead] = useState<Lead | null>(null);
  const [notFound, setNotFound] = useState(false);
  const { t } = useLang();
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [chatW, setChatW] = useState(() => Number(localStorage.getItem("crm_card_chatW")) || 360);
  const [leftW, setLeftW] = useState(() => Number(localStorage.getItem("crm_card_leftW")) || 220);
  useEffect(() => {
    const onResize = () => {
      const w = window.innerWidth;
      setChatW((x) => Math.min(x, Math.max(280, w * 0.40)));
      setLeftW((x) => Math.min(x, Math.max(170, w * 0.26)));
    };
    window.addEventListener("resize", onResize);
    onResize();
    return () => window.removeEventListener("resize", onResize);
  }, []);
  const [msg, setMsg] = useState("");

  async function changeSource(src: string) {
    if (!lead) return;
    try { await api.patch(`/api/leads/${lead.id}/`, { source: src }); setLead({ ...lead, source: src }); } catch { /* ignore */ }
  }
  const [titleEdit, setTitleEdit] = useState(false); const [titleVal, setTitleVal] = useState("");
  async function saveTitle() { if (!lead) return; const v = titleVal.trim(); if (!v) { setTitleEdit(false); return; } try { await api.patch(`/api/leads/${lead.id}/`, { title: v }); setLead({ ...lead, title: v }); } catch { alert(t("Нет прав на изменение названия","Немає прав на зміну назви")); } setTitleEdit(false); }

  function startResizeLeft(e: any) {
    e.preventDefault();
    const startX = e.clientX, startW = leftW; let w = startW;
    function mv(ev: MouseEvent) { w = Math.min(440, Math.max(170, startW + (ev.clientX - startX))); setLeftW(w); }
    function up() { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); localStorage.setItem("crm_card_leftW", String(w)); }
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }

  function startResize(e: any) {
    e.preventDefault();
    const startX = e.clientX, startW = chatW; let w = startW;
    function mv(ev: MouseEvent) { w = Math.min(760, Math.max(280, startW + (startX - ev.clientX))); setChatW(w); }
    function up() { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); localStorage.setItem("crm_card_chatW", String(w)); }
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  }

  async function dialClient() {
    if (!lead?.contact) { setMsg(t("У лида нет контакта","У ліда немає контакту")); return; }
    try { const r: any = await api.post("/api/calls/dial/", { contact: lead.contact }); setMsg(t(`📞 АТС набирает ваш ${r.extension} — поднимите трубку`, `📞 АТС набирає ваш ${r.extension} — підніміть слухавку`)); }
    catch (e: any) { const m = String(e?.message || "").match(/"detail":"([^"]+)"/); setMsg(m ? m[1] : t("Ошибка звонка","Помилка дзвінка")); }
    setTimeout(() => setMsg(""), 7000);
  }

  async function openChat() {
    if (!lead || !lead.contact) { setMsg(t("У лида нет контакта","У ліда немає контакту")); return; }
    try {
      const r: any = await api.get<any>(`/api/conversations/?contact=${lead.contact}`);
      const conv = (r.results || r || [])[0];
      if (conv) nav(`/inbox?c=${conv.id}`);
      else setMsg(t("Переписки ещё нет — чат появится после первого сообщения","Переписки ще немає — чат зʼявиться після першого повідомлення"));
    } catch { setMsg(t("Не удалось открыть чат","Не вдалося відкрити чат")); }
  }

  async function load() {
    try {
      const l = await api.get<Lead>(`/api/leads/${id}/`);
      setLead(l);
      if (!funnel || funnel.id !== l.funnel) setFunnel(await api.get<Funnel>(`/api/funnels/${l.funnel}/`));
    } catch { setNotFound(true); }
  }
  useEffect(() => { load(); }, [id]);
  // live-оновлення стадії/відповідального без перезавантаження (не чіпає поля анкети)
  useEffect(() => {
    if (!id) return;
    const tm = setInterval(async () => {
      try {
        const l = await api.get<Lead>(`/api/leads/${id}/`);
        setLead((cur) => {
          if (!cur) return cur;
          const qCh = JSON.stringify((cur as any).qualification) !== JSON.stringify((l as any).qualification);
          if (cur.stage === l.stage && (cur as any).owner === (l as any).owner && cur.funnel === l.funnel && (cur as any).is_seen === (l as any).is_seen && !qCh) return cur;
          return { ...cur, stage: l.stage, owner: (l as any).owner, owner_name: (l as any).owner_name, funnel: l.funnel, is_seen: (l as any).is_seen, qualification: (l as any).qualification };
        });
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(tm);
  }, [id]);
  if (notFound) return (
    <div className="spin" style={{ flexDirection: "column", gap: 12 }}>
      <div>{t("Лид не найден — возможно, уже сконвертирован в сделку или удалён.", "Лід не знайдено — можливо, вже сконвертований у сделку або видалений.")}</div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn btn-primary" onClick={() => nav("/leads")}>{t("← К лидам", "← До лідів")}</button>
        <button className="btn" onClick={() => nav("/deals")}>{t("Открыть сделки", "Відкрити сделки")}</button>
      </div>
    </div>
  );
  if (!lead) return <div className="spin">{t("Загрузка лида…","Загрузка ліда…")}</div>;

  async function setStage(s: number) { await api.patch(`/api/leads/${id}/`, { stage: s }); load(); }
  async function convert() {
    const r = await api.post<{ deal_id: number }>(`/api/leads/${id}/convert/`, {});
    nav(`/deals/${r.deal_id}`);
  }
  const curOrder = funnel?.stages.find((s) => s.id === lead.stage)?.order ?? 0;

  return (
    <div className="scroll fade" style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 52px)", overflow: "hidden" }}>
      <div className="dealhead">
        <button className="back" onClick={() => nav("/leads")}>←</button>
        {titleEdit ? (
          <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
            <input value={titleVal} autoFocus onChange={(e) => setTitleVal(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") saveTitle(); if (e.key === "Escape") setTitleEdit(false); }} style={{ fontSize: 15, fontWeight: 700, padding: "3px 7px", borderRadius: 6, border: "1px solid #cbd5e1", minWidth: 200 }} />
            <button className="btn btn-primary" style={{ padding: "3px 9px" }} onClick={saveTitle}>✓</button>
            <button className="btn btn-light" style={{ padding: "3px 9px" }} onClick={() => setTitleEdit(false)}>✕</button>
          </span>
        ) : (
          <b style={{ fontSize: 16, cursor: "pointer" }} title={t("Клик — изменить название","Клік — змінити назву")} onClick={() => { setTitleVal(lead.title); setTitleEdit(true); }}>{lead.title} <span style={{ fontSize: 11, opacity: .45 }}>✏️</span></b>
        )}
        {lead.is_seen ? <span style={{ fontSize: 11, fontWeight: 700, color: "#16a34a", background: "#dcfce7", padding: "2px 9px", borderRadius: 20, whiteSpace: "nowrap" }} title={t("Ответили клиенту","Відповіли клієнту")}>✓ {t("Відповіли","Відповіли")}</span> : <span style={{ fontSize: 11, fontWeight: 700, color: "#fff", background: "#ef4444", padding: "2px 9px", borderRadius: 20, whiteSpace: "nowrap", boxShadow: "0 0 0 3px rgba(239,68,68,.18)" }} title={t("Клиент написал — не отвечено","Клієнт написав — не відповіли")}>● {t("Непереглянуто","Непереглянуто")}</span>}
        <span className="muted">{funnel?.name}</span>
        {lead.created_at && <span className="muted" style={{ fontSize: 12.5, whiteSpace: "nowrap" }} title={t("Лид появился","Лід зʼявився")}>🕓 {new Date(lead.created_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>}
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        <button className="btn btn-green" onClick={convert}>{t("✅ Конвертировать в сделку","✅ Конвертувати в сделку")}</button>
      </div>

      {funnel && (
        <div className="stagebar">
          {funnel.stages.map((s) => (
            <div key={s.id} className="stage" onClick={() => setStage(s.id)}
              style={{ cursor: "pointer", background: s.order <= curOrder ? "var(--brand)" : "#cbd5e1" }}>{s.name}</div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 12, padding: "0 16px 16px", alignItems: "stretch", flex: 1, minHeight: 0, overflow: "hidden" }}>
        <div style={{ width: leftW, flexShrink: 0, display: "flex", flexDirection: "column", gap: 12, overflowY: "auto", overflowX: "hidden" }}>
          <div className="panel">
            <div className="label">{t("Клиент","Клієнт")}</div>
            <div style={{ fontWeight: 600 }}>{lead.contact_name || t("Без контакта","Без контакту")}</div>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button className="btn" style={{ flex: 1, background: "#ecfdf5", color: "#047857" }} onClick={dialClient} title={t("Позвонить клиенту через нашу АТС","Подзвонити клієнту через нашу АТС")}>📞</button>
              <button className="btn" style={{ flex: 2, background: "#eff6ff", color: "#1d4ed8" }} onClick={openChat}>{t("💬 Чат","💬 Чат")}</button>
            </div>
            {lead.contact_phone && (
              <a href={`tel:${lead.contact_phone}`} style={{ display: "block", marginTop: 8, fontSize: 13, fontWeight: 600, color: "#0f172a" }}>📱 {lead.contact_phone}</a>
            )}
            <SocialLink link={lead.contact_social_link} />
          </div>
          <div className="panel">
            <div className="label">{t("Ответственный","Відповідальний")}</div>
            <div className="owner" style={{ fontSize: 13 }}><Avatar name={lead.owner_name || "—"} />{lead.owner_name || "—"}</div>
          </div>
          <div className="panel">
            <div className="label">{t("Сумма · Источник","Сума · Джерело")}</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{Number(lead.amount).toLocaleString("ru")} <span className="muted" style={{ fontSize: 14 }}>{t("грн.","грн.")}</span></div>
            <div style={{ marginTop: 8 }}>
              <SourceChip source={lead.source} />
              <select value={lead.source} onChange={(e) => changeSource(e.target.value)} title={t("Откуда лид (ChatPlace не различает платформу — выбери вручную)","Звідки лід (ChatPlace не розрізняє платформу — обери вручну)")}
                style={{ fontSize: 12, padding: "5px 8px", borderRadius: 7, border: "1px solid #e2e8f0", width: "100%", marginTop: 6 }}>
                {([["instagram", "Instagram"], ["telegram", "Telegram"], ["tiktok", "TikTok"], ["facebook", "Facebook"], ["viber", "Viber"], ["call", t("Звонок","Дзвінок")], ["site", t("Сайт","Сайт")], ["wholesale", t("Опт / дилеры","Опт / дилери")], ["designers", t("Дизайнеры","Дизайнери")], ["other", t("Другое","Інше")]] as [string, string][]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          </div>
          <CardFields leadId={lead.id} initial={lead.card_fields} />
          <ActivityLog kind="lead" id={lead.id} />
        </div>

        <div onMouseDown={startResizeLeft} title={t("Тяни, чтобы изменить ширину левого блока","Тягни, щоб змінити ширину лівого блоку")}
          style={{ width: 6, alignSelf: "stretch", cursor: "col-resize", background: "#eef2f7", borderRadius: 3, flexShrink: 0 }} />

        <div style={{ flex: 1, minWidth: 280, overflowY: "auto", overflowX: "hidden" }}>
          <NeedsForm leadId={lead.id} initial={lead.qualification} />
        </div>

        <div onMouseDown={startResize} title={t("Тяни, чтобы изменить ширину чата","Тягни, щоб змінити ширину чату")}
          style={{ width: 6, alignSelf: "stretch", cursor: "col-resize", background: "#e2e8f0", borderRadius: 3, flexShrink: 0 }} />

        <div style={{ width: chatW, flexShrink: 0, display: "flex", flexDirection: "column", overflowY: "auto" }}>
          <div className="panel" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div className="label">{t("💬 Чат с клиентом","💬 Чат з клієнтом")}</div>
            <div style={{ flex: 1, minHeight: 0 }}><ClientChat contact={lead.contact} /></div>
          </div>
        </div>
      </div>
    </div>
  );
}
