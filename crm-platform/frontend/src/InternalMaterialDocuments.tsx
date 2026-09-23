import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { lazy, Suspense } from "react";
const PrivatePdfViewer = lazy(() => import("./PrivatePdfViewer"));

type DocumentRef = {
  id: number; title: string; kind: string; document_number: string; original_language: string;
  issued_at: string | null; valid_until: string | null; is_archived: boolean;
  notes: string; team_access_verified: boolean; translation_missing: boolean;
  url: string; file_available: boolean; file_url: string; notes_translation_missing: boolean;
};
export default function InternalMaterialDocuments({ productId, lang }: { productId: number; lang: "uk" | "ru" }) {
  const [items, setItems] = useState<DocumentRef[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);
  const [viewer, setViewer] = useState<{url: string; title: string} | null>(null);
  const [opening, setOpening] = useState<number | null>(null);
  const [fileError, setFileError] = useState(false);
  const blobRef = useRef<string | null>(null);
  const requestRef = useRef(0);
  const dialogRef = useRef<HTMLDialogElement>(null);
  function closeViewer() {
    requestRef.current++;
    if (blobRef.current) URL.revokeObjectURL(blobRef.current);
    blobRef.current = null;
    setViewer(null); setOpening(null);
  }
  useEffect(() => () => {
    requestRef.current++;
    if (blobRef.current) URL.revokeObjectURL(blobRef.current);
    blobRef.current = null;
  }, []);
  useEffect(() => { if (viewer) dialogRef.current?.showModal(); }, [viewer]);
  async function openFile(doc: DocumentRef) {
    const request = ++requestRef.current;
    setOpening(doc.id); setFileError(false);
    try {
      // Build the authenticated endpoint from numeric IDs, never from an external URL.
      const url = await api.blobUrl(`/api/products/${productId}/internal-documents/${doc.id}/file/`);
      if (request !== requestRef.current) { URL.revokeObjectURL(url); return; }
      if (blobRef.current) URL.revokeObjectURL(blobRef.current);
      blobRef.current = url;
      setViewer({ url, title: doc.title });
    } catch { if (request === requestRef.current) setFileError(true); }
    finally { if (request === requestRef.current) setOpening(null); }
  }
  const t = (uk: string, ru: string) => lang === "ru" ? ru : uk;
  useEffect(() => {
    let alive = true;
    setState("loading"); setItems([]);
    api.get<{ items: DocumentRef[] }>(`/api/products/${productId}/internal-documents/?lang=${lang}`)
      .then(result => { if (alive) { setItems(result.items); setState("ready"); } })
      .catch(() => { if (alive) setState("error"); });
    return () => { alive = false; };
  }, [productId, lang, retry]);
  const date = (value: string) => new Intl.DateTimeFormat(lang === "ru" ? "ru-UA" : "uk-UA", { timeZone: "UTC" }).format(new Date(value));
  if (state === "ready" && !items.length) return null;
  return <section aria-label={t("Документи", "Документы")} style={{ margin: "14px 0", padding: 14, border: "1px solid #cbd5e1", borderRadius: 10 }}>
    <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>{t("Документи", "Документы")}</h3>
    {state === "loading" && <p role="status">{t("Завантаження документів…", "Загрузка документов…")}</p>}
    {state === "error" && <p role="alert">{t("Не вдалося відкрити документи. Перевірте доступ або спробуйте ще раз.", "Не удалось открыть документы. Проверьте доступ или попробуйте снова.")} <button type="button" onClick={() => setRetry(n => n + 1)}>{t("Повторити", "Повторить")}</button></p>}
    {fileError && <p role="alert">{t("Не вдалося відкрити PDF. Спробуйте ще раз або зверніться до керівника.", "Не удалось открыть PDF. Попробуйте снова или обратитесь к руководителю.")}</p>}
    {viewer && <dialog ref={dialogRef} aria-label={viewer.title} onCancel={closeViewer} onClose={closeViewer} style={{ width: "min(960px, 94vw)", maxWidth: "94vw", height: "85vh", padding: 12, border: "1px solid #cbd5e1", borderRadius: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginBottom: 10 }}><strong>{viewer.title}</strong><button type="button" autoFocus onClick={closeViewer}>{t("Закрити", "Закрыть")}</button></div>
      <div style={{ height: "calc(100% - 50px)", minHeight: 0 }}>
        <Suspense fallback={<p role="status">{t("Завантаження PDF…", "Загрузка PDF…")}</p>}>
          <PrivatePdfViewer key={viewer.url} url={viewer.url} title={viewer.title} lang={lang} />
        </Suspense>
      </div>
    </dialog>}
    {state === "ready" && items.map(doc => <article key={doc.id} style={{ borderTop: "1px solid #e2e8f0", padding: "12px 0", overflowWrap: "anywhere" }}>
      <strong>{doc.title}</strong>{doc.is_archived && <span style={{ marginLeft: 8, color: "#64748b" }}>{t("Архівний", "Архивный")}</span>}
      {doc.translation_missing && <small style={{ display: "block", color: "#64748b" }}>Название на украинском</small>}
      <div style={{ fontSize: 12, marginTop: 5, color: "#475569" }}>
        {doc.document_number && <div>№ {doc.document_number}</div>}
        {doc.issued_at && <div>{t("Дата документа", "Дата документа")}: {date(doc.issued_at)}</div>}
        {doc.valid_until && <div>{t("Строк у документі: до", "Срок в документе: до")} {date(doc.valid_until)}</div>}
        {doc.original_language && <div>{t("Мова оригіналу", "Язык оригинала")}: {doc.original_language}</div>}
      </div>
      {doc.notes && <p style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{doc.notes}{doc.notes_translation_missing && <small style={{ display: "block", color: "#64748b" }}>Примечание на украинском</small>}</p>}
      {!doc.file_available && <p style={{ fontSize: 12, color: "#64748b" }}>{t("Якщо Google Диск запитає доступ, увійдіть у робочий обліковий запис.", "Если Google Диск запросит доступ, войдите в рабочую учётную запись.")}</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, fontSize: 13 }}>
        {doc.file_available ? <button type="button" disabled={opening !== null} onClick={() => openFile(doc)}>{opening === doc.id ? t("Відкриваємо…", "Открываем…") : t("Відкрити оригінал", "Открыть оригинал")}</button> : <a href={doc.url} target="_blank" rel="noopener noreferrer">{t("Відкрити оригінал", "Открыть оригинал")}</a>}
      </div>
      <small style={{ display: "block", marginTop: 6, color: "#64748b" }}>{t("Відкрийте оригінал, щоб переглянути, завантажити або надрукувати документ.", "Откройте оригинал, чтобы просмотреть, скачать или распечатать документ.")}</small>
    </article>)}
  </section>;
}
