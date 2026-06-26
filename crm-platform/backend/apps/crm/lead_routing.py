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
