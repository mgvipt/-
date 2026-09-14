"""Запуски ЗА КНОПКОЮ Олега (14.09, ai-kb2): попередня перевірка чернеток, контролер закритих чатів, публікація в Юлю.

НІЧОГО за розкладом. Кожен запуск — рядок KnowledgeRun: прогрес, оцінка ДО і фактична вартість ПІСЛЯ, результат.
Працює у фоновому потоці веб-процесу (як «Оновити» в Meta-маркетингу, crm/views.py). Якщо веб перезапустили посеред
роботи — запуск показується «перервано»; повторіть кнопку (уже перевірене/опубліковане не дублюється).
"""
import hashlib
import json
import threading
from datetime import timedelta

from django.db import connection
from django.db.models import Sum
from django.utils import timezone

from . import publisher, reviewer
from .answer import estimate_usd
from .models import KnowledgeItem, KnowledgeReviewLog, KnowledgeRun, KnowledgeSettings

RUN_INLINE = False  # тести: True — потік не бачив би тестової транзакції
STALE_MINUTES = 15
MAX_CONVS = 100
PERIODS = [("yesterday", "Вчора"), ("7d", "Останні 7 днів"), ("last_n", "N останніх закритих чатів")]


def _progress(run_id):
    def prog(done=None, total=None, cost=None, result=None):
        f = {"updated_at": timezone.now()}
        if done is not None:
            f["done"] = done
        if total is not None:
            f["total"] = total
        if cost is not None:
            f["cost_usd"] = round(float(cost), 5)
        if result is not None:
            f["result"] = result
        KnowledgeRun.objects.filter(pk=run_id).update(**f)
    return prog


def spawn(run, fn):
    """fn(run, progress) → dict результату. Помилка → статус «Помилка», зроблене раніше лишається."""
    rid = run.id

    def body():
        try:
            r = KnowledgeRun.objects.get(pk=rid)
            result = fn(r, _progress(rid)) or {}
            f = {"status": "done", "result": result, "finished_at": timezone.now(), "updated_at": timezone.now()}
            if "cost_usd" in result:
                f["cost_usd"] = round(float(result["cost_usd"] or 0), 5)
            KnowledgeRun.objects.filter(pk=rid).update(**f)
        except Exception as e:
            KnowledgeRun.objects.filter(pk=rid).update(status="error", error=str(e)[:1000], finished_at=timezone.now(),
                                                       updated_at=timezone.now())
        finally:
            if not RUN_INLINE:
                try:
                    connection.close()
                except Exception:
                    pass

    if RUN_INLINE:
        body()
    else:
        threading.Thread(target=body, daemon=True).start()


def busy(kind):
    return KnowledgeRun.objects.filter(kind=kind, status="running",
                                       updated_at__gte=timezone.now() - timedelta(minutes=STALE_MINUTES)).exists()


def run_dict(run):
    stale = run.status == "running" and run.updated_at and run.updated_at < timezone.now() - timedelta(minutes=STALE_MINUTES)
    u = run.created_by
    return {
        "id": run.id, "kind": run.kind, "kind_display": run.get_kind_display(),
        "status": "interrupted" if stale else run.status,
        "status_display": "Перервано (перезапуск сервера) — запустіть ще раз" if stale else run.get_status_display(),
        "params": {k: v for k, v in (run.params or {}).items() if k != "conversation_ids"},
        "total": run.total, "done": run.done, "est_cost_usd": run.est_cost_usd, "cost_usd": run.cost_usd,
        "result": run.result or {}, "error": run.error, "backup_count": len(run.backup or []),
        "created_by_name": ((u.get_full_name() or u.username) if u else ""),
        "created_at": run.created_at, "finished_at": run.finished_at,
    }


# ───────────────────────── контролер закритих чатів (лише за кнопкою) ─────────────────────────

def _conv_day(conv):
    return timezone.localtime(conv.last_message_at).date() if conv.last_message_at else timezone.localdate()


