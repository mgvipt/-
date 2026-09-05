/* Склад · Робота — модуль кладовщика. Вкладки: Черга (спільна, весь відділ) · Мої задачі (в роботі) ·
   Зміна (день+обід+ЗП, звʼязано з головною кнопкою «Почати робочий день») · Зарплата (період) · Контроль (керівник). */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";
import VykraskaDoc from "../VykraskaDoc";
import KpDoc from "../KpDoc";
import { useAuth } from "../auth";
import RepackForm, { RepackDocModal } from "../RepackForm";
import NPDelivery from "./NPDelivery";
import ClientChat from "../ClientChat";

const C = { terra: "#C67D5F", green: "#16a34a", amber: "#ca8a04", red: "#dc2626", blue: "#2563eb", slate: "#475569" };
const f = (v: any) => Number(v || 0).toLocaleString("uk").replace(/,/g, " ");
const NEEDS_LBL: any = { underlay: "Підкладка", room: "Тип приміщення", area: "Площа стін, м²", prep: "Підготовка стін", term: "Терміни", city: "Місто / регіон", material: "Матеріал", color: "Колір / тонування", probe: "Пробник чи обʼєм", applier: "Хто наносить", budget: "Бюджет, ₴", pay: "Спосіб оплати", ship: "Доставка", contacted: "Контакт раніше", objections: "Опис / заперечення клієнта", room_type: "Тип приміщення", wall_area: "Площа стін, м²", terms: "Терміни" };
const ST: any = { queued: ["#eff6ff", "#1d4ed8", "У черзі"], taken: ["#fff7ed", "#9a3412", "Взято"], tinting: ["#fef9c3", "#854d0e", "Тонується"], packing: ["#ede9fe", "#5b21b6", "Пакування"], awaiting_photos: ["#fef2f2", "#dc2626", "Потрібні фото"], shipped: ["#dcfce7", "#166534", "Відвантажено"] };

export default function WarehouseWork() {
  const { t } = useLang();
  const [view, setView] = useState<"queue" | "mine" | "kanban" | "shift" | "salary" | "control" | "dashboard" | "repack">(() => (localStorage.getItem("wh_view") as any) || "shift");
  useEffect(() => { try { localStorage.setItem("wh_view", view); } catch (e) { /* noop */ } }, [view]);
  const [sp] = useSearchParams();
  const [job, setJob] = useState<number | null>(null);
  useEffect(() => {
    const tb = sp.get("tab");
    if (tb && ["queue", "mine", "kanban", "shift", "salary", "control", "dashboard", "repack"].includes(tb)) { setView(tb as any); setJob(null); }
  }, [sp]);
  if (job) return <TaskCard t={t} jobId={job} onBack={() => setJob(null)} />;
  const { can } = useAuth();
  const mgr = can("warehouse.view.all") || can("roles.manage");
  const TABS: any[] = [["shift", "🏠", "Смена", "Зміна"], ["queue", "📋", "Общий список", "Загальний список"], ["kanban", "🗂", "Мои задачи", "Мої задачі"], ["salary", "💰", "Зарплата", "ЗП"], ["repack", "🧪", "Розлив", "Розлив"]].concat(mgr ? [["control", "🛡", "Контроль", "Контроль"], ["dashboard", "📊", "Дашборд", "Дашборд"]] : []);
  return (
    <div className="scroll pad fade" style={{ width: "100%" }}>
      <h2 style={{ margin: "0 0 12px", fontSize: 22, display: "flex", alignItems: "center", gap: 8 }}><Icon n="truck" size={20} /> {t("Отгрузка", "Відвантаження")}</h2>
      <div style={{ display: "flex", gap: 5, marginBottom: 16, position: "sticky", top: 0, background: "rgba(255,255,255,.88)", backdropFilter: "blur(6px)", padding: "6px 0", zIndex: 10, overflowX: "auto" }}>
        {TABS.map(([k, e, ru, uk]) => (
          <button key={k} onClick={() => setView(k as any)} className={"btn" + (view === k ? " btn-primary" : " btn-light")} style={{ flex: "1 0 auto", fontSize: 13, padding: "9px 10px", whiteSpace: "nowrap" }}>{e} {t(ru, uk)}</button>
        ))}
      </div>
      {view === "queue" && <QueueView t={t} onOpen={setJob} mgr={mgr} />}
      {view === "mine" && <MineView t={t} onOpen={setJob} />}
      {view === "kanban" && <KanbanView t={t} onOpen={setJob} />}
      {view === "shift" && <ShiftView t={t} />}
      {view === "salary" && <SalaryView t={t} />}
      {view === "repack" && <RepackPage t={t} />}
      {view === "control" && <ControlView t={t} />}
      {view === "dashboard" && <DashboardView t={t} />}
    </div>
  );
}

function RefShots({ photos, t }: { photos?: string[]; t: any }) {
  const [zoom, setZoom] = useState<string | null>(null);
  const list = photos || [];
  if (!list.length) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div className="label">📷 {t("Скриншоты от клиента", "Скріни від клієнта")} <span className="muted" style={{ fontSize: 11, fontWeight: 400 }}>({list.length})</span></div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 5 }}>
        {list.map((p, i) => (
          <img key={i} src={p} onClick={() => setZoom(p)} title={t("Открыть в масштабе", "Відкрити у масштабі")}
            style={{ width: 78, height: 78, objectFit: "cover", borderRadius: 8, border: "1px solid #e2e8f0", display: "block", cursor: "zoom-in" }} />
        ))}
      </div>
      {zoom && createPortal(
        <div onClick={() => setZoom(null)} style={{ position: "fixed", inset: 0, zIndex: 100000, background: "rgba(0,0,0,.88)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "zoom-out" }}>
          <img src={zoom} onClick={(e) => e.stopPropagation()} style={{ maxWidth: "94vw", maxHeight: "94vh", objectFit: "contain", borderRadius: 8, boxShadow: "0 10px 60px rgba(0,0,0,.6)" }} />
          <button onClick={() => setZoom(null)} style={{ position: "fixed", top: 20, right: 26, width: 40, height: 40, borderRadius: 20, border: "none", background: "rgba(255,255,255,.16)", color: "#fff", fontSize: 20, cursor: "pointer" }}>✕</button>
        </div>, document.body)}
    </div>
  );
}

