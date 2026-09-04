"""Run via manage.py shell. DRY_RUN=1 by default; LIMIT=2 for the first live sample.
Names/SKUs/stock are preserved. PRICE_REFRESH=1 explicitly refreshes selling prices.
All library prices come from Product.
"""
import hashlib, json, os, re, secrets
from pathlib import Path
from decimal import Decimal
from django.core import serializers
from django.db import transaction
from apps.inbox.models import MediaLibraryItem, SharedLink
from apps.warehouse.models import Product, ProductImage, ProductCategory
from apps.warehouse.shop_sync import queue_product_sync, catalog_validation_errors

ROOT=Path('/app/warehouse_photos/cezar-import-20260905')
MATERIAL='Плінтуси Cezar'
rows=json.loads((ROOT/'manifest.json').read_text())
dry=os.environ.get('DRY_RUN','1') != '0'
limit=int(os.environ.get('LIMIT','0'))
existing=list(Product.objects.filter(name__icontains='CEZAR'))
plan=[]
for row in rows:
    matches=[]
    ambiguous=[]
    for p in existing:
        match=re.search(r'LPC[-_ ]?(\d+(?:LE)?)\b',p.name,re.I)
        if not match or 'LPC-'+match.group(1).upper() != row['code']: continue
        length=re.search(r'\(\s*(\d[.,]\d+)\s*[mм]',p.name)
        if not length:
            ambiguous.append(p.id); continue
        if round(float(length.group(1).replace(',','.'))*1000)==row['length']: matches.append(p)
    managed=Product.objects.filter(sku=row['sku']).first()
    if managed and managed not in matches: matches.append(managed)
    if ambiguous and not matches:
        print('REQUIRES_LENGTH_CHECK',row['key'],ambiguous);continue
    assert len(matches)<=1, ('Duplicate match',row['key'])
    p=matches[0] if matches else None
    for media in row['media']:
        assert hashlib.sha256((ROOT/media['file']).read_bytes()).hexdigest()==media['sha256']
        assert (ROOT/media['thumb']).is_file()
    plan.append((row,p))
print('PLAN variants=%d existing=%d new=%d photos=%d dry=%s' % (len(plan),sum(p is not None for _,p in plan),sum(p is None for _,p in plan),sum(len(r['media']) for r,p in plan),dry))
for r,p in plan: print('would use',r['key'],'id',p.id if p else 'NEW','price',str(p.price) if p else r['price'])
if os.environ.get('DESCRIPTION_REFRESH') == '1':
    descriptions=json.loads((ROOT/'descriptions.json').read_text())
    targets=[(r,p) for r,p in plan if p and p.shop_specs.get('cezar',{}).get('description_version')!='20260905-v1']
    print('DESCRIPTION_TARGETS',len(targets),[p.id for _,p in targets])
    if not dry:
        backup=ROOT/'before-descriptions.json'
        if not backup.exists(): backup.write_text(serializers.serialize('json',Product.objects.filter(pk__in=[p.id for _,p in targets])))
        with transaction.atomic():
            for r,p in (targets[:limit] if limit else targets):
                d=descriptions[r['key']]
                for field in ('description','shop_short_description','shop_full_description','seo_description'): setattr(p,field,d[field])
                p.shop_specs['cezar']['description_version']='20260905-v1'
                p.shop_specs['cezar']['evidence']=d['evidence']
                p.save(update_fields=['description','shop_short_description','shop_full_description','seo_description','shop_specs','updated_at'])
                queue_product_sync(p)
        print('DESCRIPTIONS_UPDATED',len(targets[:limit] if limit else targets))
elif os.environ.get('PRICE_REFRESH') == '1':
    changes=[(r,p) for r,p in plan if p and p.price != Decimal(r['price'])]
    print('PRICE_CHANGES',len(changes),[(p.id,str(p.price),r['price']) for r,p in changes])
    if not dry:
        with transaction.atomic():
            for r,p in (changes[:limit] if limit else changes):
                p.price=Decimal(r['price']);p.save(update_fields=['price','updated_at']);queue_product_sync(p)
        print('PRICES_UPDATED',len(changes[:limit] if limit else changes))
