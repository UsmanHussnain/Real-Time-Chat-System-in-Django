from allauth.account.adapter import DefaultAccountAdapter
from django.core.exceptions import ValidationError
from django.urls import reverse

class CustomAccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        user.username = user.email  # Set username to email
        if commit:
            user.save()
        return user

    def get_login_redirect_url(self, request):
        """
        Redirect to profile edit page after signup
        """
        if request.user.is_authenticated:
            return reverse('profile-edit')  # This is the name from your urls.py
        return super().get_login_redirect_url(request)

    def clean_email(self, email):
        """
        Validates the email and checks for uniqueness
        """
        email = super().clean_email(email)
        if email and self._is_email_already_registered(email):
            raise ValidationError("A user is already registered with this email address.")
        return email

    def _is_email_already_registered(self, email):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.filter(email__iexact=email).exists()