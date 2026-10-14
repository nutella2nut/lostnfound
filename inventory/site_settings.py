"""Runtime settings editable by Super Users, plus the editable system emails.

Everything reads settings through get_site_settings(). It is deliberately not
cached across requests: the row is one primary-key lookup, and a process-local
cache would go stale across gunicorn workers and the email-poller process.
"""
import logging
import string
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import EmailTemplate, Item, SiteSettings

logger = logging.getLogger(__name__)

# Defaults for claimed-item visibility that differ from claimed_visibility_default_days.
DEFAULT_CLAIMED_VISIBILITY_DAYS = {
    Item.Category.ELECTRONICS: 7,
    Item.Category.SPORTS_AND_CLOTHING: 3,
}


def get_site_settings():
    """Return the SiteSettings row, creating it (seeded from env vars) on first use."""
    obj = SiteSettings.objects.filter(pk=1).first()
    if obj is None:
        obj = SiteSettings(
            pk=1,
            lf_email_address=getattr(settings, "LF_EMAIL_ADDRESS", ""),
            allowed_email_domain=getattr(settings, "LF_ALLOWED_SENDER_DOMAIN", "") or "@tisb.ac.in",
            broadcast_recipients="\n".join(getattr(settings, "LF_BROADCAST_RECIPIENTS_LIST", [])),
            sender_display_name=getattr(settings, "LF_EMAIL_DISPLAY_NAME", "") or "TRACE Lost & Found",
            claimed_visibility_days={k: v for k, v in DEFAULT_CLAIMED_VISIBILITY_DAYS.items()},
        )
        obj.save()
    return obj


def email_matches_domain(email, site=None):
    site = site or get_site_settings()
    return (email or "").strip().lower().endswith(site.allowed_email_domain.lower())


def claimed_visibility_days(category, site=None):
    site = site or get_site_settings()
    return int(site.claimed_visibility_days.get(category, site.claimed_visibility_default_days))


def visible_claimed_items_q(site=None):
    """Q matching claimed items still inside their category's public visibility window."""
    site = site or get_site_settings()
    now = timezone.now()
    q = Q()
    for category, _ in Item.Category.choices:
        q |= Q(
            status=Item.Status.CLAIMED,
            category=category,
            claimed_at__isnull=False,
            claimed_at__gte=now - timedelta(days=claimed_visibility_days(category, site)),
        )
    return q


# ---------------------------------------------------------------------------
# Editable system emails
# ---------------------------------------------------------------------------

# Available in every template.
GLOBAL_PLACEHOLDERS = {
    "site_name": "Site name, e.g. TRACE",
    "school_name": "School name, e.g. TISB",
    "signoff": "Email sign-off line",
    "contact_email": "Public contact address",
}

