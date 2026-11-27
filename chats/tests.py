from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Conversation, Message

User = get_user_model()


class ChatReplyToMessageTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="Password123!")
        self.bob = User.objects.create_user(username="bob", password="Password123!")
        self.charlie = User.objects.create_user(username="charlie", password="Password123!")

        self.conv = Conversation.objects.create(type="DIRECT", created_by=self.alice)
        self.conv.participants.add(self.alice, self.bob)

        self.other_conv = Conversation.objects.create(type="DIRECT", created_by=self.alice)
        self.other_conv.participants.add(self.alice, self.charlie)

        self.msg_a = Message.objects.create(
            conversation=self.conv,
            sender=self.alice,
            text="Original message A",
        )
        self.other_msg = Message.objects.create(
            conversation=self.other_conv,
            sender=self.charlie,
            text="Secret message in other conversation",
        )

    @patch("chats.views.notify_new_message")
    def test_send_message_with_reply_to_succeeds_and_notifies(self, mock_notify):
        self.client.force_authenticate(user=self.bob)
        res = self.client.post(
            reverse("send-message"),
            {
                "conversation_id": self.conv.id,
                "text": "Replying to A",
                "reply_to": self.msg_a.id,
                "client_id": "opt-123",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertIsNotNone(data["reply_to"])
        self.assertEqual(data["reply_to"]["id"], self.msg_a.id)
        self.assertEqual(data["reply_to"]["sender"]["id"], self.alice.id)
        self.assertEqual(data["reply_to"]["sender"]["username"], "alice")
        self.assertEqual(data["reply_to"]["text"], "Original message A")
        self.assertIsNone(data["reply_to"]["file"])
        self.assertIn("created_at", data["reply_to"])

        mock_notify.assert_called_once()
        conv_arg, payload_arg = mock_notify.call_args[0]
        self.assertEqual(conv_arg, self.conv.id)
        self.assertEqual(payload_arg["reply_to"]["id"], self.msg_a.id)

    def test_message_list_includes_reply_to(self):
        reply_msg = Message.objects.create(
            conversation=self.conv,
            sender=self.bob,
            text="Reply B",
            reply_to=self.msg_a,
        )
        self.client.force_authenticate(user=self.alice)
        res = self.client.get(reverse("message-list", args=[self.conv.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.json()
        by_id = {m["id"]: m for m in items}
        self.assertIsNone(by_id[self.msg_a.id]["reply_to"])
        self.assertEqual(by_id[reply_msg.id]["reply_to"]["id"], self.msg_a.id)
        self.assertEqual(by_id[reply_msg.id]["reply_to"]["text"], "Original message A")

    @patch("chats.views.notify_new_message")
    def test_reply_to_reply_does_not_nest_recursively(self, _mock_notify):
        msg_b = Message.objects.create(
            conversation=self.conv,
            sender=self.bob,
            text="Reply B",
            reply_to=self.msg_a,
        )
        self.client.force_authenticate(user=self.alice)
        res = self.client.post(
            reverse("send-message"),
            {
                "conversation_id": self.conv.id,
                "text": "Reply C",
                "reply_to": msg_b.id,
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["reply_to"]["id"], msg_b.id)
        self.assertNotIn("reply_to", data["reply_to"])

    @patch("chats.views.notify_new_message")
    def test_reply_to_message_in_other_conversation_rejected(self, mock_notify):
        self.client.force_authenticate(user=self.alice)
        initial_count = Message.objects.filter(conversation=self.conv).count()
        res = self.client.post(
            reverse("send-message"),
            {
                "conversation_id": self.conv.id,
                "text": "Cross-conv leak attempt",
                "reply_to": self.other_msg.id,
            },
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Message.objects.filter(conversation=self.conv).count(), initial_count)
        mock_notify.assert_not_called()

    @patch("chats.views.notify_new_message")
    def test_reply_to_invalid_or_nonexistent_id_rejected(self, mock_notify):
        self.client.force_authenticate(user=self.alice)
        for bad_id in ("abc", 999999):
            res = self.client.post(
                reverse("send-message"),
                {
                    "conversation_id": self.conv.id,
                    "text": "Bad reply target",
                    "reply_to": bad_id,
                },
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        mock_notify.assert_not_called()

    @patch("utils.pusher.notify_message_deleted")
    def test_deleting_parent_message_sets_reply_to_null(self, mock_deleted):
        reply_msg = Message.objects.create(
            conversation=self.conv,
            sender=self.bob,
            text="Still here after parent delete",
            reply_to=self.msg_a,
        )
        self.client.force_authenticate(user=self.alice)
        del_res = self.client.delete(reverse("delete-message", args=[self.msg_a.id]))
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        mock_deleted.assert_called_once_with(self.conv.id, self.msg_a.id)

        reply_msg.refresh_from_db()
        self.assertIsNone(reply_msg.reply_to)

        list_res = self.client.get(reverse("message-list", args=[self.conv.id]))
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        items = list_res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], reply_msg.id)
        self.assertIsNone(items[0]["reply_to"])

    @patch("chats.views.notify_new_message")
    def test_reply_to_file_only_message(self, _mock_notify):
        uploaded = SimpleUploadedFile("notes.txt", b"hello file", content_type="text/plain")
        file_msg = Message.objects.create(
            conversation=self.conv,
            sender=self.alice,
            text=None,
            file=uploaded,
        )
        self.client.force_authenticate(user=self.bob)
        res = self.client.post(
            reverse("send-message"),
            {
                "conversation_id": self.conv.id,
                "text": "Got your file",
                "reply_to": file_msg.id,
            },
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["reply_to"]["id"], file_msg.id)
        self.assertIsNone(data["reply_to"]["text"])
        self.assertTrue(data["reply_to"]["file"])

    @patch("chats.views.notify_new_message")
    def test_send_message_without_reply_to_backwards_compatible(self, _mock_notify):
        self.client.force_authenticate(user=self.alice)
        res_omitted = self.client.post(
            reverse("send-message"),
            {"conversation_id": self.conv.id, "text": "Plain message"},
        )
        self.assertEqual(res_omitted.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(res_omitted.json()["reply_to"])

        res_empty = self.client.post(
            reverse("send-message"),
            {"conversation_id": self.conv.id, "text": "Empty reply_to", "reply_to": ""},
        )
        self.assertEqual(res_empty.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(res_empty.json()["reply_to"])
