/* Виявлення потреби — ПОКРОКОВИЙ степер (7 кроків + блок «Заперечення»), ТЗ мультиагентів 01.07.
 * Поля → qualification (JSON) через PATCH endpoint+leadId. Спільний для ліда і сделки. */
import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";

const ROOMS = ["Кухня", "Спальня", "Вітальня", "Ванна", "Коридор", "Офіс", "Салон краси", "Кафе/ресторан", "Інше"];
const PREP = ["Ідеально гладкі (під фарбування)", "Можна дефекти", "Не підготовлені"];
const MATS = ["Galateya", "Pattera (Травертин)", "Mermi Silk", "Eleganti", "Celestial", "Velvet Luna", "Slate", "Ще не визначився"];
const TERMS = ["Терміново (1-2 тиж)", "В процесі (місяць)", "Планує (3+ міс)", "На майбутнє"];
const PROBE = ["Пробник", "Розрахунок на весь обʼєм"];
const PAY = ["Повна (LiqPay/Mono)", "Накладений платіж", "Передоплата + доплата"];
const SHIP = ["НП відділення", "НП курʼєр додому", "Поштомат", "Самовивіз зі складу"];
const CONTACTED = ["Ні — вперше", "Так — був пробник", "Так — дивився раніше"];
const APPLIER = ["Сам наноситиму", "Потрібен майстер", "Ще не вирішив"];
const UNDERLAY = ["Без підкладки", "Біла підкладка", "Тонована підкладка"];
const FIRST_Q = ["Ціна (кг/м²/пробник)", "Різниця між матеріалами", "Чи підійде на мої стіни", "Інше"];
const SOURCE_IN = ["Тригер-слово з реклами", "Сторіз-згадка", "Кнопка бота", "Пряме питання в директ", "Рекомендація друга", "Інше"];
const PROBE_REACT = ["Готовий на обʼєм", "Хоче інший відтінок", "Ще думає", "Немає пробника"];
const WALL_COAT = ["Побілка вапном", "Старі шпалери", "Старе декор. покриття", "Голий бетон/гіпсокартон", "Не знає"];
const RENO_REASON = ["Косметичне оновлення", "Після новобудови", "Не подобається старий вигляд", "Готує на продаж/здачу", "Інше"];
const EFFECT = ["Спокійний перелив", "Виразна текстура (травертин)", "Оксамитовий мат", "Ще не визначився"];
const COLOR_APPROVED = ["Не надсилали", "Надіслано, чекаємо", "Погоджено клієнтом", "Просить інший відтінок"];
const NP_DEPT = ["Вантажне (зі страховкою)", "Звичайне (без страховки)"];
const OBJECTION = ["Немає", "Дорого", "Мовчання/Ігнор", "Вже купив деінде", "Незручне НП", "Конкурент", "Не актуально/сплутаний чат"];

const inp: React.CSSProperties = { width: "100%", fontSize: 13, padding: "7px 9px", borderRadius: 8, border: "1px solid #e2e8f0", boxSizing: "border-box", background: "#fff" };

// Кастомний випадаючий список (DOM, а не нативний <select>). Причина: нативний список
// малюється на рівні ОС і НЕ потрапляє у демонстрацію екрана (Meet/Zoom). Цей — через
// портал з fixed-позицією: видно у трансляції і не обрізається панеллю.
function DomSelect({ value, options, onChange, wrapStyle, placeholder = "—" }: { value: string; options: string[]; onChange: (v: string) => void; wrapStyle?: React.CSSProperties; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  function toggle() { if (!open && btnRef.current) setRect(btnRef.current.getBoundingClientRect()); setOpen((o) => !o); }
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener("scroll", close, true); window.addEventListener("resize", close);
    return () => { window.removeEventListener("scroll", close, true); window.removeEventListener("resize", close); };
  }, [open]);
  const row = (sel: boolean): React.CSSProperties => ({ padding: "8px 11px", fontSize: 13, cursor: "pointer", whiteSpace: "nowrap", background: sel ? "#eff6ff" : "#fff", color: sel ? "#1d4ed8" : "#0f172a", fontWeight: sel ? 600 : 400 });
  return (
    <div style={{ position: "relative", width: "100%", ...wrapStyle }}>
      <button type="button" ref={btnRef} onClick={toggle} style={{ ...inp, textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: value ? "#0f172a" : "#94a3b8" }}>{value || placeholder}</span>
        <span style={{ color: "#94a3b8", fontSize: 10, flexShrink: 0 }}>▾</span>
      </button>
      {open && rect && createPortal(
        <>
          <div onMouseDown={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 3000 }} />
          <div style={{ position: "fixed", top: rect.bottom + 3, left: rect.left, width: rect.width, zIndex: 3001, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 14px 36px rgba(0,0,0,.2)", maxHeight: 300, overflowY: "auto" }}>
            <div onClick={() => { onChange(""); setOpen(false); }} style={{ ...row(false), color: "#94a3b8" }}>{placeholder}</div>
            {options.map((o) => (
              <div key={o} onClick={() => { onChange(o); setOpen(false); }} style={row(o === value)}
                onMouseEnter={(e) => { if (o !== value) e.currentTarget.style.background = "#f1f5f9"; }}
                onMouseLeave={(e) => { if (o !== value) e.currentTarget.style.background = "#fff"; }}>{o}</div>
            ))}
          </div>
        </>, document.body)}
    </div>
  );
}

