from rest_framework import serializers
from .models import FinModelArticle, FinDirection, Account, Category, Transaction, FundAllocation, AdvisoryReport


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ["id", "name", "kind", "is_active", "in_planning", "balance", "sort_order"]

    def get_balance(self, obj):
        return obj.balance()


class CategorySerializer(serializers.ModelSerializer):
    fin_article_name = serializers.CharField(source="fin_article.name", read_only=True, default="")
    fin_direction_name = serializers.CharField(source="fin_direction.name", read_only=True, default="")

    class Meta:
        model = Category
        fields = ["id", "name", "direction", "parent", "fin_article", "fin_article_name",
                  "fin_direction", "fin_direction_name", "hidden", "sort_order"]


class PlannedPaymentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    contact_name = serializers.SerializerMethodField()

    def get_contact_name(self, obj):
        c = obj.contact
        if not c:
            return ""
        return (getattr(c, "display_name", "") or
                (" ".join(filter(None, [c.first_name, c.last_name])).strip()) or
                c.nickname or c.phone or ("#%d" % c.id))
    account_name = serializers.CharField(source="account.name", read_only=True, default=None)
    fin_direction_name = serializers.CharField(source="fin_direction.name", read_only=True, default=None)
    fin_article_name = serializers.CharField(source="fin_article.name", read_only=True, default=None)
    deal_title = serializers.CharField(source="deal.title", read_only=True, default=None)
    paid_date = serializers.DateField(source="paid_tx.date", read_only=True, default=None)
    paid_account_name = serializers.CharField(source="paid_tx.account.name", read_only=True, default=None)
    remaining = serializers.SerializerMethodField()
    source_doc_id = serializers.SerializerMethodField()

    def get_remaining(self, obj):
        return round(float(obj.amount or 0) - float(obj.paid_amount or 0), 2)

    def get_source_doc_id(self, obj):
        try:
            from apps.integrations.models import IncomingDoc
            return IncomingDoc.objects.filter(created_payable_id=obj.id).values_list("id", flat=True).first()
        except Exception:
            return None

    class Meta:
        from .models import PlannedPayment
        model = PlannedPayment
        fields = ["id", "kind", "amount", "due_date", "counterparty", "contact", "contact_name", "category", "category_name",
                  "account", "account_name", "fin_direction", "fin_direction_name",
                  "fin_article", "fin_article_name", "channel", "deal", "deal_title",
                  "comment", "status", "paid_amount", "remaining", "source_doc_id", "paid_date", "paid_account_name", "is_loan", "is_internal", "counterparty_contact",
                  "source_transaction", "source_planned", "created_at"]


class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    category_path = serializers.SerializerMethodField()
    splits = serializers.SerializerMethodField()
    payer_direction_name = serializers.CharField(source="payer_direction.name", read_only=True, default="")
    contact_name = serializers.SerializerMethodField()

    def get_splits(self, obj):
        return [{"fin_direction": s.fin_direction_id, "fin_direction_name": (s.fin_direction.name if s.fin_direction_id else ""),
                 "category": s.category_id, "category_name": (s.category.name if s.category_id else ""),
                 "amount": float(s.amount)} for s in obj.splits.all()]

    def get_category_path(self, obj):
        c = obj.category
        if not c:
            return ""
        return ("%s → %s" % (c.parent.name, c.name)) if c.parent_id else c.name

    def get_contact_name(self, obj):
        c = obj.contact
        if not c:
            return ""
        return (getattr(c, "display_name", "") or
                (" ".join(filter(None, [c.first_name, c.last_name])).strip()) or
                c.nickname or c.phone or ("#%d" % c.id))
    category_name = serializers.CharField(source="category.name", read_only=True)
    set_category = serializers.CharField(write_only=True, required=False, allow_blank=True,
        help_text="Назва категорії текстом — знайде або створить")

    def _resolve_category(self, validated):
        name = (validated.pop("set_category", "") or "").strip()
        if name:
            direction = validated.get("direction") or getattr(self.instance, "direction", None) or "out"
            # спершу точний збіг за напрямком (одна назва може бути і в доході, і в витраті),
            # інакше будь-яка з такою назвою, інакше створюємо
            cat = (Category.objects.filter(name=name, direction=direction).first()
                   or Category.objects.filter(name=name).order_by("id").first())
            if not cat:
                cat = Category.objects.create(name=name, direction=direction)
            validated["category"] = cat

    def create(self, validated_data):
        self._resolve_category(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._resolve_category(validated_data)
        return super().update(instance, validated_data)
    fin_article_name = serializers.CharField(source="fin_article.name", read_only=True, default="")
    fin_direction_name = serializers.CharField(source="fin_direction.name", read_only=True, default="")
    transfer_account_name = serializers.CharField(source="transfer_account.name", read_only=True, default="")
    deal_title = serializers.CharField(source="deal.title", read_only=True, default="")

    class Meta:
        model = Transaction
        fields = ["id", "direction", "amount", "account", "account_name",
                  "category", "category_name", "category_path", "fin_article", "fin_article_name",
                  "fin_direction", "fin_direction_name", "channel",
                  "counterparty", "currency", "rate", "amount_uah", "date", "op_time",
                  "transfer_account", "transfer_account_name", "transfer_amount", "deal_title",
                  "contact", "contact_name",
                  "comment", "deal", "date", "created_at", "set_category",
                  "payer_direction", "payer_direction_name", "splits"]


class FinModelArticleSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    value_type_display = serializers.CharField(source="get_value_type_display", read_only=True)
    fund_group = serializers.CharField(read_only=True)
    margin_kind = serializers.CharField(read_only=True)

    class Meta:
        model = FinModelArticle
        fields = ["id", "category", "category_display", "name", "value", "fin_direction",
                  "value_type", "value_type_display", "unit", "sort_order", "active",
                  "parent", "is_envelope", "fund_group", "margin_kind"]


class FinDirectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinDirection
        fields = ["id", "name", "plan_income", "plan_expense", "sort_order", "active"]


class FundAllocationSerializer(serializers.ModelSerializer):
    fund_name = serializers.CharField(source="fund.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True, default="")
    fin_direction_name = serializers.CharField(source="fin_direction.name", read_only=True, default="")

    class Meta:
        model = FundAllocation
        fields = ["id", "fund", "fund_name", "account", "account_name",
                  "fin_direction", "fin_direction_name", "amount", "period", "comment", "created_at"]


class AdvisoryReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvisoryReport
        fields = ["id", "kind", "title", "body", "created_at"]
