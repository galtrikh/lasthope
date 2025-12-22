from django.shortcuts import render
from .models import Article

def index(request):
    news = Article.objects.all().order_by('-id')
    data = {
        'news': news
    }
    return render(request, 'news/index.html', data)
