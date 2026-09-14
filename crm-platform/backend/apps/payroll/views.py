"""API «Ставки співробітників» (/api/payroll/…). Бачить і змінює за замовчуванням лише власник:
payroll.rates.view / payroll.rates.edit, акти закриває objects.act.close."""
from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import engine
from .models import ObjectAct, PayComponent, PayPolicy, PayRateLog, PayScheme

KINDS = dict(PayComponent.KIND)


def _can(u, code):
    return bool(u and u.is_authenticated and (u.is_superuser or (hasattr(u, "has_perm_code") and u.has_perm_code(code))))


def _deny(msg="Немає доступу до ставок"):
    return Response({"detail": msg}, status=403)


def _comp_json(c):
    return {"id": c.id, "kind": c.kind, "kind_label": KINDS.get(c.kind, c.kind), "title": c.title, "params": c.params,
            "order": c.order, "active": c.active}


def _scheme_json(s, with_cost=False, pol=None, sh=None):
    d = {"id": s.id, "user_id": s.user_id,
         "user_name": (s.user.get_full_name() or s.user.username) if s.user_id else "",
         "position": s.position, "department": s.department, "title": s.title, "purpose": s.purpose,
         "status": s.status, "employment": s.employment, "employment_label": s.get_employment_display(),
         "valid_from": s.valid_from.isoformat(), "valid_to": s.valid_to.isoformat() if s.valid_to else None,
         "is_vacancy": s.is_vacancy, "in_plan": s.in_plan,
         "planned_start": s.planned_start.isoformat() if s.planned_start else None,
         "options": s.options, "note": s.note, "components": [_comp_json(c) for c in s.components.all()]}
    if with_cost:
        d["cost"] = engine.scheme_cost(s, pol, sh)
    return d


def _snapshot(s):
    return _scheme_json(s)


def _parse_date(v, default=None):
    if not v:
        return default
    return date.fromisoformat(str(v)[:10] if len(str(v)) >= 10 else str(v) + "-01")


