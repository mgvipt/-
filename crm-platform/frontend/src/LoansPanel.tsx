/* Кредити і позики (01.10.2026, Олег): «як правильно організувати кредиторку,
 * щоб видно було і відсотки — у кожного своя ставка за свій період».
 * Ставку будь-якого періоду приводимо до місячної й до ефективної річної —
 * тоді кредити можна чесно порівняти й побачити, який найдорожчий. */
import { useEffect, useState } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

interface Loan {
  id: number; name: string; creditor: number | null; creditor_name: string;
  principal: string; balance: string; balance_uah: number; currency: string;
  rate_pct: string; rate_period: string; monthly_rate: number; yearly_rate: number;
  interest_month_uah: number; capitalize: boolean; accrual_day: number;
  started_at: string; last_accrual: string | null; is_active: boolean; comment: string;
}
interface Entry { id: number; kind: string; kind_label: string; date: string; amount: string; amount_uah: string; balance_after: string; comment: string }
interface Sum { loans: any[]; total_uah: number; interest_month_uah: number; interest_year_uah: number }

const PERIODS: [string, string][] = [["month", "на місяць"], ["day", "на день"], ["year", "річна"], ["none", "без відсотків"]];
const money = (v: number) => Math.round(v).toLocaleString("ru").replace(/,/g, " ") + " ₴";

