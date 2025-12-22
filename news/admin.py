from django.contrib import admin

from .models import Article, ArticleImage


class ArticleImageInline(admin.StackedInline):
    model = ArticleImage
    extra = 1

class ArticleAdmin(admin.ModelAdmin):
    inlines = [ArticleImageInline]


    def save_model(self, request, obj, form, change):
        obj.save()

        for file in request.FILES.getlist("images_multiple"):
            obj.images.create(image=file)

admin.site.register(Article, ArticleAdmin)
