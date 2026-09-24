/* Розділ «Контент-завод» (24.09.2026, етап 0). Доступ — лише власник або право content_factory.access.
 * Працює: «Студія» (план і лічильники) і «Сторінки» (наші сторінки, конкуренти, натхнення в IG / TikTok / YouTube / Telegram).
 * Етап 1 (24.09): «Питання клієнтів» — нічний розбір питань у теми, з лімітом витрат (вмикає лише власник).
 * Інші вкладки — наступні етапи; показують, що там буде. Дані: /api/content-factory/*.
 * Усі компоненти — на рівні модуля (не всередині інших), щоб поля вводу не втрачали фокус. */
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";

type Channel = {
  id: number; platform: string; platform_display: string; handle: string; url: string; title: string;
  role: string; role_display: string; note: string; is_active: boolean; created_at: string;
};
type ChannelList = { results: Channel[]; roles: [string, string][]; platforms: [string, string][] };
type Overview = { channels_total: number; by_role: Record<string, number>; by_platform: Record<string, number> };
type Topic = {
  id: number; title: string; material: string; status: string; status_display: string; count_period: number;
  count_total: number; channels: Record<string, number>; examples: string[]; kb: { id: number; title: string } | null;
  last_seen: string | null;
};
type QSettings = {
  enabled: boolean; model: string; models: [string, string][]; monthly_budget_usd: number; spent_month_usd: number;
  min_new: number; last_run_at: string | null; last_run_note: string;
  pending: { questions: number; estimate_usd: number } | null;
};
type QData = { days: number; topics: Topic[]; statuses: [string, string][]; settings: QSettings };

type Section = { id: string; label: string; stage: number; group?: string; live?: boolean; what?: string[] };
const SECTIONS: Section[] = [
  { id: "studio", label: "Студія", stage: 0, live: true },
  { id: "channels", label: "Сторінки", stage: 0, live: true },
  { id: "questions", label: "Питання клієнтів", stage: 1, group: "Сировина", live: true, what: [
    "Щоночі ШІ групує вхідні з усіх каналів (Instagram, TikTok, Viber, Telegram, WhatsApp) у теми",
    "Біля теми — скільки разів спитали, чи є відповідь у базі знань, які є фото й відео",
    "Одна кнопка: зробити з теми рилс, карусель або пост у Telegram"] },
  { id: "telegram", label: "Telegram-автопілот", stage: 2, group: "Сировина", what: [
    "Щодня пост: питання дня → коротка відповідь з бази знань → 2–3 реальні фото → посилання на підбір",
    "Перші 2 тижні — через вашу кнопку «схвалити», далі повністю автоматично",
    "Посилання з міткою — CRM рахує ліди з каналу"] },
  { id: "analyst", label: "Аналітик", stage: 3, group: "Аналітика", what: [
    "Аналізує сторінки з вкладки «Сторінки»: наші й конкурентів",
    "Щотижня звіт: що спрацювало, що ні, і 5 ідей на тиждень",
    "Окремо — які ролики принесли переписки та оплати"] },
  { id: "feed", label: "Стрічка рекомендацій", stage: 3, group: "Аналітика", what: [
    "Вірусні ролики ніші з фільтрами: соцмережа, період, тривалість, формат, хук",
    "Кнопка «зробити з наших» — той самий прийом, але ваша фактура з ваших нарізок",
    "Вибране одразу в план"] },
  { id: "sources", label: "Вихідники відео", stage: 4, group: "Виробництво", what: [
    "Завантажуєте нарізки як є — без сценарію й дублів",
    "ШІ розмічає кожну сцену: матеріал, колір, етап (нанесення, блік, готова стіна), світло",
    "Пошук сцен: «Галатея, крупно, блік»"] },
  { id: "reels", label: "Рилси", stage: 5, group: "Виробництво", what: [
    "Сценарій з питання клієнтів → добір кадрів з ваших нарізок → монтаж 9:16 → субтитри → голос",
    "ШІ-кадри лише для фону; стіна в кадрі — завжди справжня",
    "Спершу чернетка — ви дивитесь і натискаєте «в публікацію»"] },
  { id: "carousels", label: "Каруселі", stage: 6, group: "Виробництво", what: [
    "З бібліотеки реальних фото й бази знань, у фірмовому стилі",
    "Ціна «від» і кодове слово — лише перевірені з бази знань"] },
  { id: "publish", label: "Публікація і гроші", stage: 7, group: "Результат", what: [
    "Кнопка «опублікувати» в Instagram, YouTube, Telegram; TikTok — через «Вхідні» застосунку",
    "Звіт: ролик → переписки → угоди → гривні"] },
];

