/* Бланк викраски — будуємо HTML (для модалки KpDoc-стилю + друку). Дані з «Виявлення потреби». */
export function vykraskaHtml(d: any): { title: string; html: string } {
  const date = d.date || new Date().toLocaleDateString("uk-UA");
  const num = d.number != null ? String(d.number) : "";
  const u = d.underlay && d.underlay !== "—" ? " " + String(d.underlay).toLowerCase() : "";
  const desc = `прорахунок ${d.material || "декору"}${d.color ? " у кольорі " + d.color : ""}${d.area ? " на " + d.area + "м2" : ""}${u}.`
    + (d.client ? " " + d.client : "") + (d.phone ? " " + d.phone : "");
  const kits: any[] = (d.kits && d.kits.length ? d.kits.slice() : []);
  while (kits.length < 3) kits.push({});
  const rows: [string, string, string][] = [
    ["1", "краска", "material"], ["2", "база", ""], ["3", "кол. краски", "color"],
    ["4", "каталог цвета", ""], ["5", "Формула цвета. Каталога", ""],
    ["6", "страница формулы с каталога", ""], ["8", "примечание (корректировка формулы)", ""],
  ];
  const block = (k: any) => `
    <tr><td class="side" rowspan="8">Викраска</td><td class="num">№</td><td colspan="2" class="fhdr">Формула</td></tr>
    ${rows.map(([nn, lbl, key]) => {
      const pre = key === "material" ? (k.material || d.material || "") : key === "color" ? (k.color || "") : "";
      return `<tr><td class="num">${nn}</td><td class="lbl">${lbl}${pre ? ' <b>' + pre + '</b>' : ''}</td><td class="blank"></td></tr>`;
    }).join("")}`;
  const style = `<style>
    .vkdoc{font-family:Arial,Helvetica,sans-serif;color:#000;}
    .vkdoc h1{font-size:17px;margin:0 0 8px;}
    .vkdoc table{border-collapse:collapse;width:100%;table-layout:fixed;}
    .vkdoc td{border:1px solid #000;padding:3px 5px;font-size:11px;vertical-align:top;word-wrap:break-word;}
    .vkdoc .side{font-weight:700;}
    .vkdoc .num{padding:1px 0;text-align:center;font-size:11px;font-weight:600;}
    .vkdoc .lbl{font-size:10px;}
    .vkdoc .fhdr{text-align:center;font-weight:700;font-size:14px;height:32px;vertical-align:middle;}
    @media print{@page{size:A4;margin:10mm;} body{margin:0;} .vkdoc{font-size:11px;}}
  </style>`;
  const html = style + `<div class="vkdoc"><h1>Бланк викраски ${num}</h1>
    <table><colgroup><col style="width:50%"><col style="width:2%"><col style="width:13%"><col style="width:35%"></colgroup>
    <tr><td class="side">Об'єкт</td><td colspan="3"><b>${date}</b><br>${desc}</td></tr>
    ${kits.map(block).join("")}</table></div>`;
  return { title: "Бланк викраски " + num, html };
}
