from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.accounts.models import Role, Department
from apps.crm.models import Funnel, Stage, Contact, Lead, Deal

User = get_user_model()

LEAD_STAGES = [
    ("Лід отриманий", "#f5b301"), ("Взято в роботу", "#f5b301"),
    ("Контакт встановлений", "#a3d039"), ("Кваліфікований", "#a3d039"),
    ("Підбір рішення", "#a3d039"), ("Не вдалося зв.", "#ef4444"),
]
DEAL_STAGES = [
    ("Дані для розрахунку", "#3b82f6"), ("Розрахунок", "#6366f1"),
    ("Домовились про оплату", "#8b5cf6"), ("Оплата отримана", "#f59e0b"),
    ("Відвантаження", "#10b981"), ("Завершити", "#16a34a"),
]


class Command(BaseCommand):
    help = "Заполняет демо-данными (роли, воронки, лиды) для проверки прав."

    def handle(self, *args, **opts):
        # роли
        admin_role, _ = Role.objects.get_or_create(
            name="Администратор",
            defaults={"permissions": ["lead.view.all", "deal.view.all", "finance.view",
                                      "warehouse.view", "telephony.view", "roles.manage"]})
        head_role, _ = Role.objects.get_or_create(
            name="Руководитель отдела",
            defaults={"permissions": ["lead.view.all", "deal.view.all", "telephony.view"]})
        mgr_role, _ = Role.objects.get_or_create(
            name="Менеджер",
            defaults={"permissions": ["lead.view.own", "deal.view.own", "telephony.view"]})

        dept, _ = Department.objects.get_or_create(name="Отдел продаж")

        head = self._user("head", "Олег", "Руководитель", head_role, dept)
        m1 = self._user("ilona", "Илона", "Ковальчук", mgr_role, dept)
        m2 = self._user("kirill", "Кирилл", "Оксаненко", mgr_role, dept)

        # воронки
        lead_f = self._funnel("Лиды", is_lead=True, order=0, stages=LEAD_STAGES)
        f21 = self._funnel("21 · Основний продукт", order=1, stages=DEAL_STAGES)
        f22 = self._funnel("22 · Тестовий набір", order=2, stages=DEAL_STAGES[:4])

        # роль менеджера видит только воронку 21 (для проверки ограничения)
        mgr_role.funnels.set([lead_f, f21])

        # демо-лиды на двух менеджеров
        if not Lead.objects.exists():
            names = [("Vladlena", "Sergeevna"), ("Христя", "Гродзевич"),
                     ("Світлана", "Родич"), ("Anna", "Кошова")]
            stage = lead_f.stages.first()
            for i, (fn, ln) in enumerate(names):
                c = Contact.objects.create(first_name=fn, last_name=ln,
                                           phone=f"+38067{i}{i}{i}0000", channels=["instagram"])
                Lead.objects.create(title=f"{fn} {ln} — Покриття для стін", contact=c,
                                    funnel=lead_f, stage=stage, source="instagram",
                                    owner=m1 if i % 2 == 0 else m2)
            Deal.objects.create(title="Угода #52059", funnel=f21,
                                stage=f21.stages.first(), owner=m2, amount=4820)

        self.stdout.write(self.style.SUCCESS(
            "Демо-данные готовы. Логины: head/ilona/kirill, пароль 'demo12345'. "
            "Менеджер видит только свои лиды и только воронку 21."))

    def _user(self, username, fn, ln, role, dept):
        u, created = User.objects.get_or_create(
            username=username, defaults={"first_name": fn, "last_name": ln,
                                         "role": role, "department": dept})
        if created:
            u.set_password("demo12345")
            u.save()
        return u

    def _funnel(self, name, order, stages, is_lead=False):
        f, created = Funnel.objects.get_or_create(
            name=name, defaults={"is_lead_funnel": is_lead, "order": order})
        if created:
            for i, (sn, color) in enumerate(stages):
                Stage.objects.create(funnel=f, name=sn, color=color, order=i)
        return f
