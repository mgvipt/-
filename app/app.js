/* Цикл вдвоём — MVP. Privacy-first: все данные хранятся только в localStorage этого устройства. */
(function () {
  "use strict";

  var KEY = "cycle-vdvoem-v1";
  var app = document.getElementById("app");

  /* ---------- state ---------- */
  function defaultState() {
    return {
      onboarded: false,
      role: "woman",              // woman | partner
      partnerName: "Партнёр",
      lastPeriod: isoToday(),     // дата начала последней менструации
      cycleLength: 28,
      periodLength: 5,
      goals: ["Понимать себя"],
      intimacy: { date: isoToday(), value: "yellow" },
      diary: {},                  // { "YYYY-MM-DD": { tags:[...], mood:"ok" } }
      tab: "today"
    };
  }
  function load() {
    try {
      var s = JSON.parse(localStorage.getItem(KEY));
      if (s && typeof s === "object") return Object.assign(defaultState(), s);
    } catch (e) {}
    return defaultState();
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  var state = load();

  /* ---------- date helpers ---------- */
  function isoToday() { return new Date().toISOString().slice(0, 10); }
  function parseISO(s) { var p = s.split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function daysBetween(a, b) { return Math.floor((b - a) / 86400000); }
  function addDays(date, n) { var d = new Date(date.getTime()); d.setDate(d.getDate() + n); return d; }
  function fmtDate(d) {
    var mon = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"];
    return d.getDate() + " " + mon[d.getMonth()];
  }
  function fmtWeekday(d) {
    var wd = ["Воскресенье","Понедельник","Вторник","Среда","Четверг","Пятница","Суббота"];
    return wd[d.getDay()];
  }

  /* ---------- cycle engine ---------- */
  function cycleInfo() {
    var len = state.cycleLength, per = state.periodLength;
    var start = parseISO(state.lastPeriod);
    var today = parseISO(isoToday());
    var elapsed = daysBetween(start, today);
    if (elapsed < 0) elapsed = 0;
    var day = (elapsed % len) + 1;                    // текущий день цикла, 1..len
    var cyclesPassed = Math.floor(elapsed / len);
    var currentStart = addDays(start, cyclesPassed * len);
    var nextPeriod = addDays(currentStart, len);
    var ovDay = Math.max(per + 2, len - 14);          // оценка овуляции
    var fertileFrom = ovDay - 5, fertileTo = ovDay + 1;
    return {
      day: day, len: len, per: per, ovDay: ovDay,
      fertile: day >= fertileFrom && day <= fertileTo,
      nextPeriod: nextPeriod,
      daysToNext: daysBetween(today, nextPeriod),
      phase: phaseFor(day, len, per, ovDay)
    };
  }
  function phaseFor(day, len, per, ovDay) {
    if (day <= per) return "menstrual";
    if (day >= ovDay - 1 && day <= ovDay + 1) return "ovulation";
    if (day < ovDay - 1) return "follicular";
    return "luteal";
  }

  var PHASES = {
    menstrual:  { name: "Менструальная", emoji: "🌑", color: "var(--p-menstrual)", sub: "низкая энергия",
      feel: "Возможны усталость, спазмы и потребность в тепле и отдыхе. Настроение чувствительное.",
      partner: "Забота и бережность: тепло, меньше нагрузки, эмпатия. Возьми на себя быт.",
      intimacy: "По обоюдному желанию. Спросить, а не предполагать." },
    follicular: { name: "Фолликулярная", emoji: "🌱", color: "var(--p-follicular)", sub: "энергия растёт",
      feel: "Растёт энергия, ясная голова, общительность. Хорошее время для новых дел.",
      partner: "Поддержи идеи и активности, планируй свидания и вылазки.",
      intimacy: "Влечение постепенно растёт, открытость и игривость." },
    ovulation:  { name: "Овуляция", emoji: "☀️", color: "var(--p-ovulation)", sub: "пик энергии",
      feel: "Пик энергии, уверенности и, как правило, влечения. Самый фертильный период.",
      partner: "Романтика, внимание, комплименты. Контрацепция — общая ответственность.",
      intimacy: "Обычно пиковый интерес. Фертильное окно — контрацепция, если не планируется зачатие." },
    luteal:     { name: "Лютеиновая", emoji: "🌘", color: "var(--p-luteal)", sub: "спад, возможен ПМС",
      feel: "Энергия постепенно снижается; ближе к концу возможен ПМС — чувствительность, тяга к еде.",
      partner: "Терпение и стабильность: помощь по быту, меньше споров, больше принятия.",
      intimacy: "Влечение переменное. Важны нежность и отсутствие давления." }
  };

  var SIGNAL = {
    green:  { em: "🟢", title: "«Открыта»",     text: "Взаимная инициатива приветствуется. Тепло и внимание — самое то." },
    yellow: { em: "🟡", title: "«Может быть»",   text: "Тёплое внимание — да, инициатива — мягко и с вопросом. Она решает." },
    red:    { em: "🔴", title: "«Не сегодня»",   text: "Сегодня — забота без близости. Поддержи, обними, будь рядом." }
  };

  /* ---------- assistant knowledge base (offline, rule-based) ---------- */
  var KB = [
    { k: ["устал","устаю","сил","энерг","слаб"], a: "Перед месячными (лютеиновая фаза) падает уровень эстрогена и прогестерона — отсюда усталость и тяга к сладкому. Помогают отдых, вода, магний и мягкая активность. Если усталость сильная — обсуди с врачом." },
    { k: ["фертил","забеременеть","зачат","овуляц"], a: "Наиболее фертильны ~5 дней до овуляции и день овуляции. У тебя овуляция примерно на день " + "{ov}" + " цикла. Если беременность не в планах — в это окно нужна контрацепция. Это ориентир, не средство контрацепции." },
    { k: ["лютеин"], a: "Лютеиновая фаза — вторая половина цикла, после овуляции и до менструации. Энергия снижается, ближе к концу возможен ПМС: чувствительность, тяга к еде, раздражительность." },
    { k: ["пмс","раздраж","плак","настроен"], a: "ПМС — набор симптомов в конце лютеиновой фазы: перепады настроения, тревожность, вздутие, тяга к еде. Помогают сон, движение, снижение соли и кофеина. Сильный ПМС стоит обсудить с гинекологом." },
    { k: ["боль","спазм","живот"], a: "Спазмы в менструацию — обычное дело из-за сокращений матки. Помогают тепло, лёгкая активность, обезболивающее по инструкции. Очень сильная боль — повод показаться врачу." },
    { k: ["секс","близост","заниматься"], a: "Безопасных «по желанию» дней нет универсальных — всё индивидуально. В приложении есть светофор близости: женщина сама отмечает 🟢/🟡/🔴, а партнёр видит только сигнал. Главное — согласие и разговор." },
    { k: ["задерж","опозда","не пришли","сбил"], a: "Небольшие сдвиги цикла — норма (стресс, сон, нагрузка). Если задержка большая или цикл сильно нерегулярный — стоит показаться врачу и исключить причины." },
    { k: ["сон","спать","бессон"], a: "Во второй половине цикла сон часто хуже из-за гормонов и роста температуры тела. Помогают прохлада в спальне, режим и меньше экранов перед сном." }
  ];
  function assistantAnswer(q) {
    var t = q.toLowerCase(), ci = cycleInfo();
    for (var i = 0; i < KB.length; i++) {
      for (var j = 0; j < KB[i].k.length; j++) {
        if (t.indexOf(KB[i].k[j]) !== -1) return KB[i].a.replace("{ov}", ci.ovDay);
      }
    }
    return "Хороший вопрос! В этой демо-версии я отвечаю на популярные темы: усталость, ПМС, фертильные дни, боль, сон, близость. Спроси про что-то из этого 💛 (и помни — это не заменяет врача).";
  }

  /* ---------- render helpers ---------- */
  function h(html) { return html; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]; }); }
  function ring(ci) {
    var C = 2 * Math.PI * 86, len = ci.len;
    function arc(color, from, to) {
      var frac = (to - from + 1) / len, dash = frac * C;
      var off = -((from - 1) / len) * C;
      return '<circle cx="100" cy="100" r="86" fill="none" stroke="' + color + '" stroke-width="15" stroke-linecap="round" stroke-dasharray="' + dash.toFixed(1) + ' ' + (C - dash).toFixed(1) + '" stroke-dashoffset="' + off.toFixed(1) + '"/>';
    }
    var ov = ci.ovDay;
    var p = PHASES[ci.phase];
    return '' +
      '<div class="ring-wrap"><div class="ring"><svg width="210" height="210" viewBox="0 0 210 210">' +
      '<circle cx="100" cy="100" r="86" fill="none" stroke="var(--line)" stroke-width="15"/>' +
      arc("var(--p-menstrual)", 1, ci.per) +
      arc("var(--p-follicular)", ci.per + 1, ov - 2) +
      arc("var(--p-ovulation)", ov - 1, ov + 1) +
      arc("var(--p-luteal)", ov + 2, len) +
      '</svg><div class="center"><div class="emoji">' + p.emoji + '</div><div class="phase-name">' + p.name.split(" ")[0] + '</div><div class="sub">день ' + ci.day + ' · ' + p.sub + '</div></div></div></div>';
  }

  /* ---------- screens ---------- */
  function screenToday() {
    var ci = cycleInfo(), p = PHASES[ci.phase], sig = SIGNAL[state.intimacy.value] || SIGNAL.yellow;
    var td = parseISO(isoToday());
    return '' +
      head(fmtWeekday(td) + ", " + fmtDate(td), "Сегодня",
        '<span class="pill"><span class="dot" style="background:' + p.color + '"></span>День ' + ci.day + '</span>') +
      ring(ci) +
      card("💛 Как ты можешь себя чувствовать", p.feel, "insight") +
      card("📅 Прогноз", "Следующая менструация примерно через <b>" + ci.daysToNext + " дн.</b> (" + fmtDate(ci.nextPeriod) + "). " + (ci.fertile ? "Сейчас фертильное окно — контрацепция, если беременность не в планах." : "Сейчас низкая вероятность зачатия — но это не метод контрацепции.")) +
      '<p class="section-label">Близость сегодня — решаешь только ты</p>' +
      '<div class="seg" data-seg="intimacy">' +
        segBtn("green", "🟢", "Открыта") + segBtn("yellow", "🟡", "Может быть") + segBtn("red", "🔴", "Не сегодня") +
      '</div>' +
      '<p class="caption" style="text-align:left">Партнёр увидит только выбранный сигнал — не даты и не симптомы.</p>' +
      '<p class="section-label">Как ты себя чувствуешь?</p>' +
      moodRow() +
      '<button class="btn" data-act="save-today">Сохранить в дневник</button>';
  }

  function screenDiary() {
    var today = isoToday();
    var entry = state.diary[today] || { tags: [], mood: null };
    var tags = [["🩸","Выделения"],["⚡","Энергия"],["😴","Сон"],["🤕","Боль"],["❤️","Либидо"],["🍫","Аппетит"]];
    var grid = tags.map(function (t) {
      var sel = entry.tags.indexOf(t[1]) !== -1 ? " sel" : "";
      return '<div class="log-cell' + sel + '" data-tag="' + t[1] + '"><span class="em">' + t[0] + '</span>' + t[1] + '</div>';
    }).join("");
    // trends: energy by phase from logged diary is sparse in a demo → show illustrative + counts
    var count = Object.keys(state.diary).length;
    var energy = [["Менструация","35","var(--p-menstrual)"],["Фолликул.","80","var(--p-follicular)"],["Овуляция","95","var(--p-ovulation)"],["Лютеин.","50","var(--p-luteal)"]];
    var bars = energy.map(function (e) { return '<div class="bar-row"><span class="name">' + e[0] + '</span><div class="bar-track"><div class="bar-fill" style="width:' + e[1] + '%;background:' + e[2] + '"></div></div></div>'; }).join("");
    return '' +
      head(fmtDate(parseISO(today)), "Дневник", "") +
      '<p class="section-label">Отметь, что сегодня</p>' +
      '<div class="log-grid">' + grid + '</div>' +
      '<button class="btn sm" data-act="save-diary" style="margin-top:12px">Сохранить запись</button>' +
      '<p class="section-label" style="margin-top:18px">Твои тренды <span style="font-weight:400">· записей: ' + count + '</span></p>' +
      card("Энергия по фазам", bars) +
      card("🔎 Инсайт", "Отмечай самочувствие каждый день — через пару циклов приложение покажет твои личные закономерности (сон, энергия, настроение по фазам).", "insight") +
      card("🩺 Забота о здоровье", "Если цикл сильно нерегулярный или боль слишком сильная — возможно, стоит показаться врачу.<br><button class=\"btn ghost sm\" data-act=\"pdf\" style=\"margin-top:10px\">Сформировать выписку для врача</button>", "redflag") +
      '<p class="caption">Ориентир, не диагноз. Каждая женщина индивидуальна.</p>';
  }

  var chatLog = [{ who: "bot", text: "Привет! Я помогу разобраться в твоём цикле и самочувствии. Спроси что угодно 💛" }];
  function screenAssistant() {
    var msgs = chatLog.map(function (m) { return '<div class="msg ' + m.who + '">' + esc(m.text).replace(/&lt;b&gt;/g,"<b>").replace(/&lt;\/b&gt;/g,"</b>") + '</div>'; }).join("");
    var sug = ["Почему я устаю перед месячными?","Когда самые фертильные дни?","Что такое лютеиновая фаза?"]
      .map(function (q) { return '<button data-ask="' + esc(q) + '">' + esc(q) + '</button>'; }).join("");
    return '' +
      head("На связи 24/7", "Ассистент", "") +
      '<div class="chat" id="chat">' + msgs + '</div>' +
      '<div class="suggest">' + sug + '</div>' +
      '<div class="chat-input"><input id="chat-input" type="text" placeholder="Напиши вопрос…" aria-label="Вопрос ассистенту" /><button class="send" data-act="send" title="Отправить">↑</button></div>' +
      '<p class="caption">Информация образовательная и не заменяет консультацию врача. Ответы формируются на устройстве.</p>';
  }

  function screenPhases() {
    var ci = cycleInfo();
    var order = ["menstrual","follicular","ovulation","luteal"];
    var ranges = { menstrual: "дни 1–" + ci.per, follicular: "дни " + (ci.per + 1) + "–" + (ci.ovDay - 2), ovulation: "≈день " + ci.ovDay, luteal: "дни " + (ci.ovDay + 2) + "–" + ci.len };
    var bg = { menstrual: "#f6e0e6", follicular: "#dcefe4", ovulation: "#f7e6d5", luteal: "#e7e1f0" };
    var items = order.map(function (k) {
      var p = PHASES[k], now = k === ci.phase;
      return '<div class="phase-item' + (now ? " now" : "") + '">' +
        '<div class="phase-emoji-box" style="background:' + bg[k] + ';color:' + p.color + '">' + p.emoji + '</div>' +
        '<div><h4>' + p.name + (now ? ' · сейчас' : '') + '</h4><span class="days">' + ranges[k] + " · " + p.sub + '</span>' +
        '<p>' + p.feel + ' <b style="color:var(--ink)">Партнёру:</b> ' + p.partner + '</p></div></div>';
    }).join("");
    return head("Твой цикл", "Фазы", "") + items + '<p class="caption">Ориентир для цикла ' + ci.len + ' дней. Каждая женщина индивидуальна.</p>';
  }

  function screenPartner() {
    var ci = cycleInfo(), p = PHASES[ci.phase], sig = SIGNAL[state.intimacy.value] || SIGNAL.yellow;
    var name = esc(state.partnerName && state.role === "partner" ? "Она" : "Аня");
    return '' +
      head("Режим поддержки", "Для партнёра", "") +
      '<div class="support-hero"><div class="who">' + name + ' сейчас в фазе</div><div class="big">' + p.emoji + " " + p.name + '</div><span class="tag">Подсказка дня</span></div>' +
      '<div class="card signal-card"><div class="signal-badge">' + sig.em + '</div><div><h3 style="margin-bottom:2px">' + name + ' отметила: ' + sig.title + '</h3><p>' + sig.text + '</p></div></div>' +
      card("🎯 Как поддержать сегодня", p.partner, "insight") +
      '<div class="card"><div class="do-dont"><div class="col"><h5 style="color:var(--good)">Помогает</h5><ul><li>Спросить, а не предполагать</li><li>Забота и внимание</li><li>Помощь по быту</li></ul></div><div class="col"><h5 style="color:var(--warn)">Осторожно</h5><ul><li>Не давить и не обесценивать</li><li>Контрацепция — общая тема</li></ul></div></div></div>' +
      '<div class="card"><h3>🎓 Мини-курс: гормональная грамотность</h3><p>Урок 2 из 5 — «Что такое ПМС и как быть рядом».</p><div class="bar-track" style="margin:8px 0"><div class="bar-fill" style="width:40%"></div></div></div>' +
      '<p class="caption">Партнёр видит только то, чем она решила поделиться.</p>';
  }

  function screenSettings() {
    return '' +
      head("Настройки и приватность", "Настройки", "") +
      '<div class="field"><label>Имя (как обращаться)</label><input type="text" id="s-name" value="' + esc(state.partnerName) + '" /></div>' +
      '<div class="field"><label>Начало последней менструации</label><input type="date" id="s-last" value="' + state.lastPeriod + '" /></div>' +
      '<div class="field"><label>Средняя длина цикла: <span id="s-lenval">' + state.cycleLength + '</span> дн.</label><div class="stepper"><button data-step="len:-1">−</button><span class="val" id="s-len">' + state.cycleLength + '</span><button data-step="len:1">+</button></div></div>' +
      '<div class="field"><label>Длительность менструации: <span id="s-perval">' + state.periodLength + '</span> дн.</label><div class="stepper"><button data-step="per:-1">−</button><span class="val" id="s-per">' + state.periodLength + '</span><button data-step="per:1">+</button></div></div>' +
      '<button class="btn" data-act="save-settings">Сохранить</button>' +
      card("🔒 Приватность", "Все данные хранятся только на этом устройстве (localStorage). Мы не отправляем их на сервер и не передаём рекламодателям.", "insight") +
      '<button class="btn danger" data-act="wipe">Удалить все мои данные</button>' +
      '<p class="caption">Версия MVP · демонстрационная. Прогнозы — ориентир, не медицинская рекомендация и не средство контрацепции.</p>';
  }

  /* ---------- small builders ---------- */
  function head(date, title, right) {
    var gear = state.onboarded ? '<button class="set" data-act="settings" title="Настройки">⚙️</button>' : "";
    return '<div class="head"><div><div class="date">' + esc(date) + '</div><h1>' + esc(title) + '</h1></div>' + (right || gear) + '</div>';
  }
  function card(title, body, cls) { return '<div class="card ' + (cls || "") + '"><h3>' + title + '</h3><p>' + body + '</p></div>'; }
  function segBtn(v, em, label) {
    var sel = state.intimacy.value === v ? " sel" : "";
    return '<button class="' + sel.trim() + '" data-v="' + v + '"><span class="lt">' + em + '</span>' + label + '</button>';
  }
  function moodRow() {
    var today = isoToday(), cur = (state.diary[today] || {}).mood;
    var moods = [["great","😄"],["ok","🙂"],["tired","😔"],["irrit","😤"],["pain","🤕"]];
    return '<div class="row">' + moods.map(function (m) {
      return '<button class="mood' + (cur === m[0] ? " sel" : "") + '" data-mood="' + m[0] + '">' + m[1] + '</button>';
    }).join("") + '</div>';
  }

  /* ---------- onboarding ---------- */
  var obStep = 1, obRole = state.role;
  function renderOnboarding() {
    var dots = [1,2,3].map(function (n) { return '<i class="' + (n <= obStep ? "on" : "") + '"></i>'; }).join("");
    var body;
    if (obStep === 1) {
      body = '<h3>Кто вы?</h3><p class="sub">От этого зависит, как будет выглядеть приложение.</p>' +
        '<div class="choice">' +
          '<button class="choice-card' + (obRole === "woman" ? " sel" : "") + '" data-role="woman"><span class="em">👩</span><span><span class="t">Я веду свой цикл</span><br><span class="d">Трекер, самочувствие, приватность</span></span></button>' +
          '<button class="choice-card' + (obRole === "partner" ? " sel" : "") + '" data-role="partner"><span class="em">🧑</span><span><span class="t">Я поддерживаю партнёршу</span><br><span class="d">Подсказки, как быть рядом</span></span></button>' +
        '</div><div class="foot"><button class="btn" data-act="ob-next">Продолжить</button></div>';
    } else if (obStep === 2) {
      body = '<h3>Пара деталей о цикле</h3><p class="sub">Нужно только для прогноза. Данные приватны.</p>' +
        '<div class="field"><label>Начало последней менструации</label><input type="date" id="ob-last" value="' + state.lastPeriod + '" /></div>' +
        '<div class="field"><label>Средняя длина цикла: <span id="ob-lenval">' + state.cycleLength + '</span> дн.</label><div class="stepper"><button data-step="oblen:-1">−</button><span class="val">' + state.cycleLength + '</span><button data-step="oblen:1">+</button></div></div>' +
        '<div class="foot"><button class="btn" data-act="ob-next">Продолжить</button></div>';
    } else {
      var goalList = ["Понимать себя","Поддержать партнёршу","Планирую беременность","Избегаю беременности","Следить за симптомами"];
      var chips = goalList.map(function (g) { return '<button class="chip' + (state.goals.indexOf(g) !== -1 ? " sel" : "") + '" data-goal="' + esc(g) + '">' + g + '</button>'; }).join("");
      body = '<h3>Ваши цели</h3><p class="sub">Можно выбрать несколько — подстроим контент.</p><div class="chips">' + chips + '</div>' +
        '<div class="foot"><button class="btn" data-act="ob-finish">Открыть приложение</button><button class="skip" data-act="ob-finish">Пропустить</button></div>';
    }
    app.innerHTML = '<div class="ob"><div class="brand"><div class="k">Добро пожаловать</div><h2>Цикл вдвоём</h2></div><div class="dots">' + dots + '</div>' + body + '</div>';
  }

  /* ---------- main render ---------- */
  var settingsOpen = false;
  function render() {
    if (!state.onboarded) { renderOnboarding(); return; }
    var body;
    if (settingsOpen) body = screenSettings();
    else if (state.role === "partner") body = { partner: screenPartner, phases: screenPhases, ai: screenAssistant }[state.tab] ? { partner: screenPartner, phases: screenPhases, ai: screenAssistant }[state.tab]() : screenPartner();
    else body = ({ today: screenToday, diary: screenDiary, ai: screenAssistant, phases: screenPhases, partner: screenPartner }[state.tab] || screenToday)();
    app.innerHTML = '<div class="view" id="view">' + body + '</div>' + (settingsOpen ? "" : tabbar());
    var v = document.getElementById("view"); if (v && state.tab === "ai") { var c = document.getElementById("chat"); if (c) c.scrollTop = c.scrollHeight; }
  }
  function tabbar() {
    var tabs = state.role === "partner"
      ? [["partner","Партнёр",iconHeart],["phases","Фазы",iconCycle],["ai","Ассистент",iconChat]]
      : [["today","Сегодня",iconClock],["diary","Дневник",iconBook],["ai","Ассистент",iconChat],["phases","Фазы",iconCycle],["partner","Партнёр",iconHeart]];
    return '<div class="tabbar">' + tabs.map(function (t) {
      return '<button class="tab' + (state.tab === t[0] ? " sel" : "") + '" data-tab="' + t[0] + '">' + t[2] + '<span>' + t[1] + '</span></button>';
    }).join("") + '</div>';
  }
  var iconClock = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';
  var iconBook = '<svg viewBox="0 0 24 24"><path d="M5 4h11l3 3v13H5z"/><path d="M9 9h6M9 13h6M9 17h3"/></svg>';
  var iconChat = '<svg viewBox="0 0 24 24"><path d="M5 5h14v10H9l-4 4z"/><path d="M9 10h.01M12 10h.01M15 10h.01"/></svg>';
  var iconCycle = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18"/></svg>';
  var iconHeart = '<svg viewBox="0 0 24 24"><path d="M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 11c0 5.5-7 10-7 10z"/></svg>';

  /* ---------- events ---------- */
  app.addEventListener("click", function (e) {
    var t = e.target.closest("[data-tab],[data-act],[data-v],[data-mood],[data-tag],[data-ask],[data-role],[data-goal],[data-step]");
    if (!t) return;

    if (t.dataset.tab) { state.tab = t.dataset.tab; settingsOpen = false; save(); render(); return; }
    if (t.dataset.role) { obRole = t.dataset.role; renderOnboarding(); return; }
    if (t.dataset.goal) {
      var g = t.dataset.goal, i = state.goals.indexOf(g);
      if (i === -1) state.goals.push(g); else state.goals.splice(i, 1);
      t.classList.toggle("sel"); return;
    }
    if (t.dataset.step) { handleStep(t.dataset.step); return; }
    if (t.dataset.v) { state.intimacy = { date: isoToday(), value: t.dataset.v }; save(); render(); return; }
    if (t.dataset.mood) { setDiary("mood", t.dataset.mood); render(); return; }
    if (t.dataset.tag) { toggleTag(t.dataset.tag); t.classList.toggle("sel"); return; }
    if (t.dataset.ask) { ask(t.dataset.ask); return; }

    var a = t.dataset.act;
    if (a === "settings") { settingsOpen = true; render(); }
    else if (a === "ob-next") { obNext(); }
    else if (a === "ob-finish") { obFinish(); }
    else if (a === "save-today" || a === "save-diary") { flash(t, "Сохранено ✓"); save(); }
    else if (a === "pdf") { flash(t, "Демо: выписка сформирована"); }
    else if (a === "send") { sendChat(); }
    else if (a === "save-settings") { saveSettings(t); }
    else if (a === "wipe") { wipe(); }
  });
  app.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target.id === "chat-input") { e.preventDefault(); sendChat(); }
  });

  function handleStep(code) {
    var parts = code.split(":"), what = parts[0], delta = +parts[1];
    if (what === "len") { state.cycleLength = clamp(state.cycleLength + delta, 21, 40); document.getElementById("s-len").textContent = state.cycleLength; document.getElementById("s-lenval").textContent = state.cycleLength; }
    else if (what === "per") { state.periodLength = clamp(state.periodLength + delta, 2, 10); document.getElementById("s-per").textContent = state.periodLength; document.getElementById("s-perval").textContent = state.periodLength; }
    else if (what === "oblen") { state.cycleLength = clamp(state.cycleLength + delta, 21, 40); renderOnboarding(); }
  }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

  function obNext() {
    if (obStep === 1) { state.role = obRole; }
    if (obStep === 2) { var d = document.getElementById("ob-last"); if (d && d.value) state.lastPeriod = d.value; }
    obStep = Math.min(3, obStep + 1); renderOnboarding();
  }
  function obFinish() {
    state.role = obRole;
    var d = document.getElementById("ob-last"); if (d && d.value) state.lastPeriod = d.value;
    state.onboarded = true; state.tab = state.role === "partner" ? "partner" : "today";
    save(); render();
  }

  function setDiary(field, val) {
    var today = isoToday();
    if (!state.diary[today]) state.diary[today] = { tags: [], mood: null };
    state.diary[today][field] = (state.diary[today][field] === val) ? null : val;
    save();
  }
  function toggleTag(tag) {
    var today = isoToday();
    if (!state.diary[today]) state.diary[today] = { tags: [], mood: null };
    var arr = state.diary[today].tags, i = arr.indexOf(tag);
    if (i === -1) arr.push(tag); else arr.splice(i, 1);
    save();
  }

  function ask(q) { chatLog.push({ who: "user", text: q }); chatLog.push({ who: "bot", text: assistantAnswer(q) }); render(); }
  function sendChat() { var el = document.getElementById("chat-input"); if (!el) return; var v = el.value.trim(); if (!v) return; el.value = ""; ask(v); }

  function saveSettings(btn) {
    var n = document.getElementById("s-name"), l = document.getElementById("s-last");
    if (n) state.partnerName = n.value.trim() || "Партнёр";
    if (l && l.value) state.lastPeriod = l.value;
    save(); flash(btn, "Сохранено ✓");
    setTimeout(function () { settingsOpen = false; render(); }, 700);
  }
  function wipe() {
    if (!confirm("Удалить все данные приложения с этого устройства? Это действие необратимо.")) return;
    try { localStorage.removeItem(KEY); } catch (e) {}
    state = defaultState(); settingsOpen = false; obStep = 1; obRole = "woman"; chatLog = chatLog.slice(0, 1);
    render();
  }
  function flash(btn, text) { var old = btn.textContent; btn.textContent = text; btn.disabled = true; setTimeout(function () { btn.textContent = old; btn.disabled = false; }, 1100); }

  /* ---------- boot ---------- */
  render();
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () { navigator.serviceWorker.register("sw.js").catch(function () {}); });
  }
})();
