from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from allauth.account.utils import send_email_confirmation
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from .forms import *
from a_rtchat.models import ChatGroup  # Import ChatGroup to handle chat group cleanup

def profile_view(request, username=None):
    if username:
        profile = get_object_or_404(User, username=username).profile
    else:
        try:
            profile = request.user.profile
        except:
            return redirect_to_login(request.get_full_path())
    return render(request, 'a_users/profile.html', {'profile': profile})

@login_required
def profile_edit_view(request):
    form = ProfileForm(instance=request.user.profile)

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            return redirect('profile')

    if request.path == reverse('profile-onboarding'):
        onboarding = True
    else:
        onboarding = False

    return render(request, 'a_users/profile_edit.html', {'form': form, 'onboarding': onboarding})

@login_required
def profile_settings_view(request):
    return render(request, 'a_users/profile_settings.html')

@login_required
def profile_emailchange(request):
    if request.htmx:
        form = EmailForm(instance=request.user)
        return render(request, 'partials/email_form.html', {'form': form})

    if request.method == 'POST':
        form = EmailForm(request.POST, instance=request.user)

        if form.is_valid():
            email = form.cleaned_data['email']
            if User.objects.filter(email=email).exclude(id=request.user.id).exists():
                messages.warning(request, f'{email} is already in use.')
                return redirect('profile-settings')

            form.save()
            send_email_confirmation(request, request.user)
            return redirect('profile-settings')
        else:
            messages.warning(request, 'Email not valid or already in use')
            return redirect('profile-settings')

    return redirect('profile-settings')

@login_required
def profile_usernamechange(request):
    if request.htmx:
        form = UsernameForm(instance=request.user)
        return render(request, 'partials/username_form.html', {'form': form})

    if request.method == 'POST':
        form = UsernameForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Username updated successfully.')
            return redirect('profile-settings')
        else:
            messages.warning(request, 'Username not valid or already in use')
            return redirect('profile-settings')

    return redirect('profile-settings')

@login_required
def profile_emailverify(request):
    send_email_confirmation(request, request.user)
    return redirect('profile-settings')

@login_required
def profile_delete_view(request):
    user = request.user
    if request.method == "POST":
        # Remove user from all chat groups
        for chat_group in ChatGroup.objects.filter(members=user):
            chat_group.members.remove(user)
            chat_group.user_online.remove(user)  # Remove from online users
            if chat_group.admin == user:
                chat_group.admin = None  # Clear admin if user was admin
                chat_group.save()
        logout(request)
        user.delete()
        messages.success(request, 'Account deleted, what a pity')
        return redirect('home')

    return render(request, 'a_users/profile_delete.html')

@login_required
def admin_users_view(request):
    if not request.user.is_staff:
        raise PermissionDenied()

    users = User. objects.all().order_by('date_joined')
    return render(request, 'a_users/admin_users.html', {'users': users})

@login_required
def admin_delete_user(request, user_id):
    if not request.user.is_staff:
        raise PermissionDenied()

    user_to_delete = get_object_or_404(User, id=user_id)

    if user_to_delete != request.user:
        # Remove user from all chat groups
        for chat_group in ChatGroup.objects.filter(members=user_to_delete):
            chat_group.members.remove(user_to_delete)
            chat_group.user_online.remove(user_to_delete)
            if chat_group.admin == user_to_delete:
                chat_group.admin = None
                chat_group.save()
        user_to_delete.delete()
        messages.success(request, f'User {user_to_delete.email} deleted successfully.')
    else:
        messages.warning(request, 'You cannot delete your own account from here.')

    return redirect('admin-users')