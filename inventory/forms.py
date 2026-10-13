import re

from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, validate_email
from django.forms import inlineformset_factory, DateInput

from .models import Item, ItemImage, SiteSettings
from .site_settings import (
    EMAIL_TEMPLATES, allowed_placeholders, email_matches_domain, get_site_settings,
    validate_template_text,
)

User = get_user_model()


def clean_school_email(email):
    """Normalise an email and require the allowed domain from Settings → Claims."""
    email = (email or "").strip().lower()
    site = get_site_settings()
    if not email_matches_domain(email, site):
        raise forms.ValidationError(f"Only {site.allowed_email_domain} email addresses are accepted.")
    return email


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
                "placeholder": "Enter your school email",
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
        return clean_school_email(self.cleaned_data.get("email"))


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
        widget=forms.EmailInput(attrs={"class": "form-control"}),
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
        return clean_school_email(self.cleaned_data.get("email"))


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
        return clean_school_email(self.cleaned_data.get("email"))


class UserSetPasswordForm(forms.Form):
    """Form for setting a user's password (§6.9.2)."""

    password = forms.CharField(
        max_length=128,
        required=True,
        widget=forms.PasswordInput(attrs={"class": "form-control", "id": "id_password"}),
    )
    send_email = forms.BooleanField(required=False, initial=True)




# ---------------------------------------------------------------------------
# Settings page (Super Users) — one form per section of SiteSettings
# ---------------------------------------------------------------------------

_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm shadow-sm "
    "focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
)


class _SettingsForm(forms.ModelForm):
    """Applies page styling, and requires integers to be at least 1 (except ZERO_OK)."""
    ZERO_OK = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "h-5 w-5 rounded border-slate-300 text-cyan-600 focus:ring-cyan-500"
                continue
            field.widget.attrs["class"] = _INPUT_CLASS
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 4
            if isinstance(field, forms.IntegerField) and name not in self.ZERO_OK:
                field.min_value = 1
                field.validators.append(MinValueValidator(1))
                field.widget.attrs["min"] = 1


class GeneralSettingsForm(_SettingsForm):
    class Meta:
        model = SiteSettings
        fields = [
            "site_name", "school_name", "email_signoff", "sender_display_name",
            "contact_email", "announcement_enabled", "announcement_text",
        ]
        labels = {
            "email_signoff": "Email sign-off",
            "sender_display_name": "Sender name on broadcasts",
            "contact_email": "Public contact address",
            "announcement_enabled": "Show announcement banner on every page",
        }

    def clean(self):
        data = super().clean()
        if data.get("announcement_enabled") and not (data.get("announcement_text") or "").strip():
            self.add_error("announcement_text", "Enter the announcement text, or turn the banner off.")
        return data


