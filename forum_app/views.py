from dataclasses import dataclass
from django.shortcuts import render, redirect, get_object_or_404
from rest_framework import request
from .models import ForumCategory, ForumTopic, ForumPost, ForumCategoryLike, ForumTopicLike, ForumPostLike
import markdown
from .templatetags import forum_filters
from django.urls import reverse
from django.http import JsonResponse
from forum_app.models import ForumPost
from forum_app.froms import PostCreationForm, TopicCreationForm, CategoryCreationForm
from django.utils.dateparse import parse_datetime
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from notification.services import notify
from notification.models import Notification
from forum_filter.services import moderate_post
from django.views.decorators.http import require_POST
from django.db.models import Exists, OuterRef, Value, BooleanField
from django.utils.text import slugify, Truncator
from django.utils.html import strip_tags
from bs4 import BeautifulSoup
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

POSTS_LIMIT = 1

# Create your views here.

def get_topic_flags(user, topic):
    is_auth = user.is_authenticated
    is_owner = is_auth and user == topic.author
    is_super = is_auth and user.is_superuser

    author_protected = (
        topic.author.has_perm('user.safety')
        if topic.author.is_authenticated
        else False
    )

    def allowed(perm):
        if not user.has_perm(perm):
            return False
        if is_super or is_owner:
            return True
        return not author_protected

    return {
        'is_auth': is_auth,
        'is_owner': is_owner,

        'can_post': user.has_perm('forum_app.can_post'),
        'can_post_closed': user.has_perm('forum_app.can_post_closed'),

        'can_create_topic': user.has_perm('forum_app.can_create_topic'),

        'can_close_topic': allowed('forum_app.can_close_topic'),
        'can_pin_topic': allowed('forum_app.can_pin_topic'),
        'can_delete_topic': allowed('forum_app.can_delete_topic'),
        'can_hide_topic': allowed('forum_app.can_hide_topic'),
    }

def index(request):
    if request.user.has_perm('forum_app.can_see_hidden_cats'):
        categories = ForumCategory.objects.all()
    else:
        categories = ForumCategory.objects.filter(visible=True)
        

    if request.method == "POST":
        if request.user.has_perm('forum_app.can_hide_cats'):
            if request.GET.get("hide"):
                category = ForumCategory.objects.get(id=request.GET.get("hide"))
                category.visible = False
                category.save()
                return redirect('forum')
            if request.GET.get("show"):
                category = ForumCategory.objects.get(id=request.GET.get("show"))
                category.visible = True
                category.save()
                return redirect('forum')
        if request.GET.get("delete") and request.user.has_perm('forum_app.can_delete_cats'):
            category = ForumCategory.objects.get(id=request.GET.get("delete"))
            category.delete()
            return redirect('forum')
        if not request.user.has_perm('forum_app.can_create_cats'):
            return HttpResponseForbidden()
        form = CategoryCreationForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.author = request.user
            category.slug = slugify(category.name)
            category.save()
            return redirect(category.get_absolute_url())
    else:
        form = CategoryCreationForm()

    if request.user.is_authenticated:
        categories = categories.annotate(
            is_liked=Exists(
                ForumCategoryLike.objects.filter(
                    user=request.user,
                    category=OuterRef('pk')
                )
            )
        )
    else:
        categories = categories.annotate(
            is_liked=Value(False, output_field=BooleanField())
        )
    data = {
        'categories' : categories,
        'form': form
    }
    return render(request, 'forum_app/index.html', data)

def topics(request, cat_slug):
    category = ForumCategory.objects.get(slug=cat_slug)
    if request.method == "POST":
        if not request.user.has_perm('forum_app.can_create_topic'):
            return HttpResponseForbidden()
        form = TopicCreationForm(request.POST)
        if form.is_valid():
            topic = form.save(commit=False)
            topic.author = request.user
            topic.category = category
            topic.save()
            return redirect(topic.get_absolute_url())
    else:
        form = TopicCreationForm()

    if request.user.has_perm('forum_app.can_see_hidden_topics'):
        topicslist = ForumTopic.objects.filter(category=category).order_by('-pinned', 'id')
    else:
        topicslist = ForumTopic.objects.filter(visible=True, category=category).order_by('-pinned', 'id')

    if request.user.is_authenticated:
        topicslist = topicslist.annotate(
            is_liked=Exists(
                ForumTopicLike.objects.filter(
                    user=request.user,
                    topic=OuterRef('pk')
                )
            )
        )
    else:
        topicslist = topicslist.annotate(
            is_liked=Value(False, output_field=BooleanField())
        )

    topics_with_flags = []

    for topic in topicslist:
        topic.flag = get_topic_flags(request.user, topic)
        topics_with_flags.append(topic)

    paginator = Paginator(topics_with_flags, 6)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    data = {
        'category' : category,
        'topics' : page_obj,
        'topics_count': len(topicslist),
        'form': form
    }
    return render(request, 'forum_app/topics.html', data)

