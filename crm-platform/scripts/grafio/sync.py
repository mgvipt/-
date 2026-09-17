#!/usr/bin/env python3
"""Read public Grafio HTML only. A failed/partial crawl never replaces output."""
import argparse, datetime as dt, decimal, hashlib, html, json, os, re, time
import urllib.request, urllib.error, urllib.robotparser
from pathlib import Path
ROOT = 'https://www.grafio-decor.com.ua'
UA = 'WallcovSupplierPriceCheck/1.0'

def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()
def plain(s): return html.unescape(re.sub('<[^>]+>', ' ', s or '')).strip()
def unpack(s):
    match = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', s, re.S)
    if not match: raise ValueError('Missing public SSR data')
    data = json.loads(match[1]); cache = {}
    def deref(i):
        if i < 0: return None
        if i in cache: return cache[i]
        v = data[i]
        if isinstance(v, dict):
            out = {}; cache[i] = out; out.update({k:deref(n) for k,n in v.items()}); return out
        if isinstance(v, list):
            if v and v[0] == 'Set': return [deref(n) for n in v[1:]]
            if v and isinstance(v[0], str):
                if v[0] not in ('Reactive','ShallowReactive','Ref','ShallowRef','Set','EmptyRef','EmptyShallowRef'): raise ValueError('Unknown SSR wrapper '+v[0])
                return deref(v[1]) if len(v)>1 and isinstance(v[1],int) else None
            out = []; cache[i] = out; out.extend(deref(n) for n in v); return out
        return v
    return deref(0)['data']
def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values(): yield from walk(child)
    elif isinstance(value,list):
        for child in value: yield from walk(child)
def money(value):
    if value is None or value == '': return None
    value = str(value).replace('\u00a0','').replace(' ','').replace(',','.')
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?',value): raise ValueError('Unrecognized price '+value)
    if decimal.Decimal(value) <= 0: raise ValueError('Non-positive price needs manual review')
    return value

def parse_page(source, text):
    p = next((v for v in walk(unpack(text)) if v.get('slug')==source['slug'] and 'description' in v),None)
    if not p: raise ValueError('Product absent in public SSR')
    sid = p.get('databaseId')
    expected = source.get('sourceID',source.get('databaseId'))
    if not sid or sid != expected: raise ValueError('Stable supplier ID mismatch')
    visible = re.sub(r'<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>', '', text, flags=re.S|re.I)
    visible = re.sub(r'\s+',' ',plain(visible))
    # Only the main purchase price block; never infer a price from related products.
    scopes = re.findall(r'<div class="flex items-baseline gap-2">(.*?)</div>\s*<div class="flex items-center gap-1 mt-1">(.*?)</div>', text, re.S)
    scoped_text = re.sub(r'\s+', ' ', plain(' '.join(scopes[0]))) if len(scopes)==1 else ''
    amounts = re.findall(r'\d[\d\s.,]*\s*₴', scoped_text)
    displayed = re.search(r'(\d[\d\s.,]*)\s*₴\s*за\s*(м\.п\.|м²|м2|шт\.?)', scoped_text) if len(amounts)==1 else None
    source_price = money(p.get('price'))
    price = money(displayed[1]) if displayed else source_price
    categories = (p.get('productCategories') or {}).get('nodes',[])
    units = [c.get('productCategoryACF',{}).get('unit') for c in categories]
    units = [u for u in units if u]
    unit_labels = sorted(set(u[-1] for u in units)); category_unit = unit_labels[0] if len(unit_labels)==1 else None
    visible_unit = displayed[2] if displayed else None
    issues = []; discrepancies = []
    if source_price is not None and not displayed: issues.append('priced_product_without_single_visible_product_price')
    if displayed and price != source_price: discrepancies.append('visible_price_differs_from_SSR')
    if visible_unit and category_unit and visible_unit != category_unit: issues.append('visible_unit_conflicts_with_category')
    description = plain(p.get('description')); unit_claims = re.findall(r'.{0,80}(?:за\s*1\s*(?:м\.п\.|шт\.?|м²)|за\s*(?:штуку|одиницю)).{0,100}',description)
    if category_unit=='м.п.' and any(re.search(r'за\s*(?:штуку|одиницю)|за\s*1\s*шт',v) for v in unit_claims): issues.append('description_unit_conflicts_with_category')
    attributes = (p.get('globalAttributes') or {}).get('edges',[])
    imgs = [p.get('image',{}).get('sourceUrl')] if p.get('image') else []
    imgs += [x.get('sourceUrl') for x in (p.get('galleryImages') or {}).get('nodes',[])]
    drawing = ((p.get('productPageACF') or {}).get('drawing') or {}).get('node') or {}
    return dict(sourceID=sid, sourceGlobalID=p.get('id'), sourceURL=source.get('source_url') or source.get('sourceURL') or ROOT+'/product/'+p['slug'],
        slug=p['slug'], name=p['name'], checkedAt=stamp(), httpStatus=200, htmlSha256=hashlib.sha256(text.encode()).hexdigest(),
        price=price, sourcePriceSSR=source_price, sourceDiscrepancies=discrepancies, regularPrice=money(p.get('regularPrice')), salePrice=money(p.get('salePrice')), currency='UAH' if p.get('currencySymbol')=='₴' else None,
        currencySymbol=p.get('currencySymbol'), unit=visible_unit or category_unit, unitCategoryEvidence=units, unitVisible=visible_unit,
        priceField='public HTML main purchase block' if displayed else 'public SSR fallback; must review if priced', visiblePriceQuote=displayed[0] if displayed else None,
        dimensions=[x['name'] for x in (p.get('allPaRozmir') or {}).get('nodes',[])], description=description,
        descriptionHTML=p.get('description'), descriptionUse='supplier source only; do not publish manufacturer first-person claims as dealer copy',
        shortDescription=plain(p.get('shortDescription')), attributes=attributes, images=list(dict.fromkeys(x for x in imgs if x)), drawings=[drawing['sourceUrl']] if drawing.get('sourceUrl') else [],
        category={k:categories[0].get(k) for k in ('slug','name')} if categories else None, categories=categories, variants=p.get('variations'), subproducts=p.get('productPageSetsACF'), stockStatus=p.get('stockStatus'),
        stockIsSupplierOnly=True, unitDescriptionEvidence=unit_claims, reviewIssues=issues, status='review_required' if issues else ('verified' if price else 'price_on_request'))

