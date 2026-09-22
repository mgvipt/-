"""16.09.2026 Розвиток v2: бали лише за якість і результати, «ти проти себе», сезон, змагання через Біржу задач,
розбір — тому, хто говорив. Лише ізольована тестова БД; ШІ не викликається (замоканий)."""
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Department
from apps.bounty.models import TaskCategory, TaskClaim, TaskOffer
from apps.crm.models import Contact, Deal, DealItem, DialogAnalysis, Funnel, Stage
from apps.finance.models import Account, Transaction
from apps.gamification import rules
from apps.gamification import views as gv
from apps.gamification.models import GamSettings, XPEvent
from apps.gamification.season import season
from apps.payroll import engine
from apps.payroll.models import PayComponent, PayPolicy, PayScheme

HOST = "crm.wallcovdec.com.ua"


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        U = get_user_model()
        self.today = timezone.localdate()
        self.period = self.today.strftime("%Y-%m")
        self.owner = U.objects.create_superuser("rz-owner", "rzo@example.test", "x")
        dep = Department.objects.create(name="Відділ продажів")
        self.mgr = U.objects.create_user("rz-mgr", "rzm@example.test", "x", first_name="Тест", last_name="Менеджер", department=dep)
        self.mgr2 = U.objects.create_user("rz-mgr2", "rzm2@example.test", "x", first_name="Друга", last_name="Менеджерка", department=dep)
        self.main = Funnel.objects.create(name="21 Основний продукт")
        self.test = Funnel.objects.create(name="22 Тестовий набір")
        self.st_main = Stage.objects.create(funnel=self.main, name="КП", order=1)
        self.st_test = Stage.objects.create(funnel=self.test, name="Оплату отримано", order=3)
        PayPolicy.objects.update_or_create(pk=1, defaults={"params": {
            "replaced_articles": [],
            "margin_estimate_pct": {str(self.main.id): 50, str(self.test.id): 50},
            "funnels": {"online": [self.main.id, self.test.id], "test": [self.test.id], "main": [self.main.id],
                        "salon": [], "diamond": []}}})
        self.acc = Account.objects.create(name="Каса rz", kind="cash")
        self.rf = APIRequestFactory()
        self.n = 0

    def contact(self):
        self.n += 1
        return Contact.objects.create(first_name=f"Клієнт{self.n}", last_name="Тест")

    def pay(self, deal, amount, day):
        return Transaction.objects.create(direction="in", amount=Decimal(str(amount)), amount_uah=Decimal(str(amount)),
                                          date=day, deal=deal, account=self.acc)

    def conversion(self, owner, main_day, test_days_before=5, amount=8000, discount=0):
        c = self.contact()
        t = Deal.objects.create(title="Тест", funnel=self.test, stage=self.st_test, contact=c, amount=500, owner=owner)
        self.pay(t, 500, main_day - timedelta(days=test_days_before))
        m = Deal.objects.create(title="Основне", funnel=self.main, stage=self.st_main, contact=c, amount=amount, owner=owner)
        DealItem.objects.create(deal=m, custom_name="Шовк", quantity=Decimal("1"), price=Decimal(str(amount + discount)),
                                discount_amount=Decimal(str(discount)))
        self.pay(m, amount, main_day)
        return t, m

    def call(self, view, user, method="get", url="/x/", data=None, **kw):
        req = getattr(self.rf, method)(url, data or {}, format="json", HTTP_HOST=HOST) if method != "get" else self.rf.get(url, HTTP_HOST=HOST)
        force_authenticate(req, user=user)
        return view.as_view()(req, **kw)

    def analysis(self, user, score, kind="call", days_ago=0):
        da = DialogAnalysis.objects.create(manager=user, kind=kind, overall_score=score, scores={"вступ": score})
        when = timezone.now() - timedelta(days=days_ago)
        DialogAnalysis.objects.filter(pk=da.pk).update(created_at=when)
        XPEvent.objects.filter(ref_type="analysis", ref_id=str(da.pk)).update(created_at=when)
        return da