elif not dry:
    backup=ROOT/'before-products.json'
    if not backup.exists(): backup.write_text(serializers.serialize('json',Product.objects.filter(pk__in=[p.id for _,p in plan if p])))
    result=[]
    with transaction.atomic():
        # Cooperative DB lock prevents two imports from making duplicate rows.
        from django.db import connection
        with connection.cursor() as c: c.execute('SELECT pg_advisory_xact_lock(%s)',[2026090501])
        parent,_=ProductCategory.objects.get_or_create(name='Плінтуси',parent=None)
        category,_=ProductCategory.objects.get_or_create(name='Cezar · дюрополімер',parent=parent)
        for index,(row,p) in enumerate(plan[:limit] if limit else plan):
            slug='cezar-'+row['key'].lower()
            created=p is None
            title=f"Плінтус Cezar {row['code']} · {row['length']/1000:g} м"
            if p is None:
                p=Product.objects.create(name=title,sku=row['sku'],price=Decimal(row['price']),unit='шт',category=category)
            if p.shop_specs.get('cezar',{}).get('import')=='20260905':
                print('ALREADY_IMPORTED',p.id,row['key']);continue
            details=f"Дюрополімерний плінтус Cezar {row['code']} під фарбування. Висота {row['height']:g} мм, товщина {row['thickness']:g} мм. Довжина однієї планки — {row['length']/1000:g} м. Ціна вказана за одну планку. Біле ґрунтоване покриття."
            p.shop_specs={**(p.shop_specs or {}),'cezar':{**{k:row[k] for k in ('code','length','height','thickness','source','checked_on')},'source_price':row['price'],'import':'20260905'},'packaging':f"1 планка · {row['length']/1000:g} м",'material':'Дюрополімер'}
            p.shop_enabled=True;p.shop_managed=True;p.shop_variant_type='product'
            p.shop_category_path=['Плінтуси','Cezar'];p.shop_parent_name=title;p.shop_group_key=slug;p.shop_slug=slug
            p.shop_short_description=details;p.shop_full_description=details;p.shop_variant_name=f"Планка {row['length']/1000:g} м";p.shop_variant_order=1
            p.seo_title=title+' — Wallcov';p.seo_h1=title;p.seo_description=details;p.seo_index=True
            p.save(update_fields=['shop_specs','shop_enabled','shop_managed','shop_variant_type','shop_category_path','shop_parent_name','shop_group_key','shop_slug','shop_short_description','shop_full_description','shop_variant_name','shop_variant_order','seo_title','seo_h1','seo_description','seo_index','updated_at'])
            assets=[]
            for i,m in enumerate(row['media']):
                # Image originals are retained in persistent media; DB files are reusable for chats.
                f=SharedLink.objects.create(token=secrets.token_urlsafe(24),filename=m['file'],content_type='image/webp',data=(ROOT/m['file']).read_bytes())
                thumb=SharedLink.objects.create(token=secrets.token_urlsafe(24),filename=m['thumb'],content_type='image/webp',data=(ROOT/m['thumb']).read_bytes())
                label='Фото товару' if i==0 else f'Фото {i+1}'
                asset=MediaLibraryItem.objects.create(title=label,kind='image',section='colors',material=MATERIAL,color_code=f"{row['code']} · {row['length']/1000:g} м",tags=f"product:{p.id} source:alexdecor cezar sample effect:Фото товару",file=f,preview_file=thumb,sort=index*10+i)
                assets.append(asset.id)
                ProductImage.objects.create(product=p,file_path=str(ROOT/m['file']),order=i,alt_text=title+' · '+label,is_primary=i==0,is_approved=True)
            assert not catalog_validation_errors(p),catalog_validation_errors(p)
            event=queue_product_sync(p)
            result.append({'product':p.id,'created':created,'assets':assets,'event':event.id,'key':row['key']})
    out=ROOT/('result-pilot.json' if limit else 'result-full.json');out.write_text(json.dumps(result,ensure_ascii=False,indent=2));print('IMPORTED',len(result))
