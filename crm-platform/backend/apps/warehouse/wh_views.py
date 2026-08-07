"""Склад Фаза-1: endpoints роботи кладовщика + движок ЗП + обід (на WorkSession.pause)."""
import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import WarehouseJob, WarehousePayrollEntry, WarehousePhoto, TareType

LUNCH_NORM_MIN = 60   # норма обіду
DAY_HOURS = 8


def _rate(code, default):
    from apps.finance.models import FinModelArticle
    a = FinModelArticle.objects.filter(code=code).first()
    try:
        return Decimal(str(a.value)) if a else Decimal(str(default))
    except Exception:
        return Decimal(str(default))


def _packing_tiers(weight):
    """Авто-розбивка ваги на місця ≤20кг → рівні упаковки."""
    w = float(weight or 0)
    t = {"T5": 0, "T10": 0, "T20": 0}
    while w > 0.001:
        if w <= 5:
            t["T5"] += 1; w = 0
        elif w <= 10:
            t["T10"] += 1; w = 0
        elif w <= 20:
            t["T20"] += 1; w = 0
        else:
            t["T20"] += 1; w -= 20
    return t


def _deal_weight(deal):
    w = Decimal("0")
    for it in deal.items.all():
        if not it.product_id:
            continue  # своя позиція без номенклатури — ваги не має
        w += (it.product.weight_kg or Decimal("0")) * it.quantity
    return w


def _job_dict(job, full=False):
    deal = job.deal
    q = deal.qualification or {}
    d = {
        "id": job.id, "status": job.status, "deal_id": deal.id,
        "client": (deal.contact.first_name if deal.contact_id else None) or (deal.title or ""),
        "city": q.get("city", ""), "ship": q.get("ship", ""), "ttn": deal.ttn or "",
        "kits": q.get("kits", []) or [], "tinted_kits": job.tinted_kits or [],
        "packed": job.packed,
        "assignee": job.assignee_id, "assignee_name": (job.assignee.get_full_name() if job.assignee_id else ""),
        "created_at": job.created_at.isoformat(),
    }
    fn = (deal.funnel.name if deal.funnel_id else "") or ""
    d["funnel"] = fn
    d["kind_type"] = "test" if "\u0442\u0435\u0441\u0442\u043e\u0432" in fn.lower() else "main"
    d["channel"] = "offline" if any(x in fn.lower() for x in ["салон", "покрыт", "покритт"]) else "online"
    try:
        d["np_stage"] = (job.deal.stage.name if (job.deal_id and getattr(job.deal, "stage_id", None)) else "")
    except Exception:
        d["np_stage"] = ""
    d["photos_n"] = job.photos.count()
    d["ref_photos_n"] = len(deal.ref_photos or [])
    try:
        d["np_name"] = ((deal.np_data or {}).get("recipient") or {}).get("name") or ""
    except Exception:
        d["np_name"] = ""
    # «Одна посилка»: звʼязані дозамовлення/родитель без ТТН — щоб склад пакував разом і робив ОДНУ ТТН
    try:
        from apps.crm.models import Deal as _Dl
        _root = deal.parent_deal or deal
        _gids = set([_root.id]) | set(_root.children.values_list("id", flat=True))
        _gids.discard(deal.id)
        d["parcel_orders"] = [{"id": gd.id, "title": gd.title, "is_dozakaz": bool(gd.parent_deal_id)}
                              for gd in _Dl.objects.filter(id__in=_gids) if not gd.ttn]
        d["parcel_main"] = _root.id
        d["is_dozakaz"] = bool(deal.parent_deal_id)
    except Exception:
        d["parcel_orders"] = []; d["parcel_main"] = deal.id; d["is_dozakaz"] = False
    # підзадачі: дозамовлення цієї посилки (показуємо всередині основної задачі)
    try:
        _subs = WarehouseJob.objects.filter(deal__parent_deal_id=deal.id).exclude(status="cancelled").select_related("deal")
        d["subtasks"] = [{"job_id": sj.id, "deal_id": sj.deal_id, "title": sj.deal.title, "status": sj.status,
                          "kits_n": len((sj.deal.qualification or {}).get("kits", []) or []),
                          "items": [{"name": (it.product.name if it.product_id else (it.custom_name or "Позиція")), "qty": str(it.quantity)} for it in sj.deal.items.all()]}
                         for sj in _subs]
    except Exception:
        d["subtasks"] = []
    if full:
        d["items"] = [{"name": (it.product.name if it.product_id else ((it.custom_name or "Позиція") + " · не зі складу")), "qty": str(it.quantity),
                       "weight_kg": str((it.product.weight_kg or 0) if it.product_id else 0)} for it in deal.items.all()]
        d["weight_kg"] = str(_deal_weight(deal))
        d["photos"] = [{"id": p.id, "kind": p.kind, "url": "/api/warehouse/jobs/%d/photo/?kind=%s" % (job.id, p.kind)} for p in job.photos.all()]
        d["needs"] = {k: v for k, v in (deal.qualification or {}).items() if k != "kits" and not str(k).startswith("_")}
        d["ref_photos"] = deal.ref_photos or []
        d["phone"] = ((deal.contact.phone if deal.contact_id else "") or "")
    return d


