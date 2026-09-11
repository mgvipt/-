"""«Закрити день» (11.09): знімок платежів дня, що змінилось після знімка, автознімок о 18:00."""
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.finance.day_close import close_day, diff
from apps.finance.models import Account, DaySnapshot, Transaction

D = date(2026, 9, 10)
HOST = "crm.wallcovdec.com.ua"


class DayCloseTests(TestCase):
    def setUp(self):
        self.a1 = Account.objects.create(name="Каса тест")
        self.a2 = Account.objects.create(name="ФОП тест")
        self.t_in = Transaction.objects.create(direction="in", amount=Decimal("1500"), amount_uah=Decimal("1500"),
                                               account=self.a1, date=D, counterparty="Клієнт")
        self.t_out = Transaction.objects.create(direction="out", amount=Decimal("200"), amount_uah=Decimal("200"),
                                                account=self.a1, date=D)
        self.t_tr = Transaction.objects.create(direction="transfer", amount=Decimal("300"), amount_uah=Decimal("300"),
                                               account=self.a1, transfer_account=self.a2, date=D)
        self.admin = get_user_model().objects.create_superuser("dc-admin", "dc@example.test", "x")

    def test_close_rows_totals_and_idempotent(self):
        s, created = close_day(D, self.admin)
        self.assertTrue(created)
        self.assertEqual(len(s.rows), 3)
        acc1 = s.totals["accounts"][str(self.a1.id)]
        self.assertEqual((acc1["in"], acc1["out"], acc1["tr_out"], acc1["net"]), (1500.0, 200.0, 300.0, 1000.0))
        self.assertEqual(s.totals["accounts"][str(self.a2.id)]["tr_in"], 300.0)
        s2, created2 = close_day(D, self.admin)
        self.assertFalse(created2)
        self.assertEqual(s2.id, s.id)

    def test_diff_changed_deleted_added(self):
        s, _ = close_day(D, self.admin)
        self.t_in.amount = Decimal("1200")
        self.t_in.save()
        self.t_out.delete()
        Transaction.objects.create(direction="in", amount=Decimal("50"), amount_uah=Decimal("50"), account=self.a1, date=D)
        dd = diff(s)
        self.assertEqual(len(dd["changed"]), 1)
        self.assertEqual(dd["changed"][0]["was"]["amount"], 1500.0)
        self.assertEqual(dd["changed"][0]["now"]["amount"], 1200.0)
        self.assertEqual(len(dd["deleted"]), 1)
        self.assertEqual(len(dd["added_after"]), 1)
        self.assertEqual(dd["count"], 3)  # змінено + видалено + додано вручну

    def test_reclose_and_reopen(self):
        s, _ = close_day(D, self.admin)
        s2, created = close_day(D, self.admin, "reclose")
        self.assertTrue(created)
        self.assertEqual(s2.version, 2)
        self.assertEqual(DaySnapshot.objects.filter(date=D).count(), 2)

    def test_api(self):
        c = APIClient()
        c.force_authenticate(self.admin)
        r = c.post("/api/day-snapshots/close/", {"date": D.isoformat()}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        sid = r.json()["id"]
        r = c.get("/api/day-snapshots/?from=2026-09-01&to=2026-09-30", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["results"][0]["id"], sid)
        r = c.get("/api/day-snapshots/%s/" % sid, HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["rows"]), 3)
        r = c.post("/api/day-snapshots/close/", {"date": "2099-01-01"}, format="json", HTTP_HOST=HOST)
        self.assertEqual(r.status_code, 400)
        plain = get_user_model().objects.create_user("dc-plain", password="x")
        c2 = APIClient()
        c2.force_authenticate(plain)
        self.assertEqual(c2.get("/api/day-snapshots/", HTTP_HOST=HOST).status_code, 403)

    def test_command_respects_kyiv_time(self):
        kyiv = ZoneInfo("Europe/Kyiv")
        target = "apps.finance.management.commands.day_close_snapshot.timezone.localtime"
        with patch(target, return_value=datetime(2026, 9, 10, 17, 30, tzinfo=kyiv)):
            call_command("day_close_snapshot", stdout=StringIO())
        self.assertFalse(DaySnapshot.objects.filter(date=D).exists())
        with patch(target, return_value=datetime(2026, 9, 10, 18, 15, tzinfo=kyiv)):
            call_command("day_close_snapshot", "--dry-run", stdout=StringIO())
            self.assertFalse(DaySnapshot.objects.filter(date=D).exists())
            call_command("day_close_snapshot", stdout=StringIO())
            call_command("day_close_snapshot", stdout=StringIO())
        self.assertEqual(DaySnapshot.objects.filter(date=D).count(), 1)
        self.assertEqual(DaySnapshot.objects.get(date=D).kind, "auto")