def pick_conversations(period, n=20):
    """Закриті чати з обох сторін розмови, які контролер ще не перевіряв."""
    from apps.inbox.models import Conversation
    today = timezone.localdate()
    qs = Conversation.objects.filter(status="closed").exclude(last_message_at=None)
    if period == "yesterday":
        qs = qs.filter(last_message_at__date=today - timedelta(days=1))
    elif period == "7d":
        qs = qs.filter(last_message_at__date__gte=today - timedelta(days=7), last_message_at__date__lt=today)
    try:
        n = int(n or 20)
    except (TypeError, ValueError):
        n = 20
    limit = max(1, min(n, MAX_CONVS)) if period == "last_n" else MAX_CONVS
    done = set(KnowledgeReviewLog.objects.values_list("conversation_id", "day"))
    out, skipped = [], 0
    for conv in qs.order_by("-last_message_at")[:limit * 5]:
        if (conv.id, _conv_day(conv)) in done:
            skipped += 1
            continue
        dirs = set(conv.messages.filter(internal=False).exclude(text="").values_list("direction", flat=True)[:50])
        if {"in", "out"} <= dirs:
            out.append(conv)
            if len(out) >= limit:
                break
    return out, skipped


def estimate_controller(period, n=20):
    convs, skipped = pick_conversations(period, n)
    model = KnowledgeSettings.get().reviewer_model
    chars = sum(len(reviewer.dialog_text(reviewer.dialog(c))[-9000:]) + 6000 for c in convs)
    return {"period": period, "n": n, "count": len(convs), "skipped_already_checked": skipped,
            "conversation_ids": [c.id for c in convs], "model": model, "max": MAX_CONVS,
            "est_usd": round(estimate_usd(model, chars, 600 * len(convs)), 3) if convs else 0.0}


def _cost_since(run):
    try:
        from apps.crm.models import AiUsage
        v = AiUsage.objects.filter(source=reviewer.SOURCE_LABEL, created_at__gte=run.created_at).aggregate(s=Sum("cost_usd"))["s"]
        return round(float(v or 0), 5)
    except Exception:
        return 0.0


def run_controller(run, progress):
    from apps.inbox.models import Conversation
    ids = list(run.params.get("conversation_ids") or [])
    model = run.params.get("model") or KnowledgeSettings.get().reviewer_model
    convs = sorted(Conversation.objects.filter(pk__in=ids).select_related("channel", "contact"), key=lambda c: ids.index(c.id))
    progress(done=0, total=len(convs))
    rows, lint_by_problem, errors = [], {}, []
    for k, conv in enumerate(convs, 1):
        day = _conv_day(conv)
        msgs = reviewer.dialog(conv)
        lint = reviewer.lint_dialog(msgs)
        for f in lint:
            f["conversation_id"] = conv.id
            lint_by_problem.setdefault(f["problem"], []).append(f)
        row = {"conversation_id": conv.id, "link": reviewer.conv_link(conv.id),
               "title": str(conv.contact or conv.title or "")[:80], "channel": conv.channel.name if conv.channel_id else "",
               "lint": [f["problem"] for f in lint], "findings": [], "items": [], "error": ""}
        log, created = KnowledgeReviewLog.objects.get_or_create(
            conversation_id=conv.id, day=day, defaults={"model": model, "lint_findings": len(lint)})
        if not created:
            row["error"] = "уже перевірено раніше — не оплачуємо вдруге"
        else:
            try:
                findings, _n = reviewer.ai_review(conv, msgs, model)
                row["findings"] = [{"type": str(f.get("type") or ""), "problem": str(f.get("problem") or "")[:300],
                                    "quote": str(f.get("quote") or "")[:200]} for f in findings]
                log.ai_findings = len(findings)
                log.items_created = reviewer.create_suggestions(conv, findings, day)
                log.save()
                row["items"] = list(KnowledgeItem.objects.filter(
                    source="reviewer", source_ref="review:%d:%s" % (conv.id, day.isoformat())).values_list("id", flat=True))
            except Exception as e:  # не записуємо як перевірений → можна повторити
                log.delete()
                row["error"] = str(e)[:200]
                errors.append("№%d: %s" % (conv.id, str(e)[:120]))
        rows.append(row)
        progress(done=k, cost=_cost_since(run), result={"rows": rows})
    lint_drafts = reviewer.create_lint_summary(timezone.localdate(), lint_by_problem) if lint_by_problem else 0
    return {"rows": rows, "checked": len(convs), "lint_drafts": lint_drafts,
            "drafts_created": sum(len(r["items"]) for r in rows) + lint_drafts, "errors": errors[:20],
            "cost_usd": _cost_since(run)}


