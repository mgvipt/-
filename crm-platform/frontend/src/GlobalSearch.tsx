/* Глибокий пошук по CRM: сделки / ліди / клієнти. Випадашка під полем у шапці. */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";
import { useLang } from "./i18n";
import { Icon } from "./Icon";

export default function GlobalSearch() {
  const nav = useNavigate();
  const { t } = useLang();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<any>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const [mopen, setMopen] = useState(false);
  const isMob = typeof window !== "undefined" && window.innerWidth <= 768;

  useEffect(() => {
    if (q.trim().length < 2) { setRes(null); setLoading(false); return; }
    setLoading(true);
    const tm = setTimeout(() => {
      api.get<any>(`/api/search/?q=${encodeURIComponent(q.trim())}`)
        .then((d) => { setRes(d); setOpen(true); })
        .catch(() => {})
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(tm);
  }, [q]);

  useEffect(() => {
    function onDoc(e: MouseEvent) { if (box.current && !box.current.contains(e.target as any)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function go(path: string) { setOpen(false); setQ(""); setRes(null); nav(path); }
  const empty = res && !res.deals.length && !res.leads.length && !res.clients.length;

  const resultsInner = (
    <>
      {loading && !res && <div className="muted" style={{ padding: 12, fontSize: 13 }}>{t("Поиск…", "Пошук…")}</div>}
      {empty && <div className="muted" style={{ padding: 12, fontSize: 13 }}>{t("Ничего не найдено", "Нічого не знайдено")}</div>}
      {res?.deals?.length > 0 && <Group title={<><Icon n="🤝" size={15} /> {t("Сделки", "Угоди")}</>} />}
      {res?.deals?.map((d: any) => (
        <Row key={"d" + d.id} onClick={() => go(`/deals/${d.id}`)} main={`#${d.id} · ${d.title}`} sub={`${d.client || ""}${d.stage ? " · " + d.stage : ""}`} right={d.amount ? `${Number(d.amount).toLocaleString("uk-UA")} ₴` : ""} />
      ))}
      {res?.leads?.length > 0 && <Group title={<><Icon n="📋" size={15} /> {t("Лиды", "Ліди")}</>} />}
      {res?.leads?.map((l: any) => (
        <Row key={"l" + l.id} onClick={() => go(`/leads/${l.id}`)} main={`#${l.id} · ${l.title}`} sub={`${l.client || ""}${l.stage ? " · " + l.stage : ""}`} />
      ))}
      {res?.clients?.length > 0 && <Group title={<><Icon n="👥" size={15} /> {t("Клиенты", "Клієнти")}</>} />}
      {res?.clients?.map((c: any) => (
        <Row key={"c" + c.id} onClick={() => go(`/clients/${c.id}`)} main={c.name} sub={`${c.phone || ""}${c.deals ? " · " + t("угод:", "угод:") + " " + c.deals : ""}`} />
      ))}
    </>
  );
  const inp = <input className="search" style={{ width: isMob ? "100%" : undefined }} value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => res && setOpen(true)} placeholder={t("Поиск по CRM (сделки, лиды, клиенты)…", "Пошук по CRM (угоди, ліди, клієнти)…")} />;
  if (isMob) return (
    <>
      <button className="btn btn-light" onClick={() => setMopen(true)} title={t("Поиск по CRM", "Пошук по CRM")} style={{ padding: "6px 9px" }}><Icon n="🔍" size={16} /></button>
      {mopen && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 1200, padding: 12 }} onClick={() => setMopen(false)}>
          <div className="panel" style={{ background: "#fff", maxWidth: 560, margin: "6px auto", padding: 12 }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
              <div style={{ flex: 1 }}>{inp}</div>
              <button onClick={() => setMopen(false)} style={{ border: "none", background: "none", fontSize: 22, color: "#94a3b8", cursor: "pointer" }}>✕</button>
            </div>
            <div style={{ maxHeight: "72vh", overflowY: "auto" }}>{resultsInner}</div>
          </div>
        </div>
      )}
    </>
  );
  return (
    <div ref={box} style={{ position: "relative" }}>
      {inp}
      {open && (res || loading) && (
        <div style={{ position: "absolute", top: 40, right: 0, width: 430, maxHeight: 470, overflowY: "auto", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 12px 36px rgba(15,23,42,.18)", zIndex: 80, padding: 6 }}>
          {resultsInner}
        </div>
      )}
    </div>
  );
}

function Group({ title }: any) {
  return <div style={{ fontSize: 11, color: "#94a3b8", padding: "6px 8px 2px", fontWeight: 600 }}>{title}</div>;
}
function Row({ main, sub, right, onClick }: any) {
  return (
    <div onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 8px", borderRadius: 7, cursor: "pointer", fontSize: 13 }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "#f1f5f9")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{main}</div>
        {sub && <div className="muted" style={{ fontSize: 11, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sub}</div>}
      </div>
      {right && <b style={{ fontSize: 12, whiteSpace: "nowrap" }}>{right}</b>}
    </div>
  );
}
