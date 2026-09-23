import { useState } from "react";
import InternalMaterialDocuments from "../InternalMaterialDocuments";
import ProductTechnicalFacts, {type Technical} from "./ProductTechnicalFacts";
interface SalesGuide { title: string; intro: string; sections: {title:string;body:string}[]; }
export interface Entry {
  sales_guide?: SalesGuide | null;
  products?: MaterialProduct[];
  id: number; date: string; category?: string; section_key?: string; section?: string;
  title_uk?: string; title_ru?: string; body_uk?: string; body_ru?: string;
  title?: string; body?: string; // legacy fallback
}

interface MaterialProduct { article_url?:string; technical?:Technical; id:number;name:string;price:string;currency:string;unit:string;description:string;short_description:string;full_description:string;benefits:string[];consumption:string|null;instruction_url:string;video_url:string;images:{id:number;url:string;alt_text:string;is_primary:boolean}[]; }
function materialPrice(p:MaterialProduct,lang:string) {
 return Number(p.price)>0?`${Number(p.price).toLocaleString(lang==="uk"?"uk-UA":"ru-RU")} ${p.currency==="UAH"?"грн":p.currency} / ${p.unit}`:(lang==="uk"?"Ціну уточнюємо":"Цену уточняем");
}
function MaterialVariant({p,lang}:{p:MaterialProduct;lang:string}) {
 const [open,setOpen]=useState(false);
 return <details onToggle={e=>setOpen(e.currentTarget.open)} style={{border:"1px solid #e2e8f0",borderRadius:8,padding:"10px 12px",marginTop:8}}>
   <summary style={{cursor:"pointer"}}><span style={{display:"inline-flex",flexWrap:"wrap",justifyContent:"space-between",gap:"4px 12px",width:"calc(100% - 20px)",verticalAlign:"top"}}><b>{p.name}</b><span style={{fontWeight:700,color:"#166534"}}>{materialPrice(p,lang)}</span></span></summary>
   {open&&<ProductLearning p={p} lang={lang}/>}
 </details>;
}
function ProductLearning({p,lang}:{p:MaterialProduct;lang:string}) {
 const uk=lang==="uk";
 const [documentsOpen,setDocumentsOpen]=useState(false);
 const mainText = p.full_description?.trim() || p.description?.trim() || p.short_description?.trim() || "";
 const legacyText = p.description?.trim() && p.description.trim() !== mainText ? p.description.trim() : "";
 return <article style={{borderTop:"1px solid #e2e8f0",paddingTop:12,marginTop:12}}>
 <h4 style={{margin:"0 0 8px"}}>{p.name}</h4>
 <details onToggle={e=>setDocumentsOpen(e.currentTarget.open)} style={{margin:"12px 0"}}><summary style={{cursor:"pointer",fontWeight:700}}>{uk?"Техлисти та документи матеріалу":"Техлисты и документы материала"}</summary>{documentsOpen&&<InternalMaterialDocuments key={`documents:${p.id}:${lang}`} productId={p.id} lang={uk?"uk":"ru"}/>}</details>
 <ProductTechnicalFacts data={p.technical} lang={uk?"uk":"ru"}/>
 <p style={{fontWeight:700,fontSize:17}}>{materialPrice(p,lang)}</p>
 {p.consumption&&<p>{uk?"Витрата":"Расход"}: {Number(p.consumption).toLocaleString("uk-UA")} {p.unit}/м²</p>}
 {!!p.images.length&&<div style={{display:"flex",gap:8,overflowX:"auto",paddingBottom:8}}>{[...p.images].sort((a,b)=>Number(b.is_primary)-Number(a.is_primary)).map(im=><a key={im.id} href={im.url} target="_blank" rel="noreferrer"><img src={im.url} alt={im.alt_text||p.name} loading="lazy" style={{width:210,height:160,objectFit:"contain",borderRadius:8,background:"#f8fafc"}}/></a>)}</div>}
 {mainText && <div style={{fontSize:14,color:"#475569"}}>{mainText.split(/\n\s*\n/).filter(Boolean).map((section,index)=>{
   const lines=section.split("\n");
   const title=lines[0].trim();
   const hasHeading=lines.length>1 && title.length<=110 && !/[.!?;]$/.test(title) && !/^[-•]/.test(title);
   return <section key={index} style={{marginTop:14}}>{hasHeading?<><h5 style={{fontSize:16,color:"#0f172a",margin:"0 0 8px"}}>{title}</h5>{lines.slice(1).map((line,i)=>renderLine(line,i))}</>:lines.map((line,i)=>renderLine(line,i))}</section>;
 })}</div>}
 {legacyText && <details style={{marginTop:12}}><summary style={{cursor:"pointer",fontWeight:700}}>{uk?"Додаткові відомості про матеріал":"Дополнительные сведения о материале"}</summary><div>{legacyText.split("\n").map((line,i)=>renderLine(line,i))}</div></details>}
 {!!p.benefits?.length&&<ul>{p.benefits.map((b,i)=><li key={i}>{b}</li>)}</ul>}
 <div style={{display:"flex",gap:12,flexWrap:"wrap",marginTop:10}}><a href={`/warehouse?product=${p.id}`} target="_blank" rel="noreferrer">{uk?"Картка товару":"Карточка товара"}</a>{p.article_url&&/^https:\/\/wallcov\.com\.ua\//.test(p.article_url)&&<a href={p.article_url} target="_blank" rel="noreferrer">{uk?"Стаття для клієнта":"Статья для клиента"}</a>}{p.instruction_url&&/^https?:/.test(p.instruction_url)&&<a href={p.instruction_url} target="_blank" rel="noreferrer">{uk?"Інструкція":"Инструкция"}</a>}{p.video_url&&/^https?:/.test(p.video_url)&&<a href={p.video_url} target="_blank" rel="noreferrer">{uk?"Відео нанесення":"Видео нанесения"}</a>}</div>
 </article>;
}

function renderLine(line: string, key: number) {
  const img = line.trim().match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
  if (img) {
    return (
      <a key={key} href={img[2]} target="_blank" rel="noreferrer" style={{ display: "block", margin: "10px 0" }}>
        <img src={img[2]} alt={img[1]} loading="lazy" style={{ maxWidth: "100%", borderRadius: 10, border: "1px solid #e2e8f0", boxShadow: "0 1px 4px rgba(0,0,0,.08)", cursor: "zoom-in" }} />
        {img[1] && <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>{img[1]}</div>}
      </a>
    );
  }
  const isBullet = line.trimStart().startsWith("- ");
  const text = isBullet ? line.trimStart().slice(2) : line;
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  const spans = parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <b key={i} style={{ color: "#0f172a" }}>{p.slice(2, -2)}</b>
      : <span key={i}>{p}</span>
  );
  if (isBullet) {
    return (
      <div key={key} style={{ display: "flex", gap: 8, margin: "3px 0", lineHeight: 1.5 }}>
        <span style={{ color: "var(--brand, #C67D5F)", flexShrink: 0 }}>•</span>
        <span>{spans}</span>
      </div>
    );
  }
  return <div key={key} style={{ margin: "6px 0", lineHeight: 1.5 }}>{spans}</div>;
}

