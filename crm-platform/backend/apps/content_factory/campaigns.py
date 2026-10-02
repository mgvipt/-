"""Campaign planning and version-bound review. No paid calls or outbound messages."""
import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.warehouse.models import Product
from apps.inbox.models import SharedLink
from .models import Blog, CampaignMaterial, Carousel, ContentCampaign, ReelDraft, TgPost, VideoScene
from .views import _Base

TARGETS = {"reel": ReelDraft, "carousel": Carousel, "post": TgPost}
LABELS = {"planned": "План", "working": "В работе", "review": "Нужна проверка", "approved": "Согласовано",
          "changed": "Изменено после согласования", "published": "Опубликовано", "error": "Ошибка", "rejected": "Отклонено"}


def product_data(p):
    return {"id": p.pk, "name": p.name, "sku": p.sku, "price": format(Decimal(str(p.price)), ".2f"), "currency": p.currency,
            "unit": p.unit, "consumption_per_m2": format(Decimal(str(p.consumption_per_m2)), ".4f") if p.consumption_per_m2 is not None else None,
            "description": p.description, "is_active": p.is_active}


def snapshot(p):
    return {"source": "CRM: карточка товара", "captured_at": timezone.now().isoformat(), "product": product_data(p)}


def content_hash(obj):
    # All editorial/render inputs, including voice references in brief, are versioned.
    # Operational fields must not invalidate review when publishing succeeds.
    excluded = {"id", "status", "published", "created_at", "updated_at", "busy", "error", "stage", "review",
                "scheduled_at", "published_at", "tg_message_id", "publish_error", "views", "reactions",
                "reactions_detail", "stats_at", "model"}
    data = {f.attname: getattr(obj, f.attname) for f in obj._meta.fields if f.name not in excluded}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def review_hash(item):
    c = item.campaign
    data = [content_hash(item.target), c.goal, c.audience, c.offer, c.product_id, c.product_snapshot, c.blog_id]
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def readiness(item):
    obj = item.target
    errors = []
    if item.campaign.archived:
        errors.append("Кампания в архиве.")
    if item.campaign.product_snapshot.get("product") != product_data(item.campaign.product):
        errors.append("Карточка товара изменилась: обновите паспорт и проверьте факты.")
    if not item.campaign.product.is_active:
        errors.append("Товар скрыт в номенклатуре.")
    if getattr(obj, "busy", False):
        errors.append("Обработка материала ещё идёт.")
    if getattr(obj, "error", ""):
        errors.append("В редакторе есть ошибка — проверьте её перед согласованием.")
    if item.kind != "post" and obj.blog_id != item.campaign.blog_id:
        errors.append("Блог материала отличается от блога кампании.")
    if item.kind == "reel":
        if not obj.file_id:
            errors.append("Сначала соберите и просмотрите видео в редакторе.")
        if not obj.beats:
            errors.append("Нет раскадровки.")
        scene_ids = {b.get("scene_id") for b in obj.beats if b.get("scene_id")}
        image_ids = {b.get("image_id") for b in obj.beats if b.get("image_id")}
        scenes = set(VideoScene.objects.filter(pk__in=scene_ids, asset__hidden=False).values_list("pk", flat=True))
        images = set(SharedLink.objects.filter(pk__in=image_ids).values_list("pk", flat=True))
        for n, beat in enumerate(obj.beats, 1):
            if not (beat.get("scene_id") or beat.get("image_id")):
                errors.append(f"Кадр {n}: не выбран исходник.")
            elif beat.get("image_id") and beat["image_id"] not in images:
                errors.append(f"Кадр {n}: изображение недоступно.")
            elif not beat.get("image_id") and beat.get("scene_id") not in scenes:
                errors.append(f"Кадр {n}: сцена удалена или исходник скрыт.")
    elif item.kind == "carousel":
        if not obj.slides or any(not s.get("rendered_id") for s in obj.slides):
            errors.append("Сначала соберите все слайды в редакторе.")
    elif not obj.text.strip():
        errors.append("Нет текста поста.")
    return errors


def material_data(item):
    obj = item.target
    digest = review_hash(item)
    errors = readiness(item)
    published = getattr(obj, "published", {}) if item.kind != "post" else ({"telegram": {"id": obj.tg_message_id}} if obj.status == "published" else {})
    approved = bool(item.approved_hash and item.approved_hash == digest and not errors and obj.status != "rejected")
    if published:
        state = "published"
    elif getattr(obj, "busy", False):
        state = "working"
    elif getattr(obj, "error", "") or getattr(obj, "publish_error", ""):
        state = "error"
    elif obj.status == "rejected":
        state = "rejected"
    elif item.approved_hash and not approved:
        state = "changed"
    elif approved:
        state = "approved"
    else:
        state = "planned" if errors else "review"
    return {"id": item.id, "kind": item.kind, "target_id": obj.pk, "title": obj.title,
            "state": state, "state_label": LABELS[state], "issues": errors,
            "version": digest, "approved_at": item.approved_at, "approval_current": approved,
            "planned_on": item.planned_on, "note": item.note, "published": published,
            "editor_tab": {"reel": "reels", "carousel": "carousels", "post": "telegram"}[item.kind],
            "blog_id": item.campaign.blog_id}


