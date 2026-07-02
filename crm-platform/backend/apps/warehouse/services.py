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
                                       comment="Реалізація по угоді #%s" % deal.id, author=user)
    cogs = Decimal("0")
    for it in items:
        cost = it.product.cost or Decimal("0")
        StockMovement.objects.create(document=doc, product=it.product, quantity=-it.quantity, price=cost)
        cogs += it.quantity * cost
    if cogs:
        try:
            from apps.finance.services import record_expense
            record_expense(cogs, deal=deal)
        except Exception:
            pass
    return doc, cogs, True
