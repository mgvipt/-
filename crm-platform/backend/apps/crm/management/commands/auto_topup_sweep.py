"""Django management command: auto_topup_sweep

ПЕРЕНЕСЕНО з Hetzner у CRM на Netcup — 2026-08-16.

Раніше цей розбір жив у /opt/kb-wallcov/auto_topup_flow.py на Hetzner і
викликав CRM через `subprocess docker exec crm-platform-web-1`. Після переїзду
CRM на Netcup ця команда била у СТАРИЙ контейнер Hetzner: сделка створювалась
би у мертвій базі, а клієнт отримав би посилання, яке на Netcup не існує
(«Посилання не знайдено або застаріло»). Тепер увесь потік працює всередині CRM.

Що робить:
  1. Знаходить діалоги, де Юля щойно сказала «Оформлюю Ваше замовлення в системі».
  2. Класифікує намір по останніх повідомленнях (Haiku, витрати пишуться в AiUsage).
  3. Якщо це ДОКУП повторника — створює сделку через auto_topup_create,
     передаючи НОМЕР ПЕРЕПИСКИ (клієнт визначається точно, без здогадок).
  4. Надсилає клієнту посилання на оплату у той самий чат — засобами самої CRM.

Тест-набори, тонування і нові обʼєкти НЕ автоматизуються — вони йдуть менеджеру,
рівно як було на Hetzner.

Запуск:
    python manage.py auto_topup_sweep --dry-run --hours 48
    python manage.py auto_topup_sweep            # бойовий, крон кожні 10 хв
"""
from __future__ import annotations

import io
import json
import re
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

TRIGGER_WORD = "оформлюю"                     # дешевий префільтр по БД
TRIGGER_RE = re.compile(r"оформл\w*\s+ваш\w*\s+замовленн\w*\s+в\s+систем", re.I)
CHANNEL_KINDS = ("instagram", "tiktok")
HAIKU_MODEL = "claude-haiku-4-5"
MIN_CONFIDENCE = 0.85
MAX_AMOUNT = 3000                             # вище — передаємо менеджеру

INTENT_SYSTEM = """Ти аналізуєш діалог з клієнтом IG/TikTok про декоративні покриття Wallcov.
Юля-консультант щойно написала фразу типу «Оформлюю Ваше замовлення в системі».
Твоя задача — визначити ТИП замовлення і витягти дані з контексту діалогу.

ТИПИ:
- test_kit — клієнт бере тестовий набір (є згадка «тест-набір», «пробник», ціни 220-635 грн)
- topup — клієнт-повторник докуповує до попереднього замовлення («докуп», «не вистачило», «мало», «як минулого разу», «того самого», «повторити»)
- new_object_order — новий об'єм на об'єкт (площа, стіни, повне нове замовлення)
- unclear — контекст неоднозначний, не зрозуміло

Прапори:
- has_tinting — згадується тонування («з тонуванням», «тонований», «колір {номер}», «з тонировкой», «в кольорі», «код кольору»)

Поверни СТРОГО JSON:
{
  "type": "test_kit" | "topup" | "new_object_order" | "unclear",
  "has_tinting": true | false,
  "material_query": "<коротка назва матеріалу як згадана>" або null,
  "quantity_kg": <число або null>,
  "customer_reference": "<цитата що підтверджує повторність>" або null,
  "confidence": 0.0-1.0
}

Поверни лише JSON без пояснень."""


