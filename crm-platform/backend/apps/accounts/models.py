from django.contrib.auth.models import AbstractUser
from django.db import models


# Каталог прав. Администратор/руководитель собирает из них роли и права отделов.
PERMISSION_GROUPS = [
    ("Ліди", [
        ("lead.view", "Доступ до розділу «Ліди»", "Вимкнути — вкладка «Ліди» зникне з меню зовсім"),
        ("lead.view.all", "Бачити ВСІ ліди", "Інакше — лише свої ліди"),
        ("lead.edit.all", "Редагувати та призначати будь-які ліди", ""),
        ("lead.delete", "Видаляти ліди", ""),
    ]),
    ("Сделки", [
        ("deal.view", "Доступ до розділу «Сделки»", "Вимкнути — вкладка «Сделки» зникне з меню зовсім"),
        ("deal.create", "Створювати сделки", ""),
        ("deal.view.all", "Бачити ВСІ сделки", "Інакше — лише свої сделки"),
        ("deal.edit.all", "Редагувати будь-які сделки", ""),
        ("deal.stage.move.all", "Рухати стадії чужих сделок", ""),
        ("deal.delete", "Видаляти сделки", ""),
        ("funnel.manage", "Налаштовувати воронки", "Створення/перейменування воронок, стадії, кольори, порядок, видалення. Менеджерам НЕ давати."),
    ]),
    ("Клієнти", [
        ("contact.view", "Доступ до розділу «Клієнти»", "Вимкнути — вкладка «Клієнти» зникне з меню зовсім"),
        ("contact.view.all", "Бачити всіх клієнтів", "Інакше — лише своїх"),
        ("contact.edit.all", "Редагувати клієнтів", ""),
        ("contact.export", "Експорт бази клієнтів", ""),
        ("contact.delete", "Видаляти клієнтів", "Менеджер без цього права не може видалити клієнта"),
        ("contact.fields.config", "Налаштування обовʼязкових полів клієнта", "Хто бачить і змінює ⚙ обовʼязкові поля у картці"),
        ("contact.kind.client", "Вкладка «Клієнти»", "Видима всім за замовчуванням. Щоб приховати вкладку Клієнти у співробітника — додайте цей код у його «Заборонені»"),
        ("contact.kind.supplier", "Вкладка «Постачальники»", "Прихована за замовчуванням. Закупівельні ціни та реквізити — відкривати лише відповідальним"),
        ("contact.kind.master", "Вкладка «Майстри»", "Прихована за замовчуванням — відкривати лише відповідальним"),
        ("contact.kind.staff", "Вкладка «Співробітники»", "Прихована за замовчуванням — відкривати лише відповідальним"),
        ("contact.kind.partner", "Вкладка «Партнери / Дизайнери»", "Прихована за замовчуванням — відкривати лише відповідальним"),
    ]),
    ("Чати / Відкриті лінії", [
        ("inbox.view", "Доступ до розділу «Чати / Відкриті лінії»", "Вимкнути — вкладка «Чати» зникне з меню зовсім"),
        ("conversation.view.all", "Бачити ВСІ чати (командна черга)", "Інакше — лише свої чати"),
        ("conversation.assign", "Переадресовувати та призначати чати", ""),
        ("deal.stage.move", "Пересувати сделки по стадіях вручну", "Без цього права стадію рухає лише автоматика (оплата, склад, ТТН)"),
        ("team.broadcast", "Писати ВСІМ у загальний чат співробітників", "Повідомлення зʼявиться на екрані кожного співробітника"),
        ("inbox.notify.unassigned", "Сповіщення про нові незакріплені чати", "Кому дзвенять чати БЕЗ відповідального. Закріплений чат дзвенить тільки тому, хто його взяв. Складу вимкнути."),
    ]),
    ("Телефонія", [
        ("telephony.view", "Доступ до телефонії (дзвонити)", ""),
        ("telephony.view.all", "Бачити дзвінки ВСІХ", "Інакше — лише свої (свої = дзвонив сам, або дзвінок по його клієнту/сделці)"),
        ("telephony.calls", "Блок «Вхідні / Вихідні дзвінки»", "Журнал дзвінків і статистика на сторінці Телефонія"),
        ("telephony.balance", "Блок «Баланс ліній»", "Бачити баланси SIM-ліній (вписувати може лише адмін)"),
        ("telephony.queue", "Блок «Черга вхідних»", "Бачити і керувати чергою вхідних дзвінків"),
        ("telephony.recordings", "Слухати записи дзвінків", ""),
    ]),
    ("Аналітика і якість", [
        ("analytics.view", "Доступ до аналітики продажів", ""),
        ("marketing.view", "Доступ до маркетинг-аналітики (Meta)", "Реклама, окупність, органіка — окремо від аналітики продажів"),
        ("marketing.money", "Бачити гроші у маркетинг-аналітиці", "Виручка, прибуток, собівартість, LTV, ROAS/ROMI. Вимкнути — маркетолог бачить ліди/діалоги/продажі у штуках і витрати на рекламу, але не бачить виручку і прибуток"),
        ("marketing.section.overview", "Маркетинг: зведений огляд (усі канали)", "Розділ для власника: всі канали разом. Якщо у людини немає ЖОДНОГО розділу маркетингу — вона бачить усі (як раніше)"),
        ("marketing.section.meta", "Маркетинг: розділ Meta (соцмережі)", "Реклама Instagram/Facebook, креативи, органіка"),
        ("marketing.section.site", "Маркетинг: розділ Сайт · Google", "Лендінги, події пікселя, Google Analytics"),
        ("marketing.section.offline", "Маркетинг: розділ Офлайн (салон)", "Воронки «Покриття для стін» і «Алмазне + Вентиляція»"),
        ("development.view", "Бачити розділ «Розвиток» (дашборд розвитку менеджера)", ""),
        ("changelog.view", "Бачити вкладку «Що нового» (історія змін CRM)", ""),
        ("analytics.warehouse", "Аналітика складу (залишки)", ""),
        ("coaching.view.all", "Бачити якість/коучинг команди (РОП)", "Інакше — лише свій"),
    ]),
    ("Фінанси · вкладки", [
        ("finance.tab.journal", "Журнал", ""),
        ("finance.tab.triage", "Разноска (уборка категорий)", "Масова розноска операцій зі сміттєвих категорій"),
        ("finance.tab.pnl", "Звіт P&L (ATM)", ""),
        ("finance.tab.be", "Точка беззбитковості", ""),
        ("finance.tab.dir", "Напрямки (проекти)", ""),
        ("finance.tab.plan", "Планування", ""),
        ("finance.tab.debts", "Дт/Кт (кредиторка/дебіторка)", ""),
        ("finance.tab.grow", "Зростання", ""),
        ("finance.tab.salary", "ЗП/KPI", ""),
        ("finance.tab.mplan", "Плани", ""),
        ("finance.tab.time", "Табель", ""),
        ("finance.tab.ref", "Довідники", ""),
        ("finance.tab.model", "Фінмодель", ""),
    ]),
    ("Фінанси · дії", [
        ("finance.tx.edit", "Редагувати операції журналу", "Без цього — тільки перегляд (дохід/витрата/переказ/правка/видалення заблоковані)"),
        ("finance.balance.total", "Бачити ЗАГАЛЬНИЙ баланс (Σ над рахунками)", ""),
        ("finance.accounts.manage", "Рахунки: створювати/редагувати/видаляти", ""),
        ("finance.plan.accounts", "Планування: обирати рахунки «До розподілу»", "Клік по рахунку у Плануванні вмикає/вимикає його з розподілу — зміна ОДНА для всіх учасників"),
        ("finance.dirs.manage", "Напрямки: створювати/видаляти", ""),
        ("finance.ref.edit", "Довідники: редагувати (категорії/контрагенти/валюти/канали)", ""),
        ("finance.model.edit", "Фінмодель: редагувати", "Без цього — тільки перегляд"),
        ("finance.period.close", "Закривати період (бухгалтерія)", "Операції до закритої дати не редагуються ніким, крім власників цього права"),
        ("finance.debts.edit", "Дт/Кт: створювати/редагувати/видаляти", ""),
        ("finance.debts.pay", "Дт/Кт: відмічати «Оплачено»", ""),
    ]),
    ("Фінанси", [
        ("finance.view", "Доступ до фінансів", ""),
        ("finance.manage", "Керування фінмоделлю (ТБ/P&L)", ""),
    ]),
    ("Склад", [
        ("warehouse.view", "Доступ до складу", ""),
        ("warehouse.view.all", "Бачити задачі ВСІХ складовщиків (керівник)", "Інакше — лише свої задачі"),
        ("warehouse.edit", "Редагувати склад", ""),
        ("warehouse.reassign", "Передавати задачі складу (зміна виконавця)", "Хто може міняти відповідального за складську задачу"),
        ("warehouse.tab.realizations", "Вкладка «Реалізації»", "Список видаткових документів у Складському обліку"),
        ("warehouse.tab.receipts", "Вкладка «Прибуткові накладні»", ""),
        ("warehouse.tab.inventory", "Вкладка «Інвентаризація»", "Включно зі списаннями"),
        ("warehouse.inventory.void", "Скасування (сторно) інвентаризації", "Хто може відмінити проведену інвентаризацію — залишок відкочується, запис лишається в історії"),
        ("product.cost.view", "Бачити собівартість (закупівельні ціни)", ""),
        ("deal.price.refresh", "Оновлення роздрібних цін з номенклатури", "Хто бачить кнопку «Оновити ціни» — масово підтягнути свіжі роздрібні ціни у НЕоплачену сделку (сума перерахується)"),
        ("client.finance.full", "Картка клієнта: повні фінанси (прибуток/маржа/собівартість/знижки)", "Без права менеджер бачить у картці клієнта лише дохід і комісії — БЕЗ маржі, собівартості, прибутку і знижок. У самій сделці собівартість лишається за правом product.cost.view"),
    ]),
    ("Платежі і документи", [
        ("payment.process", "Проводити оплати / чеки / ТТН", ""),
        ("payment.refund", "Повернення та скасування платежів", ""),
    ]),
    ("Налаштування (делегування)", [
        ("settings.sounds", "Звуки сповіщень (особисті)", "Співробітник сам вмикає та обирає звук нових повідомлень і вхідних дзвінків"),
        ("settings.agent", "AI-агент (модель, автономність, витрати)", ""),
        ("settings.automations", "Автоматизації (правила стадій)", ""),
        ("settings.rules", "Глобальні правила бізнесу", ""),
        ("settings.sounds.upload", "Завантаження власних звуків (спільна бібліотека)", "Хто може додавати нові звуки у спільну бібліотеку; вибирати наявні звуки можуть усі з доступом до Звуків"),
    ]),
    ("Адміністрування", [
        ("automation.manage", "Керування автоматизаціями і правилами", ""),
        ("roles.manage", "Керування ролями і співробітниками", ""),
    ]),
    ("Додаток «Wallcov Замер»", [
        ("zamer.access", "Доступ до застосунку", "Може користуватися застосунком замера і відправляти замер у CRM. Без цього права застосунок заблоковано."),
        ("zamer.deal.create", "Створення угод із застосунку", "Може створювати нові угоди прямо із застосунку (кнопка «+»). Без права — лише вибір існуючих угод."),
        ("zamer.client.create", "Створення клієнтів із застосунку", "Може створювати нових клієнтів у застосунку. Без права — лише вибір існуючих."),
        ("calc.access", "Калькулятор кошторисів (у застосунку)", "Кнопка «Відкрити калькулятор» у мобільному застосунку замера."),
        ("calc.view.all", "Бачити всі кошториси", "Інакше співробітник бачить кошториси лише доступних йому клієнтів і угод."),
        ("calc.edit.all", "Редагувати всі кошториси", "Інакше можна змінювати лише власні кошториси або кошториси власних угод."),
        ("calc.settings.manage", "Налаштування калькулятора", "Адміністративні ставки, запас, округлення й правила. Можна делегувати відповідальному співробітнику."),
        ("deal.smeta.tab", "Вкладка «Смета» у картці угоди (CRM)", "Показувати вкладку «Смета» (вбудований калькулятор) у картці угоди в CRM. Окреме право — не всі користувачі застосунку є в CRM."),
    ]),
]

