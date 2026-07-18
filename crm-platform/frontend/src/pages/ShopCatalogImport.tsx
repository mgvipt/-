import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { Icon } from "../Icon";
import { useLang } from "../i18n";

type ImportRow = {
  id: number; sheet_name: string; source_row: number; external_id: string;
  product_id: number | null; product_name: string; sku: string; current_price: string | null;
  source_data: Record<string, unknown>; proposed_data: Record<string, any>;
  warnings: string[]; errors: string[]; applied_at: string | null;
};

type ImportBatch = {
  id: number; source_name: string; source_hash: string; status: string;
  created_at: string; updated_at: string;
  summary: { rows: number; matched: number; unmatched: number; warnings: number; errors: number; price_changes: number; applied: number };
  rows?: ImportRow[];
};

const money = (value: unknown) => value === null || value === undefined || value === "" ? "—" : `${Number(value).toLocaleString("uk-UA", { maximumFractionDigits: 2 })} ₴`;
type EditorSection = "main" | "price" | "customer" | "service";
const editorSections: Array<[EditorSection, string, string]> = [
  ["main", "1. Основное", "Название, статус и категория"],
  ["price", "2. Цена и расход", "Упаковка, единицы и расчёт"],
  ["customer", "3. Для покупателя", "Что увидит и поймёт клиент"],
  ["service", "4. Служебные данные", "Остальные поля исходной таблицы"],
];
function editorGroup(key: string): EditorSection {
  const name = key.toLowerCase();
  if (/цена|расход|фасов|модель|мыть|износ|упаков|кг|м²|(^|\s)литр/.test(name)) return "price";
  if (/клиент|покуп|эффект|ассоц|рекоменд|использ|нанос|финиш|альтернатив/.test(name)) return "customer";
  if (/id|sku|статус|категор|внутреннее название|название$|товар/.test(name)) return "main";
  return "service";
}
const fieldHelp = (key: string) => {
  const name = key.toLowerCase();
  if (name.includes("клиент")) return "Это название увидит покупатель — пишите коротко и понятно.";
  if (name.includes("расход")) return "Укажите реальный диапазон: минимальное значение не должно быть больше максимального.";
  if (name.includes("цена")) return "После проверки значение сохранится в карточке CRM; на сайт попадёт только опубликованный товар.";
  if (name.includes("внутрен")) return "Служебное название для команды. Покупатель его не увидит.";
  return "";
};

