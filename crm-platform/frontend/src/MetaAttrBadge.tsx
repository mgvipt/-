/* Бейдж «звідки клієнт» (14.09.2026, meta-attr):
 *   🎯 З реклами Meta (оголошення …)  — Meta передала мітку оголошення (точно);
 *   🟡 Ймовірно з реклами             — перше повідомлення = текст кнопки з реклами (Meta мітку не дала);
 *   🌿 Органіка                        — Meta прислала повідомлення без даних реклами;
 *   ❔ Невідомо                        — даних немає (напр. чат ChatPlace до 22.08).
 * attr — meta_attribution ліда/угоди (рахуємо на місці, без запиту);
 * contactId / convId — запит /api/meta-attr/… (клієнт/чат: і ліди, і угоди, і чати). */
import { useEffect, useState, CSSProperties } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

type Summary = { class: string; ad?: any; phrase?: string; attributed_at?: string; method?: string };

export function classifyMetaAttr(attr: any): string {
  const a = attr && typeof attr === "object" ? attr : {};
  if (a.source_kind === "paid_ad" || a.source_kind === "lead_form") return "meta_ad";
  if (a.class === "meta_ad_likely" || a.source_kind === "likely_ad") return "meta_ad_likely";
  if (a.source_kind === "organic") return "organic";
  return "unknown";
}

export default function MetaAttrBadge({ attr, ad, source, contactId, convId, hideExact, compact, style }: {
  attr?: any; ad?: any; source?: string; contactId?: number | null; convId?: number | null;
  hideExact?: boolean; compact?: boolean; style?: CSSProperties;
}) {
  const { t } = useLang();
  const url = convId ? `/api/meta-attr/conversation/${convId}/` : contactId ? `/api/meta-attr/contact/${contactId}/` : "";
  const [remote, setRemote] = useState<Summary | null>(null);
  useEffect(() => {
    setRemote(null);
    if (!url) return;
    let alive = true;
    api.get<Summary>(url).then((r) => { if (alive) setRemote(r); }).catch(() => { /* бейдж не критичний */ });
    return () => { alive = false; };
  }, [url]);

  let s: Summary | null = null;
  if (url) s = remote;
  else if (attr && typeof attr === "object" && Object.keys(attr).length) {
    s = { class: classifyMetaAttr(attr), ad: ad || null, phrase: attr.phrase, attributed_at: attr.attributed_at, method: attr.method || attr.source_context };
  } else if (source === "instagram" || source === "facebook") s = { class: "unknown" };
  if (!s || s.class === "none") return null;
  if (hideExact && s.class === "meta_ad") return null;

  const adName = s.ad ? (s.ad.title || s.ad.ad_name || s.ad.campaign || s.ad.ad_id || "") : ((attr && (attr.ad_title || attr.ad_id)) || "");
  const when = s.attributed_at ? new Date(s.attributed_at).toLocaleDateString("uk-UA") : "";
  const phrase = s.phrase || "";
  const V: Record<string, { icon: string; text: string; short: string; bg: string; fg: string; bd: string; tip: string }> = {
    meta_ad: {
      icon: "🎯",
      text: adName ? t(`С рекламы Meta (объявление «${adName}»)`, `З реклами Meta (оголошення «${adName}»)`) : t("С рекламы Meta", "З реклами Meta"),
      short: t("Реклама", "Реклама"), bg: "#ecfdf5", fg: "#047857", bd: "#a7f3d0",
      tip: t("Meta передала метку объявления — клиент точно с рекламы", "Meta передала мітку оголошення — клієнт точно з реклами") + (adName ? ` · ${adName}` : "") + (when ? ` · ${when}` : ""),
    },
    meta_ad_likely: {
      icon: "🟡", text: t("Вероятно с рекламы", "Ймовірно з реклами"), short: t("Вероятно реклама", "Ймовірно реклама"),
      bg: "#fffbeb", fg: "#b45309", bd: "#fde68a",
      tip: (phrase ? t(`Первое сообщение «${phrase}» — текст кнопки из рекламы. `, `Перше повідомлення «${phrase}» — текст кнопки з реклами. `) : "")
        + t("Meta метку не передала, поэтому это вывод, а не подтверждение. В Meta не отправляется.", "Meta мітку не передала, тому це висновок, а не підтвердження. У Meta не відправляється.")
        + (when ? ` · ${when}` : ""),
    },
    organic: {
      icon: "🌿", text: t("Органика", "Органіка"), short: t("Органика", "Органіка"), bg: "#f5f3ff", fg: "#6d28d9", bd: "#ddd6fe",
      tip: t("Meta прислала сообщение без данных о рекламе", "Meta прислала повідомлення без даних про рекламу"),
    },
    unknown: {
      icon: "❔", text: t("Неизвестно", "Невідомо"), short: t("Неизвестно", "Невідомо"), bg: "#f8fafc", fg: "#64748b", bd: "#e2e8f0",
      tip: t("Нет данных, откуда пришёл клиент", "Немає даних, звідки прийшов клієнт"),
    },
  };
  const v = V[s.class] || V.unknown;
  return (
    <span title={v.tip} style={{
      display: "inline-flex", alignItems: "center", gap: 4, maxWidth: "100%", verticalAlign: "middle",
      fontSize: compact ? 10.5 : 12, fontWeight: 700, lineHeight: 1.3, padding: compact ? "1px 7px" : "3px 9px",
      borderRadius: 20, background: v.bg, color: v.fg, border: `1px solid ${v.bd}`,
      whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", ...(style || {}),
    }}>{v.icon} {compact ? v.short : v.text}</span>
  );
}
