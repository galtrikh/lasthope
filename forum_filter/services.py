import unicodedata
import re
from forum_filter.models import (
    AllowedIP,
    ModerationViolation,
    UserWarning
)
from django.contrib.auth.models import Permission
from .models import ForbiddenWord
from django.contrib.auth.models import User
from notification.services import notify, notify_bulk
from notification.models import Notification

IP_REGEX = re.compile(
    r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
)

def find_ips(text):
    return set(IP_REGEX.findall(text))

def normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))

    replacements = {
        '@': 'a',
        '0': 'o',
        '1': 'i',
        '$': 's',
        '*': '',
        ' ': '',
        '.': '',
        '-': '',
        '_': '',
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    text = re.sub(r'[^a-zа-яё]', '', text)
    return text

def contains_forbidden_words(text):
    normalized = normalize(text)

    for word in ForbiddenWord.objects.filter(enabled=True):
        w = normalize(word.word)
        if w in normalized:
            return word.word

    return None

def moderate_post(post):
    user = post.author

    # if user.is_superuser:
    #     return

    violations = []

    # IP
    ips = find_ips(post.content)
    allowed = set(AllowedIP.objects.values_list('ip', flat=True))

    for ip in ips:
        if ip not in allowed:
            violations.append(('ip', ip))

    # слова
    bad_word = contains_forbidden_words(post.content)
    if bad_word:
        violations.append(('word', bad_word))

    if not violations:
        return

    # скрываем пост
    post.visible = False
    post.save(update_fields=['visible'])

    # логируем
    for vtype, value in violations:
        ModerationViolation.objects.create(
            user=user,
            post=post,
            type=vtype,
            data={'value': value}
        )

    # предупреждение
    UserWarning.objects.create(
        user=user,
        post=post,
        reason='Нарушение правил форума'
    )

    # уведомления
    notify(
        user=user,
        type=Notification.Type.WARNING,
        actor=None,
        actor_type='system',
        data={'reason': 'Вам выдано предупреждение. Причина: Нарушение правил форума, последний пост был скрыт.'}
    )

    admins = User.objects.filter(is_staff=True)
    notify_bulk(
        users=admins,
        type=Notification.Type.MODERATION_ALERT,
        obj=post,
        actor_type='system',
        data={'author': user.username, 'post_id': post.id}
    )

    # авто-блокировка
    warnings_count = UserWarning.objects.filter(user=user).count()
    if warnings_count >= 3:
        perms = Permission.objects.filter(codename__in=['can_post', 'can_create_topic', 'can_edit_post'])
        user.user_permissions.remove(*perms)

        notify(
            user=user,
            type=Notification.Type.PERMISSION_REMOVED,
            actor=None,
            actor_type='system',
            data={'permissions': list(perms.values_list('name', flat=True))}
        )



