import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { createPortal } from "react-dom";
type ReferenceSource={product_id:number;name:string;date:string|null;eur_uah:string|null};
type Row={key:string;name:string;unit:string;rate:number|null;quantity:number|null;pack:number|null;packs:number|null;purchase_quantity:number|null;pack_price:number|null;subtotal:number|null;reference_prices:ReferenceSource[];needs_review:boolean;products:{id:number;name:string;updated_at:string;source_revisions:string[];needs_review:boolean;review_reasons?:string[];source_urls?:string[]}[]};
type Result={system:string;area:number;reserve:number;basis:string;rows:Row[];known_total:number;complete:boolean;technical_unverified:{key:string;name:string;products:Row["products"]}[];missing:string[];notes:string[];reference_date:string|null;eur_uah:string|null;reference_metadata:{status:"unknown"|"incomplete"|"consistent"|"mixed";sources:ReferenceSource[]};systems:{id:string;name:string;area_type:string;historical:boolean}[]};
const fmt=(n:number|null)=>n===null?"Уточнити":n.toLocaleString("uk-UA",{maximumFractionDigits:3});
const money=(n:number|null)=>n===null?"Ціну уточнюємо":`${n.toLocaleString("uk-UA",{minimumFractionDigits:2,maximumFractionDigits:2})} грн`;
const safeHttps=(value:string)=>{try{const u=new URL(value);return u.protocol==="https:"&&!u.username&&!u.password;}catch{return false;}};
const amount=(n:number|null,unit:string)=>n===null?"Уточнити":`${fmt(n)} ${unit}`;
export function TopcimentCalculator({onBack,onClose}:{onBack:()=>void;onClose:()=>void}) {
 const [area,setArea]=useState("25"),[reserve,setReserve]=useState("10"),[system,setSystem]=useState("sttandard-wall"),[basis,setBasis]=useState("sale");
 const [areaType,setAreaType]=useState("wall"),[substrate,setSubstrate]=useState("");
 const [result,setResult]=useState<Result|null>(null),[error,setError]=useState(""),[loading,setLoading]=useState(false);
 const [systems,setSystems]=useState<Result["systems"]>([]),[resultKey,setResultKey]=useState("");
 const [narrow,setNarrow]=useState(()=>window.innerWidth<760);
 const panel=useRef<HTMLElement>(null);
 const inputKey=JSON.stringify([system,area,reserve,basis,substrate]);
 const stale=!!result&&resultKey!==inputKey;
 useEffect(()=>{const f=()=>setNarrow(window.innerWidth<760);window.addEventListener("resize",f);return()=>window.removeEventListener("resize",f);},[]);
 useEffect(()=>{
   const previous=document.activeElement as HTMLElement|null;
   panel.current?.focus();
   const keys=(e:KeyboardEvent)=>{
     if(e.key!=="Tab")return;
     const nodes=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input,select,a[href],summary,[tabindex="0"]')||[]).filter(el=>el.getClientRects().length>0);
     if(!nodes.length)return;
     const first=nodes[0],last=nodes[nodes.length-1];
     if(e.shiftKey&&(document.activeElement===first||document.activeElement===panel.current)){e.preventDefault();last.focus();}
     else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
   };
   window.addEventListener("keydown",keys);
   return()=>{window.removeEventListener("keydown",keys);if(previous?.isConnected)previous.focus();};
 },[]);
 useEffect(()=>{
   let alive=true,pending=false;
   const load=async()=>{
     if(!alive||pending||document.visibilityState!=="visible")return;
     const a=Number(area),r=Number(reserve);
     if(!area.trim()||!reserve.trim()||!Number.isFinite(a)||a<=0||a>100000||!Number.isFinite(r)||r<0||r>50){setError("Вкажіть площу від 0,01 до 100 000 м² і запас від 0 до 50%.");setLoading(false);return;}
     pending=true;setLoading(true);
     try{
       const data=await api.get<Result>(`/api/content-library/instructions/?calculator=topciment&system=${encodeURIComponent(system)}&area=${encodeURIComponent(area)}&reserve=${encodeURIComponent(reserve)}&basis=${basis}&substrate=${encodeURIComponent(substrate)}`);
       if(alive){setResult(data);setSystems(data.systems);setResultKey(inputKey);setError("");}
     }catch{if(alive)setError("Не вдалося оновити розрахунок. Перевірте з’єднання. Показані нижче дані ще не підтверджені повторно.");}
     finally{pending=false;if(alive)setLoading(false);}
   };
   const delay=window.setTimeout(load,250),timer=window.setInterval(load,15000);
   window.addEventListener("focus",load);document.addEventListener("visibilitychange",load);
   return()=>{alive=false;window.clearTimeout(delay);window.clearInterval(timer);window.removeEventListener("focus",load);document.removeEventListener("visibilitychange",load);};
 },[area,reserve,system,basis,substrate,inputKey]);
 const productLinks=(r:Row)=><div style={{marginTop:5}}>
 {r.needs_review&&<p role="status" style={{color:"#92400e",fontWeight:700}}>Довідковий розрахунок — норму погодити.</p>}
 {result?.basis==="reference"&&r.reference_prices?.map(source=><small key={source.product_id} style={{display:"block",color:"#64748b"}}>{source.name}: {source.date&&source.eur_uah?`ціна перевірена ${source.date}; курс 1 € = ${source.eur_uah} грн.`:"ціну або її курс не підтверджено."}</small>)}
 {r.products.map(p=><div key={p.id} style={{marginTop:6,fontSize:12}}><a href={`/warehouse?product=${p.id}`} target="_blank" rel="noreferrer" style={{display:"block"}}>Картка {p.name}</a>
 {p.needs_review&&<div style={{color:"#92400e"}}><b>Що не вдалося перевірити</b>{(p.review_reasons?.length?p.review_reasons:["Причину потрібно уточнити у відповідального за картку матеріалу."]).map(reason=><p key={reason} style={{margin:"4px 0"}}>{reason}</p>)}</div>}
 {p.source_urls?.filter(safeHttps).map(url=><a key={url} href={url} target="_blank" rel="noreferrer" style={{display:"block"}}>Джерело технічних даних</a>)}
 <span style={{display:"block",color:"#64748b"}}>Оновлено: {p.updated_at?new Date(p.updated_at).toLocaleDateString("uk-UA"):"дату уточнити"}. Документ: {p.source_revisions?.length?p.source_revisions.join(", "):"дату уточнити"}.</span></div>)}
 </div>;

 const rowValues=(r:Row)=>[amount(r.rate,r.unit),amount(r.quantity,r.unit),amount(r.pack,r.unit),fmt(r.packs),amount(r.purchase_quantity,r.unit),money(r.pack_price),money(r.subtotal)];
 const columns=["На м²","Потрібно із запасом","Упаковка / комплект","Кількість упаковок","До закупівлі","Ціна упаковки / комплекту","Сума"];
 return createPortal(<div role="dialog" aria-modal="true" aria-label="Калькулятор TOPCIMENT" style={{position:"fixed",inset:0,zIndex:3000,background:"#0f172a66",display:"grid",placeItems:"center",padding:narrow?6:12}}><section ref={panel} tabIndex={-1} style={{width:"min(1150px,100%)",boxSizing:"border-box",maxHeight:"94dvh",overflow:"auto",background:"white",borderRadius:14,padding:narrow?14:20}}>
 <header style={{display:"flex",gap:12,alignItems:"center",flexWrap:"wrap",position:"sticky",top:narrow?-14:-20,background:"white",zIndex:1,padding:"8px 0"}}><button className="btn" onClick={onBack}>← Скрипти</button><h2 style={{flex:1,fontSize:narrow?19:24,margin:"8px 0"}}>Калькулятор TOPCIMENT</h2><button className="btn" onClick={onClose} aria-label="Закрити">×</button></header>
 <p>Підберіть систему та площу. «Потрібно» — витрата із запасом; «До закупівлі» — кількість у цілих упаковках.</p>
 <div style={{display:"flex",gap:12,flexWrap:"wrap",marginBottom:14}}><label>Де застосовуємо<br/><select value={areaType} style={{minHeight:40}} onChange={e=>{const v=e.target.value;setAreaType(v);setSystem(v==="historical"?"microdeck-dsv":`sttandard-${v}`);}}><option value="wall">Внутрішні стіни</option><option value="floor">Внутрішня підлога</option><option value="exterior">Зовнішня підлога</option><option value="historical">Історичні схеми</option></select></label>{areaType!=="historical"&&<label>Основа та ґрунт<br/><select value={substrate} onChange={e=>setSubstrate(e.target.value)} style={{minHeight:40,maxWidth:"100%"}}><option value="">Оберіть після перевірки основи</option><option value="abs">Поглинальна основа — ABS</option><option value="plus">Непоглинальна основа — PLUS</option></select></label>}</div>
 {areaType==="historical"&&<p role="status" style={{background:"#fff7ed",padding:12}}>Збережені історичні схеми. Перед замовленням потрібно перевірити склад і сумісність матеріалів.</p>}
 <div style={{display:"grid",gridTemplateColumns:narrow?"1fr 1fr":"minmax(220px,2fr) 1fr 1fr minmax(230px,2fr)",gap:12,marginBottom:16}}>
 <label style={{gridColumn:narrow?"1 / -1":undefined,minWidth:0}}>Система<br/><select style={{width:"100%",minHeight:40}} value={system} onChange={e=>setSystem(e.target.value)}>{(systems.length?systems.filter(s=>s.area_type===areaType):[{id:system,name:"Завантаження систем…"}]).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
 <label>Площа, м²<br/><input aria-label="Площа, м²" type="number" inputMode="decimal" min="0.01" max="100000" step="0.01" value={area} onChange={e=>setArea(e.target.value)} style={{width:"100%",boxSizing:"border-box",minHeight:40}}/></label>
 <label>Запас, %<br/><input aria-label="Запас, %" type="number" inputMode="decimal" min="0" max="50" value={reserve} onChange={e=>setReserve(e.target.value)} style={{width:"100%",boxSizing:"border-box",minHeight:40}}/></label>
 <label style={{gridColumn:narrow?"1 / -1":undefined,minWidth:0}}>Ціни<br/><select style={{width:"100%",minHeight:40}} value={basis} onChange={e=>setBasis(e.target.value)}><option value="sale">Продажні ціни Wallcov</option><option value="reference">Довідково: збережені ціни / курс НБУ</option></select></label></div>
 {loading&&<p role="status">Оновлюємо розрахунок…</p>}{error&&<p role="alert" style={{color:"#92400e"}}>{error}</p>}
 {stale&&<p role="status" style={{background:"#fff7ed",padding:12,fontWeight:700}}>Параметри змінено. Нижче попередній розрахунок — дочекайтеся оновлення.</p>}
 {result&&<div style={{opacity:stale?0.65:1}}><p><b>{result.system}</b> · {fmt(result.area)} м² + {fmt(result.reserve)}% запасу</p>
 {result.basis==="reference"&&<p style={{background:"#fff7ed",padding:12}}>{result.reference_metadata?.status==="consistent"?<>Відомі довідкові ціни перевірено {result.reference_date}; курс 1 € = {result.eur_uah} грн.</>:result.reference_metadata?.status==="mixed"?<>Довідкові ціни мають різні дати або курси. Дані кожного матеріалу показані у відповідному рядку.</>:<>Для частини або всіх довідкових цін дата чи курс не підтверджені. Перевірте дані у картках матеріалів.</>} Ціни та курс НБУ перевіряються щодня автоматично. Якщо джерело недоступне, зберігаються попередня ціна та дата її перевірки. Доставка, імпортні платежі та місцеві витрати не враховані. Продажну ціну Wallcov потрібно погодити.</p>}
 {!!result.technical_unverified?.length&&<p role="alert" style={{background:"#fff7ed",padding:12,color:"#92400e"}}><b>Довідковий розрахунок — норму погодити.</b> Перед замовленням уточніть застосування та витрату: {result.technical_unverified.map(r=>r.name).join("; ")}. Показані кількості та сума ще не є погодженим замовленням.</p>}
 {narrow?<div style={{display:"grid",gap:12}}>{result.rows.map(r=><article key={r.key} style={{border:"1px solid #e2e8f0",borderRadius:10,padding:12}}><h3 style={{fontSize:16,margin:"0 0 8px"}}>{r.name}</h3><dl style={{margin:0}}>{rowValues(r).map((value,i)=><div key={columns[i]} style={{display:"flex",justifyContent:"space-between",alignItems:"baseline",gap:12,borderBottom:"1px solid #f1f5f9",padding:"6px 0"}}><dt style={{color:"#475569",fontSize:13}}>{columns[i]}</dt><dd style={{margin:0,textAlign:"right",fontWeight:i>=5?700:500}}>{value}</dd></div>)}</dl>{productLinks(r)}</article>)}</div>:<div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:14}}><thead><tr>{["Матеріал",...columns].map(h=><th scope="col" key={h} style={{textAlign:"left",padding:9,borderBottom:"2px solid #cbd5e1"}}>{h}</th>)}</tr></thead><tbody>{result.rows.map(r=><tr key={r.key}><th scope="row" style={{padding:9,textAlign:"left",verticalAlign:"top",borderBottom:"1px solid #e2e8f0"}}>{r.name}{productLinks(r)}</th>{rowValues(r).map((v,i)=><td key={i} style={{padding:9,borderBottom:"1px solid #e2e8f0",verticalAlign:"top"}}>{v}</td>)}</tr>)}</tbody></table></div>}
 <h3>{stale?"Попередній підсумок":result.technical_unverified?.length?"Довідкова сума — норми потребують погодження":result.complete?"Разом":"Підсумок лише відомих цін"}: {money(result.rows.some(row=>row.subtotal!==null)?result.known_total:null)}</h3>{!!result.missing.length&&<p style={{color:"#92400e"}}>Розрахунок вартості неповний. Потрібно уточнити: {result.missing.join("; ")}.</p>}
 <details><summary style={{cursor:"pointer",fontWeight:700}}>Норми, склад системи та важливі умови</summary><ul style={{lineHeight:1.65}}>{result.notes.map(n=><li key={n}>{n.split(/(https:\/\/[^\s]+)/g).map((part,i)=>safeHttps(part)?<a key={i} href={part} target="_blank" rel="noreferrer">Офіційний документ</a>:part)}</li>)}</ul></details></div>}
 </section></div>, document.body);
}
