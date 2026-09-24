"""Контент-завод, етап 2 (24.09.2026): Telegram-автопілот — чернетки постів для @wallcovpro.

Звідки пост: найчастіше питання клієнтів за 7 днів (етап 1), яке ще не йшло в канал за 30 днів →
факти ЛИШЕ з затверджених записів бази знань (штатний пошук reader.select) → текст у стилі каналу →
2–3 РЕАЛЬНІ фото обʼєктів з бібліотеки (тег «реальне фото»), без ШІ-картинок.

Правила (Контент-стратегія @wallcovpro, Правила генерації контенту): аудиторія — жінки, що роблять ремонт самі;
коротко, 1–2 речення в абзаці, до 6 блоків; ціни й властивості — лише з бази знань, інакше «підкажемо»;
CTA від імені команди. Публікація з CRM поки вимкнена — лише чернетка на схвалення Олегом.
Витрати: ліміт на місяць, кожен виклик — AiUsage source=SOURCE («AI ЦЕНТР»). Заміна фото — без ШІ.
"""
import json
import os
import random
import urllib.error
import urllib.request
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from . import questions
from .models import QuestionTopic, TgPost, TgSettings

SOURCE = "content_factory.telegram"
REAL_TAG = "реальне фото"
PHOTOS_PER_POST = 3
CTA = ("💬 Напишіть нам у Direct: https://ig.me/m/dekor_dlia_stin\n"
       "📞 Зателефонуйте нам: +380964191890")
PRICE = {"claude-sonnet-4-6": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0)}


class BudgetError(Exception):
    pass


def month_spent():
    return questions.month_spent(SOURCE)


def estimate_usd(model):
    pin, pout = PRICE.get(model, (3.0, 15.0))
    return round((2600 * pin + 700 * pout) / 1_000_000, 4)  # ~2,6 тис. токенів фактів+правил, ~700 на пост


def next_topic():
    """Найчастіша за 7 днів робоча тема, якої не було в каналі (чернетка/схвалено/опубліковано) 30 днів."""
    since = timezone.now() - timedelta(days=7)
    used = TgPost.objects.filter(created_at__gte=timezone.now() - timedelta(days=30)).exclude(
        status=TgPost.Status.REJECTED).values_list("topic_id", flat=True)
    return (QuestionTopic.objects.exclude(status=QuestionTopic.Status.IGNORED).exclude(id__in=list(used))
            .annotate(n=Count("mentions", filter=Q(mentions__asked_at__gte=since))).filter(n__gt=0)
            .order_by("-n", "-last_seen").first())


def kb_facts(query, limit=6, max_chars=3500):
    """Затверджені записи бази знань, найближчі до теми (без правил агентів) → (текст для промпта, назви)."""
    from apps.knowledge import reader
    from apps.knowledge.models import KnowledgeItem
    items = list(KnowledgeItem.objects.filter(status="approved").exclude(kind="rule").prefetch_related("products"))
    picked = reader.select("", query=query, limit=limit, items=items)
    return reader.render_items(picked, max_chars=max_chars), [i.title for i in picked]


def real_materials():
    from apps.inbox.models import MediaLibraryItem
    return list(MediaLibraryItem.objects.filter(is_active=True, kind="image", tags__icontains=REAL_TAG)
                .exclude(material="").values_list("material", flat=True).distinct())


def pick_photos(material, exclude=()):
    """Реальні фото матеріалу; спершу ті, що ще не йшли в пости. Без ШІ."""
    from apps.inbox.models import MediaLibraryItem
    qs = list(MediaLibraryItem.objects.filter(is_active=True, kind="image", tags__icontains=REAL_TAG,
                                              material__iexact=material).exclude(id__in=list(exclude))
              .values_list("id", flat=True))
    if not qs:
        return []
    used = set()
    for ids in TgPost.objects.exclude(status=TgPost.Status.REJECTED).values_list("photo_ids", flat=True):
        used.update(ids or [])
    fresh = [i for i in qs if i not in used]
    pool = fresh if len(fresh) >= PHOTOS_PER_POST else qs
    random.shuffle(pool)
    return pool[:PHOTOS_PER_POST]


