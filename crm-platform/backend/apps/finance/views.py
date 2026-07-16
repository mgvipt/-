from datetime import date, timedelta
from django.db.models import Sum, Q, Count, Min, Max
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.common.permissions import HasPermCode
from .models import Account, Category, Transaction, FinModelArticle, FinDirection, ChannelSpend, FundAllocation, AdvisoryReport, TransactionAttachment, ManagerPlan, WorkDay, WorkSession
from .serializers import AccountSerializer, CategorySerializer, TransactionSerializer, FinModelArticleSerializer, FinDirectionSerializer, FundAllocationSerializer, AdvisoryReportSerializer
from .services import compute_pnl, compute_breakeven, compute_channels


class FinancePerm(HasPermCode):
    """Доступ к финансам только с правом finance.view."""
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.has_perm_code("finance.view")


class FinanceManagePerm(HasPermCode):
    """Редактирование финмодели — только с правом finance.manage."""
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.has_perm_code("finance.manage")


class FinDirectionPerm(HasPermCode):
    """Напрямки: ЧИТАТИ може кожен, хто працює з фінансами або створює дохід/витрату
    (finance.view АБО finance.tx.edit) — щоб напрямок було видно у випадаючих списках.
    Створення/редагування/видалення додатково закриті finance.dirs.manage у perform_*."""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        u = request.user
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return u.has_perm_code("finance.view") or u.has_perm_code("finance.tx.edit")
        return u.has_perm_code("finance.view")


class FinArticleReadPerm(HasPermCode):
    """Фонди (статті фінмоделі): ЧИТАТИ може кожен, хто працює з фінансами або створює
    дохід/витрату (finance.view АБО finance.tx.edit) — щоб фонд було видно у випадаючих
    списках картки операції. РЕДАГУВАННЯ фондів лишається під finance.manage (як було)."""
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        u = request.user
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return u.has_perm_code("finance.view") or u.has_perm_code("finance.tx.edit")
        return u.has_perm_code("finance.manage")


class FinModelArticleViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        _fin_guard(self.request, "finance.model.edit", "Фінмодель: лише перегляд (нема права редагувати)")
        serializer.save()

    def perform_update(self, serializer):
        _fin_guard(self.request, "finance.model.edit", "Фінмодель: лише перегляд (нема права редагувати)")
        serializer.save()

    def perform_destroy(self, instance):
        _fin_guard(self.request, "finance.model.edit", "Фінмодель: лише перегляд (нема права редагувати)")
        instance.delete()

    queryset = FinModelArticle.objects.all()
    serializer_class = FinModelArticleSerializer

    def perform_update(self, serializer):
        obj = serializer.save()
        if obj.code == "bundle_assembly":
            # ставка збірки набору змінилась → перерахувати собівартість усіх наборів
            try:
                from apps.warehouse.services import recalc_all_bundle_costs
                recalc_all_bundle_costs()
            except Exception:
                pass
    permission_classes = [FinArticleReadPerm]
    filterset_fields = ["category", "active"]


def _fin_guard(request, code, msg):
    u = request.user
    if not (u.is_superuser or u.has_perm_code(code)):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied(msg)


def _closed_until():
    """Дата закриття періоду (бухгалтерія). Операції до неї включно — не змінюються."""
    from apps.integrations.models import IntegrationSettings
    st = IntegrationSettings.objects.filter(provider="finance_lock").first()
    v = (st.config or {}).get("closed_until") if st else None
    if not v:
        return None
    from datetime import date as _d
    try:
        return _d.fromisoformat(str(v))
    except ValueError:
        return None


