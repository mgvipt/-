import { useEffect, useState } from "react";
import { api } from "../api";

type Choice = { id: number; name: string; sku?: string };
type Product = Choice & { price: string; currency: string; unit: string; consumption_per_m2: string | null; description: string };
type Material = {
  id: number; kind: string; target_id: number; title: string; state: string; state_label: string;
  issues: string[]; version: string; approval_current: boolean; planned_on: string | null; note: string;
  editor_tab: string; blog_id: number; published: Record<string, { permalink?: string; id?: string; share_id?: string }>;
};
type Campaign = {
  id: number; title: string; goal: string; audience: string; offer: string; blog_id: number; blog_name: string;
  product_id: number; product_snapshot: { captured_at: string; product: Product }; product_current: Product;
  product_changed: boolean; starts_on: string | null; ends_on: string | null; budget_usd: string | null;
  archived: boolean; revision: number; state: string; ready: number; total: number; materials: Material[]; budget_note: string;
};
type EditorTarget = { tab: string; id: number; blogId: number };
type Props = { blogId: number | null; onOpen: (target: EditorTarget) => void };
const base = "/api/content-factory/campaigns/";
const kindNames: Record<string, string> = { reel: "Ролик", carousel: "Карусель", post: "Telegram-пост" };

function errorText(e: unknown): string {
  const data = (e as { data?: unknown })?.data;
  if (typeof data === "string") return data;
  if (data && typeof data === "object") return Object.values(data).flat().join(" · ");
  return "Не удалось сохранить. Проверьте соединение и повторите.";
}

