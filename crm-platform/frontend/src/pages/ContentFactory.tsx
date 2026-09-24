/* Розділ «Контент-завод» (24.09.2026, етап 0). Доступ — лише власник або право content_factory.access.
 * Працює: «Студія» (план і лічильники) і «Сторінки» (наші сторінки, конкуренти, натхнення в IG / TikTok / YouTube / Telegram).
 * Етап 1 (24.09): «Питання клієнтів» — нічний розбір питань у теми, з лімітом витрат (вмикає лише власник).
 * Етап 2 (24.09): «Telegram-автопілот» — чернетки постів з найчастіших питань: факти з бази знань, реальні фото,
 *   попередній перегляд як у Telegram. 24.09: публікація через @wallcov_smm_bot — зараз / за планом / «Надіслати мені»;
 *   календар 7 днів, фото й відео з бібліотеки, пост вручну.
 * «Джерела контенту» (24.09): файли з TG-груп, каналу й Google Drive лише за посиланням, мітки з підпису/шляху папок.
 * Telegram-автопілот: підвкладка «Опубліковані й аналітика» — перегляди/реакції з публічного віджета каналу, знімки в часі.
 * Етап 3 (24.09): «Стрічка рекомендацій» (Virale, мітка ×N від звичного) і «Аналітик» (тижневий звіт + 5 ідей).
 * Етапи 4–5 (24.09): «Рилси» — розмітка сцен (Gemini) лише потрібного матеріалу, сценарій, монтаж ffmpeg 9:16.
 * Прокрутка: .view у Layout має overflow:hidden, тому сторінка гортає САМА — .cf на всю висоту, .cf-main overflow:auto (вниз і вбік).
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
type TgPhoto = { id: number; title: string; url: string; preview_url: string };
type SrcItem = {
  id: number; kind: string; kind_display: string; caption: string; material: string; tags: string[]; link: string;
  chat: string; hidden: boolean; thumb_url: string; duration: number | null; posted_at: string | null;
};
type SrcData = {
  total: number; items: SrcItem[]; ingest_ready: boolean;
  chats: { id: number; title: string; username: string; kind: string; enabled: boolean; count: number }[];
  materials: { name: string; count: number }[];
  drive_folders: DriveFolderT[]; drive_email: string;
};
type TgPostT = {
  id: number; title: string; text: string; material: string; status: string; status_display: string; photos: TgPhoto[];
  videos: TgPhoto[]; photo_ids: number[]; video_ids: number[]; sources: SrcItem[]; source_ids: number[];
  facts: string[]; checks: string[]; model: string; topic: { id: number; title: string } | null; created_at: string;
  scheduled_at: string | null; published_at: string | null; publish_error: string;
  views?: number | null; reactions?: number | null; reactions_detail?: Record<string, number>; tg_link?: string; stats_at?: string | null;
  history?: { at: string; views: number | null; reactions: number | null }[]; views_24h?: number | null;
};
type PubData = {
  posts: TgPostT[];
  summary: { count: number; avg_views: number | null; total_reactions: number; best: { id: number; title: string; views: number } | null };
};
type FeedT = {
  id: number; username: string; platform: string; url: string; preview_url: string; caption: string; media_type: string;
  duration: number | null; views: number | null; likes: number | null; comments: number | null; engagement: number | null;
  x: number | null; status: string; is_own: boolean; published_at: string | null;
};
type ReportT = { id: number; created_at: string; period_days: number; summary: string; model: string;
  ideas: { title: string; hook: string; why: string; format: string; material: string }[]; inputs: Record<string, any> };
type ReelT = {
  id: number; title: string; topic: string; material: string; caption: string; status: string; status_display: string;
  duration: number | null; error: string; facts: string[]; created_at: string; video_url: string;
  beats: { text: string; scene_id: number; seconds: number; what: string; source: string }[];
};
type DriveFolderT = { id: number; folder_id: string; title: string; enabled: boolean; files_count: number; last_error: string; last_sync_at: string | null; link: string };
type TgData = {
  settings: { daily_drafts: boolean; model: string; models: [string, string][]; monthly_budget_usd: number;
    spent_month_usd: number; estimate_usd: number; channel: string; publish_enabled: boolean };
  next_topic: { id: number; title: string; count_7d: number } | null;
  posts: TgPostT[];
};

type Section = { id: string; label: string; stage: number; group?: string; live?: boolean; what?: string[] };
const SECTIONS: Section[] = [
  { id: "studio", label: "Студія", stage: 0, live: true },
  { id: "channels", label: "Сторінки", stage: 0, live: true },
  { id: "questions", label: "Питання клієнтів", stage: 1, group: "Сировина", live: true, what: [
    "Щоночі ШІ групує вхідні з усіх каналів (Instagram, TikTok, Viber, Telegram, WhatsApp) у теми",
    "Біля теми — скільки разів спитали, чи є відповідь у базі знань, які є фото й відео",
    "Одна кнопка: зробити з теми рилс, карусель або пост у Telegram"] },
  { id: "telegram", label: "Telegram-автопілот", stage: 2, group: "Сировина", live: true, what: [
    "Щодня пост: питання дня → коротка відповідь з бази знань → 2–3 реальні фото → посилання на підбір",
    "Перші 2 тижні — через вашу кнопку «схвалити», далі повністю автоматично",
    "Посилання з міткою — CRM рахує ліди з каналу"] },
  { id: "analyst", label: "Аналітик", stage: 3, group: "Аналітика", live: true, what: [
    "Аналізує сторінки з вкладки «Сторінки»: наші й конкурентів",
    "Щотижня звіт: що спрацювало, що ні, і 5 ідей на тиждень",
    "Окремо — які ролики принесли переписки та оплати"] },
  { id: "feed", label: "Стрічка рекомендацій", stage: 3, group: "Аналітика", live: true, what: [
    "Вірусні ролики ніші з фільтрами: соцмережа, період, тривалість, формат, хук",
    "Кнопка «зробити з наших» — той самий прийом, але ваша фактура з ваших нарізок",
    "Вибране одразу в план"] },
  { id: "sources", label: "Джерела контенту", stage: 4, group: "Виробництво", live: true, what: [
    "Завантажуєте нарізки як є — без сценарію й дублів",
    "ШІ розмічає кожну сцену: матеріал, колір, етап (нанесення, блік, готова стіна), світло",
    "Пошук сцен: «Галатея, крупно, блік»"] },
  { id: "reels", label: "Рилси", stage: 5, group: "Виробництво", live: true, what: [
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
  background:var(--cf-bg);color:var(--cf-ink);border-radius:12px;display:grid;grid-template-columns:220px minmax(0,1fr);
  grid-template-rows:minmax(0,1fr);height:100%;min-height:0;overflow:hidden}
.cf-rail{border-right:1px solid var(--cf-line);padding:18px 12px;display:flex;flex-direction:column;gap:2px;overflow-y:auto;min-height:0}
.cf-brand{font-weight:800;letter-spacing:.08em;font-size:13px;padding:2px 10px 4px}
.cf-brand small{display:block;font-weight:500;letter-spacing:.02em;color:var(--cf-ink3);font-size:11px;margin-top:3px}
.cf-grp{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--cf-ink3);padding:16px 10px 6px}
.cf-nav{all:unset;box-sizing:border-box;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 10px;border-radius:7px;color:var(--cf-ink2);font-size:13px}
.cf-nav:hover{background:var(--cf-panel)}
.cf-nav:focus-visible{outline:2px solid var(--cf-blue);outline-offset:1px}
.cf-nav.on{background:var(--cf-panel2);color:var(--cf-ink)}
.cf-nav em{font-style:normal;font-size:10px;font-weight:700;color:var(--cf-ink3);font-variant-numeric:tabular-nums}
.cf-nav.on em,.cf-nav em.live{color:var(--cf-gold)}
.cf-main{padding:24px clamp(16px,2.4vw,32px) 40px;min-width:0;min-height:0;overflow:auto;overscroll-behavior:contain}
.cf-page{display:grid;gap:22px;align-content:start;min-width:880px}
.cf-main::-webkit-scrollbar{height:10px;width:10px}
.cf-main::-webkit-scrollbar-thumb{background:var(--cf-line);border-radius:5px}
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
.cf-btn[disabled]{opacity:.45;cursor:default}
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
.cf-tg{display:grid;grid-template-columns:380px minmax(0,1fr);gap:18px;align-items:start;background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:12px;padding:16px}
.tg-chat{background:#0e1621;border-radius:12px;padding:14px 12px;font-family:-apple-system,"Segoe UI",Roboto,sans-serif}
.tg-head{display:flex;gap:10px;align-items:center;margin-bottom:10px}
.tg-ava{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#c9ccd0,#8d949b);display:grid;place-items:center;color:#14181b;font-weight:800;font-size:14px}
.tg-head b{color:#fff;font-size:14px;display:block}
.tg-head span{color:#6d7f8f;font-size:12px}
.tg-bubble{background:#182533;border-radius:12px;overflow:hidden;color:#f5f5f5;font-size:14px;line-height:1.45}
.tg-album{display:grid;grid-template-columns:1fr 1fr;gap:2px}
.tg-album img{width:100%;height:100%;object-fit:cover;display:block;background:#0b1118}
.tg-album img:first-child{grid-column:1/-1;aspect-ratio:4/3}
.tg-album img:not(:first-child){aspect-ratio:1/1}
.tg-text{padding:9px 12px 4px;white-space:pre-wrap;overflow-wrap:anywhere}
.tg-text a{color:#6ab3f3;text-decoration:none}
.tg-meta{display:flex;justify-content:flex-end;gap:10px;padding:0 12px 8px;color:#6d7f8f;font-size:11.5px}
.cf-side{display:grid;gap:12px;align-content:start;min-width:0}
.cf-side h4{margin:0;font-size:16px}
.cf-list{margin:0;padding-left:18px;display:grid;gap:4px;font-size:13px;color:var(--cf-ink2)}
.cf-list.warn{color:var(--cf-gold)}
.cf-ta{box-sizing:border-box;width:100%;min-height:260px;background:var(--cf-bg);border:1px solid var(--cf-line);border-radius:8px;color:var(--cf-ink);padding:10px 12px;font:inherit;font-size:13.5px;line-height:1.5;resize:vertical}
.cf-ta:focus{outline:none;border-color:var(--cf-blue)}
.tg-album img:first-child,.tg-album .tg-vid:first-child{grid-column:1/-1}
.tg-vid{position:relative}
.tg-vid img{width:100%;aspect-ratio:4/3;object-fit:cover;display:block}
.tg-vid span{position:absolute;inset:0;display:grid;place-items:center;font-size:30px;color:#fff;text-shadow:0 2px 10px rgba(0,0,0,.6)}
.cf-media{display:flex;gap:6px;flex-wrap:wrap}
.cf-thumb{position:relative;width:64px;height:64px;border-radius:7px;overflow:hidden;border:1px solid var(--cf-line);background:#0b1118}
.cf-thumb img{width:100%;height:100%;object-fit:cover;display:block}
.cf-thumb button{all:unset;cursor:pointer;position:absolute;top:2px;right:2px;width:18px;height:18px;border-radius:50%;background:rgba(0,0,0,.7);color:#fff;font-size:11px;display:grid;place-items:center}
.cf-thumb em{position:absolute;left:3px;bottom:2px;font-style:normal;font-size:10px;color:#fff;text-shadow:0 1px 3px #000}
.cf-picker{border:1px dashed var(--cf-line);border-radius:9px;padding:10px;display:grid;gap:8px}
.cf-pick-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(78px,1fr));gap:6px;max-height:260px;overflow:auto}
.cf-pick-grid button{all:unset;cursor:pointer;position:relative;aspect-ratio:1/1;border-radius:6px;overflow:hidden;border:2px solid transparent;background:#0b1118}
.cf-pick-grid button.on{border-color:var(--cf-gold)}
.cf-pick-grid img{width:100%;height:100%;object-fit:cover;display:block}
.cf-week{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px}
.cf-day{background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:9px;padding:8px;min-height:92px;display:grid;gap:5px;align-content:start}
.cf-day.today{border-color:var(--cf-gold)}
.cf-day b{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--cf-ink2)}
.cf-slot{font-size:11.5px;line-height:1.3;background:var(--cf-panel2);border-radius:6px;padding:5px 6px}
.cf-slot i{font-style:normal;color:var(--cf-gold);font-variant-numeric:tabular-nums;margin-right:4px}
.cf-slot.pub{opacity:.6}
.cf-src-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px}
.cf-src{background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:10px;overflow:hidden;display:grid;grid-template-rows:auto 1fr}
.cf-src .ph{position:relative;aspect-ratio:1/1;background:#0b1118;display:grid;place-items:center;color:var(--cf-ink3);font-size:12px}
.cf-src .ph img{width:100%;height:100%;object-fit:cover;display:block}
.cf-src .ph span{position:absolute;left:6px;top:6px;font-size:10.5px;background:rgba(0,0,0,.65);color:#fff;padding:3px 6px;border-radius:4px}
.cf-src .bd{padding:8px 9px;display:grid;gap:5px;align-content:start;font-size:12px}
.cf-src .cap{color:var(--cf-ink);line-height:1.35;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.cf-src a{color:var(--cf-blue);text-decoration:none}
.cf-chatrow{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--cf-line);font-size:13px}
.cf-chatrow:first-of-type{border-top:0}
.cf-steps{margin:0;padding-left:18px;display:grid;gap:5px;font-size:13px;color:var(--cf-ink2)}
.cf-sub-tabs{display:flex;gap:6px;border-bottom:1px solid var(--cf-line);padding-bottom:10px}
.cf-pub{display:grid;grid-template-columns:64px minmax(0,1fr) 110px 150px 120px;gap:14px;align-items:center;background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:10px;padding:10px 12px}
.cf-pub img{width:64px;height:64px;object-fit:cover;border-radius:7px;display:block;background:#0b1118}
.cf-pub .big{font-size:20px;font-weight:800;font-variant-numeric:tabular-nums}
.cf-pub .big small{display:block;font-size:10.5px;font-weight:600;color:var(--cf-ink3)}
.cf-pub a{color:var(--cf-blue);text-decoration:none;font-size:12px}
.cf-spark{width:120px;height:34px;display:block}
.cf-feed{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
.cf-fcard{background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:11px;overflow:hidden;display:grid;grid-template-rows:auto 1fr}
.cf-fcard .ph{position:relative;aspect-ratio:9/13;background:#0b1118}
.cf-fcard .ph img{width:100%;height:100%;object-fit:cover;display:block}
.cf-fcard .x{position:absolute;left:8px;top:8px;background:var(--cf-gold);color:#1b1608;font-weight:800;font-size:13px;padding:4px 8px;border-radius:6px}
.cf-fcard .x.low{background:rgba(0,0,0,.65);color:#fff;font-weight:600}
.cf-fcard .hook{position:absolute;left:0;right:0;bottom:0;padding:26px 9px 8px;background:linear-gradient(transparent,rgba(0,0,0,.85));color:#fff;font-size:12px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.cf-fcard .bd{padding:8px 10px;display:grid;gap:6px;font-size:12px}
.cf-fcard .bd a{color:var(--cf-blue);text-decoration:none}
.cf-rep{white-space:pre-wrap;font-size:14px;line-height:1.6;max-width:78ch}
.cf-idea{display:grid;grid-template-columns:28px minmax(0,1fr);gap:10px;padding:10px 0;border-top:1px solid var(--cf-line)}
.cf-idea:first-of-type{border-top:0}
.cf-idea .n{font-weight:800;font-size:18px;color:var(--cf-gold)}
.cf-idea b{font-size:14px}
.cf-idea p{margin:3px 0 0;font-size:13px;color:var(--cf-ink2)}
.cf-reel{display:grid;grid-template-columns:270px minmax(0,1fr);gap:18px;align-items:start;background:var(--cf-panel);border:1px solid var(--cf-line);border-radius:12px;padding:14px}
.cf-reel video{width:270px;aspect-ratio:9/16;border-radius:10px;background:#000;display:block}
.cf-beat{display:grid;grid-template-columns:44px minmax(0,1fr);gap:10px;padding:7px 0;border-top:1px solid var(--cf-line);font-size:13px}
.cf-beat:first-of-type{border-top:0}
.cf-beat i{font-style:normal;color:var(--cf-gold);font-weight:700;font-variant-numeric:tabular-nums}
.cf-beat small{display:block;color:var(--cf-ink3);font-size:11.5px;margin-top:2px}
.cf-soon ul{margin:0;padding-left:18px;display:grid;gap:8px;color:var(--cf-ink);font-size:14px;line-height:1.5}
@media (max-width:900px){
  .cf-q-top{grid-template-columns:1fr}
  .cf-topic{grid-template-columns:44px minmax(0,1fr)}
  .cf-tg{grid-template-columns:340px minmax(0,1fr)}
  .cf-reel{grid-template-columns:220px minmax(0,1fr)}
  .cf-reel video{width:220px}
  .cf-topic .cf-acts{grid-column:1/-1}
  .cf{grid-template-columns:1fr;grid-template-rows:auto minmax(0,1fr)}
  .cf-rail{border-right:0;border-bottom:1px solid var(--cf-line);flex-direction:row;flex-wrap:nowrap;gap:4px;padding:12px;overflow-x:auto}
  .cf-nav{flex:0 0 auto}
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
            <div key={st.n} className={"cf-stage" + (st.n <= 3 ? " now" : "")}>
              <span className="n">{st.n}</span>
              <div><p>{st.t}</p><small>{st.d}</small></div>
              <span className={"cf-pill " + (st.n <= 3 ? "now" : "next")}>{st.n <= 3 ? "готово" : "далі"}</span>
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

const LINK_RX = /(https?:\/\/[^\s]+)/g;
function TgText({ text }: { text: string }) {
  const parts = text.split(LINK_RX);
  return <div className="tg-text">{parts.map((p, i) => (i % 2 ? <a key={i} href={p} target="_blank" rel="noreferrer">{p}</a> : <span key={i}>{p}</span>))}</div>;
}

function TgPreview({ post, channel }: { post: TgPostT; channel: string }) {
  const time = new Date(post.created_at).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
  return (
    <div className="tg-chat" aria-label="Попередній перегляд поста в Telegram">
      <div className="tg-head"><span className="tg-ava">W</span><div><b>Wallcov · рішення для інтерʼєру</b><span>{channel} · канал</span></div></div>
      <div className="tg-bubble">
        {(post.sources.length + post.videos.length + post.photos.length) > 0 && (
          <div className="tg-album">
            {post.sources.map((s) => s.kind === "video"
              ? <div key={"s" + s.id} className="tg-vid"><img src={s.thumb_url} alt={s.caption} loading="lazy" /><span>▶</span></div>
              : <img key={"s" + s.id} src={s.thumb_url} alt={s.caption} loading="lazy" />)}
            {post.videos.map((v) => <div key={"v" + v.id} className="tg-vid"><img src={v.preview_url || v.url} alt={v.title} loading="lazy" /><span>▶</span></div>)}
            {post.photos.map((ph) => <img key={ph.id} src={ph.preview_url || ph.url} alt={ph.title} loading="lazy" />)}
          </div>
        )}
        <TgText text={post.text} />
        <div className="tg-meta"><span>👁 —</span><span>{post.published_at ? new Date(post.published_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : time}</span></div>
      </div>
    </div>
  );
}

const localInput = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso); const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const dayTime = (iso: string) => new Date(iso).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });

function MediaPicker({ post, onSave }: { post: TgPostT; onSave: (b: Record<string, unknown>) => void }) {
  const [kind, setKind] = useState<"image" | "video" | "tg">("image");
  const [material, setMaterial] = useState(post.material || "");
  const [src, setSrc] = useState<SrcItem[] | null>(null);
  useEffect(() => {
    if (kind !== "tg") return;
    api.get<SrcData>(`/api/content-factory/sources/?material=${encodeURIComponent(material)}`)
      .then((d) => setSrc(d.items.filter((i) => i.kind === "photo" || i.kind === "video"))).catch(() => setSrc([]));
  }, [kind, material]);
  const [data, setData] = useState<{ items: TgPhoto[]; materials: string[] } | null>(null);
  useEffect(() => {
    if (kind === "tg") return;
    api.get<{ items: TgPhoto[]; materials: string[] }>(`/api/content-factory/telegram/media/?kind=${kind}&material=${encodeURIComponent(material)}`)
      .then(setData).catch(() => setData({ items: [], materials: [] }));
  }, [kind, material]);
  const field = kind === "tg" ? "source_ids" : kind === "video" ? "video_ids" : "photo_ids";
  const chosen: number[] = kind === "tg" ? post.source_ids : kind === "video" ? post.video_ids : post.photo_ids;
  const toggle = (id: number) => onSave({ [field]: chosen.includes(id) ? chosen.filter((x) => x !== id) : [...chosen, id] });
  return (
    <div className="cf-picker">
      <div className="cf-set">
        <div className="cf-chips">
          <button type="button" className={"cf-chip" + (kind === "image" ? " on" : "")} onClick={() => setKind("image")}>Реальні фото</button>
          <button type="button" className={"cf-chip" + (kind === "video" ? " on" : "")} onClick={() => setKind("video")}>Відео</button>
          <button type="button" className={"cf-chip" + (kind === "tg" ? " on" : "")} onClick={() => setKind("tg")}>З груп Telegram</button>
        </div>
        <select className="cf-in" value={material} onChange={(e) => setMaterial(e.target.value)} aria-label="Матеріал">
          <option value="">Усі матеріали</option>
          {(data?.materials || []).map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="cf-pick-grid">
        {kind === "tg" ? (!src ? <span className="cf-kv">Завантажую…</span> : src.length === 0 ? <span className="cf-kv">Із груп ще нічого не прийшло</span>
          : src.map((s) => (
            <button key={s.id} type="button" className={chosen.includes(s.id) ? "on" : ""} title={s.caption} onClick={() => toggle(s.id)}>
              <img src={s.thumb_url} alt={s.caption} loading="lazy" />
            </button>)))
        : !data ? <span className="cf-kv">Завантажую…</span> : data.items.length === 0 ? <span className="cf-kv">Нічого немає</span>
          : data.items.map((m) => (
            <button key={m.id} type="button" className={chosen.includes(m.id) ? "on" : ""} title={m.title} onClick={() => toggle(m.id)}>
              <img src={m.preview_url || m.url} alt={m.title} loading="lazy" />
            </button>))}
      </div>
    </div>
  );
}

function Calendar({ posts }: { posts: TgPostT[] }) {
  const start = new Date(); start.setHours(0, 0, 0, 0);
  const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  const planned = posts.filter((p) => p.scheduled_at || p.published_at);
  const unplanned = posts.filter((p) => p.status === "approved" && !p.scheduled_at);
  return (
    <div className="cf-card">
      <h3>План публікацій · 7 днів</h3>
      <div className="cf-week">
        {days.map((d, i) => {
          const items = planned.filter((p) => { const w = new Date((p.published_at || p.scheduled_at) as string); return w.toDateString() === d.toDateString(); });
          return (
            <div key={i} className={"cf-day" + (i === 0 ? " today" : "")}>
              <b>{d.toLocaleDateString("uk-UA", { weekday: "short", day: "2-digit", month: "2-digit" })}</b>
              {items.map((p) => <div key={p.id} className={"cf-slot" + (p.published_at ? " pub" : "")}><i>{dayTime((p.published_at || p.scheduled_at) as string)}</i>{p.title}{p.published_at ? " ✓" : ""}</div>)}
            </div>);
        })}
      </div>
      {unplanned.length > 0 && <div className="cf-kv"><span>Схвалені без дати: {unplanned.map((p) => p.title).join(" · ")}</span></div>}
    </div>
  );
}

function NewPost({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const create = async () => {
    try { await api.post("/api/content-factory/telegram/posts/", { text }); setText(""); setOpen(false); onDone(); }
    catch (e: any) { setErr(e?.data?.error || "Не вдалося створити."); }
  };
  if (!open) return <button type="button" className="cf-btn ghost" onClick={() => setOpen(true)}>+ Пост вручну (без ШІ)</button>;
  return (
    <div className="cf-card">
      <h3>Новий пост вручну</h3>
      <textarea id="cf-new-post" className="cf-ta" style={{ minHeight: 140 }} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Перший рядок стане назвою. Фото й відео додасте після створення." aria-label="Текст нового поста" />
      <div className="cf-acts" style={{ justifyContent: "flex-start" }}>
        <button type="button" className="cf-btn gold" style={{ height: 32 }} disabled={!text.trim()} onClick={create}>Створити чернетку</button>
        <button type="button" className="cf-btn ghost" onClick={() => setOpen(false)}>Скасувати</button>
      </div>
      {err && <div className="cf-msg err">{err}</div>}
    </div>
  );
}

function TgPostCard({ post, channel, canPublish, onChanged }: { post: TgPostT; channel: string; canPublish: boolean; onChanged: () => void }) {
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(post.text);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [note, setNote] = useState("");
  const [picker, setPicker] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [when, setWhen] = useState(localInput(post.scheduled_at));
  useEffect(() => { setWhen(localInput(post.scheduled_at)); }, [post.scheduled_at]);
  const published = post.status === "published";
  useEffect(() => { setText(post.text); }, [post.text]);
  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true); setMsg(""); setNote("");
    try { await fn(); if (ok) setNote(ok); onChanged(); } catch (e: any) { setMsg(e?.data?.error || "Не вдалося."); } finally { setBusy(false); }
  };
  const patch = (b: Record<string, unknown>) => act(() => api.patch(`/api/content-factory/telegram/posts/${post.id}/`, b));
  const caption = post.text.length;
  return (
    <div className="cf-tg">
      <TgPreview post={{ ...post, text: edit ? text : post.text }} channel={channel} />
      <div className="cf-side">
        <div className="cf-role-h">
          <h4>{post.title}</h4>
          <span className={"cf-pill " + (post.status === "approved" ? "now" : "next")}>{post.status_display}</span>
        </div>
        {post.topic && <div className="cf-kv"><span>Питання клієнток</span><b style={{ fontWeight: 500 }}>{post.topic.title}</b></div>}
        <div className="cf-kv"><span>Медіа</span><b style={{ fontWeight: 500 }}>{post.videos.length ? `${post.videos.length} відео · ` : ""}{post.photos.length} фото{post.material ? " · " + post.material : ""}</b></div>
        {!published && (<>
          <div className="cf-media">
            {post.sources.map((s) => (
              <div key={"s" + s.id} className="cf-thumb"><img src={s.thumb_url} alt={s.caption} /><em>{s.kind === "video" ? "▶ TG" : "TG"}</em>
                <button type="button" aria-label="Прибрати" onClick={() => patch({ source_ids: post.source_ids.filter((x) => x !== s.id) })}>✕</button></div>))}
            {[...post.videos.map((m) => ({ ...m, v: true })), ...post.photos.map((m) => ({ ...m, v: false }))].map((m) => (
              <div key={(m.v ? "v" : "p") + m.id} className="cf-thumb"><img src={m.preview_url || m.url} alt={m.title} />{m.v && <em>▶ відео</em>}
                <button type="button" aria-label="Прибрати" onClick={() => patch(m.v ? { video_ids: post.video_ids.filter((x) => x !== m.id) } : { photo_ids: post.photo_ids.filter((x) => x !== m.id) })}>✕</button></div>))}
            <button type="button" className="cf-btn ghost" style={{ height: 64 }} onClick={() => setPicker(!picker)}>{picker ? "Готово" : "+ Фото / відео"}</button>
          </div>
          {picker && <MediaPicker post={post} onSave={(b) => patch(b)} />}
        </>)}
        {published && <div className="cf-kv"><span>Опубліковано</span><b>{new Date(post.published_at as string).toLocaleString("uk-UA")}</b></div>}
        {post.publish_error && <div className="cf-msg err">Остання спроба: {post.publish_error}</div>}
        <div className="cf-kv"><span>Довжина</span><b style={{ fontWeight: 500 }}>{caption} симв.{caption > 1024 ? " · довше підпису до фото — текст піде окремим повідомленням" : ""}</b></div>
        {post.checks.length > 0 && (<div><div className="cf-kv"><span>Перевірте перед публікацією</span></div>
          <ul className="cf-list warn">{post.checks.map((c, i) => <li key={i}>{c}</li>)}</ul></div>)}
        {post.facts.length > 0 && (<div><div className="cf-kv"><span>Звідки факти (база знань)</span></div>
          <ul className="cf-list">{post.facts.map((f, i) => <li key={i}>{f}</li>)}</ul></div>)}
        {edit && <textarea id={`cf-tg-text-${post.id}`} className="cf-ta" value={text} onChange={(e) => setText(e.target.value)} aria-label="Текст поста" />}
        {!published && <div className="cf-acts" style={{ justifyContent: "flex-start" }}>
          {edit ? (<>
            <button type="button" className="cf-btn gold" style={{ height: 32 }} disabled={busy} onClick={() => patch({ text }).then(() => setEdit(false))}>Зберегти текст</button>
            <button type="button" className="cf-btn ghost" onClick={() => { setText(post.text); setEdit(false); }}>Скасувати</button>
          </>) : (<>
            <button type="button" className="cf-btn ghost" onClick={() => setEdit(true)}>Редагувати текст</button>
            <button type="button" className="cf-btn ghost" disabled={busy} onClick={() => act(() => api.post(`/api/content-factory/telegram/posts/${post.id}/photos/`))}>Інші фото · безкоштовно</button>
            {post.status !== "approved"
              ? <button type="button" className="cf-btn gold" style={{ height: 32 }} disabled={busy} onClick={() => patch({ status: "approved" })}>Схвалити</button>
              : <button type="button" className="cf-btn ghost" disabled={busy} onClick={() => patch({ status: "draft" })}>Повернути в чернетки</button>}
            <button type="button" className="cf-btn ghost" disabled={busy} onClick={() => patch({ status: "rejected" })}>Відхилити</button>
          </>)}
        </div>}
        {post.status === "approved" && canPublish && (
          <div className="cf-set">
            <input id={`cf-when-${post.id}`} type="datetime-local" className="cf-in" value={when} onChange={(e) => setWhen(e.target.value)} aria-label="Дата і час публікації" />
            <button type="button" className="cf-btn ghost" disabled={busy || !when} onClick={() => act(() => api.patch(`/api/content-factory/telegram/posts/${post.id}/`, { scheduled_at: when }), "Заплановано")}>
              {post.scheduled_at ? "Змінити час" : "Запланувати"}</button>
            {post.scheduled_at && <button type="button" className="cf-btn ghost" disabled={busy} onClick={() => act(() => api.patch(`/api/content-factory/telegram/posts/${post.id}/`, { scheduled_at: null }))}>Прибрати з плану</button>}
            <button type="button" className="cf-btn ghost" disabled={busy} onClick={() => act(() => api.post(`/api/content-factory/telegram/posts/${post.id}/test/`), "Надіслано вам у Telegram — перевірте, як виглядає")}>Надіслати мені</button>
            {confirm ? (<>
              <button type="button" className="cf-btn gold" style={{ height: 32 }} disabled={busy} onClick={() => { setConfirm(false); act(() => api.post(`/api/content-factory/telegram/posts/${post.id}/publish/`), "Опубліковано в " + channel); }}>Так, опублікувати в {channel}</button>
              <button type="button" className="cf-btn ghost" onClick={() => setConfirm(false)}>Ні</button>
            </>) : <button type="button" className="cf-btn gold" style={{ height: 32 }} disabled={busy} onClick={() => setConfirm(true)}>Опублікувати зараз</button>}
          </div>
        )}
        {post.status !== "approved" && !published && <div className="cf-kv"><span>Щоб запланувати чи опублікувати — спершу «Схвалити».</span></div>}
        {note && <div className="cf-msg ok" role="status">{note}</div>}
        {msg && <div className="cf-msg err" role="alert">{msg}</div>}
      </div>
    </div>
  );
}

function Telegram() {
  const [data, setData] = useState<TgData | null>(null);
  const [sub, setSub] = useState<"work" | "pub">("work");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [budget, setBudget] = useState("");
  const load = useCallback(async () => {
    try { const d = await api.get<TgData>("/api/content-factory/telegram/"); setData(d); setBudget(String(d.settings.monthly_budget_usd)); }
    catch { setMsg({ ok: false, text: "Не вдалося завантажити автопілот." }); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const save = async (b: Record<string, unknown>) => {
    try { await api.patch("/api/content-factory/telegram/settings/", b); load(); }
    catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося зберегти." }); }
  };
  const draft = async () => {
    setBusy(true); setMsg(null);
    try { const p: any = await api.post("/api/content-factory/telegram/draft/"); setMsg({ ok: true, text: `Готово: «${p.title}»` }); load(); }
    catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося створити чернетку." }); }
    finally { setBusy(false); }
  };
  if (!data) return <div className="cf-empty">Завантажую…</div>;
  const s = data.settings;
  const pct = s.monthly_budget_usd > 0 ? Math.min(100, (s.spent_month_usd / s.monthly_budget_usd) * 100) : 100;
  const tabs = (
    <div className="cf-sub-tabs" role="tablist">
      <button type="button" role="tab" aria-selected={sub === "work"} className={"cf-chip" + (sub === "work" ? " on" : "")} onClick={() => setSub("work")}>Чернетки і план</button>
      <button type="button" role="tab" aria-selected={sub === "pub"} className={"cf-chip" + (sub === "pub" ? " on" : "")} onClick={() => setSub("pub")}>Опубліковані й аналітика</button>
    </div>);
  if (sub === "pub") return (<><div><h1 className="cf-h1">Telegram-автопілот</h1></div>{tabs}<Published /></>);
  return (
    <>
      <div>
        <h1 className="cf-h1">Telegram-автопілот</h1>
        <p className="cf-sub">Щоранку — чернетка поста для {s.channel} з питання, яке клієнтки ставлять найчастіше. Факти лише з бази знань,
          фото — лише реальні обʼєкти з бібліотеки. Ви правите, схвалюєте й публікуєте одразу або за планом через @wallcov_smm_bot.</p>
      </div>
      {tabs}
      <div className="cf-q-top">
        <div className="cf-card">
          <h3>Автопілот · витрати</h3>
          <div className="cf-kv"><span>Щоранкова чернетка</span>
            <span className={"cf-pill " + (s.daily_drafts ? "now" : "next")}>{s.daily_drafts ? "увімкнено · 08:10" : "вимкнено"}</span></div>
          <div className="cf-kv"><span>Витрачено цього місяця</span><b>{usd(s.spent_month_usd)} з {usd(s.monthly_budget_usd)}</b></div>
          <div className="cf-meter" aria-hidden="true"><i style={{ width: pct + "%" }} /></div>
          <div className="cf-set">
            <select id="cf-tg-model" className="cf-in" value={s.model} onChange={(e) => save({ model: e.target.value })} aria-label="Модель ШІ">
              {s.models.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <label className="cf-kv" htmlFor="cf-tg-budget" style={{ alignItems: "center" }}>ліміт $/міс</label>
            <input id="cf-tg-budget" className="cf-in" style={{ width: 70 }} inputMode="decimal" value={budget}
              onChange={(e) => setBudget(e.target.value)} onBlur={() => budget !== String(s.monthly_budget_usd) && save({ monthly_budget_usd: budget })} />
            <button type="button" className={"cf-btn " + (s.daily_drafts ? "ghost" : "gold")} style={{ height: 32 }}
              onClick={() => save({ daily_drafts: !s.daily_drafts })}>{s.daily_drafts ? "Вимкнути" : "Увімкнути щоранку"}</button>
          </div>
        </div>
        <div className="cf-card">
          <h3>Наступний пост</h3>
          <div className="cf-kv"><span>Тема</span><b style={{ fontWeight: 500, textAlign: "right" }}>{data.next_topic ? data.next_topic.title : "нових тем немає"}</b></div>
          <div className="cf-kv"><span>Питали за 7 днів</span><b>{data.next_topic ? data.next_topic.count_7d : "—"}</b></div>
          <div className="cf-kv"><span>Ціна чернетки</span><b>≈ {usd(s.estimate_usd)}</b></div>
          <button type="button" className="cf-btn gold" disabled={busy || !data.next_topic} onClick={draft}>{busy ? "Пишу пост…" : "Створити чернетку"}</button>
          {msg && <div className={"cf-msg " + (msg.ok ? "ok" : "err")} role="status">{msg.text}</div>}
        </div>
      </div>
      <Calendar posts={data.posts} />
      {!s.publish_enabled && <div className="cf-msg err">Бот для публікації не підключений — публікація недоступна.</div>}
      <NewPost onDone={load} />
      {data.posts.length ? data.posts.map((p) => <TgPostCard key={p.id} post={p} channel={s.channel} canPublish={s.publish_enabled} onChanged={load} />)
        : <div className="cf-empty">Чернеток ще немає — натисніть «Створити чернетку».</div>}
    </>
  );
}

function Spark({ points }: { points: (number | null)[] }) {
  const v = points.filter((x): x is number => x != null);
  if (v.length < 2) return <span className="cf-kv">ще мало даних</span>;
  const max = Math.max(...v), min = Math.min(...v), w = 120, h = 34;
  const xy = v.map((y, i) => `${(i / (v.length - 1)) * (w - 4) + 2},${h - 3 - ((y - min) / (max - min || 1)) * (h - 8)}`);
  return (
    <svg className="cf-spark" viewBox={`0 0 ${w} ${h}`} aria-label="Ріст переглядів">
      <polyline points={xy.join(" ")} fill="none" stroke="#e3b85f" strokeWidth="2" strokeLinejoin="round" />
      <circle cx={xy[xy.length - 1].split(",")[0]} cy={xy[xy.length - 1].split(",")[1]} r="3" fill="#e3b85f" />
    </svg>
  );
}

function Published() {
  const [data, setData] = useState<PubData | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { try { setData(await api.get<PubData>("/api/content-factory/telegram/published/")); } catch { setData({ posts: [], summary: { count: 0, avg_views: null, total_reactions: 0, best: null } }); } }, []);
  useEffect(() => { load(); }, [load]);
  const refresh = async () => { setBusy(true); try { await api.post("/api/content-factory/telegram/published/"); await load(); } finally { setBusy(false); } };
  if (!data) return <div className="cf-empty">Завантажую…</div>;
  const s = data.summary;
  return (
    <>
      <div className="cf-kpis">
        <div className="cf-kpi"><span>Опубліковано з CRM</span><b>{s.count}</b></div>
        <div className="cf-kpi"><span>Середньо переглядів</span><b>{s.avg_views ?? "—"}</b></div>
        <div className="cf-kpi"><span>Реакцій разом</span><b>{s.total_reactions}</b></div>
        <div className="cf-kpi"><span>Найкращий</span><b style={{ fontSize: 13 }}>{s.best ? `${s.best.title} · ${s.best.views}` : "—"}</b></div>
      </div>
      <div className="cf-set">
        <button type="button" className="cf-btn ghost" disabled={busy} onClick={refresh}>{busy ? "Оновлюю…" : "Оновити цифри зараз"}</button>
        <span className="cf-kv">Перегляди й реакції — з публічної сторінки каналу: перший тиждень щогодини, далі раз на добу.</span>
      </div>
      {data.posts.length === 0 ? <div className="cf-empty">Опублікованих з CRM постів ще немає.</div> : data.posts.map((p) => {
        const thumb = p.sources[0]?.thumb_url || p.photos[0]?.preview_url || p.videos[0]?.preview_url || "";
        return (
          <div key={p.id}>
            <div className="cf-pub">
              {thumb ? <img src={thumb} alt="" /> : <div className="cf-thumb" />}
              <div style={{ minWidth: 0 }}>
                <b>{p.title}</b>
                <div className="cf-kv"><span>{p.published_at ? new Date(p.published_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : ""}
                  {p.topic ? ` · питання: ${p.topic.title}` : ""}</span></div>
                <div className="cf-acts" style={{ justifyContent: "flex-start" }}>
                  {p.tg_link && <a href={p.tg_link} target="_blank" rel="noreferrer">Відкрити в Telegram ↗</a>}
                  <button type="button" className="cf-btn ghost" style={{ height: 24, fontSize: 11 }} onClick={() => setOpen(open === p.id ? null : p.id)}>{open === p.id ? "Сховати" : "Деталі"}</button>
                </div>
              </div>
              <div className="big">{p.views ?? "—"}<small>переглядів{p.views_24h != null ? ` · ${p.views_24h} за добу` : ""}</small></div>
              <div className="big" style={{ fontSize: 15 }}>{Object.entries(p.reactions_detail || {}).map(([e, n]) => `${e} ${n}`).join("  ") || "—"}<small>реакції</small></div>
              <Spark points={(p.history || []).map((h) => h.views)} />
            </div>
            {open === p.id && (
              <div className="cf-tg" style={{ marginTop: 6 }}>
                <TgPreview post={p} channel="@wallcovpro" />
                <div className="cf-side">
                  <div className="cf-kv"><span>Медіа</span><b>{p.sources.length + p.photos.length + p.videos.length}</b></div>
                  <div className="cf-kv"><span>Останнє оновлення цифр</span><b>{p.stats_at ? new Date(p.stats_at).toLocaleString("uk-UA") : "ще не було"}</b></div>
                  {p.facts.length > 0 && <ul className="cf-list">{p.facts.map((f, i) => <li key={i}>{f}</li>)}</ul>}
                  <div className="cf-kv"><span>Знімки</span></div>
                  <ul className="cf-list">{(p.history || []).slice(-8).map((h, i) => <li key={i}>{new Date(h.at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} — {h.views ?? "—"} переглядів, {h.reactions ?? 0} реакцій</li>)}</ul>
                </div>
              </div>)}
          </div>);
      })}
    </>
  );
}

function DriveBlock({ data, reload }: { data: SrcData; reload: () => void }) {
  const [link, setLink] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const add = async () => {
    setMsg(null);
    try { await api.post("/api/content-factory/sources/drive/", { link }); setLink(""); setMsg({ ok: true, text: "Папку додано" }); reload(); }
    catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося додати." }); }
  };
  const sync = async () => {
    try { const r: any = await api.post("/api/content-factory/sources/drive/sync/"); setMsg({ ok: true, text: r.note }); }
    catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося запустити." }); }
  };
  const toggle = async (f: DriveFolderT) => { await api.patch(`/api/content-factory/sources/drive/${f.id}/`, { enabled: !f.enabled }); reload(); };
  return (
    <div className="cf-card">
      <h3>Google Drive</h3>
      {data.drive_folders.map((f) => (
        <div key={f.id} className="cf-chatrow">
          <span><a href={f.link} target="_blank" rel="noreferrer" style={{ color: "var(--cf-blue)" }}>{f.title}</a>
            <span style={{ color: "var(--cf-ink3)" }}> · {f.files_count} файлів{f.last_sync_at ? "" : " · ще не оновлювалась"}{f.last_error ? " · " + f.last_error : ""}</span></span>
          <button type="button" className="cf-btn ghost" style={{ height: 28 }} onClick={() => toggle(f)}>{f.enabled ? "Вимкнути" : "Увімкнути"}</button>
        </div>))}
      <div className="cf-set">
        <input id="cf-drive-link" className="cf-in" style={{ flex: 1, minWidth: 260 }} placeholder="Посилання на папку Google Drive" value={link} onChange={(e) => setLink(e.target.value)} />
        <button type="button" className="cf-btn gold" style={{ height: 32 }} disabled={!link.trim()} onClick={add}>Додати</button>
        <button type="button" className="cf-btn ghost" onClick={sync}>Оновити зараз</button>
      </div>
      <div className="cf-kv"><span>Папку потрібно відкрити (Поділитися → Читач) для <b style={{ userSelect: "all" }}>{data.drive_email || "—"}</b>. Файли не копіюються — лише посилання.</span></div>
      {msg && <div className={"cf-msg " + (msg.ok ? "ok" : "err")}>{msg.text}</div>}
    </div>
  );
}

function Sources() {
  const [data, setData] = useState<SrcData | null>(null);
  const [f, setF] = useState({ origin: "", chat: "", material: "", kind: "", q: "" });
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v) as [string, string][]).toString();
    try { setData(await api.get<SrcData>(`/api/content-factory/sources/?${qs}`)); setErr(""); }
    catch { setErr("Не вдалося завантажити джерела."); }
  }, [f]);
  useEffect(() => { load(); }, [load]);
  const toggleChat = async (id: number, enabled: boolean) => {
    try { await api.patch(`/api/content-factory/sources/chats/${id}/`, { enabled }); load(); }
    catch (e: any) { setErr(e?.data?.error || "Не вдалося змінити."); }
  };
  const hide = async (id: number) => { await api.patch(`/api/content-factory/sources/${id}/`, { hidden: true }); load(); };
  return (
    <>
      <div>
        <h1 className="cf-h1">Джерела контенту</h1>
        <p className="cf-sub">Фото й відео з ваших Telegram-груп, каналу й папок Google Drive. Файли лишаються там — CRM зберігає лише посилання й підпис,
          тож сервер не навантажується. Що ви пишете під фото, стає мітками: матеріал, кімната, етап, #хештеги.</p>
      </div>
      {err && <div className="cf-msg err" role="alert">{err}</div>}
      <div className="cf-q-top">
        <div className="cf-card">
          <h3>Чати</h3>
          {!data ? <div className="cf-kv">Завантажую…</div> : data.chats.length === 0
            ? <div className="cf-kv"><span>Бот ще не бачив жодної групи.</span></div>
            : data.chats.map((c) => (
              <div key={c.id} className="cf-chatrow">
                <span>{c.title}{c.username ? ` · @${c.username}` : ""} <span style={{ color: "var(--cf-ink3)" }}>· {c.count} файлів</span></span>
                <button type="button" className={"cf-btn " + (c.enabled ? "ghost" : "gold")} style={{ height: 30 }}
                  onClick={() => toggleChat(c.id, !c.enabled)}>{c.enabled ? "Вимкнути" : "Приймати файли"}</button>
              </div>))}
        </div>
        <div className="cf-card">
          <h3>Як підключити групу</h3>
          <ol className="cf-steps">
            <li>Відкрийте групу в Telegram → Керування → Адміністратори → Додати → @wallcov_smm_bot.</li>
            <li>Надішліть у групу будь-яке фото — група зʼявиться зліва.</li>
            <li>Натисніть «Приймати файли». Далі кожне нове фото чи відео потрапляє сюди саме.</li>
          </ol>
          <div className="cf-kv"><span>Бот бачить лише нові повідомлення — старі файли групи підтягнемо окремо.</span></div>
          {data && !data.ingest_ready && <div className="cf-msg err">Приймання ще не підключене на сервері.</div>}
        </div>
      </div>
      {data && <DriveBlock data={data} reload={load} />}
      <div className="cf-set">
        <select className="cf-in" value={f.origin} onChange={(e) => setF({ ...f, origin: e.target.value, chat: "" })} aria-label="Джерело">
          <option value="">Telegram і Drive</option><option value="telegram">Лише Telegram</option><option value="drive">Лише Google Drive</option>
        </select>
        <select className="cf-in" value={f.chat} onChange={(e) => setF({ ...f, chat: e.target.value })} aria-label="Чат">
          <option value="">Усі чати</option>{(data?.chats || []).map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
        <select className="cf-in" value={f.material} onChange={(e) => setF({ ...f, material: e.target.value })} aria-label="Матеріал">
          <option value="">Усі матеріали</option>{(data?.materials || []).map((m) => <option key={m.name} value={m.name}>{m.name} · {m.count}</option>)}
        </select>
        <select className="cf-in" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} aria-label="Тип">
          <option value="">Фото й відео</option><option value="photo">Фото</option><option value="video">Відео</option><option value="document">Файли</option>
        </select>
        <input id="cf-src-q" className="cf-in" style={{ width: 220 }} placeholder="Пошук у підписах" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        <span className="cf-kv">{data ? `${data.total} файлів` : ""}</span>
      </div>
      {!data ? null : data.items.length === 0 ? <div className="cf-empty">Поки порожньо — підключіть групу за інструкцією вище.</div> : (
        <div className="cf-src-grid">
          {data.items.map((s) => (
            <div key={s.id} className="cf-src">
              <div className="ph">{s.thumb_url ? <img src={s.thumb_url} alt={s.caption} loading="lazy" /> : s.kind_display}
                <span>{s.kind === "video" ? `▶ ${s.duration ?? ""}с` : s.kind_display}</span></div>
              <div className="bd">
                <div className="cap">{s.caption || <em style={{ color: "var(--cf-ink3)" }}>без підпису</em>}</div>
                <div className="cf-tags">{s.material && <span className="cf-tag kb">{s.material}</span>}{s.tags.map((t) => <span key={t} className="cf-tag">{t}</span>)}</div>
                <div className="cf-kv"><a href={s.link} target="_blank" rel="noreferrer">{s.chat} ↗</a>
                  <button type="button" className="cf-btn ghost" style={{ height: 24, fontSize: 11 }} onClick={() => hide(s.id)}>Сховати</button></div>
              </div>
            </div>))}
        </div>)}
    </>
  );
}

const fmtN = (n: number | null | undefined) => n == null ? "—" : n >= 1e6 ? (n / 1e6).toFixed(1) + " млн" : n >= 1e3 ? Math.round(n / 1e3) + " тис" : String(n);

function Feed() {
  const [q, setQ] = useState({ days: 7, sort: "outlier", status: "", all: false });
  const [data, setData] = useState<{ items: FeedT[]; total: number; tracked: number; last_sync_at: string | null; last_note: string } | null>(null);
  const [msg, setMsg] = useState("");
  const load = useCallback(async () => {
    try { setData(await api.get(`/api/content-factory/feed/?days=${q.days}&sort=${q.sort}&status=${q.status}${q.all ? "&all=1" : ""}`)); } catch { setMsg("Не вдалося завантажити стрічку."); }
  }, [q]);
  useEffect(() => { load(); }, [load]);
  const sync = async () => { try { const r: any = await api.post("/api/content-factory/feed/"); setMsg(r.note); } catch (e: any) { setMsg(e?.data?.error || "Не вдалося."); } };
  const mark = async (id: number, status: string) => { await api.patch(`/api/content-factory/feed/${id}/`, { status }); load(); };
  return (
    <>
      <div>
        <h1 className="cf-h1">Стрічка рекомендацій</h1>
        <p className="cf-sub">Ролики конкурентів і сторінок-натхнення з Virale. Жовта мітка «×3.4» — у скільки разів ролик набрав більше
          переглядів, ніж зазвичай у цього автора: це і є те, що «вистрілило». Зберігайте в ідеї — з них робитимемо рилси з ваших нарізок.</p>
      </div>
      <div className="cf-set">
        <div className="cf-chips">{[7, 30, 90].map((d) => <button key={d} type="button" className={"cf-chip" + (q.days === d ? " on" : "")} onClick={() => setQ({ ...q, days: d })}>{d} днів</button>)}</div>
        <select className="cf-in" value={q.sort} onChange={(e) => setQ({ ...q, sort: e.target.value })} aria-label="Сортування">
          <option value="outlier">Що вистрілило (×)</option><option value="views">Перегляди</option><option value="er">Залученість</option><option value="date">Нові</option>
        </select>
        <select className="cf-in" value={q.status} onChange={(e) => setQ({ ...q, status: e.target.value })} aria-label="Статус">
          <option value="">Усі</option><option value="saved">В ідеях</option><option value="used">Зроблено з наших</option><option value="hidden">Сховані</option>
        </select>
        <div className="cf-chips">
          <button type="button" className={"cf-chip" + (!q.all ? " on" : "")} onClick={() => setQ({ ...q, all: false })}>Мої сторінки{data ? ` · ${data.tracked}` : ""}</button>
          <button type="button" className={"cf-chip" + (q.all ? " on" : "")} onClick={() => setQ({ ...q, all: true })}>Усі з Virale</button>
        </div>
        <button type="button" className="cf-btn ghost" onClick={sync}>Оновити з Virale</button>
        <span className="cf-kv">{data ? `${data.total} роликів у базі${data.last_sync_at ? " · оновлено " + new Date(data.last_sync_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : " · ще не оновлювалась"}` : ""}</span>
      </div>
      {msg && <div className="cf-msg ok">{msg}</div>}
      {!data ? <div className="cf-empty">Завантажую…</div> : data.items.length === 0
        ? <div className="cf-empty">{data.total ? "За цей період нічого." : "Стрічка порожня — натисніть «Оновити з Virale»."}</div> : (
        <div className="cf-feed">
          {data.items.map((i) => (
            <div key={i.id} className="cf-fcard">
              <div className="ph">
                {i.preview_url && <img src={i.preview_url} alt="" loading="lazy" referrerPolicy="no-referrer" />}
                {i.x != null && <span className={"x" + (i.x < 1.5 ? " low" : "")}>×{i.x}</span>}
                <div className="hook">{(i.caption || "").split("\n")[0]}</div>
              </div>
              <div className="bd">
                <div className="cf-kv"><b>@{i.username}</b><span>{fmtN(i.views)}</span></div>
                <div className="cf-kv"><span>ER {i.engagement ?? "—"}% · {i.duration ? Math.round(i.duration) + " с" : i.media_type}</span>
                  <a href={i.url} target="_blank" rel="noreferrer">Відкрити ↗</a></div>
                <div className="cf-acts" style={{ justifyContent: "flex-start" }}>
                  {i.status !== "saved" ? <button type="button" className="cf-btn gold" style={{ height: 26, fontSize: 11.5 }} onClick={() => mark(i.id, "saved")}>В ідеї</button>
                    : <button type="button" className="cf-btn ghost" style={{ height: 26, fontSize: 11.5 }} onClick={() => mark(i.id, "new")}>З ідей</button>}
                  {i.status !== "hidden" && <button type="button" className="cf-btn ghost" style={{ height: 26, fontSize: 11.5 }} onClick={() => mark(i.id, "hidden")}>Сховати</button>}
                </div>
              </div>
            </div>))}
        </div>)}
    </>
  );
}

function Analyst() {
  const [data, setData] = useState<{ settings: any; reports: ReportT[] } | null>(null);
  const [pick, setPick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const load = useCallback(async () => { try { setData(await api.get("/api/content-factory/analyst/")); } catch { setMsg({ ok: false, text: "Не вдалося завантажити." }); } }, []);
  useEffect(() => { load(); }, [load]);
  const save = async (b: Record<string, unknown>) => { try { setData(await api.patch("/api/content-factory/analyst/", b)); } catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося." }); } };
  const make = async () => {
    setBusy(true); setMsg(null);
    try { setData(await api.post("/api/content-factory/analyst/", { days: 7 })); setPick(0); setMsg({ ok: true, text: "Звіт готовий" }); }
    catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося зробити звіт." }); } finally { setBusy(false); }
  };
  if (!data) return <div className="cf-empty">Завантажую…</div>;
  const s = data.settings;
  const r = data.reports[pick];
  const own = r?.inputs?.own || {};
  return (
    <>
      <div>
        <h1 className="cf-h1">Аналітик</h1>
        <p className="cf-sub">Раз на тиждень ШІ дивиться на ваш Instagram, питання клієнтів, пости в Telegram і те, що вистрілило в ніші,
          і пише простими словами: що спрацювало, що ні — і 5 ідей на тиждень.</p>
      </div>
      <div className="cf-q-top">
        <div className="cf-card">
          <h3>Налаштування · витрати</h3>
          <div className="cf-kv"><span>Щопонеділка звіт</span><span className={"cf-pill " + (s.weekly_enabled ? "now" : "next")}>{s.weekly_enabled ? "увімкнено · 08:30" : "вимкнено"}</span></div>
          <div className="cf-kv"><span>Витрачено цього місяця</span><b>{usd(s.spent_month_usd)} з {usd(s.monthly_budget_usd)}</b></div>
          <div className="cf-set">
            <select className="cf-in" value={s.model} onChange={(e) => save({ model: e.target.value })} aria-label="Модель">{s.models.map(([v, l]: [string, string]) => <option key={v} value={v}>{l}</option>)}</select>
            <button type="button" className={"cf-btn " + (s.weekly_enabled ? "ghost" : "gold")} style={{ height: 32 }} onClick={() => save({ weekly_enabled: !s.weekly_enabled })}>{s.weekly_enabled ? "Вимкнути" : "Увімкнути щотижня"}</button>
          </div>
        </div>
        <div className="cf-card">
          <h3>Звіт зараз</h3>
          <div className="cf-kv"><span>Ціна одного звіту</span><b>≈ {usd(s.estimate_usd)}</b></div>
          <button type="button" className="cf-btn gold" disabled={busy} onClick={make}>{busy ? "Аналізую… (до хвилини)" : "Зробити звіт за тиждень"}</button>
          {msg && <div className={"cf-msg " + (msg.ok ? "ok" : "err")}>{msg.text}</div>}
        </div>
      </div>
      {!r ? <div className="cf-empty">Звітів ще немає.</div> : (<>
        <div className="cf-set">
          <select className="cf-in" value={pick} onChange={(e) => setPick(Number(e.target.value))} aria-label="Звіт">
            {data.reports.map((x, n) => <option key={x.id} value={n}>{new Date(x.created_at).toLocaleDateString("uk-UA")} · {x.period_days} днів</option>)}
          </select>
        </div>
        {own.followers != null && <div className="cf-kpis">
          <div className="cf-kpi"><span>Підписники</span><b>{fmtN(own.followers)}</b></div>
          <div className="cf-kpi"><span>Медіана переглядів</span><b>{fmtN(own.medianViews)}</b></div>
          <div className="cf-kpi"><span>Медіана ніші</span><b>{fmtN(r.inputs?.niche?.views_p50)}</b></div>
          <div className="cf-kpi"><span>Постів на тиждень</span><b>{own.postsPerWeek ?? "—"}</b></div>
        </div>}
        <div className="cf-card"><h3>Що відбувається</h3><div className="cf-rep">{r.summary}</div></div>
        <div className="cf-card"><h3>5 ідей на тиждень</h3>
          {r.ideas.map((i, n) => (
            <div key={n} className="cf-idea"><span className="n">{n + 1}</span>
              <div><b>{i.title}</b>{i.format && <span className="cf-tag" style={{ marginLeft: 8 }}>{i.format}</span>}{i.material && <span className="cf-tag kb" style={{ marginLeft: 6 }}>{i.material}</span>}
                <p>Гачок: «{i.hook}»</p><p>Чому: {i.why}</p></div>
            </div>))}
        </div>
      </>)}
    </>
  );
}

function Reels() {
  const [data, setData] = useState<{ reels: ReelT[]; materials: { name: string; videos: number }[]; marked: Record<string, number>; scenes: number; spent_month_usd: number; ideas: { title: string; material: string }[] } | null>(null);
  const [topic, setTopic] = useState("");
  const [material, setMaterial] = useState("Галатея");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const load = useCallback(async () => { try { setData(await api.get("/api/content-factory/reels/")); } catch { setMsg({ ok: false, text: "Не вдалося завантажити." }); } }, []);
  useEffect(() => { load(); }, [load]);
  const make = async () => {
    setMsg(null);
    try { const r: any = await api.post("/api/content-factory/reels/", { topic, material }); setMsg({ ok: true, text: r.note + " Оновіть сторінку за кілька хвилин." }); }
    catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося." }); }
  };
  const act = async (r: ReelT, b: Record<string, unknown>) => { await api.patch(`/api/content-factory/reels/${r.id}/`, b); load(); };
  const sendMe = async (r: ReelT) => {
    try { const x: any = await api.post(`/api/content-factory/reels/${r.id}/test/`); setMsg({ ok: true, text: x.note }); }
    catch (e: any) { setMsg({ ok: false, text: e?.data?.error || "Не вдалося надіслати." }); }
  };
  if (!data) return <div className="cf-empty">Завантажую…</div>;
  return (
    <>
      <div>
        <h1 className="cf-h1">Рилси з ваших нарізок</h1>
        <p className="cf-sub">ШІ один раз переглядає відео потрібного матеріалу й запамʼятовує, що на якій секунді. Потім пише сценарій на 12–16 секунд
          (факти лише з бази знань), підбирає кадри й монтує 9:16 з великими субтитрами. Стіна в кадрі — завжди справжня. Музику додасте в Instagram.</p>
      </div>
      <div className="cf-card">
        <h3>Новий рилс</h3>
        <div className="cf-set">
          <input id="cf-reel-topic" className="cf-in" style={{ flex: 1, minWidth: 260 }} placeholder="Тема: наприклад «Чи видно шви на Галатеї»" value={topic} onChange={(e) => setTopic(e.target.value)} />
          <select id="cf-reel-mat" className="cf-in" value={material} onChange={(e) => setMaterial(e.target.value)} aria-label="Матеріал">
            {data.materials.map((m) => <option key={m.name} value={m.name}>{m.name} · {m.videos} відео · розмічено {data.marked[m.name] || 0}</option>)}
          </select>
          <button type="button" className="cf-btn gold" style={{ height: 38 }} disabled={!topic.trim()} onClick={make}>Зробити рилс</button>
        </div>
        {data.ideas.length > 0 && <div className="cf-chips">{data.ideas.map((i) => <button key={i.title} type="button" className="cf-chip" onClick={() => { setTopic(i.title); if (i.material) setMaterial(i.material); }}>💡 {i.title}</button>)}</div>}
        <div className="cf-kv"><span>Розмічено сцен: {data.scenes} · витрачено цього місяця {usd(data.spent_month_usd)} · один рилс ≈ $0.05–0.15 (перший раз по матеріалу — дорожче через розмітку)</span></div>
        {msg && <div className={"cf-msg " + (msg.ok ? "ok" : "err")}>{msg.text}</div>}
      </div>
      {data.reels.length === 0 ? <div className="cf-empty">Рилсів ще немає.</div> : data.reels.map((r) => (
        <div key={r.id} className="cf-reel">
          {r.video_url ? <video src={r.video_url} controls playsInline preload="metadata" /> : <div className="cf-empty">{r.error || "без відео"}</div>}
          <div className="cf-side">
            <div className="cf-role-h"><h4>{r.title}</h4><span className={"cf-pill " + (r.status === "approved" ? "now" : "next")}>{r.status_display}</span></div>
            <div className="cf-kv"><span>{r.material} · {r.duration ? `${r.duration} с` : ""} · {new Date(r.created_at).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span></div>
            {r.error && <div className="cf-msg err">{r.error}</div>}
            <div>{r.beats.map((b, n) => (
              <div key={n} className="cf-beat"><i>{b.seconds}с</i><div>{b.text}<small>кадр: {b.what}{b.source ? <> · <a href={b.source} target="_blank" rel="noreferrer" style={{ color: "var(--cf-blue)" }}>оригінал ↗</a></> : null}</small></div></div>))}</div>
            {r.caption && <div className="cf-card" style={{ padding: 10 }}><h3>Підпис</h3><div className="cf-rep" style={{ fontSize: 13 }}>{r.caption}</div></div>}
            {r.facts.filter((f) => f.startsWith("Перевірити")).length > 0 && <ul className="cf-list warn">{r.facts.filter((f) => f.startsWith("Перевірити")).map((f, i) => <li key={i}>{f}</li>)}</ul>}
            <div className="cf-acts" style={{ justifyContent: "flex-start" }}>
              {r.video_url && <button type="button" className="cf-btn ghost" onClick={() => sendMe(r)}>Надіслати мені в Telegram</button>}
              {r.status !== "approved" && r.video_url && <button type="button" className="cf-btn gold" style={{ height: 32 }} onClick={() => act(r, { status: "approved" })}>Схвалити</button>}
              {r.status !== "rejected" && <button type="button" className="cf-btn ghost" onClick={() => act(r, { status: "rejected" })}>Відхилити</button>}
            </div>
          </div>
        </div>))}
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
        <div className="cf-page">
        {err && <div className="cf-msg err" role="alert">{err}</div>}
        {section.id === "studio" ? <Studio ov={ov} go={go} />
          : section.id === "channels" ? <Channels data={list} reload={load} />
          : section.id === "questions" ? <Questions />
          : section.id === "telegram" ? <Telegram />
          : section.id === "sources" ? <Sources />
          : section.id === "feed" ? <Feed />
          : section.id === "analyst" ? <Analyst />
          : section.id === "reels" ? <Reels />
          : <Soon s={section} />}
        </div>
      </main>
    </div>
  );
}
