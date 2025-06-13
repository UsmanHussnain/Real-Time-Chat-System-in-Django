from django.forms import ModelForm
from django import forms
from .models import *

class ChatMessageCreationForm(ModelForm):
    class Meta:
        model = ChatMessage
        fields = ['body']
        widgets = {
            'body': forms.TextInput(attrs={
                'name': 'body',
                'placeholder': 'Type your message here...', 
                'class': 'w-full p-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500',
                'autocomplete': 'off',
                'maxlength': '1024'
            }),
        }