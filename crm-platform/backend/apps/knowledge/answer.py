"""ОДИН рушій відповіді для ІІ, що говорять з клієнтом або радять менеджеру (14.09.2026, ai-kb2).

    answer(agent, messages, include_drafts=False, topic=None) -> {text, used_items, prices, cost, …}

Промпти — ТІ САМІ, що в справжніх агентів (жодної копії правил):
    rop_hint       — COACH_SYSTEM + майстер-правила з inbox/views.py (ai_reply) + coach_prompt.knowledge_block
    compose_assist — fallbacks.compose_style() + fallbacks.compose_extra()
    funnel_agent   — crm/agent.build_system() + інструменти агента (НІЧОГО не виконується — лише показ дій)
    yulia_web      — продавець веб-чату CRM (SELLER_SYSTEM) + reader.context_for + запобіжники (guard)
    yulia_ig / yulia_tiktok — той самий продавець на базі, яку Юля отримає після публікації в ChatPlace

include_drafts=True / topic — ЛИШЕ «Тестовий чат»: у межах цього виклику (thread-local, reader.test_pool)
читач бачить «затверджене + чернетки» або одну тему. Справжні агенти в інших запитах цього не бачать.
Нічого не зберігає як чат і нікому не надсилає. Витрати пишуться в «Витрати ІІ» (crm_aiusage).
"""
import json
import os
import re
import urllib.request
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from . import catalog, reader
from .models import KnowledgeItem

TEST_AGENTS = [
    ("yulia_ig", "Юля Instagram"),
    ("yulia_tiktok", "Юля TikTok"),
    ("yulia_web", "Сайт (веб-чат)"),
    ("compose_assist", "Помічник ✨"),
    ("rop_hint", "Підказка AI-РОП"),
    ("funnel_agent", "Агент воронки"),
]
TEST_AGENT_CODES = [c for c, _ in TEST_AGENTS]
SELLER_AGENTS = ("yulia_ig", "yulia_tiktok", "yulia_web")
HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-6"
MODELS = [HAIKU, SONNET]
API = "https://api.anthropic.com/v1/messages"
SOURCE_TEST = "Тестовий чат бази знань"

# Ціни $/1М токенів для ОЦІНОК: більше з двох — таблиця CRM (crm/ai.PRICING) або прайс Anthropic,
# щоб оцінка не була заниженою (у таблиці CRM Haiku 4.5 записаний як 0.80/4.0, прайс — 1/5).
_LIST_PRICE = {HAIKU: (1.0, 5.0, 0.10, 1.25), SONNET: (3.0, 15.0, 0.30, 3.75)}

HANDOFF_TEXT = ("Дякую! Я передала питання менеджеру Wallcov — він підключиться до цього чату. "
                "Залиште номер, щоб ми не втратили зв’язок.")

CHANNEL = {"yulia_ig": "Instagram Direct", "yulia_tiktok": "TikTok", "yulia_web": "чаті на сайті Wallcov"}

SELLER_SYSTEM = (
    "Ти — Юля, консультантка Wallcov (декоративні покриття і фарби для стін) у %s. "
    "Пишеш тепло, коротко (2–5 речень), на «Ви», мовою клієнта (українська або російська), доречно 1 емодзі.\n"
    "ЗАЛІЗНІ ПРАВИЛА:\n"
    "1. Факти — ЛИШЕ з блоку «БАЗА ЗНАНЬ WALLCOV» у запиті. Чого там немає — не вигадуй: чесно скажи, що уточниш, і передай менеджеру.\n"
    "2. Ціни та будь-які суми в грн — ЛИШЕ з бази знань або блоку «Ціни з каталогу CRM». Жодних «приблизно», «від ~». "
    "Не рахуй підсумкову суму за обʼєм — це робить менеджер.\n"
    "3. Знижки, акції, промокоди — не пропонуй і не обіцяй, якщо в базі немає затвердженого правила про знижки.\n"
    "4. Клієнт хоче оформити замовлення, оплатити, отримати реквізити чи посилання на оплату, просить дзвінок — передай менеджеру.\n"
    "5. Інструмент у тест-набір НЕ входить. Захисне покриття не навʼязуй. Не пояснюй внутрішню механіку компанії.\n"
    "6. Не вигадуй товарів, тест-наборів, відео. Матеріалу немає в базі — чесно передай менеджеру.\n"
    "7. Закінчуй ОДНИМ відкритим питанням, що рухає до вибору (кімната, площа, ефект), — не «так/ні».\n"
    'Поверни СТРОГО JSON: {"reply": "текст клієнту", "handoff": true або false, "reason": "чому передаєш менеджеру"}. '
    "handoff=true — якщо не впевнена, потрібних фактів у базі немає або клієнт хоче замовити/оплатити."
)