function JobCard({ j, t, onClick, action }: any) {
  const [bg, fg, lbl] = ST[j.status] || ["#f1f5f9", C.slate, j.status];
  const tintN = (j.kits || []).filter((k: any) => k.tint).length;
  return (
    <div className="panel" style={{ margin: 0, padding: "13px 14px", cursor: onClick ? "pointer" : "default", borderLeft: `4px solid ${fg}` }} onClick={onClick}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <b style={{ fontSize: 15 }}>#{j.deal_id} · {j.client}</b>
            <span style={{ fontSize: 10.5, fontWeight: 700, background: bg, color: fg, borderRadius: 20, padding: "2px 9px" }}>{lbl}</span>
            {j.is_dozakaz
              ? <span title={t("Это допродажа к основной сделке — едет одной посылкой","Це допродаж до основної угоди — їде однією посилкою")} style={{ fontSize: 10, fontWeight: 700, background: "#fef3c7", color: "#92400e", borderRadius: 20, padding: "2px 8px" }}>📦 {t("допродажа","допродаж")} → #{j.parcel_main}</span>
              : ((j.subtasks && j.subtasks.length > 0) || (j.parcel_orders && j.parcel_orders.length > 0))
              ? <span title={t("К заказу есть допродажа — посылка не одна, пакуется вместе","До замовлення є допродаж — посилка не одна, пакується разом")} style={{ fontSize: 10, fontWeight: 700, background: "#fef3c7", color: "#92400e", borderRadius: 20, padding: "2px 8px" }}>📦 +{(j.subtasks && j.subtasks.length) || (j.parcel_orders && j.parcel_orders.length) || 0} {t("допродажа","допродаж")}</span>
              : null}
          </div>
          <div className="muted" style={{ fontSize: 12.5, marginTop: 3, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <span>📍 {j.city || "—"}</span>
            <span>{j.kind_type === "test" ? "🧪 " + t("тест-набор", "тест-набір") : "📦 " + t("основной", "основний")}</span>
            {j.channel === "offline" && <span style={{ color: C.terra }}>🏪 {t("салон", "салон")}</span>}
            <span>{t("наборов", "наборів")}: {(j.kits || []).length}</span>
            {tintN > 0 ? <span style={{ color: "#9a3412" }}>🎨 {t("тонировать", "тонувати")} {tintN}</span> : ((j.kits || []).length > 0 ? <span>{t("без тонировки", "без тонування")}</span> : null)}
            {["packing", "awaiting_photos", "shipped"].includes(j.status) && <span style={{ color: "#5b21b6" }}>{j.packed ? "📦 " + t("ручная упак.", "ручне пак.") : "🚚 " + t("НП контейнер", "НП контейнер")}</span>}
            {j.photos_n > 0 && <span style={{ color: "#2563eb" }}>📷 {j.photos_n}/2</span>}
            {j.ref_photos_n > 0 && <span style={{ color: C.terra }} title={t("Скриншоты от клиента", "Скріни від клієнта")}>🖼 {j.ref_photos_n}</span>}
            {j.np_name && <span>📥 {j.np_name}</span>}
            {j.ttn && <span style={{ color: "#16a34a", fontWeight: 600 }}>🚚 ТТН {j.ttn}</span>}
            {j.assignee_name && j.status !== "queued" && <span>👤 {j.assignee_name}</span>}
            {j.created_at && <span title={t("Создана / в очереди с","Створена / у черзі з")}>🕐 {new Date(j.created_at).toLocaleString("uk", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>}
          </div>
        </div>
        {action}
      </div>
    </div>
  );
}

function KpDocLoader({ dealId, onClose }: { dealId: number; onClose: () => void }) {
  const [deal, setDeal] = useState<any>(null);
  useEffect(() => { api.get<any>(`/api/deals/${dealId}/`).then(setDeal).catch(onClose); /* eslint-disable-next-line */ }, [dealId]);
  if (!deal) return null;
  return <KpDoc deal={deal} onClose={onClose} />;
}

// Печать накладной с учётом допродажи: если у задачи есть дозаказ — показываем обе сделки (основную и допродаж),
// чтобы склад распечатал накладную по каждой (едут одной посылкой).
function NakladnaPrint({ j, t, style, size = 16 }: any) {
  const [pick, setPick] = useState(false);
  const [kpId, setKpId] = useState<number | null>(null);
  const subs = (j.subtasks || []).filter((s: any) => s && s.deal_id);
  const deals = [{ id: j.deal_id, title: j.client || ("#" + j.deal_id), dozakaz: false },
                 ...subs.map((s: any) => ({ id: s.deal_id, title: s.title || ("#" + s.deal_id), dozakaz: true }))];
  const multi = deals.length > 1;
  const btnStyle: any = { display: "inline-flex", alignItems: "center", justifyContent: "center", cursor: "pointer", borderRadius: 8, ...style, ...(multi ? { width: "auto", paddingLeft: 9, paddingRight: 9 } : {}) };
  return (
    <>
      <button className="btn" title={multi ? t("В задаче 2 сделки — печать накладных", "У задачі 2 угоди — друк накладних") : t("Печать накладной", "Друк накладної")}
        onClick={(e) => { e.stopPropagation(); if (multi) setPick(true); else setKpId(j.deal_id); }} style={btnStyle}>
        <Icon n="file" size={size} />{multi ? <span style={{ marginLeft: 3, fontSize: 12, fontWeight: 800 }}>×{deals.length}</span> : null}
      </button>
      {pick && (
        <div onClick={(e) => { e.stopPropagation(); setPick(false); }} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 90, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, padding: 18, maxWidth: 460, width: "100%", boxShadow: "0 20px 50px rgba(15,23,42,.3)" }}>
            <div style={{ fontWeight: 800, fontSize: 15, marginBottom: 4 }}>🖨 {t("В этой задаче 2 сделки", "У цій задачі 2 угоди")}</div>
            <div className="muted" style={{ fontSize: 12.5, marginBottom: 14, lineHeight: 1.5 }}>{t("Основная сделка и допродажа. Распечатай накладную по каждой — они едут одной посылкой.", "Основна угода і допродаж. Роздрукуй накладну по кожній — вони їдуть однією посилкою.")}</div>
            {deals.map((pd: any) => (
              <button key={pd.id} className="btn btn-light" onClick={(e) => { e.stopPropagation(); setKpId(pd.id); }}
                style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, height: 48, marginBottom: 8, textAlign: "left", padding: "0 12px" }}>
                <span style={{ fontSize: 13.5 }}>{pd.dozakaz ? "📦 " + t("Допродажа", "Допродаж") : "🧾 " + t("Основная", "Основна")} · <b>#{pd.id}</b>{pd.title ? " · " + pd.title : ""}</span>
                <span style={{ color: "#1d4ed8", fontWeight: 700, whiteSpace: "nowrap" }}>🖨 {t("Печать", "Друк")}</span>
              </button>
            ))}
            <button className="btn btn-light" onClick={(e) => { e.stopPropagation(); setPick(false); }} style={{ width: "100%", height: 40, marginTop: 4 }}>{t("Закрыть", "Закрити")}</button>
          </div>
        </div>
      )}
      {kpId != null && <KpDocLoader dealId={kpId} onClose={() => setKpId(null)} />}
    </>
  );
}

function QueueView({ t, onOpen, mgr }: any) {
  const [staff, setStaff] = useState<any[]>([]);
  useEffect(() => { if (mgr) api.get<any>("/api/warehouse/jobs/0/reassign/").then((d) => setStaff(d)).catch(() => {}); }, [mgr]);
  async function reassign(jobId: number, uid: number) {
    try { await api.post(`/api/warehouse/jobs/${jobId}/reassign/`, { user_id: uid }); load(); }
    catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось","Не вдалося")); }
  }
  const [d, setD] = useState<any>(null);
  const [prev, setPrev] = useState<number | null>(null);
  const [vkJob, setVkJob] = useState<any>(null);
  const [kpId, setKpId] = useState<number | null>(null);
  const load = () => api.get<any>("/api/warehouse/queue/").then((d) => setD((p: any) => JSON.stringify(p) === JSON.stringify(d) ? p : d)).catch(() => {});
  useEffect(() => { load(); const tm = setInterval(load, 15000); return () => clearInterval(tm); }, []);
  if (!d) return <div className="spin">…</div>;
  const take = (id: number) => api.post<any>(`/api/warehouse/jobs/${id}/take/`, {}).then(() => onOpen(id)).catch((e: any) => { alert(e?.response?.data?.by ? t("Уже взяла ", "Вже взяла ") + e.response.data.by : t("Не удалось взять", "Не вдалося взяти")); load(); });
  const cancel = (id: number) => { if (!confirm(t("Удалить задачу из списка? Складовщики её не увидят.", "Видалити задачу зі списку? Працівники складу її не побачать."))) return; api.post<any>(`/api/warehouse/jobs/${id}/cancel/`, {}).then(load).catch(() => alert(t("Нет прав (только руководитель склада)", "Немає прав (лише керівник складу)"))); };
  const row = (j: any) => <JobCard key={j.id} j={j} t={t} onClick={() => setPrev(j.id)} action={<div style={{ display: "flex", gap: 6 }}><button className="btn" title={t("Печать бланка выкраски","Друк бланка викраски")} onClick={(e) => { e.stopPropagation(); setVkJob(j); }} style={{ height: 42, background: "#f5f3ff", color: "#6d28d9", border: "1px solid #ddd6fe" }}><Icon n="🎨" size={16} /></button><NakladnaPrint j={j} t={t} style={{ height: 42, background: "#eff6ff", color: "#1d4ed8", border: "1px solid #bfdbfe" }} size={16} />{mgr && <button className="btn" title={t("Удалить неактуальную задачу","Видалити неактуальну задачу")} onClick={(e) => { e.stopPropagation(); cancel(j.id); }} style={{ height: 42, color: "#dc2626", background: "#fef2f2", border: "1px solid #fecaca" }}><Icon n="trash" size={16} /></button>}<button className="btn btn-primary" style={{ height: 42, fontSize: 14, fontWeight: 600 }} onClick={(e) => { e.stopPropagation(); take(j.id); }}>{t("Взять", "Взяти")}</button>{mgr && <select value="" onClick={(e) => e.stopPropagation()} onChange={(e) => { const v = Number(e.target.value); if (e.target.value !== "") reassign(j.id, v); }} title={t("Назначить сотрудника","Призначити співробітника")} style={{ height: 42, border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 12, maxWidth: 130 }}><option value="">👤 {t("Кому…","Кому…")}</option>{staff.map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}</select>}</div>} />;
  const sal = (d.queue || []).filter((j: any) => j.channel === "offline");
  const rest = (d.queue || []).filter((j: any) => j.channel !== "offline");
  return (
    <div className="scroll pad fade" style={{ width: "100%" }}>
      {prev != null && <JobPreview jobId={prev} t={t} onClose={() => setPrev(null)} onTake={(id: number) => { setPrev(null); take(id); }} />}
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>{t("Очередь по порядку (сверху — раньше). Жми задачу — увидишь товары и потребность. Тип — бейджем в задаче.", "Черга по порядку (зверху — раніше). Тисни задачу — побачиш товари і потребу. Тип — бейджем у задачі.")} {t("Свободно", "Вільно")}: <b>{(d.queue || []).length}</b>{mgr && d.all_active ? <> · {t("В работе у сотрудников","У роботі у співробітників")}: <b>{d.all_active.length}</b></> : null}</div>
      {mgr && d.all_active && d.all_active.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <b style={{ fontSize: 14 }}>🛡 {t("В работе у сотрудников (руководитель видит всё)","У роботі у співробітників (керівник бачить все)")}</b>
          {d.all_active.map((j: any) => <JobCard key={"a" + j.id} j={j} t={t} onClick={() => onOpen(j.id)} action={
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <button className="btn" title={t("Удалить неактуальную задачу","Видалити неактуальну задачу")} onClick={(e) => { e.stopPropagation(); cancel(j.id); }} style={{ height: 36, color: "#dc2626", background: "#fef2f2", border: "1px solid #fecaca" }}><Icon n="trash" size={15} /></button>
            <select value="" onClick={(e) => e.stopPropagation()} onChange={(e) => { const v = Number(e.target.value); if (!isNaN(v) && e.target.value !== "") reassign(j.id, v); }}
              title={t("Передать задачу другому сотруднику","Передати задачу іншому співробітнику")}
              style={{ height: 36, border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 12, maxWidth: 150 }}>
              <option value="">👤 {t("Передать…","Передати…")}</option>
              <option value="0">↩ {t("В очередь (снять)","У чергу (зняти)")}</option>
              {staff.map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select></div>} />)}
        </div>
      )}
      {mgr && <ShippedFilter staff={staff} onOpen={onOpen} t={t} />}
      {(d.queue || []).length === 0 && <div className="note">{t("Очередь пуста — все задачи разобраны 👍", "Черга порожня — всі задачі розібрані 👍")}</div>}
      {sal.length > 0 && <div style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 12, padding: "10px 12px", marginBottom: 12 }}><div className="label" style={{ margin: "0 0 8px", color: C.terra }}>🔥 {t("Покрытия для стен — приоритет", "Покриття для стін — пріоритет")} <span className="muted" style={{ fontWeight: 400 }}>· {sal.length}</span></div><div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{sal.map(row)}</div></div>}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{rest.map(row)}</div>
      {vkJob && <VykraskaDoc data={{ number: vkJob.deal_id, material: vkJob.needs && vkJob.needs.material, color: vkJob.needs && vkJob.needs.color, area: vkJob.needs && vkJob.needs.area, underlay: vkJob.needs && vkJob.needs.underlay, kits: vkJob.kits, client: vkJob.client, phone: vkJob.phone }} onClose={() => setVkJob(null)} />}
      {kpId != null && <KpDocLoader dealId={kpId} onClose={() => setKpId(null)} />}
    </div>
  );
}

