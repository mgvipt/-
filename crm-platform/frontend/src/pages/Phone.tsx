/* Телефонія Wallcov-CRM — власний FreePBX (незалежно від Бітрикса).
 * Дві окремі картки: ВХІДНІ та ВИХІДНІ. Дзвінки тягнуться з нашого SIP-шлюзу. */
import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { api, Paginated } from "../api";
import { useLang } from "../i18n";
import { Icon } from "../Icon";

interface Call {
  id: number; direction: string; direction_display: string;
  from_number: string; to_number: string;
  contact?: number; contact_name?: string; manager_name?: string;
  duration: number; recording_url: string; recording_file?: string;
  extension?: string; disposition?: string; started_at?: string; created_at: string; line?: string; transcript?: string;
}
interface Stats { total: number; recorded: number; missed: number; avg_seconds: number; }

function dur(s: number) { return s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "—"; }
function when(c: Call) {
  const d = c.started_at || c.created_at;
  return d ? new Date(d).toLocaleString("uk", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
}

function LineBalances({ t }: any) {
  const [lines, setLines] = useState<any[]>([]);
  const { can } = useAuth();
  function load() { api.get<any>("/api/telephony/lines/").then(setLines).catch(() => {}); }
  useEffect(() => { load(); }, []);
  async function setBal(l: any) {
    const v = prompt(t("Текущий баланс линии «", "Поточний баланс лінії «") + l.name + "», грн:", String(l.balance));
    if (v == null) return;
    try { await api.patch("/api/telephony/lines/", { id: l.id, balance: Number(v.replace(",", ".")) }); load(); }
    catch { alert(t("Баланс может вписывать только администратор", "Баланс може вписувати лише адміністратор")); }
  }
  if (!lines.length) return null;
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="label" style={{ marginBottom: 6 }}>{t("Баланс линий (для контроля оплаты)", "Баланс ліній (для контролю оплати)")}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px,1fr))", gap: 12 }}>
        {lines.map((l: any) => (
          <div key={l.id} className="panel" style={{ margin: 0, borderLeft: "4px solid " + (l.low ? "#dc2626" : "#16a34a") }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}><Icon n="📡" size={15} /><b>{l.name}</b><span className="muted" style={{ fontSize: 12 }}>{l.number}</span></div>
            <div style={{ fontSize: 26, fontWeight: 800, color: l.low ? "#dc2626" : "#0f172a", marginTop: 4 }}>{Number(l.balance).toFixed(2)} ₴</div>
            {l.low && <div style={{ color: "#dc2626", fontSize: 12, fontWeight: 600 }}>⚠ {t("Мало — пополни!", "Мало — поповни!")}</div>}
            <div style={{ fontSize: 12.5, fontWeight: 700, marginTop: 3, color: l.busy ? "#dc2626" : "#16a34a" }}>{l.busy ? t("🔴 Линия занята (идёт звонок)", "🔴 Лінія зайнята (йде дзвінок)") : t("🟢 Свободна", "🟢 Вільна")}</div>
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{l.balance_at ? t("Обновлено: ", "Оновлено: ") + new Date(l.balance_at).toLocaleString("ru-RU") : t("Баланс ещё не вносили", "Баланс ще не вносили")}</div>
            {can && can("roles.manage") && <button className="btn btn-light" style={{ fontSize: 12, marginTop: 6, padding: "3px 10px" }} onClick={() => setBal(l)}>✎ {t("Вписать баланс", "Вписати баланс")}</button>}
          </div>
        ))}
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{t("Баланс вводится вручную: проверь на телефоне (Киевстар *111#, Vodafone *101#, lifecell *111#) и впиши сюда. Красный = пора пополнить.", "Баланс вводиться вручну: перевір на телефоні (Київстар *111#, Vodafone *101#, lifecell *111#) і впиши сюди. Червоний = час поповнити.")}</div>
    </div>
  );
}

