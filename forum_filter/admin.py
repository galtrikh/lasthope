from django.contrib import admin
from .models import ForbiddenWord, AllowedIP, UserWarning

# Register your models here.

@admin.register(ForbiddenWord)
class ForbiddenWordAdmin(admin.ModelAdmin):
    list_display = ('word', 'enabled')
    list_editable = ('enabled',)


@admin.register(AllowedIP)
class AllowedIPAdmin(admin.ModelAdmin):
    list_display = ('ip', 'comment')

@admin.register(UserWarning)
class UserWarningAdmin(admin.ModelAdmin):
    list_display = ('user', 'reason', 'created_at')