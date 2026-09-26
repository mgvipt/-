/* ШІ-РОП: розбір діалогів (Олег, 26.09.2026).
   Переробка візуалу: сторінка відповідає на три питання — чого навчити агентів, що сказати людям,
   що полагодити. Список діалогів — деталі, які розкриваються, а не полотно тексту. */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Icon } from "../Icon";

type Prop = { n: number; title: string; rule: string; why: string; examples: any[]; status?: string; kb_id?: number };
type Issue = {
  conv_id: number; contact: string; channel: string; who: string;
  tags: string[]; tag_text: string; quotes: string[]; problem: string; better: string; ai_tag: string;
  fix?: string; agents?: string[]; agent_names?: string[]; why?: string; steps?: string[];
  existing_rule?: string; missing_in?: string[]; employee?: string; script?: string;
  when?: string; quote_at?: string;
  qa?: { q: string; a: string; at: string }[];
  applied?: { kb_id: number }; feedback?: { verdict: string; note: string };
};
type Review = {
  id: number; kind: string; period_start: string; period_end: string; created_at: string;
  summary: string; metrics: any; issues_count: number; issues?: Issue[]; proposals: Prop[]; cost_usd: number;
};

const CARD: React.CSSProperties = {
  background: "#fff", borderRadius: 12, padding: 16, boxShadow: "0 1px 3px rgba(0,0,0,.07)",
};
const TAG_TEXT: Record<string, string> = {
  no_question: "без питання в кінці",
  silence: "клієнт замовк",
  slow_reply: "відповіли пізніше 30 хв",
  dup_pay_link: "посилання на оплату двічі",
  repeat: "повтор того самого",
  wrong_page: "не та сторінка",
  price_dump: "прайс-дамп 3+ цін",
  send_failed: "повідомлення не дійшло",
};
const AI_NAMES = ["ai_assistant", "operator", "ШІ у каналі", "CRM"];

function fmtDate(s: string) {
  if (!s) return "";
  const [y, m, d] = s.split("-");
  return `${d}.${m}.${y.slice(2)}`;
}
function people(who: string): string[] {
  const out: string[] = [];
  let ai = false;
  for (const raw of (who || "").split(",")) {
    const name = raw.trim();
    if (!name) continue;
    if (AI_NAMES.some((a) => name.startsWith(a))) { ai = true; continue; }
    if (!out.includes(name)) out.push(name);
  }
  return ai ? ["ШІ", ...out] : out.length ? out : ["—"];
}

