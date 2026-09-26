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
      await api.post(`/api/dialog-reviews/${open.id}/proposal/`, { n: p.n, status });
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
              {it.better && (
                <div style={{ marginTop: 8, fontSize: 13.5, background: "#f0fdf4", borderRadius: 8, padding: "8px 11px" }}>
                  <b style={{ color: "#15803d" }}>Як треба було: </b>{it.better}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
