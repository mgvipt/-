"""Перенести поточні ставки в «Налаштування → Ставки співробітників» (план v9, 14.09.2026).

За замовчуванням — лише показує (DRY). `--limit 2` — записати перші 2 схеми, `--live` — усі.
Повторний запуск нічого не дублює: схема шукається за (співробітник/посада, призначення, «діє з»). Існуюче НЕ оновлює.
Цифри: рішення Олега 11–14.09 (нова схема продажників, гарантія 15 000, 2% Ілоні з салону й актів обʼєктів),
ставки складу/SMM — із журналу виплат (позначені «перевірте»)."""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.payroll.engine import DEFAULT_POLICY, GUARANTEE_CONDITIONS
from apps.payroll.models import PayComponent, PayPolicy, PayRateLog, PayScheme

EVENT = {"kind": "event_bonus", "title": "Бонус «тест-набір → основне» 300 / 200 / 100 ₴",
         "params": {"tiers": {"fast_days": 30, "min_order": 3000, "fast": 300, "slow": 200, "small": 100}}}


def online(pct_to=10, pct_over=20):
    return {"kind": "margin_share", "title": f"{pct_to}% з маржі онлайн до плану, {pct_over}% понад план",
            "params": {"funnels": [15, 16], "pct_to_plan": pct_to, "pct_over_plan": pct_over, "gate_standard_min": 0.75}}


SEED = [
    # (username або None, дані схеми, компоненти)
    ("kirill", dict(position="Менеджер з продажу (онлайн)", department="Продажі", purpose="legacy",
                    title="Як платили до 31.08: 10% з оплат", valid_from=date(2026, 6, 1), employment="none",
                    note="Олег 10.09: 10% роздріб / 5% партнерські (партнерів у CRM ще немає)"),
     [{"kind": "revenue_share", "title": "10% з оплат по своїх угодах", "params": {"basis": "own_payments", "pct": 10}}]),
    ("kirill", dict(position="Менеджер з продажу (онлайн)", department="Продажі", purpose="official",
                    title="Нова схема з 01.09", valid_from=date(2026, 9, 1), employment="none",
                    options={"insurance_first_month": True},
                    note="Рішення 11.09: за вихід + стандарт + 10/20% маржі + бонус тест→основне. Перший місяць — страховочний"),
     [{"kind": "base_by_days", "title": "За вихід (по табелю)", "params": {"amount": 6000}},
      {"kind": "standard", "title": "Стандарт роботи (до 6 000 ₴)", "params": {"max": 6000}},
      online(), EVENT]),
    ("ilona", dict(position="Менеджер (салон, обʼєкти, онлайн)", department="Продажі", purpose="legacy",
                   title="Як платили до 31.08: ставка + 1,5% салон і обʼєкти", valid_from=date(2026, 6, 1), employment="none",
                   note="Олег 14.09: «салон і обʼєкти 1,5% рахується зараз, буде 2%». Звірити з виплатами (серпень виплачено 28 477)"),
     [{"kind": "base_by_days", "title": "Ставка (по табелю)", "params": {"amount": 15000}},
      {"kind": "revenue_share", "title": "1,5% з оплат салону", "params": {"basis": "funnels", "funnels": [5], "pct": 1.5, "own_only": False}},
      {"kind": "revenue_share", "title": "1,5% з приходів обʼєктів", "params": {"basis": "objects_income", "pct": 1.5}}]),
    ("ilona", dict(position="Менеджер (салон, обʼєкти, онлайн)", department="Продажі", purpose="official",
                   title="Нова схема з 01.09", valid_from=date(2026, 9, 1), employment="none",
                   options={"insurance_first_month": True},
                   note="Рішення 11–14.09: за вихід 7 000 + стандарт до 8 000 + 10/20% маржі онлайн + 2% салон + 2% від УСІЄЇ суми акту (акт закриває Олег)"),
     [{"kind": "base_by_days", "title": "За вихід (по табелю)", "params": {"amount": 7000}},
      {"kind": "standard", "title": "Стандарт: гроші по угодах, документи обʼєктів, склад, звірки (до 8 000 ₴)", "params": {"max": 8000}},
      online(),
      {"kind": "revenue_share", "title": "2% з оплат салону", "params": {"basis": "funnels", "funnels": [5], "pct": 2, "own_only": False}},
      {"kind": "revenue_share", "title": "2% від суми акту обʼєкта (при закритті)", "params": {"basis": "object_acts", "pct": 2}},
      EVENT]),
    ("zefir", dict(position="Менеджер з продажу (новачок)", department="Продажі", purpose="official",
                   title="Новачок: 2 місяці навчання з гарантією", valid_from=date(2026, 9, 14), employment="labor",
                   note="Вийшов 14.09. Гарантія 15 000 ₴ на 2 місяці — лише при виконанні умов (відмітка Олега щомісяця)"),
     [{"kind": "base_by_days", "title": "За вихід (по табелю)", "params": {"amount": 6000}},
      {"kind": "standard", "title": "Стандарт роботи (до 6 000 ₴)", "params": {"max": 6000}},
      online(), EVENT,
      {"kind": "guarantee", "title": "Гарантія новачку 15 000 ₴ × 2 міс.",
       "params": {"amount": 15000, "months": 2, "start": "2026-09-14", "conditions": GUARANTEE_CONDITIONS}}]),
    ("inna", dict(position="Комірник", department="Склад", purpose="official", title="Ставка + відрядно",
                  valid_from=date(2026, 7, 1), employment="none",
                  note="Ставка — з журналу (червень 8 000, липень 8 000 + 5 000, вересень 7 378) — ПЕРЕВІРТЕ"),
     [{"kind": "fixed_monthly", "title": "Ставка (перевірте суму)", "params": {"amount": 8000}},
      {"kind": "piece_rate", "title": "Відрядно: вага, пакування, тонування, день (ставки складу)", "params": {}}]),
    ("larionova", dict(position="Комірник", department="Склад", purpose="official", title="Ставка + відрядно",
                       valid_from=date(2026, 7, 1), employment="none",
                       note="Ставка — з журналу (липень 6 000, серпень 11 000, вересень 4 151) — ПЕРЕВІРТЕ"),
     [{"kind": "fixed_monthly", "title": "Ставка (перевірте суму)", "params": {"amount": 7000}},
      {"kind": "piece_rate", "title": "Відрядно: вага, пакування, тонування, день (ставки складу)", "params": {}}]),
    ("maria.k", dict(position="SMM (органіка)", department="Маркетинг", purpose="official", title="Фіксовано",
                     valid_from=date(2026, 6, 1), employment="none",
                     note="З журналу: червень 14 900, липень 3 500 — ПЕРЕВІРТЕ. Якщо її ЗП вже в статті фінмоделі «Маркетинг СММ» — приберіть звідти"),
     [{"kind": "fixed_monthly", "title": "Оплата SMM (перевірте суму)", "params": {"amount": 14000}}]),
    ("ratush.kris@gmail.com", dict(position="Таргетолог (реклама)", department="Маркетинг", purpose="official", title="Фіксовано",
                                   valid_from=date(2026, 8, 25), employment="none",
                                   note="Виплат у журналі немає — ВКАЖІТЬ суму"),
     [{"kind": "fixed_monthly", "title": "Оплата таргетолога (вкажіть суму)", "params": {"amount": 0}}]),
    (None, dict(position="Бухгалтер + прибирання", department="Офіс", purpose="official", title="Фіксовано",
                valid_from=date(2026, 6, 1), employment="none", note="З журналу січень–квітень ≈ 6 500 ₴ — перевірте"),
     [{"kind": "fixed_monthly", "title": "Бухгалтер + прибирання", "params": {"amount": 6500}}]),
    ("VACANCY", dict(position="Менеджер салону (Могилів-Подільський) — замість Ілони", department="Продажі", purpose="official",
                     title="Вакансія", valid_from=date(2026, 11, 1), employment="labor", is_vacancy=True, in_plan=False,
                     planned_start=date(2026, 11, 1), note="Приклад «що якщо»: увімкніть «врахувати», щоб побачити нову точку беззбитковості"),
     [{"kind": "base_by_days", "title": "За вихід (по табелю)", "params": {"amount": 7000}},
      {"kind": "standard", "title": "Стандарт роботи (до 8 000 ₴)", "params": {"max": 8000}},
      {"kind": "revenue_share", "title": "2% з оплат салону", "params": {"basis": "funnels", "funnels": [5], "pct": 2, "own_only": True}},
      {"kind": "guarantee", "title": "Гарантія новачку 15 000 ₴ × 2 міс.",
       "params": {"amount": 15000, "months": 2, "start": "2026-11-01", "conditions": GUARANTEE_CONDITIONS}}]),
]