class RulesTests(_Base):
    def test_points_for_results_not_for_won_deal(self):
        day = self.today - timedelta(days=1)
        self.conversion(self.mgr, day)                   # тест → основне вчасно (30) + без знижки (10)
        self.conversion(self.mgr, day, discount=500)     # тест → основне (30), знижка — без балу
        won = Stage.objects.create(funnel=self.main, name="Успіх", order=9, is_won=True)
        big = Deal.objects.create(title="Велике без тесту", funnel=self.main, stage=won, contact=self.contact(), amount=50000, owner=self.mgr)
        DealItem.objects.create(deal=big, custom_name="Шовк", quantity=Decimal("1"), price=Decimal("55000"), discount_amount=Decimal("5000"))
        self.pay(big, 50000, day)
        out = StringIO()
        call_command("gamify_recompute", stdout=out)
        ev = XPEvent.objects.filter(manager=self.mgr)
        self.assertEqual(sorted(ev.values_list("kind", flat=True)), ["no_discount", "test_main", "test_main"])
        self.assertEqual(sum(ev.values_list("xp", flat=True)), 70)
        self.assertFalse(XPEvent.objects.filter(kind__in=["deal_won", "deal_check"]).exists())
        self.assertEqual({timezone.localtime(e.created_at).date() for e in ev}, {day})   # бал — у день оплати основного
        call_command("gamify_recompute", stdout=StringIO())                             # ідемпотентно
        self.assertEqual(XPEvent.objects.filter(manager=self.mgr).count(), 3)
        dry = StringIO()
        call_command("gamify_recompute", "--dry", stdout=dry)
        self.assertIn("нових=0", dry.getvalue())

    def test_points_follow_own_scheme_tiers(self):
        s = PayScheme.objects.create(user=self.mgr, position="Менеджер", department="Продажі",
                                     valid_from=self.today.replace(day=1) - timedelta(days=40), employment="none")
        PayComponent.objects.create(scheme=s, kind="event_bonus", params={"tiers": {"fast": 500, "slow": 200, "small": 100,
                                                                                   "fast_days": 30, "min_order": 3000}})
        self.conversion(self.mgr, self.today - timedelta(days=1))
        evs = [e for e in rules.collect(self.today - timedelta(days=5), self.today) if e["kind"] == "test_main"]
        self.assertEqual([e["xp"] for e in evs], [50])

    def test_old_kinds_excluded_and_v2_command_dry_live_restore(self):
        XPEvent.objects.create(manager=self.mgr, kind="deal_won", xp=60, ref_type="deal", ref_id="999")
        chat = DialogAnalysis.objects.create(manager=self.mgr, kind="chat", overall_score=70, scores={})
        self.assertFalse(XPEvent.objects.filter(ref_id=str(chat.id)).exists())          # чат «вручну» — без балу
        XPEvent.objects.create(manager=self.mgr, kind="quality", xp=35, ref_type="analysis", ref_id=str(chat.id))
        rows, total = rules.month_points(self.mgr.id, *engine.period_bounds(self.period))
        self.assertEqual(total, 35)                                                        # 60 за угоду не рахується
        self.conversion(self.mgr, self.today)
        out = StringIO()
        call_command("gamify_rules_v2", "--since", (self.today - timedelta(days=30)).isoformat(), stdout=out)
        self.assertIn("DRY", out.getvalue())
        self.assertEqual(XPEvent.objects.filter(archived=True).count(), 0)
        self.assertFalse(XPEvent.objects.filter(kind="test_main").exists())
        call_command("gamify_rules_v2", "--since", (self.today - timedelta(days=30)).isoformat(), "--live", stdout=StringIO())
        self.assertEqual(set(XPEvent.objects.filter(archived=True).values_list("kind", flat=True)), {"deal_won", "quality"})
        self.assertTrue(XPEvent.objects.filter(kind="test_main", manager=self.mgr).exists())
        rows, total = rules.month_points(self.mgr.id, *engine.period_bounds(self.period))
        self.assertEqual(total, 40)
        call_command("gamify_rules_v2", "--restore", "--live", stdout=StringIO())
        self.assertEqual(XPEvent.objects.filter(archived=True).count(), 0)


