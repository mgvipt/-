import { useState } from "react";
export interface Entry {
  id: number; date: string; section_key?: string; section?: string;
  title_uk?: string; title_ru?: string; body_uk?: string; body_ru?: string;
  title?: string; body?: string; // legacy fallback
}

function renderLine(line: string, key: number) {
  const img = line.trim().match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
  if (img) {
    return (
      <a key={key} href={img[2]} target="_blank" rel="noreferrer" style={{ display: "block", margin: "10px 0" }}>
        <img src={img[2]} alt={img[1]} loading="lazy" style={{ maxWidth: "100%", borderRadius: 10, border: "1px solid #e2e8f0", boxShadow: "0 1px 4px rgba(0,0,0,.08)", cursor: "zoom-in" }} />
        {img[1] && <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>{img[1]}</div>}
      </a>
    );
  }
  const isBullet = line.trimStart().startsWith("- ");
  const text = isBullet ? line.trimStart().slice(2) : line;
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  const spans = parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <b key={i} style={{ color: "#0f172a" }}>{p.slice(2, -2)}</b>
      : <span key={i}>{p}</span>
  );
  if (isBullet) {
    return (
      <div key={key} style={{ display: "flex", gap: 8, margin: "3px 0", lineHeight: 1.5 }}>
        <span style={{ color: "var(--brand, #C67D5F)", flexShrink: 0 }}>•</span>
        <span>{spans}</span>
      </div>
    );
  }
  return <div key={key} style={{ margin: "6px 0", lineHeight: 1.5 }}>{spans}</div>;
}