def _guard_period(request, tx_date):
    """Заборона правок у закритому періоді (крім права finance.period.close)."""
    cu = _closed_until()
    if cu and tx_date and tx_date <= cu:
        u = request.user
        if not (u.is_superuser or u.has_perm_code("finance.period.close")):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Період до %s закрито бухгалтерією — операції не змінюються" % cu.isoformat())


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_fin("fin_accounts")
        return qs if allowed is None else qs.filter(id__in=allowed)

    def perform_create(self, serializer):
        _fin_guard(self.request, "finance.accounts.manage", "Немає права редагувати рахунки")
        serializer.save()

    def perform_update(self, serializer):
        _fin_guard(self.request, "finance.accounts.manage", "Немає права редагувати рахунки")
        serializer.save()

    def perform_destroy(self, instance):
        _fin_guard(self.request, "finance.accounts.manage", "Немає права видаляти рахунки")
        instance.delete()
    serializer_class = AccountSerializer
    permission_classes = [FinancePerm]

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        """Зберегти порядок рахунків: {ids: [id, id, ...]} — позиція у списку = порядок."""
        ids = request.data.get("ids") or []
        for i, pk in enumerate(ids):
            Account.objects.filter(id=pk).update(sort_order=i * 10)
        return Response({"ok": True, "count": len(ids)})


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        a_in = u.allowed_fin("fin_cats_in")
        a_out = u.allowed_fin("fin_cats_out")
        from django.db.models import Q as _Q
        cond = _Q()
        if a_in is not None:
            cond &= (_Q(direction="out") | _Q(id__in=a_in))
        if a_out is not None:
            cond &= (_Q(direction="in") | _Q(id__in=a_out))
        return qs.filter(cond) if (a_in is not None or a_out is not None) else qs

    def perform_create(self, serializer):
        _fin_guard(self.request, "finance.ref.edit", "Немає права редагувати довідники")
        serializer.save()

    def perform_update(self, serializer):
        _fin_guard(self.request, "finance.ref.edit", "Немає права редагувати довідники")
        serializer.save()

    def perform_destroy(self, instance):
        _fin_guard(self.request, "finance.ref.edit", "Немає права редагувати довідники")
        instance.delete()
    serializer_class = CategorySerializer
    permission_classes = [FinancePerm]


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related("account", "category", "deal", "fin_direction", "fin_article")
    serializer_class = TransactionSerializer
    permission_classes = [FinancePerm]
    filterset_fields = ["direction", "account", "category", "deal", "fin_direction", "fin_article", "channel"]
    ordering = ["-date", "-op_time", "-id"]  # журнал завжди за датою і ЧАСОМ операції (нові зверху)
    from django_filters.rest_framework import DjangoFilterBackend as _DFB
    filter_backends = [_DFB]  # без OrderingFilter: сортування керує get_queryset (клік по стовпцях)

    def _apply_splits(self, tx, data):
        if "splits" not in data:
            return
        from apps.finance.models import TransactionSplit, Category, FinDirection
        from decimal import Decimal as _D
        splits = data.get("splits") or []
        rows = []
        for sp in splits:
            amt = sp.get("amount")
            if not amt:
                continue
            fd = FinDirection.objects.filter(pk=sp.get("fin_direction")).first() if sp.get("fin_direction") else None
            cat = None
            if sp.get("category"):
                cat = Category.objects.filter(pk=sp.get("category")).first()
            elif sp.get("set_category"):
                cat = Category.objects.filter(name=sp.get("set_category"), direction=tx.direction).first() or Category.objects.filter(name=sp.get("set_category")).first()
            rows.append((fd, cat, _D(str(amt))))
        if rows and abs(sum((r[2] for r in rows), _D("0")) - (tx.amount or _D("0"))) > _D("0.01"):
            from rest_framework.exceptions import ValidationError as _VE
            raise _VE({"splits": "Сума розподілу не дорівнює сумі операції."})
        TransactionSplit.objects.filter(transaction=tx).delete()
        for fd, cat, amt in rows:
            TransactionSplit.objects.create(transaction=tx, fin_direction=fd, category=cat, amount=amt)
        try:
            from apps.finance.services import sync_internal_debts
            sync_internal_debts(tx)
        except Exception:
            pass

    def perform_create(self, serializer):
        _fin_guard(self.request, "finance.tx.edit", "Журнал: лише перегляд — нема права створювати операції")
        _guard_period(self.request, serializer.validated_data.get("date"))
        serializer.save()
        self._apply_splits(serializer.instance, self.request.data)
        try:
            from apps.crm.views import sync_deal_payment_from_tx
            sync_deal_payment_from_tx(serializer.instance)
        except Exception:
            pass

    def perform_update(self, serializer):
        _fin_guard(self.request, "finance.tx.edit", "Журнал: лише перегляд — нема права редагувати операції")
        _guard_period(self.request, serializer.instance.date)
        nd = serializer.validated_data.get("date")
        if nd:
            _guard_period(self.request, nd)
        serializer.save()
        self._apply_splits(serializer.instance, self.request.data)
        try:
            from apps.crm.views import sync_deal_payment_from_tx
            sync_deal_payment_from_tx(serializer.instance)
        except Exception:
            pass

    def perform_destroy(self, instance):
        _fin_guard(self.request, "finance.tx.edit", "Журнал: лише перегляд — нема права видаляти операції")
        _guard_period(self.request, instance.date)
        # Якщо операція повʼязана з платежем угоди (crm.Payment) — видаляємо і його,
        # щоб у картці угоди не лишався «привид» платежу з бейджем після видалення з журналу.
        pay = getattr(instance, "payment", None)
        instance.delete()
        if pay is not None:
            try:
                pay.delete()
            except Exception:
                pass

    @action(detail=False, methods=["post"], url_path="bulk-edit")
    def bulk_edit(self, request):
        """Масова зміна поля у вибраних операціях: {ids: [...], set: {поле: значення}}."""
        _fin_guard(request, "finance.tx.edit", "Нема права редагувати операції")
        ids = request.data.get("ids") or []
        st = request.data.get("set") or {}
        ALLOWED = {"currency", "category", "counterparty", "account", "deal",
                   "fin_article", "fin_direction", "channel", "comment"}
        updates = {k: v for k, v in st.items() if k in ALLOWED}
        if not ids or not updates:
            return Response({"detail": "ids і set обовʼязкові"}, status=400)
        done = 0
        for t in Transaction.objects.filter(id__in=ids[:500]).select_related("category"):
            _guard_period(request, t.date)
            for k, v in updates.items():
                if k == "category":
                    t.category_id = int(v) if v else None
                    if v:
                        c = Category.objects.filter(id=v).select_related("parent").first()
                        if c:
                            fa = c.fin_article_id or (c.parent.fin_article_id if c.parent_id else None)
                            fd = c.fin_direction_id or (c.parent.fin_direction_id if c.parent_id else None)
                            if fa and "fin_article" not in updates:
                                t.fin_article_id = fa
                            if fd and "fin_direction" not in updates:
                                t.fin_direction_id = fd
                elif k == "account":
                    if v:
                        t.account_id = int(v)
                elif k == "deal":
                    t.deal_id = int(v) if v else None
                    if v:
                        from apps.crm.models import Deal as _Dbe
                        d = _Dbe.objects.filter(id=v).first()
                        if d and d.contact_id:
                            t.contact_id = d.contact_id
                elif k == "fin_article":
                    t.fin_article_id = int(v) if v else None
                elif k == "fin_direction":
                    t.fin_direction_id = int(v) if v else None
                else:
                    setattr(t, k, (v or "")[:255] if k == "comment" else (v or ""))
            t.save()
            done += 1
        return Response({"updated": done})

    @action(detail=False, methods=["post"], url_path="counterparty-rename")
    def counterparty_rename(self, request):
        """Перейменувати контрагента в УСІХ операціях (обʼєднання написань)."""
        _fin_guard(self.request, "finance.tx.edit", "Нема права редагувати операції")
        old_n = (request.data.get("old") or "").strip()
        new_n = (request.data.get("new") or "").strip()[:160]
        if not old_n or not new_n:
            return Response({"detail": "old і new обовʼязкові"}, status=400)
        n = Transaction.objects.filter(counterparty=old_n).update(counterparty=new_n)
        return Response({"updated": n})

    @action(detail=False, methods=["post"], url_path="counterparty-delete")
    def counterparty_delete(self, request):
        """Прибрати контрагента з усіх операцій (операції ЛИШАЮТЬСЯ, поле очищується)."""
        _fin_guard(self.request, "finance.tx.edit", "Нема права редагувати операції")
        old_n = (request.data.get("name") or "").strip()
        if not old_n:
            return Response({"detail": "name обовʼязковий"}, status=400)
        n = Transaction.objects.filter(counterparty=old_n).update(counterparty="")
        return Response({"updated": n})

    @action(detail=False, methods=["get"], url_path="triage")
    def triage(self, request):
        """Розноска «сміттєвих» категорій («Категории расходов/доходов»):
        кожна операція + пропозиція категорії (історія контрагента / коментар)."""
        import re as _re
        from collections import Counter, defaultdict
        trash = list(Category.objects.filter(name__in=["Категории расходов", "Категории доходов"]))
        from django.db.models import Q as _Qtr
        txs = list(Transaction.objects.filter(
                       _Qtr(category__in=trash) |
                       _Qtr(category__isnull=True, date__gte="2026-01-01"))
                   .exclude(direction="transfer")
                   .exclude(comment__icontains="ЗВІРКА")
                   .select_related("category", "account").order_by("-date")[:3000])
        hist = defaultdict(Counter)
        for cp, cid, cname, dr in (Transaction.objects.exclude(counterparty="").exclude(category__isnull=True)
                                   .exclude(category__in=trash)
                                   .values_list("counterparty", "category_id", "category__name", "direction")):
            if cname in ("Перевод", "Зарплата"):
                continue
            hist[(cp.lower(), dr)][(cid, cname)] += 1
        SEM_OUT = [
            (r"переказ власних кошт|перевод на свою карту|перевод на карту приватбанка|на картку", None),
            (r"#корректировка|корректировка после|корректировка полсле", "Корректировка(УДАЛИТЬ В P&L)"),
            (r"декоративн|штукатур|за декор|будматеріал|будматериал|древесина", "Закупка товара"),
            (r"нанесення декору|художник|#мастер", "ЗП мастерам (объекты/сверление)"),
            (r"кондиціонер|кондиционер|тельнюка|спортшкола", "Личные расходы (ЗП управления)"),
            (r"нова пошта|новапошта|доставк|перевезен", "Доставка / логистика"),
            (r"оренд|аренд", "Аренда салона"),
            (r"податок|єсв| есв", "Налоги"),
            (r"комісі|комиси|комiсi|еквайринг", "Комиссии банка и проценты"),
            (r"паливо|бензин|азс|wog|okko", "Транспорт (топливо, поездки)"),
            (r"зарплат|аванс", "ЗП оклады (офис/склад)"),
            (r"пополнение мобильного|поповнення мобільного", "Связь (интернет + телефония)"),
            (r"учеба|учоба|educationals", "Обучение"),
        ]
        SEM_IN = [
            (r"liqpay|лікпей|ликпей", "Онлайн (Instagram/TikTok/сайт)"),
            (r"за декор|декоративн|сплата за замовлення|оплата частинами|за замовлення", "Онлайн (Instagram/TikTok/сайт)"),
        ]
        name2 = {}
        for c in Category.objects.all():
            name2.setdefault((c.name, c.direction), c.id)
        OWNER = _re.compile(r"крижевск|кріжевськ|круликовск", _re.I)
        out = []
        for t in txs:
            cp = (t.counterparty or "").strip()
            osnd = (t.comment or "").lower()
            sug_id, sug_name, src, to_tr = None, "", "", False
            for pat, catname in (SEM_OUT if t.direction == "out" else SEM_IN):
                if _re.search(pat, osnd):
                    if catname is None:
                        to_tr, src, sug_name = True, "коментар", "→ Переказ"
                    else:
                        cid = name2.get((catname, t.direction))
                        if cid:
                            sug_id, sug_name, src = cid, catname, "коментар"
                    break
            if not sug_id and not to_tr and cp and t.direction == "out" and OWNER.search(cp):
                cid = name2.get(("Личные расходы (ЗП управления)", "out"))
                if cid:
                    sug_id, sug_name, src = cid, "Личные расходы (ЗП управления)", "власник"
            if not sug_id and not to_tr and cp:
                h = hist.get((cp.lower(), t.direction))
                if h:
                    (cid, cname), _n = h.most_common(1)[0]
                    sug_id, sug_name, src = cid, cname, "історія"
            out.append({"id": t.id, "date": t.date, "direction": t.direction,
                        "amount_uah": t.amount_uah, "counterparty": cp,
                        "comment": t.comment, "cat_now": t.category.name if t.category else "",
                        "suggest": sug_id, "suggest_name": sug_name,
                        "to_transfer": to_tr, "src": src})
        return Response(out)

    @action(detail=False, methods=["post"], url_path="triage-apply")
    def triage_apply(self, request):
        """Масове застосування розноски: items=[{id, category}|{id, to_transfer, transfer_account?}]."""
        _fin_guard(request, "finance.tx.edit", "Розноска: потрібне право «Редагувати операції журналу»")
        items = request.data.get("items") or []
        done = 0
        locked = 0
        for it in items:
            t = Transaction.objects.filter(id=it.get("id")).first()
            if not t:
                continue
            try:
                _guard_period(request, t.date)
            except Exception:
                locked += 1
                continue
            if it.get("to_transfer"):
                t.direction = "transfer"
                t.category = None
                t.fin_article = None
                t.fin_direction = None
                t.transfer_account_id = it.get("transfer_account") or None
                t.save()
                done += 1
                continue
            c = Category.objects.filter(id=it.get("category")).first()
            if not c:
                continue
            t.category = c
            fa = c.fin_article_id or (c.parent.fin_article_id if c.parent_id else None)
            fd = c.fin_direction_id or (c.parent.fin_direction_id if c.parent_id else None)
            if fa:
                t.fin_article_id = fa
            if fd:
                t.fin_direction_id = fd
            t.save()
            done += 1
        return Response({"updated": done, "locked_skipped": locked})

    @action(detail=False, methods=["get", "post"], url_path="period-lock")
    def period_lock(self, request):
        """Закриття періоду (бухгалтерія): до цієї дати включно операції не змінюються.
        POST {closed_until: YYYY-MM-DD | null} — потрібне право finance.period.close."""
        from apps.integrations.models import IntegrationSettings
        if request.method == "POST":
            _fin_guard(request, "finance.period.close", "Немає права закривати період")
            st, _ = IntegrationSettings.objects.get_or_create(provider="finance_lock", defaults={"config": {}})
            cfg = st.config or {}
            cfg["closed_until"] = request.data.get("closed_until") or None
            st.config = cfg
            st.is_active = True
            st.save()
        cu = _closed_until()
        return Response({"closed_until": cu.isoformat() if cu else None,
                         "can_close": request.user.is_superuser or request.user.has_perm_code("finance.period.close")})

    @action(detail=False, methods=["post"], url_path="privat-sync")
    def privat_sync(self, request):
        """Синк ПриватБанку: за N днів або за довільний період {from,to}."""
        u = request.user
        if not (u.is_superuser or u.has_perm_code("finance.manage")):
            return Response({"detail": "Потрібне право «Керування фінмоделлю»"}, status=403)
        d_from, d_to = request.data.get("from"), request.data.get("to")
        days = int(request.data.get("days") or 4)
        created, skipped, err, batch = privat_pull(days=min(days, 366), d_from=d_from, d_to=d_to, acc=request.data.get("acc"))
        if err:
            return Response({"detail": err}, status=400)
        return Response({"ok": True, "created": created, "skipped_existing": skipped, "batch": batch})

    @action(detail=False, methods=["post"], url_path="mono-sync")
    def mono_sync(self, request):
        u = request.user
        if not (u.is_superuser or u.has_perm_code("finance.manage")):
            return Response({"detail": "Потрібне право «Керування фінмоделлю»"}, status=403)
        created, skipped, err, batch = mono_pull(request.data.get("from"), request.data.get("to"), request.data.get("account"))
        if err:
            return Response({"detail": err}, status=400)
        return Response({"ok": True, "created": created, "skipped_existing": skipped, "batch": batch})

    @action(detail=False, methods=["get", "delete"], url_path="import-batches")
    def import_batches(self, request):
        """Історія завантажень (партії) + ВІДКАТ помилкової: DELETE ?batch=PB-..."""
        u = request.user
        if not (u.is_superuser or u.has_perm_code("finance.manage")):
            return Response({"detail": "Потрібне право «Керування фінмоделлю»"}, status=403)
        if request.method == "DELETE":
            b = request.query_params.get("batch") or ""
            if not b:
                return Response({"detail": "Вкажіть batch"}, status=400)
            qs = Transaction.objects.filter(import_batch=b)
            n = qs.count()
            qs.delete()
            return Response({"ok": True, "rolled_back": n, "batch": b})
        rows = (Transaction.objects.exclude(import_batch="").values("import_batch")
                .annotate(n=Count("id"), total=Sum("amount_uah"),
                          d_min=Min("date"), d_max=Max("date"))
                .order_by("-import_batch")[:40])
        return Response([{"batch": r["import_batch"], "count": r["n"], "total": float(r["total"] or 0),
                          "from": r["d_min"], "to": r["d_max"]} for r in rows])

    @action(detail=False, methods=["get"], url_path="bank-accounts")
    def bank_accounts(self, request):
        """Рахунки на СТОРОНІ БАНКУ (для мапінгу на рахунки CRM). ?provider=privatbank|monobank"""
        import json as _json
        import urllib.request
        import time as _time
        u = request.user
        if not (u.is_superuser or u.has_perm_code("finance.manage")):
            return Response({"detail": "Потрібне право «Керування фінмоделлю»"}, status=403)
        prov = request.query_params.get("provider")
        from apps.integrations.models import IntegrationSettings
        st = IntegrationSettings.objects.filter(provider=prov).first()
        cfg = (st.config or {}) if st else {}
        token = cfg.get("token")
        if not token:
            return Response({"detail": "Спочатку збережи токен"}, status=400)
        out = []
        if prov == "privatbank":
            acc_map = dict(cfg.get("acc_map") or {})
            today = _time.strftime("%d-%m-%Y")
            url = "https://acp.privatbank.ua/api/statements/balance?startDate=%s&endDate=%s&limit=100" % (today, today)
            req = urllib.request.Request(url, headers={"token": token, "Content-Type": "application/json;charset=utf8"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = _json.loads(r.read().decode())
            except Exception as e:
                return Response({"detail": "AutoClient: %s" % str(e)[:200]}, status=400)
            for b in data.get("balances", []):
                iban = b.get("acc") or ""
                tail = iban[-4:]
                out.append({"key": iban, "tail": tail, "title": (b.get("nameACC") or "")[:60],
                            "iban": iban, "balance": b.get("balanceOut") or b.get("balanceOutEq") or "",
                            "currency": b.get("currency") or "UAH",
                            "mapped_account_id": acc_map.get(tail)})
        elif prov == "monobank":
            mono_map = dict(cfg.get("mono_map") or {})
            req = urllib.request.Request("https://api.monobank.ua/personal/client-info", headers={"X-Token": token})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = _json.loads(r.read().decode())
            except Exception as e:
                return Response({"detail": "Monobank: %s" % str(e)[:200]}, status=400)
            CCY = {980: "UAH", 840: "USD", 978: "EUR"}
            for a in data.get("accounts", []):
                pan = (a.get("maskedPan") or [""])
                pan = pan[0] if pan else ""
                out.append({"key": a.get("id"), "tail": (a.get("iban") or "")[-4:],
                            "title": ("%s %s" % (a.get("type") or "", pan)).strip()[:60],
                            "iban": a.get("iban") or "", "balance": (a.get("balance") or 0) / 100.0,
                            "currency": CCY.get(a.get("currencyCode"), str(a.get("currencyCode"))),
                            "mapped_account_id": mono_map.get(str(a.get("id")))})
        else:
            return Response({"detail": "provider: privatbank | monobank"}, status=400)
        return Response(out)

    @action(detail=False, methods=["post"], url_path="bank-map")
    def bank_map(self, request):
        """Привʼязати рахунок банку до рахунку CRM. body: {provider, key, account_id | create_name}"""
        u = request.user
        if not (u.is_superuser or u.has_perm_code("finance.manage")):
            return Response({"detail": "Потрібне право «Керування фінмоделлю»"}, status=403)
        prov = request.data.get("provider")
        key = str(request.data.get("key") or "")
        from apps.integrations.models import IntegrationSettings
        st = IntegrationSettings.objects.filter(provider=prov).first()
        if not st or not key:
            return Response({"detail": "нема провайдера або key"}, status=400)
        cfg = st.config or {}
        aid = request.data.get("account_id")
        if request.data.get("create_name"):
            acc = Account.objects.create(name=str(request.data["create_name"])[:120], kind="bank")
            aid = acc.id
        if prov == "privatbank":
            m = dict(cfg.get("acc_map") or {})
            tail = key[-4:]
            if aid:
                m[tail] = int(aid)
            else:
                m.pop(tail, None)
            cfg["acc_map"] = m
        else:
            m = dict(cfg.get("mono_map") or {})
            if aid:
                m[key] = int(aid)
            else:
                m.pop(key, None)
            cfg["mono_map"] = m
        st.config = cfg
        st.save(update_fields=["config"])
        return Response({"ok": True, "account_id": aid})

    @action(detail=False, methods=["get", "post"], url_path="bank-settings")
    def bank_settings(self, request):
        """Налаштування банків (Приват/Моно) — токени та привʼязка рахунків."""
        from apps.integrations.models import IntegrationSettings
        u = request.user
        if not (u.is_superuser or u.has_perm_code("finance.manage")):
            return Response({"detail": "Потрібне право «Керування фінмоделлю»"}, status=403)
        if request.method == "POST":
            prov = request.data.get("provider")
            if prov not in ("privatbank", "monobank"):
                return Response({"detail": "provider: privatbank | monobank"}, status=400)
            st, _ = IntegrationSettings.objects.get_or_create(provider=prov, defaults={"config": {}})
            cfg = st.config or {}
            for k in ("token", "acc", "account_id", "mono_account"):
                if k in request.data:
                    cfg[k] = request.data[k]
            st.config = cfg
            st.is_active = bool(cfg.get("token"))
            st.save()
        out = {}
        for prov in ("privatbank", "monobank"):
            st = IntegrationSettings.objects.filter(provider=prov).first()
            cfg = (st.config or {}) if st else {}
            out[prov] = {"connected": bool(st and st.is_active and cfg.get("token")),
                         "acc": cfg.get("acc") or "", "account_id": cfg.get("account_id"),
                         "mono_account": cfg.get("mono_account") or "",
                         "token_tail": ("…" + str(cfg.get("token"))[-6:]) if cfg.get("token") else ""}
        return Response(out)

    @action(detail=False, methods=["get"])
    def export(self, request):
        """Експорт журналу в CSV (Excel-friendly, ; та BOM). Фільтри як у списку."""
        import csv
        import io as _io
        qs = self.filter_queryset(self.get_queryset()).order_by("-date", "-id")[:20000]
        buf = _io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Дата", "Тип", "Сума", "Валюта", "Сума грн", "Категорія", "Контрагент",
                    "Рахунок", "Напрямок", "Сделка", "Коментар"])
        for tx in qs:
            w.writerow([tx.date.isoformat(), {"in": "Дохід", "out": "Витрата", "transfer": "Переказ"}.get(tx.direction, tx.direction),
                        str(tx.amount), tx.currency, str(tx.amount_uah),
                        tx.category.name if tx.category else "", tx.counterparty,
                        tx.account.name if tx.account else "",
                        tx.fin_direction.name if tx.fin_direction else "",
                        tx.deal_id or "", (tx.comment or "").replace("\n", " ")])
        resp = HttpResponse("\ufeff" + buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = "attachment; filename=journal.csv"
        return resp

    @action(detail=False, methods=["post"], url_path="import-statement")
    def import_statement(self, request):
        """Імпорт банківської виписки (CSV) у журнал. {data, account, commit}.
        Гнучкий парс колонок (дата/сума/призначення/контрагент/тип). Дедуп: дата+сума+призначення."""
        import csv
        import io as _io
        from datetime import datetime as _dtm
        u = request.user
        if not (u.is_superuser or u.has_perm_code("finance.manage")):
            return Response({"detail": "Потрібне право «Керування фінмоделлю»"}, status=403)
        raw = request.data.get("data") or ""
        commit = bool(request.data.get("commit"))
        acc = Account.objects.filter(id=request.data.get("account")).first() or Account.objects.first()
        if not raw.strip():
            return Response({"detail": "Порожній файл"}, status=400)
        delim = ";" if raw.count(";") >= raw.count(",") else ","
        rows = list(csv.reader(_io.StringIO(raw), delimiter=delim))
        if not rows:
            return Response({"detail": "Немає рядків"}, status=400)
        hdr = [str(c).strip().lower() for c in rows[0]]

        def col(*keys):
            for i, h in enumerate(hdr):
                if any(k in h for k in keys):
                    return i
            return None
        i_date = col("дата")
        i_sum = col("сума", "сумма", "sum")
        i_osnd = col("призначення", "опис", "назначение", "osnd", "категор")
        i_cp = col("контрагент", "кореспондент", "назва")
        i_type = col("тип", "дебет")
        if i_date is None or i_sum is None:
            return Response({"detail": "Не знайдено колонки Дата/Сума. Заголовки: %s" % hdr[:8]}, status=400)

        def _num(x):
            try:
                return float(str(x).replace(" ", "").replace("\u00a0", "").replace(",", "."))
            except (TypeError, ValueError):
                return None
        from django.utils import timezone as _tzst
        st_batch = "ST-" + _tzst.now().strftime("%Y%m%d-%H%M%S")
        p_from, p_to = request.data.get("from"), request.data.get("to")
        # ГАРД: якщо рахунок вже синхронізується з банком (є PB#-рядки) — файл НЕ може
        # створювати операції за банківський період (інакше дублі, інцидент 04-07.07)
        bank_since = None
        if acc:
            first_pb = (Transaction.objects.filter(account=acc, comment__icontains="PB#")
                        .order_by("date").values_list("date", flat=True).first())
            bank_since = first_pb
        created = dup = errs = skipped_bank = 0
        preview = []
        for r in rows[1:]:
            if not any((str(c) or "").strip() for c in r):
                continue
            ds = (r[i_date] if i_date < len(r) else "").strip()[:10]
            dte = None
            for f in ("%d.%m.%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    dte = _dtm.strptime(ds, f).date(); break
                except ValueError:
                    continue
            amt = _num(r[i_sum]) if i_sum < len(r) else None
            if dte is None or amt is None or amt == 0:
                errs += 1
                continue
            osnd = (r[i_osnd].strip() if i_osnd is not None and i_osnd < len(r) else "")[:180]
            cp = (r[i_cp].strip() if i_cp is not None and i_cp < len(r) else "")[:160]
            if i_type is not None and i_type < len(r):
                tval = str(r[i_type]).lower()
                direction = "out" if ("д" in tval[:2] or "d" in tval[:2]) else "in"
            else:
                direction = "in" if amt > 0 else "out"
            amt = abs(amt)
            if Transaction.objects.filter(date=dte, amount=amt,
                                          comment__icontains=osnd[:40] or "\u0000").exists() and osnd:
                dup += 1
                continue
            if p_from and dte.isoformat() < p_from:
                continue  # поза обраним періодом
            if p_to and dte.isoformat() > p_to:
                continue
            if bank_since and dte >= bank_since:
                skipped_bank += 1
                continue
            if commit:
                _rr = apply_bank_rules(direction, osnd, cp, acc.name if acc else "")
                cat, fdir, fart, cp2 = _rr["category"], _rr["fin_direction"], _rr["fin_article"], _rr["counterparty"]
                Transaction.objects.create(direction=direction, amount=amt, amount_uah=amt,
                                           account=acc, date=dte, counterparty=cp2, channel=_rr["channel"],
                                           category=cat, fin_direction=fdir, fin_article=fart,
                                           import_batch=st_batch,
                                           comment=("Виписка · " + osnd)[:255])
            created += 1
            if len(preview) < 8:
                preview.append({"date": dte.isoformat(), "dir": direction, "amount": amt, "osnd": osnd[:60]})
        return Response({"created": created, "duplicates": dup, "errors": errs,
                         "skipped_bank": skipped_bank,
                         "bank_since": bank_since.isoformat() if bank_since else None,
                         "committed": commit, "preview": preview, "account": acc.name if acc else None,
                         "batch": st_batch if commit else None})

    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_fin("fin_accounts")
        if allowed is not None:
            from django.db.models import Q as _Qacc
            qs = qs.filter(_Qacc(account_id__in=allowed) | _Qacc(transfer_account_id__in=allowed))
        p = self.request.query_params
        if p.get("contact"):
            qs = qs.filter(contact_id=p["contact"])
        if p.get("from"):
            qs = qs.filter(date__gte=p["from"])
        if p.get("to"):
            qs = qs.filter(date__lte=p["to"])
        if p.get("q"):
            from django.db.models import Q as _Q
            term = p["q"]
            qs = qs.filter(_Q(comment__icontains=term) | _Q(counterparty__icontains=term) | _Q(account__name__icontains=term))
        # фільтри по окремих стовпцях
        if p.get("cat"): qs = qs.filter(category__name__icontains=p["cat"])
        if p.get("cp"): qs = qs.filter(counterparty__icontains=p["cp"])
        if p.get("comment"): qs = qs.filter(comment__icontains=p["comment"])
        if p.get("currency"): qs = qs.filter(currency=p["currency"])
        if p.get("amount_min"): qs = qs.filter(amount__gte=p["amount_min"])
        if p.get("amount_max"): qs = qs.filter(amount__lte=p["amount_max"])
        if p.get("accounts"):
            from django.db.models import Q as _Qa
            ids = [int(x) for x in str(p["accounts"]).split(",") if x.strip().isdigit()]
            if ids:
                qs = qs.filter(_Qa(account_id__in=ids) | _Qa(transfer_account_id__in=ids))
        # сортування: клік по стовпцю в журналі; дефолт — дата і ЧАС операції
        ALLOWED_ORD = {"date", "amount_uah", "counterparty", "category__name", "account__name",
                       "fin_article__name", "fin_direction__name", "channel", "comment", "op_time", "id", "currency"}
        ordering = (p.get("sort") or p.get("ordering") or "-date").strip()
        flds = []
        for f in ordering.split(","):
            f = f.strip()
            if f.lstrip("-") in ALLOWED_ORD:
                flds.append(f)
        if not flds:
            flds = ["-date"]
        if flds[0].lstrip("-") == "date":
            sign = "-" if flds[0].startswith("-") else ""
            flds = [sign + "date", sign + "op_time", sign + "id"]
        else:
            flds += ["-date", "-op_time"]
        return qs.order_by(*flds)

    @action(detail=True, methods=["get"])
    def attachments(self, request, pk=None):
        tx = self.get_object()
        return Response([{"id": a.id, "filename": a.filename, "content_type": a.content_type,
                          "size": a.size, "uploaded_at": a.uploaded_at} for a in tx.attachments.all()])

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def attach(self, request, pk=None):
        """Прикріпити фото/скан чека (multipart, поле file). Макс 10 МБ."""
        tx = self.get_object()
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "немає файлу"}, status=status.HTTP_400_BAD_REQUEST)
        if f.size > 10 * 1024 * 1024:
            return Response({"detail": "файл більший за 10 МБ"}, status=status.HTTP_400_BAD_REQUEST)
        a = TransactionAttachment.objects.create(
            transaction=tx, filename=f.name[:255],
            content_type=f.content_type or "application/octet-stream",
            size=f.size, data=f.read())
        return Response({"id": a.id, "filename": a.filename, "content_type": a.content_type, "size": a.size})