EMAIL_TEMPLATES = {
    "claim_confirmation": {
        "label": "Claim confirmation (to claimant)",
        "placeholders": {
            "name": "Claimant's name",
            "item_title": "Item title",
            "category": "Item category",
            "location_found": "Where it was found",
            "date_found": "Date found",
            "claimed_at": "Claim date/time (IST)",
        },
        "subject": 'Your claim has been recorded — "{item_title}"',
        "body": (
            "Hi {name},\n\n"
            "This email confirms that you have submitted a claim for the following "
            "item through TRACE, the TISB Lost & Found system.\n\n"
            "Item:           {item_title}\n"
            "Category:       {category}\n"
            "Found at:       {location_found}\n"
            "Found on:       {date_found}\n"
            "Claim submitted: {claimed_at}\n\n"
            "To take possession of this item you must come in person to the school reception "
            "during school hours. Please bring a valid form of TISB identification. The item "
            "will only be released to you in person — it will not be released to any other "
            "student, sibling, parent, or staff member acting on your behalf.\n\n"
            "If you did not submit this claim, reply to this email immediately so that "
            "staff can investigate.\n\n"
            "{signoff}"
        ),
    },
    "report_approved": {
        "label": "Student report approved",
        "placeholders": {"first_name": "Student's first name", "item_title": "Item title"},
        "subject": 'Your lost item report has been approved — "{item_title}"',
        "body": (
            "Hi {first_name},\n\n"
            "Your lost item report has been reviewed and approved by TRACE staff. "
            "It is now visible on the Students' Lost Items page of TRACE.\n\n"
            "Item: {item_title}\n\n"
            "If this item is found, you will be contacted at this email address. "
            "To take possession of the item you must come in person to the school reception "
            "during school hours and present a valid form of TISB identification.\n\n"
            "{signoff}"
        ),
    },
    "report_rejected": {
        "label": "Student report rejected",
        "placeholders": {
            "first_name": "Student's first name",
            "item_title": "Item title",
            "submitted_at": "Submission date/time (IST)",
            "reason_line": 'The line "Reason provided by staff: …" (blank if no reason given)',
            "report_email": "Mailbox students send reports to",
        },
        "subject": 'Your lost item report was not approved — "{item_title}"',
        "body": (
            "Hi {first_name},\n\n"
            "Your lost item report submitted on {submitted_at} was reviewed "
            "by TRACE staff and was not approved for display.\n\n"
            "{reason_line}"
            "If you believe this decision was made in error, or if you would like "
            "to resubmit with additional information, you may send a new email to "
            "{report_email}. Please follow the submission format "
            "described on the \"How to report a lost item\" page of TRACE.\n\n"
            "{signoff}"
        ),
    },
    "report_acknowledgment": {
        "label": "Student report received (acknowledgment)",
        "placeholders": {
            "first_name": "Student's first name",
            "item_title": "Item title",
            "submitted_at": "Submission date/time (IST)",
            "image_count": "Number of images attached",
        },
        "subject": 'Received: your lost item report — "{item_title}"',
        "body": (
            "Hi {first_name},\n\n"
            "This is an automated confirmation that TRACE — the TISB Lost & Found system — "
            "has received your lost item report.\n\n"
            "Submission summary\n"
            "------------------\n"
            "Title:        {item_title}\n"
            "Submitted at: {submitted_at}\n"
            "Images:       {image_count} attached\n\n"
            "What happens next\n"
            "-----------------\n"
            "1. Your report is now in the approval queue. A staff member will review it.\n"
            "2. If approved, your report will appear on the \"Students' Lost Items\" page of TRACE, "
            "visible to the school community.\n"
            "3. If a staff member or another student matches your report to a found item, "
            "you will be notified by email at this address.\n"
            "4. To collect any matched item, you must come in person to the school reception. "
            "Items will not be released to anyone other than the rightful owner, in person.\n\n"
            "This is an automated message — do not reply to this email. "
            "If you need to follow up, contact your Head of Year or the school reception.\n\n"
            "{signoff}"
        ),
    },
    "report_acknowledgment_oversized": {
        "label": "Student report received, images too large",
        "placeholders": {
            "first_name": "Student's first name",
            "item_title": "Item title",
            "submitted_at": "Submission date/time (IST)",
            "max_image_mb": "Per-image limit in MB",
            "max_total_mb": "Total attachment limit in MB",
        },
        "subject": "Action needed: your lost item report could not be fully processed",
        "body": (
            "Hi {first_name},\n\n"
            "This is an automated message from TRACE — the TISB Lost & Found system.\n\n"
            "We received your lost item report, but the combined size of the attached images "
            "exceeded the {max_total_mb} MB limit. Your report has been saved without images.\n\n"
            "Title: {item_title}\n"
            "Submitted at: {submitted_at}\n\n"
            "Please resend your report with smaller images (under {max_image_mb} MB each, "
            "under {max_total_mb} MB total), "
            "or send a description-only email without attachments.\n\n"
            "{signoff}"
        ),
    },
    "broadcast_lost": {
        "label": "Broadcast: student lost item",
        "placeholders": {"item_title": "Item title"},
        "has_closing": True,
        "subject": 'TISB Lost & Found — Lost item reported: "{item_title}"',
        "body": (
            "A student has reported the following item as lost. If you have seen this item, "
            "or if you have it in your possession, please bring it to the school reception in person."
        ),
        "closing": (
            "If this item is yours and has been found, you must collect it in person from "
            "the school reception. The Lost & Found system does not release items to anyone "
            "other than the rightful owner, in person."
        ),
    },
    "broadcast_found": {
        "label": "Broadcast: found item",
        "placeholders": {"item_title": "Item title"},
        "has_closing": True,
        "subject": 'TISB Lost & Found — Item found: "{item_title}"',
        "body": (
            "An item has been found and logged by TRACE staff. If you recognise this item "
            "as your personal property, please come to the school reception in person to claim it."
        ),
        "closing": (
            "To take possession of this item you must come in person to the school reception "
            "during school hours and present a valid form of TISB identification. Items will "
            "not be handed over to any person other than the rightful owner, in person."
        ),
    },
}


def allowed_placeholders(key):
    return {**GLOBAL_PLACEHOLDERS, **EMAIL_TEMPLATES[key]["placeholders"]}


def validate_template_text(text, allowed):
    """Return a list of error strings for a template ({} = none).

    Only bare {name} fields from the allowed set are permitted: attribute/index
    access ({x.y}, {x[0]}), conversions and format specs are rejected so a
    template can never reach into Python objects.
    """
    errors = []
    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError as exc:
        return [f"Invalid braces ({exc}). Use {{{{ and }}}} for literal braces."]
    for _literal, field, spec, conversion in parsed:
        if field is None:
            continue
        if field not in allowed:
            errors.append(f"Unknown placeholder {{{field}}}.")
        elif spec or conversion:
            errors.append(f"Placeholder {{{field}}} must not have a format or conversion.")
    return errors


def get_email_template(key):
    """Return (subject, body, closing) source text — the saved override or the default."""
    default = EMAIL_TEMPLATES[key]
    row = EmailTemplate.objects.filter(key=key).first()
    if row:
        return row.subject, row.body, row.closing
    return default["subject"], default["body"], default.get("closing", "")


def render_email(key, **context):
    """Render an editable email. Returns (subject, body, closing).

    Falls back to the built-in default if a saved override somehow fails to
    render, so a bad edit can never stop an email from going out.
    """
    site = get_site_settings()
    ctx = {
        "site_name": site.site_name,
        "school_name": site.school_name,
        "signoff": site.email_signoff,
        "contact_email": site.public_contact_email,
        **{k: "" if v is None else v for k, v in context.items()},
    }
    subject, body, closing = get_email_template(key)
    try:
        return subject.format_map(ctx), body.format_map(ctx), closing.format_map(ctx)
    except (KeyError, ValueError, IndexError, AttributeError):
        logger.exception("Email template %s failed to render; using default", key)
        d = EMAIL_TEMPLATES[key]
        return (
            d["subject"].format_map(ctx),
            d["body"].format_map(ctx),
            d.get("closing", "").format_map(ctx),
        )
