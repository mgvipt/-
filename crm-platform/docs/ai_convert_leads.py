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
# ── РАННІ стадії: перевіряємо ТІЛЬКИ якщо в діалозі є ЯВНИЙ сигнал купівлі ──
#  Навіщо: клієнт часто пише «беру» ще до того, як менеджер перевів лід у «Кваліфікований»
#  (з 713 ранніх лідів такі знайшлись). Прескрінінг по словах = 0 витрат ШІ на решту.
EARLY = ["Взято в роботу", "Контакт встановлений", "Лід отриманий"]
BUY_KW = ["беру", "замовля", "заказыв", "оформ", "куплю", "купую", "виставте рахунок",
          "выставьте счет", "хочу взяти", "давайте офор", "оплачу", "оплатив", "оплатила"]

leads = Lead.objects.filter(funnel=lead_funnel, stage__name__in=(DECIDE + EARLY)).select_related("contact", "stage", "owner")
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
    # рання стадія → до ШІ тільки якщо клієнт ЯВНО щось сказав про купівлю (економія токенів)
    if lead.stage.name in EARLY:
        _in_txt = " ".join((m["text"] or "").lower() for m in msgs if m.get("direction") == "in")
        if not any(k in _in_txt for k in BUY_KW):
            skipped += 1
            continue
    checked += 1
    prompt = (
        "Ти аналізуєш діалог продажу декоративних покриттів Wallcov. "
        "Визнач, чи клієнт ЯВНО, СВОЇМИ СЛОВАМИ ПІДТВЕРДИВ, що ЗАМОВЛЯЄ / бере (не просто цікавиться, не просить інформацію/ціну). "
        "Поверни СТРОГО JSON: {\"decision\":\"none|test|main\",\"why\":\"дуже коротко чому\"} де "
        "test = клієнт ПРЯМО сказав що БЕРЕ/ЗАМОВЛЯЄ тестовий набір (напр. \"беру тест\", \"давайте оформимо пробник\", \"так, хочу тест-набір\"); "
        "main = клієнт ПРЯМО сказав що ЗАМОВЛЯЄ основний продукт/повний обʼєм на обʼєкт; "
        "none = у ВСІХ інших випадках — цікавиться, питає ціну, просить інформацію/прорахунок, думає, \"давайте тестовый набор\" як питання-уточнення без згоди, будь-який сумнів. "
        "⛔ ДУЖЕ ВАЖЛИВО: якщо немає ЯВНОГО \"беру/замовляю/оформляйте\" — це ЗАВЖДИ none. Краще не конвертувати, ніж конвертувати рано.\n\nДіалог:\n" + dialog)
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
