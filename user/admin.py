from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model
from user.models import Profile
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin
from .models import GroupProfile
from django.contrib import messages
from .forms import NotificationTextForm
from django.contrib.admin.sites import NotRegistered
from django.shortcuts import render

from notification.services import notify_bulk
from notification.models import Notification

User = get_user_model()

@admin.action(description='Отправить уведомление выбранным пользователям')
def send_notification(modeladmin, request, queryset):
    from django.http import HttpResponseRedirect

    # Шаг 2 — отправка
    if request.POST.get('apply'):
        form = NotificationTextForm(request.POST)
        if form.is_valid():
            notify_bulk(
                users=queryset.only('id'),
                type=Notification.Type.ADMIN,
                actor=request.user,
                data={'text': form.cleaned_data['text']}
            )

            modeladmin.message_user(
                request,
                f'Отправлено {queryset.count()} уведомлений'
            )

            return HttpResponseRedirect(request.get_full_path())

    # Шаг 1 — показ формы
    else:
        form = NotificationTextForm()

    return render(
        request,
        'admin/send_notification.html',
        {
            'form': form,
            'users': queryset,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
    )



class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


class CustomUserAdmin(UserAdmin):
    inlines = (ProfileInline,)
    actions = [send_notification]


try:
    admin.site.unregister(User)
except NotRegistered:
    pass

admin.site.register(User, CustomUserAdmin)

class GroupProfileInline(admin.StackedInline):
    model = GroupProfile
    can_delete = False
    extra = 0
    max_num = 1


class GroupAdmin(admin.ModelAdmin):
    inlines = [GroupProfileInline]


try:
    admin.site.unregister(Group)
except NotRegistered:
    pass

admin.site.register(Group, GroupAdmin)

