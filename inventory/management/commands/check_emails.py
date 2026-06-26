"""Fetch unseen emails from the configured mailbox and create StudentLostItem entries.

Implements §1.3 email parsing rules with XOAUTH2 IMAP authentication (§1.9.9).
"""

import email
import hashlib
import imaplib
import logging
import re
import signal
import time
from email.header import decode_header, make_header
from email.utils import parseaddr
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.constants import NEEDS_REVIEW_REASONS
from inventory.models import StudentLostItem, StudentLostItemImage

logger = logging.getLogger("inventory.check_emails")

# Limits per §1.3.4
MAX_IMAGE_SIZE = 15 * 1024 * 1024  # 15 MB
MAX_TOTAL_SIZE = 40 * 1024 * 1024  # 40 MB
MAX_IMAGES = 8
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 5000

# Accepted image extensions per §1.3.4
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp"}

# Patterns for stripping subject prefixes §1.3.2
SUBJECT_PREFIX_RE = re.compile(r"^(Re|Fwd|FW|RE|FWD)\s*:\s*", re.IGNORECASE)

# Patterns for stripping quoted reply history §1.3.3
QUOTE_LINE_RE = re.compile(r"^>+\s?")
ON_WROTE_RE = re.compile(r"^On .+wrote:\s*$", re.IGNORECASE)
SIGNATURE_SEPARATOR_RE = re.compile(r"^-- \s*$")
SENT_FROM_RE = re.compile(r"^Sent from my (iPhone|iPad|Android|Galaxy|Samsung|Pixel)", re.IGNORECASE)


