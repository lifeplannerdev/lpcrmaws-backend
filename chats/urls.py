from django.urls import path
from .views import (
    ConversationListView,
    MessageListView,
    SendMessageView,
    DeleteMessageView,
    CreateDirectConversationView,
    CreateGroupConversationView,
    EmployeeListView,
    PusherAuthView,
    MessageDeliveredView,
    MessageReadView,
)

urlpatterns = [
    path("employees-list/", EmployeeListView.as_view()),
    path("conversations/", ConversationListView.as_view(), name="conversation-list"),
    path("messages/<int:conversation_id>/", MessageListView.as_view(), name="message-list"),
    path("send/", SendMessageView.as_view(), name="send-message"),
    path("messages/<int:message_id>/delete/", DeleteMessageView.as_view(), name="delete-message"),
    path("delivered/", MessageDeliveredView.as_view(), name="message-delivered"),
    path("read/", MessageReadView.as_view(), name="message-read"),
    path("create-direct/", CreateDirectConversationView.as_view(), name="create-direct"),
    path("create-group/", CreateGroupConversationView.as_view(), name="create-group"),
    path("pusher/auth/", PusherAuthView.as_view()),
]