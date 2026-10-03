"""Explicit legacy reconciliation adds bank provenance only; journal money/classification stay intact."""
from django.db import transaction
from .models import Account,StatementRow,Transaction
from .statement_import import parse_statement


def link_existing_statement(account, csv_data, source_key, transaction_id, *, commit=False,
                            confirm_existing=False, reason='', closed_until=None, actor_id=None):
 rows,errors=parse_statement(csv_data,account)
 row=next((r for r in rows if r['key']==source_key),None)
 if not row or not row['complete_identity']:
  raise ValueError('Потрібна повна ідентичність банківської строки')
 a=row['attrs']
 with transaction.atomic():
  if commit:Account.objects.select_for_update().get(pk=account.pk)
  tx=Transaction.objects.select_for_update().filter(pk=transaction_id).first()
  if not tx or not (tx.account_id==account.pk and tx.direction==a['direction'] and tx.amount==a['amount'] and tx.currency==a['currency'] and tx.date==a['date']):
   raise ValueError('Стара операція не узгоджується за рахунком, датою, сумою, валютою та напрямком')
  existing=StatementRow.objects.filter(key=row['key']).first()
  if existing:
   if existing.transaction_id!=tx.pk:raise ValueError('Банківська строка вже належить іншій операції')
   return {'transaction_id':tx.pk,'duplicate':True,'committed':False,'financial_changes':0}
  if StatementRow.objects.filter(transaction=tx).exists():
   raise ValueError('Операція вже має іншу банківську ідентичність; не зливаємо різні операції')
  same_time=tx.op_time==a['op_time']
  if commit and closed_until and a['date']<=closed_until:
   raise ValueError('Закритий період; історичну звірку потрібно погодити окремо')
  if commit and (confirm_existing is not True or len(reason.strip())<10):
   raise ValueError('Потрібне явне підтвердження вибраної операції та підстава звірки')
  if commit and not same_time and 'час' not in reason.lower() and 'time' not in reason.lower():
   raise ValueError('Час відрізняється: явно поясніть звірку часу; запис не змінюємо')
  if commit:
   data={**row['source_data'],'legacy_resolution':{'actor_id':actor_id,'reason':reason.strip(),'time_matches':same_time}}
   StatementRow.objects.create(key=row['key'],file_hash=row['file_hash'],bank_id=row['bank_id'],bank_leg=row['leg'],source_data=data,transaction=tx)
  return {'transaction_id':tx.pk,'source_key':row['key'],'requires_explicit_confirmation':True,'time_matches':same_time,'committed':commit,'financial_changes':0}
