"""Вбудований Claude-агент Wallcov-CRM. Автономно рухає лід/сделку по воронці
та створює задачі співробітникам за глобальними правилами (GlobalRule).
Кожна дія — у Історію змін (actor «AI-агент») + аудит AgentRun."""
import json, os, urllib.request
from django.utils import timezone
from datetime import timedelta
from .models import GlobalRule, Task, AgentRun, AgentConfig, log_activity

ROOMS = ["Кухня", "Спальня", "Вітальня", "Ванна", "Коридор", "Офіс", "Салон краси", "Кафе/ресторан", "Інше"]
PREP = ["Ідеально гладкі (під фарбування)", "Можна дефекти (під шпалери)", "Не підготовлені"]
MATS = ["Galateya", "Pattera (Травертин)", "Mermi Silk", "Eleganti", "Celestial", "Velvet Luna", "Slate", "Ще не визначився"]
TERMS = ["Терміново (1-2 тиж)", "В процесі (місяць)", "Планує (3+ міс)", "На майбутнє"]
PROBE = ["Пробник", "Розрахунок на весь обʼєм"]
PAY = ["Повна (LiqPay/Mono)", "Накладений платіж", "Передоплата + доплата"]
SHIP = ["НП відділення", "НП курʼєр додому", "Самовивіз зі складу", "Власний курʼєр"]
CONTACTED = ["Ні — вперше", "Так — був пробник", "Так — дивився раніше"]
APPLIER = ["Сам наноситиму", "Потрібен майстер", "Ще не вирішив"]

API = "https://api.anthropic.com/v1/messages"

TOOLS = [
    {"name": "move_stage", "description": "Перемістити ліда/сделку на іншу стадію воронки (тільки вперед). Викликай коли клієнт за діалогом дозрів до наступної стадії за правилами воронки.",
     "input_schema": {"type": "object", "properties": {
         "to_stage": {"type": "string", "description": "Точна назва цільової стадії"},
         "reason": {"type": "string", "description": "Коротко чому"}}, "required": ["to_stage", "reason"]}},
    {"name": "create_task", "description": "Створити задачу співробітнику. Напр. дожим менеджеру коли клієнт замовк; задача складу/тонуванню коли є оплата і треба готувати замовлення.",
     "input_schema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": ["manager", "warehouse", "tinting", "followup", "other"]},
         "title": {"type": "string"}, "body": {"type": "string"},
         "due_hours": {"type": "integer", "description": "Через скільки годин дедлайн (0=без)"}},
      "required": ["kind", "title"]}},
    {"name": "fill_needs", "description": "Заповнити анкету виявлення потреби даними які клієнт ЯВНО назвав у діалозі. Передавай ТІЛЬКИ те що клієнт реально сказав, решту лиши порожнім. Не вигадуй.",
     "input_schema": {"type": "object", "properties": {
         "room": {"type": "string", "enum": ROOMS}, "area": {"type": "string", "description": "площа стін, число м²"},
         "prep": {"type": "string", "enum": PREP}, "term": {"type": "string", "enum": TERMS},
         "city": {"type": "string"}, "material": {"type": "string", "enum": MATS},
         "color": {"type": "string"}, "probe": {"type": "string", "enum": PROBE},
         "applier": {"type": "string", "enum": APPLIER}, "budget": {"type": "string", "description": "бюджет, число грн"},
         "pay": {"type": "string", "enum": PAY}, "ship": {"type": "string", "enum": SHIP},
         "contacted": {"type": "string", "enum": CONTACTED}, "objections": {"type": "string", "description": "заперечення/питання клієнта"}}, "required": []}},
    {"name": "make_offer", "description": "\u0410\u0412\u0422\u041e-\u041f\u0420\u041e\u0414\u0410\u0416 \u0442\u0435\u0441\u0442-\u043d\u0430\u0431\u043e\u0440\u0443: \u043a\u043e\u043b\u0438 \u043a\u043b\u0456\u0454\u043d\u0442 \u042f\u0412\u041d\u041e \u043e\u0431\u0440\u0430\u0432 \u043a\u043e\u043d\u043a\u0440\u0435\u0442\u043d\u0438\u0439 \u0442\u0435\u0441\u0442-\u043d\u0430\u0431\u0456\u0440/\u043c\u0430\u0442\u0435\u0440\u0456\u0430\u043b \u2014 \u0434\u043e\u0434\u0430\u0439 \u0442\u043e\u0432\u0430\u0440 \u0437 \u043d\u043e\u043c\u0435\u043d\u043a\u043b\u0430\u0442\u0443\u0440\u0438, \u043d\u0430\u0434\u0456\u0448\u043b\u0438 \u043f\u0440\u043e\u0440\u0430\u0445\u0443\u043d\u043e\u043a + \u043f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f LiqPay, \u043f\u0440\u043e\u0441\u0443\u043d\u044c \u0441\u0442\u0430\u0434\u0456\u044e. \u0422\u0456\u043b\u044c\u043a\u0438 \u043a\u043e\u043b\u0438 \u043a\u043b\u0456\u0454\u043d\u0442 \u043e\u0431\u0440\u0430\u0432. \u041d\u0430\u0437\u0432\u0443 \u0431\u0435\u0440\u0438 \u0422\u041e\u0427\u041d\u041e \u0437\u0456 \u0441\u043f\u0438\u0441\u043a\u0443 \u0442\u0435\u0441\u0442-\u043d\u0430\u0431\u043e\u0440\u0456\u0432.",
     "input_schema": {"type": "object", "properties": {
         "items": {"type": "array", "items": {"type": "object", "properties": {
             "name": {"type": "string"}, "qty": {"type": "number"}}, "required": ["name"]}},
         "reason": {"type": "string"}}, "required": ["items"]}},
    {"name": "no_action", "description": "Нічого не робити — стадія правильна, дій не треба.",
     "input_schema": {"type": "object", "properties": {"why": {"type": "string"}}, "required": []}},
]

