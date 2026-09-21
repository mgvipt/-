import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

type Identity = { kind: string; value: string; verified: boolean };
type ContactRow = {
  id: number; name: string; phone: string; email: string; source: string; campaign: string; content: string;
  preferred_channel: string; identities: Identity[]; interests: string[]; instructions: string[];
  consent: boolean; consent_at: string | null; status: string; last_touch_at: string;
};
type Report = {
  total: number; contactable: number; contact_verification: string; channels: Record<string, number>;
  multichannel: number; marketing_consent: number; no_contact: number; no_consent: number;
  unsubscribed: number; invalid: number; new_today: number; new_7d: number; new_30d: number;
  events: Record<string, number>; anonymous_events: Record<string, number>; customers: number; orders: number;
  repeat_customers: number; paid_amount: string | null; attribution_note: string;
  manager_shares: number; manager_opened: number; contacts: ContactRow[];
};

const SOURCE_LABELS: Record<string, string> = {
  website: "Сайт Wallcov", instagram: "Instagram", tiktok: "TikTok", youtube: "YouTube",
  manager: "Менеджер", ads: "Реклама",
};
const CHANNEL_LABELS: Record<string, string> = {
  viber: "Viber", whatsapp: "WhatsApp", telegram: "Telegram", instagram: "Instagram",
  email: "Email", phone: "Телефон",
};

