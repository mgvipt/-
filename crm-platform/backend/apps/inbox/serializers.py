from rest_framework import serializers
from .models import Channel, Conversation, Message


class ChannelSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Channel
        # config с секретами наружу не отдаём
        fields = ["id", "kind", "kind_display", "name", "is_active", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    attachments = serializers.SerializerMethodField()
    sender_display = serializers.SerializerMethodField()

    def get_sender_display(self, obj):
        """Людяне імʼя автора вихідного повідомлення.
        - CRM-користувач (sender_id) → його повне імʼя;
        - ChatPlace 'operator'/'manager'/'admin' → 'Менеджер · ChatPlace' (ChatPlace НЕ передає імʼя людини);
        - 'ai_assistant'/'bot' → ШІ;
        - вхідне без імені → імʼя/нік контакта діалогу (клієнт — автор вхідного),
          а не заглушка каналу «instagram»."""
        sn = (obj.sender_name or "").strip()
        if sn == "ai_assistant":
            return "Юля (AI)"
        if sn == "bot":
            return "Бот"
        if sn.lower() in ("operator", "manager", "admin", "system", "out"):
            # ChatPlace-«operator» не несе імʼя людини; якщо є CRM-користувач — показати його
            if obj.sender_id and obj.sender:
                return obj.sender.get_full_name() or obj.sender.username
            return "Менеджер · ChatPlace"
        if sn:
            return sn  # реальне збережене імʼя (Кирилл Оксаненко / Илона тощо)
        if obj.sender_id and obj.sender:
            return obj.sender.get_full_name() or obj.sender.username
        # вхідне повідомлення без імені автора → показуємо КЛІЄНТА діалогу
        # (Meta пише вхідні з порожнім sender_name; заголовок діалогу = «instagram»,
        # тож без цього фронт підставляв слово каналу замість імені людини)
        if obj.direction == "in":
            conv = getattr(obj, "conversation", None)
            ct = getattr(conv, "contact", None) if conv else None
            if ct:
                nm = (ct.first_name or "").strip()
                bad = nm.lower() in ("instagram", "facebook", "tiktok", "telegram", "viber", "whatsapp")
                if nm and not bad and not nm.isdigit():
                    return (nm + " " + (ct.last_name or "").strip()).strip()
                nick = (getattr(ct, "nickname", "") or "").strip()
                if nick:
                    return "@" + nick
        return ""

    def get_attachments(self, obj):
        from apps.inbox.views import _tg_sig
        out = []
        for i, a in enumerate(obj.attachments or []):
            a = dict(a)
            if a.get("file_id") and not a.get("url"):
                a["url"] = "/api/inbox/tg-file/%s/%s/?s=%s" % (obj.id, i, _tg_sig(obj.id, i))
            out.append(a)
        return out

    class Meta:
        model = Message
        fields = ["id", "conversation", "direction", "text", "internal", "attachments",
                  "sender_name", "sender_display", "created_at", "status"]
        read_only_fields = ["direction", "sender_name", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    channel_kind = serializers.CharField(source="channel.kind", read_only=True)
    channel_name = serializers.CharField(source="channel.name", read_only=True)
    contact_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    last_text = serializers.SerializerMethodField()
    needs_reply = serializers.SerializerMethodField()
    ai_answered = serializers.SerializerMethodField()
    deal_stage = serializers.SerializerMethodField()
    deal_id = serializers.SerializerMethodField()
    participant_names = serializers.SerializerMethodField()
    unhandled_in = serializers.SerializerMethodField()
    source_card = serializers.SerializerMethodField()

    def get_source_card(self, obj):
        """Картка джерела для комент-чатів Meta (публікація/ролик/реклама, на яку відповів клієнт)."""
        cfg = getattr(obj, "config", None) or {}
        return cfg.get("source_card") or None

    def get_contact_name(self, obj):
        if not obj.contact:
            return obj.title or ""
        base = str(obj.contact).strip()
        nick = (getattr(obj.contact, "nickname", "") or "").strip()
        # «Ім'я Прізвище (@нік)» — і повне ім'я, і нікнейм клієнта у заголовку чату
        if nick and nick.lower() not in base.lower():
            return f"{base} (@{nick})" if base else f"@{nick}"
        return base

    def get_participant_names(self, obj):
        return [(u.get_full_name() or u.username) for u in obj.participants.all()]

    def _cm(self, obj):
        return (self.context.get("conv_meta") or {}).get(obj.id)

    def _deal(self, obj):
        if not obj.contact_id:
            return None
        cm = self._cm(obj)
        if cm is not None and "deal" in cm:
            return cm.get("deal")
        if not hasattr(obj, "_cached_deal"):
            obj._cached_deal = obj.contact.deals.select_related("stage").order_by("-updated_at").first()
        return obj._cached_deal

    def get_deal_stage(self, obj):
        d = self._deal(obj)
        return (d.stage.name if d and d.stage else "") if d else ""

    def get_deal_id(self, obj):
        d = self._deal(obj)
        return d.id if d else None

    def get_assigned_to_name(self, obj):
        if not obj.assigned_to:
            return ""
        return obj.assigned_to.get_full_name() or obj.assigned_to.username

    class Meta:
        model = Conversation
        fields = ["id", "channel", "channel_kind", "channel_name", "contact",
                  "contact_name", "title", "status", "assigned_to", "assigned_to_name",
                  "unread", "last_message_at", "last_text", "needs_reply", "ai_answered", "unhandled_in", "participants", "participant_names", "priority", "priority_reason", "deal_stage", "deal_id", "source_card"]

    def _last(self, obj):
        """Останнє повідомлення (з пакетного meta або 1 запит fallback)."""
        cm = self._cm(obj)
        if cm is not None:
            return cm.get("last")
        m = obj.messages.last()
        if not m:
            return None
        return {"direction": m.direction, "sender_id": m.sender_id,
                "sender_name": m.sender_name, "internal": m.internal, "text": m.text}

    def get_last_text(self, obj):
        m = self._last(obj)
        return (m or {}).get("text") or ""

    def get_needs_reply(self, obj):
        # останнє вхідне АБО вручну позначено неотвеченим (unread>0)
        m = self._last(obj)
        return bool((m and m.get("direction") == "in") or (obj.unread or 0) > 0)

    def get_ai_answered(self, obj):
        """Останнє повідомлення — від ШІ-агента (Юля/бот)."""
        m = self._last(obj)
        return bool(m and m.get("direction") == "out" and m.get("sender_id") is None
                    and not m.get("internal") and (m.get("sender_name") or "") in ("ai_assistant", "bot"))

    def get_unhandled_in(self, obj):
        """Повідомлень клієнта без відповіді ЖИВОГО менеджера (число в червоному кружку)."""
        cm = self._cm(obj)
        if cm is not None:
            return cm.get("unhandled_in", 0)
        from django.db.models import Q as _Q
        human = _Q(sender__isnull=False) | _Q(sender_name__in=("operator", "manager", "admin"))
        last_human = (obj.messages.filter(direction="out", internal=False)
                      .filter(human).order_by("-id").values_list("id", flat=True).first())
        q = obj.messages.filter(direction="in")
        if last_human:
            q = q.filter(id__gt=last_human)
        return q.count()
