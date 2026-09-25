"""Блоги Олега (25.09.2026): у кожного свої акаунти, база знань і майстер-промт.

Генератори (рилси, каруселі) беруть із блогу: майстер-промт (тема, аудиторія, тон, заборони), факти його бази
знань і — для Wallcov — ще й затверджену базу знань CRM (AI ЦЕНТР). Незаповнений блог («[заповніть]» у промті)
не генерує: краще попросити Олега дописати, ніж вигадувати тему за нього.
"""
import re

from .models import Blog, BlogFact, ContentChannel

TODO = "[заповніть]"
TEMPLATE = (f"Про що блог: {TODO}\nДля кого: {TODO}\nТон і мова: {TODO}\n"
            f"Формати: рилси, каруселі\nЩо заборонено: вигадувати факти й цифри; шаблонні ШІ-фрази; емодзі-прикраси\n"
            f"Заклик у кінці: {TODO}")

# Спільні для всіх блогів заборони (рішення Олега 24.09: жодних ШІ-штампів і смайлів-прикрас)
COMMON_RULES = ("Пиши прямо й по-людськи, без води. ЗАБОРОНЕНО шаблони на кшталт «Плануєш… і не знаєш…», "
                "«Хочеш…, але боїшся…», «Мрієш про…», «А ти знала…», риторичні питання-пустушки, емодзі й смайли-прикраси. "
                "Факти, цифри й ціни — лише з блоку «База знань»; якщо точних даних немає — не вигадуй.")

WALLCOV_PROMPT = """Про що блог: декоративні штукатурки й фарби Wallcov — український виробник. Покриття: Галатея, мокрий шовк, вельвет, патера, травертин, мікроцемент та інші.
Для кого: переважно жінки 28–50, які роблять ремонт у квартирі чи будинку й самі обирають матеріал; майстри-оздоблювачі.
Тон і мова: українською, прямо й по-людськи, як говорить власник: факт → що робити. Без жаргону.
Формати: рилси 12–16 с з реальних кадрів, каруселі 5–8 слайдів, пости в Telegram.
Що заборонено: вигадувати цифри витрати, ціни, властивості — лише з бази знань; видавати ШІ-картинку за фото реального обʼєкта; перекрашувати чи «покращувати» фактуру.
Фактура в кадрі — завжди справжня (реальні фото й відео). ШІ-кадри — лише фон/інтерʼєр і з позначкою «ШІ-візуалізація».
Заклик у кінці: написати в Direct кодове слово або за телефоном."""

STINY_PROMPT = """Про що блог: мультсеріал «Гена і Барсик» про ремонт і декоративну штукатурку — гумор, у якому майстри й клієнти впізнають себе. Сезон «Квартира Олени».
Герої (обовʼязкові в кожній серії): Гена — майстер; Барсик — рудий кіт, «автор фактури»; замовниця Олена; Мурчик — сірий кіт-конкурент; чоловік-умілець.
Для кого: широка розважальна аудиторія TikTok (не лише ті, хто в ремонті).
Тон і мова: українською, живо й смішно; гумор на реальних болях клієнтів («чоловік сам зробить», «сам порахував матеріал», «хочу як на фото», «закінчимо в пʼятницю»). Кожна серія знімає одне заперечення.
Формати: вертикаль 22–25 с, хук у першу секунду, бейдж «СЕРІЯ N», фінал — тизер наступної серії й питання-суперечка «А чи Б?» для коментарів. Обкладинка — питання чи інтрига, не констатація.
Візуал: яскравий 2D/3D-мультфільм, ті самі персонажі від кадру до кадру. Текст на екрані — лише в безпечній зоні (не в нижній третині, не під правою колонкою кнопок).
Що заборонено: серії без героїв; пряма реклама; вигадані ціни.
Заклик у кінці: «Серія N+1 — вже в профілі» + питання «А чи Б?»."""

