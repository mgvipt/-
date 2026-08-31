"""Пошук дублів клієнтів / лідів / сделок + об'єднання.
Дублі контактів шукаємо за: НОМЕРОМ ПЕРЕПИСКИ, телефоном, email, мессенджером, ніком, іменем.
Дублі лідів/сделок = один контакт має кілька сутностей.
Доступ — лише адмін (roles.manage / staff).

ФІЛЬТРИ (GET):
  ?q=      — пошук по номеру / прізвищу / email / ніку (шукає серед учасників групи)
  ?by=     — тільки групи, знайдені за критерієм: chat | phone | email | social | nick | name
  ?min=    — мінімальна «сила» збігу: скільки полів однакові у ВСІХ учасників групи (1..4)
  ?dismissed=1 — показати навпаки ТІЛЬКИ приховані («це різні люди»), щоб можна було повернути
ПОЗНАЧКА «ЦЕ РІЗНІ ЛЮДИ» (POST {"action": "dismiss"|"undismiss", "ids": [...], "reason": "..."})
МАСОВЕ ОБ'ЄДНАННЯ (POST {"groups": [{"keep": id, "ids": [..]}, ...], "dry_run": true|false}).

31.08.2026:
  • месенджер шукаємо в УСІХ посиланнях картки (social_link + messengers + links_extra),
    раніше — тільки social_link;
  • новий критерій «номер переписки» (один external_chat_id у різних контактів = 100% дубль);
  • новий критерій «нік з месенджера» — ТІЛЬКИ справжній нік акаунта (див. _nick_is_reliable);
  • картки з міткою «[обʼєднано → #N]» (хвости після dedup_ig_contacts) зі списку прибрані —
    вони вже склеєні, просто не видалені (265 штук);
  • конфлікти: якщо всередині групи РІЗНІ телефони/акаунти — це, найімовірніше, РІЗНІ люди
    (поле "conflicts"), фронт показує попередження і не дає масово злити не глянувши.
"""
import re
from collections import defaultdict
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Count
from apps.inbox.models import Contact, Conversation
from apps.crm.models import Lead, Deal, DuplicateDismissal

# скільки груп максимум віддаємо на фронт / скільки груп максимум за один масовий мердж
MAX_GROUPS = 1200
MAX_BULK = 300
# скільки карток на одному посиланні ще схоже на дубль (більше — це спільний/службовий акаунт)
MAX_SAME_LINK = 8
# мітка, якою dedup_ig_contacts позначає вже об'єднаний дубль
_MERGED_MARK = "[обʼєднано →"


def _can(user):
    if user.is_staff or user.is_superuser:
        return True
    try:
        return "roles.manage" in user.effective_permissions()
    except Exception:
        return False


def _norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    return d[-9:] if len(d) >= 9 else ""


_PLACEHOLDERS = {"гость", "гість", "без имени", "без імені", "клиент", "клієнт", "guest",
                 "instagram", "facebook", "user", "користувач", "ноунейм", "невідомо"}


def _norm_name(f, l):
    # потрібні ОБИДВА (імʼя + прізвище) — інакше «Оксана» зливала б усіх Оксан
    f = (f or "").strip().lower()
    l = (l or "").strip().lower()
    if not f or not l or f == l:  # «Оксана Оксана» = фактично одне імʼя → не групуємо
        return ""
    s = (f + " " + l).strip()
    if any(p in s for p in _PLACEHOLDERS) or len(s) < 5:
        return ""
    return s


def _norm_email(e):
    return (e or "").strip().lower()


# рекламні/трекінгові хвости, які НЕ впливають на те, чий це акаунт
_TRACK_PARAMS = {"igshid", "fbclid", "mibextid", "hl", "ref", "ref_src", "si", "_rdr",
                 "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"}