export default function ContentCampaigns({ blogId, onOpen }: Props) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    api.get<{ campaigns: Campaign[] }>(base + (blogId ? `?blog=${blogId}` : ""))
      .then(d => { if (active) { setCampaigns(d.campaigns); setError(""); } })
      .catch(e => { if (active) setError(errorText(e)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [blogId, refresh]);
  const campaign = campaigns.find(c => c.id === selected);
  const reload = () => setRefresh(n => n + 1);
  return <section className="cf-campaigns">
    <style>{`
      .cf-campaigns{display:grid;gap:18px}.cf-campaigns h2,.cf-campaigns h3{margin:0 0 10px}
      .cf-campaigns .cc-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
      .cf-campaigns .cc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:14px}
      .cf-campaigns .cc-box{padding:20px;border:1px solid #ffffff24;border-radius:14px;background:var(--panel,#171b21)}
      .cf-campaigns label{display:grid;gap:7px;font-size:13px}.cf-campaigns input,.cf-campaigns textarea,.cf-campaigns select{font:inherit;box-sizing:border-box;width:100%;padding:10px;border:1px solid #ffffff38;border-radius:8px;background:#12161c;color:#f1f1f1}
      .cf-campaigns textarea{min-height:76px;resize:vertical}.cf-campaigns button{cursor:pointer}.cf-campaigns button:disabled{cursor:wait;opacity:.6}
      .cf-campaigns .cc-card{text-align:left;color:inherit}.cf-campaigns .cc-card[aria-pressed=true]{border-color:#e3b85f}
      .cf-campaigns .cc-muted{font-size:13px;opacity:.72;line-height:1.6}.cf-campaigns .cc-warn{color:#ffd483;line-height:1.5}
      .cf-campaigns .cc-check{display:flex;align-items:flex-start;gap:10px;margin:10px 0}.cf-campaigns .cc-check input{width:18px;height:18px;margin:0;flex:none}
      .cf-campaigns progress{width:100%;height:8px;accent-color:#e3b85f}.cf-campaigns .cc-status{font-size:12px;padding:5px 9px;border:1px solid #e3b85f66;border-radius:20px}
      .cf-campaigns .cc-spread{justify-content:space-between}.cf-campaigns .cc-stack{display:grid;gap:14px}
    `}</style>
    <div className="cc-row cc-spread"><div><h2>Кампании</h2><p className="cc-muted">Цель → материалы → проверка → результат публикации</p></div>
      <div className="cc-row"><button className="cf-btn ghost" onClick={reload}>Обновить</button><button className="cf-btn gold" onClick={() => setSelected("new")}>Новая кампания</button></div></div>
    {error && <div className="cf-msg err" role="alert">{error}</div>}
    {loading && <p role="status">Загружаю кампании…</p>}
    <div className="cc-grid">{campaigns.map(c => <button key={c.id} className="cc-box cc-card" aria-pressed={selected === c.id} onClick={() => setSelected(c.id)}>
      <div className="cc-row cc-spread"><strong>{c.title}</strong><span className="cc-status">{c.state}</span></div>
      <p className="cc-muted">{c.goal}</p><progress value={c.ready} max={c.total || 1} aria-label="Готовность материалов" />
      <p className="cc-muted">Готово {c.ready} из {c.total} · {c.blog_name}</p>
    </button>)}</div>
    {!loading && !campaigns.length && selected !== "new" && <div className="cc-box">Создайте кампанию и добавьте в неё существующие материалы или новые черновики.</div>}
    {selected === "new" && <CampaignForm blogId={blogId} onCancel={() => setSelected(null)} onSaved={c => { setSelected(c.id); reload(); }} />}
    {campaign && <CampaignDetail key={campaign.id} campaign={campaign} onChanged={reload} onOpen={onOpen} />}
  </section>;
}

function CampaignForm({ blogId, current, onSaved, onCancel }: { blogId: number | null; current?: Campaign; onSaved: (c: Campaign) => void; onCancel: () => void }) {
  const [query, setQuery] = useState("");
  const [choices, setChoices] = useState<{ products: Choice[]; blogs: Choice[] }>({ products: [], blogs: [] });
  const [form, setForm] = useState({ title: current?.title || "", goal: current?.goal || "", audience: current?.audience || "", offer: current?.offer || "",
    blog_id: String(current?.blog_id || blogId || ""), product_id: String(current?.product_id || ""), starts_on: current?.starts_on || "", ends_on: current?.ends_on || "", budget_usd: current?.budget_usd || "" });
  const [product, setProduct] = useState<Choice | null>(current?.product_current || null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const t = setTimeout(() => api.get<typeof choices>(base + `choices/?q=${encodeURIComponent(query)}`)
      .then(d => { if (active) setChoices(d); }).catch(e => { if (active) setError(errorText(e)); }), 250);
    return () => { active = false; clearTimeout(t); };
  }, [query]);
  const field = (name: keyof typeof form, value: string) => setForm(f => ({ ...f, [name]: value }));
  const products = product && !choices.products.some(p => p.id === product.id) ? [product, ...choices.products] : choices.products;
  return <form className="cc-box cc-stack" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError("");
    const body = { ...form, blog_id: Number(form.blog_id), product_id: Number(form.product_id), starts_on: form.starts_on || null, ends_on: form.ends_on || null, budget_usd: form.budget_usd || null, ...(current ? { revision: current.revision } : {}) };
    try { onSaved(current ? await api.patch<Campaign>(base + `${current.id}/`, body) : await api.post<Campaign>(base, body)); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }}>
    <h3>{current ? "Изменить кампанию" : "Новая кампания"}</h3>
    {error && <p className="cf-msg err" role="alert">{error}</p>}
    <div className="cc-grid">
      <label>Название<input required maxLength={200} value={form.title} onChange={e => field("title", e.target.value)} placeholder="Galatea для дизайнеров" /></label>
      <label>Блог<select required disabled={!!current?.total} value={form.blog_id} onChange={e => field("blog_id", e.target.value)}><option value="">Выберите блог</option>{choices.blogs.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
      <label>Найти товар в CRM<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Название или артикул" /></label>
      <label>Точная карточка товара<select required value={form.product_id} onChange={e => { field("product_id", e.target.value); setProduct(products.find(p => p.id === Number(e.target.value)) || null); }}><option value="">Выберите товар</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}{p.sku ? ` · ${p.sku}` : ""}</option>)}</select></label>
      <label>Цель<textarea required maxLength={500} value={form.goal} onChange={e => field("goal", e.target.value)} placeholder="Получить заявки на подбор образца" /></label>
      <label>Аудитория<textarea required maxLength={300} value={form.audience} onChange={e => field("audience", e.target.value)} placeholder="Дизайнеры интерьера" /></label>
      <label>Предложение<textarea maxLength={500} value={form.offer} onChange={e => field("offer", e.target.value)} /></label>
      <label>Плановый бюджет, $<input type="number" min="0" max="9999999.99" step="0.01" value={form.budget_usd} onChange={e => field("budget_usd", e.target.value)} /></label>
      <label>Начало<input type="date" value={form.starts_on} onChange={e => field("starts_on", e.target.value)} /></label>
      <label>Окончание<input type="date" min={form.starts_on} value={form.ends_on} onChange={e => field("ends_on", e.target.value)} /></label>
    </div><p className="cc-muted">Сохраняется план. Генерация и публикация запускаются отдельно в редакторе материала.</p>
    <div className="cc-row"><button className="cf-btn gold" disabled={busy} type="submit">{busy ? "Сохраняю…" : "Сохранить кампанию"}</button><button className="cf-btn ghost" type="button" onClick={onCancel}>Отмена</button></div>
  </form>;
}

