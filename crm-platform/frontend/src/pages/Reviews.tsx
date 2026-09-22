/* Розділ «Відгуки» (12.09.2026): модерація відгуків покупців з сайту + журнал просьб «кому б відправили».
 * Автоматична відправка просьб ВИМКНЕНА (вмикає розробник). Дані: /api/reviews/*.
 * 13.09.2026: тексти затверджені Олегом; вкладка «Тексти і запуск» — тексти, історія змін, тестові контакти, дата старту.
 * Усі компоненти — на рівні модуля (не всередині інших), щоб поля вводу не втрачали фокус. */
import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

type Photo = { id: number; url: string; thumb_url: string; is_public: boolean };
type Product = { crm_product_id: number; name: string; shop_slug: string | null; is_primary: boolean };
type Review = {
  id: number; status: string; status_display: string; rating: number; text: string; text_original: string;
  edited: boolean; public_name: string; city: string; room: string; applied_by: string; kind: string;
  is_test: boolean; products: Product[]; photos: Photo[]; consent_site: boolean; consent_social: boolean;
  reply_text: string; replied_at: string | null; featured: boolean; hidden_reason: string;
  deal_id: number | null; deal_title: string; contact_id: number | null; contact_name: string;
  conversation_id: number | null; task_id: number | null; created_at: string; published_at: string | null;
};
type ReviewList = { results: Review[]; count: number; counts: Record<string, number>; can_moderate: boolean };
type ReqRow = {
  id: number; status: string; status_display: string; kind_display: string; deal_id: number | null;
  deal_title: string; contact_id: number | null; contact_name: string; received_at: string | null;
  due_at: string | null; channel_label: string; reason: string; is_test: boolean; link: string;
};
type ReqList = {
  results: ReqRow[]; count: number; counts: Record<string, number>; send_enabled: boolean; live: boolean;
  can_moderate: boolean; texts_approved?: boolean; test_mode?: boolean;
};
type Rules = {
  send_enabled: boolean; texts_approved: boolean; live: boolean; start_date: string | null;
  delay_main_days: number; delay_test_days: number; remind_after_days: number; repeat_block_days: number;
  expire_days: number; window_wait_days: number; manager_quiet_hours: number; send_from: string; send_to: string;
  google_review_url: string; link_example: string; test_mode?: boolean;
};
type TextVersion = {
  id: number; field: string; field_display: string; text: string; approved: boolean; note: string;
  changed_by: string; created_at: string;
};
type TextsDraft = { text_main: string; text_test: string; text_remind: string };
type Launch = TextsDraft & {
  send_enabled: boolean; texts_approved: boolean; texts_ready: boolean; live: boolean; test_mode: boolean;
  start_date: string | null; texts_approved_at: string | null; texts_approved_note: string;
  allowlist_contact_ids: number[]; allowlist_contacts: { id: number; name: string }[]; text_versions: TextVersion[];
};

