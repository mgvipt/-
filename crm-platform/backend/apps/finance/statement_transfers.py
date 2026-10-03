"""Explicitly confirmed two bank legs map to one existing CRM transfer, never two incomes."""
from datetime import datetime
from decimal import Decimal
from django.db import transaction
from .models import Account, StatementRow, Transaction
from .statement_import import parse_statement, digest


def link_statement_transfer(source_account, source_csv, source_key, destination_account, destination_csv,
                            destination_key, *, commit=False, existing_transfer_id=None, rate=None, closed_until=None):
    source_rows, e1 = parse_statement(source_csv, source_account, rate=rate)
    destination_rows, e2 = parse_statement(destination_csv, destination_account)
    s = next((r for r in source_rows if r['key'] == source_key), None)
    d = next((r for r in destination_rows if r['key'] == destination_key), None)
    if not s or not d or not s['complete_identity'] or not d['complete_identity']:
        raise ValueError('Обидва плеча потребують повних банківських реквізитів та точного ключа строки')
    a,b = s['attrs'],d['attrs']
    if source_account.pk == destination_account.pk or a['direction'] != 'out' or b['direction'] != 'in':
        raise ValueError('Потрібні списання і зарахування на різних підтверджених власних рахунках')
    t1=datetime.fromisoformat(s['source_data']['datetime']);t2=datetime.fromisoformat(d['source_data']['datetime'])
    if abs((t1-t2).total_seconds())>2:
        raise ValueError('Дати/час двох плечей не узгоджуються; потрібна окрема звірка')
    if a['currency']==b['currency'] and a['amount'] != b['amount']:
        raise ValueError('Суми переказу не узгоджуються; не вигадуємо комісію')
    # For FX the two bank ledger amounts are authoritative; their difference is not a fee.
    # Explicit confirmation and reciprocal references bind the legs, no guessed FX amount.
    for row, other_row, other_account in ((s,d,destination_account),(d,s,source_account)):
        # User-confirmed CRM mapping may intentionally differ from the source card label.
        digits = other_row['source_data'].get('source_card') or ''.join(c for c in other_account.name if c.isdigit())[-4:]
        if len(digits) != 4 or digits not in row['description']:
            raise ValueError('Немає взаємного посилання на вихідні картки банку; потрібна ручна звірка')
    if closed_until and min(a['date'],b['date']) <= closed_until:
        raise ValueError('Закритий період')
    with transaction.atomic():
        if commit:
            list(Account.objects.select_for_update().filter(pk__in=[source_account.pk,destination_account.pk]).order_by('pk'))
        links=list(StatementRow.objects.filter(key__in=[s['key'],d['key']]).select_related('transaction'))
        linked_ids={r.transaction_id for r in links}
        if len(linked_ids)>1:
            raise ValueError('Плеча вже належать різним операціям; існуючі записи не переписуємо')
        tid=existing_transfer_id or (next(iter(linked_ids)) if linked_ids else None)
        tx=Transaction.objects.select_for_update().filter(pk=tid).first() if tid else None
        if tid and not tx:
            raise ValueError('Існуючий переказ не знайдено')
        if tx:
            if not (tx.direction=='transfer' and tx.account_id==source_account.pk and tx.transfer_account_id==destination_account.pk and
                    tx.amount==a['amount'] and (tx.transfer_amount or tx.amount)==b['amount'] and tx.currency==a['currency'] and
                    tx.date==a['date'] and (tx.op_time is None or abs((datetime.combine(tx.date,tx.op_time)-t1).total_seconds())<=2)):
                raise ValueError('Існуюча операція не відповідає обом плечам переказу')
            if linked_ids and linked_ids!={tx.pk}:
                raise ValueError('Конфлікт існуючих зв’язків')
        else:
            for acc, attrs in ((source_account,a),(destination_account,b)):
                if Transaction.objects.filter(account=acc,date=attrs['date'],amount=attrs['amount'],currency=attrs['currency']).exists() or Transaction.objects.filter(direction='transfer',transfer_account=acc,date=attrs['date'],transfer_amount=attrs['amount']).exists():
                    raise ValueError('Є кандидати старого журналу: спершу підтвердіть існуючий переказ, не створюємо новий')
            if a['rate'] is None:
                raise ValueError('Для списання потрібен підтверджений курс на дату операції')
        if commit:
            if not tx:
                attrs={**a,'direction':'transfer','transfer_account':destination_account,'transfer_amount':b['amount']}
                tx=Transaction.objects.create(**attrs,import_batch='ST-PAIR-'+digest([s['key'],d['key']])[:24])
            for row in (s,d):
                StatementRow.objects.get_or_create(key=row['key'],defaults={'transaction':tx,'file_hash':row['file_hash'],'source_data':row['source_data'],'bank_id':row['bank_id'],'bank_leg':row['leg']})
        return {'confirmed_legs':2,'new_transactions':0 if tid else 1,'duplicate':len(links)==2,
                'transaction_id':tx.pk if tx else None,'committed':commit,'source_key':s['key'],'destination_key':d['key']}
