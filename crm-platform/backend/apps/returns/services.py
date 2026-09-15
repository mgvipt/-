"""Повернення товару — логіка без HTTP (16.09.2026). views.py лише перевіряє права.

| Що                         | Як                                                                                       |
|----------------------------|------------------------------------------------------------------------------------------|
| сума угоди                 | кількість у позиції зменшується (повністю повернена позиція — видаляється, знімок у рядку |
|                            | повернення); сума угоди = Σ позицій, як DealViewSet._recalc_amount                       |
| склад «як новий»           | прибуткова накладна «ПВ-<№>» (kind="in", по собівартості зі списання реалізації),        |
|                            | _on_posted → ковзна собівартість — як будь-який прихід. Не більше, ніж списала реалізація |
| склад «в брак» / «списати» | документів НЕ створюємо: товар уже списала реалізація і на полицю не повертається;        |
|                            | собівартість — втрата в економіці угоди (cost_loss)                                       |
| гроші                      | окремий крок settle_money — лише право deal.refund (бухгалтер / власник)                  |
| аванс клієнта              | advance_hold(): повернуті гроші + «очікує рішення» — не вільний аванс (2 місця crm.views) |
| «Помилка співробітника»    | WarehouseError (На розгляді, утримання 50% суми повернення) — той самий потік, що й на складі |
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import connection, transaction
from django.db.models import Q, Sum
from django.utils import timezone

D0 = Decimal("0")
Q2 = Decimal("0.01")
ERROR_REASONS = ("wh_error", "mgr_error")
ERROR_SHARE = Decimal("0.5")          # помилка співробітника — 50% (рішення Олега 11.09); лише пропозиція, підтверджує керівник
REFUND_CATEGORY_PREFIXES = ("возврат товара", "возврат денег")   # як dealecon.build_ctx і partners
LIQPAY_REFUND_PREFIX = "Повернення LiqPay по сделці"             # коментар операції, яку пише crm.views.liqpay_refund
MAX_PHOTOS = 10
MAX_PHOTO_BYTES = 15 * 1024 * 1024


class ReturnError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def _d(x):
    try:
        return Decimal(str(x if x not in (None, "") else 0).replace(",", ".").replace(" ", ""))
    except Exception:
        raise ReturnError("Невірне число: %s" % x)


def _q(x):
    return _d(x).quantize(Q2, rounding=ROUND_HALF_UP)


def fmt(x):
    """1234.5 → «1 234,50» (як у CRM)."""
    s = "{:,.2f}".format(float(_q(x))).replace(",", " ").replace(".", ",")
    return s[:-3] if s.endswith(",00") else s


def _num(x):
    x = _d(x)
    return str(x.quantize(Decimal("1"))) if x == x.to_integral_value() else str(x.normalize())


def user_name(u):
    if not u:
        return ""
    return (u.get_full_name() or u.username or "").strip()


def contact_name(c):
    if not c:
        return ""
    return (" ".join(x for x in (c.first_name, c.last_name) if x).strip() or c.nickname or c.phone or ("#%s" % c.id))


_TABLES = {}


def tables_ready():
    """Чи застосована міграція returns (у DRY на бойовій базі до деплою таблиці ще немає)."""
    if "ok" not in _TABLES:
        try:
            names = set(connection.introspection.table_names())
        except Exception:
            names = set()
        _TABLES["ok"] = "returns_dealreturn" in names
    return _TABLES["ok"]


# ───────────────────────── категорії журналу ─────────────────────────
def refund_category_ids():
    """Категорії повернень клієнту — за НАЗВОЮ, як економіка угоди і партнери (працює і в тестовій базі)."""
    from apps.finance.models import Category
    return [r["id"] for r in Category.objects.values("id", "name")
            if (r["name"] or "").strip().lower().startswith(REFUND_CATEGORY_PREFIXES)]


def refund_category():
    """Товар повернувся → «Возврат товара…» (те саме правило, що в liqpay_refund), інакше «Возврат денег…»."""
    from apps.finance.models import Category
    return (Category.objects.filter(name__istartswith="Возврат товара").order_by("id").first()
            or Category.objects.filter(name__istartswith="Возврат денег").order_by("id").first())


# ───────────────────────── гроші угоди ─────────────────────────
def deal_paid(deal):
    return sum((_d(p.amount) for p in deal.payments.all() if p.is_paid), D0)


def _money_taken(deal_id, exclude_id=None):
    """Уже вирішено/зарезервовано по угоді: повернуто журналом + зараховано в аванс + очікує рішення.
    LiqPay-повернення не рахуємо — кнопка LiqPay сама зменшує суму платежу."""
    from .models import DealReturn
    qs = DealReturn.objects.filter(deal_id=deal_id)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    done = _d(qs.filter(money_status__in=["refund", "offset"]).aggregate(s=Sum("money_amount"))["s"])
    pend = _d(qs.filter(money_status="pending").aggregate(s=Sum("money_due"))["s"])
    return done + pend


def journal_refunded(deal_id):
    """Скільки повернуто клієнту операцією журналу (платежі угоди при цьому НЕ змінюються) — для «Оплачено» в картці."""
    if not tables_ready():
        return D0
    from .models import DealReturn
    return _d(DealReturn.objects.filter(deal_id=deal_id, money_status="refund").aggregate(s=Sum("money_amount"))["s"])


def advance_hold(contact_id):
    """Частина «вільного авансу» клієнта, яка насправді НЕ вільна:
    1) гроші, уже повернені клієнту (журнал, витрата у категоріях повернень, привʼязана до клієнта / його угоди) —
       включно з поверненнями кнопкою LiqPay;
    2) повернення товару, по яких бухгалтер ще не вирішив (money_due).
    ⚠️ Викликається з ДВОХ місць crm/views.py (плитка finance() і accept_payment «З авансу клієнта») — однаково."""
    if not contact_id:
        return D0
    from apps.finance.models import Transaction
    cats = refund_category_ids()
    refunded = D0
    if cats:
        refunded = _d(Transaction.objects.filter(Q(contact_id=contact_id) | Q(deal__contact_id=contact_id),
                                                 direction="out", category_id__in=cats)
                      .aggregate(s=Sum("amount_uah"))["s"])
    pending = D0
    if tables_ready():
        from .models import DealReturn
        pending = _d(DealReturn.objects.filter(deal__contact_id=contact_id, money_status="pending")
                     .aggregate(s=Sum("money_due"))["s"])
    return refunded + pending


def econ_extra(deal_id):
    """Для економіки угоди: які операції журналу вже враховані поверненням (сума угоди зменшена — вдруге не віднімати)
    і скільки собівартості втрачено (брак / списано)."""
    if not tables_ready():
        return {"tx_ids": set(), "loss": D0}
    from .models import DealReturn
    rows = DealReturn.objects.filter(deal_id=deal_id)
    return {"tx_ids": set(rows.exclude(refund_tx__isnull=True).values_list("refund_tx_id", flat=True)),
            "loss": _d(rows.aggregate(s=Sum("cost_loss"))["s"])}


# ───────────────────────── склад ─────────────────────────
def _written_off(deal):
    """Що реально списала ПРОВЕДЕНА реалізація угоди: {product_id: (кількість, собівартість одиниці)}."""
    from apps.warehouse.models import StockMovement
    acc = {}
    for m in StockMovement.objects.filter(document__deal=deal, document__kind="out", document__posted=True) \
            .values("product_id", "quantity", "price"):
        q = abs(_d(m["quantity"]))
        row = acc.setdefault(m["product_id"], [D0, D0])
        row[0] += q
        row[1] += q * _d(m["price"])
    return {pid: (q, (v / q if q else D0)) for pid, (q, v) in acc.items()}


def _back_on_stock(deal, exclude_id=None):
    """Скільки вже оприбутковано на склад попередніми поверненнями цієї угоди: {product_id: кількість}."""
    from apps.warehouse.models import StockMovement
    from .models import DealReturn
    docs = DealReturn.objects.filter(deal=deal, receipt_doc__isnull=False)
    if exclude_id:
        docs = docs.exclude(pk=exclude_id)
    ids = list(docs.values_list("receipt_doc_id", flat=True))
    if not ids:
        return {}
    return {r["product_id"]: _d(r["q"]) for r in StockMovement.objects.filter(document_id__in=ids, document__posted=True)
            .values("product_id").annotate(q=Sum("quantity"))}


def _stock_rows(product, qty):
    """Рядок угоди → [(товар, кількість)] для складу: набір розгортається в компоненти (як realize_deal), послуги — ні."""
    comps = list(product.components.select_related("component"))
    if comps:
        return [(r.component, qty * r.quantity) for r in comps if r.component.track_stock]
    return [(product, qty)] if product.track_stock else []


def _pick_blamed(reason, deal, data):
    """Хто помилився: явно з форми, інакше склад — виконавець відвантаження, менеджер — відповідальний за угоду."""
    from apps.accounts.models import User
    from apps.warehouse.models import WarehouseJob
    job = WarehouseJob.objects.filter(deal=deal).exclude(status="cancelled").order_by("-shipped_at", "-id").first()
    bid = data.get("blamed") or None
    if not bid:
        bid = (job.assignee_id if job else None) if reason == "wh_error" else deal.owner_id
    try:
        bid = int(bid) if bid else None
    except (TypeError, ValueError):
        bid = None
    if bid and not User.objects.filter(pk=bid, is_active=True).exists():
        bid = None
    return bid, (job if reason == "wh_error" else None)


# ───────────────────────── 1. повернення товару ─────────────────────────
def register_return(deal, user, data):
    """Оформити повернення товару. Повертає (DealReturn, created). Усе в одній транзакції: або все, або нічого.
    data: {lines: [{item, quantity, destination}], reason, delivery_payer, delivery_cost, comment, blamed, client_key}"""
    from apps.crm.models import Deal, DealItem, log_activity
    from apps.warehouse.models import StockDocument, StockMovement, Warehouse, WarehouseError
    from apps.warehouse.services import _on_posted
    from .models import DealReturn, DealReturnLine

    reason = str(data.get("reason") or "").strip()
    if reason not in dict(DealReturn.REASONS):
        raise ReturnError("Оберіть причину повернення.")
    payer = str(data.get("delivery_payer") or "client")
    if payer not in dict(DealReturn.PAYERS):
        raise ReturnError("Хто платить доставку повернення: «ми» або «клієнт».")
    dcost = _q(data.get("delivery_cost") or 0)
    if dcost < 0:
        raise ReturnError("Вартість доставки не може бути відʼємною.")
    key = str(data.get("client_key") or "").strip()[:64]
    wanted = {}
    for r in data.get("lines") or []:
        try:
            iid = int(r.get("item"))
        except (TypeError, ValueError, AttributeError):
            raise ReturnError("Невірна позиція угоди.")
        q = _q(r.get("quantity"))
        if q < 0:
            raise ReturnError("Кількість не може бути відʼємною.")
        if q == 0:
            continue
        dest = str(r.get("destination") or "stock")
        if dest not in dict(DealReturnLine.DESTINATIONS):
            raise ReturnError("Куди йде товар: на склад як новий / в брак / списати.")
        if iid in wanted:
            raise ReturnError("Одна позиція двічі в одному поверненні.")
        wanted[iid] = (q, dest)
    if not wanted:
        raise ReturnError("Вкажіть, скільки товару повернулось (хоча б одна позиція).")

    with transaction.atomic():
        deal = Deal.objects.select_for_update().get(pk=deal.pk)
        if key:
            ex = DealReturn.objects.filter(client_key=key).first()
            if ex is not None:
                if ex.deal_id != deal.pk:
                    raise ReturnError("Цю форму вже збережено для іншої угоди — оновіть сторінку.", 409)
                return ex, False
        items = {i.id: i for i in DealItem.objects.select_related("product").select_for_update(of=("self",))
                 .filter(deal=deal, id__in=list(wanted))}
        for iid, (q, _dest) in wanted.items():
            it = items.get(iid)
            if it is None:
                raise ReturnError("Позиції немає в цій угоді (можливо, її вже змінили — оновіть картку).")
            if q > _d(it.quantity):
                nm = (it.product.name if it.product_id else it.custom_name) or "позиція"
                raise ReturnError("«%s»: повернути можна не більше %s (стільки в угоді)." % (nm, _num(it.quantity)))

        ret = DealReturn.objects.create(
            deal=deal, contact_id=deal.contact_id, manager_id=deal.owner_id, created_by=user, client_key=key,
            reason=reason, delivery_payer=payer, delivery_cost=dcost, comment=str(data.get("comment") or "")[:2000])

        written = _written_off(deal)
        back_before = _back_on_stock(deal, exclude_id=ret.pk)
        stock_in, capped, texts = {}, [], []
        total = cost_back = cost_loss = D0
        for iid, (q, dest) in wanted.items():
            it = items[iid]
            p = it.product if it.product_id else None
            sold = _d(it.quantity)
            old_total = _d(it.total)
            unit_cost = _d(it.cost) if _d(it.cost) > 0 else (_d(p.cost) if p is not None else D0)
            name = ((p.name if p is not None else it.custom_name) or "позиція")[:255]
            unit_price = _d(it.price)
            if q >= sold:
                it.delete()           # повністю повернено: 0 × ціна з «мінімалкою» дала б не нуль
                new_total = D0
            else:
                it.quantity = sold - q
                it.save(update_fields=["quantity"])
                new_total = _d(it.total)
            val = _q(old_total - new_total)
            DealReturnLine.objects.create(ret=ret, deal_item_id=iid, product=p, name=name, unit=(p.unit if p is not None else ""),
                                          quantity=q, sold_quantity=sold, unit_price=unit_price, amount=val,
                                          unit_cost=_q(unit_cost), destination=dest)
            total += val
            if dest == "stock":
                cost_back += q * unit_cost
            else:
                cost_loss += q * unit_cost
            texts.append("%s × %s (%s)" % (name, _num(q), dict(DealReturnLine.DESTINATIONS)[dest].lower()))
            if dest == "stock" and p is not None:
                for sp, sq in _stock_rows(p, q):
                    w_q, w_price = written.get(sp.id, (D0, D0))
                    taken = stock_in[sp.id][1] if sp.id in stock_in else D0
                    free = w_q - back_before.get(sp.id, D0) - taken
                    take = min(sq, free) if free > 0 else D0
                    if take < sq:
                        capped.append("%s — %s з %s" % (sp.name, _num(sq - take), _num(sq)))
                    if take > 0:
                        row = stock_in.setdefault(sp.id, [sp, D0, w_price if w_price > 0 else _d(sp.cost)])
                        row[1] += take

        # сума угоди = Σ позицій — та сама формула, що DealViewSet._recalc_amount (без авто-стадій: повернення стадію не рухає)
        deal.amount = sum((_d(i.total) for i in deal.items.all()), D0)
        deal.save(update_fields=["amount"])

        notes = []
        if stock_in:
            wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
            if wh is None:
                notes.append("складу в CRM немає — прихід не створено")
            else:
                doc = StockDocument.objects.create(
                    kind="in", number="ПВ-%s" % ret.pk, warehouse=wh, author=user, doc_date=timezone.localdate(),
                    comment=("Повернення від клієнта №%s по угоді #%s" % (ret.pk, deal.pk))[:255])
                for sp, sq, price in stock_in.values():
                    StockMovement.objects.create(document=doc, product=sp, quantity=sq, price=_q(price))
                _on_posted(doc)        # прихід: ковзна собівартість — як будь-який прихід
                ret.receipt_doc = doc
        if capped:
            notes.append("не оприбутковано (реалізація цього не списувала): " + "; ".join(capped))

        over = deal_paid(deal) - _money_taken(deal.pk, exclude_id=ret.pk) - _d(deal.amount)
        due = _q(min(total, over)) if over > 0 else D0
        ret.amount = _q(total)
        ret.cost_back = _q(cost_back)
        ret.cost_loss = _q(cost_loss)
        ret.money_due = due
        ret.money_status = "pending" if due > 0 else "none"
        ret.stock_note = "; ".join(notes)[:255]

        if reason in ERROR_REASONS:
            bid, job = _pick_blamed(reason, deal, data)
            ret.error = WarehouseError.objects.create(
                job=job, deal=deal, reported_by=user, source="manager", kind="other", blamed_user_id=bid,
                deduction_uah=_q(ret.amount * ERROR_SHARE),
                description=("Повернення №%s по угоді #%s — %s. Товари: %s. Сума повернення %s ₴, утримання 50%% — "
                             "пропозиція, керівник підтверджує або змінює." % (
                                 ret.pk, deal.pk, dict(DealReturn.REASONS)[reason].lower(), "; ".join(texts),
                                 fmt(ret.amount)))[:1000])
        ret.save()
        log_activity("deal", deal.pk, "Повернення товару",
                     "№%s · %s · %s · сума угоди −%s ₴%s" % (
                         ret.pk, dict(DealReturn.REASONS)[reason], "; ".join(texts), fmt(ret.amount),
                         (" · гроші: чекає рішення бухгалтера %s ₴" % fmt(due)) if due > 0 else ""), user)
    return ret, True


# ───────────────────────── 2. гроші (лише deal.refund) ─────────────────────────
def settle_money(ret_id, user, data):
    """Рішення по грошах: refund — операція «Повернення коштів» у журналі; liqpay — гроші вже повернула кнопка LiqPay
    (привʼязати її операцію); offset — зарахувати в наступне замовлення (лишається авансом клієнта)."""
    from apps.crm.models import log_activity
    from apps.finance.models import Account, Transaction
    from .models import DealReturn

    mode = str(data.get("mode") or "")
    with transaction.atomic():
        ret = DealReturn.objects.select_for_update().filter(pk=ret_id).first()
        if ret is None:
            raise ReturnError("Повернення не знайдено.", 404)
        if ret.money_status != "pending":
            raise ReturnError("Рішення по грошах уже є: %s." % ret.get_money_status_display().lower(), 409)
        deal = ret.deal
        if deal is None:
            raise ReturnError("Угоду видалено — гроші оформіть у журналі вручну.")
        upd = ["money_status", "money_amount", "money_by", "money_at", "money_comment"]
        if mode == "refund":
            amt = _q(data.get("amount") or ret.money_due)
            if amt <= 0 or amt > ret.money_due:
                raise ReturnError("Сума повернення — від 0,01 до %s ₴." % fmt(ret.money_due))
            acc = Account.objects.filter(pk=data.get("account") or 0, is_active=True).first()
            if acc is None:
                raise ReturnError("Оберіть рахунок, з якого повертаєте гроші.")
            src = Transaction.objects.filter(deal=deal, direction="in").order_by("-date", "-id").first()
            tx = Transaction.objects.create(
                direction="out", amount=amt, account=acc, category=refund_category(),
                fin_direction=(src.fin_direction if src else None), date=timezone.localdate(),
                deal=deal, contact_id=deal.contact_id, counterparty=contact_name(deal.contact)[:160],
                comment=("Повернення коштів: повернення товару №%s по угоді #%s" % (ret.pk, deal.pk))[:255])
            ret.refund_tx = tx
            upd.append("refund_tx")
            ret.money_amount = amt
            ret.money_status = "refund"
            rest = ret.money_due - amt
            ret.money_comment = ("решта %s ₴ лишилась клієнту авансом" % fmt(rest)) if rest > 0 else ""
            what = "повернуто клієнту %s ₴ (%s)" % (fmt(amt), acc.name)
        elif mode == "liqpay":
            tx = Transaction.objects.filter(pk=data.get("tx") or 0, deal=deal, direction="out",
                                            category_id__in=refund_category_ids(),
                                            comment__startswith=LIQPAY_REFUND_PREFIX).first()
            if tx is None or DealReturn.objects.filter(refund_tx=tx).exists():
                raise ReturnError("Оберіть повернення LiqPay цієї угоди, ще не привʼязане до іншого повернення.")
            ret.refund_tx = tx
            upd.append("refund_tx")
            ret.money_amount = _q(tx.amount_uah or tx.amount)
            ret.money_status = "liqpay"
            ret.money_comment = ""
            what = "повернуто через LiqPay %s ₴" % fmt(ret.money_amount)
        elif mode == "offset":
            ret.money_amount = ret.money_due
            ret.money_status = "offset"
            ret.money_comment = "%s ₴ — аванс клієнта: наступне замовлення оплатити «З авансу клієнта»" % fmt(ret.money_due)
            what = "зараховано в наступне замовлення %s ₴" % fmt(ret.money_due)
        else:
            raise ReturnError("Оберіть: повернути гроші / вже повернуто через LiqPay / зарахувати в наступне замовлення.")
        ret.money_by = user
        ret.money_at = timezone.now()
        ret.save(update_fields=upd)
        log_activity("deal", deal.pk, "Повернення коштів", "Повернення товару №%s: %s" % (ret.pk, what), user)
    return ret


# ───────────────────────── 3. звіт ─────────────────────────
def report(d1, d2, show_cost=False):
    """Звіт «Повернення» за період (дата оформлення): скільки, чому, по матеріалах, по людях."""
    from .models import DealReturn, DealReturnLine
    rets = list(DealReturn.objects.filter(created_at__date__gte=d1, created_at__date__lte=d2)
                .select_related("deal", "manager", "contact", "error", "error__blamed_user")
                .prefetch_related("lines", "lines__product", "lines__product__category"))
    reasons = dict(DealReturn.REASONS)
    dests = dict(DealReturnLine.DESTINATIONS)
    tot = {"count": len(rets), "amount": D0, "refunded": D0, "offset": D0, "pending": D0, "loss": D0,
           "delivery_us": D0, "deals": len({r.deal_id for r in rets if r.deal_id})}
    by_reason, by_dest, by_mat, by_prod, by_person, by_blamed = {}, {}, {}, {}, {}, {}
    rows = []
    for r in rets:
        amt = _d(r.amount)
        tot["amount"] += amt
        if r.money_status in ("refund", "liqpay"):
            tot["refunded"] += _d(r.money_amount)
        elif r.money_status == "offset":
            tot["offset"] += _d(r.money_amount)
        elif r.money_status == "pending":
            tot["pending"] += _d(r.money_due)
        tot["loss"] += _d(r.cost_loss)
        if r.delivery_payer == "us":
            tot["delivery_us"] += _d(r.delivery_cost)
        g = by_reason.setdefault(r.reason, {"code": r.reason, "label": reasons.get(r.reason, r.reason), "count": 0, "amount": D0})
        g["count"] += 1
        g["amount"] += amt
        pname = user_name(r.manager) or "без відповідального"
        g = by_person.setdefault(pname, {"name": pname, "count": 0, "amount": D0, "errors": 0})
        g["count"] += 1
        g["amount"] += amt
        if r.reason in ERROR_REASONS:
            g["errors"] += 1
            e = r.error
            bname = user_name(e.blamed_user) if (e and e.blamed_user_id) else "не вказано"
            b = by_blamed.setdefault(bname, {"name": bname, "count": 0, "deduction": D0, "confirmed": 0})
            b["count"] += 1
            if e is not None and e.status == "confirmed":
                b["confirmed"] += 1
                b["deduction"] += _d(e.deduction_uah)
        mats = set()
        for ln in r.lines.all():
            la = _d(ln.amount)
            g = by_dest.setdefault(ln.destination, {"code": ln.destination, "label": dests.get(ln.destination, ln.destination),
                                                    "lines": 0, "amount": D0})
            g["lines"] += 1
            g["amount"] += la
            p = ln.product
            mat = (p.category.name if (p is not None and p.category_id) else (p.name if p is not None else ln.name)) or "—"
            g = by_mat.setdefault(mat, {"name": mat, "count": 0, "amount": D0})
            if mat not in mats:
                g["count"] += 1
                mats.add(mat)
            g["amount"] += la
            key = ln.product_id or ("custom:" + ln.name)
            g = by_prod.setdefault(key, {"name": ln.name, "unit": ln.unit, "qty": D0, "amount": D0, "count": 0})
            g["qty"] += _d(ln.quantity)
            g["amount"] += la
            g["count"] += 1
        if len(rows) < 300:
            rows.append({"id": r.pk, "date": timezone.localtime(r.created_at).date().isoformat(), "deal_id": r.deal_id,
                         "deal_title": (r.deal.title if r.deal_id else ""), "client": contact_name(r.contact),
                         "manager": user_name(r.manager), "reason": reasons.get(r.reason, r.reason),
                         "amount": float(amt), "money": r.get_money_status_display(),
                         "lines": "; ".join("%s × %s (%s)" % (ln.name, _num(ln.quantity), dests.get(ln.destination, "").lower())
                                            for ln in r.lines.all())})

    def _fl(rows_, *keys):
        out = []
        for x in rows_:
            y = dict(x)
            for k in keys:
                y[k] = float(_q(y[k]))
            out.append(y)
        return out

    if not show_cost:
        tot.pop("loss")
    return {"from": d1.isoformat(), "to": d2.isoformat(), "show_cost": bool(show_cost),
            "totals": {k: (float(_q(v)) if isinstance(v, Decimal) else v) for k, v in tot.items()},
            "by_reason": _fl(sorted(by_reason.values(), key=lambda x: -x["count"]), "amount"),
            "by_destination": _fl(sorted(by_dest.values(), key=lambda x: -x["amount"]), "amount"),
            "by_material": _fl(sorted(by_mat.values(), key=lambda x: -x["amount"]), "amount"),
            "by_product": _fl(sorted(by_prod.values(), key=lambda x: -x["amount"])[:30], "qty", "amount"),
            "by_person": _fl(sorted(by_person.values(), key=lambda x: -x["amount"]), "amount"),
            "by_blamed": _fl(sorted(by_blamed.values(), key=lambda x: -x["count"]), "deduction"),
            "rows": rows}
