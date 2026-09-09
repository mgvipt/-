"""Classify existing Orac images from visually reviewed SKU/hash evidence."""
import json,os
from pathlib import Path
from django.db import transaction
from django.core import serializers
from django.utils import timezone
from apps.warehouse.models import Product,ProductImage
from apps.warehouse.shop_sync import queue_product_sync
ROOT=Path('/app/warehouse_photos/orac-import-20260909')
dry=os.getenv('DRY_RUN','1')!='0'; selected=set(filter(None,os.getenv('SKUS','').split(',')))
proof={(r['sku'],x['sha256']):x['kind'] for r in json.loads((ROOT/'gallery-coverage.json').read_text()) for x in r['images']}
plan=[];skipped=[]
for p in Product.objects.filter(shop_specs__orac__import_version='20260909-v1').order_by('id'):
 sku=p.shop_specs['orac']['sku']
 if selected and sku not in selected:continue
 changes=[]
 for im in p.images.all():
  kind=proof.get((sku,Path(im.file_path).stem))
  if not kind:continue
  label=('Фото виробу' if p.shop_specs['orac']['seo']['category_slug']=='klei-ta-montazh' else 'Фото профілю') if kind=='profile' else 'Приклад в інтер’єрі / застосування'
  alt=sku+' · '+label
  if im.alt_text==alt:continue
  if not any(x in im.alt_text for x in ['Фото товару','Інтер’єр Orac','Офіційний вигляд профілю Orac']):skipped.append(im.id);continue
  changes.append((im,alt))
 if changes:plan.append((p,changes))
print('CAPTION_PLAN',json.dumps(dict(dry=dry,products=len(plan),images=sum(len(c) for p,c in plan),manual_skipped=skipped,skus=[p.shop_specs['orac']['sku'] for p,c in plan])),flush=True)
if not dry:
 ids=[im.id for p,c in plan for im,a in c];stamp=timezone.now().strftime('%Y%m%dT%H%M%S')
 (ROOT/('captions-before-'+stamp+'.json')).write_text(serializers.serialize('json',ProductImage.objects.filter(pk__in=ids)))
 with transaction.atomic():
  for expected,changes in plan:
   p=Product.objects.select_for_update().get(pk=expected.pk)
   assert p.updated_at==expected.updated_at,('Concurrent product edit',p.pk)
   for old,alt in changes:
    im=ProductImage.objects.select_for_update().get(pk=old.pk)
    assert im.alt_text==old.alt_text and im.file_path==old.file_path,('Concurrent image edit',im.pk)
    im.alt_text=alt;im.save(update_fields=['alt_text'])
   e=queue_product_sync(p);print('CLASSIFIED',p.shop_specs['orac']['sku'],len(changes),'EVENT',e.pk,flush=True)
