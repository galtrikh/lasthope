from django.contrib import admin
from .models import VoteBox, VoteBoxItem, VoteBoxVote, MainBanner, HelpAccardion, MainRules
from django.utils.html import format_html

# Register your models here.

@admin.register(VoteBox)
class VoteBoxAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'created_at')
    list_filter = ('title',)
    readonly_fields = ('author', 'notified_finished', 'winner')
    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))

        if obj:
            fields += [
                'title',
                'multiple'
                   # ← любое количество полей
            ]

        if obj and obj.notified_finished:
            fields.append('active')

        return fields

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.author = request.user
        super().save_model(request, obj, form, change)

@admin.register(VoteBoxItem)
class VoteBoxItemAdmin(admin.ModelAdmin):
    list_display = ('box', 'text',)
    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))

        if obj:
            fields += [
                'text',
                'box'   # ← любое количество полей
            ]
        return fields


@admin.register(MainBanner)
class MainBannerAdnim(admin.ModelAdmin):
    list_display = ('image', 'width', 'hidden')
    exclude = ('image_small',)
    readonly_fields = ('preview',)
    def preview(self, obj):
        if obj.image_small:
            return format_html(
                '<img src="{}" style="max-height:200px;">',
                obj.image_small.url
            )
        return '—'
    preview.short_description = 'Миниатюра'

    def has_add_permission(self, request):
        # запрещаем создавать больше одной записи
        return not MainBanner.objects.exists()

@admin.register(VoteBoxVote)
class VoteBoxVoteAdmin(admin.ModelAdmin):
    list_display = ('user', 'box', 'item')
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(HelpAccardion)
class HelpAccardionAdmin(admin.ModelAdmin):
    list_display = ('question', 'text')

@admin.register(MainRules)
class MainRulesAdmin(admin.ModelAdmin):
    list_display = ('text',)