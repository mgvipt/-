"""API: «Тестовий чат», «Перевірка чернеток», «Контролер», «Публікація в Юлю», веб-чат (14.09.2026, ai-kb2).

Права:
  тестовий чат і «як відповість зараз у ChatPlace» — knowledge.edit / knowledge.approve / власник
      (ШІ коштує центи; розмова НІДЕ не зберігається і нікому не надсилається);
  оцінка перевірки чернеток — ті самі; запуск перевірки — knowledge.approve (за замовчуванням лише власник);
  «Затвердити всі «готово» у темі», контролер, публікація в Юлю, веб-чат — ЛИШЕ власник (superuser).
Нічого не запускається за розкладом — лише ці кнопки.
"""
from django.db.models import F
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import precheck as pc
from . import publisher, runs
from .answer import HAIKU, MODELS, SONNET, TEST_AGENTS, answer, estimate_usd
from .models import KnowledgeItem, KnowledgeRun, KnowledgeSettings, log_version
from .views import approve_item, can_approve, can_edit, can_view

TOPICS = {c for c, _ in KnowledgeItem.TOPICS}
AGENT_NOTES = {
    "yulia_ig": "Модель CRM (Haiku) на базі, яку Юля IG отримає після публікації. Справжня Юля в ChatPlace має ще свої "
                "глобальні правила — порівняйте кнопкою «Як відповість зараз у ChatPlace».",
    "yulia_tiktok": "Те саме для Юлі TikTok. Кнопка «Як відповість зараз у ChatPlace» питає справжнього бота TikTok.",
    "yulia_web": "Рівно те, що відповість веб-чат на сайті, коли ви його ввімкнете (лише записи з позначкою «Сайт»). "
                 "Із чернетками — як відповідатиме після їх затвердження.",
    "compose_assist": "У CRM ✨ покращує чернетку менеджера. Тут — відповідь, яку він склав би на своїй базі (Sonnet).",
    "rop_hint": "Та сама підказка, що кнопка AI-РОП у чаті: діагноз паузи + готова фраза (Sonnet).",
    "funnel_agent": "Агент воронки клієнту не пише — показує, які дії зробив би (стадія, анкета, тест-набір). "
                    "Нічого не виконується.",
}


def _owner(u):
    return bool(u and u.is_authenticated and u.is_superuser)


def _deny(msg):
    return Response({"detail": msg}, status=403)


def _topic(v):
    v = str(v or "").strip()
    return v if v in TOPICS else None


def _agent_model(agent):
    if agent == "yulia_web":
        return KnowledgeSettings.get().webchat_model or HAIKU
    if agent in ("rop_hint", "compose_assist"):
        return SONNET
    if agent == "funnel_agent":
        from apps.crm.models import AgentConfig
        return AgentConfig.get().model or HAIKU
    return HAIKU


class TestChatView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not can_view(request.user):
            return _deny("Немає доступу до бази знань")
        return Response({
            "agents": [{"value": c, "label": l, "model": _agent_model(c), "note": AGENT_NOTES.get(c, "")}
                       for c, l in TEST_AGENTS],
            "can_test": can_edit(request.user), "stored": False,
        })

    def post(self, request):
        if not can_edit(request.user):
            return _deny("Тестувати може співробітник із правом «База знань: додавати й правити чернетки»")
        d = request.data
        agent = str(d.get("agent") or "")
        if agent not in dict(TEST_AGENTS):
            return Response({"detail": "Невідомий агент"}, status=400)
        msgs = d.get("messages") if isinstance(d.get("messages"), list) else []
        model = KnowledgeSettings.get().webchat_model if agent == "yulia_web" else None
        try:
            r = answer(agent, msgs, include_drafts=bool(d.get("include_drafts", True)), topic=_topic(d.get("topic")),
                       estimate_only=bool(d.get("estimate_only")), model=model)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        except Exception as e:  # ключ / мережа
            return Response({"detail": "ШІ недоступний: %s" % str(e)[:300]}, status=502)
        return Response(r)


