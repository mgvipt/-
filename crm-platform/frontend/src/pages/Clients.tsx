import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Paginated } from "../api";
import { SourceChip } from "../ui";
import { useLang } from "../i18n";

interface Contact {
  id: number; display_name: string; phone: string; email: string; channels: string[];
  source?: string; loyalty_tag?: string; owner_name?: string; created_at?: string;
  kinds?: string[]; gender?: string; monitor_docs?: boolean;
}

// сегменти контрагентів: [код, назва, колір фону, колір тексту]
const KINDS: [string, string, string, string][] = [
  ["client", "Клієнти", "#eff6ff", "#1d4ed8"],
  ["supplier", "Постачальники", "#fff7ed", "#c2410c"],
  ["master", "Майстри", "#f0fdf4", "#15803d"],
  ["staff", "Співробітники", "#f5f3ff", "#6d28d9"],
  ["partner", "Партнери", "#fdf2f8", "#be185d"],
];

const LOY_COLOR: Record<string, string> = { VIP: "#7c3aed", Активний: "#16a34a", Новий: "#2563eb", Сплячий: "#d97706", Активный: "#16a34a", Новый: "#2563eb", Спящий: "#d97706" };

// ─────────────────────────────────────────────────────────────
// Додати постачальника: одна форма — картка + реквізити + моніторинг накладних
// ─────────────────────────────────────────────────────────────
function AddSupplier({ onClose, onSaved }: { onClose: () => void; onSaved: (id: number) => void }) {
  const { t } = useLang();
  const [f, setF] = useState<any>({
    last_name: "", first_name: "", edrpou: "", iban: "",
    doc_email: "", phone: "", monitor_docs: true, comment: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const inp: any = { width: "100%", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 10px" };
  const lbl: any = { fontSize: 12, fontWeight: 700, color: "#475569", marginBottom: 3 };
  const hint: any = { fontSize: 11, color: "#94a3b8", marginTop: 2 };

  async function save() {
    if (!f.last_name.trim() && !f.first_name.trim()) { setErr(t("Впиши название или ФИО поставщика", "Впиши назву або ПІБ постачальника")); return; }
    if (f.monitor_docs && !f.doc_email.trim()) { setErr(t("Для мониторинга нужна почта, с которой поставщик присылает накладные", "Для моніторингу потрібна пошта, з якої постачальник надсилає накладні")); return; }
    setBusy(true); setErr("");
    try {
      const d: any = await api.post("/api/contacts/", {
        first_name: f.first_name.trim(), last_name: f.last_name.trim(),
        edrpou: f.edrpou.trim(), iban: f.iban.trim().replace(/\s/g, ""),
        email: f.doc_email.trim(), doc_email: f.doc_email.trim(),
        phone: f.phone.trim(), comment: f.comment.trim(),
        kinds: ["supplier"], monitor_docs: !!f.monitor_docs,
      });
      onSaved(d.id);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || t("Не удалось сохранить", "Не вдалося зберегти"));
      setBusy(false);
    }
  }

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 400, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "5vh 12px", overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 16, padding: 20, width: 520, maxWidth: "100%", boxShadow: "0 24px 70px rgba(15,23,42,.35)" }}>
        <h3 style={{ margin: "0 0 4px" }}>{t("Новый поставщик", "Новий постачальник")}</h3>
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          {t("Накладные с его почты будут сами попадать в Финансы → «Вх. накладные», а кредиторка создаваться автоматически.",
             "Накладні з його пошти самі потраплятимуть у Фінанси → «Вх. накладні», а кредиторка створюватиметься автоматично.")}
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ flex: 2 }}>
            <div style={lbl}>{t("Название / Фамилия", "Назва / Прізвище")} *</div>
            <input style={inp} value={f.last_name} onChange={(e) => set("last_name", e.target.value)} placeholder={t("напр. ФОП Корженевський", "напр. ФОП Корженевський")} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={lbl}>{t("Имя", "Імʼя")}</div>
            <input style={inp} value={f.first_name} onChange={(e) => set("first_name", e.target.value)} placeholder="Євгеній" />
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <div style={{ flex: 1 }}>
            <div style={lbl}>{t("ЄДРПОУ / ІПН", "ЄДРПОУ / ІПН")}</div>
            <input style={inp} value={f.edrpou} onChange={(e) => set("edrpou", e.target.value)} placeholder="3263606456" />
            <div style={hint}>{t("По нему кредиторка гасится с выписки", "По ньому кредиторка гаситься з виписки")}</div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={lbl}>{t("Телефон", "Телефон")}</div>
            <input style={inp} value={f.phone} onChange={(e) => set("phone", e.target.value)} placeholder="+380..." />
          </div>
        </div>

        <div style={{ marginTop: 10 }}>
          <div style={lbl}>{t("IBAN (счёт для оплаты)", "IBAN (рахунок для оплати)")}</div>
          <input style={inp} value={f.iban} onChange={(e) => set("iban", e.target.value)} placeholder="UA49 3052 9900 0002 6003 0161 06943" />
          <div style={hint}>{t("Нужен, чтобы платить ему кнопкой «💳 ФОП» из кредиторки", "Потрібен, щоб платити йому кнопкою «💳 ФОП» з кредиторки")}</div>
        </div>

        <div style={{ marginTop: 14, padding: 12, background: "#f8fafc", borderRadius: 10, border: "1px solid #e2e8f0" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontWeight: 700, fontSize: 13 }}>
            <input type="checkbox" checked={!!f.monitor_docs} onChange={(e) => set("monitor_docs", e.target.checked)} />
            {t("Мониторить накладные с почты", "Моніторити накладні з пошти")}
          </label>
          <div style={{ marginTop: 8 }}>
            <div style={lbl}>{t("Почта, С КОТОРОЙ он присылает накладные", "Пошта, З ЯКОЇ він надсилає накладні")}{f.monitor_docs ? " *" : ""}</div>
            <input style={inp} value={f.doc_email} onChange={(e) => set("doc_email", e.target.value)} placeholder="greendeco888@gmail.com" />
            <div style={hint}>
              {t("Это адрес ОТПРАВИТЕЛЯ. Письма приходят на наш ящик mogpod.vipt@gmail.com — его сюда вписывать не надо.",
                 "Це адреса ВІДПРАВНИКА. Листи приходять на нашу скриньку mogpod.vipt@gmail.com — її сюди вписувати не треба.")}
            </div>
          </div>
          <div style={{ marginTop: 8, fontSize: 11.5, color: "#64748b", lineHeight: 1.5 }}>
            <b>{t("Как это работает:", "Як це працює:")}</b><br />
            {t("1. Поставщик шлёт накладную (.xls) на нашу почту", "1. Постачальник шле накладну (.xls) на нашу пошту")}<br />
            {t("2. CRM забирает её каждые 10 минут → черновик в «Вх. накладные»", "2. CRM забирає її кожні 10 хвилин → чернетка у «Вх. накладні»")}<br />
            {t("3. Ты жмёшь «Провести», сверяешь товары → приход на склад + кредиторка", "3. Ти тиснеш «Провести», звіряєш товари → прихід на склад + кредиторка")}<br />
            {t("4. Платишь кнопкой «💳 ФОП», выписка сама гасит долг", "4. Платиш кнопкою «💳 ФОП», виписка сама гасить борг")}
          </div>
        </div>

        <div style={{ marginTop: 10 }}>
          <div style={lbl}>{t("Заметка (условия, отсрочка, скидка)", "Нотатка (умови, відстрочка, знижка)")}</div>
          <input style={inp} value={f.comment} onChange={(e) => set("comment", e.target.value)}
                 placeholder={t("напр. отсрочка 14 дней, скидка 40%", "напр. відстрочка 14 днів, знижка 40%")} />
        </div>

        {err && <div style={{ color: "#dc2626", fontSize: 12.5, marginTop: 10, fontWeight: 600 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
          <button className="btn btn-light" onClick={onClose}>{t("Отмена", "Скасувати")}</button>
          <button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? "…" : t("Создать поставщика", "Створити постачальника")}</button>
        </div>
      </div>
    </div>
  );
}

