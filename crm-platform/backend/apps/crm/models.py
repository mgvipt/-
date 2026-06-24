from django.conf import settings
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=255)
    edrpou = models.CharField("ЄДРПОУ/ИНН", max_length=32, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Contact(models.Model):
    """Карточка клиента. Каналы (Instagram/Viber/...) накапливаются по мере общения."""
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="contacts")
    channels = models.JSONField(default=list, blank=True, help_text="['instagram','viber',...]")
    loyalty_tag = models.CharField(max_length=24, blank=True, default="", help_text="Новый/Активный/VIP/Спящий")
    birthday = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=24, blank=True, default="", help_text="Звідки клієнт (instagram/site/...)")
    address = models.CharField(max_length=255, blank=True, default="", help_text="Адреса доставки / місто")
    comment = models.TextField(blank=True, default="", help_text="Нотатки менеджера про клієнта")
    social_link = models.CharField(max_length=300, blank=True, default="", help_text="Посилання на акаунт клієнта в месенджері (IG/TG/FB)")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="contacts_owned", help_text="Ответственный менеджер клиента")
    last_touch_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.phone or f"Контакт #{self.pk}"


class Funnel(models.Model):
    """Воронка продаж (напр. «21 Основний продукт», «22 Тестовий набір»)."""
    name = models.CharField(max_length=160)
    is_lead_funnel = models.BooleanField(default=False, help_text="True = воронка лидов")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Stage(models.Model):
    funnel = models.ForeignKey(Funnel, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=160)
    color = models.CharField(max_length=9, default="#3b82f6")
    order = models.PositiveIntegerField(default=0)
    is_won = models.BooleanField(default=False)
    is_lost = models.BooleanField(default=False)

    class Meta:
        ordering = ["funnel", "order"]

    def __str__(self):
        return f"{self.funnel.name} · {self.name}"


class TimestampedOwned(models.Model):
    """Базовая модель с владельцем и временем — для лидов и сделок."""
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="%(class)ss",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Lead(TimestampedOwned):
    SOURCES = [
        ("telegram", "Telegram"), ("viber", "Viber"), ("instagram", "Instagram"),
        ("facebook", "Facebook"), ("whatsapp", "WhatsApp"), ("call", "Звонок"),
        ("google_business", "Google Бизнес"), ("other", "Другое"),
        ("site", "Сайт wallcovdec"), ("wholesale", "Опт / дилери"),
        ("designers", "Дизайнери / прораби"), ("tiktok", "TikTok"),
    ]
    title = models.CharField(max_length=255)
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    funnel = models.ForeignKey(Funnel, on_delete=models.PROTECT, related_name="leads")
    stage = models.ForeignKey(Stage, on_delete=models.PROTECT, related_name="leads")
    source = models.CharField(max_length=24, choices=SOURCES, default="other")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_seen = models.BooleanField(default=False, help_text="Снимает бейдж 'НЕПЕРЕГЛЯНУТІ'")
    qualification = models.JSONField(default=dict, blank=True, help_text="Анкета виявлення потреби (тип приміщення, площа, матеріал, бюджет тощо)")
    card_fields = models.JSONField(default=list, blank=True, help_text="Кастомні поля/блоки картки (як у Бітриксі): [{label, value}]")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Deal(TimestampedOwned):
    title = models.CharField(max_length=255)
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="deals")
    funnel = models.ForeignKey(Funnel, on_delete=models.PROTECT, related_name="deals")
    stage = models.ForeignKey(Stage, on_delete=models.PROTECT, related_name="deals")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    source = models.CharField(max_length=24, choices=Lead.SOURCES, default="other")
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pay_type = models.CharField(max_length=40, blank=True, default="", help_text="Полная/Предоплата 50%/Послеоплата НП")
    ttn = models.CharField("ТТН Нова Пошта", max_length=40, blank=True, default="")
    checkbox_status = models.CharField(max_length=16, blank=True, default="none", help_text="none/аванс/финальный")
    closed_at = models.DateTimeField(null=True, blank=True)
    b24_id = models.CharField(max_length=20, blank=True, default="", db_index=True, help_text="ID угоди в Бітриксі (для токена Cashflow WC-{b24_id})")
    qualification = models.JSONField(default=dict, blank=True, help_text="Анкета виявлення потреби (переноситься з ліда)")
    card_fields = models.JSONField(default=list, blank=True, help_text="Кастомні поля картки [{label, value}]")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class DealItem(models.Model):
    """Товар в сделке. Сумма сделки = сумма строк."""
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("warehouse.Product", on_delete=models.PROTECT, related_name="deal_items")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reserved = models.BooleanField(default=False, help_text="Товар зарезервовано під цю сделку")

    @property
    def total(self):
        return self.quantity * self.price

    def __str__(self):
        return f"{self.product} × {self.quantity}"


class Payment(models.Model):
    """Перенос рабочих оплат: LiqPay / Checkbox / наличка. Питает финмодуль."""
    PROVIDERS = [("liqpay", "LiqPay"), ("checkbox", "Checkbox"), ("cash", "Наличные"), ("bank", "Банк")]
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="payments")
    provider = models.CharField(max_length=16, choices=PROVIDERS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    external_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_provider_display()} {self.amount} (#{self.deal_id})"


# ============================================================================
# АУДИТ-ЖУРНАЛ — хто/коли/що змінив (ліди, сделки, фінанси). Незалежний від Бітрикса.
# ============================================================================
class ActivityLog(models.Model):
    KIND = [("lead", "Лід"), ("deal", "Сделка"), ("finance", "Фінанси"), ("contact", "Клієнт")]
    kind = models.CharField(max_length=12, choices=KIND, db_index=True)
    object_id = models.IntegerField(db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.CharField(max_length=80, blank=True, default="", help_text="Хто дію зробив (менеджер / AI-агент / Система)")
    action = models.CharField(max_length=120)
    detail = models.CharField(max_length=400, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.kind}#{self.object_id}] {self.action}"


def log_activity(kind, object_id, action, detail="", user=None, actor=""):
    """Записати подію в аудит-журнал. Безпечно (не валить основну операцію)."""
    try:
        u = user if (user is not None and getattr(user, "is_authenticated", False)) else None
        who = actor or (u.get_full_name() or u.username if u else "Система")
        ActivityLog.objects.create(kind=kind, object_id=int(object_id), action=str(action)[:120],
                                   detail=str(detail)[:400], user=u, actor=str(who)[:80])
    except Exception:
        pass
