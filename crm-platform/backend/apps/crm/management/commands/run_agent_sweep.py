from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.crm.models import Lead, Deal, AgentConfig, AgentRun, Task
from apps.inbox.models import Conversation
from apps.crm.agent import run_agent


class Command(BaseCommand):
    help = "Прогнати вбудованого AI-агента по активних/застряглих лідах"

    def handle(self, *args, **opts):
        cfg = AgentConfig.get()
        if not cfg.enabled or not cfg.auto_on_reply:
            self.stdout.write("agent auto disabled"); return
        now = timezone.now()
        cap = 25
        done = 0
        leads = (Lead.objects.exclude(stage__is_lost=True).exclude(stage__is_won=True)
                 .select_related("stage", "funnel", "contact"))
        for lead in leads:
            if done >= cap:
                break
            if not lead.contact_id:
                continue
            conv = Conversation.objects.filter(contact_id=lead.contact_id).order_by("-last_message_at").first()
            if not conv or not conv.last_message_at:
                continue
            lastrun = AgentRun.objects.filter(lead=lead).order_by("-created_at").first()
            age = now - conv.last_message_at
            run_it = False
            if age <= timedelta(days=2):
                # свіжа активність — проганяти якщо не робили після останнього повідомлення
                if not lastrun or lastrun.created_at < conv.last_message_at:
                    run_it = True
            elif age <= timedelta(days=14):
                # застряг — дожим, але не частіше ніж раз на 3 дні і якщо нема відкритого дожиму
                has_followup = Task.objects.filter(lead=lead, kind="followup", status__in=["proposed", "open", "in_progress"]).exists()
                recent_run = lastrun and (now - lastrun.created_at) < timedelta(days=3)
                if not has_followup and not recent_run:
                    run_it = True
            if run_it:
                try:
                    run_agent(lead, "lead", trigger="sweep", user=None)
                    done += 1
                except Exception as e:
                    self.stderr.write(str(e)[:100])
        from apps.inbox.models import Conversation as _Cv
        deals = (Deal.objects.filter(funnel__name__icontains="\u0422\u0435\u0441\u0442\u043e\u0432\u0438\u0439 \u043d\u0430\u0431\u0456\u0440", closed_at__isnull=True)
                 .exclude(stage__is_lost=True).exclude(stage__is_won=True).select_related("stage", "funnel", "contact"))
        for deal in deals:
            if done >= cap:
                break
            if not deal.contact_id:
                continue
            dconv = _Cv.objects.filter(contact_id=deal.contact_id).order_by("-last_message_at").first()
            if not dconv or not dconv.last_message_at:
                continue
            if (now - dconv.last_message_at) > timedelta(days=2):
                continue
            dlast = AgentRun.objects.filter(deal=deal).order_by("-created_at").first()
            if dlast and dlast.created_at >= dconv.last_message_at:
                continue
            try:
                run_agent(deal, "deal", trigger="sweep", user=None); done += 1
            except Exception as e:
                self.stderr.write(str(e)[:100])
        self.stdout.write("agent sweep: processed=%d" % done)
