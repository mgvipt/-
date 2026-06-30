"""XP-логіка: рівні, нарахування (ідемпотентне), бейджі. Коефіцієнти з дизайн-доку."""
from django.db.models import Sum
from .models import XPEvent, ManagerLevel, BadgeAward

# (поріг, назва, емодзі, колір)
LEVELS = [
    (0, "Новачок", "\U0001f7eb", "#a16207"),
    (600, "Учень", "\U0001f7e6", "#2563eb"),
    (1800, "Продавець", "\U0001f7e9", "#16a34a"),
    (4000, "Профі", "\U0001f7e8", "#ca8a04"),
    (8000, "Майстер", "\U0001f7e7", "#ea580c"),
    (15000, "Легенда Wallcov", "\U0001f7e5", "#dc2626"),
]
SKILL_KEYS = ["вступ", "виявлення_потреби", "презентація_цінності",
              "робота_з_запереченнями", "заклик_до_дії", "тон_емпатія"]
SKILL_LABELS = {
    "вступ": "Вступ", "виявлення_потреби": "Виявлення потреби",
    "презентація_цінності": "Презентація цінності", "робота_з_запереченнями": "Робота з запереченнями",
    "заклик_до_дії": "Заклик до дії", "тон_емпатія": "Тон / емпатія",
}
BADGES = {
    "first_blood": ("\U0001f3af", "Перша кров", "Перша виграна угода"),
    "word_master": ("\U0001f5e3", "Майстер слова", "Оцінка діалогу \u226585"),
    "in_form": ("\U0001f4c8", "У формі", "4 тижні поспіль якість не падала"),
    "spurt": ("\U0001f680", "Ривок", "+5 до середньої якості за тиждень"),
    "margin": ("\U0001f48e", "Маржинал", "Маржинальні угоди \u226525%"),
    "streak7": ("\U0001f525", "Стрік-7", "7 днів поспіль активність"),
}


def level_for(xp):
    lvl = 1
    for i, (thr, _, _, _) in enumerate(LEVELS):
        if xp >= thr:
            lvl = i + 1
    return lvl


def level_info(xp):
    idx = level_for(xp) - 1
    thr, name, emoji, color = LEVELS[idx]
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    prog = 100 if nxt is None else round((xp - thr) * 100 / (nxt - thr))
    return {"level": idx + 1, "name": name, "emoji": emoji, "color": color,
            "total_xp": xp, "cur_threshold": thr, "next_threshold": nxt,
            "to_next": (nxt - xp) if nxt else 0, "progress": max(0, min(100, prog))}


def recompute_level(manager_id):
    total = XPEvent.objects.filter(manager_id=manager_id).aggregate(s=Sum("xp"))["s"] or 0
    ml, _ = ManagerLevel.objects.get_or_create(manager_id=manager_id)
    ml.total_xp = total
    ml.level = level_for(total)
    ml.save()
    return ml


def award(manager, kind, xp, ref_type="", ref_id="", meta=None):
    """Нарахувати XP. Ідемпотентно по (kind,ref_type,ref_id) якщо ref_id заданий."""
    if manager is None or xp == 0:
        return None
    if ref_id:
        ev, created = XPEvent.objects.get_or_create(
            kind=kind, ref_type=ref_type, ref_id=str(ref_id),
            defaults={"manager": manager, "xp": xp, "meta": meta or {}})
        if not created:
            return None
    else:
        ev = XPEvent.objects.create(manager=manager, kind=kind, xp=xp, ref_type=ref_type, meta=meta or {})
    recompute_level(manager.id)
    return ev


def give_badge(manager, code, meta=None):
    if manager is None:
        return
    BadgeAward.objects.get_or_create(manager=manager, badge_code=code, defaults={"meta": meta or {}})


def quality_xp(overall, scores):
    xp = round((overall or 0) * 0.5)
    sc = scores or {}
    for k in SKILL_KEYS:
        try:
            if int(sc.get(k, 0) or 0) >= 80:
                xp += 3
        except Exception:
            pass
    if (overall or 0) >= 85:
        xp += 20
    return xp


def award_for_analysis(da):
    if not da.manager_id:
        return
    from apps.accounts.models import User
    mgr = User.objects.filter(id=da.manager_id).first()
    if not mgr:
        return
    award(mgr, "quality", quality_xp(da.overall_score, da.scores), "analysis", da.id,
          {"overall": da.overall_score})
    if (da.overall_score or 0) >= 85:
        give_badge(mgr, "word_master", {"analysis": da.id})
