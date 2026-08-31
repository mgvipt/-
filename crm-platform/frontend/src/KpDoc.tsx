/* Документ «1. КП Декор» — видаткова накладна / КП. Друк + PDF + Excel. */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import { Icon } from "./Icon";

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

export default function KpDoc({ deal, onClose, dateOverride, readOnly }: { deal: any; onClose: () => void; dateOverride?: string; readOnly?: boolean }) {
  const [contact, setContact] = useState<any>(null);
  useEffect(() => { if (deal.contact_id) api.get<any>(`/api/contacts/${deal.contact_id}/`).then(setContact).catch(() => {}); }, [deal.contact_id]);

  const today = dateOverride || new Date().toLocaleDateString("uk-UA");
  const items = deal.items || [];
  // «По кімнатах»: за замовч. ВИМКНЕНО — однакові товари сумуються в один рядок (звичайна накладна).
  const [byRooms, setByRooms] = useState(false);
  const hasRooms = items.some((x: any) => (x.room_name || "").trim());
  const subtotal = items.reduce((s: number, i: any) => s + Number(i.quantity) * Number(i.price), 0);
  const discount = items.reduce((s: number, i: any) => s + Number(i.discount_sum || 0), 0);
  const total = items.reduce((s: number, i: any) => s + Number(i.total), 0);
  const clientName = contact ? `${contact.last_name || ""} ${contact.first_name || ""}`.trim() || deal.contact_name : deal.contact_name || "—";
  const clientPhone = contact?.phone || "";
  const qr = `https://api.qrserver.com/v1/create-qr-code/?size=130x130&data=${encodeURIComponent("https://instagram.com/" + SUP.ig)}`;

  const _row = (it: any, n: number) => `
    <tr>
      <td style="border:1px solid #333;padding:4px;text-align:center">${n}</td>
      <td style="border:1px solid #333;padding:4px">${(it.product_name || "").replace(/</g, "&lt;")}</td>
      <td style="border:1px solid #333;padding:4px;text-align:center">${Number(it.quantity)}</td>
      <td style="border:1px solid #333;padding:4px;text-align:center">${(it as any).unit || "шт"}</td>
      <td style="border:1px solid #333;padding:4px;text-align:right">${money(Number(it.price))}</td>
      <td style="border:1px solid #333;padding:4px;text-align:right">${money(Number(it.total))}</td>
    </tr>`;
  const _head = (title: string) => `
    <tr><td colspan="6" style="border:1px solid #333;padding:5px 6px;background:#f3f4f6;font-weight:bold">${title}</td></tr>`;
  // ЗВИЧАЙНА накладна: однакові товари (та сама назва+ціна) склеюємо в один рядок
  const _merged = (() => {
    const map = new Map<string, any>();
    for (const it of items as any[]) {
      const k = (it.product_name || "") + "|" + Number(it.price);
      const cur = map.get(k);
      if (cur) { cur.quantity = Number(cur.quantity) + Number(it.quantity); cur.total = Number(cur.total) + Number(it.total); }
      else map.set(k, { ...it, quantity: Number(it.quantity), total: Number(it.total) });
    }
    return [...map.values()];
  })();
  const rowsHtml = (byRooms && hasRooms)
    ? (() => {
        const groups = new Map<string, any[]>();
        for (const it of items as any[]) {
          const k = ((it as any).room_name || "").trim() || "__general__";
          if (!groups.has(k)) groups.set(k, []);
          groups.get(k)!.push(it);
        }
        let n = 0, out = "";
        for (const [k, arr] of groups) {
          if (k === "__general__") continue;
          out += _head(k);
          for (const it of arr) out += _row(it, ++n);
        }
        const gen = groups.get("__general__") || [];
        if (gen.length) { out += _head("Загальні позиції"); for (const it of gen) out += _row(it, ++n); }
        return out;
      })()
    : _merged.map((it: any, i: number) => _row(it, i + 1)).join("");

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
    <div style="margin-top:16px;border:2px solid #C67D5F;border-radius:10px;padding:12px 14px;background:#fdf3ee">
      <div style="font-weight:bold;font-size:14px;color:#8a4b32;margin-bottom:7px">💳 Призначення платежу — впишіть ТОЧНО цей текст при оплаті на IBAN:</div>
      <div style="font-size:15px;font-weight:bold;background:#fff;border:1.5px dashed #C67D5F;border-radius:8px;padding:9px 12px;letter-spacing:0.2px">
        Оплата згідно накладної №${deal.id}
      </div>
      <div style="font-size:11px;color:#555;margin-top:9px;line-height:1.6">
        <b style="color:#b45309">Чому це важливо:</b> без правильного призначення банк не розуміє, за що платіж — ми не бачимо, від кого й за яке замовлення надійшли гроші, і відправлення затримується.<br/>
        Коли призначення вказано правильно — ваша оплата зʼявляється в нас <b>одразу</b>, і ми відразу починаємо готувати замовлення. Номер накладної <b>№${deal.id}</b> — це ключ, за яким ми знаходимо саме вашу оплату.
      </div>
    </div>
  </div>`;

  async function copyLink() {
    try {
      const r: any = await api.post(`/api/deals/${deal.id}/kp_link/`, { html: docHtml });
      try { await navigator.clipboard.writeText(r.url); window.alert("\u2713 \u041f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u0441\u043a\u043e\u043f\u0456\u0439\u043e\u0432\u0430\u043d\u043e:\n" + r.url); }
      catch { window.prompt("\u0421\u043a\u043e\u043f\u0456\u044e\u0439\u0442\u0435 \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f:", r.url); }
    } catch { window.alert("\u041d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u0441\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f"); }
  }
  async function saveHist() {
    const note = window.prompt("Коментар до версії КП (необовʼязково):", "");
    if (note === null) return;
    try { await api.post(`/api/deals/${deal.id}/kp_save/`, { note }); window.alert("✓ Збережено в історію (видно у картці сделки)"); }
    catch { window.alert("Не вдалося зберегти"); }
  }
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
  async function excel() {
    const ExcelJS = (window as any).ExcelJS;
    if (!ExcelJS) {   // fallback: простий .xls (HTML) якщо бібліотека не завантажилась
      const rows = items.map((it: any, i: number) => `<tr><td>${i + 1}</td><td>${it.product_name}</td><td>${Number(it.quantity)}</td><td>${(it as any).unit || "шт"}</td><td>${Number(it.price)}</td><td>${Number(it.total)}</td></tr>`).join("");
      const html = `<table border="1"><tr><th>№</th><th>Товар</th><th>Кіл-сть</th><th>Од</th><th>Ціна</th><th>Сума</th></tr>${rows}</table>`;
      const blob = new Blob(["﻿" + html], { type: "application/vnd.ms-excel" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `KP_Decor_${deal.id}.xls`; a.click();
      return;
    }
    const wb = new ExcelJS.Workbook();
    const ws = wb.addWorksheet("КП Декор");
    ws.columns = [{ width: 5 }, { width: 46 }, { width: 10 }, { width: 6 }, { width: 13 }, { width: 15 }];
    const thin = { style: "thin", color: { argb: "FF333333" } };
    const box = { top: thin, left: thin, bottom: thin, right: thin };

    // ── QR Instagram ліворуч угорі (як у документі) ──
    try {
      const resp = await fetch(qr);
      if (resp.ok) {
        const ab = await resp.arrayBuffer();
        const imgId = wb.addImage({ buffer: ab, extension: "png" });
        ws.addImage(imgId, { tl: { col: 0, row: 0.15 }, ext: { width: 88, height: 88 } });
      }
    } catch { /* без QR — не ламаємо експорт */ }
    for (let i = 1; i <= 5; i++) ws.getRow(i).height = 18;

    // ── Постачальник (праворуч від QR — колонка B з відступом) ──
    const sup: [string, boolean][] = [
      ["Постачальник: " + SUP.name, true],
      ["IBAN " + SUP.iban, false],
      [`${SUP.bank} РНУКПН: ${SUP.rnukpn}; МФО: ${SUP.mfo}`, false],
      ["тел. " + SUP.phone, false],
      ["mail: " + SUP.mail, false],
    ];
    sup.forEach((s, i) => {
      const c = ws.getCell(i + 1, 2);
      c.value = s[0]; c.alignment = { indent: 8, vertical: "middle" };
      if (s[1]) c.font = { bold: true };
    });

    // ── підпис під QR ──
    ws.mergeCells("A6:B6");
    const ig = ws.getCell("A6"); ig.value = "@" + SUP.ig.toUpperCase();
    ig.font = { size: 8, bold: true }; ig.alignment = { horizontal: "center" };
    ws.mergeCells("A7:B8");
    const note = ws.getCell("A7");
    note.value = "*Скануй та підпишись! Знижки та спеціальні пропозиції діють тільки для підписників";
    note.font = { size: 7, color: { argb: "FF888888" } };
    note.alignment = { horizontal: "center", vertical: "top", wrapText: true };

    // ── Отримувач ──
    const rc = ws.getCell("B9");
    rc.value = "Отримувач: " + clientName + (clientPhone ? "    тел.: " + clientPhone : "");
    rc.font = { bold: true }; rc.alignment = { indent: 8 };

    // ── Заголовок (обʼєднано, по центру) ──
    ws.mergeCells("A11:F11");
    const tc = ws.getCell("A11");
    tc.value = `Видаткова накладна № ${deal.id} від ${today}`;
    tc.font = { bold: true, size: 13 }; tc.alignment = { horizontal: "center" };

    // ── Шапка таблиці (заливка + рамка) ──
    const HR = 13;
    ["№", "Товари (роботи, послуги)", "Кіл-сть", "Од", "Ціна", "Сума"].forEach((h, i) => {
      const c = ws.getCell(HR, i + 1);
      c.value = h; c.font = { bold: true }; c.border = box;
      c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFFDF6E3" } };
      c.alignment = { horizontal: "center", vertical: "middle", wrapText: true };
    });

    // ── Рядки товарів (з рамками) ──
    let row = HR + 1;
    items.forEach((it: any, i: number) => {
      const vals: any[] = [i + 1, it.product_name, Number(it.quantity), (it as any).unit || "шт", Number(it.price), Number(it.total)];
      vals.forEach((v, ci) => {
        const c = ws.getCell(row, ci + 1);
        c.value = v; c.border = box;
        if (ci === 0 || ci === 2 || ci === 3) c.alignment = { horizontal: "center" };
        if (ci === 4 || ci === 5) { c.alignment = { horizontal: "right" }; c.numFmt = "#,##0.00"; }
        if (ci === 1) c.alignment = { wrapText: true };
      });
      row++;
    });
    row++;

    // ── Підсумки (праворуч) ──
    const addTot = (label: string, val: number, bold: boolean) => {
      const lc = ws.getCell(row, 5); lc.value = label; lc.alignment = { horizontal: "right" }; lc.font = { bold };
      const vc = ws.getCell(row, 6); vc.value = Number(val.toFixed(2)); vc.alignment = { horizontal: "right" }; vc.numFmt = "#,##0.00"; vc.font = { bold };
      row++;
    };
    addTot("Всього:", subtotal, false);
    if (discount > 0) addTot("Сума знижки:", discount, false);
    addTot("Всього до оплати:", total, true);
    row += 1;
    ws.getCell(row, 1).value = uahWords(total); row++;
    ws.getCell(row, 1).value = "У т.ч. ПДВ: Нуль гривень 00 копійок";

    const buf = await wb.xlsx.writeBuffer();
    const blob = new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `KP_Decor_${deal.id}.xlsx`; a.click();
  }

  return createPortal(
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.5)", zIndex: 9000, display: "flex", alignItems: "flex-start", justifyContent: "center", overflow: "auto", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#f3efe9", borderRadius: 14, padding: 18, width: 820, maxWidth: "96vw" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <b style={{ fontSize: 17, flex: 1 }}>{readOnly ? `Накладна #${deal.id} · ${today}` : `1. КП Декор #${deal.id}`}</b>
          {!readOnly && <button className="btn" style={{ background: "#ecfdf5", color: "#047857" }} onClick={saveHist}><Icon n="🧾" size={15} /> Зберегти в історію</button>}
          <button className="btn btn-primary" onClick={printWin}><Icon n="🖨" size={15} /> Друк</button>
          {hasRooms && <label style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12.5, color: "#475569", cursor: "pointer", marginRight: 4 }} title="Показати позиції згруповані по приміщеннях"><input type="checkbox" checked={byRooms} onChange={(e) => setByRooms(e.target.checked)} /> по кімнатах</label>}
          <button className="btn" style={{ background: "#eff6ff", color: "#1d4ed8" }} onClick={copyLink} title="Скопіювати посилання на документ — швидко надіслати клієнту"><Icon n="link" size={15} /> Посилання</button>
          <button className="btn" onClick={pdf} title="Завантажити PDF-файл"><Icon n="📄" size={15} /> PDF</button>
          <button className="btn btn-green" onClick={excel}><Icon n="📊" size={15} /> Excel</button>
          <button className="btn" onClick={onClose}>✕</button>
        </div>
        <div id="kp-doc-print" style={{ background: "#fff", borderRadius: 10, padding: 24 }} dangerouslySetInnerHTML={{ __html: docHtml }} />
      </div>
    </div>,
    document.body
  );
}
