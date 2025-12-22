from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='main'),
    path('help/', views.help_page, name="help")
]