class Command(BaseCommand):
    help = "Перенести ставки співробітників у єдине місце (DRY за замовчуванням; --limit N; --live)"

    def add_arguments(self, p):
        p.add_argument("--live", action="store_true")
        p.add_argument("--limit", type=int, default=0)

    def handle(self, *a, **o):
        live, limit = o["live"] or o["limit"] > 0, o["limit"]
        User = get_user_model()
        made = skipped = 0
        if not PayPolicy.objects.filter(pk=1).exists():
            self.stdout.write("policy: створити правила компанії (податки, 17% раз на квартал, гарантія 15 000 × 2 міс.)")
            if live:
                PayPolicy.objects.create(pk=1, params={"guarantee": DEFAULT_POLICY["guarantee"],
                                                       "replaced_articles": DEFAULT_POLICY["replaced_articles"]})
        for uname, data, comps in SEED:
            user = None
            if uname and uname != "VACANCY":
                user = User.objects.filter(username=uname).first()
                if not user:
                    self.stdout.write(f"skip: немає користувача {uname}")
                    skipped += 1
                    continue
            q = PayScheme.objects.filter(purpose=data["purpose"], valid_from=data["valid_from"])
            q = q.filter(user=user) if user else q.filter(user__isnull=True, position=data["position"])
            if q.exists():
                self.stdout.write(f"вже є: {data['position']} · {uname or '-'} · {data['purpose']} з {data['valid_from']}")
                skipped += 1
                continue
            fixed = sum(float(c["params"].get("amount") or c["params"].get("max") or 0)
                        for c in comps if c["kind"] in ("base_by_days", "fixed_monthly", "standard"))
            self.stdout.write(f"{'LIVE' if live else 'DRY'}: {data['position']} · {uname or '—'} · {data['purpose']} з {data['valid_from']} · "
                              f"{len(comps)} частин · тверда до {fixed:,.0f} ₴".replace(",", " "))
            if not live or (limit and made >= limit):
                continue
            with transaction.atomic():
                s = PayScheme.objects.create(user=user, **data)
                for i, c in enumerate(comps):
                    PayComponent.objects.create(scheme=s, kind=c["kind"], title=c["title"], params=c["params"], order=i)
                PayRateLog.objects.create(scheme=s, action="seed", after={"position": s.position, "components": comps},
                                          note="перенесено з рішень Олега і журналу виплат 14.09")
            made += 1
        self.stdout.write(f"MODE {'LIVE' if live else 'DRY'}: створено {made}, пропущено {skipped}")
