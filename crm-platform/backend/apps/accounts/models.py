from django.contrib.auth.models import AbstractUser
from django.db import models


# Каталог прав. Администратор/руководитель собирает из них роли и права отделов.
PERMISSION_GROUPS = [
    ("Ліди", [
        ("lead.view.all", "Бачити ВСІ ліди", "Інакше — лише свої ліди"),
        ("lead.edit.all", "Редагувати та призначати будь-які ліди", ""),
        ("lead.delete", "Видаляти ліди", ""),
    ]),
    ("Сделки", [
        ("deal.view.all", "Бачити ВСІ сделки", "Інакше — лише свої сделки"),
        ("deal.edit.all", "Редагувати будь-які сделки", ""),
        ("deal.stage.move.all", "Рухати стадії чужих сделок", ""),
        ("deal.delete", "Видаляти сделки", ""),
    ]),
    ("Клієнти", [
        ("contact.view.all", "Бачити всіх клієнтів", "Інакше — лише своїх"),
        ("contact.edit.all", "Редагувати клієнтів", ""),
        ("contact.export", "Експорт бази клієнтів", ""),
        ("contact.delete", "Видаляти клієнтів", "Менеджер без цього права не може видалити клієнта"),
        ("contact.fields.config", "Налаштування обовʼязкових полів клієнта", "Хто бачить і змінює ⚙ обовʼязкові поля у картці"),
    ]),
    ("Чати / Відкриті лінії", [
        ("conversation.view.all", "Бачити ВСІ чати (командна черга)", "Інакше — лише свої чати"),
        ("conversation.assign", "Переадресовувати та призначати чати", ""),
    ]),
    ("Телефонія", [
        ("telephony.view", "Доступ до телефонії (дзвонити)", ""),
        ("telephony.view.all", "Бачити дзвінки всіх", "Інакше — лише свої"),
        ("telephony.recordings", "Слухати записи дзвінків", ""),
    ]),
    ("Аналітика і якість", [
        ("analytics.view", "Доступ до аналітики продажів", ""),
        ("development.view", "Бачити розділ «Розвиток» (дашборд розвитку менеджера)", ""),
        ("analytics.warehouse", "Аналітика складу (залишки)", ""),
        ("coaching.view.all", "Бачити якість/коучинг команди (РОП)", "Інакше — лише свій"),
    ]),
    ("Фінанси", [
        ("finance.view", "Доступ до фінансів", ""),
        ("finance.manage", "Керування фінмоделлю (ТБ/P&L)", ""),
    ]),
    ("Склад", [
        ("warehouse.view", "Доступ до складу", ""),
        ("warehouse.view.all", "Бачити задачі ВСІХ складовщиків (керівник)", "Інакше — лише свої задачі"),
        ("warehouse.edit", "Редагувати склад", ""),
        ("product.cost.view", "Бачити собівартість (закупівельні ціни)", ""),
    ]),
    ("Платежі і документи", [
        ("payment.process", "Проводити оплати / чеки / ТТН", ""),
        ("payment.refund", "Повернення та скасування платежів", ""),
    ]),
    ("Налаштування (делегування)", [
        ("settings.sounds", "Звуки сповіщень (особисті)", "Співробітник сам вмикає та обирає звук нових повідомлень і вхідних дзвінків"),
        ("settings.integrations", "Інтеграції та мова", "LiqPay / Checkbox / Нова Пошта / мова інтерфейсу"),
        ("settings.agent", "AI-агент (модель, автономність, витрати)", ""),
        ("settings.automations", "Автоматизації (правила стадій)", ""),
        ("settings.rules", "Глобальні правила бізнесу", ""),
        ("settings.sounds.upload", "Завантаження власних звуків (спільна бібліотека)", "Хто може додавати нові звуки у спільну бібліотеку; вибирати наявні звуки можуть усі з доступом до Звуків"),
    ]),
    ("Адміністрування", [
        ("automation.manage", "Керування автоматизаціями і правилами", ""),
        ("roles.manage", "Керування ролями і співробітниками", ""),
    ]),
]

PERMISSION_CHOICES = [(c, l) for _g, _it in PERMISSION_GROUPS for c, l, _h in _it]
LEGACY_PERMISSIONS = ["lead.view.own", "deal.view.own", "conversation.view.own"]


class Department(models.Model):
    """Отдел Wallcov. Дерево (parent) + права отдела (наследуются всеми сотрудниками)."""
    name = models.CharField(max_length=120)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    head = models.ForeignKey(
        "User", null=True, blank=True, on_delete=models.SET_NULL, related_name="headed_departments"
    )
    permissions = models.JSONField(default=list, blank=True, help_text="Права отдела (коды), действуют на всех членов")
    funnels = models.ManyToManyField("crm.Funnel", blank=True, related_name="departments")
    open_lines = models.JSONField(default=list, blank=True)
    color = models.CharField(max_length=9, blank=True)
    pos_x = models.FloatField(default=0)      # координаты узла на интеллект-карте
    pos_y = models.FloatField(default=0)
    sort = models.IntegerField(default=0)
    stage_view_all = models.JSONField(default=list, blank=True, help_text="ID стадій, де бачать ВСІ картки")
    stage_lock = models.JSONField(default=list, blank=True, help_text="ID стадій, куди ЗАБОРОНЕНО ручне переміщення")

    class Meta:
        ordering = ["sort", "name"]

    def __str__(self):
        return self.name

    def ancestors_incl_self(self):
        node, chain, seen = self, [], set()
        while node and node.id not in seen:
            seen.add(node.id); chain.append(node); node = node.parent
        return list(reversed(chain))

    def eff_permissions(self):
        codes = set()
        for d in self.ancestors_incl_self():
            codes |= set(d.permissions or [])
        return codes

    def eff_funnel_ids(self):
        ids = set()
        for d in self.ancestors_incl_self():
            ids |= set(d.funnels.values_list("id", flat=True))
        return ids

    def eff_open_lines(self):
        ids = set()
        for d in self.ancestors_incl_self():
            ids |= set(d.open_lines or [])
        return ids

    def eff_stage_view_all(self):
        ids = set()
        for d in self.ancestors_incl_self():
            ids |= set(d.stage_view_all or [])
        return ids

    def eff_stage_lock(self):
        ids = set()
        for d in self.ancestors_incl_self():
            ids |= set(d.stage_lock or [])
        return ids