_W = r"(?<![а-яіїєґa-z])"
PAY_RX = re.compile(
    r"оформ\w*\s+(замовлен|заказ)|хочу\s+(замовити|купити|оплатити|заказать|купить|оплатить)|"
    r"як\s+(оплатити|замовити)|как\s+(оплатить|заказать)|реквізит|реквизит|рахун\w*\s+на\s+оплат|"
    r"посиланн\w*\s+на\s+оплат|ссылк\w*\s+на\s+оплат|передзвон|перезвон|зателефонуйте|позвоните|"
    r"оформлюйте|оформляйте|" + _W + r"беру\b|" + _W + r"куплю\b|готов\w*\s+(оплатити|замовити|оплатить|заказать)",
    re.I)
_NUM = r"\d+(?:[   ]\d{3})*(?:[.,]\d+)?"
MONEY_RX = re.compile(r"(" + _NUM + r")\s*(?:грн|₴|uah|гривень|гривні|гривен|гривня)", re.I)
PCT_RX = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
DISCOUNT_RX = re.compile(r"знижк|скидк|промокод|" + _W + r"акці|" + _W + r"акци", re.I)


# ───────────────────────── виклик Claude (той самий ключ і журнал витрат, що crm/ai.py) ─────────────────────────

def call_claude(system, user_text, model, max_tokens=700, source=SOURCE_TEST, tools=None, cache=True, timeout=45):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY не налаштовано на сервері")
    payload = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": user_text}]}
    if system:
        sb = {"type": "text", "text": system}
        if cache:
            sb["cache_control"] = {"type": "ephemeral"}
        payload["system"] = [sb]
    if tools:
        payload["tools"] = tools
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    if cache:
        headers["anthropic-beta"] = "prompt-caching-2024-07-31"
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — api.anthropic.com
        resp = json.load(r)
    try:
        from apps.crm.ai import _log_usage
        _log_usage(source, model, resp.get("usage") or {})
    except Exception:
        pass
    return resp


def price_of(model):
    try:
        from apps.crm.ai import PRICING
        a = PRICING.get(model, (3.0, 15.0, 0.30, 3.75))
    except Exception:
        a = (3.0, 15.0, 0.30, 3.75)
    b = _LIST_PRICE.get(model, a)
    return tuple(max(x, y) for x, y in zip(a, b))


def cost_usd(model, usage):
    usage = usage or {}
    pin, pout, pcr, pcw = price_of(model)
    it = int(usage.get("input_tokens") or 0)
    ot = int(usage.get("output_tokens") or 0)
    cr = int(usage.get("cache_read_input_tokens") or 0)
    cw = int(usage.get("cache_creation_input_tokens") or 0)
    return round((it * pin + ot * pout + cr * pcr + cw * pcw) / 1_000_000.0, 5)


def estimate_usd(model, chars_in, out_tokens=400):
    """Оцінка ДО запуску: ~2,5 символу кирилиці на токен (з запасом)."""
    pin, pout, _cr, _cw = price_of(model)
    return round((chars_in / 2.5 * pin + out_tokens * pout) / 1_000_000.0, 5)


def resp_text(resp):
    return "".join(b.get("text", "") for b in (resp or {}).get("content") or [] if b.get("type") == "text").strip()


def parse_json(text):
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if m:
        try:
            v = json.loads(m.group(0))
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}


