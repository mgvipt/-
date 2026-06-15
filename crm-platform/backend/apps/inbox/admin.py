from django.contrib import admin
from .models import Channel, Conversation, Message


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "is_active", "created_at")
    list_filter = ("kind", "is_active")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "channel", "contact", "status", "unread", "last_message_at")
    list_filter = ("channel", "status")


admin.site.register(Message)
