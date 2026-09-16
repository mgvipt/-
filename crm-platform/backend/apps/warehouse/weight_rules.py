"""Регламент ваги й упаковки v2 для ЗП складу (15.09.2026).

Звірено з таблицею Інни по днях (серпень – 12.09, 117 угод; план v15 «Вес и упаковка — правило v2») і з поправками
Олега 15.09 (тест-набори — упаковка до 5 кг; вага кг-товарів = кількість; карниз Orac не 20 кг).

ВАГА
  • одиниця «кг» — кількість у угоді і є кілограми (поле «Вага нетто» в такій картці НЕ множиться);
  • «…_100» / «100 мл» — 0,1 кг за шт; одиниця «л» — літри × щільність; пляшка Primer Deep 1 л — 1 кг;
  • штучний товар з «N кг» / «N мл» у назві — N × к-сть (заводська тара);
  • тест-набір — вага рахується З КОМПЛЕКТАЦІЇ картки (16.09.2026, Олег: набори різні, Патера важча);
    якщо комплектації немає — 0,25 кг; викраски, тара, послуги — 0;
  • інструменти й дрібниці — вага з картки (якщо правдоподібна, до 2 кг за шт) або за типом; разом на угоду
    не менше 0,5 і не більше 5 кг («одна коробка»);
  • великі штучні (карниз, багет, люк, панель…) — вага з картки × к-сть; без ваги — «перевірити» (0 кг).
УПАКОВКА (лише якщо склад пакував сам і це не видача в салоні без ТТН)
  • цілі заводські відра не пакуємо; кожна розфасована порція — одна тара, рівень за кг у ній (до 5 / до 10 / до 20;
    важче 20 — кілька місць);
  • пляшка / банка (до 2 кг) — їде в коробці з інструментами, якщо вони є; без інструментів — окреме місце (16.09.2026);
  • інструменти / дрібниці — одна коробка на угоду (до 5 кг; з пляшкою — за вагою);
  • тест-набір з дощечкою АБО тест-набір + інструменти — одна коробка до 10 кг (16.09.2026, #66012);
  • тест-набори / викраски без іншої упаковки — одна посилка до 5 кг на угоду;
  • великі штучні — місця за вагою рядка.
Лише розрахунок, у БД нічого не пише."""
import re
from decimal import Decimal

KIT_KG = Decimal("0.25")
TOOLS_MIN = Decimal("0.5")
TOOLS_MAX = Decimal("5")
PLAUSIBLE_TOOL_KG = Decimal("2")
BOTTLE_MAX_KG = Decimal("2")   # 16.09.2026: тара до 2 кг (пляшка 1 л, банка) може їхати в коробці з інструментами
_EPS = Decimal("0.0001")

DENS = [(r"піщин|пищин|eleganti|sirena|шовк|silk|galateya|mio|iridis|mermi", "1.2"),
        (r"pattera|патер|dolomite|antico", "1.6"), (r"microcement|мікроцемент|микроцемент", "1.5"),
        (r"slate|слейт", "1.7"), (r"celestial", "1.2"), (r"velvet|luna|lux", "1.5"),
        (r"verma|perla|lumina|protection|лак|litpro|cera", "1.0"),
        (r"primer|ґрунт|грунт|fondo|quartz|second layer", "1.3")]

# Вага інструмента за типом, коли в картці порожньо (план v15 «Вес инструментов», джерела — у таблиці там)
TOOL_TYPES = [(r"валик.*(10\s*см|100\s*мм)", "0.03"), (r"валик", "0.15"),
              (r"ручк.*(250|25\s*см)", "0.25"), (r"ручк", "0.1"), (r"шпател", "0.06"),
              (r"кельм.*(пласт)", "0.25"), (r"кельм.*(240|250)", "0.45"), (r"кельм", "0.35"),
              (r"пенз|кист", "0.06"), (r"маклов", "0.2"), (r"ванночк|кювет", "0.2"),
              (r"стрічк|скотч|лент", "0.25"), (r"плівк|пленк", "0.5"), (r"лез", "0.05"), (r"ніж|нож", "0.1"),
              (r"картридж|герметик|клей.*мл", "0.45")]
LARGE_WORDS = re.compile(r"карниз|багет|молдинг|люк|панел|плінтус|плинтус|розетк", re.I)
TIER_LABEL = {"T5": "до 5 кг", "T10": "до 10 кг", "T20": "до 20 кг"}


def _dec(x):
    try:
        return Decimal(str(x or 0))
    except Exception:
        return Decimal("0")


