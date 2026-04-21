from dataclasses import dataclass, fields as dc_fields
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseNotAllowed
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Value, BooleanField
from django.utils.text import slugify, Truncator
from django.utils.html import strip_tags
from bs4 import BeautifulSoup

from .models import (
    ForumCategory, ForumTopic, ForumPost,
    ForumCategoryLike, ForumTopicLike, ForumPostLike,
)
from .templatetags import forum_filters
from .froms import PostCreationForm, TopicCreationForm, CategoryCreationForm
from forum_filter.services import moderate_post
from notification.services import notify
from notification.models import Notification


POSTS_PER_PAGE = 20


# ─────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────

@dataclass
class PostFlags:
    is_owner: bool
    can_dropdown: bool
    can_edit: bool
    can_delete: bool
    can_really_delete: bool
    can_hide: bool
    can_pin: bool
    is_guarded: bool


@dataclass
class PostsPageFlags:
    can_post: bool
    can_post_closed: bool
    can_dropdown: bool
    can_close_topic: bool
    can_pin_topic: bool
    can_delete_topic: bool
    can_hide_topic: bool


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _user_ctx(user):
    """Lightweight permission context dict."""
    return {
        'user_id':  user.id if user.is_authenticated else None,
        'perms':    user.get_all_permissions() if user.is_authenticated else set(),
        'is_super': getattr(user, 'is_superuser', False),
    }


def get_topic_flags(user, topic):
    """Used in the topics-list view (returns plain dict)."""
    is_auth  = user.is_authenticated
    is_owner = is_auth and user == topic.author
    is_super = is_auth and user.is_superuser
    author_protected = (
        topic.author.has_perm('user.safety') if topic.author.is_authenticated else False
    )

    def allowed(perm):
        return user.has_perm(perm) and (is_super or is_owner or not author_protected)

    return {
        'is_auth':          is_auth,
        'is_owner':         is_owner,
        'can_post':         user.has_perm('forum_app.can_post'),
        'can_post_closed':  user.has_perm('forum_app.can_post_closed'),
        'can_create_topic': user.has_perm('forum_app.can_create_topic'),
        'can_close_topic':  allowed('forum_app.can_close_topic'),
        'can_pin_topic':    allowed('forum_app.can_pin_topic'),
        'can_delete_topic': allowed('forum_app.can_delete_topic'),
        'can_hide_topic':   allowed('forum_app.can_hide_topic'),
    }


def get_post_flags(user_ctx, post, is_owner=None) -> PostFlags:
    if is_owner is None:
        is_owner = user_ctx['user_id'] == post.author_id

    is_super   = user_ctx.get('is_super', False)
    perms      = user_ctx['perms']
    is_guarded = 'user.safety' in post.author.get_all_permissions()

    if is_super:
        return PostFlags(
            is_owner=is_owner, is_guarded=False,
            can_edit=True, can_delete=True, can_really_delete=True,
            can_hide=True, can_pin=True, can_dropdown=True,
        )

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
        'forum_app.can_true_delete_post' in perms and not is_guarded
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

    return PostFlags(
        is_owner=is_owner, is_guarded=is_guarded,
        can_edit=can_edit, can_delete=can_delete,
        can_really_delete=can_really_delete,
        can_hide=can_hide, can_pin=can_pin,
        can_dropdown=any([can_edit, can_delete, can_really_delete, can_hide, can_pin]),
    )


def get_posts_page_flags(user_ctx, topic) -> PostsPageFlags:
    perms       = user_ctx['perms']
    is_t_author = user_ctx['user_id'] == topic.author_id
    t_guarded   = 'user.safety' in topic.author.get_all_permissions()

    can_post_closed = 'forum_app.can_post_closed' in perms
    can_post = (
        'forum_app.can_post' in perms
        and (not topic.closed or can_post_closed)
    )

    def topic_allowed(perm):
        return perm in perms and (is_t_author or not t_guarded)

    can_close  = topic_allowed('forum_app.can_close_topic')
    can_pin    = topic_allowed('forum_app.can_pin_topic')
    can_delete = topic_allowed('forum_app.can_delete_topic')
    can_hide   = topic_allowed('forum_app.can_hide_topic')

    return PostsPageFlags(
        can_post=can_post,
        can_post_closed=can_post_closed,
        can_dropdown=any([can_close, can_pin, can_delete, can_hide]),
        can_close_topic=can_close,
        can_pin_topic=can_pin,
        can_delete_topic=can_delete,
        can_hide_topic=can_hide,
    )