# ── Задачі (додано 2026-07-31) ──
PERMISSION_GROUPS.append((
    "Задачі",
    [
        ("task.view", "Доступ до розділу «Задачі»", "Вимкнути — вкладка «Задачі» зникне з меню зовсім"),
        ("task.view.others", "Бачити задачі інших співробітників",
         "Без цього права видно ТІЛЬКИ свої задачі (кнопки-фільтри «Всі», «Кирил», «Ілона» тощо приховуються). Дають керівникам."),
    ],
))

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
    fin_accounts = models.JSONField(default=list, blank=True, help_text="id рахунків; порожньо = всі")
    fin_cats_in = models.JSONField(default=list, blank=True)
    fin_cats_out = models.JSONField(default=list, blank=True)
    fin_dirs = models.JSONField(default=list, blank=True)
    fin_counterparties = models.JSONField(default=list, blank=True)
    open_lines = models.JSONField(default=list, blank=True)
    color = models.CharField(max_length=9, blank=True)
    pos_x = models.FloatField(default=0)      # координаты узла на интеллект-карте
    pos_y = models.FloatField(default=0)
    sort = models.IntegerField(default=0)
    stage_view_all = models.JSONField(default=list, blank=True, help_text="ID стадій, де бачать ВСІ картки")
    stage_lock = models.JSONField(default=list, blank=True, help_text="ID стадій, куди ЗАБОРОНЕНО ручне переміщення")
    idle_timeout_min = models.IntegerField(
        default=15,
        help_text="Хвилин простою (без активності) до авто-паузи зміни. 0 = контроль простою вимкнено (напр. Склад/Тонування — працюють руками).")

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
    fin_accounts = models.JSONField(default=list, blank=True)
    fin_cats_in = models.JSONField(default=list, blank=True)
    fin_cats_out = models.JSONField(default=list, blank=True)
    fin_dirs = models.JSONField(default=list, blank=True)
    fin_counterparties = models.JSONField(default=list, blank=True)
    open_lines = models.JSONField(default=list, blank=True)
    stage_view_all = models.JSONField(default=list, blank=True)
    stage_lock = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name

    def has(self, code: str) -> bool:
        return code in (self.permissions or [])