class ClaimSettingsForm(_SettingsForm):
    """Also renders one 'days visible' field per item category (stored as JSON)."""
    ZERO_OK = ("claimed_visibility_default_days",)

    class Meta:
        model = SiteSettings
        fields = [
            "allowed_email_domain", "claims_enabled", "allow_multiple_claims",
            "claimed_visibility_default_days",
        ]
        labels = {
            "allowed_email_domain": "Allowed email domain",
            "claims_enabled": "Accept claims",
            "allow_multiple_claims": "Accept further claims after an item's first claim",
            "claimed_visibility_default_days": "Days a claimed item stays listed (default)",
        }
        help_texts = {
            "allowed_email_domain": "Used for claims, staff accounts and emailed reports, e.g. @tisb.ac.in",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.claimed_visibility_days or {}
        for code, label in Item.Category.choices:
            self.fields[f"days_{code}"] = forms.IntegerField(
                label=f"Days listed after claim: {label}",
                min_value=0,
                required=False,
                initial=current.get(code),
                help_text="Blank = use the default above. 0 = hide as soon as claimed.",
                widget=forms.NumberInput(attrs={"class": _INPUT_CLASS, "min": 0}),
            )

    def clean_allowed_email_domain(self):
        domain = self.cleaned_data["allowed_email_domain"].strip().lower()
        if not re.fullmatch(r"@[a-z0-9-]+(\.[a-z0-9-]+)+", domain):
            raise forms.ValidationError("Enter a domain starting with @, e.g. @tisb.ac.in")
        return domain

    def save(self, commit=True):
        self.instance.claimed_visibility_days = {
            code: self.cleaned_data[f"days_{code}"]
            for code, _ in Item.Category.choices
            if self.cleaned_data.get(f"days_{code}") is not None
        }
        return super().save(commit)


class UploadSettingsForm(_SettingsForm):
    class Meta:
        model = SiteSettings
        fields = [
            "staff_uploads_require_approval", "superuser_uploads_auto_approve",
            "max_staff_upload_images", "ai_enabled", "ai_model",
        ]
        labels = {
            "staff_uploads_require_approval": "Admin (staff) uploads need Super User approval",
            "superuser_uploads_auto_approve": "Super User uploads are approved automatically",
            "max_staff_upload_images": "Max images per upload",
            "ai_enabled": "AI auto-fill of title and description",
            "ai_model": "Gemini model",
        }
        help_texts = {"ai_model": "e.g. gemini-2.5-flash. An unknown model makes AI auto-fill return nothing."}

    def clean_ai_model(self):
        model = self.cleaned_data["ai_model"].strip()
        # Goes into the API URL, so allow only model-name characters.
        if not re.fullmatch(r"[a-z0-9][a-z0-9.\-]*", model):
            raise forms.ValidationError("Use lowercase letters, digits, dots and hyphens only.")
        return model


class IntakeSettingsForm(_SettingsForm):
    class Meta:
        model = SiteSettings
        fields = [
            "email_reports_enabled", "intake_max_images", "intake_max_image_mb",
            "intake_max_total_mb", "intake_max_title_length", "intake_max_description_length",
        ]
        labels = {
            "email_reports_enabled": "Accept lost-item reports by email",
            "intake_max_images": "Max images kept per email",
            "intake_max_image_mb": "Max size per image (MB)",
            "intake_max_total_mb": "Max total attachments (MB)",
            "intake_max_title_length": "Max title length (characters)",
            "intake_max_description_length": "Max description length (characters)",
        }
        help_texts = {
            "email_reports_enabled": "When off, new emails stay unread and are processed once this is turned back on.",
        }

    def clean(self):
        data = super().clean()
        per, total = data.get("intake_max_image_mb"), data.get("intake_max_total_mb")
        if per and total and per > total:
            self.add_error("intake_max_image_mb", "Can't be larger than the total limit.")
        return data


class BroadcastSettingsForm(_SettingsForm):
    class Meta:
        model = SiteSettings
        fields = [
            "broadcast_recipients", "broadcast_limit_count", "broadcast_limit_hours",
            "broadcast_max_attachment_mb",
        ]
        labels = {
            "broadcast_recipients": "Recipients (BCC)",
            "broadcast_limit_count": "Max broadcasts per item…",
            "broadcast_limit_hours": "…within this many hours",
            "broadcast_max_attachment_mb": "Max total image attachments (MB)",
        }

    def clean_broadcast_recipients(self):
        raw = self.cleaned_data["broadcast_recipients"]
        emails = [e.strip().lower() for e in raw.replace(",", "\n").splitlines() if e.strip()]
        bad = []
        for e in emails:
            try:
                validate_email(e)
            except forms.ValidationError:
                bad.append(e)
        if bad:
            raise forms.ValidationError("Not valid email addresses: " + ", ".join(bad))
        return "\n".join(dict.fromkeys(emails))


class NoticeSettingsForm(_SettingsForm):
    class Meta:
        model = SiteSettings
        fields = ["claim_success_notice", "claim_warning", "claim_attestation", "misuse_disclaimer"]
        labels = {
            "claim_success_notice": "Shown after a successful claim",
            "claim_warning": "Warning above the claim form",
            "claim_attestation": "Claim attestation checkbox",
            "misuse_disclaimer": "Footer disclaimer (every page)",
        }


class PrivacySettingsForm(_SettingsForm):
    class Meta:
        model = SiteSettings
        fields = ["audit_retention_days", "log_page_views", "collect_fingerprint"]
        labels = {
            "audit_retention_days": "Keep audit logs for (days)",
            "log_page_views": "Log every page visit and form submission",
            "collect_fingerprint": "Collect browser/device details on claims and uploads",
        }
        help_texts = {
            "audit_retention_days": "Older records are deleted by the daily purge_access_logs job.",
            "log_page_views": "Claims, uploads, approvals, deletions and logins are always logged.",
        }


class EmailTemplateForm(forms.Form):
    subject = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"class": _INPUT_CLASS}))
    body = forms.CharField(widget=forms.Textarea(attrs={"class": _INPUT_CLASS + " font-mono", "rows": 16}))
    closing = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": _INPUT_CLASS + " font-mono", "rows": 4}),
    )

    def __init__(self, *args, key, **kwargs):
        super().__init__(*args, **kwargs)
        self.key = key
        if not EMAIL_TEMPLATES[key].get("has_closing"):
            del self.fields["closing"]
        else:
            self.fields["body"].label = "Opening paragraph"
            self.fields["body"].widget.attrs["rows"] = 4
            self.fields["closing"].label = "Closing paragraph"

    def clean(self):
        data = super().clean()
        allowed = allowed_placeholders(self.key)
        for name in ("subject", "body", "closing"):
            if name in self.fields and data.get(name) is not None:
                for err in validate_template_text(data[name], allowed):
                    self.add_error(name, err)
        return data