class CreditTests(_Base):
    TRANSCRIPT = "МЕНЕДЖЕР: Добрий день, мене звати Олена, чим можу допомогти?\nКЛІЄНТ: Хочу мокрий шовк у спальню, 20 метрів."
    AI = {"overall": 62, "scores": {"вступ": 80}, "strengths": "", "why_not_selling": "", "recommended_reply": "", "coaching": ""}

    def _transcribe(self, call):
        from apps.telephony.views import TranscribeView
        req = self.rf.post("/api/telephony/transcribe/", {"call_id": call.id, "transcript": self.TRANSCRIPT}, format="json",
                           HTTP_HOST=HOST, HTTP_X_TELEPHONY_TOKEN="tok")
        with override_settings(TELEPHONY_TOKEN="tok"), \
                mock.patch("apps.crm.sales_analyst.label_speakers", side_effect=lambda x: x), \
                mock.patch("apps.crm.sales_analyst.analyze_dialog", return_value=dict(self.AI)):
            return TranscribeView.as_view()(req)

    def test_call_credited_to_speaker_by_extension_else_owner(self):
        from apps.telephony.models import Call
        self.mgr2.extension = "702"
        self.mgr2.save(update_fields=["extension"])
        d = Deal.objects.create(title="d", funnel=self.main, stage=self.st_main, contact=self.contact(), amount=1000, owner=self.mgr)
        c1 = Call.objects.create(direction="in", deal=d, extension="702", duration=60, started_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(self._transcribe(c1).status_code, 200)
        da = DialogAnalysis.objects.filter(kind="call").order_by("-id").first()
        self.assertEqual(da.manager_id, self.mgr2.id)
        self.assertEqual(XPEvent.objects.get(ref_type="analysis", ref_id=str(da.id)).meta["credit"], "speaker")
        c2 = Call.objects.create(direction="in", deal=d, extension="", duration=60, started_at=timezone.now() - timedelta(hours=2))
        self._transcribe(c2)
        da2 = DialogAnalysis.objects.filter(kind="call").order_by("-id").first()
        self.assertEqual(da2.manager_id, self.mgr.id)
        self.assertEqual(XPEvent.objects.get(ref_type="analysis", ref_id=str(da2.id)).meta["credit"], "owner")
        q = self.call(gv.MeView, self.mgr).data["quality"]
        self.assertEqual((q["n"], q["credit"]["owner"]), (1, 1))
        self.assertIn("відповідальному", q["credit_note"])

    def test_quality_is_calls_plus_sample_only(self):
        self.analysis(self.mgr, 40)
        DialogAnalysis.objects.create(manager=self.mgr, kind="chat", overall_score=90, scores={})   # «вручну» — не рахується
        self.assertEqual(gv.quality_qs(self.mgr.id).count(), 1)
        self.assertEqual(gv.quality_label(), "Якість дзвінків")
        s = GamSettings.get()
        s.chat_sampling = True
        s.save()
        da = DialogAnalysis(manager=self.mgr, kind="chat", overall_score=70, scores={})
        da._rzv_credit = "sample"
        da.save()
        self.assertEqual(gv.quality_qs(self.mgr.id).count(), 2)
        self.assertIn("вибірка", gv.quality_label())


class ApiTests(_Base):
    def test_team_comparison_only_for_owner(self):
        self.assertEqual(self.call(gv.LeaderboardView, self.mgr).status_code, 403)
        r = self.call(gv.LeaderboardView, self.owner)
        self.assertEqual(r.status_code, 200)
        self.assertEqual({m["id"] for m in r.data["managers"]}, {self.mgr.id, self.mgr2.id})
        self.assertEqual(self.call(gv.ManagerView, self.mgr, pk=self.mgr2.id).status_code, 403)
        self.assertEqual(self.call(gv.ManagerView, self.mgr, pk=self.mgr.id).status_code, 200)
        self.assertEqual(self.call(gv.ManagerView, self.owner, pk=self.mgr.id).status_code, 200)

    def test_me_calendar_month_vs_last_month_and_record(self):
        prev = engine.add_months(self.today.replace(day=1), -1)
        e1 = XPEvent.objects.create(manager=self.mgr, kind="test_main", xp=30, ref_type="deal", ref_id="1")
        XPEvent.objects.filter(pk=e1.pk).update(created_at=timezone.make_aware(datetime(prev.year, prev.month, 15, 12)))
        XPEvent.objects.create(manager=self.mgr, kind="test_main", xp=50, ref_type="deal", ref_id="2")
        d = self.call(gv.MeView, self.mgr).data
        self.assertEqual(d["period"], self.period)
        self.assertEqual(len(d["periods"]), 2)
        p = d["points"]
        self.assertEqual((p["total"], p["prev_total"], p["delta"]), (50, 30, 20))
        self.assertEqual(p["record"]["total"], 50)
        self.assertIn("50", p["explain"])
        d2 = self.call(gv.MeView, self.mgr, url=f"/api/gamification/me/?period={prev:%Y-%m}")
        self.assertEqual(d2.data["points"]["total"], 30)
        self.assertNotIn("leaderboard", d)

    def test_practice_marks_persist_per_user_and_week(self):
        r = self.call(gv.PracticeView, self.mgr, "post", data={"key": "вступ:0", "done": True, "text": "справа"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.call(gv.PracticeView, self.mgr).data["marks"], {"вступ:0": True})
        self.assertEqual(self.call(gv.PracticeView, self.mgr2).data["marks"], {})

    def test_settings_owner_only_and_chat_sampling_off_by_default(self):
        self.assertEqual(self.call(gv.SettingsView, self.mgr).status_code, 403)
        r = self.call(gv.SettingsView, self.owner)
        self.assertFalse(r.data["chat_sampling"])
        self.assertEqual(self.call(gv.SettingsView, self.mgr, "patch", data={"chat_sampling": True}).status_code, 403)
        r = self.call(gv.SettingsView, self.owner, "patch", data={"chat_sampling": True, "chat_sample_per_week": 5})
        self.assertTrue(r.data["chat_sampling"])
        self.assertEqual(GamSettings.get().chat_sample_per_week, 5)

    def test_sampling_command_does_nothing_when_off(self):
        out = StringIO()
        with mock.patch("apps.crm.sales_analyst.analyze_dialog") as ai:
            call_command("sample_chats_weekly", "--live", stdout=out)
            ai.assert_not_called()
        self.assertIn("ВИМКНЕНО", out.getvalue())

    def test_season_index_from_standard_and_call_quality(self):
        s = PayScheme.objects.create(user=self.mgr, position="Менеджер", department="Продажі",
                                     valid_from=self.today.replace(day=1), employment="none")
        PayComponent.objects.create(scheme=s, kind="standard", params={"max": 6000, "scores": {self.period: 0.8}})
        for _ in range(3):
            self.analysis(self.mgr, 49)
        se = season(self.mgr)
        parts = {p["key"]: p["value"] for p in se["parts"]}
        self.assertEqual((parts["standard"], parts["quality"]), (80, 70))
        self.assertEqual(se["index"], 75)
        self.assertEqual(se["level"]["name"], "Профі")
        self.assertIn("÷ 2 = 75", se["formula"])
        self.assertIsNone(season(self.mgr2)["index"])                                    # немає даних — не «Старт», а «ще немає»


class ContestTests(_Base):
    def test_seed_enable_award_via_bounty_to_payroll(self):
        call_command("rozvytok_contests_seed", stdout=StringIO())
        self.assertFalse(TaskCategory.objects.filter(name="Змагання тижня").exists())      # DRY нічого не пише
        call_command("rozvytok_contests_seed", "--live", stdout=StringIO())
        self.assertEqual(TaskOffer.objects.filter(category__name="Змагання тижня", active=False).count(), 3)
        self.assertFalse(any(v["enabled"] for v in GamSettings.get().contests.values()))
        mon = self.today - timedelta(days=self.today.weekday() + 7)
        wk = f"{mon.isocalendar()[0]}-W{mon.isocalendar()[1]:02d}"
        self.conversion(self.mgr, mon + timedelta(days=1))
        r = self.call(gv.ContestsView, self.owner, "post", data={"code": "growth", "week": wk})
        self.assertEqual(r.status_code, 409)                                                # вимкнено
        self.call(gv.SettingsView, self.owner, "patch", data={"contests": {"growth": True}})
        res = self.call(gv.ContestsView, self.owner, url=f"/api/gamification/contests/?week={wk}")
        self.assertEqual(res.data["winners"]["growth"]["user_id"], self.mgr.id)
        self.assertEqual(self.call(gv.ContestsView, self.mgr).status_code, 403)
        self.assertEqual(self.call(gv.ContestsView, self.mgr, "post", data={"code": "growth", "week": wk}).status_code, 403)
        PayComponent.objects.create(scheme=PayScheme.objects.create(user=self.mgr, position="Менеджер", department="Продажі",
                                                                     valid_from=self.today.replace(day=1), employment="none"),
                                    kind="fixed_monthly", params={"amount": 1000})
        r = self.call(gv.ContestsView, self.owner, "post", data={"code": "growth", "week": wk})
        self.assertEqual(r.status_code, 200, r.data)
        c = TaskClaim.objects.get(pk=r.data["claim_id"])
        self.assertEqual((c.status, c.user_id, float(c.amount)), ("accepted", self.mgr.id, 300.0))
        line = next(l for l in engine.calc(self.mgr, c.payroll_period)["lines"] if l["kind"] == "bounty")
        self.assertEqual(line["amount"], 300)
        self.assertEqual(self.call(gv.ContestsView, self.owner, "post", data={"code": "growth", "week": wk}).status_code, 409)
        me = self.call(gv.MeView, self.mgr).data["contests"]
        g = next(i for i in me["items"] if i["code"] == "growth")
        self.assertTrue(g["won_last"])
        self.assertNotIn("Друга", str(me))                                                  # чужих цифр учасник не бачить
