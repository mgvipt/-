"""Сервіси складу."""


def create_warehouse_job(deal):
    """Стадія «Оплату отримано» → задача в чергу складу + WarehouseJob. Ідемпотентно."""
    from .models import WarehouseJob
    from apps.crm.models import Task
    if WarehouseJob.objects.filter(deal=deal).exclude(status="cancelled").exists():
        return None
    title = "\u0412\u0456\u0434\u0432\u0430\u043d\u0442\u0430\u0436\u0438\u0442\u0438: %s" % (deal.title or ("#%s" % deal.id))
    task = Task.objects.create(kind="warehouse", deal=deal, title=title[:255], status="open", created_by_agent=True)
    return WarehouseJob.objects.create(task=task, deal=deal, is_shipment=True, status="queued")


def realize_deal(deal, user=None):
    """Реалізація (відвантаження) товарів угоди зі складу — РІВНО ОДИН РАЗ, по СОБІВАРТОСТІ, з COGS у фінанси.
    ІДЕМПОТЕНТНО: якщо по угоді вже є видатковий (out) документ — повертає його і повторно НЕ списує
    (захист від подвійного списання, коли спрацьовують і менеджерський «Відвантажити», і кладовщик «Готово»).
    Повертає (doc, cogs, created)."""
    from decimal import Decimal
    from .models import Warehouse, StockDocument, StockMovement
    existing = StockDocument.objects.filter(kind="out", deal=deal).first()
    if existing:
        return existing, Decimal("0"), False
    items = list(deal.items.select_related("product"))
    if not items:
        return None, Decimal("0"), False
    rows = _expand_deal_items(items)
    if not rows:
        # у сделці немає жодної складської позиції → НЕ створюємо порожню накладну
        # (інакше картка показує «реалізація проведена», а зі складу нічого не списано)
        return None, Decimal("0"), False
    wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
    doc = StockDocument.objects.create(kind="out", number="РН-%s" % deal.id, warehouse=wh, deal=deal,
                                       comment="Реалізація по угоді #%s" % deal.id, author=user,
                                       close_stage=(deal.stage.name if deal.stage_id else ""))
    cogs = Decimal("0")
    for prod, qty, cost in rows:
        StockMovement.objects.create(document=doc, product=prod, quantity=-qty, price=cost)
        cogs += qty * cost
    _on_posted(doc)  # єдина точка: COGS-витрата з тегом COGS doc#id
    return doc, cogs, True


def _expand_deal_items(items):
    """Розузлування: рядок сделки з НАБОРОМ розгортається у компоненти
    (списуються компоненти по їх собівартості), звичайний товар — як є.
    Повертає [(product, qty, cost), ...]."""
    from decimal import Decimal
    out = []
    for it in items:
        if not it.product_id:
            continue  # своя позиція (не з номенклатури) — складський рух не створюємо
        comps = list(it.product.components.select_related("component"))
        if comps:
            for row in comps:
                if not row.component.track_stock:
                    continue  # послуга/робота у складі набору — не списується
                out.append((row.component, it.quantity * row.quantity,
                            row.component.cost or Decimal("0")))
        else:
            if not it.product.track_stock:
                continue  # номенклатура без кількісного обліку — рух не створюємо
            out.append((it.product, it.quantity, it.product.cost or Decimal("0")))
    return out


def set_bundle_components(bundle, rows):
    """Замінити склад набору. rows=[{component: Product|id, quantity}]. Повертає (bundle, помилка|None).
    Правила: глибина 1 (компонент не набір; набір ні у кого не компонент), не сам у себе."""
    from decimal import Decimal
    from .models import Product, ProductComponent
    if bundle.used_in_bundles.exists() and rows:
        return bundle, "Цей товар сам є компонентом набору — вкладені набори заборонені."
    seen = set()
    clean = []
    for r in rows:
        comp = r["component"]
        if not isinstance(comp, Product):
            comp = Product.objects.get(id=comp)
        if comp.id == bundle.id:
            return bundle, "Набір не може містити сам себе."
        if comp.components.exists():
            return bundle, "«%s» сам є набором — вкладені набори заборонені." % comp.name
        if comp.id in seen:
            continue
        seen.add(comp.id)
        qty = Decimal(str(r.get("quantity") or 1))
        if qty <= 0:
            continue
        clean.append((comp, qty))
    bundle.components.all().delete()
    for comp, qty in clean:
        ProductComponent.objects.create(bundle=bundle, component=comp, quantity=qty)
    _recalc_one_bundle(bundle)  # Σ компонентів + збірка з фінмоделі
    return bundle, None


