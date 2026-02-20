from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """Extended user profile to track Super User status for Lost & Found system."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lost_found_profile",
    )
    is_super_user = models.BooleanField(
        default=False,
        help_text="Super Users can approve items and upload without approval",
    )

    def save(self, *args, **kwargs):
    if self.user.username == "advait":  # replace with your username
        self.is_super_user = True
    super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {'Super User' if self.is_super_user else 'Admin'}"


class Item(models.Model):
    class Status(models.TextChoices):
        FOUND = "FOUND", "Found"
        CLAIMED = "CLAIMED", "Claimed"

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
    claimant_name = models.CharField(max_length=255, help_text="Name of person claiming this item")
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
    email_subject = models.CharField(max_length=500, help_text="Original email subject")
    email_from = models.EmailField(help_text="Email address of the student who submitted")
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


