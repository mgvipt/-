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

export default function ShopCatalogImport({ canEdit, onApplied }: { canEdit: boolean; onApplied: () => void }) {
  const { t } = useLang();
  const inputRef = useRef<HTMLInputElement>(null);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [batch, setBatch] = useState<ImportBatch | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [editor, setEditor] = useState<ImportRow | null>(null);
  const [editorData, setEditorData] = useState<Record<string, unknown>>({});
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
              <td style={{ padding: 8, textAlign: "right" }}><button className="btn btn-light" onClick={() => { setEditor(row); setEditorData({ ...row.source_data }); }}>{t("Проверить все поля", "Перевірити всі поля")}</button></td>
            </tr>;
          })}</tbody>
        </table></div>
      </>}
    </div>}

    {editor && <div onClick={() => setEditor(null)} style={{ position: "fixed", inset: 0, zIndex: 100, background: "rgba(15,23,42,.5)", display: "flex", justifyContent: "flex-end" }}><div onClick={event => event.stopPropagation()} style={{ width: "min(760px,97vw)", height: "100%", overflow: "auto", background: "white", padding: 20, color: "#0f172a" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><div><h2 style={{ margin: 0 }}>{editor.product_name || t("Строка без товара", "Рядок без товару")}</h2><small style={{ color: "#64748b" }}>{editor.sheet_name} · {t("строка", "рядок")} {editor.source_row} · ID {editor.external_id}</small></div><button className="btn btn-light" onClick={() => setEditor(null)}>✕</button></div>
      <div style={{ marginTop: 14, padding: 12, borderRadius: 10, background: editor.errors.length ? "#fef2f2" : "#ecfdf5" }}>{editor.errors.length ? editor.errors.map(error => <div key={error} style={{ color: "#b91c1c" }}>● {error}</div>) : <span style={{ color: "#15803d" }}>✓ {t("Строку можно сохранить", "Рядок можна зберегти")}</span>}</div>
      <p style={{ color: "#64748b", fontSize: 13 }}>{t("Здесь показан каждый столбец исходной таблицы. Исправьте значение и нажмите «Перепроверить строку». Изменения пока останутся в черновике проверки.", "Тут показано кожен стовпець вихідної таблиці. Виправте значення й натисніть «Перевірити рядок знову». Зміни поки залишаться у чернетці перевірки.")}</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(250px,1fr))", gap: 10 }}>{Object.entries(editorData).map(([key, value]) => <label key={key} style={{ fontSize: 12, color: "#64748b" }}>{key}<textarea disabled={!canEdit || !!editor.applied_at} rows={String(value ?? "").length > 80 ? 3 : 1} value={String(value ?? "")} onChange={event => setEditorData(current => ({ ...current, [key]: event.target.value }))} style={{ width: "100%", marginTop: 3 }} /></label>)}</div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 18 }}>{canEdit && !editor.applied_at && <button className="btn btn-primary" disabled={busy} onClick={saveRow}>{busy ? t("Проверяю…", "Перевіряю…") : t("Перепроверить строку", "Перевірити рядок знову")}</button>}</div>
    </div></div>}
  </div>;
}
