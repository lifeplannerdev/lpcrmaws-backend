from rest_framework import serializers
from .models import Conversation, Message
from django.contrib.auth import get_user_model

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "role"]


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer()
    file = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "sender", "text", "file", "created_at"]

    def get_file(self, obj):
        if obj.file:
            name = obj.file.name
            if name and ('raw/upload/' in name or 'image/upload/' in name):
                return f"https://res.cloudinary.com/dzmvrjvfs/{name}"
            return obj.file.url
        return None


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
        return MessageSerializer(last).data