from django.contrib import admin
from .models import ForumCategory, ForumTopic, ForumPost

# Register your models here.

@admin.register(ForumCategory)
class ForumCategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}

@admin.register(ForumTopic)
class ForumTopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'pinned', 'created_at')
    list_filter = ('category', 'pinned')
    readonly_fields = ('author',)
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.author = request.user
        super().save_model(request, obj, form, change)

@admin.register(ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display = ('topic', 'author', 'created_at', 'edited')
    readonly_fields = ('author',)
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.author = request.user
        super().save_model(request, obj, form, change)

# @admin.register(ForumPost)
# class PostAdmin(admin.ModelAdmin):
#     list_display = ('id', 'topic', 'author', 'created_at', 'edited')