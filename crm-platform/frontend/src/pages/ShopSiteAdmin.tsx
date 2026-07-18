import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../Icon";

type Mode = "content" | "analytics";
type Props = { mode: Mode; onModeChange: (mode: "products" | Mode) => void };

const sectionNames: Record<string, string> = {
  seo: "Поиск Google", hero: "Первый экран", results: "Примеры интерьеров", moods: "Выбор по настроению",
  sample: "Блок пробника", popular: "Популярные товары", process: "Как проходит покупка", faq: "Вопросы и ответы",
  final_cta: "Блок перед подвалом", footer: "Подвал сайта",
};
const labels: Record<string, string> = {
  enabled: "Показывать блок", title: "Заголовок", description: "Описание для Google", eyebrow: "Маленькая надпись над заголовком",
  text: "Текст", primary_text: "Текст главной кнопки", primary_url: "Куда ведёт главная кнопка",
  secondary_text: "Текст второй кнопки", secondary_url: "Куда ведёт вторая кнопка", button_text: "Текст кнопки",
  button_url: "Куда ведёт кнопка", proof: "Строка доверия", image: "Фотография", card_title: "Название на фото",
  card_text: "Описание на фото", label: "Подпись", url: "Ссылка", price: "Цена", phone: "Телефон", note: "Нижняя строка",
  question: "Вопрос", answer: "Ответ",
};
const help: Record<string, string> = {
  title: "Пишите коротко: этот текст должен легко читаться с телефона.", description: "Видно в поисковой выдаче, а не отдельным блоком на странице.",
  image: "Загрузите JPG, PNG или WebP до 10 МБ. После публикации магазин сохранит свою быструю копию.",
  url: "Можно указать внутренний адрес, например /catalog, или полную ссылку.", primary_url: "Например /quiz.", secondary_url: "Например /samples.", button_url: "Например /catalog.",
};
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));