def _norm_social(s):
    """Посилання на акаунт → однаковий вигляд «instagram.com/nick».
    Прибираємо протокол, www., трекінгові параметри (?igshid=…, ?fbclid=…) і слеш у кінці —
    інакше та сама сторінка у двох картках виглядає по-різному і дубль не знаходиться.
    ⚠️ ВЕСЬ «?…» різати НЕ можна: у «viber://chat?number=380…» і «tg://user?id=…» саме
    в параметрі лежить сам номер — без нього всі вайбер-контакти злипаються в одну купу."""
    v = (s or "").strip().lower()
    if not v:
        return ""
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v)
    v = v.split("#")[0]
    if "?" in v:
        base, qs = v.split("?", 1)
        keep = sorted(p for p in qs.split("&") if p and p.split("=", 1)[0] not in _TRACK_PARAMS)
        v = base + ("?" + "&".join(keep) if keep else "")
    return v.rstrip("/")


def _platform(link):
    """Площадка посилання: instagram.com / tiktok.com / t.me / viber / tg."""
    v = link or ""
    if "://" in v:                      # viber://chat?number=…, tg://user?id=…
        return v.split("://", 1)[0]
    return v.split("/", 1)[0]


def _links_of(r):
    """ВСІ посилання на акаунти контакта: головне поле + список месенджерів + додаткові.
    Раніше дивились лише в social_link — у карток, створених з переписки, воно порожнє,
    а посилання лежить у messengers → дублі були невидимі."""
    pool = [r.get("social_link")]
    pool += list(r.get("messengers") or [])
    for x in (r.get("links_extra") or []):
        pool.append(x.get("value") if isinstance(x, dict) else x)
    out = set()
    for m in pool:
        m = _norm_social(m if isinstance(m, str) else "")
        if m:
            out.add(m)
    return out


# нік вважаємо надійним, лише якщо він схожий на username месенджера (латиниця/цифри/._-).
# Текстовий нік («Людмила», «Юлія») — це просто імʼя, по ньому зливати НЕ можна.
_USERNAME_RE = re.compile(r"^[a-z0-9._\-]{3,}$")
# ⚠️ латиниця сама по собі НЕ доказ: «Iryna», «Tetiana», «Ludmila» — це теж імена, і по них
# злиплися б РІЗНІ люди (перевірено 31.08: 4 різні Ludmila, у двох є сделки). Тому нік беремо
# лише якщо в ньому є цифра/крапка/підкреслення/дефіс АБО його підтверджує посилання /<нік>.
_NICK_MARKS = re.compile(r"[0-9._\-]")
_NICK_PLACEHOLDERS = {"instagram", "facebook", "telegram", "viber", "whatsapp", "tiktok", "user", "guest"}


def _norm_nick(n):
    v = (n or "").strip().lower().lstrip("@")
    if v in _NICK_PLACEHOLDERS:
        return ""
    return v if _USERNAME_RE.match(v) else ""


def _nick_is_reliable(nick, links):
    """Чи це справжній нік акаунта, а не імʼя латиницею."""
    if not nick:
        return False
    return bool(_NICK_MARKS.search(nick)) or any(l.endswith("/" + nick) for l in links)


def _group_key(ids):
    """Ключ групи для позначки «це різні люди» — ID карток через дефіс."""
    return "-".join(str(i) for i in sorted(ids))


def _full(i):
    return ((i.get("first_name") or "") + " " + (i.get("last_name") or "")).strip() or "—"


# ── «сила» збігу: які саме поля ОДНАКОВІ у ВСІХ учасників групи ──
_NORMALIZERS = [
    ("phone", lambda r: _norm_phone(r["phone"])),
    ("email", lambda r: _norm_email(r["email"])),
    ("nick", lambda r: _norm_nick(r.get("nickname"))),
    ("name", lambda r: _norm_name(r["first_name"], r["last_name"])),
]


def _matched_fields(items):
    """Повертає список полів, що заповнені й ідентичні у всіх учасників групи."""
    out = []
    for key, fn in _NORMALIZERS:
        vals = {fn(r) for r in items}
        if len(vals) == 1 and "" not in vals:
            out.append(key)
    # месенджер рахуємо як збіг, якщо у ВСІХ є хоч одне спільне посилання
    link_sets = [_links_of(r) for r in items]
    if all(link_sets) and set.intersection(*link_sets):
        out.append("social")
    return out


