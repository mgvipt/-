// fbcomment 15.09.2026: у чаті-КОМЕНТАРІ Meta показуємо НАД полем вводу, куди саме піде відповідь.
// Раніше менеджер не бачив, що відповідь у FB/IG-коментарі публікується ПУБЛІЧНО в гілці, а при помилці
// бачив лише червоний ✕ без причини. Звичайні чати Messenger/Direct цей блок не показують.
import { useEffect, useState } from "react";
import { api } from "./api";

export type CommentMode = "public" | "private";

export type CommentTarget = {
  is_comment: boolean;
  platform?: string;
  default_mode?: CommentMode;
  private_days?: number;
  target?: { comment_id: string; message_id: number; text: string; at: string | null; nested_to_top?: boolean } | null;
  problem?: string;
  can_private?: boolean;
  private_code?: string;
  private_reason?: string;
};

/** Питає бекенд лише для Instagram/Facebook-чатів; для інших повертає null. refreshKey — перечитати (новий коментар). */
export function useCommentTarget(convId: number | undefined, channelKind: string | undefined, refreshKey: unknown): CommentTarget | null {
  const [info, setInfo] = useState<CommentTarget | null>(null);
  const enabled = !!convId && ["instagram", "facebook"].includes(channelKind || "");
  useEffect(() => {
    let alive = true;
    if (!enabled) { setInfo(null); return; }
    api.get<CommentTarget>(`/api/conversations/${convId}/comment_target/`)
      .then((r) => { if (alive) setInfo(r && (r as any).is_comment ? r : null); })
      .catch(() => { if (alive) setInfo(null); });
    return () => { alive = false; };
  }, [convId, enabled, refreshKey]);
  return info;
}

const pill = (on: boolean, disabled = false) => ({
  fontSize: 11.5, fontWeight: on ? 700 : 500, padding: "3px 10px", borderRadius: 14,
  border: "1px solid " + (on ? "#ea580c" : "#fed7aa"), background: on ? "#ea580c" : "#fff",
  color: on ? "#fff" : (disabled ? "#c2a38f" : "#9a3412"), cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.7 : 1,
} as const);

export function CommentReplyBar({ info, mode, onMode }: {
  info: CommentTarget | null;
  mode: CommentMode;
  onMode: (m: CommentMode) => void;
}) {
  if (!info || !info.is_comment) return null;
  const where = info.platform === "instagram" ? "Instagram" : "Facebook";
  if (!info.target) {
    return (
      <div style={{ background: "#fee2e2", color: "#b91c1c", fontSize: 11.5, fontWeight: 600, padding: "6px 10px", borderRadius: 6, marginBottom: 6, lineHeight: 1.35 }}>
        ⚠️ {info.problem || "Немає коментаря клієнта, на який можна відповісти."}
      </div>
    );
  }
  const t = info.target.text || "";
  const quote = t ? `«${t.slice(0, 90)}${t.length > 90 ? "…" : ""}»` : "";
  const isPrivate = mode === "private";
  return (
    <div style={{ background: isPrivate ? "#eff6ff" : "#fff7ed", border: "1px solid " + (isPrivate ? "#bfdbfe" : "#fed7aa"), color: isPrivate ? "#1e3a8a" : "#7c2d12", fontSize: 11.5, padding: "6px 10px", borderRadius: 8, marginBottom: 6, lineHeight: 1.4 }}>
      {isPrivate
        ? <div>🔒 <b>Приватно в Messenger</b> — клієнт отримає відповідь у Messenger як приватну відповідь на свій останній коментар {quote}. Meta дозволяє лише <b>одну</b> таку відповідь на коментар (до {info.private_days || 7} днів); далі клієнт має відповісти в Messenger — тоді це буде звичайний чат.</div>
        : <div>💬 <b>Публічно в гілці {where}</b> — відповідь побачать усі під публікацією. Піде у відповідь на останній коментар клієнта {quote}{info.target.nested_to_top ? " (Instagram дозволяє відповідати лише в гілку верхнього коментаря — відповідь стане в ту саму гілку)" : ""}.</div>}
      {info.platform === "facebook" && (
        <div style={{ display: "flex", gap: 6, marginTop: 5, flexWrap: "wrap", alignItems: "center" }}>
          <button type="button" style={pill(!isPrivate)} onClick={() => onMode("public")}>💬 Публічно в гілці</button>
          <button type="button" style={pill(isPrivate, !info.can_private)} disabled={!info.can_private}
            title={info.can_private ? "Одна приватна відповідь на цей коментар — у Messenger клієнта" : (info.private_reason || "")}
            onClick={() => { if (info.can_private) onMode("private"); }}>🔒 Приватно в Messenger</button>
          {!info.can_private && info.private_reason && <span style={{ fontSize: 10.5, color: "#9a3412" }}>{info.private_reason}</span>}
        </div>
      )}
    </div>
  );
}

/** Помилка відправки + кнопка «Відповісти в гілці коментаря», якщо бекенд сказав, що публічно можна. */
export function CommentSendError({ err, canPublic, onPublic, busy, style }: {
  err: string; canPublic: boolean; onPublic: () => void; busy?: boolean; style?: any;
}) {
  if (!err) return null;
  return (
    <div style={{ color: "#dc2626", fontSize: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", ...(style || {}) }}>
      <span>{err}</span>
      {canPublic && <button type="button" className="btn" disabled={busy} onClick={onPublic}
        style={{ height: 26, fontSize: 11.5, background: "#fff7ed", color: "#9a3412", border: "1px solid #fed7aa" }}>💬 Відповісти в гілці коментаря</button>}
    </div>
  );
}