def _num(s):
    return Decimal(s.replace(",", "."))


def _g(x):
    """Decimal → «5», «0,25», «12,5»."""
    x = _dec(x).quantize(Decimal("0.01"))
    s = ("%f" % x).rstrip("0").rstrip(".")
    return s.replace(".", ",")


def dens(name):
    for rx, d in DENS:
        if re.search(rx, name, re.I):
            return Decimal(d)
    return Decimal("1.3")


def tier(w):
    w = _dec(w)
    return "T5" if w <= 5 + _EPS else ("T10" if w <= 10 + _EPS else "T20")


def split_tiers(w):
    """Вага → список місць: важче 20 кг ділиться на кілька місць по 20."""
    w = _dec(w)
    out = []
    while w > 20 + _EPS:
        out.append("T20")
        w -= 20
    if w > Decimal("0.05"):
        out.append(tier(w))
    return out


def is_salon(deal):
    """Видача в салоні без ТТН — без упаковки (як у таблиці Інни). Салонна угода з ТТН — посилка, пакуємо."""
    fn = ((deal.funnel.name if getattr(deal, "funnel_id", None) else "") or "").lower()
    salon = any(x in fn for x in ("салон", "покрит", "покрыт"))
    return salon and not (getattr(deal, "ttn", "") or "").strip()


def classify(name, unit, qty, card_w=None, is_kit=False, is_tint=False, own=False):
    """Один рядок угоди → {cls, kg, bucket, note, weightless}.
    cls: tare | service | sample | kit | small | mat | bottle | piece | large | tool | unknown."""
    n = (name or "").lower().strip()
    u = (unit or "").strip().lower()
    q = _dec(qty)
    cw = _dec(card_w)
    r = {"cls": "", "kg": Decimal("0"), "bucket": None, "note": "", "weightless": False}
    if is_tint or n.startswith("послуга") or any(k in n for k in ("доставк", "документ", "робот", "замір", "замер")):
        return dict(r, cls="service")
    if re.match(r"тара", n) or "шприц" in n or "флакон пуст" in n:
        return dict(r, cls="tare", note="тара — вага не рахується")
    if "викраск" in n:
        return dict(r, cls="sample", note="викраски — вага не рахується")
    if is_kit or "набір" in n or "набор" in n:
        # 16.09.2026 (Олег): набори різні за вагою — беремо вагу з комплектації картки (cw), 0,25 кг лише як запасний варіант
        w = cw if cw > 0 else KIT_KG
        note = f"тест-набір {_g(w)} кг × {_g(q)}" + ("" if cw > 0 else " (комплектація не заповнена)")
        return dict(r, cls="kit", kg=w * q, note=note)
    if "_100" in n or re.search(r"\b100\s*(мл|ml)\b", n):
        # флакон 100 мл (Primer Deep 1 …_100) — 0,1 кг за шт; перевіряємо ДО правила «тонер у мл»
        return dict(r, cls="small", kg=Decimal("0.1") * q, note=f"{_g(q)} × 0,1 кг (100 мл)")
    if "тонер" in n or "toner" in n or u in ("мл", "ml") or re.search(r"[^\d\s]\s+мл\s*$", n):
        # колоранти / тонер у мл: к-сть — це мілілітри; 1 мл ≈ 1,5 г. «мл» без числа перед ним (…(Охра) мл),
        # а не «300 мл» / «100 мл» у назві флакона — ті рахуються за обʼємом тари нижче
        return dict(r, cls="small", kg=q * Decimal("0.0015"), note=f"{_g(q)} мл × 1,5 г")
    mk = re.search(r"(\d+[.,]?\d*)\s*(кг|kg)\b", n)
    ml = re.search(r"(\d+[.,]?\d*)\s*(мл|ml)\b", n)
    mlit = re.search(r"(\d+[.,]?\d*)\s*(л|l)\b", n)
    if u in ("кг", "kg"):
        P = _num(mk.group(1)) if mk else None
        return dict(r, cls="mat", kg=q, bucket=P,
                    note=f"{_g(q)} кг (одиниця «кг»)" + (f"; заводське відро {_g(P)} кг" if P else ""))
    if u in ("л", "l"):
        d = dens(n)
        return dict(r, cls="bottle", kg=q * d, note=f"{_g(q)} л × {_g(d)} кг/л")
    if u in ("мл", "ml"):
        return dict(r, cls="small", kg=q * Decimal("0.0015"), note=f"{_g(q)} мл × 1,5 г")
    if "primer deep 1" in n:
        return dict(r, cls="bottle", kg=q, note=f"{_g(q)} × 1 кг (пляшка 1 л)")
    if mk:
        P = _num(mk.group(1))
        return dict(r, cls="piece", kg=q * P, bucket=P, note=f"{_g(q)} шт × {_g(P)} кг")
    if ml or mlit:
        L = (_num(ml.group(1)) / 1000) if ml else _num(mlit.group(1))
        d = dens(n)
        return dict(r, cls="piece", kg=q * L * d, note=f"{_g(q)} шт × {_g(L)} л × {_g(d)} кг/л")
    if LARGE_WORDS.search(n) or cw > PLAUSIBLE_TOOL_KG:
        if cw > 0:
            return dict(r, cls="large", kg=cw * q, note=f"{_g(q)} шт × {_g(cw)} кг (вага з картки)")
        return dict(r, cls="large", weightless=True, note="великий товар без ваги в картці — перевірити")
    if own:
        return dict(r, cls="unknown", weightless=True, note="своя позиція без номенклатури — вагу вказує склад")
    if 0 < cw <= PLAUSIBLE_TOOL_KG:
        return dict(r, cls="tool", kg=cw * q, note=f"інструмент {_g(q)} шт × {_g(cw)} кг (з картки)")
    for rx, kg in TOOL_TYPES:
        if re.search(rx, n):
            return dict(r, cls="tool", kg=Decimal(kg) * q, note=f"інструмент {_g(q)} шт × {kg.replace('.', ',')} кг (за типом)")
    return dict(r, cls="tool", kg=Decimal("0.1") * q, note=f"дрібнота {_g(q)} шт × 0,1 кг (за типом)")