@login_required
@require_POST
def category_like(request, cat_slug):
    category = ForumCategory.objects.get(slug=cat_slug)

    like, created = ForumCategoryLike.objects.get_or_create(
        user=request.user,
        category=category
    )

    if created:
        liked = True
    else:
        like.delete()
        liked = False

    return JsonResponse({
        'liked': liked,
        'likes_count': category.likes.count()
    })

@login_required
@require_POST
def topic_like(request, cat_slug, topic_id):
    topic = ForumTopic.objects.get(id=topic_id)

    like, created = ForumTopicLike.objects.get_or_create(
        user=request.user,
        topic=topic
    )

    if created:
        liked = True
    else:
        like.delete()
        liked = False

    return JsonResponse({
        'liked': liked,
        'likes_count': topic.likes.count()
    })

def get_post_page(*, topic, post, per_page):
    qs = topic.posts.order_by('-pinned', 'id').values_list('id', flat=True)

    try:
        index = list(qs).index(post.id)
    except ValueError:
        return 1

    return index // per_page + 1

@dataclass
class PostFlags():
    is_owner:bool
    can_dropdown:bool
    can_edit:bool
    can_delete:bool
    can_really_delete:bool
    can_hide:bool
    can_pin:bool
    is_guarded:bool

@dataclass
class PostsPageFlags():
    can_post:bool
    can_dropdown:bool
    can_close_topic:bool
    can_pin_topic:bool
    can_delete_topic:bool
    can_hide_topic:bool
   

def get_post_flags(user_ctx, post, is_owner=None) -> PostFlags:
    if is_owner is None:
        is_owner = user_ctx['user_id'] == post.author.id

    is_super  = user_ctx.get('is_super', False)
    perms     = user_ctx['perms']
    is_guarded = 'user.safety' in post.author.get_all_permissions()

    # Суперпользователь видит всё, кроме защищённых пользователей
    if is_super and not is_guarded:
        return PostFlags(
            is_owner=is_owner,
            is_guarded=False,
            can_edit=True,
            can_delete=True,
            can_really_delete=True,
            can_hide=True,
            can_pin=True,
            can_dropdown=True,
        )

    # Обычная логика для всех остальных
    can_edit = (
        'forum_app.can_edit_post' in perms
        and (is_owner or 'forum_app.can_edit_another_post' in perms)
        and not is_guarded
    )
    can_delete = (
        'forum_app.can_delete_post' in perms
        and (is_owner or 'forum_app.can_edit_another_post' in perms)
        and not is_guarded
    )
    can_really_delete = (
        'forum_app.can_true_delete_post' in perms
        and not is_guarded
    )
    can_hide = (
        'forum_app.can_see_hidden_post' in perms
        and (is_owner or 'forum_app.can_edit_another_post' in perms)
        and not is_guarded
    )
    can_pin = (
        'forum_app.can_pin_post' in perms
        and (is_owner or 'forum_app.can_edit_another_post' in perms)
    )
    can_dropdown = can_edit or can_delete or can_really_delete or can_hide or can_pin

    return PostFlags(
        is_owner=is_owner,
        is_guarded=is_guarded,
        can_edit=can_edit,
        can_delete=can_delete,
        can_really_delete=can_really_delete,
        can_hide=can_hide,
        can_pin=can_pin,
        can_dropdown=can_dropdown,
    )


