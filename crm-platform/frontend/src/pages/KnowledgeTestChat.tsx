/* AI ЦЕНТР → База знань ✓ → «Тестовий чат» (14.09.2026, ai-kb2).
   Олег пише як клієнт — ШІ відповідає тими самими промптами, що справжній агент (apps/knowledge/answer.py).
   Під кожною відповіддю: які записи бази використано (клік — відкрити запис) і які ціни каталогу підставлено.
   Розмова живе лише в цій вкладці: не зберігається як чат і нікому не надсилається. «Почати заново» — очищає. */
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Icon } from "../Icon";
import { errText, usd } from "./KnowledgeTools";

type Choice = { value: string; label: string };
type AgentInfo = { value: string; label: string; model: string; note: string };
type Used = { id: number; title: string; status: string; topic: string; kind: string };
type Reply = {
  text: string; handoff: boolean; handoff_reason: string; draft_reply: string; used_items: Used[]; prices: string[];
  extra?: { context?: string; points?: string[] }; actions?: string[];
  cost: { usd: number; model: string; in_tok: number; out_tok: number };
  estimate: { usd: number; model: string; prompt_chars: number };
};
type CpAnswer = { answer?: string; answered?: boolean; note?: string; error?: string };
type Msg = { role: "client" | "agent"; text: string; reply?: Reply; error?: boolean; cp?: CpAnswer; cpBusy?: boolean };
type Peek = { id: number; title: string; text: string; status_display: string; topic_display: string; kind_display: string; version: number; audience: string[] };

const STATUS_COLOR: Record<string, string> = { approved: "#10b981", draft: "#f59e0b", archived: "#94a3b8" };
const inp: React.CSSProperties = { boxSizing: "border-box", border: "1px solid #e2e8f0", borderRadius: 8, padding: "7px 10px", fontSize: 13 };
const sel: React.CSSProperties = { ...inp, minWidth: 120 };
const small: React.CSSProperties = { fontSize: 11.5, color: "#64748b" };