export default function ShopCatalogImport({ canEdit, onApplied }: { canEdit: boolean; onApplied: () => void }) {
  const { t } = useLang();
  const inputRef = useRef<HTMLInputElement>(null);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [editor, setEditor] = useState<ImportRow | null>(null);
  const [editorData, setEditorData] = useState<Record<string, unknown>>({});
  const [editorSection, setEditorSection] = useState<EditorSection>("main");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [open, setOpen] = useState(true);

  async function loadBatches() {
    const list = await api.get<ImportBatch[]>("/api/shop-import/batches/");
    setBatches(list);
    if (!batch && list[0]) await openBatch(list[0].id);
  }

  async function openBatch(id: number) {
    const detail = await api.get<ImportBatch>(`/api/shop-import/batches/${id}/`);
    setBatch(detail); setSelected([]); setMessage("");
  }

  useEffect(() => { loadBatches(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  async function upload(file?: File) {
    if (!file) return;
    setBusy(true); setMessage("");
    try {
      const detail = await api.upload<ImportBatch>("/api/shop-import/upload/", file);
      setBatch(detail); setSelected([]); await loadBatches();
      setMessage(t("Таблица загружена только для проверки. Товары ещё не изменены.", "Таблицю завантажено лише для перевірки. Товари ще не змінено."));
    } catch (error: any) {
      setMessage(error?.message || t("Не удалось прочитать таблицу", "Не вдалося прочитати таблицю"));
    } finally { setBusy(false); }
  }

  async function saveRow() {
    if (!editor) return;
    setBusy(true);
    try {
      const updated = await api.patch<ImportRow>(`/api/shop-import/rows/${editor.id}/`, { source_data: editorData });
      setBatch(current => current ? { ...current, rows: (current.rows || []).map(row => row.id === updated.id ? updated : row) } : current);
      setEditor(updated); setEditorData(updated.source_data);
      const refreshed = batch ? await api.get<ImportBatch>(`/api/shop-import/batches/${batch.id}/`) : null;
      if (refreshed) setBatch(refreshed);
      setMessage(updated.errors.length ? t("Строка сохранена, но в ней ещё есть ошибки.", "Рядок збережено, але в ньому ще є помилки.") : t("Строка исправлена и готова к сохранению.", "Рядок виправлено й готовий до збереження."));
    } finally { setBusy(false); }
  }

  async function applySelected() {
    if (!batch || !selected.length) return;
    if (!window.confirm(t(`Сохранить выбранные позиции в карточках CRM: ${selected.length}? На сайт попадут только товары, у которых отдельно включено «Показывать на сайте».`, `Зберегти вибрані позиції у картках CRM: ${selected.length}? На сайт потраплять лише товари, для яких окремо ввімкнено «Показувати на сайті».`))) return;
    setBusy(true); setMessage("");
    try {
      const result = await api.post<{ applied: number; batch: ImportBatch }>(`/api/shop-import/batches/${batch.id}/apply/`, { confirm: true, row_ids: selected });
      setBatch(result.batch); setSelected([]); onApplied();
      setMessage(t(`Сохранено позиций: ${result.applied}.`, `Збережено позицій: ${result.applied}.`));
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || t("Не удалось сохранить: проверьте отмеченные строки", "Не вдалося зберегти: перевірте позначені рядки"));
    } finally { setBusy(false); }
  }

  const rows = batch?.rows || [];
  const readyRows = useMemo(() => rows.filter(row => !row.applied_at && row.product_id && row.errors.length === 0), [rows]);
  const allReadySelected = readyRows.length > 0 && readyRows.every(row => selected.includes(row.id));

  return <div className="panel" style={{ margin: "18px 0 0", padding: 0, overflow: "hidden" }}>
    <button onClick={() => setOpen(value => !value)} style={{ width: "100%", border: 0, background: "linear-gradient(135deg,#eff6ff,#fff7ed)", padding: "17px 18px", display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer", color: "#0f172a" }}>
      <span style={{ textAlign: "left" }}><b style={{ fontSize: 17 }}>1. {t("Проверить цены и описания из таблицы", "Перевірити ціни й описи з таблиці")}</b><small style={{ display: "block", color: "#64748b", marginTop: 4 }}>{t("Сначала сверяем и исправляем, затем сохраняем выбранные карточки", "Спочатку звіряємо й виправляємо, потім зберігаємо вибрані картки")}</small></span>
      <span style={{ fontSize: 20 }}>{open ? "−" : "+"}</span>
    </button>
    {open && <div style={{ padding: 18 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: 10 }}>
        {[
          ["1", t("Загрузите Excel", "Завантажте Excel"), t("Файл попадёт только в черновик проверки", "Файл потрапить лише до чернетки перевірки")],
          ["2", t("Исправьте красные строки", "Виправте червоні рядки"), t("Откройте строку и проверьте каждый столбец", "Відкрийте рядок і перевірте кожен стовпець")],
          ["3", t("Отметьте и сохраните", "Позначте та збережіть"), t("Без подтверждения CRM и сайт не меняются", "Без підтвердження CRM і сайт не змінюються")],
        ].map(([n, title, text]) => <div key={n} style={{ border: "1px solid #e2e8f0", borderRadius: 12, padding: 12, display: "flex", gap: 10 }}><span style={{ width: 28, height: 28, borderRadius: 20, background: "#2563eb", color: "white", display: "grid", placeItems: "center", fontWeight: 800, flexShrink: 0 }}>{n}</span><span><b>{title}</b><small style={{ display: "block", color: "#64748b", marginTop: 3 }}>{text}</small></span></div>)}
      </div>

      <div style={{ display: "flex", gap: 9, alignItems: "center", marginTop: 14, flexWrap: "wrap" }}>
        {canEdit && <><input ref={inputRef} hidden type="file" accept=".xlsx,.xlsm" onChange={event => { upload(event.target.files?.[0]); event.target.value = ""; }} /><button className="btn btn-primary" disabled={busy} onClick={() => inputRef.current?.click()}><Icon n="upload" /> {busy ? t("Обрабатываю…", "Обробляю…") : t("Загрузить новую таблицу", "Завантажити нову таблицю")}</button></>}
        {batches.length > 0 && <select value={batch?.id || ""} onChange={event => openBatch(Number(event.target.value))} style={{ height: 38, minWidth: 260 }}><option value="">{t("Выберите проверку", "Оберіть перевірку")}</option>{batches.map(item => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {item.source_name}</option>)}</select>}
        {message && <span style={{ color: message.includes("Не удалось") ? "#b91c1c" : "#166534", fontSize: 13 }}>{message}</span>}
      </div>

      {batch && <>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 8, marginTop: 14 }}>
          {[
            [t("Всего строк", "Усього рядків"), batch.summary.rows, "#334155"],
            [t("Найдено в CRM", "Знайдено в CRM"), batch.summary.matched, "#15803d"],
            [t("Цены отличаются", "Ціни відрізняються"), batch.summary.price_changes, "#d97706"],
            [t("Нужно исправить", "Потрібно виправити"), batch.summary.errors, "#b91c1c"],
            [t("Уже сохранено", "Уже збережено"), batch.summary.applied, "#2563eb"],
          ].map(([label, value, color]) => <div key={String(label)} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 10 }}><small style={{ color: "#64748b" }}>{label}</small><div style={{ fontWeight: 850, fontSize: 23, color: String(color), marginTop: 3 }}>{value}</div></div>)}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", marginTop: 14, flexWrap: "wrap" }}>
          <label style={{ fontSize: 13 }}><input type="checkbox" checked={allReadySelected} onChange={event => setSelected(event.target.checked ? readyRows.map(row => row.id) : [])} /> {t("Выбрать все строки без ошибок", "Обрати всі рядки без помилок")}</label>
          {canEdit && <button className="btn btn-primary" disabled={busy || selected.length === 0} onClick={applySelected}>{t(`Сохранить выбранные (${selected.length})`, `Зберегти вибрані (${selected.length})`)}</button>}
        </div>

        <div style={{ overflowX: "auto", marginTop: 10, border: "1px solid #e2e8f0", borderRadius: 10 }}><table style={{ width: "100%", borderCollapse: "collapse", minWidth: 950 }}>
          <thead><tr style={{ background: "#f8fafc", textAlign: "left", fontSize: 12, color: "#64748b" }}><th style={{ padding: 10 }}></th><th>{t("Лист / строка", "Аркуш / рядок")}</th><th>{t("Товар в CRM", "Товар у CRM")}</th><th>{t("Текущая цена", "Поточна ціна")}</th><th>{t("Цена из таблицы", "Ціна з таблиці")}</th><th>{t("Проверка", "Перевірка")}</th><th></th></tr></thead>
          <tbody>{rows.map(row => {
            const sourcePrice = row.sheet_name === "Материалы" ? row.source_data["Цена за кг, грн"] : row.source_data["Цена, грн"];
            const isReady = row.product_id && row.errors.length === 0 && !row.applied_at;
            return <tr key={row.id} style={{ borderTop: "1px solid #e2e8f0", background: row.errors.length ? "#fff7f7" : row.applied_at ? "#f0fdf4" : "white" }}>
              <td style={{ padding: 10 }}><input disabled={!isReady} type="checkbox" checked={selected.includes(row.id)} onChange={event => setSelected(current => event.target.checked ? [...current, row.id] : current.filter(id => id !== row.id))} /></td>
              <td style={{ fontSize: 12 }}>{row.sheet_name}<br/><span style={{ color: "#94a3b8" }}>#{row.source_row} · ID {row.external_id}</span></td>
              <td style={{ padding: "9px 6px", maxWidth: 280 }}><b>{row.product_name || t("Не найден", "Не знайдено")}</b><small style={{ display: "block", color: "#64748b" }}>{row.sku}</small></td>
              <td>{money(row.current_price)}</td><td><b>{money(sourcePrice)}</b></td>
              <td style={{ padding: "9px 6px", maxWidth: 360 }}>{row.applied_at ? <span style={{ color: "#15803d" }}>✓ {t("Сохранено", "Збережено")}</span> : <>{row.errors.map(error => <div key={error} style={{ color: "#b91c1c", fontSize: 12 }}>● {error}</div>)}{row.warnings.map(warning => <div key={warning} style={{ color: "#b45309", fontSize: 12 }}>● {warning}</div>)}{!row.errors.length && !row.warnings.length && <span style={{ color: "#15803d" }}>✓ {t("Совпадает", "Збігається")}</span>}</>}</td>
              <td style={{ padding: 8, textAlign: "right" }}><button className="btn btn-light" onClick={() => { setEditor(row); setEditorData({ ...row.source_data }); setEditorSection(row.errors.length ? "price" : "main"); }}>{t("Открыть понятную карточку", "Відкрити зрозумілу картку")}</button></td>
            </tr>;
          })}</tbody>
        </table></div>
      </>}
    </div>}

    {editor && <ProductReviewDrawer editor={editor} data={editorData} setData={setEditorData} section={editorSection} setSection={setEditorSection} canEdit={canEdit} busy={busy} onSave={saveRow} onClose={() => setEditor(null)} t={t} />}
  </div>;
}

