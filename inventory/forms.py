from django import forms
from django.forms import inlineformset_factory, DateInput

from .models import Item, ItemImage


class ItemForm(forms.ModelForm):
    date_found = forms.DateField(
        widget=DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
        }),
        help_text="Format: DD/MM/YYYY",
    )

    class Meta:
        model = Item
        fields = ["title", "description", "location_found", "date_found", "status", "category"]


ItemImageFormSet = inlineformset_factory(
    parent_model=Item,
    model=ItemImage,
    fields=["image"],
    extra=1,
    can_delete=False,
    min_num=0,  # Allow zero images
    validate_min=False,  # Don't validate minimum on formset level
)


class ClaimItemForm(forms.Form):
    """Form for claiming an item - captures claimant's name."""
    name = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your full name',
            'required': True,
        }),
        help_text="Please enter your name so we can contact you when you arrive."
    )