# ───────────────────────── набір записів для тесту (затверджене / + чернетки / одна тема) ─────────────────────────

def test_items(include_drafts=False, topic=None):
    """None → без підміни (читач бере справжнє «Затверджено»)."""
    if not include_drafts and not topic:
        return None
    statuses = ["approved", "draft"] if include_drafts else ["approved"]
    items = list(KnowledgeItem.objects.filter(status__in=statuses).prefetch_related("products").order_by("priority", "id"))
    if include_drafts:  # чернетка-правка замінює свій затверджений оригінал
        replaced = {i.replaces_id for i in items if i.status == "draft" and i.replaces_id}
        items = [i for i in items if i.id not in replaced]
    if topic:  # одна тема + загальні заборони («Тон і заборони»)
        items = [i for i in items if i.topic == topic or (i.kind == "rule" and i.topic == "tone")]
    return items


def _norm_messages(messages):
    out = []
    for m in (messages or [])[-40:]:
        if not isinstance(m, dict):
            continue
        text = str(m.get("text") or "").strip()[:1500]
        if text:
            out.append({"role": "client" if m.get("role") in ("client", "user", "in") else "agent", "text": text})
    return out


def _dialog(msgs, client="Клієнт: ", ours="Юля: "):
    return "\n".join((client if m["role"] == "client" else ours) + m["text"] for m in msgs[-30:])


def _query(msgs):
    last = msgs[-1]["text"] if msgs else ""
    return (last + "\n" + _dialog(msgs)[-1500:]).strip() or None


# ───────────────────────── промпти агентів ─────────────────────────

def rop_master_rules():
    """Майстер-правила підказки AI-РОП живуть усередині inbox/views.py (ai_reply) — беремо ТОЙ САМИЙ текст
    звідти, щоб тест не розходився з реальною підказкою. Не знайшли → порожньо (тест це перевіряє)."""
    try:
        from apps.inbox.views import ConversationViewSet
        fn = ConversationViewSet.ai_reply
        fn = getattr(fn, "__wrapped__", fn)
        for c in fn.__code__.co_consts:
            if isinstance(c, str) and "МАЙСТЕР-ПРАВИЛА" in c:
                return c
    except Exception:
        pass
    return ""


def _spec_seller(agent, msgs, model):
    q = _query(msgs)
    items = reader.select(agent, q, 15)
    kb = reader.context_for(agent, q, limit=15, max_chars=6000)
    user = ("БАЗА ЗНАНЬ WALLCOV (затверджено Олегом):\n%s\n\nДІАЛОГ:\n%s\n\nОстаннє повідомлення клієнта: «%s». "
            "Дай відповідь і поверни JSON." % (kb or "(порожньо)", _dialog(msgs), msgs[-1]["text"]))
    allowed = kb + "\n" + "\n".join(m["text"] for m in msgs if m["role"] == "client")
    spec = {"system": SELLER_SYSTEM % CHANNEL[agent], "user": user, "model": model or HAIKU, "max_tokens": 600,
            "mode": "seller", "cache": False, "allowed": allowed}
    if not items:
        spec["empty"] = "для цього агента немає %s записів — ІІ не викликається, $0" % (
            "жодних" if reader.approved_for(agent) == [] else "підхожих")
    return spec