class SchemesView(APIView):
    """GET — усі схеми (діючі, минулі версії, вакансії). POST — нова схема/вакансія/посада."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, "payroll.rates.view"):
            return _deny()
        pol = engine.policy()
        sh = engine.shares(pol)
        qs = PayScheme.objects.exclude(status="archived").select_related("user").prefetch_related("components")
        items = [_scheme_json(s, with_cost=(s.purpose == "official"), pol=pol, sh=sh) for s in qs]
        User = get_user_model()
        users = [{"id": u.id, "name": u.get_full_name() or u.username} for u in
                 User.objects.filter(is_active=True).exclude(username__startswith="b24_").order_by("first_name", "username")]
        return Response({"schemes": items, "users": users, "kinds": [{"kind": k, "label": v} for k, v in PayComponent.KIND],
                         "guarantee_conditions": engine.GUARANTEE_CONDITIONS,
                         "can_edit": _can(request.user, "payroll.rates.edit"),
                         "can_close_acts": _can(request.user, "objects.act.close")})

    def post(self, request):
        if not _can(request.user, "payroll.rates.edit"):
            return _deny("Немає права змінювати ставки")
        d = request.data
        with transaction.atomic():
            s = PayScheme.objects.create(
                user_id=d.get("user_id") or None, position=(d.get("position") or "Посада")[:120],
                department=(d.get("department") or "")[:60], title=(d.get("title") or "")[:160],
                purpose=d.get("purpose") or "official", status=d.get("status") or "active",
                employment=d.get("employment") or "none",
                valid_from=_parse_date(d.get("valid_from"), timezone.localdate().replace(day=1)),
                is_vacancy=bool(d.get("is_vacancy")), in_plan=bool(d.get("in_plan", not d.get("is_vacancy"))),
                planned_start=_parse_date(d.get("planned_start")), options=d.get("options") or {},
                note=d.get("note") or "", created_by=request.user)
            _save_components(s, d.get("components") or [])
            PayRateLog.objects.create(scheme=s, action="create", after=_snapshot(s), user=request.user)
        return Response(_scheme_json(s, with_cost=True))


def _save_components(s, comps):
    keep = []
    for i, c in enumerate(comps):
        kind = c.get("kind")
        if kind not in KINDS:
            continue
        obj = PayComponent.objects.filter(scheme=s, id=c.get("id")).first() if c.get("id") else None
        if obj is None:
            obj = PayComponent(scheme=s, kind=kind)
        obj.kind = kind
        obj.title = (c.get("title") or "")[:160]
        obj.params = c.get("params") or {}
        obj.order = i
        obj.active = c.get("active", True) is not False
        obj.save()
        keep.append(obj.id)
    PayComponent.objects.filter(scheme=s).exclude(id__in=keep).delete()


class SchemeSaveView(APIView):
    """POST /api/payroll/schemes/<id>/save/ — зберегти зміни.
    Якщо «діє з» пізніше за поточну версію → НОВА версія (стара закривається днем раніше, минулі місяці не змінюються).
    Якщо той самий місяць → правка цієї версії (записується в історію)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _can(request.user, "payroll.rates.edit"):
            return _deny("Немає права змінювати ставки")
        s = PayScheme.objects.filter(pk=pk).first()
        if not s:
            return Response({"detail": "Схему не знайдено"}, status=404)
        d = request.data
        vf = _parse_date(d.get("valid_from"), s.valid_from)
        before = _snapshot(s)
        with transaction.atomic():
            if vf > s.valid_from and not s.is_vacancy:
                new = PayScheme.objects.create(
                    user=s.user, position=(d.get("position") or s.position)[:120], department=(d.get("department", s.department) or "")[:60],
                    title=(d.get("title", s.title) or "")[:160], purpose=s.purpose, status="active",
                    employment=d.get("employment") or s.employment, valid_from=vf, is_vacancy=False, in_plan=True,
                    options=d.get("options", s.options) or {}, note=d.get("note", s.note) or "", based_on=s, created_by=request.user)
                _save_components(new, [{**c, "id": None} for c in (d.get("components") or [])])
                s.valid_to = vf.fromordinal(vf.toordinal() - 1)
                s.save(update_fields=["valid_to", "updated_at"])
                PayRateLog.objects.create(scheme=new, action="new_version", before=before, after=_snapshot(new), user=request.user,
                                          note=f"нова версія з {vf:%d.%m.%Y}; попередня діє до {s.valid_to:%d.%m.%Y}")
                return Response(_scheme_json(new, with_cost=True))
            for f in ("position", "department", "title", "employment", "note"):
                if f in d:
                    setattr(s, f, (d.get(f) or "")[:160] if f != "note" else (d.get(f) or ""))
            if "status" in d and d["status"] in dict(PayScheme.STATUS):
                s.status = d["status"]
            if "options" in d:
                s.options = d.get("options") or {}
            if s.is_vacancy:
                if "in_plan" in d:
                    s.in_plan = bool(d["in_plan"])
                if "planned_start" in d:
                    s.planned_start = _parse_date(d.get("planned_start"))
                if "user_id" in d and d.get("user_id"):  # вакансію закрили — людина вийшла
                    s.user_id = d["user_id"]
                    s.is_vacancy = False
                    s.in_plan = True
                    s.valid_from = s.planned_start or vf
            if vf < s.valid_from:
                s.valid_from = vf
            s.save()
            if "components" in d:
                _save_components(s, d.get("components") or [])
            PayRateLog.objects.create(scheme=s, action="update", before=before, after=_snapshot(s), user=request.user)
        return Response(_scheme_json(s, with_cost=True))


class SchemeArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _can(request.user, "payroll.rates.edit"):
            return _deny("Немає права змінювати ставки")
        s = PayScheme.objects.filter(pk=pk).first()
        if not s:
            return Response({"detail": "Схему не знайдено"}, status=404)
        before = _snapshot(s)
        s.status = "archived"
        s.save(update_fields=["status", "updated_at"])
        PayRateLog.objects.create(scheme=s, action="archive", before=before, user=request.user)
        return Response({"ok": True})


