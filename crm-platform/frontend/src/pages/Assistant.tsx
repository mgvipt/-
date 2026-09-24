/* «🧠 Асистент» (24.09.2026) — особистий ШІ-асистент Олега. Лише власник (API повертає 403 іншим).
 * Бот @wallcov_smm_bot через Telegram Business мовчки читає вибрані особисті чати й робочі групи, розшифровує голосові,
 * ШІ витягує факти/ціни/домовленості/рішення → пропозиції. «Додати в базу» створює ЧЕРНЕТКУ в базі знань
 * (агенти бачать лише затверджене в «AI ЦЕНТР»); домовленості — у приватному журналі тут.
 * Усі компоненти — на рівні модуля, щоб поля вводу не втрачали фокус. */
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

type Chat = { id: number; title: string; kind: string; kind_display: string; enabled: boolean; messages: number; voice: number; fresh: number };
type Proposal = {
  id: number; kind: string; kind_display: string; title: string; text: string; who: string; due: string | null; chat: string;
  evidence: { message_id: number; quote: string }[]; status: string; knowledge_item_id: number | null; created_at: string;
};
type Data = {
  settings: { extraction_enabled: boolean; monthly_budget_usd: number; spent_month_usd: number; owner_connected: boolean };
  chats: Chat[]; counts: Record<string, number>; proposals: Proposal[]; agreements: Proposal[]; pending_voice: number;
};
type Msg = { id: number; from_owner: boolean; author: string; kind: string; body: string; sent_at: string };

const CSS = `
.as{--bg:#14171a;--p:#1c2124;--p2:#252b2f;--ln:#2e363b;--ink:#e8ecee;--ink2:#9ca7ac;--ink3:#6b777c;--acc:#8fc2a6;--gold:#e3b85f;--bad:#e07a6e;
  background:var(--bg);color:var(--ink);border-radius:12px;height:100%;min-height:0;overflow:auto;padding:24px clamp(16px,2.4vw,32px) 40px}
.as-in{display:grid;gap:18px;min-width:820px;max-width:1200px}
.as h1{margin:0;font-size:clamp(24px,2.6vw,32px);font-weight:800}
.as-sub{color:var(--ink2);max-width:70ch;font-size:14px;line-height:1.55;margin:6px 0 0}
.as-row{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:14px}
.as-card{background:var(--p);border:1px solid var(--ln);border-radius:11px;padding:16px;display:grid;gap:10px;align-content:start}
.as-card h3{margin:0;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink2)}
.as-kv{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:var(--ink2)}
.as-kv b{color:var(--ink)}
.as-steps{margin:0;padding-left:18px;display:grid;gap:6px;font-size:13.5px;color:var(--ink)}
.as-btn{all:unset;box-sizing:border-box;cursor:pointer;height:32px;padding:0 12px;border-radius:8px;font-size:12.5px;font-weight:700;display:inline-flex;align-items:center;border:1px solid var(--ln);color:var(--ink2)}
.as-btn:hover{color:var(--ink)}
.as-btn.pri{background:var(--acc);border-color:transparent;color:#10231a}
.as-btn[disabled]{opacity:.45;cursor:default}
.as-btn:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.as-chat{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center;padding:8px 0;border-top:1px solid var(--ln);font-size:13px}
.as-chat:first-of-type{border-top:0}
.as-chat small{color:var(--ink3)}
.as-chips{display:flex;gap:6px;flex-wrap:wrap}
.as-chip{all:unset;cursor:pointer;font-size:12px;padding:6px 10px;border-radius:999px;border:1px solid var(--ln);color:var(--ink2)}
.as-chip.on{background:var(--p2);color:var(--ink);border-color:var(--ink3)}
.as-prop{background:var(--p);border:1px solid var(--ln);border-left:3px solid var(--acc);border-radius:10px;padding:12px 14px;display:grid;gap:6px}
.as-prop.price{border-left-color:var(--gold)} .as-prop.agreement{border-left-color:#7fb0d4} .as-prop.decision{border-left-color:#c79bd8}
.as-prop h4{margin:0;font-size:14.5px}
.as-tag{font-size:11px;padding:3px 7px;border-radius:5px;background:var(--p2);color:var(--ink2);margin-right:6px}
.as-q{font-size:12.5px;color:var(--ink3);border-left:2px solid var(--ln);padding-left:8px;margin:2px 0}
.as-msg{font-size:13px;padding:5px 0;border-top:1px solid var(--ln)}
.as-msg.me{color:var(--acc)}
.as-msgs{max-height:340px;overflow:auto}
.as-in-f{box-sizing:border-box;height:32px;background:var(--bg);border:1px solid var(--ln);border-radius:8px;color:var(--ink);padding:0 10px;font:inherit;font-size:12.5px;width:70px}
.as-msgok{color:var(--acc);font-size:13px} .as-msgerr{color:var(--bad);font-size:13px}
`;

