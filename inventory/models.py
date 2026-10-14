from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class UserProfile(models.Model):
    """Extended user profile for Lost & Found system."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lost_found_profile",
    )

    def __str__(self):
        return f"{self.user.username} - {'Super User' if self.user.is_superuser else 'Admin'}"


class Item(models.Model):
    class Status(models.TextChoices):
        FOUND = "FOUND", "Found"
        CLAIMED = "CLAIMED", "Claimed"
        COLLECTED = "COLLECTED", "Collected by Student"

    class Category(models.TextChoices):
        ELECTRONICS = "ELECTRONICS", "Electronics"
        BAGS_AND_CARRY = "BAGS_AND_CARRY", "Bags and Carry"
        SPORTS_AND_CLOTHING = "SPORTS_AND_CLOTHING", "Sports and clothing"
        BOTTLES_AND_CONTAINERS = "BOTTLES_AND_CONTAINERS", "Bottles and containers"
        DOCUMENTS_AND_IDS = "DOCUMENTS_AND_IDS", "Documents and Id's"
        NOTEBOOKS_AND_BOOKS = "NOTEBOOKS_AND_BOOKS", "Notebooks/books"
        OTHER_MISC = "OTHER_MISC", "Other/Misc"

    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class ItemType(models.TextChoices):
        SENIOR = "SENIOR", "Senior Years"
        PY = "PY", "Primary Years"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    location_found = models.CharField(max_length=255, blank=True)
    date_found = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.FOUND,
        db_index=True,
    )
    category = models.CharField(
        max_length=40,
        choices=Category.choices,
        default=Category.OTHER_MISC,
        db_index=True,
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
        db_index=True,
        help_text="Approval status for admin-uploaded items",
    )
    item_type = models.CharField(
        max_length=10,
        choices=ItemType.choices,
        default=ItemType.SENIOR,
        db_index=True,
        help_text="Whether this item is for Senior Years or Primary Years",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=500, blank=True)
    claimed_by_name = models.CharField(max_length=255, blank=True, help_text="Name of person who claimed this item")
    claimed_at = models.DateTimeField(null=True, blank=True, help_text="When this item was claimed")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_found", "-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["date_found"]),
            models.Index(fields=["category"]),
            models.Index(fields=["approval_status"]),
            models.Index(fields=["item_type"]),
            models.Index(fields=["approval_status", "item_type"]),
        ]

    def __str__(self) -> str:
        return self.title
    
    @property
    def claim_count(self):
        """Return the number of claims for this item."""
        return self.claims.count()
    
    @property
    def latest_claim(self):
        """Return the most recent claim."""
        return self.claims.order_by('-claimed_at').first()


class Claim(models.Model):
    """Track individual claims for items - allows multiple people to claim the same item."""
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="claims",
    )
    claimant_name = models.CharField(
        max_length=255,
        help_text="Name of person claiming this item",
    )
    claimant_email = models.EmailField(
        blank=True,
        default="",
        help_text="Email of the person claiming this item",
    )
    claimed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-claimed_at']
        indexes = [
            models.Index(fields=['item', '-claimed_at']),
        ]
    
    def __str__(self) -> str:
        return f"{self.claimant_name} claimed {self.item.title}"


class ItemImage(models.Model):
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="item_images/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Image for {self.item_id}"


class StudentLostItem(models.Model):
    """Model for student-submitted lost items via email."""
    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    email_subject = models.CharField(
        max_length=500,
        help_text="Original email subject",
    )
    email_from = models.EmailField(
        help_text="Email address of the student who submitted",
    )
    submitter_display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display name parsed from the email From header",
    )
    source_message_id = models.CharField(
        max_length=998,
        blank=True,
        db_index=True,
        help_text="Email Message-ID for deduplication",
    )
    needs_review_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Semicolon-separated canonical review reasons",
    )
    rejection_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Reason for rejection provided by staff",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_items_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["approval_status"]),
            models.Index(fields=["submitted_at"]),
        ]

    def __str__(self) -> str:
        return self.title


class StudentLostItemImage(models.Model):
    """Images for student-submitted lost items."""
    student_item = models.ForeignKey(
        StudentLostItem,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="student_item_images/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Image for {self.student_item_id}"


class MicrosoftOAuthToken(models.Model):
    """Singleton model storing the Microsoft OAuth2 refresh/access tokens."""
    account_email = models.EmailField(
        help_text="The mailbox the token authorizes access to.",
    )
    encrypted_refresh_token = models.BinaryField(
        help_text="Fernet-encrypted refresh token.",
    )
    cached_access_token = models.TextField(
        blank=True,
        help_text="Last access token in cleartext, valid until cached_access_token_expires_at.",
    )
    cached_access_token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(help_text="Space-separated scopes the token grants.")
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Microsoft OAuth Token"
        verbose_name_plural = "Microsoft OAuth Tokens"

    def save(self, *args, **kwargs):
        if not self.pk and MicrosoftOAuthToken.objects.exists():
            raise ValidationError(
                "Only one MicrosoftOAuthToken row may exist. Delete the existing one first."
            )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"OAuth token for {self.account_email}"


class BroadcastLog(models.Model):
    """Audit log of broadcast emails sent to the school body."""
    BROADCAST_KIND_CHOICES = [
        ("STUDENT_LOST", "Student lost item"),
        ("FOUND_ITEM", "Found item"),
    ]
    kind = models.CharField(max_length=20, choices=BROADCAST_KIND_CHOICES)
    student_lost_item = models.ForeignKey(
        StudentLostItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="broadcasts",
    )
    found_item = models.ForeignKey(
        Item,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="broadcasts",
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="broadcasts_sent",
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    recipients = models.TextField(
        help_text="Comma-separated recipient addresses at time of send.",
    )
    subject = models.CharField(max_length=255)
    body_preview = models.TextField(
        help_text="First 1000 chars of the body sent, for audit.",
    )
    succeeded = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-sent_at"]
        indexes = [models.Index(fields=["kind", "-sent_at"])]

    def clean(self):
        super().clean()
        if self.kind == "STUDENT_LOST" and not self.student_lost_item_id:
            raise ValidationError("STUDENT_LOST broadcast must have a student_lost_item.")
        if self.kind == "FOUND_ITEM" and not self.found_item_id:
            raise ValidationError("FOUND_ITEM broadcast must have a found_item.")
        if self.student_lost_item_id and self.found_item_id:
            raise ValidationError("A broadcast must reference exactly one item type.")

    def __str__(self) -> str:
        return f"Broadcast ({self.kind}) at {self.sent_at}"


class UserRoleChangeLog(models.Model):
    """Audit log of every role change in the user management UI."""
    ACTION_CHOICES = [
        ("CREATE", "User created"),
        ("PROMOTE_ADMIN", "Granted Admin access"),
        ("PROMOTE_SUPERUSER", "Granted Super User access"),
        ("DEMOTE_TO_ADMIN", "Demoted from Super User to Admin"),
        ("REVOKE_STAFF", "Revoked staff access"),
        ("DEACTIVATE", "Deactivated"),
        ("REACTIVATE", "Reactivated"),
        ("DELETE", "Deleted"),
        ("EDIT_PROFILE", "Profile edited (name/email)"),
        ("PASSWORD_RESET", "Password reset by Super User"),
    ]
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_changes_received",
        help_text="The user whose role was changed. SET_NULL so the log survives user deletion.",
    )
    target_username_snapshot = models.CharField(
        max_length=150,
        help_text="Username at time of change (in case the user is later deleted).",
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_changes_performed",
    )
    performed_by_username_snapshot = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    details = models.TextField(
        blank=True,
        help_text="Free-text details, e.g. 'is_staff: False → True; is_superuser: False → True'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_user", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} on {self.target_username_snapshot} by {self.performed_by_username_snapshot}"


class AccessAuditLog(models.Model):
    """Audit record of user activity: every page visit and form submission,
    plus specific events (claims, uploads, approvals, deletions, logins,
    emailed reports).

    Captures who acted and the identifying request metadata (IP, browser,
    device) for anti-misuse investigations. Rows are write-once — there is no
    edit path — and are viewable by Super Users only.
    """
    ACTION_CHOICES = [
        ("CLAIM", "Item claim"),
        ("CLAIM_FAILED", "Failed claim attempt"),
        ("ITEM_UPLOAD", "Item upload"),
        ("ITEM_APPROVE", "Item approved"),
        ("ITEM_REJECT", "Item rejected"),
        ("ITEM_COLLECTED", "Item marked collected"),
        ("ITEM_DELETE", "Item deleted"),
        ("STUDENT_REPORT", "Student lost-item report (email)"),
        ("LOGIN", "Login"),
        ("LOGIN_FAILED", "Failed login"),
        ("LOGOUT", "Logout"),
        ("SETTINGS_CHANGE", "Settings changed"),
        ("PAGE_VIEW", "Page visit"),
        ("FORM_SUBMIT", "Form submission"),
    ]
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    # Actor — the logged-in user (uploads). Null for anonymous claims.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
    )
    actor_username_snapshot = models.CharField(
        max_length=150,
        blank=True,
        help_text="Username at time of action (survives user deletion).",
    )

    # Objects the action touched.
    item = models.ForeignKey(
        Item,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
    )
    claim = models.ForeignKey(
        Claim,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
    )
    student_item = models.ForeignKey(
        StudentLostItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
    )
    item_title_snapshot = models.CharField(
        max_length=255,
        blank=True,
        help_text="Item title at time of action (survives item deletion).",
    )

    # Claimant identity snapshots (survive deletion of the Claim/Item).
    subject_name = models.CharField(max_length=255, blank=True)
    subject_email = models.EmailField(blank=True)

    # Server-side request metadata.
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    forwarded_for = models.TextField(
        blank=True,
        help_text="Full X-Forwarded-For chain as received.",
    )
    user_agent = models.TextField(blank=True)
    accept_language = models.CharField(max_length=255, blank=True)
    referer = models.TextField(blank=True)
    request_path = models.CharField(max_length=255, blank=True)
    request_method = models.CharField(max_length=10, blank=True)

    # Client-side browser/device blob gathered by inline JS.
    client_metadata = models.JSONField(default=dict, blank=True)

    # Action-specific extras (form errors, attempted username, email headers…).
    details = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["ip_address"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} at {self.created_at} from {self.ip_address or 'unknown IP'}"


class SiteSettings(models.Model):
    """Single-row table of runtime settings editable by Super Users at /staff/settings/.

    Defaults match the behaviour that was previously hardcoded. Secrets and
    infrastructure stay in environment variables. Always read through
    ``inventory.site_settings.get_site_settings()``, which creates the row on
    first use.
    """
    # General & branding
    site_name = models.CharField(max_length=60, default="TRACE")
    school_name = models.CharField(max_length=60, default="TISB")
    email_signoff = models.CharField(max_length=120, default="— TRACE, TISB Lost & Found")
    sender_display_name = models.CharField(max_length=120, default="TRACE Lost & Found")
    contact_email = models.EmailField(
        blank=True,
        help_text="Address shown to users. Leave blank to use the lost & found mailbox.",
    )
    lf_email_address = models.EmailField(
        blank=True,
        help_text="Mailbox students email reports to; also the From address on all emails.",
    )
    announcement_enabled = models.BooleanField(default=False)
    announcement_text = models.TextField(blank=True)

    # Claims
    allowed_email_domain = models.CharField(max_length=100, default="@tisb.ac.in")
    claims_enabled = models.BooleanField(default=True)
    allow_multiple_claims = models.BooleanField(default=True)
    claimed_visibility_days = models.JSONField(
        default=dict, blank=True,
        help_text="Days a claimed item stays on public lists, keyed by category code.",
    )
    claimed_visibility_default_days = models.PositiveIntegerField(default=1)

    # Uploads & approval
    staff_uploads_require_approval = models.BooleanField(default=True)
    superuser_uploads_auto_approve = models.BooleanField(default=True)
    max_staff_upload_images = models.PositiveIntegerField(default=3)
    ai_enabled = models.BooleanField(default=True)
    ai_model = models.CharField(max_length=80, default="gemini-2.5-flash")

    # Student email intake
    email_reports_enabled = models.BooleanField(default=True)
    intake_max_images = models.PositiveIntegerField(default=8)
    intake_max_image_mb = models.PositiveIntegerField(default=15)
    intake_max_total_mb = models.PositiveIntegerField(default=40)
    intake_max_title_length = models.PositiveIntegerField(default=200)
    intake_max_description_length = models.PositiveIntegerField(default=5000)

    # Broadcasts
    broadcast_recipients = models.TextField(blank=True, help_text="One email address per line.")
    broadcast_limit_count = models.PositiveIntegerField(default=3)
    broadcast_limit_hours = models.PositiveIntegerField(default=24)
    broadcast_max_attachment_mb = models.PositiveIntegerField(default=20)

    # Notices
    claim_success_notice = models.TextField(
        default=(
            "To take possession of this item you must come in person to the school reception "
            "during school hours and present a valid form of TISB identification. "
            "Items will not be handed over to any person other than the named claimant."
        ),
    )
    misuse_disclaimer = models.TextField(
        default=(
            "TRACE is operated by TISB. All claims and reports are logged. "
            "Misuse will be referred to the relevant Head of Year."
        ),
    )
    claim_warning = models.TextField(
        default=(
            "By submitting this form you are formally claiming that this specific item belongs to you. "
            "False claims, claims on behalf of someone else, and claims intended to deprive the rightful "
            "owner of their property are violations of the TISB Code of Conduct and will be referred to "
            "the relevant Head of Year."
        ),
    )
    claim_attestation = models.TextField(
        default=(
            "attest that this item is my personal property, that I am submitting this claim on my own "
            "behalf, and that I will collect this item in person from the school reception. I understand "
            "that submitting a false claim is a disciplinary matter."
        ),
        help_text='Shown after "I, <claimant name>,".',
    )

    # Audit & privacy
    audit_retention_days = models.PositiveIntegerField(default=365)
    log_page_views = models.BooleanField(default=True)
    collect_fingerprint = models.BooleanField(default=True)
    last_audit_purge_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return "Site settings"

    @property
    def broadcast_recipient_list(self):
        return [
            line.strip() for line in self.broadcast_recipients.replace(",", "\n").splitlines()
            if line.strip()
        ]

    @property
    def email_pattern(self):
        """HTML ``pattern`` attribute matching addresses on the allowed domain."""
        # Escape by hand: browsers compile `pattern` with the `v` flag, which
        # rejects re.escape()'s needless escapes such as "\-".
        domain = "".join("\\" + c if c in ".^$*+?()[]{}|/\\" else c for c in self.allowed_email_domain)
        return "^[a-zA-Z0-9._%+\\-]+" + domain + "$"

    @property
    def public_contact_email(self):
        return self.contact_email or self.lf_email_address


class EmailTemplate(models.Model):
    """Super-User-edited override of a system email. Defaults live in
    ``inventory.site_settings.EMAIL_TEMPLATES``; a missing row means "use default"."""
    key = models.CharField(max_length=50, unique=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    closing = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.key