class ChatPlaceTestView(APIView):
    """«Як відповість зараз у ChatPlace» — ai_agent_test_question: лише тест, нічого не записує в ChatPlace."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not can_edit(request.user):
            return _deny("Немає права тестувати")
        bot = str(request.data.get("bot") or "")
        q = str(request.data.get("question") or "").strip()[:1000]
        if bot not in publisher.BOTS or not q:
            return Response({"detail": "Потрібні bot (ig / tt) і питання"}, status=400)
        try:
            res = publisher.default_mcp()("ai_agent_test_question", {"botId": publisher.BOTS[bot]["bot_id"], "question": q})
        except Exception as e:
            return Response({"detail": "ChatPlace: %s" % str(e)[:300]}, status=502)
        data = res if isinstance(res, dict) else {"answer": str(res or "")}
        return Response({
            "bot": bot, "label": publisher.BOTS[bot]["label"], "answer": str(data.get("answer") or ""),
            "answered": bool(data.get("isQuestionAnswered")),
            "note": "ChatPlace перевіряє ОДНЕ питання без історії розмови — на вже опублікованій базі Юлі та її "
                    "глобальних правилах. Нічого не записує."})


class PrecheckView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not can_view(request.user):
            return _deny("Немає доступу")
        s = pc.summary(_topic(request.query_params.get("topic")))
        return Response({
            **s, "labels": [{"value": k, "label": v} for k, v in pc.LABELS.items()], "model": pc.MODEL,
            "runs": [runs.run_dict(r) for r in KnowledgeRun.objects.filter(kind="precheck").select_related("created_by")[:5]],
            "can_run": can_approve(request.user), "is_owner": _owner(request.user),
        })

    def post(self, request):
        u, d = request.user, request.data
        topic, recheck = _topic(d.get("topic")), bool(d.get("recheck"))
        if d.get("estimate"):
            if not can_edit(u):
                return _deny("Немає права")
            return Response(pc.estimate(topic, recheck))
        if not can_approve(u):
            return _deny("Запускає перевірку власник (право «База знань: затверджувати»)")
        if runs.busy("precheck"):
            return Response({"detail": "Перевірка вже виконується — дочекайтеся"}, status=409)
        est = pc.estimate(topic, recheck)
        if not est["drafts"]:
            return Response({"detail": "Немає чернеток для перевірки (усі вже перевірені — поставте «перевірити заново»)"},
                            status=400)
        run = KnowledgeRun.objects.create(kind="precheck", params={"topic": topic or "", "recheck": recheck},
                                          est_cost_usd=est["est_usd"], total=est["calls"], created_by=u)
        runs.spawn(run, lambda r, prog: pc.run_precheck(r, topic, recheck, prog))
        return Response(runs.run_dict(KnowledgeRun.objects.get(pk=run.pk)), status=201)


class ApproveReadyView(APIView):
    """«Затвердити всі «готово» у темі» — лише власник; спершу кількість, потім підтвердження тієї ж кількості."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        u = request.user
        if not _owner(u):
            return _deny("Масово затверджує лише власник")
        topic = _topic(request.data.get("topic"))
        if not topic:
            return Response({"detail": "Оберіть тему"}, status=400)
        qs = (KnowledgeItem.objects.filter(status="draft", topic=topic, precheck__label="ready",
                                           precheck__item_version=F("version")).order_by("id"))
        ids = list(qs.values_list("id", flat=True))
        expected = request.data.get("expected")
        if expected in (None, ""):
            return Response({"topic": topic, "count": len(ids), "ids": ids})
        try:
            expected = int(expected)
        except (TypeError, ValueError):
            return Response({"detail": "expected — число"}, status=400)
        if expected != len(ids):
            return Response({"detail": "Зараз «готово» у темі %d, а підтверджено %d. Оновіть список." % (len(ids), expected),
                             "count": len(ids)}, status=409)
        for item in qs:
            approve_item(item, u, "масово: «готово» за попередньою перевіркою")
        return Response({"topic": topic, "approved": len(ids), "ids": ids})


class ControllerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not can_view(request.user):
            return _deny("Немає доступу")
        return Response({
            "periods": [{"value": k, "label": v} for k, v in runs.PERIODS], "scheduled": False,
            "model": KnowledgeSettings.get().reviewer_model, "max": runs.MAX_CONVS, "can_run": _owner(request.user),
            "runs": [runs.run_dict(r) for r in KnowledgeRun.objects.filter(kind="controller").select_related("created_by")[:10]],
        })

    def post(self, request):
        u, d = request.user, request.data
        if not _owner(u):
            return _deny("Контролер запускає лише власник")
        period = str(d.get("period") or "yesterday")
        if period not in dict(runs.PERIODS):
            return Response({"detail": "Період: " + ", ".join(dict(runs.PERIODS))}, status=400)
        est = runs.estimate_controller(period, d.get("n") or 20)
        if d.get("estimate"):
            return Response({k: v for k, v in est.items() if k != "conversation_ids"})
        if not est["count"]:
            return Response({"detail": "Немає нових закритих чатів за цей період"}, status=400)
        if runs.busy("controller"):
            return Response({"detail": "Контролер уже працює — дочекайтеся"}, status=409)
        run = KnowledgeRun.objects.create(kind="controller", params={
            "period": period, "n": est["n"], "conversation_ids": est["conversation_ids"], "model": est["model"]},
            est_cost_usd=est["est_usd"], total=est["count"], created_by=u)
        runs.spawn(run, runs.run_controller)
        return Response(runs.run_dict(KnowledgeRun.objects.get(pk=run.pk)), status=201)