export function MaterialTraining({ items, lang }: { items: Entry[]; lang: string }) {
  const [category, setCategory] = useState("");
  const [brand, setBrand] = useState("");
  const [topCategory, setTopCategory] = useState("");
  const [query, setQuery] = useState("");
  const uk = lang === "uk";
  const categories = [
    { key: "topciment", label: "TOPCIMENT" },
    { key: "decor", label: uk ? "Декоративні покриття" : "Декоративные покрытия" },
    { key: "paints", label: uk ? "Фарби" : "Краски" },
    { key: "protection", label: uk ? "Захисні покриття" : "Защитные покрытия" },
    { key: "prep", label: uk ? "Ґрунти та підготовка" : "Грунты и подготовка" },
  ];
  const typeOf = (e: Entry) => e.section_key === "materials_anticatura" ? "decor" : (e.section_key || "").replace("materials_", "");
  const titleOf = (e: Entry) => (uk ? e.title_uk : e.title_ru) || e.title || "";
  const normalize = (v: string) => v.toLocaleLowerCase().replace(/[’`ʼ]/g, "'");
  const search = normalize(query.trim()).split(/\s+/).filter(Boolean);
  const topLabels: Record<string,string> = {decor: uk ? "Декоративні покриття" : "Декоративные покрытия", prep: uk ? "Ґрунти та підготовка" : "Грунты и подготовка", protection: uk ? "Захисні покриття" : "Защитные покрытия", other: uk ? "Інші матеріали" : "Другие материалы"};
  const topType = (e:Entry) => e.category && topLabels[e.category] ? e.category : "other";
  const matches = items.filter(e => (!category || typeOf(e) === category) && (!brand || (brand === "anticatura" ? e.section_key === "materials_anticatura" : e.section_key !== "materials_anticatura")) && (category !== "topciment" || !topCategory || topType(e) === topCategory) && search.every(word => normalize(titleOf(e) + " " + (e.products||[]).map(p=>[p.name,p.description,p.short_description,p.full_description,...(p.benefits||[])].join(" ")).join(" ")).includes(word)));
  return <section className="panel" aria-label={uk ? "Навчання матеріалам" : "Обучение материалам"} style={{ marginBottom: 26 }}>
    <h2 style={{ marginTop: 0 }}>🎨 {uk ? "Матеріали · адаптація та навчання" : "Материалы · адаптация и обучение"}</h2>
    <p>{uk ? "Знайдіть матеріал, вивчіть його застосування та потренуйтеся пояснювати користь клієнту." : "Найдите материал, изучите его применение и потренируйтесь объяснять пользу клиенту."}</p>
    <ol style={{ lineHeight: 1.7, paddingLeft: 22 }}>
      <li>{uk ? "Оберіть категорію та відкрийте потрібний матеріал." : "Выберите категорию и откройте нужный материал."}</li>
      <li>{uk ? "Вивчіть: де застосовувати, як підготувати основу, які шари наносити та що отримує клієнт." : "Изучите: где применять, как подготовить основание, какие слои наносить и что получает клиент."}</li>
      <li>{uk ? "Пройдіть самоперевірку в кінці картки. Перед рекомендацією звірте техкарту та зразок." : "Пройдите самопроверку в конце карточки. Перед рекомендацией сверьте техкарту и образец."}</li>
    </ol>
    <input aria-label={uk ? "Пошук матеріалів" : "Поиск материалов"} placeholder={uk ? "Назва матеріалу, ефект або застосування…" : "Название материала, эффект или применение…"} value={query} onChange={e => setQuery(e.target.value)} style={{ width: "100%", boxSizing: "border-box", padding: 12, border: "1px solid #cbd5e1", borderRadius: 10, marginBottom: 12 }} />
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
      <button aria-pressed={!category} style={chip(!category)} onClick={() => { setCategory(""); setBrand(""); setTopCategory(""); }}>{uk ? "Усі матеріали" : "Все материалы"} · {items.length}</button>
      {categories.map(c => <button key={c.key} aria-pressed={category === c.key} style={chip(category === c.key)} onClick={() => { setCategory(c.key); setBrand(""); setTopCategory(""); }}>{c.label} · {items.filter(e => typeOf(e) === c.key).length}</button>)}
    </div>
    {category === "decor" && <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
      <button style={chip(!brand)} onClick={() => setBrand("")}>{uk ? "Усі декоративні" : "Все декоративные"}</button>
      <button style={chip(brand === "wallcov")} onClick={() => setBrand("wallcov")}>WALLCOV</button>
      <button style={chip(brand === "anticatura")} onClick={() => setBrand("anticatura")}>ANTICATURA</button>
    </div>}
    {category === "topciment" && <div style={{display:"flex",flexWrap:"wrap",gap:8,marginBottom:16}}>
      <button aria-pressed={!topCategory} style={chip(!topCategory)} onClick={()=>setTopCategory("")}>{uk ? "Усі TOPCIMENT" : "Все TOPCIMENT"}</button>
      {Object.entries(topLabels).filter(([key])=>items.some(e=>typeOf(e)==="topciment"&&topType(e)===key)).map(([key,label])=><button key={key} aria-pressed={topCategory===key} style={chip(topCategory===key)} onClick={()=>setTopCategory(key)}>{label}</button>)}
    </div>}
    {!matches.length&&<p>{uk ? "Матеріалів за цим запитом не знайдено." : "Материалов по этому запросу не найдено."} <button className="btn" onClick={()=>{setQuery("");setCategory("");setBrand("");setTopCategory("");}}>{uk ? "Скинути фільтри" : "Сбросить фильтры"}</button></p>}
    <p className="muted">{uk ? "Знайдено" : "Найдено"}: {matches.length}</p>
    {categories.filter(c => !category || category === c.key).map(c => {
      const list = matches.filter(e => typeOf(e) === c.key);
      if (!list.length) return null;
      const sections = c.key === "decor" ? ["wallcov", "anticatura"] : c.key === "topciment" ? Object.keys(topLabels) : [""];
      return <div key={c.key}><h3>{c.label}</h3>{sections.map(b => {
        const entries = list.filter(e => !b || (c.key === "topciment" ? topType(e) === b : (b === "anticatura" ? e.section_key === "materials_anticatura" : e.section_key !== "materials_anticatura"))).sort((a, z) => titleOf(a).localeCompare(titleOf(z), "uk"));
        if (!entries.length) return null;
        return <div key={b}>{b && <h4>{c.key === "topciment" ? topLabels[b] : b === "anticatura" ? "ANTICATURA" : "WALLCOV"}</h4>}{entries.map(e => <details key={e.id} style={{ padding: "12px 14px", border: "1px solid #e2e8f0", borderRadius: 10, marginBottom: 8 }}>
          <summary style={{ cursor: "pointer", fontWeight: 700 }}>{titleOf(e)}</summary>
          {e.sales_guide && <section aria-label={uk?"Як продати матеріал":"Как продать материал"} style={{padding:16,marginTop:16,border:"1px solid #b9d8c5",borderRadius:10,background:"#f5faf7"}}>
            <h4 style={{margin:"0 0 8px"}}>{e.sales_guide.title || (uk?"Як продати матеріал":"Как продать материал")}</h4>
            <p style={{fontSize:13,color:"#475569"}}>{uk?"Для менеджера: підготуйте консультацію. Клієнту надсилайте статтю з бібліотеки.":"Для менеджера: подготовьте консультацию. Клиенту отправляйте статью из библиотеки."}</p>
            {e.sales_guide.intro&&<p>{e.sales_guide.intro}</p>}
            {e.sales_guide.sections.map((section,index)=><details key={index} open={index===0} style={{borderTop:"1px solid #d5e5da",padding:"10px 0"}}>
              <summary style={{cursor:"pointer",fontWeight:700}}>{section.title}</summary>
              <div style={{fontSize:14,lineHeight:1.6}}>{section.body.split("\n").map((line,i)=>renderLine(line,i))}</div>
            </details>)}
          </section>}
          {(e.products?.length||0)>1?<>
            {e.products?.[0].short_description?.trim()&&<div style={{fontSize:14,color:"#475569",margin:"10px 0"}}>{e.products[0].short_description.split("\n").map((line,i)=>renderLine(line,i))}</div>}
            <p className="muted" style={{fontSize:13,margin:"10px 0 6px"}}>{uk?"Оберіть варіант, щоб переглянути опис і фото.":"Выберите вариант, чтобы посмотреть описание и фото."}</p>
            {e.products?.map(p=><MaterialVariant key={p.id} p={p} lang={lang}/>)}
          </>:(e.products||[]).map(p=><ProductLearning key={p.id} p={p} lang={lang}/>)}
          {!e.products?.length&&<p>{uk?"Активних позицій поки немає.":"Активных позиций пока нет."}</p>}
          <div style={{ padding: 12, marginTop: 14, background: "#f8fafc", borderRadius: 8 }}>
            <b>{uk ? "Самоперевірка" : "Самопроверка"}</b>
            <ol style={{ paddingLeft: 20, lineHeight: 1.6 }}>
              <li>{uk ? "Для якої поверхні та задачі підійде цей матеріал?" : "Для какой поверхности и задачи подойдет этот материал?"}</li>
              <li>{uk ? "Які підготовка, шари та захист потрібні? Що ще треба уточнити?" : "Какие подготовка, слои и защита нужны? Что еще нужно уточнить?"}</li>
              <li>{uk ? "Як пояснити користь клієнту двома реченнями без непідтверджених обіцянок?" : "Как объяснить пользу клиенту двумя предложениями без неподтвержденных обещаний?"}</li>
            </ol>
          </div>
        </details>)}</div>;
      })}</div>;
    })}
  </section>;
}

function chip(on: boolean): React.CSSProperties {
  return {
    cursor: "pointer", userSelect: "none", fontSize: 13, fontWeight: 700,
    padding: "6px 13px", borderRadius: 999, whiteSpace: "nowrap",
    background: on ? "var(--brand, #C67D5F)" : "#fff",
    color: on ? "#fff" : "#475569",
    border: "1.5px solid " + (on ? "var(--brand, #C67D5F)" : "#e2e8f0"),
  };
}
