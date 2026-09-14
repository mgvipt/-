/* «Пропущені» (14.09.2026): черга «треба передзвонити» + звіт по менеджерах і лініях + налаштування.
 * Тут ЛИШЕ показ і дії з чергою. Дзвінок — тільки через існуючу кнопку CallButton
 * (веб-телефон WebPhone.tsx → window.wallcovDial, або заявка АТС). Живого звуку/SIP тут немає —
 * правило «вся логіка дзвінка лише у WebPhone.tsx» не порушується. */
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
import CallButton from "../CallButton";

type T = (ru: string, uk: string) => string;
interface Item {
  id: number; number: string; line: string; contact?: number | null; contact_name: string; calls_count: number;
  first_missed_at: string; wait_min: number; wait_work_min: number; due_at?: string | null; overdue: boolean;
  assignee?: number | null; assignee_name: string; assign_reason_label: string; task?: number | null; status: string;
  closed_at?: string | null; close_reason_label: string; reaction_work_min?: number | null; escalated: boolean; backfilled?: boolean;
}
interface Colleague { id: number; name: string; }
interface ListResp {
  results: Item[]; counts: { mine: number; unassigned: number; all: number | null }; scope: string;
  can_all: boolean; can_report: boolean; can_settings: boolean; colleagues: Colleague[];
  sla_minutes: number; escalate_minutes: number;
}

const GREEN = "#16a34a", AMBER = "#d97706", RED = "#dc2626", GREY = "#94a3b8";

