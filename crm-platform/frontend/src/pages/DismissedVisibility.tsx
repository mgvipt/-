/* Звільнені: де їх показувати (staffvis 15.09.2026).
   Для кожного звільненого і кожного розділу — «Авто» / «Показувати» / «Приховати».
   Активних співробітників ці налаштування не стосуються. Бекенд — /api/users/visibility/ (apps/accounts/visibility.py). */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Icon } from "../Icon";

type Choice = boolean | null;
type ChoiceKey = "auto" | "on" | "off";
interface VisEntity { key: string; label: string; where: string; auto: string; }
interface VisPerson {
  id: number; full_name: string; dismissed_at: string | null; from_bitrix: boolean;
  settings: Record<string, Choice>; now: Record<string, boolean>;
  deals: number; active_schemes: number; approved_runs: number; changed_by: string; changed_at: string | null;
}
interface VisData { entities: VisEntity[]; people: VisPerson[]; month: string; }
export interface DismissedRow { id: number; full_name: string; position?: string; department_name?: string; dismissed_at?: string | null; }

const CHOICE_STYLE: Record<ChoiceKey, React.CSSProperties> = {
  auto: { background: "#f8fafc", color: "#475569", borderColor: "#e2e8f0" },
  on: { background: "#f0fdf4", color: "#15803d", borderColor: "#bbf7d0" },
  off: { background: "#fef2f2", color: "#b91c1c", borderColor: "#fecaca" },
};
const keyOf = (v: Choice | undefined): ChoiceKey => (v === true ? "on" : v === false ? "off" : "auto");
const valueOf = (k: string): Choice => (k === "on" ? true : k === "off" ? false : null);
const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleDateString("uk-UA") : "");
const fmtDateTime = (s?: string | null) => (s ? new Date(s).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "");
const smallBtn: React.CSSProperties = { fontSize: 11.5, padding: "3px 9px", display: "inline-flex", alignItems: "center", gap: 4, whiteSpace: "nowrap" };

