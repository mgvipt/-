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
        <div className="spacer" />
        {msg && <span style={{ color: "#16a34a", fontSize: 13, marginRight: 10 }}>{msg}</span>}
        <span className="muted">{t("Потратил всего","Витратив усього")}: <b style={{ color: "#16a34a" }}>{money(c.total_spent)}</b></span>
      </div>

      <div className="grid2">
        <div>
          <div className="panel">
            <div className="label" style={{ marginBottom: 8 }}>{t("Данные клиента","Дані клієнта")} <span className="muted" style={{ fontWeight: 400 }}>{t("(кликни поле, чтобы изменить)","(клікни поле, щоб змінити)")}</span></div>
            <div style={{ display: "flex", gap: 8 }}>
              <div style={{ flex: 1 }}>{fld(t("Имя","Ім'я"), "first_name")}</div>
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
          <div className="panel">
            <div className="label">{t("Сделки клиента","Угоди клієнта")} ({c.deals.length})</div>
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
