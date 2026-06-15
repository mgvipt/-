import json
import urllib.request
from django.core.management.base import BaseCommand
from apps.inbox.models import Channel


class Command(BaseCommand):
    help = "Создаёт Telegram-канал (открытую линию) и настраивает webhook."

    def add_arguments(self, p):
        p.add_argument("--token", required=True, help="Токен бота от @BotFather")
        p.add_argument("--name", default="Telegram", help="Название открытой линии")
        p.add_argument("--domain", help="Домен CRM, напр. crm.wallcovdec.com.ua — тогда выставит webhook")

    def handle(self, *a, **o):
        ch, created = Channel.objects.get_or_create(
            kind="telegram", name=o["name"],
            defaults={"config": {"bot_token": o["token"]}},
        )
        if not created:
            ch.config["bot_token"] = o["token"]
            ch.save(update_fields=["config"])
        self.stdout.write(self.style.SUCCESS(f"Канал #{ch.id} «{ch.name}» готов."))

        path = f"/api/inbox/telegram/webhook/{ch.id}/"
        if o.get("domain"):
            hook = f"https://{o['domain']}{path}"
            url = f"https://api.telegram.org/bot{o['token']}/setWebhook"
            data = json.dumps({"url": hook}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
                    resp = json.loads(r.read().decode())
                self.stdout.write(self.style.SUCCESS(f"setWebhook -> {resp}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Не удалось выставить webhook: {e}"))
                self.stdout.write(f"Выставь вручную: {url}  c url={hook}")
        else:
            self.stdout.write(f"Webhook-путь: {path}\n"
                              f"Выставь после деплоя: https://api.telegram.org/bot<ТОКЕН>/setWebhook"
                              f"?url=https://<домен>{path}")
