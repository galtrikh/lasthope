from django import forms
from django.utils import timezone
from decimal import Decimal

from .models import Donation, Privilegion, Donator, DiscountTier


class DonationForm(forms.ModelForm):
    """
    Форма создания доната.
    - status не включён — новые донаты всегда создаются со статусом WAITING
    - end_date не включён — вычисляется при активации
    - amount заполняется пользователем (или автоматически через JS)
    """

    class Meta:
        model  = Donation
        fields = ['nickname', 'privilegion', 'amount', 'comment']
        widgets = {
            'nickname': forms.TextInput(attrs={
                'class':        'input input-bordered w-full',
                'placeholder':  'Никнейм игрока',
                'autocomplete': 'off',
                'id':           'id_nickname',
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'min':   '0.01',
                'step':  '0.01',
                'id':    'id_amount',
            }),
            'privilegion': forms.CheckboxSelectMultiple(),
            'comment': forms.Textarea(attrs={
                'class':       'textarea textarea-bordered w-full',
                'rows':        2,
                'placeholder': 'Необязательный комментарий',
            }),
        }

    # ── Валидация ─────────────────────────────────────────────────────

    def clean_nickname(self):
        return self.cleaned_data['nickname'].strip()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= Decimal('0'):
            raise forms.ValidationError('Сумма должна быть больше нуля.')
        return amount

    # ── Сохранение ────────────────────────────────────────────────────

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Статус всегда WAITING при создании
        instance.status = Donation.Status.WAITING
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    # ── AJAX-хелпер ───────────────────────────────────────────────────

    @staticmethod
    def get_discount_for_nickname(nickname: str) -> dict:
        try:
            donator = Donator.objects.get(nickname__iexact=nickname.strip())
            tier    = donator.discount_tier
            return {
                'found':   True,
                'total':   float(donator.total_amount),
                'percent': donator.discount_percent,
                'tier':    tier.label if tier else '',
            }
        except Donator.DoesNotExist:
            return {'found': False, 'percent': 0, 'total': 0, 'tier': ''}


class DonationFilterForm(forms.Form):
    """Форма фильтрации списка донатов."""

    SORT_CHOICES = [
        ('-date',         'Сначала новые'),
        ('date',          'Сначала старые'),
        ('-final_amount', 'По сумме ↓'),
        ('final_amount',  'По сумме ↑'),
        ('nickname',      'По никнейму'),
    ]

    STATUS_CHOICES = [
        ('',          'Все статусы'),
        ('waiting',   'Ожидает активации'),
        ('active',    'Активен'),
        ('expired',   'Просрочен'),
        ('completed', 'Завершён'),
    ]

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class':       'input input-bordered input-sm w-full',
            'placeholder': 'Никнейм…',
        }),
        label='Поиск',
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'select select-bordered select-sm'}),
        label='Статус',
    )
    privilegion = forms.ModelChoiceField(
        queryset=Privilegion.objects.all(),
        required=False,
        empty_label='Все привилегии',
        widget=forms.Select(attrs={'class': 'select select-bordered select-sm'}),
        label='Привилегия',
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'input input-bordered input-sm'}),
        label='С даты',
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'input input-bordered input-sm'}),
        label='По дату',
    )
    sort = forms.ChoiceField(
        choices=SORT_CHOICES,
        required=False,
        initial='-date',
        widget=forms.Select(attrs={'class': 'select select-bordered select-sm'}),
        label='Сортировка',
    )