function JobPreview({ jobId, t, onClose, onTake }: any) {
  const [j, setJ] = useState<any>(null);
  useEffect(() => { api.get<any>(`/api/warehouse/jobs/${jobId}/`).then(setJ).catch(() => {}); }, [jobId]);
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={(e) => e.stopPropagation()} className="panel" style={{ maxWidth: 560, width: "100%", maxHeight: "86vh", overflowY: "auto", margin: 0 }}>
        {!j ? <div className="spin">…</div> : <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <b style={{ fontSize: 17 }}>#{j.deal_id} · {j.client}</b>
            <button className="btn btn-light" onClick={onClose} style={{ padding: "4px 11px" }}>✕</button>
          </div>
          <div className="muted" style={{ fontSize: 12.5, margin: "4px 0 12px" }}>📍 {j.city || "—"} · {j.kind_type === "test" ? "🧪 " + t("тест-набор", "тест-набір") : "📦 " + t("основной", "основний")}{j.channel === "offline" ? " · 🏪 " + t("салон", "салон") : ""}</div>
          {(j.is_dozakaz || (j.parcel_orders && j.parcel_orders.length > 0) || (j.subtasks && j.subtasks.length > 0)) && (
            <div style={{ background: "#ecfeff", border: "1px solid #a5f3fc", borderRadius: 10, padding: "8px 11px", marginBottom: 12, fontSize: 12.5, color: "#0e7490" }}>
              📦 <b>{t("Одна посылка.","Одна посилка.")}</b> {j.is_dozakaz ? t("Это дозаказ — упаковать вместе с основной сделкой.","Це дозамовлення — пакувати разом з основною сделкою.") : t("К этой сделке едут дозаказы — упаковать в одну коробку.","До цієї сделки їдуть дозамовлення — пакувати в одну коробку.")}
              {((j.parcel_orders && j.parcel_orders.length > 0) || (j.subtasks && j.subtasks.length > 0)) ? <> {t("Вместе:","Разом:")} {((j.parcel_orders && j.parcel_orders.length > 0) ? j.parcel_orders.map((p: any) => "#" + p.id) : (j.subtasks || []).map((s: any) => "#" + s.deal_id)).join(", ")}.</> : null}{" "}{j.is_dozakaz ? <>{t("ТТН — на основной","ТТН — на основній")} #{j.parcel_main}.</> : <>{t("Склад создаёт ОДНУ ТТН здесь (внизу, «Нова Пошта»).","Склад створює ОДНУ ТТН тут (внизу, «Нова Пошта»).")}</>}
            </div>
          )}
          <div className="label">📦 {t("Товары в сделке", "Товари в угоді")}</div>
          {(j.items || []).length ? (j.items || []).map((it: any, i: number) => <div key={i} style={{ fontSize: 13.5, padding: "5px 0", borderBottom: "1px solid #f6f8fb" }}>• {it.name} <b>× {it.qty}</b> {it.weight_kg && it.weight_kg !== "0" && it.weight_kg !== "0.000" ? <span className="muted">· {it.weight_kg} кг</span> : null}</div>) : <div className="muted" style={{ fontSize: 12 }}>—</div>}
          {(j.subtasks || []).length > 0 && (j.subtasks).map((s: any) => (
            <div key={"sub" + s.job_id} style={{ marginTop: 10, background: "#f0fdff", border: "1px solid #cffafe", borderRadius: 10, padding: "8px 11px" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0e7490" }}>↳ 📦 {t("Дозаказ", "Дозамовлення")} #{s.deal_id}{s.title ? " · " + s.title : ""}</div>
              {(s.items || []).map((it: any, i: number) => <div key={i} style={{ fontSize: 13, padding: "3px 0", color: "#334155" }}>• {it.name} <b>× {it.qty}</b></div>)}
              {s.kits_n > 0 ? <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>🎨 {t("наборов", "наборів")}: {s.kits_n}</div> : null}
            </div>
          ))}
          {(j.kits || []).length > 0 && <><div className="label" style={{ marginTop: 14 }}>🎨 {t("Наборы / тонировка", "Набори / тонування")} ({(j.kits || []).length})</div>
            {(j.kits || []).map((k: any, i: number) => <div key={i} style={{ fontSize: 13.5, padding: "4px 0" }}>• <b>{k.material || "—"}</b> <span className="muted">{k.color}</span>{k.tint ? " · 🎨 " + t("тонировать", "тонувати") : ""}{k.board ? " · " + t("с дощечкой", "з дощечкою") : ""}{k.note ? <span style={{ color: "#0369a1" }}> · 💬 {k.note}</span> : null}</div>)}</>}
          <div className="label" style={{ marginTop: 14 }}>📋 {t("Выявление потребности", "Виявлення потреби")}</div>
          {Object.keys(j.needs || {}).length ? Object.entries(j.needs).filter(([, v]: any) => v !== "" && v != null && v !== "—").map(([k, v]: any) => <div key={k} style={{ fontSize: 13, padding: "3px 0", display: "flex", gap: 10, borderBottom: "1px solid #f8fafc" }}><span className="muted" style={{ minWidth: 150, flexShrink: 0 }}>{NEEDS_LBL[k] || k}</span><b>{String(v)}</b></div>) : <div className="muted" style={{ fontSize: 12 }}>{t("Потребность не заполнена", "Потребу не заповнено")}</div>}
          <RefShots photos={j.ref_photos} t={t} />
          <button className="btn btn-primary" style={{ width: "100%", height: 48, marginTop: 18, fontWeight: 700, fontSize: 15 }} onClick={() => onTake(j.id)}>✋ {t("Взять в работу", "Взяти в роботу")}</button>
        </>}
      </div>
    </div>
  );
}

function PhotoThumb({ url }: { url: string }) {
  const [src, setSrc] = useState("");
  useEffect(() => { (api as any).blobUrl(url).then(setSrc).catch(() => { /* noop */ }); }, [url]);
  return src ? <a href={src} target="_blank" rel="noreferrer"><img src={src} style={{ width: 72, height: 72, objectFit: "cover", borderRadius: 8, border: "1px solid #cbd5e1", display: "block" }} /></a> : <div style={{ width: 72, height: 72, borderRadius: 8, background: "#f1f5f9", border: "1px solid #e2e8f0" }} />;
}

function KanbanView({ t, onOpen }: any) {
  const [d, setD] = useState<any>(null);
  const load = () => api.get<any>("/api/warehouse/queue/").then((d) => setD((p: any) => JSON.stringify(p) === JSON.stringify(d) ? p : d)).catch(() => {});
  useEffect(() => { load(); const tm = setInterval(load, 15000); return () => clearInterval(tm); }, []);
  const take = (id: number) => api.post<any>(`/api/warehouse/jobs/${id}/take/`, {}).then(() => onOpen(id)).catch((e: any) => { alert(e?.response?.data?.by ? t("Уже взяла ", "Вже взяла ") + e.response.data.by : t("Не удалось взять", "Не вдалося взяти")); load(); });
  if (!d) return <div className="scroll pad"><div className="spin">…</div></div>;
  const mine = d.mine || [];
  const shipped = d.shipped || [];
  const npc = (j: any) => { const sN = (j.np_stage || "").toLowerCase(); if ((sN.includes("отриман") && !sN.includes("оплат")) || sN.includes("успіш")) return "got"; if (sN.includes("прибув") || sN.includes("відділенн")) return "arrived"; if (sN.includes("дорозі")) return "transit"; if (sN.includes("відправ")) return "sent"; return "created"; };
  const COLS: any[] = [
    { k: "work", icon: "🆕", title: t("В работе", "В роботі"), color: "#1d4ed8", items: mine.filter((j: any) => j.status === "taken") },
    { k: "tint", icon: "🎨", title: t("Тонировка", "Тонування"), color: "#854d0e", items: mine.filter((j: any) => j.status === "tinting") },
    { k: "pack", icon: "📦", title: t("Пакування", "Пакування"), color: "#5b21b6", items: mine.filter((j: any) => j.status === "packing") },
    { k: "ship", icon: "🚚", title: t("ТТН + Фото", "ТТН + Фото"), color: "#dc2626", items: mine.filter((j: any) => j.status === "awaiting_photos") },
    { k: "created", icon: "📦", title: t("ТТН создана", "ТТН створена"), color: "#166534", items: shipped.filter((j: any) => npc(j) === "created") },
    { k: "sent", icon: "📤", title: t("НП · Отправлено", "НП · Відправлено"), color: "#0d9488", items: shipped.filter((j: any) => npc(j) === "sent") },
    { k: "transit", icon: "🚛", title: t("НП · В пути", "НП · В дорозі"), color: "#0891b2", items: shipped.filter((j: any) => npc(j) === "transit") },
    { k: "arrived", icon: "🏤", title: t("НП · Прибыло", "НП · Прибуло"), color: "#7c3aed", items: shipped.filter((j: any) => npc(j) === "arrived") },
    { k: "got", icon: "🎉", title: t("Получено клиентом", "Отримано клієнтом"), color: "#16a34a", items: shipped.filter((j: any) => npc(j) === "got") },
  ];
  return (
    <div className="scroll pad fade" style={{ width: "100%" }}>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>{t("Только ТВОИ задачи (взятые в работу). Новые бери в «Общем списке». Жми карточку, чтобы продолжить.", "Тільки ТВОЇ задачі (взяті в роботу). Нові бери у «Загальному списку». Тисни картку, щоб продовжити.")}</div>
      <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 12 }}>
        {COLS.map((col) => (
          <div key={col.k} style={{ flex: "0 0 300px", minWidth: 300 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: col.color, padding: "6px 4px 8px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "2px solid " + col.color + "33" }}>
              <span>{col.icon} {col.title}</span>
              <span style={{ background: col.color + "1f", color: col.color, borderRadius: 20, padding: "1px 9px", fontSize: 12, fontWeight: 700 }}>{col.items.length}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8, maxHeight: "calc(100vh - 250px)", overflowY: "auto", paddingRight: 2 }}>
              {col.items.map((j: any) => (
                <JobCard key={j.id} j={j} t={t} onClick={() => onOpen(j.id)} action={<Icon n="chevron-down" size={15} />} />
              ))}
              {col.items.length === 0 && <div className="muted" style={{ fontSize: 11.5, padding: "12px 4px", textAlign: "center", border: "1px dashed #e2e8f0", borderRadius: 10 }}>—</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MineView({ t, onOpen }: any) {
  const [d, setD] = useState<any>(null);
  const load = () => api.get<any>("/api/warehouse/queue/").then((d) => setD((p: any) => JSON.stringify(p) === JSON.stringify(d) ? p : d)).catch(() => {});
  useEffect(() => { load(); const tm = setInterval(load, 15000); return () => clearInterval(tm); }, []);
  if (!d) return <div className="spin">…</div>;
  return (
    <div>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>{t("Задачи, которые ты взяла в работу. Жми, чтобы продолжить.", "Задачі, які ти взяла в роботу. Тисни, щоб продовжити.")}</div>
      {(d.mine || []).length === 0 ? <div className="note">{t("Нет задач в работе. Возьми из «Черги».", "Немає задач у роботі. Візьми з «Черги».")}</div>
        : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))", gap: 10 }}>{d.mine.map((j: any) => <JobCard key={j.id} j={j} t={t} onClick={() => onOpen(j.id)} action={<Icon n="chevron-down" size={16} />} />)}</div>}
    </div>
  );
}

function ShiftView({ t }: any) {
  const [d, setD] = useState<any>(null);
  const load = () => api.get<any>("/api/warehouse/my-shift/").then((d) => setD((p: any) => JSON.stringify(p) === JSON.stringify(d) ? p : d)).catch(() => {});
  useEffect(() => { load(); const tm = setInterval(load, 30000); return () => clearInterval(tm); }, []);
  if (!d) return <div className="spin">…</div>;
  const act = (url: string, body: any = {}) => api.post(url, body).then(load).catch(() => {});
  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10, textAlign: "center" }}>{t("Это тот же рабочий день, что и кнопка «Почати робочий день» вверху — одна смена.", "Це той самий робочий день, що й кнопка «Почати робочий день» вгорі — одна зміна.")}</div>
      <div className="panel" style={{ textAlign: "center", padding: "24px 16px", background: "linear-gradient(135deg,#ecfdf5,#fff)" }}>
        <div className="muted" style={{ fontSize: 13 }}>{t("Заработано сегодня", "Зароблено сьогодні")}</div>
        <div style={{ fontSize: 56, fontWeight: 800, color: C.green, lineHeight: 1.1 }}>{f(d.earned_today)} ₴</div>
      </div>
      <div className="panel">
        {!d.day_open
          ? <button className="btn btn-primary" style={{ width: "100%", height: 54, fontSize: 16 }} onClick={() => act("/api/warehouse/day/start/")}>▶ {t("Начать день", "Почати день")}</button>
          : <>
            <div className="note" style={{ marginBottom: 10, fontSize: 12 }}>{t("День открыт (это та же кнопка «Почати робочий день» вверху).", "День відкритий (це та сама кнопка «Почати робочий день» вгорі).")}</div>
            <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
              <button className="btn" style={{ flex: 1, height: 48, background: d.on_lunch ? C.amber : "#f1f5f9", color: d.on_lunch ? "#fff" : C.slate, fontWeight: 600 }} onClick={() => act("/api/warehouse/lunch/")}>{d.on_lunch ? t("⏹ Закончить обед", "⏹ Закінчити обід") : t("🍽 Обед", "🍽 Обід")}</button>
              <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", background: d.lunch_min > d.lunch_norm ? "#fef2f2" : "#f8fafc", borderRadius: 8 }}>
                <b style={{ fontSize: 19, color: d.lunch_min > d.lunch_norm ? C.red : "#0f172a" }}>{d.lunch_min} {t("мин", "хв")}</b>
                <span className="muted" style={{ fontSize: 10.5 }}>{t("обед, норма", "обід, норма")} {d.lunch_norm}</span>
              </div>
            </div>
            <CloseDay t={t} onClose={(note: string) => act("/api/warehouse/day/close/", { note })} />
          </>}
      </div>
      <button className="btn btn-light" style={{ width: "100%", marginTop: 4, height: 46 }} onClick={() => { const txt = prompt(t("Идея — что улучшить в работе/сервисе?", "Ідея — що покращити в роботі/сервісі?")); if (txt) api.post("/api/warehouse/ideas/", { text: txt }).then(() => alert(t("Спасибо! Идея отправлена 💡", "Дякуємо! Ідею надіслано 💡"))).catch(() => {}); }}>💡 {t("Подать идею", "Подати ідею")}</button>
    </div>
  );
}

function CloseDay({ t, onClose }: any) {
  const [note, setNote] = useState("");
  return (
    <div>
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 4 }}>{t("Чистота склада — 1 строка (необязательно)", "Чистота складу — 1 рядок (необовʼязково)")}</div>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("всё убрала", "все прибрала")} style={{ width: "100%", height: 40, borderRadius: 8, border: "1px solid #cbd5e1", padding: "0 10px", marginBottom: 10, boxSizing: "border-box" }} />
      <button className="btn" style={{ width: "100%", height: 46, background: C.red, color: "#fff", fontWeight: 600 }} onClick={() => onClose(note)}>⏹ {t("Завершить день", "Завершити день")}</button>
    </div>
  );
}