const TABS: [string, string][] = [
  ["pending", "На перевірці"], ["published", "Опубліковані"], ["hidden", "Приховані"],
  ["journal", "Журнал просьб"], ["texts", "Тексти і запуск"], ["rules", "Як це працює"],
];
const ROOMS: Record<string, string> = {
  living: "вітальня", bedroom: "спальня", kitchen: "кухня", bathroom: "ванна", hallway: "коридор",
  kids: "дитяча", commercial: "комерційне приміщення", other: "інше",
};
const APPLIED: Record<string, string> = { self: "наносив(ла) сам(а)", master: "наносив майстер" };
const REQ_FILTERS: [string, string][] = [
  ["all", "Усі"], ["would_send", "Відправили б"], ["waiting", "Чекаємо"], ["scheduled", "Заплановано"],
  ["skipped", "Пропущено"], ["cancelled", "Скасовано"], ["submitted", "Відгук отримано"], ["test", "Тестові"],
];
const REQ_COLOR: Record<string, string> = {
  would_send: "#2563eb", waiting: "#d97706", scheduled: "#64748b", skipped: "#94a3b8", cancelled: "#94a3b8",
  opted_out: "#dc2626", sent: "#16a34a", reminded: "#16a34a", submitted: "#059669", expired: "#94a3b8", test: "#7c3aed",
};
const TEXT_FIELDS: [keyof TextsDraft, string, string][] = [
  ["text_main", "Основне замовлення (В1)", "через 10 днів після «Отримано»"],
  ["text_test", "Тест-набір (Т1)", "через 5 днів після «Отримано»"],
  ["text_remind", "Нагадування", "одне, через 5 днів, якщо відгуку ще немає"],
];
const SAMPLE: [string, string][] = [
  ["{імʼя}", "Олена"], ["{ім'я}", "Олена"], ["{менеджер}", "Кирилл"], ["{матеріал}", "Galateya Silver"],
  ["{посилання}", "https://wallcov.com.ua/vidguk/Ab3xK9mPq2Rt"],
];
const TEXTAREA: CSSProperties = {
  width: "100%", boxSizing: "border-box", padding: 8, borderRadius: 8, border: "1px solid #cbd5e1",
  fontFamily: "inherit", fontSize: 14, marginTop: 4,
};
const PREVIEW: CSSProperties = {
  whiteSpace: "pre-wrap", fontSize: 13.5, background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10,
  padding: "8px 10px",
};
const TH: CSSProperties = { padding: "8px 10px", fontWeight: 600, color: "#475569", whiteSpace: "nowrap" };
const TD: CSSProperties = { padding: "8px 10px", verticalAlign: "top" };

function fmt(d: string | null): string {
  if (!d) return "—";
  const x = new Date(d);
  return x.toLocaleDateString("uk-UA", { day: "2-digit", month: "2-digit", year: "2-digit" }) + " " +
    x.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
}

function errText(e: unknown): string {
  const data = (e as { data?: { detail?: string } } | null)?.data;
  return data?.detail || "Не вдалося виконати дію";
}

function sample(text: string): string {
  return SAMPLE.reduce((acc, [key, value]) => acc.split(key).join(value), text);
}

function Stars({ n }: { n: number }) {
  return (
    <span style={{ fontSize: 20, letterSpacing: 1, color: n <= 3 ? "#dc2626" : "#f59e0b" }}>
      {"★".repeat(n)}<span style={{ color: "#e2e8f0" }}>{"★".repeat(Math.max(0, 5 - n))}</span>
    </span>
  );
}

function Badge({ text, color }: { text: string; color: string }) {
  return <span className="chip" style={{ background: color }}>{text}</span>;
}