const usd = (n: number) => "$" + (n < 0.1 ? n.toFixed(3) : n.toFixed(2));

function ChatRow({ c, onToggle, onOpen }: { c: Chat; onToggle: () => void; onOpen: () => void }) {
  return (
    <div className="as-chat">
      <div><b>{c.title || "без назви"}</b> <small>· {c.kind_display} · {c.messages} повідомл.{c.voice ? ` · ${c.voice} голосових` : ""}{c.fresh ? ` · ${c.fresh} нових` : ""}</small></div>
      <div className="as-chips">
        <button type="button" className="as-btn" onClick={onOpen}>Що чує</button>
        <button type="button" className={"as-btn" + (c.enabled ? "" : " pri")} onClick={onToggle}>{c.enabled ? "Не слухати" : "Слухати"}</button>
      </div>
    </div>
  );
}

function ProposalCard({ p, onAct }: { p: Proposal; onAct: (status: string) => void }) {
  return (
    <div className={"as-prop " + p.kind}>
      <div><span className="as-tag">{p.kind_display}</span>{p.who && <span className="as-tag">{p.who}</span>}{p.due && <span className="as-tag">до {new Date(p.due).toLocaleDateString("uk-UA")}</span>}<span className="as-tag">{p.chat}</span></div>
      <h4>{p.title}</h4>
      <div style={{ fontSize: 13.5, lineHeight: 1.5 }}>{p.text}</div>
      {p.evidence.map((e, i) => <div key={i} className="as-q">«{e.quote}»</div>)}
      {p.status === "new" ? (
        <div className="as-chips">
          <button type="button" className="as-btn pri" onClick={() => onAct("accepted")}>{p.kind === "agreement" ? "У журнал" : "Додати в базу (чернетка)"}</button>
          <button type="button" className="as-btn" onClick={() => onAct("rejected")}>Відхилити</button>
        </div>
      ) : <div className="as-kv"><span>{p.status === "accepted" ? (p.knowledge_item_id ? `Чернетка в базі знань #${p.knowledge_item_id} — затвердіть в «AI ЦЕНТР»` : "У журналі") : "Відхилено"}</span>
        <button type="button" className="as-btn" onClick={() => onAct("new")}>Повернути</button></div>}
    </div>
  );
}

