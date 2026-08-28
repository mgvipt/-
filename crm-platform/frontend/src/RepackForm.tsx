import { useState, useEffect } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

/* Розлив/Фасування — переливаем товар из крупной тары в мелкую.
   Два явных поля: ЧТО списываем (взял со склада) и ВО ЧТО оприходуем (что получилось).
   defaultTarget — заранее подставить товар (напр. текущая карточка) в поле «во что». */

function ProdPick({ t, val, onPick, ph, color, exclId }:
  { t: any; val: any; onPick: (p: any | null) => void; ph: string; color: string; exclId?: number }) {
  const [q, setQ] = useState(val ? val.name : "");
  const [opts, setOpts] = useState<any[]>([]);
  useEffect(() => { setQ(val ? val.name : ""); }, [val]);
  useEffect(() => {
    const s = q.trim();
    if (!s || (val && s === val.name)) { setOpts([]); return; }
    const h = setTimeout(() => api.get<any>(`/api/products/?search=${encodeURIComponent(s)}&page_size=50&is_active=true`)
      .then((r) => setOpts(((r.results || r) as any[]).filter((x: any) => x.id !== exclId))).catch(() => setOpts([])), 250);
    return () => clearTimeout(h);
    // eslint-disable-next-line
  }, [q]);
  return (
    <div style={{ position: "relative" }}>
      {val
        ? <div style={{ display: "flex", alignItems: "center", gap: 8, background: color, borderRadius: 8, padding: "9px 12px", fontSize: 13.5 }}><span style={{ flex: 1 }}><b>{val.name}</b> <span className="muted">({t("на складе", "на складі")} {val.stock})</span></span><span onClick={() => onPick(null)} style={{ cursor: "pointer", color: "#94a3b8", fontSize: 16 }}>✕</span></div>
        : <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={ph} style={{ width: "100%", height: 42, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 12px", fontSize: 13.5, boxSizing: "border-box" }} />}
      {!val && opts.length > 0 && (
        <div style={{ position: "absolute", top: 44, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, boxShadow: "0 10px 26px rgba(15,23,42,.15)", zIndex: 30, maxHeight: 240, overflow: "auto" }}>
          {opts.map((o: any) => <div key={o.id} onClick={() => { onPick(o); setOpts([]); }} style={{ padding: "9px 12px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f1f5f9" }}>{o.name} <span className="muted">{o.sku} · {t("на складе", "на складі")} {o.stock}</span></div>)}
        </div>
      )}
    </div>
  );
}

export default function RepackForm({ onDone, defaultTarget, compact }:
  { onDone?: (r: any) => void; defaultTarget?: any; compact?: boolean }) {
  const { t } = useLang();
  const [src, setSrc] = useState<any>(null);
  const [tgt, setTgt] = useState<any>(defaultTarget || null);
  const [tara, setTara] = useState<any>(null);
  const [sq, setSq] = useState("1"); const [tq, setTq] = useState(""); const [taraQty, setTaraQty] = useState("");
  const [busy, setBusy] = useState(false); const [msg, setMsg] = useState("");
  useEffect(() => { setTgt(defaultTarget || null); /* eslint-disable-next-line */ }, [defaultTarget && defaultTarget.id]);
  const doIt = async () => {
    if (!src || !tgt) { setMsg(t("Заполни оба поля: что списываешь и во что", "Заповни обидва поля: що списуєш і в що")); return; }
    if (src.id === tgt.id) { setMsg(t("Это один и тот же товар", "Це той самий товар")); return; }
    const _sq = Number(String(sq).replace(",", ".")) || 0; const _tq = Number(String(tq).replace(",", ".")) || 0;
    if (_sq <= 0 || _tq <= 0) { setMsg(t("Впиши количества (больше нуля)", "Впиши кількості (більше нуля)")); return; }
    const _taraQ = Number(String(taraQty).replace(",", ".")) || 0;
    const extras = (tara && _taraQ > 0) ? [{ product: tara.id, qty: _taraQ }] : [];
    setBusy(true); setMsg("");
    try {
      const r: any = await api.post("/api/stock-documents/repack/", { source: src.id, source_qty: _sq, target: tgt.id, target_qty: _tq, extras });
      setMsg("✓ " + t(`Готово! Списано ${_sq} «${src.name}»${extras.length ? " + тара " + _taraQ : ""}, оприходовано ${_tq} «${tgt.name}». Остаток: ${r.target_stock}`,
                        `Готово! Списано ${_sq} «${src.name}»${extras.length ? " + тара " + _taraQ : ""}, оприбутковано ${_tq} «${tgt.name}». Залишок: ${r.target_stock}`));
      setSrc(null); setTara(null); setSq("1"); setTq(""); setTaraQty("");
      if (!defaultTarget) setTgt(null);
      onDone && onDone(r);
    } catch (e: any) { setMsg(e?.response?.data?.detail || t("Не удалось провести розлив", "Не вдалося провести розлив")); }
    setBusy(false);
  };
  const lbl: any = { fontSize: 12.5, fontWeight: 700, color: "#334155", margin: "0 0 5px" };
  const qtyInp = (val: string, set: (v: string) => void, ph: string, green?: boolean) =>
    <input type="number" value={val} onChange={(e) => set(e.target.value)} placeholder={ph} style={{ width: 120, height: 38, border: "1px solid " + (green ? "#86efac" : "#cbd5e1"), borderRadius: 8, padding: "0 10px", boxSizing: "border-box" }} />;
  return (
    <div style={{ background: "#fbfdff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 14, maxWidth: 620 }}>
      {!compact && <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 4 }}>🧪 {t("Розлив / Фасовка", "Розлив / Фасування")}</div>}
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 14, lineHeight: 1.5 }}>
        {t("Это когда переливаешь товар из большой тары в маленькую (например из литровой бутылки в флаконы по 100 мл). Заполни: что взял со склада (спишется) и что получилось (оприходуется). Деньги это не двигает.",
           "Це коли переливаєш товар із великої тари в маленьку (наприклад із літрової пляшки у флакони по 100 мл). Заповни: що взяв зі складу (спишеться) і що вийшло (оприбуткується). Гроші це не рухає.")}
      </div>

      <div style={{ ...lbl }}>1️⃣ {t("Что взял со склада — спишется", "Що взяв зі складу — спишеться")}</div>
      <ProdPick t={t} val={src} onPick={(p) => { setSrc(p); }} ph={t("🔍 Найти товар (напр. Primer Deep литровый)…", "🔍 Знайти товар (напр. Primer Deep літровий)…")} color="#fee2e2" exclId={tgt && tgt.id} />
      <div style={{ margin: "8px 0 16px", display: "flex", alignItems: "center", gap: 8 }}>
        <span className="muted" style={{ fontSize: 12.5 }}>{t("Сколько взял:", "Скільки взяв:")}</span>{qtyInp(sq, setSq, "1")}
      </div>

      <div style={{ ...lbl }}>2️⃣ {t("Тара — тоже спишется (если тратишь). Не нужно — пропусти", "Тара — теж спишеться (якщо витрачаєш). Не треба — пропусти")}</div>
      <ProdPick t={t} val={tara} onPick={(p) => { setTara(p); if (p && !taraQty) setTaraQty(tq || "1"); }} ph={t("📦 Флаконы / вёдра (необязательно)…", "📦 Флакони / відра (необовʼязково)…")} color="#fef9c3" exclId={tgt && tgt.id} />
      {tara && <div style={{ margin: "8px 0 16px", display: "flex", alignItems: "center", gap: 8 }}>
        <span className="muted" style={{ fontSize: 12.5 }}>{t("Сколько тары:", "Скільки тари:")}</span>{qtyInp(taraQty, setTaraQty, "1")}
      </div>}
      {!tara && <div style={{ height: 16 }} />}

      <div style={{ ...lbl }}>3️⃣ {t("Что получилось — оприходуется", "Що вийшло — оприбуткується")}</div>
      <ProdPick t={t} val={tgt} onPick={(p) => { setTgt(p); }} ph={t("🔍 Найти товар (напр. Primer Deep 100 мл)…", "🔍 Знайти товар (напр. Primer Deep 100 мл)…")} color="#dcfce7" exclId={src && src.id} />
      <div style={{ margin: "8px 0 16px", display: "flex", alignItems: "center", gap: 8 }}>
        <span className="muted" style={{ fontSize: 12.5 }}>{t("Сколько получилось:", "Скільки вийшло:")}</span>{qtyInp(tq, setTq, t("напр. 10", "напр. 10"), true)}
      </div>

      <button className="btn btn-primary" disabled={busy || !src || !tgt} onClick={doIt} style={{ height: 44, width: "100%", fontSize: 15, fontWeight: 700 }}>{busy ? "…" : "✓ " + t("Провести розлив", "Провести розлив")}</button>
      {msg && <div style={{ fontSize: 13, marginTop: 10, padding: "8px 12px", borderRadius: 8, lineHeight: 1.5, background: msg.startsWith("✓") ? "#f0fdf4" : "#fef2f2", color: msg.startsWith("✓") ? "#166534" : "#b91c1c" }}>{msg}</div>}
    </div>
  );
}

// ── Просмотр документа розлива/списания: что списано и что оприходовано ──
export function RepackDocModal({ id, onClose }: { id: number; onClose: () => void }) {
  const { t } = useLang();
  const [doc, setDoc] = useState<any>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { setDoc(null); setErr(false); api.get<any>(`/api/stock-documents/${id}/`).then(setDoc).catch(() => setErr(true)); }, [id]);
  const items: any[] = (doc && doc.items) || [];
  const outs = items.filter((m) => Number(m.quantity) < 0);
  const ins = items.filter((m) => Number(m.quantity) > 0);
  const isRepack = doc && doc.kind === "repack";
  const money = (v: any) => Number(v || 0).toLocaleString("uk-UA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const qtyFmt = (v: any) => { const n = Number(v); return (Number.isInteger(n) ? n : n.toFixed(3).replace(/\.?0+$/, "")); };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, padding: 18, maxWidth: 560, width: "100%", maxHeight: "85vh", overflow: "auto", boxShadow: "0 20px 50px rgba(15,23,42,.3)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>{isRepack ? "🧪 " + t("Розлив / Фасовка", "Розлив / Фасування") : "🗑 " + t("Списание", "Списання")}</div>
            {doc && <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>{t("от", "від")} {(doc.doc_date || doc.created_at || "").slice(0, 10)}{doc.number ? " · №" + doc.number : ""}{doc.posted ? " · " + t("проведён", "проведено") : " · " + t("черновик", "чернетка")}</div>}
          </div>
          <button onClick={onClose} style={{ border: "none", background: "#f1f5f9", borderRadius: 8, width: 30, height: 30, cursor: "pointer", fontSize: 16 }}>✕</button>
        </div>
        {err ? <div style={{ color: "#b91c1c", fontSize: 13 }}>{t("Не удалось загрузить документ", "Не вдалося завантажити документ")}</div>
          : !doc ? <div className="muted" style={{ fontSize: 13 }}>{t("Загрузка…", "Завантаження…")}</div> : (<>
          {doc.comment && <div className="muted" style={{ fontSize: 12.5, marginBottom: 12, lineHeight: 1.5 }}>{doc.comment}</div>}
          <div style={{ fontSize: 12.5, fontWeight: 700, color: "#b91c1c", margin: "0 0 6px" }}>▼ {t("Списано со склада", "Списано зі складу")}</div>
          {outs.length === 0 ? <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>—</div> : (
            <div style={{ marginBottom: 14 }}>{outs.map((m) => (
              <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 8, background: "#fef2f2", borderRadius: 8, padding: "8px 12px", marginBottom: 4, fontSize: 13 }}>
                <span style={{ flex: 1 }}>{m.product_name}</span>
                <b style={{ color: "#b91c1c" }}>−{qtyFmt(Math.abs(Number(m.quantity)))}</b>
                <span className="muted" style={{ fontSize: 12, minWidth: 92, textAlign: "right" }}>{money(m.price)} ₴/{t("ед", "од")}</span>
              </div>
            ))}</div>
          )}
          <div style={{ fontSize: 12.5, fontWeight: 700, color: "#166534", margin: "0 0 6px" }}>▲ {t("Оприходовано на склад", "Оприбутковано на склад")}</div>
          {ins.length === 0 ? <div className="muted" style={{ fontSize: 12.5 }}>—</div> : (
            <div>{ins.map((m) => (
              <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 8, background: "#f0fdf4", borderRadius: 8, padding: "8px 12px", marginBottom: 4, fontSize: 13 }}>
                <span style={{ flex: 1 }}>{m.product_name}</span>
                <b style={{ color: "#166534" }}>+{qtyFmt(Number(m.quantity))}</b>
                <span className="muted" style={{ fontSize: 12, minWidth: 92, textAlign: "right" }}>{money(m.price)} ₴/{t("ед", "од")}</span>
              </div>
            ))}</div>
          )}
        </>)}
      </div>
    </div>
  );
}
