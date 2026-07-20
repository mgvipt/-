/* Картка клієнта (контакту): поля як у Бітриксі + історія сделок.
 * Відкривається зі списку «Клієнти» або зі сделки. /clients/:id */
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams, useLocation } from "react-router-dom";
import { api } from "../api";
import { Avatar, SourceChip, SOURCES } from "../ui";
import OwnerSelect from "../OwnerSelect";
import CallButton from "../CallButton";
import { useLang } from "../i18n";
import TxCardModal from "../TxCardModal";
import { useAuth } from "../auth";
import { SocialLink } from "../social";
import ClientChat from "../ClientChat";

interface Deal { id: number; title: string; amount: number; stage: string; is_won: boolean; created_at: string; }
interface Contact {
  id: number; first_name: string; last_name: string; middle_name?: string; display_name: string; phone: string; email: string; social_link: string; messengers?: string[];
  source: string; address: string; comment: string; loyalty_tag: string; birthday: string | null;
  kinds?: string[]; gender?: string; monitor_docs?: boolean; doc_email?: string;
  channels: string[]; owner?: number | null; owner_name?: string; deals: Deal[]; total_spent: number;
}
const money = (n: number) => Math.round(n || 0).toLocaleString("ru") + " ₴";
const LOYALTY = ["", "Новий", "Активний", "VIP", "Сплячий"];
const KINDS: [string, string][] = [
  ["client", "Клієнт"], ["supplier", "Постачальник"], ["master", "Майстер"],
  ["staff", "Співробітник"], ["partner", "Партнер / Дизайнер"],
];

