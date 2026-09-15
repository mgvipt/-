"""Біржа задач (bounty, 14.09.2026).

Прайс додаткових задач з оплатою: співробітник тисне «Беру» → виконує → здає з доказом → власник або призначений
перевіряючий «Прийнято» / «На доробку». Прийнята задача йде окремим рядком «Задачі з біржі» у ЗП того місяця
(apps.payroll.engine.calc). Гроші — з окремого фонду «Біржа задач» (стаття Фінмоделі з такою назвою, ₴/міс).

Нічого не вмикається само: усе, що заводить команда bounty_seed, неактивне з позначкою «ціна для обговорення».

v2 (15.09.2026): у задачі — «Навіщо», «Кінцевий результат» і підзадачі з простою інструкцією до кожної; у взятій
задачі — знімок підзадач на момент «Беру» і відмітки виконаних (здати можна будь-коли, перевіряючий бачить невідмічені).
Новий відділ «Найм»; відділ «Салон» показується як «Офлайн-магазин (салон)» (ключ salon не змінюється).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

DEPARTMENTS = [
    ("marketing", "Маркетинг / SMM"),
    ("sales", "Продажі"),
    ("warehouse", "Склад"),
    ("salon", "Офлайн-магазин (салон)"),
    ("objects", "Обʼєкти"),
    ("content", "Контент / сайт"),
    ("ai_crm", "ІІ і CRM"),
    ("hr", "Найм"),
    ("office", "Офіс"),
]
SUBTASKS_MAX = 12
DEPARTMENT_LABELS = dict(DEPARTMENTS)


class TaskCategory(models.Model):
    """Напрям усередині відділу: «Зйомка», «Монтаж», «Чати», «Номенклатура»…"""
    department = models.CharField(max_length=16, choices=DEPARTMENTS, db_index=True)
    name = models.CharField(max_length=120)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True, help_text="Показувати напрям на біржі")
    archived = models.BooleanField(default=False, help_text="Видалено (мʼяко): ніде не показується, історія лишається")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["department", "order", "id"]
        verbose_name = "Напрям біржі задач"
        verbose_name_plural = "Напрями біржі задач"

    def __str__(self):
        return f"{DEPARTMENT_LABELS.get(self.department, self.department)} · {self.name}"


class TaskOffer(models.Model):
    """Позиція прайсу: що зробити, як, що вважається виконаним, скільки платимо і скільки разів на місяць."""
    UNIT = [
        ("task", "за задачу"),
        ("piece", "за штуку"),
        ("hour", "за годину"),
        ("pct", "% з оплат"),
    ]
    PROOF = [
        ("any", "Посилання, фото або текст"),
        ("link", "Посилання"),
        ("photo", "Фото / файл"),
        ("text", "Текстовий звіт"),
    ]
    category = models.ForeignKey(TaskCategory, on_delete=models.PROTECT, related_name="offers")
    title = models.CharField(max_length=200)
    how_to = models.TextField(blank=True, default="", help_text="Як виконати — кроки, кожен з нового рядка")
    done_criteria = models.TextField(blank=True, default="", help_text="Що вважається виконаним і який доказ")
    why = models.CharField(max_length=255, blank=True, default="", help_text="Навіщо це бізнесу — один рядок")
    expected_result = models.TextField(blank=True, default="",
                                       help_text="Кінцевий результат, який можна виміряти («50 товарів мають вагу»)")
    subtasks = models.JSONField(default=list, blank=True,
                                help_text="Підзадачі: [{title, how}] — що зробити і як, по порядку")
    proof_type = models.CharField(max_length=6, choices=PROOF, default="any")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                help_text="₴ за одиницю; для «% з оплат» — відсоток")
    unit = models.CharField(max_length=6, choices=UNIT, default="task")
    unit_label = models.CharField(max_length=40, blank=True, default="",
                                  help_text="Для «за штуку»: що саме — «відео», «контакт», «50 товарів»")
    monthly_limit_qty = models.PositiveIntegerField(default=0, help_text="Скільки одиниць на місяць усього; 0 — без ліміту")
    max_per_person = models.PositiveIntegerField(default=0, help_text="Скільки одиниць на місяць на одну людину; 0 — без ліміту")
    max_takers = models.PositiveSmallIntegerField(default=1,
                                                  help_text="Скільки людей можуть виконувати одночасно; 1 — «зайнято» для інших; 0 — скільки завгодно")
    due_days = models.PositiveSmallIntegerField(default=3, help_text="Термін виконання після «Беру», днів")
    checker = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                help_text="Хто приймає; порожньо — власник / право «Керувати біржею задач»")
    active = models.BooleanField(default=False, help_text="Видно співробітникам і можна брати")
    archived = models.BooleanField(default=False, help_text="Видалено (мʼяко)")
    order = models.PositiveIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True, default="", help_text="Службова примітка: «ціна для обговорення»")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__department", "category__order", "order", "id"]
        verbose_name = "Задача біржі"
        verbose_name_plural = "Задачі біржі"

    def __str__(self):
        return self.title


class TaskClaim(models.Model):
    """«Беру» конкретної людини. Ціну й одиницю знімаємо в момент «Беру» — зміна прайсу не чіпає взяте."""
    STATUS = [
        ("taken", "Взято в роботу"),
        ("submitted", "Здано на перевірку"),
        ("rework", "На доробку"),
        ("accepted", "Прийнято"),
        ("cancelled", "Скасовано"),
    ]
    offer = models.ForeignKey(TaskOffer, on_delete=models.PROTECT, related_name="claims")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bounty_claims")
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Ціна на момент «Беру»")
    unit = models.CharField(max_length=6, default="task")
    base_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                      help_text="Для «% з оплат»: сума оплат, з якої рахуємо відсоток")
    status = models.CharField(max_length=10, choices=STATUS, default="taken", db_index=True)
    taken_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    proof_text = models.TextField(blank=True, default="")
    proof_url = models.CharField(max_length=500, blank=True, default="")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Нараховано після «Прийнято»")
    quality = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Оцінка якості 1–5 (для рейтингу)")
    payroll_period = models.CharField(max_length=7, blank=True, default="", db_index=True,
                                      help_text="Місяць ЗП (YYYY-MM), куди йде сума")
    comment = models.TextField(blank=True, default="", help_text="Коментар перевіряючого")
    std_score = models.FloatField(null=True, blank=True, help_text="Основний стандарт людини на момент «Беру» (0–1)")
    std_warning = models.CharField(max_length=255, blank=True, default="")
    history = models.JSONField(default=list, blank=True)
    subtasks = models.JSONField(default=list, blank=True,
                                help_text="Знімок підзадач задачі на момент «Беру» — зміна прайсу не зсуває відмітки")
    subtasks_done = models.JSONField(default=list, blank=True, help_text="Номери (з 0) виконаних підзадач")

    class Meta:
        ordering = ["-taken_at", "-id"]
        verbose_name = "Взята задача біржі"
        verbose_name_plural = "Взяті задачі біржі"

    def __str__(self):
        return f"{self.offer_id} · {self.user_id} · {self.status}"


class ClaimFile(models.Model):
    """Фото/файл-доказ. Як вкладення журналу — у БД (до 10 МБ), віддаємо лише через авторизований API."""
    claim = models.ForeignKey(TaskClaim, on_delete=models.CASCADE, related_name="files")
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, default="application/octet-stream")
    size = models.PositiveIntegerField(default=0)
    data = models.BinaryField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "id"]
