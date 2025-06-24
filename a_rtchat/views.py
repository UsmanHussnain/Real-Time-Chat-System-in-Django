from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import *
from .forms import *
from django.contrib.auth.models import User
from django.http import Http404
from django.contrib import messages
from django.db import transaction


@login_required
def chat_view(request, chatroom_name='public-chat'):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    chat_messages = chat_group.chat_messages.all()[:30]
    form = ChatMessageCreationForm()

    other_users = None
    if chat_group.is_private:
        if request.user not  in chat_group.members.all():
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
            context = {
                'message': chat_message,
                'user': request.user
            }
            return render(request, 'a_rtchat/partials/chat_messages_p.html', context)

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
    form = newGroupForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            new_groupchat = form.save(commit=False)
            new_groupchat.admin = request.user
            new_groupchat.save()
            new_groupchat.members.add(request.user)
            return redirect('chatroom', new_groupchat.group_name)

    context = {
        'form': form,
    }
    return render(request, 'a_rtchat/create_groupchat.html', context)

@login_required
def chatroom_edit_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin:
        raise Http404()

    form = ChatRoomEditForm(instance=chat_group)
    
    if request.method == 'POST':
        form = ChatRoomEditForm(request.POST, instance=chat_group)
        if form.is_valid():
            form.save()
            messages.success(request, "Chatroom updated successfully.")
            remove_members = request.POST.getlist('remove_members')
            for member_id in remove_members:
                member = User.objects.get(id=member_id)
                chat_group.members.remove(member)
            return redirect('chatroom', chatroom_name)
    context = {
        'form': form,
        'chat_group': chat_group,
    }
    return render(request, 'a_rtchat/chatroom_edit.html', context)


@login_required
def chatroom_delete_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin:
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