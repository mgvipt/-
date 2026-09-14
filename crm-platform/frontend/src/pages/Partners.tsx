/* Екран «Партнери» (14.09.2026): список партнерів і кандидатів, знижки по папках і товарах, рівні й налаштування.
 * Знижки задаються тут (у номенклатурі програми), а не в картці клієнта і не в ціні товару: ціни товарів не змінюються.
 * Правило ATM: підказка = частка маржі товару (Старт 25%, Партнер 40%, Золото 50%, Дилер 60% маржі), вниз до 5%;
 * після знижки лишається ≥ 15 п.п. маржі від роздрібної ціни — правило папки CRM сама урізає на «слабких» товарах.
 * Будь-яка зміна знижок: «Перевірити» (нічого не пише) → «Застосувати». Старі угоди не перераховуються.
 * Автознижка в угодах — ВИМКНЕНА (окремий крок 5). Усі компоненти — на рівні модуля (поля не втрачають фокус). */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../Icon";

type Level = { id: number; name: string; order: number; threshold_uah: number; margin_share: number; color: string; is_active: boolean; n_partners: number };
type Cell = {
  own_pct: number | null; inherited_pct: number | null; inherited_from: string; n_capped: number; n_discounted: number;
  suggested_pct?: number | null; suggested_src?: string; avg_left_pp?: number | null; min_left_pp?: number | null;
  growth_needed_pct?: number | null; avg_pct?: number | null;
};
type CatRow = { id: number; name: string; parent_id: number | null; depth: number; n_products: number; n_no_cost: number; no_discount: boolean; own_brand: boolean; cells: Record<string, Cell> };
type Matrix = { levels: Level[]; categories: CatRow[]; min_margin_pp: number; round_step: number; can_cost: boolean; can_manage: boolean; n_uncategorized: number; n_product_exceptions: number };
type PCell = {
  pct: number; rule_pct: number | null; source: string; source_name: string; capped: boolean; override: boolean; note: string;
  exception: boolean; exception_pct: number | null; exception_excluded: boolean;
  left_pp?: number | null; max_pct?: number | null; suggested_pct?: number | null; price_after?: number | null;
};
type PRow = { id: number; name: string; sku: string; price: number; unit: string; category_id: number | null; category_name: string; no_cost: boolean; margin_pp?: number | null; levels: Record<string, PCell> };
type PList = { results: PRow[]; count: number; page: number; page_size: number; levels: Level[]; can_cost: boolean; can_manage: boolean; can_below_min: boolean };
type Stats = { n_products: number; n_no_cost: number; n_capped: number; n_discounted: number; min_left_pp: number | null; avg_left_pp: number | null; avg_pct: number | null; growth_needed_pct: number | null };
type Ex = { id: number; name: string; before_pct: number; after_pct: number; note: string; left_pp_after?: number | null };
type Preview = { title: string; n_products: number; levels: { level_id: number; level_name: string; before: Stats; after: Stats; n_changed: number; examples: Ex[] }[]; warnings: string[]; errors: string[]; can_apply: boolean; dry_run: boolean; changed?: number };
type Target = { kind: "category"; id: number; name: string } | { kind: "products"; ids: number[]; name: string };
type Vals = Record<string, string>;

