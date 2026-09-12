/* Фінанси → Операції → Знімки дня.
 * Відповідальний (право «Закривати день», зараз — Ілона) наприкінці зміни перевіряє залишки, у касі вписує
 * фактичну готівку і натискає «Закрити день» — CRM фотографує всі операції дня (замість скріна в Telegram).
 * Якщо ніхто не закрив — автознімок у налаштований час (за замовчуванням 19:00 за Києвом).
 * Праворуч — що змінилось після знімка (було → стало), залишки «система / факт». Клік по операції — її картка. */
import { useEffect, useState } from "react";
import { api } from "../../api";
import { useLang } from "../../i18n";
import TxCardModal from "../../TxCardModal";

const fmt = (n: any) => (n == null ? "—" : Number(n).toLocaleString("uk-UA", { maximumFractionDigits: 2 }));
const dm = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split("-"); return `${d}.${m}.${y}`; };
const hm = (iso: string) => new Date(iso).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
const monthAgo = () => { const d = new Date(); d.setDate(d.getDate() - 31); return d.toISOString().slice(0, 10); };
const todayIso = () => new Date().toISOString().slice(0, 10);
const FIELD: Record<string, string> = { amount: "Сума", currency: "Валюта", rate: "Курс", direction: "Тип", account_id: "Рахунок",
  transfer_account_id: "Рахунок-отримувач", transfer_amount: "Сума переказу", category_id: "Категорія", counterparty: "Контрагент",
  comment: "Коментар", deal_id: "Угода", contact_id: "Клієнт" };
const DIR: Record<string, string> = { in: "+", out: "−", transfer: "↔" };

function val(r: any, k: string) {
  if (k === "account_id") return r.account; if (k === "transfer_account_id") return r.transfer_account;
  if (k === "category_id") return r.category; if (k === "direction") return DIR[r.direction] || r.direction;
  return r[k] == null || r[k] === "" ? "—" : String(r[k]);
}

