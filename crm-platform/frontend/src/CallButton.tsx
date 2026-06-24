/* Кнопка «Подзвонити» — ставить заявку, наша АТС дзвонить на внутрішній
 * менеджера, потім клієнту. Працює у картках ліда/сделки/клієнта. */
import { useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

export default function CallButton({ contact, phone, small }: { contact?: number; phone?: string; small?: boolean }) {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ t: string; ok: boolean } | null>(null);

  async function call() {
    setBusy(true); setMsg(null);
    try {
      const w = window as any;
      if (w.wallcovDial && w.wallcovPhoneReady) {
        const r = await api.post<any>("/api/calls/dial/", contact ? { contact, resolve_only: true } : { number: phone || "", resolve_only: true });
        w.wallcovDial(r.number);
        setMsg({ t: t(`📞 Звоню ${r.number} прямо в браузере…`, `📞 Дзвоню ${r.number} прямо в браузері…`), ok: true });
      } else {
        const r = await api.post<any>("/api/calls/dial/", contact ? { contact } : { number: phone || "" });
        setMsg({ t: t(`📞 АТС набирает ваш внутренний ${r.extension} — поднимите трубку, далее соединит с клиентом`, `📞 АТС набирає ваш внутрішній ${r.extension} — підніміть слухавку, далі зʼєднає з клієнтом`), ok: true });
      }
    } catch (e: any) {
      const d = String(e?.message || "");
      const m = d.match(/"detail"\s*:\s*"([^"]+)"/);
      setMsg({ t: m ? m[1] : t("Не удалось позвонить","Не вдалося подзвонити"), ok: false });
    } finally {
      setBusy(false);
      setTimeout(() => setMsg(null), 7000);
    }
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <button className="btn btn-green" onClick={call} disabled={busy}
        title={t("Позвонить клиенту через нашу АТС","Подзвонити клієнту через нашу АТС")}
        style={small ? { padding: "4px 10px", fontSize: 13 } : undefined}>
        {busy ? "…" : t("📞 Позвонить","📞 Подзвонити")}
      </button>
      {msg && <span style={{ fontSize: 11.5, color: msg.ok ? "#16a34a" : "#dc2626", maxWidth: 240 }}>{msg.t}</span>}
    </span>
  );
}
