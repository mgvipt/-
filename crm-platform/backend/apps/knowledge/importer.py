"""Перенесення старої бази AI ЦЕНТРУ (crm_kbentry, 894 записи з ChatPlace IG) у єдину базу знань.

Усе заходить ЧЕРНЕТКАМИ, крім 6 записів про доставку, які 13.09 уже виправлені за памʼяткою
(коміт 09f21c6a) — вони заходять затвердженими. Записи з відомими помилками аудиту — тільки
чернеткою з позначкою «⚠️ Перевірити». Повторний запуск нічого не дублює (ключ source_ref).
Плюс 12 правил із коду CRM (рішення Олега 14.09) — чернетками, щоб Олег затвердив одним кліком.
"""
from django.db import transaction
from django.utils import timezone

from .models import KnowledgeItem, KnowledgeVersion
from .topics import flags_for, guess_topic

# Записи старої бази, виправлені 13.09 за памʼяткою доставки (перевірено: тексти відповідають памʼятці)
APPROVED_ON_13_09 = [227, 488, 590, 653, 666, 717]
APPROVAL_NOTE_13_09 = "Памʼятка доставки 13.09 (виправлено й перевірено 13.09, коміт 09f21c6a)"

ALL_AGENTS = ["yulia_ig", "yulia_tiktok", "funnel_agent", "rop_hint", "compose_assist", "analyst"]
CLIENT_AGENTS = ["yulia_ig", "yulia_tiktok", "rop_hint", "compose_assist", "analyst"]

_TS = [  # тест-набори: без дощечки без тонування / з дощечкою / з тонуванням / з дощечкою і тонуванням
    ("Sirena Silk (мокрий шовк)", (1707, 1705, 1706, 1704)),
    ("Sirena Silk Bianco", (1728, 1727, 1703, 1702)),
    ("Mermi Silk", (1715, 1713, 1714, 1712)),
    ("Mermi Silk МАТ", (1711, 1709, 1710, 1708)),
    ("Galateya", (1719, 1717, 1718, 1716)),
    ("Celestia (ефект оксамиту)", (1730, 1729, 1725, 1724)),
    ("Celestial Mat", (1723, 1721, 1722, 1720)),
    ("Eleganti", (1665, 1663, 1664, 1662)),
    ("Вельвет Velvet Luna", (1689, 1687, 1688, 1686)),
    ("Вельвет Velvet Luna Bianco", (1960, 1958, 1959, 1957)),
    ("Velvet Lux — перламутровий марморин", (1661, 1659, 1660, 1658)),
    ("Pattera Fine — матовий марморин", (1675, 1956, 1677, 1676)),
    ("Pattera Micro — матовий марморин", (1955, 1674, 1953, 1954)),
    ("SLATE — арт-бетон зі слюдою", (1701, 1699, 1700, 1698)),
    ("Арт-бетон в один шар (Pattera Fine)", (1693, 1691, 1692, 1690)),
    ("Арт-бетон в два шари (Pattera Fine)", (1697, 1695, 1696, 1694)),
    ("Pattera Micro — матове гротто", (1679, 1726, 1680, 1678)),
    ("Velvet Lux — гротто на кварці", (1673, 1671, 1672, 1670)),
    ("Velvet Lux + Mermi Silk — гротто на шовку", (1669, 1667, 1668, 1666)),
    ("Мармарин полірований (Патера + венеціанка)", (1684, 1682, 1683, 1681)),
]
TESTSET_PRICES = (
    "Ціни тест-наборів (підставляються з каталогу CRM): без дощечки / з дощечкою 40×40 / з тонуванням / з дощечкою і тонуванням.\n"
    + "\n".join("• %s: %s" % (n, " / ".join("{price:%d}" % i for i in ids)) for n, ids in _TS)
)