function ItemPeek({ id, onClose }: { id: number; onClose: () => void }) {
  const [it, setIt] = useState<Peek | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setIt(null); setErr("");
    api.get<Peek>(`/api/knowledge/items/${id}/`).then(setIt).catch((e) => setErr(errText(e)));
  }, [id]);
  return (
    <div style={{ border: "1px solid #bfdbfe", background: "#eff6ff", borderRadius: 10, padding: 10, marginTop: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <b style={{ fontSize: 13 }}>Запис #{id}{it ? ` — ${it.title}` : ""}</b>
        <button className="btn btn-light" style={{ padding: "1px 8px" }} onClick={onClose}>✕</button>
      </div>
      {err && <div style={{ color: "#b91c1c", fontSize: 12.5 }}>{err}</div>}
      {it && (
        <>
          <div style={small}>{it.status_display} · {it.kind_display} · {it.topic_display} · в.{it.version} · агенти: {it.audience.join(", ") || "—"}</div>
          <div style={{ fontSize: 13, whiteSpace: "pre-wrap", marginTop: 6, color: "#1e293b" }}>{it.text}</div>
          <div style={{ ...small, marginTop: 6 }}>Змінити запис — вкладка «Записи» (пошук за №{id}).</div>
        </>
      )}
    </div>
  );
}

function ClientBubble({ m, canAskCp, onAskCp }: { m: Msg; canAskCp: boolean; onAskCp: () => void }) {
  return (
    <div style={{ alignSelf: "flex-end", maxWidth: "78%" }}>
      <div style={{ background: "#2563eb", color: "#fff", borderRadius: "12px 12px 2px 12px", padding: "7px 11px", fontSize: 13.5, whiteSpace: "pre-wrap" }}>{m.text}</div>
      {canAskCp && (
        <div style={{ textAlign: "right", marginTop: 2 }}>
          <button className="btn btn-light" style={{ padding: "1px 8px", fontSize: 11.5 }} disabled={m.cpBusy} onClick={onAskCp}>
            {m.cpBusy ? "питаю ChatPlace…" : "Як відповість зараз у ChatPlace"}
          </button>
        </div>
      )}
      {m.cp && (
        <div style={{ background: "#fdf4ff", border: "1px solid #f5d0fe", borderRadius: 8, padding: "6px 9px", marginTop: 4, fontSize: 12.5 }}>
          {m.cp.error ? <span style={{ color: "#b91c1c" }}>{m.cp.error}</span> : (
            <>
              <b>Юля в ChatPlace зараз:</b> <span style={{ whiteSpace: "pre-wrap" }}>{m.cp.answer || "(порожньо)"}</span>
              {m.cp.answered === false && <div style={{ color: "#92400e" }}>ChatPlace: у її базі немає відповіді на це питання.</div>}
              <div style={small}>{m.cp.note}</div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function AgentBubble({ m, onPeek }: { m: Msg; onPeek: (id: number) => void }) {
  const r = m.reply;
  return (
    <div style={{ alignSelf: "flex-start", maxWidth: "86%" }}>
      <div style={{ background: m.error ? "#fef2f2" : "#f1f5f9", color: m.error ? "#b91c1c" : "#0f172a", borderRadius: "12px 12px 12px 2px", padding: "7px 11px", fontSize: 13.5, whiteSpace: "pre-wrap" }}>{m.text}</div>
      {r && (
        <div style={{ marginTop: 3, paddingLeft: 4 }}>
          {r.handoff && (
            <div style={{ fontSize: 12, color: "#b45309", marginTop: 2 }}>
              <Icon n="user" size={12} /> Передала б менеджеру: {r.handoff_reason}
              {r.draft_reply && <div style={{ color: "#64748b", whiteSpace: "pre-wrap" }}>ШІ хотів відповісти: «{r.draft_reply}»</div>}
            </div>
          )}
          {r.extra?.context && <div style={{ fontSize: 12, color: "#334155" }}><Icon n="🎯" size={12} /> {r.extra.context}</div>}
          {(r.extra?.points || []).map((p, i) => <div key={i} style={{ fontSize: 12, color: "#475569" }}>• {p}</div>)}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center", marginTop: 3 }}>
            <span style={small}>Записи бази ({r.used_items.length}):</span>
            {r.used_items.map((u) => (
              <button key={u.id} onClick={() => onPeek(u.id)} title={u.title}
                style={{ border: `1px solid ${STATUS_COLOR[u.status] || "#e2e8f0"}`, background: "#fff", borderRadius: 999, padding: "0 7px", fontSize: 11.5, cursor: "pointer", color: "#1e293b" }}>
                #{u.id} {u.title.length > 38 ? u.title.slice(0, 38) + "…" : u.title}{u.status === "draft" ? " (чернетка)" : ""}
              </button>
            ))}
            {r.used_items.length === 0 && <span style={small}>жодного — агент працював на вбудованому тексті або база порожня</span>}
          </div>
          {r.prices.length > 0 && (
            <details style={{ marginTop: 2 }}>
              <summary style={{ ...small, cursor: "pointer" }}>Ціни з каталогу CRM у запиті ({r.prices.length})</summary>
              {r.prices.map((p, i) => <div key={i} style={{ fontSize: 11.5, color: "#334155" }}>{p}</div>)}
            </details>
          )}
          <div style={small}>{r.cost.model} · {r.cost.in_tok} → {r.cost.out_tok} ток. · {usd(r.cost.usd)}</div>
        </div>
      )}
    </div>
  );
}

export default function KnowledgeTestChat({ topics }: { topics: Choice[] }) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [canTest, setCanTest] = useState(false);
  const [agent, setAgent] = useState<string>(() => { try { return localStorage.getItem("kbTestAgent") || "yulia_web"; } catch { return "yulia_web"; } });
  const [drafts, setDrafts] = useState(true);
  const [topic, setTopic] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [est, setEst] = useState<Reply["estimate"] | null>(null);
  const [spent, setSpent] = useState(0);
  const [peek, setPeek] = useState<number | null>(null);
  const [loadErr, setLoadErr] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<{ agents: AgentInfo[]; can_test: boolean }>("/api/knowledge/test-chat/")
      .then((d) => { setAgents(d.agents); setCanTest(d.can_test); })
      .catch((e) => setLoadErr(errText(e)));
  }, []);
  useEffect(() => { try { localStorage.setItem("kbTestAgent", agent); } catch { /* немає сховища */ } }, [agent]);
  useEffect(() => { const b = boxRef.current; if (b) b.scrollTop = b.scrollHeight; }, [msgs, busy]);
  const history = (list: Msg[]) => list.filter((m) => !m.error).map((m) => ({ role: m.role, text: m.text }));
  useEffect(() => {  // оцінка вартості наступної відповіді — ШІ не викликається, $0
    if (!canTest) return;
    const id = window.setTimeout(() => {
      api.post<Reply>("/api/knowledge/test-chat/", { agent, include_drafts: drafts, topic, messages: history(msgs), estimate_only: true })
        .then((r) => setEst(r.estimate)).catch(() => setEst(null));
    }, 400);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent, drafts, topic, canTest, msgs.length]);

  async function send() {
    const text = input.trim();
    if (!text || busy || !canTest) return;
    const next: Msg[] = [...msgs, { role: "client", text }];
    setMsgs(next); setInput(""); setBusy(true);
    try {
      const r = await api.post<Reply>("/api/knowledge/test-chat/", { agent, include_drafts: drafts, topic, messages: history(next) });
      setMsgs([...next, { role: "agent", text: r.text, reply: r }]);
      setSpent((s) => s + (r.cost?.usd || 0));
    } catch (e) {
      setMsgs([...next, { role: "agent", text: "⚠️ " + errText(e), error: true }]);
    } finally { setBusy(false); }
  }
  function reset() { setMsgs([]); setSpent(0); setPeek(null); setInput(""); }
  async function askChatPlace(idx: number) {
    const bot = agent === "yulia_ig" ? "ig" : "tt";
    setMsgs((ms) => ms.map((m, i) => (i === idx ? { ...m, cpBusy: true } : m)));
    let cp: CpAnswer;
    try { cp = await api.post<CpAnswer>("/api/knowledge/test-chat/chatplace/", { bot, question: msgs[idx].text }); }
    catch (e) { cp = { error: errText(e) }; }
    setMsgs((ms) => ms.map((m, i) => (i === idx ? { ...m, cp, cpBusy: false } : m)));
  }

  const info = agents.find((a) => a.value === agent);
  const cpAgent = agent === "yulia_ig" || agent === "yulia_tiktok";
  if (loadErr) return <div style={{ color: "#b91c1c", fontSize: 13, marginTop: 10 }}>{loadErr}</div>;
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <select value={agent} onChange={(e) => setAgent(e.target.value)} style={sel}>
          {agents.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
        </select>
        <label style={{ fontSize: 12.5, display: "flex", gap: 4, alignItems: "center" }} title="Показати, як агент відповідатиме ПІСЛЯ затвердження чернеток">
          <input type="checkbox" checked={drafts} onChange={(e) => setDrafts(e.target.checked)} /> враховувати чернетки
        </label>
        <select value={topic} onChange={(e) => setTopic(e.target.value)} style={sel}>
          <option value="">Усі теми</option>{topics.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <button className="btn btn-light" onClick={reset}>↺ Почати заново</button>
      </div>
      {info && <div style={{ fontSize: 12, color: "#475569", marginTop: 6 }}>{info.note}</div>}
      <div style={{ ...small, marginTop: 4 }}>
        Модель: {est?.model || info?.model || "—"} · ≈ {usd(est?.usd)} за відповідь · витрачено в цьому тесті: {usd(spent)} ·
        {drafts ? " чернетки враховуються (як буде після затвердження)" : " лише затверджене (як зараз у справжнього агента)"} ·
        розмова не зберігається і клієнтам не надсилається
      </div>
      {!canTest && <div style={{ fontSize: 12.5, color: "#b45309", marginTop: 6 }}>Тестувати може співробітник із правом «База знань: додавати й правити чернетки».</div>}
      <div ref={boxRef} style={{ border: "1px solid #e2e8f0", borderRadius: 12, background: "#fff", marginTop: 8, padding: 10, height: 460, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
        {msgs.length === 0 && <div style={{ color: "#94a3b8", fontSize: 13, textAlign: "center", padding: 30 }}>Напишіть так, як написав би клієнт — напр. «Скільки коштує Галатея на 20 м²?»</div>}
        {msgs.map((m, idx) => (m.role === "client"
          ? <ClientBubble key={idx} m={m} canAskCp={cpAgent && canTest} onAskCp={() => askChatPlace(idx)} />
          : <AgentBubble key={idx} m={m} onPeek={setPeek} />))}
        {busy && <div style={{ ...small, alignSelf: "flex-start" }}>… агент пише відповідь</div>}
      </div>
      {peek !== null && <ItemPeek id={peek} onClose={() => setPeek(null)} />}
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <textarea value={input} onChange={(e) => setInput(e.target.value)} disabled={!canTest}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Повідомлення від імені клієнта… (Enter — надіслати, Shift+Enter — новий рядок)"
          style={{ ...inp, minHeight: 44, flex: 1, resize: "vertical" }} />
        <button className="btn btn-primary" onClick={send} disabled={busy || !input.trim() || !canTest}>Надіслати як клієнт</button>
      </div>
    </div>
  );
}
