import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

export default function SettingsAgent() {
  const { t } = useLang();
  const [cfg, setCfg] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);

  useEffect(() => {
    api.get<any>("/api/agent/config/").then(setCfg).catch(() => {});
    api.get<any>("/api/tasks/?created_by_agent=1").then((d) => setRuns((d.results || d).slice(0, 8))).catch(() => {});
  }, []);

  async function save(patch: any) { setCfg((c: any) => ({ ...c, ...patch })); try { await api.post("/api/agent/config/", patch); } catch { /* */ } }
  if (!cfg) return <div className="muted" style={{ padding: 16 }}>…</div>;

  const Toggle = ({ k, label, desc }: { k: string; label: string; desc: string }) => (
    <div className="panel" style={{ margin: "0 0 10px", display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ flex: 1 }}><b style={{ fontSize: 14 }}>{label}</b><div className="muted" style={{ fontSize: 12 }}>{desc}</div></div>
      <span className={"toggle" + (cfg[k] ? " on" : "")} onClick={() => save({ [k]: !cfg[k] })} />
    </div>
  );

  const ModelSel = ({ k, label, desc }: { k: string; label: string; desc: string }) => (
    <div className="panel" style={{ margin: "0 0 10px" }}>
      <b style={{ fontSize: 14 }}>{label}</b>
      <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{desc}</div>
      <select value={cfg[k]} onChange={(e) => save({ [k]: e.target.value })}
        style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }}>
        <option value="claude-haiku-4-5">Haiku 4.5 — {t("дешёвая ×0.27", "дешева ×0.27")}</option>
        <option value="claude-sonnet-4-6">Sonnet 4.6 — {t("баланс ×1", "баланс ×1")}</option>
        <option value="claude-opus-4-8">Opus 4.8 — {t("умная, дорогая ×5", "розумна, дорога ×5")}</option>
      </select>
    </div>
  );

  return (
    <div>
      <div className="note">{t(
        "Встроенный AI-агент (РОП) сам читает диалоги, двигает лиды по воронке и создаёт задачи сотрудникам по Глобальным правилам. Работает по расписанию (каждые 10 мин) + вручную из карточки.",
        "Вбудований AI-агент (РОП) сам читає діалоги, рухає ліди по воронці і створює задачі співробітникам за Глобальними правилами. Працює за розкладом (кожні 10 хв) + вручну з картки.")}</div>
      <div style={{ marginTop: 12 }}>
        <Toggle k="enabled" label={t("Агент включён", "Агент увімкнений")} desc={t("Главный выключатель агента", "Головний вимикач агента")} />
        <Toggle k="autonomous" label={t("Автономный режим", "Автономний режим")} desc={t("Сам выполняет действия (двигает стадии, создаёт задачи). Выкл = только предлагает на подтверждение", "Сам виконує дії (рухає стадії, створює задачі). Вимк = тільки пропонує на підтвердження")} />
        <Toggle k="auto_on_reply" label={t("Авто-проходка лидов", "Авто-проходка лідів")} desc={t("Каждые 10 мин: проходит активные лиды (двигает) + застрявшие (создаёт дожим менеджеру)", "Кожні 10 хв: проходить активні ліди (рухає) + застряглі (створює дожим менеджеру)")} />
      </div>
      <div className="panel" style={{ margin: "0 0 10px" }}>
        <div className="label" style={{ marginBottom: 6 }}>{t("Модель", "Модель")}</div>
        <select value={cfg.model} onChange={(e) => save({ model: e.target.value })}
          style={{ width: "100%", height: 36, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }}>
          <option value="claude-sonnet-4-6">Sonnet 4.6 — {t("дешевле, для фона", "дешевше, для фону")}</option>
          <option value="claude-opus-4-8">Opus 4.8 — {t("умнее, для сложных", "розумніша, для складних")}</option>
        </select>
      </div>
      <div className="panel" style={{ margin: 0 }}>
        <div className="label" style={{ marginBottom: 6 }}>{t("Доп. инструкция агенту", "Дод. інструкція агенту")}</div>
        <textarea defaultValue={cfg.system_extra} onBlur={(e) => save({ system_extra: e.target.value })}
          placeholder={t("Напр. тон общения, особые правила компании…", "Напр. тон спілкування, особливі правила компанії…")}
          style={{ width: "100%", minHeight: 80, borderRadius: 8, border: "1px solid #e2e8f0", padding: 9, boxSizing: "border-box", fontSize: 13, resize: "vertical" }} />
      </div>
      <div className="label" style={{ marginTop: 20, marginBottom: 8, fontSize: 15 }}><Icon n="💰" size={16} /> {t("Модели ИИ и расходы", "Моделі ШІ та витрати")}</div>
      <div className="note" style={{ marginBottom: 10 }}>{t(
        "Где можно срезать расход без потери качества. Рациональные настройки уже выставлены: дорогую модель — только где реально нужно, частую автоматику — на дешёвую.",
        "Де можна зрізати витрати без втрати якості. Раціональні налаштування вже виставлені: дорогу модель — лише де реально треба, часту автоматику — на дешеву.")}</div>
      <ModelSel k="priority_model" label={t("ИИ-РОП: приоритет чатов", "ШІ-РОП: пріоритет чатів")} desc={t(
        "Бейдж приоритета (срочно / возмущение / просчёт). АВТО каждые 5 мин на каждое новое сообщение — самый частый расход. Классификации хватает Haiku → экономия ×4. Рекоменд.: Haiku.",
        "Бейдж пріоритету (терміново / обурення / прорахунок). АВТО кожні 5 хв на кожне нове повідомлення — найчастіша витрата. Класифікації вистачає Haiku → економія ×4. Реком.: Haiku.")} />
      <Toggle k="priority_enabled" label={t("Авто-приоритет чатов включён", "Авто-пріоритет чатів увімкнено")} desc={t("Выкл = бейджи приоритета вообще не считаются (0 расход на это). Чаты не пострадают.", "Вимк = бейджі пріоритету взагалі не рахуються (0 витрат на це). Чати не постраждають.")} />
      <Toggle k="analyst_auto" label={t("Аналитик: авто при открытии карточки", "Аналітик: авто при відкритті картки")} desc={t("ВЫКЛ (рекоменд.) = коуч-разбор только по кнопке «Оцінити якість» — экономит Opus. ВКЛ = запускается сам при первом открытии карточки.", "ВИМК (реком.) = коуч-розбір лише по кнопці «Оцінити якість» — економить Opus. УВІМК = запускається сам при першому відкритті картки.")} />
      <ModelSel k="analyst_model" label={t("Аналитик продаж (коуч-разбор)", "Аналітик продажів (коуч-розбір)")} desc={t(
        "Глубокий разбор диалога — по кнопке «Оновити оцінку» (не авто, кэшируется). Sonnet даёт коуч-уровень в 5× дешевле Opus. Рекоменд.: Sonnet, Opus — только если нужно максимум.",
        "Глибокий розбір діалогу — по кнопці «Оновити оцінку» (не авто, кешується). Sonnet дає коуч-рівень у 5× дешевше Opus. Реком.: Sonnet, Opus — лише якщо треба максимум.")} />
      <ModelSel k="suggest_model" label={t("Подсказки ответа клиенту", "Підказки відповіді клієнту")} desc={t("Кнопка «подсказать ответ» в чате — только по требованию. Sonnet оптимально.", "Кнопка «підказати відповідь» у чаті — лише на вимогу. Sonnet оптимально.")} />
      <Toggle k="cache_enabled" label={t("Кэширование промптов (prompt caching)", "Кешування промптів (prompt caching)")} desc={t("Кэширует повторяющийся системный промпт — экономия до 90% при пакетной обработке. Держать включённым.", "Кешує повторюваний системний промпт — економія до 90% при пакетній обробці. Тримати увімкненим.")} />

      {runs.length > 0 && (
        <div className="panel" style={{ marginTop: 10 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("Последние задачи от агента", "Останні задачі від агента")}</div>
          {runs.map((r) => (
            <div key={r.id} style={{ fontSize: 12.5, padding: "5px 0", borderBottom: "1px solid #f1f5f9" }}>
              <Icon n="🤖" size={16} /> <b>{r.kind_display}</b>: {r.title} <span className="muted">· {r.status_display}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