export default function DismissedVisibility({ emps, onReturn, onOpen }: { emps: DismissedRow[]; onReturn: (id: number) => void; onOpen: (id: number) => void }) {
  const [data, setData] = useState<VisData | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [help, setHelp] = useState(false);

  function load() {
    api.get<VisData>("/api/users/visibility/")
      .then((d) => { setData(d); setErr(""); })
      .catch((e: any) => setErr(e?.data?.detail || "Не вдалося завантажити налаштування видимості"));
  }
  useEffect(() => { load(); }, [emps.length]);

  const byId = useMemo(() => {
    const m: Record<number, VisPerson> = {};
    (data?.people || []).forEach((p) => { m[p.id] = p; });
    return m;
  }, [data]);

  async function save(id: number, body: Record<string, unknown>) {
    setBusy(id);
    try {
      const p = await api.post<VisPerson>("/api/users/visibility/", { user_id: id, ...body });
      setData((d) => (d ? { ...d, people: d.people.some((x) => x.id === id) ? d.people.map((x) => (x.id === id ? p : x)) : [...d.people, p] } : d));
      setErr("");
    } catch (e: any) {
      setErr(e?.data?.detail || "Не вдалося зберегти");
    } finally {
      setBusy(null);
    }
  }

  const ents = data?.entities || [];
  const needle = q.trim().toLowerCase();
  const rows = emps.filter((e) => !needle || (e.full_name || "").toLowerCase().includes(needle));
  const shownSomewhere = emps.filter((e) => { const p = byId[e.id]; return !!p && ents.some((en) => p.now[en.key]); }).length;

  return (
    <div>
      <div className="note" style={{ marginBottom: 10 }}>
        <Icon n="eye" size={14} /> <b>Де показувати звільнених.</b> Для кожної людини і кожного розділу оберіть: <b>Авто</b>, <b>Показувати</b> або <b>Приховати</b>. Активних співробітників це не стосується.{" "}
        <a onClick={() => setHelp((v) => !v)} style={{ cursor: "pointer", textDecoration: "underline" }}>{help ? "сховати пояснення" : "як це працює"}</a>
        {help && (
          <div style={{ marginTop: 8, fontSize: 12.5, lineHeight: 1.55 }}>
            <div><b>Авто</b> — людина видна лише у звітах за ті місяці, коли ще працювала (до дати звільнення). Якщо дата звільнення невідома (старі акаунти з Бітрикса) — прихована. У точці беззбитковості «Авто» = не рахується: це план на майбутнє.</div>
            <div><b>Показувати</b> — видно в цьому розділі за будь-який місяць, як було до цього налаштування.</div>
            <div><b>Приховати</b> — не видно в цьому розділі і не входить у його суми по людях.</div>
            <div>Затверджені відомості ЗП, привʼязані виплати й журнал грошей не ховаються і не змінюються — це історія.</div>
            <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>{ents.map((en) => <li key={en.key}><b>{en.label}</b> — {en.where}</li>)}</ul>
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, border: "1px solid #e2e8f0", borderRadius: 8, padding: "3px 8px", background: "#fff" }}>
          <Icon n="search" size={14} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Пошук за імʼям" style={{ border: 0, outline: "none", fontSize: 13, width: 180 }} />
        </label>
        <span className="muted" style={{ fontSize: 12 }}>Звільнених: {emps.length} · зараз десь показуються: {shownSomewhere}</span>
        {err && <span style={{ color: "#dc2626", fontSize: 12.5 }}>{err}</span>}
      </div>
      {!data && !err && <div className="muted" style={{ fontSize: 12.5, marginBottom: 8 }}>Завантаження налаштувань…</div>}

      <div className="tablewrap" style={{ maxHeight: "calc(100vh - 330px)", overflow: "auto" }}><table>
        <thead><tr>
          <th>Співробітник</th>
          {ents.map((en) => <th key={en.key} title={en.where} style={{ minWidth: 124, whiteSpace: "normal", fontSize: 11.5 }}>{en.label}</th>)}
          <th>Усюди</th>
        </tr></thead>
        <tbody>{rows.map((e) => {
          const p = byId[e.id];
          const locked = busy === e.id || !p;
          const dismissed = e.dismissed_at || p?.dismissed_at || null;
          return <tr key={e.id}>
            <td style={{ minWidth: 210 }}>
              <div onClick={() => onOpen(e.id)} title="Відкрити картку співробітника" style={{ fontWeight: 600, cursor: "pointer" }}>{e.full_name}</div>
              {(e.position || e.department_name) && <div className="muted" style={{ fontSize: 11.5 }}>{[e.position, e.department_name].filter(Boolean).join(" · ")}</div>}
              <div style={{ fontSize: 11.5, color: dismissed ? "#dc2626" : "#94a3b8" }}>{dismissed ? `звільнено ${fmtDate(dismissed)}` : (p?.from_bitrix ? "дата звільнення невідома (акаунт з Бітрикса)" : "дата звільнення невідома")}</div>
              {p && p.active_schemes > 0 && (
                <div style={{ fontSize: 11.5, color: "#b45309", display: "flex", gap: 4, alignItems: "center" }}>
                  <Icon n="warn" size={12} /> є діюча ставка — у ФОТ рахується лише при «Показувати» в точці беззбитковості
                </div>
              )}
              {p && (p.deals > 0 || p.approved_runs > 0) && (
                <div className="muted" style={{ fontSize: 11 }}>
                  {[p.deals > 0 ? `угод: ${p.deals}` : "", p.approved_runs > 0 ? `затверджених відомостей ЗП: ${p.approved_runs}` : ""].filter(Boolean).join(" · ")}
                </div>
              )}
              {p && p.changed_by && <div className="muted" style={{ fontSize: 10.5 }}>змінено: {p.changed_by} {fmtDateTime(p.changed_at)}</div>}
            </td>
            {ents.map((en) => {
              const k = keyOf(p?.settings[en.key]);
              const nowTxt = p ? (p.now[en.key] ? "зараз видно" : "зараз приховано") : "";
              return <td key={en.key}>
                <select value={k} disabled={locked} title={`${en.label}: ${en.where}. Авто — ${en.auto}.`}
                  onChange={(ev) => save(e.id, { set: { [en.key]: valueOf(ev.target.value) } })}
                  style={{ borderWidth: 1, borderStyle: "solid", borderRadius: 7, padding: "3px 6px", fontSize: 12, width: "100%", ...CHOICE_STYLE[k] }}>
                  <option value="auto">{nowTxt ? `Авто · ${nowTxt}` : "Авто"}</option>
                  <option value="on">Показувати</option>
                  <option value="off">Приховати</option>
                </select>
              </td>;
            })}
            <td>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
                <button className="btn" disabled={locked} onClick={() => save(e.id, { all: true })} style={smallBtn} title="Показувати в усіх розділах"><Icon n="eye" size={13} /> Усюди увімкнути</button>
                <button className="btn" disabled={locked} onClick={() => save(e.id, { all: false })} style={smallBtn} title="Приховати з усіх розділів"><Icon n="eye-off" size={13} /> Усюди вимкнути</button>
                <button className="btn" disabled={locked} onClick={() => save(e.id, { all: null })} style={smallBtn} title="Повернути всі розділи на «Авто»"><Icon n="refresh" size={13} /> Усе на Авто</button>
                <button className="btn" onClick={() => onReturn(e.id)} style={{ ...smallBtn, color: "#16a34a" }} title="Повернути людину в активні співробітники"><Icon n="user" size={13} /> Повернути в активні</button>
              </div>
            </td>
          </tr>;
        })}</tbody>
      </table></div>
      {rows.length === 0 && <div className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>{emps.length ? "Нікого не знайдено" : "Звільнених немає"}</div>}
    </div>
  );
}