class Fetcher:
    def __init__(self): self.last=0; self.robots=None
    def get(self,url):
        if not url.startswith(ROOT+'/') or '/api/' in url: raise ValueError('Public product host only')
        if self.robots and not self.robots.can_fetch(UA,url): raise ValueError('robots disallows URL')
        time.sleep(max(0,1.1-(time.monotonic()-self.last))); self.last=time.monotonic()
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html,text/plain'}),timeout=40) as response:
            if not response.url.startswith(ROOT+'/'): raise ValueError('Unexpected redirect')
            return response.read().decode('utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--inventory',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    inventory=json.loads(Path(args.inventory).read_text())['products']; out=Path(args.output)
    if len(inventory)!=223 or len({p.get('sourceID',p.get('databaseId')) for p in inventory})!=223: raise ValueError('Expected 223 unique stable supplier IDs')
    fetch=Fetcher(); robots=fetch.get(ROOT+'/robots.txt'); fetch.robots=urllib.robotparser.RobotFileParser();fetch.robots.parse(robots.splitlines())
    result={'schemaVersion':1,'startedAt':stamp(),'source':ROOT,'robots':robots,'expectedCount':len(inventory),'complete':False,'products':[],'failures':[]}
    for i,p in enumerate(inventory,1):
        url=p.get('sourceURL') or p.get('source_url') or ROOT+'/product/'+p['slug']
        try: result['products'].append(parse_page(p,fetch.get(url)))
        except Exception as error:
            print('FAIL',p['slug'],str(error),flush=True)
            print('FAIL',p['slug'],str(error),flush=True)
            result['failures'].append({'sourceID':p.get('sourceID',p.get('databaseId')),'sourceURL':url,'error':str(error),'checkedAt':stamp()})
            if isinstance(error,urllib.error.HTTPError):
                error.close()
                if error.code in (403,429): break
            if len(result['failures']) >= 3 and not result['products']: break
        if i%10==0: print('Checked',i,'/',len(inventory),'failures',len(result['failures']),flush=True)
    result['completedAt']=stamp();result['complete']=len(result['products'])==len(inventory) and not result['failures']
    result['summary']={'priced':sum(p['price'] is not None for p in result['products']),'unpriced':sum(p['price'] is None for p in result['products']),'reviewRequired':sum(bool(p['reviewIssues']) for p in result['products'])}
    if not result['complete']:
        print(json.dumps({'complete':False,'completedAt':result['completedAt'],'summary':result['summary'],'failures':result['failures']},ensure_ascii=False));raise SystemExit('Incomplete crawl: output not replaced; preserve prior CRM/shop prices')
    temp=out.with_suffix(out.suffix+'.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,indent=2));os.replace(temp,out)
    print(json.dumps(result['summary']),flush=True)
if __name__=='__main__': main()
