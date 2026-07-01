/* Спільна логіка чату — щоб «Відкриті лінії» і чат у картці сделки поводились ОДНАКОВО.
 * Змінив тут → змінилось в обох місцях. */

// Клікабельні посилання у тексті повідомлення
export function linkify(text: string, _out?: boolean) {
  return String(text || "").split(/(https?:\/\/[^\s]+)/g).map((p, i) =>
    /^https?:\/\//.test(p)
      ? <a key={i} href={p} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} style={{ color: "#1d4ed8", textDecoration: "underline", wordBreak: "break-all" }}>{p}</a>
      : <span key={i}>{p}</span>);
}

// Підпис-роздільник дати: Сьогодні / Вчора / 29 червня
export function dayLabel(iso: any, t: any) {
  if (!iso) return "";
  const dt = new Date(iso), now = new Date(), y = new Date();
  y.setDate(now.getDate() - 1);
  const sd = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (sd(dt, now)) return t("Сегодня", "Сьогодні");
  if (sd(dt, y)) return t("Вчера", "Вчора");
  return dt.toLocaleDateString("uk", { day: "numeric", month: "long", ...(dt.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}) });
}

// Час повідомлення HH:MM
export function timeLabel(iso: any) {
  return iso ? new Date(iso).toLocaleTimeString("uk", { hour: "2-digit", minute: "2-digit" }) : "";
}

// Чи новий день порівняно з попереднім повідомленням (для роздільника)
export function isNewDay(cur: any, prev: any) {
  if (!prev) return true;
  return new Date(cur).toDateString() !== new Date(prev).toDateString();
}

export const SNDR_MAP: any = { ai_assistant: "Юля (AI)", operator: "Менеджер", bot: "Бот" };

// Вікно Instagram/Facebook 24г: чи можна писати першим
export function metaWindow(active: any, msgs: any[]) {
  if (!active || !["instagram", "facebook"].includes(active.channel_kind || "")) return null;
  let li: any = null;
  for (let i = msgs.length - 1; i >= 0; i--) { if (msgs[i].direction === "in") { li = msgs[i]; break; } }
  const hrs = li && li.created_at ? (Date.now() - new Date(li.created_at).getTime()) / 3600000 : 999;
  return { hrs: Math.floor(hrs), closed: hrs > 24 };
}