def campaign_data(c):
    items = [material_data(i) for i in c.materials.select_related("reel", "carousel", "post", "campaign__product", "campaign__blog")]
    counts = {key: sum(i["state"] == key for i in items) for key in LABELS}
    ready = counts["approved"] + counts["published"]
    state = "Архив" if c.archived else "План" if not items else "Завершена" if counts["published"] == len(items) else "Готова к публикации" if ready == len(items) else "В работе"
    return {"id": c.id, "title": c.title, "goal": c.goal, "audience": c.audience, "offer": c.offer,
            "blog_id": c.blog_id, "blog_name": c.blog.name, "product_id": c.product_id,
            "product_snapshot": c.product_snapshot, "product_current": product_data(c.product),
            "product_changed": c.product_snapshot.get("product") != product_data(c.product),
            "starts_on": c.starts_on, "ends_on": c.ends_on, "budget_usd": c.budget_usd,
            "archived": c.archived, "revision": c.revision, "state": state, "counts": counts,
            "ready": ready, "total": len(items), "materials": items,
            "budget_note": "Плановый бюджет. Расходы по кампании ещё не распределяются автоматически."}


def require_current_approval(obj):
    """Called by existing publishers; materials outside campaigns keep their existing flow."""
    kind = next(k for k, cls in TARGETS.items() if isinstance(obj, cls))
    item = CampaignMaterial.objects.select_related("campaign__product", "campaign__blog", "reel", "carousel", "post").filter(**{kind: obj}).first()
    if item:
        # Use the publisher's freshly loaded instance.
        setattr(item, kind, obj)
        if not material_data(item)["approval_current"]:
            raise ValueError("Откройте кампанию и согласуйте текущую версию материала: текст, кадры, факты и права.")


class CampaignInput(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    goal = serializers.CharField(max_length=500)
    audience = serializers.CharField(max_length=300)
    offer = serializers.CharField(max_length=500, required=False, allow_blank=True)
    blog_id = serializers.PrimaryKeyRelatedField(queryset=Blog.objects.exclude(slug__in=["marketing", "business"]), source="blog")
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True), source="product")
    starts_on = serializers.DateField(required=False, allow_null=True)
    ends_on = serializers.DateField(required=False, allow_null=True)
    budget_usd = serializers.DecimalField(max_digits=9, decimal_places=2, min_value=0, required=False, allow_null=True)
    archived = serializers.BooleanField(required=False)
    revision = serializers.IntegerField(required=False, min_value=1)

    def validate(self, data):
        old = self.context.get("campaign")
        start = data.get("starts_on", old.starts_on if old else None)
        end = data.get("ends_on", old.ends_on if old else None)
        if start and end and start > end:
            raise ValidationError("Окончание кампании должно быть не раньше начала.")
        return data


