"""Склад Фаза-1: endpoints роботи кладовщика + движок ЗП + обід (на WorkSession.pause)."""
import calendar
import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import WarehouseJob, WarehousePayrollEntry, WarehousePhoto, TareType
from . import weight_rules as WR  # 15.09.2026: регламент ваги/упаковки v2 (план v15 «Вес и упаковка»)

LUNCH_NORM_MIN = 60   # норма обіду
DAY_HOURS = 8


# ── 15.09.2026 (whpay): ставки складу — ЛИШЕ живі статті Фінмоделі (категорія «Ставки складу»; на проді id 89–95).
# Ті самі числа показують Налаштування → Ставки співробітників і Фінанси → Фінмодель. Запасних чисел у коді немає:
# статтю вимкнено або видалено → ставка 0 (не нараховуємо) і попередження у вкладці «ЗП».
WH_RATE_CODES = ("WH_RATE_KG", "WH_PACK_5", "WH_PACK_10", "WH_PACK_20", "WH_TINT_PCT", "WH_RATE_DAY", "bundle_assembly",
                 # 16.09.2026 (Олег): тест-набори — фіксовані суми за тонування + ціна доплати для клієнта
                 "WH_KIT_TINT_CAT", "WH_KIT_TINT_IND", "KIT_TINT_PRICE_IND", "KIT_TINT_PRICE_RICH",
                 "WH_WASHED_PCT", "WH_SAMPLE_SHEET", "SAMPLE_TINT_PRICE_IND",
                 # 17.09.2026 (Олег): за викраску платимо, коли вона поїхала клієнту — окремо каталог і індивідуальний колір
                 "WH_SAMPLE_CAT", "WH_SAMPLE_IND")  # 16.09.2026: мите відро (% від закупки нового), викраски (₴ за аркуш А3)
WH_RATE_TEXT = {  # code: (назва, якщо статті немає; одиниця; за що)
    "WH_RATE_KG": ("Відвантаження: ставка за кг", "₴/кг", "вага відвантаження: кілограми замовлення × ставка"),
    "WH_PACK_5": ("Упаковка до 5 кг", "₴/місце", "упаковка місця до 5 кг (якщо пакували самі)"),
    "WH_PACK_10": ("Упаковка до 10 кг", "₴/місце", "упаковка місця до 10 кг"),
    "WH_PACK_20": ("Упаковка до 20 кг", "₴/місце", "упаковка місця до 20 кг; важче — кілька місць"),
    "WH_TINT_PCT": ("Тонування", "%", "% від суми рядка «Послуга тонування» в угоді (немає рядка — за позначкою наборів)"),
    "WH_RATE_DAY": ("Ставка за робочий день", "₴/день", "кнопка «Завершити день»; мінус за обід понад норму"),
    "bundle_assembly": ("Оплата складу за збірку тестового набору", "₴/набір",
                        "збірка тестового набору (ця ж ставка входить у собівартість набору)"),
    "WH_KIT_TINT_CAT": ("Тонування набору: колір з каталогу", "₴/набір",
                        "за кожен набір з картки «з тонуванням» (колір за номером каталогу)"),
    "WH_KIT_TINT_IND": ("Тонування набору: індивідуальний колір", "₴/набір",
                        "за кожен набір, де менеджер поставив «індивідуальний / насичений колір» в угоді"),
    "KIT_TINT_PRICE_IND": ("Ціна клієнту: індивідуальний колір набору", "₴/набір",
                           "доплата в угоді, коли клієнт просить свій колір (не з каталогу)"),
    "KIT_TINT_PRICE_RICH": ("Ціна клієнту: насичений колір набору (від)", "₴/набір",
                            "доплата, коли колір насичений: від 20 мл колоранту на 250 г матеріалу — підбір довший"),
    "SAMPLE_TINT_PRICE_IND": ("Ціна клієнту: індивідуальний колір викраски", "₴/викраска",
                              "доплата до ціни викраски (за каталогом 150 ₴ → індивідуальна 250 ₴)"),
    "WH_WASHED_PCT": ("Мите відро", "%", "% від закупівельної ціни нового відра — за кожне мите відро, що поїхало до клієнта"),
    "WH_SAMPLE_SHEET": ("Викраски", "₴/аркуш А3", "за кожен аркуш А3 викрасок (з аркуша — кілька викрасок)"),
    "WH_SAMPLE_CAT": ("Викраска: колір з каталогу", "₴/викраска",
                      "за кожну відправлену викраску в кольорі з каталогу (ця ж ставка входить у собівартість викраски)"),
    "WH_SAMPLE_IND": ("Викраска: індивідуальний колір", "₴/викраска",
                      "за кожну відправлену викраску, де менеджер поставив «індивідуальний колір»"),
}


def live_rates():
    """Ставки складу з Фінмоделі одним запитом: {code: {id, name, value (Decimal), active, found}}."""
    from apps.finance.models import FinModelArticle
    out = {c: {"id": None, "name": "", "value": Decimal("0"), "active": False, "found": False} for c in WH_RATE_CODES}
    for a in FinModelArticle.objects.filter(code__in=WH_RATE_CODES).order_by("-active", "id"):
        r = out[a.code]
        if r["found"]:
            continue
        try:
            v = Decimal(str(a.value or 0))
        except Exception:
            v = Decimal("0")
        r.update(id=a.id, name=a.name, value=v, active=bool(a.active), found=True)
    return out


def _rate(code, rates=None):
    """Жива ставка складу (Decimal). Статті немає або її вимкнено → 0: «за замовчуванням» нічого не нараховуємо."""
    r = (rates if rates is not None else live_rates()).get(code)
    return r["value"] if r and r["active"] else Decimal("0")


def _dec(x):
    """Decimal('1.50') → «1,5»; 300 → «300»."""
    return ("%g" % float(x or 0)).replace(".", ",")


def rates_short(rates=None):
    """Один рядок «ставки зараз» — для розшифровки ЗП у Фінансах."""
    lr = rates if rates is not None else live_rates()
    v = {c: _dec(_rate(c, lr)) for c in WH_RATE_CODES}
    return (f"Ставки складу зараз (Фінмодель): вага {v['WH_RATE_KG']} ₴/кг · упаковка {v['WH_PACK_5']} / {v['WH_PACK_10']} / "
            f"{v['WH_PACK_20']} ₴ · тонування {v['WH_TINT_PCT']}% · тест-набір {v['bundle_assembly']} ₴"
            f" · тонування набору {v['WH_KIT_TINT_CAT']} / {v['WH_KIT_TINT_IND']} ₴"
            + (f" · день {v['WH_RATE_DAY']} ₴" if _rate("WH_RATE_DAY", lr) else ""))


def _perm(u, code):
    return bool(u and getattr(u, "is_authenticated", False)
                and (u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code(code))))


def rates_payload(user):
    """Ставки складу для вкладок «ЗП» і «Дашборд» (лише показ). Змінюють у Налаштування → Ставки співробітників
    (там само, що й Фінмодель): кнопку бачить лише той, хто там може змінювати ставки складу."""
    lr = live_rates()
    items, warnings = [], []
    for code in WH_RATE_CODES:
        r = lr[code]
        if code.startswith("KIT_TINT_PRICE") or code.startswith("SAMPLE_TINT_PRICE"):
            continue  # 16.09.2026 (Олег): ціни доплати для клієнта складу не показуємо — лише те, що платимо складу
        if code in ("WH_RATE_DAY", "WH_SAMPLE_SHEET") and not r["active"]:
            continue  # 15.09.2026 (Олег): ставка комірника — за табелем (блок «Ставка»); вимкнену ставку дня не показуємо
        name, unit, hint = WH_RATE_TEXT[code]
        items.append({"code": code, "id": r["id"], "name": r["name"] or name, "value": float(_rate(code, lr)),
                      "unit": unit, "hint": hint, "active": r["active"], "found": r["found"]})
        if not r["found"]:
            warnings.append(f"Ставки «{name}» немає у Фінмоделі — за це зараз нічого не нараховується")
        elif not r["active"]:
            warnings.append(f"Ставку «{r['name']}» у Фінмоделі вимкнено — за це зараз нічого не нараховується")
    kg, p10, tint, day = (_rate(c, lr) for c in ("WH_RATE_KG", "WH_PACK_10", "WH_TINT_PCT", "WH_RATE_DAY"))
    ex = []
    if kg or p10:
        ex.append(f"посилка 7 кг = 7 × {_dec(kg)} + {_dec(p10)} = {_dec(7 * kg + p10)} ₴")
    if tint:
        ex.append(f"«Послуга тонування» на 1 000 ₴ → {_dec(tint)}% = {_dec(1000 * tint / 100)} ₴")
    lunch = (f"Норма обіду — {LUNCH_NORM_MIN} хв; понад норму — мінус {_dec((day / DAY_HOURS).quantize(Decimal('0.01')))} ₴ "
             f"за кожну годину (ставка дня {_dec(day)} ÷ {DAY_HOURS} год)." if day else "")
    can_edit = _perm(user, "payroll.rates.view") and _perm(user, "finance.manage") and _perm(user, "finance.model.edit")
    return {"items": items, "example": ("Приклад: " + "; ".join(ex) + ".") if ex else "", "lunch": lunch,
            "warnings": warnings, "can_edit": can_edit, "edit_url": "/settings?tab=payrates",
            "same_as": "Це ті самі числа, що у Фінанси → Фінмодель («Склад / ставки») і в Налаштування → Ставки "
                       "співробітників: одна ставка на всіх. Змінили там — склад рахує по-новому з наступного "
                       "відвантаження; уже нараховані записи не переписуються."}