const TABS: [string, string][] = [
  ["partners", "Партнери"], ["categories", "Знижки: папки"], ["products", "Знижки: товари"],
  ["levels", "Рівні і налаштування"], ["log", "Історія змін"], ["help", "Як це працює"],
];
const money = (n: number | null | undefined) => (n == null ? "—" : Math.round(n).toLocaleString("uk-UA") + " ₴");
const pc = (n: number | null | undefined) => (n == null ? "—" : `${Math.round(n * 10) / 10}%`);
const dmy = (s: string | null | undefined) => (s ? s.slice(0, 10).split("-").reverse().join(".") : "");
const errText = (e: unknown, fb = "Помилка") => {
  const dd = (e as { data?: { detail?: string; errors?: string[] } } | null)?.data;
  return dd?.detail || (dd?.errors || []).join("; ") || fb;
};
const TH: CSSProperties = { textAlign: "left", padding: "6px 8px", fontSize: 11, color: "#64748b", fontWeight: 600, borderBottom: "1px solid #e2e8f0", whiteSpace: "nowrap" };
const TD: CSSProperties = { padding: "5px 8px", borderBottom: "1px solid #f1f5f9", fontSize: 12.5, verticalAlign: "top" };
const INP: CSSProperties = { height: 30, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px", fontSize: 13 };
const Badge = ({ lv }: { lv: { name: string; color: string } }) => (
  <span className="chip" style={{ background: lv.color, color: "#fff", fontWeight: 700 }}>{lv.name}</span>
);

export default function Partners() {
  const [tab, setTab] = useState("partners");
  const [target, setTarget] = useState<Target | null>(null);
  const [prefill, setPrefill] = useState<Vals | null>(null);
  const [bump, setBump] = useState(0);
  const openEditor = (t: Target, vals?: Vals) => { setTarget(t); setPrefill(vals || null); };
  return (
    <div className="scroll pad fade">
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <Icon n="💼" size={20} />
        <h2 style={{ margin: 0 }}>Партнери</h2>
        <span className="muted">рівні, знижки в номенклатурі, оборот партнерів · автознижка в угодах вимкнена</span>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "8px 0 12px" }}>
        {TABS.map(([k, l]) => (
          <button key={k} className={"btn" + (tab === k ? " btn-primary" : "")} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      {tab === "partners" && <PartnersTab />}
      {tab === "categories" && <CategoriesTab bump={bump} onEdit={openEditor} />}
      {tab === "products" && <ProductsTab bump={bump} onEdit={openEditor} />}
      {tab === "levels" && <LevelsTab />}
      {tab === "log" && <LogTab bump={bump} />}
      {tab === "help" && <HelpTab />}
      {target && <Editor target={target} prefill={prefill} onClose={() => setTarget(null)} onApplied={() => { setTarget(null); setBump((b) => b + 1); }} />}
    </div>
  );
}

/* ───────────── Партнери і кандидати ───────────── */
type PartnerRow = { contact_id: number; name: string; is_active: boolean; level: Level; since: string | null; turnover_uah: number; next_level: string | null; to_next_uah: number | null };
type Cand = { contact_id: number; name: string; turnover_uah: number; level_by_turnover: string };

function PartnersTab() {
  const [d, setD] = useState<{ results: PartnerRow[]; candidates: Cand[]; turnover_from: string } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get<any>("/api/partners/list/").then(setD).catch((e) => setErr(errText(e))); }, []);
  if (err) return <div className="panel" style={{ color: "#dc2626" }}>{err}</div>;
  if (!d) return <div className="muted">Завантаження…</div>;
  return (
    <>
      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="label" style={{ marginBottom: 6 }}>Партнери ({d.results.length})</div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Зробити партнером — у картці клієнта галочка «Партнер» (право «Присвоювати статус партнера»). Оборот — усі оплати з {dmy(d.turnover_from)}.
        </div>
        {d.results.length === 0 ? <div className="muted">Поки немає жодного партнера.</div> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
              <thead><tr><th style={TH}>Клієнт</th><th style={TH}>Рівень</th><th style={TH}>Партнер з</th><th style={TH}>Оплачено</th><th style={TH}>До наступного</th></tr></thead>
              <tbody>
                {d.results.map((r) => (
                  <tr key={r.contact_id} style={{ opacity: r.is_active ? 1 : 0.55 }}>
                    <td style={TD}><Link to={`/clients/${r.contact_id}`}>{r.name}</Link>{!r.is_active && <span className="muted"> · галочку знято</span>}</td>
                    <td style={TD}><Badge lv={r.level} /></td>
                    <td style={TD}>{dmy(r.since)}</td>
                    <td style={TD}><b>{money(r.turnover_uah)}</b></td>
                    <td style={TD}>{r.next_level ? <>«{r.next_level}»: ще {money(r.to_next_uah)}</> : <span className="muted">найвищий</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="panel">
        <div className="label" style={{ marginBottom: 6 }}>Кандидати ({d.candidates.length})</div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>Не партнери, у яких оплачений оборот уже вище першого порогу. Статус НЕ ставиться автоматично — лише галочкою в картці.</div>
        {d.candidates.length === 0 ? <div className="muted">Немає.</div> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 480 }}>
              <thead><tr><th style={TH}>Клієнт</th><th style={TH}>Оплачено</th><th style={TH}>Рівень за оборотом</th></tr></thead>
              <tbody>
                {d.candidates.map((r) => (
                  <tr key={r.contact_id}><td style={TD}><Link to={`/clients/${r.contact_id}`}>{r.name}</Link></td><td style={TD}>{money(r.turnover_uah)}</td><td style={TD}>{r.level_by_turnover}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

/* ───────────── Знижки по папках ───────────── */
function CategoriesTab({ bump, onEdit }: { bump: number; onEdit: (t: Target, v?: Vals) => void }) {
  const [m, setM] = useState<Matrix | null>(null);
  const [err, setErr] = useState("");
  const [sugg, setSugg] = useState<any | null>(null);
  const [ownOnly, setOwnOnly] = useState(true);
  const [diffOnly, setDiffOnly] = useState(true);
  const load = useCallback(() => { api.get<Matrix>("/api/partners/matrix/").then(setM).catch((e) => setErr(errText(e))); }, []);
  useEffect(() => { load(); }, [load, bump]);
  const loadSugg = async () => {
    try { setSugg(await api.post<any>("/api/partners/discounts/suggest/", { target: "categories" })); } catch (e) { setErr(errText(e)); }
  };
  useEffect(() => { if (sugg) loadSugg(); }, [bump]); // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <div className="panel" style={{ color: "#dc2626" }}>{err}</div>;
  if (!m) return <div className="muted">Завантаження…</div>;
  const valsFrom = (row: CatRow) => {
    const v: Vals = {};
    m.levels.forEach((lv) => { const c = row.cells[lv.id]; v[lv.id] = c && c.own_pct != null ? String(c.own_pct) : ""; });
    return v;
  };
  const rows = (sugg?.rows || []).filter((r: any) => (!ownOnly || r.own_brand) && (!diffOnly || r.differs));
  return (
    <>
      <div className="panel" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <div className="label" style={{ margin: 0 }}>Знижка рівня на папку діє на всі товари папки й підпапок</div>
          <span className="muted" style={{ fontSize: 12 }}>
            жирне — своє правило · сіре — успадковано від батьківської папки · «—» — без знижки · мінімум маржі {m.min_margin_pp} п.п.
          </span>
          {m.can_manage && m.can_cost && (
            <button className="btn btn-primary" style={{ marginLeft: "auto" }} onClick={loadSugg}><Icon n="sparkles" size={14} /> Запропонувати за правилом ATM</button>
          )}
        </div>
        {sugg && (
          <div style={{ marginTop: 10, borderTop: "1px solid #e2e8f0", paddingTop: 8 }}>
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", fontSize: 12.5 }}>
              <b>Підказки ATM</b>
              <label><input type="checkbox" checked={ownOnly} onChange={(e) => setOwnOnly(e.target.checked)} /> лише власні WALLCOV (покриття, грунти, інструменти)</label>
              <label><input type="checkbox" checked={diffOnly} onChange={(e) => setDiffOnly(e.target.checked)} /> лише де відрізняється від поточного</label>
              <span className="muted">Чужі бренди — за рішенням Олега винятками по товару (вкладка «Знижки: товари»).</span>
              <button className="btn btn-light" style={{ marginLeft: "auto" }} onClick={() => setSugg(null)}>Сховати</button>
            </div>
            {rows.length === 0 ? <div className="muted" style={{ marginTop: 6 }}>Усе вже збігається з підказкою.</div> : (
              <div style={{ overflowX: "auto", marginTop: 6 }}>
                <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 700 }}>
                  <thead><tr><th style={TH}>Папка</th>{sugg.levels.map((lv: Level) => <th key={lv.id} style={TH}>{lv.name}: зараз → пропонує</th>)}<th style={TH}></th></tr></thead>
                  <tbody>
                    {rows.map((r: any) => (
                      <tr key={r.category_id}>
                        <td style={{ ...TD, paddingLeft: 8 + r.depth * 14 }}>{r.name}</td>
                        {sugg.levels.map((lv: Level) => {
                          const c = r.levels[lv.id];
                          return <td key={lv.id} style={TD}>{pc(c.current)} → <b>{pc(c.suggested)}</b>{c.src === "oleg" && <span className="muted"> (Олег)</span>}{c.src === "no_cost" && <span className="muted"> немає собівартості</span>}</td>;
                        })}
                        <td style={TD}>
                          <button className="btn btn-light" style={{ fontSize: 12 }} onClick={() => {
                            const v: Vals = {};
                            sugg.levels.forEach((lv: Level) => { const s = r.levels[lv.id].suggested; v[lv.id] = s == null ? "" : String(s); });
                            onEdit({ kind: "category", id: r.category_id, name: r.name }, v);
                          }}>Перевірити і застосувати</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="panel">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 820 }}>
            <thead>
              <tr>
                <th style={TH}>Папка</th><th style={TH}>Товарів</th>
                {m.levels.map((lv) => <th key={lv.id} style={TH}><Badge lv={lv} /> <span className="muted">від {money(lv.threshold_uah)}</span></th>)}
              </tr>
            </thead>
            <tbody>
              {m.categories.map((r) => (
                <tr key={r.id} onClick={() => m.can_manage && onEdit({ kind: "category", id: r.id, name: r.name }, valsFrom(r))}
                  style={{ cursor: m.can_manage ? "pointer" : "default", background: r.no_discount ? "#f8fafc" : undefined }}
                  title={m.can_manage ? "Клікніть, щоб змінити знижки папки" : ""}>
                  <td style={{ ...TD, paddingLeft: 8 + r.depth * 16, fontWeight: r.depth === 0 ? 700 : 500 }}>
                    {r.name}{r.no_discount && <span className="muted"> · тест-набори: без знижки</span>}
                  </td>
                  <td style={TD}>{r.n_products}{r.n_no_cost > 0 && <div className="muted" style={{ fontSize: 11 }}>{r.n_no_cost} без собівартості</div>}</td>
                  {m.levels.map((lv) => <MatrixCell key={lv.id} c={r.cells[lv.id]} canCost={m.can_cost} minPp={m.min_margin_pp} />)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Без папки: {m.n_uncategorized} товарів (лише винятки по товару). Винятків по товарах: {m.n_product_exceptions}.
        </div>
      </div>
    </>
  );
}

function MatrixCell({ c, canCost, minPp }: { c?: Cell; canCost: boolean; minPp: number }) {
  if (!c) return <td style={TD}>—</td>;
  const main = c.own_pct != null ? <b>{pc(c.own_pct)}</b>
    : c.inherited_pct != null ? <span style={{ color: "#94a3b8" }} title={`успадковано від «${c.inherited_from}»`}>{pc(c.inherited_pct)} ↑</span>
    : <span className="muted">—</span>;
  const low = canCost && c.min_left_pp != null && c.min_left_pp < minPp;
  return (
    <td style={TD}>
      {main}
      {canCost && c.suggested_pct != null && <span className="muted" style={{ fontSize: 11 }}> · ATM {pc(c.suggested_pct)}</span>}
      {canCost && c.avg_left_pp != null && (c.own_pct != null || c.inherited_pct != null) && (
        <div style={{ fontSize: 11, color: low ? "#b91c1c" : "#64748b" }}>
          лишається {c.avg_left_pp} п.п.{c.n_capped > 0 ? ` · урізано ${c.n_capped}` : ""}
          {c.growth_needed_pct != null && <span title="На скільки мають вирости продажі, щоб знижка окупилась (ATM)"> · +{Math.round(c.growth_needed_pct)}% продажів</span>}
        </div>
      )}
    </td>
  );
}

/* ───────────── Знижки по товарах ───────────── */
function ProductsTab({ bump, onEdit }: { bump: number; onEdit: (t: Target, v?: Vals) => void }) {
  const [cats, setCats] = useState<CatRow[]>([]);
  const [cat, setCat] = useState("");
  const [q, setQ] = useState("");
  const [qApplied, setQApplied] = useState("");
  const [onlyExc, setOnlyExc] = useState(false);
  const [page, setPage] = useState(1);
  const [d, setD] = useState<PList | null>(null);
  const [sel, setSel] = useState<number[]>([]);
  const [err, setErr] = useState("");
  const [sugg, setSugg] = useState<any | null>(null);
  useEffect(() => { api.get<Matrix>("/api/partners/matrix/").then((m) => setCats(m.categories)).catch(() => setCats([])); }, []);
  useEffect(() => {
    const p = new URLSearchParams({ page: String(page) });
    if (cat) p.set("category", cat);
    if (qApplied) p.set("q", qApplied);
    if (onlyExc) p.set("exceptions", "1");
    api.get<PList>(`/api/partners/products/?${p}`).then((r) => { setD(r); setErr(""); }).catch((e) => setErr(errText(e)));
  }, [cat, qApplied, onlyExc, page, bump]);
  useEffect(() => { setSel([]); setSugg(null); }, [cat, qApplied, onlyExc, page, bump]);
  const toggle = (id: number) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const names = useMemo(() => new Map((d?.results || []).map((r) => [r.id, r.name])), [d]);
  const loadSugg = async () => {
    try { setSugg(await api.post<any>("/api/partners/discounts/suggest/", { target: "products", product_ids: sel })); } catch (e) { setErr(errText(e)); }
  };
  const pages = d ? Math.max(1, Math.ceil(d.count / d.page_size)) : 1;
  return (
    <div className="panel">
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
        <select value={cat} onChange={(e) => { setCat(e.target.value); setPage(1); }} style={{ ...INP, maxWidth: 360 }}>
          <option value="">Усі папки</option>
          <option value="none">— без папки —</option>
          {cats.map((c) => <option key={c.id} value={c.id}>{"  ".repeat(c.depth) + c.name}</option>)}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { setQApplied(q.trim()); setPage(1); } }}
          placeholder="Назва або артикул + Enter" style={{ ...INP, width: 240 }} />
        <label style={{ fontSize: 12.5 }}><input type="checkbox" checked={onlyExc} onChange={(e) => { setOnlyExc(e.target.checked); setPage(1); }} /> лише винятки</label>
        {d?.can_manage && sel.length > 0 && (
          <>
            <button className="btn btn-primary" onClick={() => onEdit({ kind: "products", ids: sel, name: `${sel.length} товар(ів)` })}>
              <Icon n="pencil" size={13} /> Змінити знижки вибраних ({sel.length})
            </button>
            {d.can_cost && <button className="btn" onClick={loadSugg}><Icon n="sparkles" size={13} /> Підказка ATM по кожному</button>}
          </>
        )}
      </div>
      {err && <div style={{ color: "#dc2626", marginBottom: 6 }}>{err}</div>}
      {sugg && (
        <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 8, marginBottom: 8 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <b style={{ fontSize: 12.5 }}>Підказки ATM по товарах</b>
            <span className="muted" style={{ fontSize: 12 }}>застосовується окремо по кожному товару — спершу перевірка</span>
            <button className="btn btn-light" style={{ marginLeft: "auto" }} onClick={() => setSugg(null)}>Сховати</button>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 640 }}>
              <thead><tr><th style={TH}>Товар</th><th style={TH}>Маржа</th>{sugg.levels.map((lv: Level) => <th key={lv.id} style={TH}>{lv.name}: діє → ATM</th>)}<th style={TH}></th></tr></thead>
              <tbody>
                {sugg.rows.map((r: any) => (
                  <tr key={r.product_id}>
                    <td style={TD}>{r.name}</td>
                    <td style={TD}>{r.margin_pp == null ? <span className="muted">немає собівартості</span> : pc(r.margin_pp)}</td>
                    {sugg.levels.map((lv: Level) => { const c = r.levels[lv.id]; return <td key={lv.id} style={TD}>{pc(c.effective)} → <b>{pc(c.suggested)}</b></td>; })}
                    <td style={TD}>
                      <button className="btn btn-light" style={{ fontSize: 12 }} disabled={r.margin_pp == null} onClick={() => {
                        const v: Vals = {};
                        sugg.levels.forEach((lv: Level) => { v[lv.id] = String(r.levels[lv.id].suggested ?? 0); });
                        onEdit({ kind: "products", ids: [r.product_id], name: names.get(r.product_id) || r.name }, v);
                      }}>Перевірити і застосувати</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {!d ? <div className="muted">Завантаження…</div> : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 860 }}>
              <thead>
                <tr>
                  <th style={TH}>{d.can_manage && <input type="checkbox" checked={d.results.length > 0 && sel.length === d.results.length}
                    onChange={(e) => setSel(e.target.checked ? d.results.map((r) => r.id) : [])} />}</th>
                  <th style={TH}>Товар</th><th style={TH}>Ціна</th>{d.can_cost && <th style={TH}>Маржа</th>}
                  {d.levels.map((lv) => <th key={lv.id} style={TH}><Badge lv={lv} /></th>)}
                </tr>
              </thead>
              <tbody>
                {d.results.map((r) => (
                  <tr key={r.id}>
                    <td style={TD}>{d.can_manage && <input type="checkbox" checked={sel.includes(r.id)} onChange={() => toggle(r.id)} />}</td>
                    <td style={TD}>{r.name}<div className="muted" style={{ fontSize: 11 }}>{r.category_name || "без папки"}{r.sku ? ` · ${r.sku}` : ""}</div></td>
                    <td style={TD}>{money(r.price)}</td>
                    {d.can_cost && <td style={TD}>{r.no_cost ? <span style={{ color: "#94a3b8" }}>немає собівартості</span> : pc(r.margin_pp)}</td>}
                    {d.levels.map((lv) => <ProductCell key={lv.id} c={r.levels[lv.id]} canCost={d.can_cost} />)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8, fontSize: 12.5 }}>
            <span className="muted">Знайдено {d.count}</span>
            <button className="btn btn-light" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>←</button>
            <span>{page} / {pages}</span>
            <button className="btn btn-light" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>→</button>
          </div>
        </>
      )}
    </div>
  );
}

function ProductCell({ c, canCost }: { c?: PCell; canCost: boolean }) {
  if (!c) return <td style={TD}>—</td>;
  const color = c.source === "product" || c.source === "excluded" ? "#1d4ed8" : c.capped ? "#b91c1c" : c.source === "category" ? "#475569" : "#94a3b8";
  const src = c.source === "product" ? "виняток" : c.source === "excluded" ? "виключено" : c.source === "category" ? `папка «${c.source_name}»`
    : c.source === "no_discount" ? "тест-набір" : "немає правила";
  return (
    <td style={TD} title={c.note || src}>
      <b style={{ color }}>{pc(c.pct)}</b>
      {c.capped && c.rule_pct != null && <span style={{ color: "#b91c1c", fontSize: 11 }}> (було {pc(c.rule_pct)})</span>}
      <div style={{ fontSize: 11, color: "#94a3b8" }}>{src}{canCost && c.left_pp != null && c.pct > 0 ? ` · лишається ${c.left_pp} п.п.` : ""}</div>
    </td>
  );
}

/* ───────────── Редактор: Перевірити → Застосувати ───────────── */
function Editor({ target, prefill, onClose, onApplied }: { target: Target; prefill: Vals | null; onClose: () => void; onApplied: () => void }) {
  const { can } = useAuth();
  const [levels, setLevels] = useState<Level[]>([]);
  const [vals, setVals] = useState<Vals>(prefill || {});
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { api.get<any>("/api/partners/levels/").then((r) => setLevels((r.levels as Level[]).filter((l) => l.is_active))).catch(() => setLevels([])); }, []);
  useEffect(() => { setPreview(null); }, [vals, reason]);
  const body = () => {
    const values: Record<string, unknown> = {};
    levels.forEach((lv) => {
      const v = (vals[lv.id] ?? "").trim();
      if (v === "keep") return;
      values[lv.id] = v === "" ? null : v === "exclude" ? "exclude" : v;
    });
    const base = target.kind === "category" ? { target: "category", category_id: target.id } : { target: "products", product_ids: target.ids };
    return { ...base, values, reason, source: prefill ? "atm" : "manual" };
  };
  const run = async (apply: boolean) => {
    setBusy(true);
    setErr("");
    try {
      const r = await api.post<Preview>(`/api/partners/discounts/${apply ? "apply" : "preview"}/`, body());
      if (apply) onApplied(); else setPreview(r);
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const isProducts = target.kind === "products";
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, width: "min(760px,100%)", maxHeight: "90vh", overflowY: "auto", padding: 18, fontSize: 13.5 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <Icon n="💼" size={16} /><b>{isProducts ? "Винятки для товарів" : "Знижки для папки"}: {target.name}</b>
          <button className="btn btn-light" style={{ marginLeft: "auto" }} onClick={onClose}>✕</button>
        </div>
        <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
          {isProducts
            ? "Порожньо — прибрати виняток (діятиме знижка папки). «Виключити» — товар без партнерської знижки. «не міняти» — лишити як є."
            : "Порожньо — своє правило папки прибрати (успадкує від батьківської). Товари, де маржі не вистачає, CRM урізає сама до мінімуму."}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: "6px 10px", alignItems: "center" }}>
          {levels.map((lv) => (
            <LevelInput key={lv.id} lv={lv} value={vals[lv.id] ?? (isProducts ? "keep" : "")} products={isProducts}
              onChange={(v) => setVals((s) => ({ ...s, [lv.id]: v }))} />
          ))}
        </div>
        {isProducts && can("partners.below_min") && (
          <div style={{ marginTop: 8 }}>
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Причина, якщо знижка нижче мінімальної маржі (обовʼязково в цьому випадку)"
              style={{ ...INP, width: "100%" }} />
          </div>
        )}
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button className="btn" disabled={busy} onClick={() => run(false)}><Icon n="search" size={13} /> Перевірити</button>
          <button className="btn btn-primary" disabled={busy || !preview || !preview.can_apply} onClick={() => run(true)}
            title={!preview ? "Спершу «Перевірити»" : ""}><Icon n="check" size={13} /> Застосувати</button>
          {err && <span style={{ color: "#dc2626" }}>{err}</span>}
        </div>
        {preview && <PreviewBox p={preview} />}
      </div>
    </div>
  );
}

function LevelInput({ lv, value, products, onChange }: { lv: Level; value: string; products: boolean; onChange: (v: string) => void }) {
  const mode = value === "keep" ? "keep" : value === "exclude" ? "exclude" : "pct";
  return (
    <>
      <Badge lv={lv} />
      <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        {products && (
          <select value={mode} onChange={(e) => onChange(e.target.value === "pct" ? "" : e.target.value)} style={INP}>
            <option value="keep">не міняти</option>
            <option value="pct">знижка / прибрати</option>
            <option value="exclude">виключити</option>
          </select>
        )}
        {mode === "pct" && (
          <input value={value} onChange={(e) => onChange(e.target.value.replace(",", "."))} placeholder="порожньо = прибрати"
            style={{ ...INP, width: 150 }} inputMode="decimal" />
        )}
        {mode === "pct" && <span className="muted">%</span>}
      </span>
    </>
  );
}

function PreviewBox({ p }: { p: Preview }) {
  return (
    <div style={{ marginTop: 12, borderTop: "1px solid #e2e8f0", paddingTop: 10 }}>
      <b>Перевірка: {p.title}, товарів {p.n_products}</b> <span className="muted">— нічого не записано</span>
      {p.errors.length > 0 && <div style={{ color: "#b91c1c", marginTop: 6 }}>{p.errors.map((e, i) => <div key={i}><Icon n="warn" size={13} /> {e}</div>)}</div>}
      {p.warnings.length > 0 && <div style={{ color: "#92400e", marginTop: 6 }}>{p.warnings.map((e, i) => <div key={i}>{e}</div>)}</div>}
      {p.levels.map((l) => (
        <div key={l.level_id} style={{ marginTop: 8, background: "#f8fafc", borderRadius: 8, padding: "6px 10px" }}>
          <div><b>{l.level_name}</b>: зміниться у {l.n_changed} товар(ах) · зі знижкою {l.after.n_discounted} · урізано маржею {l.after.n_capped}
            · без собівартості {l.after.n_no_cost}
            {l.after.min_left_pp != null && <> · лишається мін. {l.after.min_left_pp} / сер. {l.after.avg_left_pp} п.п.</>}
            {l.after.growth_needed_pct != null && <> · продажі мають вирости на {Math.round(l.after.growth_needed_pct)}%</>}
          </div>
          {l.examples.length > 0 && (
            <div style={{ fontSize: 12, marginTop: 4 }}>
              {l.examples.map((x) => (
                <div key={x.id}>{x.name}: {pc(x.before_pct)} → <b>{pc(x.after_pct)}</b>{x.left_pp_after != null && ` · лишається ${x.left_pp_after} п.п.`}{x.note && <span className="muted"> · {x.note}</span>}</div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ───────────── Рівні і налаштування ───────────── */
function LevelsTab() {
  const [levels, setLevels] = useState<Level[] | null>(null);
  const [canManage, setCanManage] = useState(false);
  const [st, setSt] = useState<any | null>(null);
  const [msg, setMsg] = useState("");
  const load = useCallback(() => {
    api.get<any>("/api/partners/levels/").then((r) => { setLevels(r.levels); setCanManage(r.can_manage); }).catch(() => setLevels([]));
    api.get<any>("/api/partners/settings/").then(setSt).catch(() => setSt(null));
  }, []);
  useEffect(() => { load(); }, [load]);
  const saveLevel = async (id: number, patch: Record<string, unknown>) => {
    setMsg("");
    try { await api.patch(`/api/partners/levels/${id}/`, patch); setMsg("Збережено"); load(); } catch (e) { setMsg(errText(e)); load(); }
  };
  const addLevel = async () => {
    const name = window.prompt("Назва нового рівня");
    if (!name) return;
    try { await api.post("/api/partners/levels/", { name, threshold_uah: 1000000, margin_share: 0.6 }); load(); } catch (e) { setMsg(errText(e)); }
  };
  const saveSt = async (patch: Record<string, unknown>) => {
    setMsg("");
    try { setSt(await api.patch<any>("/api/partners/settings/", patch)); setMsg("Збережено"); } catch (e) { setMsg(errText(e)); }
  };
  if (!levels) return <div className="muted">Завантаження…</div>;
  return (
    <>
      <div className="panel" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <div className="label" style={{ margin: 0 }}>Рівні</div>
          <span className="muted" style={{ fontSize: 12 }}>Статус лише підвищується. Зміна порогів нікого не знижує.</span>
          {msg && <span style={{ marginLeft: "auto", color: msg === "Збережено" ? "#16a34a" : "#dc2626" }}>{msg}</span>}
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 700 }}>
            <thead><tr><th style={TH}>Назва</th><th style={TH}>Поріг оплат, ₴</th><th style={TH}>Частка маржі для підказки</th><th style={TH}>Колір</th><th style={TH}>Активний</th><th style={TH}>Партнерів</th></tr></thead>
            <tbody>
              {levels.map((lv) => <LevelRow key={lv.id + ":" + lv.name + lv.threshold_uah + lv.margin_share + lv.color} lv={lv} canManage={canManage} onSave={saveLevel} />)}
            </tbody>
          </table>
        </div>
        {canManage && <button className="btn btn-light" style={{ marginTop: 8 }} onClick={addLevel}><Icon n="plus" size={13} /> Додати рівень</button>}
      </div>
      {st && <SettingsPanel st={st} canManage={canManage} onSave={saveSt} />}
    </>
  );
}

function LevelRow({ lv, canManage, onSave }: { lv: Level; canManage: boolean; onSave: (id: number, p: Record<string, unknown>) => void }) {
  const [name, setName] = useState(lv.name);
  const [thr, setThr] = useState(String(lv.threshold_uah));
  const [share, setShare] = useState(String(Math.round(lv.margin_share * 100)));
  const [color, setColor] = useState(lv.color);
  const dirty = name !== lv.name || Number(thr) !== lv.threshold_uah || Number(share) !== Math.round(lv.margin_share * 100) || color !== lv.color;
  return (
    <tr>
      <td style={TD}>{canManage ? <input value={name} onChange={(e) => setName(e.target.value)} style={{ ...INP, width: 130 }} /> : <Badge lv={lv} />}</td>
      <td style={TD}>{canManage ? <input value={thr} onChange={(e) => setThr(e.target.value)} style={{ ...INP, width: 120 }} inputMode="numeric" /> : money(lv.threshold_uah)}</td>
      <td style={TD}>{canManage ? <><input value={share} onChange={(e) => setShare(e.target.value)} style={{ ...INP, width: 70 }} inputMode="numeric" /> % маржі</> : `${Math.round(lv.margin_share * 100)}% маржі`}</td>
      <td style={TD}>{canManage ? <input type="color" value={color.length === 7 ? color : "#be185d"} onChange={(e) => setColor(e.target.value)} /> : <span style={{ display: "inline-block", width: 16, height: 16, borderRadius: 4, background: lv.color }} />}</td>
      <td style={TD}><input type="checkbox" checked={lv.is_active} disabled={!canManage} onChange={(e) => onSave(lv.id, { is_active: e.target.checked })} /></td>
      <td style={TD}>{lv.n_partners}{canManage && dirty && (
        <button className="btn btn-primary" style={{ marginLeft: 8, height: 26, fontSize: 12 }}
          onClick={() => onSave(lv.id, { name, threshold_uah: thr, margin_share: Number(share) / 100, color })}>Зберегти</button>
      )}</td>
    </tr>
  );
}

function SettingsPanel({ st, canManage, onSave }: { st: any; canManage: boolean; onSave: (p: Record<string, unknown>) => void }) {
  const [minPp, setMinPp] = useState(String(st.min_margin_pp));
  const [step, setStep] = useState(String(st.round_step));
  const [from, setFrom] = useState(st.turnover_from || "");
  const [start, setStart] = useState<Record<string, string>>(() => Object.fromEntries((st.start_fixed || []).map((x: any) => [String(x.category_id), String(x.pct)])));
  const list = (xs: { id: number; name: string }[]) => (xs || []).map((x) => x.name).join(", ") || "—";
  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 8 }}>Налаштування</div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(220px,300px) 1fr", gap: "8px 12px", alignItems: "center", fontSize: 13 }}>
        <span>Мінімум маржі після знижки, п.п. від роздрібної ціни</span>
        <span><input value={minPp} disabled={!canManage} onChange={(e) => setMinPp(e.target.value)} style={{ ...INP, width: 80 }} /></span>
        <span>Округлення підказки ATM вниз до, %</span>
        <span><input value={step} disabled={!canManage} onChange={(e) => setStep(e.target.value)} style={{ ...INP, width: 80 }} /></span>
        <span>Оборот рахувати з дати</span>
        <span><input type="date" value={from} disabled={!canManage} onChange={(e) => setFrom(e.target.value)} style={INP} /></span>
        <span>Підвищувати рівень одразу після оплати</span>
        <span><input type="checkbox" checked={!!st.auto_raise} disabled={!canManage} onChange={(e) => onSave({ auto_raise: e.target.checked })} /></span>
        <span>Автознижка в угодах</span>
        <span className="muted"><Icon n="lock" size={13} /> вимкнена — окремий крок 5, після перевірки на тестовій угоді й «ок» Олега</span>
        <span>«Старт» на власні папки (затверджено Олегом)</span>
        <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {(st.start_fixed || []).map((x: any) => (
            <span key={x.category_id}>
              <input value={start[String(x.category_id)] ?? ""} disabled={!canManage} onChange={(e) => setStart((s) => ({ ...s, [String(x.category_id)]: e.target.value }))}
                style={{ ...INP, width: 60 }} />% — {x.name}
            </span>
          ))}
          {(st.start_fixed || []).length === 0 && <span className="muted">—</span>}
        </span>
        <span>Без партнерської знижки</span><span className="muted">{list(st.no_discount_categories)}</span>
        <span>Не рахуються в оборот (воронки)</span><span className="muted">{list(st.exclude_funnels)}</span>
        <span>Віднімаються з обороту (повернення)</span><span className="muted">{list(st.refund_categories)}</span>
        <span>Надходження, що не є виручкою</span><span className="muted">{list(st.exclude_in_categories)}</span>
      </div>
      {canManage && (
        <button className="btn btn-primary" style={{ marginTop: 10 }} onClick={() => onSave({ min_margin_pp: minPp, round_step: step, turnover_from: from, start_fixed: start })}>
          <Icon n="💾" size={13} /> Зберегти налаштування
        </button>
      )}
    </div>
  );
}

/* ───────────── Історія змін знижок ───────────── */
function LogTab({ bump }: { bump: number }) {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { api.get<any>("/api/partners/log/").then((r) => setRows(r.results)).catch(() => setRows([])); }, [bump]);
  if (!rows) return <div className="muted">Завантаження…</div>;
  const val = (p: number | null, ex: boolean | null) => (ex ? "виключено" : p == null ? "—" : pc(p));
  return (
    <div className="panel">
      {rows.length === 0 ? <div className="muted">Змін ще не було.</div> : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 680 }}>
            <thead><tr><th style={TH}>Коли</th><th style={TH}>Хто</th><th style={TH}>Рівень</th><th style={TH}>Що</th><th style={TH}>Було → стало</th><th style={TH}>Звідки</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td style={TD}>{dmy(r.created_at)} {String(r.created_at || "").slice(11, 16)}</td>
                  <td style={TD}>{r.user || "Система"}</td>
                  <td style={TD}>{r.level}</td>
                  <td style={TD}>{r.kind}: {r.target}</td>
                  <td style={TD}>{val(r.old_pct, r.old_excluded)} → <b>{val(r.new_pct, r.new_excluded)}</b></td>
                  <td style={TD}>{r.source === "atm" ? "підказка ATM" : r.source === "seed" ? "стартові" : "вручну"}{r.note ? ` · ${r.note}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ───────────── Як це працює ───────────── */
function HelpTab() {
  return (
    <div className="panel" style={{ lineHeight: 1.6, fontSize: 13.5, maxWidth: 860 }}>
      <b>Як працює партнерська програма</b>
      <ol style={{ paddingLeft: 18 }}>
        <li>Знижки задаються тут: спершу на <b>папку</b> (діє на всі товари папки й підпапок), потім <b>винятки</b> для окремих товарів. Виняток товару важливіший за папку.</li>
        <li>У картці клієнта — лише галочка «Партнер». Вона дає рівень «Старт» (або одразу вищий, якщо клієнт уже багато оплатив).</li>
        <li>Рівень <b>тільки росте</b>: Партнер від 25 000 ₴, Золото від 75 000 ₴, Дилер від 200 000 ₴ оплат. Підвищення — одразу після оплати і нічною перевіркою.</li>
        <li><b>Не в мінус (правило ATM).</b> Підказка знижки = частка маржі товару: Старт 25%, Партнер 40%, Золото 50%, Дилер 60% маржі, вниз до цілих 5%. Після знижки має лишитись щонайменше 15 п.п. маржі від роздрібної ціни — CRM сама урізає знижку папки на товарах, де маржі не вистачає.</li>
        <li>Нижче мінімуму — лише виняток на товар, з окремим правом і причиною.</li>
        <li>Товари без собівартості — знижка 0 («немає собівартості»). Тест-набори — без партнерської знижки. Послуги — без правила, тобто 0.</li>
        <li>Ціни товарів не змінюються. Старі угоди не перераховуються. У картці угоди партнера під таблицею товарів видно, скільки маржі лишається, — це лише підказка.</li>
        <li>Автоматична знижка в угодах поки <b>вимкнена</b> — окремий наступний крок після перевірки.</li>
      </ol>
      <b>Затверджені значення (14.09.2026)</b>
      <ul style={{ paddingLeft: 18 }}>
        <li>Старт: покриття WALLCOV 15%, грунти 10%, інструменти 10%.</li>
        <li>Оборот — усі оплачені угоди з 05.05.2026. Маржа — від роздрібної ціни. Підказка — вниз до 5%.</li>
        <li>Чужі бренди — винятками по товару за правилом ATM. Тест-набори — без знижки.</li>
      </ul>
    </div>
  );
}