def _privat_cfg():
    from apps.integrations.models import IntegrationSettings
    st = IntegrationSettings.objects.filter(provider="privatbank").first()
    return (st.config or {}) if st and st.is_active else {}


def _rule_matches(r, direction, osnd, cp, acc_name):
    """Умови правила: І/АБО по полях комментар/контрагент/рахунок."""
    if r.direction and r.direction != direction:
        return False
    conds = [c for c in (r.conditions or []) if (c.get("text") or "").strip()]
    if not conds:
        return False
    vals = {"osnd": (osnd or "").lower(), "counterparty": (cp or "").lower(), "account": (acc_name or "").lower()}
    res = []
    for c in conds:
        hay = vals.get(c.get("field") or "osnd", "")
        txt = (c.get("text") or "").strip().lower()
        op = c.get("op") or "contains"
        if op == "contains":
            res.append(txt in hay)
        elif op == "not_contains":
            res.append(txt not in hay)
        else:  # equals
            res.append(hay.strip() == txt)
    return all(res) if (r.logic or "or") == "and" else any(res)


def apply_bank_rules(direction, osnd, cp, acc_name="", count_hit=True):
    """Перше активне правило (за пріоритетом), що збіглося → dict дій.
    Повертає {category, fin_direction, fin_article, counterparty, channel}."""
    from .models import BankRule, FinDirection, FinModelArticle
    from django.db.models import F as _F
    out = {"category": None, "fin_direction": None, "fin_article": None, "counterparty": cp, "channel": ""}
    for r in BankRule.objects.filter(active=True):
        if not _rule_matches(r, direction, osnd, cp, acc_name):
            continue
        a = r.actions or {}
        if a.get("category"):
            out["category"] = Category.objects.filter(id=a["category"]).first()
        if a.get("fin_direction"):
            out["fin_direction"] = FinDirection.objects.filter(id=a["fin_direction"]).first()
        if a.get("fin_article"):
            out["fin_article"] = FinModelArticle.objects.filter(id=a["fin_article"]).first()
        if a.get("counterparty"):
            out["counterparty"] = a["counterparty"]
        if a.get("channel"):
            out["channel"] = a["channel"]
        if count_hit:
            BankRule.objects.filter(id=r.id).update(hits=_F("hits") + 1)
        return out
    return out


def _fee_category():
    cat = Category.objects.filter(name__icontains="Комиссия Банка", direction="out").first()
    return cat or Category.objects.filter(name__icontains="Комис", direction="out").first()


