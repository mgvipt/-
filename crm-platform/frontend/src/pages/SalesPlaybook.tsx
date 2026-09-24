import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { api } from "../api";
import { customerScriptText, scriptFields } from "./salesScriptText";

type Locale = "uk" | "ru";
type Localized = Record<Locale, string>;
type Step = { id: string; title: Localized; customer_text: Localized; manager_only: Localized; capture?: string[]; branches?: { when: Localized; next: string }[] };
type Shared = Partial<Step> & { next?: string; terminal?: boolean; route_script_id?: string; resume_previous_step?: boolean };
type Script = { id: string; group: string; title: Localized; steps: Step[] };
type Library = { version: string; scripts: Script[]; shared_nodes: Record<string, Shared> };
const labels: Record<string, [string, string]> = {
  manager_name: ["Ваше ім’я", "Ваше имя"], contact_name: ["Ім’я співрозмовника", "Имя собеседника"],
  customer_priority: ["Що важливо клієнту", "Что важно клиенту"], agreed_action: ["Погоджена дія", "Согласованное действие"],
  agreed_channel: ["Погоджений канал", "Согласованный канал"], agreed_time: ["Погоджений час", "Согласованное время"],
  previous_need: ["Попередньо обговорена задача", "Ранее обсуждавшаяся задача"], missing_information: ["Що потрібно уточнити", "Что нужно уточнить"],
  project_summary: ["Коротко про задачу", "Кратко о задаче"],
};
export function SalesPlaybook({ scope, onBack, onClose, onInsert, disabled = false }: {
  scope: "wholesale" | "calls"; onBack: () => void; onClose: () => void; onInsert?: (text: string) => void; disabled?: boolean;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const [lang, setLang] = useState<Locale>("uk");
  const t = (uk: string, ru: string) => lang === "ru" ? ru : uk;
  const [data, setData] = useState<Library | null>(null);
  const [failed, setFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [scriptId, setScriptId] = useState(scope === "wholesale" ? "wholesale-first" : "inbound-materials");
  const [stepId, setStepId] = useState("start");
  const [values, setValues] = useState<Record<string, string>>({});
  const [returnTo, setReturnTo] = useState<{scriptId: string; stepId: string} | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, []);
  useEffect(() => {
    let alive = true; setFailed(false); setData(null);
    api.get<Library>("/api/inbox/sales-scripts/").then(value => { if (alive) setData(value); }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [reload]);
  const script = data?.scripts.find(x => x.id === scriptId);
  const step: Step | undefined = script?.steps.find(x => x.id === stepId) || (data?.shared_nodes[stepId]?.customer_text ? {
    ...data.shared_nodes[stepId], id: stepId, title: {uk: "Завершення розмови", ru: "Завершение разговора"},
  } as Step : undefined);
  const template = step?.customer_text[lang] || "";
  const prepared = useMemo(() => customerScriptText(template, values), [template, values]);
  const ready = !!step && prepared.ready && !disabled && !failed;
  function chooseScript(id: string) { setScriptId(id); setStepId("start"); setReturnTo(null); setNotice(""); }
  function next(id: string) {
    setNotice("");
    const common = data?.shared_nodes[id];
    if (common?.route_script_id) { setReturnTo({scriptId, stepId}); setScriptId(common.route_script_id); setStepId("start"); }
    else if (common?.resume_previous_step) {
      if (returnTo) { setScriptId(returnTo.scriptId); setStepId(returnTo.stepId); setReturnTo(null); }
      else setStepId("end");
    } else setStepId(id);
  }
  function insert() {
    // Re-check at the action boundary; manager_only is never passed to a callback.
    const result = customerScriptText(template, values);
    if (!ready || !result.ready) return;
    onInsert?.(result.text);
  }
  async function copy() {
    const result = customerScriptText(template, values);
    if (!ready || !result.ready) return;
    try { await navigator.clipboard.writeText(result.text); setNotice(t("Репліку скопійовано", "Реплика скопирована")); }
    catch { setNotice(t("Не вдалося скопіювати. Спробуйте ще раз.", "Не удалось скопировать. Попробуйте снова.")); }
  }
  // ── дизайн вікна (24.09): зліва кроки розмови, ситуації та сценарії; праворуч — сама репліка ──
  const group = scope === "calls" ? "retail" : "wholesale";
  const scripts = (data?.scripts || []).filter(x => x.group === group);
  const isSituation = (x: Script) => /заперечен|возражен|дожим/i.test(x.title.uk + x.title.ru + x.id);
  const flows = scripts.filter(x => !isSituation(x));
  const situations = scripts.filter(isSituation);
  const stepIndex = script?.steps.findIndex(x => x.id === stepId) ?? -1;
  const fields = scriptFields(template);
  const SIDE_BTN = (on: boolean): CSSProperties => ({
    display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left", cursor: "pointer",
    border: 0, borderRadius: 9, padding: "7px 9px", marginBottom: 2, fontSize: 12.5, lineHeight: 1.3,
    background: on ? "#e6eef8" : "transparent", color: on ? "#1d4d80" : "#334155", fontWeight: on ? 700 : 500,
  });
  const GroupLabel = ({ children }: { children: ReactNode }) =>
    <div style={{ fontSize: 10.5, letterSpacing: ".06em", textTransform: "uppercase", color: "#8a93a5", fontWeight: 800, margin: "12px 4px 5px" }}>{children}</div>;

  return <div ref={dialog} onCopy={event => event.preventDefault()} onKeyDown={event => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); return; }
    if (event.key !== "Tab") return;
    const targets = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href]") || []);
    const first = targets[0], last = targets[targets.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }} role="dialog" aria-modal="true" aria-label={scope === "wholesale" ? "Опт" : t("Дзвінки", "Звонки")}
    onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}
    style={{ position: "fixed", inset: 0, zIndex: 1000, padding: 12, background: "rgba(15,23,42,.38)", display: "grid", placeItems: "center" }}>
    <div style={{ width: "min(1180px,100%)", height: "min(780px,94vh)", background: "#fff", borderRadius: 14, boxShadow: "0 24px 64px rgba(15,23,42,.3)", display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* шапка: де я · мова · нова розмова */}
      <div style={{ borderBottom: "1px solid #e2e8f0" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 14px 8px" }}>
          <b style={{ fontSize: 15, whiteSpace: "nowrap" }}>{scope === "wholesale" ? "🤝 Опт" : t("📞 Дзвінки", "📞 Звонки")}</b>
          <span className="muted" style={{ fontSize: 11.5 }}>{t("скрипт розмови — крок за кроком", "скрипт разговора — шаг за шагом")}</span>
          <span style={{ flex: 1 }} />
          <select aria-label={t("Мова сценарію", "Язык сценария")} value={lang} onChange={e => { setLang(e.target.value as Locale); setNotice(""); }}
            style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 12.5, padding: "0 6px" }}>
            <option value="uk">Українська</option><option value="ru">Русский</option></select>
          <button className="btn" type="button" style={{ fontSize: 12 }}
            onClick={() => { setValues({}); setNotice(""); chooseScript(scope === "wholesale" ? "wholesale-first" : "inbound-materials"); }}>
            {t("Нова розмова", "Новый разговор")}</button>
          <button className="btn" type="button" onClick={onClose} aria-label={t("Закрити", "Закрыть")} style={{ padding: "2px 9px" }}>×</button>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "0 14px 9px" }}>
          <button className="btn btn-light" type="button" onClick={onBack} style={{ fontSize: 12 }}>← {t("Швидкі відповіді", "Быстрые ответы")}</button>
        </div>
      </div>

      {!data && !failed && <p role="status" style={{ padding: 16 }}>{t("Завантаження сценаріїв…", "Загрузка сценариев…")}</p>}
      {failed && <p role="alert" style={{ padding: 16 }}>{t("Не вдалося завантажити сценарії.", "Не удалось загрузить сценарии.")}{" "}
        <button className="btn" type="button" onClick={() => setReload(n => n + 1)}>{t("Повторити", "Повторить")}</button></p>}

      {data && <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "236px minmax(0, 1fr)" }}>
        {/* ЗЛІВА: кроки розмови, ситуації, сценарії */}
        <nav aria-label={t("Кроки розмови", "Шаги разговора")} style={{ overflowY: "auto", borderRight: "1px solid #eef2f7", background: "#f8fafc", padding: "2px 7px 12px" }}>
          {script && <>
            <GroupLabel>{t("Хід розмови", "Ход разговора")}</GroupLabel>
            {script.steps.map((x, i) => <button key={x.id} type="button" onClick={() => { setStepId(x.id); setNotice(""); }} style={SIDE_BTN(x.id === stepId)}>
              <span style={{ flex: "0 0 18px", height: 18, borderRadius: 6, fontSize: 10.5, fontWeight: 800, display: "inline-flex", alignItems: "center", justifyContent: "center",
                background: x.id === stepId ? "#2E6FB0" : (stepIndex > i ? "#cfe0f1" : "#e6eaf0"), color: x.id === stepId ? "#fff" : "#4a5568" }}>{i + 1}</span>
              <span style={{ minWidth: 0 }}>{x.title[lang]}</span>
            </button>)}
          </>}
          {situations.length > 0 && <>
            <GroupLabel>{t("Ситуації: дожими й заперечення", "Ситуации: дожимы и возражения")}</GroupLabel>
            {situations.map(x => <button key={x.id} type="button" onClick={() => chooseScript(x.id)} style={SIDE_BTN(scriptId === x.id)}>
              <span style={{ flex: "0 0 18px", textAlign: "center" }}>💬</span>
              <span style={{ minWidth: 0 }}>{x.title[lang]} <span className="muted" style={{ fontWeight: 500 }}>· {x.steps.length}</span></span>
            </button>)}
          </>}
          {flows.length > 1 && <>
            <GroupLabel>{t("Сценарії", "Сценарии")}</GroupLabel>
            {flows.map(x => <button key={x.id} type="button" onClick={() => chooseScript(x.id)} style={SIDE_BTN(scriptId === x.id)}>
              <span style={{ flex: "0 0 18px", textAlign: "center" }}>▸</span><span style={{ minWidth: 0 }}>{x.title[lang]}</span>
            </button>)}
          </>}
        </nav>

        {/* ПРАВОРУЧ: сам крок */}
        <div style={{ overflowY: "auto", padding: "14px 16px 18px", minWidth: 0 }}>
          {script && <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
            <b style={{ fontSize: 14 }}>{script.title[lang]}</b>
            {stepIndex >= 0 && <span className="muted" style={{ fontSize: 11.5 }}>{t("крок", "шаг")} {stepIndex + 1} {t("з", "из")} {script.steps.length}</span>}
          </div>}
          {step && <>
            <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 10, letterSpacing: "-.01em" }}>{step.title[lang]}</div>

            <aside style={{ margin: "0 0 12px", padding: "10px 12px", borderRadius: 10, background: "#fffbeb", border: "1px solid #fde68a" }}>
              <div style={{ fontSize: 10.5, letterSpacing: ".05em", textTransform: "uppercase", fontWeight: 800, color: "#92400e", marginBottom: 3 }}>
                {t("Підказка менеджеру · клієнт цього не бачить", "Подсказка менеджеру · клиент этого не видит")}</div>
              <div style={{ fontSize: 13.5, lineHeight: 1.45, color: "#5b4a1f" }}>{step.manager_only[lang]}</div>
            </aside>

            {fields.length > 0 && <div style={{ margin: "0 0 12px", padding: "10px 12px", border: "1px solid #e2e8f0", borderRadius: 10 }}>
              <div style={{ fontSize: 10.5, letterSpacing: ".05em", textTransform: "uppercase", fontWeight: 800, color: "#64748b", marginBottom: 7 }}>
                {t("Заповніть узгоджені дані", "Заполните согласованные данные")}</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(230px,100%),1fr))", gap: 9 }}>
                {fields.map(key => <label key={key} style={{ fontSize: 12, color: "#475569" }}>{labels[key]?.[lang === "uk" ? 0 : 1] || key}
                  <input maxLength={500} value={values[key] || ""} onChange={e => { setValues(v => ({ ...v, [key]: e.target.value })); setNotice(""); }}
                    style={{ display: "block", boxSizing: "border-box", width: "100%", padding: "7px 9px", marginTop: 4, border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 13 }} /></label>)}
              </div>
            </div>}

            <section style={{ margin: "0 0 10px", padding: "12px 14px", background: "#f1f6fb", border: "1px solid #d5e3f2", borderRadius: 10 }}>
              <div style={{ fontSize: 10.5, letterSpacing: ".05em", textTransform: "uppercase", fontWeight: 800, color: "#2E6FB0", marginBottom: 5 }}>
                {t("Що кажемо клієнту", "Что говорим клиенту")}</div>
              <p style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 14.5, lineHeight: 1.5 }} onCopy={event => { if (!ready) event.preventDefault(); }}>{prepared.text}</p>
            </section>
            {!prepared.ready && <p role="status" style={{ color: "#92400e", fontSize: 12.5, margin: "0 0 9px" }}>
              {t("Заповніть усі поля без дужок-шаблонів — тоді репліку можна буде вставити.", "Заполните все поля без шаблонных скобок — тогда реплику можно будет вставить.")}</p>}

            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              {onInsert && <button className="btn btn-primary" type="button" disabled={!ready} onClick={insert}>{t("Вставити в поле ↵", "Вставить в поле ↵")}</button>}
              <button className="btn" type="button" disabled={!ready} onClick={copy}>{t("Копіювати", "Копировать")}</button>
              {notice && <span role="status" className="muted" style={{ fontSize: 12 }}>{notice}</span>}
            </div>
            <p className="muted" style={{ fontSize: 11.5, marginTop: 7 }}>
              {t("Перевірте текст перед надсиланням. Дані розмови зберігаються лише до закриття вікна.", "Проверьте текст перед отправкой. Данные разговора хранятся только до закрытия окна.")}</p>

            {(step.branches?.length || data.shared_nodes[stepId]?.next) ? <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed #dbe3ee" }}>
              <div style={{ fontSize: 10.5, letterSpacing: ".05em", textTransform: "uppercase", fontWeight: 800, color: "#64748b", marginBottom: 7 }}>
                {t("Що відповів клієнт", "Что ответил клиент")}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {step.branches?.map((branch, i) => <button className="btn" type="button" key={i} onClick={() => next(branch.next)} style={{ fontSize: 12.5 }}>{branch.when[lang]} →</button>)}
                {data.shared_nodes[stepId]?.next && <button className="btn" type="button" onClick={() => next(data.shared_nodes[stepId].next!)} style={{ fontSize: 12.5 }}>{t("Завершити", "Завершить")}</button>}
              </div>
            </div> : null}
          </>}
        </div>
      </div>}
    </div>
  </div>;
}