export default function LoansPanel({ canEdit }: { canEdit: boolean }) {
  const { t } = useLang();
  const [rows, setRows] = useState<Loan[]>([]);
  const [sum, setSum] = useState<Sum | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [add, setAdd] = useState(false);
  const [err, setErr] = useState("");
  const [nw, setNw] = useState<any>({ name: "", creditor: "", balance: "", currency: "UAH", rate_pct: "", rate_period: "month", accrual_day: "1", capitalize: true, comment: "" });
  const [cands, setCands] = useState<any[]>([]);

  function load() {
    api.get<Loan[]>("/api/loans/").then((d) => setRows(d || [])).catch(() => setRows([]));
    api.get<Sum>("/api/loans/summary/").then(setSum).catch(() => {});
  }
  useEffect(load, []);
  useEffect(() => {
    if (open == null) { setEntries([]); return; }
    api.get<Entry[]>(`/api/loans/${open}/entries/`).then((d) => setEntries(d || [])).catch(() => setEntries([]));
  }, [open]);

  function findCreditor(q: string) {
    setNw((n: any) => ({ ...n, creditor_q: q }));
    if (q.trim().length < 2) { setCands([]); return; }
    api.get<any>(`/api/contacts/?search=${encodeURIComponent(q.trim())}&kind=creditor&page_size=8`)
      .then((d) => setCands(d.results || d || [])).catch(() => setCands([]));
  }

  async function save() {
    if (!nw.name.trim()) { setErr(t("Впишите название кредита", "Впишіть назву кредиту")); return; }
    setErr("");
    try {
      await api.post("/api/loans/", {
        name: nw.name.trim(), creditor: nw.creditor || null,
        principal: Number(nw.balance) || 0, balance: Number(nw.balance) || 0,
        currency: nw.currency, rate_pct: Number(nw.rate_pct) || 0, rate_period: nw.rate_period,
        accrual_day: Number(nw.accrual_day) || 1, capitalize: !!nw.capitalize,
        comment: nw.comment, is_active: true,
      });
      setAdd(false); setNw({ name: "", creditor: "", balance: "", currency: "UAH", rate_pct: "", rate_period: "month", accrual_day: "1", capitalize: true, comment: "" });
      load();
    } catch (e: any) { setErr(e?.response?.data?.detail || t("Не удалось сохранить", "Не вдалося зберегти")); }
  }

  async function accrueNow(id: number) {
    try { const r: any = await api.post(`/api/loans/${id}/accrue/`, {}); load();
      if (!r?.created) setErr(t("Начислять пока нечего — всё начислено", "Нараховувати поки нічого — все нараховано"));
    } catch { setErr(t("Не удалось начислить", "Не вдалося нарахувати")); }
  }

  const th: any = { textAlign: "left", fontSize: 11, textTransform: "uppercase", color: "#94a3b8", fontWeight: 700, padding: "7px 8px", borderBottom: "1px solid #e2e8f0", whiteSpace: "nowrap" };
  const td: any = { padding: "8px", borderBottom: "1px solid #f1f5f9", fontSize: 13 };
  const inp: any = { height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 9px", fontSize: 13, width: "100%", boxSizing: "border-box" };
  const lbl: any = { fontSize: 11.5, color: "#64748b", display: "block", marginBottom: 2 };

  return (
    <div>
      {sum && rows.length > 0 && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
          {[[t("Всего должны", "Всього винні"), money(sum.total_uah), "#7c3aed"],
            [t("Проценты в месяц", "Відсотки на місяць"), money(sum.interest_month_uah), "#dc2626"],
            [t("Проценты за год", "Відсотки за рік"), money(sum.interest_year_uah), "#b45309"]].map(([l, v, c]: any) => (
            <div key={l} className="panel" style={{ margin: 0, padding: "10px 16px", borderLeft: "4px solid " + c, minWidth: 180 }}>
              <div className="muted" style={{ fontSize: 11.5 }}>{l}</div>
              <div style={{ fontWeight: 800, fontSize: 19, color: c }}>{v}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>🏦 {t("Кредиты и займы", "Кредити і позики")}</h3>
        {canEdit && <button className="btn btn-primary" onClick={() => setAdd(!add)}>{add ? t("Отмена", "Скасувати") : "+ " + t("Добавить кредит", "Додати кредит")}</button>}
      </div>
      <p className="muted" style={{ fontSize: 12.5, margin: "0 0 12px", maxWidth: 820, lineHeight: 1.45 }}>
        {t("У каждого кредитора своя ставка и свой период. Чтобы кредиты можно было сравнить, ставка приводится к месячной и к эффективной годовой (с учётом того, что проценты капают на проценты). Самый дорогой кредит — сверху: его и гасить первым.",
           "У кожного кредитора своя ставка і свій період. Щоб кредити можна було порівняти, ставка приводиться до місячної і до ефективної річної (з урахуванням того, що відсотки капають на відсотки). Найдорожчий кредит — зверху: його й гасити першим.")}
      </p>
      {err && <div style={{ color: "#b45309", fontSize: 12.5, marginBottom: 8 }}>{err}</div>}

      {add && canEdit && (
        <div className="panel" style={{ padding: 14, marginBottom: 14 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 10 }}>
            <label><span style={lbl}>{t("Название", "Назва")}</span>
              <input style={inp} value={nw.name} onChange={(e) => setNw({ ...nw, name: e.target.value })} placeholder={t("Кредитный лимит ФОП", "Кредитний ліміт ФОП")} /></label>
            <label style={{ position: "relative" }}><span style={lbl}>{t("Кредитор", "Кредитор")}</span>
              <input style={inp} value={nw.creditor_q || ""} onChange={(e) => findCreditor(e.target.value)} placeholder={t("начните вводить…", "почніть вводити…")} />
              {cands.length > 0 && (
                <div style={{ position: "absolute", top: 56, left: 0, right: 0, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, zIndex: 20, boxShadow: "0 8px 24px rgba(15,23,42,.15)" }}>
                  {cands.map((c) => (
                    <div key={c.id} onMouseDown={() => { setNw({ ...nw, creditor: c.id, creditor_q: (c.first_name || "") + " " + (c.last_name || "") }); setCands([]); }}
                         style={{ padding: "7px 10px", cursor: "pointer", fontSize: 12.5, borderBottom: "1px solid #f1f5f9" }}>{c.first_name} {c.last_name}</div>
                  ))}
                </div>
              )}</label>
            <label><span style={lbl}>{t("Сколько должны сейчас", "Скільки винні зараз")}</span>
              <input style={inp} type="number" value={nw.balance} onChange={(e) => setNw({ ...nw, balance: e.target.value })} /></label>
            <label><span style={lbl}>{t("Валюта", "Валюта")}</span>
              <select style={inp} value={nw.currency} onChange={(e) => setNw({ ...nw, currency: e.target.value })}>
                <option value="UAH">UAH · гривня</option><option value="USD">USD · долар</option><option value="EUR">EUR · євро</option>
              </select></label>
            <label><span style={lbl}>{t("Ставка, %", "Ставка, %")}</span>
              <input style={inp} type="number" step="0.01" value={nw.rate_pct} onChange={(e) => setNw({ ...nw, rate_pct: e.target.value })} placeholder="1.3" /></label>
            <label><span style={lbl}>{t("За период", "За період")}</span>
              <select style={inp} value={nw.rate_period} onChange={(e) => setNw({ ...nw, rate_period: e.target.value })}>
                {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></label>
            {nw.rate_period === "month" && (
              <label><span style={lbl}>{t("Число начисления", "Число нарахування")}</span>
                <input style={inp} type="number" min={1} max={28} value={nw.accrual_day} onChange={(e) => setNw({ ...nw, accrual_day: e.target.value })} /></label>
            )}
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 10, fontSize: 12.5 }}>
            <input type="checkbox" checked={nw.capitalize} onChange={(e) => setNw({ ...nw, capitalize: e.target.checked })} />
            {t("Проценты добавляются к долгу (в следующий раз считаются от большей суммы)", "Відсотки додаються до боргу (наступного разу рахуються від більшої суми)")}
          </label>
          <div style={{ marginTop: 10 }}>
            <input style={inp} value={nw.comment} onChange={(e) => setNw({ ...nw, comment: e.target.value })} placeholder={t("Комментарий: условия, договор…", "Коментар: умови, договір…")} />
          </div>
          <button className="btn btn-primary" style={{ marginTop: 10 }} onClick={save}>{t("Сохранить", "Зберегти")}</button>
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 820 }}>
          <thead><tr>
            <th style={th}>{t("Кредит", "Кредит")}</th>
            <th style={{ ...th, textAlign: "right" }}>{t("Остаток", "Залишок")}</th>
            <th style={{ ...th, textAlign: "right" }}>{t("Ставка", "Ставка")}</th>
            <th style={{ ...th, textAlign: "right" }}>{t("В месяц", "На місяць")}</th>
            <th style={{ ...th, textAlign: "right" }}>{t("Годовых", "Річних")}</th>
            <th style={{ ...th, textAlign: "right" }}>{t("% в месяц", "% на місяць")}</th>
            <th style={th}></th>
          </tr></thead>
          <tbody>
            {rows.map((l) => {
              const isOpen = open === l.id;
              return [
                <tr key={l.id} style={{ cursor: "pointer", background: isOpen ? "#faf5ff" : undefined }} onClick={() => setOpen(isOpen ? null : l.id)}>
                  <td style={{ ...td, fontWeight: 600 }}>{isOpen ? "▾ " : "▸ "}{l.name}
                    {l.creditor_name && <div className="muted" style={{ fontSize: 11.5, fontWeight: 400 }}>{l.creditor_name}</div>}</td>
                  <td style={{ ...td, textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>
                    {money(l.balance_uah)}
                    {l.currency !== "UAH" && <div className="muted" style={{ fontSize: 11, fontWeight: 400 }}>{Number(l.balance).toLocaleString("ru")} {l.currency}</div>}</td>
                  <td style={{ ...td, textAlign: "right", whiteSpace: "nowrap" }}>{Number(l.rate_pct)}%
                    <div className="muted" style={{ fontSize: 11 }}>{(PERIODS.find(([v]) => v === l.rate_period) || ["", ""])[1]}</div></td>
                  <td style={{ ...td, textAlign: "right", whiteSpace: "nowrap" }}>{l.monthly_rate.toFixed(2)}%</td>
                  <td style={{ ...td, textAlign: "right", fontWeight: 700, color: l.yearly_rate >= 35 ? "#dc2626" : l.yearly_rate >= 20 ? "#b45309" : "#0f172a", whiteSpace: "nowrap" }}>{l.yearly_rate.toFixed(1)}%</td>
                  <td style={{ ...td, textAlign: "right", color: "#dc2626", whiteSpace: "nowrap" }}>{money(l.interest_month_uah)}</td>
                  <td style={{ ...td, textAlign: "right" }}>
                    {canEdit && <button className="btn btn-light" style={{ height: 26, fontSize: 11.5 }} onClick={(e) => { e.stopPropagation(); accrueNow(l.id); }}
                      title={t("Начислить проценты по сегодня", "Нарахувати відсотки по сьогодні")}>{t("Начислить", "Нарахувати")}</button>}</td>
                </tr>,
                isOpen && (
                  <tr key={l.id + "-d"}><td colSpan={7} style={{ padding: "4px 8px 14px", background: "#faf5ff" }}>
                    {l.comment && <p className="muted" style={{ fontSize: 12.5, margin: "4px 0 8px" }}>{l.comment}</p>}
                    <div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>
                      {t("Начисление", "Нарахування")}: {l.rate_period === "month" ? t("каждое ", "кожне ") + l.accrual_day + t("-е число", "-е число") : l.rate_period === "day" ? t("каждый день", "щодня") : "—"}
                      {l.capitalize ? " · " + t("проценты добавляются к долгу", "відсотки додаються до боргу") : ""}
                      {l.last_accrual ? " · " + t("последнее", "останнє") + ": " + l.last_accrual : ""}
                    </div>
                    <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
                      <thead><tr>
                        <th style={{ ...th, fontSize: 10 }}>{t("Дата", "Дата")}</th><th style={{ ...th, fontSize: 10 }}>{t("Что", "Що")}</th>
                        <th style={{ ...th, fontSize: 10, textAlign: "right" }}>{t("Сумма", "Сума")}</th>
                        <th style={{ ...th, fontSize: 10, textAlign: "right" }}>{t("Остаток после", "Залишок після")}</th>
                        <th style={{ ...th, fontSize: 10 }}>{t("Комментарий", "Коментар")}</th>
                      </tr></thead>
                      <tbody>
                        {entries.map((e) => (
                          <tr key={e.id}>
                            <td style={{ ...td, padding: "5px 8px" }}>{e.date}</td>
                            <td style={{ ...td, padding: "5px 8px" }}>{e.kind_label}</td>
                            <td style={{ ...td, padding: "5px 8px", textAlign: "right", color: Number(e.amount) < 0 ? "#16a34a" : "#dc2626", fontWeight: 600, whiteSpace: "nowrap" }}>
                              {Number(e.amount) > 0 ? "+" : ""}{Number(e.amount).toLocaleString("ru")} {l.currency}</td>
                            <td style={{ ...td, padding: "5px 8px", textAlign: "right", whiteSpace: "nowrap" }}>{Number(e.balance_after).toLocaleString("ru")}</td>
                            <td style={{ ...td, padding: "5px 8px", color: "#64748b" }}>{e.comment}</td>
                          </tr>
                        ))}
                        {!entries.length && <tr><td style={{ ...td, color: "#94a3b8" }} colSpan={5}>{t("Движений пока нет", "Рухів поки немає")}</td></tr>}
                      </tbody>
                    </table>
                  </td></tr>
                ),
              ];
            })}
            {!rows.length && <tr><td style={{ ...td, color: "#94a3b8" }} colSpan={7}>{t("Кредитов пока нет", "Кредитів поки немає")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
