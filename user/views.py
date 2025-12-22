from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required

from .forms import SignUpForm, LoginForm, EditForm
from django.contrib.auth.models import Permission

def register(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.user_permissions.add(
                Permission.objects.get(codename='can_post', content_type__app_label='forum_app'),
                Permission.objects.get(codename='can_edit_post', content_type__app_label='forum_app'),
                Permission.objects.get(codename='can_delete_post', content_type__app_label='forum_app'),
                # Permission.objects.get(codename='can_create_topic', content_type__app_label='forum_app'),
                Permission.objects.get(codename='can_vote', content_type__app_label='main')
            )
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('main')
    else:
        form = SignUpForm()
    return render(request,'user/register.html', {'form':form})

@login_required
def complete_profile(request):
    profile = request.user.profile

    if profile.servername:
        return redirect('main')

    if request.method == 'POST':
        servername = request.POST.get('servername', '').strip()
        if servername:
            profile.servername = servername
            profile.save()
            return redirect('main')

    return render(request, 'user/complete_profile.html')


def sign_in(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request=request, username=username, password=password)
            if user is not None:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                return redirect('main')
    else:
        form = LoginForm()
    return render(request, 'user/login.html', {'form':form})

@login_required
def sign_out(request):
    if request.method == 'POST':
        logout(request)
    return redirect('main')

@login_required
def user(request, username):
    UserModel = get_user_model()
    profile_user = UserModel.objects.filter(username=username).first()
    if (not profile_user):
        return redirect('main')
    is_owner = request.user == profile_user
    see_full_profile = request.user.has_perm('user.see_full_profile') and not profile_user.has_perm('user.safety')
    edit_profile = request.user.has_perm('user.edit_profile') and not profile_user.has_perm('user.safety')
    data = {
        'profile_user' : profile_user,
        'profile': profile_user.profile,
        'groups': profile_user.groups.all(),
        'is_owner': is_owner,
        'see_full_profile' : see_full_profile,
        'edit_profile': edit_profile,
        'show_menu' : False
    }
    return render(request, 'user/index.html', data)

@login_required
def notifications(request, username):
    UserModel = get_user_model()
    profile_user = UserModel.objects.filter(username=username).first()

    if not profile_user:
        return redirect('main')

    is_owner = request.user == profile_user
    see_full_profile = (
        request.user.has_perm('user.see_full_profile')
        and not profile_user.has_perm('user.safety')
    )
    edit_profile = (
        request.user.has_perm('user.edit_profile')
        and not profile_user.has_perm('user.safety')
    )

    if not is_owner and not edit_profile:
        return redirect('main')

    # 🔹 берём уведомления
    notifications_qs = profile_user.notifications.order_by('-created_at')

    # 🔹 запоминаем непрочитанные (ID)
    unread_ids = list(
        notifications_qs
        .filter(is_read=False)
        .values_list('id', flat=True)
    )

    data = {
        'profile_user': profile_user,
        'profile': profile_user.profile,
        'groups': profile_user.groups.all(),
        'is_owner': is_owner,
        'see_full_profile': see_full_profile,
        'edit_profile': edit_profile,
        'show_menu': True,
        'notifications': notifications_qs[:100],  # лимит обязателен
    }

    response = render(request, 'user/notifications.html', data)

    # ✅ ПОСЛЕ показа страницы — отмечаем прочитанными
    if unread_ids:
        profile_user.notifications.filter(id__in=unread_ids).update(is_read=True)

    return response

@login_required
def edit(request, username):
    UserModel = get_user_model()
    profile_user = UserModel.objects.filter(username=username).first()
    if (not profile_user):
        return redirect('main')
    is_owner = request.user == profile_user
    see_full_profile = request.user.has_perm('user.see_full_profile') and (not profile_user.has_perm('user.safety') or is_owner)
    edit_profile = request.user.has_perm('user.edit_profile') and (not profile_user.has_perm('user.safety') or is_owner)
    edit_user_perms = request.user.has_perm('user.edit_user_perms') and (not profile_user.has_perm('user.safety') or is_owner)
    can_edit_profile_groups = request.user.has_perm('user.can_edit_profile_gropus') and (not profile_user.has_perm('user.safety') or is_owner )
    if (not is_owner and not edit_profile):
        return redirect('main')
    if request.method == 'POST':
        form = EditForm(request.POST, request.FILES, instance=profile_user.profile, user=profile_user)
        if form.is_valid():
            form.save()
            return redirect('user', username=profile_user.username or request.user.username)
    else:
        form = EditForm(instance=profile_user.profile, user=profile_user)
    data = {
        'form' : form,
        'profile_user' : profile_user,
        'profile': profile_user.profile,
        'groups': profile_user.groups.all(),
        'is_owner': is_owner,
        'see_full_profile' : see_full_profile,
        'edit_profile': edit_profile,
        'edit_user_perms': edit_user_perms,
        'can_edit_profile_gropus' : can_edit_profile_groups,
        'show_menu' : True
    }
    return render(request, 'user/edit.html', data)