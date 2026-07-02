/* Слідкує за новою версією фронта. Коли задеплоєно новий бандл (змінюються хеші /assets/*.js),
   показує тост «Оновити» — гарантує що ВИПРАВЛЕННЯ доходять до ВСІХ співробітників навіть у
   давно відкритій вкладці, без ручного Ctrl+Shift+R. Монтується в Layout (для всіх залогінених). */
import { useEffect, useRef, useState } from "react";
import { useLang } from "./i18n";

function assetsOf(html: string): string {
  return (html.match(/\/assets\/[A-Za-z0-9_.-]+\.js/g) || []).sort().join("|");
}

export default function VersionWatcher() {
  const { t } = useLang();
  const [stale, setStale] = useState(false);
  const baseline = useRef<string>("");

  useEffect(() => {
    let stop = false;
    async function fetchAssets(): Promise<string> {
      const html = await fetch("/index.html?_=" + Date.now(), { cache: "no-store" }).then((r) => r.text());
      return assetsOf(html);
    }
    (async () => { try { baseline.current = await fetchAssets(); } catch { /* */ } })();
    async function check() {
      try {
        const fresh = await fetchAssets();
        if (baseline.current && fresh && fresh !== baseline.current) setStale(true);
      } catch { /* мовчки */ }
    }
    const tm = setInterval(() => { if (!stop && document.visibilityState !== "hidden") check(); }, 180000);
    return () => { stop = true; clearInterval(tm); };
  }, []);

  if (!stale) return null;
  return (
    <div style={{ position: "fixed", bottom: 18, left: "50%", transform: "translateX(-50%)", zIndex: 100001, background: "#0f172a", color: "#fff", borderRadius: 12, boxShadow: "0 12px 40px rgba(0,0,0,.35)", padding: "11px 16px", display: "flex", alignItems: "center", gap: 14, maxWidth: "94vw" }}>
      <span style={{ fontSize: 18 }}>✨</span>
      <span style={{ fontSize: 13.5 }}>{t("Доступно обновление CRM", "Доступне оновлення CRM")}</span>
      <button onClick={() => location.reload()} style={{ background: "#C67D5F", color: "#fff", border: "none", borderRadius: 8, padding: "7px 14px", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>{t("Обновить сейчас", "Оновити зараз")}</button>
    </div>
  );
}
