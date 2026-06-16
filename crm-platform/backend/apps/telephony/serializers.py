from rest_framework import serializers
from .models import Call


class CallSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source="manager.get_full_name", read_only=True)
    contact_name = serializers.SerializerMethodField()
    direction_display = serializers.CharField(source="get_direction_display", read_only=True)

    class Meta:
        model = Call
        fields = ["id", "direction", "direction_display", "from_number", "to_number",
                  "contact", "contact_name", "deal", "manager", "manager_name",
                  "duration", "recording_url", "created_at"]

    def get_contact_name(self, obj):
        return str(obj.contact) if obj.contact else ""
