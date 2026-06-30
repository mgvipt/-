/* Анкета виявлення потреби (за скриптом РОПа Wallcov). Поля → lead.qualification (JSON).
 * Блоки: Обʼєкт · Продукт · Фінанси/Доставка · Додатково. */
import { useState, useEffect } from "react";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";

const ROOMS = ["Кухня", "Спальня", "Вітальня", "Ванна", "Коридор", "Офіс", "Салон краси", "Кафе/ресторан", "Інше"];
const PREP = ["Ідеально гладкі (під фарбування)", "Можна дефекти (під шпалери)", "Не підготовлені"];
const MATS = ["Galateya", "Pattera (Травертин)", "Mermi Silk", "Eleganti", "Celestial", "Velvet Luna", "Slate", "Ще не визначився"];
const TERMS = ["Терміново (1-2 тиж)", "В процесі (місяць)", "Планує (3+ міс)", "На майбутнє"];
const PROBE = ["Пробник", "Розрахунок на весь обʼєм"];
const PAY = ["Повна (LiqPay/Mono)", "Накладений платіж", "Передоплата + доплата"];
const SHIP = ["НП відділення", "НП курʼєр додому", "Самовивіз зі складу", "Власний курʼєр"];
const CONTACTED = ["Ні — вперше", "Так — був пробник", "Так — дивився раніше"];
const APPLIER = ["Сам наноситиму", "Потрібен майстер", "Ще не вирішив"];
const UNDERLAY = ["Без підкладки", "Біла підкладка", "Тонована підкладка"];

const inp: React.CSSProperties = { width: "100%", fontSize: 13, padding: "7px 9px", borderRadius: 8, border: "1px solid #e2e8f0", boxSizing: "border-box", background: "#fff" };

function Field({ label, children }: any) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 11.5, color: "#64748b", marginBottom: 4, fontWeight: 600 }}>{label}</div>
      {children}
    </div>
  );
}
function Sel({ k, label, opts, q, set }: any) {
  return (
    <Field label={label}>
      <select value={q[k] || ""} onChange={(e: any) => set(k, e.target.value)} style={inp}>
        <option value="">—</option>
        {opts.map((o: string) => <option key={o} value={o}>{o}</option>)}
      </select>
    </Field>
  );
}
function Txt({ k, label, ph, type, q, set }: any) {
  return (<Field label={label}><input value={q[k] || ""} type={type || "text"} placeholder={ph} onChange={(e: any) => set(k, e.target.value)} style={inp} /></Field>);
}
function Block({ title, children }: any) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", margin: "0 0 8px", paddingBottom: 4, borderBottom: "2px solid #eef2f7" }}>{title}</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 12px" }}>{children}</div>
    </div>
  );
}

