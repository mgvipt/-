"""Append exact-SKU official regional images; never replace existing media/text/prices."""
import copy,hashlib,json,os,re,secrets
from pathlib import Path
from django.core import serializers
from django.db import transaction,connection
from django.utils import timezone
from apps.warehouse.models import Product,ProductImage
from apps.warehouse.shop_sync import queue_product_sync
from apps.inbox.models import SharedLink,MediaLibraryItem

ROOT=Path('/app/warehouse_photos/orac-import-20260909')
dry=os.environ.get('DRY_RUN','1')!='0'
selected=set(filter(None,os.environ.get('SKUS','').split(',')))
catalog={r['sku']:r for r in json.loads((ROOT/'orac-products.json').read_text())}
assets={a['source_url']:a for a in json.loads((ROOT/'media-manifest.json').read_text()) if 'error'not in a}
excluded={(r['sku'],r['sha256'])for r in json.loads((ROOT/'gallery-visual-audit.json').read_text())if r['exclude']}
plan=[]
for p in Product.objects.filter(shop_specs__orac__import_version='20260909-v1').order_by('id'):
 sku=p.shop_specs['orac']['sku']
 if selected and sku not in selected:continue
 existing={Path(x).stem for x in ProductImage.objects.filter(product=p).values_list('file_path',flat=True)}
 add=[]
 for im in catalog[sku]['images']+catalog[sku]['interior_images']:
  if re.search(r'/(?:rmin|rxmin|rxxmin)[^/]*\.',im['url']):continue
  a=assets[im['url']]
  if a['sha256'] in existing or (sku,a['sha256'])in excluded:continue
  assert a['source_url'].startswith('https://www.oracdecor.com/')
  f=ROOT/'media'/(a['sha256']+'.webp')
  assert hashlib.sha256(f.read_bytes()).hexdigest()==a['sha256']
  add.append(a);existing.add(a['sha256'])
 if add:plan.append((p,add))
print('GALLERY_PLAN',json.dumps({'dry':dry,'products':len(plan),'new_relations':sum(len(a)for p,a in plan),'new_unique_files':len({a['sha256']for p,aa in plan for a in aa}),'skus':[p.shop_specs['orac']['sku']for p,a in plan]}),flush=True)
if not dry:
 stamp=timezone.now().strftime('%Y%m%dT%H%M%S')
 (ROOT/('gallery-before-'+stamp+'.json')).write_text(serializers.serialize('json',Product.objects.filter(id__in=[p.id for p,a in plan])))
 with transaction.atomic():
  with connection.cursor()as c:c.execute('SELECT pg_advisory_xact_lock(%s)',[2026090901])
  for expected,aa in plan:
   p=Product.objects.select_for_update().get(pk=expected.id)
   assert p.updated_at==expected.updated_at,('Concurrent product edit',p.id)
   specs=copy.deepcopy(p.shop_specs);spec=specs['orac'];sku=spec['sku']
   order=max(ProductImage.objects.filter(product=p).values_list('order',flat=True),default=-1)+1
   for a in aa:
    filename=a['sha256']+'.webp';path=ROOT/'media'/filename
    shared=SharedLink.objects.filter(filename=filename,content_type='image/webp').first()
    if shared:assert hashlib.sha256(bytes(shared.data)).hexdigest()==a['sha256']
    else:shared=SharedLink.objects.create(token=secrets.token_urlsafe(24),filename=filename,content_type='image/webp',data=path.read_bytes())
    label='Інтер’єр Orac'if a['kind']=='interior'else'Офіційний вигляд профілю Orac'
    item,_=MediaLibraryItem.objects.get_or_create(file=shared,material='Orac Decor',color_code=sku[:48],defaults={'title':label,'kind':'image','section':'colors','preview_file':shared,'tags':'source:orac product:'+str(p.id),'sort':order})
    ProductImage.objects.get_or_create(product=p,file_path=str(path),defaults={'order':order,'alt_text':sku+' · '+label,'is_primary':False,'is_approved':True})
    spec['media_provenance'].append({k:a[k]for k in ['sha256','source_sha256','source_url','source_page','kind']}|{'shared_link_id':shared.id,'library_id':item.id,'enrichment':'regional-gallery-v2'})
    order+=1
   spec['gallery_enrichment']='regional-gallery-v2';p.shop_specs=specs
   p.save(update_fields=['shop_specs','updated_at']);e=queue_product_sync(p)
   print('ENRICHED',sku,p.id,len(aa),'EVENT',e.id,flush=True)
