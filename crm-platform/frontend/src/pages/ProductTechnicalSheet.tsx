import {useState} from "react";
import {api} from "../api";
import {densityLabel,densityValue,type Lang,type Technical} from "./ProductTechnicalFacts";
type Row={id:number;name:string;unit:string;pack_factor:string|null;price:string|null;currency:string;technical:Technical};
export default function ProductTechnicalSheet({ids,lang}:{ids:number[];lang:Lang}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(false); const uk=lang==="uk";
 async function print(){
  if(busy||!ids.length)return;const win=window.open("","_blank");if(!win){setError(true);return;}
  setBusy(true);setError(false);win.document.title=uk?"Шпаргалка матеріалів":"Шпаргалка материалов";win.document.body.textContent=uk?"Завантаження…":"Загрузка…";
  try{
   const result=await api.get<{items:Row[];missing_ids:number[]}>(`/api/products/technical-sheet/?ids=${[...new Set(ids)].join(",")}&lang=${lang}`);
   if(win.closed)return;if(result.missing_ids.length)throw new Error("missing products");
   const doc=win.document;doc.body.textContent="";const style=doc.createElement("style");style.textContent="body{font:12px Arial;margin:15px}table{width:100%;border-collapse:collapse}td,th{border:1px solid #aaa;padding:6px;text-align:left;white-space:pre-line}tr{break-inside:avoid}button{margin:10px}@media print{button{display:none}@page{size:landscape;margin:10mm}}";doc.head.appendChild(style);
   const heading=doc.createElement("h2");heading.textContent=doc.title;doc.body.appendChild(heading);
   const stamp=doc.createElement("p");stamp.textContent=new Date().toLocaleString(uk?"uk-UA":"ru-UA");doc.body.appendChild(stamp);
   const button=doc.createElement("button");button.textContent=uk?"Друкувати":"Печатать";button.onclick=()=>win.print();doc.body.appendChild(button);
   const table=doc.createElement("table"),head=doc.createElement("thead"),tr=doc.createElement("tr");
   [uk?"Матеріал":"Материал",uk?"Ціна / одиниця":"Цена / единица",uk?"В упаковці":"В упаковке",uk?"Густина, кг/л":"Плотность, кг/л",uk?"Перевірка":"Проверка"].forEach(text=>{const th=doc.createElement("th");th.textContent=text;tr.appendChild(th)});head.appendChild(tr);table.appendChild(head);
   const body=doc.createElement("tbody");for(const p of result.items){const row=doc.createElement("tr");const densities=(p.technical.density||[]).map(d=>`${densityLabel(d,lang)}: ${densityValue(d,lang)}`).join("\n");const values=[p.name,Number(p.price)>0?`${p.price} ${p.currency} / ${p.unit}`:uk?"Ціну уточнити":"Цену уточнить",p.pack_factor!=null&&Number(p.pack_factor)>0?`${p.pack_factor} ${p.unit}`:uk?"Не підтверджено":"Не подтверждено",densities||(uk?"Не підтверджено":"Не подтверждено"),p.technical.technical_review?.required?(uk?"Потрібне уточнення норм/системи":"Нужно уточнение норм/системы"):"—"];values.forEach(value=>{const td=doc.createElement("td");td.textContent=value;row.appendChild(td)});body.appendChild(row)}table.appendChild(body);doc.body.appendChild(table);
   const note=doc.createElement("p");note.textContent=uk?"Густина порошку та затверділого покриття не використовується для дозування рідких компонентів. Норми змішування перевіряйте окремо.":"Плотность порошка и затвердевшего покрытия не используется для дозирования жидких компонентов. Нормы смешивания проверяйте отдельно.";doc.body.appendChild(note);win.focus();win.print();
  }catch{if(!win.closed)win.document.body.textContent=uk?"Не вдалося отримати актуальні дані. Закрийте вікно та повторіть.":"Не удалось получить актуальные данные. Закройте окно и повторите.";setError(true)}finally{setBusy(false)}
 }
 return <span><button className="btn btn-light" type="button" disabled={busy||!ids.length} onClick={print}>{busy?(uk?"Готуємо…":"Готовим…"):(uk?"Друк шпаргалки · товари на цій сторінці":"Печать шпаргалки · товары на этой странице")}</button>{error&&<small role="alert"> {uk?"Не вдалося відкрити шпаргалку. Перевірте доступ і дозвіл на нові вікна.":"Не удалось открыть шпаргалку. Проверьте доступ и разрешение новых окон."}</small>}</span>;
}
