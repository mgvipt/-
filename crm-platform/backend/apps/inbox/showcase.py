"""Публічні сторінки-презентації матеріалів і кольорів з бібліотеки CRM (17.09.2026, Олег).

«Хочу, щоб ІІ не відправляв клієнтів у телеграм-бот, а слав посилання з нашої бази CRM: презентація
матеріалу з кольорами і фото інтерʼєрів, за потреби — відео обраного кольору.»

    /p/                      — усі матеріали
    /p/<матеріал>/           — кольори матеріалу (по одному образку на код) + сторінки каталогу
    /p/<матеріал>/<код>/     — колір: образок, інтерʼєри, відео

Сторінки публічні (клієнт відкриває з чату), без входу в CRM, з noindex. Показуємо лише активні файли
бібліотеки; самі байти віддає вже наявний публічний лінк /api/f/<token>/ (той самий, що менеджер шле в чат).
Нічого не пишемо в БД: лише читання.
"""
import json
import re
from html import escape
from urllib.parse import quote

from django.http import Http404, HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .models import MediaLibraryItem

PUBLIC_HOST = "https://wallcov.com.ua"          # той самий домен, що для /f/<код> (проксі на CRM)
MANAGER_PHONE = "380973282283"                  # той самий номер, що Юля дає клієнту (Viber / Telegram / WhatsApp)
MANAGER_TG = "https://t.me/wallcov_pidtrimka"
MANAGER_VIBER = "https://msng.link/o?380973282283=vi"
SECTION = "colors"
SWATCH_RE = re.compile(r"(каталог|зразок|sample)", re.I)

# Короткий опис матеріалу для клієнта (без вигадок — те саме, що в описах тест-наборів).
BLURB = {
    "Мокрий шовк": "Ефект «мокрого шовку»: стіна мʼяко переливається, як шовкова тканина, і змінює відтінок залежно від світла.",
    "Вельвет Луна": "Сатиново-шовковий перламутровий перелив: мʼяка глибока фактура, яка грає при денному й вечірньому світлі.",
    "Патера": "Фактурні покриття Pattera: травертин, матовий марморин і арт-бетон — фактура природного каменю й бетону.",
    "Песочки": "Перламутрові піщинки: делікатне сяйво, яке по-різному виглядає вдень і ввечері.",
    "Плінтуси Cezar": "Плінтуси та молдинги Cezar — моделі й розміри.",
    "Orac Decor": "Ліпнина Orac Decor: карнизи, молдинги, розетки, панелі.",
}
SLUG_MAP = {
    "мокрий шовк": "mokryi-shovk", "вельвет луна": "velvet-luna", "патера": "pattera",
    "песочки": "pisochky", "плінтуси cezar": "cezar", "orac decor": "orac",
}


def json_dumps(text):
    """Текст для JS-рядка (кнопка «Обрати цей колір» копіює його у буфер)."""
    return json.dumps(text, ensure_ascii=False)


def slug_of(material):
    low = (material or "").strip().lower()
    if low in SLUG_MAP:
        return SLUG_MAP[low]
    tr = {"а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie", "ж": "zh", "з": "z",
          "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
          "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
          "щ": "shch", "ь": "", "ю": "iu", "я": "ia", "ы": "y", "э": "e", "ё": "e", "ъ": ""}
    out = "".join(tr.get(ch, ch) for ch in low)
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    return out or "material"


def _items():
    return (MediaLibraryItem.objects.filter(is_active=True, section=SECTION)
            .select_related("file", "preview_file").defer("file__data", "preview_file__data"))


def materials():
    """Матеріали бібліотеки: назва, slug, скільки кольорів."""
    seen = {}
    for material, code in (MediaLibraryItem.objects.filter(is_active=True, section=SECTION)
                           .values_list("material", "color_code")):
        row = seen.setdefault(material or "Матеріал", {"name": material or "Матеріал", "codes": set()})
        if code:
            row["codes"].add(code)
    out = [{"name": r["name"], "slug": slug_of(r["name"]), "codes": len(r["codes"])} for r in seen.values()]
    return sorted(out, key=lambda r: (-r["codes"], r["name"]))


