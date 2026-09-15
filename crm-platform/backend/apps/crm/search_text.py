"""Розумний пошук по CRM — ОДИН розбір рядка для пошуку в «Чатах» і глобального пошуку в шапці.

15.09.2026 (chatsearch). Олег: «за іменем не знаходжу і за нікнеймом теж не шукає».
Було: кожне поле порівнювалось з УСІМ рядком цілком → «Івана Забурко» (імʼя + прізвище разом) не
знаходило нічого; «@нік», інший апостроф (' ʼ ’), латиниця (Ivana), телефон з пробілами/дужками — теж ні;
глобальний пошук взагалі не дивився нік і посилання на профіль.

Правила (однакові всюди):
- кілька слів → КОЖНЕ слово має знайтись хоч в одному полі, порядок будь-який («Забурко Івана»);
- регістр не важливий (lower() у базі en_US.utf8 і в Python — кирилиця працює);
- апострофи ' ʼ ’ ` ´ ‘ вважаються однаковими;
- «@нік», «#123», посилання на профіль (https://instagram.com/нік?igsh=…) → шукаємо сам нік / число;
- латиниця ↔ кирилиця: Ivana → Івана / Ивана, Забурко → zaburko (прості варіанти транслітерації);
- телефон у будь-якому вигляді (+380…, 0XX…, пробіли, дужки, дефіси) — порівнюємо лише ЦИФРИ
  і в запиті, і в базі: «+38 (063) 868-22-04» знайде «+380638682204» і навпаки;
- число → ще й № угоди / ліда / чату / клієнта.

Швидкодія: на кожне слово — ОДИН прохід `lower(concat_ws(' ', поля…)) LIKE ANY(ARRAY[варіанти])`
замість окремого icontains на кожне поле × кожен варіант (заміри на проді 15.09: однакові результати,
у 1,2–2,8 раза швидше). Без нових індексів і розширень (unaccent / pg_trgm у базі немає), лише Postgres.
"""
import re
from typing import List, Optional

from django.db.models import BooleanField, CharField, F, Func, Q, TextField, Value
from django.db.models.functions import Cast
from django.db.models.lookups import Contains

APOSTROPHES = "'ʼ’`´‘"
_APOS_VARIANTS = ("'", "ʼ", "’", "`")     # як реально записано в базі (326 / 25 / 6 / 6 контактів)
_APOS_RE = re.compile("[" + re.escape(APOSTROPHES) + "]")
_PHONE_LIKE_RE = re.compile(r"^\+?[\d\s().\-]+$")
_URL_RE = re.compile(r"^(https?://|www\.)|^[\w.-]+\.(com|me|ua|net|org)/", re.I)
_EDGE = " \t.,;:!?()[]{}<>\"«»|/\\-–—'"
_LAT_WORD = re.compile(r"^[a-z']{3,}$")
_CYR_WORD = re.compile(r"^[а-яіїєґё']{3,}$")
MAX_TERMS = 6
MAX_TERM_LEN = 64
MIN_PHONE_DIGITS = 5

# Поля контакту — ті самі в чатах, клієнтах, угодах і лідах.
CONTACT_TEXT_FIELDS = ("first_name", "last_name", "middle_name", "nickname", "social_link", "email")
CONTACT_JSON_FIELDS = ("messengers", "emails_extra", "links_extra")   # JSON-списки посилань / пошт
CONTACT_PHONE_FIELDS = ("phone",)
CONTACT_JSON_PHONE_FIELDS = ("phones_extra",)

# ── транслітерація (спрощена, кілька варіантів — люди пишуть по-різному) ──
_COMMON_DI = [("shch", "щ"), ("zh", "ж"), ("kh", "х"), ("ch", "ч"), ("sh", "ш"), ("ts", "ц"), ("ya", "я"), ("yu", "ю")]
_COMMON_1 = {"a": "а", "b": "б", "v": "в", "d": "д", "e": "е", "z": "з", "k": "к", "l": "л", "m": "м", "n": "н",
             "o": "о", "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф", "c": "ц", "w": "в", "q": "к",
             "j": "й", "x": "кс"}
