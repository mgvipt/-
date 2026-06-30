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
