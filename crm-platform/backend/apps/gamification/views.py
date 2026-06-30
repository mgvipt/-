import datetime
from django.db.models import Avg, Sum, Max
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.accounts.models import User
from apps.crm.models import DialogAnalysis
from .models import ManagerLevel, BadgeAward, XPEvent
from .xp import level_info, LEVELS, SKILL_KEYS, SKILL_LABELS, BADGES

PERIOD_DAYS = {"week": 7, "month": 30, "quarter": 90, "all": 3650}

# Плейн-опис навички + 2 мікро-практики (UK / RU) для блоку «Що робити далі».
SKILL_HELP = {
    "вступ": {
        "what": "Як ти починаєш розмову — чи створюєш контакт і довіру з перших секунд.",
        "what_ru": "Как ты начинаешь разговор — создаёшь ли контакт и доверие с первых секунд.",
        "practice": ["Почни наступні 3 чати з імені клієнта і короткого щирого вітання",
                     "За перші 2 репліки постав 1 питання, щоб зрозуміти запит"],
        "practice_ru": ["Начни следующие 3 чата с имени клиента и короткого искреннего приветствия",
                        "За первые 2 реплики задай 1 вопрос, чтобы понять запрос"]},
    "виявлення_потреби": {
        "what": "Чи ставиш питання, щоб зрозуміти, що реально потрібно клієнту.",
        "what_ru": "Задаёшь ли вопросы, чтобы понять, что реально нужно клиенту.",
        "practice": ["У наступних 5 діалогах постав мінімум 2 уточнюючі питання ДО ціни",
                     "Питай «для якої кімнати / якого ефекту хочете?» перш ніж пропонувати"],
        "practice_ru": ["В следующих 5 диалогах задай минимум 2 уточняющих вопроса ДО цены",
                        "Спрашивай «для какой комнаты / какого эффекта хотите?» перед предложением"]},
    "презентація_цінності": {
        "what": "Чи показуєш вигоду, а не лише ціну й характеристики.",
        "what_ru": "Показываешь ли выгоду, а не только цену и характеристики.",
        "practice": ["До кожної ціни додавай 1 речення вигоди («тихо й надовго», «без переробок»)",
                     "Розкажи 1 короткий приклад, як це вирішило проблему іншого клієнта"],
        "practice_ru": ["К каждой цене добавляй 1 фразу выгоды («тихо и надолго», «без переделок»)",
                        "Расскажи 1 короткий пример, как это решило проблему другого клиента"]},
    "робота_з_запереченнями": {
        "what": "Як ти відповідаєш на «дорого», «подумаю», «у інших дешевше».",
        "what_ru": "Как ты отвечаешь на «дорого», «подумаю», «у других дешевле».",
        "practice": ["На «дорого» — не виправдовуйся, поясни, з чого складається цінність",
                     "На «подумаю» — спитай, що саме зупиняє, і дай конкретику"],
        "practice_ru": ["На «дорого» — не оправдывайся, объясни, из чего складывается ценность",
                        "На «подумаю» — спроси, что именно останавливает, и дай конкретику"]},
    "заклик_до_дії": {
        "what": "Чи доводиш розмову до конкретного наступного кроку (оплата, замір, бронь).",
        "what_ru": "Доводишь ли разговор до конкретного следующего шага (оплата, замер, бронь).",
        "practice": ["Завершуй кожен діалог твердим кроком: «Оформляю?» / «Бронюю на 3 дні?»",
                     "Заміни «думайте» на конкретну дію з дедлайном"],
        "practice_ru": ["Завершай каждый диалог твёрдым шагом: «Оформляю?» / «Бронирую на 3 дня?»",
                        "Замени «думайте» на конкретное действие с дедлайном"]},
    "тон_емпатія": {
        "what": "Чи відчуває клієнт, що його чують і поважають.",
        "what_ru": "Чувствует ли клиент, что его слышат и уважают.",
        "practice": ["Спершу віддзеркаль емоцію клієнта («розумію, це важливо»), потім відповідай",
                     "Прибери сухі шаблони — пиши по-людськи, на імʼя"],
        "practice_ru": ["Сначала отрази эмоцию клиента («понимаю, это важно»), потом отвечай",
                        "Убери сухие шаблоны — пиши по-человечески, по имени"]},
}


def _period(request):
    p = (request.GET.get("period") or "month").lower()
    return p if p in PERIOD_DAYS else "month"


def sales_managers():
    return (User.objects.filter(department__name__icontains="продаж", is_active=True)
            .exclude(username__startswith="b24_"))


def _wk(d):
    return (d - datetime.timedelta(days=d.weekday())).date()