_LAT2CYR = [
    (_COMMON_DI + [("ye", "є"), ("yi", "ї"), ("ia", "ія"), ("iu", "ію"), ("ie", "іє")],   # укр.: Daria → Дарія
     dict(_COMMON_1, i="і", y="и", h="г", g="г")),
    (_COMMON_DI + [("ye", "є"), ("yi", "ї"), ("ia", "я"), ("iu", "ю"), ("ie", "є")],      # укр.: Mariia → Марія
     dict(_COMMON_1, i="і", y="и", h="г", g="г")),
    (_COMMON_DI + [("ye", "е"), ("ia", "ия"), ("iu", "ию")],                              # рос.: Ivana → Ивана
     dict(_COMMON_1, i="и", y="й", h="х", g="г")),
]
_CYR_1 = {"а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ye", "ж": "zh", "з": "z",
          "и": "y", "і": "i", "ї": "yi", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
          "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
          "щ": "shch", "ь": "", "ю": "yu", "я": "ya", "ы": "y", "э": "e", "ё": "yo", "ъ": ""}
_CYR2LAT = [
    ([], _CYR_1),                                                                        # Любов → lyubov
    ([], dict(_CYR_1, г="g", и="i", є="ie", ї="i", й="i", х="h", ю="iu", я="ia")),       # Марія → mariia
]


def _translit(s: str, digraphs, singles) -> str:
    out, i = [], 0
    while i < len(s):
        for src, dst in digraphs:
            if s.startswith(src, i):
                out.append(dst)
                i += len(src)
                break
        else:
            out.append(singles.get(s[i], s[i]))
            i += 1
    return "".join(out)


def term_variants(term: str) -> List[str]:
    """Варіанти одного слова: сам він, інші апострофи, транслітерація латиниця↔кирилиця."""
    out = [term]
    if "'" in term:
        out = [term.replace("'", a) for a in _APOS_VARIANTS]
    low = term.lower()
    base = low.replace("'", "")
    if _LAT_WORD.match(low):
        out += [_translit(base, sorted(d, key=lambda x: -len(x[0])), s) for d, s in _LAT2CYR]
    elif _CYR_WORD.match(low):
        out += [_translit(base, d, s) for d, s in _CYR2LAT]
    seen, res = set(), []
    for v in out:
        k = v.lower()
        if v and k not in seen:
            seen.add(k)
            res.append(v)
    return res


def phone_core(d: str) -> str:
    """Цифри телефону без коду країни/нуля: 380671234567 / 80671234567 / 0671234567 → 671234567."""
    if len(d) >= 12 and d.startswith("380"):
        return d[3:]
    if len(d) == 11 and d.startswith("80"):
        return d[2:]
    if len(d) == 10 and d.startswith("0"):
        return d[1:]
    return d


class ParsedQuery:
    """terms — слова (кожне має знайтись); phone/digits — якщо весь рядок схожий на телефон."""
    __slots__ = ("terms", "phone", "digits")

    def __init__(self, terms, phone="", digits=""):
        self.terms, self.phone, self.digits = list(terms), phone, digits

    def __repr__(self):
        return "ParsedQuery(terms=%r, phone=%r, digits=%r)" % (self.terms, self.phone, self.digits)


def _clean_word(w: str) -> str:
    w = w.strip(_EDGE)
    if _URL_RE.search(w):  # посилання на профіль → останній шматок шляху (нік)
        path = w.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        seg = path.rsplit("/", 1)[-1] if "/" in path else ""
        if seg:
            w = seg
    return w.lstrip("@#").strip(_EDGE)


def parse_query(raw) -> Optional[ParsedQuery]:
    s = _APOS_RE.sub("'", str(raw or "")).strip()[:200]
    if not s:
        return None
    if _PHONE_LIKE_RE.match(s):
        d = re.sub(r"\D", "", s)
        if len(d) >= MIN_PHONE_DIGITS:
            return ParsedQuery([], phone_core(d), d)
    terms, seen = [], set()
    for w in s.split():
        w = _clean_word(w)[:MAX_TERM_LEN]
        if w and w.lower() not in seen:
            seen.add(w.lower())
            terms.append(w)
    longer = [t for t in terms if len(t) >= 2]
    if longer:  # ініціали («І. Забурко») не заважають
        terms = longer
    terms = terms[:MAX_TERMS]
    return ParsedQuery(terms) if terms else None


def digits_only(field_path: str):
    """SQL: лише цифри поля — regexp_replace(phone, '\\D', '', 'g')."""
    return Func(F(field_path), Value(r"\D"), Value(""), Value("g"),
                function="regexp_replace", output_field=CharField())


