"""Import explicit Privat bank commissions independently of their parent payment.

REF identifies a payment group, not a statement row. REFN distinguishes the
commission leg (e.g. Z) from the principal (1). Keep legacy PB# payment markers
untouched so reconciled cash/acquiring transfers retain their existing dedup.
"""
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import connection, transaction
from .models import Category, Transaction


def _norm(value):
    return " ".join((value or "").casefold().split())


def fee_details(row, account):
    purpose = row.get("OSND") or ""
    if row.get("TRANTYPE") != "D" or not re.match(r"^ком[іи]с[іи][яiя]", purpose.strip(), re.I):
        return None
    if account is None or not row.get("REF"):
        return None
    currency = row.get("CCY") or "UAH"
    # The existing journal import is UAH-only. Never relabel an FX fee as UAH.
    if currency != "UAH":
        return None
    try:
        amount = abs(Decimal(str(row.get("SUM") or row.get("SUM_E") or "0")))
        day = datetime.strptime(row["DAT_OD"], "%d.%m.%Y").date()
    except (ValueError, KeyError, InvalidOperation):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    op_time = None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            op_time = datetime.strptime(row.get("TIM_P") or "", fmt).time()
            break
        except ValueError:
            pass
    # ID includes posting time, which can change between interim/final.
    # REF+REFN is the bank's stable group/leg identity, scoped to the account.
    # Amount/date/currency also protect rows where REFN is absent.
    identity = [account.pk, row["REF"], row.get("REFN") or "", currency,
                format(amount, ".2f"), day.isoformat()]
    key = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()[:32]
    return dict(amount=amount, date=day, op_time=op_time, currency=currency,
                purpose=purpose, tag="PB-COM#" + key, ref=row["REF"])


def find_existing_fee(row, account, details=None):
    d = details or fee_details(row, account)
    if d is None:
        return None
    exact = Transaction.objects.filter(comment__startswith=d["tag"]).first()
    if exact:
        return exact  # Never overwrite manual edits on an already imported fee.
    candidates = Transaction.objects.filter(
        account=account, direction="out", amount=d["amount"],
        currency=d["currency"], date=d["date"])
    legacy = []
    for tx in candidates:
        if tx.comment.startswith("PB-COM#"):
            continue  # Different bank leg; same amount is not proof of a duplicate.
        text = tx.comment or ""
        same_ref = text.startswith("PB#%s/D" % d["ref"])
        fm = (tx.import_batch or "").startswith("FM-")
        purpose_match = _norm(d["purpose"]) in _norm(text)
        # Explicit commission purpose is required, not merely a shared amount/REF.
        if purpose_match and (same_ref or fm):
            if fm and tx.op_time and d["op_time"]:
                if (tx.op_time.hour, tx.op_time.minute) != (d["op_time"].hour, d["op_time"].minute):
                    continue
            legacy.append(tx)
    if len(legacy) > 1:
        raise ValueError("Ambiguous legacy bank fee: %s" % d["ref"])
    return legacy[0] if legacy else None


def import_privat_fee(row, account, batch, dry_run=False):
    """Return None for other rows; (transaction, created) for a bank commission."""
    d = fee_details(row, account)
    if d is None:
        return None
    with transaction.atomic():
        if not dry_run and connection.vendor == "postgresql":
            # Serialize cron/manual imports of the same bank leg.
            lock_id = int(hashlib.sha256(d["tag"].encode()).hexdigest()[:15], 16)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
        existing = find_existing_fee(row, account, d)
        if existing:
            return existing, False
        category = Category.objects.filter(name="Комиссии банка и проценты", direction="out").first()
        if category is None:
            raise ValueError("Bank fee category is missing")
        if dry_run:
            return None, True
        bank_id = str(row.get("ID") or "")
        prefix = d["tag"] + " · PB#" + d["ref"] + "/D"
        if bank_id:
            prefix += " · ID=" + bank_id
        tx = Transaction.objects.create(
            account=account, direction="out", amount=d["amount"], amount_uah=d["amount"],
            currency=d["currency"], rate=1, date=d["date"], op_time=d["op_time"],
            category=category, counterparty="ПриватБанк", import_batch=batch,
            comment=(prefix + " · " + d["purpose"])[:255])
        return tx, True
