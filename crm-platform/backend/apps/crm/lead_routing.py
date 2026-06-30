"""Авто-розподіл нових лідів між активними менеджерами продажів (балансування навантаження).
Лід отримує власника з найменшою к-стю поточних лідів — щоб усі отримували порівну."""


def lead_owner_pool():
    from apps.accounts.models import User
    pool = list(User.objects.filter(is_active=True, is_superuser=False)
                .exclude(username__startswith="b24_")
                .filter(department__name__icontains="продаж"))
    if not pool:  # fallback — будь-які активні реальні не-адміни
        pool = list(User.objects.filter(is_active=True, is_superuser=False).exclude(username__startswith="b24_"))
    return pool


def next_lead_owner():
    from .models import Lead
    pool = lead_owner_pool()
    if not pool:
        return None
    counts = {u.id: Lead.objects.filter(owner=u).count() for u in pool}
    return min(pool, key=lambda u: (counts[u.id], u.id))



def make_lead_for_contact(contact, funnel, source="other"):
    """Створити лід. Якщо клієнт ПОВЕРТАЄТЬСЯ (вже є лід у цій воронці) — перенести
    контекст (qualification: тип приміщення/площа/матеріал/бюджет) і стартувати зі стадії,
    де він зупинився. Новий клієнт → перша стадія + авто-розподіл власника.
    Повернення → власник None (вільний пул «Не призначені»)."""
    from .models import Lead, log_activity
    stages = list(funnel.stages.order_by("order"))
    if not stages:
        return None
    if source not in dict(Lead.SOURCES):
        source = "other"
    start = stages[0]
    qual = {}
    prev = Lead.objects.filter(contact=contact, funnel=funnel).order_by("-created_at").first()
    if prev:
        qual = dict(prev.qualification or {})
        rid = qual.pop("_reached_stage_id", None)
        qual.pop("_reached_stage_name", None)
        reached = next((st for st in stages if st.id == rid and not st.is_lost and not st.is_won), None)
        if reached:
            start = reached
        owner = None  # повернення → у вільний пул
    else:
        owner = next_lead_owner()  # новий клієнт → авто-розподіл
    ld = Lead.objects.create(title=(str(contact) or "Клієнт")[:255], contact=contact, funnel=funnel,
                             stage=start, source=source, is_seen=False, owner=owner, qualification=qual)
    if prev:
        log_activity("lead", ld.id, "Новий запит — клієнт повернувся",
                     "Контекст перенесено · старт зі стадії: %s" % start.name, None, "Система")
    return ld
