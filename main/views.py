from django.shortcuts import render, redirect
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import VoteBox, VoteBoxItem, VoteBoxVote, MainBanner, HelpAccardion, MainRules
from .forms import VoteForm
from django.http import HttpResponseBadRequest
from django.db.models import Count
from core.models import FooterInfo

# Create your views here.

def index(request):
    banner = MainBanner.objects.all().first()
    polls = VoteBox.objects.filter(closed=False)

    # --- POST: обработка голосования ---
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return HttpResponseBadRequest('Требуется авторизация')

        poll_id = request.POST.get('poll_id')
        if not poll_id:
            return HttpResponseBadRequest('Нет poll_id')

        poll = get_object_or_404(VoteBox, id=poll_id, closed=False)

        # защита
        if not poll.active:
            return HttpResponseBadRequest('Голосование закрыто')

        if VoteBoxVote.objects.filter(box=poll, user=request.user).exists():
            return HttpResponseBadRequest('Вы уже голосовали')

        form = VoteForm(request.POST, poll=poll)
        if form.is_valid():
            selected = form.cleaned_data['options']
            if not isinstance(selected, list):
                selected = [selected]

            for option_id in selected:
                VoteBoxVote.objects.create(
                    box=poll,
                    user=request.user,
                    item_id=option_id
                )

        # 🔥 ВАЖНО
        return redirect('main')  # обновление страницы

    # --- GET: отображение ---
    
    poll_forms = []
    rules = MainRules.objects.all()
    for poll in polls:
        total_votes = VoteBoxVote.objects.filter(box=poll).count()
        items = (
        VoteBoxItem.objects
        .filter(box=poll)
        .annotate(votes=Count('vote_item_vote'))
            )
        items_with_stats = []

        for item in items:
            percent = round(item.votes * 100 / total_votes, 1) if total_votes > 0 else 0

            items_with_stats.append({
                'id': item.id,
                'is_winner': item.is_winner,
                'text': item.text,
                'votes': item.votes,
                'percent': int(percent),
            })
        selected_ids = VoteBoxVote.objects.filter(
            box=poll,
            user=request.user
        ).values_list('item_id', flat=True) if request.user.is_authenticated else []

        user_voted = bool(selected_ids)

        form = VoteForm(
            poll=poll,
            initial={'options': list(selected_ids)}
        )

        if not poll.active or user_voted:
            form.fields['options'].disabled = True

        poll_forms.append({
            'poll': poll,
            'form': form,
            'items': items_with_stats,
            'total_votes' : total_votes,
            'can_vote': (
                request.user.is_authenticated
                and request.user.has_perm('main.can_vote')
                and poll.active
                and not user_voted
            ),
            'voted': user_voted,
        })

    return render(request, 'main/index.html', {
        'polls': poll_forms,
        'user': request.user,
        'banner': banner,
        'rules': rules
    })

def help_page(request):
    points = HelpAccardion.objects.all()
    data = {
        'points': points
    }
    return render(request, 'main/help.html', data)