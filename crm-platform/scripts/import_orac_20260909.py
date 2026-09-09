"""Orac release only. manage.py shell; DRY_RUN=1 default, SKUS=C200,C201 pilot.
Snapshots and hashes are required. Existing historical IDs/SKUs/stock are preserved.
"""
import copy, hashlib, json, os, re, secrets
from decimal import Decimal
from pathlib import Path
from django.core import serializers
from django.db import transaction, connection
from django.utils import timezone
from apps.warehouse.models import Product, ProductCategory, ProductImage
from apps.warehouse.shop_sync import queue_product_sync, catalog_validation_errors
from apps.inbox.models import SharedLink, MediaLibraryItem

ROOT=Path('/app/warehouse_photos/orac-import-20260909')
VERSION='20260909-v1'
dry=os.environ.get('DRY_RUN','1')!='0'
selected=set(filter(None,os.environ.get('SKUS','').split(',')))
plan=json.loads((ROOT/'orac-import-dry-run.json').read_text())['rows']
catalog={r['sku']:r for r in json.loads((ROOT/'orac-products.json').read_text())}
overlay={r['sku']:r for r in json.loads((ROOT/'orac-seo-overlay.json').read_text())}
assets=json.loads((ROOT/'media-manifest.json').read_text())
asset_by_url={a['source_url']:a for a in assets if 'error'not in a}
categories={'karnyzy':(35,'Карнизы'),'moldynhy':(39,'Молдинги'),'plintusy':(41,'Плинтусы'),'rozetky':(40,'Потолочные розетки'),'dekoratyvni-elementy':(None,'Декоративні елементи'),'stinovi-paneli':(None,'Стінові панелі'),'klei-ta-montazh':(38,'Клей')}
def category_for(r,seo):
 if r['price_ua']['category'].strip()=='Інструмент':return 37,'Инструменты'
 if r['sku'].startswith('DX'):return 36,'Дверное обрамление'
 return categories[seo['category_slug']]
prepared=[]
for row in plan:
 if selected and row['sku'] not in selected:continue
 if not row['publish']:
  print('HOLD',row['sku'],row['holds']);continue
 r=catalog[row['sku']];seo=copy.deepcopy(overlay[row['sku']]['seo'])
 assert not overlay[row['sku']].get('publication_holds'), (row['sku'],'SEO holds')
 p=Product.objects.filter(pk=row['crm_id']).first() if row['crm_id'] else Product.objects.filter(shop_specs__orac__sku=row['sku']).first()
 if p and p.shop_specs.get('orac',{}).get('import_version')==VERSION:
  print('ALREADY_IMPORTED',row['sku'],p.id);continue
 if p:
  if str(p.updated_at)!=row['expected_updated_at'] or float(p.price)!=row['old_price']:
   raise RuntimeError(('Concurrent manual change; regenerate plan',row['sku'],p.id))
  assert (p.is_active or p.id in {2286,2287,1230}) and 'cezar' not in p.name.lower()
 images=sorted(r['images'],key=lambda im:not im['is_main'])
 images += [dict(url=i['url'],is_main=False,kind='interior',title=i['title'])for i in r['interior_images'][:4]]
 media=[];seen=set()
 for im in images:
  if re.search(r'/(?:rmin|rxmin|rxxmin)[^/]*\.',im['url']):continue
  a=asset_by_url.get(im['url'])
  if not a:raise RuntimeError(('Missing official media',row['sku'],im['url']))
  if a['sha256']in seen:continue
  seen.add(a['sha256']);path=ROOT/'media'/(a['sha256']+'.webp')
  assert hashlib.sha256(path.read_bytes()).hexdigest()==a['sha256']
  media.append((a,im))
 assert media
 category=seo['category_slug']
 if category not in categories:raise RuntimeError(('Unknown category',category))
 prepared.append((row,r,seo,p,media))
counts={
 'products':len(prepared),'create':sum(p is None for _,_,_,p,_ in prepared),
 'update':sum(p is not None for _,_,_,p,_ in prepared),
 'price_changes':sum(p is not None and Decimal(str(row['new_price']))!=p.price for row,_,_,p,_ in prepared),
 'category_changes':sum(p is not None and p.category_id!=category_for(r,seo)[0] for _,r,seo,p,_ in prepared),
 'reactivate':sum(p is not None and not p.is_active for _,_,_,p,_ in prepared),
 'product_image_relations':sum(len(m)for _,_,_,_,m in prepared),
 'unique_media':len({a['sha256']for _,_,_,_,media in prepared for a,_ in media})}
