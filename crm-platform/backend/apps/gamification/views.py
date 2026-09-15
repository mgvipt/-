"""API «Розвиток» (Розвиток v2, 16.09.2026 — рішення Олега: «синхронно з ЗП і KPI; публічний рейтинг прибрати»).

- /api/gamification/me/?period=YYYY-MM — «ти проти себе»: бали цього місяця проти минулого і особистий рекорд,
  якість дзвінків, навички, сезонний рівень, змагання тижня (лише свої цифри), що робити далі. Місяць = КАЛЕНДАРНИЙ.
- /api/gamification/manager/<id>/ — те саме про іншу людину: лише власник / право «Бачити якість/коучинг команди (РОП)».
- /api/gamification/leaderboard/ — порівняння команди: ЛИШЕ власник / РОП (раніше бачили всі; для інших — 403).
- /api/gamification/practice/ — відмітки «маленьких справ на тиждень» (зберігаються; лише свої).
- /api/gamification/settings/ — вибірка чатів для ІІ (вимк. за замовчуванням), змагання: читати — РОП/власник, змінювати — власник.
- /api/gamification/contests/?week=РРРР-Wтт — результати змагання тижня (власник/РОП); POST {code, week} — нарахувати приз.
"""
import datetime
import re

from django.db.models import Avg, Count, Max, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.crm.models import DialogAnalysis
from apps.payroll import engine

from .models import BadgeAward, GamSettings, PracticeMark, XPEvent
from .xp import BADGES, SKILL_KEYS, SKILL_LABELS, live_events

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MONTHS = ["", "січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень",
          "вересень", "жовтень", "листопад", "грудень"]
MONTHS_SHORT = ["", "січ", "лют", "бер", "кві", "тра", "чер", "лип", "сер", "вер", "жов", "лис", "гру"]

