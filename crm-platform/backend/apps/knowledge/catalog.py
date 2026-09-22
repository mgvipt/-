"""Ціни — тільки з каталогу CRM, у момент читання (не зберігаються текстом у базі знань).

У тексті запису пишемо місце для ціни:
  {price:1623}        → «1330 грн/кг» (ціна товару 1623 з каталогу)
  {m2:1623}           → «200 грн/м²»  (ціна × витрата кг/м² з картки товару)
  {m2:1650:0.45}      → ціна × 0,45 кг/м² (якщо в картці товару витрата не заповнена)
Товар не знайдено / неактивний / ціна 0 → «(ціну уточнює менеджер)» — агент не вигадає цифру.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

PLACEHOLDER = re.compile(r"\{(price|m2):(\d+)(?::(\d+(?:[.,]\d+)?))?\}")
UNKNOWN = "(ціну уточнює менеджер)"

# Згадка матеріалу в розмові → які товари показати агенту з цінами
FAMILIES = [
    ("Galateya", r"галате|galat", "galateya"),
    ("Sirena Silk (мокрий шовк)", r"сирен|sirena|мокр\w*\s+шовк", "sirena silk"),
    ("Mermi Silk", r"мерм|mermi", "mermi"),
    ("Celestial", r"целест|селест|celest", "celestia"),
    ("Velvet Luna", r"луна|luna", "velvet luna"),
    ("Velvet Lux", r"люкс|lux", "velvet lux"),
    ("Eleganti", r"елеган|элеган|elegant", "eleganti"),
    ("Pattera (травертин, марморин)", r"патер|pattera|травертин|марморин|мармарин", "pattera"),
    ("Slate", r"slate|слейт|слюд", "slate"),
    ("Primalex", r"primalex|прімалекс|прималекс", "primalex"),
    ("Play&Clean", r"play\s*&?\s*clean|плей", "play"),
]


def fmt(value):
    """1080 → «1080»; 199.5 → «200»; 0.15 → «0,15»."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    if d >= 100:
        return str(int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
    s = format(q, "f")
    return s.replace(".", ",")


def load_products(ids):
    from apps.warehouse.models import Product
    ids = {int(i) for i in ids if str(i).isdigit()}
    if not ids:
        return {}
    return {p.id: p for p in Product.objects.filter(id__in=ids).only(
        "id", "name", "price", "unit", "consumption_per_m2", "is_active")}


def _unit_suffix(product):
    unit = (product.unit or "").strip().lower()
    return "/кг" if unit.startswith("кг") else ("/л" if unit in ("л", "литр", "літр") else "")


def _one(kind, pid, override, products):
    p = products.get(int(pid))
    if not p or not p.is_active or not p.price or p.price <= 0:
        return UNKNOWN
    if kind == "price":
        return "%s грн%s" % (fmt(p.price), _unit_suffix(p))
    cons = None
    if override:
        try:
            cons = Decimal(override.replace(",", "."))
        except InvalidOperation:
            cons = None
    if cons is None:
        cons = p.consumption_per_m2
    if not cons:
        return "%s грн/кг (витрату уточнює менеджер)" % fmt(p.price)
    return "%s грн/м²" % fmt(Decimal(p.price) * Decimal(cons))


def render(text, products=None):
    """Підставити в текст актуальні ціни каталогу. Ніколи не падає."""
    if not text or "{" not in text:
        return text or ""
    try:
        if products is None:
            products = load_products(m.group(2) for m in PLACEHOLDER.finditer(text))
        return PLACEHOLDER.sub(lambda m: _one(m.group(1), m.group(2), m.group(3), products), text)
    except Exception:
        return PLACEHOLDER.sub(UNKNOWN, text)


def placeholder_ids(texts):
    ids = set()
    for t in texts:
        for m in PLACEHOLDER.finditer(t or ""):
            ids.add(int(m.group(2)))
    return ids


def mentioned_families(query):
    q = (query or "").lower()
    return [(label, term) for label, rx, term in FAMILIES if re.search(rx, q)]


def _line(p):
    name = re.sub(r"\s+", " ", p.name or "").strip()
    if len(name) > 95:
        name = name[:92] + "…"
    s = "• %s — %s грн%s" % (name, fmt(p.price), _unit_suffix(p))
    if p.consumption_per_m2:
        s += " (витрата %s кг/м² ≈ %s грн/м²)" % (fmt(p.consumption_per_m2), fmt(Decimal(p.price) * p.consumption_per_m2))
    return s


def prices_block(items=None, query=None, max_lines=24, per_family=10):
    """Блок «Ціни з каталогу CRM» для товарів, привʼязаних до записів, і матеріалів, згаданих у розмові."""
    try:
        from apps.warehouse.models import Product
        seen, lines = set(), []
        for it in items or []:
            for p in it.products.all():
                if p.id not in seen and p.is_active and p.price and p.price > 0:
                    seen.add(p.id)
                    lines.append(_line(p))
        for _label, term in mentioned_families(query):
            rows = (Product.objects.filter(is_active=True, price__gt=0, name__icontains=term)
                    .order_by("name")[:per_family])
            for p in rows:
                if p.id not in seen:
                    seen.add(p.id)
                    lines.append(_line(p))
        prices = ("Ціни з каталогу CRM (актуальні зараз; інших цифр не називай):\n" + "\n".join(lines[:max_lines])) if lines else ""
        facts = current_product_facts(items, query)
        return "\n\n".join(x for x in [prices, facts] if x)
    except Exception:
        return ""


def current_product_facts(items=None, query=None, limit=6):
    """Resolve current descriptions by Product IDs; never copy them into KnowledgeItem."""
    from apps.warehouse.models import Product
    from apps.content_library.models import Instruction
    from django.db.models import Q
    from django.utils.html import strip_tags
    linked={p.id for item in items or [] for p in item.products.all()}
    taught=Instruction.objects.filter(content__kind='staff_training').values('products__id')
    query=(query or '').lower()
    aliases={'мікроцемент':'microcement','микроцемент':'microcement','топцемент':'topciment','топ цемент':'topciment','міо':'mio','мио':'mio','сірена':'sirena','сирена':'sirena','паттера':'pattera','патера':'pattera','праймер':'primer','антикатура':'anticatura'}
    for key,value in aliases.items():query=query.replace(key,value)
    words=set(re.findall(r'[a-zа-яіїєґ]+',query))
    selected=[]
    generic={'paint','primer','topciment','anticatura','silver','gold','bianco','pearl','perl','мат','фарба','лак','клей','шпаклівка'}
    for p in Product.objects.filter(Q(id__in=linked)|Q(id__in=taught),is_active=True).only('id','name','description','price','currency','unit','consumption_per_m2','shop_specs'):
        tokens={w for w in re.findall(r'[a-z]+',p.name.lower()) if len(w)>=3}
        overlap=(tokens-generic)&words
        score=1000 if p.id in linked else sum(len(w) for w in overlap)
        if not score:continue
        selected.append((score,p))
    if not selected:return ''
    blocks=[]
    for _,p in sorted(selected,key=lambda item:(-item[0],item[1].id))[:limit]:
        text=strip_tags(p.description or '').strip()[:2600]
        price=(str(p.price)+' '+p.currency+'/'+p.unit) if p.price>0 else 'ціну потрібно уточнити'
        block=p.name+'\nЦіна: '+price
        if p.consumption_per_m2 is not None:block+='\nВитрата на всі шари: '+str(p.consumption_per_m2)+' '+p.unit+'/м²'
        if text:block+='\n'+text
        blocks.append(block)
    return 'Поточні властивості матеріалів. Якщо старий текст суперечить цим даним, використовуй ці дані; не додавай непідтверджених характеристик. Не пояснюй клієнту внутрішнє зберігання даних.\n\n'+'\n\n'.join(blocks)