def decode_mime_header(value):
    """Decode MIME-encoded email header to a readable string."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def strip_subject_prefixes(subject):
    """Remove Re:, Fwd:, etc. prefixes (repeated)."""
    prev = None
    while prev != subject:
        prev = subject
        subject = SUBJECT_PREFIX_RE.sub("", subject).strip()
    return subject


def strip_html_tags(html):
    """Strip HTML tags, returning plain text."""
    try:
        import bleach
        return bleach.clean(html, tags=[], strip=True)
    except ImportError:
        return re.sub(r"<[^>]+>", "", html)


def strip_quoted_and_signature(text):
    """Strip quoted reply history and email signatures."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        # Stop at signature separator
        if SIGNATURE_SEPARATOR_RE.match(line):
            break
        # Stop at "Sent from my ..."
        if SENT_FROM_RE.match(line.strip()):
            break
        # Stop at "On ... wrote:" blocks
        if ON_WROTE_RE.match(line.strip()):
            break
        # Skip quoted lines
        if QUOTE_LINE_RE.match(line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def strip_exif_gps(image_bytes):
    """Strip EXIF GPS data from image bytes. Returns (cleaned_bytes, success)."""
    try:
        from PIL import Image
        img = Image.open(BytesIO(image_bytes))
        exif = img.getexif()
        # GPS IFD tag
        GPS_TAG = 0x8825
        if GPS_TAG in exif:
            del exif[GPS_TAG]
        # Re-save without GPS
        output = BytesIO()
        img.save(output, format=img.format or "JPEG", exif=exif.tobytes() if exif else b"")
        output.seek(0)
        return output.read(), True
    except Exception as e:
        logger.warning("EXIF GPS stripping failed: %s", e)
        return image_bytes, False


def is_image_attachment(part):
    """Check if an email part is an image attachment."""
    content_type = part.get_content_type() or ""
    if content_type.startswith("image/"):
        return True
    filename = part.get_filename() or ""
    if filename:
        import os
        ext = os.path.splitext(filename)[1].lower()
        return ext in IMAGE_EXTENSIONS
    return False


def connect_imap():
    """Connect and authenticate to IMAP, using XOAUTH2 if available."""
    imap_host = settings.LF_IMAP_HOST
    imap_port = int(settings.LF_IMAP_PORT)

    mail = imaplib.IMAP4_SSL(imap_host, imap_port)

    if getattr(settings, "MS_OAUTH_CLIENT_ID", ""):
        from inventory.ms_oauth import get_access_token, force_refresh
        access_token = get_access_token()
        auth_string = f"user={settings.LF_EMAIL_ADDRESS}\x01auth=Bearer {access_token}\x01\x01"
        try:
            mail.authenticate("XOAUTH2", lambda _: auth_string.encode())
        except imaplib.IMAP4.error:
            logger.warning("XOAUTH2 auth failed, forcing refresh and retrying...")
            access_token = force_refresh()
            auth_string = f"user={settings.LF_EMAIL_ADDRESS}\x01auth=Bearer {access_token}\x01\x01"
            mail.authenticate("XOAUTH2", lambda _: auth_string.encode())
    else:
        email_password = settings.LF_EMAIL_PASSWORD
        if not email_password:
            raise RuntimeError(
                "Neither MS_OAUTH_CLIENT_ID nor LF_EMAIL_PASSWORD is set. "
                "Cannot authenticate to IMAP."
            )
        mail.login(settings.LF_EMAIL_ADDRESS, email_password)

    return mail


class Command(BaseCommand):
    help = "Fetch unseen emails from the configured mailbox and create StudentLostItem entries."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", default=True, help="Run once (default)")
        parser.add_argument("--loop", type=int, default=0, metavar="SECONDS",
                            help="Run forever with SECONDS sleep between cycles")

    def handle(self, *args, **options):
        email_address = getattr(settings, "LF_EMAIL_ADDRESS", "")
        imap_host = getattr(settings, "LF_IMAP_HOST", "")

        if not email_address or not imap_host:
            self.stderr.write("LF_EMAIL_ADDRESS and LF_IMAP_HOST must be set.")
            return

        loop_seconds = options.get("loop", 0)
        self._running = True

        if loop_seconds:
            def handle_sigterm(sig, frame):
                logger.info("Received SIGTERM, shutting down...")
                self._running = False
            signal.signal(signal.SIGTERM, handle_sigterm)
            signal.signal(signal.SIGINT, handle_sigterm)

        while self._running:
            self._run_cycle()
            if not loop_seconds:
                break
            logger.info("Sleeping %d seconds before next cycle...", loop_seconds)
            time.sleep(loop_seconds)

    def _run_cycle(self):
        """Single email-check cycle."""
        allowed_domain = settings.LF_ALLOWED_SENDER_DOMAIN
        n_fetched = 0
        n_created = 0
        n_skipped = 0
        n_failed = 0

        try:
            mail = connect_imap()
        except Exception as exc:
            logger.error("IMAP connection failed: %s", exc)
            return

        try:
            mail.select(settings.LF_IMAP_MAILBOX)
            status, data = mail.search(None, "UNSEEN")
            if status != "OK":
                logger.error("Failed to search mailbox.")
                return

            message_ids = data[0].split() if data[0] else []
            n_fetched = len(message_ids)

            if not message_ids:
                logger.info("No new messages found.")
                return

            for num in message_ids:
                try:
                    created = self._process_message(mail, num, allowed_domain)
                    if created:
                        n_created += 1
                    else:
                        n_skipped += 1
                except Exception as exc:
                    n_failed += 1
                    logger.error("Failed to process message %s: %s", num, exc, exc_info=True)

        finally:
            try:
                mail.logout()
            except Exception:
                pass

        logger.info(
            "check_emails run complete: %d fetched, %d created, %d skipped, %d failed",
            n_fetched, n_created, n_skipped, n_failed,
        )

    def _process_message(self, mail, num, allowed_domain):
        """Process a single IMAP message. Returns True if a StudentLostItem was created."""
        status, msg_data = mail.fetch(num, "(RFC822)")
        if status != "OK":
            return False

        msg = email.message_from_bytes(msg_data[0][1])

        # Parse From header
        raw_from = msg.get("From", "")
        display_name, from_email = parseaddr(raw_from)
        if not from_email:
            logger.warning("Could not parse From header: %s", raw_from)
            return False

        from_email = from_email.strip().lower()
        display_name = decode_mime_header(display_name).strip()

        # §1.3.1 Sender validation
        if allowed_domain and not from_email.endswith(allowed_domain.lower()):
            logger.info("Skipped email from non-TISB sender: %s", from_email)
            mail.store(num, "+FLAGS", "\\Seen")
            return False

        # §1.3.5 Deduplication via Message-ID
        message_id = decode_mime_header(msg.get("Message-ID", "")).strip()
        source_message_id = message_id
        if not source_message_id:
            # Fallback hash
            subject_raw = decode_mime_header(msg.get("Subject", ""))
            body_preview = self._extract_body(msg)[:500]
            first_attachment = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if is_image_attachment(part):
                        first_attachment = part.get_filename() or ""
                        break
            hash_input = f"{from_email}|{subject_raw}|{body_preview}|{first_attachment}"
            source_message_id = "hash:" + hashlib.sha256(hash_input.encode()).hexdigest()[:64]

        if StudentLostItem.objects.filter(source_message_id=source_message_id).exists():
            logger.info("Duplicate message, skipping: %s", source_message_id[:80])
            mail.store(num, "+FLAGS", "\\Seen")
            return False

        # §1.3.2 Subject → Title
        raw_subject = decode_mime_header(msg.get("Subject", "")).strip()
        title = strip_subject_prefixes(raw_subject)
        review_reasons = []

        if not title:
            title = "Untitled lost item submission"
            review_reasons.append("TITLE_MISSING")

        if len(title) > MAX_TITLE_LENGTH:
            title = title[:MAX_TITLE_LENGTH] + "…"
            logger.info("Title truncated to %d chars for: %s", MAX_TITLE_LENGTH, from_email)

        # §1.3.3 Body → Description
        body = self._extract_body(msg)
        body = strip_quoted_and_signature(body).strip()

        if not body:
            body = "No description was provided by the student in the email body."
            review_reasons.append("BODY_EMPTY")

        if len(body) > MAX_DESCRIPTION_LENGTH:
            body = body[:MAX_DESCRIPTION_LENGTH] + "\n\n[Description truncated — original email body exceeded 5000 characters.]"

        # §1.3.4 Attachments → Images
        images = []
        total_size = 0
        oversized_total = False
        if msg.is_multipart():
            for part in msg.walk():
                if not is_image_attachment(part):
                    continue

                filename = decode_mime_header(part.get_filename() or "image.jpg")
                img_bytes = part.get_payload(decode=True) or b""
                if not img_bytes:
                    continue

                size = len(img_bytes)

                if size > MAX_IMAGE_SIZE:
                    review_reasons.append("ATTACHMENT_OVERSIZED")
                    logger.info("Skipping oversized attachment (%d bytes): %s", size, filename)
                    continue

                total_size += size
                if total_size > MAX_TOTAL_SIZE:
                    oversized_total = True
                    review_reasons.append("TOTAL_OVERSIZED")
                    logger.info("Total attachment size exceeded 40 MB")
                    break

                if len(images) >= MAX_IMAGES:
                    review_reasons.append("TOO_MANY_IMAGES")
                    break

                # EXIF GPS stripping §1.3.4
                cleaned_bytes, exif_ok = strip_exif_gps(img_bytes)
                if not exif_ok:
                    review_reasons.append("EXIF_STRIP_FAILED")
                    cleaned_bytes = img_bytes

                images.append((filename, cleaned_bytes))

        if oversized_total:
            images = []
            body += "\n\n[Note: combined attachment size exceeded 40 MB. Images were not attached to this submission.]"

        n_total_attachments = sum(
            1 for part in msg.walk() if is_image_attachment(part)
        ) if msg.is_multipart() else 0

        if n_total_attachments > MAX_IMAGES and "TOO_MANY_IMAGES" in review_reasons:
            body += f"\n\n[Note: this submission included {n_total_attachments} images; only the first {MAX_IMAGES} were attached.]"

        # Deduplicate review reasons and join
        seen_reasons = set()
        unique_reasons = []
        # Maintain canonical order
        for key in NEEDS_REVIEW_REASONS:
            if key in review_reasons and key not in seen_reasons:
                unique_reasons.append(NEEDS_REVIEW_REASONS[key])
                seen_reasons.add(key)

        needs_review_reason = "; ".join(unique_reasons)
        if len(needs_review_reason) > 500:
            needs_review_reason = needs_review_reason[:497] + "..."

        # Create the StudentLostItem
        student_item = StudentLostItem.objects.create(
            title=title,
            description=body,
            email_subject=raw_subject or "",
            email_from=from_email,
            submitter_display_name=display_name,
            source_message_id=source_message_id,
            needs_review_reason=needs_review_reason,
        )

        # Save images
        for filename, img_bytes in images:
            try:
                image_file = ContentFile(img_bytes, name=filename)
                StudentLostItemImage.objects.create(
                    student_item=student_item,
                    image=image_file,
                )
            except Exception as exc:
                logger.error("Failed to save image %s: %s", filename, exc)

        # §1.3.8 Mark as Seen AFTER DB commit
        mail.store(num, "+FLAGS", "\\Seen")

        # §1.4 Acknowledgment email
        self._send_acknowledgment(student_item, oversized_total)

        logger.info("Created StudentLostItem #%d: %s", student_item.pk, title[:60])
        return True

    def _extract_body(self, msg):
        """Extract body text from an email message."""
        if msg.is_multipart():
            # Try text/plain first
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = part.get("Content-Disposition", "")
                if content_type == "text/plain" and "attachment" not in disposition:
                    try:
                        return (part.get_payload(decode=True) or b"").decode(
                            part.get_content_charset() or "utf-8", "ignore"
                        )
                    except Exception:
                        return (part.get_payload(decode=True) or b"").decode("utf-8", "ignore")

            # Fall back to text/html stripped
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = part.get("Content-Disposition", "")
                if content_type == "text/html" and "attachment" not in disposition:
                    try:
                        html = (part.get_payload(decode=True) or b"").decode(
                            part.get_content_charset() or "utf-8", "ignore"
                        )
                        return strip_html_tags(html)
                    except Exception:
                        pass
            return ""
        else:
            content_type = msg.get_content_type()
            try:
                raw = (msg.get_payload(decode=True) or b"").decode(
                    msg.get_content_charset() or "utf-8", "ignore"
                )
            except Exception:
                raw = (msg.get_payload(decode=True) or b"").decode("utf-8", "ignore")

            if content_type == "text/html":
                return strip_html_tags(raw)
            return raw

    def _send_acknowledgment(self, item, oversized):
        """Send acknowledgment email to the student per §1.4."""
        from inventory.views import send_system_email

        first_name = item.submitter_display_name.split()[0] if item.submitter_display_name else "there"
        submitted_at_ist = item.submitted_at.astimezone(
            timezone.get_fixed_timezone(330)  # IST = UTC+5:30
        ).strftime("%-d %B %Y, %-I:%M %p IST")
        image_count = item.images.count()
        base_url = getattr(settings, "MAGIC_LINK_BASE_URL", "") or ""

        if oversized:
            subject = f'Action needed: your lost item report could not be fully processed'
            body = (
                f"Hi {first_name},\n\n"
                "This is an automated message from TRACE — the TISB Lost & Found system.\n\n"
                "We received your lost item report, but the combined size of the attached images "
                "exceeded the 40 MB limit. Your report has been saved without images.\n\n"
                f"Title: {item.title}\n"
                f"Submitted at: {submitted_at_ist}\n\n"
                "Please resend your report with smaller images (under 15 MB each, under 40 MB total), "
                "or send a description-only email without attachments.\n\n"
                "— TRACE, TISB Lost & Found"
            )
        else:
            subject = f'Received: your lost item report — "{item.title}"'
            body = (
                f"Hi {first_name},\n\n"
                "This is an automated confirmation that TRACE — the TISB Lost & Found system — "
                "has received your lost item report.\n\n"
                "Submission summary\n"
                "------------------\n"
                f"Title:        {item.title}\n"
                f"Submitted at: {submitted_at_ist}\n"
                f"Images:       {image_count} attached\n\n"
                "What happens next\n"
                "-----------------\n"
                "1. Your report is now in the approval queue. A staff member will review it.\n"
                "2. If approved, your report will appear on the \"Students' Lost Items\" page of TRACE, "
                "visible to the school community.\n"
                "3. If a staff member or another student matches your report to a found item, "
                "you will be notified by email at this address.\n"
                "4. To collect any matched item, you must come in person to the school reception. "
                "Items will not be released to anyone other than the rightful owner, in person.\n\n"
                f"You can view all reports you have submitted, and any claims you have made, by visiting:\n"
                f"{base_url}/my-reports/\n\n"
                "This is an automated message — do not reply to this email. "
                "If you need to follow up, contact your Head of Year or the school reception.\n\n"
                "— TRACE, TISB Lost & Found"
            )

        try:
            send_system_email(
                subject=subject,
                message=body,
                recipient_list=[item.email_from],
            )
        except Exception as exc:
            logger.error("Failed to send acknowledgment to %s: %s", item.email_from, exc)