DEPT_BY_KIND = {"warehouse": "Склад", "tinting": "Виробництв", "manager": "продаж"}


def _call(system, user_text, model, max_tokens=1200):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY не налаштовано")
    from apps.crm.models import AgentConfig
    use_cache = AgentConfig.get().cache_enabled
    sys_block = [{"type": "text", "text": system}]
    tools = [dict(t) for t in TOOLS]
    if use_cache:
        sys_block[0]["cache_control"] = {"type": "ephemeral"}  # кешуємо системний промпт (правила+товари)
        if tools:
            tools[-1]["cache_control"] = {"type": "ephemeral"}  # + кеш схеми інструментів
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "system": sys_block,
        "messages": [{"role": "user", "content": user_text}], "tools": tools,
    }).encode()
    hdrs = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if use_cache:
        hdrs["anthropic-beta"] = "prompt-caching-2024-07-31"
    req = urllib.request.Request(API, data=body, headers=hdrs)
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.load(r)
    try:
        from apps.crm.ai import _log_usage
        _log_usage("ИИ-РОП дожим (продажник)", model, resp.get("usage") or {})
    except Exception:
        pass
    return resp


def build_system(entity, kind):
    parts = ["Ти AI-РОП компанії Wallcov (декоративні покриття для стін). Працюєш ВСЕРЕДИНІ CRM. "
             "Твоя задача: рухати ліда/сделку по воронці за правилами і створювати задачі співробітникам. "
             "Дій рішуче але точно: рухай стадію тільки коли клієнт реально дозрів. Якщо клієнт замовк — створи задачу-дожим менеджеру. "
             "Рухати можна ТІЛЬКИ вперед і на сусідню стадію (не перестрибуй). Відповідай українською у reason/тексті задач. "
             "ЗАПОВНЮЙ анкету потреби (fill_needs) даними які клієнт ЯВНО назвав у діалозі (приміщення, площа, матеріал, колір, бюджет, місто, терміни, спосіб оплати тощо) — це економить менеджеру час. Не вигадуй те чого клієнт не казав."]
    for gr in GlobalRule.objects.filter(enabled=True).order_by("block", "priority"):
        parts.append("## [%s] %s\n%s" % (gr.get_block_display(), gr.title, gr.body))
    if entity.funnel_id:
        stages = list(entity.funnel.stages.order_by("order").values_list("name", flat=True))
        parts.append("## Стадії воронки (по порядку): " + " → ".join(stages))
    if entity.funnel_id and "\u0442\u0435\u0441\u0442\u043e\u0432" in (entity.funnel.name or "").lower():
        from apps.warehouse.models import Product
        prods = list(Product.objects.filter(is_active=True).filter(name__iregex=r"\u0442\u0435\u0441\u0442\u043e\u0432|\u043f\u0440\u043e\u0431\u043d\u0438").order_by("name").values_list("name", "price")[:120])
        if prods:
            parts.append("## \u0414\u043e\u0441\u0442\u0443\u043f\u043d\u0456 \u0442\u0435\u0441\u0442-\u043d\u0430\u0431\u043e\u0440\u0438 (\u043d\u0430\u0437\u0432\u0430 \u0422\u041e\u0427\u041d\u041e \u0434\u043b\u044f make_offer):\n" + "\n".join("- %s \u2014 %s \u0433\u0440\u043d" % (n, p) for n, p in prods))
            parts.append("## \u041a\u041e\u041b\u0418 \u043a\u043b\u0456\u0454\u043d\u0442 \u044f\u0432\u043d\u043e \u043e\u0431\u0440\u0430\u0432 \u0442\u0435\u0441\u0442-\u043d\u0430\u0431\u0456\u0440 \u2014 \u0412\u0406\u0414\u0420\u0410\u0417\u0423 \u0432\u0438\u043a\u043b\u0438\u0447 make_offer \u0437 \u0442\u043e\u0447\u043d\u043e\u044e \u043d\u0430\u0437\u0432\u043e\u044e. \u042f\u043a\u0449\u043e \u0449\u0435 \u043d\u0435 \u043e\u0431\u0440\u0430\u0432 \u2014 \u0443\u0442\u043e\u0447\u043d\u0438, \u043e\u0444\u0444\u0435\u0440 \u043d\u0435 \u0440\u043e\u0431\u0438.")
    cfg = AgentConfig.get()
    if cfg.system_extra:
        parts.append("## Додатково: " + cfg.system_extra)
    return "\n\n".join(parts)