def _conflict_fields(items):
    """Поля, які у групі РОЗХОДЯТЬСЯ → швидше за все це РІЗНІ люди, а не дублі.
    Приклад із життя (31.08): два різні клієнти на одному номері — Анна Пікшрєнє і
    Юлия Чикаловец (+380678664328). Збіг телефону є, але аккаунти різні → не зливати."""
    out = []
    for key, fn in _NORMALIZERS:
        vals = {fn(r) for r in items}
        vals.discard("")
        if len(vals) > 1:
            out.append(key)
    # ⚠️ порівнюємо акаунти ПОМАЙДАНЧИКОВО: «instagram.com/natasha.sharun» і
    # «tiktok.com/@natasha.sharun» — це та сама людина у двох мережах, а не розбіжність.
    # Конфлікт = на ОДНІЙ площадці різні акаунти (instagram.com/baranovska953 vs .../zhmurko784).
    by_platform = defaultdict(list)
    for r in items:
        seen = defaultdict(set)
        for l in _links_of(r):
            seen[_platform(l)].add(l)
        for plat, links in seen.items():
            by_platform[plat].append(links)
    for plat, sets_ in by_platform.items():
        if len(sets_) > 1 and not set.intersection(*sets_):
            out.append("social")
            break
    return out


# жорсткі ідентифікатори: розбіжність тут — вагома підстава вважати людей різними
_HARD_IDS = {"phone", "email", "social"}


def _conflicts_to_show(by, conflicts):
    """Що саме попереджати. Не кожна розбіжність = різні люди:
    • знайшли по НОМЕРУ ПЕРЕПИСКИ — це точно одна людина (у Meta/IG імʼя міняють вільно:
      «MARGO RYSTAMOVA» → «MARGO CHUB»), попереджати немає про що;
    • знайшли по СПІЛЬНОМУ АКАУНТУ — акаунт особистий, імʼя/нік у картках можуть різнитись,
      важливо лише якщо розходяться телефон/пошта;
    • знайшли по телефону або імені — попереджаємо про будь-яку розбіжність (один номер на
      двох людей реально буває: Анна Пікшрєнє / Юлия Чикаловец на +380678664328)."""
    if by == "chat":
        return []
    if by == "social":
        return [c for c in conflicts if c in _HARD_IDS]
    return conflicts


def _filled_score(r):
    """Скільки корисних полів заповнено — щоб запропонувати кого залишати."""
    return sum(1 for f in ("phone", "email", "social_link", "first_name", "last_name") if (r.get(f) or "").strip())


def _row_hits(r, q):
    """Чи підходить контакт під пошуковий рядок (номер / прізвище / email / нік)."""
    ql = q.strip().lower()
    if not ql:
        return True
    digits = re.sub(r"\D", "", ql)
    if digits and len(digits) >= 3:
        if digits in re.sub(r"\D", "", r.get("phone") or ""):
            return True
    hay = " ".join([(r.get("first_name") or ""), (r.get("last_name") or ""),
                    (r.get("email") or ""), (r.get("social_link") or ""),
                    (r.get("nickname") or ""), " ".join(_links_of(r)),
                    (r.get("phone") or "")]).lower()
    return ql in hay


class DuplicatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can(request.user):
            return Response({"detail": "Немає доступу"}, status=403)
        typ = request.query_params.get("type", "contacts")
        q = (request.query_params.get("q") or "").strip()
        by = (request.query_params.get("by") or "").strip()
        try:
            min_strength = int(request.query_params.get("min") or 0)
        except ValueError:
            min_strength = 0
        if typ == "contacts":
            return Response(self._contacts(q=q, by=by, min_strength=min_strength,
                                           dismissed=request.query_params.get("dismissed") in ("1", "true"),
                                           user=request.user))
        if typ == "leads":
            return Response(self._entity(Lead, "leads", q=q))
        if typ == "deals":
            return Response(self._entity(Deal, "deals", q=q))
        return Response({"type": typ, "total": 0, "groups": []})

    # ── дублі контактів ──
    def _contacts(self, q="", by="", min_strength=0, dismissed=False, user=None):
        rows = [r for r in Contact.objects.values(
            "id", "first_name", "last_name", "phone", "email",
            "social_link", "messengers", "links_extra", "nickname", "comment")
            # хвости вже об'єднаних карток (мітку ставить dedup_ig_contacts) — не дублі,
            # а порожні залишки: показувати їх у списку немає сенсу
            if _MERGED_MARK not in (r.get("comment") or "")]
        idx = {r["id"]: r for r in rows}
        buckets = {"chat": defaultdict(list), "phone": defaultdict(list), "email": defaultdict(list),
                   "social": defaultdict(list), "nick": defaultdict(list), "name": defaultdict(list)}
        for r in rows:
            ph = _norm_phone(r["phone"])
            if ph:
                buckets["phone"][ph].append(r)
            em = _norm_email(r["email"])
            if em:
                buckets["email"][em].append(r)
            # месенджер: усі посилання картки (головне поле + список + додаткові)
            for sl in _links_of(r):
                buckets["social"][sl].append(r)
            nk = _norm_nick(r.get("nickname"))
            if nk and _nick_is_reliable(nk, _links_of(r)):
                buckets["nick"][nk].append(r)
            nm = _norm_name(r["first_name"], r["last_name"])
            if nm:
                buckets["name"][nm].append(r)

        # службові/спільні посилання (наш власний профіль, заглушки без номера) —
        # це не «одна людина двома картками», прибираємо цілком
        for sl in [k for k, v in buckets["social"].items() if len(v) > MAX_SAME_LINK]:
            del buckets["social"][sl]

        # ── НОМЕР ПЕРЕПИСКИ: один і той самий чат у різних карток = 100% дубль ──
        chats = defaultdict(set)
        for cid, ch, ext in Conversation.objects.exclude(contact__isnull=True).values_list(
                "contact_id", "channel_id", "external_chat_id"):
            if ext:
                chats[(ch, ext)].add(cid)
        for (ch, ext), cids in chats.items():
            if len(cids) > 1:
                buckets["chat"][f"{ch}:{ext}"] = [idx[i] for i in cids if i in idx]

        # головною пропонуємо картку, де Є СДЕЛКИ (там гроші та історія), а вже потім —
        # де більше заповнених полів. Раніше рахували лише поля — і система пропонувала
        # лишити порожню новішу картку замість тієї, де сделка (кейс MARGO 31.08).
        deal_cnt = {}
        for cid, n in Deal.objects.values_list("contact_id").annotate(n=Count("id")):
            if cid:
                deal_cnt[cid] = n

        # ── склеюємо однакові набори контактів: одна група = один набір id ──
        # (раніше та сама пара контактів показувалась 4 рази — по разу на критерій)
        cand = {}
        for reason, b in buckets.items():
            for key, items in b.items():
                if len(items) < 2:
                    continue
                fs = frozenset(i["id"] for i in items)
                e = cand.setdefault(fs, {"by": set(), "keys": {}})
                e["by"].add(reason)
                e["keys"][reason] = key

        # приховані рішенням «це різні люди»
        hidden = dict(DuplicateDismissal.objects.values_list("key", "reason"))
        labels = {"chat": "Номер переписки", "phone": "Телефон", "email": "Email",
                  "social": "Мессенджер/нік", "nick": "Нік з месенджера", "name": "Имя"}
        order = {"chat": 0, "phone": 1, "email": 2, "social": 3, "nick": 4, "name": 5}
        groups = []
        n_hidden = 0
        for fs, e in cand.items():
            items = [idx[i] for i in sorted(fs)]
            gkey = _group_key(fs)
            is_hidden = gkey in hidden
            if is_hidden:
                n_hidden += 1
            # звичайний режим — ховаємо позначені; ?dismissed=1 — показуємо ТІЛЬКИ їх
            if is_hidden != bool(dismissed):
                continue
            if q and not any(_row_hits(r, q) for r in items):
                continue
            if by and by not in e["by"]:
                continue
            matched = _matched_fields(items)
            if min_strength and len(matched) < min_strength:
                continue
            primary = sorted(e["by"], key=lambda x: order.get(x, 9))[0]
            conflicts = _conflicts_to_show(primary, _conflict_fields(items))
            keep_suggest = sorted(items, key=lambda r: (-deal_cnt.get(r["id"], 0),
                                                        -_filled_score(r), r["id"]))[0]["id"]
            groups.append({
                "reason": labels[primary], "by": primary, "key": e["keys"][primary],
                "gkey": gkey,                             # ключ для позначки «це різні люди»
                "dismissed": is_hidden,
                "dismiss_reason": hidden.get(gkey, ""),
                "matched": matched,                       # список полів, однакових у ВСІХ
                "conflicts": conflicts,                   # поля, що РОЗХОДЯТЬСЯ (ознака різних людей)
                "strength": len(matched),                 # «сила» збігу 1..4
                "count": len(items),
                "keep_suggest": keep_suggest,
                "items": [{"id": i["id"], "name": _full(i), "phone": i["phone"] or "",
                           "email": i["email"] or "",
                           # показуємо ВСІ месенджери картки, а не лише головне поле
                           "social": " · ".join(sorted(_links_of(i))) or ""} for i in items],
            })
        # спершу найнадійніший критерій (переписка → телефон → …), потім сила збігу
        groups.sort(key=lambda g: (order.get(g["by"], 9), -g["strength"], -g["count"]))
        return {"type": "contacts", "total": len(groups), "hidden_total": n_hidden,
                "groups": groups[:MAX_GROUPS]}

    # ── дублі лідів/сделок: один контакт + ОДНАКОВА назва (реальний дубль вводу) ──
    def _entity(self, Model, typ, q=""):
        seen = defaultdict(list)
        for o in Model.objects.select_related("contact", "stage", "owner").exclude(contact__isnull=True):
            title = (o.title or "").strip().lower()
            if not title:
                continue
            seen[(o.contact_id, title)].append(o)
        ql = (q or "").strip().lower()
        groups = []
        for (cid, title), objs in seen.items():
            if len(objs) < 2:
                continue
            c = objs[0].contact
            cname = ((c.first_name or "") + " " + (c.last_name or "")).strip() or f"#{cid}"
            if ql and ql not in (cname + " " + (objs[0].title or "") + " " + (c.phone or "")).lower():
                continue
            groups.append({
                "reason": "Одинаковые у одного контакта", "by": "contact",
                "key": f"{cname} · {objs[0].title}", "count": len(objs),
                "matched": [], "conflicts": [], "strength": 0, "keep_suggest": objs[0].id,
                "items": [{"id": o.id, "name": o.title or "—", "stage": getattr(o.stage, "name", "") or "",
                           "owner": (o.owner.get_full_name() if o.owner else "") or "",
                           "amount": str(o.amount or 0)} for o in objs],
            })
        groups.sort(key=lambda g: -g["count"])
        return {"type": typ, "total": len(groups), "groups": groups[:MAX_GROUPS]}

    # ── об'єднання контактів ──
    def post(self, request):
        if not _can(request.user):
            return Response({"detail": "Немає доступу"}, status=403)

        # ── позначка «це РІЗНІ люди» / повернути назад ──
        action = (request.data.get("action") or "").strip()
        if action in ("dismiss", "undismiss"):
            ids = [int(i) for i in (request.data.get("ids") or [])]
            if len(ids) < 2:
                return Response({"detail": "Потрібні мінімум 2 картки"}, status=400)
            key = _group_key(ids)
            if action == "undismiss":
                DuplicateDismissal.objects.filter(key=key).delete()
                return Response({"ok": True, "dismissed": False})
            DuplicateDismissal.objects.update_or_create(
                key=key, defaults={"contact_ids": sorted(ids),
                                   "reason": (request.data.get("reason") or "")[:200],
                                   "by_user": request.user if request.user.is_authenticated else None})
            return Response({"ok": True, "dismissed": True})

        # ── МАСОВЕ об'єднання: [{keep, ids}, ...] ──
        bulk = request.data.get("groups")
        if isinstance(bulk, list):
            return self._bulk(bulk, bool(request.data.get("dry_run")))

        keep = request.data.get("keep")
        ids = [i for i in (request.data.get("ids") or []) if i != keep]
        if not keep or not ids:
            return Response({"detail": "keep + ids обов'язкові"}, status=400)
        with transaction.atomic():
            self._merge_one(keep, ids, request.data.get("fields") or {}, request.data.get("messengers"))
        return Response({"ok": True, "merged": len(ids), "keep": keep})

    # ── масовий мердж: спершу dry_run (що саме буде зроблено), потім live ──
    def _bulk(self, bulk, dry_run):
        plan, skipped = [], []
        seen_ids = set()
        for g in bulk[:MAX_BULK]:
            keep = g.get("keep")
            ids = [i for i in (g.get("ids") or []) if i != keep]
            if not keep or not ids:
                skipped.append({"keep": keep, "why": "порожня група"})
                continue
            # один і той самий контакт не можна чіпати двічі за один прохід
            touched = set(ids) | {keep}
            if touched & seen_ids:
                skipped.append({"keep": keep, "why": "контакт вже задіяний в іншій групі"})
                continue
            seen_ids |= touched
            plan.append({"keep": keep, "ids": ids})

        if dry_run:
            names = {c.id: (((c.first_name or "") + " " + (c.last_name or "")).strip() or f"#{c.id}")
                     for c in Contact.objects.filter(id__in=list(seen_ids))}
            return Response({
                "dry_run": True,
                "groups": len(plan),
                "will_delete": sum(len(p["ids"]) for p in plan),
                "skipped": skipped,
                "preview": [{"keep": p["keep"], "keep_name": names.get(p["keep"], f"#{p['keep']}"),
                             "delete": [{"id": i, "name": names.get(i, f"#{i}")} for i in p["ids"]]}
                            for p in plan[:50]],
            })

        done, failed = 0, []
        for p in plan:
            try:
                with transaction.atomic():
                    self._merge_one(p["keep"], p["ids"], {}, None)
                done += len(p["ids"])
            except Exception as e:  # одна погана група не валить весь прохід
                failed.append({"keep": p["keep"], "error": str(e)[:200]})
        return Response({"ok": True, "groups": len(plan) - len(failed), "merged": done,
                         "failed": failed, "skipped": skipped})

    # ── саме злиття одного набору: keep ← ids ──
    def _merge_one(self, keep, ids, fields, msgs):
        k = Contact.objects.get(id=keep)
        # перепривʼязати ВСІ реверсивні FK з дублів → на keep
        for rel in Contact._meta.related_objects:
            fname = rel.field.name
            model = rel.related_model
            try:
                if rel.many_to_many:
                    for obj in model.objects.filter(**{f"{fname}__in": ids}):
                        getattr(obj, fname).remove(*list(getattr(obj, fname).filter(id__in=ids)))
                        getattr(obj, fname).add(k)
                else:
                    model.objects.filter(**{f"{fname}__in": ids}).update(**{fname: k})
            except Exception:
                pass
        # 1) ЯВНИЙ вибір полів (галочки в модалці об'єднання): що обрано — те й ставимо на keep
        ALLOWED = {"first_name", "last_name", "middle_name", "nickname", "phone", "email",
                   "social_link", "address", "birthday", "source", "edrpou", "iban", "comment"}
        for f, v in (fields or {}).items():
            if f not in ALLOWED:
                continue
            if f == "birthday":
                setattr(k, f, v or None)
            else:
                setattr(k, f, v if v is not None else "")
        # 1b) МУЛЬТИ-месенджери: зберігаємо обраний список (галочки) + дозаповнюємо з дублів
        if isinstance(msgs, list):
            seen, res = set(), []
            src_all = [k] + list(Contact.objects.filter(id__in=ids))
            pool = list(msgs)
            for c in src_all:
                if c.social_link:
                    pool.append(c.social_link)
                for m in (c.messengers or []):
                    pool.append(m)
            picked = set((x or "").strip().lower() for x in msgs if (x or "").strip())
            for m in pool:
                m = (m or "").strip()
                if m and m.lower() in picked and m.lower() not in seen:
                    seen.add(m.lower()); res.append(m)
            k.messengers = res
            if res and not (fields or {}).get("social_link"):
                k.social_link = res[0]
        else:
            # масовий мердж без ручного вибору: зберігаємо ВСІ месенджери з усіх дублів
            try:
                seen, res = set(), []
                for c in [k] + list(Contact.objects.filter(id__in=ids)):
                    for m in ([c.social_link] + list(c.messengers or [])):
                        m = (m or "").strip()
                        if m and m.lower() not in seen:
                            seen.add(m.lower()); res.append(m)
                k.messengers = res
            except Exception:
                pass
        # 2) обʼєднати канали месенджерів (union усіх)
        try:
            chans = set(k.channels or [])
            for src in Contact.objects.filter(id__in=ids):
                chans |= set(src.channels or [])
            k.channels = sorted(chans)
        except Exception:
            pass
        # 3) дозаповнити ПОРОЖНІ поля keep з дублів (для полів, що НЕ обрані явно)
        dups = list(Contact.objects.filter(id__in=ids))
        for src in dups:
            for f in ["phone", "email", "social_link", "first_name", "last_name", "address", "company", "birthday"]:
                if not getattr(k, f) and getattr(src, f):
                    setattr(k, f, getattr(src, f))
        # 4) ⚠️ НІЧОГО НЕ ГУБИМО: другий телефон / друга пошта дубля не влізають у головне
        # поле (воно вже зайняте) — складаємо їх у «Додаткові телефони/пошти» з підписом,
        # з якої картки прийшли. Раніше такі дані просто зникали разом з дублем.
        def _push_extra(field, value, label):
            if not value:
                return
            cur = list(getattr(k, field, None) or [])
            main = (getattr(k, "phone" if field == "phones_extra" else "email", "") or "").strip().lower()
            same = {(x.get("value") or "").strip().lower() for x in cur if isinstance(x, dict)}
            same.add(main)
            if value.strip().lower() in same:
                return
            cur.append({"label": label, "value": value})
            setattr(k, field, cur)

        for src in dups:
            src_name = ((src.first_name or "") + " " + (src.last_name or "")).strip() or ("#%d" % src.id)
            _push_extra("phones_extra", (src.phone or "").strip(), "з картки %s" % src_name)
            _push_extra("emails_extra", (src.email or "").strip(), "з картки %s" % src_name)
            for x in (src.phones_extra or []):
                if isinstance(x, dict):
                    _push_extra("phones_extra", (x.get("value") or "").strip(), x.get("label") or ("з картки %s" % src_name))
            for x in (src.emails_extra or []):
                if isinstance(x, dict):
                    _push_extra("emails_extra", (x.get("value") or "").strip(), x.get("label") or ("з картки %s" % src_name))
            # інша адреса — дописуємо в нотатки, щоб не загубити доставку
            a = (src.address or "").strip()
            if a and a.lower() != (k.address or "").strip().lower():
                note = "Адреса з картки %s: %s" % (src_name, a)
                if note not in (k.comment or ""):
                    k.comment = ((k.comment or "") + (" | " if k.comment else "") + note)[:4000]
        k.save()
        Contact.objects.filter(id__in=ids).delete()