CODE_SEEDS = [
    dict(key="payment_methods", kind="rule", topic="payment", audience=ALL_AGENTS, priority=10,
         title="Способи оплати",
         text="1) За замовчуванням — LiqPay онлайн (картка / Apple Pay / Google Pay / Приват24), кнопка «Прийняти оплату → LiqPay». "
              "2) Клієнт не хоче онлайн — реквізити рахунку ФОП (IBAN, шаблон «Реквізити» у CRM), призначення «Оплата замовлення №…». "
              "3) На картку фізособи оплату НЕ приймаємо — лише рахунок ФОП (для фіскального чека). Ніколи не писати «номер карти»."),
    dict(key="cod_prepay", kind="rule", topic="payment", audience=ALL_AGENTS, priority=10,
         title="Накладений платіж і передоплата (рішення Олега 14.09)",
         text="Накладений платіж НП — тільки для НЕТОНОВАНИХ матеріалів і тільки якщо клієнт сам спитав. Передоплата за сумою замовлення: "
              "до 5 000 грн — 20%; 5 000–15 000 грн — 15%; понад 15 000 грн — 10%; але не менше за доставку туди й назад. "
              "Решта — при отриманні на Новій Пошті. ТОНОВАНИЙ матеріал: або тонер у шприцах — клієнт тонує сам (попередити: такий колір "
              "ми не архівуємо, точного повтору не буде), або тонуємо у нас з передоплатою 50% — вона не повертається, бо колір індивідуальний. "
              "Тест-набори — 100% передоплата."),
    dict(key="installments", kind="rule", topic="payment", audience=CLIENT_AGENTS, priority=20,
         title="Розстрочка",
         text="Оплата частинами ПриватБанку (через LiqPay, до 9 міс) — лише коли клієнт сам спитав. Посилання з опцією «Оплата частинами» надсилає менеджер."),
    dict(key="testsets", kind="rule", topic="test_sets", audience=ALL_AGENTS, priority=10,
         title="Тест-набори: склад і оплата",
         text="Тест-набір — 100% передоплата. 4 варіанти: без дощечки / з дощечкою 40×40 см, без тонування / з тонуванням. "
              "У наборі: декоративний матеріал, ґрунт-підкладка, тара, відео-інструкція (+ дощечка 40×40 у варіантах «з дощечкою»). "
              "Інструмент (пензель, кельма, макловиця, валик) НЕ входить — купується окремо. Тест-наборів по 1 кг не буває; фарби тест-наборів не мають."),
    dict(key="testset_prices", kind="fact", topic="test_sets", audience=ALL_AGENTS, priority=15,
         title="Ціни тест-наборів", text=TESTSET_PRICES),
    dict(key="pricing_m2", kind="rule", topic="pricing", audience=CLIENT_AGENTS, priority=20,
         title="Прорахунок на обʼєм",
         text="Мінімальні орієнтири за м² (з каталогу CRM): Галатея {m2:1623} / Мокрий шовк {m2:1610} / Celestial {m2:1614} / "
              "Velvet Lux {m2:1650:0.45} / Патера {m2:1639:1}. Ціна за м² — лише декоративний матеріал (без ґрунту й захисту). "
              "Підсумкову суму не давати без названого матеріалу й підтвердження клієнта; тонування рахується індивідуально; точний кошторис — менеджер."),
    dict(key="contacts", kind="fact", topic="contacts", audience=ALL_AGENTS, priority=10,
         title="Контакти Wallcov",
         text="Дзвінки — 096 419 18 90 (сайти, Google, бот). Viber / Telegram / WhatsApp — 097 328 22 83 "
              "(Viber: https://msng.link/o?380973282283=vi, Telegram: https://t.me/wallcov_pidtrimka). Інших номерів клієнтам не давати."),
    dict(key="material_names", kind="rule", topic="materials", audience=CLIENT_AGENTS, priority=30,
         title="Багатозначні назви матеріалів",
         text="«Вельвет» — не конкретний матеріал: є Velvet Luna (тонкошаровий, ефект мокрого шовку) і Velvet Lux (структурний перламутровий, "
              "дорожчий у 3–4 рази) — спершу уточнити який. «Мокрий шовк» — Sirena Silk / Mermi Silk / Velvet Luna: дивитися контекст, не вгадувати."),
    dict(key="protection", kind="rule", topic="tone", audience=CLIENT_AGENTS, priority=20,
         title="Захисне покриття не навʼязувати",
         text="Для тонкошарових (Мокрий шовк, Галатея, Вельвет, Celestial) захист НЕ обовʼязковий і в набір не входить. Говорити про захист лише якщо "
              "клієнт сам спитав про захист/миття/вологу або сказав, що це ванна, кухня з прямим попаданням води чи фасад. "
              "Verma visk — частина фактурних наборів (Pattera Fine, Slate, травертин)."),
    dict(key="no_invention", kind="rule", topic="tone", audience=ALL_AGENTS, priority=5,
         title="Не вигадувати",
         text="Жодної вигаданої цифри, товару, тест-набору чи відео. Ціни — лише з блоку «Ціни з каталогу CRM» або з того, що вже звучало в діалозі. "
              "Немає точної ціни — «порахую точно і надішлю». Матеріалу немає в каталозі — чесно передати менеджеру."),
    dict(key="no_mechanics", kind="rule", topic="tone", audience=CLIENT_AGENTS, priority=20,
         title="Не пояснювати внутрішню механіку",
         text="Клієнту не пояснювати внутрішню механіку компанії (черговість продажів, допродажі, етапи воронки) — лише корисна інформація про товар."),
    dict(key="repeat_clients", kind="rule", topic="process", audience=CLIENT_AGENTS, priority=30,
         title="Повторні клієнти",
         text="«Купувала минулого року», «повторити те саме» — не вгадувати матеріал; передати менеджеру, щоб знайти в CRM історію і повторити точно."),
]


