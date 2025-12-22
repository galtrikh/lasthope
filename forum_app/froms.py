from django import forms
from .models import ForumPost

class PostCreationForm(forms.ModelForm):
    class Meta:
        model = ForumPost
        fields = ('content',)
