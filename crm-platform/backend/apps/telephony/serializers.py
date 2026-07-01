from rest_framework import serializers
from .models import Call


class CallSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source="manager.get_full_name", read_only=True)
    contact_name = serializers.SerializerMethodField()
    direction_display = serializers.CharField(source="get_direction_display", read_only=True)
    recording_url = serializers.SerializerMethodField()

    class Meta:
        model = Call
        fields = ["id", "direction", "direction_display", "from_number", "to_number",
                  "contact", "contact_name", "deal", "manager", "manager_name",
                  "duration", "recording_url", "recording_file", "extension",
                  "disposition", "started_at", "line", "created_at", "transcript"]

    def get_contact_name(self, obj):
        return str(obj.contact) if obj.contact else ""

    def get_recording_url(self, obj):
        if not obj.recording_file:
            return ""
        import hmac, hashlib, time
        from django.conf import settings
        exp = int(time.time()) + 8 * 3600  # посилання живе 8 годин, потім протухає (безпека)
        sig = hmac.new(settings.SECRET_KEY.encode(), f"{obj.id}.{exp}".encode(), hashlib.sha256).hexdigest()[:20]
        return f"/api/telephony/rec/{obj.id}/?s={sig}&exp={exp}"
