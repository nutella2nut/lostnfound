from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory, DateInput

from .models import Item, ItemImage

User = get_user_model()


class ItemForm(forms.ModelForm):
    date_found = forms.DateField(
        widget=DateInput(
            attrs={
                "type": "date",
                "class": "form-control",
            }
        ),
        help_text="Format: DD/MM/YYYY",
    )

    class Meta:
        model = Item
        fields = [
            "title",
            "description",
            "location_found",
            "date_found",
            "status",
            "category",
            "item_type",
        ]


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
    """Form for claiming an item — with attestation checkbox per §3.1."""

    name = forms.CharField(
        max_length=100,
        min_length=2,
        required=True,
        label="Full name (as it appears on your TISB record)",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your full name",
                "id": "claim-name-input",
            }
        ),
    )

    email = forms.EmailField(
        required=True,
        label="TISB email address",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your @tisb.ac.in email",
            }
        ),
    )

    attestation = forms.BooleanField(
        required=True,
        error_messages={
            "required": "You must check the attestation checkbox to submit a claim.",
        },
    )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email.endswith("@tisb.ac.in"):
            raise forms.ValidationError("Only @tisb.ac.in email addresses are accepted.")
        return email


class UserCreateForm(forms.Form):
    """Form for creating a new staff user (§6.8)."""

    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "user@tisb.ac.in"}),
    )
    role = forms.ChoiceField(
        choices=[("admin", "Admin"), ("superuser", "Super User")],
        widget=forms.RadioSelect,
    )
    is_active = forms.BooleanField(required=False, initial=True)
    password = forms.CharField(
        max_length=128,
        required=True,
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "id_password"}),
    )
    send_welcome_email = forms.BooleanField(required=False, initial=True)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with this username already exists (case-insensitive).")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email.endswith("@tisb.ac.in"):
            raise forms.ValidationError("Only @tisb.ac.in email addresses are accepted.")
        return email


class UserEditForm(forms.Form):
    """Form for editing an existing staff user (§6.9.1)."""

    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    role = forms.ChoiceField(
        choices=[
            ("admin", "Admin"),
            ("superuser", "Super User"),
            ("no_staff", "No staff access"),
        ],
        widget=forms.RadioSelect,
    )
    is_active = forms.BooleanField(required=False)

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance:
            self.fields["first_name"].initial = instance.first_name
            self.fields["last_name"].initial = instance.last_name
            self.fields["email"].initial = instance.email
            self.fields["is_active"].initial = instance.is_active
            if instance.is_superuser:
                self.fields["role"].initial = "superuser"
            elif instance.is_staff:
                self.fields["role"].initial = "admin"
            else:
                self.fields["role"].initial = "no_staff"

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email.endswith("@tisb.ac.in"):
            raise forms.ValidationError("Only @tisb.ac.in email addresses are accepted.")
        return email


class UserSetPasswordForm(forms.Form):
    """Form for setting a user's password (§6.9.2)."""

    password = forms.CharField(
        max_length=128,
        required=True,
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "id_password"}),
    )
    send_email = forms.BooleanField(required=False, initial=True)


