# -*- coding: utf-8 -*-
"""22.09.2026 (Олег, тест «На 10 м давайте сразу»): Юля ChatPlace відповіла «Передала Ваш запрос менеджеру»,
а продавець CRM мовчав — він перевіряв передачу лише тоді, коли клієнт напише ЩЕ РАЗ.
Тепер щойно в чаті зʼявляється така відповідь Юлі (echo «ai_assistant»), продавець CRM одразу відповідає
на останнє повідомлення клієнта. Ті самі перевірки, що й завжди (should_reply): канал, менеджер у чаті, ліміт."""
import threading

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Message


@receiver(post_save, sender=Message, dispatch_uid="ai_handoff_after_yulia")
def after_yulia_handoff(sender, instance, created, **kwargs):
    if not created or instance.direction != "out" or instance.internal or instance.sender_name != "ai_assistant":
        return
    try:
        from .ai_reply import HANDOFF_RX, _maybe_effect_photos, _takeover_channel, channel_on, reply_now, should_reply
        # 23.09.2026 (Олег): «якщо мова про вибір кольору — одразу кілька фото, як це виглядає в інтерʼєрі,
        # а вже потім посилання». Юля в ChatPlace фото не надсилає — щойно вона дала сторінку кольорів,
        # фото в цей самий чат докидає CRM.
        if channel_on(instance.conversation.channel):
            _photos_after_link(instance)
        if not HANDOFF_RX.search(instance.text or ""):
            return
        conv = instance.conversation
        if not _takeover_channel(conv.channel):
            return
        incoming = (Message.objects.filter(conversation=conv, direction="in", internal=False, id__lt=instance.id)
                    .order_by("-id").first())
        if incoming is None or not should_reply(conv, incoming):
            return
        cid = conv.id   # після коміту — щоб потік бачив щойно записане повідомлення
        transaction.on_commit(lambda: threading.Thread(target=reply_now, args=(cid,), daemon=True).start())
    except Exception:
        pass


def _photos_after_link(msg):
    """Юля дала посилання на сторінку матеріалу → CRM надсилає 2-3 фото цього матеріалу в інтерʼєрі.
    Те саме, що робить продавець CRM у своїх відповідях (одне фото на ефект, один раз на діалог)."""
    from django.db import transaction
    from .ai_reply import _maybe_effect_photos, _manager_active, _limits
    try:
        conv = msg.conversation
        hours, _max = _limits()
        if _manager_active(conv, hours):
            return                      # менеджер у чаті — нічого не докидаємо
        text = msg.text or ""
        transaction.on_commit(lambda: _maybe_effect_photos(conv, text))
    except Exception:
        pass
