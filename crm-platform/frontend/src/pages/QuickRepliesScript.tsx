import { useEffect, useMemo, useRef, useState } from "react";

/* Швидкі відповіді як «скрипт продажів» (14.09, запит Олега): велике вікно, зліва — етапи розмови
 * в порядку скрипта, зверху — карта розмови (куди вести клієнта далі), посередині — відповіді етапу
 * з підказкою «коли», праворуч — повний текст. Клік «Вставити» — текст іде в поле вводу, НЕ клієнту.
 * Незаповнені поля [сума] підсвічені; сервер не відправить повідомлення з ними. */

type Reply = { id: number; title: string; text: string; asset_ids: number[]; category?: string; when_to_use?: string };
type Stage = { key: string; label: string; icon: string; goal: string; next: string };

// Порядок = хід розмови (аналіз продажів 12.09, «Скрипт продажів Wallcov»).
const STAGES: Stage[] = [
  { key: "Виявлення потреби", label: "Виявлення потреби", icon: "🔎", next: "Розрахунок і ціна",
    goal: "Дізнатися кімнату, площу, стиль. Клієнт, що назвав площу, купує в 14% випадків (без неї — 5%), надіслав фото стіни — у 28%." },
  { key: "Розрахунок і ціна", label: "Розрахунок і ціна", icon: "🧮", next: "Тест-набір",
    goal: "Назвати суму під його площу, а не прайс. Дати вибір із двох варіантів і спитати, що ближче." },
  { key: "Тест-набір", label: "Тест-набір", icon: "🎨", next: "Закриття на оплату",
    goal: "Тест-набір — крок до рішення, коли клієнт вагається з кольором або фактурою." },
  { key: "Заперечення", label: "Заперечення", icon: "💬", next: "Закриття на оплату",
    goal: "«Дорого» і «подумаю» — це інтерес: такі клієнти платять у 22% і 15% випадків. Відповісти по суті і дати наступний крок." },
  { key: "Закриття на оплату", label: "Закриття на оплату", icon: "✅", next: "Після оплати",
    goal: "Реквізити або посилання, резерв товару. Наступного дня — нагадування: після посилання за тиждень платить лише половина." },
  { key: "Після оплати", label: "Після оплати", icon: "📦", next: "Тест → основне замовлення",
    goal: "ТТН, інструкція з нанесення, прохання про відгук." },
  { key: "Тест → основне замовлення", label: "Тест → основне", icon: "🔁", next: "",
    goal: "Після тест-набору спитати площу і зробити розрахунок: так основне замовлення роблять у 22% випадків замість 7–11%." },
  { key: "Дожими і повернення з ігнору", label: "Дожими", icon: "⏰", next: "",
    goal: "Клієнт замовк. Дожим 1 — через 2 дні, особисто, по його ситуації. Дожим 2 — теплим через 4–5 днів з новою користю. Далі стоп." },
];
const OTHER: Stage = { key: "", label: "Інше", icon: "📁", goal: "Відповіді без етапу. Етап задається в Налаштування → Швидкі відповіді.", next: "" };
const LS = "qr_script_stage";

function Highlight({ text }: { text: string }) {
  const parts = text.split(/(\[[^\]\n]{1,40}\])/g);
  return <>{parts.map((p, i) => /^\[[^\]]+\]$/.test(p) && !/^\[\d+\/\d+\]$/.test(p)
    ? <mark key={i} style={{ background: "#fde68a", color: "#78350f", borderRadius: 4, padding: "0 3px" }}>{p}</mark>
    : <span key={i}>{p}</span>)}</>;
}

