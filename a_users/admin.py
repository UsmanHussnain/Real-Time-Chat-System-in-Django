from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from a_rtchat.models import ChatGroup, ChatMessage
from allauth.account.models import EmailAddress
from .models import Profile

class UserAdmin(BaseUserAdmin):
    def delete_queryset(self, request, queryset):
        """
        Override bulk deletion in admin to handle foreign key relationships.
        """
        for user in queryset:
            # Remove user from all chat groups
            for chat_group in ChatGroup.objects.filter(members=user):
                chat_group.members.remove(user)
                chat_group.user_online.remove(user)
                if chat_group.admin == user:
                    chat_group.admin = None
                    chat_group.save()
            # Delete user's chat messages
            ChatMessage.objects.filter(author=user).delete()
            # Delete user's email addresses from allauth
            EmailAddress.objects.filter(user=user).delete()
        # Proceed with deletion
        super().delete_queryset(request, queryset)

    def delete_model(self, request, obj):
        """
        Override single object deletion in admin to handle foreign key relationships.
        """
        # Remove user from all chat groups
        for chat_group in ChatGroup.objects.filter(members=obj):
            chat_group.members.remove(obj)
            chat_group.user_online.remove(obj)
            if chat_group.admin == obj:
                chat_group.admin = None
                chat_group.save()
        # Delete user's chat messages
        ChatMessage.objects.filter(author=obj).delete()
        # Delete user's email addresses from allauth
        EmailAddress.objects.filter(user=obj).delete()
        # Proceed with deletion
        super().delete_model(request, obj)

# Unregister the default User admin and register the custom one
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(Profile)