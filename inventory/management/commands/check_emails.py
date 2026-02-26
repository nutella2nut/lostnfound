import email
import imaplib
from email.header import decode_header, make_header
from email.utils import parseaddr

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.models import StudentLostItem, StudentLostItemImage
from inventory.views import send_system_email


def decode_mime_header(value: str | None) -> str:
    """Decode MIME-encoded email header to a readable string."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


class Command(BaseCommand):
    help = "Fetch unseen emails from the configured mailbox and create StudentLostItem entries."

    def handle(self, *args, **options):
        email_address = getattr(settings, "LF_EMAIL_ADDRESS", "")
        email_password = getattr(settings, "LF_EMAIL_PASSWORD", "")
        imap_host = getattr(settings, "LF_IMAP_HOST", "")
        imap_port = int(getattr(settings, "LF_IMAP_PORT", 993))
        mailbox = getattr(settings, "LF_IMAP_MAILBOX", "INBOX")
        allowed_domain = getattr(settings, "LF_ALLOWED_SENDER_DOMAIN", "@tisb.ac.in")

        if not (email_address and email_password and imap_host):
            self.stdout.write(
                self.style.ERROR(
                    "LF_EMAIL_ADDRESS, LF_EMAIL_PASSWORD, and LF_IMAP_HOST must be set."
                )
            )
            return

        self.stdout.write(
            f"Connecting to IMAP server {imap_host}:{imap_port} as {email_address}..."
        )

        try:
            mail = imaplib.IMAP4_SSL(imap_host, imap_port)
            mail.login(email_address, email_password)
        except Exception as exc:  # pragma: no cover - depends on external server
            self.stdout.write(self.style.ERROR(f"IMAP login failed: {exc}"))
            return

        try:
            mail.select(mailbox)
            status, data = mail.search(None, "UNSEEN")
            if status != "OK":
                self.stdout.write(self.style.ERROR("Failed to search mailbox."))
                return

            message_ids = data[0].split()
            if not message_ids:
                self.stdout.write("No new messages found.")
                return

            created_count = 0

            for num in message_ids:
                status, msg_data = mail.fetch(num, "(RFC822)")
                if status != "OK":
                    continue

                msg = email.message_from_bytes(msg_data[0][1])

                # Deduplication using Message-ID header where possible
                message_id = decode_mime_header(msg.get("Message-ID", "")).strip()
                if (
                    message_id
                    and StudentLostItem.objects.filter(
                        email_subject=message_id
                    ).exists()
                ):
                    # Already processed
                    continue

                raw_from = msg.get("From", "")
                _, from_email = parseaddr(raw_from)
                from_email = from_email.strip().lower()

                if allowed_domain and not from_email.endswith(allowed_domain):
                    # Skip senders outside the allowed domain
                    continue

                subject = decode_mime_header(msg.get("Subject", "")).strip()

                # Extract plain-text body; fall back to first text part
                body_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = part.get("Content-Disposition", "")
                        if content_type == "text/plain" and "attachment" not in (
                            content_disposition or ""
                        ):
                            try:
                                body_text = (
                                    part.get_payload(decode=True) or b""
                                ).decode(part.get_content_charset() or "utf-8", "ignore")
                            except Exception:
                                body_text = (
                                    part.get_payload(decode=True) or b""
                                ).decode("utf-8", "ignore")
                            break
                else:
                    try:
                        body_text = (msg.get_payload(decode=True) or b"").decode(
                            msg.get_content_charset() or "utf-8", "ignore"
                        )
                    except Exception:
                        body_text = (msg.get_payload(decode=True) or b"").decode(
                            "utf-8", "ignore"
                        )

                title = subject or (body_text.splitlines()[0][:255] if body_text else "")

                student_item = StudentLostItem.objects.create(
                    title=title or "Untitled Lost Item",
                    description=body_text or "",
                    email_subject=subject or "",
                    email_from=from_email,
                )

                # Extract image attachments
                image_created = False
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type.startswith("image/"):
                            filename = decode_mime_header(
                                part.get_filename() or "uploaded.jpg"
                            )
                            img_bytes = part.get_payload(decode=True) or b""
                            if not img_bytes:
                                continue
                            image_file = ContentFile(img_bytes, name=filename)
                            StudentLostItemImage.objects.create(
                                student_item=student_item,
                                image=image_file,
                            )
                            image_created = True

                created_count += 1

                # Send acknowledgement email to the student
                if from_email:
                    send_system_email(
                        subject="Lost & Found submission received",
                        message=(
                            "We have received your lost item request and it is pending "
                            "approval by the Lost & Found team."
                        ),
                        recipient_list=[from_email],
                    )

                # Optionally mark the message as seen
                mail.store(num, "+FLAGS", "\\Seen")

            self.stdout.write(
                self.style.SUCCESS(f"Created {created_count} new StudentLostItem(s).")
            )

        finally:
            try:
                mail.logout()
            except Exception:
                pass

