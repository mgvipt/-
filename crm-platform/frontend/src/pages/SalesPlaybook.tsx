import { useEffect, useMemo, useRef, useState } from "react";
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
  return <div ref={dialog} onCopy={event => event.preventDefault()} onKeyDown={event => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); return; }
    if (event.key !== "Tab") return;
    const targets = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href]") || []);
    const first = targets[0], last = targets[targets.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }} role="dialog" aria-modal="true" aria-label={scope === "wholesale" ? "Опт" : t("Дзвінки", "Звонки")} onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }} style={{ position: "fixed", inset: 0, zIndex: 1000, padding: 10, background: "rgba(15,23,42,.38)", display: "grid", placeItems: "center" }}>
    <div style={{ width: "min(1080px,100%)", height: "min(820px,95vh)", background: "white", borderRadius: 12, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <header style={{ display: "flex", gap: 10, flexWrap: "wrap", padding: 12, alignItems: "center", borderBottom: "1px solid #e2e8f0" }}>
        <button type="button" onClick={onBack}>← {t("Швидкі відповіді", "Быстрые ответы")}</button><strong>{scope === "wholesale" ? "Опт" : t("Дзвінки", "Звонки")}</strong>
        <select aria-label={t("Мова сценарію", "Язык сценария")} value={lang} onChange={e => { setLang(e.target.value as Locale); setNotice(""); }}><option value="uk">Українська</option><option value="ru">Русский</option></select>
        <button type="button" onClick={() => { setValues({}); setNotice(""); chooseScript(scope === "wholesale" ? "wholesale-first" : "inbound-materials"); }}>{t("Нова розмова", "Новый разговор")}</button>
        <button type="button" onClick={onClose} style={{ marginLeft: "auto" }}>{t("Закрити", "Закрыть")}</button>
      </header>
      <div style={{ overflowY: "auto", padding: 14, minHeight: 0 }}>
        {!data && !failed && <p role="status">{t("Завантаження сценаріїв…", "Загрузка сценариев…")}</p>}
        {failed && <p role="alert">{t("Не вдалося завантажити сценарії.", "Не удалось загрузить сценарии.")} <button type="button" onClick={() => setReload(n => n + 1)}>{t("Повторити", "Повторить")}</button></p>}
        {data && <>
          <nav aria-label={t("Сценарії", "Сценарии")} style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>{data.scripts.filter(x => x.group === (scope === "calls" ? "retail" : "wholesale")).map(x => <button type="button" key={x.id} aria-pressed={scriptId === x.id} onClick={() => chooseScript(x.id)}>{x.title[lang]}</button>)}</nav>
          {script && <><h3>{script.title[lang]}</h3><label>{t("Крок розмови", "Шаг разговора")} <select value={script.steps.some(x => x.id === stepId) ? stepId : "__end"} onChange={e => { setStepId(e.target.value); setNotice(""); }}>
            {script.steps.map((x,i) => <option key={x.id} value={x.id}>{i + 1}. {x.title[lang]}</option>)}{!script.steps.some(x => x.id === stepId) && <option value="__end">{t("Завершення", "Завершение")}</option>}
          </select></label></>}
          {step && <>
            <aside style={{ margin: "12px 0", padding: 12, borderRadius: 8, background: "#fff7ed", border: "1px solid #fed7aa" }}><strong>{t("Підказка менеджеру · не надсилати", "Подсказка менеджеру · не отправлять")}</strong><p style={{ marginBottom: 0 }}>{step.manager_only[lang]}</p></aside>
            {scriptFields(template).length > 0 && <fieldset style={{ border: "1px solid #cbd5e1", borderRadius: 8 }}><legend>{t("Заповніть узгоджені дані", "Заполните согласованные данные")}</legend><div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(220px,100%),1fr))", gap: 10 }}>
              {scriptFields(template).map(key => <label key={key}>{labels[key]?.[lang === "uk" ? 0 : 1] || key}<input maxLength={500} value={values[key] || ""} onChange={e => { setValues(v => ({...v,[key]:e.target.value})); setNotice(""); }} style={{ display: "block", boxSizing: "border-box", width: "100%", padding: 8, marginTop: 4 }} /></label>)}
            </div></fieldset>}
            <section style={{ margin: "12px 0", padding: 12, background: "#f8fafc", border: "1px solid #cbd5e1", borderRadius: 8 }}><strong>{t("Репліка клієнту", "Реплика клиенту")}</strong><p style={{ whiteSpace: "pre-wrap", marginBottom: 0 }} onCopy={event => { if (!ready) event.preventDefault(); }}>{prepared.text}</p></section>
            {!prepared.ready && <p role="status" style={{ color: "#92400e" }}>{t("Заповніть усі поля без дужок-шаблонів. Вставлення й копіювання поки недоступні.", "Заполните все поля без шаблонных скобок. Вставка и копирование пока недоступны.")}</p>}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
              {onInsert && <button type="button" disabled={!ready} onClick={insert}>{t("Вставити репліку в поле чату", "Вставить реплику в поле чата")}</button>}
              <button type="button" disabled={!ready} onClick={copy}>{t("Копіювати репліку", "Копировать реплику")}</button>
            </div><p style={{ fontSize: 12, color: "#64748b" }}>{t("Перевірте текст перед надсиланням. Дані розмови зберігаються лише до закриття цього вікна.", "Проверьте текст перед отправкой. Данные разговора хранятся только до закрытия этого окна.")}</p>
            {notice && <p role="status">{notice}</p>}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>{step.branches?.map((branch,i) => <button type="button" key={i} onClick={() => next(branch.next)}>{branch.when[lang]} →</button>)}</div>
            {data.shared_nodes[stepId]?.next && <button type="button" onClick={() => next(data.shared_nodes[stepId].next!)}>{t("Завершити", "Завершить")}</button>}
          </>}
        </>}
      </div>
    </div>
  </div>;
}