def build_context(entity, kind):
    from apps.inbox.models import Conversation, Message
    conv = Conversation.objects.filter(contact_id=entity.contact_id).order_by("-last_message_at").first() if entity.contact_id else None
    msgs = []
    if conv:
        for m in list(Message.objects.filter(conversation=conv).order_by("created_at").values("direction", "text"))[-25:]:
            if m.get("text"):
                msgs.append(("Клієнт: " if m["direction"] == "in" else "Ми: ") + m["text"])
    last_in = None
    if conv:
        lm = Message.objects.filter(conversation=conv, direction="in").order_by("-created_at").first()
        if lm:
            last_in = (timezone.now() - lm.created_at).days
    ctx = {
        "тип": kind, "поточна_стадія": entity.stage.name if entity.stage_id else None,
        "сума": str(getattr(entity, "amount", "") or ""),
        "днів_від_останнього_повідомлення_клієнта": last_in,
        "діалог": "\n".join(msgs)[-4500:],
    }
    return "Контекст картки:\n" + json.dumps(ctx, ensure_ascii=False) + "\n\nПроаналізуй і виклич потрібні інструменти."


def _move_stage(entity, kind, to_name, reason, user, autonomous):
    funnel = entity.funnel
    target = funnel.stages.filter(name__iexact=(to_name or "").strip()).first()
    if not target:
        target = funnel.stages.filter(name__icontains=(to_name or "").strip()[:12]).first()
    if not target or not entity.stage_id:
        return {"ok": False, "msg": "стадію не знайдено: %s" % to_name}
    if target.order <= entity.stage.order:
        return {"ok": False, "msg": "не вперед"}
    if target.order > entity.stage.order + 1:
        # тільки на наступну існуючу стадію (захист від дір у order)
        target = funnel.stages.filter(order__gt=entity.stage.order).order_by("order").first() or target
    if not autonomous:
        return {"ok": False, "proposed": "→ %s: %s" % (target.name, reason)}
    old = entity.stage.name
    entity.stage = target
    flds = ["stage"]
    if hasattr(entity, "stage_changed_at"):
        entity.stage_changed_at = timezone.now(); flds.append("stage_changed_at")
    entity.save(update_fields=flds)
    log_activity(kind, entity.id, "AI-агент: стадія", "%s → %s (%s)" % (old, target.name, reason), user, "AI-агент")
    return {"ok": True, "moved_to": target.name}