export default function ShopSiteAdmin({ mode, onModeChange }: Props) {
  const { can } = useAuth();
  const canEdit = can("warehouse.edit");
  const [content, setContent] = useState<Record<string, any>>({});
  const [published, setPublished] = useState<Record<string, any>>({});
  const [analytics, setAnalytics] = useState<any>(null);
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const dirty = useMemo(() => JSON.stringify(content) !== JSON.stringify(published), [content, published]);

  async function loadContent() {
    setBusy(true); setMessage("");
    try { const data = await api.get<any>("/api/shop-site/content/"); setContent(data.draft || {}); setPublished(data.published || {}); }
    catch (error: any) { setMessage(error?.data?.detail || "Не удалось загрузить настройки сайта"); }
    finally { setBusy(false); }
  }
  async function loadAnalytics(period = days) {
    setBusy(true); setMessage("");
    try { setAnalytics(await api.get<any>(`/api/shop-site/analytics/?days=${period}`)); }
    catch (error: any) { setMessage(error?.data?.detail || "Не удалось загрузить аналитику"); }
    finally { setBusy(false); }
  }
  useEffect(() => { if (mode === "content") loadContent(); else loadAnalytics(); }, [mode]);

  function change(path: (string | number)[], value: any) {
    const next = clone(content); let cursor: any = next;
    path.slice(0, -1).forEach((key) => { cursor = cursor[key]; }); cursor[path[path.length - 1]] = value; setContent(next);
  }
  async function upload(path: (string | number)[], file?: File) {
    if (!file) return; setBusy(true);
    try { const media = await api.upload<{ url: string }>("/api/shop-site/media/", file); change(path, media.url); setMessage("Фото загружено. Сохраните черновик и опубликуйте изменения."); }
    finally { setBusy(false); }
  }
  async function save() {
    setBusy(true); setMessage("");
    try { await api.patch("/api/shop-site/content/", { content }); setMessage("Черновик сохранён. На сайте пока ничего не изменилось."); }
    catch (error: any) { setMessage(error?.data?.detail || "Не удалось сохранить"); } finally { setBusy(false); }
  }
  async function publish() {
    if (!window.confirm("Опубликовать сохранённые изменения на сайте?")) return;
    setBusy(true); setMessage("");
    try { await api.patch("/api/shop-site/content/", { content }); await api.post("/api/shop-site/publish/", { confirm: true }); setPublished(clone(content)); setMessage("Готово: изменения опубликованы на сайте."); }
    catch (error: any) { setMessage(error?.data?.detail || "Не удалось опубликовать"); } finally { setBusy(false); }
  }

  const nav = <div className="panel" style={{ margin: "18px 0", padding: 8, display: "flex", gap: 7, flexWrap: "wrap" }}>
    <button className="btn btn-light" onClick={() => onModeChange("products")}><Icon n="bag" /> Товары и цены</button>
    <button className={mode === "content" ? "btn btn-primary" : "btn btn-light"} onClick={() => onModeChange("content")}><Icon n="pencil" /> Главная и дизайн</button>
    <button className={mode === "analytics" ? "btn btn-primary" : "btn btn-light"} onClick={() => onModeChange("analytics")}><Icon n="chart" /> Аналитика сайта</button>
  </div>;

  const renderField = (key: string, value: any, path: (string | number)[]) => {
    if (key === "enabled" && typeof value === "boolean") return <label key={key} style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 750 }}><input disabled={!canEdit} type="checkbox" checked={value} onChange={e => change(path, e.target.checked)} />{labels[key]}</label>;
    if (typeof value !== "string") return null;
    const isImage = key === "image";
    const multiline = ["text", "description", "note", "answer", "card_text"].includes(key) || value.length > 90;
    return <label key={key} style={{ display: "block", fontSize: 12, color: "#64748b" }}>
      <b style={{ display: "block", color: "#334155", marginBottom: 5 }}>{labels[key] || key}</b>
      {isImage ? <div style={{ display: "grid", gridTemplateColumns: "100px 1fr", gap: 10, alignItems: "center" }}>
        <img src={value} alt="" style={{ width: 100, height: 74, objectFit: "cover", borderRadius: 8, background: "#f1f5f9" }} />
        <div><input disabled={!canEdit || busy} type="file" accept="image/jpeg,image/png,image/webp" onChange={e => upload(path, e.target.files?.[0])} /><small style={{ display: "block", marginTop: 4 }}>{help[key]}</small></div>
      </div> : multiline ? <textarea disabled={!canEdit} rows={3} value={value} onChange={e => change(path, e.target.value)} style={{ width: "100%" }} /> : <input disabled={!canEdit} value={value} onChange={e => change(path, e.target.value)} style={{ width: "100%", height: 38 }} />}
      {!isImage && help[key] && <small style={{ display: "block", marginTop: 4 }}>{help[key]}</small>}
    </label>;
  };

  if (mode === "analytics") {
    const s = analytics?.summary || {};
    return <div className="scroll fade" style={{ padding: "22px 26px 50px", maxWidth: 1560, margin: "0 auto", width: "100%", minHeight: 0, overflowX: "hidden", WebkitOverflowScrolling: "touch" }}>
      <h1 style={{ margin: 0 }}>Аналитика интернет-магазина</h1><p className="muted">Показывает путь посетителя от просмотра страницы до заказа. Личные данные здесь не собираются.</p>{nav}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>{[7, 30, 90].map(n => <button key={n} className={days === n ? "btn btn-primary" : "btn btn-light"} onClick={() => { setDays(n); loadAnalytics(n); }}>{n} дней</button>)}</div>
      {message && <div className="panel" style={{ padding: 14, color: "#b45309" }}>{message}</div>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 12 }}>{[["Посещения",s.views],["Посетители",s.visitors],["Просмотры товаров",s.product_views],["Добавили в корзину",s.add_to_cart],["Начали оформление",s.checkout_started],["Заказы",s.orders],["Конверсия",`${s.conversion || 0}%`],["Выручка",`${Number(s.revenue || 0).toLocaleString("uk-UA")} ₴`]].map(([label,value])=><div className="panel" style={{padding:17,margin:0}} key={String(label)}><small className="muted">{label}</small><div style={{fontSize:28,fontWeight:850,marginTop:7}}>{value}</div></div>)}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 14, marginTop: 15 }}>
        <SimpleTable title="Популярные страницы" rows={analytics?.top_pages || []} nameKey="path" valueKey="views" />
        <SimpleTable title="Популярные товары" rows={analytics?.top_products || []} nameKey="name" valueKey="views" />
        <SimpleTable title="Откуда приходят" rows={analytics?.sources || []} nameKey="source" valueKey="views" />
      </div>
    </div>;
  }

  return <div className="scroll fade" style={{ padding: "22px 26px 60px", maxWidth: 1280, margin: "0 auto", width: "100%", minHeight: 0, overflowX: "hidden", WebkitOverflowScrolling: "touch" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 14, flexWrap: "wrap" }}><div><h1 style={{ margin: 0 }}>Главная страница и дизайн</h1><p className="muted">Измените нужный блок, сохраните черновик, проверьте и только затем нажмите «Опубликовать».</p></div><a className="btn btn-light" href="https://wallcov.com.ua/" target="_blank" rel="noreferrer"><Icon n="eye" /> Открыть сайт</a></div>
    {nav}{message && <div className="panel" style={{ padding: 14, color: message.startsWith("Готово") ? "#15803d" : "#475569" }}>{message}</div>}
    {Object.entries(content).map(([sectionKey, section]: [string, any]) => <section className="panel" key={sectionKey} style={{ padding: 18, margin: "0 0 13px" }}>
      <h2 style={{ margin: "0 0 5px" }}>{sectionNames[sectionKey] || sectionKey}</h2><p className="muted" style={{ marginTop: 0, fontSize: 13 }}>Все поля этого блока независимы. Можно скрыть блок целиком, не удаляя текст.</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 13 }}>{Object.entries(section).filter(([,v]) => !Array.isArray(v)).map(([key,value]) => renderField(key,value,[sectionKey,key]))}</div>
      {Object.entries(section).filter(([,v]) => Array.isArray(v)).map(([listKey,items]: [string,any]) => <div key={listKey} style={{ marginTop: 15 }}><b>{listKey === "steps" ? "Шаги" : listKey === "items" ? "Карточки блока" : listKey}</b><div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(270px,1fr))",gap:10,marginTop:8}}>{items.map((item:any,index:number)=><div key={index} style={{border:"1px solid #e2e8f0",padding:12,borderRadius:10,display:"grid",gap:9}}><strong>Карточка {index+1}</strong>{Object.entries(item).map(([key,value])=>renderField(key,value,[sectionKey,listKey,index,key]))}</div>)}</div></div>)}
    </section>)}
    <div style={{ position: "sticky", bottom: 12, display: "flex", justifyContent: "flex-end", gap: 9, background: "rgba(255,255,255,.94)", padding: 12, border: "1px solid #e2e8f0", borderRadius: 12 }}><span style={{marginRight:"auto",alignSelf:"center",color:dirty?"#b45309":"#15803d"}}>{dirty ? "Есть неопубликованные изменения" : "Сайт и редактор совпадают"}</span><button disabled={!canEdit || busy} className="btn btn-light" onClick={save}>Сохранить черновик</button><button disabled={!canEdit || busy} className="btn btn-primary" onClick={publish}>Опубликовать на сайте</button></div>
  </div>;
}

function SimpleTable({ title, rows, nameKey, valueKey }: { title: string; rows: any[]; nameKey: string; valueKey: string }) {
  return <div className="panel" style={{padding:16,margin:0}}><h3 style={{marginTop:0}}>{title}</h3>{rows.length ? rows.map((row,index)=><div key={index} style={{display:"flex",justifyContent:"space-between",gap:12,padding:"9px 0",borderTop:"1px solid #e2e8f0"}}><span>{row[nameKey] || "Без названия"}</span><b>{row[valueKey]}</b></div>) : <p className="muted">Данные появятся после посещений нового сайта.</p>}</div>;
}