export default function NeedsForm({ leadId, initial, endpoint = "/api/leads/" }: { leadId: number; initial?: any; endpoint?: string }) {
  const { t } = useLang();
  const [q, setQ] = useState<any>(initial || {});
  const [mats, setMats] = useState<string[]>(MATS);
  useEffect(() => { api.get<string[]>("/api/deals/kit_materials/").then((d) => { if (Array.isArray(d) && d.length) setMats([...d, "\u0429\u0435 \u043d\u0435 \u0432\u0438\u0437\u043d\u0430\u0447\u0438\u0432\u0441\u044f"]); }).catch(() => {}); }, []);
  const [saved, setSaved] = useState(true);
  const [busy, setBusy] = useState(false);
  function set(k: string, v: any) { setQ((p: any) => ({ ...p, [k]: v })); setSaved(false); }
  const kits: any[] = q.kits || [];
  function setKit(i: number, field: string, v: any) { const a = [...(q.kits || [])]; a[i] = { ...a[i], [field]: v }; set("kits", a); }
  function addKit() { set("kits", [...(q.kits || []), { material: "", color: "", board: false, tint: false }]); }
  function removeKit(i: number) { const a = [...(q.kits || [])]; a.splice(i, 1); set("kits", a); }
  // агент/сервер заповнив анкету → підхопити ТІЛЬКИ порожні поля (ручний ввід не чіпаємо)
  useEffect(() => {
    if (!initial) return;
    setQ((p: any) => {
      const m = { ...p }; let ch = false;
      for (const k of Object.keys(initial)) {
        if ((m[k] === undefined || m[k] === "" || m[k] === null) && initial[k]) { m[k] = initial[k]; ch = true; }
      }
      return ch ? m : p;
    });
  }, [initial]);
  async function save() {
    setBusy(true);
    try { await api.patch(`${endpoint}${leadId}/`, { qualification: q }); setSaved(true); } catch { /* ignore */ }
    setBusy(false);
  }

  return (
    <div className="panel">
      <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
        <div className="label" style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}><Icon n="📋" size={16} /> {t("Выявление потребности","Виявлення потреби")}</div>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: saved ? "#16a34a" : "#d97706", marginRight: 10 }}>{saved ? t("✓ сохранено","✓ збережено") : t("● несохранено","● незбережено")}</span>
        <button className="btn btn-primary" style={{ padding: "5px 14px" }} onClick={save} disabled={busy || saved}>{busy ? "…" : <><Icon n="💾" size={14} /> {t("Сохранить","Зберегти")}</>}</button>
      </div>

      <Block title={<><Icon n="🏠" size={15} /> {t("Объект","Обʼєкт")}</>}>
        <Sel q={q} set={set} k="room" label={t("Тип помещения","Тип приміщення")} opts={ROOMS} />
        <Txt q={q} set={set} k="area" label={t("Площадь стен, м²","Площа стін, м²")} type="number" ph={t("напр. 20","напр. 20")} />
        <Sel q={q} set={set} k="prep" label={t("Подготовка стен","Підготовка стін")} opts={PREP} />
        <Sel q={q} set={set} k="term" label={t("Сроки","Терміни")} opts={TERMS} />
        <Txt q={q} set={set} k="city" label={t("Город / регион","Місто / регіон")} ph={t("напр. Киев","напр. Київ")} />
      </Block>

      <Block title={<><Icon n="🎨" size={15} /> {t("Продукт","Продукт")}</>}>
        <Sel q={q} set={set} k="material" label={t("Материал","Матеріал")} opts={mats} />
        <Txt q={q} set={set} k="color" label={t("Цвет / тонировка","Колір / тонування")} ph={t("белый / под тон…","білий / під тон…")} />
        <Sel q={q} set={set} k="underlay" label={t("Подложка (для бланка выкраски)","Підкладка (для бланка викраски)")} opts={UNDERLAY} />
        <Sel q={q} set={set} k="probe" label={t("Пробник или объём","Пробник чи обʼєм")} opts={PROBE} />
        <Sel q={q} set={set} k="applier" label={t("Кто наносит","Хто наносить")} opts={APPLIER} />
      </Block>

      <Block title={<><Icon n="📋" size={15} /> {t("Тест-наборы для склада","Тест-набори для складу")}</>}>
        <div style={{ gridColumn: "1 / -1" }}>
          {kits.map((kit: any, i: number) => (
            <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6, alignItems: "center", flexWrap: "wrap" }}>
              <select value={kit.material || ""} onChange={(e) => setKit(i, "material", e.target.value)} style={{ ...inp, flex: "2 1 130px", width: "auto" }}>
                <option value="">{t("материал…","матеріал…")}</option>
                {mats.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <input value={kit.color || ""} placeholder={t("цвет 09-15","колір 09-15")} onChange={(e) => setKit(i, "color", e.target.value)} style={{ ...inp, flex: "1 1 90px", width: "auto" }} />
              <label style={{ fontSize: 11.5, display: "flex", gap: 3, alignItems: "center", whiteSpace: "nowrap" }}><input type="checkbox" checked={!!kit.board} onChange={(e) => setKit(i, "board", e.target.checked)} />{t("дощечка","дощечка")}</label>
              <label style={{ fontSize: 11.5, display: "flex", gap: 3, alignItems: "center", whiteSpace: "nowrap" }}><input type="checkbox" checked={!!kit.tint} onChange={(e) => setKit(i, "tint", e.target.checked)} />{t("тонировка","тонування")}</label>
              <button onClick={() => removeKit(i)} title={t("Удалить","Видалити")} style={{ border: "none", background: "#fef2f2", color: "#dc2626", borderRadius: 6, width: 26, height: 26, cursor: "pointer" }}>✕</button>
            </div>
          ))}
          <button onClick={addKit} className="btn btn-light" style={{ fontSize: 12, marginTop: 2 }}>+ {t("Добавить тест-набор","Додати тест-набір")}</button>
          <div className="muted" style={{ fontSize: 10.5, marginTop: 4 }}>{t("Несколько наборов → склад получит правильное ТЗ","Декілька наборів → склад отримає правильне ТЗ")}</div>
        </div>
      </Block>

      <Block title={<><Icon n="💳" size={15} /> {t("Финансы · Доставка","Фінанси · Доставка")}</>}>
        <Txt q={q} set={set} k="budget" label={t("Бюджет, ₴","Бюджет, ₴")} type="number" ph={t("напр. 5000","напр. 5000")} />
        <Sel q={q} set={set} k="pay" label={t("Способ оплаты","Спосіб оплати")} opts={PAY} />
        <Sel q={q} set={set} k="ship" label={t("Доставка","Доставка")} opts={SHIP} />
        <Sel q={q} set={set} k="contacted" label={t("Контакт ранее","Контакт раніше")} opts={CONTACTED} />
      </Block>

      <Block title={<><Icon n="📝" size={15} /> {t("Дополнительно","Додатково")}</>}>
        <div style={{ gridColumn: "1 / -1" }}>
          <Field label={t("Возражения / вопросы клиента","Заперечення / питання клієнта")}>
            <textarea value={q.objections || ""} onChange={(e) => set("objections", e.target.value)} rows={2} placeholder={t("напр. «дорого», «ждёт чёрную пятницу»…","напр. «дорого», «чекає чорну пʼятницю»…")} style={{ ...inp, resize: "vertical" }} />
          </Field>
        </div>
      </Block>
    </div>
  );
}
