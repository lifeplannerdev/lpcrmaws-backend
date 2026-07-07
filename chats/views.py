from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Prefetch

from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer
from utils.pusher import pusher_client
from utils import notify_new_message, notify_new_conversation

User = get_user_model()


#  Conversation List
class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Conversation.objects.filter(
            participants=request.user
        ).prefetch_related(
            "participants",
            Prefetch("messages", queryset=Message.objects.order_by("-created_at"))
        ).order_by("-created_at")

        serializer = ConversationSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


#  Message List
class MessageListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            participants=request.user
        )

        messages = Message.objects.filter(
            conversation=conversation
        ).select_related("sender").order_by("created_at")

        serializer = MessageSerializer(messages, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


#  Send Message
class SendMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        conversation_id = request.data.get("conversation_id")
        text = request.data.get("text", "").strip()
        file = request.FILES.get("file")

        if not conversation_id or not str(conversation_id).isdigit():
            return Response(
                {"error": "Valid conversation_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not text and not file:
            return Response(
                {"error": "Message must have text or a file"},
                status=status.HTTP_400_BAD_REQUEST
            )

        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            participants=request.user
        )

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            text=text or None,
            file=file
        )

        # Re-fetch with sender to avoid N+1
        message = Message.objects.select_related("sender").get(id=message.id)

        serialized_message = MessageSerializer(message, context={'request': request}).data

        # 🔔 Notify all participants via Pusher
        notify_new_message(conversation.id, serialized_message)

        return Response(serialized_message, status=status.HTTP_201_CREATED)


#  Create Direct Conversation
class CreateDirectConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        other_user_id = request.data.get("user_id")

        if not other_user_id:
            return Response(
                {"error": "user_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        other_user = get_object_or_404(User, id=other_user_id)

        if other_user == request.user:
            return Response(
                {"error": "Cannot create conversation with yourself"},
                status=status.HTTP_400_BAD_REQUEST
            )

        existing = Conversation.objects.filter(
            type="DIRECT",
            participants=request.user
        ).filter(participants=other_user).first()

        if existing:
            return Response(
                {"conversation_id": existing.id},
                status=status.HTTP_200_OK
            )

        conversation = Conversation.objects.create(
            type="DIRECT",
            created_by=request.user
        )
        conversation.participants.add(request.user, other_user)

        # 🔔 Notify the other user
        notify_new_conversation(other_user.id, conversation.id, "DIRECT")

        return Response(
            {"conversation_id": conversation.id},
            status=status.HTTP_201_CREATED
        )


#  Create Group Conversation
class CreateGroupConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        name = request.data.get("name")
        user_ids = request.data.get("user_ids", [])

        if not name:
            return Response(
                {"error": "Group name required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        conversation = Conversation.objects.create(
            type="GROUP",
            name=name,
            created_by=request.user
        )

        users = User.objects.filter(id__in=user_ids)
        conversation.participants.add(request.user, *users)

        # 🔔 Notify each added member
        for user in users:
            notify_new_conversation(user.id, conversation.id, "GROUP", name=name)

        return Response(
            {"conversation_id": conversation.id},
            status=status.HTTP_201_CREATED
        )


#  Employee List
class EmployeeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        users = User.objects.prefetch_related('db_roles').all()
        # Exclude the requesting user
        # users = users.exclude(id=request.user.id) # Already handled in frontend possibly, but fine.
        from .serializers import UserSerializer
        data = UserSerializer(users, many=True).data
        return Response(data, status=status.HTTP_200_OK)


#  Pusher Auth
class PusherAuthView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        channel_name = request.data.get('channel_name')
        socket_id = request.data.get('socket_id')

        if not channel_name or not socket_id:
            return Response(
                {'error': 'channel_name and socket_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not pusher_client:
            return Response(
                {'error': 'Pusher not initialized'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        if channel_name.startswith('private-user-'):
            user_id = channel_name.split('private-user-')[-1]
            if str(request.user.id) != user_id:
                return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        elif channel_name.startswith('private-chat-'):
            chat_id = channel_name.split('private-chat-')[-1]
            if not chat_id.isdigit():
                return Response({'error': 'Invalid channel'}, status=status.HTTP_400_BAD_REQUEST)

            is_participant = Conversation.objects.filter(
                id=int(chat_id),
                participants=request.user
            ).exists()

            if not is_participant:
                return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
                
        elif channel_name == 'private-leads-updates':
            # Anyone authenticated can listen to leads updates
            pass

        else:
            return Response({'error': 'Channel not allowed'}, status=status.HTTP_403_FORBIDDEN)

        try:
            auth = pusher_client.authenticate(
                channel=channel_name,
                socket_id=socket_id
            )
            return Response(auth, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"[Pusher] Auth error: {e}")
            return Response({'error': 'Auth failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)