from channels.generic.websocket import WebsocketConsumer
from .models import *
from django.shortcuts import get_object_or_404
import json
from django.template.loader import render_to_string
from asgiref.sync import async_to_sync

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
                    }
                )
        
        async_to_sync(self.channel_layer.group_add)(
            self.chatroom_name,
            self.channel_name
        )
        
        # Add and update the user to the online users in the chatroom
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

        # Remove and update the user from online users in the chatroom
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
        context = {
            'message': message,
            'user': self.user,
        }
        html = render_to_string("a_rtchat/partials/chat_messages_p.html", context=context)
        self.send(text_data=html)

    def update_online_count(self):
        online_count = self.chatroom.user_online.count() - 1
        event = {
            'type': 'online_count_handler',
            'online_count': online_count,
        }
        async_to_sync(self.channel_layer.group_send)(
            self.chatroom_name, event
        )

    def online_count_handler(self, event):
        online_count = event['online_count']
        # Update online count
        html = render_to_string(
            "a_rtchat/partials/online_count.html",
            {'online_count': online_count}
        )
        # Update online-icon for public chats
        icon_html = f'<div id="online-icon" class="{"green-dot" if online_count > 0 else "gray-dot"} absolute top-2 left-2"></div>'
        self.send(text_data=html + icon_html)

    def update_private_online_status(self):
        if self.chatroom.is_private:
            for member in self.chatroom.members.all():
                if member != self.user:
                    other_user = member
                    break
            else:
                other_user = None
            is_online = other_user in self.chatroom.user_online.all() if other_user else False
            event = {
                'type': 'private_online_status_handler',
                'is_online': is_online,
            }
            async_to_sync(self.channel_layer.group_send)(
                self.chatroom_name, event
            )

    def private_online_status_handler(self, event):
        is_online = event['is_online']
        html = f'<div id="online-icon" class="{"green-dot" if is_online else "gray-dot"} absolute top-2 left-2"></div>'
        self.send(text_data=html)