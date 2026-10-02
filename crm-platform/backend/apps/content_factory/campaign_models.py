"""Campaigns coordinate existing factory objects; they never duplicate media."""
from django.conf import settings
from django.db import models


class ContentCampaign(models.Model):
    title = models.CharField(max_length=200)
    goal = models.CharField(max_length=500)
    audience = models.CharField(max_length=300)
    offer = models.CharField(max_length=500, blank=True)
    blog = models.ForeignKey("content_factory.Blog", on_delete=models.PROTECT)
    product = models.ForeignKey("warehouse.Product", on_delete=models.PROTECT)
    product_snapshot = models.JSONField(default=dict)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    budget_usd = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    archived = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class CampaignMaterial(models.Model):
    campaign = models.ForeignKey(ContentCampaign, on_delete=models.CASCADE, related_name="materials")
    reel = models.OneToOneField("content_factory.ReelDraft", null=True, blank=True, on_delete=models.CASCADE)
    carousel = models.OneToOneField("content_factory.Carousel", null=True, blank=True, on_delete=models.CASCADE)
    post = models.OneToOneField("content_factory.TgPost", null=True, blank=True, on_delete=models.CASCADE)
    planned_on = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=1000, blank=True)
    approved_hash = models.CharField(max_length=64, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    review_checks = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["planned_on", "id"]
        constraints = [models.CheckConstraint(
            check=(models.Q(reel__isnull=False, carousel__isnull=True, post__isnull=True)
                   | models.Q(reel__isnull=True, carousel__isnull=False, post__isnull=True)
                   | models.Q(reel__isnull=True, carousel__isnull=True, post__isnull=False)),
            name="cf_campaign_material_one_target")]

    @property
    def target(self):
        return self.reel or self.carousel or self.post

    @property
    def kind(self):
        return "reel" if self.reel_id else "carousel" if self.carousel_id else "post"
