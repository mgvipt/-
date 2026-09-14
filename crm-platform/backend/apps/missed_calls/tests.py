"""Черга «Пропущені» (14.09.2026): відкриття/закриття, задачі, відповідальний, неробочий час, ескалація, API.
Лише ізольована тестова БД. Нікому нічого не надсилається (у коді немає відправки клієнтам)."""
import io
import json
import os
import tempfile
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.crm.models import Contact, Deal, Funnel, Stage, Task
from apps.finance.models import WorkSession
from apps.inbox.models import Notification
from apps.telephony.models import Call, CallQueueMember

from . import engine, services
from .models import MissedCallItem, MissedCallSettings

KYIV = ZoneInfo("Europe/Kyiv")
INSTA = "Інста Онлайн · 0673812855"
SALON = "Салон · 0964191890"


def kt(day, h, m=0):
    """2026-09-<day> у Києві. 14 = понеділок, 19 = субота, 20 = неділя, 21 = понеділок."""
    return datetime(2026, 9, day, h, m, tzinfo=KYIV)


class EngineTests(SimpleTestCase):
    cal = engine.WorkCalendar()   # 9:00–18:00 щодня

    def test_add_inside_work_hours(self):
        self.assertEqual(self.cal.add_work_minutes(kt(14, 10), 15), kt(14, 10, 15))

    def test_add_crosses_end_of_day(self):
        self.assertEqual(self.cal.add_work_minutes(kt(14, 17, 50), 15), kt(15, 9, 5))

    def test_after_hours_next_day_915(self):
        self.assertEqual(self.cal.add_work_minutes(kt(14, 20, 30), 15), kt(15, 9, 15))

    def test_before_opening_same_day_915(self):
        self.assertEqual(self.cal.add_work_minutes(kt(14, 7, 0), 15), kt(14, 9, 15))

    def test_day_off_skipped(self):
        cal = engine.WorkCalendar(days=frozenset(range(6)))   # неділя вихідна
        self.assertEqual(cal.add_work_minutes(kt(19, 20, 0), 15), kt(21, 9, 15))

    def test_work_minutes_between_over_night(self):
        self.assertEqual(self.cal.work_minutes_between(kt(14, 17, 30), kt(15, 9, 30)), 60)
        self.assertEqual(self.cal.work_minutes_between(kt(14, 20, 0), kt(15, 9, 10)), 10)

    def test_classify_and_numbers(self):
        self.assertEqual(engine.classify("missed", "BUSY"), "missed")
        self.assertEqual(engine.classify("in", "NO ANSWER"), "missed")
        self.assertEqual(engine.classify("in", "ANSWERED"), "answered_in")
        self.assertEqual(engine.classify("out", "BUSY"), "attempt_out")
        self.assertEqual(engine.classify("out", "ANSWERED"), "answered_out")
        self.assertIsNone(engine.classify("in", ""))
        self.assertEqual(engine.norm9("+380 67 111-22-33"), "671112233")
        self.assertEqual(engine.line_key("Алмаз/Рекупер · 0673812702"), engine.line_key("Алмазне/Рекуператори · 0673812702"))

    def test_choose_responsible(self):
        self.assertEqual(engine.choose_responsible(5, 6, [7], {}, {5, 6, 7}), (5, "owner"))
        self.assertEqual(engine.choose_responsible(5, 6, [7], {}, {6, 7}), (6, "last_manager"))
        self.assertEqual(engine.choose_responsible(None, None, [7, 8], {7: 2, 8: 0}, {7, 8}), (8, "on_duty"))
        self.assertEqual(engine.choose_responsible(None, None, [], {}, {7}), (None, ""))

    def test_replay_open_merge_close(self):
        calls = [
            {"id": 1, "direction": "missed", "disposition": "BUSY", "from_number": "+380671112233", "to_number": "s", "line": INSTA, "ts": kt(14, 10)},
            {"id": 2, "direction": "missed", "disposition": "NO ANSWER", "from_number": "+380671112233", "to_number": "s", "line": INSTA, "ts": kt(14, 10, 2)},
            {"id": 3, "direction": "out", "disposition": "BUSY", "from_number": "789", "to_number": "0671112233", "line": SALON, "ts": kt(14, 10, 7)},
            {"id": 4, "direction": "out", "disposition": "ANSWERED", "from_number": "789", "to_number": "0671112233", "line": SALON, "ts": kt(14, 10, 30)},
            {"id": 5, "direction": "missed", "disposition": "BUSY", "from_number": "+380509998877", "to_number": "s", "line": INSTA, "ts": kt(14, 11)},
        ]
        items = engine.replay(calls, self.cal)
        self.assertEqual(len(items), 2)
        a, b = items
        self.assertEqual((a.calls_count, a.status, a.close_reason, a.reaction_work_min), (2, "closed", "callback", 7))
        self.assertEqual(b.status, "open")
        st = engine.stats(items, self.cal, kt(14, 12, 30), 60)
        self.assertEqual((st["items"], st["calls"], st["cb15"], st["never"], st["would_escalate"]), (2, 3, 1, 1, 1))