def _packing_tiers(weight):
    """Авто-розбивка ваги на місця ≤20кг → рівні упаковки."""
    w = float(weight or 0)
    t = {"T5": 0, "T10": 0, "T20": 0}
    while w > 0.001:
        if w <= 5:
            t["T5"] += 1; w = 0
        elif w <= 10:
            t["T10"] += 1; w = 0
        elif w <= 20:
            t["T20"] += 1; w = 0
        else:
            t["T20"] += 1; w -= 20
    return t


def _deal_weight(deal):
    """15.09.2026: вага за регламентом v2 (одиниця «кг» = кількість; тест-набір 0,25 кг; інструменти — одна коробка…).
    Раніше було «вага з картки × к-сть» — давало 5–8 кг за тест-набір і 0 кг за кг-товари з порожньою карткою."""
    return WR.deal_plan(deal, packing=False)["weight"]


# ── 14.09.2026 (wh-accrual): тонування з рядка «Послуга тонування», тестові набори, товари без ваги ──
TINT_SERVICE_PREFIX = "послуга тонування"  # товар-послуга в угоді (у CRM: id 1311, B24-35270)
TEST_SET_WORD = "тестов"                   # «Тестовий/тестовый набір» у назві товару


def _is_tint_service(p):
    return bool(p is not None and (p.name or "").strip().lower().startswith(TINT_SERVICE_PREFIX))


def _is_sample(p):
    """Викраска 10×30 см (готовий зразок) — не набір і не послуга."""
    from apps.crm.kit_tint import is_sample_product
    return bool(p is not None and is_sample_product(p))


def _is_test_set(p):
    """Тестовий набір = товар-НАБІР (має компоненти, розділ «НАБОРИ») або «тестов…» у назві."""
    if p is None or _is_tint_service(p):
        return False
    if TEST_SET_WORD in (p.name or "").lower():
        return True
    return p.components.exists()


def _num(x):
    x = Decimal(x or 0)
    return str(x.quantize(Decimal("1"))) if x == x.to_integral_value() else str(x)


def _deal_accrual_facts(deal):
    """Факти угоди для нарахувань складу (лише читання):
    tint_base — сума рядків «Послуга тонування» (зі знижкою рядка); test_sets — к-сть тестових наборів;
    weightless — фізичні товари без ваги (не тест-набори і не послуги): за них не буде оплати за кг/упаковку."""
    tint_base = Decimal("0"); tint_lines = 0; test_sets = Decimal("0"); weightless = {}
    kit_cat = Decimal("0"); kit_ind = Decimal("0")   # 16.09.2026: набори з тонуванням — каталог / індивідуальне
    sample_cat = Decimal("0"); sample_ind = Decimal("0")  # 17.09.2026: викраски — колір з каталогу / індивідуальний
    for it in deal.items.select_related("product"):
        p = it.product
        if p is None:
            continue  # своя позиція без номенклатури
        if _is_tint_service(p):
            if str(getattr(it, "tint_mode", "") or "").startswith("auto"):
                continue  # доплата за тонування набору: складу йде фіксована ставка, а не 20% — двічі не платимо
            tint_base += Decimal(it.total or 0); tint_lines += 1
            continue
        if _is_sample(p):
            # 17.09.2026 (Олег): викраски роблять аркушем (4 шт), решта лишається на складі;
            # складу платимо за кожну ВІДПРАВЛЕНУ викраску: з каталогу — одна ставка, індивідуальний колір — більша.
            q = it.quantity or Decimal("0")
            if str(getattr(it, "tint_mode", "") or "") == "s_ind":
                sample_ind += q
            else:
                sample_cat += q
            continue
        if _is_test_set(p):
            q = it.quantity or Decimal("0")
            test_sets += q
            if str(getattr(it, "tint_mode", "") or "") in ("ind", "rich"):
                kit_ind += q
            elif getattr(p, "shop_is_tinted", False):
                kit_cat += q
            continue
    # 15.09.2026 (регламент v2): «без ваги» — лише те, що правило не може зважити (великий товар без ваги в картці,
    # своя позиція без номенклатури). Кг-товари, тест-набори, інструменти — вага за правилом.
    wl = WR.deal_plan(deal, salon=False, packing=False)["weightless"]
    return {"tint_base": tint_base, "tint_lines": tint_lines, "test_sets": test_sets, "weightless": wl,
            "kit_cat": kit_cat, "kit_ind": kit_ind, "sample_cat": sample_cat, "sample_ind": sample_ind}


PHOTO_LABEL = {"buckets": "Відерця з наклейкою", "parcel": "Готова коробка", "invoice": "Накладна",
               "tint_archive": "Архів тонування (рецепт кольору)"}


def _needs_tint_photo(job):
    """16.09.2026 (Олег): якщо в угоді є тонування — склад фотографує запис в архіві тонування (рецепт)."""
    try:
        fx = _deal_accrual_facts(job.deal)
        return bool(fx["tint_base"] > 0 or fx.get("kit_cat") or fx.get("kit_ind") or (job.tinted_kits or []))
    except Exception:
        return False


def _no_parcel(job):
    """Коробки немає: самовивіз із салону або салонна угода без ТТН (алмазне, вентиляція, покриття, опт)."""
    deal = job.deal
    return bool(_is_pickup(deal) or (WR.is_salon_funnel(deal.funnel.name if deal.funnel_id else "")
                                     and not (deal.ttn or "").strip()))


def _is_pickup(job_or_deal):
    """23.09.2026 (Олег): клієнт забирає в салоні — посилка не їде, пакувати не треба."""
    deal = getattr(job_or_deal, "deal", job_or_deal)
    return bool((getattr(deal, "qualification", None) or {}).get("pickup_salon"))


def _required_photo_kinds(job):
    """Обовʼязкові фото перед «Готово — відправлено»: відерця, коробка, накладна; + архів тонування, якщо є тонування.
    Самовивіз із салону — коробки немає, решта документів як завжди."""
    kinds = ["buckets", "invoice"] if _no_parcel(job) else ["buckets", "parcel", "invoice"]
    if _needs_tint_photo(job):
        kinds.append("tint_archive")
    return kinds


def _job_dict(job, full=False):
    deal = job.deal
    q = deal.qualification or {}
    d = {
        "id": job.id, "status": job.status, "deal_id": deal.id,
        "client": (deal.contact.first_name if deal.contact_id else None) or (deal.title or ""),
        "city": q.get("city", ""), "ship": q.get("ship", ""), "ttn": deal.ttn or "",
        "kits": q.get("kits", []) or [], "tinted_kits": job.tinted_kits or [],
        "packed": job.packed,
        "assignee": job.assignee_id, "assignee_name": (job.assignee.get_full_name() if job.assignee_id else ""),
        "created_at": job.created_at.isoformat(),
    }
    fn = (deal.funnel.name if deal.funnel_id else "") or ""
    d["funnel"] = fn
    d["ship_offreg"] = bool(q.get("ship_offreg") or q.get("ship_offreg_note"))
    d["pickup_salon"] = bool(q.get("pickup_salon"))   # 23.09.2026: не їде НП, не пакувати
    d["kind_type"] = "test" if "\u0442\u0435\u0441\u0442\u043e\u0432" in fn.lower() else "main"
    # 23.09.2026: салон — це і воронки «N.С/…» (алмазне, вентиляція, опт), і позначка «забирає в салоні»
    # канал лишається онлайн навіть із самовивозом (Олег 23.09): це онлайн-продаж, просто без відправки
    d["channel"] = "offline" if WR.is_salon_funnel(fn) else "online"
    try:
        d["np_stage"] = (job.deal.stage.name if (job.deal_id and getattr(job.deal, "stage_id", None)) else "")
    except Exception:
        d["np_stage"] = ""
    d["photos_n"] = job.photos.count()
    d["ref_photos_n"] = len(deal.ref_photos or [])
    try:
        d["np_name"] = ((deal.np_data or {}).get("recipient") or {}).get("name") or ""
    except Exception:
        d["np_name"] = ""
    # «Одна посилка»: звʼязані дозамовлення/родитель без ТТН — щоб склад пакував разом і робив ОДНУ ТТН
    try:
        from apps.crm.models import Deal as _Dl
        _root = deal.parent_deal or deal
        _gids = set([_root.id]) | set(_root.children.values_list("id", flat=True))
        _gids.discard(deal.id)
        d["parcel_orders"] = [{"id": gd.id, "title": gd.title, "is_dozakaz": bool(gd.parent_deal_id)}
                              for gd in _Dl.objects.filter(id__in=_gids) if not gd.ttn]
        d["parcel_main"] = _root.id
        d["is_dozakaz"] = bool(deal.parent_deal_id)
    except Exception:
        d["parcel_orders"] = []; d["parcel_main"] = deal.id; d["is_dozakaz"] = False
    # підзадачі: дозамовлення цієї посилки (показуємо всередині основної задачі)
    try:
        _subs = WarehouseJob.objects.filter(deal__parent_deal_id=deal.id).exclude(status="cancelled").select_related("deal")
        d["subtasks"] = [{"job_id": sj.id, "deal_id": sj.deal_id, "title": sj.deal.title, "status": sj.status,
                          "kits_n": len((sj.deal.qualification or {}).get("kits", []) or []),
                          "items": [{"name": (it.product.name if it.product_id else (it.custom_name or "Позиція")), "qty": str(it.quantity)} for it in sj.deal.items.all()]}
                         for sj in _subs]
    except Exception:
        d["subtasks"] = []
    if full:
        d["items"] = [{"name": (it.product.name if it.product_id else ((it.custom_name or "Позиція") + " · не зі складу")), "qty": str(it.quantity),
                       "weight_kg": str((it.product.weight_kg or 0) if it.product_id else 0)} for it in deal.items.all()]
        _w = _deal_weight(deal)
        d["weight_kg"] = str(_w)
        # 14.09 (wh-accrual): товари без ваги → оплата за кг/упаковку не нарахується; склад бачить список ДО відправки
        try:
            _wl = _deal_accrual_facts(deal)["weightless"]
        except Exception:
            _wl = []
        d["weightless"] = _wl
        d["weightless_zero_total"] = bool(_wl) and _w <= 0
        d["photos"] = [{"id": p.id, "kind": p.kind, "url": "/api/warehouse/jobs/%d/photo/?id=%d" % (job.id, p.id)} for p in job.photos.all()]
        d["required_photos"] = [{"kind": k, "label": PHOTO_LABEL.get(k, k)} for k in _required_photo_kinds(job)]
        try:
            from .tare_samples import tare_lines
            d["tare_lines"] = tare_lines(job)  # 16.09.2026: тара угоди, яку можна відправити митим відром
        except Exception:
            d["tare_lines"] = []
        d["needs"] = {k: v for k, v in (deal.qualification or {}).items() if k != "kits" and not str(k).startswith("_")}
        d["ref_photos"] = deal.ref_photos or []
        d["phone"] = ((deal.contact.phone if deal.contact_id else "") or "")
    return d