function CampaignDetail({ campaign: c, onChanged, onOpen }: { campaign: Campaign; onChanged: () => void; onOpen: Props["onOpen"] }) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const patch = async (data: Record<string, unknown>) => {
    setBusy(true); setError("");
    try { await api.patch(base + `${c.id}/`, { revision: c.revision, ...data }); onChanged(); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  if (editing) return <CampaignForm key={c.revision} current={c} blogId={c.blog_id} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); onChanged(); }} />;
  const p = c.product_snapshot.product;
  return <div className="cc-stack">
    <div className="cc-box"><div className="cc-row cc-spread"><h3>{c.title}</h3><button className="cf-btn ghost" onClick={() => setEditing(true)}>Изменить</button></div>
      <p><strong>Цель:</strong> {c.goal}</p><p><strong>Для кого:</strong> {c.audience}</p>{c.offer && <p><strong>Предложение:</strong> {c.offer}</p>}
      <p className="cc-muted">{c.starts_on || "Начало не задано"} — {c.ends_on || "Окончание не задано"} · Бюджет: {c.budget_usd === null ? "не задан" : `$${c.budget_usd}`}</p>
      <p className="cc-muted">{c.budget_note}</p>
      <details><summary>Паспорт товара · {p.name}</summary><p>Источник: карточка CRM №{p.id}. Снимок: {new Date(c.product_snapshot.captured_at).toLocaleString("ru-RU")}</p>
        <p>{p.price} {p.currency}/{p.unit} · Расход: {p.consumption_per_m2 ?? "не указан"}{p.consumption_per_m2 ? ` ${p.unit}/м²` : ""}</p><p style={{ whiteSpace: "pre-wrap" }}>{p.description || "Описание в карточке отсутствует."}</p></details>
      {c.product_changed && <p className="cc-warn">Карточка товара изменилась. Обновите паспорт и заново проверьте материалы.</p>}
      {error && <p role="alert" className="cf-msg err">{error}</p>}
      <div className="cc-row"><button className="cf-btn ghost" disabled={busy} onClick={() => patch({ refresh_product: true })}>Обновить паспорт из CRM</button><button className="cf-btn ghost" disabled={busy} onClick={() => patch({ archived: !c.archived })}>{c.archived ? "Вернуть в работу" : "В архив"}</button></div>
    </div>
    {!c.archived && <AddMaterial campaign={c} onChanged={onChanged} onOpen={onOpen} />}
    <h3>Материалы · готово {c.ready} из {c.total}</h3>
    {c.materials.map(m => <MaterialCard key={`${m.id}:${m.version}:${m.approval_current}`} material={m} campaign={c} onChanged={onChanged} onOpen={onOpen} />)}
  </div>;
}