class _LikeAny(Func):
    """SQL: lower(<вираз>) LIKE ANY(ARRAY[шаблони]) — вираз (копиця полів) рахується ОДИН раз на рядок."""
    output_field = BooleanField()

    def __init__(self, expression, patterns):
        super().__init__(expression)
        self.patterns = list(patterns)

    def as_sql(self, compiler, connection, **extra_context):
        sql, params = compiler.compile(self.source_expressions[0])
        return "(lower(%s) LIKE ANY (%%s))" % sql, [*params, self.patterns]


def _haystack(text, json_text):
    parts = [F(f) for f in text] + [Cast(F(f), TextField()) for f in json_text]
    return Func(Value(" "), *parts, function="concat_ws", output_field=TextField())


def _like(v: str) -> str:
    return "%" + v.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def build_q(parsed, *, text=(), json_text=(), phones=(), json_phones=(), exact_ids=()):
    """Q для пошуку або None (порожній запит).
    text — CharField-и, json_text — JSON-списки: разом «копиця», де шукаємо кожне слово з усіма варіантами
    (регістр / апостроф / транслітерація); phones — телефонні CharField (порівнюємо лише цифри);
    json_phones — JSON-списки телефонів; exact_ids — числові id (угода / лід / чат / клієнт)."""
    if parsed is None:
        return None
    if parsed.phone:
        d, core = parsed.digits, parsed.phone
        q = Q(_LikeAny(_haystack(text, json_text), [_like(d)]))   # ТТН, ЄДРПОУ, нік із цифрами
        for f in phones:
            q |= Q(Contains(digits_only(f), core))
        for f in json_phones:
            q |= Q(**{f + "__icontains": core})
        if len(d) <= 9:
            for f in exact_ids:
                q |= Q(**{f: int(d)})
        return q
    q = Q()
    for term in parsed.terms:
        tq = Q(_LikeAny(_haystack(text, json_text), [_like(v) for v in term_variants(term)]))
        dig = re.sub(r"\D", "", term) if _PHONE_LIKE_RE.match(term) else ""
        if len(dig) >= 3:  # «Івана 067…» — цифрове слово шукаємо і в телефонах
            core = phone_core(dig)
            for f in phones:
                tq |= Q(Contains(digits_only(f), core))
            for f in json_phones:
                tq |= Q(**{f + "__icontains": core})
        if term.isdigit() and len(term) <= 9:
            for f in exact_ids:
                tq |= Q(**{f: int(term)})
        q &= tq
    return q


def _parsed(raw_or_parsed):
    return raw_or_parsed if isinstance(raw_or_parsed, ParsedQuery) else parse_query(raw_or_parsed)


def _with_contact(parsed, prefix, *, text=(), exact_ids=()):
    return build_q(parsed,
                   text=tuple(text) + tuple(prefix + f for f in CONTACT_TEXT_FIELDS),
                   json_text=tuple(prefix + f for f in CONTACT_JSON_FIELDS),
                   phones=tuple(prefix + f for f in CONTACT_PHONE_FIELDS),
                   json_phones=tuple(prefix + f for f in CONTACT_JSON_PHONE_FIELDS),
                   exact_ids=exact_ids)


def contact_search_q(raw_or_parsed):
    """Клієнт: імʼя/прізвище/по батькові, нік, посилання, email, телефони, ЄДРПОУ, № клієнта."""
    return _with_contact(_parsed(raw_or_parsed), "", text=("edrpou",), exact_ids=("id",))


def conversation_search_q(raw_or_parsed):
    """Чат: назва чату + усе про контакт + № чату + № угоди цього клієнта."""
    return _with_contact(_parsed(raw_or_parsed), "contact__", text=("title",),
                         exact_ids=("id", "contact__deals__id"))


def deal_search_q(raw_or_parsed):
    """Угода: назва, ID Бітрикса, ТТН, checkbox + усе про контакт + № угоди."""
    return _with_contact(_parsed(raw_or_parsed), "contact__",
                         text=("title", "b24_id", "ttn", "checkbox_relation_id"), exact_ids=("id",))


def lead_search_q(raw_or_parsed):
    """Лід: назва + усе про контакт + № ліда."""
    return _with_contact(_parsed(raw_or_parsed), "contact__", text=("title",), exact_ids=("id",))
