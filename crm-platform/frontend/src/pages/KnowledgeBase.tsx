/* AI ЦЕНТР → «База знань ✓» — ЄДИНА база знань для всіх ІІ-агентів CRM (14.09.2026).
   Агенти читають лише «Затверджено». Нове додається чернеткою → затверджує власник (право knowledge.approve).
   Вкладки: Записи · Тестовий чат (+ «Що бачить агент») · Перевірка чернеток · Контролер · Публікація в Юлю · Команда агентів
   (ai-kb2, 14.09: усе, що витрачає гроші на ІІ, — лише за кнопкою, з оцінкою вартості). */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import KnowledgeTestChat from "./KnowledgeTestChat";
import { CheckChip, ControllerPanel, LABEL_FILTERS, PrecheckPanel, PublishPanel, WebchatCard, type Precheck } from "./KnowledgeTools";

type Choice = { value: string; label: string };
type Role = { agent: string; name: string; does: string; reads: string; checked_by: string };
type KSettings = {
  reviewer_enabled: boolean; reviewer_model: string; reviewer_sample: number; reviewer_models: string[];
  webchat_ai_enabled: boolean; webchat_model: string; webchat_items: number;
  webchat_estimate?: { model: string; per_reply_usd: number; models: string[] };
};
type Meta = {
  kinds: Choice[]; topics: Choice[]; audiences: Choice[]; statuses: Choice[]; sources: Choice[];
  counts: Record<string, number>; flagged_drafts: number; reviewer_drafts: number;
  can_edit: boolean; can_approve: boolean; is_owner: boolean; settings: KSettings; roles: Role[];
};
type Item = {
  id: number; kind: string; kind_display: string; topic: string; topic_display: string; audience: string[];
  status: string; status_display: string; title: string; text: string; internal_note: string;
  products: number[]; product_names: string[]; source: string; source_display: string; source_ref: string;
  evidence: { conversation_id?: number; conversation_ids?: number[]; problem?: string; quote?: string };
  replaces: number | null; priority: number; popularity: number; version: number;
  approved_by_name: string; approved_at: string | null; approval_note: string; updated_by_name: string;
  updated_at: string; flagged: boolean; precheck?: Precheck | null;
};
type Version = { id: number; version: number; action_display: string; snapshot: { title?: string; text?: string; status?: string }; note: string; changed_by_name: string; created_at: string };
type Form = { kind: string; topic: string; audience: string[]; title: string; text: string; internal_note: string; priority: number; products: string };
type EditMode = { id: number | "new"; mode: "edit" | "propose" | "new" };

const STATUS_COLOR: Record<string, string> = { draft: "#f59e0b", approved: "#10b981", archived: "#94a3b8" };
const inp: React.CSSProperties = { width: "100%", boxSizing: "border-box", border: "1px solid #e2e8f0", borderRadius: 8, padding: "7px 10px", fontSize: 13 };
const sel: React.CSSProperties = { ...inp, width: "auto", minWidth: 120 };
const card: React.CSSProperties = { border: "1px solid #eef2f7", borderRadius: 10, padding: "10px 12px", background: "#fff" };
const chip = (bg: string, color = "#fff"): React.CSSProperties => ({ display: "inline-block", fontSize: 11, padding: "2px 8px", borderRadius: 999, background: bg, color, fontWeight: 600 });

function fmtDate(s: string | null) {
  if (!s) return "";
  try { return new Date(s).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }); } catch { return s; }
}
function errText(e: unknown) {
  const d = (e as { data?: { detail?: string } })?.data;
  if (d && typeof d === "object") return d.detail || JSON.stringify(d);
  return String(e);
}
function toForm(it: Item | null, meta: Meta): Form {
  if (!it) return { kind: "qa", topic: "other", audience: meta.audiences.map((a) => a.value).filter((a) => a !== "funnel_agent"), title: "", text: "", internal_note: "", priority: 100, products: "" };
  return { kind: it.kind, topic: it.topic, audience: [...it.audience], title: it.title, text: it.text, internal_note: it.internal_note, priority: it.priority, products: it.products.join(", ") };
}