def plan(items, salon=False, packing=True):
    """items: [{name, unit, qty, card_w, is_kit, is_tint, own, product_id}] → вага, місця упаковки, пояснення."""
    kg = Decimal("0")
    tiers = {"T5": 0, "T10": 0, "T20": 0}
    how, weightless = [], []
    tools_kg = Decimal("0")
    small_kg = Decimal("0")
    bottles = []   # 16.09.2026 (Олег): пляшки/банки до 2 кг — їдуть у коробці з інструментами, якщо вона є
    n_tools = n_small = n_kits = n_samples = n_board = containers = 0
    do_pack = packing and not salon

    def add(t, why):
        nonlocal containers
        tiers[t] += 1
        containers += 1
        how.append(f"  {why} → упаковка {TIER_LABEL[t]}")

    for it in items:
        c = classify(it.get("name"), it.get("unit"), it.get("qty"), it.get("card_w"),
                     it.get("is_kit", False), it.get("is_tint", False), it.get("own", False))
        title = (it.get("name") or "")[:48]
        if c["cls"] == "service":
            continue
        if c["note"]:
            how.append(f"{title} — {c['note']}")
        if c["weightless"]:
            weightless.append({"product_id": it.get("product_id"), "name": it.get("name") or "", "unit": it.get("unit") or "",
                               "qty": str(_dec(it.get("qty")))})
        if c["cls"] == "tool":
            tools_kg += c["kg"]
            n_tools += 1
            continue
        kg += c["kg"]
        if c["cls"] == "small":
            n_small += 1
            small_kg += c["kg"]
        elif c["cls"] == "kit":
            n_kits += 1
            low = (it.get("name") or "").lower()
            if "дощечк" in low and "без дощечк" not in low:  # «з дощечкою»; «бе-з дощечки» — без
                n_board += 1
        elif c["cls"] == "sample":
            n_samples += 1
        if not do_pack:
            continue
        if c["cls"] == "mat":
            q, P = c["kg"], c["bucket"]
            full = int((q + Decimal("0.01")) / P) if (P and q >= P - Decimal("0.01")) else 0
            rest = q - full * (P or 0)
            # 16.09.2026 (Олег): цілі заводські відра теж пакуємо; без упаковки — лише «контейнер НП» (packed = ні)
            for _ in range(full):
                for t in split_tiers(P):
                    add(t, f"заводське відро {_g(P)} кг")
            for t in split_tiers(rest):
                add(t, f"розфасовка {_g(rest)} кг")
        elif c["cls"] in ("bottle", "piece"):
            n_ = max(1, int(round(float(_dec(it.get("qty")))))) if c["cls"] == "piece" else 1
            per = c["kg"] / n_ if n_ else c["kg"]
            for _ in range(n_):
                if per <= BOTTLE_MAX_KG:
                    bottles.append(per)   # пляшка/банка: вирішимо після циклу — з інструментами чи окремо
                else:
                    for t in split_tiers(per) or ["T5"]:
                        add(t, f"тара {_g(per)} кг")
        elif c["cls"] == "large" and c["kg"] > 0:
            for t in split_tiers(c["kg"]):
                add(t, f"великий товар {_g(c['kg'])} кг")
    if n_tools:
        clamped = min(max(tools_kg, TOOLS_MIN), TOOLS_MAX)
        kg += clamped
        how.append(f"  інструменти/дрібниці разом {_g(tools_kg)} кг → рахуємо {_g(clamped)} кг (не менше 0,5, не більше 5)")
    if do_pack:
        box_goods = bool(n_tools or n_small)
        ride = bool(bottles) and box_goods          # пляшки їдуть разом з інструментами — клієнт платить за менше місць
        bottles_kg = sum(bottles, Decimal("0"))
        with_bottle = f" + пляшки {_g(bottles_kg)} кг у тій же коробці" if ride else ""
        if n_board:
            # 16.09.2026 (Олег): тест-набір з дощечкою — коробка до 10 кг; інструменти й дрібниці — в ній же
            tiers["T10"] += 1
            how.append("  тест-набір з дощечкою — коробка до 10 кг" + (" (інструменти/дрібниці — в ній же)" if box_goods else "") + with_bottle)
        elif n_kits and box_goods:
            # 16.09.2026 (Олег, #66012): тест-набір без дощечки разом з інструментами — теж одна коробка до 10 кг
            tiers["T10"] += 1
            how.append("  тест-набір без дощечки + інструменти — одна коробка до 10 кг" + with_bottle)
        elif box_goods:
            box = (min(max(tools_kg, TOOLS_MIN), TOOLS_MAX) if n_tools else Decimal("0")) + small_kg + (bottles_kg if ride else Decimal("0"))
            t = tier(box) if box > 0 else "T5"
            tiers[t] += 1
            how.append(f"  інструменти/дрібниці — одна коробка {TIER_LABEL[t]}" + with_bottle)
        elif (n_kits or n_samples) and not (containers or bottles):
            tiers["T5"] += 1
            how.append("  тест-набори/викраски — одна посилка до 5 кг")
        if bottles and not ride:
            # 16.09.2026 (Олег): пляшка без інструментів — окреме місце за її вагою (зазвичай до 5 кг)
            for per in bottles:
                for t in split_tiers(per) or ["T5"]:
                    add(t, f"пляшка/банка {_g(per)} кг — окреме місце")
    elif salon:
        how.append("  видача в салоні без ТТН — упаковка не оплачується")
    return {"weight": kg.quantize(Decimal("0.001")), "tiers": tiers, "how": how, "weightless": weightless}


