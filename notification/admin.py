from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'type',
        'actor',
        'is_read',
        'created_at'
    )

    list_filter = (
        'type',
        'is_read',
        'created_at'
    )

    search_fields = (
        'user__username',
        'actor__username',
    )

    readonly_fields = (
        'created_at',
        'is_read',
        'actor'
    )
