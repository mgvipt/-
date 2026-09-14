"""Публікація затвердженої бази в ChatPlace (Юля IG / TikTok) — в один бік: CRM → ChatPlace.

Фаза 1 (зараз): лише записи бази знань ChatPlace (Q&A) — тип «Питання-відповідь», «Факт», «Шаблон»,
статус «Затверджено», у «Для яких агентів» є yulia_ig / yulia_tiktok. Глобальні правила ChatPlace
(повна заміна 24 тис. символів) НЕ чіпаємо — це фаза 2 з окремим бекапом і тестом.
Нічого не видаляємо. Відповідь оновлюємо окремим викликом без «правила» (відома особливість ChatPlace:
оновлення відповіді разом із правилом стирає правило).
"""
import re

from .catalog import render
from .models import log_version
from .reader import approved_for

# ті самі id, що в inbox/yulia_toggle.py
BOTS = {
    "ig": {"agent": "yulia_ig", "bot_id": "647e28e9-73fd-4f06-81cc-5970409a7381", "key": "chatplace_ig",
           "label": "Юля Instagram"},
    "tt": {"agent": "yulia_tiktok", "bot_id": "4aab5db8-4efa-46aa-a0bf-56fc20610b35", "key": "chatplace_tt",
           "label": "Юля TikTok"},
}
PUBLISH_KINDS = ("qa", "fact", "template")


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _rows(res):
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        for k in ("items", "data", "results", "entries", "dataset", "knowledgeBase", "list"):
            v = res.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                inner = _rows(v)
                if inner:
                    return inner
    return []


def _extract_id(res):
    if isinstance(res, dict):
        for k in ("id", "datasetId", "_id"):
            if res.get(k):
                return str(res[k])
        for v in res.values():
            if isinstance(v, dict):
                got = _extract_id(v)
                if got:
                    return got
    return ""


def default_mcp():
    from apps.inbox.chatplace import _mcp
    return _mcp


def desired(bot):
    b = BOTS[bot]
    out = []
    for it in approved_for(b["agent"]):
        if it.kind in PUBLISH_KINDS:
            out.append((it, render(it.title).strip(), render(it.text).strip()))
    return out


def rules_count(bot):
    return sum(1 for it in approved_for(BOTS[bot]["agent"]) if it.kind == "rule")


def fetch_remote(bot, mcp=None, page=200, max_pages=40):
    mcp = mcp or default_mcp()
    out, offset = [], 0
    for _ in range(max_pages):
        rows = _rows(mcp("ai_agent_knowledge_base_list", {"botId": BOTS[bot]["bot_id"], "limit": page, "offset": offset}))
        for r in rows:
            out.append({"id": str(r.get("id") or r.get("datasetId") or ""), "question": r.get("question") or "",
                        "answer": r.get("answer") or ""})
        if len(rows) < page:
            break
        offset += page
    return out


def fetch_crm_copy():
    """Знімок IG-бази, що лежить у CRM (стара база AI ЦЕНТРУ) — щоб показати різницю без звернення до ChatPlace."""
    from apps.crm.models import KbEntry
    return [{"id": e.ext_id, "question": e.question, "answer": e.answer}
            for e in KbEntry.objects.exclude(ext_id="").only("ext_id", "question", "answer")]


def plan(bot, remote):
    key = BOTS[bot]["key"]
    by_id = {r["id"]: r for r in remote if r.get("id")}
    by_q = {}
    for r in remote:
        by_q.setdefault(_norm(r["question"]), r)
    ops = []
    for it, q, a in desired(bot):
        rid = (it.external_ids or {}).get(key)
        r = by_id.get(rid) if rid else None
        if r is None:
            r = by_q.get(_norm(q))
        if r is None:
            ops.append({"op": "add", "item": it, "question": q, "new": a})
        elif _norm(r["answer"]) == _norm(a):
            ops.append({"op": "same", "item": it, "dataset": r["id"], "question": q})
        else:
            ops.append({"op": "update", "item": it, "dataset": r["id"], "question": q, "old": r["answer"], "new": a})
    return ops


def apply(bot, ops, mcp=None, user=None):
    mcp = mcp or default_mcp()
    b = BOTS[bot]
    done = {"add": 0, "update": 0, "errors": []}
    for op in ops:
        it = op["item"]
        try:
            if op["op"] == "update":
                mcp("ai_agent_knowledge_base_update", {"botId": b["bot_id"], "datasetId": op["dataset"], "answer": op["new"]})
                new_id = op["dataset"]
            elif op["op"] == "add":
                new_id = _extract_id(mcp("ai_agent_knowledge_base_add",
                                         {"botId": b["bot_id"], "question": op["question"], "answer": op["new"]}))
            else:
                if (it.external_ids or {}).get(b["key"]) != op["dataset"]:
                    it.external_ids = dict(it.external_ids or {}, **{b["key"]: op["dataset"]})
                    it.save(update_fields=["external_ids"])
                continue
            if new_id:
                it.external_ids = dict(it.external_ids or {}, **{b["key"]: new_id})
                it.save(update_fields=["external_ids"])
            log_version(it, "publish", user, "%s: %s" % (b["label"], "оновлено" if op["op"] == "update" else "додано"))
            done[op["op"]] += 1
        except Exception as e:
            done["errors"].append("#%d: %s" % (it.id, str(e)[:160]))
    return done