class ComponentMarkView(APIView):
    """POST /api/payroll/components/<id>/mark/ {period, score?} або {period, ok, note} —
    оцінка стандарту за місяць або «умови гарантії виконано»."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _can(request.user, "payroll.rates.edit"):
            return _deny("Немає права змінювати ставки")
        c = PayComponent.objects.filter(pk=pk).first()
        period = (request.data.get("period") or "")[:7]
        if not c or len(period) != 7:
            return Response({"detail": "Невірні дані"}, status=400)
        p = dict(c.params or {})
        before = dict(p)
        if c.kind == "standard":
            try:
                score = max(0.0, min(1.0, float(request.data.get("score"))))
            except (TypeError, ValueError):
                return Response({"detail": "Оцінка — число від 0 до 1"}, status=400)
            p.setdefault("scores", {})[period] = score
        elif c.kind == "guarantee":
            p.setdefault("checks", {})[period] = {"ok": bool(request.data.get("ok")), "note": (request.data.get("note") or "")[:200],
                                                   "by": request.user.get_full_name() or request.user.username,
                                                   "at": timezone.now().isoformat()}
        else:
            return Response({"detail": "Для цієї частини позначок немає"}, status=400)
        c.params = p
        c.save(update_fields=["params"])
        PayRateLog.objects.create(scheme=c.scheme, action="mark", before={"params": before}, after={"params": p}, user=request.user,
                                  note=f"{c.get_kind_display()} · {period}")
        return Response(_comp_json(c))


class CalcView(APIView):
    """GET ?period=YYYY-MM[&user=ID][&scheme=ID] — ЗП за ставками (одна людина або команда)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, "payroll.rates.view"):
            return _deny()
        period = (request.query_params.get("period") or timezone.localdate().strftime("%Y-%m"))[:7]
        sid = request.query_params.get("scheme")
        if sid:
            s = PayScheme.objects.filter(pk=sid).select_related("user").first()
            if not s:
                return Response({"detail": "Схему не знайдено"}, status=404)
            return Response(engine.calc(s.user, period, scheme=s, purpose=s.purpose))
        uid = request.query_params.get("user")
        if uid:
            u = get_user_model().objects.filter(pk=uid).first()
            if not u:
                return Response({"detail": "Співробітника не знайдено"}, status=404)
            return Response(engine.calc(u, period))
        return Response(engine.calc_team(period))


