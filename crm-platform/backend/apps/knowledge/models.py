"""Єдина база знань ІІ-агентів Wallcov (AI ЦЕНТР), 14.09.2026.

Одна правда для всіх ІІ: агент воронки, AI-РОП підказка, помічник ✨, рецензент,
а Юля IG/TikTok отримує копію через kb_publish_chatplace.

Правила (рішення Олега 14.09):
- агенти читають ТІЛЬКИ записи зі статусом «Затверджено»;
- нове додається лише як «Чернетка» (вручну, з імпорту, від рецензента);
- затверджує власник (право knowledge.approve, за замовчуванням — лише власник);
- ціни в тексті не пишемо — підставляємо з каталогу CRM: {price:ID} або {m2:ID};
- кожна зміна — рядок в історії версій (KnowledgeVersion).
"""
from django.conf import settings
from django.db import models


class KnowledgeItem(models.Model):
    KINDS = [
        ("rule", "Правило"),
        ("fact", "Факт"),
        ("qa", "Питання-відповідь"),
        ("template", "Шаблон"),
    ]
    TOPICS = [
        ("payment", "Оплата"),
        ("delivery", "Доставка"),
        ("test_sets", "Тест-набори"),
        ("pricing", "Ціни і прорахунок"),
        ("materials", "Матеріали"),
        ("application", "Нанесення та інструмент"),
        ("tinting", "Тонування і кольори"),
        ("contacts", "Контакти"),
        ("discounts", "Знижки та акції"),
        ("objections", "Заперечення"),
        ("company", "Про компанію"),
        ("tone", "Тон і заборони"),
        ("process", "Процеси CRM"),
        ("other", "Інше"),
    ]
    AGENTS = [
        ("yulia_ig", "Юля Instagram (ChatPlace)"),
        ("yulia_tiktok", "Юля TikTok (ChatPlace)"),
        ("yulia_web", "Сайт — веб-чат (ІІ CRM)"),
        ("funnel_agent", "Агент воронки CRM"),
        ("rop_hint", "AI-РОП підказка"),
        ("compose_assist", "Помічник ✨"),
        ("analyst", "Аналітик / рецензент"),
    ]
    STATUS = [
        ("draft", "Чернетка"),
        ("approved", "Затверджено"),
        ("archived", "Архів"),
    ]
    SOURCES = [
        ("manual", "Вручну"),
        ("import_kb", "Стара база AI ЦЕНТРУ"),
        ("code", "Правило з коду CRM"),
        ("reviewer", "Рецензент (пропозиція)"),
        ("chatplace", "ChatPlace"),
    ]

    kind = models.CharField("Тип", max_length=12, choices=KINDS, default="qa", db_index=True)
    topic = models.CharField("Тема", max_length=20, choices=TOPICS, default="other", db_index=True)
    audience = models.JSONField("Для яких агентів", default=list, blank=True,
                                help_text="Коди агентів з AGENTS: хто отримує цей запис")
    status = models.CharField("Статус", max_length=10, choices=STATUS, default="draft", db_index=True)
    title = models.CharField("Питання / назва", max_length=300)
    text = models.TextField("Текст для агента / відповідь клієнту",
                            help_text="Ціни не писати цифрами — {price:ID товару} або {m2:ID товару}")
    internal_note = models.TextField("Внутрішня примітка", blank=True, default="")
    products = models.ManyToManyField("warehouse.Product", blank=True, related_name="knowledge_items",
                                      help_text="Товари, ціни яких агент бачить разом із записом")
    source = models.CharField("Джерело", max_length=12, choices=SOURCES, default="manual", db_index=True)
    source_ref = models.CharField("Посилання на джерело", max_length=120, blank=True, default="", db_index=True,
                                  help_text="kbentry:<id> — стара база AI ЦЕНТРУ; code:<ключ>; proposal:<id>")
    external_ids = models.JSONField(default=dict, blank=True,
                                    help_text="Ідентифікатори копій: chatplace_ig / chatplace_tt")
    evidence = models.JSONField(default=dict, blank=True,
                                help_text="Для пропозицій рецензента: діалог, цитата, у чому проблема")
    replaces = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="proposals",
                                 help_text="Пропонована правка до затвердженого запису")
    priority = models.IntegerField("Пріоритет (менше — вище)", default=100)
    popularity = models.IntegerField("Скільки разів питали клієнти", default=0)
    version = models.PositiveIntegerField(default=1)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_note = models.CharField(max_length=200, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["topic", "priority", "id"]
        indexes = [models.Index(fields=["status", "topic"], name="kn_item_status_topic")]

    def __str__(self):
        return "[%s] %s" % (self.get_status_display(), (self.title or "")[:60])


class KnowledgeVersion(models.Model):
    """Історія: хто, коли і що змінив у записі (знімок цілком)."""
    ACTIONS = [
        ("create", "Створено"),
        ("import", "Імпортовано"),
        ("edit", "Змінено"),
        ("propose", "Запропоновано правку"),
        ("approve", "Затверджено"),
        ("archive", "В архів"),
        ("restore", "Повернуто в чернетки"),
        ("publish", "Опубліковано в ChatPlace"),
    ]
    item = models.ForeignKey(KnowledgeItem, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    action = models.CharField(max_length=10, choices=ACTIONS)
    snapshot = models.JSONField(default=dict)
    note = models.CharField(max_length=300, blank=True, default="")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class KnowledgeSettings(models.Model):
    """Налаштування команди агентів (один рядок, id=1). Усе, що витрачає гроші на ІІ, — ВИМКНЕНО."""
    reviewer_enabled = models.BooleanField(default=False, help_text="Щоденний рецензент закритих чатів (Claude)")
    reviewer_model = models.CharField(max_length=40, default="claude-haiku-4-5")
    reviewer_sample = models.PositiveIntegerField(default=20, help_text="Скільки закритих чатів за день перевіряти")
    # 14.09 (ai-kb2): веб-чат на сайті відповідає з бази знань. ВИМКНЕНО, вмикає лише власник.
    webchat_ai_enabled = models.BooleanField(default=False, help_text="ІІ відповідає у веб-чаті (лише затверджене «Сайт»)")
    webchat_model = models.CharField(max_length=40, default="claude-haiku-4-5")
    # 17.09.2026 (Олег): ІІ у каналах CRM (Viber, Telegram, WhatsApp, Facebook) — налаштування тут, в AI ЦЕНТРІ.
    ai_silence_hours = models.PositiveSmallIntegerField(default=12,
        help_text="Скільки годин ІІ мовчить у чаті після повідомлення менеджера")
    ai_max_per_day = models.PositiveSmallIntegerField(default=15,
        help_text="Скільки відповідей ІІ може дати в одному чаті за добу")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


class KnowledgeReviewLog(models.Model):
    """Який закритий чат рецензент уже перевірив (щоб не платити двічі за той самий діалог)."""
    conversation_id = models.IntegerField(db_index=True)
    day = models.DateField(db_index=True)
    lint_findings = models.IntegerField(default=0)
    ai_findings = models.IntegerField(default=0)
    items_created = models.IntegerField(default=0)
    model = models.CharField(max_length=40, blank=True, default="")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["conversation_id", "day"], name="kn_review_conv_day")]


