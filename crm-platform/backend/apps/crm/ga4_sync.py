# -*- coding: utf-8 -*-
"""Google Analytics 4 → CRM: щоденна статистика сайтів Wallcov.

Доступ: сервісний акаунт ads-bot@ads-analytics-492919.iam.gserviceaccount.com
(роль «Читатель» на рівні GA-акаунта 130927577, додано 28.08.2026). Ключ —
у .env як GA4_SA_KEY_B64 (base64 JSON), список сайтів — GA4_PROPERTIES
(«property_id:домен,…»). Бібліотек Google НЕ використовуємо: JWT підписуємо
самі через cryptography (він уже в образі web).
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from django.utils import timezone

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
_token_cache = {"token": None, "exp": 0}


def ga4_properties() -> list[tuple[str, str]]:
    raw = os.environ.get("GA4_PROPERTIES", "").strip()
    out = []
    for chunk in raw.split(","):
        if ":" in chunk:
            pid, site = chunk.split(":", 1)
            out.append((pid.strip(), site.strip()))
    return out


def ga4_configured() -> bool:
    return bool(os.environ.get("GA4_SA_KEY_B64", "").strip() and ga4_properties())


def _b64u(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _access_token() -> str:
    if _token_cache["token"] and _token_cache["exp"] > time.time() + 60:
        return _token_cache["token"]
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = json.loads(base64.b64decode(os.environ["GA4_SA_KEY_B64"]))
    now = int(time.time())
    header = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64u(json.dumps({
        "iss": key["client_email"], "scope": SCOPE,
        "aud": TOKEN_URL, "iat": now, "exp": now + 3600,
    }).encode())
    signing_input = header + b"." + claims
    pk = serialization.load_pem_private_key(key["private_key"].encode(), password=None)
    signature = _b64u(pk.sign(signing_input, padding.PKCS1v15(), hashes.SHA256()))
    assertion = (signing_input + b"." + signature).decode()
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode()
    token = json.load(urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=30))
    _token_cache["token"] = token["access_token"]
    _token_cache["exp"] = time.time() + int(token.get("expires_in", 3600))
    return _token_cache["token"]


def _run_report(property_id: str, body: dict) -> dict:
    request = urllib.request.Request(
        "https://analyticsdata.googleapis.com/v1beta/properties/%s:runReport" % property_id,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + _access_token(), "Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(request, timeout=60))


def sync_ga4(days: int = 30) -> dict:
    """Тягне по кожному сайту денні sessions/users/new/key events + топ джерел."""
    from .models import Ga4DailyStat

    if not ga4_configured():
        return {"error": "GA4 not configured (GA4_SA_KEY_B64 / GA4_PROPERTIES)"}
    since = (timezone.localdate() - timedelta(days=max(1, days))).isoformat()
    until = timezone.localdate().isoformat()
    saved = 0
    errors = []
    for property_id, site in ga4_properties():
        try:
            daily = _run_report(property_id, {
                "dateRanges": [{"startDate": since, "endDate": until}],
                "dimensions": [{"name": "date"}],
                "metrics": [{"name": "sessions"}, {"name": "activeUsers"},
                            {"name": "newUsers"}, {"name": "keyEvents"},
                            {"name": "engagementRate"}, {"name": "averageSessionDuration"}],
                "limit": 400,
            })
            channels = _run_report(property_id, {
                "dateRanges": [{"startDate": since, "endDate": until}],
                "dimensions": [{"name": "date"}, {"name": "sessionDefaultChannelGroup"}],
                "metrics": [{"name": "sessions"}, {"name": "keyEvents"}],
                "limit": 2000,
            })
            ch_by_day: dict[str, dict] = {}
            for row in channels.get("rows") or []:
                day = row["dimensionValues"][0]["value"]
                group = row["dimensionValues"][1]["value"] or "(other)"
                sessions_n = int(float(row["metricValues"][0]["value"] or 0))
                key_n = int(float(row["metricValues"][1]["value"] or 0))
                ch_by_day.setdefault(day, {})[group] = {"s": sessions_n, "k": key_n}
            sources = _run_report(property_id, {
                "dateRanges": [{"startDate": since, "endDate": until}],
                "dimensions": [{"name": "date"}, {"name": "sessionSourceMedium"}],
                "metrics": [{"name": "sessions"}],
                "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
                "limit": 2000,
            })
            src_by_day: dict[str, dict] = {}
            for row in sources.get("rows") or []:
                day = row["dimensionValues"][0]["value"]
                medium = row["dimensionValues"][1]["value"]
                cnt = int(float(row["metricValues"][0]["value"] or 0))
                bucket = src_by_day.setdefault(day, {})
                if len(bucket) < 10:
                    bucket[medium] = bucket.get(medium, 0) + cnt
            for row in daily.get("rows") or []:
                raw_day = row["dimensionValues"][0]["value"]  # YYYYMMDD
                day = date(int(raw_day[:4]), int(raw_day[4:6]), int(raw_day[6:8]))
                raw_values = [float(v["value"] or 0) for v in row["metricValues"]]
                Ga4DailyStat.objects.update_or_create(
                    property_id=property_id, date=day,
                    defaults={
                        "site": site,
                        "sessions": int(raw_values[0]), "active_users": int(raw_values[1]),
                        "new_users": int(raw_values[2]), "key_events": int(raw_values[3]),
                        "engagement_rate": round(raw_values[4] * 100, 1),
                        "avg_duration_sec": int(raw_values[5]),
                        "sources": src_by_day.get(raw_day, {}),
                        "channels": ch_by_day.get(raw_day, {}),
                    },
                )
                saved += 1
        except Exception as exc:  # одна зламана property не валить решту
            errors.append("%s: %s" % (site, str(exc)[:160]))
    try:
        from django.core.cache import cache as _c
        _c.set("mm_ver", int(_c.get("mm_ver", 0)) + 1, None)
    except Exception:
        pass
    return {"saved": saved, "since": since, "until": until, "errors": errors}
