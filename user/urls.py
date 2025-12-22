from django.urls import path
from . import views

urlpatterns = [
    # path('', views.index, name='user'),
    # path('notifications', views.notifications, name='notifications'),
    # path('edit', views.edit, name='edit'),
    path('register', views.register, name='register'),
    path('complete-profile/', views.complete_profile, name='complete_profile'),
    path('login', views.sign_in, name='login'),
    path('logout', views.sign_out, name='logout'),
    path('<str:username>', views.user, name='user'),
    path('<str:username>/notifications', views.notifications, name='notifications'),
    path('<str:username>/edit', views.edit, name='edit'),
]