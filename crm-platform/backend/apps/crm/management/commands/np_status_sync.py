"""Поллер статусів НП → авто-рух по воронці + авто-повідомлення клієнту (шаблони з Bitrix).
ТТН створена → Відправлення → В дорозі → Прибув на відділення → 3 дні → Отримано.
Стадія = колонка складської канбан-дошки (синхронно). Повідомлення — один раз на сделку (флаг у np_data). Крон */20."""
from datetime import datetime
from django.core.management.base import BaseCommand
from apps.crm.models import Deal, Stage
from apps.integrations import adapters as ad
from apps.crm.views import _advance_deal_stage
from apps.inbox.models import Conversation
from apps.inbox.services import send_message

CODE_STAGE = {
    "1": "ТТН створена",
    "4": "Відправлен", "41": "Відправлен",
    "5": "В дорозі", "6": "В дорозі", "101": "В дорозі", "104": "В дорозі",
    "7": "Прибув на відділення", "8": "Прибув на відділення",
    "9": "__received__", "10": "__received__", "11": "__received__",
}
SEND_CAP = 40  # ліміт повідомлень на один запуск (щоб не блокували канали)


def _parse_np_dt(s):
    for fmt in ("%d-%m-%Y %H:%M:%S", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime((s or "").strip(), fmt)
        except Exception:
            pass
    return None


def _find_stage(funnel_id, sub, received=False):
    qs = Stage.objects.filter(funnel_id=funnel_id, name__icontains=sub)
    if received:
        qs = qs.exclude(name__icontains="оплат")
    return qs.order_by("order").first()


def _mgr(deal):
    o = deal.owner
    if not o:
        return "Wallcov"
    return o.first_name or o.get_full_name() or "Wallcov"


def _msg(key, deal, row):
    mgr = _mgr(deal)
    num = getattr(deal, "b24_id", None) or deal.id
    ttn = deal.ttn
    city = (row or {}).get("CityRecipient") or ""
    wh = (row or {}).get("WarehouseRecipient") or ""
    track = "https://novaposhta.ua/tracking/?cargo_number=%s" % ttn
    if key == "shipped":
        return ("На зв'язку %s: \nДоброго дня! 👋\n\n📦 Ваше замовлення №%s відправлено!\n\n"
                "🚚 Номер ТТН: %s\n📍 Відстежувати: %s\n\nЗазвичай посилка йде 1-3 робочих дні. "
                "Як прибуде у відділення — ми надішлемо повідомлення з нагадуванням про правила перевірки.\n\n"
                "Дякуємо, що обрали Wallcov! 💚" % (mgr, num, ttn, track))
    if key == "arrived":
        return ("На зв'язку %s: \nДоброго дня! 👋\n\n✍ Ваше замовлення №%s прибуло у відділення Нової Пошти!\n\n"
                "🚚 ТТН: %s\n📍 Адреса: %s, %s\n\n🕒 Зберігання у відділенні безкоштовне 5 робочих днів.\n"
                "Будь ласка, заберіть посилку якомога швидше.\n\n📌 Перевірити статус: %s\n──────\n"
                "❗ ВАЖЛИВО при отриманні\n\nПеревірте товар у відділенні або при кур'єрі:\n"
                "  • цілісність упаковки\n  • відсутність дефектів на товарі\n  • комплектацію та зовнішній вигляд\n\n"
                "Якщо є пошкодження:\n  1) Знайдіть місце пошкодження упаковки\n"
                "  2) Складіть «Акт прийому-передачі» прямо у відділенні НП\n"
                "  3) Потім оформлюється «Претензія на відшкодування коштів»\n\n"
                "⚠ Якщо клієнт не оформить Акт прийому-передачі належним чином — ми не зможемо замінити товар. "
                "Пошкоджений товар вважатиметься прийнятим.\n\nДякуємо, що обрали Wallcov! 💚"
                % (mgr, num, ttn, city, wh, track))
    return ("На зв'язку %s: \nДоброго дня! 👋\n\n📦 Нагадуємо: ваше замовлення №%s вже декілька днів чекає "
            "на відділенні Нової Пошти.\n\n🚚 ТТН: %s\n📍 %s, %s\n\n🕒 Безкоштовне зберігання — 5 робочих днів. "
            "Будь ласка, заберіть посилку, щоб вона не повернулася назад 🙏\n\n📌 %s"
            % (mgr, num, ttn, city, wh, track))


def _maybe_send(deal, row, ctr):
    name = (deal.stage.name or "").lower()
    nd = deal.np_data or {}
    if "відправлен" in name and not nd.get("msg_shipped"):
        key, flag = "shipped", "msg_shipped"
    elif "прибув" in name and not nd.get("msg_arrived"):
        key, flag = "arrived", "msg_arrived"
    elif "3 дні" in name and not nd.get("msg_3days"):
        key, flag = "3days", "msg_3days"
    else:
        return
    if ctr["sent"] >= SEND_CAP or not deal.contact_id:
        return
    conv = Conversation.objects.filter(contact_id=deal.contact_id).order_by("-last_message_at").first()
    if not conv or not conv.external_chat_id:
        return
    try:
        send_message(conv, _msg(key, deal, row), user=None)
    except Exception:
        return
    nd = dict(deal.np_data or {}); nd[flag] = True; deal.np_data = nd
    deal.save(update_fields=["np_data"])
    ctr["sent"] += 1


class Command(BaseCommand):
    help = "Синхронізувати статуси НП у стадії + авто-повідомлення клієнту"

    def handle(self, *args, **opts):
        # «закритість» визначаємо ТІЛЬКИ за стадією (is_won/is_lost). closed_at НЕ фільтруємо:
        # у частини сделок він проставлений артефактом імпорту з Бітрикса, хоча угода відкрита (напр. #65145).
        # Сортуємо за stage_changed_at (найдовше застряглі — першими), ліміт піднято зі 120 (було замало на 213).
        from django.db.models import F
        deals = (Deal.objects.exclude(ttn="").exclude(ttn__isnull=True)
                 .exclude(stage__is_won=True).exclude(stage__is_lost=True).select_related("stage", "funnel")
                 .order_by(F("stage_changed_at").asc(nulls_first=True))[:400])
        moved = 0
        ctr = {"sent": 0}
        for d in deals:
            try:
                r = ad.np_track(d.ttn)
                rows = (r or {}).get("data") or []
                if not rows or not d.stage_id:
                    continue
                row = rows[0]
                code = str(row.get("StatusCode") or "")
                npstatus = row.get("Status") or ""
                if code in ("7", "8"):
                    wdt = _parse_np_dt(row.get("WarehouseRecipientDateTime"))
                    if wdt and (datetime.now() - wdt).days >= 3:
                        st3 = _find_stage(d.funnel_id, "відділення 3 дні")
                        if st3 and st3.order > d.stage.order:
                            if _advance_deal_stage(d, st3.order, "НП: 3 дні на відділенні · %s" % npstatus):
                                moved += 1
                            _maybe_send(d, row, ctr)
                            continue
                target_sub = CODE_STAGE.get(code)
                received = False
                if target_sub == "__received__":
                    target_sub = "Отримано"; received = True
                if target_sub:
                    target = _find_stage(d.funnel_id, target_sub, received=received)
                    if target and target.order > d.stage.order:
                        if _advance_deal_stage(d, target.order, "НП: %s" % npstatus):
                            moved += 1
                if received:
                    _record_cod_payment(d, cod_hint=row.get("AfterpaymentOnGoodsCost"))  # наложка: сума з НП
                _maybe_send(d, row, ctr)
            except Exception as e:
                self.stderr.write(str(e)[:120])
        # ── АВТО-«Успішна»: доставлені («Отримано») + гроші РЕАЛЬНО на рахунку → успішна угода ──
        # Передоплата: is_paid=True одразу на отриманні. Наложка: чекаємо, поки виплата НоваПей
        # матчиться у банк-виписці (Payment.is_paid стає True). Толеранс 5₴ на округлення суми НП.
        from decimal import Decimal as _Dec
        _TOL = _Dec("5")
        won_auto = 0
        recv = (Deal.objects.filter(stage__is_won=False, stage__is_lost=False,
                                    stage__name__icontains="отримано")
                .exclude(stage__name__icontains="оплат").select_related("stage", "funnel"))
        for d in recv:
            try:
                if not d.amount or d.amount <= 0:
                    continue
                paid = sum((pp.amount for pp in d.payments.filter(is_paid=True)), _Dec("0"))
                if paid <= 0 or paid < (d.amount - _TOL):
                    continue  # немає грошей взагалі / наложка ще не надійшла — чекаємо (не закривати копійчані)
                won = _find_stage(d.funnel_id, "успішн")
                if won and won.order > d.stage.order:
                    if _advance_deal_stage(d, won.order, "авто: доставлено + гроші отримано → успішна"):
                        won_auto += 1
            except Exception as e:
                self.stderr.write(str(e)[:120])
        self.stdout.write("np sync: moved=%d sent=%d won_auto=%d" % (moved, ctr["sent"], won_auto))


def _record_cod_payment(deal, cod_hint=None):
    """Клієнт отримав посилку з наложкою → Payment(np_cod) + дохід у фінанси.
    Ідемпотентно: один np_cod-платіж на угоду (external_id=ТТН)."""
    from decimal import Decimal
    from apps.crm.models import Payment
    try:
        cod = Decimal(str((deal.np_data or {}).get("cod_amount") or 0))
        # fallback на backward.amount ЛИШЕ якщо backward.on=True (надійна ознака наложки:
        # TTN створений з післяплатою). Деякі TTN мають суму тільки у backward.amount.
        if cod <= 0:
            _bw = (deal.np_data or {}).get("backward") or {}
            if _bw.get("on") and _bw.get("amount"):
                try:
                    cod = Decimal(str(_bw.get("amount") or 0))
                except Exception:
                    cod = Decimal("0")
        if cod <= 0 and cod_hint:
            # НП підтверджує післяплату (AfterpaymentOnGoodsCost) — надійна ознака реальної наложки
            try:
                cod = Decimal(str(cod_hint or 0))
            except Exception:
                cod = Decimal("0")
        if cod <= 0:
            return
        if Payment.objects.filter(deal=deal, provider="np_cod").exists():
            return
        # клієнт ОПЛАТИВ на відділенні (фіскальний чек бʼється зараз), але ГРОШІ ще у НоваПей:
        # у сделці «оплачено» стане True лише коли виплата надійде на рахунок банку
        pay = Payment.objects.create(deal=deal, provider="np_cod", amount=cod,
                                     is_paid=False, external_id=deal.ttn or "")
        # ГРОШІ В ЖУРНАЛ НЕ ПИШЕМО: дохід зʼявиться автоматично, коли виплата від
        # НоваПей реально надійде на рахунок ПриватБанку (банківська синхронізація).
        # Payment вище — лише для сделки: «оплачено», стадії, фінальний чек.
        # фінальний фіскальний чек Checkbox на доплату: ланцюг аванс → фінал
        # (relation до авансового чека, у фіналі — ТТН; регламент післяплати)
        try:
            from apps.crm.views import _issue_checkbox_for_deal
            # РЕАЛЬНА оплата наложки (НП StatusCode=9) → чек СТВОРЮЄТЬСЯ і ВІДПРАВЛЯЄТЬСЯ клієнту.
            # notify=False лишається ТІЛЬКИ для ручного дозакриття старих хвостів.
            _issue_checkbox_for_deal(deal, user=None)
        except Exception:
            pass
    except Exception:
        pass
