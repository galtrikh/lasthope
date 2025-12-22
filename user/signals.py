from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from user.models import Profile
from .models import GroupProfile
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from notification.services import notify
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from core.middleware import get_current_user
from notification.models import Notification

User = get_user_model()     

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance, displayname=instance.username)

@receiver(post_save, sender=Group)
def create_group_profile(sender, instance, created, **kwargs):
    if created:
        # Создаём профиль группы с дефолтным цветом
        GroupProfile.objects.get_or_create(group=instance)


# @receiver(m2m_changed, sender=User.groups.through)
# def notify_user_groups_changed(sender, instance, action, pk_set, **kwargs):
#     """
#     instance — пользователь, которому меняют группы
#     """

#     actor = get_current_user()

#     if action == 'post_add':
#         groups = Group.objects.filter(pk__in=pk_set)
#         for group in groups:
#             notify(
#                 user=instance,
#                 type=Notification.Type.GROUP_ADDED,
#                 actor=actor,
#                 data={
#                     'group': group.name
#                 }
#             )

#     elif action == 'post_remove':
#         groups = Group.objects.filter(pk__in=pk_set)
#         for group in groups:
#             notify(
#                 user=instance,
#                 type=Notification.Type.GROUP_REMOVED,
#                 actor=actor,
#                 data={
#                     'group': group.name
#                 }
#             )

#     elif action == 'post_clear':
#         notify(
#             user=instance,
#             type=Notification.Type.GROUPS_CLEARED,
#             actor=actor,
#             data={}
#         )

# @receiver(m2m_changed, sender=User.user_permissions.through)
# def notify_user_permissions_changed(sender, instance, action, pk_set, **kwargs):
#     """
#     instance — пользователь, которому меняют права
#     """
#     actor = get_current_user()

#     if action == 'post_add':
#         perms = Permission.objects.filter(pk__in=pk_set)
#         for perm in perms:
#             notify(
#                 user=instance,
#                 type=Notification.Type.PERMISSION_ADDED,
#                 actor=actor,
#                 data={
#                     'permission': perm.name,
#                     'codename': perm.codename,
#                 }
#             )

#     elif action == 'post_remove':
#         perms = Permission.objects.filter(pk__in=pk_set)
#         for perm in perms:
#             notify(
#                 user=instance,
#                 type=Notification.Type.PERMISSION_REMOVED,
#                 actor=actor,
#                 data={
#                     'permission': perm.name,
#                     'codename': perm.codename,
#                 }
#             )

#     elif action == 'post_clear':
#         notify(
#             user=instance,
#             type=Notification.Type.PERMISSIONS_CLEARED,
#             actor=actor,
#             data={}
#         )
