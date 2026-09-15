"""Бали розвитку, навички, бейджі.

Розвиток v2 (16.09.2026, рішення Олега: «синхронно з ЗП і KPI; публічний рейтинг прибрати, мотивувати людей»):
- бали — лише за якість і результати, які людина контролює (правила — rules.py). За сам факт виграної угоди балів
  більше немає (раніше 60 + сума/1000 — це було 77–93% усіх балів; тест-набір за 300 ₴ = замовлення за 50 000 ₴);
- рівні — сезонні, від власного плану / стандарту / якості за квартал (season.py), а не від балів за весь час;
- бейджі: лишились «Перша кров» (історія) і «Майстер слова» з досяжним порогом; 4 бейджі, яких ніхто ніколи не
  отримав і які ніде не нараховувались («У формі», «Ривок», «Маржинал», «Стрік-7»), прибрано.
"""
from django.db.models import Sum
from .models import XPEvent, ManagerLevel, BadgeAward

# Колишні рівні «за бали за весь час» — більше НЕ показуються (див. season.py). Лишено для сумісності ManagerLevel.
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
WORD_MASTER_MIN = 75   # раніше 85 — за весь час найкращий розбір 78 (чат) / 68 (дзвінок), бейдж був недосяжним
BADGES = {
    "first_blood": ("\U0001f3af", "Перша кров", "Перша виграна угода (нагорода за старими правилами — лишається в історії)"),
    "word_master": ("\U0001f5e3", "Майстер слова", f"Розбір розмови з оцінкою від {WORD_MASTER_MIN}"),
}
# Старі види балів (до 16.09.2026) — ніде не рахуються, навіть якщо рядок ще не архівовано командою gamify_rules_v2.
OLD_KINDS = ("deal_won", "deal_check")


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


def live_events():
    """Бали, що рахуються: не архівні і не старих видів."""
    return XPEvent.objects.filter(archived=False).exclude(kind__in=OLD_KINDS)


def recompute_level(manager_id):
    total = live_events().filter(manager_id=manager_id).aggregate(s=Sum("xp"))["s"] or 0
    ml, _ = ManagerLevel.objects.get_or_create(manager_id=manager_id)
    ml.total_xp = total
    ml.level = level_for(total)
    ml.save()
    return ml


def award(manager, kind, xp, ref_type="", ref_id="", meta=None, when=None):
    """Нарахувати бали. Ідемпотентно по (kind, ref_type, ref_id), якщо ref_id заданий.
    manager — користувач або його id; when — дата події (бали лягають у місяць події, а не в момент запуску крону)."""
    mid = getattr(manager, "id", manager)
    if not mid or xp == 0:
        return None
    if ref_id:
        ev, created = XPEvent.objects.get_or_create(
            kind=kind, ref_type=ref_type, ref_id=str(ref_id),
            defaults={"manager_id": mid, "xp": xp, "meta": meta or {}})
        if not created:
            return None
    else:
        ev = XPEvent.objects.create(manager_id=mid, kind=kind, xp=xp, ref_type=ref_type, meta=meta or {})
    if when is not None:
        XPEvent.objects.filter(pk=ev.pk).update(created_at=when)
    recompute_level(mid)
    return ev


def give_badge(manager, code, meta=None):
    mid = getattr(manager, "id", manager)
    if not mid:
        return
    BadgeAward.objects.get_or_create(manager_id=mid, badge_code=code, defaults={"meta": meta or {}})


QUALITY_FLOOR = 40   # розбір до 40 балів — 0: бали за ЯКІСТЬ розмови, а не за кількість дзвінків


def quality_xp(overall, scores):
    """Бали за розбір: (бал − 40) × 0,5, але не менше 0; + 3 за кожну з 6 навичок від 80; + 20, якщо розбір від 75.
    Приклад: розбір 70 з навичкою «Вступ» 85 → (70 − 40) × 0,5 = 15 + 3 = 18. Слабкий дзвінок (≤ 40) балів не дає."""
    xp = round(max(0, (overall or 0) - QUALITY_FLOOR) * 0.5)
    sc = scores or {}
    for k in SKILL_KEYS:
        try:
            if int(sc.get(k, 0) or 0) >= 80:
                xp += 3
        except Exception:
            pass
    if (overall or 0) >= WORD_MASTER_MIN:
        xp += 20
    return xp


def counts_for_quality(da, credit=None):
    """Чи йде розбір у «Якість дзвінків» і бали: дзвінок — так; чат — лише з випадкової тижневої вибірки
    (credit="sample"). Чати, розібрані «вручну» кнопкою, не рахуються: їх можна вибирати (лише вдалі)."""
    return da.kind == "call" or credit == "sample"


def award_for_analysis(da):
    """Бали за розбір — ТОМУ, ХТО ГОВОРИВ. credit у meta: speaker — оператор дзвінка / автор повідомлень;
    owner — оператор невідомий, зараховано власнику угоди; sample — випадкова вибірка чатів (автор повідомлень)."""
    if not da.manager_id:
        return
    credit = getattr(da, "_rzv_credit", None)
    if not counts_for_quality(da, credit):
        return
    meta = {"overall": da.overall_score, "kind": da.kind, "credit": credit or ("owner" if da.kind == "call" else "")}
    if credit == "sample":
        meta["sample"] = True
    award(da.manager_id, "quality", quality_xp(da.overall_score, da.scores), "analysis", da.id, meta, when=da.created_at)
    if (da.overall_score or 0) >= WORD_MASTER_MIN:
        give_badge(da.manager_id, "word_master", {"analysis": da.id})
