"""Бекфіл міток реклами Meta (14.09.2026, meta-attr).

За замовчуванням DRY-RUN — нічого не пише, лише рахує і показує приклади.
  --limit N      обробити лише N перших клієнтів/угод (перевірка на 1–2)
  --live         реально записати (тільки після «ок» Олега)

Режим за замовчуванням — «ймовірно з реклами» (класи A+C): перше повідомлення IG/FB-чату =
текст кнопки з оголошення («Galatea🔥», «Сирена💎», «Розрахунок на обʼєм»…):
  • «сліпий» період 01.07–21.08 (Meta ще не передавала мітку в CRM);
  • чати з 22.08, де Meta мітку загубила.
Режим --exact-carry — ТОЧНІ мітки, які вже є в CRM, але не дійшли до угод/лідів:
  • угоди клієнта, у ліда якого є перевірена мітка Meta;
  • чати-коментарі під рекламою (ad_id від Meta), де в ліда мітки немає.

Правила (однакові для обох режимів):
  • точну мітку не чіпаємо НІКОЛИ (у --exact-carry «ймовірно» підвищується до точної);
  • ліди — створені не раніше ніж за 1 день до першого контакту;
  • угоди — лише відкриті або виграні, створені не раніше ніж за 1 день до контакту
    (програні й закриті до контакту — не чіпаємо); у --exact-carry ще й клік ≤30 днів до угоди;
  • запис через .update(): без сигналів (у Meta CAPI нічого не йде) і без зміни «оновлено».
"""
from collections import Counter, defaultdict
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.meta_attr import services as ma

AFTER_FIX = date(2026, 8, 22)   # з цього дня вебхук Meta ловить referral (коміт d11105b9)


def _chunks(seq, size=500):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _d(dt):
    return timezone.localtime(dt).strftime("%d.%m.%Y") if dt else "—"


def _stage_word(obj):
    st = obj.stage
    if st.is_won:
        return "виграна %s₴" % int(obj.amount or 0)
    if st.is_lost:
        return "програна"
    return "відкрита"