# ───────────────────────── публікація в Юлю (ChatPlace) після затвердження ─────────────────────────

def _h(s):
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()[:12]


def fingerprint(ops):
    rows = sorted([o["op"], o["item"].id, o["item"].version, o.get("dataset") or "", _h(o.get("new")), _h(o.get("old"))]
                  for o in ops if o["op"] in ("add", "update"))
    return hashlib.sha1(json.dumps(rows).encode()).hexdigest()[:16]


def publish_preview(bot, remote=None):
    """Різниця «затверджене в CRM» ↔ жива база Юлі в ChatPlace (лише читання ChatPlace)."""
    remote = publisher.fetch_remote(bot) if remote is None else remote
    ops = publisher.plan(bot, remote)
    add = [{"item_id": o["item"].id, "version": o["item"].version, "question": o["question"][:300], "new": o["new"][:800]}
           for o in ops if o["op"] == "add"]
    upd = [{"item_id": o["item"].id, "version": o["item"].version, "question": o["question"][:300],
            "old": (o.get("old") or "")[:800], "new": o["new"][:800], "dataset": o.get("dataset")}
           for o in ops if o["op"] == "update"]
    preview = {"bot": bot, "label": publisher.BOTS[bot]["label"], "remote_count": len(remote), "approved": len(ops),
               "same": sum(1 for o in ops if o["op"] == "same"), "add": add, "update": upd,
               "changes": len(add) + len(upd), "rules_not_published": publisher.rules_count(bot),
               "fingerprint": fingerprint(ops)}
    return preview, remote, ops


def run_publish(run, progress):
    bot = run.params["bot"]
    ops = publisher.plan(bot, run.backup or [])
    if fingerprint(ops) != run.params.get("fingerprint"):
        raise RuntimeError("План змінився між переглядом і записом — нічого не записано. Натисніть «Показати зміни» ще раз.")
    key = publisher.BOTS[bot]["key"]
    changes = [o for o in ops if o["op"] in ("add", "update")]
    same = [o for o in ops if o["op"] == "same"]
    progress(done=0, total=len(changes))
    items, errors, added, updated = [], [], 0, 0
    for k, op in enumerate(changes, 1):
        d = publisher.apply(bot, [op], user=run.created_by)
        ok = not d["errors"]
        it = op["item"]
        if ok:
            it.refresh_from_db(fields=["external_ids"])
            it.external_ids = dict(it.external_ids or {}, **{key + "_v": it.version})
            it.save(update_fields=["external_ids"])
            added += d["add"]
            updated += d["update"]
        else:
            errors.extend(d["errors"])
        items.append({"id": it.id, "version": it.version, "op": op["op"], "ok": ok})
        progress(done=k, result={"items": items, "added": added, "updated": updated, "errors": errors[:30]})
    if same:  # лише привʼязка id до записів CRM; у ChatPlace нічого не пише
        publisher.apply(bot, same, user=run.created_by)
    return {"bot": bot, "label": publisher.BOTS[bot]["label"], "items": items, "added": added, "updated": updated,
            "errors": errors[:30], "backup_run": run.id, "backup_count": len(run.backup or [])}