export default function Assistant() {
  const [data, setData] = useState<Data | null>(null);
  const [status, setStatus] = useState("new");
  const [open, setOpen] = useState<{ title: string; messages: Msg[] } | null>(null);
  const [budget, setBudget] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { const d = await api.get<Data>(`/api/assistant/?status=${status}`); setData(d); setBudget(String(d.settings.monthly_budget_usd)); }
    catch (e: any) { setMsg({ ok: false, text: e?.status === 403 ? "Асистент доступний лише власнику." : "Не вдалося завантажити." }); }
  }, [status]);
  useEffect(() => { load(); }, [load]);
  const save = async (b: Record<string, unknown>) => { try { await api.patch("/api/assistant/", b); load(); } catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося." }); } };
  const run = async (action: string) => {
    setBusy(true); setMsg(null);
    try { const r: any = await api.post("/api/assistant/", { action }); setMsg({ ok: true, text: action === "extract" ? `Нових пропозицій: ${r.done}` : `Розшифровано: ${r.done}` }); load(); }
    catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося." }); } finally { setBusy(false); }
  };
  const toggle = async (c: Chat) => { await api.patch(`/api/assistant/chats/${c.id}/`, { enabled: !c.enabled }); load(); };
  const openChat = async (c: Chat) => setOpen(await api.get(`/api/assistant/chats/${c.id}/`));
  const act = async (p: Proposal, st: string) => { await api.patch(`/api/assistant/proposals/${p.id}/`, { status: st }); load(); };
  const s = data?.settings;
  return (
    <div className="as">
      <style>{CSS}</style>
      <div className="as-in">
        <div>
          <h1>🧠 Асистент</h1>
          <p className="as-sub">Мовчки слухає ваші переписки й голосові, розшифровує їх і пропонує, що записати в базу знань: ціни й умови постачальників,
            домовленості з таргетологом, ваші рішення. У базу нічого не потрапляє без вашої кнопки, а агенти бачать лише затверджене.</p>
        </div>
        {msg && <div className={msg.ok ? "as-msgok" : "as-msgerr"}>{msg.text}</div>}
        {data && s && (<>
          <div className="as-row">
            <div className="as-card">
              <h3>Підключення</h3>
              <div className="as-kv"><span>Ваш Telegram</span><b>{s.owner_connected ? "підключено ✓" : "ще не підключено"}</b></div>
              <ol className="as-steps">
                <li>Telegram → Налаштування → <b>Telegram для бізнесу</b> → <b>Чат-боти</b>.</li>
                <li>Вкажіть бота <b>@wallcov_smm_bot</b>.</li>
                <li>Доступ: «Усі особисті чати» або виберіть потрібні (таргетолог, постачальники). Можна виключити особисті.</li>
                <li><b>Вимкніть</b> «Відповідати на повідомлення» — бот лише слухає, нікому не пише.</li>
                <li>Напишіть або надішліть голосове в будь-який підключений чат (напр., таргетологу) — повідомлення зʼявиться тут. «Обране» бот не бачить.</li>
              </ol>
            </div>
            <div className="as-card">
              <h3>Розбір · витрати</h3>
              <div className="as-kv"><span>Витрачено цього місяця</span><b>{usd(s.spent_month_usd)} з {usd(s.monthly_budget_usd)}</b></div>
              <div className="as-kv"><span>Голосових чекає розшифровки</span><b>{data.pending_voice}</b></div>
              <div className="as-chips">
                <button type="button" className="as-btn" disabled={busy || !data.pending_voice} onClick={() => run("transcribe")}>Розшифрувати зараз</button>
                <button type="button" className="as-btn pri" disabled={busy} onClick={() => run("extract")}>{busy ? "Аналізую…" : "Розібрати нові зараз"}</button>
              </div>
              <div className="as-chips">
                <button type="button" className={"as-btn" + (s.extraction_enabled ? "" : " pri")} onClick={() => save({ extraction_enabled: !s.extraction_enabled })}>
                  {s.extraction_enabled ? "Вимкнути нічний розбір" : "Розбирати щоночі"}</button>
                <label className="as-kv" htmlFor="as-budget" style={{ alignItems: "center" }}>ліміт $/міс</label>
                <input id="as-budget" className="as-in-f" inputMode="decimal" value={budget} onChange={(e) => setBudget(e.target.value)}
                  onBlur={() => budget !== String(s.monthly_budget_usd) && save({ monthly_budget_usd: budget })} />
              </div>
              <div className="as-kv"><span>Голосові розшифровуються кожні 5 хв (≈$0.001 за хвилину мовлення).</span></div>
            </div>
          </div>
          <div className="as-card">
            <h3>Чати ({data.chats.length})</h3>
            {data.chats.length === 0 ? <div className="as-kv"><span>Поки порожньо — підключіть бота за інструкцією вище.</span></div>
              : data.chats.map((c) => <ChatRow key={c.id} c={c} onToggle={() => toggle(c)} onOpen={() => openChat(c)} />)}
            {open && (<div>
              <div className="as-kv"><b>{open.title}</b><button type="button" className="as-btn" onClick={() => setOpen(null)}>Закрити</button></div>
              <div className="as-msgs">{open.messages.map((m) => <div key={m.id} className={"as-msg" + (m.from_owner ? " me" : "")}>
                {new Date(m.sent_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} · {m.from_owner ? "Ви" : m.author}{m.kind !== "text" ? ` · ${m.kind}` : ""}: {m.body || "—"}</div>)}</div>
            </div>)}
          </div>
          <div className="as-card">
            <h3>Пропозиції</h3>
            <div className="as-chips">
              {[["new", "Нові"], ["accepted", "Додано"], ["rejected", "Відхилено"], ["all", "Усі"]].map(([v, l]) =>
                <button key={v} type="button" className={"as-chip" + (status === v ? " on" : "")} onClick={() => setStatus(v)}>{l}{data.counts[v] ? ` · ${data.counts[v]}` : ""}</button>)}
            </div>
            {data.proposals.length === 0 ? <div className="as-kv"><span>Тут зʼявиться те, що варто запамʼятати з ваших розмов.</span></div>
              : data.proposals.map((p) => <ProposalCard key={p.id} p={p} onAct={(st) => act(p, st)} />)}
          </div>
          <div className="as-card">
            <h3>Журнал домовленостей (бачите лише ви)</h3>
            {data.agreements.length === 0 ? <div className="as-kv"><span>Порожньо.</span></div>
              : data.agreements.map((p) => <div key={p.id} className="as-kv"><span><b>{p.title}</b> · {p.who} · {p.text}</span><b>{p.due ? new Date(p.due).toLocaleDateString("uk-UA") : "без строку"}</b></div>)}
          </div>
        </>)}
      </div>
    </div>
  );
}
