from django.shortcuts import render, redirect
from .models import ForumCategory, ForumTopic, ForumPost, ForumCategoryLike, ForumTopicLike
import markdown
from .templatetags import forum_filters
from django.urls import reverse
from django.http import JsonResponse
from forum_app.models import ForumPost
from forum_app.froms import PostCreationForm, TopicCreationForm
from django.utils.dateparse import parse_datetime
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from notification.services import notify
from notification.models import Notification
from forum_filter.services import moderate_post
from django.views.decorators.http import require_POST
from django.db.models import Exists, OuterRef, Value, BooleanField


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
        'categories' : categories
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

def posts(request, cat_slug, topic_id):
    POSTS_PER_PAGE = 20
    category = ForumCategory.objects.get(slug=cat_slug)
    topic = ForumTopic.objects.get(id=topic_id)
    if request.user.has_perm('forum_app.can_see_hidden_post'):
        postslist = ForumPost.objects.filter(topic=topic).order_by('-pinned', 'id')
    else:
        postslist = ForumPost.objects.filter(visible=True, topic=topic).order_by('-pinned', 'id')
    posts = []
    for post in postslist:
        post.content = forum_filters.safe_html(post.content)

        is_owner = request.user == post.author

        can_edit = (
            is_owner
            or request.user.has_perm('forum_app.can_edit_another_post')
        ) and not post.author.has_perm('user.safety')

        can_delete = (
            request.user.has_perm('forum_app.can_delete_post')
            or (
                is_owner and request.user.has_perm('forum_app.can_delete_own_post')
            )
        ) and not post.author.has_perm('user.safety')

        can_pin = request.user.has_perm('forum_app.can_pin_post')

        is_safety = not request.user.is_superuser and post.author.has_perm('user.safety')

        posts.append({
            'obj': post,
            'is_owner': is_owner,
            'can_edit': can_edit,
            'can_delete': can_delete,
            'can_pin': can_pin,
            'is_safety': is_safety
        })

        
    if request.method == "POST":
        form = PostCreationForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.topic = topic
            post.author = request.user
            post.save()
            moderate_post(post)
            posts_qs = topic.posts.order_by('created_at')  # важно: тот же order_by
            paginator = Paginator(posts_qs, POSTS_PER_PAGE)

            last_page = paginator.num_pages
            return redirect(f"{reverse('topic', kwargs={'cat_slug': category.slug, 'topic_id': topic.id})}?page={last_page}#post-id-{post.id}")
    else:
        form = PostCreationForm
    flag = {
        'is_auth': request.user.is_authenticated,
        'can_post': request.user.has_perm('forum_app.can_post'),
        'can_post_closed': request.user.has_perm('forum_app.can_post_closed'),
        'is_owner': request.user == topic.author,
        'can_close_topic': request.user.has_perm('forum_app.can_close_topic') and (not topic.author.has_perm('user.safety') or request.user == topic.author) or request.user.is_superuser,
        'can_pin_topic': request.user.has_perm('forum_app.can_pin_topic') and (not topic.author.has_perm('user.safety') or request.user == topic.author ) or request.user.is_superuser,
        'can_delete_topic': request.user.has_perm('forum_app.can_delete_topic') and (not topic.author.has_perm('user.safety') or request.user == topic.author ) or request.user.is_superuser,
        'can_hide_topic': request.user.has_perm('forum_app.can_hide_topic') and (not topic.author.has_perm('user.safety') or request.user == topic.author ) or request.user.is_superuser,
        'can_hide_post': request.user.has_perm('forum_app.can_hide_post'),
        'can_pin_post': request.user.has_perm('forum_app.can_pin_post'),
        'can_edit_post': request.user.has_perm('forum_app.can_edit_post'),
        'can_edit_another_post': request.user.has_perm('forum_app.can_edit_another_post'),
        'can_delete_post': request.user.has_perm('forum_app.can_delete_post'),
        'can_really_delete_post': request.user.has_perm('forum_app.can_really_delete_post'),
    }

    paginator = Paginator(posts, POSTS_PER_PAGE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    data = {
        'category' : category,
        'topic' : topic,
        'posts' : page_obj,
        'posts_count': len(posts),
        'form' : form,
        'flag': flag,
    }
    return render(request, 'forum_app/posts.html', data)

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

def posts_poll(request, topic_id):
    """
    ?after=2025-12-13T18:00:00
    """
    after = request.GET.get('after')
    topic = ForumTopic.objects.get(id=topic_id)
    if request.user.has_perm('forum_app.can_see_hidden_posts'):
        qs = ForumPost.objects.filter(topic=topic).order_by('created_at')
    else:
        qs = ForumPost.objects.filter(visible=True, topic=topic).order_by('created_at')


    if after:
        dt = parse_datetime(after)
        if dt:
            qs = qs.filter(created_at__gt=dt)

    paginator = Paginator(qs, 1)
   
    data = []
    for post in qs:
        group = post.author.groups.first()
        if group:
            group_name = group.name
            group_style = group.profile.style
        else:
            group_name = ''
            group_style = ''
        html = markdown.markdown(post.content)
        safe_html = forum_filters.safe_html(post.content)
        data.append({
            'id': post.id,
            'author_userurl': reverse('user', args=[post.author.username]),
            'author_displayname': post.author.profile.displayname,
            'author_avatar': post.author.profile.avatar.url,
            'author_group': group_name,
            'author_group_style': group_style,
            'content': safe_html, #MUST SAFE
            'created_at': post.created_at.strftime('%d.%m.%Y %H:%M'),
            'created_at_iso': post.created_at.isoformat(),
        })

    return JsonResponse({'topic_id': topic_id, 'posts': data})

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
        return render(request, 'forum_app/post.html', {'post':post, 'form': PostCreationForm(initial={'content':post.content})})
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
    post.save()
    return redirect('topic', cat_slug=cat_slug, topic_id=topic_id)