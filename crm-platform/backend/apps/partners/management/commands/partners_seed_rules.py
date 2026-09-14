"""Стартові знижки на ВЛАСНІ категорії WALLCOV (покриття, грунти, інструменти) — за правилом ATM.

«Старт» — числа Олега (покриття 15%, грунти 10%, інструменти 10%, налаштування start_fixed),
Партнер / Золото / Дилер — підказка ATM (медіана по товарах папки, вниз до 5%).
Чужі бренди, послуги, тест-набори — НЕ чіпаємо (чужі бренди — винятками по товару на екрані «Партнери»).

  python manage.py partners_seed_rules           # DRY-RUN: лише показує план
  python manage.py partners_seed_rules --apply   # записує правила папок (з історією), наявні правила НЕ перезаписує
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.partners.models import PartnerDiscountRule
from apps.partners.services import RuleBook, load_products, q2, stats_for, subtree_ids, tree_maps, upsert_rule
from apps.warehouse.models import ProductCategory


class Command(BaseCommand):
    help = "Партнери: стартові знижки на кореневі категорії WALLCOV (DRY-RUN за замовчуванням)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        book = RuleBook()
        if not book.start_fixed:
            self.stdout.write("Немає кореневих категорій у налаштуванні start_fixed — нічого робити")
            return
        children = tree_maps(book)
        products = load_products()
        by_cat = {}
        for p in products:
            by_cat.setdefault(p.category_id, []).append(p)
        self.stdout.write("Партнери: стартові знижки — %s" % ("LIVE" if apply else "DRY-RUN (нічого не пишу)"))
        plan = []
        for cat_id in book.start_fixed:
            cat = ProductCategory.objects.filter(pk=cat_id).first()
            if cat is None:
                continue
            sugg = book.category_suggestions(cat_id, by_cat, children)
            sub = [p for cid in subtree_ids(cat_id, children) for p in by_cat.get(cid, [])]
            self.stdout.write("\n%s (#%s), товарів у папці й підпапках: %s" % (cat.name, cat.id, len(sub)))
            over = {}
            for lv in book.levels:
                val, src = sugg[lv.id]
                existing = PartnerDiscountRule.objects.filter(level=lv, category=cat, product__isnull=True).first()
                if val is None:
                    self.stdout.write("  %-8s — немає собівартості, пропускаю" % lv.name)
                    continue
                over[(lv.id, cat_id)] = val
                preview = stats_for(book.copy_with(cat_over={(lv.id, cat_id): val}), sub, lv)
                note = "вже є %s%% — не чіпаю" % q2(existing.pct) if existing else "буде записано"
                self.stdout.write("  %-8s %5s%% (%s) · урізано маржею: %s · без собівартості: %s · мін. залишок %s п.п. · %s" % (
                    lv.name, q2(val), "Олег" if src == "oleg" else "ATM", preview["n_capped"], preview["n_no_cost"],
                    preview["min_left_pp"], note))
                if existing is None:
                    plan.append((lv, cat, val))
        if not apply:
            self.stdout.write("\nDRY-RUN: нічого не записано. Правил до запису: %s. Для запису: --apply" % len(plan))
            return
        with transaction.atomic():
            n = sum(1 for lv, cat, val in plan
                    if upsert_rule(lv, None, "seed", note="стартові знижки WALLCOV", category=cat, pct=val, suggested=val))
        self.stdout.write("\nЗаписано правил: %s" % n)
