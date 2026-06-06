(() => {
  "use strict";

  /* ============================================================
   * Подбор цвета мебели — интерактивный конфигуратор
   * Чистый JS, без зависимостей. Состояние хранится в localStorage.
   * ============================================================ */

  const STORAGE_KEY = "furniture.picker.v1";
  const SAVED_KEY = "furniture.picker.saved.v1";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const uid = () => Math.random().toString(36).slice(2, 9);

  /* -------------------- Каталог мебели -------------------- */
  // Каждый предмет: viewBox 0 0 400 300, список частей и набор фигур.
  // Фигура: {part, x,y,w,h,rx} (прямоугольник) или {part, d} (path).

  const FURNITURE = {
    sofa: {
      name: "Диван", icon: "🛋️", viewBox: "0 0 400 300",
      parts: [
        { key: "body", label: "Обивка (каркас)", def: "#8a6f5b" },
        { key: "accent", label: "Подушки", def: "#c9b79c" },
        { key: "legs", label: "Ножки", def: "#3f2d1f" },
      ],
      shapes: [
        { part: "legs", x: 72, y: 242, w: 14, h: 18, rx: 3 },
        { part: "legs", x: 150, y: 242, w: 14, h: 18, rx: 3 },
        { part: "legs", x: 236, y: 242, w: 14, h: 18, rx: 3 },
        { part: "legs", x: 314, y: 242, w: 14, h: 18, rx: 3 },
        { part: "body", x: 58, y: 120, w: 284, h: 72, rx: 20 },
        { part: "body", x: 66, y: 182, w: 268, h: 64, rx: 14 },
        { part: "accent", x: 92, y: 128, w: 104, h: 58, rx: 14 },
        { part: "accent", x: 204, y: 128, w: 104, h: 58, rx: 14 },
        { part: "accent", x: 80, y: 168, w: 120, h: 30, rx: 12 },
        { part: "accent", x: 200, y: 168, w: 120, h: 30, rx: 12 },
        { part: "body", x: 48, y: 150, w: 42, h: 96, rx: 16 },
        { part: "body", x: 310, y: 150, w: 42, h: 96, rx: 16 },
      ],
    },

    armchair: {
      name: "Кресло", icon: "🪑", viewBox: "0 0 400 300",
      parts: [
        { key: "body", label: "Обивка (каркас)", def: "#7c5a4a" },
        { key: "accent", label: "Подушки", def: "#d4c3a8" },
        { key: "legs", label: "Ножки", def: "#2e2017" },
      ],
      shapes: [
        { part: "legs", x: 132, y: 232, w: 14, h: 20, rx: 3 },
        { part: "legs", x: 254, y: 232, w: 14, h: 20, rx: 3 },
        { part: "body", x: 120, y: 110, w: 160, h: 100, rx: 26 },
        { part: "body", x: 118, y: 180, w: 164, h: 60, rx: 16 },
        { part: "accent", x: 138, y: 120, w: 124, h: 78, rx: 18 },
        { part: "accent", x: 132, y: 172, w: 136, h: 30, rx: 12 },
        { part: "body", x: 104, y: 160, w: 30, h: 80, rx: 12 },
        { part: "body", x: 266, y: 160, w: 30, h: 80, rx: 12 },
      ],
    },

    chair: {
      name: "Стул", icon: "🪑", viewBox: "0 0 400 300",
      parts: [
        { key: "body", label: "Каркас", def: "#6b4a2f" },
        { key: "accent", label: "Сиденье / спинка", def: "#b08d5b" },
      ],
      shapes: [
        { part: "body", x: 150, y: 72, w: 14, h: 180, rx: 4 },
        { part: "body", x: 236, y: 72, w: 14, h: 180, rx: 4 },
        { part: "accent", x: 150, y: 84, w: 100, h: 40, rx: 8 },
        { part: "accent", x: 150, y: 132, w: 100, h: 18, rx: 6 },
        { part: "body", x: 132, y: 158, w: 136, h: 18, rx: 6 },
        { part: "accent", x: 138, y: 148, w: 124, h: 16, rx: 8 },
        { part: "body", x: 140, y: 174, w: 13, h: 78, rx: 3 },
        { part: "body", x: 247, y: 174, w: 13, h: 78, rx: 3 },
      ],
    },

    table: {
      name: "Стол", icon: "🍽️", viewBox: "0 0 400 300",
      parts: [
        { key: "tabletop", label: "Столешница", def: "#9c6b3f" },
        { key: "legs", label: "Опоры", def: "#5b3a24" },
      ],
      shapes: [
        { part: "legs", x: 120, y: 188, w: 14, h: 64, rx: 3 },
        { part: "legs", x: 266, y: 188, w: 14, h: 64, rx: 3 },
        { part: "tabletop", x: 82, y: 176, w: 236, h: 14, rx: 3 },
        { part: "legs", x: 88, y: 188, w: 18, h: 64, rx: 3 },
        { part: "legs", x: 294, y: 188, w: 18, h: 64, rx: 3 },
        { part: "tabletop", x: 64, y: 150, w: 272, h: 26, rx: 7 },
      ],
    },

    bed: {
      name: "Кровать", icon: "🛏️", viewBox: "0 0 400 300",
      parts: [
        { key: "body", label: "Каркас / изголовье", def: "#6b4a33" },
        { key: "accent", label: "Матрас / бельё", def: "#e3dccb" },
        { key: "legs", label: "Ножки", def: "#3a281a" },
      ],
      shapes: [
        { part: "legs", x: 66, y: 240, w: 14, h: 18, rx: 3 },
        { part: "legs", x: 330, y: 240, w: 14, h: 18, rx: 3 },
        { part: "body", x: 56, y: 200, w: 300, h: 46, rx: 8 },
        { part: "body", x: 56, y: 116, w: 56, h: 130, rx: 10 },
        { part: "accent", x: 108, y: 166, w: 248, h: 42, rx: 14 },
        { part: "accent", x: 208, y: 172, w: 148, h: 32, rx: 10 },
        { part: "accent", x: 122, y: 146, w: 82, h: 36, rx: 14 },
      ],
    },

    wardrobe: {
      name: "Шкаф", icon: "🚪", viewBox: "0 0 400 300",
      parts: [
        { key: "body", label: "Корпус", def: "#7a5638" },
        { key: "accent", label: "Фасады", def: "#a37545" },
        { key: "hardware", label: "Фурнитура", def: "#cfcfcf" },
        { key: "legs", label: "Опоры", def: "#3a281a" },
      ],
      shapes: [
        { part: "legs", x: 110, y: 240, w: 16, h: 14, rx: 2 },
        { part: "legs", x: 274, y: 240, w: 16, h: 14, rx: 2 },
        { part: "body", x: 90, y: 52, w: 220, h: 16, rx: 4 },
        { part: "body", x: 96, y: 64, w: 208, h: 178, rx: 6 },
        { part: "accent", x: 104, y: 72, w: 94, h: 162, rx: 4 },
        { part: "accent", x: 202, y: 72, w: 94, h: 162, rx: 4 },
        { part: "hardware", x: 189, y: 138, w: 6, h: 34, rx: 3 },
        { part: "hardware", x: 205, y: 138, w: 6, h: 34, rx: 3 },
      ],
    },

    dresser: {
      name: "Комод", icon: "🗄️", viewBox: "0 0 400 300",
      parts: [
        { key: "body", label: "Корпус", def: "#8a6240" },
        { key: "accent", label: "Ящики", def: "#b08454" },
        { key: "hardware", label: "Ручки", def: "#2c2c2c" },
        { key: "legs", label: "Ножки", def: "#3a281a" },
      ],
      shapes: [
        { part: "legs", x: 104, y: 240, w: 16, h: 16, rx: 2 },
        { part: "legs", x: 280, y: 240, w: 16, h: 16, rx: 2 },
        { part: "body", x: 90, y: 110, w: 220, h: 12, rx: 4 },
        { part: "body", x: 96, y: 120, w: 208, h: 122, rx: 6 },
        { part: "accent", x: 104, y: 128, w: 192, h: 32, rx: 4 },
        { part: "accent", x: 104, y: 165, w: 192, h: 32, rx: 4 },
        { part: "accent", x: 104, y: 202, w: 192, h: 32, rx: 4 },
        { part: "hardware", x: 188, y: 141, w: 24, h: 6, rx: 3 },
        { part: "hardware", x: 188, y: 178, w: 24, h: 6, rx: 3 },
        { part: "hardware", x: 188, y: 215, w: 24, h: 6, rx: 3 },
      ],
    },

    shelf: {
      name: "Стеллаж", icon: "📚", viewBox: "0 0 400 300",
      parts: [
        { key: "body", label: "Каркас / полки", def: "#7a5638" },
        { key: "accent", label: "Задняя стенка", def: "#d8cdbb" },
      ],
      shapes: [
        { part: "accent", x: 124, y: 84, w: 152, h: 152 },
        { part: "body", x: 110, y: 70, w: 14, h: 180, rx: 3 },
        { part: "body", x: 276, y: 70, w: 14, h: 180, rx: 3 },
        { part: "body", x: 110, y: 70, w: 180, h: 14, rx: 3 },
        { part: "body", x: 110, y: 126, w: 180, h: 12, rx: 3 },
        { part: "body", x: 110, y: 182, w: 180, h: 12, rx: 3 },
        { part: "body", x: 110, y: 238, w: 180, h: 14, rx: 3 },
      ],
    },
  };

  /* -------------------- Материалы -------------------- */
  const MATERIALS = {
    fabric:  { label: "Ткань",     overlay: "fx-fabric", opacity: 1 },
    leather: { label: "Кожа",      overlay: "fx-gloss",  opacity: 0.22 },
    wood:    { label: "Дерево",    overlay: "fx-wood",   opacity: 1 },
    matte:   { label: "Матовый",   overlay: null,        opacity: 0 },
    satin:   { label: "Сатин",     overlay: "fx-gloss",  opacity: 0.14 },
    gloss:   { label: "Глянец",    overlay: "fx-gloss",  opacity: 0.40 },
    metal:   { label: "Металл",    overlay: "fx-metal",  opacity: 0.50 },
  };

  /* -------------------- Палитра образцов -------------------- */
  const SWATCHES = [
    "#ffffff", "#f1ece2", "#e3dccb", "#cbb79c", "#b08d5b", "#9c6b3f", "#6b4a2f", "#3f2d1f", "#241a12",
    "#2a2a2e", "#4a4a52", "#7d7d86", "#a8a8b0", "#cfcfd6", "#1f3a4d", "#2f5d72", "#5e8ca3", "#9cb4c4",
    "#3d5a3d", "#6b8a5b", "#8a9a6b", "#b7c49a", "#7a2f33", "#a8504f", "#b5713f", "#d8a679", "#c2a24a",
  ];

  /* -------------------- Готовые гаммы -------------------- */
  const THEMES = [
    { name: "Скандинавский", desc: "светлый, уютный",
      colors: { body: "#e6e1d8", accent: "#9cb4c4", legs: "#c8a574", tabletop: "#d6b98c", hardware: "#bdbdbd" },
      material: "fabric", room: { wall: "#f3f0ea", floor: "#d8c3a0" } },
    { name: "Лофт", desc: "графит и медь",
      colors: { body: "#3c3c40", accent: "#b5673a", legs: "#222226", tabletop: "#5b3a24", hardware: "#1c1c1c" },
      material: "leather", room: { wall: "#cfc9c0", floor: "#6b5440" } },
    { name: "Классика", desc: "крем и орех",
      colors: { body: "#efe3cf", accent: "#7a2f33", legs: "#5b3a24", tabletop: "#5b3a24", hardware: "#c2a24a" },
      material: "wood", room: { wall: "#e7dcc6", floor: "#8a6a45" } },
    { name: "Эко-натурель", desc: "зелень и дерево",
      colors: { body: "#8a9a6b", accent: "#d8cdb6", legs: "#6b5036", tabletop: "#9c7a4f", hardware: "#9a9a8a" },
      material: "fabric", room: { wall: "#eef0e6", floor: "#b79b73" } },
    { name: "Тёплый минимал", desc: "терракота и беж",
      colors: { body: "#d8a679", accent: "#efe6da", legs: "#b5825a", tabletop: "#c08a5a", hardware: "#9a8472" },
      material: "satin", room: { wall: "#f1e7dc", floor: "#cdb091" } },
    { name: "Тёмный модерн", desc: "синий и латунь",
      colors: { body: "#2f3b46", accent: "#c2a24a", legs: "#1e2126", tabletop: "#3a2f26", hardware: "#c2a24a" },
      material: "gloss", room: { wall: "#d7d3cc", floor: "#4a4036" } },
  ];

  const ROOM_PRESETS = [
    { name: "Тёплый", wall: "#efe7da", floor: "#cbb79c" },
    { name: "Светлый", wall: "#f5f3ee", floor: "#e0d4c0" },
    { name: "Серый лофт", wall: "#cfc9c0", floor: "#6b5440" },
    { name: "Тёмный", wall: "#3a3631", floor: "#2a241f" },
    { name: "Холодный", wall: "#e6ebef", floor: "#b9c2c8" },
  ];

  /* -------------------- Состояние -------------------- */
  const state = {
    furniture: "sofa",
    material: "fabric",
    activePart: "body",
    colors: {},
    room: { wall: "#efe7da", floor: "#cbb79c" },
  };

  /* -------------------- Цветовые утилиты -------------------- */
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  function normalizeHex(hex) {
    if (typeof hex !== "string") return null;
    let h = hex.trim().replace(/^#/, "");
    if (/^[0-9a-fA-F]{3}$/.test(h)) h = h.split("").map((c) => c + c).join("");
    if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
    return "#" + h.toLowerCase();
  }

  function hexToRgb(hex) {
    const h = normalizeHex(hex) || "#000000";
    return {
      r: parseInt(h.slice(1, 3), 16),
      g: parseInt(h.slice(3, 5), 16),
      b: parseInt(h.slice(5, 7), 16),
    };
  }

  function rgbToHex(r, g, b) {
    const to = (n) => clamp(Math.round(n), 0, 255).toString(16).padStart(2, "0");
    return "#" + to(r) + to(g) + to(b);
  }

  function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h = 0, s = 0;
    const l = (max + min) / 2;
    const d = max - min;
    if (d !== 0) {
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      switch (max) {
        case r: h = (g - b) / d + (g < b ? 6 : 0); break;
        case g: h = (b - r) / d + 2; break;
        default: h = (r - g) / d + 4;
      }
      h *= 60;
    }
    return { h: Math.round(h), s: Math.round(s * 100), l: Math.round(l * 100) };
  }

  function hslToRgb(h, s, l) {
    h = ((h % 360) + 360) % 360; s /= 100; l /= 100;
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    const m = l - c / 2;
    let r = 0, g = 0, b = 0;
    if (h < 60) [r, g, b] = [c, x, 0];
    else if (h < 120) [r, g, b] = [x, c, 0];
    else if (h < 180) [r, g, b] = [0, c, x];
    else if (h < 240) [r, g, b] = [0, x, c];
    else if (h < 300) [r, g, b] = [x, 0, c];
    else [r, g, b] = [c, 0, x];
    return { r: (r + m) * 255, g: (g + m) * 255, b: (b + m) * 255 };
  }

  function hexToHsl(hex) { const { r, g, b } = hexToRgb(hex); return rgbToHsl(r, g, b); }
  function hslToHex(h, s, l) { const { r, g, b } = hslToRgb(h, s, l); return rgbToHex(r, g, b); }

  /* -------------------- Сохранение состояния -------------------- */
  function save() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (_) {}
  }
  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const p = JSON.parse(raw);
      if (p && FURNITURE[p.furniture]) {
        state.furniture = p.furniture;
        if (MATERIALS[p.material]) state.material = p.material;
        if (p.colors && typeof p.colors === "object") state.colors = p.colors;
        if (p.room && p.room.wall && p.room.floor) state.room = p.room;
        if (p.activePart) state.activePart = p.activePart;
      }
    } catch (_) {}
  }

  function ensureColors() {
    // Гарантируем цвет для каждой части текущего предмета.
    const f = FURNITURE[state.furniture];
    f.parts.forEach((p) => {
      if (!normalizeHex(state.colors[p.key])) state.colors[p.key] = p.def;
    });
    if (!f.parts.some((p) => p.key === state.activePart)) {
      state.activePart = f.parts[0].key;
    }
  }

  /* -------------------- Построение SVG -------------------- */
  function shapeOpen(s) {
    if (s.d) return `<path d="${s.d}" `;
    return `<rect x="${s.x}" y="${s.y}" width="${s.w}" height="${s.h}" rx="${s.rx || 0}" `;
  }

  function buildFurnitureMarkup(colors, material, opts = {}) {
    const f = FURNITURE[state.furniture];
    const mat = MATERIALS[material] || MATERIALS.matte;
    let out = "";
    f.shapes.forEach((s, i) => {
      const fill = colors[s.part] || "#cccccc";
      out += shapeOpen(s) + `class="paint" data-part="${s.part}" fill="${fill}"/>`;
      if (mat.overlay) {
        out += shapeOpen(s) + `class="finish" fill="url(#${mat.overlay})" opacity="${mat.opacity}" pointer-events="none"/>`;
      }
    });
    if (opts.outlineActive) {
      f.shapes.filter((s) => s.part === opts.outlineActive).forEach((s) => {
        out += shapeOpen(s) + `class="sel-outline"/>`;
      });
    }
    return out;
  }

  function getDefs() {
    const d = document.querySelector("svg.defs defs");
    return d ? d.outerHTML : "";
  }

  // Полная сцена (стены + пол + мебель) для экспорта и миниатюр.
  function buildSceneSVG(st) {
    const prev = { furniture: state.furniture, material: state.material };
    state.furniture = st.furniture; state.material = st.material;
    const f = FURNITURE[st.furniture];
    const [, , vw, vh] = f.viewBox.split(/\s+/).map(Number);
    const floorY = vh * 0.68;
    const markup = buildFurnitureMarkup(st.colors, st.material, {});
    state.furniture = prev.furniture; state.material = prev.material;
    return (
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${f.viewBox}" width="${vw}" height="${vh}">` +
      getDefs() +
      `<rect x="0" y="0" width="${vw}" height="${vh}" fill="${st.room.wall}"/>` +
      `<rect x="0" y="${floorY}" width="${vw}" height="${vh - floorY}" fill="${st.room.floor}"/>` +
      markup +
      `</svg>`
    );
  }

  function sceneDataURL(st) {
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(buildSceneSVG(st));
  }

  /* -------------------- Рендер превью -------------------- */
  const svg = $("#furniture-svg");
  const stage = $("#stage");

  function renderFurniture() {
    const f = FURNITURE[state.furniture];
    svg.setAttribute("viewBox", f.viewBox);
    svg.innerHTML = buildFurnitureMarkup(state.colors, state.material, { outlineActive: state.activePart });
  }

  function updatePartColor(part) {
    const color = state.colors[part];
    $$(`.paint[data-part="${part}"]`, svg).forEach((el) => el.setAttribute("fill", color));
    // Обновим строку в списке частей и превью цвета.
    const row = $(`.part-row[data-key="${part}"]`);
    if (row) {
      $(".part-swatch", row).style.background = color;
      $(".part-hex", row).textContent = color.toUpperCase();
    }
    if (part === state.activePart) $("#picker-preview").style.background = color;
  }

  function applyRoom() {
    stage.style.setProperty("--wall", state.room.wall);
    stage.style.setProperty("--floor", state.room.floor);
    $("#wall-color").value = state.room.wall;
    $("#floor-color").value = state.room.floor;
  }

  /* -------------------- Списки UI -------------------- */
  function renderFurnitureList() {
    const root = $("#furniture-list");
    root.innerHTML = "";
    Object.entries(FURNITURE).forEach(([id, f]) => {
      const b = document.createElement("button");
      b.className = "furniture-btn" + (id === state.furniture ? " active" : "");
      b.type = "button";
      b.innerHTML = `<span class="ico">${f.icon}</span><span>${f.name}</span>`;
      b.addEventListener("click", () => selectFurniture(id));
      root.appendChild(b);
    });
  }

  function renderPartsList() {
    const f = FURNITURE[state.furniture];
    const root = $("#parts-list");
    root.innerHTML = "";
    f.parts.forEach((p) => {
      const row = document.createElement("div");
      row.className = "part-row" + (p.key === state.activePart ? " active" : "");
      row.dataset.key = p.key;
      const color = state.colors[p.key];
      row.innerHTML =
        `<span class="part-swatch" style="background:${color}"></span>` +
        `<span class="part-name">${p.label}</span>` +
        `<span class="part-hex">${color.toUpperCase()}</span>`;
      row.addEventListener("click", () => selectPart(p.key));
      root.appendChild(row);
    });
  }

  function renderMaterialList() {
    const root = $("#material-list");
    root.innerHTML = "";
    Object.entries(MATERIALS).forEach(([id, m]) => {
      const c = document.createElement("button");
      c.className = "chip" + (id === state.material ? " active" : "");
      c.type = "button";
      c.textContent = m.label;
      c.addEventListener("click", () => selectMaterial(id));
      root.appendChild(c);
    });
  }

  function renderSwatches() {
    const root = $("#swatches");
    root.innerHTML = "";
    SWATCHES.forEach((hex) => {
      const s = document.createElement("button");
      s.className = "swatch";
      s.type = "button";
      s.style.background = hex;
      s.title = hex.toUpperCase();
      s.addEventListener("click", () => applyColor(hex));
      root.appendChild(s);
    });
  }

  function renderHarmony() {
    const root = $("#harmony");
    const { h, s, l } = hexToHsl(state.colors[state.activePart]);
    const groups = [
      { title: "Контраст (комплементарный)", colors: [hslToHex(h + 180, s, l)] },
      { title: "Аналоговые", colors: [hslToHex(h - 30, s, l), hslToHex(h + 30, s, l)] },
      { title: "Триада", colors: [hslToHex(h + 120, s, l), hslToHex(h - 120, s, l)] },
      { title: "Светлее / темнее", colors: [
        hslToHex(h, s, clamp(l + 18, 0, 96)),
        hslToHex(h, s, clamp(l - 18, 4, 100)),
      ] },
    ];
    root.innerHTML = "";
    groups.forEach((g) => {
      const wrap = document.createElement("div");
      wrap.className = "harmony-group";
      const title = document.createElement("h3");
      title.textContent = g.title;
      const row = document.createElement("div");
      row.className = "harmony-row";
      g.colors.forEach((hex) => {
        const chip = document.createElement("button");
        chip.className = "harmony-chip";
        chip.type = "button";
        chip.style.background = hex;
        chip.title = hex.toUpperCase();
        chip.addEventListener("click", () => applyColor(hex));
        row.appendChild(chip);
      });
      wrap.appendChild(title);
      wrap.appendChild(row);
      root.appendChild(wrap);
    });
  }

  function renderThemes() {
    const root = $("#themes");
    root.innerHTML = "";
    THEMES.forEach((t) => {
      const b = document.createElement("button");
      b.className = "theme-btn";
      b.type = "button";
      const dots = [t.colors.body, t.colors.accent, t.colors.legs]
        .map((c) => `<span style="background:${c}"></span>`).join("");
      b.innerHTML =
        `<span class="theme-dots">${dots}</span>` +
        `<span class="theme-info"><b>${t.name}</b><small>${t.desc}</small></span>`;
      b.addEventListener("click", () => applyTheme(t));
      root.appendChild(b);
    });
  }

  function renderRoomPresets() {
    const root = $("#room-presets");
    root.innerHTML = "";
    ROOM_PRESETS.forEach((r) => {
      const c = document.createElement("button");
      c.className = "chip";
      c.type = "button";
      c.textContent = r.name;
      c.addEventListener("click", () => {
        state.room = { wall: r.wall, floor: r.floor };
        applyRoom(); save();
      });
      root.appendChild(c);
    });
  }

  /* -------------------- Синхронизация пикера -------------------- */
  function syncPicker() {
    const hex = state.colors[state.activePart];
    const { h, s, l } = hexToHsl(hex);
    $("#sl-h").value = h;
    $("#sl-s").value = s;
    $("#sl-l").value = l;
    $("#hex-input").value = hex.toUpperCase();
    $("#picker-preview").style.background = hex;
    $("#active-part-label").textContent =
      (FURNITURE[state.furniture].parts.find((p) => p.key === state.activePart) || {}).label || "—";
  }

  /* -------------------- Действия -------------------- */
  function selectFurniture(id) {
    state.furniture = id;
    ensureColors();
    renderFurnitureList();
    renderPartsList();
    renderFurniture();
    syncPicker();
    renderHarmony();
    save();
  }

  function selectPart(key) {
    state.activePart = key;
    $$(".part-row").forEach((r) => r.classList.toggle("active", r.dataset.key === key));
    renderFurniture(); // обновляем рамку выделения
    syncPicker();
    renderHarmony();
    save();
  }

  function selectMaterial(id) {
    state.material = id;
    renderMaterialList();
    renderFurniture();
    save();
  }

  // Применить цвет к активной части (из свотча/гармонии/пикера).
  function setColor(hex, { fromSlider = false, fromHex = false } = {}) {
    const norm = normalizeHex(hex);
    if (!norm) return;
    state.colors[state.activePart] = norm;
    updatePartColor(state.activePart);
    if (!fromSlider) {
      const { h, s, l } = hexToHsl(norm);
      $("#sl-h").value = h; $("#sl-s").value = s; $("#sl-l").value = l;
    }
    if (!fromHex) $("#hex-input").value = norm.toUpperCase();
    $("#picker-preview").style.background = norm;
    renderHarmony();
    save();
  }

  function applyColor(hex) { setColor(hex); }

  function applyTheme(t) {
    const f = FURNITURE[state.furniture];
    f.parts.forEach((p) => {
      if (t.colors[p.key]) state.colors[p.key] = t.colors[p.key];
    });
    if (MATERIALS[t.material]) state.material = t.material;
    if (t.room) state.room = { wall: t.room.wall, floor: t.room.floor };
    renderPartsList();
    renderMaterialList();
    renderFurniture();
    applyRoom();
    syncPicker();
    renderHarmony();
    save();
  }

  function randomLook() {
    const f = FURNITURE[state.furniture];
    const baseH = Math.floor(Math.random() * 360);
    f.parts.forEach((p, i) => {
      let s, l, hue = baseH;
      if (p.key === "legs" || p.key === "hardware") { s = 15 + Math.random() * 20; l = 15 + Math.random() * 20; hue = baseH + 20; }
      else if (p.key === "accent") { hue = baseH + 150 + Math.random() * 60; s = 30 + Math.random() * 40; l = 45 + Math.random() * 25; }
      else { s = 25 + Math.random() * 35; l = 40 + Math.random() * 30; }
      state.colors[p.key] = hslToHex(hue, s, l);
    });
    const mats = Object.keys(MATERIALS);
    state.material = mats[Math.floor(Math.random() * mats.length)];
    renderPartsList();
    renderMaterialList();
    renderFurniture();
    syncPicker();
    renderHarmony();
    save();
  }

  function resetAll() {
    if (!confirm("Сбросить цвета к значениям по умолчанию?")) return;
    state.colors = {};
    state.material = "fabric";
    state.room = { wall: "#efe7da", floor: "#cbb79c" };
    ensureColors();
    renderPartsList();
    renderMaterialList();
    renderFurniture();
    applyRoom();
    syncPicker();
    renderHarmony();
    save();
  }

  /* -------------------- Экспорт PNG -------------------- */
  function exportPNG() {
    const f = FURNITURE[state.furniture];
    const [, , vw, vh] = f.viewBox.split(/\s+/).map(Number);
    const scale = 3;
    const canvas = document.createElement("canvas");
    canvas.width = vw * scale; canvas.height = vh * scale;
    const ctx = canvas.getContext("2d");
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const a = document.createElement("a");
      a.href = canvas.toDataURL("image/png");
      a.download = `${f.name}_${state.material}.png`;
      document.body.appendChild(a); a.click(); a.remove();
    };
    img.onerror = () => alert("Не удалось сформировать изображение.");
    img.src = sceneDataURL(state);
  }

  /* -------------------- Сохранённые варианты -------------------- */
  function loadSaved() {
    try { return JSON.parse(localStorage.getItem(SAVED_KEY) || "[]"); } catch (_) { return []; }
  }
  function persistSaved(list) {
    try { localStorage.setItem(SAVED_KEY, JSON.stringify(list)); } catch (_) {}
  }

  function snapshot() {
    return {
      id: uid(),
      furniture: state.furniture,
      material: state.material,
      colors: { ...state.colors },
      room: { ...state.room },
    };
  }

  function saveVariant() {
    const list = loadSaved();
    list.unshift(snapshot());
    persistSaved(list.slice(0, 24));
    renderSaved();
  }

  function renderSaved() {
    const list = loadSaved();
    const root = $("#saved-list");
    const empty = $("#saved-empty");
    root.innerHTML = "";
    empty.style.display = list.length ? "none" : "block";
    list.forEach((st) => {
      const item = document.createElement("div");
      item.className = "saved-item";
      const f = FURNITURE[st.furniture] || FURNITURE.sofa;
      item.innerHTML =
        `<img class="saved-thumb" alt="${f.name}" src="${sceneDataURL(st)}"/>` +
        `<div class="saved-meta"><span>${f.name}</span><span>${(MATERIALS[st.material] || {}).label || ""}</span></div>` +
        `<div class="saved-actions">` +
          `<button class="load" type="button">Открыть</button>` +
          `<button class="del" type="button">Удалить</button>` +
        `</div>`;
      $(".load", item).addEventListener("click", () => loadVariant(st));
      $(".del", item).addEventListener("click", () => deleteVariant(st.id));
      root.appendChild(item);
    });
  }

  function loadVariant(st) {
    state.furniture = st.furniture;
    state.material = st.material;
    state.colors = { ...st.colors };
    state.room = { ...st.room };
    ensureColors();
    renderFurnitureList();
    renderPartsList();
    renderMaterialList();
    renderFurniture();
    applyRoom();
    syncPicker();
    renderHarmony();
    save();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function deleteVariant(id) {
    persistSaved(loadSaved().filter((s) => s.id !== id));
    renderSaved();
  }

  /* -------------------- Привязка элементов управления -------------------- */
  function bindControls() {
    const onSlider = () => {
      const h = +$("#sl-h").value, s = +$("#sl-s").value, l = +$("#sl-l").value;
      setColor(hslToHex(h, s, l), { fromSlider: true });
    };
    $("#sl-h").addEventListener("input", onSlider);
    $("#sl-s").addEventListener("input", onSlider);
    $("#sl-l").addEventListener("input", onSlider);

    $("#hex-input").addEventListener("input", (e) => {
      const norm = normalizeHex(e.target.value);
      if (norm) setColor(norm, { fromHex: true });
    });

    $("#wall-color").addEventListener("input", (e) => {
      state.room.wall = e.target.value; applyRoom(); save();
    });
    $("#floor-color").addEventListener("input", (e) => {
      state.room.floor = e.target.value; applyRoom(); save();
    });

    // Клик по части прямо на превью.
    svg.addEventListener("click", (e) => {
      const el = e.target.closest(".paint");
      if (el && el.dataset.part) selectPart(el.dataset.part);
    });

    $("#btn-random").addEventListener("click", randomLook);
    $("#btn-reset").addEventListener("click", resetAll);
    $("#btn-export").addEventListener("click", exportPNG);
    $("#btn-save").addEventListener("click", saveVariant);
  }

  /* -------------------- Старт -------------------- */
  function init() {
    loadState();
    ensureColors();
    renderFurnitureList();
    renderPartsList();
    renderMaterialList();
    renderSwatches();
    renderThemes();
    renderRoomPresets();
    renderFurniture();
    applyRoom();
    syncPicker();
    renderHarmony();
    renderSaved();
    bindControls();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
