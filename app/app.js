/* Цикл вдвоём — MVP v2. Privacy-first: данные только в localStorage этого устройства. */
(function () {
  "use strict";
  var KEY = "cycle-vdvoem-v1";
  var app = document.getElementById("app");
  var VOICE = !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  /* Системный промпт для «умного» ИИ-режима (настоящая LLM). */
  var SYSTEM_PROMPT = [
    "Ты — тёплый, чуткий помощник в приложении о женском цикле «Цикл вдвоём». Ты поддерживаешь и женщину, и её партнёра. Ты не врач и не бот, выдающий справку, а понимающий собеседник: сначала слышишь человека, потом помогаешь.",
    "Приоритет — поддержка, потом информация. Дай почувствовать, что человека понимают и он не один.",
    "Ценности: каждая женщина индивидуальна, универсальной «нормы» нет; понимать, а не предполагать (если она говорит, что ей больно или не хочется — верь сразу); любовь ≠ секс, забота не «предоплата» за близость; согласие и никакого давления; в менструацию секса и инициативы нет, если она сама не предложила; разрушай миф про «пик желания в овуляцию» — часто наоборот, бывает боль; её тело — её.",
    "Про близость с женщиной говори в последнюю очередь и бережно: не внушай ей, что она должна что-то хотеть или чувствовать — желание индивидуально, его может не быть, и это нормально; тема секса нужна только чтобы она лучше понимала себя и дала себе то, что ей нужно. Границы важнее всего: она не обязана соглашаться через боль или потому что партнёр хочет — «нет» это достаточная причина; терпеть вредно для тела и психики. Чувствительность и ощущения меняются по фазам (после месячных и к овуляции часто ярче; в пик овуляции бывает боль — тогда лучше воздержаться). Прелюдия важна почти всегда, при меньшем желании — дольше и нежнее. Про зачатие/защиту: в конце фолликулярной и в начале овуляции при незащищённой близости можно забеременеть; планирующим — подходящие дни, не планирующим — надёжная защита, прерванный акт ненадёжен. Женщина — человек, а не объект; приложение учит жить по своим циклам (гормоны, еда, спорт, отдых), а секс — лишь одна из частей жизни.",
    "Тон: тепло, простыми словами, 2–5 предложений, без списков-чеклистов, без канцелярита, без «как ИИ», без обесценивания. Сначала эмпатия, потом по делу. Отвечай на языке пользователя (по умолчанию русский).",
    "Безопасность: не ставь диагнозы; при тревожных признаках мягко советуй врача; календарный расчёт — не контрацепция. КРИЗИС: если звучит безнадёжность, «жизнь бессмысленна», «я никому не нужна» или мысли о самоповреждении — отнесись максимально серьёзно и тепло, скажи, что она важна и не одна, мягко предложи связаться с близким и линией психологической помощи, при угрозе жизни — 112. Никогда не отмахивайся."
  ].join("\n\n");

  /* ---------- state ---------- */
  function defaultState() {
    return {
      onboarded: false, role: "woman", partnerName: "Партнёр",
      lastPeriod: isoToday(), cycleLength: 28, periodLength: 5,
      goals: ["Понимать себя"],
      intimacy: { date: isoToday(), value: "yellow" },
      diary: {}, course: [], lastMood: null,
      ai: { mode: "server", server: "", token: "", userId: "", status: null, payProvider: "yookassa",
            provider: "claude", key: "", model: "claude-sonnet-5" },
      tab: "today"
    };
  }
  function load() { try { var s = JSON.parse(localStorage.getItem(KEY)); if (s && typeof s === "object") return Object.assign(defaultState(), s); } catch (e) {} return defaultState(); }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  var state = load();

  /* ---------- server (monetized proxy: подписка + кредиты) ---------- */
  // Владелец: впиши сюда адрес своего сервера (VPS), напр. "https://api.tvoydomen.ru".
  // Тогда у клиентов по умолчанию включён умный ИИ через твой сервер с лимитами и оплатой.
  var API_BASE = "";
  function apiBase() { return ((state.ai && state.ai.server) || API_BASE || "").replace(/\/+$/, ""); }
  function serverOn() { return !!(state.ai && state.ai.mode === "server" && apiBase()); }
  function byokOn() { return !!(state.ai && state.ai.mode === "byok" && state.ai.key); }
  function smartOn() { return serverOn() || byokOn(); }
  function authHdr() { return { "content-type": "application/json", "authorization": "Bearer " + state.ai.token }; }

  function ensureAccount() {
    if (!serverOn()) return Promise.reject(new Error("сервер не настроен"));
    if (state.ai.token) return Promise.resolve();
    return fetch(apiBase() + "/v1/account/init", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (!d.token) throw new Error("не удалось создать аккаунт"); state.ai.token = d.token; state.ai.userId = d.userId; save(); });
  }
  function serverChat() {
    var msgs = llmMessages(); while (msgs.length && msgs[0].role !== "user") msgs.shift();
    var ci = cycleInfo();
    var ctx = { role: state.role, phaseName: PHASES[ci.phase].name, day: ci.day, len: ci.len, mood: state.lastMood || "" };
    return fetch(apiBase() + "/v1/chat", { method: "POST", headers: authHdr(), body: JSON.stringify({ messages: msgs, ctx: ctx }) })
      .then(function (r) { return r.json().then(function (d) { return { s: r.status, d: d }; }); })
      .then(function (o) {
        if (o.s === 402) { var e = new Error("quota"); e.quota = true; e.status = o.d.status; throw e; }
        if (o.s === 401) { state.ai.token = ""; save(); throw new Error("нужно переподключиться"); }
        if (o.d.error) throw new Error(o.d.message || o.d.error);
        return { text: o.d.text, status: o.d.status };
      });
  }
  function refreshMe() {
    if (!serverOn() || !state.ai.token) return Promise.resolve(null);
    return fetch(apiBase() + "/v1/me", { headers: { "authorization": "Bearer " + state.ai.token } })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d && !d.error) { state.ai.status = d; save(); } return d; })
      .catch(function () { return null; });
  }
  function startCheckout(product, packId) {
    if (!serverOn()) { alert("Сначала укажи адрес сервера в Настройках."); return; }
    var provider = state.ai.payProvider || "yookassa";
    ensureAccount()
      .then(function () { return fetch(apiBase() + "/v1/billing/checkout", { method: "POST", headers: authHdr(), body: JSON.stringify({ product: product, packId: packId, provider: provider }) }); })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.url) { location.href = d.url; } else { alert("Не удалось создать оплату: " + (d.message || d.error || "ошибка")); } })
      .catch(function (e) { alert("Ошибка оплаты: " + (e && e.message ? e.message : "")); });
  }
  function serverRemaining(st) {
    if (!st) return null;
    var n = 0;
    if (st.sub && st.sub.active) n += Math.max(0, (st.sub.remaining != null ? st.sub.remaining : st.sub.cap - st.sub.used));
    n += (st.credits || 0);
    if (st.free) n += (st.free.remaining || 0);
    return n;
  }

  /* ---------- dates ---------- */
  function isoToday() { return new Date().toISOString().slice(0, 10); }
  function parseISO(s) { var p = s.split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function daysBetween(a, b) { return Math.floor((b - a) / 86400000); }
  function addDays(d, n) { var x = new Date(d.getTime()); x.setDate(x.getDate() + n); return x; }
  function fmtDate(d) { var m = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"]; return d.getDate() + " " + m[d.getMonth()]; }
  function fmtWeekday(d) { return ["Воскресенье","Понедельник","Вторник","Среда","Четверг","Пятница","Суббота"][d.getDay()]; }

  /* ---------- cycle engine ---------- */
  function cycleInfo() {
    var len = state.cycleLength, per = state.periodLength, start = parseISO(state.lastPeriod), today = parseISO(isoToday());
    var el = daysBetween(start, today); if (el < 0) el = 0;
    var day = (el % len) + 1, cp = Math.floor(el / len), cur = addDays(start, cp * len), next = addDays(cur, len);
    var ovDay = Math.max(per + 2, len - 14);
    return { day: day, len: len, per: per, ovDay: ovDay, fertile: day >= ovDay - 5 && day <= ovDay + 1, nextPeriod: next, daysToNext: daysBetween(today, next), phase: phaseFor(day, len, per, ovDay) };
  }
  function phaseFor(day, len, per, ov) { if (day <= per) return "menstrual"; if (day >= ov - 1 && day <= ov + 1) return "ovulation"; if (day < ov - 1) return "follicular"; return "luteal"; }

  var PHASES = {
    menstrual: { name: "Менструация", short: "Отдых", emoji: "🌑", color: "var(--p-menstrual)",
      today: "Тебе может быть тяжело: боль, отёчность, усталость. Отдыхай и будь к себе бережна.",
      feel: "Боль, отёки, усталость, всё чувствуется острее.",
      partner: "Никакого секса и никакой инициативы — даже мягкой. Только забота, тепло и нежность, потому что любишь.",
      intim: "Секса нет. Только если она сама захочет и сама предложит. Заботься и люби не ради близости.",
      food: ["Печень, красное мясо — железо", "Гречка, чечевица, шпинат", "Тёплое питьё и суп", "Витамин C — усвоить железо"],
      aff: ["Я разрешаю себе отдыхать.", "Моя ценность — не в делах.", "Я нежна к себе."], med: "breath" },
    follicular: { name: "Фолликулярная", short: "Подъём", emoji: "🌱", color: "var(--p-follicular)",
      today: "Сил и лёгкости становится больше. Хорошее время для дел, идей и движения.",
      feel: "Возвращаются силы и лёгкость.",
      partner: "Поддержи её идеи и активности. Близость — если она хочет; всё равно спрашивай, не предполагай.",
      intim: "У многих влечение выше именно сейчас, сразу после месячных. Но всё равно спрашивай.",
      food: ["Свежие овощи и зелень", "Белок: яйца, рыба", "Йогурт, кефир", "Цельные злаки"],
      aff: ["Во мне много сил.", "Я открыта новому.", "Я иду своим темпом."], med: "focus" },
    ovulation: { name: "Овуляция", short: "Фертильность", emoji: "☀️", color: "var(--p-ovulation)",
      today: "Очень индивидуально: у кого-то лёгкость, у кого-то тянущая боль внизу. Прислушайся к себе.",
      feel: "По-разному: от прилива сил до боли. Влечения может и не быть.",
      partner: "Забудь миф про «пик желания». Ей может быть больно, и секса может не хотеться. Наблюдай и говори — внимание без ожиданий.",
      intim: "Стереотип, что тут женщина «жаждет секса», — неправда. Часто наоборот: боль и нет желания. Для зачатия близость нужна ДО овуляции.",
      food: ["Лёгкая клетчатка", "Ягоды, антиоксиданты", "Больше воды", "Цинк: тыквенные семечки"],
      aff: ["Я слушаю своё тело.", "Я достойна любви.", "Мой голос важен."], med: "gratitude" },
    luteal: { name: "Лютеиновая", short: "Спад", emoji: "🌘", color: "var(--p-luteal)",
      today: "Энергия снижается, возможен ПМС. Будь мягче к себе.",
      feel: "Спад, чувствительность, тяга к еде, раздражительность.",
      partner: "Терпение и помощь по быту. Меньше споров, больше принятия. Нежность без давления.",
      intim: "Переменно. Нежность без давления, только по её желанию.",
      food: ["Магний: орехи, зелень", "Сложные углеводы", "Меньше соли и кофеина", "Кальций: йогурт"],
      aff: ["Я принимаю свои чувства.", "Мне можно быть неидеальной.", "Я — не мои тревоги."], med: "selfcompassion" }
  };
  var ORDER = ["menstrual", "follicular", "ovulation", "luteal"];
  var SIGNAL = {
    green: { em: "🟢", title: "«Открыта»", text: "Взаимная инициатива приветствуется." },
    yellow: { em: "🟡", title: "«Может быть»", text: "Внимание — да, инициатива — мягко и с вопросом." },
    red: { em: "🔴", title: "«Не сегодня»", text: "Сегодня — забота без близости. Просто будь рядом." }
  };
  var IRON = {
    eat: ["Говядина, печень", "Чечевица, фасоль, нут", "Шпинат, петрушка", "Гречка, овсянка", "Гранат, яблоки", "Тыквенные семечки"],
    boost: "Витамин C (перец, цитрус, ягоды) усиливает усвоение железа.",
    avoid: "Чай и кофе — не во время еды: они мешают усвоению."
  };
  var MED = {
    breath: { title: "Дыхание 4-7-8", mins: 2, note: "Успокаивает за пару минут.", steps: ["Вдох носом на 4 счёта", "Задержи дыхание на 7", "Выдох ртом на 8", "Повтори 4 раза"] },
    selfcompassion: { title: "Мягкость к себе", mins: 3, note: "Когда трудно и грустно.", steps: ["Положи руку на сердце", "Скажи: мне трудно — и это нормально", "Дыши медленно и глубоко", "Ты уже делаешь достаточно"] },
    gratitude: { title: "Благодарность", mins: 2, note: "Больше тепла и радости.", steps: ["Сделай глубокий вдох", "Вспомни 3 хороших момента", "Побудь в этом чувстве", "Поблагодари себя"] },
    focus: { title: "Ясность на день", mins: 3, note: "Настроиться и найти опору.", steps: ["Сядь удобно, закрой глаза", "3 медленных вдоха", "Представь один добрый шаг на сегодня", "Открой глаза с улыбкой"] },
    ground: { title: "Заземление 5-4-3-2-1", mins: 3, note: "Быстро вернуться в момент.", steps: ["Назови 5 вещей, что видишь", "4 — что слышишь", "3 — что можешь потрогать", "2 — какие запахи", "1 — глубокий вдох"] }
  };
  var MED_LIST = ["breath", "selfcompassion", "gratitude", "focus", "ground"];
  var MOVIES = [
    ["Амели", "тёплое и доброе"], ["Головоломка", "все чувства важны"], ["Тайная жизнь Уолтера Митти", "решиться мечтать"],
    ["Джули и Джулия", "радость в мелочах"], ["Маленькие женщины", "быть собой"], ["Отель «Мэриголд»", "светлое, жизнеутверждающее"],
    ["Ешь, молись, люби", "поиск себя"], ["Форрест Гамп", "доброта и путь"]
  ];
  var COURSE = [
    { id: "main", title: "Главное: понимать, а не получать", mins: 2, body: [
      "Это приложение — не инструкция, как получить секс или сделать свою жизнь удобнее. Оно про другое: понимать её и любить по-настоящему.",
      "Забота, внимание и нежность — это не «предоплата» за близость. Если ты нежен только тогда, когда хочешь секса, она это чувствует. И это ранит.",
      "И ещё важное: все женщины разные. То, что написано про фазы, — это общая картинка, а не закон. У твоей женщины всё может быть по-своему.",
      "Поэтому не действуй «по учебнику» — узнавай именно её. Как? Наблюдай и разговаривай. Спрашивай, как она себя чувствует и что ей сейчас нужно. Это и есть забота." ] },
    { id: "menstr", title: "Менструация: забота без ожиданий", mins: 2, body: [
      "В эти дни ей часто физически тяжело: тянет и болит низ живота, тело будто отекает, наваливается усталость, а эмоции ближе к поверхности.",
      "Что ей нужно: тепло, покой и чтобы ты взял на себя быт. Грелка, чай, «полежи, я всё сделаю». Просто будь рядом.",
      "Про близость честно: секса в эти дни нет. И никакой инициативы — даже мягкой и лёгкой. Единицы женщин хотят близости во время месячных, и не на этих исключениях строятся отношения.",
      "Секс возможен только в одном случае: если она сама захотела и сама предложила. Во всех остальных — нет.",
      "Самое ценное сейчас — чтобы она почувствовала, что ты внимателен и нежен просто потому, что любишь её. А не потому, что чего-то хочешь." ] },
    { id: "afterm", title: "После месячных: возвращение сил", mins: 2, body: [
      "Когда месячные заканчиваются, к ней возвращаются силы и лёгкость. Голова яснее, настроение выше, тянет на новое.",
      "У многих женщин именно сейчас — а не в «книжную овуляцию» — просыпается желание. У кого-то пик влечения приходит сразу после месячных.",
      "Это хорошее время для свиданий, планов, живых разговоров. И для близости — если она этого хочет.",
      "Но правило то же: спрашивай, а не предполагай. «Хочу тебя» звучит теплее, когда за ним слышно «а ты как?»." ] },
    { id: "ovul", title: "Овуляция: разрушаем миф", mins: 3, body: [
      "Есть стереотип, будто в овуляцию женщина «сходит с ума от желания». Это миф, и он мешает понимать реальную женщину.",
      "На самом деле овуляция очень индивидуальна. У многих это не про желание, а про боль: тянет или резко колет внизу живота, когда выходит яйцеклетка. Бывает так сильно, что трудно даже сесть. Некоторые чувствуют, в каком боку это происходит.",
      "И желание в этот момент часто, наоборот, пропадает — какой секс, когда болит. У кого-то оно есть, у кого-то нет. Это нормально и очень по-разному.",
      "Если вы планируете ребёнка, полезно знать: активная близость нужна ДО овуляции. Сперматозоиды живут несколько дней и «дожидаются» яйцеклетку, которая выходит как раз в овуляцию.",
      "Вывод один: не иди по стереотипу. Понаблюдай за своей женщиной и поговори с ней — только так ты узнаешь, как овуляция проходит именно у неё." ] },
    { id: "beforem", title: "Перед месячными: ПМС и как быть рядом", mins: 2, body: [
      "За несколько дней до месячных гормоны идут вниз — начинается то, что называют ПМС. Это не «характер испортился», это тело.",
      "Как это может проявляться: перепады настроения, раздражительность, тревога, слёзы без явной причины, усталость, тяга к сладкому, болит и наливается грудь.",
      "Что помогает: твоё спокойствие и терпение. Не спорь по мелочам, не обесценивай («ты просто на нервах»), возьми на себя быт, будь тёплым и предсказуемым.",
      "Иногда лучшее — не «чинить проблему», а просто обнять и сказать: «я рядом». Близость — только по её желанию, без всякого давления." ] },
    { id: "know", title: "Как понять именно твою женщину", mins: 2, body: [
      "Всё, что здесь написано, — это общая карта. Живая женщина всегда богаче любой схемы.",
      "Два простых способа узнать её по-настоящему: наблюдать и разговаривать. Замечай, как меняются её силы, настроение и желание в разные дни. И спрашивай прямо, по-доброму: «как ты сегодня? что тебе сейчас нужно?».",
      "Она — лучший эксперт по себе. Если она говорит, что ей больно или не хочется, — верь ей сразу, без «ну может, всё-таки».",
      "И помни главное: её тело — её. Твоя забота нужна не чтобы что-то получить, а потому что ты любишь. Тогда и близость, когда она случается, будет настоящей." ] }
  ];
  var NEG = { tired: 1, irrit: 1, sad: 1, pain: 1 };
  var MOODS = [["great", "😄"], ["ok", "🙂"], ["tired", "😔"], ["sad", "😢"], ["irrit", "😤"], ["pain", "🤕"]];

  /* ---------- assistant (offline knowledge base) ---------- */
  var KB = [
    { k: ["привет","здравств","хай","добрый"], a: "Привет! 💛 Спроси про месячные, овуляцию, ПМС, боль, настроение, сон, либидо, питание, железо или контрацепцию." },
    { k: ["беремен","забеременеть","зачат","месячн","менструац"], a: "Забеременеть во время месячных менее вероятно, но НЕ невозможно (при коротком цикле). Если беременность не в планах — контрацепция нужна в любой день. Это ориентир, не метод контрацепции." },
    { k: ["фертил","овуляц","самые лучшие дни","планир"], a: "Наиболее фертильны ~5 дней до овуляции и её день (у тебя ≈день {ov}, сейчас день {day}). Для зачатия — близость в эти дни; чтобы избежать — контрацепция." },
    { k: ["устал","нет сил","энерг","слаб","вял"], a: "Усталость перед месячными — от падения гормонов. Помогают сон, вода, магний, железо. Сильная слабость — к врачу (проверить железо)." },
    { k: ["пмс","предменструальн"], a: "ПМС: перепады настроения, тревога, вздутие, тяга к еде. Облегчают сон, движение, магний, меньше соли/кофеина. Тяжёлый ПМС — к гинекологу." },
    { k: ["раздраж","злюсь","нервн"], a: "Раздражительность перед месячными — частая часть ПМС. Помогают сон, прогулки, дыхание и не пропускать еду." },
    { k: ["плак","груст","подавлен","тоск","ненужн","бессмыслен"], a: "Тебе сейчас тяжело — и это важно. Часто это гормоны в лютеиновой фазе, и станет легче. Если чувство не проходит — открой раздел «Забота → Срочная помощь». Ты не одна 💛" },
    { k: ["трев","паник","беспоко"], a: "Тревога часто усиливается перед месячными. Помогают режим сна, движение, дыхание 4-7-8 (есть в медитациях)." },
    { k: ["боль","спазм","живот","поясниц"], a: "Спазмы — от сокращений матки. Помогают тепло, лёгкая активность, обезболивающее по инструкции, магний. Очень сильная боль — к врачу." },
    { k: ["груд","набух"], a: "Чувствительность груди во второй половине цикла — обычная реакция на гормоны, проходит с месячными." },
    { k: ["секс","близост","интим"], a: "Универсальных «можно/нельзя» дней нет. Есть светофор близости: ты ставишь 🟢/🟡/🔴, партнёр видит только сигнал. Главное — согласие." },
    { k: ["либидо","влечен","желани"], a: "Либидо очень индивидуально. У многих оно выше сразу после месячных, а не «в овуляцию». Миф, что в овуляцию все «хотят»: часто наоборот — бывает боль и желания нет. Ориентируйся на себя, а не на стереотипы. Если желания меньше — с тобой всё в порядке." },
    { k: ["по-разному","по разному","разные ощущен","ярче","оргазм","чувствительн"], a: "Ощущения в близости в разные фазы правда разные — это гормоны. После месячных и ближе к овуляции чувствительность у многих выше, возбуждение приходит быстрее, ощущения ярче. В пик овуляции бывает наоборот — боль и спазмы, тогда близость может быть неприятна, и это нормально. Ориентируйся на себя. Подробно — «Забота → Тело и близость»." },
    { k: ["прелюд","возбужд","разогрев","предыгр"], a: "Прелюдия важна почти всегда — мгновенная готовность бывает редко, и это норма. Когда желания меньше, дай себе больше времени и нежности: так сохраняется чувствительность и близость приносит радость." },
    { k: ["не хочу","терп","больно во время","больно при","заставл","через силу","принужд","партнер хочет","хочет секс","хочет близост","должна ли"], a: "Ты не обязана соглашаться на близость через боль или потому что партнёр хочет. «Нет» — достаточная причина. Когда терпишь через силу, страдают тело и нервная система, остаётся чувство, что тебя использовали. Слушай сигналы тела — так тебе лучше. Ты человек, а не объект." },
    { k: ["прерванн","прерыв","вытаскива"], a: "Прерванный акт — ненадёжный и рискованный способ, полагаться на него нельзя. Если беременность не в планах, в фертильные дни защищайся надёжным методом (барьерный или гормональный по назначению врача)." },
    { k: ["задерж","нерегуляр","сбил","пропал"], a: "Небольшие сдвиги — норма (стресс, сон, нагрузка). Большая задержка или сильная нерегулярность — к врачу." },
    { k: ["выделен","слизь","овуляц"], a: "Выделения меняются: около овуляции — прозрачные, тянущиеся. Зуд, запах, необычный цвет — повод к врачу." },
    { k: ["сон","бессон","высып"], a: "Во второй половине цикла сон часто хуже. Помогают прохлада, режим, меньше экранов и кофеина вечером." },
    { k: ["ест","еда","питан","сладк","тяга","аппетит","железо"], a: "Тяга к сладкому перед месячными — гормоны. Помогают белок, сложные углеводы, магний. Для железа: печень, гречка, чечевица + витамин C. Подробно — «Забота → Питание»." },
    { k: ["спорт","трениров","бег","нагрузк"], a: "Тренироваться можно в любой день. В менструацию и ПМС — мягче (йога, ходьба), около овуляции — больше сил." },
    { k: ["контрацеп","таблетк","презерв","предохран"], a: "Календарный расчёт — НЕ надёжная контрацепция. Барьерные или гормональные методы по назначению врача." },
    { k: ["медитац","дыхан","успоко"], a: "Загляни в «Забота → Медитации»: дыхание 4-7-8, мягкость к себе, заземление 5-4-3-2-1 — короткие и помогают." },
    { k: ["фаз","цикл устро","фолликул","лютеин"], a: "4 фазы: менструация (дни 1–{per}), фолликулярная, овуляция (≈день {ov}), лютеиновая. Подробно — «Все фазы» на «Сегодня»." }
  ];
  function normalize(s) { return " " + String(s).toLowerCase().replace(/ё/g, "е").replace(/[^а-яa-z0-9 ]+/g, " ") + " "; }
  function assistantAnswer(q) {
    var t = normalize(q), ci = cycleInfo(), best = null, bs = 0;
    for (var i = 0; i < KB.length; i++) { var sc = 0; for (var j = 0; j < KB[i].k.length; j++) if (t.indexOf(normalize(KB[i].k[j]).trim()) !== -1) sc++; if (sc > bs) { bs = sc; best = KB[i]; } }
    if (best && bs > 0) return best.a.replace(/\{ov\}/g, ci.ovDay).replace(/\{day\}/g, ci.day).replace(/\{per\}/g, ci.per);
    return "Я отвечаю на темы про цикл: месячные, овуляция, ПМС, боль, настроение, сон, либидо, питание, железо, контрацепция. Спроси про что-то из этого 💛 Это не заменяет врача.";
  }

  /* ---------- helpers ---------- */
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]; }); }
  function head(title, backTo) {
    var left = backTo != null ? '<button class="back" data-nav="__back">← Назад</button>' : '<div class="date">' + fmtWeekday(parseISO(isoToday())) + ", " + fmtDate(parseISO(isoToday())) + '</div>';
    var gear = backTo == null ? '<button class="set" data-nav="settings" title="Настройки">⚙️</button>' : "";
    return '<div class="head"><div>' + left + '<h1>' + esc(title) + '</h1></div>' + gear + '</div>';
  }
  function phase4(cur) {
    return '<div class="phase4">' + ORDER.map(function (k) {
      var p = PHASES[k]; return '<div class="p4' + (k === cur ? " on" : "") + '" style="background:' + p.color + '"><span class="e">' + p.emoji + '</span>' + p.short + '</div>';
    }).join("") + '</div>';
  }
  function micBtn(id) { return VOICE ? '<button class="mic" data-voice="' + id + '" title="Голосовой ввод" aria-label="Голосовой ввод">🎤</button>' : ""; }

  /* ---------- tab screens ---------- */
  function screenToday() {
    var ci = cycleInfo(), p = PHASES[ci.phase];
    var nudge = NEG[state.lastMood] ? '<div class="support-nudge" data-nav="crisis">💗 Тебе сейчас непросто? Загляни за поддержкой →</div>' : "";
    return head(p.name) +
      '<div class="phase-banner" style="background:linear-gradient(135deg,' + p.color + ', color-mix(in srgb,' + p.color + ' 62%, #000))">' +
        '<div class="pb-emoji">' + p.emoji + '</div><h2>' + p.name + '</h2>' +
        '<div class="pb-day">День ' + ci.day + ' · след. месячные через ' + ci.daysToNext + ' дн.</div>' +
        '<div class="pb-line">' + p.today + '</div></div>' +
      phase4(ci.phase) +
      '<button class="back" data-nav="phases" style="margin-bottom:12px">Все фазы →</button>' +
      nudge +
      '<button class="btn" data-nav="checkin" style="margin-bottom:14px">Как ты себя чувствуешь?</button>' +
      '<div class="quick">' +
        qbtn("💗", "Аффирмация", "aff") + qbtn("🧘", "Медитация", "med:" + p.med) +
        qbtn("🍎", "Питание", "food") + qbtn("🩸", "Железо", "iron") +
      '</div>';
  }
  function qbtn(e, t, nav) { return '<button data-nav="' + nav + '"><span class="qe">' + e + '</span>' + t + '</button>'; }

  function screenCare() {
    return head("Забота") +
      '<p class="section-label">Выбери, что тебе сейчас нужно</p>' +
      '<div class="hub">' +
        hub("🍎", "Питание", "по фазе", "food") +
        hub("🩸", "Железо", "не терять железо", "iron") +
        hub("💗", "Аффирмации", "на сегодня", "aff") +
        hub("🧘", "Медитации", "короткие практики", "medlist") +
        hub("🎬", "Фильмы", "что посмотреть", "movies") +
        hub("🌸", "Тело и близость", "понимать себя", "body") +
        '<button class="sos" data-nav="crisis"><span class="he">🆘</span><span class="ht">Срочная помощь</span><span class="hd">если очень тяжело — ты не одна</span></button>' +
      '</div>';
  }
  function hub(e, t, d, nav) { return '<button data-nav="' + nav + '"><span class="he">' + e + '</span><span class="ht">' + t + '</span><span class="hd">' + d + '</span></button>'; }

  function screenBody() {
    function card(h, body) { return '<div class="card"><h3>' + h + '</h3>' + body + '</div>'; }
    return head("Тело и близость", "back") +
      '<div class="card insight"><h3>Это — про тебя, не про секс</h3><p>Здесь нет ответа на вопрос «когда тебе можно близость». Это только для того, чтобы ты лучше понимала своё тело и могла дать себе то, что тебе нужно. Желание у каждой женщины своё: оно может быть, а может и не быть — и это нормально. С тобой всё в порядке в любом случае.</p></div>' +
      card("🌗 Тело меняется по фазам", '<p>Это гормоны, а не «правильно» или «неправильно». Всё индивидуально, у тебя может быть иначе:</p>' +
        '<p>• После месячных и ближе к овуляции у многих чувствительность выше — возбуждение может приходить быстрее, ощущения ярче.</p>' +
        '<p>• В самый пик овуляции, когда выходит яйцеклетка, бывает наоборот: тянущая или резкая боль, спазмы, слизистые выделения. Тогда близость может быть неприятна — и воздержаться совершенно нормально.</p>' +
        '<p>• В другие фазы желания может быть меньше. Это тоже норма — перестраивается вся гормональная система.</p>') +
      '<div class="card redflag"><h3>💗 Твои границы важнее всего</h3><p>Ты никому ничего не должна. Не соглашайся на близость через боль или «потому что партнёр хочет». Если тело говорит «нет» — это «нет», и этого достаточно.</p><p>Когда женщина терпит и делает через силу, страдает и тело, и нервная система: остаётся чувство, что тебя использовали. Когда ты слушаешь сигналы своего тела — тебе физически и душевно лучше. Ты — человек, а не объект.</p></div>' +
      card("🕯️ Если ты сама хочешь близости", '<p>Возбуждение почти всегда нужно «разогреть»: прелюдия важна практически всегда, мгновенная готовность бывает редко — и это нормально.</p>' +
        '<p>В фазы, когда влечение и так выше (после месячных, к овуляции), прелюдия может быть короче. Когда желания меньше — дай себе больше времени и нежности: так сохраняется чувствительность, и близость приносит радость, а не разочарование.</p>') +
      card("🤰 Зачатие и защита", '<p>В конце фолликулярной фазы и в начале овуляции при незащищённой близости можно забеременеть.</p>' +
        '<p>• Планируешь ребёнка — это как раз подходящие дни.</p>' +
        '<p>• Беременность не в планах — в эти дни особенно важно защищаться, и лучше надёжным способом. Прерванный акт ненадёжен и рискован, полагаться на него нельзя. Метод подбери с врачом.</p>') +
      '<p class="caption">Это часть заботы о себе, а не инструкция. Всё индивидуально; при вопросах о здоровье — к врачу.</p>';
  }

  function screenAssistant() {
    var msgs = chatLog.map(function (m) { return '<div class="msg ' + m.who + '">' + esc(m.text) + '</div>'; }).join("");
    var sug = ["Почему я устаю перед месячными?", "Когда фертильные дни?", "Что есть для железа?"].map(function (q) { return '<button data-ask="' + esc(q) + '">' + esc(q) + '</button>'; }).join("");
    var quotaOut = chatLog.some(function (m) { return m.quota; });
    var badge, cap;
    if (serverOn()) {
      var st = state.ai.status, left = st ? serverRemaining(st) : null;
      if (quotaOut) { badge = '<span class="pill" data-nav="paywall" style="cursor:pointer;background:#fdecec;color:#b3261e">🔴 Лимит исчерпан · тарифы →</span>'; }
      else { badge = '<span class="pill" data-nav="paywall" style="cursor:pointer">🟢 Умный ИИ' + (left != null ? " · осталось " + left : "") + ' →</span>'; }
      cap = "Умный режим: ответы формирует нейросеть. Лимит и оплата — на вкладке «Тарифы». Не заменяет врача.";
    } else if (byokOn()) {
      badge = '<span class="pill" data-nav="settings" style="cursor:pointer">🟢 Умный ИИ (свой ключ) →</span>';
      cap = "Умный режим на твоём ключе. Не заменяет врача.";
    } else {
      badge = '<span class="pill" data-nav="settings" style="cursor:pointer">⚪ Офлайн-режим · включить умный ИИ →</span>';
      cap = "Офлайн-режим на устройстве. Не заменяет врача. Умный ИИ включается в Настройках.";
    }
    return head("Ассистент") + '<div style="margin-bottom:10px">' + badge + '</div>' +
      '<div class="chat" id="chat">' + msgs + '</div>' +
      '<div class="suggest">' + sug + '</div>' +
      '<div class="chat-input">' + micBtn("chat-input") + '<input id="chat-input" type="text" placeholder="Напиши или скажи…" aria-label="Вопрос" /><button class="send" data-act="send" title="Отправить">↑</button></div>' +
      '<p class="caption">' + cap + '</p>';
  }

  function screenPartner() {
    var ci = cycleInfo(), p = PHASES[ci.phase], sig = SIGNAL[state.intimacy.value] || SIGNAL.yellow;
    var intimClass = ci.phase === "menstrual" ? " redflag" : "";
    return head("Для партнёра") +
      '<div class="phase-banner" style="background:linear-gradient(135deg,' + p.color + ', color-mix(in srgb,' + p.color + ' 62%, #000))"><div class="pb-emoji">' + p.emoji + '</div><h2>Она в фазе: ' + p.name + '</h2><div class="pb-line">' + p.partner + '</div></div>' +
      '<div class="card' + intimClass + '"><h3>💞 Про близость сейчас</h3><p>' + p.intim + '</p></div>' +
      '<div class="card signal-card"><div class="signal-badge">' + sig.em + '</div><div><h3 style="margin-bottom:2px">Её сигнал: ' + sig.title + '</h3><p>' + sig.text + '</p></div></div>' +
      '<div class="card insight"><h3>❤️ Главное</h3><p>Это приложение не о том, как получить секс, а о том, чтобы понимать её. Заботься и проявляй нежность не только когда хочешь близости — а просто потому, что любишь.</p></div>' +
      courseCard() +
      '<p class="caption">Партнёр видит только то, чем она поделилась.</p>';
  }
  function courseCard() {
    var done = state.course.length, total = COURSE.length, pct = Math.round(done / total * 100);
    var next = COURSE.findIndex(function (l) { return state.course.indexOf(l.id) === -1; });
    var label = done === 0 ? "Начать курс" : (next === -1 ? "Пройти заново" : "Продолжить");
    return '<div class="card"><h3>🎓 Мини-курс для партнёра</h3><p>Пройдено ' + done + ' из ' + total + '. Читай любой урок — по выбору.</p>' +
      '<div class="bar-track" style="margin:8px 0"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
      '<button class="btn ghost sm" data-nav="course">' + label + '</button></div>';
  }

  /* ---------- overlay screens ---------- */
  function screenCheckin() {
    var today = isoToday(), e = state.diary[today] || {}, cur = e.mood;
    var moods = MOODS.map(function (m) { return '<button class="mood' + (cur === m[0] ? " sel" : "") + '" data-mood="' + m[0] + '">' + m[1] + '</button>'; }).join("");
    var support = NEG[cur] ? '<div class="support-nudge" data-nav="crisis" style="margin-top:6px">💗 Хочешь поддержки прямо сейчас? →</div>' +
      '<div class="row" style="gap:8px;margin-bottom:12px"><button class="btn ghost sm" data-nav="aff">Аффирмация</button><button class="btn ghost sm" data-nav="med:selfcompassion">Медитация</button></div>' : "";
    return head("Как ты?", "back") +
      '<div class="row" style="margin-bottom:14px;flex-wrap:wrap;gap:8px">' + moods + '</div>' + support +
      '<p class="section-label">Хочешь рассказать? Можно голосом 🎤</p>' +
      '<div class="note-wrap"><textarea id="note" placeholder="Пара слов о себе…">' + esc(e.note || "") + '</textarea>' + micBtn("note") + '</div>' +
      '<p class="section-label" style="margin-top:14px">Близость сегодня — решаешь только ты</p>' +
      '<div class="seg" data-seg="1">' + ["green", "yellow", "red"].map(function (v) { return '<button class="' + (state.intimacy.value === v ? "sel" : "") + '" data-v="' + v + '"><span class="lt">' + SIGNAL[v].em + '</span>' + SIGNAL[v].title.replace(/[«»]/g, "") + '</button>'; }).join("") + '</div>' +
      '<p class="caption" style="text-align:left">Партнёр увидит только сигнал — без дат и симптомов.</p>' +
      '<button class="btn" data-act="save-checkin">Сохранить</button>';
  }

  function screenPhases() {
    var ci = cycleInfo();
    var items = ORDER.map(function (k) {
      var p = PHASES[k], now = k === ci.phase;
      return '<div class="phase-item' + (now ? " now" : "") + '"><div class="phase-emoji-box" style="background:' + p.color + ';color:#fff">' + p.emoji + '</div>' +
        '<div><h4>' + p.name + (now ? " · сейчас" : "") + '</h4><span class="days">' + p.short + '</span><p>' + p.feel + '</p></div></div>';
    }).join("");
    return head("Все фазы", "back") + phase4(ci.phase) + items + '<p class="caption">Каждая женщина индивидуальна.</p>';
  }

  function screenFood() {
    var p = PHASES[cycleInfo().phase];
    return head("Питание", "back") +
      '<div class="phase-banner" style="padding:14px;background:linear-gradient(135deg,' + p.color + ', color-mix(in srgb,' + p.color + ' 62%, #000))"><div class="pb-line" style="margin:0">' + p.emoji + " " + p.name + ' — что поддержит тебя:</div></div>' +
      '<ul class="tlist">' + p.food.map(function (f) { return '<li><span class="ic">•</span>' + f + '</li>'; }).join("") + '</ul>' +
      '<button class="btn ghost sm" data-nav="iron">Как не терять железо 🩸</button>';
  }
  function screenIron() {
    return head("Железо", "back") +
      '<p class="section-label">Что есть, чтобы не терять железо</p>' +
      '<ul class="tlist">' + IRON.eat.map(function (f) { return '<li><span class="ic">•</span>' + f + '</li>'; }).join("") + '</ul>' +
      '<div class="card insight"><h3>➕ Усилить усвоение</h3><p>' + IRON.boost + '</p></div>' +
      '<div class="card"><h3>➖ Мешает усвоению</h3><p>' + IRON.avoid + '</p></div>' +
      '<p class="caption">При сильной слабости сдай анализ на железо/ферритин — обсуди с врачом.</p>';
  }
  function screenAff() {
    var p = PHASES[cycleInfo().phase], list = p.aff, q = list[affIdx % list.length];
    return head("Аффирмация", "back") +
      '<div class="aff" style="background:linear-gradient(135deg,' + p.color + ', color-mix(in srgb,' + p.color + ' 62%, #000))"><div class="quote">«' + q + '»</div></div>' +
      '<button class="btn" data-act="aff-next">Другая аффирмация</button>' +
      '<p class="caption">Повтори про себя несколько раз, медленно.</p>';
  }
  function screenMedList() {
    return head("Медитации", "back") +
      MED_LIST.map(function (id) { var m = MED[id]; return '<div class="phase-item" data-nav="med:' + id + '" style="cursor:pointer"><div class="phase-emoji-box" style="background:var(--brand-soft);color:var(--brand)">🧘</div><div><h4>' + m.title + '</h4><span class="days">' + m.mins + ' мин · ' + m.note + '</span></div></div>'; }).join("") +
      '<p class="caption">Короткие практики. Найди тихое место и следуй шагам.</p>';
  }
  function screenMed(id) {
    var m = MED[id]; if (!m) return screenMedList();
    return head(m.title, "back") +
      '<div class="breath-wrap"><div class="breath">дыши</div><span class="caption" style="margin:0">Пусть круг задаёт ритм дыхания</span></div>' +
      '<ol class="steps">' + m.steps.map(function (s) { return '<li>' + s + '</li>'; }).join("") + '</ol>' +
      '<button class="btn" data-nav="__back" style="margin-top:14px">Готово</button>';
  }
  function screenMovies() {
    return head("Фильмы", "back") +
      '<p class="section-label">Тёплое и поддерживающее</p>' +
      '<ul class="tlist">' + MOVIES.map(function (m) { return '<li class="movie"><span class="ic">🎬</span><span><span class="mt">' + esc(m[0]) + '</span><br><span class="mw">' + esc(m[1]) + '</span></span></li>'; }).join("") + '</ul>';
  }
  function screenCrisis() {
    return head("Срочная помощь", "back") +
      '<div class="crisis-hero"><h2>Ты не одна 💗</h2><p>То, что ты чувствуешь сейчас, — реально и тяжело. Но это состояние пройдёт. Ты важна, даже когда так не кажется.</p></div>' +
      '<a class="call sos-call" href="tel:112"><span class="ce">🚨</span><span><span class="cn">112</span><br><span class="cl">Экстренно, если есть угроза жизни</span></span></a>' +
      '<a class="call" href="tel:88002000122"><span class="ce">📞</span><span><span class="cn">8-800-2000-122</span><br><span class="cl">Психологическая помощь · бесплатно, анонимно, круглосуточно</span></span></a>' +
      '<div class="card"><h3>Прямо сейчас</h3><p>Позвони тому, кому доверяешь, и скажи как есть. Просить о помощи — это сила, а не слабость.</p></div>' +
      '<button class="btn" data-nav="med:ground">Успокоиться: заземление 5-4-3-2-1</button>' +
      '<button class="btn ghost" data-nav="aff" style="margin-top:8px">Тёплые слова себе</button>' +
      '<p class="caption">Если есть мысли причинить себе вред — обратись за помощью немедленно (112 или к близкому). Номера линий доверия различаются по странам — поищи местную, если ты не в России.</p>';
  }

  function screenSettings() {
    return head("Настройки", "back") +
      '<div class="field"><label>Как к тебе обращаться</label><input type="text" id="s-name" value="' + esc(state.partnerName) + '" /></div>' +
      '<div class="field"><label>Начало последней менструации</label><input type="date" id="s-last" value="' + state.lastPeriod + '" /></div>' +
      '<div class="field"><label>Длина цикла: <span id="s-lenv">' + state.cycleLength + '</span> дн.</label><div class="stepper"><button data-step="len:-1">−</button><span class="val" id="s-len">' + state.cycleLength + '</span><button data-step="len:1">+</button></div></div>' +
      '<div class="field"><label>Длительность менструации: <span id="s-perv">' + state.periodLength + '</span> дн.</label><div class="stepper"><button data-step="per:-1">−</button><span class="val" id="s-per">' + state.periodLength + '</span><button data-step="per:1">+</button></div></div>' +
      '<p class="section-label" style="margin-top:10px">🤖 Умный ИИ-ассистент</p>' +
      '<div class="field"><label>Режим</label><select id="s-ai-mode">' +
        '<option value="server"' + (state.ai.mode === "server" ? " selected" : "") + '>Через сервис (подписка/кредиты)</option>' +
        '<option value="byok"' + (state.ai.mode === "byok" ? " selected" : "") + '>Свой ключ (для разработчика)</option>' +
        '<option value="off"' + (state.ai.mode === "off" ? " selected" : "") + '>Выключить (офлайн)</option>' +
      '</select></div>' +
      '<div class="field"><label>Адрес сервера' + (API_BASE ? " (по умолчанию задан)" : "") + '</label><input type="text" id="s-ai-server" value="' + esc(state.ai.server || "") + '" placeholder="' + (API_BASE || "https://api.твойдомен.ru") + '" autocomplete="off" /></div>' +
      (serverOn() ? '<button class="btn ghost" data-nav="paywall" style="margin-bottom:10px">💳 Тарифы и оплата</button>' : "") +
      '<details style="margin:0 2px 10px"><summary class="caption" style="cursor:pointer">Свой ключ (расширенный режим)</summary>' +
      '<div class="field" style="margin-top:8px"><label>Провайдер</label><select id="s-ai-provider"><option value="claude"' + (state.ai.provider === "claude" ? " selected" : "") + '>Claude (Anthropic)</option><option value="openai"' + (state.ai.provider === "openai" ? " selected" : "") + '>OpenAI</option></select></div>' +
      '<div class="field"><label>API-ключ (хранится только на устройстве)</label><input type="password" id="s-ai-key" value="' + esc(state.ai.key || "") + '" placeholder="sk-..." autocomplete="off" /></div>' +
      '<div class="field"><label>Модель</label><input type="text" id="s-ai-model" value="' + esc(state.ai.model || "") + '" placeholder="claude-sonnet-5" /></div>' +
      '<p class="caption" style="text-align:left;margin:0">Claude: claude-sonnet-5 · claude-opus-5 · claude-haiku-4-5. OpenAI: gpt-4o-mini · gpt-4o.</p></details>' +
      '<button class="btn" data-act="save-settings">Сохранить</button>' +
      '<div class="card insight" style="margin-top:12px"><h3>Как работает умный режим</h3><p><b>Через сервис</b> — умный ИИ работает по подписке или пакетам сообщений, оплата в приложении. <b>Свой ключ</b> — для разработчика: ответы идут напрямую в нейросеть по твоему ключу. Текст вопросов уходит на сервер ИИ — включай по желанию. Без обоих — офлайн-режим на устройстве.</p></div>' +
      '<div class="card insight"><h3>🔒 Приватность</h3><p>Данные цикла хранятся только на этом устройстве. Без сервера и рекламы.</p></div>' +
      '<button class="btn danger" data-act="wipe">Удалить все мои данные</button>' +
      '<p class="caption">Версия 2.6 · MVP-демо. Прогнозы — ориентир, не медицинская рекомендация.</p>';
  }

  function screenPaywall() {
    if (!serverOn()) {
      return head("Тарифы", "back") +
        '<div class="card insight"><h3>Умный ИИ через сервис не подключён</h3><p>Оплата и лимиты работают, когда указан адрес сервера. Открой Настройки → «Умный ИИ» и выбери режим «Через сервис».</p></div>' +
        '<button class="btn" data-nav="settings">Открыть настройки</button>';
    }
    var cur = "cur", pay = state.ai.payProvider || "yookassa";
    var provSel = '<div class="field"><label>Способ оплаты</label><select id="pay-prov">' +
      ['yookassa|ЮKassa (карты РФ, СБП)', 'stripe|Банковская карта (мир)', 'telegram|Telegram'].map(function (o) {
        var p = o.split("|"); return '<option value="' + p[0] + '"' + (pay === p[0] ? " selected" : "") + '>' + p[1] + '</option>';
      }).join("") + '</select></div>';

    function money(v, c) { return v + " " + (c === "RUB" || !c ? "₽" : c); }
    var body = head("Тарифы", "back");
    var st = state.ai.status;
    if (st) {
      cur = st.currency || (st.plan && st.plan.currency) || "RUB";
      var subLine = (st.sub && st.sub.active)
        ? ("✅ Подписка активна: осталось " + (st.sub.remaining != null ? st.sub.remaining : (st.sub.cap - st.sub.used)) + " из " + st.sub.cap + " сообщений.")
        : "Подписка не активна.";
      var freeLine = st.free ? ("Бесплатно сегодня: " + st.free.remaining + " из " + st.free.limit + ".") : "";
      body += '<div class="card insight"><h3>Твой доступ</h3><p>' + subLine + '<br>💳 Кредиты (сообщения): <b>' + (st.credits || 0) + '</b>.' + (freeLine ? "<br>" + freeLine : "") + '</p></div>';
    } else {
      body += '<div class="card"><p class="caption" style="text-align:left">Загружаю статус…</p></div>';
    }
    body += provSel;

    var plan = st && st.plan;
    if (plan) {
      body += '<div class="phase-item"><div class="phase-emoji-box" style="background:var(--brand-soft);color:var(--brand)">★</div>' +
        '<div style="flex:1"><h4>Подписка · ' + money(plan.price, plan.currency || cur) + '</h4>' +
        '<span class="days">' + plan.cap + ' сообщений на ' + plan.days + ' дн.</span></div>' +
        '<button class="btn" style="width:auto;padding:8px 14px" data-act="buy-sub">Оформить</button></div>';
    }
    var packs = st && st.packs;
    if (packs && packs.length) {
      body += '<p class="section-label" style="margin-top:12px">Пакеты сообщений (не сгорают)</p>';
      body += packs.map(function (p) {
        return '<div class="phase-item"><div class="phase-emoji-box" style="background:var(--brand-soft);color:var(--brand)">💬</div>' +
          '<div style="flex:1"><h4>' + p.credits + ' сообщений</h4><span class="days">' + money(p.price, cur) + '</span></div>' +
          '<button class="btn" style="width:auto;padding:8px 14px" data-act="buy-pack" data-pack="' + esc(p.id) + '">Купить</button></div>';
      }).join("");
    }
    body += '<p class="caption">Оплата откроется в защищённом окне провайдера. После оплаты вернись в приложение — доступ обновится.</p>';
    return body;
  }

  function screenCourseList() {
    var items = COURSE.map(function (l, i) {
      var done = state.course.indexOf(l.id) !== -1;
      return '<div class="phase-item" data-nav="lesson:' + i + '" style="cursor:pointer"><div class="phase-emoji-box" style="background:var(--brand-soft);color:var(--brand)">' + (done ? "✓" : (i + 1)) + '</div><div><h4>' + esc(l.title) + '</h4><span class="days">' + l.mins + ' мин' + (done ? " · пройдено" : "") + '</span></div></div>';
    }).join("");
    return head("Мини-курс", "back") + '<p class="section-label">Читай любой урок — по выбору. Пройдено ' + state.course.length + '/' + COURSE.length + '</p>' + items;
  }
  function screenLesson(i) {
    var l = COURSE[i]; if (!l) return screenCourseList();
    var done = state.course.indexOf(l.id) !== -1;
    return head("Урок " + (i + 1) + " из " + COURSE.length, "back") +
      '<h3 style="font-family:var(--serif);font-size:19px;margin:2px 0 12px">' + esc(l.title) + '</h3>' +
      l.body.map(function (t) { return '<p style="margin:0 0 12px;font-size:14px">' + t + '</p>'; }).join("") +
      '<button class="btn" data-act="course-done" data-idx="' + i + '">' + (done ? "Готово" : "Пройдено ✓") + '</button>';
  }

  /* ---------- onboarding ---------- */
  var obStep = 1, obRole = state.role;
  function renderOnboarding() {
    var dots = [1, 2, 3].map(function (n) { return '<i class="' + (n <= obStep ? "on" : "") + '"></i>'; }).join(""), body;
    if (obStep === 1) body = '<h3>Кто вы?</h3><p class="sub">Настроим приложение под вас.</p><div class="choice">' +
      '<button class="choice-card' + (obRole === "woman" ? " sel" : "") + '" data-role="woman"><span class="em">👩</span><span><span class="t">Я веду свой цикл</span><br><span class="d">Забота, самочувствие, приватность</span></span></button>' +
      '<button class="choice-card' + (obRole === "partner" ? " sel" : "") + '" data-role="partner"><span class="em">🧑</span><span><span class="t">Я поддерживаю партнёршу</span><br><span class="d">Подсказки, как быть рядом</span></span></button>' +
      '</div><div class="foot"><button class="btn" data-act="ob-next">Продолжить</button></div>';
    else if (obStep === 2) body = '<h3>Пара деталей</h3><p class="sub">Только для прогноза. Данные приватны.</p>' +
      '<div class="field"><label>Начало последней менструации</label><input type="date" id="ob-last" value="' + state.lastPeriod + '" /></div>' +
      '<div class="field"><label>Длина цикла: <span>' + state.cycleLength + '</span> дн.</label><div class="stepper"><button data-step="oblen:-1">−</button><span class="val">' + state.cycleLength + '</span><button data-step="oblen:1">+</button></div></div>' +
      '<div class="foot"><button class="btn" data-act="ob-next">Продолжить</button></div>';
    else body = '<h3>Готово!</h3><p class="sub">Всё просто: на «Сегодня» — твоя фаза и вопрос «как ты?», в «Заботе» — питание, аффирмации, медитации и поддержка.</p>' +
      '<div class="foot"><button class="btn" data-act="ob-finish">Начать</button></div>';
    app.innerHTML = '<div class="ob"><div class="brand"><div class="k">Добро пожаловать</div><h2>Цикл вдвоём</h2></div><div class="dots">' + dots + '</div>' + body + '</div>';
  }

  /* ---------- router ---------- */
  var overlay = null, navStack = [];
  function navGo(r) {
    if (r === "__back") { overlay = navStack.length ? navStack.pop() : null; return render(); }
    navStack.push(overlay); overlay = r; render();
    if (r === "paywall" && serverOn()) { ensureAccount().then(refreshMe).then(function (d) { if (d && overlay === "paywall") render(); }).catch(function () {}); }
  }
  var chatLog = [{ who: "bot", text: "Привет! Спроси про самочувствие, цикл или питание 💛" }];
  var affIdx = 0;

  function overlayScreen(r) {
    if (r === "settings") return screenSettings();
    if (r === "checkin") return screenCheckin();
    if (r === "phases") return screenPhases();
    if (r === "food") return screenFood();
    if (r === "iron") return screenIron();
    if (r === "aff") return screenAff();
    if (r === "medlist") return screenMedList();
    if (r === "movies") return screenMovies();
    if (r === "crisis") return screenCrisis();
    if (r === "body") return screenBody();
    if (r === "course") return screenCourseList();
    if (r === "paywall") return screenPaywall();
    if (r.indexOf("med:") === 0) return screenMed(r.slice(4));
    if (r.indexOf("lesson:") === 0) return screenLesson(+r.slice(7));
    return screenToday();
  }
  function tabScreen() {
    if (state.role === "partner") return ({ partner: screenPartner, phases: screenPhases, ai: screenAssistant }[state.tab] || screenPartner)();
    return ({ today: screenToday, care: screenCare, ai: screenAssistant, partner: screenPartner }[state.tab] || screenToday)();
  }
  function render() {
    if (!state.onboarded) return renderOnboarding();
    var body = overlay ? overlayScreen(overlay) : tabScreen();
    app.innerHTML = '<div class="view" id="view">' + body + '</div>' + (overlay ? "" : tabbar());
    if (!overlay && state.tab === "ai") { var c = document.getElementById("chat"); if (c) c.scrollTop = c.scrollHeight; }
  }
  function tabbar() {
    var tabs = state.role === "partner"
      ? [["partner", "Партнёр", iHeart], ["phases", "Фазы", iCycle], ["ai", "Ассистент", iChat]]
      : [["today", "Сегодня", iSun], ["care", "Забота", iCare], ["ai", "Ассистент", iChat], ["partner", "Партнёр", iHeart]];
    return '<div class="tabbar">' + tabs.map(function (t) { return '<button class="tab' + (state.tab === t[0] ? " sel" : "") + '" data-tab="' + t[0] + '">' + t[2] + '<span>' + t[1] + '</span></button>'; }).join("") + '</div>';
  }
  var iSun = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/></svg>';
  var iCare = '<svg viewBox="0 0 24 24"><path d="M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 11c0 5.5-7 10-7 10z"/><path d="M12 8v4M10 10h4" stroke-width="1.4"/></svg>';
  var iChat = '<svg viewBox="0 0 24 24"><path d="M5 5h14v10H9l-4 4z"/><path d="M9 10h.01M12 10h.01M15 10h.01"/></svg>';
  var iHeart = '<svg viewBox="0 0 24 24"><path d="M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 11c0 5.5-7 10-7 10z"/></svg>';
  var iCycle = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18"/></svg>';

  /* ---------- events ---------- */
  app.addEventListener("click", function (e) {
    var t = e.target.closest("[data-tab],[data-nav],[data-act],[data-v],[data-mood],[data-role],[data-step],[data-ask],[data-voice]");
    if (!t) return;
    if (t.dataset.voice) { return startVoice(t.dataset.voice, t); }
    if (t.dataset.tab) { state.tab = t.dataset.tab; overlay = null; navStack = []; save(); return render(); }
    if (t.dataset.nav) { return navGo(t.dataset.nav); }
    if (t.dataset.role) { obRole = t.dataset.role; return renderOnboarding(); }
    if (t.dataset.step) { return handleStep(t.dataset.step); }
    if (t.dataset.v) { state.intimacy = { date: isoToday(), value: t.dataset.v }; save(); return render(); }
    if (t.dataset.mood) { setMood(t.dataset.mood); return render(); }
    if (t.dataset.ask) { return ask(t.dataset.ask); }
    var a = t.dataset.act;
    if (a === "ob-next") obNext();
    else if (a === "ob-finish") obFinish();
    else if (a === "save-checkin") saveCheckin(t);
    else if (a === "aff-next") { affIdx++; render(); }
    else if (a === "course-done") courseDone(+t.dataset.idx);
    else if (a === "send") sendChat();
    else if (a === "save-settings") saveSettings(t);
    else if (a === "buy-sub") startCheckout("sub", null);
    else if (a === "buy-pack") startCheckout("credits", t.dataset.pack);
    else if (a === "wipe") wipe();
  });
  app.addEventListener("change", function (e) {
    if (e.target.id === "pay-prov") { if (!state.ai) state.ai = {}; state.ai.payProvider = e.target.value; save(); }
  });
  app.addEventListener("keydown", function (e) { if (e.key === "Enter" && e.target.id === "chat-input") { e.preventDefault(); sendChat(); } });

  function handleStep(code) {
    var pt = code.split(":"), w = pt[0], d = +pt[1];
    if (w === "len") { state.cycleLength = clamp(state.cycleLength + d, 21, 40); byId("s-len").textContent = state.cycleLength; byId("s-lenv").textContent = state.cycleLength; }
    else if (w === "per") { state.periodLength = clamp(state.periodLength + d, 2, 10); byId("s-per").textContent = state.periodLength; byId("s-perv").textContent = state.periodLength; }
    else if (w === "oblen") { state.cycleLength = clamp(state.cycleLength + d, 21, 40); renderOnboarding(); }
  }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
  function byId(id) { return document.getElementById(id); }

  function setMood(m) { var d = isoToday(); if (!state.diary[d]) state.diary[d] = {}; state.diary[d].mood = (state.diary[d].mood === m ? null : m); state.lastMood = state.diary[d].mood; save(); }
  function saveCheckin(btn) { var d = isoToday(), n = byId("note"); if (!state.diary[d]) state.diary[d] = {}; if (n) state.diary[d].note = n.value.trim(); save(); flash(btn, "Сохранено ✓"); setTimeout(function () { navGo("__back"); }, 700); }

  function obNext() { if (obStep === 1) state.role = obRole; if (obStep === 2) { var d = byId("ob-last"); if (d && d.value) state.lastPeriod = d.value; } obStep = Math.min(3, obStep + 1); renderOnboarding(); }
  function obFinish() { state.role = obRole; var d = byId("ob-last"); if (d && d.value) state.lastPeriod = d.value; state.onboarded = true; state.tab = state.role === "partner" ? "partner" : "today"; save(); render(); }

  function courseDone(i) { var id = COURSE[i].id; if (state.course.indexOf(id) === -1) state.course.push(id); save(); overlay = (i < COURSE.length - 1) ? "lesson:" + (i + 1) : "course"; render(); }

  function ask(q) {
    chatLog.push({ who: "user", text: q });
    if (serverOn()) {
      var phs = { who: "bot", text: "…", pending: true }; chatLog.push(phs); render();
      ensureAccount().then(serverChat).then(function (r) {
        phs.text = r.text; phs.pending = false; if (r.status) state.ai.status = r.status; save(); render();
      }).catch(function (e) {
        phs.pending = false;
        if (e && e.quota) {
          if (e.status) state.ai.status = e.status; save();
          phs.text = "Лимит умного ИИ исчерпан. Оформи подписку или купи сообщения на вкладке «Тарифы» ниже — а пока отвечу из офлайн-базы:\n\n" + assistantAnswer(q);
          phs.quota = true; render();
        } else {
          phs.text = "Сервер недоступен (" + (e && e.message ? e.message : "ошибка") + "). Отвечу из офлайн-базы:\n\n" + assistantAnswer(q); render();
        }
      });
      return;
    }
    if (byokOn()) {
      var ph = { who: "bot", text: "…", pending: true }; chatLog.push(ph); render();
      callLLM().then(function (ans) { ph.text = ans; ph.pending = false; render(); })
               .catch(function (e) { ph.text = "Не получилось связаться с ИИ (" + (e && e.message ? e.message : "ошибка") + "). Проверь ключ в Настройках. Пока отвечу коротко: " + assistantAnswer(q); ph.pending = false; render(); });
      return;
    }
    chatLog.push({ who: "bot", text: assistantAnswer(q) }); render();
  }
  function sendChat() { var el = byId("chat-input"); if (!el) return; var v = el.value.trim(); if (!v) return; el.value = ""; ask(v); }

  function llmMessages() {
    return chatLog.filter(function (m) { return !m.pending; }).slice(1)
      .map(function (m) { return { role: m.who === "user" ? "user" : "assistant", content: m.text }; });
  }
  function llmContext() {
    var ci = cycleInfo();
    return "Контекст: пользователь — " + (state.role === "partner" ? "партнёр" : "женщина") +
      ". Фаза цикла сейчас: " + PHASES[ci.phase].name + ", день " + ci.day + " из " + ci.len + "." +
      ((state.lastMood) ? " Отмеченное настроение: " + state.lastMood + "." : "");
  }
  function callLLM() {
    var ai = state.ai, msgs = llmMessages();
    while (msgs.length && msgs[0].role !== "user") msgs.shift();
    return (ai.provider === "openai") ? callOpenAI(msgs) : callAnthropic(msgs);
  }
  function callAnthropic(msgs) {
    return fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": state.ai.key,
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true"
      },
      body: JSON.stringify({
        model: state.ai.model || "claude-sonnet-5",
        max_tokens: 700,
        system: SYSTEM_PROMPT + "\n\n" + llmContext(),
        messages: msgs
      })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.error) throw new Error(d.error.message || d.error.type || "API error");
      var block = d && d.content && d.content.find ? d.content.find(function (b) { return b.type === "text"; }) : (d.content && d.content[0]);
      return (block && block.text) || "…";
    });
  }
  function callOpenAI(msgs) {
    var m = [{ role: "system", content: SYSTEM_PROMPT + "\n\n" + llmContext() }].concat(msgs);
    return fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { "content-type": "application/json", "authorization": "Bearer " + state.ai.key },
      body: JSON.stringify({ model: state.ai.model || "gpt-4o-mini", max_tokens: 700, messages: m })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.error) throw new Error(d.error.message || "API error");
      return (d.choices && d.choices[0] && d.choices[0].message && d.choices[0].message.content) || "…";
    });
  }

  function saveSettings(btn) {
    var n = byId("s-name"), l = byId("s-last"); if (n) state.partnerName = n.value.trim() || "Партнёр"; if (l && l.value) state.lastPeriod = l.value;
    if (!state.ai) state.ai = {};
    var mode = byId("s-ai-mode"), srv = byId("s-ai-server");
    if (mode) state.ai.mode = mode.value;
    if (srv) state.ai.server = srv.value.trim().replace(/\/+$/, "");
    var p = byId("s-ai-provider"), k = byId("s-ai-key"), md = byId("s-ai-model");
    if (p) state.ai.provider = p.value;
    if (k) state.ai.key = k.value.trim();
    if (md) state.ai.model = md.value.trim() || (state.ai.provider === "openai" ? "gpt-4o-mini" : "claude-sonnet-5");
    save(); flash(btn, "Сохранено ✓"); setTimeout(function () { navGo("__back"); }, 700);
  }
  function wipe() { if (!confirm("Удалить все данные с этого устройства? Необратимо.")) return; try { localStorage.removeItem(KEY); } catch (e) {} state = defaultState(); overlay = null; navStack = []; obStep = 1; obRole = "woman"; chatLog = chatLog.slice(0, 1); render(); }
  function flash(btn, text) { var o = btn.textContent; btn.textContent = text; btn.disabled = true; setTimeout(function () { btn.textContent = o; btn.disabled = false; }, 1000); }

  /* ---------- voice input ---------- */
  var rec = null;
  function startVoice(targetId, micEl) {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert("Голосовой ввод не поддерживается этим браузером."); return; }
    if (rec) { try { rec.stop(); } catch (e) {} rec = null; if (micEl) micEl.classList.remove("live"); return; }
    rec = new SR(); rec.lang = "ru-RU"; rec.interimResults = false; rec.maxAlternatives = 1;
    if (micEl) micEl.classList.add("live");
    rec.onresult = function (ev) { var txt = ev.results[0][0].transcript; var el = byId(targetId); if (el) { el.value = (el.value ? el.value + " " : "") + txt; el.focus(); } };
    rec.onerror = function () {};
    rec.onend = function () { if (micEl) micEl.classList.remove("live"); rec = null; };
    try { rec.start(); } catch (e) { if (micEl) micEl.classList.remove("live"); rec = null; }
  }

  /* ---------- boot ---------- */
  render();
  /* PWA: регистрируем сервис-воркер для установки и офлайн-работы. */
  if ("serviceWorker" in navigator) window.addEventListener("load", function(){ navigator.serviceWorker.register("sw.js").catch(function(){}); });
})();
