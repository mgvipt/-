"""Воронка лендингу за зразком «Лендинг · wallcovdliastin.com.ua» (id 22).

Копіює стадії (назва, колір, порядок, успішна/провалена, «лише авто»), відділ,
доступи ролей і співробітників до воронки та «Права по статусах» (stage_view_all / stage_lock).
Без --apply нічого не записує — лише показує план. Повторний запуск нічого не дублює.

    python manage.py ensure_landing_funnels            # показати план (DRY)
    python manage.py ensure_landing_funnels --apply    # створити
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from apps.accounts.models import Department, Role, User
from apps.crm.models import Funnel, Stage
from apps.inbox.landing_intake import LANDING_ID, LANDINGS


def _remap(ids, mapping):
    ids = list(ids or [])
    extra = [mapping[i] for i in ids if i in mapping and mapping[i] not in ids]
    return ids + extra, extra


class Command(BaseCommand):
    help = "Створити воронку лендингу за зразком воронки wallcovdliastin (без --apply — лише план)"

    def add_arguments(self, parser):
        parser.add_argument("--landing", default="dekoratyvna-shtukaturka.com.ua")
        parser.add_argument("--apply", action="store_true", help="Записати (без прапорця — лише план)")

    def handle(self, *args, **opts):
        landing = opts["landing"]
        cfg = LANDINGS.get(landing)
        if not cfg or landing == LANDING_ID or "Лендинг" not in cfg["funnel"]:
            raise CommandError("Невідомий лендинг %r (див. LANDINGS в apps/inbox/landing_intake.py)" % landing)
        template = Funnel.objects.filter(name=LANDINGS[LANDING_ID]["funnel"]).first()
        if not template:
            raise CommandError("Немає воронки-зразка «%s»" % LANDINGS[LANDING_ID]["funnel"])
        apply = opts["apply"]
        w = self.stdout.write
        w("%s: воронка «%s» за зразком #%s «%s»" % ("LIVE" if apply else "DRY", cfg["funnel"], template.id, template.name))
        with transaction.atomic():
            funnel = Funnel.objects.filter(name=cfg["funnel"]).first()
            if funnel:
                w("  воронка вже є: #%s" % funnel.id)
            else:
                order = (Funnel.objects.aggregate(m=Max("order"))["m"] or 0) + 1
                funnel = Funnel.objects.create(name=cfg["funnel"], is_lead_funnel=template.is_lead_funnel,
                                               is_archive=False, order=order)
                w("  + воронка #%s (порядок %s)" % (funnel.id, order))
            mapping = {}
            for st in template.stages.order_by("order", "id"):
                new = funnel.stages.filter(name=st.name).first()
                if not new:
                    new = Stage.objects.create(funnel=funnel, name=st.name, color=st.color, order=st.order,
                                               is_won=st.is_won, is_lost=st.is_lost, auto_only=st.auto_only)
                    w("  + стадія %s «%s»%s" % (st.order, st.name,
                                                 " (успішна)" if st.is_won else " (провалена)" if st.is_lost else ""))
                mapping[st.id] = new.id
            for dept in template.departments.all():
                if not dept.funnels.filter(pk=funnel.pk).exists():
                    dept.funnels.add(funnel)
                    w("  + відділ «%s»: воронка" % dept.name)
            for role in Role.objects.filter(funnels=template):
                if not role.funnels.filter(pk=funnel.pk).exists():
                    role.funnels.add(funnel)
                    w("  + роль «%s»: доступ до воронки" % role.name)
            for user in User.objects.filter(extra_funnels=template):
                if not user.extra_funnels.filter(pk=funnel.pk).exists():
                    user.extra_funnels.add(funnel)
                    w("  + співробітник %s: доступ до воронки" % user.username)
            for model in (Department, Role, User):
                for obj in model.objects.all():
                    changed = []
                    for field in ("stage_view_all", "stage_lock"):
                        if not hasattr(obj, field):
                            continue
                        value, extra = _remap(getattr(obj, field), mapping)
                        if extra:
                            setattr(obj, field, value)
                            changed.append(field)
                            w("  + %s «%s»: %s += %s стадій" % (model.__name__, obj, field, len(extra)))
                    if changed:
                        obj.save(update_fields=changed)
            if apply:
                w("LIVE: готово, воронка #%s" % funnel.id)
            else:
                transaction.set_rollback(True)
                w("DRY: нічого не записано. Для запису запустіть з --apply.")