def privat_pull(days=4, d_from=None, d_to=None, batch=None, acc=None):
    """Тягне виписку ПриватБанк AutoClient → журнал за період. Ідемпотентно (PB#REF).
    Правила розноски + авто-комісія LiqPay. Повертає (created, skipped, err, batch)."""
    import json as _json
    import urllib.request
    import time as _time
    from datetime import datetime as _dtm
    from django.utils import timezone as _tz
    cfg = _privat_cfg()
    token = cfg.get("token")
    if not token:
        return 0, 0, "ПриватБанк не налаштовано (Інтеграції: token)", None
    default_account = None
    if cfg.get("account_id"):
        default_account = Account.objects.filter(id=cfg["account_id"]).first()
    if default_account is None:
        default_account = Account.objects.filter(name__icontains="ФОП").first() or Account.objects.first()
    acc_map = dict(cfg.get("acc_map") or {})  # хвіст IBAN (4 цифри) → account_id

    def _resolve_account(iban):
        """Рахунок CRM для IBAN — ТІЛЬКИ через мапу підключень (⚙️ Банки).
        Непідключений рахунок банку -> None -> операція НЕ заливається."""
        tail = (iban or "")[-4:]
        if tail and tail in acc_map:
            return Account.objects.filter(id=acc_map[tail]).first()
        return None
    if d_from and d_to:
        start = _dtm.fromisoformat(str(d_from)).strftime("%d-%m-%Y")
        end = _dtm.fromisoformat(str(d_to)).strftime("%d-%m-%Y")
    else:
        end = _time.strftime("%d-%m-%Y")
        start = _time.strftime("%d-%m-%Y", _time.localtime(_time.time() - days * 86400))
    batch = batch or ("PB-" + _tz.now().strftime("%Y%m%d-%H%M%S"))
    txs = []
    follow = ""
    for _page in range(40):  # пагінація AutoClient (до 20000 операцій); БЕЗ acc = усі рахунки токена
        url = ("https://acp.privatbank.ua/api/statements/transactions"
               "?startDate=%s&endDate=%s&limit=500%s%s" % (start, end, follow, ("&acc=" + str(acc)) if acc else ""))
        req = urllib.request.Request(url, headers={"token": token, "Content-Type": "application/json;charset=utf8"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = _json.loads(r.read().decode())
        except Exception as e:
            return 0, 0, "AutoClient: %s" % str(e)[:200], None
        txs.extend(data.get("transactions", []))
        if data.get("exist_next_page") and data.get("next_page_id"):
            follow = "&followId=" + str(data["next_page_id"])
        else:
            break
    # + ПРОМІЖНА виписка за сьогодні: операції зʼявляються ОДРАЗУ, не чекаючи проводки банку
    # (дедуп по PB#REF — коли операція перейде у фінальну виписку, дубль не створиться)
    try:
        today_s = _time.strftime("%d-%m-%Y")
        url_i = ("https://acp.privatbank.ua/api/statements/transactions/interim"
                 "?startDate=%s&endDate=%s&limit=500%s" % (today_s, today_s, ("&acc=" + str(acc)) if acc else ""))
        req_i = urllib.request.Request(url_i, headers={"token": token, "Content-Type": "application/json;charset=utf8"})
        with urllib.request.urlopen(req_i, timeout=60) as r_i:
            data_i = _json.loads(r_i.read().decode("utf-8", errors="replace"))
        txs.extend(data_i.get("transactions", []))
    except Exception:
        pass
    created = skipped = 0
    for tr in txs:
        ref = tr.get("REF") or ""
        reftag = "PB#%s/%s" % (ref, tr.get("TRANTYPE") or "")
        if not ref or Transaction.objects.filter(comment__startswith=reftag).exists():
            skipped += 1
            continue
        try:
            amt = abs(float(tr.get("SUM_E") or tr.get("SUM") or 0))
        except (TypeError, ValueError):
            continue
        if amt <= 0:
            continue
        direction = "in" if (tr.get("TRANTYPE") == "C") else "out"
        d_od = (tr.get("DAT_OD") or "").strip()
        try:
            dte = _dtm.strptime(d_od, "%d.%m.%Y").date()
        except ValueError:
            dte = date.today()
        osnd = (tr.get("OSND") or "")[:180]
        from .services import canonical_counterparty as _ccp
        cp = _ccp(tr.get("AUT_CNTR_NAM") or "")[:160]
        op_t = None
        try:
            tim = (tr.get("TIM_P") or "").strip()
            if tim:
                op_t = _dtm.strptime(tim, "%H:%M").time()
        except ValueError:
            op_t = None
        account = _resolve_account(tr.get("AUT_MY_ACC") or "")
        if account is None:  # рахунок банку не підключено у ⚙️ Банки — пропускаємо
            skipped += 1
            continue
        # еквайринг по угоді (WCCRM-<id>): дохід ВЖЕ створений CRM при оплаті — не дублюємо,
        # АЛЕ комісію LiqPay (дохід сделки − зарахування банку) розносимо витратою автоматично
        import re as _re
        m = _re.search(r"WCCRM-(\d+)", osnd)
        if m and direction == "in":
            did = int(m.group(1))
            # шукаємо САМЕ ту оплату, чиє зарахування прийшло (gross >= net, комісія <= 6%)
            dealtx = (Transaction.objects.filter(deal_id=did, direction="in",
                      amount_uah__gte=amt - 1, amount_uah__lte=float(amt) * 1.06 + 5)
                      .order_by("id").first()
                      or Transaction.objects.filter(deal_id=did, direction="in").order_by("id").first())
            if dealtx:
                from .services import liqpay_account as _liqacc
                _liq = _liqacc()
                feetag = "PBFEE#%s" % ref
                fee = float(dealtx.amount_uah or dealtx.amount) - amt
                if fee > 0.009 and not Transaction.objects.filter(comment__startswith=feetag).exists():
                    Transaction.objects.create(
                        direction="out", amount=round(fee, 2), amount_uah=round(fee, 2),
                        account=_liq, date=dte, op_time=op_t, deal_id=did, category=_fee_category(),
                        counterparty="LiqPay", import_batch=batch,
                        comment=(feetag + " · Комісія еквайрингу по угоді #%s" % did)[:255])
                    created += 1
                # зарахування банку = ПЕРЕКАЗ LiqPay → банківський рахунок (нетто), НЕ дохід
                Transaction.objects.create(
                    direction="transfer", amount=amt, amount_uah=amt,
                    account=_liq, transfer_account=account, date=dte, op_time=op_t, deal_id=did,
                    counterparty="LiqPay", import_batch=batch,
                    comment=(reftag + " · Зарахування еквайрингу по угоді #%s" % did)[:255])
                created += 1
                continue
        # оплата за РЕКВІЗИТАМИ з призначенням «Оплата замовлення WCR-<id>» →
        # привʼязка до сделки + Payment (ідемпотентно по банківському REF) + чек + стадія
        # виплата накладених платежів від НоваПей/Нової Пошти = ДОХІД (гроші реально на рахунку).
        # Категорія «Онлайн (Instagram/TikTok/сайт)», напрямок ДЕКОР — як продаж.
        if direction == "in" and ("нова пошта" in (cp or "").lower() or "новапошта" in (cp or "").lower()
                                  or "новапей" in (cp or "").lower() or "novapay" in (cp or "").lower()):
            cat_np = Category.objects.filter(name="Онлайн (Instagram/TikTok/сайт)", direction="in").first()
            tx_np = Transaction.objects.create(
                direction="in", amount=amt, amount_uah=amt, account=account,
                category=cat_np, date=dte, op_time=op_t, counterparty=(cp or "НоваПей")[:160], rate=1,
                import_batch=batch, comment=(reftag + " · " + osnd)[:255])
            created += 1
            # гроші дійшли → закрити очікування по наложках: старіші виплати покривають
            # раніше отримані посилки (виплата йде пачкою, тому список, а не одна сделка)
            try:
                from apps.crm.models import Payment as _PayNP, log_activity as _laNP
                waiting = list(_PayNP.objects.filter(provider="np_cod", is_paid=False)
                               .order_by("created_at"))
                # спершу ТОЧНИЙ поодинокий матч: виплата = одна наложка мінус комісія (до 8%)
                _singles = [w for w in waiting if float(amt) <= float(w.amount) <= float(amt) * 1.08]
                if len(_singles) == 1:
                    waiting = _singles
                rest = float(amt) * 1.05  # запас на комісію НоваПей
                matched = []
                for w in waiting:
                    if float(w.amount) <= rest:
                        w.is_paid = True
                        w.save(update_fields=["is_paid"])
                        rest -= float(w.amount)
                        matched.append(w)
                        _laNP("deal", w.deal_id, "Наложка виплачена",
                              "Виплата НоваПей надійшла на рахунок банку — %s грн зараховано як оплату" % w.amount,
                              None, "Банк")
                # привʼязка доходу до сделки: рівно ОДНА наложка у виплаті → сделка/клієнт/канал;
                # кілька — перелічуємо сделки в коменті (одна банківська сума на кілька посилок)
                if len(matched) == 1 and matched[0].deal_id:
                    _dnp = matched[0].deal
                    tx_np.deal = _dnp
                    if _dnp.contact_id:
                        tx_np.contact = _dnp.contact
                        tx_np.counterparty = ((" ".join(filter(None, [_dnp.contact.first_name or "", _dnp.contact.last_name or ""])).strip()
                                               or (_dnp.contact.nickname or "")) or tx_np.counterparty)[:160]
                    tx_np.channel = (_dnp.source or "")[:24] or tx_np.channel
                    tx_np.comment = (tx_np.comment[:200] + " · наложка по сделці #%s" % _dnp.id)[:255]
                    tx_np.save(update_fields=["deal", "contact", "counterparty", "channel", "comment"])
                elif len(matched) > 1:
                    _ids = ", ".join("#%s" % w.deal_id for w in matched if w.deal_id)
                    tx_np.comment = (tx_np.comment[:180] + " · наложки по сделках: " + _ids)[:255]
                    tx_np.save(update_fields=["comment"])
            except Exception:
                pass
            continue
        # ідентифікатор оплати = НОМЕР СДЕЛКИ у призначенні (5-6 цифр).
        # Роки (4 цифри), телефони (10+), рахунки (7+) під шаблон не потрапляють.
        did_r = 0
        if direction == "in":
            from apps.crm.models import Deal as _DealChk
            from django.utils import timezone as _tzn
            from datetime import timedelta as _tdn
            found = []
            for numtxt in set(_re.findall(r"(?<!\d)(\d{5,6})(?!\d)", osnd)):
                num = int(numtxt)
                # число == сумі платежу — це сума, а не номер угоди
                try:
                    if num == int(round(float(amt))):
                        continue
                except (TypeError, ValueError):
                    pass
                _dc = _DealChk.objects.filter(id=num).select_related("stage").first()
                if _dc is None:
                    continue
                # захист від випадкових збігів (номери рахунків/накладних/суми у призначенні):
                # угода свіжа (180 днів), не програна, з сумою, і платіж не більший за суму угоди
                if _dc.created_at < _tzn.now() - _tdn(days=180):
                    continue
                if _dc.stage_id and getattr(_dc.stage, "is_lost", False):
                    continue
                if not _dc.amount or float(amt) > float(_dc.amount) * 1.05 + 100:
                    continue
                found.append(num)
            if len(found) == 1:
                did_r = found[0]
        if did_r and direction == "in":
            from apps.crm.models import Deal as _Deal, Payment as _Pay, log_activity as _la
            _d = _Deal.objects.filter(id=did_r).first()
            if _d and not _Pay.objects.filter(external_id=ref).exists():
                rr0 = apply_bank_rules(direction, osnd, cp, account.name if account else "")
                cust = ((" ".join(filter(None, [_d.contact.first_name or "", _d.contact.last_name or ""])).strip() if _d.contact_id else "") or cp)
                Transaction.objects.create(
                    direction="in", amount=amt, amount_uah=amt, account=account, deal=_d,
                    date=dte, op_time=op_t, counterparty=cust[:160],
                    category=Category.objects.filter(name="Продаж товару", direction="in").first(),
                    fin_direction=rr0["fin_direction"], channel=(_d.source or "")[:24],
                    import_batch=batch, comment=(reftag + " · " + osnd)[:255])
                _w = _Pay.objects.filter(deal=_d, provider="reqs", is_paid=False,
                                         external_id__startswith="WAIT-").first()
                if _w:
                    _w.amount = amt; _w.is_paid = True; _w.external_id = ref
                    _w.save(update_fields=["amount", "is_paid", "external_id"])
                else:
                    _Pay.objects.create(deal=_d, provider="reqs", amount=amt, is_paid=True, external_id=ref)
                created += 1
                try:
                    from apps.crm.views import _advance_after_payment, _issue_checkbox_for_deal
                    from decimal import Decimal as _Dec
                    paid_r = sum((pp.amount for pp in _Pay.objects.filter(deal=_d, is_paid=True)), _Dec("0"))
                    if paid_r > 0:
                        _advance_after_payment(_d, "Оплата за реквізитами отримана (банк, REF %s)" % ref)
                    _issue_checkbox_for_deal(_d, user=None)
                    _la("deal", _d.id, "Оплата за реквізитами", "%s грн з банку (REF %s) — авто-фіксація" % (amt, ref), None, "Банк")
                except Exception:
                    pass
                continue
        # переказ власних коштів (на свою картку/рахунок) — це transfer, не витрата (не спотворює P&L)
        transfer_dest = None
        if "переказ власних" in osnd.lower():
            # отримувач: карта з призначення («5221 **** **** 6953») → рахунок CRM за хвостом у назві
            mm = _re.search(r"\*\*\*\*\s*(\d{4})", osnd)
            if mm:
                transfer_dest = Account.objects.filter(name__icontains=mm.group(1)).first()
            if direction == "in":
                # зарахування переказу: якщо друга сторона (списання /D) вже в журналі — це ТОЙ САМИЙ переказ:
                # проставляємо їй отримувача і НЕ створюємо другий рядок
                twin = Transaction.objects.filter(comment__startswith="PB#%s/D" % ref, direction="transfer").first()
                if twin:
                    if not twin.transfer_account_id:
                        twin.transfer_account = account
                        twin.save(update_fields=["transfer_account"])
                    skipped += 1
                    continue
                # друга сторона ще НЕ в журналі: зарахування = переказ НА цей рахунок.
                # Джерело невідоме поки не прийде /D — тимчасово транзит (при /D зіллється)
                _transit, _ = Account.objects.get_or_create(
                    name="Транзит · поповнення карток (нез'ясовано)", defaults={"kind": "bank", "is_active": False})
                Transaction.objects.create(
                    direction="transfer", amount=amt, amount_uah=amt, account=_transit, transfer_account=account,
                    date=dte, op_time=op_t, counterparty=cp, import_batch=batch,
                    comment=(reftag + " · " + osnd)[:255])
                created += 1
                continue
            # списання (/D): якщо C-сторона вже створена (через транзит) — зливаємо в ОДИН переказ
            twin_c = Transaction.objects.filter(comment__startswith="PB#%s/C" % ref, direction="transfer").first()
            if twin_c:
                dest_acc = twin_c.transfer_account
                twin_c.delete()
                transfer_dest = transfer_dest or dest_acc
            direction = "transfer"
        _rr = apply_bank_rules(direction, osnd, cp, account.name if account else "")
        Transaction.objects.create(
            direction=direction, amount=amt, amount_uah=amt, account=account,
            transfer_account=transfer_dest if direction == "transfer" else None,
            date=dte, op_time=op_t, counterparty=_rr["counterparty"], channel=_rr["channel"],
            category=_rr["category"], fin_direction=_rr["fin_direction"], fin_article=_rr["fin_article"],
            import_batch=batch, comment=(reftag + " · " + osnd)[:255])
        created += 1
    # зберегти мапу IBAN→рахунок (нові рахунки, авто-матчі)
    try:
        from apps.integrations.models import IntegrationSettings
        st = IntegrationSettings.objects.filter(provider="privatbank").first()
        if st and (st.config or {}).get("acc_map") != acc_map:
            st.config["acc_map"] = acc_map
            st.save(update_fields=["config"])
    except Exception:
        pass
    try:
        auto_settle_payables(batch)
    except Exception:
        pass
    return created, skipped, None, batch


def auto_settle_payables(batch):
    """Авто-погашення кредиторки: вихідні операції виписки цього батчу матчимо з planned-payable
    ТІЛЬКИ за отримувачем (ЄДРПОУ або IBAN) + сума <= залишок. Інкремент paid_amount, закриваємо при 0.
    Один платіж гасить один борг (гард used_tx). Назва-матч НЕ використовуємо (щоб не переплутати)."""
    import re as _re
    from decimal import Decimal as _D
    from .models import PlannedPayment
    if not batch:
        return 0
    used_tx = set(PlannedPayment.objects.exclude(paid_tx=None).values_list("paid_tx_id", flat=True))
    payables = list(PlannedPayment.objects.filter(kind="payable", status="planned").select_related("contact"))
    if not payables:
        return 0
    settled = 0
    for tx in Transaction.objects.filter(import_batch=batch, direction="out"):
        if tx.id in used_tx:
            continue
        amount = float(tx.amount_uah or tx.amount or 0)
        if amount <= 0:
            continue
        text = tx.comment or ""
        m = _re.search(r"(?:ЄДРПОУ|ІПН)\s*(\d{8,12})", text)
        tx_crf = m.group(1) if m else None
        m = _re.search(r"(UA\d{27})", text)
        tx_iban = m.group(1) if m else None
        if not tx_crf and not tx_iban:
            continue  # немає надійного ідентифікатора отримувача — не чіпаємо
        best = None
        for pp in payables:
            if pp.status != "planned":
                continue
            remaining = float(pp.amount) - float(pp.paid_amount or 0)
            if remaining <= 0.01 or amount > remaining + 0.5:
                continue
            nceo = (getattr(pp.contact, "edrpou", "") if pp.contact_id else "") or ""
            iban = (getattr(pp.contact, "iban", "") if pp.contact_id else "") or ""
            ptext = pp.comment or ""
            if not nceo:
                mm = _re.search(r"(?:ЄДРПОУ|ІПН)\s*(\d{8,12})", ptext)
                nceo = mm.group(1) if mm else ""
            if not iban:
                mm = _re.search(r"(UA\d{27})", ptext)
                iban = mm.group(1) if mm else ""
            if not ((tx_crf and nceo and tx_crf == nceo) or (tx_iban and iban and tx_iban == iban)):
                continue
            score = 3 if abs(remaining - amount) < 0.01 else (2 if abs(float(pp.amount) - amount) < 0.01 else 1)
            if best is None or score > best[1]:
                best = (pp, score)
        if best:
            pp = best[0]
            pp.paid_amount = _D(str(pp.paid_amount or 0)) + _D(str(amount))
            if pp.paid_amount >= _D(str(pp.amount)):
                pp.status = "paid"
            pp.paid_tx = tx
            pp.save(update_fields=["paid_amount", "status", "paid_tx"])
            used_tx.add(tx.id)
            settled += 1
    return settled


def mono_pull(d_from, d_to, mono_account=None):
    """Виписка Monobank personal API → журнал. Ліміт API: період ≤31 доби, 1 запит/хв.
    Ідемпотентно (MONO#id). Повертає (created, skipped, err, batch)."""
    import json as _json
    import urllib.request
    from datetime import datetime as _dtm, timedelta as _td2
    from django.utils import timezone as _tz
    from apps.integrations.models import IntegrationSettings
    st = IntegrationSettings.objects.filter(provider="monobank").first()
    cfg = (st.config or {}) if st and st.is_active else {}
    token = cfg.get("token")
    if not token:
        return 0, 0, "Monobank не налаштовано (Інтеграції: token)", None
    mono_acc = mono_account or cfg.get("mono_account") or "0"
    mono_map = dict(cfg.get("mono_map") or {})  # id рахунку mono -> account_id CRM
    account = (Account.objects.filter(id=mono_map.get(str(mono_acc)) or 0).first()
               or Account.objects.filter(id=cfg.get("account_id") or 0).first()
               or Account.objects.filter(name__icontains="МОНО").first() or Account.objects.first())
    f = _dtm.fromisoformat(str(d_from))
    t = _dtm.fromisoformat(str(d_to)) + _td2(days=1)
    if (t - f).days > 31:
        return 0, 0, "Monobank: період не більше 31 доби за один раз (ліміт API)", None
    url = "https://api.monobank.ua/personal/statement/%s/%d/%d" % (mono_acc, int(f.timestamp()), int(t.timestamp()))
    req = urllib.request.Request(url, headers={"X-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            items = _json.loads(r.read().decode())
    except Exception as e:
        return 0, 0, "Monobank API: %s" % str(e)[:200], None
    if not isinstance(items, list):
        return 0, 0, "Monobank: %s" % str(items)[:150], None
    batch = "MONO-" + _tz.now().strftime("%Y%m%d-%H%M%S")
    created = skipped = 0
    for it in items:
        tid = it.get("id") or ""
        tag = "MONO#%s" % tid
        if not tid or Transaction.objects.filter(comment__startswith=tag).exists():
            skipped += 1
            continue
        amt = (it.get("amount") or 0) / 100.0
        direction = "in" if amt > 0 else "out"
        osnd = (it.get("description") or "")[:180]
        _mdt = _dtm.fromtimestamp(it.get("time") or 0)
        dte = _mdt.date()
        _rr = apply_bank_rules(direction, osnd, osnd, account.name if account else "")
        Transaction.objects.create(
            direction=direction, amount=abs(amt), amount_uah=abs(amt), account=account,
            date=dte, op_time=_mdt.time(), counterparty=(_rr["counterparty"] or "")[:160], channel=_rr["channel"],
            category=_rr["category"], fin_direction=_rr["fin_direction"], fin_article=_rr["fin_article"],
            import_batch=batch, comment=(tag + " · " + osnd)[:255])
        created += 1
    return created, skipped, None, batch


class PlannedPaymentViewSet(viewsets.ModelViewSet):
    """Дебіторка/Кредиторка. mark-paid → фактична операція в журналі + статус paid."""
    from .models import PlannedPayment as _PP
    queryset = _PP.objects.select_related("category", "account")
    from .serializers import PlannedPaymentSerializer as _PPS
    serializer_class = _PPS
    filterset_fields = ["kind", "status"]
    permission_classes = [FinancePerm]

    def perform_create(self, serializer):
        _fin_guard(self.request, "finance.debts.edit", "Дт/Кт: нема права створювати записи")
        serializer.save()

    def perform_update(self, serializer):
        _fin_guard(self.request, "finance.debts.edit", "Дт/Кт: нема права редагувати записи")
        serializer.save()

    def perform_destroy(self, instance):
        _fin_guard(self.request, "finance.debts.edit", "Дт/Кт: нема права видаляти записи")
        instance.delete()

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        from django.utils import timezone as _tz
        _fin_guard(request, "finance.debts.pay", "Дт/Кт: нема права відмічати оплату")
        pp = self.get_object()
        if pp.status == "paid":
            return Response({"detail": "вже оплачено"}, status=400)
        from decimal import Decimal as _D
        remaining = _D(str(pp.amount)) - _D(str(pp.paid_amount or 0))
        raw = request.data.get("amount")
        try:
            amt = _D(str(raw)) if raw not in (None, "") else remaining
        except Exception:
            amt = remaining
        if amt <= 0:
            return Response({"detail": "Сума погашення має бути > 0"}, status=400)
        if amt > remaining:
            amt = remaining
        acc = pp.account or Account.objects.filter(is_active=True).first()
        tx = Transaction.objects.create(
            direction="out" if pp.kind == "payable" else "in",
            amount=amt, amount_uah=amt, account=acc,
            date=_tz.localdate(), op_time=_tz.localtime().time(),
            category=pp.category, counterparty=pp.counterparty, deal=pp.deal, contact=pp.contact,
            fin_direction=pp.fin_direction, fin_article=pp.fin_article, channel=pp.channel or "",
            comment=("Дт/Кт погашення: " + (pp.comment or ""))[:255])
        pp.paid_amount = _D(str(pp.paid_amount or 0)) + amt
        if pp.paid_amount >= _D(str(pp.amount)):
            pp.status = "paid"
        pp.paid_tx = tx
        pp.save(update_fields=["paid_amount", "status", "paid_tx"])
        return Response(self.get_serializer(pp).data)

    @action(detail=True, methods=["post"], url_path="pay-with-fop")
    def pay_with_fop(self, request, pk=None):
        """Готує платіж по кредиторці через ПриватБанк Автоклієнт (ФОП).
        БЕЗ confirm=1 — dry-run (показує що піде, нічого не шле). З confirm=1 — створює
        ЧЕРНЕТКУ платежу у Приват24 (НЕ підписану). Гроші йдуть лише коли Олег підпише КЕП у Приват24."""
        import json as _json
        import urllib.request as _ur
        import urllib.error as _ue
        import re as _re2
        from django.utils import timezone as _tz
        from apps.integrations.models import IntegrationSettings

        _fin_guard(request, "finance.debts.pay", "Немає права оплачувати")
        pp = self.get_object()
        if pp.kind != "payable":
            return Response({"detail": "Оплата тільки для кредиторки"}, status=400)
        if pp.status == "paid":
            return Response({"detail": "Вже оплачено"}, status=400)
        # реквізити отримувача
        iban = nceo = None
        if pp.contact_id:
            iban = (getattr(pp.contact, "iban", "") or "").strip() or None
            nceo = (getattr(pp.contact, "edrpou", "") or "").strip() or None
        text = pp.comment or ""
        if not iban:
            m = _re2.search(r"(UA\d{27})", text)
            iban = m.group(1) if m else None
        if not nceo:
            m = _re2.search(r"(?:ЄДРПОУ|ІПН)\s*(\d{8,12})", text)
            nceo = m.group(1) if m else None
        name = (pp.counterparty or (pp.contact.first_name if pp.contact_id else "") or "").strip()
        if not iban:
            return Response({"detail": "Немає IBAN отримувача — впиши реквізити у картці контрагента"}, status=400)
        cfg = IntegrationSettings.objects.filter(provider="privatbank").first()
        cfg = (cfg.config if cfg else {}) or {}
        payer = (cfg.get("acc") or "").strip()
        token = (cfg.get("token") or "").strip()
        from decimal import Decimal as _D2
        remaining = float(_D2(str(pp.amount)) - _D2(str(pp.paid_amount or 0)))
        raw_amt = request.data.get("amount")
        try:
            pay_amt = float(raw_amt) if raw_amt not in (None, "") else remaining
        except Exception:
            pay_amt = remaining
        if pay_amt <= 0 or pay_amt > remaining:
            pay_amt = remaining
        dest = ("Оплата: " + (pp.comment or "рахунку"))[:420]
        if len(dest) < 5:
            dest = "Оплата рахунку постачальника"
        docnum = "CRM%s-%s" % (pp.id, _tz.now().strftime("%y%m%d%H%M"))
        payload = {
            "document_number": docnum,
            "payer_account": payer,
            "recipient_account": iban,
            "recipient_nceo": nceo or "0000000000",
            "payment_naming": name[:120] or "Отримувач",
            "payment_amount": ("%.2f" % pay_amt),
            "payment_destination": dest,
        }
        confirm = str(request.data.get("confirm") or "").lower() in ("1", "true", "yes", "on")
        if not confirm or not token or not payer:
            return Response({"dry_run": True, "would_send": payload, "ready": bool(token and payer),
                             "note": "Для відправки — confirm=1. Створиться ЧЕРНЕТКА у Приват24 — підпиши її КЕП (SmartID), тоді гроші підуть."})
        # LIVE — створити чернетку платежу (Олег ініціює кнопкою)
        body = _json.dumps(payload, ensure_ascii=False).encode("cp1251", "replace")
        req = _ur.Request("https://acp.privatbank.ua/api/proxy/payment/create_pred", data=body, method="POST",
                          headers={"token": token, "User-Agent": "WallcovCRM", "Content-Type": "application/json;charset=cp1251"})
        try:
            with _ur.urlopen(req, timeout=40) as r:
                resp = _json.loads(r.read().decode("cp1251", "ignore"))
        except _ue.HTTPError as e:
            return Response({"detail": "Приват відхилив: %s" % e.read().decode("cp1251", "ignore")[:400]}, status=400)
        except Exception as e:  # noqa
            return Response({"detail": "Помилка звʼязку з Приват: %s" % e}, status=400)
        ref = resp.get("payment_ref")
        pp.comment = ((pp.comment or "")[:200] + (" · Privat:%s" % (ref or "?")))[:255]
        pp.save(update_fields=["comment"])
        return Response({"ok": True, "payment_ref": ref, "payment_status": resp.get("payment_status"),
                         "note": "Платіж створено у Приват24 як чернетку. Підпиши його КЕП у Приват24 Бізнес — тоді гроші підуть."})


    # ── Імпорт акта Нової Пошти → кредиторка (пункт 4) ──────────────────────
    @action(detail=False, methods=["post"], url_path="import-np-act",
            parser_classes=[MultiPartParser, FormParser])
    def import_np_act(self, request):
        """Імпорт акта Нової Пошти (Специфікація [+ опц. Рахунок-фактура] xlsx) → КРЕДИТОРКА.
        files: spec (обов'язково), rahunok (опц). commit=1 — застосувати, інакше preview.
        Створює ОДИН PlannedPayment(payable) на суму акта. Собівартість доставки по кожній
        сделці пишеться в Deal.np_data['delivery_acts'] БЕЗ грошової операції — щоб не задвоїти
        P&L (реальна витрата зайде один раз при оплаті кредиторки). Ідемпотентно за номером акта."""
        from .np_act import parse_act
        from .models import PlannedPayment
        from apps.crm.models import Deal
        from django.utils import timezone as _tz
        import datetime as _dt

        _fin_guard(request, "finance.debts.edit", "Дт/Кт: нема права створювати записи")
        spec_f = request.FILES.get("spec")
        rah_f = request.FILES.get("rahunok")
        if not spec_f:
            return Response({"detail": "Потрібен файл Специфікації (xlsx)"}, status=400)
        try:
            act = parse_act(spec_f, rah_f)
        except Exception as e:
            return Response({"detail": "Не вдалося розібрати файл: %s" % e}, status=400)
        inv = act.get("invoice_number")
        amount = act.get("amount")
        if not inv or not amount:
            return Response({"detail": "У файлі не знайдено номер акта або суму"}, status=400)

        # мапимо відправлення на сделки за номером ЕН (Deal.ttn)
        ship_rows = []
        for s in act["shipments"]:
            d = Deal.objects.filter(ttn=s["ttn"]).first() if s.get("ttn") else None
            ship_rows.append({"ttn": s["ttn"], "date": s["date"], "route": s["route"],
                              "cost": s["cost"],
                              "deal_id": d.id if d else None,
                              "deal_title": (getattr(d, "title", "") or "")[:40] if d else ""})
        matched = sum(1 for r in ship_rows if r["deal_id"])
        fund = FinModelArticle.objects.filter(name="Логістика / доставка", active=True).first()

        existing = PlannedPayment.objects.filter(kind="payable", comment__icontains=inv).first()
        preview = {
            "invoice_number": inv, "invoice_date": act.get("invoice_date"),
            "contract": act.get("contract"), "amount": amount, "vat": act.get("vat"),
            "counterparty": act.get("counterparty"), "fund": fund.name if fund else None,
            "shipments_count": len(ship_rows), "matched_deals": matched,
            "unmatched": len(ship_rows) - matched, "shipments": ship_rows,
            "checks": act.get("checks"),
            "already_imported": bool(existing),
            "existing_payable_id": existing.id if existing else None,
        }
        commit = str(request.data.get("commit") or "").lower() in ("1", "true", "yes", "on")
        if existing or not commit:
            return Response({"committed": False, **preview})

        # ── COMMIT ──
        due = None
        if act.get("invoice_date"):
            try:
                due = _dt.datetime.strptime(act["invoice_date"], "%d.%m.%Y").date()
            except ValueError:
                due = None
        due = due or _tz.localdate()
        cp = act.get("counterparty") or {}
        detail = "ЄДРПОУ %s · IBAN %s" % (cp.get("edrpou") or "?", cp.get("iban") or "?")
        pp = PlannedPayment.objects.create(
            kind="payable", amount=amount, due_date=due,
            counterparty=(cp.get("name") or "Нова Пошта")[:160],
            fin_article=fund, status="planned",
            comment=("Нова Пошта · акт %s від %s · договір %s · %d відправлень · %s"
                     % (inv, act.get("invoice_date") or "?",
                        (act.get("contract") or {}).get("number", "?"),
                        len(ship_rows), detail))[:255],
        )
        # собівартість доставки по сделкам — в Deal.np_data (без грошової операції)
        deals_updated = 0
        for r in ship_rows:
            if not r["deal_id"]:
                continue
            d = Deal.objects.filter(id=r["deal_id"]).first()
            if not d:
                continue
            nd = d.np_data if isinstance(d.np_data, dict) else {}
            acts = nd.get("delivery_acts") or []
            if any(a.get("act") == inv and a.get("ttn") == r["ttn"] for a in acts):
                continue  # дедуп
            acts.append({"act": inv, "ttn": r["ttn"], "cost": r["cost"],
                         "date": r["date"], "route": r["route"]})
            nd["delivery_acts"] = acts
            nd["delivery_cost_total"] = round(sum(a.get("cost") or 0 for a in acts), 2)
            d.np_data = nd
            d.save(update_fields=["np_data"])
            deals_updated += 1
        return Response({"committed": True, "payable_id": pp.id,
                         "deals_updated": deals_updated, **preview})


FUND_KEYWORDS = [
    (["поставщик", "закупівля товару", "закупка товара", "другие материали", "будмаркет", "будматеріали"], "Постачальники (закупка)"),
    (["доставка", "логистик", "логістик", "нова пошта", "новая почта"], "Логістика / доставка"),
    (["упак"], "Упаковка (матеріали)"),
    (["фот % продажи", "фот % продажу", "% продажи(зп)"], "ФОТ % продажу (комісія менеджера)"),
    (["фот мастера", "мастерам", "майстрам"], "Дивіденди майстрам"),
    (["ликпей", "liqpay"], "Комісія LiqPay"),
    (["чекбокс", "checkbox"], "Комісія Чекбокс"),
    (["маркетинг", "смм", "объявления в соцсетях", "помощьник по маркетингу", "таргетолог", "развитие бренда"], "Маркетинг СММ (контент, копірайт, реклама)"),
    (["фонд управления зп", "управления(зп)", "управління"], "ФОТ управління"),
    (["фот оклады", "фот(зп_оклады)", "уборка", "администратор салона", "бухгалтер"], "ФОТ офіс (склад/менеджер/прибиральниця/бухгалтер)"),
    (["комиссия банка", "комісії банка", "комиссия за перевод", "комісія за поповнення", "користування лімітом", "лiмiто", "обслуговування рахунку", "відсотків"], "Списання відсотків + комісії банку"),
    (["аренда", "оренд"], "Оренда салону"),
    (["возврат тела", "погашение кредита", "повернення тіла"], "Кредити (повернення тіла)"),
    (["коммунальн", "комуналк"], "Комуналка (салон)"),
    (["связь", "звʼязок", "київстар", "киевстар", "телефон", "интернет", "інтернет"], "Звʼязок (Інтернет + телефонія)"),
    (["сервисы", "сервіси", "приложени", "программ", "програм", "netflix", "hetzner", "anthropic", "claude", "chat gpt", "chatplace", "canva", "notion", "midjourney"], "Сервіси / Програми"),
    (["налог", "податк"], "Податки"),
    (["транспорт", "топливо", "паливо", "поездки"], "Транспортні (паливо, поїздки)"),
    (["обслуживание оборуд", "обладнання", "інструмент"], "Обслуговування обладнання / інструментів"),
    (["хоз", "господарськ"], "Господарські витрати"),
    (["жизнедеятельности офиса", "життєдіяльність офісу"], "Життєдіяльність офісу (вода, кава, канцелярія)"),
    (["навчання", "обучение"], "Навчання"),
]


def fund_for_category(cat_name, hint=""):
    """Фонд фінмоделі за назвою категорії (+ контрагент як підказка для таргету)."""
    from .models import FinModelArticle
    hay = ("%s %s" % (cat_name or "", hint or "")).lower()
    if "таргет" in hay:
        nm = ("Таргет-бюджет Facebook (Meta-ads)"
              if ("фейсбук" in hay or "facebook" in hay)
              else "Таргет-бюджет Instagram (Meta-ads)")
        return FinModelArticle.objects.filter(name=nm, active=True).first()
    for keys, fund_name in FUND_KEYWORDS:
        if any(k in hay for k in keys):
            return FinModelArticle.objects.filter(name=fund_name, active=True).first()
    return None


class BankRuleViewSet(viewsets.ModelViewSet):
    """Правила авторозноски банківських операцій. Читати — finance.view; міняти — finance.tx.edit."""
    permission_classes = [FinancePerm]
    from .models import BankRule as _BR
    queryset = _BR.objects.all()
    pagination_class = None

    def perform_create(self, serializer):
        _fin_guard(self.request, "finance.tx.edit", "Правила розноски: потрібне право «Редагувати операції журналу»")
        serializer.save()

    def perform_update(self, serializer):
        _fin_guard(self.request, "finance.tx.edit", "Правила розноски: потрібне право «Редагувати операції журналу»")
        serializer.save()

    def perform_destroy(self, instance):
        _fin_guard(self.request, "finance.tx.edit", "Правила розноски: потрібне право «Редагувати операції журналу»")
        instance.delete()

    def get_serializer_class(self):
        from rest_framework import serializers as _sz
        from .models import BankRule as _BR2

        class S(_sz.ModelSerializer):
            class Meta:
                model = _BR2
                fields = ["id", "name", "direction", "logic", "conditions", "actions",
                          "priority", "active", "hits"]
        return S

    @action(detail=False, methods=["get"], url_path="suggest")
    def suggest(self, request):
        """Відновлення правил з історії (= правила ФінМапа, бо вони цю історію і розносили):
        повторюваний контрагент → домінантна категорія/напрямок. Тільки пропозиції, нічого не створює."""
        from collections import defaultdict
        from .models import BankRule, FinDirection
        existing = set()
        for r in BankRule.objects.all():
            for cnd in (r.conditions or []):
                existing.add((cnd.get("text") or "").strip().lower())
        stats = defaultdict(lambda: defaultdict(int))
        pretty = {}
        # тільки ПОТОЧНИЙ рік — свіжа розноска найточніша (можна ?from=YYYY-MM-DD)
        d_from = request.query_params.get("from") or (date.today().replace(month=1, day=1).isoformat())
        qs = (Transaction.objects.filter(date__gte=d_from)
              .exclude(counterparty="").exclude(direction="transfer")
              .exclude(category__isnull=True).values_list("counterparty", "direction", "category_id", "fin_direction_id"))
        for cp, direction, cat_id, dir_id in qs.iterator(chunk_size=5000):
            cp = (cp or "").strip()
            if len(cp) < 3:
                continue
            key = (cp.lower(), direction)
            stats[key][(cat_id, dir_id)] += 1
            pretty[key] = cp
        out = []
        cat_cache = {c.id: c.name for c in Category.objects.all()}
        dir_cache = {d.id: d.name for d in FinDirection.objects.all()}
        for key, combos in stats.items():
            total = sum(combos.values())
            (cat_id, dir_id), best = max(combos.items(), key=lambda x: x[1])
            if total < 5 or best / total < 0.8 or not cat_id:
                continue
            cp = pretty[key]
            if cp.lower() in existing:
                continue
            fund = fund_for_category(cat_cache.get(cat_id) or "", cp) if key[1] == "out" else None
            out.append({"counterparty": cp, "direction": key[1], "count": total,
                        "share": int(round(best / total * 100)),
                        "category": cat_id, "category_name": cat_cache.get(cat_id),
                        "fin_direction": dir_id, "fin_direction_name": dir_cache.get(dir_id),
                        "fin_article": fund.id if fund else None, "fin_article_name": fund.name if fund else None})
        out.sort(key=lambda x: -x["count"])
        return Response(out[:300])

    @action(detail=False, methods=["post"], url_path="suggest-create")
    def suggest_create(self, request):
        """Створити правила з обраних пропозицій. body: {items: [...]}"""
        from .models import BankRule
        made = 0
        for it in (request.data.get("items") or []):
            cp = (it.get("counterparty") or "").strip()
            actions = {}
            if it.get("category"):
                actions["category"] = int(it["category"])
            if it.get("fin_direction"):
                actions["fin_direction"] = int(it["fin_direction"])
            if it.get("fin_article"):
                actions["fin_article"] = int(it["fin_article"])
            if not cp or not actions:
                continue
            BankRule.objects.create(
                name=("%s → %s" % (cp, it.get("category_name") or ""))[:160],
                direction=it.get("direction") or "", logic="or",
                conditions=[{"field": "counterparty", "op": "contains", "text": cp}],
                actions=actions, active=True)
            made += 1
        return Response({"ok": True, "created": made})

    @action(detail=False, methods=["post"], url_path="apply-journal")
    def apply_journal(self, request):
        """Прогнати правила по журналу: заповнити ПОРОЖНІ поля (нічого не перезаписуємо).
        body: {dry: 1|0, from?: date, to?: date}"""
        dry = str(request.data.get("dry") or "") in ("1", "true", "True")
        if not dry:
            _fin_guard(request, "finance.tx.edit", "Застосування правил до журналу потребує права «Редагувати операції журналу»")
        qs = Transaction.objects.all().select_related("account")
        _cu = _closed_until()
        if _cu:
            qs = qs.filter(date__gt=_cu)  # закритий період не чіпаємо
        if request.data.get("from"):
            qs = qs.filter(date__gte=request.data["from"])
        if request.data.get("to"):
            qs = qs.filter(date__lte=request.data["to"])
        # правила та їх дії — ОДИН раз у памʼять (інакше 20к операцій × запити = таймаут)
        from .models import BankRule as _BRx, FinDirection as _FDx, FinModelArticle as _FAx
        _rules = list(_BRx.objects.filter(active=True))
        _res = {}
        for _r in _rules:
            _a = _r.actions or {}
            _res[_r.id] = {
                "category": Category.objects.filter(id=_a.get("category") or 0).first(),
                "fin_direction": _FDx.objects.filter(id=_a.get("fin_direction") or 0).first(),
                "fin_article": _FAx.objects.filter(id=_a.get("fin_article") or 0).first(),
                "counterparty": _a.get("counterparty") or "", "channel": _a.get("channel") or "",
            }

        def _fast_rules(direction, osnd, cp, acc_name):
            for _r in _rules:
                if _rule_matches(_r, direction, osnd, cp, acc_name):
                    d = dict(_res[_r.id])
                    if not d["counterparty"]:
                        d["counterparty"] = cp
                    return d
            return {"category": None, "fin_direction": None, "fin_article": None, "counterparty": cp, "channel": ""}
        changed = 0
        for tx in qs.iterator(chunk_size=1000):
            rr = _fast_rules(tx.direction, tx.comment or "", tx.counterparty or "",
                             tx.account.name if tx.account_id else "")
            upd = {}
            if rr["category"] and not tx.category_id and tx.direction != "transfer":
                upd["category"] = rr["category"]
            if rr["fin_direction"] and not tx.fin_direction_id:
                upd["fin_direction"] = rr["fin_direction"]
            if rr["fin_article"] and not tx.fin_article_id:
                upd["fin_article"] = rr["fin_article"]
            if rr["counterparty"] and rr["counterparty"] != (tx.counterparty or "") and not (tx.counterparty or "").strip():
                upd["counterparty"] = rr["counterparty"]
            if rr["channel"] and not (tx.channel or "").strip():
                upd["channel"] = rr["channel"]
            if upd:
                changed += 1
                if not dry:
                    for k, v in upd.items():
                        setattr(tx, k, v)
                    tx.save(update_fields=list(upd.keys()))
        return Response({"ok": True, "changed": changed, "dry": dry})


class FinanceDashboardView(APIView):
    permission_classes = [FinancePerm]

    def get(self, request):
        today = date.today()
        month_start = today.replace(day=1)
        tx = Transaction.objects.all()
        month = tx.filter(date__gte=month_start)
        income = month.filter(direction="in").aggregate(s=Sum("amount_uah"))["s"] or 0
        expense = month.filter(direction="out").aggregate(s=Sum("amount_uah"))["s"] or 0
        total_balance = sum(a.balance() for a in Account.objects.all())

        # денежный поток по дням за 30 дней
        days = []
        for i in range(29, -1, -1):
            d = today - timedelta(days=i)
            day_tx = tx.filter(date=d)
            days.append({
                "date": d.isoformat(),
                "in": float(day_tx.filter(direction="in").aggregate(s=Sum("amount_uah"))["s"] or 0),
                "out": float(day_tx.filter(direction="out").aggregate(s=Sum("amount_uah"))["s"] or 0),
            })
        return Response({
            "total_balance": float(total_balance),
            "month_income": float(income),
            "month_expense": float(expense),
            "month_profit": float(income - expense),
            "accounts": AccountSerializer(Account.objects.all(), many=True).data,
            "cashflow": days,
        })


class CashflowSeriesView(APIView):
    """Рух грошей за довільний період. ?from=YYYY-MM-DD&to=YYYY-MM-DD.
    До 92 днів — по днях; довше — по місяцях. Перекази (transfer) не враховуються."""
    permission_classes = [FinancePerm]

    def get(self, request):
        from django.db.models.functions import TruncMonth
        d_from, d_to = _period(request)
        if d_to < d_from:
            d_from, d_to = d_to, d_from
        span = (d_to - d_from).days + 1
        qs = Transaction.objects.filter(date__gte=d_from, date__lte=d_to).exclude(direction="transfer")
        rows = []
        if span <= 92:
            agg = {r["date"]: r for r in qs.values("date", "direction").annotate(s=Sum("amount_uah"))
                   .values("date").annotate(
                       inc=Sum("amount_uah", filter=Q(direction="in")),
                       out=Sum("amount_uah", filter=Q(direction="out")))}
            cur = d_from
            while cur <= d_to:
                a = agg.get(cur) or {}
                i = float(a.get("inc") or 0); o = float(a.get("out") or 0)
                rows.append({"d": cur.isoformat(), "in": i, "out": o, "net": i - o})
                cur += timedelta(days=1)
            gran = "day"
        else:
            agg = {r["m"].date() if hasattr(r["m"], "date") else r["m"]: r
                   for r in qs.annotate(m=TruncMonth("date")).values("m").annotate(
                       inc=Sum("amount_uah", filter=Q(direction="in")),
                       out=Sum("amount_uah", filter=Q(direction="out")))}
            cur = d_from.replace(day=1)
            while cur <= d_to:
                a = agg.get(cur) or {}
                i = float(a.get("inc") or 0); o = float(a.get("out") or 0)
                rows.append({"d": cur.isoformat()[:7], "in": i, "out": o, "net": i - o})
                cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
            gran = "month"
        t_in = sum(r["in"] for r in rows); t_out = sum(r["out"] for r in rows)
        return Response({"granularity": gran, "rows": rows,
                         "totals": {"in": round(t_in), "out": round(t_out), "net": round(t_in - t_out)},
                         "from": d_from.isoformat(), "to": d_to.isoformat()})


def _period(request):
    from datetime import date
    from django.utils import timezone
    from rest_framework.exceptions import ValidationError
    now = timezone.now().date()
    d_from = request.GET.get("from") or now.replace(day=1).isoformat()
    d_to = request.GET.get("to") or now.isoformat()
    try:
        return date.fromisoformat(d_from), date.fromisoformat(d_to)
    except (ValueError, TypeError):
        raise ValidationError({"detail": "Невірний формат дати — очікується YYYY-MM-DD"})


class ProfitLossView(APIView):
    """P&L по ATM (5 уровней) за период."""
    permission_classes = [FinancePerm]

    def get(self, request):
        d_from, d_to = _period(request)
        return Response({"from": d_from.isoformat(), "to": d_to.isoformat(), **compute_pnl(d_from, d_to)})


class BreakevenView(APIView):
    """Точка беззбитковості: рахується ВІД ФІНМОДЕЛІ (нормативи затрат і маржі),
    факт поточного місяця — лише для прогресу. Період не обирається."""
    permission_classes = [FinancePerm]

    def get(self, request):
        import calendar
        today = date.today()
        d_from = today.replace(day=1)
        d_to = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        return Response({"from": d_from.isoformat(), "to": d_to.isoformat(), **compute_breakeven(d_from, d_to)})


class FinDirectionViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        qs = super().get_queryset()
        allowed = self.request.user.allowed_fin("fin_dirs")
        return qs if allowed is None else qs.filter(id__in=allowed)

    def perform_create(self, serializer):
        _fin_guard(self.request, "finance.dirs.manage", "Немає права створювати напрямки")
        serializer.save()

    def perform_update(self, serializer):
        _fin_guard(self.request, "finance.dirs.manage", "Немає права редагувати напрямки")
        serializer.save()

    def perform_destroy(self, instance):
        _fin_guard(self.request, "finance.dirs.manage", "Немає права видаляти напрямки")
        instance.delete()

    queryset = FinDirection.objects.all()
    serializer_class = FinDirectionSerializer
    permission_classes = [FinDirectionPerm]


def _direction_sums(dr, d_from, d_to):
    """Доходи/витрати напрямку З УРАХУВАННЯМ розподілу (splits):
    операції БЕЗ розподілу — по власному fin_direction; операції З розподілом — по частках splits
    (щоб спільна витрата ділилась між підрозділами, а не висіла на одному)."""
    from .models import TransactionSplit as _TS
    base = Transaction.objects.filter(fin_direction=dr, date__gte=d_from, date__lte=d_to, splits__isnull=True)
    inc = float(base.filter(direction="in").aggregate(s=Sum("amount_uah"))["s"] or 0)
    exp = float(base.filter(direction="out").aggregate(s=Sum("amount_uah"))["s"] or 0)
    sp = _TS.objects.filter(fin_direction=dr, transaction__date__gte=d_from, transaction__date__lte=d_to)
    inc += float(sp.filter(transaction__direction="in").aggregate(s=Sum("amount"))["s"] or 0)
    exp += float(sp.filter(transaction__direction="out").aggregate(s=Sum("amount"))["s"] or 0)
    return inc, exp


class DirectionsReportView(APIView):
    """Звіт по напрямках (як Finmap Проекти): доходи/витрати/прибуток/рентабельність + план/факт."""
    permission_classes = [FinancePerm]

    def get(self, request):
        d_from, d_to = _period(request)
        rows = []
        for dr in FinDirection.objects.filter(active=True):
            inc, exp = _direction_sums(dr, d_from, d_to)
            profit = inc - exp
            rows.append({
                "id": dr.id, "name": dr.name,
                "income": round(inc), "expense": round(exp), "profit": round(profit),
                "profitability": round(profit / inc * 100, 1) if inc else 0,
                "plan_income": float(dr.plan_income), "plan_expense": float(dr.plan_expense),
                "plan_profit": float(dr.plan_income - dr.plan_expense),
            })
        total = {
            "income": sum(r["income"] for r in rows), "expense": sum(r["expense"] for r in rows),
            "profit": sum(r["profit"] for r in rows),
            "plan_income": sum(r["plan_income"] for r in rows),
            "plan_expense": sum(r["plan_expense"] for r in rows),
        }
        return Response({"from": d_from.isoformat(), "to": d_to.isoformat(), "rows": rows, "total": total})


class ChannelSpendSerializer_(__import__("rest_framework").serializers.ModelSerializer):
    class Meta:
        model = ChannelSpend
        fields = ["id", "channel", "period", "spend", "src"]


class ChannelSpendViewSet(viewsets.ModelViewSet):
    queryset = ChannelSpend.objects.all()
    serializer_class = ChannelSpendSerializer_
    permission_classes = [FinanceManagePerm]
    filterset_fields = ["channel", "period"]


class ChannelsView(APIView):
    """Доход по каналах (для росту доходу): /api/finance/channels/?from&to."""
    permission_classes = [FinancePerm]

    def get(self, request):
        d_from, d_to = _period(request)
        return Response({"from": d_from.isoformat(), "to": d_to.isoformat(), **compute_channels(d_from, d_to)})


class FundAllocationViewSet(viewsets.ModelViewSet):
    queryset = FundAllocation.objects.select_related("fund", "account", "fin_direction")
    serializer_class = FundAllocationSerializer
    permission_classes = [FinancePerm]
    filterset_fields = ["fund", "account", "fin_direction", "period"]


_GROUP_META = [
    ("revenue", "📊 Фонди виручки (ФВ)", "#2563eb"),
    ("margin", "💎 Фонди маржі (ФМ)", "#7c3aed"),
    ("skd", "🎯 Фонди СКД (ФСКД)", "#059669"),
    ("upr", "🏛 Управлінські (УПР)", "#475569"),
    ("other", "⚙️ Інше", "#64748b"),
]


def _fund_stats(period):
    """Для кожного фонду: розподілено (allocations) − витрачено (Transaction out) = залишок."""
    alloc = {r["fund"]: float(r["s"]) for r in
             FundAllocation.objects.filter(period=period).values("fund").annotate(s=Sum("amount"))}
    spent = {}
    y, mo = int(period[:4]), int(period[5:7])
    for r in (Transaction.objects.filter(direction="out", fin_article__isnull=False,
                                          date__year=y, date__month=mo)
              .values("fin_article").annotate(s=Sum("amount_uah"))):
        spent[r["fin_article"]] = float(r["s"])
    return alloc, spent


class FundsView(APIView):
    """Планування по фондах-конвертах: залишок у кожному фонді (ФВ→ФМ→ФСКД)."""
    permission_classes = [FinancePerm]

    def get(self, request):
        period = request.query_params.get("period") or date.today().strftime("%Y-%m")
        alloc, spent = _fund_stats(period)

        def node(a):
            al = alloc.get(a.id, 0.0)
            sp = spent.get(a.id, 0.0)
            return {"id": a.id, "name": a.name, "category": a.category, "fund_group": a.fund_group,
                    "margin_kind": a.margin_kind, "is_envelope": a.is_envelope,
                    "value": float(a.value), "value_type": a.value_type,
                    "allocated": round(al), "spent": round(sp), "balance": round(al - sp),
                    "subfunds": [node(s) for s in a.subfunds.all()]}

        arts = list(FinModelArticle.objects.filter(active=True, parent__isnull=True).prefetch_related("subfunds"))
        groups = []
        for key, label, color in _GROUP_META:
            funds = [node(a) for a in arts if a.fund_group == key]
            if funds:
                groups.append({"key": key, "label": label, "color": color, "funds": funds})
        accounts_qs = Account.objects.filter(is_active=True)
        try:
            _allowed = request.user.allowed_fin("fin_accounts")
        except Exception:
            _allowed = None
        if _allowed is not None:
            accounts_qs = accounts_qs.filter(id__in=_allowed)
        accounts = [{"id": ac.id, "name": ac.name, "in_planning": ac.in_planning, "balance": round(float(ac.balance()), 2)} for ac in accounts_qs]
        tot_al = sum(alloc.values()); tot_sp = sum(spent.values())
        return Response({"period": period, "groups": groups, "accounts": accounts,
                         "totals": {"allocated": round(tot_al), "spent": round(tot_sp), "balance": round(tot_al - tot_sp)}})

    def post(self, request):
        """Авто-розподіл виручки по фондах виручки: кожен ФВ отримує value% від суми.
        body: {account, period, revenue, fin_direction?}"""
        period = request.data.get("period") or date.today().strftime("%Y-%m")
        revenue = float(request.data.get("revenue") or 0)
        account_id = request.data.get("account")
        direction_id = request.data.get("fin_direction")
        # ідемпотентність: прибрати попередній авто-розподіл цього періоду (повторний клік не дублює)
        FundAllocation.objects.filter(period=period, comment__startswith="Авто-розподіл виручки").delete()
        created = []
        for a in FinModelArticle.objects.filter(active=True, category="revenue_fund", value_type="percent"):
            amt = round(revenue * float(a.value) / 100, 2)
            if amt <= 0:
                continue
            FundAllocation.objects.create(fund=a, account_id=account_id, fin_direction_id=direction_id,
                                          amount=amt, period=period, comment=f"Авто-розподіл виручки {revenue:.0f}₴")
            created.append({"fund": a.name, "amount": amt})
        return Response({"created": created})


from rest_framework import serializers as _sz


class ManagerPlanSerializer(_sz.ModelSerializer):
    user_name = _sz.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = ManagerPlan
        fields = ["id", "user", "user_name", "period", "min_revenue", "target_revenue", "ambition_revenue"]


class ManagerPlanViewSet(viewsets.ModelViewSet):
    queryset = ManagerPlan.objects.select_related("user")
    serializer_class = ManagerPlanSerializer
    permission_classes = [FinancePerm]
    filterset_fields = ["user", "period"]


def _sales_team():
    """Менеджери, які мають угоди або право продажів."""
    from apps.crm.models import Deal
    from django.contrib.auth import get_user_model
    User = get_user_model()
    ids = set(Deal.objects.exclude(owner__isnull=True).values_list("owner_id", flat=True))
    return User.objects.filter(id__in=ids) if ids else User.objects.filter(is_active=True)[:10]


class SalaryView(APIView):
    """ЗП/KPI менеджерів за місяць (стратегія РОП+психолог). /api/finance/salary/?period=YYYY-MM[&user=ID]"""
    permission_classes = [FinancePerm]

    def get(self, request):
        from .services import compute_manager_salary, compute_breakeven
        period = request.query_params.get("period") or date.today().strftime("%Y-%m")
        uid = request.query_params.get("user")
        if uid:
            from django.contrib.auth import get_user_model
            u = get_user_model().objects.filter(id=uid).first()
            if not u:
                return Response({})
            me = request.user  # #12 чужу ЗП — лише свій відділ або керівник
            same_dept = getattr(u, "department_id", None) and u.department_id == getattr(me, "department_id", None)
            if str(u.id) != str(me.id) and not (me.is_superuser or me.has_perm_code("roles.manage") or same_dept):
                return Response({"detail": "Немає доступу до ЗП цього співробітника."}, status=403)
            return Response(compute_manager_salary(u, period))
        rows = [compute_manager_salary(u, period) for u in _sales_team()]
        rows.sort(key=lambda r: r["revenue"], reverse=True)
        # покриття цілі компанії
        y, mo = int(period[:4]), int(period[5:7])
        d_from = date(y, mo, 1)
        d_to = date(y + (mo // 12), (mo % 12) + 1, 1) - timedelta(days=1)
        be = compute_breakeven(d_from, d_to)
        company_target = round(be.get("breakeven", 0) * 1.3)
        sum_targets = sum(r["plan_target"] or 0 for r in rows)
        return Response({
            "period": period, "rows": rows,
            "company": {"breakeven": be.get("breakeven", 0), "target": company_target,
                        "sum_plans": sum_targets,
                        "coverage_pct": round(sum_targets / company_target * 100) if company_target else 0,
                        "total_payroll": sum(r["total"] for r in rows)},
        })


class AdvisoryReportViewSet(viewsets.ModelViewSet):
    """Звіти радчої системи (план зростання прибутку). Читають усі з finance.view."""
    queryset = AdvisoryReport.objects.all()
    serializer_class = AdvisoryReportSerializer
    permission_classes = [FinancePerm]
    filterset_fields = ["kind"]


class FxRateView(APIView):
    """Живий курс валют від НБУ (bank.gov.ua) — UAH за 1 одиницю валюти.
    GET /api/finance/fx-rate/?ccy=USD  → {ccy, rate, date}."""
    permission_classes = [FinancePerm]

    def get(self, request):
        import json as _json, urllib.request
        ccy = (request.query_params.get("ccy") or "USD").upper()
        if ccy == "UAH":
            return Response({"ccy": "UAH", "rate": 1.0, "date": date.today().isoformat()})
        url = f"https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode={ccy}&json"
        try:
            with urllib.request.urlopen(url, timeout=12) as r:
                data = _json.load(r)
            if not data:
                return Response({"ccy": ccy, "rate": None, "detail": "немає курсу"}, status=404)
            row = data[0]
            return Response({"ccy": ccy, "rate": float(row.get("rate") or 0), "date": row.get("exchangedate", "")})
        except Exception as e:
            return Response({"ccy": ccy, "rate": None, "detail": str(e)}, status=502)


class AttachmentFileView(APIView):
    """Віддає байти файлу-вкладення (авторизовано). GET /api/attachments/<id>/file/."""
    permission_classes = [FinancePerm]

    def get(self, request, pk):
        try:
            a = TransactionAttachment.objects.get(pk=pk)
        except TransactionAttachment.DoesNotExist:
            return Response({"detail": "не знайдено"}, status=status.HTTP_404_NOT_FOUND)
        resp = HttpResponse(bytes(a.data), content_type=a.content_type)
        resp["Content-Disposition"] = f'inline; filename="{a.filename}"'
        return resp

    def delete(self, request, pk):
        TransactionAttachment.objects.filter(pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FxImpactView(APIView):
    """Вплив курсу валют на прибуток + рекомендації.
    Закупка декор-матеріалів привʼязана до валюти → падіння гривні зʼїдає маржу.
    GET /api/finance/fx-impact/?ccy=USD&from&to"""
    permission_classes = [FinancePerm]

    def get(self, request):
        import json as _json, urllib.request
        ccy = (request.query_params.get("ccy") or "USD").upper()
        d_from, d_to = _period(request)

        # живий курс НБУ
        live = None
        try:
            with urllib.request.urlopen(f"https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode={ccy}&json", timeout=10) as r:
                data = _json.load(r)
            live = float(data[0]["rate"]) if data else None
        except Exception:
            live = None

        # витрати у цій валюті за період
        fx = Transaction.objects.filter(direction="out", currency=ccy,
                                        date__gte=d_from, date__lte=d_to)
        fx_orig = float(fx.aggregate(s=Sum("amount"))["s"] or 0)
        fx_uah = float(fx.aggregate(s=Sum("amount_uah"))["s"] or 0)

        # частка постачальників (імпорт-залежна) з фінмоделі — найбільший revenue_fund
        sup = FinModelArticle.objects.filter(active=True, category="revenue_fund").order_by("-value").first()
        supplier_pct = float(sup.value) if sup else 48.78
        pnl = compute_pnl(d_from, d_to)
        revenue = pnl["revenue"]
        supplier_cost = revenue * supplier_pct / 100.0  # імпорт-залежна частина собівартості

        # сценарії руху курсу: наскільки впаде прибуток
        scenarios = []
        for delta in (5, 10, 15, -5):
            extra_cost = supplier_cost * delta / 100.0  # подорожчання закупки
            new_margin_pct = pnl["margin_pct"] - (extra_cost / revenue * 100.0 if revenue else 0)
            scenarios.append({
                "delta_pct": delta,
                "extra_cost": round(extra_cost),
                "profit_change": round(-extra_cost),
                "new_margin_pct": round(new_margin_pct, 1),
            })

        recs = [
            f"Закупка завʼязана на курс: постачальники ≈ {supplier_pct:.0f}% виручки. Падіння гривні на 10% зʼїдає ≈ {round(supplier_cost*0.10):,} ₴ прибутку/період.".replace(",", " "),
            "Додавай у договір/КП курсове застереження: ціна фіксується за курсом на день відвантаження, а не замовлення.",
            "Тримай резерв 5-10% маржі на курсові коливання — не давай знижки, що зʼїдають цей буфер.",
            "При падінні гривні на >5% — оновлюй прайс або закуповуй ходові позиції наперед (валютна подушка).",
            "Частину виручки тримай у валюті — природний хедж проти подорожчання закупки.",
        ]
        return Response({
            "ccy": ccy, "live_rate": live, "from": d_from.isoformat(), "to": d_to.isoformat(),
            "fx_expense_orig": round(fx_orig), "fx_expense_uah": round(fx_uah),
            "supplier_pct": round(supplier_pct, 2), "supplier_cost": round(supplier_cost),
            "revenue": round(revenue), "margin_pct": pnl["margin_pct"],
            "scenarios": scenarios, "recommendations": recs,
        })


class CounterpartiesView(APIView):
    """Контрагенти. Якщо у співробітника позначені дозволені — бачить лише їх."""

    """Довідник контрагентів — зведення з операцій (унікальні + к-сть + сума).
    GET /api/finance/counterparties/"""
    permission_classes = [FinancePerm]

    def get(self, request):
        from django.db.models import Count, Sum
        qs = Transaction.objects.exclude(counterparty="")
        allowed = request.user.allowed_fin("fin_counterparties")
        if allowed is not None:
            qs = qs.filter(counterparty__in=allowed)
        rows = (qs.values("counterparty")
                .annotate(n=Count("id"), total=Sum("amount_uah"))
                .order_by("-n"))
        # звʼязок із клієнтами CRM (по імені/назві)
        from apps.crm.models import Contact
        contact_names = {str(c).strip().lower(): c.id for c in Contact.objects.all()}
        out = []
        for r in rows:
            nm = r["counterparty"]
            out.append({"name": nm, "count": r["n"], "total": round(float(r["total"] or 0)),
                        "contact_id": contact_names.get(nm.strip().lower())})
        return Response(out)


class WorkDaySerializer(_sz.ModelSerializer):
    class Meta:
        model = WorkDay
        fields = ["id", "user", "date", "status", "note"]


class WorkDayViewSet(viewsets.ModelViewSet):
    queryset = WorkDay.objects.select_related("user")
    serializer_class = WorkDaySerializer
    permission_classes = [FinancePerm]
    filterset_fields = ["user", "status"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("year") and p.get("month"):
            qs = qs.filter(date__year=p["year"], date__month=p["month"])
        return qs

    @action(detail=False, methods=["post"])
    def set(self, request):
        """Upsert статусу дня: {user, date, status}."""
        uid = request.data.get("user"); d = request.data.get("date"); st = request.data.get("status")
        if not (uid and d):
            return Response({"detail": "user+date обовʼязкові"}, status=status.HTTP_400_BAD_REQUEST)
        if st in (None, "", "clear"):
            WorkDay.objects.filter(user_id=uid, date=d).delete()
            return Response({"cleared": True})
        obj, _ = WorkDay.objects.update_or_create(user_id=uid, date=d, defaults={"status": st})
        return Response(WorkDaySerializer(obj).data)


class OverviewView(APIView):
    """Зведений дашборд (FP&A): світлофор, тренд, топ-витрати, напрямки, рахунки, коеф., алерти.
    GET /api/finance/overview/?period=YYYY-MM"""
    permission_classes = [FinancePerm]

    def get(self, request):
        from datetime import date as _date, timedelta as _td
        from django.db.models import Sum
        per = request.query_params.get("period") or _date.today().strftime("%Y-%m")
        y, mo = int(per[:4]), int(per[5:7])
        q_from, q_to = request.query_params.get("from"), request.query_params.get("to")

        def month_bounds(yy, mm):
            f = _date(yy, mm, 1)
            t = (_date(yy + (mm == 12), (mm % 12) + 1, 1) - _td(days=1))
            return f, t

        def sums(f, t):
            q = Transaction.objects.filter(date__gte=f, date__lte=t)
            inc = float(q.filter(direction="in").aggregate(s=Sum("amount_uah"))["s"] or 0)
            exp = float(q.filter(direction="out").aggregate(s=Sum("amount_uah"))["s"] or 0)
            return inc, exp

        # тренд 12 місяців до обраного
        months = []
        yy, mm = y, mo
        seq = []
        for _ in range(12):
            seq.append((yy, mm))
            mm -= 1
            if mm == 0:
                mm = 12; yy -= 1
        for (a, b) in reversed(seq):
            f, t = month_bounds(a, b)
            inc, exp = sums(f, t)
            months.append({"ym": f"{a}-{b:02d}", "income": round(inc), "expense": round(exp), "net": round(inc - exp)})

        if q_from and q_to:
            try:
                cf, ct = _date.fromisoformat(q_from), _date.fromisoformat(q_to)
                if ct < cf:
                    cf, ct = ct, cf
            except (ValueError, TypeError):
                cf, ct = month_bounds(y, mo)
            span_days = (ct - cf).days + 1
            pf, pt = cf - _td(days=span_days), cf - _td(days=1)
        else:
            cf, ct = month_bounds(y, mo)
            pf, pt = month_bounds(*seq[1])
        cur_inc, cur_exp = sums(cf, ct)
        prev_inc, prev_exp = sums(pf, pt)
        total_balance = sum(float(a.balance()) for a in Account.objects.filter(is_active=True))

        # топ-витрати (обраний місяць)
        top_exp = [{"name": r["category__name"] or "(без категорії)", "sum": round(float(r["s"]))}
                   for r in Transaction.objects.filter(direction="out", date__gte=cf, date__lte=ct)
                   .values("category__name").annotate(s=Sum("amount_uah")).order_by("-s")[:8]]

        # напрямки (обраний місяць)
        dirs = []
        for d in FinDirection.objects.filter(active=True):
            di, de = _direction_sums(d, cf, ct)
            if di or de:
                dirs.append({"name": d.name, "income": round(di), "expense": round(de), "net": round(di - de)})
        dirs.sort(key=lambda x: -x["income"])

        # рахунки
        accounts = sorted([{"id": a.id, "name": a.name, "balance": round(float(a.balance()), 2)}
                           for a in Account.objects.filter(is_active=True)], key=lambda x: -x["balance"])

        # cashflow 30 днів
        today = _date.today()
        cashflow = []
        for i in range(29, -1, -1):
            dd = today - _td(days=i)
            dq = Transaction.objects.filter(date=dd)
            cashflow.append({"date": dd.isoformat(),
                             "in": float(dq.filter(direction="in").aggregate(s=Sum("amount"))["s"] or 0),
                             "out": float(dq.filter(direction="out").aggregate(s=Sum("amount"))["s"] or 0)})

        # надходження по категоріях (за період)
        by_cat_in = [{"name": r["category__name"] or "(без категорії)", "sum": round(float(r["s"]))}
                     for r in Transaction.objects.filter(direction="in", date__gte=cf, date__lte=ct)
                     .values("category__name").annotate(s=Sum("amount_uah")).order_by("-s")[:10]]

        # серія руху грошей за період: ≤92 днів — по днях, інакше по місяцях
        from django.db.models.functions import TruncMonth
        ser_q = Transaction.objects.filter(date__gte=cf, date__lte=ct).exclude(direction="transfer")
        span = (ct - cf).days + 1
        srows = []
        if span <= 92:
            agg = {r["date"]: r for r in ser_q.values("date").annotate(
                inc=Sum("amount_uah", filter=Q(direction="in")),
                out=Sum("amount_uah", filter=Q(direction="out")))}
            cur = cf
            while cur <= ct:
                a = agg.get(cur) or {}
                i2 = float(a.get("inc") or 0); o2 = float(a.get("out") or 0)
                srows.append({"d": cur.isoformat(), "in": i2, "out": o2, "net": i2 - o2})
                cur += _td(days=1)
            gran = "day"
        else:
            agg = {(r["m"].date() if hasattr(r["m"], "date") else r["m"]): r
                   for r in ser_q.annotate(m=TruncMonth("date")).values("m").annotate(
                       inc=Sum("amount_uah", filter=Q(direction="in")),
                       out=Sum("amount_uah", filter=Q(direction="out")))}
            cur = cf.replace(day=1)
            while cur <= ct:
                a = agg.get(cur) or {}
                i2 = float(a.get("inc") or 0); o2 = float(a.get("out") or 0)
                srows.append({"d": cur.isoformat()[:7], "in": i2, "out": o2, "net": i2 - o2})
                cur = (cur.replace(day=28) + _td(days=4)).replace(day=1)
            gran = "month"

        # коефіцієнти
        net = cur_inc - cur_exp
        margin_pct = round(net / cur_inc * 100, 1) if cur_inc else 0
        exp_ratio = round(cur_exp / cur_inc * 100, 1) if cur_inc else 0
        personal = next((c["sum"] for c in top_exp if "особ" in c["name"].lower() or "личн" in c["name"].lower()), 0)
        personal_pct = round(personal / cur_exp * 100, 1) if cur_exp else 0
        avg_burn = sum(max(0, m["expense"] - m["income"]) for m in months[-3:]) / 3
        burn_months = round(total_balance / avg_burn, 1) if avg_burn > 0 else None

        # алерти
        alerts = []
        losing = sum(1 for m in months[-6:] if m["net"] < 0)
        if losing >= 2:
            alerts.append({"level": "warn", "text": f"{losing} збиткових місяці з останніх 6 — нестабільний прибуток"})
        if personal_pct >= 10:
            alerts.append({"level": "danger", "text": f"Особисті витрати = {personal_pct}% усіх витрат місяця ({money_fmt(personal)})"})
        mk = next((c["sum"] for c in top_exp if "маркет" in c["name"].lower()), 0)
        if cur_inc and mk / cur_inc * 100 >= 12:
            alerts.append({"level": "warn", "text": f"Маркетинг {round(mk/cur_inc*100)}% від виручки — перевір окупність (ROI)"})
        for a in accounts:
            if -100 < a["balance"] < 500 and a["balance"] != 0:
                alerts.append({"level": "warn", "text": f"Рахунок «{a['name']}» майже порожній ({money_fmt(a['balance'])})"})
                break
        if net < 0:
            alerts.append({"level": "danger", "text": f"Поточний місяць у мінусі: {money_fmt(net)}"})
        if not alerts:
            alerts.append({"level": "ok", "text": "Критичних сигналів немає — бізнес у нормі"})

        return Response({
            "period": per,
            "kpi": {"income": round(cur_inc), "expense": round(cur_exp), "net": round(net),
                    "prev_net": round(prev_inc - prev_exp), "balance": round(total_balance)},
            "months": months, "top_expense": top_exp, "directions": dirs,
            "accounts": accounts, "cashflow": cashflow,
            "by_cat_in": by_cat_in, "series": {"granularity": gran, "rows": srows},
            "from": cf.isoformat(), "to": ct.isoformat(),
            "ratios": {"margin_pct": margin_pct, "expense_ratio": exp_ratio,
                       "personal_pct": personal_pct, "burn_months": burn_months},
            "alerts": alerts,
        })


def money_fmt(n):
    return f"{round(n):,}".replace(",", " ") + " ₴"


class WorkTimeView(APIView):
    """Таймер робочого дня. GET → поточна зміна; POST {action: start|pause|stop}."""
    from rest_framework.permissions import IsAuthenticated as _IsAuth
    permission_classes = [_IsAuth]

    def _payload(self, ws):
        if not ws:
            return {"active": False}
        return {"active": True, "id": ws.id, "started_at": ws.started_at,
                "on_pause": bool(ws.paused_at), "paused_seconds": ws.paused_seconds,
                "worked_seconds": ws.worked_seconds()}

    def get(self, request):
        ws = WorkSession.objects.filter(user=request.user, ended_at__isnull=True).first()
        return Response(self._payload(ws))

    def post(self, request):
        from django.utils import timezone
        from datetime import date as _date
        action = request.data.get("action")
        ws = WorkSession.objects.filter(user=request.user, ended_at__isnull=True).first()
        if action == "start":
            if not ws:
                ws = WorkSession.objects.create(user=request.user)
                WorkDay.objects.update_or_create(user=request.user, date=_date.today(), defaults={"status": "worked"})
        elif action == "pause" and ws:
            if ws.paused_at:
                ws.paused_seconds += int((timezone.now() - ws.paused_at).total_seconds()); ws.paused_at = None
            else:
                ws.paused_at = timezone.now()
            ws.save()
        elif action == "stop" and ws:
            if ws.paused_at:
                ws.paused_seconds += int((timezone.now() - ws.paused_at).total_seconds()); ws.paused_at = None
            ws.ended_at = timezone.now(); ws.save()
            return Response({"active": False, "worked_seconds": ws.worked_seconds()})
        return Response(self._payload(ws))
