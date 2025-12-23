from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, UserChangeForm
from django.contrib.auth.models import User
from user.models import Profile
from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from django.contrib.auth.models import Group, Permission
from core.middleware import get_current_user
from notification.services import notify
from notification.models import Notification
from django.core.exceptions import ValidationError

class SignUpForm(UserCreationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'id': 'name',
            'class': 'bg-blue-50 p-2 px-4 rounded-full border-2 border-sky-900 text-black w-full',
            'autofocus': 'autofocus',
        })
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'bg-blue-50 p-2 px-4 rounded-full border-2 border-sky-900 text-black w-full',
            'placeholder': 'От 8 символов'
        })
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'bg-blue-50 p-2 px-4 rounded-full border-2 border-sky-900 text-black w-full',
            'placeholder': 'Проверь раскладку клавиатуры'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'password1', 'password2')

class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'id': 'username',
        'class': 'bg-blue-50 p-2 px-4 rounded-full border-2 border-sky-900 text-black w-full',  
        'autofocus': 'autofocus',
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'id': 'password',
        'class': 'bg-blue-50 p-2 px-4 rounded-full border-2 border-sky-900 text-black w-full',
        'placeholder': 'Проверь раскладку клавиатуры'
    }))

EDITABLE_PERMISSIONS = [
    ('forum_app', 'can_post'),
    ('forum_app', 'can_edit_post'),
    ('forum_app', 'can_delete_post'),
    #('forum_app', 'can_create_topic'),
    ('main', 'can_vote'),
]

def allowed_permissions_qs():
    q = Q()
    for app, codename in EDITABLE_PERMISSIONS:
        q |= Q(
            codename=codename,
            content_type__app_label=app
        )
    return Permission.objects.filter(q)

class EditForm(forms.ModelForm):
    displayname = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'id': 'displayname',
        'class': 'bg-blue-50 p-2 px-4 rounded-full border-2 border-sky-900 text-black w-full'
    }))
    servername = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'id': 'servername',
        'class': 'bg-blue-50 p-2 px-4 rounded-full border-2 border-sky-900 text-black w-full'
    }))
    bio = forms.CharField(required=False, widget=forms.Textarea(attrs={
        'id': 'bio',
        'class': 'bg-blue-50 p-2 px-4 rounded-3xl border-2 border-sky-900 text-black w-full',
        'rows' : 5
    }))
    avatar = forms.ImageField(required=False, widget=forms.FileInput(attrs={
        'id': 'avatar',
        'class': 'bg-blue-50 p-2 px-4 rounded-full border-2 border-sky-900 text-black w-fit bg-sky-500 hover:bg-sky-700 cursor-pointer block',
        'accept': 'image/png, image/jpeg, image/bmp, image/gif'
    }))
    groups = forms.ModelMultipleChoiceField(
    queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'id': 'groups',
            'class': ''
    }))
    permissions = forms.ModelMultipleChoiceField(
        queryset=allowed_permissions_qs(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    def clean_file(self):
        file = self.cleaned_data['avatar']
        max_size = 1 * 1024 * 1024  # 1 MB
        if file.size > max_size:
            raise ValidationError("Файл слишком большой (макс 1MB)")
        return file

    class Meta:
        model = Profile
        fields = ('displayname', 'bio', 'avatar')  # только поля Profile

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # передаём user при инициализации
        super().__init__(*args, **kwargs)

        actor = get_current_user()
        is_owner = actor == user
        edit_user_perms = actor.has_perm('user.edit_user_perms') and (not user.has_perm('user.safety') or is_owner)
        can_edit_profile_groups = actor.has_perm('user.can_edit_profile_gropus') and (not user.has_perm('user.safety') or is_owner )

        if not can_edit_profile_groups:
            self.fields.pop('groups', None)

        if not edit_user_perms:
            self.fields.pop('permissions', None)

        if user:
            self._initial_groups = set(
                user.groups.values_list('id', flat=True)
            )
            self._initial_perms = set(
                user.user_permissions.values_list('id', flat=True)
            )
            if user and 'groups' in self.fields:
                self.fields['groups'].initial = [g.pk for g in user.groups.all()]
            if user and 'permissions' in self.fields:
                self.fields['permissions'].initial = (
                    user.user_permissions
                    .filter(id__in=allowed_permissions_qs())
                    .values_list('id', flat=True)
                )
                self.fields['permissions'].label_from_instance = (
                lambda perm: perm.name
                )

    def _notify_changes(
        self,
        user,
        added_groups,
        removed_groups,
        added_perms,
        removed_perms
        ):

        actor = get_current_user()

        if added_groups:
            notify(
                user=user,
                actor=actor,
                type=Notification.Type.GROUP_ADDED,
                data={
                    'groups': list(
                        Group.objects.filter(id__in=added_groups)
                        .values_list('name', flat=True)
                    )
                }
            )

        if removed_groups:
            notify(
                user=user,
                actor=actor,
                type=Notification.Type.GROUP_REMOVED,
                data={
                    'groups': list(
                        Group.objects.filter(id__in=removed_groups)
                        .values_list('name', flat=True)
                    )
                }
            )

        if added_perms:
            notify(
                user=user,
                actor=actor,
                type=Notification.Type.PERMISSION_ADDED,
                data={
                    'permissions': list(
                        Permission.objects.filter(id__in=added_perms)
                        .values_list('name', flat=True)
                    )
                }
            )

        if removed_perms:
            notify(
                user=user,
                actor=actor,
                type=Notification.Type.PERMISSION_REMOVED,
                data={
                    'permissions': list(
                        Permission.objects.filter(id__in=removed_perms)
                        .values_list('name', flat=True)
                    )
                }
            )


    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user

        # --- GROUPS ---
        if 'groups' in self.fields:
            new_groups = set(
                self.cleaned_data.get('groups', [])
                .values_list('id', flat=True)
            )
        else:
            new_groups = self._initial_groups

        added_groups = new_groups - self._initial_groups
        removed_groups = self._initial_groups - new_groups

        # --- PERMISSIONS ---
        if 'permissions' in self.fields:
            new_perms = set(
                self.cleaned_data.get('permissions', [])
                .values_list('id', flat=True)
            )
        else:
            new_perms = self._initial_perms

        added_perms = new_perms - self._initial_perms
        removed_perms = self._initial_perms - new_perms

        if commit:
            profile.save()

            # применяем только если поле было
            if 'groups' in self.fields:
                user.groups.set(new_groups)

            if 'permissions' in self.fields:
                user.user_permissions.set(new_perms)

            user.save()

            # уведомляем только если есть изменения
            if added_groups or removed_groups or added_perms or removed_perms:
                self._notify_changes(
                    user,
                    added_groups,
                    removed_groups,
                    added_perms,
                    removed_perms
                )

        return profile
    
class NotificationTextForm(forms.Form):
    text = forms.CharField(
        label='Текст уведомления',
        widget=forms.Textarea
    )