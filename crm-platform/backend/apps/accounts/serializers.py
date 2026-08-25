from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError

from .models import User, Role, Department, Invite, PERMISSION_CHOICES


def normalize_client_phone(value):
    """Return a canonical registration/login phone, or ``None`` if invalid."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    if not 7 <= len(digits) <= 15:
        return None
    return "+" + digits


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
                  "idle_timeout_min",
                  "fin_accounts", "fin_cats_in", "fin_cats_out", "fin_dirs", "fin_counterparties"]

    def get_members_count(self, obj):
        return obj.members.filter(is_active=True).count()

    def get_eff_permissions(self, obj):
        return list(obj.eff_permissions())


class ClientRegistrationSerializer(serializers.Serializer):
    """Strict public input: account privileges are never client-controlled."""

    name = serializers.CharField(max_length=240, trim_whitespace=True)
    phone = serializers.CharField(max_length=32, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128, trim_whitespace=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Ожидается объект с данными регистрации")
        unexpected = sorted(set(data.keys()) - {"name", "phone", "email", "password"})
        if unexpected:
            raise serializers.ValidationError({
                "detail": "Недопустимые поля регистрации",
                "fields": unexpected,
            })
        return super().to_internal_value(data)

    def validate_name(self, value):
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Укажите имя")
        return value

    def validate_phone(self, value):
        normalized = normalize_client_phone(value)
        if not normalized:
            raise serializers.ValidationError("Укажите корректный телефон")
        return normalized

    def validate_email(self, value):
        return value.strip().lower()

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs):
        if User.objects.filter(phone=attrs["phone"]).exists():
            raise serializers.ValidationError({"phone": "Аккаунт с таким телефоном уже существует"})
        email = attrs.get("email") or ""
        if email and User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": "Аккаунт с таким email уже существует"})
        return attrs


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    full_name = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()
    on_shift = serializers.SerializerMethodField()      # зараз на робочому дні (зелений бейдж)
    shift_paused = serializers.SerializerMethodField()  # на зміні, але на паузі/обіді
    effective_idle_timeout = serializers.SerializerMethodField()  # фактичний поріг (особ. або відділ)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "full_name", "email",
                  "phone", "account_kind", "extension", "role", "role_name", "department", "department_name",
                  "extra_permissions", "denied_permissions", "effective_permissions", "stage_view_all", "stage_lock", "theme", "is_active",
                  "employment_status", "dismissed_at", "date_joined", "last_login",
                  "photo", "position", "birthday", "about", "interests", "telegram",
                  "idle_timeout_min", "effective_idle_timeout",
                  "on_shift", "shift_paused",
                  "extra_funnels", "extra_open_lines",
                  "fin_accounts", "fin_cats_in", "fin_cats_out", "fin_dirs", "fin_counterparties"]
        read_only_fields = ["date_joined", "account_kind", "last_login"]

    def get_full_name(self, obj):
        return ("%s %s" % (obj.first_name, obj.last_name)).strip() or obj.username

    def get_effective_permissions(self, obj):
        return list(obj.effective_permissions())

    def get_effective_idle_timeout(self, obj):
        return obj.effective_idle_timeout()

    # ── «на зміні зараз»: множини id беруться ОДНИМ запитом у context (без N+1) ──
    def _shift_sets(self):
        ctx = self.context
        if "on_shift_ids" not in ctx:
            try:
                from apps.finance.models import WorkSession
                act = WorkSession.objects.filter(ended_at__isnull=True).values_list("user_id", "paused_at")
                ctx["on_shift_ids"] = {uid for uid, _ in act}
                ctx["paused_ids"] = {uid for uid, p in act if p}
            except Exception:
                ctx["on_shift_ids"] = set(); ctx["paused_ids"] = set()
        return ctx["on_shift_ids"], ctx["paused_ids"]

    def get_on_shift(self, obj):
        on, _ = self._shift_sets()
        return obj.id in on

    def get_shift_paused(self, obj):
        _, paused = self._shift_sets()
        return obj.id in paused


class MeSerializer(UserSerializer):
    permissions = serializers.SerializerMethodField()
    permission_catalog = serializers.SerializerMethodField()
    contact_id = serializers.SerializerMethodField()
    allowed_contact_kinds = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["permissions", "permission_catalog", "is_superuser", "contact_id", "allowed_contact_kinds"]

    def get_permissions(self, obj):
        return list(obj.effective_permissions())

    def get_allowed_contact_kinds(self, obj):
        v = obj.allowed_contact_kinds()
        return None if v is None else sorted(v)

    def get_permission_catalog(self, obj):
        return [{"code": c, "label": l} for c, l in PERMISSION_CHOICES]

    def get_contact_id(self, obj):
        try:
            return obj.portal_contact.id
        except (AttributeError, ObjectDoesNotExist):
            return None


class InviteSerializer(serializers.ModelSerializer):
    link = serializers.SerializerMethodField()
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = Invite
        fields = ["id", "email", "username", "first_name", "last_name", "department", "department_name",
                  "role", "token", "status", "expires_at", "created_at", "link"]
        read_only_fields = ["token", "status", "created_at", "expires_at"]

    def validate_username(self, value):
        value = (value or "").strip()
        if value:
            from .models import User
            if User.objects.filter(username__iexact=value).exists():
                raise serializers.ValidationError("Такий логін вже зайнятий")
        return value

    def get_link(self, obj):
        return "https://crm.wallcovdec.com.ua/invite/" + obj.token
