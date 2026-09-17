from rest_framework import viewsets, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.db.models import Q

from .models import User, Role, Department, Invite, PERMISSION_CHOICES
from .serializers import (
    ClientRegistrationSerializer, DepartmentSerializer, InviteSerializer,
    MeSerializer, RoleSerializer, UserSerializer, normalize_client_phone,
)
from apps.common.permissions import HasPermCode


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all().order_by("name")
    serializer_class = RoleSerializer
    permission_classes = [HasPermCode]
    required_perm = "roles.manage"


def _rr_reassign(qs, field, pool, snap=None):
    """Round-robin: розподілити записи qs рівномірно між pool (список юзерів). Повертає к-сть.
    snap (dict) — запамʼятати, КОМУ які id передали (для скасування помилкового звільнення, 17.09.2026)."""
    ids = list(qs.values_list("id", flat=True))
    if not pool or not ids:
        return 0
    nn = len(pool)
    key = "%s.%s:%s" % (qs.model._meta.app_label, qs.model.__name__, field)
    for i, p in enumerate(pool):
        chunk = ids[i::nn]
        if chunk:
            qs.model.objects.filter(id__in=chunk).update(**{field: p})
            if snap is not None:
                snap.setdefault(key, {})[str(p.id)] = chunk
    return len(ids)


UNDO_DISMISS_DAYS = 7
_UNDO_LABELS = {"crm.Contact:owner": "клієнти", "crm.Lead:owner": "ліди", "crm.Deal:owner": "сделки",
                "inbox.Conversation:assigned_to": "чати", "crm.Task:assignee": "задачі",
                "warehouse.WarehouseJob:assignee": "склад_задачі"}


