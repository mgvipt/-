from rest_framework import serializers
from .models import Company, Contact, Funnel, Stage, Lead, Deal, Payment


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
