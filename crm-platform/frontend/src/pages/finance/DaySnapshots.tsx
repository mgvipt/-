/* Фінанси → Операції → Знімки дня.
 * «Закрити день» фотографує всі операції дня (замість скріна журналу в Telegram о 18:00);
 * автознімок — о 18:00 за Києвом. Праворуч — що змінилось після знімка (було → стало). */
import { useEffect, useState } from "react";
import { api } from "../../api";
import { useLang } from "../../i18n";

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

function RowLine({ r }: { r: any }) {
  return (
    <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
      <td style={{ padding: "5px 6px", whiteSpace: "nowrap", color: "#64748b" }}>{r.op_time || ""}</td>
      <td style={{ padding: "5px 6px" }}>{r.account}{r.transfer_account ? ` → ${r.transfer_account}` : ""}</td>
      <td style={{ padding: "5px 6px" }}>{r.counterparty || r.category || "—"}</td>
      <td style={{ padding: "5px 6px", color: "#94a3b8", fontSize: 11 }}>{r.src}</td>
      <td style={{ padding: "5px 6px", textAlign: "right", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: r.direction === "in" ? "#16a34a" : r.direction === "out" ? "#dc2626" : "#475569" }}>
        {DIR[r.direction]}{fmt(r.amount)} {r.currency !== "UAH" ? r.currency : ""}
      </td>
    </tr>
  );
}