def _spec_rop(agent, msgs, model):
    from apps.crm.coach_prompt import COACH_SYSTEM, knowledge_block
    dialog = _dialog(msgs, "Клієнт: ", "Менеджер/AI: ")
    last = msgs[-1]["text"]
    prompt = (
        "Клієнт: %s\nКанал: %s\n\nПереписка:\n%s\n\n"
        "❗ ОСТАННЄ ПОВІДОМЛЕННЯ КЛІЄНТА%s: «%s»\n"
        "Твоя відповідь МУСИТЬ реагувати САМЕ на нього. Якщо клієнт сказав «подумаю»/«дякую»/замовк — "
        "це НЕ привід повторювати прорахунок: потрібен мʼякий дожим або відпрацювання заперечення.%s\n\n"
        "Поверни СТРОГО JSON без пояснень: "
        '{"context": "1 коротке речення-підсумок", '
        '"points": ["3-6 коротких тез: на якому етапі клієнт, що хоче, площа/матеріал/бюджет якщо згадані, '
        'заперечення, ПОМИЛКИ наших відповідей якщо є, наступний крок"], '
        '"suggestion": "готова відповідь клієнту ТІЄЮ Ж мовою, що й він — по суті, з наступним кроком до продажу"}'
    ) % ("тестовий клієнт", "Тестовий чат (AI ЦЕНТР)", dialog or "(переписки ще немає)", "", last, "")
    prompt += knowledge_block((last + "\n" + dialog[-1500:]).strip() or None)
    from .fallbacks import ROP_CHUNKS
    return {"system": COACH_SYSTEM + rop_master_rules(), "user": prompt, "model": model or SONNET, "max_tokens": 1200,
            "mode": "rop", "cache": True, "chunks": ROP_CHUNKS}


def _spec_compose(agent, msgs, model):
    from .fallbacks import COMPOSE_CHUNKS, compose_extra, compose_style
    dialog = _dialog(msgs, "Клієнт: ", "Менеджер: ")
    prompt = (
        "ЗАВДАННЯ (тестовий чат AI ЦЕНТРУ): менеджер ще не написав чернетку. Напиши відповідь клієнту на його останнє "
        "повідомлення так, як написав би топовий РОП Wallcov — грамотно, тепло, живо, мовою клієнта. "
        "Факти й ціни — лише з бази знань у системному тексті та довідки нижче; нічого не вигадуй.\n\n"
        "Переписка з клієнтом (для тону, мови та контексту):\n" + (dialog or "(переписки ще немає)") + "\n\n"
        'Поверни СТРОГО JSON без пояснень: {"text": "готове повідомлення клієнту тією потрібною мовою"}')
    prompt += compose_extra((msgs[-1]["text"] + "\n" + dialog[-1500:]).strip())
    return {"system": compose_style(), "user": prompt, "model": model or SONNET, "max_tokens": 1000,
            "mode": "compose", "cache": True, "chunks": COMPOSE_CHUNKS}


def _spec_funnel(agent, msgs, model):
    from apps.crm.agent import TOOLS, build_system
    from apps.crm.models import AgentConfig
    system = build_system(SimpleNamespace(funnel_id=None), "lead")
    ctx = {"тип": "lead", "поточна_стадія": None, "сума": "", "днів_від_останнього_повідомлення_клієнта": 0,
           "діалог": _dialog(msgs, "Клієнт: ", "Ми: ")[-4500:]}
    user = "Контекст картки:\n" + json.dumps(ctx, ensure_ascii=False) + "\n\nПроаналізуй і виклич потрібні інструменти."
    tools = [dict(t) for t in TOOLS if t.get("name") != "create_task"]  # як у crm/agent._call
    return {"system": system, "user": user, "model": model or AgentConfig.get().model or HAIKU, "max_tokens": 1200,
            "mode": "funnel", "cache": True, "tools": tools}


SPECS = {"yulia_ig": _spec_seller, "yulia_tiktok": _spec_seller, "yulia_web": _spec_seller,
         "rop_hint": _spec_rop, "compose_assist": _spec_compose, "funnel_agent": _spec_funnel}


# ───────────────────────── що саме потрапило в промпт ─────────────────────────

def _ws(s):
    return re.sub(r"\s+", " ", s or "")


def used_items(items, haystack_ws):
    """Записи, текст яких реально потрапив у промпт (перші 80 символів після підстановки цін)."""
    if not items:
        return []
    prods = catalog.load_products(catalog.placeholder_ids([i.text for i in items] + [i.title for i in items]))
    out = []
    for i in items:
        key = _ws(catalog.render(i.text or "", prods)).strip()[:80]
        if len(key) < 12:
            key = _ws(catalog.render(i.title or "", prods)).strip()[:80]
        if len(key) >= 6 and key in haystack_ws:
            out.append(i)
    return out


