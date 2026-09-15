"""Перерахувати бали «Розвитку» за НОВИМИ правилами (Розвиток v2, 16.09.2026). За замовчуванням — DRY (нічого не пише).

    python manage.py gamify_rules_v2                      # DRY: що буде по кожній людині (було → стане)
    python manage.py gamify_rules_v2 --since 2026-05-01   # DRY з іншої дати
    python manage.py gamify_rules_v2 --live               # записати (1 транзакція)
    python manage.py gamify_rules_v2 --restore --live     # відкат: повернути старі бали з архіву

Що робить --live:
  1. Старі бали (60 за виграну угоду, сума/1000; розбори чатів «вручну») → archived=True. Нічого не видаляється:
     рядки лишаються, --restore повертає їх як було.
  2. Бали за новими правилами (rules.collect) з --since по сьогодні — з датою події (у свій місяць).
  3. Розбори дзвінків без балів — бали (як сигнал розбору).
  4. Розбори дзвінків, де АТС знає оператора (call.manager / внутрішній номер) і він не той, кому зараховано, —
     переносимо на того, хто говорив (DialogAnalysis.manager і бал цього розбору). Станом на 16.09 таких 0:
     АТС не передає оператора.
  5. Перерахунок ManagerLevel.
Гроші, ЗП, угоди, оплати — не чіпаються.
"""
from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.crm.models import DialogAnalysis
from apps.gamification import rules
from apps.gamification.models import XPEvent
from apps.gamification.xp import OLD_KINDS, award_for_analysis, recompute_level


def _manual_chat_quality():
    """Бали за розбори чатів «вручну» (не з вибірки) — за новими правилами не рахуються."""
    chat_ids = {str(i) for i in DialogAnalysis.objects.filter(kind="chat").values_list("id", flat=True)}
    qs = XPEvent.objects.filter(kind="quality", ref_type="analysis", ref_id__in=chat_ids)
    # не .exclude(meta__sample=True): у SQL рядки без ключа sample дають NULL і теж випали б
    ids = [e.id for e in qs.only("id", "meta") if not (e.meta or {}).get("sample")]
    return XPEvent.objects.filter(id__in=ids)


def _recredit_candidates():
    from apps.telephony.models import Call
    out = []
    for da in DialogAnalysis.objects.filter(kind="call", deal__isnull=False).only("id", "deal_id", "created_at", "manager_id"):
        c = Call.objects.filter(deal_id=da.deal_id, started_at=da.created_at).first()
        sp = rules.speaker_of(c)
        if sp and sp != da.manager_id:
            out.append((da.id, da.manager_id, sp))
    return out


class Command(BaseCommand):
    help = "Бали «Розвитку» за новими правилами: DRY за замовчуванням, --live — записати, --restore — відкат архіву."

    def add_arguments(self, parser):
        parser.add_argument("--since", default="2026-05-01", help="з якої дати рахувати нові бали (РРРР-ММ-ДД)")
        parser.add_argument("--live", action="store_true", help="записати (інакше DRY)")
        parser.add_argument("--restore", action="store_true", help="відкат: зняти archived зі старих балів")

    def handle(self, *a, **o):
        live = o["live"]
        try:
            since = date.fromisoformat(o["since"])
        except ValueError:
            raise CommandError("--since у форматі РРРР-ММ-ДД")
        today = timezone.localdate()
        w = self.stdout.write
        if o["restore"]:
            qs = XPEvent.objects.filter(archived=True)
            w(f"Відкат: у архіві {qs.count()} рядків балів ({sum(qs.values_list('xp', flat=True))} балів).")
            if live:
                with transaction.atomic():
                    mids = set(qs.values_list("manager_id", flat=True))
                    n = qs.update(archived=False)
                    for mid in mids:
                        recompute_level(mid)
                w(f"LIVE: повернуто {n} рядків. Нові бали не видалялись.")
            else:
                w("DRY: нічого не змінено. Додайте --live, щоб повернути.")
            return

        old = XPEvent.objects.filter(kind__in=OLD_KINDS, archived=False)
        chat = _manual_chat_quality().filter(archived=False)
        events = rules.collect(since, today)
        res = rules.apply(events, live=False)
        pending = rules.quality_pending(since, today)
        recredit = _recredit_candidates()

        before = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for mid, kind, xp in XPEvent.objects.filter(archived=False).values_list("manager_id", "kind", "xp"):
            r = before[mid][kind]
            r[0] += 1
            r[1] += xp
        old_by = defaultdict(lambda: [0, 0])
        for mid, xp in list(old.values_list("manager_id", "xp")) + list(chat.values_list("manager_id", "xp")):
            old_by[mid][0] += 1
            old_by[mid][1] += xp
        new_by = rules.summarize(res["new"])
        for da in pending:
            r = new_by[da.manager_id]["quality"]
            r[0] += 1
        w(f"=== Розвиток v2: бали за новими правилами з {since} по {today} ({'LIVE' if live else 'DRY — нічого не пишу'}) ===")
        for mid in sorted(set(before) | set(new_by), key=lambda x: (x is None, x)):
            was = sum(v[1] for v in before[mid].values())
            arch = old_by[mid][1]
            add = sum(v[1] for v in new_by[mid].values())
            w(f"людина {mid}: було {was} балів; в архів {old_by[mid][0]} рядків ({arch} б.); нових {add} б. → стане {was - arch + add}")
            for k, v in sorted(new_by[mid].items()):
                w(f"    + {rules.KIND_LABELS.get(k, k)}: {v[0]} шт., {v[1]} б." + (" (розбори без балів — бал рахує сигнал)" if k == "quality" else ""))
        w(f"Разом: в архів {old.count()} старих рядків за угоди + {chat.count()} розборів чатів «вручну»; "
          f"нових подій {len(res['new'])} (вже були {res['skipped']}); розборів дзвінків без балів {len(pending)}; "
          f"перенести на того, хто говорив: {len(recredit)}")
        for x in recredit[:20]:
            w(f"    розбір #{x[0]}: {x[1]} → {x[2]}")
        if not live:
            w("DRY: нічого не змінено. Перевірте цифри; щоб записати — додайте --live.")
            return
        with transaction.atomic():
            touched = set(old.values_list("manager_id", flat=True)) | set(chat.values_list("manager_id", flat=True))
            n_old = old.update(archived=True)
            n_chat = chat.update(archived=True)
            rules.apply(events, live=True)
            for da in pending:
                award_for_analysis(da)
            for da_id, was, sp in recredit:
                DialogAnalysis.objects.filter(pk=da_id).update(manager_id=sp)
                for ev in XPEvent.objects.filter(kind="quality", ref_type="analysis", ref_id=str(da_id)):
                    ev.manager_id = sp
                    ev.meta = {**(ev.meta or {}), "credit": "speaker", "was": was}
                    ev.save(update_fields=["manager_id", "meta"])
                touched |= {was, sp}
            touched |= {e["manager_id"] for e in res["new"]} | {da.manager_id for da in pending}
            for mid in touched:
                if mid:
                    recompute_level(mid)
        w(f"LIVE: в архів {n_old} + {n_chat}; нових подій {len(res['new'])}; розборів {len(pending)}; перенесено {len(recredit)}.")
