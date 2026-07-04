import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Funnel } from "../api";
import Board from "./Board";
import ListView from "../ListView";
import FunnelEditor from "./FunnelEditor";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

/* ── Розумний фільтр сделок: пишеш — шукає по назві; клік — панель фільтрів ── */
function SmartFilter({ funnel, users, onQuery }: { funnel: Funnel; users: { id: number; name: string }[]; onQuery: (q: string, stages: number[]) => void }) {
  const { t } = useLang();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [cliQ, setCliQ] = useState("");
  const [cliOpts, setCliOpts] = useState<any[]>([]);
  const [cli, setCli] = useState<any>(null);
  const [phoneQ, setPhoneQ] = useState("");
  const [phoneOpts, setPhoneOpts] = useState<any[]>([]);
  const [dealId, setDealId] = useState("");
  const [selStages, setSelStages] = useState<number[]>([]);
  const [owner, setOwner] = useState("");
  const [datePreset, setDatePreset] = useState("");
  const [dFrom, setDFrom] = useState("");
  const [dTo, setDTo] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);

  // клік поза панеллю — закрити
  useEffect(() => {
    const h = (e: MouseEvent) => { if (boxRef.current && !boxRef.current.contains(e.target as any)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  // автокомпліт клієнта за іменем/прізвищем
  useEffect(() => {
    if (!cliQ.trim() || cli) { setCliOpts([]); return; }
    const tm = setTimeout(() => api.get<any>(`/api/contacts/?search=${encodeURIComponent(cliQ.trim())}&page_size=8`)
      .then((d) => setCliOpts(d.results || d)).catch(() => setCliOpts([])), 300);
    return () => clearTimeout(tm);
  }, [cliQ, cli]);

  // пошук клієнта за телефоном (цифри)
  useEffect(() => {
    const digits = phoneQ.replace(/\D/g, "");
    if (digits.length < 3 || cli) { setPhoneOpts([]); return; }
    const tm = setTimeout(() => api.get<any>(`/api/contacts/?search=${digits}&page_size=8`)
      .then((d) => setPhoneOpts((d.results || d).filter((c: any) => (c.phone || "").replace(/\D/g, "").includes(digits)))).catch(() => setPhoneOpts([])), 300);
    return () => clearTimeout(tm);
  }, [phoneQ, cli]);

  function dateRange(p: string): [string, string] {
    const n = new Date();
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    if (p === "today") return [iso(n), iso(n)];
    if (p === "yesterday") { const y = new Date(n.getTime() - 864e5); return [iso(y), iso(y)]; }
    if (p === "month") return [iso(new Date(n.getFullYear(), n.getMonth(), 1)), iso(n)];
    if (p === "prevmonth") return [iso(new Date(n.getFullYear(), n.getMonth() - 1, 1)), iso(new Date(n.getFullYear(), n.getMonth(), 0))];
    if (p === "year") return [iso(new Date(n.getFullYear(), 0, 1)), iso(n)];
    return [dFrom, dTo];
  }

  function build(txt: string, stages: number[], extra?: any) {
    const e = { cli, dealId, owner, datePreset, dFrom, dTo, ...(extra || {}) };
    let q = "";
    if (txt.trim()) q += `&search=${encodeURIComponent(txt.trim())}`;
    if (e.cli) q += `&contact=${e.cli.id}`;
    if (e.dealId.trim()) q += `&deal_id=${encodeURIComponent(e.dealId.trim().replace("#", ""))}`;
    if (e.owner) q += `&owner=${e.owner}`;
    if (stages.length) q += `&stages=${stages.join(",")}`;
    if (e.datePreset) {
      const [f, tt] = dateRange(e.datePreset);
      if (f) q += `&created_from=${f}`;
      if (tt) q += `&created_to=${tt}`;
    }
    onQuery(q, stages);
  }

  function apply() { build(text, selStages); setOpen(false); }
  function reset() {
    setText(""); setCli(null); setCliQ(""); setPhoneQ(""); setDealId(""); setSelStages([]); setOwner(""); setDatePreset(""); setDFrom(""); setDTo("");
    onQuery("", []);
  }
  const active = !!(cli || dealId || owner || selStages.length || datePreset);
  const inp = { height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", fontSize: 13, width: "100%" } as any;

  return (
    <div ref={boxRef} style={{ position: "relative", flex: "1 1 300px", maxWidth: 560, zIndex: 200 }}>
      <input value={text}
        onChange={(e) => { setText(e.target.value); build(e.target.value, selStages); }}
        onFocus={() => setOpen(true)}
        placeholder={t("🔍 Поиск сделки по названию… (клик — все фильтры)","🔍 Пошук сделки за назвою… (клік — усі фільтри)")}
        style={{ ...inp, borderColor: active ? "var(--brand)" : "#cbd5e1", borderWidth: active ? 2 : 1 }} />
      {active && <span onClick={reset} title={t("Сбросить фильтры","Скинути фільтри")} style={{ position: "absolute", right: 10, top: 8, cursor: "pointer", color: "#dc2626", fontWeight: 700 }}>✕</span>}
      {open && (
        <div style={{ position: "absolute", top: 40, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, boxShadow: "0 16px 40px rgba(15,23,42,.18)", padding: 14, zIndex: 1000 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {/* клієнт за іменем */}
            <div style={{ position: "relative" }}>
              <label className="muted" style={{ fontSize: 11 }}>{t("Клиент (имя/фамилия)","Клієнт (імʼя/прізвище)")}</label>
              {cli ? (
                <div style={{ ...inp, display: "flex", alignItems: "center", justifyContent: "space-between", background: "#eff6ff" }}>
                  <b style={{ fontSize: 13 }}>{cli.display_name || `${cli.first_name || ""} ${cli.last_name || ""}`}</b>
                  <span onClick={() => { setCli(null); setCliQ(""); setPhoneQ(""); }} style={{ cursor: "pointer", color: "#dc2626" }}>✕</span>
                </div>
              ) : (
                <input value={cliQ} onChange={(e) => setCliQ(e.target.value)} placeholder={t("начни писать имя…","почни писати імʼя…")} style={inp} />
              )}
              {cliOpts.length > 0 && (
                <div style={{ position: "absolute", top: 56, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, zIndex: 50, maxHeight: 200, overflow: "auto", boxShadow: "0 8px 20px rgba(15,23,42,.15)" }}>
                  {cliOpts.map((c: any) => (
                    <div key={c.id} onClick={() => { setCli(c); setCliOpts([]); }} style={{ padding: "7px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f1f5f9" }}>
                      {(c.display_name || `${c.first_name || ""} ${c.last_name || ""}`).trim() || c.nickname} <span className="muted">{c.phone || ""}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {/* клієнт за телефоном */}
            <div style={{ position: "relative" }}>
              <label className="muted" style={{ fontSize: 11 }}>{t("Телефон клиента","Телефон клієнта")}</label>
              <input value={phoneQ} onChange={(e) => setPhoneQ(e.target.value)} placeholder={t("набери цифры…","набери цифри…")} style={inp} disabled={!!cli} />
              {phoneOpts.length > 0 && (
                <div style={{ position: "absolute", top: 56, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, zIndex: 50, maxHeight: 200, overflow: "auto", boxShadow: "0 8px 20px rgba(15,23,42,.15)" }}>
                  {phoneOpts.map((c: any) => (
                    <div key={c.id} onClick={() => { setCli(c); setPhoneOpts([]); }} style={{ padding: "7px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f1f5f9" }}>
                      <b>{c.phone}</b> · {(c.display_name || `${c.first_name || ""} ${c.last_name || ""}`).trim() || c.nickname}
                    </div>
                  ))}
                </div>
              )}
            </div>
            {/* ID сделки */}
            <div>
              <label className="muted" style={{ fontSize: 11 }}>{t("ID сделки (#)","ID сделки (#)")}</label>
              <input value={dealId} onChange={(e) => setDealId(e.target.value)} placeholder="#65450" style={inp} />
            </div>
            {/* відповідальний */}
            <div>
              <label className="muted" style={{ fontSize: 11 }}>{t("Ответственный","Відповідальний")}</label>
              <select value={owner} onChange={(e) => setOwner(e.target.value)} style={inp}>
                <option value="">{t("— все —","— всі —")}</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
            </div>
          </div>
          {/* стадії — мультивибір чипами */}
          <div style={{ marginTop: 10 }}>
            <label className="muted" style={{ fontSize: 11 }}>{t("Стадии (выбранные останутся в канбане и списке)","Стадії (обрані залишаться в канбані та списку)")}</label>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 4 }}>
              {funnel.stages.map((st: any) => {
                const on = selStages.includes(st.id);
                return (
                  <span key={st.id} onClick={() => setSelStages((p) => on ? p.filter((x) => x !== st.id) : [...p, st.id])}
                    style={{ padding: "3px 10px", borderRadius: 7, fontSize: 11.5, cursor: "pointer", userSelect: "none", fontWeight: on ? 700 : 400,
                      background: on ? st.color : "#f1f5f9", color: on ? "#fff" : "#475569", border: `1px solid ${on ? st.color : "#e2e8f0"}` }}>
                    {st.name}
                  </span>
                );
              })}
            </div>
          </div>
          {/* дата */}
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end", marginTop: 10, flexWrap: "wrap" }}>
            <div>
              <label className="muted" style={{ fontSize: 11 }}>{t("Дата создания","Дата створення")}</label>
              <select value={datePreset} onChange={(e) => setDatePreset(e.target.value)} style={{ ...inp, width: 170 }}>
                <option value="">{t("— любая —","— будь-яка —")}</option>
                <option value="today">{t("Сегодня","Сьогодні")}</option>
                <option value="yesterday">{t("Вчера","Вчора")}</option>
                <option value="month">{t("Текущий месяц","Поточний місяць")}</option>
                <option value="prevmonth">{t("Прошлый месяц","Минулий місяць")}</option>
                <option value="year">{t("Этот год","Цей рік")}</option>
                <option value="range">{t("Диапазон…","Діапазон…")}</option>
              </select>
            </div>
            {datePreset === "range" && (
              <>
                <input type="date" value={dFrom} onChange={(e) => setDFrom(e.target.value)} style={{ ...inp, width: 150 }} />
                <span className="muted">—</span>
                <input type="date" value={dTo} onChange={(e) => setDTo(e.target.value)} style={{ ...inp, width: 150 }} />
              </>
            )}
            <div style={{ flex: 1 }} />
            <button className="btn btn-light" onClick={reset}>{t("Сбросить","Скинути")}</button>
            <button className="btn btn-primary" onClick={apply}>{t("Применить","Застосувати")}</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Deals() {
  const [funnels, setFunnels] = useState<Funnel[]>([]);
  const [curId, setCurId] = useState<number | null>(null);
  const [ver, setVer] = useState(0);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [editFunnel, setEditFunnel] = useState(false);
  const [users, setUsers] = useState<{ id: number; name: string }[]>([]);
  const [view, setView] = useState(localStorage.getItem("deals_view") || "kanban");
  const [fltQuery, setFltQuery] = useState("");
  const [fltStages, setFltStages] = useState<number[]>([]);
  const { t } = useLang();
  const nav = useNavigate();

  useEffect(() => {
    api.get<{ results: Funnel[] }>("/api/funnels/").then((d) => {
      const sales = d.results.filter((f) => !f.is_lead_funnel);
      setFunnels(sales);
      const saved = Number(localStorage.getItem("deals_funnel"));
      setCurId(sales.find((f) => f.id === saved) ? saved : (sales[0]?.id ?? null));
    });
  }, []);

  useEffect(() => { api.get<any>("/api/users/?page_size=100").then((d) => setUsers((d.results || d).map((u: any) => ({ id: u.id, name: u.get_full_name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.username })))).catch(() => {}); }, []);

  const cur = funnels.find((f) => f.id === curId);
  const query = `&ordering=-created_at${fltQuery}`;

  async function create() {
    if (!title.trim() || !cur) return;
    const stage = cur.stages[0]?.id;
    const d = await api.post<{ id: number }>("/api/deals/", { title: title.trim(), funnel: cur.id, stage, amount: 0, source: "other" });
    setCreating(false); setTitle("");
    nav(`/deals/${d.id}`);
  }

  if (!cur) return <div className="spin">{t("Нет доступных воронок продаж.","Немає доступних воронок продажів.")}</div>;

  return (
    <div className="kanban">
      <div className="toolbar">
        <button className="btn btn-primary" onClick={() => setCreating(true)}>{t("+ Сделка","+ Угода")}</button>
        <select value={curId ?? ""} onChange={(e) => { const id = Number(e.target.value); setCurId(id); localStorage.setItem("deals_funnel", String(id)); }}>
          {funnels.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <button className="btn btn-light" onClick={() => setEditFunnel(true)}>{<><Icon n="⚙" size={15} /> {t("Воронка","Воронка")}</>}</button>
        <SmartFilter funnel={cur} users={users} onQuery={(q, st) => { setFltQuery(q); setFltStages(st); }} />
        <div style={{ display: "flex", gap: 2, background: "#eef2f7", borderRadius: 8, padding: 2 }}>
          <button className={"btn" + (view === "kanban" ? " btn-primary" : " btn-light")} style={{ height: 28 }} onClick={() => { setView("kanban"); localStorage.setItem("deals_view", "kanban"); }}><Icon n="grid" size={15} /> {t("Канбан","Канбан")}</button>
          <button className={"btn" + (view === "list" ? " btn-primary" : " btn-light")} style={{ height: 28 }} onClick={() => { setView("list"); localStorage.setItem("deals_view", "list"); }}><Icon n="☰" size={15} /> {t("Список","Список")}</button>
        </div>
        <div className="spacer" />
        <span className="muted">{t("Воронок доступно:","Воронок доступно:")} {funnels.length}</span>
      </div>
      {view === "kanban"
        ? <Board key={ver} endpoint="/api/deals/" funnel={cur} query={query} visibleStages={fltStages} />
        : <ListView endpoint="/api/deals/" funnel={cur} query={query} onChanged={() => setVer((v) => v + 1)} />}

      {creating && (
        <div onClick={() => setCreating(false)} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 12, padding: 22, width: 380 }}>
            <h3 style={{ marginTop: 0 }}>{t("Новая сделка","Нова сделка")}</h3>
            <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()} placeholder={t("Название сделки","Назва сделки")} style={{ width: "100%", height: 38, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", marginBottom: 14 }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setCreating(false)}>{t("Отмена","Скасувати")}</button>
              <button className="btn btn-primary" style={{ flex: 1 }} onClick={create}>{t("Создать","Створити")}</button>
            </div>
          </div>
        </div>
      )}
      {editFunnel && cur && (
        <FunnelEditor funnel={cur} onClose={() => setEditFunnel(false)}
          onSaved={(f) => { setFunnels((fs) => fs.map((x) => (x.id === f.id ? f : x))); setEditFunnel(false); setVer((v) => v + 1); }} />
      )}
    </div>
  );
}