def injected_prices(used, haystack_raw, haystack_ws, chunks=None):
    lines, seen = [], set()
    pos = haystack_raw.find("Ціни з каталогу CRM")
    while pos >= 0:
        for ln in haystack_raw[pos:].splitlines()[1:40]:
            ln = ln.strip()
            if not ln.startswith("•"):
                break
            if ln not in seen:
                seen.add(ln)
                lines.append(ln)
        pos = haystack_raw.find("Ціни з каталогу CRM", pos + 10)
    texts = [i.text for i in used] + [i.title for i in used]
    for _t, chunk in (chunks or []):
        head = _ws(catalog.render(chunk)).strip()[:60]
        if head and head in haystack_ws:
            texts.append(chunk)
    ids = catalog.placeholder_ids(texts)
    prods = catalog.load_products(ids)
    for pid in sorted(ids):
        p = prods.get(pid)
        name = re.sub(r"\s+", " ", p.name).strip()[:90] if p else "товар не знайдено"
        ln = "#%d %s — %s" % (pid, name, catalog._one("price", pid, None, prods))
        if ln not in seen:
            seen.add(ln)
            lines.append(ln)
    return lines[:60]


# ───────────────────────── запобіжники продавця (веб-чат і тест Юлі) ─────────────────────────

def _num(s):
    s = re.sub(r"[   ]", "", str(s or "")).replace(",", ".")
    try:
        d = Decimal(s).normalize()
    except InvalidOperation:
        return s
    return format(d, "f")


def numbers_in(text):
    out = set()
    for m in re.finditer(_NUM, text or ""):
        out.add(_num(m.group(0)))
    for m in re.finditer(r"\d+(?:[.,]\d+)?", text or ""):
        out.add(_num(m.group(0)))
    return out


def guard(reply, allowed, used, client_last):
    """Перелік причин передати менеджеру (порожньо → відповідь можна надсилати)."""
    problems = []
    if PAY_RX.search(client_last or ""):
        problems.append("клієнт хоче замовити / оплатити — веде менеджер")
    nums = numbers_in(allowed)
    for m in MONEY_RX.finditer(reply or ""):
        if _num(m.group(1)) not in nums:
            problems.append("сума «%s» не з каталогу CRM і не з бази" % m.group(0).strip())
    for m in PCT_RX.finditer(reply or ""):
        if _num(m.group(1)) not in nums:
            problems.append("відсоток «%s%%» не з бази" % m.group(1))
    if DISCOUNT_RX.search(reply or "") and not any(u.topic == "discounts" for u in used):
        problems.append("про знижки — лише за затвердженим правилом (його немає)")
    return problems


# ───────────────────────── обробка відповіді ─────────────────────────

def _finish_seller(res, resp, msgs, spec, used):
    txt = resp_text(resp)
    data = parse_json(txt)
    reply = str(data.get("reply") or ("" if data else txt)).strip()
    problems = guard(reply, spec["allowed"], used, msgs[-1]["text"])
    if data.get("handoff"):
        reason = str(data.get("reason") or "").strip()
        problems.insert(0, "ІІ сам вирішив передати менеджеру" + (": " + reason if reason else ""))
    if not reply:
        problems.append("порожня відповідь")
    if problems:
        res.update(text=HANDOFF_TEXT, handoff=True, handoff_reason="; ".join(problems)[:600], draft_reply=reply[:2000])
    else:
        res["text"] = reply[:1200]


def _finish_rop(res, resp, msgs, spec, used):
    txt = resp_text(resp)
    data = parse_json(txt)
    res["text"] = str(data.get("suggestion") or txt).strip()
    res["extra"] = {"context": str(data.get("context") or ""),
                    "points": [str(p) for p in (data.get("points") or []) if p][:8]}


def _finish_compose(res, resp, msgs, spec, used):
    txt = resp_text(resp)
    data = parse_json(txt)
    res["text"] = str(data.get("text") or data.get("suggestion") or txt).strip()


STAGE_BLOCKED = re.compile(r"оплат\w*\s+(отрим|получ|отрым)|домовил", re.I)


