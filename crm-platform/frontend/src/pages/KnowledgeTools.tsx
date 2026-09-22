/* AI ЦЕНТР → База знань ✓ — інструменти ЗА КНОПКОЮ (14.09.2026, ai-kb2):
   «Перевірка чернеток», «Контролер» (лише за запуском), «Публікація в Юлю», картка «ШІ у веб-чаті».
   Нічого не працює за розкладом. Усе, що витрачає гроші на ШІ, показує оцінку ДО запуску. */
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

type Choice = { value: string; label: string };
export type Precheck = { label: string; label_display: string; reason: string; ref: number | null; stale: boolean; source: string; checked_at: string };
export type Run = {
  id: number; kind: string; kind_display: string; status: string; status_display: string; params: Record<string, unknown>;
  total: number; done: number; est_cost_usd: number; cost_usd: number; result: Record<string, any>; error: string;
  created_by_name: string; created_at: string; finished_at: string | null; backup_count: number;
};
export type ChannelAi = { id: number; name: string; kind: string; dialogs30: number; ai_reply: boolean; only_chats: string[]; chatplace: boolean };
export type WebSettings = {
  webchat_ai_enabled: boolean; webchat_model: string; webchat_items: number; reviewer_models: string[];
  webchat_estimate?: { model: string; per_reply_usd: number; models: string[] };
  // 17.09.2026 (Олег): усі налаштування ШІ — тут, в AI ЦЕНТРІ
  ai_silence_hours?: number; ai_max_per_day?: number; channels?: ChannelAi[];
};

const card: React.CSSProperties = { border: "1px solid #eef2f7", borderRadius: 10, padding: "10px 12px", background: "#fff" };
const inp: React.CSSProperties = { boxSizing: "border-box", border: "1px solid #e2e8f0", borderRadius: 8, padding: "7px 10px", fontSize: 13 };
const sel: React.CSSProperties = { ...inp, minWidth: 120 };
const chipBase: React.CSSProperties = { display: "inline-block", fontSize: 11, padding: "2px 8px", borderRadius: 999, fontWeight: 600 };
const note: React.CSSProperties = { background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "8px 12px", fontSize: 12.5, color: "#334155", margin: "10px 0" };

export const LABEL_STYLE: Record<string, { bg: string; color: string; short: string }> = {
  ready: { bg: "#dcfce7", color: "#166534", short: "✓ готово до затвердження" },
  fix: { bg: "#fef3c7", color: "#92400e", short: "✎ потрібна правка" },
  dup: { bg: "#e0e7ff", color: "#3730a3", short: "⧉ дубль" },
  conflict: { bg: "#fee2e2", color: "#b91c1c", short: "⚠ суперечить" },
};
export const LABEL_FILTERS: Choice[] = [
  { value: "ready", label: "✓ готово до затвердження" },
  { value: "fix", label: "✎ потрібна правка" },
  { value: "dup", label: "⧉ дубль" },
  { value: "conflict", label: "⚠ суперечить затвердженому / каталогу" },
  { value: "none", label: "ще не перевірено" },
  { value: "stale", label: "мітка застаріла (запис змінено)" },
];

export function errText(e: unknown) {
  const d = (e as { data?: { detail?: string } })?.data;
  if (d && typeof d === "object") return d.detail || JSON.stringify(d);
  return String(e);
}
export function usd(v: number | undefined | null) {
  const n = Number(v || 0);
  return "$" + (n < 0.01 ? n.toFixed(4) : n.toFixed(3));
}
function fmtDate(s: string | null | undefined) {
  if (!s) return "";
  try { return new Date(s).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); } catch { return s; }
}

export function CheckChip({ c }: { c?: Precheck | null }) {
  if (!c) return null;
  const s = LABEL_STYLE[c.label] || { bg: "#f1f5f9", color: "#334155", short: c.label_display };
  const text = c.label === "dup" && c.ref ? `⧉ дубль #${c.ref}` : c.label === "conflict" && c.ref ? `⚠ суперечить #${c.ref}` : s.short;
  return (
    <span title={c.reason || c.label_display} style={{ ...chipBase, background: c.stale ? "#f1f5f9" : s.bg, color: c.stale ? "#94a3b8" : s.color }}>
      {text}{c.stale ? " (застаріла — запис змінено)" : ""}
    </span>
  );
}

