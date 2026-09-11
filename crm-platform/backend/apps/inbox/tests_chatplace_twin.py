"""Регресія 11.09: Instagram-клієнт не повинен записуватись як TikTok через тезку в TikTok.

ChatPlace не віддає платформу, синк вгадував її по ніку (TikTok oembed «акаунт існує»).
Ніки в IG і TikTok часто збігаються → IG-клієнт отримував другий контакт/лід у каналі
«ChatPlace · TikTok», а відповідь менеджера туди не доходила (@boris462, @shilko74, @svitlana7736).
"""
import datetime
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.crm.models import Contact
from apps.inbox import chatplace
from apps.inbox.models import Channel, Conversation

CP_ID = "cp-chat-boris"


def _fake_mcp(items):
    def _call(name, args=None):
        if name == "chats_list":
            return {"items": items}
        if name == "chats_messages":
            return {"items": []}
        return {}
    return _call


class ChatPlaceInstagramTwinTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.meta_ig = Channel.objects.create(
            kind="instagram", name="Meta · instagram", config={"meta": True, "platform": "instagram"})
        self.ig_contact = Contact.objects.create(first_name="boris462", nickname="boris462",
                                                 social_link="https://instagram.com/boris462")
        self.ig_conv = Conversation.objects.create(
            channel=self.meta_ig, contact=self.ig_contact, title="instagram · коментар",
            external_chat_id="comment:instagram:post-1:boris462")
        Conversation.objects.filter(pk=self.ig_conv.pk).update(last_message_at=self.now)

    def _item(self, name="@boris462", seconds_after=-16):
        return {"id": CP_ID, "clientName": name,
                "lastMessageAt": int(self.now.timestamp()) + seconds_after}

    def _tiktok_convs(self):
        return Conversation.objects.filter(channel__name="ChatPlace · TikTok", external_chat_id=CP_ID)

    @patch("apps.inbox.chatplace._tt_exists", return_value=True)   # тезка в TikTok існує
    def test_fresh_meta_twin_is_not_created_as_tiktok(self, _tt):
        with patch("apps.inbox.chatplace._mcp", side_effect=_fake_mcp([self._item()])):
            chatplace.sync_chats()
        self.assertFalse(self._tiktok_convs().exists())
        self.assertFalse(Contact.objects.filter(social_link="https://www.tiktok.com/@boris462").exists())
        _tt.assert_not_called()   # до oembed навіть не доходимо — двійник знайдений у своїй базі

    @patch("apps.inbox.chatplace._tt_exists", return_value=True)
    def test_real_tiktok_without_meta_twin_still_created(self, _tt):
        with patch("apps.inbox.chatplace._mcp", side_effect=_fake_mcp([self._item(name="@real_tiktoker")])):
            chatplace.sync_chats()
        self.assertEqual(self._tiktok_convs().count(), 1)

    @patch("apps.inbox.chatplace._tt_exists", return_value=True)
    def test_stale_meta_contact_does_not_hide_real_tiktoker(self, _tt):
        # Той самий нік, але в Instagram писав 10 днів тому — не поруч у часі → не двійник.
        Conversation.objects.filter(pk=self.ig_conv.pk).update(
            last_message_at=self.now - datetime.timedelta(days=10))
        with patch("apps.inbox.chatplace._mcp", side_effect=_fake_mcp([self._item()])):
            chatplace.sync_chats()
        self.assertEqual(self._tiktok_convs().count(), 1)

    @patch("apps.inbox.chatplace._tt_exists", return_value=True)
    def test_existing_tiktok_chat_is_left_untouched(self, _tt):
        tt = Channel.objects.create(kind="tiktok", name="ChatPlace · TikTok", config={"chatplace": True})
        Conversation.objects.create(channel=tt, external_chat_id=CP_ID, title="@boris462")
        with patch("apps.inbox.chatplace._mcp", side_effect=_fake_mcp([self._item()])):
            chatplace.sync_chats()
        self.assertEqual(self._tiktok_convs().count(), 1)   # існуючі не переносимо і не видаляємо

    def test_twin_match_is_exact_nick_only(self):
        ts = int(self.now.timestamp())
        self.assertTrue(chatplace._meta_ig_twin("@Boris462", ts))   # регістр і @ не заважають
        self.assertFalse(chatplace._meta_ig_twin("boris46", ts))    # частковий збіг — НІ
        self.assertFalse(chatplace._meta_ig_twin("boris462", None)) # без часу чату — НІ
