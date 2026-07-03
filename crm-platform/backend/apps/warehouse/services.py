"""Сервіси складу."""


def create_warehouse_job(deal):
    """Стадія «Оплату отримано» → задача в чергу складу + WarehouseJob. Ідемпотентно."""
    from .models import WarehouseJob
    from apps.crm.models import Task
    if WarehouseJob.objects.filter(deal=deal).exclude(status="cancelled").exists():
        return None
    title = "\u0412\u0456\u0434\u0432\u0430\u043d\u0442\u0430\u0436\u0438\u0442\u0438: %s" % (deal.title or ("#%s" % deal.id))
    task = Task.objects.create(kind="warehouse", deal=deal, title=title[:255], status="open", created_by_agent=True)
    return WarehouseJob.objects.create(task=task, deal=deal, is_shipment=True, status="queued")


def realize_deal(deal, user=None):
    """Реалізація (відвантаження) товарів угоди зі складу — РІВНО ОДИН РАЗ, по СОБІВАРТОСТІ, з COGS у фінанси.
    ІДЕМПОТЕНТНО: якщо по угоді вже є видатковий (out) документ — повертає його і повторно НЕ списує
    (захист від подвійного списання, коли спрацьовують і менеджерський «Відвантажити», і кладовщик «Готово»).
    Повертає (doc, cogs, created)."""
    from decimal import Decimal
    from .models import Warehouse, StockDocument, StockMovement
    existing = StockDocument.objects.filter(kind="out", deal=deal).first()
    if existing:
        return existing, Decimal("0"), False
    items = list(deal.items.select_related("product"))
    if not items:
        return None, Decimal("0"), False
    wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
    doc = StockDocument.objects.create(kind="out", number="РН-%s" % deal.id, warehouse=wh, deal=deal,
                                       comment="Реалізація по угоді #%s" % deal.id, author=user,
                                       close_stage=(deal.stage.name if deal.stage_id else ""))
    cogs = Decimal("0")
    for it in items:
        cost = it.product.cost or Decimal("0")
        StockMovement.objects.create(document=doc, product=it.product, quantity=-it.quantity, price=cost)
        cogs += it.quantity * cost
    _on_posted(doc)  # єдина точка: COGS-витрата з тегом COGS doc#id
    return doc, cogs, True


def _weighted_cost_update(doc):
    """Прихід: ковзна середньозважена собівартість.
    cost_new = (залишок_до × cost + к-сть × ціна_приходу) / (залишок_до + к-сть).
    Якщо залишок_до <= 0 або ціна приходу нульова — cost = ціна приходу (як є)."""
    from decimal import Decimal
    for m in doc.items.select_related("product"):
        price = m.price or Decimal("0")
        if price <= 0 or m.quantity <= 0:
            continue
        p = m.product
        stock_after = p.stock(doc.warehouse) if doc.warehouse_id else p.stock()
        stock_before = Decimal(stock_after) - m.quantity
        if stock_before <= 0:
            new_cost = price
        else:
            new_cost = ((stock_before * (p.cost or Decimal("0"))) + m.quantity * price) / (stock_before + m.quantity)
        new_cost = new_cost.quantize(Decimal("0.01"))
        if p.cost != new_cost:
            p.cost = new_cost
            p.save(update_fields=["cost"])
            recalc_bundle_costs(p)


def recalc_bundle_costs(component):
    """Перерахувати cost наборів, куди входить цей товар (якщо модель складу є)."""
    try:
        from .models import ProductComponent
    except ImportError:
        return
    from decimal import Decimal
    for pc in ProductComponent.objects.filter(component=component).select_related("bundle"):
        b = pc.bundle
        total = Decimal("0")
        for row in b.components.select_related("component"):
            total += (row.component.cost or Decimal("0")) * row.quantity
        total = total.quantize(Decimal("0.01"))
        if b.cost != total:
            b.cost = total
            b.save(update_fields=["cost"])


def _on_posted(doc):
    """ЄДИНА точка грошових ефектів проведеного документа. Ідемпотентна (теги в comment).
    out(по угоді) → COGS-витрата; inv → нестача/надлишок у гроші; writeoff → витрата «Списання»;
    in → перерахунок середньозваженої собівартості."""
    from decimal import Decimal
    from apps.finance.models import Transaction

    if doc.kind == "in":
        _weighted_cost_update(doc)
        return

    if doc.kind == "out" and doc.deal_id:
        tag = "COGS doc#%s" % doc.id
        if not Transaction.objects.filter(comment=tag).exists():
            cogs = _doc_cogs(doc)
            if cogs:
                try:
                    from apps.finance.services import record_expense
                    tx = record_expense(cogs, deal=doc.deal)
                    tx.comment = tag
                    tx.save(update_fields=["comment"])
                except Exception:
                    pass
        return

    if doc.kind == "writeoff":
        tag = "WRITEOFF doc#%s" % doc.id
        if not Transaction.objects.filter(comment=tag).exists():
            total = _doc_cogs(doc)
            if total:
                try:
                    from apps.finance.services import record_expense
                    tx = record_expense(total, category="Списання товару")
                    tx.comment = tag
                    tx.save(update_fields=["comment"])
                except Exception:
                    pass
        return

    if doc.kind == "inv":
        tag = "INV doc#%s" % doc.id
        if Transaction.objects.filter(comment__startswith=tag).exists():
            return
        shortage = Decimal("0")   # нестача (qty<0)
        surplus = Decimal("0")    # надлишок (qty>0)
        for m in doc.items.all():
            val = abs(m.quantity) * (m.price or Decimal("0"))
            if m.quantity < 0:
                shortage += val
            else:
                surplus += val
        try:
            from apps.finance.services import record_expense
            from apps.finance.models import Transaction as _T
            from apps.finance.services import _category, default_account
            if shortage:
                tx = record_expense(shortage, category="Інвентаризаційна нестача")
                tx.comment = tag + " нестача"
                tx.save(update_fields=["comment"])
            if surplus:
                _T.objects.create(direction="in", amount=surplus, amount_uah=surplus,
                                  account=default_account(),
                                  category=_category("Інвентаризаційний надлишок", "in"),
                                  comment=tag + " надлишок")
        except Exception:
            pass
        return


def _on_unposted(doc):
    """Сторно грошових ефектів при скасуванні проведення (по тегах)."""
    from apps.finance.models import Transaction
    for tag in ("COGS doc#%s" % doc.id, "WRITEOFF doc#%s" % doc.id):
        Transaction.objects.filter(comment=tag).delete()
    Transaction.objects.filter(comment__startswith="INV doc#%s" % doc.id).delete()


def _doc_cogs(doc):
    """Собівартість документа = сума (кількість×ціна) по рядках (для out qty від'ємний → плюс)."""
    from decimal import Decimal
    total = Decimal("0")
    for m in doc.items.all():
        total += abs(m.quantity) * (m.price or 0)
    return total


def post_document(doc):
    """Провести документ: рухи знову рахуються у залишок; для реалізації по угоді — забронювати COGS."""
    if doc.posted:
        return False
    doc.posted = True
    doc.save(update_fields=["posted"])
    _on_posted(doc)
    return True


def unpost_document(doc):
    """Скасувати проведення: рухи перестають рахуватись (залишок повертається); COGS сторнується."""
    if not doc.posted:
        return False
    doc.posted = False
    doc.save(update_fields=["posted"])
    _on_unposted(doc)  # сторно COGS / списання / інвентаризації
    return True
