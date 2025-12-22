from django.contrib import admin

# Register your models here.

from .models import SiteSettings, FooterInfo


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ('maintenance', 'updated_at')

    def has_add_permission(self, request):
        # запрещаем создавать больше одной записи
        return not SiteSettings.objects.exists()
    
@admin.register(FooterInfo)
class FooterInfoAdmin(admin.ModelAdmin):
    list_display = ('data', 'copy_data')
    fields = ('data', 'action_type', 'copy_data', 'link_data')

    class Media:
        js = ('core/admin/action_toggle.js',)