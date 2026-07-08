from django.urls import path
from . import views

urlpatterns = [
    path('', views.FeedPostListCreateView.as_view(), name='feed-list-create'),
    path('<int:pk>/', views.FeedPostDetailView.as_view(), name='feed-detail'),
    path('<int:pk>/react/', views.FeedReactView.as_view(), name='feed-react'),
    path('<int:pk>/comments/', views.FeedCommentListCreateView.as_view(), name='feed-comment-list-create'),
    path('comments/<int:pk>/', views.FeedCommentDetailView.as_view(), name='feed-comment-detail'),
]