export default function Clients() {
  const { t } = useLang();
  const nav = useNavigate();
  const [rows, setRows] = useState<Contact[]>([]);
  const [count, setCount] = useState(0);
  const [q, setQ] = useState("");
  const [loys, setLoys] = useState<string[]>([]);
  const [src, setSrc] = useState("");
  const [withPhone, setWithPhone] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [ordering, setOrdering] = useState("-created_at");
  const [kind, setKind] = useState("");        // "" = всі сегменти
  const [addSup, setAddSup] = useState(false);  // форма «Додати постачальника»

  function load(p = page) {
    const qp = new URLSearchParams({ page: String(p), page_size: String(pageSize), ordering });
    if (q.trim()) qp.set("search", q.trim());
    if (loys.length) qp.set("loyalty_in", loys.join(","));
    if (withPhone) qp.set("has_phone", "1");
    if (src) qp.set("source", src);
    if (kind) qp.set("kind", kind);
    api.get<Paginated<Contact>>(`/api/contacts/?${qp.toString()}`).then((d) => {
      setRows(d.results); setCount(d.count ?? d.results.length);
    });
  }
  useEffect(() => { load(1); setPage(1); /* eslint-disable-next-line */ }, [pageSize, loys, src, ordering, withPhone, kind]);
  const totalPages = Math.max(1, Math.ceil(count / pageSize));
  function apply() { setPage(1); load(1); }
  function go(p: number) { setPage(p); load(p); }

  return (
    <div className="scroll pad fade">
      {/* ── СЕГМЕНТИ ── */}
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
        <button onClick={() => setKind("")}
          style={{ padding: "6px 13px", borderRadius: 999, fontSize: 13, cursor: "pointer", fontWeight: kind === "" ? 700 : 500,
                   border: "1px solid " + (kind === "" ? "#0f172a" : "#e2e8f0"), background: kind === "" ? "#0f172a" : "#fff",
                   color: kind === "" ? "#fff" : "#64748b" }}>{t("Все","Всі")}</button>
        {KINDS.map(([k, lbl, bg, fg]) => {
          const on = kind === k;
          return (
            <button key={k} onClick={() => setKind(on ? "" : k)}
              style={{ padding: "6px 13px", borderRadius: 999, fontSize: 13, cursor: "pointer", fontWeight: on ? 700 : 500,
                       border: "1px solid " + (on ? fg : "#e2e8f0"), background: on ? bg : "#fff", color: on ? fg : "#64748b" }}>
              {lbl}
            </button>
          );
        })}
        <div className="spacer" style={{ flex: 1 }} />
        <button className="btn btn-primary" onClick={() => setAddSup(true)}
          title={t("Добавить поставщика и сразу включить мониторинг накладных","Додати постачальника і одразу увімкнути моніторинг накладних")}>
          + {t("Поставщик","Постачальник")}
        </button>
      </div>
      {addSup && <AddSupplier onClose={() => setAddSup(false)} onSaved={(id: number) => { setAddSup(false); nav(`/clients/${id}`); }} />}

      {/* фільтри */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10, background: "#fff", padding: 10, borderRadius: 8, border: "1px solid #e2e8f0" }}>
        <input placeholder={t("🔍 Имя / телефон / email","🔍 Імʼя / телефон / email")} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && apply()} style={{ flex: "1 1 220px", height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 10px" }} />
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <span className="muted" style={{ fontSize: 12 }}>{t("Статус","Статус")}:</span>
          {["VIP", "Активний", "Новий", "Сплячий"].map((x) => {
            const on = loys.includes(x);
            return <span key={x} onClick={() => setLoys((c) => on ? c.filter((y) => y !== x) : [...c, x])} style={{ cursor: "pointer", fontSize: 12, fontWeight: 600, padding: "5px 10px", borderRadius: 14, border: "1px solid " + (on ? "#2563eb" : "#cbd5e1"), background: on ? "#2563eb" : "#fff", color: on ? "#fff" : "#475569" }}>{x}</span>;
          })}
        </div>
        <input placeholder={t("Источник","Джерело")} value={src} onChange={(e) => setSrc(e.target.value)} onKeyDown={(e) => e.key === "Enter" && apply()} style={{ width: 130, height: 34, border: "1px solid #cbd5e1", borderRadius: 7, padding: "0 8px" }} />
        <select value={ordering} onChange={(e) => setOrdering(e.target.value)} style={{ height: 34, border: "1px solid #cbd5e1", borderRadius: 7 }}>
          <option value="-created_at">{t("Сначала новые","Спершу нові")}</option><option value="created_at">{t("Сначала старые","Спершу старі")}</option><option value="first_name">{t("По имени А-Я","За імʼям А-Я")}</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 13 }}><input type="checkbox" checked={withPhone} onChange={(e) => setWithPhone(e.target.checked)} />{t("только с телефоном","лише з телефоном")}</label>
        <button className="btn btn-primary" onClick={apply}>{t("Найти","Знайти")}</button>
      </div>
      {/* пагінація */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, fontSize: 13 }}>
        <span className="muted">{t("Всего клиентов","Всього клієнтів")}: <b>{count.toLocaleString("ru")}</b></span>
        <div style={{ flex: 1 }} />
        <span className="muted">{t("На стр.","На стор.")}:</span>
        <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 6 }}>{[20, 50, 100, 200, 500].map((n) => <option key={n} value={n}>{n}</option>)}</select>
        <button className="btn btn-light" disabled={page <= 1} onClick={() => go(page - 1)}>←</button>
        <span>{t("стр.","стор.")} <b>{page}</b> {t("из","з")} {totalPages}</span>
        <button className="btn btn-light" disabled={page >= totalPages} onClick={() => go(page + 1)}>→</button>
      </div>
      <div className="tablewrap">
        <table>
          <thead><tr><th>{t("Имя","Імʼя")}</th><th>{t("Телефон","Телефон")}</th><th>{t("Email","Email")}</th><th>{t("Источник","Джерело")}</th><th>{t("Лояльность","Лояльність")}</th><th>{t("Ответственный","Відповідальний")}</th><th>{t("Создано","Створено")}</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={7} className="muted" style={{ padding: 14 }}>{t("Ничего не найдено.","Нічого не знайдено.")}</td></tr>}
            {rows.map((c) => (
              <tr key={c.id} onClick={() => nav(`/clients/${c.id}`)} style={{ cursor: "pointer" }}>
                <td style={{ fontWeight: 500, color: "#1d4ed8" }}>{c.display_name}</td>
                <td className="muted">{c.phone || "—"}</td>
                <td className="muted">{c.email || "—"}</td>
                <td>{c.source ? <SourceChip source={c.source} /> : <span className="muted">—</span>}</td>
                <td>{c.loyalty_tag ? <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20, background: (LOY_COLOR[c.loyalty_tag] || "#64748b") + "22", color: LOY_COLOR[c.loyalty_tag] || "#64748b" }}>{c.loyalty_tag}</span> : <span className="muted">—</span>}</td>
                <td className="muted">{c.owner_name || "—"}</td>
                <td className="muted">{c.created_at ? new Date(c.created_at).toLocaleDateString("ru") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