def _is_nested(job):
    """Дозамовлення, що їде посилкою основної (у якої є активна задача) — ховаємо з черги, показуємо підзадачею."""
    pid = job.deal.parent_deal_id if job.deal_id else None
    if not pid:
        return False
    return WarehouseJob.objects.filter(deal_id=pid).exclude(status__in=["shipped", "cancelled"]).exists()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def queue(request):
    jobs = (WarehouseJob.objects.filter(status="queued", assignee__isnull=True)
            .select_related("deal", "deal__contact", "deal__stage").order_by("created_at")[:50])
    mine = (WarehouseJob.objects.filter(assignee=request.user)
            .exclude(status__in=["shipped", "cancelled"]).select_related("deal", "deal__contact", "deal__stage")[:50])
    shipped = (WarehouseJob.objects.filter(assignee=request.user, status="shipped")
               .select_related("deal", "deal__contact", "deal__stage").order_by("-shipped_at")[:30])
    out = {"queue": [_job_dict(j) for j in jobs if not _is_nested(j)], "mine": [_job_dict(j) for j in mine if not _is_nested(j)], "shipped": [_job_dict(j) for j in shipped]}
    u = request.user
    if u.is_superuser or (hasattr(u, "has_perm_code") and (u.has_perm_code("warehouse.view.all") or u.has_perm_code("roles.manage"))):
        # керівник/адмін: УСІ активні задачі всіх співробітників (хто що робить зараз)
        act = (WarehouseJob.objects.exclude(status__in=["shipped", "cancelled"]).exclude(assignee__isnull=True)
               .select_related("deal", "deal__contact", "deal__stage", "assignee").order_by("-created_at")[:80])
        from django.utils import timezone as _tz
        from datetime import timedelta as _td
        recent = (WarehouseJob.objects.filter(status="shipped", shipped_at__gte=_tz.now() - _td(days=7))
                  .select_related("deal", "deal__contact", "deal__stage", "assignee").order_by("-shipped_at")[:40])
        out["all_active"] = [_job_dict(j) for j in act if not _is_nested(j)]
        out["all_shipped_7d"] = [_job_dict(j) for j in recent]
    return Response(out)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def job_detail(request, pk):
    job = WarehouseJob.objects.filter(pk=pk).select_related("deal").first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    return Response(_job_dict(job, full=True))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def deal_shipment(request, deal_id):
    """Задача відвантаження по сделці (read-only): статус, фото складовщика, дати."""
    job = (WarehouseJob.objects.filter(deal_id=deal_id)
           .select_related("deal", "deal__contact", "deal__stage", "assignee").order_by("-created_at").first())
    if not job:
        return Response({"job": None})
    d = _job_dict(job, full=True)
    d["taken_at"] = job.taken_at.isoformat() if job.taken_at else None
    d["shipped_at"] = job.shipped_at.isoformat() if job.shipped_at else None
    d["shipped_weight_kg"] = str(job.shipped_weight_kg or 0)
    return Response({"job": d})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shipments_history(request):
    """Історія відвантажень з фільтром за період + пошук по № сделки / клієнту."""
    from django.db.models import Q as _Qh
    u = request.user
    if not (u.is_superuser or (hasattr(u, "has_perm_code") and (u.has_perm_code("warehouse.view.all") or u.has_perm_code("roles.manage") or u.has_perm_code("warehouse.view")))):
        return Response({"detail": "Немає доступу"}, status=403)
    qs = WarehouseJob.objects.select_related("deal", "deal__contact", "deal__stage", "assignee")
    frm = (request.GET.get("from") or "").strip()
    to = (request.GET.get("to") or "").strip()
    if frm:
        qs = qs.filter(created_at__date__gte=frm)
    if to:
        qs = qs.filter(created_at__date__lte=to)
    emp = (request.GET.get("employee") or "").strip()
    if emp.isdigit():
        qs = qs.filter(assignee_id=int(emp))
    q = (request.GET.get("q") or "").strip()
    if q:
        cond = (_Qh(deal__contact__first_name__icontains=q) | _Qh(deal__contact__last_name__icontains=q)
                | _Qh(deal__title__icontains=q) | _Qh(np_ttn__icontains=q))
        _num = q.replace("#", "").strip()
        if _num.isdigit():
            cond |= _Qh(deal_id=int(_num))
        qs = qs.filter(cond)
    qs = qs.order_by("-created_at")[:200]
    rows = []
    for j in qs:
        d = _job_dict(j)
        d["taken_at"] = j.taken_at.isoformat() if j.taken_at else None
        d["shipped_at"] = j.shipped_at.isoformat() if j.shipped_at else None
        rows.append(d)
    return Response({"rows": rows, "count": len(rows)})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def reassign(request, pk):
    """Змінити відповідального за задачу складу. GET → список складських співробітників.
    POST {user_id} (0 = зняти виконавця, задача повертається у чергу). Право: керівник."""
    from django.contrib.auth import get_user_model
    u = request.user
    is_mgr = bool(u.is_superuser or (hasattr(u, "has_perm_code") and (
        u.has_perm_code("warehouse.view.all") or u.has_perm_code("roles.manage") or u.has_perm_code("warehouse.reassign"))))
    if not is_mgr:
        return Response({"detail": "Потрібне право «Передавати задачі складу»"}, status=403)
    U = get_user_model()
    if request.method == "GET":
        pool = (U.objects.filter(is_active=True)
                .filter(department__name__icontains="Склад").order_by("first_name"))
        if not pool.exists():
            pool = U.objects.filter(is_active=True, is_superuser=False).order_by("first_name")[:30]
        return Response([{"id": x.id, "name": (x.get_full_name() or x.username)} for x in pool])
    with transaction.atomic():
        job = WarehouseJob.objects.select_for_update().filter(pk=pk).first()
        if not job:
            return Response({"detail": "no job"}, status=404)
        uid = int(request.data.get("user_id") or 0)
        old_name = job.assignee.get_full_name() if job.assignee_id else "—"
        if uid == 0:
            if job.status in ("shipped", "cancelled"):
                return Response({"detail": "Задача вже завершена — в чергу не повертається"}, status=400)
            job.assignee = None
            job.status = "queued"
            job.save(update_fields=["assignee", "status"])
            new_name = "черга"
        else:
            target = U.objects.filter(id=uid, is_active=True).first()
            if not target:
                return Response({"detail": "співробітника не знайдено"}, status=400)
            job.assignee = target
            if job.status == "queued":
                job.status = "taken"
                job.taken_at = timezone.now()
                job.save(update_fields=["assignee", "status", "taken_at"])
            else:
                job.save(update_fields=["assignee"])
            new_name = target.get_full_name() or target.username
        if job.task_id:
            job.task.assignee = job.assignee
            job.task.save(update_fields=["assignee"])
        # каскад на дозамовлення цієї посилки (той самий виконавець / у чергу)
        for _sub in WarehouseJob.objects.filter(deal__parent_deal_id=job.deal_id).exclude(status__in=["shipped", "cancelled"]):
            _sub.assignee = job.assignee
            if job.assignee_id is None:
                _sub.status = "queued"
            elif _sub.status == "queued":
                _sub.status = "taken"; _sub.taken_at = _sub.taken_at or timezone.now()
            _sub.save()
            if _sub.task_id:
                _sub.task.assignee = job.assignee; _sub.task.save(update_fields=["assignee"])
        try:
            from apps.crm.models import log_activity
            log_activity("deal", job.deal_id, "Склад: зміна виконавця", "%s → %s" % (old_name, new_name), u)
        except Exception:
            pass
    return Response(_job_dict(job, full=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def take(request, pk):
    with transaction.atomic():
        job = WarehouseJob.objects.select_for_update().filter(pk=pk).first()
        if not job:
            return Response({"detail": "no job"}, status=404)
        if job.assignee_id and job.assignee_id != request.user.id:
            return Response({"detail": "taken", "by": job.assignee.get_full_name()}, status=409)
        job.assignee = request.user; job.status = "taken"; job.taken_at = timezone.now()
        job.save(update_fields=["assignee", "status", "taken_at"])
        if job.task_id:
            job.task.status = "in_progress"; job.task.assignee = request.user
            job.task.save(update_fields=["status", "assignee"])
        # каскад: дозамовлення цієї посилки бере той самий складовщик (одна коробка)
        for _sub in WarehouseJob.objects.filter(deal__parent_deal_id=job.deal_id).exclude(status__in=["shipped", "cancelled"]):
            if not _sub.assignee_id:
                _sub.assignee = request.user; _sub.status = "taken"; _sub.taken_at = timezone.now()
                _sub.save(update_fields=["assignee", "status", "taken_at"])
                if _sub.task_id:
                    _sub.task.status = "in_progress"; _sub.task.assignee = request.user; _sub.task.save(update_fields=["status", "assignee"])
        # склад узяв замовлення в роботу → сделка йде у «Відвантаження» (за НАЗВОЮ стадії).
        # «Заброньовано» ставиться лише оплатою з типом «Бронь», склад його НЕ ставить.
        try:
            deal = job.deal
            st = (deal.stage.name if deal.stage_id else "").lower()
            if deal.stage_id and (("оплат" in st and "отриман" in st) or "заброньов" in st or "оплата/предоплата" in st):
                target = deal.funnel.stages.filter(name__icontains="відвантаж").order_by("order").first()
                if not target:
                    target = deal.funnel.stages.filter(name__icontains="в работе").order_by("order").first()
                if target and target.order > deal.stage.order:
                    from apps.crm.views import _advance_deal_stage
                    _advance_deal_stage(deal, target.order, "Склад узяв задачу в роботу (%s)" % (request.user.get_full_name() or request.user.username))
        except Exception:
            pass
    return Response(_job_dict(job, full=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def tinting(request, pk):
    job = WarehouseJob.objects.filter(pk=pk, assignee=request.user).first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    if job.status in ("shipped", "cancelled"):
        return Response({"detail": "Задача вже завершена"}, status=400)
    idx = request.data.get("kit")
    tinted = set(job.tinted_kits or [])
    if idx is not None:
        idx = int(idx)
        tinted.discard(idx) if idx in tinted else tinted.add(idx)
    job.tinted_kits = sorted(tinted)
    if job.status in ("taken",):
        job.status = "tinting"
    job.save(update_fields=["tinted_kits", "status"])
    return Response(_job_dict(job, full=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def packing(request, pk):
    job = WarehouseJob.objects.filter(pk=pk, assignee=request.user).first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    if job.status in ("shipped", "cancelled"):
        return Response({"detail": "Задача вже завершена"}, status=400)
    job.packed = bool(request.data.get("packed", True))
    job.status = "packing"
    try:
        if (job.deal.ttn or "").strip():
            kinds = set(p.kind for p in job.photos.all())
            if not ({"buckets", "parcel"} <= kinds):
                job.status = "awaiting_photos"
    except Exception:
        pass
    job.save(update_fields=["packed", "status"])
    return Response(_job_dict(job, full=True))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def photo(request, pk):
    if request.method == "GET":
        job = WarehouseJob.objects.filter(pk=pk).first()
        if not job:
            return Response({"detail": "no job"}, status=404)
        kind = request.GET.get("kind") or "buckets"
        p = job.photos.filter(kind=kind).order_by("-id").first()
        if not p or not p.image:
            return Response({"detail": "no photo"}, status=404)
        from django.http import HttpResponse
        import mimetypes
        try:
            data = p.image.read()
        except Exception:
            return Response({"detail": "file missing"}, status=404)
        ct = mimetypes.guess_type(p.image.name)[0] or "image/jpeg"
        return HttpResponse(data, content_type=ct)
    job = WarehouseJob.objects.filter(pk=pk, assignee=request.user).first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    f = request.FILES.get("image") or request.FILES.get("file")
    if not f:
        return Response({"detail": "no image"}, status=400)
    kind = request.GET.get("kind") or request.data.get("kind") or "buckets"
    WarehousePhoto.objects.create(job=job, deal=job.deal, employee=request.user, kind=kind, image=f)
    return Response({"ok": True, "photos": [{"id": p.id, "kind": p.kind} for p in job.photos.all()]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ship(request, pk):
    job = WarehouseJob.objects.filter(pk=pk, assignee=request.user).first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    if job.status == "shipped":
        # ідемпотентно: повторний клік/запит НЕ нараховує ЗП вдруге
        return Response(_job_dict(job, full=True))
    kinds = set(p.kind for p in job.photos.all())
    if not ({"buckets", "parcel"} <= kinds):
        job.status = "awaiting_photos"; job.save(update_fields=["status"])
        return Response({"detail": "Потрібні 2 фото: відерця + посилка"}, status=400)
    _finalize(job, request.user)
    # каскад: дозамовлення цієї посилки — та сама коробка → списання без подвійної упаковки/фото
    for _sub in WarehouseJob.objects.filter(deal__parent_deal_id=job.deal_id).exclude(status__in=["shipped", "cancelled"]):
        try:
            _finalize(_sub, request.user, pay_packing=False)
        except Exception:
            pass
    return Response(_job_dict(job, full=True))


def _finalize(job, user, pay_packing=True):
    today = timezone.now().date(); deal = job.deal
    weight = _deal_weight(deal); job.shipped_weight_kg = weight
    kits = (deal.qualification or {}).get("kits", []) or []
    total_kits = len(kits); tinted = len(job.tinted_kits or [])
    job.tintings_count = tinted
    amount = deal.amount or Decimal("0")
    job.tintings_base = (amount * Decimal(tinted) / Decimal(total_kits)) if total_kits else Decimal("0")
    tiers = _packing_tiers(weight) if (job.packed and pay_packing) else {"T5": 0, "T10": 0, "T20": 0}
    job.pack_le5_count = tiers["T5"]; job.pack_le10_count = tiers["T10"]; job.pack_le20_count = tiers["T20"]
    r_kg = _rate("WH_RATE_KG", 1.5); r5 = _rate("WH_PACK_5", 8); r10 = _rate("WH_PACK_10", 13)
    r20 = _rate("WH_PACK_20", 20); rtint = _rate("WH_TINT_PCT", 20) / Decimal("100")

    def add(op, amt, **kw):
        WarehousePayrollEntry.objects.create(employee=user, work_date=today, job=job, deal=deal,
                                             op_type=op, amount=amt.quantize(Decimal("0.01")), **kw)
    if weight > 0:
        add("shipment_weight", weight * r_kg, quantity_kg=weight, rate_applied=r_kg, note="%s кг" % weight)
    for tier, cnt, rate in [("T5", tiers["T5"], r5), ("T10", tiers["T10"], r10), ("T20", tiers["T20"], r20)]:
        if cnt > 0:
            add("packing", rate * cnt, pack_tier=tier, rate_applied=rate, note="%d шт" % cnt)
    if job.tintings_base > 0:
        add("tinting", job.tintings_base * rtint, base_value=job.tintings_base, rate_applied=rtint)
    job.done_snapshot = {"weight": str(weight), "tiers": tiers, "tint_base": str(job.tintings_base)}
    job.status = "shipped"; job.shipped_at = timezone.now(); job.save()
    from .services import realize_deal
    realize_deal(deal, user)  # спільне списання по собівартості + COGS, ідемпотентно (без подвійного списання)
    if job.task_id:
        job.task.status = "done"; job.task.save(update_fields=["status"])
    return job


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_salary(request):
    period = request.GET.get("period", "month")
    days = {"week": 7, "month": 30, "quarter": 90, "all": 3650}.get(period, 30)
    since = timezone.now().date() - datetime.timedelta(days=days)
    qs = WarehousePayrollEntry.objects.filter(employee=request.user, work_date__gte=since, status="confirmed")
    total = qs.aggregate(s=Sum("amount"))["s"] or 0
    lines = []
    for op in ["workday", "shipment_weight", "packing", "tinting", "bonus_initiative", "bonus_cleanliness", "error", "wrong_material"]:
        r = qs.filter(op_type=op).aggregate(s=Sum("amount"), n=Count("id"))
        if r["n"]:
            lines.append({"op": op, "amount": str(r["s"] or 0), "count": r["n"]})
    shipments = WarehouseJob.objects.filter(assignee=request.user, status="shipped", shipped_at__date__gte=since).count()
    tintings = qs.filter(op_type="tinting").count()
    return Response({"total": str(total), "lines": lines, "period": period,
                     "shipments": shipments, "tintings": tintings})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_shift(request):
    from apps.finance.models import WorkDay, WorkSession
    today = timezone.now().date()
    wd = WorkDay.objects.filter(user=request.user, date=today).first()
    sess = WorkSession.objects.filter(user=request.user, ended_at__isnull=True).order_by("-started_at").first()
    earned = WarehousePayrollEntry.objects.filter(employee=request.user, work_date=today, status="confirmed").aggregate(s=Sum("amount"))["s"] or 0
    lunch_min = (sess.paused_seconds // 60) if sess else 0
    return Response({"day_open": bool(sess), "earned_today": str(earned),
                     "lunch_min": lunch_min, "on_lunch": bool(sess and sess.paused_at),
                     "lunch_norm": LUNCH_NORM_MIN, "cleanliness_note": (wd.note if wd else "")})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def day_start(request):
    from apps.finance.models import WorkDay, WorkSession
    today = timezone.now().date()
    WorkDay.objects.get_or_create(user=request.user, date=today, defaults={"status": "worked"})
    if not WorkSession.objects.filter(user=request.user, ended_at__isnull=True).exists():
        WorkSession.objects.create(user=request.user)
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def day_close(request):
    from apps.finance.models import WorkSession, WorkDay
    today = timezone.now().date()
    sess = WorkSession.objects.filter(user=request.user, ended_at__isnull=True).order_by("-started_at").first()
    if sess:
        if sess.paused_at:
            sess.paused_seconds += int((timezone.now() - sess.paused_at).total_seconds()); sess.paused_at = None
        sess.ended_at = timezone.now(); sess.save()
        lunch_min = sess.paused_seconds // 60
        excess = max(0, lunch_min - LUNCH_NORM_MIN)
        day_rate = _rate("WH_RATE_DAY", 300)
        penalty = (Decimal(excess) / Decimal(60)) * (day_rate / Decimal(DAY_HOURS))
        day_pay = max(Decimal("0"), day_rate - penalty)
        note = "обід %d хв" % lunch_min + ((" (-%s за перебір)" % penalty.quantize(Decimal("0.01"))) if excess else "")
        if not WarehousePayrollEntry.objects.filter(employee=request.user, work_date=today, op_type="workday").exists():
            WarehousePayrollEntry.objects.create(employee=request.user, work_date=today, op_type="workday",
                                                 amount=day_pay.quantize(Decimal("0.01")), rate_applied=day_rate, note=note)
    clean = (request.data.get("note") or "")[:160]
    if clean:
        wd = WorkDay.objects.filter(user=request.user, date=today).first()
        if wd:
            wd.note = clean; wd.save(update_fields=["note"])
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def lunch_toggle(request):
    from apps.finance.models import WorkSession
    sess = WorkSession.objects.filter(user=request.user, ended_at__isnull=True).order_by("-started_at").first()
    if not sess:
        return Response({"detail": "Спершу почни день"}, status=400)
    if sess.paused_at:
        sess.paused_seconds += int((timezone.now() - sess.paused_at).total_seconds()); sess.paused_at = None
    else:
        sess.paused_at = timezone.now()
    sess.save(update_fields=["paused_seconds", "paused_at"])
    return Response({"on_lunch": bool(sess.paused_at), "lunch_min": sess.paused_seconds // 60})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tare_types(request):
    return Response([{"id": t.id, "name": t.name, "max_fill_kg": str(t.max_fill_kg)}
                     for t in TareType.objects.filter(active=True)])


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def errors(request):
    from .models import WarehouseError
    if request.method == "POST":
        src = request.data.get("source", "manual_staff")
        e = WarehouseError.objects.create(
            job_id=request.data.get("job") or None, deal_id=request.data.get("deal") or None,
            reported_by=request.user, source=src, kind=request.data.get("kind", "other"),
            description=(request.data.get("description") or "")[:1000],
            deduction_uah=Decimal(str(request.data.get("deduction") or 0)),
            blamed_user_id=request.data.get("blamed") or (request.user.id if src == "manual_staff" else None))
        return Response({"ok": True, "id": e.id})
    qs = WarehouseError.objects.select_related("blamed_user", "deal")[:100]
    return Response([{"id": e.id, "deal": e.deal_id, "kind": e.get_kind_display(),
                      "desc": e.description, "deduction": str(e.deduction_uah), "status": e.status,
                      "blamed": (e.blamed_user.get_full_name() if e.blamed_user_id else ""),
                      "source": e.source, "at": e.created_at.isoformat()} for e in qs])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_error(request, pk):
    u = request.user
    if not (u.is_superuser or u.has_perm_code("roles.manage") or u.has_perm_code("warehouse.view.all")):
        return Response({"detail": "Підтверджувати помилки/утримання може лише керівник складу або адмін"}, status=403)
    from .models import WarehouseError
    e = WarehouseError.objects.filter(pk=pk).first()
    if not e:
        return Response({"detail": "no"}, status=404)
    if request.data.get("action") == "reject":
        e.status = "rejected"; e.save(update_fields=["status"]); return Response({"ok": True})
    if request.data.get("deduction") is not None:
        e.deduction_uah = Decimal(str(request.data.get("deduction")))
    e.status = "confirmed"; e.confirmed_by = request.user; e.confirmed_at = timezone.now(); e.save()
    if e.blamed_user_id and e.deduction_uah > 0:
        WarehousePayrollEntry.objects.create(
            employee_id=e.blamed_user_id, work_date=timezone.now().date(), deal_id=e.deal_id,
            op_type=("wrong_material" if e.kind == "wrong_material" else "error"),
            amount=-e.deduction_uah, status="confirmed", source="manual", note=e.get_kind_display())
    return Response({"ok": True})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def ideas(request):
    from .models import InitiativeIdea
    if request.method == "POST":
        i = InitiativeIdea.objects.create(author=request.user, text=(request.data.get("text") or "")[:2000])
        return Response({"ok": True, "id": i.id})
    return Response([{"id": i.id, "author": i.author.get_full_name(), "text": i.text,
                      "status": i.status, "award": str(i.award_uah), "at": i.created_at.isoformat()}
                     for i in InitiativeIdea.objects.select_related("author")[:100]])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def award_idea(request, pk):
    u = request.user
    if not (u.is_superuser or u.has_perm_code("roles.manage") or u.has_perm_code("warehouse.view.all")):
        return Response({"detail": "Нараховувати премії за ідеї може лише керівник складу або адмін"}, status=403)
    from .models import InitiativeIdea
    i = InitiativeIdea.objects.filter(pk=pk).first()
    if not i:
        return Response({"detail": "no"}, status=404)
    i.status = request.data.get("status", "accepted")
    award = Decimal(str(request.data.get("award") or 0))
    if award > 0 and i.award_uah == 0:
        i.award_uah = award; i.awarded_by = request.user
        WarehousePayrollEntry.objects.create(employee=i.author, work_date=timezone.now().date(),
                                             op_type="bonus_initiative", amount=award, status="confirmed",
                                             source="manual", note="Ідея")
    i.save()
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    """Зведення складу для керівника: по співробітниках + команда + онлайн/офлайн + період."""
    from django.contrib.auth import get_user_model
    from django.db.models import Sum
    period = request.GET.get("period", "month")
    days = {"week": 7, "month": 30, "quarter": 90, "all": 3650}.get(period, 30)
    since = timezone.now().date() - datetime.timedelta(days=days)
    U = get_user_model()
    emp_ids = set(WarehousePayrollEntry.objects.filter(work_date__gte=since).values_list("employee_id", flat=True))
    emp_ids |= set(WarehouseJob.objects.filter(status="shipped", shipped_at__date__gte=since, assignee__isnull=False).values_list("assignee_id", flat=True))
    OPS = ["workday", "shipment_weight", "packing", "tinting", "bonus_initiative", "error", "wrong_material"]
    rows = []
    for uid in emp_ids:
        u = U.objects.filter(id=uid).first()
        if not u:
            continue
        pe = WarehousePayrollEntry.objects.filter(employee_id=uid, work_date__gte=since, status="confirmed")
        total = pe.aggregate(s=Sum("amount"))["s"] or 0
        by = {op: float(pe.filter(op_type=op).aggregate(s=Sum("amount"))["s"] or 0) for op in OPS}
        ship = WarehouseJob.objects.filter(assignee_id=uid, status="shipped", shipped_at__date__gte=since)
        rows.append({"id": uid, "name": u.get_full_name() or u.username,
                     "shipments": ship.count(),
                     "weight": float(ship.aggregate(s=Sum("shipped_weight_kg"))["s"] or 0),
                     "tintings": int(sum(j.tintings_count for j in ship)),
                     "deductions": float(by["error"] + by["wrong_material"]),
                     "total": float(total), "by": by})
    rows.sort(key=lambda r: -r["total"])
    team = {"total": round(sum(r["total"] for r in rows), 2), "shipments": sum(r["shipments"] for r in rows),
            "weight": round(sum(r["weight"] for r in rows), 1), "tintings": sum(r["tintings"] for r in rows),
            "people": len(rows)}
    onoff = {"online": {"count": 0, "weight": 0.0, "value": 0.0}, "offline": {"count": 0, "weight": 0.0, "value": 0.0}}
    for j in WarehouseJob.objects.filter(status="shipped", shipped_at__date__gte=since).select_related("deal", "deal__funnel"):
        fn = (j.deal.funnel.name if (j.deal and j.deal.funnel_id) else "").lower()
        ch = "offline" if any(x in fn for x in ["салон", "покрыт", "покритт"]) else "online"
        onoff[ch]["count"] += 1
        onoff[ch]["weight"] += float(j.shipped_weight_kg or 0)
        onoff[ch]["value"] += float(j.deal.amount or 0) if j.deal else 0
    return Response({"period": period, "rows": rows, "team": team, "onoff": onoff, "ops": OPS})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_job(request, pk):
    """Видалити (скасувати) складську задачу — лише керівник складу/адмін. Soft: status=cancelled."""
    u = request.user
    is_mgr = bool(u.is_superuser or (hasattr(u, "has_perm_code") and (u.has_perm_code("warehouse.view.all") or u.has_perm_code("roles.manage"))))
    if not is_mgr:
        return Response({"detail": "Видаляти задачі може лише керівник складу"}, status=403)
    job = WarehouseJob.objects.filter(pk=pk).select_related("task").first()
    if not job:
        return Response({"detail": "no job"}, status=404)
    job.status = "cancelled"
    job.save(update_fields=["status"])
    if job.task_id:
        try:
            job.task.status = "cancelled"; job.task.save(update_fields=["status"])
        except Exception:
            pass
    return Response({"ok": True})
