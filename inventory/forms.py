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


