/* Анкета виявлення потреби (за скриптом РОПа Wallcov). Поля → lead.qualification (JSON).
 * Блоки: Обʼєкт · Продукт · Фінанси/Доставка · Додатково. */
import { useState } from "react";
import { api } from "./api";

const ROOMS = ["Кухня", "Спальня", "Вітальня", "Ванна", "Коридор", "Офіс", "Салон краси", "Кафе/ресторан", "Інше"];
const PREP = ["Ідеально гладкі (під фарбування)", "Можна дефекти (під шпалери)", "Не підготовлені"];
const MATS = ["Galateya", "Pattera (Травертин)", "Mermi Silk", "Eleganti", "Celestial", "Velvet Luna", "Slate", "Ще не визначився"];
const TERMS = ["Терміново (1-2 тиж)", "В процесі (місяць)", "Планує (3+ міс)", "На майбутнє"];
const PROBE = ["Пробник", "Розрахунок на весь обʼєм"];
const PAY = ["Повна (LiqPay/Mono)", "Накладений платіж", "Передоплата + доплата"];
const SHIP = ["НП відділення", "НП курʼєр додому", "Самовивіз зі складу", "Власний курʼєр"];
const CONTACTED = ["Ні — вперше", "Так — був пробник", "Так — дивився раніше"];
const APPLIER = ["Сам наноситиму", "Потрібен майстер", "Ще не вирішив"];

const inp: React.CSSProperties = { width: "100%", fontSize: 13, padding: "7px 9px", borderRadius: 8, border: "1px solid #e2e8f0", boxSizing: "border-box", background: "#fff" };

export default function NeedsForm({ leadId, initial }: { leadId: number; initial?: any }) {
  const [q, setQ] = useState<any>(initial || {});
  const [saved, setSaved] = useState(true);
  const [busy, setBusy] = useState(false);
  function set(k: string, v: any) { setQ((p: any) => ({ ...p, [k]: v })); setSaved(false); }
  async function save() {
    setBusy(true);
    try { await api.patch(`/api/leads/${leadId}/`, { qualification: q }); setSaved(true); } catch { /* ignore */ }
    setBusy(false);
  }

  const Field = ({ label, children }: { label: string; children: any }) => (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 11.5, color: "#64748b", marginBottom: 4, fontWeight: 600 }}>{label}</div>
      {children}
    </div>
  );
  const Sel = ({ k, label, opts }: { k: string; label: string; opts: string[] }) => (
    <Field label={label}>
      <select value={q[k] || ""} onChange={(e) => set(k, e.target.value)} style={inp}>
        <option value="">—</option>
        {opts.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </Field>
  );
  const Txt = ({ k, label, ph, type }: { k: string; label: string; ph?: string; type?: string }) => (
    <Field label={label}><input value={q[k] || ""} type={type || "text"} placeholder={ph} onChange={(e) => set(k, e.target.value)} style={inp} /></Field>
  );
  const Block = ({ title, children }: { title: string; children: any }) => (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", margin: "0 0 8px", paddingBottom: 4, borderBottom: "2px solid #eef2f7" }}>{title}</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 12px" }}>{children}</div>
    </div>
  );

  return (
    <div className="panel">
      <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
        <div className="label" style={{ margin: 0 }}>📋 Виявлення потреби</div>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: saved ? "#16a34a" : "#d97706", marginRight: 10 }}>{saved ? "✓ збережено" : "● незбережено"}</span>
        <button className="btn btn-primary" style={{ padding: "5px 14px" }} onClick={save} disabled={busy || saved}>{busy ? "…" : "💾 Зберегти"}</button>
      </div>

      <Block title="🏠 Обʼєкт">
        <Sel k="room" label="Тип приміщення" opts={ROOMS} />
        <Txt k="area" label="Площа стін, м²" type="number" ph="напр. 20" />
        <Sel k="prep" label="Підготовка стін" opts={PREP} />
        <Sel k="term" label="Терміни" opts={TERMS} />
        <Txt k="city" label="Місто / регіон" ph="напр. Київ" />
      </Block>

      <Block title="🎨 Продукт">
        <Sel k="material" label="Матеріал" opts={MATS} />
        <Txt k="color" label="Колір / тонування" ph="білий / під тон…" />
        <Sel k="probe" label="Пробник чи обʼєм" opts={PROBE} />
        <Sel k="applier" label="Хто наносить" opts={APPLIER} />
      </Block>

      <Block title="💳 Фінанси · Доставка">
        <Txt k="budget" label="Бюджет, ₴" type="number" ph="напр. 5000" />
        <Sel k="pay" label="Спосіб оплати" opts={PAY} />
        <Sel k="ship" label="Доставка" opts={SHIP} />
        <Sel k="contacted" label="Контакт раніше" opts={CONTACTED} />
      </Block>

      <Block title="📝 Додатково">
        <div style={{ gridColumn: "1 / -1" }}>
          <Field label="Заперечення / питання клієнта">
            <textarea value={q.objections || ""} onChange={(e) => set("objections", e.target.value)} rows={2} placeholder="напр. «дорого», «чекає чорну пʼятницю»…" style={{ ...inp, resize: "vertical" }} />
          </Field>
        </div>
      </Block>
    </div>
  );
}