def get_posts_page_flags(user_ctx, topic) -> PostsPageFlags:
    perms = user_ctx['perms']
    is_t_author = user_ctx['user_id'] == topic.author.id
    t_guarded = 'user.safety' in topic.author.get_all_permissions()
    can_post = (
        'forum_app.can_post' in perms
        and (not topic.closed or 'forum_app.can_post_closed' in perms)
    )
    can_close_topic = (
        'forum_app.can_close_topic' in perms
        and (is_t_author or not t_guarded)
    )
    can_pin_topic = (
        'forum_app.can_pin_topic' in perms
        and (is_t_author or not t_guarded)
    )
    can_delete_topic = (
        'forum_app.can_delete_topic' in perms
        and (is_t_author or not t_guarded)
    )
    can_hide_topic = (
        'forum_app.can_hide_topic' in perms
        and (is_t_author or not t_guarded)
    )
    can_dropdown = (
        can_close_topic or
        can_pin_topic or
        can_delete_topic or
        can_hide_topic
    )
    return PostsPageFlags(
        can_post=can_post,
        can_close_topic=can_close_topic,
        can_pin_topic=can_pin_topic,
        can_delete_topic=can_delete_topic,
        can_hide_topic=can_hide_topic,
        can_dropdown=can_dropdown
    )



def get_posts_cursor(*, topic, user=None, before_id=None, after_id=None, limit=20):
    """Cursor-based пагинация с поддержкой пиннинга."""
    
    qs = ForumPost.objects.filter(
        topic=topic,
        pinned=False,      # закреплённые грузим отдельно
        visible=True,
    ).select_related(
        'author', 'author__profile', 'parent', 'parent__author'
    ).prefetch_related('author__groups')
    
    if user and user.is_authenticated:
        qs = qs.annotate(is_liked_by_user=Exists(
            ForumPostLike.objects.filter(user=user, post=OuterRef('pk'))
        ))
    
    # КРИТИЧНО: базовая сортировка (закреплённые сверху, потом по ID вниз)
    # Для cursor pagination НЕ ДОЛЖНО быть пиннинга в запросе
    # Пиннинг — это UI-фича, которую нужно обрабатывать отдельно
    
    if before_id:
        # Загружаем посты СТАРШЕ (ID < before_id), берём limit+1 для has_more
        qs = qs.filter(id__lt=before_id).order_by('-id')[:limit + 1]
        posts = list(qs)
        has_older = len(posts) > limit
        if has_older:
            posts = posts[:limit]
        posts.reverse()  # В обратный порядок (ID растёт вниз)
        return posts, has_older, True  # (posts, has_older, has_newer)
        
    elif after_id:
        # Загружаем посты НОВЕЕ (ID > after_id)
        qs = qs.filter(id__gt=after_id).order_by('id')[:limit + 1]
        posts = list(qs)
        has_newer = len(posts) > limit
        if has_newer:
            posts = posts[:limit]
        return posts, True, has_newer  # (posts, has_older, has_newer)
        
    else:
        # Первая загрузка — последние N постов
        qs = qs.order_by('-id')[:limit + 1]
        posts = list(qs)
        has_older = len(posts) > limit
        if has_older:
            posts = posts[:limit]
        posts.reverse()
        return posts, has_older, False  # (posts, has_older, has_newer)