class User(AbstractUser):
    class AccountKind(models.TextChoices):
        CLIENT = "client", "Клієнт"
        STAFF = "staff", "Співробітник"

    # Backward compatible default: every account created by the existing CRM
    # staff/admin flows remains staff. The public registration endpoint always
    # overrides this with CLIENT and never accepts this field from the caller.
    account_kind = models.CharField(
        max_length=12,
        choices=AccountKind.choices,
        default=AccountKind.STAFF,
        db_index=True,
    )
    role = models.ForeignKey(Role, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="members"
    )
    phone = models.CharField(max_length=32, blank=True)
    extension = models.CharField(max_length=16, blank=True, help_text="внутрішній номер у АТС, напр. 789")
    theme = models.JSONField(default=dict, blank=True, help_text="Персональные настройки фона/акцента")
    # ── Статус занятости сотрудника (для аналитики и фильтров: активные / неактивные / уволенные) ──
    EMPLOYMENT_STATUS = [
        ("active", "Активний"),
        ("inactive", "Неактивний (тимчасово — відпустка/пауза, без доступу)"),
        ("dismissed", "Звільнений"),
    ]
    employment_status = models.CharField(
        max_length=12, choices=EMPLOYMENT_STATUS, default="active", db_index=True,
        help_text="Активний / Неактивний / Звільнений. Керує доступом (is_active) і фільтрами аналітики.")
    dismissed_at = models.DateField(null=True, blank=True, help_text="Дата звільнення (для розрахунку скільки пропрацював)")
    # Персональний поріг простою (хв до авто-паузи). None = брати з відділу; 0 = вимкнено особисто.
    idle_timeout_min = models.IntegerField(null=True, blank=True,
        help_text="Особистий поріг простою (хв). Порожньо = як у відділі; 0 = вимкнути для цього співробітника.")
    # ── Картка співробітника (особисті дані, заповнює сам або керівник) ──
    photo = models.TextField(blank=True, default="", help_text="Фото/лого — data URL (стиснене до 256px у браузері)")
    position = models.CharField(max_length=120, blank=True, default="", help_text="Посада (вільний текст, напр. «Старший менеджер»)")
    birthday = models.DateField(null=True, blank=True, help_text="День народження")
    about = models.TextField(blank=True, default="", help_text="Коротко про співробітника")
    interests = models.TextField(blank=True, default="", help_text="Інтереси, хобі (щоб краще знати команду)")
    telegram = models.CharField(max_length=64, blank=True, default="", help_text="Telegram (@nick)")
    # Индивидуальные права (поверх отдела/роли)
    extra_permissions = models.JSONField(default=list, blank=True, help_text="Персонально выданные права")
    denied_permissions = models.JSONField(default=list, blank=True, help_text="Персонально запрещённые (приоритет над всем)")
    extra_funnels = models.ManyToManyField("crm.Funnel", blank=True, related_name="extra_users")
    fin_accounts = models.JSONField(default=list, blank=True)
    fin_cats_in = models.JSONField(default=list, blank=True)
    fin_cats_out = models.JSONField(default=list, blank=True)
    fin_dirs = models.JSONField(default=list, blank=True)
    fin_counterparties = models.JSONField(default=list, blank=True)
    extra_open_lines = models.JSONField(default=list, blank=True)
    stage_view_all = models.JSONField(default=list, blank=True)
    stage_lock = models.JSONField(default=list, blank=True)

    def apply_employment_status(self, new_status, when=None):
        """Змінити статус занятості і синхронно доступ. active→доступ є; inactive/dismissed→доступу нема.
        dismissed фіксує дату звільнення; повернення на active/inactive її очищає."""
        from django.utils import timezone
        if new_status not in dict(self.EMPLOYMENT_STATUS):
            return
        self.employment_status = new_status
        self.is_active = (new_status == "active")
        if new_status == "dismissed":
            self.dismissed_at = when or timezone.localdate()
            self.is_superuser = False
        else:
            self.dismissed_at = None
        self.save(update_fields=["employment_status", "is_active", "dismissed_at", "is_superuser"])

    def effective_idle_timeout(self):
        """Скільки хв простою до авто-паузи. Особисте значення важливіше за відділ:
        персональне задано → воно; порожнє → з відділу; немає відділу → 15. 0 = вимкнено."""
        if self.idle_timeout_min is not None:
            return int(self.idle_timeout_min)
        dep = self.department
        try:
            return int(dep.idle_timeout_min) if dep else 15
        except Exception:
            return 15

    # ── РЕЗОЛЮЦИЯ ПРАВ: отдел ∪ роль ∪ индивидуальные − запрещённые ──
    def effective_permissions(self) -> set:
        # A public client account never inherits internal CRM permissions,
        # even if an administrator accidentally assigns it a role before the
        # explicit promotion action changes account_kind to STAFF.
        if self.account_kind == self.AccountKind.CLIENT:
            return set()
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
        if self.account_kind == self.AccountKind.CLIENT:
            return False
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

    def allowed_contact_kinds(self):
        """Які вкладки-сегменти контрагентів бачить користувач.
        None = ВСІ (лише суперадмін).
        Вкладка «Клієнти» — увімкнена всім за замовчуванням; зникає, якщо код
        contact.kind.client додано у «Заборонені» співробітнику.
        Постачальники / Майстри / Співробітники / Партнери — приховані за
        замовчуванням, видно лише тим, кому видали право на конкретну вкладку."""
        if self.is_superuser:
            return None
        ks = set()
        if "contact.kind.client" not in (self.denied_permissions or []):
            ks.add("client")
        for k in ("supplier", "master", "staff", "partner"):
            if self.has_perm_code("contact.kind." + k):
                ks.add(k)
        return ks

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

    def _fin_union(self, attr):
        vals = set()
        if self.department_id:
            for d in self.department.ancestors_incl_self():
                vals |= set(getattr(d, attr, None) or [])
        if self.role_id:
            vals |= set(getattr(self.role, attr, None) or [])
        vals |= set(getattr(self, attr, None) or [])
        return vals

    def allowed_fin(self, attr):
        """Пообʼєктний доступ у фінансах (рахунки/категорії/напрямки/контрагенти).
        None = обмежень нема (нічого не позначено ніде)."""
        if self.is_superuser:
            return None
        v = self._fin_union(attr)
        return None if not v else list(v)

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
    username = models.CharField(max_length=150, blank=True, default="", help_text="Бажаний логін; якщо порожньо — з пошти")
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="invites")
    role = models.ForeignKey(Role, null=True, blank=True, on_delete=models.SET_NULL)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("User", null=True, on_delete=models.SET_NULL, related_name="sent_invites")

    class Meta:
        ordering = ["-created_at"]
