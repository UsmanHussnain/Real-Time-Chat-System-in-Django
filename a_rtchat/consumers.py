# consumers.py
from channels.generic.websocket import WebsocketConsumer
from .models import *
from django.shortcuts import get_object_or_404
import json
from django.template.loader import render_to_string
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model

User = get_user_model()

class ChatroomConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope['user']
        self.chatroom_name = self.scope['url_route']['kwargs']['chatroom_name']
        self.chatroom = get_object_or_404(ChatGroup, group_name=self.chatroom_name)
        
        # Remove user from other chatrooms' user_online
        for group in ChatGroup.objects.filter(user_online=self.user):
            if group != self.chatroom:
                group.user_online.remove(self.user)
                async_to_sync(self.channel_layer.group_send)(
                    group.group_name,
                    {
                        'type': 'update_online_count' if not group.is_private else 'update_private_online_status',
                        'user_id': self.user.id,
                        'is_online': False,
                    }
                )
        
        async_to_sync(self.channel_layer.group_add)(
            self.chatroom_name,
            self.channel_name
        )
        
        if self.user not in self.chatroom.user_online.all():
            self.chatroom.user_online.add(self.user)
            self.update_online_count()
            if self.chatroom.is_private:
                self.update_private_online_status()

        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.chatroom_name,
            self.channel_name
        )

        if self.user in self.chatroom.user_online.all():
            self.chatroom.user_online.remove(self.user)
            self.update_online_count()
            if self.chatroom.is_private:
                self.update_private_online_status()

    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        body = text_data_json['body']
        message = ChatMessage.objects.create(
            body=body,
            author=self.user,
            group=self.chatroom
        )
        event = {
            'type': 'message_handler',
            'message_id': message.id,
        }
        async_to_sync(self.channel_layer.group_send)(
            self.chatroom_name, event
        )

    def message_handler(self, event):
        message_id = event['message_id']
        message = ChatMessage.objects.get(id=message_id)
        # Render message HTML with the correct user context
        context = {
            'message': message,
            'user': self.user,  # Use the receiving user's context
            'chatgroup': self.chatroom,
        }
        # Always render using chat_message.html to ensure correct sender/receiver styling
        html = render_to_string("a_rtchat/chat_message.html", context=context)
        self.send(text_data=json.dumps({
            'type': 'chat_message',  # Use 'chat_message' for both text and files
            'message_html': html
        }))

    def update_online_count(self):
        online_count = self.chatroom.user_online.count() - 1
        event = {
            'type': 'online_count_handler',
            'online_count': online_count,
            'is_online': online_count > 0,
            'user_id': self.user.id,
            'is_user_online': self.user in self.chatroom.user_online.all(),
        }
        async_to_sync(self.channel_layer.group_send)(
            self.chatroom_name, event
        )

    def online_count_handler(self, event):
        online_count = event['online_count']
        is_online = event['is_online']
        user_id = event['user_id']
        is_user_multiple = event['is_user_online']

        chat_messages = self.chatroom.chat_messages.all()[:30]
        author_ids = [message.author.id for message in chat_messages]
        users = User.objects.filter(id__in=author_ids).distinct()
        
        context = {
            'online_count': online_count,
            'chatroom': self.chatroom,
            'users': users,
            'user': self.user,
        }
        html = render_to_string("a_rtchat/partials/online_count.html", context)
        self.send(text_data=json.dumps({
            'type': 'online_status',
            'html': html,
            'is_online': is_online,
            'user_id': user_id,
            'isJon': is_user_multiple,
        }))

    def update_private_online_status(self):
        if self.chatroom.is_private:
            for member in self.chatroom.members.all():
                is_online = member in self.chatroom.user_online.all()
                event = {
                    'type': 'private_online_status_handler',
                    'is_online': is_online,
                    'user_id': member.id,
                }
                async_to_sync(self.channel_layer.group_send)(
                    self.chatroom_name, event
                )

    def private_online_status_handler(self, event):
        is_online = event['is_online']
        user_id = event['user_id']
        self.send(text_data=json.dumps({
            'type': 'private_online_status',
            'is_online': is_online,
            'user_id': user_id,
        }))

class OnlineStatusConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope['user']
        self.group_name = 'online_status'

        async_to_sync(self.channel_layer.group_add)(
            self.group_name,
            self.channel_name
        )

        if self.user.is_authenticated:
            try:
                self.group = ChatGroup.objects.get(group_name='global_online')
                if self.user not in self.group.user_online.all():
                    self.group.user_online.add(self.user)
            except ChatGroup.DoesNotExist:
                self.group = ChatGroup.objects.create(group_name='global_online', is_private=False)
                self.group.user_online.add(self.user)

        self.accept()
        self.online_status()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name,
            self.channel_name
        )

        if self.user.is_authenticated and hasattr(self, 'group'):
            if self.user in self.group.user_online.all():
                self.group.user_online.remove(self.user)
            self.online_status()

    def online_status(self):
        if hasattr(self, 'group'):
            online_count = self.group.user_online.count() - 1
            event = {
                'type': 'online_status_handler',
                'online_count': online_count,
            }
            async_to_sync(self.channel_layer.group_send)(
                self.group_name, event
            )

    def online_status_handler(self, event):
        online_count = event['online_count']
        
        try:
            public_chat = ChatGroup.objects.get(group_name='public_chat')
            public_chat_users = public_chat.user_online.all()
            other_online_users = [u for u in public_chat_users if u.id != self.user.id]
            public_chat_status = public_chat.user_online.exists()
        except ChatGroup.DoesNotExist:
            public_chat = ChatGroup.objects.create(group_name='public_chat', is_private=False)
            other_online_users = []
            public_chat_status = False

        my_chats = self.user.chat_groups.all()
        chat_statuses = []
        
        for chat in my_chats:
            online_users = chat.user_online.all()
            
            if chat.is_private:
                for member in chat.members.all():
                    if member != self.user:
                        chat_statuses.append({
                            'type': 'private',
                            'chat_id': chat.id,
                            'user_id': member.id,
                            'is_online': member in online_users,
                            'avatar': member.profile.avatar,
                            'name': member.profile.name,
                            'group_name': chat.group_name
                        })
            else:
                chat_statuses.append({
                    'type': 'group',
                    'chat_id': chat.id,
                    'is_online': any(u.id != self.user.id for u in online_users),
                    'group_name': chat.group_name,
                    'chat_name': chat.groupchat_name,
                    'online_users': [u for u in online_users if u.id != self.user.id]
                })
        
        online_in_chats = bool(other_online_users or any(
            status['is_online'] for status in chat_statuses
        ))
        
        context = {
            'online_count': online_count,
            'online_in_chats': online_in_chats,
            'public_chat_status': public_chat_status,
            'chat_statuses': chat_statuses,
            'user': self.user,
        }
        
        html = render_to_string("a_rtchat/partials/online_status.html", context)
        self.send(text_data=json.dumps({
            'type': 'online_status',
            'html': html,
            'online_count': online_count,
        }))