class RunView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not can_view(request.user):
            return _deny("Немає доступу")
        run = KnowledgeRun.objects.select_related("created_by").filter(pk=pk).first()
        if not run:
            return Response({"detail": "Не знайдено"}, status=404)
        return Response(runs.run_dict(run))


class PublishPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _owner(request.user):
            return _deny("Публікує в Юлю лише власник")
        bot = str(request.data.get("bot") or "")
        if bot not in publisher.BOTS:
            return Response({"detail": "bot: ig або tt"}, status=400)
        try:
            preview, _remote, _ops = runs.publish_preview(bot)
        except Exception as e:
            return Response({"detail": "ChatPlace: %s" % str(e)[:300]}, status=502)
        return Response(preview)


class PublishView(APIView):
    """Запис у ChatPlace — лише власник, лише з тим самим відбитком плану, що він бачив. Бекап — у KnowledgeRun."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        u, d = request.user, request.data
        if not _owner(u):
            return _deny("Публікує в Юлю лише власник")
        bot = str(d.get("bot") or "")
        if bot not in publisher.BOTS:
            return Response({"detail": "bot: ig або tt"}, status=400)
        if runs.busy("publish"):
            return Response({"detail": "Публікація вже виконується — дочекайтеся"}, status=409)
        try:
            preview, remote, _ops = runs.publish_preview(bot)
        except Exception as e:
            return Response({"detail": "ChatPlace: %s" % str(e)[:300]}, status=502)
        try:
            changes = int(d.get("changes"))
        except (TypeError, ValueError):
            changes = -1
        if preview["fingerprint"] != str(d.get("fingerprint") or "") or preview["changes"] != changes:
            return Response({"detail": "План змінився (хтось затвердив запис або змінив базу в ChatPlace). "
                                       "Подивіться зміни ще раз.", "preview": preview}, status=409)
        if not preview["changes"]:
            return Response({"detail": "Змін немає"}, status=400)
        run = KnowledgeRun.objects.create(kind="publish", params={"bot": bot, "fingerprint": preview["fingerprint"],
                                                                  "changes": preview["changes"]},
                                          backup=remote, total=preview["changes"], created_by=u)
        runs.spawn(run, runs.run_publish)
        return Response(runs.run_dict(KnowledgeRun.objects.get(pk=run.pk)), status=201)


class WebchatAudienceView(APIView):
    """Додати агента «Сайт (веб-чат)» до записів Юлі IG (лише власник): без expected — лише кількість."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        u = request.user
        if not _owner(u):
            return _deny("Лише власник")
        statuses = ["approved", "draft"] if request.data.get("include_drafts") else ["approved"]
        items = [i for i in KnowledgeItem.objects.filter(status__in=statuses).order_by("id")
                 if "yulia_ig" in (i.audience or []) and "yulia_web" not in (i.audience or [])]
        expected = request.data.get("expected")
        if expected in (None, ""):
            return Response({"count": len(items), "statuses": statuses})
        if str(expected) != str(len(items)):
            return Response({"detail": "Зараз таких записів %d, а підтверджено %s" % (len(items), expected),
                             "count": len(items)}, status=409)
        for i in items:
            i.audience = list(i.audience or []) + ["yulia_web"]
            i.version += 1
            i.updated_by = u
            i.save(update_fields=["audience", "version", "updated_by", "updated_at"])
            log_version(i, "edit", u, "додано агента «Сайт (веб-чат)»")
        return Response({"updated": len(items)})


def webchat_estimate():
    """Орієнтир для інтерфейсу: одна відповідь веб-чату ≈ 6 тис. символів запиту + 300 токенів відповіді."""
    m = KnowledgeSettings.get().webchat_model or HAIKU
    return {"model": m, "per_reply_usd": estimate_usd(m, 7000, 300), "models": MODELS}
