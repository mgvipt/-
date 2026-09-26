/* ШІ-РОП: розбір діалогів (Олег, 26.09.2026).
   Щоночі CRM читає вчорашні переписки, знаходить помилки і пропонує правила.
   26.09 переробив після зауваження Олега: «список чатів — просто полотно тексту, не видно чиї діалоги».
   Тепер видно: хто вів (менеджер чи ШІ), що саме зламалось, цитата, як треба було, і фільтри. */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Icon } from "../Icon";

type Prop = { n: number; title: string; rule: string; why: string; examples: any[]; status?: string; kb_id?: number };
type Issue = {
  conv_id: number; contact: string; channel: string; who: string;
  tags: string[]; tag_text: string; quotes: string[]; problem: string; better: string; ai_tag: string;
  fix?: string; agents?: string[]; agent_names?: string[];
  why?: string; steps?: string[]; qa?: { q: string; a: string; at: string }[];
  existing_rule?: string; missing_in?: string[];
  applied?: { kb_id: number; at: string; by: string };
  feedback?: { verdict: string; note: string };
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
};
const AI_NAMES = ["ai_assistant", "operator", "ШІ у каналі", "CRM"];

function fmtDate(s: string) {
  if (!s) return "";
  const [y, m, d] = s.split("-");
  return `${d}.${m}.${y.slice(2)}`;
}

