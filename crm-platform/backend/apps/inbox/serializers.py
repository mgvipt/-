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
    contact_name = serializers.CharField(source="contact.__str__", read_only=True)
    last_text = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ["id", "channel", "channel_kind", "channel_name", "contact",
                  "contact_name", "title", "status", "assigned_to", "unread",
                  "last_message_at", "last_text"]

    def get_last_text(self, obj):
        m = obj.messages.last()
        return m.text if m else ""