SYSTEM = """Ти редактор Telegram-каналу Wallcov @wallcovpro «Сучасні та практичні рішення для інтер'єру».
Аудиторія — жінки, які хочуть самі зробити красивий і практичний ремонт; не професійні майстри. Мова — українська, звертання на «ти».

Пишеш короткий корисний пост-відповідь на питання, яке клієнтки ставлять найчастіше.
Формат: перший рядок — гачок, що називає ситуацію так, як її відчуває клієнтка (переказ, НЕ дослівна цитата з її повідомлення: без її розмірів, міст, імен); далі до 5 коротких блоків, абзац — 1–2 речення,
список — максимум 3 пункти; один простий крок, який можна зробити самій. Без професійного жаргону, без тиску і «лише сьогодні».
Емодзі — не більше 2 на пост, без хештегів. Разом 350–700 символів без блоку контактів.

ФАКТИ — ЛИШЕ з блоку «База знань» нижче. Не вигадуй властивостей, строків служби, ціни, витрати, складу, гарантій.
Якщо в базі знань немає точної ціни чи цифри — не пиши її, а скажи, що порахуємо під її стіну.
Кожне твердження з цифрою чи властивістю матеріалу додай у checks для перевірки людиною.
Майстер-клас згадуй лише як доступний після покупки тестового набору. Не згадуй Юлію, ШІ, «базу знань» і внутрішні назви. Блок контактів НЕ пиши — він додається автоматично.

material — один матеріал зі списку «Є реальні фото», про який пост (для підбору фото); якщо пост загальний — найдоречніший зі списку.

Відповідай ЛИШЕ JSON:
{"title": "коротка назва для CRM", "text": "текст поста", "material": "...", "checks": ["..."]}"""


def generate(topic=None, call=None):
    """Створити одну чернетку. Піднімає BudgetError, якщо ліміт місяця не дозволяє. call — підміна ШІ (тести)."""
    s = TgSettings.get()
    topic = topic or next_topic()
    if topic is None:
        raise ValueError("Немає нових тем за 7 днів — спершу розберіть питання клієнтів.")
    est = estimate_usd(s.model)
    if month_spent() + est > float(s.monthly_budget_usd):
        raise BudgetError(f"Досягнуто місячного ліміту ${float(s.monthly_budget_usd):.2f} для Telegram-чернеток.")
    facts_text, fact_titles = kb_facts(topic.title + " " + " ".join((topic.examples or [])[:2]))
    materials = real_materials()
    prompt = "\n".join([
        f"Питання клієнток (разів за тиждень — найчастіше): {topic.title}",
        "Як саме питали: " + " | ".join((topic.examples or [])[:4]),
        f"Матеріал теми: {topic.material or 'не вказано'}",
        "Є реальні фото: " + ", ".join(materials),
        "", "База знань:", facts_text or "(немає записів — пиши загально, без цифр і властивостей)",
    ])
    if call is None:
        from apps.crm.ai import claude_json
        call = lambda p: claude_json(p, model=s.model, max_tokens=1500, system=SYSTEM, source=SOURCE)
    r = call(prompt) or {}
    text = str(r.get("text") or "").strip()
    if not text:
        raise ValueError("ШІ не повернув текст поста — спробуйте ще раз.")
    material = str(r.get("material") or topic.material or "").strip()
    if material not in materials:
        material = topic.material if topic.material in materials else (materials[0] if materials else "")
    return TgPost.objects.create(
        topic=topic, title=str(r.get("title") or topic.title)[:200], text=text.rstrip() + "\n\n" + CTA,
        material=material, photo_ids=pick_photos(material) if material else [], facts=fact_titles,
        checks=[str(c)[:200] for c in (r.get("checks") or [])][:8], model=s.model)


# ── Публікація і план (24.09.2026) ─────────────────────────────────────────────────────────────
# Бот @wallcov_smm_bot (адмін @wallcovpro). Токен лише в .env CRM: TG_CONTENT_BOT_TOKEN / _CHANNEL_ID / _OWNER_CHAT_ID.
# Публікуються ЛИШЕ схвалені пости: кнопкою «Опублікувати зараз» або за scheduled_at (крон кожні 5 хв).
# «Надіслати мені» шле точну копію в особистий чат Олега з ботом — перевірка без каналу.
CAPTION_LIMIT = 1024
MAX_MEDIA = 10


class PublishError(Exception):
    pass


def tg_config():
    return (os.environ.get("TG_CONTENT_BOT_TOKEN", ""), os.environ.get("TG_CONTENT_CHANNEL_ID", ""),
            os.environ.get("TG_CONTENT_OWNER_CHAT_ID", ""))


def publish_ready():
    token, channel, _owner = tg_config()
    return bool(token and channel)


def _multipart(fields, files):
    boundary = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out += [f"--{boundary}".encode(), f'Content-Disposition: form-data; name="{k}"'.encode(), b"", str(v).encode()]
    for name, (filename, data, ctype) in files.items():
        out += [f"--{boundary}".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode(),
                f"Content-Type: {ctype}".encode(), b"", data]
    out += [f"--{boundary}--".encode(), b""]
    return b"\r\n".join(out), f"multipart/form-data; boundary={boundary}"