/** «ai_assistant, Кирилл Оксаненко, ШІ у каналі · Meta · instagram» → ["ШІ", "Кирилл Оксаненко"] */
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
  const [fWho, setFWho] = useState("");
  const [fTag, setFTag] = useState("");
  const [chat, setChat] = useState<any | null>(null);     // дзеркало переписки в цьому ж вікні
  const [note, setNote] = useState("");
  const [ask, setAsk] = useState("");
  const [asking, setAsking] = useState(false);

  async function load(k = kind) {
    const r: any = await api.get(`/api/dialog-reviews/?kind=${k}`);
    const list: Review[] = r.results || [];
    setRows(list);
    if (list.length) await openOne(list[0].id);
    else setOpen(null);
  }
  async function openOne(id: number) {
    const r: any = await api.get(`/api/dialog-reviews/${id}/`);
    setOpen(r); setFWho(""); setFTag("");
  }
  useEffect(() => { void load(); }, [kind]);

  async function decide(p: Prop, status: "approved" | "declined") {
    if (!open) return;
    setBusy(`${p.n}`);
    try {
      let why = "";
      if (status === "declined") {
        why = window.prompt("Чому відхиляєте? Аналітик врахує це в наступних розборах:", "") || "";
      }
      await api.post(`/api/dialog-reviews/${open.id}/proposal/`, { n: p.n, status, note: why });
      const r: any = await api.get(`/api/dialog-reviews/${open.id}/`);
      setOpen(r);
    } finally { setBusy(""); }
  }
  async function showChat(convId: number) {
    if (!open) return;
    setChat({ conv_id: convId, loading: true, messages: [] });
    setNote("");
    const r: any = await api.get(`/api/dialog-reviews/${open.id}/dialog/?conv=${convId}`);
    setChat(r);
  }
  async function askRop(convId: number) {
    if (!open || !ask.trim()) return;
    setAsking(true);
    try {
      const r: any = await api.post(`/api/dialog-reviews/${open.id}/ask/`, { conv_id: convId, question: ask });
      const fresh: any = await api.get(`/api/dialog-reviews/${open.id}/`);
      setOpen(fresh);
      setChat((c: any) => ({ ...c, answer: r.answer, lastQ: ask }));
      setAsk("");
    } finally { setAsking(false); }
  }
  async function sendFeedback(convId: number, verdict: "wrong" | "ok") {
    if (!open) return;
    setBusy("fb");
    try {
      await api.post(`/api/dialog-reviews/${open.id}/issue_feedback/`, { conv_id: convId, verdict, note });
      const r: any = await api.get(`/api/dialog-reviews/${open.id}/`);
      setOpen(r); setNote("");
    } finally { setBusy(""); }
  }
  async function applyFix(it: Issue) {
    if (!open) return;
    setBusy(`fix${it.conv_id}`);
    try {
      await api.post(`/api/dialog-reviews/${open.id}/apply_fix/`, { conv_id: it.conv_id });
      const r: any = await api.get(`/api/dialog-reviews/${open.id}/`);
      setOpen(r);
    } finally { setBusy(""); }
  }
  async function runNow() {
    setBusy("run");
    try { await api.post(`/api/dialog-reviews/run/`, { weekly: kind === "weekly" }); await load(); }
    finally { setBusy(""); }
  }

  const issues = open?.issues || [];
  const byWho = useMemo(() => {
    const m: Record<string, { n: number; tags: Record<string, number> }> = {};
    for (const it of issues) {
      for (const p of people(it.who)) {
        m[p] = m[p] || { n: 0, tags: {} };
        m[p].n += 1;
        for (const t of it.tags || []) m[p].tags[t] = (m[p].tags[t] || 0) + 1;
      }
    }
    return Object.entries(m).sort((a, b) => b[1].n - a[1].n);
  }, [issues]);
  const byTag = useMemo(() => {
    const m: Record<string, number> = {};
    for (const it of issues) for (const t of it.tags || []) m[t] = (m[t] || 0) + 1;
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [issues]);
  const shown = issues.filter((it) =>
    (!fWho || people(it.who).includes(fWho)) && (!fTag || (it.tags || []).includes(fTag)));

  const st = open?.metrics?.stats || {};
  const cur = open?.metrics?.current || {};
  const prev = open?.metrics?.previous || {};
  const chip = (active: boolean): React.CSSProperties => ({
    fontSize: 12.5, borderRadius: 20, padding: "4px 11px", cursor: "pointer", border: "1px solid",
    borderColor: active ? "#0f172a" : "#e2e8f0", background: active ? "#0f172a" : "#fff",
    color: active ? "#fff" : "#334155",
  });

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
              {` · зауважень ${r.issues_count}`}
            </option>
          ))}
        </select>
        <button className="btn" onClick={runNow} disabled={!!busy}>
          <Icon n="refresh" size={14} /> {busy === "run" ? "Рахую…" : "Перерахувати"}
        </button>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "#64748b" }}>
          Розбір іде щоночі о 5:00 · звіт у Telegram
        </div>
      </div>

      {!open && <div style={CARD}>Розборів ще немає — натисніть «Перерахувати».</div>}

      {open && (
        <div style={CARD}>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 12 }}>
            {(open.kind === "daily"
              ? [["Діалогів", st.dialogs, null], ["З ціною", st.with_price, null], ["З накладною", st.with_invoice, null],
                 ["Сделок", st.deals, null], ["Оплат", st.payments, null], ["Із зауваженнями", open.issues_count, null]]
              : [["Діалогів", cur.dialogs, prev.dialogs], ["З ціною", cur.with_price, prev.with_price],
                 ["З накладною", cur.with_invoice, prev.with_invoice], ["Сделок", cur.deals, prev.deals],
                 ["Оплат", cur.payments, prev.payments], ["Із зауваженнями", cur.with_issues, prev.with_issues]]
            ).map(([l, v, p]: any) => (
              <div key={l}>
                <div style={{ fontSize: 12, color: "#64748b" }}>{l}</div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{v ?? "—"}
                  {p !== null && p !== undefined &&
                    <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 400 }}> (було {p})</span>}
                </div>
              </div>
            ))}
          </div>
          <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{open.summary}</div>
          {(open.metrics?.systemic || []).length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Повторюється системно</div>
              <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.65 }}>
                {(open.metrics.systemic || []).map((s: string, i: number) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
          <div style={{ marginTop: 10, fontSize: 12, color: "#94a3b8" }}>Розбір коштував ${open.cost_usd}</div>
        </div>
      )}

      {open && byWho.length > 0 && (
        <div style={CARD}>
          <div style={{ fontWeight: 600, marginBottom: 10 }}>Хто вів ці діалоги</div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", fontSize: 13.5, minWidth: 420 }}>
              <thead>
                <tr style={{ color: "#64748b", textAlign: "left" }}>
                  <th style={{ padding: "5px 12px 5px 0" }}>Хто</th>
                  <th style={{ padding: "5px 12px 5px 0" }}>Діалогів із зауваженнями</th>
                  <th style={{ padding: "5px 0" }}>Найчастіше</th>
                </tr>
              </thead>
              <tbody>
                {byWho.map(([name, d]) => {
                  const top = Object.entries(d.tags).sort((a, b) => b[1] - a[1])[0];
                  return (
                    <tr key={name} style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer" }}
                      onClick={() => setFWho(fWho === name ? "" : name)}>
                      <td style={{ padding: "7px 12px 7px 0", fontWeight: fWho === name ? 700 : 500 }}>
                        {name === "ШІ" ? "🤖 ШІ-продавець" : `👤 ${name}`}
                      </td>
                      <td style={{ padding: "7px 12px 7px 0" }}>{d.n}</td>
                      <td style={{ padding: "7px 0", color: "#475569" }}>
                        {top ? `${TAG_TEXT[top[0]] || top[0]} (${top[1]})` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {open && (open.proposals || []).length > 0 && (
        <div style={CARD}>
          <div style={{ fontWeight: 600, marginBottom: 10 }}>Правила на підтвердження</div>
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
                    <button className="btn btn-green" disabled={busy === `${p.n}`} onClick={() => decide(p, "approved")}>
                      Прийняти — у базу знань
                    </button>
                    <button className="btn" disabled={busy === `${p.n}`} onClick={() => decide(p, "declined")}>
                      Відхилити
                    </button>
                  </>
                ) : (
                  <div style={{ fontSize: 13, color: p.status === "approved" ? "#15803d" : "#64748b" }}>
                    {p.status === "approved"
                      ? `✓ Прийнято${p.kb_id ? ` — запис бази знань #${p.kb_id}` : ""}`
                      : "Відхилено"}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {open && issues.length > 0 && (
        <div style={CARD}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
            <div style={{ fontWeight: 600 }}>Діалоги із зауваженнями</div>
            <div style={{ fontSize: 13, color: "#64748b" }}>показано {shown.length} з {issues.length}</div>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
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
                {people(it.who).map((p) => (
                  <span key={p} style={{
                    fontSize: 11.5, borderRadius: 20, padding: "2px 9px",
                    background: p === "ШІ" ? "#eef2ff" : "#f1f5f9", color: p === "ШІ" ? "#4338ca" : "#334155",
                  }}>{p === "ШІ" ? "🤖 ШІ" : p}</span>
                ))}
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "7px 0" }}>
                {(it.tags || []).map((t) => (
                  <span key={t} style={{
                    fontSize: 11.5, background: "#fef3c7", color: "#92400e", borderRadius: 20, padding: "2px 9px",
                  }}>{TAG_TEXT[t] || t}</span>
                ))}
              </div>
              {it.problem && <div style={{ lineHeight: 1.55 }}>{it.problem}</div>}
              {Array.from(new Set(it.quotes || [])).slice(0, 2).map((q, i) => (
                <div key={i} style={{
                  marginTop: 6, fontSize: 13, color: "#475569", borderLeft: "3px solid #e2e8f0", paddingLeft: 10,
                }}>«{q}»</div>
              ))}
              {it.why && (
                <div style={{ marginTop: 6, fontSize: 13.5, color: "#475569" }}>
                  <b>Чому клієнт так відреагував: </b>{it.why}
                </div>
              )}
              {it.better && (
                <div style={{ marginTop: 8, fontSize: 13.5, background: "#f0fdf4", borderRadius: 8, padding: "8px 11px" }}>
                  <b style={{ color: "#15803d" }}>Як треба було написати: </b>{it.better}
                </div>
              )}
              {(it.steps || []).length > 0 && (
                <div style={{ marginTop: 8, fontSize: 13.5, background: "#fff7ed", borderRadius: 8, padding: "8px 11px" }}>
                  <b style={{ color: "#c2410c" }}>Що зробити в цьому чаті зараз:</b>
                  <ol style={{ margin: "5px 0 0", paddingLeft: 20, lineHeight: 1.6 }}>
                    {(it.steps || []).map((x, i) => <li key={i}>{x}</li>)}
                  </ol>
                </div>
              )}
              {it.fix && (
                <div style={{
                  marginTop: 8, fontSize: 13.5, background: "#eff6ff", border: "1px solid #bfdbfe",
                  borderRadius: 8, padding: "9px 11px",
                }}>
                  <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 5 }}>
                    <b style={{ color: "#1d4ed8" }}>
                      {it.existing_rule ? "Правило вже є — агент його порушив:" : "Що додати агенту:"}
                    </b>
                    {(it.agent_names || []).map((a) => (
                      <span key={a} style={{
                        fontSize: 11.5, borderRadius: 20, padding: "2px 9px",
                        background: a === "Юля ChatPlace" ? "#fdf2f8" : a === "Продавець CRM" ? "#ecfdf5" : "#f1f5f9",
                        color: a === "Юля ChatPlace" ? "#be185d" : a === "Продавець CRM" ? "#047857" : "#334155",
                      }}>{a}</span>
                    ))}
                  </div>
                  {it.existing_rule && (
                    <div style={{
                      fontSize: 13, background: "#fee2e2", color: "#991b1b", borderRadius: 6,
                      padding: "6px 9px", marginBottom: 6,
                    }}>
                      Чинне правило: {it.existing_rule}
                      {(it.missing_in || []).length > 0
                        ? ` · бракує: ${(it.missing_in || []).map((x) => x === "crm" ? "продавцю CRM" : "Юлі ChatPlace").join(", ")}`
                        : " · є в обох агентів — питання виконання, а не правил"}
                    </div>
                  )}
                  <div style={{ lineHeight: 1.5 }}>{it.fix}</div>
                  <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                    {it.applied?.kb_id ? (
                      <span style={{ fontSize: 12.5, color: "#15803d" }}>
                        ✓ додано продавцю CRM — запис бази знань #{it.applied.kb_id}
                      </span>
                    ) : (
                      <button className="btn btn-green" disabled={busy === `fix${it.conv_id}`}
                        onClick={() => applyFix(it)}>Додати продавцю CRM</button>
                    )}
                    {(it.agents || []).includes("chatplace") && (
                      <button className="btn" onClick={() => {
                        navigator.clipboard?.writeText(it.fix || "");
                        window.alert("Скопійовано — вставте в правила Юлі ChatPlace");
                      }}>Скопіювати для Юлі ChatPlace</button>
                    )}
                  </div>
                </div>
              )}
              <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center", flexWrap: "wrap" }}>
                <button className="btn" onClick={() => showChat(it.conv_id)}>💬 Показати діалог</button>
                {it.feedback?.verdict === "wrong" && (
                  <span style={{ fontSize: 12, color: "#b45309" }}>
                    ✎ ви позначили розбір неправильним{it.feedback?.note ? `: ${it.feedback.note}` : ""}
                  </span>
                )}
                {it.feedback?.verdict === "ok" && (
                  <span style={{ fontSize: 12, color: "#15803d" }}>✓ розбір підтверджено</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {chat && (
        <div onClick={() => setChat(null)}
          style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.35)", zIndex: 60 }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{
              position: "absolute", top: 0, right: 0, bottom: 0, width: "min(460px, 100%)", background: "#f8fafc",
              display: "flex", flexDirection: "column", boxShadow: "-4px 0 24px rgba(0,0,0,.18)",
            }}>
            <div style={{
              padding: "12px 14px", background: "#fff", borderBottom: "1px solid #e2e8f0",
              display: "flex", alignItems: "center", gap: 10,
            }}>
              <div style={{ fontWeight: 700 }}>{chat.contact || `Чат #${chat.conv_id}`}</div>
              <div style={{ fontSize: 12, color: "#64748b" }}>{chat.channel}</div>
              <a href={`/inbox?c=${chat.conv_id}`} target="_blank" rel="noreferrer"
                style={{ marginLeft: "auto", fontSize: 13 }}>відкрити чат ↗</a>
              <button className="btn" onClick={() => setChat(null)}>✕</button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              {chat.loading && <div style={{ color: "#64748b" }}>Завантажую переписку…</div>}
              {(chat.messages || []).map((m: any) => (
                <div key={m.id} style={{ display: "flex", justifyContent: m.dir === "in" ? "flex-start" : "flex-end" }}>
                  <div style={{
                    maxWidth: "82%", padding: "8px 11px", borderRadius: 12, fontSize: 13.5, lineHeight: 1.45,
                    whiteSpace: "pre-wrap", wordBreak: "break-word",
                    background: m.internal ? "#fffbeb" : m.dir === "in" ? "#fff" : "#e0f2fe",
                    border: m.internal ? "1px solid #fde68a" : "1px solid #e2e8f0",
                    color: m.internal ? "#92400e" : "#0f172a",
                  }}>
                    <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 3 }}>
                      {m.internal ? "службова нотатка" : m.dir === "in" ? "клієнт" : (m.who || "ми")}
                      {" · "}{new Date(m.at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </div>
                    {m.text}
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
              <div style={{ fontSize: 12.5, color: "#64748b", marginBottom: 6 }}>
                Якщо ШІ-РОП оцінив цей діалог неправильно — напишіть чому, він врахує це в наступних розборах
              </div>
              <textarea value={note} onChange={(e) => setNote(e.target.value)}
                placeholder="Напр.: клієнт сам просив не писати, тут усе зроблено правильно"
                style={{ width: "100%", minHeight: 54, borderRadius: 8, border: "1px solid #cbd5e1", padding: 8, fontSize: 13 }} />
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button className="btn" disabled={busy === "fb"} onClick={() => sendFeedback(chat.conv_id, "wrong")}>
                  Неправильно оцінив
                </button>
                <button className="btn btn-green" disabled={busy === "fb"} onClick={() => sendFeedback(chat.conv_id, "ok")}>
                  Розбір правильний
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