def get_page_range(page_obj, paginator, delta=2):
    """
    Returns a list of page numbers (int) with None where ellipsis should appear.
    Example for page 6 of 15:  [1, None, 4, 5, 6, 7, 8, None, 15]
    """
    current = page_obj.number
    total   = paginator.num_pages

    if total <= 7:
        return list(range(1, total + 1))

    pages = {1, total}
    pages.update(range(max(2, current - delta), min(total, current + delta + 1)))

    result, prev = [], 0
    for p in sorted(pages):
        if p - prev > 1:
            result.append(None)
        result.append(p)
        prev = p
    return result


def _get_page_for_post(post, topic):
    """Return the paginator page number where a given post appears."""
    ids = list(
        ForumPost.objects
        .filter(topic=topic, visible=True)
        .order_by('-pinned', 'id')
        .values_list('id', flat=True)
    )
    try:
        return ids.index(post.pk) // POSTS_PER_PAGE + 1
    except ValueError:
        return 1


def _topic_url(cat_slug, topic_id, page=1, anchor=''):
    url = reverse('topic', kwargs={'cat_slug': cat_slug, 'topic_id': topic_id})
    url += f'?page={page}'
    if anchor:
        url += f'#{anchor}'
    return url


# ─────────────────────────────────────────────────────────────
# Views: forum index
# ─────────────────────────────────────────────────────────────

def index(request):
    if request.user.has_perm('forum_app.can_see_hidden_cats'):
        categories = ForumCategory.objects.all()
    else:
        categories = ForumCategory.objects.filter(visible=True)

    if request.method == 'POST':
        if request.GET.get('hide') and request.user.has_perm('forum_app.can_hide_cats'):
            cat = get_object_or_404(ForumCategory, id=request.GET['hide'])
            cat.visible = False; cat.save()
            return redirect('forum')

        if request.GET.get('show') and request.user.has_perm('forum_app.can_hide_cats'):
            cat = get_object_or_404(ForumCategory, id=request.GET['show'])
            cat.visible = True; cat.save()
            return redirect('forum')

        if request.GET.get('delete') and request.user.has_perm('forum_app.can_delete_cats'):
            cat = get_object_or_404(ForumCategory, id=request.GET['delete'])
            cat.delete()
            return redirect('forum')

        if not request.user.has_perm('forum_app.can_create_cats'):
            return HttpResponseForbidden()

        form = CategoryCreationForm(request.POST)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.author = request.user
            cat.slug   = slugify(cat.name)
            cat.save()
            return redirect(cat.get_absolute_url())
    else:
        form = CategoryCreationForm()

    if request.user.is_authenticated:
        categories = categories.annotate(
            is_liked=Exists(ForumCategoryLike.objects.filter(
                user=request.user, category=OuterRef('pk')
            ))
        )
    else:
        categories = categories.annotate(
            is_liked=Value(False, output_field=BooleanField())
        )

    return render(request, 'forum_app/index.html', {'categories': categories, 'form': form})


# ─────────────────────────────────────────────────────────────
# Views: topics list
# ─────────────────────────────────────────────────────────────