def posts(request, cat_slug, topic_id):
    """
    Отображение постов в теме.
    GET  ?before=<id>  — cursor pagination: старше (HTMX)
    GET  ?after=<id>   — cursor pagination: новее  (HTMX)
    GET  (без параметров) — первые N постов (начало темы)
    """
    category = get_object_or_404(ForumCategory, slug=cat_slug)
    topic    = get_object_or_404(ForumTopic, id=topic_id)

    before_id = request.GET.get('before')
    after_id  = request.GET.get('after')
    
    # Закреплённые — всегда отдельно, только на первой загрузке
    pinned_posts = []
    if not before_id and not after_id:
        pinned_posts = list(
            ForumPost.objects.filter(topic=topic, pinned=True, visible=True)
            .select_related('author', 'author__profile', 'parent', 'parent__author')
            .prefetch_related('author__groups')
        )
    
    posts_list, has_older, has_newer = get_posts_cursor(
        topic=topic, user=request.user,
        before_id=before_id, after_id=after_id, limit=20,
    )
    
    # Убираем закреплённые из основного потока чтобы не дублировать
    pinned_ids = {p.id for p in pinned_posts}
    posts_list = [p for p in posts_list if p.id not in pinned_ids]

    if request.method == 'POST' and request.htmx:
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        if not request.user.has_perm('forum_app.can_post') or (topic.closed and not request.user.has_perm('forum_app.can_post_closed')):
            return HttpResponseForbidden()
        
        content = request.POST.get('content', '').strip()
        parent_id = request.POST.get('parent_id') or None
        
        if not content:
            return JsonResponse({'error': 'Пустой пост'}, status=400)
        
        post = ForumPost.objects.create(
            topic=topic,
            author=request.user,
            content=content,
            parent_id=parent_id,
        )
        moderate_post(post)
        
        # WebSocket — уведомление всем
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'topic_{topic_id}',
            {
                'type': 'new_post',
                'post_id': post.id,
                'author': post.author.profile.displayname,
                'content_preview': post.content[:100],
            }
        )
        
        user_ctx = {
            'user_id': request.user.id if request.user.is_authenticated else None,
            'perms':   request.user.get_all_permissions() if request.user.is_authenticated else set(),
            'is_super': request.user.is_superuser if request.user.is_authenticated else False,
            }

        post.flag = get_post_flags(user_ctx=user_ctx, post=post, is_owner=True)
        post.is_liked_by_user = False
        flags = get_posts_page_flags(user_ctx=user_ctx, topic=topic)
        form = PostCreationForm(request.POST)

        return render(request, 'forum_app/forum_post.html', {
            'post': post,
            'category': category,
            'topic': topic,
            'flags': flags,
            'form': form,
        })

    # Фильтрация скрытых для обычных пользователей
    if not request.user.has_perm('forum_app.can_see_hidden_post'):
        posts_list = [p for p in posts_list if p.visible]

    # Превью родительских постов
    for post in posts_list:
        if not post.parent:
            continue
        clean_parent  = forum_filters.safe_html(post.parent.content)
        text_parent   = strip_tags(clean_parent)
        post.parent_preview = Truncator(text_parent).chars(160, truncate='…')
        soup = BeautifulSoup(clean_parent, 'html.parser')
        indicators = []
        if soup.find('img'):
            indicators.append('<span><i class="fa-solid fa-image"></i> изображение</span>')
        if soup.find('table'):
            indicators.append('<span><i class="fa-solid fa-table"></i> таблица</span>')
        if soup.find('iframe'):
            indicators.append('<span><i class="fa-solid fa-film"></i> медиа</span>')
        post.indicators = indicators

    # Контекст прав
    user_ctx = {
        'user_id': request.user.id if request.user.is_authenticated else None,
        'perms':   request.user.get_all_permissions() if request.user.is_authenticated else set(),
        'is_super': request.user.is_superuser if request.user.is_authenticated else False,
    }

    flags = get_posts_page_flags(user_ctx=user_ctx, topic=topic)

    if request.user.is_authenticated:
        for post in posts_list:
            post.flag = get_post_flags(
                user_ctx=user_ctx,
                post=post,
                is_owner=(request.user.id == post.author.id),
            )
            if not hasattr(post, 'is_liked_by_user'):
                post.is_liked_by_user = False
    else:
        for post in posts_list:
            # Анонимам — пустые флаги
            from dataclasses import fields
            post.flag = PostFlags(**{f.name: False for f in fields(PostFlags)})
            post.is_liked_by_user = False

    context = {
        'posts':     posts_list,
        'category':  category,
        'topic':     topic,
        'flags':     flags,
        'has_older': has_older,
        'has_newer': has_newer,
        'min_id':    posts_list[0].id  if posts_list else None,
        'max_id':    posts_list[-1].id if posts_list else None,
        'edit_post_id': None,  # для совместимости со старым шаблоном
        'form': PostCreationForm(),
    }

    # HTMX запрос → partial (только список постов)
    if request.htmx:
        return render(request, 'forum_app/partials/posts_list.html', context)

    # Полная страница
    return render(request, 'forum_app/posts.html', context)

# def posts(request, cat_slug, topic_id):
#     """
#     Отображение постов в теме
#     """
# def posts(request, cat_slug, topic_id):
#     category = get_object_or_404(ForumCategory, slug=cat_slug)
#     topic = get_object_or_404(ForumTopic, id=topic_id)
    
#     before_id = request.GET.get('before')
#     after_id = request.GET.get('after')
    
