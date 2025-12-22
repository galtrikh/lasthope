from django.contrib import admin
from django.db import models
import datetime

def article_cover_path(instance, filename):
    return f"articles/{instance.id}/cover/{filename}"


def article_gallery_path(instance, filename):
    return f"articles/{instance.article.id}/gallery/{filename}"

class Article(models.Model):
    title = models.CharField('Заголовок', max_length=255)
    text = models.TextField('Текст новости')
    cover = models.ImageField('Обложка новости', upload_to=article_cover_path, blank=True, null=True)
    date = models.DateField('Дата', auto_now_add=True)

    def __str__(self):
        return f"[{self.date}] {self.title}"

    class Meta:
        verbose_name = "Новость"
        verbose_name_plural = "Новости"

class ArticleImage(models.Model):
    article = models.ForeignKey(
        Article,
        related_name="images",
        on_delete=models.CASCADE,
        verbose_name="Картинка",
    )
    image = models.ImageField(upload_to=article_gallery_path, blank=True, null=True, verbose_name='Картинка')

    def __str__(self):
        return f"Картинка для {self.article.title}"

    class Meta:
        verbose_name = "Картинка"
        verbose_name_plural = "Картинки"