"""Контент-завод, етап 3 (24.09.2026): стрічка рекомендацій і аналітик.

Стрічка: ролики сторінок, які відстежує Virale (ChatPlace MCP, уже оплачено). Раз на добу — по одному запиту
на сторінку з паузою (ChatPlace має жорсткий ліміт запитів, спільний з чатами CRM). Головний сигнал — «×N від
звичного»: перегляди ролика до медіани переглядів цього ж автора. Так видно, що саме «вистрілило», а не просто
у кого більше підписників.
Аналітик: раз на тиждень (вмикає власник) — один виклик ШІ зі зведенням: наш акаунт (Virale), теми питань
клієнтів, наші пости в Telegram, найсильніші ролики ніші. Ліміт на місяць, облік у «AI ЦЕНТР».
"""
import json
import statistics
import time
from datetime import timedelta

from django.db import DataError
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import questions
from .models import (AnalystReport, AnalystSettings, ContentChannel, FeedItem, QuestionTopic, TgPost)

SOURCE = "content_factory.analyst"
OWN_USERNAMES = {"dekor_dlia_stin"}
IG_BOT_ID = "647e28e9-73fd-4f06-81cc-5970409a7381"  # бот ChatPlace нашого Instagram — його дашборд Virale
PAUSE_SEC = 2.5
PRICE = {"claude-sonnet-4-6": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0)}


class BudgetError(Exception):
    pass


def _mcp(name, args=None):
    from apps.inbox.chatplace import _mcp as call
    return call(name, args or {})


def own_usernames():
    return OWN_USERNAMES | set(ContentChannel.objects.filter(role=ContentChannel.Role.OWN)
                               .values_list("handle", flat=True))


def _save_item(v, acc, own):
    FeedItem.objects.update_or_create(external_id=v["id"], defaults={
        "username": v.get("username") or acc.get("username", ""), "platform": v.get("platform", ""),
        "url": v.get("url", ""), "preview_url": v.get("previewUrl") or "", "caption": v.get("caption") or "",
        "media_type": v.get("mediaType", ""), "duration": v.get("duration"), "views": v.get("viewsCount"),
        "likes": v.get("likeCount"), "comments": v.get("commentsCount"), "engagement": v.get("engagementRate"),
        "viral_score": v.get("viralScore"), "is_own": (v.get("username") or "") in own,
        "published_at": parse_datetime((v.get("publishedAt") or "").replace(" ", "T") + "+00:00")
        if v.get("publishedAt") else None,
    })


def sync_feed(per_account=20):
    """Оновити стрічку з Virale. Повертає {"accounts": n, "items": m} або піднімає RuntimeError ChatPlace."""
    s = AnalystSettings.get()
    accounts = _mcp("virale_accounts_list") or []
    own = own_usernames()
    items = 0
    for acc in accounts:
        if acc.get("isRestricted"):
            continue
        time.sleep(PAUSE_SEC)
        try:
            data = _mcp("virale_videos_list", {"accountId": acc["id"], "limit": per_account, "sortBy": "date"}) or {}
        except RuntimeError:
            continue
        for v in data.get("data", []):
            try:
                _save_item(v, acc, own)
                items += 1
            except (DataError, KeyError, ValueError):  # один «кривий» ролик не зупиняє всю стрічку
                continue
    names = {(a.get("username") or "").lower() for a in accounts}  # що саме відстежує Virale — позначка в «Сторінках»
    ContentChannel.objects.filter(handle__in=names).update(in_virale=True)
    ContentChannel.objects.exclude(handle__in=names).update(in_virale=False)
    s.last_feed_sync_at = timezone.now()
    s.last_feed_note = f"{len(accounts)} сторінок, {items} роликів"
    s.save(update_fields=["last_feed_sync_at", "last_feed_note"])
    return {"accounts": len(accounts), "items": items}


def medians():
    """Медіана переглядів кожного автора (з усього, що є в базі)."""
    by = {}
    for u, v in FeedItem.objects.exclude(views=None).values_list("username", "views"):
        by.setdefault(u, []).append(v)
    return {u: statistics.median(vs) for u, vs in by.items() if vs}


def outlier(item, med):
    m = med.get(item.username)
    return round(item.views / m, 1) if m and item.views else None