function fmtMin(m: number, t: T) {
  if (m < 60) return `${m} ${t("мин", "хв")}`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} ${t("ч", "год")} ${m % 60} ${t("мин", "хв")}`;
  return `${Math.floor(h / 24)} ${t("д", "д")} ${h % 24} ${t("ч", "год")}`;
}
function when(s?: string | null) {
  return s ? new Date(s).toLocaleString("uk", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
}
function waitColor(it: Item, sla: number, esc: number) {
  if (it.status !== "open") return GREY;
  return it.wait_work_min < sla ? GREEN : it.wait_work_min < esc ? AMBER : RED;
}
function errText(e: any, t: T) {
  const m = String(e?.message || "").match(/"detail"\s*:\s*"([^"]+)"/);
  return m ? m[1] : t("Не удалось", "Не вдалося");
}
function localIso(x: Date) {
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
}

export default function MissedCallsSection() {
  const { t } = useLang();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [d, setD] = useState<ListResp | null>(null);
  const [scope, setScope] = useState<string>("");
  const [showClosed, setShowClosed] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [transferFor, setTransferFor] = useState<number | null>(null);

  function load() {
    const q = new URLSearchParams();
    q.set("status", showClosed ? "all" : "open");
    if (scope) q.set("scope", scope);
    api.get<ListResp>("/api/telephony/missed/?" + q.toString())
      .then((r) => setD((p) => (JSON.stringify(p) === JSON.stringify(r) ? p : r)))
      .catch(() => {});
  }
  useEffect(() => {
    load();
    const tm = setInterval(load, 30000);
    return () => clearInterval(tm);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, showClosed]);
  useEffect(() => {
    if (sp.get("tab") === "missed") setTimeout(() => document.getElementById("missed")?.scrollIntoView({ behavior: "smooth", block: "start" }), 250);
  }, [sp]);

  if (!d) return null;   // немає доступу до телефонії — блок не показуємо

  async function act(it: Item, body: any) {
    setBusyId(it.id);
    try { await api.post(`/api/telephony/missed/${it.id}/action/`, body); setTransferFor(null); load(); }
    catch (e: any) { alert(errText(e, t)); }
    finally { setBusyId(null); }
  }
  function closeWith(it: Item, reason: "other_channel" | "not_relevant") {
    const q = reason === "other_channel"
      ? t("Клиенту ответили в другом канале (чат/Viber/Instagram)? Комментарий (необязательно):", "Клієнту відповіли в іншому каналі (чат/Viber/Instagram)? Коментар (необовʼязково):")
      : t("Клиент не актуален (спам, ошибся номером, уже не нужно)? Комментарий (необязательно):", "Клієнт не актуальний (спам, помилився номером, вже не треба)? Коментар (необовʼязково):");
    const note = prompt(q, "");
    if (note === null) return;
    act(it, { action: "close", reason, note });
  }

  const sla = d.sla_minutes || 15, esc = d.escalate_minutes || 60;
  const open = d.results.filter((x) => x.status === "open");
  const effScope = scope || d.scope;
  const btn = (on: boolean): any => ({ fontSize: 12, padding: "4px 10px", borderRadius: 7, cursor: "pointer", border: "1px solid #e2e8f0", background: on ? "#0f172a" : "#fff", color: on ? "#fff" : "#334155", fontWeight: on ? 700 : 500 });

  return (
    <>
      <div id="missed" className="panel" style={{ margin: "0 0 16px", padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "12px 14px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", background: open.length ? "#fef2f2" : "#f0fdf4" }}>
          <Icon n="📵" size={18} />
          <b style={{ fontSize: 15 }}>{t("Пропущенные — нужно перезвонить", "Пропущені — треба передзвонити")}</b>
          <span className="chip" style={{ background: open.length ? RED : GREEN }}>{open.length}</span>
          <div style={{ display: "flex", gap: 6, marginLeft: "auto", alignItems: "center", flexWrap: "wrap" }}>
            {d.can_all && <>
              <button style={btn(effScope === "mine")} onClick={() => setScope("mine")}>{t("Мои", "Мої")} ({d.counts.mine + d.counts.unassigned})</button>
              <button style={btn(effScope === "all")} onClick={() => setScope("all")}>{t("Все", "Усі")} ({d.counts.all ?? 0})</button>
            </>}
            <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}>
              <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
              {t("показать обработанные (3 дня)", "показати оброблені (3 дні)")}
            </label>
          </div>
        </div>

        {d.results.length === 0 ? (
          <div style={{ padding: 16, fontSize: 13, color: GREEN, fontWeight: 600 }}>✓ {t("Всем перезвонили — пропущенных нет.", "Усім передзвонили — пропущених немає.")}</div>
        ) : d.results.map((it) => {
          const col = waitColor(it, sla, esc);
          return (
            <div key={it.id} style={{ display: "flex", gap: 12, alignItems: "center", padding: "9px 12px", borderBottom: "1px solid #f1f5f9", borderLeft: `4px solid ${col}`, flexWrap: "wrap", opacity: it.status === "open" ? 1 : 0.7 }}>
              <div style={{ width: 92, textAlign: "center", flexShrink: 0 }}>
                <div style={{ fontWeight: 800, color: col, fontSize: 15 }}>{fmtMin(it.status === "open" ? it.wait_work_min : (it.reaction_work_min ?? it.wait_work_min), t)}</div>
                <div className="muted" style={{ fontSize: 10.5 }}>{it.status === "open" ? t("ждёт (раб. время)", "чекає (роб. час)") : it.close_reason_label}</div>
              </div>
              <div style={{ flex: "1 1 200px", minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {it.contact
                    ? <a onClick={() => nav(`/clients/${it.contact}`)} style={{ color: "var(--brand,#C67D5F)", cursor: "pointer" }}>{it.contact_name || it.number}</a>
                    : <span>{it.number} <span className="muted" style={{ fontWeight: 500, fontSize: 11.5 }}>· {t("новый номер", "новий номер")}</span></span>}
                  {it.calls_count > 1 && <span style={{ marginLeft: 6, fontSize: 11, background: "#fee2e2", color: RED, borderRadius: 6, padding: "1px 6px" }}>×{it.calls_count}</span>}
                  {it.escalated && it.status === "open" && <span title={t("Руководитель уже уведомлён", "Керівника вже повідомлено")} style={{ marginLeft: 6, fontSize: 11, color: "#d97706" }}><Icon n="⚠" size={12} /></span>}
                </div>
                <div className="muted" style={{ fontSize: 11.5 }}>{it.contact ? it.number + " · " : ""}{when(it.first_missed_at)}</div>
                {it.line && <div style={{ fontSize: 10.5, color: "#7c5cff", marginTop: 1 }}><Icon n="📡" size={12} /> {it.line}</div>}
              </div>
              <div style={{ fontSize: 12, width: 150, flexShrink: 0 }}>
                <div style={{ fontWeight: 600 }}>{it.assignee_name || <span style={{ color: RED }}>{t("не назначен", "не призначено")}</span>}</div>
                <div className="muted" style={{ fontSize: 10.5 }}>{it.assign_reason_label}{it.status === "open" && it.due_at ? ` · ${t("до", "до")} ${when(it.due_at)}` : ""}</div>
              </div>
              {it.status === "open" && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                  <CallButton phone={it.number} small />
                  <button className="btn btn-light" style={{ fontSize: 12, padding: "4px 9px" }} disabled={busyId === it.id} onClick={() => setTransferFor(transferFor === it.id ? null : it.id)}>↪ {t("Передать коллеге", "Передати колезі")}</button>
                  <button className="btn btn-light" style={{ fontSize: 12, padding: "4px 9px" }} disabled={busyId === it.id} onClick={() => closeWith(it, "other_channel")} title={t("Ответили в чате / Viber / Instagram", "Відповіли в чаті / Viber / Instagram")}>✓ {t("Другим каналом", "Іншим каналом")}</button>
                  <button className="btn btn-light" style={{ fontSize: 12, padding: "4px 9px", color: "#64748b" }} disabled={busyId === it.id} onClick={() => closeWith(it, "not_relevant")}>✕ {t("Не актуален", "Не актуальний")}</button>
                </div>
              )}
              {transferFor === it.id && (
                <div style={{ flexBasis: "100%", display: "flex", gap: 6, flexWrap: "wrap", paddingLeft: 104 }}>
                  <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>{t("Кому передать:", "Кому передати:")}</span>
                  {d.colleagues.filter((c) => c.id !== it.assignee).map((c) => (
                    <button key={c.id} className="btn btn-light" style={{ fontSize: 12, padding: "3px 9px" }} disabled={busyId === it.id}
                      onClick={() => act(it, { action: "transfer", user_id: c.id })}>{c.name}</button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        <div className="muted" style={{ fontSize: 11.5, padding: "8px 14px", lineHeight: 1.5 }}>
          {t(
            `Строка исчезает сама, как только с этим номером был разговор (вы перезвонили или клиент дозвонился). Зелёный — до ${sla} мин, жёлтый — ${sla}–${esc} мин, красный — больше ${esc} мин (считается только рабочее время; ночь и нерабочие дни не считаются). Через ${esc} мин без перезвона руководитель получает уведомление в CRM. Клиенту ничего автоматически не отправляется.`,
            `Рядок зникає сам, щойно з цим номером була розмова (ви передзвонили або клієнт додзвонився). Зелений — до ${sla} хв, жовтий — ${sla}–${esc} хв, червоний — понад ${esc} хв (рахується лише робочий час; ніч і неробочі дні не рахуються). Через ${esc} хв без передзвону керівник отримує сповіщення в CRM. Клієнту нічого автоматично не надсилається.`,
          )}
        </div>
      </div>
      {d.can_report && <MissedReport t={t} />}
      {d.can_settings && <MissedSettings t={t} colleagues={d.colleagues} onSaved={load} />}
    </>
  );
}

function MissedReport({ t }: { t: T }) {
  const [from, setFrom] = useState(localIso(new Date(Date.now() - 29 * 864e5)));
  const [to, setTo] = useState(localIso(new Date()));
  const [r, setR] = useState<any>(null);
  useEffect(() => {
    api.get<any>(`/api/telephony/missed/report/?from=${from}&to=${to}`).then(setR).catch(() => setR(null));
  }, [from, to]);
  const cols: [string, (x: any) => any][] = [
    [t("Пропущено звонков", "Пропущено дзвінків"), (x) => x.calls],
    [t("Клиентов", "Клієнтів"), (x) => x.items],
    [t("Перезвонили ≤15 мин", "Передзвонили ≤15 хв"), (x) => `${x.cb15_pct}% (${x.cb15})`],
    [t("≤1 час", "≤1 год"), (x) => `${x.cb60_pct}% (${x.cb60})`],
    [t("Не перезвонили", "Не передзвонили"), (x) => <b style={{ color: x.never ? RED : undefined }}>{x.never}</b>],
    [t("Дозвонился сам", "Додзвонився сам"), (x) => x.client_called],
    [t("Закрыли вручную", "Закрили вручну"), (x) => x.manual],
    [t("Медиана реакции", "Медіана реакції"), (x) => (x.median_work_min == null ? "—" : fmtMin(x.median_work_min, t))],
  ];
  const table = (rows: any[], first: string, key: string) => (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
        <thead><tr>
          <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid #e2e8f0" }}>{first}</th>
          {cols.map(([h]) => <th key={h} style={{ textAlign: "right", padding: "6px 8px", borderBottom: "1px solid #e2e8f0", whiteSpace: "nowrap" }}>{h}</th>)}
        </tr></thead>
        <tbody>
          {rows.map((x, i) => (
            <tr key={i}>
              <td style={{ padding: "6px 8px", borderBottom: "1px solid #f1f5f9", fontWeight: 600 }}>{x[key]}</td>
              {cols.map(([h, f]) => <td key={h} style={{ textAlign: "right", padding: "6px 8px", borderBottom: "1px solid #f1f5f9" }}>{f(x)}</td>)}
            </tr>
          ))}
          {r && r.total && (
            <tr style={{ background: "#f8fafc", fontWeight: 700 }}>
              <td style={{ padding: "6px 8px" }}>{t("Итого", "Разом")}</td>
              {cols.map(([h, f]) => <td key={h} style={{ textAlign: "right", padding: "6px 8px" }}>{f(r.total)}</td>)}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
  return (
    <div className="panel" style={{ margin: "0 0 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
        <div className="label" style={{ margin: 0 }}><Icon n="📊" size={15} /> {t("Отчёт по пропущенным", "Звіт по пропущених")}</div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center", fontSize: 12.5 }}>
          <input type="date" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} style={{ height: 30, borderRadius: 7, border: "1px solid #cbd5e1" }} />
          —
          <input type="date" value={to} onChange={(e) => e.target.value && setTo(e.target.value)} style={{ height: 30, borderRadius: 7, border: "1px solid #cbd5e1" }} />
        </div>
      </div>
      {!r ? <div className="muted" style={{ fontSize: 12.5 }}>…</div> : r.total.items === 0
        ? <div className="muted" style={{ fontSize: 12.5 }}>{t("За период пропущенных нет (очередь считает с момента включения).", "За період пропущених немає (черга рахує з моменту увімкнення).")}</div>
        : <>
          <div className="muted" style={{ fontSize: 12, margin: "0 0 4px" }}>{t("По ответственным", "По відповідальних")}</div>
          {table(r.by_manager, t("Менеджер", "Менеджер"), "name")}
          <div className="muted" style={{ fontSize: 12, margin: "12px 0 4px" }}>{t("По линиям", "По лініях")}</div>
          {table(r.by_line, t("Линия", "Лінія"), "line")}
        </>}
      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        {t("Реакция = первый исходящий на номер после пропуска; время — в рабочих минутах. «Дозвонился сам» — клиент перезвонил и с ним поговорили раньше, чем мы.", "Реакція = перший вихідний на номер після пропуску; час — у робочих хвилинах. «Додзвонився сам» — клієнт передзвонив і з ним поговорили раніше, ніж ми.")}
      </div>
    </div>
  );
}

function MissedSettings({ t, colleagues, onSaved }: { t: T; colleagues: Colleague[]; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [s, setS] = useState<any>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (open && !s) api.get<any>("/api/telephony/missed/settings/").then((r) => setS({ ...r, ignore_text: (r.ignore_numbers || []).join(", ") })).catch(() => {});
  }, [open, s]);
  async function save() {
    try {
      const r = await api.patch<any>("/api/telephony/missed/settings/", {
        work_start: s.work_start, work_end: s.work_end, sla_minutes: Number(s.sla_minutes), escalate_minutes: Number(s.escalate_minutes),
        auto_task: !!s.auto_task, ignore_staff_numbers: !!s.ignore_staff_numbers, ignore_numbers: s.ignore_text || "",
        escalate_user_ids: s.escalate_user_ids || [],
      });
      setS({ ...r, ignore_text: (r.ignore_numbers || []).join(", ") }); setMsg(t("Сохранено", "Збережено")); onSaved();
    } catch (e: any) { setMsg(errText(e, t)); }
  }
  const inp: any = { height: 30, borderRadius: 7, border: "1px solid #cbd5e1", fontSize: 12.5, padding: "0 6px" };
  return (
    <div className="panel" style={{ margin: "0 0 16px" }}>
      <div style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }} onClick={() => setOpen((o) => !o)}>
        <div className="label" style={{ margin: 0 }}><Icon n="⚙" size={15} /> {t("Настройки пропущенных", "Налаштування пропущених")}</div>
        <span className="muted" style={{ fontSize: 12 }}>{open ? "▲" : "▼"}</span>
      </div>
      {open && s && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10, fontSize: 12.5 }}>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
            <label>{t("Рабочий день:", "Робочий день:")} <input type="time" value={s.work_start} onChange={(e) => setS({ ...s, work_start: e.target.value })} style={inp} /> — <input type="time" value={s.work_end} onChange={(e) => setS({ ...s, work_end: e.target.value })} style={inp} /></label>
            <label>{t("Перезвонить за, мин:", "Передзвонити за, хв:")} <input type="number" min={1} value={s.sla_minutes} onChange={(e) => setS({ ...s, sla_minutes: e.target.value })} style={{ ...inp, width: 64 }} /></label>
            <label>{t("Сообщить руководителю через, мин:", "Повідомити керівника через, хв:")} <input type="number" min={5} value={s.escalate_minutes} onChange={(e) => setS({ ...s, escalate_minutes: e.target.value })} style={{ ...inp, width: 64 }} /></label>
          </div>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={!!s.auto_task} onChange={(e) => setS({ ...s, auto_task: e.target.checked })} /> {t("Ставить задачу «Перезвонить» ответственному", "Ставити задачу «Передзвонити» відповідальному")}</label>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={!!s.ignore_staff_numbers} onChange={(e) => setS({ ...s, ignore_staff_numbers: e.target.checked })} /> {t("Не считать звонки с номеров сотрудников", "Не рахувати дзвінки з номерів співробітників")}</label>
          <label>{t("Номера, которые не попадают в очередь (через запятую):", "Номери, які не потрапляють у чергу (через кому):")}<br />
            <input value={s.ignore_text || ""} onChange={(e) => setS({ ...s, ignore_text: e.target.value })} placeholder="0671234567, 0501234567" style={{ ...inp, width: "100%", maxWidth: 520 }} /></label>
          <div>
            <div>{t("Кому сообщать о просрочке:", "Кому повідомляти про прострочення:")} <span className="muted">{t("(пусто = ", "(порожньо = ")}{(s.escalate_default || []).map((x: any) => x.name).join(", ") || "—"})</span></div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 4 }}>
              {colleagues.map((c) => {
                const on = (s.escalate_user_ids || []).includes(c.id);
                return <label key={c.id} style={{ display: "flex", gap: 4, alignItems: "center" }}><input type="checkbox" checked={on} onChange={() => setS({ ...s, escalate_user_ids: on ? s.escalate_user_ids.filter((x: number) => x !== c.id) : [...(s.escalate_user_ids || []), c.id] })} /> {c.name}</label>;
              })}
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {s.can_edit && <button className="btn btn-primary" onClick={save}>{t("Сохранить", "Зберегти")}</button>}
            {msg && <span className="muted">{msg}</span>}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>{t("SMS/Viber клиенту после пропущенного НЕ отправляется — это отдельное решение Олега (нужен провайдер SMS).", "SMS/Viber клієнту після пропущеного НЕ надсилається — це окреме рішення Олега (потрібен SMS-провайдер).")}</div>
        </div>
      )}
    </div>
  );
}
