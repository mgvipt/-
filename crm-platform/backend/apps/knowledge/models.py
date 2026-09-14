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
