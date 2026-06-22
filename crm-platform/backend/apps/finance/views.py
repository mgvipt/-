from datetime import date, timedelta
from django.db.models import Sum, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.common.permissions import HasPermCode
from .models import Account, Category, Transaction, FinModelArticle, FinDirection, ChannelSpend, FundAllocation, AdvisoryReport, TransactionAttachment, ManagerPlan
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


class FinModelArticleViewSet(viewsets.ModelViewSet):
    queryset = FinModelArticle.objects.all()
    serializer_class = FinModelArticleSerializer
    permission_classes = [FinanceManagePerm]
    filterset_fields = ["category", "active"]


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [FinancePerm]


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [FinancePerm]


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related("account", "category", "deal", "fin_direction", "fin_article")
    serializer_class = TransactionSerializer
    permission_classes = [FinancePerm]
    filterset_fields = ["direction", "account", "category", "deal", "fin_direction", "fin_article", "channel"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("from"):
            qs = qs.filter(created_at__date__gte=p["from"])
        if p.get("to"):
            qs = qs.filter(created_at__date__lte=p["to"])
        return qs

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


class FinanceDashboardView(APIView):
    permission_classes = [FinancePerm]

    def get(self, request):
        today = date.today()
        month_start = today.replace(day=1)
        tx = Transaction.objects.all()
        month = tx.filter(created_at__date__gte=month_start)
        income = month.filter(direction="in").aggregate(s=Sum("amount"))["s"] or 0
        expense = month.filter(direction="out").aggregate(s=Sum("amount"))["s"] or 0
        total_balance = sum(a.balance() for a in Account.objects.all())

        # денежный поток по дням за 30 дней
        days = []
        for i in range(29, -1, -1):
            d = today - timedelta(days=i)
            day_tx = tx.filter(created_at__date=d)
            days.append({
                "date": d.isoformat(),
                "in": float(day_tx.filter(direction="in").aggregate(s=Sum("amount"))["s"] or 0),
                "out": float(day_tx.filter(direction="out").aggregate(s=Sum("amount"))["s"] or 0),
            })
        return Response({
            "total_balance": float(total_balance),
            "month_income": float(income),
            "month_expense": float(expense),
            "month_profit": float(income - expense),
            "accounts": AccountSerializer(Account.objects.all(), many=True).data,
            "cashflow": days,
        })


def _period(request):
    from datetime import date
    from django.utils import timezone
    now = timezone.now().date()
    d_from = request.GET.get("from") or now.replace(day=1).isoformat()
    d_to = request.GET.get("to") or now.isoformat()
    return date.fromisoformat(d_from), date.fromisoformat(d_to)


class ProfitLossView(APIView):
    """P&L по ATM (5 уровней) за период."""
    permission_classes = [FinancePerm]

    def get(self, request):
        d_from, d_to = _period(request)
        return Response({"from": d_from.isoformat(), "to": d_to.isoformat(), **compute_pnl(d_from, d_to)})


class BreakevenView(APIView):
    """Точка безубыточности + прогресс + форекаст за период."""
    permission_classes = [FinancePerm]

    def get(self, request):
        d_from, d_to = _period(request)
        return Response({"from": d_from.isoformat(), "to": d_to.isoformat(), **compute_breakeven(d_from, d_to)})


class FinDirectionViewSet(viewsets.ModelViewSet):
    queryset = FinDirection.objects.all()
    serializer_class = FinDirectionSerializer
    permission_classes = [FinanceManagePerm]


class DirectionsReportView(APIView):
    """Звіт по напрямках (як Finmap Проекти): доходи/витрати/прибуток/рентабельність + план/факт."""
    permission_classes = [FinancePerm]

    def get(self, request):
        d_from, d_to = _period(request)
        rows = []
        for dr in FinDirection.objects.filter(active=True):
            tx = Transaction.objects.filter(fin_direction=dr,
                created_at__date__gte=d_from, created_at__date__lte=d_to)
            inc = float(tx.filter(direction="in").aggregate(s=Sum("amount"))["s"] or 0)
            exp = float(tx.filter(direction="out").aggregate(s=Sum("amount"))["s"] or 0)
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
                                          created_at__year=y, created_at__month=mo)
              .values("fin_article").annotate(s=Sum("amount"))):
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
        accounts = [{"id": ac.id, "name": ac.name, "balance": round(float(ac.balance()))} for ac in Account.objects.filter(is_active=True)]
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
            return Response(compute_manager_salary(u, period) if u else {})
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
                                        created_at__date__gte=d_from, created_at__date__lte=d_to)
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