export default function DaySnapshots() {
  const { t } = useLang();
  const [list, setList] = useState<any>(null);
  const [sel, setSel] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const load = () => api.get<any>(`/api/day-snapshots/?from=${monthAgo()}&to=${todayIso()}`).then(setList).catch(() => setErr(t("Нет доступа или ошибка загрузки", "Немає доступу або помилка завантаження")));
  const open = (id: number) => api.get<any>(`/api/day-snapshots/${id}/`).then(setSel).catch(() => setErr(t("Не удалось открыть снимок", "Не вдалося відкрити знімок")));
  useEffect(() => { load(); }, []);
  async function act(url: string, body: any = {}) {
    setBusy(true); setErr("");
    try { const r = await api.post<any>(url, body); await load(); if (r?.id) await open(r.id); }
    catch (e: any) { setErr(e?.data?.detail || e?.response?.data?.detail || t("Ошибка", "Помилка")); }
    setBusy(false);
  }
  if (!list) return <div className="spin">{err || t("Загрузка…", "Завантаження…")}</div>;
  const d = sel?.diff;
  const box: any = { border: "1px solid #e2e8f0", borderRadius: 10, padding: "10px 12px", marginTop: 10, background: "#fff" };
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 340px) minmax(0, 1fr)", gap: 14, alignItems: "start" }}>
      <div className="panel" style={{ margin: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <b style={{ fontSize: 14 }}>📸 {t("Снимки дня", "Знімки дня")}</b>
          {list.can_close_day && !list.today_closed && (
            <button className="btn btn-primary" style={{ height: 28, fontSize: 12.5, marginLeft: "auto" }} disabled={busy}
              onClick={() => act("/api/day-snapshots/close/", { date: list.today })}>{t("Закрыть день", "Закрити день")}</button>
          )}
        </div>
        <div className="muted" style={{ fontSize: 11.5, margin: "4px 0 8px", lineHeight: 1.4 }}>
          {t("Фото всех операций дня вместо скрина в Telegram. Автоснимок — в 18:00 по Киеву.", "Фото всіх операцій дня замість скріна в Telegram. Автознімок — о 18:00 за Києвом.")}
          {list.today_closed ? " " + t("Сегодня уже закрыт.", "Сьогодні вже закрито.") : ""}
        </div>
        {err && <div style={{ color: "#b91c1c", fontSize: 12, marginBottom: 6 }}>{err}</div>}
        {list.results.length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>{t("Снимков пока нет", "Знімків поки немає")}</div>}
        {list.results.map((s: any) => (
          <div key={s.id} onClick={() => open(s.id)} style={{ padding: "8px 8px", borderRadius: 8, cursor: "pointer", background: sel?.id === s.id ? "#eff6ff" : "transparent", borderBottom: "1px solid #f1f5f9" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <b>{dm(s.date)}</b>{s.version > 1 && <span className="muted" style={{ fontSize: 11 }}>v{s.version}</span>}
              {s.reopened_at && <span style={{ fontSize: 11, color: "#b45309" }}>{t("открыт", "відкрито")}</span>}
              {s.diff_count > 0 && <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, color: "#b91c1c", background: "#fef2f2", borderRadius: 999, padding: "1px 7px" }}>⚠ {s.diff_count}</span>}
            </div>
            <div className="muted" style={{ fontSize: 11.5 }}>
              {s.kind_label} · {s.closed_by} {hm(s.closed_at)} · +{fmt(s.totals?.all?.in)} / −{fmt(s.totals?.all?.out)}
            </div>
          </div>
        ))}
      </div>

      <div style={{ minWidth: 0 }}>
        {!sel && <div className="panel muted" style={{ margin: 0 }}>{t("Выберите день слева", "Оберіть день зліва")}</div>}
        {sel && (
          <div className="panel" style={{ margin: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <b style={{ fontSize: 15 }}>{dm(sel.date)}</b>
              <span className="muted" style={{ fontSize: 12 }}>{sel.kind_label} · {sel.closed_by} · {hm(sel.closed_at)}</span>
              {list.can_edit_closed_day && (
                <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  <button className="btn btn-light" style={{ height: 28, fontSize: 12 }} disabled={busy} onClick={() => act(`/api/day-snapshots/${sel.id}/reclose/`)}>{t("Переснять", "Перезнімок")}</button>
                  {!sel.reopened_at && <button className="btn btn-light" style={{ height: 28, fontSize: 12 }} disabled={busy} onClick={() => act(`/api/day-snapshots/${sel.id}/reopen/`)}>{t("Открыть день", "Відкрити день")}</button>}
                </span>
              )}
            </div>

            <div className="tb" style={{ overflowX: "auto", marginTop: 8 }}>
              <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
                <thead><tr style={{ color: "#64748b", fontSize: 11 }}><th style={{ textAlign: "left", padding: 4 }}>{t("Счёт", "Рахунок")}</th><th style={{ textAlign: "right", padding: 4 }}>{t("В снимке", "У знімку")}</th><th style={{ textAlign: "right", padding: 4 }}>{t("Сейчас", "Зараз")}</th><th style={{ textAlign: "right", padding: 4 }}>Δ</th></tr></thead>
                <tbody>
                  {Array.from(new Set([...Object.keys(sel.totals?.accounts || {}), ...Object.keys(d?.totals_now?.accounts || {})])).map((k) => {
                    const a = sel.totals?.accounts?.[k]; const b = d?.totals_now?.accounts?.[k];
                    const delta = (b?.net || 0) - (a?.net || 0);
                    return (
                      <tr key={k} style={{ borderTop: "1px solid #f1f5f9" }}>
                        <td style={{ padding: 4 }}>{(a || b)?.name}</td>
                        <td style={{ padding: 4, textAlign: "right" }}>{fmt(a?.net ?? 0)}</td>
                        <td style={{ padding: 4, textAlign: "right" }}>{fmt(b?.net ?? 0)}</td>
                        <td style={{ padding: 4, textAlign: "right", fontWeight: 700, color: Math.abs(delta) > 0.009 ? "#b91c1c" : "#94a3b8" }}>{Math.abs(delta) > 0.009 ? fmt(delta) : "0"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {d && d.changed.length > 0 && (
              <div style={{ ...box, borderColor: "#fecaca" }}>
                <b style={{ color: "#b91c1c" }}>{t("Изменены деньги после снимка", "Змінено гроші після знімка")}</b>
                {d.changed.map((c: any) => (
                  <div key={c.id} style={{ fontSize: 12.5, marginTop: 4 }}>
                    #{c.id} · {c.now.account} · {c.fields.map((f: string) => <span key={f} style={{ marginRight: 8 }}>{FIELD[f] || f}: <s style={{ color: "#b91c1c" }}>{val(c.was, f)}</s> → <b style={{ color: "#15803d" }}>{val(c.now, f)}</b></span>)}
                  </div>
                ))}
              </div>
            )}
            {d && d.deleted.length > 0 && (
              <div style={{ ...box, borderColor: "#fecaca" }}>
                <b style={{ color: "#b91c1c" }}>{t("Удалено после снимка", "Видалено після знімка")}</b>
                <table style={{ width: "100%", fontSize: 12.5 }}><tbody>{d.deleted.map((r: any) => <RowLine key={r.id} r={r} />)}</tbody></table>
              </div>
            )}
            {d && d.moved.length > 0 && (
              <div style={{ ...box, borderColor: "#fde68a" }}>
                <b style={{ color: "#b45309" }}>{t("Перенесена дата", "Перенесено дату")}</b>
                {d.moved.map((m: any) => <div key={m.id} style={{ fontSize: 12.5, marginTop: 4 }}>#{m.id} · {m.was.account} · {fmt(m.was.amount)}: {dm(m.was.date)} → <b>{dm(m.now.date)}</b></div>)}
              </div>
            )}
            {d && (d.added_after.length > 0 || d.appeared.length > 0) && (
              <div style={box}>
                <b>{t("Добавлено после снимка", "Додано після знімка")}</b>
                <span className="muted" style={{ fontSize: 11.5, marginLeft: 6 }}>{t("банк/система — норма, «вручну» — проверить", "банк/система — норма, «вручну» — перевірити")}</span>
                <table style={{ width: "100%", fontSize: 12.5 }}><tbody>{[...d.added_after, ...d.appeared].map((r: any) => (
                  <tr key={r.id} style={{ background: r.src === "вручну" ? "#fffbeb" : "transparent" }}><td colSpan={5} style={{ padding: 0 }}><table style={{ width: "100%" }}><tbody><RowLine r={r} /></tbody></table></td></tr>
                ))}</tbody></table>
              </div>
            )}
            {d && d.other.length > 0 && (
              <details style={{ ...box }}>
                <summary style={{ cursor: "pointer", fontWeight: 600, color: "#475569" }}>{t("Изменено прочее", "Змінено інше")} ({d.other.length})</summary>
                {d.other.map((c: any) => <div key={c.id} style={{ fontSize: 12, marginTop: 4, color: "#475569" }}>#{c.id} · {c.fields.map((f: string) => `${FIELD[f] || f}: ${val(c.was, f)} → ${val(c.now, f)}`).join("; ")}</div>)}
              </details>
            )}
            {sel.log?.length > 0 && (
              <details style={box}>
                <summary style={{ cursor: "pointer", fontWeight: 600, color: "#475569" }}>{t("Кто что менял", "Хто що змінював")} ({sel.log.length})</summary>
                {sel.log.map((l: any, i: number) => <div key={i} style={{ fontSize: 12, marginTop: 3 }}>{hm(l.at)} · {l.actor} · #{l.object_id} · {l.action}: {l.detail}</div>)}
              </details>
            )}
            {d && d.count === 0 && d.other.length === 0 && <div style={{ ...box, color: "#15803d", borderColor: "#bbf7d0" }}>✓ {t("После снимка деньги не менялись", "Після знімка гроші не змінювались")}</div>}

            <div style={{ ...box }}>
              <b>{t("Операции в снимке", "Операції у знімку")} ({sel.rows.length})</b>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", fontSize: 12.5 }}><tbody>{sel.rows.map((r: any) => <RowLine key={r.id} r={r} />)}</tbody></table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
