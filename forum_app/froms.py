from django import forms
from .models import ForumPost, ForumTopic, ForumCategory
from django.utils.safestring import mark_safe

ICON_CHOICES_TOPIC = [
    ('fa-solid fa-star', 'Star'),
    ('fa-solid fa-heart', 'Heart'),
    ('fa-solid fa-flask-vial', 'Flask'),
    ('fa-solid fa-gamepad', 'Gamepad'),
    ('fa-solid fa-tablet', 'Tablet'),
    ('fa-solid fa-table', 'Table'),
    ('fa-solid fa-comment-dots', 'Comment'),
    ('fa-solid fa-message', 'Message'),
    ('fa-solid fa-poo', 'Poo'),
    ('fa-solid fa-comments', 'Comments'),
    ('fa-solid fa-envelope-circle-check', 'Evenlope Check'),
    ('fa-solid fa-envelope', 'Evenlope'),
    ('fa-solid fa-bullhorn', 'Bullhorn'),
    ('fa-solid fa-face-smile', 'Face Smile'),
]

ICON_CHOICES_CATEGORY = [
    ('fa-solid fa-star', 'Star'),
    ('fa-solid fa-heart', 'Heart'),
    ('fa-solid fa-flask-vial', 'Flask'),
    ('fa-solid fa-gamepad', 'Gamepad'),
    ('fa-solid fa-tablet', 'Tablet'),
    ('fa-solid fa-table', 'Table'),
    ('fa-solid fa-comment-dots', 'Comment'),
    ('fa-solid fa-message', 'Message'),
    ('fa-solid fa-poo', 'Poo'),
    ('fa-solid fa-comments', 'Comments'),
    ('fa-solid fa-envelope-circle-check', 'Evenlope Check'),
    ('fa-solid fa-envelope', 'Evenlope'),
    ('fa-solid fa-bullhorn', 'Bullhorn'),
    ('fa-solid fa-face-smile', 'Face Smile'),
]

class IconSelectWidget(forms.Select):
    template_name = 'widgets/icon_select.html'

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        # Добавляем HTML превью иконки
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        option['label'] = mark_safe(f'<i class="{value}"></i> {label}')
        return option

class PostCreationForm(forms.ModelForm):
    class Meta:
        model = ForumPost
        fields = ('content',)
        # widgets = {
        #     "content": CKEditor5Widget(config_name="default"),
        # }


class TopicCreationForm(forms.ModelForm):
    icon = forms.ChoiceField(choices=ICON_CHOICES_TOPIC, widget=IconSelectWidget(attrs={
        'class': 'select'
    }), required=False)

    title = forms.CharField(widget=forms.TextInput(attrs={
        'placeholder': 'Как назовем?',
    }))
    pinned = forms.BooleanField(widget=forms.CheckboxInput(attrs={
        'class': 'toggle'
    }), required=False)
    visible = forms.BooleanField(widget=forms.CheckboxInput(attrs={
        'class': 'toggle'
    }), required=False)
    closed = forms.BooleanField(widget=forms.CheckboxInput(attrs={
        'class': 'toggle'
    }), required=False)

    class Meta:
        model = ForumTopic
        fields = ('title', 'icon', 'pinned', 'visible', 'closed',)

class CategoryCreationForm(forms.ModelForm):
    icon = forms.ChoiceField(choices=ICON_CHOICES_CATEGORY, widget=IconSelectWidget(attrs={
        'class': 'select'
    }), required=False)

    name = forms.CharField(widget=forms.TextInput(attrs={
        'placeholder': 'Как назовем?',
    }))
    description = forms.CharField(widget=forms.TextInput(attrs={
        'placeholder': 'О чем тут будут говорить?',
    }), required=False)
    visible = forms.BooleanField(widget=forms.CheckboxInput(attrs={
        'class': 'toggle',
    }), required=False)

    class Meta:
        model = ForumCategory
        fields = ('name', 'icon', 'description', 'visible',)