function ProductReviewDrawer({ editor, data, setData, section, setSection, canEdit, busy, onSave, onClose, t }: { editor: ImportRow; data: Record<string, unknown>; setData: React.Dispatch<React.SetStateAction<Record<string, unknown>>>; section: EditorSection; setSection: (value: EditorSection) => void; canEdit: boolean; busy: boolean; onSave: () => void; onClose: () => void; t: (ru: string, uk: string) => string }) {
  const entries = Object.entries(data);
  const visibleEntries = entries.filter(([key]) => editorGroup(key) === section);
  const minKey = entries.find(([key]) => /расход min/i.test(key))?.[0];
  const maxKey = entries.find(([key]) => /расход max/i.test(key))?.[0];
  const minValue = minKey ? Number(data[minKey]) : NaN;
  const maxValue = maxKey ? Number(data[maxKey]) : NaN;
  const inverted = Number.isFinite(minValue) && Number.isFinite(maxValue) && minValue > maxValue;
  const clientName = String(entries.find(([key]) => /клиент.*назван|назван.*клиент/i.test(key))?.[1] || editor.product_name || "");
  const packagePrice = entries.find(([key]) => /^цена за кг/i.test(key))?.[1] ?? entries.find(([key]) => /^цена, грн$/i.test(key))?.[1] ?? entries.find(([key]) => /^цена от/i.test(key))?.[1];
  const swapConsumption = () => { if (minKey && maxKey) setData(current => ({ ...current, [minKey]: current[maxKey], [maxKey]: current[minKey] })); };
  return <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 100, background: "rgba(15,23,42,.58)", display: "flex", justifyContent: "flex-end" }}><div onClick={event => event.stopPropagation()} style={{ width: "min(980px,98vw)", height: "100%", overflow: "auto", background: "#f7f8fa", color: "#0f172a", display: "flex", flexDirection: "column" }}>
    <header style={{ position: "sticky", top: 0, zIndex: 4, background: "rgba(255,255,255,.97)", borderBottom: "1px solid #e2e8f0", padding: "17px 20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}><div><div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginBottom: 7 }}><span style={{ padding: "4px 8px", borderRadius: 12, background: "#eff6ff", color: "#1d4ed8", fontSize: 11, fontWeight: 800 }}>ИЗ EXCEL</span><span style={{ padding: "4px 8px", borderRadius: 12, background: editor.product_id ? "#ecfdf5" : "#fef2f2", color: editor.product_id ? "#15803d" : "#b91c1c", fontSize: 11, fontWeight: 800 }}>{editor.product_id ? "НАЙДЕН В CRM" : "НЕ НАЙДЕН В CRM"}</span>{editor.errors.length > 0 && <span style={{ padding: "4px 8px", borderRadius: 12, background: "#fef2f2", color: "#b91c1c", fontSize: 11, fontWeight: 800 }}>НУЖНО ИСПРАВИТЬ: {editor.errors.length}</span>}</div><h2 style={{ margin: 0, fontSize: 22 }}>{clientName || t("Товар без понятного названия", "Товар без зрозумілої назви")}</h2><small style={{ color: "#64748b" }}>SKU {editor.sku || editor.external_id} · {editor.sheet_name}, {t("строка", "рядок")} {editor.source_row}</small></div><button className="btn btn-light" onClick={onClose} aria-label="Закрыть">✕</button></div>
    </header>

    <div style={{ padding: 18 }}>
      <div style={{ padding: 14, borderRadius: 12, background: editor.errors.length ? "#fff1f2" : "#ecfdf5", border: `1px solid ${editor.errors.length ? "#fecdd3" : "#bbf7d0"}` }}>{editor.errors.length ? <><b style={{ color: "#b91c1c" }}>Что нужно исправить</b>{editor.errors.map(error => <div key={error} style={{ color: "#b91c1c", marginTop: 5 }}>● {error}</div>)}{inverted && <button className="btn" onClick={swapConsumption} style={{ marginTop: 10, background: "#fff", border: "1px solid #fda4af", color: "#be123c" }}>Поменять минимальный и максимальный расход местами</button>}</> : <span style={{ color: "#15803d", fontWeight: 750 }}>✓ Данные прошли проверку. Их можно сохранить в карточку CRM.</span>}</div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 9, margin: "14px 0" }}>
        <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 12, padding: 12 }}><small className="muted">Сейчас в CRM</small><div style={{ fontWeight: 850, fontSize: 20, marginTop: 4 }}>{money(editor.current_price)}</div></div>
        <div style={{ background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 12, padding: 12 }}><small style={{ color: "#9a3412" }}>Цена из таблицы</small><div style={{ fontWeight: 850, fontSize: 20, marginTop: 4 }}>{money(packagePrice)}</div></div>
        <div style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 12, padding: 12 }}><small className="muted">Расход на 1 м²</small><div style={{ fontWeight: 850, fontSize: 20, marginTop: 4 }}>{Number.isFinite(minValue) ? minValue : "—"}–{Number.isFinite(maxValue) ? maxValue : "—"} кг</div></div>
      </div>

      <nav style={{ display: "flex", gap: 7, overflowX: "auto", paddingBottom: 4, marginBottom: 14 }}>{editorSections.map(([key,title,description]) => <button key={key} onClick={() => setSection(key)} className={section === key ? "btn btn-primary" : "btn btn-light"} style={{ height: "auto", minHeight: 44, padding: "7px 11px", flexShrink: 0 }}><span style={{ textAlign: "left" }}><b style={{ display: "block" }}>{title}</b><small style={{ opacity: .78 }}>{description}</small></span></button>)}</nav>

      <section style={{ background: "white", border: "1px solid #e2e8f0", borderRadius: 14, padding: 17 }}>
        <h3 style={{ margin: "0 0 4px" }}>{editorSections.find(([key]) => key === section)?.[1]}</h3><p className="muted" style={{ margin: "0 0 15px", fontSize: 13 }}>{section === "price" ? "Проверьте цену, единицу продажи и реальный расход. Система пересчитает строку после сохранения черновика." : section === "customer" ? "Эти данные помогают покупателю понять товар простыми словами." : section === "service" ? "Исходные поля для команды. Они не должны запутывать покупателя на сайте." : "Сначала убедитесь, что выбран правильный товар и категория."}</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 12 }}>{visibleEntries.map(([key,value]) => { const text=String(value ?? ""); const numeric=/цена|расход|кг|м²|id/i.test(key) && text.length < 30; const multiline=text.length>75 || /опис|комментар|рекоменд|где использовать|когда/i.test(key); return <label key={key} style={{ fontSize: 12, color: "#475569" }}><b style={{ display: "block", marginBottom: 5, color: "#334155" }}>{key}</b>{multiline ? <textarea disabled={!canEdit || !!editor.applied_at} rows={3} value={text} onChange={event => setData(current => ({ ...current, [key]: event.target.value }))} style={{ width: "100%" }} /> : <input disabled={!canEdit || !!editor.applied_at} inputMode={numeric ? "decimal" : "text"} value={text} onChange={event => setData(current => ({ ...current, [key]: event.target.value }))} style={{ width: "100%", height: 40 }} />}{fieldHelp(key) && <small style={{ display: "block", marginTop: 4, color: "#64748b" }}>{fieldHelp(key)}</small>}{inverted && (key===minKey || key===maxKey) && <small style={{ display: "block", marginTop: 4, color: "#b91c1c", fontWeight: 750 }}>Минимальный расход должен быть меньше или равен максимальному.</small>}</label>; })}</div>
      </section>
    </div>

    <footer style={{ position: "sticky", bottom: 0, zIndex: 4, marginTop: "auto", background: "rgba(255,255,255,.97)", borderTop: "1px solid #e2e8f0", padding: "13px 18px", display: "flex", alignItems: "center", gap: 9, justifyContent: "flex-end", flexWrap: "wrap" }}><span style={{ marginRight: "auto", fontSize: 12, color: editor.errors.length ? "#b91c1c" : "#15803d" }}>{editor.errors.length ? `Исправьте ошибок: ${editor.errors.length}, затем перепроверьте строку` : "После сохранения данные останутся в проверке до общего подтверждения"}</span><button className="btn btn-light" onClick={onClose}>Закрыть без изменений</button>{canEdit && !editor.applied_at && <button className="btn btn-primary" disabled={busy} onClick={onSave}>{busy ? t("Проверяю…", "Перевіряю…") : t("Сохранить и перепроверить", "Зберегти й перевірити")}</button>}</footer>
  </div></div>;
}
