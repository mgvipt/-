/* Картка клієнта (контакту): поля як у Бітриксі + історія сделок.
 * Відкривається зі списку «Клієнти» або зі сделки. /clients/:id */
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Avatar, SourceChip, SOURCES } from "../ui";
import OwnerSelect from "../OwnerSelect";
import CallButton from "../CallButton";
import { useLang } from "../i18n";
import { SocialLink } from "../social";

interface Deal { id: number; title: string; amount: number; stage: string; is_won: boolean; created_at: string; }
interface Contact {
  id: number; first_name: string; last_name: string; display_name: string; phone: string; email: string; social_link: string;
  source: string; address: string; comment: string; loyalty_tag: string; birthday: string | null;
  channels: string[]; owner?: number | null; owner_name?: string; deals: Deal[]; total_spent: number;
}
const money = (n: number) => Math.round(n || 0).toLocaleString("ru") + " ₴";
const LOYALTY = ["", "Новий", "Активний", "VIP", "Сплячий"];

export default function ClientCard() {
  const { id } = useParams();
  const { t } = useLang();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const backChat = sp.get("c");
  const [c, setC] = useState<Contact | null>(null);
  const [msg, setMsg] = useState("");
  const [ndOpen, setNdOpen] = useState(false);
  const [ndFunnels, setNdFunnels] = useState<any[]>([]);
  const [nd, setNd] = useState<any>({ funnel: 0, title: "", amount: "" });
  const [ndBusy, setNdBusy] = useState(false);
  async function openNewDeal() {
    if (ndOpen) { setNdOpen(false); return; }
    try {
      const r = await api.get<any>("/api/funnels/");
      const fs = ((r.results || r) as any[]).filter((f: any) => !f.is_lead_funnel && (f.stages || []).length);
      setNdFunnels(fs);
      const def = fs.find((f: any) => (f.name || "").toLowerCase().includes("покры") || (f.name || "").toLowerCase().includes("покрит")) || fs[0];
      setNd({ funnel: def?.id || 0, title: c?.display_name || "", amount: "" });
      setNdOpen(true);
    } catch { setMsg(t("Не удалось загрузить воронки","Не вдалося завантажити воронки")); }
  }
  async function createDeal() {
    const f = ndFunnels.find((x: any) => x.id === Number(nd.funnel));
    if (!f || !nd.title.trim()) { setMsg(t("Выбери воронку и впиши название","Обери воронку і впиши назву")); return; }
    setNdBusy(true);
    try {
      const stage = (f.stages || []).slice().sort((a: any, b: any) => a.order - b.order)[0];
      const body: any = { title: nd.title.trim(), contact: Number(id), funnel: f.id, stage: stage?.id, amount: Number(nd.amount) || 0 };
      const src = (c?.channels && c.channels[0]) || "";
      if (src) body.source = src;
      const r = await api.post<any>("/api/deals/", body);
      nav(`/deals/${r.id}`);
    } catch (e: any) { setMsg(e?.response?.data?.detail || t("Не удалось создать сделку","Не вдалося створити угоду")); }
    finally { setNdBusy(false); }
  }
  const load = () => api.get<Contact>(`/api/contacts/${id}/`).then(setC);
  useEffect(() => { load(); }, [id]);
  if (!c) return <div className="spin">{t("Загрузка клиента…","Завантаження клієнта…")}</div>;

  async function save(patch: Partial<Contact>) {
    await api.patch(`/api/contacts/${id}/`, patch);
    setMsg(t("Сохранено","Збережено")); setTimeout(() => setMsg(""), 1500);
  }
  const fld = (label: string, key: keyof Contact, hint?: string) => (
    <div style={{ marginBottom: 10 }}>
      <div className="label" title={hint}>{label}</div>
      <input defaultValue={(c as any)[key] || ""} onBlur={(e) => save({ [key]: e.target.value } as any)}
        style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 10px" }} />
    </div>
  );

  return (
    <div className="scroll pad fade">
      <div className="dealhead">
        <button className="back" title={backChat ? t("Вернуться в чат с клиентом","Повернутися в чат з клієнтом") : t("К списку клиентов","До списку клієнтів")} onClick={() => nav(backChat ? `/inbox?c=${backChat}` : "/clients")}>←</button>
        <Avatar name={c.display_name} cls="av-md" />
        <b style={{ fontSize: 16 }}>{c.display_name}</b>
        {c.loyalty_tag && <span className="chip" style={{ background: "#eef2ff", color: "#4338ca" }}>{c.loyalty_tag}</span>}
        <CallButton contact={c.id} small />
        <button className="btn btn-primary" style={{ height: 30, fontSize: 12.5, padding: "0 12px" }} onClick={openNewDeal}>{ndOpen ? "✕" : "➕ " + t("Создать сделку","Створити угоду")}</button>
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        <span className="muted">{t("Потратил всего","Витратив усього")}: <b style={{ color: "#16a34a" }}>{money(c.total_spent)}</b></span>
      </div>

      <div className="grid2">
        <div>
          <div className="panel">
            <div className="label" style={{ marginBottom: 8 }}>{t("Данные клиента","Дані клієнта")} <span className="muted" style={{ fontWeight: 400 }}>{t("(кликни поле, чтобы изменить)","(клікни поле, щоб змінити)")}</span></div>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ flex: 1 }}>{fld(t("Имя","Імʼя"), "first_name")}</div>
              <div style={{ flex: 1 }}>{fld(t("Фамилия","Прізвище"), "last_name")}</div>
            </div>
            {fld(t("Телефон","Телефон"), "phone", t("Основной контактный номер","Основний контактний номер"))}
            {fld(t("Email","Email"), "email")}
            {fld(t("Ссылка на аккаунт (мессенджер)","Посилання на акаунт (месенджер)"), "social_link", "t.me / instagram.com…")}
            <SocialLink link={c.social_link} />
            {fld(t("Адрес / город","Адреса / місто"), "address", t("Куда доставлять","Куди доставляти"))}
            <div style={{ marginBottom: 10 }}>
              <div className="label">{t("Лояльность","Лояльність")}</div>
              <select defaultValue={c.loyalty_tag} onChange={(e) => save({ loyalty_tag: e.target.value })}
                style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7 }}>
                {LOYALTY.map((l) => <option key={l} value={l}>{l || "—"}</option>)}
              </select>
            </div>
            <div style={{ marginBottom: 10 }}>
              <div className="label">{t("Источник","Джерело")}</div>
              <select value={c.source || ""} onChange={(e) => save({ source: e.target.value })}
                style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7 }}>
                <option value="">—</option>
                {Object.keys(SOURCES).map((k) => <option key={k} value={k}>{(SOURCES as any)[k][0]}</option>)}
              </select>
            </div>
            <div>
              <div className="label">{t("Заметки менеджера","Нотатки менеджера")}</div>
              <textarea defaultValue={c.comment} onBlur={(e) => save({ comment: e.target.value })}
                style={{ width: "100%", minHeight: 70, border: "1px solid #cbd5e1", borderRadius: 7, padding: 8 }} />
            </div>
            <div style={{ marginTop: 10 }}><div className="label">{t("Ответственный","Відповідальний")}</div><OwnerSelect ownerId={c.owner} ownerName={c.owner_name} onSet={async (uid) => { await api.patch(`/api/contacts/${id}/`, { owner: uid }); load(); }} /></div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 8 }}>{(c.channels || []).map((ch) => <SourceChip key={ch} source={ch} />)}</div>
          </div>
        </div>
        <div>
          <FinBlock contactId={c.id} cname={c.display_name} />
          <div className="panel">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div className="label" style={{ flex: 1, margin: 0 }}>{t("Сделки клиента","Угоди клієнта")} ({c.deals.length})</div>
              <button className="btn btn-primary" style={{ height: 28, fontSize: 12, padding: "0 12px" }} onClick={openNewDeal}>{ndOpen ? "✕" : "➕ " + t("Создать сделку","Створити угоду")}</button>
            </div>
            {ndOpen && (
              <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, margin: "8px 0" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div>
                    <div className="label" style={{ fontSize: 11 }}>{t("Воронка","Воронка")}</div>
                    <select value={nd.funnel} onChange={(e) => setNd({ ...nd, funnel: Number(e.target.value) })} style={{ width: "100%", height: 34, borderRadius: 7, border: "1px solid #cbd5e1", fontSize: 13 }}>
                      {ndFunnels.map((f: any) => <option key={f.id} value={f.id}>{f.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <div className="label" style={{ fontSize: 11 }}>{t("Сумма, ₴ (можно потом)","Сума, ₴ (можна потім)")}</div>
                    <input type="number" value={nd.amount} onChange={(e) => setNd({ ...nd, amount: e.target.value })} style={{ width: "100%", height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 13, boxSizing: "border-box" }} />
                  </div>
                </div>
                <div className="label" style={{ fontSize: 11, marginTop: 8 }}>{t("Название сделки","Назва угоди")}</div>
                <input value={nd.title} onChange={(e) => setNd({ ...nd, title: e.target.value })} style={{ width: "100%", height: 34, borderRadius: 7, border: "1px solid #cbd5e1", padding: "0 8px", fontSize: 13, boxSizing: "border-box" }} />
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  <button className="btn btn-primary" style={{ flex: 1 }} disabled={ndBusy} onClick={createDeal}>{ndBusy ? "…" : t("✓ Создать и открыть","✓ Створити і відкрити")}</button>
                  <button className="btn btn-light" onClick={() => setNdOpen(false)}>{t("Отмена","Скасувати")}</button>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{t("Сделка создаётся на первой стадии воронки, клиент подставится автоматически. Товары добавишь в карточке.","Угода створюється на першій стадії воронки, клієнт підставиться автоматично. Товари додаси в картці.")}</div>
              </div>
            )}
            {c.deals.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>{t("Сделок ещё нет.","Угод ще немає.")}</div> : (
              <table style={{ width: "100%", fontSize: 13, marginTop: 6 }}>
                <thead><tr><th style={{ textAlign: "left" }}>{t("Сделка","Угода")}</th><th>{t("Сумма","Сума")}</th><th>{t("Стадия","Стадія")}</th></tr></thead>
                <tbody>
                  {c.deals.map((d) => (
                    <tr key={d.id} onClick={() => nav(`/deals/${d.id}`)} style={{ cursor: "pointer", borderTop: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "6px 0", color: "#1d4ed8" }}>{d.title}</td>
                      <td style={{ textAlign: "right" }}>{money(d.amount)}</td>
                      <td style={{ textAlign: "center" }}><span className="chip" style={{ background: d.is_won ? "#dcfce7" : "#f1f5f9", color: d.is_won ? "#166534" : "#475569" }}>{d.stage || "—"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


function FinBlock({ contactId, cname }: { contactId: number; cname?: string }) {
  const navFB = useNavigate();
  const [opsLimit, setOpsLimit] = useState(50);
  const [opsPage, setOpsPage] = useState(0);
  /* Гроші по клієнту: доходи/витрати/аванси + останні операції + швидке створення доходу/витрати
     з автопривʼязкою клієнта (контрагент може бути майстром/магазином — гроші все одно по клієнту). */
  const { t } = useLang();
  const [d, setD] = useState<any>(null);
  const [form, setForm] = useState<null | "in" | "out">(null);
  const [accs, setAccs] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [fa, setFa] = useState({ amount: "", account: 0, cat: "", cp: "", comment: "" });
  const [payNow, setPayNow] = useState(true);
  const [recvLoan, setRecvLoan] = useState(false); // дебіторка: позика (мої гроші в борг) vs продаж (прибуток)
  const [busy, setBusy] = useState(false);
  const load = () => api.get<any>(`/api/contacts/${contactId}/finance/?limit=${opsLimit}&offset=${opsPage * opsLimit}`).then(setD).catch(() => {});
  useEffect(() => { load(); }, [contactId, opsLimit, opsPage]); // eslint-disable-line
  useEffect(() => { setOpsPage(0); }, [contactId]);
  const [cps, setCps] = useState<string[]>([]);
  useEffect(() => {
    if (form && accs.length === 0) {
      api.get<any>("/api/accounts/?page_size=200").then((x) => setAccs((x.results || x).filter((a: any) => a.is_active !== false)));
      api.get<any>("/api/categories/?page_size=500").then((x) => setCats((x.results || x).filter((cc: any) => !cc.hidden)));
      api.get<any>("/api/finance/counterparties/").then((x) => setCps(((x.results || x) as any[]).map((y: any) => y.name || String(y)).filter(Boolean))).catch(() => {});
    }
  }, [form]); // eslint-disable-line
  const money0 = (n: number) => Math.round(n || 0).toLocaleString("ru") + " ₴";
  async function add() {
    if (!Number(fa.amount) || busy) return;
    if (payNow && !fa.account) return;
    setBusy(true);
    try {
      if (form === "out" && !payNow) {
        // кредиторка: НЕ у журнал — у Дт/Кт; у журнал попаде після «Оплачено»
        const catId = (cats.find((cc: any) => cc.name === fa.cat) || {}).id || null;
        await api.post("/api/planned-payments/", { kind: "payable", amount: Number(String(fa.amount).replace(",", ".")),
          due_date: new Date().toISOString().slice(0, 10), counterparty: fa.cp, contact: contactId,
          category: catId, account: fa.account || null, comment: fa.comment });
      } else if (form === "in" && !payNow) {
        // дебіторка: нам винні → у Дт/Кт (не у журнал, доки не «Оплачено»)
        const catId = (cats.find((cc: any) => cc.name === fa.cat) || {}).id || null;
        await api.post("/api/planned-payments/", { kind: "receivable", is_loan: recvLoan, amount: Number(String(fa.amount).replace(",", ".")),
          due_date: new Date().toISOString().slice(0, 10), counterparty: fa.cp, contact: contactId,
          category: catId, account: fa.account || null, comment: fa.comment });
      } else {
        await api.post("/api/transactions/", { direction: form, amount: Number(String(fa.amount).replace(",", ".")), account: fa.account,
          set_category: fa.cat, counterparty: fa.cp, comment: fa.comment, contact: contactId, currency: "UAH", rate: 1 });
      }
      setForm(null); setFa({ amount: "", account: 0, cat: "", cp: "", comment: "" }); setPayNow(true); setRecvLoan(false); load();
    } finally { setBusy(false); }
  }
  const inpF: React.CSSProperties = { width: "100%", height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 9px", fontSize: 13, marginBottom: 6 };
  if (!d) return null;
  return (
    <div className="panel" style={{ marginBottom: 12 }}>
      <div className="label" style={{ marginBottom: 8 }}>{t("Финансы клиента","Фінанси клієнта")} <span className="muted" style={{ fontWeight: 400 }}>({d.count} {t("операций","операцій")})</span></div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        {[[t("Доход","Дохід"), d.income, "#16a34a", "#f0fdf4"], [t("Расход","Витрата"), d.expense, "#dc2626", "#fef2f2"], [t("Аванс (остаток денег клиента)","Аванс (залишок грошей клієнта)"), d.advance, "#2563eb", "#eff6ff"], [t("Кредиторка (мы должны)","Кредиторка (ми винні)"), d.debt, "#b45309", "#fffbeb"], [t("Дебиторка (нам должны)","Дебіторка (нам винні)"), d.receivable, "#0e7490", "#ecfeff"]].map(([l, v, cl, bg]: any, i) => (
          <div key={i} style={{ flex: 1, minWidth: 110, background: bg, borderRadius: 10, padding: "8px 10px" }}>
            <div className="muted" style={{ fontSize: 10.5 }}>{l}</div>
            <b style={{ color: cl, fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{money0(Number(v))}</b>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <button className="btn btn-light" style={{ flex: 1, color: "#16a34a", fontWeight: 700 }} onClick={() => { setPayNow(true); setRecvLoan(false); setForm(form === "in" ? null : "in"); }}>+ {t("Доход","Дохід")}</button>
        <button className="btn btn-light" style={{ flex: 1, color: "#dc2626", fontWeight: 700 }} onClick={() => { setPayNow(true); setForm(form === "out" ? null : "out"); }}>+ {t("Расход","Витрата")}</button>
        <a href={`/finance?client=${contactId}&cname=${encodeURIComponent(cname || "")}`} className="btn btn-light" style={{ whiteSpace: "nowrap" }} title={t("Открыть журнал с фильтром по клиенту","Відкрити журнал з фільтром за клієнтом")}>🧾</a>
      </div>
      {form && (
        <div style={{ background: form === "in" ? "#f0fdf4" : "#fef2f2", borderRadius: 10, padding: 10, marginBottom: 10 }}>
          {form === "out" && (
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              <span onClick={() => setPayNow(true)} style={{ flex: 1, textAlign: "center", padding: "6px 8px", borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: "pointer", background: payNow ? "#dc2626" : "#fff", color: payNow ? "#fff" : "#64748b", border: "1.5px solid " + (payNow ? "#dc2626" : "#e2e8f0") }}>💸 {t("Оплата сейчас","Оплата зараз")}</span>
              <span onClick={() => setPayNow(false)} style={{ flex: 1, textAlign: "center", padding: "6px 8px", borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: "pointer", background: !payNow ? "#b45309" : "#fff", color: !payNow ? "#fff" : "#64748b", border: "1.5px solid " + (!payNow ? "#b45309" : "#e2e8f0") }}>🕐 {t("Кредиторка (оплатим позже)","Кредиторка (оплатимо пізніше)")}</span>
            </div>
          )}
          {form === "in" && (
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              <span onClick={() => setPayNow(true)} style={{ flex: 1, textAlign: "center", padding: "6px 8px", borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: "pointer", background: payNow ? "#16a34a" : "#fff", color: payNow ? "#fff" : "#64748b", border: "1.5px solid " + (payNow ? "#16a34a" : "#e2e8f0") }}>💰 {t("Деньги пришли","Гроші прийшли")}</span>
              <span onClick={() => setPayNow(false)} style={{ flex: 1, textAlign: "center", padding: "6px 8px", borderRadius: 999, fontSize: 12, fontWeight: 700, cursor: "pointer", background: !payNow ? "#0e7490" : "#fff", color: !payNow ? "#fff" : "#64748b", border: "1.5px solid " + (!payNow ? "#0e7490" : "#e2e8f0") }}>🕐 {t("Нам должны (дебиторка)","Нам винні (дебіторка)")}</span>
            </div>
          )}
          {form === "in" && !payNow && (
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              <span onClick={() => setRecvLoan(false)} title={t("Клиент должен за товар/услугу — это будущая прибыль","Клієнт винен за товар/послугу — це майбутній прибуток")} style={{ flex: 1, textAlign: "center", padding: "5px 6px", borderRadius: 999, fontSize: 11.5, fontWeight: 700, cursor: "pointer", background: !recvLoan ? "#16a34a" : "#fff", color: !recvLoan ? "#fff" : "#64748b", border: "1.5px solid " + (!recvLoan ? "#16a34a" : "#e2e8f0") }}>🛒 {t("Продажа","Продаж")}</span>
              <span onClick={() => setRecvLoan(true)} title={t("Я дал свои деньги в долг — возврат НЕ прибыль (только проценты доход)","Я дав свої гроші в борг — повернення НЕ прибуток (лише відсотки дохід)")} style={{ flex: 1, textAlign: "center", padding: "5px 6px", borderRadius: 999, fontSize: 11.5, fontWeight: 700, cursor: "pointer", background: recvLoan ? "#7c3aed" : "#fff", color: recvLoan ? "#fff" : "#64748b", border: "1.5px solid " + (recvLoan ? "#7c3aed" : "#e2e8f0") }}>🤝 {t("Заём (в долг)","Позика (в борг)")}</span>
            </div>
          )}
          <input value={fa.amount} onChange={(e) => setFa({ ...fa, amount: e.target.value })} placeholder={t("Сумма, грн","Сума, грн")} style={inpF} />
          <select value={fa.account} onChange={(e) => setFa({ ...fa, account: Number(e.target.value) })} style={inpF}>
            <option value={0}>{t("— счёт —","— рахунок —")}</option>
            {accs.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <select value={fa.cat} onChange={(e) => setFa({ ...fa, cat: e.target.value })} style={inpF}>
            <option value="">{t("— категория —","— категорія —")}</option>
            {cats.filter((cc: any) => cc.direction === form).map((cc: any) => <option key={cc.id} value={cc.name}>{cc.parent ? "└ " : ""}{cc.name}</option>)}
          </select>
          <input value={fa.cp} onChange={(e) => setFa({ ...fa, cp: e.target.value })} placeholder={t("Контрагент (мастер/магазин/клиент)","Контрагент (майстер/магазин/клієнт)")} list="ccfin-cps" style={inpF} />
          <datalist id="ccfin-cps">{cps.slice(0, 400).map((nm) => <option key={nm} value={nm} />)}</datalist>
          <input value={fa.comment} onChange={(e) => setFa({ ...fa, comment: e.target.value })} placeholder={t("Комментарий","Коментар")} style={inpF} />
          <button className="btn btn-primary" style={{ width: "100%", background: form === "out" && !payNow ? "#b45309" : (form === "in" && !payNow ? "#0e7490" : undefined) }} disabled={busy || !Number(fa.amount) || (payNow && !fa.account)} onClick={add}>{busy ? "…" : (form === "out" && !payNow ? t("В кредиторку (журнал — после оплаты)","У кредиторку (журнал — після оплати)") : form === "in" && !payNow ? t("В дебиторку (нам должны)","У дебіторку (нам винні)") : t("Сохранить (клиент привяжется сам)","Зберегти (клієнт привʼяжеться сам)"))}</button>
        </div>
      )}
      {d.count > 0 && (
        <div style={{ marginTop: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6, fontSize: 12 }}>
            <span className="muted">{t("Показывать:", "Показувати:")}</span>
            <select value={opsLimit} onChange={(e) => { setOpsLimit(Number(e.target.value)); setOpsPage(0); }} style={{ height: 28, border: "1px solid #cbd5e1", borderRadius: 6, fontSize: 12 }}>
              {[15, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <span className="muted">{t("Всего", "Всього")}: <b>{d.count}</b></span>
            {d.count > opsLimit && (
              <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
                <button className="btn btn-light" style={{ height: 26, padding: "0 8px" }} disabled={opsPage <= 0} onClick={() => setOpsPage(opsPage - 1)}>←</button>
                <span>{t("стр.", "стор.")} <b>{opsPage + 1}</b> / {Math.max(1, Math.ceil(d.count / opsLimit))}</span>
                <button className="btn btn-light" style={{ height: 26, padding: "0 8px" }} disabled={(opsPage + 1) * opsLimit >= d.count} onClick={() => setOpsPage(opsPage + 1)}>→</button>
              </span>
            )}
          </div>
          <div style={{ maxHeight: 420, overflowY: "auto", border: "1px solid #f1f5f9", borderRadius: 8 }}>
            <table style={{ width: "100%", fontSize: 12 }}>
              <tbody>
                {(d.ops || []).map((o: any) => (
                  <tr key={o.id} style={{ borderTop: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "4px 8px", whiteSpace: "nowrap", color: "#64748b" }}>{o.date}</td>
                    <td style={{ textAlign: "right", fontWeight: 700, whiteSpace: "nowrap", color: o.direction === "in" ? "#16a34a" : o.direction === "out" ? "#dc2626" : "#6366f1" }}>{o.direction === "in" ? "+" : o.direction === "out" ? "−" : "⇄"}{Math.round(o.amount_uah).toLocaleString("ru")}</td>
                    <td style={{ paddingLeft: 8, color: "#475569", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={o.comment}>{o.category || o.comment || o.counterparty || "—"}</td>
                    <td style={{ padding: "4px 8px", whiteSpace: "nowrap", textAlign: "right" }}>{o.deal ? <a onClick={() => navFB(`/deals/${o.deal}`)} style={{ color: "#1d4ed8", cursor: "pointer", fontWeight: 600, textDecoration: "none" }} title={t("Открыть сделку", "Відкрити угоду") + (o.deal_title ? ": " + o.deal_title : "")}>№{o.deal}{o.deal_title ? " · " + String(o.deal_title).slice(0, 18) : ""}</a> : <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
