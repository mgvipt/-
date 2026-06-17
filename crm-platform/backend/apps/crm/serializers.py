from rest_framework import serializers
from .models import Company, Contact, Funnel, Stage, Lead, Deal, DealItem, Payment


class DealItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = DealItem
        fields = ["id", "deal", "product", "product_name", "quantity", "price", "total"]
        read_only_fields = ["deal"]


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = "__all__"


class ContactSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = ["id", "first_name", "last_name", "display_name", "phone",
                  "email", "company", "channels", "created_at"]

    def get_display_name(self, obj):
        return str(obj)


class StageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stage
        fields = ["id", "funnel", "name", "color", "order", "is_won", "is_lost"]


class FunnelSerializer(serializers.ModelSerializer):
    stages = StageSerializer(many=True, read_only=True)

    class Meta:
        model = Funnel
        fields = ["id", "name", "is_lead_funnel", "order", "stages"]


class LeadSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True)
    contact_name = serializers.SerializerMethodField()

    def get_contact_name(self, obj):
        return str(obj.contact) if obj.contact else ""

    class Meta:
        model = Lead
        fields = ["id", "title", "contact", "contact_name", "funnel", "stage",
                  "source", "amount", "is_seen", "owner", "owner_name",
                  "created_at", "updated_at"]


class DealSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True)
    contact_name = serializers.SerializerMethodField()

    def get_contact_name(self, obj):
        return str(obj.contact) if obj.contact else ""

    class Meta:
        model = Deal
        fields = ["id", "title", "contact", "contact_name", "funnel", "stage",
                  "source", "amount", "owner", "owner_name", "closed_at",
                  "created_at", "updated_at"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"


class DealDetailSerializer(DealSerializer):
    """Расширенная карточка сделки: товары, оплаты, кешфлоу (доход/расход/прибыль)."""
    items = DealItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    paid = serializers.SerializerMethodField()
    cashflow = serializers.SerializerMethodField()

    class Meta(DealSerializer.Meta):
        fields = DealSerializer.Meta.fields + ["items", "payments", "paid", "cashflow"]

    def get_paid(self, obj):
        return float(sum(p.amount for p in obj.payments.all() if p.is_paid))

    def get_cashflow(self, obj):
        """Кешфлоу по сделке: доход, расход (себестоимость), прибыль, маржа."""
        income = sum(t.amount for t in obj.transactions.all() if t.direction == "in")
        expense = sum(t.amount for t in obj.transactions.all() if t.direction == "out")
        # потенциальная себестоимость по товарам (если ещё не отгружено)
        cogs_planned = sum(i.quantity * i.product.cost for i in obj.items.all())
        profit = float(income - expense)
        margin = round(profit / float(income) * 100, 1) if income else 0
        return {
            "income": float(income), "expense": float(expense),
            "profit": profit, "margin": margin, "cogs_planned": float(cogs_planned),
        }