const PLATFORM_MARK: Record<string, string> = { instagram: "IG", tiktok: "TT", youtube: "YT", telegram: "TG" };
const ROLE_ORDER = ["own", "competitor", "inspiration"];
const ROLE_HINT: Record<string, string> = {
  own: "Ваші сторінки — з них аналітик рахує, що працює.",
  competitor: "Конкуренти в ніші — стежимо за їхніми сильними роликами.",
  inspiration: "Не конкуренти, але вчимося прийомів: дизайн, ремонт, DIY.",
};

const CSS = `
.cf{--cf-bg:#14181b;--cf-panel:#1c2225;--cf-panel2:#232a2e;--cf-line:#2d363b;--cf-ink:#e7ecee;--cf-ink2:#9aa6ab;--cf-ink3:#6c787d;
  --cf-gold:#e3b85f;--cf-blue:#7fb0d4;--cf-good:#6cc08f;--cf-bad:#e07a6e;
  background:var(--cf-bg);color:var(--cf-ink);border-radius:12px;display:grid;grid-template-columns:220px minmax(0,1fr);min-height:calc(100vh - 110px);overflow:hidden}
.cf-rail{border-right:1px solid var(--cf-line);padding:18px 12px;display:flex;flex-direction:column;gap:2px}
.cf-brand{font-weight:800;letter-spacing:.08em;font-size:13px;padding:2px 10px 4px}
.cf-brand small{display:block;font-weight:500;letter-spacing:.02em;color:var(--cf-ink3);font-size:11px;margin-top:3px}
.cf-grp{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--cf-ink3);padding:16px 10px 6px}
.cf-nav{all:unset;box-sizing:border-box;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 10px;border-radius:7px;color:var(--cf-ink2);font-size:13px}
.cf-nav:hover{background:var(--cf-panel)}
.cf-nav:focus-visible{outline:2px solid var(--cf-blue);outline-offset:1px}
.cf-nav.on{background:var(--cf-panel2);color:var(--cf-ink)}
.cf-nav em{font-style:normal;font-size:10px;font-weight:700;color:var(--cf-ink3);font-variant-numeric:tabular-nums}
.cf-nav.on em,.cf-nav em.live{color:var(--cf-gold)}
.cf-main{padding:24px clamp(16px,2.4vw,32px) 40px;display:grid;gap:22px;align-content:start;min-width:0}
.cf-h1{font-size:clamp(24px,2.6vw,32px);font-weight:800;letter-spacing:-.01em;margin:0;line-height:1.15}
.cf-sub{color:var(--cf-ink2);max-width:64ch;font-size:14px;line-height:1.55;margin:6px 0 0}
.cf-hero{display:grid;grid-template-columns:minmax(0,1fr) 220px;gap:24px;align-items:end}
.cf-sw{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;height:96px}
.cf-sw div{border-radius:3px}
.cf-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.cf-kpi{background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:9px;padding:12px 14px}
.cf-kpi span{display:block;font-size:11px;color:var(--cf-ink2)}
.cf-kpi b{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums}
.cf-card{background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:10px;padding:16px 18px;display:grid;gap:12px}
.cf-card h3{margin:0;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--cf-ink2)}
.cf-stages{display:grid;gap:0}
.cf-stage{display:grid;grid-template-columns:34px minmax(0,1fr) auto;gap:12px;align-items:center;padding:10px 0;border-top:1px solid var(--cf-line)}
.cf-stage:first-child{border-top:0}
.cf-stage .n{font-weight:800;font-size:18px;color:var(--cf-ink3);font-variant-numeric:tabular-nums}
.cf-stage.now .n{color:var(--cf-gold)}
.cf-stage p{margin:0;font-size:13.5px}
.cf-stage small{color:var(--cf-ink2);font-size:12px}
.cf-pill{font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:4px 8px;border-radius:5px;white-space:nowrap}
.cf-pill.now{background:rgba(227,184,95,.16);color:var(--cf-gold)}
.cf-pill.next{background:var(--cf-panel2);color:var(--cf-ink3)}
.cf-add{display:grid;grid-template-columns:minmax(0,1fr) 150px 140px auto;gap:8px}
.cf-in{box-sizing:border-box;width:100%;height:38px;background:var(--cf-bg);border:1px solid var(--cf-line);border-radius:8px;color:var(--cf-ink);padding:0 12px;font:inherit;font-size:13.5px}
.cf-in:focus{outline:none;border-color:var(--cf-blue)}
.cf-btn{all:unset;box-sizing:border-box;cursor:pointer;height:38px;padding:0 16px;border-radius:8px;font-size:13px;font-weight:700;display:inline-flex;align-items:center;justify-content:center;white-space:nowrap}
.cf-btn:focus-visible{outline:2px solid var(--cf-blue);outline-offset:2px}
.cf-btn.gold{background:var(--cf-gold);color:#1b1608}
.cf-btn.gold[disabled]{opacity:.5;cursor:default}
.cf-btn.ghost{height:30px;padding:0 10px;font-weight:600;font-size:12px;color:var(--cf-ink2);border:1px solid var(--cf-line)}
.cf-btn.ghost:hover{color:var(--cf-ink)}
.cf-btn.danger{height:30px;padding:0 10px;font-size:12px;background:rgba(224,122,110,.16);color:var(--cf-bad)}
.cf-msg{font-size:13px}
.cf-msg.err{color:var(--cf-bad)} .cf-msg.ok{color:var(--cf-good)}
.cf-role{display:grid;gap:8px}
.cf-role-h{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.cf-role-h b{font-size:15px}
.cf-role-h span{color:var(--cf-ink3);font-size:12px}
.cf-row{display:grid;grid-template-columns:38px minmax(0,1fr) auto;gap:12px;align-items:center;background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:9px;padding:10px 12px}
.cf-row.off{opacity:.5}
.cf-mark{width:38px;height:38px;border-radius:8px;display:grid;place-items:center;font-size:11px;font-weight:800;letter-spacing:.04em;background:var(--cf-panel2);color:var(--cf-ink)}
.cf-mark.instagram{background:linear-gradient(135deg,#6b3fa0,#c13584 55%,#e1a14b)}
.cf-mark.tiktok{background:#0b0b0b;box-shadow:inset 2px 0 0 #25f4ee,inset -2px 0 0 #fe2c55}
.cf-mark.youtube{background:#c4302b}
.cf-mark.telegram{background:#2a8bc7}
.cf-row a{color:var(--cf-ink);text-decoration:none;font-weight:700;font-size:14px}
.cf-row a:hover{text-decoration:underline}
.cf-row .meta{color:var(--cf-ink2);font-size:12px;margin-top:2px;overflow-wrap:anywhere}
.cf-acts{display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.cf-sel{height:30px;background:var(--cf-bg);border:1px solid var(--cf-line);border-radius:7px;color:var(--cf-ink);font:inherit;font-size:12px;padding:0 6px}
.cf-empty{border:1px dashed var(--cf-line);border-radius:9px;padding:14px 16px;color:var(--cf-ink3);font-size:13px}
.cf-q-top{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:14px}
.cf-meter{height:6px;border-radius:3px;background:var(--cf-panel2);overflow:hidden}
.cf-meter i{display:block;height:100%;background:var(--cf-gold)}
.cf-kv{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:var(--cf-ink2)}
.cf-kv b{color:var(--cf-ink);font-variant-numeric:tabular-nums}
.cf-set{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.cf-set .cf-in{width:auto;height:32px;font-size:12.5px}
.cf-chips{display:flex;gap:6px;flex-wrap:wrap}
.cf-chip{all:unset;cursor:pointer;font-size:12px;padding:6px 10px;border-radius:999px;border:1px solid var(--cf-line);color:var(--cf-ink2)}
.cf-chip.on{background:var(--cf-panel2);color:var(--cf-ink);border-color:var(--cf-ink3)}
.cf-chip:focus-visible{outline:2px solid var(--cf-blue)}
.cf-topic{display:grid;grid-template-columns:54px minmax(0,1fr) auto;gap:14px;align-items:start;background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:10px;padding:12px 14px}
.cf-topic .cnt{font-size:24px;font-weight:800;color:var(--cf-gold);line-height:1;font-variant-numeric:tabular-nums;text-align:right}
.cf-topic .cnt small{display:block;font-size:10px;font-weight:600;color:var(--cf-ink3);margin-top:4px}
.cf-topic h4{margin:0;font-size:14.5px;line-height:1.35}
.cf-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.cf-tag{font-size:11px;padding:3px 7px;border-radius:5px;background:var(--cf-panel2);color:var(--cf-ink2)}
.cf-tag.kb{background:rgba(108,192,143,.14);color:var(--cf-good)}
.cf-tag.nokb{background:rgba(227,184,95,.14);color:var(--cf-gold)}
.cf-ex{margin:8px 0 0;padding-left:16px;color:var(--cf-ink2);font-size:12.5px;display:grid;gap:3px}
.cf-soon ul{margin:0;padding-left:18px;display:grid;gap:8px;color:var(--cf-ink);font-size:14px;line-height:1.5}
@media (max-width:900px){
  .cf-q-top{grid-template-columns:1fr}
  .cf-topic{grid-template-columns:44px minmax(0,1fr)}
  .cf-topic .cf-acts{grid-column:1/-1}
  .cf{grid-template-columns:1fr}
  .cf-rail{border-right:0;border-bottom:1px solid var(--cf-line);flex-direction:row;flex-wrap:wrap;gap:4px;padding:12px}
  .cf-brand,.cf-grp{display:none}
  .cf-nav{padding:6px 9px;font-size:12px}
  .cf-hero{grid-template-columns:1fr}
  .cf-sw{height:56px}
  .cf-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .cf-add{grid-template-columns:1fr 1fr}
  .cf-add .cf-in:first-child{grid-column:1/-1}
  .cf-row{grid-template-columns:38px minmax(0,1fr)}
  .cf-acts{grid-column:1/-1;justify-content:flex-start}
}
`;

