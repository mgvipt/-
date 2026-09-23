export type Lang = "uk" | "ru";
type Source = { url?: string; revision?: string; page?: number | number[] };
export type Density = { state: "powder" | "liquid" | "mix" | "cured" | "unknown"; component?: string | null; value?: number | null; min?: number | null; max?: number | null; uncertainty?: number | null; unit: string; status: string; source?: Source };
export type Technical = { schema_version: number; density: Density[]; consumption?: {value:number|number[];unit:string;coat_count:number|null;kind?:string;source?:Source}[]; notes?: {uk:string;ru:string}[]; technical_review?: {required:boolean;codes:string[]} };
const names = { uk:{powder:"Порошок",liquid:"Рідкий матеріал",mix:"Готова суміш",cured:"Затверділе покриття",unknown:"Стан не уточнено"}, ru:{powder:"Порошок",liquid:"Жидкий материал",mix:"Готовая смесь",cured:"Затвердевшее покрытие",unknown:"Состояние не уточнено"} };
export function densityLabel(d:Density,lang:Lang){return `${names[lang][d.state] || d.state}${d.component ? ` · ${lang==="uk"?"компонент":"компонент"} ${d.component}` : ""}`;}
export function densityValue(d:Density,lang:Lang){
 const valid=(v:unknown)=>typeof v==="number"&&Number.isFinite(v)&&v>0;
 const number=(v:number)=>v.toLocaleString(lang==="uk"?"uk-UA":"ru-UA",{maximumFractionDigits:6});
 if(d.status!=="confirmed"||d.unit!=="kg/L")return lang==="uk"?"Не підтверджено":"Не подтверждено";
 const value=valid(d.value)?number(d.value!)+(valid(d.uncertainty)?` ± ${number(d.uncertainty!)}`:""):valid(d.min)&&valid(d.max)&&d.min!<=d.max!?`${number(d.min!)}–${number(d.max!)}`:null;
 return value?`${value} ${lang==="uk"?"кг/л":"кг/л"}`:lang==="uk"?"Не підтверджено":"Не подтверждено";
}
function SourceLine({source,lang}:{source?:Source;lang:Lang}){if(!source)return null;return <small style={{display:"block",color:"#64748b"}}>{source.url&&/^https:\/\//.test(source.url)?<a href={source.url} target="_blank" rel="noreferrer">{lang==="uk"?"Технічний лист":"Технический лист"}</a>:null}{source.revision?` · ${source.revision}`:""}{source.page?` · ${lang==="uk"?"стор.":"стр."} ${Array.isArray(source.page)?source.page.join(", "):source.page}`:""}</small>}
export default function ProductTechnicalFacts({data,lang="uk",compact=false}:{data?:Technical;lang?:Lang;compact?:boolean}){
 const uk=lang==="uk", density=data?.density||[];
 const unitLabel=(unit:string)=>({"kg powder/m²":uk?"кг порошку/м²":"кг порошка/м²","kg/m²":"кг/м²","L/m²":"л/м²","L mixed A+B/m²":uk?"л суміші A+B/м²":"л смеси A+B/м²","m²/L mixed A+B":uk?"м²/л суміші A+B":"м²/л смеси A+B","m²/L":"м²/л","m²/kg":"м²/кг"}[unit]||unit);
 return <section aria-label={uk?"Технічні характеристики":"Технические характеристики"} style={{margin:"12px 0"}}>
 <h4 style={{margin:"0 0 8px"}}>{uk?"Густина та технічні норми":"Плотность и технические нормы"}</h4>
 {data?.technical_review?.required&&<p role="status" style={{color:"#92400e",background:"#fffbeb",padding:8}}>{uk?"Потрібна технічна перевірка: джерела або розрахункові норми розходяться. Перед розрахунком уточніть систему та партію матеріалу.":"Нужна техническая проверка: источники или расчётные нормы расходятся. Перед расчётом уточните систему и партию материала."}</p>}
 {!density.length?<p>{uk?"Густина: Не підтверджено":"Плотность: Не подтверждено"}</p>:<table style={{borderCollapse:"collapse",width:"100%"}}><thead><tr><th style={{textAlign:"left"}}>{uk?"Стан матеріалу":"Состояние материала"}</th><th style={{textAlign:"left"}}>{uk?"Густина":"Плотность"}</th></tr></thead><tbody>{density.map((d,i)=><tr key={i}><td style={{padding:"5px 8px 5px 0"}}>{densityLabel(d,lang)}{!compact&&<SourceLine source={d.source} lang={lang}/>}</td><td>{densityValue(d,lang)}</td></tr>)}</tbody></table>}
 {!compact&&<>
 <p style={{fontSize:12,color:"#475569"}}>{uk?"Густина порошку, суміші та затверділого покриття — різні величини. Не використовуйте їх для дозування рідких компонентів. Густини для чинного калькулятора вказані окремо в нормах змішування.":"Плотность порошка, смеси и затвердевшего покрытия — разные величины. Не используйте их для дозирования жидких компонентов. Плотности для действующего калькулятора указаны отдельно в нормах смешивания."}</p>
 {(data?.consumption||[]).map((row,i)=><p key={i}><b>{row.unit.startsWith("m²/")?(uk?"Покривність за техлистом":"Укрывная площадь по техлисту"):(uk?"Витрата за техлистом":"Расход по техлисту")}:</b> {Array.isArray(row.value)?row.value.join("–"):row.value} {unitLabel(row.unit)}{row.coat_count?` · ${row.coat_count} ${uk?"шар(и)":"слой/слоя"}`:` · ${uk?"кількість шарів уточнити":"количество слоёв уточнить"}`}<SourceLine source={row.source} lang={lang}/></p>)}
 {(data?.notes||[]).map((n,i)=><p key={i}>{n[lang]}</p>)}
 </>}
 </section>;
}
