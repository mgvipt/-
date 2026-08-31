from rest_framework import serializers
from .models import Company, Contact, Funnel, Stage, Lead, Deal, DealItem, Payment, AutomationRule, GlobalRule, Task


class DealItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    product_stock = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    room_name = serializers.SerializerMethodField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    def get_room_name(self, obj):
        return obj.room.name if obj.room_id else ""

    def get_unit(self, obj):
        """Одиниця виміру З НОМЕНКЛАТУРИ (щоб у накладній було те саме, що в картці товару)."""
        return (getattr(obj.product, "unit", "") or "шт") if obj.product_id else "шт"

    def get_product_name(self, obj):
        if obj.product_id:
            return obj.product.name
        return (obj.custom_name or "Позиція") + " · не зі складу"

    def get_product_stock(self, obj):
        if not obj.product_id:
            return None
        st = obj.product.stock
        return st() if callable(st) else st

    class Meta:
        model = DealItem
        fields = ["room", "room_name", "unit", "id", "deal", "product", "custom_name", "product_name", "product_stock", "quantity", "price", "cost", "discount_pct", "discount_amount", "discount_sum", "total", "reserved"]
        read_only_fields = ["deal"]


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = "__all__"


class ContactSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True, default="")
    meta_ad = serializers.SerializerMethodField()   # з якого оголошення прийшов клієнт (для чату)

    class Meta:
        model = Contact
        fields = ["id", "first_name", "last_name", "middle_name", "nickname", "display_name", "phone",
                  "email", "social_link", "messengers", "company", "channels", "loyalty_tag", "birthday",
                  "source", "address", "comment", "edrpou", "iban", "owner", "owner_name", "created_at",
                  "kinds", "gender", "monitor_docs", "doc_email", "default_purchase_category", "payment_purpose",
                  "emails_extra", "phones_extra", "links_extra", "accounts", "monitor_emails", "meta_ad", "advance_adjust", "advance_adjust_note", "expense_adjust", "expense_adjust_note"]

    def get_display_name(self, obj):
        return str(obj)

    def get_meta_ad(self, obj):
        """Реклама, з якої прийшов цей клієнт — беремо з його ліда або сделки.
        Потрібно менеджеру/агенту в чаті: одразу видно, на ЯКИЙ продукт відгукнулись
        (напр. «Галатея»), бо ChatPlace рекламний контекст не передає."""
        try:
            for model_name in ("leads", "deals"):
                rel = getattr(obj, model_name, None)
                if rel is None:
                    continue
                for row in rel.all().order_by("-id")[:6]:
                    card = _resolve_meta_ad(getattr(row, "meta_attribution", None))
                    if card:
                        return card
        except Exception:
            pass
        return None


class ContactDetailSerializer(ContactSerializer):
    """Картка клієнта: + історія сделок + сумарні витрати."""
    deals = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()
    zamer_projects = serializers.SerializerMethodField()

    class Meta(ContactSerializer.Meta):
        fields = ContactSerializer.Meta.fields + ["deals", "total_spent", "zamer_projects"]

    def get_zamer_projects(self, obj):
        """Только проекты замера выбранного клиента, без данных других клиентов."""
        from .models import ZamerProject
        # Связь с клиентом проверяет endpoint при сохранении. Не доверяем
        # clientId внутри JSON: старый payload мог быть неполным или смешанным.
        rows = (ZamerProject.objects.filter(contact=obj)
                .order_by("-updated_at")[:50])
        return [{
            "project_uuid": row.project_uuid,
            "title": row.title,
            "payload": row.payload,
            "updated_at": row.updated_at,
        } for row in rows]

    def get_deals(self, obj):
        out = []
        for d in obj.deals.select_related("stage").prefetch_related("items", "items__product").order_by("-created_at")[:50]:
            _cost = 0.0
            for _it in d.items.all():
                _cu = _it.cost if (_it.cost or 0) > 0 else (getattr(_it.product, "cost", 0) or 0)
                try:
                    _cost += float(_it.quantity or 0) * float(_cu or 0)
                except Exception:
                    pass
            out.append({"id": d.id, "title": d.title, "amount": float(d.amount),
                        "stage": d.stage.name if d.stage else "", "is_won": d.stage.is_won if d.stage else False,
                        "cost": round(_cost, 2), "created_at": d.created_at})
        return out

    def get_total_spent(self, obj):
        # «Купив у магазині» = сума сделок, які РЕАЛЬНО куплені: виграні АБО оплачені
        from django.db.models import Sum, Q
        from .models import Deal
        _ids = list(obj.deals.filter(Q(stage__is_won=True) | Q(payments__is_paid=True)).values_list("id", flat=True).distinct())
        return float(Deal.objects.filter(id__in=_ids).aggregate(s=Sum("amount"))["s"] or 0)


class StageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stage
        fields = ["id", "funnel", "name", "color", "order", "is_won", "is_lost", "auto_only"]


class FunnelSerializer(serializers.ModelSerializer):
    stages = StageSerializer(many=True, read_only=True)

    class Meta:
        model = Funnel
        fields = ["id", "name", "is_lead_funnel", "is_archive", "order", "stages"]


def _resolve_meta_ad(attr):
    """Читабельна картка джерела реклами з meta_attribution ліда/угоди.
    Резолвить ad_id → назву кампанії/оголошення з уже синхронізованої статистики
    (MetaAdDailyStat), додає назву та мініатюру креативу з referral. None — якщо це
    не платний клік (щоб фронт не малював плашку органіці)."""
    if not isinstance(attr, dict) or attr.get("source_kind") != "paid_ad":
        return None
    ad_id = str(attr.get("ad_id") or "")
    campaign = ad_name = permalink = ""
    if ad_id:
        from .models import MetaAdDailyStat
        row = (MetaAdDailyStat.objects.filter(ad_id=ad_id).exclude(campaign_name="").order_by("-date").first()
               or MetaAdDailyStat.objects.filter(ad_id=ad_id).order_by("-date").first())
        if row:
            campaign = row.campaign_name or ""
            ad_name = row.ad_name or ""
            permalink = getattr(row, "permalink_url", "") or ""
    return {
        "platform": attr.get("platform", ""),
        "ad_id": ad_id,
        "campaign": campaign,
        "ad_name": ad_name,
        "title": attr.get("ad_title", ""),
        "thumb": attr.get("ad_thumb", ""),
        "ref": attr.get("ad_ref", ""),
        "permalink": permalink,
    }


class LeadSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True)
    contact_name = serializers.SerializerMethodField()
    contact_social_link = serializers.CharField(source="contact.social_link", read_only=True, default="")
    contact_phone = serializers.CharField(source="contact.phone", read_only=True, default="")
    meta_ad = serializers.SerializerMethodField()
    conversation_id = serializers.SerializerMethodField()

    def get_contact_name(self, obj):
        return str(obj.contact) if obj.contact else ""

    def get_meta_ad(self, obj):
        return _resolve_meta_ad(obj.meta_attribution)

    def get_conversation_id(self, obj):
        if not obj.contact_id:
            return None
        from apps.inbox.models import Conversation
        c = Conversation.objects.filter(contact=obj.contact).order_by("-last_message_at").first()
        return c.id if c else None

    class Meta:
        model = Lead
        fields = ["id", "title", "contact", "contact_name", "funnel", "stage",
                  "source", "amount", "is_seen", "qualification", "card_fields", "meta_attribution", "meta_ad", "contact_social_link", "contact_phone", "owner", "owner_name", "conversation_id",
                  "created_at", "updated_at"]
        read_only_fields = ["meta_attribution"]


