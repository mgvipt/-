"""File imports only. No bank access; unresolved legacy matches never create money."""
import csv
import hashlib
import io
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Q
from .models import Account, StatementRow, Transaction


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def number(value):
    try:
        result = Decimal(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise ValueError("Некоректна сума/курс")
    if not result.is_finite():
        raise ValueError("Некоректна сума/курс")
    return result


def parse_statement(raw, account, currency="UAH", rate=None, rates=None):
    reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")), delimiter=";" if raw.count(";") >= raw.count(",") else ",")
    file_hash = digest([account.pk, raw, currency, str(rate)])
    rows, errors = [], []
    aliases = {
        "date": ["дата", "дата операції", "дата і час", "date", "dat_od"], "time": ["час", "время", "time", "tim_p"],
        "amount": ["сума", "сума в валюті рахунку", "сума у валюті рахунку", "сумма", "amount", "sum_e", "sum"],
        "description": ["призначення", "назначение", "опис", "description", "osnd"],
        "counterparty": ["контрагент", "кореспондент", "counterparty"],
        "currency": ["валюта", "валюта рахунку", "currency", "ccy"], "rate": ["курс", "rate"],
        "bank_id": ["bank_id", "id операції", "id операции", "id транзакції", "ref"],
        "leg": ["refn", "bank_leg"], "direction": ["напрямок", "тип", "direction", "trantype"],
        "transfer_account": ["transfer_account", "рахунок отримувача"],
        "transfer_amount": ["transfer_amount", "сума отримувача"],
        "original_amount": ["original_amount"], "original_currency": ["original_currency"],
        "balance": ["balance"], "balance_currency": ["balance_currency"], "card": ["card"],
    }
    headers = {str(h).strip().lower(): h for h in (reader.fieldnames or [])}
    columns = {k: next((headers[a] for a in names if a in headers), None) for k, names in aliases.items()}
    if not columns["date"] or not columns["amount"]:
        raise ValueError("Потрібні колонки Дата та Сума")
    for index, raw_row in enumerate(reader, 2):
        if not any(str(v or "").strip() for v in raw_row.values()):
            continue
        get = lambda k: str(raw_row.get(columns[k]) or "").strip() if columns[k] else ""
        try:
            ds = get("date")
            parsed = None
            for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    parsed = datetime.strptime(ds[:10], fmt); break
                except ValueError:
                    pass
            if parsed is None:
                raise ValueError("Некоректна дата")
            ts = get("time") or ds[11:19]
            op_time = datetime.strptime(ts, "%H:%M:%S" if ts.count(":") == 2 else "%H:%M").time() if ts else None
            signed = number(get("amount"))
            if signed == 0 or signed != signed.quantize(Decimal("0.01")):
                raise ValueError("Сума має бути ненульова, до 2 знаків")
            cur = (get("currency") or currency).upper()
            if not re.fullmatch(r"[A-Z]{3}", cur):
                raise ValueError("Вкажіть валюту ISO (UAH/USD/EUR)")
            fx_raw = get("rate") or rate or ("1" if cur == "UAH" else "")
            fx = number(fx_raw) if fx_raw else None
            if fx is not None and (fx <= 0 or (cur == "UAH" and fx != 1)):
                raise ValueError("Вкажіть коректний курс на дату операції")
            direction = get("direction").lower()
            if direction in ("d", "д", "дебет", "out", "расход", "витрата"):
                direction = "out"
            elif direction in ("c", "к", "кредит", "in", "доход", "дохід"):
                direction = "in"
            elif direction not in ("", "transfer"):
                raise ValueError("Невідомий напрямок")
            direction = direction or ("out" if signed < 0 else "in")
            dest = None
            transfer_amount = None
            if direction == "transfer":
                dest = Account.objects.filter(pk=get("transfer_account"), is_active=True).first()
                if not dest or dest.pk == account.pk:
                    raise ValueError("Для переказу виберіть інший власний рахунок")
                transfer_amount = number(get("transfer_amount"))
                if transfer_amount <= 0:
                    raise ValueError("Потрібна сума зарахування переказу")
            bank_id, leg = get("bank_id"), get("leg")
            if len(bank_id) > 160 or len(leg) > 160:
                raise ValueError("Задовгий банківський ID")
            attrs = dict(account=account, date=parsed.date(), op_time=op_time, amount=abs(signed),
                         currency=cur, rate=fx, direction=direction, counterparty=get("counterparty")[:160],
                         comment=("Виписка · " + get("description"))[:255], transfer_account=dest,
                         transfer_amount=transfer_amount)
            metadata = {}
            complete = all(columns[k] and get(k) for k in ("original_amount", "original_currency", "balance", "balance_currency")) and op_time is not None
            if complete:
                original_amount = number(get("original_amount"))
                balance = number(get("balance"))
                original_currency = get("original_currency").upper()
                balance_currency = get("balance_currency").upper()
                if original_amount < 0 or balance_currency != cur or not re.fullmatch(r"[A-Z]{3}", original_currency):
                    raise ValueError("Некоректні вихідні реквізити банківської строки")
                metadata = {"schema": "privat-card-v1", "account_id": account.pk,
                            "datetime": parsed.date().isoformat() + "T" + op_time.isoformat(),
                            "signed_amount": format(signed.quantize(Decimal("0.01")), "f"), "currency": cur,
                            "original_amount": format(original_amount.quantize(Decimal("0.01")), "f"),
                            "original_currency": original_currency, "description": get("description"),
                            "balance": format(balance.quantize(Decimal("0.01")), "f"), "balance_currency": balance_currency, "source_card": re.sub(r"\D", "", get("card"))[-4:]}
            # Full ledger identity excludes filename, row order, category and FX analytics rate.
            key = digest([account.pk, cur, direction, bank_id, leg]) if bank_id else digest({k:v for k,v in metadata.items() if k != "source_card"}) if metadata else digest([file_hash, index])
            if rates and key in rates:
                attrs["rate"] = number(rates[key])
                if attrs["rate"] <= 0 or (cur == "UAH" and attrs["rate"] != 1):
                    raise ValueError("Некоректний погоджений курс")
            rows.append(dict(line=index, key=key, file_hash=file_hash, bank_id=bank_id, attrs=attrs,
                             description=get("description"), leg=leg, source_data=metadata, complete_identity=bool(metadata)))
        except (ValueError, TypeError, InvalidOperation) as exc:
            errors.append({"line": index, "reason": str(exc)})
    return rows, errors


def import_statement(raw, account, *, commit=False, currency="UAH", rate=None, closed_until=None,
                     date_from=None, date_to=None, apply_rules=None, approved_keys=None, rates=None):
    rows, errors = parse_statement(raw, account, currency, rate, rates)
    result = dict(created=0, duplicates=0, errors=len(errors), review=0, skipped_closed=0,
                  skipped_bank=0, committed=commit, account=account.name, preview=[], issues=errors, batch=None)
    batch = "ST-" + digest([account.pk, raw, currency, str(rate)])[:32]
    # Lock the account for overlapping/concurrent imports; no financial writes in preview.
    with transaction.atomic():
        if commit:
            Account.objects.select_for_update().get(pk=account.pk)
        seen = set()
        for row in rows:
            a, key = row["attrs"], row["key"]
            if date_from and a["date"].isoformat() < date_from or date_to and a["date"].isoformat() > date_to:
                continue
            status, reason = "new", ""
            source = StatementRow.objects.filter(key=key).select_related("transaction").first()
            if source:
                old = source.transaction
                same = all(getattr(old, k) == a[k] for k in ("amount", "date", "direction", "currency", "op_time", "transfer_account", "transfer_amount")) and (a["rate"] is None or old.rate == a["rate"])
                if source.source_data.get("legacy_resolution") and {k:v for k,v in source.source_data.items() if k not in ("legacy_resolution", "source_card")} == {k:v for k,v in row["source_data"].items() if k != "source_card"}:
                    same = old.account_id == account.pk and all(getattr(old, k) == a[k] for k in ("amount", "date", "direction", "currency"))
                if old.direction == "transfer" and source.source_data and {k:v for k,v in source.source_data.items() if k not in ("legacy_resolution", "source_card")} == {k:v for k,v in row["source_data"].items() if k != "source_card"}:
                    same = (a["direction"] == "out" and old.account_id == account.pk and old.amount == a["amount"] and old.currency == a["currency"]) or (a["direction"] == "in" and old.transfer_account_id == account.pk and (old.transfer_amount or old.amount) == a["amount"])
                status, reason = ("duplicate", "") if same else ("review", "Банківський ID вже має інші реквізити")
            elif key in seen:
                status, reason = "review", "Повтор повної ідентичності усередині файлу; потрібне уточнення"
            else:
                existing = Transaction.objects.filter(account=account, date=a["date"], amount=a["amount"],
                                                      currency=a["currency"], direction=a["direction"])
                existing = existing.exclude(statement_row__file_hash=row["file_hash"])
                if row["complete_identity"]:
                    existing = existing.exclude(statement_row__source_data__schema="privat-card-v1")
                if row["bank_id"]:
                    legacy = Transaction.objects.filter(account=account, comment__startswith="PB#" + row["bank_id"] + "/")
                    # Old PB group identities cannot safely distinguish commission legs.
                    if legacy.exists():
                        status, reason = "review", "Є банківська операція старого імпорту; звірте ID/комісію"
                    elif existing.filter(statement_row__isnull=True).exists():
                        status, reason = "review", "Є стара операція без збереженого ID: спершу звірте перекриття"
                elif existing.exists():
                    status, reason = "review", "Немає банківського ID: можливе перекриття з журналом"
                if status == "new" and row["complete_identity"]:
                    meta = row["source_data"]
                    old_native = Transaction.objects.filter(account=account, date=a["date"], direction=a["direction"],
                        currency=meta["original_currency"], amount=number(meta["original_amount"]), statement_row__isnull=True)
                    old_time = Transaction.objects.filter(account=account, date=a["date"], op_time=a["op_time"], statement_row__isnull=True)
                    if old_native.exists() or old_time.exists():
                        status, reason = "review", "Є стара операція за вихідною сумою/часом; звірте комісію та обидва реквізити, не додаємо другі гроші"
                if status == "new" and a["direction"] == "in":
                    transfers = Transaction.objects.filter(direction="transfer", transfer_account=account, date=a["date"])
                    if transfers.filter(Q(transfer_amount=a["amount"]) | Q(transfer_amount__isnull=True, amount=a["amount"])).exists():
                        status, reason = "review", "Можливе друге плече власного переказу: не додаємо прихід повторно"
                if status == "new" and a["direction"] == "out" and Transaction.objects.filter(direction="transfer", account=account, date=a["date"], amount=a["amount"], currency=a["currency"]).exists():
                    status, reason = "review", "Можливе перше плече вже внесеного власного переказу"
            if status == "new" and approved_keys is not None and key not in approved_keys:
                status, reason = "review", "Строка не входить до підтвердженого списку нових історичних рухів"
            if status == "new" and not row["bank_id"] and not row["complete_identity"]:
                status, reason = "review", "Недостатньо реквізитів для сталої ідентичності: потрібен ID або час, сума/валюта операції та банківський залишок"
            if status == "new" and a["rate"] is None:
                status, reason = "review", "Немає підтвердженого курсу на дату операції; суму у валюті збережено в предпросмотрі"
            if status == "new" and re.search(r"(?:переказ|перевод|transfer|поповнення).*?(?:карт|card)|(?:карт|card).*?(?:переказ|перевод|transfer)|(?:на свою|зі своєї|з власної|со своей).*?(?:карт|card)|переказ власн|перевод собственн|власних кошт|own funds", row["description"], re.I):
                status, reason = "review", "Можливий власний переказ: підтвердіть і зв’яжіть обидва плеча"
            if closed_until and a["date"] <= closed_until and status in ("new", "review"):
                status, reason = "closed", "Закритий період" + (" · " + reason if reason else "")
            seen.add(key)
            result["preview"].append({"line": row["line"], "date": str(a["date"]), "time": str(a["op_time"] or ""),
                                      "dir": a["direction"], "amount": str(a["amount"]), "currency": a["currency"],
                                      "rate": str(a["rate"]), "bank_id": row["bank_id"], "osnd": row["description"],
                                      "status": status, "reason": reason, "source_key": key, "source_data": row["source_data"], "identity": "ledger" if row["complete_identity"] else "bank_id" if row["bank_id"] else "file_only"})
            if status == "duplicate":
                result["duplicates"] += 1; continue
            if status == "review":
                result["review"] += 1; continue
            if status == "closed":
                result["skipped_closed"] += 1; continue
            if commit:
                if apply_rules and a["direction"] != "transfer":
                    rule = apply_rules(a["direction"], row["description"], a["counterparty"], account.name)
                    a.update({k: rule[k] for k in ("category", "fin_direction", "fin_article", "channel")})
                    a["counterparty"] = rule["counterparty"]
                tx = Transaction.objects.create(**a, import_batch=batch)
                # Transaction.save supplies current time when absent; preserve the statement's unknown time.
                if a["op_time"] is None:
                    Transaction.objects.filter(pk=tx.pk).update(op_time=None)
                StatementRow.objects.create(key=key, file_hash=row["file_hash"], bank_id=row["bank_id"], bank_leg=row["leg"], source_data=row["source_data"], transaction=tx)
            result["created"] += 1
    result["batch"] = batch if commit else None
    return result