function ReviewCard({ r, canModerate, onChanged }: { r: Review; canModerate: boolean; onChanged: () => void }) {
  const [reply, setReply] = useState(r.reply_text);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const act = async (body: Record<string, unknown>) => {
    setBusy(true);
    setErr("");
    try {
      await api.post(`/api/reviews/${r.id}/moderate/`, body);
      onChanged();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const hide = () => {
    const reason = window.prompt("Чому приховуємо? (мат, реклама, чужі персональні дані, не про нас)", "");
    if (reason !== null) act({ action: "hide", reason });
  };
  const low = r.rating <= 3;
  return (
    <div className="panel" style={{ borderLeft: `5px solid ${low ? "#ef4444" : "#10b981"}` }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <Stars n={r.rating} />
        <b style={{ fontSize: 15 }}>{r.public_name}{r.city ? `, ${r.city}` : ""}</b>
        {r.is_test && <Badge text="ТЕСТ" color="#7c3aed" />}
        {r.kind === "test" && <Badge text="тест-набір" color="#0ea5e9" />}
        {r.featured && <Badge text="на головній" color="#f59e0b" />}
        {!r.consent_site && <Badge text="без згоди на публікацію" color="#dc2626" />}
        <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>{fmt(r.created_at)}</span>
      </div>
      <div style={{ margin: "10px 0", fontSize: 15, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
        {r.text || <span className="muted">Без тексту — на сайті не публікується, лише у статистиці.</span>}
      </div>
      {r.edited && <div className="muted" style={{ fontSize: 12 }}>Оригінал клієнта: «{r.text_original}»</div>}
      <div style={{ fontSize: 13, color: "#475569", display: "flex", gap: 12, flexWrap: "wrap" }}>
        {r.products.map((p) => <span key={p.crm_product_id}>{p.is_primary ? "🎨 " : ""}{p.name}</span>)}
        {r.room && <span>🏠 {ROOMS[r.room] || r.room}</span>}
        {APPLIED[r.applied_by] && <span>🖌 {APPLIED[r.applied_by]}</span>}
        {r.consent_social && <span>✅ можна показати в соцмережах</span>}
      </div>
      {r.photos.length > 0 && (
        <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
          {r.photos.map((p) => (
            <div key={p.id} style={{ textAlign: "center" }}>
              <a href={p.url} target="_blank" rel="noreferrer">
                <img src={p.thumb_url} alt="Фото покупця" loading="lazy"
                  style={{ width: 120, height: 90, objectFit: "cover", borderRadius: 8, border: "1px solid #e2e8f0",
                    opacity: p.is_public ? 1 : 0.35 }} />
              </a>
              {canModerate && (
                <div>
                  <button className="btn btn-light" style={{ fontSize: 11, marginTop: 4 }} disabled={busy}
                    onClick={() => act({ action: p.is_public ? "hide_photo" : "show_photo", photo_id: p.id })}>
                    {p.is_public ? "Сховати фото" : "Показати фото"}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div style={{ fontSize: 13, marginTop: 10, display: "flex", gap: 12, flexWrap: "wrap" }}>
        {r.deal_id && <Link to={`/deals/${r.deal_id}`}>Угода #{r.deal_id}</Link>}
        {r.contact_id && <Link to={`/clients/${r.contact_id}`}>{r.contact_name || "Клієнт"}</Link>}
        {r.task_id && <Link to="/tasks">🔴 Задача менеджеру #{r.task_id}</Link>}
        {r.status === "hidden" && r.hidden_reason && <span className="muted">Приховано: {r.hidden_reason}</span>}
      </div>
      {canModerate && (
        <div style={{ marginTop: 12, borderTop: "1px solid #eef2f7", paddingTop: 10 }}>
          <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={2}
            placeholder="Відповідь від Wallcov (буде видно на сайті під відгуком)"
            style={{ width: "100%", boxSizing: "border-box", padding: 8, borderRadius: 8, border: "1px solid #cbd5e1",
              fontFamily: "inherit", fontSize: 14 }} />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            {r.status !== "published" && (
              <button className="btn btn-green" disabled={busy} onClick={() => act({ action: "publish" })}>✓ Опублікувати</button>
            )}
            {r.status !== "hidden" && <button className="btn btn-light" disabled={busy} onClick={hide}>Приховати</button>}
            <button className="btn btn-primary" disabled={busy || reply === r.reply_text}
              onClick={() => act({ action: "reply", reply_text: reply })}>
              {r.reply_text ? "Зберегти відповідь" : "Відповісти"}
            </button>
            <button className="btn btn-light" disabled={busy} onClick={() => act({ action: r.featured ? "unfeature" : "feature" })}>
              {r.featured ? "Зняти з головної" : "На головну сайту"}
            </button>
          </div>
          {err && <div style={{ color: "#dc2626", fontSize: 13, marginTop: 6 }}>{err}</div>}
        </div>
      )}
    </div>
  );
}

function Journal() {
  const [filter, setFilter] = useState("all");
  const [data, setData] = useState<ReqList | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const load = useCallback(() => {
    api.get<ReqList>(`/api/reviews/requests/?status=${filter}&page_size=200`).then(setData).catch((e) => setNote(errText(e)));
  }, [filter]);
  useEffect(() => { load(); }, [load]);
  const refresh = async () => {
    setBusy(true);
    setNote("");
    try {
      const res = await api.post<{ stats: Record<string, number> }>("/api/reviews/requests/refresh/");
      const parts = Object.entries(res.stats).filter(([k]) => k !== "live").map(([k, v]) => `${k}: ${v}`);
      setNote("Журнал оновлено" + (parts.length ? " — " + parts.join(", ") : ""));
      load();
    } catch (e) {
      setNote(errText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <div className="panel" style={{ background: "linear-gradient(135deg,#fffbeb,#fef3c7)", border: "1px solid #fcd34d" }}>
        <b style={{ fontSize: 15 }}>
          {data?.live ? (data?.test_mode ? "🧪 Відправка увімкнена лише для тестових контактів" : "✅ Відправка увімкнена")
            : "🔒 Автоматична відправка просьб вимкнена"}
        </b>
        <div style={{ fontSize: 13, marginTop: 4 }}>
          {data?.texts_approved ? "Тексти затверджені (вкладка «Тексти і запуск»). " : "Тексти ще не затверджені. "}
          {data?.live ? "Просьби йдуть за правилами нижче." : <>CRM сама нікому не пише — тут лише список, кому і яким
            каналом вона <b>відправила б</b> просьбу про відгук, і чому когось пропускає.</>}
        </div>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10, alignItems: "center" }}>
        {REQ_FILTERS.map(([k, label]) => (
          <button key={k} className={"btn " + (filter === k ? "btn-primary" : "btn-light")} onClick={() => setFilter(k)}>
            {label}{k !== "all" && data?.counts[k] ? ` · ${data.counts[k]}` : ""}
          </button>
        ))}
        <span className="spacer" />
        {data?.can_moderate && (
          <button className="btn btn-light" disabled={busy} onClick={refresh}>{busy ? "Оновлюю…" : "↻ Оновити журнал"}</button>
        )}
      </div>
      {note && <div className="muted" style={{ marginBottom: 8 }}>{note}</div>}
      <div className="panel" style={{ padding: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f8fafc", textAlign: "left" }}>
              <th style={TH}>Коли просити</th><th style={TH}>Клієнт / угода</th><th style={TH}>Що купив</th>
              <th style={TH}>Статус</th><th style={TH}>Канал і пояснення</th>
            </tr>
          </thead>
          <tbody>
            {(data?.results || []).map((row) => (
              <tr key={row.id} style={{ borderTop: "1px solid #eef2f7" }}>
                <td style={TD}>
                  {fmt(row.due_at)}
                  <div className="muted" style={{ fontSize: 11 }}>отримано {fmt(row.received_at)}</div>
                </td>
                <td style={TD}>
                  {row.contact_id ? <Link to={`/clients/${row.contact_id}`}>{row.contact_name || "Клієнт"}</Link> : "—"}
                  {row.deal_id && <div><Link to={`/deals/${row.deal_id}`}>угода #{row.deal_id}</Link></div>}
                </td>
                <td style={TD}>{row.kind_display}</td>
                <td style={TD}><Badge text={row.status_display} color={REQ_COLOR[row.status] || "#64748b"} /></td>
                <td style={TD}>
                  {row.channel_label && <div><b>{row.channel_label}</b></div>}
                  <div className="muted">{row.reason}</div>
                  {row.link && <div><a href={row.link} target="_blank" rel="noreferrer">{row.link}</a></div>}
                </td>
              </tr>
            ))}
            {data && data.results.length === 0 && (
              <tr><td style={TD} colSpan={5}><span className="muted">Поки порожньо. Натисніть «Оновити журнал».</span></td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RulesPanel() {
  const [s, setS] = useState<Rules | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.get<Rules>("/api/reviews/settings/").then(setS).catch((e) => setErr(errText(e))); }, []);
  if (err) return <div className="panel" style={{ color: "#dc2626" }}>{err}</div>;
  if (!s) return <div className="muted">Завантаження…</div>;
  return (
    <div className="panel" style={{ fontSize: 14, lineHeight: 1.6 }}>
      <h3 style={{ marginTop: 0 }}>Як працюють відгуки</h3>
      <ol style={{ paddingLeft: 20 }}>
        <li>Старт — статус Нової Пошти <b>«Отримано»</b> (беремо посилки, отримані з {s.start_date || "—"}).</li>
        <li>Основне замовлення — просьба через <b>{s.delay_main_days} днів</b>; тест-набір — через <b>{s.delay_test_days} днів</b> і
          лише коли менеджер зараз не веде продаж (не писав клієнту {s.manager_quiet_hours} год і немає відкритої угоди).</li>
        <li>Канал: месенджер, де вже є діалог (WhatsApp / Viber / Telegram через e-chat). Instagram, Facebook, TikTok — лише
          протягом 24 годин після останнього повідомлення клієнта. Інакше пишемо першими за номером телефону
          (WhatsApp → Viber → Telegram).</li>
        <li>Одне нагадування через {s.remind_after_days} днів. Не більше 1 просьби на клієнта за {s.repeat_block_days} днів.
          Відповідь «стоп» — більше ніколи не просимо.</li>
        <li>Розсилка лише з {s.send_from} до {s.send_to} за Києвом. Посилання діє {s.expire_days} днів, вигляд:{" "}
          <code>{s.link_example}</code>.</li>
        <li>Відгук з сайту потрапляє сюди «На перевірку». Публікуємо чесні відгуки без спаму й образ; 1–3★ — одразу задача
          менеджеру. Бонусів за відгук немає.</li>
        <li>Кнопка <b>«⭐ Попросити відгук»</b> у чаті й картці угоди: менеджер бачить точний текст і куди він піде,
          надсилає лише після «Надіслати». Відповідь клієнта («дякую») на просьбу не запускає ШІ-агента і не рухає угоду.</li>
        <li>Після відгуку клієнт бачить посилання на Google:{" "}
          <a href={s.google_review_url} target="_blank" rel="noreferrer">{s.google_review_url}</a>.</li>
      </ol>
      <div style={{ marginTop: 8, padding: 12, borderRadius: 10, background: s.live ? "#ecfdf5" : "#fff7ed",
        border: `1px solid ${s.live ? "#6ee7b7" : "#fdba74"}` }}>
        {s.live
          ? (s.test_mode ? "🧪 Відправка увімкнена лише для тестових контактів." : "✅ Відправка увімкнена.")
          : (s.texts_approved
            ? "🔒 Тексти затверджені, але автоматична відправка вимкнена. Увімкнути може лише розробник після перевірки на вашому контакті (вкладка «Тексти і запуск»)."
            : "🔒 Відправка вимкнена: тексти просьб ще не затверджені.")}
      </div>
    </div>
  );
}

function TextsPanel() {
  const { me } = useAuth();
  const owner = !!me?.is_superuser;
  const [s, setS] = useState<Launch | null>(null);
  const [draft, setDraft] = useState<TextsDraft>({ text_main: "", text_test: "", text_remind: "" });
  const [start, setStart] = useState("");
  const [addId, setAddId] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const apply = (d: Launch) => {
    setS(d);
    setDraft({ text_main: d.text_main, text_test: d.text_test, text_remind: d.text_remind });
    setStart(d.start_date || "");
  };
  useEffect(() => { api.get<Launch>("/api/reviews/settings/").then(apply).catch((e) => setErr(errText(e))); }, []);
  const save = async (body: Record<string, unknown>, okText: string) => {
    setBusy(true);
    setErr("");
    setNote("");
    try {
      apply(await api.patch<Launch>("/api/reviews/settings/", body));
      setNote(okText);
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };
  if (!s) return err ? <div className="panel" style={{ color: "#dc2626" }}>{err}</div> : <div className="muted">Завантаження…</div>;
  const changed: Record<string, string> = {};
  TEXT_FIELDS.forEach(([k]) => { if (draft[k] !== s[k]) changed[k] = draft[k]; });
  const dirty = Object.keys(changed).length > 0;
  const addContact = () => {
    const id = Number(addId);
    if (!Number.isInteger(id) || id <= 0) { setErr("ID клієнта — число з адреси картки клієнта"); return; }
    save({ allowlist_contact_ids: [...s.allowlist_contact_ids, id] }, "Тестовий контакт додано");
    setAddId("");
  };
  const removeContact = (id: number) =>
    save({ allowlist_contact_ids: s.allowlist_contact_ids.filter((x) => x !== id) }, "Контакт прибрано зі списку");
  return (
    <div>
      {note && <div className="panel" style={{ color: "#16a34a", padding: "8px 12px" }}>✓ {note}</div>}
      {err && <div className="panel" style={{ color: "#dc2626", padding: "8px 12px" }}>{err}</div>}
      <div className="panel" style={{ fontSize: 14, lineHeight: 1.7 }}>
        <h3 style={{ marginTop: 0 }}>Запуск</h3>
        <div>{s.texts_approved ? "✅" : "⚠️"} <b>Тексти:</b> {s.texts_approved ? "затверджені" : "не затверджені"}
          {s.texts_approved_note ? ` — ${s.texts_approved_note}` : ""}</div>
        <div>{s.send_enabled ? "✅" : "🔒"} <b>Автоматична відправка:</b>{" "}
          {s.send_enabled ? "увімкнена" : "вимкнена — вмикає розробник лише після перевірки на вашому контакті"}</div>
        <div>🧪 <b>Тестовий режим:</b>{" "}
          {s.test_mode ? "так — просьби (автоматичні й кнопка «⭐ Попросити відгук») отримують лише тестові контакти нижче"
            : "ні — усі клієнти за правилами"}</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
          <b>Дата старту:</b>
          <input type="date" value={start} disabled={!owner || busy} onChange={(e) => setStart(e.target.value)} style={{ height: 30 }} />
          {owner && start !== (s.start_date || "") && (
            <button className="btn btn-primary" disabled={busy || !start} onClick={() => save({ start_date: start }, "Дату старту збережено")}>Зберегти дату</button>
          )}
          <span className="muted" style={{ fontSize: 12 }}>просимо лише за посилками, отриманими в цей день і пізніше — старі клієнти з журналу повідомлень не отримають</span>
        </div>
        <div style={{ marginTop: 10 }}>
          <b>Тестові контакти</b> <span className="muted" style={{ fontSize: 12 }}>(поки йде перевірка, просьбу отримують лише вони)</span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "6px 0" }}>
            {s.allowlist_contacts.map((c) => (
              <span key={c.id} className="chip" style={{ background: "#7c3aed" }}>
                <Link to={`/clients/${c.id}`} style={{ color: "#fff" }}>{c.name || "Клієнт"} · #{c.id}</Link>
                {owner && (
                  <button onClick={() => removeContact(c.id)} disabled={busy} title="Прибрати зі списку"
                    style={{ marginLeft: 6, background: "none", border: 0, color: "#fff", cursor: "pointer" }}>✕</button>
                )}
              </span>
            ))}
            {s.allowlist_contacts.length === 0 && <span className="muted">Список порожній — CRM нікому не надсилає просьби.</span>}
          </div>
          {owner && (
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <input value={addId} onChange={(e) => setAddId(e.target.value.replace(/\D/g, ""))} placeholder="ID клієнта" style={{ width: 120, height: 30 }} />
              <button className="btn btn-light" disabled={busy || !addId} onClick={addContact}>Додати</button>
              <span className="muted" style={{ fontSize: 12 }}>ID — число в адресі картки клієнта: …/clients/<b>12345</b></span>
            </div>
          )}
        </div>
      </div>
      <div className="panel">
        <h3 style={{ marginTop: 0 }}>Тексти просьби</h3>
        <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
          Підстановки: <code>{"{імʼя}"}</code> — імʼя клієнта (якщо невідоме — без звертання), <code>{"{менеджер}"}</code> — імʼя
          відповідального за угоду (якщо немає — «команда Wallcov»), <code>{"{матеріал}"}</code> — головний матеріал замовлення,{" "}
          <code>{"{посилання}"}</code> — особисте посилання на форму відгуку (обовʼязково в кожному тексті).
        </div>
        {TEXT_FIELDS.map(([k, label, when]) => (
          <div key={k} style={{ marginBottom: 14 }}>
            <div><b>{label}</b> <span className="muted" style={{ fontSize: 12 }}>— {when}</span></div>
            <textarea value={draft[k]} readOnly={!owner} rows={5} style={TEXTAREA}
              onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
            <div className="muted" style={{ fontSize: 12, margin: "4px 0 2px" }}>Так побачить клієнт (приклад):</div>
            <div style={PREVIEW}>{sample(draft[k]) || "—"}</div>
          </div>
        ))}
        {owner && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-primary" disabled={busy || !dirty}
              onClick={() => save(changed, "Тексти збережено. Після змін їх треба затвердити знову")}>Зберегти тексти</button>
            {(!s.texts_approved || dirty) && (
              <button className="btn btn-green" disabled={busy}
                onClick={() => save({ ...changed, approve_texts: true }, "Тексти затверджено")}>✓ Затвердити тексти</button>
            )}
          </div>
        )}
        {!owner && <div className="muted" style={{ fontSize: 12 }}>Змінювати тексти може лише власник.</div>}
      </div>
      <div className="panel" style={{ padding: 0, overflowX: "auto" }}>
        <div style={{ padding: "10px 12px", fontWeight: 600 }}>Історія змін текстів</div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f8fafc", textAlign: "left" }}>
              <th style={TH}>Коли</th><th style={TH}>Хто</th><th style={TH}>Текст</th><th style={TH}>Статус</th>
            </tr>
          </thead>
          <tbody>
            {s.text_versions.map((v) => (
              <tr key={v.id} style={{ borderTop: "1px solid #eef2f7" }}>
                <td style={TD}>{fmt(v.created_at)}</td>
                <td style={TD}>{v.changed_by || "—"}</td>
                <td style={TD}><b>{v.field_display}</b><div style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>{v.text}</div></td>
                <td style={TD}>
                  <Badge text={v.approved ? "затверджено" : "змінено"} color={v.approved ? "#16a34a" : "#d97706"} />
                  {v.note && <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{v.note}</div>}
                </td>
              </tr>
            ))}
            {s.text_versions.length === 0 && (
              <tr><td style={TD} colSpan={4}><span className="muted">Змін ще не було.</span></td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Reviews() {
  const [tab, setTab] = useState("pending");
  const [data, setData] = useState<ReviewList | null>(null);
  const [err, setErr] = useState("");
  const isReviewTab = tab === "pending" || tab === "published" || tab === "hidden";
  const load = useCallback(() => {
    if (!isReviewTab) return;
    api.get<ReviewList>(`/api/reviews/?status=${tab}&page_size=100`)
      .then((d) => { setData(d); setErr(""); })
      .catch((e) => setErr(errText(e)));
  }, [tab, isReviewTab]);
  useEffect(() => { load(); }, [load]);
  return (
    <div className="scroll fade" style={{ padding: 16 }}><div style={{ maxWidth: 1100 }}>
      <h2 style={{ margin: "0 0 4px" }}>⭐ Відгуки покупців</h2>
      <div className="muted" style={{ marginBottom: 12 }}>
        Відгуки з форми на сайті wallcov.com.ua. На сайті зʼявляються лише після «Опублікувати».
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {TABS.map(([k, label]) => (
          <button key={k} className={"btn " + (tab === k ? "btn-primary" : "btn-light")} onClick={() => setTab(k)}>
            {label}{data && data.counts[k] ? ` · ${data.counts[k]}` : ""}
          </button>
        ))}
      </div>
      {err && <div className="panel" style={{ color: "#dc2626" }}>{err}</div>}
      {isReviewTab && data && data.results.length === 0 && <div className="panel muted">Тут поки порожньо.</div>}
      {isReviewTab && data && data.results.map((r) => (
        <ReviewCard key={r.id} r={r} canModerate={data.can_moderate} onChanged={load} />
      ))}
      {tab === "journal" && <Journal />}
      {tab === "texts" && <TextsPanel />}
      {tab === "rules" && <RulesPanel />}
    </div></div>
  );
}
