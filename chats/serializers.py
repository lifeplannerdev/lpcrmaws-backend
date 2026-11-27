from rest_framework import serializers
from .models import Conversation, Message
from django.contrib.auth import get_user_model

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "role", "is_active"]

    def get_role(self, obj):
        first_role = obj.db_roles.first()
        return first_role.name if first_role else (obj.team or "")


def _get_message_file_url(obj, context):
    if obj.file:
        request = context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url
    return None


class ReplyToMessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    file = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "sender", "text", "file", "created_at"]

    def get_file(self, obj):
        return _get_message_file_url(obj, self.context)


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer()
    file = serializers.SerializerMethodField()
    reply_to = ReplyToMessageSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ["id", "client_id", "sender", "text", "file", "reply_to", "delivered_to", "read_by", "created_at"]

    def get_file(self, obj):
        return _get_message_file_url(obj, self.context)


class ConversationSerializer(serializers.ModelSerializer):
    participants = UserSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ["id", "type", "name", "participants", "last_message", "created_by"]

    def get_last_message(self, obj):
        # Uses prefetched messages — no extra DB query
        prefetched = obj.messages.all()
        if not prefetched:
            return None
        # Get the latest from already-fetched queryset (sorted in view)
        last = prefetched[0]
        return MessageSerializer(last, context=self.context).data