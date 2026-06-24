/* Документ «1. КП Декор» — видаткова накладна / КП. Друк + PDF + Excel. */
import { useEffect, useState } from "react";
import { api } from "./api";

const SUP = {
  name: "ФОП Кріжевські Олег Леонідович",
  iban: "UA983052990000026002046111493",
  bank: 'АТ КБ "Приват Банк"', rnukpn: "3031640354", mfo: "305299",
  phone: "(096) 419-18-90", mail: "mogpod.vipt@gmail.com", ig: "dekor_dlia_stin",
};

// ── сума прописом (гривні) ──
function uahWords(amount: number): string {
  const grn = Math.floor(amount), kop = Math.round((amount - grn) * 100);
  const ones = ["", "один", "два", "три", "чотири", "пʼять", "шість", "сім", "вісім", "девʼять"];
  const onesF = ["", "одна", "дві", "три", "чотири", "пʼять", "шість", "сім", "вісім", "девʼять"];
  const teens = ["десять", "одинадцять", "дванадцять", "тринадцять", "чотирнадцять", "пʼятнадцять", "шістнадцять", "сімнадцять", "вісімнадцять", "девʼятнадцять"];
  const tens = ["", "", "двадцять", "тридцять", "сорок", "пʼятдесят", "шістдесят", "сімдесят", "вісімдесят", "девʼяносто"];
  const huns = ["", "сто", "двісті", "триста", "чотириста", "пʼятсот", "шістсот", "сімсот", "вісімсот", "девʼятсот"];
  const triple = (num: number, fem: boolean) => {
    const o = fem ? onesF : ones; const r: string[] = [];
    const h = Math.floor(num / 100), t = Math.floor((num % 100) / 10), u = num % 10;
    if (h) r.push(huns[h]);
    if (t === 1) r.push(teens[u]); else { if (t) r.push(tens[t]); if (u) r.push(o[u]); }
    return r.join(" ");
  };
  const plural = (n: number, f: [string, string, string]) => {
    const a = n % 10, b = n % 100;
    if (a === 1 && b !== 11) return f[0];
    if (a >= 2 && a <= 4 && (b < 10 || b >= 20)) return f[1];
    return f[2];
  };
  const w: string[] = []; const th = Math.floor(grn / 1000), rest = grn % 1000;
  if (th) { w.push(triple(th, true)); w.push(plural(th, ["тисяча", "тисячі", "тисяч"])); }
  if (rest || !th) w.push(triple(rest, false));
  let str = (w.join(" ").trim() || "нуль"); str = str.charAt(0).toUpperCase() + str.slice(1);
  return `${str} ${plural(grn, ["гривня", "гривні", "гривень"])} ${String(kop).padStart(2, "0")} ${plural(kop, ["копійка", "копійки", "копійок"])}`;
}