#     posts_list, has_older, has_newer = get_posts_cursor(
#         topic=topic,
#         user=request.user,
#         before_id=before_id,
#         after_id=after_id,
#         limit=20
#     )
    
#     # Фильтруем скрытые
#     if not request.user.has_perm('forum_app.can_see_hidden_post'):
#         posts_list = [p for p in posts_list if p.visible]

#     for post in posts_list:
#         if not post.parent: 
#             continue
#         # Безопасный HTML для превью родителя
#         clean_parent = forum_filters.safe_html(post.parent.content)
#         text_parent = strip_tags(clean_parent)
#         post.parent_preview = Truncator(text_parent).chars(160, truncate='…')
#         soup = BeautifulSoup(clean_parent, 'html.parser')
#         has_image = bool(soup.find('img'))
#         has_table = bool(soup.find('table'))
#         has_iframe = bool(soup.find('iframe'))
#         indicators = []
#         if has_image:
#             indicators.append('<span><i class="fa-solid fa-image"></i> изображение</span>')
#         if has_table:
#             indicators.append('<span><i class="fa-solid fa-table"></i> таблица</span>')
#         if has_iframe:
#             indicators.append('<span><i class="fa-solid fa-iframe"></i> iframe</span>')
#         post.indicators = indicators
    
#     # Контекст пользователя для прав доступа
#     user_ctx = {
#         'user_id': request.user.id if request.user.is_authenticated else None,
#         'perms': request.user.get_all_permissions() if request.user.is_authenticated else set()
#     }
    
#     # Флаги для страницы
#     flags = get_posts_page_flags(user_ctx=user_ctx, topic=topic)
    
#     # Добавляем флаги для каждого поста
#     if request.user.is_authenticated:
#         for post in posts_list:
#             post.flag = get_post_flags(
#                 user_ctx=user_ctx,
#                 post=post,
#                 is_owner=(request.user == post.author)
#             )
#             # is_liked уже добавлен через annotate, но для совместимости:
#             if not hasattr(post, 'is_liked_by_user'):
#                 post.is_liked_by_user = False
    
#     context = {
#         'posts': posts_list,
#         'category': category,
#         'topic': topic,
#         'flags': flags,
#         'has_older': has_older,
#         'has_newer': has_newer,
#         'min_id': posts_list[0].id if posts_list else None,
#         'max_id': posts_list[-1].id if posts_list else None,
#     }
    