// [тип, ключ, лейбл, опції?]  типи: sel | num | txt | chk | kits
const STEPS: any[] = [
  { n: 1, icon: "🎯", title: "Тригер і перше питання", stage: "Взято в роботу",
    tip: "Тип першого питання задає весь сценарій. «Ціна» → веди на площу стін, НЕ називай суму без розрахунку. «Різниця матеріалів» → покажи 2 варіанти з фото (Galateya — спокійний перелив, дешевше; Pattera — травертин, дорожче). «Чи підійде на мої стіни» → це прихований страх: одразу скажи «підходить майже будь-яка поверхня після ґрунту глибокого проникнення».",
    fields: [["sel", "source_in", "Звідки прийшов", SOURCE_IN], ["sel", "first_question", "Перше питання клієнта", FIRST_Q]] },
  { n: 2, icon: "🏠", title: "Обʼєкт і терміни", stage: "Контакт встановлений",
    tip: "Питай розміри кімнати (довжина+висота), а не «яка площа» — клієнту легше. Терміни = маркер гарячий/холодний: «1-2 тижні» веди швидко до розрахунку; «на майбутнє» — в чергу прогріву, не тисни.",
    fields: [["sel", "room", "Тип приміщення", ROOMS], ["num", "area", "Площа стін, м²"], ["txt", "city", "Місто / регіон"], ["sel", "term", "Терміни ремонту", TERMS]] },
  { n: 3, icon: "🔥", title: "Прогрів після пробника", stage: "Прогрів після пробника",
    tip: "Найконверсійніший місток. «Готовий на обʼєм» → веди прямо до розрахунку (крок 6), не консультуй повторно. «Хоче інший відтінок» → запропонуй новий пробник, не тисни на великий обсяг зараз.",
    fields: [["sel", "contacted", "Контакт раніше", CONTACTED], ["sel", "probe_reaction", "Реакція на пробник", PROBE_REACT]] },
  { n: 4, icon: "🧱", title: "Стан стін і причина ремонту", stage: "Завдання виявлено",
    tip: "Скажи прямо: «підходить після ґрунту глибокого проникнення» — закриває страх «чи підійде». Побілка вапном → треба спецґрунт-адгезив (попередь про доп. вартість ЗАРАЗ). «Готує на продаж» → базова Galateya; «для себе надовго» → можна дорожчий (Velvet Lux).",
    fields: [["sel", "wall_current_coating", "Поточне покриття стін", WALL_COAT], ["sel", "prep", "Підготовка стін", PREP], ["sel", "renovation_reason", "Причина ремонту", RENO_REASON]] },
  { n: 5, icon: "🎨", title: "Підбір матеріалу і ефекту", stage: "Каталог відправлено / Рекомендації",
    tip: "Озвуч вигоду під ефект: «Спокійний перелив» → «не набридає з часом»; «Виразна текстура» → «акцентна стіна, ефект каменю»; «Оксамитовий мат» → «дорого і стримано». «Ще не визначився» → максимум 2 варіанти + тест-набір. «Сам наносить» → «після оплати даємо відео-МК, ви не один на один з матеріалом».",
    fields: [["sel", "material", "Матеріал", null], ["sel", "effect", "Бажаний ефект", EFFECT], ["txt", "color", "Колір / тонування"], ["kits"], ["sel", "underlay", "Підкладка (бланк викраски)", UNDERLAY], ["sel", "applier", "Хто наносить", APPLIER]] },
  { n: 6, icon: "🧮", title: "Розрахунок і колір", stage: "Розрахунок (КП) / Домовились про оплату",
    tip: "Прорахунок за 15-20 хв, ЗАВЖДИ з PDF і розкладкою по шарах — не називай суму без цього. Наполягає «просто суму»? → «щоб не помилитись, дайте хвилину — порахую точно». Фото кольору погодь ДО тонування всього обсягу. Якщо «надіслано, чекаємо» >2-3 дні — сигнал для дотиску. Бюджет менший за розрахунок → пропонуй меншу площу (стіна-акцент), не знижку.",
    fields: [["sel", "probe", "Пробник чи обʼєм", PROBE], ["num", "budget", "Бюджет, ₴"], ["chk", "calc_sent_date", "КП відправлено клієнту"], ["chk", "layers_shown", "Розкладку по шарах показано"], ["sel", "color_photo_approved", "Фото кольору погоджено", COLOR_APPROVED]] },
  { n: 7, icon: "🚚", title: "Оплата і доставка", stage: "Оплату отримано → Відвантаження → …",
    tip: "ОБОВʼЯЗКОВО попередь про звичайне відділення НП ДО оплати: рідкі/пилоподібні товари НП страхує лише на ВАНТАЖНИХ відділеннях. Клієнт наполягає на звичайному → постав галочку підтвердження з датою (фіксує попередження, закриває спір при пошкодженні).",
    fields: [["sel", "pay", "Спосіб оплати", PAY], ["sel", "ship", "Спосіб доставки", SHIP], ["sel", "np_department_type", "Тип відділення НП", NP_DEPT], ["chk", "np_insurance_confirmed", "Клієнт попереджений про страховку"]] },
];

