"""Вбудований Claude-агент Wallcov-CRM. Автономно рухає лід/сделку по воронці
та створює задачі співробітникам за глобальними правилами (GlobalRule).
Кожна дія — у Історію змін (actor «AI-агент») + аудит AgentRun."""
import json, os, urllib.request
from django.utils import timezone
from datetime import timedelta
from .models import GlobalRule, Task, AgentRun, AgentConfig, log_activity

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
    {"name": "no_action", "description": "Нічого не робити — стадія правильна, дій не треба.",
     "input_schema": {"type": "object", "properties": {"why": {"type": "string"}}, "required": []}},
]

DEPT_BY_KIND = {"warehouse": "Склад", "tinting": "Тонуванн", "manager": "Продаж"}


def _call(system, user_text, model, max_tokens=1200):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY не налаштовано")
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user_text}], "tools": TOOLS,
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def build_system(entity, kind):
    parts = ["Ти AI-РОП компанії Wallcov (декоративні покриття для стін). Працюєш ВСЕРЕДИНІ CRM. "
             "Твоя задача: рухати ліда/сделку по воронці за правилами і створювати задачі співробітникам. "
             "Дій рішуче але точно: рухай стадію тільки коли клієнт реально дозрів. Якщо клієнт замовк — створи задачу-дожим менеджеру. "
             "Рухати можна ТІЛЬКИ вперед і на сусідню стадію (не перестрибуй). Відповідай українською у reason/тексті задач."]
    for gr in GlobalRule.objects.filter(enabled=True).order_by("block", "priority"):
        parts.append("## [%s] %s\n%s" % (gr.get_block_display(), gr.title, gr.body))
    if entity.funnel_id:
        stages = list(entity.funnel.stages.order_by("order").values_list("name", flat=True))
        parts.append("## Стадії воронки (по порядку): " + " → ".join(stages))
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
        # тільки на сусідню — беремо наступну
        target = funnel.stages.filter(order=entity.stage.order + 1).first() or target
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
            else:
                r = {"no_action": inp.get("why", "")}
            actions.append({"tool": name, "input": inp, "result": r})
    except Exception as e:
        run.error = str(e)[:500]
    run.output = {"actions": actions}
    run.save()
    return {"actions": actions, "error": run.error, "run_id": run.id}