# slug, назва, тип, про що, акаунти [(платформа, handle)], промт, заклик, use_crm_kb, label_ai, real_footage, колір
SEED = [
    ("wallcov", "Wallcov · декор для стін", Blog.Kind.BRAND, "Декоративні штукатурки й фарби Wallcov",
     [("instagram", "dekor_dlia_stin"), ("tiktok", "dekor_dlia_stin"), ("telegram", "wallcovpro")],
     WALLCOV_PROMPT, "Напишіть нам у Direct: https://ig.me/m/dekor_dlia_stin\nТелефон: +380964191890", True, True, True, "#e3b85f"),
    ("stiny-v-shotsi", "Стіни в шоці · мультики", Blog.Kind.FUN, "Мультсеріал «Гена і Барсик» про ремонт",
     [("tiktok", "stiny_v_shotsi")], STINY_PROMPT, "Серія N+1 — вже в профілі. А ви за А чи Б?", False, False, False, "#f2a33a"),
    ("oleg", "Олег Кріжевський · особистий", Blog.Kind.PERSONAL, "Особистий блог Олега",
     [("instagram", "krijevskhi.ai"), ("tiktok", "kri_pro_dvijenie")], TEMPLATE, "", False, False, False, "#7fb0d4"),
    ("robota", "Найм · про роботу", Blog.Kind.HIRING, "Найм у команду",
     [("instagram", "pro.robotu_job")], TEMPLATE, "", False, False, False, "#d7f24a"),
    ("artbeton", "Артбетон Wallcov", Blog.Kind.BRAND, "",
     [("instagram", "artbeton_wallcov")], TEMPLATE, "", True, True, False, "#c9ccd0"),
    ("wallcovmade", "Wallcov made", Blog.Kind.BRAND, "",
     [("instagram", "wallcovmade")], TEMPLATE, "", True, True, False, "#b89d78"),
    ("povitrya", "Повітря", Blog.Kind.OTHER, "",
     [("instagram", "povitrya_")], TEMPLATE, "", False, False, False, "#6cc08f"),
    ("ventylyiatsia", "Вентиляція", Blog.Kind.OTHER, "",
     [("tiktok", "ventylyiatsia")], TEMPLATE, "", False, False, False, "#5fb3c9"),
    ("viplight", "VIP light", Blog.Kind.OTHER, "",
     [("instagram", "viplight_mg")], TEMPLATE, "", False, False, False, "#b07fd4"),
]

URLS = {"instagram": "https://www.instagram.com/{}/", "tiktok": "https://www.tiktok.com/@{}",
        "telegram": "https://t.me/{}", "youtube": "https://www.youtube.com/@{}"}


GOALS = {
    "wallcov": "Заявки: людина пише в Direct кодове слово або дзвонить. Вторинне — збереження ролика.",
    "stiny-v-shotsi": "Підписки й досмотр серій: людина додивляється, пише в коментарях «А чи Б» і йде в профіль по наступну серію.",
}


def ensure_blogs():
    """Створити стартові блоги й привʼязати їхні акаунти (ідемпотентно; нічого не перезаписує)."""
    if Blog.objects.exists():
        return
    for n, (slug, name, kind, about, accs, prompt, cta, crm_kb, label, footage, color) in enumerate(SEED):
        b = Blog.objects.create(slug=slug, name=name, kind=kind, about=about, master_prompt=prompt, cta=cta,
                                use_crm_kb=crm_kb, label_ai=label, real_footage=footage, color=color,
                                is_default=(slug == "wallcov"), sort=(n + 1) * 10, goal=GOALS.get(slug, ""))
        for platform, handle in accs:
            ch, created = ContentChannel.objects.get_or_create(
                platform=platform, handle=handle,
                defaults={"url": URLS[platform].format(handle), "role": ContentChannel.Role.OWN, "blog": b})
            if not created and ch.blog_id is None and ch.role == ContentChannel.Role.OWN:
                ch.blog = b
                ch.save(update_fields=["blog"])
    from .models import ReelDraft
    wallcov = Blog.objects.filter(slug="wallcov").first()
    if wallcov:
        ReelDraft.objects.filter(blog=None).update(blog=wallcov)  # усі рилси до 25.09 — Wallcov


def default_blog():
    ensure_blogs()
    return Blog.objects.filter(is_default=True).first() or Blog.objects.first()


def get_blog(blog_id):
    return Blog.objects.filter(pk=blog_id or 0).first() or default_blog()


def is_ready(blog):
    return bool(blog.master_prompt.strip()) and TODO not in blog.master_prompt


def require_ready(blog):
    if not is_ready(blog):
        raise ValueError(f"Блог «{blog.name}» ще не налаштований: допишіть майстер-промт (місця «{TODO}») у розділі «Блоги».")


def handle(blog):
    """Головний акаунт блогу для підпису на слайдах."""
    ch = blog.channels.filter(role=ContentChannel.Role.OWN).order_by("platform").first()
    return f"@{ch.handle}" if ch else ""


_WORD = re.compile(r"[\wʼ'’-]{4,}", re.U)


def _words(text):
    return {w.lower()[:6] for w in _WORD.findall(text or "")}


def facts_block(blog, query, limit=8, max_chars=3500):
    """База знань для промпта: правила й заборони блогу — завжди; факти/приклади — найближчі до теми;
    для блогів з use_crm_kb — ще й затверджені записи CRM. Повертає (текст, назви)."""
    rows, titles = [], []
    own = list(BlogFact.objects.filter(blog=blog, active=True))
    always = [f for f in own if f.kind in (BlogFact.Kind.RULE, BlogFact.Kind.BAN)]
    q = _words(query)
    ranked = sorted((f for f in own if f not in always), key=lambda f: -len(q & _words(f.title + " " + f.text)))
    for f in always + ranked[:limit]:
        rows.append(f"[{f.get_kind_display()}] {f.title}: {f.text}".strip())
        titles.append(f.title)
    text = "\n".join(rows)
    if blog.use_crm_kb:
        from .telegram import kb_facts
        crm_text, crm_titles = kb_facts(query, limit=6, max_chars=max_chars)
        text = (text + "\n" + crm_text).strip()
        titles += crm_titles
    return text[:max_chars + 1500], titles


