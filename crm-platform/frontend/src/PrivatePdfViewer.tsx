/// <reference types="vite/client" />
import { useEffect, useRef, useState } from "react";
import { GlobalWorkerOptions, getDocument, type PDFDocumentProxy, type RenderTask } from "pdfjs-dist/legacy/build/pdf.mjs";
import workerUrl from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";

// Vite emits a same-origin worker asset. No PDF data is sent to an external service.
GlobalWorkerOptions.workerSrc = workerUrl;

type Props = { url: string; title: string; lang: "uk" | "ru" };
export default function PrivatePdfViewer({ url, title, lang }: Props) {
  const t = (uk: string, ru: string) => lang === "ru" ? ru : uk;
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [width, setWidth] = useState(600);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [printing, setPrinting] = useState<number | null>(null);
  const [printError, setPrintError] = useState(false);
  const [printReady, setPrintReady] = useState(false);
  const printAction = useRef<(() => void) | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const printCleanup = useRef<(() => void) | null>(null);

  useEffect(() => {
    let alive = true;
    setPdf(null); setPage(1); setBusy(true); setError(false);
    // The parent owns/revokes this authenticated, in-memory blob URL.
    const task = getDocument({ url, useSystemFonts: true, cMapUrl: `${import.meta.env.BASE_URL}pdfjs/cmaps/`, cMapPacked: true, standardFontDataUrl: `${import.meta.env.BASE_URL}pdfjs/standard_fonts/`, wasmUrl: `${import.meta.env.BASE_URL}pdfjs/wasm/` });
    task.promise.then(doc => { if (alive) setPdf(doc); }).catch(() => {
      if (alive) { setError(true); setBusy(false); }
    });
    return () => { alive = false; printCleanup.current?.(); void task.destroy(); };
  }, [url, retry]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const measure = () => {
      // Border-box width stays stable when a vertical scrollbar appears.
      // A cached lazy module may mount while its parent dialog is still closed.
      const measured = element.getBoundingClientRect().width;
      if (measured > 0) setWidth(Math.max(160, Math.floor(measured - 32)));
    };
    const observer = new ResizeObserver(measure);
    measure();
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!pdf || !canvas.current) return;
    let alive = true;
    let render: RenderTask | undefined;
    setBusy(true); setError(false);
    const timeout = window.setTimeout(() => {
      if (alive) { alive = false; render?.cancel(); setError(true); setBusy(false); }
    }, 20000);
    (async () => {
      const pdfPage = await pdf.getPage(page);
      if (!alive || !canvas.current) return;
      const target = canvas.current;
      const base = pdfPage.getViewport({ scale: 1 });
      const cssScale = Math.min(width, 1200) / base.width;
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      const scale = Math.min(cssScale * pixelRatio, Math.sqrt(4_000_000 / (base.width * base.height)));
      const viewport = pdfPage.getViewport({ scale });
      target.width = Math.ceil(viewport.width); target.height = Math.ceil(viewport.height);
      target.style.width = `${base.width * cssScale}px`;
      target.style.height = `${base.height * cssScale}px`;
      render = pdfPage.render({ canvas: target, viewport });
      await render.promise;
      if (alive) { window.clearTimeout(timeout); setBusy(false); }
    })().catch(() => { if (alive) { window.clearTimeout(timeout); setError(true); setBusy(false); } });
    return () => { alive = false; window.clearTimeout(timeout); render?.cancel(); };
  }, [pdf, page, width]);

  async function printDocument() {
    if (!pdf || printing !== null) return;
    printCleanup.current?.(); setPrintError(false); setPrintReady(false); setPrinting(0);
    let cancelled = false;
    let activeRender: RenderTask | undefined;
    const images: string[] = [];
    const frame = document.createElement("iframe");
    frame.title = t("Друк документа", "Печать документа");
    frame.style.cssText = "position:fixed;left:-10000px;top:0;width:800px;height:1000px;border:0";
    // Keep the frame inside the modal; siblings of a modal dialog are inert.
    (host.current?.closest("dialog") || document.body).appendChild(frame);
    const clean = () => {
      cancelled = true; activeRender?.cancel(); frame.remove(); setPrinting(null);
      printAction.current = null; setPrintReady(false);
      images.forEach(image => URL.revokeObjectURL(image));
      if (printCleanup.current === clean) printCleanup.current = null;
    };
    printCleanup.current = clean;
    try {
      const doc = frame.contentDocument;
      if (!doc || !frame.contentWindow) throw new Error("Print frame unavailable");
      doc.title = title;
      const style = doc.createElement("style");
      style.textContent = "@page{margin:0}html,body{margin:0}img{display:block;width:100%;height:auto;break-after:page;page-break-after:always}img:last-child{break-after:auto;page-break-after:auto}";
      doc.head.appendChild(style);
      for (let index = 1; index <= pdf.numPages; index++) {
        if (cancelled) return;
        const pdfPage = await pdf.getPage(index);
        if (cancelled) return;
        const base = pdfPage.getViewport({ scale: 1 });
        const viewport = pdfPage.getViewport({ scale: Math.min(1500 / base.width, Math.sqrt(3_000_000 / (base.width * base.height))) });
        const printCanvas = document.createElement("canvas");
        printCanvas.width = Math.ceil(viewport.width); printCanvas.height = Math.ceil(viewport.height);
        activeRender = pdfPage.render({ canvas: printCanvas, viewport, intent: "print" });
        await activeRender.promise;
        const blob = await new Promise<Blob>((resolve, reject) => printCanvas.toBlob(value => value ? resolve(value) : reject(new Error("Cannot prepare page")), "image/png"));
        printCanvas.width = 0; printCanvas.height = 0;
        if (cancelled) return;
        const objectUrl = URL.createObjectURL(blob); images.push(objectUrl);
        const image = doc.createElement("img");
        image.alt = `${index}`; image.src = objectUrl;
        doc.body.appendChild(image);
        await image.decode();
        if (cancelled) return;
        setPrinting(index);
      }
      if (cancelled || !frame.contentWindow) return;
      frame.contentWindow.addEventListener("afterprint", clean, { once: true });
      printAction.current = () => {
        if (cancelled || !frame.contentWindow) return;
        try { frame.contentWindow.focus(); frame.contentWindow.print(); }
        catch { setPrintError(true); clean(); }
      };
      // A second explicit click preserves user activation after async page preparation.
      setPrintReady(true);
    } catch { if (!cancelled) { setPrintError(true); clean(); } }
    finally { if (!cancelled) setPrinting(null); }
  }

  const filename = `${title.replace(/[\\/:*?"<>|\u0000-\u001f]/g, "_").replace(/\.pdf$/i, "").slice(0, 150) || "document"}.pdf`;
  return <div style={{ display: "flex", flexDirection: "column", minHeight: 0, height: "100%", gap: 10 }}>
    <div role="toolbar" aria-label={t("Перегляд PDF", "Просмотр PDF")} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
      <button type="button" disabled={!pdf || page <= 1} onClick={() => setPage(n => n - 1)}>{t("Попередня", "Предыдущая")}</button>
      <span aria-live="polite">{pdf ? `${t("Сторінка", "Страница")} ${page} / ${pdf.numPages}` : "PDF"}</span>
      <button type="button" disabled={!pdf || page >= pdf.numPages} onClick={() => setPage(n => n + 1)}>{t("Наступна", "Следующая")}</button>
      <a href={url} download={filename}>{t("Завантажити оригінал PDF", "Скачать оригинал PDF")}</a>
      <button type="button" disabled={!pdf || printing !== null} onClick={() => printReady ? printAction.current?.() : void printDocument()}>{printReady ? t("Відкрити діалог друку", "Открыть диалог печати") : t("Друкувати документ", "Печатать документ")}</button>
    </div>
    {printing !== null && <div role="status">{t("Підготовка до друку", "Подготовка к печати")}: {printing} / {pdf?.numPages} <button type="button" onClick={() => { printCleanup.current?.(); setPrinting(null); }}>{t("Скасувати", "Отменить")}</button></div>}
    {printError && <p role="alert">{t("Не вдалося підготувати друк. Завантажте PDF та надрукуйте з нього.", "Не удалось подготовить печать. Скачайте PDF и распечатайте его.")}</p>}
    {busy && <div role="status">{t("Завантаження сторінки…", "Загрузка страницы…")}</div>}
    {error && <p role="alert">{t("Не вдалося показати PDF. Спробуйте ще раз або завантажте оригінал.", "Не удалось показать PDF. Попробуйте снова или скачайте оригинал.")} <button type="button" onClick={() => setRetry(n => n + 1)}>{t("Повторити", "Повторить")}</button></p>}
    <div ref={host} style={{ flex: 1, minHeight: 0, overflow: "auto", scrollbarGutter: "stable", background: "#e2e8f0", textAlign: "center", padding: "8px 0" }}>
      <canvas ref={canvas} role="img" aria-label={`${title}, ${t("сторінка", "страница")} ${page}`} style={{ display: "inline-block", visibility: busy || error ? "hidden" : "visible", background: "white", maxWidth: "100%", verticalAlign: "top" }} />
    </div>
  </div>;
}
