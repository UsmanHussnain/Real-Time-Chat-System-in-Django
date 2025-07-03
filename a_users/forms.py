from django.forms import ModelForm
from django import forms
from django.contrib.auth.models import User
from .models import Profile
from allauth.account.forms import SignupForm
from django.core.exceptions import ValidationError

class CustomSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('username', None)
        
    def save(self, request):
        user = super().save(request)
        user.username = self.cleaned_data['email']  # Use email as username
        user.save()
        return user

class ProfileForm(ModelForm):
    class Meta:
        model = Profile
        fields = ['image', 'displayname', 'info']
        widgets = {
            'image': forms.FileInput(),
            'displayname': forms.TextInput(attrs={'placeholder': 'Add display name'}),
            'info': forms.Textarea(attrs={'rows':3, 'placeholder': 'Add information'})
        }
        
class EmailForm(ModelForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['email']

class UsernameForm(ModelForm):
    class Meta:
        model = User
        fields = ['username']