export default function DialogReview() {
  const [kind, setKind] = useState<"daily" | "weekly">("daily");
  const [rows, setRows] = useState<Review[]>([]);
  const [open, setOpen] = useState<Review | null>(null);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const [fWho, setFWho] = useState("");
  const [fTag, setFTag] = useState("");
  const [showDialogs, setShowDialogs] = useState(false);
  const [chat, setChat] = useState<any | null>(null);
  const [note, setNote] = useState("");
  const [ask, setAsk] = useState("");
  const [asking, setAsking] = useState(false);
  const [days, setDays] = useState(1);   // за який період рахувати новий розбір

  async function load(k = kind) {
    const r: any = await api.get(`/api/dialog-reviews/?kind=${k}`);
    const list: Review[] = r.results || [];
    setRows(list);
    if (list.length) await openOne(list[0].id); else setOpen(null);
  }
  async function openOne(id: number) {
    const r: any = await api.get(`/api/dialog-reviews/${id}/`);
    setOpen(r); setFWho(""); setFTag("");
  }
  useEffect(() => { void load(); }, [kind]);

  function flash(ok: boolean, text: string) {
    setToast({ ok, text });
    setTimeout(() => setToast(null), 8000);
  }
  async function decide(p: Prop, status: "approved" | "declined") {
    if (!open) return;
    setBusy(`p${p.n}`);
    try {
      let why = "";
      if (status === "declined") why = window.prompt("Чому відхиляєте? Аналітик врахує в наступних розборах:", "") || "";
      const res: any = await api.post(`/api/dialog-reviews/${open.id}/proposal/`, { n: p.n, status, note: why });
      await openOne(open.id);
      flash(true, status === "approved"
        ? `Правило «${p.title}» у базі знань${res?.proposal?.kb_id ? ` — запис #${res.proposal.kb_id}` : ""}. Його бачать усі агенти.`
        : `Правило «${p.title}» відхилено — аналітик це врахує.`);
    } catch (e: any) { flash(false, `Не вдалося: ${e?.message || "помилка"}`); }
    finally { setBusy(""); }
  }
  async function applyFix(it: Issue) {
    if (!open) return;
    setBusy(`f${it.conv_id}`);
    try {
      const res: any = await api.post(`/api/dialog-reviews/${open.id}/apply_fix/`, { conv_id: it.conv_id });
      await openOne(open.id);
      flash(true, `Правило додано продавцю CRM — запис бази знань #${res?.kb_id || ""}.`);
    } catch (e: any) { flash(false, `Не вдалося додати: ${e?.message || "помилка"}`); }
    finally { setBusy(""); }
  }
  async function showChat(convId: number) {
    if (!open) return;
    setChat({ conv_id: convId, loading: true, messages: [] }); setNote(""); setAsk("");
    const r: any = await api.get(`/api/dialog-reviews/${open.id}/dialog/?conv=${convId}`);
    setChat(r);
  }
  async function sendFeedback(convId: number, verdict: "wrong" | "ok") {
    if (!open) return;
    setBusy("fb");
    try {
      await api.post(`/api/dialog-reviews/${open.id}/issue_feedback/`, { conv_id: convId, verdict, note });
      await openOne(open.id); setNote("");
      flash(true, verdict === "wrong" ? "Записав: розбір неправильний. Аналітик врахує." : "Розбір підтверджено.");
    } finally { setBusy(""); }
  }
  async function askRop(convId: number) {
    if (!open || !ask.trim()) return;
    setAsking(true);
    try {
      await api.post(`/api/dialog-reviews/${open.id}/ask/`, { conv_id: convId, question: ask });
      await openOne(open.id);
      setAsk("");
    } catch (e: any) { flash(false, `ШІ-РОП не відповів: ${e?.message || "помилка"}`); }
    finally { setAsking(false); }
  }
  async function runNow() {
    setBusy("run");
    try { await api.post(`/api/dialog-reviews/run/`, { weekly: kind === "weekly", days }); await load(); }
    finally { setBusy(""); }
  }

  const issues = open?.issues || [];
  const st = open?.metrics?.stats || {};
  const delivery = st.delivery || {};
  const m = open?.metrics || {};
  const cur = m.current || {};
  const prev = m.previous || {};

  const missingCrm = issues.filter((i) => (i.missing_in || []).includes("crm"));
  const violations = issues.filter((i) => (i.existing_rule || "").trim() && !(i.missing_in || []).length);
  const byPerson = useMemo(() => {
    const map: Record<string, { n: number; advice: string[] }> = {};
    for (const it of issues) {
      const names = people(it.who).filter((p) => p !== "ШІ" && p !== "—");
      for (const p of names) {
        map[p] = map[p] || { n: 0, advice: [] };
        map[p].n += 1;
        if (it.employee && !map[p].advice.includes(it.employee)) map[p].advice.push(it.employee);
      }
    }
    return Object.entries(map).sort((a, b) => b[1].n - a[1].n);
  }, [issues]);
  const scripts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const it of issues) if (it.script) c[it.script] = (c[it.script] || 0) + 1;
    return Object.entries(c).sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [issues]);
  const byTag = useMemo(() => {
    const c: Record<string, number> = {};
    for (const it of issues) for (const t of it.tags || []) c[t] = (c[t] || 0) + 1;
    return Object.entries(c).sort((a, b) => b[1] - a[1]);
  }, [issues]);
  const shown = issues.filter((it) =>
    (!fWho || people(it.who).includes(fWho)) && (!fTag || (it.tags || []).includes(fTag)));

  const conv = st.dialogs ? Math.round((st.payments / st.dialogs) * 100) : 0;
  const chip = (active: boolean): React.CSSProperties => ({
    fontSize: 12.5, borderRadius: 20, padding: "4px 11px", cursor: "pointer", border: "1px solid",
    borderColor: active ? "#0f172a" : "#e2e8f0", background: active ? "#0f172a" : "#fff",
    color: active ? "#fff" : "#334155",
  });
  const H: React.CSSProperties = { fontSize: 15, fontWeight: 700, marginBottom: 10 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 1100, margin: "0 auto", width: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6 }}>
          {(["daily", "weekly"] as const).map((k) => (
            <button key={k} className="btn" onClick={() => setKind(k)}
              style={{ background: kind === k ? "#0f172a" : "#fff", color: kind === k ? "#fff" : "#0f172a" }}>
              {k === "daily" ? "За день" : "Тиждень"}
            </button>
          ))}
        </div>
        <select value={open?.id || ""} onChange={(e) => openOne(Number(e.target.value))}
          style={{ padding: "7px 10px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13.5 }}>
          {rows.map((r) => (
            <option key={r.id} value={r.id}>
              {r.kind === "weekly" ? `${fmtDate(r.period_start)} – ${fmtDate(r.period_end)}` : fmtDate(r.period_start)}
              {` · ${r.issues_count} зауважень`}
            </option>
          ))}
        </select>
        {kind === "daily" && (
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}
            title="За який період рахувати новий розбір"
            style={{ padding: "7px 10px", borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13.5 }}>
            <option value={1}>за вчора</option>
            <option value={3}>за 3 дні</option>
            <option value={7}>за тиждень</option>
            <option value={14}>за 2 тижні</option>
            <option value={30}>за місяць</option>
          </select>
        )}
        <button className="btn" onClick={runNow} disabled={!!busy}>
          <Icon n="refresh" size={14} /> {busy === "run" ? "Рахую…" : "Порахувати"}
        </button>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "#64748b" }}>щоночі о 5:00 · звіт у Telegram</div>
      </div>

      {toast && (
        <div style={{
          padding: "10px 14px", borderRadius: 10, fontSize: 13.5,
          background: toast.ok ? "#dcfce7" : "#fee2e2", color: toast.ok ? "#14532d" : "#991b1b",
          border: "1px solid " + (toast.ok ? "#86efac" : "#fca5a5"),
        }}>{toast.text}</div>
      )}
      {!open && <div style={CARD}>Розборів ще немає — натисніть «Перерахувати».</div>}

      {open && (
        <div style={CARD}>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap", marginBottom: 12 }}>
            {(open.kind === "daily"
              ? [["Діалогів", st.dialogs, null], ["Дійшли до ціни", st.with_price, null],
                 ["Отримали накладну", st.with_invoice, null], ["Оплат", st.payments, null],
                 ["Конверсія", conv ? conv + "%" : "—", null]]
              : [["Діалогів", cur.dialogs, prev.dialogs], ["До ціни", cur.with_price, prev.with_price],
                 ["Накладних", cur.with_invoice, prev.with_invoice], ["Оплат", cur.payments, prev.payments],
                 ["Із зауваженнями", cur.with_issues, prev.with_issues]]
            ).map(([l, v, p]: any) => (
              <div key={l}>
                <div style={{ fontSize: 12, color: "#64748b" }}>{l}</div>
                <div style={{ fontSize: 23, fontWeight: 700 }}>{v ?? "—"}
                  {p !== null && p !== undefined && <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 400 }}> (було {p})</span>}
                </div>
              </div>
            ))}
          </div>
          <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{open.summary}</div>
        </div>
      )}

      {open && (
        <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(310px, 1fr))" }}>
          {/* 1. агенти */}
          <div style={{ ...CARD, borderTop: "3px solid #4f46e5" }}>
            <div style={H}>🤖 Навчити агентів</div>
            <div style={{ fontSize: 13.5, marginBottom: 8 }}>
              Продавцю CRM бракує <b>{missingCrm.length}</b> правил, які вже знає Юля.
              {violations.length > 0 && <> Ще <b>{violations.length}</b> разів агенти порушили те, що вже прописано.</>}
            </div>
            <ul style={{ margin: "0 0 10px", paddingLeft: 18, lineHeight: 1.6, fontSize: 13.5 }}>
              {(m.agents_plan || []).map((x: string, i: number) => <li key={i}>{x}</li>)}
            </ul>
            {missingCrm.slice(0, 4).map((it) => (
              <div key={it.conv_id} style={{ borderTop: "1px solid #f1f5f9", padding: "8px 0", fontSize: 13 }}>
                <div style={{ color: "#334155" }}>{it.fix}</div>
                <div style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center" }}>
                  {it.applied?.kb_id
                    ? <span style={{ color: "#15803d", fontSize: 12.5 }}>✓ додано — запис #{it.applied.kb_id}</span>
                    : <button className="btn btn-green" disabled={busy === `f${it.conv_id}`} onClick={() => applyFix(it)}>
                        {busy === `f${it.conv_id}` ? "Додаю…" : "Додати продавцю CRM"}
                      </button>}
                  <button className="btn" onClick={() => showChat(it.conv_id)}>діалог</button>
                </div>
              </div>
            ))}
          </div>

          {/* 2. люди */}
          <div style={{ ...CARD, borderTop: "3px solid #0891b2" }}>
            <div style={H}>👤 Сказати людям</div>
            <ul style={{ margin: "0 0 10px", paddingLeft: 18, lineHeight: 1.6, fontSize: 13.5 }}>
              {(m.people_plan || []).map((x: string, i: number) => <li key={i}>{x}</li>)}
            </ul>
            {byPerson.map(([name, d]) => (
              <div key={name} style={{ borderTop: "1px solid #f1f5f9", padding: "8px 0", fontSize: 13 }}>
                <div style={{ fontWeight: 600 }}>{name} <span style={{ color: "#64748b", fontWeight: 400 }}>· {d.n} діалогів із зауваженнями</span></div>
                {d.advice.slice(0, 2).map((a, i) => <div key={i} style={{ color: "#334155", marginTop: 3 }}>• {a}</div>)}
              </div>
            ))}
            {scripts.length > 0 && (
              <div style={{ marginTop: 10, borderTop: "1px solid #f1f5f9", paddingTop: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 4 }}>Скрипти, які варто переписати</div>
                {scripts.map(([sName, n]) => (
                  <div key={sName} style={{ fontSize: 13, color: "#334155" }}>• {sName} <span style={{ color: "#94a3b8" }}>({n})</span></div>
                ))}
              </div>
            )}
          </div>

          {/* 3. доставка */}
          <div style={{ ...CARD, borderTop: "3px solid " + ((delivery.total || 0) > 0 ? "#dc2626" : "#16a34a") }}>
            <div style={H}>📮 Не дійшло до клієнтів</div>
            {(delivery.total || 0) === 0 ? (
              <div style={{ fontSize: 13.5, color: "#15803d" }}>Усі повідомлення доставлені 👍</div>
            ) : (
              <>
                <div style={{ fontSize: 13.5, marginBottom: 8 }}>
                  <b style={{ fontSize: 22 }}>{delivery.total}</b> повідомлень не дійшли
                  {delivery.by_kind?.failed ? ` · ${delivery.by_kind.failed} відхилив канал` : ""}
                  {delivery.by_kind?.window_risk ? ` · ${delivery.by_kind.window_risk} поза вікном 24 год` : ""}
                </div>
                {m.delivery_note && <div style={{ fontSize: 13, color: "#334155", marginBottom: 8 }}>{m.delivery_note}</div>}
                {(delivery.samples || []).slice(0, 5).map((x: any, i: number) => (
                  <div key={i} style={{ borderTop: "1px solid #f1f5f9", padding: "7px 0", fontSize: 13 }}>
                    <a href={`/inbox?c=${x.conv_id}`} target="_blank" rel="noreferrer" style={{ fontWeight: 600 }}>
                      {x.contact || `чат #${x.conv_id}`}
                    </a>
                    <span style={{ color: "#64748b" }}> · {x.kind}</span>
                    <div style={{ color: "#475569" }}>{x.text}</div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      )}

      {open && (open.proposals || []).length > 0 && (
        <div style={CARD}>
          <div style={H}>Правила на підтвердження</div>
          {(open.proposals || []).map((p) => (
            <div key={p.n} style={{
              border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, marginBottom: 10,
              background: p.status === "approved" ? "#f0fdf4" : p.status === "declined" ? "#f8fafc" : "#fff",
            }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{p.n}. {p.title}</div>
              <div style={{ lineHeight: 1.55 }}>{p.rule}</div>
              <div style={{ fontSize: 12, color: "#64748b", marginTop: 6 }}>{p.why}</div>
              <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                {!p.status || p.status === "new" ? (
                  <>
                    <button className="btn btn-green" disabled={busy === `p${p.n}`} onClick={() => decide(p, "approved")}>
                      {busy === `p${p.n}` ? "Додаю…" : "Прийняти — у базу знань"}
                    </button>
                    <button className="btn" disabled={busy === `p${p.n}`} onClick={() => decide(p, "declined")}>Відхилити</button>
                  </>
                ) : (
                  <div style={{ fontSize: 13, color: p.status === "approved" ? "#15803d" : "#64748b" }}>
                    {p.status === "approved" ? `✓ Прийнято${p.kb_id ? ` — запис #${p.kb_id}` : ""}` : "Відхилено"}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {open && issues.length > 0 && (
        <div style={CARD}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div style={H}>Діалоги із зауваженнями · {issues.length}</div>
            <button className="btn" style={{ marginLeft: "auto" }} onClick={() => setShowDialogs(!showDialogs)}>
              {showDialogs ? "Згорнути" : "Показати всі"}
            </button>
          </div>
          {showDialogs && (
            <>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "4px 0 12px" }}>
                <span style={chip(!fTag && !fWho)} onClick={() => { setFTag(""); setFWho(""); }}>усі</span>
                {byTag.map(([t, n]) => (
                  <span key={t} style={chip(fTag === t)} onClick={() => setFTag(fTag === t ? "" : t)}>
                    {TAG_TEXT[t] || t} · {n}
                  </span>
                ))}
              </div>
              {shown.map((it) => (
                <div key={it.conv_id} style={{ borderTop: "1px solid #f1f5f9", padding: "13px 0" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <a href={`/inbox?c=${it.conv_id}`} target="_blank" rel="noreferrer"
                      style={{ fontWeight: 700, fontSize: 15 }}>{it.contact || `Чат #${it.conv_id}`}</a>
                    <span style={{ fontSize: 12, color: "#64748b" }}>{it.channel}</span>
                    {it.when && <span style={{ fontSize: 12, color: "#94a3b8" }}>🕘 {it.when}</span>}
                    {people(it.who).map((p) => (
                      <span key={p} style={{
                        fontSize: 11.5, borderRadius: 20, padding: "2px 9px",
                        background: p === "ШІ" ? "#eef2ff" : "#f1f5f9", color: p === "ШІ" ? "#4338ca" : "#334155",
                      }}>{p === "ШІ" ? "🤖 ШІ" : p}</span>
                    ))}
                    {(it.tags || []).map((t) => (
                      <span key={t} style={{
                        fontSize: 11.5, background: "#fef3c7", color: "#92400e", borderRadius: 20, padding: "2px 9px",
                      }}>{TAG_TEXT[t] || t}</span>
                    ))}
                  </div>
                  {it.problem && <div style={{ marginTop: 6, lineHeight: 1.5 }}>{it.problem}</div>}
                  {(it.quotes || []).slice(0, 2).map((q, i) => (
                    <div key={i} style={{
                      marginTop: 5, fontSize: 13, color: "#475569", borderLeft: "3px solid #e2e8f0", paddingLeft: 10,
                    }}>{q}</div>
                  ))}
                  {it.quote_at && (
                    <div style={{ marginTop: 5, fontSize: 13, color: "#334155", borderLeft: "3px solid #fbbf24", paddingLeft: 10 }}>
                      {it.quote_at}
                    </div>
                  )}
                  {it.why && <div style={{ marginTop: 4, fontSize: 13.5, color: "#475569" }}><b>Чому: </b>{it.why}</div>}
                  {it.better && (
                    <div style={{ marginTop: 7, fontSize: 13.5, background: "#f0fdf4", borderRadius: 8, padding: "8px 11px" }}>
                      <b style={{ color: "#15803d" }}>Як треба було: </b>{it.better}
                    </div>
                  )}
                  {(it.steps || []).length > 0 && (
                    <ol style={{ margin: "7px 0 0", paddingLeft: 20, lineHeight: 1.6, fontSize: 13.5 }}>
                      {(it.steps || []).map((x, i) => <li key={i}>{x}</li>)}
                    </ol>
                  )}
                  <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <button className="btn" onClick={() => showChat(it.conv_id)}>💬 Показати діалог</button>
                    {it.fix && !it.applied?.kb_id && (
                      <button className="btn btn-green" disabled={busy === `f${it.conv_id}`} onClick={() => applyFix(it)}>
                        {busy === `f${it.conv_id}` ? "Додаю…" : "Додати правило продавцю CRM"}
                      </button>
                    )}
                    {it.applied?.kb_id && <span style={{ fontSize: 12.5, color: "#15803d" }}>✓ правило додано #{it.applied.kb_id}</span>}
                    {it.feedback?.verdict === "wrong" && <span style={{ fontSize: 12, color: "#b45309" }}>✎ ви позначили розбір неправильним</span>}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {chat && (
        <div onClick={() => setChat(null)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.35)", zIndex: 60 }}>
          <div onClick={(e) => e.stopPropagation()} style={{
            position: "absolute", top: 0, right: 0, bottom: 0, width: "min(460px, 100%)", background: "#f8fafc",
            display: "flex", flexDirection: "column", boxShadow: "-4px 0 24px rgba(0,0,0,.18)",
          }}>
            <div style={{ padding: "12px 14px", background: "#fff", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ fontWeight: 700 }}>{chat.contact || `Чат #${chat.conv_id}`}</div>
              <div style={{ fontSize: 12, color: "#64748b" }}>{chat.channel}</div>
              <a href={`/inbox?c=${chat.conv_id}`} target="_blank" rel="noreferrer" style={{ marginLeft: "auto", fontSize: 13 }}>відкрити чат ↗</a>
              <button className="btn" onClick={() => setChat(null)}>✕</button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              {chat.loading && <div style={{ color: "#64748b" }}>Завантажую переписку…</div>}
              {(chat.messages || []).map((msg: any) => (
                <div key={msg.id} style={{ display: "flex", justifyContent: msg.dir === "in" ? "flex-start" : "flex-end" }}>
                  <div style={{
                    maxWidth: "82%", padding: "8px 11px", borderRadius: 12, fontSize: 13.5, lineHeight: 1.45,
                    whiteSpace: "pre-wrap", wordBreak: "break-word",
                    background: msg.internal ? "#fffbeb" : msg.dir === "in" ? "#fff" : "#e0f2fe",
                    border: "1px solid " + (msg.internal ? "#fde68a" : "#e2e8f0"),
                  }}>
                    <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 3 }}>
                      {msg.internal ? "службова нотатка" : msg.dir === "in" ? "клієнт" : (msg.who || "ми")}
                      {" · "}{new Date(msg.at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </div>
                    {msg.text}
                  </div>
                </div>
              ))}
            </div>
            <div style={{ borderTop: "1px solid #e2e8f0", background: "#fff", padding: 12 }}>
              <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 6 }}>Спитати ШІ-РОПа</div>
              {(issues.find((x) => x.conv_id === chat.conv_id)?.qa || []).map((qa, i) => (
                <div key={i} style={{ marginBottom: 8, fontSize: 13, lineHeight: 1.5 }}>
                  <div style={{ color: "#64748b" }}>— {qa.q}</div>
                  <div style={{ background: "#eef2ff", borderRadius: 8, padding: "7px 10px", marginTop: 3 }}>{qa.a}</div>
                </div>
              ))}
              <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
                <input value={ask} onChange={(e) => setAsk(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") void askRop(chat.conv_id); }}
                  placeholder="Чому ти вважаєш, що тут помилка?"
                  style={{ flex: 1, borderRadius: 8, border: "1px solid #cbd5e1", padding: "8px 10px", fontSize: 13 }} />
                <button className="btn" disabled={asking || !ask.trim()} onClick={() => askRop(chat.conv_id)}>
                  {asking ? "…" : "Спитати"}
                </button>
              </div>
              <textarea value={note} onChange={(e) => setNote(e.target.value)}
                placeholder="Не згодні з розбором? Напишіть чому — аналітик врахує"
                style={{ width: "100%", minHeight: 48, borderRadius: 8, border: "1px solid #cbd5e1", padding: 8, fontSize: 13 }} />
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button className="btn" disabled={busy === "fb"} onClick={() => sendFeedback(chat.conv_id, "wrong")}>Неправильно оцінив</button>
                <button className="btn btn-green" disabled={busy === "fb"} onClick={() => sendFeedback(chat.conv_id, "ok")}>Розбір правильний</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
