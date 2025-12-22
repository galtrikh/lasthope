from django import forms
from .models import VoteBox, VoteBoxItem

class VoteForm(forms.Form):
      def __init__(self, *args, poll=None, **kwargs):
        super().__init__(*args, **kwargs)

        if poll is None:
            raise ValueError('poll is required')

        self.poll = poll

        options = VoteBoxItem.objects.filter(box=poll)

        choices = [(opt.id, opt.text) for opt in options]

        if poll.multiple:
            self.fields['options'] = forms.MultipleChoiceField(
                choices=choices,
                widget=forms.CheckboxSelectMultiple,
                required=True,
            )
        else:
            self.fields['options'] = forms.ChoiceField(
                choices=choices,
                widget=forms.RadioSelect,
                required=True,
            )