@override_settings(TELEPHONY_TOKEN="test-only-token")
class QueueTests(TestCase):
    def setUp(self):
        # рядок налаштувань створює міграція 0002 (active_since = момент міграції) — зсуваємо на 01.09
        MissedCallSettings.objects.all().delete()
        MissedCallSettings.objects.create(active_since=kt(1, 0), work_days=[0, 1, 2, 3, 4, 5, 6])
        perms = ["telephony.view"]          # як у менеджерів: доступ до телефонії, без «бачити всі»
        self.m1 = User.objects.create_user(username="tm-ilona", first_name="Ілона", extra_permissions=perms)
        self.m2 = User.objects.create_user(username="tm-kirill", first_name="Кирило", extra_permissions=perms)
        self.m3 = User.objects.create_user(username="tm-inna", first_name="Інна", extra_permissions=perms)
        self.boss = User.objects.create_user(username="tm-boss", first_name="Олег", is_superuser=True)
        for pos, u in enumerate([self.m2, self.m3]):
            CallQueueMember.objects.create(user=u, position=pos, enabled=True)
        self.shift2 = WorkSession.objects.create(user=self.m2)
        self.client_c = Contact.objects.create(first_name="Олена", last_name="Тестова", phone="0671112233", owner=self.m1)

    def missed(self, ts, frm="+380671112233", line=INSTA, contact="auto"):
        c = self.client_c if contact == "auto" and frm.endswith("671112233") else (None if contact == "auto" else contact)
        return Call.objects.create(direction="missed", disposition="BUSY", from_number=frm, to_number="s",
                                   line=line, started_at=ts, contact=c)

    def out(self, ts, to="0671112233", disp="ANSWERED"):
        return Call.objects.create(direction="out", disposition=disp, from_number="789", to_number=to, line=SALON, started_at=ts)

    def inbound(self, ts, frm="+380671112233"):
        return Call.objects.create(direction="in", disposition="ANSWERED", from_number=frm, to_number="s", line=INSTA, started_at=ts)

    # ── відкриття ──
    def test_webhook_missed_opens_item_and_task_for_owner(self):
        r = APIClient().post("/api/telephony/webhook/", {
            "direction": "missed", "from_number": "+380671112233", "to_number": "s", "line": INSTA,
            "disposition": "BUSY", "started_at": kt(14, 10).isoformat(), "external_id": "cdr-1"},
            format="json", HTTP_X_TELEPHONY_TOKEN="test-only-token")
        self.assertEqual(r.status_code, 201)
        it = MissedCallItem.objects.get()
        self.assertEqual((it.status, it.assignee_id, it.assign_reason), ("open", self.m1.id, "owner"))
        self.assertEqual(it.contact_id, self.client_c.id)
        self.assertEqual(it.due_at, kt(14, 10, 15))
        t = it.task
        self.assertEqual((t.kind, t.status, t.assignee_id, t.priority), ("manager", "open", self.m1.id, "high"))
        self.assertEqual(t.due_at, kt(14, 10, 15))
        self.assertIn("Передзвонити", t.title)

    def test_repeat_same_line_merges_other_line_separate(self):
        self.missed(kt(14, 10))
        self.missed(kt(14, 10, 3))
        self.assertEqual(MissedCallItem.objects.count(), 1)
        self.assertEqual(MissedCallItem.objects.get().calls_count, 2)
        self.assertEqual(Task.objects.count(), 1)
        self.missed(kt(14, 10, 5), line=SALON)
        self.assertEqual(MissedCallItem.objects.filter(status="open").count(), 2)

    # ── закриття ──
    def test_attempt_keeps_open_then_answered_callback_closes_all_lines_and_task(self):
        self.missed(kt(14, 10))
        self.missed(kt(14, 10, 1), line=SALON)
        self.out(kt(14, 10, 6), disp="BUSY")
        a = MissedCallItem.objects.get(line=INSTA)
        self.assertEqual((a.status, a.reaction_work_min), ("open", 6))
        self.out(kt(14, 10, 20))
        for it in MissedCallItem.objects.all():
            self.assertEqual((it.status, it.close_reason), ("closed", "callback"))
            self.assertEqual(it.task.status, "done")

    def test_client_got_through_closes(self):
        self.missed(kt(14, 10))
        self.inbound(kt(14, 10, 4))
        it = MissedCallItem.objects.get()
        self.assertEqual((it.status, it.close_reason, it.first_attempt_at), ("closed", "client_called", None))
        self.assertEqual(it.task.status, "done")

    def test_earlier_answered_call_does_not_close(self):
        self.inbound(kt(14, 9, 30))
        self.missed(kt(14, 10))
        self.assertEqual(MissedCallItem.objects.get().status, "open")

    def test_out_of_order_cdr_creates_closed_item_without_task(self):
        self.out(kt(14, 10, 20))                     # розмова прийшла в CRM раніше за пропущений
        self.missed(kt(14, 10))
        it = MissedCallItem.objects.get()
        self.assertEqual((it.status, it.close_reason, it.reaction_work_min), ("closed", "callback", 20))
        self.assertIsNone(it.task_id)
        self.assertEqual(Task.objects.count(), 0)

    # ── відповідальний ──
    def test_unknown_number_goes_to_on_duty_with_fewest_open(self):
        WorkSession.objects.create(user=self.m3)
        # у черзі дзвінків і на зміні, але БЕЗ доступу до телефонії (як склад) — пропущені не отримує
        store = User.objects.create_user(username="tm-store", first_name="Склад")
        CallQueueMember.objects.create(user=store, position=0, enabled=True)
        WorkSession.objects.create(user=store)
        self.missed(kt(14, 10), frm="+380501110001")
        self.missed(kt(14, 10, 1), frm="+380501110002")
        a, b = MissedCallItem.objects.order_by("id")
        self.assertEqual((a.assignee_id, a.assign_reason), (self.m2.id, "on_duty"))
        self.assertEqual((b.assignee_id, b.assign_reason), (self.m3.id, "on_duty"))

    def test_owner_without_phone_access_falls_back_to_on_duty(self):
        old = User.objects.create_user(username="tm-b24-old", first_name="Старий")   # акаунт без прав
        c = Contact.objects.create(first_name="Клієнт", last_name="Старого", phone="0931234567", owner=old)
        self.missed(kt(14, 10), frm="+380931234567", contact=c)
        it = MissedCallItem.objects.get()
        self.assertEqual((it.assignee_id, it.assign_reason), (self.m2.id, "on_duty"))
        boss = APIClient()
        boss.force_authenticate(self.boss)
        ids = {c["id"] for c in boss.get("/api/telephony/missed/").data["colleagues"]}
        self.assertNotIn(old.id, ids)
        r = boss.post(f"/api/telephony/missed/{it.id}/action/", {"action": "transfer", "user_id": old.id}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_last_manager_from_deal(self):
        f = Funnel.objects.create(name="tm funnel")
        s = Stage.objects.create(funnel=f, name="Нова", order=0)
        c = Contact.objects.create(first_name="Без", last_name="Власника", phone="0632223344")
        Deal.objects.create(title="tm deal", contact=c, funnel=f, stage=s, owner=self.m3)
        self.missed(kt(14, 10), frm="+380632223344", contact=c)
        it = MissedCallItem.objects.get()
        self.assertEqual((it.assignee_id, it.assign_reason), (self.m3.id, "last_manager"))

    def test_nobody_on_duty_then_sweep_assigns_when_shift_starts(self):
        WorkSession.objects.filter(user=self.m2).update(ended_at=kt(14, 9))
        self.missed(kt(14, 20, 30), frm="+380501110003")
        it = MissedCallItem.objects.get()
        self.assertIsNone(it.assignee_id)
        self.assertIsNone(it.task.assignee_id)
        self.assertEqual(it.due_at, kt(15, 9, 15))            # неробочий час → наступний день 9:15
        self.assertEqual(it.task.due_at, kt(15, 9, 15))
        WorkSession.objects.create(user=self.m3)
        res = services.sweep(now=kt(15, 9, 1))
        it.refresh_from_db()
        self.assertEqual(res["assigned"], 1)
        self.assertEqual((it.assignee_id, it.assign_reason), (self.m3.id, "on_duty"))
        self.assertEqual(Task.objects.get(id=it.task_id).assignee_id, self.m3.id)

    # ── ескалація ──
    def test_escalation_once_after_60_work_minutes(self):
        self.missed(kt(14, 10))
        self.assertEqual(services.sweep(now=kt(14, 10, 30))["escalated"], 0)
        self.assertEqual(services.sweep(now=kt(14, 11, 1))["escalated"], 1)
        self.assertEqual(services.sweep(now=kt(14, 12))["escalated"], 0)
        n = Notification.objects.filter(user=self.boss)
        self.assertEqual(n.count(), 1)
        self.assertIn("без передзвону", n.get().text)
        self.assertFalse(Notification.objects.filter(user=self.m1).exists())

    def test_no_escalation_over_night(self):
        self.missed(kt(14, 17, 40))
        self.assertEqual(services.sweep(now=kt(15, 9, 0))["escalated"], 0)   # 20 роб. хв
        self.assertEqual(services.sweep(now=kt(15, 9, 41))["escalated"], 1)

    def test_task_closed_by_hand_closes_item(self):
        self.missed(kt(14, 10))
        it = MissedCallItem.objects.get()
        Task.objects.filter(id=it.task_id).update(status="done")
        self.assertEqual(services.sweep(now=kt(14, 10, 5))["task_closed"], 1)
        it.refresh_from_db()
        self.assertEqual((it.status, it.close_reason), ("closed", "task_closed"))

    def test_sweep_picks_up_missed_call_without_item(self):
        from django.db.models.signals import post_save
        from .signals import on_call_saved
        post_save.disconnect(on_call_saved, sender=Call, dispatch_uid="missed_calls_on_call_saved")
        try:
            self.missed(kt(14, 10))
        finally:
            post_save.connect(on_call_saved, sender=Call, dispatch_uid="missed_calls_on_call_saved")
        self.assertEqual(MissedCallItem.objects.count(), 0)
        self.assertEqual(services.sweep(now=kt(14, 10, 5))["picked_up"], 1)
        self.assertEqual(MissedCallItem.objects.count(), 1)

    # ── фільтри ──
    def test_ignore_staff_and_old_history(self):
        self.m2.phone = "0509998877"
        self.m2.save()
        self.missed(kt(14, 10), frm="+380509998877")
        self.missed(datetime(2026, 8, 1, 10, 0, tzinfo=KYIV), frm="+380501110009")   # до active_since
        self.assertEqual(MissedCallItem.objects.count(), 0)

    # ── API ──
    def test_manual_close_and_permissions(self):
        self.missed(kt(14, 10))
        it = MissedCallItem.objects.get()
        c2 = APIClient()
        c2.force_authenticate(self.m2)
        r = c2.post(f"/api/telephony/missed/{it.id}/action/", {"action": "close", "reason": "other_channel"}, format="json")
        self.assertEqual(r.status_code, 403)                    # чужий пропущений
        c1 = APIClient()
        c1.force_authenticate(self.m1)
        r = c1.post(f"/api/telephony/missed/{it.id}/action/", {"action": "close", "reason": "bad"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = c1.post(f"/api/telephony/missed/{it.id}/action/", {"action": "close", "reason": "other_channel", "note": "відповіла у Viber"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        it.refresh_from_db()
        self.assertEqual((it.status, it.close_reason, it.closed_by_id), ("closed", "other_channel", self.m1.id))
        self.assertEqual(it.task.status, "done")

    def test_transfer_to_colleague(self):
        self.missed(kt(14, 10))
        it = MissedCallItem.objects.get()
        c1 = APIClient()
        c1.force_authenticate(self.m1)
        r = c1.post(f"/api/telephony/missed/{it.id}/action/", {"action": "transfer", "user_id": self.m3.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        it.refresh_from_db()
        self.assertEqual((it.assignee_id, it.assign_reason), (self.m3.id, "transfer"))
        self.assertEqual(Task.objects.get(id=it.task_id).assignee_id, self.m3.id)
        self.assertTrue(Notification.objects.filter(user=self.m3, text__contains="передає").exists())

    def test_list_summary_report_settings(self):
        self.missed(kt(14, 10))
        self.missed(kt(14, 10, 1), frm="+380501110004")          # → черговий Кирило
        self.out(kt(14, 10, 12))                                  # Олені передзвонили за 12 хв
        boss = APIClient()
        boss.force_authenticate(self.boss)
        r = boss.get("/api/telephony/missed/?status=all&days=60")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["results"]), 2)
        self.assertTrue(r.data["can_report"])
        r = boss.get("/api/telephony/missed/report/?from=2026-09-01&to=2026-09-30")
        self.assertEqual(r.status_code, 200)
        tot = r.data["total"]
        self.assertEqual((tot["items"], tot["cb15"], tot["never"]), (2, 1, 1))
        names = {row["name"]: row for row in r.data["by_manager"]}
        self.assertEqual(names["Ілона"]["median_work_min"], 12)
        self.assertEqual(r.data["by_line"][0]["line"], INSTA)
        self.assertEqual(boss.get("/api/telephony/missed/settings/").status_code, 200)
        r = boss.patch("/api/telephony/missed/settings/", {"sla_minutes": 20, "work_start": "08:30"}, format="json")
        self.assertEqual((r.status_code, r.data["sla_minutes"], r.data["work_start"]), (200, 20, "08:30"))
        k = APIClient()
        k.force_authenticate(self.m2)
        s = k.get("/api/telephony/missed/summary/").data
        self.assertEqual((s["mine"], s["unassigned"]), (1, 0))
        self.assertEqual(k.get("/api/telephony/missed/report/").status_code, 403)
        self.assertEqual(k.patch("/api/telephony/missed/settings/", {"sla_minutes": 1}, format="json").status_code, 403)

    def test_backfill_dry_writes_nothing(self):
        from django.db.models.signals import post_save
        from .signals import on_call_saved
        post_save.disconnect(on_call_saved, sender=Call, dispatch_uid="missed_calls_on_call_saved")
        try:
            now = datetime.now(KYIV)
            Call.objects.create(direction="missed", disposition="BUSY", from_number="+380671112233", to_number="s",
                                line=INSTA, started_at=now.replace(microsecond=0) - __import__("datetime").timedelta(days=2),
                                contact=self.client_c)
        finally:
            post_save.connect(on_call_saved, sender=Call, dispatch_uid="missed_calls_on_call_saved")
        out = io.StringIO()
        call_command("missed_calls_backfill", days=30, stdout=out)
        self.assertIn("DRY_RUN", out.getvalue())
        self.assertEqual(MissedCallItem.objects.count(), 0)
        self.assertIn('"items": 1', out.getvalue())

    def test_backfill_from_json(self):
        ds = {"now": kt(14, 12).isoformat(), "calls": [
            {"id": 1, "direction": "missed", "disposition": "BUSY", "from_number": "+380671112233", "to_number": "s", "line": INSTA, "ts": kt(14, 10).isoformat(), "contact_id": 9},
            {"id": 2, "direction": "out", "disposition": "ANSWERED", "from_number": "789", "to_number": "0671112233", "line": SALON, "ts": kt(14, 10, 40).isoformat(), "contact_id": 9}],
            "contacts": {"9": {"owner": 3, "last": None}}, "active_ids": [3], "users": {"3": "Кирило"}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(ds, fh)
        try:
            out = io.StringIO()
            call_command("missed_calls_backfill", from_json=fh.name, stdout=out)
        finally:
            os.unlink(fh.name)
        txt = out.getvalue()
        self.assertIn('"name": "Кирило"', txt)
        self.assertIn('"cb60": 1', txt)
        self.assertEqual(MissedCallItem.objects.count(), 0)
