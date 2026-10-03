"""Approved account/key scoped historical supplement. Never reopen or rewrite day snapshots."""
from contextlib import contextmanager
from datetime import date
import re
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.integrations.models import IntegrationSettings
from .models import Account,Transaction,DaySnapshot
from .statement_import import digest,parse_statement
PROVIDER='finance_stmt_hist_approval'


def ledger_digest(account_ids):
 fields=('id','account_id','transfer_account_id','direction','date','op_time','amount','amount_uah','currency','rate','transfer_amount','channel','contact_id','deal_id','payment_id','category_id','fin_direction_id','fin_article_id','counterparty','comment','import_batch')
 rows=Transaction.objects.filter(Q(account_id__in=account_ids)|Q(transfer_account_id__in=account_ids)).order_by('pk').values(*fields)
 return digest([{k:str(v) if v is not None else None for k,v in r.items()} for r in rows])


def snapshots_digest(until):
 fields=('id','date','version','closed_at','reopened_at','rows','totals','note')
 rows=DaySnapshot.objects.filter(date__lte=until).order_by('pk').values(*fields)
 return digest([{k:str(v) if k in ('date','closed_at','reopened_at') and v is not None else v for k,v in r.items()} for r in rows])


@contextmanager
def historical_context(user, approval_id, sources, *, kind, commit=False, selected_keys=None, existing_id=None):
 if not approval_id:
  yield None;return
 if not (user.is_superuser or user.has_perm_code('finance.day.edit_closed')):
  raise ValueError('Історичне доповнення дозволене лише власнику/бухгалтеру')
 with transaction.atomic():
  st=IntegrationSettings.objects.select_for_update().filter(provider=PROVIDER).first()
  cfg=dict(st.config or {}) if st else {}
  if not st or cfg.get('approval_id')!=approval_id:
   raise ValueError('Немає серверного погодження конкретного історичного доповнення')
  if commit and not (st.is_active and cfg.get('approved') is True and cfg.get('backup_verified') is True and cfg.get('restore_tested') is True and re.fullmatch(r'[a-f0-9]{64}',str(cfg.get('backup_sha256') or ''))):
   raise ValueError('Потрібні погоджений план, перевірений backup і тест відновлення перед записом')
  ids={int(i) for i in cfg.get('account_ids',[])}
  start=date.fromisoformat(cfg['date_from']);end=date.fromisoformat(cfg['date_to'])
  if commit:
   list(Account.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
   list(Transaction.objects.select_for_update().filter(Q(account_id__in=ids)|Q(transfer_account_id__in=ids)).order_by('pk'))
   list(DaySnapshot.objects.select_for_update().filter(date__lte=end).order_by('pk'))
  for account,raw in sources:
   if account.pk not in ids:raise ValueError('Рахунок поза погодженим коридором')
   parsed,errors=parse_statement(raw,account)
   if errors:raise ValueError('Є помилки банківських реквізитів; спершу виправте предпросмотр')
   if any(not r['complete_identity'] or not start<=r['attrs']['date']<=end for r in parsed):
    raise ValueError('Строка без повної ідентичності або поза погодженими датами')
  if cfg.get('ledger_digest')!=ledger_digest(ids) or cfg.get('snapshots_digest')!=snapshots_digest(end):
   raise ValueError('Журнал або заморожені знімки змінилися після погодження: повторіть звірку')
  selected_keys=selected_keys or []
  if kind=='legacy':
   if len(selected_keys)!=1 or str(cfg.get('legacy_links',{}).get(selected_keys[0]))!=str(existing_id):
    raise ValueError('Це зіставлення bank-key/txID окремо не підтверджене')
  elif kind=='transfer':
   pair=digest(selected_keys)
   if pair not in cfg.get('transfer_pairs',{}) or str(cfg['transfer_pairs'][pair])!=str(existing_id):
    raise ValueError('Обидва плеча/існуючий переказ окремо не підтверджені')
  elif kind!='import':raise ValueError('Невідомий тип історичної звірки')
  scope={'new_keys':set(cfg.get('new_keys',[])),'rates':cfg.get('rates',{}),'result':None}
  before=ledger_digest(ids);before_snap=snapshots_digest(end)
  yield scope
  if snapshots_digest(end)!=before_snap:
   raise ValueError('Історичне доповнення не може змінювати заморожені знімки')
  if commit:
   cfg['ledger_digest']=ledger_digest(ids)
   cfg.setdefault('audit',[]).append({'at':timezone.now().isoformat(),'actor_id':user.pk,'kind':kind,'account_ids':[a.pk for a,_ in sources],
     'selected_keys':selected_keys,'before_ledger':before,'after_ledger':cfg['ledger_digest'],'snapshots_digest':before_snap,'result':scope['result']})
   st.config=cfg;st.save(update_fields=['config','updated_at'])