class Command(BaseCommand):
    help = "Мітки реклами Meta: «ймовірно з реклами» (A+C) або --exact-carry. DRY за замовчуванням."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true", help="реально записати (без прапорця — DRY-RUN)")
        parser.add_argument("--limit", type=int, default=0, help="лише N перших клієнтів/угод")
        parser.add_argument("--since", default="2026-07-01", help="перший контакт від (РРРР-ММ-ДД)")
        parser.add_argument("--until", default="", help="перший контакт до, включно (порожньо = сьогодні)")
        parser.add_argument("--exact-carry", action="store_true",
                            help="точні мітки: угоди клієнтів з рекламним лідом + чати-коментарі під рекламою")
        parser.add_argument("--samples", type=int, default=10, help="скільки прикладів показати")

    def handle(self, *args, **opts):
        self.live = bool(opts["live"])
        self.limit = max(0, int(opts["limit"] or 0))
        self.samples = max(0, int(opts["samples"] or 0))
        try:
            since = date.fromisoformat(opts["since"])
            until = date.fromisoformat(opts["until"]) if opts["until"] else timezone.localdate()
        except ValueError:
            raise CommandError("Дата має бути у форматі РРРР-ММ-ДД")
        self.since_dt = timezone.make_aware(datetime.combine(since, dtime.min))
        self.until_dt = timezone.make_aware(datetime.combine(until + timedelta(days=1), dtime.min))
        self.mode = "LIVE" if self.live else "DRY-RUN"
        self.period = "%s … %s" % (since.strftime("%d.%m.%Y"), until.strftime("%d.%m.%Y"))
        if opts["exact_carry"]:
            self._exact_carry()
        else:
            self._likely()

    # ───────── спільне ─────────

    def out(self, line=""):
        self.stdout.write(line)

    def _exact_contact_ids(self):
        from apps.crm.models import Deal, Lead
        ids = set(Lead.objects.filter(meta_attribution__source_kind__in=ma.EXACT_KINDS)
                  .exclude(contact_id=None).values_list("contact_id", flat=True))
        ids |= set(Deal.objects.filter(meta_attribution__source_kind__in=ma.EXACT_KINDS)
                   .exclude(contact_id=None).values_list("contact_id", flat=True))
        return ids

    def _load(self, contact_ids):
        from apps.crm.models import Deal, Lead
        leads, deals = defaultdict(list), defaultdict(list)
        for chunk in _chunks(contact_ids):
            for obj in Lead.objects.filter(contact_id__in=chunk).select_related("stage").order_by("id"):
                leads[obj.contact_id].append(obj)
            for obj in Deal.objects.filter(contact_id__in=chunk).select_related("stage").order_by("id"):
                deals[obj.contact_id].append(obj)
        return leads, deals

    @staticmethod
    def _lead_ok(lead, first_at, upgrade_likely=False):
        cur = lead.meta_attribution or {}
        if ma.is_exact(cur) or (ma.is_likely(cur) and not upgrade_likely):
            return False
        return lead.created_at >= first_at - ma.CLICK_BEFORE_TOLERANCE

    @staticmethod
    def _deal_check(deal, first_at, upgrade_likely=False):
        cur = deal.meta_attribution or {}
        if ma.is_exact(cur):
            return "вже з точною"
        if ma.is_likely(cur) and not upgrade_likely:
            return "вже «ймовірно»"
        if deal.stage.is_lost:
            return "програна"
        if deal.created_at < first_at - ma.CLICK_BEFORE_TOLERANCE:
            return "створена раніше за контакт"
        return ""

    def _write(self, model, objs, attr, upgrade_likely=False):
        """Запис з повторною перевіркою під замком: точну мітку не перезаписуємо."""
        if not self.live or not objs:
            return 0
        n = 0
        with transaction.atomic():
            fresh = dict(model.objects.select_for_update().filter(pk__in=[o.pk for o in objs])
                         .values_list("id", "meta_attribution"))
            for pk, cur in fresh.items():
                cur = cur or {}
                if ma.is_exact(cur) or (ma.is_likely(cur) and not upgrade_likely):
                    continue
                new = dict(attr)
                if ma.is_likely(cur):
                    new["upgraded_from_likely"] = cur.get("phrase") or "так"
                model.objects.filter(pk=pk).update(meta_attribution=new)
                n += 1
        return n

    # ───────── «ймовірно з реклами» ─────────

    def _likely(self):
        from apps.crm.models import Deal, Lead
        from apps.inbox.models import Channel, Message
        cfg = ma.get_phrase_config(use_cache=False)
        chans = {c.id: c for c in Channel.objects.filter(kind__in=("instagram", "facebook"))}
        meta_ch = {cid for cid, c in chans.items() if (c.config or {}).get("meta")}
        after_fix_dt = timezone.make_aware(datetime.combine(AFTER_FIX, dtime.min))
        plain_words = {ma._norm(w) for w in (cfg.get("emoji_words") or [])}
        exact_ids = self._exact_contact_ids()

        firsts = (Message.objects.filter(conversation__channel_id__in=list(chans), direction="in", internal=False)
                  .exclude(conversation__external_chat_id__startswith="comment:")
                  .order_by("conversation_id", "created_at", "id").distinct("conversation_id")
                  .values_list("conversation_id", "conversation__contact_id", "conversation__channel_id",
                                "created_at", "text"))
        precision = defaultdict(lambda: [0, 0])
        per_contact, skipped_exact, matched_chats = {}, set(), 0
        for conv_id, contact_id, ch_id, created_at, text in firsts.iterator():
            phrase, group = ma.match_ad_phrase_group(text, cfg)
            if ch_id in meta_ch and contact_id and created_at >= after_fix_dt:
                g = group or ("B" if ma._norm(text).rstrip(" .!?,") in plain_words else "інше")
                precision[g][0] += 1
                precision[g][1] += int(contact_id in exact_ids)
            if not phrase or not contact_id or not (self.since_dt <= created_at < self.until_dt):
                continue
            matched_chats += 1
            if contact_id in exact_ids:
                skipped_exact.add(contact_id)
                continue
            prev = per_contact.get(contact_id)
            if prev is None or created_at < prev[0]:
                per_contact[contact_id] = (created_at, conv_id, phrase, group, chans[ch_id].kind)

        items = sorted(per_contact.items(), key=lambda kv: kv[1][0])
        if self.limit:
            items = items[:self.limit]
        leads, deals = self._load([cid for cid, _ in items])

        cols = ("blind", "after")
        stat = {c: Counter() for c in cols}
        won_sum = {c: Decimal("0") for c in cols}
        months = defaultdict(Counter)
        skip = Counter()
        no_target = 0
        samples, written_l, written_d = [], 0, 0
        now_iso = timezone.now().isoformat()
        for cid, (first_at, conv_id, phrase, group, platform) in items:
            tl = [x for x in leads[cid] if self._lead_ok(x, first_at)]
            td = []
            for d in deals[cid]:
                why = self._deal_check(d, first_at)
                if why:
                    skip[why] += 1
                else:
                    td.append(d)
            if not tl and not td:
                no_target += 1
                continue
            col = "blind" if timezone.localtime(first_at).date() < AFTER_FIX else "after"
            won = [d for d in td if d.stage.is_won]
            stat[col].update(contacts=1, leads=len(tl), deals=len(td), won=len(won))
            won_sum[col] += sum((d.amount or Decimal("0") for d in won), Decimal("0"))
            months[timezone.localtime(first_at).strftime("%Y-%m")].update(contacts=1, leads=len(tl), deals=len(td))
            if len(samples) < self.samples:
                samples.append("  клієнт #%s · чат #%s · %s · «%s» (%s) · ліди: %s · угоди: %s" % (
                    cid, conv_id, _d(first_at), phrase, group,
                    ", ".join("#%s" % x.id for x in tl) or "—",
                    ", ".join("#%s (%s)" % (x.id, _stage_word(x)) for x in td) or "—"))
            attr = ma.likely_attr(phrase, platform=platform, method="first_text_backfill", at=first_at,
                                  conversation_id=conv_id, backfilled_at=now_iso)
            written_l += self._write(Lead, tl, attr)
            written_d += self._write(Deal, td, attr)

        o = self.out
        o("=== backfill_meta_likely_ad · %s · «ймовірно з реклами» (класи A+C) ===" % self.mode)
        o("Перший контакт: %s%s" % (self.period, (" · LIMIT %s" % self.limit) if self.limit else ""))
        o("Фрази: слово+емодзі %s; префікси %s; фрази %s" % (
            cfg.get("emoji_words"), cfg.get("prefixes"), cfg.get("phrases")))
        o("")
        o("Перевірка точності (чати Meta з 22.08, де Meta вже дає точну мітку):")
        for g, label in (("A", "A слово+емодзі"), ("C", "C «Розрахунок на обʼєм»"), ("B", "B просто слово (НЕ мітимо)"),
                         ("інше", "інше (фон)")):
            n, hit = precision[g]
            o("  %-28s чатів %5s · з точною міткою %5s · %s" % (label, n, hit, ("%d%%" % round(hit * 100 / n)) if n else "—"))
        o("")
        o("Чатів з фразою в першому повідомленні за період: %s" % matched_chats)
        o("Клієнтів з фразою: %s (вже мають точну мітку — пропущено: %s; нема ліда/угоди для мітки: %s)" % (
            len(per_contact) + len(skipped_exact), len(skipped_exact), no_target))
        o("")
        o("%-26s %14s %16s %10s" % ("", "«сліпий» до 21.08", "з 22.08 (загубила)", "разом"))
        for key, label in (("contacts", "Клієнтів"), ("leads", "Лідів позначити"), ("deals", "Угод позначити"),
                           ("won", " з них виграних")):
            a, b = stat["blind"][key], stat["after"][key]
            o("%-26s %14s %16s %10s" % (label, a, b, a + b))
        o("%-26s %14s %16s %10s" % (" сума виграних, ₴", int(won_sum["blind"]), int(won_sum["after"]),
                                    int(won_sum["blind"] + won_sum["after"])))
        o("Угод НЕ чіпаємо: " + (", ".join("%s — %s" % (k, v) for k, v in skip.most_common()) or "—"))
        o("По місяцях першого контакту: " + "; ".join(
            "%s: клієнтів %s / лідів %s / угод %s" % (m, c["contacts"], c["leads"], c["deals"]) for m, c in sorted(months.items())))
        o("")
        o("Приклади (%s):" % len(samples))
        for line in samples:
            o(line)
        if self.live:
            o("")
            o("[LIVE] записано: лідів %s, угод %s" % (written_l, written_d))
        else:
            o("")
            o("DRY-RUN: нічого не записано. Перевірка на 1–2: --limit 1 --live; усе: --live (після «ок»).")

    # ───────── точні мітки ─────────

    def _exact_carry(self):
        from apps.crm.models import Deal, Lead
        from apps.inbox.models import Conversation
        o = self.out
        o("=== backfill_meta_likely_ad --exact-carry · %s · точні мітки, що не дійшли ===" % self.mode)
        now_iso = timezone.now().isoformat()

        # 1) угоди клієнтів, у ліда яких є перевірена мітка
        clicks = defaultdict(list)
        for lead in Lead.objects.filter(meta_attribution__source_kind__in=ma.EXACT_KINDS).exclude(contact_id=None):
            a = lead.meta_attribution or {}
            clicks[lead.contact_id].append((ma.click_time(a, lead.created_at), a, lead.id))
        rows = []
        skip = Counter()
        total = 0
        for chunk in _chunks(clicks.keys()):
            for d in (Deal.objects.filter(contact_id__in=chunk).select_related("stage").order_by("created_at")):
                cur = d.meta_attribution or {}
                if ma.is_exact(cur):
                    continue
                total += 1
                if d.stage.is_lost:
                    skip["програна"] += 1
                    continue
                ok = [(t, a, lid) for (t, a, lid) in clicks[d.contact_id]
                      if t <= d.created_at + ma.CLICK_BEFORE_TOLERANCE and t >= d.created_at - ma.INHERIT_WINDOW]
                if not ok:
                    later = any(t > d.created_at + ma.CLICK_BEFORE_TOLERANCE for (t, _a, _l) in clicks[d.contact_id])
                    skip["створена раніше за клік" if later else "клік старший за 30 днів"] += 1
                    continue
                t, a, lid = max(ok, key=lambda row: row[0])
                rows.append((d, t, a, lid))
        if self.limit:
            rows = rows[:self.limit]
        o("1) Угоди без мітки, хоча в ліда цього клієнта точна мітка є: %s" % total)
        o("   позначити: %s (відкритих %s, виграних %s на %s₴)" % (
            len(rows), sum(1 for r in rows if not r[0].stage.is_won), sum(1 for r in rows if r[0].stage.is_won),
            int(sum((r[0].amount or 0 for r in rows if r[0].stage.is_won), Decimal("0")))))
        o("   НЕ чіпаємо: " + (", ".join("%s — %s" % (k, v) for k, v in skip.most_common()) or "—"))
        written_d = 0
        for i, (d, t, a, lid) in enumerate(rows):
            if i < self.samples:
                o("   угода #%s (%s, створена %s) ← лід #%s · клік %s · оголошення %s" % (
                    d.id, _stage_word(d), _d(d.created_at), lid, _d(t), a.get("ad_title") or a.get("ad_id") or "—"))
            attr = ma.stamp_exact(dict(a), method=a.get("method") or "referral", at=t)
            attr.update(inherited_from="lead:%s" % lid, backfilled_at=now_iso)
            written_d += self._write(Deal, [d], attr, upgrade_likely=True)

        # 2) чати-коментарі під рекламою з ad_id, а в клієнта точної мітки ніде немає
        exact_ids = self._exact_contact_ids()
        convs = [c for c in (Conversation.objects.filter(config__source_card__is_ad=True).exclude(contact_id=None)
                             .select_related("channel").order_by("created_at"))
                 if ((c.config or {}).get("source_card") or {}).get("ad_id") and c.contact_id not in exact_ids]
        if self.limit:
            convs = convs[:self.limit]
        leads, deals = self._load({c.contact_id for c in convs})
        n_leads = n_deals = 0
        written_l2 = written_d2 = 0
        o("")
        o("2) Чати-коментарі під рекламою (ad_id від Meta), у клієнта мітки немає: %s" % len(convs))
        for i, conv in enumerate(convs):
            card = (conv.config or {}).get("source_card") or {}
            first_at = conv.created_at
            tl = [x for x in leads[conv.contact_id] if self._lead_ok(x, first_at, upgrade_likely=True)]
            td = [x for x in deals[conv.contact_id] if not self._deal_check(x, first_at, upgrade_likely=True)]
            n_leads += len(tl)
            n_deals += len(td)
            if i < self.samples:
                o("   чат #%s · %s · клієнт #%s · оголошення %s · ліди: %s · угоди: %s" % (
                    conv.id, _d(first_at), conv.contact_id, card.get("ad_id"),
                    ", ".join("#%s" % x.id for x in tl) or "—",
                    ", ".join("#%s (%s)" % (x.id, _stage_word(x)) for x in td) or "—"))
            attr = {"source_kind": "paid_ad", "platform": card.get("platform") or conv.channel.kind or "instagram",
                    "source_context": "comment_ad", "ad_id": str(card.get("ad_id"))[:180],
                    "content_id": str(card.get("media_id") or "")[:180], "class": ma.CLASS_EXACT,
                    "method": "comment_ad_backfill", "attributed_at": first_at.isoformat(),
                    "conversation_id": conv.id, "backfilled_at": now_iso}
            written_l2 += self._write(Lead, tl, attr, upgrade_likely=True)
            written_d2 += self._write(Deal, td, attr, upgrade_likely=True)
        o("   позначити: лідів %s, угод %s" % (n_leads, n_deals))
        o("")
        if self.live:
            o("[LIVE] записано: угод (п.1) %s; лідів (п.2) %s, угод (п.2) %s" % (written_d, written_l2, written_d2))
        else:
            o("DRY-RUN: нічого не записано. Перевірка на 1–2: --exact-carry --limit 1 --live.")
