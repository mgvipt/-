import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../Icon";
import { AutomationMessages } from "./AutomationMessages";

/* Швидкі відповіді — «скрипт продажів» (14.09; структура переписана 17.09.2026, запит Олега «зараз заплутано»).
 * Як у CRM з готовими скриптами (HubSpot playbooks, Salesforce Quick Text, amoCRM «/»):
 *  • зліва навігація групами: ⭐ обрані й нещодавні → ХІД РОЗМОВИ (кроки по порядку) → СИТУАЦІЇ (заперечення,
 *    дожими — бувають будь-коли) → ТОВАРИ З ЦІНАМИ (описи з номенклатури) → Інше;
 *  • посередині — відповіді розділу: назва, «коли» і початок тексту; у товарах — діапазон цін;
 *  • праворуч — повний текст, «коли використовувати», ціни з номенклатури і кнопка «Вставити».
 * Пошук — по всіх розділах. «/» у порожньому полі чату відкриває це вікно одразу.
 * Клік «Вставити» — текст іде в поле вводу, НЕ клієнту. Незаповнені поля [сума] підсвічені; сервер не відправить з ними. */

export type Reply = {
  id: number; title: string; text: string; asset_ids: number[]; category?: string; when_to_use?: string;
  kind?: string; folder?: string; price_range?: string; products?: { id: number; name: string; price: string }[]; sort?: number;
};
type Stage = { key: string; label: string; icon: string; goal: string; next: string; group: "flow" | "situation" | "products" | "other" | "mine"; step?: number };

// Хід розмови — справжня послідовність, тому з номерами. Ситуації — без номерів: трапляються на будь-якому кроці.
const FLOW: Stage[] = [
  { key: "Виявлення потреби", label: "Виявлення потреби", icon: "🔎", next: "Розрахунок і ціна", group: "flow", step: 1,
    goal: "Дізнатися кімнату, площу, стиль. Клієнт, що назвав площу, купує в 14% випадків (без неї — 5%), надіслав фото стіни — у 28%." },
  { key: "Розрахунок і ціна", label: "Розрахунок і ціна", icon: "🧮", next: "Тест-набір", group: "flow", step: 2,
    goal: "Назвати суму під його площу, а не прайс. Дати вибір із двох варіантів і спитати, що ближче." },
  { key: "Тест-набір", label: "Тест-набір", icon: "🎨", next: "Закриття на оплату", group: "flow", step: 3,
    goal: "Тест-набір — крок до рішення, коли клієнт вагається з кольором або фактурою. Готові описи з цінами по кожному матеріалу — у розділі «Тест-набори з цінами»." },
  { key: "Закриття на оплату", label: "Закриття на оплату", icon: "✅", next: "Після оплати", group: "flow", step: 4,
    goal: "Реквізити або посилання, резерв товару. Наступного дня — нагадування: після посилання за тиждень платить лише половина." },
  { key: "Після оплати", label: "Після оплати", icon: "📦", next: "Тест → основне замовлення", group: "flow", step: 5,
    goal: "Перевірте автоматичні повідомлення про оплату, майстер-клас і доставку кнопкою вгорі. Перед ручною відповіддю перегляньте чат, щоб не дублювати відправку." },
  { key: "Тест → основне замовлення", label: "Тест → основне", icon: "🔁", next: "", group: "flow", step: 6,
    goal: "Після тест-набору спитати площу і зробити розрахунок: так основне замовлення роблять у 22% випадків замість 7–11%." },
];
const SITUATIONS: Stage[] = [
  { key: "Заперечення", label: "Заперечення", icon: "💬", next: "Закриття на оплату", group: "situation",
    goal: "«Дорого» і «подумаю» — це інтерес: такі клієнти платять у 22% і 15% випадків. Відповісти по суті і дати наступний крок." },
  { key: "Дожими і повернення з ігнору", label: "Клієнт замовк", icon: "⏰", next: "", group: "situation",
    goal: "Дожим 1 — через 2 дні, особисто, по його ситуації. Дожим 2 — теплим через 4–5 днів з новою користю. Далі стоп." },
];
const FAV: Stage = { key: "__fav", label: "Обрані", icon: "⭐", goal: "Ваші відповіді під рукою. Зірочка ☆ у відповіді — додати або прибрати.", next: "", group: "mine" };
const RECENT: Stage = { key: "__recent", label: "Нещодавні", icon: "🕘", goal: "Останні відповіді, які Ви вставляли.", next: "", group: "mine" };
const OTHER: Stage = { key: "", label: "Інше", icon: "📁", goal: "Відповіді без розділу. Розділ задається в Налаштування → Відкриті лінії → Швидкі відповіді.", next: "", group: "other" };
const LS_STAGE = "qr_script_stage", LS_FAV = "qr_fav_v1", LS_RECENT = "qr_recent_v1";