export default function ContentAudience() {
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [source, setSource] = useState("");
  const [campaign, setCampaign] = useState("");
  const [content, setContent] = useState("");
  const [query, setQuery] = useState("instruction=microcement");

  useEffect(() => {
    let active = true;
    setError(""); setData(null);
    api.get<Report>("/api/content-library/audience/?" + query)
      .then((response) => { if (active) setData(response); })
      .catch(() => { if (active) setError("Не вдалося отримати звіт. Перевірте доступ і спробуйте ще раз."); });
    return () => { active = false; };
  }, [query]);

  const apply = () => setQuery(new URLSearchParams({ instruction: "microcement", source, campaign, content }).toString());
  const pct = (n: number, d: number) => d ? `${(100 * n / d).toFixed(1)}%` : "—";
  const channel = (value: string) => CHANNEL_LABELS[value] || value || "Не обрано";

  return <main style={{ padding: 24, maxWidth: 1350, width: "100%", height: "100%", margin: "auto", overflow: "auto", boxSizing: "border-box", minWidth: 0 }}>
    <h1>База контент-лідів</h1>
    <p>Люди, які отримали онлайн-інструкцію Wallcov. Повторні запити об’єднуються за контактом.</p>

    <form onSubmit={(event) => { event.preventDefault(); apply(); }} style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "end", margin: "24px 0" }}>
      <label style={{ display: "grid", gap: 5 }}><span>Звідки прийшов клієнт</span>
        <select value={source} onChange={(event) => setSource(event.target.value)} style={{ minWidth: 180 }}>
          <option value="">Усі джерела</option>
          {Object.entries(SOURCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label style={{ display: "grid", gap: 5 }}><span>Рекламна кампанія</span>
        <input value={campaign} onChange={(event) => setCampaign(event.target.value)} placeholder="Назва кампанії, якщо відома" style={{ minWidth: 260 }} />
      </label>
      <label style={{ display: "grid", gap: 5 }}><span>Публікація або відео</span>
        <input value={content} onChange={(event) => setContent(event.target.value)} placeholder="Назва або ID Reels / допису" style={{ minWidth: 260 }} />
      </label>
      <button className="btn btn-primary">Показати</button>
      {(source || campaign || content) && <button type="button" className="btn btn-light" onClick={() => { setSource(""); setCampaign(""); setContent(""); setQuery("instruction=microcement"); }}>Скинути</button>}
    </form>
    <p className="muted" style={{ marginTop: -14 }}>Два останні поля потрібні лише для пошуку людей з конкретної реклами чи публікації. Їх можна залишити порожніми.</p>

    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>Завантаження…</p>}
    {data && <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 14 }}>
        {Object.entries({
          "Унікальних клієнтів": data.total,
          "Є контакт для зв’язку": data.contactable,
          Viber: data.channels.viber || 0,
          WhatsApp: data.channels.whatsapp || 0,
          Telegram: data.channels.telegram || 0,
          Email: data.channels.email || 0,
          "Дозволили повідомлення": data.marketing_consent,
          "Нові сьогодні": data.new_today,
          "За 7 днів": data.new_7d,
          "За 30 днів": data.new_30d,
          "Без згоди": data.no_consent,
          "Відписалися": data.unsubscribed,
          "Некоректний контакт": data.invalid,
        }).map(([label, number]) => <section className="card" key={label} style={{ padding: 18 }}><small>{label}</small><div style={{ fontSize: 32, fontWeight: 700 }}>{number}</div></section>)}
      </div>
      <p className="muted">{data.contact_verification}. Наявність контакту не є згодою на розсилку.</p>

      <h2>Шлях контакту після запиту інструкції</h2>
      <div style={{ overflowX: "auto", maxWidth: "100%" }}><table className="table" style={{ minWidth: 620 }}><thead><tr><th>Етап</th><th>Унікальних людей</th><th>Від усіх контактів</th></tr></thead><tbody>
        {[["Отримали інструкцію", data.total], ["Відкрили інструкцію", data.events.instruction_open || 0], ["Натиснули розрахунок", data.events.calculation_click || 0], ["Запросили розрахунок", data.events.calculation_request || 0], ["Покупці", data.customers]].map(([label, number]) => <tr key={String(label)}><td>{label}</td><td>{number}</td><td>{pct(Number(number), data.total)}</td></tr>)}
      </tbody></table></div>

      <h2>Замовлення цієї аудиторії</h2>
      <p>Замовлень: <b>{data.orders}</b> · Повторних покупців: <b>{data.repeat_customers}</b>{data.paid_amount !== null && <> · Оплачено: <b>{Number(data.paid_amount).toLocaleString("uk-UA")} грн</b></>}</p>
      <p className="muted">{data.attribution_note}</p>

      <h2>Робота менеджерів</h2>
      <p>Надіслано інструкцій: {data.manager_shares} · Відкрито посилань: {data.manager_opened}. Вставлений, але не надісланий текст не рахується.</p>

      <h2>Стаття та форма</h2>
      <p>Події від відвідувачів без прив’язаного контакту показані окремо.</p>
      <div style={{ overflowX: "auto", maxWidth: "100%" }}><table className="table" style={{ minWidth: 620 }}><thead><tr><th>Подія</th><th>Контактів</th><th>Анонімних подій</th></tr></thead><tbody>
        {(["article_view", "article_scroll_50", "article_scroll_90", "lead_cta_click", "lead_form_start", "lead_form_submit", "product_click"] as const).map((key) => <tr key={key}><td>{{ article_view: "Перегляд статті", article_scroll_50: "Прочитано 50%", article_scroll_90: "Прочитано 90%", lead_cta_click: "Перехід до техкарти", lead_form_start: "Початок форми", lead_form_submit: "Надіслана форма", product_click: "Перехід до товару" }[key]}</td><td>{data.events[key] || 0}</td><td>{data.anonymous_events[key] || 0}</td></tr>)}
      </tbody></table></div>

      <h2>Останні контакти</h2>
      {data.contacts.length === 0 ? <p>Контактів поки немає або немає права перегляду клієнтів.</p> :
        <div style={{ overflowX: "auto", maxWidth: "100%" }}><table className="table" style={{ minWidth: 980 }}><thead><tr><th>Клієнт</th><th>Телефон / email</th><th>Зручний канал</th><th>Що запитував</th><th>Звідки прийшов</th><th>Повідомлення</th></tr></thead><tbody>
          {data.contacts.map((person) => <tr key={person.id}>
            <td><Link to={`/clients/${person.id}`}>{person.name}</Link></td>
            <td>{person.phone || "—"}<br />{person.email || "—"}</td>
            <td><b>{channel(person.preferred_channel)}</b><br /><small>{person.identities.some((identity) => identity.kind === person.preferred_channel && identity.verified) ? "Підтверджено" : "Обрано клієнтом"}</small></td>
            <td>{person.instructions.join(", ") || "—"}</td>
            <td>{SOURCE_LABELS[person.source] || person.source || "—"}{person.campaign && <><br /><small>{person.campaign}</small></>}</td>
            <td>{person.consent ? "Дозволив" : "Не дозволяв"}</td>
          </tr>)}
        </tbody></table></div>}
    </>}
  </main>;
}