const SWATCHES = [
  "linear-gradient(115deg,#d9d4ca,#f3efe7 22%,#cfc8bb 40%,#efeae1 58%,#c9c1b3 78%,#e9e3d8)",
  "linear-gradient(135deg,#c9ccd0,#eef0f2 18%,#b9bec4 35%,#e6e9ec 52%,#aeb4ba 70%,#dfe3e7)",
  "linear-gradient(160deg,#b89d78,#d9c3a2 30%,#a48662 55%,#cfb690 80%,#9c7e5a)",
  "radial-gradient(circle at 30% 30%,#6b6f75,#3c4046 45%,#26292d)",
];

function Rail({ tab, setTab, total }: { tab: string; setTab: (t: string) => void; total: number }) {
  let lastGroup = "";
  return (
    <nav className="cf-rail" aria-label="Розділи контент-заводу">
      <div className="cf-brand">КОНТЕНТ-ЗАВОД<small>доступ: лише власник</small></div>
      {SECTIONS.map((s) => {
        const head = s.group && s.group !== lastGroup ? s.group : "";
        if (s.group) lastGroup = s.group;
        return (
          <div key={s.id} style={{ display: "contents" }}>
            {head && <div className="cf-grp">{head}</div>}
            <button type="button" className={"cf-nav" + (tab === s.id ? " on" : "")} onClick={() => setTab(s.id)}
              aria-current={tab === s.id ? "page" : undefined}>
              <span>{s.label}</span>
              {s.id === "channels" ? <em className="live">{total}</em> : !s.live ? <em>ет. {s.stage}</em> : null}
            </button>
          </div>
        );
      })}
    </nav>
  );
}

