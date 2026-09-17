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
import datetime
import json
import re
from html import escape
from urllib.parse import quote

from django.core import signing
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Conversation, MediaLibraryItem, Message

PUBLIC_HOST = "https://wallcov.com.ua"          # той самий домен, що для /f/<код> (проксі на CRM)
MANAGER_PHONE = "380973282283"                  # той самий номер, що Юля дає клієнту (Viber / Telegram / WhatsApp)
MANAGER_TG = "https://t.me/wallcov_pidtrimka"
MANAGER_VIBER = "https://msng.link/o?380973282283=vi"   # той самий лінк, що дає Юля (viber://chat відкривається не в усіх)
# Ліпнина і плінтуси — це моделі, а не кольори (Олег 17.09)
MODEL_MATERIALS = {"Orac Decor", "Плінтуси Cezar"}
SECTION = "colors"
SWATCH_RE = re.compile(r"(каталог|зразок|sample)", re.I)

# Короткий опис матеріалу для клієнта (без вигадок — те саме, що в описах тест-наборів).
BLURB = {
    "Мокрий шовк": "Ефект «мокрого шовку»: стіна мʼяко переливається, як шовкова тканина, і змінює відтінок залежно від світла.",
    "Вельвет Луна": "Сатиново-шовковий перламутровий перелив: мʼяка глибока фактура, яка грає при денному й вечірньому світлі.",
    "Патера": "Фактурні покриття Pattera: травертин, матовий марморин і арт-бетон — фактура природного каменю й бетону.",
    "Перламутрові піщинки": "Делікатне сяйво перламутрових піщинок, яке по-різному виглядає вдень і ввечері.",
    "Плінтуси Cezar": "Плінтуси та молдинги Cezar — моделі й розміри.",
    "Orac Decor": "Ліпнина Orac Decor: карнизи, молдинги, розетки, панелі.",
}
SLUG_MAP = {
    "мокрий шовк": "mokryi-shovk", "вельвет луна": "velvet-luna", "патера": "pattera",
    "песочки": "pisochky", "перламутрові піщинки": "pisochky",   # 18.09.2026: стара назва була російською; адреса лишилась
    "плінтуси cezar": "cezar", "orac decor": "orac",
}


TOKEN_SALT = "showcase-pick"
TOKEN_MAX_AGE = 60 * 60 * 24 * 60        # 60 днів — стільки живе персональне посилання
PICK_SENDER = "Клієнт · сторінка кольорів"
PICK_RE = re.compile(r"\{(?:кольори|кольори|colors)(?::([a-z0-9\-]+))?(?:/([^}]+))?\}")


def conv_token(conv_id):
    return signing.dumps({"c": int(conv_id)}, salt=TOKEN_SALT)


def page_link(slug="", code="", conv_id=None):
    """Посилання клієнту. З conv_id — персональне: кнопка «Обрати» напише в ЦЕЙ чат CRM."""
    url = PUBLIC_HOST + "/p/"
    if slug:
        url += "%s/" % slug
        if code:
            url += "%s/" % quote(str(code).replace(" ", "+"), safe="+/")
    if conv_id:
        url += "?c=%s" % conv_token(conv_id)
    return url


PLAIN_LINK_RE = re.compile(r"https://wallcov\.com\.ua/p/[^\s<>\"\'\)\]]*", re.I)


def personalize(text, conv):
    """Готуємо посилання для клієнта у вихідному повідомленні:
    • {кольори} / {кольори:velvet-luna} → посилання на сторінку кольорів;
    • будь-яке посилання wallcov.com.ua/p/… (його міг написати менеджер або ІІ) робимо ПЕРСОНАЛЬНИМ —
      додаємо мітку цього чату, щоб кнопка «Обрати цей колір» прилетіла назад саме сюди (18.09.2026, Олег)."""
    if not text:
        return text
    conv_id = getattr(conv, "id", None)
    out = PICK_RE.sub(lambda m: page_link(m.group(1) or "", m.group(2) or "", conv_id), text) if "{кольори" in text else text
    if not conv_id or "wallcov.com.ua/p/" not in out:
        return out

    def _mark(m):
        url = m.group(0)
        if "c=" in url.split("?", 1)[-1] and "?" in url:
            return url
        tail = "" if url.endswith("/") or url.endswith("=") else ""
        return "%s%s%sc=%s" % (url, tail, "&" if "?" in url else "?", conv_token(conv_id))
    return PLAIN_LINK_RE.sub(_mark, out)


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