export default function ClientCard() {
  const { id } = useParams();
  const { t } = useLang();
  const nav = useNavigate();
  const loc = useLocation();
  const [sp] = useSearchParams();
  const backChat = sp.get("c");
  const [c, setC] = useState<Contact | null>(null);
  const { can } = useAuth();
  const [msg, setMsg] = useState("");
  const [ndOpen, setNdOpen] = useState(false);
  const [ndFunnels, setNdFunnels] = useState<any[]>([]);
  const [nd, setNd] = useState<any>({ funnel: 0, title: "", amount: "" });
  const [ndBusy, setNdBusy] = useState(false);
  const [chatOpen, setChatOpen] = useState(Boolean(backChat));
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
  async function delDeal(dealId: number) {
    if (!confirm(t("Удалить сделку безвозвратно? Действие необратимо.","Видалити угоду безповоротно? Дію не відмінити."))) return;
    try { await api.del("/api/deals/" + dealId + "/"); load(); }
    catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось удалить сделку","Не вдалося видалити угоду")); }
  }
  useEffect(() => { load(); }, [id]);
  useEffect(() => { if (backChat) setChatOpen(true); }, [backChat, id]);
  if (!c) return <div className="spin">{t("Загрузка клиента…","Завантаження клієнта…")}</div>;

  async function save(patch: Partial<Contact>) {
    await api.patch(`/api/contacts/${id}/`, patch);
    setC((cur) => (cur ? { ...cur, ...patch } as Contact : cur));  // одразу оновити картку
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
        <button className="back" title={backChat ? t("Вернуться в чат с клиентом","Повернутися в чат з клієнтом") : t("К списку клиентов","До списку клієнтів")} onClick={() => backChat ? nav(`/inbox?c=${backChat}`) : (loc.key !== "default" ? nav(-1) : nav("/clients"))}>←</button>
        <Avatar name={c.display_name} cls="av-md" />
        <b style={{ fontSize: 16 }}>{c.display_name}</b>
        {c.loyalty_tag && <span className="chip" style={{ background: "#eef2ff", color: "#4338ca" }}>{c.loyalty_tag}</span>}
        {(c.kinds || []).map((k) => {
          const lbl = (KINDS.find(([kk]) => kk === k) || ["", k])[1];
          const clr: any = { supplier: ["#fff7ed", "#c2410c"], master: ["#f0fdf4", "#15803d"], staff: ["#f5f3ff", "#6d28d9"], partner: ["#fdf2f8", "#be185d"], client: ["#eff6ff", "#1d4ed8"] };
          const [bg, fg] = clr[k] || ["#f1f5f9", "#475569"];
          return <span key={k} className="chip" style={{ background: bg, color: fg, fontWeight: 700 }}>{lbl}</span>;
        })}
        <CallButton contact={c.id} small />
        <button data-testid="client-chat-toggle" className="btn" style={{ height: 30, fontSize: 12.5, padding: "0 12px", background: chatOpen ? "#dbeafe" : "#eff6ff", color: "#1d4ed8" }}
          onClick={() => setChatOpen((open) => !open)}>💬 {chatOpen ? t("Свернуть чат","Згорнути чат") : t("Открыть чат","Відкрити чат")}</button>
        <button className="btn btn-primary" style={{ height: 30, fontSize: 12.5, padding: "0 12px" }} onClick={openNewDeal}>{ndOpen ? "✕" : "➕ " + t("Создать сделку","Створити угоду")}</button>
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        <span className="muted" title={t("Сумма выигранных сделок — сколько клиент купил у нас. Это НЕ расходы по объекту (те в блоке «Финансы клиента»).","Сума виграних угод — скільки клієнт купив у нас. Це НЕ витрати по обʼєкту (ті у блоці «Фінанси клієнта»).")}>{t("Купил в нашем магазине (сделки)","Купив у нашому магазині (угоди)")}: <b style={{ color: "#16a34a" }}>{money(c.total_spent)}</b></span>
      </div>

      <div className="grid2">
        <div>
          <div className="panel">
            <div className="label" style={{ marginBottom: 8 }}>{t("Данные клиента","Дані клієнта")} <span className="muted" style={{ fontWeight: 400 }}>{t("(кликни поле, чтобы изменить)","(клікни поле, щоб змінити)")}</span></div>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ flex: 1 }}>{fld(t("Фамилия","Прізвище"), "last_name")}</div>
              <div style={{ flex: 1 }}>{fld(t("Имя","Імʼя"), "first_name")}</div>
              <div style={{ flex: 1 }}>{fld(t("Отчество","По батькові"), "middle_name", t("По отчеству точно определяется пол (Олександрович / Олександрівна)","За по батькові точно визначається стать (Олександрович / Олександрівна)"))}</div>
            </div>
            {fld(t("Телефон","Телефон"), "phone", t("Основной контактный номер","Основний контактний номер"))}
            {fld(t("Email","Email"), "email")}
            {fld(t("Ссылка на аккаунт (мессенджер)","Посилання на акаунт (месенджер)"), "social_link", "t.me / instagram.com…")}
            <SocialLink link={c.social_link} />
            {Array.isArray(c.messengers) && c.messengers.filter((m) => m && m !== c.social_link).map((m, i) => <SocialLink key={i} link={m} />)}
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
            {/* ── ТИП КОНТРАГЕНТА (можна кілька) ── */}
            <div style={{ marginBottom: 10 }}>
              <div className="label">{t("Тип контрагента","Тип контрагента")} <span className="muted" style={{ fontWeight: 400 }}>{t("(можно несколько)","(можна кілька)")}</span></div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {KINDS.map(([k, lbl]) => {
                  const on = (c.kinds || []).includes(k);
                  return (
                    <button key={k} onClick={() => {
                      const cur = c.kinds || [];
                      save({ kinds: on ? cur.filter((x) => x !== k) : [...cur, k] });
                    }} style={{ cursor: "pointer", padding: "5px 11px", borderRadius: 999, fontSize: 12.5,
                                border: "1px solid " + (on ? "#4338ca" : "#e2e8f0"), background: on ? "#eef2ff" : "#fff",
                                color: on ? "#4338ca" : "#64748b", fontWeight: on ? 700 : 500 }}>
                      {on ? "✓ " : ""}{lbl}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* ── СТАТЬ ── */}
            <div style={{ marginBottom: 10 }}>
              <div className="label">{t("Пол","Стать")} <span className="muted" style={{ fontWeight: 400 }}>{t("(определён по имени — можно исправить)","(визначено за іменем — можна виправити)")}</span></div>
              <select value={c.gender || ""} onChange={(e) => save({ gender: e.target.value })}
                style={{ width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7 }}>
                <option value="">— {t("не определён","не визначено")} —</option>
                <option value="m">{t("Мужской","Чоловіча")}</option>
                <option value="f">{t("Женский","Жіноча")}</option>
              </select>
            </div>

            {/* ── МОНІТОРИНГ НАКЛАДНИХ — лише для постачальника ── */}
            {(c.kinds || []).includes("supplier") && (
              <div style={{ marginBottom: 10, padding: 10, background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontWeight: 700, fontSize: 13 }}>
                  <input type="checkbox" checked={!!c.monitor_docs} onChange={(e) => save({ monitor_docs: e.target.checked })} />
                  {t("Мониторить накладные этого поставщика","Моніторити накладні цього постачальника")}
                </label>
                <div className="muted" style={{ fontSize: 11.5, margin: "4px 0 8px" }}>
                  {t("Его накладные и счета сами попадут в Финансы → «Вх. накладные», кредиторка создастся автоматически.","Його накладні та рахунки самі потраплять у Фінанси → «Вх. накладні», кредиторка створиться автоматично.")}
                </div>
                {fld(t("Почта для накладных (если другая)","Пошта для накладних (якщо інша)"), "doc_email", t("Если пусто — берём основной Email","Якщо порожньо — беремо основний Email"))}
              </div>
            )}
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
          <FinBlock contactId={c.id} cname={c.display_name} deals={c.deals} />
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
                <thead><tr><th style={{ textAlign: "left", width: 66 }}>№</th><th style={{ textAlign: "left" }}>{t("Сделка","Угода")}</th><th style={{ textAlign: "right" }}>{t("Сумма","Сума")}</th>{can("product.cost.view") && <th style={{ textAlign: "right", color: "#9a3412" }}>{t("Закупка","Закупка")}</th>}<th style={{ textAlign: "center" }}>{t("Стадия","Стадія")}</th>{can("deal.delete") && <th style={{ width: 30 }}></th>}</tr></thead>
                <tbody>
                  {c.deals.map((d) => (
                    <tr key={d.id} onClick={() => nav(`/deals/${d.id}`)} style={{ cursor: "pointer", borderTop: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "6px 0", color: "#64748b", fontSize: 12, whiteSpace: "nowrap" }}>#{d.id}</td><td style={{ padding: "6px 0", color: "#1d4ed8" }}>{d.title}</td>
                      <td style={{ textAlign: "right" }}>{money(d.amount)}</td>
                      {can("product.cost.view") && <td style={{ textAlign: "right", color: "#9a3412" }} title={t("Себестоимость сделки (закупка товаров)","Собівартість сделки (закупка товарів)")}>{Number((d as any).cost) > 0 ? money((d as any).cost) : "—"}</td>}
                      <td style={{ textAlign: "center" }}><span className="chip" style={{ background: d.is_won ? "#dcfce7" : "#f1f5f9", color: d.is_won ? "#166534" : "#475569" }}>{d.stage || "—"}</span></td>
                      {can("deal.delete") && <td style={{ textAlign: "center", width: 30 }} onClick={(e) => { e.stopPropagation(); delDeal(d.id); }}><span title={t("Удалить сделку","Видалити угоду")} style={{ cursor: "pointer", color: "#dc2626", fontSize: 14 }}>🗑</span></td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <ClientDebtsBlock contactId={c.id} />
        </div>
      </div>
      {chatOpen && (
        <>
          <div data-testid="client-chat-backdrop" onClick={() => setChatOpen(false)}
            style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.28)", zIndex: 70 }} />
          <aside data-testid="client-chat-drawer" role="dialog" aria-label={t("Диалог с клиентом","Діалог з клієнтом")}
            style={{ position: "fixed", top: 0, right: 0, bottom: 0, width: "min(500px, calc(100vw - 12px))", background: "#fff", zIndex: 71, boxShadow: "-18px 0 46px rgba(15,23,42,.22)", display: "flex", flexDirection: "column", borderLeft: "1px solid #dbe3ef" }}>
            <div style={{ padding: "12px 14px 10px", borderBottom: "1px solid #e2e8f0", background: "linear-gradient(90deg,#f8fafc,#eef2ff)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 9 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: ".04em" }}>{t("Диалог с клиентом","Діалог з клієнтом")}</div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.display_name}</div>
                </div>
                <button className="btn" data-testid="client-chat-close" onClick={() => setChatOpen(false)}
                  title={t("Свернуть чат","Згорнути чат")} style={{ height: 32, padding: "0 11px", background: "#fff" }}>✕ {t("Свернуть","Згорнути")}</button>
              </div>
              <div id={`client-reply-channel-${c.id}`} data-testid="client-reply-channel-target" />
            </div>
            <div style={{ flex: 1, minHeight: 0, overflow: "hidden", padding: "10px 12px 12px" }}>
              <ClientChat contact={c.id} channelPickerTargetId={`client-reply-channel-${c.id}`} />
            </div>
          </aside>
        </>
      )}
    </div>
  );
}

function ClientDebtsBlock({ contactId }: { contactId: number }) {
  const { t } = useLang();
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    api.get<any>(`/api/contacts/${contactId}/finance/`).then((d) => setRows(d?.debts_list || [])).catch(() => setRows([]));
  }, [contactId]);
  if (!rows.length) return null;
  return (
    <div className="panel" style={{ marginTop: 12 }}>
      <div className="label" style={{ marginBottom: 8 }}>{t("Долги по клиенту (дебиторка / кредиторка)","Борги по клієнту (дебіторка / кредиторка)")}</div>
      {[["receivable", t("Дебиторка — нам должны","Дебіторка — нам винні"), "#0e7490"], ["payable", t("Кредиторка — мы должны","Кредиторка — ми винні"), "#b45309"]].map(([kind, title, cl]: any) => {
        const list = rows.filter((x) => x.kind === kind);
        if (!list.length) return null;
        return (
          <div key={kind} style={{ marginBottom: 8 }}>
            <div className="muted" style={{ fontSize: 11.5, fontWeight: 700, color: cl, marginBottom: 4 }}>{title} · {list.length}</div>
            {list.map((x) => {
              const paid = x.status === "paid";
              return (
                <div key={x.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 9px", borderRadius: 8, background: paid ? "#f0fdf4" : "#fff7ed", border: "1px solid " + (paid ? "#bbf7d0" : "#fed7aa"), marginBottom: 4, fontSize: 12.5 }}>
                  <span>{paid ? "✅" : "🕐"}</span>
                  <span style={{ flex: 1, textDecoration: paid ? "line-through" : "none", color: paid ? "#16a34a" : "#0f172a", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.counterparty || t("Без имени","Без імені")}{x.comment ? " · " + x.comment : ""}{x.deal ? " · №" + x.deal : ""}</span>
                  <b style={{ color: cl, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{Math.round(Number(x.amount)).toLocaleString("ru")} ₴</b>
                  <span style={{ fontSize: 10, fontWeight: 700, color: paid ? "#16a34a" : "#c2410c", whiteSpace: "nowrap" }}>{paid ? t("оплачено","оплачено") : t("не оплачено","не оплачено")}</span>
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}


function FinBlock({ contactId, cname, deals }: { contactId: number; cname?: string; deals?: any[] }) {
  const navFB = useNavigate();
  const { can } = useAuth();
  const canDelTx = can("finance.tx.edit") || can("roles.manage");
  const [selOps, setSelOps] = useState<Record<number, boolean>>({});
  const [txCardId, setTxCardId] = useState<number | null>(null);
  const [createOp, setCreateOp] = useState<null | "in" | "out">(null);
  const [opsLimit, setOpsLimit] = useState(50);
  const [opsPage, setOpsPage] = useState(0);
  const [opsCp, setOpsCp] = useState("");      // фільтр: кому / від кого
  const [opsObj, setOpsObj] = useState("");    // фільтр: клієнт-обʼєкт
  const [opsFrom, setOpsFrom] = useState("");  // період від
  const [opsTo, setOpsTo] = useState("");      // період до
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
  const [faDeal, setFaDeal] = useState(0);        // оплата привʼязана до сделки
  const [faDealInfo, setFaDealInfo] = useState<any>(null); // {amount, paid, remaining}
  const [busy, setBusy] = useState(false);
  const load = () => api.get<any>(`/api/contacts/${contactId}/finance/?limit=${opsLimit}&offset=${opsPage * opsLimit}&op_cp=${encodeURIComponent(opsCp)}&op_obj=${encodeURIComponent(opsObj)}&op_from=${opsFrom}&op_to=${opsTo}`).then(setD).catch(() => {});
  useEffect(() => { const tmr = setTimeout(() => load(), 300); return () => clearTimeout(tmr); }, [contactId, opsLimit, opsPage, opsCp, opsObj, opsFrom, opsTo]); // eslint-disable-line
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
  useEffect(() => {
    if (!faDeal) { setFaDealInfo(null); return; }
    let ok = true;
    api.get<any>(`/api/deals/${faDeal}/`).then((dl: any) => { if (ok) setFaDealInfo({ title: dl.title, amount: Number(dl.amount || 0), paid: Number(dl.paid || 0), remaining: Number(dl.amount || 0) - Number(dl.paid || 0) }); }).catch(() => { if (ok) setFaDealInfo(null); });
    return () => { ok = false; };
  }, [faDeal]);
  async function delOps(ids: number[]) {
    if (!ids.length || busy) return;
    if (!confirm(t(`Удалить ${ids.length} операц.? Это повлияет на остатки и аналитику. Отменить нельзя.`, `Видалити ${ids.length} операц.? Це вплине на залишки й аналітику. Скасувати не можна.`))) return;
    setBusy(true);
    try { for (const id of ids) { try { await api.del(`/api/transactions/${id}/`); } catch { /* пропускаємо збій одного */ } } }
    finally { setSelOps({}); setBusy(false); load(); }
  }
  async function add() {
    if (!Number(fa.amount) || busy) return;
    if (payNow && !fa.account) return;
    if (form === "in" && payNow && faDeal && faDealInfo) {
      const amt = Number(String(fa.amount).replace(",", "."));
      const rem = faDealInfo.remaining;
      if (amt < rem - 0.5 && !confirm(t(`Оплата ${money0(amt)} меньше остатка ${money0(rem)}. Это частичная оплата — останется ${money0(rem - amt)}, остаток внесёшь позже. Провести?`, `Оплата ${money0(amt)} менша за залишок ${money0(rem)}. Це часткова оплата — залишиться ${money0(rem - amt)}, решту внесеш пізніше. Провести?`))) return;
      if (amt > rem + 0.5 && !confirm(t(`Оплата ${money0(amt)} больше остатка ${money0(rem)} на ${money0(amt - rem)} (переплата). Провести?`, `Оплата ${money0(amt)} більша за залишок ${money0(rem)} на ${money0(amt - rem)} (переплата). Провести?`))) return;
    }
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
          set_category: fa.cat, counterparty: fa.cp, comment: fa.comment, contact: contactId, currency: "UAH", rate: 1, deal: (form === "in" && payNow && faDeal) ? faDeal : undefined });
      }
      setForm(null); setFa({ amount: "", account: 0, cat: "", cp: "", comment: "" }); setPayNow(true); setRecvLoan(false); setFaDeal(0); load();
    } finally { setBusy(false); }
  }
  const inpF: React.CSSProperties = { width: "100%", height: 32, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 9px", fontSize: 13, marginBottom: 6 };
  if (!d) return null;
  return (
    <div className="panel" style={{ marginBottom: 12 }}>
      <div className="label" style={{ marginBottom: 8 }}>{t("Финансы клиента","Фінанси клієнта")} <span className="muted" style={{ fontWeight: 400 }}>({d.count} {t("операций","операцій")})</span></div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        {[[t("Доход","Дохід"), d.income, "#16a34a", "#f0fdf4"], [t("Расход (журнал+склад)","Витрата (журнал+склад)"), Number(d.expense || 0) + Number(d.cogs || 0), "#dc2626", "#fef2f2"], (Number(d.advance) < 0 ? [t("Недоплата по сделкам","Недоплата по угодах"), Math.abs(Number(d.advance)), "#dc2626", "#fef2f2"] : [t("Аванс (свободные деньги клиента)","Аванс (вільні гроші клієнта)"), d.advance, "#2563eb", "#eff6ff"]), [t("Кредиторка (мы должны)","Кредиторка (ми винні)"), d.debt, "#b45309", "#fffbeb"], [t("Дебиторка (нам должны)","Дебіторка (нам винні)"), d.receivable, "#0e7490", "#ecfeff"]].map(([l, v, cl, bg]: any, i) => (
          <div key={i} style={{ flex: 1, minWidth: 110, background: bg, borderRadius: 10, padding: "8px 10px" }}>
            <div className="muted" style={{ fontSize: 10.5 }}>{l}</div>
            <b style={{ color: cl, fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{money0(Number(v))}</b>
          </div>
        ))}
      </div>
      {can("product.cost.view") && (Number(d.revenue) > 0 || Number(d.cost_ext) > 0 || Number(d.cogs) > 0) && (
        <div style={{ marginBottom: 10, padding: "10px 12px", borderRadius: 10, background: (Number(d.profit) >= 0 ? "#f0fdf4" : "#fef2f2"), border: "1px solid " + (Number(d.profit) >= 0 ? "#bbf7d0" : "#fecaca") }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
            <div className="muted" style={{ fontSize: 11.5 }}>
              {t("Выручка","Виручка")}: <b style={{ color: "#0f172a" }}>{money0(Number(d.revenue || 0))}</b>
              <span style={{ margin: "0 5px" }}>−</span>{t("Себест. склада","Собівар. складу")}: <b style={{ color: "#b45309" }}>{money0(Number(d.cogs || 0))}</b>
              <span style={{ margin: "0 5px" }}>−</span>{t("Закупки/услуги","Закупки/послуги")}: <b style={{ color: "#dc2626" }}>{money0(Number(d.cost_ext || 0))}</b>
            </div>
            <div style={{ fontSize: 15, fontWeight: 800, color: (Number(d.profit) >= 0 ? "#16a34a" : "#dc2626") }}>
              {t("Прибыль","Прибуток")}: {money0(Number(d.profit || 0))}{Number(d.revenue) > 0 ? <span style={{ fontSize: 12.5, fontWeight: 700, marginLeft: 8, color: "#64748b" }}>· {t("маржа","маржа")} {Math.round(Number(d.profit || 0) / Number(d.revenue) * 100)}%</span> : null}
            </div>
          </div>
          <div className="muted" style={{ fontSize: 10.5, marginTop: 4 }}>{t("Складские товары — из сделок (себестоимость авто при отгрузке), закупки под заказ — из журнала. Без двойного счёта.","Складські товари — зі сделок (собівартість авто при відвантаженні), закупки під замовлення — з журналу. Без подвійного рахунку.")}</div>
          {Number(d.actual_srv || 0) > Number(d.planned_srv || 0) + 1 && (
            <div style={{ marginTop: 8, padding: "7px 10px", borderRadius: 8, background: "#fef2f2", border: "1px solid #fecaca", fontSize: 12, color: "#b91c1c", fontWeight: 600 }}>
              ⚠️ {t("Мастерам выплачено больше плана на","Майстрам виплачено більше плану на")} {money0(Number(d.actual_srv) - Number(d.planned_srv))} ₴
              <span style={{ fontWeight: 400, color: "#7f1d1d" }}> · {t("план по услугам","план по послугах")} {money0(Number(d.planned_srv))}, {t("факт (журнал, без материалов)","факт (журнал, без матеріалів)")} {money0(Number(d.actual_srv))}</span>
            </div>
          )}
        </div>
      )}
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <button className="btn btn-light" style={{ flex: 1, color: "#16a34a", fontWeight: 700 }} onClick={() => setCreateOp("in")} title={t("Полная карточка дохода — как в журнале (клиент подставится)","Повна картка доходу — як у журналі (клієнт підставиться)")}>+ {t("Доход","Дохід")}</button>
        <button className="btn btn-light" style={{ flex: 1, color: "#dc2626", fontWeight: 700 }} onClick={() => setCreateOp("out")} title={t("Полная карточка расхода — как в журнале (клиент подставится)","Повна картка витрати — як у журналі (клієнт підставиться)")}>+ {t("Расход","Витрата")}</button>
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
          {form === "in" && payNow && (deals || []).length > 0 && (
            <>
              <select value={faDeal} onChange={(e) => setFaDeal(Number(e.target.value))} style={{ ...inpF, borderColor: faDeal ? "#16a34a" : "#cbd5e1" }} title={t("Привязать оплату к сделке — попадёт в «Оплачено» сделки","Привʼязати оплату до сделки — потрапить в «Оплачено» сделки")}>
                <option value={0}>{t("— оплата по сделке (необязательно) —","— оплата по сделці (необовʼязково) —")}</option>
                {(deals || []).map((dl: any) => <option key={dl.id} value={dl.id}>№{dl.id} · {String(dl.title).slice(0, 30)}</option>)}
              </select>
              {!!faDeal && faDealInfo && (
                <div style={{ fontSize: 12, margin: "-2px 0 8px", padding: "6px 9px", borderRadius: 7, background: "#f0fdf4", color: "#166534" }}>
                  {t("Сумма сделки","Сума сделки")}: <b>{money0(faDealInfo.amount)}</b> · {t("оплачено","оплачено")}: <b>{money0(faDealInfo.paid)}</b> · {t("остаток","залишок")}: <b style={{ color: faDealInfo.remaining > 0 ? "#b45309" : "#166534" }}>{money0(faDealInfo.remaining)}</b>
                  {Number(fa.amount) > 0 && Math.abs(Number(fa.amount) - faDealInfo.remaining) > 0.5 && (
                    <div style={{ marginTop: 4, fontWeight: 700, color: Number(fa.amount) < faDealInfo.remaining ? "#b45309" : "#dc2626" }}>
                      {Number(fa.amount) < faDealInfo.remaining
                        ? "⚠️ " + t("Меньше остатка — частичная. Останется ","Менше залишку — часткова. Залишиться ") + money0(faDealInfo.remaining - Number(fa.amount))
                        : "⚠️ " + t("Больше остатка на ","Більше залишку на ") + money0(Number(fa.amount) - faDealInfo.remaining) + " " + t("(переплата)","(переплата)")}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
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
      {(d.count > 0 || opsCp || opsObj || opsFrom || opsTo) && (
        <div style={{ marginTop: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6, fontSize: 12 }}>
            <span className="muted">{t("Показывать:", "Показувати:")}</span>
            <select value={opsLimit} onChange={(e) => { setOpsLimit(Number(e.target.value)); setOpsPage(0); }} style={{ height: 28, border: "1px solid #cbd5e1", borderRadius: 6, fontSize: 12 }}>
              {[15, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <input value={opsCp} onChange={(e) => { setOpsCp(e.target.value); setOpsPage(0); }} placeholder={t("🔎 Кому/от кого", "🔎 Кому/від кого")} style={{ height: 28, border: "1px solid #cbd5e1", borderRadius: 6, fontSize: 12, padding: "0 8px", width: 140 }} />
            <input value={opsObj} onChange={(e) => { setOpsObj(e.target.value); setOpsPage(0); }} placeholder={t("🔎 Клиент (объект)", "🔎 Клієнт (обʼєкт)")} style={{ height: 28, border: "1px solid #cbd5e1", borderRadius: 6, fontSize: 12, padding: "0 8px", width: 150 }} />
            <span className="muted" style={{ fontSize: 11 }}>{t("Период:", "Період:")}</span>
            <input type="date" value={opsFrom} onChange={(e) => { setOpsFrom(e.target.value); setOpsPage(0); }} title={t("Дата от", "Дата від")} style={{ height: 28, border: "1px solid #cbd5e1", borderRadius: 6, fontSize: 12, padding: "0 6px" }} />
            <span className="muted" style={{ fontSize: 11 }}>—</span>
            <input type="date" value={opsTo} onChange={(e) => { setOpsTo(e.target.value); setOpsPage(0); }} title={t("Дата до", "Дата до")} style={{ height: 28, border: "1px solid #cbd5e1", borderRadius: 6, fontSize: 12, padding: "0 6px" }} />
            {(opsCp || opsObj || opsFrom || opsTo) && <button className="btn btn-light" style={{ height: 28, padding: "0 8px", fontSize: 12 }} title={t("Сбросить фильтры", "Скинути фільтри")} onClick={() => { setOpsCp(""); setOpsObj(""); setOpsFrom(""); setOpsTo(""); setOpsPage(0); }}>✕ {t("Сброс", "Скинути")}</button>}
            <span className="muted">{t("Всего", "Всього")}: <b>{d.count}</b></span>
            {canDelTx && Object.values(selOps).filter(Boolean).length > 0 && (
              <button className="btn" style={{ height: 26, padding: "0 10px", background: "#fee2e2", color: "#b91c1c", fontWeight: 700, fontSize: 12 }} disabled={busy}
                onClick={() => delOps(Object.keys(selOps).filter((k) => selOps[Number(k)]).map(Number))}>🗑 {t("Удалить выбранные", "Видалити обрані")} ({Object.values(selOps).filter(Boolean).length})</button>
            )}
            {d.count > opsLimit && (
              <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
                <button className="btn btn-light" style={{ height: 26, padding: "0 8px" }} disabled={opsPage <= 0} onClick={() => setOpsPage(opsPage - 1)}>←</button>
                <span>{t("стр.", "стор.")} <b>{opsPage + 1}</b> / {Math.max(1, Math.ceil(d.count / opsLimit))}</span>
                <button className="btn btn-light" style={{ height: 26, padding: "0 8px" }} disabled={(opsPage + 1) * opsLimit >= d.count} onClick={() => setOpsPage(opsPage + 1)}>→</button>
              </span>
            )}
          </div>
          <div style={{ maxHeight: 420, overflowY: "auto", overflowX: "auto", border: "1px solid #f1f5f9", borderRadius: 8 }}>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ position: "sticky", top: 0, zIndex: 1, background: "#f8fafc", boxShadow: "0 1px 0 #e2e8f0" }}>
                  {canDelTx && <th style={{ width: 30, padding: "7px 4px", textAlign: "center" }}>
                    <input type="checkbox" title={t("Выбрать все на странице", "Вибрати всі на сторінці")} style={{ accentColor: "#C67D5F" }}
                      checked={(d.ops || []).length > 0 && (d.ops || []).every((o: any) => selOps[o.id])}
                      onChange={(e) => { const n: any = { ...selOps }; (d.ops || []).forEach((o: any) => { n[o.id] = e.target.checked; }); setSelOps(n); }} /></th>}
                  <th style={{ padding: "7px 8px", textAlign: "left", fontSize: 10.5, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em" }}>{t("Дата", "Дата")}</th>
                  <th style={{ padding: "7px 8px", textAlign: "right", fontSize: 10.5, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em" }}>{t("Сумма", "Сума")}</th>
                  <th style={{ padding: "7px 8px", textAlign: "left", fontSize: 10.5, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em" }}>{t("Категория / описание", "Категорія / опис")}</th>
                  <th style={{ padding: "7px 8px", textAlign: "left", fontSize: 10.5, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em" }} title={t("Кому оплачено (расход) / кто оплатил (доход)", "Кому сплачено (витрата) / хто сплатив (дохід)")}>{t("Кому / от кого", "Кому / від кого")}</th>
                  <th style={{ padding: "7px 8px", textAlign: "left", fontSize: 10.5, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em" }} title={t("Клиент-объект, к которому относится платёж (может отличаться от этой карточки)", "Клієнт-обʼєкт, якого стосується платіж (може відрізнятися від цієї картки)")}>{t("Клиент (объект)", "Клієнт (обʼєкт)")}</th>
                  <th style={{ padding: "7px 8px", textAlign: "right", fontSize: 10.5, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em" }}>{t("Сделка", "Угода")}</th>
                  {canDelTx && <th style={{ width: 34, padding: "7px 4px" }}></th>}
                </tr>
              </thead>
              <tbody>
                {(d.ops || []).map((o: any) => (
                  <tr key={o.id} onClick={() => setTxCardId(o.id)} title={t("Открыть карточку операции", "Відкрити картку операції")} style={{ borderTop: "1px solid #f1f5f9", cursor: "pointer", background: selOps[o.id] ? "#fdf3ec" : undefined }}>
                    {canDelTx && <td onClick={(e) => e.stopPropagation()} style={{ textAlign: "center", padding: "4px" }}>
                      <input type="checkbox" checked={!!selOps[o.id]} onChange={(e) => setSelOps({ ...selOps, [o.id]: e.target.checked })} style={{ accentColor: "#C67D5F" }} /></td>}
                    <td style={{ padding: "4px 8px", whiteSpace: "nowrap", color: "#64748b" }}>{o.date}</td>
                    <td style={{ textAlign: "right", fontWeight: 700, whiteSpace: "nowrap", color: o.direction === "in" ? "#16a34a" : o.direction === "out" ? "#dc2626" : "#6366f1" }}>{o.direction === "in" ? "+" : o.direction === "out" ? "−" : "⇄"}{Math.round(o.amount_uah).toLocaleString("ru")}</td>
                    <td style={{ paddingLeft: 8, color: "#475569", maxWidth: 170, overflow: "hidden" }} title={(o.category || o.comment || "") + (o.fin_direction ? " · напрям: " + o.fin_direction : "")}>
                      <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{o.category || o.comment || "—"}</div>
                      {o.fin_direction ? <div style={{ fontSize: 10, color: "#0e7490", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={t("Направление","Напрямок")}>↳ {o.fin_direction}</div> : null}
                    </td>
                    <td style={{ padding: "4px 8px", color: "#0f172a", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 500 }} title={o.counterparty}>{o.counterparty || <span className="muted">—</span>}</td>
                    <td style={{ padding: "4px 8px", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={o.contact_name}>{o.contact ? <a onClick={(e) => { e.stopPropagation(); navFB(`/clients/${o.contact}`); }} style={{ color: "#0e7490", cursor: "pointer", fontWeight: 600, textDecoration: "none" }} title={t("Открыть карточку клиента-объекта", "Відкрити картку клієнта-обʼєкта")}>{o.contact_name}</a> : <span className="muted">—</span>}</td>
                    <td style={{ padding: "4px 8px", whiteSpace: "nowrap", textAlign: "right" }}>{o.deal ? <a onClick={(e) => { e.stopPropagation(); navFB(`/deals/${o.deal}`); }} style={{ color: "#1d4ed8", cursor: "pointer", fontWeight: 600, textDecoration: "none" }} title={t("Открыть сделку", "Відкрити угоду") + (o.deal_title ? ": " + o.deal_title : "")}>№{o.deal}{o.deal_title ? " · " + String(o.deal_title).slice(0, 18) : ""}</a> : <span className="muted">—</span>}</td>
                    {canDelTx && <td onClick={(e) => e.stopPropagation()} style={{ textAlign: "center", padding: "4px" }}>
                      <span onClick={() => delOps([o.id])} title={t("Удалить операцию", "Видалити операцію")} style={{ cursor: "pointer", color: "#cbd5e1", fontSize: 13 }}>🗑</span></td>}
                  </tr>
                ))}
                {(d.ops || []).length === 0 && <tr><td colSpan={canDelTx ? 8 : 6} style={{ padding: 14, textAlign: "center", color: "#94a3b8" }}>{t("Ничего не найдено по фильтру", "Нічого не знайдено за фільтром")}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {txCardId && <TxCardModal txId={txCardId} nav={navFB} onClose={() => setTxCardId(null)} onSaved={() => { setTxCardId(null); load(); }} />}
      {createOp && <TxCardModal initDirection={createOp} initContact={contactId} initContactName={cname} nav={navFB} onClose={() => setCreateOp(null)} onSaved={() => { setCreateOp(null); load(); }} />}
    </div>
  );
}