def topics(request, cat_slug):
    category = get_object_or_404(ForumCategory, slug=cat_slug)

    if request.method == 'POST':
        if not request.user.has_perm('forum_app.can_create_topic'):
            return HttpResponseForbidden()
        form = TopicCreationForm(request.POST)
        if form.is_valid():
            topic          = form.save(commit=False)
            topic.author   = request.user
            topic.category = category
            topic.save()
            return redirect(topic.get_absolute_url())
    else:
        form = TopicCreationForm()

    if request.user.has_perm('forum_app.can_see_hidden_topics'):
        topics_qs = ForumTopic.objects.filter(category=category).order_by('-pinned', 'id')
    else:
        topics_qs = ForumTopic.objects.filter(visible=True, category=category).order_by('-pinned', 'id')

    if request.user.is_authenticated:
        topics_qs = topics_qs.annotate(
            is_liked=Exists(ForumTopicLike.objects.filter(
                user=request.user, topic=OuterRef('pk')
            ))
        )
    else:
        topics_qs = topics_qs.annotate(
            is_liked=Value(False, output_field=BooleanField())
        )

    topics_list = list(topics_qs)
    for t in topics_list:
        t.flag = get_topic_flags(request.user, t)

    paginator = Paginator(topics_list, 1)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'forum_app/topics.html', {
        'category':     category,
        'topics':       page_obj,
        'paginator':    paginator,
        'topics_count': len(topics_list),
        'form':         form,
    })


# ─────────────────────────────────────────────────────────────
# Views: likes
# ─────────────────────────────────────────────────────────────

@login_required
def category_like(request, cat_slug):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    category = get_object_or_404(ForumCategory, slug=cat_slug)
    like, created = ForumCategoryLike.objects.get_or_create(
        user=request.user, category=category
    )
    if not created:
        like.delete()
    return JsonResponse({'liked': created, 'likes_count': category.likes.count()})