function Studio({ ov, go }: { ov: Overview | null; go: (t: string) => void }) {
  const r = ov?.by_role || {};
  const p = ov?.by_platform || {};
  return (
    <>
      <div className="cf-hero">
        <div>
          <h1 className="cf-h1">Контент-завод</h1>
          <p className="cf-sub">Рилси з ваших нарізок, каруселі й щоденні пости в Telegram — з реальних питань клієнтів і відповідей бази знань.
            Аналітик щотижня підкаже, що знімати далі. Працюють «Сторінки» (що аналізувати) і «Питання клієнтів» (що людей цікавить найбільше).</p>
        </div>
        <div className="cf-sw" aria-hidden="true">{SWATCHES.map((bg, i) => <div key={i} style={{ background: bg }} />)}</div>
      </div>
      <div className="cf-kpis">
        <div className="cf-kpi"><span>Наші сторінки</span><b>{r.own ?? "—"}</b></div>
        <div className="cf-kpi"><span>Конкуренти</span><b>{r.competitor ?? "—"}</b></div>
        <div className="cf-kpi"><span>Натхнення</span><b>{r.inspiration ?? "—"}</b></div>
        <div className="cf-kpi"><span>IG · TT · YT · TG</span><b>{ov ? `${p.instagram}·${p.tiktok}·${p.youtube}·${p.telegram}` : "—"}</b></div>
      </div>
      <div className="cf-card">
        <h3>План запуску</h3>
        <div className="cf-stages">
          {[{ n: 0, t: "Каркас розділу і сторінки для аналізу", d: "доступ лише вам" },
            ...SECTIONS.filter((s) => s.stage > 0).reduce<{ n: number; t: string; d: string }[]>((acc, s) => {
              const ex = acc.find((a) => a.n === s.stage);
              if (ex) ex.t += " + " + s.label.toLowerCase(); else acc.push({ n: s.stage, t: s.label, d: s.what?.[0] || "" });
              return acc;
            }, [])].map((st) => (
            <div key={st.n} className={"cf-stage" + (st.n <= 1 ? " now" : "")}>
              <span className="n">{st.n}</span>
              <div><p>{st.t}</p><small>{st.d}</small></div>
              <span className={"cf-pill " + (st.n <= 1 ? "now" : "next")}>{st.n <= 1 ? "готово" : "далі"}</span>
            </div>
          ))}
        </div>
      </div>
      {(ov?.channels_total ?? 0) === 0 && (
        <div className="cf-empty">Ще немає жодної сторінки. <button type="button" className="cf-btn ghost" onClick={() => go("channels")}>Додати сторінки →</button></div>
      )}
    </>
  );
}