def _tg(method, fields, files=None):
    token = tg_config()[0]
    if not token:
        raise PublishError("Бот для публікації не налаштований (TG_CONTENT_BOT_TOKEN).")
    body, ctype = _multipart(fields, files or {})
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=body,
                                 headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            resp = json.load(e)
        except Exception:
            raise PublishError(f"Telegram HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise PublishError(f"Telegram недоступний: {e}") from None
    if not resp.get("ok"):
        raise PublishError("Telegram: " + str(resp.get("description") or resp)[:200])
    return resp["result"]


def _media(post):
    """(kind, filename, bytes|None, content_type, file_id) у порядку: файли з TG-груп, відео, фото бібліотеки.
    Файли з груп ідуть за Telegram file_id — без завантаження на сервер і назад."""
    from apps.inbox.models import MediaLibraryItem
    from .models import SourceAsset
    out = []
    by_src = {a.id: a for a in SourceAsset.objects.filter(id__in=post.source_ids or [], kind__in=["photo", "video"])}
    for i in post.source_ids or []:
        if i in by_src:
            out.append((by_src[i].kind, "", None, "", by_src[i].file_id))
    ids = list(post.video_ids or []) + list(post.photo_ids or [])
    items = {m.id: m for m in MediaLibraryItem.objects.filter(id__in=ids).select_related("file")}
    for i in ids:
        m = items.get(i)
        if not m or not m.file_id or not m.file.data:
            continue
        kind = "video" if m.kind == "video" else "photo"
        out.append((kind, m.file.filename or f"{kind}-{i}", bytes(m.file.data), m.file.content_type, ""))
    return out[:MAX_MEDIA]


def send(post, chat_id):
    """Надіслати пост у чат. Довгий текст (>1024) — окремим повідомленням після медіа. Повертає id повідомлень."""
    text = post.text.strip()
    media = _media(post)
    ids = []
    caption = text if len(text) <= CAPTION_LIMIT else ""
    if not media:
        r = _tg("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"})
        return [r["message_id"]]
    if len(media) == 1:
        kind, fn, data, ct, file_id = media[0]
        method, field = ("sendVideo", "video") if kind == "video" else ("sendPhoto", "photo")
        fields = {"chat_id": chat_id}
        if caption:
            fields["caption"] = caption
        if file_id:
            fields[field] = file_id
            r = _tg(method, fields)
        else:
            r = _tg(method, fields, {field: (fn, data, ct)})
        ids.append(r["message_id"])
    else:
        group, files = [], {}
        for n, (kind, fn, data, ct, file_id) in enumerate(media):
            entry = {"type": kind, "media": file_id or f"attach://m{n}"}
            if n == 0 and caption:
                entry["caption"] = caption
            group.append(entry)
            if not file_id:
                files[f"m{n}"] = (fn, data, ct)
        r = _tg("sendMediaGroup", {"chat_id": chat_id, "media": json.dumps(group, ensure_ascii=False)}, files)
        ids += [m["message_id"] for m in r]
    if not caption:
        r = _tg("sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"})
        ids.append(r["message_id"])
    return ids


def send_test(post):
    owner = tg_config()[2]
    if not owner:
        raise PublishError("Не вказано особистий чат для перевірки (TG_CONTENT_OWNER_CHAT_ID).")
    return send(post, owner)


def publish(post_id):
    """Опублікувати схвалений пост у канал. Один раз: повторний виклик нічого не шле."""
    channel = tg_config()[1]
    error = None
    with transaction.atomic():
        post = TgPost.objects.select_for_update().get(pk=post_id)
        if post.status == TgPost.Status.PUBLISHED:
            return post
        if post.status != TgPost.Status.APPROVED:
            raise PublishError("Публікуються лише схвалені пости.")
        try:
            ids = send(post, channel)
        except PublishError as e:
            error = e
        else:
            post.status, post.published_at = TgPost.Status.PUBLISHED, timezone.now()
            post.tg_message_id, post.publish_error = ",".join(str(i) for i in ids), ""
            post.save(update_fields=["status", "published_at", "tg_message_id", "publish_error", "updated_at"])
    if error:
        # поза транзакцією, щоб текст помилки не відкотився разом з нею
        TgPost.objects.filter(pk=post_id).update(publish_error=str(error)[:300], updated_at=timezone.now())
        raise error
    return post


def publish_due():
    """Крон: схвалені пости, у яких настав scheduled_at. Помилка одного не зупиняє інші."""
    done, failed = [], []
    due = TgPost.objects.filter(status=TgPost.Status.APPROVED, scheduled_at__lte=timezone.now()).values_list("id", flat=True)
    for pid in list(due):
        try:
            publish(pid)
            done.append(pid)
        except PublishError as e:
            failed.append((pid, str(e)))
    return done, failed