class Role(models.Model):
    """Динамическая роль-пресет: набор прав + доступ к воронкам/линиям."""
    name = models.CharField(max_length=120, unique=True)
    permissions = models.JSONField(default=list, help_text="Список кодов из PERMISSION_CHOICES")
    funnels = models.ManyToManyField("crm.Funnel", blank=True, related_name="roles")
    open_lines = models.JSONField(default=list, blank=True)
    stage_view_all = models.JSONField(default=list, blank=True)
    stage_lock = models.JSONField(default=list, blank=True)

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
    extension = models.CharField(max_length=16, blank=True, help_text="внутрішній номер у АТС, напр. 789")
    theme = models.JSONField(default=dict, blank=True, help_text="Персональные настройки фона/акцента")
    # Индивидуальные права (поверх отдела/роли)
    extra_permissions = models.JSONField(default=list, blank=True, help_text="Персонально выданные права")
    denied_permissions = models.JSONField(default=list, blank=True, help_text="Персонально запрещённые (приоритет над всем)")
    extra_funnels = models.ManyToManyField("crm.Funnel", blank=True, related_name="extra_users")
    extra_open_lines = models.JSONField(default=list, blank=True)
    stage_view_all = models.JSONField(default=list, blank=True)
    stage_lock = models.JSONField(default=list, blank=True)

    # ── РЕЗОЛЮЦИЯ ПРАВ: отдел ∪ роль ∪ индивидуальные − запрещённые ──
    def effective_permissions(self) -> set:
        if self.is_superuser:
            return {c for c, _ in PERMISSION_CHOICES}
        codes = set()
        if self.department_id:
            codes |= self.department.eff_permissions()
        if self.role:
            codes |= set(self.role.permissions or [])
        codes |= set(self.extra_permissions or [])
        codes -= set(self.denied_permissions or [])      # запрет всегда побеждает
        return codes

    # --- помощники прав (сигнатуры НЕ менялись — весь RBAC работает) ---
    def has_perm_code(self, code: str) -> bool:
        if self.is_superuser:
            return True
        return code in self.effective_permissions()

    def can_see_all_leads(self) -> bool:
        return self.has_perm_code("lead.view.all")

    def can_see_all_deals(self) -> bool:
        return self.has_perm_code("deal.view.all")

    def can_see_all_conversations(self) -> bool:
        return self.has_perm_code("conversation.view.all")

    def can_see_all_clients(self) -> bool:
        return self.has_perm_code("contact.view.all") or self.can_see_all_deals()

    def allowed_funnel_ids(self):
        # None = бачить ВСЕ (тільки адмін/право). Порожній список = нічого (НЕ fail-open).
        if self.is_superuser or self.can_see_all_deals():
            return None
        ids = set()
        if self.department_id:
            ids |= self.department.eff_funnel_ids()
        if self.role:
            ids |= set(self.role.funnels.values_list("id", flat=True))
        ids |= set(self.extra_funnels.values_list("id", flat=True))
        return list(ids)

    def allowed_channel_ids(self):
        if self.is_superuser:
            return None
        ids = set()
        if self.department_id:
            ids |= self.department.eff_open_lines()
        if self.role:
            ids |= set(self.role.open_lines or [])
        ids |= set(self.extra_open_lines or [])
        return list(ids) or None

    # ── права на рівні СТАДІЙ воронки ──
    def viewable_all_stage_ids(self):
        """Стадії, де користувач бачить ВСІ картки (навіть чужі). None = всі стадії."""
        if self.is_superuser:
            return None
        ids = set()
        if self.department_id:
            ids |= self.department.eff_stage_view_all()
        if self.role:
            ids |= set(self.role.stage_view_all or [])
        ids |= set(self.stage_view_all or [])
        return ids

    def locked_move_stage_ids(self):
        """Стадії, куди ЗАБОРОНЕНО ручне переміщення картки."""
        if self.is_superuser or self.has_perm_code("roles.manage"):
            return set()
        ids = set()
        if self.department_id:
            ids |= self.department.eff_stage_lock()
        if self.role:
            ids |= set(self.role.stage_lock or [])
        ids |= set(self.stage_lock or [])
        try:
            from apps.crm.models import Stage
            ids |= set(Stage.objects.filter(auto_only=True).values_list("id", flat=True))
        except Exception:
            pass
        return ids


class Invite(models.Model):
    """Приглашение сотрудника по почте: генерится ссылка + выбор отдела перед генерацией."""
    STATUS = [("pending", "Очікує"), ("accepted", "Прийнято"), ("revoked", "Відкликано"), ("expired", "Прострочено")]
    email = models.EmailField()
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="invites")
    role = models.ForeignKey(Role, null=True, blank=True, on_delete=models.SET_NULL)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("User", null=True, on_delete=models.SET_NULL, related_name="sent_invites")

    class Meta:
        ordering = ["-created_at"]