def restore_staff_transfer(tr, user, actor=None):
    """Скасувати передачу при звільненні: повернути співробітнику ЛИШЕ ті записи, які досі лежать у того,
    кому їх передали (якщо колега вже змінив відповідального — не чіпаємо). Ставку, закриту звільненням,
    відкриваємо знову (якщо з того часу її ніхто не міняв). Повертає {назва: к-сть}."""
    from django.apps import apps as _apps
    from django.utils import timezone
    res = {}
    for key, per_target in (tr.data or {}).items():
        if key == "payroll" or not isinstance(per_target, dict):
            continue
        label, field = key.split(":")
        model = _apps.get_model(label)
        n = 0
        for to_id, ids in per_target.items():
            n += model.objects.filter(id__in=ids, **{field + "_id": int(to_id)}).update(**{field: user})
        res[_UNDO_LABELS.get(key, key)] = n
    try:
        from apps.payroll.models import PayScheme, PayRateLog
        for p in (tr.data or {}).get("payroll", []):
            sc = PayScheme.objects.filter(id=p.get("scheme"), user=user).first()
            if not sc:
                continue
            aft, bef = p.get("after") or {}, p.get("before") or {}
            now_vt = sc.valid_to.isoformat() if sc.valid_to else None
            if now_vt != aft.get("valid_to") or sc.status != aft.get("status"):
                continue  # ставку вже змінили вручну — не перетираємо
            from datetime import date as _d
            sc.valid_to = _d.fromisoformat(bef["valid_to"]) if bef.get("valid_to") else None
            sc.status = bef.get("status") or sc.status
            sc.save(update_fields=["valid_to", "status", "updated_at"])
            PayRateLog.objects.create(scheme=sc, action="update", before=aft, after=bef, user=actor,
                                      note="Звільнення скасовано (повернули в активні): ставку відкрито знову")
            res["ставки"] = res.get("ставки", 0) + 1
    except Exception:
        pass
    tr.restored_at = timezone.now()
    tr.restored = res
    tr.save(update_fields=["restored_at", "restored"])
    return res


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("role", "department", "portal_contact").order_by("username")
    serializer_class = UserSerializer
    permission_classes = [HasPermCode]
    required_perm = "roles.manage"

    def destroy(self, request, *args, **kwargs):
        """Видаляти можна ЛИШЕ помилкові акаунти, які жодного разу не входили.
        Реальних співробітників не видаляємо — їх звільняють (історія лишається)."""
        u = self.get_object()
        if u.last_login is not None:
            return Response({"detail": "Цей співробітник уже працював у системі — його не можна видалити. Використайте «Звільнити»: доступ закриється, а історія залишиться."},
                            status=status.HTTP_400_BAD_REQUEST)
        if u.is_superuser or u.id == request.user.id:
            return Response({"detail": "Не можна видалити цей акаунт"}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        """Фільтр за статусом занятості: ?status=active|inactive|dismissed|all.
        За замовчуванням (без параметра) — тільки активні (сумісність зі старим фронтом).
        ⚠️ Тільки для списку — detail-дії (set_status/dismiss/patch) мусять бачити ВСІХ,
        інакше повернення звільненого/неактивного дає 404."""
        qs = super().get_queryset()
        if self.action != "list":
            return qs
        account_kind = (self.request.query_params.get("account_kind") or "staff").strip().lower()
        if account_kind == User.AccountKind.CLIENT:
            qs = qs.filter(account_kind=User.AccountKind.CLIENT)
        else:
            # Existing employee screens keep their previous behaviour and do
            # not mix public client registrations into staff lists.
            qs = qs.filter(account_kind=User.AccountKind.STAFF)

        # staffvis 15.09: ?visible_in=<сутність>&period=YYYY-MM — активні + звільнені, яких дозволено показувати
        # там (напр. «Табель»). Без параметра — усе як було.
        vis_in = (self.request.query_params.get("visible_in") or "").strip()
        if vis_in:
            from . import visibility as _vis
            if vis_in in _vis.ENTITY_KEYS:
                ids = _vis.visible_dismissed_ids(vis_in, self.request.query_params.get("period"))
                return qs.filter(Q(is_active=True) | Q(id__in=ids))
        st = (self.request.query_params.get("status") or "").strip().lower()
        if st in ("active", "inactive", "dismissed"):
            return qs.filter(employment_status=st)
        if st == "all":
            return qs
        # дефолт: активні (включно зі старими записами де employment_status ще 'active' за замовч.)
        return qs.filter(is_active=True)

    # поля картки, які можна редагувати (решта — тільки через адмінку/права)
    PROFILE_FIELDS = ["photo", "position", "birthday", "about", "interests", "telegram", "phone"]

    @action(detail=False, methods=["get"], permission_classes=[__import__("rest_framework.permissions", fromlist=["IsAuthenticated"]).IsAuthenticated])
    def staff_brief(self, request):
        """Легкий список активних співробітників для селекторів (без прав roles.manage).
        Повертає id, full_name, department_name, role_name."""
        qs = User.objects.select_related("role", "department").filter(is_active=True, account_kind=User.AccountKind.STAFF).order_by("first_name", "last_name", "username")
        data = [{
            "id": u.id,
            "full_name": ((u.first_name or "") + " " + (u.last_name or "")).strip() or u.username,
            "department_name": u.department.name if u.department_id else "",
            "role_name": u.role.name if u.role_id else "",
        } for u in qs]
        from rest_framework.response import Response
        return Response(data)

    def get_permissions(self):
        # свою картку співробітник редагує сам — без права roles.manage
        if getattr(self, "action", None) == "profile":
            from rest_framework.permissions import IsAuthenticated
            return [IsAuthenticated()]
        # legkij список для селекторів (напр. модалка задачі) — усі authenticated
        if getattr(self, "action", None) == "staff_brief":
            from rest_framework.permissions import IsAuthenticated
            return [IsAuthenticated()]
        return super().get_permissions()

    @action(detail=True, methods=["patch"])
    def profile(self, request, pk=None):
        """Картка співробітника: свою редагує сам, чужу — адмін / roles.manage."""
        u = User.objects.filter(pk=pk).first()
        if not u:
            return Response({"detail": "Немає такого"}, status=status.HTTP_404_NOT_FOUND)
        actor = request.user
        is_admin = actor.is_superuser or (hasattr(actor, "has_perm_code") and actor.has_perm_code("roles.manage"))
        if u.id != actor.id and not is_admin:
            return Response({"detail": "Можна редагувати лише свою картку"}, status=status.HTTP_403_FORBIDDEN)
        data = {f: request.data[f] for f in self.PROFILE_FIELDS if f in request.data}
        if not data:
            return Response(UserSerializer(u, context={"request": request}).data)
        # фото зберігається як data URL у БД — обмежуємо розмір (фронт стискає до 256px)
        if data.get("photo") and len(str(data["photo"])) > 400000:
            return Response({"detail": "Фото завелике — стисніть зображення"}, status=status.HTTP_400_BAD_REQUEST)
        if "birthday" in data and not data["birthday"]:
            data["birthday"] = None
        for k, v in data.items():
            setattr(u, k, v)
        u.save(update_fields=list(data.keys()))
        return Response(UserSerializer(u, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def promote(self, request, pk=None):
        """Admin-only transition from an ordinary client to a staff account."""
        unexpected = sorted(set((request.data or {}).keys()) - {"role", "department"})
        if unexpected:
            return Response({"detail": "Недопустимые поля", "fields": unexpected},
                            status=status.HTTP_400_BAD_REQUEST)
        u = self.get_object()
        if u.account_kind != User.AccountKind.CLIENT:
            return Response({"detail": "Этот аккаунт уже является сотрудником"},
                            status=status.HTTP_400_BAD_REQUEST)

        role = None
        department = None
        role_id = request.data.get("role")
        department_id = request.data.get("department")
        if role_id not in (None, ""):
            try:
                role = Role.objects.get(pk=int(role_id))
            except (Role.DoesNotExist, TypeError, ValueError):
                return Response({"detail": "Роль не найдена"}, status=status.HTTP_400_BAD_REQUEST)
        if department_id not in (None, ""):
            try:
                department = Department.objects.get(pk=int(department_id))
            except (Department.DoesNotExist, TypeError, ValueError):
                return Response({"detail": "Отдел не найден"}, status=status.HTTP_400_BAD_REQUEST)

        u.account_kind = User.AccountKind.STAFF
        u.role = role
        u.department = department
        # Public registration cannot populate these fields. Clearing them here
        # also prevents any stale/manual hidden grant from becoming active at
        # the moment of promotion.
        u.extra_permissions = []
        u.denied_permissions = []
        u.extra_open_lines = []
        u.stage_view_all = []
        u.stage_lock = []
        u.is_superuser = False
        u.is_staff = False
        u.save(update_fields=[
            "account_kind", "role", "department", "extra_permissions",
            "denied_permissions", "extra_open_lines", "stage_view_all",
            "stage_lock", "is_superuser", "is_staff",
        ])
        u.extra_funnels.clear()
        return Response(UserSerializer(u, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        """Змінити статус занятості: active / inactive / dismissed. Лише адмін / roles.manage.
        Для 'dismissed' краще використовувати /dismiss/ (він ще й розподіляє сутності)."""
        actor = request.user
        if not (actor.is_superuser or (hasattr(actor, "has_perm_code") and actor.has_perm_code("roles.manage"))):
            return Response({"detail": "Лише адмін може змінювати статус"}, status=status.HTTP_403_FORBIDDEN)
        u = self.get_object()
        new_status = (request.data.get("status") or "").strip().lower()
        if new_status not in dict(User.EMPLOYMENT_STATUS):
            return Response({"detail": "Невідомий статус"}, status=status.HTTP_400_BAD_REQUEST)
        if u.id == actor.id and new_status != "active":
            return Response({"detail": "Не можна деактивувати себе"}, status=status.HTTP_400_BAD_REQUEST)
        old = u.employment_status
        u.apply_employment_status(new_status)
        try:
            from apps.crm.models import log_activity
            log_activity("contact", 0, "Зміна статусу співробітника",
                         "%s: %s → %s" % (u.get_full_name() or u.username, old, new_status), actor, "Адмін")
        except Exception:
            pass
        # 17.09.2026: помилково звільнили і одразу повернули → віддаємо назад клієнтів/ліди/сделки/чати і ставку
        restored = {}
        if old == "dismissed" and new_status == "active":
            from datetime import timedelta
            from django.utils import timezone
            from .models import StaffTransfer
            tr = (StaffTransfer.objects.filter(user=u, restored_at__isnull=True,
                                               at__gte=timezone.now() - timedelta(days=UNDO_DISMISS_DAYS))
                  .order_by("-at").first())
            if tr:
                restored = restore_staff_transfer(tr, u, actor)
                try:
                    from apps.crm.models import log_activity
                    log_activity("contact", 0, "Скасування звільнення",
                                 "%s: повернуто %s" % (u.get_full_name() or u.username,
                                                       ", ".join("%s %s" % (k, v) for k, v in restored.items() if v) or "нічого"),
                                 actor, "Адмін")
                except Exception:
                    pass
        return Response({"ok": True, "employment_status": u.employment_status,
                         "is_active": u.is_active, "dismissed_at": u.dismissed_at,
                         "restored": {k: v for k, v in restored.items() if v}})

    @action(detail=False, methods=["get", "post"])
    def visibility(self, request):
        """Звільнені: де їх показувати (staffvis 15.09.2026). Лише адмін / roles.manage (як увесь розділ).
        GET — звільнені з вибором по сутностях. POST {user_id, set: {сутність: true|false|null}} змінює ЛИШЕ
        передані сутності однієї людини (новіші налаштування інших не затираються); {user_id, all: true|false|null} —
        «усюди увімкнути / вимкнути / усе на Авто». Активних співробітників це не стосується."""
        from . import visibility as vis
        if request.method != "POST":
            return Response(vis.overview())
        d = request.data or {}
        try:
            uid = int(d.get("user_id"))
        except (TypeError, ValueError):
            return Response({"detail": "Не вказано співробітника"}, status=status.HTTP_400_BAD_REQUEST)
        u = User.objects.filter(pk=uid, account_kind=User.AccountKind.STAFF).first()
        if not u:
            return Response({"detail": "Немає такого співробітника"}, status=status.HTTP_404_NOT_FOUND)
        if u.employment_status != "dismissed":
            return Response({"detail": "Ці налаштування діють лише для звільнених. Активних вони не стосуються."},
                            status=status.HTTP_400_BAD_REQUEST)
        if "all" in d:
            v = d.get("all")
            if not vis.valid_choice(v):
                return Response({"detail": "Невірне значення"}, status=status.HTTP_400_BAD_REQUEST)
            changes = {k: v for k in vis.ENTITY_KEYS}
        else:
            changes = d.get("set")
            if not isinstance(changes, dict) or not changes:
                return Response({"detail": "Нічого не змінено"}, status=status.HTTP_400_BAD_REQUEST)
            bad = [k for k in changes if k not in vis.ENTITY_KEYS]
            if bad:
                return Response({"detail": "Невідомий розділ: %s" % ", ".join(map(str, bad))}, status=status.HTTP_400_BAD_REQUEST)
            if not all(vis.valid_choice(v) for v in changes.values()):
                return Response({"detail": "Невірне значення"}, status=status.HTTP_400_BAD_REQUEST)
        before, after = vis.save_choices(u.id, changes, by=request.user)
        if before != after:
            try:
                from apps.crm.models import log_activity
                log_activity("contact", 0, "Видимість звільненого",
                             "%s: %s → %s" % (u.get_full_name() or u.username, vis.describe(before), vis.describe(after)),
                             request.user, "Адмін")
            except Exception:
                pass
        return Response(vis.person_json(u))

    @action(detail=True, methods=["post"])
    def dismiss(self, request, pk=None):
        """Звільнення: акаунт деактивується (доступ зникає, НЕ видаляється), а його сутності
        переходять: продажник → round-robin на всіх активних продажників; інший відділ →
        керівнику відділу (він розподілить), або round-robin на активних членів відділу."""
        actor = request.user
        if not (actor.is_superuser or (hasattr(actor, "has_perm_code") and actor.has_perm_code("roles.manage"))):
            return Response({"detail": "Лише адмін може звільняти"}, status=status.HTTP_403_FORBIDDEN)
        u = self.get_object()
        if u.id == actor.id:
            return Response({"detail": "Не можна звільнити себе"}, status=status.HTTP_400_BAD_REQUEST)
        from apps.crm.models import Deal, Lead, Contact, Task
        from apps.inbox.models import Conversation
        from apps.warehouse.models import WarehouseJob
        from apps.crm.lead_routing import lead_owner_pool
        dept = u.department
        is_sales = bool(dept and "продаж" in (dept.name or "").lower())
        moved = {}
        snap = {}
        # 17.09.2026: передаємо лише ВІДКРИТІ ліди/сделки і незакриті чати. Виграні/програні лишаються за тим,
        # хто їх вів — інакше історія продажів і аналітика «переїжджають» на колег.
        _open = lambda q: q.exclude(stage__is_won=True).exclude(stage__is_lost=True)
        if is_sales:
            pool = [p for p in lead_owner_pool() if p.id != u.id]
            if not pool:
                pool = list(User.objects.filter(is_active=True, is_superuser=False).exclude(id=u.id)[:10])
            moved["клиенты"] = _rr_reassign(Contact.objects.filter(owner=u), "owner", pool, snap)
            moved["лиды"] = _rr_reassign(_open(Lead.objects.filter(owner=u)), "owner", pool, snap)
            moved["сделки"] = _rr_reassign(_open(Deal.objects.filter(owner=u)), "owner", pool, snap)
            moved["чаты"] = _rr_reassign(Conversation.objects.filter(assigned_to=u).exclude(status="closed"),
                                         "assigned_to", pool, snap)
        else:
            head = dept.head if (dept and dept.head_id and dept.head_id != u.id and getattr(dept.head, "is_active", False)) else None
            if head:
                pool = [head]
            elif dept:
                pool = list(User.objects.filter(is_active=True, department=dept).exclude(id=u.id))
            else:
                pool = []
            if not pool:
                pool = list(User.objects.filter(is_active=True, is_superuser=True).exclude(id=u.id)[:1])
            moved["задачи"] = _rr_reassign(Task.objects.filter(assignee=u), "assignee", pool, snap)
            moved["склад_задачи"] = _rr_reassign(WarehouseJob.objects.filter(assignee=u), "assignee", pool, snap)
            moved["сделки"] = _rr_reassign(_open(Deal.objects.filter(owner=u)), "owner", pool, snap)
            moved["лиды"] = _rr_reassign(_open(Lead.objects.filter(owner=u)), "owner", pool, snap)
        u.apply_employment_status("dismissed")  # → is_active=False, is_superuser=False, dismissed_at=сьогодні
        # 15.09.2026 (Олег): «Звільнити» закриває ставку з дати звільнення — ЗП лише за відпрацьований період
        # (payroll._prorate рахує до valid_to включно); майбутні версії ставки — в архів. Затверджені місяці не змінюються.
        try:
            from apps.payroll.models import PayScheme, PayRateLog
            d_end = u.dismissed_at
            if d_end:
                for sc in PayScheme.objects.filter(user=u, status="active", is_vacancy=False).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=d_end)):
                    before = {"valid_to": sc.valid_to.isoformat() if sc.valid_to else None, "status": sc.status}
                    if sc.valid_from > d_end:
                        sc.status = "archived"
                        sc.save(update_fields=["status", "updated_at"])
                        note = "Звільнення %s: майбутню версію ставки (з %s) — в архів" % (d_end.strftime("%d.%m.%Y"), sc.valid_from.strftime("%d.%m.%Y"))
                    else:
                        sc.valid_to = d_end
                        sc.save(update_fields=["valid_to", "updated_at"])
                        note = "Звільнення: ставку закрито з %s" % d_end.strftime("%d.%m.%Y")
                    _after = {"valid_to": sc.valid_to.isoformat() if sc.valid_to else None, "status": sc.status}
                    PayRateLog.objects.create(scheme=sc, action="update", before=before,
                                              after=_after, user=actor, note=note[:255])
                    snap.setdefault("payroll", []).append({"scheme": sc.id, "before": before, "after": _after})
                    moved["ставки"] = moved.get("ставки", 0) + 1
        except Exception:
            pass
        targets = [p.get_full_name() or p.username for p in pool]
        try:  # що кому передали — щоб помилкове звільнення можна було скасувати поверненням в «Активні»
            from .models import StaffTransfer
            StaffTransfer.objects.create(user=u, by=actor, data=snap)
        except Exception:
            pass
        try:
            from apps.crm.models import log_activity
            log_activity("contact", 0, "Звільнення співробітника",
                         "%s деактивовано, дані → %s" % (u.get_full_name() or u.username, ", ".join(targets) or "—"),
                         actor, "Адмін")
        except Exception:
            pass
        return Response({"ok": True, "is_sales": is_sales, "moved": {k: v for k, v in moved.items() if v},
                         "to": targets})
class MeView(APIView):
    """Текущий пользователь + его права (для фронта: какие пункты меню показывать)."""
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        # сотрудник может менять только свою тему оформления
        theme = request.data.get("theme")
        if theme is not None:
            request.user.theme = theme
            request.user.save(update_fields=["theme"])
        return Response(MeSerializer(request.user).data)


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.prefetch_related("members", "funnels").all()
    serializer_class = DepartmentSerializer
    permission_classes = [HasPermCode]
    required_perm = "roles.manage"


class InviteViewSet(viewsets.ModelViewSet):
    queryset = Invite.objects.select_related("department", "role").all()
    serializer_class = InviteSerializer
    permission_classes = [HasPermCode]
    required_perm = "roles.manage"

    def perform_create(self, serializer):
        import secrets
        from django.utils import timezone
        from datetime import timedelta
        serializer.save(token=secrets.token_urlsafe(24), status="pending",
                        expires_at=timezone.now() + timedelta(days=7),
                        created_by=self.request.user if self.request.user.is_authenticated else None)

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        inv = self.get_object(); inv.status = "revoked"; inv.save(update_fields=["status"])
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        from datetime import timedelta
        inv = self.get_object()
        inv.status = "pending"
        if inv.expires_at < timezone.now() + timedelta(days=1):
            inv.expires_at = timezone.now() + timedelta(days=7)
        inv.save(update_fields=["status", "expires_at"])
        return Response(self.get_serializer(inv).data)


class AcceptInviteView(APIView):
    """Публічна сторінка прийняття запрошення: інфо + встановлення пароля -> створення співробітника."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def _get(self, token):
        from django.utils import timezone
        inv = Invite.objects.filter(token=token, status="pending").select_related("department").first()
        if not inv or inv.expires_at < timezone.now():
            return None
        return inv

    def get(self, request, token):
        raw = Invite.objects.filter(token=token).first()
        if raw and raw.status == "accepted":
            return Response({"valid": False, "already_registered": True})
        inv = self._get(token)
        if not inv:
            return Response({"valid": False})
        return Response({"valid": True, "email": inv.email, "first_name": inv.first_name,
                         "last_name": inv.last_name, "username": inv.username or (inv.email.split("@")[0] if inv.email else ""),
                         "department": inv.department.name if inv.department else ""})

    def post(self, request, token):
        inv = self._get(token)
        if not inv:
            return Response({"detail": "Запрошення недійсне або прострочене"}, status=status.HTTP_400_BAD_REQUEST)
        pwd = request.data.get("password") or ""
        if len(pwd) < 6:
            return Response({"detail": "Пароль мінімум 6 символів"}, status=status.HTTP_400_BAD_REQUEST)
        if inv.email and User.objects.filter(email__iexact=inv.email).exists():
            return Response({"detail": "Користувач з таким email вже існує"}, status=status.HTTP_400_BAD_REQUEST)
        base_un = ((inv.username or "").strip() or inv.email.split("@")[0] or "user").lower()
        un = base_un; i = 1
        while User.objects.filter(username=un).exists():
            i += 1; un = "%s%d" % (base_un, i)
        u = User.objects.create_user(username=un, email=inv.email, password=pwd,
                                     first_name=inv.first_name, last_name=inv.last_name,
                                     department=inv.department, role=inv.role,
                                     account_kind=User.AccountKind.STAFF)
        inv.status = "accepted"; inv.save(update_fields=["status"])
        return Response({"ok": True, "username": u.username}, status=status.HTTP_201_CREATED)


class ClientRegistrationThrottle(AnonRateThrottle):
    rate = "5/hour"


class ClientLoginThrottle(AnonRateThrottle):
    rate = "30/hour"


class FlexibleAuthTokenView(APIView):
    """Issue the usual token for username, or a client's exact phone/email."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientLoginThrottle]
    invalid_credentials = {"non_field_errors": ["Unable to log in with provided credentials."]}

    def post(self, request):
        identifier = str(request.data.get("username") or request.data.get("login") or "").strip()
        password = request.data.get("password")
        if not identifier or not isinstance(password, str) or not password:
            return Response(self.invalid_credentials, status=status.HTTP_400_BAD_REQUEST)

        # Preserve the existing username contract first. Django performs a
        # dummy password hash for an unknown username, reducing account probes.
        user = authenticate(request=request, username=identifier, password=password)
        if user is None:
            phone = normalize_client_phone(identifier)
            # Пошта — для ВСІХ (співробітники теж входять поштою, а не лише логіном).
            # Телефон — лише клієнти, як було. Успіх тільки при ОДНОМУ точному збігу.
            matches = list(User.objects.filter(
                email__iexact=identifier,
            ).only("id", "username")[:2])
            if not matches and phone:
                matches = list(User.objects.filter(
                    phone=phone, account_kind=User.AccountKind.CLIENT,
                ).only("id", "username")[:2])
            if len(matches) == 1:
                user = authenticate(
                    request=request,
                    username=matches[0].username,
                    password=password,
                )

        if user is None or not user.is_active:
            return Response(self.invalid_credentials, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})


class ClientRegisterView(APIView):
    """Public account registration; privilege fields are rejected by serializer."""

    permission_classes = [AllowAny]
    throttle_classes = [ClientRegistrationThrottle]

    def post(self, request):
        serializer = ClientRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        name_parts = data["name"].split(" ", 1)
        first_name = name_parts[0][:150]
        last_name = name_parts[1][:150] if len(name_parts) > 1 else ""

        try:
            with transaction.atomic():
                # Repeat uniqueness checks inside the transaction. Contact is
                # always new: matching an existing CRM contact by phone alone
                # would allow account takeover.
                if User.objects.select_for_update().filter(phone=data["phone"]).exists():
                    return Response({"phone": ["Аккаунт с таким телефоном уже существует"]},
                                    status=status.HTTP_400_BAD_REQUEST)
                if data.get("email") and User.objects.select_for_update().filter(
                        email__iexact=data["email"]).exists():
                    return Response({"email": ["Аккаунт с таким email уже существует"]},
                                    status=status.HTTP_400_BAD_REQUEST)

                user = User.objects.create_user(
                    username=data["phone"],
                    password=data["password"],
                    first_name=first_name,
                    last_name=last_name,
                    phone=data["phone"],
                    email=data.get("email") or "",
                    account_kind=User.AccountKind.CLIENT,
                    role=None,
                    department=None,
                    extra_permissions=[],
                    denied_permissions=[],
                    is_superuser=False,
                    is_staff=False,
                )
                from apps.crm.models import Contact
                contact = Contact.objects.create(
                    first_name=first_name[:120],
                    last_name=last_name[:120],
                    phone=data["phone"],
                    email=data.get("email") or "",
                    source="app_zamer",
                    kinds=["client"],
                    comment="Личный кабинет приложения Wallcov Замер",
                    portal_user=user,
                )
                token = Token.objects.create(user=user)
        except IntegrityError:
            return Response({"detail": "Аккаунт с такими данными уже существует"},
                            status=status.HTTP_409_CONFLICT)

        profile = MeSerializer(user, context={"request": request}).data
        return Response({"token": token.key, "profile": profile, "contact_id": contact.id},
                        status=status.HTTP_201_CREATED)


class PermissionsCatalogView(APIView):
    def get(self, request):
        from apps.accounts.models import PERMISSION_GROUPS
        groups = [{"group": g, "items": [{"code": c, "label": l, "hint": h} for c, l, h in items]} for g, items in PERMISSION_GROUPS]
        flat = [{"code": c, "label": l} for c, l in PERMISSION_CHOICES]
        return Response({"groups": groups, "flat": flat})
