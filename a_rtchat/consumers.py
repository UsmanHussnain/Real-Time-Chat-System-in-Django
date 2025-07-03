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
        
        # Mark all messages as read for THIS chatroom when connected, filtered by date_joined
        unread_messages = self.chatroom.chat_messages.filter(created__gte=self.user.date_joined).exclude(read_by=self.user)
        for message in unread_messages:
            message.read_by.add(self.user)
        
        # Notify other components that messages have been read
        async_to_sync(self.channel_layer.group_send)(
            f"user_{self.user.id}",
            {
                'type': 'chat_read',
                'chatroom_name': self.chatroom_name
            }
        )
        
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
        
        if 'type' in text_data_json and text_data_json['type'] == 'mark_chat_read':
            # Handle marking chat as read, filtered by date_joined
            chatroom_name = text_data_json['chatroom_name']
            chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
            unread_messages = chat_group.chat_messages.filter(created__gte=self.user.date_joined).exclude(read_by=self.user)
            for message in unread_messages:
                message.read_by.add(self.user)
            return
            
        if 'type' in text_data_json and text_data_json['type'] == 'mark_message_read':
            # Handle marking single message as read
            message_id = text_data_json['message_id']
            message = get_object_or_404(ChatMessage, id=message_id)
            if message.created >= self.user.date_joined:
                message.read_by.add(self.user)
            return
            
        # Normal message handling
        body = text_data_json.get('body')
        if body:
            message = ChatMessage.objects.create(
                body=body,
                author=self.user,
                group=self.chatroom
            )
            
            # Get unread count for this chatroom for other users
            unread_counts = {}
            for member in self.chatroom.members.all():
                if member != self.user:
                    unread_count = self.chatroom.chat_messages.filter(created__gte=member.date_joined).exclude(read_by=member).count()
                    unread_counts[member.id] = unread_count
            
            # Broadcast to all clients in the chatroom
            async_to_sync(self.channel_layer.group_send)(
                self.chatroom_name,
                {
                    'type': 'message_handler',
                    'message_id': message.id,
                    'author_id': self.user.id
                }
            )
            
            # Send unread notifications to other members
            for member in self.chatroom.members.all():
                if member != self.user:
                    async_to_sync(self.channel_layer.group_send)(
                        f"user_{member.id}",
                        {
                            'type': 'unread_message',
                            'chatroom_name': self.chatroom_name,
                            'sender_id': self.user.id,
                            'sender_name': self.user.profile.name,
                            'sender_avatar': self.user.profile.avatar,
                            'message_body': body,
                            'unread_count': unread_counts.get(member.id, 0)
                        }
                    )

    def message_handler(self, event):
        message_id = event['message_id']
        message = ChatMessage.objects.get(id=message_id)
        
        # Only handle message if created after user's join date
        if message.created >= self.user.date_joined:
            # Mark message as read if user is in chat
            if self.user in self.chatroom.user_online.all():
                message.read_by.add(self.user)
        
            # Render message with the correct user context
            context = {
                'message': message,
                'user': self.user,  # Use the receiving user's context
                'chatgroup': self.chatroom,
            }
            message_html = render_to_string("a_rtchat/chat_message.html", context)
        
            self.send(text_data=json.dumps({
                'type': 'chat_message',
                'message_html': message_html,
                'message_id': message_id,
                'author_id': event['author_id']
            }))

    def file_handler(self, event):
        """Handle file upload messages"""
        message_id = event['message_id']
        message = ChatMessage.objects.get(id=message_id)
        
        # Only handle message if created after user's join date
        if message.created >= self.user.date_joined:
            # Mark message as read if user is in chat
            if self.user in self.chatroom.user_online.all():
                message.read_by.add(self.user)
        
            # Render file message with the correct user context
            context = {
                'message': message,
                'user': self.user,  # Use the receiving user's context
                'chatgroup': self.chatroom,
            }
            message_html = render_to_string("a_rtchat/chat_message.html", context)
        
            self.send(text_data=json.dumps({
                'type': 'file_message',
                'message_html': message_html,
                'message_id': message_id,
                'author_id': event['author_id']
            }))

    def unread_message(self, event):
        # Handle unread message notification
        chatroom_name = event['chatroom_name']
        sender_id = event['sender_id']
        unread_count = event['unread_count']
        sender_name = event.get('sender_name', '')
        sender_avatar = event.get('sender_avatar', '')
        message_body = event.get('message_body', '')
        
        self.send(text_data=json.dumps({
            'type': 'unread_message',
            'chatroom_name': chatroom_name,
            'sender_id': sender_id,
            'sender_name': sender_name,
            'sender_avatar': sender_avatar,
            'message_body': message_body,
            'unread_count': unread_count
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

        chat_messages = self.chatroom.chat_messages.filter(created__gte=self.user.date_joined)[:30]
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

    def chat_read(self, event):
        self.send(text_data=json.dumps({
            'type': 'chat_read',
            'chatroom_name': event['chatroom_name']
        }))

class OnlineStatusConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope['user']
        self.group_name = 'online_status'
        self.user_group_name = f"user_{self.user.id}"

        async_to_sync(self.channel_layer.group_add)(
            self.group_name,
            self.channel_name
        )
        
        async_to_sync(self.channel_layer.group_add)(
            self.user_group_name,
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
        
        async_to_sync(self.channel_layer.group_discard)(
            self.user_group_name,
            self.channel_name
        )

        if self.user.is_authenticated and hasattr(self, 'group'):
            if self.user in self.group.user_online.all():
                self.group.user_online.remove(self.user)
            self.online_status()

    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        
        if text_data_json.get('type') == 'get_unread_counts':
            # Send current unread counts to client
            self.send_unread_counts()
        elif text_data_json.get('type') == 'mark_chat_read':
            # Handle marking a chat as read
            chatroom_name = text_data_json['chatroom_name']
            chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
            unread_messages = chat_group.chat_messages.filter(created__gte=self.user.date_joined).exclude(read_by=self.user)
            for message in unread_messages:
                message.read_by.add(self.user)

    def send_unread_counts(self):
        # Calculate unread counts for all user's chats
        my_chats = self.user.chat_groups.all()
        unread_counts = {}
        
        for chat in my_chats:
            unread_count = chat.chat_messages.filter(created__gte=self.user.date_joined).exclude(read_by=self.user).count()
            if unread_count > 0:
                unread_counts[chat.group_name] = unread_count
        
        # Also check public chat
        try:
            public_chat = ChatGroup.objects.get(group_name='public-chat')
            public_unread = public_chat.chat_messages.filter(created__gte=self.user.date_joined).exclude(read_by=self.user).count()
            if public_unread > 0:
                unread_counts['public-chat'] = public_unread
        except ChatGroup.DoesNotExist:
            pass
        
        self.send(text_data=json.dumps({
            'type': 'unread_counts',
            'counts': unread_counts
        }))

    def mark_chat_read(self, event):
        # Handle marking a chat as read
        chatroom_name = event['chatroom_name']
        chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
        unread_messages = chat_group.chat_messages.filter(created__gte=self.user.date_joined).exclude(read_by=self.user)
        for message in unread_messages:
            message.read_by.add(self.user)
        
        # Send confirmation back to client
        self.send(text_data=json.dumps({
            'type': 'chat_read',
            'chatroom_name': chatroom_name
        }))

    def unread_message(self, event):
        # Handle unread message notification
        chatroom_name = event['chatroom_name']
        sender_id = event['sender_id']
        unread_count = event['unread_count']
        
        self.send(text_data=json.dumps({
            'type': 'unread_message',
            'chatroom_name': chatroom_name,
            'sender_id': sender_id,
            'unread_count': unread_count
        }))

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
            
            # Calculate unread counts for each chat
            unread_count = chat.chat_messages.filter(created__gte=self.user.date_joined).exclude(read_by=self.user).count()
            
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
                            'group_name': chat.group_name,
                            'unread_count': unread_count
                        })
            else:
                chat_statuses.append({
                    'type': 'group',
                    'chat_id': chat.id,
                    'is_online': any(u.id != self.user.id for u in online_users),
                    'group_name': chat.group_name,
                    'chat_name': chat.groupchat_name,
                    'online_users': [u for u in online_users if u.id != self.user.id],
                    'unread_count': unread_count
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

    def chat_read(self, event):
        """Handle marking a chat as read"""
        chatroom_name = event['chatroom_name']
        chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
        
        # Mark messages as read
        unread_messages = chat_group.chat_messages.filter(created__gte=self.user.date_joined).exclude(read_by=self.user)
        for message in unread_messages:
            message.read_by.add(self.user)
        
        # Send confirmation back to client
        self.send(text_data=json.dumps({
            'type': 'chat_read',
            'chatroom_name': chatroom_name
        }))
        
        # Update unread counts
        self.send_unread_counts()