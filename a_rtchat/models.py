# models.py
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
import shortuuid

class ChatGroup(models.Model):
    group_name = models.CharField(max_length=128, unique=True)
    groupchat_name = models.CharField(max_length=128, blank=True, null=True)
    admin = models.ForeignKey(User, related_name='groupchats', blank=True, null=True, on_delete=models.SET_NULL)
    user_online = models.ManyToManyField(
        User,
        related_name='online_in_groups',
        blank=True,
    )
    members = models.ManyToManyField(
        User,
        related_name='chat_groups',
        blank=True,
    )
    is_private = models.BooleanField(default=False)

    def __str__(self):
        return self.group_name
    
class ChatMessage(models.Model):
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name='chat_messages')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.CharField(max_length=1024, blank=True, null=True)
    file = models.FileField(upload_to='files/', blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    read_by = models.ManyToManyField(
        User,
        related_name='read_messages',
        blank=True
    )

    def __str__(self):
        body_preview = self.body[:100] if self.body else "(No message content)"
        return f"{self.author.username}: {body_preview}"
    
    class Meta:
        ordering = ['-created']