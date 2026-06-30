/* Документ «Бланк викраски» — відкривається у модалці в СРМ. Кнопка «Друк» викликає принтер. */
import { Icon } from "./Icon";
import { vykraskaHtml } from "./printForms";

export default function VykraskaDoc({ data, onClose }: { data: any; onClose: () => void }) {
  const { title, html } = vykraskaHtml(data);
  function printWin() {
    const w = window.open("", "_blank", "width=820,height=920");
    if (!w) { alert("Дозвольте спливаючі вікна"); return; }
    w.document.write(`<html><head><meta charset="utf-8"><title>${title}</title></head><body style="margin:0">${html}</body></html>`);
    w.document.close(); w.focus(); setTimeout(() => w.print(), 350);
  }
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 70, display: "flex", alignItems: "flex-start", justifyContent: "center", overflow: "auto", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#f3efe9", borderRadius: 14, padding: 18, width: 780, maxWidth: "96vw" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <b style={{ fontSize: 17, flex: 1 }}>{title}</b>
          <button className="btn btn-primary" onClick={printWin}><Icon n="🖨" size={15} /> Друк</button>
          <button className="btn" onClick={onClose}>✕</button>
        </div>
        <div style={{ background: "#fff", borderRadius: 10, padding: 20 }} dangerouslySetInnerHTML={{ __html: html }} />
      </div>
    </div>
  );
}
