/* Помічник формування повідомлення клієнту. Бере ЧЕРНЕТКУ менеджера і повертає
 * покращений (грамотно, тон Wallcov, та сама мова) або перекладений (на мову
 * клієнта) варіант. НІЧОГО не надсилає — менеджер вставляє варіант у поле і сам
 * тисне «Надіслати». Використовується у всіх місцях чату (Inbox, картка клієнта,
 * старт діалогу). */
import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { Icon } from "./Icon";

type Mode = "improve" | "translate";

export function AiComposeAssist({ draft, convId, contactId, onApply, compact = false, up = true, t }: {
  draft: string;
  convId?: number | null;
  contactId?: number | null;
  onApply: (text: string) => void;
  compact?: boolean;
  up?: boolean;
  t?: (ru: string, uk: string) => string;
}) {
  const tr = t || ((_ru: string, uk: string) => uk);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState<"" | Mode>("");
  const [result, setResult] = useState("");
  const [err, setErr] = useState("");
  const btnRef = useRef<HTMLButtonElement>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  useEffect(() => {
    if (!open) return;
    const upd = () => { if (btnRef.current) setRect(btnRef.current.getBoundingClientRect()); };
    upd();
    window.addEventListener("scroll", upd, true); window.addEventListener("resize", upd);
    return () => { window.removeEventListener("scroll", upd, true); window.removeEventListener("resize", upd); };
  }, [open]);

  async function run(mode: Mode) {
    if (!draft.trim()) { setErr(tr("Сначала напишите черновик сообщения", "Спочатку напишіть чернетку повідомлення")); setOpen(true); return; }
    setLoading(mode); setErr(""); setResult(""); setOpen(true);
    try {
      const r = await api.post<any>("/api/conversations/ai_compose/", {
        draft, mode, conversation_id: convId || undefined, contact_id: contactId || undefined,
      });
      const txt = (r?.text || "").trim();
      setResult(txt);
      if (!txt) setErr(tr("Помощник не вернул текст", "Помічник не повернув текст"));
    } catch (e: any) {
      setErr(e?.response?.data?.detail || tr("Помощник временно недоступен", "Помічник тимчасово недоступний"));
    }
    setLoading("");
  }

  return (
    <div style={{ position: "relative", flex: "0 0 auto" }}>
      <button ref={btnRef} className="btn" type="button" title={tr("Помощник: улучшить или перевести черновик перед отправкой", "Помічник: покращити або перекласти чернетку перед відправкою")}
        style={{ background: "#ede9fe", color: "#6d28d9", fontWeight: 600, height: compact ? 38 : undefined, whiteSpace: "nowrap" }}
        onClick={() => (open ? setOpen(false) : run("improve"))}>
        <Icon n="✨" size={16} />{!compact && <> {tr("Помощник", "Помічник")}</>}
      </button>
      {open && rect && createPortal(
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 4000 }} />
          <div style={(() => {
            const w = Math.min(330, window.innerWidth * 0.86);
            const left = Math.max(8, Math.min(rect.right - w, window.innerWidth - w - 8));
            const base: React.CSSProperties = { position: "fixed", left, width: w, zIndex: 4001, maxHeight: "72vh", overflowY: "auto", background: "#fff", border: "1px solid #ddd6fe", borderRadius: 12, boxShadow: "0 16px 40px rgba(76,29,149,.28)", padding: 12 };
            return up ? { ...base, bottom: window.innerHeight - rect.top + 6 } : { ...base, top: rect.bottom + 6 };
          })()}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 9 }}>
              <Icon n="✨" size={15} />
              <b style={{ fontSize: 13, color: "#5b21b6" }}>{tr("Помощник сообщения", "Помічник повідомлення")}</b>
              <button type="button" onClick={() => setOpen(false)} style={{ marginLeft: "auto", border: "none", background: "transparent", cursor: "pointer", color: "#94a3b8", fontSize: 16, lineHeight: 1 }}>✕</button>
            </div>
            <div style={{ display: "flex", gap: 6, marginBottom: 9 }}>
              <button className="btn" type="button" style={{ flex: 1, fontSize: 12, background: "#f5f3ff", color: "#6d28d9" }} disabled={!!loading} onClick={() => run("improve")}>{loading === "improve" ? "…" : tr("✍️ Улучшить", "✍️ Покращити")}</button>
              <button className="btn" type="button" style={{ flex: 1, fontSize: 12, background: "#f5f3ff", color: "#6d28d9" }} disabled={!!loading} onClick={() => run("translate")}>{loading === "translate" ? "…" : tr("🌐 Перевести клиенту", "🌐 Перекласти клієнту")}</button>
            </div>
            {err && <div style={{ color: "#dc2626", fontSize: 12, marginBottom: 6 }}>{err}</div>}
            {loading && <div className="muted" style={{ fontSize: 12.5 }}>{tr("Помощник думает…", "Помічник думає…")}</div>}
            {result && !loading && (
              <>
                <div style={{ fontSize: 13, background: "#faf5ff", border: "1px solid #e9d5ff", borderRadius: 8, padding: 9, whiteSpace: "pre-wrap", lineHeight: 1.5, maxHeight: 200, overflowY: "auto", marginBottom: 8, color: "#1e1b4b" }}>{result}</div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button className="btn btn-primary" type="button" style={{ flex: 1, fontSize: 12.5 }} onClick={() => { onApply(result); setOpen(false); }}><Icon n="✍️" size={13} /> {tr("Вставить в поле", "Вставити у поле")}</button>
                  <button className="btn" type="button" style={{ fontSize: 12.5 }} onClick={() => { navigator.clipboard?.writeText(result); }} title={tr("Скопировать", "Скопіювати")}><Icon n="📋" size={14} /></button>
                </div>
                <div className="muted" style={{ fontSize: 10.5, marginTop: 6, lineHeight: 1.35 }}>{tr("Можно отредактировать после вставки. Клиенту уйдёт только когда вы нажмёте «Отправить».", "Можна відредагувати після вставки. Клієнту піде лише коли ви натиснете «Надіслати».")}</div>
              </>
            )}
          </div>
        </>, document.body)}
    </div>
  );
}
