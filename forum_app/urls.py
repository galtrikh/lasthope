from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='forum'),
    path('category/<slug:cat_slug>', views.topics, name='category'),
    path('category/<slug:cat_slug>/like/', views.category_like, name='category_like'),
    path('category/<slug:cat_slug>/<int:topic_id>', views.posts, name='topic'),
    path('category/<slug:cat_slug>/<int:topic_id>/like/', views.topic_like, name='topic_like'),
    path('category/<slug:cat_slug>/<int:topic_id>/<str:flag>', views.posts_edit, name='topic_edit'),
    path('category/<slug:cat_slug>/<int:topic_id>/<int:post_id>/<str:flag>', views.post, name='post'),
    path('api/<int:topic_id>/posts/', views.posts_poll, name='posts_poll'),
]