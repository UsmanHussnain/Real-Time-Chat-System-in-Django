from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import *
from .forms import *
from django.contrib.auth.models import User
from django.http import Http404, HttpResponse, JsonResponse
from django.contrib import messages
from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.template.loader import render_to_string
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
import json
import shortuuid
import uuid
import time
from django.db import IntegrityError
import logging

logger = logging.getLogger(__name__)

@login_required
def chat_view(request, chatroom_name='public-chat'):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    # Filter messages to show only those created after the user's signup
    chat_messages = chat_group.chat_messages.filter(created__gte=request.user.date_joined)[:30]
    form = ChatMessageCreationForm()

    # Ensure user is added to public chat members if not already
    if chatroom_name == 'public-chat' and request.user not in chat_group.members.all():
        chat_group.members.add(request.user)

    # Only mark messages as read for THIS chatroom when opened
    if request.user in chat_group.members.all():
        unread_messages = chat_group.chat_messages.filter(created__gte=request.user.date_joined).exclude(read_by=request.user)
        for message in unread_messages:
            message.read_by.add(request.user)

    other_users = None
    if chat_group.is_private:
        if request.user not in chat_group.members.all():
            raise Http404()
        for member in chat_group.members.all():
            if member != request.user:
                other_users = member
                break

    if chat_group.groupchat_name:
        if request.user not in chat_group.members.all():
            if request.user.emailaddress_set.filter(verified=True).exists():
                chat_group.members.add(request.user)
            else:
                messages.warning(request, "You need to verify your email to join this chat.")
                return redirect('profile-settings')
    
    if request.htmx and request.method == 'POST':
        form = ChatMessageCreationForm(request.POST)
        if form.is_valid():
            chat_message = form.save(commit=False)
            chat_message.author = request.user
            chat_message.group = chat_group
            chat_message.save()
            
            # Mark message as read for sender immediately
            chat_message.read_by.add(request.user)
            
            # Send notification to other members
            channel_layer = get_channel_layer()
            for member in chat_group.members.all():
                if member != request.user:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{member.id}",
                        {
                            'type': 'unread_message',
                            'chatroom_name': chatroom_name,
                            'sender_id': request.user.id,
                            'sender_name': request.user.profile.name,
                            'sender_avatar': request.user.profile.avatar,
                            'message_body': chat_message.body,
                            'unread_count': chat_group.chat_messages.filter(created__gte=member.date_joined).exclude(read_by=member).count()
                        }
                    )
            
            context = {
                'message': chat_message,
                'user': request.user,
                'chatgroup': chat_group,
            }
            return render(request, 'a_rtchat/chat_message.html', context)

    context = {
        'chat_messages': chat_messages,
        'form': form,
        'other_users': other_users,
        'chatroom_name': chatroom_name,
        'chat_group': chat_group,
    }
    return render(request, 'a_rtchat/chat.html', context)


@login_required
def get_or_create_chatroom(request, username):
    if request.user.username == username:
        return redirect('home')
    
    other_user = get_object_or_404(User, username=username)
    
    # Check if private chat already exists between these two users
    my_chatrooms = request.user.chat_groups.filter(is_private=True)
    
    chatroom = None
    if my_chatrooms.exists():
        for room in my_chatrooms:
            if other_user in room.members.all():
                chatroom = room
                break
    
    # If no existing chatroom found, create new one
    if not chatroom:
        try:
            with transaction.atomic():
                # Generate consistent group name to avoid duplicates
                user_ids = sorted([request.user.id, other_user.id])
                group_name = f"private-{user_ids[0]}-{user_ids[1]}"
                
                # Check if chatroom with this name already exists
                existing_chatroom = ChatGroup.objects.filter(group_name=group_name).first()
                if existing_chatroom:
                    chatroom = existing_chatroom
                    # Make sure both users are members
                    if request.user not in chatroom.members.all():
                        chatroom.members.add(request.user)
                    if other_user not in chatroom.members.all():
                        chatroom.members.add(other_user)
                else:
                    # Create new chatroom with specific group_name
                    chatroom = ChatGroup.objects.create(
                        group_name=group_name,
                        is_private=True
                    )
                    chatroom.members.add(other_user, request.user)
        except Exception as e:
            # If error occurs, try to find any existing private chat
            existing_chat = ChatGroup.objects.filter(
                is_private=True,
                members=request.user
            ).filter(members=other_user).first()
            
            if existing_chat:
                chatroom = existing_chat
            else:
                messages.error(request, "Error creating chat. Please try again.")
                return redirect('home')

    return redirect('chatroom', chatroom.group_name)


@login_required
def create_groupchat(request):
    if not request.user.is_superuser:
        messages.error(request, "Only superusers can create group chats.")
        return redirect('home')
    
    form = newGroupForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            max_retries = 15  # Increased retry limit
            for attempt in range(max_retries):
                new_groupchat = form.save(commit=False)
                new_groupchat.admin = request.user
                timestamp = int(time.time() * 1000)
                new_groupchat.group_name = f"group-{shortuuid.uuid()}-{timestamp}"  # Use full UUID
                logger.debug(f"Attempt {attempt + 1}: Trying group_name={new_groupchat.group_name}")

                try:
                    new_groupchat.save()
                    new_groupchat.members.add(request.user)
                    messages.success(request, f"Group '{new_groupchat.groupchat_name}' created successfully!")
                    logger.debug(f"Group created: {new_groupchat.group_name}")
                    return redirect('chatroom', new_groupchat.group_name)
                except IntegrityError as e:
                    logger.error(f"IntegrityError on attempt {attempt + 1}: {e}, group_name={new_groupchat.group_name}")
                    if attempt == max_retries - 1:
                        messages.error(request, "Could not create unique group chat after multiple attempts. Please try again.")
                        return redirect('home')
                    continue

    context = {
        'form': form,
    }
    return render(request, 'a_rtchat/create_groupchat.html', context)