function AddMaterial({ campaign: c, onChanged, onOpen }: { campaign: Campaign; onChanged: () => void; onOpen: Props["onOpen"] }) {
  const [kind, setKind] = useState("reel"); const [title, setTitle] = useState(""); const [date, setDate] = useState("");
  const [mode, setMode] = useState("new"); const [options, setOptions] = useState<{ kind: string; id: number; title: string }[]>([]);
  const [chosen, setChosen] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    if (mode !== "existing") return;
    let active = true;
    const t = setTimeout(() => api.get<{ materials: typeof options }>(base + `${c.id}/materials/?q=${encodeURIComponent(search)}`)
      .then(d => { if (active) setOptions(d.materials); }).catch(e => { if (active) setError(errorText(e)); }), 250);
    return () => { active = false; clearTimeout(t); };
  }, [mode, c.id, search]);
  return <form className="cc-box cc-stack" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError("");
    const selected = options.find(o => `${o.kind}:${o.id}` === chosen);
    try {
      const m = await api.post<Material>(base + `${c.id}/materials/`, { ...(mode === "new" ? { kind, title } : { kind: selected?.kind, target_id: selected?.id }), planned_on: date || null });
      setTitle(""); setChosen(""); setOptions(o => o.filter(v => !(v.kind === m.kind && v.id === m.target_id))); onChanged();
      if (mode === "new") onOpen({ tab: m.editor_tab, id: m.target_id, blogId: c.blog_id });
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }}>
    <h3>Добавить материал</h3><div className="cc-grid">
      <label>Способ<select value={mode} onChange={e => setMode(e.target.value)}><option value="new">Новый черновик</option><option value="existing">Из существующих материалов</option></select></label>
      {mode === "new" ? <><label>Формат<select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(kindNames).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label><label>Название<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label></>
        : <><label>Поиск материала<input value={search} onChange={e => { setSearch(e.target.value); setChosen(""); }} /></label><label>Материал<select required value={chosen} onChange={e => setChosen(e.target.value)}><option value="">Выберите материал</option>{options.map(o => <option key={`${o.kind}:${o.id}`} value={`${o.kind}:${o.id}`}>{kindNames[o.kind]} · {o.title} · №{o.id}</option>)}</select></label></>}
      <label>Плановая дата<input type="date" value={date} onChange={e => setDate(e.target.value)} /></label>
    </div><p className="cc-muted">Плановая дата не включает автопубликацию. Новый черновик откроется в существующем редакторе.</p>
    {error && <p role="alert" className="cf-msg err">{error}</p>}<button type="submit" className="cf-btn gold" disabled={busy}>{mode === "new" ? "Создать и открыть редактор" : "Добавить в кампанию"}</button>
  </form>;
}

function MaterialCard({ material: m, campaign: c, onChanged, onOpen }: { material: Material; campaign: Campaign; onChanged: () => void; onOpen: Props["onOpen"] }) {
  const [checks, setChecks] = useState({ facts: false, visual: false, rights: false });
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [date, setDate] = useState(m.planned_on || ""); const [note, setNote] = useState(m.note);
  const mutate = async (approve: boolean) => {
    setBusy(true); setError("");
    try {
      if (approve) await api.post(base + `${c.id}/materials/${m.id}/`, { version: m.version, checks });
      else await api.patch(base + `${c.id}/materials/${m.id}/`, { planned_on: date || null, note });
      onChanged();
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return <article className="cc-box cc-stack">
    <div className="cc-row cc-spread"><h3>{kindNames[m.kind]} · {m.title}</h3><span className="cc-status">{m.state_label}</span></div>
    <button className="cf-btn ghost" onClick={() => onOpen({ tab: m.editor_tab, id: m.target_id, blogId: m.blog_id })}>Открыть материал №{m.target_id}</button>
    {m.issues.length > 0 && <ul className="cc-warn">{m.issues.map((x, i) => <li key={i}>{x}</li>)}</ul>}
    <div className="cc-grid"><label>Плановая дата<input type="date" value={date} onChange={e => setDate(e.target.value)} /></label><label>Что сделать<input maxLength={1000} value={note} onChange={e => setNote(e.target.value)} /></label></div>
    <button className="cf-btn ghost" disabled={busy} onClick={() => mutate(false)}>Сохранить план</button>
    {!m.approval_current && m.state !== "published" && !c.archived && <div>
      <p>После просмотра текущей версии подтвердите:</p>
      {([["facts", "Факты и предложение проверены по карточке товара"], ["visual", "Каждая фраза соответствует кадру; фактура и оформление проверены"], ["rights", "Права на видео, голос и музыку проверены"]] as const).map(([key, label]) => <label className="cc-check" key={key}><input type="checkbox" checked={checks[key]} onChange={e => setChecks(s => ({ ...s, [key]: e.target.checked }))} />{label}</label>)}
      <button className="cf-btn gold" disabled={busy || m.issues.length > 0 || !Object.values(checks).every(Boolean)} onClick={() => mutate(true)}>Согласовать эту версию</button>
      <p className="cc-muted">Это проверка материала. Публикация запускается отдельно в его редакторе.</p>
    </div>}
    {Object.entries(m.published).map(([platform, info]) => <p key={platform}>{platform}: {info.permalink && /^https:\/\//.test(info.permalink) ? <a href={info.permalink} target="_blank" rel="noreferrer">Открыть публикацию</a> : `зарегистрирована в CRM, ID ${info.id || info.share_id || "не указан"}`}</p>)}
    {error && <p role="alert" className="cf-msg err">{error}</p>}
  </article>;
}
