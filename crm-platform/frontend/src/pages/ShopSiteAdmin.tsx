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
const pageSectionOrder = ["hero", "results", "moods", "sample", "popular", "process", "faq", "final_cta", "footer", "seo"];
const sectionHints: Record<string, string> = {
  hero: "Первое, что видит покупатель: главное обещание, фото и кнопки.",
  results: "Фотографии готовых интерьеров и короткие пояснения.",
  moods: "Помогает выбрать покрытие не по сложному названию, а по ощущению.",
  sample: "Объясняет, зачем начать с пробника и как его заказать.",
  popular: "Подборка покрытий, которые чаще всего выбирают покупатели.",
  process: "Показывает путь от выбора до готовой стены.",
  faq: "Ответы на сомнения перед заказом.",
  final_cta: "Последнее понятное предложение помощи перед подвалом.",
  footer: "Контакты, ссылки и служебная информация внизу сайта.",
  seo: "Служебное название и описание для поисковой выдачи Google.",
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
  const [selectedSection, setSelectedSection] = useState("hero");
  const [previewDevice, setPreviewDevice] = useState<"desktop" | "mobile">("desktop");
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

  const orderedSections = pageSectionOrder.filter(key => content[key]);
  const activeKey = content[selectedSection] ? selectedSection : orderedSections[0];
  const activeSection = content[activeKey] || {};

  return <div className="scroll fade" style={{ padding: "18px 20px 86px", width: "100%", minHeight: 0, overflowX: "hidden", WebkitOverflowScrolling: "touch", background: "#f4f1ec" }}>
    <div style={{ maxWidth: 1660, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 14, flexWrap: "wrap", alignItems: "flex-start" }}><div><h1 style={{ margin: 0 }}>Редактор главной страницы</h1><p className="muted" style={{ margin: "5px 0 0" }}>Выберите блок слева или прямо в макете сайта. В настройках откроются только его тексты, кнопки и фотографии.</p></div><a className="btn btn-light" href="https://wallcov.com.ua/" target="_blank" rel="noreferrer"><Icon n="eye" /> Открыть настоящий сайт</a></div>
      {nav}{message && <div className="panel" style={{ padding: 14, color: message.startsWith("Готово") ? "#15803d" : "#475569" }}>{message}</div>}

      <div style={{ display: "flex", gap: 14, alignItems: "flex-start", flexWrap: "wrap" }}>
        <aside className="panel" style={{ flex: "0 1 220px", minWidth: 205, padding: 10, margin: 0, position: "sticky", top: 10 }}>
          <b style={{ display: "block", padding: "7px 8px 10px" }}>Структура страницы</b>
          {orderedSections.map((key, index) => { const section = content[key] || {}; const active = key === activeKey; return <button key={key} onClick={() => setSelectedSection(key)} style={{ width: "100%", border: active ? "1px solid #c67d5f" : "1px solid transparent", background: active ? "#fff4ee" : "transparent", borderRadius: 10, padding: "9px 10px", display: "flex", gap: 9, textAlign: "left", cursor: "pointer", marginBottom: 4, color: "#1e293b" }}><span style={{ width: 24, height: 24, borderRadius: 12, display: "grid", placeItems: "center", background: active ? "#c67d5f" : "#eef2f7", color: active ? "white" : "#64748b", fontSize: 11, flexShrink: 0 }}>{key === "seo" ? "G" : index + 1}</span><span style={{ minWidth: 0 }}><b style={{ display: "block", fontSize: 12.5 }}>{sectionNames[key] || key}</b><small style={{ color: section.enabled === false ? "#b91c1c" : "#15803d" }}>{section.enabled === false ? "Скрыто" : key === "seo" ? "Для Google" : "Видно на сайте"}</small></span></button>; })}
        </aside>

        <section style={{ flex: "1 1 430px", minWidth: 330 }}>
          <div className="panel" style={{ margin: 0, padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", flexWrap: "wrap" }}><div><small style={{ color: "#c67d5f", fontWeight: 800 }}>НАСТРОЙКИ ВЫБРАННОГО БЛОКА</small><h2 style={{ margin: "4px 0" }}>{sectionNames[activeKey] || activeKey}</h2><p className="muted" style={{ margin: 0, fontSize: 13 }}>{sectionHints[activeKey]}</p></div>{typeof activeSection.enabled === "boolean" && <label style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 10px", borderRadius: 9, background: activeSection.enabled ? "#ecfdf5" : "#fef2f2", fontWeight: 750 }}><input disabled={!canEdit} type="checkbox" checked={activeSection.enabled} onChange={e => change([activeKey,"enabled"],e.target.checked)} />{activeSection.enabled ? "Видно на сайте" : "Блок скрыт"}</label>}</div>
            <div style={{ height: 1, background: "#e2e8f0", margin: "16px 0" }} />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(245px,1fr))", gap: 13 }}>{Object.entries(activeSection).filter(([key,v]) => key !== "enabled" && !Array.isArray(v)).map(([key,value]) => renderField(key,value,[activeKey,key]))}</div>
            {Object.entries(activeSection).filter(([,v]) => Array.isArray(v)).map(([listKey,items]: [string,any]) => <div key={listKey} style={{ marginTop: 18 }}><b>{listKey === "steps" ? "Шаги блока" : listKey === "items" ? "Карточки блока" : "Элементы блока"}</b><p className="muted" style={{ fontSize: 12, margin: "3px 0 9px" }}>Каждая карточка сразу обновляется в макете справа.</p><div style={{display:"grid",gap:9}}>{items.map((item:any,index:number)=><details key={index} open={index===0} style={{border:"1px solid #e2e8f0",padding:11,borderRadius:10,background:"#fafafa"}}><summary style={{cursor:"pointer",fontWeight:750}}>Карточка {index+1}{item.title ? ` · ${item.title}` : item.question ? ` · ${item.question}` : ""}</summary><div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:10,marginTop:11}}>{Object.entries(item).map(([key,value])=>renderField(key,value,[activeKey,listKey,index,key]))}</div></details>)}</div></div>)}
          </div>
        </section>

        <aside style={{ flex: "1 1 360px", minWidth: 330, position: "sticky", top: 10 }}>
          <div className="panel" style={{ margin: 0, padding: 12, background: "#e9e6e1" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", marginBottom: 10 }}><b>Так страницу видит покупатель</b><div style={{ display: "flex", gap: 5 }}><button className={previewDevice === "desktop" ? "btn btn-primary" : "btn btn-light"} onClick={() => setPreviewDevice("desktop")}>Компьютер</button><button className={previewDevice === "mobile" ? "btn btn-primary" : "btn btn-light"} onClick={() => setPreviewDevice("mobile")}>Телефон</button></div></div>
            <div style={{ width: previewDevice === "mobile" ? 330 : "100%", maxWidth: "100%", margin: "0 auto", height: 610, overflowY: "auto", background: "#fbf8f3", border: "1px solid #d8d1c7", borderRadius: previewDevice === "mobile" ? 24 : 8, boxShadow: "0 12px 30px rgba(51,41,31,.14)" }}>
              <div style={{ padding: "10px 14px", display: "flex", justifyContent: "space-between", borderBottom: "1px solid #e7e0d7", fontFamily: "Georgia,serif" }}><b>Wallcov</b><small>Каталог · Пробники</small></div>
              {orderedSections.filter(key => key !== "seo").map(key => <PreviewBlock key={key} sectionKey={key} section={content[key] || {}} active={key === activeKey} onSelect={() => setSelectedSection(key)} mobile={previewDevice === "mobile"} />)}
            </div>
            <small style={{ display: "block", color: "#64748b", marginTop: 8 }}>Нажмите на любой блок в макете — его настройки откроются слева.</small>
          </div>
        </aside>
      </div>
    </div>
    <div style={{ position: "fixed", left: "clamp(12px, 14vw, 230px)", right: 18, bottom: 12, zIndex: 25, display: "flex", justifyContent: "flex-end", gap: 9, background: "rgba(255,255,255,.96)", boxShadow: "0 8px 30px rgba(15,23,42,.18)", padding: 12, border: "1px solid #e2e8f0", borderRadius: 12, flexWrap: "wrap" }}><span style={{marginRight:"auto",alignSelf:"center",color:dirty?"#b45309":"#15803d",fontWeight:700}}>{dirty ? "Есть изменения — сайт пока не изменён" : "Опубликованная версия и редактор совпадают"}</span>{dirty && <button disabled={busy} className="btn btn-light" onClick={() => setContent(clone(published))}>Отменить изменения</button>}<button disabled={!canEdit || busy} className="btn btn-light" onClick={save}>Сохранить черновик</button><button disabled={!canEdit || busy} className="btn btn-primary" onClick={publish}>Опубликовать на сайте</button></div>
  </div>;
}

function PreviewBlock({ sectionKey, section, active, onSelect, mobile }: { sectionKey: string; section: any; active: boolean; onSelect: () => void; mobile: boolean }) {
  const items = Array.isArray(section.items) ? section.items : Array.isArray(section.steps) ? section.steps : [];
  const image = section.image || items.find((item: any) => item?.image)?.image;
  const hidden = section.enabled === false;
  return <button onClick={onSelect} style={{ width: "100%", display: "block", border: active ? "3px solid #c67d5f" : "3px solid transparent", padding: 0, textAlign: "left", background: hidden ? "#f1f5f9" : "#fbf8f3", color: "#2f2a25", cursor: "pointer", opacity: hidden ? .55 : 1, position: "relative" }}>
    <span style={{ position: "absolute", top: 7, right: 7, zIndex: 2, background: active ? "#c67d5f" : "rgba(255,255,255,.9)", color: active ? "white" : "#475569", padding: "3px 7px", borderRadius: 9, fontSize: 9, fontWeight: 800 }}>{hidden ? "СКРЫТО" : active ? "НАСТРАИВАЕТСЯ" : "ИЗМЕНИТЬ"}</span>
    {sectionKey === "hero" ? <div style={{ minHeight: mobile ? 250 : 290, padding: mobile ? 22 : 34, display: "flex", flexDirection: "column", justifyContent: "flex-end", background: image ? `linear-gradient(0deg,rgba(31,25,21,.62),rgba(31,25,21,.08)),url(${image}) center/cover` : "linear-gradient(135deg,#ded3c7,#f4ece3)", color: image ? "white" : "#2f2a25" }}><small>{section.eyebrow}</small><strong style={{ fontFamily: "Georgia,serif", fontSize: mobile ? 26 : 34, lineHeight: 1.02, maxWidth: 470 }}>{section.title || "Заголовок первого экрана"}</strong><span style={{ marginTop: 8, fontSize: 11, maxWidth: 420 }}>{section.text}</span><span style={{ marginTop: 12, display: "inline-block", background: "#c67d5f", color: "white", padding: "8px 12px", width: "fit-content", fontSize: 10 }}>{section.primary_text || section.button_text || "Кнопка"}</span></div> :
    sectionKey === "final_cta" ? <div style={{ padding: mobile ? 23 : 30, background: "#5f7565", color: "white", textAlign: "center" }}><small>{section.eyebrow}</small><h3 style={{ fontFamily: "Georgia,serif", margin: "5px 0" }}>{section.title}</h3><p style={{ fontSize: 11 }}>{section.text}</p><span style={{ display: "inline-block", background: "#fff", color: "#2f2a25", padding: "7px 11px", fontSize: 10 }}>{section.button_text || "Получить помощь"}</span></div> :
    sectionKey === "footer" ? <div style={{ padding: 20, background: "#302a25", color: "white" }}><b style={{ fontFamily: "Georgia,serif" }}>Wallcov</b><p style={{ fontSize: 10, opacity: .8, maxWidth: 300 }}>{section.text || section.note}</p><small>{section.phone}</small></div> :
    <div style={{ padding: mobile ? 18 : 24 }}><small style={{ color: "#9a6a55" }}>{section.eyebrow || sectionNames[sectionKey]}</small><h3 style={{ fontFamily: "Georgia,serif", fontSize: mobile ? 21 : 25, margin: "4px 0 9px" }}>{section.title || sectionNames[sectionKey]}</h3>{section.text && <p style={{ fontSize: 11, color: "#6b665f" }}>{section.text}</p>}{image && <img src={image} alt="" style={{ width: "100%", height: mobile ? 120 : 150, objectFit: "cover", marginBottom: 9 }} />}{items.length > 0 && <div style={{ display: "grid", gridTemplateColumns: mobile ? "1fr" : `repeat(${Math.min(items.length,3)},1fr)`, gap: 7 }}>{items.slice(0,4).map((item:any,index:number)=><div key={index} style={{ border: "1px solid #e4ddd4", background: "white", padding: 9, minHeight: 54 }}><b style={{ fontSize: 10 }}>{item.title || item.question || item.label || `Карточка ${index+1}`}</b><p style={{ fontSize: 9, margin: "4px 0 0", color: "#746f68" }}>{item.text || item.answer || item.description}</p></div>)}</div>}</div>}
  </button>;
}

function SimpleTable({ title, rows, nameKey, valueKey }: { title: string; rows: any[]; nameKey: string; valueKey: string }) {
  return <div className="panel" style={{padding:16,margin:0}}><h3 style={{marginTop:0}}>{title}</h3>{rows.length ? rows.map((row,index)=><div key={index} style={{display:"flex",justifyContent:"space-between",gap:12,padding:"9px 0",borderTop:"1px solid #e2e8f0"}}><span>{row[nameKey] || "Без названия"}</span><b>{row[valueKey]}</b></div>) : <p className="muted">Данные появятся после посещений нового сайта.</p>}</div>;
}
