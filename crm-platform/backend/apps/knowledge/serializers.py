from rest_framework import serializers

from apps.warehouse.models import Product
from .models import KnowledgeItem, KnowledgeVersion

AGENT_CODES = [c for c, _ in KnowledgeItem.AGENTS]


def _name(u):
    return (u.get_full_name() or u.username) if u else ""


class KnowledgeItemSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    topic_display = serializers.CharField(source="get_topic_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    products = serializers.PrimaryKeyRelatedField(many=True, queryset=Product.objects.all(), required=False)
    product_names = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    flagged = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeItem
        fields = ["id", "kind", "kind_display", "topic", "topic_display", "audience", "status", "status_display",
                  "title", "text", "internal_note", "products", "product_names", "source", "source_display",
                  "source_ref", "external_ids", "evidence", "replaces", "priority", "popularity", "version",
                  "approved_by_name", "approved_at", "approval_note", "created_by_name", "updated_by_name",
                  "created_at", "updated_at", "flagged", "precheck"]
        read_only_fields = ["status", "source", "source_ref", "external_ids", "evidence", "replaces", "popularity",
                            "version", "approved_at", "approval_note", "created_at", "updated_at"]

    def get_product_names(self, obj):
        return [p.name for p in obj.products.all()]

    def get_approved_by_name(self, obj):
        return _name(obj.approved_by)

    def get_created_by_name(self, obj):
        return _name(obj.created_by)

    def get_updated_by_name(self, obj):
        return _name(obj.updated_by)

    def get_flagged(self, obj):
        return "⚠️" in (obj.internal_note or "")

    precheck = serializers.SerializerMethodField()

    def get_precheck(self, obj):
        """Мітка попередньої перевірки (ai-kb2); stale — запис змінили після перевірки."""
        try:
            c = obj.precheck
        except Exception:
            return None
        return {"label": c.label, "label_display": c.get_label_display(), "reason": c.reason, "ref": c.ref_item_id,
                "stale": c.item_version != obj.version, "source": c.source, "checked_at": c.checked_at}

    def validate_audience(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Список агентів")
        bad = [v for v in value if v not in AGENT_CODES]
        if bad:
            raise serializers.ValidationError("Невідомі агенти: %s" % ", ".join(map(str, bad)))
        return list(dict.fromkeys(value))

    def validate_title(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Впишіть питання або назву")
        return value

    def validate_text(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Впишіть текст")
        return value


class VersionSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeVersion
        fields = ["id", "version", "action", "action_display", "snapshot", "note", "changed_by_name", "created_at"]

    def get_changed_by_name(self, obj):
        return _name(obj.changed_by) or "система"