const readIds = (k: string): number[] => { try { const v = JSON.parse(localStorage.getItem(k) || "[]"); return Array.isArray(v) ? v.filter((x) => typeof x === "number") : []; } catch { return []; } };
const writeIds = (k: string, ids: number[]) => { try { localStorage.setItem(k, JSON.stringify(ids)); } catch { /* приватний режим */ } };

function Highlight({ text }: { text: string }) {
  const parts = text.split(/(\[[^\]\n]{1,40}\]|\{[^}\n]{1,30}\})/g);
  return <>{parts.map((p, i) => (/^\[[^\]]+\]$/.test(p) && !/^\[\d+\/\d+\]$/.test(p)) || /^\{[^}]+\}$/.test(p)
    ? <mark key={i} style={{ background: "#fde68a", color: "#78350f", borderRadius: 4, padding: "0 3px" }}>{p}</mark>
    : <span key={i}>{p}</span>)}</>;
}

function SideItem({ s, on, count, onPick }: { s: Stage; on: boolean; count: number; onPick: (k: string) => void }) {
  return <button type="button" onClick={() => onPick(s.key)} aria-current={on ? "true" : undefined}
    style={{ display: "flex", alignItems: "center", gap: 7, width: "100%", textAlign: "left", border: 0, borderRadius: 8, padding: "6px 8px", cursor: "pointer",
      background: on ? "#e6eef8" : "transparent", color: "#1b2230", fontSize: 13, fontWeight: on ? 700 : 500 }}>
    {s.step ? <span style={{ flex: "0 0 18px", height: 18, borderRadius: 999, background: on ? "#2E6FB0" : "#dbe3ee", color: on ? "#fff" : "#475569", fontSize: 11, fontWeight: 700, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>{s.step}</span>
      : <span style={{ flex: "0 0 18px", textAlign: "center" }}><Icon n={s.icon} size={14} /></span>}
    <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.label}</span>
    <span style={{ color: "#7b8496", fontWeight: 500, fontSize: 12, fontVariantNumeric: "tabular-nums" }}>{count}</span>
  </button>;
}

function GroupLabel({ children }: { children: any }) {
  return <div style={{ fontSize: 10.5, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: ".06em", margin: "12px 8px 4px" }}>{children}</div>;
}

export function QuickRepliesScript({ replies, loading, fillName, busy, error, onClose, onBack, onInsert, onSend }: {
  replies: Reply[]; loading?: boolean; fillName: (t: string) => string; busy: boolean; error: string;
  onClose: () => void; onBack: () => void; onInsert?: (t: string) => void; onSend: (replyId: number) => void;
}) {
  const [q, setQ] = useState("");
  const [automations, setAutomations] = useState(false);
  const [stage, setStage] = useState<string>(() => { try { return localStorage.getItem(LS_STAGE) ?? FLOW[0].key; } catch { return FLOW[0].key; } });
  const [selId, setSelId] = useState<number | null>(null);
  const [fav, setFav] = useState<number[]>(() => readIds(LS_FAV));
  const [recent, setRecent] = useState<number[]>(() => readIds(LS_RECENT));
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.innerWidth < 900);
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => { const f = () => setNarrow(window.innerWidth < 900); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);

  // Розділи: відомі кроки й ситуації — у своєму порядку; розділи з номенклатури (kind) і нові категорії — у «Товари з цінами»
  const { products, others } = useMemo(() => {
    const known = new Set([...FLOW, ...SITUATIONS].map((s) => s.key));
    const cats = new Map<string, { kind: boolean; n: number }>();
    replies.forEach((r) => {
      const c = r.category || "";
      if (!c || known.has(c)) return;
      const cur = cats.get(c) || { kind: false, n: 0 };
      cats.set(c, { kind: cur.kind || !!r.kind, n: cur.n + 1 });
    });
    const icon = (c: string) => /викраск/i.test(c) ? "🖌" : /тест/i.test(c) ? "🧪" : /фарб/i.test(c) ? "🪣" : "📦";
    const list = Array.from(cats.entries()).sort((a, b) => Number(b[1].kind) - Number(a[1].kind) || a[0].localeCompare(b[0], "uk"))
      .map(([c, v]) => ({ key: c, label: c, icon: icon(c), group: "products" as const, next: "",
        goal: v.kind ? "Описи з цінами з номенклатури: ціни підставляються актуальні, нова позиція в папці — нова відповідь тут." : "" }));
    return { products: list, others: replies.some((r) => !r.category) ? [OTHER] : [] };
  }, [replies]);
  const all: Stage[] = useMemo(() => [FAV, RECENT, ...FLOW, ...SITUATIONS, ...products, ...others], [products, others]);
  const byId = useMemo(() => new Map(replies.map((r) => [r.id, r])), [replies]);
  const inStage = (k: string): Reply[] => k === "__fav" ? fav.map((id) => byId.get(id)).filter(Boolean) as Reply[]
    : k === "__recent" ? recent.map((id) => byId.get(id)).filter(Boolean) as Reply[]
    : replies.filter((r) => (r.category || "") === k).sort((a, b) => (a.sort || 0) - (b.sort || 0) || a.id - b.id);
  const cur = all.find((s) => s.key === stage) || FLOW[0];
  const pick = (k: string) => { setStage(k); setQ(""); setSelId(null); try { localStorage.setItem(LS_STAGE, k); } catch { /* приватний режим */ } };

  const list = useMemo(() => {
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (words.length) return replies.filter((r) => { const hay = `${r.title} ${r.text} ${r.when_to_use || ""} ${r.category || ""}`.toLowerCase(); return words.every((w) => hay.includes(w)); });
    return inStage(cur.key);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replies, q, cur.key, fav, recent]);
  const sel = list.find((r) => r.id === selId) || list[0] || null;
  const hasAssets = !!sel && (sel.asset_ids || []).length > 0;
  const isFav = !!sel && fav.includes(sel.id);

  function toggleFav(id: number) { setFav((v) => { const n = v.includes(id) ? v.filter((x) => x !== id) : [id, ...v]; writeIds(LS_FAV, n); return n; }); }
  function use(r: Reply | null) {
    if (!r || busy) return;
    setRecent((v) => { const n = [r.id, ...v.filter((x) => x !== r.id)].slice(0, 10); writeIds(LS_RECENT, n); return n; });
    if ((r.asset_ids || []).length > 0 || !onInsert) { onSend(r.id); return; }
    onInsert(fillName(r.text || ""));
  }
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
      if (automations || (e.target as HTMLElement)?.closest("button")) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (!list.length) return;
        e.preventDefault();
        const i = Math.max(0, list.findIndex((r) => r.id === sel?.id));
        const n = e.key === "ArrowDown" ? Math.min(list.length - 1, i + 1) : Math.max(0, i - 1);
        setSelId(list[n].id);
        listRef.current?.querySelector<HTMLElement>(`[data-rid="${list[n].id}"]`)?.scrollIntoView({ block: "nearest" });
      }
      if (e.key === "Enter" && !e.shiftKey && (e.target as HTMLElement)?.tagName !== "TEXTAREA") { e.preventDefault(); use(sel); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  const count = (k: string) => inStage(k).length;
  const side = (items: Stage[]) => items.map((s) => <SideItem key={s.key || "_other"} s={s} on={!q && s.key === cur.key} count={count(s.key)} onPick={pick} />);
  const productStage = cur.group === "products" && !q;

  if (automations) return <AutomationMessages onBack={() => setAutomations(false)} onClose={onClose} />;

  return <div role="dialog" aria-label="Швидкі відповіді — скрипт продажів" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(15,23,42,.38)", display: "flex", alignItems: "center", justifyContent: "center", padding: narrow ? 6 : 16 }}>
    <div style={{ width: "min(1180px, 100%)", height: narrow ? "96vh" : "min(760px, 92vh)", background: "#fff", borderRadius: 14, boxShadow: "0 24px 64px rgba(15,23,42,.3)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* шапка */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderBottom: "1px solid #e2e8f0", flexWrap: "wrap" }}>
        <b style={{ fontSize: 15 }}><Icon n="⚡" size={15} /> Швидкі відповіді</b>
        <button className="btn" type="button" onClick={() => setAutomations(true)} style={{ background: "#e5f2e9", fontSize: 12 }}>Оплата, доставка, майстер-класи · автоматичні повідомлення</button>
        <input value={q} onChange={(e) => { setQ(e.target.value); setSelId(null); }} autoFocus placeholder="Пошук по всіх розділах: «дорого», «галатея», «доставка»…"
          style={{ flex: "1 1 240px", minWidth: 180, height: 34, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", fontSize: 13 }} />
        <button className="btn btn-light" type="button" onClick={onBack} style={{ fontSize: 12 }}><Icon n="🎨" size={13} /> Кольори й каталоги</button>
        <button className="btn" type="button" onClick={onClose} aria-label="Закрити" style={{ padding: "2px 9px" }}>×</button>
      </div>
      {narrow && <div style={{ display: "flex", gap: 6, overflowX: "auto", padding: "7px 10px", borderBottom: "1px solid #eef2f7", background: "#f8fafc" }}>
        {all.filter((s) => count(s.key) > 0 || s.group === "flow").map((s) => {
          const on = !q && s.key === cur.key;
          return <button key={s.key || "_o"} type="button" onClick={() => pick(s.key)} style={{ flex: "0 0 auto", border: `1px solid ${on ? "#2E6FB0" : "#dbe3ee"}`, background: on ? "#e6eef8" : "#fff", borderRadius: 999, padding: "4px 10px", fontSize: 12, fontWeight: on ? 700 : 500, whiteSpace: "nowrap" }}>
            {s.step ? `${s.step}. ` : <Icon n={s.icon} size={12} />} {s.label} <span style={{ color: "#7b8496" }}>{count(s.key)}</span></button>;
        })}
      </div>}
      <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: narrow ? "1fr" : "220px minmax(0, 1fr) minmax(0, 1.15fr)", gridTemplateRows: narrow ? "minmax(0, 1fr) auto" : "1fr" }}>
        {/* навігація */}
        {!narrow && <nav style={{ overflowY: "auto", borderRight: "1px solid #eef2f7", background: "#f8fafc", padding: "4px 6px 10px" }} aria-label="Розділи">
          {(fav.length > 0 || recent.length > 0) && <><GroupLabel>Мої</GroupLabel>{side([FAV, RECENT].filter((s) => count(s.key) > 0))}</>}
          <GroupLabel>Хід розмови</GroupLabel>{side(FLOW)}
          <GroupLabel>Ситуації</GroupLabel>{side(SITUATIONS)}
          {products.length > 0 && <><GroupLabel>Матеріали та майстер-класи</GroupLabel>{side(products)}</>}
          {others.length > 0 && <><GroupLabel>Без розділу</GroupLabel>{side(others)}</>}
        </nav>}
        {/* список */}
        <div ref={listRef} style={{ overflowY: "auto", padding: "10px 12px", borderRight: narrow ? "none" : "1px solid #eef2f7" }}>
          {!q && cur.goal && <div style={{ background: "#f1f5f9", borderRadius: 8, padding: "8px 10px", fontSize: 12.5, lineHeight: 1.45, marginBottom: 8 }}>
            <b>{cur.step ? `Крок ${cur.step}. ` : ""}{cur.label}.</b> {cur.goal}
            {(cur.next || cur.key === "Тест-набір") && <div style={{ marginTop: 4, display: "flex", gap: 12, flexWrap: "wrap" }}>
              {cur.next && <button type="button" onClick={() => pick(cur.next)} style={{ border: 0, background: "none", color: "#2E6FB0", cursor: "pointer", padding: 0, fontSize: 12.5, fontWeight: 600 }}>Далі: {cur.next} →</button>}
              {cur.key === "Тест-набір" && products.some((s) => /тест/i.test(s.key)) && <button type="button" onClick={() => pick(products.find((s) => /тест/i.test(s.key))!.key)} style={{ border: 0, background: "none", color: "#2E6FB0", cursor: "pointer", padding: 0, fontSize: 12.5, fontWeight: 600 }}>Ціни по матеріалах →</button>}
            </div>}
          </div>}
          {q && <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Знайдено: {list.length}</div>}
          {loading && replies.length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>Завантажую…</div>}
          {!loading && list.length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>{cur.key === "__fav" ? "Поки порожньо — натисніть ☆ у відповіді." : "Тут поки немає відповідей. Додати — Налаштування → Відкриті лінії → Швидкі відповіді."}</div>}
          {list.map((r) => {
            const on = sel?.id === r.id;
            const stageOf = (all.find((s) => s.key === (r.category || "")) || OTHER).label;
            return <button key={r.id} data-rid={r.id} type="button" onClick={() => setSelId(r.id)} onDoubleClick={() => use(r)}
              style={{ display: "block", width: "100%", textAlign: "left", border: `1px solid ${on ? "#2E6FB0" : "#e2e8f0"}`, background: on ? "#f3f8fe" : "#fff", borderRadius: 9, padding: productStage ? "7px 10px" : "8px 10px", marginBottom: 6, cursor: "pointer" }}>
              <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
                {fav.includes(r.id) && <span title="в обраних" style={{ color: "#d97706", fontSize: 12 }}>★</span>}
                <b style={{ fontSize: 13, flex: 1, minWidth: 0 }}>{r.title}</b>
                {(r.asset_ids || []).length > 0 && <span title="з фото/відео" style={{ fontSize: 11, color: "#64748b" }}><Icon n="🖼" size={12} /></span>}
                {r.price_range && <span style={{ fontSize: 12.5, fontWeight: 700, color: "#166534", whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>{r.price_range}</span>}
                {q && <span className="muted" style={{ fontSize: 11, whiteSpace: "nowrap" }}>{stageOf}</span>}
              </div>
              {!productStage && r.when_to_use && <div style={{ fontSize: 11.5, color: "#2E6FB0", marginTop: 2, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>Коли: {r.when_to_use}</div>}
              <div className="muted" style={{ fontSize: 12, marginTop: 3, display: "-webkit-box", WebkitLineClamp: productStage ? 1 : 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{r.text}</div>
            </button>;
          })}
        </div>
        {/* перегляд */}
        <div style={{ display: "flex", flexDirection: "column", minHeight: 0, padding: "10px 14px", borderTop: narrow ? "1px solid #e2e8f0" : "none", maxHeight: narrow ? "46vh" : undefined }}>
          {sel ? <>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <b style={{ fontSize: 14.5, flex: 1 }}>{sel.title}</b>
              <button type="button" onClick={() => toggleFav(sel.id)} title={isFav ? "Прибрати з обраних" : "Додати в обрані"} aria-pressed={isFav}
                style={{ border: "1px solid #e2e8f0", background: isFav ? "#fffbeb" : "#fff", color: isFav ? "#d97706" : "#64748b", borderRadius: 8, padding: "2px 8px", cursor: "pointer", fontSize: 13 }}>{isFav ? "★ В обраних" : "☆ В обрані"}</button>
            </div>
            {sel.when_to_use && <div style={{ fontSize: 12.5, lineHeight: 1.45, color: "#1e3a5f", background: "#eef5fc", borderRadius: 8, padding: "6px 9px", margin: "6px 0" }}><b>Коли:</b> {sel.when_to_use}</div>}
            <div style={{ flex: 1, minHeight: 90, overflowY: "auto", whiteSpace: "pre-wrap", fontSize: 13.5, lineHeight: 1.5, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 9, padding: "10px 12px" }}>
              <Highlight text={fillName(sel.text || "")} />
            </div>
            {(sel.products || []).length > 0 && <details style={{ marginTop: 6, fontSize: 12 }}>
              <summary style={{ cursor: "pointer", color: "#475569" }}>Ціни з номенклатури — {sel.products!.length} поз. (оновлюються самі{sel.folder ? `, папка «${sel.folder}»` : ""})</summary>
              <div style={{ maxHeight: 120, overflowY: "auto", marginTop: 4 }}>{sel.products!.map((p) => <div key={p.id} style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "2px 0", borderBottom: "1px solid #f1f5f9" }}>
                <span style={{ minWidth: 0 }}>{p.name}</span><b style={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>{Number(p.price).toLocaleString("uk-UA")} ₴</b></div>)}</div>
            </details>}
            {/\[[^\]\n]{1,40}\]|\{[^}\n]{1,30}\}/.test(fillName(sel.text || "")) && <div style={{ fontSize: 11.5, color: "#92400e", marginTop: 5 }}>Жовті поля заповніть перед відправкою: поля в [дужках] сервер не відправить, а поля у {"{фігурних}"} дужках клієнт побачить як є.</div>}
            {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 5 }}>{error}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
              <button className="btn btn-primary" type="button" disabled={busy} onClick={() => use(sel)}>
                {busy ? "…" : hasAssets || !onInsert ? "Надіслати з фото/відео" : "Вставити в поле ⏎"}
              </button>
              <span className="muted" style={{ fontSize: 11.5 }}>{hasAssets ? "Фото/відео підуть разом із текстом." : "Текст зʼявиться в полі вводу — перевірте і надішліть самі."} ↑↓ — вибір, Enter — вставити, Esc — закрити, «/» у порожньому полі чату — відкрити це вікно.</span>
            </div>
          </> : <div className="muted" style={{ fontSize: 12.5 }}>Оберіть відповідь зліва.</div>}
        </div>
      </div>
    </div>
  </div>;
}