function ItemEditor({ meta, form, setForm, mode, onSave, onCancel, busy }: {
  meta: Meta; form: Form; setForm: (f: Form) => void; mode: EditMode["mode"]; onSave: () => void; onCancel: () => void; busy: boolean;
}) {
  const toggleAud = (a: string) => setForm({ ...form, audience: form.audience.includes(a) ? form.audience.filter((x) => x !== a) : [...form.audience, a] });
  return (
    <div style={{ border: "1px solid #bfdbfe", background: "#eff6ff", borderRadius: 10, padding: 12, marginTop: 8 }}>
      {mode === "propose" && <div style={{ fontSize: 12, color: "#1e40af", marginBottom: 6 }}>Правка до затвердженого запису: збережеться як чернетка. Після затвердження власником старий запис автоматично піде в архів.</div>}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
        <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} style={sel}>{meta.kinds.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}</select>
        <select value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} style={sel}>{meta.topics.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}</select>
        <label style={{ fontSize: 12, color: "#475569", display: "flex", alignItems: "center", gap: 4 }}>Пріоритет <input type="number" value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) || 100 })} style={{ ...inp, width: 70 }} /></label>
      </div>
      <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder={form.kind === "qa" ? "Питання клієнта" : "Назва правила / факту"} style={{ ...inp, marginBottom: 8 }} />
      <textarea value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} placeholder="Текст для агента / відповідь клієнту. Ціни не пишіть цифрами: {price:ID товару} або {m2:ID товару}" style={{ ...inp, minHeight: 110, resize: "vertical" }} />
      <div style={{ fontSize: 12, color: "#475569", margin: "8px 0 4px" }}>Для яких агентів:</div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {meta.audiences.map((a) => (
          <label key={a.value} style={{ fontSize: 12.5, display: "flex", alignItems: "center", gap: 4 }}>
            <input type="checkbox" checked={form.audience.includes(a.value)} onChange={() => toggleAud(a.value)} /> {a.label}
          </label>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        <input value={form.products} onChange={(e) => setForm({ ...form, products: e.target.value })} placeholder="ID товарів через кому (агент побачить їхні ціни)" style={{ ...inp, flex: 1, minWidth: 220 }} />
        <input value={form.internal_note} onChange={(e) => setForm({ ...form, internal_note: e.target.value })} placeholder="Внутрішня примітка (агентам не йде)" style={{ ...inp, flex: 2, minWidth: 220 }} />
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button className="btn btn-primary" disabled={busy} onClick={onSave}>{mode === "propose" ? "Надіслати правку" : "Зберегти"}</button>
        <button className="btn" onClick={onCancel}>Скасувати</button>
      </div>
    </div>
  );
}

function ItemCard({ it, meta, selected, onSelect, onAct, onEdit, onPropose, history, onHistory, children }: {
  it: Item; meta: Meta; selected: boolean; onSelect: (v: boolean) => void; onAct: (it: Item, action: string) => void;
  onEdit: (it: Item) => void; onPropose: (it: Item) => void; history: Version[] | undefined; onHistory: (it: Item) => void; children?: React.ReactNode;
}) {
  const audLabel = (a: string) => meta.audiences.find((x) => x.value === a)?.label || a;
  const ev = it.evidence || {};
  const convIds = ev.conversation_ids || (ev.conversation_id ? [ev.conversation_id] : []);
  const editable = meta.can_approve || (meta.can_edit && it.status === "draft");
  return (
    <div style={{ ...card, borderLeft: `4px solid ${STATUS_COLOR[it.status] || "#e2e8f0"}` }}>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
          {meta.can_approve && it.status === "draft" && <input type="checkbox" checked={selected} onChange={(e) => onSelect(e.target.checked)} style={{ marginTop: 3 }} />}
          <div>
            <div style={{ fontWeight: 600, fontSize: 13.5, color: "#0f172a" }}>#{it.id} {it.title}</div>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 4 }}>
              <span style={chip(STATUS_COLOR[it.status] || "#64748b")}>{it.status_display}</span>
              <span style={chip("#e0e7ff", "#3730a3")}>{it.kind_display}</span>
              <span style={chip("#f1f5f9", "#334155")}>{it.topic_display}</span>
              {it.flagged && <span style={chip("#fee2e2", "#b91c1c")}>⚠️ перевірити</span>}
              <CheckChip c={it.precheck} />
              {it.replaces && <span style={chip("#fef3c7", "#92400e")}>правка до #{it.replaces}</span>}
              {it.popularity > 0 && <span style={chip("#e0f2fe", "#0369a1")}>👥 {it.popularity}</span>}
              <span style={{ fontSize: 11, color: "#94a3b8" }}>{it.source_display} · в.{it.version}</span>
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", justifyContent: "flex-end", flexShrink: 0 }}>
          {meta.can_approve && it.status === "draft" && <button className="btn btn-green" style={{ padding: "3px 10px" }} onClick={() => onAct(it, "approve")}>✓ Затвердити</button>}
          {editable && it.status !== "archived" && <button className="btn btn-light" style={{ padding: "3px 10px" }} onClick={() => onEdit(it)}>Редагувати</button>}
          {!meta.can_approve && meta.can_edit && it.status === "approved" && <button className="btn btn-light" style={{ padding: "3px 10px" }} onClick={() => onPropose(it)}>Запропонувати правку</button>}
          {meta.can_approve && it.status !== "archived" && <button className="btn btn-light" style={{ padding: "3px 10px" }} onClick={() => onAct(it, "archive")}>В архів</button>}
          {meta.can_approve && it.status === "archived" && <button className="btn btn-light" style={{ padding: "3px 10px" }} onClick={() => onAct(it, "restore")}>Повернути</button>}
          {meta.can_edit && it.status === "draft" && <button className="btn btn-light" style={{ padding: "3px 10px" }} onClick={() => onAct(it, "delete")}>Видалити</button>}
          <button className="btn btn-light" style={{ padding: "3px 10px" }} onClick={() => onHistory(it)}>Історія</button>
        </div>
      </div>
      <div style={{ marginTop: 6, fontSize: 13, color: "#334155", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{it.text}</div>
      <div style={{ marginTop: 6, fontSize: 11.5, color: "#64748b" }}>Агенти: {it.audience.length ? it.audience.map(audLabel).join(" · ") : <b style={{ color: "#b91c1c" }}>жоден (запис ніхто не читає)</b>}</div>
      {it.product_names.length > 0 && <div style={{ fontSize: 11.5, color: "#64748b" }}>Товари (ціни з каталогу): {it.product_names.join("; ")}</div>}
      {it.internal_note && <div style={{ marginTop: 4, fontSize: 12, color: it.flagged ? "#b91c1c" : "#64748b", whiteSpace: "pre-wrap" }}>{it.internal_note}</div>}
      {it.precheck && it.precheck.label !== "ready" && it.precheck.reason && <div style={{ marginTop: 4, fontSize: 12, color: "#92400e" }}>Попередня перевірка: {it.precheck.reason}</div>}
      {convIds.length > 0 && (
        <div style={{ marginTop: 4, fontSize: 12 }}>Діалоги: {convIds.slice(0, 12).map((c) => <Link key={c} to={`/inbox?c=${c}`} style={{ marginRight: 8 }}>№{c}</Link>)}</div>
      )}
      {it.status === "approved" && <div style={{ fontSize: 11, color: "#15803d", marginTop: 4 }}>Затверджено: {it.approved_by_name || "—"} {fmtDate(it.approved_at)} {it.approval_note && `· ${it.approval_note}`}</div>}
      {children}
      {history && (
        <div style={{ marginTop: 8, borderTop: "1px dashed #e2e8f0", paddingTop: 6 }}>
          {history.length === 0 && <div style={{ fontSize: 12, color: "#94a3b8" }}>Історії ще немає</div>}
          {history.map((v) => (
            <div key={v.id} style={{ fontSize: 12, color: "#475569", marginBottom: 4 }}>
              <b>в.{v.version} · {v.action_display}</b> — {v.changed_by_name} {fmtDate(v.created_at)} {v.note && `· ${v.note}`}
              {v.snapshot?.text && <div style={{ color: "#94a3b8", whiteSpace: "pre-wrap" }}>{String(v.snapshot.text).slice(0, 300)}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Cards({ meta, reloadMeta }: { meta: Meta; reloadMeta: () => void }) {
  const [f, setF] = useState({ status: "draft", kind: "", topic: "", audience: "", search: "", flagged: false, source: "", label: "" });
  const [rows, setRows] = useState<Item[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [edit, setEdit] = useState<EditMode | null>(null);
  const [form, setForm] = useState<Form>(() => toForm(null, meta));
  const [hist, setHist] = useState<Record<number, Version[]>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (pg: number) => {
    setLoading(true);
    const qs = new URLSearchParams({ page: String(pg), page_size: "30" });
    (["status", "kind", "topic", "audience", "search", "source", "label"] as const).forEach((k) => { if (f[k]) qs.set(k, f[k]); });
    if (f.flagged) qs.set("flagged", "1");
    try {
      const d = await api.get<{ results: Item[]; count: number }>(`/api/knowledge/items/?${qs.toString()}`);
      setRows((rs) => (pg === 1 ? d.results : [...rs, ...d.results])); setCount(d.count); setPage(pg);
    } catch (e) { window.alert(errText(e)); } finally { setLoading(false); }
  }, [f]);
  useEffect(() => { const id = setTimeout(() => { setSelected([]); load(1); }, 300); return () => clearTimeout(id); }, [load]);

  const replaceRow = (it: Item) => setRows((rs) => rs.map((r) => (r.id === it.id ? it : r)));
  async function act(it: Item, action: string) {
    try {
      if (action === "delete") {
        if (!window.confirm("Видалити чернетку?")) return;
        await api.del(`/api/knowledge/items/${it.id}/`); setRows((rs) => rs.filter((r) => r.id !== it.id)); setCount((c) => c - 1);
      } else {
        if (action === "archive" && !window.confirm("Перенести в архів? Агенти перестануть це читати.")) return;
        replaceRow(await api.post<Item>(`/api/knowledge/items/${it.id}/${action}/`, {}));
      }
      reloadMeta();
    } catch (e) { window.alert(errText(e)); }
  }
  async function history(it: Item) {
    if (hist[it.id]) { setHist((h) => { const n = { ...h }; delete n[it.id]; return n; }); return; }
    try { const v = await api.get<Version[]>(`/api/knowledge/items/${it.id}/history/`); setHist((h) => ({ ...h, [it.id]: v })); } catch (e) { window.alert(errText(e)); }
  }
  function startEdit(it: Item | null, mode: EditMode["mode"]) { setForm(toForm(it, meta)); setEdit({ id: it ? it.id : "new", mode }); }
  async function save() {
    if (!edit) return;
    const body = { kind: form.kind, topic: form.topic, audience: form.audience, title: form.title, text: form.text, internal_note: form.internal_note, priority: form.priority,
      products: form.products.split(/[\s,;]+/).map((x) => parseInt(x, 10)).filter((n) => !Number.isNaN(n)) };
    setBusy(true);
    try {
      if (edit.mode === "new") { const it = await api.post<Item>(`/api/knowledge/items/`, body); setRows((rs) => [it, ...rs]); setCount((c) => c + 1); }
      else if (edit.mode === "propose") { const it = await api.post<Item>(`/api/knowledge/items/${edit.id}/propose/`, body); setRows((rs) => [it, ...rs]); window.alert("Правку надіслано на затвердження (чернетка #" + it.id + ")"); }
      else { replaceRow(await api.patch<Item>(`/api/knowledge/items/${edit.id}/`, body)); }
      setEdit(null); reloadMeta();
    } catch (e) { window.alert(errText(e)); } finally { setBusy(false); }
  }
  async function bulkApprove() {
    if (!selected.length || !window.confirm(`Затвердити ${selected.length} записів? Агенти почнуть їх читати.`)) return;
    try { await api.post(`/api/knowledge/items/bulk/`, { ids: selected, action: "approve" }); setSelected([]); load(1); reloadMeta(); } catch (e) { window.alert(errText(e)); }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", margin: "10px 0" }}>
        <input value={f.search} onChange={(e) => setF({ ...f, search: e.target.value })} placeholder="Пошук у питанні, тексті, примітці або №" style={{ ...inp, flex: 1, minWidth: 200 }} />
        <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} style={sel}>
          <option value="">Усі статуси</option>{meta.statuses.map((s) => <option key={s.value} value={s.value}>{s.label} ({meta.counts[s.value] || 0})</option>)}
        </select>
        <select value={f.topic} onChange={(e) => setF({ ...f, topic: e.target.value })} style={sel}><option value="">Усі теми</option>{meta.topics.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
        <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} style={sel}><option value="">Усі типи</option>{meta.kinds.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
        <select value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })} style={sel}><option value="">Усі агенти</option>{meta.audiences.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
        <select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} style={sel}><option value="">Усі джерела</option>{meta.sources.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
        <select value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} style={sel}><option value="">Будь-яка мітка перевірки</option>{LABEL_FILTERS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
        <label style={{ fontSize: 12.5, display: "flex", alignItems: "center", gap: 4 }}><input type="checkbox" checked={f.flagged} onChange={(e) => setF({ ...f, flagged: e.target.checked })} /> ⚠️ лише «перевірити» ({meta.flagged_drafts})</label>
        {meta.can_edit && <button className="btn btn-primary" onClick={() => startEdit(null, "new")}>+ Додати</button>}
        {meta.can_approve && selected.length > 0 && <button className="btn btn-green" onClick={bulkApprove}>✓ Затвердити вибрані ({selected.length})</button>}
      </div>
      {edit?.id === "new" && <ItemEditor meta={meta} form={form} setForm={setForm} mode="new" onSave={save} onCancel={() => setEdit(null)} busy={busy} />}
      <div style={{ fontSize: 12, color: "#64748b", margin: "8px 0" }}>Знайдено: <b>{count}</b>{loading && " · завантаження…"}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rows.map((it) => (
          <ItemCard key={it.id} it={it} meta={meta} selected={selected.includes(it.id)}
            onSelect={(v) => setSelected((s) => (v ? [...s, it.id] : s.filter((x) => x !== it.id)))}
            onAct={act} onEdit={(x) => startEdit(x, "edit")} onPropose={(x) => startEdit(x, "propose")} history={hist[it.id]} onHistory={history}>
            {edit && edit.id === it.id && <ItemEditor meta={meta} form={form} setForm={setForm} mode={edit.mode} onSave={save} onCancel={() => setEdit(null)} busy={busy} />}
          </ItemCard>
        ))}
      </div>
      {rows.length < count && <button className="btn" style={{ marginTop: 10 }} disabled={loading} onClick={() => load(page + 1)}>Показати ще</button>}
    </div>
  );
}

function Preview({ meta }: { meta: Meta }) {
  const [agent, setAgent] = useState("rop_hint");
  const [q, setQ] = useState("Скільки коштує Галатея і яка передоплата на накладений платіж?");
  const [res, setRes] = useState<{ text: string; chars: number } | null>(null);
  async function show() {
    try { setRes(await api.get<{ text: string; chars: number }>(`/api/knowledge/preview/?agent=${agent}&q=${encodeURIComponent(q)}`)); } catch (e) { window.alert(errText(e)); }
  }
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ fontSize: 12.5, color: "#475569", marginBottom: 8 }}>Точно той блок знань, який агент отримає зараз на таке повідомлення клієнта (ІІ не викликається, $0).</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <select value={agent} onChange={(e) => setAgent(e.target.value)} style={sel}>{meta.audiences.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}</select>
        <input value={q} onChange={(e) => setQ(e.target.value)} style={{ ...inp, flex: 1, minWidth: 240 }} />
        <button className="btn btn-primary" onClick={show}>Показати</button>
      </div>
      {res && (
        <div style={{ ...card, marginTop: 10 }}>
          <div style={{ fontSize: 11.5, color: "#94a3b8", marginBottom: 6 }}>{res.chars} символів ≈ {Math.round(res.chars / 3)} токенів</div>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12.5, margin: 0, fontFamily: "inherit", color: "#1e293b" }}>{res.text || "(порожньо — агент працює на старому вбудованому тексті)"}</pre>
        </div>
      )}
    </div>
  );
}

function Team({ meta, reloadMeta }: { meta: Meta; reloadMeta: () => void }) {
  const [s, setS] = useState<KSettings>(meta.settings);
  const [saving, setSaving] = useState(false);
  async function save() {
    setSaving(true);
    try { setS(await api.patch<KSettings>(`/api/knowledge/settings/`, { reviewer_enabled: s.reviewer_enabled, reviewer_sample: s.reviewer_sample, reviewer_model: s.reviewer_model })); reloadMeta(); }
    catch (e) { window.alert(errText(e)); } finally { setSaving(false); }
  }
  const th: React.CSSProperties = { textAlign: "left", padding: "6px 8px", fontSize: 12, color: "#475569", borderBottom: "1px solid #e2e8f0" };
  const td: React.CSSProperties = { padding: "6px 8px", fontSize: 12.5, verticalAlign: "top", borderBottom: "1px solid #f1f5f9" };
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
          <thead><tr><th style={th}>Агент</th><th style={th}>Що робить</th><th style={th}>Що читає з бази</th><th style={th}>Хто перевіряє</th></tr></thead>
          <tbody>{meta.roles.map((r) => <tr key={r.agent}><td style={{ ...td, fontWeight: 600 }}>{r.name}</td><td style={td}>{r.does}</td><td style={td}>{r.reads}</td><td style={td}>{r.checked_by}</td></tr>)}</tbody>
        </table>
      </div>
      <WebchatCard s={s} isOwner={meta.is_owner} onSaved={(ns) => { setS({ ...s, ...ns }); reloadMeta(); }} />
      <div style={{ ...card, marginTop: 12 }}>
        <b>Контролер закритих чатів — лише за запуском.</b> Розкладу немає: перевірка з ІІ запускається тільки кнопкою
        «Запустити перевірку» у вкладці «Контролер» (власник), з оцінкою вартості до запуску. Знахідки падають сюди
        чернетками з посиланням на діалог — затверджуєте ви. Пропозицій зараз: <b>{meta.reviewer_drafts}</b>.
      </div>
    </div>
  );
}

export default function KnowledgeBase() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [err, setErr] = useState("");
  const [sub, setSub] = useState<"cards" | "preview" | "precheck" | "controller" | "publish" | "team">("cards");
  const reloadMeta = useCallback(() => { api.get<Meta>("/api/knowledge/meta/").then(setMeta).catch((e) => setErr(errText(e))); }, []);
  useEffect(() => { reloadMeta(); }, [reloadMeta]);
  if (err && !meta) return <div style={{ maxWidth: 1100, margin: "12px auto", color: "#b91c1c", fontSize: 13 }}>Немає доступу до бази знань: {err}</div>;
  if (!meta) return <div style={{ maxWidth: 1100, margin: "12px auto", color: "#94a3b8", fontSize: 13 }}>Завантаження…</div>;
  const subBtn = (k: typeof sub, label: string) => (
    <button key={k} onClick={() => setSub(k)} className={sub === k ? "btn btn-primary" : "btn btn-light"} style={{ padding: "4px 12px" }}>{label}</button>
  );
  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 4px" }}>
      <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, padding: "8px 12px", fontSize: 12.5, color: "#14532d", margin: "10px 0" }}>
        Одна база для всіх ІІ-агентів CRM. Агенти читають <b>лише «Затверджено»</b>. Нове (вручну, з імпорту, від рецензента) заходить чернеткою —
        затверджує власник. Ціни не пишіть цифрами: <code>{"{price:ID}"}</code> або <code>{"{m2:ID}"}</code> — агент отримає актуальну ціну з каталогу.
        Затверджено: <b>{meta.counts.approved || 0}</b> · чернеток: <b>{meta.counts.draft || 0}</b> · архів: <b>{meta.counts.archived || 0}</b>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {subBtn("cards", "Записи")}{subBtn("preview", "Тестовий чат")}{subBtn("precheck", "Перевірка чернеток")}
        {subBtn("controller", "Контролер")}{subBtn("publish", "Публікація в Юлю")}{subBtn("team", "Команда агентів")}
      </div>
      {sub === "cards" && <Cards meta={meta} reloadMeta={reloadMeta} />}
      {sub === "preview" && (
        <div>
          <KnowledgeTestChat topics={meta.topics} />
          <details style={{ marginTop: 14 }}>
            <summary style={{ cursor: "pointer", fontSize: 13, color: "#475569" }}>Що бачить агент — точний блок знань без виклику ІІ ($0)</summary>
            <Preview meta={meta} />
          </details>
        </div>
      )}
      {sub === "precheck" && <PrecheckPanel topics={meta.topics} canApprove={meta.can_approve} />}
      {sub === "controller" && <ControllerPanel />}
      {sub === "publish" && <PublishPanel isOwner={meta.is_owner} />}
      {sub === "team" && <Team meta={meta} reloadMeta={reloadMeta} />}
    </div>
  );
}