export function MaterialTraining({ items, lang }: { items: Entry[]; lang: string }) {
  const [category, setCategory] = useState("");
  const [brand, setBrand] = useState("");
  const [query, setQuery] = useState("");
  const uk = lang === "uk";
  const categories = [
    { key: "decor", label: uk ? "Декоративні покриття" : "Декоративные покрытия" },
    { key: "paints", label: uk ? "Фарби" : "Краски" },
    { key: "protection", label: uk ? "Захисні покриття" : "Защитные покрытия" },
    { key: "prep", label: uk ? "Ґрунти та підготовка" : "Грунты и подготовка" },
  ];
  const typeOf = (e: Entry) => e.section_key === "materials_anticatura" ? "decor" : (e.section_key || "").replace("materials_", "");
  const titleOf = (e: Entry) => (uk ? e.title_uk : e.title_ru) || e.title || "";
  const bodyOf = (e: Entry) => (uk ? e.body_uk : e.body_ru) || e.body || "";
  const search = query.trim().toLocaleLowerCase();
  const matches = items.filter(e => (!category || typeOf(e) === category) && (!brand || (brand === "anticatura" ? e.section_key === "materials_anticatura" : e.section_key !== "materials_anticatura")) && (!search || (titleOf(e) + " " + bodyOf(e)).toLocaleLowerCase().includes(search)));
  return <section className="panel" aria-label={uk ? "Навчання матеріалам" : "Обучение материалам"} style={{ marginBottom: 26 }}>
    <h2 style={{ marginTop: 0 }}>🎨 {uk ? "Матеріали · адаптація та навчання" : "Материалы · адаптация и обучение"}</h2>
    <p>{uk ? "Знайдіть матеріал, вивчіть його застосування та потренуйтеся пояснювати користь клієнту." : "Найдите материал, изучите его применение и потренируйтесь объяснять пользу клиенту."}</p>
    <ol style={{ lineHeight: 1.7, paddingLeft: 22 }}>
      <li>{uk ? "Оберіть категорію та відкрийте потрібний матеріал." : "Выберите категорию и откройте нужный материал."}</li>
      <li>{uk ? "Вивчіть: де застосовувати, як підготувати основу, які шари наносити та що отримує клієнт." : "Изучите: где применять, как подготовить основание, какие слои наносить и что получает клиент."}</li>
      <li>{uk ? "Пройдіть самоперевірку в кінці картки. Перед рекомендацією звірте техкарту та зразок." : "Пройдите самопроверку в конце карточки. Перед рекомендацией сверьте техкарту и образец."}</li>
    </ol>
    <input aria-label={uk ? "Пошук матеріалів" : "Поиск материалов"} placeholder={uk ? "Назва матеріалу, ефект або застосування…" : "Название материала, эффект или применение…"} value={query} onChange={e => setQuery(e.target.value)} style={{ width: "100%", boxSizing: "border-box", padding: 12, border: "1px solid #cbd5e1", borderRadius: 10, marginBottom: 12 }} />
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
      <button style={chip(!category)} onClick={() => { setCategory(""); setBrand(""); }}>{uk ? "Усі матеріали" : "Все материалы"} · {items.length}</button>
      {categories.map(c => <button key={c.key} style={chip(category === c.key)} onClick={() => { setCategory(c.key); setBrand(""); }}>{c.label} · {items.filter(e => typeOf(e) === c.key).length}</button>)}
    </div>
    {category === "decor" && <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
      <button style={chip(!brand)} onClick={() => setBrand("")}>{uk ? "Усі декоративні" : "Все декоративные"}</button>
      <button style={chip(brand === "wallcov")} onClick={() => setBrand("wallcov")}>WALLCOV</button>
      <button style={chip(brand === "anticatura")} onClick={() => setBrand("anticatura")}>ANTICATURA</button>
    </div>}
    <p className="muted">{uk ? "Знайдено" : "Найдено"}: {matches.length}</p>
    {categories.filter(c => !category || category === c.key).map(c => {
      const list = matches.filter(e => typeOf(e) === c.key);
      if (!list.length) return null;
      const sections = c.key === "decor" ? ["wallcov", "anticatura"] : [""];
      return <div key={c.key}><h3>{c.label}</h3>{sections.map(b => {
        const entries = list.filter(e => !b || (b === "anticatura" ? e.section_key === "materials_anticatura" : e.section_key !== "materials_anticatura")).sort((a, z) => titleOf(a).localeCompare(titleOf(z), "uk"));
        if (!entries.length) return null;
        return <div key={b}>{b && <h4>{b === "anticatura" ? "ANTICATURA" : "WALLCOV"}</h4>}{entries.map(e => <details key={e.id} style={{ padding: "12px 14px", border: "1px solid #e2e8f0", borderRadius: 10, marginBottom: 8 }}>
          <summary style={{ cursor: "pointer", fontWeight: 700 }}>{titleOf(e)}</summary>
          <div style={{ fontSize: 14, color: "#475569", marginTop: 12 }}>{bodyOf(e).split("\n").map((ln, i) => renderLine(ln, i))}</div>
          <div style={{ padding: 12, marginTop: 14, background: "#f8fafc", borderRadius: 8 }}>
            <b>{uk ? "Самоперевірка" : "Самопроверка"}</b>
            <ol style={{ paddingLeft: 20, lineHeight: 1.6 }}>
              <li>{uk ? "Для якої поверхні та задачі підійде цей матеріал?" : "Для какой поверхности и задачи подойдет этот материал?"}</li>
              <li>{uk ? "Які підготовка, шари та захист потрібні? Що ще треба уточнити?" : "Какие подготовка, слои и защита нужны? Что еще нужно уточнить?"}</li>
              <li>{uk ? "Як пояснити користь клієнту двома реченнями без непідтверджених обіцянок?" : "Как объяснить пользу клиенту двумя предложениями без неподтвержденных обещаний?"}</li>
            </ol>
          </div>
        </details>)}</div>;
      })}</div>;
    })}
  </section>;
}

function chip(on: boolean): React.CSSProperties {
  return {
    cursor: "pointer", userSelect: "none", fontSize: 13, fontWeight: 700,
    padding: "6px 13px", borderRadius: 999, whiteSpace: "nowrap",
    background: on ? "var(--brand, #C67D5F)" : "#fff",
    color: on ? "#fff" : "#475569",
    border: "1.5px solid " + (on ? "var(--brand, #C67D5F)" : "#e2e8f0"),
  };
}
