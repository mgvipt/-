import os, sys
sys.path.insert(0, os.getcwd()); sys.path.insert(0, "/app")
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); django.setup()
from apps.crm.models import Lead, Deal, Funnel, log_activity
from apps.inbox.models import Conversation, Message
from apps.crm.ai import claude_json

# ── ЕКОНОМІЯ ТОКЕНІВ ─────────────────────────────────────────────────────────
#  1) Дешева модель Хайку замість Сонета (класифікація — проста задача).
#  2) НЕ перепитувати той самий лід, поки не зʼявилось НОВЕ повідомлення
#     (memo у lead.card_fields['_ai_conv_n'] = скільки повідомлень бачили).
#  3) Підпис source — щоб було видно у «Витрати ШІ».
MODEL = "claude-haiku-4-5"
SRC = "ИИ: конвертация лида в сделку"
# ─────────────────────────────────────────────────────────────────────────────

DRY = os.environ.get("DRY_RUN") == "1"
lead_funnel = Funnel.objects.filter(is_lead_funnel=True).first()
test_funnel = (Funnel.objects.filter(is_lead_funnel=False, name__icontains="Тестовий набір").exclude(name__contains="·").first() or Funnel.objects.filter(is_lead_funnel=False, name__icontains="Тестовий набір").first())
main_funnel = (Funnel.objects.filter(is_lead_funnel=False, name__icontains="Основний продукт").exclude(name__contains="·").first() or Funnel.objects.filter(is_lead_funnel=False, name__icontains="Основний продукт").first())
DECIDE = ["Кваліфікований", "Підбір рішення"]

leads = Lead.objects.filter(funnel=lead_funnel, stage__name__in=DECIDE).select_related("contact", "stage", "owner")
checked = converted = skipped = 0
for lead in leads:
    if not lead.contact_id:
        continue
    tg = [f for f in (test_funnel, main_funnel) if f]
    if tg and Deal.objects.filter(contact_id=lead.contact_id, funnel__in=tg).exists():
        continue
    conv = Conversation.objects.filter(contact_id=lead.contact_id).order_by("-last_message_at").first()
    if not conv:
        continue
    # ── skip: вже перевіряли цей лід і НОВИХ повідомлень не було ──
    cnt = Message.objects.filter(conversation=conv).count()
    cf = lead.card_fields if isinstance(lead.card_fields, dict) else {}
    if cf.get("_ai_conv_n") == cnt:
        skipped += 1
        continue
    msgs = list(Message.objects.filter(conversation=conv).order_by("created_at").values("direction", "text"))[-15:]
    dialog = "\n".join((("Клієнт: " if m["direction"] == "in" else "Менеджер: ") + (m["text"] or "")) for m in msgs if m.get("text"))
    if not dialog.strip():
        continue
    checked += 1
    prompt = (
        "Ти аналізуєш діалог продажу декоративних покриттів Wallcov. "
        "Визнач, чи клієнт ВЖЕ остаточно визначився що замовляє. Поверни СТРОГО JSON: "
        '{"decision":"none|test|main","why":"дуже коротко чому"} де '
        "test = клієнт погодився взяти ТЕСТОВИЙ НАБІР / пробник / зразок; "
        "main = клієнт обрав ОСНОВНИЙ продукт / повний обʼєм / замовляє на обʼєкт; "
        "none = ще не визначився остаточно. Будь суворим: 'none' якщо є сумнів.\n\nДіалог:\n" + dialog)
    try:
        res = claude_json(prompt, model=MODEL, source=SRC)
    except Exception:
        continue
    dec = (res.get("decision") or "none").lower()
    why = (res.get("why") or "")[:55]
    if dec not in ("test", "main"):
        # запамʼятати що перевірили на цій кількості повідомлень → не перепитувати
        if not DRY:
            cf["_ai_conv_n"] = cnt; lead.card_fields = cf; lead.save(update_fields=["card_fields"])
        else:
            print("lead %s [%s] -> none | %s" % (lead.id, lead.stage.name, why))
        continue
    funnel = test_funnel if dec == "test" else main_funnel
    if not funnel:
        continue
    if DRY:
        print("lead %s '%s' [%s] -> CONVERT %s (%s) | %s" % (lead.id, (lead.title or "")[:22], lead.stage.name, dec, funnel.name, why))
        continue
    stage = funnel.stages.order_by("order").first()
    deal = Deal.objects.create(title=lead.title, contact=lead.contact, funnel=funnel, stage=stage,
                               amount=lead.amount, source=lead.source, owner=lead.owner,
                               qualification=lead.qualification, card_fields=lead.card_fields)
    log_activity("deal", deal.id, "Створено AI з ліда (лід видалено)", "Лід #%s · %s · контакт #%s" % (lead.id, why, lead.contact_id), None, "AI")
    lead.delete()
    converted += 1
print("checked=%d converted=%d skipped=%d DRY=%s" % (checked, converted, skipped, DRY))