def material_by_slug(slug):
    for m in materials():
        if m["slug"] == slug:
            return m
    return None


def file_url(item):
    """Публічне посилання на файл — те саме, що бачить клієнт у чаті."""
    if item.public_url:
        return item.public_url
    if not item.file_id:
        return ""
    token = item.file.token
    return "%s/f/%s" % (PUBLIC_HOST, token[:12]) if len(token) >= 12 else "/api/f/%s/" % token


def is_swatch(item):
    return item.kind == "image" and bool(SWATCH_RE.search("%s %s" % (item.title, item.tags)))


def _page(title, body, subtitle="", back=None):
    """Проста мобільна сторінка: без входу, без індексації пошуком."""
    nav = ('<a class="back" href="%s">← %s</a>' % (escape(back[0]), escape(back[1]))) if back else ""
    return HttpResponse("""<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow">
<title>%s · Wallcov</title><style>
:root{--ink:#1b2230;--muted:#6b7686;--line:#e4e8ef;--bg:#fbfcfe;--brand:#2E6FB0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:16px 16px 56px}
h1{font-size:22px;margin:4px 0 6px;line-height:1.25}p.lead{color:var(--muted);margin:0 0 14px}
.back{display:inline-block;color:var(--brand);text-decoration:none;font-size:14px;margin-bottom:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.card{display:block;color:inherit;text-decoration:none;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card img{width:100%%;aspect-ratio:1/1;object-fit:cover;display:block;background:#eef2f7}
.card .t{padding:8px 10px;font-size:14px;font-weight:600}
.card .s{padding:0 10px 9px;font-size:12px;color:var(--muted)}
.big img,.big video{width:100%%;border-radius:12px;border:1px solid var(--line);display:block;background:#eef2f7}
.row{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:12px}
.note{background:#eef5fc;border-radius:10px;padding:10px 12px;font-size:14px;color:#1e3a5f;margin:14px 0}
.foot{color:var(--muted);font-size:13px;margin-top:28px;text-align:center}
.pick{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;margin:16px 0}
.pick b{font-size:16px}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.btn{display:inline-flex;align-items:center;gap:6px;border-radius:10px;padding:10px 14px;font-size:15px;font-weight:600;text-decoration:none;border:1px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}
.btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
.ok{color:#2F8F5B;font-size:14px;margin-top:8px;display:none}
</style></head><body><div class="wrap">%s<h1>%s</h1>%s%s
<div class="foot">Wallcov · декоративні покриття</div></div></body></html>""" % (
        escape(title), nav, escape(title),
        ('<p class="lead">%s</p>' % escape(subtitle)) if subtitle else "", body))


class ShowcaseIndexView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        cards = []
        for m in materials():
            first = _items().filter(material=m["name"]).order_by("sort", "id").first()
            img = file_url(first) if first else ""
            cards.append('<a class="card" href="/p/%s/">%s<div class="t">%s</div><div class="s">%d кольорів</div></a>' % (
                m["slug"], ('<img loading="lazy" src="%s" alt="">' % escape(img)) if img else "", escape(m["name"]), m["codes"]))
        return _page("Наші матеріали", '<div class="grid">%s</div>' % "".join(cards),
                     "Оберіть матеріал — усередині кольори, фото інтерʼєрів і відео.")


