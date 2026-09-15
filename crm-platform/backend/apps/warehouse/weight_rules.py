"""Регламент ваги й упаковки v2 для ЗП складу (15.09.2026).

Звірено з таблицею Інни по днях (серпень – 12.09, 117 угод; план v15 «Вес и упаковка — правило v2») і з поправками
Олега 15.09 (тест-набори — упаковка до 5 кг; вага кг-товарів = кількість; карниз Orac не 20 кг).

ВАГА
  • одиниця «кг» — кількість у угоді і є кілограми (поле «Вага нетто» в такій картці НЕ множиться);
  • «…_100» / «100 мл» — 0,1 кг за шт; одиниця «л» — літри × щільність; пляшка Primer Deep 1 л — 1 кг;
  • штучний товар з «N кг» / «N мл» у назві — N × к-сть (заводська тара);
  • тест-набір — 0,25 кг за набір (ваги в картках наборів 3 / 5 / 7 кг — помилкові); викраски, тара, послуги — 0;
  • інструменти й дрібниці — вага з картки (якщо правдоподібна, до 2 кг за шт) або за типом; разом на угоду
    не менше 0,5 і не більше 5 кг («одна коробка»);
  • великі штучні (карниз, багет, люк, панель…) — вага з картки × к-сть; без ваги — «перевірити» (0 кг).
УПАКОВКА (лише якщо склад пакував сам і це не видача в салоні без ТТН)
  • цілі заводські відра не пакуємо; кожна розфасована порція — одна тара, рівень за кг у ній (до 5 / до 10 / до 20;
    важче 20 — кілька місць);
  • пляшка / банка — окрема тара за її вагою (зазвичай до 5 кг);
  • інструменти / дрібниці — одна коробка до 5 кг на угоду;
  • тест-набори / викраски без іншої упаковки — одна посилка до 5 кг на угоду;
  • великі штучні — місця за вагою рядка.
Лише розрахунок, у БД нічого не пише."""
import re
from decimal import Decimal

KIT_KG = Decimal("0.25")
TOOLS_MIN = Decimal("0.5")
TOOLS_MAX = Decimal("5")
PLAUSIBLE_TOOL_KG = Decimal("2")
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
        return dict(r, cls="kit", kg=KIT_KG * q, note=f"тест-набір {_g(KIT_KG)} кг × {_g(q)}")
    if "тонер" in n or "toner" in n or u in ("мл", "ml") or re.search(r"\bмл\s*$", n):
        # колоранти / тонер у мл: к-сть — це мілілітри (у картці часто одиниця «шт»); 1 мл ≈ 1,5 г
        return dict(r, cls="small", kg=q * Decimal("0.0015"), note=f"{_g(q)} мл × 1,5 г")
    if "_100" in n or re.search(r"\b100\s*(мл|ml)\b", n):
        return dict(r, cls="small", kg=Decimal("0.1") * q, note=f"{_g(q)} × 0,1 кг (100 мл)")
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
    n_tools = n_small = n_kits = n_samples = containers = 0
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
        elif c["cls"] == "kit":
            n_kits += 1
        elif c["cls"] == "sample":
            n_samples += 1
        if not do_pack:
            continue
        if c["cls"] == "mat":
            q, P = c["kg"], c["bucket"]
            full = int((q + Decimal("0.01")) / P) if (P and q >= P - Decimal("0.01")) else 0
            rest = q - full * (P or 0)
            if full:
                how.append(f"  {full} заводськ. відро(а) по {_g(P)} кг — не пакуємо")
            for t in split_tiers(rest):
                add(t, f"розфасовка {_g(rest)} кг")
        elif c["cls"] in ("bottle", "piece"):
            n_ = max(1, int(round(float(_dec(it.get("qty")))))) if c["cls"] == "piece" else 1
            per = c["kg"] / n_ if n_ else c["kg"]
            for _ in range(n_):
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
        if n_tools or n_small:
            tiers["T5"] += 1
            how.append("  інструменти/дрібниці — одна коробка до 5 кг")
        elif (n_kits or n_samples) and not containers:
            tiers["T5"] += 1
            how.append("  тест-набори/викраски — одна посилка до 5 кг")
    elif salon:
        how.append("  видача в салоні без ТТН — упаковка не оплачується")
    return {"weight": kg.quantize(Decimal("0.001")), "tiers": tiers, "how": how, "weightless": weightless}


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
        out.append({"name": name, "unit": p.unit or "", "qty": it.quantity, "card_w": p.weight_kg,
                    "is_kit": is_kit, "is_tint": is_tint, "own": False, "product_id": p.id})
    return out


def deal_plan(deal, salon=None, packing=True):
    return plan(deal_items(deal), salon=is_salon(deal) if salon is None else salon, packing=packing)