function CallQueuePanel({ t }: any) {
  const [d, setD] = useState<any>(null);
  const [addId, setAddId] = useState("");
  const load = () => api.get<any>("/api/telephony/queue/").then(setD).catch(() => {});
  useEffect(() => { load(); }, []);
  if (!d) return null;
  const admin = d.can_manage;
  const cfg = d.config;
  const act = (body: any) => api.post<any>("/api/telephony/queue/", body).then(setD).catch(() => alert(t("Нет прав", "Немає прав")));
  const move = (uid: number, dir: number) => {
    const ids = d.members.map((m: any) => m.user_id);
    const i = ids.indexOf(uid), j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    act({ action: "reorder", order: ids });
  };
  const btn: any = { width: 26, height: 26, borderRadius: 6, border: "1px solid #e2e8f0", background: "#fff", cursor: "pointer", fontSize: 13 };
  return (
    <div className="panel" style={{ margin: "0 0 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
        <div className="label" style={{ margin: 0 }}>📞 {t("Очередь входящих звонков", "Черга вхідних дзвінків")}</div>
        {admin && <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 7, fontSize: 12.5, cursor: "pointer" }}>
          <span className={"toggle" + (cfg.active ? " on" : "")} onClick={() => act({ action: "config", active: !cfg.active })} />
          {cfg.active ? t("Очередь включена", "Черга увімкнена") : t("Очередь выключена", "Черга вимкнена")}
        </label>}
      </div>

      {d.members.length === 0
        ? <div className="muted" style={{ fontSize: 12.5, marginBottom: 8 }}>{t("Пусто. Добавь сотрудников — им будут поступать входящие по очереди.", "Порожньо. Додай співробітників — їм надходитимуть вхідні по черзі.")}</div>
        : <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {d.members.map((m: any, i: number) => (
            <div key={m.user_id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", border: "1px solid #e8edf3", borderRadius: 9, opacity: m.enabled ? 1 : 0.5 }}>
              <b style={{ width: 20, textAlign: "center", color: "#64748b" }}>{i + 1}</b>
              <span style={{ fontWeight: 600, flex: 1, minWidth: 0 }}>{m.name}</span>
              <span title={t("Внутренний номер", "Внутрішній номер")} style={{ fontSize: 11.5, background: "#eef2ff", color: "#4338ca", borderRadius: 6, padding: "2px 7px", fontWeight: 700 }}>#{m.extension || "—"}</span>
              <span title={m.on_shift ? t("На смене", "На зміні") : t("День не начат", "День не почато")} style={{ fontSize: 12 }}>{m.on_shift ? "🟢" : "⚪"}</span>
              {admin && <>
                <input type="number" min={5} max={120} defaultValue={m.ring_seconds} title={t("Секунд дозвона", "Секунд дозвону")}
                  onBlur={(e) => act({ action: "ring_seconds", user_id: m.user_id, value: e.target.value })}
                  style={{ width: 46, height: 26, borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12, textAlign: "center" }} />
                <button onClick={() => move(m.user_id, -1)} disabled={i === 0} style={btn}>↑</button>
                <button onClick={() => move(m.user_id, 1)} disabled={i === d.members.length - 1} style={btn}>↓</button>
                <span className={"toggle" + (m.enabled ? " on" : "")} onClick={() => act({ action: "toggle", user_id: m.user_id })} />
                <button onClick={() => { if (confirm(t("Убрать из очереди?", "Прибрати з черги?"))) act({ action: "remove", user_id: m.user_id }); }} style={{ ...btn, color: "#dc2626" }}>✕</button>
              </>}
            </div>
          ))}
        </div>}

      {admin && <>
        <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
          <select value={addId} onChange={(e) => setAddId(e.target.value)} style={{ flex: 1, minWidth: 160, height: 34, borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }}>
            <option value="">{t("+ Добавить сотрудника…", "+ Додати співробітника…")}</option>
            {d.candidates.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="btn btn-primary" disabled={!addId} onClick={() => { act({ action: "add", user_id: Number(addId) }); setAddId(""); }}>{t("Добавить", "Додати")}</button>
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12.5, cursor: "pointer" }}>
            <span className={"toggle" + (cfg.on_shift_only ? " on" : "")} onClick={() => act({ action: "config", on_shift_only: !cfg.on_shift_only })} />
            {t("Звонить только тем, кто начал рабочий день", "Дзвонити лише тим, хто почав робочий день")}
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12.5 }}>
            {t("Как звонить:", "Як дзвонити:")}
            <select value={cfg.strategy} onChange={(e) => act({ action: "config", strategy: e.target.value })} style={{ height: 30, borderRadius: 7, border: "1px solid #cbd5e1", fontSize: 12.5 }}>
              <option value="sequential">{t("По очереди (один за другим)", "По черзі (один за одним)")}</option>
              <option value="ringall">{t("Всем сразу", "Усім одразу")}</option>
            </select>
          </label>
        </div>
      </>}

      <div className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
        🟢 {t("на смене", "на зміні")} · ⚪ {t("день не начат — звонки не идут", "день не почато — дзвінки не йдуть")}. {t("Кто не в очереди — звонки не получает. Если никто не взял — звонок фиксируется как пропущенный.", "Хто не в черзі — дзвінків не отримує. Якщо ніхто не взяв — дзвінок фіксується як пропущений.")}
      </div>
    </div>
  );
}

