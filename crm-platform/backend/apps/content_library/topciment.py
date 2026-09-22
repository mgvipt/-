"""Area calculator. Product prices are read on every request; no cached price copies."""
from decimal import Decimal, ROUND_CEILING
from apps.warehouse.models import Product
D=Decimal
MATERIALS={'acricem': {'name': 'TOPCIMENT Acricem resina', 'unit': 'л'}, 'abs': {'name': 'TOPCIMENT Primacem ABS', 'unit': 'л'}, 'plus': {'name': 'TOPCIMENT Primacem PLUS', 'unit': 'л'}, 'microbase': {'name': 'TOPCIMENT Sttandard Microbase L', 'unit': 'кг'}, 'microstone': {'name': 'TOPCIMENT Sttandard Microstone L', 'unit': 'кг'}, 'microdeck': {'name': 'TOPCIMENT Unlimitted Microdeck M', 'unit': 'кг'}, 'microfino-old': {'name': 'TOPCIMENT Microfino', 'unit': 'кг'}, 'presealer': {'name': 'TOPCIMENT Presealer', 'unit': 'л'}, 'dsv-b': {'name': 'TOPCIMENT Topsealer DSV · компонент B', 'unit': 'л'}, 'dsv-a': {'name': 'TOPCIMENT Topsealer DSV Mate · компонент A', 'unit': 'л'}, 'wt-b': {'name': 'TOPCIMENT Topsealer WT One Coat · компонент B', 'unit': 'л'}, 'wt-mate': {'name': 'TOPCIMENT Topsealer WT One Coat Mate · компонент A', 'unit': 'л'}, 'wt-kit-old': {'name': 'TOPCIMENT Topsealer WT One Coat Mate A+B', 'unit': 'кг'}, 'microfino': {'name': 'TOPCIMENT Sttandard Microfino S', 'unit': 'кг'}, 'grip': {'name': 'TOPCIMENT Primacem GRIP', 'unit': 'кг'}, 'eq-super': {'name': 'TOPCIMENT Efectto Quartz Super Grain', 'unit': 'кг'}, 'eq-medium': {'name': 'TOPCIMENT Efectto Quartz Medium Grain', 'unit': 'кг'}, 'eq-big': {'name': 'TOPCIMENT Efectto Quartz Big Grain', 'unit': 'кг'}, 'eq-small': {'name': 'TOPCIMENT Efectto Quartz Small Grain', 'unit': 'кг'}, 'wt-super': {'name': 'TOPCIMENT Topsealer WT One Coat Supermate · компонент A', 'unit': 'л'}, 'pigment-yellow': {'name': 'TOPCIMENT Arcocem BASIC Amarillo', 'unit': 'г'}, 'pigment-blue': {'name': 'TOPCIMENT Arcocem BASIC Azul', 'unit': 'г'}, 'pigment-black': {'name': 'TOPCIMENT Arcocem BASIC Negro', 'unit': 'г'}, 'pigment-orange': {'name': 'TOPCIMENT Arcocem BASIC Rojo Naranja', 'unit': 'г'}, 'pigment-green': {'name': 'TOPCIMENT Arcocem BASIC Verde', 'unit': 'г'}, 'mesh': {'name': 'Армувальна сітка', 'unit': 'м²'}, 'xz': {'name': 'Ґрунт XZ · уточнити марку', 'unit': 'кг'}}
SYSTEMS=[{'id': 'microdeck-dsv', 'name': 'Unlimitted Microdeck M + DSV · підлога', 'materials': ['acricem', 'microbase', 'microdeck', 'mesh', 'dsv-kit']}, {'id': 'microfino-dsv', 'name': 'Sttandard Microfino S + DSV · стіни', 'materials': ['acricem', 'microbase', 'microfino', 'mesh', 'dsv-kit']}, {'id': 'microdeck-wt', 'name': 'Unlimitted Microdeck M + WT · підлога', 'materials': ['acricem', 'microbase', 'microdeck', 'mesh', 'presealer', 'wt-kit']}, {'id': 'microfino-wt', 'name': 'Sttandard Microfino S + WT · стіни', 'materials': ['acricem', 'microbase', 'microfino', 'mesh', 'presealer', 'wt-kit']}, {'id': 'efectto-floor', 'name': 'Efectto Quartz + WT · підлога', 'materials': ['xz', 'grip', 'eq-super', 'eq-medium', 'wt-kit']}, {'id': 'efectto-wall', 'name': 'Efectto Quartz + WT · стіни', 'materials': ['xz', 'grip', 'eq-big', 'eq-small', 'wt-kit']}]
MATERIALS.update({
 'wt-kit': {'name': 'Topsealer WT · комплект A + B', 'unit': 'л суміші'},
 'dsv-kit': {'name': 'Topsealer DSV · комплект A + B', 'unit': 'л суміші'},
})
NOTES=[
 'Це попередній розрахунок матеріалів. Основа, кількість шарів і реальна витрата потребують перевірки майстром. Роботи, доставка й тонування не включені.',
 'Витрата, фасування та пропорції беруться з карток матеріалів. Серії та фракції не взаємозамінні.',
 'Кількість Acricem враховує ґрунтування та смолу для кожного порошкового матеріалу обраної системи.',
 'Калькулятор рахує закупівельні комплекти захисту, а не дозування для замішування. Перевірте склад комплекту та технічну карту.',
 'Вихід WT обмежений кількістю компонентів з урахуванням густини та пропорції за масою. Для DSV показаний номінальний обсяг закупівельного комплекту; комплектність звірте з постачальником.',
 'Ґрунт XZ у схемі Efectto: точну марку й сумісність потрібно підтвердити. Позиції без підтвердженої номенклатури або норми не входять у підсумок вартості.',
]
def positive(value,allow_zero=False):
 if value is None:return None
 try: number=D(str(value))
 except (ValueError,ArithmeticError):raise ValueError('Некоректне числове значення у картці товару.')
 if not number.is_finite() or number<0 or (number==0 and not allow_zero):raise ValueError('Норма, густина та пропорції мають бути додатними.')
 return number