def _snap(item):
    return {"kind": item.kind, "topic": item.topic, "audience": list(item.audience), "status": item.status,
            "title": item.title, "text": item.text, "internal_note": item.internal_note, "priority": item.priority,
            "products": [], "replaces": None}


def plan_import(approve_ids=None, seeds=True):
    """Що буде створено (нічого не пише)."""
    from apps.crm.models import KbEntry
    approve_ids = set(APPROVED_ON_13_09 if approve_ids is None else approve_ids)
    existing = set(KnowledgeItem.objects.exclude(source_ref="").values_list("source_ref", flat=True))
    plan, skipped_existing, skipped_empty = [], 0, 0
    for e in KbEntry.objects.order_by("id"):
        ref = "kbentry:%d" % e.id
        if ref in existing:
            skipped_existing += 1
            continue
        answer = (e.answer or "").strip()
        question = (e.question or "").strip()
        if not answer or not question:
            skipped_empty += 1
            continue
        flags = flags_for("\n".join([question, answer, e.specific_rules or ""]))
        topic = guess_topic(question)
        if topic == "other":
            topic = guess_topic(answer)
        note = ["Імпорт зі старої бази AI ЦЕНТРУ (запис №%d)." % e.id]
        if flags:
            note.append("⚠️ Перевірити: " + "; ".join(flags))
        if (e.specific_rules or "").strip():
            note.append("Окремі правила ChatPlace: " + e.specific_rules.strip())
        status = "draft"
        if not e.enabled:
            status = "archived"
        elif e.id in approve_ids and not flags:
            status = "approved"
        plan.append({
            "ref": ref, "kb_id": e.id, "kind": "qa", "topic": topic, "status": status, "flags": flags,
            "title": question[:300], "text": answer, "internal_note": "\n".join(note),
            "source": "import_kb", "audience": list(CLIENT_AGENTS), "popularity": int(e.client_chat_count or 0),
            "external_ids": {"chatplace_ig": e.ext_id} if (e.source == "chatplace" and e.ext_id) else {},
            "approved_at": e.updated_at if status == "approved" else None,
        })
    seeds_plan = []
    if seeds:
        for s in CODE_SEEDS:
            ref = "code:" + s["key"]
            if ref in existing:
                skipped_existing += 1
                continue
            seeds_plan.append({
                "ref": ref, "kb_id": None, "kind": s["kind"], "topic": s["topic"], "status": "draft", "flags": [],
                "title": s["title"], "text": s["text"], "source": "code", "audience": list(s["audience"]),
                "internal_note": "Правило з коду CRM / рішення Олега 14.09 — затвердіть, і всі агенти читатимуть його з бази.",
                "popularity": 0, "external_ids": {}, "approved_at": None, "priority": s.get("priority", 100),
            })
    return {"rows": plan, "seeds": seeds_plan, "skipped_existing": skipped_existing, "skipped_empty": skipped_empty}


@transaction.atomic
def apply_import(plan, user=None):
    now = timezone.now()
    items = []
    for r in plan["rows"] + plan["seeds"]:
        items.append(KnowledgeItem(
            kind=r["kind"], topic=r["topic"], audience=r["audience"], status=r["status"], title=r["title"],
            text=r["text"], internal_note=r["internal_note"], source=r["source"], source_ref=r["ref"],
            external_ids=r["external_ids"], popularity=r["popularity"], priority=r.get("priority", 100),
            approved_at=(r["approved_at"] or now) if r["status"] == "approved" else None,
            approval_note=APPROVAL_NOTE_13_09 if r["status"] == "approved" else "",
            created_by=user, updated_by=user))
    created = KnowledgeItem.objects.bulk_create(items, batch_size=200)
    if created and created[0].pk is None:  # не-Postgres: перечитати id
        refs = [i.source_ref for i in items]
        created = list(KnowledgeItem.objects.filter(source_ref__in=refs))
    KnowledgeVersion.objects.bulk_create([
        KnowledgeVersion(item=i, version=1, action="import", snapshot=_snap(i), changed_by=user,
                         note=(i.approval_note or "імпорт")[:300])
        for i in created], batch_size=200)
    return len(created)


def summary(plan):
    rows, seeds = plan["rows"], plan["seeds"]
    by_topic, by_status, flagged = {}, {}, {}
    for r in rows:
        by_topic[r["topic"]] = by_topic.get(r["topic"], 0) + 1
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        for f in r["flags"]:
            flagged.setdefault(f, []).append(r["kb_id"])
    return {"rows": len(rows), "seeds": len(seeds), "by_topic": by_topic, "by_status": by_status,
            "approved_ids": [r["kb_id"] for r in rows if r["status"] == "approved"], "flagged": flagged,
            "skipped_existing": plan["skipped_existing"], "skipped_empty": plan["skipped_empty"]}
