from datetime import date, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.finance.models import Account, Transaction

from .meta_marketing import _action_map, _date_chunks, _nbu_rate, _pick, sync_account
from .models import (
    Contact, Deal, Funnel, Lead, MetaAccountDailyStat, MetaAdDailyStat, MetaPaidFollowStat,
    MetaContentStat, Payment, Stage,
)


class MetaMarketingAnalyticsTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="meta-analytics-admin", password="test-pass-123", email="analytics@example.com",
        )
        self.client.force_login(self.admin)

    def test_paid_ads_and_organic_content_are_returned_separately(self):
        common = {
            "date": date(2026, 8, 20), "account_id": "act_1", "account_name": "Wallcov",
            "currency": "USD", "spend": "12.5000", "impressions": 1000, "reach": 800,
            "clicks": 50, "messages_started": 10, "meta_leads": 2,
        }
        MetaAdDailyStat.objects.create(level="account", object_id="1", **common)
        MetaAdDailyStat.objects.create(
            level="ad", object_id="ad-1", campaign_id="campaign-1", campaign_name="Test campaign",
            adset_id="adset-1", adset_name="Test adset", ad_id="ad-1", ad_name="Test creative",
            thumbnail_url="https://example.com/ad.jpg", **common,
        )
        MetaPaidFollowStat.objects.create(
            date=date(2026, 8, 20), campaign_name="Test campaign", adset_name="Test adset",
            ad_name="Test creative", follows=7, report_uid="100",
        )
        MetaContentStat.objects.create(
            ig_account_id="ig-1", media_id="media-1", caption="Organic post",
            media_type="IMAGE", media_product_type="FEED",
            published_at=timezone.now(), like_count=25, comments_count=3,
            reach=500, views=550, saved=7, shares=4, total_interactions=39,
            follows=6, profile_visits=11,
        )

        response = self.client.get("/api/meta-marketing/?from=2026-08-01&to=2026-08-31")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["paid"]["summary"]["spend"], 12.5)
        self.assertEqual(body["paid"]["summary"]["instagram_follows"], 7)
        self.assertEqual(body["paid"]["summary"]["cost_per_instagram_follow"], round(12.5 / 7, 2))
        self.assertEqual(body["paid"]["ads"][0]["ad_id"], "ad-1")
        self.assertEqual(body["paid"]["ads"][0]["instagram_follows"], 7)
        self.assertEqual(body["organic"]["content"][0]["media_id"], "media-1")
        self.assertEqual(body["organic"]["content"][0]["follows"], 6)
        self.assertNotIn("caption", body["paid"]["summary"])

    def test_followers_daily_meta_funnel_and_profitability_are_exposed(self):
        lead_funnel = Funnel.objects.create(name="Лиды", is_lead_funnel=True)
        lead_stage = Stage.objects.create(funnel=lead_funnel, name="Новый")
        core = Funnel.objects.create(name="21 Основний продукт")
        core_stage = Stage.objects.create(funnel=core, name="Оплачено", is_won=True)
        other = Funnel.objects.create(name="Другая воронка")
        other_stage = Stage.objects.create(funnel=other, name="Оплачено", is_won=True)
        first_customer = Contact.objects.create(first_name="Первый")
        ad_customer = Contact.objects.create(first_name="Реклама")

        Lead.objects.create(
            title="Instagram без ID", contact=first_customer, funnel=lead_funnel,
            stage=lead_stage, source="instagram",
        )
        Lead.objects.create(
            title="Instagram с ID", contact=ad_customer, funnel=lead_funnel,
            stage=lead_stage, source="instagram",
            meta_attribution={"platform": "instagram", "source_kind": "paid_ad", "ad_id": "ad-1"},
        )
        first = Deal.objects.create(
            title="Первая", contact=first_customer, funnel=core, stage=core_stage,
            source="instagram", amount=1000,
        )
        repeat = Deal.objects.create(
            title="Повторная", contact=first_customer, funnel=core, stage=core_stage,
            source="instagram", amount=2000,
        )
        excluded = Deal.objects.create(
            title="Исключена", contact=ad_customer, funnel=other, stage=other_stage,
            source="other", amount=3000,
        )
        attributed = Deal.objects.create(
            title="Реклама", contact=ad_customer, funnel=other, stage=other_stage,
            source="facebook", amount=4000,
            meta_attribution={"platform": "facebook", "source_kind": "paid_ad", "ad_id": "ad-1"},
        )
        moments = [
            (first, "2026-08-10T08:00:00+00:00"),
            (repeat, "2026-08-11T08:00:00+00:00"),
            (excluded, "2026-08-12T08:00:00+00:00"),
            (attributed, "2026-08-13T08:00:00+00:00"),
        ]
        for deal, moment in moments:
            payment = Payment.objects.create(deal=deal, provider="cash", amount=deal.amount, is_paid=True)
            Payment.objects.filter(pk=payment.pk).update(created_at=datetime.fromisoformat(moment))

        MetaAccountDailyStat.objects.create(
            date=date(2026, 8, 13), ig_account_id="ig-1", username="wallcov",
            followers_total=63057, followers_gained=25,
        )
        MetaAdDailyStat.objects.create(
            date=date(2026, 8, 13), level="account", account_id="act_1", object_id="1",
            currency="USD", spend="10", fx_rate_to_uah="40", spend_uah="400",
            messages_started=7,
        )

        body = self.client.get("/api/meta-marketing/?from=2026-08-01&to=2026-08-31").json()
        self.assertEqual(body["followers"]["current_total"], 63057)
        self.assertEqual(body["followers"]["period_gained"], 25)
        self.assertEqual(body["summary"]["meta_origin_leads"], 2)
        self.assertEqual(body["summary"]["meta_unassigned_leads"], 1)
        self.assertEqual(body["profitability"]["sales"], 3)
        self.assertEqual(body["profitability"]["repeat_sales"], 1)
        self.assertEqual(body["profitability"]["revenue"], 7000.0)
        self.assertEqual(body["profitability"]["repeat_revenue"], 2000.0)
        self.assertEqual(body["profitability"]["average_ltv"], 3500.0)
        self.assertEqual(body["profitability"]["ad_spend_uah"], 400.0)
        self.assertTrue(any(row["crm_meta_leads"] == 2 for row in body["daily"]))
        self.assertTrue(any(row["followers_total"] == 63057 for row in body["daily"]))
        rows_by_date = {row["date"]: row for row in body["daily"]}
        first_details = rows_by_date["2026-08-10"]["deals"]
        self.assertEqual(len(first_details["primary"]), 1)
        self.assertEqual(first_details["primary"][0]["deal_id"], first.id)
        self.assertEqual(first_details["primary"][0]["paid_today"], 1000.0)
        self.assertEqual(first_details["repeat"], [])
        repeat_details = rows_by_date["2026-08-11"]["deals"]
        self.assertEqual(repeat_details["primary"], [])
        self.assertEqual(len(repeat_details["repeat"]), 1)
        self.assertEqual(repeat_details["repeat"][0]["deal_id"], repeat.id)
        self.assertEqual(repeat_details["repeat"][0]["paid_today"], 2000.0)
        self.assertEqual(repeat_details["repeat"][0]["payment_methods"], ["Наличные"])

    def test_daily_deal_breakdown_groups_same_day_payments_and_reconciles_totals(self):
        core = Funnel.objects.create(name="22 Тестовий набір")
        paid_stage = Stage.objects.create(funnel=core, name="Оплачено", is_won=True)
        customer = Contact.objects.create(first_name="Тест", last_name="Клиент")
        deal = Deal.objects.create(
            title="Две оплаты", contact=customer, funnel=core, stage=paid_stage,
            amount=1500,
        )
        for amount, provider, moment in (
            (500, "cash", "2026-08-20T08:00:00+00:00"),
            (1000, "bank", "2026-08-20T10:00:00+00:00"),
        ):
            payment = Payment.objects.create(
                deal=deal, provider=provider, amount=amount, is_paid=True,
            )
            Payment.objects.filter(pk=payment.pk).update(created_at=datetime.fromisoformat(moment))

        body = self.client.get("/api/meta-marketing/?from=2026-08-20&to=2026-08-20").json()
        row = body["daily"][0]
        self.assertEqual(row["sales"], 1)
        self.assertEqual(row["revenue"], 1500.0)
        self.assertEqual(len(row["deals"]["primary"]), 1)
        detail = row["deals"]["primary"][0]
        self.assertEqual(detail["paid_today"], row["revenue"])
        self.assertEqual(detail["payment_count"], 2)
        self.assertEqual(detail["payment_methods"], ["Наличные", "Банк"])

    def test_main_product_after_tripwire_is_not_repeat_but_next_main_product_is(self):
        tripwire = Funnel.objects.create(name="22 Тестовий набір")
        tripwire_paid = Stage.objects.create(funnel=tripwire, name="Оплачено", is_won=True)
        main = Funnel.objects.create(name="21 Основний продукт")
        main_paid = Stage.objects.create(funnel=main, name="Оплачено", is_won=True)
        customer = Contact.objects.create(first_name="Повторний", last_name="Клієнт")

        deals = [
            Deal.objects.create(title="Тест", contact=customer, funnel=tripwire, stage=tripwire_paid, amount=300),
            Deal.objects.create(title="Перший основний", contact=customer, funnel=main, stage=main_paid, amount=3000),
            Deal.objects.create(title="Повторний основний", contact=customer, funnel=main, stage=main_paid, amount=4000),
        ]
        for deal, moment in zip(deals, (
            "2026-08-18T08:00:00+00:00",
            "2026-08-19T08:00:00+00:00",
            "2026-08-20T08:00:00+00:00",
        )):
            payment = Payment.objects.create(deal=deal, provider="bank", amount=deal.amount, is_paid=True)
            Payment.objects.filter(pk=payment.pk).update(created_at=datetime.fromisoformat(moment))

        body = self.client.get("/api/meta-marketing/?from=2026-08-18&to=2026-08-20").json()
        rows = {row["date"]: row for row in body["daily"]}
        self.assertEqual(rows["2026-08-18"]["repeat_sales"], 0)
        self.assertEqual(rows["2026-08-19"]["repeat_sales"], 0)
        self.assertEqual(rows["2026-08-20"]["repeat_sales"], 1)
        self.assertEqual(rows["2026-08-20"]["repeat_revenue"], 4000.0)
        self.assertEqual(body["profitability"]["repeat_sales"], 1)
        self.assertEqual(body["profitability"]["repeat_revenue"], 4000.0)

    def test_historical_finance_transactions_restore_sales_before_native_payments(self):
        main = Funnel.objects.create(name="21 Основний продукт")
        main_paid = Stage.objects.create(funnel=main, name="Успішна угода", is_won=True)
        tripwire = Funnel.objects.create(name="22 Тестовий набір")
        tripwire_paid = Stage.objects.create(funnel=tripwire, name="Успішна угода", is_won=True)
        account = Account.objects.create(name="Поступ | ФОП ОНЛ", kind="bank")

        regular_contacts = [Contact.objects.create(first_name=f"Клієнт {idx}") for idx in range(4)]
        repeat_contact = Contact.objects.create(first_name="Повторний")
        after_test_contact = Contact.objects.create(first_name="Після тесту")

        prior_main = Deal.objects.create(
            title="Попередній основний", contact=repeat_contact, funnel=main,
            stage=main_paid, amount="2078.00",
        )
        prior_test = Deal.objects.create(
            title="Попередній тест", contact=after_test_contact, funnel=tripwire,
            stage=tripwire_paid, amount="500.00",
        )
        Transaction.objects.create(
            direction="in", amount="2078.00", account=account, deal=prior_main,
            date=date(2026, 4, 25),
        )
        Transaction.objects.create(
            direction="in", amount="500.00", account=account, deal=prior_test,
            date=date(2026, 6, 12),
        )

        deals = [
            Deal.objects.create(title="Тест 2797", contact=regular_contacts[0], funnel=tripwire, stage=tripwire_paid, amount="2797.00"),
            Deal.objects.create(title="Тест 1119", contact=regular_contacts[1], funnel=tripwire, stage=tripwire_paid, amount="1119.00"),
            Deal.objects.create(title="Основний після тесту", contact=after_test_contact, funnel=main, stage=main_paid, amount="2490.50"),
            Deal.objects.create(title="Повторний основний", contact=repeat_contact, funnel=main, stage=main_paid, amount="200.00"),
            Deal.objects.create(title="Основний", contact=regular_contacts[2], funnel=main, stage=main_paid, amount="806.90"),
            Deal.objects.create(title="Тест 844", contact=regular_contacts[3], funnel=tripwire, stage=tripwire_paid, amount="844.00", closed_at=datetime.fromisoformat("2026-06-22T00:00:00+00:00")),
        ]
        Deal.objects.filter(pk__in=[deal.pk for deal in deals]).update(
            created_at=datetime.fromisoformat("2026-06-15T08:00:00+00:00"),
        )
        for deal in deals[:5]:
            Transaction.objects.create(
                direction="in", amount=deal.amount, account=account, deal=deal,
                date=date(2026, 6, 15),
            )
        # Старе надходження є у фінансах CRM, але посилання на угоду не
        # перенеслося. Система має зв'язати його лише коли кандидат один.
        Transaction.objects.create(
            direction="in", amount="844.00", account=account,
            date=date(2026, 6, 15),
        )
        Transaction.objects.create(
            direction="in", amount="1500.00", account=account,
            date=date(2026, 6, 15),
        )

        body = self.client.get("/api/meta-marketing/?from=2026-06-15&to=2026-06-15").json()
        row = body["daily"][0]
        self.assertEqual(row["sales"], 6)
        self.assertEqual(row["revenue"], 8257.4)
        self.assertEqual(row["repeat_sales"], 1)
        self.assertEqual(row["repeat_revenue"], 200.0)
        self.assertEqual(len(row["deals"]["primary"]), 5)
        self.assertEqual(len(row["deals"]["repeat"]), 1)
        inferred = next(item for item in row["deals"]["primary"] if item["paid_today"] == 844.0)
        self.assertTrue(inferred["historical_payment"])
        self.assertTrue(inferred["inferred_payment_link"])
        self.assertIn("история CRM", inferred["payment_methods"][0])

    def test_uah_rate_does_not_call_network(self):
        self.assertEqual(_nbu_rate("UAH", date(2026, 8, 21)), 1)

    def test_unsupported_follower_metric_stays_null_not_zero(self):
        MetaContentStat.objects.create(
            ig_account_id="ig-1", media_id="reel-1", caption="Reel",
            media_type="VIDEO", media_product_type="REELS", published_at=timezone.now(),
            follows=None, profile_visits=None,
        )
        body = self.client.get("/api/meta-marketing/?from=2026-08-01&to=2026-08-31").json()
        row = body["organic"]["content"][0]
        self.assertIsNone(row["follows"])
        self.assertIsNone(row["profile_visits"])

    def test_daily_stat_identity_is_unique(self):
        values = {"date": date(2026, 8, 20), "level": "account", "account_id": "act_1", "object_id": "1"}
        MetaAdDailyStat.objects.create(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MetaAdDailyStat.objects.create(**values)

    def test_action_parser_uses_meta_action_names(self):
        actions = _action_map([
            {"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "17"},
            {"action_type": "lead", "value": "3"},
        ])
        self.assertEqual(_pick(actions, ("onsite_conversion.messaging_conversation_started_7d",)), 17)
        self.assertEqual(_pick(actions, ("lead", "leadgen_grouped")), 3)

    def test_long_backfill_is_split_into_small_meta_requests(self):
        chunks = list(_date_chunks(date(2026, 6, 16), date(2026, 7, 2), days=7))
        self.assertEqual(chunks, [
            (date(2026, 6, 16), date(2026, 6, 22)),
            (date(2026, 6, 23), date(2026, 6, 29)),
            (date(2026, 6, 30), date(2026, 7, 2)),
        ])

    @patch("apps.crm.meta_marketing.configured_ig_account", return_value="ig-1")
    @patch("apps.crm.meta_marketing.graph_get")
    def test_follower_history_uses_last_30_completed_days(self, graph_get_mock, _configured):
        graph_get_mock.side_effect = [
            {"id": "ig-1", "username": "wallcov", "followers_count": 63058},
            {"data": []},
        ]

        with patch("apps.crm.meta_marketing.timezone.localdate", return_value=date(2026, 8, 22)):
            result = sync_account(date(2026, 6, 1), date(2026, 8, 22))

        self.assertEqual(result["followers_total"], 63058)
        insight_calls = graph_get_mock.call_args_list[1:]
        self.assertEqual(len(insight_calls), 1)
        params = insight_calls[0].args[1]
        self.assertEqual(params["since"], "2026-07-23")
        self.assertEqual(params["until"], "2026-08-21")
