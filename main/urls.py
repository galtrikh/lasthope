from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='main'),
    path('api/server-stats/', views.server_stats_api, name='server_stats_api'),
    path('api/server-players/', views.server_players_api, name='server_players_api'),
    path('api/server-full/', views.server_full_info, name='server_full_info'),
    path('404/', views.e404),
    path('403/', views.e403),
    path('500/', views.e500),
    path('502/', views.e502),
    path('503/', views.e503),
    path('help/', views.help_page, name="help"),
    path('about/', views.about_page, name="about"),
    path('job/', views.job_page, name="job"),
    path('contacts/', views.contacts_page, name="contacts"),
]