def num(v):return float(v.quantize(D('0.001')))
def catalog():
 return {p.shop_specs['topciment_key']:p for p in Product.objects.filter(sku__startswith='TC-20260922-',is_active=True) if p.shop_specs.get('topciment_key')}
def calculate(system_id,area,reserve,basis='sale'):
 area=D(str(area));reserve=D(str(reserve))
 if not area.is_finite() or not reserve.is_finite() or not D('0')<area<=D('100000') or not D('0')<=reserve<=D('50'):raise ValueError('Вкажіть площу від 0 до 100 000 м² та запас 0–50%.')
 if basis not in ('sale','reference'):raise ValueError('Невідомий тип ціни.')
 system=next((s for s in SYSTEMS if s['id']==system_id),None)
 if not system:raise ValueError('Оберіть систему.')
 products=catalog();rows=[];total=D(0);missing=[]
 def unit_price(p):
  if basis=='sale':return p.price if p.price>0 and p.currency=='UAH' else None
  ref=p.shop_specs.get('reference_price') or {}
  return D(str(ref['uah_pack']))/p.pack_factor if ref.get('uah_pack') and p.pack_factor>0 else None
 for key in system['materials']:
  p=products.get(key)
  owner=products.get('wt-mate' if key=='wt-kit' else 'dsv-a' if key=='dsv-kit' else key)
  rate=(owner.shop_specs.get('calculator_rates',{}).get(system_id) if owner else None)
  if key=='acricem' and owner:
   rate=positive(owner.shop_specs.get('primer_rate_l_m2'),allow_zero=True) if owner.unit=='л' else None
   for powder_key in ('microbase','microdeck','microfino'):
    if powder_key not in system['materials']:continue
    powder=products.get(powder_key)
    spec=powder.shop_specs if powder else {}
    consumption=spec.get('calculator_rates',{}).get(system_id)
    resin=spec.get('acricem_l_per_kg')
    if rate is None or consumption is None or resin is None or not powder or powder.unit!='кг':
     rate=None;break
    rate+=positive(consumption)*positive(resin)
  if rate is None:
   name=MATERIALS[key]['name']
   missing.append(name)
   rows.append({'key':key,'name':name+' · уточнити норму','unit':MATERIALS[key]['unit'],'rate':None,'quantity':None,'pack':None,'packs':None,'purchase_quantity':None,'pack_price':None,'subtotal':None,'products':[{'id':owner.id,'name':owner.name}] if owner else []})
   continue
  rate=D(str(rate))
  if not rate.is_finite() or rate<=0:raise ValueError('Некоректна норма витрати у картці товару.')
  quantity=area*rate*(1+reserve/100);pack=None;price=None;links=[]
  if key.endswith('-kit'):
   a=products.get('wt-mate' if key=='wt-kit' else 'dsv-a')
   b=products.get('wt-b' if key=='wt-kit' else 'dsv-b')
   mix=a.shop_specs.get('mixing',{}) if a else {}
   count=positive(mix.get('b_pack_count'))
   if count is not None and count!=count.to_integral_value():raise ValueError('Кількість упаковок компонента B має бути цілою.')
   valid=a and b and a.pack_factor>0 and b.pack_factor>0 and a.unit=='л' and b.unit=='л' and count is not None
   parts=[(a.shop_specs['topciment_key'],a.pack_factor),(b.shop_specs['topciment_key'],b.pack_factor*count)] if valid else []
   if valid and key=='wt-kit':
    ratio=positive(mix.get('a_to_b_mass'));da=positive(mix.get('density_a_kg_l'));db=positive(mix.get('density_b_kg_l'))
    if all(v is not None for v in (ratio,da,db)):
     av=a.pack_factor;bv=b.pack_factor*count
     usable_a=min(av,bv*db*ratio/da);pack=usable_a+usable_a*da/ratio/db
   elif valid and key=='dsv-kit':pack=a.pack_factor+b.pack_factor*count
   name=MATERIALS[key]['name']
   unit='л суміші';prices=[]
   for part,q in parts:
    pp=products.get(part)
    if pp and pp.unit=='л' and pp.pack_factor>0:
     links.append({'id':pp.id,'name':pp.name});pr=unit_price(pp);prices.append(pr*q if pr is not None else None)
    else:prices.append(None)
   price=sum(prices,D(0)) if prices and pack and all(pr is not None for pr in prices) else None
  elif p:
   name=p.name;unit=MATERIALS[key]['unit'];links=[{'id':p.id,'name':p.name}]
   if p.pack_factor>0 and p.unit==unit:
    pack=p.pack_factor;pr=unit_price(p);price=pr*pack if pr is not None else None
   else:name+=' · перевірте одиницю та фасування'
  else:name=MATERIALS[key]['name']+' · потрібна картка';unit=MATERIALS[key]['unit']
  packs=int((quantity/pack).to_integral_value(rounding=ROUND_CEILING)) if pack else None
  subtotal=price*packs if price is not None else None
  if subtotal is None:missing.append(name)
  else:total+=subtotal
  rows.append({'key':key,'name':name,'unit':unit,'rate':float(rate),'quantity':num(quantity),'pack':num(pack) if pack else None,'packs':packs,'purchase_quantity':num(pack*packs) if pack else None,'pack_price':round(float(price),2) if price is not None else None,'subtotal':round(float(subtotal),2) if subtotal is not None else None,'products':links})
 return {'system':system['name'],'area':float(area),'reserve':float(reserve),'basis':basis,'rows':rows,'known_total':round(float(total),2),'complete':not missing,'missing':missing,'notes':NOTES,'reference_date':'2026-09-22','eur_uah':'51.3671'}
