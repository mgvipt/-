from rest_framework import serializers
from .models import User, Role, Department, PERMISSION_CHOICES


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "permissions", "funnels", "open_lines"]


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "head"]


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email",
                  "phone", "role", "role_name", "department", "theme", "is_active"]


class MeSerializer(UserSerializer):
    permissions = serializers.SerializerMethodField()
    permission_catalog = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["permissions", "permission_catalog", "is_superuser"]

    def get_permissions(self, obj):
        return obj.role.permissions if obj.role else []

    def get_permission_catalog(self, obj):
        return [{"code": c, "label": l} for c, l in PERMISSION_CHOICES]
