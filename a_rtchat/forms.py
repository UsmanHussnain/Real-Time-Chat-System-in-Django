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

class newGroupForm(ModelForm):
    class Meta:
        model = ChatGroup
        fields = ['groupchat_name']
        widgets = {
            'groupchat_name': forms.TextInput(attrs={
                'name': 'groupchat_name',
                'placeholder': 'Enter group chat name', 
                'class': 'w-full p-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500',
                'autocomplete': 'off',
                'maxlength': '300',
                'autofocus': True,
            }),
        }

class ChatRoomEditForm(ModelForm):
    class Meta:
        model = ChatGroup
        fields = ['groupchat_name']
        widgets = {
            'groupchat_name': forms.TextInput(attrs={
                'class': 'p-4 text-xl font-bold mb-4',
                'autocomplete': 'off',
                'maxlength': '300',
                'autofocus': True,
            }),
        }