def _weighted_cost_update(doc):
    """Прихід: ковзна середньозважена собівартість.
    cost_new = (залишок_до × cost + к-сть × ціна_приходу) / (залишок_до + к-сть).
    Якщо залишок_до <= 0 або ціна приходу нульова — cost = ціна приходу (як є)."""
    from decimal import Decimal
    for m in doc.items.select_related("product"):
        price = m.price or Decimal("0")
        if price <= 0 or m.quantity <= 0:
            continue
        p = m.product
        stock_after = p.stock(doc.warehouse) if doc.warehouse_id else p.stock()
        stock_before = Decimal(stock_after) - m.quantity
        if stock_before <= 0:
            new_cost = price
        else:
            new_cost = ((stock_before * (p.cost or Decimal("0"))) + m.quantity * price) / (stock_before + m.quantity)
        new_cost = new_cost.quantize(Decimal("0.01"))
        if p.cost != new_cost:
            p.cost = new_cost
            p.save(update_fields=["cost"])
            recalc_bundle_costs(p)
            # оновити «закупку» позицій у ВІДКРИТИХ угодах з цим товаром (щоб деал показував актуальну собівартість
            # після приходу). Закриті (won/lost) угоди НЕ чіпаємо — там снапшот на момент продажу (історія).
            try:
                from apps.crm.models import DealItem
                from apps.warehouse.models import StockMovement
                DealItem.objects.filter(product=p, deal__stage__is_won=False, deal__stage__is_lost=False).update(cost=new_cost)
                # ДРОП-товар: закуповуємо ПІСЛЯ продажу — тому оновлюємо собівартість і в ЗАКРИТИХ (won) угодах,
                # і в русі товару (розхід), щоб приход «догнав» продаж. lost (програні) не чіпаємо.
                if getattr(p, "is_drop", False) and doc.deal_id:
                    # прихід зроблено ІЗ конкретної угоди (кнопка «Прихід» у картці сделки) — оновлюємо
                    # собівартість САМЕ цієї угоди (навіть закритої) + її рух розходу. Старі угоди не чіпаємо.
                    DealItem.objects.filter(product=p, deal_id=doc.deal_id).update(cost=new_cost)
                    StockMovement.objects.filter(product=p, quantity__lt=0, document__deal_id=doc.deal_id).update(price=new_cost)
            except Exception:
                pass


def bundle_assembly_fee():
    """Оплата роботи складу за збірку одного тестового набору — З ФІНМОДЕЛІ.
    Стаття FinModelArticle(code="bundle_assembly", категорія «Ставки складу»).
    Олег міняє суму у Фінанси → Налаштування фінмоделі → Склад/ставки — і собівартість
    усіх наборів перераховується автоматично (маржа та ЗП чесні)."""
    from decimal import Decimal
    try:
        from apps.finance.models import FinModelArticle
        art, _ = FinModelArticle.objects.get_or_create(
            code="bundle_assembly",
            defaults={"category": "warehouse_rate", "name": "Оплата складу за збірку тестового набору",
                      "value": 0, "value_type": "fixed_per_deal", "unit": "₴/набір"})
        if not art.active:
            return Decimal("0")
        return Decimal(art.value or 0)
    except Exception:
        return Decimal("0")


def recalc_all_bundle_costs():
    """Перерахувати собівартість УСІХ наборів (після зміни ставки збірки у фінмоделі)."""
    from .models import ProductComponent, Product
    ids = ProductComponent.objects.values_list("bundle_id", flat=True).distinct()
    n = 0
    for b in Product.objects.filter(id__in=list(ids)):
        _recalc_one_bundle(b)
        n += 1
    return n


def _recalc_one_bundle(bundle):
    from decimal import Decimal
    total = Decimal("0")
    rows = list(bundle.components.select_related("component"))
    for row in rows:
        total += (row.component.cost or Decimal("0")) * row.quantity
    if rows:
        total += bundle_assembly_fee()  # + робота складу за збірку (з фінмоделі)
    total = total.quantize(Decimal("0.01"))
    if bundle.cost != total:
        bundle.cost = total
        bundle.save(update_fields=["cost"])


def recalc_bundle_costs(component):
    """Перерахувати cost наборів, куди входить цей товар (якщо модель складу є)."""
    try:
        from .models import ProductComponent
    except ImportError:
        return
    for pc in ProductComponent.objects.filter(component=component).select_related("bundle"):
        _recalc_one_bundle(pc.bundle)


def _on_posted(doc):
    """Ефекти проведеного документа. МЕТОДОЛОГІЯ (як 1С, кассовий метод):
    касовий журнал (Transaction) = ТІЛЬКИ реальні гроші — оплата поставщику вноситься
    при закупівлі і вже є у журналі. Собівартість реалізації / списання / інвентаризація —
    це рух СКЛАДУ (StockDocument по собівартості), НЕ рух грошей: у журнал НЕ пишемо.
    Маржа/прибутковість рахується окремо: DealItem.cost (знімок) + складські документи."""
    if doc.kind == "in":
        _weighted_cost_update(doc)  # ковзна середньозважена собівартість


def _on_unposted(doc):
    """Скасування проведення — теж лише склад: рухи перестають рахуватись через posted=False.
    У грошах сторнувати нічого (їх і не було)."""
    return


def _doc_cogs(doc):
    """Собівартість документа = сума (кількість×ціна) по рядках (для out qty від'ємний → плюс)."""
    from decimal import Decimal
    total = Decimal("0")
    for m in doc.items.all():
        total += abs(m.quantity) * (m.price or 0)
    return total


def post_document(doc):
    """Провести документ: рухи знову рахуються у залишок; для реалізації по угоді — забронювати COGS."""
    if doc.posted:
        return False
    doc.posted = True
    doc.save(update_fields=["posted"])
    _on_posted(doc)
    return True


def unpost_document(doc):
    """Скасувати проведення: рухи перестають рахуватись (залишок повертається); COGS сторнується."""
    if not doc.posted:
        return False
    doc.posted = False
    doc.save(update_fields=["posted"])
    _on_unposted(doc)  # сторно COGS / списання / інвентаризації
    return True


def sync_job_status_after_ttn(deal):
    """ТТН створена → якщо задача взята/тонується/пакується і немає 2 фото —
    статус «Потрібні фото» (колонка «ТТН + Фото» у канбані складу). Ідемпотентно."""
    from .models import WarehouseJob
    job = (WarehouseJob.objects.filter(deal=deal)
           .filter(status__in=["taken", "tinting", "packing"]).first())
    if not job:
        return None
    kinds = set(p.kind for p in job.photos.all())
    if {"buckets", "parcel"} <= kinds:
        return None  # фото вже є — кладовщик сам натисне «Відвантажено»
    job.status = "awaiting_photos"
    job.save(update_fields=["status"])
    return job
