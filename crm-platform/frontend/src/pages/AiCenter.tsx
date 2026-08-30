/* AI ЦЕНТР — единый раздел про ИИ: Витрати · База знань · Невідомі питання · Налаштування.
   Витрати и Налаштування — существующие компоненты БЕЗ изменений (обёрнуты во вкладки). */
import { useEffect, useState, useCallback } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
import AiCosts from "./AiCosts";
import SettingsAgent from "./SettingsAgent";

type KbEntry = { id: number; question: string; answer: string; specific_rules: string; source: string; client_chat_count: number; tags: string; enabled: boolean };
type KbQ = { id: number; question: string; status: string; source: string; times_asked: number; answer_preview: string };

const wrap: React.CSSProperties = { maxWidth: 1100, margin: "0 auto", padding: "0 4px" };
const inp: React.CSSProperties = { width: "100%", boxSizing: "border-box", border: "1px solid #e2e8f0", borderRadius: 8, padding: "8px 10px", fontSize: 13 };

function KbBase() {
  const { t } = useLang();
  const [rows, setRows] = useState<KbEntry[]>([]);
  const [count, setCount] = useState(0);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [edit, setEdit] = useState<Record<number, string>>({});
  const [adding, setAdding] = useState(false);
  const [nq, setNq] = useState(""); const [na, setNa] = useState("");

  const load = useCallback(async (search: string) => {
    setLoading(true);
    try {
      const d = await api.get<any>(`/api/kb-entries/?page_size=50${search ? "&search=" + encodeURIComponent(search) : ""}`);
      setRows(d.results || d); setCount(d.count ?? (d.results || d).length);
    } catch { /* */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { const id = setTimeout(() => load(q), 300); return () => clearTimeout(id); }, [q, load]);

  async function save(id: number) {
    const answer = edit[id]; if (answer === undefined) return;
    try { await api.patch(`/api/kb-entries/${id}/`, { answer }); setRows((rs) => rs.map((r) => r.id === id ? { ...r, answer } : r)); setEdit((e) => { const n = { ...e }; delete n[id]; return n; }); }
    catch { window.alert(t("Не удалось сохранить", "Не вдалося зберегти")); }
  }
  async function del(id: number) {
    if (!window.confirm(t("Удалить запись из базы?", "Видалити запис з бази?"))) return;
    try { await api.del(`/api/kb-entries/${id}/`); setRows((rs) => rs.filter((r) => r.id !== id)); setCount((c) => c - 1); } catch { /* */ }
  }
  async function add() {
    if (!nq.trim() || !na.trim()) { window.alert(t("Впишите вопрос и ответ", "Впишіть питання і відповідь")); return; }
    try { const r = await api.post<KbEntry>(`/api/kb-entries/`, { question: nq.trim(), answer: na.trim() }); setRows((rs) => [r, ...rs]); setCount((c) => c + 1); setNq(""); setNa(""); setAdding(false); } catch { window.alert(t("Не удалось", "Не вдалося")); }
  }

  return (
    <div style={wrap}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "10px 0" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Поиск по вопросу или ответу…", "Пошук за питанням або відповіддю…")} style={{ ...inp, flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setAdding((v) => !v)} style={{ whiteSpace: "nowrap" }}><Icon n="plus" size={14} /> {t("Добавить", "Додати")}</button>
      </div>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>{t("Всего в базе", "Всього в базі")}: <b>{count}</b> {q && `· ${t("найдено", "знайдено")}: ${rows.length}`}</div>
      {adding && (
        <div style={{ border: "1px solid #bfdbfe", background: "#eff6ff", borderRadius: 10, padding: 12, marginBottom: 12 }}>
          <input value={nq} onChange={(e) => setNq(e.target.value)} placeholder={t("Вопрос клиента", "Питання клієнта")} style={{ ...inp, marginBottom: 8 }} />
          <textarea value={na} onChange={(e) => setNa(e.target.value)} placeholder={t("Ответ, который даст ИИ", "Відповідь, яку дасть ІІ")} style={{ ...inp, minHeight: 80, resize: "vertical" }} />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}><button className="btn btn-primary" onClick={add}>{t("Сохранить", "Зберегти")}</button><button className="btn" onClick={() => setAdding(false)}>{t("Отмена", "Скасувати")}</button></div>
        </div>
      )}
      {loading && <div style={{ color: "#94a3b8", fontSize: 13 }}>{t("Загрузка…", "Завантаження…")}</div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rows.map((r) => (
          <div key={r.id} style={{ border: "1px solid #eef2f7", borderRadius: 10, padding: "10px 12px", background: "#fff" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
              <div style={{ fontWeight: 600, fontSize: 13.5, color: "#0f172a" }}>{r.question}</div>
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
                {r.client_chat_count > 0 && <span title={t("Как часто спрашивают", "Як часто питають")} style={{ fontSize: 11, color: "#0369a1", background: "#e0f2fe", borderRadius: 10, padding: "1px 7px" }}>👥 {r.client_chat_count}</span>}
                <span style={{ fontSize: 10, color: "#94a3b8" }}>{r.source}</span>
                <button className="btn" style={{ padding: "2px 6px" }} title={t("Удалить", "Видалити")} onClick={() => del(r.id)}><Icon n="trash" size={13} /></button>
              </div>
            </div>
            {edit[r.id] !== undefined ? (
              <div style={{ marginTop: 6 }}>
                <textarea value={edit[r.id]} onChange={(e) => setEdit((ed) => ({ ...ed, [r.id]: e.target.value }))} style={{ ...inp, minHeight: 90, resize: "vertical" }} />
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}><button className="btn btn-primary" style={{ padding: "4px 12px" }} onClick={() => save(r.id)}>{t("Сохранить", "Зберегти")}</button><button className="btn" style={{ padding: "4px 12px" }} onClick={() => setEdit((e) => { const n = { ...e }; delete n[r.id]; return n; })}>{t("Отмена", "Скасувати")}</button></div>
              </div>
            ) : (
              <div onClick={() => setEdit((e) => ({ ...e, [r.id]: r.answer }))} title={t("Нажмите чтобы редактировать", "Натисніть щоб редагувати")} style={{ marginTop: 6, fontSize: 13, color: "#334155", whiteSpace: "pre-wrap", cursor: "text", lineHeight: 1.45 }}>{r.answer || <span style={{ color: "#cbd5e1" }}>{t("(пусто — нажмите чтобы добавить ответ)", "(порожньо — натисніть щоб додати відповідь)")}</span>}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function KbQuestions() {
  const { t } = useLang();
  const [rows, setRows] = useState<KbQ[]>([]);
  const [count, setCount] = useState(0);
  const [q, setQ] = useState("");
  const [st, setSt] = useState("new");
  const [ans, setAns] = useState<Record<number, string>>({});

  const load = useCallback(async (search: string, status: string) => {
    try {
      const d = await api.get<any>(`/api/kb-questions/?page_size=50&status=${status}${search ? "&search=" + encodeURIComponent(search) : ""}`);
      setRows(d.results || d); setCount(d.count ?? (d.results || d).length);
    } catch { /* */ }
  }, []);
  useEffect(() => { const id = setTimeout(() => load(q, st), 300); return () => clearTimeout(id); }, [q, st, load]);

  async function toKb(id: number) {
    const answer = (ans[id] || "").trim(); if (!answer) { window.alert(t("Впишите ответ", "Впишіть відповідь")); return; }
    try { await api.post(`/api/kb-questions/${id}/to_kb/`, { answer }); setRows((rs) => rs.filter((r) => r.id !== id)); setCount((c) => c - 1); }
    catch { window.alert(t("Не удалось", "Не вдалося")); }
  }
  async function ignore(id: number) {
    try { await api.post(`/api/kb-questions/${id}/ignore/`, {}); setRows((rs) => rs.filter((r) => r.id !== id)); setCount((c) => c - 1); } catch { /* */ }
  }

  return (
    <div style={wrap}>
      <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "8px 12px", fontSize: 12.5, color: "#78350f", margin: "10px 0" }}>
        {t("Это вопросы клиентов, на которые ИИ не знал ответа. Впишите ответ — он попадёт в базу знаний, и дальше ИИ будет отвечать сам.", "Це питання клієнтів, на які ІІ не знав відповіді. Впишіть відповідь — вона потрапить у базу знань, і далі ІІ відповідатиме сам.")}
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Поиск по вопросу…", "Пошук за питанням…")} style={{ ...inp, flex: 1 }} />
        <select value={st} onChange={(e) => setSt(e.target.value)} style={{ ...inp, width: "auto" }}>
          <option value="new">{t("Новые", "Нові")}</option>
          <option value="answered">{t("Добавлены в базу", "Додані в базу")}</option>
          <option value="ignored">{t("Игнор", "Ігнор")}</option>
        </select>
      </div>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>{t("Всего", "Всього")}: <b>{count}</b></div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rows.map((r) => (
          <div key={r.id} style={{ border: "1px solid #eef2f7", borderRadius: 10, padding: "10px 12px", background: "#fff" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <div style={{ fontWeight: 600, fontSize: 13.5, color: "#0f172a" }}>{r.question}</div>
              {r.times_asked > 1 && <span style={{ fontSize: 11, color: "#0369a1", background: "#e0f2fe", borderRadius: 10, padding: "1px 7px", flexShrink: 0 }}>×{r.times_asked}</span>}
            </div>
            {st === "new" && (
              <div style={{ marginTop: 6 }}>
                <textarea value={ans[r.id] || ""} onChange={(e) => setAns((a) => ({ ...a, [r.id]: e.target.value }))} placeholder={t("Ответ, который даст ИИ…", "Відповідь, яку дасть ІІ…")} style={{ ...inp, minHeight: 70, resize: "vertical" }} />
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                  <button className="btn btn-primary" style={{ padding: "4px 12px" }} onClick={() => toKb(r.id)}><Icon n="plus" size={13} /> {t("В базу знаний", "В базу знань")}</button>
                  <button className="btn" style={{ padding: "4px 12px" }} onClick={() => ignore(r.id)}>{t("Игнор", "Ігнор")}</button>
                </div>
              </div>
            )}
            {st === "answered" && r.answer_preview && <div style={{ marginTop: 6, fontSize: 12.5, color: "#15803d" }}>✅ {r.answer_preview}…</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

const TABS: [string, string, string][] = [
  ["costs", "Витрати", "Витрати"],
  ["kb", "База знань", "База знань"],
  ["q", "Невідомі питання", "Невідомі питання"],
  ["settings", "Налаштування", "Налаштування"],
];

export default function AiCenter() {
  const { t } = useLang();
  const [tab, setTab] = useState<string>(() => localStorage.getItem("aiCenterTab") || "costs");
  useEffect(() => { localStorage.setItem("aiCenterTab", tab); }, [tab]);
  return (
    <div style={{ padding: "12px 8px" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto 6px" }}>
        <h2 style={{ margin: "0 0 10px", fontSize: 20, fontWeight: 800, color: "#0f172a" }}>🧠 AI ЦЕНТР</h2>
        <div style={{ display: "flex", gap: 6, borderBottom: "1px solid #e2e8f0", flexWrap: "wrap" }}>
          {TABS.map(([k, ru, ua]) => (
            <button key={k} onClick={() => setTab(k)} style={{ border: "none", background: "none", cursor: "pointer", padding: "8px 14px", fontSize: 13.5, fontWeight: tab === k ? 700 : 500, color: tab === k ? "var(--brand)" : "#64748b", borderBottom: "2px solid " + (tab === k ? "var(--brand)" : "transparent"), marginBottom: -1 }}>{t(ru, ua)}</button>
          ))}
        </div>
      </div>
      {tab === "costs" && <AiCosts />}
      {tab === "kb" && <KbBase />}
      {tab === "q" && <KbQuestions />}
      {tab === "settings" && <SettingsAgent />}
    </div>
  );
}
