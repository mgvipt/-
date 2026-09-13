/* Відгуки поза розділом «Відгуки» (13.09.2026):
 *  AskReviewButton — «⭐ Попросити відгук» у чаті й картці угоди. Спершу показує ТОЧНИЙ текст і куди він піде,
 *    надсилає лише після «Надіслати» (ручна дія менеджера). Поки тестовий режим — лише тестовим контактам.
 *  ReviewOptOutToggle — «Не просити відгуки» у картці клієнта (поставити може кожен, зняти — власник).
 * Компоненти на рівні модуля (не всередині інших) — поля не втрачають фокус. */
import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";

type AskResult = {
  ok: boolean; can_send: boolean; sent: boolean; reason: string; text: string; channel_label: string;
  deal_id: number | null; deal_title?: string; conversation_id: number | null; test_mode?: boolean;
};
type OptOut = { opt_out: boolean; reason: string; can_remove: boolean };

function reasonOf(e: unknown, fallback: string): string {
  const d = (e as { data?: { reason?: string; detail?: string } } | null)?.data;
  return d?.reason || d?.detail || fallback;
}

const OVERLAY: CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1000,
  display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
};
const BOX: CSSProperties = {
  background: "#fff", borderRadius: 14, width: "min(560px, 100%)", maxHeight: "90vh", overflowY: "auto",
  padding: 18, boxShadow: "0 20px 50px rgba(0,0,0,.25)", fontSize: 14, lineHeight: 1.5, color: "#0f172a",
};
const TEXT_BOX: CSSProperties = {
  whiteSpace: "pre-wrap", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10,
  padding: "10px 12px", margin: "8px 0", fontSize: 14,
};
const NOTE_BOX: CSSProperties = {
  background: "#fff7ed", border: "1px solid #fdba74", borderRadius: 10, padding: "10px 12px", margin: "8px 0",
};

export function AskReviewButton({ dealId, convId, style }: { dealId?: number; convId?: number; style?: CSSProperties }) {
  const [open, setOpen] = useState(false);
  const [res, setRes] = useState<AskResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const preview = async () => {
    setOpen(true);
    setBusy(true);
    setErr("");
    setRes(null);
    try {
      setRes(await api.post<AskResult>("/api/reviews/requests/", { deal_id: dealId, conversation_id: convId, confirm: false }));
    } catch (e) {
      setErr(reasonOf(e, "Не вдалося підготувати просьбу"));
    } finally {
      setBusy(false);
    }
  };
  const send = async () => {
    if (!res) return;
    setBusy(true);
    setErr("");
    try {
      setRes(await api.post<AskResult>("/api/reviews/requests/", {
        deal_id: res.deal_id, conversation_id: res.conversation_id ?? undefined, confirm: true,
      }));
    } catch (e) {
      setErr(reasonOf(e, "Не вдалося надіслати"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button className="btn" onClick={preview}
        title="Надіслати клієнту затверджену просьбу про відгук з особистим посиланням (спершу покаже текст)"
        style={{ height: 30, fontSize: 12.5, padding: "0 10px", background: "#fffbeb", color: "#b45309", fontWeight: 600,
          border: "1px solid #fde68a", whiteSpace: "nowrap", ...style }}>
        ⭐ Попросити відгук
      </button>
      {open && createPortal(
        <div style={OVERLAY} onClick={() => !busy && setOpen(false)}>
          <div style={BOX} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: "0 0 6px" }}>⭐ Попросити відгук</h3>
            {busy && !res && <div className="muted">Готую текст…</div>}
            {res && res.deal_id && (
              <div className="muted" style={{ fontSize: 13 }}>Угода #{res.deal_id}{res.deal_title ? ` · ${res.deal_title}` : ""}</div>
            )}
            {res && !res.can_send && !res.sent && <div style={NOTE_BOX}>{res.reason}</div>}
            {res && res.can_send && (
              <>
                <div style={{ marginTop: 6 }}><b>Куди:</b> {res.channel_label}</div>
                <div style={{ marginTop: 6 }}><b>Текст, який отримає клієнт:</b></div>
                <div style={TEXT_BOX}>{res.text}</div>
                <div className="muted" style={{ fontSize: 12 }}>
                  Особисте посилання (замість •••) CRM створить у момент надсилання. Відгук прийде в розділ «Відгуки».
                </div>
              </>
            )}
            {res && res.sent && (
              <>
                <div style={{ ...NOTE_BOX, background: "#ecfdf5", borderColor: "#6ee7b7" }}>✓ {res.reason}</div>
                <div style={TEXT_BOX}>{res.text}</div>
              </>
            )}
            {err && <div style={{ color: "#dc2626", fontSize: 13, marginTop: 6 }}>{err}</div>}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12, flexWrap: "wrap" }}>
              {res && res.can_send && !res.sent && (
                <button className="btn btn-green" disabled={busy} onClick={send}>{busy ? "Надсилаю…" : "Надіслати клієнту"}</button>
              )}
              <button className="btn btn-light" disabled={busy} onClick={() => setOpen(false)}>
                {res && res.can_send && !res.sent ? "Скасувати" : "Закрити"}
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

export function ReviewOptOutToggle({ contactId }: { contactId: number }) {
  const [st, setSt] = useState<OptOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const load = useCallback(() => (
    api.get<OptOut>(`/api/reviews/opt-out/?contact_id=${contactId}`).then(setSt).catch(() => setSt(null))
  ), [contactId]);
  useEffect(() => { load(); }, [load]);
  if (!st) return null;
  const locked = st.opt_out && !st.can_remove;
  const toggle = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.post("/api/reviews/opt-out/", { contact_id: contactId, opt_out: !st.opt_out });
      await load();
    } catch (e) {
      setErr(reasonOf(e, "Не вдалося змінити"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5,
      color: st.opt_out ? "#b91c1c" : "#475569", cursor: locked ? "not-allowed" : "pointer" }}
      title={locked ? "Зняти позначку може лише власник" : "Клієнт не отримуватиме просьб про відгук — ні автоматичних, ні через кнопку"}>
      <input type="checkbox" checked={st.opt_out} disabled={busy || locked} onChange={toggle} />
      🚫 Не просити відгуки{st.opt_out && st.reason ? ` (${st.reason})` : ""}
      {err && <span style={{ color: "#dc2626" }}> {err}</span>}
    </label>
  );
}