#     # Выбираем шаблон в зависимости от типа запроса
#     template = (
#         'forum_app/posts.html'  # ← используем ОДИН шаблон
#         if not request.htmx     # если НЕ htmx — полная страница
#         else 'forum_app/partials/posts_list.html'  # если htmx — только список
#     )
#     return render(request, template, context)

    # POSTS_PER_PAGE = 20
    # category = ForumCategory.objects.get(slug=cat_slug)
    # topic = ForumTopic.objects.get(id=topic_id)

    # edit_post_id = request.GET.get("edit")
    # edit_post = None

    # if edit_post_id:
    #     edit_post = get_object_or_404(
    #         ForumPost,
    #         id=edit_post_id,
    #         author=request.user
    #     )

    # if request.user.has_perm('forum_app.can_see_hidden_post'):
    #     postslist = ForumPost.objects.filter(topic=topic).order_by('-pinned', 'id')
    # else:
    #     postslist = ForumPost.objects.filter(visible=True, topic=topic).order_by('-pinned', 'id')

    # if request.user.is_authenticated:
    #     postslist = postslist.annotate(
    #         is_liked=Exists(
    #             ForumPostLike.objects.filter(
    #                 user=request.user,
    #                 post=OuterRef('pk')
    #             )
    #         )
    #     )
    # else:
    #     postslist = postslist.annotate(
    #         is_liked=Value(False, output_field=BooleanField())
    #     )

    # posts = []
    # for post in postslist:
    #     post.content = forum_filters.safe_html(post.content)

    #     is_owner = request.user == post.author

    #     can_edit = (
    #         is_owner
    #         or request.user.has_perm('forum_app.can_edit_another_post')
    #     ) and not post.author.has_perm('user.safety')

    #     can_delete = (
    #         request.user.has_perm('forum_app.can_delete_post')
    #         or (
    #             is_owner and request.user.has_perm('forum_app.can_delete_own_post')
    #         )
    #     ) and not post.author.has_perm('user.safety')

    #     can_pin = request.user.has_perm('forum_app.can_pin_post')

    #     is_safety = not request.user.is_superuser and post.author.has_perm('user.safety')

    #     parent_preview = None
    #     parent_url = None
    #     meta = ''
    #     if post.parent:
    #         clean_parent = forum_filters.safe_html(post.parent.content)
    #         text_parent = strip_tags(clean_parent)

    #         parent_preview = Truncator(text_parent).chars(
    #             160,
    #             truncate='…'
    #         )

    #         soup = BeautifulSoup(clean_parent, 'html.parser')

    #         has_image = bool(soup.find('img'))
    #         has_table = bool(soup.find('table'))
    #         has_iframe = bool(soup.find('iframe'))

    #         indicators = []
    #         if has_image:
    #             indicators.append('<span><i class="fa-solid fa-image"></i> изображение</span>')
    #         if has_table:
    #             indicators.append('<span><i class="fa-solid fa-table"></i> таблица</span>')
    #         if has_iframe:
    #             indicators.append('<span><i class="fa-solid fa-film"></i> медиа</span>')

    #         meta = ' · '.join(indicators) if indicators else None

    #         page = get_post_page(
    #             topic=topic,
    #             post=post.parent,
    #             per_page=POSTS_PER_PAGE
    #         )

    #         parent_url = (
    #             f"{reverse('topic', kwargs={'cat_slug': category.slug, 'topic_id': topic.id})}"
    #             f"?page={page}#post-id-{post.parent.id}"
    #         )
    #     posts.append({
    #         'obj': post,
    #         'parent_preview': parent_preview,
    #         'parent_meta': meta,
    #         'parent_url': parent_url,
    #         'is_owner': is_owner,
    #         'can_edit': can_edit,
    #         'can_delete': can_delete,
    #         'can_pin': can_pin,
    #         'is_safety': is_safety
    #     })
        
    
    # flags = {
    #     'is_auth': request.user.is_authenticated,
    #     'can_post': request.user.has_perm('forum_app.can_post'),
    #     'can_post_closed': request.user.has_perm('forum_app.can_post_closed'),
    #     'is_owner': request.user == topic.author,
    #     'can_close_topic': request.user.has_perm('forum_app.can_close_topic') and (not topic.author.has_perm('user.safety') or request.user == topic.author) or request.user.is_superuser,
    #     'can_pin_topic': request.user.has_perm('forum_app.can_pin_topic') and (not topic.author.has_perm('user.safety') or request.user == topic.author ) or request.user.is_superuser,
    #     'can_delete_topic': request.user.has_perm('forum_app.can_delete_topic') and (not topic.author.has_perm('user.safety') or request.user == topic.author ) or request.user.is_superuser,
    #     'can_hide_topic': request.user.has_perm('forum_app.can_hide_topic') and (not topic.author.has_perm('user.safety') or request.user == topic.author ) or request.user.is_superuser,
    #     'can_hide_post': request.user.has_perm('forum_app.can_hide_post'),
    #     'can_pin_post': request.user.has_perm('forum_app.can_pin_post'),
    #     'can_edit_post': request.user.has_perm('forum_app.can_edit_post'),
    #     'can_edit_another_post': request.user.has_perm('forum_app.can_edit_another_post'),
    #     'can_delete_post': request.user.has_perm('forum_app.can_delete_post'),
    #     'can_really_delete_post': request.user.has_perm('forum_app.can_really_delete_post'),
    # }

    # paginator = Paginator(posts, POSTS_PER_PAGE)
    # page_number = request.GET.get('page')
    # page_obj = paginator.get_page(page_number)

    # if request.htmx:
    #     if edit_post:
    #         form = PostCreationForm(
    #             request.POST,
    #             request.FILES,
    #             instance=edit_post
    #         )
    #     else:
    #         form = PostCreationForm(request.POST, request.FILES)
    #     parent = None
    #     parent_id = request.POST.get("parent_id")

    #     if parent_id:
    #         parent = get_object_or_404(
    #             ForumPost,
    #             id=parent_id,
    #             topic=topic
    #         )
    #     # form = PostCreationForm(request.POST, request.FILES)
    #     if form.is_valid():
    #         post = form.save(commit=False)
    #         post.topic = topic
    #         post.author = request.user
    #         if not post.parent:
    #             post.parent = parent
    #         if edit_post:
    #             post.edited = True
    #         post.save()
    #         moderate_post(post)
    #         posts_qs = topic.posts.order_by('created_at')  # важно: тот же order_by
    #         paginator = Paginator(posts_qs, POSTS_PER_PAGE)

    #         last_page = paginator.num_pages
    #         context = {
    #             'post': post,
    #             'flags': flags,
    #             'edit_post_id': edit_post_id
    #         }
    #         return render(request, 'forum_app/partials/forum_post_p.html', context)
    #         # return redirect(f"{reverse('topic', kwargs={'cat_slug': category.slug, 'topic_id': topic.id})}?page={last_page}#post-id-{post.id}")
    # else:
    #     if edit_post:
    #         form = PostCreationForm(instance=edit_post)
    #     else:
    #         form = PostCreationForm()

    # data = {
    #     'category' : category,
    #     'topic' : topic,
    #     'posts' : page_obj,
    #     'posts_count': len(posts),
    #     'form' : form,
    #     'flags': flags,
    #     'edit_post_id': edit_post.id if edit_post else None
    # }
    # return render(request, 'forum_app/posts.html', data)