class BreakevenView(APIView):
    """GET ?with=1,2&without=3 — точка беззбитковості за ATM зі ставками; with/without — «що якщо» для вакансій і людей."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_can(request.user, "payroll.rates.view") or _can(request.user, "finance.tab.be")):
            return _deny()

        def ids(k):
            return tuple(int(x) for x in (request.query_params.get(k) or "").split(",") if x.strip().isdigit())
        data = engine.breakeven_atm(extra_ids=ids("with"), without_ids=ids("without"))
        if not _can(request.user, "payroll.rates.view"):  # без права на ставки — без імен і сум по людях
            data["payroll"] = []
            data["vacancies"] = [{k: v for k, v in r.items() if k in ("position", "included", "delta_breakeven")} for r in data["vacancies"]]
        return Response(data)


class PolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, "payroll.rates.view"):
            return _deny()
        from apps.finance.models import FinModelArticle
        arts = [{"id": a.id, "name": a.name, "category": a.get_category_display(), "value": float(a.value)}
                for a in FinModelArticle.objects.filter(active=True, category__in=["revenue_fund", "fixed", "variable", "upr_cat2"])]
        return Response({"params": engine.policy(), "articles": arts})

    def post(self, request):
        if not _can(request.user, "payroll.rates.edit"):
            return _deny("Немає права змінювати правила")
        p, _ = PayPolicy.objects.get_or_create(pk=1)
        before = dict(p.params or {})
        new = request.data.get("params") or {}
        if not isinstance(new, dict):
            return Response({"detail": "params — обʼєкт"}, status=400)
        p.params = engine._merge(dict(p.params or {}), new)
        p.updated_by = request.user
        p.save()
        PayRateLog.objects.create(action="policy", before=before, after=p.params, user=request.user)
        return Response({"params": engine.policy()})


class LogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user, "payroll.rates.view"):
            return _deny()
        qs = PayRateLog.objects.select_related("user", "scheme")
        if request.query_params.get("scheme"):
            qs = qs.filter(scheme_id=request.query_params["scheme"])
        return Response({"results": [{"id": l.id, "at": l.at.isoformat(), "action": l.action, "note": l.note,
                                      "user": (l.user.get_full_name() or l.user.username) if l.user_id else "",
                                      "scheme": str(l.scheme) if l.scheme_id else "Правила компанії",
                                      "before": l.before, "after": l.after} for l in qs[:200]]})


def _act_json(a):
    return {"id": a.id, "title": a.title, "number": a.number, "act_date": a.act_date.isoformat(),
            "amount_total": float(a.amount_total), "status": a.status, "status_label": a.get_status_display(),
            "contact_id": a.contact_id, "contact_name": str(a.contact) if a.contact_id else "",
            "manager_id": a.manager_id, "manager_name": (a.manager.get_full_name() or a.manager.username) if a.manager_id else "",
            "closed_at": a.closed_at.isoformat() if a.closed_at else None,
            "closed_by": (a.closed_by.get_full_name() or a.closed_by.username) if a.closed_by_id else "",
            "commission_pct": float(a.commission_pct_applied) if a.commission_pct_applied is not None else None,
            "commission_amount": float(a.commission_amount) if a.commission_amount is not None else None,
            "payroll_period": a.payroll_period, "note": a.note}


def _act_pct(manager, on):
    sc = engine.active_scheme(manager, on) if manager else None
    if sc:
        for c in sc.components.filter(active=True, kind="revenue_share"):
            if (c.params or {}).get("basis") == "object_acts":
                return float(c.params.get("pct") or 0)
    return 2.0


class ActsView(APIView):
    """Акти обʼєктів: GET список; POST внести акт (payroll.rates.edit)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_can(request.user, "payroll.rates.view") or _can(request.user, "objects.act.close")):
            return _deny()
        return Response({"results": [_act_json(a) for a in ObjectAct.objects.select_related("contact", "manager", "closed_by")[:300]],
                         "can_close": _can(request.user, "objects.act.close")})

    def post(self, request):
        if not _can(request.user, "payroll.rates.edit"):
            return _deny("Немає права вносити акти")
        d = request.data
        try:
            amount = float(str(d.get("amount_total")).replace(",", ".").replace(" ", ""))
        except (TypeError, ValueError):
            return Response({"detail": "Сума акту — число"}, status=400)
        a = ObjectAct.objects.create(title=(d.get("title") or "Акт")[:200], number=(d.get("number") or "")[:40],
                                     act_date=_parse_date(d.get("act_date"), timezone.localdate()), amount_total=amount,
                                     contact_id=d.get("contact_id") or None, manager_id=d.get("manager_id") or None,
                                     note=d.get("note") or "", created_by=request.user)
        return Response(_act_json(a))


class ActCloseView(APIView):
    """POST /api/payroll/acts/<id>/close/ — «Акт закрито» (лише objects.act.close). Ідемпотентно."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _can(request.user, "objects.act.close"):
            return _deny("Закривати акти може лише власник")
        with transaction.atomic():
            a = ObjectAct.objects.select_for_update().filter(pk=pk).first()
            if not a:
                return Response({"detail": "Акт не знайдено"}, status=404)
            if a.status != "closed":
                now = timezone.now()
                pct = _act_pct(a.manager, timezone.localdate())
                a.status = "closed"
                a.closed_at = now
                a.closed_by = request.user
                a.commission_pct_applied = pct
                a.commission_amount = round(float(a.amount_total) * pct / 100, 2)
                a.payroll_period = timezone.localdate().strftime("%Y-%m")
                a.save()
        return Response(_act_json(a))