def tracked_handles(blog=None):
    """Сторінки з розділу «Сторінки» (конкуренти й натхнення); з blog — лише сторінки цього блогу."""
    qs = ContentChannel.objects.filter(is_active=True).exclude(role=ContentChannel.Role.OWN)
    if blog is not None:
        qs = qs.filter(blog=blog)
    return set(qs.values_list("handle", flat=True))


def feed(days=7, sort="outlier", status="", include_own=False, limit=60, only_tracked=True, blog=None):
    since = timezone.now() - timedelta(days=days)
    qs = FeedItem.objects.filter(published_at__gte=since)
    handles = tracked_handles(blog) if only_tracked else set()
    if handles:
        qs = qs.filter(username__in=handles)
    elif blog is not None and only_tracked:
        qs = qs.none()  # у блогу ще немає сторінок для стрічки
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status=FeedItem.Status.HIDDEN)
    if not include_own:
        qs = qs.filter(is_own=False)
    med = medians()
    rows = [(i, outlier(i, med)) for i in qs]
    key = {"views": lambda r: -(r[0].views or 0), "er": lambda r: -(r[0].engagement or 0),
           "date": lambda r: -(r[0].published_at.timestamp() if r[0].published_at else 0)}.get(
        sort, lambda r: -(r[1] or 0))
    return sorted(rows, key=key)[:limit]


# ── Аналітик ────────────────────────────────────────────────────────────────────────────────────

def estimate_usd(model):
    pin, pout = PRICE.get(model, (3.0, 15.0))
    return round((6000 * pin + 1800 * pout) / 1_000_000, 4)


def build_inputs(days=7):
    since = timezone.now() - timedelta(days=days)
    inputs = {"period_days": days}
    try:  # наш акаунт і ніша з Virale (дашборд бота Instagram)
        dash = _mcp("virale_dashboard", {"botId": IG_BOT_ID}) or {}
        hero, niche = dash.get("accountHero") or {}, dash.get("nichePosition") or {}
        inputs["own"] = {k: hero.get(k) for k in ("username", "followers", "avgViews", "medianViews",
                                                   "avgEngagementRate", "postsPerWeek")}
        inputs["niche"] = {"views_p50": (niche.get("benchmarkPercentiles") or {}).get("viewsP50"),
                           "views_percentile": niche.get("viewsPercentile")}
        ca = dash.get("contentAnalysis") or {}
        inputs["own_top"] = [{"caption": (v.get("caption") or "")[:160], "views": v.get("views")}
                             for v in (ca.get("topVideos") or [])[:5]]
        inputs["own_worst"] = [{"caption": (v.get("caption") or "")[:120], "views": v.get("views")}
                               for v in (ca.get("worstVideos") or [])[:3]]
        inputs["gaps"] = [g.get("insight") for g in ((dash.get("nicheLandscape") or {}).get("gapAnalysis") or [])][:3]
    except Exception as e:  # ChatPlace недоступний — звіт без цього блоку
        inputs["own_error"] = str(e)[:120]
    inputs["questions"] = [{"title": t.title, "n": t.n} for t in QuestionTopic.objects.exclude(
        status=QuestionTopic.Status.IGNORED).annotate(n=Count("mentions", filter=Q(mentions__asked_at__gte=since)))
        .filter(n__gt=0).order_by("-n")[:12]]
    inputs["telegram"] = [{"title": p.title, "views": p.views, "reactions": p.reactions}
                          for p in TgPost.objects.filter(status=TgPost.Status.PUBLISHED, published_at__gte=since)]
    inputs["niche_hits"] = [{"user": i.username, "views": i.views, "x": x, "hook": (i.caption or "")[:140]}
                            for i, x in feed(days=days, sort="outlier", limit=10) if x and x >= 1.5]
    return inputs


