"""Аналітика TikTok (@dekor_dlia_stin) — знімки метрик з TikTok Business API.

Окремий застосунок: НЕ чіпає inbox/Meta-маркетинг. Дані тягне tiktok_sync (крон на хості),
читає сторінка «TikTok» у CRM. Джерело: /business/get/ (акаунт+аудиторія, добові метрики)
та /business/video/list/ (метрики кожного відео).
"""
from django.db import models


class TtDailyStat(models.Model):
    """Один день акаунта TikTok: скільки прийшло/пішло підписників, перегляди, кліки."""
    date = models.DateField(unique=True, db_index=True)
    followers_total = models.IntegerField(default=0)      # daily_total_followers
    followers_gained = models.IntegerField(default=0)     # daily_new_followers
    followers_lost = models.IntegerField(default=0)       # daily_lost_followers
    profile_views = models.IntegerField(default=0)
    video_views = models.IntegerField(default=0)
    unique_video_views = models.IntegerField(default=0)
    likes = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    shares = models.IntegerField(default=0)
    engagement_rate = models.FloatField(default=0.0)
    bio_link_clicks = models.IntegerField(default=0)
    email_clicks = models.IntegerField(default=0)
    phone_clicks = models.IntegerField(default=0)
    address_clicks = models.IntegerField(default=0)
    lead_submissions = models.IntegerField(default=0)
    raw = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return "TikTok %s: +%s підписників" % (self.date, self.followers_gained)


class TtAccountSnapshot(models.Model):
    """Останній зріз акаунта: лічильники + аудиторія (вік/стать/гео) + активність по годинах.
    Один рядок (id=1), перезаписується кожним синком."""
    followers_count = models.IntegerField(default=0)
    total_likes = models.BigIntegerField(default=0)
    videos_count = models.IntegerField(default=0)
    audience_ages = models.JSONField(default=list, blank=True)       # [{age, percentage}]
    audience_genders = models.JSONField(default=list, blank=True)    # [{gender, percentage}]
    audience_countries = models.JSONField(default=list, blank=True)  # [{country, percentage}]
    audience_cities = models.JSONField(default=list, blank=True)     # [{city, percentage}]
    audience_activity = models.JSONField(default=list, blank=True)   # [{hour, count}] — коли аудиторія онлайн
    averages = models.JSONField(default=dict, blank=True)            # average_views/likes/comments/shares, engagement_rate...
    profile = models.JSONField(default=dict, blank=True)             # username, display_name, profile_image, bio...
    fetched_at = models.DateTimeField(auto_now=True)


class TtVideo(models.Model):
    """Метрики одного відео TikTok (оновлюються кожним синком)."""
    item_id = models.CharField(max_length=32, unique=True, db_index=True)
    caption = models.TextField(blank=True, default="")
    create_time = models.DateTimeField(null=True, blank=True, db_index=True)
    thumbnail_url = models.TextField(blank=True, default="")
    share_url = models.TextField(blank=True, default="")
    duration = models.FloatField(default=0.0)
    views = models.BigIntegerField(default=0)
    reach = models.BigIntegerField(default=0)
    likes = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    shares = models.IntegerField(default=0)
    average_time_watched = models.FloatField(default=0.0)
    full_video_watched_rate = models.FloatField(default=0.0)
    total_time_watched = models.FloatField(default=0.0)
    impression_sources = models.JSONField(default=list, blank=True)  # [{impression_source, percentage}]
    audience_countries = models.JSONField(default=list, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-create_time"]

    def __str__(self):
        return "TikTok video %s (%s views)" % (self.item_id, self.views)
