from django.contrib.auth.models import AbstractUser
from django.db import models


# Каталог прав. Администратор собирает из них роли (динамически).
PERMISSION_CHOICES = [
    ("lead.view.own", "Видеть только свои лиды"),
    ("lead.view.all", "Видеть все лиды (руководитель отдела)"),
    ("deal.view.own", "Видеть только свои сделки"),
    ("deal.view.all", "Видеть все сделки"),
    ("finance.view", "Доступ к финансам"),
    ("warehouse.view", "Доступ к складу"),
    ("telephony.view", "Доступ к телефонии и записям"),
    ("finance.manage", "Управление финмоделью (статьи ТБ/P&L)"),
    ("analytics.view", "Доступ к аналитике"),
    ("conversation.view.own", "Видеть только свои чаты"),
    ("conversation.view.all", "Видеть все чаты (руководитель)"),
    ("roles.manage", "Управление ролями и сотрудниками"),
]


class Department(models.Model):
    name = models.CharField(max_length=120)
    head = models.ForeignKey(
        "User", null=True, blank=True, on_delete=models.SET_NULL, related_name="headed_departments"
    )

    def __str__(self):
        return self.name


class Role(models.Model):
    """Динамическая роль: набор глобальных прав + доступ к конкретным воронкам/линиям."""
    name = models.CharField(max_length=120, unique=True)
    permissions = models.JSONField(default=list, help_text="Список кодов из PERMISSION_CHOICES")
    # доступ к конкретным воронкам и открытым линиям (по id), задаётся администратором
    funnels = models.ManyToManyField("crm.Funnel", blank=True, related_name="roles")
    # каналы (открытые линии) подключатся на этапе inbox; пока строкой-плейсхолдером
    open_lines = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name

    def has(self, code: str) -> bool:
        return code in (self.permissions or [])


class User(AbstractUser):
    role = models.ForeignKey(Role, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="members"
    )
    phone = models.CharField(max_length=32, blank=True)
    theme = models.JSONField(default=dict, blank=True, help_text="Персональные настройки фона/акцента")

    # --- помощники прав ---
    def has_perm_code(self, code: str) -> bool:
        if self.is_superuser:
            return True
        return bool(self.role and self.role.has(code))

    def can_see_all_leads(self) -> bool:
        return self.has_perm_code("lead.view.all")

    def can_see_all_deals(self) -> bool:
        return self.has_perm_code("deal.view.all")

    def can_see_all_conversations(self) -> bool:
        return self.has_perm_code("conversation.view.all")

    def can_see_all_clients(self) -> bool:
        # клієнтів бачить керівник (хто бачить усі сделки) або хто має явне право
        return self.has_perm_code("contact.view.all") or self.can_see_all_deals()

    def allowed_funnel_ids(self):
        """None = все воронки (нет ограничения); иначе — список разрешённых id.

        Пустой набор воронок у роли трактуем как «ограничение не задано» = все
        воронки (стандартная практика CRM: админ ограничивает явно, добавляя
        нужные воронки в роль)."""
        if self.is_superuser or not self.role:
            return None
        ids = list(self.role.funnels.values_list("id", flat=True))
        return ids or None

    def allowed_channel_ids(self):
        """Доступ к открытым линиям. None = все; иначе список id из role.open_lines.
        Пусто = ограничение не задано (все линии)."""
        if self.is_superuser or not self.role:
            return None
        ids = self.role.open_lines or []
        return ids or None