function TaskCard({ t, jobId, onBack }: any) {
  const [j, setJ] = useState<any>(null);
  const [deal, setDeal] = useState<any>(null);
  const [docOpen, setDocOpen] = useState(false);
  const [vkOpen, setVkOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [packedLocal, setPackedLocal] = useState(false);
  const [msg, setMsg] = useState("");
  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 2600); };
  const load = () => api.get<any>(`/api/warehouse/jobs/${jobId}/`).then(setJ).catch(() => {});
  const { can: canFn } = useAuth();
  const canReassign = canFn("warehouse.view.all") || canFn("roles.manage") || canFn("warehouse.reassign");
  const [reStaff, setReStaff] = useState<any[]>([]);
  const [chatOpen, setChatOpen] = useState(false);
  useEffect(() => { if (canReassign) api.get<any>("/api/warehouse/jobs/0/reassign/").then(setReStaff).catch(() => {}); }, [canReassign]);
  const loadDeal = (did: number) => api.get<any>(`/api/deals/${did}/`).then(setDeal).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  useEffect(() => { if (j && j.deal_id) { loadDeal(j.deal_id); if (["awaiting_photos", "shipped"].includes(j.status)) setPackedLocal(true); } /* eslint-disable-next-line */ }, [j && j.deal_id]);
  if (!j) return <div className="scroll pad"><div className="spin">…</div></div>;
  const toggleTint = (i: number) => api.post<any>(`/api/warehouse/jobs/${jobId}/tinting/`, { kit: i }).then(setJ).catch(() => {});
  const setPacked = (p: boolean) => api.post<any>(`/api/warehouse/jobs/${jobId}/packing/`, { packed: p }).then((jj: any) => { setJ(jj); setPackedLocal(true); }).catch(() => {});
  const upload = (kind: string, file: File) => { (api as any).upload(`/api/warehouse/jobs/${jobId}/photo/?kind=${kind}`, file).then(load).catch(() => {}); };
  const ship = () => { setBusy(true); api.post<any>(`/api/warehouse/jobs/${jobId}/ship/`, {}).then(() => { alert(t("Готово — отправлено!", "Готово — відправлено!")); onBack(); }).catch((e: any) => { alert(e?.response?.data?.detail || t("Сделай 2 фото", "Зроби 2 фото")); load(); }).finally(() => setBusy(false)); };

  const tinted = new Set(j.tinted_kits || []);
  const kits = j.kits || [];
  const hasTint = kits.some((k: any) => k.tint);
  const tintDone = kits.every((k: any, i: number) => !k.tint || tinted.has(i));
  const packDone = packedLocal || ["packing", "awaiting_photos", "shipped"].includes(j.status);
  const rcp = (deal && deal.np_data && deal.np_data.recipient) || {};
  const npDone = j.channel === "offline" ? packDone : !!(deal && (deal.ttn || (rcp.name && (rcp.wh_number || rcp.street_ref))));
  const pk = new Set((j.photos || []).map((p: any) => p.kind));
  const photosDone = pk.has("buckets") && pk.has("parcel");

  const badge = (state: string) => ({ display: "inline-flex", alignItems: "center", justifyContent: "center", minWidth: 24, height: 24, borderRadius: "50%", fontSize: 13, fontWeight: 700, color: "#fff", background: state === "done" ? C.green : state === "lock" ? "#cbd5e1" : C.terra, padding: "0 4px" });
  const Step = ({ n, title, done, locked, hint, children }: any) => (
    <div className="panel" style={{ borderLeft: `4px solid ${done ? C.green : locked ? "#cbd5e1" : C.terra}`, opacity: locked ? 0.6 : 1 }}>
      <div className="label" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: locked ? 0 : 8 }}>
        <span style={badge(done ? "done" : locked ? "lock" : "todo")}>{done ? "✓" : locked ? "🔒" : n}</span> {title}
      </div>
      {locked ? <div className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>{hint}</div> : children}
    </div>
  );

  return (
    <div className="scroll pad fade" style={{ width: "100%" }}>
      <button className="btn btn-light" style={{ marginBottom: 10 }} onClick={onBack}>← {t("Назад к задачам", "Назад до задач")}</button>
      {deal && deal.contact_id ? (
        <div style={{ position: "fixed", top: 68, right: 0, bottom: 12, zIndex: 70, display: "flex", width: chatOpen ? "min(430px, 94vw)" : 22, transition: "width .28s ease", background: "#fff", borderRadius: "14px 0 0 14px", boxShadow: chatOpen ? "-12px 0 30px rgba(15,23,42,.22)" : "-6px 0 16px rgba(99,102,241,.35)", overflow: "hidden" }}>
          <button onClick={() => setChatOpen(!chatOpen)} title={t("Чат с клиентом", "Чат з клієнтом")}
            style={{ width: 22, flexShrink: 0, border: "none", background: "linear-gradient(90deg, #8b5cf6 0%, #3b82f6 100%)", color: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", padding: 0, fontSize: 15, fontWeight: 700, borderRadius: chatOpen ? "14px 0 0 14px" : "14px 0 0 14px", textShadow: "0 1px 2px rgba(15,23,42,.35)" }}>
            {chatOpen ? "›" : "‹"}
          </button>
          {chatOpen && (
            <div className="fade" style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <div style={{ padding: "9px 12px", fontWeight: 700, borderBottom: "1px solid #eef2f7", fontSize: 14, flexShrink: 0 }}>💬 {t("Чат с клиентом", "Чат з клієнтом")}: {j.client}</div>
              <div style={{ flex: 1, overflowY: "auto", padding: 10 }}>
                <ClientChat contact={deal.contact_id} markSeen={false} />
              </div>
            </div>
          )}
        </div>
      ) : null}
      {docOpen && deal ? <KpDoc deal={deal} onClose={() => setDocOpen(false)} /> : null}
      {vkOpen ? <VykraskaDoc data={{ number: j.deal_id, material: j.needs && j.needs.material, color: j.needs && j.needs.color, area: j.needs && j.needs.area, underlay: j.needs && j.needs.underlay, kits: j.kits, client: j.client, phone: j.phone }} onClose={() => setVkOpen(false)} /> : null}
      {msg && <div style={{ position: "sticky", top: 6, zIndex: 50, background: C.green, color: "#fff", padding: "10px 14px", borderRadius: 10, fontWeight: 600, marginBottom: 8 }}>{msg}</div>}
      <div className="panel" style={{ borderLeft: `4px solid ${C.terra}` }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
          <b style={{ fontSize: 17, flex: 1 }}>#{j.deal_id} · {j.client}</b>
          <NakladnaPrint j={j} t={t} style={{ minWidth: 36, height: 32, borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", flexShrink: 0 }} size={17} />
          <button title={t("Печать бланка выкраски", "Друк бланка викраски")} onClick={() => setVkOpen(true)} style={{ width: 36, height: 32, borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><Icon n="palette" size={17} /></button>
        </div>
        <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>📍 {j.city || "—"} · {j.ship || ""}{(deal && deal.ttn) ? " · ТТН " + deal.ttn : ""}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6, fontSize: 13 }}>
          <span className="muted">👤 {t("Ответственный","Відповідальний")}:</span>
          <b>{j.assignee_name || t("не назначен","не призначено")}</b>
          {canReassign && (
            <select value="" onChange={async (e) => { const v = e.target.value; if (v === "") return;
              try { await api.post(`/api/warehouse/jobs/${j.id}/reassign/`, { user_id: Number(v) }); load(); }
              catch (err: any) { alert(err?.response?.data?.detail || t("Не удалось","Не вдалося")); }
            }} style={{ height: 30, border: "1px solid #cbd5e1", borderRadius: 7, fontSize: 12 }}>
              <option value="">{t("Сменить…","Змінити…")}</option>
              <option value="0">↩ {t("В очередь","У чергу")}</option>
              {reStaff.map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          )}
        </div>
      </div>

      <div className="panel" style={{ borderLeft: "4px solid #2563eb" }}>
        <div className="label" style={{ marginBottom: 8 }}>📋 {t("Что отгрузить — ознакомься", "Що відвантажити — ознайомся")}</div>
        {(j.items || []).length > 0 && <div style={{ marginBottom: 9 }}><div className="muted" style={{ fontSize: 11.5, marginBottom: 3 }}>📦 {t("Товары", "Товари")}</div>{(j.items || []).map((it: any, i: number) => <div key={i} style={{ fontSize: 13.5, padding: "2px 0" }}>• {it.name} <b>× {it.qty}</b>{it.weight_kg && it.weight_kg !== "0" && it.weight_kg !== "0.000" ? <span className="muted"> · {it.weight_kg} кг</span> : null}</div>)}</div>}
        {(j.subtasks || []).length > 0 && (j.subtasks).map((s: any) => (
          <div key={"subship" + s.job_id} style={{ marginBottom: 9, background: "#f0fdff", border: "1px solid #cffafe", borderRadius: 10, padding: "8px 11px" }}>
            <div style={{ fontSize: 12.5, fontWeight: 700, color: "#0e7490", marginBottom: 3 }}>↳ 📦 {t("Допродажа", "Допродаж")} #{s.deal_id}{s.title ? " · " + s.title : ""} <span style={{ fontWeight: 400 }}>— {t("упаковать вместе", "спакувати разом")}</span></div>
            {(s.items || []).map((it: any, i: number) => <div key={i} style={{ fontSize: 13, padding: "2px 0", color: "#334155" }}>• {it.name} <b>× {it.qty}</b></div>)}
            {s.kits_n > 0 ? <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>🎨 {t("наборов", "наборів")}: {s.kits_n}</div> : null}
          </div>
        ))}
        {(j.kits || []).length > 0 && <div style={{ marginBottom: 9 }}><div className="muted" style={{ fontSize: 11.5, marginBottom: 3 }}>🎨 {t("Наборы", "Набори")} ({(j.kits || []).length})</div>{(j.kits || []).map((k: any, i: number) => <div key={i} style={{ fontSize: 13.5, padding: "2px 0" }}>• <b>{k.material || "—"}</b> <span className="muted">{k.color}</span>{k.tint ? " · 🎨 " + t("тонировать", "тонувати") : ""}{k.board ? " · " + t("с дощечкой", "з дощечкою") : ""}{k.note ? <span style={{ color: "#0369a1" }}> · 💬 {k.note}</span> : null}</div>)}</div>}
        {Object.keys(j.needs || {}).filter((k) => (j.needs[k] !== "" && j.needs[k] != null && j.needs[k] !== "—" && !k.startsWith("_"))).length > 0 && <div><div className="muted" style={{ fontSize: 11.5, marginBottom: 3 }}>📝 {t("Выявление потребности", "Виявлення потреби")}</div>{Object.entries(j.needs).filter(([k, v]: any) => v !== "" && v != null && v !== "—" && !k.startsWith("_")).map(([k, v]: any) => <div key={k} style={{ fontSize: 12.5, padding: "1px 0", display: "flex", gap: 8 }}><span className="muted" style={{ minWidth: 140, flexShrink: 0 }}>{NEEDS_LBL[k] || k}</span><b>{String(v)}</b></div>)}</div>}
        <RefShots photos={j.ref_photos} t={t} />
        {(j.items || []).length === 0 && (j.kits || []).length === 0 && <div className="muted" style={{ fontSize: 12.5 }}>{t("Позиции не указаны — уточни у менеджера", "Позиції не вказані — уточни у менеджера")}</div>}
      </div>

      <Step n="1" title={t("Тонировка наборов", "Тонування наборів")} done={tintDone}>
        {kits.map((k: any, i: number) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 12px", borderRadius: 10, marginBottom: 6, background: tinted.has(i) ? "#ecfdf5" : "#f8fafc", border: "1px solid " + (tinted.has(i) ? "#a7f3d0" : "#eef2f7") }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <b style={{ fontSize: 14.5 }}>{k.material || "—"} <span className="muted">{k.color}</span></b>
              {k.note ? <div style={{ fontSize: 12.5, color: "#0369a1", marginTop: 2 }}>💬 {k.note}</div> : null}
              <div style={{ display: "flex", gap: 6, marginTop: 3, flexWrap: "wrap" }}>
                {k.tint && <span className="chip" style={{ background: "#fff7ed", color: "#9a3412", fontSize: 10.5 }}>{t("тонировать", "тонувати")}</span>}
                <span className="chip" style={{ background: "#f1f5f9", fontSize: 10.5 }}>{k.board ? t("с дощечкой", "з дощечкою") : t("без дощечки", "без дощечки")}</span>
              </div>
            </div>
            {k.tint && <button className="btn" onClick={() => toggleTint(i)} style={{ background: tinted.has(i) ? C.green : "#f1f5f9", color: tinted.has(i) ? "#fff" : C.slate, fontWeight: 600, minWidth: 120, height: 42 }}>{tinted.has(i) ? "✓ " + t("готово", "готово") : t("затонировать", "затонувати")}</button>}
          </div>
        ))}
        {!hasTint && <div className="muted" style={{ fontSize: 12.5 }}>{t("Тонировка не требуется", "Тонування не потрібне")}</div>}
      </Step>

      <Step n="2" title={t("Пакування", "Пакування")} done={packDone} locked={!tintDone} hint={t("Сначала затонируй все наборы", "Спочатку затонуй усі набори")}>
        <div className="muted" style={{ fontSize: 11.5, marginBottom: 8 }}>{t("Вес считается сам.", "Вага рахується сама.")} {t("Вес", "Вага")}: <b>{j.weight_kg} кг</b></div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={() => setPacked(true)} style={{ flex: 1, height: 46, background: (packDone && j.packed) ? C.green : "#f1f5f9", color: (packDone && j.packed) ? "#fff" : C.slate, fontWeight: 600 }}>{t("Ручная упаковка", "Ручне пакування")}</button>
          <button className="btn" onClick={() => setPacked(false)} style={{ flex: 1, height: 46, background: (packDone && !j.packed) ? C.amber : "#f1f5f9", color: (packDone && !j.packed) ? "#fff" : C.slate, fontWeight: 600 }}>{t("НП контейнер", "НП контейнер")}</button>
        </div>
      </Step>

      {j.channel !== "offline" && (
      <Step n="3" title={t("Новая Почта — заполни все данные", "Нова Пошта — заповни всі дані")} done={npDone} locked={!packDone} hint={t("Сначала упакуй посылку", "Спочатку спакуй посилку")}>
        {deal ? <NPDelivery deal={deal} flash={flash} defaultWeight={j.weight_kg} codReadOnly onReload={() => { loadDeal(j.deal_id); load(); }} /> : <div className="muted">…</div>}
      </Step>)}
      {j.channel === "offline" && (
      <div className="panel" style={{ borderLeft: "4px solid #16a34a", opacity: 0.85 }}><div className="label" style={{ display: "flex", alignItems: "center", gap: 8 }}><span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", minWidth: 24, height: 24, borderRadius: "50%", fontSize: 13, fontWeight: 700, color: "#fff", background: "#16a34a", padding: "0 4px" }}>✓</span> {t("Салон — самовывоз, Нова Пошта не нужна", "Салон — самовивіз, Нова Пошта не потрібна")}</div></div>)}

      <Step n="4" title={t("2 фото — обязательно", "2 фото — обовʼязково")} done={photosDone} locked={!npDone} hint={t("Сначала заполни Новую Почту", "Спочатку заповни Нову Пошту")}>
        <div style={{ display: "flex", gap: 10 }}>
          {([["buckets", t("Ведёрки с наклейкой", "Відерця з наклейкою")], ["parcel", t("Готовая коробка", "Готова коробка")]] as any[]).map(([kind, label]) => (
            <label key={kind} style={{ flex: 1, textAlign: "center", border: "2px dashed " + (pk.has(kind) ? C.green : "#cbd5e1"), borderRadius: 12, padding: "16px 8px", cursor: "pointer", background: pk.has(kind) ? "#ecfdf5" : "#fff" }}>
              <input type="file" accept="image/*" capture="environment" style={{ display: "none" }} onChange={(e) => e.target.files && e.target.files[0] && upload(kind, e.target.files[0])} />
              <div style={{ fontSize: 30 }}>{pk.has(kind) ? "✅" : "📷"}</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>{label}</div>
            </label>
          ))}
        </div>
        {(j.photos || []).length > 0 && <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>{(j.photos || []).map((p: any) => <div key={p.id} style={{ textAlign: "center" }}><PhotoThumb url={p.url} /><div className="muted" style={{ fontSize: 10, marginTop: 2 }}>{p.kind === "buckets" ? t("ведёрки", "відерця") : t("коробка", "коробка")}</div></div>)}</div>}
      </Step>

      <button className="btn btn-light" style={{ width: "100%", marginBottom: 10, color: C.red }} onClick={() => { const dd = prompt(t("Что не так? (ошибка/брак)", "Що не так? (помилка/брак)")); if (dd) api.post("/api/warehouse/errors/", { job: jobId, deal: j.deal_id, source: "manual_staff", kind: "other", description: dd }).then(() => alert(t("Записано, проверит руководитель", "Записано, перевірить керівник"))).catch(() => {}); }}>⚠ {t("Сообщить об ошибке", "Повідомити про помилку")}</button>
      <button className="btn" onClick={ship} disabled={busy || !photosDone} style={{ width: "100%", height: 58, fontSize: 17, fontWeight: 700, background: photosDone ? C.green : "#cbd5e1", color: "#fff", marginBottom: 30 }}>{busy ? "…" : "✅ " + t("Готово — отправлено", "Готово — відправлено")}</button>
    </div>
  );
}

function SalaryView({ t }: any) {
  const [d, setD] = useState<any>(null);
  const [period, setPeriod] = useState("month");
  useEffect(() => { api.get<any>(`/api/warehouse/my-salary/?period=${period}`).then(setD).catch(() => {}); }, [period]);
  const LBL: any = { workday: ["Дни (ставка)", "Дні (ставка)"], shipment_weight: ["Вес отгрузки", "Вага відвантаження"], packing: ["Пакування", "Пакування"], tinting: ["Тонировка", "Тонування"], bonus_initiative: ["Бонус-идея", "Бонус-ідея"], bonus_cleanliness: ["Бонус-чистота", "Бонус-чистота"], error: ["Ошибки", "Помилки"], wrong_material: ["Не тот материал", "Не той матеріал"] };
  if (!d) return <div className="spin">…</div>;
  return (
    <div>
      <div style={{ display: "flex", gap: 4, marginBottom: 12, background: "#f1f5f9", borderRadius: 9, padding: 3 }}>
        {([["week", "Неделя", "Тиждень"], ["month", "Месяц", "Місяць"], ["quarter", "Квартал", "Квартал"], ["all", "Всё", "Все"]] as any[]).map(([p, ru, uk]) => (
          <button key={p} onClick={() => setPeriod(p)} style={{ flex: 1, fontSize: 12.5, padding: "7px", borderRadius: 7, border: "none", cursor: "pointer", background: period === p ? C.terra : "transparent", color: period === p ? "#fff" : C.slate, fontWeight: 600 }}>{t(ru, uk)}</button>
        ))}
      </div>
      <div className="panel" style={{ textAlign: "center", padding: "22px", background: "linear-gradient(135deg,#ecfdf5,#fff)" }}>
        <div className="muted" style={{ fontSize: 13 }}>{t("Заработано за период", "Зароблено за період")}</div>
        <div style={{ fontSize: 48, fontWeight: 800, color: C.green }}>{f(d.total)} ₴</div>
      </div>
      <div className="panel">
        {(d.lines || []).map((l: any) => (
          <div key={l.op} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid #f1f5f9" }}>
            <span style={{ fontSize: 13.5 }}>{t(...(LBL[l.op] || [l.op, l.op]))} <span className="muted">×{l.count}</span></span>
            <b style={{ color: Number(l.amount) < 0 ? C.red : "#0f172a" }}>{f(l.amount)} ₴</b>
          </div>
        ))}
        {(d.lines || []).length === 0 && <div className="muted" style={{ fontSize: 13 }}>{t("Пока пусто", "Поки порожньо")}</div>}
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
        <div className="panel" style={{ flex: 1, textAlign: "center", margin: 0 }}><div style={{ fontSize: 24, fontWeight: 800 }}>{d.shipments}</div><div className="muted" style={{ fontSize: 11 }}>{t("отгрузок", "відвантажень")}</div></div>
        <div className="panel" style={{ flex: 1, textAlign: "center", margin: 0 }}><div style={{ fontSize: 24, fontWeight: 800 }}>{d.tintings}</div><div className="muted" style={{ fontSize: 11 }}>{t("тонировок", "тонувань")}</div></div>
      </div>
      <div className="muted" style={{ fontSize: 11, textAlign: "center", marginTop: 8 }}>{t("Ставки управляются в финмодели", "Ставки керуються у фінмоделі")}</div>
    </div>
  );
}

function ShippedFilter({ staff, onOpen, t }: any) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [emp, setEmp] = useState("");
  const [q, setQ] = useState("");
  const [opened, setOpened] = useState(false);
  const load = () => {
    setRows(null);
    const p = new URLSearchParams();
    if (from) p.set("from", from);
    if (to) p.set("to", to);
    if (emp) p.set("employee", emp);
    if (q.trim()) p.set("q", q.trim());
    api.get<any>(`/api/warehouse/shipments/?${p.toString()}`).then((d) => setRows(d.rows || [])).catch(() => setRows([]));
  };
  useEffect(() => { if (opened && rows === null) load(); /* eslint-disable-next-line */ }, [opened]);
  return (
    <details style={{ marginBottom: 14 }} onToggle={(e: any) => setOpened(e.currentTarget.open)}>
      <summary style={{ cursor: "pointer", fontSize: 13.5, fontWeight: 700 }}>🔎 {t("Отгрузки — поиск и период", "Відвантаження — пошук і період")}</summary>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", margin: "10px 0" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} placeholder={t("🔎 № сделки / клиент", "🔎 № угоди / клієнт")} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 10px", fontSize: 13, flex: 1, minWidth: 150 }} />
        <select value={emp} onChange={(e) => setEmp(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 12.5 }}><option value="">{t("Все сотрудники", "Усі співробітники")}</option>{(staff || []).map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}</select>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 6px", fontSize: 12 }} />
        <span className="muted">—</span>
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} style={{ height: 32, border: "1px solid #cbd5e1", borderRadius: 8, padding: "0 6px", fontSize: 12 }} />
        <button className="btn btn-primary" style={{ height: 32, fontSize: 13 }} onClick={load}>{t("Показать", "Показати")}</button>
      </div>
      {rows === null ? <div className="muted" style={{ fontSize: 12.5 }}>{t("Загрузка…", "Завантаження…")}</div> : rows.length === 0 ? <div className="muted" style={{ fontSize: 12.5 }}>{t("Ничего не найдено", "Нічого не знайдено")}</div> : (
        <><div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>{t("Найдено", "Знайдено")}: {rows.length}</div><div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{rows.map((j: any) => <JobCard key={"h" + j.id} j={j} t={t} onClick={() => onOpen(j.id)} action={<span />} />)}</div></>
      )}
    </details>
  );
}

function DashboardView({ t }: any) {
  const [d, setD] = useState<any>(null);
  const [period, setPeriod] = useState("month");
  useEffect(() => { api.get<any>(`/api/warehouse/dashboard/?period=${period}`).then(setD).catch(() => {}); }, [period]);
  if (!d) return <div className="spin">…</div>;
  const cols: any[] = [["workday", t("Ставка", "Ставка")], ["shipment_weight", t("Вес₴", "Вага₴")], ["packing", t("Упак.", "Упак.")], ["tinting", t("Тонир.", "Тонув.")], ["bonus_initiative", t("Бонус", "Бонус")]];
  return (
    <div>
      <div style={{ display: "flex", gap: 4, marginBottom: 12, background: "#f1f5f9", borderRadius: 9, padding: 3, maxWidth: 440 }}>
        {([["week", "Неделя", "Тиждень"], ["month", "Месяц", "Місяць"], ["quarter", "Квартал", "Квартал"], ["all", "Всё", "Все"]] as any[]).map(([p, ru, uk]) => <button key={p} onClick={() => setPeriod(p)} style={{ flex: 1, fontSize: 12.5, padding: "7px", borderRadius: 7, border: "none", cursor: "pointer", background: period === p ? C.terra : "transparent", color: period === p ? "#fff" : C.slate, fontWeight: 600 }}>{t(ru, uk)}</button>)}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12, marginBottom: 14 }}>
        {([["offline", "🏪", t("Офлайн (покрытия/салон)", "Офлайн (покриття/салон)"), C.terra], ["online", "🌐", t("Онлайн (тест+основной)", "Онлайн (тест+основний)"), C.blue]] as any[]).map(([k, e, lbl, col]) => {
          const o = d.onoff[k] || { count: 0, weight: 0, value: 0 };
          return <div key={k} className="panel" style={{ margin: 0, borderLeft: `4px solid ${col}` }}>
            <div style={{ fontSize: 13, fontWeight: 700 }}>{e} {lbl}</div>
            <div style={{ display: "flex", gap: 18, marginTop: 6 }}>
              <div><div style={{ fontSize: 22, fontWeight: 800 }}>{o.count}</div><div className="muted" style={{ fontSize: 11 }}>{t("отгрузок", "відвантажень")}</div></div>
              <div><div style={{ fontSize: 22, fontWeight: 800 }}>{f(o.weight)}</div><div className="muted" style={{ fontSize: 11 }}>кг</div></div>
              <div><div style={{ fontSize: 22, fontWeight: 800 }}>{f(o.value)}</div><div className="muted" style={{ fontSize: 11 }}>₴</div></div>
            </div>
          </div>;
        })}
      </div>
      <div className="panel" style={{ overflowX: "auto", padding: 0, margin: 0 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead><tr style={{ background: "#f8fafc", textAlign: "left" }}>
            <th style={{ padding: "10px 12px" }}>{t("Сотрудник", "Співробітник")}</th>
            <th style={{ padding: "10px 8px", textAlign: "center" }}>{t("Отгр.", "Відв.")}</th>
            <th style={{ padding: "10px 8px", textAlign: "center" }}>{t("Вес", "Вага")}</th>
            <th style={{ padding: "10px 8px", textAlign: "center" }}>{t("Тонир.", "Тонув.")}</th>
            {cols.map(([k, lbl]: any) => <th key={k} style={{ padding: "10px 8px", textAlign: "right" }}>{lbl}</th>)}
            <th style={{ padding: "10px 8px", textAlign: "right", color: C.red }}>{t("Удерж.", "Утрим.")}</th>
            <th style={{ padding: "10px 12px", textAlign: "right" }}>{t("ИТОГО", "РАЗОМ")}</th>
          </tr></thead>
          <tbody>
            {d.rows.map((r: any) => (
              <tr key={r.id} style={{ borderTop: "1px solid #f1f5f9" }}>
                <td style={{ padding: "10px 12px", fontWeight: 600 }}>{r.name}</td>
                <td style={{ padding: "10px 8px", textAlign: "center" }}>{r.shipments}</td>
                <td style={{ padding: "10px 8px", textAlign: "center" }}>{f(r.weight)}</td>
                <td style={{ padding: "10px 8px", textAlign: "center" }}>{r.tintings}</td>
                {cols.map(([k]: any) => <td key={k} style={{ padding: "10px 8px", textAlign: "right" }}>{f(r.by[k])}</td>)}
                <td style={{ padding: "10px 8px", textAlign: "right", color: r.deductions ? C.red : "#cbd5e1" }}>{r.deductions ? "-" + f(r.deductions) : "—"}</td>
                <td style={{ padding: "10px 12px", textAlign: "right", fontWeight: 800, color: C.green }}>{f(r.total)} ₴</td>
              </tr>
            ))}
            {d.rows.length === 0 && <tr><td colSpan={10} style={{ padding: 16, color: "#94a3b8" }}>{t("Нет данных за период", "Немає даних за період")}</td></tr>}
          </tbody>
          {d.rows.length > 0 && <tfoot><tr style={{ borderTop: "2px solid #e2e8f0", fontWeight: 700, background: "#f8fafc" }}>
            <td style={{ padding: "10px 12px" }}>{t("КОМАНДА", "КОМАНДА")} ({d.team.people})</td>
            <td style={{ padding: "10px 8px", textAlign: "center" }}>{d.team.shipments}</td>
            <td style={{ padding: "10px 8px", textAlign: "center" }}>{f(d.team.weight)}</td>
            <td style={{ padding: "10px 8px", textAlign: "center" }}>{d.team.tintings}</td>
            <td colSpan={cols.length + 1}></td>
            <td style={{ padding: "10px 12px", textAlign: "right", color: C.green }}>{f(d.team.total)} ₴</td>
          </tr></tfoot>}
        </table>
      </div>
      <div className="muted" style={{ fontSize: 11, textAlign: "center", marginTop: 8 }}>{t("Только для руководителя. Ставки — в финмодели.", "Тільки для керівника. Ставки — у фінмоделі.")}</div>
    </div>
  );
}

function ControlView({ t }: any) {
  const [er, setEr] = useState<any[]>([]);
  const [id, setId] = useState<any[]>([]);
  const load = () => { api.get<any[]>("/api/warehouse/errors/").then(setEr).catch(() => {}); api.get<any[]>("/api/warehouse/ideas/").then(setId).catch(() => {}); };
  useEffect(load, []);
  const confirmErr = (e: any) => { const dd = prompt(t("Сумма удержания, ₴", "Сума утримання, ₴"), e.deduction); if (dd === null) return; api.post(`/api/warehouse/errors/${e.id}/confirm/`, { deduction: dd }).then(load).catch(() => {}); };
  const rejectErr = (e: any) => api.post(`/api/warehouse/errors/${e.id}/confirm/`, { action: "reject" }).then(load).catch(() => {});
  const award = (i: any) => { const a = prompt(t("Премия за идею, ₴", "Премія за ідею, ₴"), "200"); if (a === null) return; api.post(`/api/warehouse/ideas/${i.id}/award/`, { status: "accepted", award: a }).then(load).catch(() => {}); };
  const pend = er.filter((e) => e.status === "suggested");
  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>{t("Для руководителя: подтверждай удержания и премируй идеи.", "Для керівника: підтверджуй утримання і преміюй ідеї.")}</div>
      <div className="label" style={{ marginBottom: 8 }}>⚠ {t("Ошибки на подтверждение", "Помилки на підтвердження")}</div>
      {pend.length === 0 && <div className="muted" style={{ fontSize: 13 }}>{t("Нет", "Немає")}</div>}
      {pend.map((e) => (
        <div key={e.id} className="panel" style={{ marginBottom: 8 }}>
          <b>{e.kind}</b> · {e.blamed || "—"}
          <div className="muted" style={{ fontSize: 12 }}>{e.desc}{e.deal ? " · угода #" + e.deal : ""}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button className="btn" style={{ background: C.red, color: "#fff", flex: 1 }} onClick={() => confirmErr(e)}>{t("Удержать", "Утримати")}</button>
            <button className="btn btn-light" style={{ flex: 1 }} onClick={() => rejectErr(e)}>{t("Отклонить", "Відхилити")}</button>
          </div>
        </div>
      ))}
      <div className="label" style={{ margin: "16px 0 8px" }}>💡 {t("Идеи сотрудников", "Ідеї співробітників")}</div>
      {id.length === 0 && <div className="muted" style={{ fontSize: 13 }}>{t("Нет", "Немає")}</div>}
      {id.map((i) => (
        <div key={i.id} className="panel" style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 13.5 }}>{i.text}</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>{i.author} · {i.status}{Number(i.award) > 0 ? " · +" + i.award + "₴" : ""}</div>
          {i.status === "new" && <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={() => award(i)}>{t("Премировать", "Преміювати")}</button>}
        </div>
      ))}
    </div>
  );
}