print('DRY_RUN_COUNTS',json.dumps(counts),'dry',dry)
if not dry:
 stamp=timezone.now().strftime('%Y%m%dT%H%M%S')
 ids=[p.id for _,_,_,p,_ in prepared if p]
 (ROOT/('before-products-'+stamp+'.json')).write_text(serializers.serialize('json',Product.objects.filter(id__in=ids)))
 result=[]
 with transaction.atomic():
  with connection.cursor()as c:c.execute('SELECT pg_advisory_xact_lock(%s)',[2026090901])
  parent=ProductCategory.objects.get(pk=34)
  for row,r,seo,p,media in prepared:
   if p:
    p=Product.objects.select_for_update().get(pk=p.pk)
    if str(p.updated_at)!=row['expected_updated_at']:raise RuntimeError(('Concurrent change',p.pk))
   else:
    assert not Product.objects.filter(shop_specs__orac__sku=row['sku']).exists()
   cid,cname=category_for(r,seo)
   category=ProductCategory.objects.get(pk=cid)if cid else ProductCategory.objects.get_or_create(parent=parent,name=cname)[0]
   slug='orac-'+row['sku'].lower()
   if p is None:
    p=Product.objects.create(name=seo['h1'],sku='ORAC-'+row['sku'],unit=r.get('unit','шт'),price=Decimal(str(row['new_price'])),category=category)
   p.category=category;p.price=Decimal(str(row['new_price']));p.unit=r.get('unit','шт');p.is_active=True
   if not p.sku.strip():
    new_sku='ORAC-'+row['sku'];assert not Product.objects.filter(sku=new_sku).exclude(pk=p.pk).exists();p.sku=new_sku
   source_sync={'source_url':row['supplier_url'],'last_applied':str(p.price),'hold':row['price_hold'],'initial_price_source':r['price_ua']['source_url'],'initial_price_date':'2026-08-24'}
   spec={k:r[k]for k in ['sku','model','material','dimensions_mm','variant','documents','source_url','unit']}
   spec.update(import_version=VERSION,seo=seo,price_sync=source_sync,checked_on='2026-09-09',media_provenance=[])
   p.description=seo['full_description']
   p.shop_enabled=True;p.shop_managed=True;p.shop_variant_type='product'
   p.shop_category_path=['Orac',cname];p.shop_parent_name=seo['h1'];p.shop_group_key=slug;p.shop_slug=slug
   p.shop_short_description=seo['short_description'];p.shop_full_description=seo['full_description'];p.shop_variant_name=row['sku'];p.shop_variant_order=1
   p.seo_title=seo['title'];p.seo_h1=seo['h1'];p.seo_description=seo['description'];p.seo_index=True
   spec['seo']['images']=[]
   for i,(a,im)in enumerate(media):
    filename=a['sha256']+'.webp'
    shared=SharedLink.objects.filter(filename=filename,content_type='image/webp').first()
    if shared:
     assert hashlib.sha256(bytes(shared.data)).hexdigest()==a['sha256']
    else:shared=SharedLink.objects.create(token=secrets.token_urlsafe(24),filename=filename,content_type='image/webp',data=(ROOT/'media'/filename).read_bytes())
    label='Інтер’єр Orac' if a['kind']=='interior'else 'Фото товару'
    item,_=MediaLibraryItem.objects.get_or_create(file=shared,material='Orac Decor',color_code=row['sku'][:48],defaults={'title':label,'kind':'image','section':'colors','preview_file':shared,'tags':'source:orac','sort':i})
    tag='product:'+str(p.id);tags=set(item.tags.split());tags.add(tag)
    if i==0:tags.add('sample')
    value=' '.join(sorted(tags));assert len(value)<=240,('Too many product references',filename)
    if item.tags!=value:item.tags=value;item.save(update_fields=['tags'])
    alt=seo['h1']+' · '+label
    ProductImage.objects.get_or_create(product=p,file_path=str(ROOT/'media'/filename),defaults={'order':i,'alt_text':alt,'is_primary':i==0,'is_approved':True})
    spec['media_provenance'].append({'sha256':a['sha256'],'source_sha256':a['source_sha256'],'source_url':a['source_url'],'source_page':a['source_page'],'kind':a['kind'],'shared_link_id':shared.id,'library_id':item.id})
   p.shop_specs={**(p.shop_specs or {}),'orac':spec,'commercial':{'unit':p.unit},'price_per_m2':0,'material':r['material'],'packaging':'Комплект: 2 елементи'if row['sku']=='D330LR'else '1 шт.'}
   p.save(update_fields=['sku','category','price','unit','is_active','description','shop_specs','shop_enabled','shop_managed','shop_variant_type','shop_category_path','shop_parent_name','shop_group_key','shop_slug','shop_short_description','shop_full_description','shop_variant_name','shop_variant_order','seo_title','seo_h1','seo_description','seo_index','updated_at'])
   assert not catalog_validation_errors(p),catalog_validation_errors(p)
   event=queue_product_sync(p)
   result.append({'sku':row['sku'],'id':p.id,'url':'https://wallcov.com.ua/product/'+slug,'event':event.id})
 (ROOT/('result-'+stamp+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print('IMPORTED',json.dumps(result,ensure_ascii=False))