@login_required
def chatroom_edit_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)

    # Only superuser and group admin can edit
    if not request.user.is_superuser:
        messages.error(request, "Only superusers can edit group chats.")
        raise Http404()
    if request.user != chat_group.admin:
        messages.error(request, "Only the admin can edit this group chat.")
        raise Http404()

    # Pre-fill form
    form = ChatRoomEditForm(instance=chat_group)

    # Handle submission
    if request.method == 'POST':
        form = ChatRoomEditForm(request.POST, instance=chat_group)
        if form.is_valid():
            form.save()
            messages.success(request, "Chatroom updated successfully.")
            
            # Remove members permanently (including WebSocket)
            remove_members = request.POST.getlist('remove_members')
            for member_id in remove_members:
                try:
                    member = User.objects.get(id=member_id)
                    chat_group.members.remove(member)
                    chat_group.user_online.remove(member)  # WebSocket disconnect
                except User.DoesNotExist:
                    continue  # just skip if member doesn't exist

            return redirect('chatroom', chatroom_name)

    context = {
        'form': form,
        'chat_group': chat_group,
    }
    return render(request, 'a_rtchat/chatroom_edit.html', context)


@login_required
def chatroom_delete_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if not request.user.is_superuser:
        messages.error(request, "Only superusers can delete group chats.")
        raise Http404()
    if request.user != chat_group.admin:
        messages.error(request, "Only the admin can delete this group chat.")
        raise Http404()

    if request.method == 'POST':
        chat_group.delete()
        messages.success(request, "Chatroom deleted successfully.")
        return redirect('home')

    context = {
        'chat_group': chat_group,
    }
    return render(request, 'a_rtchat/chatroom_delete.html', context)


@login_required
def chatroom_leave_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user not in chat_group.members.all():
        raise Http404()

    if request.method == 'POST':
        chat_group.members.remove(request.user)
        messages.success(request, "You have left the chatroom.")
        return redirect('home')
    return redirect('home')


@login_required
def chat_file_upload(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.htmx and request.FILES:
        file = request.FILES.get('file')
        if file:
            # Create the message
            message = ChatMessage.objects.create(
                file=file,
                author=request.user,
                group=chat_group,
            )
            
            # Mark as read for sender
            message.read_by.add(request.user)
            
            # Get unread counts for notifications
            unread_counts = {}
            for member in chat_group.members.all():
                if member != request.user:
                    unread_count = chat_group.chat_messages.filter(created__gte=member.date_joined).exclude(read_by=member).count()
                    unread_counts[member.id] = unread_count
            
            # Send notifications to other members
            channel_layer = get_channel_layer()
            for member in chat_group.members.all():
                if member != request.user:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{member.id}",
                        {
                            'type': 'unread_message',
                            'chatroom_name': chatroom_name,
                            'sender_id': request.user.id,
                            'sender_name': request.user.profile.name,
                            'sender_avatar': request.user.profile.avatar,
                            'message_body': '',
                            'unread_count': unread_counts.get(member.id, 0)
                        }
                    )
            
            # Broadcast to all clients via WebSocket (no HTMX response for sender)
            async_to_sync(channel_layer.group_send)(
                chatroom_name,
                {
                    'type': 'file_handler',
                    'message_id': message.id,
                    'author_id': request.user.id,
                }
            )
            
            return HttpResponse(status=204)  # No content response to prevent duplicate rendering
    
    return HttpResponse(status=400)


@login_required
def filter_chat_messages(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    filter_type = request.GET.get('filter', 'all')
    # Filter messages by user's join date
    chat_messages = chat_group.chat_messages.filter(created__gte=request.user.date_joined)

    if filter_type == 'files':
        chat_messages = chat_messages.filter(
            file__isnull=False
        ).filter(
            Q(body__isnull=True) | Q(body__exact='')
        ).exclude(
            file__icontains='.jpg'
        ).exclude(
            file__icontains='.jpeg'
        ).exclude(
            file__icontains='.png'
        ).exclude(
            file__icontains='.gif'
        )
    elif filter_type == 'photos':
        chat_messages = chat_messages.filter(
            Q(file__icontains='.jpg') |
            Q(file__icontains='.jpeg') |
            Q(file__icontains='.png') |
            Q(file__icontains='.gif')
        )
    elif filter_type == 'links':
        chat_messages = chat_messages.filter(body__regex=r'(https?://|www\.)[^\s]+')
    elif filter_type == 'all':
        pass  # No additional filtering beyond date_joined

    chat_messages = chat_messages[:30]

    context = {
        'chat_messages': chat_messages,
        'user': request.user,
        'chatgroup': chat_group,
    }
    return render(request, 'a_rtchat/partials/chat_messages_filtered.html', context)

@csrf_exempt
@login_required
def add_member_via_email(request, chatroom_name):
    if request.method == 'POST':
        chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
        if request.user != chat_group.admin:
            return JsonResponse({'status': 'error', 'message': 'Only admin can add members.'})

        try:
            data = json.loads(request.body)
            email = data.get('email')
            user = User.objects.get(email=email)

            if user in chat_group.members.all():
                return JsonResponse({'status': 'error', 'message': 'User already in group.'})

            chat_group.members.add(user)
            return JsonResponse({
                'status': 'success', 
                'message': f'{user.username} added to group successfully.'
            })
        except User.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'User not found.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request.'})