export default function Phone() {
  const [calls, setCalls] = useState<Call[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const nav = useNavigate();
  const { t } = useLang();

  function load() {
    api.get<Paginated<Call>>("/api/calls/?page_size=300").then((d) => setCalls(d.results)).catch(() => {});
    api.get<Stats>("/api/calls/stats/").then(setStats).catch(() => {});
  }
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);

  const incoming = calls.filter((c) => c.direction === "in" || c.direction === "missed");
  const outgoing = calls.filter((c) => c.direction === "out");

  // ── одна картка дзвінка ──
  function Row({ c }: { c: Call }) {
    const missed = c.direction === "missed";
    const [open, setOpen] = useState(false);
    const [rate, setRate] = useState(1);
    const aRef = useRef<HTMLAudioElement>(null);
    useEffect(() => { if (aRef.current) aRef.current.playbackRate = rate; });
    return (
      <div style={{ borderBottom: "1px solid #f1f5f9" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px" }}>
          <div style={{ fontSize: 18, width: 22, textAlign: "center" }}>
            <Icon n={c.direction === "out" ? "📤" : missed ? "📵" : "📥"} size={18} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 13.5, color: missed ? "#dc2626" : "#1e293b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {c.contact ? (
                <a onClick={() => nav(`/clients/${c.contact}`)} style={{ color: "var(--brand,#C67D5F)", cursor: "pointer" }}>{c.contact_name}</a>
              ) : (c.contact_name || (c.direction === "out" ? c.to_number : c.from_number) || "—")}
            </div>
            <div className="muted" style={{ fontSize: 11.5 }}>
              {c.direction === "out" ? c.to_number : c.from_number}{c.manager_name ? ` · ${c.manager_name}` : ""}
            </div>
            {c.line && <div style={{ fontSize: 10.5, color: "#7c5cff", marginTop: 1 }}><Icon n="📡" size={12} /> {c.line}</div>}
          </div>
          <div style={{ textAlign: "right", fontSize: 11.5 }}>
            <div className="muted">{when(c)}</div>
            <div style={{ color: missed ? "#dc2626" : "#64748b" }}>{missed ? t("пропущенный","пропущений") : dur(c.duration)}</div>
          </div>
          {c.recording_url
            ? <button onClick={() => setOpen((o) => !o)} title={t("Прослушать","Прослухати")} style={{ border: "none", width: 30, height: 30, borderRadius: 8, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", background: open ? "#C67D5F" : "#eff6ff", color: open ? "#fff" : "#2563eb" }}><Icon n={open ? "pause" : "play"} size={15} /></button>
            : c.recording_file ? <span title={t("Запись есть на сервере","Запис є на сервері")} style={{ color: "#94a3b8", fontSize: 14 }}><Icon n="🎙" size={14} /></span>
            : <span style={{ width: 16 }} />}
        </div>
        {open && c.recording_url && (
          <div style={{ padding: "0 12px 10px 44px", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <audio ref={aRef} src={c.recording_url} controls autoPlay style={{ height: 34, flex: "1 1 220px", minWidth: 0 }} />
            <div style={{ display: "flex", gap: 3 }}>
              {[1, 1.5, 2].map((s) => <button key={s} onClick={() => setRate(s)} style={{ fontSize: 11, fontWeight: rate === s ? 700 : 500, padding: "3px 8px", borderRadius: 6, cursor: "pointer", border: "1px solid #e2e8f0", background: rate === s ? "#C67D5F" : "#fff", color: rate === s ? "#fff" : "#475569" }}>{s}×</button>)}
            </div>
            {c.transcript && (
              <div style={{ flexBasis: "100%", marginTop: 4, fontSize: 12, lineHeight: 1.55, maxHeight: 220, overflowY: "auto", background: "#f8fafc", borderRadius: 8, padding: "8px 10px" }}>
                {c.transcript.split("\n").map((ln, i) => {
                  const mgr = ln.startsWith("МЕНЕДЖЕР:"); const cl = ln.startsWith("КЛІЄНТ:");
                  const body = (mgr || cl) ? ln.slice(ln.indexOf(":") + 1).trim() : ln;
                  return <div key={i} style={{ marginBottom: 3 }}>{(mgr || cl) && <b style={{ color: mgr ? "#16a34a" : "#2563eb" }}>{mgr ? t("Менеджер","Менеджер") : t("Клиент","Клієнт")}: </b>}{body}</div>;
                })}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── колонка (вхідні / вихідні) ──
  function Column({ title, icon, color, list }: { title: string; icon: string; color: string; list: Call[] }) {
    return (
      <div className="panel" style={{ margin: 0, padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "12px 14px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 8, background: color + "14" }}>
          <span style={{ fontSize: 18 }}><Icon n={icon} size={18} /></span>
          <b style={{ fontSize: 15 }}>{title}</b>
          <span className="chip" style={{ background: color, marginLeft: "auto" }}>{list.length}</span>
        </div>
        <div style={{ maxHeight: "calc(100vh - 250px)", overflowY: "auto" }}>
          {list.length === 0
            ? <div className="muted" style={{ padding: 18, fontSize: 13 }}>{t("Пока пусто.","Поки порожньо.")}</div>
            : list.map((c) => <Row key={c.id} c={c} />)}
        </div>
      </div>
    );
  }

  return (
    <div className="scroll pad fade">
      <h2 style={{ margin: "0 0 4px" }}><Icon n="📞" size={22} /> {t("Телефония","Телефонія")}</h2>
      <div className="muted" style={{ fontSize: 13, marginBottom: 14 }}>{t("Собственный SIP-шлюз на нашем сервере (независимо от Битрикса). Звонки и записи — наши.","Власний SIP-шлюз на нашому сервері (незалежно від Бітрикса). Дзвінки і записи — наші.")}</div>

      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px,1fr))", gap: 12, marginBottom: 16 }}>
          {[[t("Всего","Всього"), stats.total], [t("С записью","Із записом"), stats.recorded], [t("Пропущенные","Пропущені"), stats.missed], [t("Ср. длительность","Сер. тривалість"), dur(stats.avg_seconds)]].map(([lbl, v]) => (
            <div key={lbl} className="panel" style={{ margin: 0 }}><div className="muted" style={{ fontSize: 12 }}>{lbl}</div><div style={{ fontSize: 24, fontWeight: 700 }}>{v}</div></div>
          ))}
        </div>
      )}

      <LineBalances t={t} />
      <CallQueuePanel t={t} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px,1fr))", gap: 14, alignItems: "start" }}>
        <Column title={t("Входящие","Вхідні")} icon="📥" color="#16a34a" list={incoming} />
        <Column title={t("Исходящие","Вихідні")} icon="📤" color="#3b82f6" list={outgoing} />
      </div>

      <div className="note" style={{ marginTop: 14 }}><Icon n="💡" size={15} /> {t("Журнал обновляется сам каждые 30 сек. Клик на имя клиента → его карточка. Дальше подключим звонок по клику и прослушивание записи прямо тут.","Журнал оновлюється сам кожні 30 сек. Клік на імʼя клієнта → його картка. Далі підключимо дзвінок по кліку і прослуховування запису прямо тут.")}</div>
    </div>
  );
}