def kit_kg(product):
    """Вага тест-набору = сума ваг його комплектації (16.09.2026, Олег: «всі набори мають рахуватися зі складу»).
    Кожен компонент зважується тим самим classify(): «кг» — це кілограми, «л» — × щільність, шт — вага картки.
    Комплектації немає (або нульова) → None, тоді спрацює запасне значення KIT_KG."""
    try:
        comps = list(product.components.select_related("component").all())
    except Exception:
        return None
    tot = Decimal("0")
    for c in comps:
        cp = c.component
        if cp is None:
            continue
        tot += classify(cp.name, cp.unit, c.quantity, card_w=cp.weight_kg)["kg"]
    return tot.quantize(Decimal("0.001")) if tot > 0 else None


def deal_items(deal):
    """Рядки угоди → вхід для plan(): назва, одиниця, к-сть, вага з картки, чи тест-набір, чи тонування."""
    out = []
    for it in deal.items.select_related("product").all():
        p = it.product
        if p is None:
            out.append({"name": getattr(it, "custom_name", "") or "Позиція", "unit": "шт", "qty": it.quantity,
                        "card_w": None, "own": True, "product_id": None})
            continue
        name = p.name or ""
        low = name.lower()
        is_tint = low.strip().startswith("послуга тонування")
        is_kit = (not is_tint) and ("тестов" in low or (not ("викраск" in low) and p.components.exists()))
        cw = kit_kg(p) if is_kit else p.weight_kg  # 16.09.2026: вага набору — сума комплектації, а не цифра в картці
        out.append({"name": name, "unit": p.unit or "", "qty": it.quantity, "card_w": cw,
                    "is_kit": is_kit, "is_tint": is_tint, "own": False, "product_id": p.id})
    return out


def deal_plan(deal, salon=None, packing=True):
    return plan(deal_items(deal), salon=is_salon(deal) if salon is None else salon, packing=packing)
