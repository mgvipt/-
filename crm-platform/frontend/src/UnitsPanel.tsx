/* Довідник одиниць виміру (01.10.2026, Олег): «щоб усі одиниці з цього одного блоку
 * тягнулись у всьому CRM і скрізь був випадний список».
 * Тут правимо список — у приході, картці товару й масовій зміні він оновиться сам. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";
import { invalidateUnits, Unit } from "./units";

export default function UnitsPanel({ canEdit }: { canEdit: boolean }) {
  const { t } = useLang();
  const [rows, setRows] = useState<Unit[]>([]);
  const [nm, setNm] = useState(""); const [full, setFull] = useState("");
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);

  function load() {
    api.get<Unit[]>("/api/units/?all=1").then((d) => setRows(d || [])).catch(() => setRows([]));
  }
  useEffect(load, []);

  async function add() {
    const n = nm.trim();
    if (!n) { setErr(t("Впишите сокращение: кг, л, шт", "Впишіть скорочення: кг, л, шт")); return; }
    if (rows.some((r) => r.name.toLowerCase() === n.toLowerCase())) { setErr(t("Такая единица уже есть", "Така одиниця вже є")); return; }
    setBusy(true); setErr("");
    try {
      await api.post("/api/units/", { name: n, full_name: full.trim(), sort_order: 500, is_active: true });
      setNm(""); setFull(""); invalidateUnits(); load();
    } catch (e: any) { setErr(e?.response?.data?.detail || t("Не удалось добавить", "Не вдалося додати")); }
    setBusy(false);
  }
  async function save(u: Unit, patch: Partial<Unit>) {
    try { await api.patch(`/api/units/${u.id}/`, patch); invalidateUnits(); load(); }
    catch { setErr(t("Не удалось сохранить", "Не вдалося зберегти")); }
  }
  async function del(u: Unit) {
    if ((u.products_count || 0) > 0) {
      setErr(t(`«${u.name}» стоит у ${u.products_count} товаров — удалять нельзя. Снимите галочку «активна», чтобы убрать из выбора.`,
               `«${u.name}» стоїть у ${u.products_count} товарів — видаляти не можна. Зніміть галочку «активна», щоб прибрати з вибору.`));
      return;
    }
    if (!confirm(t(`Удалить единицу «${u.name}»?`, `Видалити одиницю «${u.name}»?`))) return;
    try { await api.del(`/api/units/${u.id}/`); invalidateUnits(); load(); }
    catch { setErr(t("Не удалось удалить", "Не вдалося видалити")); }
  }

  const th: any = { textAlign: "left", fontSize: 11, textTransform: "uppercase", color: "#94a3b8", fontWeight: 700, padding: "6px 8px", borderBottom: "1px solid #e2e8f0" };
  const td: any = { padding: "6px 8px", borderBottom: "1px solid #f1f5f9", fontSize: 13 };
  const inp: any = { height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 9px", fontSize: 13 };

  return (
    <div className="card" style={{ padding: 16, maxWidth: 740 }}>
      <h3 style={{ margin: "0 0 4px", fontSize: 16 }}>{t("Единицы измерения","Одиниці виміру")}</h3>
      <p className="muted" style={{ fontSize: 12.5, margin: "0 0 12px", lineHeight: 1.45 }}>
        {t("Один список на всю CRM. Что здесь добавите — появится в выпадающем списке в карточке товара, в приходе и в массовой смене единицы.",
           "Один список на всю CRM. Що тут додасте — зʼявиться у випадному списку в картці товару, у приході й у масовій зміні одиниці.")}
      </p>
      {canEdit && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
          <input value={nm} onChange={(e) => setNm(e.target.value)} placeholder={t("кг","кг")} style={{ ...inp, width: 110 }} maxLength={16} />
          <input value={full} onChange={(e) => setFull(e.target.value)} placeholder={t("Килограмм (необязательно)","Кілограм (необовʼязково)")} style={{ ...inp, width: 260 }} maxLength={60} />
          <button className="btn btn-primary" onClick={add} disabled={busy}>{t("Добавить","Додати")}</button>
        </div>
      )}
      {err && <div style={{ color: "#b91c1c", fontSize: 12.5, marginBottom: 8 }}>{err}</div>}
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            <th style={th}>{t("Сокращение","Скорочено")}</th>
            <th style={th}>{t("Полное название","Повна назва")}</th>
            <th style={{ ...th, textAlign: "center" }}>{t("Товаров","Товарів")}</th>
            <th style={{ ...th, textAlign: "center" }}>{t("В списке","У списку")}</th>
            <th style={th}></th>
          </tr></thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id}>
                <td style={{ ...td, fontWeight: 700 }}>{u.name}</td>
                <td style={td}>
                  {canEdit ? (
                    <input defaultValue={u.full_name} onBlur={(e) => e.target.value !== u.full_name && save(u, { full_name: e.target.value })}
                           style={{ ...inp, height: 30, width: "100%", border: "1px solid #e2e8f0" }} />
                  ) : (u.full_name || "—")}
                </td>
                <td style={{ ...td, textAlign: "center", color: (u.products_count || 0) > 0 ? "#0f172a" : "#94a3b8" }}>{u.products_count ?? 0}</td>
                <td style={{ ...td, textAlign: "center" }}>
                  <input type="checkbox" checked={u.is_active} disabled={!canEdit}
                         onChange={(e) => save(u, { is_active: e.target.checked })}
                         title={t("Снять — единица исчезнет из выбора, но у старых товаров останется","Зняти — одиниця зникне з вибору, але у старих товарів лишиться")} />
                </td>
                <td style={{ ...td, textAlign: "right" }}>
                  {canEdit && <span onClick={() => del(u)} style={{ cursor: "pointer", color: (u.products_count || 0) > 0 ? "#cbd5e1" : "#ef4444" }}
                                    title={t("Удалить","Видалити")}>✕</span>}
                </td>
              </tr>
            ))}
            {!rows.length && <tr><td style={{ ...td, color: "#94a3b8" }} colSpan={5}>{t("Список пуст","Список порожній")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
