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
                        'user_id': self.user.id,
                        'is_online': False,
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
        self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_html': html
        }))

    def update_online_count(self):
        online_count = self.chatroom.user_online.count()
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
        is_user_online = event['is_user_online']
        context = {
            'online_count': online_count,
            'chatroom': self.chatroom,
        }
        html = render_to_string("a_rtchat/partials/online_count.html", context)
        self.send(text_data=json.dumps({
            'type': 'online_status',
            'html': html,
            'is_online': is_online,
            'user_id': user_id,
            'is_user_online': is_user_online,
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