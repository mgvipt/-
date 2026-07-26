import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

type Values = Record<string, number | boolean | string[]>;
interface CalcSettingsResponse { values: Values; can_manage: boolean; updated_at: string; }

const NUMBERS: [string, string, string][] = [
  ["reserve_pct", "Запас к площади, %", "Запас материалов, который автоматически предлагается по умолчанию"],
  ["labor_wall_m2", "Работа по стенам, ₴/м²", "Базовая ставка работ по чистой площади стен"],
  ["labor_reveal_linear_m", "Работа по откосам, ₴/м.п.", "Для стоимости работ откосы считаются в погонных метрах"],
  ["material_reveal_m2", "Материал откосов, ₴/м²", "Для материалов используется площадь откосов с учётом глубины"],
  ["transport_per_km", "Выезд, ₴/км", "Стоимость расстояния сверх минимального выезда"],
  ["transport_min", "Минимальный выезд, ₴", "Минимальная сумма транспорта"],
  ["minimum_order", "Минимальная смета, ₴", "Ниже этой суммы калькулятор показывает минимальный заказ"],
  ["overhead_pct", "Накладные расходы, %", "Внутренняя надбавка к себестоимости"],
  ["max_discount_pct", "Максимальная скидка, %", "Ограничение скидки для обычного сотрудника"],
  ["rounding_step", "Шаг округления, ₴", "Например, 10 округляет итог до десятков гривен"],
];

const SIDES: [string, string][] = [
  ["left", "Левый"], ["right", "Правый"], ["top", "Верхний"], ["bottom", "Нижний"],
];

export default function CalculatorSettings() {
  const { t } = useLang();
  const [values, setValues] = useState<Values>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<CalcSettingsResponse>("/api/calc-settings/")
      .then((r) => setValues(r.values || {}))
      .catch((e: any) => setError(e?.response?.data?.detail || "Не удалось загрузить настройки"))
      .finally(() => setLoading(false));
  }, []);

  function number(key: string, raw: string) {
    setValues((current) => ({ ...current, [key]: raw === "" ? 0 : Number(raw) }));
  }

  function toggleSide(side: string) {
    const current = Array.isArray(values.reveal_sides) ? values.reveal_sides as string[] : [];
    setValues({ ...values, reveal_sides: current.includes(side) ? current.filter((v) => v !== side) : [...current, side] });
  }

  async function save() {
    setSaving(true); setSaved(false); setError("");
    try {
      const response = await api.patch<CalcSettingsResponse>("/api/calc-settings/", { values });
      setValues(response.values); setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Не удалось сохранить настройки");
    } finally { setSaving(false); }
  }

  if (loading) return <div className="muted">{t("Загрузка…", "Завантаження…")}</div>;

  return (
    <div style={{ maxWidth: 980 }}>
      <div className="note" style={{ marginBottom: 14 }}>
        <b>{t("Единые условия калькулятора", "Єдині умови калькулятора")}</b><br />
        {t("Эти значения хранятся внутри CRM и применяются к сметам приложения замера. Клиент не видит внутренние ставки и ограничения.",
           "Ці значення зберігаються всередині CRM і застосовуються до кошторисів застосунку заміру. Клієнт не бачить внутрішні ставки та обмеження.")}
      </div>
      {error && <div className="note" style={{ color: "#b91c1c", borderColor: "#fecaca", background: "#fef2f2" }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12 }}>
        {NUMBERS.map(([key, label, hint]) => (
          <label key={key} className="panel" style={{ margin: 0, display: "block" }}>
            <b style={{ fontSize: 13 }}>{t(label, label)}</b>
            <input type="number" min="0" step="0.01" value={Number(values[key] || 0)}
              onChange={(e) => number(key, e.target.value)}
              style={{ width: "100%", height: 38, border: "1px solid #cbd5e1", borderRadius: 8, marginTop: 7, padding: "0 10px", fontSize: 15 }} />
            <span className="muted" style={{ display: "block", fontSize: 11.5, marginTop: 5 }}>{t(hint, hint)}</span>
          </label>
        ))}
      </div>

      <div className="panel" style={{ margin: "14px 0 0" }}>
        <b>{t("Какие стороны входят в площадь откоса", "Які сторони входять у площу укосу")}</b>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 10 }}>
          {SIDES.map(([key, label]) => {
            const checked = Array.isArray(values.reveal_sides) && (values.reveal_sides as string[]).includes(key);
            return <label key={key} style={{ display: "flex", gap: 7, alignItems: "center", cursor: "pointer" }}>
              <input type="checkbox" checked={checked} onChange={() => toggleSide(key)} /> {t(label, label)}
            </label>;
          })}
        </div>
      </div>

      <label className="panel" style={{ margin: "14px 0 0", display: "flex", gap: 10, alignItems: "center" }}>
        <input type="checkbox" checked={Boolean(values.show_internal_rates_to_client)}
          onChange={(e) => setValues({ ...values, show_internal_rates_to_client: e.target.checked })} />
        <span><b>{t("Показывать клиенту внутренние ставки", "Показувати клієнту внутрішні ставки")}</b><br />
          <span className="muted" style={{ fontSize: 11.5 }}>{t("По умолчанию выключено.", "За замовчуванням вимкнено.")}</span></span>
      </label>

      <button className="btn btn-primary" disabled={saving} onClick={save} style={{ marginTop: 16, minWidth: 180 }}>
        {saving ? t("Сохраняю…", "Зберігаю…") : saved ? t("✓ Сохранено", "✓ Збережено") : t("Сохранить условия", "Зберегти умови")}
      </button>
    </div>
  );
}