function AddChannel({ roles, platforms, onAdded }: { roles: [string, string][]; platforms: [string, string][]; onAdded: () => void }) {
  const [link, setLink] = useState("");
  const [role, setRole] = useState("competitor");
  const [platform, setPlatform] = useState("instagram");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const atName = link.trim().startsWith("@");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!link.trim()) return;
    setBusy(true); setMsg(null);
    try {
      const ch = await api.post<Channel>("/api/content-factory/channels/", { link, role, platform: atName ? platform : "" });
      setMsg({ ok: true, text: `Додано: ${ch.platform_display} @${ch.handle}` });
      setLink("");
      onAdded();
    } catch (err: any) {
      setMsg({ ok: false, text: err?.data?.error || err?.message || "Не вдалося додати." });
    } finally { setBusy(false); }
  };
  return (
    <form className="cf-card" onSubmit={submit}>
      <h3>Додати сторінку</h3>
      <div className="cf-add">
        <input id="cf-link" className="cf-in" value={link} onChange={(e) => setLink(e.target.value)}
          placeholder="Посилання: instagram.com/…, tiktok.com/@…, youtube.com/@…, t.me/…" aria-label="Посилання на сторінку" />
        <select id="cf-role" className="cf-in" value={role} onChange={(e) => setRole(e.target.value)} aria-label="Тип сторінки">
          {roles.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select id="cf-platform" className="cf-in" value={platform} onChange={(e) => setPlatform(e.target.value)}
          aria-label="Соцмережа" disabled={!atName} title={atName ? "" : "Визначається з посилання"}>
          {platforms.map(([v, l]) => <option key={v} value={v}>{atName ? l : "з посилання"}</option>)}
        </select>
        <button type="submit" className="cf-btn gold" disabled={busy || !link.trim()}>{busy ? "Додаю…" : "Додати"}</button>
      </div>
      {msg && <div className={"cf-msg " + (msg.ok ? "ok" : "err")} role="status">{msg.text}</div>}
    </form>
  );
}

