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
    """Створити лід лише для нового контакту.
    Якщо контакт уже має лід у будь-якій воронці, повертаємо його: усі відкриті лінії
    прив'язують нове звернення до того самого клієнта і не створюють дубль."""
    from .models import Lead
    existing = Lead.objects.filter(contact=contact).order_by("-created_at").first()
    if existing:
        return existing
    stages = list(funnel.stages.order_by("order"))
    if not stages:
        return None
    if source not in dict(Lead.SOURCES):
        source = "other"
    start = stages[0]
    owner = next_lead_owner()
    ld = Lead.objects.create(title=(str(contact) or "Клієнт")[:255], contact=contact, funnel=funnel,
                             stage=start, source=source, is_seen=False, owner=owner, qualification={})
    return ld
