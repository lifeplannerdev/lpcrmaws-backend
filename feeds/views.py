from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import FeedPost, FeedReaction, FeedComment
from .serializers import FeedPostSerializer, FeedReactionSerializer, FeedCommentSerializer
from utils.pusher import trigger_pusher
from accounts.permissions import has_dynamic_permission
from rest_framework.exceptions import PermissionDenied

from django.utils import timezone
from django.db.models import Q

class FeedPostListCreateView(generics.ListCreateAPIView):
    serializer_class = FeedPostSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = FeedPost.objects.all().prefetch_related('reactions__user', 'comments__author', 'author')
        if self.request.query_params.get('dashboard') == 'true':
            now = timezone.now()
            qs = qs.filter(valid_from__lte=now).filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=now)
            )
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if not (user.is_superuser or user.is_staff or has_dynamic_permission(user, 'feeds:post') or has_dynamic_permission(user, 'feeds:admin')):
            raise PermissionDenied("You do not have permission to post on feeds.")
        
        # Check if media is provided
        media = self.request.FILES.get('media', None)
        media_type = self.request.data.get('media_type', 'none')
        
        valid_from = self.request.data.get('valid_from', None)
        valid_until = self.request.data.get('valid_until', None)
        
        save_kwargs = {'author': user, 'media': media, 'media_type': media_type}
        if valid_from: save_kwargs['valid_from'] = valid_from
        if valid_until: save_kwargs['valid_until'] = valid_until
        
        post = serializer.save(**save_kwargs)
        
        # Trigger pusher event
        trigger_pusher('feeds', 'new_post', FeedPostSerializer(post).data)

class FeedPostDetailView(generics.DestroyAPIView):
    queryset = FeedPost.objects.all()
    permission_classes = [IsAuthenticated]

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.author != user and not (user.is_superuser or user.is_staff or has_dynamic_permission(user, 'feeds:admin')):
            raise PermissionDenied("You do not have permission to delete this post.")
        
        post_id = instance.id
        instance.delete()
        trigger_pusher('feeds', 'delete_post', {'id': post_id})

class FeedReactView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        post = get_object_or_404(FeedPost, pk=pk)
        emoji = request.data.get('emoji')
        
        if not emoji:
            return Response({"error": "Emoji is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        reaction, created = FeedReaction.objects.get_or_create(post=post, user=user, emoji=emoji)
        
        if not created:
            # If already reacted with this emoji, toggle it (remove)
            reaction.delete()
            trigger_pusher('feeds', 'remove_reaction', {'post_id': post.id, 'user_id': user.id, 'emoji': emoji})
            return Response({"status": "Reaction removed"}, status=status.HTTP_200_OK)
        else:
            reaction_data = FeedReactionSerializer(reaction).data
            reaction_data['post'] = post.id
            trigger_pusher('feeds', 'new_reaction', reaction_data)
            return Response(FeedReactionSerializer(reaction).data, status=status.HTTP_201_CREATED)

class FeedCommentListCreateView(generics.ListCreateAPIView):
    serializer_class = FeedCommentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return FeedComment.objects.filter(post_id=self.kwargs['pk'])

    def perform_create(self, serializer):
        post = get_object_or_404(FeedPost, pk=self.kwargs['pk'])
        comment = serializer.save(author=self.request.user, post=post)
        
        comment_data = FeedCommentSerializer(comment).data
        comment_data['post'] = post.id
        trigger_pusher('feeds', 'new_comment', comment_data)

class FeedCommentDetailView(generics.DestroyAPIView):
    queryset = FeedComment.objects.all()
    permission_classes = [IsAuthenticated]

    def perform_destroy(self, instance):
        user = self.request.user
        if instance.author != user and not (user.is_superuser or user.is_staff or has_dynamic_permission(user, 'feeds:admin')):
            raise PermissionDenied("You do not have permission to delete this comment.")
        
        comment_id = instance.id
        post_id = instance.post.id
        instance.delete()
        trigger_pusher('feeds', 'delete_comment', {'id': comment_id, 'post_id': post_id})