@login_required
def toggle_like(request, cat_slug, topic_id, post_id):
    """
    Переключение лайка (будет работать с WebSocket для живого обновления счетчика)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    post = get_object_or_404(ForumPost, id=post_id, topic_id=topic_id)
    
    like, created = ForumPostLike.objects.get_or_create(
        user=request.user,
        post=post
    )
    
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
    
    # Обновляем счетчик
    likes_count = post.likes.count()
    
    # Отправляем обновление через WebSocket всем подключенным
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'topic_{topic_id}',
        {
            'type': 'update_likes',
            'post_id': post_id,
            'likes_count': likes_count,
        }
    )
    
    return JsonResponse({
        'liked': liked,
        'likes_count': likes_count,
    })

@login_required
def create_post(request, cat_slug, topic_id):
    """
    Создание нового поста (будет работать с WebSocket)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    category = get_object_or_404(ForumCategory, slug=cat_slug)
    topic = get_object_or_404(ForumTopic, id=topic_id)
    
    # Проверяем права
    user_ctx = {
        'user_id': request.user.id,
        'perms': request.user.get_all_permissions()
    }
    flags = get_posts_page_flags(user_ctx=user_ctx, topic=topic)
    
    if not flags['can_post']:
        return JsonResponse({'error': 'No permission'}, status=403)
    
    if topic.closed and not flags['can_post_closed']:
        return JsonResponse({'error': 'Topic closed'}, status=403)
    
    # Создаем пост
    content = request.POST.get('content')
    parent_id = request.POST.get('parent_id')
    
    if not content:
        return JsonResponse({'error': 'Content required'}, status=400)
    
    post = ForumPost.objects.create(
        topic=topic,
        author=request.user,
        content=content,
        parent_id=parent_id if parent_id else None
    )
    
    # Отправляем уведомление через WebSocket
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'topic_{topic.id}',
        {
            'type': 'new_post',
            'post_id': post.id,
            'author': post.author.profile.displayname,
            'content_preview': post.content[:100],
        }
    )
    
    # Возвращаем HTML фрагмент для HTMX
    post.flag = get_post_flags(user_ctx=user_ctx, post=post, is_owner=True)
    post.is_liked_by_user = False
    
    context = {
        'post': post,
        'category': category,
        'topic': topic,
        'flags': flags,
    }
    
    return render(request, 'forum_app/forum_post.html', context)

