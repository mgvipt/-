import { useEffect, useState } from "react";
import { api } from "../api";
import { MaterialTraining, type Entry } from "./MaterialTraining";
type Instruction = {slug:string;title:string;description:string;cover_url:string;public_url:string;article_url:string;version:number;updated_at:string};
export function InstructionLibrary({conversationId,onInsertText,onClose,onBack}:{conversationId:number;onInsertText?:(text:string)=>void;onClose:()=>void;onBack:()=>void}) {
 const [lang,setLang]=useState<"uk"|"ru">("uk");
 const uk=lang==="uk";
 const [items,setItems]=useState<Instruction[]>([]),[error,setError]=useState(""),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const [query,setQuery]=useState("");
 const [training,setTraining]=useState<Entry[]>([]),[mode,setMode]=useState<"training"|"client">("training");
 useEffect(()=>{let alive=true,version=""; setLoading(true); const refresh=()=>api.get<{items?:Instruction[];training?:Entry[];unchanged?:boolean;version?:string}>(`/api/content-library/instructions/?lang=${lang}&version=${version}`).then(r=>{if(alive){if(!r.unchanged){setItems(r.items||[]);setTraining(r.training||[]);}version=r.version||"";setError("");}}).catch(()=>{if(alive)setError(uk?"Не вдалося оновити інструкції. Перевірте з’єднання.":"Не удалось обновить инструкции. Проверьте соединение.");}).finally(()=>{if(alive)setLoading(false);}); refresh(); const timer=window.setInterval(()=>{if(document.visibilityState==="visible")refresh();},15000); window.addEventListener("focus",refresh);return()=>{alive=false;window.clearInterval(timer);window.removeEventListener("focus",refresh);};},[lang]);
 const visibleItems=items.filter(i=>query.toLowerCase().trim().split(/\s+/).every(w=>`${i.title} ${i.description}`.toLowerCase().includes(w)));
 async function insert(slug:string){setBusy(true);setError("");try{const r=await api.post<{text:string}>(`/api/conversations/${conversationId}/prepare-instruction/`,{instruction_slug:slug,lang});onInsertText?.(r.text);onClose();}catch{setError(uk?"Не вдалося вставити інструкцію. Спробуйте ще раз.":"Не удалось вставить инструкцию. Попробуйте ещё раз.");}finally{setBusy(false);}}
 return <div style={{position:"absolute",zIndex:50,left:0,bottom:46,width:720,maxWidth:"calc(100vw - 24px)",maxHeight:"min(680px, calc(100vh - 150px))",overflowY:"auto",background:"white",border:"1px solid #cbd5e1",borderRadius:12,padding:14,boxShadow:"0 12px 32px #0f172a33"}}>
 <div style={{display:"flex",gap:10,alignItems:"center",position:"sticky",top:-14,background:"white",zIndex:1,padding:"10px 0",flexWrap:"wrap"}}><button className="btn" onClick={onBack} aria-label={uk?"Назад до бібліотеки":"Назад в библиотеку"}>←</button><b>{uk?"Бібліотека · Інструкції":"Библиотека · Инструкции"}</b><button className="btn" style={{marginLeft:"auto"}} onClick={onClose} aria-label={uk?"Закрити":"Закрыть"}>×</button></div>
 <div role="group" aria-label={uk?"Мова описів":"Язык описаний"} style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:8}}>{(["uk","ru"] as const).map(l=><button key={l} disabled={busy} aria-pressed={lang===l} className={lang===l?"btn btn-primary":"btn"} onClick={()=>{if(l!==lang){setLoading(true);setQuery("");setLang(l);}}}>{l==="uk"?"Українська":"Русский"}</button>)}</div>
 <div style={{display:"flex",gap:8,margin:"12px 0",flexWrap:"wrap"}}><button className={mode==="training"?"btn btn-primary":"btn"} onClick={()=>setMode("training")}>{uk?"Навчання матеріалам":"Обучение материалам"}</button><button className={mode==="client"?"btn btn-primary":"btn"} onClick={()=>setMode("client")}>{uk?"Інструкції для клієнта":"Инструкции для клиента"}</button></div>
 {mode==="client"&&<><p className="muted">{uk?"Знайдіть матеріал, перегляньте статтю та вставте посилання в повідомлення клієнту.":"Найдите материал, просмотрите статью и вставьте ссылку в сообщение клиенту."}</p><input aria-label={uk?"Пошук інструкцій для клієнта":"Поиск инструкций для клиента"} value={query} onChange={e=>setQuery(e.target.value)} placeholder={uk?"Назва матеріалу або застосування…":"Название материала или применение…"} style={{width:"100%",boxSizing:"border-box",padding:10,marginBottom:12}}/></>}
 {loading&&<p role="status">{uk?"Завантаження…":"Загрузка…"}</p>}{error&&<p role="alert" style={{color:"#b91c1c"}}>{error}</p>}
 {!loading&&!error&&mode==="training"&&<MaterialTraining items={training} lang={lang}/>}
 {!loading&&!error&&mode==="client"&&items.length===0&&<p>{uk?"Опублікованих інструкцій поки немає.":"Опубликованных инструкций пока нет."}</p>}
 {!loading&&!error&&mode==="client"&&items.length>0&&!visibleItems.length&&<p>{uk?"За цим запитом інструкцій не знайдено.":"По этому запросу инструкций не найдено."} <button className="btn" onClick={()=>setQuery("")}>{uk?"Скинути пошук":"Сбросить поиск"}</button></p>}
 {!loading&&!error&&mode==="client"&&visibleItems.map(i=><article key={i.slug} style={{borderTop:"1px solid #e2e8f0",paddingTop:12}}>
 {i.cover_url&&<img src={i.cover_url} alt={i.title} style={{width:"100%",height:155,objectFit:"cover",borderRadius:8}}/>}<h3>{i.title}</h3><p>{i.description}</p>
 <small className="muted">{uk?"Версія":"Версия"} {i.version} · {new Date(i.updated_at).toLocaleDateString(uk?"uk-UA":"ru-RU")}</small>
 <div style={{display:"flex",gap:10,flexWrap:"wrap",marginTop:12}}><a href={i.public_url} target="_blank" rel="noreferrer" className="btn">{uk?"Переглянути":"Просмотреть"}</a><a href={i.article_url} target="_blank" rel="noreferrer" className="btn">{uk?"Стаття":"Статья"}</a><button disabled={busy||!onInsertText} onClick={()=>insert(i.slug)} className="btn btn-primary">{busy?(uk?"Вставляємо…":"Вставляем…"):(uk?"Вставити в чат":"Вставить в чат")}</button></div>
 </article>)}
 </div>;
}