def is_model(material):
    return material in MODEL_MATERIALS


def words(material):
    """Кольори чи моделі — щоб на ліпнині й плінтусах не писати «оберіть колір»."""
    if is_model(material):
        return {"many": "Моделі", "code": "артикул", "liked": "Сподобалась ця модель?",
                "pick": "📐 Обрати цю модель", "open": "Подивитись фото →"}
    return {"many": "Кольори", "code": "код кольору", "liked": "Сподобався цей колір?",
            "pick": "🎨 Обрати цей колір", "open": "Подивитись у інтерʼєрі →"}


def material_by_slug(slug):
    for m in materials():
        if m["slug"] == slug:
            return m
    return None


def effect_photos(material, code=None, limit=3):
    """По одному фото на КОЖЕН ефект матеріалу (Патера: травертин, марморин, фактура) —
    18.09.2026 (Олег): «коли запит на Патеру, треба відправляти фото ефектів, а не просто слова»."""
    rows = []
    for it in _items():
        if (it.material or "") != material or it.kind != "image" or is_swatch(it):
            continue
        m = re.search(r"effect:([^|]+)", it.tags or "")
        if not m:
            continue
        rows.append((m.group(1).split(",")[0].strip()[:40], it))
    out, seen = [], set()
    for want in ([code] if code else []) + [None]:
        for eff, it in rows:
            if eff in seen or (want and (it.color_code or "") != want):
                continue
            seen.add(eff)
            out.append((eff, it))
            if len(out) >= limit:
                return out
    return out[:limit]


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
.vids{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin-top:12px}
.vids video{max-height:70vh;max-width:100%%;width:auto;border-radius:12px;background:#0f172a;display:block}
.note{background:#eef5fc;border-radius:10px;padding:10px 12px;font-size:14px;color:#1e3a5f;margin:14px 0}
.foot{color:var(--muted);font-size:13px;margin-top:28px;text-align:center}
.pick{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;margin:16px 0}
.pick b{font-size:16px}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.btn{display:inline-flex;align-items:center;gap:6px;border-radius:10px;padding:10px 14px;font-size:15px;font-weight:600;text-decoration:none;border:1px solid var(--line);background:#fff;color:var(--ink);cursor:pointer}
.btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}
.ok{color:#2F8F5B;font-size:14px;margin-top:8px;display:none}
.lb{position:fixed;inset:0;background:rgba(15,23,42,.94);display:none;align-items:center;justify-content:center;padding:14px;z-index:60}
.lb.on{display:flex}
.lb img{max-width:100%%;max-height:84vh;border-radius:10px;display:block}
.lb .x{position:absolute;top:12px;right:12px;background:#fff;color:var(--ink);border:0;border-radius:999px;padding:9px 16px;font-size:15px;font-weight:700;cursor:pointer}
.lb .hint{position:absolute;bottom:16px;left:0;right:0;text-align:center;color:#e7ebf2;font-size:13px}
</style></head><body><div class="wrap">%s<h1>%s</h1>%s%s
<div class="foot">Wallcov · декоративні покриття</div></div>
<div class="lb" id="lb" role="dialog" aria-label="Фото"><button class="x" type="button" id="lbx">✕ Закрити</button>
<img id="lbi" src="" alt=""><div class="hint">Натисніть будь-де, щоб повернутись</div></div>
<script>(function(){var lb=document.getElementById("lb"),im=document.getElementById("lbi");
function open(src){im.src=src;lb.classList.add("on");document.body.style.overflow="hidden";
 try{history.pushState({lb:1},"");}catch(e){}}
function close(){lb.classList.remove("on");im.src="";document.body.style.overflow="";}
document.addEventListener("click",function(e){var a=e.target.closest("[data-full]");
 if(a){e.preventDefault();open(a.getAttribute("data-full"));return;}
 if(lb.classList.contains("on")){close();}});
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&lb.classList.contains("on")){close();}});
window.addEventListener("popstate",function(){if(lb.classList.contains("on")){close();}});})();</script>
</body></html>""" % (
        escape(title), nav, escape(title),
        ('<p class="lead">%s</p>' % escape(subtitle)) if subtitle else "", body))


class ShowcasePickView(APIView):
    """Клієнт натиснув «Обрати цей колір» на персональному посиланні — пишемо вибір у ТОЙ САМИЙ чат CRM,
    звідки клієнт прийшов (17.09.2026, Олег). Посилання підписане: підробити чи підставити чужий чат не можна."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        token = (request.data.get("c") or "").strip()
        cp = str(request.data.get("cp") or "").strip()[:128]
        text = (request.data.get("text") or "").strip()[:300]
        conv = None
        if token:
            try:
                data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
            except Exception:
                return Response({"ok": False, "detail": "посилання застаріле"}, status=400)
            conv = Conversation.objects.filter(id=data.get("c")).select_related("channel").first()
        elif cp:
            # 18.09.2026 (Олег): «незалежно, де клієнт — Instagram чи інший месенджер».
            # Юля (ChatPlace) підставляє у посилання свій ідентифікатор чату — шукаємо ту саму розмову в CRM.
            conv = (Conversation.objects.filter(external_chat_id=cp, status="open")
                    .select_related("channel").order_by("-last_message_at").first()
                    or Conversation.objects.filter(external_chat_id=cp)
                    .select_related("channel").order_by("-last_message_at").first())
        if not conv or not text:
            return Response({"ok": False}, status=400)
        recent = Message.objects.filter(conversation=conv, sender_name=PICK_SENDER,
                                        created_at__gte=timezone.now() - datetime.timedelta(hours=1)).count()
        if recent >= 10:
            return Response({"ok": False, "detail": "забагато натискань"}, status=429)
        Message.objects.create(conversation=conv, direction="in", text=text, sender_name=PICK_SENDER)
        Conversation.objects.filter(id=conv.id).update(unread=(conv.unread or 0) + 1, last_message_at=timezone.now(),
                                                       status="open")
        return Response({"ok": True})


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
            # 18.09.2026: за цією ж адресою живуть ПОСИЛАННЯ НА ОПЛАТУ (/p/<код>/) — якщо це не матеріал,
            # віддаємо керування їм, інакше клієнт бачив би 404 замість сторінки оплати.
            from apps.crm.views import paylink_redirect
            return paylink_redirect(request, slug)
        w = words(m["name"])
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
                         '<div class="s">%s</div></a>' % (
                             slug, escape(it.color_code.replace(" ", "+")), escape(file_url(it)), escape(it.color_code),
                             w["open"]))
        body = ""
        if catalog:
            body += '<h2 style="font-size:17px;margin:14px 0 6px">Каталог</h2><div class="grid">%s</div>' % "".join(
                '<a class="card" href="%s" data-full="%s"><img loading="lazy" src="%s" alt="">'
                '<div class="t">%s</div></a>' % (escape(file_url(c)), escape(file_url(c)), escape(file_url(c)),
                                                 escape(c.title[:60])) for c in catalog)
        body += '<h2 style="font-size:17px;margin:18px 0 6px">%s (%d)</h2><div class="grid">%s</div>' % (
            w["many"], len(cards), "".join(cards))
        body += ('<div class="note">Сподобалось — напишіть менеджеру %s: порахуємо матеріал на Вашу площу%s.</div>'
                 % (w["code"], "" if is_model(m["name"]) else " і підготуємо тест-набір саме в цьому кольорі"))
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
            body += ('<div class="big"><a href="%s" data-full="%s"><img src="%s" alt=""></a></div>'
                     % (escape(file_url(swatch)), escape(file_url(swatch)), escape(file_url(swatch))))
        if photos:
            body += '<h2 style="font-size:17px;margin:18px 0 6px">У інтерʼєрі (%d)</h2><div class="row">%s</div>' % (
                len(photos), "".join('<a href="%s" data-full="%s"><img loading="lazy" src="%s" alt="" '
                                     'style="width:100%%;border-radius:12px;border:1px solid var(--line)"></a>'
                                     % (escape(file_url(p)), escape(file_url(p)), escape(file_url(p))) for p in photos))
        if videos:
            # 18.09.2026 (Олег): вертикальне відео не розтягуємо на всю ширину — інакше півекрана порожнечі
            body += '<h2 style="font-size:17px;margin:18px 0 6px">Відео</h2><div class="vids">%s</div>' % "".join(
                '<video controls playsinline preload="metadata" src="%s"></video>' % escape(file_url(v)) for v in videos)
        # 17.09.2026 (Олег): «щоб клієнт кнопкою обирав колір і потрапляв у чат з менеджером»
        w = words(m["name"])
        # 18.09.2026 (Олег): продаємо насамперед ТЕСТ-НАБІР; викраска — виняток, коли навіть набір дорогий
        msg = ("Обрав модель %s · %s. Порахуйте, будь ласка." % (m["name"], code) if is_model(m["name"])
               else "Обрав колір %s · %s. Оформіть, будь ласка, тест-набір у цьому кольорі." % (m["name"], code))
        q = quote(msg)
        body += ('<div class="pick"><b>%s</b>'
                 '<div style="color:var(--muted);font-size:14px;margin-top:4px">Натисніть — %s піде менеджеру, '
                 'і ми все порахуємо під Вас.</div>'
                 '<div class="btns">'
                 '<button class="btn primary" type="button" onclick="pick()">%s</button>'
                 '<a class="btn" href="%s" target="_blank" rel="noopener">Viber</a>'
                 '<a class="btn" href="%s" target="_blank" rel="noopener">Telegram</a>'
                 '<a class="btn" href="https://wa.me/%s?text=%s" target="_blank" rel="noopener">WhatsApp</a>'
                 '</div><div class="ok" id="ok">Скопійовано — вставте у ваш чат з менеджером 👍</div></div>'
                 '<script>if(new URLSearchParams(location.search).get("c")||new URLSearchParams(location.search).get("cp")){'
                 'document.querySelectorAll(".pick .btn:not(.primary)").forEach(function(b){b.style.display="none";});}</script>'
                 '<script>function pick(){var t=%s;var o=document.getElementById("ok");'
                 'var q=new URLSearchParams(location.search);var c=q.get("c")||q.get("cp");'
                 'if(c){fetch("/p/pick/",{method:"POST",headers:{"Content-Type":"application/json"},'
                 'body:JSON.stringify(q.get("c")?{c:c,text:t}:{cp:c,text:t})}).then(function(r){return r.json();}).then(function(d){'
                 'o.textContent=d && d.ok ? "Готово — менеджер уже бачить Ваш вибір у чаті ✅" : '
                 '"Не вдалось надіслати — напишіть код менеджеру, будь ласка";o.style.display="block";})'
                 '.catch(function(){o.textContent="Не вдалось надіслати — напишіть код менеджеру";o.style.display="block";});return;}'
                 'try{navigator.clipboard.writeText(t);}catch(e){}'
                 'o.textContent="Код скопійовано — поверніться у чат, де ми спілкуємось, і надішліть його 👍";'
                 'o.style.display="block";}</script>'
                 % (w["liked"], escape(code), w["pick"], escape(MANAGER_VIBER), escape(MANAGER_TG + "?text=" + q),
                    MANAGER_PHONE, q, json_dumps(msg)))
        return _page("%s · %s" % (m["name"], code), body, BLURB.get(m["name"], ""),
                     back=("/p/%s/" % slug, m["name"]))