# Плейн-опис навички + 2 мікро-практики (UK / RU) для блоку «Що робити далі».
SKILL_HELP = {
    "вступ": {
        "what": "Як ти починаєш розмову — чи створюєш контакт і довіру з перших секунд.",
        "what_ru": "Как ты начинаешь разговор — создаёшь ли контакт и доверие с первых секунд.",
        "practice": ["Почни наступні 3 розмови з імені клієнта і короткого щирого вітання",
                     "За перші 2 репліки постав 1 питання, щоб зрозуміти запит"],
        "practice_ru": ["Начни следующие 3 разговора с имени клиента и короткого искреннего приветствия",
                        "За первые 2 реплики задай 1 вопрос, чтобы понять запрос"]},
    "виявлення_потреби": {
        "what": "Чи ставиш питання, щоб зрозуміти, що реально потрібно клієнту.",
        "what_ru": "Задаёшь ли вопросы, чтобы понять, что реально нужно клиенту.",
        "practice": ["У наступних 5 розмовах постав мінімум 2 уточнюючі питання ДО ціни",
                     "Питай «для якої кімнати / якого ефекту хочете?» перш ніж пропонувати"],
        "practice_ru": ["В следующих 5 разговорах задай минимум 2 уточняющих вопроса ДО цены",
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
        "practice": ["Завершуй кожну розмову твердим кроком: «Оформляю?» / «Бронюю на 3 дні?»",
                     "Заміни «думайте» на конкретну дію з дедлайном"],
        "practice_ru": ["Завершай каждый разговор твёрдым шагом: «Оформляю?» / «Бронирую на 3 дня?»",
                        "Замени «думайте» на конкретное действие с дедлайном"]},
    "тон_емпатія": {
        "what": "Чи відчуває клієнт, що його чують і поважають.",
        "what_ru": "Чувствует ли клиент, что его слышат и уважают.",
        "practice": ["Спершу віддзеркаль емоцію клієнта («розумію, це важливо»), потім відповідай",
                     "Прибери сухі шаблони — говори по-людськи, на імʼя"],
        "practice_ru": ["Сначала отрази эмоцию клиента («понимаю, это важно»), потом отвечай",
                        "Убери сухие шаблоны — говори по-человечески, по имени"]},
}


# ─────────────────────────── хто що бачить ───────────────────────────

def is_team_viewer(u):
    """Порівняння команди і сторінки інших людей — лише власник або право «Бачити якість/коучинг команди (РОП)»."""
    if not (u and u.is_authenticated):
        return False
    if u.is_superuser:
        return True
    try:
        return "coaching.view.all" in u.effective_permissions()
    except Exception:
        return False


def sales_managers():
    return (User.objects.filter(department__name__icontains="продаж", is_active=True)
            .exclude(username__startswith="b24_"))


# ─────────────────────────── якість: лише дзвінки (+ вибірка чатів, якщо увімкнено) ───────────────────────────

def _sample_ids():
    return [int(x) for x in XPEvent.objects.filter(kind="quality", ref_type="analysis", meta__sample=True)
            .values_list("ref_id", flat=True) if str(x).isdigit()]


def quality_label(settings=None):
    s = settings or GamSettings.get()
    return "Якість розмов (дзвінки + вибірка чатів)" if s.chat_sampling else "Якість дзвінків"


def quality_qs(uid=None, d1=None, d2=None):
    """Розбори, з яких рахується «Якість дзвінків»: усі розбори дзвінків; чати — лише з випадкової тижневої вибірки
    (якщо власник її увімкнув). Чати, розібрані вручну кнопкою, не рахуються. d1/d2 — дати включно (календар)."""
    q = Q(kind="call")
    if GamSettings.get().chat_sampling:
        ids = _sample_ids()
        if ids:
            q |= Q(id__in=ids)
    qs = DialogAnalysis.objects.filter(q)
    if uid is not None:
        qs = qs.filter(manager_id=uid)
    if d1 is not None:
        qs = qs.filter(created_at__date__gte=d1)
    if d2 is not None:
        qs = qs.filter(created_at__date__lte=d2)
    return qs


# ─────────────────────────── періоди: календарний місяць ───────────────────────────

def _label(p):
    return f"{MONTHS[int(p[5:7])]} {p[:4]}"


def _month(request):
    today = timezone.localdate()
    p = (request.GET.get("period") or "")[:7]
    return p if PERIOD_RE.match(p) else today.strftime("%Y-%m")


def _prev(p):
    return engine.add_months(engine.period_bounds(p)[0], -1).strftime("%Y-%m")


def _periods(today):
    cur = today.strftime("%Y-%m")
    return [{"value": cur, "label": _label(cur)}, {"value": _prev(cur), "label": _label(_prev(cur))}]


def _week_start(d=None):
    d = d or timezone.localdate()
    return d - datetime.timedelta(days=d.weekday())


# ─────────────────────────── блоки сторінки ───────────────────────────

def _points(uid, period):
    from .rules import KIND_LABELS, NO_DISCOUNT_XP, REVIEW_ASK_XP, REVIEW_XP, month_points
    d1, d2 = engine.period_bounds(period)
    p = _prev(period)
    rows, total = month_points(uid, d1, d2)
    prows, ptotal = month_points(uid, *engine.period_bounds(p))
    best = (live_events().filter(manager_id=uid).annotate(m=TruncMonth("created_at")).values("m")
            .annotate(s=Sum("xp")).order_by("-s", "-m").first())
    record = None
    if best and best["s"]:
        m = best["m"]
        m = timezone.localtime(m).date() if hasattr(m, "hour") and timezone.is_aware(m) else (m.date() if hasattr(m, "hour") else m)
        record = {"period": m.strftime("%Y-%m"), "label": _label(m.strftime("%Y-%m")), "total": int(best["s"])}
    recent = []
    for e in (live_events().filter(manager_id=uid, created_at__date__gte=d1, created_at__date__lte=d2)
              .order_by("-created_at")[:12]):
        deal = (e.meta or {}).get("deal") or (int(e.ref_id) if e.ref_type == "deal" and str(e.ref_id).isdigit() else None)
        recent.append({"date": timezone.localtime(e.created_at).date().isoformat(), "kind": e.kind,
                       "label": KIND_LABELS.get(e.kind, e.kind), "xp": e.xp, "deal_id": deal,
                       "credit": (e.meta or {}).get("credit") or ""})
    fixed = {"no_discount": NO_DISCOUNT_XP, "review": REVIEW_XP, "review_ask": REVIEW_ASK_XP}
    if rows:
        explain = (f"Бали за {_label(period)}: " + " + ".join(
            (f"{r['label']} {r['count']} × {fixed[r['kind']]} = {r['xp']}" if r["kind"] in fixed
             else f"{r['label']} ({r['count']} шт.) {r['xp']}") for r in rows) + f" → разом {total}.")
    else:
        explain = f"За {_label(period)} балів ще немає. Бали дають: тест-набір → основне, основне без знижки, відгук, розбір дзвінка."
    return {"total": total, "rows": rows, "prev_total": ptotal, "prev_label": _label(p), "delta": total - ptotal,
            "prev_rows": prows, "record": record, "recent": recent, "explain": explain,
            "compare": "Порівнюєш себе з собою: цей місяць проти минулого і твій найкращий місяць. Інших людей тут немає."}


def _quality(uid, period):
    d1, d2 = engine.period_bounds(period)
    p = _prev(period)
    pd1, pd2 = engine.period_bounds(p)
    cur = quality_qs(uid, d1, d2)
    agg = cur.aggregate(a=Avg("overall_score"), n=Count("id"), b=Max("overall_score"), s=Sum("overall_score"))
    prev = quality_qs(uid, pd1, pd2).aggregate(a=Avg("overall_score"), n=Count("id"))
    ids = [str(i) for i in cur.values_list("id", flat=True)]
    credit = {"speaker": 0, "owner": 0, "sample": 0}
    for m in XPEvent.objects.filter(kind="quality", ref_type="analysis", ref_id__in=ids).values_list("meta", flat=True):
        c = (m or {}).get("credit") or "owner"
        credit[c if c in credit else "owner"] = credit.get(c if c in credit else "owner", 0) + 1
    a = round(agg["a"]) if agg["a"] is not None else None
    pa = round(prev["a"]) if prev["a"] is not None else None
    label = quality_label()
    if agg["n"]:
        explain = (f"Середнє з {agg['n']} розборів за {_label(period)}: сума балів {agg['s']} ÷ {agg['n']} = {a}. "
                   "Бал 0–100 ставить ІІ-аналітик за 6 навичками; ціль — 70.")
    else:
        explain = f"За {_label(period)} розборів дзвінків ще немає — бал зʼявиться після першого розбору."
    note = ""
    if credit["owner"]:
        note = (f"{credit['owner']} з {agg['n']} розборів зараховано тобі як відповідальному за угоду: АТС не передає, "
                "хто саме говорив. Коли АТС почне передавати оператора, розбір піде тому, хто говорив.")
    return {"label": label, "avg": a, "n": agg["n"], "best": agg["b"], "prev_avg": pa, "prev_n": prev["n"],
            "delta": (a - pa) if (a is not None and pa is not None) else None, "credit": credit,
            "credit_note": note, "explain": explain}


def _skills(uid, period):
    d1, d2 = engine.period_bounds(period)
    pd1, pd2 = engine.period_bounds(_prev(period))

    def window(a, b):
        rows = list(quality_qs(uid, a, b).values_list("scores", flat=True))
        out = {}
        for k in SKILL_KEYS:
            vals = []
            for r in rows:
                v = (r or {}).get(k)
                try:
                    if v is not None:
                        vals.append(int(v))
                except (TypeError, ValueError):
                    pass
            out[k] = round(sum(vals) / len(vals)) if vals else 0
        return out
    cur, prev = window(d1, d2), window(pd1, pd2)
    return [{"key": k, "label": SKILL_LABELS[k], "cur": cur[k], "prev": prev[k]} for k in SKILL_KEYS]


def _trend(uid, period):
    """Якість по календарних місяцях: 6 місяців до обраного включно."""
    pts = []
    for i in range(5, -1, -1):
        p = engine.add_months(engine.period_bounds(period)[0], -i).strftime("%Y-%m")
        d1, d2 = engine.period_bounds(p)
        agg = quality_qs(uid, d1, d2).aggregate(a=Avg("overall_score"), n=Count("id"))
        pts.append({"period": p, "date": MONTHS_SHORT[int(p[5:7])], "avg": round(agg["a"]) if agg["a"] is not None else None,
                    "n": agg["n"]})
    total_n = quality_qs(uid).count()
    nonnull = [x for x in pts if x["avg"] is not None]
    state = "empty" if total_n == 0 else ("sparse" if len(nonnull) < 2 else "enough")
    first_score = last_score = delta = None
    if state == "sparse":
        scores = list(quality_qs(uid).order_by("created_at").values_list("overall_score", flat=True))
        half = max(1, len(scores) // 2)
        first_score = round(sum(scores[:half]) / len(scores[:half]))
        rest = scores[half:] or scores[:half]
        last_score = round(sum(rest) / len(rest))
        delta = last_score - first_score
    return {"state": state, "points": pts, "first_score": first_score, "last_score": last_score, "delta": delta,
            "dialogs_needed": max(0, 3 - total_n)}


def _next_steps(uid, period, skills):
    nz = [s for s in skills if s["cur"]]
    if not nz:
        return None
    focus = min(nz, key=lambda s: s["cur"])
    fk = focus["key"]
    d1, d2 = engine.period_bounds(period)
    since = d1 - datetime.timedelta(days=60)
    rows = [a for a in DialogAnalysis.objects.filter(manager_id=uid, created_at__date__gte=since,
                                                     created_at__date__lte=d2).order_by("-created_at")[:200]
            if (a.scores or {}).get(fk) is not None]

    def sk(a):
        try:
            return int((a.scores or {}).get(fk, 999))
        except (TypeError, ValueError):
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
    wk = _week_start()
    marks = {m.key: m.done for m in PracticeMark.objects.filter(user_id=uid, week=wk)}
    practice = [{"key": f"{fk}:{i}", "text": t, "text_ru": (h.get("practice_ru") or [""] * 2)[i] if i < len(h.get("practice_ru") or []) else t,
                 "done": bool(marks.get(f"{fk}:{i}"))} for i, t in enumerate(h.get("practice", []))]
    return {"focus": {"key": fk, "label": focus["label"], "cur": focus["cur"], "prev": focus["prev"],
                      "target": min(100, max(focus["cur"] + 13, 65)),
                      "what": h.get("what", ""), "what_ru": h.get("what_ru", "")},
            "tips": tips, "model": model, "practice": practice, "week": wk.isoformat(),
            "practice_note": "Відмітки зберігаються до кінця тижня; з понеділка — нові справи."}


def _badges(uid):
    out = []
    for b in BadgeAward.objects.filter(manager_id=uid):
        if b.badge_code in BADGES:
            e, l, d = BADGES[b.badge_code]
            out.append({"code": b.badge_code, "emoji": e, "label": l, "desc": d})
    return out


def payload(uid, period, viewer=None):
    from . import contests
    from .season import season
    u = User.objects.filter(id=uid).first()
    skills = _skills(uid, period)
    data = {"id": uid, "name": (u.get_full_name() or u.username) if u else str(uid), "period": period,
            "period_label": _label(period), "periods": _periods(timezone.localdate()),
            "is_current": period == timezone.localdate().strftime("%Y-%m"),
            "points": _points(uid, period), "quality": _quality(uid, period), "skills": skills,
            "trend": _trend(uid, period), "season": season(u) if u else None, "badges": _badges(uid),
            "next_steps": _next_steps(uid, period, skills),
            "is_team_viewer": bool(viewer and is_team_viewer(viewer)), "is_self": bool(viewer and viewer.id == uid)}
    try:
        data["contests"] = contests.for_user(uid)
    except Exception:
        data["contests"] = None
    return data


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(payload(request.user.id, _month(request), request.user))


class ManagerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if request.user.id != pk and not is_team_viewer(request.user):
            return Response({"detail": "Сторінку розвитку іншої людини бачить лише керівник"}, status=403)
        return Response(payload(pk, _month(request), request.user))


class LeaderboardView(APIView):
    """Порівняння команди — лише власник / РОП. Співробітникам рейтингу між людьми більше немає (403)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_team_viewer(request.user):
            return Response({"detail": "Порівняння команди бачить лише керівник. Твій прогрес — «ти проти себе» на сторінці «Розвиток»."},
                            status=403)
        from .rules import month_points
        from .season import season
        period = _month(request)
        d1, d2 = engine.period_bounds(period)
        p = _prev(period)
        pd1, pd2 = engine.period_bounds(p)
        rows = []
        for m in sales_managers().order_by("id"):
            _r, pts = month_points(m.id, d1, d2)
            _pr, ppts = month_points(m.id, pd1, pd2)
            q = quality_qs(m.id, d1, d2).aggregate(a=Avg("overall_score"), n=Count("id"))
            pq = quality_qs(m.id, pd1, pd2).aggregate(a=Avg("overall_score"))
            s = season(m)
            rows.append({"id": m.id, "name": m.get_full_name() or m.username, "points": pts, "prev_points": ppts,
                         "quality": round(q["a"]) if q["a"] is not None else None, "quality_n": q["n"],
                         "prev_quality": round(pq["a"]) if pq["a"] is not None else None,
                         "season_index": s["index"], "season_level": (s["level"] or {}).get("name"),
                         "season_emoji": (s["level"] or {}).get("emoji")})
        qv = [r["quality"] for r in rows if r["quality"] is not None]
        return Response({"period": period, "period_label": _label(period), "prev_label": _label(p),
                         "periods": _periods(timezone.localdate()), "managers": rows, "me": request.user.id,
                         "team_avg": round(sum(qv) / len(qv)) if qv else None, "team_count": len(rows),
                         "quality_label": quality_label(),
                         "note": "Бачиш лише ти (власник / РОП). Співробітники бачать тільки себе: цей місяць проти минулого."})


class PracticeView(APIView):
    """Відмітки «маленьких справ на тиждень» — лише свої, лише поточний тиждень."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wk = _week_start()
        return Response({"week": wk.isoformat(), "marks": {m.key: m.done for m in PracticeMark.objects.filter(user=request.user, week=wk)}})

    def post(self, request):
        key = str(request.data.get("key") or "").strip()[:60]
        if not key:
            return Response({"detail": "Не вказано справу"}, status=400)
        done = bool(request.data.get("done"))
        wk = _week_start()
        PracticeMark.objects.update_or_create(user=request.user, week=wk, key=key,
                                              defaults={"done": done, "text": str(request.data.get("text") or "")[:300]})
        return Response({"week": wk.isoformat(), "key": key, "done": done})


def _settings_json(s):
    from . import contests
    return {"chat_sampling": s.chat_sampling, "chat_sample_per_week": s.chat_sample_per_week,
            "quality_label": quality_label(s), "contests": contests.state(),
            "cost_note": "Один ІІ-розбір коштує ≈ $0,02 (факт CRM: 338 розборів за 60 днів = $5,54). "
                         "3 чати × 3 менеджери × 4,3 тижня ≈ 39 розборів ≈ $0,8 на місяць."}


class SettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_team_viewer(request.user):
            return Response({"detail": "Немає доступу"}, status=403)
        return Response(_settings_json(GamSettings.get()))

    def patch(self, request):
        from apps.bounty.services import can_manage
        u = request.user
        d = request.data or {}
        wants_ai = any(k in d for k in ("chat_sampling", "chat_sample_per_week"))
        if wants_ai and not u.is_superuser:
            return Response({"detail": "Вибірку чатів (платний ІІ) вмикає лише власник"}, status=403)
        if "contests" in d and not (u.is_superuser or (is_team_viewer(u) and can_manage(u))):
            return Response({"detail": "Змагання вмикає власник / хто керує біржею задач"}, status=403)
        s = GamSettings.get()
        if "chat_sampling" in d:
            s.chat_sampling = bool(d.get("chat_sampling"))
        if "chat_sample_per_week" in d:
            try:
                s.chat_sample_per_week = max(1, min(20, int(d.get("chat_sample_per_week"))))
            except (TypeError, ValueError):
                return Response({"detail": "Кількість чатів — число 1–20"}, status=400)
        if "contests" in d:
            raw = d.get("contests") or {}
            if not isinstance(raw, dict):
                return Response({"detail": "contests — {код: true/false}"}, status=400)
            cfg = dict(s.contests or {})
            for code, on in raw.items():
                if code in cfg and isinstance(cfg[code], dict):
                    cfg[code] = {**cfg[code], "enabled": bool(on)}
            s.contests = cfg
        s.updated_by = u
        s.save()
        return Response(_settings_json(s))


class ContestsView(APIView):
    """Змагання тижня: результати всіх — лише власник / РОП; POST — нарахувати приз (власник / керує біржею)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from . import contests
        if not is_team_viewer(request.user):
            return Response({"detail": "Результати всіх бачить лише керівник; свої цифри — на сторінці «Розвиток»"}, status=403)
        try:
            mon, sun = contests.week_bounds(request.GET.get("week") or None)
        except contests.ContestError as e:
            return Response({"detail": e.text}, status=e.status)
        res = contests.results(mon, sun)
        st = contests.state()
        for s in st:
            c = contests.awarded(s["code"], res["week"])
            s["awarded"] = ({"user_id": c.user_id, "name": c.user.get_full_name() or c.user.username,
                             "amount": float(c.amount or 0), "status": c.status} if c else None)
        return Response({**res, "contests": st})

    def post(self, request):
        from apps.bounty.services import can_manage
        from . import contests
        u = request.user
        if not (u.is_superuser or (is_team_viewer(u) and can_manage(u))):
            return Response({"detail": "Приз нараховує власник / хто керує біржею задач"}, status=403)
        try:
            c = contests.award(str(request.data.get("code") or ""), str(request.data.get("week") or ""), u,
                               request.data.get("user_id"))
        except contests.ContestError as e:
            return Response({"detail": e.text}, status=e.status)
        return Response({"ok": True, "claim_id": c.id, "user_id": c.user_id, "amount": float(c.amount or 0),
                         "payroll_period": c.payroll_period})
