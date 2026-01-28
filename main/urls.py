from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='main'),
    path('404/', views.e404),
    path('help/', views.help_page, name="help"),
]