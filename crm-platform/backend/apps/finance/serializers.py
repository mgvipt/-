from rest_framework import serializers
from .models import FinModelArticle, FinDirection, Account, Category, Transaction, FundAllocation, AdvisoryReport


class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ["id", "name", "kind", "is_active", "balance", "sort_order"]

    def get_balance(self, obj):
        return obj.balance()


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "direction", "parent"]


class PlannedPaymentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    account_name = serializers.CharField(source="account.name", read_only=True, default=None)
    fin_direction_name = serializers.CharField(source="fin_direction.name", read_only=True, default=None)
    fin_article_name = serializers.CharField(source="fin_article.name", read_only=True, default=None)
    deal_title = serializers.CharField(source="deal.title", read_only=True, default=None)

    class Meta:
        from .models import PlannedPayment
        model = PlannedPayment
        fields = ["id", "kind", "amount", "due_date", "counterparty", "category", "category_name",
                  "account", "account_name", "fin_direction", "fin_direction_name",
                  "fin_article", "fin_article_name", "channel", "deal", "deal_title",
                  "comment", "status", "created_at"]


class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    set_category = serializers.CharField(write_only=True, required=False, allow_blank=True,
        help_text="Назва категорії текстом — знайде або створить")

    def _resolve_category(self, validated):
        name = (validated.pop("set_category", "") or "").strip()
        if name:
            cat, _ = Category.objects.get_or_create(name=name, defaults={"direction": validated.get("direction", "out")})
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
                  "category", "category_name", "fin_article", "fin_article_name",
                  "fin_direction", "fin_direction_name", "channel",
                  "counterparty", "currency", "rate", "amount_uah", "date", "op_time",
                  "transfer_account", "transfer_account_name", "deal_title",
                  "comment", "deal", "date", "created_at", "set_category"]


class FinModelArticleSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    value_type_display = serializers.CharField(source="get_value_type_display", read_only=True)
    fund_group = serializers.CharField(read_only=True)
    margin_kind = serializers.CharField(read_only=True)

    class Meta:
        model = FinModelArticle
        fields = ["id", "category", "category_display", "name", "value",
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
