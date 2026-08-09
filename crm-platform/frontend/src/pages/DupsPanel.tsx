/* ============================================================================
 *  ДУБЛІ ТОВАРІВ — frontend/src/pages/DupsPanel.tsx
 * ----------------------------------------------------------------------------
 *  [1] Авто-знахідка: точні дублі (однакова назва) з /api/products/duplicates/
 *      → обрати головну карточку → «Склеїти» (переносить сделки+рухи, дублі ховає).
 *  [2] Ручна склейка: знайти товари пошуком → додати в кошик → обрати головну →
 *      склеїти. Для дублів з різним артикулом (фаззі-пошук не використовуємо —
 *      він плутає дублі з розмірними варіантами).
 * ========================================================================== */
import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../Icon";
import { useLang } from "../i18n";

interface DupRow {
  id: number; sku: string; name: string; unit: string;
  balance: number; sold: number; received: number; deal_items: number; last: string | null;
}
interface DupGroup { suggest_keeper: number; products: DupRow[]; }

export default function DupsPanel() {
  const { t } = useLang();
  const [groups, setGroups] = useState<DupGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [keeperOf, setKeeperOf] = useState<Record<number, number>>({}); // groupIndex → keeperId
  const [busy, setBusy] = useState<number | null>(null);

  // ручна склейка
  const [q, setQ] = useState("");
  const [results, setResults] = useState<DupRow[]>([]);
  const [basket, setBasket] = useState<DupRow[]>([]);
  const [mKeeper, setMKeeper] = useState<number | null>(null);
  const [mBusy, setMBusy] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<{ groups: DupGroup[] }>("/api/products/duplicates/");
      setGroups(r.groups || []);
      const km: Record<number, number> = {};
      (r.groups || []).forEach((g, i) => (km[i] = g.suggest_keeper));
      setKeeperOf(km);
    } catch { setGroups([]); }
    setLoading(false);
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }
    const tmr = setTimeout(async () => {
      try {
        const r = await api.get<{ results: any[] }>(`/api/products/?is_active=true&search=${encodeURIComponent(q.trim())}&page_size=12`);
        setResults((r.results || []).map((p: any) => ({ id: p.id, sku: p.sku || "", name: p.name, unit: p.unit, balance: p.stock ?? 0, sold: 0, received: 0, deal_items: 0, last: null })));
      } catch { setResults([]); }
    }, 250);
    return () => clearTimeout(tmr);
  }, [q]);

  async function mergeGroup(gi: number) {
    const g = groups[gi];
    const keeper = keeperOf[gi] || g.suggest_keeper;
    const dups = g.products.map((p) => p.id).filter((id) => id !== keeper);
    if (!dups.length) return;
    const keepName = g.products.find((p) => p.id === keeper)?.name || "";
    if (!window.confirm(t(`Склеить ${dups.length} карточку(ок) в «${keepName}»? Отменить сложно.`, `Склеїти ${dups.length} карточку(ок) у «${keepName}»? Скасувати складно.`))) return;
    setBusy(gi);
    try {
      const r: any = await api.post("/api/products/merge/", { keeper, dups });
      alert(t(`Готово. Перенесено позиций: ${r.moved_deal_items}, движений: ${r.moved_movements}. Остаток главной: ${r.keeper_balance}`,
              `Готово. Перенесено позицій: ${r.moved_deal_items}, рухів: ${r.moved_movements}. Залишок головної: ${r.keeper_balance}`));
      await load();
    } catch (e: any) { alert(e?.data?.detail || t("Не удалось склеить", "Не вдалося склеїти")); }
    setBusy(null);
  }

  function addToBasket(p: DupRow) {
    if (basket.some((x) => x.id === p.id)) return;
    const nb = [...basket, p];
    setBasket(nb);
    if (mKeeper == null) setMKeeper(p.id);
    setQ(""); setResults([]);
  }
  function rmFromBasket(id: number) {
    const nb = basket.filter((x) => x.id !== id);
    setBasket(nb);
    if (mKeeper === id) setMKeeper(nb[0]?.id ?? null);
  }
  async function mergeManual() {
    if (basket.length < 2 || mKeeper == null) return;
    const dups = basket.map((p) => p.id).filter((id) => id !== mKeeper);
    const keepName = basket.find((p) => p.id === mKeeper)?.name || "";
    if (!window.confirm(t(`Склеить ${dups.length} карточку(ок) в «${keepName}»? Убедись, что это ОДИН товар!`, `Склеїти ${dups.length} карточку(ок) у «${keepName}»? Переконайся, що це ОДИН товар!`))) return;
    setMBusy(true);
    try {
      const r: any = await api.post("/api/products/merge/", { keeper: mKeeper, dups });
      alert(t(`Готово. Перенесено позиций: ${r.moved_deal_items}, движений: ${r.moved_movements}. Остаток: ${r.keeper_balance}`,
              `Готово. Перенесено позицій: ${r.moved_deal_items}, рухів: ${r.moved_movements}. Залишок: ${r.keeper_balance}`));
      setBasket([]); setMKeeper(null); await load();
    } catch (e: any) { alert(e?.data?.detail || t("Не удалось склеить", "Не вдалося склеїти")); }
    setMBusy(false);
  }

  const stat = (p: DupRow) => (
    <span style={{ fontSize: 11, color: "#64748b" }}>
      {t("ост.", "зал.")} <b style={{ color: p.balance < 0 ? "#dc2626" : "#0f172a" }}>{p.balance}</b>
      {" · "}{t("продано", "продано")} {p.sold}{" · "}{t("сделок", "сделок")} {p.deal_items}
      {p.last ? " · " + p.last.slice(0, 10) : ""}
    </span>
  );

  return (
    <div style={{ padding: "4px 2px", maxWidth: 900 }}>
      <div style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 10, padding: "10px 14px", marginBottom: 14, fontSize: 12.5, color: "#9a3412" }}>
        <b>⚠️ {t("Сливай только карточки ОДНОГО товара.", "Склеюй тільки карточки ОДНОГО товару.")}</b>{" "}
        {t("Продажи, приходы и остатки соберутся на выбранную главную карточку, дубли скроются. Отменить сложно.",
           "Продажі, приходи і залишки зберуться на обрану головну карточку, дублі сховаються. Скасувати складно.")}
      </div>

      {/* [1] Авто-знахідка точних дублів */}
      <h3 style={{ fontSize: 15, fontWeight: 700, margin: "6px 0 10px" }}>
        {t("Найдено дублей (одинаковые названия):", "Знайдено дублів (однакові назви):")} {loading ? "…" : groups.length}
      </h3>
      {!loading && groups.length === 0 && (
        <div style={{ color: "#16a34a", fontSize: 13, marginBottom: 18 }}>✓ {t("Точных дублей по названию нет.", "Точних дублів за назвою немає.")}</div>
      )}
      {groups.map((g, gi) => (
        <div key={gi} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, marginBottom: 12, background: "#fff" }}>
          <div style={{ fontSize: 12, color: "#475569", marginBottom: 8 }}>{t("Выбери ГЛАВНУЮ карточку (в неё соберётся всё):", "Обери ГОЛОВНУ карточку (у неї збереться все):")}</div>
          {g.products.map((p) => (
            <label key={p.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", cursor: "pointer" }}>
              <input type="radio" name={`keep-${gi}`} checked={(keeperOf[gi] || g.suggest_keeper) === p.id}
                     onChange={() => setKeeperOf((s) => ({ ...s, [gi]: p.id }))} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {p.name} {p.sku ? <span style={{ color: "#94a3b8", fontWeight: 400 }}>· {p.sku}</span> : <span style={{ color: "#f59e0b" }}>· {t("без артикула", "без артикула")}</span>}
                </div>
                {stat(p)}
              </div>
            </label>
          ))}
          <button className="btn btn-primary" disabled={busy === gi} style={{ marginTop: 8 }} onClick={() => mergeGroup(gi)}>
            <Icon n="check" size={15} /> {busy === gi ? t("Склеиваю…", "Склеюю…") : t("Склеить в главную", "Склеїти в головну")}
          </button>
        </div>
      ))}

      {/* [2] Ручна склейка */}
      <h3 style={{ fontSize: 15, fontWeight: 700, margin: "22px 0 8px" }}>{t("Ручная склейка (по поиску)", "Ручна склейка (за пошуком)")}</h3>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
        {t("Для дублей с разным артикулом (как праймер). Найди и добавь карточки, которые точно один товар.", "Для дублів з різним артикулом (як праймер). Знайди і додай карточки, що точно один товар.")}
      </div>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Поиск товара по названию/артикулу…", "Пошук товару за назвою/артикулом…")}
             style={{ width: "100%", height: 34, border: "1px solid #e2e8f0", borderRadius: 8, padding: "0 10px", fontSize: 13, marginBottom: 6 }} />
      {results.length > 0 && (
        <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, marginBottom: 10, maxHeight: 220, overflowY: "auto" }}>
          {results.map((p) => (
            <div key={p.id} onClick={() => addToBasket(p)} style={{ padding: "7px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", gap: 8 }}>
              <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{p.name}</span>
              <span style={{ color: "#94a3b8", fontSize: 11, whiteSpace: "nowrap" }}>{p.sku || "—"} · +</span>
            </div>
          ))}
        </div>
      )}
      {basket.length > 0 && (
        <div style={{ border: "1px solid #cbd5e1", borderRadius: 10, padding: 12, background: "#f8fafc" }}>
          <div style={{ fontSize: 12, color: "#475569", marginBottom: 8 }}>{t("Корзина склейки — выбери главную:", "Кошик склейки — обери головну:")}</div>
          {basket.map((p) => (
            <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0" }}>
              <input type="radio" name="mkeeper" checked={mKeeper === p.id} onChange={() => setMKeeper(p.id)} />
              <span style={{ flex: 1, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {p.name} <span style={{ color: "#94a3b8" }}>· {p.sku || t("без артикула", "без артикула")}</span>
              </span>
              <button className="btn btn-light" style={{ height: 26, fontSize: 11 }} onClick={() => rmFromBasket(p.id)}>✕</button>
            </div>
          ))}
          <button className="btn btn-primary" disabled={mBusy || basket.length < 2 || mKeeper == null} style={{ marginTop: 8 }} onClick={mergeManual}>
            <Icon n="check" size={15} /> {mBusy ? t("Склеиваю…", "Склеюю…") : t("Склеить выбранные", "Склеїти вибрані")}
          </button>
        </div>
      )}
    </div>
  );
}
