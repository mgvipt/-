import { useEffect, useState } from "react";
import { api } from "../api";
import { MaterialTraining, type Entry } from "./MaterialTraining";
type Instruction = {slug:string;title:string;description:string;cover_url:string;public_url:string;article_url:string;version:number;updated_at:string};
export function InstructionLibrary({conversationId,onInsertText,onClose,onBack}:{conversationId:number;onInsertText?:(text:string)=>void;onClose:()=>void;onBack:()=>void}) {
 const [items,setItems]=useState<Instruction[]>([]),[error,setError]=useState(""),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const [training,setTraining]=useState<Entry[]>([]),[mode,setMode]=useState<"training"|"client">("training");
 useEffect(()=>{let alive=true; const refresh=()=>api.get<{items:Instruction[];training?:Entry[]}>("/api/content-library/instructions/").then(r=>{if(alive){setItems(r.items);setTraining(r.training||[]);setError("");}}).catch(()=>{if(alive)setError("Не вдалося оновити інструкції. Перевірте з’єднання.");}).finally(()=>{if(alive)setLoading(false);}); refresh(); const timer=window.setInterval(()=>{if(document.visibilityState==="visible")refresh();},15000); window.addEventListener("focus",refresh);return()=>{alive=false;window.clearInterval(timer);window.removeEventListener("focus",refresh);};},[]);
 async function insert(slug:string){setBusy(true);setError("");try{const r=await api.post<{text:string}>(`/api/conversations/${conversationId}/prepare-instruction/`,{instruction_slug:slug});onInsertText?.(r.text);onClose();}catch{setError("Не вдалося вставити інструкцію. Спробуйте ще раз.");}finally{setBusy(false);}}
 return <div style={{position:"absolute",zIndex:50,left:0,bottom:46,width:720,maxWidth:"calc(100vw - 24px)",maxHeight:"min(680px, calc(100vh - 150px))",overflowY:"auto",background:"white",border:"1px solid #cbd5e1",borderRadius:12,padding:14,boxShadow:"0 12px 32px #0f172a33"}}>
 <div style={{display:"flex",gap:10,alignItems:"center"}}><button className="btn" onClick={onBack}>←</button><b>Бібліотека · Інструкції</b><button className="btn" style={{marginLeft:"auto"}} onClick={onClose} aria-label="Закрити">×</button></div>
 <div style={{display:"flex",gap:8,margin:"12px 0",flexWrap:"wrap"}}><button className={mode==="training"?"btn btn-primary":"btn"} onClick={()=>setMode("training")}>Навчання матеріалам</button><button className={mode==="client"?"btn btn-primary":"btn"} onClick={()=>setMode("client")}>Інструкції для клієнта</button></div>
 {mode==="client"&&<p className="muted">Вставте готову картку в повідомлення та надішліть клієнту.</p>}
 {loading&&<p>Завантаження…</p>}{error&&<p role="alert" style={{color:"#b91c1c"}}>{error}</p>}
 {!loading&&!error&&mode==="training"&&<MaterialTraining items={training} lang="uk"/>}
 {!loading&&!error&&mode==="client"&&items.length===0&&<p>Опублікованих інструкцій поки немає.</p>}
 {mode==="client"&&items.map(i=><article key={i.slug} style={{borderTop:"1px solid #e2e8f0",paddingTop:12}}>
 <img src={i.cover_url} alt="AI-візуалізація системи Microcement" style={{width:"100%",height:155,objectFit:"cover",borderRadius:8}}/><h3>{i.title}</h3><p>{i.description}</p>
 <small className="muted">Версія {i.version} · {new Date(i.updated_at).toLocaleDateString("uk-UA")}</small>
 <div style={{display:"flex",gap:10,flexWrap:"wrap",marginTop:12}}><a href={i.public_url} target="_blank" rel="noreferrer" className="btn">Переглянути</a><a href={i.article_url} target="_blank" rel="noreferrer" className="btn">Стаття</a><button disabled={busy||!onInsertText} onClick={()=>insert(i.slug)} className="btn btn-primary">{busy?"Вставляємо…":"Вставити в чат"}</button></div>
 </article>)}
 </div>;
}
