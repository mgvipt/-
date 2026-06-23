from rest_framework import serializers
from .models import Company, Contact, Funnel, Stage, Lead, Deal, DealItem, Payment


class DealItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_stock = serializers.DecimalField(source="product.stock", max_digits=12, decimal_places=2, read_only=True, default=0)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = DealItem
        fields = ["id", "deal", "product", "product_name", "product_stock", "quantity", "price", "total", "reserved"]
        read_only_fields = ["deal"]


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = "__all__"


class ContactSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True, default="")

    class Meta:
        model = Contact
        fields = ["id", "first_name", "last_name", "display_name", "phone",
                  "email", "company", "channels", "loyalty_tag", "birthday",
                  "source", "address", "comment", "owner", "owner_name", "created_at"]

    def get_display_name(self, obj):
        return str(obj)


class ContactDetailSerializer(ContactSerializer):
    """Картка клієнта: + історія сделок + сумарні витрати."""
    deals = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()

    class Meta(ContactSerializer.Meta):
        fields = ContactSerializer.Meta.fields + ["deals", "total_spent"]

    def get_deals(self, obj):
        return [{"id": d.id, "title": d.title, "amount": float(d.amount),
                 "stage": d.stage.name if d.stage else "", "is_won": d.stage.is_won if d.stage else False,
                 "created_at": d.created_at} for d in obj.deals.select_related("stage").order_by("-created_at")[:50]]

    def get_total_spent(self, obj):
        from django.db.models import Sum
        return float(obj.deals.filter(stage__is_won=True).aggregate(s=Sum("amount"))["s"] or 0)


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
                  "source", "amount", "is_seen", "qualification", "owner", "owner_name",
                  "created_at", "updated_at"]


class DealSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True)
    contact_name = serializers.SerializerMethodField()

    def get_contact_name(self, obj):
        return str(obj.contact) if obj.contact else ""

    class Meta:
        model = Deal
        fields = ["id", "title", "contact", "contact_name", "funnel", "stage",
                  "source", "amount", "discount_pct", "pay_type", "ttn", "checkbox_status",
                  "owner", "owner_name", "closed_at",
                  "created_at", "updated_at"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"


class DealDetailSerializer(DealSerializer):
    """Расширенная карточка сделки: товары, оплаты, оплачено/осталось + маржа/бонус/лояльность."""
    items = DealItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    paid = serializers.SerializerMethodField()
    margin = serializers.SerializerMethodField()
    bonus = serializers.SerializerMethodField()
    days_in_stage = serializers.SerializerMethodField()
    contact_loyalty = serializers.SerializerMethodField()
    contact_id = serializers.IntegerField(source="contact.id", read_only=True)
    conversation_id = serializers.SerializerMethodField()

    def get_conversation_id(self, obj):
        if not obj.contact_id:
            return None
        from apps.inbox.models import Conversation
        c = Conversation.objects.filter(contact=obj.contact).order_by("-last_message_at").first()
        return c.id if c else None

    class Meta(DealSerializer.Meta):
        fields = DealSerializer.Meta.fields + [
            "items", "payments", "paid", "margin", "bonus",
            "days_in_stage", "contact_loyalty", "contact_id", "conversation_id", "b24_id",
        ]

    def get_paid(self, obj):
        return float(sum(p.amount for p in obj.payments.all() if p.is_paid))

    def get_margin(self, obj):
        # Маржа = выручка по строкам − себестоимость (cost товара). Без товаров — оценка 35%.
        items = list(obj.items.all())
        if not items:
            return round(float(obj.amount) * 0.35, 2)
        revenue = float(sum(i.total for i in items))
        cogs = float(sum(float(i.quantity) * float(getattr(i.product, "cost", 0) or 0) for i in items))
        return round(revenue - cogs, 2)

    def get_bonus(self, obj):
        # Бонус менеджера з цієї угоди = % обороту + % маржі (ставки з Фінмоделі, синхронно).
        from apps.finance.services import deal_manager_bonus
        return deal_manager_bonus(obj.amount, self.get_margin(obj))

    def get_days_in_stage(self, obj):
        from django.utils import timezone
        return (timezone.now() - obj.updated_at).days

    def get_contact_loyalty(self, obj):
        return getattr(obj.contact, "loyalty_tag", "") if obj.contact else ""
