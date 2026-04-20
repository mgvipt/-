(() => {
  "use strict";

  const STORAGE_KEY = "smeta.state.v1";

  const state = {
    meta: { title: "", client: "", contractor: "", date: "" },
    sections: [],
    overheadRate: 0,
    discountRate: 0,
    vatRate: 20,
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const uid = () => Math.random().toString(36).slice(2, 10);

  const fmtRUB = new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const sectionsRoot = $("#sections-root");
  const sectionTpl = $("#section-template");
  const itemTpl = $("#item-template");

  function makeItem(partial = {}) {
    return {
      id: uid(),
      name: "",
      unit: "",
      qty: 0,
      price: 0,
      ...partial,
    };
  }

  function makeSection(partial = {}) {
    return {
      id: uid(),
      title: "",
      items: [makeItem()],
      ...partial,
    };
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (err) {
      console.warn("Не удалось сохранить состояние:", err);
    }
  }

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const parsed = JSON.parse(raw);
      Object.assign(state, parsed);
      if (!Array.isArray(state.sections) || state.sections.length === 0) {
        state.sections = [makeSection({ title: "Основные работы" })];
      }
      return true;
    } catch (err) {
      console.warn("Не удалось загрузить состояние:", err);
      return false;
    }
  }

  function renderAll() {
    $("#project-title").value = state.meta.title || "";
    $("#project-client").value = state.meta.client || "";
    $("#project-contractor").value = state.meta.contractor || "";
    $("#project-date").value = state.meta.date || "";
    $("#overhead-rate").value = state.overheadRate;
    $("#discount-rate").value = state.discountRate;
    $("#vat-rate").value = state.vatRate;

    sectionsRoot.innerHTML = "";
    state.sections.forEach(renderSection);
    recalcTotals();
  }

  function renderSection(section) {
    const node = sectionTpl.content.firstElementChild.cloneNode(true);
    node.dataset.sectionId = section.id;
    const titleInput = $(".section-title", node);
    titleInput.value = section.title || "";
    titleInput.addEventListener("input", () => {
      section.title = titleInput.value;
      save();
    });

    $(".btn-remove-section", node).addEventListener("click", () => {
      if (state.sections.length === 1) {
        if (!confirm("Удалить единственный раздел? Будет создан пустой.")) return;
        state.sections = [makeSection({ title: "" })];
      } else {
        state.sections = state.sections.filter((s) => s.id !== section.id);
      }
      renderAll();
      save();
    });

    $(".btn-add-item", node).addEventListener("click", () => {
      const item = makeItem();
      section.items.push(item);
      const row = renderItem(section, item);
      $(".items-body", node).appendChild(row);
      reindexRows(node);
      recalcSection(section, node);
      recalcTotals();
      save();
      $(".item-name", row).focus();
    });

    const body = $(".items-body", node);
    section.items.forEach((item) => body.appendChild(renderItem(section, item)));
    reindexRows(node);
    recalcSection(section, node);

    sectionsRoot.appendChild(node);
  }

  function renderItem(section, item) {
    const row = itemTpl.content.firstElementChild.cloneNode(true);
    row.dataset.itemId = item.id;

    const nameInput = $(".item-name", row);
    const unitInput = $(".item-unit", row);
    const qtyInput = $(".item-qty", row);
    const priceInput = $(".item-price", row);

    nameInput.value = item.name || "";
    unitInput.value = item.unit || "";
    qtyInput.value = item.qty;
    priceInput.value = item.price;

    nameInput.addEventListener("input", () => { item.name = nameInput.value; save(); });
    unitInput.addEventListener("input", () => { item.unit = unitInput.value; save(); });
    qtyInput.addEventListener("input", () => {
      item.qty = toNumber(qtyInput.value);
      onAmountChanged(section, row);
    });
    priceInput.addEventListener("input", () => {
      item.price = toNumber(priceInput.value);
      onAmountChanged(section, row);
    });

    $(".btn-remove-item", row).addEventListener("click", () => {
      section.items = section.items.filter((i) => i.id !== item.id);
      const sectionNode = row.closest(".section");
      row.remove();
      if (section.items.length === 0) {
        const empty = makeItem();
        section.items.push(empty);
        $(".items-body", sectionNode).appendChild(renderItem(section, empty));
      }
      reindexRows(sectionNode);
      recalcSection(section, sectionNode);
      recalcTotals();
      save();
    });

    updateRowSum(item, row);
    return row;
  }

  function onAmountChanged(section, row) {
    const item = findItem(section, row.dataset.itemId);
    updateRowSum(item, row);
    recalcSection(section, row.closest(".section"));
    recalcTotals();
    save();
  }

  function updateRowSum(item, row) {
    const sum = (item.qty || 0) * (item.price || 0);
    $(".item-sum", row).textContent = fmtRUB.format(sum);
  }

  function reindexRows(sectionNode) {
    $$(".item-row", sectionNode).forEach((row, i) => {
      $(".item-idx", row).textContent = String(i + 1);
    });
  }

  function recalcSection(section, sectionNode) {
    const subtotal = section.items.reduce(
      (acc, it) => acc + (it.qty || 0) * (it.price || 0),
      0
    );
    $(".section-subtotal", sectionNode).textContent = fmtRUB.format(subtotal);
    return subtotal;
  }

  function computeTotals() {
    const subtotal = state.sections.reduce(
      (acc, s) =>
        acc + s.items.reduce((a, it) => a + (it.qty || 0) * (it.price || 0), 0),
      0
    );
    const overhead = subtotal * (state.overheadRate / 100);
    const afterOverhead = subtotal + overhead;
    const discount = afterOverhead * (state.discountRate / 100);
    const afterDiscount = afterOverhead - discount;
    const vat = afterDiscount * (state.vatRate / 100);
    const grand = afterDiscount + vat;
    return { subtotal, overhead, discount, vat, grand };
  }

  function recalcTotals() {
    const t = computeTotals();
    $("#total-subtotal").textContent = fmtRUB.format(t.subtotal);
    $("#total-overhead").textContent = fmtRUB.format(t.overhead);
    $("#total-discount").textContent = "−" + fmtRUB.format(t.discount);
    $("#total-vat").textContent = fmtRUB.format(t.vat);
    $("#total-grand").textContent = fmtRUB.format(t.grand);
    $("#total-in-words").textContent = t.grand > 0 ? "Прописью: " + amountInWords(t.grand) : "";
  }

  function findItem(section, id) {
    return section.items.find((i) => i.id === id);
  }

  function toNumber(v) {
    const n = parseFloat(String(v).replace(",", "."));
    return Number.isFinite(n) && n >= 0 ? n : 0;
  }

  function bindMeta() {
    $("#project-title").addEventListener("input", (e) => { state.meta.title = e.target.value; save(); });
    $("#project-client").addEventListener("input", (e) => { state.meta.client = e.target.value; save(); });
    $("#project-contractor").addEventListener("input", (e) => { state.meta.contractor = e.target.value; save(); });
    $("#project-date").addEventListener("input", (e) => { state.meta.date = e.target.value; save(); });

    $("#overhead-rate").addEventListener("input", (e) => {
      state.overheadRate = toNumber(e.target.value);
      recalcTotals(); save();
    });
    $("#discount-rate").addEventListener("input", (e) => {
      state.discountRate = toNumber(e.target.value);
      recalcTotals(); save();
    });
    $("#vat-rate").addEventListener("input", (e) => {
      state.vatRate = toNumber(e.target.value);
      recalcTotals(); save();
    });
  }

  function bindTopActions() {
    $("#btn-add-section").addEventListener("click", () => {
      const section = makeSection({ title: "" });
      state.sections.push(section);
      renderSection(section);
      recalcTotals();
      save();
      const nodes = $$(".section");
      $(".section-title", nodes[nodes.length - 1]).focus();
    });

    $("#btn-new").addEventListener("click", () => {
      if (!confirm("Создать новую смету? Текущая будет очищена из памяти.")) return;
      resetState();
      renderAll();
      save();
    });

    $("#btn-print").addEventListener("click", () => window.print());

    $("#btn-export-json").addEventListener("click", exportJSON);
    $("#btn-export-csv").addEventListener("click", exportCSV);

    const fileInput = $("#file-input");
    $("#btn-import").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const parsed = JSON.parse(String(reader.result));
          if (!parsed || typeof parsed !== "object") throw new Error("Некорректный формат");
          Object.assign(state, {
            meta: parsed.meta || state.meta,
            sections: Array.isArray(parsed.sections) ? parsed.sections : state.sections,
            overheadRate: toNumber(parsed.overheadRate),
            discountRate: toNumber(parsed.discountRate),
            vatRate: toNumber(parsed.vatRate),
          });
          renderAll();
          save();
        } catch (err) {
          alert("Не удалось импортировать файл: " + err.message);
        }
      };
      reader.readAsText(file);
      fileInput.value = "";
    });
  }

  function resetState() {
    state.meta = { title: "", client: "", contractor: "", date: todayISO() };
    state.sections = [makeSection({ title: "Основные работы" })];
    state.overheadRate = 0;
    state.discountRate = 0;
    state.vatRate = 20;
  }

  function todayISO() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function exportJSON() {
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
    downloadBlob(blob, filenameFor("json"));
  }

  function exportCSV() {
    const rows = [];
    rows.push(["Раздел", "№", "Наименование", "Ед.", "Кол-во", "Цена", "Сумма"]);
    state.sections.forEach((s) => {
      s.items.forEach((it, i) => {
        const sum = (it.qty || 0) * (it.price || 0);
        rows.push([
          s.title || "",
          String(i + 1),
          it.name || "",
          it.unit || "",
          String(it.qty || 0),
          String(it.price || 0),
          sum.toFixed(2),
        ]);
      });
    });
    const t = computeTotals();
    rows.push([]);
    rows.push(["Сумма по позициям", "", "", "", "", "", t.subtotal.toFixed(2)]);
    rows.push([`Накладные ${state.overheadRate}%`, "", "", "", "", "", t.overhead.toFixed(2)]);
    rows.push([`Скидка ${state.discountRate}%`, "", "", "", "", "", (-t.discount).toFixed(2)]);
    rows.push([`НДС ${state.vatRate}%`, "", "", "", "", "", t.vat.toFixed(2)]);
    rows.push(["ИТОГО", "", "", "", "", "", t.grand.toFixed(2)]);

    const csv = rows.map((r) => r.map(csvEscape).join(";")).join("\r\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    downloadBlob(blob, filenameFor("csv"));
  }

  function csvEscape(v) {
    const s = String(v ?? "");
    if (/[";\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function downloadBlob(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function filenameFor(ext) {
    const safe = (state.meta.title || "smeta")
      .replace(/[\\/:*?"<>|]+/g, "")
      .trim() || "smeta";
    const d = state.meta.date || todayISO();
    return `${safe}_${d}.${ext}`;
  }

  // --- Сумма прописью (рубли и копейки) ---
  function amountInWords(amount) {
    const rub = Math.floor(amount);
    const kop = Math.round((amount - rub) * 100);
    const rubWord = pluralRu(rub, ["рубль", "рубля", "рублей"]);
    const kopWord = pluralRu(kop, ["копейка", "копейки", "копеек"]);
    const rubText = numToWordsRu(rub, "m");
    const kopText = String(kop).padStart(2, "0");
    const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
    return `${cap(rubText)} ${rubWord} ${kopText} ${kopWord}`;
  }

  function pluralRu(n, forms) {
    const a = Math.abs(n) % 100;
    const b = a % 10;
    if (a > 10 && a < 20) return forms[2];
    if (b > 1 && b < 5) return forms[1];
    if (b === 1) return forms[0];
    return forms[2];
  }

  function numToWordsRu(num, gender = "m") {
    if (num === 0) return "ноль";
    const units_m = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"];
    const units_f = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"];
    const teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"];
    const tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"];
    const hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"];

    function triad(n, g) {
      const units = g === "f" ? units_f : units_m;
      const parts = [];
      const h = Math.floor(n / 100);
      const rem = n % 100;
      const t = Math.floor(rem / 10);
      const u = rem % 10;
      if (h) parts.push(hundreds[h]);
      if (t === 1) parts.push(teens[u]);
      else {
        if (t) parts.push(tens[t]);
        if (u) parts.push(units[u]);
      }
      return parts.join(" ");
    }

    const scales = [
      { div: 1, g: gender === "f" ? "f" : "m", forms: null },
      { div: 1000, g: "f", forms: ["тысяча", "тысячи", "тысяч"] },
      { div: 1_000_000, g: "m", forms: ["миллион", "миллиона", "миллионов"] },
      { div: 1_000_000_000, g: "m", forms: ["миллиард", "миллиарда", "миллиардов"] },
    ];

    let n = Math.floor(num);
    const chunks = [];
    let i = 0;
    while (n > 0) {
      chunks.push(n % 1000);
      n = Math.floor(n / 1000);
      i++;
    }

    const parts = [];
    for (let j = chunks.length - 1; j >= 0; j--) {
      const value = chunks[j];
      if (value === 0) continue;
      const scale = scales[j];
      parts.push(triad(value, scale.g));
      if (scale.forms) parts.push(pluralRu(value, scale.forms));
    }
    return parts.join(" ").trim();
  }

  // --- bootstrap ---
  function init() {
    const loaded = load();
    if (!loaded) resetState();
    if (!state.meta.date) state.meta.date = todayISO();
    bindMeta();
    bindTopActions();
    renderAll();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
