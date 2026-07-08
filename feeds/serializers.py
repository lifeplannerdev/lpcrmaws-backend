from rest_framework import serializers
from .models import FeedPost, FeedReaction, FeedComment
from django.contrib.auth import get_user_model

User = get_user_model()

class UserBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'avatar']

class FeedReactionSerializer(serializers.ModelSerializer):
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = FeedReaction
        fields = ['id', 'user', 'emoji', 'created_at']

class FeedCommentSerializer(serializers.ModelSerializer):
    author = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = FeedComment
        fields = ['id', 'author', 'content', 'created_at']

class FeedPostSerializer(serializers.ModelSerializer):
    author = UserBasicSerializer(read_only=True)
    reactions = FeedReactionSerializer(many=True, read_only=True)
    comments = FeedCommentSerializer(many=True, read_only=True)
    
    class Meta:
        model = FeedPost
        fields = ['id', 'author', 'content', 'media', 'media_type', 'created_at', 'reactions', 'comments']
        
    def to_representation(self, instance):
        repr = super().to_representation(instance)
        # Add summary counts
        repr['reaction_count'] = instance.reactions.count()
        repr['comment_count'] = instance.comments.count()
        return repr