export function QuickRepliesScript({ replies, fillName, busy, error, onClose, onBack, onInsert, onSend }: {
  replies: Reply[]; fillName: (t: string) => string; busy: boolean; error: string;
  onClose: () => void; onBack: () => void; onInsert?: (t: string) => void; onSend: (replyId: number) => void;
}) {
  const [q, setQ] = useState("");
  const [stage, setStage] = useState<string>(() => { try { return localStorage.getItem(LS) ?? STAGES[0].key; } catch { return STAGES[0].key; } });
  const [selId, setSelId] = useState<number | null>(null);
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.innerWidth < 820);
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => { const f = () => setNarrow(window.innerWidth < 820); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);

  // етапи: відомі — у порядку скрипта; нові категорії з Налаштувань — у кінці; «Інше» — якщо є без етапу
  const stages = useMemo(() => {
    const cats = new Set(replies.map((r) => r.category || ""));
    const known = new Set(STAGES.map((s) => s.key));
    const extra: Stage[] = Array.from(cats).filter((c) => c && !known.has(c)).sort()
      .map((c) => ({ key: c, label: c, icon: "📁", goal: "", next: "" }));
    return [...STAGES, ...extra, ...(cats.has("") ? [OTHER] : [])];
  }, [replies]);
  const count = (k: string) => replies.filter((r) => (r.category || "") === k).length;
  const cur = stages.find((s) => s.key === stage) || stages[0];
  const pickStage = (k: string) => { setStage(k); setQ(""); setSelId(null); try { localStorage.setItem(LS, k); } catch { /* приватний режим */ } };

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (s) return replies.filter((r) => `${r.title} ${r.text} ${r.when_to_use || ""} ${r.category || ""}`.toLowerCase().includes(s));
    return replies.filter((r) => (r.category || "") === cur.key);
  }, [replies, q, cur.key]);
  const sel = list.find((r) => r.id === selId) || list[0] || null;
  const hasAssets = !!sel && (sel.asset_ids || []).length > 0;

  function use(r: Reply | null) {
    if (!r || busy) return;
    if ((r.asset_ids || []).length > 0 || !onInsert) { onSend(r.id); return; }
    onInsert(fillName(r.text || ""));
  }
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
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

  const chip = (s: Stage) => {
    const on = !q && s.key === cur.key;
    return <button key={s.key || "_other"} type="button" onClick={() => pickStage(s.key)}
      style={{ border: `1px solid ${on ? "#2E6FB0" : "#dbe3ee"}`, background: on ? "#e6eef8" : "#fff", color: "#1b2230", borderRadius: 999, padding: "4px 10px", fontSize: 12, fontWeight: on ? 700 : 500, whiteSpace: "nowrap", cursor: "pointer" }}>
      {s.icon} {s.label} <span style={{ color: "#7b8496", fontWeight: 500 }}>{count(s.key)}</span>
    </button>;
  };
  const flow = stages.filter((s) => s.key !== "Дожими і повернення з ігнору" && s.key !== "Тест → основне замовлення" && s.key !== "");
  const side = stages.filter((s) => !flow.includes(s));

  return <div role="dialog" aria-label="Швидкі відповіді — скрипт продажів" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(15,23,42,.38)", display: "flex", alignItems: "center", justifyContent: "center", padding: narrow ? 6 : 16 }}>
    <div style={{ width: "min(1080px, 100%)", height: narrow ? "96vh" : "min(720px, 92vh)", background: "#fff", borderRadius: 14, boxShadow: "0 24px 64px rgba(15,23,42,.3)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* шапка */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", borderBottom: "1px solid #e2e8f0", flexWrap: "wrap" }}>
        <b style={{ fontSize: 15 }}>⚡ Швидкі відповіді — скрипт продажів</b>
        <input value={q} onChange={(e) => { setQ(e.target.value); setSelId(null); }} autoFocus placeholder="Пошук по всіх етапах: «дорого», «доставка», «тест»…"
          style={{ flex: "1 1 220px", minWidth: 180, height: 32, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", fontSize: 13 }} />
        <button className="btn btn-light" type="button" onClick={onBack} style={{ fontSize: 12 }}>🎨 Матеріали</button>
        <button className="btn" type="button" onClick={onClose} aria-label="Закрити" style={{ padding: "2px 9px" }}>×</button>
      </div>
      {/* карта розмови */}
      <div style={{ padding: "8px 14px", borderBottom: "1px solid #eef2f7", background: "#f8fafc", overflowX: "auto" }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 5 }}>Карта розмови — веди клієнта зліва направо</div>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: narrow ? "nowrap" : "wrap" }}>
          {flow.map((s, i) => <span key={s.key} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>{chip(s)}{i < flow.length - 1 && <span style={{ color: "#94a3b8" }}>→</span>}</span>)}
          {side.length > 0 && <span style={{ color: "#94a3b8", margin: "0 4px" }}>·</span>}
          {side.map(chip)}
        </div>
      </div>
      {/* тіло */}
      <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: narrow ? "1fr" : "minmax(0, 1fr) minmax(0, 1.15fr)", gridTemplateRows: narrow ? "minmax(0, 1fr) auto" : "1fr" }}>
        <div ref={listRef} style={{ overflowY: "auto", padding: "10px 12px", borderRight: narrow ? "none" : "1px solid #eef2f7" }}>
          {!q && <div style={{ background: "#f1f5f9", borderRadius: 8, padding: "8px 10px", fontSize: 12.5, lineHeight: 1.45, marginBottom: 8 }}>
            <b>{cur.icon} {cur.label}.</b> {cur.goal}
            {cur.next && <div style={{ marginTop: 4 }}>Далі: <button type="button" onClick={() => pickStage(cur.next)} style={{ border: 0, background: "none", color: "#2E6FB0", cursor: "pointer", padding: 0, fontSize: 12.5, fontWeight: 600 }}>{cur.next} →</button></div>}
          </div>}
          {q && <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Знайдено: {list.length}</div>}
          {list.length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>Тут поки немає відповідей. Додати — Налаштування → Швидкі відповіді (поле «Категорія»).</div>}
          {list.map((r) => {
            const on = sel?.id === r.id;
            return <button key={r.id} data-rid={r.id} type="button" onClick={() => setSelId(r.id)} onDoubleClick={() => use(r)}
              style={{ display: "block", width: "100%", textAlign: "left", border: `1px solid ${on ? "#2E6FB0" : "#e2e8f0"}`, background: on ? "#f3f8fe" : "#fff", borderRadius: 9, padding: "8px 10px", marginBottom: 6, cursor: "pointer" }}>
              <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
                <b style={{ fontSize: 13 }}>{r.title}</b>
                {(r.asset_ids || []).length > 0 && <span title="з фото/відео" style={{ fontSize: 11 }}>🖼</span>}
                {q && <span className="muted" style={{ fontSize: 11, marginLeft: "auto", whiteSpace: "nowrap" }}>{(stages.find((s) => s.key === (r.category || "")) || OTHER).label}</span>}
              </div>
              {r.when_to_use && <div style={{ fontSize: 11.5, color: "#2E6FB0", marginTop: 2 }}>Коли: {r.when_to_use}</div>}
              <div className="muted" style={{ fontSize: 12, marginTop: 3, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{r.text}</div>
            </button>;
          })}
        </div>
        <div style={{ display: "flex", flexDirection: "column", minHeight: 0, padding: "10px 14px", borderTop: narrow ? "1px solid #e2e8f0" : "none", maxHeight: narrow ? "42vh" : undefined }}>
          {sel ? <>
            <b style={{ fontSize: 14 }}>{sel.title}</b>
            {sel.when_to_use && <div style={{ fontSize: 12.5, color: "#2E6FB0", margin: "3px 0 6px" }}>Коли використовувати: {sel.when_to_use}</div>}
            <div style={{ flex: 1, minHeight: 0, overflowY: "auto", whiteSpace: "pre-wrap", fontSize: 13.5, lineHeight: 1.5, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 9, padding: "10px 12px" }}>
              <Highlight text={fillName(sel.text || "")} />
            </div>
            {/\[[^\]\n]{1,40}\]/.test(sel.text || "") && <div style={{ fontSize: 11.5, color: "#92400e", marginTop: 5 }}>Жовті поля в [дужках] заповніть перед відправкою — з ними повідомлення не піде.</div>}
            {error && <div style={{ color: "#dc2626", fontSize: 12, marginTop: 5 }}>{error}</div>}
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <button className="btn btn-primary" type="button" disabled={busy} onClick={() => use(sel)}>
                {busy ? "…" : hasAssets || !onInsert ? "Надіслати з фото/відео" : "Вставити в поле ⏎"}
              </button>
              <span className="muted" style={{ fontSize: 11.5, alignSelf: "center" }}>{hasAssets ? "Фото/відео підуть разом із текстом." : "Текст зʼявиться в полі вводу — перевірте і надішліть самі."} ↑↓ — вибір, Enter — вставити, Esc — закрити.</span>
            </div>
          </> : <div className="muted" style={{ fontSize: 12.5 }}>Оберіть відповідь зліва.</div>}
        </div>
      </div>
    </div>
  </div>;
}