class ShowcaseMaterialView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug):
        m = material_by_slug(slug)
        if not m:
            raise Http404
        items = list(_items().filter(material=m["name"]).order_by("sort", "id"))
        seen, cards, catalog = set(), [], []
        for it in items:
            if it.kind == "catalog":
                catalog.append(it)
                continue
            if not it.color_code or it.color_code in seen or not is_swatch(it):
                continue
            seen.add(it.color_code)
            cards.append('<a class="card" href="/p/%s/%s/"><img loading="lazy" src="%s" alt=""><div class="t">%s</div>'
                         '<div class="s">Подивитись у інтерʼєрі →</div></a>' % (
                             slug, escape(it.color_code.replace(" ", "+")), escape(file_url(it)), escape(it.color_code)))
        body = ""
        if catalog:
            body += '<h2 style="font-size:17px;margin:14px 0 6px">Каталог</h2><div class="grid">%s</div>' % "".join(
                '<a class="card" href="%s" target="_blank" rel="noopener"><img loading="lazy" src="%s" alt="">'
                '<div class="t">%s</div></a>' % (escape(file_url(c)), escape(file_url(c)), escape(c.title[:60])) for c in catalog)
        body += '<h2 style="font-size:17px;margin:18px 0 6px">Кольори (%d)</h2><div class="grid">%s</div>' % (len(cards), "".join(cards))
        body += '<div class="note">Сподобався колір — напишіть менеджеру його код, і ми підготуємо розрахунок або викраску 10×30 см у цьому кольорі.</div>'
        return _page(m["name"], body, BLURB.get(m["name"], ""), back=("/p/", "усі матеріали"))


class ShowcaseColorView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug, code):
        m = material_by_slug(slug)
        if not m:
            raise Http404
        code = (code or "").replace("+", " ").strip()
        items = list(_items().filter(material=m["name"], color_code=code).order_by("sort", "id"))
        if not items:
            raise Http404
        swatch = next((i for i in items if is_swatch(i)), None)
        videos = [i for i in items if i.kind == "video"]
        photos = [i for i in items if i.kind == "image" and i is not swatch and not is_swatch(i)]
        body = ""
        if swatch:
            body += '<div class="big"><img src="%s" alt=""></div>' % escape(file_url(swatch))
        if photos:
            body += '<h2 style="font-size:17px;margin:18px 0 6px">У інтерʼєрі (%d)</h2><div class="row">%s</div>' % (
                len(photos), "".join('<a href="%s" target="_blank" rel="noopener"><img loading="lazy" src="%s" alt="" '
                                     'style="width:100%%;border-radius:12px;border:1px solid var(--line)"></a>'
                                     % (escape(file_url(p)), escape(file_url(p))) for p in photos))
        if videos:
            body += '<h2 style="font-size:17px;margin:18px 0 6px">Відео</h2><div class="row">%s</div>' % "".join(
                '<video controls preload="metadata" src="%s"></video>' % escape(file_url(v)) for v in videos)
        # 17.09.2026 (Олег): «щоб клієнт кнопкою обирав колір і потрапляв у чат з менеджером»
        msg = "Обрав колір %s · %s. Порахуйте, будь ласка, матеріал (або викраску 10×30 см у цьому кольорі)." % (m["name"], code)
        q = quote(msg)
        body += ('<div class="pick"><b>Сподобався цей колір?</b>'
                 '<div style="color:var(--muted);font-size:14px;margin-top:4px">Натисніть — код %s піде менеджеру, '
                 'і ми порахуємо матеріал на Вашу площу або зробимо викраску 10×30 см у цьому кольорі.</div>'
                 '<div class="btns">'
                 '<button class="btn primary" type="button" onclick="pick()">🎨 Обрати цей колір</button>'
                 '<a class="btn" href="viber://chat?number=%%2B%s&amp;draft=%s" rel="noopener">Viber</a>'
                 '<a class="btn" href="%s" target="_blank" rel="noopener">Telegram</a>'
                 '<a class="btn" href="https://wa.me/%s?text=%s" target="_blank" rel="noopener">WhatsApp</a>'
                 '</div><div class="ok" id="ok">Код скопійовано — вставте його у ваш чат з менеджером 👍</div></div>'
                 '<script>function pick(){var t=%s;try{navigator.clipboard.writeText(t);}catch(e){}'
                 'var o=document.getElementById("ok");o.style.display="block";'
                 'setTimeout(function(){location.href="%s";},900);}</script>'
                 % (escape(code), MANAGER_PHONE, q, escape(MANAGER_TG + "?text=" + q), MANAGER_PHONE, q,
                    json_dumps(msg), escape(MANAGER_TG + "?text=" + q)))
        return _page("%s · %s" % (m["name"], code), body, BLURB.get(m["name"], ""),
                     back=("/p/%s/" % slug, m["name"]))