def system_for(blog, task, platform=True):
    """Системний промпт: завдання генератора + майстер-промт блогу + правила Instagram + спільні заборони."""
    from .platform_rules import INSTAGRAM
    rules = f"\n\nПРАВИЛА INSTAGRAM (офіційні рекомендації Meta — дотримуйся):\n{INSTAGRAM}" if platform else ""
    return (f"{task}{rules}\n\nБЛОГ: «{blog.name}».\nМАЙСТЕР-ПРОМТ БЛОГУ (головне, дотримуйся буквально):\n{blog.master_prompt.strip()}\n\n"
            f"Мета блогу: {blog.goal.strip() or '(не вказана)'}\nЗаклик блогу: {blog.cta.strip() or '(немає — без заклику)'}\n\n{COMMON_RULES}")


MASTER_FROM_BRIEF = """Олег коротко описав свій блог. Склади з цього майстер-промт для ШІ, який пише контент цього блогу.
Формат рівно такий (українською, кожен пункт 1–3 речення, лише з того, що сказав Олег; чого немає — залиш «[заповніть]»):
Про що блог: …
Для кого: …
Тон і мова: …
Формати: …
Візуал: …
Що заборонено: …
Заклик у кінці: …
Відповідай ЛИШЕ JSON: {"master_prompt":"...","cta":"...","about":"один рядок"}"""


def master_from_brief(blog, brief, call=None):
    """Чернетка майстер-промту з опису Олега (Haiku, ≈$0.003). Нічого не зберігає — Олег править і зберігає сам."""
    if call is None:
        from apps.crm.ai import claude_json
        call = lambda p: claude_json(p, model="claude-haiku-4-5", max_tokens=1200, system=MASTER_FROM_BRIEF,
                                     source="content_factory.blogs")
    r = call(f"Блог: {blog.name}\nАкаунти: {', '.join('@' + c.handle for c in blog.channels.all())}\n\nОпис Олега:\n{brief}") or {}
    return {"master_prompt": str(r.get("master_prompt") or "")[:6000], "cta": str(r.get("cta") or "")[:1000],
            "about": str(r.get("about") or "")[:300]}



# ── Памʼять блогу: що вже зробили й що пообіцяли ────────────────────────────────────────────────

MEMORY_RULES = ("ПАМʼЯТЬ БЛОГУ нижче. Не повторюй уже зроблені теми тими самими словами. Якщо є ВІДКРИТІ ОБІЦЯНКИ "
                "(«у наступному покажемо…») і тема цього контенту їх стосується — відповідай на найстаршу й вкажи її id в "
                "answers_promise_id. Якщо тема інша (термінова чи для розбавлення) — не давай нової обіцянки поверх відкритої, "
                "а в заклику коротко нагадай, що відповідь на обіцяне буде далі. Нову обіцянку (поле promise) давай лише якщо "
                "справді плануєш продовження, одним реченням.")


def memory_block(blog, limit=8):
    from .models import ContentMemory
    recent = list(ContentMemory.objects.filter(blog=blog)[:limit])
    opened = list(ContentMemory.objects.filter(blog=blog, promise_done=False).exclude(promise="").order_by("created_at")[:5])
    lines = [MEMORY_RULES, "Останнє:"] + ([f"- {m.get_kind_display()} «{m.title}»: {m.summary[:160]}" for m in recent] or ["- (нічого)"])
    lines.append("ВІДКРИТІ ОБІЦЯНКИ:" if opened else "ВІДКРИТІ ОБІЦЯНКИ: немає")
    lines += [f"- id {m.id}: {m.promise} (з «{m.title}», {m.created_at:%d.%m})" for m in opened]
    return "\n".join(lines)


def remember(blog, kind, ref_id, title, summary, promise="", answers_id=None):
    """Записати одиницю контенту в памʼять; якщо вона відповідає на обіцянку — закрити її."""
    from .models import ContentMemory
    ans = None
    try:
        ans = ContentMemory.objects.filter(pk=int(answers_id), blog=blog, promise_done=False).first() if answers_id else None
    except (TypeError, ValueError):
        ans = None
    m = ContentMemory.objects.create(blog=blog, kind=kind, ref_id=ref_id, title=title[:200], summary=summary[:1000],
                                     promise=(promise or "")[:300], answers=ans)
    if ans:
        ans.promise_done = True
        ans.save(update_fields=["promise_done"])
    return m
