"""Пошук дублів клієнтів / лідів / сделок + об'єднання.
Дублі контактів шукаємо за: телефоном, email, мессенджером(social_link), іменем.
Дублі лідів/сделок = один контакт має кілька сутностей.
Доступ — лише адмін (roles.manage / staff).

ФІЛЬТРИ (GET):
  ?q=      — пошук по номеру / прізвищу / email / ніку (шукає серед учасників групи)
  ?by=     — тільки групи, знайдені за критерієм: phone | email | social | name
  ?min=    — мінімальна «сила» збігу: скільки полів однакові у ВСІХ учасників групи (1..4)
МАСОВЕ ОБ'ЄДНАННЯ (POST {"groups": [{"keep": id, "ids": [..]}, ...], "dry_run": true|false}).
"""
import re
from collections import defaultdict
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from apps.inbox.models import Contact, Conversation
from apps.crm.models import Lead, Deal

# скільки груп максимум віддаємо на фронт / скільки груп максимум за один масовий мердж
MAX_GROUPS = 500
MAX_BULK = 300


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


def _norm_social(s):
    return (s or "").strip().lower().rstrip("/")


def _full(i):
    return ((i.get("first_name") or "") + " " + (i.get("last_name") or "")).strip() or "—"


# ── «сила» збігу: які саме поля ОДНАКОВІ у ВСІХ учасників групи ──
_NORMALIZERS = [
    ("phone", lambda r: _norm_phone(r["phone"])),
    ("email", lambda r: _norm_email(r["email"])),
    ("social", lambda r: _norm_social(r["social_link"])),
    ("name", lambda r: _norm_name(r["first_name"], r["last_name"])),
]


def _matched_fields(items):
    """Повертає список полів, що заповнені й ідентичні у всіх учасників групи."""
    out = []
    for key, fn in _NORMALIZERS:
        vals = {fn(r) for r in items}
        if len(vals) == 1 and "" not in vals:
            out.append(key)
    return out


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
            return Response(self._contacts(q=q, by=by, min_strength=min_strength))
        if typ == "leads":
            return Response(self._entity(Lead, "leads", q=q))
        if typ == "deals":
            return Response(self._entity(Deal, "deals", q=q))
        return Response({"type": typ, "total": 0, "groups": []})

    # ── дублі контактів ──
    def _contacts(self, q="", by="", min_strength=0):
        rows = list(Contact.objects.values("id", "first_name", "last_name", "phone", "email", "social_link"))
        idx = {r["id"]: r for r in rows}
        buckets = {"phone": defaultdict(list), "email": defaultdict(list),
                   "social": defaultdict(list), "name": defaultdict(list)}
        for r in rows:
            ph = _norm_phone(r["phone"])
            if ph:
                buckets["phone"][ph].append(r)
            em = _norm_email(r["email"])
            if em:
                buckets["email"][em].append(r)
            sl = _norm_social(r["social_link"])
            if sl:
                buckets["social"][sl].append(r)
            nm = _norm_name(r["first_name"], r["last_name"])
            if nm:
                buckets["name"][nm].append(r)

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

        labels = {"phone": "Телефон", "email": "Email", "social": "Мессенджер/нік", "name": "Имя"}
        order = {"phone": 0, "email": 1, "social": 2, "name": 3}
        groups = []
        for fs, e in cand.items():
            items = [idx[i] for i in sorted(fs)]
            if q and not any(_row_hits(r, q) for r in items):
                continue
            if by and by not in e["by"]:
                continue
            matched = _matched_fields(items)
            if min_strength and len(matched) < min_strength:
                continue
            primary = sorted(e["by"], key=lambda x: order.get(x, 9))[0]
            keep_suggest = sorted(items, key=lambda r: (-_filled_score(r), r["id"]))[0]["id"]
            groups.append({
                "reason": labels[primary], "by": primary, "key": e["keys"][primary],
                "matched": matched,                       # список полів, однакових у ВСІХ
                "strength": len(matched),                 # «сила» збігу 1..4
                "count": len(items),
                "keep_suggest": keep_suggest,
                "items": [{"id": i["id"], "name": _full(i), "phone": i["phone"] or "",
                           "email": i["email"] or "", "social": i["social_link"] or ""} for i in items],
            })
        # найнадійніші (збіг по багатьох полях) — першими
        groups.sort(key=lambda g: (-g["strength"], order.get(g["by"], 9), -g["count"]))
        return {"type": "contacts", "total": len(groups), "groups": groups[:MAX_GROUPS]}

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
                "matched": [], "strength": 0, "keep_suggest": objs[0].id,
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
        for src in Contact.objects.filter(id__in=ids):
            for f in ["phone", "email", "social_link", "first_name", "last_name", "address", "company", "birthday"]:
                if not getattr(k, f) and getattr(src, f):
                    setattr(k, f, getattr(src, f))
        k.save()
        Contact.objects.filter(id__in=ids).delete()