def _create_task(entity, kind, inp, user, autonomous):
    from apps.accounts.models import Department
    dept = None
    dn = DEPT_BY_KIND.get(inp.get("kind"))
    if dn:
        dept = Department.objects.filter(name__icontains=dn).first()
    due = None
    if inp.get("due_hours"):
        due = timezone.now() + timedelta(hours=int(inp["due_hours"]))
    t = Task.objects.create(
        kind=inp.get("kind", "other"), title=(inp.get("title") or "Задача")[:255],
        body=inp.get("body", ""), department=dept,
        deal=entity if kind == "deal" else None, lead=entity if kind == "lead" else None,
        status=("open" if autonomous else "proposed"), due_at=due, created_by_agent=True)
    log_activity(kind, entity.id, "AI-агент: задача", "%s — %s" % (t.get_kind_display(), t.title), user, "AI-агент")
    return {"ok": True, "task_id": t.id, "status": t.status}


def _fill_needs(entity, inp, kind, user):
    """Заповнити lead.qualification з діалогу — ТІЛЬКИ порожні поля (не затирати ручний ввід)."""
    q = dict(entity.qualification or {})
    filled = []
    for k, v in (inp or {}).items():
        if v and not q.get(k):
            q[k] = v
            filled.append(k)
    if filled:
        entity.qualification = q
        entity.save(update_fields=["qualification"])
        log_activity(kind, entity.id, "AI-агент: анкета потреби", "заповнено: " + ", ".join(filled), user, "AI-агент")
    return {"ok": True, "filled": filled}


def run_agent(entity, kind, trigger="manual", user=None, model=None):
    cfg = AgentConfig.get()
    if not cfg.enabled:
        return {"skipped": "agent disabled"}
    model = model or cfg.model
    run = AgentRun(kind=kind, trigger=trigger, user=user, model=model)
    setattr(run, kind, entity)
    actions = []
    try:
        resp = _call(build_system(entity, kind), build_context(entity, kind), model)
        for block in resp.get("content", []):
            if block.get("type") != "tool_use":
                continue
            name, inp = block.get("name"), block.get("input", {})
            if name == "move_stage":
                r = _move_stage(entity, kind, inp.get("to_stage"), inp.get("reason", ""), user, cfg.autonomous)
            elif name == "create_task":
                r = _create_task(entity, kind, inp, user, cfg.autonomous)
                if r.get("ok"):
                    run.tasks_created += 1
            elif name == "fill_needs":
                r = _fill_needs(entity, inp, kind, user)
            elif name == "make_offer":
                if kind != "deal":
                    r = {"ok": False, "msg": "make_offer only for deal"}
                elif not cfg.autonomous:
                    r = {"ok": False, "proposed": "offer: " + ", ".join((i or {}).get("name", "") for i in inp.get("items", []))}
                else:
                    from .views import make_offer as _mo
                    r = _mo(entity, inp.get("items"), user=user)
            else:
                r = {"no_action": inp.get("why", "")}
            actions.append({"tool": name, "input": inp, "result": r})
    except Exception as e:
        run.error = str(e)[:500]
    run.output = {"actions": actions}
    run.save()
    return {"actions": actions, "error": run.error, "run_id": run.id}
