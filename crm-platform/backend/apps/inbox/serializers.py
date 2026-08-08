from rest_framework import serializers
from .models import Channel, Conversation, Message


class ChannelSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Channel
        # config с секретами наружу не отдаём
        fields = ["id", "kind", "kind_display", "name", "is_active", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()

    def get_attachments(self, obj):
        from apps.inbox.views import _tg_sig
        out = []
        for i, a in enumerate(obj.attachments or []):
            a = dict(a)
            if a.get("file_id") and not a.get("url"):
                a["url"] = "/api/inbox/tg-file/%s/%s/?s=%s" % (obj.id, i, _tg_sig(obj.id, i))
            out.append(a)
        return out

    class Meta:
        model = Message
        fields = ["id", "conversation", "direction", "text", "internal", "attachments",
                  "sender_name", "created_at", "status"]
        read_only_fields = ["direction", "sender_name", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    channel_kind = serializers.CharField(source="channel.kind", read_only=True)
    channel_name = serializers.CharField(source="channel.name", read_only=True)
    contact_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    last_text = serializers.SerializerMethodField()
    needs_reply = serializers.SerializerMethodField()
    ai_answered = serializers.SerializerMethodField()
    deal_stage = serializers.SerializerMethodField()
    deal_id = serializers.SerializerMethodField()
    participant_names = serializers.SerializerMethodField()
    manager_replied = serializers.SerializerMethodField()
    pending_in = serializers.SerializerMethodField()

    def get_contact_name(self, obj):
        return str(obj.contact) if obj.contact else (obj.title or "")

    def get_participant_names(self, obj):
        return [(u.get_full_name() or u.username) for u in obj.participants.all()]

    def _deal(self, obj):
        if not obj.contact_id:
            return None
        if not hasattr(obj, "_cached_deal"):
            obj._cached_deal = obj.contact.deals.select_related("stage").order_by("-updated_at").first()
        return obj._cached_deal

    def get_deal_stage(self, obj):
        d = self._deal(obj)
        return (d.stage.name if d and d.stage else "") if d else ""

    def get_deal_id(self, obj):
        d = self._deal(obj)
        return d.id if d else None

    def get_assigned_to_name(self, obj):
        if not obj.assigned_to:
            return ""
        return obj.assigned_to.get_full_name() or obj.assigned_to.username

    class Meta:
        model = Conversation
        fields = ["id", "channel", "channel_kind", "channel_name", "contact",
                  "contact_name", "title", "status", "assigned_to", "assigned_to_name",
                  "unread", "last_message_at", "last_text", "needs_reply", "ai_answered", "manager_replied", "pending_in", "participants", "participant_names", "priority", "priority_reason", "deal_stage", "deal_id"]

    def get_last_text(self, obj):
        m = obj.messages.last()
        return m.text if m else ""

    def get_needs_reply(self, obj):
        # останнє вхідне АБО вручну позначено неотвеченим (unread>0) → потрібна відповідь
        m = obj.messages.last()
        return bool((m and m.direction == "in") or (obj.unread or 0) > 0)

    def get_ai_answered(self, obj):
        """Останнє повідомлення — від ШІ-агента (Юля/бот) = «відповів агент»."""
        m = obj.messages.last()
        return bool(m and m.direction == "out" and m.sender_id is None and not m.internal
                    and (m.sender_name or "") in ("ai_assistant", "bot"))

    def get_manager_replied(self, obj):
        """Чи відповіла клієнту ЛЮДИНА: CRM-користувач АБО ChatPlace operator/manager/admin.
        Будь-який ШІ (ai_assistant/bot/system/AI-персони/порожнє) — НЕ людина → червоний."""
        from django.db.models import Q
        human_sides = ("operator", "manager", "admin")
        return obj.messages.filter(direction="out", internal=False).filter(
            Q(sender__isnull=False) | Q(sender_name__in=human_sides)).exists()

    def get_pending_in(self, obj):
        """Скільки повідомлень клієнта без відповіді (після останнього нашого вихідного)."""
        last_out = obj.messages.filter(direction="out").order_by("-id").values_list("id", flat=True).first()
        q = obj.messages.filter(direction="in")
        if last_out:
            q = q.filter(id__gt=last_out)
        return q.count()
