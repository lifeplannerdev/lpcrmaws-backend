from django.db import models
from django.conf import settings
from django.utils import timezone
from storages.backends.s3boto3 import S3Boto3Storage

class FeedPost(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feed_posts')
    content = models.TextField(blank=True, null=True)
    media = models.FileField(storage=S3Boto3Storage(), upload_to='feeds/media/%Y/%m/', blank=True, null=True)
    MEDIA_CHOICES = (
        ('image', 'Image'),
        ('video', 'Video'),
        ('none', 'None')
    )
    media_type = models.CharField(max_length=10, choices=MEDIA_CHOICES, default='none')
    created_at = models.DateTimeField(auto_now_add=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Post by {self.author.username} at {self.created_at}"

class FeedReaction(models.Model):
    post = models.ForeignKey(FeedPost, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feed_reactions')
    emoji = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('post', 'user', 'emoji') # Can have multiple emojis but only one of each type per user

    def __str__(self):
        return f"{self.user.username} reacted {self.emoji} on {self.post.id}"

class FeedComment(models.Model):
    post = models.ForeignKey(FeedPost, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feed_comments')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.username} on {self.post.id}"
