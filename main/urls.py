from django.urls import path
from django.contrib.auth import views as auth_views
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
    path('password_reset/', 
     auth_views.PasswordResetView.as_view(
         template_name='registration/password_reset_form.html',
         html_email_template_name='registration/password_reset_email.html',
         email_template_name='registration/password_reset_email.txt',
     ), 
     name='password_reset'),
    path('password_reset/done/', 
         auth_views.PasswordResetDoneView.as_view(), 
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(), 
         name='password_reset_confirm'),
    path('reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(), 
         name='password_reset_complete')
]