function useNarrow() {
  const [n, setN] = useState(() => typeof window !== "undefined" && window.innerWidth < 900);
  useEffect(() => { const f = () => setN(window.innerWidth < 900); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);
  return n;
}

function OpRow({ r, onOpen, bg }: { r: any; onOpen: (id: number) => void; bg?: string }) {
  return (
    <div onClick={() => onOpen(r.id)} title="Відкрити операцію"
      style={{ display: "grid", gridTemplateColumns: "44px minmax(0,1fr) auto", gap: 8, padding: "7px 6px", borderBottom: "1px solid #f1f5f9", cursor: "pointer", background: bg || "transparent", alignItems: "center" }}>
      <span style={{ color: "#64748b", fontSize: 12 }}>{r.op_time || "—"}</span>
      <span style={{ minWidth: 0 }}>
        <span style={{ display: "block", fontSize: 12.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.counterparty || r.category || "—"}</span>
        <span style={{ display: "block", fontSize: 11, color: "#94a3b8" }}>{r.account}{r.transfer_account ? ` → ${r.transfer_account}` : ""} · {r.src}</span>
      </span>
      <span style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", color: r.direction === "in" ? "#16a34a" : r.direction === "out" ? "#dc2626" : "#475569" }}>
        {DIR[r.direction]}{fmt(r.amount)}{r.currency && r.currency !== "UAH" ? " " + r.currency : ""}
      </span>
    </div>
  );
}

function CloseDialog({ day, onDone, onCancel }: { day: string; onDone: (id: number) => void; onCancel: () => void }) {
  const { t } = useLang();
  const [accs, setAccs] = useState<any[] | null>(null);
  const [facts, setFacts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { api.get<any>("/api/day-snapshots/balances/").then((r) => setAccs(r.accounts || [])).catch(() => setErr(t("Не удалось загрузить остатки", "Не вдалося завантажити залишки"))); }, []);
  async function go() {
    setBusy(true); setErr("");
    try { const r = await api.post<any>("/api/day-snapshots/close/", { date: day, facts }); onDone(r.id); }
    catch (e: any) { setErr(e?.data?.detail || e?.response?.data?.detail || t("Ошибка", "Помилка")); setBusy(false); }
  }
  return (
    <div style={{ border: "2px solid #2E6FB0", borderRadius: 12, padding: 12, margin: "8px 0", background: "#f8fbff" }}>
      <b>{t("Закрыть день", "Закрити день")} {dm(day)}</b>
      <div className="muted" style={{ fontSize: 12, margin: "4px 0 8px", lineHeight: 1.4 }}>
        {t("Проверьте остатки. В кассе пересчитайте наличные и впишите факт — расхождение попадёт в снимок. Остальные счета — по желанию.",
           "Перевірте залишки. У касі перерахуйте готівку і впишіть факт — розбіжність потрапить у знімок. Інші рахунки — за бажанням.")}
      </div>
      {!accs && !err && <div className="muted" style={{ fontSize: 12 }}>{t("Загрузка…", "Завантаження…")}</div>}
      {accs && accs.map((a) => {
        const f = facts[String(a.id)]; const d = f !== undefined && f !== "" ? Number(String(f).replace(",", ".")) - a.system : null;
        return (
          <div key={a.id} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 90px 100px", gap: 6, alignItems: "center", padding: "4px 0", borderBottom: "1px solid #eef2f7" }}>
            <span style={{ fontSize: 12.5, overflow: "hidden", textOverflow: "ellipsis" }}>{a.kind === "cash" ? "💵 " : ""}{a.name}</span>
            <span style={{ fontSize: 12.5, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{fmt(a.system)}</span>
            <span>
              <input inputMode="decimal" placeholder={t("факт", "факт")} value={f ?? ""} onChange={(e) => setFacts({ ...facts, [String(a.id)]: e.target.value })}
                style={{ width: "100%", height: 28, border: `1px solid ${d != null && Math.abs(d) > 0.009 ? "#f59e0b" : "#cbd5e1"}`, borderRadius: 6, padding: "0 6px", textAlign: "right" }} />
            </span>
          </div>
        );
      })}
      {err && <div style={{ color: "#b91c1c", fontSize: 12, marginTop: 6 }}>{err}</div>}
      <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
        <button className="btn btn-primary" disabled={busy} onClick={go}>{busy ? "…" : t("Закрыть день", "Закрити день")}</button>
        <button className="btn btn-light" onClick={onCancel}>{t("Отмена", "Скасувати")}</button>
      </div>
    </div>
  );
}

export default function DaySnapshots() {
  const { t } = useLang();
  const narrow = useNarrow();
  const [list, setList] = useState<any>(null);
  const [sel, setSel] = useState<any>(null);
  const [closing, setClosing] = useState(false);
  const [help, setHelp] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [txOpen, setTxOpen] = useState<number | null>(null);
  const [timeEdit, setTimeEdit] = useState<string | null>(null);

  const open = (id: number) => api.get<any>(`/api/day-snapshots/${id}/`).then((r) => { setSel(r); setErr(""); }).catch(() => setErr(t("Не удалось открыть снимок", "Не вдалося відкрити знімок")));
  const load = async (pick?: number) => {
    try {
      const r = await api.get<any>(`/api/day-snapshots/?from=${monthAgo()}&to=${todayIso()}`);
      setList(r);
      if (pick) open(pick);
      else if (!narrow && !sel && r.results?.length) {
        const first = r.results.find((s: any) => (s.totals?.all?.n || 0) > 0) || r.results[0];
        open(first.id);
      }
    } catch { setErr(t("Нет доступа или ошибка загрузки", "Немає доступу або помилка завантаження")); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  async function act(url: string) {
    setBusy(true); setErr("");
    try { const r = await api.post<any>(url, {}); await load(r?.id); }
    catch (e: any) { setErr(e?.data?.detail || e?.response?.data?.detail || t("Ошибка", "Помилка")); }
    setBusy(false);
  }
  async function saveTime() {
    try { const r = await api.post<any>("/api/day-snapshots/settings/", { auto_time: timeEdit }); setList({ ...list, auto_time: r.auto_time }); setTimeEdit(null); }
    catch (e: any) { setErr(e?.data?.detail || e?.response?.data?.detail || t("Ошибка", "Помилка")); }
  }
  if (!list) return <div className="spin">{err || t("Загрузка…", "Завантаження…")}</div>;
  const d = sel?.diff;
  const box: any = { border: "1px solid #e2e8f0", borderRadius: 10, padding: "10px 12px", marginTop: 10, background: "#fff" };
  const showList = !narrow || !sel;
  const showDetail = !narrow || !!sel;
  const bal: any[] = sel?.totals?.balances || [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr" : "minmax(260px, 340px) minmax(0, 1fr)", gap: 14, alignItems: "start" }}>
      {showList && (
        <div className="panel" style={{ margin: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <b style={{ fontSize: 14 }}>📸 {t("Снимки дня", "Знімки дня")}</b>
            <button className="btn btn-light" style={{ height: 26, fontSize: 12, padding: "0 8px" }} onClick={() => setHelp(!help)}>{t("Как это работает", "Як це працює")}</button>
            {list.can_close_day && !list.today_closed && !closing && (
              <button className="btn btn-primary" style={{ height: 28, fontSize: 12.5, marginLeft: "auto" }} onClick={() => setClosing(true)}>{t("Закрыть день", "Закрити день")}</button>
            )}
          </div>
          {help && (
            <div style={{ fontSize: 12, lineHeight: 1.5, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "8px 10px", margin: "8px 0" }}>
              {t("1) В конце смены ответственный за деньги (право «Закрывать день») проверяет остатки, в кассе вписывает фактическую наличность и жмёт «Закрыть день» — CRM фотографирует все операции дня и остатки. 2) Не закрыли — автоснимок в ", "1) Наприкінці зміни відповідальний за гроші (право «Закривати день») перевіряє залишки, у касі вписує фактичну готівку і тисне «Закрити день» — CRM фотографує всі операції дня і залишки. 2) Не закрили — автознімок о ")}
              <b>{list.auto_time}</b>{t(" по Киеву (и в выходные). 3) Выберите день: видно, что изменилось после снимка — было → стало, удалено, перенесено, добавлено позже, кто менял. Клик по операции — её карточка с историей изменений. 4) Видят все, у кого есть доступ к Журналу. 5) Следующий шаг: после закрытия дня сумму, дату и счёт прошлым числом меняет только владелец и роль «Бухгалтер».", " за Києвом (і у вихідні). 3) Оберіть день: видно, що змінилось після знімка — було → стало, видалено, перенесено, додано пізніше, хто змінював. Клік по операції — її картка з історією змін. 4) Бачать усі, хто має доступ до Журналу. 5) Наступний крок: після закриття дня суму, дату й рахунок минулим числом змінює лише власник і роль «Бухгалтер».")}
            </div>
          )}
          <div className="muted" style={{ fontSize: 11.5, margin: "4px 0 8px", lineHeight: 1.4 }}>
            {t("Автоснимок в ", "Автознімок о ")}
            {timeEdit === null
              ? <b>{list.auto_time}</b>
              : <input value={timeEdit} onChange={(e) => setTimeEdit(e.target.value)} style={{ width: 60, height: 22, fontSize: 12 }} />}
            {t(" по Киеву.", " за Києвом.")}
            {list.can_edit_closed_day && (timeEdit === null
              ? <button className="btn btn-light" style={{ height: 20, fontSize: 11, padding: "0 6px", marginLeft: 6 }} onClick={() => setTimeEdit(list.auto_time)}>⚙</button>
              : <><button className="btn btn-primary" style={{ height: 22, fontSize: 11, padding: "0 6px", marginLeft: 6 }} onClick={saveTime}>OK</button><button className="btn btn-light" style={{ height: 22, fontSize: 11, padding: "0 6px", marginLeft: 4 }} onClick={() => setTimeEdit(null)}>✕</button></>)}
            {list.today_closed ? " " + t("Сегодня уже закрыт.", "Сьогодні вже закрито.") : ""}
          </div>
          {closing && <CloseDialog day={list.today} onCancel={() => setClosing(false)} onDone={(id) => { setClosing(false); load(id); }} />}
          {err && <div style={{ color: "#b91c1c", fontSize: 12, marginBottom: 6 }}>{err}</div>}
          {list.results.length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>{t("Снимков пока нет", "Знімків поки немає")}</div>}
          {list.results.map((s: any) => (
            <div key={s.id} onClick={() => open(s.id)} style={{ padding: "8px 8px", borderRadius: 8, cursor: "pointer", background: sel?.id === s.id ? "#eff6ff" : "transparent", borderBottom: "1px solid #f1f5f9" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <b>{dm(s.date)}</b>{s.version > 1 && <span className="muted" style={{ fontSize: 11 }}>v{s.version}</span>}
                {s.reopened_at && <span style={{ fontSize: 11, color: "#b45309" }}>{t("открыт заново", "відкрито знову")}</span>}
                <span className="muted" style={{ fontSize: 11 }}>{s.totals?.all?.n || 0} {t("оп.", "оп.")}</span>
                {s.diff_count > 0 && <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, color: "#b91c1c", background: "#fef2f2", borderRadius: 999, padding: "1px 7px" }}>⚠ {s.diff_count}</span>}
              </div>
              <div className="muted" style={{ fontSize: 11.5 }}>
                {s.kind_label} · {s.closed_by} {hm(s.closed_at)} · +{fmt(s.totals?.all?.in)} / −{fmt(s.totals?.all?.out)}
              </div>
            </div>
          ))}
        </div>
      )}

      {showDetail && (
        <div style={{ minWidth: 0 }}>
          {!sel && <div className="panel muted" style={{ margin: 0 }}>{t("Выберите день слева", "Оберіть день зліва")}</div>}
          {sel && (
            <div className="panel" style={{ margin: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {narrow && <button className="btn btn-light" style={{ height: 28, fontSize: 12 }} onClick={() => setSel(null)}>← {t("К списку", "До списку")}</button>}
                <b style={{ fontSize: 15 }}>{dm(sel.date)}</b>
                <span className="muted" style={{ fontSize: 12 }}>{sel.kind_label} · {sel.closed_by} · {hm(sel.closed_at)}{sel.version > 1 ? ` · v${sel.version}` : ""}</span>
                {list.can_edit_closed_day && (
                  <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                    <button className="btn btn-light" style={{ height: 28, fontSize: 12 }} disabled={busy} onClick={() => act(`/api/day-snapshots/${sel.id}/reclose/`)}>{t("Переснять", "Перезнімок")}</button>
                    {!sel.reopened_at && <button className="btn btn-light" style={{ height: 28, fontSize: 12 }} disabled={busy} onClick={() => act(`/api/day-snapshots/${sel.id}/reopen/`)}>{t("Открыть день", "Відкрити день")}</button>}
                  </span>
                )}
              </div>
              {sel.rows.length === 0 && (
                <div style={{ ...box, background: "#fffbeb", borderColor: "#fde68a", fontSize: 12.5 }}>
                  {t("На момент снимка за этот день не было ни одной операции. Если день закрыли слишком рано — нажмите «Переснять».", "На момент знімка за цей день не було жодної операції. Якщо день закрили зарано — натисніть «Перезнімок».")}
                </div>
              )}

              {bal.some((b) => b.fact != null) && (
                <div style={{ ...box }}>
                  <b>{t("Остатки при закрытии: система / факт", "Залишки при закритті: система / факт")}</b>
                  {bal.filter((b) => b.fact != null).map((b) => (
                    <div key={b.id} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto auto", gap: 10, fontSize: 12.5, padding: "4px 0", borderBottom: "1px solid #f1f5f9" }}>
                      <span>{b.name}</span><span>{fmt(b.system)}</span><span>{fmt(b.fact)}</span>
                      <b style={{ color: Math.abs(b.diff || 0) > 0.009 ? "#b91c1c" : "#15803d" }}>{Math.abs(b.diff || 0) > 0.009 ? fmt(b.diff) : "✓"}</b>
                    </div>
                  ))}
                </div>
              )}

              {d && d.changed.length > 0 && (
                <div style={{ ...box, borderColor: "#fecaca" }}>
                  <b style={{ color: "#b91c1c" }}>{t("Изменены деньги после снимка", "Змінено гроші після знімка")}</b>
                  {d.changed.map((c: any) => (
                    <div key={c.id} onClick={() => setTxOpen(c.id)} style={{ fontSize: 12.5, marginTop: 4, cursor: "pointer" }}>
                      #{c.id} · {c.now.account} · {c.fields.map((f: string) => <span key={f} style={{ marginRight: 8 }}>{FIELD[f] || f}: <s style={{ color: "#b91c1c" }}>{val(c.was, f)}</s> → <b style={{ color: "#15803d" }}>{val(c.now, f)}</b></span>)}
                    </div>
                  ))}
                </div>
              )}
              {d && d.deleted.length > 0 && (
                <div style={{ ...box, borderColor: "#fecaca" }}>
                  <b style={{ color: "#b91c1c" }}>{t("Удалено после снимка", "Видалено після знімка")}</b>
                  {d.deleted.map((r: any) => <OpRow key={r.id} r={r} onOpen={() => {}} bg="#fef2f2" />)}
                </div>
              )}
              {d && d.moved.length > 0 && (
                <div style={{ ...box, borderColor: "#fde68a" }}>
                  <b style={{ color: "#b45309" }}>{t("Перенесена дата", "Перенесено дату")}</b>
                  {d.moved.map((m: any) => <div key={m.id} onClick={() => setTxOpen(m.id)} style={{ fontSize: 12.5, marginTop: 4, cursor: "pointer" }}>#{m.id} · {m.was.account} · {fmt(m.was.amount)}: {dm(m.was.date)} → <b>{dm(m.now.date)}</b></div>)}
                </div>
              )}
              {d && (d.added_after.length > 0 || d.appeared.length > 0) && (
                <div style={box}>
                  <b>{t("Добавлено после снимка", "Додано після знімка")}</b>
                  <span className="muted" style={{ fontSize: 11.5, marginLeft: 6 }}>{t("банк/система — норма, «вручну» — проверить", "банк/система — норма, «вручну» — перевірити")}</span>
                  {[...d.added_after, ...d.appeared].map((r: any) => <OpRow key={r.id} r={r} onOpen={setTxOpen} bg={r.src === "вручну" ? "#fffbeb" : undefined} />)}
                </div>
              )}
              {d && d.other.length > 0 && (
                <details style={box}>
                  <summary style={{ cursor: "pointer", fontWeight: 600, color: "#475569" }}>{t("Изменено прочее", "Змінено інше")} ({d.other.length})</summary>
                  {d.other.map((c: any) => <div key={c.id} onClick={() => setTxOpen(c.id)} style={{ fontSize: 12, marginTop: 4, color: "#475569", cursor: "pointer" }}>#{c.id} · {c.fields.map((f: string) => `${FIELD[f] || f}: ${val(c.was, f)} → ${val(c.now, f)}`).join("; ")}</div>)}
                </details>
              )}
              {sel.log?.length > 0 && (
                <details style={box}>
                  <summary style={{ cursor: "pointer", fontWeight: 600, color: "#475569" }}>{t("Кто что менял", "Хто що змінював")} ({sel.log.length})</summary>
                  {sel.log.map((l: any, i: number) => <div key={i} style={{ fontSize: 12, marginTop: 3 }}>{hm(l.at)} · {l.actor} · #{l.object_id} · {l.action}: {l.detail}</div>)}
                </details>
              )}
              {d && sel.rows.length > 0 && d.count === 0 && d.other.length === 0 && <div style={{ ...box, color: "#15803d", borderColor: "#bbf7d0" }}>✓ {t("После снимка деньги не менялись", "Після знімка гроші не змінювались")}</div>}

              {sel.rows.length > 0 && (
                <div style={box}>
                  <b>{t("Операции в снимке", "Операції у знімку")} ({sel.rows.length})</b>
                  <span className="muted" style={{ fontSize: 11.5, marginLeft: 6 }}>{t("клик — открыть операцию", "клік — відкрити операцію")}</span>
                  {sel.rows.map((r: any) => <OpRow key={r.id} r={r} onOpen={setTxOpen} />)}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {txOpen && <TxCardModal txId={txOpen} onClose={() => setTxOpen(null)} onSaved={() => { setTxOpen(null); if (sel) open(sel.id); }} />}
    </div>
  );
}
