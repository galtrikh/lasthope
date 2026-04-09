from django.urls import path
from . import views

app_name = 'donations'

urlpatterns = [
    path('',                         views.donation_list,     name='list'),
    path('create/',                  views.donation_create,   name='create'),
    path('<int:pk>/activate/',       views.donation_activate, name='activate'),
    path('<int:pk>/complete/',       views.donation_complete,  name='complete'),
    path('donator/<str:nickname>/',  views.donator_detail,    name='donator'),

    # AJAX
    path('ajax/discount/', views.ajax_discount,          name='ajax_discount'),
    path('ajax/price/',    views.ajax_privilegion_price,  name='ajax_price'),
]
