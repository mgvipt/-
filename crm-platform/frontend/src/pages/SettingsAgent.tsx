import { useEffect, useState } from "react";
import { api } from "../api";
import { useLang } from "../i18n";

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
      {runs.length > 0 && (
        <div className="panel" style={{ marginTop: 10 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("Последние задачи от агента", "Останні задачі від агента")}</div>
          {runs.map((r) => (
            <div key={r.id} style={{ fontSize: 12.5, padding: "5px 0", borderBottom: "1px solid #f1f5f9" }}>
              🤖 <b>{r.kind_display}</b>: {r.title} <span className="muted">· {r.status_display}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
