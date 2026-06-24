/* Кнопка «Подзвонити» — ставить заявку, наша АТС дзвонить на внутрішній
 * менеджера, потім клієнту. Працює у картках ліда/сделки/клієнта. */
import { useState } from "react";
import { api } from "./api";

export default function CallButton({ contact, phone, small }: { contact?: number; phone?: string; small?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ t: string; ok: boolean } | null>(null);

  async function call() {
    setBusy(true); setMsg(null);
    try {
      const r = await api.post<any>("/api/calls/dial/", contact ? { contact } : { number: phone || "" });
      setMsg({ t: `📞 АТС набирає ваш внутрішній ${r.extension} — підніміть слухавку, далі зʼєднає з клієнтом`, ok: true });
    } catch (e: any) {
      const d = String(e?.message || "");
      const m = d.match(/"detail"\s*:\s*"([^"]+)"/);
      setMsg({ t: m ? m[1] : "Не вдалося подзвонити", ok: false });
    } finally {
      setBusy(false);
      setTimeout(() => setMsg(null), 7000);
    }
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <button className="btn btn-green" onClick={call} disabled={busy}
        title="Подзвонити клієнту через нашу АТС"
        style={small ? { padding: "4px 10px", fontSize: 13 } : undefined}>
        {busy ? "…" : "📞 Подзвонити"}
      </button>
      {msg && <span style={{ fontSize: 11.5, color: msg.ok ? "#16a34a" : "#dc2626", maxWidth: 240 }}>{msg.t}</span>}
    </span>
  );
}