const money = (n: number) => Number(n || 0).toLocaleString("uk-UA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function KpDoc({ deal, onClose }: { deal: any; onClose: () => void }) {
  const [contact, setContact] = useState<any>(null);
  useEffect(() => { if (deal.contact_id) api.get<any>(`/api/contacts/${deal.contact_id}/`).then(setContact).catch(() => {}); }, [deal.contact_id]);

  const today = new Date().toLocaleDateString("uk-UA");
  const items = deal.items || [];
  const subtotal = items.reduce((s: number, i: any) => s + Number(i.quantity) * Number(i.price), 0);
  const discount = items.reduce((s: number, i: any) => s + Number(i.discount_sum || 0), 0);
  const total = items.reduce((s: number, i: any) => s + Number(i.total), 0);
  const clientName = contact ? `${contact.last_name || ""} ${contact.first_name || ""}`.trim() || deal.contact_name : deal.contact_name || "—";
  const clientPhone = contact?.phone || "";
  const qr = `https://api.qrserver.com/v1/create-qr-code/?size=130x130&data=${encodeURIComponent("https://instagram.com/" + SUP.ig)}`;

  const rowsHtml = items.map((it: any, i: number) => `
    <tr>
      <td style="border:1px solid #333;padding:4px;text-align:center">${i + 1}</td>
      <td style="border:1px solid #333;padding:4px">${(it.product_name || "").replace(/</g, "&lt;")}</td>
      <td style="border:1px solid #333;padding:4px;text-align:center">${Number(it.quantity)}</td>
      <td style="border:1px solid #333;padding:4px;text-align:center">шт</td>
      <td style="border:1px solid #333;padding:4px;text-align:right">${money(Number(it.price))}</td>
      <td style="border:1px solid #333;padding:4px;text-align:right">${money(Number(it.total))}</td>
    </tr>`).join("");

  const docHtml = `
  <div style="font-family:Arial,sans-serif;color:#111;max-width:720px;margin:0 auto;font-size:13px">
    <table style="width:100%;border-collapse:collapse;margin-bottom:14px"><tr>
      <td style="width:150px;vertical-align:top;text-align:center">
        <img src="${qr}" width="110" height="110" crossorigin="anonymous" style="display:block;margin:0 auto" onerror="this.style.display='none'"/>
        <div style="font-size:10px;margin-top:3px">@${SUP.ig.toUpperCase()}</div>
        <div style="font-size:9px;color:#555;margin-top:4px">*Скануй та підпишись!<br/>Знижки та спеціальні пропозиції<br/>діють тільки для підписників</div>
      </td>
      <td style="vertical-align:top;font-size:12px;line-height:1.5">
        <b>Постачальник:</b> ${SUP.name}<br/>
        IBAN ${SUP.iban}<br/>${SUP.bank} РНУКПН: ${SUP.rnukpn}; МФО: ${SUP.mfo}<br/>
        тел.${SUP.phone};<br/>mail: ${SUP.mail}<br/><br/>
        <b>Отримувач:</b> ${clientName}<br/>${clientPhone ? "тел.: " + clientPhone : ""}
      </td>
    </tr></table>
    <h3 style="text-align:center;margin:10px 0">Видаткова накладна № ${deal.id} від ${today}</h3>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <thead><tr style="background:#fdf6e3">
        <th style="border:1px solid #333;padding:4px;width:30px">№</th>
        <th style="border:1px solid #333;padding:4px">Товари (роботи, послуги)</th>
        <th style="border:1px solid #333;padding:4px;width:55px">Кіл-сть</th>
        <th style="border:1px solid #333;padding:4px;width:40px">Од</th>
        <th style="border:1px solid #333;padding:4px;width:80px">Ціна</th>
        <th style="border:1px solid #333;padding:4px;width:90px">Сума</th>
      </tr></thead>
      <tbody>${rowsHtml}</tbody>
    </table>
    <div style="text-align:right;margin-top:10px;font-size:13px">
      <div>Всього: <b>${money(subtotal)}</b> грн.</div>
      ${discount > 0 ? `<div>Сума знижки: <b>${money(discount)}</b> грн.</div>` : ""}
      <div style="font-size:14px;margin-top:4px">Всього до оплати: <b>${money(total)}</b> грн.</div>
    </div>
    <div style="margin-top:14px;font-size:12px">
      ${uahWords(total)}<br/>У т.ч. ПДВ: Нуль гривень 00 копійок
    </div>
  </div>`;

  function printWin() {
    const w = window.open("", "_blank", "width=800,height=900"); if (!w) return;
    w.document.write(`<html><head><title>КП Декор #${deal.id}</title></head><body style="margin:20px">${docHtml}</body></html>`);
    w.document.close(); w.focus(); setTimeout(() => w.print(), 400);
  }
  function pdf() {
    const el = document.getElementById("kp-doc-print");
    const h2p = (window as any).html2pdf;
    if (!el || !h2p) { printWin(); return; }   // нема бібліотеки → fallback на друк
    h2p().set({
      margin: 8, filename: `KP_Decor_${deal.id}.pdf`,
      image: { type: "jpeg", quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true },
      jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
    }).from(el).save();
  }
  function excel() {
    const rows = items.map((it: any, i: number) =>
      `<tr><td>${i + 1}</td><td>${it.product_name}</td><td>${Number(it.quantity)}</td><td>шт</td><td>${Number(it.price)}</td><td>${Number(it.total)}</td></tr>`).join("");
    const html = `<table border="1"><tr><th>№</th><th>Товар</th><th>Кіл-сть</th><th>Од</th><th>Ціна</th><th>Сума</th></tr>${rows}
      <tr><td colspan="5">Всього до оплати, грн</td><td>${total.toFixed(2)}</td></tr></table>`;
    const blob = new Blob(["﻿" + html], { type: "application/vnd.ms-excel" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `KP_Decor_${deal.id}.xls`; a.click();
  }

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 60, display: "flex", alignItems: "flex-start", justifyContent: "center", overflow: "auto", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#f3efe9", borderRadius: 14, padding: 18, width: 820, maxWidth: "96vw" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <b style={{ fontSize: 17, flex: 1 }}>1. КП Декор #{deal.id}</b>
          <button className="btn btn-primary" onClick={printWin}>🖨 Друк</button>
          <button className="btn" onClick={pdf} title="Завантажити PDF-файл">📄 PDF</button>
          <button className="btn btn-green" onClick={excel}>📊 Excel</button>
          <button className="btn" onClick={onClose}>✕</button>
        </div>
        <div id="kp-doc-print" style={{ background: "#fff", borderRadius: 10, padding: 24 }} dangerouslySetInnerHTML={{ __html: docHtml }} />
      </div>
    </div>
  );
}
