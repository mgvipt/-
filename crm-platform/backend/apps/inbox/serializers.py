from rest_framework import serializers
from .models import Channel, Conversation, Message


class ChannelSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Channel
        # config с секретами наружу не отдаём
        fields = ["id", "kind", "kind_display", "name", "is_active", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "conversation", "direction", "text", "attachments",
                  "sender_name", "created_at"]
        read_only_fields = ["direction", "sender_name", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    channel_kind = serializers.CharField(source="channel.kind", read_only=True)
    channel_name = serializers.CharField(source="channel.name", read_only=True)
    contact_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    last_text = serializers.SerializerMethodField()
    needs_reply = serializers.SerializerMethodField()

    def get_contact_name(self, obj):
        return str(obj.contact) if obj.contact else (obj.title or "")

    def get_assigned_to_name(self, obj):
        if not obj.assigned_to:
            return ""
        return obj.assigned_to.get_full_name() or obj.assigned_to.username

    class Meta:
        model = Conversation
        fields = ["id", "channel", "channel_kind", "channel_name", "contact",
                  "contact_name", "title", "status", "assigned_to", "assigned_to_name",
                  "unread", "last_message_at", "last_text", "needs_reply"]

    def get_last_text(self, obj):
        m = obj.messages.last()
        return m.text if m else ""

    def get_needs_reply(self, obj):
        m = obj.messages.last()
        return bool(m and m.direction == "in")
