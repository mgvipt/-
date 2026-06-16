"""Бухгалтерские проводки: оплата сделки -> доход, отгрузка -> расход (себестоимость)."""
from .models import Account, Category, Transaction


def default_account():
    return (Account.objects.filter(is_active=True).first()
            or Account.objects.create(name="Каса", kind="cash"))


def _category(name, direction):
    return Category.objects.get_or_create(name=name, direction=direction)[0]


def record_income(amount, *, deal=None, account=None, payment=None, category="Продаж товару"):
    return Transaction.objects.create(
        direction="in", amount=amount, account=account or default_account(),
        category=_category(category, "in"), deal=deal, payment=payment)


def record_expense(amount, *, deal=None, account=None, category="Собівартість"):
    return Transaction.objects.create(
        direction="out", amount=amount, account=account or default_account(),
        category=_category(category, "out"), deal=deal)