def snapshot(item):
    return {
        "kind": item.kind, "topic": item.topic, "audience": list(item.audience or []), "status": item.status,
        "title": item.title, "text": item.text, "internal_note": item.internal_note, "priority": item.priority,
        "products": sorted(item.products.values_list("id", flat=True)) if item.pk else [],
        "replaces": item.replaces_id,
    }


def log_version(item, action, user=None, note=""):
    return KnowledgeVersion.objects.create(
        item=item, version=item.version, action=action, snapshot=snapshot(item), note=(note or "")[:300],
        changed_by=user if (user and getattr(user, "is_authenticated", False)) else None)


class KnowledgeRun(models.Model):
    """Запуск за кнопкою Олега (14.09, ai-kb2): попередня перевірка чернеток, контролер закритих чатів,
    публікація в Юлю. Нічого не запускається за розкладом. Тут — прогрес, оцінка й фактична вартість,
    результат і (для публікації) бекап бази ChatPlace перед записом."""
    KINDS = [
        ("precheck", "Попередня перевірка чернеток"),
        ("controller", "Контролер закритих чатів"),
        ("publish", "Публікація в Юлю (ChatPlace)"),
    ]
    STATUS = [("running", "Виконується"), ("done", "Готово"), ("error", "Помилка")]
    kind = models.CharField(max_length=12, choices=KINDS, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS, default="running", db_index=True)
    params = models.JSONField(default=dict, blank=True)
    total = models.PositiveIntegerField(default=0)
    done = models.PositiveIntegerField(default=0)
    est_cost_usd = models.FloatField(default=0)
    cost_usd = models.FloatField(default=0)
    result = models.JSONField(default=dict, blank=True)
    backup = models.JSONField(default=list, blank=True, help_text="Публікація: база ChatPlace до запису")
    error = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class KnowledgeCheck(models.Model):
    """Мітка попередньої перевірки чернетки (одна на запис). Нічого не затверджує.
    Якщо запис змінили після перевірки (item_version ≠ version) — мітка «застаріла»."""
    LABELS = [
        ("ready", "Готово до затвердження"),
        ("fix", "Потрібна правка"),
        ("dup", "Дубль"),
        ("conflict", "Суперечить затвердженому або каталогу CRM"),
    ]
    item = models.OneToOneField(KnowledgeItem, on_delete=models.CASCADE, related_name="precheck")
    label = models.CharField(max_length=10, choices=LABELS, db_index=True)
    reason = models.CharField(max_length=300, blank=True, default="")
    ref_item_id = models.IntegerField(null=True, blank=True, help_text="Дубль / суперечність з записом №")
    item_version = models.PositiveIntegerField(default=1)
    source = models.CharField(max_length=6, default="ai", help_text="code — перевірка кодом ($0); ai — Claude")
    model = models.CharField(max_length=40, blank=True, default="")
    run = models.ForeignKey(KnowledgeRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    checked_at = models.DateTimeField(auto_now=True)