function NeedsForm({ leadId, initial, endpoint = "/api/leads/" }: { leadId: number; initial?: any; endpoint?: string }) {
  const { t } = useLang();
  const [q, setQ] = useState<any>(initial || {});
  const [mats, setMats] = useState<string[]>(MATS);
  const [saved, setSaved] = useState(true);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<number>(0);
  useEffect(() => { api.get<string[]>("/api/deals/kit_materials/").then((d) => { if (Array.isArray(d) && d.length) setMats([...d, "Ще не визначився"]); }).catch(() => {}); }, []);
  function set(k: string, v: any) { setQ((p: any) => ({ ...p, [k]: v })); setSaved(false); }
  const kits: any[] = q.kits || [];
  function setKit(i: number, f: string, v: any) { const a = [...(q.kits || [])]; a[i] = { ...a[i], [f]: v }; set("kits", a); }
  function addKit() { set("kits", [...(q.kits || []), { material: "", color: "", note: "", board: false, tint: false }]); }
  function removeKit(i: number) { const a = [...(q.kits || [])]; a.splice(i, 1); set("kits", a); }
  // сервер/агент заповнив анкету → підхопити лише порожні поля
  useEffect(() => {
    if (!initial) return;
    setQ((p: any) => { const m = { ...p }; let ch = false; for (const k of Object.keys(initial)) { if ((m[k] === undefined || m[k] === "" || m[k] === null) && initial[k]) { m[k] = initial[k]; ch = true; } } return ch ? m : p; });
  }, [initial]);
  // авто-відкрити перший незаповнений крок
  useEffect(() => { if (open === 0) { const first = STEPS.find((st) => !stepDone(st)); setOpen(first ? first.n : 1); } /* eslint-disable-next-line */ }, [initial]);
  async function save() { setBusy(true); try { await api.patch(`${endpoint}${leadId}/`, { qualification: q }); setSaved(true); } catch { /* ignore */ } setBusy(false); }

  function stepDone(st: any) { return st.fields.some((f: any) => f[0] === "kits" ? (q.kits || []).length : q[f[1]]); }
  function stepSummary(st: any) { const parts: string[] = []; st.fields.forEach((f: any) => { if (f[0] === "kits") { if ((q.kits || []).length) parts.push(`${(q.kits || []).length} набір`); } else if (q[f[1]]) parts.push(String(q[f[1]])); }); return parts.join(" · "); }
  const doneCount = STEPS.filter(stepDone).length;

  function renderField(f: any) {
    const [type, k, label, opts] = f;
    if (type === "kits") return (
      <div key="kits" style={{ marginBottom: 8 }}>
        <div style={{ fontSize: 12, color: "#0f172a", marginBottom: 4, fontWeight: 700 }}>🎨 {t("Тест-наборы клиента — добавь КАЖДЫЙ отдельно", "Тест-набори клієнта — додай КОЖЕН окремо")}</div>
        <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>{t("У каждого набора — свой материал, цвет и комментарий к цвету. Это видит склад при отгрузке.", "У кожного набору — свій матеріал, колір і коментар до кольору. Це бачить склад при відвантаженні.")}</div>
        {kits.map((kit: any, i: number) => (
          <div key={i} style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "8px 9px", marginBottom: 6, background: "#fbfdff" }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", minWidth: 18 }}>#{i + 1}</span>
              <DomSelect value={kit.material || ""} options={mats} onChange={(v) => setKit(i, "material", v)} wrapStyle={{ flex: "2 1 120px" }} placeholder={t("материал…", "матеріал…")} />
              <input value={kit.color || ""} placeholder={t("цвет", "колір")} onChange={(e) => setKit(i, "color", e.target.value)} style={{ ...inp, flex: "1 1 80px", width: "auto" }} />
              <label style={{ fontSize: 11, display: "flex", gap: 3, alignItems: "center" }}><input type="checkbox" checked={!!kit.board} onChange={(e) => setKit(i, "board", e.target.checked)} />{t("дощечка", "дощечка")}</label>
              <label style={{ fontSize: 11, display: "flex", gap: 3, alignItems: "center" }}><input type="checkbox" checked={!!kit.tint} onChange={(e) => setKit(i, "tint", e.target.checked)} />{t("тон.", "тон.")}</label>
              <button onClick={() => removeKit(i)} style={{ border: "none", background: "#fef2f2", color: "#dc2626", borderRadius: 6, width: 24, height: 24, cursor: "pointer", marginLeft: "auto" }}>✕</button>
            </div>
            <input value={kit.note || ""} placeholder={t("💬 комментарий к цвету (напр. база + перламутр, наносить в 2 слоя)", "💬 коментар до кольору (напр. база + перламутр, наносити у 2 шари)")} onChange={(e) => setKit(i, "note", e.target.value)} style={{ ...inp, width: "100%" }} />
          </div>
        ))}
        <button onClick={addKit} className="btn btn-light" style={{ fontSize: 12 }}>+ {t("Добавить набор", "Додати набір")}</button>
      </div>
    );
    if (type === "chk") return (
      <label key={k} style={{ display: "flex", gap: 7, alignItems: "center", fontSize: 12.5, margin: "8px 0", cursor: "pointer", gridColumn: "1 / -1" }}>
        <input type="checkbox" checked={!!q[k]} onChange={(e) => set(k, e.target.checked ? new Date().toISOString().slice(0, 10) : "")} />
        {label}{q[k] && <span style={{ color: "#16a34a", fontSize: 11 }}>· {q[k]}</span>}
      </label>
    );
    return (
      <div key={k} style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 11.5, color: "#64748b", marginBottom: 4, fontWeight: 600 }}>{label}</div>
        {type === "sel"
          ? <DomSelect value={q[k] || ""} options={opts || mats} onChange={(v) => set(k, v)} />
          : <input value={q[k] || ""} type={type === "num" ? "number" : "text"} onChange={(e) => set(k, e.target.value)} style={inp} />}
      </div>
    );
  }

  return (
    <div className="panel">
      <div style={{ display: "flex", alignItems: "center", marginBottom: 6 }}>
        <div className="label" style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}><Icon n="📋" size={16} /> {t("Выявление потребности", "Виявлення потреби")}</div>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: saved ? "#16a34a" : "#d97706", marginRight: 10 }}>{saved ? t("✓ сохранено", "✓ збережено") : t("● несохранено", "● незбережено")}</span>
        <button className="btn btn-primary" style={{ padding: "5px 14px" }} onClick={save} disabled={busy || saved}>{busy ? "…" : <><Icon n="💾" size={14} /> {t("Сохранить", "Зберегти")}</>}</button>
      </div>
      {/* прогрес */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div style={{ flex: 1, height: 7, background: "#e2e8f0", borderRadius: 5, overflow: "hidden" }}><div style={{ width: `${(doneCount / 7) * 100}%`, height: "100%", background: "linear-gradient(90deg,#22c55e,#16a34a)", transition: "width .3s" }} /></div>
        <span className="muted" style={{ fontSize: 11.5, whiteSpace: "nowrap" }}>{t("Шаг", "Крок")} {open || 1} {t("из", "з")} 7 · {doneCount}/7 ✓</span>
      </div>
      {/* кроки-акордеон */}
      {STEPS.map((st) => {
        const isOpen = open === st.n; const done = stepDone(st);
        return (
          <div key={st.n} style={{ border: "1px solid " + (isOpen ? "#93c5fd" : "#e8edf3"), borderRadius: 10, marginBottom: 8, overflow: "hidden", background: isOpen ? "#fbfdff" : "#fff" }}>
            <div onClick={() => setOpen(isOpen ? 0 : st.n)} style={{ display: "flex", alignItems: "center", gap: 9, padding: "9px 11px", cursor: "pointer", background: isOpen ? "#eff6ff" : "transparent" }}>
              <span style={{ width: 22, height: 22, borderRadius: 11, background: done ? "#16a34a" : "#cbd5e1", color: "#fff", fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{done ? "✓" : st.n}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: "#0f172a" }}>{st.icon} {t("Шаг", "Крок")} {st.n} — {st.title}</div>
                {!isOpen && done && <div className="muted" style={{ fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{stepSummary(st)}</div>}
                {!isOpen && !done && <div className="muted" style={{ fontSize: 11 }}>{st.stage}</div>}
              </div>
              <Icon n={isOpen ? "chevron-up" : "chevron-down"} size={16} />
            </div>
            {isOpen && (
              <div style={{ padding: "6px 12px 12px" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 12px" }}>{st.fields.map(renderField)}</div>
                <div style={{ background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: 8, padding: "8px 11px", fontSize: 11.5, lineHeight: 1.5, color: "#0c4a6e", marginTop: 6 }}>
                  <b>💡 {t("Совет менеджеру", "Порада менеджеру")}:</b> {st.tip}
                  <div style={{ marginTop: 5, fontSize: 10.5, color: "#0369a1" }}>📍 {t("Стадия воронки", "Стадія воронки")}: {st.stage}</div>
                </div>
              </div>
            )}
          </div>
        );
      })}
      {/* Заперечення — завжди видимий */}
      <div style={{ border: "1px solid #fecaca", borderRadius: 10, marginTop: 12, padding: "10px 12px", background: "#fff7f7" }}>
        <div style={{ fontSize: 12.5, fontWeight: 700, color: "#b91c1c", marginBottom: 8 }}>⚠️ {t("Возражения (виден всегда)", "Заперечення (видно завжди)")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 12px" }}>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11.5, color: "#64748b", marginBottom: 4, fontWeight: 600 }}>{t("Тип возражения", "Тип заперечення")}</div>
            <DomSelect value={q.objection_type || ""} options={OBJECTION} onChange={(v) => set("objection_type", v)} />
          </div>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11.5, color: "#64748b", marginBottom: 4, fontWeight: 600 }}>{t("Дата фоллоу-апа", "Дата фоллоу-апу")}</div>
            <input type="date" value={q.followup_date || ""} onChange={(e) => set("followup_date", e.target.value)} style={inp} />
          </div>
        </div>
        <div style={{ marginBottom: 4 }}>
          <div style={{ fontSize: 11.5, color: "#64748b", marginBottom: 4, fontWeight: 600 }}>{t("Комментарий / вопросы клиента", "Коментар / питання клієнта")}</div>
          <textarea value={q.objections || ""} onChange={(e) => set("objections", e.target.value)} rows={2} style={{ ...inp, resize: "vertical" }} />
        </div>
        <div style={{ fontSize: 11, color: "#7f1d1d", lineHeight: 1.5, background: "#fef2f2", borderRadius: 7, padding: "6px 9px" }}>
          <b>💡</b> «Дорого» → аргумент розкладкою ціни по шарах, НЕ знижка. «Ігнор» → нагадування через N днів: «наш діалог міг змішатись з іншими… ще актуально?». «Вже купив» → «коли захочете оновити стіни — ми тут». «Незручне НП» → запропонуй самовивіз/курʼєр.
        </div>
      </div>
    </div>
  );
}
export default NeedsForm;