class Command(BaseCommand):
    help = "Авто-докуп: розбір діалогів «оформлюю в системі» і створення сделки (Netcup)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Нічого не створювати і не надсилати — тільки показати рішення")
        parser.add_argument("--hours", type=int, default=6,
                            help="Наскільки давні тригери дивитись (за замовчуванням 6 годин)")
        parser.add_argument("--limit", type=int, default=20,
                            help="Максимум діалогів за прогін — запобіжник від лавини")

    # ── допоміжне ────────────────────────────────────────────────────
    def _dialog(self, Message, conv, upto):
        rows = list(
            Message.objects.filter(conversation=conv, created_at__lte=upto)
            .order_by("-created_at")[:15]
        )[::-1]
        out = []
        for m in rows:
            t = (m.text or "").strip()
            if t:
                out.append({"side": "client" if m.direction == "in" else "we", "text": t[:600]})
        return out

    def _create_deal(self, payload, dry):
        """Викликаємо існуючу перевірену команду створення. Вона друкує JSON і виходить."""
        buf = io.StringIO()
        try:
            call_command("auto_topup_create",
                         json=json.dumps(payload, ensure_ascii=False),
                         dry_run=dry, stdout=buf)
        except SystemExit:
            pass
        except Exception as e:
            return {"ok": False, "error": "create_command_failed", "detail": str(e)}
        lines = [l for l in buf.getvalue().splitlines() if l.strip()]
        if not lines:
            return {"ok": False, "error": "no_output"}
        try:
            return json.loads(lines[-1])
        except Exception:
            return {"ok": False, "error": "bad_output", "detail": lines[-1][:200]}

    # ── основне ──────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        from apps.crm.ai import claude_json
        from apps.crm.models import Deal
        from apps.inbox.models import Message
        from apps.inbox.services import send_message

        dry = bool(opts.get("dry_run"))
        hours = int(opts.get("hours") or 6)
        limit = int(opts.get("limit") or 20)
        since = timezone.now() - timedelta(hours=hours)

        triggers = (
            Message.objects
            .filter(direction="out", created_at__gte=since,
                    text__icontains=TRIGGER_WORD,
                    conversation__channel__kind__in=CHANNEL_KINDS)
            .select_related("conversation", "conversation__contact", "conversation__channel")
            .order_by("-created_at")[:200]
        )

        seen, results = set(), []
        for msg in triggers:
            if len(results) >= limit:
                break
            conv = msg.conversation
            if conv.id in seen:
                continue
            seen.add(conv.id)
            if not TRIGGER_RE.search(msg.text or ""):
                continue

            item = {"conv": conv.id, "chat_id": conv.external_chat_id}
            try:
                contact = conv.contact
                if not contact:
                    item.update(action="skipped", reason="no_contact")
                    results.append(item); continue
                item["contact"] = contact.id

                # вже оформлено після цього тригера — не дублюємо
                if Deal.objects.filter(contact=contact, title__icontains="докуп",
                                       created_at__gte=msg.created_at).exists():
                    item.update(action="skipped", reason="already_created")
                    results.append(item); continue

                dialog = self._dialog(Message, conv, msg.created_at)
                if not dialog:
                    item.update(action="skipped", reason="empty_dialog")
                    results.append(item); continue

                intent = claude_json(
                    prompt=json.dumps(dialog, ensure_ascii=False),
                    model=HAIKU_MODEL, max_tokens=300, system=INTENT_SYSTEM,
                    cache=True, source="auto_topup_intent",
                )
                if not isinstance(intent, dict) or "type" not in intent:
                    item.update(action="escalated", reason="intent_failed")
                    results.append(item); continue

                itype = intent.get("type")
                conf = float(intent.get("confidence") or 0)
                item["intent"] = {"type": itype, "conf": conf,
                                  "tinting": bool(intent.get("has_tinting"))}

                # маршрутизація — один-в-один як було на Hetzner
                if itype == "test_kit":
                    item.update(action="test_kit_fallback"); results.append(item); continue
                if bool(intent.get("has_tinting")):
                    item.update(action="escalated", reason="tinting_needs_manager")
                    results.append(item); continue
                if itype == "new_object_order":
                    item.update(action="escalated", reason="new_object_order")
                    results.append(item); continue
                if itype != "topup":
                    item.update(action="test_kit_fallback", reason="unclear_%s" % itype)
                    results.append(item); continue
                if conf < MIN_CONFIDENCE:
                    item.update(action="escalated", reason="low_confidence")
                    results.append(item); continue

                mq, qty = intent.get("material_query"), intent.get("quantity_kg")
                if not mq or not qty:
                    item.update(action="escalated", reason="missing_material_or_qty")
                    results.append(item); continue

                payload = {
                    "chat_id": conv.external_chat_id,        # ← точне опізнання клієнта
                    "ig_username": (contact.nickname or "").lstrip("@"),
                    "client_name": ("%s %s" % (contact.first_name or "",
                                               contact.last_name or "")).strip(),
                    "material_query": mq,
                    "quantity_kg": qty,
                    "max_amount": MAX_AMOUNT,
                }
                res = self._create_deal(payload, dry)
                item["crm"] = res
                if not res.get("ok"):
                    item.update(action="escalated", reason=res.get("error") or "crm_failed")
                    results.append(item); continue

                if dry:
                    item.update(action="would_create"); results.append(item); continue

                link = res.get("pay_link_short")
                if link:
                    send_message(conv, "💳 Оплатити онлайн 👉 %s\nСума: %s грн"
                                 % (link, res.get("amount")), user=None)
                    item.update(action="created_and_sent", deal=res.get("deal_id"))
                else:
                    item.update(action="created_no_link", deal=res.get("deal_id"))
                results.append(item)

            except Exception as e:  # один поганий діалог не валить увесь прогін
                item.update(action="error", detail=str(e)[:200])
                results.append(item)

        self.stdout.write(json.dumps(
            {"ok": True, "dry": dry, "hours": hours,
             "triggers_seen": len(seen), "processed": len(results), "items": results},
            ensure_ascii=False, default=str))