def _skills_window(mid, since, until):
    rows = list(DialogAnalysis.objects.filter(manager_id=mid, created_at__gte=since, created_at__lt=until)
                .values_list("scores", flat=True))
    out = {}
    for k in SKILL_KEYS:
        vals = []
        for r in rows:
            v = (r or {}).get(k)
            if v is not None:
                try:
                    vals.append(int(v))
                except Exception:
                    pass
        out[k] = round(sum(vals) / len(vals)) if vals else 0
    return out


def _avg(mid, since, until):
    return DialogAnalysis.objects.filter(manager_id=mid, created_at__gte=since,
                                         created_at__lt=until).aggregate(a=Avg("overall_score"))["a"]


def _trend(mid, period, now):
    """week→дні(7), month→тижні(5), quarter→тижні(12), all→тижні(12). state: empty/sparse/enough."""
    pts = []
    if period == "week":
        for i in range(6, -1, -1):
            d = (now - datetime.timedelta(days=i)).date()
            qs = DialogAnalysis.objects.filter(manager_id=mid, created_at__date=d)
            a = qs.aggregate(x=Avg("overall_score"))["x"]
            pts.append({"date": d.isoformat()[5:], "avg": round(a) if a else None, "n": qs.count()})
    else:
        weeks = 5 if period == "month" else 12
        for i in range(weeks - 1, -1, -1):
            ws = _wk(now) - datetime.timedelta(weeks=i)
            we = ws + datetime.timedelta(days=7)
            qs = DialogAnalysis.objects.filter(manager_id=mid, created_at__date__gte=ws, created_at__date__lt=we)
            a = qs.aggregate(x=Avg("overall_score"))["x"]
            pts.append({"date": ws.isoformat()[5:], "avg": round(a) if a else None, "n": qs.count()})
    nonnull = [p for p in pts if p["avg"] is not None]
    total_n = DialogAnalysis.objects.filter(manager_id=mid).count()
    state = "empty" if total_n == 0 else ("sparse" if len(nonnull) < 3 else "enough")
    first_score = last_score = delta = None
    if state == "sparse" and total_n:
        scores = list(DialogAnalysis.objects.filter(manager_id=mid).order_by("created_at")
                      .values_list("overall_score", flat=True))
        half = max(1, len(scores) // 2)
        first_score = round(sum(scores[:half]) / len(scores[:half]))
        rest = scores[half:] or scores[:half]
        last_score = round(sum(rest) / len(rest))
        delta = last_score - first_score
    return {"state": state, "points": pts, "first_score": first_score,
            "last_score": last_score, "delta": delta, "dialogs_needed": max(0, 3 - total_n)}


def _next_steps(mid, period, now, skills, info):
    nz = [s for s in skills if s["cur"]]
    if not nz:
        return None
    focus = min(nz, key=lambda s: s["cur"])
    fk = focus["key"]
    since = now - datetime.timedelta(days=PERIOD_DAYS[period])
    rows = [a for a in DialogAnalysis.objects.filter(manager_id=mid, created_at__gte=since).order_by("-created_at")[:200]
            if (a.scores or {}).get(fk) is not None]

    def sk(a):
        try:
            return int((a.scores or {}).get(fk, 999))
        except Exception:
            return 999

    rows.sort(key=sk)
    tips = []
    for a in rows[:3]:
        if a.coaching:
            tips.append({"coaching": a.coaching[:400], "deal_id": a.deal_id, "kind": a.kind,
                         "date": a.created_at.date().isoformat()[5:], "score": sk(a)})
    model = None
    for a in rows:
        if a.recommended_reply:
            model = {"recommended_reply": a.recommended_reply[:700], "why": (a.why_not_selling or "")[:300],
                     "deal_id": a.deal_id, "date": a.created_at.date().isoformat()[5:]}
            break
    h = SKILL_HELP.get(fk, {})
    nxt_name = LEVELS[info["level"]][1] if info["level"] < len(LEVELS) else None
    return {"focus": {"key": fk, "label": focus["label"], "cur": focus["cur"], "prev": focus["prev"],
                      "target": min(100, max(focus["cur"] + 13, 65)),
                      "what": h.get("what", ""), "what_ru": h.get("what_ru", "")},
            "tips": tips, "model": model,
            "practice": h.get("practice", []), "practice_ru": h.get("practice_ru", []),
            "level_goal": {"to_next": info["to_next"], "next_level": nxt_name}}


def payload(mid, period="month"):
    ml, _ = ManagerLevel.objects.get_or_create(manager_id=mid)
    info = level_info(ml.total_xp)
    now = timezone.now()
    days = PERIOD_DAYS[period]
    cur_start = now - datetime.timedelta(days=days)
    prev_start = now - datetime.timedelta(days=2 * days)
    until = now + datetime.timedelta(days=1)
    avg_cur = _avg(mid, cur_start, until)
    avg_prev = _avg(mid, prev_start, cur_start)
    cur = _skills_window(mid, cur_start, until)
    prev = _skills_window(mid, prev_start, cur_start)
    skills = [{"key": k, "label": SKILL_LABELS[k], "cur": cur[k], "prev": prev[k]} for k in SKILL_KEYS]
    n_period = DialogAnalysis.objects.filter(manager_id=mid, created_at__gte=cur_start).count()
    n_all = DialogAnalysis.objects.filter(manager_id=mid).count()
    xp_period = XPEvent.objects.filter(manager_id=mid, created_at__gte=cur_start).aggregate(s=Sum("xp"))["s"] or 0
    best = DialogAnalysis.objects.filter(manager_id=mid, created_at__gte=cur_start).aggregate(m=Max("overall_score"))["m"]
    badges = []
    for b in BadgeAward.objects.filter(manager_id=mid):
        e, l, d = BADGES.get(b.badge_code, ("\U0001f3c5", b.badge_code, ""))
        badges.append({"code": b.badge_code, "emoji": e, "label": l, "desc": d})
    nz = [s for s in skills if s["cur"]]
    weak = min(nz, key=lambda s: s["cur"])["label"] if nz else None
    u = User.objects.filter(id=mid).first()
    return {"id": mid, "name": (u.get_full_name() or u.username) if u else str(mid),
            "level": info, "skills": skills, "trend": _trend(mid, period, now), "badges": badges,
            "analyses": n_period, "analyses_all": n_all,
            "avg_overall": round(avg_cur) if avg_cur is not None else None,
            "avg_prev": round(avg_prev) if avg_prev is not None else None,
            "quality_delta": (round(avg_cur) - round(avg_prev)) if (avg_cur is not None and avg_prev is not None) else None,
            "xp_period": xp_period, "best": best,
            "xp_per_dialog": round(info["total_xp"] / n_all) if n_all else 0,
            "weakest": weak, "next_steps": _next_steps(mid, period, now, skills, info), "period": period}


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(payload(request.user.id, _period(request)))


class ManagerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if request.user.id != pk:
            try:
                can = "analytics.view_all" in request.user.effective_permissions()
            except Exception:
                can = request.user.is_staff
            if not (can or request.user.is_staff or request.user.is_superuser):
                return Response({"detail": "Немає доступу"}, status=403)
        return Response(payload(pk, _period(request)))


class LeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = _period(request)
        now = timezone.now()
        days = PERIOD_DAYS[period]
        cur_start = now - datetime.timedelta(days=days)
        prev_start = now - datetime.timedelta(days=2 * days)
        until = now + datetime.timedelta(days=1)
        rows = []
        for m in sales_managers():
            ml, _ = ManagerLevel.objects.get_or_create(manager_id=m.id)
            info = level_info(ml.total_xp)
            xp_p = XPEvent.objects.filter(manager_id=m.id, created_at__gte=cur_start).aggregate(s=Sum("xp"))["s"] or 0
            a_cur = _avg(m.id, cur_start, until)
            a_prev = _avg(m.id, prev_start, cur_start)
            growth = (round(a_cur) - round(a_prev)) if (a_cur is not None and a_prev is not None) else None
            ac = round(a_cur) if a_cur is not None else None
            rows.append({"id": m.id, "name": m.get_full_name() or m.username,
                         "level": info["level"], "level_name": info["name"],
                         "level_emoji": info["emoji"], "color": info["color"],
                         "total_xp": info["total_xp"], "week_xp": xp_p, "period_xp": xp_p,
                         "avg_overall": ac, "was": round(a_prev) if a_prev is not None else None,
                         "now": ac, "growth": growth,
                         "status": "green" if (ac or 0) >= 70 else "amber" if (ac or 0) >= 50 else "red"})

        def board(key):
            return sorted(rows, key=lambda r: (r.get(key) if r.get(key) is not None else -999), reverse=True)

        qvals = [r["avg_overall"] for r in rows if r["avg_overall"] is not None]
        return Response({"week": board("period_xp"), "quality": board("avg_overall"),
                         "growth": board("growth"), "me": request.user.id, "period": period,
                         "managers": sorted(rows, key=lambda r: -(r.get("total_xp") or 0)),
                         "team_avg": round(sum(qvals) / len(qvals)) if qvals else None,
                         "team_count": len(rows)})