function ChannelRow({ ch, roles, onChanged }: { ch: Channel; roles: [string, string][]; onChanged: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const patch = async (b: Partial<Channel>) => {
    setBusy(true);
    try { await api.patch(`/api/content-factory/channels/${ch.id}/`, b); onChanged(); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await api.del(`/api/content-factory/channels/${ch.id}/`); onChanged(); } finally { setBusy(false); }
  };
  return (
    <div className={"cf-row" + (ch.is_active ? "" : " off")}>
      <span className={"cf-mark " + ch.platform} aria-label={ch.platform_display}>{PLATFORM_MARK[ch.platform] || "?"}</span>
      <div style={{ minWidth: 0 }}>
        <a href={ch.url} target="_blank" rel="noreferrer">@{ch.handle}</a>
        <div className="meta">{ch.platform_display}{ch.title ? " · " + ch.title : ""}{ch.note ? " · " + ch.note : ""}{ch.is_active ? "" : " · вимкнена"}</div>
      </div>
      <div className="cf-acts">
        <select className="cf-sel" value={ch.role} disabled={busy} onChange={(e) => patch({ role: e.target.value })} aria-label="Тип сторінки">
          {roles.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <button type="button" className="cf-btn ghost" disabled={busy} onClick={() => patch({ is_active: !ch.is_active })}>
          {ch.is_active ? "Вимкнути" : "Увімкнути"}
        </button>
        {confirm ? (
          <>
            <button type="button" className="cf-btn danger" disabled={busy} onClick={remove}>Так, прибрати</button>
            <button type="button" className="cf-btn ghost" onClick={() => setConfirm(false)}>Ні</button>
          </>
        ) : (
          <button type="button" className="cf-btn ghost" onClick={() => setConfirm(true)}>Прибрати</button>
        )}
      </div>
    </div>
  );
}

function Channels({ data, reload }: { data: ChannelList | null; reload: () => void }) {
  if (!data) return <div className="cf-empty">Завантажую…</div>;
  return (
    <>
      <div>
        <h1 className="cf-h1">Сторінки</h1>
        <p className="cf-sub">Наші сторінки, конкуренти й джерела натхнення. З етапу 3 аналітик збиратиме їхні ролики й щотижня пропонуватиме ідеї.
          Вставте посилання на профіль — соцмережа визначиться сама.</p>
      </div>
      <AddChannel roles={data.roles} platforms={data.platforms} onAdded={reload} />
      {ROLE_ORDER.map((role) => {
        const rows = data.results.filter((c) => c.role === role);
        const label = data.roles.find(([v]) => v === role)?.[1] || role;
        return (
          <section key={role} className="cf-role">
            <div className="cf-role-h"><b>{label}</b><span>{rows.length} · {ROLE_HINT[role]}</span></div>
            {rows.length ? rows.map((ch) => <ChannelRow key={ch.id} ch={ch} roles={data.roles} onChanged={reload} />)
              : <div className="cf-empty">Поки порожньо.</div>}
          </section>
        );
      })}
    </>
  );
}

const usd = (n: number) => "$" + (n < 0.1 ? n.toFixed(3) : n.toFixed(2));
const CHANNEL_LABEL: Record<string, string> = { instagram: "IG", tiktok: "TikTok", echat: "Viber", echat_whatsapp: "WhatsApp", telegram: "TG", facebook: "FB" };

function CostCard({ s, reload }: { s: QSettings; reload: () => void }) {
  const [budget, setBudget] = useState(String(s.monthly_budget_usd));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { setBudget(String(s.monthly_budget_usd)); }, [s.monthly_budget_usd]);
  const save = async (b: Record<string, unknown>) => {
    setBusy(true); setMsg(null);
    try { await api.patch("/api/content-factory/questions/settings/", b); reload(); }
    catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося зберегти." }); }
    finally { setBusy(false); }
  };
  const runNow = async () => {
    setBusy(true); setMsg(null);
    try {
      const r: any = await api.post("/api/content-factory/questions/run/");
      setMsg({ ok: true, text: r.note || "Готово" }); reload();
    } catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося запустити." }); }
    finally { setBusy(false); }
  };
  const pct = s.monthly_budget_usd > 0 ? Math.min(100, (s.spent_month_usd / s.monthly_budget_usd) * 100) : 100;
  const pend = s.pending;
  return (
    <div className="cf-q-top">
      <div className="cf-card">
        <h3>Розбір питань · витрати</h3>
        <div className="cf-kv"><span>Стан</span>
          <span className={"cf-pill " + (s.enabled ? "now" : "next")}>{s.enabled ? "увімкнено · щоночі 03:40" : "вимкнено"}</span></div>
        <div className="cf-kv"><span>Витрачено цього місяця</span><b>{usd(s.spent_month_usd)} з {usd(s.monthly_budget_usd)}</b></div>
        <div className="cf-meter" aria-hidden="true"><i style={{ width: pct + "%" }} /></div>
        <div className="cf-set">
          <select id="cf-q-model" className="cf-in" value={s.model} disabled={busy} onChange={(e) => save({ model: e.target.value })} aria-label="Модель ШІ">
            {s.models.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <label className="cf-kv" htmlFor="cf-q-budget" style={{ alignItems: "center" }}>ліміт $/міс</label>
          <input id="cf-q-budget" className="cf-in" style={{ width: 70 }} inputMode="decimal" value={budget}
            onChange={(e) => setBudget(e.target.value)} onBlur={() => budget !== String(s.monthly_budget_usd) && save({ monthly_budget_usd: budget })} />
          <button type="button" className={"cf-btn " + (s.enabled ? "ghost" : "gold")} style={{ height: 32 }} disabled={busy}
            onClick={() => save({ enabled: !s.enabled })}>{s.enabled ? "Вимкнути" : "Увімкнути щоночі"}</button>
        </div>
        {msg && <div className={"cf-msg " + (msg.ok ? "ok" : "err")} role="status">{msg.text}</div>}
      </div>
      <div className="cf-card">
        <h3>Чекає розбору</h3>
        <div className="cf-kv"><span>Нових питань (відібрано без ШІ)</span><b>{pend ? pend.questions : "—"}</b></div>
        <div className="cf-kv"><span>Орієнтовна ціна розбору</span><b>{pend ? "≈ " + usd(pend.estimate_usd) : "—"}</b></div>
        <div className="cf-kv"><span>Останній запуск</span><b style={{ fontWeight: 500, textAlign: "right" }}>{s.last_run_note || "ще не було"}</b></div>
        <button type="button" className="cf-btn gold" disabled={busy || !pend?.questions} onClick={runNow}>
          {busy ? "Розбираю…" : pend?.questions ? `Розібрати зараз · до 120 питань` : "Нових питань немає"}
        </button>
      </div>
    </div>
  );
}

function TopicRow({ t, statuses, onChanged }: { t: Topic; statuses: [string, string][]; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const setStatus = async (status: string) => { await api.patch(`/api/content-factory/questions/${t.id}/`, { status }); onChanged(); };
  return (
    <div className="cf-topic">
      <div className="cnt">{t.count_period}<small>разів</small></div>
      <div style={{ minWidth: 0 }}>
        <h4>{t.title}</h4>
        <div className="cf-tags">
          {t.material && <span className="cf-tag">{t.material}</span>}
          {Object.entries(t.channels).map(([ch, n]) => <span key={ch} className="cf-tag">{CHANNEL_LABEL[ch] || ch} · {n}</span>)}
          {t.kb ? <span className="cf-tag kb" title={t.kb.title}>є в базі знань</span> : <span className="cf-tag nokb">немає в базі знань</span>}
        </div>
        {open && <ul className="cf-ex">{t.examples.map((e, i) => <li key={i}>{e}</li>)}</ul>}
      </div>
      <div className="cf-acts">
        <button type="button" className="cf-btn ghost" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Сховати" : "Як питають"}</button>
        <select className="cf-sel" value={t.status} onChange={(e) => setStatus(e.target.value)} aria-label="Статус теми">
          {statuses.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
    </div>
  );
}

function Questions() {
  const [days, setDays] = useState(7);
  const [status, setStatus] = useState("active");
  const [data, setData] = useState<QData | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try { setData(await api.get<QData>(`/api/content-factory/questions/?days=${days}&status=${status}`)); setErr(""); }
    catch { setErr("Не вдалося завантажити питання."); }
  }, [days, status]);
  useEffect(() => { load(); }, [load]);
  return (
    <>
      <div>
        <h1 className="cf-h1">Питання клієнтів</h1>
        <p className="cf-sub">Щоночі CRM відбирає з переписок справжні питання (без ШІ), а ШІ групує лише нові в теми. Кожне повідомлення
          розбирається один раз, є місячний ліміт. Найчастіші теми — готові ідеї для рилсів, каруселей і постів.</p>
      </div>
      {err && <div className="cf-msg err" role="alert">{err}</div>}
      {data && <CostCard s={data.settings} reload={load} />}
      <div className="cf-chips" role="group" aria-label="Період">
        {[7, 30, 90].map((d) => <button key={d} type="button" className={"cf-chip" + (days === d ? " on" : "")} onClick={() => setDays(d)}>{d} днів</button>)}
        <span style={{ width: 12 }} />
        {[["active", "Усі робочі"], ["planned", "У плані"], ["done", "Зроблено"], ["ignored", "Не для контенту"]].map(([v, l]) =>
          <button key={v} type="button" className={"cf-chip" + (status === v ? " on" : "")} onClick={() => setStatus(v)}>{l}</button>)}
      </div>
      {!data ? <div className="cf-empty">Завантажую…</div>
        : data.topics.length ? data.topics.map((t) => <TopicRow key={t.id} t={t} statuses={data.statuses} onChanged={load} />)
        : <div className="cf-empty">{data.settings.last_run_at ? "За цей період тем немає." : "Тем ще немає — увімкніть розбір або натисніть «Розібрати зараз»."}</div>}
    </>
  );
}

function Soon({ s }: { s: Section }) {
  return (
    <>
      <div>
        <h1 className="cf-h1">{s.label}</h1>
        <p className="cf-sub">Етап {s.stage}. Запускається після вашого «ок» на попередні етапи.</p>
      </div>
      <div className="cf-card cf-soon">
        <h3>Що тут буде</h3>
        <ul>{(s.what || []).map((w) => <li key={w}>{w}</li>)}</ul>
      </div>
    </>
  );
}

export default function ContentFactory() {
  const [tab, setTab] = useState(() => {
    try { return localStorage.getItem("cf.tab") || "studio"; } catch { return "studio"; }
  });
  const [ov, setOv] = useState<Overview | null>(null);
  const [list, setList] = useState<ChannelList | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try {
      const [o, l] = await Promise.all([
        api.get<Overview>("/api/content-factory/overview/"),
        api.get<ChannelList>("/api/content-factory/channels/"),
      ]);
      setOv(o); setList(l); setErr("");
    } catch (e: any) {
      setErr(e?.status === 403 ? "Розділ доступний лише власнику." : "Не вдалося завантажити дані. Оновіть сторінку.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  const go = (t: string) => { setTab(t); try { localStorage.setItem("cf.tab", t); } catch { /* приватний режим */ } };
  const section = SECTIONS.find((s) => s.id === tab) || SECTIONS[0];
  return (
    <div className="cf">
      <style>{CSS}</style>
      <Rail tab={section.id} setTab={go} total={list?.results.length ?? 0} />
      <main className="cf-main">
        {err && <div className="cf-msg err" role="alert">{err}</div>}
        {section.id === "studio" ? <Studio ov={ov} go={go} />
          : section.id === "channels" ? <Channels data={list} reload={load} />
          : section.id === "questions" ? <Questions />
          : <Soon s={section} />}
      </main>
    </div>
  );
}