SYSTEM = """Ти — аналітик контенту Wallcov (декоративні штукатурки й фарби, Україна). Власник — не маркетолог і не програміст:
пиши простою українською, коротко, без англіцизмів і жаргону. Аудиторія Wallcov — жінки, що роблять ремонт самі.

Отримаєш JSON із цифрами за період: наш Instagram (Virale), позиція в ніші, питання клієнтів з CRM, наші пости
в Telegram, ролики конкурентів, що «вистрілили» (x — у скільки разів більше переглядів, ніж зазвичай у автора).
Не вигадуй цифр, яких немає. Якщо даних мало — так і скажи. Гачки ідей — без шаблонів «Плануєш… і не знаєш», «Хочеш…, але боїшся» і без емодзі.

Відповідай ЛИШЕ JSON:
{"summary": "3–6 коротких абзаців: що спрацювало, що ні і чому, що робити цього тижня. Абзаци розділяй \\n\\n",
 "ideas": [{"title": "назва ідеї", "hook": "перше речення/кадр ролика", "why": "чому саме це (з яких цифр)",
            "format": "рилс / карусель / пост TG", "material": "матеріал Wallcov або ''"}]}
Ідей — рівно 5, кожна повʼязана з реальним питанням клієнтів або ролику ніші з даних."""


BLOG_TASK = """Ти — аналітик контенту цього блогу. Власник — не маркетолог: пиши простою українською, коротко, без жаргону.
Отримаєш JSON за період: наші публікації (перегляди, ×N від звичного), ролики конкурентів і натхнення блогу, що «вистрілили»,
памʼять блогу (що вже зробили, які обіцянки відкриті). Не вигадуй цифр. Якщо даних мало — так і скажи й поясни, яких сторінок бракує.
Відповідай ЛИШЕ JSON:
{"summary": "3–6 коротких абзаців: що спрацювало, що ні, що робити цього тижня (\\n\\n між абзацами)",
 "ideas": [{"title": "...", "hook": "перше речення/кадр", "why": "з яких даних", "format": "рилс / карусель", "material": ""}]}
Ідей — рівно 5, під мету й майстер-промт блогу; якщо є відкрита обіцянка — одна ідея на неї."""


def build_blog_inputs(blog, days=7):
    from . import blogs as _b
    own = [c.handle for c in blog.channels.filter(role=ContentChannel.Role.OWN)]
    med = medians()
    since = timezone.now() - timedelta(days=max(days, 30))
    mine = [{"user": i.username, "views": i.views, "x": outlier(i, med), "caption": (i.caption or "")[:140]}
            for i in FeedItem.objects.filter(username__in=own, published_at__gte=since).order_by("-published_at")[:15]]
    return {"period_days": days, "blog": blog.name, "own_accounts": own, "own_posts": mine,
            "niche_hits": [{"user": i.username, "views": i.views, "x": x, "hook": (i.caption or "")[:140]}
                           for i, x in feed(days=max(days, 14), sort="outlier", limit=12, blog=blog) if x and x >= 1.5],
            "tracked_pages": sorted(tracked_handles(blog)), "memory": _b.memory_block(blog)}


def generate_report(days=7, call=None, blog=None):
    s = AnalystSettings.get()
    if questions.month_spent(SOURCE) + estimate_usd(s.model) > float(s.monthly_budget_usd):
        raise BudgetError(f"Досягнуто місячного ліміту ${float(s.monthly_budget_usd):.2f} для аналітика.")
    if blog is not None and blog.slug != "wallcov":  # інший блог: його сторінки, стрічка, памʼять і майстер-промт
        from . import blogs as _b
        inputs, system = build_blog_inputs(blog, days), _b.system_for(blog, BLOG_TASK)
    else:
        inputs, system = build_inputs(days), SYSTEM
    if call is None:
        from apps.crm.ai import claude_json
        call = lambda p: claude_json(p, model=s.model, max_tokens=2500, system=system, source=SOURCE)
    r = call(json.dumps(inputs, ensure_ascii=False, default=str)) or {}
    summary = str(r.get("summary") or r.get("suggestion") or "").strip()
    if not summary:
        raise ValueError("ШІ не повернув звіт — спробуйте ще раз.")
    ideas = [{k: str(i.get(k, ""))[:300] for k in ("title", "hook", "why", "format", "material")}
             for i in (r.get("ideas") or []) if isinstance(i, dict)][:5]
    return AnalystReport.objects.create(period_days=days, summary=summary, ideas=ideas, inputs=inputs, model=s.model, blog=blog)