class DealSerializer(serializers.ModelSerializer):
    parent_deal_title = serializers.CharField(source="parent_deal.title", read_only=True, default=None)
    funnel_name = serializers.SerializerMethodField()
    contact_social_link = serializers.CharField(source="contact.social_link", read_only=True, default="")
    contact_phone = serializers.CharField(source="contact.phone", read_only=True, default="")
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True)
    contact_name = serializers.SerializerMethodField()
    meta_ad = serializers.SerializerMethodField()

    def get_contact_name(self, obj):
        return str(obj.contact) if obj.contact else ""

    def get_funnel_name(self, obj):
        return obj.funnel.name if obj.funnel_id else ""

    def get_meta_ad(self, obj):
        return _resolve_meta_ad(obj.meta_attribution)

    class Meta:
        model = Deal
        fields = ["area_m2", "id", "title", "contact", "contact_name", "contact_social_link", "contact_phone", "funnel", "funnel_name", "stage",
                  "source", "amount", "discount_pct", "pay_type", "ttn", "checkbox_status", "checkbox_url", "checkbox_relation_id", "parent_deal", "parent_deal_title",
                  "qualification", "card_fields", "meta_attribution", "meta_ad", "owner", "owner_name", "closed_at", "is_seen",
                  "created_at", "updated_at"]
        read_only_fields = ["meta_attribution"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"


class DealDetailSerializer(DealSerializer):
    """Расширенная карточка сделки: товары, оплаты, оплачено/осталось + маржа/бонус/лояльность."""
    items = DealItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    paid = serializers.SerializerMethodField()
    margin = serializers.SerializerMethodField()
    bonus = serializers.SerializerMethodField()
    days_in_stage = serializers.SerializerMethodField()
    contact_loyalty = serializers.SerializerMethodField()
    contact_id = serializers.IntegerField(source="contact.id", read_only=True)
    conversation_id = serializers.SerializerMethodField()
    responsible_display = serializers.SerializerMethodField()
    pay_method = serializers.SerializerMethodField()

    def get_responsible_display(self, obj):
        # Ответственный для карточки: имя менеджера, иначе «ІІ (Юля)» если вёл только ИИ.
        if obj.owner_id:
            return obj.owner.get_full_name() or obj.owner.username
        if obj.contact_id:
            from apps.inbox.models import Conversation, Message
            if Conversation.objects.filter(contact_id=obj.contact_id, assigned_to__isnull=False).exists():
                return ""
            if Message.objects.filter(conversation__contact_id=obj.contact_id, sender_name="ai_assistant").exists():
                return "ІІ (Юля)"
        return ""
    realization = serializers.SerializerMethodField()
    linked_orders = serializers.SerializerMethodField()

    def get_realization(self, obj):
        """Документ реалізації (списання товару) по угоді — для блоку проведення/скасування у картці."""
        from apps.warehouse.models import StockDocument
        doc = StockDocument.objects.filter(kind="out", deal=obj).order_by("-id").first()
        if not doc:
            return None
        return {"id": doc.id, "number": doc.number, "posted": doc.posted,
                "total": float(doc.total), "created_at": doc.created_at, "close_stage": doc.close_stage}

    def get_pay_method(self, obj):
        paid = [p for p in obj.payments.all() if p.is_paid]
        if paid:
            return sorted(paid, key=lambda p: -p.id)[0].provider
        from .models import PayLink
        if PayLink.objects.filter(deal=obj).exists():
            return "liqpay"
        return ""

    def get_conversation_id(self, obj):
        if not obj.contact_id:
            return None
        from apps.inbox.models import Conversation
        c = Conversation.objects.filter(contact=obj.contact).order_by("-last_message_at").first()
        return c.id if c else None

    class Meta(DealSerializer.Meta):
        fields = DealSerializer.Meta.fields + ["responsible_display", 
            "items", "payments", "paid", "margin", "bonus",
            "days_in_stage", "contact_loyalty", "contact_id", "conversation_id", "b24_id", "pay_method",
            "np_data", "np_delivery_date", "ref_photos", "kp_history", "realization", "linked_orders",
        ]

    def get_linked_orders(self, obj):
        """Дозамовлення (одна посилка): родитель + дети без ТТН, кроме себя."""
        from apps.crm.models import Deal
        root = obj.parent_deal or obj
        ids = set([root.id]) | set(root.children.values_list("id", flat=True))
        ids.discard(obj.id)
        if not ids:
            return []
        res = []
        for d in Deal.objects.filter(id__in=ids).prefetch_related("payments", "items"):
            if d.ttn:
                continue
            paid = float(sum(p.amount for p in d.payments.all() if p.is_paid))
            res.append({"id": d.id, "title": d.title, "amount": float(d.amount or 0),
                        "paid": paid, "remaining": max(0.0, float(d.amount or 0) - paid),
                        "items_n": d.items.count()})
        return res

    def get_paid(self, obj):
        return float(sum(p.amount for p in obj.payments.all() if p.is_paid))

    def get_margin(self, obj):
        # Маржа = выручка по строкам − себестоимость (cost товара). Без товаров — оценка 35%.
        items = list(obj.items.all())
        if not items:
            return round(float(obj.amount) * 0.35, 2)
        revenue = float(sum(i.total for i in items))
        cogs = float(sum(
            float(i.quantity) * float((i.cost if (i.cost or 0) > 0 else getattr(i.product, "cost", 0)) or 0)
            for i in items))  # снимок себестоимости на момент продажи; fallback — живой cost (старые строки)
        return round(revenue - cogs, 2)

    def get_bonus(self, obj):
        # Бонус менеджера з цієї угоди = % обороту + % маржі (ставки з Фінмоделі, синхронно).
        from apps.finance.services import deal_manager_bonus
        return deal_manager_bonus(obj.amount, self.get_margin(obj))

    def get_days_in_stage(self, obj):
        from django.utils import timezone
        base = obj.stage_changed_at or obj.created_at
        return (timezone.now() - base).days

    def get_contact_loyalty(self, obj):
        return getattr(obj.contact, "loyalty_tag", "") if obj.contact else ""


class AutomationRuleSerializer(serializers.ModelSerializer):
    from_stage_name = serializers.CharField(source="from_stage.name", read_only=True)
    to_stage_name = serializers.CharField(source="to_stage.name", read_only=True)
    trigger_display = serializers.CharField(source="get_trigger_display", read_only=True)
    funnel_name = serializers.CharField(source="funnel.name", read_only=True)

    class Meta:
        model = AutomationRule
        fields = ["id", "funnel", "funnel_name", "from_stage", "from_stage_name", "to_stage",
                  "to_stage_name", "trigger", "trigger_display", "enabled", "entry_conditions",
                  "actions", "description", "delay_hours", "note_to_staff"]


class GlobalRuleSerializer(serializers.ModelSerializer):
    block_display = serializers.CharField(source="get_block_display", read_only=True)

    class Meta:
        model = GlobalRule
        fields = ["id", "block", "block_display", "title", "body", "funnel", "priority", "enabled", "updated_at"]


class TaskSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default="")
    assignee_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    contact_name = serializers.SerializerMethodField()
    conversation_title = serializers.CharField(source="conversation.title", read_only=True, default="")
    deal_title = serializers.CharField(source="deal.title", read_only=True, default="")
    lead_title = serializers.CharField(source="lead.title", read_only=True, default="")
    bucket = serializers.SerializerMethodField()

    def _uname(self, u):
        return (u.get_full_name() or u.username) if u else ""

    def get_assignee_name(self, obj):
        return self._uname(obj.assignee)

    def get_created_by_name(self, obj):
        return self._uname(obj.created_by)

    def get_contact_name(self, obj):
        if not obj.contact_id:
            return ""
        c = obj.contact
        return (" ".join(x for x in (c.first_name, c.last_name) if x) or c.phone or c.email or "")[:80]

    def get_bucket(self, obj):
        """Канбан-колонка: today | week | later | done"""
        from django.utils import timezone as _tz
        if obj.status in ("done", "canceled"):
            return "done"
        if not obj.due_at:
            return "later"
        now = _tz.now()
        end_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        # межа тижня = 6 днів вперед (сьогодні + 6 = 7 днів вікна)
        from datetime import timedelta
        end_week = end_today + timedelta(days=6)
        if obj.due_at <= end_today:
            return "today"
        if obj.due_at <= end_week:
            return "week"
        return "later"

    class Meta:
        model = Task
        fields = ["id", "kind", "kind_display", "title", "body",
                  "priority", "priority_display",
                  "deal", "deal_title", "lead", "lead_title",
                  "contact", "contact_name",
                  "conversation", "conversation_title",
                  "department", "department_name",
                  "assignee", "assignee_name",
                  "created_by", "created_by_name",
                  "status", "status_display",
                  "due_at", "created_by_agent", "created_at", "bucket"]
        read_only_fields = ["created_by", "created_at", "created_by_agent"]


class KbEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = __import__("apps.crm.models", fromlist=["KbEntry"]).KbEntry
        fields = ["id", "ext_id", "question", "answer", "specific_rules", "source",
                  "client_chat_count", "tags", "enabled", "created_at", "updated_at"]
        read_only_fields = ["ext_id", "client_chat_count", "created_at", "updated_at"]


class KbUnknownQuestionSerializer(serializers.ModelSerializer):
    answer_preview = serializers.SerializerMethodField()

    class Meta:
        model = __import__("apps.crm.models", fromlist=["KbUnknownQuestion"]).KbUnknownQuestion
        fields = ["id", "ext_id", "question", "status", "source", "answer_entry",
                  "answer_preview", "times_asked", "created_at", "updated_at"]
        read_only_fields = ["ext_id", "created_at", "updated_at"]

    def get_answer_preview(self, obj):
        return (obj.answer_entry.answer[:120] if obj.answer_entry_id and obj.answer_entry else "")


class DealRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = __import__("apps.crm.models", fromlist=["DealRoom"]).DealRoom
        fields = ["id", "deal", "name", "area_m2", "order"]
        read_only_fields = ["deal"]
