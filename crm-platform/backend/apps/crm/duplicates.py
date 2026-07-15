"""Пошук дублів клієнтів / лідів / сделок + об'єднання.
Дублі контактів шукаємо за: телефоном, email, мессенджером(social_link), іменем.
Дублі лідів/сделок = один контакт має кілька сутностей.
Доступ — лише адмін (roles.manage / staff)."""
import re
from collections import defaultdict
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from apps.inbox.models import Contact, Conversation
from apps.crm.models import Lead, Deal


def _can(user):
    if user.is_staff or user.is_superuser:
        return True
    try:
        return "roles.manage" in user.effective_permissions()
    except Exception:
        return False


def _norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    return d[-9:] if len(d) >= 9 else ""


_PLACEHOLDERS = {"гость", "гість", "без имени", "без імені", "клиент", "клієнт", "guest",
                 "instagram", "facebook", "user", "користувач", "ноунейм", "невідомо"}


def _norm_name(f, l):
    # потрібні ОБИДВА (імʼя + прізвище) — інакше «Оксана» зливала б усіх Оксан
    f = (f or "").strip().lower()
    l = (l or "").strip().lower()
    if not f or not l or f == l:  # «Оксана Оксана» = фактично одне імʼя → не групуємо
        return ""
    s = (f + " " + l).strip()
    if any(p in s for p in _PLACEHOLDERS) or len(s) < 5:
        return ""
    return s


def _full(i):
    return ((i.get("first_name") or "") + " " + (i.get("last_name") or "")).strip() or "—"


class DuplicatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user):
            return Response({"detail": "Немає доступу"}, status=403)
        typ = request.query_params.get("type", "contacts")
        if typ == "contacts":
            return Response(self._contacts())
        if typ == "leads":
            return Response(self._entity(Lead, "leads"))
        if typ == "deals":
            return Response(self._entity(Deal, "deals"))
        return Response({"type": typ, "total": 0, "groups": []})

    # ── дублі контактів ──
    def _contacts(self):
        rows = list(Contact.objects.values("id", "first_name", "last_name", "phone", "email", "social_link"))
        buckets = {"phone": defaultdict(list), "email": defaultdict(list),
                   "social": defaultdict(list), "name": defaultdict(list)}
        for r in rows:
            ph = _norm_phone(r["phone"])
            if ph:
                buckets["phone"][ph].append(r)
            em = (r["email"] or "").strip().lower()
            if em:
                buckets["email"][em].append(r)
            sl = (r["social_link"] or "").strip().lower().rstrip("/")
            if sl:
                buckets["social"][sl].append(r)
            nm = _norm_name(r["first_name"], r["last_name"])
            if nm:
                buckets["name"][nm].append(r)
        labels = {"phone": "Телефон", "email": "Email", "social": "Мессенджер/нік", "name": "Имя"}
        groups = []
        for reason, b in buckets.items():
            for key, items in b.items():
                if len(items) < 2:
                    continue
                groups.append({
                    "reason": labels[reason], "by": reason, "key": key, "count": len(items),
                    "items": [{"id": i["id"], "name": _full(i), "phone": i["phone"] or "",
                               "email": i["email"] or "", "social": i["social_link"] or ""} for i in items],
                })
        # надійні збіги (телефон/email/мессенджер) — першими, імʼя — в кінці (потребує перевірки)
        order = {"phone": 0, "email": 1, "social": 2, "name": 3}
        groups.sort(key=lambda g: (order.get(g["by"], 9), -g["count"]))
        return {"type": "contacts", "total": len(groups), "groups": groups[:300]}

    # ── дублі лідів/сделок: один контакт + ОДНАКОВА назва (реальний дубль вводу) ──
    def _entity(self, Model, typ):
        seen = defaultdict(list)
        for o in Model.objects.select_related("contact", "stage", "owner").exclude(contact__isnull=True):
            title = (o.title or "").strip().lower()
            if not title:
                continue
            seen[(o.contact_id, title)].append(o)
        groups = []
        for (cid, title), objs in seen.items():
            if len(objs) < 2:
                continue
            c = objs[0].contact
            cname = ((c.first_name or "") + " " + (c.last_name or "")).strip() or f"#{cid}"
            groups.append({
                "reason": "Одинаковые у одного контакта", "by": "contact",
                "key": f"{cname} · {objs[0].title}", "count": len(objs),
                "items": [{"id": o.id, "name": o.title or "—", "stage": getattr(o.stage, "name", "") or "",
                           "owner": (o.owner.get_full_name() if o.owner else "") or "",
                           "amount": str(o.amount or 0)} for o in objs],
            })
        groups.sort(key=lambda g: -g["count"])
        return {"type": typ, "total": len(groups), "groups": groups[:300]}

    # ── об'єднання контактів ──
    @transaction.atomic
    def post(self, request):
        if not _can(request.user):
            return Response({"detail": "Немає доступу"}, status=403)
        keep = request.data.get("keep")
        ids = [i for i in (request.data.get("ids") or []) if i != keep]
        if not keep or not ids:
            return Response({"detail": "keep + ids обов'язкові"}, status=400)
        k = Contact.objects.get(id=keep)
        # перепривʼязати ВСІ реверсивні FK з дублів → на keep
        for rel in Contact._meta.related_objects:
            fname = rel.field.name
            model = rel.related_model
            try:
                if rel.many_to_many:
                    for obj in model.objects.filter(**{f"{fname}__in": ids}):
                        getattr(obj, fname).remove(*list(getattr(obj, fname).filter(id__in=ids)))
                        getattr(obj, fname).add(k)
                else:
                    model.objects.filter(**{f"{fname}__in": ids}).update(**{fname: k})
            except Exception:
                pass
        # 1) ЯВНИЙ вибір полів (галочки в модалці об'єднання): що обрано — те й ставимо на keep
        fields = request.data.get("fields") or {}
        ALLOWED = {"first_name", "last_name", "middle_name", "nickname", "phone", "email",
                   "social_link", "address", "birthday", "source", "edrpou", "iban", "comment"}
        for f, v in fields.items():
            if f not in ALLOWED:
                continue
            if f == "birthday":
                setattr(k, f, v or None)
            else:
                setattr(k, f, v if v is not None else "")
        # 1b) МУЛЬТИ-месенджери: зберігаємо обраний список (галочки) + дозаповнюємо з дублів
        msgs = request.data.get("messengers")
        if isinstance(msgs, list):
            seen, res = set(), []
            src_all = [k] + list(Contact.objects.filter(id__in=ids))
            pool = list(msgs)
            for c in src_all:
                if c.social_link:
                    pool.append(c.social_link)
                for m in (c.messengers or []):
                    pool.append(m)
            picked = set((x or "").strip().lower() for x in msgs if (x or "").strip())
            for m in pool:
                m = (m or "").strip()
                if m and m.lower() in picked and m.lower() not in seen:
                    seen.add(m.lower()); res.append(m)
            k.messengers = res
            if res and not (request.data.get("fields") or {}).get("social_link"):
                k.social_link = res[0]
        # 2) обʼєднати канали месенджерів (union усіх)
        try:
            chans = set(k.channels or [])
            for src in Contact.objects.filter(id__in=ids):
                chans |= set(src.channels or [])
            k.channels = sorted(chans)
        except Exception:
            pass
        # 3) дозаповнити ПОРОЖНІ поля keep з дублів (для полів, що НЕ обрані явно)
        for src in Contact.objects.filter(id__in=ids):
            for f in ["phone", "email", "social_link", "first_name", "last_name", "address", "company", "birthday"]:
                if not getattr(k, f) and getattr(src, f):
                    setattr(k, f, getattr(src, f))
        k.save()
        Contact.objects.filter(id__in=ids).delete()
        return Response({"ok": True, "merged": len(ids), "keep": keep})
