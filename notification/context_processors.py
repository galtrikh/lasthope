def notifications(request):
    if not request.user.is_authenticated:
        return {}

    qs = request.user.notifications.only(
        'id', 'type', 'is_read', 'created_at', 'data'
    )

    unread_exists = qs.filter(is_read=False).only('id')[:1].exists()

    return {
        'notifications': qs[:20],
        'notifications_unread': unread_exists,
    }
