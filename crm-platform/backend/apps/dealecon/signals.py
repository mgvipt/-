"""Коли перераховувати економіку угоди — сигнали цього застосунку (чужі файли не змінюємо).

| Подія                                        | Сигнал                                   |
|----------------------------------------------|------------------------------------------|
| оплата (LiqPay / каса / наложка / реквізити)  | Payment post_save / post_delete          |
| банк: комісія LiqPay (PBFEE) / НоваПей,       | finance.Transaction post_save / delete   |
| виплата майстру / транспорт / повернення     | (лише витрати; і стара, і нова угода)    |
| склад: пакування, вага, тонування            | WarehousePayrollEntry post_save / delete |
| склад: відвантажено                          | WarehouseJob post_save (status=shipped)  |
| позиції угоди / собівартість                 | DealItem post_save / post_delete         |
| ТТН, np_data (акт НП, np_cost), сума         | Deal post_save                           |
| статус НП у поллері                          | store_np_cost() → schedule (явний виклик)|

Сам перерахунок — після commit (services.schedule_recompute), будь-яка помилка ловиться і пишеться в лог.
"""
from django.db.models.signals import post_delete, post_save, pre_save

from .services import schedule_recompute

_DEAL_FIELDS = {"np_data", "ttn", "amount", "parent_deal", "parent_deal_id", "discount_pct"}


def _sched(*ids):
    for i in ids:
        if i:
            schedule_recompute(i)


def _on_deal_save(sender, instance, created=False, update_fields=None, raw=False, **kw):
    if raw:
        return
    if created or update_fields is None or (set(update_fields) & _DEAL_FIELDS):
        _sched(instance.pk)


def _on_deal_child(sender, instance, raw=False, **kw):
    if raw:
        return
    _sched(getattr(instance, "deal_id", None))


def _on_tx_pre(sender, instance, raw=False, **kw):
    if raw or not instance.pk:
        return
    try:
        instance._dealecon_old = sender.objects.filter(pk=instance.pk).values_list("deal_id", "direction").first()
    except Exception:
        instance._dealecon_old = None


def _on_tx_save(sender, instance, raw=False, **kw):
    if raw:
        return
    old = getattr(instance, "_dealecon_old", None) or (None, None)
    ids = []
    if instance.deal_id and instance.direction == "out":
        ids.append(instance.deal_id)
    if old[0] and (old[0] != instance.deal_id or old[1] != instance.direction) and old[1] == "out":
        ids.append(old[0])       # витрату перевісили на іншу угоду / змінили тип — стара теж перераховується
    _sched(*ids)


def _on_tx_delete(sender, instance, **kw):
    if instance.deal_id and instance.direction == "out":
        _sched(instance.deal_id)


def _on_job_save(sender, instance, raw=False, **kw):
    if raw:
        return
    if getattr(instance, "status", "") == "shipped":
        _sched(instance.deal_id)


def connect():
    from django.apps import apps
    Deal = apps.get_model("crm", "Deal")
    DealItem = apps.get_model("crm", "DealItem")
    Payment = apps.get_model("crm", "Payment")
    Transaction = apps.get_model("finance", "Transaction")
    Payroll = apps.get_model("warehouse", "WarehousePayrollEntry")
    Job = apps.get_model("warehouse", "WarehouseJob")

    post_save.connect(_on_deal_save, sender=Deal, dispatch_uid="dealecon_deal_save")
    for model, uid in ((DealItem, "item"), (Payment, "payment"), (Payroll, "payroll")):
        post_save.connect(_on_deal_child, sender=model, dispatch_uid="dealecon_%s_save" % uid)
        post_delete.connect(_on_deal_child, sender=model, dispatch_uid="dealecon_%s_delete" % uid)
    pre_save.connect(_on_tx_pre, sender=Transaction, dispatch_uid="dealecon_tx_pre")
    post_save.connect(_on_tx_save, sender=Transaction, dispatch_uid="dealecon_tx_save")
    post_delete.connect(_on_tx_delete, sender=Transaction, dispatch_uid="dealecon_tx_delete")
    post_save.connect(_on_job_save, sender=Job, dispatch_uid="dealecon_job_save")
