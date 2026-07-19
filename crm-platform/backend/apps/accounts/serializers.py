from rest_framework import serializers
from .models import User, Role, Department, Invite, PERMISSION_CHOICES


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "permissions", "funnels", "open_lines", "stage_view_all", "stage_lock",
                  "fin_accounts", "fin_cats_in", "fin_cats_out", "fin_dirs", "fin_counterparties"]


class DepartmentSerializer(serializers.ModelSerializer):
    members_count = serializers.SerializerMethodField()
    eff_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ["id", "name", "parent", "head", "permissions", "funnels",
                  "open_lines", "color", "pos_x", "pos_y", "sort", "stage_view_all", "stage_lock", "members_count", "eff_permissions",
                  "fin_accounts", "fin_cats_in", "fin_cats_out", "fin_dirs", "fin_counterparties"]

    def get_members_count(self, obj):
        return obj.members.filter(is_active=True).count()

    def get_eff_permissions(self, obj):
        return list(obj.eff_permissions())


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    full_name = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "full_name", "email",
                  "phone", "extension", "role", "role_name", "department", "department_name",
                  "extra_permissions", "denied_permissions", "effective_permissions", "stage_view_all", "stage_lock", "theme", "is_active",
                  "employment_status", "dismissed_at", "date_joined",
                  "extra_funnels", "extra_open_lines",
                  "fin_accounts", "fin_cats_in", "fin_cats_out", "fin_dirs", "fin_counterparties"]
        read_only_fields = ["date_joined"]

    def get_full_name(self, obj):
        return ("%s %s" % (obj.first_name, obj.last_name)).strip() or obj.username

    def get_effective_permissions(self, obj):
        return list(obj.effective_permissions())


class MeSerializer(UserSerializer):
    permissions = serializers.SerializerMethodField()
    permission_catalog = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["permissions", "permission_catalog", "is_superuser"]

    def get_permissions(self, obj):
        return list(obj.effective_permissions())

    def get_permission_catalog(self, obj):
        return [{"code": c, "label": l} for c, l in PERMISSION_CHOICES]


class InviteSerializer(serializers.ModelSerializer):
    link = serializers.SerializerMethodField()
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = Invite
        fields = ["id", "email", "first_name", "last_name", "department", "department_name",
                  "role", "token", "status", "expires_at", "created_at", "link"]
        read_only_fields = ["token", "status", "created_at", "expires_at"]

    def get_link(self, obj):
        return "https://crm.wallcovdec.com.ua/invite/" + obj.token