@login_required
def topic_like(request, cat_slug, topic_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    topic = get_object_or_404(ForumTopic, id=topic_id)
    like, created = ForumTopicLike.objects.get_or_create(
        user=request.user, topic=topic
    )
    if not created:
        like.delete()
    return JsonResponse({'liked': created, 'likes_count': topic.likes.count()})


# ─────────────────────────────────────────────────────────────
# Views: posts (main view)
# ─────────────────────────────────────────────────────────────

def _build_posts_qs(topic, user):
    qs = (
        ForumPost.objects
        .filter(topic=topic)
        .select_related('author', 'author__profile', 'parent', 'parent__author')
        .prefetch_related('author__groups')
    )
    if not user.has_perm('forum_app.can_see_hidden_post'):
        qs = qs.filter(visible=True)

    if user.is_authenticated:
        qs = qs.annotate(is_liked_by_user=Exists(
            ForumPostLike.objects.filter(user=user, post=OuterRef('pk'))
        ))
    else:
        qs = qs.annotate(is_liked_by_user=Value(False, output_field=BooleanField()))

    return qs.order_by('-pinned', 'id')


def _enrich_posts(posts_list):
    """Attach parent_preview and media indicators to posts that have a parent."""
    for post in posts_list:
        if not post.parent:
            continue
        clean = forum_filters.safe_html(post.parent.content)
        text  = strip_tags(clean)
        post.parent_preview = Truncator(text).chars(160, truncate='…')

        soup       = BeautifulSoup(clean, 'html.parser')
        indicators = []
        if soup.find('img'):
            indicators.append('<span><i class="fa-solid fa-image"></i> изображение</span>')
        if soup.find('table'):
            indicators.append('<span><i class="fa-solid fa-table"></i> таблица</span>')
        if soup.find('iframe'):
            indicators.append('<span><i class="fa-solid fa-film"></i> медиа</span>')
        post.indicators = indicators


def _apply_post_flags(posts_list, user_ctx, user):
    empty = PostFlags(**{f.name: False for f in dc_fields(PostFlags)})
    for post in posts_list:
        if user.is_authenticated:
            post.flag = get_post_flags(
                user_ctx=user_ctx,
                post=post,
                is_owner=(user_ctx['user_id'] == post.author_id),
            )
        else:
            post.flag             = empty
            post.is_liked_by_user = False


def posts(request, cat_slug, topic_id):
    """
    Display topic posts with standard paginator.

    GET  ?page=N  — show page N (default 1; 'last' resolves to last page)
    POST          — create a new post, then redirect to the last page
    """
    category = get_object_or_404(ForumCategory, slug=cat_slug)
    topic    = get_object_or_404(ForumTopic, id=topic_id)
    ctx      = _user_ctx(request.user)
    flags    = get_posts_page_flags(user_ctx=ctx, topic=topic)

    # ── Create new post ──────────────────────────────────────
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        if not flags.can_post:
            return HttpResponseForbidden()

        form = PostCreationForm(request.POST)
        if form.is_valid():
            new_post = ForumPost.objects.create(
                topic=topic,
                author=request.user,
                content=form.cleaned_data['content'],
                parent_id=request.POST.get('parent_id') or None,
            )
            moderate_post(new_post)

            # Go to the last page so the new post is immediately visible
            total_visible = _build_posts_qs(topic, request.user).count()
            last_page     = max(1, (total_visible + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE)
            return redirect(_topic_url(cat_slug, topic_id, page=last_page, anchor=f'post-{new_post.pk}'))

        # Form invalid — fall through and re-render with errors
    else:
        form = PostCreationForm()

    # ── Display ──────────────────────────────────────────────
    qs        = _build_posts_qs(topic, request.user)
    paginator = Paginator(qs, POSTS_PER_PAGE)

    page_num = request.GET.get('page', 1)
    if page_num == 'last':
        page_num = paginator.num_pages
    page_obj = paginator.get_page(page_num)

    posts_list = list(page_obj.object_list)
    _enrich_posts(posts_list)
    _apply_post_flags(posts_list, ctx, request.user)

    return render(request, 'forum_app/posts.html', {
        'posts':        posts_list,
        'page_obj':     page_obj,
        'paginator':    paginator,
        'page_range':   get_page_range(page_obj, paginator),
        'current_page': page_obj.number,
        'category':     category,
        'topic':        topic,
        'flags':        flags,
        'form':         form,
    })


# ─────────────────────────────────────────────────────────────
# Views: toggle post like
# ─────────────────────────────────────────────────────────────

@login_required
def toggle_like(request, cat_slug, topic_id, post_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    post = get_object_or_404(ForumPost, id=post_id, topic_id=topic_id)
    like, created = ForumPostLike.objects.get_or_create(user=request.user, post=post)
    if not created:
        like.delete()
    return JsonResponse({'liked': created, 'likes_count': post.likes.count()})


# ─────────────────────────────────────────────────────────────
# Views: topic-level moderation
# ─────────────────────────────────────────────────────────────

_TOPIC_PERM = {
    'close':   'forum_app.can_close_topic',
    'unclose': 'forum_app.can_close_topic',
    'hide':    'forum_app.can_hide_topic',
    'show':    'forum_app.can_hide_topic',
    'pin':     'forum_app.can_pin_topic',
    'unpin':   'forum_app.can_pin_topic',
    'delete':  'forum_app.can_delete_topic',
}

_TOPIC_FLAG_CHECK = {
    'close':   lambda f: f.can_close_topic,
    'unclose': lambda f: f.can_close_topic,
    'hide':    lambda f: f.can_hide_topic,
    'show':    lambda f: f.can_hide_topic,
    'pin':     lambda f: f.can_pin_topic,
    'unpin':   lambda f: f.can_pin_topic,
    'delete':  lambda f: f.can_delete_topic,
}


@login_required
def posts_edit(request, cat_slug, topic_id, flag):
    """Topic-level moderation: close, pin, hide, delete."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    if flag not in _TOPIC_PERM:
        return HttpResponseNotAllowed(['POST'])

    # Fast pre-check before hitting the DB
    if not request.user.has_perm(_TOPIC_PERM[flag]):
        return HttpResponseForbidden()

    topic = get_object_or_404(ForumTopic, id=topic_id)
    ctx   = _user_ctx(request.user)
    flags = get_posts_page_flags(user_ctx=ctx, topic=topic)

    # Detailed check (respects author protection etc.)
    if not _TOPIC_FLAG_CHECK[flag](flags):
        return HttpResponseForbidden()

    current_page = request.POST.get('current_page', 1)
    redirect_url = _topic_url(cat_slug, topic_id, page=current_page)

    if flag == 'close':
        topic.closed = True
        notify(user=topic.author, type=Notification.Type.TOPIC_CLOSED,
               actor=request.user, obj=topic)

    elif flag == 'unclose':
        topic.closed = False
        notify(user=topic.author, type=Notification.Type.TOPIC_UNCLOSED,
               actor=request.user, obj=topic)

    elif flag == 'hide':
        topic.visible = False
        notify(user=topic.author, type=Notification.Type.TOPIC_HIDDEN,
               actor=request.user, obj=topic)

    elif flag == 'show':
        topic.visible = True
        notify(user=topic.author, type=Notification.Type.TOPIC_SHOWN,
               actor=request.user, obj=topic)

    elif flag == 'pin':
        topic.pinned = True
        notify(user=topic.author, type=Notification.Type.TOPIC_PINNED,
               actor=request.user, obj=topic)

    elif flag == 'unpin':
        topic.pinned = False
        notify(user=topic.author, type=Notification.Type.TOPIC_UNPINNED,
               actor=request.user, obj=topic)

    elif flag == 'delete':
        notify(user=topic.author, type=Notification.Type.TOPIC_DELETED,
               actor=request.user, data={'title': topic.title})
        topic.delete()
        return redirect('category', cat_slug=cat_slug)

    topic.save()
    return redirect(redirect_url)


# ─────────────────────────────────────────────────────────────
# Views: post-level moderation
# ─────────────────────────────────────────────────────────────

@login_required
def post(request, cat_slug, topic_id, post_id, flag):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    post_obj   = get_object_or_404(ForumPost, id=post_id, topic_id=topic_id)
    ctx        = _user_ctx(request.user)
    post_flags = get_post_flags(user_ctx=ctx, post=post_obj)

    # Always redirect back to the exact paginator page where this post lives
    page         = _get_page_for_post(post_obj, post_obj.topic)
    redirect_url = _topic_url(cat_slug, topic_id, page=page, anchor=f'post-{post_id}')

    if flag == 'hide':
        if not post_flags.can_hide:
            return HttpResponseForbidden()
        post_obj.visible = False

    elif flag == 'show':
        if not post_flags.can_hide:
            return HttpResponseForbidden()
        post_obj.visible = True

    elif flag == 'pin':
        if not post_flags.can_pin:
            return HttpResponseForbidden()
        post_obj.pinned = True
        notify(user=post_obj.author, type=Notification.Type.POST_PINNED,
               actor=request.user, obj=post_obj)

    elif flag == 'unpin':
        if not post_flags.can_pin:
            return HttpResponseForbidden()
        post_obj.pinned = False
        notify(user=post_obj.author, type=Notification.Type.POST_UNPINNED,
               actor=request.user, obj=post_obj)

    elif flag == 'delete':
        if not post_flags.can_delete:
            return HttpResponseForbidden()
        post_obj.visible = False
        post_obj.deleted = True
        notify(user=post_obj.author, type=Notification.Type.POST_DELETED,
               actor=request.user, obj=post_obj,
               data={'content': post_obj.content, 'topic': post_obj.topic.title})

    elif flag == 'true_delete':
        if not post_flags.can_really_delete:
            return HttpResponseForbidden()
        if not post_obj.deleted:
            notify(user=post_obj.author, type=Notification.Type.POST_DELETED,
                   actor=request.user, obj=post_obj,
                   data={'content': post_obj.content, 'topic': post_obj.topic.title})
        post_obj.delete()
        return redirect(_topic_url(cat_slug, topic_id, page=page))

    elif flag == 'save_edit':
        if not post_flags.can_edit:
            return HttpResponseForbidden()
        form = PostCreationForm(request.POST, request.FILES, instance=post_obj)
        if form.is_valid():
            saved        = form.save(commit=False)
            saved.edited = True
            saved.save()
            notify(user=post_obj.author, type=Notification.Type.POST_EDITED,
                   actor=request.user, obj=post_obj)
        return redirect(redirect_url)

    else:
        return HttpResponseNotAllowed(['POST'])

    post_obj.save()
    return redirect(redirect_url)