@login_required
def posts_edit(request, cat_slug, topic_id, flag):
    if not request.method == "POST":
        return HttpResponseNotAllowed(['POST'])
    if not request.user.is_authenticated:
        return HttpResponseForbidden()
    if not request.user.has_perm('forum_app.change_forumtopic'):
        return HttpResponseForbidden()
    topic = ForumTopic.objects.get(id=topic_id)
    if flag == 'close':
        topic.closed = True
        notify(
            user=topic.author,
            type=Notification.Type.TOPIC_CLOSED,
            actor=request.user,
            obj=topic
        )
    if flag == 'unclose':
        topic.closed = False
        notify(
            user=topic.author,
            type=Notification.Type.TOPIC_UNCLOSED,
            actor=request.user,
            obj=topic
        )
    if flag == 'hide':
        topic.visible = False
        notify(
            user=topic.author,
            type=Notification.Type.TOPIC_HIDDEN,
            actor=request.user,
            obj=topic
        )
    if flag == 'show':
        topic.visible = True
        notify(
            user=topic.author,
            type=Notification.Type.TOPIC_SHOWN,
            actor=request.user,
            obj=topic
        )
    if flag == "pin":   
        topic.pinned = True
        notify(
        user=topic.author,
        type=Notification.Type.TOPIC_PINNED,
        actor=request.user,
        obj=topic
    )
    if flag == 'unpin':
        topic.pinned = False
        notify(
            user=topic.author,
            type=Notification.Type.TOPIC_UNPINNED,
            actor=request.user,
            obj=topic
        )
    if flag == 'delete':
        notify(
            user=topic.author,
            type=Notification.Type.TOPIC_DELETED,
            actor=request.user,
            data={
                "title": topic.title
            }
        )
        topic.delete()
        return redirect('category', cat_slug=cat_slug)
    topic.save()
    return redirect('topic', cat_slug=cat_slug, topic_id=topic_id)


@login_required
def post(request, cat_slug, topic_id, post_id, flag):
    print(flag, request.user.get_all_permissions())
    post = ForumPost.objects.get(id=post_id)
    if request.method != "POST":
        return HttpResponseNotAllowed(['POST'])

    if not request.user.is_authenticated:
        return HttpResponseForbidden()

    if not (
        request.user.has_perm('forum_app.change_forumpost')
        or request.user == post.author
    ):
        return HttpResponseForbidden()
    if flag == 'hide' and request.user.has_perm('forum_app.can_hide_post'):
        post.visible = False
    if flag == 'show' and request.user.has_perm('forum_app.can_hide_post'):
        post.visible = True
    if flag == "pin" and request.user.has_perm('forum_app.can_pin_post'):
        post.pinned = True
        notify(
            user=post.author,
            type=Notification.Type.POST_PINNED,
            actor=request.user,
            obj=post
        )
    if flag == 'unpin' and request.user.has_perm('forum_app.can_pin_post'):
        post.pinned = False
        notify(
            user=post.author,
            type=Notification.Type.POST_UNPINNED,
            actor=request.user,
            obj=post
        )
    if flag == 'edit' and request.user.has_perm('forum_app.can_edit_post'):
        return render(request, 'forum_app/posts.html', {'post':post, 'form': PostCreationForm(initial={'content':post.content})})
    if flag == 'save_edit' and request.user.has_perm('forum_app.can_edit_post'):
        form = PostCreationForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            post.edited = True
            post.save()
            notify(
                user=post.author,
                type=Notification.Type.POST_EDITED,
                actor=request.user,
                obj=post
            )
        return redirect('topic', cat_slug=cat_slug, topic_id=topic_id)
    if flag == 'delete' and request.user.has_perm('forum_app.can_delete_post'):
        post.visible = False
        post.deleted = True
        notify(
            user=post.author,
            type=Notification.Type.POST_DELETED,
            actor=request.user,
            obj=post,
            data={
                "content": post.content,
                "topic": post.topic.title
            }
        )
    if flag == 'true_delete' and request.user.has_perm('forum_app.can_really_delete_post'):
        if not post.deleted:
            notify(
            user=post.author,
            type=Notification.Type.POST_DELETED,
            actor=request.user,
            obj=post,
            data={
                "content": post.content,
                "topic" : post.topic.title
            }
        )
        post.delete()
        return redirect('topic', cat_slug=cat_slug, topic_id=topic_id)
    # if flag == 'like':

    #     like, created = ForumPostLike.objects.get_or_create(
    #         user=request.user,
    #         post=post
    #     )

    #     if created:
    #         liked = True
    #     else:
    #         like.delete()
    #         liked = False

        
    #     return JsonResponse({
    #         'status': 'ok',
    #         'liked': liked,
    #         'likes_count': post.likes.count()
    #     })
    post.save()
    return redirect('topic', cat_slug=cat_slug, topic_id=topic_id)