def _is_nested(job):
    """Дозамовлення, що їде посилкою основної (у якої є активна задача) — ховаємо з черги, показуємо підзадачею."""
    pid = job.deal.parent_deal_id if job.deal_id else None
    if not pid:
        return False
    return WarehouseJob.objects.filter(deal_id=pid).exclude(status__in=["shipped", "cancelled"]).exists()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def queue(request):
    jobs = (WarehouseJob.objects.filter(status="queued", assignee__isnull=True)
            .select_related("deal", "deal__contact", "deal__stage").order_by("created_at")[:50])
    mine = (WarehouseJob.objects.filter(assignee=request.user)
            .exclude(status__in=["shipped", "cancelled"]).select_related("deal", "deal__contact", "deal__stage")[:50])
    shipped = (WarehouseJob.objects.filter(assignee=request.user, status="shipped")
               .select_related("deal", "deal__contact", "deal__stage").order_by("-shipped_at")[:30])
    out = {"queue": [_job_dict(j) for j in jobs if not _is_nested(j)], "mine": [_job_dict(j) for j in mine if not _is_nested(j)], "shipped": [_job_dict(j) for j in shipped]}
    u = request.user
    if u.is_superuser or (hasattr(u, "has_perm_code") and (u.has_perm_code("warehouse.view.all") or u.has_perm_code("roles.manage"))):
        # керівник/адмін: УСІ активні задачі всіх співробітників (хто що робить зараз)
        act = (WarehouseJob.objects.exclude(status__in=["shipped", "cancelled"]).exclude(assignee__isnull=True)
               .select_related("deal", "deal__contact", "deal__stage", "assignee").order_by("-created_at")[:80])
        from django.utils import timezone as _tz
        from datetime import timedelta as _td
        recent = (WarehouseJob.objects.filter(status="shipped", shipped_at__gte=_tz.now() - _td(days=7))
                  .select_related("deal", "deal__contact", "deal__stage", "assignee").order_by("-shipped_at")[:40])
        out["all_active"] = [_job_dict(j) for j in act if not _is_nested(j)]
        out["all_shipped_7d"] = [_job_dict(j) for j in recent]
    return Response(out)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_detail(request, pk):
    job = WarehouseJob.objects.filter(pk=pk).select_related("deal").first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    return Response(_job_dict(job, full=True))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def deal_shipment(request, deal_id):
    """Задача відвантаження по сделці (read-only): статус, фото складовщика, дати."""
    job = (WarehouseJob.objects.filter(deal_id=deal_id)
           .select_related("deal", "deal__contact", "deal__stage", "assignee").order_by("-created_at").first())
    if not job:
        return Response({"job": None})
    d = _job_dict(job, full=True)
    d["taken_at"] = job.taken_at.isoformat() if job.taken_at else None
    d["shipped_at"] = job.shipped_at.isoformat() if job.shipped_at else None
    d["shipped_weight_kg"] = str(job.shipped_weight_kg or 0)
    return Response({"job": d})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shipments_history(request):
    """Історія відвантажень з фільтром за період + пошук по № сделки / клієнту."""
    from django.db.models import Q as _Qh
    u = request.user
    if not (u.is_superuser or (hasattr(u, "has_perm_code") and (u.has_perm_code("warehouse.view.all") or u.has_perm_code("roles.manage") or u.has_perm_code("warehouse.view")))):
        return Response({"detail": "Немає доступу"}, status=403)
    qs = WarehouseJob.objects.select_related("deal", "deal__contact", "deal__stage", "assignee")
    frm = (request.GET.get("from") or "").strip()
    to = (request.GET.get("to") or "").strip()
    if frm:
        qs = qs.filter(created_at__date__gte=frm)
    if to:
        qs = qs.filter(created_at__date__lte=to)
    emp = (request.GET.get("employee") or "").strip()
    if emp.isdigit():
        qs = qs.filter(assignee_id=int(emp))
    q = (request.GET.get("q") or "").strip()
    if q:
        cond = (_Qh(deal__contact__first_name__icontains=q) | _Qh(deal__contact__last_name__icontains=q)
                | _Qh(deal__title__icontains=q) | _Qh(np_ttn__icontains=q))
        _num = q.replace("#", "").strip()
        if _num.isdigit():
            cond |= _Qh(deal_id=int(_num))
        qs = qs.filter(cond)
    qs = qs.order_by("-created_at")[:200]
    rows = []
    for j in qs:
        d = _job_dict(j)
        d["taken_at"] = j.taken_at.isoformat() if j.taken_at else None
        d["shipped_at"] = j.shipped_at.isoformat() if j.shipped_at else None
        rows.append(d)
    return Response({"rows": rows, "count": len(rows)})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def reassign(request, pk):
    """Змінити відповідального за задачу складу. GET → список складських співробітників.
    POST {user_id} (0 = зняти виконавця, задача повертається у чергу). Право: керівник."""
    from django.contrib.auth import get_user_model
    u = request.user
    is_mgr = bool(u.is_superuser or (hasattr(u, "has_perm_code") and (
        u.has_perm_code("warehouse.view.all") or u.has_perm_code("roles.manage") or u.has_perm_code("warehouse.reassign"))))
    if not is_mgr:
        return Response({"detail": "Потрібне право «Передавати задачі складу»"}, status=403)
    U = get_user_model()
    if request.method == "GET":
        pool = (U.objects.filter(is_active=True)
                .filter(department__name__icontains="Склад").order_by("first_name"))
        if not pool.exists():
            pool = U.objects.filter(is_active=True, is_superuser=False).order_by("first_name")[:30]
        return Response([{"id": x.id, "name": (x.get_full_name() or x.username)} for x in pool])
    with transaction.atomic():
        job = WarehouseJob.objects.select_for_update().filter(pk=pk).first()
        if not job:
            return Response({"detail": "no job"}, status=404)
        uid = int(request.data.get("user_id") or 0)
        old_name = job.assignee.get_full_name() if job.assignee_id else "—"
        if uid == 0:
            if job.status in ("shipped", "cancelled"):
                return Response({"detail": "Задача вже завершена — в чергу не повертається"}, status=400)
            job.assignee = None
            job.status = "queued"
            job.save(update_fields=["assignee", "status"])
            new_name = "черга"
        else:
            target = U.objects.filter(id=uid, is_active=True).first()
            if not target:
                return Response({"detail": "співробітника не знайдено"}, status=400)
            job.assignee = target
            if job.status == "queued":
                job.status = "taken"
                job.taken_at = timezone.now()
                job.save(update_fields=["assignee", "status", "taken_at"])
            else:
                job.save(update_fields=["assignee"])
            new_name = target.get_full_name() or target.username
        if job.task_id:
            job.task.assignee = job.assignee
            job.task.save(update_fields=["assignee"])
        # каскад на дозамовлення цієї посилки (той самий виконавець / у чергу)
        for _sub in WarehouseJob.objects.filter(deal__parent_deal_id=job.deal_id).exclude(status__in=["shipped", "cancelled"]):
            _sub.assignee = job.assignee
            if job.assignee_id is None:
                _sub.status = "queued"
            elif _sub.status == "queued":
                _sub.status = "taken"; _sub.taken_at = _sub.taken_at or timezone.now()
            _sub.save()
            if _sub.task_id:
                _sub.task.assignee = job.assignee; _sub.task.save(update_fields=["assignee"])
        try:
            from apps.crm.models import log_activity
            log_activity("deal", job.deal_id, "Склад: зміна виконавця", "%s → %s" % (old_name, new_name), u)
        except Exception:
            pass
    return Response(_job_dict(job, full=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def take(request, pk):
    with transaction.atomic():
        job = WarehouseJob.objects.select_for_update().filter(pk=pk).first()
        if not job:
            return Response({"detail": "no job"}, status=404)
        if job.assignee_id and job.assignee_id != request.user.id:
            return Response({"detail": "taken", "by": job.assignee.get_full_name()}, status=409)
        job.assignee = request.user; job.status = "taken"; job.taken_at = timezone.now()
        job.save(update_fields=["assignee", "status", "taken_at"])
        if job.task_id:
            job.task.status = "in_progress"; job.task.assignee = request.user
            job.task.save(update_fields=["status", "assignee"])
        # каскад: дозамовлення цієї посилки бере той самий складовщик (одна коробка)
        for _sub in WarehouseJob.objects.filter(deal__parent_deal_id=job.deal_id).exclude(status__in=["shipped", "cancelled"]):
            if not _sub.assignee_id:
                _sub.assignee = request.user; _sub.status = "taken"; _sub.taken_at = timezone.now()
                _sub.save(update_fields=["assignee", "status", "taken_at"])
                if _sub.task_id:
                    _sub.task.status = "in_progress"; _sub.task.assignee = request.user; _sub.task.save(update_fields=["status", "assignee"])
        # склад узяв замовлення в роботу → сделка йде у «Відвантаження» (за НАЗВОЮ стадії).
        # «Заброньовано» ставиться лише оплатою з типом «Бронь», склад його НЕ ставить.
        try:
            deal = job.deal
            st = (deal.stage.name if deal.stage_id else "").lower()
            if deal.stage_id and (("оплат" in st and "отриман" in st) or "заброньов" in st or "оплата/предоплата" in st):
                target = deal.funnel.stages.filter(name__icontains="відвантаж").order_by("order").first()
                if not target:
                    target = deal.funnel.stages.filter(name__icontains="в работе").order_by("order").first()
                if target and target.order > deal.stage.order:
                    from apps.crm.views import _advance_deal_stage
                    _advance_deal_stage(deal, target.order, "Склад узяв задачу в роботу (%s)" % (request.user.get_full_name() or request.user.username))
        except Exception:
            pass
    return Response(_job_dict(job, full=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def tinting(request, pk):
    job = WarehouseJob.objects.filter(pk=pk, assignee=request.user).first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    if job.status in ("shipped", "cancelled"):
        return Response({"detail": "Задача вже завершена"}, status=400)
    idx = request.data.get("kit")
    tinted = set(job.tinted_kits or [])
    if idx is not None:
        idx = int(idx)
        tinted.discard(idx) if idx in tinted else tinted.add(idx)
    job.tinted_kits = sorted(tinted)
    if job.status in ("taken",):
        job.status = "tinting"
    job.save(update_fields=["tinted_kits", "status"])
    return Response(_job_dict(job, full=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def packing(request, pk):
    job = WarehouseJob.objects.filter(pk=pk, assignee=request.user).first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    if job.status in ("shipped", "cancelled"):
        return Response({"detail": "Задача вже завершена"}, status=400)
    job.packed = bool(request.data.get("packed", True))
    job.status = "packing"
    try:
        if (job.deal.ttn or "").strip():
            kinds = set(p.kind for p in job.photos.all())
            if not (set(_required_photo_kinds(job)) <= kinds):
                job.status = "awaiting_photos"
    except Exception:
        pass
    job.save(update_fields=["packed", "status"])
    return Response(_job_dict(job, full=True))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def photo(request, pk):
    if request.method == "GET":
        job = WarehouseJob.objects.filter(pk=pk).first()
        if not job:
            return Response({"detail": "no job"}, status=404)
        pid = request.GET.get("id")
        if pid:
            p = job.photos.filter(id=pid).first()  # конкретне фото за id (щоб різні фото не показувались однаково)
        else:
            kind = request.GET.get("kind") or "buckets"
            p = job.photos.filter(kind=kind).order_by("-id").first()
        if not p or not p.image:
            return Response({"detail": "no photo"}, status=404)
        from django.http import HttpResponse
        import mimetypes
        try:
            data = p.image.read()
        except Exception:
            return Response({"detail": "file missing"}, status=404)
        ct = mimetypes.guess_type(p.image.name)[0] or "image/jpeg"
        return HttpResponse(data, content_type=ct)
    job = WarehouseJob.objects.filter(pk=pk, assignee=request.user).first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    f = request.FILES.get("image") or request.FILES.get("file")
    if not f:
        return Response({"detail": "no image"}, status=400)
    kind = request.GET.get("kind") or request.data.get("kind") or "buckets"
    WarehousePhoto.objects.create(job=job, deal=job.deal, employee=request.user, kind=kind, image=f)
    return Response({"ok": True, "photos": [{"id": p.id, "kind": p.kind} for p in job.photos.all()]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ship(request, pk):
    job = WarehouseJob.objects.filter(pk=pk, assignee=request.user).first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    if job.status == "shipped":
        # ідемпотентно: повторний клік/запит НЕ нараховує ЗП вдруге
        return Response(_job_dict(job, full=True))
    kinds = set(p.kind for p in job.photos.all())
    missing = [k for k in _required_photo_kinds(job) if k not in kinds]
    if missing:
        job.status = "awaiting_photos"; job.save(update_fields=["status"])
        return Response({"detail": "Не вистачає фото: " + ", ".join(PHOTO_LABEL.get(k, k) for k in missing)}, status=400)
    _finalize(job, request.user)
    if _is_pickup(job):
        _close_pickup_deal(job.deal, request.user)   # видали в салоні → сделка закрита, НП не чекаємо
    # каскад: дозамовлення цієї посилки — та сама коробка → списання без подвійної упаковки/фото
    for _sub in WarehouseJob.objects.filter(deal__parent_deal_id=job.deal_id).exclude(status__in=["shipped", "cancelled"]):
        try:
            _finalize(_sub, request.user, pay_packing=False)
        except Exception:
            pass
    out = _job_dict(job, full=True)
    # 14.09 (wh-accrual): що нараховано за це відвантаження (лише своє — «Відправлено» тисне тільки виконавець)
    out["accrued"] = [{"op": e.op_type, "label": e.get_op_type_display(), "amount": str(e.amount), "note": e.note}
                      for e in WarehousePayrollEntry.objects.filter(job=job, employee=request.user).order_by("id")]
    return Response(out)


def _test_set_rate(rates=None):
    """Ставка «Оплата складу за збірку тестового набору» (Фінмодель, code=bundle_assembly) — ЖИВЕ значення:
    Олег змінює суму у Фінмоделі → наступні відвантаження рахуються по новій (старі записи не змінюються).
    Та сама стаття вже входить у собівартість набору, тому «Економіка угоди» її окремо НЕ додає.
    Статтю вимкнено або її немає → 0 (не нараховуємо). Лише читання.
    15.09.2026 (whpay): той самий хелпер живих ставок, що й для ваги, упаковки, тонування і дня."""
    return _rate("bundle_assembly", rates)


def _accrual_plan(job, pay_packing=True):
    """14.09 (wh-accrual): ЄДИНА формула нарахувань складу за відвантаження (без запису в БД).
    Повертає (rows, meta); rows = [(op_type, сума, поля запису)].
      вага        — кг × WH_RATE_KG (як і раніше);
      упаковка    — місця ≤5/≤10/≤20 кг × WH_PACK_* (як і раніше; лише ручне пакування основної посилки);
      тонування   — WH_TINT_PCT % від суми рядка «Послуга тонування» (позначка не потрібна); якщо такого
                    рядка немає — як раніше, за ручною позначкою наборів. Обидва разом НІКОЛИ не рахуються;
      тест-набори — ставка bundle_assembly × кількість тестових наборів в угоді;
      викраски    — WH_SAMPLE_CAT / WH_SAMPLE_IND × кількість відправлених викрасок (17.09.2026)."""
    deal = job.deal
    salon = WR.is_salon(deal)
    # 23.09.2026: самовивіз не робить угоду салонною, але пакування теж не оплачується
    wp = WR.deal_plan(deal, salon=WR.no_packing(deal), packing=bool(job.packed and pay_packing))
    weight = wp["weight"]
    fx = _deal_accrual_facts(deal)
    kits = (deal.qualification or {}).get("kits", []) or []
    total_kits = len(kits); tinted = len(job.tinted_kits or [])
    if fx["tint_base"] > 0:
        tint_base = fx["tint_base"]; tint_source = "service_line"; tint_count = max(tinted, fx["tint_lines"])
    else:
        amount = deal.amount or Decimal("0")
        tint_base = (amount * Decimal(tinted) / Decimal(total_kits)) if total_kits else Decimal("0")
        tint_source = "manual" if tint_base > 0 else ""; tint_count = tinted
    tiers = wp["tiers"]  # 15.09.2026: місця за регламентом v2 (відра, розфасовка, тара, коробка дрібниць, посилка набору)
    _lr = live_rates()  # 15.09 (whpay): усі ставки одним запитом, лише з Фінмоделі (без чисел у коді)
    r_kg = _rate("WH_RATE_KG", _lr); r5 = _rate("WH_PACK_5", _lr); r10 = _rate("WH_PACK_10", _lr)
    r20 = _rate("WH_PACK_20", _lr); rtint = _rate("WH_TINT_PCT", _lr) / Decimal("100")
    rows = []
    if weight > 0:
        rows.append(("shipment_weight", weight * r_kg, {"quantity_kg": weight, "rate_applied": r_kg, "note": "%s кг" % WR._g(weight)}))
    for tier, cnt, rate in [("T5", tiers["T5"], r5), ("T10", tiers["T10"], r10), ("T20", tiers["T20"], r20)]:
        if cnt > 0:
            rows.append(("packing", rate * cnt, {"pack_tier": tier, "rate_applied": rate, "note": "%d шт" % cnt}))
    if tint_base > 0:
        tb = tint_base.quantize(Decimal("0.01"))
        note = ("Послуга тонування: %s ₴" % tb) if tint_source == "service_line" else ("позначка: %d з %d наборів" % (tinted, total_kits))
        rows.append(("tinting", tint_base * rtint, {"base_value": tb, "rate_applied": rtint, "note": note}))
    if fx["test_sets"] > 0:
        r_ts = _test_set_rate(_lr)
        if r_ts > 0:
            rows.append(("test_set", r_ts * fx["test_sets"],
                         {"rate_applied": r_ts, "note": "%s шт × %s ₴" % (_num(fx["test_sets"]), _num(r_ts))}))
    # 16.09.2026 (Олег): тонування тест-набору — фіксована сума за набір, окремо каталог і індивідуальний колір
    for code, cnt, op, label in (("WH_KIT_TINT_CAT", fx.get("kit_cat", 0), "kit_tint_cat", "колір з каталогу"),
                                 ("WH_KIT_TINT_IND", fx.get("kit_ind", 0), "kit_tint_ind", "індивідуальний колір")):
        if cnt and cnt > 0:
            r_kt = _rate(code, _lr)
            if r_kt > 0:
                rows.append((op, r_kt * cnt,
                             {"rate_applied": r_kt, "note": "%s наб. × %s ₴ (%s)" % (_num(cnt), _num(r_kt), label)}))
    for code, cnt, label in (("WH_SAMPLE_CAT", fx.get("sample_cat", 0), "колір з каталогу"),
                             ("WH_SAMPLE_IND", fx.get("sample_ind", 0), "індивідуальний колір")):
        if cnt and cnt > 0:
            r_s = _rate(code, _lr)
            if r_s > 0:
                rows.append(("samples", r_s * cnt,
                             {"rate_applied": r_s, "note": "%s викр. × %s ₴ (%s)" % (_num(cnt), _num(r_s), label)}))
    # 19.09.2026 (Олег): «кожне тонування і кожен тестовий набір з тонуванням вписувати в кількість тонувань»
    tint_count = int(tint_count) + int(fx.get("kit_cat", 0) or 0) + int(fx.get("kit_ind", 0) or 0)
    meta = {"weight": weight, "tiers": tiers, "tint_base": tint_base, "tint_source": tint_source,
            "tint_count": tint_count, "test_sets": fx["test_sets"], "weightless": fx["weightless"],
            "kit_cat": fx.get("kit_cat", 0), "kit_ind": fx.get("kit_ind", 0),
            "sample_cat": fx.get("sample_cat", 0), "sample_ind": fx.get("sample_ind", 0),
            "how": wp["how"], "salon": salon}
    return rows, meta


def _close_pickup_deal(deal, user):
    """23.09.2026 (Олег): «склад закрив задачу, додав документи — сделка теж вважається закритою».
    Самовивіз: ТТН і статусів Нової пошти не буде, тому одразу ставимо виграшну стадію воронки."""
    from apps.crm.models import Stage, log_activity
    try:
        if not deal.funnel_id or (deal.stage_id and (deal.stage.is_won or deal.stage.is_lost)):
            return
        st = Stage.objects.filter(funnel_id=deal.funnel_id, is_won=True).order_by("order").first()
        if not st:
            return
        old = deal.stage.name if deal.stage_id else "—"
        deal.stage = st
        deal.save(update_fields=["stage"])
        log_activity("deal", deal.id, "Видано в салоні",
                     "%s → %s (самовивіз, Новою поштою не відправляємо)" % (old, st.name), user,
                     (user.get_full_name() or user.username) if user else "Склад")
    except Exception:
        pass


def _finalize(job, user, pay_packing=True):
    today = timezone.now().date(); deal = job.deal
    rows, meta = _accrual_plan(job, pay_packing)  # 14.09 (wh-accrual): одна формула для запису і перегляду
    weight = meta["weight"]; tiers = meta["tiers"]
    job.shipped_weight_kg = weight
    job.tintings_count = meta["tint_count"]
    job.tintings_base = meta["tint_base"].quantize(Decimal("0.01"))
    job.pack_le5_count = tiers["T5"]; job.pack_le10_count = tiers["T10"]; job.pack_le20_count = tiers["T20"]
    for op, amt, kw in rows:
        WarehousePayrollEntry.objects.create(employee=user, work_date=today, job=job, deal=deal,
                                             op_type=op, amount=amt.quantize(Decimal("0.01")), **kw)
    job.done_snapshot = {"required_photos": _required_photo_kinds(job),
                         "weight": str(weight), "tiers": tiers, "tint_base": str(job.tintings_base),
                         "tint_source": meta["tint_source"], "test_sets": str(meta["test_sets"]),
                         "weightless": [w["product_id"] for w in meta["weightless"]],
                         "rule": "v2", "how": meta.get("how", [])[:40]}
    job.status = "shipped"; job.shipped_at = timezone.now(); job.save()
    from .services import realize_deal
    realize_deal(deal, user)  # спільне списання по собівартості + COGS, ідемпотентно (без подвійного списання)
    try:
        from .tare_samples import apply_washed_on_ship  # 16.09.2026: мите відро замість нового + оплата складу
        apply_washed_on_ship(job, user)
    except Exception:
        pass
    if job.task_id:
        job.task.status = "done"; job.task.save(update_fields=["status"])
    return job


_FAR = datetime.date(2100, 1, 1)  # «без верхньої межі» для режиму «останні N днів»


def _req_range(request):
    """15.09 (wh-day): період звітів складу. ?date=РРРР-ММ-ДД — один день; ?from=&to= — свій проміжок;
    інакше ?period=week|month|quarter|all — «останні N днів», як було (без верхньої межі).
    Повертає (з, по або None, period, підпис)."""
    def _d(s):
        try:
            return datetime.date.fromisoformat((s or "").strip()[:10])
        except ValueError:
            return None
    day = _d(request.GET.get("date"))
    if day:
        return day, day, "day", day.strftime("%d.%m.%Y")
    d1, d2 = _d(request.GET.get("from")), _d(request.GET.get("to"))
    if d1 or d2:
        d1, d2 = d1 or d2, d2 or timezone.localdate()
        if d1 > d2:
            d1, d2 = d2, d1
        return d1, d2, "range", "%s — %s" % (d1.strftime("%d.%m.%Y"), d2.strftime("%d.%m.%Y"))
    period = request.GET.get("period", "month")
    days = {"week": 7, "month": 30, "quarter": 90, "all": 3650}.get(period, 30)
    return timezone.now().date() - datetime.timedelta(days=days), None, period, ""


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_salary(request):
    period = request.GET.get("period", "month")
    if period == "calendar":
        return _my_calendar_month(request)  # 14.09 (wh-accrual): календарний місяць (поточний / попередній)
    since, until, period, label = _req_range(request)  # 15.09 (wh-day): один день / свій проміжок / останні N днів
    qs = WarehousePayrollEntry.objects.filter(employee=request.user, work_date__gte=since, work_date__lte=until or _FAR, status="confirmed")
    total = qs.aggregate(s=Sum("amount"))["s"] or 0
    # 17.09.2026 (Олег: на 17.09 рядки давали 204,68 з 404,68): список типів був старий — без тонування наборів,
    # мийки відер і викрасок. Тепер ті самі типи й назви, що в місяці (PIECE_OPS), решта — «Інше».
    lines = _piece_lines(qs)
    shipments = WarehouseJob.objects.filter(assignee=request.user, status="shipped", shipped_at__date__gte=since, shipped_at__date__lte=until or _FAR).count()
    tintings = qs.filter(op_type="tinting").count()
    dg, dg_cut = _deal_groups_for(qs)
    day = kpi = None
    if period == "day":
        # 17.09.2026 (Олег): «за день із ставки скільки і за KPI теж немає пункту» — день = ставка за вихід + KPI + відрядно
        first = since.replace(day=1)
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        _sc, base_lines, _w, _t, _pis = _scheme_lines(request.user, "%04d-%02d" % (first.year, first.month))
        kpi = _kpi_info(request.user, first, last, base_lines)
        month_qs = WarehousePayrollEntry.objects.filter(employee=request.user, work_date__gte=first, work_date__lte=last, status="confirmed")
        day = next((x for x in _month_days(request.user, first, last, month_qs, base_lines, kpi) if x["date"] == since.isoformat()), None)
    return Response({"total": str(total), "lines": lines, "period": period, "label": label,
                     "day": day, "kpi": kpi,
                     "deal_groups": dg, "deal_groups_truncated": dg_cut,
                     "from": since.isoformat(), "to": (until or timezone.localdate()).isoformat(),
                     "shipments": shipments, "tintings": tintings,
                     "rates": rates_payload(request.user)})  # 15.09 (whpay): ставки зараз — з Фінмоделі


# ── 14.09.2026 (wh-accrual): ЗП складу за календарний місяць ──
MONTHS_UK = ["січень", "лютий", "березень", "квітень", "травень", "червень",
             "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"]
PIECE_OPS = [("workday", "Робочі дні (ставка за день)"), ("shipment_weight", "Вага відвантаження"),
             ("packing", "Упаковка"), ("tinting", "Тонування"), ("test_set", "Збірка тестових наборів"),
             ("bonus_initiative", "Бонус за ідеї"), ("bonus_cleanliness", "Бонус за чистоту"),
             ("error", "Утримання: помилки"), ("wrong_material", "Утримання: невірний матеріал"),
             # 17.09.2026 (Олег: «у ставці є пункт Інше — що це?»): це були тонування наборів — тепер окремими рядками
             ("kit_tint_cat", "Тонування тест-наборів (колір з каталогу)"),
             ("kit_tint_ind", "Тонування тест-наборів (індивідуальний колір)"),
             ("washed_bucket", "Мите відро"), ("samples", "Викраски")]
DEDUCTION_OPS = ("error", "wrong_material")
# Короткі назви для карток днів (17.09.2026: «у блоках по днях — кожен рядок, що і скільки пораховано»)
PIECE_SHORT = {"workday": "Робочий день", "shipment_weight": "Вага", "packing": "Упаковка", "tinting": "Тонування",
               "test_set": "Збірка наборів", "kit_tint_cat": "Тонування наборів (каталог)",
               "kit_tint_ind": "Тонування наборів (індивід.)", "washed_bucket": "Мите відро", "samples": "Викраски",
               "bonus_initiative": "Бонус за ідеї", "bonus_cleanliness": "Бонус за чистоту",
               "error": "Утримання: помилки", "wrong_material": "Утримання: матеріал"}


def _piece_lines(qs):
    """Відрядні рядки за типами (однакові для дня і місяця); невідомі типи — одним рядком «Інше»."""
    lines = []
    for op, label in PIECE_OPS:
        r = qs.filter(op_type=op).aggregate(s=Sum("amount"), n=Count("id"))
        if r["n"]:
            lines.append({"op": op, "label": label, "amount": str(r["s"] or 0), "count": r["n"],
                          "deduction": op in DEDUCTION_OPS})
    rest = qs.exclude(op_type__in=[op for op, _l in PIECE_OPS]).aggregate(s=Sum("amount"), n=Count("id"))
    if rest["n"]:
        lines.append({"op": "other", "label": "Інше", "amount": str(rest["s"] or 0), "count": rest["n"], "deduction": False})
    return lines


def _money(x):
    """8000 → «8 000», 363.64 → «363,64» (як у картках)."""
    x = round(float(x or 0), 2)
    s = ("{:,.2f}".format(x)).replace(",", " ").replace(".", ",")
    return s[:-3] if s.endswith(",00") else s


def _scheme_lines(u, period):
    """Рядки схеми ЗП за місяць (без відрядної частини — вона = записи складу). Лише читання engine.calc."""
    scheme, base_lines, warnings, total, piece_in_scheme = None, [], [], None, False
    try:
        from apps.payroll import engine
        res = engine.calc(u, period)
        sc = res.get("scheme")
        if sc:
            scheme = {"title": sc.get("title") or "", "position": sc.get("position") or ""}
            total = res.get("total")
        for ln in res.get("lines") or []:
            if ln.get("kind") == "piece_rate":
                piece_in_scheme = True  # = сума записів складу нижче; окремо не показуємо (без подвійного)
                continue
            base_lines.append({"title": ln.get("title") or "", "amount": ln.get("amount") or 0,
                               "detail": ln.get("detail") or "", "kind": ln.get("kind") or "", "basis": ln.get("basis"),
                               "rate": ln.get("rate") or ""})
        warnings = [w for w in (res.get("warnings") or []) if w]
    except Exception:
        warnings.append("Ставку зі схеми ЗП не вдалося прочитати — показано лише відрядні записи складу")
    return scheme, base_lines, warnings, total, piece_in_scheme


def _kpi_info(u, first, last, base_lines):
    """17.09.2026 (Олег: «за KPI теж немає пункту»). Стандарт складу (KPI) цього місяця:
    діє — сума рядка стандарту (максимум × оцінка); ще не діє — з якої дати, скільки максимум
    і скільки було б зараз за підказкою CRM (лише довідка, у суму не входить)."""
    std = [l for l in base_lines if l.get("kind") == "standard"]
    if std:
        amt = sum(float(l.get("amount") or 0) for l in std)
        mx = sum(float(l.get("basis") or 0) for l in std)
        return {"active": True, "title": std[0]["title"] or "Стандарт складу (KPI)", "amount": round(amt, 2), "max": mx,
                "note": "до %s ₴ × оцінка місяця %s" % (_money(mx), std[0].get("rate") or "")}
    from apps.payroll.models import PayComponent
    comp = (PayComponent.objects.filter(scheme__user=u, scheme__purpose="official", scheme__status="active", kind="standard",
                                        active=True, scheme__valid_from__gt=last)
            .select_related("scheme").order_by("scheme__valid_from").first())
    if not comp:
        return {"active": False, "title": "KPI (стандарт складу)", "amount": 0, "max": 0,
                "note": "у вашій схемі ЗП цього місяця KPI немає"}
    mx = float((comp.params or {}).get("max") or 0)
    info = {"active": False, "title": comp.title or "Стандарт складу (KPI)", "amount": 0, "max": mx,
            "from": comp.scheme.valid_from.isoformat(),
            "note": "з %s: до %s ₴ × оцінка місяця; у цьому місяці не нараховується" % (comp.scheme.valid_from.strftime("%d.%m.%Y"), _money(mx))}
    try:
        from apps.payroll.wh_kpi import suggest_wh_standard
        s = suggest_wh_standard(u, "%04d-%02d" % (first.year, first.month), comp)
        info["preview"] = "якби діяло зараз: %s з %s пунктів (%s%%) → %s ₴" % (
            s["good"], len(s["points"]), s["suggested_pct"], _money(mx * float(s["suggested_score"])))
    except Exception:
        pass
    return info


def _deal_groups_for(qs, limit=300):
    """15.09.2026 (Олег): «по яких угодах як нараховано» — та сама розбивка, що у ЗП/KPI → «Як прорахувалось» (одна функція)."""
    from apps.payroll.detail_views import _piece_deal_groups
    labels = dict(PIECE_OPS)
    labels.update({k: v for k, v in WarehousePayrollEntry.OP if k not in labels})
    entries = list(qs.select_related("deal", "deal__contact", "job", "job__deal", "job__deal__contact").order_by("work_date", "id"))
    groups = _piece_deal_groups(entries, labels)
    groups.reverse()  # свіжі зверху
    return groups[:limit], len(groups) > limit


DAY_STATUS_UK = {"worked": "вихід", "overtime": "вихід у вихідний", "dayoff": "вихідний", "sick": "лікарняний",
                 "vacation": "відпустка", "absent": "прогул"}


def _month_days(u, first, last, qs, base_lines, kpi=None):
    """17.09.2026 (Олег): «у блоці Ставка — по днях, з прокруткою». Кожен день місяця до сьогодні:
    табель, ставка за день (ставка за вихід ÷ робочі дні місяця — орієнтовно; точна сума за місяць — у рядку ставки,
    бо там норма і лишній день ×2), KPI за день (сума стандарту ÷ робочі дні, якщо діє), відрядно за день
    (записи складу) і скільки відправлено. lines — кожен рядок дня: що і скільки пораховано."""
    from collections import defaultdict
    from apps.finance.models import WorkDay
    from apps.payroll import engine as _eng
    try:
        norm = _eng.workdays(first, last) or 1
        basis = sum(float(l.get("basis") or 0) for l in base_lines if l.get("kind") == "base_by_days")
        daily = basis / norm
        kpi_daily = (float(kpi.get("amount") or 0) / norm) if (kpi and kpi.get("active")) else 0.0
        st = dict(WorkDay.objects.filter(user=u, date__gte=first, date__lte=last).values_list("date", "status"))
        per = defaultdict(list)
        for r in qs.values("work_date", "op_type").annotate(s=Sum("amount"), n=Count("id")):
            per[r["work_date"]].append((r["op_type"], float(r["s"] or 0), r["n"]))
        order = {op: i for i, (op, _l) in enumerate(PIECE_OPS)}
        ships = {r["d"]: r["n"] for r in WarehouseJob.objects.filter(assignee=u, status="shipped", shipped_at__date__gte=first,
                                                                     shipped_at__date__lte=last)
                 .annotate(d=models_TruncDate("shipped_at")).values("d").annotate(n=Count("id"))}
        out, d, end = [], first, min(last, timezone.localdate())
        while d <= end:
            s = st.get(d, "")
            worked = s in ("worked", "overtime")
            base = round(daily, 2) if worked else 0.0
            kd = round(kpi_daily, 2) if worked else 0.0
            rows = sorted(per.get(d, []), key=lambda x: order.get(x[0], 99))
            p = sum(x[1] for x in rows)
            if not basis:
                base_note = "ставки за вихід у схемі немає"
            elif worked:
                base_note = "%s ₴ ÷ %s роб. днів місяця" % (_money(basis), norm)
            else:
                base_note = "день не відмічено в табелі" if not s else "%s — ставка не нараховується" % DAY_STATUS_UK.get(s, s)
            lines = [{"op": "base", "label": "Ставка за вихід", "amount": base, "note": base_note}]
            if kpi and (kpi.get("active") or kpi.get("max")):
                lines.append({"op": "kpi", "label": "KPI (стандарт)", "amount": kd,
                              "note": ("%s ₴ за місяць ÷ %s роб. днів" % (_money(kpi.get("amount")), norm)) if kpi.get("active")
                              else ("з %s" % datetime.date.fromisoformat(kpi["from"]).strftime("%d.%m") if kpi.get("from") else kpi.get("note", ""))})
            for op, amt, n in rows:
                lines.append({"op": op, "label": PIECE_SHORT.get(op, "Інше"), "full_label": dict(PIECE_OPS).get(op, "Інше"),
                              "amount": round(amt, 2), "count": n, "deduction": op in DEDUCTION_OPS})
            out.append({"date": d.isoformat(), "weekday": d.weekday(), "status": s, "status_label": DAY_STATUS_UK.get(s, "не відмічено"),
                        "base": base, "kpi": kd, "piece": round(p, 2), "entries": sum(x[2] for x in rows),
                        "shipments": ships.get(d, 0), "total": round(base + kd + p, 2), "lines": lines})
            d += datetime.timedelta(days=1)
        return out
    except Exception:
        return []


def models_TruncDate(field):
    from django.db.models.functions import TruncDate
    return TruncDate(field)


def _my_calendar_month(request):
    """ЗП за КАЛЕНДАРНИЙ місяць (which=current|prev) — ТІЛЬКИ свої дані (request.user; параметр людини
    не приймається). Ставка — з модуля «Ставки співробітників» (apps.payroll.engine.calc, лише читання);
    відрядно — записи складу за типами. «Разом» = як рахує модуль ЗП (якщо схеми немає — лише відрядні)."""
    u = request.user
    which = (request.GET.get("which") or "current").strip()
    if which not in ("current", "prev"):
        return Response({"detail": "Доступні лише поточний і попередній місяць"}, status=400)
    first = timezone.localdate().replace(day=1)
    if which == "prev":
        first = (first - datetime.timedelta(days=1)).replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    period = "%04d-%02d" % (first.year, first.month)
    qs = WarehousePayrollEntry.objects.filter(employee=u, work_date__gte=first, work_date__lte=last, status="confirmed")
    piece = _piece_lines(qs)
    piece_total = qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    scheme, base_lines, warnings, total, piece_in_scheme = _scheme_lines(u, period)
    if scheme and not piece_in_scheme and piece:
        warnings.append("У вашій схемі ЗП немає відрядної частини — записи складу показано довідково, у «Разом» не входять")
    if total is None:
        total = float(piece_total)
    elif piece_in_scheme:
        # 15.09.2026: «Разом» = рядки ставки + відрядно з копійками — щоб сума сходилась з рядками нижче
        total = round(sum(float(l["amount"] or 0) for l in base_lines) + float(piece_total), 2)
    dg, dg_cut = _deal_groups_for(qs)
    shipments = WarehouseJob.objects.filter(assignee=u, status="shipped", shipped_at__date__gte=first,
                                            shipped_at__date__lte=last).count()
    kpi = _kpi_info(u, first, last, base_lines)  # 17.09.2026: пункт KPI — і коли вже діє, і коли почнеться
    days = _month_days(u, first, last, qs, base_lines, kpi)
    return Response({"which": which, "period": period, "label": "%s %d" % (MONTHS_UK[first.month - 1], first.year), "days": days,
                     "kpi": kpi,
                     "from": first.isoformat(), "to": last.isoformat(), "scheme": scheme,
                     "base_lines": base_lines, "base_total": sum(float(l["amount"] or 0) for l in base_lines),
                     "piece": piece, "piece_total": str(piece_total), "piece_in_scheme": piece_in_scheme,
                     "total": total, "warnings": warnings, "shipments": shipments,
                     "deal_groups": dg, "deal_groups_truncated": dg_cut,
                     "rates": rates_payload(u)})  # 15.09 (whpay)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_shift(request):
    from apps.finance.models import WorkDay, WorkSession
    today = timezone.now().date()
    wd = WorkDay.objects.filter(user=request.user, date=today).first()
    sess = WorkSession.objects.filter(user=request.user, ended_at__isnull=True).order_by("-started_at").first()
    earned = WarehousePayrollEntry.objects.filter(employee=request.user, work_date=today, status="confirmed").aggregate(s=Sum("amount"))["s"] or 0
    lunch_min = (sess.paused_seconds // 60) if sess else 0
    return Response({"day_open": bool(sess), "earned_today": str(earned),
                     "lunch_min": lunch_min, "on_lunch": bool(sess and sess.paused_at),
                     "lunch_norm": LUNCH_NORM_MIN, "cleanliness_note": (wd.note if wd else "")})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def day_start(request):
    from apps.finance.models import WorkDay, WorkSession
    today = timezone.now().date()
    WorkDay.objects.get_or_create(user=request.user, date=today, defaults={"status": "worked"})
    if not WorkSession.objects.filter(user=request.user, ended_at__isnull=True).exists():
        WorkSession.objects.create(user=request.user)
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def day_close(request):
    from apps.finance.models import WorkSession, WorkDay
    today = timezone.now().date()
    sess = WorkSession.objects.filter(user=request.user, ended_at__isnull=True).order_by("-started_at").first()
    if sess:
        if sess.paused_at:
            sess.paused_seconds += int((timezone.now() - sess.paused_at).total_seconds()); sess.paused_at = None
        sess.ended_at = timezone.now(); sess.save()
        lunch_min = sess.paused_seconds // 60
        excess = max(0, lunch_min - LUNCH_NORM_MIN)
        day_rate = _rate("WH_RATE_DAY")  # 15.09 (whpay): лише Фінмодель; статтю вимкнено → 0
        penalty = (Decimal(excess) / Decimal(60)) * (day_rate / Decimal(DAY_HOURS))
        day_pay = max(Decimal("0"), day_rate - penalty)
        note = "обід %d хв" % lunch_min + ((" (-%s за перебір)" % penalty.quantize(Decimal("0.01"))) if excess else "")
        if not WarehousePayrollEntry.objects.filter(employee=request.user, work_date=today, op_type="workday").exists():
            WarehousePayrollEntry.objects.create(employee=request.user, work_date=today, op_type="workday",
                                                 amount=day_pay.quantize(Decimal("0.01")), rate_applied=day_rate, note=note)
    clean = (request.data.get("note") or "")[:160]
    if clean:
        wd = WorkDay.objects.filter(user=request.user, date=today).first()
        if wd:
            wd.note = clean; wd.save(update_fields=["note"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def lunch_toggle(request):
    from apps.finance.models import WorkSession
    sess = WorkSession.objects.filter(user=request.user, ended_at__isnull=True).order_by("-started_at").first()
    if not sess:
        return Response({"detail": "Спершу почни день"}, status=400)
    if sess.paused_at:
        sess.paused_seconds += int((timezone.now() - sess.paused_at).total_seconds()); sess.paused_at = None
    else:
        sess.paused_at = timezone.now()
    sess.save(update_fields=["paused_seconds", "paused_at"])
    return Response({"on_lunch": bool(sess.paused_at), "lunch_min": sess.paused_seconds // 60})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tare_types(request):
    return Response([{"id": t.id, "name": t.name, "max_fill_kg": str(t.max_fill_kg)}
                     for t in TareType.objects.filter(active=True)])


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def errors(request):
    from .models import WarehouseError
    if request.method == "POST":
        src = request.data.get("source", "manual_staff")
        _kind = str(request.data.get("kind") or "other")
        if _kind not in dict(WarehouseError.KIND):
            _kind = "other"
        e = WarehouseError.objects.create(
            job_id=request.data.get("job") or None, deal_id=request.data.get("deal") or None,
            reported_by=request.user, source=src, kind=_kind,
            description=(request.data.get("description") or "")[:1000],
            deduction_uah=Decimal(str(request.data.get("deduction") or 0)),
            blamed_user_id=request.data.get("blamed") or (request.user.id if src == "manual_staff" else None))
        return Response({"ok": True, "id": e.id})
    # 19.09.2026: список з іменами й сумами утримань — лише керівнику; співробітник бачить свої
    u = request.user
    qs = WarehouseError.objects.select_related("blamed_user", "deal")
    if not (u.is_superuser or u.has_perm_code("roles.manage") or u.has_perm_code("warehouse.view.all")):
        from django.db.models import Q as _Qe
        qs = qs.filter(_Qe(blamed_user=u) | _Qe(reported_by=u))
    if request.query_params.get("kinds"):
        return Response([{"code": c, "label": l} for c, l in WarehouseError.KIND])
    qs = qs[:100]
    return Response([{"id": e.id, "deal": e.deal_id, "kind": e.get_kind_display(),
                      "desc": e.description, "deduction": str(e.deduction_uah), "status": e.status,
                      "blamed": (e.blamed_user.get_full_name() if e.blamed_user_id else ""),
                      "source": e.source, "at": e.created_at.isoformat()} for e in qs])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_error(request, pk):
    u = request.user
    if not (u.is_superuser or u.has_perm_code("roles.manage") or u.has_perm_code("warehouse.view.all")):
        return Response({"detail": "Підтверджувати помилки/утримання може лише керівник складу або адмін"}, status=403)
    from .models import WarehouseError
    e = WarehouseError.objects.filter(pk=pk).first()
    if not e:
        return Response({"detail": "no"}, status=404)
    if request.data.get("action") == "reject":
        e.status = "rejected"; e.save(update_fields=["status"]); return Response({"ok": True})
    if request.data.get("deduction") is not None:
        e.deduction_uah = Decimal(str(request.data.get("deduction")))
    e.status = "confirmed"; e.confirmed_by = request.user; e.confirmed_at = timezone.now(); e.save()
    if e.blamed_user_id and e.deduction_uah > 0:
        WarehousePayrollEntry.objects.create(
            employee_id=e.blamed_user_id, work_date=timezone.now().date(), deal_id=e.deal_id,
            op_type=("wrong_material" if e.kind == "wrong_material" else "error"),
            amount=-e.deduction_uah, status="confirmed", source="manual", note=e.get_kind_display())
    return Response({"ok": True})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def ideas(request):
    from .models import InitiativeIdea
    if request.method == "POST":
        i = InitiativeIdea.objects.create(author=request.user, text=(request.data.get("text") or "")[:2000])
        return Response({"ok": True, "id": i.id})
    return Response([{"id": i.id, "author": i.author.get_full_name(), "text": i.text,
                      "status": i.status, "award": str(i.award_uah), "at": i.created_at.isoformat()}
                     for i in InitiativeIdea.objects.select_related("author")[:100]])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def award_idea(request, pk):
    u = request.user
    if not (u.is_superuser or u.has_perm_code("roles.manage") or u.has_perm_code("warehouse.view.all")):
        return Response({"detail": "Нараховувати премії за ідеї може лише керівник складу або адмін"}, status=403)
    from .models import InitiativeIdea
    i = InitiativeIdea.objects.filter(pk=pk).first()
    if not i:
        return Response({"detail": "no"}, status=404)
    i.status = request.data.get("status", "accepted")
    award = Decimal(str(request.data.get("award") or 0))
    if award > 0 and i.award_uah == 0:
        i.award_uah = award; i.awarded_by = request.user
        WarehousePayrollEntry.objects.create(employee=i.author, work_date=timezone.now().date(),
                                             op_type="bonus_initiative", amount=award, status="confirmed",
                                             source="manual", note="Ідея")
    i.save()
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    """Зведення складу для керівника: по співробітниках + команда + онлайн/офлайн + період."""
    from django.contrib.auth import get_user_model
    from .models import StockMovement
    from django.db.models import Sum
    since, until, period, label = _req_range(request)  # 15.09 (wh-day): один день / свій проміжок / останні N днів
    until_q = until or _FAR
    U = get_user_model()
    emp_ids = set(WarehousePayrollEntry.objects.filter(work_date__gte=since, work_date__lte=until_q).values_list("employee_id", flat=True))
    emp_ids |= set(WarehouseJob.objects.filter(status="shipped", shipped_at__date__gte=since, shipped_at__date__lte=until_q, assignee__isnull=False).values_list("assignee_id", flat=True))
    OPS = ["workday", "shipment_weight", "packing", "tinting", "test_set", "kit_tint_cat", "kit_tint_ind",
           "washed_bucket", "samples", "bonus_initiative", "error", "wrong_material"]
    rows = []
    for uid in emp_ids:
        u = U.objects.filter(id=uid).first()
        if not u:
            continue
        pe = WarehousePayrollEntry.objects.filter(employee_id=uid, work_date__gte=since, work_date__lte=until_q, status="confirmed")
        total = pe.aggregate(s=Sum("amount"))["s"] or 0
        by = {op: float(pe.filter(op_type=op).aggregate(s=Sum("amount"))["s"] or 0) for op in OPS}
        ship = WarehouseJob.objects.filter(assignee_id=uid, status="shipped", shipped_at__date__gte=since, shipped_at__date__lte=until_q)
        # 16.09.2026 (Олег): звіт для власника — скільки чого відвантажено і скільки за це нараховано
        def _cnt(op):
            n = Decimal("0")
            for e in pe.filter(op_type=op):
                if e.rate_applied:
                    n += (e.amount or 0) / e.rate_applied
            return int(round(float(n)))
        ship_l = list(ship.select_related("deal__funnel"))
        n_test = sum(1 for j in ship_l if j.deal and j.deal.funnel_id and "тест" in (j.deal.funnel.name or "").lower())
        detail = {"test_orders": n_test, "main_orders": len(ship_l) - n_test,
                  "pack": {"T5": sum(j.pack_le5_count or 0 for j in ship_l), "T10": sum(j.pack_le10_count or 0 for j in ship_l),
                           "T20": sum(j.pack_le20_count or 0 for j in ship_l)},
                  "packed_manual": sum(1 for j in ship_l if j.packed), "np_container": sum(1 for j in ship_l if not j.packed),
                  "tint_service": int(sum(j.tintings_count or 0 for j in ship_l)),
                  "tint_base": float(sum((j.tintings_base or 0) for j in ship_l)),
                  "test_sets": _cnt("test_set"), "kit_tint_cat": _cnt("kit_tint_cat"), "kit_tint_ind": _cnt("kit_tint_ind"),
                  "washed_shipped": int(sum(sum(int(v) for v in ((j.done_snapshot or {}).get("washed_applied") or {}).values()) for j in ship_l)),
                  "washed_made": int(sum(float(m.quantity) for m in StockMovement.objects.filter(
                      document__kind="repack", document__number__startswith="МВ-", document__author_id=uid, quantity__gt=0,
                      document__created_at__date__gte=since, document__created_at__date__lte=until_q))),
                  "sample_sheets": _cnt("samples")}
        rows.append({"id": uid, "name": u.get_full_name() or u.username,
                     "shipments": ship.count(),
                     "weight": float(ship.aggregate(s=Sum("shipped_weight_kg"))["s"] or 0),
                     "tintings": int(sum(j.tintings_count for j in ship)),
                     "deductions": float(by["error"] + by["wrong_material"]),
                     "total": float(total), "by": by, "detail": detail})
    rows.sort(key=lambda r: -r["total"])
    team = {"total": round(sum(r["total"] for r in rows), 2), "shipments": sum(r["shipments"] for r in rows),
            "weight": round(sum(r["weight"] for r in rows), 1), "tintings": sum(r["tintings"] for r in rows),
            "people": len(rows)}
    onoff = {"online": {"count": 0, "weight": 0.0, "value": 0.0}, "offline": {"count": 0, "weight": 0.0, "value": 0.0}}
    for j in WarehouseJob.objects.filter(status="shipped", shipped_at__date__gte=since, shipped_at__date__lte=until_q).select_related("deal", "deal__funnel"):
        fn = (j.deal.funnel.name if (j.deal and j.deal.funnel_id) else "").lower()
        ch = "offline" if any(x in fn for x in ["салон", "покрыт", "покритт"]) else "online"
        onoff[ch]["count"] += 1
        onoff[ch]["weight"] += float(j.shipped_weight_kg or 0)
        onoff[ch]["value"] += float(j.deal.amount or 0) if j.deal else 0
    # 16.09.2026 (Олег): кожне відвантаження періоду з фото (накладна, коробка, архів тонування) і що бракує
    shipments = []
    jobs = (WarehouseJob.objects.filter(status="shipped", shipped_at__date__gte=since, shipped_at__date__lte=until_q)
            .select_related("deal", "deal__funnel", "assignee").prefetch_related("photos").order_by("-shipped_at")[:300])
    for j in jobs:
        have = {p.kind for p in j.photos.all()}
        need = set((j.done_snapshot or {}).get("required_photos") or ["buckets", "parcel"])
        acc = WarehousePayrollEntry.objects.filter(job=j).aggregate(s=Sum("amount"))["s"] or 0
        fn = (j.deal.funnel.name if (j.deal and j.deal.funnel_id) else "") or ""
        shipments.append({
            "job": j.id, "deal": j.deal_id, "date": timezone.localtime(j.shipped_at).strftime("%d.%m %H:%M"),
            "employee": (j.assignee.get_full_name() or j.assignee.username) if j.assignee_id else "",
            "kind": "test" if "тест" in fn.lower() else "main", "weight": float(j.shipped_weight_kg or 0),
            "pack": {"T5": j.pack_le5_count or 0, "T10": j.pack_le10_count or 0, "T20": j.pack_le20_count or 0},
            "packed": bool(j.packed), "tint": j.tintings_count or 0, "accrued": float(acc),
            "photos": [{"id": p.id, "kind": p.kind, "label": PHOTO_LABEL.get(p.kind, p.kind),
                        "url": "/api/warehouse/jobs/%d/photo/?id=%d" % (j.id, p.id)} for p in j.photos.all()],
            "missing": [PHOTO_LABEL.get(k, k) for k in sorted(need - have)]})
    return Response({"period": period, "label": label, "from": since.isoformat(),
                     "to": (until or timezone.localdate()).isoformat(), "rows": rows, "team": team, "onoff": onoff, "ops": OPS,
                     "shipments": shipments,
                     "rates": rates_payload(request.user)})  # 15.09 (whpay)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_job(request, pk):
    """Видалити (скасувати) складську задачу — лише керівник складу/адмін. Soft: status=cancelled."""
    u = request.user
    is_mgr = bool(u.is_superuser or (hasattr(u, "has_perm_code") and (u.has_perm_code("warehouse.view.all") or u.has_perm_code("roles.manage"))))
    if not is_mgr:
        return Response({"detail": "Видаляти задачі може лише керівник складу"}, status=403)
    job = WarehouseJob.objects.filter(pk=pk).select_related("task").first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    job.status = "cancelled"
    job.save(update_fields=["status"])
    if job.task_id:
        try:
            job.task.status = "cancelled"; job.task.save(update_fields=["status"])
        except Exception:
            pass
    return Response({"ok": True})