// ── Кабінет складу: форма розливу + список останніх розливів/списань (з відміною/видаленням) ──
function RepackPage({ t }: { t: any }) {
  const [docs, setDocs] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState<number | null>(null);
  const load = () => { setBusy(true); api.get<any>("/api/stock-documents/?kinds=writeoff,repack&page_size=20").then((r: any) => setDocs(r.results || r)).catch(() => setDocs([])).finally(() => setBusy(false)); };
  useEffect(() => { load(); }, []);
  const del = async (id: number, kind: string) => {
    const nm = kind === "repack" ? t("этот розлив", "цей розлив") : t("это списание", "це списання");
    if (!confirm(t("Удалить " + nm + "? Движения откатятся, остаток пересчитается. Отменить нельзя.", "Видалити " + nm + "? Рухи відкотяться, залишок перерахується. Скасувати не можна."))) return;
    try { await api.del(`/api/stock-documents/${id}/`); load(); } catch (e: any) { alert(e?.response?.data?.detail || t("Не удалось удалить", "Не вдалося видалити")); }
  };
  const toggle = async (id: number, post: boolean) => {
    if (!post && !confirm(t("Отменить проведение? Товар вернётся/уйдёт с остатка.", "Скасувати проведення? Товар повернеться/піде із залишку."))) return;
    try { await api.post(`/api/stock-documents/${id}/${post ? "post" : "unpost"}/`, {}); load(); } catch { alert(t("Нет доступа (нужно «Редактировать склад»)", "Немає доступу (потрібне «Редагувати склад»)")); }
  };
  return (
    <div style={{ maxWidth: 720 }}>
      <RepackForm onDone={load} />
      <div style={{ marginTop: 18 }}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>{t("Последние розливы и списания", "Останні розливи та списання")}</div>
        {busy ? <div className="muted">{t("Загрузка…", "Завантаження…")}</div> : docs.length === 0 ? <div className="muted" style={{ fontSize: 13 }}>{t("Пока пусто", "Поки порожньо")}</div> : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 13 }}>
              <thead><tr><th style={{ textAlign: "left" }}>{t("Тип", "Тип")}</th><th style={{ textAlign: "left" }}>{t("Дата", "Дата")}</th><th style={{ textAlign: "left" }}>{t("Что", "Що")}</th><th style={{ textAlign: "center" }}>{t("Статус", "Статус")}</th><th></th></tr></thead>
              <tbody>{docs.map((d: any) => (
                <tr key={d.id} onClick={() => setSel(d.id)} style={{ cursor: "pointer" }} title={t("Открыть — посмотреть что списано и оприходовано", "Відкрити — подивитись що списано і оприбутковано")}>
                  <td>{d.kind === "repack" ? "🧪 " + t("Розлив", "Розлив") : "🗑 " + t("Списание", "Списання")}</td>
                  <td className="muted">{(d.doc_date || d.created_at || "").slice(0, 10)}</td>
                  <td className="muted" style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={d.comment}>{d.comment || "—"}</td>
                  <td style={{ textAlign: "center" }}><span style={{ padding: "2px 8px", borderRadius: 6, fontSize: 12, fontWeight: 600, background: d.posted ? "#dcfce7" : "#fef3c7", color: d.posted ? "#166534" : "#92400e" }}>{d.posted ? t("Проведён", "Проведено") : t("Черновик", "Чернетка")}</span></td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }} onClick={(e) => e.stopPropagation()}>
                    <button className="btn btn-light" style={{ padding: "2px 8px", fontSize: 11.5 }} onClick={() => toggle(d.id, !d.posted)}>{d.posted ? t("Отменить", "Скасувати") : t("Провести", "Провести")}</button>
                    <button className="btn btn-light" style={{ padding: "2px 8px", fontSize: 11.5, color: "#dc2626", marginLeft: 4 }} onClick={() => del(d.id, d.kind)}>{t("Удалить", "Видалити")}</button>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
      {sel && <RepackDocModal id={sel} onClose={() => setSel(null)} />}
    </div>
  );
}