def _finish_funnel(res, resp, msgs, spec, used):
    actions = []
    for b in (resp or {}).get("content") or []:
        if b.get("type") != "tool_use":
            continue
        name, inp = b.get("name"), b.get("input") or {}
        if name == "move_stage":
            to = str(inp.get("to_stage") or "")
            line = "➡️ Перемістив би на стадію «%s» — %s" % (to, inp.get("reason") or "")
            if STAGE_BLOCKED.search(to):
                line += " (у CRM це заблоковано: таку стадію ставить лише реальна оплата / відправка оплати)"
            actions.append(line)
        elif name == "fill_needs":
            actions.append("📝 Заповнив би анкету: " + ", ".join("%s: %s" % (k, v) for k, v in inp.items() if v))
        elif name == "make_offer":
            actions.append("🧾 Запропонував би тест-набір (LiqPay): " + ", ".join(
                str((i or {}).get("name") or "") for i in inp.get("items") or []))
        elif name == "no_action":
            actions.append("— Нічого не робив би: " + str(inp.get("why") or ""))
        else:
            actions.append("%s: %s" % (name, json.dumps(inp, ensure_ascii=False)[:200]))
    res["actions"] = actions
    txt = resp_text(resp)
    res["text"] = "\n".join(actions) or txt or "Агент нічого не зробив би."


FINISH = {"seller": _finish_seller, "rop": _finish_rop, "compose": _finish_compose, "funnel": _finish_funnel}


def answer(agent, messages, include_drafts=False, topic=None, *, model=None, estimate_only=False,
           source=SOURCE_TEST, timeout=45):
    """Відповідь агента на діалог. messages = [{"role": "client"|"agent", "text": …}], останнє — клієнта.
    estimate_only=True — лише зібрати промпт і порахувати оцінку ($0, ІІ не викликається)."""
    if agent not in SPECS:
        raise ValueError("Невідомий агент: %s" % agent)
    msgs = _norm_messages(messages)
    if not msgs or msgs[-1]["role"] != "client":
        if not estimate_only:
            raise ValueError("Останнім має бути повідомлення клієнта")
        msgs = msgs + [{"role": "client", "text": "Скільки коштує і як оплатити?"}]
    pool = test_items(include_drafts, topic)
    with (reader.test_pool(pool) if pool is not None else nullcontext()):
        spec = SPECS[agent](agent, msgs, model)
        agent_items = reader.approved_for(agent)
        raw = spec["system"] + "\n" + spec["user"]
        hay = _ws(raw)
        used = used_items(agent_items, hay)
        prices = injected_prices(used, raw, hay, spec.get("chunks"))
    chars = len(spec["system"]) + len(spec["user"])
    res = {
        "agent": agent, "include_drafts": bool(include_drafts), "topic": topic or "", "text": "",
        "handoff": False, "handoff_reason": "", "draft_reply": "", "extra": {}, "actions": [],
        "used_items": [{"id": i.id, "title": i.title[:160], "status": i.status, "topic": i.topic, "kind": i.kind}
                       for i in used],
        "prices": prices,
        "estimate": {"usd": estimate_usd(spec["model"], chars, spec["max_tokens"] // 2), "model": spec["model"],
                     "prompt_chars": chars},
        "cost": {"usd": 0.0, "model": spec["model"], "in_tok": 0, "out_tok": 0, "cache_read": 0},
    }
    if spec.get("empty"):
        res.update(text=HANDOFF_TEXT, handoff=True, handoff_reason=spec["empty"])
        return res
    if estimate_only:
        return res
    resp = call_claude(spec["system"], spec["user"], spec["model"], max_tokens=spec["max_tokens"], source=source,
                       tools=spec.get("tools"), cache=spec["cache"], timeout=timeout)
    usage = (resp or {}).get("usage") or {}
    res["cost"] = {"usd": cost_usd(spec["model"], usage), "model": spec["model"],
                   "in_tok": int(usage.get("input_tokens") or 0), "out_tok": int(usage.get("output_tokens") or 0),
                   "cache_read": int(usage.get("cache_read_input_tokens") or 0)}
    FINISH[spec["mode"]](res, resp, msgs, spec, used)
    return res
