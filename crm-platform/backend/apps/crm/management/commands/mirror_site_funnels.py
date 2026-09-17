"""Воронки сайтів — стадії як у робочих онлайн-воронках (17.09.2026, Олег).

Уся автоматика CRM шукає стадії ЗА НАЗВОЮ: оплата LiqPay → «Оплату отримано» (+ задача складу),
склад узяв задачу → «Відвантаження», ТТН → «НП_ТТН створена», статуси Нової Пошти → «НП_В дорозі» /
«НП_Прибув на відділення» / «Отримано», посилання на оплату → «Домовились про оплату».
У воронці лендингу стадії були інші («Подбор 3 вариантов», «Заказ оплачен»…), тому оплачена сделка
їхала на «Подбор 3 вариантов», склад задачу не отримував, НП стадії не рухала.

Команда робить стадії воронок сайтів ТАКИМИ Ж, як у «21 Основний продукт» (назви, порядок,
«лише авто», успішна/провалена, колір). Робочі воронки 21/22 НЕ змінюються — з них лише читаємо.
Сделки зі старих стадій переносяться за фактами: оплачено повністю → «Оплату отримано»
(і задача складу, якщо її ще нема), є посилання на оплату або часткова оплата → «Домовились про оплату»,
є товари → «Розрахунок здійснено (КП)», інакше → «Данні для розрахунку»; закриті — «Успішна угода» /
«НЕ АКТУАЛЬНО». Стадія переноситься без сигналів (Meta-події не створюються), у історії сделки — запис.

    python manage.py mirror_site_funnels                 # план (нічого не пише)
    python manage.py mirror_site_funnels --apply --limit 2
    python manage.py mirror_site_funnels --apply
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.crm.models import Deal, Funnel, Lead, Stage, log_activity

TEMPLATE_NAME = "21 Основний продукт"
TWIN_NAME = "22 Тестовий набір"
# Перша стадія магазину має свою назву (її шукає імпорт замовлень і Meta) — лишаємо як є.
FIRST_STAGE_ALIASES = {"Нове замовлення з сайту"}
PAID, AGREED, CALC, START = "Оплату отримано", "Домовились про оплату", "Розрахунок здійснено (КП)", "Данні для розрахунку"
WON, LOST = "Успішна угода", "НЕ АКТУАЛЬНО"


def site_funnels():
    return Funnel.objects.filter(Q(name__startswith="Лендинг ·") | Q(name__icontains="Інтернет-магазин")).order_by("id")


def _paid(deal):
    return sum((p.amount for p in deal.payments.all() if p.is_paid), Decimal("0"))


def target_for(deal, old_stage):
    """Нова стадія для сделки зі старої (невідомої робочим воронкам) стадії — за фактами."""
    if old_stage.is_won:
        return WON, "була успішна"
    if old_stage.is_lost:
        return LOST, "була закрита"
    paid, amount = _paid(deal), Decimal(deal.amount or 0)
    if amount > 0 and paid >= amount:
        return PAID, "оплачено %s ₴" % paid
    if paid > 0:
        return AGREED, "оплачено частково %s з %s ₴" % (paid, amount)
    if deal.pay_links.exists():
        return AGREED, "надіслано посилання на оплату"
    if deal.items.exists():
        return CALC, "є прорахунок (товари)"
    return START, "ще без прорахунку"


class Command(BaseCommand):
    help = "Стадії воронок сайтів — як у робочих онлайн-воронках (без --apply лише план)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--limit", type=int, default=0, help="перенести не більше N сделок (перевірка на 1–2)")
        parser.add_argument("--funnel", type=int, action="append", help="лише ці воронки (id)")

    def _carry_stage_rights(self, funnel, old_ids, new_ids, apply, w):
        """«Права по статусах» (бачити всі сделки на стадії / заборона ручного руху) на старих стадіях
        цієї воронки → ті самі права на всіх нових стадіях (напр. роль «Менеджер» бачить усі заявки лендингу)."""
        from apps.accounts.models import Department, Role, User
        old, live = set(old_ids), set(funnel.stages.values_list("id", flat=True)) if apply else set()
        if not old:
            return
        for model in (Role, Department, User):
            for obj in model.objects.all():
                upd = {}
                for fld in ("stage_view_all", "stage_lock"):
                    cur = list(getattr(obj, fld, None) or [])
                    if not set(cur) & old:
                        continue
                    add = [i for i in new_ids if i not in cur]
                    nv = cur + add
                    if apply:  # стадії, яких уже нема, прибираємо
                        nv = [i for i in nv if i in live or i not in old]
                    if nv != cur:
                        upd[fld] = nv
                        w("  права «%s» у %s «%s»: +%s нових стадій" % (fld, model.__name__, obj, len(add)))
                if upd and apply:
                    model.objects.filter(pk=obj.pk).update(**upd)

    def handle(self, *args, **o):
        apply, limit = o["apply"], o["limit"]
        w = self.stdout.write
        tpl = Funnel.objects.filter(name=TEMPLATE_NAME).first()
        if not tpl:
            raise CommandError("Немає воронки-зразка «%s»" % TEMPLATE_NAME)
        tpl_stages = list(tpl.stages.order_by("order", "id"))
        twin = Funnel.objects.filter(name=TWIN_NAME).first()
        if twin and [s.name for s in twin.stages.order_by("order", "id")] != [s.name for s in tpl_stages]:
            raise CommandError("Стадії «%s» і «%s» різняться — спершу звірити зразок" % (TEMPLATE_NAME, TWIN_NAME))
        names = [s.name for s in tpl_stages]
        for n in (PAID, AGREED, CALC, START, WON, LOST):
            if n not in names:
                raise CommandError("У зразку немає стадії «%s»" % n)
        funnels = site_funnels()
        if o.get("funnel"):
            funnels = funnels.filter(id__in=o["funnel"])
        moved_total = 0
        w("%s · зразок #%s «%s» (%s стадій)" % ("LIVE" if apply else "DRY", tpl.id, tpl.name, len(tpl_stages)))
        for f in funnels:
            if f.id in (tpl.id, getattr(twin, "id", None)):
                continue
            w("\n#%s «%s»" % (f.id, f.name))
            with transaction.atomic():
                cur = {s.name: s for s in f.stages.all()}
                alias_used = next((a for a in FIRST_STAGE_ALIASES if a in cur and names[0] not in cur), None)
                old_stages = [s for s in f.stages.order_by("order", "id") if s.name not in names and s.name != alias_used]
                old_ids = [s.id for s in old_stages]  # після delete() у обʼєкта id = None — запамʼятовуємо заздалегідь
                if apply:  # старі стадії — в кінець дошки, щоб їхній порядок не збігався з новими
                    for s in old_stages:
                        Stage.objects.filter(id=s.id).update(order=100 + s.order)
                new_by_name = {}
                for t in tpl_stages:
                    st = cur.get(t.name)
                    if st is None and t.order == 0 and alias_used:
                        st = cur[alias_used]
                    fields = dict(order=t.order, color=t.color, is_won=t.is_won, is_lost=t.is_lost, auto_only=t.auto_only)
                    if st is None:
                        w("  + стадія %2s «%s»" % (t.order, t.name))
                        if apply:
                            st = Stage.objects.create(funnel=f, name=t.name, **fields)
                    else:
                        diff = {k: v for k, v in fields.items() if getattr(st, k) != v}
                        if diff:
                            w("  ~ стадія «%s»: %s" % (st.name, ", ".join("%s→%s" % (k, v) for k, v in diff.items())))
                            if apply:
                                Stage.objects.filter(id=st.id).update(**diff)
                    new_by_name[t.name] = st
                for old in old_stages:
                    deals = list(Deal.objects.filter(stage=old).select_related("stage").order_by("id"))
                    if Lead.objects.filter(stage=old).exists():
                        w("  ! «%s»: є ліди — стадію не чіпаю" % old.name)
                        continue
                    for d in deals:
                        if limit and moved_total >= limit:
                            break
                        tname, why = target_for(d, old)
                        w("  #%s «%s» → «%s» (%s)" % (d.id, old.name, tname, why))
                        moved_total += 1
                        if not apply:
                            continue
                        st = new_by_name[tname]
                        Deal.objects.filter(id=d.id, stage=old).update(stage=st)
                        log_activity("deal", d.id, "Воронку сайту вирівняно",
                                     "%s → %s (%s)" % (old.name, st.name, why), None, "Автоматизація")
                        if tname == PAID:
                            from apps.warehouse.services import create_warehouse_job
                            d.refresh_from_db()
                            if d.items.exists() and create_warehouse_job(d):
                                w("     + задача складу")
                                log_activity("deal", d.id, "Задача складу", "створено: сделка оплачена, чекала з «%s»" % old.name,
                                             None, "Автоматизація")
                    left = Deal.objects.filter(stage=old).count() if apply else len(deals)
                    if apply and left == 0:
                        old.delete()
                        w("  − стадія «%s» (порожня)" % old.name)
                    elif not apply:
                        w("  − стадія «%s» буде видалена, коли сделки перенесено" % old.name)
                self._carry_stage_rights(f, old_ids, [s.id for s in new_by_name.values() if s is not None],
                                         apply, w)
                if apply and limit and moved_total >= limit:
                    w("  (ліміт %s — решту наступним запуском)" % limit)
        w("\nперенесено сделок: %s%s" % (moved_total, "" if apply else " (план)"))