export function RunBox({ run, onUpdate, children }: { run: Run; onUpdate: (r: Run) => void; children?: React.ReactNode }) {
  useEffect(() => {
    if (run.status !== "running") return;
    const t = window.setTimeout(async () => {
      try { onUpdate(await api.get<Run>(`/api/knowledge/runs/${run.id}/`)); } catch { onUpdate({ ...run }); }
    }, 2000);
    return () => window.clearTimeout(t);
  }, [run, onUpdate]);
  const pct = run.total ? Math.min(100, Math.round((run.done / run.total) * 100)) : run.status === "running" ? 0 : 100;
  const color = run.status === "error" || run.status === "interrupted" ? "#b91c1c" : run.status === "done" ? "#15803d" : "#1d4ed8";
  return (
    <div style={{ ...card, marginTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", fontSize: 12.5 }}>
        <b style={{ color }}>{run.kind_display} №{run.id}: {run.status_display}</b>
        <span style={{ color: "#64748b" }}>{run.done}/{run.total} · оцінка {usd(run.est_cost_usd)} · фактично {usd(run.cost_usd)} · {run.created_by_name} {fmtDate(run.created_at)}</span>
      </div>
      <div style={{ height: 6, background: "#f1f5f9", borderRadius: 4, marginTop: 6 }}>
        <div style={{ width: pct + "%", height: 6, background: color, borderRadius: 4, transition: "width .3s" }} />
      </div>
      {run.error && <div style={{ color: "#b91c1c", fontSize: 12.5, marginTop: 6 }}>{run.error}</div>}
      {children}
    </div>
  );
}

/* ───────────────────────── Перевірка чернеток ───────────────────────── */

type PItem = { id: number; title: string; text: string; topic: string; topic_display: string; kind_display: string; version: number; replaces: number | null; precheck?: Precheck | null };
type PSummary = {
  drafts: number; counts: Record<string, number>; stale: number; unchecked: number; by_topic: Record<string, { drafts: number; ready: number }>;
  labels: Choice[]; model: string; runs: Run[]; can_run: boolean; is_owner: boolean;
};
type PEst = { drafts: number; code_only: number; ai_items: number; calls: number; est_usd: number; model: string };

export function PrecheckPanel({ topics, canApprove }: { topics: Choice[]; canApprove: boolean }) {
  const [topic, setTopic] = useState("");
  const [recheck, setRecheck] = useState(false);
  const [sum, setSum] = useState<PSummary | null>(null);
  const [est, setEst] = useState<PEst | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [label, setLabel] = useState("ready");
  const [rows, setRows] = useState<PItem[]>([]);
  const [count, setCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const topicLabel = (v: string) => topics.find((t) => t.value === v)?.label || v;

  const loadSum = useCallback(async () => {
    try {
      const d = await api.get<PSummary>(`/api/knowledge/precheck/${topic ? `?topic=${topic}` : ""}`);
      setSum(d);
      setRun((r) => r || (d.runs[0] && d.runs[0].status === "running" ? d.runs[0] : null));
    } catch (e) { window.alert(errText(e)); }
  }, [topic]);
  const loadRows = useCallback(async () => {
    const qs = new URLSearchParams({ status: "draft", page_size: "50", ordering: "topic" });
    if (label) qs.set("label", label);
    if (topic) qs.set("topic", topic);
    try {
      const d = await api.get<{ results: PItem[]; count: number }>(`/api/knowledge/items/?${qs.toString()}`);
      setRows(d.results); setCount(d.count);
    } catch (e) { window.alert(errText(e)); }
  }, [label, topic]);
  useEffect(() => { loadSum(); setEst(null); }, [loadSum]);
  useEffect(() => { loadRows(); }, [loadRows]);
  const onRun = useCallback((r: Run) => { setRun(r); if (r.status !== "running") { loadSum(); loadRows(); } }, [loadSum, loadRows]);

  async function estimate() {
    setBusy(true);
    try { setEst(await api.post<PEst>(`/api/knowledge/precheck/`, { topic, recheck, estimate: true })); } catch (e) { window.alert(errText(e)); } finally { setBusy(false); }
  }
  async function start() {
    if (!est) return;
    if (!window.confirm(`Перевірити ${est.drafts} чернеток${topic ? ` теми «${topicLabel(topic)}»` : ""}?\n` +
      `Кодом ($0): ${est.code_only}. ШІ (${est.model}): ${est.ai_items} у ${est.calls} викликах ≈ ${usd(est.est_usd)}.\n` +
      `Нічого не затверджується — лише мітки.`)) return;
    setBusy(true);
    try { setRun(await api.post<Run>(`/api/knowledge/precheck/`, { topic, recheck })); setEst(null); } catch (e) { window.alert(errText(e)); } finally { setBusy(false); }
  }
  async function approveReady(t: string) {
    try {
      const d = await api.post<{ count: number }>(`/api/knowledge/precheck/approve-ready/`, { topic: t });
      if (!d.count) { window.alert("У темі немає актуальних «готово»."); return; }
      if (!window.confirm(`Затвердити ${d.count} записів з міткою «готово» у темі «${topicLabel(t)}»? Агенти почнуть їх читати.`)) return;
      const r = await api.post<{ approved: number }>(`/api/knowledge/precheck/approve-ready/`, { topic: t, expected: d.count });
      window.alert(`Затверджено: ${r.approved}`);
      loadSum(); loadRows();
    } catch (e) { window.alert(errText(e)); }
  }
  async function approveOne(it: PItem) {
    try {
      await api.post(`/api/knowledge/items/${it.id}/approve/`, { note: "після попередньої перевірки" });
      setRows((rs) => rs.filter((x) => x.id !== it.id)); setCount((c) => c - 1); loadSum();
    } catch (e) { window.alert(errText(e)); }
  }

  const th: React.CSSProperties = { textAlign: "left", padding: "5px 8px", fontSize: 12, color: "#475569", borderBottom: "1px solid #e2e8f0" };
  const td: React.CSSProperties = { padding: "5px 8px", fontSize: 12.5, borderBottom: "1px solid #f1f5f9" };
  const byTopic = sum ? Object.entries(sum.by_topic).sort((a, b) => b[1].drafts - a[1].drafts) : [];
  return (
    <div>
      <div style={note}>
        Кожна чернетка отримує мітку: <b>готово до затвердження</b> / <b>потрібна правка</b> (з причиною) / <b>дубль #N</b> /
        <b> суперечить затвердженому або каталогу CRM</b>. Відомі помилки й дублі — кодом ($0), решта — Claude Haiku пачками.
        <b> Нічого не затверджується само</b>: затверджуєте ви — поштучно або «Затвердити всі «готово» у темі» (лише власник).
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <select value={topic} onChange={(e) => setTopic(e.target.value)} style={sel}><option value="">Усі теми</option>{topics.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select>
        <label style={{ fontSize: 12.5, display: "flex", gap: 4, alignItems: "center" }}><input type="checkbox" checked={recheck} onChange={(e) => { setRecheck(e.target.checked); setEst(null); }} /> перевірити заново вже перевірені</label>
        <button className="btn btn-light" disabled={busy} onClick={estimate}>Порахувати вартість ($0)</button>
        {est && (
          <span style={{ fontSize: 12.5, color: "#334155" }}>
            Чернеток <b>{est.drafts}</b>: кодом {est.code_only} ($0), ШІ — {est.ai_items} у {est.calls} викликах ≈ <b>{usd(est.est_usd)}</b> ({est.model})
          </span>
        )}
        {est && sum?.can_run && est.drafts > 0 && <button className="btn btn-primary" disabled={busy || run?.status === "running"} onClick={start}>Запустити перевірку</button>}
        {sum && !sum.can_run && <span style={{ fontSize: 12, color: "#94a3b8" }}>Запускає власник (право «затверджувати»)</span>}
      </div>
      {run && (
        <RunBox run={run} onUpdate={onRun}>
          {run.result?.counts && (
            <div style={{ fontSize: 12.5, marginTop: 6 }}>
              {Object.entries(run.result.counts as Record<string, number>).map(([k, v]) => <span key={k} style={{ marginRight: 12 }}>{LABEL_STYLE[k]?.short || k}: <b>{v}</b></span>)}
              {run.result.unlabeled ? <span>без мітки: {run.result.unlabeled}</span> : null}
            </div>
          )}
        </RunBox>
      )}
      {sum && (
        <div style={{ ...card, marginTop: 10 }}>
          <div style={{ fontSize: 12.5, marginBottom: 6 }}>
            Чернеток {topic ? `у темі «${topicLabel(topic)}»` : "усього"}: <b>{sum.drafts}</b> · не перевірено: {sum.unchecked} · мітка застаріла: {sum.stale}
            {" · "}{Object.entries(sum.counts).map(([k, v]) => (
              <button key={k} onClick={() => setLabel(k)} className="btn btn-light" style={{ padding: "1px 8px", marginRight: 4, fontSize: 12 }}>{LABEL_STYLE[k]?.short || k}: {v}</button>
            ))}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr><th style={th}>Тема</th><th style={th}>Чернеток</th><th style={th}>«Готово»</th><th style={th}></th></tr></thead>
              <tbody>
                {byTopic.map(([t, v]) => (
                  <tr key={t}>
                    <td style={td}>{topicLabel(t)}</td><td style={td}>{v.drafts}</td><td style={td}>{v.ready}</td>
                    <td style={td}>{sum.is_owner && v.ready > 0 && <button className="btn btn-green" style={{ padding: "2px 10px" }} onClick={() => approveReady(t)}>✓ Затвердити всі «готово» у темі ({v.ready})</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0 6px", flexWrap: "wrap" }}>
        <b style={{ fontSize: 13 }}>Чернетки з міткою:</b>
        <select value={label} onChange={(e) => setLabel(e.target.value)} style={sel}>{LABEL_FILTERS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select>
        <span style={{ fontSize: 12, color: "#64748b" }}>знайдено {count}{count > rows.length ? ` (показано ${rows.length})` : ""}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {rows.map((it) => (
          <div key={it.id} style={card}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>#{it.id} {it.title}</div>
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 3, alignItems: "center" }}>
                  <CheckChip c={it.precheck} />
                  <span style={{ fontSize: 11, color: "#94a3b8" }}>{it.topic_display} · {it.kind_display} · в.{it.version}{it.replaces ? ` · правка до #${it.replaces}` : ""}</span>
                </div>
              </div>
              {canApprove && <button className="btn btn-green" style={{ padding: "3px 10px", flexShrink: 0 }} onClick={() => approveOne(it)}>✓ Затвердити</button>}
            </div>
            {it.precheck?.reason && <div style={{ fontSize: 12, color: "#92400e", marginTop: 4 }}>Причина: {it.precheck.reason}</div>}
            <div style={{ fontSize: 12.5, color: "#334155", marginTop: 4, whiteSpace: "pre-wrap" }}>{it.text.length > 400 ? it.text.slice(0, 400) + "…" : it.text}</div>
          </div>
        ))}
        {rows.length === 0 && <div style={{ fontSize: 12.5, color: "#94a3b8" }}>Немає чернеток з цією міткою.</div>}
      </div>
    </div>
  );
}

/* ───────────────────────── Контролер (лише за запуском) ───────────────────────── */

type CRow = { conversation_id: number; link: string; title: string; channel: string; lint: string[]; findings: { type: string; problem: string; quote: string }[]; items: number[]; error: string };
type CInfo = { periods: Choice[]; scheduled: boolean; model: string; max: number; can_run: boolean; runs: Run[] };
type CEst = { count: number; skipped_already_checked: number; est_usd: number; model: string; max: number };
const FTYPE: Record<string, string> = { contradiction: "суперечність", missed_step: "пропущений крок", unknown_question: "питання без відповіді" };

export function ControllerPanel() {
  const [info, setInfo] = useState<CInfo | null>(null);
  const [period, setPeriod] = useState("yesterday");
  const [n, setN] = useState(20);
  const [est, setEst] = useState<CEst | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const d = await api.get<CInfo>(`/api/knowledge/controller/`);
      setInfo(d);
      setRun((r) => r || (d.runs[0] && d.runs[0].status === "running" ? d.runs[0] : null));
    } catch (e) { window.alert(errText(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setEst(null); }, [period, n]);
  const onRun = useCallback((r: Run) => { setRun(r); if (r.status !== "running") load(); }, [load]);

  async function estimate() {
    setBusy(true);
    try { setEst(await api.post<CEst>(`/api/knowledge/controller/`, { period, n, estimate: true })); } catch (e) { window.alert(errText(e)); } finally { setBusy(false); }
  }
  async function start() {
    if (!est || !est.count) return;
    if (!window.confirm(`Перевірити ${est.count} закритих чатів (${est.model}) ≈ ${usd(est.est_usd)}?\nЗнахідки стануть чернетками з посиланням на діалог — затверджуєте ви.`)) return;
    setBusy(true);
    try { setRun(await api.post<Run>(`/api/knowledge/controller/`, { period, n })); setEst(null); } catch (e) { window.alert(errText(e)); } finally { setBusy(false); }
  }
  const [onlyIssues, setOnlyIssues] = useState(true);
  const rows: CRow[] = (run?.result?.rows as CRow[]) || [];
  const hasIssue = (r: CRow) => r.lint.length > 0 || r.findings.length > 0 || r.items.length > 0;
  const shown = onlyIssues ? rows.filter(hasIssue) : rows;
  // 22.09.2026: підсумок рахуємо з рядків — у перерваного запуску result.drafts_created немає
  const runStats = (r: Run) => {
    const rr: CRow[] = (r.result?.rows as CRow[]) || [];
    return { checked: rr.length, issues: rr.filter(hasIssue).length,
      drafts: r.result?.drafts_created ?? rr.reduce((a, x) => a + x.items.length, 0) };
  };
  return (
    <div>
      <div style={note}>
        Контролер перевіряє закриті чати <b>лише коли ви натиснете «Запустити перевірку»</b> — розкладу немає
        {info && !info.scheduled ? " (перевірено: автозапуск вимкнений)" : ""}. Шукає суперечності з базою, пропущені кроки продажу, питання без відповіді.
        Кожна знахідка — чернетка з посиланням на діалог. Той самий чат двічі не оплачується. Максимум {info?.max || 100} чатів за раз.
      </div>
      {info && !info.can_run && <div style={{ fontSize: 12.5, color: "#94a3b8" }}>Запускає лише власник.</div>}
      {info?.can_run && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          {info.periods.map((p) => (
            <label key={p.value} style={{ fontSize: 13, display: "flex", gap: 4, alignItems: "center" }}>
              <input type="radio" checked={period === p.value} onChange={() => setPeriod(p.value)} /> {p.label}
            </label>
          ))}
          {period === "last_n" && <input type="number" min={1} max={info.max} value={n} onChange={(e) => setN(Math.max(1, Math.min(info.max, Number(e.target.value) || 1)))} style={{ ...inp, width: 70 }} />}
          <button className="btn btn-light" disabled={busy} onClick={estimate}>Порахувати вартість ($0)</button>
          {est && <span style={{ fontSize: 12.5 }}>Нових закритих чатів: <b>{est.count}</b>{est.skipped_already_checked ? ` (уже перевірені пропущено: ${est.skipped_already_checked})` : ""} ≈ <b>{usd(est.est_usd)}</b> ({est.model})</span>}
          {est && est.count > 0 && <button className="btn btn-primary" disabled={busy || run?.status === "running"} onClick={start}>Запустити перевірку</button>}
        </div>
      )}
      {run && (
        <RunBox run={run} onUpdate={onRun}>
          {rows.length > 0 && (
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", fontSize: 12.5, marginTop: 6 }}>
              <span>Перевірено чатів: <b>{runStats(run).checked}</b> · із зауваженнями: <b>{runStats(run).issues}</b> · нових чернеток: <b>{runStats(run).drafts}</b> (у «Записи», джерело «Рецензент»)</span>
              <label style={{ display: "flex", gap: 4, alignItems: "center" }}><input type="checkbox" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} /> лише із зауваженнями</label>
              <button className="btn btn-light" style={{ padding: "1px 8px", fontSize: 12 }} onClick={() => setRun(null)}>Закрити</button>
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
            {shown.map((r) => (
              <div key={r.conversation_id} style={{ borderTop: "1px dashed #e2e8f0", paddingTop: 6, fontSize: 12.5 }}>
                <a href={r.link} target="_blank" rel="noreferrer">Діалог №{r.conversation_id} ↗</a> {r.title} <span style={{ color: "#94a3b8" }}>{r.channel}</span>
                {r.lint.map((x, i) => <div key={"l" + i} style={{ color: "#92400e" }}>• кодом: {x}</div>)}
                {r.findings.map((f, i) => <div key={"f" + i} style={{ color: "#1e293b" }}>• ШІ, {FTYPE[f.type] || f.type}: {f.problem}{f.quote ? ` — «${f.quote}»` : ""}</div>)}
                {r.items.length > 0 && <div style={{ color: "#15803d" }}>Чернетки: {r.items.map((i, k) => <span key={i}>{k > 0 && ", "}<a href={`/ai-costs?kb=${i}`} target="_blank" rel="noreferrer">#{i} ↗</a></span>)}</div>}
                {r.error && <div style={{ color: "#94a3b8" }}>{r.error}</div>}
                {!r.lint.length && !r.findings.length && !r.error && <div style={{ color: "#94a3b8" }}>зауважень немає</div>}
              </div>
            ))}
          </div>
        </RunBox>
      )}
      {info && info.runs.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 12.5 }}>
          <b>Попередні запуски:</b>
          {info.runs.map((r) => (
            <div key={r.id}>
              <b>№{r.id}</b> {fmtDate(r.created_at)} · {r.status_display} · перевірено {runStats(r).checked} з {r.total} · із зауваженнями {runStats(r).issues} · чернеток {runStats(r).drafts} · {usd(r.cost_usd)}{" "}
              {runStats(r).checked > 0 && <button className="btn btn-primary" style={{ padding: "1px 10px", fontSize: 12 }} onClick={() => { setRun(r); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Відкрити результати</button>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ───────────────────────── Публікація в Юлю ───────────────────────── */

type PvItem = { item_id: number; version: number; question: string; new: string; old?: string; dataset?: string };
type Preview = { bot: string; label: string; remote_count: number; approved: number; same: number; add: PvItem[]; update: PvItem[]; changes: number; rules_not_published: number; fingerprint: string };
const BOTS: [string, string][] = [["ig", "Instagram"], ["tt", "TikTok"]];

export function PublishPanel({ isOwner }: { isOwner: boolean }) {
  const [pv, setPv] = useState<Record<string, Preview | null>>({});
  const [runs, setRuns] = useState<Record<string, Run | null>>({});
  const [busy, setBusy] = useState("");
  const onRun = useCallback((r: Run) => setRuns((x) => ({ ...x, [String(r.params?.bot || "")]: r })), []);
  if (!isOwner) return <div style={note}>Публікує в Юлю лише власник. Після затвердження записів він бачить тут різницю і підтверджує запис.</div>;

  async function preview(bot: string) {
    setBusy(bot);
    try { const d = await api.post<Preview>(`/api/knowledge/publish/preview/`, { bot }); setPv((p) => ({ ...p, [bot]: d })); } catch (e) { window.alert(errText(e)); } finally { setBusy(""); }
  }
  async function publish(bot: string) {
    const p = pv[bot];
    if (!p || !p.changes) return;
    if (!window.confirm(`Опублікувати в ${p.label}: додати ${p.add.length}, оновити ${p.update.length}?\n` +
      `Перед записом зберігається бекап бази ChatPlace (${p.remote_count} записів). Нічого не видаляється, глобальні правила Юлі не змінюються.`)) return;
    setBusy(bot);
    try {
      const r = await api.post<Run>(`/api/knowledge/publish/`, { bot, fingerprint: p.fingerprint, changes: p.changes });
      setRuns((x) => ({ ...x, [bot]: r })); setPv((x) => ({ ...x, [bot]: null }));
    } catch (e) {
      const d = (e as { data?: { preview?: Preview } }).data;
      window.alert(errText(e));
      if (d?.preview) setPv((x) => ({ ...x, [bot]: d.preview || null }));
    } finally { setBusy(""); }
  }
  return (
    <div>
      <div style={note}>
        Після затвердження: подивіться різницю між затвердженим у CRM і живою базою Юлі в ChatPlace і підтвердіть запис.
        Перед записом — бекап бази ChatPlace; нічого не видаляється; глобальні правила Юлі не змінюються; публікуються лише
        «Питання-відповідь», «Факт», «Шаблон» з позначкою потрібної Юлі.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 10 }}>
        {BOTS.map(([bot, name]) => {
          const p = pv[bot];
          const r = runs[bot];
          return (
            <div key={bot} style={card}>
              <b>Юля {name}</b>
              <div style={{ marginTop: 6 }}><button className="btn btn-light" disabled={!!busy} onClick={() => preview(bot)}>{busy === bot ? "Читаю ChatPlace…" : "Показати зміни"}</button></div>
              {p && (
                <div style={{ fontSize: 12.5, marginTop: 8 }}>
                  У ChatPlace зараз {p.remote_count} записів · затверджено для публікації {p.approved} · без змін {p.same} · оновити <b>{p.update.length}</b> · додати <b>{p.add.length}</b>
                  {p.rules_not_published > 0 && <div style={{ color: "#64748b" }}>Правила ({p.rules_not_published}) у глобальні правила ChatPlace не публікуються.</div>}
                  <div style={{ maxHeight: 360, overflowY: "auto", marginTop: 6 }}>
                    {p.update.map((x) => (
                      <div key={"u" + x.item_id} style={{ borderTop: "1px dashed #e2e8f0", padding: "4px 0" }}>
                        <b>~ #{x.item_id}</b> {x.question}
                        <div style={{ color: "#b91c1c", whiteSpace: "pre-wrap" }}>БУЛО: {x.old}</div>
                        <div style={{ color: "#15803d", whiteSpace: "pre-wrap" }}>СТАНЕ: {x.new}</div>
                      </div>
                    ))}
                    {p.add.map((x) => (
                      <div key={"a" + x.item_id} style={{ borderTop: "1px dashed #e2e8f0", padding: "4px 0" }}>
                        <b>+ #{x.item_id}</b> {x.question}<div style={{ color: "#15803d", whiteSpace: "pre-wrap" }}>{x.new}</div>
                      </div>
                    ))}
                  </div>
                  {p.changes > 0
                    ? <button className="btn btn-primary" style={{ marginTop: 8 }} disabled={!!busy} onClick={() => publish(bot)}>Опублікувати в Юлю {name} — {p.changes} змін</button>
                    : <div style={{ marginTop: 6, color: "#15803d" }}>Змін немає — Юля вже знає все затверджене.</div>}
                </div>
              )}
              {r && (
                <RunBox run={r} onUpdate={onRun}>
                  {r.result?.items && <div style={{ fontSize: 12.5, marginTop: 6 }}>Додано {r.result.added} · оновлено {r.result.updated} · помилок {(r.result.errors || []).length} · бекап у запуску №{r.id} ({r.backup_count} записів)</div>}
                  {(r.result?.errors || []).map((x: string, i: number) => <div key={i} style={{ fontSize: 12, color: "#b91c1c" }}>{x}</div>)}
                </RunBox>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ───────────────────────── ШІ у веб-чаті ───────────────────────── */

export function ChannelsAiCard({ s, isOwner, onSaved }: { s: WebSettings; isOwner: boolean; onSaved: (s: WebSettings) => void }) {
  /* 17.09.2026 (Олег): «ШІ має працювати як Юля: якщо менеджер написав — агент у цьому чаті мовчить,
     і час цієї паузи налаштовується в AI ЦЕНТРІ». Тут же вмикаємо ШІ по кожному каналу. */
  const [busy, setBusy] = useState(false);
  const [hours, setHours] = useState<number>(s.ai_silence_hours ?? 12);
  const [perDay, setPerDay] = useState<number>(s.ai_max_per_day ?? 15);
  const [edit, setEdit] = useState<number | null>(null);
  const [chats, setChats] = useState("");
  const channels = s.channels || [];
  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    try { onSaved(await api.patch<WebSettings>(`/api/knowledge/settings/`, body)); } catch (e) { window.alert(errText(e)); } finally { setBusy(false); }
  }
  function toggle(c: ChannelAi, on: boolean) {
    if (on && !window.confirm(`Увімкнути відповіді ШІ у каналі «${c.name}»?\n` +
      `Клієнтам почне відповідати ШІ з ${s.webchat_items} затверджених записів бази знань. Якщо менеджер уже пише в чаті — ШІ мовчить ${hours} год.\n` +
      `Спершу краще вказати «лише ці чати» і перевірити на своєму номері.`)) return;
    patch({ channel: c.id, ai_reply: on });
  }
  const th: React.CSSProperties = { textAlign: "left", padding: "6px 8px", fontSize: 12, color: "#475569", borderBottom: "1px solid #e2e8f0" };
  const td: React.CSSProperties = { padding: "6px 8px", fontSize: 12.5, borderBottom: "1px solid #f1f5f9", verticalAlign: "middle" };
  const on = channels.filter((c) => c.ai_reply).length;
  return (
    <div style={{ ...card, marginTop: 12, borderLeft: `4px solid ${on ? "#10b981" : "#94a3b8"}` }}>
      <b>ШІ відповідає у каналах</b> — зараз увімкнено в <b>{on}</b> з {channels.length}.
      <div style={{ fontSize: 12.5, color: "#475569", margin: "4px 0 8px" }}>
        Працює як Юля: відповідає з <b>затверджених</b> записів бази знань і цін каталогу; замовлення, оплата чи сумнів — «передала менеджеру».
        <b> Якщо менеджер написав клієнту — ШІ в цьому чаті мовчить</b> (час нижче). Instagram і TikTok веде Юля в ChatPlace — їх тут вмикати не треба.
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
        <label style={{ fontSize: 12.5 }}>Пауза після менеджера, годин:&nbsp;
          <input type="number" min={0} max={168} value={hours} disabled={!isOwner || busy}
            onChange={(e) => setHours(Number(e.target.value))} style={{ ...inp, width: 80 }} /></label>
        <label style={{ fontSize: 12.5 }}>Відповідей на добу в чаті:&nbsp;
          <input type="number" min={1} max={100} value={perDay} disabled={!isOwner || busy}
            onChange={(e) => setPerDay(Number(e.target.value))} style={{ ...inp, width: 80 }} /></label>
        {isOwner && <button className="btn btn-light" disabled={busy} onClick={() => patch({ ai_silence_hours: hours, ai_max_per_day: perDay })}>Зберегти</button>}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={th}>Канал</th><th style={th}>Діалогів за 30 днів</th><th style={th}>ШІ відповідає</th><th style={th}>Лише ці чати (перевірка)</th></tr></thead>
          <tbody>{channels.map((c) => (
            <tr key={c.id}>
              <td style={{ ...td, fontWeight: 600 }}>{c.name} <span style={{ color: "#94a3b8", fontWeight: 400 }}>{c.kind}</span></td>
              <td style={td}>{c.dialogs30}</td>
              <td style={td}>
                <button className={c.ai_reply ? "btn btn-primary" : "btn btn-light"} disabled={!isOwner || busy}
                  style={{ padding: "3px 10px", fontSize: 12 }} onClick={() => toggle(c, !c.ai_reply)}>
                  {c.ai_reply ? "увімкнено" : "вимкнено"}</button>
              </td>
              <td style={td}>
                {edit === c.id ? (
                  <span style={{ display: "inline-flex", gap: 6 }}>
                    <input value={chats} onChange={(e) => setChats(e.target.value)} placeholder="380971112233, 380980001122"
                      style={{ ...inp, width: 240 }} />
                    <button className="btn btn-primary" disabled={busy} style={{ padding: "3px 10px", fontSize: 12 }}
                      onClick={() => { patch({ channel: c.id, only_chats: chats }); setEdit(null); }}>OK</button>
                    <button className="btn btn-light" style={{ padding: "3px 10px", fontSize: 12 }} onClick={() => setEdit(null)}>×</button>
                  </span>
                ) : (
                  <span>
                    {c.only_chats.length ? c.only_chats.join(", ") : <span style={{ color: "#94a3b8" }}>усі чати каналу</span>}
                    {isOwner && <button className="btn btn-light" style={{ padding: "2px 8px", fontSize: 11.5, marginLeft: 6 }}
                      onClick={() => { setEdit(c.id); setChats(c.only_chats.join(", ")); }}>змінити</button>}
                  </span>
                )}
              </td>
            </tr>))}
          </tbody>
        </table>
      </div>
      {!isOwner && <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 6 }}>Вмикає лише власник.</div>}
    </div>
  );
}

export function WebchatCard({ s, isOwner, onSaved }: { s: WebSettings; isOwner: boolean; onSaved: (s: WebSettings) => void }) {
  const [busy, setBusy] = useState(false);
  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    try { onSaved(await api.patch<WebSettings>(`/api/knowledge/settings/`, body)); } catch (e) { window.alert(errText(e)); } finally { setBusy(false); }
  }
  function toggle(v: boolean) {
    if (v && !window.confirm(`Увімкнути ШІ у веб-чаті на сайті?\nВідповідатиме лише з ${s.webchat_items} затверджених записів з позначкою «Сайт». ` +
      `Ціни — лише з каталогу, знижки — лише за затвердженим правилом; замовлення, оплата або сумнів — одразу менеджер.\n` +
      `Орієнтовно ${usd(s.webchat_estimate?.per_reply_usd)} за відповідь.`)) return;
    patch({ webchat_ai_enabled: v });
  }
  async function audience(includeDrafts: boolean) {
    try {
      const d = await api.post<{ count: number }>(`/api/knowledge/webchat/audience/`, { include_drafts: includeDrafts });
      if (!d.count) { window.alert("Немає записів Юлі IG без позначки «Сайт»."); return; }
      if (!window.confirm(`Додати позначку «Сайт (веб-чат)» до ${d.count} записів Юлі IG${includeDrafts ? " (затверджених і чернеток)" : " (затверджених)"}? Текст записів не змінюється.`)) return;
      const r = await api.post<{ updated: number }>(`/api/knowledge/webchat/audience/`, { include_drafts: includeDrafts, expected: d.count });
      window.alert(`Готово: ${r.updated}`);
      patch({});
    } catch (e) { window.alert(errText(e)); }
  }
  return (
    <div style={{ ...card, marginTop: 12, borderLeft: `4px solid ${s.webchat_ai_enabled ? "#10b981" : "#94a3b8"}` }}>
      <b>ШІ відповідає у веб-чаті на сайті</b> — зараз <b>{s.webchat_ai_enabled ? "УВІМКНЕНО" : "вимкнено"}</b>.
      <div style={{ fontSize: 12.5, color: "#475569", marginTop: 4 }}>
        Вимкнено — усе як раніше: відвідувач одразу отримує «передала менеджеру». Увімкнено — Юля відповідає лише з
        <b> затверджених</b> записів з позначкою «Сайт» ({s.webchat_items} зараз) і цін каталогу CRM; знижки — лише за затвердженим правилом;
        замовлення, оплата, сумнів або цифра не з каталогу — «передала менеджеру», а менеджер бачить нотатку з причиною.
        Перевірити заздалегідь — «Тестовий чат» → «Сайт (веб-чат)». ≈ {usd(s.webchat_estimate?.per_reply_usd)} за відповідь ({s.webchat_model}).
      </div>
      {isOwner ? (
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
          <label style={{ display: "flex", gap: 5, alignItems: "center", fontSize: 13 }}>
            <input type="checkbox" disabled={busy} checked={s.webchat_ai_enabled} onChange={(e) => toggle(e.target.checked)} /> ШІ відповідає у веб-чаті
          </label>
          <select value={s.webchat_model} disabled={busy} onChange={(e) => patch({ webchat_model: e.target.value })} style={sel}>
            {(s.webchat_estimate?.models || s.reviewer_models || []).map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <button className="btn btn-light" onClick={() => audience(false)}>Додати «Сайт» до затверджених записів Юлі IG</button>
          <button className="btn btn-light" onClick={() => audience(true)}>… і до чернеток</button>
        </div>
      ) : <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 6 }}>Вмикає лише власник.</div>}
    </div>
  );
}