class CampaignListView(_Base):
    def get(self, request):
        qs = ContentCampaign.objects.select_related("blog", "product")
        if request.query_params.get("blog"):
            try:
                qs = qs.filter(blog_id=int(request.query_params["blog"]))
            except ValueError:
                raise ValidationError("Некорректный блог.")
        return Response({"campaigns": [campaign_data(c) for c in qs[:100]]})

    def post(self, request):
        s = CampaignInput(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        data.pop("revision", None)
        c = ContentCampaign.objects.create(**data, product_snapshot=snapshot(data["product"]), created_by=request.user)
        return Response(campaign_data(c), status=201)


class CampaignDetailView(_Base):
    def get(self, request, pk):
        return Response(campaign_data(get_object_or_404(ContentCampaign.objects.select_related("blog", "product"), pk=pk)))

    @transaction.atomic
    def patch(self, request, pk):
        c = get_object_or_404(ContentCampaign.objects.select_for_update(), pk=pk)
        s = CampaignInput(data=request.data, partial=True, context={"campaign": c})
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        if data.pop("revision", None) != c.revision:
            return Response({"error": "Кампания изменена в другом окне. Обновите страницу."}, status=409)
        if "blog" in data and data["blog"].pk != c.blog_id and c.materials.exists():
            raise ValidationError("Блог кампании с материалами менять нельзя.")
        for name, value in data.items():
            setattr(c, name, value)
        if "product" in data or request.data.get("refresh_product") is True:
            c.product_snapshot = snapshot(c.product)
        c.revision += 1
        c.save()
        return Response(campaign_data(c))


class CampaignChoicesView(_Base):
    def get(self, request):
        q = request.query_params.get("q", "").strip()[:100]
        products = Product.objects.filter(is_active=True)
        if q:
            products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
        return Response({"products": [{"id": p.id, "name": p.name, "sku": p.sku} for p in products.order_by("name")[:40]],
                         "blogs": list(Blog.objects.exclude(slug__in=["marketing", "business"]).values("id", "name", "slug"))})


class MaterialInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=list(TARGETS))
    target_id = serializers.IntegerField(min_value=1, required=False)
    title = serializers.CharField(max_length=200, required=False)
    planned_on = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class CampaignMaterialsView(_Base):
    def get(self, request, pk):
        c = get_object_or_404(ContentCampaign, pk=pk)
        result = []
        q = request.query_params.get("q", "").strip()[:100]
        for kind, cls in TARGETS.items():
            qs = cls.objects.filter(campaignmaterial__isnull=True)
            if kind != "post":
                qs = qs.filter(blog_id=c.blog_id)
            elif c.blog.slug != "wallcov":
                continue
            if q:
                qs = qs.filter(title__icontains=q)
            result.extend({"kind": kind, "id": o.pk, "title": o.title} for o in qs[:40])
        return Response({"materials": result})

    @transaction.atomic
    def post(self, request, pk):
        c = get_object_or_404(ContentCampaign.objects.select_for_update(), pk=pk)
        if c.archived:
            raise ValidationError("Сначала верните кампанию из архива.")
        s = MaterialInput(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        kind = d["kind"]
        cls = TARGETS[kind]
        if kind == "post" and c.blog.slug != "wallcov":
            raise ValidationError("Telegram-посты доступны только блогу Wallcov.")
        if d.get("target_id"):
            obj = get_object_or_404(cls.objects.select_for_update(), pk=d["target_id"])
            if kind != "post" and obj.blog_id != c.blog_id:
                raise ValidationError("Выберите материал того же блога.")
            if CampaignMaterial.objects.filter(**{kind: obj}).exists():
                return Response({"error": "Материал уже связан с кампанией."}, status=409)
        else:
            if not d.get("title"):
                raise ValidationError("Укажите название нового материала.")
            args = {"title": d["title"]}
            if kind != "post":
                args["blog"] = c.blog
            if kind == "reel":
                args.update(stage="idea", material=c.product.name[:80], topic=d["title"], brief={"goal": c.goal})
            obj = cls.objects.create(**args)
        item = CampaignMaterial.objects.create(campaign=c, **{kind: obj}, planned_on=d.get("planned_on"), note=d.get("note", ""))
        return Response(material_data(item), status=201)


class CampaignMaterialView(_Base):
    @transaction.atomic
    def post(self, request, pk, mid):
        campaign = get_object_or_404(ContentCampaign.objects.select_for_update(), pk=pk)
        item = get_object_or_404(CampaignMaterial.objects.select_for_update(), pk=mid, campaign_id=pk)
        obj = TARGETS[item.kind].objects.select_for_update().get(pk=item.target.pk)
        setattr(item, item.kind, obj)
        # Serialize against campaign edits as well as edits to this material.
        item.campaign = campaign
        digest = review_hash(item)
        if request.data.get("version") != digest:
            return Response({"error": "Материал изменился. Обновите и просмотрите новую версию."}, status=409)
        checks = request.data.get("checks", {})
        if not isinstance(checks, dict) or not all(checks.get(k) is True for k in ("facts", "visual", "rights")):
            raise ValidationError("Подтвердите факты, соответствие кадров словам и права использования.")
        errors = readiness(item)
        if errors:
            return Response({"error": " ".join(errors)}, status=400)
        if obj.status == "rejected":
            raise ValidationError("Верните отклонённый материал в работу в редакторе.")
        item.approved_hash, item.approved_at, item.approved_by = digest, timezone.now(), request.user
        item.review_checks = {k: True for k in ("facts", "visual", "rights")}
        item.save(update_fields=["approved_hash", "approved_at", "approved_by", "review_checks"])
        # This is an editorial review, not permission to schedule or send to a social account.
        return Response(material_data(item))

    @transaction.atomic
    def patch(self, request, pk, mid):
        item = get_object_or_404(CampaignMaterial.objects.select_for_update(), pk=mid, campaign_id=pk)
        class PlanInput(serializers.Serializer):
            planned_on = serializers.DateField(required=False, allow_null=True)
            note = serializers.CharField(max_length=1000, required=False, allow_blank=True)
        s = PlanInput(data=request.data)
        s.is_valid(raise_exception=True)
        for key, val in s.validated_data.items():
            setattr(item, key, val)
        item.save(update_fields=list(s.validated_data))
        return Response(material_data(item))
